# Ghép Supplier với Function

## 1. Mục tiêu bài học

Spring Cloud Function giúp phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function` và `Consumer`, độc lập với giao thức gọi. Cùng logic có thể chạy trong Java nội bộ hoặc được kết nối với HTTP, sự kiện, serverless qua adapter phù hợp. Trong chương **Ghép hàm**, một trường hợp quan trọng là kết nối **nguồn dữ liệu** với **bước biến đổi dữ liệu**.

Bài này tập trung vào phép ghép:

~~~text
Supplier<A> --get()--> A --Function<A, B>.apply(...)--> B

Kết quả về mặt hành vi: Supplier<B>
~~~

Sau bài học, bạn có thể:

- Phân biệt `Supplier.get()` với `Function.apply(...)`.
- Giải thích vì sao ghép `Supplier<A>` và `Function<A, B>` tạo ra `Supplier<B>`.
- Viết phép ghép trong Java thuần và tra cứu composition theo tên bằng `FunctionCatalog.lookup(...)`.
- Chỉ định pipeline với `spring.cloud.function.definition` và hiểu vai trò của adapter.
- Nhận diện lỗi về thứ tự, kiểu dữ liệu, số lần thực thi, ngoại lệ và luồng reactive.
- Kiểm thử thứ tự gọi cũng như kết quả của pipeline nhiều bước.

## 2. Supplier tạo dữ liệu, Function biến đổi dữ liệu

`Supplier<T>` là một giao diện của Java với phương thức `T get()`. Nó không có tham số đầu vào.

~~~java
import java.util.function.Supplier;

Supplier<String> greetingSource = () -> "Xin chao";
String greeting = greetingSource.get();

System.out.println(greeting); // Xin chao
~~~

`Function<T, R>` nhận `T` và trả `R` bằng phương thức `R apply(T input)`.

~~~java
import java.util.function.Function;

Function<String, Integer> countChars = String::length;
System.out.println(countChars.apply("Xin chao")); // 8
~~~

Với một nguồn `Supplier<String>` và một bước `Function<String, Integer>`, ta có thể nối chúng:

~~~text
                        get()                 apply(...)
Supplier<String> ----------------> String ----------------> Integer
                                   Function<String,Integer>
~~~

Người gọi cuối cùng chỉ cần kích hoạt nguồn đã ghép. Vì người gọi **không truyền đầu vào**, kết quả phù hợp với giao diện `Supplier<Integer>`.

### 2.1. Công thức tổng quát

Cho:

~~~text
source: Supplier<A>
transform: Function<A, B>
~~~

Phép ghép có thể mô tả bằng:

~~~text
combined: Supplier<B>

combined.get() = transform.apply(source.get())
~~~

Bảng sau tóm tắt hợp đồng:

| Thành phần | Đầu vào do người gọi truyền | Đầu ra | Cách gọi |
|---|---|---|---|
| `Supplier<A>` | Không có | `A` | `get()` |
| `Function<A, B>` | `A` | `B` | `apply(A)` |
| Hai thành phần đã ghép | Không có | `B` | `get()` |

**Điểm quan trọng:** một `Supplier` tiêu chuẩn của Java **không có** phương thức `andThen` hay `compose`. Các phương thức đó thuộc `Function`; Spring Cloud Function bổ sung cơ chế ghép các function bean theo tên.

## 3. Tự ghép trong Java thuần

Ví dụ: một nguồn trả số lượng cần tính tiền, một hàm tính giá từ số lượng.

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFunctionExample {

    public static void main(String[] args) {
        Supplier<Integer> quantitySource = () -> 4;
        Function<Integer, Long> calculateCost =
                quantity -> quantity * 75_000L;

        Supplier<Long> totalCostSource = () ->
                calculateCost.apply(quantitySource.get());

        System.out.println(totalCostSource.get()); // 300000
    }
}
~~~

Lần gọi `totalCostSource.get()` diễn ra theo thứ tự:

1. `quantitySource.get()` tạo ra `4`.
2. `calculateCost.apply(4)` trả về `300000L`.
3. `totalCostSource.get()` trả kết quả `Long` đó cho người gọi.

Dòng khai báo `totalCostSource` mới tạo lambda; **chưa chạy nguồn hoặc hàm biến đổi**. Các bước được thực thi khi có `get()`.

### 3.1. Viết tiện ích ghép có generic

Nếu dùng nhiều nơi, bạn có thể định nghĩa một phương thức Java thuần:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

public final class SupplierComposition {

    private SupplierComposition() {}

    public static <A, B> Supplier<B> combine(
            Supplier<? extends A> source,
            Function<? super A, ? extends B> transform) {

        return () -> transform.apply(source.get());
    }
}
~~~

Dùng hai `Function` nối sau Supplier:

~~~java
Supplier<String> textSource = () -> "  spring  ";

Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Supplier<Integer> result =
        SupplierComposition.combine(
                textSource,
                trim.andThen(length));

System.out.println(result.get()); // 6
~~~

`trim.andThen(length)` kết hợp **Function với Function**. Helper `combine` kết hợp **Supplier với Function đã ghép**. Kiểu tổng thể vẫn là `Supplier<Integer>`.

### 3.2. Vì sao không dùng source.andThen(transform)?

Đây là cách viết **không biên dịch**:

~~~java
Supplier<String> source = () -> "abc";
Function<String, Integer> length = String::length;

// Supplier<Integer> invalid = source.andThen(length);
~~~

`Supplier` không có `andThen` chuẩn của Java. Cách đúng trong Java thuần là:

~~~java
Supplier<Integer> valid = () -> length.apply(source.get());
~~~

Trong ứng dụng Spring Cloud Function, `FunctionCatalog` cho phép nối theo tên mà không cần tự viết lambda cho mỗi tổ hợp.

## 4. Ví dụ nghiệp vụ: nguồn đơn hàng và báo giá

Giả sử một dịch vụ cần lấy đơn hàng đang chờ, định giá, rồi chuẩn bị nội dung báo giá. Để minh họa chính xác phép ghép, ta cho Supplier trả về một đơn hàng cố định; việc kết nối database hoặc broker nằm ở tầng tích hợp sau này.

Luồng dữ liệu dự kiến:

~~~text
pendingOrder: Supplier<OrderDraft>
            |
            | get()
            v
OrderDraft("SKU-17", 2)
            |
            v
priceOrder: Function<OrderDraft, Quote>
            |
            | apply(order)
            v
Quote("SKU-17", 2, 250000)
            |
            v
formatQuote: Function<Quote, String>
            |
            | apply(quote)
            v
"SKU-17 x 2 = 250000 VND"
~~~

### 4.1. Định nghĩa function bean trong Spring

Dùng Java 17 trở lên với `record`:

~~~java
package example.functions;

import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuoteFunctions {

    public record OrderDraft(String sku, int quantity) {}

    public record Quote(
            String sku,
            int quantity,
            long totalVnd) {}

    @Bean
    public Supplier<OrderDraft> pendingOrder() {
        return () -> new OrderDraft("SKU-17", 2);
    }

    @Bean
    public Function<OrderDraft, Quote> priceOrder() {
        return order -> {
            if (order == null
                    || order.sku() == null
                    || !order.sku().matches("SKU-[0-9]+")
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Don hang khong hop le");
            }

            long unitPrice = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPrice);

            return new Quote(
                    order.sku(),
                    order.quantity(),
                    totalVnd);
        };
    }

    @Bean
    public Function<Quote, String> formatQuote() {
        return quote ->
                quote.sku() + " x " + quote.quantity()
                + " = " + quote.totalVnd() + " VND";
    }
}
~~~

Các tên bean mặc định là `pendingOrder`, `priceOrder` và `formatQuote`. Khi Spring Cloud Function được cấu hình và các bean được ứng dụng phát hiện, chúng có thể được đăng ký vào `FunctionCatalog`.

| Bean | Hợp đồng | Vai trò |
|---|---|---|
| `pendingOrder` | `Supplier<OrderDraft>` | Tạo dữ liệu đơn hàng |
| `priceOrder` | `Function<OrderDraft, Quote>` | Tính báo giá |
| `formatQuote` | `Function<Quote, String>` | Định dạng văn bản |

Giá `125_000L` và đơn hàng `SKU-17` là dữ liệu minh họa. Nguồn thật cần định nghĩa cách đọc dữ liệu mới, xử lý bản ghi chưa sẵn sàng và tránh phát trùng.

### 4.2. Lấy Supplier đã ghép bằng FunctionCatalog.lookup

`FunctionCatalog` hỗ trợ ghép hàm theo tên với dấu `|`. Các bước ở bên trái chạy trước bước ở bên phải theo hợp đồng dữ liệu.

~~~java
package example.functions;

import java.util.function.Supplier;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public String generateQuote() {
        Supplier<String> pipeline =
                catalog.lookup(
                        "pendingOrder|priceOrder|formatQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return pipeline.get();
    }
}
~~~

Tổ hợp `pendingOrder|priceOrder|formatQuote` có hợp đồng tổng thể:

~~~text
Supplier<OrderDraft>
    |
    v
Function<OrderDraft, Quote>
    |
    v
Function<Quote, String>
    |
    v
Supplier<String>
~~~

Dòng `pipeline.get()` sẽ kích hoạt Supplier, sau đó truyền dữ liệu qua từng Function. Kết quả từ ví dụ là:

~~~text
SKU-17 x 2 = 250000 VND
~~~

Không gọi `pipeline.apply(...)` vì pipeline bắt đầu từ `Supplier`, nên **không yêu cầu input từ người gọi**.

### 4.3. Ví dụ lớp khởi động Spring Boot

Đặt lớp ứng dụng trong package `example.functions` để quét được các lớp trên:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }
}
~~~

Cần có Spring Boot, Spring Cloud Function và cấu hình dependency phù hợp. Phép tra cứu trong Java nội bộ không yêu cầu phải tạo HTTP controller. Nếu tích hợp HTTP, broker hay serverless, cần adapter tương ứng.

## 5. Chọn pipeline bằng spring.cloud.function.definition

Có thể khai báo tên chuỗi hàm cho adapter/framework trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "pendingOrder|priceOrder|formatQuote"
~~~

Hoặc trong `application.properties`:

~~~properties
spring.cloud.function.definition=pendingOrder|priceOrder|formatQuote
~~~

Ý nghĩa các cấu hình là: chọn một **pipeline có nguồn** `pendingOrder`, rồi lần lượt đi qua `priceOrder` và `formatQuote`.

Hai cách sử dụng cần phân biệt:

| Nhu cầu | Cách làm |
|---|---|
| Code Java tự lấy pipeline để gọi | `catalog.lookup("pendingOrder|priceOrder|formatQuote")` |
| Adapter chọn pipeline được cấu hình | `spring.cloud.function.definition` |
| Gọi pipeline đã lấy trong Java | `pipeline.get()` |
| Kết nối để phát qua broker | Cài binder/adapter và cấu hình output phù hợp |

`spring.cloud.function.definition` **không tự tạo endpoint HTTP, kích hoạt polling hay kết nối broker**. Nó chọn tên/tổ hợp function; cách kích hoạt và gửi kết quả vẫn do môi trường tích hợp quyết định.

### 5.1. Chỉ ghép Supplier với một Function

Nếu cần một đối tượng `Quote` thay vì `String`:

~~~java
import java.util.function.Supplier;

Supplier<QuoteFunctions.Quote> quotes =
        catalog.lookup("pendingOrder|priceOrder");

if (quotes == null) {
    throw new IllegalStateException("Thieu supplier bao gia");
}

QuoteFunctions.Quote quote = quotes.get();
~~~

Tổ hợp `pendingOrder|priceOrder` là `Supplier<Quote>`, còn tổ hợp có thêm `formatQuote` là `Supplier<String>`. Chỉ cần thêm hoặc bớt một Function ở cuối cũng thay đổi hợp đồng đầu ra của pipeline.

## 6. Khi gọi get() nhiều lần, chuyện gì xảy ra?

Mỗi lời gọi `get()` kích hoạt logic của Supplier đã ghép trong cách triển khai đồng bộ thông thường. Để thấy rõ, xét ví dụ tạo mã đơn hàng tăng dần:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.function.Supplier;

AtomicLong sequence = new AtomicLong();

Supplier<Long> nextId = sequence::incrementAndGet;
Function<Long, String> label = id -> "ORDER-" + id;

Supplier<String> nextOrderCode =
        () -> label.apply(nextId.get());

System.out.println(nextOrderCode.get()); // ORDER-1
System.out.println(nextOrderCode.get()); // ORDER-2
System.out.println(nextOrderCode.get()); // ORDER-3
~~~

Một lần gọi `nextOrderCode.get()` gồm hai bước: tăng số thứ tự rồi định dạng. Hàm không tự lưu kết quả để trả lại ở lần sau.

Ngược lại, `pendingOrder` ở ví dụ trước trả về cùng dữ liệu `SKU-17` mỗi lần được gọi. Điều đó tiện cho bài học nhưng có thể gây **phát lặp đơn hàng** nếu gắn vào một adapter sự kiện được kích hoạt nhiều lần.

### 6.1. Ai quyết định khi nào gọi Supplier?

Điều này phụ thuộc môi trường:

- Java nội bộ: code gọi `get()` bao nhiêu lần thì pipeline chạy theo số lần đó.
- Spring Cloud Stream với Supplier imperative: cơ chế poller/trigger của binder thường quyết định lúc lấy dữ liệu; cần cấu hình theo phiên bản.
- Supplier reactive: có thể được subscribe và phát nhiều phần tử theo mô hình Publisher, khác cách poll Supplier thường.
- Serverless hoặc HTTP: hành vi kích hoạt tùy adapter và kiểu handler được cấu hình.

Dấu `|` chỉ nói lên **thứ tự nối dữ liệu**. Nó không tự thiết lập lịch chạy, retry, giao dịch hay cơ chế chống trùng.

## 7. Kiểu dữ liệu giữa các bước phải tương thích

Quy tắc:

~~~text
Supplier<A> | Function<A, B> | Function<B, C>
                                  ↓
                            Supplier<C>
~~~

Điều kiện để nối hai bước là giá trị đầu ra của bước trước phải dùng được làm đầu vào của bước sau. Ví dụ hợp lệ:

~~~java
Supplier<String> raw = () -> "  42  ";

Function<String, Integer> parse =
        text -> Integer.parseInt(text.trim());

Function<Integer, Long> price =
        amount -> amount * 1_000L;

Supplier<Long> total =
        () -> price.apply(parse.apply(raw.get()));

System.out.println(total.get()); // 42000
~~~

Nhưng trường hợp sau **không biên dịch trong Java thuần**:

~~~java
Supplier<String> raw = () -> "SKU-17";
Function<Integer, Long> price =
        amount -> amount * 1_000L;

// Sai: String không phải Integer.
// Supplier<Long> invalid = () -> price.apply(raw.get());
~~~

Khi ghép bằng tên `catalog.lookup("raw|price")`, trình biên dịch không thể kiểm tra các bước dựa trên chuỗi tên. Lỗi do bean không tồn tại hoặc không tương thích có thể xuất hiện khi tra cứu/thực thi ở runtime. Vì vậy, cần biết chữ ký thực của từng bean và viết integration test.

### 7.1. Khác tên kiểu chưa chắc không tương thích

Java cho phép chuyển giá trị kiểu con vào một hàm nhận kiểu cha:

~~~java
Supplier<Integer> numberSource = () -> 5;

Function<Number, String> describe =
        number -> "Gia tri: " + number;

Supplier<String> description =
        () -> describe.apply(numberSource.get());

System.out.println(description.get()); // Gia tri: 5
~~~

`Integer` là kiểu con của `Number`, nên các bước nối được. Nên giữ generic rõ ràng, không dùng raw type để che giấu lỗi.

### 7.2. Đúng kiểu nhưng sai ý nghĩa nghiệp vụ

Một nguồn có thể trả `String` là mã khách hàng, trong khi Function phía sau nhận `String` nhưng cho rằng nó là địa chỉ email. Pipeline vẫn có thể chạy nhưng xử lý sai loại dữ liệu.

Có thể dùng record làm kiểu nghiệp vụ tường minh:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

Khi đó `Supplier<CustomerId>` không thể được truyền trực tiếp vào `Function<EmailAddress, Boolean>` theo generic của Java, giúp phát hiện lỗi thiết kế sớm hơn.

## 8. Xử lý dữ liệu không có, null và ngoại lệ

### 8.1. Không tùy tiện dùng null để biểu diễn không có dữ liệu

~~~java
Supplier<String> maybeEmpty = () -> null;
Function<String, Integer> length = String::length;

// Khi gọi get(), đoạn này sẽ phát sinh NullPointerException.
Supplier<Integer> invalid =
        () -> length.apply(maybeEmpty.get());
~~~

Phép ghép không tự quyết định rằng `null` có nghĩa “bỏ qua bước”. Nếu nguồn đôi lúc không có bản ghi, nên thiết kế hợp đồng rõ ràng.

Trong Java thuần, `Optional` có thể giúp biểu diễn trường hợp thiếu giá trị:

~~~java
import java.util.Optional;
import java.util.function.Function;
import java.util.function.Supplier;

Supplier<Optional<String>> source = Optional::empty;

Function<Optional<String>, Optional<Integer>> measure =
        value -> value.map(String::length);

Supplier<Optional<Integer>> result =
        () -> measure.apply(source.get());

System.out.println(result.get()); // Optional.empty
~~~

Đây là `Supplier<Optional<Integer>>`, không phải `Supplier<Integer>`. Nếu dùng adapter thông điệp, `Optional.empty()` **không nhất thiết** tự được hiểu là “không phát message”; cần kiểm tra hợp đồng adapter.

### 8.2. Ngoại lệ từ Supplier dừng bước kế tiếp trong Java đồng bộ

~~~java
Supplier<String> brokenSource = () -> {
    throw new IllegalStateException("Nguon khong san sang");
};

Function<String, Integer> measure = String::length;

Supplier<Integer> pipeline =
        () -> measure.apply(brokenSource.get());

// pipeline.get() ném IllegalStateException;
// measure.apply(...) chưa chạy.
~~~

Nếu `Supplier.get()` thất bại, dữ liệu chưa đến Function. Nếu Function ném ngoại lệ, kết quả cuối của Supplier đã ghép cũng không được tạo ra bình thường.

Trong triển khai qua HTTP, sự kiện hoặc serverless, cách ghi nhận, trả lỗi và retry phụ thuộc adapter. **Ghép hàm tự nó không cung cấp retry, exactly-once hoặc idempotency.** Với dữ liệu thật, cần làm rõ khi nào nguồn xác nhận đã lấy bản ghi, khi nào bản ghi được phép thử lại và cách tránh gửi lặp.

### 8.3. Những câu hỏi thiết kế với nguồn có tác dụng phụ

Nếu Supplier đọc database hoặc API ngoài, cần xác định:

1. Một lần gọi `get()` có thể lấy bao nhiêu dữ liệu?
2. Nguồn có thể trả cùng bản ghi ở hai lần gọi liên tiếp không?
3. Nếu Function sau thất bại, dữ liệu đã bị đánh dấu là “đã xử lý” chưa?
4. Có thể có nhiều lời gọi `get()` đồng thời hay không?
5. Nên đặt timeout, giới hạn tốc độ, retry và idempotency ở đâu?

Ví dụ nguồn cố định trong bài dùng để học composition; để đưa vào production, cần thiết kế riêng vòng đời dữ liệu và cách xử lý lỗi.

## 9. Trường hợp Supplier reactive

Trong Spring Cloud Function có thể dùng Reactor để xử lý luồng dữ liệu. Khi đó, chữ ký tổng thể phải thể hiện **Publisher** chứ không chỉ phần tử.

Ví dụ Java:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

import reactor.core.publisher.Flux;

Supplier<Flux<String>> source = () ->
        Flux.just("  a  ", "  bb ");

Function<Flux<String>, Flux<Integer>> measure =
        input -> input
                .map(String::trim)
                .map(String::length);

Supplier<Flux<Integer>> transformed =
        () -> measure.apply(source.get());
~~~

Sơ đồ kiểu dữ liệu:

~~~text
Supplier<Flux<String>>
          |
          v
Function<Flux<String>, Flux<Integer>>
          |
          v
Supplier<Flux<Integer>>
~~~

Khi gọi `transformed.get()`, ta nhận được `Flux<Integer>`. Phần tử có thể chỉ được xử lý khi có subscriber:

~~~java
import java.util.List;

List<Integer> lengths =
        transformed.get().collectList().block();

System.out.println(lengths); // [1, 2]
~~~

`block()` chỉ dùng để minh họa trong chương trình/kiểm thử đồng bộ, không nên gọi tùy tiện trong pipeline reactive đang chạy.

### 9.1. Tránh nhầm kiểu phần tử và kiểu Publisher

Hai khai báo:

~~~text
Supplier<Flux<Order>>
Function<Order, Quote>
~~~

không tự nối theo generic Java như:

~~~text
Supplier<Flux<Order>>
Function<Flux<Order>, Flux<Quote>>
~~~

Spring Cloud Function và adapter có thể cung cấp khả năng thích ứng trong một số trường hợp, nhưng không nên giả định mọi tổ hợp reactive/imperative đều được chuyển đổi tự động. Hãy xem hợp đồng phiên bản đang dùng, làm rõ nơi xử lý từng phần tử và kiểm thử với Publisher thật.

### 9.2. Số lần gọi reactive Supplier có thể khác Supplier thường

Trong Spring Cloud Stream, Supplier imperative thường được poll theo cấu hình. Supplier reactive có thể được lấy Publisher và subscribe theo cách khác, tùy binder/phiên bản. Không nên suy luận rằng mỗi phần tử của Flux tương đương với một lời gọi `get()` mới.

Cần kiểm tra subscription, backpressure, thời điểm kết thúc luồng và cách xử lý lỗi trước khi đưa một nguồn reactive vào hệ thống sự kiện.

## 10. Triển khai pipeline qua HTTP, sự kiện hoặc serverless

Mục tiêu của Spring Cloud Function là **tách logic nghiệp vụ khỏi phương tiện gọi**. Các bean `pendingOrder`, `priceOrder`, `formatQuote` không cần biết chúng sẽ được dùng qua HTTP, message broker hay handler serverless.

| Môi trường | Ai kích hoạt Supplier? | Điều cần kiểm tra |
|---|---|---|
| Java nội bộ | Code gọi `get()` | Tên bean, kiểu dữ liệu, kết quả và số lần gọi |
| HTTP | Adapter Web theo cách công bố Supplier được hỗ trợ | Phương thức/path, response và lỗi |
| Sự kiện | Binder/poller hoặc subscription | Binding đầu ra, lịch kích hoạt, serializer, retry |
| Serverless | Trigger và handler tương ứng | Khả năng hỗ trợ Supplier, mapping event/kết quả |

Một Supplier không có đầu vào như `Function<Order, Receipt>`. Nếu yêu cầu là **nhận** đơn hàng từ HTTP request body hoặc message inbound, thường nên định nghĩa một Function hoặc Consumer nhận dữ liệu đó. Supplier phù hợp hơn khi nghiệp vụ **chủ động tạo hoặc lấy** dữ liệu.

### 10.1. Minh họa nguồn phát sự kiện

~~~text
Nguồn dữ liệu
     |
     v
pendingOrder: Supplier<OrderDraft>
     |
     v
priceOrder: Function<OrderDraft, Quote>
     |
     v
formatQuote: Function<Quote, String>
     |
     v
Supplier<String> hợp thành
     |
     v
Adapter/binder có output binding
     |
     v
Broker hoặc đích phát sự kiện
~~~

Để hoạt động thật, ứng dụng phải có binder phù hợp, destination/output binding, cơ chế poll hoặc reactive subscription và chính sách xử lý lỗi. Chỉ cấu hình `spring.cloud.function.definition` là chưa đủ.

## 11. Kiểm thử phép ghép

### 11.1. Unit test kiểm tra thứ tự và số lần gọi

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

class SupplierFunctionOrderTest {

    @Test
    void callsSupplierBeforeFunctionOnEachGet() {
        List<String> calls = new ArrayList<>();

        Supplier<Integer> source = () -> {
            calls.add("supplier");
            return 3;
        };

        Function<Integer, Integer> doubleIt = value -> {
            calls.add("function");
            return value * 2;
        };

        Supplier<Integer> composed =
                () -> doubleIt.apply(source.get());

        assertEquals(List.of(), calls); // Chua chay luc khai bao
        assertEquals(6, composed.get());
        assertEquals(
                List.of("supplier", "function"),
                calls);

        assertEquals(6, composed.get());
        assertEquals(
                List.of(
                    "supplier", "function",
                    "supplier", "function"),
                calls);
    }
}
~~~

Kiểm thử này chứng minh hai đặc điểm của phép ghép đồng bộ: nguồn chạy trước Function, và từng lần gọi `get()` thực hiện lại chuỗi.

### 11.2. Integration test dùng FunctionCatalog

Để kiểm tra tên function bean và cơ chế composition của Spring Cloud Function, cần một Spring context chứa `QuoteFunctions` và `QuoteApplication` ở mục 4.

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = QuoteApplication.class)
class SupplierCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogComposesSupplierWithFunctions() {
        Supplier<String> quoteSource =
                catalog.lookup(
                        "pendingOrder|priceOrder|formatQuote");

        assertNotNull(quoteSource);
        assertEquals(
                "SKU-17 x 2 = 250000 VND",
                quoteSource.get());
    }
}
~~~

Kiểm thử trên cần Spring Boot Test, Spring Cloud Function context và component scan phù hợp. Nó xác minh pipeline có thể được tìm bằng tên, hợp đồng đầu ra là `Supplier<String>` và kết quả đúng.

Để kiểm thử adapter sự kiện, cần thêm bài thử đầu ra qua binder hoặc broker phù hợp, đặc biệt là số lần phát và cách xử lý nguồn khi retry.

### 11.3. Những trường hợp nên kiểm tra thêm

- Supplier ném ngoại lệ: Function tiếp theo có bị gọi không?
- Supplier trả `null` hoặc dữ liệu sai: pipeline phản ứng ra sao?
- Function ném lỗi: adapter xử lý và có gọi lại Supplier không?
- Supplier được kích hoạt nhiều lần: dữ liệu có thể lặp không?
- Payload sau cùng có đúng cấu trúc, charset/content-type để adapter gửi đi không?

Unit test đơn lẻ cho mỗi bean chưa đảm bảo toàn bộ chuỗi tên và adapter đã được cấu hình đúng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `source.andThen(transform)` không biên dịch | Java `Supplier` không có `andThen` | Dùng lambda `() -> transform.apply(source.get())` hoặc composition của Spring |
| Gọi `pipeline.apply(...)` với chuỗi bắt đầu bằng Supplier | Hợp đồng tổng thể là Supplier | Tra cứu đúng kiểu và gọi `get()` |
| Viết `transform|source` | Supplier không nhận dữ liệu từ hàm trước | Đặt Supplier ở đầu pipeline |
| `lookup` không tìm thấy hàm | Sai tên bean, thiếu đăng ký hoặc component scan | Kiểm tra `@Bean`, dependency, catalog |
| Ghép tên được nhưng runtime lỗi | Kiểu trung gian hoặc dữ liệu thực không hợp lệ | Xem chữ ký từng bước và test `get()` |
| Phát message trùng | Nguồn trả cùng dữ liệu khi gọi lặp | Thiết kế nguồn, acknowledgment, idempotency |
| Không thấy event đầu ra | Thiếu binder, binding hoặc trigger | Cấu hình adapter và kiểm thử thực tế |
| Flux không phát | Không có subscription hoặc luồng đã kết thúc/lỗi | Kiểm tra publisher, operator và log |

Không nên ép tất cả bước về `Object` hoặc `String` chỉ để nối cho được. Điều đó che khuất hợp đồng nghiệp vụ, làm lỗi khó phát hiện hơn.

## 13. Bài tập tự luyện

**Bài 1.** Cho `Supplier<String> source = () -> " 15 "` và `Function<String, Integer> parse = s -> Integer.parseInt(s.trim())`. Viết `Supplier<Integer>` đã ghép, gọi nó và nêu kết quả.

**Bài 2.** Cho `Supplier<Integer> quantity`, `Function<Integer, Long> price` và `Function<Long, String> format`. Hãy xác định kiểu của cả pipeline và viết lambda nối đủ ba bước.

**Bài 3.** Dựa vào `QuoteFunctions`, viết giá trị `spring.cloud.function.definition` để thu được `Supplier<Quote>`, và một giá trị khác để thu được `Supplier<String>`.

**Bài 4.** Vì sao `Supplier<OrderDraft>` không thể nối trực tiếp với `Function<Quote, String>` theo generic Java? Đề xuất hàm trung gian.

**Bài 5.** Nếu `pendingOrder.get()` ném ngoại lệ, `priceOrder` và `formatQuote` có chạy tiếp không trong luồng đồng bộ? Nếu adapter retry, điều gì có thể xảy ra?

**Bài 6.** Một Supplier luôn trả cùng mã đơn hàng và được poll định kỳ để phát sự kiện. Nêu rủi ro cùng hai biện pháp giảm thiểu.

### Gợi ý đáp án

- **Bài 1:** `Supplier<Integer> result = () -> parse.apply(source.get());`; `result.get()` trả `15`.
- **Bài 2:** `Supplier<String>`; `() -> format.apply(price.apply(quantity.get()))`.
- **Bài 3:** `"pendingOrder|priceOrder"` tạo `Supplier<Quote>`; `"pendingOrder|priceOrder|formatQuote"` tạo `Supplier<String>`.
- **Bài 4:** Cần `Function<OrderDraft, Quote>` như `priceOrder`.
- **Bài 5:** Bước sau không được gọi nếu nguồn ném ngoại lệ; retry có thể gọi nguồn thêm lần nữa.
- **Bài 6:** Có thể phát trùng. Thiết kế chọn bản ghi mới/đánh dấu tiến độ và xử lý idempotent theo khóa định danh.

## 14. Ghi nhớ

- `Supplier<A>` tạo dữ liệu bằng `get()`; `Function<A, B>` biến đổi bằng `apply(A)`.
- Phép ghép `Supplier<A>` với `Function<A, B>` cho kết quả `Supplier<B>` về mặt hành vi: `() -> transform.apply(source.get())`.
- Trong Java thuần, `Supplier` không có `andThen`; Spring Cloud Function hỗ trợ ghép theo tên như `catalog.lookup("pendingOrder|priceOrder")`.
- Với pipeline bắt đầu bằng Supplier, hãy lấy kiểu kết quả `Supplier<R>` và gọi `get()`; kiểm tra kiểu giữa mọi bước.
- `spring.cloud.function.definition` chọn logic cho adapter; cách kích hoạt, lịch phát và xử lý lỗi phụ thuộc HTTP, messaging hoặc serverless adapter được sử dụng.
- Khi Supplier lấy dữ liệu thật, phải thiết kế rõ trường hợp thiếu dữ liệu, lỗi nguồn, số lần gọi và khả năng phát trùng.
