# Kiểm tra header và payload trong Spring Integration Adapters

## 1. Mục tiêu và bối cảnh bài học

Trong **Spring Integration**, dữ liệu không đơn thuần được chuyển từ một hàm Java sang hàm khác: một **message** mang theo **payload** (nội dung nghiệp vụ) và **headers** (metadata giúp định tuyến, chuyển đổi, trả lời, truy vết và xử lý lỗi). Khi dùng inbound/outbound adapter, gateway, poller và MessageChannel để tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, một payload đúng nhưng header sai cũng có thể gây lỗi nghiêm trọng: gửi nhầm topic, mất correlation, ghi sai filename, thiếu content type hoặc mất thông tin định danh yêu cầu.

Bài **“Kiểm tra header và payload”** thuộc chương **Testing** của module **Spring Integration Adapters**. Mục tiêu không phải chỉ viết `assertEquals("OK", message.getPayload())` mà là thiết kế và kiểm chứng **hợp đồng message đầu vào–đầu ra (message contract)**, xác định ranh giới kiểm tra ở từng adapter, và biết kết luận nào được hỗ trợ bởi bằng chứng test.

Sau bài này, người học có thể:

- Phân biệt `Message<?>`, payload, `MessageHeaders` và những header do framework, adapter hoặc ứng dụng định nghĩa.
- Chọn đúng điểm quan sát trên `DirectChannel`, `QueueChannel`, gateway reply, error channel và các flow bất đồng bộ.
- Viết unit test, flow test JUnit 5 và adapter integration test kiểm tra **kiểu payload, nội dung, header, số lượng, thứ tự, correlation và lỗi**.
- Kiểm tra mapping metadata giữa Spring message và file/SFTP/HTTP/JMS/AMQP/Kafka/DB mà không giả định các giao thức dùng chung tên header.
- Phát hiện lỗi mất header khi biến đổi message, chuyển kiểu/encoding sai, dữ liệu vượt phạm vi tenant, hoặc sao chép thông tin nhạy cảm vào message ngoài ý muốn.
- Thiết kế test đáng tin với thời hạn hữu hạn, fixture cô lập và assertion ở hệ thống đích khi contract yêu cầu side effect.

**Phạm vi code:** Các ví dụ sử dụng Java hiện đại, Spring Integration Java DSL, JUnit 5 và Spring Test theo cách minh họa. Những header cụ thể do adapter cấp có thể khác theo module, cấu hình mapper và phiên bản; trước khi áp dụng, cần đối chiếu API của đúng phiên bản đang dùng.

## 2. Message contract là gì?

Một message trong Spring Messaging có dạng khái niệm:

~~~text
Message<T>
 ├─ payload: T
 │   └─ nội dung nghiệp vụ hoặc representation trung gian
 └─ headers: Map<String, Object>
     ├─ metadata do Spring quản lý
     ├─ metadata transport/adapter
     └─ metadata nghiệp vụ do ứng dụng định nghĩa
~~~

Ví dụ một event đơn hàng đi từ file/SFTP vào hệ thống:

~~~text
Payload:
  OrderEvent(orderId="ORD-42", amountMinor=12500, currency="VND")

Headers:
  correlationId = "corr-2026-42"
  sourceSystem  = "sftp-partner-a"
  tenantId      = "tenant-a"
  eventType     = "order.created"
  schemaVersion = "1"
  sourceFile    = "orders-42.csv"
~~~

**Payload** trả lời câu hỏi: *“Thông tin cần xử lý là gì?”*. **Headers** trả lời các câu hỏi bổ sung: *“Nguồn nào? Phần xử lý nào? Chuyển đến đâu? Trả về ai? Có cùng yêu cầu không? Định dạng gì?”*

Không phải header nào cũng là dữ liệu tin cậy. Ví dụ `tenantId` xuất phát từ HTTP request bên ngoài cần được đối chiếu với danh tính đã xác thực, không được dùng ngay để chọn database tenant hoặc resource nội bộ. Message test phải kiểm tra **nguồn, sự tồn tại, kiểu dữ liệu và điều kiện sử dụng** của header.

### 2.1. Payload và headers không thay thế nhau

| Thông tin | Nên đặt ở đâu? | Lý do |
|---|---|---|
| `orderId`, số tiền, sản phẩm | Payload hoặc DTO theo schema | Là dữ liệu nghiệp vụ chính |
| `correlationId` xuyên luồng | Header nghiệp vụ được kiểm soát; có thể sao chép sang event envelope khi cần bền vững | Truy vết giữa adapter, gateway và log |
| Loại sự kiện/số phiên bản schema | Payload envelope và/hoặc header theo contract | Consumer biết cách diễn giải |
| Filename/path | Adapter header hoặc payload metadata đã được chuẩn hóa | Phục vụ file routing, audit |
| Kafka key/routing key | Header transport hoặc record configuration | Quyết định partition/destination |
| Reply/error channel | Header messaging nội bộ nếu flow sử dụng | Điều phối phản hồi/lỗi |
| Password, access token, private key | **Không đưa vào headers nghiệp vụ để phát tán** | Rủi ro rò rỉ qua message bus/log/trace |
| Tenant/quyền truy cập | Dữ liệu từ security context đã xác minh, có mapping rõ | Không tin claim từ caller tùy ý |

**Thiết kế contract trước khi test**, sau đó mới quyết định header nào bắt buộc, header nào tùy chọn và biến đổi nào được phép loại bỏ chúng.

## 3. Những lớp header cần phân biệt

### 3.1. Header do Spring Framework quản lý

`org.springframework.messaging.MessageHeaders` chứa các khóa chuẩn như:

- `MessageHeaders.ID`: định danh của **message instance**.
- `MessageHeaders.TIMESTAMP`: thời điểm tạo message theo cơ chế framework.
- `MessageHeaders.CONTENT_TYPE`: nội dung kiểu MIME/content type khi được đặt.
- `MessageHeaders.REPLY_CHANNEL`: kênh nhận reply trong một số luồng request–reply.
- `MessageHeaders.ERROR_CHANNEL`: kênh báo lỗi khi thành phần/luồng có hỗ trợ.

**Không mặc định** mọi message có tất cả các header trên. `replyChannel` và `errorChannel` thường chỉ xuất hiện khi luồng/gateway cần. ID và timestamp do framework quản lý có thể được tạo lại khi endpoint tạo message mới, nên không dùng chúng làm khóa nghiệp vụ bền vững xuyên hệ thống.

### 3.2. Header của Spring Integration và adapter

Spring Integration bổ sung những nhóm metadata tùy module, chẳng hạn:

- **File:** filename, original filename, relative path; kiểm tra constant trong `FileHeaders` và header mapper của phiên bản.
- **SFTP:** remote directory, remote filename, host/transport-related metadata khi adapter đặt/cấu hình.
- **HTTP:** HTTP request/response headers và status qua `HttpHeaders`, header mapper hoặc message conversion.
- **JMS:** correlation ID, destination, message ID, delivery mode, redelivered flag... theo JMS mapping.
- **AMQP/RabbitMQ:** exchange, routing key, delivery tag, consumer queue và metadata theo adapter mapping.
- **Kafka:** topic, partition, key, offset, timestamp và metadata producer/consumer theo mapper.
- **JDBC/JPA:** thông thường payload là row/DTO, metadata nghiệp vụ do flow tạo; không có một bộ header thống nhất cho mọi schema.

**Không phải tất cả các adapter mặc định phát cùng tên hoặc giữ mọi header.** Quy tắc của một transport không tự áp dụng cho transport khác. Với metadata cụ thể, dùng constant của module khi có và test **message thực** ở đúng ranh giới.

### 3.3. Custom headers do ứng dụng định nghĩa

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("correlationId", "corr-42")
        .setHeader("tenantId", "tenant-a")
        .setHeader("eventType", "order.created")
        .setHeader("schemaVersion", "1")
        .build();
~~~

Những header này có thể được truyền qua một số endpoint trong flow, nhưng **sự bảo toàn không nên chỉ được suy đoán**. Nếu một transformer tạo message mới, router tạo flow khác hoặc adapter đổi transport, test phải xác minh những header cần thiết còn hiện diện theo thiết kế.

## 4. Kiến trúc kiểm thử header/payload qua adapter

