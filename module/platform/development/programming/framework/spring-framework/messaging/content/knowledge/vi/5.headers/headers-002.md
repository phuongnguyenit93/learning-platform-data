# Header chuẩn, header ứng dụng và quy tắc đặt tên

Trong Spring Messaging, một Message gồm payload và một tập header. Payload chứa dữ liệu chính mà consumer cần xử lý; header chứa metadata giúp định danh, định tuyến, chuyển đổi, theo dõi và điều khiển cách message được xử lý.

Một header không đơn thuần là một cặp key-value tùy ý. Tùy vị trí trong luồng, nó có thể là header chuẩn do Spring định nghĩa, header nội bộ phục vụ định tuyến, header của protocol như JMS/STOMP hoặc metadata do ứng dụng tự đặt. Hiểu rõ các nhóm này giúp tránh xung đột tên, mất metadata khi chuyển transport và vô tình tin dữ liệu do client gửi lên.

## 1. Header nằm ở đâu trong Message?

Hợp đồng Message<T> của Spring có hai thành phần:

- **Payload:** đối tượng dữ liệu, ví dụ OrderCreated, một chuỗi JSON hoặc một command.
- **Headers:** tập metadata được truy cập qua MessageHeaders.

Ví dụ một message có thể mang payload là mã đơn hàng, đồng thời có header chứa correlation ID, content type và phiên bản schema. Consumer đọc payload để thực hiện nghiệp vụ; header hỗ trợ xác định message thuộc luồng xử lý nào và phải được diễn giải ra sao.

~~~text
Message<T>
├── payload
│   └── OrderCreated(...)
└── headers
    ├── id
    ├── timestamp
    ├── contentType
    ├── appCorrelationId
    └── appSchemaVersion
~~~

Header không thay thế payload. Nếu dữ liệu là một phần của hợp đồng nghiệp vụ mà consumer cần hiểu, lưu trữ hoặc kiểm tra, hãy cân nhắc đặt dữ liệu đó trong payload. Header phù hợp hơn với metadata phục vụ truyền tải, định tuyến, quan sát và xử lý.

## 2. Các header chuẩn của Spring MessageHeaders

Lớp org.springframework.messaging.MessageHeaders định nghĩa một số tên header dùng chung. Hãy dùng hằng số của lớp này thay vì tự gõ chuỗi để tránh sai chính tả.

| Hằng số | Tên key | Ý nghĩa và kiểu giá trị |
|---|---|---|
| MessageHeaders.ID | id | UUID nhận diện một message instance |
| MessageHeaders.TIMESTAMP | timestamp | Long biểu diễn thời điểm tạo message, theo epoch milliseconds |
| MessageHeaders.CONTENT_TYPE | contentType | MimeType mô tả định dạng payload |
| MessageHeaders.REPLY_CHANNEL | replyChannel | MessageChannel hoặc tên channel dùng cho reply |
| MessageHeaders.ERROR_CHANNEL | errorChannel | MessageChannel hoặc tên channel dùng cho error |

### 2.1. id và timestamp

Spring tự quản lý id và timestamp khi tạo MessageHeaders thông thường. ID là UUID để phân biệt một message instance; timestamp ghi nhận thời điểm message được tạo.

Không dùng id của Spring làm khóa nghiệp vụ, khóa idempotency hoặc correlation ID xuyên suốt một quy trình. Khi ứng dụng tạo message mới từ message cũ, message instance và metadata hệ thống có thể được tạo lại. Nếu cần nhận diện một đơn hàng, sự kiện hoặc yêu cầu qua nhiều service, hãy tạo header nghiệp vụ riêng như appEventId hoặc appCorrelationId.

Tương tự, timestamp của Spring không nhất thiết là thời điểm nghiệp vụ xảy ra. Nếu cần biết một đơn hàng được tạo lúc nào, hãy lưu thời gian đó trong payload hoặc header nghiệp vụ appOccurredAt. Đừng đánh đồng thời điểm tạo message với thời điểm xảy ra sự kiện.

Không tự đặt MessageHeaders.ID bằng giá trị tùy ý. Javadoc quy định ID được sinh tự động và chỉ nên khôi phục rõ ràng trong tình huống deserialize message đã được serialize trước đó.

