# Khái niệm số đầu vào và đầu ra của hàm

## 1. Vì sao cần quan tâm đến số đầu vào và đầu ra?

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được biểu diễn bằng các hàm Java có hợp đồng đầu vào và đầu ra rõ ràng. Một hàm có thể nhận dữ liệu để biến đổi, tạo dữ liệu mà không cần đầu vào, hoặc chỉ xử lý dữ liệu mà không trả kết quả. Khi tích hợp với HTTP, hệ thống sự kiện hoặc môi trường serverless, hợp đồng này giúp framework biết cách đưa dữ liệu đến hàm và xử lý kết quả.

**Số đầu vào và số đầu ra** (còn gọi là *arity*) trả lời hai câu hỏi:

- Hàm cần bao nhiêu **nguồn/cổng đầu vào logic**?
- Hàm tạo ra bao nhiêu **luồng/cổng đầu ra logic**?

Đây là khái niệm quan trọng khi thiết kế pipeline xử lý sự kiện, đặc biệt khi một hàm cần nhận nhiều luồng hoặc phân loại kết quả sang nhiều đích. Cần phân biệt số cổng với **số phần tử dữ liệu** đi qua từng cổng: một cổng có thể truyền hàng nghìn thông điệp.

Ví dụ trong hệ thống đơn hàng:

| Nhu cầu nghiệp vụ | Mô hình đầu vào → đầu ra | Diễn giải |
| --- | --- | --- |
| Tạo mã đơn hàng mới | `0 → 1` | Không nhận dữ liệu từ bên gọi, trả một mã |
| Chuẩn hóa mã đơn hàng | `1 → 1` | Nhận một mã, trả mã đã chuẩn hóa |
| Ghi nhật ký xử lý đơn | `1 → 0` | Nhận một mã, thực hiện tác dụng phụ, không trả giá trị |
| Gộp luồng đơn hàng và hóa đơn | `2 → 1` | Nhận hai luồng sự kiện, phát ra một luồng |
| Phân luồng đơn VIP và đơn thường | `1 → 2` | Nhận một luồng, phát sang hai luồng đích |

> **Quy ước:** Trong bài này, `m → n` biểu thị **m cổng vào, n cổng ra ở mức hợp đồng hàm hoặc binding**, không phải số tham số xuất hiện trong cú pháp Java, cũng không phải số bản ghi được xử lý trong một lần chạy.

## 2. Ba dạng hàm cơ bản trong Spring Cloud Function

Spring Cloud Function sử dụng các functional interface chuẩn của Java: `Supplier<O>`, `Function<I, O>` và `Consumer<I>`. Chúng được đăng ký dưới dạng Spring bean và được `FunctionCatalog` nhận diện để sử dụng qua những cơ chế gọi khác nhau.

| Functional interface | Số đầu vào | Số đầu ra | Phương thức | Vai trò |
| --- | ---: | ---: | --- | --- |
| `Supplier<O>` | 0 | 1 | `O get()` | Sinh dữ liệu |
| `Function<I, O>` | 1 | 1 | `O apply(I input)` | Biến đổi dữ liệu |
| `Consumer<I>` | 1 | 0 | `void accept(I input)` | Tiếp nhận và xử lý dữ liệu |

Ví dụ minh họa với các bean độc lập:

~~~java
import java.util.Locale;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    // 0 -> 1: tạo mã mỗi khi Supplier được gọi.
    @Bean
    public Supplier<String> generateOrderId() {
        return () -> UUID.randomUUID().toString();
    }

    // 1 -> 1: nhận một mã, trả một mã đã chuẩn hóa.
    @Bean
    public Function<String, String> normalizeOrderId() {
        return id -> id.trim().toUpperCase(Locale.ROOT);
    }

    // 1 -> 0: xử lý mã, không trả về payload.
    @Bean
    public Consumer<String> auditOrderId() {
        return id -> System.out.println("Da xu ly don: " + id);
    }
}
~~~

Chẳng hạn, `normalizeOrderId` nhận `" ord-42 "` và trả `"ORD-42"`. `auditOrderId` có thể ghi log, cập nhật cơ sở dữ liệu hoặc gọi một dịch vụ khác; phương thức `accept` vẫn có kiểu trả về `void`. Trong ứng dụng thực tế, nên dùng hệ thống logging thay cho `System.out.println`.