~~~mermaid
flowchart LR
    EXT["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> IN["Inbound adapter"]
    IN --> IC["inputChannel"]
    IC --> MAP["Transform / filter / route / enrich"]
    MAP --> OC["outputChannel"]
    OC --> OUT["Outbound adapter / gateway"]
    OUT --> TARGET["Hệ thống đích"]
    IC -. "test observation" .-> T1["Kiểm payload/header đầu vào"]
    OC -. "test observation" .-> T2["Kiểm message sau biến đổi"]
    TARGET -. "integration test" .-> T3["Kiểm protocol/side effect"]
    MAP -. "error" .-> ERR["Error flow / recovery"]
~~~

Các lớp kiểm tra phải trả lời **khác nhau**:

| Lớp | Cách test | Có thể kết luận |
|---|---|---|
| Unit mapper | Gọi mapper với DTO/`Message<?>` | Logic chuyển đổi dữ liệu/header do mapper thực hiện |
| Channel/flow test | Gửi message vào channel, nhận ở terminal channel | Wiring/transform/routing đúng trong context test |
| Adapter contract test | Tạo file/HTTP request/broker record rồi nhận message | Cách adapter map transport ↔ Spring message |
| Outbound adapter test | Gửi message thật qua handler và dùng mock server/broker/DB | Mapping ra request/record/file và phản hồi phù hợp |
| End-to-end test | Chạy cả inbound và outbound với hạ tầng thử nghiệm | Kết quả nghiệp vụ qua toàn chuỗi được quan sát |

**Không đồng nhất** `inputChannel.send(...) == true` với HTTP POST hoặc broker publish đã thành công. Nếu một handler/transport bất đồng bộ, message mới chỉ được tiếp nhận để xử lý tiếp. Khi cần xác minh side effect, kiểm tra **ở đích**.

## 5. Chọn MessageChannel làm điểm quan sát đúng

| Channel | Đặc điểm | Cách assert |
|---|---|---|
| `DirectChannel` | Dispatch đồng bộ đến một subscriber được chọn trong cấu hình mặc định | Assert handler/reply sau `send()` khi flow thực sự đồng bộ |
| `QueueChannel` | `PollableChannel` với queue | `receive(timeout)` rồi kiểm payload/header |
| `PublishSubscribeChannel` | Fan-out đến nhiều subscriber; có thể dùng executor | Assert từng subscriber/nhánh, không nhầm competing consumer |
| `ExecutorChannel` | Handler chạy qua executor, thường bất đồng bộ | Chờ bằng latch/await/queue có timeout |
| `RendezvousChannel` | Sender/receiver gặp nhau đồng bộ | Kiểm send/receive timeout |
| `PriorityChannel` | Message được nhận theo priority | Kiểm thứ tự theo priority nếu contract |
| Reactive channel | Subscription/backpressure | Dùng công cụ test reactive phù hợp |

**Cảnh báo quan trọng:** Gắn thêm một test subscriber vào `DirectChannel` production không tạo ra bản sao message cho test. Nó có thể trở thành **consumer cạnh tranh**, khiến handler thật không nhận được message. Nếu cần theo dõi mà không chiếm message, hãy dùng wire tap/monitoring channel được thiết kế rõ hoặc terminal output riêng của test context.

### 5.1. Vì sao QueueChannel thường được dùng trong test?

`QueueChannel` cho phép nhận output với timeout hữu hạn mà không cần chờ cố định:

~~~java
Message<?> actual = observedOutput.receive(1000);
assertNotNull(actual, "Không có message trong thời gian test");
~~~

Nhưng nếu `observedOutput` có **consumer khác** đang đọc, test có thể bỏ lỡ message. Hãy cô lập output channel, dọn queue giữa các test và dùng correlation ID để ngăn nhận nhầm.

### 5.2. Không suy diễn quá mức từ queue rỗng

`observedOutput.receive(0) == null` chỉ có nghĩa **tại thời điểm kiểm tra** không có message chờ. Với executor/poller, message có thể đến muộn. Nếu contract yêu cầu “không có output”, cần kiểm soát thời điểm hoàn tất, deadline hoặc trạng thái downstream.

## 6. Ví dụ đầy đủ: JUnit 5 kiểm tra payload và headers qua flow

Một flow thử nghiệm nhận String từ nguồn adapter giả lập, chuẩn hóa nội dung, rồi đưa output vào `QueueChannel`. Ví dụ này kiểm tra **message contract ở channel**, không kết nối hạ tầng ngoài.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class MessageContractConfig {

    @Bean
    MessageChannel adapterInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel observedOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeFlow() {
        return IntegrationFlow.from("adapterInput")
                .<String, String>transform(String::trim)
                .channel("observedOutput")
                .get();
    }
}
~~~

Test tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(MessageContractConfig.class)
class MessageContractTest {

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel adapterInput;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel observedOutput;

    @Test
    void normalizesPayloadButPreservesBusinessHeaders() {
        Message<String> incoming = MessageBuilder
                .withPayload("  ORD-42  ")
                .setHeader("correlationId", "corr-42")
                .setHeader("tenantId", "tenant-a")
                .setHeader("sourceSystem", "sftp")
                .build();

        assertTrue(adapterInput.send(incoming));

        Message<?> actual = observedOutput.receive(1000);
        assertNotNull(actual);

        assertInstanceOf(String.class, actual.getPayload());
        assertEquals("ORD-42", actual.getPayload());
        assertEquals("corr-42",
                actual.getHeaders().get("correlationId"));
        assertEquals("tenant-a",
                actual.getHeaders().get("tenantId"));
        assertEquals("sftp",
                actual.getHeaders().get("sourceSystem"));

        // Flow đồng bộ và chỉ một output: hàng đợi phải trống lúc này.
        assertNull(observedOutput.receive(0));
    }
}
~~~

**Điều test chứng minh:** `DirectChannel` đã chuyển message, transformer chuẩn hóa String và các header nghiệp vụ cần giữ được thấy ở output. Đây là một **flow test** với Spring context thật.

**Điều chưa chứng minh:** SFTP thực sự đã tải file, một broker đã ack hoặc HTTP outbound đã gửi body/header đến server. Các bước đó cần test adapter và hệ thống đích riêng.

### 6.1. Tránh một assertion quá lỏng

~~~java
assertNotNull(observedOutput.receive(1000));
~~~

Điều này chỉ chứng minh **có một message**. Nó có thể mang sai payload, thiếu tenant, sai correlation hoặc từ test khác. Ít nhất phải assert **kiểu, dữ liệu nghiệp vụ và header quan trọng**.

### 6.2. Tránh một assertion quá chặt

Không nên mặc định:

~~~java
assertEquals(incoming.getHeaders(), actual.getHeaders());
~~~

Toàn bộ map headers có thể khác vì framework tạo ID/timestamp mới hoặc endpoint quản lý metadata. Chỉ so sánh **tập header thuộc contract**, kèm assertion không có header nguy hiểm nếu cần.

## 7. Unit test MessageBuilder và kiểu payload

Trước khi đưa message qua adapter, hãy xác minh cách tạo payload và header:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

class MessageConstructionTest {

    @Test
    void buildsAContractWithStableBusinessIdentifiers() {
        Message<String> message = MessageBuilder
                .withPayload("{\"orderId\":\"42\"}")
                .setHeader("eventId", "order-created-42")
                .setHeader("correlationId", "corr-42")
                .setHeader(MessageHeaders.CONTENT_TYPE,
                           MimeTypeUtils.APPLICATION_JSON)
                .build();

        assertEquals("{\"orderId\":\"42\"}", message.getPayload());
        assertEquals("order-created-42",
                message.getHeaders().get("eventId"));
        assertEquals("corr-42",
                message.getHeaders().get("correlationId"));

        assertNotNull(message.getHeaders().getId());
        assertNotNull(message.getHeaders().getTimestamp());
    }
}
~~~

**Chú ý:** ví dụ tạo JSON dưới dạng String; đặt header content type **không tự động biến payload thành byte[] hoặc DTO**. Việc mã hóa/giải mã được thực hiện bởi converter/transformer hoặc adapter theo cấu hình.

### 7.1. Type mismatch phải được kiểm tra rõ

Nếu handler dự kiến `OrderEvent` nhưng nhận String raw hoặc `byte[]`, test phải chứng minh:

- Có converter đúng được chạy, hoặc
- Handler từ chối payload với lỗi được xác định.

**Không bỏ qua lỗi bằng cách cast dữ liệu**. Việc một String chứa JSON hợp lệ không có nghĩa object Java đã có type `OrderEvent`.

### 7.2. MessageHeaders và tính bất biến

`MessageHeaders` được cung cấp như một cấu trúc metadata không nên bị sửa trực tiếp qua map trả về. Để bổ sung hoặc thay header, xây message mới bằng `MessageBuilder` hoặc dùng enricher/transformer phù hợp.

~~~java
Message<String> original = MessageBuilder
        .withPayload("ORD-42")
        .setHeader("eventType", "order.created")
        .build();

Message<String> revised = MessageBuilder.fromMessage(original)
        .setHeader("correlationId", "corr-42")
        .build();

assertEquals("ORD-42", revised.getPayload());
assertEquals("order.created",
        revised.getHeaders().get("eventType"));
assertEquals("corr-42",
        revised.getHeaders().get("correlationId"));
~~~

Không cần cố gắng sửa map header bằng `put`: contract được kiểm tra trên **message trả về sau biến đổi**, không trên việc mutate metadata tại chỗ.

## 8. Kiểm tra header propagation qua transformer, filter và enricher

Khi đi qua nhiều endpoint, message có thể đổi payload hoặc thêm metadata. Cần xác định **điều gì phải giữ**, **điều gì phải đổi**, **điều gì phải loại bỏ**.

| Endpoint | Hành vi đáng kiểm tra | Ví dụ |
|---|---|---|
| Transformer | Kiểu/nội dung payload mới; header nghiệp vụ cần thiết còn tồn tại | CSV String → `OrderEvent` |
| Header enricher | Header mới được tính đúng; không ghi đè header đã tin cậy ngoài policy | Thêm `eventType` |
| Filter | Message hợp lệ đi tiếp; message bị loại không gây side effect | Amount > 0 |
| Router | Chuyển đúng channel/destination; không tin header từ người gửi tùy ý | `tenantId` → tenant channel |
| Splitter | Một input → nhiều output; correlation/sequence phù hợp | Batch ba order |
| Aggregator | Group theo correlation, kết quả chỉ xuất khi đủ điều kiện | Ghép batch |
| Bridge | Message được chuyển đến output channel đúng | Không mất header quan trọng |
| Gateway | Request/reply mapping, reply channel và timeout | HTTP/gRPC/JMS request–reply |

### 8.1. Test transformer không vô tình làm rơi correlation

Nếu transformer chỉ trả payload mới, nhiều endpoint của Spring Integration có cơ chế truyền header từ request sang reply theo cấu hình. Tuy nhiên không nên **dựa vào phỏng đoán** khi custom transformer tạo `Message<?>` mới hoặc có header filter.

Ví dụ hành vi mong đợi:

~~~text
Input:
  payload = "  ORD-42  "
  correlationId = "corr-42"
  tenantId = "tenant-a"

After transformation:
  payload = "ORD-42"
  correlationId = "corr-42"
  tenantId = "tenant-a"
~~~

Test phải assert cả ba trường. Khi thay implementation từ built-in transformer sang custom function, test sẽ phát hiện mất header.

### 8.2. Khi nào cần xóa header?

Không phải giữ mọi header là an toàn. Ví dụ một inbound HTTP adapter nhận header `Authorization` từ client, nhưng outbound message chuyển sang Kafka có thể **không được phép** mang token ấy. Contract cần chỉ định header phải redaction/drop trước khi ra biên khác.

Assertion minh họa:

~~~java
Message<?> actual = output.receive(1000);
assertNotNull(actual);
assertNull(actual.getHeaders().get("Authorization"));
assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
~~~

Cần thống nhất tên header theo hệ thống cụ thể; `Authorization` ở đây là **header ứng dụng minh họa**, không khẳng định tất cả adapters map tên này nguyên vẹn.

## 9. Header bắt buộc, tùy chọn và giá trị mặc định

Một contract tốt nên phân ba nhóm:

1. **Bắt buộc:** thiếu là từ chối hoặc báo lỗi. Ví dụ `eventId` cho idempotency, `tenantId` đã xác minh trước khi ghi dữ liệu đa tenant.
2. **Tùy chọn:** thiếu vẫn xử lý hợp lệ theo một quy tắc rõ. Ví dụ `sourceFileName` nếu event đến từ HTTP.
3. **Có mặc định an toàn:** ví dụ `schemaVersion` chỉ default sang một version đã được định nghĩa cho dữ liệu cũ; không tự nâng quyền hoặc đổi đích.

Ma trận test:

| Trường | Có | Thiếu | Sai kiểu | Không hợp lệ |
|---|---|---|---|---|
| `correlationId` | Giữ và truyền qua flow | Sinh theo policy hoặc từ chối | Từ chối nếu contract yêu cầu String | Quá dài/trùng/lộ PII → xử lý |
| `tenantId` | So với identity đã xác minh | Từ chối ở tài nguyên phân tenant | Từ chối | Tenant không được phép → từ chối |
| `schemaVersion` | Dùng converter phù hợp | Chỉ default nếu contract cho phép | Từ chối | Unknown version → reject/DLQ |
| `eventType` | Router chọn nhánh | Error/reject | Từ chối | Không route về nhánh mặc định có đặc quyền |
| `sourceFileName` | Dùng để audit/target name nếu đã validate | Fallback có kiểm soát | Từ chối | Chặn traversal/đường dẫn trái phép |

**Đừng kiểm thử “không có header” bằng cách chờ timeout vô hạn**. Một input không hợp lệ phải có kết quả quy định: exception đồng bộ, reject output, `ErrorMessage` hoặc dead-letter flow.

## 10. Kiểm tra content type, charset, JSON và binary payload

Payload có thể cùng một ý nghĩa nghiệp vụ nhưng có biểu diễn khác:

~~~text
Java DTO  -> JSON String -> UTF-8 byte[] -> transport record
   ^                               |
   |                               v
  mapper                      converter/serializer
~~~

Kiểm tra cần đặt tại **đúng ranh giới**:

| Ranh giới | Assertion |
|---|---|
| DTO sau parser | Kiểu Java, trường bắt buộc, giá trị chính xác |
| JSON String sau serializer | JSON hợp lệ, schema, tên field và kiểu |
| byte[] trước transport | Byte encoding/size/content chính xác |
| HTTP request | `Content-Type`, charset nếu áp dụng, body thực gửi |
| JMS/AMQP/Kafka record | Converter/serializer và metadata transport |
| File/SFTP output | Nội dung file thật sau khi ghi, line endings/encoding theo contract |

### 10.1. Byte array không thể so bằng toString()

~~~java
byte[] expected = "Xin chào".getBytes(StandardCharsets.UTF_8);
byte[] actual = (byte[]) result.getPayload();

assertArrayEquals(expected, actual);
~~~

`actual.toString()` của mảng byte không phải nội dung. Nếu nội dung là text, dùng charset đã thống nhất để decode; nếu là binary, kiểm byte/hash/length theo contract.

### 10.2. JSON: so schema và trường, không phụ thuộc thứ tự key

~~~java
JsonNode tree = objectMapper.readTree(
        (String) result.getPayload());

assertEquals("ORD-42", tree.path("orderId").asText());
assertEquals("VND", tree.path("currency").asText());
assertEquals(12500, tree.path("amountMinor").asLong());
~~~

`objectMapper` là Jackson `ObjectMapper` của test fixture và payload được giả định là String. Nếu payload là `byte[]`, dùng overload parse byte. Kiểm thử số tiền nên dùng **đơn vị nhỏ nhất bằng số nguyên** hoặc decimal chính xác theo contract, tránh assert bằng dấu phẩy động khi độ chính xác là yêu cầu.

### 10.3. Content type phải tương thích với payload

Ví dụ header công bố `application/json` nhưng body là CSV có thể làm converter/consumer lỗi. Một test hoàn chỉnh phải so cả header `MessageHeaders.CONTENT_TYPE`, payload thực và request/record ở đích (với transport adapter có header mapper riêng).

## 11. Kiểm tra File inbound: từ File tới payload nghiệp vụ

File inbound adapter có thể đọc file từ thư mục và phát message với payload `java.io.File`. Những bước đọc bytes, parse CSV hoặc transform thành DTO thường do endpoint tiếp theo thực hiện. **Test cần phân biệt payload tại source channel và payload sau transformer**.

Tình huống:

~~~text
Input directory:
  orders-42.csv: orderId,total
                 ORD-42,12500
  README.txt: file không được xử lý

File inbound adapter:
  pattern *.csv
  output Message<File>

CSV parser:
  output Message<OrderEvent>
  headers sourceFileName="orders-42.csv", eventType="order.created"
~~~

### 11.1. Kiểm tra FileReadingMessageSource độc lập

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.Message;

class FilePayloadContractTest {

    @TempDir
    Path inbox;

    @Test
    void fileSourceCreatesFilePayloadFromMatchingPath() throws Exception {
        Files.writeString(
                inbox.resolve("orders-42.csv"),
                "orderId,total\nORD-42,12500\n",
                StandardCharsets.UTF_8);

        Files.writeString(
                inbox.resolve("ignore.tmp"), "ignored",
                StandardCharsets.UTF_8);

        FileReadingMessageSource source = new FileReadingMessageSource();
        source.setDirectory(inbox.toFile());
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        source.afterPropertiesSet();

        Message<File> found = source.receive();
        assertNotNull(found);
        assertInstanceOf(File.class, found.getPayload());
        assertEquals("orders-42.csv", found.getPayload().getName());
        assertTrue(found.getPayload().isFile());
    }
}
~~~

Test này chỉ chứng minh **file source và filename filtering**, chưa kiểm scheduler/poller, header custom hay downstream parsing.

### 11.2. Kiểm tra header file đúng nguồn

Nếu một transformer đặt header `sourceFileName` từ `File.getName()`, test cần xác minh:

- Header được tạo bằng **metadata của file thực**, không lấy từ header người dùng tùy ý.
- Giá trị được chuẩn hóa an toàn và đủ để truy vết.
- Hệ thống tránh dùng path ngoài thư mục cho phép.
- Đường dẫn đầy đủ có thể là dữ liệu vận hành nhạy cảm; chỉ log nếu cần và được cho phép.

Nếu adapter cung cấp header file cụ thể theo module, dùng hằng số từ `FileHeaders` tương ứng và assert **đúng tại output của adapter**. Nếu custom transformer đổi tên header, test ở channel kế tiếp phải dùng tên custom đó; **không giả định header truyền xuyên mọi endpoint**.

### 11.3. Filter và duplicate

`SimplePatternFileListFilter("*.csv")` kiểm tra tên; nó **không tự bảo đảm accept-once**. Nếu yêu cầu mỗi file chỉ được xử lý một lần, cấu hình filter/metadata store phù hợp và test:

1. Poll lần đầu có một message.
2. Poll tiếp không tái phát ngoài policy.
3. Restart endpoint với metadata store bền vững có hành vi đã quy định.
4. File bị sửa hoặc trùng tên được xử lý theo contract.

Chỉ test header/payload của lần poll đầu tiên không đủ chứng minh chống trùng hoặc xử lý lifecycle.

## 12. Kiểm tra SFTP inbound/outbound: metadata remote và nội dung thực

SFTP tích hợp qua SSH có thể đưa file remote về staging local hoặc phát dữ liệu theo adapter/streaming mode. Một test chỉ nhìn payload `File` có thể không thấy lỗi remote directory, partial transfer hay file bị đọc khi đang upload.

Các metadata thường quan tâm:

| Trường nghiệp vụ | Nguồn | Assertion |
|---|---|---|
| `sourceSystem` | Cấu hình adapter/flow đã tin cậy | Đúng SFTP partner đã phê duyệt |
| Remote filename/path | Adapter hoặc synchronizer | Đúng thư mục/filename, không traversal |
| Local temporary filename | Staging/synchronizer | Không coi file dở là đã xử lý hoàn tất |
| File content/size/hash | File remote và local | Readback khớp sau đồng bộ |
| `correlationId` | Business file ID hoặc event metadata | Liên kết file với từng operation downstream |
| Timestamp/modified info | Metadata nếu adapter expose | Xử lý timezone, clock skew và freshness theo policy |

**Không có một header SFTP thống nhất cho mọi kiểu adapter.** SFTP synchronizer, inbound streaming adapter và outbound adapter có thể đặt metadata khác nhau. Cần test thực tế tại đúng channel và dựa trên API hằng số/module của phiên bản đang dùng.

### 12.1. Inbound SFTP

Dùng server SFTP cô lập/container, tạo file remote và kiểm tra:

- File được tải đúng byte (đặc biệt UTF-8 và line endings).
- Message sau parsing có payload đúng schema, header origin chính xác.
- File tạm/partial upload không được coi như file sẵn sàng.
- Retry/reconnect không phát một business event trùng ngoài ý định.
- Sai host key hoặc credential bị từ chối, không disable SSH verification để test xanh.

### 12.2. Outbound SFTP

Ví dụ message trước outbound:

~~~text
payload: byte[] containing order CSV
headers:
  remoteDirectory = "/partners/a/outgoing"
  targetFileName   = "orders-42.csv"
  eventId          = "order-export-42"
~~~

Những tên ở trên là **hợp đồng ứng dụng minh họa**, không phải cam kết header mặc định của SFTP module. Test phải xác minh **adapter cấu hình mapping** các giá trị này, và ở test server:

- Remote file thật xuất hiện đúng directory.
- Nội dung đúng byte/charset.
- Tên không bị escape ra ngoài folder được phép.
- Temporary file và rename hoàn thành theo contract.
- Lỗi upload, network timeout và retry không báo thành công giả.

**Collector trước outbound chỉ chứng minh message được chuẩn bị**, chưa chứng minh remote file đã được ghi.

## 13. HTTP inbound: từ request headers và body tới Message

HTTP inbound gateway thường nhận request bên ngoài rồi tạo Spring message. Một contract ví dụ:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
X-Correlation-Id: corr-42
X-Tenant-Id: tenant-a

{"orderId":"ORD-42","amountMinor":12500}
~~~

Test cần kiểm tra:

1. Request method, URL và content type đúng route.
2. HTTP message converter parse body thành đúng representation/DTO.
3. Header mapper **chỉ chuyển các header được phép**.
4. Correlation giữ đúng tên và kiểu qua Spring message.
5. Tenant được xác minh từ security context/policy, **không chỉ tin header tự khai**.
6. Gateway trả reply/status/body phù hợp; thiếu reply hoặc timeout có hành vi rõ.
7. Invalid JSON, content type sai, thiếu auth hoặc header quá lớn bị xử lý đúng.

**Không giả định** `X-Correlation-Id` trong HTTP request tự trở thành header custom `correlationId` trong Spring message. Cần mapper/enricher/transformer hoặc logic chủ động. Test phải dựa trên **tên header sau khi mapping thật**.

### 13.1. Ví dụ test hợp đồng HTTP bằng mock client/server

Với ứng dụng dùng Spring MVC inbound HTTP, có thể gửi request qua `MockMvc` hoặc HTTP client test thay vì gọi trực tiếp transformer. Ý tưởng assertion:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Correlation-Id", "corr-42")
        .content("{\"orderId\":\"ORD-42\",\"amountMinor\":12500}"))
    .andExpect(status().isAccepted());