### 2.2. contentType

contentType mô tả định dạng của payload để converter hoặc consumer diễn giải đúng. Ví dụ: application/json, text/plain hoặc application/octet-stream.

Trong Spring Messaging, content type được biểu diễn bằng MimeType. Khi có thể, dùng MessageHeaderAccessor.setContentType hoặc hằng số MessageHeaders.CONTENT_TYPE với MimeType tương ứng thay vì lưu một chuỗi không thống nhất.

Không khai báo contentType là application/json nếu payload thực tế là một object hoặc định dạng khác mà converter không thể serialize thành JSON. Header chỉ là metadata; converter và payload phải thực sự tương thích.

### 2.3. replyChannel và errorChannel

replyChannel và errorChannel là metadata phục vụ định tuyến nội bộ trong các luồng messaging của Spring. Giá trị có thể là một MessageChannel hoặc tên bean/channel tùy cơ chế sử dụng.

Đây không phải là trường nghiệp vụ như orderId hay tenantId. Các giá trị này có thể tham chiếu đến object nội bộ của ứng dụng, vì vậy không nên tùy tiện serialize hoặc chuyển nguyên vẹn chúng sang broker hay service khác.

## 3. MessageHeaders là immutable

MessageHeaders triển khai Map<String, Object>, nhưng đối tượng này là immutable. Các thao tác thay đổi trực tiếp như put, remove, clear hoặc putAll sẽ ném UnsupportedOperationException.

Ví dụ sau không hợp lệ:

~~~java
message.getHeaders().put("appCorrelationId", "corr-42");
~~~

Muốn bổ sung hoặc thay đổi header, hãy tạo Message mới bằng MessageBuilder hoặc dùng MessageHeaderAccessor.

Cách đơn giản với MessageBuilder:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("appCorrelationId", "corr-42")
        .setHeader("appSchemaVersion", 1)
        .build();

Message<String> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("appSource", "checkout")
        .build();
~~~

Message mới giữ payload và các header đã được copy, sau đó thêm hoặc thay giá trị appSource. Message ban đầu không bị sửa trực tiếp.

Các thao tác thường dùng:

- setHeader(name, value): đặt hoặc thay giá trị header.
- setHeaderIfAbsent(name, value): chỉ đặt nếu key chưa có giá trị.
- removeHeader(name): bỏ một header.
- copyHeaders(map): copy nhiều header và có thể ghi đè key đã tồn tại.
- copyHeadersIfAbsent(map): chỉ copy key chưa tồn tại.
- removeHeaders(patterns): loại bỏ các header khớp pattern.

Khi dùng copyHeaders, cần hiểu rõ việc ghi đè. Nếu metadata đến từ nhiều nguồn, hãy ưu tiên copyHeadersIfAbsent hoặc chỉ copy các key đã được cho phép.

## 4. Dùng MessageHeaderAccessor khi cần thao tác header có kiểm soát

MessageHeaderAccessor là wrapper cung cấp API đọc và chỉnh sửa header. Nó còn có các accessor chuyên biệt cho native header, STOMP, JMS và những protocol khác.

Ví dụ tạo message mới:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("appCorrelationId", "corr-42");
accessor.setHeaderIfAbsent("appSource", "checkout");
accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);

MessageHeaders headers = accessor.getMessageHeaders();
Message<String> message = MessageBuilder.createMessage(
        "{\"orderId\":\"order-42\"}",
        headers
);
~~~

Khi gọi getMessageHeaders(), accessor mặc định hoàn tất việc xây dựng header và không còn cho phép chỉnh sửa qua chính accessor đó; MessageHeaders trả về cũng immutable. Đây là hành vi giúp tránh việc một message đã được chuyển sang thành phần khác lại bị sửa âm thầm.

Nếu có lý do kỹ thuật cần để header mutable trong một giai đoạn khởi tạo ngắn, MessageHeaderAccessor có setLeaveMutable(true). Khi đã hoàn tất, phải gọi setImmutable() để đóng khả năng chỉnh sửa. Cách này phù hợp với quá trình khởi tạo trong một thread; không nên truyền một bộ header còn mutable qua nhiều thread hoặc chia sẻ cho nhiều thành phần.

