# Conversion lỗi trước khi handler chạy

Trong **Spring Integration runtime**, một message thường đi qua inbound adapter, channel, consumer endpoint, transformer rồi mới tới handler thực thi nghiệp vụ. Nếu bước **chuyển đổi dữ liệu (conversion)** thất bại ở phía trước handler đích, breakpoint đặt trong phương thức nghiệp vụ sẽ không được chạm tới. Từ bên ngoài, hiện tượng này dễ bị nhầm là “channel không chuyển message”, “consumer không chạy” hoặc “handler bị treo”.

Bài học thuộc chương **Conversion** của module **SPRING_INTEGRATION_RUNTIME**. Mục tiêu là tìm đúng điểm phát sinh lỗi, hiểu cách Spring Integration điều phối lỗi qua channel, endpoint, poller và executor; sau đó áp dụng transaction, retry, error flow, message store và correlation đúng ranh giới.

> **Điểm cần phân biệt:** “Handler chưa chạy” ở đây là **handler đích hoặc phương thức service nghiệp vụ chưa được gọi**. Một transformer chạy ở bước trước cũng có thể được Spring Integration triển khai như một message handler. Vì vậy, nói “không handler nào chạy” thường là kết luận sai.

## 1. Conversion có thể diễn ra ở đâu?

~~~mermaid
flowchart LR
    SRC["Nguồn bên ngoài<br/>HTTP, AMQP, Kafka, file..."]
    AD["Inbound adapter<br/>deserialize / decode"]
    CH["MessageChannel"]
    TR["Transformer<br/>payload A → B"]
    EP["Consumer endpoint<br/>resolve argument"]
    H["Handler đích<br/>business method"]
    SRC --> AD --> CH --> TR --> EP --> H
    AD -. "lỗi A" .-> ER["Error handling theo adapter"]
    TR -. "lỗi B" .-> EI["Flow exception / error channel"]
    EP -. "lỗi C" .-> EI
~~~

Sơ đồ là một flow **minh họa**: không phải integration flow nào cũng có đủ các bước và thứ tự conversion phụ thuộc adapter, cấu hình channel, endpoint và method signature. Ví dụ, endpoint có thể nhận trực tiếp từ channel mà không có transformer riêng; một channel có ràng buộc kiểu dữ liệu cũng có thể từ chối message ngay khi gửi.

| Vị trí | Ví dụ lỗi | Handler nghiệp vụ đã chạy? | Điều cần quan sát |
|---|---|---|---|
| **A. Inbound adapter / listener** | Không giải mã được body, sai serialization format, JSON không hợp lệ | Chưa | Exception ở listener/adapter, dữ liệu đầu vào thô, chính sách ACK/redelivery |
| **B. Transformer trước handler** | Không parse được JSON hoặc chuyển kiểu ngày/số | Chưa | Input/output của transformer, endpoint transformer, chuỗi nguyên nhân exception |
| **C. Trước khi gọi method handler** | Payload là <code>String</code> nhưng tham số yêu cầu DTO và không có converter phù hợp | Phương thức đích chưa chạy | Payload type, content type, cấu hình converter và method resolution |
| **Ràng buộc của channel** | Datatype channel không chấp nhận payload hiện tại, không thể chuyển đổi | Chưa tới consumer phía sau | Kiểu dữ liệu channel chấp nhận, converter dùng tại channel |
| **Bên trong handler** | Handler tự gọi <code>ObjectMapper</code> và deserialize thất bại | Đã vào handler | Stack trace có frame của phương thức handler |

Với lỗi ở **A**, có trường hợp framework chưa tạo được <code>Message&lt;?&gt;</code> hợp lệ. Với lỗi ở **B/C**, thường đã có message đi vào flow nhưng handler đích chưa được gọi. Phân biệt hai tình huống quyết định cách lấy lại payload gốc, dùng error channel và xử lý retry.

## 2. Dấu hiệu nhận biết conversion thất bại trước handler

Một số biểu hiện thường gặp:

1. Log ở inbound listener hoặc transformer ghi nhận lỗi, nhưng log đầu tiên của handler đích không xuất hiện.
2. Một endpoint phía trước nhận message; endpoint phía sau có bộ đếm xử lý bằng 0 hoặc không có dữ liệu đầu ra.
3. Exception liên quan đến <code>MessageConversionException</code>, <code>MessageTransformationException</code>, <code>MessageHandlingException</code> hay exception đặc thù của adapter. Các lớp exception **không cố định** cho mọi flow; phải đọc nguyên nhân gốc (<code>cause</code>).
4. Message có header <code>contentType</code> là JSON nhưng payload vẫn là <code>byte[]</code> hoặc <code>String</code>, trong khi handler yêu cầu một đối tượng Java.
5. Với <code>DirectChannel</code>, người gửi nhận exception ngay khi gọi <code>send()</code>; với poller hoặc executor, người gửi có thể đã hoàn thành trong khi lỗi được ghi nhận ở thread tiêu thụ.

**Không nên suy diễn từ việc breakpoint không được chạm tới.** Endpoint có thể chưa start, poller có thể chưa kích hoạt, channel có thể không có subscriber, executor có thể bị nghẽn hoặc message có thể đã được route sang flow khác. Cần chứng minh message thực sự đến bước chuyển đổi rồi mới kết luận conversion là nguyên nhân.

## 3. Tại sao có header <code>contentType</code> vẫn không tự chuyển được JSON?

Spring Messaging/Spring Integration phân biệt:

- **Payload:** giá trị thực tế trong message, chẳng hạn <code>byte[]</code>, <code>String</code>, <code>Map</code> hoặc một DTO.
- **Content type:** metadata mô tả biểu diễn dữ liệu, chẳng hạn <code>application/json</code>; bản thân header **không bảo đảm** endpoint sẽ tự deserialize.
- **Message converter:** thành phần chuyển đổi message/payload theo cơ chế được cấu hình, ví dụ converter ở adapter hoặc trong quá trình resolve tham số.
- **Transformer:** một endpoint của flow được khai báo để biến đổi payload trước endpoint tiếp theo.
- **ConversionService:** hạ tầng chuyển kiểu Java khi được thành phần tương ứng sử dụng, ví dụ <code>String</code> sang một số kiểu đơn giản; không mặc nhiên biết parse mọi JSON thành DTO tùy ý.

Giả sử endpoint đích có method:

~~~java
@ServiceActivator(inputChannel = "orders.typed")
public void accept(OrderCommand command) {
    orderService.place(command);
}
~~~

Nếu gửi <code>Message&lt;String&gt;</code> chứa <code>{"orderId":"O-17","quantity":3}</code> vào <code>orders.typed</code>, việc khai báo tham số <code>OrderCommand</code> **không đủ** để bảo đảm JSON được biến thành DTO. Method-invoking infrastructure phải có cơ chế convert phù hợp, hoặc flow phải có transformer trước đó. Nếu không, lỗi có thể xuất hiện ở bước resolve tham số và phần thân <code>accept()</code> chưa chạy.

Ngược lại, nếu payload đã là <code>OrderCommand</code> đúng kiểu, không cần thêm conversion JSON. Hãy kiểm tra **kiểu thực tế tại từng ranh giới**, không chỉ kiểu mong muốn trong phương thức.

## 4. Ví dụ: JSON sai làm handler đích không được gọi

Ví dụ dưới đây dùng Java 17+, Spring Integration Java DSL và Jackson. Flow nhận JSON dạng <code>String</code> trên <code>DirectChannel</code>, chuyển thành <code>OrderCommand</code>, rồi gọi service nghiệp vụ. Để chạy thực tế, ứng dụng cần các dependency tương ứng với Spring Integration và Jackson, cùng cấu hình Spring tạo bean <code>ObjectMapper</code>.

**Bước 1 — command và service không phụ thuộc Spring Integration:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void place(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        // Gọi repository và thực thi use case đặt hàng.
    }
}
~~~

**Bước 2 — converter được đặt rõ ràng trước service activator:**

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfig {

    @Bean(name = "orders.raw")
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    GenericTransformer<String, OrderCommand> decodeOrder(ObjectMapper mapper) {
        return json -> {
            try {
                return mapper.readValue(json, OrderCommand.class);
            } catch (JsonProcessingException ex) {
                throw new IllegalArgumentException("JSON đơn hàng không hợp lệ", ex);
            }
        };
    }

    @Bean
    IntegrationFlow orderFlow(
            @Qualifier("orders.raw") MessageChannel input,
            GenericTransformer<String, OrderCommand> decodeOrder,
            OrderService service) {
        return IntegrationFlow.from(input)
            .transform(decodeOrder)
            .handle(service, "place")
            .get();
    }
}
~~~

