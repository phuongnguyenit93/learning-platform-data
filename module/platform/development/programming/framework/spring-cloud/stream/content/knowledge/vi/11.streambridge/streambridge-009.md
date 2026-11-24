# Chế độ gửi bất đồng bộ và truyền ngữ cảnh theo phiên bản hỗ trợ

`StreamBridge` cho phép một thành phần không được kích hoạt bởi binding đầu vào của Spring Cloud Stream gửi dữ liệu tới output binding. Nguồn dữ liệu có thể là REST controller, tác vụ định kỳ, callback từ thư viện bên ngoài hoặc một luồng nghiệp vụ Spring MVC truyền thống. `StreamBridge` đưa dữ liệu vào cùng cơ chế output của Spring Cloud Stream, bao gồm chuyển đổi kiểu dữ liệu và phân vùng theo cấu hình producer.

Mặc định, thao tác gửi dùng thread của bên gọi và có tính blocking. Từ Spring Cloud Stream 4.1.1, API `StreamBridge.setAsync(true)` cho phép chuyển việc gửi qua một kênh thực thi bất đồng bộ. Khi công việc đi qua thread khác, các ngữ cảnh được giữ trong `ThreadLocal` có thể không còn hiện diện. Micrometer Context Propagation giúp truyền các context đã đăng ký, đặc biệt là ngữ cảnh Observation/Tracing, qua ranh giới thread này.

Hai cơ chế cần được hiểu riêng: gửi bất đồng bộ thay đổi cách thread thực hiện việc dispatch message; truyền ngữ cảnh giữ các metadata gắn với luồng thực thi khi đổi thread. Cả hai đều không tự tạo bảo đảm message đã được broker lưu bền vững hoặc consumer đã xử lý thành công.

## 1. Khi nào dùng StreamBridge?

Mô hình hàm `Supplier`, `Function` và `Consumer` là lựa chọn tự nhiên khi nguồn và đích dữ liệu đã được biểu diễn thành các binding của ứng dụng. Nhưng có những thành phần phát sinh dữ liệu bên ngoài mô hình đó. Ví dụ:

- REST endpoint tiếp nhận yêu cầu tạo đơn hàng rồi phát sự kiện `OrderCreated`.
- Tác vụ định kỳ đọc dữ liệu từ hệ thống cũ và gửi bản ghi sang broker.
- Callback từ thư viện thanh toán cần phát sự kiện `PaymentCompleted`.
- Một dịch vụ Spring MVC cần gửi thông điệp sang Kafka, RabbitMQ hoặc Pulsar mà không phải khai báo một `Supplier` chỉ để gọi thủ công.

Trong các tình huống này, `StreamBridge` cung cấp cách gửi tới output binding bằng tên binding:

```java
streamBridge.send("orders-out-0", orderCreated);
```

Đối số đầu tiên là tên output binding. Đối số thứ hai là object hoặc `Message<?>` cần gửi. Nếu truyền POJO, Spring Cloud Stream áp dụng quy trình output conversion và partitioning theo binding. Nếu truyền `Message`, các header của message cũng được đưa vào quá trình xử lý output.

`StreamBridge` không thay thế toàn bộ mô hình hàm. Nếu nguồn dữ liệu vốn là một `Supplier` được framework quản lý, hãy để function binding đảm nhiệm việc phát dữ liệu. `StreamBridge` hữu ích khi nguồn phát nằm ngoài cơ chế kích hoạt đó hoặc khi mã ứng dụng cần chủ động gửi tại một điểm cụ thể.

## 2. Gửi đồng bộ là mặc định

Mặc định, `StreamBridge.send(...)` dùng thread của bên gọi. Nếu REST controller gọi `send`, thread xử lý request sẽ thực hiện thao tác gửi qua output channel. Điều này có nghĩa request có thể phải chờ phần gửi hoàn tất ở mức mà channel/binder đang thực hiện.

Gửi đồng bộ phù hợp khi:

- Lưu lượng thấp hoặc vừa và độ trễ gửi không ảnh hưởng đáng kể tới request.
- Bên gọi cần biết ngay thao tác gửi có được channel chấp nhận hay không.
- Cần giữ ngữ cảnh thread hiện tại trong suốt quá trình gọi.
- Muốn luồng xử lý đơn giản và dễ quan sát khi gỡ lỗi.

Ví dụ một endpoint gửi đồng bộ:

```java
@RestController
public class OrderController {
    private final StreamBridge streamBridge;

    public OrderController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    public ResponseEntity<Void> create(@RequestBody OrderCreated event) {
        boolean accepted = streamBridge.send("orders-out-0", event);
        return accepted
                ? ResponseEntity.accepted().build()
                : ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

Giá trị boolean cho biết thao tác gửi được output channel chấp nhận theo hợp đồng của channel. Nó không phải bằng chứng rằng broker đã ghi bền vững message, consumer đã nhận hoặc nghiệp vụ đã hoàn tất. Với binder hỗ trợ xác nhận gửi bất đồng bộ, cần xử lý kết quả gửi theo cơ chế riêng của binder.

## 3. Bật async send theo phiên bản hỗ trợ

API `setAsync(boolean)` được bổ sung cho `StreamBridge` từ Spring Cloud Stream 4.1.1. Với phiên bản này hoặc mới hơn có hỗ trợ API, gọi `setAsync(true)` trước khi gửi để bật chế độ bất đồng bộ:

```java
@Configuration
public class StreamBridgeConfiguration {

    @Bean
    ApplicationRunner enableAsyncStreamBridge(StreamBridge streamBridge) {
        return args -> streamBridge.setAsync(true);
    }
}
```

Thiết lập một lần khi ứng dụng khởi động. `StreamBridge` là bean được chia sẻ trong ứng dụng; không nên bật/tắt `setAsync` theo từng request vì nhiều request có thể chạy đồng thời và cùng sử dụng một cấu hình. Nếu cần hai chính sách gửi khác nhau, hãy thiết kế hai luồng gửi có chủ đích và kiểm tra khả năng của phiên bản đang dùng.

Khi dùng async send, lời gọi `send` có thể trả về trước khi việc gửi qua channel hoàn tất. Thread của request không phải chờ toàn bộ công việc gửi như chế độ mặc định. Điều này hữu ích khi endpoint cần tiếp nhận nhanh, nhưng cũng có nghĩa lỗi phát sinh sau khi dispatch có thể không được ném trực tiếp về thread đã gọi.

Async send không có nghĩa mọi bước trong `StreamBridge.send` đều chạy ở thread nền. Việc phân giải binding, chuẩn bị message và một phần chuyển đổi payload có thể diễn ra trước khi message được chuyển vào output channel. Vì vậy, vẫn cần đo thời gian thực tế với binder và phiên bản đang dùng; không xem `setAsync(true)` như cam kết rằng toàn bộ lời gọi luôn không blocking.

### 3.1. Khai báo output binding

Với destination đã biết trước, nên khai báo binding rõ ràng trong `application.yml`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          content-type: application/json
```

`destination` là topic, exchange hoặc đích logic được binder ánh xạ tới broker. Tên binding trong lời gọi `send` phải khớp với tên đã khai báo. Với cấu hình trên, `StreamBridge` có thể tạo output binding khi gửi lần đầu và tái sử dụng cho các lần tiếp theo.

Nếu muốn tạo binding trước khi ứng dụng nhận request, có thể khai báo thêm `spring.cloud.stream.output-bindings` với tên output binding. Việc tạo channel trước và cách `setAsync(true)` áp dụng cho channel đó có thể phụ thuộc đường tạo binding và phiên bản cụ thể; hãy xác minh bằng kiểm thử tích hợp thay vì giả định mọi channel có sẵn đều được chuyển thành executor channel.

Cách tạo binding động tiện lợi khi destination chỉ biết tại runtime, nhưng cần giới hạn tập destination và theo dõi cache. Một ứng dụng tạo ra số lượng destination động không giới hạn có thể tăng bộ nhớ và chi phí tạo binding.

### 3.2. Phiên bản cũ hơn

