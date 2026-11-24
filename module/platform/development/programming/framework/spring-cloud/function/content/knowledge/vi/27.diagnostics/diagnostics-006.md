# Ghép hàm sai thứ tự hoặc không tương thích kiểu

## 1. Triệu chứng: từng function chạy được nhưng composition thất bại

Một ứng dụng **Spring Cloud Function** có ba bước xử lý đơn hàng:

~~~java
@Bean
public Function<RawOrder, NormalizedOrder> normalizeOrder() {
    return order -> new NormalizedOrder(
        order.orderId().trim().toUpperCase(),
        order.items()
    );
}

@Bean
public Function<NormalizedOrder, PriceQuote> calculatePrice() {
    return order -> new PriceQuote(
        order.orderId(),
        calculateTotal(order.items())
    );
}

@Bean
public Function<PriceQuote, OrderReceipt> renderReceipt() {
    return quote -> new OrderReceipt(
        quote.orderId(),
        quote.total().toPlainString()
    );
}
~~~

Mỗi function có thể hoạt động tốt khi gọi riêng. Nhưng sau khi khai báo:

~~~properties
spring.cloud.function.definition=calculatePrice|normalizeOrder|renderReceipt
~~~

ứng dụng có thể không tạo được pipeline đúng hoặc chỉ phát sinh lỗi khi có dữ liệu chạy qua. Thứ tự ở đây không phù hợp: đầu ra của `calculatePrice` là `PriceQuote`, trong khi `normalizeOrder` cần `RawOrder`.

Các triệu chứng thường gặp:

- Một function riêng lẻ chạy đúng nhưng composition không resolve hoặc lỗi khi invoke.
- `ClassCastException`, `MessageConversionException` hoặc lỗi chuyển đổi kiểu ở giữa pipeline.
- Kết quả khác dự kiến dù tất cả bước đều trả đúng kiểu Java.
- Function đầu tiên chạy nhưng function thứ hai không nhận được dữ liệu mong đợi.
- Một `Consumer` được đặt giữa pipeline khiến bước sau không có dữ liệu đầu vào.
- `Supplier`/`Consumer` bị ghép sai chiều, làm composition không còn kiểu đầu vào/đầu ra mà caller mong đợi.
- Composition imperative chạy nhưng reactive pipeline không phát kết quả do chưa subscribe hoặc sai kiểu phần tử.
- Cấu hình dùng `;` thay vì `|` khiến ứng dụng tạo nhiều function/binding độc lập thay vì một chuỗi tuần tự.

Bài thuộc chương **Chẩn đoán** của module **SPRING_CLOUD_FUNCTION**. Module tập trung phát triển logic nghiệp vụ tái sử dụng bằng `Supplier`, `Function` và `Consumer`, độc lập với giao thức gọi; học `FunctionCatalog`, composition, message conversion và triển khai qua HTTP, sự kiện hoặc serverless.

**Câu hỏi chẩn đoán chính:**

> Đầu ra của mỗi bước có phải là dữ liệu phù hợp với đầu vào của bước kế tiếp, theo đúng thứ tự và đúng hợp đồng thực thi hay không?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu composition tuần tự theo `Function.andThen` và thứ tự trái sang phải.
2. Phân biệt composition với việc chọn nhiều function độc lập trong Spring Cloud Stream hoặc web adapter.
3. Kiểm tra tương thích giữa generic input/output của hai function.
4. Nhận biết khi nào Spring Cloud Function có thể dùng message conversion để nối các kiểu khác nhau.
5. Phân biệt `Function`, `Supplier`, `Consumer` và kiểu kết quả sau khi ghép.
6. Chẩn đoán lỗi do sai thứ tự, sai tên, thiếu bean, converter, message header, reactive stream hoặc side effect.
7. Kiểm thử từng function, composition qua `FunctionCatalog` và adapter thật.
8. Thiết kế pipeline có hợp đồng dữ liệu rõ ràng, dễ quan sát và an toàn khi triển khai.

## 2. Composition nghĩa là gì?

Function composition ghép nhiều bước thành **một luồng xử lý tuần tự**. Kết quả của bước trước trở thành input của bước sau.

~~~mermaid
flowchart LR
    INPUT["RawOrder"] --> A["normalizeOrder"]
    A --> B["calculatePrice"]
    B --> C["renderReceipt"]
    C --> OUTPUT["OrderReceipt"]
~~~

Với các hàm:

- `normalizeOrder`: `Function<RawOrder, NormalizedOrder>`.
- `calculatePrice`: `Function<NormalizedOrder, PriceQuote>`.
- `renderReceipt`: `Function<PriceQuote, OrderReceipt>`.

Ta có pipeline:

~~~text
RawOrder
  → normalizeOrder
  → NormalizedOrder
  → calculatePrice
  → PriceQuote
  → renderReceipt
  → OrderReceipt
~~~

Trong Java, composition của hai `Function` dựa trên `andThen`:

~~~java
Function<RawOrder, OrderReceipt> pipeline =
    normalizeOrder
        .andThen(calculatePrice)
        .andThen(renderReceipt);
~~~

`andThen` có nghĩa là **chạy function hiện tại trước, rồi chuyển kết quả cho function được truyền vào**. Vì vậy:

~~~java
f.andThen(g)
~~~

tương ứng:

~~~text
input → f → output của f → g → output cuối
~~~

Đây không phải xử lý song song, fan-out hoặc gọi nhiều handler độc lập. Nếu cần một function chia dữ liệu thành nhiều output, đó là bài toán function arity/multi-output và có hợp đồng riêng.

### 2.1. Thứ tự là một phần của hợp đồng

Hai function cùng kiểu `String → String` vẫn có thể cho kết quả khác nhau khi đổi thứ tự.

~~~java
Function<String, String> appendSuffix =
    value -> value + "-sig";

Function<String, String> uppercase =
    String::toUpperCase;
~~~

Ghép theo thứ tự:

~~~java
String first = appendSuffix
    .andThen(uppercase)
    .apply("order-1");
~~~

Kết quả:

~~~text
ORDER-1-SIG
~~~

Đổi thứ tự:

~~~java
String second = uppercase
    .andThen(appendSuffix)
    .apply("order-1");
~~~

Kết quả:

~~~text
ORDER-1-sig
~~~

Cả hai pipeline đều tương thích kiểu, nhưng **ngữ nghĩa nghiệp vụ khác nhau**. Không thể chỉ nhìn generic type để kết luận thứ tự đã đúng.

## 3. Các DTO của ví dụ xuyên suốt

Dùng Java 17+ và record để thể hiện hợp đồng từng bước:

~~~java
package demo.composition;

import java.math.BigDecimal;
import java.util.List;

public record RawOrder(
    String orderId,
    List<RawOrderItem> items
) {}

public record RawOrderItem(
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

public record NormalizedOrder(
    String orderId,
    List<RawOrderItem> items
) {}

public record PriceQuote(
    String orderId,
    BigDecimal total
) {}

public record OrderReceipt(
    String orderId,
    String total
) {}
~~~

Trong project thật, đặt mỗi `public record` vào một file Java riêng có cùng tên; code block trên gom các DTO để đọc hợp đồng trong một chỗ.

Ba function:

~~~java
package demo.composition;

import java.util.function.Function;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<RawOrder, NormalizedOrder> normalizeOrder() {
        return order -> new NormalizedOrder(
            order.orderId().trim().toUpperCase(Locale.ROOT),
            order.items()
        );
    }

    @Bean
    public Function<NormalizedOrder, PriceQuote> calculatePrice() {
        return order -> {
            var total = order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

            return new PriceQuote(order.orderId(), total);
        };
    }

    @Bean
    public Function<PriceQuote, OrderReceipt> renderReceipt() {
        return quote -> new OrderReceipt(
            quote.orderId(),
            quote.total().toPlainString()
        );
    }
}
~~~

