# Metadata key expression trong Spring Integration runtime

## 1. Metadata key expression giải quyết vấn đề nào?

Trong **SPRING_INTEGRATION_RUNTIME**, message có thể được gửi lại do retry, broker redelivery, poller khởi chạy lại, lỗi mạng hoặc người vận hành replay. Một message có `MessageHeaders.ID` mới nhưng vẫn chứa **cùng một sự kiện nghiệp vụ**. Nếu handler ghi đơn hàng, xuất hóa đơn hoặc gọi API thanh toán nhiều lần, hệ thống có thể tạo tác động trùng lặp.

Spring Integration cung cấp `MetadataStore` để lưu **trạng thái nhỏ dạng chuỗi key–value**. Khi dùng với mẫu **Idempotent Receiver**, một `MetadataStoreSelector` chọn key từ message, kiểm tra xem key đã tồn tại chưa rồi quyết định chấp nhận hay đánh dấu/từ chối message.

**Metadata key expression** là biểu thức Spring Expression Language (SpEL) tính ra key ấy, thường được cấu hình qua thuộc tính `key-expression` của `<int:idempotent-receiver>`. Nó không phải một câu lệnh truy vấn SQL, cũng không phải tính năng tự động của interface `MetadataStore`.

Ví dụ cùng một shipment được nhận hai lần:

~~~text
Message A: payload.shipmentId = "SHP-101", headers.tenantId = "shop-1"
Message B: payload.shipmentId = "SHP-101", headers.tenantId = "shop-1"

key-expression = 'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId

A -> metadata key "shipment:v1:shop-1:SHP-101" -> chưa có -> chấp nhận
B -> metadata key "shipment:v1:shop-1:SHP-101" -> đã có -> duplicate
~~~

Bài học thuộc chương **Metadata store**, nhưng tập trung vào cách **chọn một key đúng với danh tính logic của công việc**, cách dùng biểu thức đó tại consumer endpoint và hệ quả ở runtime đối với concurrency, retry, transaction, message store, correlation, lỗi và hiệu năng.

~~~mermaid
flowchart LR
    M["Message"] --> K["Đánh giá key-expression"]
    K --> S{"ConcurrentMetadataStore.putIfAbsent(key, value)"}
    S -->|Key mới| A["Message được chấp nhận"]
    S -->|Key tồn tại| D{"Chính sách duplicate"}
    A --> H["Message handler"]
    D -->|discard-channel| Q["Kênh duplicate"]
    D -->|không discard| F["Đặt header duplicateMessage=true"]
    F --> H
    D -->|throwExceptionOnRejection| E["MessageRejectedException"]
~~~

Lưu ý: key thường được **đăng ký trước khi handler nghiệp vụ hoàn tất**. Chống trùng dựa vào key chưa đủ để bảo đảm giao dịch nghiệp vụ đã commit hay xử lý đúng một lần.

## 2. Các thành phần cần phân biệt

| Thành phần | Nhiệm vụ | Nhận gì, trả gì? |
| --- | --- | --- |
| `MetadataStore` | Lưu/lấy/xóa metadata | `String key → String value` |
| `ConcurrentMetadataStore` | Thêm khả năng cập nhật nguyên tử | `putIfAbsent(key, value)` và `replace(key, old, new)` |
| `MetadataStoreSelector` | Trích xuất key/value, đánh giá message mới hay trùng | `Message<?> → boolean accept` |
| `IdempotentReceiverInterceptor` | Áp kết quả selector lên `MessageHandler.handleMessage()` | Cho qua, gắn header duplicate hoặc discard/throw |
| `key-expression` | SpEL để **tạo key** cho selector | `Message<?> → key dạng String` |
| `value-expression` | SpEL để **tạo value** đi kèm key | `Message<?> → value dạng String` |
| `compare-values` | So sánh value đã lưu và mới cho cùng key | `(oldValue, newValue) → boolean` |

Hai điểm quan trọng:

1. **`MetadataStore` không hiểu SpEL.** Nó biết `get`, `put`, `remove`. `ConcurrentMetadataStore` thêm `putIfAbsent`, `replace`. Cơ chế xử lý `key-expression` nằm ở endpoint/selector sử dụng store.
2. **`MessageStore` khác `MetadataStore`.** Message store lưu message hoặc message group; metadata store lưu dấu vết/idempotency state. Cả hai có thể dùng JDBC, Redis hoặc backend khác nhưng không thay thế được vai trò của nhau.

Ví dụ khi nhận từ SFTP, một persistent accept-once file filter có thể dùng metadata store để nhớ trạng thái file đã thấy. Tuy nhiên cách tạo key của **file filter** do filter/adapter quy định, có thể kết hợp prefix/path/modified time; thuộc tính `key-expression` của **idempotent receiver** không tự động được dùng trong file filter. Luôn xác định đúng component sở hữu cách tạo khóa.

## 3. Đánh giá SpEL: root object là Message

Tại `<int:idempotent-receiver key-expression="...">`, biểu thức được đưa vào `ExpressionEvaluatingMessageProcessor` của `MetadataStoreSelector`. Trong trường hợp này, **evaluation root là `Message<?>` đầu vào**. Vì vậy có thể truy cập:

- `payload`: dữ liệu nghiệp vụ.
- `headers`: map metadata đi kèm message.
- `headers['tenantId']`, `headers['eventId']`: giá trị header cụ thể.
- `payload.shipmentId`: property của payload nếu payload có accessor tương thích với SpEL/JavaBean.

Ví dụ dùng POJO có `getShipmentId()` để property `payload.shipmentId` được phân giải rõ:

