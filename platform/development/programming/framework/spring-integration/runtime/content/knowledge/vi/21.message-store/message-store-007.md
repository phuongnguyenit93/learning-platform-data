# Serialization payload và compatibility trong Spring Integration Message Store

## 1. Tại sao message đã lưu vẫn có thể không đọc được?

Trong module **SPRING_INTEGRATION_RUNTIME**, message di chuyển qua channel, endpoint, consumer, poller và executor. Khi dùng `MessageStore` hoặc `MessageGroupStore` để giữ message qua thời gian, người vận hành còn phải giải quyết một bài toán quan trọng: **dữ liệu đã ghi bằng phiên bản ứng dụng cũ có đọc và xử lý được sau khi triển khai phiên bản mới không?**

Giả sử một đơn hàng được đưa vào queue bền vững lúc 09:00:

~~~text
Message<OrderCreatedV1>
payload = OrderCreatedV1("ORD-101", 125000)
headers = { eventId, correlationId, contentType, ... }
~~~

Đến 09:05, ứng dụng được triển khai lại. Consumer mới dùng `OrderCreatedV2` có thêm `currency`, field cũ đã đổi tên, hoặc class Java đã chuyển package. Message còn trong store được đọc lên: có thể bị lỗi deserialize, đọc sai ý nghĩa của amount, mất header tương quan hoặc không được consumer chấp nhận.

Chủ đề **Message store → Serialization payload và compatibility** giúp trả lời:

1. `MessageStore` lưu **đối tượng** hay **bytes**? Payload và headers được biểu diễn thế nào?
2. Khác nhau giữa tính tương thích của schema nghiệp vụ, serializer và cấu trúc lưu trữ là gì?
3. Cách thiết kế envelope có `schemaVersion`, `eventId`, `contentType` và codec đọc nhiều version.
4. Cách kiểm thử readback, restart, rolling deployment, replay, rollback release và xử lý poison message.
5. Tác động lên transaction, retry, message store, correlation, threading và hiệu năng runtime.

Mục tiêu không phải chỉ “serialize được hôm nay” mà là **giữ khả năng đọc những message còn tồn tại ngày mai**.

~~~mermaid
flowchart LR
    P["Producer phiên bản cũ"] --> E["Encode payload + schemaVersion"]
    E --> S[("Persistent Message Store")]
    S --> N["App phiên bản mới\nread & deserialize"]
    N --> V{"Schema được hỗ trợ?"}
    V -->|Có| U["Chuyển về model hiện tại"]
    U --> C["Consumer / aggregator"]
    V -->|Không| Q["Quarantine / DLQ\nđể xử lý riêng"]
~~~

## 2. Phân biệt message, payload, headers và store

Spring Integration sử dụng `Message<?>` của Spring Messaging gồm:

- **Payload:** object nghiệp vụ (ví dụ `OrderCreated`), `String`, `byte[]` hoặc cấu trúc dữ liệu khác.
- **Headers:** `id`, `timestamp`, `correlationId`, `sequenceNumber`, `sequenceSize`, `replyChannel`, `errorChannel` và metadata tùy biến.
- **Channel/endpoint:** xác định cách gửi, nhận và xử lý; không tự bảo đảm được duy trì chỉ nhờ serialize payload.

Một `MessageStore` cung cấp contract lưu/lấy message; `MessageGroupStore` phục vụ **nhóm message** cho các thành phần như aggregator, resequencer và một số tình huống correlation. `ChannelMessageStore` phục vụ dữ liệu của pollable channel/queue. Các API có quan hệ nhưng cần chọn **implementation đúng loại store mà endpoint yêu cầu**.

| Thành phần | Lưu cái gì? | Câu hỏi về tương thích |
| --- | --- | --- |
| `SimpleMessageStore` in-memory | Thông tin message trong bộ nhớ ứng dụng | Không survive restart; dễ che lỗi serializer vì có thể không phải chuyển qua bytes |
| `JdbcChannelMessageStore` với durable queue | Message đang chờ được poll, trong database qua biểu diễn của provider | Serializer cho message, schema DB, transaction khi dequeue, payload/headers có đọc lại được không |
| `JdbcMessageStore` hoặc message-group store phù hợp | Message và group metadata dùng cho correlation/aggregation | Message serialization, group key, sequence, release/expiry sau nâng cấp |
| Store dựa trên Redis, MongoDB hoặc backend khác | Biểu diễn tùy implementation/provider | Serializer, codec/mapper, key namespace, TTL, format/version cụ thể |
| Broker hoặc object storage ngoài Spring Integration | Bytes/record theo contract của hệ thống đó | Payload schema, headers, codec và acknowledgement theo adapter |

**Không mặc định rằng mọi persistent store đều dùng JSON hoặc cùng một serializer.** Một số implementation lưu representation dựa trên Java serialization; loại khác dùng mapper riêng hoặc có cấu hình serializer. Cùng là `MessageStore` nhưng cách lưu và cách phát hiện lỗi có thể khác nhau giữa backend và phiên bản framework.

### Hai tầng serialization phải cùng được kiểm tra

~~~text
Message<OrderCreated>                  (domain object)
         |
         v
Encode domain: JSON/Avro/Protobuf       (payload bytes + version)
         |
         v
Message<byte[]> + Headers               (Spring Message)
         |
         v
Store serializer / persistence mapper   (cách store lưu toàn bộ message)
         |
         v
DB / Redis / Mongo / ...
~~~

