# Xác định kiểu đầu vào, đầu ra và kiểu tham số tổng quát

Trong Spring Cloud Stream, chữ ký hàm cho biết một thành phần nhận dữ liệu gì và tạo ra dữ liệu gì. Khi khai báo đúng kiểu generic, compiler có thể kiểm tra luồng dữ liệu giữa các hàm; Spring Cloud Function và Spring Cloud Stream cũng có thêm thông tin để chuyển đổi payload thành kiểu Java mà hàm yêu cầu. Nếu dùng kiểu thô (raw type), `Object` hoặc ép kiểu tùy tiện, lỗi có thể chỉ xuất hiện khi message thực sự đi qua binder.

Spring Cloud Stream dùng mô hình hàm của Java với ba dạng chính: `Supplier<T>` tạo dữ liệu, `Function<T, R>` biến đổi dữ liệu và `Consumer<T>` xử lý dữ liệu. Các kiểu `T` và `R` là tham số kiểu tổng quát: `T` biểu thị kiểu đầu vào, `R` biểu thị kiểu đầu ra. Bài học này tập trung vào cách xác định các kiểu đó, cách dùng `Message<T>` để giữ header và cách chọn chữ ký phù hợp với payload đồng bộ hoặc luồng reactive.

## 1. Đọc chữ ký generic của ba loại hàm

| Kiểu hàm | Chữ ký khái quát | Đầu vào | Đầu ra |
|---|---|---|---|
| `Supplier<T>` | `T get()` | Không có | Một giá trị kiểu `T` |
| `Function<T, R>` | `R apply(T input)` | Một giá trị kiểu `T` | Một giá trị kiểu `R` |
| `Consumer<T>` | `void accept(T input)` | Một giá trị kiểu `T` | Không có giá trị trả về |

Ví dụ trong ứng dụng đơn hàng:

```java
@Bean
Supplier<OrderCreated> orderCreated() {
    return () -> new OrderCreated("ORD-1001", 250_000);
}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), order.total());
}

@Bean
Consumer<OrderAccepted> notifyWarehouse() {
    return order -> System.out.println("Prepare " + order.orderId());
}
```

Trong ví dụ này:

- `Supplier<OrderCreated>` không nhận tham số và tạo một `OrderCreated`.
- `Function<OrderCreated, OrderAccepted>` nhận `OrderCreated`, trả về `OrderAccepted`.
- `Consumer<OrderAccepted>` nhận `OrderAccepted` và thực hiện tác dụng phụ; kiểu trả về là `void`.

Các kiểu DTO có thể là Java record hoặc POJO. Ví dụ dùng record yêu cầu Java 16 trở lên:

```java
public record OrderCreated(String orderId, long total) {}

public record OrderAccepted(String orderId, long total) {}
```

Nếu dự án dùng Java phiên bản cũ hơn, có thể thay record bằng lớp POJO có constructor, getter và các thuộc tính tương ứng. Điều quan trọng là chữ ký hàm khai báo đúng kiểu payload thực tế.

## 2. Xác định kiểu đầu vào và đầu ra của Function

Với `Function<T, R>`, tham số generic thứ nhất luôn là kiểu đầu vào và tham số thứ hai là kiểu đầu ra. Ví dụ:

```java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return event -> new OrderAccepted(event.orderId(), event.total());
}
```

Chữ ký trên có nghĩa:

- Binder chuyển payload đầu vào thành `OrderCreated` trước khi gọi hàm.
- Hàm nhận một đối tượng `OrderCreated`.
- Kết quả trả về phải là `OrderAccepted`.
- Output binding phát payload `OrderAccepted`.

Nếu khai báo nhầm `Function<OrderAccepted, OrderCreated>` nhưng phần thân lại truy cập thuộc tính chỉ có trên `OrderCreated`, compiler sẽ báo lỗi. Nếu khai báo `Function<Object, Object>`, compiler cho phép nhiều thao tác hơn nhưng ứng dụng mất kiểm tra kiểu và thường phải ép kiểu ở runtime.

