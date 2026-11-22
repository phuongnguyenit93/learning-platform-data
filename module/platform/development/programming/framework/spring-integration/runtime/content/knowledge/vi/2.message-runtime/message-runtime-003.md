# Payload type và chuyển đổi tại handler boundary

Trong Spring Integration, một message có thể đi qua nhiều channel và endpoint trước khi đến phần xử lý nghiệp vụ. Channel chuyển message giữa các thành phần; endpoint nhận message và gọi handler. Tại ranh giới gọi handler, framework phải xác định tham số nào lấy từ payload, tham số nào lấy từ header và payload có tương thích với kiểu mà phương thức yêu cầu hay không.

Hiểu rõ ranh giới này giúp tránh những lỗi như handler nhận `String` trong khi mong đợi một DTO, JSON chưa được giải mã, hoặc một header bị hiểu nhầm là payload. Nó cũng giúp quyết định khi nào nên dùng chuyển đổi tự động và khi nào nên đặt một transformer tường minh trong flow.

## 1. Message là envelope, payload là dữ liệu bên trong

Spring Messaging biểu diễn message bằng `Message<T>`. Một message gồm hai phần:

- **Payload**: đối tượng dữ liệu mà flow đang vận chuyển, ví dụ `String`, `byte[]`, `Order` hoặc `List<Order>`.
- **Headers**: metadata đi kèm, ví dụ `contentType`, `correlationId`, `tenantId`, `replyChannel` hoặc `errorChannel`.

Có thể tạo một message như sau:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("tenantId", "tenant-42")
        .setHeader("correlationId", "corr-1001")
        .build();
```

`MessageHeaders` là cấu trúc bất biến: không sửa trực tiếp header của message đã tạo. Khi cần thay payload hoặc metadata, hãy tạo message mới. Bản thân đối tượng payload vẫn có thể mutable; tính bất biến của envelope không tự làm cho object bên trong trở thành immutable.

Tham số generic `T` giúp mã nguồn biểu đạt kiểu mong muốn, nhưng Java type erasure có nghĩa là `Message<Order>` không tự kiểm tra payload thực tế tại runtime. Nếu message được khai báo là `Message<?>`, hãy kiểm tra kiểu của payload trước khi ép kiểu:

```java
Object payload = message.getPayload();

if (payload instanceof Order order) {
    orderService.accept(order);
}
```

Trong flow có hợp đồng kiểu rõ ràng, nên kiểm tra và chuẩn hóa payload sớm để các endpoint phía sau không phải đoán kiểu dữ liệu.

## 2. Channel vận chuyển message; endpoint thực hiện xử lý

Channel là điểm nối giữa producer và consumer. Các channel phổ biến quyết định cách dispatch hoặc lưu message:

| Channel | Hành vi chính | Có tự đổi kiểu payload không? |
|---|---|---|
| `DirectChannel` | Gọi subscriber đồng bộ trên luồng gửi message | Không |
| `ExecutorChannel` | Dispatch subscriber thông qua executor | Không |
| `QueueChannel` | Giữ message trong hàng đợi để consumer nhận sau | Không |

Việc message chuyển qua một channel không có nghĩa payload được serialize, parse JSON hay đổi từ `String` thành DTO. Những thao tác đó thuộc về converter, transformer hoặc logic của handler.

Ranh giới handler xuất hiện khi endpoint nhận message rồi gọi thành phần xử lý. Với API mức thấp, một `MessageHandler` nhận toàn bộ envelope:

```java
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();
    Object tenantId = message.getHeaders().get("tenantId");
    // Xử lý message và metadata.
}
```

Với endpoint gọi một phương thức POJO, chẳng hạn `@ServiceActivator` hoặc `@Transformer`, Spring Integration phân giải tham số từ message. Vì vậy chữ ký phương thức quyết định handler nhìn thấy toàn bộ message hay chỉ payload/header.

## 3. Framework phân giải tham số tại handler boundary

Một endpoint gọi phương thức POJO thường cần thực hiện các bước sau:

1. Xác định nguồn của từng tham số: toàn bộ message, payload hay một header cụ thể.
2. Lấy giá trị tương ứng từ message.
3. Kiểm tra giá trị có gán được cho kiểu tham số hay không.
4. Nếu cần và có converter phù hợp, yêu cầu `ConversionService` chuyển giá trị sang kiểu đích.
5. Gọi phương thức handler. Nếu không thể phân giải hoặc chuyển đổi tham số, endpoint phát sinh lỗi xử lý message.

Ví dụ, một endpoint có thể giải mã JSON thành `Order`, sau đó chuyển DTO cho service:

```java
@Component
class OrderEndpoints {

