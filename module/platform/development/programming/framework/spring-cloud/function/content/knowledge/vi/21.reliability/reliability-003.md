# Phân biệt ngoại lệ trực tiếp và tín hiệu lỗi Reactor

## 1. Mục tiêu bài học

Một hàm Java xử lý đơn hàng có thể báo lỗi ngay khi gọi `apply(...)`. Nhưng nếu cùng phép tính được áp dụng bên trong `Mono.map(...)` hoặc `Flux.map(...)`, lỗi thường xuất hiện dưới dạng tín hiệu `onError` **khi Publisher được subscribe**, không phải khi tạo pipeline.

Sự khác biệt này ảnh hưởng trực tiếp đến độ tin cậy của hệ thống: nơi đặt `try/catch`, cách log, retry, xử lý dữ liệu sai, xác nhận message và kiểm tra tác dụng phụ. Đặc biệt trong Spring Cloud Function, cùng logic nghiệp vụ có thể được đăng ký dưới dạng `Function`, ghép bằng `FunctionCatalog` rồi được gọi qua HTTP, sự kiện hoặc môi trường serverless. Adapter có thể quyết định lúc nào subscription được khởi tạo và cách chuyển lỗi sang giao thức vận chuyển.

Trong chương **Độ tin cậy**, bài này giúp bạn:

- Phân biệt ngoại lệ Java xảy ra **ngay trong lời gọi** với lỗi được phát qua `Publisher.onError`.
- Hiểu rõ các pha **tạo Publisher (assembly)**, **subscription** và **xử lý tín hiệu**.
- Biết khi nào `try/catch` có tác dụng, khi nào cần `onErrorResume`, `onErrorMap` và `StepVerifier`.
- Thiết kế Function đồng bộ và reactive có generic rõ ràng, dùng lại một quy tắc nghiệp vụ trong nhiều luồng.
- Phân loại lỗi validation, lỗi hạ tầng, lỗi transient để tránh retry dữ liệu sai.
- Kiểm soát thứ tự validation và side effect, đặc biệt khi có retry hoặc resubscription.
- Kiểm thử hành vi của `FunctionCatalog` và ranh giới HTTP/message/serverless mà không nhầm lẫn thành công của `lookup` với thành công xử lý dữ liệu.

> Trong Reactor, thông thường các ngoại lệ không phải loại fatal ném **bên trong callback operator** (như `map`) được biến thành tín hiệu `onError`. Một số lỗi xảy ra trước khi Publisher được tạo vẫn ném trực tiếp; không được khẳng định “mọi lỗi reactive đều là onError”.

## 2. Hai kênh báo lỗi cơ bản

Xét hàm đồng bộ:

~~~java
import java.util.function.Function;

Function<String, Integer> parseQuantity =
        text -> Integer.parseInt(text.trim());
~~~

Với `parseQuantity.apply("abc")`, `NumberFormatException` được ném ngay trên call stack đang chạy. Để bắt nó, ta có thể dùng `try/catch` bao quanh lời gọi:

~~~java
try {
    int quantity = parseQuantity.apply("abc");
    System.out.println(quantity);
} catch (NumberFormatException ex) {
    System.out.println("Quantity khong phai so nguyen");
}
~~~

Đặt cùng logic trong Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<Integer> quantities = Flux.just("10", "abc", "30")
        .map(parseQuantity);
~~~

Dòng trên thường chỉ xây dựng `Flux`. Khi subscriber đăng ký nhận dữ liệu và yêu cầu phần tử, kết quả có thể là:

~~~text
onSubscribe
request
onNext(10)
onError(NumberFormatException)
~~~

Phần tử `"30"` không được xử lý tiếp trong chuỗi mặc định sau một `onError` kết thúc.

| Tiêu chí | Ngoại lệ trực tiếp | Tín hiệu lỗi Reactor |
|---|---|---|
| Nơi xuất hiện | Trong lời gọi Java hiện tại | Trong vòng đời Publisher/subscription |
| Ví dụ | `parse.apply("abc")` | `Flux.just("abc").map(parse)` |
| Cách quan sát | `try/catch`, `assertThrows` | `onError`, `StepVerifier.expectError` |
| Cách phục hồi thường dùng | `catch` rồi trả kết quả/đổi exception | `onErrorResume`, `onErrorReturn`, `onErrorMap` |
| Thời điểm | Thường ngay khi code chạy đến lời gọi | Thường khi source phát tới phần tử gây lỗi |
| Điểm cần chú ý | Lời gọi chưa trả một kết quả | Có thể đã phát một số `onNext` trước `onError` |

Reactor tuân theo quy tắc tín hiệu **`onNext*` rồi một tín hiệu terminal `onComplete` hoặc `onError`**. Sau khi `onError` được phát cho một subscriber, chuỗi đó không tiếp tục phát `onNext` bình thường.

## 3. Ngoại lệ đồng bộ ở Function.apply

Giả sử logic định giá nhận số lượng:

~~~java
import java.util.function.Function;

Function<Integer, Long> calculatePrice = quantity -> {
    if (quantity == null || quantity <= 0) {
        throw new IllegalArgumentException(
                "Quantity phai lon hon 0");
    }
    return Math.multiplyExact(quantity.longValue(), 125_000L);
};
~~~

Lời gọi:

~~~java
long total = calculatePrice.apply(2); // 250000
~~~

chạy đồng bộ. Với input `0`:

~~~java
calculatePrice.apply(0);
~~~

exception được ném trước khi `apply` trả thành công.

### 3.1. Vì sao try/catch phù hợp ở Java thuần?

~~~java
try {
    Long amount = calculatePrice.apply(0);
    System.out.println(amount);
} catch (IllegalArgumentException ex) {
    // Phản hồi lỗi dữ liệu ngay tại ranh giới Java.
    System.out.println("ORDER_REJECTED");
}
~~~

Có thể kiểm tra bằng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void rejectsNonPositiveQuantity() {
    assertThrows(IllegalArgumentException.class,
            () -> calculatePrice.apply(0));
}
~~~

Trong đoạn test, `calculatePrice` là Function đã được khai báo ở trên và được cung cấp cho test.

### 3.2. Thời gian chạy không quyết định kiểu interface

Một `Function<T,R>` có thể gọi HTTP/JDBC blocking hoặc làm việc nhanh trong bộ nhớ. Cách khai báo Java chỉ cho biết hợp đồng input/output, **không bảo đảm non-blocking hay thread-safe**.

Ngược lại, một Function trả `Mono<R>` có thể ném ngoại lệ ngay **trước khi tạo Mono** nếu code kiểm tra input ngoài Publisher. Xem mục tiếp theo.

## 4. Reactive: tạo Publisher khác với thực thi công việc

Reactor xây dựng mô tả của một luồng tín hiệu:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<Mono<String>, Mono<Integer>> parseMono =
        mono -> mono.map(Integer::parseInt);

