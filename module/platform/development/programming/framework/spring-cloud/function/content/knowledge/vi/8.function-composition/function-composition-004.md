# Thứ tự thực thi và tương thích kiểu giữa các bước

## 1. Mục tiêu bài học

Trong Spring Cloud Function, mỗi `Supplier`, `Function` hoặc `Consumer` có thể đóng vai trò một đơn vị logic nghiệp vụ độc lập với giao thức gọi. Nhờ cơ chế **composition**, ta có thể kết hợp các hàm nhỏ thành một luồng xử lý có thể dùng lại qua Java, HTTP, sự kiện hoặc serverless khi ứng dụng được trang bị adapter phù hợp.

Để phép ghép hàm đúng, phải giải quyết đồng thời hai câu hỏi:

1. **Các bước chạy theo thứ tự nào?** Đầu vào đi qua những bước nào trước khi tạo ra kết quả?
2. **Đầu ra của bước trước có dùng được làm đầu vào cho bước sau không?** Kiểu Java, cấu trúc dữ liệu và ý nghĩa nghiệp vụ có tương thích không?

Bài học thuộc chương **Ghép hàm**, tập trung vào hai điều kiện đó. Kết thúc bài, bạn có thể:

- Dự đoán thứ tự chạy của `andThen`, `compose` và chuỗi tên `A|B|C` trong `FunctionCatalog`.
- Đọc hợp đồng `Function<A, B>` và suy ra kiểu tổng thể của pipeline.
- Phân biệt kiểm tra kiểu khi biên dịch Java với việc ghép theo tên và chuyển đổi payload ở runtime.
- Thiết kế pipeline nghiệp vụ nhiều bước, xử lý dữ liệu không hợp lệ và giữ được khả năng tái sử dụng.
- Viết kiểm thử chứng minh **đúng thứ tự, đúng dữ liệu truyền giữa các bước và dừng khi có lỗi**.

## 2. Thứ tự thực thi của các phép ghép

Giả sử có ba hàm:

~~~text
f: A → B
g: B → C
h: C → D
~~~

Ta muốn tính:

~~~text
A --f--> B --g--> C --h--> D
~~~

Kết quả cuối là `h(g(f(x)))`. Trong Java, có hai cách viết tương đương về thứ tự:

~~~java
Function<A, D> pipeline1 = f.andThen(g).andThen(h);
Function<A, D> pipeline2 = h.compose(g).compose(f);
~~~

Ở đây, `A`, `B`, `C`, `D` là ký hiệu kiểu khái niệm; để biến đoạn mã thành Java chạy được cần khai báo các kiểu/hàm tương ứng.

Trong Spring Cloud Function, nếu `f`, `g`, `h` là tên các function bean được đăng ký trong `FunctionCatalog`, một biểu thức ghép theo tên là:

~~~java
catalog.lookup("f|g|h");
~~~

Cách đọc chuỗi tên cũng là **f trước, g sau, h cuối**.

| Cách viết | Thứ tự xử lý | Công thức |
|---|---|---|
| `f.andThen(g)` | `f` → `g` | `g(f(x))` |
| `g.compose(f)` | `f` → `g` | `g(f(x))` |
| `f.andThen(g).andThen(h)` | `f` → `g` → `h` | `h(g(f(x)))` |
| `h.compose(g).compose(f)` | `f` → `g` → `h` | `h(g(f(x)))` |
| `"f|g|h"` | `f` → `g` → `h` | `h(g(f(x)))` |

`andThen` và `compose` là phương thức trên `java.util.function.Function`; dấu `|` là cú pháp ghép các function được đăng ký qua Spring Cloud Function. Chúng biểu diễn quy tắc thứ tự tương tự nhưng hoạt động ở hai tầng khác nhau.

### 2.1. Minh họa bằng kết quả số

~~~java
import java.util.function.Function;

Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> multiplyThree = n -> n * 3;

int firstThenSecond =
        addTwo.andThen(multiplyThree).apply(4); // (4 + 2) * 3 = 18