Chuyển payload sang JSON `byte[]` **giúp ổn định contract nghiệp vụ**, nhưng không tự loại bỏ mọi nguy cơ tương thích nếu persistent store vẫn phải serialize **outer Message và headers** bằng cơ chế khác. Phải kiểm tra cả hai tầng với đúng backend production.

## 3. Lúc nào serialization và deserialization xảy ra?

Cần biết điểm thực thi để xác định exception có xuất hiện ở thread gửi hay thread poll:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant T as Payload encoder
    participant Q as Durable QueueChannel
    participant DB as Persistent store
    participant R as Polling consumer
    participant D as Payload decoder
    participant H as Business handler
    P->>T: Message<OrderCreated>
    T-->>Q: Message<byte[]> (versioned)
    Q->>DB: Store message (+ headers)
    Note over Q,DB: Encode/serialize ngoài hoặc trong store
    R->>DB: Poll / claim / remove
    DB-->>R: Stored message
    R->>D: Message<byte[]>
    D->>H: OrderCreated hiện tại
    Note over R,H: Decode, validate, process
~~~

| Ranh giới | Việc thường xảy ra | Lỗi có thể gặp |
| --- | --- | --- |
| Transformer trước store | Encode payload domain thành bytes | Dữ liệu không hợp lệ, mapper không hỗ trợ type |
| `send()` vào channel có store | Serialize message theo store provider rồi ghi vào backend | Object/header không serializable, connection/transaction lỗi, schema store sai |
| `receive()` từ store | Đọc row/document, dựng lại message | Không nhận ra class/serializer, bytes hỏng, incompatibility sau deploy |
| Decoder sau poll | Chuyển payload bytes theo `schemaVersion` vào model hiện tại | Unknown version, thiếu field, incompatible type/enum |
| Handler nghiệp vụ | Áp quy tắc domain và side effect | Lỗi nghiệp vụ, duplicate, transaction hoặc dependency lỗi |

Ở một số provider, conversion có thể bị trì hoãn hay nằm trong thao tác khác; bảng mô tả vị trí **logic** để thiết kế quan sát, không khẳng định tất cả backend thực thi cùng một phương thức.

Nếu deserialization của **outer message** thất bại ngay khi store đọc, decoder nghiệp vụ chưa có cơ hội chạy. Trường hợp đó cần logging/error handling tại tầng store và quy trình xử lý raw record. Nếu outer message đọc được nhưng schema payload không hỗ trợ, decoder có thể chuyển message qua quarantine/error flow.

## 4. Các định dạng payload và trade-off compatibility

| Định dạng | Lợi ích | Rủi ro thường gặp | Cách giữ tương thích |
| --- | --- | --- | --- |
| Java object serialization | Tiện khi code và dữ liệu cùng JVM/phiên bản, không cần mapper nghiệp vụ | Phụ thuộc tên class, `serialVersionUID`, trường, cấu trúc graph; nguy cơ deserialize dữ liệu không tin cậy | Chỉ dùng ở môi trường kiểm soát; kiểm thử khác phiên bản; kiểm soát class allow-list |
| JSON UTF-8 | Dễ quan sát, hỗ trợ ngôn ngữ khác, không đòi class Java cũ hiện diện | Rename field, đổi số thành string, enum mới, thiếu schema/version; payload lớn | Versioned envelope, reader chấp nhận field cũ theo contract, validation |
| Avro | Binary gọn, schema resolution, thích hợp dùng schema registry | Writer/reader schema không tương thích hoặc cấu hình registry sai | Quản lý schema ID/version, compatibility policy và default field |
| Protocol Buffers | Binary hiệu quả, field numbers giúp tiến hóa schema có kỷ luật | Tái sử dụng field number, đổi wire type, enum/oneof thay đổi ý nghĩa | Không tái dùng field tag, reserve trường đã xóa, kiểm thử schema evolution |
| CBOR/MessagePack/custom binary | Có thể gọn/nhanh | Thiếu quy tắc version và tooling kiểm tra | Định nghĩa schema, magic/version marker, test dữ liệu lịch sử |

**Java `Serializable` không đồng nghĩa backward compatibility.** Một class có thể có `serialVersionUID` ổn định nhưng vẫn không đọc được khi field đổi kiểu không tương thích, class đổi tên/package, class loader khác, hoặc logic `readObject`/constructor không phù hợp. `InvalidClassException` và `ClassNotFoundException` là dấu hiệu quen thuộc.

Với dữ liệu phải tồn tại lâu hoặc đi qua nhiều phiên bản ứng dụng, nên định nghĩa **wire contract độc lập model runtime**: mã loại event, schema version, encoding, event ID, correlation ID và bytes. JSON được dùng trong ví dụ vì dễ đọc; các nguyên tắc không phụ thuộc JSON.

## 5. Schema compatibility có nhiều chiều

Giả sử payload version 1:

~~~json
{
  "schemaVersion": 1,
  "eventType": "order.created",
  "eventId": "evt-1001",
  "correlationId": "corr-A",
  "data": {
    "orderId": "ORD-101",
    "amountMinorUnits": 125000
  }
}
~~~

Version 2 bổ sung `currency`:

~~~json
{
  "schemaVersion": 2,
  "eventType": "order.created",
  "eventId": "evt-1002",
  "correlationId": "corr-A",
  "data": {
    "orderId": "ORD-102",
    "amountMinorUnits": 125000,
    "currency": "VND"
  }
}
~~~

Trong ví dụ, **hợp đồng v1 quy định tất cả amount là VND**. Vì vậy decoder v2 có thể map v1 thành model hiện tại với `currency = "VND"`. Nếu v1 cho phép nhiều loại tiền mà không có dấu hiệu phân biệt, tự thêm VND sẽ **làm sai dữ liệu**; khi đó phải có migration từ nguồn đáng tin cậy hoặc chuyển record thành lỗi cần xử lý thủ công.