Để sửa message đã có, có thể lấy mutable accessor:

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(message);

accessor.setHeader("appTenantId", "tenant-7");

Message<String> updated = MessageBuilder.createMessage(
        message.getPayload(),
        accessor.getMessageHeaders()
);
~~~

Hãy chỉ sửa những metadata mà thành phần hiện tại có quyền sở hữu. Nếu một header chứa thông tin xác thực hoặc tenant do hệ thống xác lập, không để dữ liệu từ client ghi đè nó.

## 5. Header chuẩn, header framework và header ứng dụng

Trong một hệ thống thực tế, nên phân loại header theo nguồn gốc và phạm vi sử dụng.

| Nhóm | Ví dụ | Ai định nghĩa? | Quy tắc xử lý |
|---|---|---|---|
| Spring core | id, timestamp, contentType, replyChannel, errorChannel | Spring Framework | Dùng hằng số/API chuẩn; tránh tự ghi đè |
| Spring messaging/SIMP | destination, message type, session ID, subscription ID, user | Spring messaging | Dùng accessor chuyên biệt; không xem là metadata nghiệp vụ |
| Protocol-native | JMS correlation ID, STOMP destination, receipt, content-type | Protocol/provider | Dùng adapter/accessor tương ứng |
| Application-specific | appCorrelationId, appTenantId, appSchemaVersion | Ứng dụng | Có namespace, kiểu dữ liệu và contract được tài liệu hóa |

Không nên gom tất cả thành một nhóm "custom header". Một giá trị có thể là header chuẩn ở tầng Spring nhưng lại được chuyển đổi thành native header ở tầng transport. Ngược lại, header do broker gửi vào có thể chỉ tồn tại trong phần native header và chưa được chuyển thành header nghiệp vụ của ứng dụng.

## 6. Native headers và header của protocol

NativeMessageHeaderAccessor cung cấp cơ chế lưu header lấy từ nguồn bên ngoài như broker. Những header này được giữ trong một sub-map riêng có key NativeMessageHeaderAccessor.NATIVE_HEADERS (giá trị key là nativeHeaders).

Việc tách riêng giúp Spring phân biệt:

- **Processing headers:** metadata mà Spring dùng để định tuyến hoặc xử lý bên trong.
- **Native headers:** metadata thuộc protocol hoặc message broker, cần được giữ lại khi encode/decode hoặc gửi/nhận qua transport.

NativeMessageHeaderAccessor cung cấp các thao tác như setNativeHeader, addNativeHeader, getNativeHeader, getFirstNativeHeader, removeNativeHeader và toNativeHeaderMap. Một số protocol có accessor chuyên biệt kế thừa lớp này.

### 6.1. Header JMS

Khi dùng spring-jms, JmsHeaders và JmsMessageHeaderAccessor giúp làm việc với metadata của Jakarta Messaging. Các thuộc tính có thể gặp gồm:

- correlation ID;
- destination;
- delivery mode;
- expiration;
- message ID;
- priority;
- reply-to;
- redelivered;
- type;
- timestamp.

Dùng JmsHeaders và JmsMessageHeaderAccessor thay vì tự đoán tên key. Ví dụ đọc correlation ID đã được ánh xạ vào Spring Message:

~~~java
JmsMessageHeaderAccessor jmsAccessor =
        JmsMessageHeaderAccessor.wrap(message);

String correlationId = jmsAccessor.getCorrelationId();
Boolean redelivered = jmsAccessor.getRedelivered();
~~~

Các thuộc tính JMS có thể được ánh xạ giữa JMS message header, JMS property và Spring Message header tùy loại thuộc tính. Không giả định mọi application header đều tự động trở thành JMS property. Cần kiểm tra cấu hình MessageConverter và mapping của integration đang sử dụng.

JMS property name có giới hạn cú pháp theo quy tắc Java identifier. Tránh dấu chấm, dấu gạch ngang hoặc khoảng trắng nếu header cần đi qua JMS. Ngoài ra, các prefix dành riêng của JMS như JMSX và JMS_ không nên dùng cho header nghiệp vụ do ứng dụng tự định nghĩa.