// Sau đó thu message ở channel thử nghiệm có timeout.
Message<?> received = observedOrders.receive(1000);
assertNotNull(received);
assertEquals("corr-42", received.getHeaders().get("correlationId"));
~~~

Đây là **snippet minh họa**: endpoint test phải cấu hình HTTP inbound gateway/controller, response status theo contract, header mapper, `mockMvc` và `observedOrders`. Không phải Spring Integration gateway nào cũng tự tạo controller `/api/orders` hay status 202. Test phải cung cấp flow thật phù hợp với ví dụ.

### 13.2. HTTP inbound truyền header bảo mật

Một message có thể vô tình chứa `Authorization` hoặc cookie khi adapter map tất cả request headers. Hãy test chính sách **allowlist**: downstream chỉ nhận những trường cần thiết, không đưa raw bearer token vào Kafka hoặc audit log. Việc chỉ drop một header có tên đúng chữ hoa không đủ nếu lớp HTTP xử lý tên header không phân biệt hoa–thường; kiểm tra mapper và chuẩn hóa phù hợp.

## 14. HTTP outbound: header Spring không tự thành HTTP header

Giả sử flow gửi:

~~~text
Message payload: {"orderId":"ORD-42"}
Message headers:
  correlationId = corr-42
  contentType   = application/json
  tenantId      = tenant-a