~~~java
public final class Shipment {
    private final String shipmentId;
    private final String status;

    public Shipment(String shipmentId, String status) {
        this.shipmentId = shipmentId;
        this.status = status;
    }

    public String getShipmentId() {
        return shipmentId;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Bảng so sánh cách chọn key:

| Expression | Key dự kiến | Nhận xét |
| --- | --- | --- |
| `headers['eventId']` | `evt-182` | Tốt khi event ID ổn định, duy nhất cho logical event |
| `'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId` | `shipment:v1:shop-1:SHP-101` | Có namespace và tenant để tránh đụng khóa |
| `payload.shipmentId` | `SHP-101` | Nguy hiểm nếu nhiều tenant có cùng shipment ID |
| `headers['id'].toString()` | UUID của message transport | Thường **không ổn định qua redelivery** hoặc message mới |
| `headers['correlationId']` | ID của một nhóm flow | Có thể gộp nhầm nhiều message khác nhau cùng nhóm |
| `payload.toString()` | Phụ thuộc `toString()` của object | Không nên dùng: dễ thay đổi hoặc chứa dữ liệu nhạy cảm |

**Chọn identity theo đơn vị nghiệp vụ cần chống trùng.** Nếu hai message có chung `orderId` nhưng là hai event `order.created` và `order.cancelled` khác nhau, không thể dùng mỗi `orderId` để loại bỏ một trong hai. Có thể dùng `eventType + eventId`, hoặc `tenant + orderId + operationType` theo contract.

### SpEL expression và interpolation

Trong XML, `key-expression` là **nội dung SpEL**, không cần bọc toàn bộ trong `#{...}` như một giá trị bean reference. Ví dụ:

~~~xml
key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
~~~

Dấu nháy đơn quanh `shipment:v1:` và `:` là **literal của SpEL**. Dấu nháy kép bên ngoài thuộc cú pháp XML attribute. Với header có dấu chấm hoặc gạch nối, dạng `headers['x-correlation-id']` rõ hơn `headers.x-correlation-id`.

Biểu thức do hệ thống triển khai nên được xem là **cấu hình tin cậy**. Không lấy trực tiếp chuỗi SpEL từ HTTP header hoặc payload người dùng rồi tự parse/evaluate bằng quyền truy cập bean tùy ý.

## 4. Thiết kế key ổn định, duy nhất và có phạm vi

Một key tốt cần đồng thời đáp ứng:

1. **Ổn định:** cùng logical event sinh cùng key khi retry, redelivery, restart hoặc xử lý trên node khác.
2. **Đúng phạm vi:** hai event khác nhau không được vô tình sinh cùng key.
3. **Có namespace:** tách hệ thống, tenant, event/operation type và các phiên bản key khi cần.
4. **Canonical:** trim, normalize kiểu chữ, format ID và delimiter theo quy ước thống nhất.
5. **Có thể quản lý:** chiều dài phù hợp backend, không làm lộ token/PII hoặc tạo cardinality không kiểm soát.

Một format minh họa:

~~~text
<environment>/<application>/<operation>/v<keyVersion>/<tenant>/<businessId>
prod/billing/issue-invoice/v1/shop-1/INV-2026-0021
~~~

Đây là **chuẩn key do ứng dụng thiết kế**, không phải định dạng do Spring Integration áp đặt. Khi sử dụng delimiter `/`, cần bảo đảm từng thành phần không chứa `/` hoặc encode chính xác để tránh key collision.

**Ví dụ collision khi nối chuỗi thiếu phân tách:**

~~~text
tenant="ab", order="c"   -> "abc"
tenant="a",  order="bc"  -> "abc"
~~~

Nối với delimiter có escape hoặc encode từng trường ngăn lỗi đó:

~~~text
order:v1:ab:c
order:v1:a:bc
~~~

Để xử lý case-sensitivity, chỉ chuyển chữ hoa/thường nếu ID contract cho phép. Chẳng hạn `SHP-ab` và `SHP-AB` có thể là hai ID khác nhau ở một hệ thống. Đừng âm thầm `toLowerCase()` rồi làm mất phân biệt nghiệp vụ.

### Tên key, version và migration

| Khi thay đổi | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| Từ `headers['eventId']` sang `payload.orderId` | Dữ liệu cũ và mới dùng hai định nghĩa identity | Dự tính khoảng chạy song song hoặc migration key |
| Đổi prefix `shipment:v1` thành `shipment:v2` | Duplicate cũ có thể được chấp nhận như mới | Giữ tương thích hoặc di chuyển metadata một cách có kiểm chứng |
| Đổi cách chuẩn hóa ID | Cùng event sinh hai key khác nhau | Chuẩn hóa producer/consumer cùng contract |
| Đổi namespace tenant | Nhiều tenant có thể dùng chung key và chặn nhầm | Include tenant ổn định hoặc phạm vi store tách biệt |
| Thêm shard/node mới | Store in-memory riêng mỗi node sẽ không biết key của node khác | Dùng shared store hỗ trợ atomic operations xuyên node |

Một key cần có **version của quy tắc identity**, không nhất thiết trùng schema version payload. Khi đổi serializer mà identity không đổi, có thể giữ nguyên key version để trạng thái dedup vẫn dùng được.

## 5. Cấu hình XML: `key-expression` cho Idempotent Receiver

Cách rõ nhất để thấy thuộc tính `key-expression` là XML namespace của Spring Integration. Fragment sau sử dụng service activator có bean handler, và interceptor đánh dấu một shipment là duplicate nếu key đã được ghi:

~~~xml
<!-- Fragment: yêu cầu namespace int, bean shipmentService và channel hợp lệ. -->
<bean id="dedupStore"
      class="org.springframework.integration.metadata.SimpleMetadataStore"/>

<int:channel id="shipments"/>

<int:service-activator id="shipEndpoint"
                       input-channel="shipments"
                       ref="shipmentService"
                       method="handle"/>

<int:idempotent-receiver
    id="shipmentIdempotent"
    endpoint="shipEndpoint"
    metadata-store="dedupStore"
    key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
    discard-channel="nullChannel"/>
~~~

Ở đây:

- `endpoint="shipEndpoint"` là **ID endpoint** phải áp advice, không phải tên channel.
- `metadata-store="dedupStore"` là bean `ConcurrentMetadataStore` dùng để ghi key.
- `key-expression` tính key từ mỗi message trước khi handler được gọi.
- `discard-channel="nullChannel"` giúp **bỏ qua** duplicate có chủ đích; nếu muốn giám sát, dùng một channel có subscriber để nhận duplicate.
- `SimpleMetadataStore` chỉ giữ trạng thái trong memory của context hiện tại; restart sẽ mất dấu key, phù hợp **demo**, không phù hợp yêu cầu dedup xuyên restart.

**Kết quả dự kiến:** hai message có cùng `tenantId` và `shipmentId` được gửi liên tiếp: lần đầu đến `shipmentService.handle(...)`, lần hai bị loại qua `nullChannel`. Nếu tenant khác nhưng shipment ID giống, key khác nên cả hai được phép xử lý.

### Cấu hình `value-expression`

Thông thường chỉ cần key để quyết định "đã thấy chưa". `MetadataStoreSelector` lưu **timestamp header** làm value mặc định (ở dạng biểu diễn chuỗi do selector chọn). Có thể tự định nghĩa value:

~~~xml
<int:idempotent-receiver
    id="shipmentWithValue"
    endpoint="shipEndpoint"
    metadata-store="dedupStore"
    key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"
    value-expression="headers['eventId']"
    discard-channel="nullChannel"/>
~~~

Đây là **cấu hình thay thế**, không khai báo đồng thời với bean interceptor trước trên cùng endpoint nếu muốn demo một lần kiểm tra. `value-expression` không tự thay đổi logic "key đã tồn tại thì duplicate". Khi muốn **so sánh value cũ/mới** để quyết định chấp nhận message, phải cấu hình `compare-values` riêng.

Cần cung cấp `eventId` có giá trị String hợp lệ; nếu header vắng hoặc SpEL gây lỗi, message có thể thất bại trong bước chọn key/value trước khi handler chạy.

### Các attribute loại trừ nhau

| Attribute | Chức năng | Quan hệ |
| --- | --- | --- |
| `selector` | Bean `MessageSelector` do ứng dụng tự cung cấp | Không dùng cùng `metadata-store` và `key-strategy`/`key-expression` |
| `key-expression` | SpEL tạo idempotent key | Không dùng cùng `key-strategy` |
| `key-strategy` | Bean `MessageProcessor` tạo key | Không dùng cùng `key-expression` |
| `value-expression` | SpEL tạo value | Không dùng cùng `value-strategy` |
| `value-strategy` | Bean `MessageProcessor` tạo value | Không dùng cùng `value-expression` |
| `compare-values` | Bean `BiPredicate<String,String>` so sánh old/new | Chỉ dùng khi value có ý nghĩa so sánh |
| `throw-exception-on-rejection` | Ném lỗi khi duplicate bị từ chối | Cần hiểu ảnh hưởng rollback/retry |

XML fragment dùng `int` namespace và schema đúng Spring Integration version. Đối với Spring Boot/Java configuration, có thể dùng Java DSL hoặc annotation, không bắt buộc dùng XML.

## 6. Java configuration tương đương: `MetadataStoreSelector`

Java API sử dụng `MessageProcessor<String>` thay cho viết SpEL. Điều này có lợi khi key cần validation, canonicalization, hash hoặc quy tắc nghiệp vụ phức tạp:

~~~java
ConcurrentMetadataStore metadataStore = new SimpleMetadataStore();

MetadataStoreSelector selector = new MetadataStoreSelector(
    message -> {
        Shipment shipment = (Shipment) message.getPayload();
        String tenant = (String) message.getHeaders().get("tenantId");

        if (tenant == null || tenant.isBlank() ||
                shipment.getShipmentId().isBlank()) {
            throw new IllegalArgumentException("Missing stable identity");
        }

        return "shipment:v1:" + tenant + ":" + shipment.getShipmentId();
    },
    metadataStore
);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
advice.setDiscardChannelName("nullChannel");
~~~

Đoạn trên minh họa **logic chính**; các type `Shipment`, import và Spring bean wiring nằm ở ví dụ hoàn chỉnh mục 7. So sánh:

| XML SpEL | Java callback |
| --- | --- |
| `key-expression="'shipment:v1:' + headers['tenantId'] + ':' + payload.shipmentId"` | `message -> "shipment:v1:" + tenant + ":" + shipment.getShipmentId()` |
| Ngắn gọn, phù hợp công thức đơn giản | Dễ đặt breakpoint, validate input và viết test đơn vị |
| SpEL sử dụng evaluation context của framework | Java compiler kiểm tra method/type tốt hơn |
| Cấu hình thông qua XML attributes | Đăng ký bean selector/interceptor qua `@Configuration` |

Hai cách cùng phục vụ **chọn idempotent key**. Nếu cần giữ một công thức chung giữa XML và Java, có thể đặt logic canonicalization vào bean/service riêng và tham chiếu theo cách được hỗ trợ. Không chạy cả hai interceptor trên một endpoint trừ khi chủ đích muốn hai lớp kiểm tra khác nhau.

## 7. Ví dụ Java hoàn chỉnh: nhận shipment, bỏ duplicate

Ví dụ Java 17+, Spring Boot tương thích Spring Integration. Đặt toàn bộ code vào file `MetadataKeyDemoApplication.java` thuộc package `demo.integration`. Cần dependency Spring Integration Core hoặc `spring-boot-starter-integration` tương thích và component scan package này.

~~~java
package demo.integration;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IdempotentReceiver;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class MetadataKeyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataKeyDemoApplication.class, args);
    }

    @Bean("shipments")
    MessageChannel shipments() {
        return new DirectChannel();
    }

    @Bean("shipmentMetadataStore")
    ConcurrentMetadataStore shipmentMetadataStore() {
        return new SimpleMetadataStore();
    }

    @Bean("shipmentIdempotentAdvice")
    IdempotentReceiverInterceptor shipmentIdempotentAdvice(
            @Qualifier("shipmentMetadataStore") ConcurrentMetadataStore store) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> {
                    Shipment shipment = (Shipment) message.getPayload();
                    String tenant = Objects.toString(
                            message.getHeaders().get("tenantId"), "");

                    if (tenant.isBlank() || shipment.id().isBlank()) {
                        throw new IllegalArgumentException(
                                "tenantId and shipment.id are required");
                    }

                    return "shipment:v1:" + tenant + ":" + shipment.id();
                },
                store
        );

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);
        advice.setDiscardChannelName("nullChannel");
        return advice;
    }

    @Bean
    ApplicationRunner produce(
            @Qualifier("shipments") MessageChannel input,
            @Qualifier("shipmentMetadataStore") ConcurrentMetadataStore store) {

        return args -> {
            send(input, "shop-1", "SHP-101");
            send(input, "shop-1", "SHP-101"); // duplicate
            send(input, "shop-2", "SHP-101"); // tenant khác

            System.out.println("storedKey="
                    + store.get("shipment:v1:shop-1:SHP-101"));
        };
    }

    private static void send(
            MessageChannel input, String tenant, String shipmentId) {

        Message<Shipment> message = MessageBuilder
                .withPayload(new Shipment(shipmentId))
                .setHeader("tenantId", tenant)
                .setHeader("traceId", "trace-" + tenant + "-" + shipmentId)
                .build();
        input.send(message);
    }
}