Có thể xem kiểu generic như hợp đồng giữa các bước xử lý. Khi ghép hai hàm, kiểu đầu ra của bước trước phải tương thích với kiểu đầu vào của bước sau:

```java
Function<OrderCreated, ValidatedOrder> validate = this::validateOrder;
Function<ValidatedOrder, OrderAccepted> accept = this::createAcceptedEvent;

Function<OrderCreated, OrderAccepted> pipeline = validate.andThen(accept);
```

`andThen` tạo hàm mới có kiểu đầu vào `OrderCreated` và đầu ra `OrderAccepted`. Nếu bước thứ nhất trả về `ValidatedOrder` nhưng bước thứ hai nhận `OrderCreated`, chuỗi hàm không thể ghép theo kiểu generic đã khai báo.

Trong Spring Cloud Function, có thể cấu hình composition bằng tên bean, ví dụ `validateOrder|acceptOrder`. Khi composition được sử dụng, hãy bảo đảm kiểu đầu ra của hàm bên trái phù hợp với kiểu đầu vào của hàm bên phải. Cú pháp composition không tự chuyển đổi một DTO nghiệp vụ thành DTO khác nếu không có hàm thực hiện chuyển đổi.

## 3. Kiểu dữ liệu của Supplier và Consumer

### Supplier: chỉ có kiểu đầu ra

`Supplier<T>` không có kiểu đầu vào vì nó không nhận payload từ input binding. Kiểu `T` là kiểu giá trị mà supplier tạo ra:

```java
@Bean
Supplier<OrderCreated> createOrderEvent() {
    return () -> new OrderCreated("ORD-2001", 480_000);
}
```

Spring Cloud Stream tạo output binding cho supplier. Với tên hàm `createOrderEvent`, tên binding mặc định là `createOrderEvent-out-0`. Có thể cấu hình destination tương ứng:

```yaml
spring:
  cloud:
    function:
      definition: createOrderEvent
    stream:
      bindings:
        createOrderEvent-out-0:
          destination: orders.created
          content-type: application/json
```

Supplier thông thường được gọi theo cơ chế polling của framework. Nếu cần phát một luồng sự kiện liên tục hoặc dùng kiểu reactive, có thể khai báo `Supplier<Flux<T>>`; khi đó `T` vẫn là kiểu phần tử của luồng, còn `Flux<T>` là kiểu giá trị được trả về.

### Consumer: chỉ có kiểu đầu vào

`Consumer<T>` nhận một payload kiểu `T` và không trả về kết quả:

```java
@Bean
Consumer<OrderAccepted> updateWarehouse() {
    return event -> warehouseService.reserve(event.orderId());
}
```

Với tên hàm `updateWarehouse`, input binding mặc định là `updateWarehouse-in-0`. Consumer không tạo output binding. Nếu nghiệp vụ cần phát sự kiện sau khi xử lý, hãy dùng `Function<T, R>` để trả về sự kiện hoặc dùng một thành phần gửi message riêng có thiết kế rõ ràng.

## 4. Khi nào nên dùng Message<T> thay cho payload T?

Một hàm có thể nhận trực tiếp payload:

```java
Function<OrderCreated, OrderAccepted>
```

hoặc nhận toàn bộ Spring `Message`:

```java
Function<Message<OrderCreated>, Message<OrderAccepted>>
```

`Message<T>` bao bọc payload kiểu `T` cùng headers. Dùng `Message<T>` khi logic cần đọc hoặc ghi metadata như correlation ID, event ID, tenant ID, content type hoặc thông tin định tuyến. Nếu nghiệp vụ chỉ cần dữ liệu đơn hàng, nhận payload trực tiếp sẽ đơn giản hơn.

