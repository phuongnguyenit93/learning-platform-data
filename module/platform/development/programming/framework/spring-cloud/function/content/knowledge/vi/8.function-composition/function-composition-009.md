# Ghép hàm đồng bộ với hàm phản ứng

## 1. Giới thiệu

Spring Cloud Function giúp phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function` và `Consumer`, độc lập với cách gọi qua HTTP, sự kiện hoặc môi trường serverless. Khi xây dựng pipeline, đôi khi một bước xử lý từng giá trị theo phong cách Java đồng bộ (**imperative**), trong khi bước khác xử lý cả một dòng dữ liệu bất đồng bộ theo Reactor (**reactive**).

Ví dụ một ứng dụng đã có hàm chuẩn hóa mã sản phẩm:

~~~java
Function<String, String> normalizeSku =
        sku -> sku.trim().toUpperCase(Locale.ROOT);
~~~

Ứng dụng mới cần xử lý nhiều mã:

~~~java
Function<Flux<String>, Flux<Integer>> measureLengths =
        flux -> flux.map(String::length);
~~~

Nếu chỉ nối hai hàm bằng `andThen`, hợp đồng kiểu sẽ không khớp: `String` không phải `Flux<String>`. Nhưng Spring Cloud Function và Reactor cung cấp các cơ chế để tái sử dụng logic cũ trong pipeline reactive.

Bài học thuộc chương **Ghép hàm** và tập trung vào:

- Nhận biết sự khác biệt giữa Function đồng bộ và Function nhận/trả `Mono` hoặc `Flux`.
- Hiểu tại sao việc ghép trực tiếp bằng Java generic có thể không hợp lệ.
- Dùng `map` hoặc `flatMap` để tạo bridge reactive tường minh.
- Biết vai trò của `FunctionCatalog.lookup` và `spring.cloud.function.definition`.
- Phân tích subscription, backpressure, thứ tự phần tử, lỗi và nguy cơ blocking.
- Viết kiểm thử JUnit 5 cùng `StepVerifier`.

> **Lưu ý phiên bản:** Spring Cloud Function có cơ chế composition và adaptation khi tra cứu hàm qua catalog. Mức hỗ trợ ghép tự động giữa imperative/reactive có thể phụ thuộc phiên bản và adapter. Bài này ưu tiên **bridge tường minh** để kiểu Java rõ ràng, dễ kiểm thử; các biến thể mixed composition ngầm phải được kiểm chứng trên runtime thực tế.

## 2. Hợp đồng của hàm đồng bộ

Một `Function<T,R>` tiêu chuẩn nhận một giá trị kiểu `T`, trả một giá trị `R` bằng `apply`:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> normalize =
        input -> input.trim().toUpperCase(Locale.ROOT);

System.out.println(normalize.apply(" sku-42 "));
// SKU-42
~~~

Trong ví dụ, xử lý được thực hiện ngay khi gọi `apply` và trả về một `String`. Một Function như vậy dễ unit test và tái sử dụng trong một request hoặc một bước xử lý.

Tuy nhiên, chữ ký `Function<T,R>` **không bảo đảm** bên trong luôn non-blocking: implementation có thể truy vấn JDBC, gọi API đồng bộ hoặc thực hiện thao tác tốn CPU. Tính chất đồng bộ hay blocking phải được đánh giá dựa trên công việc thực tế.

## 3. Hợp đồng của hàm phản ứng

Reactor cung cấp `Mono<T>` và `Flux<T>`, là các kiểu Publisher thường dùng trong hệ sinh thái Spring.

- `Mono<T>` biểu diễn 0 hoặc 1 phần tử, hoặc một tín hiệu lỗi.
- `Flux<T>` biểu diễn 0 đến nhiều phần tử, hoặc một tín hiệu lỗi.
- Cả hai thường cung cấp các operator như `map`, `filter` và `flatMap` để xây dựng luồng dữ liệu theo cách khai báo.

Ví dụ:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<Integer>> lengths =
        flux -> flux
                .map(String::trim)
                .map(String::length);
~~~

Hợp đồng là `Flux<String> → Flux<Integer>`. Không được nhầm với `Function<String,Integer>`.

| Giao diện/hợp đồng | Input của `apply` | Output của `apply` |
|---|---|---|
| `Function<String,Integer>` | Một `String` | Một `Integer` |
| `Function<Mono<String>,Mono<Integer>>` | Một `Mono<String>` | Một `Mono<Integer>` |
| `Function<Flux<String>,Flux<Integer>>` | Một `Flux<String>` | Một `Flux<Integer>` |

### 3.1. Lời gọi apply có thể mới chỉ xây dựng Publisher

~~~java
Flux<Integer> result =
        lengths.apply(Flux.just("  ab ", " cde "));
~~~

Trong trường hợp sử dụng các operator Reactor lười như `map`, phép biến đổi trên từng phần tử thường xảy ra **khi có subscription**, không nhất thiết ngay tại lời gọi `apply`.

Để thử trong chương trình đồng bộ:

~~~java
import java.util.List;

List<Integer> values = result.collectList().block();
System.out.println(values); // [2, 3]
~~~

`block()` ở đây dùng để minh họa trong chương trình/kiểm thử; không nên chặn luồng reactive đang xử lý request hoặc sự kiện.

## 4. Vì sao không thể dùng andThen trực tiếp?

Giả sử:

~~~java
Function<String, String> normalize = String::trim;

Function<Flux<String>, Flux<Integer>> measure =
        flux -> flux.map(String::length);
~~~

Phép ghép Java sau không biên dịch:

~~~java
// Sai: normalize trả String,
// nhưng measure cần Flux<String>.
// var invalid = normalize.andThen(measure);
~~~

`Function.andThen` chỉ hợp lệ khi kiểu đầu ra của hàm trước có thể được truyền làm đầu vào của hàm sau.

~~~text
normalize:  String       → String
measure:   Flux<String> → Flux<Integer>

String khác Flux<String> → điểm nối không tương thích.
~~~

Đảo thứ tự cũng không giải quyết được:

~~~java
Function<Integer, String> describe =
        value -> "length=" + value;

// Sai: measure trả Flux<Integer>,
// describe lại nhận Integer.
// var invalid = measure.andThen(describe);
~~~

**Không nên dùng raw type, ép `Object` hoặc cast tùy tiện** để bỏ qua kiểm tra generic. Thay vì vậy, hãy chuyển function đồng bộ thành một bước xử lý trên từng phần tử trong Mono/Flux.

## 5. Nâng một Function đồng bộ lên Flux bằng map

Cho:

~~~java
import java.util.Locale;

Function<String, String> normalize =
        sku -> sku.trim().toUpperCase(Locale.ROOT);
~~~

Tạo một Function có hợp đồng reactive:

~~~java
Function<Flux<String>, Flux<String>> normalizeStream =
        flux -> flux.map(normalize);
~~~

Sau đó nối với một Function reactive khác:

~~~java
Function<Flux<String>, Flux<Integer>> measureStream =
        flux -> flux.map(String::length);

Function<Flux<String>, Flux<Integer>> pipeline =
        normalizeStream.andThen(measureStream);
~~~

Sơ đồ:

~~~text
Flux<String>               Flux<String>          Flux<Integer>
" sku-42 " --normalizeStream--> "SKU-42" --measureStream--> 6
" sku-7 "  --normalizeStream--> "SKU-7"  --measureStream--> 5
~~~

Một lần thử:

~~~java
List<Integer> values = pipeline
        .apply(Flux.just(" sku-42 ", " sku-7 "))
        .collectList()
        .block();

System.out.println(values); // [6, 5]
~~~

`Flux.map` áp dụng một `Function<T,R>` cho từng phần tử và giữ cấu trúc luồng. Đây là bridge tự nhiên với các phép biến đổi đồng bộ **nhanh, không chặn**.

### 5.1. Tạo helper liftFlux có generic

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public final class ReactiveAdapters {

    private ReactiveAdapters() {}

    public static <T, R> Function<Flux<T>, Flux<R>> liftFlux(
            Function<? super T, ? extends R> mapper) {

        return flux -> flux.map(mapper);
    }
}
~~~

Dùng helper:

~~~java
Function<String, String> trim = String::trim;
Function<String, Integer> count = String::length;

Function<Flux<String>, Flux<String>> trimFlux =
        ReactiveAdapters.liftFlux(trim);

Function<Flux<String>, Flux<Integer>> countFlux =
        ReactiveAdapters.liftFlux(count);

Function<Flux<String>, Flux<Integer>> pipeline =
        trimFlux.andThen(countFlux);
~~~

Không có bước nào phải cast `Flux` sang `String`. Trình biên dịch Java kiểm tra đúng hợp đồng từ `Flux<String>` qua `Flux<Integer>`.

### 5.2. Logic đồng bộ được dùng ở đâu?

Hàm `trim` vẫn có thể gọi riêng:

~~~java
String single = trim.apply("  abc  "); // "abc"
~~~

Hàm `trimFlux` dùng lại đúng quy tắc đó cho nhiều phần tử. Lợi ích là **không nhân đôi nghiệp vụ**, trong khi pipeline vẫn thể hiện rõ dữ liệu được xử lý theo kiểu reactive.

## 6. Khi hàm reactive đứng trước hàm đồng bộ

Ví dụ:

~~~java
Function<Flux<String>, Flux<String>> sanitize =
        flux -> flux.map(String::trim)
                    .filter(text -> !text.isBlank());

Function<String, Integer> lengthOne =
        String::length;
~~~

Cách viết `sanitize.andThen(lengthOne)` không khớp kiểu vì `sanitize` trả `Flux<String>`, còn `lengthOne` nhận `String`.

Sửa bằng cách tạo bridge ở **bước sau**:

~~~java
Function<Flux<String>, Flux<Integer>> lengthStream =
        flux -> flux.map(lengthOne);

Function<Flux<String>, Flux<Integer>> pipeline =
        sanitize.andThen(lengthStream);
~~~

Công thức chung:

~~~text
Reactive trước: Function<Flux<A>, Flux<B>>
Imperative sau: Function<B, C>

Bridge sau:     Function<Flux<B>, Flux<C>>
Kết quả:        Function<Flux<A>, Flux<C>>
~~~

Cho dù imperative đặt trước hay sau, điểm nối luôn phải phù hợp **toàn bộ kiểu**.

## 7. Ví dụ Spring Cloud Function: xử lý mã SKU

Giả sử hệ thống nhận một luồng mã sản phẩm, cần:

1. Chuẩn hóa từng mã bằng Java đồng bộ.
2. Xác thực mã dưới dạng luồng reactive.
3. Định dạng kết quả thành chuỗi gửi cho bên nhận.

Một pipeline rõ ràng:

~~~text
Flux<String>
     |
     v
normalizeSkuStream   Flux<String> → Flux<String>
     |
     v
validateSkuStream    Flux<String> → Flux<Sku>
     |
     v
formatSkuStream      Flux<Sku> → Flux<String>
     |
     v
Flux<String>
~~~

### 7.1. Khai báo các bean

Ví dụ Java 17 trở lên:

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration
public class SkuFunctions {

    public record Sku(String code) {}

    // Hàm nghiệp vụ đồng bộ vẫn tái sử dụng độc lập.
    @Bean
    public Function<String, String> normalizeSku() {
        return sku -> sku.trim().toUpperCase(Locale.ROOT);
    }

    // Bridge: áp dụng normalizeSku cho từng phần tử Flux.
    @Bean
    public Function<Flux<String>, Flux<String>> normalizeSkuStream(
            @Qualifier("normalizeSku")
            Function<String, String> normalizeSku) {

        return flux -> flux.map(normalizeSku);
    }

    @Bean
    public Function<Flux<String>, Flux<Sku>> validateSkuStream() {
        return flux -> flux.map(code -> {
            if (!code.matches("SKU-[0-9]+")) {
                throw new IllegalArgumentException(
                        "Ma SKU khong hop le: " + code);
            }
            return new Sku(code);
        });
    }

    @Bean
    public Function<Flux<Sku>, Flux<String>> formatSkuStream() {
        return flux -> flux.map(
                sku -> "accepted:" + sku.code());
    }
}
~~~

Tên bean mặc định là `normalizeSku`, `normalizeSkuStream`, `validateSkuStream` và `formatSkuStream`. Trong Spring Cloud Function, các bean Function có thể được đăng ký vào `FunctionCatalog`, miễn ứng dụng cấu hình và component scan phù hợp.

| Bean | Kiểu | Vai trò |
|---|---|---|
| `normalizeSku` | `String → String` | Quy tắc imperative tái sử dụng |
| `normalizeSkuStream` | `Flux<String> → Flux<String>` | Bridge `map` |
| `validateSkuStream` | `Flux<String> → Flux<Sku>` | Xác thực và tạo record |
| `formatSkuStream` | `Flux<Sku> → Flux<String>` | Chuẩn bị kết quả |

Những bean này không chứa tên endpoint, topic broker hay handler serverless.

### 7.2. Tra cứu composition bằng FunctionCatalog

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class SkuPipelineService {

    private final FunctionCatalog catalog;

    public SkuPipelineService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Flux<String> process(Flux<String> input) {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay pipeline SKU");
        }

        return pipeline.apply(input);
    }
}
~~~

Nếu truyền vào `Flux.just(" sku-42 ", " sku-7 ")`, pipeline dự kiến phát:

~~~text
accepted:SKU-42
accepted:SKU-7
~~~

Lưu ý rằng lời gọi `process(...)` trả một Publisher; nó không tự gửi dữ liệu tới client/broker. Bên dùng Publisher hoặc adapter sẽ điều phối subscription.

### 7.3. Chọn pipeline bằng spring.cloud.function.definition

Trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSkuStream|validateSkuStream|formatSkuStream"
~~~

Trong `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeSkuStream|validateSkuStream|formatSkuStream
~~~