~~~

Một outbound HTTP adapter/gateway phải chọn:

- HTTP method/URI và danh sách destination được phép.
- Body serializer và content type.
- **Header mapper** chuyển các header nội bộ sang tên header HTTP đúng.
- Authorization lấy từ cơ chế credential an toàn, không sao chép token đầu vào tùy ý.
- Response status/body/error được xử lý theo hợp đồng one-way hoặc request–reply.

### 14.1. Kiểm tra bằng mock HTTP server

Với một outbound handler dùng `RestTemplate` theo phiên bản phù hợp, `MockRestServiceServer` có thể kiểm tra request mà không ra Internet:

~~~java
MockRestServiceServer server =
        MockRestServiceServer.bindTo(partnerRestTemplate).build();

server.expect(requestTo(
            "https://partner.example/api/orders"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("X-Correlation-Id", "corr-42"))
    .andExpect(content().json("{\"orderId\":\"ORD-42\"}"))
    .andRespond(withSuccess(
            "", MediaType.APPLICATION_JSON));

// Kích hoạt outbound IntegrationFlow đã cấu hình dùng
// chính instance partnerRestTemplate và map correlation header...
server.verify();
~~~

Đây là **phần test với fixture đã cấu hình**; nếu không có flow/handler thật thì `server.verify()` không thể pass. Dùng mock HTTP server chạy qua socket nếu cần kiểm tra network timeout, connection reset hoặc lỗi TLS. Các phiên bản Spring Integration/Spring Framework mới có hỗ trợ `RestClient`; chọn HTTP client và test API theo version đang dùng.

**Kết luận hợp lệ:** mock server đã nhận request khớp body/header mong đợi. **Không được kết luận:** server production đã commit thay đổi nghiệp vụ.

### 14.2. Status và reply

Với outbound **gateway**, kiểm tra thêm output payload từ response, HTTP status metadata (nếu được map) và correlation. Với outbound **adapter one-way**, không mặc định có reply message; test đúng chủ yếu là request side effect và error behavior.

## 15. JMS: header transport, correlation và message conversion

JMS có metadata protocol khác Spring `MessageHeaders`: message ID, correlation ID, destination, reply-to, priority, delivery mode, redelivery flag... Chúng được map thông qua message converter/header mapper của integration endpoint.

Kiểm thử nên tách:

| Giai đoạn | Assertion |
|---|---|
| Spring message trước JMS outbound | Payload và business correlation đúng |
| JMS message ở test broker | Property/correlation/header được map, body đúng kiểu |
| JMS inbound sau consume | Message Spring có payload và các metadata cần thiết |
| Handler nghiệp vụ | Không lẫn reply/destination, đúng business key |
| Lỗi/redelivery | Retry/ack/transacted session đúng policy |

**Không tự suy ra** header custom `correlationId` sẽ luôn tự chuyển thành `JMSCorrelationID`. Nếu protocol cần correlation, cấu hình converter/header mapping rõ ràng và test **JMS message thực** hoặc mock ở tầng JMS message/producer.

### 15.1. Ví dụ hợp đồng

~~~text
Internal:
  payload OrderEvent(ORD-42)
  correlationId = corr-42

Expected JMS:
  destination=orders.events
  message body=JSON OrderEvent
  JMSCorrelationID=corr-42 (nếu đã cấu hình mapping)
  businessEventId=order-created-42

After consume:
  payload có cùng orderId
  correlation/businessEventId đúng contract
~~~

JMS queue và topic có semantics khác nhau; một message đã được publish chưa chứng minh consumer xử lý xong. Với ack/transaction/redelivery, cần provider test phù hợp.

## 16. AMQP/RabbitMQ: exchange, routing key và xác nhận publish

RabbitMQ có metadata về **exchange**, **routing key**, **consumer queue**, **delivery tag** và message properties. Đặt `routingKey` trong payload hoặc Spring message header không đảm bảo producer tự dùng đúng key nếu adapter không map.

Một test cần kiểm tra:

- Exchange và routing key ở outbound handler/producer.
- Payload bytes và content type/encoding.
- Correlation ID và business event ID trong properties/headers như cấu hình.
- Broker route được message tới queue có binding đúng.
- Publisher confirms/returns, consumer ack/nack, retry và DLQ ở tầng broker.
- Không dùng delivery tag/transport ID làm business key bền vững.

### 16.1. Sự khác nhau giữa mock và broker test

~~~text
Unit test:
  verify(RabbitTemplate).convertAndSend(
      "orders.events", "order.created", expectedEvent)

Integration test:
  publish record qua RabbitMQ thật
  queue đã bind nhận đúng message
  body/headers/properties đúng
  consumer xử lý hoặc reject theo contract
~~~

Cú pháp verify là **minh họa**; `RabbitTemplate` có nhiều overload và có thể dùng message converter/postprocessor, nên test phải đối chiếu method mà code thực sự gọi.

**Không lấy việc `MessageChannel.send()` trả true làm publisher confirm**. Việc ghi được vào channel không bảo đảm broker đã lưu hoặc route record.

## 17. Kafka: payload, topic, key, partition và headers

Kafka bao gồm message value, key, topic, partition, offset, timestamp và headers; Spring Integration/Spring Kafka ánh xạ metadata qua các hằng số và converter tùy endpoint/phiên bản.

| Metadata | Vai trò | Cách test |
|---|---|---|
| Value payload | Nội dung event được serialize | Schema, encoding, fields |
| Record key | Chọn partition và ordering theo key | Key đúng business identity |
| Topic | Destination của event | Không xuất sang sai topic/môi trường |
| Partition | Bảo đảm thứ tự theo partition (với điều kiện phù hợp) | Không giả định thứ tự toàn topic |
| Offset | Vị trí bản ghi đã consume | Không dùng offset làm business event ID |
| Record headers | Version/schema/correlation | Map đúng, không leak secret |
| Consumer group | Phân phối và commit vị trí đọc | Test namespace/group độc lập |
| Delivery outcome | Producer ack, consumer commit | Phân biệt với side effect business |

### 17.1. Ví dụ hợp đồng Kafka

~~~text
Spring message before outbound:
  payload = {"orderId":"ORD-42"}
  headers:
    eventId=order-created-42
    correlationId=corr-42
    kafkaTopic=orders.events
    kafkaKey=ORD-42

Kafka record:
  topic=orders.events
  key=ORD-42
  value=JSON bytes
  header eventId=order-created-42
  header correlationId=corr-42
~~~

Các tên `kafkaTopic`/`kafkaKey` là **tên minh họa**, không phải tuyên bố tên header chính thức. Khi cấu hình Spring Integration Kafka, nên sử dụng constants/mapping đúng version, ví dụ những khóa được `KafkaHeaders` định nghĩa ở module liên quan. Test outbound phải xác minh **ProducerRecord hoặc record thực**; không chỉ đọc Spring message trước adapter.

### 17.2. Ví dụ assertion với Kafka consumer test

~~~java
ConsumerRecord<String, String> record =
        receiveOneRecordFromTestKafkaTopic();

assertEquals("orders.events", record.topic());
assertEquals("ORD-42", record.key());

JsonNode body = objectMapper.readTree(record.value());
assertEquals("ORD-42", body.path("orderId").asText());

Header eventHeader = record.headers().lastHeader("eventId");
assertNotNull(eventHeader);
assertEquals(
        "order-created-42",
        new String(eventHeader.value(), StandardCharsets.UTF_8));
~~~

Đây là **phần assertion**; `receiveOneRecordFromTestKafkaTopic()` là helper của fixture tạo Kafka test topic/consumer group độc lập. `ConsumerRecord`, `Header` và `objectMapper` cần import, instance và broker test. Nếu consumer value type là byte[] hay Avro, decode theo serializer/schema đã chọn, không hardcode String.

### 17.3. Kafka test binder không phải Kafka thật

Nếu ứng dụng dùng **Spring Cloud Stream** test binder với `InputDestination`/`OutputDestination`, việc nhận message ở output in-memory chỉ chứng minh binding/flow. Để chứng minh topic, key, partition, serializer và offset broker, cần test với Kafka broker riêng. **Không nhầm** legacy `MessageCollector` của Spring Cloud Stream với tiện ích có sẵn trong Spring Integration core.

## 18. Database inbound/outbound: payload và row mapping

Database adapter có thể tạo message từ row/JDBC/JPA query, map `ResultSet` sang `Map<String,Object>`/DTO, hoặc ghi payload thành SQL parameters. Không có bộ header database mặc định thống nhất cho mọi query và mapper.

Ví dụ nguồn:

~~~text
Table orders_outbox:
  id=42
  event_id=order-created-42
  payload={"orderId":"ORD-42","amountMinor":12500}
  status=NEW

After inbound polling:
  payload OrderEvent(orderId="ORD-42", amountMinor=12500)
  headers eventId=order-created-42, sourceRecordId=42

After outbound processing:
  table order_status has orderId=ORD-42, state=SENT
~~~

### 18.1. Assertion nào cần ở đâu?

- Test `RowMapper`/converter riêng để bắt lỗi null, kiểu SQL → Java, timezone và decimal.
- Test channel sau inbound để kiểm payload/header **sau mapping**.
- Test database thật cô lập để xác minh query/filter/locking/transaction và row status.
- Test outbound handler mapping SQL parameters đúng nhưng không coi mock JDBC return 1 là row đã commit.
- Test duplicate polling và nhiều instance: không xử lý cùng business event sai ngoài chính sách.

### 18.2. Source record ID và business ID khác nhau

`id=42` có thể là primary key của một outbox row; `eventId=order-created-42` là định danh nghiệp vụ bền vững. Không nên dùng một primary key chỉ có ý nghĩa trong database A để định danh toàn cục nếu hệ thống nhận có nhiều source. Nếu nhiều nguồn có cùng event ID, contract phải quy định namespace/source ID rõ.

## 19. Kiểm tra replyChannel, errorChannel và correlation trong gateway

Gateway có thể dùng các header messaging nội bộ để quản lý request–reply:

- `MessageHeaders.REPLY_CHANNEL`: nơi nhận reply khi có dùng theo contract.
- `MessageHeaders.ERROR_CHANNEL`: nơi gửi lỗi khi flow/endpoint hỗ trợ.
- Header ứng dụng `correlationId`: cho phép liên kết yêu cầu và kết quả nghiệp vụ.
- Header transport như JMS correlation, HTTP request ID có thể được map từ/đến Spring message tùy cấu hình.

**Không sửa hoặc giả định replyChannel do framework đặt sẽ giữ nguyên xuyên mọi protocol.** Gateway có thể tạo temporary reply channel nội bộ; nếu một message outbound được serialize sang Kafka/HTTP, bạn thường chỉ truyền **business correlation**, không mang object `MessageChannel` Java sang hệ thống khác.

### 19.1. Hai request đồng thời

Ví dụ có hai đơn hàng gửi qua gateway:

~~~text
Request A: orderId=ORD-42, correlationId=corr-A
Request B: orderId=ORD-43, correlationId=corr-B

Reply B đến trước reply A:
  replyB must resolve to B, không phải A
  replyA must resolve to A, không phải B
~~~

Bài test phải dùng **identifier riêng** và kiểm kết quả trả về đúng caller. Nếu chỉ đếm “hai reply đã đến” mà không so mapping, lỗi ghép nhầm phiên có thể không bị phát hiện.

### 19.2. Khi không có reply

Kiểm gateway reply timeout, kiểu lỗi và trạng thái request khi downstream không trả lời. Đừng gọi `receive()` không timeout rồi để test treo vô hạn. Với adapter one-way, không tự viết test đòi có reply nếu thiết kế không có.

## 20. Kiểm tra error payload và failed message

Trong luồng Spring Integration, một số endpoint dùng `ErrorMessage` hoặc `MessagingException` để biểu diễn lỗi. Test cần biết **lỗi xảy ra đồng bộ hay bất đồng bộ**.

| Topology | Hành vi có thể xảy ra | Cách test |
|---|---|---|
| `DirectChannel` đồng bộ | Exception ném về caller | `assertThrows`, kiểm cause |
| Poller chạy scheduler | Lỗi được error handler xử lý | Quan sát error channel/recovery theo config |
| `ExecutorChannel` | Error flow trên thread khác | Chờ `ErrorMessage` hoặc điều kiện lỗi |
| JMS/AMQP/Kafka consumer | Reject/nack/redelivery/DLQ | Broker test/handler config |
| HTTP outbound gateway | Client exception/status code | Assert mapping và reply/error |
| Retry advice | Lỗi trước đó được retry | Assert số attempts, trạng thái sau cùng |

Ví dụ **nếu endpoint đã được cấu hình** phát `ErrorMessage` tới `PollableChannel errors`:

~~~java
Message<?> message = errors.receive(2000);
assertNotNull(message);

ErrorMessage error = assertInstanceOf(
        ErrorMessage.class, message);

Throwable cause = error.getPayload();
assertNotNull(cause);
~~~

Cần import `org.springframework.messaging.support.ErrorMessage`; `errors` là channel được khai báo trong test context. `MessagingException.getFailedMessage()` có thể giúp truy vết input khi exception type có cung cấp, nhưng không phải mọi Throwable đều mang một failed message. **Không giả định cứ có bean `errorChannel` thì tất cả exception sẽ tự xuất hiện ở đó**.

### 20.1. An toàn khi kiểm tra lỗi

Không assert bằng cách in nguyên payload chứa PII/secret vào CI log. Thay vào đó, kiểm error category, correlation, loại exception, thông tin đủ điều tra và trạng thái không có side effect ngoài ý muốn.

~~~text
Input: schema invalid
Expected:
  ErrorMessage hoặc reject branch có eventId
  không có request gửi tới shipping API
  log chỉ ghi metadata an toàn
  không retry vô hạn vì dữ liệu sai cấu trúc
~~~

## 21. Header và payload trong xử lý bất đồng bộ

Khi đi qua `ExecutorChannel`, poller, JMS/Kafka listener hoặc outbound client trả `CompletableFuture`, message output có thể đến **sau khi lời gọi gửi trả về**. Việc kiểm tra ngay:

~~~java
input.send(message);
assertNotNull(resultChannel.receive(0));
~~~

có thể flaky. Thay bằng:

~~~java
assertTrue(input.send(message));

Message<?> actual = resultChannel.receive(2000);
assertNotNull(actual, "Chưa nhận message output trong thời hạn test");
assertEquals("corr-42",
        actual.getHeaders().get("correlationId"));
~~~

Thời hạn 2 giây chỉ minh họa; lựa chọn phụ thuộc scheduler, môi trường CI, SLA và có test infrastructure hay không. Không dùng `Thread.sleep(5000)` như cơ chế duy nhất, vì nó vừa chậm vừa không chứng minh flow đã hoàn thành.

### 21.1. Kiểm nhiều message bất đồng bộ

Nếu splitter/router đưa nhiều message đi các executor khác nhau, test phải quyết định có yêu cầu thứ tự hay không.

- Với order được phép **bất kỳ thứ tự**, thu đủ N rồi so **tập business IDs**.
- Với contract bảo đảm thứ tự theo một key/partition, assert thứ tự **trong phạm vi được bảo đảm**, không suy ra toàn hệ thống.
- Với aggregator, test completion criteria trước khi kết luận output còn thiếu.
- Với fan-out pub/sub, đợi từng subscriber hoàn thành thay vì chỉ một collector đã nhận.

### 21.2. Race khi test dùng chung context

Một `QueueChannel` được dùng bởi nhiều test đồng thời có thể chứa output của test khác. Dùng unique correlation, output channel/context riêng hoặc phân vùng test rõ ràng; khi test run kết thúc phải dừng poller/listener có thể tiếp tục gửi message.

### 21.3. Header là object reference trong JVM

Một header có thể chứa object Java có thể thay đổi. Message API không tự biến mọi nested value thành bất biến; nếu hai thread đọc/sửa cùng object, kết quả test có thể khó dự đoán. Ưu tiên header dạng giá trị đơn giản/bất biến và không nhét một mutable map lớn vào header rồi hy vọng các subscriber không chỉnh sửa nó.

## 22. Nhiều output: splitter, router và aggregator

### 22.1. Một input sinh ba message

Ví dụ một batch có ba order được splitter tạo thành ba message:

~~~text
Input:
  batchId=batch-7
  orderIds=[ORD-41, ORD-42, ORD-43]

Expected outputs:
  (ORD-41, batch-7)
  (ORD-42, batch-7)
  (ORD-43, batch-7)
~~~

Test với `PollableChannel output`:

~~~java
Set<String> orderIds = new HashSet<>();

for (int i = 0; i < 3; i++) {
    Message<?> part = output.receive(2000);
    assertNotNull(part);
    assertEquals("batch-7", part.getHeaders().get("batchId"));

    OrderEvent event =
            assertInstanceOf(OrderEvent.class, part.getPayload());
    assertTrue(orderIds.add(event.orderId()),
            "Trùng orderId trong output batch");
}

assertEquals(
        Set.of("ORD-41", "ORD-42", "ORD-43"),
        orderIds);
~~~

`OrderEvent` là DTO trong test fixture, ví dụ record có accessor `orderId()`. Snippet chưa cung cấp việc tạo flow/splitter. Số lượng 3 phải được thiết kế từ contract và input test.

**Chú ý:** Headers correlation/sequence do **splitter** có thể khác các header nghiệp vụ. Kiểm các metadata `IntegrationMessageHeaderAccessor.CORRELATION_ID`/`SEQUENCE_NUMBER` hoặc hằng số tương đương **khi flow thật có sử dụng**; không mặc định tên custom `batchId` trùng với sequence header do framework tạo.

### 22.2. Router: đúng nhánh, không có rò rỉ sang nhánh khác

Giả sử:

~~~text
eventType=order.created -> ordersChannel
eventType=order.failed  -> failuresChannel
eventType khác          -> rejectedChannel
~~~

Nên có collector riêng cho từng nhánh. Test cần kiểm payload, event type và tenant đúng nhánh, đồng thời đảm bảo **không gửi dữ liệu tenant A sang consumer tenant B**. Nếu router đọc header từ nguồn không tin cậy, có thể cần xác minh nguồn trước khi route.

### 22.3. Aggregator: output chỉ khi nhóm hoàn tất

Aggregator có thể chờ đủ số message hoặc timeout. Test:

- Gửi từng part với correlation ID đúng.
- Đảm bảo chưa có aggregate trước completion rule.
- Gửi part cuối, kiểm output hợp đồng.
- Gửi duplicate/late part, kiểm chính sách.
- Kiểm nội dung aggregate, headers và group release behavior.

Đừng chỉ assert một message xuất hiện; với aggregator, điều cần kiểm là **tập dữ liệu đầu ra đúng nhóm và không thiếu/thừa**.

## 23. Header validation và bảo mật: dữ liệu ngoài không mặc nhiên đáng tin

**Header có thể bị giả mạo** nếu nó đến từ HTTP client, Kafka publisher, file metadata do đối tác cung cấp hoặc hệ thống tích hợp chưa xác thực. Một header như `tenantId=tenant-a` không đủ chứng minh người gửi có quyền truy cập dữ liệu tenant A.

Những trường cần kiểm soát:

| Header | Rủi ro | Test đề nghị |
|---|---|---|
| `tenantId` | Truy cập chéo tenant | So với principal/security context đã xác thực |
| `destinationUri` | SSRF, gửi dữ liệu tới host lạ | URI whitelist và network policy |
| `targetFileName` | Path traversal, ghi đè file | Giới hạn ký tự/path, chặn `../`/absolute path |
| `kafkaTopic` / routing key | Gửi sang sai topic/queue | Topic/exchange whitelist, scope theo tenant |
| `Authorization` | Lộ token sang transport/log khác | Redaction/drop trước outbound |
| `correlationId` | Log injection/PII/đầu vào quá dài | Validate length/charset và nguồn |
| `contentType` | Parser chọn sai loại dữ liệu | Chỉ nhận MIME được hỗ trợ, xác minh body |
| `schemaVersion` | Chạy nhầm converter hoặc hạ cấp schema | Reject version chưa hỗ trợ |

Ví dụ kiểm soát trong flow:

~~~text
HTTP request:
  X-Tenant-Id: tenant-b
  authenticated principal: tenant-a

Expected:
  reject request hoặc thực hiện mapping từ principal theo policy
  không gửi message tenant-b vào outbound topic tenant-b
  error event có correlation nhưng không log token
~~~

### 23.1. Test header allowlist

Nếu flow chỉ cho phép `correlationId` và `eventType` qua outbound, kiểm tra header nhạy cảm đã bị gỡ:

~~~java
Message<?> message = outboundProbe.receive(1000);
assertNotNull(message);

assertEquals("corr-42",
        message.getHeaders().get("correlationId"));
assertNull(message.getHeaders().get("Authorization"));
assertNull(message.getHeaders().get("rawClientCookie"));
~~~

`outboundProbe` là channel quan sát **trước adapter**. Cần thêm transport-level test nếu muốn chứng minh HTTP/JMS/Kafka output thực sự không chứa các header nhạy cảm; adapter có thể thêm header riêng từ client config.

### 23.2. Test chống path traversal

Gửi các tên như:

~~~text
orders-42.csv            -> hợp lệ
../secrets.txt           -> từ chối
/subdir/override.csv     -> từ chối nếu contract chỉ cho basename
order\nInjected-Header   -> từ chối hoặc normalize theo quy tắc
~~~

Kiểm tra từ chối **trước khi outbound client được gọi**. Với Windows và Unix, chú ý khác biệt dấu phân tách đường dẫn, absolute path và Unicode normalization nếu hợp đồng yêu cầu.

## 24. Đo contract bằng parameterized tests

Khi có nhiều giá trị payload/header không hợp lệ, JUnit 5 `@ParameterizedTest` làm rõ boundary cases hơn các method lặp lại.

Ví dụ thuần cho hàm validator của ứng dụng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class CorrelationIdValidationTest {

    private static boolean validCorrelationId(String value) {
        return value != null
                && !value.isBlank()
                && value.length() <= 64
                && value.matches("[A-Za-z0-9_-]+");
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {
        " ", "bad\nvalue", "has/slash", "with space"
    })
    void rejectsInvalidCorrelationId(String value) {
        assertFalse(validCorrelationId(value));
    }
}
~~~

Đây là **unit test validator minh họa**. Nếu ứng dụng chấp nhận UUID với dấu gạch hoặc tracing IDs với format khác, điều chỉnh rule. **Không tự đặt giới hạn 64 cho mọi hệ thống** mà không xét contract thực tế.

Trong flow test, dùng parameterized inputs để xác minh:

- Payload `null` **không thể tạo thành một Spring `Message` thông thường** trong nhiều builder path; phải kiểm tra validator/trường DTO null ở tầng phù hợp.
- Payload rỗng/trắng có bị từ chối hay không.
- `contentType` không hỗ trợ.
- `tenantId` sai type hoặc không có quyền.
- UTF-8 có ký tự tiếng Việt; emoji/multibyte.
- Size limit, batch limit và số lượng headers lớn.

### 24.1. Chọn assert theo ý nghĩa nghiệp vụ

Một số event có timestamp/ID mới mỗi lần. Test nên inject clock/ID generator hoặc assert quan hệ:

~~~text
output.eventId không rỗng
output.correlationId == input.correlationId
output.occurredAt nằm trong thời điểm đã kiểm soát
output.schemaVersion thuộc version đã hỗ trợ
~~~

Không làm test phụ thuộc vào `MessageHeaders.ID` hoặc timestamp biến động của framework nếu contract không yêu cầu.

## 25. Test payload schema evolution và tính tương thích

Các adapter thường liên kết hệ thống được phát triển độc lập. Payload/header có thể đổi khi nâng cấp version:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 2,
  "orderId": "ORD-42",
  "amount": {
    "currency": "VND",
    "minorUnits": 12500
  }
}
~~~

