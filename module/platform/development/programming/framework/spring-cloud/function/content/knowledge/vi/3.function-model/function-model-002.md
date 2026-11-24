# Function<T, R>: biến đổi đầu vào thành kết quả

Trong **SPRING_CLOUD_FUNCTION**, **Function<T, R>** là mô hình cốt lõi để biểu diễn một thao tác nhận dữ liệu kiểu **T** và tạo ra kết quả kiểu **R**. Spring Cloud Function cho phép đăng ký logic này dưới dạng Spring bean, tìm qua **FunctionCatalog**, ghép chuỗi với hàm khác và đưa vào những môi trường gọi khác nhau như HTTP, luồng sự kiện hoặc serverless. Nhờ vậy, phần biến đổi nghiệp vụ tập trung vào dữ liệu đầu vào và đầu ra, còn giao thức do adapter đảm nhiệm.

Bài học thuộc chương **Mô hình hàm**, tập trung vào hợp đồng **Function<T, R>**, cách triển khai có kiểu rõ ràng, chuyển đổi thông điệp, composition, cơ chế xử lý lỗi và kiểm thử độc lập với giao thức.

## 1. Hợp đồng Function<T, R> trong Java

**java.util.function.Function<T, R>** là functional interface với phương thức trừu tượng **R apply(T input)**:

~~~java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T input);
}
~~~

Trong đó:

- **T** là kiểu dữ liệu đầu vào; người gọi cung cấp một giá trị kiểu này cho **apply(...)**.
- **R** là kiểu kết quả; hàm có thể tạo một đối tượng cùng kiểu T hoặc một kiểu hoàn toàn khác.
- **apply(...)** là nơi thực thi logic. Ví dụ **Function<String, Integer>** có thể nhận chuỗi và trả về số ký tự.
- Một đối tượng **Function** có thể được gọi nhiều lần với các input khác nhau; cùng input có thể cho kết quả giống hoặc khác nhau tùy thiết kế.

Ví dụ Java thuần:

~~~java
import java.util.function.Function;

Function<String, String> normalizeCode =
    raw -> raw.trim().toUpperCase(java.util.Locale.ROOT);

String result = normalizeCode.apply("  sku-108  ");
// "SKU-108"
~~~

Hàm trên không phụ thuộc request HTTP, message broker hay serverless handler. Nó chỉ quan tâm đến giá trị đầu vào.

**Function không bắt buộc là hàm thuần.** Một Function có thể gọi repository, đọc thời gian hệ thống, ghi log hoặc cập nhật trạng thái. Tuy nhiên, khi cùng input tạo cùng output và không gây tác dụng phụ, nó sẽ dễ kiểm thử, ghép chuỗi và thử lại hơn. Cần phân biệt *chữ ký hàm* với *cam kết nghiệp vụ*.

### So sánh ba mô hình chức năng

| Giao diện | Chữ ký | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| **Supplier<R>** | () → R | Sinh dữ liệu không nhận input nghiệp vụ | Sinh heartbeat |
| **Function<T, R>** | T → R | Biến đổi input thành kết quả | Tính báo giá từ thông tin đơn |
| **Consumer<T>** | T → void | Xử lý input, không trả kết quả nghiệp vụ | Ghi audit event |

Khi endpoint cần **request body** hoặc khi sự kiện tới phải được biến đổi để xuất sự kiện khác, **Function<T, R>** thường là lựa chọn tự nhiên. Khi logic không có đầu vào nghiệp vụ, dùng **Supplier<R>**; khi không cần đầu ra, cân nhắc **Consumer<T>**.

## 2. Spring Cloud Function bổ sung điều gì?

Một bean Spring kiểu **Function** được Spring Cloud Function nhận diện và đưa vào **FunctionCatalog**. Catalog giúp các adapter chọn hàm theo tên thay vì phải biết lớp Java đang chứa logic.