Property này chọn **tên pipeline** cho phần tích hợp. Nó không tự tạo endpoint HTTP hoặc binding sự kiện. Để chạy qua transport thực tế, cần adapter, dependency, chuyển đổi payload và cấu hình phù hợp.

## 8. Mixed composition tự động của FunctionCatalog: cần kiểm chứng

Trong một số phiên bản/tình huống, Spring Cloud Function hỗ trợ **thích ứng** khi ghép function imperative và reactive qua `FunctionCatalog`.

Ví dụ ý định:

~~~text
normalizeSku:      Function<String, String>
validateSkuStream: Function<Flux<String>, Flux<Sku>>

Biểu thức tên: "normalizeSku|validateSkuStream"
~~~

Đừng suy từ cú pháp rằng biểu thức trên chắc chắn trả `Function<Flux<String>,Flux<Sku>>` trong mọi phiên bản/adapter. Kiểu wrapper và cách adaptation phụ thuộc phiên bản, cấu hình và ngữ cảnh invocation.

**Cách kiểm soát tốt hơn:** đăng ký bridge `normalizeSkuStream` tường minh như mục 7 rồi dùng `"normalizeSkuStream|validateSkuStream"`. Pipeline có hợp đồng Flux nhất quán, có thể được compiler kiểm tra và dễ viết test.

