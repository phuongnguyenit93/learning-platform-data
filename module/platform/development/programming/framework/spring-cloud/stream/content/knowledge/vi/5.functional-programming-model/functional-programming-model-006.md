# Trả kết quả, thay đổi kiểu dữ liệu và xử lý không có đầu ra

Trong Spring Cloud Stream, chữ ký hàm quyết định cách dữ liệu đi vào và đi ra khỏi một thành phần xử lý. `Supplier<T>` tạo dữ liệu đầu ra, `Function<T, R>` nhận dữ liệu kiểu `T` và trả kết quả kiểu `R`, còn `Consumer<T>` nhận dữ liệu để thực hiện tác dụng nghiệp vụ mà không tạo đầu ra qua binding của hàm.

Việc chọn đúng kiểu hàm giúp mô tả rõ hợp đồng của từng bước trong luồng sự kiện. Một bước cần biến đổi dữ liệu nên trả về kiểu kết quả cụ thể; một bước chỉ ghi dữ liệu, gửi thông báo hoặc cập nhật projection nên được biểu diễn bằng `Consumer`. Khi cần giữ metadata, có thể nhận `Message<T>` và trả `Message<R>` để kiểm soát payload cùng headers.

## 1. Kết quả đầu ra trong mô hình hàm

Mỗi loại hàm có các cổng dữ liệu khác nhau:

| Kiểu hàm | Đầu vào | Đầu ra | Binding mặc định |
|---|---|---|---|
| `Supplier<T>` | Không có | `T` | `supplierName-out-0` |
| `Function<T, R>` | `T` | `R` | `functionName-in-0`, `functionName-out-0` |
| `Consumer<T>` | `T` | Không có | `consumerName-in-0` |

Tên binding được suy ra từ tên bean hàm. Phần `in-0` là cổng đầu vào đầu tiên, `out-0` là cổng đầu ra đầu tiên. Spring Cloud Stream ánh xạ các cổng này tới destination thông qua cấu hình `spring.cloud.stream.bindings`.

Ví dụ, hàm `enrichOrder` có kiểu `Function<OrderPlaced, OrderEnriched>` sẽ nhận một payload `OrderPlaced` qua `enrichOrder-in-0` và phát kết quả `OrderEnriched` qua `enrichOrder-out-0`. Binder chịu trách nhiệm chuyển dữ liệu đầu ra tới broker được cấu hình.

## 2. Function trả kết quả cùng kiểu dữ liệu

Một function có thể nhận và trả cùng kiểu khi nó chuẩn hóa, kiểm tra hoặc bổ sung giá trị nhưng vẫn giữ hợp đồng dữ liệu:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderNormalizationConfiguration {

    @Bean
    Function<CreateOrder, CreateOrder> normalizeOrder() {
        return command -> new CreateOrder(
            command.orderId().trim(),
            command.customerId().trim()
        );
    }
}

record CreateOrder(String orderId, String customerId) {}
```

Hàm nhận `CreateOrder` và trả một `CreateOrder` mới đã loại bỏ khoảng trắng ở hai trường định danh. Việc trả về một đối tượng mới giúp tránh thay đổi trực tiếp payload đầu vào nếu đối tượng có thể được chia sẻ ở nơi khác.

Cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.commands.raw
          group: order-normalizer
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.commands.normalized
          content-type: application/json
```

Luồng dữ liệu là:

1. Binder nhận message từ `orders.commands.raw`.
2. Converter tạo payload `CreateOrder` và chuyển vào `normalizeOrder-in-0`.
3. Function chuẩn hóa dữ liệu và trả `CreateOrder`.
4. Framework chuyển kết quả tới `normalizeOrder-out-0`.
5. Binder serialize kết quả và publish tới `orders.commands.normalized`.

Đầu vào và đầu ra có thể dùng hai destination khác nhau. Điều này giúp tách dữ liệu thô khỏi dữ liệu đã được chuẩn hóa, đồng thời cho phép các consumer khác đăng ký vào luồng kết quả.