Ví dụ cố ý dùng type khác nhau cho mỗi bước để việc kiểm tra thứ tự dễ nhìn thấy. Trong ứng dụng thật, mỗi function có thể inject service/repository riêng; điều quan trọng là chữ ký input/output thể hiện đúng dữ liệu.

### 3.1. Định nghĩa composition đúng

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

Hoặc theo cú pháp comma được Spring Cloud Function hỗ trợ:

~~~properties
spring.cloud.function.definition=normalizeOrder,calculatePrice,renderReceipt
~~~

Cả hai cách trên đều mô tả composition tuần tự. Dùng pipe thường dễ đọc hơn vì trực quan thể hiện chuỗi xử lý.

### 3.2. Kết quả sai do đảo thứ tự

~~~properties
spring.cloud.function.definition=calculatePrice|normalizeOrder|renderReceipt
~~~

Sau `calculatePrice`, dữ liệu có kiểu `PriceQuote`. Bước kế là `normalizeOrder`, cần `RawOrder`. Đây là điểm không tương thích.

Nếu converter không có khả năng chuyển `PriceQuote` thành `RawOrder`, invocation sẽ lỗi ở ranh giới đó. Ngay cả khi có converter tổng quát có thể chuyển đổi về mặt kỹ thuật, pipeline vẫn sai ngữ nghĩa vì một báo giá không chứa danh sách dòng hàng gốc.

**Không sửa lỗi này bằng cách đổi DTO tùy tiện chỉ để composition chạy.** Hãy khôi phục đúng thứ tự nghiệp vụ hoặc thiết kế một bước chuyển đổi có ý nghĩa và được kiểm thử.

## 4. Quy tắc tương thích kiểu giữa hai Function

Với Java Function:

~~~java
Function<A, B> first;
Function<C, D> second;
~~~

Cách ghép trực tiếp bằng `first.andThen(second)` yêu cầu output `B` có thể được truyền vào input `C`. Trường hợp đơn giản nhất là:

~~~text
B == C
~~~

hoặc kiểu đầu ra có thể gán cho kiểu đầu vào theo quy tắc type system của Java.

Ví dụ hợp lệ:

~~~java
Function<RawOrder, NormalizedOrder> normalize = ...;
Function<NormalizedOrder, PriceQuote> calculate = ...;

Function<RawOrder, PriceQuote> pipeline =
    normalize.andThen(calculate);
~~~

Ví dụ không hợp lệ về kiểu Java:

~~~java
Function<PriceQuote, NormalizedOrder> wrong =
    calculate.andThen(normalize); // Không compile.
~~~

`calculate` trả `PriceQuote`, còn `normalize` nhận `RawOrder`. Java compiler phát hiện mismatch ngay tại thời điểm biên dịch.

### 4.1. Spring Cloud Function có thể chuyển đổi giữa hai kiểu

Composition qua `FunctionCatalog` có thêm khả năng chuyển đổi kiểu. Theo tài liệu Spring Cloud Function, content-type negotiation có thể chuyển đổi dữ liệu trong quá trình composition, giúp một số function vốn không thể ghép trực tiếp theo kiểu Java vẫn có thể kết nối khi converter phù hợp.

Điều đó không có nghĩa mọi kiểu đều chuyển được.

Ví dụ:

- `Function<String, OrderEvent>` trả JSON text có thể chuyển thành kiểu mà bước sau yêu cầu nếu converter và content type hỗ trợ.
- `Function<Map<String,Object>, OrderEvent>` có thể được nối nếu payload map có cấu trúc tương thích với DTO và conversion được hỗ trợ.
- `Function<PriceQuote, RawOrder>` không nên được giả định chuyển đổi được chỉ vì cả hai là Java object. Nếu không có converter hoặc dữ liệu cần thiết không tồn tại, pipeline sẽ thất bại.

### 4.2. Phân biệt hai loại tương thích

| Loại | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Tương thích Java | Có thể truyền trực tiếp output vào input? | `NormalizedOrder → NormalizedOrder` |
| Tương thích qua converter | Framework có converter cho payload/type/contentType? | JSON String → `OrderEvent` |
| Tương thích nghiệp vụ | Dữ liệu có đủ ý nghĩa để bước sau xử lý đúng? | `PriceQuote` không thể thay `RawOrder` nếu thiếu line items |

Một composition chỉ chạy qua converter **không tự động đúng nghiệp vụ**. Hãy kiểm tra cả schema và ý nghĩa dữ liệu.

## 5. Cách Spring Cloud Function ghép qua FunctionCatalog

Spring Cloud Function chuẩn hóa các function do người dùng khai báo thành biểu diễn thống nhất trong `FunctionCatalog`. Khi lookup qua catalog, function nhận được có thể được wrap để hỗ trợ type conversion, composition và các tính năng của framework.

~~~java
FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

Object pipeline =
    catalog.lookup("normalizeOrder|calculatePrice|renderReceipt");
~~~

Ví dụ lookup theo kiểu tổng quát:

~~~java
Function<?, ?> pipeline =
    (Function<?, ?>) catalog.lookup(
        "normalizeOrder|calculatePrice|renderReceipt"
    );
~~~

Trong code thực tế, cần cast theo input/output đã biết hoặc dùng wrapper/API phù hợp với phiên bản SCF. `FunctionCatalog.lookup` không thay thế việc kiểm tra hợp đồng kiểu.

### 5.1. Vì sao lấy bean trực tiếp khác lấy từ catalog?

~~~java
Function<RawOrder, NormalizedOrder> original =
    applicationContext.getBean("normalizeOrder", Function.class);

Function<?, ?> wrapped =
    catalog.lookup("normalizeOrder");
~~~

Bean gốc là object như đã khai báo. Function lấy từ catalog được framework instrument và có thể hỗ trợ conversion/composition. Nếu tự lấy bean gốc rồi gọi theo cách bỏ qua wrapper, không nên kỳ vọng toàn bộ khả năng conversion của SCF vẫn áp dụng.

### 5.2. Kiểm tra từng tên trước khi kiểm tra chuỗi

~~~java
Set<String> names = catalog.getNames(null);

assert names.contains("normalizeOrder");
assert names.contains("calculatePrice");
assert names.contains("renderReceipt");
~~~

Nếu một function không có trong catalog, composition không thể tìm thấy mắt xích đó. Nhưng nếu tất cả tên đều có, vẫn phải kiểm tra **thứ tự và tương thích kiểu**.

### 5.3. Đừng nhầm lookup thành công với invocation thành công

Một composition có thể được tạo hoặc tra cứu thành công nhưng lỗi chỉ xuất hiện khi có payload thật đi qua converter hoặc business function. Hãy kiểm tra cả:

1. Tên từng function có tồn tại.
2. Composition definition được nhận diện.
3. Function đầu tiên nhận đúng input.
4. Đầu ra của từng bước phù hợp bước kế tiếp.
5. Kết quả cuối có đúng type/format.
6. Side effect chỉ xảy ra đúng một lần theo thiết kế.

## 6. Sai thứ tự: dấu hiệu và cách sửa

Một pipeline có thể sai thứ tự theo nhiều cách:

| Sai sót | Ví dụ | Hậu quả |
| --- | --- | --- |
| Validation trước normalization | validate raw input chưa trim | Dữ liệu hợp lệ bị từ chối hoặc rule không áp dụng |
| Persist trước enrichment | lưu order trước khi gắn tenant/audit data | Record thiếu metadata |
| Render trước pricing | tạo receipt khi chưa có quote | Thiếu total |
| Serialize trước business processing | biến DTO thành JSON quá sớm | Các bước sau phải parse lại |
| Consumer trước function | side effect kết thúc pipeline | Không còn output cho bước kế |
| Retry/de-duplicate đặt sai chỗ | retry sau side effect không idempotent | Tạo tác dụng phụ trùng |

### 6.1. Ví dụ normalize và validate

~~~java
@Bean
Function<String, String> normalizeCode() {
    return value -> value == null ? "" : value.trim().toUpperCase();
}

@Bean
Function<String, Boolean> validateCode() {
    return value -> value.matches("[A-Z]{3}-[0-9]{4}");
}
~~~

Composition đúng:

~~~properties
spring.cloud.function.definition=normalizeCode|validateCode
~~~

Input `" abc-1234 "` được chuẩn hóa thành `"ABC-1234"` rồi mới validate.

Nếu đảo:

~~~properties
spring.cloud.function.definition=validateCode|normalizeCode
~~~

thì function đầu tiên trả `Boolean`, function sau lại nhận `String`. Đây là mismatch kiểu, không chỉ là khác kết quả.

### 6.2. Ví dụ hai bước cùng kiểu nhưng sai logic

~~~java
@Bean
Function<String, String> appendSignature() {
    return value -> value + "-sig";
}

@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Hai definition:

~~~properties
spring.cloud.function.definition=appendSignature|uppercase
~~~

và:

~~~properties
spring.cloud.function.definition=uppercase|appendSignature
~~~

đều hợp lệ về kiểu `String → String` nhưng có thể cho output khác nhau về chữ hoa/thường của suffix. Khi không có lỗi type, hãy so sánh **kết quả kỳ vọng của từng bước**, không chỉ kiểm tra pipeline có chạy.

## 7. Dấu phân cách: composition khác danh sách function độc lập

Một nguồn nhầm lẫn phổ biến là dùng sai delimiter trong `spring.cloud.function.definition`.

### 7.1. Trong Spring Cloud Function, pipe hoặc comma biểu thị composition

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

hoặc:

~~~properties
spring.cloud.function.definition=normalizeOrder,calculatePrice
~~~

Đây là một định nghĩa ghép: output của `normalizeOrder` chuyển sang `calculatePrice`.

### 7.2. Trong Spring Cloud Stream, dấu chấm phẩy chọn nhiều function độc lập

Giả sử ứng dụng có hai handler riêng:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

Cấu hình:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Trong Spring Cloud Stream, dấu `;` chọn hai function riêng để bind. Nó không biểu thị output của `uppercase` đi vào `reverse`.

### 7.3. Web adapter cũng dùng danh sách export riêng

Với Spring Cloud Function web adapter, `;` có thể liệt kê các function/composition cần export. Ví dụ:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice;renderReceipt
~~~

Cấu hình này biểu thị composition `normalizeOrder|calculatePrice` và function độc lập `renderReceipt` được chọn theo quy tắc export của web adapter.

| Cú pháp | Ý nghĩa thường gặp |
| --- | --- |
| `a|b` | Ghép tuần tự a rồi b |
| `a,b` | Dấu phân cách composition được SCF hỗ trợ |
| `a;b` trong Stream | Chọn nhiều function độc lập để bind |
| `a;b` trong web export | Liệt kê nhiều function/composition cần export |

**Không suy nghĩa dấu phân cách ngoài ngữ cảnh adapter.** Nếu thấy hai function chạy trên hai binding độc lập, hãy xem binding name; nếu muốn pipeline trong cùng JVM, hãy khai báo composition.

## 8. Function, Supplier và Consumer không có cùng quy tắc ghép

Spring Cloud Function hỗ trợ một số tổ hợp không chỉ gồm Function.

| Tổ hợp | Kiểu kết quả sau ghép | Ý nghĩa |
| --- | --- | --- |
| `Function<I,M>` + `Function<M,O>` | `Function<I,O>` | Chuỗi biến đổi |
| `Supplier<T>` + `Function<T,R>` | `Supplier<R>` | Nguồn tạo T rồi biến đổi thành R |
| `Supplier<T>` + `Consumer<T>` | `Runnable` | Nguồn tạo T rồi tiêu thụ |
| `Function<I,T>` + `Consumer<T>` | `Consumer<I>` | Nhận I, biến đổi rồi tiêu thụ T |
| `Consumer<T>` + `Function<T,R>` | Không hỗ trợ như composition chuẩn | Consumer không có output để truyền tiếp |
| `Consumer<T>` + `Supplier<R>` | Không hỗ trợ như composition chuẩn | Consumer không tạo dữ liệu cho Supplier |

### 8.1. Supplier → Function

~~~java
@Bean
Supplier<String> currentStatus() {
    return () -> "pending";
}

