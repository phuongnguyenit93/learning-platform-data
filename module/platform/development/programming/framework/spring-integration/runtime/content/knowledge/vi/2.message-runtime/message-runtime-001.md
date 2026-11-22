# Message immutable và dữ liệu được truyền qua runtime

Trong Spring Integration, một message là đơn vị dữ liệu được truyền giữa các thành phần của một integration flow. Message mang theo **payload** (nội dung nghiệp vụ) và **headers** (metadata phục vụ định tuyến, tương quan, phản hồi, xử lý lỗi và quan sát runtime). Hiểu đúng tính immutable của message giúp ta dự đoán dữ liệu nào được chia sẻ giữa các endpoint, tránh lỗi tranh chấp khi chạy đa luồng và thiết kế retry, splitter, aggregator ổn định.

Điểm cần nhớ ngay từ đầu: message chuẩn của Spring có envelope bất biến, nhưng điều đó **không tự động làm payload bất biến**. Nếu payload hoặc giá trị trong header là một object có thể thay đổi, nhiều endpoint vẫn có thể cùng nhìn thấy và sửa chính object đó khi message đi qua các channel trong cùng JVM.

## 1. Cấu trúc của một message

Trong Spring Messaging, `Message<T>` biểu diễn một payload có kiểu `T` cùng một tập headers:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

Ví dụ một message chứa đơn hàng:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("tenantId", "tenant-42")
        .setHeader("correlationId", "checkout-2026-001")
        .build();
```

Có thể hình dung cấu trúc như sau:

```text
Message<Order>
├── payload: Order
│   ├── orderId
│   ├── customer
│   └── lines
└── headers: MessageHeaders
    ├── id
    ├── timestamp
    ├── tenantId
    └── correlationId
```

Payload thường chứa dữ liệu mà bước xử lý cần đọc hoặc biến đổi. Headers mô tả message và ngữ cảnh xử lý: message thuộc tenant nào, đang nằm trong luồng nghiệp vụ nào, cần trả lời về đâu hoặc cần được định tuyến theo tiêu chí nào.

### 1.1. Immutable của envelope có nghĩa gì?

Các implementation message tiêu chuẩn như `GenericMessage` không cung cấp setter để thay payload sau khi tạo. `MessageHeaders` cũng được thiết kế như một map chỉ đọc. Vì vậy, đoạn mã sau không phải cách cập nhật header hợp lệ:

```java
message.getHeaders().put("priority", 10); // Không được hỗ trợ
```

Map headers không cho phép ghi trực tiếp; thao tác này thường ném `UnsupportedOperationException`. Muốn thay đổi metadata, ứng dụng phải tạo một message mới bằng `MessageBuilder`, header enricher hoặc một endpoint thích hợp.

Tuy nhiên, immutable ở đây là **bất biến nông (shallow immutability)**:

- Không thể thay payload reference hoặc sửa cấu trúc map headers của message chuẩn sau khi tạo.
- Có thể vẫn thay đổi trạng thái bên trong object payload nếu class payload có setter, collection mutable hoặc object con mutable.
- Giá trị được lưu trong một header cũng có thể là object mutable. Map không cho thay cặp key/value không có nghĩa object nằm sau value đó bất biến.

Ví dụ, nếu payload là `ArrayList`, code nhận message vẫn có thể gọi `add()` trên danh sách đó. Nếu header `routingContext` chứa một `HashMap`, code giữ reference tới map vẫn có thể sửa nội dung map. Envelope không bị thay thế, nhưng dữ liệu mà các endpoint quan sát được đã thay đổi.

| Thành phần | Điều được bảo vệ | Điều không được bảo vệ tự động |
|---|---|---|
| Message chuẩn | Không có API setter để thay payload trên message đã tạo | Trạng thái bên trong payload |
| `MessageHeaders` | Cấu trúc map headers chỉ đọc | Trạng thái bên trong object dùng làm giá trị header |
| Payload là object immutable | Giá trị nghiệp vụ không đổi sau khi tạo | Các object con nếu chúng vẫn mutable |
| Payload là collection mutable | Không có bảo vệ đặc biệt | Phần tử, thứ tự và nội dung collection |

Do đó, khi cần một message thực sự an toàn để chia sẻ giữa nhiều luồng, phải xem xét cả thiết kế payload và các giá trị header, không chỉ bản thân `Message<?>`.

## 2. Tạo message mới khi cần thay đổi dữ liệu

`MessageBuilder` là API phổ biến để tạo message. Hai cách dùng chính tương ứng với hai tình huống khác nhau.

### 2.1. Tạo message mới từ payload

Khi bắt đầu một luồng hoặc tạo payload mới, dùng `withPayload()`:

```java
Message<Order> incoming = MessageBuilder
        .withPayload(order)
        .setHeader("source", "checkout-api")
        .setHeader("tenantId", tenantId)
        .setHeader("correlationId", requestId)
        .build();