    private final ObjectMapper objectMapper;
    private final OrderService orderService;

    OrderEndpoints(ObjectMapper objectMapper, OrderService orderService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
    }

    @Transformer(inputChannel = "rawOrders", outputChannel = "typedOrders")
    Order decode(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, Order.class);
    }

    @ServiceActivator(inputChannel = "typedOrders")
    void store(
            @Payload Order order,
            @Header("tenantId") String tenantId) {
        orderService.accept(tenantId, order);
    }
}
```

Trong ví dụ này, transformer nhận payload dạng `String` và chủ động giải mã JSON. Service activator nhận payload dạng `Order` cùng header `tenantId`. Nếu header bắt buộc không tồn tại hoặc payload không thể chuyển thành `Order`, việc gọi handler sẽ thất bại tại endpoint tương ứng.

Các dạng tham số thường gặp:

| Chữ ký tham số | Giá trị handler nhận |
|---|---|
| `Message<?> message` | Toàn bộ message, gồm payload và headers |
| `Order order` | Payload, sau khi phân giải và chuyển đổi nếu cần và có thể |
| `@Payload Order order` | Payload một cách tường minh |
| `@Header("tenantId") String tenantId` | Giá trị của header `tenantId` |
| `MessageHeaders headers` | Tập hợp headers của message |

Nếu cần đọc nhiều header, kiểm tra loại message hoặc tự quyết định cách xử lý payload, nhận `Message<?>` thường rõ ràng hơn. Nếu handler chỉ cần dữ liệu nghiệp vụ, tham số payload cụ thể giúp thể hiện hợp đồng đầu vào.

## 4. Chuyển đổi kiểu bằng ConversionService

`ConversionService` của Spring chuyển đổi một giá trị từ kiểu nguồn sang kiểu đích, ví dụ `String` thành `Integer` hoặc một enum. Trong endpoint gọi phương thức, Spring Integration có thể dùng conversion service để chuyển payload sang kiểu tham số khi payload chưa tương thích trực tiếp và có converter phù hợp.

Ví dụ, một handler yêu cầu `Integer` có thể nhận payload `String` như `"42"` nếu conversion service đang dùng có converter tương ứng. Tuy nhiên, không nên suy ra rằng mọi cặp kiểu đều tự chuyển đổi được. Khả năng chuyển đổi phụ thuộc converter đã đăng ký, conversion service mà endpoint sử dụng và cách endpoint phân giải tham số.

Có thể đăng ký converter riêng cho một quy tắc chuyển đổi nhỏ, ổn định:

```java
@Configuration
class IntegrationConversionConfiguration {

