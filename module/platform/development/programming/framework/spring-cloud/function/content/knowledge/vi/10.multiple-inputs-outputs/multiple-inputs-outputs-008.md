# Giới hạn chữ ký và hỗ trợ của từng adapter

## 1. Vì sao một chữ ký hợp lệ chưa chắc chạy được ở mọi môi trường?

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đóng gói dưới dạng `Supplier`, `Function` và `Consumer` để có thể tái sử dụng mà không gắn cứng với HTTP, message broker hoặc một nhà cung cấp serverless. `FunctionCatalog` cho phép tra cứu, chuẩn hóa, composition và hỗ trợ chuyển đổi thông điệp dựa trên kiểu dữ liệu đã khai báo. Tuy nhiên, **năng lực biểu diễn của một Java function khác với năng lực kết nối của adapter**.

Ví dụ, cả hai chữ ký dưới đây đều diễn tả một `Function`:

~~~java
Function<String, String> normalize;

Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>> split;
~~~

Hàm `normalize` có **một giá trị vào, một giá trị ra** nên có thể ánh xạ tương đối trực tiếp thành một HTTP request/response, một message vào/message ra hoặc một invocation serverless. Hàm `split` lại có **một luồng vào, hai luồng ra**. Điều này có ý nghĩa tự nhiên khi một adapter hỗ trợ **hai output binding độc lập**, nhưng không đồng nghĩa một HTTP request sẽ sinh hai HTTP response hoặc một Lambda invocation sẽ tự phát sang hai topic.

Trong chương **Nhiều đầu vào/ra**, cần phân biệt ba tầng:

1. **Chữ ký và logic Java:** Những kiểu nào được khai báo trong `Supplier`, `Function`, `Consumer`?
2. **Spring Cloud Function:** `FunctionCatalog` có nhận diện, chuẩn hóa và chuyển đổi kiểu được chữ ký đó không?
3. **Adapter/binder:** Môi trường thực thi có tạo được đúng số nguồn/đích, quản lý subscription, chuyển đổi dữ liệu, bảo đảm giao nhận và xử lý lỗi hay không?

> **Nguyên tắc thiết kế:** Chữ ký hợp lệ trong Java, hoặc tra cứu được từ `FunctionCatalog`, **không tự bảo đảm** mọi adapter sẽ hỗ trợ cùng số đầu vào, đầu ra và ngữ nghĩa vận hành.

## 2. Các chữ ký nền tảng và giới hạn tự thân

Spring Cloud Function sử dụng ba functional interface chuẩn của Java, đồng thời có hỗ trợ cho kiểu reactive của Project Reactor:

| Chữ ký | Hợp đồng logic | Điều cần chú ý |
| --- | --- | --- |
| `Supplier<O>` | 0 vào → 1 ra | Không có input để kích hoạt; adapter quyết định khi nào gọi `get()` |
| `Function<I, O>` | 1 vào → 1 ra | Tương đối dễ sử dụng trong request/response và xử lý từng message |
| `Consumer<I>` | 1 vào → 0 ra | `accept` có kiểu trả về `void`; kết quả nghiệp vụ chủ yếu là tác dụng phụ |
| `Supplier<Flux<O>>` | 0 vào → 1 luồng ra | Nguồn reactive có thể dài hoặc không kết thúc; vòng đời và cách phát phụ thuộc adapter |
| `Function<Flux<I>, Flux<O>>` | 1 luồng vào → 1 luồng ra | Có thể biến đổi nhiều sự kiện trong một pipeline reactive |
| `Function<Flux<I>, Mono<Void>>` | 1 luồng vào → không phát payload kết quả | Mẫu xử lý reactive có tín hiệu hoàn tất, có thể thích hợp hơn `Consumer<Flux<I>>` trong messaging |
| `Consumer<Flux<I>>` | Nhận một publisher, trả `void` | Framework không có publisher trả về để subscribe; bên triển khai phải quản lý subscription |

### 2.1. Invocation của hàm imperative và reactive khác nhau

Trong Spring Cloud Stream, một `Function<I, O>` imperative thường được gọi **cho từng message**. Ngược lại, một `Function<Flux<I>, Flux<O>>` reactive được gọi để **thiết lập pipeline**; sau đó các phần tử đi qua luồng mà không cần gọi lại phương thức `apply` cho mỗi bản ghi.