Nếu dự án dùng Spring Cloud Stream trước 4.1.1, không giả định `StreamBridge.setAsync(true)` có sẵn. Hãy kiểm tra Javadoc đúng phiên bản trong dependency đang dùng. Nếu cần gửi bất đồng bộ trên phiên bản chưa hỗ trợ API này, có thể dùng executor do ứng dụng quản lý để gọi `send` từ tác vụ nền, nhưng khi đó ứng dụng phải tự quản lý vòng đời executor, giới hạn hàng đợi, từ chối tác vụ, lỗi nền và truyền context. Cần tránh dùng executor không giới hạn hoặc tạo một thread mới cho mỗi request.

Không nâng riêng Spring Cloud Stream lên một phiên bản tùy ý để có API mới. Hãy chọn release train Spring Cloud tương thích với Spring Boot của dự án, sau đó dùng BOM tương ứng để quản lý phiên bản thư viện.

## 4. Ví dụ REST endpoint gửi bất đồng bộ và mang metadata nghiệp vụ

Một message có thể mang `eventId` và `correlationId` để các dịch vụ tiếp theo liên kết sự kiện với yêu cầu ban đầu. Những giá trị nghiệp vụ này nên được đưa vào payload hoặc header một cách tường minh, thay vì chỉ tồn tại trong `ThreadLocal` hoặc MDC của thread HTTP.

