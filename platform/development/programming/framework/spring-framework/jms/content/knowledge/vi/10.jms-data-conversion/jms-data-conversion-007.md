# Phiên bản schema và khả năng tương thích hai chiều trong Spring JMS

## 1. Bối cảnh và mục tiêu

Trong hệ thống Spring JMS, producer và consumer thường **không được triển khai đồng thời**. Ví dụ, service đặt hàng phát sự kiện `OrderCreated` theo schema v1; tuần sau producer được nâng cấp để gửi schema v2 có thêm ghi chú giao hàng. Trong lúc rollout, một consumer vẫn ở phiên bản cũ, một consumer khác đã được nâng cấp, và Queue có thể còn message cũ chưa xử lý.

Nếu không có chiến lược **schema evolution**, những thay đổi tưởng như nhỏ — thêm trường, đổi tên trường, thay `int` bằng `String`, đổi đơn vị tiền tệ — có thể làm listener deserialization thất bại, đưa message vào DLQ, hoặc tệ hơn là **xử lý thành công về cú pháp nhưng sai ý nghĩa**.

Bài học tập trung vào việc **phiên bản hóa cấu trúc dữ liệu được truyền bằng JMS và bảo đảm khả năng tương thích hai chiều** giữa writer/producer và reader/consumer:

- Hiểu `schema`, `writer schema`, `reader schema`, **backward**, **forward**, **full/bidirectional** và **transitive** compatibility.
- Lập ma trận bốn trường hợp producer v1/v2 × consumer v1/v2.
- Thiết kế một thay đổi **không phá vỡ** có thêm trường tùy chọn và xử lý trường lạ/thiếu.
- Đưa tên/phiên bản schema vào **JMS properties** và sử dụng `MessageConverter` hoặc JSON parser đúng trách nhiệm.
- Xây dựng ví dụ **Java 17 + Spring Boot 3.5 + Artemis embedded + Jackson** để chứng minh cả hai hướng đọc.
- Nhận diện các thay đổi có vẻ hợp lệ về kiểu dữ liệu nhưng **phá vỡ hợp đồng nghiệp vụ**.
- Đưa ra chiến lược triển khai, kiểm thử contract và xử lý message không thể chuyển đổi.

**Điểm xuất phát:** Jakarta Messaging/JMS là **kênh vận chuyển message**, không tự định nghĩa schema JSON, Avro hoặc Protobuf cho domain object. Không có một header chuẩn `JMSSchemaVersion`. Ứng dụng phải quản lý contract và version, có thể dùng thư viện serializer/schema registry ngoài JMS.

## 2. Phân biệt schema, message version và phiên bản chương trình

**Schema** mô tả cấu trúc và quy tắc của dữ liệu truyền: tên trường, kiểu trường, yêu cầu bắt buộc, giá trị mặc định, các ràng buộc (ví dụ `amount >= 0`), ký hiệu sự kiện và ngữ nghĩa. Cần phân biệt ba thứ:

| Khái niệm | Ví dụ | Thể hiện điều gì? |
| --- | --- | --- |
| **Schema version** | `orders.created` v2 | Phiên bản hợp đồng định dạng message. |
| **Application version** | `order-service 5.8.0` | Phiên bản triển khai service; có thể hỗ trợ nhiều schema. |
| **JMSMessageID** | `ID:...` | Định danh do provider gán cho một lần gửi, **không phải** schema version. |

Một service triển khai phiên bản 5.8 có thể **vẫn ghi schema v1** trong giai đoạn rollout, đồng thời **đọc được schema v1 và v2**. Không đặt `schemaVersion = 5` chỉ vì artifact jar đang có major version 5.

**Writer schema** là cấu trúc dữ liệu producer thực sự phát ra. **Reader schema** là cấu trúc mà consumer mong đợi và có khả năng đọc. Cùng một message có thể được producer mới ghi, nhưng consumer cũ vẫn phải deserialize được nếu hệ thống tuyên bố hỗ trợ forward compatibility.

Ví dụ payload v1:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50
}
~~~

Payload v2 thêm trường **tùy chọn**:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50,
  "note": "gift"
}
~~~

Để hai phiên bản cùng sống được:

1. **Reader v1** phải chấp nhận trường `note` chưa biết (hoặc được schema resolver bỏ qua).
2. **Reader v2** phải chấp nhận message v1 thiếu `note` và gán giá trị phù hợp (ví dụ `null`, hoặc một mặc định đã thỏa thuận).
3. Cả hai phải giữ ý nghĩa của `orderId` và `amount`.
4. Không được tự cho rằng một công cụ cụ thể (Jackson/Avro/JSON Schema) áp dụng cùng quy tắc; khả năng tương thích **phụ thuộc định dạng, validator và cấu hình reader**.

## 3. Backward, forward và full compatibility: hướng đọc quyết định tên

Nói `schema v2 compatible với v1` mà không chỉ rõ hướng rất dễ nhầm. Hãy luôn hỏi **“Reader phiên bản nào đọc dữ liệu do writer phiên bản nào ghi?”**

| Loại tương thích | Điều được bảo đảm | Cách nhớ |
| --- | --- | --- |
| **Backward** | **Reader mới (v2)** đọc được dữ liệu của **writer cũ (v1)**. | Mã mới đọc được dữ liệu cũ. |
| **Forward** | **Reader cũ (v1)** đọc được dữ liệu của **writer mới (v2)**. | Mã cũ đọc được dữ liệu mới. |
| **Full / two-way** | Đúng **cả backward lẫn forward**. | Hai hướng đều đọc được trong phạm vi phiên bản được kiểm tra. |
| **Transitive** | Kiểm tra tương thích với **tất cả phiên bản trước liên quan**, không chỉ phiên bản liền kề. | Không bỏ quên các message nhiều đời trước. |

Ma trận tối thiểu v1 và v2:

| Writer gửi | Reader nhận | Tình huống | Điều kiện |
| --- | --- | --- | --- |
| **v1** | **v1** | Baseline | Bản thân v1 phải hoạt động. |
| **v1** | **v2** | **Backward** | Reader v2 đọc và xử lý dữ liệu v1. |
| **v2** | **v1** | **Forward** | Reader v1 đọc và xử lý dữ liệu v2. |
| **v2** | **v2** | Baseline | Bản thân v2 phải hoạt động. |

Khi nói một cặp v1–v2 **full compatible**, cần kiểm tra cả bốn ô, trong đó hai ô chéo là bằng chứng quan trọng.

### 3.1. Backward không có nghĩa old consumer tự đọc được new producer

Ví dụ reader v2 xử lý `note` mặc định khi message v1 không có trường này. Đó là **backward**, nhưng chưa chứng minh reader v1 chấp nhận payload v2 chứa `note`. Nếu reader v1 cấu hình strict (từ chối unknown fields), **forward sẽ thất bại**.

### 3.2. Forward không có nghĩa new consumer tự đọc được old producer