Mono<Integer> result =
        parseMono.apply(Mono.just("abc"));
~~~

Trong ví dụ, `parseMono.apply(...)` trả một Publisher. `Integer.parseInt("abc")` thường chưa được gọi tại thời điểm đó, vì `map` sẽ xử lý khi subscriber nhận phần tử.

Khi một subscriber subscribe:

~~~java
result.subscribe(
        value -> System.out.println("Value: " + value),
        error -> System.err.println(
                "Error: " + error.getClass().getSimpleName()));
~~~

Lỗi thông thường được gửi tới callback xử lý error. Ví dụ `subscribe(...)` này chỉ minh họa cách nhận tín hiệu; ứng dụng có WebFlux, Spring Cloud Stream hoặc serverless adapter nên tuân thủ cơ chế subscription và lifecycle của framework, không tự gọi `subscribe` rải rác.

### 4.1. Assembly và subscription

~~~text
Pha assembly (Java hiện tại)
    Flux.just("10", "abc").map(Integer::parseInt)
                           |
                           v
                 Tạo Publisher, chưa parse

Pha subscription
    Subscriber subscribe / request
                           |
                           v
                     parse "10"
                           |
                           v
                     onNext(10)
                           |
                           v
                     parse "abc"
                           |
                           v
               onError(NumberFormatException)
~~~

Một operator dùng `map`/`filter` không làm công việc thực thi tức thời chỉ vì phương thức tạo operator đã được gọi. Nhưng **không phải mọi đoạn code trong phương thức tạo pipeline đều lazy**: code chạy trước `return flux.map(...)` vẫn chạy ngay.

### 4.2. onError là tín hiệu terminal, không phải giá trị dữ liệu

`Mono<T>` có thể phát:

- Một `onNext(T)` rồi `onComplete`.
- Một `onComplete` không có phần tử.
- Một `onError(Throwable)`.

`Flux<T>` có thể phát 0 đến nhiều `onNext(T)`, rồi `onComplete` hoặc `onError`.

Vì `onError` là tín hiệu lỗi, bạn **không thể xem nó như một đối tượng `T` trong `Flux<T>`**. Muốn biểu diễn lỗi nghiệp vụ như dữ liệu, có thể dùng kiểu kết quả tường minh như `Result<T>` rồi thiết kế operator tương ứng.

## 5. Lỗi xảy ra ngay khi tạo Publisher

Một Function reactive **vẫn có thể ném exception đồng bộ**:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<String, Mono<Integer>> parseReactive = input -> {
    // Kiểm tra này xảy ra NGAY khi apply được gọi.
    if (input == null) {
        throw new IllegalArgumentException(
                "Input khong duoc null");
    }

    // Phần parse này được trì hoãn đến subscription.
    return Mono.fromCallable(
            () -> Integer.parseInt(input));
};
~~~

Khi gọi:

~~~java
parseReactive.apply(null); // Ném IllegalArgumentException ngay.
~~~

Nhưng:

~~~java
Mono<Integer> result = parseReactive.apply("bad");
// Dòng trên tạo được Mono.

result.subscribe(
        System.out::println,
        error -> System.err.println(error.getMessage()));
// NumberFormatException được phát qua onError.
~~~

Trong cùng một Function, **hai lỗi nằm ở hai kênh khác nhau** tùy code được đặt trước hay trong Publisher.

### 5.1. Lỗi từ Mono.just với biểu thức tính ngay

~~~java
Function<String, Mono<Integer>> eager =
        input -> Mono.just(Integer.parseInt(input));
~~~

`Integer.parseInt(input)` là đối số của `Mono.just`, nên Java phải tính nó **trước khi gọi `Mono.just(...)`**. Với `"bad"`, exception xảy ra trực tiếp trong `apply`.

Đây là điểm khác biệt căn bản so với:

~~~java
Function<String, Mono<Integer>> deferred =
        input -> Mono.fromCallable(
                () -> Integer.parseInt(input));
~~~

Ở bản `deferred`, lambda trong `fromCallable` được gọi khi có subscription và lỗi được Reactor chuyển thành `onError`.

### 5.2. Tại sao try/catch quanh apply không đủ?

~~~java
try {
    Mono<Integer> result =
            deferred.apply("bad");

    // Phương thức apply trả Mono thành công.
} catch (NumberFormatException ex) {
    // Không phải nơi xử lý lỗi phát sinh khi subscribe.
}
~~~

`try/catch` vẫn hữu ích khi kiểm tra phần assembly hoặc lời gọi đồng bộ, nhưng **không thay thế** xử lý error signal của Publisher.

## 6. Mono.defer, Mono.fromCallable và Mono.error

Các factory thường gặp có ý nghĩa khác nhau.

### 6.1. Mono.fromCallable: trì hoãn lời gọi có kết quả

~~~java
Mono<Integer> parsed = Mono.fromCallable(
        () -> Integer.parseInt("bad"));
~~~

Lời gọi trong `Callable` được thực hiện khi subscribe; với lỗi parse bình thường, subscriber nhận `onError(NumberFormatException)`. Nếu Callable trả `null`, `Mono.fromCallable` hoàn thành rỗng, không phát `onNext(null)`.

### 6.2. Mono.defer: trì hoãn cả việc tạo Publisher

~~~java
Mono<Integer> parsed = Mono.defer(
        () -> Mono.just(Integer.parseInt("bad")));
~~~

`Mono.just(...)` nằm bên trong callback `defer`, nên việc gọi `Integer.parseInt` xảy ra lúc subscription. Nếu callback ném exception thông thường, Reactor truyền thành `onError`.

`Mono.defer` hữu ích khi mỗi subscription phải **tạo lại một Publisher** dựa trên ngữ cảnh tại thời điểm đó. Điều này có thể làm các side effect trong callback chạy lại khi retry/resubscribe; cần cẩn thận.

### 6.3. Mono.error: tạo Publisher phát lỗi

~~~java
Mono<Integer> rejected =
        Mono.error(new IllegalArgumentException(
                "ORDER_INVALID"));
~~~

Tạo `Mono.error(...)` không có nghĩa exception được `throw` tại chỗ. Publisher phát `onError` khi subscribe.

Có thể dùng biến thể nhận Supplier để tạo exception theo từng subscription khi cần:

~~~java
Mono<Integer> rejected =
        Mono.error(() -> new IllegalArgumentException(
                "ORDER_INVALID"));
~~~

### 6.4. Bảng so sánh ngắn