Các kiểu chính ở đây thuộc <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.transformer.GenericTransformer</code>, <code>org.springframework.integration.channel.DirectChannel</code> và <code>org.springframework.messaging.MessageChannel</code>. <code>JsonProcessingException</code> thuộc Jackson, <code>@Qualifier</code> thuộc Spring Beans, còn <code>@EnableIntegration</code> thuộc Spring Integration.

**Bước 3 — gửi dữ liệu qua channel:**

~~~java
Message<String> valid = MessageBuilder
    .withPayload("{\"orderId\":\"O-17\",\"quantity\":3}")
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();

inputChannel.send(valid); // convert thành OrderCommand rồi gọi service.place(...)

Message<String> invalid = MessageBuilder
    .withPayload("{\"orderId\":\"O-17\",\"quantity\":")
    .build();

inputChannel.send(invalid); // conversion thất bại; service.place(...) không chạy
~~~

Trong đoạn gửi, <code>inputChannel</code> là bean <code>orders.raw</code>; <code>MessageBuilder</code> thuộc <code>org.springframework.integration.support.MessageBuilder</code>, <code>MessageHeaders</code> thuộc Spring Messaging và <code>MimeTypeUtils</code> thuộc Spring Core. JSON sai có cú pháp chưa hoàn chỉnh, nên Jackson ném exception tại <code>mapper.readValue(...)</code>. Exception được gói/lan theo đường đi của messaging endpoint; không nên dựa vào **một** kiểu exception ngoài cùng.

### Chuyện gì xảy ra khi JSON không hợp lệ?

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant C as DirectChannel
    participant T as Transformer
    participant H as OrderService
    S->>C: Message<String> (JSON sai)
    C->>T: dispatch đồng bộ
    T->>T: ObjectMapper.readValue(...)
    T--xC: exception
    C--xS: exception (có thể được wrap)
    Note over H: place() chưa được gọi
~~~

Transformer đã nhận message nhưng không tạo ra <code>OrderCommand</code>. Vì vậy, endpoint <code>.handle(service, "place")</code> không nhận được output hợp lệ, và transaction đặt trên method nghiệp vụ cũng chưa được mở qua lời gọi đó.

Lưu ý khác biệt: nếu JSON parse thành công nhưng <code>quantity = -1</code>, service **đã được gọi**, rồi mới ném lỗi validation nghiệp vụ. Không nên đưa cả hai trường hợp vào cùng chính sách xử lý “conversion error”.

## 5. Quy trình chẩn đoán theo từng ranh giới

### Bước 1 — xác định thông điệp đã đến đâu

Đọc log theo đường đi **adapter → channel → transformer → consumer endpoint → handler đích**. Tìm thời điểm gần nhất có dấu hiệu nhận hoặc chuyển message thành công. Nếu endpoint là polling consumer, xác nhận poller đang chạy và đã lấy được message. Nếu dùng <code>ExecutorChannel</code>, kiểm tra executor còn thread, queue còn capacity và có tác vụ bị từ chối hay không.

Với Spring Integration, có thể dùng metric/observation, wire tap ở ranh giới thích hợp, hoặc logging tạm thời để quan sát thông điệp. Wire tap chỉ thấy message **đã tồn tại trên channel**; nó không thể quan sát một message không được inbound adapter tạo ra vì deserialize thất bại.

### Bước 2 — xác nhận kiểu payload thực tế

Tại ranh giới trước conversion, ghi nhận các thông tin tối thiểu:

~~~java
Message<?> message = /* message đã nhận tại ranh giới */;
Object payload = message.getPayload();

log.debug("messageId={}, payloadType={}, contentType={}, correlationId={}",
    message.getHeaders().getId(),
    payload.getClass().getName(),
    message.getHeaders().get(MessageHeaders.CONTENT_TYPE),
    message.getHeaders().get("correlationId"));
~~~

Hạn chế ghi toàn bộ payload vào log vì có thể chứa dữ liệu cá nhân hoặc bí mật. Cũng không nên kết luận kiểu payload từ <code>contentType</code>: một <code>byte[]</code> JSON vẫn có kiểu Java là <code>byte[]</code>.