| Kiểu compatibility | Câu hỏi | Trong ví dụ |
| --- | --- | --- |
| **Backward** | Reader **mới** có đọc được data **cũ** không? | Decoder v2 nhận được `schemaVersion=1` và điền VND theo contract v1 |
| **Forward** | Reader **cũ** có đọc được data **mới** không? | Chỉ khi reader cũ có quy tắc chấp nhận field mới/version mới; nếu reject unknown version thì không |
| **Full** | Cả hai hướng trên có được bảo đảm không? | Cần thiết kế reader/version và kiểm thử cả hai chiều |
| **Semantic compatibility** | Đọc được thì ý nghĩa nghiệp vụ còn đúng không? | `125000` vẫn là đơn vị tiền nhỏ (không đổi sang major units) |

Schema tiến hóa không chỉ là parser chấp nhận JSON mới. Có thể parse thành công nhưng **sai ý nghĩa** nếu từ `amountMinorUnits` đổi sang `amount` mà không đổi quy tắc, hoặc field status bị tái sử dụng cho trạng thái khác.

### Thay đổi an toàn và thay đổi nguy hiểm

- **Thường dễ tiến hóa:** thêm field tùy chọn có default hợp lệ về nghiệp vụ; thêm metadata không ảnh hưởng quyết định cũ; giữ nguyên tên và kiểu field đang được lưu.
- **Cần kế hoạch migration:** đổi tên field, đổi package/class khi lưu bằng Java serialization, thay `long` bằng `String`, đổi đơn vị tiền, đổi format thời gian, xóa trường bắt buộc.
- **Cần kiểm tra reader cũ:** thêm giá trị enum/loại message mới, làm cũ không còn hiểu được trường hợp mới.
- **Tuyệt đối tránh âm thầm:** parse không được rồi trả object rỗng, dùng default bừa cho tiền hoặc định danh, bỏ qua event type lạ như đã xử lý thành công.

Version nên là **một phần của dữ liệu đã lưu**, không chỉ dựa vào số phiên bản artifact hoặc thời điểm deploy. Nếu cả hai nguồn gửi cùng tồn tại trong rolling deployment, một queue có thể đồng thời chứa payload nhiều version.

## 6. Ví dụ codec versioned JSON có thể chạy độc lập

Ví dụ Java 17+ sử dụng `jackson-databind`. Đặt code trong một file `StoredOrderCodec.java`; chương trình encode v2, đọc lại v2, rồi đọc một record v1 mô phỏng được lưu từ trước. Đoạn này chạy độc lập với Spring Integration để kiểm thử **wire contract** trước khi ghép store.

~~~java
package demo.integration;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

public final class StoredOrderCodec {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String EVENT_TYPE = "order.created";
    private static final int MAX_BYTES = 1024 * 1024; // 1 MiB demo limit

    private StoredOrderCodec() { }

    public record OrderCreated(
            String orderId, long amountMinorUnits, String currency) { }

    public record Decoded(
            String eventId, String correlationId, OrderCreated order) { }

    // Writer hiện tại: chỉ ghi schema v2.
    public static byte[] encodeV2(
            OrderCreated order, String eventId, String correlationId)
            throws JsonProcessingException {

        Objects.requireNonNull(order, "order");
        requireValue(eventId, "eventId");
        requireValue(correlationId, "correlationId");
        requireValue(order.orderId(), "orderId");
        requireValue(order.currency(), "currency");

        if (order.amountMinorUnits() <= 0) {
            throw new IllegalArgumentException("Invalid amountMinorUnits");
        }

        ObjectNode root = MAPPER.createObjectNode();
        root.put("schemaVersion", 2);
        root.put("eventType", EVENT_TYPE);
        root.put("eventId", eventId);
        root.put("correlationId", correlationId);

        ObjectNode data = root.putObject("data");
        data.put("orderId", order.orderId());
        data.put("amountMinorUnits", order.amountMinorUnits());
        data.put("currency", order.currency());

        byte[] bytes = MAPPER.writeValueAsBytes(root);
        if (bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Payload too large");
        }
        return bytes;
    }

    // Reader hiện tại: chấp nhận v1 và v2.
    public static Decoded decode(byte[] bytes) throws IOException {
        if (bytes == null || bytes.length == 0 ||
                bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid payload size");
        }

        JsonNode root = MAPPER.readTree(bytes);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Invalid envelope");
        }

        int version = root.path("schemaVersion").asInt(-1);
        if (version != 1 && version != 2) {
            throw new IllegalArgumentException(
                    "Unsupported schemaVersion: " + version);
        }

        String type = requiredText(root, "eventType");
        if (!EVENT_TYPE.equals(type)) {
            throw new IllegalArgumentException(
                    "Unexpected eventType: " + type);
        }

        String eventId = requiredText(root, "eventId");
        String correlationId = requiredText(root, "correlationId");
        JsonNode data = root.path("data");
        if (!data.isObject()) {
            throw new IllegalArgumentException("Missing data object");
        }

        String orderId = requiredText(data, "orderId");
        JsonNode amount = data.path("amountMinorUnits");
        if (!amount.isIntegralNumber() ||
                !amount.canConvertToLong() ||
                amount.longValue() <= 0) {
            throw new IllegalArgumentException("Invalid amountMinorUnits");
        }

