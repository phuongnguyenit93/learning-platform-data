# Message có payload null và cách biểu diễn

Trong **Spring Integration**, message là đơn vị trao đổi giữa các endpoint của một luồng **Enterprise Integration Patterns** (EIP). Một message thường chứa **payload** — dữ liệu cần xử lý — và **headers** — metadata phục vụ điều phối, correlation, định tuyến, truy vết hoặc xử lý lỗi. Vậy nếu một lời gọi nghiệp vụ không tìm thấy dữ liệu, hoặc một hệ thống bên ngoài gửi giá trị `null`, ta có thể tạo `Message` với payload `null` không?

**Câu trả lời ngắn:** Với API message chuẩn của Spring (`org.springframework.messaging.Message<T>`, `GenericMessage<T>` và `MessageBuilder`), **payload của một message hiện hữu không được là `null`**. Cần phân biệt rõ giữa **không có message**, **message có payload là một đối tượng biểu diễn sự vắng mặt**, **message chứa một đối tượng có trường `null`**, và **giá trị null ở tầng giao thức bên ngoài**. Những trường hợp này có ý nghĩa và cách xử lý khác nhau.

Sau bài này, bạn sẽ biết cách:

- Giải thích quy tắc không-null của payload trong Spring Messaging và Spring Integration.
- Thiết kế biểu diễn phù hợp cho kết quả không tìm thấy, dữ liệu tùy chọn, thông báo rỗng, hoặc sự kiện xóa.
- Phân biệt `null` trong payload với không có message/reply, header vắng mặt và giá trị `null` của JSON hoặc broker.
- Chọn Filter, Router, Transformer, Gateway, `nullChannel` và error channel đúng mục đích mà không làm mất ngữ nghĩa nghiệp vụ.
- Kiểm thử những nhánh không có dữ liệu hoặc không có phản hồi.

## 1. Quy tắc cốt lõi: payload của `Message` không được null

Spring cung cấp giao diện message theo mô hình sau:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

Đây là hình dạng tối giản để hiểu khái niệm; không phải khai báo đầy đủ các thành phần của framework. Trong các cách xây dựng message tiêu chuẩn, payload phải khác `null`. Ví dụ:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> valid = MessageBuilder.withPayload("hello").build();

// KHÔNG HỢP LỆ: payload null bị từ chối khi xây dựng message.
Message<String> invalid = MessageBuilder.withPayload((String) null).build();
```

Lời gọi thứ hai ném `IllegalArgumentException` do vi phạm tiền điều kiện payload không-null. Điều này cũng áp dụng khi sử dụng `GenericMessage` theo cách thông thường. Kể cả khi tham số kiểu là `Message<Object>` hay `Message<Void>`, tên kiểu **không tạo ngoại lệ** cho quy tắc này.

```text
Message hiện hữu
├── payload  = đối tượng KHÁC null   ✓
└── headers  = metadata của message