int secondThenFirst =
        multiplyThree.andThen(addTwo).apply(4); // (4 * 3) + 2 = 14
~~~

Hai hàm có cùng chữ ký `Integer → Integer`, nên cả hai thứ tự đều **hợp lệ về kiểu**. Nhưng `18` khác `14`: **đúng kiểu không đảm bảo đúng trình tự nghiệp vụ**.

### 2.2. Theo dõi thứ tự bằng dấu vết

Khi khó quan sát thứ tự, thêm một danh sách ghi lại các bước được gọi trong ví dụ thử nghiệm:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

List<String> calls = new ArrayList<>();

Function<String, String> first = text -> {
    calls.add("first");
    return text.trim();
};

Function<String, Integer> second = text -> {
    calls.add("second");
    return text.length();
};

Function<Integer, Integer> third = number -> {
    calls.add("third");
    return number * 2;
};

Function<String, Integer> pipeline =
        first.andThen(second).andThen(third);

int result = pipeline.apply("  abc  ");

System.out.println(result); // 6
System.out.println(calls);  // [first, second, third]
~~~

Đây là kỹ thuật minh họa và kiểm thử. Trong code nghiệp vụ thật, tránh dùng một `ArrayList` mutable chia sẻ giữa các request đồng thời để lưu trạng thái của pipeline.

## 3. Tương thích kiểu: điều kiện nối các bước

`Function<T, R>` nhận đầu vào kiểu `T` và trả kết quả kiểu `R`:

~~~text
Function<A, B> first
Function<B, C> second
                   |
                   v
first.andThen(second): Function<A, C>
~~~

Để nối hai bước, **kiểu đầu ra của bước trước phải có thể dùng làm đầu vào của bước sau**. Với ví dụ cơ bản:

~~~java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Long> calculate = value -> value * 1_000L;

Function<String, Long> pipeline = parse.andThen(calculate);

System.out.println(pipeline.apply("25")); // 25000
~~~

Hợp đồng tổng thể của pipeline là `String → Long`. Nó **không** còn là `String → Integer` hay `Integer → Long`.

### 3.1. Lỗi kiểu khi biên dịch

~~~java
Function<String, Integer> parse = Integer::parseInt;
Function<String, Boolean> startsWithSku =
        text -> text.startsWith("SKU-");

// Không biên dịch: parse trả Integer,
// nhưng startsWithSku cần String.
// Function<String, Boolean> invalid = parse.andThen(startsWithSku);
~~~

Đây là ưu điểm của ghép `Function` Java trực tiếp: trình biên dịch kiểm tra generic, ngăn nhiều cấu hình sai.

Không nên dùng raw type để né lỗi:

~~~java
// Tránh viết kiểu thô như sau:
// Function raw = parse;
// Function unsafe = raw.andThen(startsWithSku);
~~~

Sử dụng raw type làm mất thông tin kiểu và có thể đẩy lỗi sang runtime, ví dụ `ClassCastException`.

### 3.2. Tính tương thích không nhất thiết là hai tên kiểu giống hệt nhau

Java generic cho phép truyền đối tượng con vào hàm nhận kiểu cha, nếu chữ ký cho phép. Chẳng hạn:

~~~java
Function<String, Integer> stringLength = String::length;
Function<Number, String> describeNumber =
        number -> "Gia tri: " + number;

Function<String, String> describeLength =
        stringLength.andThen(describeNumber);

System.out.println(describeLength.apply("Java"));
// Gia tri: 4
~~~

`stringLength` trả `Integer`, còn `describeNumber` nhận `Number`; vì `Integer` là một `Number`, Java cho phép nối.

Chữ ký tổng quát của `andThen`:

~~~java
<V> Function<T, V> andThen(
        Function<? super R, ? extends V> after);
~~~

`? super R` cho phép hàm phía sau nhận một kiểu cha phù hợp của `R`. Khi thiết kế pipeline, vẫn nên ưu tiên những hợp đồng cụ thể, dễ hiểu thay vì cố tận dụng ép kiểu phức tạp.