### Bước 3 — đi tới nguyên nhân gốc của exception

Một chuỗi nguyên nhân minh họa có thể như sau:

~~~text
MessagingException (được ném/bao bởi endpoint)
  └─ MessageTransformationException hoặc MessageConversionException
       └─ IllegalArgumentException
            └─ JsonProcessingException: unexpected end-of-input
~~~

Chuỗi thực tế thay đổi theo Spring Integration version, adapter và cách ứng dụng bọc lỗi. Đọc <code>cause</code> từ ngoài vào trong; nếu là <code>MessagingException</code>, kiểm tra <code>failedMessage</code> khi có. Nếu lỗi ở inbound adapter trước khi tạo message, <code>failedMessage</code> có thể không tồn tại: phải dựa vào log/metadata của listener và cơ chế lưu bản tin lỗi của nguồn.

### Bước 4 — kiểm tra converter có được dùng thực sự

- Đầu vào là JSON bytes hay JSON string? Adapter có chuyển thành Java object không, hay chỉ phát <code>byte[]</code>/<code>String</code>?
- Transformer có đứng **trước** endpoint nghiệp vụ không? Có nhầm kiểu input mà transformer nhận không?
- Handler có tham số <code>OrderCommand</code> nhưng flow gửi <code>String</code> hoặc <code>Map</code> không? Có converter thích hợp trong đường gọi method không?
- <code>contentType</code> có đúng và có thực sự được converter đọc không? Một header được gắn không chứng minh nó được sử dụng.
- Có mismatch schema (tên field, ngày giờ, enum, kiểu số), encoding, version DTO hoặc class không? JSON hợp lệ về cú pháp vẫn có thể sai về cấu trúc.
- Có áp dụng converter khác nhau ở môi trường test và runtime không? Có nhiều inbound adapter đi vào cùng channel nhưng phát payload không đồng nhất không?

### Bước 5 — thử lại bằng dữ liệu tối thiểu

Tạo một message hợp lệ có kiểu chính xác để xác nhận handler được gọi, sau đó thay **một** yếu tố: JSON hỏng, field sai kiểu hoặc payload đổi từ DTO thành <code>String</code>. Theo dõi xem flow hỏng ở adapter, transformer hay method argument resolution. Với flow đồng bộ, gửi trực tiếp vào channel rồi xác nhận exception; với flow bất đồng bộ, cần quan sát error handler và trạng thái xử lý cuối cùng, vì <code>send()</code> thành công không đồng nghĩa nghiệp vụ đã thành công.

## 6. Tại sao error channel không phải lúc nào cũng nhận lỗi?

Cách Spring Integration báo lỗi phụ thuộc **thread boundary** và thành phần phát sinh lỗi:

| Runtime | Khi conversion lỗi | Hướng xử lý |
|---|---|---|
| <code>DirectChannel</code> đồng bộ | Exception ở consumer thường lan trở lại thread gửi | Caller bắt lỗi hoặc nơi gửi cấu hình xử lý phù hợp |
| <code>ExecutorChannel</code> | Sender có thể hoàn tất gửi trước khi consumer lỗi ở thread khác | Quan sát error handler/channel được cấu hình cho xử lý bất đồng bộ |
| <code>QueueChannel</code> + poller | Poller lấy message rồi transformer/handler lỗi | Kiểm tra poller error handler, giao dịch nhận message và recovery |
| Inbound adapter của broker | Deserialize có thể lỗi trước khi Spring message vào flow | Kiểm tra cơ chế conversion, error handler, ACK/nack và dead-letter của **adapter cụ thể** |

Trong các thành phần bất đồng bộ hoặc polling, Spring Integration thường có cơ chế publish <code>ErrorMessage</code> lên error channel khi được cấu hình và khi hạ tầng lỗi có thể nắm được exception. Tuy nhiên, **không có bảo đảm rằng mọi lỗi trước handler đều vào một <code>errorChannel</code> toàn cục**. Lỗi giải mã trước khi tạo message có thể nằm hoàn toàn ở listener/container của broker; lỗi trong flow đồng bộ có thể ném trực tiếp về caller.

Phân biệt:

