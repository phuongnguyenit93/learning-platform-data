# `@Transformer`, `@Filter` và `@Router` method trong Spring Integration

## 1. Vị trí của ba method trong message flow

Trong Spring Integration, một message gồm **payload** (dữ liệu nghiệp vụ) và **headers** (metadata như `id`, `replyChannel`, `errorChannel`, mã tương quan). `MessageChannel` chuyển message giữa các endpoint; endpoint lấy message từ channel, gọi thành phần xử lý và quyết định bước tiếp theo.

Ba annotation thuộc nhóm **handler adapter**: Spring Integration có thể gọi phương thức Java thông thường (POJO) như một message endpoint mà không buộc mã nghiệp vụ phải tự triển khai `MessageHandler`. Chúng giải quyết ba câu hỏi khác nhau:

| Annotation trên method | Câu hỏi xử lý | Giá trị trả về | Kết quả ở runtime |
| --- | --- | --- | --- |
| `@Transformer` | Message cần **đổi dữ liệu/định dạng** như thế nào? | Payload mới hoặc `Message<?>` mới, **không được `null`** | Tạo message đầu ra rồi gửi đến output channel. |
| `@Filter` | Message này có **được đi tiếp** không? | `boolean` hoặc `Boolean` | `true`: chuyển nguyên message sang output; `false`: từ chối, có thể discard hoặc báo lỗi. |
| `@Router` | Message nên **đi vào channel nào**? | Tên channel, `MessageChannel` hoặc tập hợp các đích | Gửi message đến một hay nhiều channel được chọn. |

Ví dụ quy trình tiếp nhận đơn hàng:

~~~mermaid
flowchart LR
    A["ordersIn"] --> T["@Transformer normalize()"]
    T --> N["normalized"]
    N --> F{"@Filter valid()"}
    F -->|true| R["@Router route()"]
    F -->|false| D["rejected"]
    R -->|priority| P["priority"]
    R -->|standard| S["standard"]
~~~

Một nhầm lẫn quan trọng: nếu method `@Transformer` trả về chuỗi `"priority"`, chuỗi đó được hiểu là **payload mới**, không phải tên channel. Trái lại, khi method `@Router` trả về `"priority"`, đó là **địa chỉ đích**. `@Filter` trả về `true`/`false` để quyết định tiếp nhận, không để tạo payload Boolean.

## 2. Từ annotation đến endpoint thực thi

Quá trình diễn ra theo những bước chính:

1. Spring đăng ký bean có các method được đánh dấu, thường qua `@MessageEndpoint` (stereotype có tính chất `@Component`) và component scanning; bật hạ tầng Spring Integration qua `@EnableIntegration` hoặc cấu hình tự động phù hợp.
2. Bộ xử lý annotation tạo **consumer endpoint** cùng **message handler/adapter** tương ứng; method Java được gọi qua cơ chế ánh xạ tham số dựa trên payload, headers và kiểu dữ liệu.
3. Endpoint đăng ký nhận từ `inputChannel`. Với channel có khả năng đăng ký subscriber (như `DirectChannel`), endpoint thường chạy theo sự kiện; với `QueueChannel`, cần polling consumer và poller để chủ động lấy message.
4. Handler diễn giải giá trị trả về theo vai trò transformer, filter hoặc router rồi gửi message tiếp theo. Cấu hình channel, advice, transaction và executor quyết định cách việc gửi thực sự xảy ra.

Vì vậy **annotation mô tả hành vi endpoint**, không tự tạo luồng xử lý nền, cơ chế retry, transaction hoặc lưu bền vững. Một `IntegrationFlow` có thể ghép các endpoint này với channel, poller, executor, gateway, error flow và message store; bản thân các method vẫn chỉ đảm nhiệm logic đã khai báo.

Khi một method có `inputChannel = "normalized"`, đó là **đầu vào** của endpoint. `outputChannel = "accepted"` (nếu annotation hỗ trợ) là nơi trả message đi tiếp. Nếu endpoint tạo reply mà không chỉ rõ output channel, cơ chế reply có thể tìm `replyChannel` trong headers. Riêng router chọn đích bằng kết quả route và thuộc tính định tuyến thay vì có một output channel chung.