        // Theo business contract v1: tiền luôn tính bằng VND.
        String currency = version == 1
                ? "VND"
                : requiredText(data, "currency");

        return new Decoded(eventId, correlationId,
                new OrderCreated(orderId, amount.longValue(), currency));
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.textValue().isBlank()) {
            throw new IllegalArgumentException("Missing/invalid " + field);
        }
        return value.textValue();
    }

    private static void requireValue(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + field);
        }
    }

    public static void main(String[] args) throws Exception {
        OrderCreated order =
                new OrderCreated("ORD-102", 125000L, "VND");
        byte[] newBytes = encodeV2(order, "evt-1002", "corr-A");
        Decoded roundTrip = decode(newBytes);
        if (!order.equals(roundTrip.order())) {
            throw new AssertionError("v2 round-trip failed");
        }

        String legacyJson = """
            {
              "schemaVersion": 1,
              "eventType": "order.created",
              "eventId": "evt-1001",
              "correlationId": "corr-A",
              "data": {
                "orderId": "ORD-101",
                "amountMinorUnits": 125000
              }
            }
            """;
        Decoded old = decode(
                legacyJson.getBytes(StandardCharsets.UTF_8));

        if (!"VND".equals(old.order().currency())) {
            throw new AssertionError("v1 compatibility failed");
        }

        System.out.println("V2 " + roundTrip);
        System.out.println("V1->current " + old);
    }
}
~~~

Kỳ vọng:

~~~text
V2 Decoded[eventId=evt-1002, correlationId=corr-A, order=OrderCreated[orderId=ORD-102, amountMinorUnits=125000, currency=VND]]
V1->current Decoded[eventId=evt-1001, correlationId=corr-A, order=OrderCreated[orderId=ORD-101, amountMinorUnits=125000, currency=VND]]
~~~

Đây là **bài kiểm tra codec**, chưa phải demo lưu JDBC. Cần thêm dependency Jackson vào classpath và cấu hình actual message store của ứng dụng để kiểm chứng tầng persistence.

### Điều gì trong ví dụ khiến contract bền hơn?

1. `schemaVersion` nói rõ cách đọc; `eventType` xác định loại event.
2. `eventId` và `correlationId` tồn tại trong **envelope**, giúp đối soát ngay cả khi một số header ngoài bị mất.
3. Writer chỉ ghi **một format hiện tại**; reader duy trì các format cũ còn trong store.
4. Decoder giới hạn kích thước, validate kiểu số, chặn event/version không hiểu thay vì tự đoán.
5. Codec trả về model hiện tại; handler không cần tự biết version 1 hay 2.
6. JSON bytes không phụ thuộc tên class Java của producer, thuận lợi cho deploy và mở rộng hệ thống.

Lưu ý: `ObjectMapper` được dùng như singleton không thay đổi cấu hình sau khi khởi tạo; sử dụng theo cách này phù hợp khi chạy nhiều consumer threads. Production có thể cần validator mạnh hơn, số byte giới hạn theo loại event và quy ước chuẩn hóa text/định danh.

## 7. Nối codec với Spring Integration channel và endpoint

Tách **encode** trước message store và **decode** sau khi lấy lại giúp boundary rõ ràng. Đây là hai method endpoint minh họa, dùng `StoredOrderCodec` ở mục 6.

~~~java
import java.io.IOException;

import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

@MessageEndpoint
class PersistedOrderTransforms {

    @Transformer(
            inputChannel = "newOrders",
            outputChannel = "durableOrders")
    public Message<byte[]> encode(
            Message<StoredOrderCodec.OrderCreated> input)
            throws IOException {

        Object eventId = input.getHeaders().get("eventId");
        Object correlation = input.getHeaders().get("correlationId");
        if (!(eventId instanceof String id) || id.isBlank() ||
            !(correlation instanceof String corr) || corr.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing eventId/correlationId headers");
        }

        byte[] encoded = StoredOrderCodec.encodeV2(
                input.getPayload(), id, corr);

        return MessageBuilder.withPayload(encoded)
                .copyHeaders(input.getHeaders())
                .setHeader(MessageHeaders.CONTENT_TYPE, "application/json")
                .setHeader("payloadSchemaVersion", 2)
                .build();
    }

    // durableOrders được cấu hình là pollable channel có message store.
    @Transformer(
            inputChannel = "durableOrders",
            outputChannel = "decodedOrders",
            poller = @Poller(fixedDelay = "1000"))
    public Message<StoredOrderCodec.OrderCreated> decode(
            Message<byte[]> input) throws IOException {

        StoredOrderCodec.Decoded decoded =
                StoredOrderCodec.decode(input.getPayload());

        return MessageBuilder.withPayload(decoded.order())
                .copyHeaders(input.getHeaders())
                .setHeader("eventId", decoded.eventId())
                .setHeader("correlationId", decoded.correlationId())
                .build();
    }
}
~~~

**Điều kiện để snippet hoạt động:**

- Khai báo các channel `newOrders`, `durableOrders` và `decodedOrders` cùng consumer cho `decodedOrders`.
- `durableOrders` phải là **pollable queue channel** được nối với persistent store thích hợp, không chỉ một `DirectChannel` có tên gợi nhớ “durable”.
- `@Poller` dùng để lấy message từ queue; cấu hình thread pool, transaction và error handling theo runtime thực tế.
- `copyHeaders(...)` giúp chuyển metadata cần thiết giữa hai representation, nhưng ID/timestamp hệ thống của message mới có thể được sinh lại theo cơ chế builder. **Dùng `eventId` riêng làm logical ID ổn định**, không dựa vào `MessageHeaders.ID` qua mọi bước.
- Trong ứng dụng thật, tách schema/content metadata thành contract có kiểm soát; `contentType` chỉ là metadata, không làm message store tự decode JSON.