~~~mermaid
flowchart LR
    A["HTTP POST + JSON"] --> D["Adapter"]
    B["Sự kiện từ broker"] --> D
    C["Serverless invocation"] --> D
    D --> E["FunctionCatalog"]
    E --> F["Function<T, R>.apply(input)"]
    F --> G["Kết quả R"]
    G --> H["Adapter: HTTP response / output event / handler result"]
~~~

Các bước chính:

1. Ứng dụng đăng ký bean **Function<T, R>**, ví dụ **calculateQuote**.
2. Adapter nhận dữ liệu từ request, message hoặc runtime.
3. Adapter và cơ chế chuyển đổi của Spring Cloud Function xây dựng input tương thích với **T**.
4. **FunctionCatalog** cung cấp hàm có tên phù hợp; logic nghiệp vụ chạy qua **apply(input)**.
5. Kết quả **R** được adapter chuyển thành phản hồi hoặc dữ liệu đầu ra theo môi trường tích hợp.

Việc có một bean Function **không tự động mở cả ba kiểu triển khai**. Mỗi môi trường cần dependency, cấu hình, binder hoặc adapter thích hợp. Khả năng chuyển đổi dữ liệu cũng phụ thuộc kiểu Java, thư viện serialize và metadata của nội dung.

## 3. Ví dụ thực tế: tính thành tiền cho đơn hàng

Một dịch vụ bán hàng nhận mã đơn, số lượng và đơn giá **đã được xác thực ở hệ thống nguồn**, sau đó trả về tổng tiền. Đây là một bài toán biến đổi dữ liệu có đầu vào và đầu ra rõ ràng:

**OrderInput → Function<OrderInput, OrderQuote> → OrderQuote**

Ví dụ dưới đây dùng Java 17+, Spring Boot và Spring Cloud Function với các phiên bản tương thích. Với Maven, dependency cho adapter web là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Phiên bản Spring Cloud nên được quản lý qua BOM phù hợp với Spring Boot của dự án; không tự suy ra rằng bất kỳ cặp phiên bản nào cũng dùng được với nhau.

Khai báo một ứng dụng với bean **calculateQuote**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }

    @Bean
    Function<OrderInput, OrderQuote> calculateQuote() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || input.orderId().isBlank()
                    || input.quantity() <= 0
                    || input.unitPrice() == null
                    || input.unitPrice().signum() < 0) {
                throw new IllegalArgumentException("Invalid order input");
            }

            BigDecimal subtotal = input.unitPrice()
                .multiply(BigDecimal.valueOf(input.quantity()));

            return new OrderQuote(input.orderId(), subtotal);
        };
    }

    public record OrderInput(
        String orderId,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record OrderQuote(
        String orderId,
        BigDecimal subtotal
    ) {}
}
~~~

Giải thích các quyết định thiết kế:

- **OrderInput** là hợp đồng đầu vào và **OrderQuote** là hợp đồng kết quả. Dùng hai kiểu riêng giúp làm rõ sự thay đổi cấu trúc dữ liệu.
- Bean **calculateQuote** mang tên hàm. Spring Cloud Function có thể tra cứu bean đó bằng tên này.
- **BigDecimal** phù hợp hơn kiểu số thực **double** cho bài toán tính tiền, vì tránh một số sai lệch biểu diễn nhị phân. Tuy nhiên, sản phẩm thực vẫn cần quy tắc làm tròn và đơn vị tiền tệ rõ ràng.
- Kiểm tra input ngay trước khi tính tránh trường hợp số lượng âm, đơn giá âm và giá trị thiếu.
- **apply(input)** tạo một **OrderQuote** mới, không thay đổi bản ghi đầu vào.

Ví dụ lấy đơn giá từ input nhằm làm rõ mô hình **Function**. Với API công khai, không nên tin đơn giá do khách hàng gửi: dịch vụ cần kiểm tra giá từ nguồn dữ liệu có thẩm quyền hoặc dùng service giá đáng tin cậy trước khi chốt báo giá.

### Gọi hàm qua HTTP

Khi ứng dụng có adapter web, giả sử chạy trên cổng mặc định **8080**, gửi JSON vào endpoint của hàm:

~~~bash
curl -i -X POST http://localhost:8080/calculateQuote \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-1001","quantity":3,"unitPrice":120000}'
~~~

Phần thân phản hồi JSON minh họa:

~~~json
{
  "orderId": "ORD-1001",
  "subtotal": 360000
}
~~~

Trong đường xử lý này, adapter HTTP nhận JSON và ánh xạ sang **OrderInput**, sau đó gọi **calculateQuote.apply(...)**; kết quả **OrderQuote** được serialize thành JSON. Với lớp **Function** thuần, chính adapter quyết định đường dẫn HTTP, định dạng request/response và mã trạng thái. Không nên viết logic đọc **HttpServletRequest** hoặc tự tạo HTTP response bên trong Function nếu mục tiêu là tái sử dụng ở môi trường khác.

## 4. T và R xác định ranh giới dữ liệu

**Kiểu đầu vào và đầu ra là một phần hợp đồng**, không phải chi tiết phụ. Chúng ảnh hưởng đến khả năng deserialize JSON, conversion của message và composition.

Một số dạng thông dụng:

~~~java
Function<String, String> uppercase =
    text -> text.toUpperCase(java.util.Locale.ROOT);

Function<String, Integer> length =
    text -> text.length();

Function<OrderInput, OrderQuote> quote =
    input -> new OrderQuote(
        input.orderId(),
        input.unitPrice().multiply(BigDecimal.valueOf(input.quantity()))
    );
~~~

Các hàm trên chỉ minh họa kiểu; **quote** trong ví dụ rút gọn không có validation như bean **calculateQuote** ở phần trước.

Khi cần nhiều trường đầu vào, hãy gói chúng vào một **record** hoặc DTO thay vì đổi thành **BiFunction<A, B, R>** và kỳ vọng mọi adapter sẽ coi đó là một Function một đầu vào. Hợp đồng của Spring Cloud Function cho luồng xử lý cơ bản là **một đầu vào T và một đầu ra R**; một DTO có thể chứa bao nhiêu trường nghiệp vụ cần thiết.

### Chuyển đổi kiểu tại biên hệ thống

Ví dụ dòng xử lý khi nhận JSON:

~~~text
HTTP JSON bytes
   -> adapter / message conversion
   -> OrderInput
   -> calculateQuote.apply(input)
   -> OrderQuote
   -> JSON HTTP response
~~~

Những rủi ro thường thấy gồm tên trường không khớp DTO, thiếu trường bắt buộc, số tiền không hợp lệ, hoặc content type sai. Cần xác định rõ hợp đồng schema và kiểm thử với payload thực tế. Không nên giả định converter luôn tự giải quyết mọi kiểu Java tùy ý.

**Validation và chuyển đổi là hai trách nhiệm khác nhau:** converter có thể tạo đối tượng Java, nhưng không có nghĩa đối tượng đã hợp lệ theo quy tắc nghiệp vụ. Trong ví dụ này, kiểm tra số lượng và đơn giá nằm trong hàm; ứng dụng HTTP thực tế có thể bổ sung Bean Validation tại ranh giới API.

## 5. FunctionCatalog: định danh và chọn hàm

Thay vì gọi trực tiếp bean theo tên lớp, có thể tra cứu từ **FunctionCatalog**:

~~~java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

public class QuoteInvoker {
    private final FunctionCatalog catalog;

    public QuoteInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public QuoteApplication.OrderQuote run(
            QuoteApplication.OrderInput input) {

        Function<QuoteApplication.OrderInput, QuoteApplication.OrderQuote> fn =
            catalog.lookup("calculateQuote");

        if (fn == null) {
            throw new IllegalStateException("Function not found");
        }

        return fn.apply(input);
    }
}
~~~

Đây là ví dụ của một lớp được tạo/đăng ký trong Spring application context để nhận **FunctionCatalog** qua dependency injection. Catalog có thể cung cấp lớp wrapper phục vụ type conversion và composition, vì vậy không nên phụ thuộc vào kiểu lớp cụ thể của đối tượng trả về.