- **Exception trên luồng gọi:** caller nắm lỗi và quyết định xử lý hoặc trả lỗi cho upstream.
- **<code>ErrorMessage</code>:** một message chứa exception và, khi có, thông tin message thất bại; nó cần một cơ chế phát error và subscriber thực sự xử lý.
- **Dead-letter/quarantine:** nơi lưu payload lỗi để phân tích và sửa dữ liệu; không tự xuất hiện chỉ vì khai báo error channel.

Khi thiết kế flow, ghi rõ lỗi ở từng đoạn thuộc về ai: inbound listener, gateway caller, consumer endpoint hay poller. Cấu hình recovery tại đúng nơi **có quyền quyết định** ACK, retry hoặc chuyển bản tin hỏng sang kênh cách ly.

## 7. Retry conversion: tránh lặp vô hạn dữ liệu hỏng

Không phải conversion error nào cũng đáng retry.

| Nhóm lỗi | Ví dụ | Chiến lược thường phù hợp |
|---|---|---|
| **Deterministic / permanent** | JSON sai cú pháp, schema không được hỗ trợ, enum không hợp lệ | Không retry vô hạn; đưa bản tin vào quarantine/DLQ, báo lỗi dữ liệu |
| **Transient / environmental** | Converter phải gọi schema service ngoài đang tạm mất kết nối, cấu hình nạp động chưa sẵn sàng | Retry giới hạn, backoff, cảnh báo khi hết lượt |
| **Không rõ nguyên nhân** | Converter có lỗi code, bất tương thích phiên bản | Dừng retry ồ ạt, ghi nguyên nhân và kiểm thử tái hiện |

Nếu retry được đặt ở **handler đích** nhưng exception phát sinh ở inbound adapter hoặc transformer chạy trước đó, advice trên handler đích có thể **không bao phủ** bước conversion. Đặt chính sách tại điểm phát sinh lỗi hoặc bao quanh đúng endpoint/adapter.

Khi tích hợp với broker, cần hiểu cơ chế redelivery và ACK riêng của adapter. Một poison message có thể được nhận lại liên tục nếu container requeue mà không có giới hạn và đường dead-letter phù hợp. Với poller dựa trên message store, hành vi nhận lại phụ thuộc transaction và việc message bị remove/ack lúc nào.

Lỗi conversion xuất hiện **trước** khi service được gọi thường không kích hoạt transaction khai báo trên service đó. Nếu adapter/poller có transaction riêng, rollback ở tầng này vẫn có thể xảy ra. Không được giả định <code>@Transactional</code> trong service sẽ rollback một hoạt động nhận message đã hoàn tất ở tầng khác.

## 8. Message store, correlation và khả năng điều tra sự cố

Message store chỉ lưu được những message đã đi vào vùng lưu của flow. Nếu converter của inbound adapter thất bại **trước khi tạo message**, lưu <code>Message&lt;?&gt;</code> ở downstream store không thể khôi phục nội dung gốc. Với loại lỗi này, cần cơ chế bảo quản bản tin thô của adapter/broker (ví dụ DLQ với payload gốc) hoặc một bước nhận thô được thiết kế trước conversion, khi phù hợp yêu cầu bảo mật và lưu trữ.

Nếu message **đã tồn tại**, các metadata sau giúp điều tra:

- <code>MessageHeaders.ID</code>: định danh một message cụ thể; có thể thay đổi khi message mới được tạo trong flow.
- <code>correlationId</code>: header correlation theo hợp đồng ứng dụng/flow, hữu ích để nối các bước; không phải mọi message đều có.
- <code>contentType</code>, phiên bản schema, nguồn/partition/offset hay delivery tag: ý nghĩa và khả năng xuất hiện phụ thuộc adapter.
- Tên endpoint, channel, thread, timestamp, loại payload đầu vào và tên converter đã chạy.

Đối với aggregator/splitter, hãy phân biệt **correlation để gom nhóm message** với **khóa idempotency để ngăn side effect trùng lặp**. Khi conversion fail, log một định danh ổn định do upstream cung cấp nếu có; không dùng riêng message ID để kết luận đã hay chưa xử lý một tác vụ nghiệp vụ.

## 9. Cách thiết kế để lỗi conversion dễ khoanh vùng

Một flow thường dễ vận hành hơn khi ranh giới chuyển đổi được công khai:

~~~text
raw input channel
  → decode / validate transport format
  → typed command channel
  → business handler
  → result / reply