### 3.3. Kiểu dữ liệu và ý nghĩa dữ liệu là hai hợp đồng riêng

Hai hàm có thể đều nhận/trả `String` nhưng xử lý những loại thông tin khác nhau:

~~~text
fetchCustomerId: String → String     (email → customerId)
validateEmail:   String → Boolean    (email → hợp lệ?)
~~~

Dù biểu thức `fetchCustomerId|validateEmail` có kiểu `String → Boolean`, hàm thứ hai sẽ kiểm tra **customerId như thể đó là email**. Pipeline vẫn sai nghiệp vụ.

Khi cần, hãy dùng các kiểu dữ liệu tường minh:

~~~java
record EmailAddress(String value) {}
record CustomerId(String value) {}
~~~

Sau đó định nghĩa `Function<EmailAddress, CustomerId>` và `Function<EmailAddress, Boolean>`; trình biên dịch sẽ giúp phát hiện nhiều cách nối không hợp lý mà `String` trần không thể phát hiện.

## 4. Ví dụ xuyên suốt: xử lý báo giá đơn hàng

Một dịch vụ nhận dữ liệu đơn hàng dạng chuỗi `"SKU-42,2"`, rồi lần lượt:

1. Phân tích và xác thực đầu vào.
2. Tính báo giá.
3. Định dạng kết quả gửi cho người gọi.

Sơ đồ:

~~~text
"SKU-42,2"                (String)
    |
    v
 parseLine                 String → OrderLine
    |
    v
 OrderLine("SKU-42", 2)
    |
    v
 priceOrder                OrderLine → Quote
    |
    v
 Quote("SKU-42", 2, 250000)
    |
    v
 formatQuote               Quote → String
    |
    v
"SKU-42 x 2 = 250000 VND"
~~~

Ba bước có thể đăng ký thành những `Function` bean độc lập. Ví dụ sử dụng Java 17 trở lên và giả định một đơn giá cố định để học thứ tự và hợp đồng kiểu.

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderLine(String sku, int quantity) {}

    public record Quote(String sku, int quantity, long totalVnd) {}

    @Bean
    public Function<String, OrderLine> parseLine() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException("Don hang rong");
            }

            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Can dinh dang SKU,soLuong");
            }

            String sku =
                    parts[0].trim().toUpperCase(Locale.ROOT);
            int quantity = Integer.parseInt(parts[1].trim());

            if (!sku.matches("SKU-[0-9]+") || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Ma SKU hoac so luong khong hop le");
            }

            return new OrderLine(sku, quantity);
        };
    }

    @Bean
    public Function<OrderLine, Quote> priceOrder() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd =
                    Math.multiplyExact(order.quantity(), unitPriceVnd);
            return new Quote(
                    order.sku(), order.quantity(), totalVnd);
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

Tên bean mặc định là `parseLine`, `priceOrder`, `formatQuote`. Nếu cấu hình Spring Cloud Function đã đăng ký chúng vào `FunctionCatalog`, pipeline cần có thứ tự:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseLine|priceOrder|formatQuote"
~~~

Hoặc lấy trực tiếp bằng catalog trong code Spring:

~~~java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

// catalog được inject từ Spring context:
Function<String, String> createQuote =
        catalog.lookup("parseLine|priceOrder|formatQuote");

if (createQuote == null) {
    throw new IllegalStateException("Khong tim thay pipeline");
}

System.out.println(createQuote.apply("sku-42,2"));
// SKU-42 x 2 = 250000 VND
~~~

Đây là ví dụ ứng dụng của Spring Cloud Function, nơi **logic nghiệp vụ tách khỏi giao thức**. Với Spring Cloud Function Web, Stream hoặc adapter serverless, ứng dụng còn cần dependency, khai báo endpoint/binding/handler và chuyển đổi payload phù hợp với môi trường.

### 4.1. Vì sao không thể tùy tiện đổi thứ tự?

Các hợp đồng trong ví dụ:

| Bước | Đầu vào | Đầu ra |
|---|---|---|
| `parseLine` | `String` | `OrderLine` |
| `priceOrder` | `OrderLine` | `Quote` |
| `formatQuote` | `Quote` | `String` |

Chuỗi `"priceOrder|parseLine|formatQuote"` không nối đúng kiểu: `priceOrder` trả `Quote`, còn `parseLine` yêu cầu `String`. Chuỗi `"parseLine|formatQuote"` cũng không phù hợp vì `formatQuote` cần `Quote`, không phải `OrderLine`.

Một cấu hình cho ra kiểu tổng thể `String → String` chưa chắc đúng; ta phải xem **cả các kiểu trung gian**. Điều này quan trọng hơn khi có các bước trước/sau đều dùng `String`, vì chỉ nhìn kiểu đầu và cuối sẽ bỏ sót logic sai ở giữa.

## 5. Kiểm tra kiểu tại biên dịch và tại runtime

Cần phân biệt hai cách ghép:

| Khía cạnh | Ghép trực tiếp trong Java | Ghép tên qua Spring Cloud Function |
|---|---|---|
| Ví dụ | `first.andThen(second)` | `catalog.lookup("first|second")` |
| Thời điểm xác định chuỗi | Khi viết code Java | Khi tra cứu/cấu hình và chạy ứng dụng |
| Kiểm tra kiểu | Generic hỗ trợ kiểm tra lúc biên dịch | Tên và kiểu function được giải quyết tại runtime |
| Lỗi thường gặp | Báo lỗi biên dịch do không tương thích generic | Không tìm thấy bean, lỗi composition, lỗi kiểu/payload khi xử lý |
| Chuyển đổi dữ liệu | Không tự động thêm chuyển đổi tùy ý | Framework/adapter có cơ chế chuyển đổi trong phạm vi hỗ trợ |

Một khai báo như sau **được trình biên dịch Java chấp nhận** vì nó chỉ thấy giá trị trả về đã được gán kiểu:

~~~java
Function<String, String> pipeline =
        catalog.lookup("priceOrder|parseLine");
~~~

Điều đó **không chứng minh** chuỗi function bean bên trong tương thích. `lookup` được đánh giá tại runtime; một tên sai hoặc một chuỗi không hợp lệ có thể khiến việc tra cứu/thực thi thất bại. Hãy kiểm tra kiểu của từng bean và thêm kiểm thử tích hợp với catalog.

### 5.1. Chuyển đổi kiểu không thay thế hợp đồng nghiệp vụ

Spring Cloud Function hỗ trợ các cơ chế chuyển đổi dữ liệu, bao gồm tích hợp với `Message<?>` và xử lý payload dựa trên thông tin kiểu trong những trường hợp được hỗ trợ. Tuy nhiên, không nên giả định framework sẽ tự hiểu mọi cách nối:

~~~text
Function<String, Integer> parseQuantity
Function<String, Boolean> validateSku
~~~

Từ `Integer` sang `String` có thể tồn tại phép chuyển đổi kỹ thuật trong một hệ sinh thái chuyển đổi. Nhưng việc chuyển một **số lượng** thành chuỗi rồi kiểm tra như **mã SKU** vẫn sai về ý nghĩa. Hãy bổ sung bước chuyển đổi có mục đích rõ ràng, hoặc thiết kế lại pipeline.

### 5.2. Kiểu payload khác với kiểu Message

Một hàm:

~~~java
Function<String, String> normalize = String::trim;
~~~

không có cùng chữ ký Java với:

~~~java
Function<Message<String>, Message<String>> normalizeMessage;
~~~

vì `Message<String>` chứa cả payload lẫn headers. Nếu pipeline có hàm xử lý `Message<T>`, cần xác định rõ hợp đồng trước/sau và hành vi chuyển đổi của phiên bản Spring Cloud Function/adapter.

Đừng khẳng định mọi header sẽ tự được giữ nguyên, mọi payload JSON sẽ tự ánh xạ thành POJO hoặc mọi kiểu `Message<A>` đều kết nối được với `Function<B, C>`. Một pipeline làm việc tốt qua `apply` Java thuần vẫn cần kiểm thử với message thật ở ranh giới adapter.