// Record nghiệp vụ minh họa, giữ package-private trong cùng file.
record Shipment(String id) { }

@MessageEndpoint
class ShipmentEndpoint {

    private final AtomicInteger processed = new AtomicInteger();

    @ServiceActivator(inputChannel = "shipments")
    @IdempotentReceiver("shipmentIdempotentAdvice")
    public void handle(Shipment shipment) {
        System.out.println("PROCESS #" + processed.incrementAndGet()
                + " shipment=" + shipment.id());
    }
}
~~~

Kết quả về mặt hành vi:

~~~text
PROCESS #1 shipment=SHP-101
PROCESS #2 shipment=SHP-101
storedKey=<chuỗi timestamp đã lưu>
~~~

**Hai lần PROCESS** ở trên tương ứng `shop-1` lần đầu và `shop-2` lần đầu. Bản duplicate thứ hai của `shop-1` không đến handler. Vì bản in chỉ có `shipmentId`, log không hiển thị tenant; trong môi trường thật hãy log cả tenant hoặc trace ID để phân biệt.

`storedKey` không được mặc định là `null`: ở lần chấp nhận đầu tiên, `MetadataStoreSelector` đã đặt một value cho key. Value mặc định dựa trên timestamp header và có thể thay đổi giữa các message/chương trình. Demo chủ yếu xác nhận **key tồn tại**, không dựa vào format value làm contract nghiệp vụ.