Ví dụ giữ lại correlation ID khi biến đổi message:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrderWithHeaders() {
    return message -> {
        OrderCreated input = message.getPayload();
        OrderAccepted output = new OrderAccepted(input.orderId(), input.total());

        return MessageBuilder.withPayload(output)
            .copyHeadersIfAbsent(message.getHeaders())
            .setHeader("eventType", "OrderAccepted")
            .build();
    };
}
```

Trong chữ ký này, kiểu payload đầu vào là `OrderCreated`, còn kiểu payload đầu ra là `OrderAccepted`. Kiểu generic bên ngoài `Message<...>` cho biết hàm làm việc với message có header; nó không biến header thành payload. Nếu dùng `Message<?>`, kiểu payload không được xác định cụ thể và ứng dụng phải kiểm tra kiểu trước khi sử dụng.

Có thể kết hợp payload trực tiếp ở đầu vào và message ở đầu ra nếu chỉ cần thêm metadata:

```java
Function<OrderCreated, Message<OrderAccepted>>
```

Hoặc nhận message nhưng chỉ trả payload:

```java
Function<Message<OrderCreated>, OrderAccepted>
```

Chọn chữ ký theo đúng nhu cầu. Không cần bọc mọi payload trong `Message` nếu hàm không sử dụng header.

## 5. Kiểu generic ảnh hưởng đến chuyển đổi message như thế nào?

Broker thường truyền byte hoặc một dạng dữ liệu đã serialize. Trước khi gọi hàm, Spring Cloud Stream sử dụng content type và message converter để chuyển dữ liệu thành kiểu Java được khai báo. Với output, kết quả hàm được chuyển đổi thành dạng message phù hợp để gửi qua binder.

Ví dụ cấu hình JSON:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Với chữ ký `Function<OrderCreated, OrderAccepted>`, converter có mục tiêu tạo `OrderCreated` từ payload đầu vào và serialize kết quả `OrderAccepted` ở đầu ra. `content-type` mô tả định dạng message; generic type mô tả kiểu Java mà hàm nhận hoặc trả về. Hai thông tin này bổ sung cho nhau.

Một số quy tắc thực hành:

- Dùng DTO có trường và kiểu dữ liệu rõ ràng thay vì `Map<String, Object>` nếu cấu trúc sự kiện đã ổn định.
- Khai báo `Function<OrderCreated, OrderAccepted>` thay vì raw `Function` để giữ thông tin kiểu.
- Đảm bảo JSON đầu vào có thể ánh xạ vào các thuộc tính của `OrderCreated`; tên trường, kiểu số, ngày giờ và cấu hình serializer phải nhất quán.
- Nếu payload là chuỗi thuần, byte array, Avro hoặc định dạng riêng, cấu hình converter/serializer tương ứng thay vì mặc định giả định JSON.
- Nếu một hàm cần header, dùng `Message<T>` và đọc payload bằng `getPayload()`.

Java xóa phần lớn thông tin generic tại runtime (type erasure). Framework có thể đọc metadata generic từ chữ ký khai báo của bean để hỗ trợ chuyển đổi, nhưng kiểu khai báo vẫn cần cụ thể. Những chữ ký như `Function`, `Function<Object, Object>` hoặc `Function<Message<?>, Message<?>>` không cung cấp cùng mức thông tin như `Function<OrderCreated, OrderAccepted>`. Với payload lồng generic, chẳng hạn `Envelope<List<OrderCreated>>`, hãy khai báo đầy đủ kiểu ở chữ ký và kiểm thử chuyển đổi với binder/converter của phiên bản đang dùng.

## 6. Kiểu reactive: Flux<T> và phần tử của luồng

Spring Cloud Stream hỗ trợ hàm reactive dựa trên Reactive Streams. Khi khai báo `Function<Flux<T>, Flux<R>>`, hàm nhận một luồng các phần tử kiểu `T` và trả về luồng các phần tử kiểu `R`:

```java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return orders -> orders
        .filter(order -> order.total() > 0)
        .map(order -> new OrderAccepted(order.orderId(), order.total()));
}
```

Ở đây:

- `Flux<OrderCreated>` là đầu vào; mỗi phần tử là một `OrderCreated`.
- `Flux<OrderAccepted>` là đầu ra; mỗi phần tử được chuyển thành `OrderAccepted`.
- `filter` giữ lại các phần tử thỏa điều kiện.
- `map` biến đổi kiểu phần tử từ `OrderCreated` thành `OrderAccepted`.

`Flux<T>` không đồng nghĩa với một payload JSON là mảng `T` trong mọi cấu hình. Nó biểu thị một luồng reactive gồm nhiều phần tử; cách binder nhận và phát các phần tử tuân theo mô hình reactive của Spring Cloud Stream. Hãy phân biệt hàm xử lý một message có payload là collection với hàm reactive xử lý một luồng message.

Supplier reactive có thể khai báo như sau:

```java
@Bean
Supplier<Flux<OrderCreated>> orderEvents() {
    return () -> Flux.interval(Duration.ofSeconds(1))
        .map(index -> new OrderCreated("ORD-" + index, 100_000));
}
```

`Supplier<Flux<OrderCreated>>` tạo ra luồng phần tử `OrderCreated`; không có kiểu đầu vào. Cần chú ý lifecycle và tốc độ phát dữ liệu của publisher để không tạo nguồn sự kiện vô hạn ngoài dự kiến. Với reactive function, tránh tự gọi `subscribe()` bên trong hàm vì việc đó tách công việc khỏi quá trình quản lý subscription và backpressure của framework.

Với xử lý reactive, ưu tiên chữ ký trả về publisher như `Function<Flux<T>, Flux<R>>` khi cần biến đổi luồng. Không tự gọi `subscribe()` bên trong một hàm rồi kết thúc ngay nếu binder cần quản lý vòng đời, backpressure và tín hiệu lỗi. Nếu cần một consumer reactive thuần, hãy dùng đúng dạng chữ ký và cách subscription được tài liệu của phiên bản Spring Cloud Function/Spring Cloud Stream đang dùng hỗ trợ; không suy luận rằng `Consumer<Flux<T>>` có cùng hành vi với `Consumer<T>` chỉ vì cả hai đều là `Consumer`.

## 7. Đặt tên binding theo chữ ký hàm

Spring Cloud Stream suy ra binding name từ tên bean function và vị trí input/output:

| Kiểu bean | Binding mặc định |
|---|---|
| `Supplier<T> orderEvents` | `orderEvents-out-0` |
| `Function<T, R> acceptOrder` | `acceptOrder-in-0`, `acceptOrder-out-0` |
| `Consumer<T> notifyWarehouse` | `notifyWarehouse-in-0` |

Ví dụ cấu hình function:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Tên binding không được quyết định bởi kiểu Java generic. `Function<OrderCreated, OrderAccepted>` xác định kiểu dữ liệu; tên bean `acceptOrder` xác định phần tên binding. Khi đổi tên bean hoặc dùng composition, cần cập nhật `spring.cloud.function.definition` và cấu hình binding tương ứng.

Nếu có nhiều bean `Supplier`, `Function` hoặc `Consumer`, hãy chỉ định rõ function cần kích hoạt bằng `spring.cloud.function.definition`. Việc để framework tự lựa chọn khi có nhiều bean có thể khiến binding được tạo cho hàm không mong muốn.

## 8. Tránh mất an toàn kiểu khi dùng generic

Các ví dụ dưới đây cho thấy sự khác nhau giữa khai báo rõ kiểu và khai báo quá tổng quát:

```java
// Có kiểu cụ thể: compiler kiểm tra được input và output.
Function<OrderCreated, OrderAccepted> typed = this::accept;