## 6. Supplier, Function và Consumer có vị trí khác nhau

Spring Cloud Function hỗ trợ ba dạng logic cơ bản:

| Loại | Hợp đồng Java | Vai trò điển hình trong một luồng |
|---|---|---|
| `Supplier<T>` | `() → T` | Tạo dữ liệu đầu vào |
| `Function<T, R>` | `T → R` | Biến đổi dữ liệu ở giữa |
| `Consumer<T>` | `T → void` | Nhận kết quả, thực hiện tác dụng phụ ở cuối |

Các phép ghép được hỗ trợ phụ thuộc hợp đồng của từng loại hàm và phiên bản framework. Với luồng dữ liệu một chiều, mô hình dễ hiểu là:

~~~text
Supplier<A> → Function<A, B> → Consumer<B>
  nguồn            biến đổi         điểm nhận
~~~

Tuy nhiên, `Supplier` và `Consumer` **không phải** đối tượng `Function<T, R>` thông thường. `Supplier` không có `andThen`/`compose` chuẩn của `Function`; `Consumer` có `andThen` riêng cho hai hành động `Consumer`, nhưng không có `compose` giống `Function`.

Trong Spring Cloud Function, framework có hỗ trợ một số kiểu composition kết hợp các loại hàm này. Khi cấu hình một chuỗi như `"produce|transform|publish"`, phải đối chiếu khả năng composition của phiên bản đang dùng và đảm bảo thứ tự tạo → biến đổi → nhận dữ liệu phù hợp. Không được giả định bất kỳ thứ tự nào của `Supplier`, `Function` và `Consumer` cũng hợp lệ.

## 7. Thứ tự khi xử lý lỗi và giá trị đặc biệt

### 7.1. Ngoại lệ ở bước trước dừng phép ghép đồng bộ

Với `Function.andThen` của Java, nếu bước trước ném ngoại lệ, bước sau không được gọi:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

AtomicInteger calls = new AtomicInteger();

Function<String, Integer> parse = Integer::parseInt;
Function<Integer, Integer> doubleValue = number -> {
    calls.incrementAndGet();
    return number * 2;
};

Function<String, Integer> pipeline = parse.andThen(doubleValue);

try {
    pipeline.apply("khong-phai-so");
} catch (NumberFormatException expected) {
    System.out.println("Gia tri khong hop le");
}

System.out.println(calls.get()); // 0
~~~

Khi gọi `apply("khong-phai-so")`, `parse` ném `NumberFormatException` và `doubleValue` chưa được chạy. Đây là hành vi bình thường của pipeline đồng bộ Java.

Với Spring Cloud Function, lớp adapter có thể bắt/ánh xạ ngoại lệ thành HTTP response hoặc hành vi xử lý message theo cấu hình. **Phép ghép hàm không tự tạo retry hay cơ chế phục hồi lỗi**. Cần xác định rõ ai chịu trách nhiệm validation, retry và thông báo lỗi cho người gọi.

### 7.2. Null có thể truyền tới bước tiếp theo

~~~java
Function<String, String> sometimesNull =
        value -> value.isBlank() ? null : value;

Function<String, Integer> count = String::length;

Function<String, Integer> pipeline =
        sometimesNull.andThen(count);

// pipeline.apply("") sẽ ném NullPointerException tại count.
~~~

`andThen` không tự chặn `null` trả về bởi một hàm. Nên thiết kế hợp đồng xử lý thiếu dữ liệu rõ ràng: từ chối đầu vào, trả một kiểu kết quả tường minh hoặc sử dụng một mô hình như `Optional` tại ranh giới được kiểm soát. Tránh tự suy đoán `null` có nghĩa là kết quả rỗng hay bỏ qua bước.

### 7.3. Bước có tác dụng phụ cần lưu ý số lần gọi