Message có payload = null           ✗ (không tạo được bằng API chuẩn)
Không có message/reply              ✓ (trạng thái khác hoàn toàn)
Message có payload = Optional.empty ✓ (Optional là đối tượng khác null)
Message có payload = NoData.INSTANCE✓ (marker là đối tượng khác null)
```

**Vì sao phải phân biệt?** Khi các endpoint xử lý `Message<?>`, framework có thể giả định đã tồn tại một payload và sử dụng nó để chọn handler, chuyển đổi kiểu, lọc hay định tuyến. Nếu nghiệp vụ có trạng thái “không có giá trị”, trạng thái đó cần được biểu diễn tường minh, không dựa vào việc đưa `null` làm toàn bộ payload.

## 2. Năm trạng thái dễ bị đánh đồng

| Trạng thái | Ví dụ | Có phải `Message` với payload null? | Cách hiểu đúng |
| --- | --- | --- | --- |
| Không có message được phát | Filter loại bỏ đầu vào | Không | Không có message đầu ra ở nhánh đó. |
| Message tồn tại, kết quả “không tìm thấy” | Payload `NotFound("ORD-404")` | Không | Payload là một giá trị nghiệp vụ hợp lệ. |
| Message có đối tượng chứa trường null | `new LookupData("ORD-404", null)` | Không | Toàn bộ payload không null; trường bên trong có thể null theo hợp đồng. |
| Message chứa một giá trị rỗng | `""`, `List.of()`, `new byte[0]` | Không | Giá trị rỗng khác `null`; ý nghĩa do hợp đồng dữ liệu quy định. |
| Giao thức bên ngoài có null | JSON `null`, bản ghi Kafka có value null | Không nhất thiết | Đó là biểu diễn của giao thức; adapter phải xử lý và ánh xạ đúng. |

### Không có reply không đồng nghĩa reply chứa null

Ở luồng request–reply, một handler có thể không tạo kết quả trả về; Gateway có thể không nhận được reply và sẽ tuân theo timeout hoặc chính sách lỗi của cấu hình. Không thể kết luận rằng đã có một `Message` chứa payload `null`. Tương tự, một phương thức Java trả `null` không tự động tạo ra `Message<T>` hợp lệ có payload `null`: hành vi tiếp theo phụ thuộc vào loại endpoint và hợp đồng reply.

### Không có trường header cũng không phải payload null

Header là metadata có thể thiếu. Chẳng hạn `message.getHeaders().get("traceId")` có thể trả `null` khi không tồn tại khóa `traceId`; nhưng payload của message vẫn không null. Với `MessageBuilder`, đặt header có giá trị `null` được xử lý như thao tác không giữ header đó, chứ không phải cách đặt payload null.

## 3. Biểu diễn sự vắng mặt theo nhu cầu nghiệp vụ

Không có một biểu diễn duy nhất phù hợp với mọi luồng. Câu hỏi đúng là: **bên nhận cần phân biệt những trạng thái nào, và chúng có phải được bảo toàn khi gửi qua một hệ thống khác hay không?**

### Cách A — Kiểu kết quả nghiệp vụ rõ ràng: nên ưu tiên khi cần phản hồi

Giả sử một Gateway tra cứu đơn hàng. “Không tìm thấy” là một **kết quả bình thường**, không phải sự cố truyền message. Có thể dùng kiểu kết quả đóng (*sealed hierarchy*) trong Java 17+:

```java
import java.math.BigDecimal;
import java.util.Optional;

record FindOrder(String orderId) {}
record OrderInfo(String orderId, BigDecimal totalAmount) {}

sealed interface FindOrderResult permits Found, NotFound {}
record Found(OrderInfo order) implements FindOrderResult {}
record NotFound(String orderId) implements FindOrderResult {}

interface OrderRepository {
    Optional<OrderInfo> findById(String orderId);
}

class OrderLookup {
    private final OrderRepository repository;

    OrderLookup(OrderRepository repository) {
        this.repository = repository;
    }

    FindOrderResult lookup(FindOrder command) {
        return repository.findById(command.orderId())
                .<FindOrderResult>map(Found::new)
                .orElseGet(() -> new NotFound(command.orderId()));
    }
}
```

Kết quả có thể được đặt vào message như mọi payload hợp lệ:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

FindOrderResult result = new NotFound("ORD-404");
Message<FindOrderResult> reply = MessageBuilder.withPayload(result)
        .setHeader("traceId", "trace-123")
        .build();
```

Ưu điểm: người đọc và Router có thể phân biệt `Found`/`NotFound` bằng kiểu; không phải suy đoán từ một giá trị null tùy tiện. Trường `traceId` chỉ là metadata theo dõi, không ảnh hưởng đến ý nghĩa của kết quả.

### Cách B — `Optional.empty()` trong payload: phù hợp cho phạm vi nội bộ có kiểm soát

`Optional.empty()` **khác `null`**: nó là một đối tượng biểu diễn “không có giá trị”. Vì thế về mặt quy tắc payload, đây là message hợp lệ:

```java
import java.util.Optional;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<Optional<String>> message = MessageBuilder
        .withPayload(Optional.<String>empty())
        .build();

boolean absent = message.getPayload().isEmpty(); // true
```