| Đoạn code | Exception có thể xuất hiện khi nào? |
|---|---|
| `Integer.parseInt("bad")` | Ngay |
| `Mono.just(Integer.parseInt("bad"))` | Ngay, trước khi tạo Mono |
| `Mono.fromCallable(() -> Integer.parseInt("bad"))` | Khi subscribe → `onError` |
| `Mono.defer(() -> Mono.just(Integer.parseInt("bad")))` | Khi subscribe → `onError` |
| `Mono.error(new IllegalArgumentException())` | Publisher phát `onError` khi subscribe |
| `Flux.just("bad").map(Integer::parseInt)` | Khi map xử lý phần tử → `onError` |

Không nên làm rối hợp đồng chỉ để mọi lỗi luôn có cùng hình thức. Quan trọng là ranh giới xử lý phải được **thiết kế và kiểm thử rõ**.

## 7. Các chữ ký Function dễ bị nhầm

Ba chữ ký sau có ý nghĩa khác nhau:

~~~text
Function<OrderInput, Quote>
Function<OrderInput, Mono<Quote>>
Function<Mono<OrderInput>, Mono<Quote>>
~~~

| Hợp đồng | Tham số `apply` | Giá trị `apply` trả về |
|---|---|---|
| `Function<OrderInput,Quote>` | Một OrderInput | Một Quote |
| `Function<OrderInput,Mono<Quote>>` | Một OrderInput | Publisher cho tối đa một Quote |
| `Function<Mono<OrderInput>,Mono<Quote>>` | Một Mono của OrderInput | Mono của Quote |

Ví dụ chuyển phép tính đồng bộ sang reactive:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

Function<String, Integer> parseOne = Integer::parseInt;

Function<Mono<String>, Mono<Integer>> parseMono =
        mono -> mono.map(parseOne);
~~~

Ở đây, `parseOne` vẫn là Function Java thuần. Lỗi `NumberFormatException` bị ném bên trong callback `map` khi có phần tử, do đó thường xuất hiện dưới dạng `onError`.

Đừng dùng `Function<String,Integer>.andThen(Function<Mono<Integer>,Mono<String>>)` trực tiếp trong Java: đầu ra `Integer` không phải `Mono<Integer>`. Muốn ghép, phải thống nhất kiểu trung gian hoặc dùng bridge tường minh.

### 7.1. map và flatMap quyết định kiểu lỗi và dữ liệu

- `mono.map(Function<T,R>)`: callback trả giá trị `R`; exception trong mapper thường trở thành `onError`.
- `mono.flatMap(Function<T,Mono<R>>)`: callback trả Publisher; lỗi có thể tới từ cả callback và inner Publisher.
- `flux.flatMap(Function<T,Publisher<R>>)`: có thể xử lý nhiều inner Publisher đồng thời, ảnh hưởng thứ tự và thời điểm lỗi.
- `concatMap`: xử lý các inner Publisher theo thứ tự, thường phù hợp khi cần thứ tự chặt.

Với `flatMap`, lỗi của một inner Publisher thường kết thúc chuỗi mặc định và có thể hủy các công việc chưa hoàn tất; hãy kiểm tra yêu cầu nghiệp vụ nếu nhiều side effect đang chạy song song.

## 8. Ví dụ Spring Cloud Function: báo giá

Ta xây dựng một Function xử lý một yêu cầu và một Function biến đổi cả `Flux`. Cả hai dùng chung quy tắc định giá.

### 8.1. Model và lỗi nghiệp vụ

~~~java
package example.functions;

public final class QuoteModels {

    private QuoteModels() {}

    public record OrderInput(String orderId, int quantity) {}

    public record Quote(String orderId, long totalVnd) {}
}
~~~

Lỗi validation riêng giúp nhận diện lỗi không nên retry:

~~~java
package example.functions;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

### 8.2. Bean imperative và reactive

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

@Configuration
public class QuoteFunctions {

    @Bean
    public Function<OrderInput, Quote> quoteOne() {
        return input -> {
            if (input == null
                    || input.orderId() == null
                    || !input.orderId().matches("ORD-[0-9]+")
                    || input.quantity() <= 0) {
                throw new InvalidOrderException(
                        "Order khong hop le");
            }

            long total = Math.multiplyExact(
                    input.quantity(), 125_000L);

            return new Quote(input.orderId(), total);
        };
    }

    @Bean
    public Function<Flux<OrderInput>, Flux<Quote>> quoteStream(
            @Qualifier("quoteOne")
            Function<OrderInput, Quote> quoteOne) {

        // Mapper chạy theo subscription, không parse ngay tại apply.
        return orders -> orders.map(quoteOne);
    }

    @Bean
    public Function<Mono<OrderInput>, Mono<Quote>> quoteMono(
            @Qualifier("quoteOne")
            Function<OrderInput, Quote> quoteOne) {

        return order -> order.map(quoteOne);
    }

    @Bean
    public Function<Flux<Quote>, Flux<String>> formatQuoteStream() {
        return quotes -> quotes.map(
                quote -> quote.orderId()
                        + "=" + quote.totalVnd());
    }
}
~~~

Bảng hợp đồng:

| Bean | Input | Output |
|---|---|---|
| `quoteOne` | `OrderInput` | `Quote` |
| `quoteStream` | `Flux<OrderInput>` | `Flux<Quote>` |
| `quoteMono` | `Mono<OrderInput>` | `Mono<Quote>` |
| `formatQuoteStream` | `Flux<Quote>` | `Flux<String>` |

Trong `quoteOne`, lỗi validation ném trực tiếp tại `apply(OrderInput)`. Nhưng khi `quoteOne` được gọi qua `Flux.map(quoteOne)`, ngoại lệ đó thường trở thành `onError` trên Flux.

### 8.3. Cùng lỗi nghiệp vụ, hai cách biểu hiện

Java imperative:

~~~java
QuoteFunctions config = new QuoteFunctions();

try {
    config.quoteOne().apply(
            new QuoteModels.OrderInput("ORD-42", 0));
} catch (InvalidOrderException ex) {
    System.out.println("Rejected ngay trong apply");
}
~~~

Reactive:

~~~java
import reactor.core.publisher.Flux;

Flux<QuoteModels.Quote> result =
        config.quoteStream(config.quoteOne())
              .apply(Flux.just(
                    new QuoteModels.OrderInput("ORD-42", 0)));

// Lỗi thường chỉ xuất hiện khi result được subscribe.
~~~

Cùng một quy tắc, không nhất thiết cùng **thời điểm quan sát lỗi**.

## 9. FunctionCatalog và ghép pipeline reactive

Khi các Function bean đã được Spring đăng ký, chúng có thể được tra cứu theo tên từ `FunctionCatalog`. Với hai bean ở mục 8:

~~~text
quoteStream|formatQuoteStream
~~~

Hợp đồng của phép ghép:

~~~text
Function<Flux<OrderInput>, Flux<Quote>>
            |
            v
Function<Flux<Quote>, Flux<String>>
            |
            v
Function<Flux<OrderInput>, Flux<String>>
~~~

Service minh họa:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import example.functions.QuoteModels.OrderInput;

@Service
public class QuoteStreamService {