~~~text
Imperative
message A ─> apply(A) ─> result A
message B ─> apply(B) ─> result B
message C ─> apply(C) ─> result C

Reactive
Flux nguồn ─> apply(Flux nguồn) ─> Flux kết quả
                  (thiết lập pipeline)
Các message về sau đi qua pipeline đã được kết nối.
~~~

Khác biệt này ảnh hưởng đến retry, error handler và routing theo từng message. Trong Spring Cloud Stream, các cơ chế retry/error handler theo invocation của **message handler imperative** không thể mặc nhiên áp dụng tương tự cho phần tử bên trong một `Flux`. Với reactive code, cần xử lý lỗi bằng các toán tử Reactor và đánh giá khả năng của binder.

### 2.2. BiFunction không phải hỗ trợ tùy ý cho hai nguồn đầu vào

Spring Cloud Function còn nhận diện trường hợp `BiFunction<T, Map, R>` và `BiConsumer<T, Map>`, trong đó đối số thứ hai là **Map của headers** được lấy từ **cùng một `Message`** với payload `T`. Ví dụ:

~~~java
import java.util.Map;
import java.util.function.BiFunction;

BiFunction<String, Map, String> describeEvent =
        (payload, headers) ->
                payload + ":" + headers.getOrDefault("source", "unknown");
~~~

Chữ ký này có **hai tham số Java**, nhưng không diễn tả hai topic độc lập. Nó là một cách đọc **payload + metadata của một message**. Không nên suy rằng `BiFunction<Order, Payment, Result>` sẽ tự động tạo các binding `-in-0`, `-in-1`.

Nếu muốn xử lý metadata một cách tường minh hơn, dùng `Function<Message<I>, O>` hoặc `Function<Message<I>, Message<O>>`, tùy nhu cầu bảo toàn headers.

## 3. Giới hạn của function arity nhiều đầu vào/ra

Theo mô hình **Function Arity** của Spring Cloud Function, khả năng biểu diễn nhiều cổng được xây dựng cho **reactive functions** dùng các `Flux` và `TupleN` của Reactor:

~~~java
// Một luồng đầu vào, hai luồng đầu ra.
Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>

// Hai luồng đầu vào, một luồng đầu ra.
Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>

// Hai luồng đầu vào, hai luồng đầu ra.
Function<
    Tuple2<Flux<A>, Flux<B>>,
    Tuple2<Flux<C>, Flux<D>>>
~~~

`TupleN` cho biết **số lượng cổng** và **kiểu của từng cổng**; Spring Cloud Stream sử dụng thông tin này để tạo binding tương ứng:

| Vị trí tuple | Accessor Reactor | Chỉ số input/output binding |
| --- | --- | --- |
| Thành phần thứ nhất | `getT1()` | `-in-0` / `-out-0` |
| Thành phần thứ hai | `getT2()` | `-in-1` / `-out-1` |
| Thành phần thứ ba | `getT3()` | `-in-2` / `-out-2` |

**Không tương đương với multi-output binding:**

~~~java
Function<Order, Tuple2<Accepted, Rejected>> // Một đối tượng trả về.
Function<Order, List<Result>>              // Một Collection trả về.
Function<Flux<Order>, Flux<Tuple2<A, B>>>  // Một luồng phát các cặp.
~~~

Ba chữ ký này **không tự tạo** các output binding riêng biệt. Với `Flux<Tuple2<A, B>>`, mỗi phần tử của **một** luồng là một tuple giá trị. Với `Tuple2<Flux<A>, Flux<B>>`, có **hai** publisher độc lập.

Sự khác biệt cũng áp dụng cho `Flux<List<T>>`, `List<Message<T>>` và số message được phát trên một destination: **số phần tử hay số message không phải số cổng**. Một số adapter có quy tắc riêng cho Collection, nên phải kiểm tra cách adapter serialize hoặc phát từng phần tử.

## 4. Ma trận khả năng theo adapter

