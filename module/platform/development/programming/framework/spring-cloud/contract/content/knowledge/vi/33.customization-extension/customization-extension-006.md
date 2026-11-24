# Adapter messaging cho công nghệ không có hỗ trợ sẵn

**Spring Cloud Contract** không chỉ giúp xác minh HTTP API. Một producer có thể công bố sự kiện `OrderCreated`, một consumer nhận lệnh `ReserveInventory`, hoặc hai dịch vụ giao tiếp qua một nền tảng messaging nội bộ. Hợp đồng cần mô tả **destination, payload, headers và hành vi có thể quan sát**, sau đó tạo **producer verification tests**, phát hành artifact `stubs`, cho **Stub Runner** kích hoạt sự kiện trong consumer tests và đưa kiểm thử vào CI/CD.

Vấn đề xuất hiện khi nhóm dùng **broker độc quyền, SDK nội bộ, một message gateway tự phát triển hoặc protocol chưa có integration được Spring Cloud Contract hỗ trợ sẵn**. Nếu generated test không thể gửi hoặc nhận message qua công nghệ đó, một hợp đồng Groovy/YAML hợp lệ vẫn có thể không kiểm được producer. Cách giải quyết là xây dựng một **messaging adapter ở ranh giới kiểm thử**, chuyển giao tiếp test của Spring Cloud Contract thành lệnh gửi/nhận của transport hiện có, đồng thời giữ rõ giới hạn giữa **mock/fake transport** và **broker thật**.

Bài thuộc chương **Tùy biến và mở rộng** của mô-đun **SPRING_CLOUD_CONTRACT**. Trọng tâm là thiết kế, hiện thực và kiểm một adapter cho công nghệ messaging chưa được hỗ trợ trực tiếp; qua đó tiếp tục thực hành Groovy/YAML DSL, generated producer tests, stub packaging, Stub Runner và CI để phát hiện thay đổi không tương thích giữa producer và consumer.

Các đoạn Java trong bài minh họa **kiến trúc tích hợp trên Spring Cloud Contract 4.x**. Chữ ký SPI và API cấu hình có thể khác theo dòng thư viện, vì vậy cần kiểm dependency và generated test thực tế khi đưa vào project. Các lớp `TestBusPort`, `BusEnvelope` và tên broker `AsterBus` là **ví dụ giả định**, không phải API có sẵn của Spring Cloud Contract.

## 1. Khi nào thực sự cần adapter tùy biến?

Spring Cloud Contract có tích hợp messaging cho những stack Spring phổ biến như **Spring Cloud Stream, Spring Integration, Spring JMS và Apache Camel**. Với công nghệ không nằm trong những integration được cung cấp, cần có một cầu nối giữa verifier và transport.

| Tình huống | Lựa chọn nên cân nhắc | Vì sao |
| --- | --- | --- |
| Ứng dụng dùng Spring Cloud Stream với binder đã được hỗ trợ | Dùng integration/test binder sẵn có | Ít code bảo trì; đủ cho nhiều producer/consumer contract tests. |
| Dùng Spring JMS trên broker được tích hợp đúng | Dùng integration Spring JMS | Không phải tái hiện send/receive từ đầu. |
| Dùng Apache Camel route đã có adapter | Tận dụng Camel integration | Giữ contract ở mức message/destination. |
| Dùng **SDK broker độc quyền** không được tích hợp | Viết `MessageVerifierSender`/`MessageVerifierReceiver` adapter | Cần biến lời gọi verifier thành send/receive của SDK. |
| Dùng Kafka/RabbitMQ nhưng chỉ muốn test payload nhanh | Dùng test binder/fake nếu phù hợp, **thêm broker integration test** | Tránh tạo adapter riêng khi framework hiện tại đã giải quyết phần lớn bài toán. |
| Muốn kiểm binary wire protocol, schema registry, broker delivery guarantee | Adapter + integration tests với transport thật | Contract verifier ở mức message có thể chưa bao phủ toàn bộ bytes/metadata trên dây. |

**Không nên viết adapter chỉ vì có thể.** Adapter là phần code phải bảo trì khi nâng Spring Cloud Contract, thay SDK broker hoặc đổi quy ước headers. Trước tiên xác nhận ứng dụng có thể tận dụng integration hiện có, hoặc dùng Spring Cloud Stream binder làm lớp bao ngoài transport mà không làm thay đổi semantics quan trọng.

## 2. Kiến trúc: adapter nằm ở đâu?

~~~mermaid
flowchart TD
    A["Groovy/YAML messaging contract"] --> B["Spring Cloud Contract Plugin"]
    B --> C["Generated producer verification tests"]
    B --> D["JAR artifact classifier stubs"]
    C --> E["ContractVerifierMessaging / message exchange"]
    E --> F["MessageVerifierSender / Receiver adapter"]
    F --> G["TestBusPort: ánh xạ destination, payload, headers"]
    G --> H["Broker test environment hoặc fake transport"]
    H --> I["Producer publisher / consumer listener thật"]
    D --> J["Stub Runner"]
    J --> K["StubTrigger theo label"]
    K --> F
~~~

**Đường đi ở producer:**

1. Contract định nghĩa message mà producer phải tạo hoặc tiêu thụ.
2. Plugin sinh test; generated test kích hoạt producer và chờ message qua **verifier receiver**, hoặc gửi input qua **verifier sender**.
3. Adapter chuyển lời gọi này thành hành động với broker/test port.
4. Test assert destination, payload và headers theo DSL.

**Đường đi ở consumer:**

1. Stub Runner tải artifact `stubs` cùng một hợp đồng đã được producer kiểm.
2. Consumer test gọi `StubTrigger.trigger(label)` hoặc API tương ứng để phát message mẫu.
3. **MessageVerifierSender adapter** đưa message vào transport mà listener thật của consumer đang đọc.
4. Consumer test assert kết quả nghiệp vụ sau khi listener xử lý.

**Lưu ý:** một adapter có thể phục vụ cả producer tests và consumer tests, nhưng hai phía thường có **Spring context, test port và broker credentials khác nhau**. Không chia sẻ singleton mutable state giữa các CI jobs rồi coi hai luồng kiểm là độc lập.

## 3. Những SPI cần biết

Tài liệu Spring Cloud Contract mô tả hai giao diện:

- `org.springframework.cloud.contract.verifier.messaging.MessageVerifierSender<M>`: gửi message tới một **destination logic**.
- `org.springframework.cloud.contract.verifier.messaging.MessageVerifierReceiver<M>`: nhận message ở một destination, thường có thể giới hạn **timeout**.

Một kiểu hợp nhất `MessageVerifier<M>` có thể mở rộng cả sender và receiver ở những dòng thư viện hỗ trợ. Các phương thức cụ thể và tham số contract metadata phụ thuộc version.

Ở nhiều dòng Spring Cloud Contract 3.x/4.x, adapter có thể phải hiện thực các overload liên quan đến `YamlContract`, chẳng hạn:

~~~java
// Chữ ký minh họa để xác định trách nhiệm SPI.
void send(Message<?> message, String destination, YamlContract contract);

<T> void send(
    T payload,
    Map<String, Object> headers,
    String destination,
    YamlContract contract
);

Message<?> receive(
    String destination,
    long timeout,
    TimeUnit unit,
    YamlContract contract
);

Message<?> receive(String destination, YamlContract contract);
~~~