Giả sử producer v2 bỏ hẳn trường mà reader v1 không dùng, vì thế reader v1 vẫn đọc được. Tuy nhiên reader v2 có thể bắt buộc một trường mới mà writer v1 không cung cấp; lúc đó **backward thất bại**.

### 3.3. FULL không đồng nghĩa “mọi phiên bản đều hiểu mọi dữ liệu”

Các chế độ `BACKWARD`, `FORWARD`, `FULL` của nhiều schema registry chỉ kiểm tra schema mới so với **schema gần nhất trước nó**. Các chế độ `*_TRANSITIVE` mới kiểm tra với các phiên bản trước đó trong phạm vi registry. Không tuyên bố `FULL` đồng nghĩa `FULL_TRANSITIVE`, hoặc tự đảm bảo chuyển đổi ngữ nghĩa trong code nghiệp vụ.

## 4. Tại sao Queue, Topic và deployment độc lập làm vấn đề quan trọng?

JMS nhận và gửi message **không phụ thuộc phiên bản Java của service khác**:

~~~mermaid
flowchart LR
    P1["Producer v1"] --> Q[("orders.events")]
    P2["Producer v2"] --> Q
    Q --> C1["Consumer v1"]
    Q --> C2["Consumer v2"]
~~~

Sơ đồ này mô tả **các phiên bản có thể cùng tồn tại theo thời gian**; đối với cùng một Queue, mỗi lần giao message thường đến **một** competing consumer, không phải broadcast đến cả C1 và C2. Với Topic, từng subscription nhận bản sao theo JMS semantics riêng.

Tình huống thực tế:

- **Rolling deployment:** một số instance reader v1 vẫn chạy trong lúc reader v2 bắt đầu hoạt động.
- **Message backlog:** một message v1 được lưu từ hôm qua có thể được reader v2 đọc hôm nay.
- **Redelivery/DLQ replay:** message có thể được phát lại sau vài ngày, thậm chí sau khi producer v1 đã ngừng chạy.
- **Multi-service subscriptions:** nhiều nhóm phát triển cập nhật consumer với lịch khác nhau.
- **Blue/green deployment:** hai nhóm consumer khác phiên bản có thể cùng hoạt động trong cửa sổ chuyển đổi.

Với Queue, nếu **một consumer v1 không đọc được v2** mà vẫn chạy, nó có thể nhận message v2 và lỗi/rollback liên tục; không thể dựa vào chuyện “consumer mới cũng đã chạy” để chắc chắn v2 không rơi vào consumer cũ.

Với Topic, một subscriber cũ có thể tiếp tục nhận event mới. Nếu subscription durable giữ backlog, khả năng reader mới đọc dữ liệu **cũ** càng quan trọng.

**Kết luận kiến trúc:** compatibility là hợp đồng giữa **writer và reader**, không chỉ là property trên message; phải gắn với cách **đồng triển khai, giữ backlog và xử lý lỗi**.

## 5. Ví dụ tiến hóa an toàn: thêm trường tùy chọn

Định nghĩa v1:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50
}
~~~

Định nghĩa v2:

~~~json
{
  "orderId": "O-129",
  "amount": 125.50,
  "note": "gift"
}
~~~

Với **JSON reader permissive** được thiết kế chủ ý:

- Reader v1 đọc v2: bỏ qua `note` không biết, nhưng vẫn đọc đúng `orderId` và `amount`. Đây là **forward**.
- Reader v2 đọc v1: `note` không tồn tại được ánh xạ `null` hoặc default có ý nghĩa. Đây là **backward**.
- Cả hai: **full compatibility ở mức reader implementation** cho hai payload và giả định đã nêu.

**Điều kiện quan trọng:** nếu schema v1 dùng JSON Schema `additionalProperties: false` và validator thực hiện kiểm tra chặt, việc v2 có thêm `note` có thể **bị reader v1 từ chối**, bất kể một Jackson DTO có thể ignore field đó. Tương thích phụ thuộc cả **schema validation** và **mã deserializer/logic nghiệp vụ**. Không đánh tráo “Jackson parse được” với “hợp đồng schema qua mọi consumer đều hợp lệ”.

### 5.1. Trường nào được coi là “tùy chọn”?

Một trường mới thực sự tùy chọn khi:

1. Writer cũ không gửi trường đó mà reader mới vẫn xử lý đúng.
2. Reader mới có giá trị mặc định hoặc logic fallback được **quy định rõ**.
3. Mã nghiệp vụ không giả định trường luôn tồn tại.
4. Nếu gửi `null` và bỏ hẳn trường có ý nghĩa khác nhau, contract mô tả riêng.
5. Giá trị mặc định có ý nghĩa nghiệp vụ hợp lý; không phải tùy tiện thay `null` bằng 0.

Ví dụ thêm `discountPercent` với mặc định 0 có thể hợp lý **nếu đã thống nhất rằng thiếu trường nghĩa là không giảm giá**. Nhưng thêm `currency` với mặc định `VND` có thể sai nếu dữ liệu cũ từng chứa USD. Tương thích **ngữ nghĩa** quan trọng hơn JSON parser không ném exception.

## 6. Những thay đổi dễ gây breaking change

| Thay đổi từ v1 sang v2 | Nguy cơ | Gợi ý |
| --- | --- | --- |
| **Thêm trường tùy chọn** | Old reader từ chối unknown field; new reader xử lý missing sai. | Old reader ignore unknown khi phù hợp; new reader có default/nullable; test cả hai hướng. |
| **Thêm trường bắt buộc** | Old payload không có trường, new reader fail. | Dùng giai đoạn optional trước, backfill hoặc phát event mới. |
| **Xóa trường** | Reader cũ còn phụ thuộc trường bị xóa. | Deprecate rồi đo usage, giai đoạn dual-write, chỉ xóa khi hết consumer phụ thuộc. |
| **Đổi tên trường** | Reader cũ hoặc mới không biết tên kia. | Thêm alias/adapter hoặc dual fields có migration rõ ràng. |
| **Đổi kiểu `number` → `string`** | Converter có thể fail hoặc coercion nguy hiểm. | Giữ trường cũ, thêm trường mới có tên rõ nghĩa, version lớn nếu cần. |
| **Đổi `amount` từ đồng sang nghìn đồng** | Dữ liệu parse được nhưng kết quả nghiệp vụ sai. | Không đổi meaning âm thầm; thêm field/unit, event version mới. |
| **Thêm giá trị enum** | Old reader switch không có `default`, lỗi hoặc hành vi sai. | Unknown enum strategy, test và cân nhắc expand/deploy. |
| **Đổi `null` ↔ missing** | Các reader có semantics khác nhau. | Quy định nullability, omission và default. |
| **Đổi schema nhưng giữ cùng schemaVersion** | Không thể xác định đúng decoder; replay khó. | Version bất biến, không rewrite hợp đồng đã phát hành. |
| **Thay đổi format JSON → Avro/Protobuf** | Old consumer không thể parse payload mới. | Content type/schema ID và rollout/route/dual publication rõ. |
| **Đổi routing/Queue/Topic** | Consumer có thể không nhận dù schema hợp lệ. | Thay đổi routing độc lập, test delivery và ACL. |

