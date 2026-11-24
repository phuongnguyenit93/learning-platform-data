# Khai báo Supplier, Function và Consumer bằng @Bean

Spring Cloud Stream sử dụng mô hình lập trình hàm để nối logic nghiệp vụ với hệ thống truyền tin. Thay vì viết một listener container hoặc producer riêng cho từng broker, ứng dụng khai báo các bean theo ba kiểu hàm chuẩn của Java: `Supplier`, `Function` và `Consumer`. Binder kết nối các hàm đó với destination thông qua input binding và output binding.

Ba kiểu hàm thể hiện ba vai trò cơ bản trong một luồng sự kiện: tạo dữ liệu để phát hành, nhận và biến đổi dữ liệu, hoặc nhận dữ liệu để thực hiện một tác vụ. Khi nắm được chữ ký hàm, tên bean và quy tắc đặt tên binding, bạn có thể tổ chức ứng dụng Spring Cloud Stream rõ ràng và chuyển đổi giữa Kafka, RabbitMQ hoặc Pulsar với ít thay đổi ở phần nghiệp vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `Supplier<T>`, `Function<I, O>` và `Consumer<T>` trong Spring Cloud Stream.
- Khai báo từng kiểu hàm bằng phương thức `@Bean` trong lớp cấu hình Spring.
- Xác định tên input binding và output binding từ tên bean.
- Kích hoạt một hoặc nhiều function bean bằng `spring.cloud.function.definition`.
- Cấu hình destination và group cho từng binding.
- Phân biệt dữ liệu payload với `Message<T>` và message header.
- Kiểm thử logic hàm độc lập trước khi kiểm thử kết nối broker.

## 1. Mô hình hàm trong Spring Cloud Stream

Trong mô hình hàm, ứng dụng tập trung vào việc xử lý dữ liệu. Spring Cloud Stream quản lý phần kết nối hàm với middleware thông qua binder.

| Kiểu hàm | Chữ ký tổng quát | Vai trò | Binding mặc định |
|---|---|---|---|
| Supplier | `Supplier<T>` | Tạo dữ liệu để phát hành | `<beanName>-out-0` |
| Function | `Function<I, O>` | Nhận dữ liệu, biến đổi và phát hành kết quả | `<beanName>-in-0`, `<beanName>-out-0` |
| Consumer | `Consumer<T>` | Nhận dữ liệu và thực hiện tác vụ | `<beanName>-in-0` |

Trong bảng, `T` là kiểu dữ liệu được tạo hoặc tiêu thụ, `I` là kiểu đầu vào và `O` là kiểu đầu ra. Các kiểu này có thể là lớp Java thông thường, record, kiểu dữ liệu dùng chung hoặc `Message<T>`.

### Supplier: nguồn phát dữ liệu

`Supplier<T>` không có tham số đầu vào và trả về một giá trị. Spring Cloud Stream gọi supplier thông qua poller để lấy dữ liệu và gửi dữ liệu đó vào output binding.

~~~java
@Bean
Supplier<String> greetingSource() {
    return () -> "Xin chào từ Spring Cloud Stream";
}
~~~

Bean có tên `greetingSource` tạo output binding mặc định `greetingSource-out-0`. Supplier phù hợp khi ứng dụng cần phát dữ liệu từ một nguồn có thể truy vấn theo chu kỳ, chẳng hạn outbox, hàng đợi nội bộ hoặc một nguồn dữ liệu định kỳ.

Supplier không phải là hàm được gọi trực tiếp bởi một message đến từ broker. Nếu dữ liệu cần phát sinh khi có một thao tác nghiệp vụ xảy ra trong service hoặc controller, có thể dùng `StreamBridge` để gửi dữ liệu qua output binding. Cách chọn này giúp phân biệt nguồn được poll định kỳ với thao tác phát sự kiện chủ động.

### Function: nhận và biến đổi dữ liệu

`Function<I, O>` nhận một giá trị kiểu `I`, thực hiện xử lý rồi trả về kết quả kiểu `O`. Spring Cloud Stream kết nối input binding và output binding của function với broker.

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase();
}
~~~

Bean `uppercase` có input binding `uppercase-in-0` và output binding `uppercase-out-0`. Mỗi message đầu vào được chuyển thành giá trị đầu ra theo logic của hàm.

Function phù hợp với các bước biến đổi độc lập như chuẩn hóa dữ liệu, bổ sung thông tin, tính toán thuộc tính hoặc chuyển đổi một sự kiện thành dạng phù hợp cho bước tiếp theo.

### Consumer: nhận và xử lý dữ liệu

