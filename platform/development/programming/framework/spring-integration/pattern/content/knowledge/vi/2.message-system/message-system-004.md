# Message ID, timestamp và correlation metadata trong Spring Integration

Trong **Message system**, một thông điệp không chỉ mang dữ liệu cần xử lý (*payload*) mà còn mang **metadata** để hệ thống biết thông điệp được tạo khi nào, đang thuộc luồng xử lý nào và liên quan đến những thông điệp nào khác. Đây là nền tảng để triển khai các **Enterprise Integration Patterns** bằng Spring Integration: Gateway, Router, Filter, Transformer, Splitter, Aggregator, retry và error channel.

Hãy hình dung một đơn hàng gồm ba dòng hàng được tách thành ba thông điệp để xử lý độc lập. Mỗi thông điệp con cần có danh tính riêng, nhưng cả ba phải được nhận ra là cùng một nhóm để `Aggregator` ghép kết quả. `id`, `timestamp` và `correlationId` giải quyết các nhu cầu khác nhau trong bài toán đó.

## 1. Cấu trúc của một Message

Spring Messaging biểu diễn thông điệp qua `org.springframework.messaging.Message<T>`, gồm hai phần:

- **Payload**: dữ liệu nghiệp vụ, chẳng hạn đơn hàng, dòng hàng hoặc kết quả xác thực.
- **Headers** (`MessageHeaders`): metadata dùng cho định tuyến, liên kết, quan sát, xử lý lỗi và quản lý luồng.

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder.withPayload("ORDER_ACCEPTED")
        .setHeader("businessOrderId", "ORD-204")
        .setHeader("eventId", UUID.randomUUID().toString())
        .build();

UUID messageId = message.getHeaders().getId();
Long timestampMillis = message.getHeaders().getTimestamp();

System.out.println("Message ID: " + messageId);
System.out.println("Created at: " + Instant.ofEpochMilli(timestampMillis));
System.out.println("Order ID: " + message.getHeaders().get("businessOrderId"));
```

Trong cấu hình tạo thông điệp thông thường, framework sinh `id` và `timestamp`. Ứng dụng thêm header nghiệp vụ như `businessOrderId` mà không cần tự cấp giá trị cho hai header hệ thống.

Các header cần phân biệt:

| Metadata | Ý nghĩa | Phạm vi sử dụng |
| --- | --- | --- |
| `id` (`MessageHeaders.ID`) | Định danh một đối tượng Message; thường là `UUID` | Theo dõi một thông điệp cụ thể |
| `timestamp` (`MessageHeaders.TIMESTAMP`) | Thời điểm Message được tạo, tính bằng mili giây từ Unix epoch | Quan sát thời điểm phát sinh Message |
| `correlationId` (`IntegrationMessageHeaderAccessor.CORRELATION_ID`) | Khóa liên kết các Message thuộc cùng một nhóm xử lý | Splitter, Aggregator và các luồng cần ghép kết quả |
| `sequenceNumber` | Vị trí của một phần tử trong chuỗi, thường bắt đầu từ `1` | Xác định thứ tự logic của Message con |
| `sequenceSize` | Tổng số phần tử được kỳ vọng trong chuỗi, nếu biết | Điều kiện hoàn tất nhóm của Aggregator |
| `businessOrderId` / `eventId` | Header nghiệp vụ do ứng dụng định nghĩa | Tra cứu đơn hàng, đối soát và chống xử lý trùng |
| `traceparent` / `traceId` | Ngữ cảnh quan sát phân tán, nếu hệ thống tracing được cấu hình | Theo dấu yêu cầu xuyên dịch vụ |

**Lưu ý:** `correlationId`, `sequenceNumber`, `sequenceSize` là các header của Spring Integration; các header này không nhất thiết xuất hiện ở mọi Message. Không nên suy ra `correlationId` từ `id` nếu một thành phần chưa thực sự thiết lập nó.

## 2. Message ID: danh tính của thông điệp

`MessageHeaders.ID` giúp nhận diện một Message trong log, ở điểm kiểm thử hoặc khi một thành phần báo lỗi. Ví dụ, một Router nhận Message có `id=M0`; Splitter tạo ra ba Message con `M1`, `M2`, `M3` và có thể dùng `M0` làm `correlationId` của cả nhóm.

```text
Message gốc:  id=M0, payload=[A, B, C]
                 |
              Splitter
                 |
     +-----------+-----------+
     |           |           |
  id=M1       id=M2       id=M3
  corr=M0     corr=M0     corr=M0
  seq=1/3     seq=2/3     seq=3/3
     |           |           |
     +-----------+-----------+
                 |
             Aggregator