Cần kiểm tra:

1. Consumer đọc được version được hỗ trợ.
2. Header `schemaVersion` và field trong payload không mâu thuẫn.
3. Trường mới không làm parser cũ lỗi nếu chính sách tương thích cho phép.
4. Trường bắt buộc bị bỏ làm reject có kiểm soát.
5. Enum unknown/extra fields được xử lý theo contract.
6. Giá trị money/timezone/decimal được chuyển chính xác.
7. Khi đổi Avro/Protobuf/JSON schema, test đúng serializer và schema registry/mock tương ứng nếu có.
8. Không tự nâng/hạ version từ header không được xác minh.

### 25.1. Contract tests giữa producer và consumer

Một outbound adapter có thể gửi JSON đúng cú pháp nhưng không đúng schema consumer yêu cầu. Hãy kiểm:

- **Producer-side**: DTO → serialized payload đúng schema/version.
- **Transport-side**: content type/schema header/key được map đúng.
- **Consumer-side**: parser/handler nhận và diễn giải đúng.
- **Compatibility**: những phiên bản đã công bố vẫn được xử lý hoặc từ chối rõ.

**Đừng lấy String equality của JSON làm toàn bộ contract** khi số thứ tự field hoặc whitespace không quan trọng. Dùng JSON tree/schema validation và field assertions; kiểm byte khi encoding chính xác là một phần protocol.