`YamlContract` là đối tượng contract nội bộ dùng bởi một số phiên bản SPI; **không yêu cầu người viết Groovy DSL phải chuyển toàn bộ hợp đồng sang YAML thủ công**. Các overload ít tham số có thể là default methods gọi phiên bản nhận contract. Khi tạo adapter thật, hãy mở **interface từ dependency đã resolve** để khớp chính xác kiểu generics, package và annotations.

| SPI | Trách nhiệm | Điều phải bảo đảm |
| --- | --- | --- |
| Sender | Gửi payload/message qua transport. | Đúng destination, content type, serialization, required headers. |
| Receiver | Chờ và trả message được producer phát. | Đúng destination, timeout hữu hạn, không lấy nhầm message cũ. |
| Message conversion | Chuyển `byte[]`/JSON/record sang object mà verifier có thể assert. | Không làm mất null/type/headers, không sửa payload sai nghĩa. |
| Destination resolution | Ánh xạ tên logic trong DSL tới queue/topic thực. | Cấu hình tập trung, có validate, không ném message sang môi trường thật. |
| Lifecycle | Kết nối/đăng ký listener và đóng resources. | Cô lập test, clear offsets/queues, đóng client và thread. |

**Điểm cốt lõi:** Spring Cloud Contract mô tả **hành vi message**, không tự biết SDK độc quyền gọi phương thức `publishAsync(...)` hay `pollPartition(...)`. Adapter là nơi dịch những thao tác đó.

## 4. Chọn một kịch bản xuyên suốt: AsterBus

Giả sử tổ chức dùng **AsterBus** — một broker **giả định** có SDK nội bộ. Order Service gọi `AsterBusClient.publish(destination, bytes, headers)`; Billing Service đăng ký listener. Hợp đồng mong đợi:

~~~text
Producer: order-service
Logical destination: orders.created
Event type: OrderCreated
Schema version: 1
Content type: application/json
Payload:
  eventId: evt-00042
  orderId: ORD-42
  amountMinor: 125000
  currency: VND
~~~

Một message envelope ở mức transport:

~~~text
Destination: tenant-test.orders.created
Headers:
  eventType: OrderCreated
  schemaVersion: 1
  contentType: application/json
  correlationId: test-run-123
Payload bytes (UTF-8 JSON):
  {"eventId":"evt-00042","orderId":"ORD-42",
   "amountMinor":125000,"currency":"VND"}
~~~

**`orders.created` trong contract là tên logic**, còn `tenant-test.orders.created` là tên vật lý minh họa sau ánh xạ test namespace. Adapter không được thay đổi `orderId`, `amountMinor` hoặc `currency`; nếu thay, generated test có thể kiểm dữ liệu do adapter tạo ra thay vì dữ liệu producer phát.

## 5. Định nghĩa message contract bằng Groovy DSL