```

Sơ đồ thể hiện **quan hệ logic**, không đòi hỏi các Message phải được xử lý tuần tự. Ở nhánh bất đồng bộ, Message số `3` hoàn toàn có thể hoàn thành trước Message số `1`.

Những điểm cần ghi nhớ:

1. `id` là danh tính của **Message**, không mặc nhiên là định danh của đơn hàng, sự kiện hay giao dịch.
2. Khi một thành phần giữ nguyên Message hoặc xây dựng Message mới, cách bảo toàn/tạo lại `id` phụ thuộc API và cấu hình xây dựng Message. Đừng dựa vào giả định rằng ID luôn giữ nguyên hoặc luôn đổi sau Transformer.
3. Retry có thể phát lại cùng Message, trong khi một lần nhận lại từ broker có thể tạo Message mới. Vì vậy **không dùng riêng `id` làm khóa idempotency xuyên dịch vụ**; nên dùng `eventId`, `commandId` hoặc khóa nghiệp vụ có quy ước ổn định.
4. `MessageHeaders` được thiết kế để truy cập như metadata bất biến. Muốn bổ sung header, hãy dùng `MessageBuilder` để tạo Message thay vì sửa trực tiếp bản đồ headers.

Ví dụ bổ sung một khóa theo dõi nghiệp vụ vào Message hiện có:

```java
Message<String> enriched = MessageBuilder.fromMessage(message)
        .setHeader("businessCorrelationId", "ORD-204")
        .build();
```

Trong ví dụ này, `businessCorrelationId` là **header riêng của ứng dụng**; nó không tự thay thế khóa `correlationId` mà Aggregator của Spring Integration đang sử dụng.

## 3. Timestamp: thời điểm tạo Message khác thời điểm sự kiện nghiệp vụ

`MessageHeaders.TIMESTAMP` thông thường là `Long` lưu số mili giây từ `1970-01-01T00:00:00Z`. Dùng `Instant` để đọc thời điểm theo UTC:

```java
Long createdAtMillis = message.getHeaders().getTimestamp();
if (createdAtMillis != null) {
    Instant createdAt = Instant.ofEpochMilli(createdAtMillis);
    System.out.println(createdAt);
}
```

Trong một luồng xử lý có nhiều tầng, cần phân biệt:

| Loại thời gian | Câu hỏi được trả lời | Cách biểu diễn gợi ý |
| --- | --- | --- |
| Message timestamp | Message hiện tại được tạo lúc nào? | Header `timestamp` do framework quản lý |
| Event time | Sự kiện nghiệp vụ xảy ra lúc nào? | Payload `occurredAt` hoặc header nghiệp vụ ổn định |
| Received time | Thành phần hiện tại nhận Message lúc nào? | Giá trị đo tại điểm nhận |
| Processed/completed time | Bước xử lý hoặc cả pipeline kết thúc lúc nào? | Metric, span hoặc bản ghi kết quả |

Ví dụ: khách đặt hàng lúc 10:00, sự kiện vào hàng đợi lúc 10:01 và được đọc lại lúc 10:05. Ba mốc thời gian này phục vụ ba mục đích khác nhau. Nếu dựng Message mới lúc đọc lại hàng đợi thì `timestamp` của Message mới không thay cho thời điểm khách đặt hàng.

Không nên tự ghi đè header `timestamp` để diễn đạt *event time*. Hãy khai báo rõ trường `occurredAt` (ví dụ ISO-8601 UTC), đồng thời đo thời điểm nhận và xử lý để tính độ trễ. Trong hệ thống phân tán, đồng hồ giữa máy chủ có thể lệch nhau; timestamp là dấu mốc hữu ích nhưng không phải bằng chứng tuyệt đối về thứ tự thực thi.

## 4. Correlation metadata dùng để ghép Message

**Correlation** là việc xác định những thông điệp thuộc cùng một tác vụ hoặc một nhóm kết quả. Trong Spring Integration, các header chuẩn thường liên quan trực tiếp đến Splitter và Aggregator:

- `correlationId`: mọi phần tử của cùng một nhóm có cùng khóa.
- `sequenceNumber`: thứ tự logic của phần tử trong nhóm.
- `sequenceSize`: số phần tử dự kiến khi nhóm được tách thành một chuỗi có độ dài đã biết.

Có thể đọc chúng qua `IntegrationMessageHeaderAccessor`:

```java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

