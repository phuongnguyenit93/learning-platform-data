# Ghép hàm bằng Function.andThen và Function.compose

## 1. Mục tiêu bài học

Trong Spring Cloud Function, logic nghiệp vụ có thể được biểu diễn bằng các hàm nhỏ, độc lập với cách chúng được gọi qua HTTP, sự kiện hoặc môi trường serverless. Khi một yêu cầu cần đi qua nhiều bước xử lý, ta có thể **ghép các hàm** thành một luồng xử lý có thể tái sử dụng.

Sau bài học, bạn có thể:

- Giải thích cách `java.util.function.Function` biểu diễn một bước biến đổi đầu vào thành đầu ra.
- Phân biệt chính xác thứ tự thực thi của `andThen` và `compose`.
- Kiểm tra tính tương thích kiểu dữ liệu khi nối các `Function`.
- Tạo một pipeline nghiệp vụ bằng Java và hiểu cách Spring Cloud Function ghép các hàm được đăng ký trong `FunctionCatalog`.
- Chọn cách ghép hàm phù hợp, đồng thời nhận diện các lỗi phổ biến về thứ tự, chuyển kiểu, dữ liệu không hợp lệ và tác dụng phụ.

## 2. Ghép hàm là gì?

Giả sử có hai hàm:

- `f: A → B` xử lý dữ liệu từ kiểu `A` sang kiểu `B`.
- `g: B → C` xử lý kết quả từ kiểu `B` sang kiểu `C`.

Ta có thể tạo một hàm mới `h: A → C` với quy tắc:

~~~text
Đầu vào A ──f──> Kết quả B ──g──> Kết quả C
h(x) = g(f(x))
~~~

Hàm `h` có thể được gọi như một `Function<A, C>` thông thường. Người gọi không cần tự gọi từng bước `f` và `g`.

Trong Java, giao diện `Function<T, R>` ở gói `java.util.function` có hai phương thức mặc định phục vụ việc ghép hàm:

- `f.andThen(g)`: chạy **f trước, g sau**.
- `g.compose(f)`: chạy **f trước, g sau**, nhưng biểu thức được viết từ góc nhìn hàm nhận kết quả (`g`).

Vì vậy, `f.andThen(g)` và `g.compose(f)` diễn tả cùng một thứ tự xử lý nếu chúng nhận cùng các hàm.

> **Phân biệt hai tầng:** `Function.andThen`/`Function.compose` là API của Java. Spring Cloud Function bổ sung `FunctionCatalog` và cơ chế ghép các function bean theo tên, chẳng hạn `normalizeSku|validateSku`. Chúng phục vụ mục đích liên quan nhưng không phải cùng một API.

## 3. Dùng Function.andThen: đọc pipeline từ trái sang phải

Chữ ký rút gọn:

~~~java
<V> Function<T, V> andThen(
    Function<? super R, ? extends V> after
);
~~~

Với `Function<T, R> first` và `Function<R, V> second`, biểu thức `first.andThen(second)` tạo ra một `Function<T, V>`. Bước `first` hoàn tất rồi đầu ra của nó mới trở thành đầu vào của `second`.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class AndThenExample {
    public static void main(String[] args) {
        Function<String, String> normalize =
                text -> text.trim().toLowerCase(Locale.ROOT);

        Function<String, Integer> countCharacters =
                String::length;

        Function<String, Integer> normalizedLength =
                normalize.andThen(countCharacters);

        int length = normalizedLength.apply("  SPRING  ");
        System.out.println(length); // 6
    }
}
~~~

Diễn biến:

1. `normalize.apply("  SPRING  ")` trả về `"spring"`.
2. `countCharacters.apply("spring")` trả về `6`.
3. `normalizedLength.apply(...)` trả về `6`.

Khi có nhiều bước, có thể tiếp tục nối:

~~~java
Function<Integer, Boolean> isLong = length -> length >= 8;

Function<String, Boolean> isLongNormalizedText =
        normalize
            .andThen(countCharacters)
            .andThen(isLong);

System.out.println(isLongNormalizedText.apply("  SPRING CLOUD  ")); // true
~~~

Cách viết `andThen` rất hợp với luồng nghiệp vụ được mô tả theo trình tự: chuẩn hóa → phân tích → kiểm tra → tạo kết quả.

## 4. Dùng Function.compose: đọc theo bước được thực thi trước

Chữ ký rút gọn:

~~~java
<V> Function<V, R> compose(
    Function<? super V, ? extends T> before
);
~~~