    @Bean
    @IntegrationConverter
    Converter<String, Priority> priorityConverter() {
        return source -> Priority.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

`@IntegrationConverter` đánh dấu converter để Spring Integration đưa vào conversion service dành cho tích hợp. Nếu ứng dụng thay thế hoặc tùy biến conversion service, cần xác minh converter được đăng ký trong đúng service mà endpoint sử dụng.

Chuyển đổi kiểu đơn giản phù hợp với converter, nhưng giải mã một định dạng phức tạp thường nên là bước riêng trong flow. Ví dụ, không nên giả định rằng `DefaultConversionService` sẽ tự biến một chuỗi JSON bất kỳ thành DTO chỉ vì phương thức nhận tham số `Order`. Hãy dùng transformer với Jackson hoặc một message converter được cấu hình phù hợp để thể hiện rõ cách giải mã.

## 5. Phân biệt ConversionService và MessageConverter

Hai cơ chế này có thể cùng xuất hiện trong một ứng dụng nhưng giải quyết những bài toán khác nhau:

| Cơ chế | Trách nhiệm điển hình | Ví dụ |
|---|---|---|
| `ConversionService` | Chuyển một object từ kiểu nguồn sang kiểu đích khi phân giải giá trị cho tham số hoặc biểu thức | `String` thành `Integer`, `String` thành enum |
| `MessageConverter` | Chuyển đổi payload theo hợp đồng message, định dạng hoặc giao thức; thường gặp ở ranh giới messaging và adapter | JSON bytes thành object, object thành JSON bytes |
| Transformer nghiệp vụ | Thực hiện biến đổi có ý nghĩa trong flow và thể hiện rõ bước xử lý | Chuỗi JSON thành `Order`, chuẩn hóa mã đơn hàng |

Header `contentType` có thể cung cấp gợi ý cho một số message converter, đặc biệt khi xử lý JSON hoặc nội dung có MIME type. Header này không tự động khiến mọi handler trong flow giải mã payload. Converter phải được cấu hình và endpoint phải thực sự sử dụng converter đó.

Một cách phân chia trách nhiệm dễ bảo trì là: adapter xử lý định dạng của hệ thống bên ngoài; transformer chuyển dữ liệu đầu vào thành mô hình mà ứng dụng hiểu; service activator thực hiện nghiệp vụ trên mô hình đã chuẩn hóa.

## 6. Payload và headers khi tạo message đầu ra

Transformer có thể trả về payload mới hoặc một `Message<?>` mới. Khi chỉ trả về payload, endpoint tạo message phản hồi theo cơ chế của Spring Integration và áp dụng quy tắc truyền headers của endpoint. Nếu một header nghiệp vụ phải được giữ lại qua bước biến đổi, hãy xác định rõ điều đó trong thiết kế và kiểm thử.

Khi cần tự kiểm soát message đầu ra, có thể tạo message mới và sao chép các header được flow cần:

```java
Message<Order> output = MessageBuilder
        .withPayload(normalizedOrder)
        .setHeader("tenantId", input.getHeaders().get("tenantId"))
        .setHeader("correlationId", input.getHeaders().get("correlationId"))
        .build();
```

Cách này làm rõ header nào là một phần của hợp đồng nghiệp vụ. Không nên sao chép metadata một cách máy móc nếu transformer đang tạo một message có ngữ nghĩa mới; các header điều khiển luồng như reply hoặc error channel cần được cân nhắc theo mục đích của flow.

## 7. Lỗi thường gặp tại ranh giới handler

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Handler nhận `String` nhưng code kỳ vọng DTO | Chưa có bước giải mã hoặc converter phù hợp | Thêm transformer tường minh trước handler |
| Không thể gán payload cho kiểu tham số | Payload không tương thích và conversion service không có converter | Kiểm tra kiểu runtime và đăng ký converter đúng nơi |
| Chuyển đổi JSON thất bại | JSON sai định dạng, schema không khớp hoặc chọn sai message converter | Kiểm tra payload gốc, `contentType` và cấu hình parser |
| Handler thiếu một header bắt buộc | Producer không gửi header hoặc bước trước làm mất header | Kiểm tra message ở từng boundary và xác định quy tắc truyền header |
| Lỗi chỉ xuất hiện khi chạy bất đồng bộ | Lỗi xảy ra trên executor hoặc ở consumer/poller nên không được ném trực tiếp về luồng gửi | Kiểm tra error channel và cấu hình xử lý lỗi của endpoint/poller |

Lỗi trong lúc gọi handler thường được Spring Integration biểu diễn dưới dạng lỗi xử lý message, chẳng hạn `MessageHandlingException`, kèm message gây lỗi và nguyên nhân sâu hơn. Khi chẩn đoán, hãy đọc cả exception gốc thay vì chỉ nhìn lớp exception bên ngoài.

Một quy trình kiểm tra hữu ích:

1. Ghi nhận `message.getPayload().getClass().getName()` ngay trước endpoint lỗi.
2. Kiểm tra các header mà chữ ký handler yêu cầu, đặc biệt `contentType`, `correlationId` và header nghiệp vụ.
3. Đối chiếu kiểu runtime của payload với kiểu tham số handler.
4. Nếu cần chuyển đổi, xác minh converter đã được đăng ký trong conversion service hoặc message converter mà endpoint thực sự sử dụng.
5. Với flow bất đồng bộ hoặc có poller, kiểm tra error channel và nơi nhận `ErrorMessage`.

Không nên dùng `Object` cho mọi tham số chỉ để né lỗi kiểu. Cách đó đẩy việc kiểm tra và ép kiểu vào sâu trong nghiệp vụ, khiến hợp đồng của endpoint khó đọc và lỗi khó định vị hơn.

## 8. Kiểm thử hợp đồng kiểu ở từng boundary

Kiểm thử nên xác nhận cả kiểu payload và metadata cần thiết, không chỉ xác nhận rằng flow không ném exception.

Ví dụ, kiểm thử bước giải mã độc lập:

```java
Message<String> input = MessageBuilder
        .withPayload("{\"id\":\"ORD-1001\"}")
        .setHeader("tenantId", "tenant-42")
        .build();

Order order = orderEndpoints.decode(input.getPayload());

assertThat(order.getId()).isEqualTo("ORD-1001");
```

Với kiểm thử tích hợp flow, gửi message qua channel đầu vào và xác nhận:

- Payload ở channel sau transformer có đúng kiểu DTO mong đợi.
- Giá trị payload đã được chuẩn hóa hoặc giải mã chính xác.
- Các header nghiệp vụ cần thiết vẫn có mặt ở endpoint kế tiếp.
- Payload sai định dạng hoặc thiếu header bắt buộc tạo ra lỗi có thể quan sát và định tuyến.

Nếu dùng converter tùy chỉnh, kiểm thử riêng converter với dữ liệu hợp lệ, dữ liệu rỗng và dữ liệu sai định dạng. Điều này giúp phân biệt lỗi của quy tắc chuyển đổi với lỗi điều phối message.

## 9. Nguyên tắc thiết kế

- **Đặt hợp đồng kiểu ở đầu flow**: xác định payload đầu vào là bytes, text hay DTO và chuẩn hóa sớm.
- **Dùng transformer cho biến đổi có ý nghĩa nghiệp vụ**: JSON thành DTO, chuẩn hóa mã hoặc ánh xạ schema nên là bước có tên và có thể kiểm thử.
- **Dùng ConversionService cho chuyển đổi kiểu nhỏ, xác định**: số, enum hoặc các kiểu đơn giản có quy tắc rõ ràng.
- **Không trông chờ channel đổi payload**: channel điều phối việc gửi, nhận hoặc lưu message; endpoint/converter mới xử lý kiểu dữ liệu.
- **Giữ metadata có chủ đích**: phân biệt header nghiệp vụ với header điều khiển flow và kiểm thử những header cần đi xuyên suốt.
- **Ưu tiên chữ ký handler cụ thể**: dùng `Order` nếu handler cần `Order`; dùng `Message<?>` khi thực sự cần truy cập envelope.
- **Quan sát lỗi ở đúng execution model**: luồng đồng bộ có thể trả lỗi về sender, còn executor hoặc poller cần được kiểm tra qua error handling của flow.

Trước khi nối một handler mới vào flow, hãy trả lời ba câu hỏi: payload thực tế có kiểu gì, handler yêu cầu kiểu gì và bước nào chịu trách nhiệm chuyển đổi nếu hai kiểu khác nhau. Khi ba điều này được thể hiện rõ, lỗi tại handler boundary dễ dự đoán, kiểm thử và chẩn đoán hơn.
