# Cấu trúc Message<T>: phần dữ liệu và tập header trong Spring Messaging

## 1. Message là gì?

Trong Spring Messaging, **Message<T>** là một phong bì dữ liệu chuẩn hóa để các thành phần trong ứng dụng trao đổi thông tin. Mỗi message gồm hai phần:

1. **Payload:** nội dung chính mà bên nhận cần xử lý.
2. **Headers:** tập metadata mô tả ngữ cảnh, định tuyến hoặc cách xử lý payload.

Có thể mô hình hóa:

~~~text
Message<T>
+--------------------------------------+
| payload: T                           |
|                                      |
| headers: MessageHeaders              |
|   id                                 |
|   timestamp                          |
|   contentType                        |
|   correlationId (nếu ứng dụng cần)   |
|   tenantId (nếu ứng dụng cần)        |
+--------------------------------------+
~~~

Ví dụ, khi phát sự kiện đơn hàng, payload có thể chứa mã đơn và tổng tiền. Headers có thể chứa mã tenant, correlation ID hoặc loại nội dung. Nhờ đó, handler nhận được cả dữ liệu nghiệp vụ lẫn thông tin cần thiết để theo dõi và định tuyến message.

Message<T> là abstraction của Spring Messaging, nằm trong package org.springframework.messaging. Nó không phải một giao thức mạng hay một message broker. Message có thể được truyền giữa các thành phần trong cùng tiến trình, qua channel, hoặc được adapter ánh xạ sang một giao thức bên ngoài.

## 2. Payload: phần dữ liệu chính

### 2.1 Payload mang nội dung gì?

Payload là đối tượng mà message muốn chuyển tới bên nhận. Kiểu dữ liệu có thể là:

- String cho văn bản hoặc nội dung đơn giản.
- byte[] cho dữ liệu nhị phân.
- DTO hoặc Java record cho lệnh, sự kiện và dữ liệu nghiệp vụ.
- Object được serializer hoặc message converter hỗ trợ.
- Kiểu dữ liệu khác mà thành phần nhận có thể hiểu và xử lý.

Ví dụ, payload của sự kiện OrderCreated có thể là:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        long totalAmount
) {
}
~~~

Payload này mô tả sự kiện nghiệp vụ. Các trường orderId, customerId và totalAmount thuộc nội dung mà consumer cần hiểu để thực hiện công việc của mình.

### 2.2 Chọn kiểu payload rõ ràng

Nên dùng kiểu cụ thể để thể hiện hợp đồng dữ liệu:

- Message<OrderCreated> cho message chứa sự kiện tạo đơn hàng.
- Message<CreateOrderCommand> cho message chứa yêu cầu tạo đơn.
- Message<String> cho message văn bản.
- Message<byte[]> cho dữ liệu nhị phân.

Khi một thành phần cần xử lý nhiều loại payload, có thể dùng Message<?>. Dấu ? có nghĩa là kiểu payload chưa được xác định cụ thể tại vị trí khai báo; bên xử lý cần kiểm tra hoặc chuyển đổi phù hợp trước khi sử dụng.

Không nên lạm dụng Message<Object> chỉ để gom mọi loại message. Message<OrderCreated> và Message<Object> là hai kiểu generic khác nhau; generic của Java không có tính đồng biến như vậy. Message<?> thường là lựa chọn phù hợp hơn khi cần nhận message với nhiều kiểu payload.

### 2.3 Payload và việc chuyển đổi dữ liệu

Payload trong bộ nhớ có thể là object Java. Khi đi qua ranh giới giao thức hoặc broker, object thường cần được chuyển thành dạng dữ liệu mà bên nhận có thể giải mã, chẳng hạn JSON hoặc byte array.

Spring Messaging có abstraction MessageConverter cho việc chuyển đổi payload. Cần phân biệt ba việc:

- Tạo một message trong ứng dụng.
- Chuyển payload từ object sang định dạng truyền tải.
- Chuyển dữ liệu nhận được trở lại thành kiểu payload mà consumer mong đợi.

Có Message<T> không có nghĩa object payload tự động được serialize hoặc mọi adapter đều dùng cùng một converter. Cần cấu hình converter và thống nhất schema giữa bên gửi và bên nhận.

## 3. Headers: metadata đi kèm payload