Nếu dự án chủ ý dựa vào adaptation tự động, cần có integration test trên runtime thật để xác minh:

- Hàm được catalog tra cứu thành công.
- Đầu vào/đầu ra thực tế đúng kiểu và đúng số phần tử.
- Hàm imperative chạy đúng thứ tự và số lần.
- Ngoại lệ và tín hiệu `onError` được xử lý đúng.
- Headers/payload vẫn đúng nếu adapter sử dụng `Message`.

Thành công của bridge tường minh **không chứng minh** mixed composition ngầm chắc chắn hành xử tương tự.

## 9. Dùng Mono khi chỉ có một kết quả reactive

Với nguồn tạo tối đa một phần tử, `Mono<T>` thường phù hợp hơn `Flux<T>`.

~~~java
import java.util.function.Function;
import reactor.core.publisher.Mono;

record Order(String id, int quantity) {}
record Receipt(String orderId, long totalVnd) {}

Function<Order, Receipt> priceOne =
        order -> new Receipt(
                order.id(),
                order.quantity() * 125_000L);

Function<Mono<Order>, Mono<Receipt>> priceMono =
        mono -> mono.map(priceOne);
~~~

Hợp đồng:

~~~text
Mono<Order> → map(Function<Order,Receipt>) → Mono<Receipt>
~~~