~~~

Tại bước decode, chuẩn hóa payload về một DTO có hợp đồng rõ ràng. Sau đó service chỉ nhận command typed và kiểm tra bất biến nghiệp vụ. Cách này giúp test độc lập parser/transformer với use case; đồng thời đặt retry/recovery đúng nơi.

**Không nên:**

~~~java
@ServiceActivator(inputChannel = "orders.raw")
public void handle(Message<String> message) {
    try {
        OrderCommand order = objectMapper.readValue(
            message.getPayload(), OrderCommand.class);
        orderService.place(order);
    } catch (Exception ex) {
        log.warn("Bỏ qua message lỗi", ex); // Endpoint có thể bị xem là thành công
    }
}
~~~

Đoạn trên vừa parse JSON vừa xử lý nghiệp vụ, lại nuốt tất cả exception. Với một số nguồn, lỗi không được lan ra có thể dẫn tới ACK bản tin dù thực tế chưa xử lý. Nên tách conversion thành transformer hoặc adapter rõ ràng, chỉ recover có chủ đích và đưa dữ liệu lỗi vào đường xử lý được giám sát.

### Kiểm thử nên bao phủ ranh giới nào?

| Kịch bản | Kiểm tra |
|---|---|
| JSON hợp lệ, đúng schema | Transformer tạo đúng DTO và handler đích được gọi một lần |
| JSON sai cú pháp | Converter/transformer báo lỗi; handler đích **không được gọi** |
| JSON hợp lệ nhưng vi phạm quy tắc nghiệp vụ | Handler **được gọi**; service phát lỗi validation |
| Payload đúng JSON nhưng sai phiên bản schema | Có thông báo lỗi rõ trường/kiểu bị sai; áp dụng chính sách dữ liệu lỗi |
| Flow qua <code>ExecutorChannel</code> hoặc poller | Error routing và retry xảy ra ở đúng thread/endpoint, không dựa vào exception từ <code>send()</code> |
| Re-delivery message lỗi | Có giới hạn retry, DLQ/quarantine phù hợp và không gây side effect trùng lặp |

Ví dụ cách kiểm thử với một Spring Integration flow dùng <code>DirectChannel</code>: đặt mock cho <code>OrderService</code>, gửi JSON hợp lệ rồi <code>verify(service).place(expected)</code>. Tiếp theo, gửi JSON thiếu dấu đóng và kiểm tra lệnh gửi ném exception, trong khi <code>verifyNoInteractions(service)</code> vẫn đúng ở case dữ liệu lỗi. Với channel bất đồng bộ, thay kiểm tra exception trực tiếp bằng một test có điều kiện chờ kết quả error handling.

## 10. Checklist chẩn đoán production

1. Xác nhận adapter đã nhận dữ liệu; xác định message đã được tạo và đưa lên channel chưa.
2. Xác định endpoint cuối cùng đã chạy và **bước conversion cụ thể** bị lỗi.
3. Ghi nhận payload type, content type, schema version, correlation ID và nguyên nhân gốc; tránh log dữ liệu nhạy cảm.
4. Xác minh converter đúng loại, đúng vị trí và có thể parse/convert dữ liệu mẫu; đừng mặc định JSON tự biến thành DTO.
5. Kiểm tra channel đồng bộ/bất đồng bộ, trạng thái consumer/poller/executor và đường đi của exception hoặc <code>ErrorMessage</code>.
6. Phân loại lỗi dữ liệu vĩnh viễn hay lỗi hạ tầng tạm thời; đặt retry, transaction và recovery tại đúng adapter/endpoint.
7. Xác thực khả năng giữ bản tin gốc để điều tra, cơ chế DLQ/quarantine, correlation và chính sách idempotency.
8. Kiểm thử trường hợp conversion thất bại **trước handler đích** và trường hợp validation thất bại **bên trong handler/service**.

**Kết luận:** Khi không thấy handler chạy, hãy lần theo **nơi Spring Integration cần đổi biểu diễn hoặc kiểu dữ liệu** trước khi gọi method đích. Lỗi ở inbound adapter, transformer, channel datatype hoặc method argument conversion có hành vi báo lỗi khác nhau. Xác định đúng ranh giới giúp tránh retry vô hạn, mất bản tin và kết luận sai về transaction, consumer hay trạng thái runtime.