Tuy nhiên, `Optional` chủ yếu thích hợp làm kiểu kết quả API Java. **Không nên mặc định dùng nó làm hợp đồng message lưu bền vững hoặc gửi xuyên tiến trình**, vì serializer và schema của bên nhận có thể không biểu diễn được cùng ngữ nghĩa; `Optional` cũng không phải kiểu được thiết kế như một định dạng truyền dữ liệu phổ quát. Với message tích hợp liên hệ thống, kiểu `Found`/`NotFound` hoặc một schema kết quả rõ ràng thường dễ tương tác hơn.

### Cách C — Marker/sentinel: cho thông điệp điều khiển trong nội bộ

Nếu cần gửi một tín hiệu mà không có dữ liệu chi tiết, có thể dùng một marker **khác null**:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

enum NoData {
    INSTANCE
}

Message<NoData> signal = MessageBuilder.withPayload(NoData.INSTANCE)
        .setHeader("reason", "refresh-completed")
        .build();
```

Điều này có thể hợp lý cho một luồng nội bộ. Nhưng `NoData.INSTANCE` **không phải khái niệm chung được Spring tự hiểu**; nó chỉ có ý nghĩa nếu tất cả handler và converter liên quan thống nhất về kiểu và cách xử lý. Nếu dữ liệu phải đi qua JSON/broker, hãy thiết kế và kiểm thử định dạng tuần tự hóa của tín hiệu này thay vì truyền một enum tùy tiện mà không có contract.

### Cách D — Đối tượng có trường nullable: khi chính một thuộc tính có thể vắng mặt

Đôi khi payload là một kết quả có nhiều trường và **chỉ một phần thông tin được phép vắng mặt**:

```java
record CustomerProfile(String customerId, String secondaryEmail) {}

CustomerProfile profile = new CustomerProfile("CUS-08", null);
// profile khác null; secondaryEmail có thể null theo hợp đồng nghiệp vụ.
```

Hãy định nghĩa rõ: `secondaryEmail == null` nghĩa là “chưa biết”, “không cung cấp”, hay “đã xóa”? Nếu những trạng thái này khác nhau, một trường nullable đơn lẻ là không đủ; nên dùng trạng thái tường minh hoặc một schema có phân biệt *missing* và *explicit null*.

### Cách E — Empty collection/string/bytes: chỉ khi “rỗng” thực sự có nghĩa

`List.of()`, `""` và `new byte[0]` đều khác null và có thể làm payload nếu kiểu phù hợp. Tuy nhiên, **danh sách rỗng** thường có nghĩa là “đã truy vấn, có 0 phần tử”, trong khi **không có kết quả** có thể nghĩa là “không tra cứu”, “không được phép trả dữ liệu” hoặc “không tìm thấy”. Không biến những trường hợp này thành một cách biểu diễn nếu nghiệp vụ cần phân biệt chúng.

## 4. Biểu diễn dữ liệu JSON và giao thức ngoài

Trong JSON, các biểu diễn sau không tương đương:

```json
{}
```

```json
{"customerEmail": null}
```

```json
{"customerEmail": ""}
```

```json
{"status": "NOT_FOUND", "orderId": "ORD-404"}
```

Trường vắng mặt, trường có giá trị `null`, chuỗi rỗng và kết quả không tìm thấy là bốn tình huống khác nhau. Với một hợp đồng API, cần ghi rõ trường nào bắt buộc, nullable và trạng thái nào được phép.

Lưu ý quan trọng: message có payload là **chuỗi** `"null"` vẫn có payload khác null — cụ thể đó là bốn ký tự `n`, `u`, `l`, `l` — dù nội dung chuỗi có thể được một JSON parser diễn giải thành giá trị JSON `null`. Khi bộ chuyển đổi nội dung đọc giá trị null ở cấp gốc, phải xác định liệu hệ thống cần **giữ thông tin bằng một kiểu thay thế hợp lệ**, loại bỏ nó theo chính sách, hay báo lỗi, thay vì cố ép `MessageBuilder` nhận `null`.

### Trường hợp Kafka tombstone

Trong Kafka, bản ghi có **record value = null** được dùng theo ngữ nghĩa giao thức, thường là *tombstone* cho compacted topic. Đây không phải là một Spring `Message<?>` hợp lệ với payload null. Nếu cần đi qua các API message của Spring, adapter hoặc tích hợp Kafka phải có cách đại diện cho trạng thái này (ví dụ marker `KafkaNull.INSTANCE` của Spring Kafka trong các luồng phù hợp) và ánh xạ ra giá trị null ở transport đúng cách.

**Không tự suy luận** rằng `MessageBuilder.withPayload(null)` sẽ tạo Kafka tombstone, hoặc rằng mọi adapter đều hiểu `KafkaNull`. Cách xử lý phụ thuộc phiên bản, thư viện tích hợp, serializer, cấu hình endpoint và hợp đồng của producer/consumer. Với bài toán này, việc phân biệt **giá trị null của broker** với **payload của Spring Message** là bắt buộc.

## 5. Khi cần “không gửi tiếp”, dùng EIP phù hợp thay vì payload null

Một số bài toán không cần trả về một message diễn đạt “không có dữ liệu”; yêu cầu thực tế chỉ là **dừng xử lý message không hợp lệ hoặc không phù hợp**. Khi đó hãy chọn pattern đúng mục đích.

| Mục đích | Pattern/cơ chế | Hành vi mong muốn |
| --- | --- | --- |
| Loại bỏ yêu cầu không thỏa điều kiện | **Filter** | Không chuyển message sang nhánh chấp nhận. |
| Chọn nhánh theo trạng thái | **Router** | Chuyển message có payload hợp lệ tới nhánh tương ứng. |
| Biến dữ liệu đầu vào thành kết quả có kiểu | **Transformer** | Trả về payload mới khác null, ví dụ `Found` hoặc `NotFound`. |
| Bỏ qua thông điệp một cách chủ đích | **`nullChannel`** | Nhận và loại bỏ message; không biến payload thành null. |
| Phản hồi đồng bộ cho caller | **Gateway** | Thiết kế hợp đồng có reply rõ ràng hoặc có cơ chế timeout/no-reply. |
| Báo lỗi xử lý | **Error channel / ErrorMessage** | Chuyển thông tin lỗi theo cơ chế lỗi, không gán payload null. |

### Ví dụ 1: Filter loại bỏ đầu vào không đủ điều kiện

Ví dụ đơn giản với Spring Integration annotation:

```java
import org.springframework.integration.annotation.Filter;
import org.springframework.stereotype.Component;