```

Các header được đưa vào builder trước khi gọi `build()`. Sau khi build, ứng dụng nhận một message hoàn chỉnh với payload và headers đã được thiết lập.

### 2.2. Tạo message mới dựa trên message hiện có

Khi chỉ cần bổ sung hoặc điều chỉnh metadata mà vẫn giữ payload, dùng `fromMessage()`:

```java
Message<Order> prioritized = MessageBuilder
        .fromMessage(incoming)
        .setHeader("priority", 10)
        .setHeader("route", "express")
        .build();
```

Builder tạo ra một message mới dựa trên message đầu vào. Message cũ vẫn tồn tại và không bị sửa tại chỗ. Đây là cách phù hợp để giữ lại payload và metadata cần thiết trong khi tạo phiên bản message tiếp theo.

### 2.3. Tạo payload mới và mang theo headers cần thiết

Khi một transformer chuyển payload từ kiểu này sang kiểu khác, hãy tạo message với payload kết quả và sao chép các header cần truyền tiếp:

```java
Message<NormalizedOrder> normalized = MessageBuilder
        .withPayload(normalize(incoming.getPayload()))
        .copyHeaders(incoming.getHeaders())
        .setHeader("normalizationVersion", 1)
        .build();
```

`copyHeaders()` giúp giữ metadata trong quá trình biến đổi. Việc sao chép map headers là sao chép cấu trúc map; các object được tham chiếu bởi giá trị header không nhất thiết được clone sâu. Nếu một header chứa collection hoặc object mutable, message mới và message cũ có thể cùng tham chiếu tới object đó.

Các header hệ thống như `id` và `timestamp` do Spring quản lý theo quy tắc của API tạo message. Không nên dùng chúng làm mã đơn hàng, mã thanh toán hoặc khóa idempotency. Hãy truyền các định danh nghiệp vụ riêng như `orderId`, `requestId` hoặc `correlationId`.

### 2.4. Headers nên chứa gì?

Headers phù hợp với metadata nhỏ, có ý nghĩa xuyên suốt luồng xử lý:

- `correlationId`: liên kết các message thuộc cùng một nghiệp vụ hoặc một yêu cầu.
- `tenantId`: xác định ngữ cảnh tenant khi hệ thống hỗ trợ multi-tenancy.
- `contentType`: mô tả định dạng nội dung khi các converter cần thông tin này.
- `replyChannel` và `errorChannel`: cung cấp đích phản hồi hoặc đích lỗi trong các flow có hỗ trợ cơ chế tương ứng.
- `sequenceNumber` và `sequenceSize`: hỗ trợ xử lý nhóm message được tạo bởi splitter và aggregator.

Không nên đưa toàn bộ object nghiệp vụ lớn vào headers. Dữ liệu chính thuộc payload; headers nên mô tả cách runtime định tuyến hoặc xử lý message. Cũng cần thận trọng khi đưa channel object, connection, session hoặc object không thể serialize vào headers nếu message có thể đi qua message store hay ranh giới hệ thống.

## 3. Thiết kế payload bất biến

Nếu nhiều endpoint có thể đọc cùng payload, cách an toàn nhất là dùng object bất biến. Với Java, `record` là lựa chọn gọn cho DTO chỉ chứa các giá trị bất biến:

```java
public record OrderLine(String sku, int quantity) {}