Nếu encoder throw trước khi gửi đến `durableOrders`, message chưa được lưu bằng flow này. Nếu store đã nhận nhưng decoder throw lúc poll, kết quả còn phụ thuộc transaction của poller và đặc tính store: có thể được re-deliver, đã bị remove hoặc chuyển sang error flow. Đó là lý do cần thử nghiệm cả hai điểm lỗi.

### Cấu hình durable queue minh họa bằng XML

Một lựa chọn là dùng `JdbcChannelMessageStore`. Cần schema JDBC tương thích và một `DataSource` đã cấu hình:

~~~xml
<bean id="orderChannelStore"
      class="org.springframework.integration.jdbc.store.JdbcChannelMessageStore">
    <constructor-arg ref="dataSource"/>
</bean>

<int:channel id="durableOrders">
    <int:queue message-store="orderChannelStore"/>
</int:channel>
~~~

Đây là **đoạn cấu hình tích hợp**, chưa phải file XML độc lập; cần khai báo namespace `int`, Spring context, `dataSource`, chạy DDL do phiên bản Spring Integration tương ứng cung cấp và cấu hình poller/consumer.

Đừng nhầm `JdbcChannelMessageStore` dùng cho pollable channel với `JdbcMessageStore` thường được dùng cho message group/aggregation. Chọn đúng interface và implementation cho thành phần được cấu hình. Việc store sử dụng JDBC **không chứng minh payload đã tương thích**: cần kiểm tra serializer provider của toàn bộ message và thử đọc record qua deploy mới.

## 8. Headers và correlation cũng là dữ liệu phải tiến hóa

Chỉ version payload là chưa đủ. Một số header ảnh hưởng trực tiếp đến runtime:

| Header/metadata | Vai trò | Vấn đề khi lưu qua restart |
| --- | --- | --- |
| `eventId` hoặc idempotency key tùy biến | Nhận dạng logical event xuyên retry, replay | Cần ổn định; không tạo ID mới mỗi lần đọc từ store |
| `correlationId` | Gom các message cùng một quá trình/nhóm | Đổi kiểu `String` thành `UUID` hoặc đổi ý nghĩa sẽ làm tách nhóm |
| `sequenceNumber` và `sequenceSize` | Thứ tự và số phần trong splitter/aggregator | Thiếu/sai kiểu có thể khiến group không bao giờ release |
| `replyChannel` / `errorChannel` | Đường phản hồi và lỗi của flow | Tham chiếu object channel tạm thời có thể vô nghĩa sau restart |
| `contentType` và schema version | Chọn decoder đúng định dạng | Thiếu thông tin làm decode nhầm hoặc không biết version |
| `timestamp` / expiration metadata | Timeout, expiry, retention | Số giây/millisecond, timezone, TTL và clock drift cần thống nhất |

**Đặc biệt với `replyChannel` và `errorChannel`:** header có thể mang tên channel hoặc tham chiếu `MessageChannel`. Một object channel tồn tại trong application context cũ không đảm bảo có thể serialize, khôi phục hoặc chuyển tiếp sau restart. Với message bền vững, nên thiết kế địa chỉ trả lời/lỗi có thể phân giải lại và có vòng đời đủ dài (ví dụ tên/đích bền vững), hoặc thiết kế async callback riêng. Không coi temporary reply channel của gateway đồng bộ là durable route.

Với `MessageGroupStore` của aggregator, cần kiểm thử sau restart rằng:

- Message còn đủ payload, headers và sequence metadata.
- Group key/correlation strategy phiên bản mới vẫn nhận diện được group cũ.
- Release strategy có thể hoàn tất group và không giữ message mãi do đổi cách đếm/định nghĩa sequence.
- Expiry/timeout, group cleanup và lock hoạt động với cùng store/region như trước.
- Trong cluster, nhiều instance có cơ chế chia sẻ state/locking thích hợp; persistence tự nó chưa bảo đảm không có hai consumer xử lý trùng.

## 9. Compatibility matrix trước một lần nâng cấp

Trước khi deploy, lập ma trận **writer version × reader version × stored data version**. Ví dụ:

| Writer | Message trong store | Reader | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| v1 | schema 1 | v1 | OK (baseline) |
| v1 | schema 1 | v2 | **Phải OK** để nâng cấp reader trước |
| v2 | schema 2 | v2 | OK (current format) |
| v2 | schema 2 | v1 | Chỉ OK nếu reader cũ hỗ trợ, nếu không **cấm rollback deploy tùy tiện** |
| v1 + v2 đồng thời | schema 1 và 2 | v2 | **Phải OK** trong rolling deployment |
| Một record schema mới chưa được hỗ trợ | schema 3 | v2 | Quarantine có kiểm soát, không nuốt lỗi rồi ack |

Một quy trình an toàn thường là **expand → migrate/observe → contract**:

1. Đưa decoder có khả năng đọc schema cũ và mới vào tất cả consumer đang hoạt động.
2. Xác nhận consumer mới đọc được **fixtures thực sự lấy từ store phiên bản cũ**, gồm cả headers.
3. Chỉ sau đó mới bật writer emit format mới.
4. Quan sát tỷ lệ schema cũ còn trong store, số decode failures và backlog.
5. Sau khi dữ liệu cũ đã được xử lý/migrate và retention cho phép, mới xem xét gỡ decoder cũ.