Một `Supplier` không có đối số đầu vào **không có nghĩa** nó chỉ chạy một lần trong suốt vòng đời ứng dụng: tần suất gọi do cơ chế kích hoạt quyết định. Tương tự, `Consumer` không có giá trị trả về **không có nghĩa** công việc của nó không tạo tác dụng phụ.

## 3. Số cổng khác số phần tử và số thuộc tính

### 3.1. Một đối tượng có nhiều trường vẫn là một đầu vào

Hàm `Function<Order, Result>` nhận một đối tượng `Order`, dù đối tượng có các trường `id`, `customerId`, `items` và `total`. Những trường này không tự trở thành các cổng đầu vào độc lập.

Tương tự, `Function<Message<Order>, Result>` nhận **một** thông điệp gồm `payload` và `headers`. Dữ liệu nghiệp vụ và metadata cùng nằm trong một đối tượng `Message`.

Spring Cloud Function còn hỗ trợ trường hợp đặc biệt `BiFunction<T, Map, R>` và `BiConsumer<T, Map>`: khi gọi qua `FunctionCatalog`, framework có thể tách **payload** và **headers** của cùng một `Message` để truyền thành hai đối số Java. Đối số thứ hai bắt buộc là kiểu `Map`. Đây là **một thông điệp kèm metadata**, không phải hai nguồn sự kiện độc lập; không nên suy rằng mọi `BiFunction<A, B, R>` đều tự động tạo hai input binding.

### 3.2. Một `Flux` chứa nhiều phần tử nhưng vẫn có thể chỉ là một cổng

Trong mô hình reactive của Project Reactor:

~~~java
@Bean
public Function<Flux<Integer>, Flux<Integer>> duplicateValues() {
    return input -> input.flatMap(number ->
            Flux.just(number, number * 10));
}
~~~

Với đầu vào lần lượt là `2, 3`, luồng đầu ra có thể phát `2, 20, 3, 30`. Số **phần tử** đã tăng từ 2 thành 4, nhưng chữ ký hàm vẫn là **một luồng vào, một luồng ra** (`1 → 1`). Lưu ý thứ tự giữa các phần tử có thể thay đổi khi dùng `flatMap` với các tác vụ bất đồng bộ.

Các trường hợp dễ nhầm:

| Chữ ký hoặc hành vi | Cách hiểu đúng |
| --- | --- |
| `Function<Order, List<Result>>` | Một giá trị đầu ra Java chứa danh sách kết quả |
| `Function<Flux<Order>, Flux<Result>>` | Một luồng đầu vào và một luồng đầu ra; mỗi luồng có nhiều phần tử |
| `Flux.empty()` trong hàm reactive | Không phát phần tử nào ở lần xử lý đó; **không** xóa cổng đầu ra đã khai báo |
| `flatMap` sinh nhiều phần tử | Thay đổi số phần tử phát ra, **không** tạo thêm output binding |
| `Consumer<Order>` ghi vào hai bảng dữ liệu | Vẫn là `1 → 0` ở hợp đồng functional bean; hai tác dụng phụ không phải hai cổng trả về |

Một adapter cụ thể có thể xử lý collection theo quy tắc riêng. Ví dụ Spring Cloud Stream hỗ trợ trường hợp trả một `List<Message<T>>` rồi gửi từng `Message` thành thông điệp riêng. Đây là **nhiều thông điệp trên một đầu ra**, khác với nhiều output binding.

### 3.3. Số tham số Java không luôn bằng số cổng logic

Chữ ký `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` chỉ có **một tham số Java** của phương thức `apply`: một `Tuple2`. Tuy nhiên, Spring Cloud Function có thể nhận diện hai thành phần `Flux` của tuple như **hai cổng đầu vào logic** trong mô hình function arity. Đây là lý do phải đọc kiểu dữ liệu bên trong, thay vì chỉ đếm dấu phẩy của phương thức.

## 4. Nhiều đầu vào, nhiều đầu ra với reactive function

Khi bài toán cần **nhiều luồng độc lập**, Spring Cloud Function cung cấp cơ chế *Function Arity* dựa trên `Flux` và các tuple của Reactor, chẳng hạn `Tuple2`. Các phần tử trong tuple mang thông tin về **số cổng** và **kiểu dữ liệu của từng cổng**.