record SubmitOrder(String orderId, long amount) {}

@Component
class OrderValidationFilter {

    @Filter(
        inputChannel = "ordersInput",
        outputChannel = "ordersAccepted",
        discardChannel = "nullChannel"
    )
    public boolean accept(SubmitOrder order) {
        return order.orderId() != null
                && !order.orderId().isBlank()
                && order.amount() > 0;
    }
}
```

Nếu `accept()` trả `false`, message không đi tới `ordersAccepted`; nó được chuyển sang `nullChannel` để loại bỏ theo cấu hình minh họa. **Không có message đầu ra ở kênh chấp nhận** là kết quả của Filter, không phải message có payload null. Trong hệ thống thực, có thể dùng một **discard channel** để ghi log có kiểm soát, thống kê hoặc xử lý yêu cầu bị từ chối, thay vì loại bỏ âm thầm.

### Ví dụ 2: Transformer vẫn xuất một kết quả hợp lệ khi không tìm thấy

```java
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
class FindOrderTransformer {
    private final OrderLookup lookup;

    FindOrderTransformer(OrderRepository repository) {
        this.lookup = new OrderLookup(repository);
    }

    @Transformer(
        inputChannel = "findOrderRequests",
        outputChannel = "findOrderResponses"
    )
    public FindOrderResult transform(FindOrder request) {
        return lookup.lookup(request); // Found hoặc NotFound; không trả null.
    }
}
```

Trong ví dụ, các `record`, `interface` và `OrderLookup` đã định nghĩa ở mục 3 được dùng lại. Transformer trả về payload là `Found` hoặc `NotFound` để cả hai trường hợp vẫn có thể được Router, service khác hoặc Gateway quan sát và kiểm thử. Nếu có lỗi truy cập kho dữ liệu, không nên đánh tráo lỗi đó với `NotFound`; hãy để cơ chế báo lỗi/khôi phục phù hợp xử lý.

### Ví dụ 3: Phân biệt kết quả không tìm thấy với lỗi thực sự

```text
FindOrder request
       │
       ▼
  Order lookup
       │
       ├── Tìm thấy ───────────► Message<Found>
       │
       ├── Không tìm thấy ─────► Message<NotFound>
       │
       └── Lỗi truy cập dữ liệu ► Exception / error flow