Ví dụ:

~~~java
Mono<Receipt> result =
        priceMono.apply(
                Mono.just(new Order("ORD-42", 2)));
~~~

Có thể kiểm tra kết quả bằng `StepVerifier` hoặc `block()` ở môi trường thử nghiệm đồng bộ. Không nên block trong một chuỗi WebFlux đang phục vụ request.

### 9.1. Phân biệt map và flatMap

Khi một Function trả **giá trị thường** `Receipt`, dùng `map`.

Khi một Function trả `Mono<Receipt>`:

~~~java
Function<Order, Mono<Receipt>> priceAsync =
        order -> Mono.just(new Receipt(
                order.id(),
                order.quantity() * 125_000L));
~~~

thì cần `flatMap` nếu muốn đầu ra cuối vẫn là `Mono<Receipt>`:

~~~java
Function<Mono<Order>, Mono<Receipt>> pricePipeline =
        mono -> mono.flatMap(priceAsync);
~~~

Nếu dùng `mono.map(priceAsync)`, kiểu đầu ra là `Mono<Mono<Receipt>>`. Đây là lỗi dễ gặp khi trộn code trả giá trị thường với code trả Publisher.

### 9.2. Null không đồng nhất với luồng rỗng

`Mono.just(null)` không hợp lệ. Khi giá trị có thể là `null`, có thể dùng `Mono.justOrEmpty(value)` để biểu diễn 0 hoặc 1 phần tử.