Với hệ thống không thể đảm bảo reader cũ hiểu schema mới, phải có **rollback plan**: giữ reader tương thích, tạm dừng producer mới, hoặc migrate dữ liệu về định dạng cũ bằng công cụ được kiểm chứng. Đừng mặc định rollback artifact là rollback dữ liệu đã lưu.

### Thay đổi schema của chính store

Ngoài schema payload, việc nâng cấp version Spring Integration/DB driver cũng có thể thay đổi **schema bảng JDBC**, serialization metadata, key region hoặc query behavior. Chạy migration DDL đúng version, backup, kiểm tra indexes và quyền truy cập. Schema upgrade của store và schema event domain là **hai kế hoạch độc lập**; cần test kết hợp.

## 10. Retry, transaction và poison message

Khi payload deserialize không thành công, **retry cùng bytes** thường không làm schema tự trở nên hợp lệ:

~~~mermaid
flowchart TD
    S[("Persistent Store")] --> R["Poll message"]
    R --> D{"Deserialize thành công?"}
    D -->|Có| H["Business handler"]
    D -->|Không| T{"Transient? ví dụ DB/read timeout"}
    T -->|Có| B["Retry giới hạn + backoff"]
    B --> R
    T -->|Không| Q["Quarantine raw payload + metadata"]
    Q --> A["Ack/remove theo transaction\nsau khi quarantine chắc chắn"]
    H --> O["Commit và xử lý tiếp"]
~~~

Cần phân loại lỗi rõ:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Transient I/O** | DB/Redis bị timeout, khóa tạm, mạng ngắt | Retry có giới hạn và backoff; kiểm tra transaction/poller |
| **Compatibility** | Unsupported `schemaVersion`, thiếu class Java cũ | Không retry mãi; cảnh báo, nâng decoder/migration/quarantine |
| **Corrupt data** | JSON hỏng, bytes bị cắt, checksum fail | Cách ly bản ghi raw và metadata để điều tra |
| **Validation/domain** | Field bắt buộc thiếu, amount sai đơn vị | Ghi nhận event lỗi; không tự chọn giá trị mặc định gây sai nghiệp vụ |
| **Downstream failure** | Handler đã decode nhưng HTTP 503 | Retry ở handler/adapter với idempotency, độc lập codec |

Nếu poller lấy message từ **store có thao tác receive/remove transactional** cùng transaction manager phù hợp, rollback có thể khiến message vẫn còn để retry. Nếu queue in-memory hoặc thao tác remove đã commit trước lỗi, không thể giả định message sẽ quay lại.

### Vòng lặp poison message

Một message không decode được có thể liên tục xuất hiện ở đầu queue:

~~~text
receive -> decode fails -> rollback -> receive same bytes
       -> decode fails -> rollback -> ...
~~~

Hậu quả: queue không tiến, poller bận, connection pool bị chiếm, số lần log tăng, các message hợp lệ phía sau bị chặn. Biện pháp:

- Giới hạn retry và phân loại **non-retryable** cho compatibility/corruption.
- Định nghĩa quarantine/DLQ có khả năng lưu **raw bytes**, exception class, message ID, event ID nếu đọc được, store key và thời điểm.
- Đảm bảo quá trình lưu quarantine và đánh dấu/loại message lỗi có semantics transaction phù hợp; nếu cần atomicity, dùng cùng resource/store hoặc outbox.
- Theo dõi số lần message bị đọc lại, chuyển sang kênh xử lý thủ công hoặc dừng flow có kiểm soát khi serializer tầng ngoài không thể tái tạo message.
- Sau khi deploy decoder mới, có quy trình **replay có idempotency**, không sửa bytes gốc mà không audit.

**Trường hợp khó:** nếu store không deserialize được cả outer message, một `@ServiceActivator` nhận `Message<byte[]>` chưa từng thấy message; retry advice đặt tại handler **không giải quyết được lỗi ở tầng store**. Cần handler/error hook của store, chẩn đoán theo backend và phương án xử lý record trực tiếp với công cụ được kiểm soát.

## 11. Kiểm thử đáng tin cậy: fixtures, restart, mixed-version

### 11.1. Bộ fixture phải được lưu lâu dài

Tạo các record thực bằng producer cũ và lưu làm fixture có kiểm soát:

- Schema 1 hợp lệ, schema 2 hợp lệ, record với optional field thiếu.
- Record có field thêm/giá trị enum mới, field số ở biên `Long.MAX_VALUE` và amount 0/âm.
- Header `correlationId`, `sequenceNumber`, `sequenceSize`, `contentType` và metadata ứng dụng.
- Một payload hỏng và một version không hỗ trợ để kiểm tra quarantine.
- Nếu store dùng serializer Java, fixture là **serialized message/provider record** chứ không chỉ JSON domain.

Đừng chỉ test `new Writer().encode() → new Reader().decode()` trong cùng source version: test đó không chứng minh rằng binary đã lưu từ version cũ đọc được ở phiên bản mới.

### 11.2. Ma trận test