## 26. Retry, duplicate và header idempotency

Một message có thể được giao **nhiều lần** do:

- Kafka/JMS/AMQP redelivery sau consumer crash.
- HTTP client timeout sau khi server đã xử lý.
- SFTP poller đọc lại file sau restart.
- JDBC polling lấy lại row vì transaction rollback.
- Application retry logic khi lỗi transient.

Header hoặc payload `eventId` cần **ổn định qua retries**, nhưng `attemptId` có thể thay đổi giữa các lần thử. Nếu tạo business ID mới mỗi lần retry, consumer khó nhận ra trùng.

### 26.1. Mẫu contract

~~~text
First attempt:
  eventId=order-created-42
  correlationId=corr-42
  attempt=1

Second attempt after timeout:
  eventId=order-created-42      (không đổi)
  correlationId=corr-42        (thường không đổi theo workflow)
  attempt=2                    (thay đổi)
~~~

Test cần chứng minh:
 
- Hai attempts có cùng business event ID.
- Consumer idempotent không tạo hai order/shipment.
- Error/retry log giữ được correlation.
- Bộ xử lý không dùng `MessageHeaders.ID` mới làm dedup key.
- Không coi một response timeout là chắc chắn server chưa xử lý.

### 26.2. Kiểm header dưới retry advice