## 3. Cách khai báo method và ánh xạ tham số

Các method có thể nhận toàn bộ `Message<T>`, chỉ payload kiểu `T`, một hoặc nhiều giá trị header qua `@Header`, hoặc bản đồ headers qua `@Headers`:

~~~java
@Transformer(inputChannel = "raw", outputChannel = "clean")
public Customer normalize(CustomerInput input,
                          @Header(value = "tenant", required = false) String tenant) {
    return new Customer(input.id().trim(), tenant);
}

// Dạng thay thế: lấy Message để chủ động xem cả payload và headers.
@Filter(inputChannel = "clean", outputChannel = "accepted")
public boolean acceptable(Message<Customer> message) {
    return message.getPayload().id() != null
            && !message.getPayload().id().isBlank();
}

// Dạng thay thế: quyết định chỉ từ metadata, không cần lấy payload.
@Router(inputChannel = "toRoute")
public String routeByTier(@Header("tier") String tier) {
    return "gold".equals(tier) ? "priority" : "standard";
}
~~~

Đây là **ba ví dụ chữ ký độc lập**, không phải toàn bộ chương trình chạy ngay. Cần khai báo các channel đích và consumer tương ứng.

- `@Header("tier")` đọc một header; mặc định header được yêu cầu phải hiện diện. Dùng `required = false` và xử lý `null` khi header có thể vắng.
- `@Headers Map<String, Object>` cho phép xem toàn bộ headers. Có thể dùng `@Payload` để chỉ định rõ tham số payload trong các chữ ký phức tạp.
- Payload có thể được chuyển đổi nhờ các converter phù hợp với hạ tầng message conversion; lỗi chuyển đổi hoặc method không tương thích có thể xuất hiện lúc xử lý message.
- Tránh overload cùng tên với kiểu tham số khó phân biệt nếu không cần thiết; chữ ký rõ ràng giúp việc chọn method ổn định và dễ chẩn đoán.

### `@Transformer`: đổi payload mà không làm rơi message

Ví dụ nhập `OrderRequest` và trả về `Order` là đúng vai trò của transformer. Khi method trả về một đối tượng nghiệp vụ, Spring Integration tạo message có payload mới; các headers phù hợp của request được chuyển tiếp theo cơ chế xây dựng reply. Khi method trả về `Message<?>`, phương thức có thể chủ động tạo payload và headers của message đầu ra.

**Không dùng `return null` để loại bỏ message.** Transformer yêu cầu reply; trả về `null` dẫn đến lỗi `MessageTransformationException`. Nếu mục đích là chặn message, đặt một `@Filter` riêng. Trả về `void` cũng không phù hợp với transformer.

Ví dụ khi cần chủ động chỉnh header:

~~~java
@Transformer(inputChannel = "raw", outputChannel = "clean")
public Message<String> normalize(Message<String> inbound) {
    return MessageBuilder.withPayload(inbound.getPayload().trim())
            .copyHeaders(inbound.getHeaders())
            .setHeader("normalized", true)
            .build();
}
~~~

`MessageBuilder` quản lý các header hệ thống như ID và timestamp theo quy tắc tạo message; không giả định mọi header hệ thống sẽ có giá trị y hệt message nguồn.

### `@Filter`: nhận hoặc từ chối message

Với method trả về `true`, filter chuyển tiếp **message đang xét**, không thay payload theo giá trị Boolean. Với `false`, có ba cách xử lý chính:

| Cấu hình | Hành vi đối với message bị từ chối |
| --- | --- |
| Không có `discardChannel`, mặc định không ném ngoại lệ | Bỏ message; các phiên bản mới có thể ghi log cảnh báo về việc discard. |
| `discardChannel = "rejected"` | Chuyển message bị từ chối tới channel `rejected` để ghi nhận, kiểm tra hoặc xử lý riêng. |
| `throwExceptionOnRejection = "true"` | Ném ngoại lệ khi từ chối, phù hợp nếu việc từ chối phải được xem là lỗi của flow. |

Ví dụ cấu hình minh bạch:

~~~java
@Filter(
    inputChannel = "clean",
    outputChannel = "accepted",
    discardChannel = "rejected")