Các dạng thường gặp:

| Chữ ký | Arity logic | Tình huống sử dụng |
| --- | --- | --- |
| `Function<Flux<A>, Flux<B>>` | `1 → 1` | Biến đổi một luồng sự kiện |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<C>>` | `2 → 1` | Gộp hai luồng nguồn |
| `Function<Flux<A>, Tuple2<Flux<B>, Flux<C>>>` | `1 → 2` | Phân loại sự kiện sang hai luồng |
| `Function<Tuple2<Flux<A>, Flux<B>>, Tuple2<Flux<C>, Flux<D>>>` | `2 → 2` | Xử lý hai nguồn và phát ra hai luồng |

Điểm giới hạn cần nhớ: **hỗ trợ nhiều cổng bằng function arity tập trung vào reactive functions**. Viết một hàm imperative trả về `Tuple2<Value1, Value2>` không mặc nhiên tạo hai output binding. Việc ánh xạ những cổng này ra topic/queue cụ thể còn phụ thuộc adapter, điển hình là Spring Cloud Stream.

### 4.1. Ví dụ `2 → 1`: gộp hai luồng

Giả sử một luồng mang mã đơn hàng (`String`), luồng còn lại mang mã hóa đơn (`Long`). Hàm `combineEvents` gắn nhãn từng loại và đưa cả hai về một luồng kết quả:

~~~java
@Bean
public Function<Tuple2<Flux<String>, Flux<Long>>, Flux<String>>
        combineEvents() {
    return sources -> Flux.merge(
            sources.getT1().map(id -> "ORDER:" + id),
            sources.getT2().map(id -> "INVOICE:" + id));
}
~~~

`getT1()` truy cập luồng đầu vào thứ nhất, `getT2()` truy cập luồng thứ hai. `Flux.merge` đưa các sự kiện từ hai luồng vào một luồng kết quả khi chúng đến; **không** tự ghép đơn hàng với hóa đơn có cùng mã. Nếu cần đối soát theo khóa, phải thiết kế thêm quy tắc tương quan, đồng bộ thời gian hoặc cửa sổ xử lý thích hợp.

Sơ đồ luồng:

~~~text
Luồng đơn hàng  ──> [ input 0 ] ┐
                                ├── combineEvents ──> [ output 0 ] ──> Luồng sự kiện chung
Luồng hóa đơn   ──> [ input 1 ] ┘
~~~

### 4.2. Ví dụ `1 → 2`: phân loại đơn hàng

Hàm sau chia mã đơn hàng thành nhóm VIP (mã bắt đầu bằng `VIP-`) và nhóm thông thường:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class MultiPortFunctions {

    @Bean
    public Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>>
            classifyOrders() {
        return incoming -> {
            // Chia sẻ một nguồn cho hai nhánh, chờ đủ hai subscriber.
            Flux<String> shared = incoming.publish().autoConnect(2);

            Flux<String> vip = shared.filter(id -> id.startsWith("VIP-"));
            Flux<String> regular = shared.filter(id -> !id.startsWith("VIP-"));

            return Tuples.of(vip, regular);
        };
    }
}
~~~

Nếu luồng đầu vào có `VIP-101`, `ORD-102`, `VIP-103` thì luồng VIP nhận `VIP-101` và `VIP-103`, còn luồng thường nhận `ORD-102`. Đây là hai **đầu ra độc lập**: phía tích hợp có thể nối mỗi đầu ra đến một đích khác nhau.

`publish().autoConnect(2)` giúp hai nhánh dùng chung subscription đến nguồn và chỉ kết nối khi cả hai nhánh đã có subscriber, tránh việc mỗi nhánh tự subscribe riêng vào nguồn. Ví dụ giả định **cả hai output đều được subscribe**; nếu thiếu một subscriber, kết nối sẽ chưa bắt đầu. Khi xây dựng hệ thống thực tế, cần kiểm tra vòng đời subscription, backpressure và cách xử lý lỗi theo adapter/binder đang sử dụng.

Sơ đồ luồng:

~~~text
                     ┌── [ output 0: VIP ] ─────> orders.vip
orders.in ──> classifyOrders
                     └── [ output 1: thường ] ──> orders.regular
~~~

## 5. Các cổng được ánh xạ thành binding như thế nào?

`FunctionCatalog` chịu trách nhiệm khám phá, chuẩn hóa và tra cứu các functional bean; nó hỗ trợ composition và chuyển đổi dữ liệu theo kiểu được khai báo. **Spring Cloud Stream** là một ví dụ adapter biến các cổng logic thành *binding* nối với topic/queue trong hệ thống messaging.

Với hàm `classifyOrders` ở trên, quy ước tên binding mặc định là:

| Tên binding | Ý nghĩa |
| --- | --- |
| `classifyOrders-in-0` | Luồng đầu vào duy nhất |
| `classifyOrders-out-0` | Luồng đầu ra thứ nhất: đơn VIP |
| `classifyOrders-out-1` | Luồng đầu ra thứ hai: đơn thường |

Ví dụ cấu hình trong `application.yml` (khi ứng dụng có Spring Cloud Stream và binder phù hợp):

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrders
    stream:
      bindings:
        classifyOrders-in-0:
          destination: orders.in
        classifyOrders-out-0:
          destination: orders.vip
        classifyOrders-out-1:
          destination: orders.regular
~~~

Tương ứng, hàm `combineEvents` dạng `2 → 1` có các binding mặc định: `combineEvents-in-0`, `combineEvents-in-1` và `combineEvents-out-0`.

**Chú ý:** Để cấu hình chạy được, dự án cần các dependency Spring Cloud Function, Reactor, Spring Cloud Stream và một binder messaging thích hợp. Khai báo functional bean **tự nó chưa tạo ra topic/queue**. Tên binding mô tả cổng logic, còn `destination` cấu hình đích cụ thể.

## 6. Composition có làm thay đổi số đầu vào và đầu ra không?

Spring Cloud Function cho phép ghép các hàm trong `spring.cloud.function.definition` bằng ký hiệu `|`. Ví dụ:

~~~properties
spring.cloud.function.definition=normalizeOrderId|auditOrderId
~~~

Đầu ra của `normalizeOrderId` (một `String`) trở thành đầu vào của `auditOrderId`. Chuỗi cuối cùng có hợp đồng `1 → 0` vì kết thúc bằng `Consumer`. Nếu ghép hai `Function<I, O>` tương thích, chuỗi thông thường vẫn là `1 → 1`; nếu ghép `Supplier` với `Function`, chuỗi vẫn không cần đầu vào trực tiếp.

~~~text
" ord-42 " ──> normalizeOrderId ──> "ORD-42" ──> auditOrderId
      1 đầu vào                                 không có giá trị trả về
~~~

Composition theo `|` là **kết nối tuần tự** giữa các hàm, không phải cơ chế tự tạo thêm nhánh đầu ra. Khi yêu cầu là đưa dữ liệu sang nhiều kênh khác nhau, hãy thiết kế rõ số cổng bằng reactive tuple hoặc sử dụng các thành phần định tuyến/tích hợp thích hợp.

Một số tổ hợp không có ý nghĩa nối tiếp: `Consumer` không trả giá trị cho `Function` kế tiếp xử lý. Hãy kiểm tra kiểu đầu ra của bước trước và kiểu đầu vào của bước sau trước khi định nghĩa pipeline.

## 7. Tách logic hàm khỏi giao thức gọi

Mục tiêu thiết kế của Spring Cloud Function là viết logic có thể tái sử dụng mà không gắn cứng với HTTP, broker hay nền tảng serverless. Cùng một bean `Function<I, O>` có thể được `FunctionCatalog` tìm và bao bọc bằng cơ chế chuyển đổi kiểu/thông điệp, sau đó adapter cụ thể quyết định cách gọi:

| Môi trường | Cách một hợp đồng hàm có thể được sử dụng |
| --- | --- |
| HTTP | Web adapter ánh xạ request đến đầu vào và biến kết quả thành response |
| Sự kiện/message broker | Spring Cloud Stream gắn input/output binding với destination |
| Serverless | Adapter của nền tảng chuyển sự kiện gọi hàm thành input và xử lý output |

Khả năng hỗ trợ **kiểu chữ ký cụ thể** có thể khác nhau giữa các adapter. Đặc biệt, mô hình nhiều cổng reactive cần cơ chế hỗ trợ luồng và binding phù hợp; không thể mặc nhiên xem một hàm `2 → 2` là bốn HTTP endpoint độc lập.

Khi dữ liệu đi qua thông điệp, cần lưu ý **payload**, **headers** và **content type**. Một `Function<Message<Order>, Result>` có thể dùng metadata ngoài payload, và `FunctionCatalog` có khả năng hỗ trợ chuyển đổi đầu vào/đầu ra theo thông tin kiểu khi adapter cung cấp dữ liệu phù hợp. Chuyển đổi kiểu không làm thay đổi số cổng đã thiết kế.

## 8. Cách chọn hợp đồng hàm và những lỗi phổ biến

Hãy bắt đầu từ sơ đồ luồng nghiệp vụ và xác định **nguồn dữ liệu độc lập** cùng **đích xử lý độc lập**:

| Câu hỏi thiết kế | Gợi ý |
| --- | --- |
| Không có thông điệp đầu vào mà cần tạo dữ liệu? | `Supplier<O>` |
| Một dữ liệu vào cần một kết quả? | `Function<I, O>` |
| Chỉ cần tác dụng phụ như lưu hoặc ghi log? | `Consumer<I>` |
| Một nguồn có thể sinh nhiều bản ghi trên cùng kênh? | `Function<Flux<I>, Flux<O>>` với `flatMap`/`concatMap` khi phù hợp |
| Có hai luồng đầu vào độc lập cần hợp nhất/xử lý cùng nhau? | Reactive function với `Tuple2<Flux<A>, Flux<B>>` ở đầu vào |
| Cần đưa sự kiện ra hai đích khác nhau? | Reactive function trả `Tuple2<Flux<A>, Flux<B>>` và ánh xạ từng output binding |

Những sai lầm thường gặp:

1. **Đếm số trường của đối tượng thành số cổng.** Đối tượng có nhiều thuộc tính vẫn là một input nếu hàm nhận một payload.
2. **Đếm số phần tử của `List`/`Flux` thành số cổng.** Một luồng có thể có vô hạn phần tử nhưng chỉ chiếm một binding.
3. **Nhầm `BiFunction` với hai nguồn message.** Trường hợp `BiFunction<T, Map, R>` dành cho payload và headers của cùng một thông điệp.
4. **Dùng tuple imperative để kỳ vọng hai output binding.** Function arity nhiều cổng được hỗ trợ trong mô hình reactive.
5. **Quên ràng buộc kỹ thuật của các nhánh reactive.** Việc chia một `Flux` thành nhiều nhánh có thể dẫn đến subscription lặp, mất sự kiện hoặc không khởi chạy nếu kết nối/subscription không được quản lý đúng.
6. **Nhầm composition với phân nhánh.** `a|b` gọi `b` sau `a`; nó không có nghĩa là một đầu vào được phát đồng thời sang cả hai hàm.

### Ví dụ tự đối chiếu

- `Supplier<Flux<Order>>`: **0 → 1** (một luồng do Supplier cung cấp).
- `Function<Message<Order>, Result>`: **1 → 1** (một thông điệp mang payload và headers).
- `Function<Flux<Order>, Flux<Result>>`: **1 → 1** (số phần tử có thể thay đổi).
- `Function<Tuple2<Flux<Order>, Flux<Invoice>>, Flux<Report>>`: **2 → 1** (hai nguồn độc lập gộp thành một luồng).
- `Function<Flux<Order>, Tuple2<Flux<Accepted>, Flux<Rejected>>>`: **1 → 2** (hai cổng đầu ra).
- `Consumer<Order>`: **1 → 0** (không trả payload).

Khi đã nhận diện đúng số cổng, việc thiết kế `FunctionCatalog`, composition, chuyển đổi thông điệp và triển khai cùng logic qua HTTP, sự kiện hoặc serverless sẽ rõ ràng hơn: **chữ ký hàm xác định hợp đồng logic; adapter xác định cách hợp đồng đó kết nối với thế giới bên ngoài**.

### Tài liệu tham khảo

- [Spring Cloud Function — Programming model và Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