```java
@RestController
public class OrderIngressController {
    private final StreamBridge streamBridge;

    public OrderIngressController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    public ResponseEntity<Void> publish(
            @RequestBody OrderCreated event,
            @RequestHeader(value = "X-Correlation-Id", required = false)
                    String correlationId) {

        MessageBuilder<OrderCreated> builder = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId());

        if (correlationId != null && !correlationId.isBlank()) {
            builder.setHeader("correlationId", correlationId);
        }

        boolean accepted = streamBridge.send("orders-out-0", builder.build());
        return accepted
                ? ResponseEntity.accepted().build()
                : ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

Trong ứng dụng, `setAsync(true)` được gọi một lần lúc khởi động như ví dụ ở phần trước. Endpoint chỉ tạo message và gửi. Header `eventId` giữ định danh sự kiện nghiệp vụ; `correlationId` nối message với request hoặc các bước xử lý liên quan. Nếu hệ thống có quy tắc định dạng ID, hãy xác thực trước khi gửi.

HTTP `202 Accepted` ở ví dụ chỉ biểu thị ứng dụng đã chấp nhận yêu cầu gửi theo kết quả mà `StreamBridge.send` trả về. Nó không xác nhận message đã được broker lưu hoặc consumer xử lý. Nếu API cần cam kết mạnh hơn, phải thiết kế phản hồi dựa trên cơ chế xác nhận thực tế của broker hoặc trạng thái nghiệp vụ được lưu bền vững.

## 5. Truyền Observability context qua ranh giới thread

Trong chế độ đồng bộ, mã gửi chạy trên thread của bên gọi. Các context dựa trên `ThreadLocal` có thể được đọc trong cùng thread. Khi chuyển sang async send, công việc được thực hiện ở thread khác. `ThreadLocal` của thread HTTP không tự xuất hiện ở thread gửi.

Điều này có thể ảnh hưởng đến:

- Trace/span hiện tại và quan hệ cha-con của distributed trace.
- Observation context dùng để liên kết metric và trace.
- MDC hoặc thông tin log gắn với thread.
- Context tùy chỉnh do ứng dụng giữ trong `ThreadLocal`.

Spring Cloud Stream hỗ trợ Micrometer Context Propagation cho async send. Thêm dependency `io.micrometer:context-propagation` tương thích với BOM của dự án:

```kotlin
dependencies {
    implementation("io.micrometer:context-propagation")
}
```

Nếu dependency được quản lý bởi Spring Boot/Spring Cloud BOM, để BOM chọn phiên bản tương thích thay vì ghim một phiên bản cũ trong build file. Với dự án không dùng BOM, cần chọn phiên bản Micrometer Context Propagation tương thích với phiên bản Spring Cloud Stream và Micrometer đang sử dụng.

Khi thư viện có mặt, các phiên bản Spring Cloud Stream hỗ trợ cơ chế này có thể bọc executor của `StreamBridge` bằng context-aware executor để capture context đã đăng ký ở thread gửi và khôi phục nó khi tác vụ chạy. Cần bật async send và cấu hình Observability/Tracing phù hợp của ứng dụng; chỉ thêm dependency không tự bật toàn bộ tracing nếu hệ thống chưa cấu hình Observation hoặc tracer.

### 5.1. Context propagation không thay thế message headers

Micrometer Context Propagation xử lý context giữa các thread trong cùng tiến trình. Khi message đã đi qua broker sang một tiến trình khác, `ThreadLocal` của producer không tồn tại ở consumer. Muốn truyền metadata nghiệp vụ qua broker, hãy đặt chúng vào payload hoặc message headers:

| Loại thông tin | Cách truyền phù hợp |
|---|---|
| Trace/span context | Dùng tích hợp Observability/Tracing và propagation headers được hỗ trợ bởi Spring/binder |
| `correlationId`, `tenantId`, `eventId` | Đặt rõ trong payload hoặc custom header theo hợp đồng ứng dụng |
| Thông tin xác thực hoặc bí mật | Dùng cơ chế bảo mật phù hợp; không đưa token nhạy cảm vào header message nếu không có thiết kế bảo vệ |
| Biến tạm chỉ phục vụ logging trong một request | MDC hoặc context cục bộ; không coi đó là dữ liệu bền vững của message |

Nếu ứng dụng dùng `ThreadLocal` riêng, Micrometer chỉ có thể truyền giá trị khi accessor tương ứng được đăng ký với Context Propagation. Không giả định mọi `ThreadLocal`, MDC hoặc `SecurityContext` tùy chỉnh đều tự động được sao chép. Hãy kiểm tra accessor mà thư viện tích hợp cung cấp hoặc đăng ký accessor cho context riêng theo API của phiên bản Micrometer đang dùng.

## 6. Phân biệt các loại bất đồng bộ

Trong một ứng dụng Spring Cloud Stream có thể có nhiều lớp async khác nhau. Chúng giải quyết các vấn đề khác nhau:

| Cơ chế | Tác động | Điều không tự bảo đảm |
|---|---|---|
| `StreamBridge.setAsync(true)` | Chuyển dispatch qua output channel sang cơ chế thực thi bất đồng bộ của StreamBridge | Không xác nhận broker đã lưu message |
| Producer client của broker gửi bất đồng bộ | Client có thể gửi nền và trả kết quả qua callback/future theo API riêng | Không tự truyền context của thread gọi StreamBridge |
| Micrometer Context Propagation | Capture/restore context đã đăng ký khi tác vụ đổi thread | Không serialize context thành dữ liệu nghiệp vụ qua broker |
| `@Async` hoặc executor của ứng dụng | Chạy phương thức gửi trong executor do ứng dụng quản lý | Không tự cấu hình binder, retry, xác nhận hoặc DLQ |
| Reactive API | Biểu diễn chuỗi xử lý bằng `Publisher` và các toán tử | Không biến binder blocking thành reactive hoặc tạo back-pressure xuyên hệ thống |

Không nên bật nhiều lớp async chỉ vì muốn endpoint phản hồi nhanh. Mỗi ranh giới thread bổ sung đều làm tăng độ phức tạp về context, thứ tự, lỗi và shutdown. Chọn một điểm chịu trách nhiệm rõ ràng cho việc dispatch và kiểm thử toàn bộ đường đi.

## 7. Xử lý kết quả gửi và lỗi bất đồng bộ

Trong async send, lỗi có thể xuất hiện sau khi thread gọi đã nhận kết quả từ `send`. Vì vậy, không chỉ dựa vào boolean trả về để theo dõi việc publish. Cần kiểm tra các cơ chế sau theo binder và phiên bản:

1. **Lỗi trước dispatch:** lỗi tạo binding, chuyển đổi payload hoặc cấu hình producer có thể xuất hiện ngay trong lời gọi.
2. **Lỗi ở channel/executor:** tác vụ có thể không được chấp nhận hoặc gặp lỗi khi thực thi nền.
3. **Lỗi từ producer client:** broker có thể từ chối hoặc không xác nhận việc gửi sau khi tác vụ đã được dispatch.
4. **Lỗi sau khi broker nhận:** consumer có thể xử lý thất bại; đây là bài toán retry/DLQ ở phía nhận, khác với lỗi publish.

Với binder hỗ trợ asynchronous send results, producer property `errorChannelEnabled` có thể chuyển lỗi gửi vào error channel của destination:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          producer:
            error-channel-enabled: true
```