public record Order(String id, List<OrderLine> lines) {
    public Order {
        lines = List.copyOf(lines);
    }
}
```

`List.copyOf()` tạo một danh sách không thể sửa thông qua reference được lưu trong record. Ví dụ này an toàn khi các phần tử `OrderLine` cũng bất biến. Nếu phần tử là object mutable, việc copy danh sách vẫn chỉ là copy nông; cần tạo bản sao bất biến cho từng phần tử hoặc chuyển chúng thành kiểu dữ liệu bất biến.

Một số nguyên tắc thực tế:

1. Ưu tiên `record`, class chỉ có field `final` và collection bất biến cho DTO được truyền qua flow.
2. Sao chép collection ở ranh giới nhận dữ liệu; không giữ reference tới collection mutable do caller sở hữu.
3. Không cung cấp setter hoặc method thay đổi trạng thái nghiệp vụ sau khi payload đã được đưa vào message.
4. Khi cần cập nhật, tạo payload mới từ payload cũ thay vì sửa object đang được chia sẻ.
5. Tránh đặt object mutable vào headers; nếu cần, dùng giá trị đơn giản hoặc object bất biến.

Nếu không thể dùng payload bất biến, cần xác định rõ endpoint nào sở hữu quyền ghi và nơi nào phải tạo defensive copy. Quy ước này phải được áp dụng nhất quán trên toàn flow; chỉ một endpoint sửa dữ liệu cũng có thể làm kết quả của endpoint khác phụ thuộc vào thứ tự thực thi.

## 4. Message được truyền qua runtime như thế nào?

Một flow thường nhận dữ liệu từ inbound adapter hoặc gateway, tạo message, chuyển message qua channel, rồi giao cho các endpoint xử lý:

```mermaid
flowchart LR
    A[Inbound adapter / Gateway] --> B[Message]
    B --> C[MessageChannel]
    C --> D[Transformer / Router / Filter]
    D --> E[MessageChannel]
    E --> F[Service Activator]
    F --> G[Outbound adapter]
```

Channel là cơ chế chuyển giao message giữa các thành phần. Channel không mặc định clone payload, serialize message hoặc chuyển đổi kiểu dữ liệu. Với channel chạy trong cùng JVM, payload thường tiếp tục là cùng object reference được tạo ở đầu flow, trừ khi một endpoint, interceptor hoặc cơ chế tích hợp cụ thể tạo message/payload mới.

Vì vậy, cần phân biệt **message được chuyển qua channel** với **dữ liệu được sao chép hoặc chuyển đổi**. Hai việc này không đồng nghĩa.

### 4.1. Khác biệt giữa các channel thường gặp

| Channel | Cách chuyển giao | Hệ quả đối với payload mutable |
|---|---|---|
| `DirectChannel` | Gọi handler đồng bộ trên luồng gửi | Handler xử lý ngay trong luồng gửi và thường nhận cùng payload reference |
| `QueueChannel` | Đưa message vào hàng đợi để consumer lấy ra sau | Hàng đợi trong bộ nhớ giữ message/reference; thời điểm xử lý khác thời điểm gửi nhưng không tự tạo bản sao sâu |
| `ExecutorChannel` | Gửi việc xử lý qua `TaskExecutor` | Handler có thể chạy ở thread khác; việc chia sẻ payload mutable có thể gây race condition |
| `PublishSubscribeChannel` | Phát message tới nhiều subscriber | Nhiều subscriber có thể cùng quan sát một payload; nếu chạy đồng thời, việc sửa payload có thể xung đột |

`PublishSubscribeChannel` có thể được cấu hình với executor để xử lý bất đồng bộ. Nếu không có executor, việc phát tới subscriber thường diễn ra đồng bộ. `DirectChannel` thường phân phối message tới một subscriber được chọn theo cấu hình dispatcher/load-balancing; nó không mang ý nghĩa broadcast như `PublishSubscribeChannel`.

`QueueChannel` có thể dùng message store làm nơi lưu message. Khi dùng store bền vững hoặc adapter giao tiếp với broker/hệ thống khác, dữ liệu có thể được ánh xạ, serialize hoặc deserialize tùy cấu hình. Sau ranh giới đó, không nên dựa vào Java object identity của payload ban đầu.

### 4.2. Đồng bộ và bất đồng bộ không quyết định tính immutable

Đồng bộ chỉ mô tả thời điểm và thread thực thi handler. Bất đồng bộ chỉ việc gửi và xử lý có thể tách rời nhau. Cả hai không tự biến payload mutable thành payload immutable.

Ví dụ, nếu hai endpoint cùng giữ reference tới một `ArrayList`, việc chuyển qua `ExecutorChannel` có thể khiến một endpoint đọc trong lúc endpoint kia thêm phần tử. Kết quả có thể phụ thuộc vào lịch chạy của thread, gây lỗi khó tái hiện.

```java
// Rủi ro: payload chứa danh sách có thể thay đổi.
List<OrderLine> lines = new ArrayList<>(order.getLines());
Message<List<OrderLine>> message = MessageBuilder
        .withPayload(lines)
        .build();