Bảng dưới mô tả **mô hình sử dụng tự nhiên và được tài liệu hướng dẫn**, không phải cam kết mọi phiên bản, binder hoặc trigger đều hỗ trợ mọi cách khai báo:

| Kiểu hàm | Spring Cloud Function + FunctionCatalog | Web adapter (HTTP) | Spring Cloud Stream (messaging) | AWS/Azure/GCP serverless adapter |
| --- | --- | --- | --- | --- |
| `Function<I, O>` | Tra cứu/gọi và chuyển đổi kiểu | Request → response | Input binding → output binding | Phù hợp cho event/request → kết quả khi adapter hỗ trợ kiểu |
| `Supplier<O>` | Hàm không đối số | Có thể truy cập qua HTTP GET | Output binding; cơ chế poll/kích hoạt do framework xử lý | Phụ thuộc trigger và adapter |
| `Consumer<I>` | Nhận đầu vào, không trả payload | HTTP request gọi consumer | Input binding, xử lý message | Phù hợp với một số event trigger |
| `Function<Flux<I>, Flux<O>>` | Hỗ trợ reactive API | Có hỗ trợ phản hồi nhiều giá trị/SSE trong trường hợp phù hợp | Hỗ trợ pipeline reactive; tính năng thực tế tùy binder | Phải kiểm tra cách adapter ánh xạ publisher và vòng đời invocation |
| `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` | Mô hình arity reactive | **Không tự tạo hai HTTP response/endpoint** | Có thể tạo **hai output binding** | **Không tự tạo hai destination/trigger** |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` | Mô hình arity reactive | **Không tự tạo hai request source** | Có thể tạo **hai input binding** | **Không tự tạo hai nguồn sự kiện** |
| `Function<I, List<O>>` | Một giá trị Collection | Có thể trả một mảng JSON | Cách phát Collection phụ thuộc cơ chế adapter/binder | Có thể serialize một payload Collection; tùy adapter |

Các ô có chữ **“không tự”** rất quan trọng: có thể viết **mã tích hợp bổ sung** để lấy nhiều sự kiện từ các nguồn khác rồi gọi hàm, hoặc tự gửi kết quả đến nhiều dịch vụ. Nhưng đó là trách nhiệm của phần tích hợp, không phải hành vi suy ra tự động từ chữ ký `TupleN`.

## 5. Adapter HTTP: một lời gọi gắn với một phản hồi

Module `spring-cloud-function-web` có thể xuất các functional bean thành các HTTP endpoint trong ứng dụng Spring Boot web. Ví dụ:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeCode() {
        return code -> code.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Với web adapter được bật, có thể gửi request theo đường dẫn của hàm:

~~~http
POST /normalizeCode HTTP/1.1
Content-Type: text/plain
Accept: text/plain

 ord-42
~~~

Hàm trả giá trị `ORD-42` để adapter chuyển thành HTTP response. Web adapter hỗ trợ các ánh xạ cơ bản cho `Supplier` (chẳng hạn GET), `Function` và `Consumer` (chẳng hạn POST). Với kết quả nhiều giá trị, client có thể yêu cầu **server-sent events** qua `Accept: text/event-stream` khi chữ ký và môi trường phù hợp.

Tuy vậy:

- Một HTTP request thông thường có **một kênh response**. Trả `List<Result>` có thể tạo một mảng JSON, và trả `Flux<Result>` có thể tạo một dòng response; cả hai vẫn là **một endpoint/response**.
- Trả `Tuple2<Flux<A>, Flux<B>>` **không tự biến thành** hai endpoint hoặc hai response độc lập với hai mã trạng thái HTTP.
- HTTP không có khái niệm nhiều **input binding** đặt tên `-in-0`, `-in-1` tương tự Spring Cloud Stream. Nếu một request chứa nhiều dữ liệu, adapter sẽ parse chúng theo hợp đồng request.
- Nếu cần API phức tạp (nhiều route, xác thực, xử lý lỗi theo chuẩn REST, streaming nâng cao), nên cân nhắc xây dựng API bằng Spring MVC/WebFlux và **gọi lại bean nghiệp vụ**.

Web adapter giúp xuất hàm qua HTTP, nhưng **không thay thế toàn bộ** khả năng của Spring MVC hoặc WebFlux.

## 6. Spring Cloud Stream: nơi function arity thành nhiều binding

Với messaging, Spring Cloud Stream biến các đầu vào/ra logic thành **input/output binding**; mỗi binding có thể gắn vào một destination của binder như Kafka hoặc RabbitMQ.

Ví dụ phân loại thanh toán thành hai luồng:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class PaymentRoutingFunctions {

    public record Payment(String id, long amountVnd) {}

    @Bean
    public Function<Flux<Payment>,
            Tuple2<Flux<Payment>, Flux<Payment>>> splitPayments() {

        return input -> {
            // Chỉ kết nối upstream khi cả hai output có subscriber.
            Flux<Payment> shared = input.publish().autoConnect(2);

            Flux<Payment> large = shared
                    .filter(p -> p.amountVnd() >= 1_000_000L);
            Flux<Payment> regular = shared
                    .filter(p -> p.amountVnd() < 1_000_000L);

            return Tuples.of(large, regular);
        };
    }
}
~~~

Hàm có **1 input binding, 2 output binding**:

~~~text
payments.received  --> splitPayments-in-0
                           |
                      splitPayments
                      /            \
             -out-0                 -out-1
                 |                      |
       payments.large         payments.regular
~~~

Ví dụ `application.yml` (giả định dự án đã có Spring Cloud Stream cùng binder thích hợp):

~~~yaml
spring:
  cloud:
    function:
      definition: splitPayments
    stream:
      bindings:
        splitPayments-in-0:
          destination: payments.received
          content-type: application/json
        splitPayments-out-0:
          destination: payments.large
          content-type: application/json
        splitPayments-out-1:
          destination: payments.regular
          content-type: application/json
~~~

`getT1()` là luồng output 0; `getT2()` là luồng output 1. Adapter phải subscribe các luồng đầu ra để dữ liệu chạy. Mẫu `publish().autoConnect(2)` trong ví dụ **giả định cả hai nhánh đều được subscribe**; nếu một nhánh không có subscriber thì nguồn chưa kết nối. Cách chia sẻ nguồn cần được kiểm tra cùng vòng đời subscription và backpressure.

### 6.1. Có dùng được mọi tính năng reactive với mọi binder không?

**Không.** Dùng `Flux` trong chữ ký không đồng nghĩa hệ thống có **backpressure end-to-end**. Với binder không reactive (chẳng hạn các binder Kafka/Rabbit thông thường), mã Reactor vẫn cung cấp phép biến đổi luồng, nhưng giới hạn tốc độ từ broker đến ứng dụng và khả năng điều tiết phía broker khác với một hệ thống reactive toàn diện. Tài liệu Spring Cloud Stream phân biệt rõ **reactive API** với binder có hỗ trợ cơ chế reactive tương ứng.

Khi chọn binder, cần kiểm tra:

- Kiểu binder và mức hỗ trợ reactive/backpressure.
- Cách adapter nối và subscribe các publisher.
- Cấu hình serialization, `content-type` và schema riêng của từng cổng.
- Tác động khi một output chậm hoặc một destination không sẵn sàng.
- Chính sách lỗi/retry/DLQ, đặc biệt đối với reactive function.

### 6.2. Retry của reactive function khác imperative function

Với imperative message handler, Spring Cloud Stream có thể áp dụng retry/error handling quanh **mỗi lần xử lý message**, tùy binder. Với reactive function, framework thường chỉ gọi hàm lúc thiết lập pipeline rồi không trực tiếp quản lý từng phần tử trong pipeline đó. Vì vậy các cấu hình retry/error handler của imperative không mặc nhiên hoạt động giống hệt với reactive.

Ví dụ cách **mô tả chính sách lỗi cho từng phần tử** ngay trong luồng:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

// Chuyển số hợp lệ; dữ liệu sai được ghi nhận ở một xử lý bổ sung.
Function<Flux<String>, Flux<Long>> parseNumbers = input ->
        input.flatMap(text -> {
            try {
                return Flux.just(Long.parseLong(text));
            } catch (NumberFormatException invalidNumber) {
                // Ví dụ minh họa chính sách bỏ qua bản ghi không hợp lệ.
                // Production: ghi nhận lỗi / dead-letter theo yêu cầu.
                return Flux.<Long>empty();
            }
        });
~~~

Đoạn ví dụ này **cố tình bỏ qua** phần tử sai để minh họa phạm vi xử lý lỗi, chưa đáp ứng yêu cầu ghi nhận lỗi hoặc giao nhận bền vững của một hệ thống production. Với yêu cầu đáng tin cậy hơn, cần thiết kế nhánh lỗi/quan sát, retry giới hạn và bảo đảm giao nhận của binder.

### 6.3. Reactive Consumer là một trường hợp đặc biệt

Một bean `Consumer<Flux<T>>` trả về `void`, do đó adapter không có publisher kết quả để subscribe. Theo hướng dẫn Spring Cloud Stream, nếu cần kiểu chữ ký này, **code của consumer phải chủ động subscribe**; nhưng subscription thủ công có thể khiến vòng đời và xử lý lỗi khó kiểm soát.

Với việc xử lý luồng đến lúc hoàn tất, có thể cân nhắc dạng `Function<Flux<T>, Mono<Void>>` sử dụng toán tử `then()` để biểu diễn completion. Cần kiểm tra hành vi subscription và hỗ trợ của phiên bản adapter/binder thực tế, đặc biệt khi luồng không bao giờ hoàn tất.

## 7. Adapter serverless: một lần kích hoạt theo hợp đồng nền tảng

Spring Cloud Function có adapter cho các nền tảng như **AWS Lambda**, **Azure Functions** và **Google Cloud Functions**. Điểm chung là adapter chuyển request/sự kiện theo hợp đồng nền tảng thành lời gọi hàm trong `FunctionCatalog` và chuyển kết quả trở lại nền tảng.

Ví dụ một bean nghiệp vụ dùng chung:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClassificationFunctions {

    public record Order(String id, long totalVnd) {}
    public record Decision(String id, String category) {}

    @Bean
    public Function<Order, Decision> classifyOrder() {
        return order -> new Decision(
                order.id(),
                order.totalVnd() >= 1_000_000L ? "PRIORITY" : "STANDARD");
    }
}
~~~

Đây là chữ ký **`Function<I, O>`** tương đối dễ mang sang nhiều adapter: một đối tượng `Order` đi vào, một `Decision` đi ra. **Mã phân loại** không cần biết ai gọi nó. Phần cấu hình triển khai khác nhau theo nền tảng:

| Adapter | Hình thức kích hoạt điển hình | Điều cần cấu hình và kiểm tra |
| --- | --- | --- |
| AWS Lambda | API Gateway, SQS, S3 hoặc trigger khác | `spring-cloud-function-adapter-aws`; handler `FunctionInvoker`; event type và response contract |
| Azure Functions | HTTP trigger, queue/event trigger... | Adapter Azure và Azure Function entry point/trigger binding; runtime và kiểu dữ liệu |
| Google Cloud Functions | HTTP hoặc background event | Adapter GCP, entry point, định dạng sự kiện và giới hạn trigger |

**Một lời gọi serverless không tự tương đương một input/output binding của Spring Cloud Stream.** Ví dụ, Lambda được kích hoạt bởi SQS thường nhận một event theo hợp đồng của Lambda; nó **không tự gắn** các `getT1()`/`getT2()` vào hai queue chỉ vì bean trả `Tuple2<Flux<A>, Flux<B>>`. Để lấy nhiều nguồn hoặc phát nhiều đích, cần thiết kế tích hợp theo khả năng của nền tảng, chẳng hạn event source mapping, message publisher hoặc stream processor chuyên biệt.

### 7.1. Ví dụ chọn function trên AWS Lambda

Với adapter AWS chính thức, handler tích hợp được khuyến nghị là:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Nếu dự án có nhiều functional bean, có thể cung cấp cấu hình chọn hàm, ví dụ biến môi trường theo quy tắc AWS/SCF:

~~~text
spring_cloud_function_definition=classifyOrder
~~~

Khi nhận một event phù hợp với `Order`, adapter cố gắng chuyển kiểu vào `Order` và serialize kết quả `Decision` theo quy tắc của nền tảng. Nếu trigger nhận đối tượng chuyên biệt như sự kiện SQS hoặc S3, chữ ký có thể cần sử dụng **kiểu event** của AWS, hoặc một lớp chuyển đổi riêng. Không nên giả định mọi event đều có JSON giống `Order`.

### 7.2. Vòng đời, thời gian thực thi và kết quả

Serverless thường có các ràng buộc cụ thể: timeout mỗi invocation, bộ nhớ, kích thước payload, số lần retry và xử lý sự kiện thất bại. Một `Flux` vô hạn có thể phù hợp với hệ thống messaging chạy liên tục nhưng **không mặc nhiên thích hợp** với một invocation serverless hữu hạn. Việc adapter hỗ trợ publisher reactive, phát streaming response hay xử lý batch phải kiểm chứng theo tài liệu và runtime của nền tảng cụ thể.

Nếu cần phản hồi HTTP khác với kết quả event trigger, hãy kiểm tra hợp đồng của trigger: một hàm `Consumer<I>` không trả payload Java, nhưng nền tảng có thể vẫn cần mã trạng thái/acknowledgment hoặc một kết quả theo kiểu riêng.

## 8. Composition và routing: giới hạn không thể suy từ kiểu bên ngoài

Spring Cloud Function hỗ trợ composition bằng `spring.cloud.function.definition`:

~~~properties
spring.cloud.function.definition=normalize|validate
~~~

Ghép hai `Function` tương thích có thể tạo một function nhìn từ bên ngoài; ghép `Supplier` với `Function` vẫn là nguồn không cần input, và ghép `Function` với `Consumer` cho kết quả kiểu consumer không trả payload.

Tuy nhiên:

- **Không thể ghép tuần tự tùy ý** một `Consumer` trả `void` rồi mong có payload cho `Function` kế tiếp.
- Composition `a|b` là **dữ liệu đi từ a sang b**, không tự tạo thêm input/output binding như một fan-out.
- Với một pipeline reactive, cần kiểm tra tính tương thích kiểu và cách adapter subscribe; kết hợp reactive với imperative consumer có thể vướng giới hạn về subscription.
- Tên binding của composition cần được xác định theo **hàm tổng hợp được adapter bind**, không suy từ tên từng bean độc lập.

### 8.1. Routing theo từng message và routing theo cả luồng

Trong Spring Cloud Function, routing có thể dựa trên headers, cấu hình hoặc callback. Một **imperative function** có thể chọn route cho **từng message** nhờ metadata của message. Nhưng đối với reactive function, đơn vị xử lý là **cả stream**, nên chỉ dẫn routing cho từng message qua header không được áp dụng theo cùng cơ chế; tài liệu hướng dẫn dùng **cấu hình cấp ứng dụng** khi routing reactive stream.

~~~text
Imperative:
Message A + header route=alpha ──> alpha
Message B + header route=beta  ──> beta

Reactive:
Flux các message ──> một pipeline đã được chọn theo cấu hình
~~~

Nếu yêu cầu là phân loại từng message đến nhiều topic trên pipeline reactive, hãy xây dựng nhánh dữ liệu có chủ đích (chẳng hạn `Tuple2<Flux<A>, Flux<B>>`) hoặc cơ chế dynamic destination do Spring Cloud Stream hỗ trợ; không trông đợi header routing của imperative tự xử lý mọi phần tử trong `Flux`.

## 9. Bảng quyết định: chọn chữ ký dựa trên môi trường đích

| Nhu cầu | Chữ ký/kiến trúc nên cân nhắc | Cần kiểm tra thêm |
| --- | --- | --- |
| Một request nhận một giá trị trả về | `Function<I, O>` | HTTP serialization, timeout, validation |
| Đọc dữ liệu không cần input | `Supplier<O>` | GET trên web hoặc poller/trigger trên messaging |
| Xử lý sự kiện chỉ có tác dụng phụ | `Consumer<I>` | Ack, retry, idempotency, khả năng khôi phục |
| Một topic nhận, một topic phát | `Function<I, O>` hoặc `Function<Flux<I>, Flux<O>>` | Binder, retry và backpressure |
| Hai topic đầu vào cần đồng bộ | `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` | Reactive multi-binding, join/window, state, late events |
| Một topic cần hai topic đầu ra | `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` | Cả hai output được subscribe, destination và thứ tự tuple |
| Một HTTP endpoint trả danh sách | `Function<I, List<O>>` hoặc response stream phù hợp | Một response, content negotiation, giới hạn payload |
| Một invocation AWS/GCP/Azure xử lý một event | `Function<Event, Result>` hoặc `Consumer<Event>` | Loại trigger, kiểu event, timeout, quy tắc trả kết quả |
| Cần nhiều cổng phản hồi trên HTTP/serverless | Tích hợp/custom adapter hoặc thiết kế lại hợp đồng | Không suy ra nhiều cổng từ `TupleN` một cách tự động |

### 9.1. Checklist kiểm tra trước khi chuyển adapter

Trước khi mang một function từ môi trường này sang môi trường khác:

1. **Xác định hợp đồng:** tên bean, generic `I/O`, số cổng, giá trị hay publisher.
2. **Kiểm tra kích hoạt:** request, poller, event trigger hoặc subscription nào khiến hàm chạy?
3. **Kiểm tra quy tắc output:** response, message, collection, stream hay nhiều binding?
4. **Xác nhận chuyển đổi:** payload, header, `content-type` và kiểu Java có tương thích không?
5. **Đối chiếu vòng đời:** hàm được gọi mỗi message hay một lần để thiết lập `Flux`?
6. **Đối chiếu lỗi:** exception, retry, DLQ, cancellation, timeout và idempotency.
7. **Kiểm chứng trên đúng adapter/binder:** unit test của logic chưa đủ để kết luận kết nối ngoài hệ thống thành công.

## 10. Kiểm thử tính di động và hành vi theo adapter

### 10.1. Unit test độc lập với giao thức

Ví dụ kiểm thử trực tiếp bean `classifyOrder` mà không khởi động HTTP server hoặc broker:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ClassificationFunctionsTest {

    @Test
    void assignsPriorityWithoutDependingOnTransport() {
        var function = new ClassificationFunctions().classifyOrder();

        var result = function.apply(
                new ClassificationFunctions.Order("O-101", 1_000_000L));

        assertEquals(
                new ClassificationFunctions.Decision("O-101", "PRIORITY"),
                result);
    }
}
~~~

Kiểm thử này chứng minh quy tắc nghiệp vụ đúng ở mức Java. Nó **chưa xác nhận** JSON của HTTP, binding topic, Lambda event contract hay retry.

### 10.2. Unit test cho hàm hai đầu ra

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PaymentRoutingFunctionsTest {

    @Test
    void separatesLargePaymentsFromRegularPayments() {
        var large = new PaymentRoutingFunctions.Payment(
                "P-101", 1_500_000L);
        var regular = new PaymentRoutingFunctions.Payment(
                "P-102", 250_000L);

        var outputs = new PaymentRoutingFunctions()
                .splitPayments()
                .apply(Flux.just(large, regular));

        // Đăng ký cả hai publisher để đạt autoConnect(2).
        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(both -> {
                    assertEquals(List.of(large), both.getT1());
                    assertEquals(List.of(regular), both.getT2());
                })
                .verifyComplete();
    }
}
~~~

Ở đây `Mono.zip` giúp **cả hai nhánh được subscribe**, từ đó phù hợp với `autoConnect(2)` của hàm. `collectList()` chỉ dành cho nguồn kiểm thử **hữu hạn**. Để chứng minh hai destination hoạt động đúng, vẫn cần kiểm thử tích hợp với **Spring Cloud Stream Test Binder** hoặc broker/binder thật.

### 10.3. Bộ kiểm tra tích hợp tối thiểu cho từng adapter

| Môi trường | Kiểm tra tối thiểu |
| --- | --- |
| HTTP | Gửi request thật; kiểm tra status, content type, cấu trúc response, trường hợp lỗi |
| Spring Cloud Stream | Gửi message vào từng binding; đọc từng output binding; xác nhận payload, headers, thứ tự cổng |
| AWS Lambda | Gọi handler/invocation với event mẫu đúng trigger; xác nhận serialization và kết quả |
| Azure/GCP | Chạy qua entry point/trigger chính thức, payload thực tế và cơ chế trả kết quả |

Đặc biệt với reactive multi-output, nên thử cả trường hợp một nhánh không được tiêu thụ, một destination bị lỗi hoặc tốc độ hai output chênh lệch. Khả năng backpressure và retry không thể được chứng minh chỉ qua unit test `Flux.just(...)`.

## 11. Những nhận định sai thường gặp

| Nhận định | Thực tế |
| --- | --- |
| “Là Java `Function` thì mọi adapter đều hỗ trợ y hệt nhau.” | Adapter có hợp đồng event/request, kiểu dữ liệu và vòng đời riêng |
| “`Tuple2<OutputA, OutputB>` tạo hai output binding.” | Không; nhiều cổng của Spring Cloud Function dùng cơ chế reactive arity với tuple các `Flux` |
| “`Flux` nghĩa là broker chắc chắn có backpressure.” | Phải có binder và các thành phần bên dưới hỗ trợ tương ứng |
| “HTTP có thể có hai response vì hàm trả `Tuple2`.” | HTTP thường chỉ có một kênh response; cần định nghĩa payload/stream tương ứng |
| “`BiFunction<A, B, R>` luôn nhận được hai topic.” | Trường hợp đặc biệt được Spring Cloud Function nhận diện là payload và `Map` headers của một message |
| “Retry của imperative function cũng tự xử lý từng phần tử reactive.” | Reactive pipeline phải tự xác định chính sách lỗi phù hợp |
| “`Consumer<Flux<T>>` không cần subscribe vì là Consumer.” | Chữ ký `void` không cung cấp publisher kết quả để framework subscribe |
| “Một Lambda invocation sẽ tự gắn hai đầu vào `Tuple2` với hai trigger.” | Cần thiết kế event source và lớp tích hợp theo khả năng nền tảng |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một hàm trả `Tuple2<Flux<Accepted>, Flux<Rejected>>` được Spring Cloud Stream bind thành hai output. Nếu chuyển nguyên bean sang HTTP web adapter, nó có tự tạo hai endpoint `/accepted` và `/rejected` không?

**Đáp án:** **Không.** Hai output binding là khái niệm của messaging adapter. Muốn xuất hai API HTTP, phải thiết kế cách định tuyến/response phù hợp bằng web layer.

**Câu 2.** `BiFunction<Order, Map, Decision>` có phải là hai input binding do có hai tham số?

**Đáp án:** **Không.** Với chữ ký đặc biệt được nhận diện, tham số thứ hai là **headers của cùng một message**.

**Câu 3.** Tại sao `Function<Flux<I>, Flux<O>>` có thể cần chiến lược retry khác `Function<I, O>` trong Spring Cloud Stream?

**Đáp án:** Hàm reactive được gọi để thiết lập pipeline; framework không gọi lại `apply` cho từng message để bao bọc bằng retry/error handler theo từng invocation như imperative.

**Câu 4.** Nếu một ứng dụng dùng regular Kafka binder nhưng function trả `Flux<O>`, có thể khẳng định có backpressure toàn tuyến từ consumer đến Kafka broker không?

**Đáp án:** **Không.** API Reactor không tự tạo khả năng reactive ở broker/binder; cần xem mức hỗ trợ thực tế của hệ thống kết nối.

**Câu 5.** Một nghiệp vụ phân loại đơn hàng cần vừa được gọi từ HTTP vừa phát sự kiện sang hai topic. Thiết kế nào dễ tái sử dụng?

**Đáp án:** Đặt **quy tắc phân loại thuần** trong `Function<Order, Decision>` (hoặc một service không phụ thuộc transport). Web adapter gọi logic đó và trả một response. Ứng dụng messaging sử dụng cùng quy tắc trong một reactive function phân nhánh `Tuple2<Flux<...>, Flux<...>>`; chỉ messaging adapter tạo hai output binding.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model, FunctionCatalog, Function Arity, routing và type conversion](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Reactive Functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Function — Microsoft Azure Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html)
- [Spring Cloud Function — Google Cloud Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/gcp-intro.html)