Đặt ở producer, ví dụ `src/test/resources/contracts/messaging/order_created_v1.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldPublishOrderCreatedV1'
    description 'Order Service phát OrderCreated v1 qua AsterBus'
    label 'orderCreatedV1'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Giải thích:

1. `input.triggeredBy(...)` yêu cầu generated test **gọi một phương thức trong base test**, từ đó kích hoạt **mã producer thật**.
2. `outputMessage.sentTo(...)` chỉ định destination logic mà test phải quan sát.
3. `headers` chứa metadata **có ý nghĩa liên dịch vụ**; adapter phải map chúng đúng loại/giá trị.
4. `body` chứa payload mẫu; generated test kiểm những phần hợp đồng yêu cầu.
5. `label` cho phép **consumer test** kích hoạt message mẫu bằng Stub Runner nếu stub messaging đã được thiết lập.

**Đừng cho `publishOrderCreated()` trong base test trực tiếp dựng một message giả rồi đưa vào adapter receiver.** Như vậy generated test có thể PASS dù publisher production hỏng. Phương thức trigger phải đi qua **đường code mà producer thực sự sử dụng** để phát message, ít nhất ở mức application publisher đang được kiểm.

### 5.1. Biến thể YAML DSL

Nếu nhóm chọn YAML, một hợp đồng tương đương:

~~~yaml
name: shouldPublishOrderCreatedV1
description: Order Service phát OrderCreated v1 qua AsterBus
label: orderCreatedV1
input:
  triggeredBy: publishOrderCreated()
outputMessage:
  sentTo: orders.created
  headers:
    contentType: application/json
    eventType: OrderCreated
    schemaVersion: 1
  body:
    eventId: evt-00042
    orderId: ORD-42
    amountMinor: 125000
    currency: VND
~~~

Đây là **lựa chọn thay thế**, không phải hợp đồng thứ hai phải được nạp trùng cùng Groovy file. Cú pháp YAML có thể cần điều chỉnh theo version/plugin DSL đã dùng; sau khi sinh test hãy kiểm **source test và artifact stubs** đúng như mong đợi.

## 6. Hợp đồng inbound: khi producer là dịch vụ tiêu thụ message

Không phải hợp đồng messaging nào cũng xuất phát từ `triggeredBy(...)`. Nếu Order Service **nhận** một lệnh `ReserveInventory` từ bên khác, một contract có thể mô tả **input message**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldHandleReserveInventory'
    description 'Listener xử lý lệnh đặt giữ hàng hợp lệ'

    input {
        messageFrom('inventory.reserve')
        messageHeaders {
            header('contentType', 'application/json')
            header('eventType', 'ReserveInventory')
        }
        messageBody(
            requestId: 'req-42',
            sku: 'SKU-42',
            quantity: 2
        )
        assertThat('inventoryWasReserved()')
    }
}
~~~

**Khác biệt quan trọng:**

- Với **outbound**: gọi `triggeredBy(...)` để producer phát, rồi **receiver adapter** quan sát message.
- Với **inbound**: generated test dùng **sender adapter** đưa lệnh tới `messageFrom(...)`, rồi kiểm **side effect** bằng `assertThat(...)`/base test theo DSL và plugin version.

Không được biến `inventoryWasReserved()` thành phương thức luôn trả `true`. Nó phải kiểm **dữ liệu nghiệp vụ đã thay đổi bởi consumer listener thật**. Khi test handler bất đồng bộ, cần chờ một điều kiện có timeout hữu hạn rồi mới kết luận.

Nếu handler sinh response message sau khi nhận lệnh, contract có thể mô tả cả input và output; khi đó adapter phải bảo vệ **hai hướng giao tiếp** và đảm bảo receive không lấy nhầm message của lần thử trước.

## 7. Tách adapter khỏi SDK bằng `TestBusPort`

Để nội dung tích hợp không phụ thuộc API độc quyền, bắt đầu bằng một port do nhóm kiểm thử sở hữu:

~~~java
package com.acme.contracttest.bus;

import java.time.Duration;
import java.util.Map;

public interface TestBusPort {
    void publish(String destination, BusEnvelope envelope);

    // Trả null khi không có message trong thời hạn đã cho.
    BusEnvelope receive(String destination, Duration timeout);

    record BusEnvelope(
        byte[] payload,
        Map<String, Object> headers
    ) {}
}
~~~

**`TestBusPort` không phải SPI của Spring Cloud Contract**. Nó là lớp trung gian của dự án để adapter không cần biết chi tiết retry, partition, session hoặc acknowledgement của AsterBus SDK.

Thiết kế này có ba ưu điểm:

1. **Adapter chỉ phụ thuộc một port hẹp**, có thể dùng trong unit test mà không khởi động broker.
2. Nhóm có thể thay implementation `InMemoryTestBusPort` bằng `AsterBusSdkTestPort` mà không đổi Groovy/YAML contract.
3. Có thể viết **conformance tests cho port**: gửi–nhận, headers, payload bytes, timeout, destination isolation.

**Ranh giới quan trọng:** nếu cả producer publisher và adapter dùng chung một **fake port** tự viết, test chứng minh integration ở mức fake, **không chứng minh AsterBus SDK thật serialize, route và acknowledge đúng**. Phải có ít nhất một lớp kiểm tra transport thật hoặc test environment tương đương đủ đại diện.

## 8. Một fake in-memory port để học và thử adapter

Ví dụ không phụ thuộc broker, dùng queue riêng cho từng destination:

~~~java
package com.acme.contracttest.bus;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class InMemoryTestBusPort implements TestBusPort {

    private final ConcurrentHashMap<String,
            BlockingQueue<BusEnvelope>> queues =
            new ConcurrentHashMap<>();

    private BlockingQueue<BusEnvelope> queue(String destination) {
        return queues.computeIfAbsent(
            destination, key -> new LinkedBlockingQueue<>()
        );
    }

    @Override
    public void publish(String destination, BusEnvelope envelope) {
        queue(destination).add(envelope);
    }

    @Override
    public BusEnvelope receive(String destination, Duration timeout) {
        try {
            return queue(destination).poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS
            );
        }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted while awaiting " + destination,
                interrupted
            );
        }
    }
}
~~~

**Đây là một fake minh họa**, không phải broker simulator đầy đủ. Nó không mô phỏng delivery semantics, acknowledgements, retention, partition assignment hoặc security. Trong ứng dụng thật cần thận trọng với payload/headers mutable: nên copy dữ liệu khi publish/receive nếu test có concurrency để tránh sửa bytes/Map sau khi xếp hàng.

Fake nên được **tạo mới mỗi test context hoặc reset có kiểm soát**. Nếu `queues` sống qua nhiều tests, generated test có thể nhận message cũ và PASS giả. Không dùng fake này trong production hoặc diễn giải test xanh của nó như chứng nhận chất lượng broker.

## 9. Adapter bridge: implement Sender và Receiver

Khi dùng Spring Cloud Contract 3.x/4.x có SPI với `YamlContract`, một bridge minh họa có thể khai báo:

~~~java
package com.acme.contracttest.bus;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.cloud.contract.verifier.converter.YamlContract;
import org.springframework.cloud.contract.verifier.messaging.MessageVerifierReceiver;
import org.springframework.cloud.contract.verifier.messaging.MessageVerifierSender;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class AsterBusMessageVerifier
        implements MessageVerifierSender<Message<?>>,
                   MessageVerifierReceiver<Message<?>> {

    private final TestBusPort bus;
    private final ObjectMapper mapper;

    public AsterBusMessageVerifier(
            TestBusPort bus, ObjectMapper mapper) {
        this.bus = bus;
        this.mapper = mapper;
    }

    @Override
    public void send(
            Message<?> message,
            String destination,
            YamlContract contract) {
        bus.publish(destination, new TestBusPort.BusEnvelope(
            toBytes(message.getPayload()),
            Map.copyOf(message.getHeaders())
        ));
    }

    @Override
    public <T> void send(
            T payload,
            Map<String, Object> headers,
            String destination,
            YamlContract contract) {
        bus.publish(destination, new TestBusPort.BusEnvelope(
            toBytes(payload),
            Map.copyOf(headers)
        ));
    }

    @Override
    public Message<?> receive(
            String destination,
            long timeout,
            TimeUnit unit,
            YamlContract contract) {
        TestBusPort.BusEnvelope envelope = bus.receive(
            destination, Duration.ofMillis(
                unit.toMillis(timeout)
            )
        );
        if (envelope == null) {
            return null;
        }
        return MessageBuilder.withPayload(
                new String(envelope.payload(), StandardCharsets.UTF_8))
            .copyHeaders(envelope.headers())
            .build();
    }

    @Override
    public Message<?> receive(
            String destination, YamlContract contract) {
        return receive(
            destination, 5, TimeUnit.SECONDS, contract
        );
    }

    private byte[] toBytes(Object value) {
        if (value instanceof byte[] bytes) {
            return bytes;
        }
        if (value instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        try {
            return mapper.writeValueAsBytes(value);
        }
        catch (Exception ex) {
            throw new IllegalArgumentException(
                "Cannot encode test message payload", ex
            );
        }
    }
}
~~~

**Đây là khung ví dụ, cần kiểm compile với chính SPI mà dự án đã resolve**. Một số overload/default methods hoặc generic return type có thể khác theo phiên bản; không chép nguyên code mà bỏ qua API/Javadoc dependency. Trong bản chạy thực còn phải bổ sung validation destination, timeouts, content type và xử lý lỗi SDK.

### 9.1. Những quyết định đang ẩn trong ví dụ

- `toBytes(...)` dùng **UTF-8 JSON** cho object, nhưng không phải broker nào cũng dùng JSON. Nếu contract là Avro, Protobuf hoặc binary, phải dùng **codec thực**.
- `receive(...)` trả body dạng **String UTF-8**, phù hợp nhiều kịch bản JSON text. Với binary payload hoặc verifier expectation khác, phải trả `byte[]`/object tương ứng.
- `Map.copyOf(...)` không chấp nhận null key/value. Nếu SDK cho phép null headers, cần có **header normalization policy** thay vì copy một cách máy móc.
- Một số `Spring MessageHeaders` chứa metadata nội bộ (`id`, `timestamp`) không nên được đẩy sang broker. Adapter production-grade cần **allowlist/map headers**.
- `receive(...)` trả `null` khi hết timeout; không được tạo một message “rỗng” giả rồi khiến generated test hiểu là đã nhận.

Một adapter đủ tốt phải giữ **ý nghĩa hợp đồng**, không chỉ “làm sao để generated test xanh”.

## 10. Chuyển đổi headers và payload không được làm mất ý nghĩa

Message trong Spring có thể có payload và headers khác với envelope của broker độc quyền:

~~~text
Spring Message
  payload: Object | String | byte[]
  headers: MessageHeaders (id, timestamp, contentType, custom metadata)

Adapter
  validate destination
  encode payload với charset/codec được thỏa thuận
  map header types + allowlist
  chuyển logical destination -> physical routing key

AsterBus Envelope
  payload: byte[]
  headers: Map<String, native field>
  destination: tenant-test.orders.created
~~~

| Trường | Rủi ro adapter làm sai | Quy tắc kiểm |
| --- | --- | --- |
| `contentType` | `MediaType` bị chuyển thành chuỗi sai hoặc bị mất. | Kiểm giá trị thực trên envelope và khi receive. |
| `schemaVersion` | Integer `1` bị thành string `"1"` trái contract. | Giữ kiểu có ý nghĩa hoặc chuẩn hóa có tài liệu. |
| `eventType` | Header name bị đổi chữ hoa/thường hoặc bị bỏ. | Có policy rõ; consumer test đọc đúng key. |
| `correlationId` | SDK tự sinh/ghi đè không thông báo. | Phân biệt header do ứng dụng cam kết và metadata transport. |
| JSON number | `125000` bị encode thành string. | Kiểm type qua JSON parser và wire test. |
| Timestamp | Offset/timezone bị đổi khi serialize. | Dùng định dạng chuẩn và matcher đúng phạm vi. |
| `null` vs missing | Converter bỏ field null ngoài ý muốn. | Kiểm theo chính sách schema/consumer compatibility. |
| Binary payload | Convert qua UTF-8 string làm hỏng bytes. | Dùng `byte[]` và codec/schema phù hợp. |

**Không nên copy tất cả Spring-internal headers ra broker thật**. Những header như message `id`, `timestamp` hoặc converter-specific metadata có thể không có ý nghĩa đối với giao thức ngoài. Ngược lại, không được âm thầm bỏ header contract như `eventType` chỉ để adapter dễ chạy.

### 10.1. Policy ánh xạ destination

Một lớp mapping riêng có thể tách tên hợp đồng khỏi tên transport vật lý:

~~~java
public final class TestDestinationResolver {
    private final String prefix;

    public TestDestinationResolver(String testNamespace) {
        if (testNamespace.isBlank()) {
            throw new IllegalArgumentException(
                "testNamespace must not be blank");
        }
        this.prefix = testNamespace + ".";
    }

    public String physical(String logical) {
        return switch (logical) {
            case "orders.created" -> prefix + "orders.created";
            case "inventory.reserve" -> prefix + "inventory.reserve";
            default -> throw new IllegalArgumentException(
                "Unknown contract destination: " + logical);
        };
    }
}
~~~

Khi dùng resolver, **sender và receiver phải áp dụng cùng mapping**; producer publisher test và consumer listener cũng phải kết nối namespace đúng. Nên **fail fast** khi destination không được khai báo, không mặc định gửi vào topic production.

## 11. Kết nối với AsterBus SDK thật: một adapter transport khác

Vì **AsterBus là giả định**, đoạn dưới minh họa luồng trách nhiệm bằng **pseudocode**, không phải thư viện có thể import:

~~~java
// PSEUDOCODE — thay bằng API AsterBus SDK thật của dự án.
public final class AsterBusSdkTestPort implements TestBusPort {

    private final AsterBusClient client; // API giả định
    private final TestDestinationResolver resolver;

    @Override
    public void publish(String destination, BusEnvelope message) {
        String topic = resolver.physical(destination);
        client.publishAndAwaitAck(
            topic, message.payload(), message.headers()
        );
    }

    @Override
    public BusEnvelope receive(
            String destination, Duration timeout) {
        String topic = resolver.physical(destination);
        AsterBusRecord record = client.pollOne(topic, timeout);
        return record == null ? null : new BusEnvelope(
            record.payloadBytes(), record.headers()
        );
    }
}
~~~

Phải thiết kế lại tùy broker thật:

1. **Gửi đồng bộ/async:** `publishAndAwaitAck` minh họa ý tưởng đợi gửi thành công. Nếu SDK chỉ trả future, cần chờ có timeout, không bỏ qua lỗi background.
2. **Receive semantics:** Queue consumption có thể remove/ack message; topic subscription thường dùng consumer group/offset. Không gộp hai semantics bằng cách poll tùy tiện.
3. **Cleanup:** Test client/subscription/consumer group phải đóng và tách biệt; message cũ từ test trước không được lọt vào.
4. **Retry:** Adapter không tự retry vô hạn khiến generated test đợi mãi; cần policy và failure rõ.
5. **Ordering:** Nếu hợp đồng cam kết thứ tự, cần kiểm partition/key/sequence; nếu không, không ép thứ tự ngẫu nhiên.
6. **Environment:** Không cho CI test gửi vào queue/topic production; credentials test phải có namespace và quyền giới hạn.

**Adapter này kiểm transport thật tốt hơn fake**, nhưng vẫn cần phân biệt một test gửi–nhận bằng cùng SDK với một test xác nhận **application listener/publisher thật** đã đi qua SDK. Test adapter riêng không tự thay thế contract test ở service.

## 12. Đăng ký adapter trong Spring Test context

Giả sử chọn test profile `contract`, một cấu hình minh họa:

~~~java
package com.acme.orders;

import com.acme.contracttest.bus.AsterBusMessageVerifier;
import com.acme.contracttest.bus.InMemoryTestBusPort;
import com.acme.contracttest.bus.TestBusPort;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
public class ContractBusTestConfiguration {

    @Bean
    TestBusPort testBusPort() {
        return new InMemoryTestBusPort();
    }

    @Bean
    AsterBusMessageVerifier asterBusMessageVerifier(
            TestBusPort testBusPort, ObjectMapper objectMapper) {
        return new AsterBusMessageVerifier(
            testBusPort, objectMapper);
    }
}
~~~

Nếu muốn kiểm **broker thật**, chỉ cần thay `TestBusPort` bean bằng port dùng SDK test environment, nhưng các business components của producer cũng phải được cấu hình **phát vào cùng broker/namespace**. Nếu ứng dụng production publisher đã bị thay bằng một fake chỉ để test xanh, kết quả có thể không chứng minh hành vi như mong đợi.

### 12.1. Tránh xung đột với auto-configuration sẵn có

Khi classpath có Spring Cloud Stream/JMS/Camel/Integration, Spring Cloud Contract có thể tự đăng ký messaging integration. Nếu thêm custom sender/receiver song song:

- Có thể xuất hiện nhiều bean cùng kiểu và **ambiguous injection**.
- Generated tests có thể sử dụng **adapter mặc định**, không phải adapter custom.
- Consumer Stub Runner có thể gửi tới in-memory channel khác broker mà listener thật đang đọc.

Trong test context, hãy **kiểm bean thực sự được inject** và điều kiện auto-configuration theo version. Có thể dùng `@Primary` hoặc exclude auto-config phù hợp nếu framework hỗ trợ, nhưng phải giải quyết rõ **chỉ một transport adapter có hiệu lực cho từng test scope**; không tùy tiện ẩn lỗi bằng bean overriding toàn cục.

## 13. Base test producer: kích hoạt mã publisher thật

Contract `triggeredBy('publishOrderCreated()')` cần một phương thức được generated test gọi:

~~~java
package com.acme.orders;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.verifier.messaging.boot.AutoConfigureMessageVerifier;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMessageVerifier
@ActiveProfiles("contract")
@Import(ContractBusTestConfiguration.class)
public abstract class OrderMessagingContractBase {

    @Autowired
    OrderApplicationPublisher publisher;

    @BeforeEach
    void prepareFixture() {
        // Seed Order 42 và reset trạng thái transport test.
    }

    protected void publishOrderCreated() {
        // Dùng phương thức application thực sự phát OrderCreated.
        publisher.publishCreatedOrder(42L);
    }
}
~~~

**`OrderApplicationPublisher` là thành phần ứng dụng giả định**. Lớp `OrderApplication`/fixture phải tồn tại trong dự án. Cấu hình Maven/Gradle của Spring Cloud Contract cần trỏ `baseClassForTests` tới `OrderMessagingContractBase` và dùng test framework tương thích.

Hãy kiểm tên package của `@AutoConfigureMessageVerifier` theo phiên bản đã resolve (Spring Cloud Contract messaging auto-configuration thường dùng package `org.springframework.cloud.contract.verifier.messaging.boot`). Generated test phải nhận **đúng adapter** và **đúng test profile**.

### 13.1. Không lẫn việc “trigger” với việc “đưa message giả”

Sai:

~~~java
protected void publishOrderCreated() {
    testBusPort.publish("orders.created",
        new BusEnvelope(staticJson, staticHeaders));
}
~~~

Cách này test **chính fake payload do base test tạo**. Một regression trong Order Service serializer, event mapper hoặc publisher có thể không bị phát hiện.

Đúng hướng:

~~~text
publishOrderCreated()
    -> OrderApplicationPublisher
    -> mapping Order domain object thành event
    -> app outbound adapter/SDK test config
    -> broker/test port
    -> MessageVerifierReceiver
    -> generated assertions
~~~

Nếu dùng in-memory port để chạy nhanh, vẫn cần xác nhận publisher đang sử dụng cùng transport abstraction/adapter mà app production dùng ở ranh giới phù hợp, và bổ sung integration test cho SDK thật.

## 14. Generated producer test làm gì?

Một generated test cho contract outbound có thể có **hình thái logic**:

~~~java
// PSEUDOCODE — không phải output chính xác của generator.
@Test
void shouldPublishOrderCreatedV1() {
    publishOrderCreated();

    ContractVerifierMessage actual =
        contractVerifierMessaging.receive("orders.created", contract);

    assertThat(actual).isNotNull();
    assertThat(actual.getHeader("eventType").toString())
        .isEqualTo("OrderCreated");
    assertThat(actual.getHeader("schemaVersion").toString())
        .isEqualTo("1");

    // Parse payload và kiểm eventId, orderId, amountMinor, currency.
}
~~~

Generated tests thực tế có thể sử dụng những class khác hoặc code generation của JUnit/Spock. Ví dụ chỉ giúp đọc **chuỗi trách nhiệm**:

1. Gọi trigger method.
2. Chờ message ở destination.
3. Fail nếu không có message trong khoảng chờ.
4. Assert headers, body, các matchers và metadata như contract quy định.

**Đừng chỉnh trực tiếp generated test để “sửa” adapter**. Nếu không nhận message, hãy kiểm destination mapping, bean wiring và SDK/test broker trước. Khi cần đổi expected behavior, sửa contract DSL và kiểm cả producer lẫn consumer compatibility.

## 15. Timeout, polling và bất đồng bộ: thiết kế không flaky

Một adapter receiver cần chính sách cụ thể:

| Đối tượng | Nguy cơ | Cách thiết kế |
| --- | --- | --- |
| **Timeout** | `receive` chờ vô hạn, CI kẹt. | Timeout hữu hạn, đơn vị nhất quán, trả null/exception đúng SPI. |
| **Poll interval** | Poll quá dày, làm broker quá tải; quá thưa, chậm test. | Dùng long-poll/await có kiểm soát, không busy loop. |
| **Send completion** | Future chưa hoàn tất nhưng generated test đã receive. | Chờ ack/future theo timeout nếu semantics yêu cầu. |
| **Retry** | Nhận message hai lần, test fail ngẫu nhiên. | Dùng event ID và policy retry/idempotency phù hợp. |
| **Queue tồn đọng** | Test nhận event từ lượt chạy trước. | Namespace/consumer group riêng, dọn state hoặc filter correlation. |
| **Parallel tests** | Hai receivers cạnh tranh cùng queue. | Tách đích/nhóm test hoặc chạy tuần tự phần không độc lập. |
| **Clock** | Message timestamp động làm matcher fail. | Kiểm format/miền giá trị, inject Clock nếu cần. |
| **Cleanup** | Client/background thread còn chạy sau test. | Close/stop trong lifecycle test. |

**Không dùng `Thread.sleep(5000)` làm giải pháp chung**. Một sleep cố định vẫn có thể fail khi CI chậm hơn 5 giây và làm suite chậm khi broker nhanh. Nên dùng receive/poll với timeout đúng mức, condition/await có chẩn đoán rõ.

### 15.1. Timeout kết hợp với log có chọn lọc

Khi không có message, một exception hữu ích nên nêu:

~~~text
Expected message was not received:
  logicalDestination = orders.created
  physicalDestination = run-483.orders.created
  waitTime = 5 s
  testRunId = run-483
  eventType = OrderCreated
~~~

Không in **Authorization**, broker password, raw customer payload hoặc token trong log. Nếu phải ghi correlation ID, dùng ID test giả và quy ước bảo mật.

## 16. Headers, content type và matcher cho message

Trong bài học contract HTTP, response matcher có thể dùng JSONPath. Với messaging, những trường tương tự cần được kiểm theo **destination, message headers và payload**.

Một contract có `eventId` động:

~~~groovy
outputMessage {
    sentTo('orders.created')
    headers {
        header('eventType', 'OrderCreated')
        header('schemaVersion', 1)
        header('contentType', 'application/json')
    }
    body(
        eventId: 'evt-example',
        orderId: 'ORD-42',
        amountMinor: 125000,
        currency: 'VND'
    )
    bodyMatchers {
        jsonPath('$.eventId', byRegex('evt-[A-Za-z0-9-]+'))
    }
}
~~~

**Không nới tất cả field thành “bất kỳ String”.** Consumer phụ thuộc vào `orderId`, `amountMinor` và `currency` nên các giá trị/kiểu quan trọng vẫn cần bảo vệ theo fixture hoặc invariant. Nếu adapter luôn convert payload thành một String cố định do nó tự tạo, body matcher sẽ mất giá trị.

Một lỗi tinh vi là **header type conversion**: broker trả `schemaVersion="1"` còn contract kiểm số `1`. Có thể cần quy tắc chuẩn hóa **được thống nhất** ở boundary, hoặc sửa chính contract nếu wire semantics cam kết string. Đừng lặng lẽ đổi kiểu chỉ để test xanh.

## 17. Adapter unit tests: kiểm chính cầu nối

Adapter có thể có bug dù producer và consumer đúng. Hãy viết một bộ **conformance tests** tối thiểu, độc lập với generated contract tests.

| Trường hợp | Input | Kỳ vọng |
| --- | --- | --- |
| Gửi JSON | Payload object `OrderCreated` | Port nhận bytes JSON tương đương và đúng destination. |
| Gửi binary | `byte[]` | Bytes giữ nguyên, không tự chuyển String. |
| Headers | `eventType`, `schemaVersion`, `contentType` | Các header contract được giữ đúng ý nghĩa. |
| Destination chưa khai báo | `unknown.topic` | Fail rõ ràng; không gửi sang default/prod topic. |
| Nhận message | Port có event đúng destination | Verifier nhận đúng payload/headers. |
| Timeout | Không có message | Nhận kết quả timeout theo SPI, không treo test. |
| Interrupt | Thread bị interrupt | Giữ interruption semantics, cleanup. |
| Nhiều destination | Event A và B | Không đọc nhầm queue. |
| Serialisation error | Payload không encode được | Fail sớm, không publish payload rỗng. |
| Message cũ | Queue có event của run trước | Cô lập/clear/filter đúng test run ID. |

Một test port ngắn:

~~~java
@Test
void keepsPayloadAndDestination() {
    TestBusPort bus = new InMemoryTestBusPort();
    byte[] body = "{\"orderId\":\"ORD-42\"}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

    bus.publish("orders.created",
        new TestBusPort.BusEnvelope(
            body, Map.of("eventType", "OrderCreated")));

    TestBusPort.BusEnvelope received =
        bus.receive("orders.created", Duration.ofSeconds(1));

    assertThat(received).isNotNull();
    assertThat(received.payload()).containsExactly(body);
    assertThat(received.headers())
        .containsEntry("eventType", "OrderCreated");
}
~~~

Đây là test cho **fake TestBusPort**, chưa phải test của `AsterBusMessageVerifier` hoặc broker thật. Tương tự, nên viết test riêng cho adapter gửi/nhận để kiểm codec và header mapping; sau đó mới cho generated producer tests sử dụng adapter.

## 18. Stub Runner với messaging adapter custom

Producer verification đã đạt và xuất bản một artifact:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

Ở **Billing Service**, consumer test có thể dùng `@AutoConfigureStubRunner` và trigger event theo `label`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(BillingContractBusTestConfiguration.class)
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderCreatedContractTest {

    @Autowired
    StubTrigger stubTrigger;

    @Autowired
    BillingEventProbe billingEventProbe;

    @Test
    void handlesPublishedOrderCreated() {
        assertThat(stubTrigger.trigger(
            "com.acme:order-service", "orderCreatedV1"
        )).isTrue();

        assertThat(billingEventProbe.awaitOrder(
            "ORD-42", java.time.Duration.ofSeconds(5)
        )).isTrue();
    }
}
~~~

`BillingContractBusTestConfiguration` và `BillingEventProbe` là **thành phần test do dự án tự tạo**; `BillingEventProbe.awaitOrder(...)` phải quan sát kết quả **listener thật** thay vì trả `true` vô điều kiện.

**Một số điểm bắt buộc:**

1. `LOCAL` yêu cầu JAR stub đã có trong Maven local của consumer test runner; `REMOTE` tải qua artifact repository với credentials/phương thức xác thực phù hợp.
2. `StubTrigger.trigger(...)` dùng **label** từ contract. Có thể dùng `StubFinder` vì nó mở rộng khả năng trigger; không phải API HTTP port.
3. Spring context phải có **sender adapter hoạt động**. Tải được artifact `stubs` nhưng không có transport sender sẽ không đưa message tới consumer listener.
4. Consumer test nên assert **side effect nghiệp vụ** của listener, ví dụ Billing đã ghi một event hoặc cập nhật trạng thái, chứ không chỉ assert trigger trả `true`.
5. Trigger trả thành công không tự chứng minh broker đã **delivery/acknowledge** nếu adapter gửi bất đồng bộ và không chờ kết quả.

### 18.1. Khi dùng Stub Runner JUnit 5 extension thay vì Spring annotation

Các API builder của Stub Runner JUnit 5 extension có thể cho phép truyền **sender/receiver implementation** trực tiếp, thay vì dựa hoàn toàn vào Spring context:

~~~java
// PSEUDOCODE API shape: kiểm exact builder methods theo version.
StubRunnerExtension extension = new StubRunnerExtension()
    .stubsMode(StubRunnerProperties.StubsMode.LOCAL)
    .downloadStub("com.acme:order-service:1.0.0:stubs")
    .messageVerifierSender(customSender)
    .messageVerifierReceiver(customReceiver);
~~~

**Đừng trộn ví dụ này với annotation như hai bước bắt buộc**. Chọn **Spring annotation/config beans** hoặc **JUnit extension builder** theo kiến trúc test, rồi xem phiên bản Stub Runner có các setter được nêu hay không. Khi quên cung cấp messaging sender/receiver cho JUnit extension, việc trigger message có thể ném lỗi thay vì gửi được.

## 19. Test dùng broker thật: phạm vi khác fake adapter

Một lớp test có thể chọn **broker container/test tenant** thay vì fake. Nếu AsterBus không có Testcontainers module, có thể:

- Khởi động một service container từ **image được duyệt** hoặc docker-compose tương ứng trong CI.
- Dùng một **test cluster/tenant** với queue/topic prefix tách biệt, credentials ít quyền.
- Tạo port SDK thực kết nối endpoint test, có health check và cleanup.
- Dùng test message có `runId`/`correlationId` riêng để tránh đọc nhầm message của job khác.

| Mức kiểm | Phát hiện tốt | Không chứng minh |
| --- | --- | --- |
| **Adapter unit test với fake** | Cấu trúc send/receive, mapping, timeout cơ bản. | Broker SDK/transport thật. |
| **Producer contract test với fake đúng boundary** | Publisher tạo dữ liệu phù hợp contract ở ranh giới đã chọn. | Wire encoding và broker delivery semantics. |
| **Broker integration test** | SDK serialization, headers, routing, send/receive, ack/retry trong test environment. | Mọi chính sách/cấu hình của production. |
| **Consumer Stub Runner test qua broker test** | Listener thật có thể xử lý message mẫu của contract. | Producer implementation thật đang deploy đúng release nếu không có producer verification/deploy evidence. |
| **End-to-end staging** | Luồng nhiều dịch vụ qua môi trường gần production. | Tính tái lập và cô lập như contract tests. |

**Không cần biến mọi contract test thành một E2E test nặng**, nhưng đừng gọi fake test là “đã chứng minh Kafka/AsterBus production”. Phân tầng giúp suite nhanh, ổn định và vẫn phát hiện lỗi SDK/codec ở lớp integration phù hợp.

### 19.1. Kiểm bytes trên dây khi cần

Giả sử `amountMinor` là một số nhưng serializer biến nó thành string:

~~~json
{"orderId":"ORD-42","amountMinor":"125000"}
~~~

Nếu adapter test bỏ qua codec thật, generated producer test có thể nhận một domain object và PASS dù **consumer thật không parse được wire bytes**. Hãy có integration test đọc **bytes do SDK thật publish**, decode theo cùng schema, assert:

- `amountMinor` vẫn là JSON number hoặc kiểu Avro/Protobuf đã cam kết.
- Timestamp, enum, null/missing và numeric precision đúng.
- `contentType`/`schemaVersion` và transport metadata tương ứng.
- Consumer decoder của phiên bản được hỗ trợ nhận được.

Đặc biệt với Avro/Protobuf, schema registry và compatibility mode là một phần của môi trường test, không chỉ là `outputMessage.body(...)`.

## 20. Bảo mật của custom messaging adapter

Một adapter tùy biến có quyền publish và consume message, nên nó có thể **gây tác động thật** nếu cấu hình sai.

| Rủi ro | Biện pháp |
| --- | --- |
| CI gửi vào production topic | Destination allowlist, test namespace bắt buộc, credentials chỉ dùng test tenant. |
| Secret broker lộ trong logs | Inject secret runtime, không in headers Authorization/token, redaction. |
| Stub artifact chứa dữ liệu thật | Dùng synthetic fixtures, secret scanning cho Groovy/YAML/stubs. |
| Consumer test tranh queue production | Dùng isolated test queue, không subscribe live customer traffic. |
| SSL verification bị vô hiệu để “cho test chạy” | Cài CA/truststore đúng, không chấp nhận TLS insecure workaround. |
| Adapter cho phép arbitrary destination | Fail closed, kiểm mappings, tránh input chưa tin cậy điều khiển tên queue. |
| Retry vô hạn gây spam | Giới hạn attempts/backoff, timeout và quota test. |
| Dùng account admin broker | Service identity ít quyền cho topic/namespace test. |

**Không đưa secret vào contract DSL hoặc JAR stubs**. Những artifacts này có thể được nhiều consumer teams tải để test, nên phải coi nội dung của chúng như tài liệu chia sẻ.

## 21. CI/CD: bảo đảm producer tests và consumer tests dùng cùng hợp đồng

~~~mermaid
flowchart TD
    A["Producer commit + Groovy/YAML contract"] --> B["Resolve Spring Cloud Contract Plugin + adapter version"]
    B --> C["Run adapter conformance tests"]
    C --> D["Generate producer verification tests"]
    D --> E["Run producer contract tests"]
    E --> F{"Tests thực sự chạy và đạt?"}
    F -->|Không| G["Chặn stub publish"]
    F -->|Có| H["Broker SDK integration tests theo policy"]
    H --> I["Đóng gói immutable JAR stubs"]
    I --> J["Publish version + checksum/provenance"]
    J --> K["Consumer CI tải đúng stub artifact"]
    K --> L["Stub Runner trigger qua custom sender"]
    L --> M["Assert listener thật + kết quả nghiệp vụ"]
~~~

Một pipeline nên lưu:

1. **Contract source Git SHA**, Groovy/YAML path và version/label.
2. **Spring Cloud Contract plugin/starter/BOM versions** tương thích.
3. **Custom adapter version** và SDK version.
4. **Producer generated test report** với số lượng tests đã chạy, không chỉ `BUILD SUCCESS`.
5. **Broker integration test report**, nếu required.
6. **Stub JAR Maven coordinates + SHA-256** để consumer tải đúng bytes.
7. **Consumer CI run**, artifact version, test profile, backend là fake hay broker.
8. **Test environment ID**/namespace cùng logs đã redaction để điều tra flaky.

**Không phát hành stubs chỉ vì converter đã tạo file**; cần generated producer tests kiểm implementation và một release artifact có provenance. Với adapter custom, cũng cần chặn publish nếu **adapter conformance tests không đạt**.

### 21.1. Dependency Maven và Gradle

Producer cần Contract Verifier ở **test scope** và Maven/Gradle Contract Plugin để sinh tests; consumer cần Stub Runner ở **test scope**. Ví dụ Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ở consumer:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation(
        'org.springframework.cloud:spring-cloud-starter-contract-verifier'
    )
    // Consumer module, nếu cần:
    testImplementation(
        'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
    )
}
~~~

Đây là **mảnh cấu hình**, không phải build đầy đủ. Cần Spring Cloud BOM phù hợp Spring Boot/Contract Plugin; phần **SDK AsterBus** và module adapter test phải được bổ sung theo project. **Không tự thêm cả Verifier và Stub Runner vào mọi module** nếu không cần vai trò tương ứng.

## 22. Lỗi thường gặp khi tự viết adapter

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Generated test báo không có messaging verifier | Thiếu `@AutoConfigureMessageVerifier`, bean sai type hoặc context không nạp. | Kiểm annotation, bean report, plugin/starter compatibility. |
| Có hai `MessageVerifierSender` beans | Auto-integration và custom adapter cùng đăng ký. | Kiểm bean selection, profile và auto-config conditions. |
| Trigger producer chạy nhưng không receive event | Publisher gửi tới destination vật lý khác với receiver. | Log logical→physical mapping đã redaction, kiểm namespace. |
| Generated test nhận message cũ và PASS | Queue/offset chưa reset, test dùng shared consumer group. | Cô lập test run, correlation và cleanup. |
| `receive` treo CI | Poll vô hạn hoặc timeout không được SDK tôn trọng. | Thêm timeout hữu hạn, kiểm cancellation và cleanup. |
| `receive` trả null quá sớm | Poll timeout quá thấp hoặc async send chưa hoàn tất. | Kiểm send ack, timeout policy và scheduling. |
| Header `schemaVersion` so sai | SDK biến integer thành string. | Chuẩn hóa có hợp đồng hoặc sửa mapping; test wire metadata. |
| JSON payload bị double-encode | `ObjectMapper` serialize String lần nữa thành quoted string. | Tách String/byte[]/object paths và test codecs. |
| Binary payload hỏng | Convert bytes qua UTF-8 String. | Giữ bytes/serializer tương ứng. |
| Stub Runner báo trigger label không có | Label sai hoặc JAR `stubs` không chứa contract. | Kiểm contract label, artifact version/content và source scan. |
| Trigger trả thành công nhưng listener không xử lý | Sender chỉ enqueue vào fake khác với listener port, hoặc không chờ delivery. | Kiểm cùng context/namespace, verify business side effect. |
| Test xanh trên fake, fail trên broker | Routing, serialization, ack, auth khác. | Broker integration test với SDK thực. |
| Bị 401/403/SSL khi tải stub | Repository credentials/TLS, không phải messaging destination. | Phân biệt artifact download và message transport. |
| Message test fail trên CI song song | Topic/group/queue chia sẻ, event cũ hoặc port collision. | Test namespace/consumer group riêng, reset state. |
| Test không thấy header bắt buộc | Adapter allowlist quá hẹp hoặc converter bỏ metadata. | Kiểm envelope trước/sau adapter và contract DSL. |
| Gradle/Maven build xanh nhưng không chạy generated tests | Plugin/source paths/test runner không cấu hình đúng. | Kiểm generated sources, test reports, test count. |

**Đường chẩn đoán:** DSL đã được nạp → generated tests tồn tại → verifier bean đúng → trigger gọi publisher thật → adapter mapping đúng → broker/test port nhận message → verifier assertions đúng → stub artifact đúng label/version → Stub Runner sender vào đúng listener → consumer side effect được xác nhận.

## 23. Mutation tests giúp xác minh adapter không che lỗi

Một cầu nối tự viết rất dễ trở thành “máy làm test xanh”. Hãy thử thay đổi có chủ đích trong một nhánh:

| Mutation | Kết quả mong đợi |
| --- | --- |
| Producer đổi `amountMinor` thành String | **FAIL** contract/test wire codec. |
| Producer đổi `orders.created` thành `orders.cancelled` | **FAIL** receive theo destination. |
| Producer bỏ `eventType` | **FAIL** header assertion. |
| Producer đổi `schemaVersion` từ 1 sang 2 mà không version hóa | **FAIL** nếu consumer cần v1. |
| Producer phát payload đúng nhưng thiếu `orderId` | **FAIL** required body field. |
| `eventId` thay giá trị nhưng đúng định dạng được phép | **PASS** nếu contract chỉ cam kết format. |
| Broker test bị down | **FAIL rõ ràng**, không silently pass vì NoOp adapter. |
| Consumer listener không xử lý event | **FAIL** side-effect assertion. |
| Stub Runner trigger label sai | **FAIL** với thông tin label/artifact rõ. |
| Nhận message từ test run cũ | **FAIL hoặc bị loại lọc**, không pass giả. |

**Không viết adapter để tự synthesize “expected message” sau khi timeout.** Nếu không có message, test phải fail hoặc nhận kết quả timeout đúng SPI. Có thể dùng một conformance test cho receiver để chứng minh nó không tự tạo payload khi broker im lặng.

## 24. Lộ trình triển khai custom messaging adapter trong một nhóm

Một quy trình khả thi gồm:

1. **Xác định trách nhiệm adapter**: cần producer outbound, consumer inbound, Stub Runner trigger hay cả ba?
2. **Đối chiếu tích hợp sẵn** trước khi tự viết.
3. **Chọn contract source/versions** và các destination/header semantics mà consumer thực sự cần.
4. **Định nghĩa TestBusPort** và codec/destination/header policy độc lập SDK.
5. **Viết fake port** cho unit/conformance tests của adapter.
6. **Viết custom Sender/Receiver** khớp SPI của Spring Cloud Contract version dự án.
7. **Đăng ký bean trong test context** và xử lý xung đột với auto-configuration.
8. **Tạo base test** để generated tests kích hoạt **publisher thật** hoặc assert side effect của listener thật.
9. **Viết transport port cho SDK** dùng broker test tenant/container, kiểm serialization/headers/ack/offset.
10. **Sinh và chạy generated producer tests**, kiểm số test và các mutation lỗi.
11. **Đóng gói/publish JAR `stubs`** theo coordinates/version xác định.
12. **Cấu hình consumer Stub Runner** và cung cấp sender adapter cho test context/JUnit extension.
13. **Trigger theo label** và assert listener thật đã xử lý event.
14. **Cô lập CI test namespace**, timeout, cleanup và quyền broker; lưu artifact checksum/provenance.
15. **Review, tài liệu hóa adapter**: SDK, test modes, supported content types, header mappings, known limitations.

**Nên bắt đầu từ kịch bản một destination và một event JSON**, sau đó mở rộng sang nhiều schema/destination, async retry, DLQ, binary serializer và parallel execution theo mức cần thiết. Tránh xây dựng một framework broker tổng quát trước khi chứng minh một contract đi hết producer→consumer.

## 25. Bài thực hành: tích hợp AsterBus chưa được hỗ trợ

Bài thực hành dùng **broker giả định AsterBus** với producer **Order Service** và consumer **Billing Service**. Người học có thể dùng fake trong bộ unit tests, sau đó thay bằng SDK/broker thật nếu môi trường được cung cấp.

1. **Viết Groovy contract** `order_created_v1.groovy` có `label=orderCreatedV1`, `triggeredBy('publishOrderCreated()')`, `sentTo('orders.created')`, headers `eventType`/`schemaVersion` và payload `orderId`/`amountMinor`/`currency`.
2. **Viết YAML contract tương đương để so sánh**, nhưng chỉ để một DSL có hiệu lực trong mỗi lượt generate.
3. **Định nghĩa `TestBusPort`** với `publish(destination, envelope)` và `receive(destination, timeout)`.
4. **Tạo fake in-memory port**, mỗi destination có queue riêng; test gửi nhận giữ đúng bytes và headers.
5. **Hiện thực `MessageVerifierSender`/`MessageVerifierReceiver` adapter**, tách object/String/byte[] và không nuốt lỗi serializer.
6. **Đăng ký adapter ở Spring Test context** bằng `@TestConfiguration`; kiểm bean type/version và tránh duplicate auto-configured verifiers.
7. **Tạo `OrderMessagingContractBase`** có `@AutoConfigureMessageVerifier`; `publishOrderCreated()` gọi application publisher thật.
8. **Chạy generated producer verification**, kiểm test nhận được message ở destination đúng và assert payload/headers.
9. **Thử phá một header** `eventType` hoặc đổi `amountMinor` sang String, bảo đảm test FAIL; hoàn nguyên.
10. **Thay fake bằng SDK port của AsterBus test broker** nếu có; kiểm publisher thật, serialize bytes, header mapping và broker delivery.
11. **Thêm inbound contract** cho `ReserveInventory` bằng `messageFrom` và kiểm business side effect sau khi sender adapter đẩy input.
12. **Đóng gói artifact `stubs`** của producer với version cụ thể; mở JAR và kiểm label/contract tồn tại.
13. **Ở Billing**, cấu hình Stub Runner và custom sender, trigger `orderCreatedV1`, assert listener cập nhật trạng thái order.
14. **Mô phỏng timeout và message cũ**, bảo đảm receiver không tự tạo payload hoặc nhận event sai run.
15. **Chạy song song hai tests/destinations** và quan sát khả năng cô lập topic/queue/consumer group.
16. **Tạo CI gates**: conformance tests → producer verification → broker integration tests theo policy → publish stubs → consumer Stub Runner tests.
17. **Ghi kết quả** theo Git SHA, adapter version, Spring Cloud Contract version, broker test mode, stub checksum và test reports.

**Tiêu chí đạt:** generated producer test chỉ PASS khi **producer application thực sự phát message đúng hợp đồng**; adapter truyền đúng destination/payload/headers và timeout; consumer Stub Runner trigger **listener thật** qua adapter; một mutation phá hợp đồng FAIL trong khi một metadata động hợp lệ không gây false failure; báo cáo phân biệt rõ **fake test** và **real broker integration test**.

## 26. Câu hỏi tự kiểm tra

1. Khi nào nên tận dụng Spring Cloud Stream/JMS/Camel integration thay vì tự viết adapter?
2. `MessageVerifierSender` và `MessageVerifierReceiver` có trách nhiệm khác nhau thế nào?
3. Vì sao custom `TestBusPort` không phải một SPI có sẵn của Spring Cloud Contract?
4. `triggeredBy(...)` khác `messageFrom(...)` về hướng kiểm thử như thế nào?
5. Vì sao `publishOrderCreated()` phải gọi application publisher thật thay vì đưa payload tĩnh vào queue?
6. `outputMessage.sentTo(...)` nên biểu thị tên logic hay tên topic vật lý của một CI runner?
7. Khi mapping destination, vì sao cần allowlist/namespace để tránh gửi nhầm vào production?
8. Vì sao không nên copy tất cả Spring MessageHeaders ra broker?
9. Khi nào chuyển payload thành UTF-8 String là không an toàn?
10. `schemaVersion=1` dưới dạng Integer có thể khác `"1"` dưới dạng String như thế nào?
11. Nếu receiver không thấy message trong timeout, nên làm gì để test không đạt giả?
12. Vì sao sleep cố định thường làm messaging CI flaky?
13. Nếu có sẵn Spring Cloud Stream auto-configured verifier, thêm custom sender/receiver có thể gây lỗi gì?
14. `@AutoConfigureMessageVerifier` cần ở đâu trong producer messaging test setup?
15. Stub Runner consumer trigger theo label làm gì, và tại sao phải có sender adapter?
16. Stub Runner gửi message thành công có đủ chứng minh consumer xử lý nghiệp vụ đúng không?
17. Một fake in-memory queue kiểm được gì và không kiểm được gì về broker?
18. Vì sao phải có integration test trên SDK/codec/broker khi transport dùng Avro/Protobuf hoặc custom headers?
19. Khi chạy CI song song, topic/consumer group/offset ảnh hưởng test như thế nào?
20. Vì sao artifact `stubs` phải có version/checksum và producer verification report đi kèm?
21. Khi nào một adapter nên fail fast thay vì tự normalize dữ liệu cho “phù hợp contract”?
22. Những mutation nào chứng minh adapter không che breaking change?

## 27. Nguồn đọc thêm và nguyên tắc nâng phiên bản

- **Spring Cloud Contract — Messaging:** https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html
- **Spring Cloud Contract 4.1 — Messaging:** https://docs.spring.io/spring-cloud-contract/reference/4.1/project-features-messaging.html
- **Stub Runner Core / Messaging Stubs:** https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html
- **Stub Runner JUnit extension với messaging:** https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-junit.html
- **Spring Cloud Contract — YAML schema:** https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html

Khi nâng Spring Cloud Contract, phải xem lại **SPI sender/receiver signatures**, auto-configuration, generated test imports, Stub Runner builder API, codec/header behavior và compatibility với Spring Boot/BOM. Các ví dụ package, annotation và `YamlContract` trong bài mô tả **một kiểu tích hợp phổ biến**, không phải API bất biến qua mọi phiên bản.

**Ghi nhớ:** **Adapter messaging tùy biến là cầu nối giữa hợp đồng và công nghệ truyền message, không phải nơi “tạo kết quả cho test xanh”**. Hãy giữ Groovy/YAML DSL mô tả đúng destination, headers, payload và semantics; hiện thực `MessageVerifierSender`/`MessageVerifierReceiver` bằng một port có kiểm soát; dùng generated producer tests để xác minh **mã publisher/listener thật**, Stub Runner để kiểm **mã consumer thật**, và thêm integration tests khi cần chứng minh codec, broker routing, ack/retry hay schema registry. Cô lập môi trường, timeout hữu hạn, không gửi message vào production, ghi đúng artifact `stubs`/version/CI evidence. Nhờ đó, Spring Cloud Contract vẫn bảo vệ được sự tương thích giữa producer và consumer ngay cả khi nền tảng messaging của nhóm chưa có adapter hỗ trợ sẵn.