    private final FunctionCatalog catalog;

    public QuoteStreamService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Flux<String> process(Flux<OrderInput> orders) {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                        "quoteStream|formatQuoteStream");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return pipeline.apply(orders);
    }
}
~~~

Với `OrderInput("ORD-42", 2)` và `OrderInput("ORD-43", 3)`, luồng kết quả dự kiến phát `"ORD-42=250000"` và `"ORD-43=375000"`. Nếu có phần tử quantity bằng `0`, `quoteOne` ném `InvalidOrderException` trong mapper, lỗi thường được truyền thành `onError` khi subscriber tới phần tử đó.

### 9.1. Lookup thành công chưa chứng minh pipeline chạy được

Tên sai, không được đăng ký, không thể ghép hoặc xung đột kiểu có thể phát sinh ngay tại `catalog.lookup(...)`. Một số lỗi khác chỉ xuất hiện ở `apply` hoặc lúc subscribe.

Vì vậy integration test cần kiểm tra cả bốn việc:

1. Catalog tìm thấy bean hoặc expression.
2. `apply` nhận đúng kiểu đầu vào và trả Publisher đúng hợp đồng.
3. Subscriber nhận đúng `onNext`, `onComplete` hoặc `onError`.
4. Side effect được thực thi hoặc bị chặn theo quy tắc nghiệp vụ.

### 9.2. Cấu hình definition

~~~yaml
spring:
  cloud:
    function:
      definition: "quoteStream|formatQuoteStream"
~~~

Hoặc:

~~~properties
spring.cloud.function.definition=quoteStream|formatQuoteStream
~~~

`spring.cloud.function.definition` chọn biểu thức hàm cho adapter phù hợp. Nó **không tự mở HTTP endpoint**, tạo message binding, serverless trigger, subscribe Publisher hay định nghĩa chính sách retry.

### 9.3. Không mặc định hỗ trợ mixed composition giống Java

`quoteOne` có kiểu `Function<OrderInput,Quote>`, trong khi `formatQuoteStream` nhận `Flux<Quote>`. Vì `Quote` khác `Flux<Quote>`, Java `andThen` không nối trực tiếp được hai chữ ký này.

Spring Cloud Function có các cơ chế adaptation tùy phiên bản/ngữ cảnh, nhưng không được mặc định phép ghép mixed trực tiếp sẽ có cùng hành vi trong mọi adapter. Bean `quoteStream` là bridge tường minh, giúp loại trừ sự mơ hồ về kiểu và thời điểm lỗi.

## 10. onError kết thúc Flux; phần tử phía sau thì sao?

Xét:

~~~java
Flux<Integer> numbers = Flux.just("4", "5", "bad", "6")
        .map(Integer::parseInt);
~~~

Khi subscribe, chuỗi thường phát:

~~~text
onNext(4)
onNext(5)
onError(NumberFormatException)
~~~

Phần tử `"6"` không được phát vì `onError` là terminal signal.

Nếu gắn fallback:

~~~java
Flux<Integer> recovered = numbers
        .onErrorResume(ex -> Flux.just(-1));
~~~

kết quả sẽ là `4, 5, -1` rồi `onComplete`. `-1` là phần tử fallback, **không có nghĩa nguồn ban đầu đã tiếp tục từ phần tử `"6"`**.

### 10.1. Nếu muốn tiếp tục xử lý các event độc lập

Khi mỗi phần tử là một message riêng, có thể thiết kế xử lý lỗi **cho từng phần tử**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Integer> valid = Flux.just("4", "bad", "6")
        .concatMap(raw ->
            Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(
                    NumberFormatException.class,
                    error -> Mono.empty()));
~~~

Kết quả là `4` và `6`. `concatMap` giúp xử lý từng inner Publisher theo thứ tự, còn `onErrorResume` chỉ xử lý phần tử đang thất bại.

**Lưu ý:** bỏ qua message sai không phải lúc nào cũng đúng. Ứng dụng thực có thể phải lưu lỗi vào DLQ/quarantine, ghi nhận định danh message và metrics, đồng thời bảo đảm quy tắc xác nhận của broker.

### 10.2. Thận trọng với onErrorContinue

`onErrorContinue` có cách tác động lên một số operator upstream không phải lúc nào cũng dễ dự đoán khi pipeline phức tạp. Nếu mục tiêu là cách ly lỗi từng message, ưu tiên tạo inner Publisher và xử lý `onErrorResume` **bên trong inner** như ví dụ trên, với policy rõ ràng.

## 11. Các toán tử xử lý lỗi của Reactor

| Operator | Mục đích | Có thay đổi tín hiệu terminal không? |
|---|---|---|
| `doOnError` | Quan sát lỗi, log hoặc metrics | Không phục hồi lỗi |
| `onErrorMap` | Chuyển loại exception | Vẫn phát `onError` |
| `onErrorResume` | Chuyển sang Publisher dự phòng | Có thể phục hồi |
| `onErrorReturn` | Trả một giá trị dự phòng | Có thể phục hồi |
| `retry` / `retryWhen` | Subscribe lại upstream | Có thể xử lý lại dữ liệu |

### 11.1. doOnError không nuốt lỗi

~~~java
Flux<Integer> observed = Flux.just("bad")
        .map(Integer::parseInt)
        .doOnError(error ->
            System.err.println("Parse failed: "
                    + error.getClass().getSimpleName()));
~~~

`doOnError` chỉ thực hiện một callback quan sát. Nếu không có bước phục hồi, downstream vẫn thấy `onError`.

### 11.2. onErrorMap đổi loại lỗi và giữ cause

Có thể định nghĩa exception của ứng dụng:

~~~java
package example.functions;