Thuộc tính này chỉ có tác dụng khi binder hỗ trợ kết quả gửi bất đồng bộ và được cấu hình theo đúng phiên bản. Nó không phải một callback chung bảo đảm bắt mọi exception từ executor hoặc mọi lỗi nghiệp vụ của consumer. Hãy kiểm tra tài liệu binder đang dùng và đăng ký handler/monitor cho error channel phù hợp.

Theo dõi tối thiểu số lần gửi được yêu cầu, số lần channel từ chối, lỗi producer, thời gian gửi, số message vào error channel và số message được consumer xử lý. Log nên có `eventId`, `correlationId`, binding và destination để điều tra một message xuyên suốt các thành phần.

## 8. Bảo đảm giao nhận và thứ tự

Async send cải thiện khả năng tách request thread khỏi công việc gửi, nhưng không tăng mức bảo đảm giao nhận của broker. Nó không tự cung cấp exactly-once, không thay transaction và không bảo đảm message sẽ còn tồn tại nếu tiến trình dừng khi tác vụ đang chờ.

Với sự kiện quan trọng về nghiệp vụ, cân nhắc các nguyên tắc sau:

- Lưu thay đổi nghiệp vụ và bản ghi outbox trong cùng một transaction database; một publisher riêng đọc outbox rồi gửi qua `StreamBridge`.
- Dùng `eventId` ổn định và consumer idempotent để xử lý message giao lại.
- Nếu binder/broker cung cấp producer confirms, acknowledgements hoặc transaction, cấu hình và kiểm tra chúng theo đúng broker.
- Không trả lời HTTP thành công với ý nghĩa “đã giao bền vững” nếu ứng dụng mới chỉ biết channel đã nhận tác vụ gửi.
- Khi shutdown, có chính sách drain hoặc xử lý lại các tác vụ chưa hoàn tất; không dựa vào bộ nhớ của executor làm hàng đợi bền vững.

Việc gửi từ nhiều thread cũng có thể làm thứ tự hoàn tất khác với thứ tự request đến. Nếu các sự kiện của cùng một đơn hàng phải theo thứ tự, hãy dùng khóa nghiệp vụ làm partition key, bảo đảm các sự kiện cùng khóa đi tới cùng partition/queue theo khả năng binder, và thiết kế consumer để xử lý thứ tự theo ngữ nghĩa broker. Không suy ra thứ tự chỉ từ thứ tự gọi `send` trên các thread khác nhau.

## 9. Kiểm thử async send và context propagation

Kiểm thử nên xác nhận cả việc gửi lẫn những gì xảy ra sau khi đổi thread. Có thể dùng `StreamOperations` trong service để dễ thay thế bằng mock trong unit test; `StreamBridge` triển khai hợp đồng này.

Các nhóm kiểm thử cần có:

- **Unit test:** xác nhận đúng binding name, payload, `eventId`, `correlationId` và content type được truyền tới `send`.
- **Async behavior test:** xác nhận caller không phải chờ tác vụ gửi hoàn tất trong tình huống async; dùng latch hoặc đồng bộ hóa trong test thay vì `Thread.sleep` tùy tiện.
- **Context test:** tạo Observation/trace hoặc context đã đăng ký trước khi gọi send, rồi xác nhận tác vụ nền nhìn thấy context tương ứng.
- **Custom ThreadLocal test:** xác nhận accessor đã đăng ký capture và restore giá trị; đồng thời xác nhận giá trị được dọn sau khi task hoàn tất để tránh rò context giữa các task.
- **Integration test:** dùng broker thật hoặc môi trường kiểm thử tương đương để xác nhận message được nhận, header cần thiết còn nguyên và lỗi producer được quan sát.
- **Failure test:** mô phỏng broker từ chối, executor không nhận tác vụ, ứng dụng shutdown khi còn tác vụ và consumer xử lý lỗi.
- **Ordering test:** gửi nhiều message có cùng key và xác nhận thứ tự theo bảo đảm thực tế của binder/broker.