### 6.2. Header STOMP và WebSocket

Khi dùng STOMP trên WebSocket, StompHeaderAccessor quản lý header của STOMP frame. Lớp này kế thừa SimpMessageHeaderAccessor và NativeMessageHeaderAccessor.

Các header protocol có thể gặp gồm destination, content-type, subscription, receipt, ack, message-id và heart-beat. Các header processing của Spring có thể gồm destination, message type, session ID, session attributes, subscription ID và user.

Một số API thường dùng:

- StompHeaderAccessor.getDestination() hoặc setDestination(...).
- StompHeaderAccessor.setNativeHeader(name, value).
- StompHeaderAccessor.getFirstNativeHeader(name).
- SimpMessageHeaderAccessor.getSessionId() và getUser().

Ví dụ đọc một native header do STOMP client gửi:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
String clientVersion = accessor.getFirstNativeHeader("appClientVersion");
String destination = accessor.getDestination();
~~~

Header destination của STOMP và destination processing của Spring có quan hệ ánh xạ, nhưng không nên tự sửa raw map nếu accessor đã cung cấp API chuyên biệt. Việc chuyển từ processing header sang STOMP frame còn phụ thuộc command và hướng gửi message.

### 6.3. Không nhầm native header với application header

Native header phản ánh protocol bên ngoài. Application header phản ánh metadata do contract của ứng dụng định nghĩa.

Ví dụ appCorrelationId là header nghiệp vụ có thể cần tồn tại khi event đi qua JMS rồi được phát tiếp qua STOMP. JMS correlation ID hoặc STOMP receipt lại là metadata của từng protocol. Khi bridge giữa hai protocol, ứng dụng phải xác định header nào cần được ánh xạ, đổi tên, chuẩn hóa hoặc loại bỏ.

Không copy nguyên toàn bộ nativeHeaders từ một protocol sang protocol khác. Một key hợp lệ ở STOMP có thể không hợp lệ hoặc không có ý nghĩa trong JMS. Hãy dùng một allowlist mapping có chủ đích.

## 7. Quy tắc đặt tên application header

Tên header là một phần của contract giữa producer và consumer. Nếu không có quy ước, các module dễ tạo key trùng nhau, sai kiểu dữ liệu hoặc hiểu cùng một tên theo hai ý nghĩa khác nhau.

### 7.1. Dùng namespace riêng

Đặt prefix cho header do ứng dụng sở hữu. Ví dụ:

| Header | Ý nghĩa | Kiểu gợi ý |
|---|---|---|
| appCorrelationId | ID liên kết các message trong một workflow | String |
| appCausationId | ID của message/event gây ra message hiện tại | String |
| appEventId | ID ổn định của event nghiệp vụ | String hoặc UUID dạng chuỗi |
| appTenantId | Tenant đã được xác định bởi server | String |
| appSchemaVersion | Phiên bản contract payload | Integer hoặc String |
| appSource | Tên service hoặc thành phần phát message | String |
| appOccurredAt | Thời điểm nghiệp vụ xảy ra | Instant trong payload hoặc epoch/string theo contract |
| appTraceId | Trace ID phục vụ quan sát | String |

Prefix app chỉ là ví dụ. Với hệ thống có nhiều team, có thể dùng prefix ngắn đã được tổ chức thống nhất như order, billing hoặc một namespace của tổ chức. Điều quan trọng là không dùng các key chung chung như type, source, status hoặc id nếu chúng dễ va chạm với header của framework hay protocol.

### 7.2. Chọn quy tắc tương thích nhiều transport

Tên header trong Spring là String và có thể biểu diễn bằng nhiều kiểu đặt tên. Tuy nhiên, nếu message sẽ đi qua nhiều transport, nên chọn tập ký tự có khả năng tương thích rộng.

Quy ước khuyến nghị cho header dùng chung giữa Spring, JMS và STOMP:

- Bắt đầu bằng chữ cái.
- Chỉ dùng chữ cái ASCII, chữ số và dấu gạch dưới nếu cần.
- Dùng camelCase thống nhất, ví dụ appCorrelationId.
- Không dùng khoảng trắng, dấu chấm hoặc dấu gạch ngang trong key cần ánh xạ sang JMS property.
- Giữ nguyên chữ hoa/thường ở mọi producer và consumer.
- Không đổi tên header chỉ để phù hợp với một lớp code cục bộ; nếu protocol cần tên khác, ánh xạ tại adapter.

Nếu header chỉ tồn tại trong STOMP, tên dạng app-correlation-id có thể dễ đọc, nhưng không nên mặc định nó tương thích với JMS property. Một tên camelCase như appCorrelationId thường thuận lợi hơn khi cùng một metadata phải đi qua nhiều protocol.

### 7.3. Tránh namespace đã được dành riêng

Không tự định nghĩa application header trùng với các nhóm sau:

- Header chuẩn của Spring như id, timestamp, contentType, replyChannel và errorChannel.
- Header nội bộ SIMP như simpSessionId, simpDestination, simpMessageType hoặc simpSubscriptionId.
- Header protocol STOMP như destination, content-type, receipt, subscription, ack và message-id.
- Thuộc tính JMS hoặc prefix dành riêng như JMSMessageID, JMSCorrelationID, JMSXDeliveryCount.
- Key nội bộ như nativeHeaders.

Không nên dùng prefix jms, stomp, simp hoặc spring cho metadata nghiệp vụ của ứng dụng. Những namespace này thuộc adapter/framework và có thể thay đổi cách xử lý theo protocol.

### 7.4. Quy định kiểu dữ liệu

Header có thể chứa Object trong Java, nhưng không phải transport nào cũng có thể serialize mọi kiểu object.

Ưu tiên các kiểu đơn giản, ổn định:

- String cho ID, tên service, tenant và version dạng ký hiệu.
- Integer/Long cho counter, priority nghiệp vụ hoặc epoch milliseconds nếu contract quy định.
- Boolean cho cờ đơn giản.
- MimeType cho contentType chuẩn của Spring.
- UUID chỉ khi mọi bên hiểu cách serialize và deserialize.

Tránh lưu một entity JPA, Spring bean, MessageChannel, HttpServletRequest hoặc object lớn vào application header. Những object đó không phải metadata truyền tải bền vững và có thể không serialize được.

Không dùng một key lúc thì String, lúc thì Integer. Producer và consumer phải thống nhất kiểu dữ liệu. Khi qua JMS hoặc STOMP, một số converter có thể biến giá trị thành String; hãy kiểm tra kiểu thực tế sau khi đi qua adapter.

## 8. Phân biệt các ID thường gặp

Các hệ thống messaging dễ nhầm lẫn giữa message ID, correlation ID, causation ID và business ID.

| Loại ID | Mục đích | Vòng đời |
|---|---|---|
| Spring message id | Nhận diện một Message instance trong Spring | Do Spring tạo; không phải khóa nghiệp vụ |
| JMS message ID | Nhận diện message theo JMS provider | Do provider quản lý |
| Correlation ID | Liên kết request/reply hoặc nhiều message trong cùng workflow | Được producer/ứng dụng giữ theo contract |
| Causation ID | Chỉ ra message nào đã tạo ra message hiện tại | Thường bằng ID của event/command trước đó |
| Business ID | Nhận diện thực thể nghiệp vụ như orderId | Theo vòng đời của thực thể |
| Trace ID | Liên kết các span/log trong một distributed trace | Theo trace context và hệ thống tracing |

Ví dụ:

~~~text
OrderCreated
  appEventId       = evt-100
  appCorrelationId = corr-900
  appCausationId   = null
  orderId          = order-42

PaymentRequested
  appEventId       = evt-101
  appCorrelationId = corr-900
  appCausationId   = evt-100
  orderId          = order-42
~~~

Correlation ID giúp tìm tất cả message thuộc một workflow. Causation ID thể hiện quan hệ nguyên nhân. Business ID xác định đối tượng nghiệp vụ. Các giá trị này không thay thế lẫn nhau.

Nếu cần idempotency, hãy chọn một event ID hoặc business key ổn định và lưu kết quả xử lý tương ứng. Không chỉ dựa vào Spring message id vì message có thể được chuyển đổi, tái tạo hoặc phát lại qua broker.