~~~java
String maybeMissing = null;
Mono<String> value = Mono.justOrEmpty(maybeMissing);
~~~

Tuy nhiên, một `Mono.empty()` không tự đảm bảo mọi HTTP/message adapter sẽ xử lý thành status hoặc “không phát message” giống nhau. Cần kiểm thử tại ranh giới thực tế.

## 10. Ngoại lệ: ngay trong apply hay thành onError?

### 10.1. Function đồng bộ có thể ném lỗi trực tiếp

~~~java
Function<String, Integer> parse = Integer::parseInt;

// parse.apply("bad") ném NumberFormatException ngay.
~~~

Đưa Function đó vào Flux:

~~~java
Function<Flux<String>, Flux<Integer>> parseAll =
        flux -> flux.map(Integer::parseInt);

Flux<Integer> numbers =
        parseAll.apply(Flux.just("10", "bad", "30"));
~~~

Khi subscriber yêu cầu dữ liệu, `10` được phát, `"bad"` gây `NumberFormatException` và Reactor biến lỗi mapper thành tín hiệu `onError`. Luồng dừng theo mặc định, nên `30` không tiếp tục được phát.

### 10.2. try/catch ngoài apply có thể không bắt lỗi trên từng phần tử

~~~java
try {
    Flux<Integer> values =
            parseAll.apply(Flux.just("bad"));
    // Chỉ tạo Publisher, mapper có thể chưa chạy.
} catch (NumberFormatException ex) {
    // Không đảm bảo bắt được lỗi phát sinh lúc subscribe.
}
~~~

Cần dùng operator Reactor hoặc kiểm thử error signal:

~~~java
Flux<Integer> safe =
        parseAll.apply(Flux.just("10", "bad", "30"))
                .onErrorResume(ex -> Flux.just(-1));
~~~

Trong ví dụ, kết quả là `10` rồi `-1`. `onErrorResume` thay thế **phần luồng sau lỗi** bằng fallback, không tự quay về xử lý `"30"`.

### 10.3. Trường hợp Function ném lỗi khi đang tạo Publisher

~~~java
Function<Flux<String>, Flux<String>> brokenFactory = flux -> {
    throw new IllegalStateException("Khong tao duoc Flux");
};
~~~

Ngoại lệ trong trường hợp này xảy ra ngay tại `brokenFactory.apply(...)`. Nó khác lỗi phát sinh bên trong `map` khi subscription. Khi thiết kế chính sách retry, đừng giả định mọi lỗi đều ở cùng một kênh.

## 11. Blocking I/O vẫn blocking dù nằm trong reactive map

Một Function đơn giản như chuẩn hóa chuỗi thường thích hợp đặt trong `map`. Nhưng Function gọi JDBC blocking là trường hợp khác:

~~~java
// Mã khái niệm: repository là dependency được ứng dụng cung cấp.
Function<String, Customer> loadCustomerBlocking =
        id -> repository.loadById(id);
~~~

`Customer` và `repository` trong ví dụ này là các kiểu/phụ thuộc nghiệp vụ cần khai báo thực tế.

Đưa `loadCustomerBlocking` vào `flux.map(...)` **không biến truy vấn blocking thành non-blocking**. Nếu chạy trên event-loop, thao tác chặn có thể gây nghẽn nhiều request.

Một cách cô lập lời gọi blocking trong Reactor là:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Function<String, Mono<Customer>> loadCustomer =
        id -> Mono.fromCallable(
                    () -> loadCustomerBlocking.apply(id))
                .subscribeOn(Schedulers.boundedElastic());
~~~

Với nhiều ID:

~~~java
Function<Flux<String>, Flux<Customer>> loadAll =
        flux -> flux.flatMap(loadCustomer);
~~~

Đây là giải pháp quản lý thread cho I/O blocking, không tự làm database client trở thành reactive. Cần giới hạn concurrency, quản lý connection pool, timeout và retry phù hợp.

## 12. Thứ tự phần tử trong pipeline reactive

Dấu `|` xác định thứ tự **các bước Function**, không mặc định bảo đảm thứ tự **mọi phần tử đầu ra** khi xử lý bất đồng bộ.

~~~text
Bước A | Bước B  = A tạo dữ liệu cho B

Phần tử 1, 2, 3  có thể xử lý đồng thời nếu dùng flatMap.
~~~