### 3.1 Vai trò của headers

Headers mô tả message và ngữ cảnh xử lý. Chúng không nên trở thành nơi chứa toàn bộ dữ liệu nghiệp vụ.

Một số nhóm metadata thường gặp:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Nhận diện | id, timestamp | Nhận diện message và thời điểm tạo |
| Định dạng | contentType | Gợi ý cách diễn giải hoặc chuyển đổi payload |
| Tương quan | correlationId, traceId | Liên kết nhiều bước trong cùng một luồng xử lý |
| Định tuyến | destination hoặc thông tin route | Chỉ ra đích nhận theo cơ chế tích hợp |
| Ngữ cảnh ứng dụng | tenantId, locale | Bổ sung ngữ cảnh cần thiết cho xử lý |
| Điều khiển giao nhận | delivery attempt hoặc thông tin ACK theo adapter | Hỗ trợ chính sách giao nhận của hạ tầng |

Các tên trong bảng là ví dụ về metadata. Không phải tất cả đều là header mặc định của Spring Messaging. MessageHeaders định nghĩa các tên chuẩn như id, timestamp và contentType; các header như tenantId, correlationId hoặc traceId thường do ứng dụng, thư viện tích hợp hoặc adapter quy định.

Một số header đặc thù như replyChannel và errorChannel có thể xuất hiện trong các luồng tích hợp của Spring Integration. Không nên giả định chúng tồn tại trong mọi message Spring Messaging.

### 3.2 Phân biệt payload và header

| Tiêu chí | Payload | Header |
|---|---|---|
| Trả lời câu hỏi | Message mang nội dung gì? | Message có ngữ cảnh hoặc metadata nào? |
| Ví dụ | OrderCreated, CreateOrderCommand | correlationId, tenantId, contentType |
| Cấu trúc | Theo schema nghiệp vụ | Theo quy ước metadata |
| Cách dùng | Consumer đọc và xử lý dữ liệu chính | Hạ tầng hoặc handler dùng để định tuyến, theo dõi và điều khiển |
| Kích thước | Có thể chứa dữ liệu nghiệp vụ lớn | Nên nhỏ, gọn và có ý nghĩa rõ ràng |

Một quy tắc hữu ích: nếu consumer cần trường dữ liệu để quyết định nghiệp vụ, trường đó thường thuộc payload. Nếu trường chỉ mô tả cách theo dõi, định dạng hoặc chuyển tiếp message, nó thường phù hợp với header.

Ví dụ, totalAmount của đơn hàng nên nằm trong payload vì đó là dữ liệu nghiệp vụ. correlationId phù hợp với header vì nó liên kết message với một luồng xử lý. Nếu tenantId quyết định quyền sở hữu dữ liệu, phải xác minh nó từ ngữ cảnh bảo mật đáng tin cậy; không được coi một header do client gửi lên là bằng chứng xác thực tenant.

### 3.3 Header không phải nơi lưu bí mật

Không đưa password, access token, private key hoặc dữ liệu nhạy cảm vào header nếu không có yêu cầu và biện pháp bảo vệ rõ ràng. Headers có thể được ghi log, hiển thị trong tracing, chuyển qua broker hoặc được adapter ánh xạ ra giao thức khác.

Cũng không nên đưa payload lớn vào header. Dữ liệu nghiệp vụ nên nằm trong payload hoặc một kho lưu trữ chuyên dụng; header chỉ giữ metadata cần thiết để tham chiếu.

## 4. Các API cốt lõi

### 4.1 Message<T>

Message<T> là interface đại diện cho một message. Hai phương thức quan trọng:

- getPayload() trả về payload có kiểu T.
- getHeaders() trả về tập MessageHeaders.

Consumer có thể nhận Message<?> nếu không cần biết kiểu payload tại thời điểm khai báo, hoặc dùng Message<OrderCreated> khi hợp đồng đầu vào đã rõ.

### 4.2 MessageHeaders

MessageHeaders là kiểu chứa các header của message. Nó triển khai Map<String, Object> để truy cập theo tên header, đồng thời cung cấp các hằng số cho một số header chuẩn:

- MessageHeaders.ID
- MessageHeaders.TIMESTAMP
- MessageHeaders.CONTENT_TYPE

Ví dụ truy cập:

~~~java
Object tenantId = message.getHeaders().get("tenantId");
Object correlationId = message.getHeaders().get("correlationId");
~~~

Có thể dùng API lấy giá trị theo kiểu trong những trường hợp phù hợp; nếu lấy bằng Map.get, cần kiểm tra và chuyển kiểu an toàn.

MessageHeaders cung cấp một view chỉ đọc của tập header. Sau khi message được tạo, không nên sửa map header trực tiếp. Hãy dùng builder hoặc accessor để tạo message mới có metadata đã cập nhật.

Lưu ý: map header không cho phép thay đổi trực tiếp không đồng nghĩa toàn bộ message được sao chép sâu. Giá trị lưu trong header có thể là object có trạng thái mutable; payload cũng có thể là object mutable. Nếu các thành phần cùng giữ tham chiếu tới object đó, thay đổi nội dung object có thể được quan sát ở nơi khác. Ưu tiên payload và giá trị header bất biến, chẳng hạn record, String, UUID hoặc kiểu value object phù hợp.

### 4.3 GenericMessage<T>

GenericMessage<T> là implementation cơ bản của Message<T>. Trong phần lớn trường hợp tạo message ở tầng ứng dụng, có thể dùng MessageBuilder để không phải tự quản lý việc tạo MessageHeaders.

### 4.4 MessageBuilder<T>

MessageBuilder là API thuận tiện để xây dựng message. Hai cách khởi tạo thường dùng:

- MessageBuilder.withPayload(payload) tạo message từ payload mới.
- MessageBuilder.fromMessage(existingMessage) tạo builder dựa trên message hiện có.

Các thao tác thường gặp:

- setHeader(name, value) đặt hoặc thay giá trị header.
- setHeaderIfAbsent(name, value) chỉ đặt khi header chưa có.
- removeHeader(name) loại bỏ một header.
- copyHeaders(map) sao chép các header từ map.
- copyHeadersIfAbsent(map) chỉ sao chép các header chưa tồn tại.
- build() tạo message hoàn chỉnh.

Dùng builder giúp tạo một message mới có cấu trúc nhất quán. Không sửa trực tiếp MessageHeaders sau khi message đã được phát đi.

## 5. Tạo và đọc Message<T> bằng Java

Ví dụ sau là một lớp Java 17 hoàn chỉnh, sử dụng dependency org.springframework:spring-messaging. Trong dự án Maven hoặc Gradle, hãy khai báo dependency này và quản lý phiên bản đồng bộ bằng Spring Framework BOM hoặc Spring Boot dependency management.

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageStructureDemo {

    record OrderCreated(String orderId, BigDecimal total) {
    }

    public static void main(String[] args) {
        OrderCreated payload = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125000")
        );

        Message<OrderCreated> message = MessageBuilder
                .withPayload(payload)
                .setHeader("tenantId", "acme")
                .setHeader("correlationId", "corr-001")
                .build();

        System.out.println(message.getPayload().orderId());
        System.out.println(message.getPayload().total());
        System.out.println(message.getHeaders().get("tenantId"));
        System.out.println(message.getHeaders().get("correlationId"));
    }
}
~~~

Kết quả khi chạy:

~~~text
ORD-1001
125000
acme
corr-001
~~~

Trong ví dụ:

- OrderCreated là kiểu payload cụ thể.
- Message<OrderCreated> biểu diễn message có payload kiểu OrderCreated.
- tenantId và correlationId là metadata do ứng dụng định nghĩa.
- getPayload() trả về object nghiệp vụ.
- getHeaders() cung cấp metadata đi kèm.

Chương trình cần có spring-messaging và các dependency bắc cầu tương ứng trong classpath. Có thể chạy lớp main bằng IDE hoặc task chạy Java của dự án sau khi Maven/Gradle đã resolve dependency.

## 6. Tạo message mới từ message hiện có

Trong một pipeline, handler đôi khi cần bổ sung metadata hoặc thay payload. Hãy tạo message mới từ message gốc bằng fromMessage:

~~~java
Message<OrderCreated> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("source", "order-service")
        .setHeaderIfAbsent("schemaVersion", 1)
        .build();
~~~

Builder sao chép thông tin message hiện có để tạo message mới. Payload vẫn là object cũ nếu không thay payload; thao tác trên không tự tạo bản sao sâu của object payload.