Filter loại bỏ message ────────► Không có message ở output channel
```

`ErrorMessage` của Spring Messaging chứa **exception** làm payload khác null. Vì thế, “không tìm thấy đơn hàng” (một kết quả nghiệp vụ hợp lệ) và “cơ sở dữ liệu không truy cập được” (một sự cố) không nên được gom làm một tín hiệu `null` duy nhất.

## 6. Gateway, Splitter/Aggregator, correlation và retry

**Gateway:** Với lời gọi request–reply, phải quyết định xem “không tìm thấy” có trả một `NotFound` hay không, caller có được phép không nhận reply không, và nếu không có reply thì timeout được xử lý thế nào. Một phương thức Gateway trả về `null` trong một kịch bản no-reply/timeout (nếu cấu hình cho phép) **không chứng minh** tồn tại Spring message có payload null. Với API đồng bộ phục vụ nghiệp vụ, kết quả có kiểu thường dễ kiểm soát hơn một phản hồi ngầm định.

**Splitter:** Nếu đầu vào chứa một danh sách rỗng, luồng có thể không tạo ra các message phần tử. Danh sách rỗng là **payload đầu vào hợp lệ**, nhưng điều đó không đồng nghĩa Splitter tạo một message con có payload null. Nếu nghiệp vụ cần “đã xử lý xong nhưng không có phần tử”, hãy thiết kế tín hiệu hoặc reply độc lập khi cần.

**Aggregator:** Aggregator chỉ gom những message đã được tạo và nhận ở đầu vào. Việc **không có message con** không tạo ra một phần tử “null” để Aggregator tự kết thúc nhóm; cần thiết kế điều kiện hoàn tất nhóm, timeout, empty-result hoặc kênh thông báo kết thúc tùy bài toán. `correlationId` và `sequenceSize` giúp nhóm và xác định tiến độ khi có các message, nhưng không tự biểu diễn một payload null.

**Retry:** Một lần retry tạo ra lần xử lý hoặc giao nhận mới, không thay đổi định nghĩa payload. Nếu một nhánh không có kết quả vì dữ liệu thực sự không tồn tại, retry mù có thể không giúp ích; nếu lỗi là tạm thời, nên xử lý bằng retry policy và error flow rõ ràng. Không dùng `null` làm tín hiệu vừa “không tìm thấy”, vừa “thử lại”, vừa “lỗi” vì sẽ khó giám sát và dễ gây xử lý sai.

**Observability:** Khi theo dõi luồng, nên ghi nhận các trạng thái như `FOUND`, `NOT_FOUND`, `FILTERED`, `TIMED_OUT`, `FAILED` với correlation ID/trace ID phù hợp. Những trạng thái này không thể suy ra an toàn từ một `null` không rõ nguồn gốc. Tránh đưa dữ liệu cá nhân nhạy cảm vào headers hoặc logs chỉ để thuận tiện theo dõi.

## 7. Kiểm thử ranh giới null và giá trị rỗng

Những kiểm tra tối thiểu nên bao gồm:

1. **Không tạo được message với payload null:** kiểm tra constructor/builder từ chối `null`.
2. **Biểu diễn absence hợp lệ:** message với `NotFound` hoặc `Optional.empty()` tạo được và xử lý theo đúng nhánh.
3. **Nullable field:** trường null bên trong đối tượng payload được đọc đúng nếu schema cho phép.
4. **Filter không chuyển tiếp:** đầu vào bị loại không xuất hiện ở output channel; nếu cần giám sát, xác minh discard channel nhận được message gốc.
5. **Gateway không có phản hồi:** kiểm tra timeout, reply-required policy và cách báo lỗi theo cấu hình thực tế, không giả định tất cả Gateway có hành vi giống nhau.
6. **Codec/adapter:** kiểm tra JSON `null`, trường missing/nullable, empty bytes, Kafka tombstone và header mapping theo transport thực sự dùng.

Một unit test ngắn cho quy tắc payload:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessagePayloadTest {

    @Test
    void rejectNullPayload() {
        assertThrows(IllegalArgumentException.class,
                () -> MessageBuilder.withPayload((String) null).build());
    }

    @Test
    void notFoundIsAValidPayload() {
        Message<FindOrderResult> message = MessageBuilder
                .<FindOrderResult>withPayload(new NotFound("ORD-404"))
                .build();

        NotFound payload = assertInstanceOf(NotFound.class, message.getPayload());
        assertEquals("ORD-404", payload.orderId());
    }
}
```