- `map` đồng bộ thường giữ thứ tự phần tử với nguồn có thứ tự.
- `flatMap` có thể chạy nhiều Publisher con đồng thời và phát kết quả xen kẽ.
- `concatMap` xử lý từng Publisher con theo thứ tự, không chạy đồng thời các Publisher con.
- `flatMapSequential` có thể xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn, với chi phí buffering.

Nếu nghiệp vụ yêu cầu các giao dịch được xử lý theo thứ tự, lựa chọn operator và chính sách concurrency quan trọng không kém thứ tự tên function.

### 12.1. Backpressure và luồng chậm

Reactive Streams cho phép subscriber biểu đạt demand. Tuy nhiên, không nên xem backpressure là giải pháp tự động cho mọi nguồn dữ liệu bên ngoài. Binder hoặc adapter có thể có chính sách buffering, polling, nhận message hoặc lỗi riêng.

Các câu hỏi cần kiểm tra gồm:

1. Bên nhận xử lý chậm thì nguồn có thể giảm tốc không?
2. Nếu dữ liệu được đệm, giới hạn bộ đệm và chính sách tràn là gì?
3. Khi một phần tử lỗi, cả luồng dừng hay từng phần tử được xử lý riêng?
4. Có cho phép nhiều tác vụ I/O đồng thời không?
5. Điều gì xảy ra khi subscription bị hủy?

## 13. Ghép với Message và headers

Trong hệ thống sự kiện, `Message<T>` chứa payload và headers. Một hàm nhận `Flux<Message<String>>` có hợp đồng khác với hàm nhận `Flux<String>`.

~~~text
Function<String, String>
Function<Flux<Message<String>>, Flux<Message<String>>>
~~~

Khi cần tái sử dụng Function imperative cho từng payload, có thể tạo bridge tường minh:

~~~java
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import reactor.core.publisher.Flux;

Function<String, String> normalize = String::trim;

Function<Flux<Message<String>>,
         Flux<Message<String>>> normalizeMessages =
        flux -> flux.map(message ->
                MessageBuilder
                        .withPayload(
                                normalize.apply(message.getPayload()))
                        .copyHeaders(message.getHeaders())
                        .build());
~~~

Đoạn này chủ động sao chép các headers trong Message mới. Nó không đảm bảo mọi header transport đều được giữ hoặc có ý nghĩa giống nhau khi adapter thay đổi. Với HTTP, Spring Cloud Stream và serverless, cần kiểm thử payload, content-type, correlation ID cùng lỗi chuyển đổi dữ liệu.

**Không** coi khả năng message conversion của Spring Cloud Function là lý do bỏ qua hợp đồng generic hoặc tự động hóa mọi chuyển đổi JSON/POJO.

## 14. Triển khai cùng logic qua HTTP, sự kiện và serverless

Pipeline `normalizeSkuStream|validateSkuStream|formatSkuStream` chỉ mô tả logic xử lý. Cách kết nối với thế giới bên ngoài do adapter quyết định:

| Môi trường | Cần thiết ngoài function bean | Điểm cần kiểm thử |
|---|---|---|
| Java nội bộ | Spring context hoặc các Function trực tiếp | Subscription, generic, thứ tự, lỗi |
| HTTP | Adapter Web và ánh xạ route/request | Body, response reactive, status lỗi |
| Sự kiện/messaging | Binder, binding, destination và converter | Headers, serialization, retry/ack |
| Serverless | Adapter/handler và cấu hình trigger | Event mapping, lỗi, cold start |

`spring.cloud.function.definition` chọn **pipeline theo tên**, không tự tạo HTTP endpoint hoặc cấu hình broker.

### 14.1. Khi nào không cần reactive?

Nếu nghiệp vụ chỉ tính toán một `Order` thành một `Quote` và không có luồng hay I/O bất đồng bộ, `Function<Order,Quote>` thường đơn giản hơn. Không chuyển mọi bước thành `Flux` chỉ để “đồng bộ phong cách” với adapter.

Dùng `map` như bridge khi cần tái sử dụng logic xử lý từng giá trị trong pipeline reactive; dùng Function reactive thực sự khi nghiệp vụ cần xử lý Publisher, phối hợp nhiều nguồn, backpressure hoặc các tác vụ bất đồng bộ.

## 15. Kiểm thử Java với StepVerifier