void inspectFragment(Message<?> fragment) {
    Object correlationId = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.CORRELATION_ID);
    Integer sequenceNumber = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, Integer.class);
    Integer sequenceSize = fragment.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, Integer.class);

    System.out.printf("group=%s, sequence=%s/%s%n",
            correlationId, sequenceNumber, sequenceSize);
}
```

Với Splitter thông thường, Spring Integration có thể thiết lập metadata tuần tự cho các Message con, thường liên kết chúng bằng ID của Message đầu vào. Aggregator sử dụng khóa tương quan để xác định nhóm và một chiến lược giải phóng nhóm (*release strategy*) để quyết định khi nào đủ dữ liệu cho kết quả tổng hợp.

Không nên tự gán một `correlationId` cố định cho tất cả đơn hàng: khi đó các nhóm độc lập có nguy cơ bị ghép lẫn. Ngược lại, nếu mỗi Message con có một `correlationId` khác nhau thì Aggregator khó kết hợp chúng.

### Hai kiểu correlation không nên đánh đồng

**Correlation kỹ thuật** cho Aggregator: một khóa nội bộ dùng để gom các phần của một lần Splitter. **Correlation nghiệp vụ**: một khóa như `businessOrderId` để lần theo đơn hàng qua Gateway, Router, Filter và các dịch vụ khác.

Một đơn hàng có thể đi qua nhiều lần tách/gộp. Khi đó các nhóm con có thể dùng correlation kỹ thuật khác nhau nhưng vẫn mang cùng `businessOrderId`. Tương tự, trace ID theo dõi một hành trình phân tán có thể bao trùm nhiều Message và nhiều nhóm Aggregator.

## 5. Ví dụ thực hành: Splitter → WireTap → Aggregator

Ví dụ sau nhận danh sách ba dòng hàng. `Splitter` phát từng dòng thành Message riêng; `WireTap` sao chép thông điệp tới kênh kiểm tra; `Aggregator` gom các phần tử và đưa kết quả tới kênh đầu ra.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderLineFlowConfig {

    @Bean
    public DirectChannel orderLinesInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel splitAudit() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel orderLinesOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow orderLineFlow() {
        return IntegrationFlow.from("orderLinesInput")
                .split()
                .wireTap("splitAudit")
                .aggregate()
                .channel("orderLinesOutput")
                .get();
    }
}
```

Có thể gửi một Message và kiểm tra các bản ghi ở `splitAudit` bằng mã sau trong một phép thử hoặc thành phần được inject các bean kênh:

```java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

void exercise(DirectChannel orderLinesInput,
              QueueChannel splitAudit,
              QueueChannel orderLinesOutput) {

    Message<List<String>> order = MessageBuilder
            .withPayload(List.of("item-A", "item-B", "item-C"))
            .setHeader("businessOrderId", "ORD-204")
            .setHeader("eventId", UUID.randomUUID().toString())
            .setHeader("occurredAt", Instant.now().toString())
            .build();

    orderLinesInput.send(order);

    for (int i = 0; i < 3; i++) {
        Message<?> part = splitAudit.receive(1_000);
        if (part == null) {
            throw new IllegalStateException("Không nhận đủ Message con");
        }
        System.out.printf(
                "id=%s, corr=%s, seq=%s/%s, order=%s, ts=%s%n",
                part.getHeaders().getId(),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                part.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE),
                part.getHeaders().get("businessOrderId"),
                part.getHeaders().getTimestamp());
    }

    Message<?> aggregated = orderLinesOutput.receive(1_000);
    if (aggregated == null) {
        throw new IllegalStateException("Aggregator chưa tạo kết quả");
    }
    System.out.println("Aggregated payload: " + aggregated.getPayload());
}
```

Khi chạy theo luồng đồng bộ ở ví dụ này, kết quả mong đợi là:

1. Có ba Message ở `splitAudit`, mỗi Message có `id` riêng và cùng một `correlationId`.
2. Ba `sequenceNumber` lần lượt là `1`, `2`, `3`; `sequenceSize` là `3`.
3. Các Message con mang theo header nghiệp vụ `businessOrderId=ORD-204`.
4. Aggregator phát một Message chứa danh sách payload đã gom. Với cấu hình mặc định của ví dụ, kết quả là danh sách các dòng hàng.

Những giá trị `UUID` và `timestamp` cụ thể sẽ khác nhau giữa các lần chạy. Nếu thêm `ExecutorChannel` hoặc kết nối broker, không được giả định thứ tự Message **đến nơi** bằng thứ tự `sequenceNumber`.

> Khi dùng Splitter/Aggregator, hãy để framework quản lý các header tương quan theo cơ chế mặc định nếu không có yêu cầu đặc biệt. Chỉ cấu hình correlation strategy và release strategy riêng khi hiểu rõ vòng đời nhóm.

## 6. Metadata đi qua các Enterprise Integration Patterns như thế nào?

| Pattern / thành phần | Vai trò của metadata | Điều cần kiểm tra |
| --- | --- | --- |
| **Gateway** | Đưa yêu cầu từ lời gọi Java vào luồng Message; quản lý các kênh reply/error theo hợp đồng gateway | Header nghiệp vụ có được đưa vào hoặc truyền tiếp đúng không? |
| **Router** | Chọn một hoặc nhiều kênh đầu ra dựa trên payload/header | Các nhánh có giữ được khóa nghiệp vụ cần tra cứu không? |
| **Filter** | Cho đi tiếp hoặc loại bỏ Message theo điều kiện | Việc loại bỏ một phần tử có khiến nhóm Aggregator chờ thiếu phần tử không? |
| **Transformer** | Tạo payload khác hoặc Message mới | Các header cần thiết có được giữ/thiết lập đúng qua bước biến đổi không? |
| **Splitter** | Biến một Message thành nhiều Message con | Có `correlationId`, `sequenceNumber`, `sequenceSize` thích hợp không? |
| **Aggregator** | Gom các Message có cùng khóa thành kết quả nhóm | Correlation strategy, release strategy, timeout và message store đã phù hợp chưa? |
| **Retry** | Thực hiện lại bước lỗi theo chính sách | Có phân biệt một lần thử lại với một sự kiện nghiệp vụ mới không? |
| **Error channel** | Chuyển lỗi vào luồng xử lý lỗi | Có thể truy ra Message thất bại và khóa nghiệp vụ tương ứng không? |

Một số endpoint truyền tiếp chính Message đầu vào, trong khi một số endpoint tạo Message mới. Vì vậy, khi viết Transformer hoặc service tùy chỉnh, hãy kiểm tra **metadata thực tế tại đầu ra**. Việc dùng `MessageBuilder` để truyền tiếp các header cần thiết nên có quy ước rõ ràng; không sao chép mù các header hệ thống sang sự kiện nghiệp vụ độc lập.

### Khi có nhóm chưa hoàn tất