public boolean isValid(Customer customer) {
    return customer.id() != null && !customer.id().isBlank();
}
~~~

Có thể dùng bean `nullChannel` làm discard channel nếu việc bỏ message thực sự là chủ đích và không muốn cảnh báo discard. Không đồng thời thiết kế cùng một trường hợp vừa “loại bỏ bình thường” vừa “bắt buộc báo lỗi” nếu chưa xác định quy tắc nghiệp vụ. Method nên trả về kết quả Boolean có nghĩa rõ ràng; đừng trả về `null` từ kiểu `Boolean`.

### `@Router`: chọn một hoặc nhiều channel

Các chữ ký hợp lệ thường gặp:

~~~java
@Router(inputChannel = "toRoute")
public String choose(Order order) {
    return order.urgent() ? "priority" : "standard";
}

// Biến thể độc lập: gửi cùng message đến nhiều nhánh.
@Router(inputChannel = "broadcastInput", applySequence = "true")
public List<String> chooseMany(Order order) {
    return List.of("audit", "fulfillment");
}
~~~

Router có thể trả về `String`, `MessageChannel`, mảng hoặc collection các phần tử thuộc các loại này. Với tên dạng chuỗi, endpoint phải phân giải tên thành channel có thực. `channelMappings` ánh xạ route key sang tên channel; `prefix` và `suffix` thay đổi tên trước khi phân giải.

Các tùy chọn đáng quan tâm:

| Thuộc tính của `@Router` | Ý nghĩa |
| --- | --- |
| `defaultOutputChannel` | Đích dự phòng khi không xác định được destination và chế độ resolution cho phép. |
| `resolutionRequired` (mặc định `true`) | Yêu cầu route key phải phân giải được; nếu không thì phát sinh lỗi. `"false"` cho phép bỏ qua đích không phân giải được, kết hợp đích dự phòng nếu cấu hình. |
| `channelMappings` | Khai báo ánh xạ dạng `{"VIP=priority", "NORMAL=standard"}`, tách khóa nghiệp vụ khỏi bean channel. |
| `applySequence` | Bổ sung metadata thứ tự/kích thước chuỗi trong tình huống phân phối đến nhiều đích khi được bật; hữu ích cho luồng gom kết quả. |
| `ignoreSendFailures` | Ảnh hưởng cách router xử lý lỗi gửi message đến một đích, nhất là khi có nhiều đích. |

**Gửi nhiều đích không có nghĩa mọi nhánh đều thành công**: nếu dùng các channel đồng bộ, lỗi tại một nhánh có thể ngăn gửi tiếp sang nhánh sau (khi không bỏ qua send failure). Đừng dựa vào route đa đích như một cơ chế phát sự kiện bảo đảm giao hàng.

## 4. Ví dụ hoàn chỉnh: phân loại đơn hàng ở runtime

Ví dụ dưới đây dùng Java record (Java 17+) và Spring Boot có Spring Integration. Các class được đặt cùng package được component scan. Mỗi đầu vào đi qua ba method theo thứ tự: chuẩn hóa → xác thực → định tuyến. Những channel đều là `DirectChannel` để dễ nhìn thấy hành vi đồng bộ.

~~~java
package demo.integration;

import java.util.Locale;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Router;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean MessageChannel ordersIn()   { return new DirectChannel(); }
    @Bean MessageChannel normalized() { return new DirectChannel(); }
    @Bean MessageChannel accepted()   { return new DirectChannel(); }
    @Bean MessageChannel priority()   { return new DirectChannel(); }
    @Bean MessageChannel standard()   { return new DirectChannel(); }
    @Bean MessageChannel rejected()   { return new DirectChannel(); }

    @Bean
    ApplicationRunner sample(@Qualifier("ordersIn") MessageChannel in) {
        return args -> {
            in.send(MessageBuilder.withPayload(
                    new OrderRequest("  a-01  ", 1_500_000))
                    .setHeader("traceId", "t-001").build());
            in.send(MessageBuilder.withPayload(
                    new OrderRequest(" b-02 ", 150_000))
                    .setHeader("traceId", "t-002").build());
            in.send(MessageBuilder.withPayload(
                    new OrderRequest("   ", -10))
                    .setHeader("traceId", "t-003").build());
        };
    }
}