Với `g: B → C` và `f: A → B`, `g.compose(f)` có nghĩa **thực thi f trước, sau đó thực thi g**. Đọc theo biểu thức toán học `g(f(x))` sẽ dễ nhớ hơn.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class ComposeExample {
    public static void main(String[] args) {
        Function<String, String> normalize =
                text -> text.trim().toLowerCase(Locale.ROOT);

        Function<String, Integer> countCharacters = String::length;

        Function<String, Integer> normalizedLength =
                countCharacters.compose(normalize);

        System.out.println(normalizedLength.apply("  SPRING  ")); // 6
    }
}
~~~

Trong ví dụ trên:

~~~text
normalize.andThen(countCharacters)
                  tương đương
countCharacters.compose(normalize)

Cả hai đều tính: countCharacters(normalize(input))
~~~

Một công thức cần nhớ:

| Biểu thức | Thứ tự gọi | Kết quả |
|---|---|---|
| `f.andThen(g)` | `f` rồi `g` | `g(f(x))` |
| `f.compose(g)` | `g` rồi `f` | `f(g(x))` |
| `g.compose(f)` | `f` rồi `g` | `g(f(x))` |

### Ví dụ cho thấy đổi thứ tự sẽ đổi kết quả

~~~java
Function<Integer, Integer> addOne = n -> n + 1;
Function<Integer, Integer> doubleIt = n -> n * 2;

System.out.println(addOne.andThen(doubleIt).apply(3)); // (3 + 1) * 2 = 8
System.out.println(addOne.compose(doubleIt).apply(3)); // (3 * 2) + 1 = 7
~~~

Hai biểu thức khác nhau vì phép cộng một và nhân đôi **không giao hoán**. Trong nghiệp vụ, việc đổi thứ tự “kiểm tra trước khi chuẩn hóa” và “chuẩn hóa trước khi kiểm tra” cũng có thể tạo ra kết quả khác nhau.

## 5. Kiểu dữ liệu là hợp đồng giữa các bước

Một chuỗi hàm chỉ ghép được khi kiểu đầu ra của bước trước phù hợp với kiểu đầu vào của bước sau.

~~~text
Function<A, B> first
Function<B, C> second
Function<C, D> third

first.andThen(second).andThen(third) : Function<A, D>
third.compose(second).compose(first) : Function<A, D>
~~~

Ví dụ hợp lệ:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<Integer, Long> toLong = Integer::longValue;

Function<String, Long> pipeline = parseQuantity.andThen(toLong);
System.out.println(pipeline.apply("12")); // 12
~~~

Ví dụ **không hợp lệ về kiểu**:

~~~java
Function<String, Integer> parseQuantity = Integer::parseInt;
Function<String, Boolean> hasPrefix = text -> text.startsWith("SKU-");

// Không biên dịch: parseQuantity tạo Integer,
// trong khi hasPrefix yêu cầu đầu vào String.
// Function<String, Boolean> invalid = parseQuantity.andThen(hasPrefix);
~~~

Trình biên dịch sẽ chặn nhiều lỗi ghép sai kiểu. Tuy nhiên, **tương thích kiểu không đồng nghĩa tương thích ý nghĩa**: `Function<Integer, Integer>` chuyển số lượng thành giá có thể ghép với một hàm nhận mã trạng thái `Integer`, nhưng chuỗi xử lý đó chưa chắc đúng nghiệp vụ.

Các ký hiệu `? super R` và `? extends V` trong chữ ký `andThen` cho phép sử dụng kiểu cha/kiểu con thích hợp theo quy tắc generic của Java. Khi mới học, hãy kiểm tra đơn giản: **đầu ra bước trước phải dùng được làm đầu vào bước sau**.

## 6. Ví dụ nghiệp vụ: từ dòng đơn hàng đến báo giá

Giả sử hệ thống nhận dữ liệu `"SKU-01,3"`, sau đó phân tích thành yêu cầu mua hàng, tính tiền và định dạng kết quả. Ba bước độc lập có thể được nối thành một `Function<String, String>`.

