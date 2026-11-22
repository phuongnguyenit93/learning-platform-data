# JMSType, JMSX properties và application-defined properties trong Jakarta Messaging (JMS)

## 1. Vì sao một JMS message cần thông tin ngoài body?

Khi gửi một thông điệp như “đơn hàng 42 vừa được tạo”, body chứa dữ liệu nghiệp vụ; nhưng bên nhận còn cần biết **thông điệp thuộc loại sự kiện nào**, **phiên bản contract**, **tenant**, **mức ưu tiên xử lý**, hoặc **đây có phải lần giao lại không**. Jakarta Messaging cung cấp ba nhóm thông tin cần phân biệt:

1. **Header chuẩn** trên đối tượng jakarta.jms.Message: ví dụ JMSType, JMSMessageID, JMSCorrelationID, JMSDestination, JMSRedelivered. Mỗi header có getter/setter hoặc cơ chế do provider điền.
2. **Message properties**: các cặp tên/giá trị kiểu đơn giản. Trong đó có properties chuẩn tên bắt đầu bằng **JMSX**, properties riêng của provider và properties do ứng dụng định nghĩa.
3. **Body**: TextMessage, BytesMessage, MapMessage, ObjectMessage, StreamMessage hoặc Message không có body; đây là phần payload mà nghiệp vụ đọc.

Ví dụ một TextMessage:

~~~text
JMS message
├── Standard headers
│   ├── JMSType          = "order.created.v1"
│   ├── JMSMessageID     = "ID:..."           (provider gán)
│   ├── JMSCorrelationID = "trace-123"       (ứng dụng gán, nếu cần)
│   └── JMSRedelivered   = false              (provider gán khi giao)
├── Message properties
│   ├── JMSXDeliveryCount = 1                 (provider gán khi nhận)
│   ├── JMSXGroupID       = "order-42"        (ứng dụng gán nếu dùng nhóm)
│   ├── TenantId          = "acme"            (ứng dụng gán)
│   ├── SchemaVersion     = 2                 (ứng dụng gán)
│   └── RequiresAudit     = true              (ứng dụng gán)
└── Body (TextMessage)
    └── {"orderId":"42","total":250}
~~~

**Lưu ý:** giá trị trong sơ đồ là minh họa. JMSXDeliveryCount chỉ có ý nghĩa trên message **đã nhận**; đừng cho rằng producer tự biết delivery count của một message chưa được giao. Bảng điều khiển broker có thể hiển thị metadata theo cách riêng, nhưng contract lập trình ở đây là Jakarta Messaging API.

| Câu hỏi | Nơi nên tìm | API liên quan |
| --- | --- | --- |
| Message này thuộc loại nghiệp vụ nào? | Header JMSType | setJMSType / getJMSType |
| Message đã được provider giao mấy lần? | JMSX property | getIntProperty("JMSXDeliveryCount") |
| Nhiều message có thuộc cùng nhóm logic? | JMSX property | setStringProperty("JMSXGroupID", ...) |
| Tenant, schema version, nhãn định tuyến? | Application-defined property | setStringProperty / setIntProperty / get...Property |
| Cần tìm message liên quan trong luồng request-reply? | Header JMSCorrelationID | setJMSCorrelationID / getJMSCorrelationID |
| Dữ liệu đơn hàng thực tế? | Body | TextMessage.getText hoặc Message.getBody |

Ba nhóm metadata không thay thế cho nhau; tên property tự đặt cũng không tự trở thành một JMS header chuẩn.

## 2. JMSType: message-type identifier nằm trong header chuẩn

### 2.1. Ý nghĩa và cách đọc/ghi

**JMSType** là một **String header** chứa định danh loại thông điệp do phía gửi cung cấp. Đây là một phần của contract message, không phải tên Java class, không phải tên destination, và cũng không phải kiểu JMS object như TextMessage hay MapMessage.

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"42\"}");
message.setJMSType("order.created.v1");

// Sau khi nhận ở consumer:
String type = receivedMessage.getJMSType();
~~~

Đoạn trên minh họa trên các biến session và receivedMessage đã được tạo; chương trình chạy đầy đủ có ở mục 7.

Một số provider có message-definition repository và có thể dùng JMSType để tham chiếu định nghĩa thông điệp. Jakarta Messaging **không bắt buộc** mọi provider hỗ trợ repository hay áp đặt quy tắc đặt tên JMSType; ứng dụng cần tự quy ước tên và phiên bản.

**Khác biệt dễ nhầm:**

- **JMSType = "order.created.v1"**: tên sự kiện/loại message do hệ thống tự quy ước.
- **TextMessage**: class/interface thể hiện body là văn bản; nhiều JMSType khác nhau vẫn có thể cùng dùng TextMessage.
- **JMSDestination**: queue/topic mà broker gửi message đến.
- **JMSCorrelationID**: khóa liên hệ thông điệp, thường dùng cho request-reply; không phân loại business event.

JMSType có thể không được đặt (null). Bên nhận cần có chính sách rõ: chỉ nhận các message hợp lệ qua selector, hoặc kiểm tra type rồi xử lý trường hợp null/không hỗ trợ như một lỗi contract.

### 2.2. Dùng JMSType làm tiêu chí chọn thông điệp

JMS selector có thể tham chiếu trực tiếp header JMSType:

~~~sql
JMSType = 'order.created.v1'
~~~

Selector là cú pháp điều kiện gần với SQL-92, được provider áp dụng khi giao message cho consumer. Không viết:

~~~java
message.setStringProperty("JMSType", "order.created.v1"); // Không phải API đúng để gán header.
~~~

Hãy gọi **message.setJMSType(...)**. getPropertyNames() cũng không liệt kê các JMS standard header, nên JMSType được đọc bằng getJMSType().

### 2.3. Chọn contract tên và version

Một quy ước dễ hiểu:

~~~text
JMSType        = "order.created.v1"
SchemaVersion  = 2
TenantId       = "acme"
~~~

Ở đây JMSType v1 biểu diễn **họ sự kiện/định danh phiên bản của loại message**, còn SchemaVersion=2 biểu diễn phiên bản payload cụ thể theo thỏa thuận. Hai cách quản lý version có thể trùng nhau hoặc được dùng riêng; cần ghi thành contract thống nhất giữa producer và consumer. Không tự động tin rằng broker giải mã JSON hay xác thực schema chỉ vì JMSType có đuôi v1.

Trong môi trường có nhiều consumer, muốn hỗ trợ song song phiên bản cũ/mới, cần lập kế hoạch selector, tương thích schema, fallback và chiến lược nâng cấp. Một message có JMSType hợp lệ nhưng body không đúng schema vẫn là lỗi nghiệp vụ cần xử lý.

## 3. Message properties: cơ chế chung và ranh giới với body

Properties được dùng như những “header mở rộng” có tên/giá trị đơn giản. API hỗ trợ **boolean, byte, short, int, long, float, double, String**. Các setter có kiểu và getter tương ứng:

~~~java
message.setStringProperty("TenantId", "acme");
message.setIntProperty("SchemaVersion", 2);
message.setBooleanProperty("RequiresAudit", true);
message.setLongProperty("ReceivedAtEpochMillis", 1760000000000L);

// Ở bên nhận:
String tenant = message.getStringProperty("TenantId");
int version = message.getIntProperty("SchemaVersion");
boolean audit = message.getBooleanProperty("RequiresAudit");
long time = message.getLongProperty("ReceivedAtEpochMillis");
~~~

Đây là snippet minh họa. Không gửi DTO Java tùy ý như một property bằng setObjectProperty("Order", new Order(...)); **setObjectProperty** chỉ chấp nhận các wrapper primitive và String được tiêu chuẩn cho phép. Dữ liệu phức tạp cần nằm trong body hoặc một kho dữ liệu riêng có tham chiếu trong message.

### 3.1. Quy tắc tên property

Tên property phải thỏa cú pháp **identifier của JMS message selector**: phân biệt hoa/thường và không chứa dấu cách, dấu chấm, dấu gạch nối hay ký tự trái quy tắc identifier. Tránh từ khóa selector như AND, OR, TRUE, NULL, BETWEEN, LIKE, IN, IS, ESCAPE, NOT. Property name không được null hoặc chuỗi rỗng.

~~~text
Hợp lệ:   TenantId, SchemaVersion, OrderId, RequiresAudit
Không nên: tenant-id, order.id, "Tenant Id", AND, 123Name
~~~

Về namespace:

- **JMSX...**: tên dành riêng cho Jakarta Messaging-defined properties, ví dụ JMSXDeliveryCount. Ứng dụng không tạo một property mới tên JMSXRetryReason.
- **JMS_<vendor>...**: dành cho properties provider-specific, ví dụ những extension do broker công bố. Không dùng làm app property portable.
- **Tên ứng dụng**: đặt khác các namespace chuẩn/dành riêng, ví dụ TenantId, SchemaVersion, BusinessAction. Đừng tự tạo property có tiền tố JMS để tránh nhầm với API/dành riêng.

Kiểu dữ liệu của một property là một phần của hợp đồng: setIntProperty("SchemaVersion", 2) tạo giá trị numeric; setStringProperty("SchemaVersion", "2") tạo String. Selector **SchemaVersion >= 2** cần giá trị numeric, không thể dựa vào việc selector tự chuyển String "2" thành số.

### 3.2. Properties so với body

| Thuộc tính | Message properties | Body |
| --- | --- | --- |
| Mục đích chính | Metadata, lọc/routing, version, nhóm, chẩn đoán | Payload nghiệp vụ |
| Giá trị | Các primitive/wrapper được JMS hỗ trợ và String | Theo kiểu JMS message và format do hệ thống chọn |
| Có thể tham chiếu trong JMS selector? | Có, nếu dùng tên/kiểu hợp lệ | Không |
| Dữ liệu phức tạp | Không phù hợp | Phù hợp qua JSON/XML/binary/MapMessage… |
| Hợp đồng thay đổi | Nên tương thích và tránh đổi tên/kiểu đột ngột | Quản lý schema/version độc lập |

Thông điệp thường nên có metadata nhỏ, cố định và ổn định. Không đưa các thông tin nhạy cảm (token, mật khẩu, dữ liệu cá nhân) vào property chỉ vì muốn thuận tiện lọc; broker, log và công cụ giám sát có thể hiển thị metadata.

### 3.3. Thuộc tính của message đã nhận là read-only

Trước khi send, phía tạo message có thể set properties. Sau khi nhận, message properties ở **chế độ chỉ đọc**. Gọi setStringProperty(...) trên một message vừa receive thông thường gây MessageNotWriteableException.