Không nên chỉ kiểm tra rằng `send()` trả về `true`. Một kiểm thử tích hợp cần chứng minh message thực sự xuất hiện ở destination hoặc consumer nhận được payload theo hợp đồng.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy `setAsync` khi biên dịch | Spring Cloud Stream cũ hơn 4.1.1 hoặc dependency/BOM không tương thích | Kiểm tra phiên bản thực tế và chọn release train tương thích |
| Trace bị đứt sau khi bật async | Context không được truyền qua executor hoặc thiếu cấu hình Observability | Thêm Micrometer Context Propagation tương thích và kiểm tra tracer/accessor |
| `correlationId` không có ở consumer | Chỉ lưu giá trị trong MDC/ThreadLocal mà không đưa vào message | Gắn header hoặc payload trước khi gọi `send` |
| `send()` trả `true` nhưng consumer không nhận | Giá trị boolean không xác nhận toàn bộ quá trình broker/consumer | Kiểm tra producer result, broker metric, destination và consumer group |
| Exception không xuất hiện trong REST request | Lỗi phát sinh sau khi tác vụ đã được dispatch | Theo dõi error channel/log/metric theo binder và thiết kế xử lý bù |
| Sự kiện cùng đơn hàng đến sai thứ tự | Nhiều thread gửi song song hoặc partition key không nhất quán | Chọn partition key ổn định và kiểm thử thứ tự trên broker |
| Mất sự kiện khi ứng dụng dừng | Tác vụ gửi còn trong bộ nhớ executor, không có kho bền vững | Dùng outbox hoặc cơ chế lưu trữ và phát lại bền vững |
| Context của request trước xuất hiện ở task sau | Accessor không reset context hoặc tái sử dụng thread không đúng cách | Kiểm tra accessor, scope và việc dọn context sau task |

## 11. Danh sách kiểm tra trước khi triển khai

- [ ] Dùng `StreamBridge` cho nguồn dữ liệu bên ngoài mô hình function binding.
- [ ] Phiên bản Spring Cloud Stream hỗ trợ `setAsync(true)`; API có từ 4.1.1.
- [ ] Async mode được cấu hình một lần khi khởi động, không bật/tắt tùy tiện theo request.
- [ ] Output binding và destination được khai báo rõ nếu biết trước; dynamic destinations có giới hạn.
- [ ] Đã phân biệt channel acceptance với xác nhận broker và xử lý của consumer.
- [ ] Micrometer Context Propagation và Observability/Tracing được cấu hình tương thích.
- [ ] Context tùy chỉnh có accessor; dữ liệu nghiệp vụ cần đi qua broker được đặt trong payload/header.
- [ ] Lỗi gửi bất đồng bộ có error handling và metric phù hợp với binder.
- [ ] Có idempotency, outbox hoặc cơ chế tương đương cho sự kiện quan trọng.
- [ ] Đã kiểm thử context, lỗi gửi, shutdown và thứ tự message trong cấu hình triển khai.

`StreamBridge.setAsync(true)` giúp tách việc dispatch message khỏi thread gọi khi phiên bản Spring Cloud Stream hỗ trợ. Micrometer Context Propagation giữ các context đã đăng ký qua ranh giới thread để trace và log không bị đứt. Ứng dụng vẫn phải truyền metadata nghiệp vụ qua message, theo dõi lỗi sau dispatch và dùng cơ chế bền vững như outbox khi không thể chấp nhận mất sự kiện.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream 4.1.1 release notes — async send for StreamBridge](https://github.com/spring-cloud/spring-cloud-stream/releases/tag/v4.1.1)