**Giới hạn có chủ đích:** `SimpleMetadataStore` là bộ nhớ cục bộ của tiến trình. Demo cho thấy dedup trong cùng một lần chạy, nhưng không chứng minh ngăn duplicate khi hai ứng dụng chạy song song hoặc sau restart.

### Dùng `@IdempotentReceiver` hoặc Java DSL

`@IdempotentReceiver("shipmentIdempotentAdvice")` khai báo trên cùng method mang annotation messaging, ví dụ `@ServiceActivator`. Tên phải khớp bean `IdempotentReceiverInterceptor` trong Spring context.

Với Java DSL, có thể thêm interceptor tại endpoint:

~~~java
@Bean
IntegrationFlow shipmentFlow(
        ShipmentService service,
        IdempotentReceiverInterceptor shipmentIdempotentAdvice) {

    return IntegrationFlow.from("shipments")
            .handle(service, "handle",
                    e -> e.advice(shipmentIdempotentAdvice))
            .get();
}
~~~

Đây là **phương án thay thế** cho `@MessageEndpoint` trong demo, cần bean `ShipmentService`/imports. Không chạy đồng thời cả hai consumer trên cùng `DirectChannel` nếu bạn muốn mỗi message được xử lý đúng một lần bởi một endpoint.

## 8. Selector chấp nhận, loại bỏ hay đánh dấu duplicate?

Khi `MetadataStoreSelector` chọn một key:

1. Tính key từ message.
2. Tính value từ message (mặc định từ timestamp header hoặc strategy riêng).
3. Gọi cập nhật nguyên tử qua `ConcurrentMetadataStore.putIfAbsent(key, value)`.
4. Nếu key **chưa có**: ghi key/value và trả `true`.
5. Nếu key **đã có**: thường trả `false`; có thể dùng `compareValues` để chấp nhận value mới theo quy tắc thay thế.