### 15.1. Unit test cho bridge và thứ tự

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class MixedCompositionTest {

    @Test
    void imperativeMapperRunsForEachElement() {
        Function<String, String> trim = String::trim;

        Function<Flux<String>, Flux<String>> trimStream =
                flux -> flux.map(trim);

        Function<Flux<String>, Flux<Integer>> lengths =
                flux -> flux.map(String::length);

        Function<Flux<String>, Flux<Integer>> pipeline =
                trimStream.andThen(lengths);

        StepVerifier.create(
                pipeline.apply(Flux.just("  ab ", " cde ")))
                .expectNext(2, 3)
                .verifyComplete();
    }
}
~~~

Kiểm thử này xác nhận cả giá trị lẫn thứ tự phần tử. `verifyComplete` đảm bảo luồng kết thúc bình thường.

### 15.2. Unit test cho tín hiệu lỗi

~~~java
import java.util.function.Function;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveErrorTest {

    @Test
    void parseErrorIsPublishedDuringSubscription() {
        Function<Flux<String>, Flux<Integer>> parseAll =
                flux -> flux.map(Integer::parseInt);

        Flux<Integer> result =
                parseAll.apply(Flux.just("10", "bad", "30"));

        StepVerifier.create(result)
                .expectNext(10)
                .expectError(NumberFormatException.class)
                .verify();
    }
}
~~~

Test không chỉ kiểm tra `apply` chạy được, mà còn xác nhận lỗi thật sự xuất hiện khi subscriber xử lý dữ liệu.

## 16. Integration test qua FunctionCatalog