record OrderRequest(String id, long amountMinorUnits) {}
record Order(String id, long amountMinorUnits) {}

@MessageEndpoint
class OrderMethods {

    @Transformer(inputChannel = "ordersIn", outputChannel = "normalized")
    public Order normalize(OrderRequest input) {
        return new Order(input.id().trim().toUpperCase(Locale.ROOT),
                         input.amountMinorUnits());
    }

    @Filter(inputChannel = "normalized",
            outputChannel = "accepted",
            discardChannel = "rejected")
    public boolean valid(Order order) {
        return !order.id().isBlank() && order.amountMinorUnits() > 0;
    }

    @Router(inputChannel = "accepted")
    public String route(Order order) {
        return order.amountMinorUnits() >= 1_000_000
                ? "priority" : "standard";
    }

    @ServiceActivator(inputChannel = "priority")
    public void onPriority(Order order) {
        System.out.println("PRIORITY " + order.id());
    }

    @ServiceActivator(inputChannel = "standard")
    public void onStandard(Order order) {
        System.out.println("STANDARD " + order.id());
    }

    @ServiceActivator(inputChannel = "rejected")
    public void onRejected(Order order) {
        System.out.println("REJECTED " + order.id());
    }
}
~~~

Để chạy ví dụ, dự án cần Spring Boot, starter Spring Integration phù hợp với phiên bản Spring Boot đang dùng, và package `demo.integration` nằm trong phạm vi component scan. Ví dụ dùng `System.out` để quan sát; ứng dụng thật nên dùng logging có cấu trúc, bao gồm mã tương quan và không ghi dữ liệu nhạy cảm.

| Message vào | Sau `normalize()` | `valid()` | Nhánh được gọi |
| --- | --- | --- | --- |
| `("  a-01  ", 1_500_000)` | `("A-01", 1_500_000)` | `true` | `priority` |
| `(" b-02 ", 150_000)` | `("B-02", 150_000)` | `true` | `standard` |
| `("   ", -10)` | `("", -10)` | `false` | `rejected`; router không được gọi |

Ở nhánh `rejected`, consumer nhận `Order` đã được transformer tạo, vì filter hoạt động **sau** transformer. Header `traceId` có thể được truy cập ở các bước bằng `@Header("traceId")`. Khi mọi channel là `DirectChannel`, lời gọi `send()` có thể chạy toàn bộ chuỗi handler trên cùng thread gọi; điều này quan trọng nếu một handler chặn I/O hoặc ném lỗi.

## 5. Threading, poller và transaction

Annotation không quyết định riêng số thread. **Loại channel tại mỗi ranh giới** mới là yếu tố chính:

| Channel/consumer | Hành vi runtime | Hệ quả thiết kế |
| --- | --- | --- |
| `DirectChannel` | Gọi subscriber cùng luồng gửi (đồng bộ). | Lỗi thường đi ngược về sender; một method chậm làm chậm lời gọi trước đó. |
| `ExecutorChannel` | Bàn giao việc xử lý sang `TaskExecutor`. | Có ranh giới bất đồng bộ; cần kiểm soát queue, số worker và xử lý lỗi phù hợp. |
| `QueueChannel` + polling consumer | Đưa message vào hàng đợi, endpoint nhận theo lịch poll. | Cần poller; có thể chịu tải theo lô/nhịp và phải tính capacity, backpressure. |
| `PublishSubscribeChannel` | Phân phối đến các subscriber, tùy executor mà đồng bộ hay bất đồng bộ. | Phù hợp fan-out; khác `DirectChannel` vốn thường phân phối cho một subscriber mỗi message. |

Nếu đổi `ordersIn` thành `QueueChannel`, endpoint đọc từ đó cần poller, ví dụ (một **cấu hình thay thế** cho annotation `normalize` trong ví dụ trước):

~~~java
@Transformer(
    inputChannel = "ordersIn",
    outputChannel = "normalized",
    poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "10"))
public Order normalize(OrderRequest request) {
    return new Order(request.id().trim(), request.amountMinorUnits());
}
~~~