`IdempotentReceiverInterceptor` xử lý kết quả `false` như sau:

| Cấu hình interceptor | Khi selector trả `false` | Handler có được gọi không? |
| --- | --- | --- |
| Không `discardChannel`, không ném lỗi | Tạo message có header `duplicateMessage = true` | **Có**; downstream cần tự quyết định |
| `discardChannel = "nullChannel"` | Chuyển duplicate sang sink để bỏ qua | **Không** |
| `discardChannel = "duplicates"` | Chuyển duplicate sang kênh để ghi nhận/điều tra | **Không** (consumer duplicate chạy riêng) |
| `throwExceptionOnRejection = true` | Ném `MessageRejectedException` theo contract | **Không**; cần lưu ý rollback, retry |
| Có discard channel **và** throw on rejection | Gửi duplicate sang discard, sau đó vẫn có thể ném exception | **Không**; tránh cấu hình mơ hồ |

Header `duplicateMessage` là **tín hiệu của idempotent interceptor**; nó không mặc định có sẵn trên mọi message. Dùng `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE` hoặc tên header do framework định nghĩa thay vì tự chế một string không khớp.

Cần phân biệt hai chính sách:

- **Detect only:** vẫn gửi duplicate tới handler, handler đọc cờ và bỏ tác vụ không idempotent nếu cần. Phù hợp khi muốn downstream biết event trùng để thực hiện audit.
- **Reject/discard:** loại duplicate trước handler, đơn giản hơn khi message trùng không nên kích hoạt nghiệp vụ. Cần đo discard và đảm bảo nghiệp vụ đã xử lý xong đối với key đầu tiên.

## 9. `value-expression` và `compareValues`: một key có thể đại diện tiến độ

Đôi khi mỗi record riêng không cần một key. Ví dụ poller/splitter xử lý file có 10.000 dòng: dùng `fileName` làm key, `lineNumber` làm value để nhớ dòng cuối đã chấp nhận.

~~~text
key   = "file:v1:orders-2026-11-22.csv"
value = "125"

message line 126 -> compare old=125, new=126 -> accept, replace
message line 124 -> compare old=126, new=124 -> reject
~~~

Ví dụ Java minh họa:

~~~java
ConcurrentMetadataStore store = new SimpleMetadataStore();

MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> "file:v1:" + message.getHeaders().get("fileName"),
        message -> String.valueOf(message.getHeaders().get("lineNumber")),
        store
);

selector.setCompareValues((oldValue, newValue) -> {
    long oldLine = Long.parseLong(oldValue);
    long newLine = Long.parseLong(newValue);
    return newLine > oldLine;
});
~~~

`compareValues` nhận `BiPredicate<String, String>`, tham số **thứ nhất là value cũ**, thứ hai là value mới. Khi predicate chấp nhận, selector có thể thay value bằng cập nhật nguyên tử theo implementation và tiếp tục nhận message. Logic này hữu ích khi *chỉ có một tiến độ tăng dần*.

**Cảnh báo quan trọng về thứ tự:** nếu các dòng được xử lý song song hoặc có khả năng đến sai thứ tự, nhận dòng 126 trước có thể làm dòng 125 bị xem là cũ và bị bỏ qua **dù chưa xử lý**. Chỉ dùng mô hình high-water mark khi nguồn, consumer và chính sách xử lý bảo đảm thứ tự hoặc việc bỏ qua giá trị thấp hơn là hợp lệ.

Một lựa chọn khác là dùng key `fileName + lineNumber` để theo dõi từng dòng, nhưng số lượng key tăng theo số dòng. Có thể cân nhắc retention, group/correlation và chiến lược nén tiến độ phù hợp với volume.

### Đừng nhầm `value-expression` với key

Trong ví dụ line number:

- `key-expression` chọn **đơn vị nhận dạng** (tên file).
- `value-expression` chọn **giá trị tiến độ** (số dòng).
- `compare-values` quyết định **có được tăng tiến độ** hay không.

Nếu không có `compareValues`, key file đã tồn tại thường khiến các dòng tiếp theo bị đánh là duplicate dù line number khác; riêng việc đặt `value-expression` không tự giải quyết bài toán cập nhật.

## 10. Cạnh tranh giữa consumer: vì sao cần `ConcurrentMetadataStore`?

Giả sử hai executor workers nhận cùng logical event gần như đồng thời:

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant S as ConcurrentMetadataStore
    participant W2 as Worker 2
    W1->>S: putIfAbsent("shipment:shop1:SHP101", value1)
    W2->>S: putIfAbsent("shipment:shop1:SHP101", value2)
    S-->>W1: null (đặt thành công)
    S-->>W2: value1 (đã có)
    W1->>W1: handler xử lý
    W2->>W2: duplicate -> discard / mark
~~~

Nếu code chỉ thực hiện `if (store.get(key) == null) store.put(key, value)` thì hai worker có thể **đồng thời thấy key chưa tồn tại** rồi cùng xử lý. `ConcurrentMetadataStore.putIfAbsent` cung cấp contract atomic insert.

Tuy nhiên tính atomic **trong toàn hệ thống** phụ thuộc backend:

| Backend | Phạm vi đồng bộ | Khuyến nghị |
| --- | --- | --- |
| `SimpleMetadataStore` | Trong cùng ứng dụng/JVM | Phù hợp unit test và một tiến trình |
| `PropertiesPersistingMetadataStore` | Bộ nhớ/file theo cấu hình | Không mặc định coi file chung trên nhiều node là distributed lock |
| `JdbcMetadataStore` | Dữ liệu qua DB, query/transaction/unique constraint | Kiểm tra DDL, transaction manager và hành vi nhiều instance |
| `RedisMetadataStore` | Redis khi cùng key namespace/instance | Kiểm tra availability, eviction/TTL và cấu hình failover |
| `MongoDbMetadataStore`/các backend khác | Theo khả năng atomic của provider | Kiểm thử conflict, connection failure, retention |
| Store tùy biến | Theo implementation `putIfAbsent`/`replace` | Test concurrency, restart, lỗi mạng |

Một store chỉ implement `MetadataStore` mà không có atomic method phù hợp có thể **không đủ** cho idempotent receiver dưới concurrency.

### Ghi key trước hay sau business commit?

`MetadataStoreSelector` ghi key khi message được **chấp nhận**, trước khi handler thực hiện thành công. Điều này tạo ra rủi ro:

~~~text
putIfAbsent(key) -> thành công
handler gọi DB/API -> thất bại
message được retry với cùng key -> selector thấy duplicate -> chặn lại
~~~

Vì vậy interceptor này bảo vệ bước **nhận/đánh dấu đã thấy**, không đảm bảo toàn bộ giao dịch nghiệp vụ đã hoàn thành. Với công việc quan trọng, cân nhắc:

- **Inbox table** có unique constraint theo event ID và transaction cùng DB với business effects.
- State machine `RECEIVED → PROCESSING → COMPLETED/FAILED` để phân biệt "đã thấy" với "đã xử lý xong".
- Recovery hoặc compensation rõ ràng khi key đã ghi nhưng handler thất bại.
- TTL/lease/retry state có giới hạn trong hệ thống hỗ trợ, tránh khóa vĩnh viễn một việc chưa hoàn thành.
- Idempotency key được gửi sang external API; nếu API không hỗ trợ thì cần cơ chế đối soát kết quả.

Không tự ý `store.remove(key)` trong mọi catch: nếu worker khác đã xử lý hoặc cập nhật key, xóa vội có thể mở cửa cho duplicate. Khi cần điều kiện xóa/thay, thiết kế ownership/version và atomic operation thích hợp.

## 11. Retry, transaction, poller và executor trong flow thực tế

Metadata selection xảy ra lúc endpoint xử lý message. Vị trí của endpoint trên các loại channel quyết định thread, error handling và mức độ trùng lặp có thể quan sát.

| Ranh giới | Điều xảy ra ở runtime | Điều phải kiểm tra |
| --- | --- | --- |
| `DirectChannel` | Idempotent advice và handler thường chạy đồng bộ trên thread gọi `send()` | Exception có đi ngược sender không, transaction có bao cả store và business DB không |
| `ExecutorChannel` | Selector/handler chạy ở worker thread sau async handoff | Error flow của worker, pool saturation và shared store giữa workers |
| `QueueChannel` + poller | Selector được gọi khi message được lấy ra xử lý | Thời điểm message bị dequeue, transaction và khả năng redelivery |
| Broker inbound adapter | Broker có thể redeliver cùng event khi ack thất bại | Giữ key ổn định qua delivery, consistency của ack và business state |
| `IntegrationFlow` đăng ký động | Endpoint start/stop theo lifecycle của flow | Bean store/advice có còn sống sau stop/remove, key namespace có được dùng lại không |

### Thứ tự advice và retry

Giả sử đặt retry và idempotent advice cùng một endpoint:

~~~text
Retry bên ngoài -> mỗi attempt có thể đi qua idempotent selector
Idempotent bên ngoài -> mỗi logical message được xét key trước khi retry phía trong
~~~

Khi idempotent selector ở **bên trong retry**, key đã ghi trong attempt đầu tiên có thể khiến attempt kế tiếp bị coi là duplicate. Khi selector ở **bên ngoài retry**, một vòng retry bên trong có thể chạy nhiều attempt nhưng chỉ đánh dấu key một lần, tuy nhiên nếu tất cả attempt đều thất bại thì key vẫn tồn tại.

Do đó thứ tự advice phải được quyết định cùng **commit/recovery contract**. Kết hợp transaction advice, poller retry và broker redelivery càng cần fault injection ở đúng ranh giới. Không mặc định một thứ tự advice tạo ra "exactly once".

### Transaction

`ConcurrentMetadataStore` không tự động nhập transaction với business database. Ví dụ metadata ở Redis, business data ở JDBC: rollback JDBC không tự xóa key Redis. Ngay cả khi cả hai dùng JDBC, phải xác nhận transaction manager/DataSource, isolation và thời điểm gọi store thực sự tham gia transaction phù hợp.

Nếu metadata write được commit riêng trước khi handler lỗi, việc dùng `@Transactional` trên handler không bảo đảm key được rollback. Hãy kiểm tra bằng trạng thái store và DB sau lỗi, không chỉ bằng log rollback.

### Correlation và message identity

Các header `correlationId`, `sequenceNumber`, `sequenceSize` rất hữu ích khi splitter/aggregator cần nối message cùng nhóm, nhưng thường **không đủ** để nhận dạng từng sự kiện độc lập. Hai phần trong cùng group có thể chia sẻ correlationId; dùng nó làm key duy nhất sẽ bỏ mất phần sau. Key idempotency cho splitter có thể cần `correlationId + sequenceNumber`, nếu sequence ổn định theo cùng logical group.