Một ứng dụng Spring Boot đặt cùng package `example.functions` với `SkuFunctions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SkuApplication {

    public static void main(String[] args) {
        SpringApplication.run(SkuApplication.class, args);
    }
}
~~~

Kiểm thử tra cứu các bean theo tên:

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

@SpringBootTest(classes = SkuApplication.class)
class SkuCompositionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void namedPipelineTransformsFlux() {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        assertNotNull(pipeline);

        StepVerifier.create(
                pipeline.apply(Flux.just(" sku-42 ", " sku-7 ")))
                .expectNext(
                        "accepted:SKU-42",
                        "accepted:SKU-7")
                .verifyComplete();
    }

    @Test
    void invalidSkuTerminatesWithError() {
        Function<Flux<String>, Flux<String>> pipeline =
                catalog.lookup(
                    "normalizeSkuStream|validateSkuStream|formatSkuStream");

        assertNotNull(pipeline);

        StepVerifier.create(
                pipeline.apply(Flux.just(" sku-42 ", "bad")))
                .expectNext("accepted:SKU-42")
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

Bài kiểm thử cần Spring Cloud Function context, Spring Boot Test và `reactor-test` phù hợp với phiên bản dự án. Nó xác minh **tên bean**, **hợp đồng kiểu**, **thứ tự ghép** và **lỗi reactive** khi chạy trong Spring.

Nếu adapter HTTP/message sử dụng các wrapper/converter riêng, cần một lớp integration test ở ranh giới adapter thay vì mặc định test catalog chứng minh toàn bộ hệ thống hoạt động.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `andThen` không biên dịch | `T` khác `Flux<T>` hoặc `Mono<T>` | Lift Function qua `map` |
| Kết quả là `Mono<Mono<R>>` | Dùng `map` với mapper trả Mono | Dùng `flatMap` để flatten |
| Không thấy phần tử được xử lý | Publisher chưa có subscription | Dùng `StepVerifier` hoặc kiểm tra adapter |
| Không bắt được lỗi bằng try/catch ngoài `apply` | Lỗi mapper phát qua `onError` | Kiểm tra error signal |
| Block event-loop | Đưa I/O blocking vào `map` | Cô lập blocking hoặc dùng client reactive |
| Kết quả sai thứ tự | `flatMap` xử lý đồng thời | Cân nhắc `concatMap`/`flatMapSequential` |
| `lookup` thành công nhưng adapter lỗi | Sai converter, wrapper hoặc binding | Test input/output thực tế |
| Header bị mất hoặc không như mong đợi | Thay đổi giữa Message và payload | Thiết kế giữ headers tường minh |
| Không có HTTP endpoint hoặc message | Chỉ cấu hình `definition` | Thêm adapter, route/binding và cấu hình |
| Pipeline ngầm không tương thích khi nâng version | Tự động adaptation thay đổi | Integration test hoặc bridge tường minh |

Tránh dùng raw type, `Object` hoặc `block()` như cách vá lỗi kiểu. Chúng có thể làm che khuất vấn đề thiết kế hoặc phá vỡ đặc tính reactive của ứng dụng.

## 18. Bài tập thực hành

**Bài 1 — Bridge cơ bản.** Cho `Function<String,String> normalize` và `Function<Flux<String>,Flux<Integer>> countStream`. Vì sao `normalize.andThen(countStream)` không biên dịch? Hãy viết `normalizeFlux` để ghép hợp lệ.

**Bài 2 — Reactive trước, imperative sau.** Cho `cleanStream: Function<Flux<String>,Flux<String>>` và `parseOne: Function<String,Integer>`. Hãy xây dựng `parseStream` rồi nối sau `cleanStream`.

**Bài 3 — Mono lồng nhau.** Cho `findCustomer: Function<String,Mono<Customer>>`. Nếu dùng `mono.map(findCustomer)` với `Mono<String>`, kiểu kết quả là gì? Operator nào tạo `Mono<Customer>`?

**Bài 4 — Lỗi khi subscribe.** Cho `Flux.just("3","bad","5").map(Integer::parseInt)`. Khi nào lỗi được phát? Viết một test `StepVerifier` xác minh `3` được phát rồi gặp `NumberFormatException`.

**Bài 5 — Thứ tự sự kiện.** Một pipeline dùng `flatMap` gọi API bất đồng bộ cho mỗi input. Nếu nghiệp vụ yêu cầu kết quả theo thứ tự nguồn, hãy chọn một operator khác và nêu đánh đổi.

**Bài 6 — Blocking.** Một Function dùng JDBC blocking được đặt trong `Flux.map`. Vì sao có nguy cơ làm chậm ứng dụng? Nêu một kỹ thuật cô lập blocking có chủ đích.

**Bài 7 — Cấu hình Spring.** Viết `spring.cloud.function.definition` cho chuỗi `normalizeSkuStream|validateSkuStream|formatSkuStream`. Vì sao cấu hình đó chưa đủ để nhận message Kafka?

**Bài 8 — Kiểm thử mixed composition.** Nếu dự án muốn ghép trực tiếp `normalizeSku|validateSkuStream` thay cho bridge tường minh, cần kiểm tra những điều gì trước khi triển khai?

### Gợi ý đáp án

- **Bài 1:** `Function<Flux<String>,Flux<String>> normalizeFlux = flux -> flux.map(normalize);`; sau đó `normalizeFlux.andThen(countStream)`.
- **Bài 2:** `Function<Flux<String>,Flux<Integer>> parseStream = flux -> flux.map(parseOne);`.
- **Bài 3:** `Mono<Mono<Customer>>` nếu dùng map; dùng `flatMap` để nhận `Mono<Customer>`.
- **Bài 4:** Lỗi phát lúc subscription; dùng `expectNext(3).expectError(NumberFormatException.class).verify()`.
- **Bài 5:** `concatMap` xử lý tuần tự; `flatMapSequential` cho phép concurrency nhưng giữ thứ tự phát.
- **Bài 6:** Blocking chặn thread xử lý; có thể dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giới hạn concurrency.
- **Bài 7:** Property nêu trên chỉ chọn function; cần binder Kafka, binding/destination, converter, chính sách lỗi.
- **Bài 8:** Kiểu wrapper thực tế, số lần áp dụng mapper, subscription, thứ tự, lỗi, headers và adapter ở version tương ứng.

## 19. Ghi nhớ

- `Function<T,R>` xử lý một giá trị; `Function<Flux<T>,Flux<R>>` hoặc `Function<Mono<T>,Mono<R>>` xử lý Publisher và thường thực thi theo subscription.
- Java `andThen` chỉ nối khi **toàn bộ kiểu output** phù hợp với **toàn bộ kiểu input**; `T` không đồng nhất với `Flux<T>`.
- Dùng `flux.map(imperativeFunction)` hoặc `mono.map(imperativeFunction)` để nâng phép biến đổi đồng bộ trên từng phần tử lên hợp đồng reactive rõ ràng.
- Dùng `flatMap` khi mapper trả một Publisher cần được flatten; chú ý thứ tự, concurrency và backpressure.
- Spring Cloud Function cung cấp `FunctionCatalog` và composition, nhưng khả năng adaptation tự động giữa imperative/reactive phải được kiểm chứng theo phiên bản và adapter.
- Không đặt blocking I/O vào luồng reactive mà không có chiến lược scheduler/client phù hợp.
- `spring.cloud.function.definition` chọn logic, không thay thế cấu hình adapter HTTP, sự kiện hoặc serverless và cũng không thay thế kiểm thử subscription, error signal và Message conversion.