public class OrderRejectedException extends RuntimeException {
    public OrderRejectedException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Rồi chuyển một lỗi parse sang loại dễ phân loại hơn:

~~~java
Flux<Integer> mapped = Flux.just("bad")
        .map(Integer::parseInt)
        .onErrorMap(NumberFormatException.class,
            error -> new OrderRejectedException(
                    "So luong khong hop le", error));
~~~

Chuỗi này vẫn kết thúc bằng lỗi, nhưng ngoại lệ đã thành loại `OrderRejectedException` và giữ cause ban đầu. Việc đổi loại lỗi không tự khắc phục input sai.

### 11.3. onErrorResume chỉ nên dùng khi fallback hợp lệ

~~~java
Mono<Integer> parsed = Mono.fromCallable(
        () -> Integer.parseInt("bad"));

Mono<Integer> fallback = parsed.onErrorResume(
        NumberFormatException.class,
        error -> Mono.just(-1));
~~~

`-1` trong ví dụ chỉ minh họa cơ chế. **Không dùng một số giả trong báo giá hoặc tồn kho** chỉ để tránh lỗi nếu giá trị đó làm sai nghiệp vụ. Có thể chọn cách chuyển lỗi thành thông tin từ chối hoặc cách ly input sai.

### 11.4. onErrorReturn không tương đương retry

~~~java
Mono<Integer> result =
        Mono.<Integer>error(new IllegalStateException("Unavailable"))
            .onErrorReturn(-1);
~~~

`onErrorReturn` thay lỗi bằng một giá trị và hoàn tất, **không gọi lại nguồn**. Ngược lại, `retry` có thể subscribe lại, khiến nguồn được xử lý lại — bao gồm các side effect nếu có.

## 12. Retry phải phân loại lỗi và thời điểm lỗi

Một lỗi validation như `quantity=0` không tự trở thành hợp lệ khi lặp lại cùng input. Nếu gắn `retry(10)`, pipeline thường chỉ ném lại cùng lỗi nhiều lần.

Ngược lại, database hoặc API từ xa có thể gặp timeout tạm thời. Retry có giới hạn có thể phù hợp **khi thao tác an toàn để gọi lại**.

### 12.1. Giới hạn và lọc exception được retry

Định nghĩa loại lỗi hạ tầng tạm thời:

~~~java
package example.functions;

public class TemporaryDependencyException
        extends RuntimeException {

    public TemporaryDependencyException(String message) {
        super(message);
    }
}
~~~

Một Publisher từ adapter hạ tầng có thể được retry với `Retry`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

// remoteCall là Mono<String> đại diện cho dịch vụ phụ thuộc ngoài.
Mono<String> retryable = remoteCall.retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
             .filter(error ->
                 error instanceof TemporaryDependencyException));
~~~

`Retry.backoff(2, ...)` cho phép tối đa **hai lần retry thêm** sau lượt subscribe đầu, với khoảng lùi theo cấu hình Reactor. Các loại exception không khớp bộ lọc sẽ không được operator này retry. Cần tránh retry chồng nhiều tầng gây số lần gọi ngoài dự kiến.

### 12.2. Retry là resubscribe, không sửa riêng phần tử lỗi

~~~java
Flux<Integer> retrying = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .retry(1);
~~~

Subscriber có thể nhận:

~~~text
onNext(1)
onNext(1)
onError(NumberFormatException)
~~~

Nguồn được subscribe lại từ đầu. Nếu trước đó có Consumer ghi kết quả cho `1`, lần thứ hai có thể ghi trùng.

### 12.3. Lỗi trước khi Publisher tồn tại không nằm trong retryWhen

Nếu `function.apply(input)` ném exception **trước khi trả Mono/Flux**, bạn chưa có Publisher để gắn `retryWhen`. Có thể chủ động trì hoãn:

~~~java
import reactor.core.publisher.Mono;

// quoteOne là Function<OrderInput, Quote> do ứng dụng cung cấp.
Mono<QuoteModels.Quote> deferredQuote =
        Mono.fromCallable(() ->
            quoteOne.apply(
                new QuoteModels.OrderInput("ORD-42", 2)));
~~~

Exception thông thường ném trong Callable sẽ được Reactor chuyển thành `onError`. Nhưng điều đó **không có nghĩa mọi exception đều nên retry**. Validation failure, lỗi quyền và xung đột nghiệp vụ cần chính sách từ chối hoặc xử lý riêng.

## 13. Side effect: onError không tự hoàn tác dữ liệu

Xét:

~~~text
Flux<OrderInput>
     |
     v
validate → calculate → saveQuote (DB commit)
                              |
                              v
                         nextStep lỗi
                              |
                              v
                            onError
~~~

Dù downstream nhận `onError`, database có thể đã commit. Nếu toàn pipeline được retry, `saveQuote` có thể chạy lại. **Tín hiệu `onError` không đồng nghĩa transaction rollback.**

Ba thời điểm cần phân biệt:

1. **Lỗi trước side effect:** chưa ghi dữ liệu.
2. **Lỗi trước commit:** xem transaction/storage có rollback không.
3. **Lỗi sau commit nhưng trước response/ack:** dữ liệu có thể đã lưu, caller không biết; retry dễ tạo trùng.

### 13.1. Validation trước Consumer

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

Function<QuoteModels.OrderInput, QuoteModels.Quote> quoteOne =
        new QuoteFunctions().quoteOne();

Consumer<QuoteModels.Quote> store =
        quote -> System.out.println("Save: " + quote);

Consumer<QuoteModels.OrderInput> pipeline =
        input -> store.accept(quoteOne.apply(input));
~~~

Nếu `quoteOne.apply(input)` ném `InvalidOrderException`, `store.accept(...)` không được gọi trong lần thực thi đồng bộ. Khi dùng `Flux.map(quoteOne)`, lỗi validation thường dừng luồng trước khi downstream xử lý phần tử sai đó.

Tuy nhiên, **các phần tử đã được ghi trước lỗi không tự rollback**. Điều này quan trọng với batch và message broker.

### 13.2. Idempotency bảo vệ retry và redelivery

Ở ranh giới ghi dữ liệu nên có:

- Khóa nghiệp vụ hoặc idempotency key ổn định, chẳng hạn `orderId`.
- Unique constraint hoặc thao tác ghi nguyên tử tại storage. `SELECT` rồi `INSERT` không khóa có thể đua ghi giữa các instance.
- Quy tắc cho **cùng key nhưng payload khác**.
- Cơ chế phục hồi khi DB đã commit nhưng response/ack bị mất.

Nếu lưu DB rồi phát sự kiện, cân nhắc transactional outbox hoặc mô hình nhất quán tương đương. Ghép `Function` với `Consumer` không tự tạo transaction xuyên DB và broker.

### 13.3. Không tự subscribe trong Consumer thiếu quản lý

~~~java
import java.util.function.Consumer;
import reactor.core.publisher.Flux;

Consumer<Flux<QuoteModels.Quote>> unsafeSink =
        flux -> flux.subscribe(
                quote -> System.out.println("Save: " + quote));
~~~

Đây là ví dụ minh họa **điều nên tránh trong production**. Nếu Consumer tự gọi `subscribe` rồi trả về, adapter có thể coi lời gọi đã hoàn tất trước khi toàn bộ phần tử được ghi; lỗi không được thông báo đúng về tầng ack/retry.

Với Spring Cloud Function/Stream, cần tuân theo cơ chế quản lý subscription của adapter, không dựa vào `Consumer<Flux<T>>` để suy rằng mọi side effect đã xong khi `accept` trả về.

## 14. HTTP: chuyển lỗi sang status không phụ thuộc throw hay onError

Giả sử một controller tự gọi service đồng bộ:

~~~java
@PostMapping("/quotes/sync")
public QuoteModels.Quote quoteSync(
        @RequestBody QuoteModels.OrderInput input) {

    return quoteOne.apply(input);
}
~~~