Đọc database, gửi thông điệp hoặc ghi log trong một bước có thể tạo tác dụng phụ. Pipeline không tự đảm bảo tính idempotent, giao dịch hay exactly-once. Nếu adapter thực hiện retry, một bước có tác dụng phụ có thể chạy lại theo chính sách adapter.

Nếu cần gửi một sự kiện sau khi xử lý thành công, hãy làm rõ thứ tự: xác thực → tính toán → lưu/đăng sự kiện, đồng thời thiết kế cơ chế chống ghi trùng phù hợp với hệ thống.

## 8. Thứ tự trong luồng reactive

Khi xử lý luồng sự kiện, Spring Cloud Function có thể sử dụng Reactor, ví dụ `Flux<T>`:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<String>> normalize =
        input -> input.map(String::trim);

Function<Flux<String>, Flux<Integer>> measure =
        input -> input.map(String::length);

Function<Flux<String>, Flux<Integer>> pipeline =
        normalize.andThen(measure);
~~~

Về kiểu, phép ghép có dạng:

~~~text
Flux<String> --normalize--> Flux<String>
             --measure---> Flux<Integer>
~~~

Tuy nhiên, nhiều toán tử Reactor như `map` hoạt động **lười**: lúc gọi `pipeline.apply(flux)`, ta có thể mới chỉ tạo một pipeline reactive; phép xử lý phần tử diễn ra khi có subscription và demand phù hợp.

Vì vậy, cần phân biệt:

- **Thứ tự khai báo operator:** `normalize` trước `measure`.
- **Thời điểm tác vụ trên phần tử thực sự chạy:** tùy subscription, scheduler và operator.
- **Mức độ đồng thời/thứ tự các phần tử:** phụ thuộc toán tử như `map`, `flatMap`, `concatMap` và cấu hình scheduler.

Đừng suy luận rằng dấu `|` tự làm mọi bước chạy đồng bộ trên một thread, hoặc rằng pipeline sẽ tự song song hóa. Trong ứng dụng reactive, hãy kiểm thử cả hợp đồng `Publisher` và thứ tự phần tử nếu nghiệp vụ cần giữ thứ tự.

Một `Function<String, String>` không tự trở thành `Function<Flux<String>, Flux<String>>` theo cơ chế generic Java. Việc wrapper/adapter Spring Cloud Function xử lý sự khác biệt imperative và reactive phải được xem xét theo phiên bản và hợp đồng tích hợp cụ thể.

## 9. Cách thiết kế pipeline dễ kiểm chứng

Một pipeline đáng tin cậy nên có những đặc điểm sau:

1. **Mỗi bước làm một việc rõ ràng.** Ví dụ `parseLine` chỉ phân tích dữ liệu, `priceOrder` chỉ tính báo giá, `formatQuote` chỉ định dạng kết quả.
2. **Tên và kiểu phản ánh ý nghĩa.** Tên `OrderLine`, `Quote` giúp phân biệt hai dữ liệu mà `String` hoặc `Map<String, Object>` dễ làm lẫn.
3. **Đầu ra ổn định.** Hạn chế một hàm trả nhiều cấu trúc khác nhau theo từng trường hợp nếu các bước sau phải ép kiểu.
4. **Xác thực ở đúng bước.** Dữ liệu được kiểm tra trước khi phép tính hoặc tác dụng phụ quan trọng diễn ra.
5. **Lỗi có chính sách nhất quán.** Xác định có ném ngoại lệ, trả kiểu kết quả hay chuyển lỗi ở adapter; không tự che giấu ngoại lệ.
6. **Luồng xử lý có thể quan sát.** Khi cần chẩn đoán, sử dụng tracing/logging có correlation ID phù hợp, tránh làm rò dữ liệu nhạy cảm.

### Bảng kiểm hợp đồng giữa các bước

Trước khi thêm một tên hàm vào `spring.cloud.function.definition`, lập bảng ngắn:

| Bước | Kiểu nhận | Kiểu trả | Điều kiện dữ liệu | Xử lý lỗi |
|---|---|---|---|---|
| `parseLine` | `String` | `OrderLine` | `SKU-<số>,số lượng > 0` | Ném lỗi dữ liệu |
| `priceOrder` | `OrderLine` | `Quote` | Số lượng hợp lệ, không tràn số | Ném lỗi tính toán |
| `formatQuote` | `Quote` | `String` | Đã có báo giá | Trả chuỗi định dạng |

Bảng kiểm này giúp phát hiện lỗi khi thêm hàm thứ tư, nhất là khi kiểu đầu vào/đầu ra đều là `String` nhưng ý nghĩa khác nhau.

## 10. Kiểm thử thứ tự và kiểu trong Spring Cloud Function

### 10.1. Unit test thứ tự bằng Java thuần

Ta có thể kiểm tra thứ tự thực thi trước khi đưa function vào Spring:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class CompositionOrderTest {

    @Test
    void invokesStepsInDefinedOrder() {
        List<String> trace = new ArrayList<>();

        Function<Integer, Integer> addOne = value -> {
            trace.add("add");
            return value + 1;
        };
        Function<Integer, Integer> doubleValue = value -> {
            trace.add("double");
            return value * 2;
        };

        int actual = addOne.andThen(doubleValue).apply(3);

        assertEquals(8, actual);
        assertEquals(List.of("add", "double"), trace);
    }
}
~~~

Với cùng input `3`, đổi thứ tự sẽ trả `7`. Test này phát hiện cả lỗi **kết quả** và **thứ tự**, thay vì chỉ xác nhận pipeline gọi không ném lỗi.

### 10.2. Integration test với FunctionCatalog

Muốn kiểm tra ghép theo tên, cần một Spring context đã đăng ký các bean `OrderFunctions` và Spring Cloud Function:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class OrderCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void catalogBuildsValidOrderPipeline() {
        Function<String, String> createQuote =
                catalog.lookup("parseLine|priceOrder|formatQuote");

        assertNotNull(createQuote);
        assertEquals(
                "SKU-42 x 2 = 250000 VND",
                createQuote.apply("sku-42,2"));
    }
}
~~~

Đây là ví dụ kiểm thử trong một ứng dụng Spring Boot có cấu hình component scan và dependency test phù hợp. Nó giúp bắt lỗi đổi tên bean, tra cứu sai hoặc ghép sai kiểu ở runtime.

### 10.3. Kiểm thử ranh giới adapter

Nếu cùng pipeline được sử dụng qua HTTP, sự kiện và serverless, cần thử thêm:

| Ranh giới | Điểm cần xác minh |
|---|---|
| HTTP | Kiểu body đầu vào, status code, định dạng kết quả/lỗi |
| Sự kiện | Binding, serialization, content-type, headers, chính sách retry |
| Serverless | Event mapping, handler, cấu trúc phản hồi và xử lý lỗi |
| Reactive | Kiểu Publisher, subscription, thứ tự phần tử khi cần |

Kiểm thử catalog chứng minh được logic ghép trong Spring context, nhưng chưa đảm bảo mọi adapter đã được cấu hình đúng.

## 11. Các lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Kết quả khác mong đợi dù không lỗi | Đảo thứ tự các bước cùng kiểu | Ghi lại input/output trung gian và thử dữ liệu phân biệt được hai thứ tự |
| Code `andThen` không biên dịch | Generic giữa hai bước không khớp | So chữ ký đầu ra/đầu vào từng cặp |
| `lookup` không lấy được pipeline | Tên bean sai hoặc function chưa đăng ký | Kiểm tra `@Bean`, component scan và tên catalog |
| Ghép theo tên được nhưng gọi lỗi | Kiểu trung gian, payload hoặc dữ liệu thực không phù hợp | Test `apply` với input thật; xem thông báo và nguyên nhân lỗi |
| Nhận sai kiểu payload từ HTTP/event | Adapter/serializer/converter không đúng | Xác nhận content-type và cấu hình chuyển đổi |
| Hàm sau không chạy | Hàm trước ném lỗi hoặc reactive stream chưa subscribe | Kiểm tra log, lỗi bước trước và subscription |
| Tác dụng phụ bị lặp | Retry hoặc nhiều lần gọi pipeline | Xem chính sách retry/idempotency và hành vi adapter |