Ví dụ sau dùng cú pháp `record` của Java 17 trở lên; đơn giá cố định chỉ để minh họa, không phải quy tắc báo giá thực tế.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class OrderPipeline {
    record OrderInput(String sku, int quantity) {}
    record Quote(String sku, int quantity, long totalVnd) {}

    public static void main(String[] args) {
        Function<String, OrderInput> parseOrder = raw -> {
            String[] parts = raw.split(",");
            if (parts.length != 2) {
                throw new IllegalArgumentException("Dinh dang: SKU,soLuong");
            }

            String sku = parts[0].trim().toUpperCase(Locale.ROOT);
            int quantity = Integer.parseInt(parts[1].trim());
            if (sku.isEmpty() || quantity <= 0) {
                throw new IllegalArgumentException("SKU/so luong khong hop le");
            }

            return new OrderInput(sku, quantity);
        };

        Function<OrderInput, Quote> calculateQuote = order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd
            );
            return new Quote(order.sku(), order.quantity(), totalVnd);
        };

        Function<Quote, String> formatQuote = quote ->
                quote.sku() + " x " + quote.quantity()
                + " = " + quote.totalVnd() + " VND";

        Function<String, String> createQuote =
                parseOrder
                    .andThen(calculateQuote)
                    .andThen(formatQuote);

        System.out.println(createQuote.apply(" sku-01 , 3"));
        // SKU-01 x 3 = 375000 VND
    }
}
~~~

Sơ đồ xử lý:

~~~text
" sku-01 , 3"
      │
      ▼
parseOrder: String → OrderInput
      │  OrderInput("SKU-01", 3)
      ▼
calculateQuote: OrderInput → Quote
      │  Quote("SKU-01", 3, 375000)
      ▼
formatQuote: Quote → String
      │
      ▼
"SKU-01 x 3 = 375000 VND"
~~~

Mỗi hàm có một trách nhiệm. `parseOrder` có thể dùng trong một quy trình khác; `calculateQuote` có thể được kiểm thử bằng `OrderInput` mà không phải mô phỏng HTTP. Khi cơ chế gọi thay đổi từ REST sang sự kiện, logic báo giá vẫn có thể được tái sử dụng.

Tương đương với `compose`:

~~~java
Function<String, String> createQuoteWithCompose =
        formatQuote
            .compose(calculateQuote)
            .compose(parseOrder);
~~~

Ở đây, viết bằng `compose` bắt đầu từ bước cuối cùng (`formatQuote`) rồi khai báo dần những bước phải chạy trước.

## 7. Ghép các Function bean trong Spring Cloud Function

Spring Cloud Function cung cấp `FunctionCatalog` để tra cứu những hàm đã được ứng dụng đăng ký. Nếu ta khai báo các hàm bằng `@Bean`, catalog có thể tạo một pipeline từ **tên hàm**, dùng dấu `|` để mô tả thứ tự thực thi.