Nếu retry advice đã được cấu hình trong flow, mock client ném lỗi lần đầu rồi thành công ở lần sau. Assert các args có cùng `eventId` và business payload, đồng thời verify số attempts **sau khi retry hoàn tất**. Mockito stub hai kết quả **không tự kích hoạt retry**; phải có policy/advice hoặc handler thực hiện retry.

### 26.3. Side effect tại đích

Chỉ thấy hai `Message<?>` trên collector không chứng minh có hai record tại đích. Ngược lại, chỉ thấy một message output không chứng minh retry không nhân đôi side effect: server có thể đã ghi hai lần trước khi trả result. Để kết luận, cần test stateful với mock server, DB hoặc broker test.

## 27. Case study: File/SFTP → OrderEvent → HTTP → Kafka

Một hệ thống nhận CSV đơn hàng từ SFTP, parse thành `OrderEvent`, gửi HTTP đến hệ thống fulfillment và phát event Kafka cho dashboard. Ta muốn kiểm tra payload/header **ở nhiều ranh giới**.

~~~mermaid
flowchart LR
    SFTP["SFTP/file inbound"] --> A["Message<File>"]
    A --> PARSER["CSV parser"]
    PARSER --> DTO["Message<OrderEvent>"]
    DTO --> ROUTER["Route tenant + validate"]
    ROUTER --> HTTP["HTTP outbound gateway"]
    HTTP --> RESULT["Message<ShipmentReceipt>"]
    RESULT --> KAFKA["Kafka outbound adapter"]
    PARSER -. "invalid" .-> REJECT["Rejected events / error channel"]
    A -. "probe" .-> P1["File contract"]
    DTO -. "probe" .-> P2["DTO + headers"]
    RESULT -. "probe" .-> P3["Response contract"]
    KAFKA --> EXT["Kafka test broker"]
~~~

### 27.1. Hợp đồng đề xuất

~~~text
Source:
  file: /incoming/orders-42.csv
  content: orderId,amountMinor,currency
           ORD-42,12500,VND

After parser:
  payload: OrderEvent("ORD-42", 12500, "VND")
  headers:
    eventId=order-created-42
    correlationId=corr-42
    sourceSystem=partner-sftp
    tenantId=tenant-a
    schemaVersion=1

HTTP request:
  POST /shipments
  X-Correlation-Id: corr-42
  body: {"orderId":"ORD-42","amountMinor":12500,"currency":"VND"}

HTTP reply:
  payload: ShipmentReceipt("sh-42","ACCEPTED")
  correlationId=corr-42

Kafka output:
  topic=shipment.events
  key=ORD-42
  eventId=order-created-42
  payload schemaVersion=1
~~~

### 27.2. Bài test theo từng lớp

| Tầng | Đầu vào | Assertion bắt buộc |
|---|---|---|
| File/SFTP source | File thử nghiệm | Tên/path/content đúng, file filter phù hợp |
| Parser unit | CSV bytes | DTO đúng số tiền, currency, error với CSV sai |
| Channel/flow | `Message<File>` hoặc DTO | Payload đúng class, giữ correlation, tenant |
| Header validation | Thiếu/sai `tenantId`, `eventId` | Reject trước khi gửi ra ngoài |
| HTTP gateway | DTO | Mock server thấy method/body/header đúng; reply được map |
| Kafka outbound | Event từ reply | Broker record đúng topic/key/headers/schema |
| Retry/idempotency | Timeout/replay | Event ID giữ ổn định, một side effect theo contract |
| Negative/poison | CSV lỗi, schema unknown | Không gửi HTTP/Kafka sai, có error/recovery |
| Lifecycle | Stop/restart poller | Không tạo duplicate ngoài chính sách |
| Security | Input có bearer token hoặc tên file độc hại | Không forward secret, không path traversal |

### 27.3. Những assertion không đủ

- `fileChannel.receive(...) != null`: mới chứng minh file message vào flow, không biết HTTP thành công.
- `httpInput.send(message) == true`: chưa chứng minh mock server nhận request.
- `kafkaOutputChannel.receive(...) != null`: chưa chứng minh Kafka broker có record.
- `eventId` bằng `MessageHeaders.ID`: không ổn định khi flow tạo message mới.
- `tenantId` tồn tại: chưa chứng minh nó tương ứng principal được phép.
- `errors.receive(0) == null`: không chứng minh error bất đồng bộ sẽ không đến sau.

### 27.4. Mẫu kết quả kiểm thử

~~~text
Scenario: order ORD-42, tenant-a

File stage: PASS
  File payload đúng, input filename khớp

Parser stage: PASS
  OrderEvent(ORD-42, 12500, VND)

Message contract: PASS
  eventId=order-created-42
  correlationId=corr-42
  tenantId=tenant-a

HTTP stage: PASS
  Mock server received POST /shipments
  body/schema/header matched
  reply shipmentId=sh-42

Kafka stage: PASS
  Test broker record topic=shipment.events, key=ORD-42
  schema/eventId matched

Overall: PASS trong phạm vi hạ tầng thử nghiệm
Production behavior: chưa được chứng minh
~~~

Chỉ dùng `PASS` khi **đã chạy kiểm thử tương ứng**. Bảng trên là **minh họa tiêu chí nghiệm thu**, không phải báo cáo một môi trường đã chạy thật.

## 28. Ma trận kiểm thử và các anti-pattern

| Anti-pattern | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ kiểm payload String | Mất header correlation/tenant/schema | Assert toàn bộ header bắt buộc |
| So sánh cả `MessageHeaders` | Flaky vì ID/timestamp thay đổi | Chỉ so contract headers |
| Header tên gì cũng tự forward | Rò secret và mở rộng trust | Allowlist/redaction |
| Đồng nhất message header với HTTP/JMS/Kafka header | Transport mapping sai | Test tại biên protocol |
| Đặt `contentType=JSON` và coi đã serialize | Payload có thể vẫn là DTO/CSV | Kiểm converter/body thực |
| So sánh `byte[]` bằng `toString()` | Không kiểm nội dung | `assertArrayEquals`/decode |
| Dùng email/message ID làm correlation duy nhất | Không bền vững hoặc có rủi ro PII | Business event ID đúng scope |
| Gửi vào `DirectChannel` rồi gắn collector thứ hai | Collector cướp message của handler | Queue terminal/wire tap/pub-sub |
| `receive()` không timeout | Test treo mãi | `receive(timeout)` |
| Assert không output ngay sau async send | Có thể message đến muộn | Completion signal/deadline |
| Test chỉ một output của splitter | Thiếu/trùng message không được thấy | Thu đủ số lượng, so tập IDs |
| Router tin `tenantId` từ caller | Dẫn đến truy cập sai tenant | Verify security context + deny |
| Mọi lỗi đều được giả định vào global errorChannel | Lỗi bị phát khác đường | Test topology/error handler thật |
| File pattern filter được coi là accept-once | Dễ xử lý lại sau poll/restart | Filter + metadata store + restart test |
| Kafka test binder được coi là broker thật | Không test offset/partition/ack | Test broker thật cô lập |
| Không dọn queue/listener | Test xanh giả từ message cũ | Context isolation/teardown |
| Dùng một ID cố định trên nhiều test song song | Cross-talk | Unique business ID/test namespace |
| Assert mock client call là side effect thành công | Không chứng minh server commit | Test tại hệ thống đích |
| Không test schema evolution | Phá tương thích với consumer cũ | Contract/schema version tests |
| Log toàn bộ message khi fail | Rò PII/token/credential | Safe metadata, redaction |