`quoteOne` là Function được inject vào controller. Nếu `apply` ném `InvalidOrderException`, lỗi xảy ra trong call stack của request. Spring MVC/WebFlux có thể dùng exception handler ánh xạ lỗi theo cấu hình.

Một handler reactive trả `Mono<Quote>`:

~~~java
@PostMapping("/quotes/reactive")
public Mono<QuoteModels.Quote> quoteReactive(
        @RequestBody QuoteModels.OrderInput input) {

    return Mono.fromCallable(() -> quoteOne.apply(input));
}
~~~

Khi WebFlux subscribe Publisher để xử lý response, ngoại lệ từ Callable thường thành `onError`. Để chạy, controller cần các import Spring Web phù hợp, `Mono` và một field `quoteOne` được inject.

### 14.1. Không đặt try/catch quanh return rồi coi đã bắt lỗi async

~~~java
try {
    return Mono.fromCallable(() -> quoteOne.apply(input));
} catch (InvalidOrderException ex) {
    // Khong bat duoc exception tu Callable luc subscribe.
}
~~~

Dòng tạo Mono thường không ném lỗi của Callable. Framework hoặc operator reactive phải quan sát error signal sau subscription.

### 14.2. Ánh xạ theo loại lỗi

| Loại lỗi | Hành vi HTTP tham khảo |
|---|---|
| Payload sai/validation lỗi | 400 hoặc 4xx theo API contract |
| Không được phép | 401/403 theo chính sách bảo mật |
| Cùng idempotency key nhưng nội dung khác | 409 nếu phù hợp |
| Phụ thuộc hạ tầng không khả dụng | 5xx phù hợp, cân nhắc retry |
| Lỗi hệ thống không dự kiến | 5xx, không công bố stacktrace nhạy cảm |

Hình thức exception đồng bộ hay tín hiệu Reactor **không tự quyết định HTTP status**. API cần chính sách mapping rõ ràng.

### 14.3. Function Web adapter khác controller tùy chỉnh

Spring Cloud Function có web adapter theo starter/phiên bản. Endpoint, converter và cơ chế error mapping có thể khác với `@RestController` tự viết. Đừng mặc định `spring.cloud.function.definition` sẽ chuyển `InvalidOrderException` thành HTTP 400 mà không có cấu hình/kiểm thử.

## 15. Messaging và serverless: tránh poison message bị retry vô hạn

Message sai cú pháp JSON có thể bị từ chối **trước khi Function chạy** tại converter. Message hợp lệ về kiểu nhưng quantity bằng 0 có thể gây `InvalidOrderException` từ nghiệp vụ. Database timeout là lỗi hạ tầng khác hẳn.

~~~text
Broker event
    |
    v
Deserialize --- sai schema ---> adapter error policy
    |
    v
Validate  ------ invalid -----> reject / DLQ / quarantine
    |
    v
Business & Persist --- timeout ---> retry có điều kiện
    |
    v
Ack theo binder
~~~

Một **poison message** liên tục gây lỗi không thể sửa bằng retry giống hệt. Cấu hình retry vô hạn có thể gây vòng lặp xử lý lỗi hoặc chặn thông điệp hợp lệ.

| Lỗi | Retry cùng payload? | Xử lý tham khảo |
|---|---|---|
| Deserialize sai schema | Thường không | DLQ/quarantine |
| Validation sai | Thường không | Lưu lỗi, quan sát |
| Authorization không hợp lệ | Không dùng retry để bỏ qua security | Từ chối |
| Timeout database | Có thể nếu idempotent | Retry giới hạn/backoff |
| Mất ack sau DB commit | Có thể có redelivery | Idempotency tại storage |
| Lỗi không rõ nguyên nhân | Tùy phân loại | Điều tra, circuit breaker/DLQ |

Khả năng DLQ, cách ack, retry và binding tùy binder, broker, phiên bản và cấu hình. `onError` của Reactor không tự đồng nghĩa với một hành động nack cụ thể: cần xem adapter có quan sát được error signal theo đúng vòng đời hay không.

### 15.1. Serverless có cùng hai loại lỗi

Một invocation có thể ném exception ngay khi handler kiểm tra input, hoặc trả Publisher/giá trị bất đồng bộ rồi thất bại trong quá trình thực thi (nếu adapter hỗ trợ). Có trường hợp dữ liệu đã commit nhưng invocation timeout trước khi phản hồi.

Nền tảng có thể retry theo trigger cụ thể. Không nên giả định mọi môi trường serverless xử lý `onError` giống nhau hoặc có exactly-once; cần kiểm thử handler và chính sách trigger thật.

## 16. Threading và blocking khi xử lý lỗi reactive

`Mono.fromCallable(...)` trì hoãn lời gọi nhưng **không tự đưa code sang thread khác**. Nếu Callable thực hiện JDBC blocking, nó có thể chặn thread subscriber hoặc event loop.