Không nên sửa lỗi kiểu bằng cách ép mọi bước về `Object` hoặc `String`. Làm như vậy thường che khuất hợp đồng dữ liệu, khiến sai sót chuyển sang runtime.

## 12. Bài tập tự luyện

**Bài 1 — Thứ tự thực thi.** Cho:

~~~java
Function<Integer, Integer> increment = n -> n + 1;
Function<Integer, Integer> square = n -> n * n;
~~~

Tính `increment.andThen(square).apply(4)` và `increment.compose(square).apply(4)`. Giải thích kết quả bằng thứ tự gọi.

**Bài 2 — Suy ra kiểu pipeline.** Cho `parse: String → Integer`, `toLong: Integer → Long` và `describe: Number → String`. Hãy xác định kiểu của `parse.andThen(toLong).andThen(describe)` và giải thích vì sao tham số kiểu `Number` của bước cuối phù hợp.

**Bài 3 — Tìm sai hợp đồng.** Cho `readOrder: String → Order`, `validateOrder: Order → ValidationResult`, `calculateTotal: Order → Receipt`. Vì sao `readOrder|validateOrder|calculateTotal` không có hợp đồng nối trực tiếp? Hãy đề xuất cách thiết kế khi nghiệp vụ vẫn cần tính tổng tiền sau xác thực.

**Bài 4 — Kiểm tra dữ liệu không hợp lệ.** Dựa vào ví dụ `OrderFunctions`, mô tả điều gì xảy ra với input `"SKU-42,0"` và `"SKU-42,abc"`. Bước `priceOrder` và `formatQuote` có được gọi không? Bạn sẽ kiểm tra hành vi này thế nào?

**Bài 5 — Triển khai và tích hợp.** Viết `spring.cloud.function.definition` cho ba bước `parseLine`, `priceOrder`, `formatQuote`; sau đó nêu hai kiểm thử bổ sung khi pipeline được gọi thông qua message broker thay vì Java trực tiếp.

### Gợi ý lời giải

- **Bài 1:** `increment.andThen(square).apply(4) = 25`; `increment.compose(square).apply(4) = 17`.
- **Bài 2:** Kiểu tổng thể là `Function<String, String>`; `Long` là kiểu con của `Number`.
- **Bài 3:** `ValidationResult` không phải `Order`. Cần bước chuyển đổi hoặc kết quả validation giữ dữ liệu `Order` đã hợp lệ để có thể tính tiền tiếp.
- **Bài 4:** Cả hai input đều thất bại ở `parseLine`; các bước sau không chạy trong composition đồng bộ thông thường.
- **Bài 5:** `"parseLine|priceOrder|formatQuote"`. Cần kiểm tra serialization/content-type và binding/retry, ngoài việc xác nhận đầu ra nghiệp vụ.

## 13. Ghi nhớ

- Pipeline `A|B|C` thực thi **A → B → C**; về ý nghĩa giống `A.andThen(B).andThen(C)` và `C.compose(B).compose(A)` khi hợp đồng kiểu phù hợp.
- Hai bước nối nhau cần có **kiểu đầu ra/đầu vào tương thích** và **ý nghĩa nghiệp vụ phù hợp**. Chỉ kiểm tra kiểu của đầu vào và đầu ra toàn pipeline là chưa đủ.
- Java generic giúp kiểm tra `andThen`/`compose` tại biên dịch; ghép theo tên qua `FunctionCatalog` phải được kiểm tra thêm ở runtime.
- Lỗi tại bước trước có thể ngăn bước sau chạy; xử lý message, reactive và retry phụ thuộc hợp đồng pipeline và adapter cụ thể.
- Mục tiêu của Spring Cloud Function là giữ logic có thể tái sử dụng giữa HTTP, sự kiện và serverless. Thiết kế hợp đồng từng bước rõ ràng giúp giữ được tính đúng đắn khi đổi môi trường gọi.