## 3. Function thay đổi kiểu dữ liệu

Một function thường được dùng để chuyển đổi từ hợp đồng đầu vào sang hợp đồng đầu ra khác. Ví dụ, dịch vụ nhận sự kiện đơn hàng vừa tạo, tra cứu thông tin khách hàng rồi tạo dữ liệu giàu thông tin hơn cho bước tiếp theo:

```java
import java.time.Instant;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEnrichmentConfiguration {

    @Bean
    Function<OrderPlaced, OrderEnriched> enrichOrder(
            CustomerDirectory customerDirectory) {
        return order -> new OrderEnriched(
            order.orderId(),
            order.customerId(),
            customerDirectory.displayName(order.customerId()),
            order.totalAmount(),
            Instant.now()
        );
    }
}

record OrderPlaced(
    String orderId,
    String customerId,
    long totalAmount
) {}

record OrderEnriched(
    String orderId,
    String customerId,
    String customerName,
    long totalAmount,
    Instant enrichedAt
) {}
```

Đầu vào có kiểu `OrderPlaced`, đầu ra có kiểu `OrderEnriched`. Kiểu trả về `R` trong `Function<T, R>` là hợp đồng của payload được phát ra. Vì vậy, consumer phía sau cần hiểu schema của `OrderEnriched`, không thể mặc định rằng payload đầu ra vẫn là `OrderPlaced`.

Cấu hình hai binding:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.placed
          group: order-enrichment
          content-type: application/json
        enrichOrder-out-0:
          destination: orders.enriched
          content-type: application/json
```

Framework dùng thông tin kiểu hàm và cấu hình content type để chuyển payload ở ranh giới binding. Binder sau đó chuyển dữ liệu đầu ra sang định dạng mà broker lưu trữ. Khi đổi kiểu dữ liệu, cần kiểm tra cả hai phía:

- Consumer đầu vào có giải mã được schema của `OrderPlaced` không?
- Function có tạo đủ trường cần thiết cho `OrderEnriched` không?
- Content type đầu ra có khớp với định dạng được công bố không?
- Consumer của `orders.enriched` có tương thích với phiên bản schema mới không?

Việc generic type được khai báo trong Java giúp trình biên dịch kiểm tra một phần hợp đồng, nhưng không thay thế kiểm tra schema ở thời điểm chạy. Serialization vẫn có thể thất bại do trường không hợp lệ, kiểu không hỗ trợ hoặc cấu hình converter không phù hợp.

## 4. Trả Message để kiểm soát payload và headers

Khi function chỉ nhận và trả đối tượng nghiệp vụ, framework xử lý message envelope ở mức binding. Nếu cần đọc hoặc thay đổi metadata, hàm có thể dùng `Message<T>` thay cho payload thuần.

Ví dụ dưới đây chuyển `OrderPlaced` thành `OrderEnriched`, đồng thời giữ các header đầu vào và bổ sung header cho bước xử lý:

```java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<Message<OrderPlaced>, Message<OrderEnriched>> enrichWithHeaders = input -> {
    OrderPlaced order = input.getPayload();

    OrderEnriched result = new OrderEnriched(
        order.orderId(),
        order.customerId(),
        "Customer " + order.customerId(),
        order.totalAmount(),
        java.time.Instant.now()
    );

    return MessageBuilder.withPayload(result)
        .copyHeaders(input.getHeaders())
        .setHeader("processingStage", "enriched")
        .build();
};
```

`MessageBuilder` giúp xây dựng message mới với payload đã đổi kiểu. `copyHeaders` sao chép metadata đầu vào, còn `setHeader` bổ sung hoặc cập nhật header cần thiết. Chỉ nên giữ những header có ý nghĩa ở bước tiếp theo; header nội bộ hoặc header đặc thù của broker có thể không phù hợp để chuyển tiếp.

Headers thường dùng cho `correlationId`, thông tin truy vết, nguồn phát hoặc metadata vận chuyển. Dữ liệu nghiệp vụ bắt buộc phải được đặt trong payload và được mô tả bằng schema. Khả năng truyền header qua broker phụ thuộc binder và broker, vì vậy không nên coi mọi header Java sẽ được bảo toàn nguyên vẹn sau khi publish rồi consume.

Nếu không cần thao tác với headers, chữ ký đơn giản `Function<OrderPlaced, OrderEnriched>` thường dễ đọc và dễ kiểm thử hơn.

## 5. Đầu ra một-một và đầu ra dạng luồng

Function đồng bộ kiểu `Function<T, R>` thường biểu diễn một kết quả `R` cho mỗi lần gọi với đầu vào `T`. Khi cần xử lý một luồng dữ liệu liên tục hoặc biến đổi nhiều phần tử, mô hình reactive có thể sử dụng `Flux`:

```java
import reactor.core.publisher.Flux;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;