`Consumer<T>` nhận một giá trị kiểu `T` và không trả về kết quả. Đây thường là điểm cuối của một luồng xử lý: ghi dữ liệu, cập nhật trạng thái, gọi một dịch vụ nghiệp vụ hoặc tạo tác động phụ.

~~~java
@Bean
Consumer<String> logMessage() {
    return value -> System.out.println("Đã nhận: " + value);
}
~~~

Bean `logMessage` tạo input binding `logMessage-in-0`. Vì Consumer không phát ra giá trị trả về, nó không có output binding được tạo từ chữ ký hàm.

Consumer chỉ nên xác nhận xử lý thành công sau khi công việc nghiệp vụ cần thiết đã hoàn tất. Nếu logic ném exception, cơ chế xử lý lỗi, retry hoặc dead-letter sẽ phụ thuộc cấu hình binder và Spring Cloud Stream.

## 2. Tên bean quyết định tên binding

Tên phương thức được đánh dấu `@Bean` thường trở thành tên bean trong Spring Application Context. Spring Cloud Stream dùng tên function bean để suy ra tên binding.

Với một bean tên `processOrder`:

- Nếu là `Supplier<T>`, output binding là `processOrder-out-0`.
- Nếu là `Function<I, O>`, input binding là `processOrder-in-0` và output binding là `processOrder-out-0`.
- Nếu là `Consumer<T>`, input binding là `processOrder-in-0`.

Hậu tố `-in-0` và `-out-0` biểu thị cổng vào và cổng ra đầu tiên. Các function có nhiều đầu vào hoặc đầu ra có thể có thêm chỉ số tương ứng; khi dùng kiểu hàm phức tạp, cần đối chiếu tên binding mà framework tạo ra với cấu hình thực tế.

Có thể đặt tên bean tường minh bằng thuộc tính của `@Bean`:

~~~java
@Bean("orderNormalizer")
Function<OrderCreated, NormalizedOrder> normalize() {
    return event -> new NormalizedOrder(
        event.orderId(),
        event.total().stripTrailingZeros()
    );
}
~~~

Trong ví dụ này, tên function bean là `orderNormalizer`, do đó tên binding được suy ra từ tên này, không phải tên phương thức `normalize`. Đặt tên rõ ràng giúp cấu hình binding ổn định và dễ đọc.

Không nên đổi tên bean tùy tiện sau khi đã triển khai. Tên binding có thể được tham chiếu trong cấu hình môi trường, dashboard, kiểm thử và các tài liệu vận hành.

## 3. Kích hoạt function bean bằng function definition

Một ứng dụng có thể khai báo nhiều bean thuộc các kiểu hàm khác nhau. Thuộc tính `spring.cloud.function.definition` chỉ định function nào được Spring Cloud Stream kích hoạt để tạo binding.

Ví dụ, ứng dụng khai báo ba function bean:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;enrichOrder;recordOrder
~~~

Dấu chấm phẩy phân tách các function độc lập cần kích hoạt. Nó không có nghĩa là đầu ra của function trước tự động trở thành đầu vào của function sau. Mỗi function vẫn có binding riêng và có thể kết nối tới destination khác nhau.

Nếu muốn ghép hàm theo kiểu function composition, Spring Cloud Function hỗ trợ toán tử `|` trong function definition. Khi đó đầu ra của hàm trước được chuyển trực tiếp sang hàm sau trong cùng chuỗi xử lý, theo quy tắc composition. Chỉ sử dụng composition khi các chữ ký hàm và mục đích xử lý phù hợp; không nhầm nó với việc nhiều function độc lập cùng kết nối qua broker.

Khi chỉ có một function bean, framework có thể tự nhận diện function đó trong một số cấu hình. Với ứng dụng có nhiều bean, nên khai báo definition tường minh để tránh kích hoạt nhầm hoặc không xác định được function mong muốn.

## 4. Ví dụ hoàn chỉnh: Supplier, Function và Consumer cho đơn hàng

Xét luồng xử lý đơn hàng gồm ba bước:

1. Nguồn sự kiện lấy một sự kiện `OrderCreated` đang chờ.
2. Function bổ sung thông tin và chuyển thành `EnrichedOrder`.
3. Consumer ghi kết quả vào sổ theo dõi đơn hàng.

Ví dụ dùng destination `orders` cho bước đầu và `enriched-orders` cho bước sau. Đây là cách tổ chức một luồng qua broker; mỗi function có thể được triển khai trong cùng ứng dụng hoặc tách thành ứng dụng riêng tùy yêu cầu vận hành.

### Khai báo kiểu dữ liệu và các hợp đồng phụ trợ

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}