~~~java
// receivedMessage là message đã nhận:
int version = receivedMessage.getIntProperty("SchemaVersion");
// receivedMessage.setIntProperty("SchemaVersion", 3);
// -> MessageNotWriteableException khi properties vẫn read-only.

receivedMessage.clearProperties(); // Xóa TOÀN BỘ properties, cho phép ghi lại.
receivedMessage.setIntProperty("SchemaVersion", 3);
~~~

**Không dùng clearProperties() chỉ để sửa một field mà quên các field còn lại.** Nó xóa tất cả property entries, bao gồm metadata cần bảo toàn; không làm mất body, và JMS không có API chuẩn để xóa riêng một property. Khi cần tạo message outbound mới, thường tốt hơn là tạo message mới và chọn lọc metadata cần truyền đi, không “chỉnh sửa tại chỗ” message đã nhận.

### 3.4. Đọc thuộc tính không có giá trị, duyệt và chuyển kiểu

- **propertyExists("Key")** giúp xác định key thực sự có trên message.
- **getObjectProperty("Key")** trả null nếu key không tồn tại; dùng để kiểm tra thiếu trường trước khi ép kiểu.
- **getPropertyNames()** trả Enumeration tên các message properties (không gồm các standard JMS headers); thứ tự không được bảo đảm.
- Getter kiểu primitive trên một key không tồn tại có quy tắc chuyển từ null riêng, có thể ném exception; không giả định tất cả trả về giá trị mặc định 0/false.
- JMS định nghĩa một số chuyển kiểu giữa các property types (ví dụ nhiều loại số có thể đọc thành String), nhưng không phải phép chuyển nào cũng hợp lệ; để selector và consumer dễ dự đoán, producer nên ghi **đúng kiểu contract ngay từ đầu**.

~~~java
if (message.propertyExists("SchemaVersion")) {
    int schema = message.getIntProperty("SchemaVersion");
    // Chỉ xử lý khi hợp đồng xác nhận field này có kiểu int.
}
~~~

## 4. JMSX: các properties do Jakarta Messaging định nghĩa

Tiền tố **JMSX** được dành riêng cho nhóm metadata chuẩn do đặc tả quy định, phân biệt với properties do ứng dụng tự đặt. Một số trường do producer gán, một số do provider gán lúc gửi hoặc lúc nhận. **Không phải tất cả JMSX properties đều bắt buộc xuất hiện trên mọi message.**

### 4.1. Danh sách chuẩn theo Jakarta Messaging 3.1

| Tên property | Kiểu | Gán bởi | Ý nghĩa |
| --- | --- | --- | --- |
| JMSXDeliveryCount | int | Provider lúc nhận | Số lần message đã được giao. **Bắt buộc** trên message nhận. |
| JMSXGroupID | String | Client | Tên nhóm message logic; trường tùy chọn, provider phải hỗ trợ property này. |
| JMSXGroupSeq | int | Client | Vị trí message trong nhóm, thường 1, 2, 3…; trường tùy chọn, provider phải hỗ trợ property này. |
| JMSXUserID | String | Provider lúc gửi | Định danh user gửi, nếu provider hỗ trợ/bật. |
| JMSXAppID | String | Provider lúc gửi | Định danh application gửi, nếu provider hỗ trợ/bật. |
| JMSXProducerTXID | String | Provider lúc gửi | Định danh transaction sản xuất, nếu hỗ trợ. |
| JMSXConsumerTXID | String | Provider lúc nhận | Định danh transaction tiêu thụ, nếu hỗ trợ. |
| JMSXRcvTimestamp | long | Provider lúc nhận | Thời điểm message được giao, nếu hỗ trợ. |
| JMSXState | int | Provider | State của bản sao message trong mô hình message warehouse; không phải field consumer thông thường có API tra cứu chuẩn. |

**Sắc thái quan trọng:** bảng chuẩn có cột “Optional” đối với JMSXGroupID/JMSXGroupSeq vì message có thể không mang chúng. Điều đó **không có nghĩa provider được từ chối hỗ trợ tên property**: đặc tả yêu cầu mọi provider hỗ trợ hai property chuẩn này. Cách nhóm được ánh xạ sang consumer, sticky affinity, chuyển quyền nhóm và xử lý group sequence trong vận hành cần đối chiếu tài liệu provider.

### 4.2. JMSXDeliveryCount và JMSRedelivered

Khi consumer nhận message, **JMSXDeliveryCount** phản ánh số lần provider đã giao message đó:

- Lần giao đầu tiên: **1**.
- Giá trị **2 trở lên**: message đã được giao lại một hay nhiều lần.
- JMSRedelivered là một **header boolean chuẩn** khác: khi true, nó cho biết provider đang đánh dấu message là redelivered. Nếu JMSRedelivered=true, JMSXDeliveryCount phải từ 2 trở lên.

~~~java
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
boolean redelivered = message.getJMSRedelivered();

if (deliveryCount >= 2) {
    // Theo dõi redelivery, tăng log/metric hoặc áp dụng xử lý idempotent.
}
~~~

**JMSXDeliveryCount là số lần giao, không phải số lần exception trong code**, không phải số lần business retry do ứng dụng tự thực hiện. Trong một số tình huống provider/server failure, đặc tả không buộc count phải bảo đảm tuyệt đối qua mọi sự cố. Vì vậy không dùng con số này làm nguồn duy nhất cho idempotency, hạn mức nghiệp vụ hoặc tiền tệ. Để chống duplicate end-to-end, dùng business id/orderId/idempotency key lưu bền.