// Raw type: mất kiểm tra generic và có thể gây lỗi ép kiểu lúc chạy.
Function raw = this::accept;

// Quá tổng quát: hàm phải tự kiểm tra kiểu và không mô tả hợp đồng payload.
Function<Object, Object> generic = value -> value;
```

Không dùng raw type chỉ để làm cho lỗi biên dịch biến mất. Nếu một hàm thực sự nhận nhiều kiểu payload, hãy mô hình hóa hợp đồng rõ ràng, ví dụ một interface hoặc sealed hierarchy có discriminator, rồi dùng kiểu cha đó làm tham số generic. Với event có nhiều loại, một envelope có trường `eventType` và payload được xác định theo schema có thể phù hợp hơn một `Object` không có quy ước.

Ví dụ kiểu cha:

```java
public sealed interface OrderEvent permits OrderCreated, OrderCancelled {
    String orderId();
}

public record OrderCreated(String orderId, long total) implements OrderEvent {}

public record OrderCancelled(String orderId, String reason) implements OrderEvent {}

@Bean
Consumer<OrderEvent> handleOrderEvent() {
    return event -> {
        if (event instanceof OrderCreated created) {
            orderService.create(created);
        } else if (event instanceof OrderCancelled cancelled) {
            orderService.cancel(cancelled);
        }
    };
}
```

Đây là ví dụ Java 17 trở lên. Với Java cũ hơn, có thể dùng interface thông thường và kiểm tra kiểu theo cách tương ứng. Dù dùng kiểu cha, converter vẫn phải biết cách tạo đúng subtype từ message; có thể cần discriminator, custom converter hoặc cấu hình serializer rõ ràng.

## 9. Kiểm thử kiểu đầu vào và đầu ra

Trước tiên có thể kiểm thử logic hàm trực tiếp bằng kiểu generic:

```java
@Test
void mapsCreatedOrderToAcceptedOrder() {
    Function<OrderCreated, OrderAccepted> function = order ->
        new OrderAccepted(order.orderId(), order.total());

    OrderAccepted result = function.apply(new OrderCreated("ORD-9", 300_000));

    assertEquals("ORD-9", result.orderId());
    assertEquals(300_000, result.total());
}
```

Kiểm thử này xác nhận phép biến đổi kiểu Java. Nó chưa xác nhận message converter có thể đọc payload JSON thành `OrderCreated`, binder có thể serialize `OrderAccepted`, hoặc header được giữ đúng. Những trường hợp đó cần kiểm thử tích hợp với test binder hoặc broker tương ứng.

Khi kiểm thử binding, nên bao gồm các tình huống:

- Gửi JSON hợp lệ và xác nhận hàm nhận đúng kiểu DTO.
- Gửi payload thiếu trường bắt buộc hoặc sai kiểu dữ liệu và kiểm tra lỗi conversion được quan sát rõ.
- Với `Message<T>`, xác nhận event ID/correlation ID trong header được giữ hoặc cập nhật đúng.
- Với `Function<T, R>`, xác nhận output binding phát đúng kiểu `R`.
- Với `Flux<T>`, kiểm tra nhiều phần tử, lỗi trong luồng và việc hủy subscription theo thiết kế.
- Với payload generic lồng nhau, kiểm tra converter của phiên bản đang sử dụng có thể giải quyết đầy đủ kiểu phần tử.

## 10. Quy tắc chọn chữ ký hàm

| Nhu cầu | Chữ ký nên cân nhắc |
|---|---|
| Tạo sự kiện theo cơ chế supplier | `Supplier<OrderCreated>` |
| Nhận sự kiện và chỉ thực hiện tác dụng phụ | `Consumer<OrderCreated>` |
| Nhận một loại event và tạo loại event khác | `Function<OrderCreated, OrderAccepted>` |
| Cần đọc header đầu vào | `Function<Message<OrderCreated>, OrderAccepted>` |
| Cần tạo hoặc cập nhật header đầu ra | `Function<OrderCreated, Message<OrderAccepted>>` |
| Nhận và trả message có header | `Function<Message<OrderCreated>, Message<OrderAccepted>>` |
| Biến đổi một luồng reactive | `Function<Flux<OrderCreated>, Flux<OrderAccepted>>` |

Khi thiết kế function, hãy xác định payload đầu vào, payload đầu ra, nhu cầu sử dụng header và mô hình đồng bộ hay reactive trước khi viết lambda. Sau đó khai báo generic cụ thể, cấu hình content type phù hợp và kiểm thử conversion qua binding. Chữ ký rõ ràng giúp compiler, framework và người bảo trì cùng hiểu chính xác hợp đồng dữ liệu của từng bước xử lý sự kiện trong Spring Cloud Stream.