| Kiểm thử | Cách thực hiện | Dấu hiệu PASS |
| --- | --- | --- |
| Codec round-trip | Encode v2 rồi decode v2 | Domain value và eventId/correlationId đúng |
| Backward compatibility | Decode bytes v1 bằng reader v2 | Map đúng business default theo contract |
| Unsupported version | Cho `schemaVersion=99` | Error có thể phân loại; không biến thành success |
| Real store readback | Ghi message vào **đúng provider** đang chạy production, đọc lại | Payload/headers còn đúng |
| Restart | Ghi message, tắt app, chạy phiên bản khác cùng store | Consumer đọc và xử lý đúng |
| Rolling deployment | Hai version reader chạy cùng thời điểm trên queue | Không có version đọc nhầm, không tạo duplicate ngoài ý muốn |
| Rollback deploy | Writer mới đã ghi schema mới, chạy reader cũ | Đạt theo rollback plan; nếu không hỗ trợ thì phát hiện sớm |
| Crash giữa poll và commit | Cố tình kill instance theo kịch bản kiểm thử | Không mất message ngoài contract; redelivery/dedup đúng |
| Aggregator sau restart | Giữ group chưa đủ message, restart, gửi phần còn lại | Correlation/release không bị kẹt |
| Poison message | Đưa JSON hỏng/outer bytes sai codec | Quarantine/cảnh báo, queue có thể tiếp tục xử lý |

Với JDBC, kiểm tra schema DDL/index từ đúng phiên bản và transaction manager dùng chung `DataSource`. Với Redis/MongoDB, kiểm tra serializer, TTL, region/key prefix, lock/distribution và retention thật. Với nhiều instance, test concurrent consumers thay vì chỉ chạy đơn luồng.

### 11.3. Dùng một bộ dữ liệu cũ để kiểm tra release mới

Quy trình thử nghiệm nâng cấp:

~~~text
1. Chạy app v1 + real persistent store.
2. Gửi message nhưng tạm dừng consumer/poller.
3. Snapshot database/store (giữ raw bytes, headers, metadata).
4. Tắt app v1.
5. Chạy app v2 kết nối cùng bản snapshot.
6. Start consumer; kiểm tra decode + side effects + correlation.
7. Kiểm tra exception, DLQ, queue depth và remaining group.
8. Thử bản rollback nếu hệ thống yêu cầu có thể quay về v1.
~~~

Cần tránh test tự động vô tình xóa database hoặc purge queue production; dùng môi trường tách biệt và dữ liệu được quản lý.

## 12. Security, privacy và quản trị dữ liệu đã lưu

Payload bền vững tồn tại lâu hơn request/worker thread, nên quy định bảo mật cũng phải đi cùng schema:

- Không đưa token, password, session hoặc thông tin cá nhân không cần thiết vào payload/headers. Tránh persist `MessageChannel` hoặc đối tượng framework chứa state không thiết kế để serialize.
- Khi sử dụng Java native deserialization, **không deserialize bytes không tin cậy**; kiểm soát nguồn, class filtering/allow-list và cập nhật thư viện. JSON/Avro cũng cần validate input, giới hạn độ sâu/kích thước và đề phòng payload độc hại.
- Với encryption, lưu metadata cần thiết như `encoding`/`keyId` trong envelope có cấu trúc; khóa bí mật phải nằm ở KMS/secret manager. Khi rotate key, cần đảm bảo đọc được message cũ đến hết retention hoặc migrate có kiểm soát.
- Nếu nén dữ liệu, ghi rõ thuật toán và giới hạn kích thước **sau giải nén** để tránh payload bị phóng đại quá mức.
- Tránh lưu stack trace chứa payload vào log. Chỉ ghi size, schema version, event type, hash/checksum có chủ đích, channel, endpoint và ID có kiểm soát.
- Định nghĩa retention, TTL, purge policy và quyền truy cập store; message group/aggregation có thể giữ dữ liệu lâu hơn queue nếu chưa release.
- Bảo đảm backup/restore cũng lưu đủ **serializer metadata và schema registry**; restore bytes mà không có reader/key/registry sẽ không giúp hệ thống hoạt động.

## 13. Hiệu năng và vận hành runtime

Serialization/deserialization có thể tạo CPU, memory allocation và I/O, đặc biệt khi message chứa graph object lớn hoặc JSON/Avro nặng.

| Triệu chứng | Nguyên nhân khả dĩ | Điều nên đo |
| --- | --- | --- |
| `send()` vào queue chậm bất thường | Encode hoặc store write chạy đồng bộ, DB/Redis nghẽn | Duration encode, store write, connection pool |
| Poller đọc ít message dù backlog cao | Deserialize chậm, error/retry loop, transaction giữ lock | Poll latency, decode latency, queue depth, error rate |
| GC tăng sau deploy | Payload lớn, copies của `byte[]`, mapper tạo nhiều object | Allocation, heap, GC pauses, payload size distribution |
| Queue bị kẹt ở một bản ghi | Unknown version/poison message, rollback lặp | Offending store key, retry count, DLQ rate |
| Aggregator giữ group mãi | Thiếu `correlationId`/sequence hoặc reader đổi semantics | Group age, group size, expiry, release criteria |
| Một số instance lỗi, instance khác không | Phiên bản reader khác nhau hoặc serializer config lệch | App build ID, schema versions, serializer version |
| Chuyển store rồi không đọc được dữ liệu | Provider-specific serialization và layout khác nhau | Bytes lưu thật, metadata, migration strategy |

Không sử dụng eventId/orderId làm metric label vì cardinality cao. Dùng tag ổn định: `storeType`, `channel`, `eventType`, `schemaVersion`, `status`, exception family. Event ID nên đặt trong trace/log có kiểm soát để truy vấn từng message.

### Một số chỉ số quan trọng

- `store.write.count`, `store.write.error`, `store.read.count`, `store.read.error`.
- `payload.encode.duration`, `payload.decode.duration`, `payload.bytes` theo percentile.
- Số message tồn, oldest-message age, group count và oldest-group age.
- Số lần `unsupported_schema_version`, `corrupt_payload` và quarantine thành công/thất bại.
- Retry/redelivery count theo logical event, số duplicate bị dedup.
- Tỷ lệ các schema version đang tồn tại trước khi quyết định bỏ reader cũ.