Một cách cô lập lời gọi blocking:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// blockingGateway là dependency minh họa do ứng dụng cung cấp.
Mono<String> result = Mono.fromCallable(
        () -> blockingGateway.load("ORD-42"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` thường thích hợp cho số lượng công việc blocking có giới hạn; nó không biến client blocking thành non-blocking hoặc thay thế timeout, connection pool và kiểm soát concurrency.

Nếu Callable ném exception thông thường ở scheduler đó, Reactor vẫn thường phát `onError`. `try/catch` quanh dòng tạo Mono không bắt được exception phát sinh bất đồng bộ.

Đừng dựa vào thread name để quyết định error handler; hãy ghi nhận exception cause, correlation ID và trách nhiệm xử lý tại đúng ranh giới.

### 16.1. Không tuyệt đối hóa quy tắc onError

Constructor, validation argument, null argument không hợp lệ trong API Reactor và code chạy trước return vẫn có thể ném ngay. Một số lỗi fatal/JVM không bình thường cũng có quy tắc đặc biệt. Vì vậy cần kiểm tra **vị trí thực thi** thay vì coi tất cả `Throwable` trong code reactive là `onError`.

## 17. Unit test: đúng loại lỗi và đúng thời điểm

Để kiểm tra Reactor, nên thêm dependency `reactor-test` và dùng `StepVerifier`, ví dụ với Maven:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Cần thêm JUnit/Spring Boot Test và Reactor tương thích với dự án. `StepVerifier` đóng vai trò subscriber, giúp kiểm tra **tín hiệu thực tế**, không chỉ việc tạo một Publisher.

### 17.1. Ngoại lệ trực tiếp từ Function

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

class ImmediateExceptionTest {

    @Test
    void imperativeFunctionThrowsAtApply() {
        Function<OrderInput, Quote> quoteOne =
                new QuoteFunctions().quoteOne();

        assertThrows(InvalidOrderException.class,
                () -> quoteOne.apply(
                    new OrderInput("ORD-42", 0)));
    }
}
~~~

Test không cần Spring context hoặc Publisher; exception được ném ngay trong `quoteOne.apply(...)`.

### 17.2. Lỗi của mapper xuất hiện qua onError

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import example.functions.QuoteModels.OrderInput;
import example.functions.QuoteModels.Quote;

class ReactiveErrorSignalTest {

    @Test
    void mapperFailureIsOnError() {
        QuoteFunctions config = new QuoteFunctions();

        Function<Flux<OrderInput>, Flux<Quote>> stream =
                config.quoteStream(config.quoteOne());

        Flux<Quote> result = stream.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 0),
                new OrderInput("ORD-44", 3)));

        assertNotNull(result);

        StepVerifier.create(result)
                .expectNext(new Quote("ORD-42", 250_000L))
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
~~~

`ORD-44` không được xử lý tiếp theo cách mặc định, vì `ORD-43` gây một terminal error sau khi đã phát kết quả của `ORD-42`.

### 17.3. So sánh Mono.just và Mono.fromCallable

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class EagerDeferredTest {

    @Test
    void eagerParsingThrowsBeforeMonoExists() {
        Function<String, Mono<Integer>> eager =
                value -> Mono.just(Integer.parseInt(value));

        assertThrows(NumberFormatException.class,
                () -> eager.apply("bad"));
    }

    @Test
    void deferredParsingSignalsError() {
        Function<String, Mono<Integer>> deferred =
                value -> Mono.fromCallable(
                    () -> Integer.parseInt(value));

        Mono<Integer> result = assertDoesNotThrow(
                () -> deferred.apply("bad"));

        StepVerifier.create(result)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

Hai test đều dùng `Integer.parseInt("bad")`, nhưng chứng minh **hai thời điểm báo lỗi khác nhau**.

## 18. Kiểm thử retry và side effect

### 18.1. Chỉ retry lỗi transient

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetryErrorTest {

    @Test
    void transientFailureIsRetried() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<Integer> remote = Mono.fromCallable(() -> {
            if (attempts.incrementAndGet() < 3) {
                throw new TemporaryDependencyException(
                    "Temporary failure");
            }
            return 42;
        });

        StepVerifier.create(remote.retryWhen(
                Retry.max(2).filter(error ->
                    error instanceof TemporaryDependencyException)))
                .expectNext(42)
                .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void validationFailureIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<Integer> rejected = Mono.fromCallable(() -> {
            attempts.incrementAndGet();
            throw new InvalidOrderException("Invalid input");
        });

        StepVerifier.create(rejected.retryWhen(
                Retry.max(2).filter(error ->
                    error instanceof TemporaryDependencyException)))
                .expectError(InvalidOrderException.class)
                .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Các exception ở đây là lớp `InvalidOrderException` và `TemporaryDependencyException` đã định nghĩa trước đó. `Retry.max(2)` cho tối đa hai lần thử lại, không có nghĩa luôn phải dùng hết.

### 18.2. onError không tự rollback tác dụng phụ

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class SideEffectAfterErrorTest {

    @Test
    void previousWriteIsNotUndone() {
        List<Integer> saved = new CopyOnWriteArrayList<>();

        Flux<Integer> stream =
                Flux.just("1", "bad", "3")
                    .map(Integer::parseInt)
                    .doOnNext(saved::add);

        StepVerifier.create(stream)
                .expectNext(1)
                .expectError(NumberFormatException.class)
                .verify();

        assertEquals(List.of(1), saved);
    }
}
~~~

`doOnNext` chỉ đóng vai trò side effect thử nghiệm. Đối với database production, cần transaction, idempotency và cách xử lý retry riêng, không dựa vào `onError` để hoàn tác.

## 19. Integration test với FunctionCatalog

Unit test một Function chưa kiểm tra được Spring đã đăng ký bean và ghép đúng tên hay chưa. Một ứng dụng Spring Boot tối thiểu trong package `example.functions`:

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

Khi class `QuoteApplication`, `QuoteFunctions` và dependency Spring Cloud Function có trong context, ta kiểm tra pipeline bằng `StepVerifier`:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import example.functions.QuoteModels.OrderInput;

@SpringBootTest(classes = QuoteApplication.class)
class QuoteCatalogErrorTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedCompositionEmitsValuesAndCompletes() {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                    "quoteStream|formatQuoteStream");

        assertNotNull(pipeline);

        StepVerifier.create(pipeline.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 3))))
                .expectNext("ORD-42=250000", "ORD-43=375000")
                .verifyComplete();
    }

    @Test
    void invalidOrderBecomesReactiveErrorSignal() {
        Function<Flux<OrderInput>, Flux<String>> pipeline =
                catalog.lookup(
                    "quoteStream|formatQuoteStream");

        assertNotNull(pipeline);

        StepVerifier.create(pipeline.apply(Flux.just(
                new OrderInput("ORD-42", 2),
                new OrderInput("ORD-43", 0))))
                .expectNext("ORD-42=250000")
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
~~~

Bộ test chứng minh việc đăng ký tên, kết nối kiểu, biến đổi kết quả và phát lỗi khi subscription chạy trong Spring context. Nó **không thay thế** test ở ranh giới HTTP, message hoặc serverless.

### 19.1. Test catalog thành công nhưng adapter vẫn lỗi

Những nguyên nhân có thể gồm:

- Adapter cấp `Message<OrderInput>` trong khi pipeline đòi `Flux<OrderInput>`.
- Converter không deserialize được JSON vào `OrderInput`.
- Adapter subscribe hoặc quản lý lifecycle khác kỳ vọng.
- Headers hoặc content-type không phù hợp.
- Error signal không được chuyển thành response/ack/retry như thiết kế.
- Khả năng tự adaptation imperative/reactive thay đổi theo phiên bản.

Vì vậy, khi chuyển cùng Function sang adapter khác, cần kiểm thử payload thật, subscription, error mapping và cơ chế xác nhận.

## 20. Chẩn đoán và quan sát lỗi

### 20.1. Các tình huống dễ nhầm

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `assertThrows` bao quanh `apply` không bắt lỗi | Mapper chạy lúc subscribe | Dùng `StepVerifier.expectError` |
| `Mono.just(parse(...))` ném ngay | Java tính đối số trước khi gọi `just` | Cân nhắc `fromCallable` hoặc `defer` |
| `doOnError` ghi log nhưng subscriber vẫn thấy lỗi | Operator chỉ quan sát | Chọn rõ phục hồi hay chuyển lỗi lên adapter |
| `onErrorResume` không xử lý phần tử sau lỗi | Nó thay toàn bộ phần còn lại bằng fallback | Thiết kế ranh giới lỗi từng phần tử |
| `retry` làm ghi trùng | Subscribe lại upstream có side effect | Dùng idempotency/transaction |
| `lookup` được nhưng chưa xử lý dữ liệu | Chưa subscribe hoặc adapter chưa kích hoạt | Test tín hiệu/adapter thực tế |
| Không có HTTP 400 với input sai | Error handler/adapter mapping chưa đúng | Test status và response |
| Broker lặp poison message | Retry không phân biệt lỗi cố định | Giới hạn retry, DLQ/quarantine |
| DB đã commit nhưng pipeline báo lỗi | Lỗi xảy ra sau commit | Kiểm tra transaction, ack và data state |
| Thread bị chặn | Blocking I/O chạy trên scheduler không phù hợp | Đo latency, thread/scheduler và connection pool |

### 20.2. Observability ở đúng ranh giới

Nên ghi nhận các thông tin có thể đối chiếu:

- Correlation ID/message ID tin cậy và tên pipeline.
- Bước xử lý thất bại và loại lỗi.
- Error category: invalid input, conflict, transient dependency, unexpected.
- Số lần retry, thời gian xử lý và trạng thái commit/ack nếu biết được.
- Message vào dead-letter hoặc quarantine, cùng tỷ lệ xử lý thành công sau retry.

Không log toàn bộ payload nhạy cảm hoặc token chỉ để debug. Khi Reactor chuyển scheduler, `ThreadLocal` truyền thống có thể không giữ context như dự kiến; cần dùng cách truyền context/observability phù hợp với phiên bản framework.

### 20.3. Checklist trước production

1. `Function.apply` có thể ném lỗi trước khi trả Mono/Flux không?
2. Mapper nào chỉ chạy khi có subscription?
3. Ai subscribe Publisher, và ai nhận `onError` terminal?
4. Có dùng `onErrorMap`, `onErrorResume` hoặc truyền lỗi lên adapter đúng không?
5. Retry có giới hạn và lọc đúng loại lỗi chưa?
6. Resubscription có thể kích hoạt lại việc ghi dữ liệu không?
7. Có idempotency key, uniqueness và transaction ở storage không?
8. Validation có chạy trước side effect không?
9. Một lỗi trong Flux có chặn các phần tử phía sau không?
10. HTTP status, message ack/DLQ và serverless retry đã được test trên adapter thật chưa?
11. Blocking I/O có được cô lập và giới hạn concurrency phù hợp không?
12. Các test có kiểm tra **cả direct throw và onError** không?

## 21. Bài tập thực hành

**Bài 1 — Lỗi xảy ra khi nào?** So sánh `Mono.just(Integer.parseInt("bad"))` và `Mono.fromCallable(() -> Integer.parseInt("bad"))`. Ở pha nào exception được quan sát?

**Bài 2 — try/catch.** Vì sao `try/catch` quanh `parseMono.apply(Mono.just("bad"))` có thể không bắt lỗi? Hãy viết một assertion `StepVerifier` phù hợp.

**Bài 3 — Flux terminal.** Với `Flux.just("2","bad","9").map(Integer::parseInt)`, các tín hiệu nào được phát? Phần tử `9` có còn không?

**Bài 4 — onErrorResume.** Thêm `onErrorResume(ex -> Flux.just(-1))` vào bài 3. Mô tả kết quả và giải thích vì sao không có `9`.

**Bài 5 — Per-message.** Thiết kế xử lý `"2"`, `"bad"` và `"9"` để hai phần tử hợp lệ vẫn được phát. Việc bỏ qua message sai cần bổ sung chính sách nào?

**Bài 6 — Retry.** Vì sao `Flux.just("1","bad").map(Integer::parseInt).retry(1)` có thể phát `1` hai lần? Nếu có ghi database sau `map`, cần bảo vệ ra sao?

**Bài 7 — Composition.** Cho `quoteOne: Function<OrderInput,Quote>` và `formatQuoteStream: Function<Flux<Quote>,Flux<String>>`. Vì sao Java `andThen` không nối trực tiếp? Đề xuất một bridge.

**Bài 8 — Phân loại lỗi.** Một message có quantity `0`, message khác gặp database timeout **sau commit**. Có nên xử lý retry và ack giống nhau không?

**Bài 9 — Kiểm thử.** Đề xuất một test `assertThrows`, một test `StepVerifier`, một test retry có filter và một integration test catalog; nêu mục tiêu từng test.

**Bài 10 — Side effect.** Một Flux đã ghi hai báo giá rồi lỗi ở phần tử thứ ba. Vì sao downstream nhận `onError` không có nghĩa database rollback hai bản ghi đầu?

### Gợi ý đáp án

- **Bài 1:** `Mono.just(parse(...))` tính đối số ngay; `fromCallable` chuyển lỗi thường sang `onError` khi subscribe.
- **Bài 2:** `map` lazy; dùng `StepVerifier.create(publisher).expectError(NumberFormatException.class).verify()`.
- **Bài 3:** `onNext(2)` rồi `onError(NumberFormatException)`; `9` không được phát.
- **Bài 4:** `2` rồi `-1` rồi complete; fallback không tiếp tục upstream.
- **Bài 5:** Dùng inner `Mono.fromCallable(...).onErrorResume(...)` trong `concatMap` và cách ly/ghi nhận message sai.
- **Bài 6:** Retry resubscribe upstream; dùng idempotency key, transaction, giới hạn retry.
- **Bài 7:** `Quote` khác `Flux<Quote>`; tạo `quoteStream: Function<Flux<OrderInput>,Flux<Quote>>` qua `flux.map(quoteOne)`.
- **Bài 8:** Validation thường không retry; timeout sau commit cần kiểm tra/idempotency chống trùng.
- **Bài 9:** Direct throw test kiểm tra call stack; StepVerifier kiểm tra error signal; retry test số lần thử; catalog test tên/kiểu và kết quả.
- **Bài 10:** Reactor không tự rollback DB; thiết kế transaction ở ranh giới thích hợp, idempotency và xử lý delivery.

## 22. Ghi nhớ

- Hàm Java đồng bộ có thể ném exception **ngay khi gọi `Function.apply`**.
- Trong Reactor `map`, `flatMap`, `fromCallable` hoặc `defer`, lỗi thông thường trong callback thường phát qua **`onError` khi subscribe**.
- `Mono.just(calculate())` có thể ném trực tiếp vì Java tính `calculate()` trước khi tạo Mono.
- `onError` là tín hiệu terminal, không phải phần tử `T` và không tự rollback side effect đã commit.
- `onErrorResume` chuyển sang fallback; `doOnError` chỉ quan sát; `retry`/`retryWhen` subscribe lại upstream và có thể xử lý lặp.
- `FunctionCatalog` và `spring.cloud.function.definition` giúp ghép/chọn hàm, không tự quyết định HTTP error mapping, binder ack, DLQ, transaction hay serverless retry.
- Test `assertThrows`, `StepVerifier`, FunctionCatalog và adapter ở **đúng tầng** để xác minh hành vi lỗi thực tế.