`MessageHeaders.ID` có thể thay đổi khi message được tái tạo; đối với redelivery từ broker, hãy chọn application eventId/operationId được producer giữ ổn định. Không dùng tên thread, timestamp nhận message hoặc UUID mới phát sinh ở mỗi lần nhận làm idempotent key.

## 12. Lưu bền vững, khởi động lại và vòng đời key

Nếu không cấu hình persistent store, một ứng dụng dùng `SimpleMetadataStore` sẽ mất metadata sau restart. Điều này có thể dẫn tới xử lý trùng những message được broker gửi lại.

~~~text
T0: app A chấp nhận eventId=evt-7 -> key nằm trong memory A
T1: app A restart -> memory bị xóa
T2: broker redeliver evt-7 -> key chưa có -> app A nhận như mới
~~~

Để giữ dấu qua restart, chọn backend thích hợp (`JdbcMetadataStore`, `RedisMetadataStore`, `MongoDbMetadataStore` hoặc implementation có persistence theo nhu cầu). Cần quan tâm schema DB, credential, namespace, flush/commit, backup, startup recovery và tính sẵn sàng.

`PropertiesPersistingMetadataStore` có thể lưu ra file, nhưng mặc định thường ghi state khi context đóng bình thường hoặc khi gọi `flush()` theo contract. Không giả định crash đột ngột vẫn giữ được mọi key chưa flush.

### Retention và TTL

Một key được ghi mãi làm store tăng không giới hạn. Nếu ứng dụng định nghĩa khoảng chống trùng 30 ngày, cần có cơ chế expiration/cleanup được thiết kế:

- **Thời gian chống trùng** phải dài hơn cửa sổ broker redelivery/replay được phép, nếu không duplicate cũ có thể lọt qua khi key bị xóa sớm.
- **Xóa nhầm** một key khi handler vẫn đang xử lý có thể khiến worker thứ hai nhận lại cùng event.
- Khi dữ liệu đã expire, ứng dụng phải có chính sách rõ là xem event cũ như mới, đưa vào review hay từ chối dựa vào event age.
- Nếu dùng backend có TTL, hãy xác nhận TTL và eviction policy của chính backend; không giả định mọi `MetadataStore` đều có TTL tự động.

Giảm cardinality bằng `compareValues` phù hợp với một số luồng tiến độ tăng dần nhưng không thể thay thế từng-event key ở mọi bài toán.

## 13. Debug sai expression, sai key hoặc duplicate lọt qua

| Hiện tượng | Nguyên nhân thường gặp | Hướng xác minh |
| --- | --- | --- |
| Key rỗng, không thấy trong store | Thiếu header, null payload property, SpEL evaluate lỗi | Log loại payload/header có kiểm soát; test expression với message mẫu |
| Message thuộc hai tenant bị xem là trùng | Key thiếu tenant hoặc normalization làm collision | So sánh computed key (có mask), key namespace |
| Mọi message sau message đầu đều bị chặn | `key-expression` trả constant hoặc cùng ID cho toàn bộ flow | Đánh giá expression bằng dữ liệu nhiều event khác nhau |
| Duplicate vẫn đến handler | Không có `discardChannel` và interceptor chỉ đặt `duplicateMessage=true` | Kiểm tra header duplicate và cấu hình discard |
| Duplicate bị chặn sau một lần handler lỗi | Key được ghi trước commit, retry dùng lại key | Kiểm tra timeline metadata write → handler → transaction |
| Restart khiến event cũ chạy lại | Dùng `SimpleMetadataStore` hoặc store chưa flush/bền vững | Test stop/restart cùng backing store |
| Hai instance cùng chạy một event | Mỗi instance dùng store khác hoặc atomic operation sai | Xác nhận shared `ConcurrentMetadataStore`, thử concurrent send |
| `compareValues` bỏ qua event hợp lệ | High-water mark với message out-of-order | Dùng per-event key hoặc bắt buộc thứ tự xử lý |
| Log chứa PII trong key | Nối raw email/customer identifier vào key | Dùng opaque ID hoặc keyed hash có version phù hợp |
| Store lớn và lookup chậm | Không có retention, khóa quá dài, index/connection không phù hợp | Đo key count, p95 lookup, backend index và purge |

### Quy trình quan sát có thể làm ngay

1. Lấy **hai message cụ thể**: một phải được nhận, một phải bị xem là trùng; ghi logical event ID, tenant, operation, payload type.
2. Tính **key kỳ vọng** theo contract bên ngoài handler.
3. Kiểm tra expression/callback thực tế cho đúng message root: `payload`, `headers`.
4. Ghi kết quả `putIfAbsent` hoặc quyết định selector (có mask dữ liệu nhạy cảm), và xác định metadata value.
5. Kiểm tra interceptor có `discardChannel` hay chỉ gắn header `duplicateMessage`.
6. Đặt lỗi giả lập **sau khi selector chấp nhận nhưng trước business commit**, xác nhận message retry sẽ ra sao.
7. Lặp kiểm thử với hai consumer đồng thời, sau restart và trên hai instance chung store.
8. Theo dõi metrics: `dedupe.accepted`, `dedupe.duplicate`, `dedupe.selector.error`, store latency, số key và retry/redelivery count.

**Không tag metric theo eventId, orderId hoặc full metadata key** vì cardinality quá lớn. Có thể dùng nhãn `endpoint`, `operation`, `tenantTier` (nếu cardinality thấp và được phép), `result` và `storeType`; event ID đặt trong trace/log theo chính sách bảo mật.

## 14. Bảo mật và hiệu năng của key expression