Giả sử Splitter tạo ba phần tử nhưng Filter loại bỏ phần tử thứ hai. Nếu Aggregator vẫn chờ `sequenceSize=3`, nhóm có thể không bao giờ hoàn tất theo điều kiện mặc định. Tùy yêu cầu, cần thiết kế một trong các hướng: lọc trước khi chia, cập nhật logic phát thông điệp, quy định release strategy cho kết quả một phần hoặc đặt cơ chế timeout/expired group và xử lý thông điệp chưa hoàn tất.

Đối với luồng dài hoặc có broker, cần xem xét **MessageGroupStore** phù hợp để lưu nhóm, xử lý khởi động lại, thông điệp đến muộn và dọn nhóm hết hạn. `correlationId` chỉ là khóa gom nhóm; nó tự thân không bảo đảm xử lý đúng một lần, dữ liệu bền vững hay thứ tự đến.

## 7. Thiết kế metadata xuyên các dịch vụ

Một ứng dụng thường cần song song ba lớp định danh:

```text
traceId                  --> Theo dõi một hành trình xuyên dịch vụ
businessOrderId / eventId--> Theo dõi thực thể và sự kiện nghiệp vụ
correlationId            --> Gom một nhóm Message trong integration flow
message.id               --> Nhận diện một Message cụ thể
```

Ví dụ khi xử lý đơn hàng `ORD-204`, tất cả bước có thể gắn cùng `businessOrderId`, nhưng mỗi Message có thể mang `id` riêng, mỗi nhóm Splitter có `correlationId` riêng và mỗi request phân tán có trace context riêng. Không dùng một giá trị duy nhất cho mọi mục đích trừ khi đó là quyết định thiết kế có kiểm soát.

Khi qua HTTP, Kafka, AMQP hoặc hệ thống bên ngoài, header không mặc nhiên được giữ nguyên: adapter/header mapper, cấu hình serialization và quy định giao thức quyết định những gì đi tiếp. Hãy liệt kê rõ metadata bắt buộc tại ranh giới, đặc biệt `eventId`, khóa nghiệp vụ, `occurredAt` và trace context. Tránh phụ thuộc vào một Spring Integration `correlationId` chỉ có ý nghĩa nội bộ nếu dịch vụ bên kia không sử dụng cùng quy ước.

Để chống xử lý trùng, có thể lưu một khóa idempotency ổn định (chẳng hạn `eventId`) cùng trạng thái xử lý trong kho dữ liệu có khả năng kiểm tra nguyên tử. Cùng một sự kiện được phát lại phải giữ nguyên khóa này; Message ID mới không biến nó thành sự kiện nghiệp vụ mới.

## 8. Logging, monitoring và xử lý sự cố

Một log theo cấu trúc có thể ghi các trường sau tại điểm bắt đầu/kết thúc endpoint:

```json
{
  "stage": "aggregate-input",
  "messageId": "<uuid-cua-message>",
  "messageTimestamp": "<epoch-millis>",
  "correlationId": "<khoa-nhom>",
  "sequenceNumber": 2,
  "sequenceSize": 3,
  "businessOrderId": "ORD-204",
  "eventId": "<khoa-su-kien>",
  "outcome": "accepted"
}
```

Log nên có tên endpoint, kết quả, thời lượng xử lý và các khóa dùng để tra cứu. Thay vì log toàn bộ payload, chọn những trường cần thiết và tránh ghi dữ liệu nhạy cảm. Metrics nên đo tổng số Message, lỗi, retry, thời gian chờ Aggregator, số nhóm chưa hoàn tất và số nhóm hết hạn; tracing ghi nhận các nhánh xử lý khi hạ tầng tracing được bật.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Aggregator chờ mãi | Thiếu phần tử, sai `sequenceSize`, Filter bỏ phần tử hoặc release strategy không khớp | Đối chiếu `correlationId`, dãy `sequenceNumber`, timeout và nhóm đang lưu |
| Kết quả gộp lẫn đơn hàng | Dùng một `correlationId` cố định hoặc khóa bị trùng | Kiểm tra nguồn cấp correlation key và phạm vi duy nhất của mỗi nhóm |
| Các Message liên quan không được gom | `correlationId` bị đổi hoặc mất qua Transformer/adapter | Kiểm tra header tại từng ranh giới và chiến lược correlation |
| Log không nối được luồng xuyên dịch vụ | Chưa truyền business key hoặc trace context qua adapter | Kiểm tra header mapper, định dạng và nơi khôi phục context |
| Xử lý nghiệp vụ lặp | Dùng Message ID làm dedup key; nhận lại cùng sự kiện với Message ID mới | Kiểm tra idempotency key và thao tác ghi kết quả nguyên tử |
| Timestamp cho thấy thứ tự bất thường | Tạo Message ở các thời điểm khác nhau, xử lý song song hoặc lệch đồng hồ | Phân biệt event time, message time, receive time và trace span |