## 9. Quy tắc propagation khi message đi qua nhiều service

Một message có thể đi qua nhiều lớp:

~~~text
HTTP / WebSocket / JMS
          |
          v
    Inbound adapter
          |
          v
   Spring Message
          |
          v
    Business handler
          |
          v
   Outbound adapter
          |
          v
  Another protocol/service
~~~

Mỗi adapter có thể chuyển đổi payload và header. Không phải mọi header đều được giữ nguyên. Một số header bị đổi tên, một số trở thành native header, một số không thể biểu diễn ở transport đích.

Hãy lập mapping rõ ràng:

| Application header | JMS mapping | STOMP mapping |
|---|---|---|
| appCorrelationId | JMSCorrelationID hoặc JMS property theo contract | Native STOMP header |
| appEventId | JMS property theo contract | Native STOMP header |
| appSchemaVersion | JMS property theo contract | Native STOMP header |
| contentType | JMS `content_type` property qua `JmsHeaderMapper.CONTENT_TYPE_PROPERTY`; khác `JMSType` (`JmsHeaders.TYPE`) | STOMP `content-type` và Spring `contentType` |
| replyChannel | Không chuyển nguyên object channel | Không chuyển nguyên object channel |

Trong Spring JMS, `SimpleJmsHeaderMapper` ánh xạ `MessageHeaders.CONTENT_TYPE` sang JMS property `content_type`. Thuộc tính `JMSType` là loại message ở cấp JMS và được Spring biểu diễn bằng `JmsHeaders.TYPE`; nó không phải content type của payload.

Bảng này là một ví dụ thiết kế. Việc mapping chính xác phải được triển khai trong adapter hoặc MessageConverter và kiểm thử với provider thực tế.

Các nguyên tắc propagation:

1. Chỉ chuyển những header mà bên nhận thực sự cần.
2. Giữ nguyên ý nghĩa và kiểu dữ liệu theo contract.
3. Chuẩn hóa correlation ID ở biên hệ thống.
4. Không chuyển Spring internal channel/session object qua broker.
5. Không copy header xác thực hoặc thông tin nhạy cảm sang log hoặc service không cần chúng.
6. Xác định hành vi khi header thiếu, sai kiểu hoặc không hợp lệ.
7. Có versioning cho application header khi thay đổi contract.

Khi cần copy header, có thể dùng copyHeaders hoặc copyHeadersIfAbsent trên builder/accessor. Trong hệ thống có ranh giới trust khác nhau, hãy tạo map mới chứa allowlist thay vì copy toàn bộ headers từ inbound message.

## 10. Bảo mật và dữ liệu nhạy cảm trong header

Header thường dễ được log, hiển thị trong tracing hoặc lưu vào broker metadata. Vì vậy không nên đưa thông tin bí mật vào header chỉ vì thao tác đó thuận tiện.

Các giá trị cần hạn chế:

- access token, refresh token, session cookie và mật khẩu;
- API key hoặc credential kết nối broker;
- thông tin cá nhân không cần thiết;
- dữ liệu phân quyền có thể bị giả mạo từ client;
- nội dung payload lớn hoặc dữ liệu nhạy cảm.

Header appTenantId, appUserId hoặc role không tự trở thành thông tin đáng tin cậy chỉ vì nó nằm trong MessageHeaders. Nếu giá trị đến từ WebSocket client hoặc một nguồn không đáng tin, phải xác thực principal và tự xác định tenant/quyền ở phía server. Không dùng header do client gửi để cấp quyền truy cập topic hoặc queue.

Khi log message, nên ghi correlation ID, event ID và metadata vận hành cần thiết; che hoặc bỏ các header bí mật. Cũng cần kiểm tra log level vì một số accessor có thể tạo log message chứa metadata.

## 11. Ví dụ thiết kế một bộ application header

Giả sử service Order phát sự kiện OrderCreated. Có thể định nghĩa tập key tập trung:

~~~java
public final class OrderMessageHeaders {