## 29. Checklist nghiệm thu và câu hỏi tự đánh giá

### 29.1. Checklist

- [ ] Đã xác định điểm đo input/output: trước adapter, sau transform, sau gateway hay tại đích.
- [ ] Hợp đồng mô tả **payload type**, schema, encoding, headers bắt buộc/tùy chọn và quyền tin cậy.
- [ ] Message test dùng dữ liệu và correlation ID cô lập.
- [ ] Kiểm kiểu payload bằng `assertInstanceOf` hoặc assertion tương đương.
- [ ] Kiểm content bằng so sánh chính xác, JSON tree/schema hoặc byte arrays đúng cách.
- [ ] Kiểm correlation/business event ID, không dựa `MessageHeaders.ID` như khóa nghiệp vụ.
- [ ] Kiểm content type và converter khớp body thật.
- [ ] Không so sánh toàn bộ framework headers trừ khi thực sự là contract.
- [ ] Header nhạy cảm được loại bỏ/giới hạn qua outbound.
- [ ] Router/filter/transformer có test header thiếu, sai kiểu và chưa được xác minh.
- [ ] Các nhánh splitter/router/aggregator được kiểm số lượng/tập output.
- [ ] Với luồng async có timeout hữu hạn và điều kiện completion.
- [ ] Với HTTP/JMS/AMQP/Kafka đã test mapping sang transport metadata.
- [ ] Với file/SFTP đã test metadata nguồn và nội dung/đường dẫn thực tế.
- [ ] Với DB đã test row mapper, datatype và transaction/side effect khi quan trọng.
- [ ] Có đường lỗi với correlation, không log secret.
- [ ] Có test duplicate/retry/idempotency nếu transport có thể gửi lại.
- [ ] Có setup/teardown, không giữ message từ test trước.
- [ ] Đã phân biệt **đã nhận message** với **đã xử lý thành công ở đích**.

### 29.2. Tình huống A

**Câu hỏi:** Message output có payload đúng nhưng thiếu `correlationId`. Có thể đánh dấu flow test thành công vì business field đủ chưa?

**Trả lời:** Không nếu correlation là phần bắt buộc của contract. Thiếu correlation làm hỏng trace/reply/retry mapping. Cần tìm endpoint làm mất header và thêm assertion xuyên flow.

### 29.3. Tình huống B

**Câu hỏi:** HTTP inbound nhận `X-Tenant-Id=tenant-b`, trong khi JWT được xác minh cho tenant-a. Test chỉ kiểm header này đã được map thành `tenantId=tenant-b`. Có đủ an toàn?

**Trả lời:** Không. Cần ràng buộc tenant với principal/authorization policy, reject hoặc dùng mapping được phép; **tồn tại header không chứng minh tính hợp lệ**.

### 29.4. Tình huống C

**Câu hỏi:** Kafka outbound message có custom header `kafkaKey=ORD-42` nhưng record trên broker có key null. Vì sao?

**Trả lời:** Một tên header custom không tự trở thành Kafka record key. Cần cấu hình mapper đúng, dùng hằng số/module version phù hợp và test record tại broker.

### 29.5. Tình huống D

**Câu hỏi:** Test File inbound phát `Message<File>`, nhưng handler sau lại cast payload thành `String`. Cần sửa thế nào?

**Trả lời:** Thêm transformer đọc nội dung/parse hoặc thay contract handler phù hợp. Test rõ payload type ở **cả trước và sau** transformer.

### 29.6. Tình huống E

**Câu hỏi:** `assertEquals(input.getHeaders(), output.getHeaders())` fail vì message ID khác. Có chắc transformer làm sai?

**Trả lời:** Không. Framework có thể tạo message mới và ID/timestamp mới. Test nên kiểm những business headers bắt buộc; chỉ kiểm ID framework khi thực sự cần theo semantics đó.

### 29.7. Tình huống F

**Câu hỏi:** `contentType=application/json`, payload là text CSV. Bài test chỉ assert content type thì có kết luận body đúng không?

**Trả lời:** Không. Phải kiểm body, converter, charset/schema. Header khai báo không tự chuyển nội dung.

### 29.8. Tình huống G

**Câu hỏi:** Hai retries có `MessageHeaders.ID` khác nhau nhưng cùng `eventId`. Có phải hai event nghiệp vụ?

**Trả lời:** Không nhất thiết. Framework message ID có thể đổi giữa các attempts; business event ID cần ổn định để idempotent consumer nhận biết một sự kiện được phát lại.

### 29.9. Tình huống H

**Câu hỏi:** Outbound HTTP mock client nhận request đúng, nhưng service thật xử lý dữ liệu sai. Test hiện tại chứng minh điều gì?

**Trả lời:** Nó chỉ chứng minh request mapping/call ở mức mock. Cần contract/integration test với server tương thích và assert side effect; không khẳng định production đã xử lý đúng.

### 29.10. Tình huống I

**Câu hỏi:** Một splitter tạo ba message, test nhận hai rồi timeout. Chỉ so payload của hai message nhận được có đủ không?

**Trả lời:** Không. Cần assert **đúng số lượng** ba, tập IDs, correlation và trạng thái phần bị thiếu; lỗi có thể do filter, routing, concurrency hoặc exception.

### 29.11. Tình huống J

**Câu hỏi:** Một message có header `Authorization`, sau đó được chuyển sang Kafka và log nguyên header này. Nên sửa ở đâu?

**Trả lời:** Thiết lập allowlist/sanitization ở biên phù hợp, không truyền raw token qua messaging downstream; thêm test kiểm transport record và audit log không chứa credential.

## 30. Hướng dẫn thực hành và phạm vi kiểm thử

### 30.1. Bài thực hành đề xuất

Tự xây một flow nhỏ:

~~~text
File inbound (CSV order)
  -> fileInput
  -> CSV-to-OrderEvent transformer
  -> validate tenant + schemaVersion
  -> route by eventType
  -> outbound HTTP gateway
  -> resultChannel
  -> Kafka outbound
~~~

Yêu cầu:

1. Tạo `@TempDir` và CSV fixture với một order hợp lệ, một order thiếu field, một file sai pattern.
2. Dùng một `QueueChannel` làm test output sau transform, assert payload type, order ID, amount và correlation/tenant.
3. Thêm lỗi header `tenantId` thiếu/sai và chứng minh HTTP outbound không được gọi.
4. Cấu hình mock HTTP server và kiểm request body/header thực.
5. Test reply gateway và correlation.
6. Với Kafka test broker, kiểm topic/key/headers/schema.
7. Mô phỏng timeout và retry, giữ `eventId` ổn định.
8. Dừng poller, dọn file/queue/topic/group giữa các test.
9. Chạy test song song có namespace/correlation riêng hoặc giữ isolation rõ.
10. Ghi báo cáo **đã chứng minh gì** và **chưa chứng minh gì** cho mỗi tầng.

### 30.2. Tài liệu tham khảo

Để đối chiếu API và các header constants theo phiên bản dự án:

- **Spring Integration Reference — Message:** https://docs.spring.io/spring-integration/reference/message.html
- **Spring Integration Reference — Testing:** https://docs.spring.io/spring-integration/reference/testing.html
- **Spring Integration Reference — File Support:** https://docs.spring.io/spring-integration/reference/file.html
- **Spring Integration Reference — HTTP:** https://docs.spring.io/spring-integration/reference/http.html
- **Spring Framework Reference — Messaging:** https://docs.spring.io/spring-framework/reference/integration.html

Các đường dẫn là nguồn tham khảo API nói chung; đường dẫn tài liệu hoặc tên hàm có thể thay đổi theo version. Những ví dụ chỉ đưa **snippet minh họa có fixture** đã được chú thích; STEP 4 là bước viết bài, không phải chứng nhận đã chạy build hoặc kiểm thử dự án thực tế.

## Kết luận

**Kiểm tra header và payload** là phần cốt lõi của kiểm thử luồng **Spring Integration Adapters** vì payload quyết định *dữ liệu nghiệp vụ*, còn headers quyết định *ngữ cảnh, định tuyến, chuyển đổi, correlation và ranh giới tin cậy*. Một chiến lược tốt kiểm kiểu/nội dung payload tại đúng channel, kiểm những header **thật sự thuộc contract**, xác minh mapping khi đi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, đồng thời thử đường lỗi, bất đồng bộ, duplicate và schema evolution. Cần đặc biệt tránh nhầm **header nội bộ** với **metadata transport** và nhầm **message đến channel** với **side effect đã hoàn tất**. Khi mọi assertion đều gắn với một kết quả có thể quan sát và có setup/teardown rõ ràng, bộ test giúp phát hiện sớm sai lệch dữ liệu, thất lạc correlation, phân quyền sai hoặc lỗi tích hợp khó tái hiện ở production.