public record EnrichedOrder(
    String eventId,
    String orderId,
    BigDecimal total,
    BigDecimal tax,
    Instant processedAt
) {}
~~~

Nguồn dữ liệu và thành phần lưu kết quả được biểu diễn bằng các interface nghiệp vụ:

~~~java
public interface OrderEventSource {
    // Trả về sự kiện đang chờ; trả về null nếu hiện không có sự kiện.
    OrderCreated pollNextPendingEvent();
}

public interface OrderLedger {
    void append(EnrichedOrder order);
}
~~~

Các interface này được triển khai bởi ứng dụng. Ví dụ không phụ thuộc cách lưu trữ cụ thể, vì mục tiêu là minh họa cách Spring Cloud Stream kết nối chữ ký hàm với binding.

### Khai báo ba function bean

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctionConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderEventSource source) {
        return source::pollNextPendingEvent;
    }

    @Bean
    Function<OrderCreated, EnrichedOrder> enrichOrder() {
        return event -> {
            BigDecimal tax = event.total()
                .multiply(new BigDecimal("0.10"));

            return new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                tax,
                Instant.now()
            );
        };
    }

    @Bean
    Consumer<EnrichedOrder> recordOrder(OrderLedger ledger) {
        return ledger::append;
    }
}
~~~

Ba bean đảm nhiệm ba vai trò khác nhau:

- `orderSource` là Supplier. Mỗi lần poller gọi, nguồn lấy sự kiện đang chờ và trả về cho output binding.
- `enrichOrder` là Function. Nó nhận `OrderCreated`, tính thuế minh họa và phát ra `EnrichedOrder`.
- `recordOrder` là Consumer. Nó nhận `EnrichedOrder` rồi ghi vào `OrderLedger`.

Trong ví dụ, `OrderEventSource` cần bảo đảm một sự kiện đã được lấy khỏi nguồn không bị phát lại vô hạn chỉ vì poller gọi nhiều lần. Với nguồn dựa trên database, nên có cơ chế đánh dấu hoặc transactional outbox để phối hợp trạng thái lấy sự kiện và phát hành.

### Cấu hình function definition và binding

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;enrichOrder;recordOrder
    stream:
      poller:
        fixed-delay: 1000
      bindings:
        orderSource-out-0:
          destination: orders

        enrichOrder-in-0:
          destination: orders
        enrichOrder-out-0:
          destination: enriched-orders

        recordOrder-in-0:
          destination: enriched-orders
          group: order-ledger
~~~

Cấu hình này cho biết:

| Binding | Hướng | Destination | Ý nghĩa |
|---|---|---|---|
| `orderSource-out-0` | Output | `orders` | Supplier phát sự kiện đơn hàng |
| `enrichOrder-in-0` | Input | `orders` | Function nhận sự kiện gốc |
| `enrichOrder-out-0` | Output | `enriched-orders` | Function phát kết quả đã bổ sung |
| `recordOrder-in-0` | Input | `enriched-orders` | Consumer nhận kết quả |

Poller gọi Supplier theo chu kỳ cấu hình. Khoảng thời gian một giây chỉ là ví dụ cho môi trường thử nghiệm; cần điều chỉnh theo tốc độ nguồn dữ liệu, tải hệ thống và độ trễ chấp nhận được. Poller không tạo ra một thông điệp nghiệp vụ mới nếu nguồn không có dữ liệu cần phát.

Consumer có group `order-ledger` để giữ subscription ổn định. Với Kafka, group này ánh xạ thành consumer group; với RabbitMQ, binder thường tạo queue tương ứng cho group; với Pulsar, group được biểu diễn bằng subscription name. Tên và chi tiết tài nguyên phụ thuộc binder.

## 5. Cấu hình destination và group cho từng kiểu hàm

Function bean chỉ mô tả logic. Destination và group được cấu hình riêng trên binding để binder biết nơi gửi hoặc nhận dữ liệu.

Ví dụ một Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

Ví dụ một Function:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: raw-orders
          group: order-normalizer
        normalizeOrder-out-0:
          destination: normalized-orders
~~~

Ví dụ một Supplier:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource
    stream:
      poller:
        fixed-delay: 2000
      bindings:
        orderSource-out-0:
          destination: orders
~~~

Một số nguyên tắc cần ghi nhớ:

- Input binding có thể dùng group để xác định subscription có tên và tiến độ tiêu thụ ổn định.
- Output binding thường cần destination; group là thuộc tính của phía tiêu thụ.
- Nhiều consumer độc lập đọc cùng destination nên có group riêng.
- Nhiều instance của cùng một consumer thường dùng chung group để chia tải.
- Không dựa vào tên binding tự suy đoán tên tài nguyên cuối cùng trên broker; hãy kiểm tra cấu hình binder và trạng thái broker.