@Bean
Function<Flux<OrderPlaced>, Flux<OrderEnriched>> enrichOrders() {
    return orders -> orders.map(order -> new OrderEnriched(
        order.orderId(),
        order.customerId(),
        "Customer " + order.customerId(),
        order.totalAmount(),
        java.time.Instant.now()
    ));
}
```

Ở đây, hàm nhận một `Flux<OrderPlaced>` và trả `Flux<OrderEnriched>`. Mỗi phần tử đầu vào được chuyển thành một phần tử đầu ra. Framework tích hợp pipeline reactive với binding; ứng dụng không nên tự gọi `subscribe()` bên trong function chỉ để kích hoạt luồng vì việc đó có thể tách vòng đời xử lý khỏi cơ chế điều phối của framework.

Với pipeline reactive, cần hiểu cách xử lý lỗi và backpressure. Một lỗi phát sinh trong luồng có thể kết thúc pipeline hoặc được xử lý bằng các toán tử reactive phù hợp. Tránh gọi API blocking trực tiếp trên luồng xử lý reactive nếu chưa bố trí scheduler phù hợp. Không nên giả định retry và xác nhận của broker có cùng hành vi giữa mọi binder hoặc mọi kiểu function.

## 6. Xử lý không có đầu ra bằng Consumer

Không phải bước xử lý nào cũng cần phát một message mới. Ví dụ, một consumer chỉ cập nhật projection hoặc lưu trạng thái xử lý vào cơ sở dữ liệu. Khi đó, hãy khai báo `Consumer<T>`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderProjectionConfiguration {

    @Bean
    Consumer<OrderEnriched> updateOrderProjection(
            OrderProjectionService projectionService) {
        return projectionService::apply;
    }
}
```

Vì `updateOrderProjection` là `Consumer`, nó chỉ có binding đầu vào `updateOrderProjection-in-0`. Không có binding `updateOrderProjection-out-0` vì chữ ký hàm không trả dữ liệu để publish.

```yaml
spring:
  cloud:
    function:
      definition: updateOrderProjection
    stream:
      bindings:
        updateOrderProjection-in-0:
          destination: orders.enriched
          group: order-projection
          content-type: application/json
```

Consumer không có đầu ra qua binding, nhưng vẫn có thể tạo tác dụng nghiệp vụ như ghi database, cập nhật cache hoặc gọi một dịch vụ khác. Tác dụng đó cần được thiết kế có thể quan sát và chịu được việc message được giao lại. Nếu consumer ghi dữ liệu rồi dừng trước ACK/commit, broker có thể giao lại message; vì vậy nên dùng `eventId` hoặc khóa idempotency để tránh cập nhật trùng.

### Vì sao không dùng Function trả về null?