JMSXDeliveryCount do **provider đặt khi nhận**. Không thiết kế producer tự gán JMSXDeliveryCount=0 hoặc selector phía broker kiểu:

~~~sql
JMSXDeliveryCount >= 3
~~~

để định tuyến message trước khi giao. Đặc tả nói **hành vi của selector dựa trên property được gán khi nhận là không xác định**. Consumer nên đọc property sau khi receive; retry/backoff và dead-letter address/queue (DLQ) cần cấu hình ở broker/container/ứng dụng theo provider.

### 4.3. JMSXGroupID và JMSXGroupSeq

Hai property liên quan đến **message grouping**: những message cùng group có thể cần được xử lý theo thứ tự và gắn với một consumer để bảo toàn ngữ cảnh.

~~~java
TextMessage first = session.createTextMessage("{\"step\":1}");
first.setStringProperty("JMSXGroupID", "order-42");
first.setIntProperty("JMSXGroupSeq", 1);

TextMessage second = session.createTextMessage("{\"step\":2}");
second.setStringProperty("JMSXGroupID", "order-42");
second.setIntProperty("JMSXGroupSeq", 2);
~~~

Đây là ví dụ mô tả metadata. JMSXGroupID **không phải** JMSCorrelationID: cùng correlation ID có thể dùng request-reply, còn group ID liên quan đến cách nhóm những message khi xử lý. JMSXGroupSeq là số thứ tự **do client đặt**; broker không tự soạn đúng dãy 1,2,3 thay producer.

Một số broker hỗ trợ group affinity/sticky consumer; điều kiện để nhóm được giữ thứ tự và cách release group cụ thể khác nhau theo provider và cấu hình. Không mặc định rằng đặt JMSXGroupID tự bảo đảm transaction nguyên tử, exactly-once, hay thứ tự toàn cục khi có nhiều queue/topic. Khi thiếu sequence hoặc có gap, nghiệp vụ vẫn cần kiểm soát.

### 4.4. Kiểm tra JMSX nào được provider hỗ trợ

ConnectionMetaData.getJMSXPropertyNames() trả danh sách tên JMSX mà provider công bố hỗ trợ:

~~~java
ConnectionMetaData metadata = connection.getMetaData();
java.util.Enumeration<?> names = metadata.getJMSXPropertyNames();
while (names.hasMoreElements()) {
    System.out.println(names.nextElement());
}
~~~

Đây là snippet cần biến connection. Danh sách thực tế tùy Artemis/IBM MQ/khác và phiên bản, không nên viết cứng stdout. Việc provider **hỗ trợ một property** cũng không đồng nghĩa nó được điền vào mọi message: hãy kiểm tra propertyExists và đặc tả “set by” trước khi đọc.

## 5. Application-defined properties: hợp đồng metadata do hệ thống tự thiết kế

Ứng dụng đặt những tên/giá trị không dành riêng cho chuẩn để phục vụ chức năng cụ thể, ví dụ:

| Property | Kiểu | Ví dụ | Ý nghĩa và lưu ý |
| --- | --- | --- | --- |
| TenantId | String | "acme" | Khoanh vùng dữ liệu; **không thay thế kiểm tra ủy quyền**. |
| SchemaVersion | int | 2 | Phiên bản payload/contract dùng khi đọc body. |
| BusinessEvent | String | "OrderCreated" | Tên nghiệp vụ bổ sung nếu không dùng JMSType cho việc đó. |
| Region | String | "vn-south" | Routing theo vùng nếu kiến trúc yêu cầu. |
| RequiresAudit | boolean | true | Quy tắc xử lý/audit, cần contract rõ. |
| RetryBudget | int | 3 | Giá trị do ứng dụng gán; không đồng nhất với JMSXDeliveryCount. |
| CorrelationKey | String | "job-42" | Khóa nghiệp vụ nếu không chọn header JMSCorrelationID. |

Không nhất thiết điền tất cả properties vào mọi message. Chỉ thêm khi consumer, selector hoặc monitoring cần dùng; mỗi property làm tăng ràng buộc giữa producer và consumer.

**Tên nhất quán, kiểu nhất quán, ý nghĩa nhất quán** quan trọng hơn việc đưa thật nhiều metadata. Ví dụ nếu đã chuẩn hóa TenantId, đừng lúc thì gửi TenantId, lúc lại tenantId hoặc TenantID: property identifiers **phân biệt chữ hoa/chữ thường**.

### 5.1. Property không phải cơ chế bảo mật

Dù selector có TenantId = 'acme', producer thiếu tin cậy vẫn có thể gửi một message tự ghi TenantId='acme'. Broker chỉ lọc dựa trên giá trị metadata, không tự bảo đảm người gửi có quyền với tenant. Áp dụng xác thực producer/consumer, quyền queue/topic, xác minh nội dung nghiệp vụ và trust boundary riêng.

### 5.2. Versioning và khả năng tương thích

Một mẫu tiến hóa payload:

1. Producer gửi JMSType='order.created.v1', SchemaVersion=1, body schema v1.
2. Consumer mới chấp nhận SchemaVersion IN (1, 2), parse theo từng version và bảo đảm fallback cho trường mới.
3. Khi chuyển dần sang v2, producer có thể gửi SchemaVersion=2 trong phạm vi hợp đồng đã duyệt, hoặc dùng JMSType='order.created.v2' nếu tên type cũng cần thay đổi.
4. Khi bỏ v1, kiểm tra queue/backlog và subscriber cũ; không thay đổi selector quá sớm khiến message v1 tồn đọng mà không ai nhận.