Ví dụ ứng dụng Spring Boot có hai function bean:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductFunctions {

    @Bean
    public Function<String, String> normalizeSku() {
        return raw -> raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, Boolean> validateSku() {
        return sku -> sku.matches("SKU-[0-9]+");
    }
}
~~~

Lúc này:

- `normalizeSku` nhận `String` và trả về `String`.
- `validateSku` nhận `String` và trả về `Boolean`.
- `normalizeSku|validateSku` nhận `String` và trả về `Boolean`.

Có thể tra cứu pipeline trực tiếp từ catalog (khi ứng dụng đã khởi động và có Spring Cloud Function trên classpath):

~~~java
import java.util.function.Function;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.cloud.function.context.FunctionCatalog;

@Component
public class CatalogExample implements ApplicationRunner {
    private final FunctionCatalog catalog;

    public CatalogExample(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        Function<String, Boolean> checkSku =
                catalog.lookup("normalizeSku|validateSku");

        if (checkSku == null) {
            throw new IllegalStateException("Khong tim thay function pipeline");
        }

        System.out.println(checkSku.apply(" sku-42 ")); // true
        System.out.println(checkSku.apply(" abc "));    // false
    }
}
~~~

Biểu thức catalog `normalizeSku|validateSku` có cùng **thứ tự ý nghĩa** với Java `normalizeSku.andThen(validateSku)`. Tuy nhiên, catalog còn chịu trách nhiệm tra cứu và cung cấp function cho các adapter của Spring Cloud Function; nó không phải là phương thức `andThen` trên một đối tượng Java.

Có thể chọn pipeline mặc định bằng cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeSku|validateSku"
~~~

Cấu hình `spring.cloud.function.definition` khai báo chuỗi hàm mà môi trường tích hợp sẽ chọn. Khi dùng Spring Cloud Function Web, Spring Cloud Stream hoặc adapter serverless, cách đưa đầu vào và công bố đầu ra phụ thuộc vào adapter đang cài đặt; **cấu hình này một mình không tự tạo endpoint HTTP hay kết nối message broker**.

| Tiêu chí | `Function.andThen` / `Function.compose` | `FunctionCatalog` và `|` |
|---|---|---|
| Nơi định nghĩa | Đối tượng Java `Function` | Các function được đăng ký trong Spring |
| Cách ghép | Gọi phương thức trên đối tượng hàm | Ghép theo tên, ví dụ `"normalizeSku|validateSku"` |
| Kiểm tra kiểu | Chủ yếu lúc biên dịch | Có yếu tố tra cứu, kiểu hàm và chuyển đổi tại runtime |
| Cách sử dụng | Trong code Java thuần hoặc Spring | Khi tích hợp với Spring Cloud Function và các adapter |
| Khả năng tái sử dụng | Tạo một `Function` mới, có thể đăng ký thành bean | Chọn tổ hợp từ các function bean có sẵn |

### Khi nào nên dùng cách nào?

Dùng `andThen` khi bạn đang triển khai một pipeline bên trong Java, muốn trình bày bước xử lý theo chiều thuận và tận dụng kiểm tra kiểu lúc biên dịch. Dùng `compose` khi muốn đọc pipeline như hàm toán học từ ngoài vào trong hoặc bổ sung bước tiền xử lý vào một hàm đã có.

Dùng tổ hợp theo tên qua `FunctionCatalog` khi các function đã được đăng ký trong Spring và bạn muốn lựa chọn thứ tự ghép bằng cấu hình hoặc tra cứu theo tên. Điều này phù hợp với mục tiêu của Spring Cloud Function: cùng logic có thể được gọi trong nhiều môi trường khác nhau.

## 8. Những giới hạn và lỗi cần chú ý

### 8.1. Ghép sai thứ tự

~~~java
Function<String, String> trim = String::trim;
Function<String, Boolean> isExactSku = "SKU-01"::equals;

System.out.println(trim.andThen(isExactSku).apply(" SKU-01 ")); // true
~~~

Nếu kiểm tra `isExactSku` trước khi `trim`, dữ liệu có khoảng trắng sẽ không được nhận diện. Hãy ghi rõ thứ tự thành các bước và kiểm thử ít nhất một đầu vào mà việc đảo thứ tự làm thay đổi kết quả.

### 8.2. Dữ liệu hợp kiểu nhưng không hợp lệ

`Integer.parseInt("abc")` sẽ ném `NumberFormatException` dù chuỗi `String → Integer` có kiểu hoàn toàn hợp lệ. Tương tự, hàm có thể ném ngoại lệ khi gặp `null`, giá trị ngoài khoảng cho phép hoặc thiếu trường bắt buộc.

Một ngoại lệ phát sinh ở bước trước thường làm chuỗi ghép dừng lại; bước sau không được gọi. Nếu cần phản hồi lỗi có cấu trúc, hãy thiết kế một mô hình kết quả như `Result<T>`/`Either<L, R>` hoặc xử lý và ánh xạ ngoại lệ tại ranh giới ứng dụng. Không nên tự ý nuốt lỗi bên trong mọi hàm.

### 8.3. Nhầm Function với Consumer hoặc Supplier

`Function<T, R>` có cả `andThen` và `compose`. `Consumer<T>` có `andThen` riêng để nối các thao tác không trả về giá trị, nhưng **không có `compose`** giống `Function`. `Supplier<T>` cũng không có hai phương thức này theo giao diện chuẩn Java.

Spring Cloud Function có cơ chế tổ hợp các dạng hàm khác nhau trong những trường hợp được hỗ trợ, nhưng ví dụ `Function<A, B> → Function<B, C>` là điểm xuất phát rõ ràng nhất để học `andThen`/`compose`.

### 8.4. Tác dụng phụ, hiệu năng và trạng thái

Việc ghép hàm không tự tạo tác vụ song song hay cơ chế retry. Mặc định `andThen`/`compose` gọi các hàm theo thứ tự khi `apply` được thực thi. Nếu một bước gọi cơ sở dữ liệu, ghi log hoặc cập nhật trạng thái dùng chung, thứ tự và số lần gọi có thể ảnh hưởng tới kết quả.

Ưu tiên các hàm biến đổi dữ liệu rõ ràng, tránh trạng thái mutable chia sẻ. Với bước có I/O, cần thiết kế timeout, retry và xử lý lỗi ở tầng thích hợp; không suy luận rằng phép ghép hàm sẽ tự quản lý chúng.

### 8.5. Hàm reactive phải có hợp đồng kiểu phù hợp

Nếu đang dùng Reactor, một pipeline có thể gồm `Function<Flux<A>, Flux<B>>` và `Function<Flux<B>, Flux<C>>`; hai đối tượng Java đó vẫn có thể ghép bằng `andThen` nếu kiểu tương thích. Nhưng `Function<A, B>` không tự trở thành `Function<Flux<A>, Flux<B>>` chỉ vì chúng cùng xử lý dữ liệu `A` và `B`. Việc Spring Cloud Function xử lý, nhận dạng và chuyển đổi giữa dạng imperative/reactive cần tuân theo hợp đồng của framework và adapter đang dùng.

### 8.6. Khác biệt giữa chạy Java thuần và gọi qua adapter

Ví dụ Java `checkSku.apply(" sku-42 ")` truyền trực tiếp một chuỗi. Khi đưa pipeline ra HTTP hoặc kênh sự kiện, adapter còn phải đọc payload, chuyển đổi kiểu, xử lý header/message và mã hóa kết quả. Kiểu Java khớp chưa đủ để đảm bảo payload ở bên ngoài đúng định dạng. Nên kiểm thử thêm tại ranh giới adapter khi triển khai thực tế.

## 9. Kiểm thử chuỗi ghép hàm

Mỗi bước cần có kiểm thử riêng; ngoài ra phải có kiểm thử toàn pipeline để xác nhận đúng thứ tự và đầu ra.

Ví dụ JUnit 5 độc lập với Spring:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

class FunctionCompositionTest {

    @Test
    void andThenRunsLeftToRight() {
        Function<Integer, Integer> addOne = n -> n + 1;
        Function<Integer, Integer> doubleIt = n -> n * 2;

        assertEquals(8, addOne.andThen(doubleIt).apply(3));
        assertEquals(7, addOne.compose(doubleIt).apply(3));
    }

    @Test
    void exceptionFromFirstStepStopsPipeline() {
        Function<String, Integer> parse = Integer::parseInt;
        Function<Integer, Integer> doubleIt = n -> n * 2;

        Function<String, Integer> pipeline = parse.andThen(doubleIt);

        assertEquals(24, pipeline.apply("12"));
        assertThrows(NumberFormatException.class,
                () -> pipeline.apply("invalid"));
    }
}
~~~

Với `FunctionCatalog`, nên có một kiểm thử tích hợp khởi động Spring context, lấy `catalog.lookup("normalizeSku|validateSku")` và xác minh pipeline có thể tra cứu, thực thi đúng. Khi triển khai HTTP hoặc sự kiện, kiểm thử thêm dữ liệu đầu vào/đầu ra thực tế qua adapter đó.

## 10. Tự luyện tập

1. Cho `trim: String → String`, `toUpper: String → String` và `length: String → Integer`. Hãy viết một biểu thức `andThen` và một biểu thức `compose` đều trả về độ dài chuỗi sau khi xóa khoảng trắng đầu/cuối và chuyển chữ hoa.
2. Với `addTax: Long → Long` và `formatMoney: Long → String`, giải thích vì sao `formatMoney.andThen(addTax)` không biên dịch.
3. Tạo các bean `trimInput`, `parseNumber`, `doubleNumber`. Viết chuỗi tên thích hợp để dùng trong `FunctionCatalog`; kiểm tra kết quả của đầu vào `" 21 "`.
4. Thử đảo thứ tự chuẩn hóa và kiểm tra SKU trong ví dụ Spring Cloud Function. Nêu một đầu vào khiến kết quả khác đi, và giải thích nguyên nhân.

Gợi ý câu 1: thứ tự mong muốn là `trim → toUpper → length`. Câu 3 sử dụng chuỗi `"trimInput|parseNumber|doubleNumber"`, với hợp đồng đầu ra/đầu vào tương thích giữa từng cặp.

## 11. Ghi nhớ

- `f.andThen(g)` chạy `f` rồi `g` và trả về `g(f(x))`.
- `f.compose(g)` chạy `g` rồi `f` và trả về `f(g(x))`.
- `f.andThen(g)` tương đương `g.compose(f)` về thứ tự thực thi.
- Đầu ra của bước trước phải tương thích với đầu vào của bước tiếp theo; kiểm tra kiểu chỉ là bước đầu, còn phải xác minh ý nghĩa nghiệp vụ và dữ liệu lỗi.
- Spring Cloud Function dùng `FunctionCatalog` và chuỗi tên như `"normalizeSku|validateSku"` để ghép các function đã đăng ký; adapter HTTP, sự kiện và serverless quyết định cách pipeline được gọi từ bên ngoài.