`Function<T, R>` được định nghĩa để trả một kết quả `R`. Dùng `Function<T, Void>` hoặc trả `null` để biểu thị “không có đầu ra” làm hợp đồng trở nên mơ hồ và phụ thuộc cách framework/converter xử lý giá trị null. Nếu nghiệp vụ không cần phát kết quả qua binding, hãy dùng `Consumer<T>` để thể hiện đúng ý định.

## 7. Khi Consumer cần phát một thông điệp khác

Có trường hợp bước xử lý chính không trả kết quả qua chữ ký hàm nhưng vẫn cần phát một thông điệp phụ, chẳng hạn consumer ghi nhận trạng thái rồi yêu cầu một dịch vụ thông báo gửi email. Có thể inject `StreamBridge` và gửi tới một output binding tường minh:

```java
import java.util.function.Consumer;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.context.annotation.Bean;

@Bean
Consumer<OrderEnriched> updateAndNotify(
        OrderProjectionService projectionService,
        StreamBridge streamBridge) {
    return order -> {
        projectionService.apply(order);
        streamBridge.send("notificationRequests-out-0",
            new NotificationRequest(order.orderId(), order.customerName()));
    };
}

record NotificationRequest(String orderId, String customerName) {}
```

Khai báo binding đầu ra được sử dụng bởi `StreamBridge`:

```yaml
spring:
  cloud:
    function:
      definition: updateAndNotify
    stream:
      output-bindings: notificationRequests-out-0
      bindings:
        updateAndNotify-in-0:
          destination: orders.enriched
          group: order-projection
        notificationRequests-out-0:
          destination: notifications.requests
          content-type: application/json
```

Chữ ký bean vẫn là `Consumer<OrderEnriched>` nên không có output binding tự động `updateAndNotify-out-0`. Binding `notificationRequests-out-0` là đầu ra được gửi tường minh qua `StreamBridge`.

Gửi message và cập nhật database trong cùng consumer là hai thao tác có thể thất bại độc lập. Nếu database commit nhưng publish thất bại, yêu cầu thông báo có thể bị thiếu; nếu publish thành công nhưng consumer chưa ACK rồi chạy lại, yêu cầu có thể được gửi hai lần. Với tác vụ quan trọng, hãy cân nhắc transactional outbox và idempotency ở phía nhận thay vì giả định hai thao tác tự động nguyên tử.

## 8. Ghép hàm và kiểu dữ liệu giữa các bước