JMS không tự kiểm tra JSON schema hoặc tiến hóa schema; cách đặt JMSType/SchemaVersion là **quy ước của ứng dụng**. Contract nên được mô tả và kiểm thử độc lập ở producer/consumer.

## 6. Message selectors: kết hợp JMSType và application properties

Message selector là một chuỗi điều kiện dựa trên **một tập header được chuẩn cho phép** và **message properties**. Nó được áp dụng ở phía JMS provider để lựa chọn message được giao cho MessageConsumer.

Ví dụ:

~~~sql
JMSType = 'order.created.v1'
AND TenantId = 'acme'
AND SchemaVersion >= 2
~~~

Trong Jakarta Messaging, những **standard headers** có thể được tham chiếu trong selector gồm: JMSDeliveryMode, JMSPriority, JMSMessageID, JMSTimestamp, JMSCorrelationID, JMSType. Không mặc định mọi header khác (chẳng hạn JMSRedelivered) là selector field hợp lệ. Cũng không thể viết selector đọc trực tiếp trường orderId bên trong JSON body.

### 6.1. Các phép kiểm tra hữu ích

~~~sql
-- Chỉ nhận đơn hàng thuộc tenant đã định:
TenantId = 'acme'

-- Chỉ nhận loại sự kiện cụ thể:
JMSType = 'order.created.v1'

-- Cả type, tenant và phiên bản:
JMSType = 'order.created.v1' AND TenantId = 'acme'
  AND SchemaVersion >= 2

-- Các phiên bản được hỗ trợ:
SchemaVersion IN (1, 2)

-- Boolean property:
RequiresAudit = TRUE

-- Bỏ qua message không có Region:
Region IS NOT NULL

-- Có thể kết hợp nhiều loại sự kiện:
(JMSType = 'order.created.v1' OR JMSType = 'order.updated.v1')
  AND TenantId = 'acme'
~~~

Các phép AND/OR, so sánh, IN, BETWEEN, LIKE, IS NULL tuân theo một tập cú pháp kiểu SQL-92; string literal phải nằm trong **nháy đơn**, muốn có dấu nháy đơn bên trong thì nhân đôi. Kiểu identifier phân biệt hoa/thường; keywords selector không phân biệt hoa/thường.

**Ba trạng thái logic:** khi property không tồn tại, nó được coi là NULL trong biểu thức selector. Một phép so sánh với NULL thường ra UNKNOWN; chỉ kết quả TRUE mới match. Vì vậy lỗi tên TenantId so với tenantId, hoặc quên set property, có thể khiến message không được deliver cho consumer có selector mà không báo lỗi Java trong producer.

**Kiểu dữ liệu quan trọng:**

~~~java
message.setStringProperty("SchemaVersion", "2");
~~~

Selector SchemaVersion >= 2 **không match như một phép so sánh số** vì property thực tế là String. Nên dùng setIntProperty("SchemaVersion", 2), hoặc nếu contract là String thì selector phải so sánh như String. Đừng dựa vào phép ép kiểu ngầm của broker khi triển khai sang nhiều provider.

### 6.2. Selector giúp lọc, nhưng không phải định tuyến lại

Với **queue**, consumer có selector chỉ lấy những message match; message không match vẫn tồn tại cho consumer phù hợp hoặc chờ đến khi timeout/expiration/quy tắc khác áp dụng. Nếu không có consumer nào match, backlog có thể tăng. Với **topic**, cách subscription/selector ảnh hưởng từng subscriber; thông điệp không match không tự trở thành một “rejected-message queue”.

Selector không có quyền tự thay đổi metadata của message, không có nghĩa payload đã được validate và không thay thế Dead Letter Queue. Khi thiết kế nhiều consumer theo JMSType hoặc TenantId, hãy kiểm tra phần message **không khớp bất cứ selector nào** trước khi đưa lên production.

### 6.3. Vì sao không dùng JMSXDeliveryCount để selector?

JMSXDeliveryCount được gán **khi nhận**, còn selector quyết định message nào sẽ được giao. Vì vậy kết quả selector tham chiếu một JMSX property set by provider on receive **không được đặc tả xác định**. Tốt hơn dùng cấu hình retry/DLQ của broker, rồi sau receive kiểm tra JMSXDeliveryCount để ghi log hoặc quyết định handling.

## 7. Ví dụ hoàn chỉnh: Java 17 + Jakarta Messaging 3.1 + Apache Artemis

Ví dụ tạo temporary queue, gửi bốn TextMessage cùng một body format nhưng khác **JMSType / TenantId / SchemaVersion**. Consumer dùng selector chỉ nhận hai message phù hợp. Hai message đầu còn minh họa JMSXGroupID/JMSXGroupSeq; phía nhận đọc JMSXDeliveryCount.

### 7.1. Yêu cầu chạy

Cần JDK 17+, Maven, Docker và cổng 61616 còn trống. Chạy broker Artemis thử nghiệm:

~~~bash
docker run --detach --rm --name jms-property-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ broker khởi động trước khi chạy Java. Image chính thức mặc định dùng user/password artemis/artemis; không sử dụng credentials demo trong môi trường thật.

Cấu trúc file:

~~~text
jms-property-demo/
├── pom.xml
└── src/main/java/example/jms/MessageMetadataDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-property-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
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