Nếu cần thay payload, dùng builder với payload mới hoặc phương thức thay payload mà builder hỗ trợ trong phiên bản đang sử dụng. Khi thay đổi kiểu payload, hãy khai báo kiểu generic tương ứng và bảo đảm consumer sau đó hiểu schema mới.

Không nên sao chép tất cả header từ một nguồn không đáng tin cậy rồi chuyển tiếp nguyên trạng. Với message đi qua ranh giới hệ thống, hãy chọn lọc header được phép giữ lại, chuẩn hóa tên và kiểu dữ liệu, loại bỏ metadata nội bộ không còn ý nghĩa và xác minh các trường ảnh hưởng tới quyền truy cập.

## 7. MessageHeaderAccessor và header chuyên biệt

Khi cần thao tác header có kiểm soát hoặc làm việc với metadata đặc thù của giao thức, Spring cung cấp MessageHeaderAccessor. Các accessor chuyên biệt mở rộng cách truy cập này, ví dụ accessor dành cho STOMP hoặc Simp messaging.

Accessor hữu ích khi:

- Cần đọc hoặc thiết lập một nhóm header liên quan.
- Cần làm việc với header native của giao thức.
- Cần phân biệt header ứng dụng với header do framework quản lý.
- Cần tạo message sau khi hoàn thành việc cập nhật metadata.

Trong lúc xây dựng message, accessor có thể cung cấp một giai đoạn thao tác header mutable. Khi message được hoàn tất và công bố, headers được chuyển sang trạng thái chỉ đọc theo cơ chế của framework. Hãy tuân thủ vòng đời của accessor và tránh giữ một accessor mutable để thay đổi message sau khi đã gửi.

Với nhu cầu thông thường như thêm tenantId hoặc correlationId, MessageBuilder thường dễ đọc và đủ dùng. Dùng accessor chuyên biệt khi cần tính năng cụ thể mà builder tổng quát không thể hiện rõ.

## 8. Vòng đời message trong một luồng xử lý

Một luồng messaging thường có các bước:

~~~text
Payload nghiệp vụ
       |
       v
MessageBuilder.withPayload(...)
       |
       v
Message<T>
  + payload
  + headers
       |
       v
MessageChannel.send(message)
       |
       v
MessageHandler.handleMessage(message)
       |
       +---- đọc payload
       |
       +---- đọc metadata
       |
       +---- xử lý hoặc tạo message mới
~~~

Các abstraction có trách nhiệm khác nhau:

- Message<T> mô tả dữ liệu và metadata.
- MessageChannel là điểm gửi message.
- MessageHandler là thành phần nhận và xử lý message.
- Adapter hoặc broker có thể chuyển message qua ranh giới hệ thống.

Việc một channel chấp nhận message không có nghĩa xử lý nghiệp vụ đã thành công. Nếu cần xác nhận hoàn tất, retry hoặc bảo đảm giao nhận, hãy dùng cơ chế phù hợp của channel, adapter hoặc broker đang triển khai.

## 9. Các lưu ý khi thiết kế payload và headers

### 9.1 Giữ payload ổn định và có phiên bản

Payload là hợp đồng dữ liệu giữa producer và consumer. Khi schema thay đổi, cần cân nhắc tương thích ngược và xuôi:

- Thêm trường mới với quy tắc mặc định phù hợp.
- Tránh đổi tên hoặc đổi kiểu trường đang được consumer sử dụng mà không có kế hoạch chuyển đổi.
- Định nghĩa cách xử lý trường thiếu, trường thừa và giá trị không hợp lệ.
- Cân nhắc trường phiên bản schema trong payload hoặc metadata nếu hệ thống cần quản lý nhiều phiên bản.

Không giả định serializer có thể tự giải quyết mọi thay đổi schema. Producer và consumer cần thống nhất cách diễn giải dữ liệu.

### 9.2 Dùng header cho metadata ổn định

Header nên nhỏ, rõ nghĩa và có quy ước nhất quán. Ví dụ:

- correlationId để nối các message trong cùng một yêu cầu.
- traceId để liên kết với trace phân tán nếu hệ thống sử dụng tracing.
- tenantId để cung cấp ngữ cảnh tenant sau khi đã xác minh nguồn đáng tin cậy.
- contentType để mô tả định dạng nội dung khi converter hoặc adapter cần dùng.