Thống nhất cách đo từ lúc producer tạo message đến khi consumer commit; một `MessageStore` có khả năng lưu bền vững không tự bảo đảm exactly-once processing hoặc SLA.

## 14. Những sai lầm phổ biến và cách xử lý

| Sai lầm | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| “Đã dùng JDBC Message Store nên object nào cũng survive deploy” | JDBC bảo toàn bytes/row; class/serializer mới có thể không đọc được | Có versioned contract + real-store upgrade tests |
| “Payload là JSON, thế là xong” | Outer `Message<?>` và headers vẫn do store serializer quản lý | Kiểm tra cả envelope, headers và backend mapper |
| “Java `Serializable` thì đổi package vẫn ổn” | Native serialized form phụ thuộc class metadata | Dùng stable wire contract và migration có kiểm chứng |
| “`contentType` tự decode sau `getMessage()`” | Header là metadata; cần message converter/decoder thực sự chạy | Đặt codec ở ranh giới rõ ràng |
| “`correlationId` lấy từ `MessageHeaders.ID` mãi mãi” | Message ID có thể đổi ở các bước xây dựng message mới | Tạo logical eventId/correlationId ổn định |
| “Rollback DB sẽ tự đưa queue message trở lại” | Phải có source/store receive transactional và ack policy phù hợp | Kiểm tra queue/provider/transaction manager |
| “Thêm field optional luôn forward-compatible” | Reader cũ có thể reject unknown field hoặc schema version | Test cả hai hướng, rolling deploy |
| “Deserialize fail thì retry mãi sẽ hết lỗi” | Bytes/schema không đổi, message poison quay lại | Quarantine raw bytes, dừng retry vô hạn |
| “Đã có persistent message store là exactly once” | Redelivery và crash giữa side effects có thể gây duplicate | Idempotency/inbox/outbox, transaction và recovery rõ |
| “Chỉ cần nâng framework là store tự migrate” | Store schema và serialized representation có thể thay đổi | Version pinning, backup, compatibility/migration plan |

## 15. Bài thực hành và câu hỏi kiểm chứng

1. **Codec:** chạy `StoredOrderCodec.main()`. Đổi `schemaVersion` của JSON v1 thành 99; xác nhận decoder từ chối rõ ràng. Thử `amountMinorUnits` là chuỗi, số âm và số vượt phạm vi `long`.
2. **Đảm bảo business semantics:** sửa contract v1 để tiền có thể là nhiều currency; giải thích vì sao fallback `"VND"` không còn hợp lệ và đề xuất migration/lookup đúng.
3. **Thử với channel:** kết nối encoder/decoder mục 7 qua một `QueueChannel`; ghi `traceId`, `eventId` và `correlationId` ở trước/sau.
4. **Thử persistence thực:** thay queue trong bộ nhớ bằng `JdbcChannelMessageStore` với DDL và cấu hình tương thích; gửi nhiều message, dừng app và khởi động lại consumer. Kiểm tra chưa mất message và headers.
5. **Version cũ sau deploy:** với app v1 tạo raw rows/serialized messages rồi app v2 đọc lại; không dùng v2 tạo fixture v1 bằng cách sửa thủ công rồi kết luận toàn bộ outer serializer đã tương thích.
6. **Poison message:** đưa một record không giải mã được vào môi trường test; xác định tầng lỗi thuộc store serializer hay domain decoder; cấu hình quarantine/DLQ tránh poll lại vô hạn.
7. **Aggregator:** gửi một phần sequence, lưu group, restart, gửi phần còn lại; kiểm chứng `correlationId`, `sequenceSize`, release strategy và expiry.
8. **Rolling upgrade:** chạy hai consumer versions song song; gửi schema 1/2, sau đó thử rollback reader để kiểm chứng kế hoạch tương thích.
9. **An toàn:** thử payload có kích thước lớn và độ sâu JSON bất thường; xác minh giới hạn trước khi deserialize và điều kiện logging.
10. **Hiệu năng:** benchmark encode/decode, số byte/record, latency enqueue/dequeue và GC khi tăng kích thước payload; xác định bottleneck ở codec hay backend.

### Checklist sẵn sàng triển khai

- Có versioned payload contract và registry/quy định tiến hóa schema.
- Kiểm thử cả data cũ đọc bởi reader mới và chiều ngược lại nếu cần rollback.
- Kiểm tra serializer thực tế của **payload, outer Message, headers** trên đúng provider/phiên bản.
- Dùng logical eventId/correlationId ổn định qua restart/retry; bảo toàn sequence metadata.
- Có transaction/ack/recovery phù hợp với durable queue và message group.
- Có quarantine raw bytes cho unsupported/corrupt payload, không retry vô hạn.
- Có metric theo schema version, lỗi deserialize, queue backlog và group age.
- Có backup, retention, migration plan và test restore trước khi nâng cấp store/framework.

## 16. Nguồn tra cứu chính thức

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): các khái niệm `MessageStore` và `MessageGroupStore` trong flow.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): `QueueChannel`, pollable channel và message store cho channel.
- [Spring Integration Reference — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): cách tích hợp JDBC và yêu cầu database/schema.
- [Spring Integration API — MessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageStore.html) và [MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html): contract lưu message/group.
- [Spring Integration API — JdbcChannelMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcChannelMessageStore.html): persistent channel storage.
- [Spring Framework — Message / MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): message abstraction và headers.