Đây là một ứng dụng **JMS thuần để giải thích API**, không phải Spring Boot. Sau mục này, mục 8 cho thấy chính các thao tác metadata đó trong JmsTemplate và @JmsListener của Spring.

### 7.3. MessageMetadataDemo.java

~~~java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class MessageMetadataDemo {

    private MessageMetadataDemo() {}

    public static void main(String[] args) throws JMSException {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        try (Connection connection =
                     factory.createConnection("artemis", "artemis")) {

            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            TemporaryQueue queue = session.createTemporaryQueue();
            MessageProducer producer = session.createProducer(queue);

            String selector =
                    "JMSType = 'order.created.v1' " +
                    "AND TenantId = 'acme' AND SchemaVersion >= 2";
            MessageConsumer consumer =
                    session.createConsumer(queue, selector);

            // Hai message khớp: cùng một JMSXGroupID, sequence 1 và 2.
            send(session, producer, "order.created.v1",
                    "acme", 2, "order-42", 1);
            send(session, producer, "order.created.v1",
                    "acme", 3, "order-43", 2);

            // Không khớp TenantId.
            send(session, producer, "order.created.v1",
                    "other", 2, "order-44", 0);

            // Không khớp JMSType.
            send(session, producer, "order.cancelled.v1",
                    "acme", 2, "order-45", 0);

            // Classic Connection mới tạo ở trạng thái stopped.
            connection.start();

            for (int i = 0; i < 2; i++) {
                Message message = consumer.receive(5_000);
                if (message == null) {
                    throw new IllegalStateException(
                            "Timed out waiting for matching message " + i);
                }
                System.out.printf(
                        "type=%s | tenant=%s | version=%d | body=%s | deliveries=%d%n",
                        message.getJMSType(),
                        message.getStringProperty("TenantId"),
                        message.getIntProperty("SchemaVersion"),
                        ((TextMessage) message).getText(),
                        message.getIntProperty("JMSXDeliveryCount"));
            }
        }
    }

    private static void send(
            Session session,
            MessageProducer producer,
            String type,
            String tenant,
            int version,
            String body,
            int groupSeq) throws JMSException {

        TextMessage message = session.createTextMessage(body);
        message.setJMSType(type);                           // Header chuẩn
        message.setStringProperty("TenantId", tenant);      // App property
        message.setIntProperty("SchemaVersion", version);   // App property
        if (groupSeq > 0) {
            message.setStringProperty("JMSXGroupID", "order-batch-7");
            message.setIntProperty("JMSXGroupSeq", groupSeq);
        }
        producer.send(message);
    }
}
~~~

Điểm cần quan sát:

1. **setJMSType** gán header chuẩn. Không có property tự đặt tên JMSType nào được tạo.
2. **setStringProperty / setIntProperty** gán metadata ứng dụng dùng trong selector, **không nằm trong body**.
3. **JMSXGroupID và JMSXGroupSeq** được đặt trên hai message đầu; đó là hai property JMSX client được phép gán.
4. **JMSXDeliveryCount** được đọc từ message đã nhận, do provider gán.
5. Selector được tạo **trước khi start()**; consumer nhận đúng hai message đầu theo điều kiện.
6. Hai message không match có thể còn ở temporary queue khi consumer đang chạy; khi Connection đóng, temporary queue cũng hết vòng đời. Đây chỉ là demo selection, không phải quy trình xử lý toàn bộ backlog.
7. Ví dụ chỉ dùng một Connection/Session/consumer trên một thread, tránh khác biệt về dispatch khi có nhiều consumer cạnh tranh.

### 7.4. Lệnh chạy và stdout

Từ thư mục jms-property-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.jms.MessageMetadataDemo
~~~

Khi broker đã sẵn sàng, selector hoạt động và message được giao lần đầu, những dòng **do System.out.printf của ứng dụng** in ra là:

~~~text
type=order.created.v1 | tenant=acme | version=2 | body=order-42 | deliveries=1
type=order.created.v1 | tenant=acme | version=3 | body=order-43 | deliveries=1
~~~

Có thể thấy thêm log từ thư viện/broker tùy cấu hình. Nếu xảy ra redelivery hoặc provider không kịp giao trong 5 giây, delivery count hoặc kết quả chạy có thể khác; phần trên là output của **đường chạy thành công thông thường**, không phải cam kết mọi lần chạy luôn đúng thời điểm. Dừng container bằng lệnh docker stop jms-property-broker khi thực hành xong.

### 7.5. Thử thay đổi selector và property

- Đổi selector sang TenantId = 'other': chỉ chọn order-44; hãy đổi vòng lặp receive từ hai lần sang một lần để không timeout.
- Đổi selector sang JMSType = 'order.cancelled.v1': chỉ chọn order-45.
- Đổi send(..., "acme", 2, ...) thành send(..., "acme", 1, ...): message đó không còn match điều kiện SchemaVersion >= 2.
- Đổi setIntProperty("SchemaVersion", version) thành setStringProperty("SchemaVersion", String.valueOf(version)): điều kiện numeric >= 2 không còn match như mong đợi.
- Đọc getStringProperty("JMSXGroupID") trên message đã nhận để xác minh grouping metadata của hai message đầu.

Mỗi lần chạy dùng temporary queue mới. Đừng so sánh queue depth giữa những lần chạy như thể queue cũ còn tồn tại.

## 8. Dùng metadata trong Spring Framework JMS