Expression chạy trong luồng tiếp nhận message; nếu nó gọi database hoặc truy vấn bên ngoài, độ trễ có thể bị nhân lên trên số message và làm nghẽn `DirectChannel`, poller hoặc executor.

Các nguyên tắc:

- Giữ key expression **deterministic và nhẹ**. Đọc property/header sẵn có, tránh side effect, HTTP/DB call hoặc random.
- Nếu key cần tính hash, định nghĩa phiên bản thuật toán và normalize input trước khi hash; kiểm thử collision và encoding.
- Không đưa email, token, nội dung tài liệu hay payload nhạy cảm nguyên văn vào metadata key khi không cần.
- Không để client cung cấp **mã SpEL cần evaluate**. Client chỉ gửi dữ liệu, expression được ứng dụng cấu hình.
- Backend metadata nên có quyền truy cập tối thiểu, backup phù hợp và metric độ trễ `putIfAbsent`, `replace`.
- Không bỏ qua lỗi store availability: nếu store tạm mất kết nối, thiết kế rõ fail-open hay fail-closed; với nghiệp vụ có side effect đắt, fail-open dễ tạo duplicate, fail-closed có thể gây giảm throughput.
- Khi muốn tăng concurrency, xác nhận khóa có tính phân tán, và tránh một key quá rộng khiến toàn bộ traffic bị xem là duplicate.

### Một số phép thử hiệu năng

| Bài thử | Điều quan sát |
| --- | --- |
| 10.000 message unique | Throughput selector, latency backend, key growth |
| 10.000 message cùng key | Số handler invocation, contention và tải backend |
| Nhiều tenant có cùng business ID | Có collision hay không |
| Nhiều instance cùng nhận event | `putIfAbsent` có đảm bảo chỉ một accept trong shared store không |
| Store mất kết nối | Error flow, backpressure, retry và hành vi ack |
| Reconnect sau restart | Metadata còn hay mất, duplicate có bị xử lý lại không |

Với transaction, metadata write và business side effects nên được đo trong cùng timeline để tìm "đã ghi key nhưng chưa hoàn thành". Một bộ đếm duplicate tăng không đồng nghĩa lỗi; cần đối chiếu nguồn redelivery và số logical events.

## 15. Bài thực hành và tình huống suy luận

1. **Key cơ bản:** chạy Java demo ở mục 7; xác nhận hai message của `shop-1`/`SHP-101` chỉ xử lý một lần, còn `shop-2` vẫn được xử lý.
2. **Khóa thiếu tenant:** sửa selector thành chỉ `shipment.id()` và quan sát một tenant bị loại nhầm; khôi phục key đúng.
3. **Expression XML:** chuyển cùng công thức Java sang `key-expression` trên `<int:idempotent-receiver>`; kiểm tra literal quote và `payload.shipmentId` với POJO getter.
4. **Không discard:** tắt discard channel; kiểm tra handler nhận lại duplicate với header `duplicateMessage=true` và xử lý cờ một cách có chủ đích.
5. **Lỗi trước commit:** làm handler throw sau khi selector ghi key. Gửi lại cùng logical message; giải thích tại sao message có thể bị chặn và cách thiết kế inbox/transaction/recovery.
6. **Value progress:** thử `key=fileName`, `value=lineNumber` và `compareValues`; gửi 1, 2, 4, 3 để thấy tác động của out-of-order.
7. **Concurrency:** gửi 100 message cùng key bằng nhiều thread trong một JVM; thử tiếp hai instance với shared JDBC/Redis store theo phiên bản và cấu hình thực tế.
8. **Restart:** thay `SimpleMetadataStore` bằng persistent store và chạy lại producer trước/sau restart, kiểm chứng metadata vẫn tồn tại.
9. **Schema evolution:** thêm `eventType` vào key v2; lập kế hoạch chuyển đổi để không làm duplicate cũ lọt qua.
10. **Chẩn đoán:** tạo input thiếu `tenantId`; xác nhận không có handler side effect và lỗi selector được báo đúng error flow/transaction boundary.

### Câu hỏi tự kiểm tra

- Tại sao `headers['id']` thường là lựa chọn kém cho idempotent key?
- `key-expression` được evaluate trên object nào? Nếu payload là `String`, `payload.shipmentId` có dùng được không?
- Khác nhau giữa `key-expression` và `value-expression`? Khi nào `compareValues` thật sự cần thiết?
- Vì sao `putIfAbsent` tốt hơn cặp `get()` rồi `put()` với nhiều consumer?
- Nếu selector ghi key thành công nhưng handler bị rollback, có tự rollback metadata key không?
- Khi cấu hình không có `discardChannel`, duplicate có còn vào handler không?
- Một bộ nhớ metadata in-memory có đủ cho hai ứng dụng trên hai máy và replay sau restart không?

## 16. Nguồn tham khảo chính thức

- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): contract key–value, các backend và metadata store mặc định.
- [Spring Integration — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): `key-expression`, `value-expression`, `compare-values`, `discardChannel` và `@IdempotentReceiver`.
- [Spring Integration — SpEL](https://docs.spring.io/spring-integration/reference/spel.html): message root, `payload` và `headers`.
- [Spring Integration Javadoc — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): `putIfAbsent`, selector constructors và `compareValues`.
- [Spring Integration Javadoc — IdempotentReceiverInterceptor](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html): semantics duplicate, discard và exception.
- [Spring Integration Javadoc — ConcurrentMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html): atomic `putIfAbsent` và `replace`.
- [Spring Integration Javadoc — IdempotentReceiver annotation](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/IdempotentReceiver.html): method-level attachment.