Tránh tạo nhiều tên header gần nghĩa như requestId, reqId, correlation, correlationId mà không có quy ước chung.

### 9.3 Không phụ thuộc vào việc mọi header đều đi xuyên hệ thống

Khi message được chuyển qua HTTP, WebSocket, STOMP, JMS, AMQP hoặc Kafka, adapter có thể ánh xạ header sang metadata native của giao thức. Một số header nội bộ có thể bị bỏ qua hoặc đổi cách biểu diễn.

Nếu một metadata bắt buộc phải đến consumer, hãy xác định rõ cách serialize hoặc map nó, kiểm thử ở ranh giới tích hợp và không chỉ dựa vào việc nó tồn tại trong MessageHeaders ở bộ nhớ.

## 10. Lỗi phổ biến

- **Nhầm payload với headers:** đưa dữ liệu nghiệp vụ vào metadata khiến schema khó quản lý và consumer khó hiểu.
- **Dùng Message<Object> cho mọi loại message:** làm mất thông tin kiểu hữu ích; dùng kiểu cụ thể hoặc Message<?> đúng mục đích.
- **Coi headers là map có thể sửa tự do:** MessageHeaders là cấu trúc chỉ đọc; tạo message mới qua builder hoặc accessor.
- **Cho rằng message bất biến sâu:** payload hoặc giá trị header vẫn có thể tham chiếu object mutable.
- **Sao chép mọi header từ đầu vào:** có thể chuyển tiếp dữ liệu không đáng tin cậy, metadata nội bộ hoặc thông tin nhạy cảm.
- **Coi correlation ID là định danh nghiệp vụ:** correlation ID phục vụ liên kết luồng xử lý; nó không thay thế khóa đơn hàng hoặc định danh domain.
- **Đưa secret vào header:** metadata có thể bị log hoặc chuyển tiếp qua nhiều hệ thống.
- **Giả định header luôn được giữ nguyên qua broker:** adapter có thể ánh xạ hoặc loại bỏ header; cần kiểm thử việc truyền metadata.
- **Không thống nhất kiểu dữ liệu của header:** một producer gửi số, producer khác gửi chuỗi sẽ gây lỗi khi consumer chuyển kiểu.
- **Dùng header để thay thế payload schema:** consumer sẽ phụ thuộc vào nhiều metadata rời rạc và khó kiểm soát hợp đồng.

## 11. Checklist tự đánh giá

Bạn đã nắm được cấu trúc message khi có thể giải thích:

- Message<T> gồm những thành phần nào?
- Payload khác headers ở trách nhiệm và cách sử dụng ra sao?
- Vì sao nên khai báo Message<OrderCreated> thay vì luôn dùng Message<Object>?
- MessageHeaders cung cấp những header chuẩn nào?
- Vì sao không thể sửa trực tiếp header map sau khi message được tạo?
- MessageBuilder.withPayload và MessageBuilder.fromMessage khác nhau thế nào?
- Khi nào nên dùng MessageHeaderAccessor?
- Vì sao message envelope chỉ bất biến ở mức cấu trúc, không bảo đảm deep immutability?
- Vì sao không nên tin tenantId hoặc quyền truy cập chỉ vì chúng xuất hiện trong header đầu vào?
- Điều gì có thể xảy ra với headers khi message đi qua adapter hoặc broker?

Khi có thể tạo một Message<T>, đọc đúng payload và metadata, tạo message mới có kiểm soát, đồng thời giải thích được ranh giới của headers, bạn đã nắm được nền tảng dữ liệu của Spring Messaging.

## 12. Tài liệu tra cứu

- Spring Framework Reference Documentation: phần Messaging và các API Message, MessageHeaders, MessageBuilder.
- Javadoc của package org.springframework.messaging.
- Javadoc của package org.springframework.messaging.support, đặc biệt GenericMessage, MessageBuilder và MessageHeaderAccessor.
- Tài liệu Spring Integration khi cần tìm hiểu thêm các header và metadata đặc thù của integration flow.

Khi tra cứu, hãy dùng tài liệu đúng phiên bản Spring Framework hoặc Spring Boot của dự án. API cụ thể và cách tích hợp có thể thay đổi giữa các phiên bản lớn.