Trong Spring, **JmsTemplate** tự tạo/gửi JMS message thông qua ConnectionFactory và MessageConverter. Khi cần điền JMSType/properties sau khi chuyển đổi body, dùng **MessagePostProcessor**:

~~~java
import org.springframework.jms.core.JmsTemplate;

// Đây là method trong một Spring bean đã inject JmsTemplate.
void publish(JmsTemplate jmsTemplate) {
    jmsTemplate.convertAndSend(
            "orders.events",
            "{\"orderId\":\"42\"}",
            message -> {
                message.setJMSType("order.created.v1");
                message.setStringProperty("TenantId", "acme");
                message.setIntProperty("SchemaVersion", 2);
                message.setStringProperty("JMSXGroupID", "order-42");
                message.setIntProperty("JMSXGroupSeq", 1);
                return message;
            });
}
~~~

Đây là **snippet Spring**, không phải một class main Java độc lập: phải có Spring JMS starter/config, ConnectionFactory, JmsTemplate và destination phù hợp. Đoạn trên giả định MessageConverter của JmsTemplate biến String thành TextMessage; với default SimpleMessageConverter, điều này thường đúng. Nếu converter tùy chỉnh tạo định dạng khác, metadata vẫn được gán qua MessagePostProcessor.

Ở phía nhận, **@JmsListener** cho phép chỉ định selector:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        id = "orderCreatedListener",
        destination = "orders.events",
        selector = "JMSType = 'order.created.v1' " +
                   "AND TenantId = 'acme' AND SchemaVersion >= 2")
    public void onMessage(Message message) throws JMSException {
        String type = message.getJMSType();
        int deliveryCount =
                message.getIntProperty("JMSXDeliveryCount");
        String tenant = message.getStringProperty("TenantId");

        // Nội dung business nhận được nằm trong body.
        String payload = message.getBody(String.class);

        System.out.printf(
                "type=%s tenant=%s delivery=%d payload=%s%n",
                type, tenant, deliveryCount, payload);
    }
}
~~~

Ứng dụng Spring Boot cần dependency Spring JMS/provider và cấu hình broker. Đăng ký @JmsListener cần JMS infrastructure (Spring Boot có thể auto-config khi dependency phù hợp). **Listener container** quản lý connection/session/start/ack/transaction, còn selector hoạt động ở phía JMS provider trước khi Spring gọi onMessage. Không nhầm **Jakarta Message** với Spring Messaging MessageHeaders: ở ví dụ này tham số là jakarta.jms.Message, do đó đọc header/property bằng Jakarta JMS API.

Nếu cần route theo nhiều event types, có thể tạo nhiều listener với selectors khác nhau hoặc một listener chung tự dispatch dựa trên getJMSType(); lựa chọn phụ thuộc backlog, khả năng mở rộng và hợp đồng vận hành. Một queue có nhiều consumer với selector phải được thiết kế để mọi nhóm message hợp lệ có người nhận, nếu không sẽ bị tồn đọng.

### 8.1. Giữ metadata khi chuyển từ hệ thống này sang hệ thống khác

Giả sử listener nhận JMS message A và cần phát message B sang queue khác. B là **message mới** với MessageID/DeliveryCount riêng; đừng copy toàn bộ properties của A một cách mù quáng. Quyết định rõ metadata nào phải truyền tiếp: CorrelationID hoặc business trace, TenantId, SchemaVersion theo contract mới; **không tự copy JMSXDeliveryCount** của message cũ sang message mới.

~~~java
jmsTemplate.convertAndSend("audit.events", payload, outgoing -> {
    outgoing.setJMSType("audit.recorded.v1");
    outgoing.setStringProperty("TenantId", tenant);
    outgoing.setStringProperty("OriginEventType", originalType);
    return outgoing;
});
~~~

Đây là snippet: jmsTemplate, payload, tenant, originalType có từ context xử lý bên ngoài. Message mới do converter tạo ra sẽ có vòng đời gửi/nhận riêng.

## 9. Thiết kế contract đáng tin cậy khi triển khai thực tế

### 9.1. Phân công ownership của metadata

| Loại metadata | Ai chịu trách nhiệm? | Kiểm tra ở consumer |
| --- | --- | --- |
| JMSType | Producer/contract owner | Type hợp lệ, có consumer xử lý |
| SchemaVersion | Producer theo schema registry/contract | Version được hỗ trợ, parse đúng body |
| TenantId | Producer và tầng xác thực | Quyền thực tế, không chỉ tin metadata |
| JMSXGroupID / JMSXGroupSeq | Producer nếu cần nhóm | Group key ổn định, ứng xử provider rõ ràng |
| JMSXDeliveryCount | Provider lúc nhận | Quan sát retry, không thay business idempotency |
| JMSMessageID | Provider | Trace transport, không thay business ID |
| JMSCorrelationID | Producer/ứng dụng | Liên kết request-reply hoặc trace nếu đã quy ước |

### 9.2. Các quyết định nên ghi thành tài liệu

- **Danh mục JMSType**: ai sở hữu, tên có phân biệt version không, consumer nào lắng nghe mỗi type.
- **Property schema**: danh sách tên chính xác, kiểu chính xác, có bắt buộc không, default nào được phép, có được để null/vắng mặt không.
- **Selector của consumer**: điều kiện bao phủ, message không match đi đâu, trạng thái khi nâng cấp.
- **JMSX phụ thuộc provider**: kiểm tra bằng getJMSXPropertyNames(); kiểm thử grouping, redelivery, restart broker và concurrency theo triển khai.
- **Khóa nghiệp vụ**: gắn business id vào body/property, kiểm soát duplicate bằng DB/idempotency key.
- **Quyền và dữ liệu**: RBAC/ACL cho destination, log không lộ token/dữ liệu nhạy cảm, giới hạn kích thước properties.