    public static final String CORRELATION_ID = "appCorrelationId";
    public static final String EVENT_ID = "appEventId";
    public static final String SCHEMA_VERSION = "appSchemaVersion";
    public static final String SOURCE = "appSource";

    private OrderMessageHeaders() {
    }
}
~~~

Tạo message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(OrderMessageHeaders.CORRELATION_ID, correlationId)
        .setHeader(OrderMessageHeaders.EVENT_ID, eventId)
        .setHeader(OrderMessageHeaders.SCHEMA_VERSION, 1)
        .setHeader(OrderMessageHeaders.SOURCE, "order-service")
        .build();
~~~

Đọc message:

~~~java
String correlationId = message.getHeaders().get(
        OrderMessageHeaders.CORRELATION_ID,
        String.class
);

Integer schemaVersion = message.getHeaders().get(
        OrderMessageHeaders.SCHEMA_VERSION,
        Integer.class
);
~~~

Tập hằng số giúp producer và consumer dùng cùng key. Trong hệ thống nhiều module, nên đặt contract này ở một package/module chia sẻ có versioning rõ ràng. Nếu nhiều service không thể chia sẻ cùng thư viện, hãy quản lý tên và kiểu header trong tài liệu schema hoặc contract test.

Không tạo một lớp hằng số dùng chung cho mọi protocol nếu các key đó chỉ có ý nghĩa trong JMS hoặc STOMP. Giữ riêng application header và protocol header để ranh giới dễ hiểu.

## 12. Kiểm thử header contract

Một bộ kiểm thử header nên xác nhận cả tên, kiểu, giá trị mặc định và cách propagation.

Các trường hợp nên có:

1. Message được tạo có đủ application header bắt buộc.
2. Header chuẩn contentType có đúng MimeType.
3. ID và timestamp được Spring sinh theo cấu hình.
4. Consumer đọc header bằng kiểu mong muốn.
5. setHeaderIfAbsent không ghi đè giá trị đã có.
6. copyHeaders và copyHeadersIfAbsent có hành vi đúng với key trùng.
7. MessageHeaders không bị thay đổi trực tiếp sau khi build.
8. Header nội bộ như replyChannel hoặc simpSessionId không bị phát ra ngoài nếu không được cho phép.
9. JMS mapping giữ đúng correlation ID, event ID và kiểu giá trị mà contract quy định.
10. STOMP native header được encode/decode đúng qua WebSocket.
11. Header thiếu hoặc sai kiểu được xử lý theo chính sách rõ ràng.
12. Client không thể giả mạo tenant hoặc user identity bằng application header.

Unit test có thể kiểm tra MessageBuilder và MessageHeaderAccessor. Integration test cần dùng adapter/provider thật hoặc môi trường test tương ứng để xác nhận mapping native header, bởi kiểm tra Message trong bộ nhớ không chứng minh được transport giữ nguyên metadata.

## 13. Checklist trước khi phát hành một header mới

- Tên header có namespace thuộc sở hữu của ứng dụng chưa?
- Có đụng tên với Spring core, SIMP, JMS hoặc STOMP không?
- Tên có tương thích với mọi transport trong luồng không?
- Kiểu dữ liệu và đơn vị đo đã được xác định chưa?
- Header có thực sự là metadata hay nên nằm trong payload?
- Producer nào được phép đặt header?
- Consumer nào đọc và có xử lý khi header thiếu không?
- Header có được giữ, đổi tên hoặc loại bỏ ở mỗi adapter không?
- Có rò rỉ token, PII hoặc thông tin phân quyền không?
- Contract test đã xác nhận mapping và propagation chưa?

## 14. Tài liệu tham khảo

- [Spring Framework 6.1 — MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.1 — MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework 6.1 — NativeMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- [Spring Framework 6.1 — JmsMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/support/JmsMessageHeaderAccessor.html)
- [Spring Framework 6.1 — StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)

Header tốt là header có một ý nghĩa rõ ràng, một chủ sở hữu, một kiểu dữ liệu ổn định và một quy tắc propagation có thể kiểm thử. Khi giữ được bốn điều đó, các service có thể trao đổi message qua nhiều transport mà không phụ thuộc vào tên key ngẫu hứng hoặc metadata nội bộ của một adapter.