Không có quy tắc phổ quát “thêm trường là luôn backward/forward/full” cho **mọi** JSON Schema, Avro, Protobuf và Jackson. Ví dụ Avro có cơ chế writer/reader schema resolution; JSON Schema có quy tắc `required`, `additionalProperties`; Protobuf dựa trên field numbers, reserved tags và wire types. Chính sách của registry/provider phải được kiểm tra trên **định dạng thật**.

## 7. Schema version nằm ở đâu trong JMS?

JMS chuẩn có header như `JMSType`, `JMSCorrelationID` và property custom. **Không có header JMS chuẩn mang tên `JMSSchemaVersion`**. Bạn có thể đặt:

- `JMSType = "order.created"` để gắn loại nghiệp vụ.
- `schemaName = "orders.created"` là `String` property.
- `schemaVersion = 2` là `int` property.
- `contentType = "application/json"` là `String` property nếu hệ thống tự quy ước.
- `eventId` là `String` property để hỗ trợ idempotency.

Ví dụ trong Spring JMS:

~~~java
// Fragment trong Spring bean có JmsTemplate jmsTemplate.
jmsTemplate.convertAndSend("orders.events", jsonBody, msg -> {
    msg.setJMSType("order.created");
    msg.setStringProperty("schemaName", "orders.created");
    msg.setIntProperty("schemaVersion", 2);
    msg.setStringProperty("contentType", "application/json");
    msg.setStringProperty("eventId", "event-O-129");
    return msg;
});
~~~

`jsonBody` phải được serialize đúng hợp đồng; metadata không làm body tự biến thành schema v2. Nếu `jsonBody` vẫn là v1 nhưng property ghi v2, consumer theo version sẽ **chọn sai decoder**. Phải xem serialization và metadata là **một thao tác logic**, kiểm thử đồng thời.

Với raw JMS consumer:

~~~java
// Fragment: jakarta.jms.Message received đã được nhận.
String schemaName = received.getStringProperty("schemaName");
int schemaVersion = received.getIntProperty("schemaVersion");
String contentType = received.getStringProperty("contentType");
~~~

**Cần validate:** property có thực sự tồn tại không? Sai type thì xử lý ra sao? Không tự giả định default `schemaVersion=1` cho mọi message thiếu trường trừ khi contract quy định như vậy. Với hệ thống legacy, có thể định nghĩa rõ `missing version => v1` và giới hạn thời gian hỗ trợ; khi hết giai đoạn migration, chuyển sang yêu cầu version bắt buộc.

### 7.1. JMS selector theo phiên bản

~~~java
// Fragment: có jakarta.jms.Session session và Queue queue.
jakarta.jms.MessageConsumer consumer = session.createConsumer(
        queue, "schemaName = 'orders.created' AND schemaVersion = 2");
~~~

Selector làm việc với **headers/properties**, không parse JSON body. Nếu version gửi dưới dạng `String "2"` thay vì `int 2`, điều kiện số trong selector có thể không khớp.

Dùng selector trong migration cần thận trọng: trên **Queue**, message không khớp vẫn có thể tồn đọng nếu không có consumer khác nhận; trên **Topic**, selector thuộc điều kiện subscription và semantics khác. Selector **không phải cơ chế bảo mật** hay phép kiểm chứng schema.

### 7.2. Schema Registry có phải một phần của JMS?

**Không.** Jakarta Messaging/JMS không mặc định cung cấp schema registry hoặc compatibility check. Có thể xây một **schema catalog/registry** độc lập để đăng ký các phiên bản, lưu schema ID, phát triển tooling CI, và gắn schema ID/version trong JMS properties hay envelope.

Confluent Schema Registry là ví dụ hệ sinh thái nổi tiếng trong Kafka; **không nên nói rằng tích hợp nó là mặc định của ActiveMQ Artemis hay JMS**. Nếu muốn dùng với JMS, cần tự chọn serializer, registry client, schema identifier và quy trình decode/validation phù hợp.

## 8. MessageConverter của Spring liên quan gì?

Spring JMS có abstraction `org.springframework.jms.support.converter.MessageConverter`:

- `toMessage(Object, Session)`: biến đối tượng Java thành `jakarta.jms.Message` để gửi.
- `fromMessage(Message)`: chuyển JMS Message nhận được thành đối tượng Java.

`JmsTemplate.convertAndSend(...)` sử dụng converter để tạo JMS message. `JmsTemplate.receiveAndConvert(...)` dùng converter để đọc payload. Với listener, container có thể sử dụng converter và mapping method arguments.

### 8.1. Converter mặc định không có phiên bản domain tự động

`SimpleMessageConverter` xử lý các kiểu phổ biến như:

| Java input | JMS message |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` với giá trị phù hợp | `MapMessage` |
| Một số `Serializable` object | `ObjectMessage` theo provider/setting |

**Không giả định bất kỳ POJO nào đưa vào `convertAndSend` đều được serialize thành JSON.** Với hệ thống liên service, JSON `TextMessage`, Avro/Protobuf `BytesMessage` có contract rõ ràng thường dễ quản lý tương thích hơn việc phụ thuộc vào Java `ObjectMessage` (class name, serialVersionUID, serialization và khả năng khai thác deserialization).

### 8.2. Hai chiến lược JSON

**Cách A — gửi JSON String và tự decode theo version:** code rõ ràng, dễ kiểm soát khi cần hỗ trợ v1/v2 đồng thời. Demo ở mục 10 dùng cách này, tránh phụ thuộc vào quy tắc type-header tự động.

**Cách B — dùng custom `MessageConverter`, ví dụ `MappingJackson2MessageConverter`:** chuyển domain object thành JSON message và từ message thành domain type, có thể sử dụng type-id property và mappings cấu hình rõ. Tuy nhiên việc chọn Java type từ JMS header **không đồng nghĩa** schema compatible: vẫn cần validator, migration, reader cho nhiều phiên bản và kiểm soát loại được phép deserialize.

Nếu contract được phân loại bởi `schemaName` và `schemaVersion`, lựa chọn reader nên **whitelist** các tổ hợp đã hỗ trợ thay vì dùng tên class Java tùy ý do producer gửi. Cần tránh biến một header JMS không đáng tin thành quyền yêu cầu ứng dụng tải bất kỳ class nào.

## 9. Contract JSON mẫu: v1 và v2

Một cách tài liệu hóa thay đổi là lưu hai bản JSON Schema có version bất biến. Sau đây là **bản minh họa**, không phải file được tạo tự động bởi JMS:

**`order-created-v1.schema.json`:**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderCreated v1",
  "type": "object",
  "required": ["orderId", "amount"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1},
    "amount": {"type": "number", "minimum": 0}
  },
  "additionalProperties": true
}
~~~

**`order-created-v2.schema.json`:**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderCreated v2",
  "type": "object",
  "required": ["orderId", "amount"],
  "properties": {
    "orderId": {"type": "string", "minLength": 1},
    "amount": {"type": "number", "minimum": 0},
    "note": {"type": ["string", "null"]}
  },
  "additionalProperties": true
}
~~~

Ý nghĩa:

1. `orderId` và `amount` tiếp tục **bắt buộc, giữ nguyên kiểu và ý nghĩa**.
2. `note` không nằm trong `required`, nên message v1 thiếu trường vẫn hợp lệ theo v2.
3. `additionalProperties: true` cố ý cho phép trường chưa được mô tả để minh họa khả năng old reader nhận payload có thêm `note`. Với API security-critical, có thể không chấp nhận chính sách mở này; cần thiết kế schema/validator và rollout phù hợp.
4. `type: ["string", "null"]` cho phép gửi `null`, nhưng **missing** và **null** vẫn là hai trạng thái JSON khác nhau; consumer quyết định fallback.
5. Schema kiểm tra dạng/kiểu, không tự xác nhận giá trị `amount` theo đúng đơn vị tiền tệ nghiệp vụ. Việc đổi đơn vị mà không đổi trường là một **breaking semantic change**.

**Thực hành quan trọng:** dùng schema validator chạy trên payload thực và CI test nhiều version. Ví dụ Java bên dưới dùng **Jackson DTO** để minh họa read compatibility, không tự thực thi JSON Schema validator từ hai file trên.

## 10. Demo chạy được: hai hướng đọc JSON qua Spring JMS

Bài thực hành dùng **Java 17+, Maven, Spring Boot 3.5.7, ActiveMQ Artemis embedded, Jackson**. Ta có **producer v1/v2** và **reader v1/v2**, thử trực tiếp hai hướng khó:

- **Writer v2 → Reader v1**: reader v1 bỏ qua `note` mới.
- **Writer v1 → Reader v2**: reader v2 xem `note` vắng mặt là `null`.

Đây là **full compatibility của hai DTO cụ thể trong demo**, không phải chứng minh mọi định dạng JSON Schema/consumer đều chấp nhận thay đổi này.

### 10.1. Cấu trúc dự án

~~~text
jms-schema-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jmsschema/
        │   └── JmsSchemaDemoApplication.java
        └── resources/
            └── application.properties
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-schema-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong ví dụ, `spring-boot-starter-json` cung cấp Jackson ObjectMapper để mã hóa/giải mã JSON; `spring-boot-starter-artemis` mang client Spring JMS; `artemis-jakarta-server` cho phép broker chạy nhúng. Parent quản lý dependency versions tương thích.

### 10.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.schema
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

`demo.schema` được tạo khi broker embedded khởi động. Persistence tắt có chủ ý **chỉ cho demo**; không lấy đó làm bằng chứng về khả năng replay sau restart. `receive-timeout=5s` giúp tránh treo vô hạn khi có lỗi.

### 10.4. JmsSchemaDemoApplication.java

~~~java
package com.example.jmsschema;

import java.math.BigDecimal;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsSchemaDemoApplication {

    public record OrderV1(String orderId, BigDecimal amount) {}

    public record OrderV2(
            String orderId,
            BigDecimal amount,
            String note) {}

    public static void main(String[] args) {
        SpringApplication.run(JmsSchemaDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            ObjectMapper mapper = new ObjectMapper()
                    .configure(
                            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
                            false);

            // 1) Writer v2 -> Reader v1 (FORWARD).
            String jsonV2 = mapper.writeValueAsString(
                    new OrderV2("O-NEW", new BigDecimal("125.50"), "gift"));

            template.convertAndSend("demo.schema", jsonV2, message -> {
                message.setStringProperty("schemaName", "orders.created");
                message.setIntProperty("schemaVersion", 2);
                return message;
            });

            TextMessage fromV2 = receiveText(template);
            int versionV2 = fromV2.getIntProperty("schemaVersion");
            OrderV1 oldReader = mapper.readValue(
                    fromV2.getText(), OrderV1.class);

            requireCore(oldReader.orderId(), oldReader.amount());
            System.out.println(
                    "V2->V1: " + oldReader.orderId() + " | "
                            + oldReader.amount());
            System.out.println("versionFromV2=" + versionV2);

            // 2) Writer v1 -> Reader v2 (BACKWARD).
            String jsonV1 = mapper.writeValueAsString(
                    new OrderV1("O-OLD", new BigDecimal("100.00")));

            template.convertAndSend("demo.schema", jsonV1, message -> {
                message.setStringProperty("schemaName", "orders.created");
                message.setIntProperty("schemaVersion", 1);
                return message;
            });

            TextMessage fromV1 = receiveText(template);
            int versionV1 = fromV1.getIntProperty("schemaVersion");
            OrderV2 newReader = mapper.readValue(
                    fromV1.getText(), OrderV2.class);

            requireCore(newReader.orderId(), newReader.amount());
            System.out.println(
                    "V1->V2: " + newReader.orderId() + " | "
                            + newReader.amount() + " | note="
                            + newReader.note());
            System.out.println("versionFromV1=" + versionV1);
        };
    }

    private static TextMessage receiveText(JmsTemplate template)
            throws JMSException {

        Message message = template.receive("demo.schema");
        if (!(message instanceof TextMessage text)) {
            throw new IllegalStateException(
                    "Không nhận được TextMessage trong 5 giây");
        }
        String name = text.getStringProperty("schemaName");
        if (!"orders.created".equals(name)) {
            throw new IllegalArgumentException(
                    "Schema không được hỗ trợ: " + name);
        }
        return text;
    }

    private static void requireCore(String orderId, BigDecimal amount) {
        if (orderId == null || orderId.isBlank()
                || amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "Missing or invalid core order fields");
        }
    }
}
~~~

**Từng bước trong demo:**

1. **DTO v1** có `orderId`, `amount`; **DTO v2** bổ sung `note` tùy chọn.
2. Một `ObjectMapper` được cấu hình **`FAIL_ON_UNKNOWN_PROPERTIES=false`**. Đây là quyết định có chủ ý: reader v1 bỏ qua trường `note` khi writer v2 gửi. Trong Jackson 2.x, không tự giả định cấu hình mặc định cho phép điều này.
3. `OrderV2` được serialize thành JSON String rồi đi qua `JmsTemplate.convertAndSend`; `SimpleMessageConverter` tạo `TextMessage`, không tự serialize record.
4. `MessagePostProcessor` gắn `schemaName` và **`schemaVersion` kiểu `int`**. JMS không tự xác minh rằng body thực sự đúng version đó.
5. `JmsTemplate.receive` trả về raw `Message` để kiểm tra metadata, rồi nhận `TextMessage`.
6. **Reader v1** bỏ qua `note` không biết, giữ được `orderId` và `amount` → ví dụ **forward**.
7. Gửi JSON v1, **Reader v2** deserialize được, `note` là `null` vì trường vắng mặt → ví dụ **backward**.
8. `requireCore` vẫn kiểm tra các field nghiệp vụ bắt buộc; việc deserializer parse được **không tự chứng minh** dữ liệu hợp lệ.

Chạy tại thư mục `jms-schema-demo`:

~~~bash
mvn spring-boot:run
~~~

Các dòng do **mã ứng dụng** in ra, bên cạnh log Maven/Spring/Artemis, dự kiến là:

~~~text
V2->V1: O-NEW | 125.50
versionFromV2=2
V1->V2: O-OLD | 100.00 | note=null
versionFromV1=1
~~~

Mã cố ý nhận từng message ngay sau khi gửi trong một broker mới, chỉ có một consumer. Nếu môi trường dùng chung queue hoặc có nhiều consumer, thứ tự nhận có thể khác và phải dùng test isolation. Kết quả trên là **stdout kỳ vọng** của bản demo, không phụ thuộc timestamp/message ID do JMS provider gán.

### 10.5. Vì sao không “cứ ignore unknown là tương thích”?

Đổi `FAIL_ON_UNKNOWN_PROPERTIES` sang `true` sẽ làm reader v1 từ chối trường `note` chưa biết trong JSON v2 (thường với `UnrecognizedPropertyException`). Điều này chứng minh **forward phụ thuộc cấu hình reader**.

Nhưng bật ignore-unknown không đủ nếu writer v2:

- Xóa `orderId`: DTO v1 nhận `orderId=null`; `requireCore` phải chặn.
- Đổi `amount` thành object hoặc dữ liệu không parse được: converter có thể ném lỗi.
- Đổi đơn vị `amount` nhưng vẫn giữ kiểu JSON number: deserialize thành công nhưng logic sai.
- Thêm trường bắt buộc mà consumer v2 không có default khi đọc v1.
- Đưa nội dung không đáng tin vào trường nhạy cảm: reader phải validate đầy đủ.

Trong hệ thống có schema validator strict hoặc security requirements cao, cần rule rõ và **không tắt validation toàn cục** chỉ để qua một lần rollout. Demo là bằng chứng ở tầng deserialization Java, không thay thế schema registry và semantic contract test.

## 11. Tương thích giữa JSON, Avro và Protobuf có gì khác?

| Công nghệ | Cách nhận schema | Chi tiết evolution cần nhớ |
| --- | --- | --- |
| **JSON + Jackson** | Java DTO/converter và optional JSON Schema validator. | Unknown fields, missing fields, null/default, coercion và mapper config quyết định. |
| **JSON Schema** | Schema độc lập mô tả kiểu/required/additionalProperties. | Open/closed content model, `required`, `enum`, `oneOf` ảnh hưởng compatibility; không tự được JMS kiểm tra. |
| **Apache Avro** | Writer schema + reader schema, theo schema resolution. | Reader thiếu field từ writer thì cần default thích hợp; writer có field thừa có thể bỏ qua khi reader không dùng; alias có thể hỗ trợ rename trong một số trường hợp. |
| **Protocol Buffers** | Schema message + field numbers/wire types. | Không tái sử dụng field number đã xóa; dùng `reserved`, cân nhắc unknown fields, enum evolution và presence semantics. |

### 11.1. Avro: default thuộc reader schema

Ví dụ một record Avro v2 thêm trường optional:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "example.events",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinor", "type": "long"},
    {"name": "note", "type": ["null", "string"], "default": null}
  ]
}
~~~

Khi đọc message được ghi bằng writer schema cũ không có `note`, Avro reader schema mới có thể sử dụng **default của trường mới**. Một default của Avro **không có nghĩa writer tự bỏ field đó khỏi binary encoding**; default được dùng khi **giải mã dữ liệu thiếu trường theo schema resolution**. Với union, phải chú ý thứ tự branch, default và phiên bản Avro.

**Không khẳng định** một alias hay type promotion bảo đảm mọi thay đổi đều hợp lệ; phải dùng compatibility checker của Avro/registry đúng phiên bản và test dữ liệu thật.

### 11.2. Protobuf: field number quan trọng hơn tên trường

Minh họa schema Protobuf:

~~~protobuf
syntax = "proto3";
package example.events;

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  optional string note = 3;
}
~~~

Trong Protobuf, các **tag numbers** (1, 2, 3) là phần quan trọng của wire format. Nếu xóa field, cân nhắc đánh dấu `reserved` số/tag đã dùng để tránh tái sử dụng gây diễn giải sai dữ liệu cũ. Thay đổi kiểu có thể làm dữ liệu cũ không đọc được hoặc thay ý nghĩa. Những trường default, unknown fields và presence semantics cũng khác JSON/Jackson; không áp cùng một bảng compatibility cứng cho tất cả.

### 11.3. Schema registry khác với message broker

Nếu dùng Avro/Protobuf và schema registry, một message có thể mang `schemaId` hoặc envelope để reader tải schema theo ID rồi decode. Đó là **quy ước serializer của ứng dụng/hệ sinh thái**, không phải một phần mặc định của JMS header. Chỉ khi các bên thống nhất format, schema registry và quản lý quyền truy cập thì cơ chế này mới hoạt động.

## 12. Chế độ TRANSITIVE và lịch sử nhiều phiên bản

Giả sử đã có v1 → v2 → v3. Nếu registry kiểm tra **FULL nhưng không transitive**, v3 có thể được so với v2 mà **không bắt buộc** trực tiếp tương thích với v1. Nếu Queue/DLQ còn message v1, consumer v3 có thể gặp dữ liệu không đọc được.

| Chế độ | Khi đăng ký v3, so với những phiên bản nào? |
| --- | --- |
| `BACKWARD` | v2: reader v3 phải đọc được writer v2. |
| `FORWARD` | v2: reader v2 phải đọc được writer v3. |
| `FULL` | v2: cả hai hướng v2 ↔ v3. |
| `BACKWARD_TRANSITIVE` | Các version đã đăng ký trong phạm vi (v1, v2): reader v3 đọc được tất cả writer cũ. |
| `FORWARD_TRANSITIVE` | Các version cũ (v1, v2): các reader cũ đọc được writer v3. |
| `FULL_TRANSITIVE` | Các version cũ (v1, v2): cả hai hướng cho mọi cặp mới–cũ. |

Đây là **cách gọi chế độ phổ biến của Schema Registry**, không phải enum của JMS. Tên và luật chính xác có thể khác giữa registries và loại schema. Confluent Schema Registry chẳng hạn phân biệt chế độ non-transitive với `*_TRANSITIVE`.

Trong JMS, quyết định retention/durable subscription/DLQ có thể tạo ra khoảng thời gian hỗ trợ schema dài hơn dự kiến. Nếu các message có thể được replay sau sáu tháng, phải có reader tương ứng hoặc cơ chế upcast/migration cho dữ liệu cũ đó.

Một số doanh nghiệp chọn không tương thích ngược vô hạn, nhưng phải có **chính sách có thời hạn rõ**: version đã ngừng hỗ trợ, thời điểm purge/migrate backlog, quyền replay, deprecation notice và kế hoạch rollback.

## 13. Chiến lược rollout không đồng bộ

### 13.1. Với BACKWARD: nâng reader trước

Nếu **new reader đọc old writer** được, trình tự tự nhiên:

1. Deploy consumer v2, nhưng producer vẫn gửi v1.
2. Xác minh consumer v2 đọc v1 và không phát sinh DLQ.
3. Sau khi các consumer cũ đã hết phiên bản hoặc không còn nhận queue/topic đó, bắt đầu cho producer phát v2.
4. Theo dõi lỗi decode, selector, lag và số message ở DLQ.

Nếu producer v2 được bật quá sớm, consumer v1 còn chạy **không được bảo đảm** đọc v2 (vì backward không bao hàm forward). Với Queue có competing consumers, một instance cũ vẫn có thể nhận v2 và thất bại.

### 13.2. Với FORWARD: writer mới có thể đi trước, nhưng có điều kiện

Nếu **old reader đọc new writer** được, producer v2 có thể phát message trong khi consumer v1 vẫn chạy. Tuy nhiên khi sau đó nâng consumer lên v2, **forward không tự bảo đảm reader v2 đọc được message v1 tồn đọng**. Trước khi đổi reader phải bảo đảm backlog v1 đã được xử lý, hoặc reader v2 có adapter/compatibility riêng để đọc v1.

### 13.3. Với FULL: cho phép nhiều thứ tự hơn, vẫn cần guardrails

Nếu cả reader v1/v2 đều đọc được writer v1/v2 trong môi trường thật, ta có thể triển khai độc lập hơn trong giai đoạn hai phiên bản cùng tồn tại. Nhưng **FULL chỉ ở mức cấu trúc** chưa chứng minh các side effects nghiệp vụ, selector, transaction, routing hay version quá cũ đều ổn.

Một rollout an toàn có thể dùng **expand → migrate → contract**:

~~~mermaid
flowchart LR
    A["Expand: reader hỗ trợ v1+v2"] --> B["Migrate: producer chuyển v2 theo feature flag"]
    B --> C["Observe: logs, DLQ, backlog, contract tests"]
    C --> D["Contract: ngừng hỗ trợ v1 khi được phép"]
~~~

Thứ tự này đặc biệt hữu ích khi schema có breaking change. Tránh deploy producer và consumer mới đồng thời rồi cho rằng sẽ không có cửa sổ rủi ro.

### 13.4. Breaking change: không nên sửa âm thầm

Nếu v2 thật sự không tương thích với v1 (ví dụ `amount` đổi đơn vị hoặc cấu trúc hoàn toàn khác), lựa chọn:

- Phát event type mới như `OrderCreatedV2` hoặc destination riêng có hợp đồng rõ, rồi chuyển subscription có kiểm soát.
- Dual-publish trong một giai đoạn **nếu có cơ chế chống xử lý trùng** và các side effects được kiểm soát.
- Reader adapter/upcaster chuyển v1 thành **canonical model** nội bộ.
- Chuyển đổi/replay backlog trước khi dỡ reader cũ.
- Phối hợp người sở hữu consumer khác, công bố deadline deprecation.

Không tái sử dụng cùng `schemaVersion=1` để chứa payload v2 không tương thích; điều đó làm việc xử lý retry, audit và replay không xác định.

## 14. Thiết kế reader đa phiên bản và lỗi không nhận dạng được

Trong code consumer thực tế, nên tách các bước:

1. Đọc raw `jakarta.jms.Message` và xác thực type được phép (ví dụ `TextMessage`).
2. Kiểm tra `schemaName`, `schemaVersion`, `contentType`; **không tin header mù quáng**.
3. Chọn **reader/decoder từ whitelist**; chỉ những version đã được hỗ trợ.
4. Deserialize, validate cấu trúc và nghĩa nghiệp vụ.
5. Chuẩn hóa thành **domain model** nội bộ.
6. Chỉ sau khi dữ liệu hợp lệ mới thực hiện side effect; bảo đảm ack/transaction, idempotency và retry policy.

Ví dụ fragment:

~~~java
// Fragment: textMessage đã được lấy từ listener hoặc JmsTemplate.receive.
// deserializeV1, deserializeV2 và toCanonical là logic ứng dụng.
String name = textMessage.getStringProperty("schemaName");
if (!"orders.created".equals(name)
        || !textMessage.propertyExists("schemaVersion")) {
    throw new IllegalArgumentException("Unsupported event schema");
}
int version = textMessage.getIntProperty("schemaVersion");

OrderCanonical order = switch (version) {
    case 1 -> toCanonical(deserializeV1(textMessage.getText()));
    case 2 -> toCanonical(deserializeV2(textMessage.getText()));
    default -> throw new IllegalArgumentException(
            "Unsupported schema version " + version);
};
validateOrder(order);
~~~

Đây là **pseudo-integrating fragment**: `OrderCanonical`, `deserializeV1`, `deserializeV2`, `toCanonical` và `validateOrder` do ứng dụng tự định nghĩa; **không phải file biên dịch độc lập**. Mục đích là làm rõ cách xử lý version.

Không nên làm:

~~~java
// Phản ví dụ: KHÔNG lấy tên class tùy ý từ JMS property do producer gửi
// để reflection/class loading mà không có whitelist.
String arbitraryClass = message.getStringProperty("javaClassName");
// Class.forName(arbitraryClass) ... // tránh thiết kế này.
~~~

Khi schema lạ xuất hiện, **không được âm thầm ép sang v1 và ack như đã xử lý thành công**. Tùy chính sách, chuyển message sang quarantine/DLQ, giữ raw message cùng version/error metadata, cảnh báo người quản lý contract và cho phép replay có kiểm soát sau khi bổ sung decoder.

## 15. Kiểm thử hợp đồng: không chỉ kiểm tra parse thành công

Một CI test tốt phải thử **cặp writer–reader** và cả validation ngữ nghĩa:

| Test | Producer/schema dùng tạo payload | Reader/consumer | Điều phải assert |
| --- | --- | --- | --- |
| V1→V1 | v1 | v1 | Baseline có body và business values chính xác. |
| V1→V2 | v1 | v2 | **Backward**; missing optional field/default an toàn. |
| V2→V1 | v2 | v1 | **Forward**; extra field không làm fail; old behavior đúng. |
| V2→V2 | v2 | v2 | Baseline mới. |
| V1→V3 | v1 | v3 | Bắt buộc nếu cam kết backward transitive/replay v1. |
| V3→V1 | v3 | v1 | Bắt buộc nếu cam kết forward transitive. |

### 15.1. Những assertion nên có

- JSON validator theo schema version phù hợp chấp nhận message hợp lệ.
- Mất field bắt buộc làm reader/business validator từ chối.
- Unknown fields được xử lý theo **policy**, không tùy tiện tắt mọi validation.
- Missing field mới được default đúng, kể cả giá trị `null` khi khác ý nghĩa với bỏ field.
- Numeric type/precision/range: `BigDecimal` hoặc integer minor units khi cần tiền tệ; tránh silent loss.
- Enum mới/cũ: có chiến lược `UNKNOWN` hoặc fail rõ.
- JMS property `schemaVersion` đúng kiểu, tên property hợp lệ cho selector.
- Correlation ID/event ID bất biến qua retry cùng sự kiện.
- Không lộ bí mật hoặc PII không cần thiết trong headers/properties.
- Không commit side effect nếu dữ liệu không hợp lệ.
- Replay từ DLQ/backlog bằng reader mới hoạt động theo thời gian retention.

**“Deserialize không ném exception” chỉ là một assertion**, chưa đủ để kết luận tương thích hợp đồng. Ví dụ DTO v1 bỏ qua `note`, nhưng nếu business v2 dùng `note` để quyết định quyền giao hàng, old consumer có thể vẫn parse và **bỏ qua một quy tắc mới**. Khi đó schema full ở mức cú pháp nhưng không an toàn ở mức nghiệp vụ.

### 15.2. Golden messages / fixtures bất biến

Nên lưu một số payload mẫu **v1/v2/v3** làm fixtures tại hệ thống test (không sửa lại payload lịch sử sau khi schema đổi). Các fixtures bao gồm:

- Message tối thiểu hợp lệ (chỉ các field required).
- Message có đủ optional fields.
- Trường `null` so với missing, giá trị rỗng, ký tự Unicode.
- Boundary values cho số, thời gian, tiền tệ và enum.
- Message thiếu/trùng field, sai kiểu, version lạ.
- Metadata JMS đi kèm: `schemaName`, `schemaVersion`, `JMSType`/contentType.

Mỗi lần đổi schema hoặc code converter, CI chạy lại toàn bộ **ma trận hỗ trợ**. Nếu dùng registry, kết hợp registry compatibility check với **consumer-driven contract tests** và integration test qua broker: registry có thể pass nhưng handler logic vẫn fail.

## 16. Khi nào cần upcaster, schema registry hay đổi event name?

| Tình huống | Giải pháp thường phù hợp | Lý do |
| --- | --- | --- |
| Thêm field tùy chọn, reader cũ bỏ qua được, reader mới có default | **Full-compatible v2** | Không phải di chuyển message đã có. |
| JSON schema nhiều version, nhiều consumer triển khai riêng | **Schema catalog/registry + contract CI** | Theo dõi versions và ngăn đăng ký thay đổi phá vỡ. |
| Cần đọc message v1 đã lưu lâu, domain model mới v3 | **Upcaster / versioned decoder** | Chuẩn hóa message cũ thành canonical model. |
| Thay đổi nghĩa nghiệp vụ căn bản | **Event type/destination mới** | Không bắt dữ liệu cũ giả làm dữ liệu mới. |
| Consumer không thể nâng cấp đồng loạt | **Expand/migrate/contract, feature flag, dual reader** | Giảm rủi ro rolling deploy. |
| Có dữ liệu chứa schema ID nhúng trong Avro/Protobuf bytes | **Serializer/registry integration** | Reader xác định đúng writer schema. |

**Upcaster** là hàm chuyển từ dạng dữ liệu cũ sang dạng mới/canonical, ví dụ:

~~~java
// Fragment minh họa adapter thuần Java:
public record CanonicalOrder(
        String orderId,
        java.math.BigDecimal amount,
        String note) {}

public static CanonicalOrder fromV1(OrderV1 old) {
    return new CanonicalOrder(old.orderId(), old.amount(), null);
}

public static CanonicalOrder fromV2(OrderV2 current) {
    return new CanonicalOrder(
            current.orderId(), current.amount(), current.note());
}
~~~

`OrderV1`/`OrderV2` là các record đã nêu trong demo; snippet trên cần được đặt trong class thích hợp, không phải file độc lập. Nếu nghiệp vụ chuyển field `amount` từ major sang minor unit, **upcast phải thực hiện chuyển đổi được định nghĩa rõ và kiểm tra overflow/rounding**, không chỉ map field theo tên.

## 17. Giao tiếp đa ngôn ngữ và giảm phụ thuộc vào Java class

Khi producer Spring Boot viết message cho consumer Node.js, Go hoặc .NET, **Java ObjectMessage** có thể không phải lựa chọn phù hợp: nó phụ thuộc vào Java serialization, class và `serialVersionUID`, cùng rủi ro deserialize object không đáng tin.

Một contract liên ngôn ngữ thường dùng:

- **JSON TextMessage** + JSON Schema + tên/version schema, hoặc
- **Avro/Protobuf BytesMessage** + schema ID/format và resolver được thống nhất.

Từng loại phải thống nhất:

1. Encoding (UTF-8, JSON, binary).
2. Kiểu số: tiền bằng minor units `long`/decimal string hoặc schema decimal rõ; tránh float làm tròn.
3. Timestamp: UTC epoch millis hoặc ISO 8601 có timezone; không đổi ngầm.
4. Null/missing/empty và default.
5. Enum, id formats, Unicode normalization nếu có liên quan.
6. Required vs optional fields, unknown field strategy.
7. Max message size và bảo mật payload.
8. Schema registry access/version retention, khi dùng registry.

Giữ **schema contract** độc lập với class Java mang tên gói `com.example...`. Khi rename class nội bộ, không nên buộc mọi consumer bên ngoài đổi schema chỉ vì package class Java thay.

## 18. Xử lý lỗi chuyển đổi và DLQ an toàn

Với Spring JMS listener, lỗi parse có thể xuất hiện trước khi business method chạy nếu container đã tự converter payload sang DTO. Cần cấu hình listener conversion/error handling, transaction và broker redelivery phù hợp.

Một số lỗi như payload **vĩnh viễn sai schema** sẽ không được sửa bằng cách retry 100 lần trên cùng dữ liệu. Phân loại:

| Lỗi | Có nên retry y nguyên? | Xử lý gợi ý |
| --- | --- | --- |
| Mất kết nối registry/network tạm thời | Có thể retry có giới hạn. | Backoff, metric, timeout, alert. |
| Version không được hỗ trợ | Thường **không** retry vô hạn. | Quarantine/DLQ, nâng reader hoặc migration. |
| JSON không hợp lệ/cấu trúc sai | Không, trừ khi nguồn dữ liệu được sửa hoặc decoder đổi. | DLQ, log ID/schema/error metadata an toàn. |
| Vi phạm business invariant | Thường không retry cùng dữ liệu. | Quy trình xử lý lỗi nghiệp vụ. |
| DB/service downstream tạm lỗi | Có thể retry. | Transaction, idempotency, backoff. |
| Message thiếu schema metadata | Tùy chính sách legacy. | Adapter v1 được quy định rõ hoặc quarantine. |

Đừng catch `JsonProcessingException` rồi **ack thành công, bỏ message** chỉ để giữ throughput đẹp. Ngược lại, đừng rollback vô hạn một poison message khiến Queue bị kẹt. Lựa chọn redelivery limit + DLQ và khả năng replay khi sửa decoder giúp kiểm soát vòng đời.

**Bảo mật:** header như `schemaName`/`schemaVersion` do producer đặt **không phải nguồn tin tuyệt đối**. Consumer cần xác thực quyền truy cập broker, giới hạn decoder versions, validate content; không dùng giá trị property để reflection load class tùy ý. Quản lý schema registry credentials và payload nhạy cảm theo chính sách tổ chức.

## 19. Troubleshooting theo hiện tượng

| Triệu chứng | Nguyên nhân điển hình | Hướng kiểm tra |
| --- | --- | --- |
| Old consumer lỗi khi producer thêm field | Reader v1 từ chối unknown JSON property. | Kiểm tra `FAIL_ON_UNKNOWN_PROPERTIES`, validator v1, triển khai reader trước. |
| New consumer lỗi khi nhận message cũ | Trường mới bị xem là required, thiếu default. | Xem schema v2, null/missing semantics, adapter v1. |
| JSON parse được nhưng số tiền sai | Unit/scale của field đổi mà giữ nguyên tên. | Audit business contract; đặt field mới hoặc version incompatibility. |
| Selector `schemaVersion = 2` không match | Producer gửi property kiểu String thay vì int, hoặc tên sai. | Kiểm tra raw JMS properties và selector expression. |
| Listener deserialize fail nhưng raw Message có body đúng | Converter type-id, JSON schema/DTO không tương thích. | Test raw `TextMessage`, chọn đúng decoder theo version. |
| Message V1 còn ở DLQ sau khi bỏ reader v1 | Retention/replay vượt thời gian hỗ trợ. | Giữ upcaster, migrate backlog hoặc chính sách purge rõ. |
| Registry pass compatibility nhưng consumer fail | Semantic incompatibility hoặc checker chỉ so phiên bản liền trước. | Test golden messages; cân nhắc transitive compatibility. |
| Rollout chạy tốt trên staging nhưng lỗi ở production | Còn instance reader cũ, backlog khác hoặc schema cũ hơn. | Inventory consumers/versions, Queue depth và retention. |
| Thay `ObjectMessage` bằng JSON gây lỗi | Producer/consumer khác format trong một destination. | ContentType/schemaName/version rõ và kế hoạch chuyển đổi. |
| Message liên tục redelivery với cùng ID | Poison message/unsupported schema, transaction rollback. | DLQ + alert thay vì retry vô hạn; kiểm tra eventId, delivery count. |

## 20. Bài tập kiểm tra kiến thức

1. **Reader v2 đọc writer v1 được gọi là gì?** Backward compatibility.
2. **Reader v1 đọc writer v2 được gọi là gì?** Forward compatibility.
3. **Hai hướng cùng thành công gọi là gì?** Full/bidirectional compatibility **trong phạm vi các phiên bản đã kiểm tra**.
4. **Chỉ FULL v3↔v2 có bảo đảm v3↔v1?** Không; cần transitive hoặc kiểm tra trực tiếp.
5. **V1 có `{"orderId":"O1"}`, v2 thêm trường `note` bắt buộc. V2 đọc v1 sẽ sao?** Có thể fail vì missing required; phải default/migration hoặc thay đổi contract.
6. **V1 reader có `FAIL_ON_UNKNOWN_PROPERTIES=true`, v2 thêm `note`. Old reader đọc v2 được không?** Thường không, vì unknown field; forward thất bại.
7. **JSON Schema v1 đóng `additionalProperties: false`, v2 thêm field mới. Chỉ đổi Jackson config có đủ chứng minh full?** Không; strict schema validator có thể từ chối.
8. **Có nên đổi `amount` từ VNĐ sang nghìn đồng mà vẫn giữ `schemaVersion=1`?** Không; semantic breaking change.
9. **`JMSSchemaVersion` là header chuẩn?** Không; `schemaVersion` custom JMS property là quy ước ứng dụng.
10. **`JMSMessageID` có thay schema ID hoặc eventId?** Không; mỗi loại ID có mục đích khác.
11. **Vì sao consumer mới cần đọc message cũ ngay cả khi producer cũ đã nghỉ?** Queue backlog, redelivery, durable subscription, DLQ replay.
12. **Khi nào nên dùng upcaster?** Khi phải chuyển đổi message lịch sử sang canonical domain model mà reader mới không thể xử lý trực tiếp.
13. **Mã demo ở mục 10 chứng minh điều gì?** Reader v1 parse writer v2 khi bỏ qua `note` và reader v2 parse writer v1 khi `note=null`; không chứng minh mọi schema/validator tương thích.
14. **Khi producer v2 thay đổi schema nhưng consumer v1 còn chạy, backward alone có an toàn?** Không, vì backward chỉ bảo đảm reader v2 đọc writer v1; nên nâng readers trước.
15. **Schema registry pass có đủ để bỏ integration test broker?** Không; còn conversion, headers, selector, transaction, business validation và routing.

## 21. Tài liệu tham khảo

- [Confluent Schema Registry — Schema evolution and compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): định nghĩa backward/forward/full/transitive và lưu ý kiểm tra liền kề so với toàn bộ lịch sử. Ví dụ về **một registry**, không phải mặc định của JMS.
- [Apache Avro — Specification, Schema Resolution](https://avro.apache.org/docs/current/specification/): writer/reader schema, default, field aliases và schema resolution.
- [JSON Schema — Understanding JSON Schema](https://json-schema.org/understanding-json-schema/): `required`, `additionalProperties`, nullability, validation.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field numbers, unknown fields, reserved field tags và evolution.
- [Spring Framework — JMS using/message conversion](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, `MessageConverter` và listener integration.
- [Spring Framework 6.2 — SimpleMessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html): các loại message có thể chuyển đổi.
- [Spring Framework 6.2 — MappingJackson2MessageConverter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html): JSON serialization/conversion trong Spring JMS.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): auto-configuration, embedded broker và `JmsTemplate`.
- [Jackson Databind — Deserialization features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features): `FAIL_ON_UNKNOWN_PROPERTIES` và cách xử lý unknown field.

**Tóm tắt:** Schema v2 **backward** khi reader v2 đọc được writer v1; **forward** khi reader v1 đọc được writer v2; **full** khi cả hai hướng đúng. Với Spring JMS, khả năng tương thích phụ thuộc vào **contract, serializer/converter, metadata JMS, validation và code nghiệp vụ**, không tự phát sinh chỉ nhờ `schemaVersion`. Khi thay đổi schema, hãy kiểm thử ma trận producer/consumer, lập kế hoạch rollout và tính cả message cũ còn trong Queue/DLQ.