### 9.3. Các lỗi phổ biến

| Hiện tượng | Lỗi nguyên nhân | Cách sửa |
| --- | --- | --- |
| getJMSType() trả null | Producer chỉ setStringProperty("JMSType", ...) hoặc không set header | Gọi setJMSType trên chính message trước send |
| Selector không nhận message | Sai chữ hoa/thường: tenantId khác TenantId | Chuẩn hóa tên property và test selector |
| Selector số không match | setStringProperty("SchemaVersion", "2") | Dùng setIntProperty(..., 2) |
| Message cứ tồn trong queue | Không có consumer nào có selector match | Kiểm tra toàn bộ consumer và backlog |
| Đọc JMSXDeliveryCount ở producer | Property do provider gán khi nhận | Chỉ đọc ở consumer sau receive |
| Dùng JMSXDeliveryCount để filter trước delivery | Hành vi selector undefined theo đặc tả | Retry/DLQ ở provider/container; đọc count sau nhận |
| Tin JMSXGroupID đảm bảo exactly-once | Message group không phải distributed transaction | Idempotency và transaction của business store |
| Trộn javax.jms và jakarta.jms | Dependency/API hai thế hệ khác nhau | Chọn namespace nhất quán (Spring 6/Boot 3 dùng jakarta.jms) |
| Sửa property trên message đã nhận bị exception | Properties read-only | Tạo message mới, hoặc hiểu rõ clearProperties trước khi dùng |
| Dùng dấu chấm/gạch nối trong property name | Tên vi phạm cú pháp selector identifier | Dùng tên như EventVersion, TenantId |
| Đưa JSON vào property | JMS property không hỗ trợ DTO arbitrary | Đưa JSON vào TextMessage body |
| Copy JMSXDeliveryCount sang outbound message | Nhầm metadata do provider cấp với business metadata | Không copy; outbound có delivery lifecycle riêng |

## 10. Tự kiểm tra bằng các tình huống

**Tình huống A — Hai message có cùng body nhưng khác JMSType.** Một message là order.created.v1, một message là order.cancelled.v1. Consumer có selector JMSType = 'order.created.v1' chỉ nhận message đầu dù body giống nhau. Bài học: JMSType là header có thể được provider xét độc lập body.

**Tình huống B — Producer gửi setStringProperty("SchemaVersion", "3").** Consumer dùng selector SchemaVersion >= 2. Vì property có kiểu String nên so sánh số không thể dựa vào kiểu literal 2; thiết kế đúng là dùng int property (hoặc dùng selector kiểu chuỗi theo contract).

**Tình huống C — Giao lại sau rollback.** Consumer có thể nhìn thấy JMSXDeliveryCount=2 và JMSRedelivered=true; các thuộc tính này giúp chẩn đoán delivery, nhưng idempotency vẫn phải dựa trên business key vì side effect có thể đã hoàn tất trước khi ack/commit.

**Tình huống D — Consumer nhận message không có TenantId.** Selector TenantId = 'acme' cho kết quả UNKNOWN, do đó message không match. Điều đó không tự đưa message vào DLQ. Phải kiểm tra contract producer và chính sách xử lý message không match.

**Tình huống E — Có hai consumer cạnh tranh trên cùng queue, chung JMSXGroupID.** Dùng grouping nếu provider hỗ trợ semantics cần thiết để giảm nguy cơ mỗi message cùng nhóm vào một worker khác nhau. Tuy nhiên phải kiểm thử affinity, failover và thứ tự thực tế; JMSXGroupID không tự biến mọi xử lý thành tuần tự/chính xác một lần.

**Tình huống F — Listener nhận message rồi gọi clearProperties().** Mọi property entries bị xóa và properties chuyển sang writable; body vẫn còn, nhưng TenantId, SchemaVersion và JMSX fields đang có không còn được bảo toàn như ban đầu. Không dùng thao tác này một cách vô ý.

### Bài tập

1. Chạy ví dụ mục 7, lần lượt chỉnh JMSType, TenantId, SchemaVersion để thấy selector chọn message nào.
2. Thêm boolean property RequiresAudit và thử selector RequiresAudit = TRUE.
3. Duyệt getPropertyNames() trước/sau khi nhận; kiểm tra JMSType vắng khỏi Enumeration vì đó là header.
4. Dùng connection.getMetaData().getJMSXPropertyNames() liệt kê tên JMSX được Artemis công bố. Tìm tên nào được hỗ trợ nhưng không nhất thiết có mặt trên từng message.
5. Viết thử handler tính toán business action một cách idempotent bằng OrderId; giả lập redelivery và chứng minh không có tác dụng phụ lặp.
6. Trong Spring JMS, đổi selector ở @JmsListener để nhận một loại JMSType khác; kiểm tra queue depth khi không có listener match.

## 11. Tài liệu chuẩn để đối chiếu

- Jakarta Messaging 3.1 specification, §§3.4.8, 3.5, 3.8: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API, jakarta.jms.Message: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta EE Tutorial — JMS concepts và message properties: https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- Spring Framework — Sending a Message/MessagePostProcessor: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