Trong biến thể này cần import `org.springframework.integration.annotation.Poller`, và bean `ordersIn` phải là loại pollable (`QueueChannel`); không gắn poller vào `DirectChannel`. Thuộc tính `poller` và `reactive` trên cùng annotation endpoint là hai lựa chọn loại trừ nhau ở các phiên bản hỗ trợ reactive endpoint.

Về transaction:

- Với chuỗi `DirectChannel` đồng bộ, transaction của thread gọi có thể bao trùm các handler bên dưới, tùy nơi transaction bắt đầu và advice/proxy áp dụng.
- Qua `ExecutorChannel` hoặc polling consumer, execution sang thread/ngữ cảnh khác; transaction gắn với thread **không tự truyền** qua ranh giới đó. Cần xác định transaction cho từng đoạn hoặc cho poller và hệ thống lưu trữ liên quan.
- Retry có thể được cấu hình bằng advice cho handler (ví dụ `RequestHandlerRetryAdvice`). Advice ở một endpoint không mặc nhiên bao phủ mọi nhánh downstream; với router và filter cần cân nhắc idempotency khi xử lý lại.
- `QueueChannel` trong bộ nhớ không phải là cam kết lưu bền vững. Nếu cần khôi phục sau restart, xem xét `MessageStore` bền vững hoặc hệ thống broker và cơ chế xác nhận phù hợp.

Tương tự, header tương quan (ví dụ `correlationId`) giúp liên kết log và các nhánh; nó không tự biến router thành aggregator hay bảo đảm các kết quả sẽ quay lại một nơi. Nếu dùng route đa đích rồi hợp nhất, phải thiết kế correlation, release strategy, timeout và message store cho bước gom.

## 6. Lỗi, retry và kiểm soát luồng

Đặt lỗi vào đúng loại giúp dễ chẩn đoán:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
| --- | --- | --- |
| `@Transformer` ném `MessageTransformationException` | Method trả `null` hoặc không tạo được payload hợp lệ. | Kiểm tra dữ liệu vào; dùng `@Filter` nếu muốn loại bỏ hợp lệ. |
| Message biến mất sau filter | Method trả `false`, không cấu hình discard hoặc xử lý discard chưa có subscriber. | Ghi log điều kiện từ chối; cấu hình `discardChannel` để quan sát. |
| Router báo không phân giải được channel | Kết quả route không khớp bean channel; `resolutionRequired` mặc định yêu cầu phân giải. | Kiểm tra tên, `channelMappings`, tiền tố/hậu tố, và channel consumer. |
| `MessageDeliveryException` / `Dispatcher has no subscribers` | Gửi vào channel không có consumer khả dụng hoặc bị lỗi gửi. | Kiểm tra endpoint có được scan, trạng thái start/stop và cấu trúc channel. |
| Không thấy handler chạy với `QueueChannel` | Chưa có polling consumer/poller, hoặc poller chưa khởi chạy. | Xem `@Poller`, `autoStartup`, phase và cấu hình scheduling. |
| Message đến nhưng độ trễ tăng | Method chặn I/O trên `DirectChannel`, hàng đợi executor/poller tích tụ. | Đo thời gian từng endpoint, queue depth, pool saturation; tách việc nặng có chủ đích. |
| Lỗi chỉ xuất hiện trên async flow | Exception không còn truyền trực tiếp về thread gửi; xử lý lỗi chưa quan sát được. | Cấu hình và theo dõi error flow/`ErrorMessage`, header `errorChannel` khi thích hợp. |

Đối với xử lý đồng bộ, exception từ method thường lan về bên gọi thông qua chain. Trong luồng bất đồng bộ hoặc polling, lỗi thường được xuất bản dưới dạng `ErrorMessage` theo cách endpoint/error handler được cấu hình; không giả định rằng một `try/catch` bao quanh `send()` sẽ bắt mọi lỗi phát sinh sau đó.

Mẫu phân biệt quyết định nghiệp vụ và lỗi hạ tầng:

- `@Filter` trả `false` khi dữ liệu hợp lệ về cú pháp nhưng không thỏa **quy tắc chấp nhận** (ví dụ đơn hàng không đủ điều kiện).
- Ném exception khi không thể đánh giá quy tắc do lỗi hạ tầng (ví dụ dịch vụ tra cứu không khả dụng); xử lý retry có giới hạn, backoff và dead-letter/luồng lỗi.
- `@Router` chọn nhánh dự phòng **được thiết kế rõ** cho tình huống nghiệp vụ chưa có route; đừng dùng `resolutionRequired = "false"` chỉ để che lỗi đánh máy tên channel.