Khi xử lý lỗi, nếu nhận `MessagingException`, có thể xem `getFailedMessage()` khi thông tin đó tồn tại để truy ngược `id`, `correlationId` và khóa nghiệp vụ. Không giả định mọi lỗi đều mang đầy đủ Message gốc; điều này phụ thuộc nơi lỗi phát sinh và cách đóng gói lỗi.

## 9. Kiểm thử metadata đúng hành vi

Một bài kiểm thử đủ ý nghĩa cho luồng ở mục 5 nên xác minh cả nội dung lẫn metadata:

1. **Message ban đầu:** `getHeaders().getId()` và `getHeaders().getTimestamp()` có giá trị; `eventId`, `businessOrderId`, `occurredAt` được gắn đúng.
2. **Sau Splitter:** nhận đúng ba Message, mỗi Message có ID; tất cả chia sẻ một `correlationId`; tập `sequenceNumber` bằng `{1, 2, 3}` và mọi `sequenceSize` bằng `3`.
3. **Sau Aggregator:** nhận một kết quả nhóm đúng ba dòng hàng, không trộn với nhóm của đơn hàng thứ hai.
4. **Kịch bản mất phần tử:** cố ý bỏ một Message và xác minh ứng dụng xử lý nhóm chưa hoàn tất theo chính sách đã chọn.
5. **Kịch bản xử lý lại:** phát lại cùng `eventId` qua một Message khác và xác minh cơ chế idempotency không tạo tác dụng nghiệp vụ lặp.
6. **Kịch bản qua adapter:** kiểm tra những header bắt buộc vẫn được bảo toàn khi sang dịch vụ hoặc broker.

Không nên viết test cứng vào giá trị UUID hoặc timestamp cụ thể, vì đây là metadata được tạo tại thời điểm chạy. Hãy kiểm tra kiểu dữ liệu, tính hiện diện, quan hệ giữa các Message và kết quả của toàn luồng.

## 10. Những nguyên tắc áp dụng khi thiết kế flow

- Dùng **Message ID** để theo dõi một Message cụ thể; dùng **eventId/commandId** ổn định cho deduplication và idempotency.
- Dùng **timestamp của Message** cho quan sát thời điểm tạo Message; dùng **event time** riêng cho thời gian nghiệp vụ.
- Dùng **correlationId** nhất quán trong phạm vi một nhóm cần Aggregator gom; giữ **business correlation key** khi cần lần theo toàn giao dịch.
- Khi dùng **Splitter, Filter, Router, Transformer, Aggregator**, kiểm tra tác động của từng bước đến header và số phần tử kỳ vọng.
- Với xử lý song song, retry và broker, thiết kế rõ **group completion, timeout, persistence, duplicate handling**; correlation metadata một mình không giải quyết các vấn đề này.
- Ghi log và kiểm thử từ đầu luồng tới cuối luồng bằng các khóa liên kết đủ rõ để có thể lần theo từng Message và từng tác vụ nghiệp vụ.

Hiểu đúng ranh giới giữa `id`, `timestamp`, `correlationId` và `sequenceNumber` giúp một flow Spring Integration dễ mở rộng, quan sát và xử lý lỗi hơn, đặc biệt khi các Message được tách, đi qua nhiều nhánh và được ghép lại thành kết quả.