Khi kiểm thử flow tích hợp thực sự, cần thêm cấu hình channel, dependency Spring Integration, môi trường adapter và test fixtures tương ứng. Ví dụ JUnit trên kiểm tra lớp `Message` và kiểu kết quả, **không thay thế** bài test đầu-cuối của toàn bộ Filter, Transformer hoặc Gateway.

## 8. Tình huống thực hành: chọn biểu diễn nào?

Giả sử hệ thống kho nhận yêu cầu kiểm tra một mã sản phẩm. Hãy cân nhắc các tình huống:

| Tình huống | Biểu diễn đề xuất | Không nên làm |
| --- | --- | --- |
| Mã sản phẩm không tồn tại | `ProductNotFound(productId)` trong payload | Trả `null` rồi để caller tự đoán nguyên nhân. |
| Sản phẩm có tồn tại, mô tả phụ chưa được nhập | `ProductInfo` với field mô tả nullable hoặc trạng thái rõ ràng | Đồng nhất việc thiếu mô tả với sản phẩm không tồn tại. |
| Danh sách tồn kho được truy vấn và có 0 dòng | `InventoryResult(items = [])` | Tự hiểu danh sách rỗng là lỗi hệ thống. |
| Message không cần đi qua nhánh xử lý tiếp theo | Filter hoặc Router/discard channel | Tạo message có payload null để “dừng luồng”. |
| Hết thời gian chờ dịch vụ kho | Timeout / error flow / result `Unavailable` nếu là contract | Đồng nhất timeout với `ProductNotFound`. |
| Cần xóa key từ một Kafka compacted topic | Tombstone theo hợp đồng Kafka, mapping qua adapter | Dùng `MessageBuilder.withPayload(null)` như cách phát tombstone. |

**Bài tập suy luận:** Nếu hệ thống kho trả JSON `{ "status": "NOT_FOUND" }`, ứng dụng Spring nhận một chuỗi JSON khác null, rồi parse thành `ProductNotFound`. Nếu hệ thống lại trả đúng JSON `null` ở cấp gốc, một converter có thể tạo giá trị Java null. Hãy thiết kế một bước **validation/translation trước khi xây dựng Spring message đầu ra**: phân biệt “không tìm thấy có chủ đích”, “payload rỗng không hợp lệ” và “lỗi giải mã” bằng các kiểu kết quả hoặc error flow riêng. Khi luồng có nhiều adapter, kiểm thử từng ranh giới để không mất ý nghĩa của trạng thái.

## Tổng kết

- Spring `Message<T>` được tạo bằng API chuẩn **không cho payload null**; `Message<Void>` cũng không phải cách lách quy tắc.
- **Không có message**, **không có reply**, **header vắng mặt**, **payload chứa trường null** và **giá trị null của giao thức** là những khái niệm khác nhau.
- Khi “không tìm thấy” là kết quả nghiệp vụ, hãy dùng **kiểu kết quả rõ ràng** như `Found`/`NotFound`; `Optional.empty()` hoặc marker khác null chỉ phù hợp khi contract cho phép.
- Khi cần **không gửi tiếp message**, dùng **Filter**, Router hoặc `nullChannel`, thay vì cố tạo message có payload null.
- Khi cần **báo lỗi**, dùng error flow/exception và policy retry phù hợp; không trộn lỗi, timeout và trạng thái không tìm thấy.
- Khi kết nối hệ thống ngoài, thiết kế rõ JSON nullable, mapping của adapter và các trường hợp đặc biệt như **Kafka tombstone** để Spring Integration vẫn giữ được ngữ nghĩa nghiệp vụ, khả năng kiểm thử và truy vết.