## 6. Payload và Message<T>

Các hàm có thể nhận hoặc trả về payload trực tiếp như `OrderCreated`, hoặc làm việc với `Message<T>` khi cần truy cập header.

Dùng payload trực tiếp khi logic chỉ cần dữ liệu nghiệp vụ:

~~~java
@Bean
Function<OrderCreated, EnrichedOrder> enrichOrder() {
    return event -> enrich(event);
}
~~~

Dùng `Message<T>` khi cần đọc metadata như correlation ID, partition key hoặc header do publisher gửi:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderCreated>, Message<EnrichedOrder>> enrichWithHeaders() {
    return message -> {
        OrderCreated event = message.getPayload();
        EnrichedOrder result = enrich(event);

        return MessageBuilder.withPayload(result)
            .copyHeaders(message.getHeaders())
            .setHeader("processedBy", "order-enricher")
            .build();
    };
}
~~~

`Message<T>` gồm payload và headers. Payload là nội dung chính; headers chứa metadata phục vụ định tuyến, tương quan, partition hoặc xử lý. Không nên đưa dữ liệu nghiệp vụ lớn vào header, và không nên sao chép mọi header một cách thiếu chọn lọc nếu chúng chứa thông tin không cần chuyển tiếp.

Tương tự, Supplier có thể trả về `Message<T>` để đính kèm metadata khi phát hành. Consumer có thể nhận `Message<T>` để kiểm tra header trước khi xử lý. Khi dùng payload thuần, Spring Cloud Stream và binder thực hiện chuyển đổi message theo cấu hình content type và message converter.

## 7. Phân biệt function bean và StreamBridge

Function bean là cách khai báo một nguồn, bước biến đổi hoặc consumer được kích hoạt và quản lý như một endpoint hàm. `StreamBridge` phù hợp khi logic phát hành nằm trong một luồng gọi chủ động, chẳng hạn sau khi service hoàn thành một thao tác nghiệp vụ.

Ví dụ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

Output binding `orders-out-0` cần trỏ tới destination phù hợp. Giá trị boolean từ `send` phản ánh kết quả gửi qua binding ở bước đó; nó không xác nhận mọi subscriber đã nhận hoặc hoàn tất xử lý.

Có thể chọn theo tình huống:

| Nhu cầu | Cách tiếp cận |
|---|---|
| Đọc dữ liệu theo chu kỳ từ một nguồn | Supplier |
| Nhận message, biến đổi rồi phát kết quả | Function |
| Nhận message và thực hiện tác vụ cuối | Consumer |
| Phát sự kiện ngay trong một lời gọi nghiệp vụ | StreamBridge |

Hai cách tiếp cận có thể cùng xuất hiện trong một ứng dụng. Điều quan trọng là tên output binding được dùng trong mã phải khớp với cấu hình.

## 8. Kiểm thử các function bean

Có thể kiểm thử logic hàm mà không cần khởi động broker. Vì các bean trả về interface hàm Java, unit test có thể gọi trực tiếp chúng.

Ví dụ kiểm thử Function:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class OrderFunctionTest {

    @Test
    void enrichesOrder() {
        Function<OrderCreated, EnrichedOrder> function =
            event -> new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                event.total().multiply(new BigDecimal("0.10")),
                Instant.parse("2026-01-01T00:00:00Z")
            );

        OrderCreated input = new OrderCreated(
            "evt-1",
            "order-1",
            new BigDecimal("100.00"),
            Instant.parse("2026-01-01T00:00:00Z")
        );

        EnrichedOrder output = function.apply(input);

        assertEquals("order-1", output.orderId());
        assertEquals(new BigDecimal("10.0000"), output.tax());
    }
}
~~~

Trong test thực tế, nên tạo bean từ cấu hình hoặc tách logic nghiệp vụ thành service để tránh viết lại cùng một thuật toán trong test. Ví dụ trên chỉ minh họa cách gọi một Function bằng `apply`.

Các mức kiểm thử nên bao gồm:

1. **Unit test:** kiểm tra logic Supplier, Function và Consumer; xác minh dữ liệu vào/ra và tác động nghiệp vụ.
2. **Spring context test:** khởi tạo Application Context để xác nhận các bean có tên đúng và được Spring nhận diện.
3. **Binding test:** dùng test binder để xác minh function được kích hoạt, binding đúng tên và payload được chuyển qua.
4. **Broker integration test:** chạy broker phù hợp để xác minh destination, group, converter và hành vi thực tế của binder.