Khi retry hoặc phát lại message, các method có side effect cần idempotent theo khóa nghiệp vụ; đặc biệt nếu router đã gửi thành công tới nhánh thứ nhất nhưng lỗi ở nhánh thứ hai.

## 7. Quản lý vòng đời và quan sát trạng thái

Method annotation tạo endpoint do Spring quản lý, nên các tùy chọn như `autoStartup`, `phase`, `poller` và `adviceChain` gắn với **endpoint được sinh ra**, không trực tiếp thay đổi bean POJO nghiệp vụ. Có thể quản lý các endpoint thông qua cơ chế lifecycle/management của Spring Integration nếu được bật. Với integration flow đăng ký động bằng `IntegrationFlowContext`, cần phân biệt việc start/stop/remove **flow registration** với việc một method annotation được scan khi container khởi tạo; chúng là hai cách khai báo và quản lý khác nhau.

Khi chẩn đoán runtime nên theo dấu một message qua các mốc:

1. **Ingress:** đã nhận message tại channel nào, có `id`/`traceId`/`correlationId` nào?
2. **Transformer:** payload trước và sau có đúng kiểu, không trả `null`, thời gian xử lý bao lâu?
3. **Filter:** điều kiện `true`/`false`, tỷ lệ discard, có consumer cho discard channel không?
4. **Router:** kết quả route key và channel đích là gì, đã phân giải được chưa, có send failure không?
5. **Consumer đích:** endpoint đang running không, đang xử lý trên thread nào, queue/executor còn capacity không?

Ghi metric số message vào/ra, discard và lỗi theo endpoint khi quan sát được; đặt log có mã tương quan để nối các bước khi đổi thread. Tránh ghi payload chứa thông tin riêng tư vào log production.

## 8. Bài tập kiểm chứng và tình huống biên

Dùng ví dụ ở mục 4 để tự xác nhận những hành vi sau:

1. Gửi ba input mẫu và đối chiếu kết quả trong bảng. Bật log thread tại `normalize`, `valid`, `route`, `onPriority` để xác nhận hành vi đồng bộ.
2. Cho `normalize` trả `null` một cách có kiểm soát trong môi trường thử nghiệm. Xác nhận lỗi thay vì chuyển sang `rejected`; khôi phục implementation đúng ngay sau khi kiểm tra.
3. Đổi `route` trả về tên channel không tồn tại; quan sát lỗi phân giải. Chỉ sau đó thử `resolutionRequired = "false"` cùng `defaultOutputChannel` có consumer để hiểu fallback.
4. Thử `@Router` trả về `List.of("priority", "standard")` trong một cấu hình thử nghiệm, quan sát cả hai consumer nhận message và xem `applySequence` ảnh hưởng metadata như thế nào.
5. Thay ranh giới đầu vào bằng `QueueChannel` và cấu hình poller thích hợp. Đo latency/throughput khi có nhiều message; quan sát sự thay đổi thread và cách exception được xử lý.

Các lỗi thường gặp cần tránh: dùng transformer để “lọc bằng `null`”; trả về Boolean từ router để chọn nhánh; quên subscriber cho channel đích; quên poller cho pollable channel; dùng method filter để gọi API chậm trên `DirectChannel`; giả định retry, transaction và correlation tự xuất hiện chỉ vì có annotation.

## 9. Nguồn tra cứu chính thức

- [Spring Integration — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): cơ chế nhận method, ánh xạ tham số, input/output channel và tạo endpoint.
- [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transformer POJO, headers và quy tắc không trả `null`.
- [Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html): semantics của selector, discard channel, ngoại lệ khi từ chối.
- [Spring Integration — Router annotation](https://docs.spring.io/spring-integration/reference/router/annotation.html): kiểu trả về của router và định tuyến theo headers.
- [Javadoc `@Transformer`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Transformer.html), [`@Filter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html), [`@Router`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Router.html): thuộc tính cấu hình và hành vi endpoint.