// Nếu nhiều consumer cùng nhận message, một consumer sửa list
// có thể ảnh hưởng tới consumer còn lại.
```

Giải pháp là chuyển payload thành dữ liệu bất biến trước khi phát tới nhiều consumer, hoặc tạo bản sao riêng cho từng nhánh nếu mỗi nhánh cần quyền ghi. Nếu cần đồng bộ hóa trạng thái mutable, phải thiết kế cơ chế đồng bộ rõ ràng; không nên kỳ vọng channel tự giải quyết vấn đề này.

## 5. Endpoint tác động đến message ra sao?

Các endpoint trong Spring Integration có vai trò khác nhau. Phân biệt vai trò giúp xác định bước nào chỉ chuyển tiếp message và bước nào tạo dữ liệu mới.

| Endpoint | Hành vi thường thấy | Điều cần kiểm tra |
|---|---|---|
| Router | Chọn channel đích dựa trên payload hoặc headers | Message được chuyển tới nhánh nào; header định tuyến có đúng không |
| Filter | Cho message đi tiếp hoặc loại bỏ message | Điều kiện lọc; message bị loại có được xử lý theo discard flow không |
| Transformer | Chuyển payload hoặc bổ sung metadata, thường tạo message kết quả | Kiểu payload đầu vào/đầu ra và headers cần giữ lại |
| Splitter | Tách một payload thành nhiều message con | Correlation và sequence metadata để ghép lại |
| Aggregator | Gom các message liên quan thành một kết quả | Correlation strategy, release strategy và trạng thái nhóm |
| Service Activator | Gọi method nghiệp vụ với payload/headers; có thể phát reply | Kiểu tham số, header binding và giá trị trả về |
| Bridge | Nối hai channel và chuyển tiếp message | Channel đích và các interceptor trên đường đi |

Một flow DSL minh họa việc enrich metadata rồi biến đổi payload:

```java
@Bean
IntegrationFlow normalizeOrders() {
    return IntegrationFlow.from("orders.input")
            .enrichHeaders(headers -> headers
                    .header("source", "checkout")
                    .header("schemaVersion", 1))
            .transform(Order.class, this::normalize)
            .channel("orders.normalized")
            .get();
}
```

Ở đây, header enricher bổ sung metadata cho message trong flow. Transformer gọi hàm `normalize` để tạo payload đã chuẩn hóa. Khi payload thay đổi kiểu hoặc nội dung, cần kiểm tra headers nào phải được giữ lại để các bước sau vẫn định tuyến, tương quan và xử lý đúng.

### 5.1. Splitter và aggregator

Splitter thường biến một message đầu vào thành nhiều message con. Các message con cần metadata tương quan và thứ tự để aggregator biết chúng thuộc cùng nhóm. Spring Integration sử dụng các header như `correlationId`, `sequenceNumber` và `sequenceSize` trong các tình huống này.

Aggregator thu thập các message cùng nhóm theo correlation strategy, kiểm tra điều kiện giải phóng bằng release strategy rồi tạo message kết quả. Khi tự xây splitter hoặc aggregator, không nên tùy tiện xóa hoặc ghi đè các header tương quan. Nếu nghiệp vụ cần correlation key riêng, hãy xác định rõ key đó và bảo đảm mọi nhánh đều truyền tiếp nhất quán.

## 6. Message, conversion và ranh giới hệ thống

Một channel trong cùng ứng dụng thường chuyển message object. Việc chuyển đổi định dạng thường xuất hiện ở adapter, gateway hoặc endpoint được cấu hình converter. Ví dụ, một inbound adapter có thể chuyển dữ liệu từ giao thức bên ngoài thành payload Java; outbound adapter có thể ánh xạ payload và một số headers thành dữ liệu gửi tới hệ thống đích.

Không nên giả định mọi header nội bộ sẽ tự động đi qua ranh giới hệ thống. Header mapper có thể chỉ cho phép một tập header nhất định, đổi tên hoặc bỏ qua header không phù hợp. Những giá trị như `replyChannel` và `errorChannel` có thể đại diện cho đối tượng runtime trong ứng dụng, không phải dữ liệu giao thức phù hợp để gửi sang hệ thống khác.

Khi message được lưu vào message store hoặc gửi qua broker, cần xác định rõ:

- Payload có thể serialize/deserialize được bằng cơ chế đang cấu hình hay không.
- Các header cần khôi phục sau khi đọc lại là những header nào.
- Header nào chỉ có ý nghĩa trong JVM hiện tại và phải loại bỏ hoặc ánh xạ.
- Phiên bản schema của payload được quản lý thế nào khi producer và consumer triển khai khác thời điểm.
- Dữ liệu có được sao chép tại ranh giới đó hay chỉ được giữ reference trong bộ nhớ.

Serialization không thay thế thiết kế schema. Một class Java serialize được ở thời điểm hiện tại vẫn có thể gây vấn đề khi đổi package, đổi field hoặc nâng phiên bản ứng dụng. Với luồng liên hệ thống, nên dùng hợp đồng dữ liệu rõ ràng và converter có cấu hình thay vì dựa vào chi tiết object nội bộ.

## 7. Ảnh hưởng tới retry, transaction và correlation

Tính immutable giúp việc xử lý lại message dễ dự đoán hơn. Khi một endpoint thất bại và cơ chế retry gọi lại logic, payload bất biến giữ nguyên đầu vào nghiệp vụ. Nếu lần xử lý trước đã sửa một object mutable dùng chung, lần retry có thể bắt đầu từ trạng thái đã bị thay đổi và tạo kết quả khác.

Transaction quản lý commit/rollback của các resource tham gia transaction. Transaction không tự hoàn tác thay đổi trên một Java object đang nằm trong bộ nhớ. Nếu code sửa payload rồi database transaction rollback, object payload vẫn có thể giữ trạng thái đã sửa. Vì vậy, không nên coi rollback là cơ chế phục hồi payload.

Correlation và idempotency cũng cần được phân biệt:

- `correlationId` liên kết các message trong cùng một yêu cầu hoặc nhóm xử lý.
- `MessageHeaders.ID` nhận diện một message cụ thể theo cơ chế của Spring.
- Idempotency key là định danh nghiệp vụ do ứng dụng quy định để nhận biết yêu cầu đã được xử lý; ví dụ `paymentRequestId` hoặc `orderId` kết hợp loại thao tác.

Không dùng message ID thay cho idempotency key nếu nghiệp vụ cần nhận biết hai lần gửi lại cùng một yêu cầu. Message mới có thể có identity message khác trong khi vẫn đại diện cho cùng một yêu cầu nghiệp vụ.

Khi một flow có retry, message store hoặc aggregator, hãy giữ payload và metadata tương quan ổn định. Nếu cần ghi nhận trạng thái xử lý, tạo metadata hoặc event mới có chủ đích; tránh sửa ngầm object đang được chia sẻ.

## 8. Quan sát và chẩn đoán dữ liệu trong runtime

Khi một message đi qua nhiều endpoint, nên quan sát cả payload type lẫn metadata. Một log hữu ích thường ghi nhận:

- Tên flow, endpoint hoặc channel đang xử lý.
- `id` và `correlationId` nếu có.
- Kiểu payload (`payload.getClass().getName()`) và một định danh nghiệp vụ an toàn để log.
- Các header định tuyến hoặc phiên bản schema có liên quan.
- Thread name và thời điểm xử lý khi điều tra vấn đề concurrency.

Không nên log toàn bộ payload hoặc headers một cách mặc định nếu chúng có thể chứa thông tin nhạy cảm, token hay dữ liệu cá nhân. Hãy chọn trường cần thiết và che dữ liệu theo chính sách của ứng dụng.

Khi dữ liệu đầu ra không như mong đợi, kiểm tra theo thứ tự:

1. Inbound adapter/gateway tạo payload kiểu gì và có converter nào tham gia?
2. Channel đang dùng là đồng bộ, queue hay executor; có bao nhiêu consumer?
3. Endpoint nào biến đổi payload hoặc bổ sung/xóa header?
4. Có `ChannelInterceptor` nào thay message ở bước `preSend` hoặc chặn message không?
5. Message có đi qua message store, broker hoặc ranh giới serialize/deserialize không?
6. Có nhiều consumer cùng giữ reference tới payload/header value mutable không?

Đặc biệt, nếu lỗi chỉ xuất hiện khi bật executor hoặc khi tăng số subscriber, hãy kiểm tra quyền sở hữu và tính mutable của payload trước khi kết luận channel làm mất dữ liệu.

## 9. Quy tắc thiết kế nên áp dụng

- Xem message là envelope gồm payload và headers; dùng payload cho dữ liệu nghiệp vụ, headers cho metadata runtime.
- Coi message và `MessageHeaders` chuẩn là immutable; dùng builder hoặc endpoint để tạo message mới khi cần thay đổi.
- Thiết kế payload bất biến, bao gồm cả collection và object lồng nhau, trước khi chia sẻ qua nhiều nhánh hoặc thread.
- Không giả định channel trong cùng JVM sẽ clone, deep-copy hoặc serialize payload.
- Xác định rõ channel và mô hình thực thi để hiểu message được xử lý đồng bộ, qua queue hay qua executor.
- Giữ các header correlation/sequence cần thiết khi transform, split và aggregate.
- Không dùng `id` hoặc `timestamp` của message làm định danh nghiệp vụ hay idempotency key.
- Xác định hợp đồng payload/header tại ranh giới message store và hệ thống bên ngoài; chỉ truyền các header thực sự cần thiết.
- Khi debug, theo dõi correlation, payload type, endpoint và thread; kiểm tra interceptor nếu message thay đổi ngoài dự kiến.

Khi tuân thủ các nguyên tắc này, message trở thành đơn vị trao đổi có thể dự đoán trong runtime. Envelope immutable giúp các endpoint không vô tình ghi đè cấu trúc message; payload immutable giúp nhiều endpoint và thread cùng đọc dữ liệu an toàn; còn việc hiểu channel và ranh giới chuyển đổi giúp xác định chính xác nơi dữ liệu được giữ nguyên, được biến đổi hoặc được lưu trữ.