Khi kiểm thử Supplier, cần kiểm soát nguồn dữ liệu để tránh poller phát message liên tục ngoài ý muốn. Với Consumer, nên kiểm tra cả trường hợp xử lý thành công và trường hợp ném exception.

## 9. Lỗi thường gặp khi khai báo function bean

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có binding được tạo | Function bean không được kích hoạt hoặc definition sai | Kiểm tra tên bean và `spring.cloud.function.definition` |
| Binding có tên khác cấu hình | Tên bean thực tế khác tên phương thức dự kiến | Kiểm tra tên khai báo trong `@Bean` |
| Supplier không phát message | Supplier không được poll, nguồn không có dữ liệu hoặc binding output sai | Kiểm tra poller, logic nguồn và output binding |
| Function nhận được nhưng không thấy output | Hàm lỗi, trả về null hoặc output binding chưa cấu hình đúng | Kiểm tra log, giá trị trả về và destination |
| Consumer không nhận message | Function chưa kích hoạt, destination/group sai hoặc broker chưa kết nối | Kiểm tra function definition, input binding và log binder |
| Consumer nhận dữ liệu sai kiểu | Content type hoặc message converter không phù hợp | Kiểm tra kiểu payload, schema và cấu hình content type |
| Nhiều function bị bỏ qua | Definition chưa liệt kê đầy đủ function cần chạy | Khai báo tường minh các function trong definition |
| Message bị phát lặp | Supplier đọc lại cùng dữ liệu hoặc nguồn không đánh dấu đã lấy | Thiết kế cơ chế lấy sự kiện và chống phát trùng |
| Consumer thực hiện tác động lặp | Message có thể được giao lại sau lỗi hoặc restart | Thiết kế handler idempotent và dùng event ID |

Khi function không hoạt động như mong đợi, hãy kiểm tra theo trình tự: bean có được Spring tạo không, function có được kích hoạt không, binding có được tạo không, binder có kết nối không và cuối cùng message có đi qua endpoint không. Cách kiểm tra theo lớp giúp khoanh vùng lỗi ở đúng thành phần.

## 10. Quy trình thực hành

Tạo một ứng dụng nhỏ có ba function bean để xử lý sự kiện đơn hàng:

1. Khai báo record `OrderCreated` và `EnrichedOrder`.
2. Khai báo `Supplier<OrderCreated>` tên `orderSource` để lấy sự kiện đang chờ từ nguồn dữ liệu.
3. Khai báo `Function<OrderCreated, EnrichedOrder>` tên `enrichOrder` để bổ sung thông tin.
4. Khai báo `Consumer<EnrichedOrder>` tên `recordOrder` để lưu kết quả.
5. Khai báo `spring.cloud.function.definition` gồm ba function.
6. Cấu hình `orderSource-out-0`, `enrichOrder-in-0`, `enrichOrder-out-0` và `recordOrder-in-0` với destination tương ứng.
7. Đặt group ổn định cho Consumer.
8. Chạy unit test cho từng hàm, sau đó chạy ứng dụng với binder thử nghiệm.
9. Gửi một sự kiện mẫu, xác minh dữ liệu đầu vào, đầu ra và tác động của Consumer.
10. Thử thay binder trong môi trường thử nghiệm và kiểm tra logic hàm có cần thay đổi hay chỉ cần cấu hình lại kết nối.

Kết quả cần đạt là bạn có thể giải thích được vì sao Supplier tạo output binding, Function có cả input và output binding, Consumer chỉ có input binding; đồng thời xác định được tên binding dựa trên tên bean và cấu hình.

## Kết luận

Mô hình hàm giúp ứng dụng Spring Cloud Stream mô tả xử lý sự kiện bằng các chữ ký Java quen thuộc. Supplier tạo dữ liệu, Function biến đổi dữ liệu, còn Consumer tiếp nhận và thực hiện tác vụ. Phương thức `@Bean` cung cấp tên function; Spring Cloud Stream dùng tên đó để tạo binding mặc định và binder kết nối binding với destination trên broker.

Khi tổ chức ứng dụng, hãy khai báo rõ function definition, cấu hình đúng tên binding, destination và group, đồng thời chọn payload hoặc `Message<T>` theo nhu cầu metadata. Nhờ giữ logic nghiệp vụ trong các hàm độc lập và để binder đảm nhiệm kết nối, ứng dụng có thể sử dụng Kafka, RabbitMQ hoặc Pulsar với ít phụ thuộc hơn vào chi tiết của broker.