@Bean
Function<String, StatusEvent> toStatusEvent() {
    return value -> new StatusEvent(value, Instant.now());
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=currentStatus|toStatusEvent
~~~

Kết quả về mặt hợp đồng vẫn là `Supplier<StatusEvent>`: mỗi lần nguồn được gọi, giá trị được tạo rồi chuyển qua function.

### 8.2. Supplier → Consumer

~~~java
@Bean
Supplier<String> currentStatus() {
    return () -> "pending";
}

@Bean
Consumer<String> publishStatus() {
    return status -> statusPublisher.publish(status);
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=currentStatus|publishStatus
~~~

Đây là một thao tác tương đương `Runnable`: không có input từ caller và không trả output payload.

### 8.3. Function → Consumer

~~~java
@Bean
Function<OrderEvent, NormalizedOrder> normalizeOrder() {
    return order -> normalize(order);
}

@Bean
Consumer<NormalizedOrder> persistOrder() {
    return repository::save;
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=normalizeOrder|persistOrder
~~~

Kết quả là `Consumer<OrderEvent>`: nhận đơn hàng, chuẩn hóa rồi lưu; caller không nhận một `NormalizedOrder` làm output.

### 8.4. Vì sao Consumer không thể đứng giữa pipeline?

`Consumer<T>` có phương thức `accept(T)` trả `void`. Nó là điểm cuối tiêu thụ dữ liệu. Không có output `R` để chuyển cho một function kế tiếp.

Nếu cần vừa lưu vừa tiếp tục pipeline, hãy viết một `Function<T,T>` hoặc `Function<T,R>` có output rõ ràng:

~~~java
@Bean
Function<NormalizedOrder, NormalizedOrder> persistAndReturn() {
    return order -> {
        repository.save(order);
        return order;
    };
}
~~~

Cách này thể hiện side effect nhưng vẫn giữ dữ liệu cho bước kế tiếp. Cần bảo đảm thao tác lưu có idempotency và transaction semantics phù hợp.

## 9. Composition qua Java andThen và composition khai báo của SCF

Hai cách có quan hệ nhưng không hoàn toàn giống nhau.

### 9.1. Java andThen

~~~java
Function<RawOrder, NormalizedOrder> normalize = ...;
Function<NormalizedOrder, PriceQuote> calculate = ...;
Function<PriceQuote, OrderReceipt> render = ...;

Function<RawOrder, OrderReceipt> pipeline =
    normalize.andThen(calculate).andThen(render);
~~~

Java compiler kiểm tra kiểu giữa các bước. Nếu output và input không khớp, code không compile.

### 9.2. SCF declarative composition

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

SCF tìm function theo tên trong catalog và xây dựng composition wrapper. Ngoài thứ tự, framework còn có thể thực hiện conversion ở các ranh giới khi content type và type metadata cho phép.

### 9.3. Vì sao declarative composition có thể chạy dù Java andThen không ghép trực tiếp?

Ví dụ:

~~~java
Function<String, OrderEvent> parseJson = ...;
Function<OrderEvent, OrderReceipt> acceptOrder = ...;
~~~

Java andThen yêu cầu output của function đầu có thể truyền vào input function sau. Trong ví dụ, hai bước có thể ghép trực tiếp vì `OrderEvent` khớp.

Một trường hợp khác:

~~~java
Function<String, String> parseText = ...;
Function<OrderEvent, OrderReceipt> acceptOrder = ...;
~~~

Java không thể ghép trực tiếp `String` với `OrderEvent`. Tuy nhiên, nếu output String là JSON, metadata content type phù hợp và SCF có converter tương ứng, declarative composition có thể chuyển đổi dữ liệu giữa các bước.

**Không coi khả năng conversion là bảo đảm chung.** Nếu converter không hỗ trợ định dạng/target, hoặc content type không mô tả đúng payload, composition vẫn lỗi.

## 10. Content-Type negotiation trong composition

Spring Cloud Function dùng hai cơ chế Spring để chuyển dữ liệu vào function:

- `MessageConverter` khi dữ liệu được truyền dưới dạng `Message<?>`.
- `ConversionService` khi dữ liệu đầu vào không phải Message.

Đối với các request HTTP hoặc messaging, adapter thường tạo Spring Message. Chữ ký function cung cấp target type; header `contentType` giúp chọn converter phù hợp.

Vì vậy khi composition lỗi ở ranh giới giữa hai function, cần xác định payload đang được chuyển như `Message` hay dữ liệu Java thông thường. Với Message, kiểm tra converter và header; với non-Message, kiểm tra `ConversionService` và kiểu runtime của object.

### 10.1. Tình huống JSON giữa hai bước

Giả sử:

~~~java
@Bean
Function<OrderEvent, String> serializeOrder() {
    return event -> objectMapper.writeValueAsString(event);
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> process(event);
}
~~~

Nếu function đầu trả `String` chứa JSON, bước sau cần `OrderEvent`. Để converter có thể chuyển, pipeline cần metadata content type phù hợp và converter JSON tương ứng. Nếu chuỗi bị xem là `text/plain`, SCF không nên được kỳ vọng tự parse thành OrderEvent.

Thiết kế dễ hiểu hơn thường là **không serialize giữa hai function nội bộ**:

~~~java
Function<OrderEvent, NormalizedOrder>
    .andThen(Function<NormalizedOrder, PriceQuote>)
~~~

Giữ object có kiểu qua pipeline và chỉ serialize ở biên transport.

### 10.2. Content type và argument type phải đồng thời phù hợp

| Dữ liệu trung gian | Target bước kế | Điều cần kiểm tra |
| --- | --- | --- |
| `OrderEvent` object | `OrderEvent` | Có thể truyền trực tiếp |
| JSON `String` | `OrderEvent` | `contentType=application/json` và JSON converter |
| `byte[]` JSON | `OrderEvent` | Content type/encoding và converter |
| `Map<String,Object>` | `OrderEvent` | Converter hỗ trợ Map → DTO hoặc mapping rõ |
| `PriceQuote` | `RawOrder` | Không giả định có converter hoặc ý nghĩa tương đương |

### 10.3. Message headers có thể bị thay đổi giữa các bước

Một function có thể nhận `Message<T>` và trả `Message<R>`. Khi composition, cần xem payload và headers mà bước kế tiếp thực sự nhận được.

Không mặc định tất cả input headers tự động được giữ qua output. Nếu bước sau cần correlation ID hoặc content type đặc biệt, hãy truyền chọn lọc và kiểm thử.

## 11. Chẩn đoán từng bước thay vì chỉ nhìn definition tổng

Khi composition lỗi, kiểm tra theo thứ tự:

1. Mỗi tên function có tồn tại trong catalog không?
2. Mỗi function riêng có chạy đúng với input hợp đồng không?
3. Thứ tự trong definition có đúng quy trình nghiệp vụ không?
4. Output type của bước i có khớp input type bước i+1 không?
5. Nếu không khớp, có converter hỗ trợ và content type chính xác không?
6. Có bước nào là `Consumer` làm pipeline kết thúc sớm không?
7. Có `Supplier` ở đầu chuỗi nhưng caller lại mong input từ request không?
8. Nếu reactive, generic của từng item và subscription có đúng không?
9. Có routing/header/definition khác ghi đè composition dự kiến không?
10. Adapter đang chạy có sử dụng đúng definition và binding không?

### 11.1. Bảng dấu hiệu nhanh

| Triệu chứng | Nghi vấn | Kiểm tra đầu tiên |
| --- | --- | --- |
| `NoSuchBeanDefinition` hoặc không tìm thấy function | Sai tên hoặc bean chưa đăng ký | `catalog.getNames(null)` |
| Composition lookup không resolve | Tên thành phần/definition sai | Lookup từng tên riêng |
| Lỗi ngay khi gọi bước thứ hai | Output/input mismatch hoặc converter | Runtime payload type |
| Kết quả sai nhưng không exception | Thứ tự logic sai | Gọi từng function và so output |
| Pipeline không trả output | Consumer ở cuối hoặc giữa | Kiểu kết quả composition |
| Supplier chạy nhưng không nhận request input | Supplier là nguồn, không có input | Chọn Function/Consumer nếu cần input |
| JSON giữa các bước thành String/Map | Content type hoặc target type | Message headers và generic signature |
| Reactive pipeline không phát dữ liệu | Chưa subscribe hoặc nguồn chưa phát | StepVerifier, adapter lifecycle |
| Chỉ Stream binding lỗi | Definition/binding name/binder | Startup binding logs |
| HTTP route không đúng | Web export/definition/path | Mapping và effective properties |

## 12. Sơ đồ chẩn đoán composition

~~~mermaid
flowchart TD
    START["Composition lỗi hoặc kết quả sai"] --> NAMES{"Từng function có trong catalog?"}
    NAMES -->|Không| REG["Kiểm tra bean name, scan,\nregistration và definition"]
    NAMES -->|Có| ORDER{"Thứ tự nghiệp vụ đúng?"}
    ORDER -->|Không| REORDER["Sắp xếp lại pipeline"]
    ORDER -->|Có| TYPES{"Output bước trước phù hợp input bước sau?"}
    TYPES -->|Có| INVOKE["Gọi từng bước rồi gọi composition"]
    TYPES -->|Không| CONVERT{"Có converter phù hợp?"}
    CONVERT -->|Không| CONTRACT["Sửa chữ ký hoặc thêm mapping có kiểu rõ"]
    CONVERT -->|Có| CONTENT["Kiểm tra contentType,\nMessage headers và metadata"]
    INVOKE --> REACTIVE{"Có reactive signature?"}
    REACTIVE -->|Có| SUBSCRIBE["Kiểm tra subscribe,\nitem type và terminal signal"]
    REACTIVE -->|Không| ADAPTER["Kiểm tra HTTP / Stream /\nserverless adapter"]
    REG --> VERIFY["Test lại từng bước và toàn pipeline"]
    REORDER --> VERIFY
    CONTRACT --> VERIFY
    CONTENT --> VERIFY
    SUBSCRIBE --> VERIFY
    ADAPTER --> VERIFY
~~~

## 13. FunctionCatalog và fallback tên: tránh chẩn đoán nhầm

Khi catalog chỉ có một functional bean, single-function fallback có thể trả function duy nhất cho một tên lookup không chính xác. Do đó:

~~~java
catalog.lookup("calculatePrce");
~~~

có thể không đủ để chứng minh đã có function tên `calculatePrce` nếu catalog chỉ có một candidate.

Kiểm tra inventory:

~~~java
Set<String> names = catalog.getNames(null);

boolean exists =
    names.contains("calculatePrice");
~~~

Trong môi trường cần tên chính xác, có thể tắt fallback:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

### 13.1. Một function bị thiếu có thể bị che khi catalog chỉ có một candidate

Nếu composition chứa nhiều bước, lỗi tên trong một chuỗi thường vẫn phải được xác minh theo từng mắt xích. Đừng suy từ việc một lookup tên sai trả function rằng cả composition đã đúng. Kiểm tra **từng tên**, sau đó kiểm tra composition đầy đủ.

### 13.2. Đọc definition runtime

~~~java
String definition = environment.getProperty(
    "spring.cloud.function.definition",
    "<unset>"
);

log.info("function.definition={}", definition);
~~~

Property trong file local có thể bị profile, environment variable hoặc command-line argument ghi đè. Hãy log giá trị hiệu lực và không in toàn bộ environment chứa secret.

## 14. Sai loại function: Supplier, Function, Consumer

Không phải mọi bean functional đều có thể xếp nối theo bất kỳ thứ tự nào.

| Interface | Input | Output | Vai trò |
| --- | --- | --- | --- |
| `Supplier<T>` | Không có | `T` | Tạo dữ liệu |
| `Function<I,O>` | `I` | `O` | Biến đổi dữ liệu |
| `Consumer<T>` | `T` | Không có | Tiêu thụ/side effect |

### 14.1. Composition hợp lệ

~~~text
Supplier<OrderEvent>
    → Function<OrderEvent, NormalizedOrder>
    → Consumer<NormalizedOrder>
~~~

Kết quả cuối tương đương một `Runnable` vì không có input từ caller và không trả output.

~~~text
Function<RawOrder, NormalizedOrder>
    → Consumer<NormalizedOrder>
~~~

Kết quả cuối tương đương `Consumer<RawOrder>`.

### 14.2. Composition không hợp lệ

~~~text
Consumer<NormalizedOrder>
    → Function<NormalizedOrder, PriceQuote>
~~~

Consumer không trả `NormalizedOrder`; không có giá trị để function sau nhận.

~~~text
Consumer<NormalizedOrder>
    → Supplier<PriceQuote>
~~~

Consumer cũng không tạo input cho Supplier. Đây không phải composition tuần tự chuẩn được Spring Cloud Function hỗ trợ.

### 14.3. Cần vừa tiêu thụ vừa trả dữ liệu?

Dùng Function thay vì Consumer:

~~~java
@Bean
Function<NormalizedOrder, NormalizedOrder> persistOrder() {
    return order -> {
        repository.save(order);
        return order;
    };
}
~~~

Nếu chỉ muốn lưu và kết thúc, Consumer là đúng. Nếu muốn bước kế tiếp dùng dữ liệu, phải khai báo output.

## 15. Reactive composition: ghép stream theo kiểu phần tử

Spring Cloud Function hỗ trợ reactive API của Project Reactor. Một reactive function được gọi để nhận publisher; việc xử lý phần tử diễn ra khi publisher được subscribe.

~~~java
@Bean
Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeStream() {
    return orders -> orders.map(order ->
        new NormalizedOrder(
            order.orderId().trim().toUpperCase(),
            order.items()
        )
    );
}

@Bean
Function<Flux<NormalizedOrder>, Flux<PriceQuote>> priceStream() {
    return orders -> orders.map(order ->
        new PriceQuote(order.orderId(), calculateTotal(order.items()))
    );
}
~~~

Composition:

~~~properties
spring.cloud.function.definition=normalizeStream|priceStream
~~~

Ở đây phải khớp **kiểu phần tử** `NormalizedOrder`, không chỉ kiểu outer `Flux`.

### 15.1. Sai generic phần tử

~~~java
Function<Flux<Object>, Flux<Object>>
~~~

không tương đương:

~~~java
Function<Flux<NormalizedOrder>, Flux<PriceQuote>>
~~~

Nếu registration làm mất nested generic, converter có thể không biết phải tạo object nào cho từng phần tử.

### 15.2. Lỗi chỉ xuất hiện khi subscribe

~~~java
Flux<PriceQuote> result =
    priceStream.apply(input);
~~~

Nếu `input` là cold publisher, function body có thể chưa xử lý item cho tới khi có subscription. Lỗi type hoặc business exception có thể phát thành `onError` muộn.

Test bằng `StepVerifier`:

~~~java
StepVerifier.create(
        normalizeStream().andThen(priceStream())
            .apply(Flux.just(
                new RawOrder(" ord-1 ", List.of())
            ))
    )
    .expectNextMatches(quote ->
        quote.orderId().equals("ORD-1")
    )
    .verifyComplete();
~~~

Ví dụ này kiểm tra composition reactive với input POJO đã đúng kiểu. Nó chưa chứng minh HTTP/Kafka bytes được chuyển thành `RawOrder`/`NormalizedOrder`; cần integration test adapter.

### 15.3. Imperative và reactive không cùng đơn vị gọi

Với imperative function, adapter thường gọi function cho từng event. Với reactive function, adapter đưa một publisher cho function; pipeline xử lý nhiều event bên trong stream.

Có thể ghép function imperative và reactive khi hợp đồng và adapter hỗ trợ, nhưng phải test kiểu payload, lifecycle và subscription. Không chuyển qua lại `T` và `Flux<T>` tùy tiện rồi mong composition tự hiểu ý định.

## 16. Message composition: payload, headers và content type

Một function có thể dùng `Message<T>` khi cần metadata:

~~~java
@Bean
Function<Message<OrderEvent>, Message<NormalizedOrder>> enrichOrder() {
    return message -> MessageBuilder.withPayload(
        normalize(message.getPayload())
    )
    .setHeader(
        "correlationId",
        message.getHeaders().get("correlationId")
    )
    .build();
}
~~~

Khi ghép với function kế tiếp, hãy xác minh:

- Payload output có đúng kiểu input kế tiếp?
- Header correlation ID có được giữ nếu cần?
- `contentType` có còn mô tả đúng payload mới?
- Có header routing nào bị copy không chủ đích?
- Adapter có chuyển đổi payload qua converter phù hợp không?

### 16.1. Input header không mặc định luôn được truyền tiếp

Spring Cloud Function không mặc định propagate mọi input headers ra output trong mọi trường hợp. Nếu cần giữ header, có thể trả `Message` và copy có chọn lọc hoặc dùng cấu hình `copy-input-headers` phù hợp.

Không copy nguyên header không kiểm soát: header cũ có thể không còn đúng với payload mới hoặc mang routing instruction không nên truyền tiếp.

### 16.2. Conversion trong composition

Tài liệu SCF mô tả content-type negotiation có thể chuyển đổi dữ liệu không chỉ lúc function nhận request mà cả **giữa các bước composition**. Converter cần biết target type và content type phù hợp.

Nếu output của bước A là `String` JSON nhưng bước B yêu cầu `OrderEvent`, hãy xác minh `contentType` và converter. Thiết kế nội bộ thường tốt hơn khi giữ POJO typed xuyên pipeline và chỉ serialize tại biên transport.

## 17. Function routing có thể ghi đè chuỗi composition dự kiến

Spring Cloud Function có `functionRouter` trong catalog. Routing instructions có thể đến từ application properties hoặc message headers, tùy loại function và cơ chế adapter.

Ví dụ header:

~~~text
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

Một request/message có thể chọn function hoặc composition theo routing instruction. Nếu hệ thống có routing callback, header hoặc property ghi đè, function thực tế chạy có thể khác definition mà developer đang xem trong file cấu hình.

### 17.1. Thứ tự ưu tiên routing

Theo tài liệu SCF hiện hành, khi nhiều cơ chế cùng cung cấp routing instruction, thứ tự ưu tiên gồm:

1. `MessageRoutingCallback` đối với imperative function.
2. Message headers nếu là imperative function và không có callback.
3. Application properties.

Với reactive function, routing được áp dụng cho **toàn stream** thông qua application properties; không route riêng từng message bằng header.

### 17.2. Kiểm tra target thực tế

- Giá trị `spring.cloud.function.definition` hiệu lực.
- Header routing thực sự đến function.
- `MessageRoutingCallback` được đăng ký không.
- Function target và composition có trong catalog không.
- Input type của target có khớp payload không.
- Routing instruction có bị client không tin cậy điều khiển không.

Routing sai có thể trông giống composition sai thứ tự vì pipeline thực tế không phải pipeline developer mong đợi.

### 17.3. Không cho caller chọn tùy ý function nội bộ

Nếu header HTTP hoặc message broker cho phép chọn composition, hãy dùng allowlist theo quyền/capability và bảo vệ endpoint/broker. Không đưa expression động không tin cậy vào routing configuration. Ghi audit target được chọn, không log dữ liệu nhạy cảm.

## 18. Spring Cloud Stream: composition và binding names

Spring Cloud Stream sử dụng Spring Cloud Function làm programming model. Khi chọn composition:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice
~~~

adapter tạo binding cho **composition** theo quy tắc binding name của Stream, thay vì coi hai function là hai consumer độc lập.

Nếu muốn bind hai function riêng:

~~~properties
spring.cloud.function.definition=normalizeOrder;calculatePrice
~~~

Trong trường hợp này, mỗi function có input/output binding riêng. Dấu `;` là danh sách nhiều function độc lập trong ngữ cảnh Stream.

### 18.1. Đừng dùng binding name làm function name

Ví dụ với function `normalizeOrder`:

~~~text
normalizeOrder-in-0
normalizeOrder-out-0
~~~

Đây là binding names, còn `normalizeOrder` là tên function trong catalog. Với composition, tên binding được tạo dựa trên definition/composition và convention của Stream.

### 18.2. Kiểm tra theo ba lớp

| Lớp | Cần xác minh |
| --- | --- |
| Catalog | Các function thành phần có tên đúng? |
| Definition | Pipe/comma tạo đúng thứ tự composition? |
| Binding/broker | Input/output binding, destination và binder đúng? |

Nếu function chạy đúng khi gọi trực tiếp nhưng Stream không nhận message, có thể lỗi nằm ở binding/destination chứ không phải type composition.

### 18.3. Message conversion và native decoding

Nếu Stream nhận payload qua native deserializer, kiểu runtime có thể đã là Map/bytes trước khi function wrapper chuyển đổi. Hãy kiểm tra content type, generic signatures và `useNativeDecoding`. Đừng giả định composition sẽ tự sửa mọi kiểu dữ liệu từ broker.

## 19. HTTP và serverless: cùng composition nhưng khác đường vào

### 19.1. HTTP adapter

Web adapter có thể export một function hoặc một composition thành endpoint. Ví dụ definition:

~~~properties
spring.cloud.function.definition=normalizeOrder|calculatePrice|renderReceipt
~~~

Một request tới route được export sẽ đi qua adapter, message conversion, composition wrapper và các bước nghiệp vụ. Nếu lỗi chỉ xuất hiện ở HTTP:

- Kiểm tra route và definition thực tế.
- Kiểm tra HTTP Content-Type.
- Kiểm tra payload type tại function đầu tiên.
- Xác minh output của từng bước.
- Kiểm tra security và routing headers.

HTTP 404 không chứng minh composition sai kiểu; có thể chỉ là route chưa được export.

### 19.2. Serverless adapter

Trong serverless, handler nhận event và chọn business function/composition. Cần phân biệt:

- Handler/entry point của platform.
- Tên function hoặc composition trong `FunctionCatalog`.
- Event envelope và business payload.
- Runtime property chọn function.
- Retry/timeout và side effect của từng bước.

Một event có thể là envelope chứa `body` thay vì `RawOrder` trực tiếp. Nếu composition đầu tiên mong `RawOrder`, adapter cần đưa đúng payload vào.

### 19.3. Đừng sửa composition để bù cho event envelope sai

Nếu adapter chuyển toàn bộ event envelope trong khi function đầu mong DTO nghiệp vụ, hãy sửa event mapping/adapter hoặc thêm bước unwrap có kiểu rõ ràng. Đổi thứ tự function không giải quyết được sai schema ở đầu vào.

## 20. Lỗi thường gặp và cách đọc stack trace

| Exception/triệu chứng | Nguyên nhân có thể | Bằng chứng |
| --- | --- | --- |
| Function not found | Tên thành phần sai/bean chưa đăng ký | `catalog.getNames(null)` |
| `ClassCastException` | Output bước trước không phải input bước sau | Runtime payload class |
| `MessageConversionException` | Converter không chuyển được giữa hai kiểu | Content type, generic type, converter |
| `IllegalArgumentException` trong business code | Function nhận dữ liệu đúng kiểu nhưng sai giá trị | Input/output từng bước |
| Output null | Một function trả null hoặc terminal semantics | Trace từng bước |
| Không có output sau Consumer | Consumer là bước kết thúc | Chữ ký composition |
| Reactive `onError` khi subscribe | Lỗi xảy ra trong stream | `StepVerifier` và operator stack |
| HTTP 404 | Route/definition không export | Web mapping |
| Stream không tạo binding | Definition/list/binding config sai | Startup logs |
| Kết quả sai nhưng không lỗi | Thứ tự nghiệp vụ sai | Expected vs actual từng bước |

### 20.1. Log theo ranh giới

Có thể thêm log tạm thời vào function:

~~~java
@Bean
Function<RawOrder, NormalizedOrder> normalizeOrder() {
    return order -> {
        log.debug("normalize input orderId={}", order.orderId());
        NormalizedOrder result = normalize(order);
        log.debug("normalize output orderId={}", result.orderId());
        return result;
    };
}
~~~

Trong production, không log toàn bộ payload nếu chứa thông tin khách hàng, dữ liệu thanh toán hoặc bí mật. Ưu tiên correlation ID, function name, payload type, thời gian xử lý và trạng thái.

### 20.2. Xác định bước đầu tiên lỗi

Nếu log cho thấy:

~~~text
normalizeOrder: completed
calculatePrice: failed
renderReceipt: not invoked
~~~

thì tập trung vào output của `normalizeOrder` và input của `calculatePrice`. Không sửa `renderReceipt` vì nó chưa được gọi.

## 21. Test từng function trước, rồi test composition

Dùng JUnit 5 và AssertJ. Các function có thể được tách thành class/service để unit test độc lập; ví dụ đơn giản:

~~~java
class OrderPipelineTest {

    private final Function<RawOrder, NormalizedOrder> normalize =
        order -> new NormalizedOrder(
            order.orderId().trim().toUpperCase(),
            order.items()
        );

    private final Function<NormalizedOrder, PriceQuote> calculate =
        order -> new PriceQuote(
            order.orderId(),
            order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
        );

    private final Function<PriceQuote, OrderReceipt> render =
        quote -> new OrderReceipt(
            quote.orderId(),
            quote.total().toPlainString()
        );

    @Test
    void eachStageHasExpectedContract() {
        RawOrder raw = sampleOrder();

        NormalizedOrder normalized = normalize.apply(raw);
        assertThat(normalized.orderId()).isEqualTo("ORD-101");

        PriceQuote quote = calculate.apply(normalized);
        assertThat(quote.orderId()).isEqualTo("ORD-101");

        OrderReceipt receipt = render.apply(quote);
        assertThat(receipt.total()).isNotBlank();
    }

    @Test
    void compositionRunsInTheExpectedOrder() {
        Function<RawOrder, OrderReceipt> pipeline =
            normalize.andThen(calculate).andThen(render);

        OrderReceipt result = pipeline.apply(sampleOrder());

        assertThat(result.orderId()).isEqualTo("ORD-101");
    }
}
~~~

Các helper `sampleOrder()` và import DTO/`BigDecimal`/AssertJ/JUnit được bổ sung trong test class thật. Ví dụ cho thấy unit test Java giữ type safety trước khi kiểm tra SCF catalog.

### 21.1. Test sai thứ tự không compile

~~~java
// Không compile: calculate trả PriceQuote,
// nhưng normalize cần RawOrder.
var invalid = calculate.andThen(normalize);
~~~

Đây là lợi thế của Java generic composition: một số lỗi thứ tự được bắt ngay khi compile. Declarative SCF composition còn có conversion layer, nên vẫn cần test runtime để xác nhận.

## 22. Test composition qua FunctionCatalog

Một integration test có thể dùng chính Spring configuration:

~~~java
@SpringBootTest(classes = OrderApplication.class)
class CatalogCompositionTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void expectedCompositionWorks() {
        assertThat(catalog.getNames(null))
            .contains(
                "normalizeOrder",
                "calculatePrice",
                "renderReceipt"
            );

        Function<?, ?> pipeline =
            catalog.lookup(
                "normalizeOrder|calculatePrice|renderReceipt"
            );

        assertThat(pipeline).isNotNull();

        Object result = ((Function) pipeline).apply(sampleOrder());

        assertThat(result).isInstanceOf(OrderReceipt.class);
        assertThat(((OrderReceipt) result).orderId())
            .isEqualTo("ORD-101");
    }
}
~~~

Ví dụ giả định các bean ở mục 3 được đăng ký trong `OrderApplication` và test có Spring Boot Test, Spring Cloud Function, JUnit 5, AssertJ. Có thể cần suppress unchecked/raw warnings khi gọi API lookup tùy version.

### 22.1. Test thiếu một function

~~~java
assertThat(catalog.getNames(null))
    .doesNotContain("calculatePrice");
~~~

Sau đó xác nhận composition không thể được sử dụng nếu một mắt xích thực sự vắng mặt. Không dựa riêng vào `lookup != null` nếu single-function fallback có thể làm tên sai trả về function duy nhất.

### 22.2. Test định nghĩa runtime

~~~java
assertThat(environment.getProperty(
    "spring.cloud.function.definition"
)).isEqualTo(
    "normalizeOrder|calculatePrice|renderReceipt"
);
~~~

Test cấu hình giúp phát hiện typo, sai delimiter hoặc profile ghi đè.

## 23. Test reactive composition bằng StepVerifier

Với hai function reactive:

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<RawOrder>, Flux<NormalizedOrder>> normalizeStream =
    orders -> orders.map(order ->
        new NormalizedOrder(
            order.orderId().trim().toUpperCase(Locale.ROOT),
            order.items()
        )
    );

Function<Flux<NormalizedOrder>, Flux<PriceQuote>> calculateStream =
    orders -> orders.map(order ->
        new PriceQuote(
            order.orderId(),
            order.items().stream()
                .map(item -> item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
        )
    );
~~~

Kiểm thử:

~~~java
@Test
void reactiveCompositionProducesQuotes() {
    Function<Flux<RawOrder>, Flux<PriceQuote>> pipeline =
        normalizeStream.andThen(calculateStream);

    StepVerifier.create(pipeline.apply(
            Flux.just(sampleOrder())
        ))
        .expectNextMatches(quote ->
            quote.orderId().equals("ORD-101")
        )
        .verifyComplete();
}
~~~

Test phải subscribe publisher. Nếu không, pipeline cold có thể chưa thực thi.

### 23.1. Kiểm tra error path

~~~java
StepVerifier.create(
        pipeline.apply(Flux.just(invalidOrder()))
    )
    .expectError()
    .verify();
~~~

Trong test thực tế, nên assert exception cụ thể hoặc business error contract. Không chỉ assert mọi exception đều được chấp nhận, vì điều đó có thể che lỗi conversion/logic ngoài dự kiến.

## 24. Test adapter: catalog test chưa đủ

| Test | Điều nó chứng minh |
| --- | --- |
| Unit test từng function | Logic từng bước |
| Java `andThen` test | Generic compatibility và thứ tự |
| FunctionCatalog composition test | SCF lookup/wrapper tạo pipeline |
| HTTP integration test | Route, request conversion và composition |
| Stream test binder/broker test | Binding, content type, event flow |
| Serverless handler test | Event envelope, function selection và output |
| Production smoke test | Profile, runtime property, deployment wiring |

Một function có thể chạy qua `FunctionCatalog` nhưng HTTP route chưa được export; composition có thể đúng trong unit test nhưng Stream binding/destination sai. Kiểm tra đúng adapter triển khai.

## 25. Spring Cloud Stream: test nhiều function độc lập khác composition

Nếu muốn bind hai function riêng:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Spring Cloud Stream tạo bindings riêng cho từng function. Test binder có thể gửi message riêng đến input binding của từng function và kiểm tra output tương ứng.

Nếu muốn một pipeline trong cùng JVM:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

thì output của `uppercase` được đưa vào `reverse`. Đây là hai cách wiring khác nhau.

**Đừng test composition bằng cách gửi message tới hai input bindings độc lập**; như vậy chỉ test hai function riêng.

## 26. Những tình huống cần đặc biệt chú ý

### 26.1. Function trả null

Một bước có thể trả `null`. Bước sau có thể ném exception hoặc không xử lý null. Đặt hợp đồng null rõ ràng: reject, default, optional hoặc route lỗi.

~~~java
@Bean
Function<OrderEvent, NormalizedOrder> normalizeOrder() {
    return order -> {
        if (order == null) {
            throw new IllegalArgumentException("Order is required");
        }
        return normalize(order);
    };
}
~~~

Không để null lan qua nhiều bước rồi mới phát sinh lỗi khó truy vết.

### 26.2. Side effect trước khi bước sau lỗi

Nếu `persistOrder` chạy trước `publishEvent` và bước publish thất bại, dữ liệu đã được lưu nhưng pipeline chưa hoàn tất. Thiết kế transaction/outbox/idempotency phù hợp; composition không tự tạo transaction phân tán cho mọi bước.

### 26.3. Retry cả composition có thể lặp side effect

Nếu retry từ đầu sau khi bước thứ ba thất bại, các bước đầu có thể chạy lại. Chỉ dùng retry khi các thao tác idempotent hoặc có cơ chế chống trùng. Đặt retry boundary đúng bước, không coi composition là một transaction nguyên tử mặc định.

### 26.4. Consumer ở cuối không tạo output

Một composition kết thúc bằng Consumer là terminal operation. Caller/adapter không nên chờ một business payload output như khi composition kết thúc bằng Function.

### 26.5. Supplier không nhận request input

Nếu pipeline bắt đầu bằng Supplier, nó tạo dữ liệu độc lập với input caller. Nếu nghiệp vụ cần xử lý payload HTTP/message, điểm đầu nên là Function hoặc Consumer tùy output mong muốn.

## 27. Checklist trước khi sửa composition

1. Ghi lại definition thực tế, bao gồm mọi routing override.
2. Xác minh tên từng function bằng `catalog.getNames(null)`.
3. Kiểm tra chữ ký generic input/output của từng bean.
4. Vẽ chuỗi output → input theo đúng thứ tự.
5. Gọi từng function riêng với dữ liệu đại diện.
6. Kiểm tra conversion/contentType nếu hai kiểu không trùng.
7. Kiểm tra Consumer có nằm ở cuối không.
8. Kiểm tra Supplier có phù hợp với việc không nhận input không.
9. Nếu reactive, kiểm tra kiểu item, subscription và terminal signal.
10. Nếu dùng Stream, phân biệt composition với danh sách function độc lập.
11. Nếu dùng HTTP/serverless, kiểm tra route/handler và event envelope.
12. Test side effect, retry và idempotency.
13. Chạy test catalog composition và integration test adapter.
14. Ghi log target/function thực tế, không log dữ liệu nhạy cảm.

## 28. Các hiểu nhầm phổ biến

| Hiểu nhầm | Sự thật |
| --- | --- |
| “`a|b` gọi a và b song song.” | Đây là composition tuần tự: a trước, b sau. |
| “`a|b` tương đương hai function độc lập.” | Không; Stream dùng `;` cho nhiều function độc lập. |
| “Hai function có tên trong catalog là ghép được.” | Cần hợp đồng output/input phù hợp hoặc converter hỗ trợ. |
| “Generic type khớp thì thứ tự nghiệp vụ chắc chắn đúng.” | Cùng kiểu vẫn có thể cho kết quả khác khi đảo thứ tự. |
| “Spring Cloud Function không bao giờ convert giữa các bước.” | Content-type negotiation có thể chuyển đổi ở composition. |
| “Converter luôn sửa được mismatch.” | Chỉ khi converter hỗ trợ và payload có ý nghĩa tương ứng. |
| “Consumer có thể đứng giữa rồi trả dữ liệu cho Function.” | Consumer trả void, không có output để truyền tiếp. |
| “Supplier nhận input như Function.” | Supplier không có input. |
| “Function → Consumer vẫn trả output của Function.” | Composition kết thúc là Consumer. |
| “Supplier → Consumer trả dữ liệu.” | Kết quả tương đương Runnable. |
| “`Function<Flux<T>,Flux<R>>` chạy từng item khi gọi apply.” | Function nhận publisher; xử lý thường xảy ra khi subscribe. |
| “Catalog lookup thành công nghĩa invocation thành công.” | Converter/business logic vẫn có thể lỗi. |
| “HTTP 404 chứng minh type composition sai.” | Có thể route chưa được export. |
| “Đổi destination broker sửa sai thứ tự function.” | Destination và composition là hai tầng khác nhau. |
| “Retry composition không có side effect trùng.” | Các bước trước có thể chạy lại. |

## 29. Câu hỏi tự đánh giá

1. Composition của hai Function dựa trên nguyên tắc Java nào?
2. Trong `f.andThen(g)`, function nào chạy trước?
3. Với `Function<A,B>` và `Function<C,D>`, điều kiện tương thích đơn giản nhất là gì?
4. Vì sao Spring Cloud Function có thể ghép một số kiểu không khớp trực tiếp qua Java andThen?
5. Tại sao converter không thể bảo đảm mọi mismatch đều hợp lệ về nghiệp vụ?
6. Dấu `|` và dấu `,` có ý nghĩa gì trong composition definition?
7. Dấu `;` được dùng thế nào khi chọn nhiều function độc lập trong Spring Cloud Stream?
8. Vì sao `normalizeOrder|calculatePrice|renderReceipt` có thứ tự đúng?
9. Điều gì xảy ra nếu đổi thành `calculatePrice|normalizeOrder`?
10. Hai function `String → String` có thể ghép đúng kiểu nhưng sai logic ra sao?
11. Composition `Supplier<T>` với `Function<T,R>` có kiểu kết quả gì?
12. Composition `Supplier<T>` với `Consumer<T>` có kiểu kết quả gì?
13. Vì sao không thể ghép Consumer rồi Function theo cách chuẩn?
14. Khi nào nên dùng Function thay cho Consumer để giữ output cho bước sau?
15. Tại sao `FunctionCatalog.lookup` khác lấy bean trực tiếp từ ApplicationContext?
16. Vì sao catalog lookup thành công chưa chứng minh payload conversion đúng?
17. Header `contentType` ảnh hưởng conversion giữa các bước thế nào?
18. Reactive composition cần kiểm tra kiểu phần tử và subscription ra sao?
19. Vì sao một composition có thể lỗi chỉ khi subscribe?
20. Routing callback và message header có thể làm target thực tế khác definition trong file cấu hình thế nào?
21. Vì sao reactive function không route riêng từng message qua header như imperative function?
22. Làm thế nào phân biệt composition với nhiều binding độc lập trong Stream?
23. Khi composition có side effect, retry từ đầu có thể gây vấn đề gì?
24. Bạn sẽ viết những test nào để xác nhận đúng thứ tự và đúng type trên adapter thực tế?

## 30. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `FunctionCatalog`, declarative composition, `Supplier`/`Function`/`Consumer`, routing, conversion và reactive function.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — chọn một hoặc nhiều function, binding names và message handlers độc lập.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — export function/composition và danh sách function qua HTTP.
- [Java Function.andThen API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Function.html#andThen(java.util.function.Function)) — semantics của composition tuần tự và hợp đồng kiểu.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` để kiểm tra reactive composition và lỗi khi subscribe.
- [Spring Cloud Function — Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-routing) — routing callback, message headers, application properties và thứ tự ưu tiên.

Tài liệu tham khảo theo Spring Cloud Function 5.1.0 và Spring Cloud Stream reference hiện hành tại thời điểm biên soạn. Cấu hình binding, web export và API cụ thể có thể khác giữa BOM/phiên bản; hãy kiểm tra dependency thực tế và chạy integration test với đúng adapter triển khai.

**Ghi nhớ:** Ghép hàm là một pipeline tuần tự: **output của bước trước phải phù hợp input của bước sau, và thứ tự phải đúng nghiệp vụ**. Dùng `|` (hoặc dấu phẩy theo cú pháp SCF) cho composition; trong Spring Cloud Stream, `;` chọn nhiều function độc lập. Java `andThen` bắt lỗi generic mismatch lúc compile, còn composition qua `FunctionCatalog` có thể dùng converter nếu content type và target type hỗ trợ. Hãy kiểm tra riêng `Supplier`, `Function`, `Consumer`, nested reactive types và routing; cuối cùng test cả từng bước lẫn toàn composition trên adapter thật để phát hiện lỗi type, thứ tự và side effect.