Nếu ứng dụng có nhiều bean **Function**, **Supplier** và **Consumer**, nên khai báo rõ tên hàm mà adapter cần sử dụng:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
~~~

**spring.cloud.function.definition** dùng để chọn một hàm hoặc một chuỗi hàm theo tên. Nên kiểm tra tên bean thực tế: viết sai **calculateQuote**, đổi tên bean mà quên sửa definition, hoặc chọn một hàm khác có thể khiến endpoint hay binding không hoạt động như dự định.

## 6. Composition: nối các bước biến đổi

Năng lực quan trọng của Spring Cloud Function là **ghép các hàm**. Giả sử sau khi tính báo giá, ta muốn định dạng kết quả thành một chuỗi đơn giản cho một hệ thống bên ngoài.

Thêm bean sau vào **QuoteApplication**:

~~~java
@Bean
Function<OrderQuote, String> formatQuote() {
    return quote -> "order=" + quote.orderId()
        + "; subtotal=" + quote.subtotal().toPlainString();
}
~~~

Lúc này:

~~~mermaid
flowchart LR
    A["OrderInput"] --> B["calculateQuote"]
    B --> C["OrderQuote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

Cấu hình composition:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote|formatQuote
~~~

Hệ thống trước tiên đưa **OrderInput** qua **calculateQuote**, sau đó đưa **OrderQuote** sang **formatQuote**. Kết quả cuối là **String**.

Có thể tra cứu chuỗi hàm theo định nghĩa từ catalog:

~~~java
Function<OrderInput, String> pipeline =
    catalog.lookup("calculateQuote|formatQuote");

String response = pipeline.apply(
    new OrderInput("ORD-1001", 3, new BigDecimal("120000"))
);
// "order=ORD-1001; subtotal=360000"
~~~

Đoạn mã minh họa ngữ cảnh có sẵn các kiểu **OrderInput**, **FunctionCatalog** và bean được đăng ký trong ứng dụng. Spring Cloud Function xử lý composition theo thứ tự từ trái sang phải; quy tắc quan trọng là **đầu ra của hàm đứng trước phải tương thích với đầu vào của hàm đứng sau**.

Ví dụ:

| Chuỗi | Tương thích? | Lý do |
| --- | --- | --- |
| **Function<OrderInput, OrderQuote> → Function<OrderQuote, String>** | Có | R của hàm đầu khớp T của hàm sau |
| **Function<OrderInput, OrderQuote> → Function<String, Integer>** | Không trực tiếp | OrderQuote không phải String |
| **Function<String, String> → Function<String, Integer>** | Có | Cùng dùng String tại ranh giới ghép |

Các adapter có thể hỗ trợ chuyển đổi kiểu tại ranh giới phù hợp, nhưng khi thiết kế nghiệp vụ nên khai báo kiểu tương thích rõ ràng thay vì trông chờ conversion ngầm để bù cho một pipeline thiếu chặt chẽ.

## 7. Kết hợp Function với Message<T>

Trong các hệ thống sự kiện, nội dung payload thường đi kèm header như loại sự kiện, mã tương quan (correlation ID) hoặc nguồn phát. Khi cần kiểm soát cả hai, có thể định nghĩa:

**Function<Message<OrderInput>, Message<OrderQuote>>**

Ví dụ bean bổ sung trong lớp cấu hình:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderInput>, Message<OrderQuote>> quoteMessage() {
    Function<OrderInput, OrderQuote> calculator = calculateQuote();

    return message -> {
        OrderQuote result = calculator.apply(message.getPayload());

        return MessageBuilder.withPayload(result)
            .copyHeaders(message.getHeaders())
            .setHeader("processedBy", "calculateQuote")
            .build();
    };
}
~~~

Ở đây:

- **message.getPayload()** trích dữ liệu nghiệp vụ đầu vào.
- **calculateQuote()** thực hiện phép biến đổi chính mà không cần biết về broker.
- **copyHeaders(...)** giữ lại các header có thể sao chép; **processedBy** bổ sung metadata ở đầu ra.
- Phần tích hợp quyết định header nào được bảo toàn, bỏ qua hoặc ánh xạ vào hệ thống truyền tải thực tế.

Trong một số cấu hình, Spring Cloud Function có thể cung cấp wrapper message/conversion xung quanh bean **Function<OrderInput, OrderQuote>**. Chỉ chuyển chữ ký sang **Message<T>** khi logic thật sự cần truy cập hoặc thay đổi metadata. Tránh làm cho mọi quy tắc nghiệp vụ phụ thuộc vào header kỹ thuật khi điều đó không cần thiết.

## 8. Dùng Function để xử lý sự kiện đến và phát sự kiện đi

Với Spring Cloud Stream và binder thích hợp, một Function có thể xử lý từng message đi vào rồi tạo message đầu ra:

~~~text
Topic / Queue đầu vào
    -> calculateQuote.apply(OrderInput)
    -> Topic / Queue đầu ra chứa OrderQuote
~~~

Ví dụ cấu hình trong một ứng dụng có binder tương ứng:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
    stream:
      bindings:
        calculateQuote-in-0:
          destination: order-inputs
        calculateQuote-out-0:
          destination: order-quotes
~~~

**calculateQuote-in-0** là binding đầu vào, **calculateQuote-out-0** là binding đầu ra của hàm. **destination** chỉ tên đích logic và cần được broker/binder xử lý. Cấu hình này không đủ để chạy nếu thiếu Spring Cloud Stream, binder cụ thể, broker và kết nối hợp lệ.

So với HTTP, bản thân Function không thay đổi: nó vẫn nhận **OrderInput** và trả về **OrderQuote**. Khác biệt nằm ở nguồn dữ liệu đầu vào, serialization, retry, cơ chế gửi message và cách báo lỗi.

Cần thiết kế thêm cho môi trường sự kiện:

- **Idempotency:** cùng một message có thể được xử lý lại khi hệ thống retry; Function có tác dụng phụ cần chịu được xử lý trùng.
- **Định dạng và phiên bản schema:** thay đổi tên hoặc kiểu field có thể làm consumer cũ không đọc được.
- **Xử lý lỗi:** một exception có thể dẫn đến retry, error channel hoặc dead-letter tùy binder và cấu hình; không có một hành vi cố định cho mọi broker.
- **Thông lượng và thứ tự:** số consumer, concurrency, partition và cấu hình binder có thể làm thay đổi thứ tự xử lý hoặc tốc độ phát kết quả.

## 9. Triển khai dưới dạng hàm serverless

Trong môi trường serverless, adapter nhận payload của runtime, chuyển thành input, gọi **Function<T, R>**, sau đó chuyển kết quả về định dạng mà nền tảng yêu cầu.

Ví dụ cùng bean **calculateQuote** có thể được đóng gói cho một runtime hỗ trợ Spring Cloud Function adapter. Logic tính tổng không cần chứa API đặc thù của AWS Lambda hay nền tảng khác. Tuy nhiên, deployment vẫn cần handler/adaptor, dependency, packaging, cấu hình thời gian chạy và quyền truy cập dịch vụ theo hướng dẫn của nền tảng đó.

Một khác biệt thực tế so với ứng dụng HTTP chạy liên tục là **vòng đời khởi tạo**. Runtime có thể tái sử dụng hoặc tạo lại instance theo nhu cầu. Vì thế không nên dựa vào biến mutable trong bean để lưu một trạng thái nghiệp vụ duy nhất, lâu dài giữa các lần gọi.

## 10. Function đồng bộ và Function phản ứng

Chữ ký **Function<T, R>** cũng có thể kết hợp với kiểu reactive như **Flux** của Project Reactor:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

@Bean
Function<Flux<OrderInput>, Flux<OrderQuote>> calculateQuoteStream() {
    Function<OrderInput, OrderQuote> calculator = calculateQuote();
    return inputs -> inputs.map(calculator);
}
~~~

Trong ví dụ này, **apply(...)** nhận một **Flux<OrderInput>**, trả về **Flux<OrderQuote>**. Các phần tử được chuyển đổi khi publisher được subscribe và có tín hiệu phát dữ liệu, theo ngữ nghĩa Reactor.

| Đặc điểm | Function<OrderInput, OrderQuote> | Function<Flux<OrderInput>, Flux<OrderQuote>> |
| --- | --- | --- |
| Đầu vào của **apply** | Một OrderInput | Một publisher chứa nhiều OrderInput |
| Đầu ra | Một OrderQuote | Một publisher chứa nhiều OrderQuote |
| Xử lý | Thường một lần biến đổi cho mỗi lời gọi | Chuỗi biến đổi trên một luồng dữ liệu |
| Điểm cần chú ý | Exception, latency, tài nguyên dùng chung | Subscription, backpressure, xử lý lỗi trong stream |

**Không mặc định** rằng tất cả adapter HTTP đều nhận hoặc xuất luồng reactive vô hạn theo cách giống binder stream. Ngữ nghĩa kích hoạt, đóng luồng và chuyển đổi payload phụ thuộc phiên bản framework và adapter. Chỉ chọn reactive khi có yêu cầu rõ về luồng dữ liệu, I/O bất đồng bộ hoặc thông lượng và có kế hoạch kiểm thử lifecycle của publisher.

## 11. Lỗi, validation và tác dụng phụ

Trong Java, **apply(...)** có thể ném **RuntimeException** khi input sai hoặc tài nguyên phụ trợ lỗi. Việc ném **IllegalArgumentException** trong ví dụ báo giá là cách đánh dấu dữ liệu không hợp lệ *trong logic hàm*. Tuy nhiên, nó **không tự đảm bảo HTTP 400** hoặc chính sách retry phù hợp: adapter và tầng ứng dụng quyết định chuyển exception sang HTTP response, error message hay retry.

Với bài toán nghiệp vụ thực tế, cân nhắc ba loại lỗi:

1. **Sai hợp đồng đầu vào:** trường thiếu, kiểu sai, giá trị âm. Nên kiểm tra sớm và cung cấp thông tin lỗi có cấu trúc tại ranh giới của kênh gọi.
2. **Quy tắc nghiệp vụ không thỏa:** tồn kho thiếu, đơn hàng bị khóa. Có thể dùng một kiểu kết quả biểu đạt thành công/thất bại thay vì exception chung, tùy convention của hệ thống.
3. **Lỗi hạ tầng tạm thời:** database không sẵn sàng, broker mất kết nối. Thiết kế timeout, retry và idempotency tại tầng phù hợp; tránh đặt vòng retry vô hạn bên trong Function.

Một Function **ghi dữ liệu** hoặc **gọi dịch vụ bên ngoài** hoàn toàn hợp lệ về mặt interface. Nhưng cần hiểu rằng việc ghép chuỗi, retry hoặc gọi lại cùng input có thể lặp lại tác dụng phụ. Với các bước biến đổi thuần, việc chia nhỏ thành nhiều Function thường an toàn và dễ quan sát hơn.

### Những lỗi triển khai thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Endpoint hoặc binding không thấy hàm | Sai tên bean/definition hoặc thiếu adapter | Kiểm tra tên **calculateQuote**, dependency, cấu hình definition |
| JSON không chuyển thành OrderInput | Sai content type, trường/kiểu dữ liệu không khớp | Kiểm tra DTO, payload, converter và log ở biên |
| Composition thất bại | Kiểu R của bước trước không phù hợp với T của bước sau | Thiết kế type contract và kiểm thử từng bước |
| Kết quả sai khi gửi request đồng thời | Bean Function sử dụng trạng thái mutable dùng chung | Ưu tiên dữ liệu bất biến; quản lý concurrency khi có shared state |
| Xử lý sự kiện lặp lại làm ghi trùng | Retry/redelivery và tác dụng phụ không idempotent | Dùng event ID, khóa duy nhất hoặc cơ chế idempotency |
| Request chậm hoặc timeout | Logic **apply** gọi I/O chặn lâu, thiếu timeout | Đo thời gian xử lý, đặt timeout và cân nhắc kiến trúc bất đồng bộ |
| Lỗi nghiệp vụ trả status không mong muốn | Exception chưa được ánh xạ ở adapter | Định nghĩa error mapping cho kênh HTTP/stream/serverless |

## 12. Kiểm thử phần biến đổi mà không khởi động adapter

Vì Function có hợp đồng Java đơn giản, có thể kiểm thử trực tiếp qua **apply(input)**. Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class QuoteApplicationTest {

    private final Function<QuoteApplication.OrderInput,
            QuoteApplication.OrderQuote> calculator =
                new QuoteApplication().calculateQuote();

    @Test
    void calculatesSubtotal() {
        var input = new QuoteApplication.OrderInput(
            "ORD-1001", 3, new BigDecimal("120000")
        );

        var quote = calculator.apply(input);

        assertEquals("ORD-1001", quote.orderId());
        assertEquals(0,
            new BigDecimal("360000").compareTo(quote.subtotal()));
    }

    @Test
    void rejectsInvalidQuantity() {
        var input = new QuoteApplication.OrderInput(
            "ORD-1001", 0, new BigDecimal("120000")
        );

        assertThrows(IllegalArgumentException.class,
            () -> calculator.apply(input));
    }
}
~~~

Bài kiểm thử đầu bảo đảm input đúng được biến đổi thành subtotal dự kiến; bài thứ hai bảo đảm quantity bằng 0 bị từ chối. Có thể bổ sung trường hợp đơn giá âm, đơn giá thiếu, mã đơn trống và giới hạn dữ liệu lớn.

Sau unit test, bổ sung **integration test** cho những ranh giới thật sự sử dụng: JSON qua HTTP, header và serialization khi nhận/gửi message, hoặc handler trên runtime serverless. Unit test của Function không thay thế việc xác minh mapping của adapter.

## 13. Thực hành củng cố

**Bài tập 1 — Biến đổi rõ kiểu.** Tạo **Function<TemperatureInput, TemperatureOutput>**, nhận nhiệt độ Celsius và trả Fahrenheit. Dùng DTO/record cho cả hai kiểu và kiểm thử trường hợp **0 °C → 32 °F**.

**Bài tập 2 — Ghép chuỗi.** Viết thêm **Function<TemperatureOutput, String>** để định dạng kết quả và khai báo composition bằng **spring.cloud.function.definition**. Giải thích tại sao không thể nối trực tiếp một Function đầu ra **OrderQuote** với Function nhận **TemperatureOutput**.

**Bài tập 3 — Thay adapter.** Giữ nguyên **Function<OrderInput, OrderQuote>** từ ví dụ. Xác định cấu hình, dependency và các kiểm thử cần có nếu thay HTTP POST bằng một message từ topic **order-inputs** rồi phát kết quả sang **order-quotes**.

**Bài tập 4 — Dữ liệu lỗi.** Giả sử input có quantity **-2**, đơn giá **null** hoặc mã đơn rỗng. Viết unit test tương ứng và mô tả cách mà tầng HTTP có thể ánh xạ lỗi validation thành một response dễ hiểu; chỉ rõ vì sao việc ném exception đơn lẻ chưa đảm bảo mã trạng thái HTTP cụ thể.

### Ghi nhớ

- **Function<T, R>** có chữ ký **T → R**, với thao tác chính **R apply(T)**; dùng khi logic phải nhận dữ liệu và trả về một kết quả.
- Spring Cloud Function đăng ký các bean chức năng trong **FunctionCatalog**, cho phép adapter tra cứu và gọi logic mà không đưa chi tiết HTTP, broker hay serverless vào phần xử lý.
- **Composition** yêu cầu các kiểu đầu vào/đầu ra tương thích; **Message<T>** hữu ích khi cần đọc hoặc tạo header ngoài payload.
- Chuyển đổi dữ liệu, xử lý lỗi, retry, serialization và runtime vẫn phụ thuộc adapter. Unit test **apply(...)** kiểm tra nghiệp vụ; integration test xác minh biên giao thức.