Spring Cloud Function cho phép ghép các hàm có kiểu đầu ra/đầu vào tương thích. Ví dụ, `normalizeOrder` trả `CreateOrder`, còn `enrichOrder` nhận `CreateOrder` và trả `OrderEnriched`. Hai bước có thể nằm trong cùng một pipeline:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|enrichOrder|publishOrder
```

Đầu ra của bước trước trở thành đầu vào của bước sau. Kiểu dữ liệu phải tương thích giữa các bước: kiểu `R` của function trước phải có thể được chuyển thành kiểu `T` mà function sau nhận. Nếu có `Consumer` ở cuối chuỗi, pipeline kết thúc bằng xử lý không có output binding. Nếu cần một kết quả được publish ra broker, bước cuối phải có đầu ra phù hợp.

Ghép hàm không tạo một broker destination riêng giữa mỗi bước. Đây là pipeline trong cùng ứng dụng. Nếu cần các bước có thể triển khai độc lập hoặc cần lưu trữ sự kiện trung gian, hãy dùng binding và destination riêng.

## 9. Lỗi chuyển đổi và lỗi khi tạo kết quả

Đổi kiểu dữ liệu làm xuất hiện các điểm lỗi mới:

- Payload đầu vào không thể deserialize thành `T`.
- Dữ liệu đầu vào thiếu trường hoặc không thỏa mãn quy tắc để tạo `R`.
- Logic function ném exception khi tra cứu hoặc biến đổi dữ liệu.
- Payload `R` không serialize được theo content type đầu ra.
- Consumer nhận phiên bản schema không tương thích với phiên bản producer.

Khi function ném exception trước khi trả kết quả, đầu ra thông thường của lần gọi đó không được tạo. Cơ chế retry, error channel hoặc DLQ phụ thuộc cấu hình Spring Cloud Stream và binder. Với consumer, exception cũng có thể kích hoạt chính sách xử lý lỗi và redelivery. Hãy phân loại lỗi tạm thời và lỗi dữ liệu; không retry vô hạn một payload không thể giải mã.

Khi đổi schema, ưu tiên thay đổi tương thích như thêm trường tùy chọn có giá trị mặc định và triển khai consumer có thể đọc cả phiên bản cũ lẫn mới trong giai đoạn chuyển tiếp. Với Avro/Protobuf hoặc schema registry, kiểm tra chính sách compatibility bằng công cụ tương ứng trước khi phát hành.

## 10. Kiểm thử hợp đồng đầu ra và trường hợp không có đầu ra

Spring Cloud Stream Test Binder có thể kiểm thử các binding trong phạm vi ứng dụng. Với function có đầu ra, gửi message vào binding đầu vào và xác minh payload đầu ra có đúng kiểu, đúng trường và đúng header cần giữ. Với consumer, gửi message vào binding đầu vào rồi xác minh tác dụng nghiệp vụ qua repository hoặc service mock.

| Loại kiểm thử | Điều cần xác minh |
|---|---|
| `Function<T, T>` | Dữ liệu được chuẩn hóa đúng và vẫn giữ hợp đồng kiểu. |
| `Function<T, R>` | Payload đầu ra có kiểu/schema `R`, dữ liệu được ánh xạ đầy đủ. |
| `Function<Message<T>, Message<R>>` | Payload đổi đúng kiểu, header cần thiết được giữ hoặc cập nhật đúng. |
| `Consumer<T>` | Chỉ có binding đầu vào; tác dụng nghiệp vụ được thực hiện đúng. |
| Consumer gửi qua `StreamBridge` | Output binding tường minh nhận đúng thông điệp phụ. |
| Function reactive | Các phần tử đầu ra đúng thứ tự/biến đổi theo hợp đồng và lỗi luồng được xử lý phù hợp. |

Test Binder không thay thế kiểm thử tích hợp với broker thật. Các vấn đề serialization cụ thể, partition, transaction, ACK, retry và DLQ cần được xác minh với binder/broker được triển khai.

## 11. Quy tắc chọn chữ ký hàm

Trước khi khai báo bean, hãy xác định rõ kết quả mà bước xử lý cần tạo:

1. Nếu thành phần chỉ tạo dữ liệu mới và không cần đầu vào, dùng `Supplier<T>`.
2. Nếu nhận dữ liệu và cần tạo một kết quả mới hoặc biến đổi kiểu dữ liệu, dùng `Function<T, R>`.
3. Nếu nhận dữ liệu để thực hiện tác dụng nghiệp vụ và không phát kết quả qua binding, dùng `Consumer<T>`.
4. Nếu cần thao tác với metadata, cân nhắc `Message<T>` và `Message<R>`; chỉ giữ các header có ý nghĩa ở chặng tiếp theo.
5. Nếu xử lý một luồng liên tục, cân nhắc kiểu reactive như `Flux<T>` và `Flux<R>`, đồng thời hiểu rõ backpressure và xử lý lỗi.
6. Nếu consumer cần phát thông điệp phụ, dùng output binding tường minh qua `StreamBridge` và thiết kế độ tin cậy cho cả thao tác ghi dữ liệu lẫn publish.

Khi chữ ký hàm phản ánh đúng hợp đồng đầu vào/đầu ra, Spring Cloud Stream có thể thiết lập binding phù hợp, còn người đọc mã nguồn dễ nhận ra bước nào tạo kết quả, bước nào đổi kiểu và bước nào chỉ thực hiện tác dụng nghiệp vụ.
