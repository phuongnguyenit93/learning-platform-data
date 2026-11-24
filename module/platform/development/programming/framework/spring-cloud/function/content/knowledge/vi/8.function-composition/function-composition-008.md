# Những thứ tự ghép không hợp lệ

## 1. Vì sao cần biết thứ tự ghép không hợp lệ?

Spring Cloud Function cho phép đóng gói logic nghiệp vụ thành các bean `Supplier`, `Function` và `Consumer`, rồi lựa chọn hoặc ghép chúng thông qua `FunctionCatalog`. Nhờ đó, logic có thể tái sử dụng độc lập với HTTP, hệ thống sự kiện hoặc môi trường serverless khi có adapter thích hợp.

Tuy nhiên, **không phải mọi cách sắp xếp ba loại hàm đều tạo thành một pipeline có nghĩa**. Một chuỗi tên như `"parseOrder|saveOrder|formatOrder"` trông giống pipeline hợp lệ nhưng có thể sai vì `saveOrder` là Consumer: nó thực hiện hành động mà **không tạo đầu ra** cho `formatOrder`. Tương tự, đặt Supplier sau Function không có nghĩa Supplier sẽ nhận dữ liệu từ Function.

Bài học thuộc chương **Ghép hàm**, tập trung vào nhận diện những thứ tự không hợp lệ, giải thích nguyên nhân và sửa bằng hợp đồng kiểu phù hợp.

Sau bài này, bạn có thể:

- Đọc hợp đồng đầu vào/đầu ra của `Supplier<T>`, `Function<T, R>` và `Consumer<T>`.
- Phát hiện chuỗi ghép đặt nguồn ở giữa/cuối hoặc đặt Consumer trước một bước vẫn cần dữ liệu.
- Phân biệt **sai thứ tự**, **không tương thích kiểu**, **sai ngữ nghĩa nghiệp vụ** và **cấu hình adapter không hỗ trợ**.
- Sửa một pipeline bằng cách đổi thứ tự, thêm Function trung gian hoặc gộp các hành động cuối vào một Consumer.
- Kiểm thử composition qua Java thuần, `FunctionCatalog.lookup(...)` và adapter ở mức cần thiết.

> **Phạm vi:** Ví dụ dùng Java 17, Spring Boot và Spring Cloud Function. Khả năng ghép trực tiếp một số tổ hợp (đặc biệt những tổ hợp liên quan `Supplier`/`Consumer`, reactive hoặc `Message`) có thể phụ thuộc phiên bản Spring Cloud Function và adapter. Các quy tắc dưới đây xuất phát từ **hợp đồng dữ liệu**; với biểu thức tên trong catalog, luôn xác minh trên phiên bản đang sử dụng.

## 2. Nhớ lại “cổng vào” và “cổng ra” của từng loại hàm

Ba giao diện Java có vai trò khác nhau:

| Loại | Giao diện | Cổng đầu vào | Cổng đầu ra |
|---|---|---|---|
| Nguồn | `Supplier<T>` | Không có | `T` |
| Biến đổi | `Function<T, R>` | `T` | `R` |
| Điểm nhận | `Consumer<T>` | `T` | Không có (void) |

Các phương thức được gọi tương ứng:

~~~java
Supplier<String> source = () -> "42";
Function<String, Integer> parse = Integer::parseInt;
Consumer<Integer> sink = System.out::println;

String raw = source.get();         // "42"
Integer number = parse.apply(raw); // 42
sink.accept(number);              // in 42
~~~

Một pipeline hợp lý phải nối **cổng ra của bước trước** với **cổng vào của bước sau**. Nếu một bước không có cổng ra, không có dữ liệu để chuyển tiếp. Nếu một bước không có cổng vào, nó không thể sử dụng kết quả mà bước trước gửi đến.

Sơ đồ của các dạng thường gặp:

~~~text
Function<A,B> → Function<B,C>       ⇒ Function<A,C>

Supplier<A>   → Function<A,B>       ⇒ Supplier<B>

Function<A,B> → Consumer<B>         ⇒ Consumer<A>

Supplier<A>   → Consumer<A>         ⇒ Runnable (không input/output)

Supplier<A> → Function<A,B> → Consumer<B>
                                    ⇒ Runnable
~~~

Trong Java thuần, kết quả `Runnable` có thể viết bằng `() -> sink.accept(source.get())`. Với Spring Cloud Function, chuỗi tên `"source|sink"` có thể biểu diễn tổ hợp tương ứng theo cơ chế composition được hỗ trợ. Đừng nhầm đây là một lịch tác vụ tự động: `Runnable.run()` chỉ chạy khi được gọi.

### 2.1. Dấu | có nghĩa nối dữ liệu, không phải liệt kê tùy ý

Khi viết:

~~~java
catalog.lookup("first|second|third");
~~~

thứ tự mong muốn là:

~~~text
input → first → second → third → output/hành động cuối
~~~

Từng tên phải được catalog đăng ký và có hợp đồng tương thích với tên tiếp theo. Thứ tự này không thể hoán đổi theo ý thích, ngay cả khi mọi bean đều tồn tại trong Spring context.

## 3. Phân loại các lý do khiến phép ghép sai

Trước khi sửa một chuỗi, cần xác định nó sai theo kiểu nào:

1. **Thiếu cổng đầu vào:** đặt Supplier sau một bước khác dù Supplier không nhận dữ liệu của bước trước.
2. **Thiếu cổng đầu ra:** đặt Consumer trước một Function/Consumer khác và mong chuyển kết quả `void` cho bước sau.
3. **Kiểu không nối được:** bước trước trả `Order` nhưng bước tiếp theo chỉ nhận `EmailAddress`.
4. **Kiểu nối được, ý nghĩa lại sai:** cả hai dùng `String` nhưng một bên tạo mã khách hàng, bên kia tưởng đó là email.
5. **Nhầm giao diện tổng thể:** pipeline bắt đầu bằng Supplier và kết thúc bằng Consumer mang hành vi `Runnable`, không phải `Function` nhận input.
6. **Nhầm khả năng của adapter:** ghép được bằng Java/catalog không chứng minh binder HTTP hoặc sự kiện sẽ tự kích hoạt và kết nối pipeline.

Một cách kiểm tra nhanh là viết từng bước dưới dạng `Input → Output` trước khi quyết định chuỗi tên.

## 4. Không đặt Supplier sau Function

Xét:

~~~text
normalize: Function<String, String>
generate:  Supplier<String>

"normalize|generate"  ← không phải luồng truyền dữ liệu hợp lệ
~~~

Sau `normalize`, ứng dụng có một `String`. Nhưng `generate.get()` **không nhận tham số**, nên nó không có chỗ để dùng `String` đó.

Trong Java:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, String> normalize = String::trim;
Supplier<String> generate = () -> "NEW";

// Không biên dịch: andThen cần một Function, không phải Supplier.
// Function<String, String> bad = normalize.andThen(generate);
~~~

### 4.1. Sửa thế nào?

**Tình huống A:** Nhu cầu là “tạo dữ liệu rồi chuẩn hóa”. Hãy đảo thành nguồn trước, biến đổi sau:

~~~java
Supplier<String> generate = () -> "  NEW  ";
Function<String, String> normalize = String::trim;

Supplier<String> normalized =
        () -> normalize.apply(generate.get());

System.out.println(normalized.get()); // NEW
~~~

Với bean được đăng ký trong Spring Cloud Function, biểu thức theo tên là:

~~~text
generate|normalize
~~~

**Tình huống B:** Nhu cầu là “nhận dữ liệu từ người gọi rồi tạo một mã mới có liên hệ với nó”. Khi đó bước thứ hai **không nên là Supplier độc lập**. Hãy viết một `Function<Input, Output>` thật sự sử dụng input:

~~~java
Function<String, String> generateId =
        normalized -> "ID-" + normalized;

Function<String, String> pipeline =
        normalize.andThen(generateId);
~~~

Trong Spring Cloud Function, sau khi đăng ký cả hai Function, biểu thức là `"normalize|generateId"`.

## 5. Không đặt Consumer trước Function

Xét:

~~~text
saveOrder:   Consumer<Order>
formatOrder: Function<Order, String>

"saveOrder|formatOrder"  ← sai theo mô hình truyền đầu ra
~~~

`Consumer.accept(order)` có kiểu trả về `void`. Vì vậy, không có `Order` mới được trả để `formatOrder` sử dụng.

Đoạn Java tương ứng không thể tạo một `Function` nối sau Consumer theo cách `andThen` của Function:

~~~java
Consumer<String> save = System.out::println;
Function<String, Integer> length = String::length;

// Không tồn tại phép ghép kiểu Function dựa trên output của save:
// var invalid = save.andThen(length);
~~~

`Consumer.andThen` trong Java chỉ nhận **một Consumer tiếp theo**, không nhận `Function`.

### 5.1. Đổi thứ tự để Consumer đứng cuối

Nếu mục tiêu là “định dạng rồi lưu”, thứ tự là:

~~~text
formatOrder: Function<Order, String>
saveText:    Consumer<String>

"formatOrder|saveText" ⇒ Consumer<Order>
~~~

Java thuần:

~~~java
Function<String, String> normalize = String::trim;
Consumer<String> save = System.out::println;

Consumer<String> pipeline =
        raw -> save.accept(normalize.apply(raw));

pipeline.accept("  ORD-42  "); // ORD-42
~~~

Ở đây, bước cuối **không trả giá trị nghiệp vụ**. Toàn pipeline cũng là Consumer, được gọi bằng `accept`.

### 5.2. Khi vừa cần lưu vừa trả kết quả

Không nên đặt một Consumer ở giữa rồi cố “nối tiếp” nó. Có hai phương án thiết kế:

- Dùng một `Function<Order, Receipt>` thực hiện nghiệp vụ và trả `Receipt` có nghĩa, với trách nhiệm side effect được mô tả tường minh.
- Tách một workflow orchestration: tạo kết quả, gọi Consumer lưu trữ, sau đó trả kết quả do workflow đang giữ; không xem đó là việc Consumer phát ra output.

Cách Java minh họa cho phương án thứ hai:

~~~java
Function<String, String> normalize = String::trim;
Consumer<String> audit = System.out::println;

Function<String, String> normalizeAndAudit = raw -> {
    String value = normalize.apply(raw);
    audit.accept(value);
    return value;
};
~~~

`normalizeAndAudit` trả một giá trị **do code chủ động trả lại**, không phải giá trị từ `audit.accept`. Nếu có side effect, cần xác định rõ hành vi lỗi và retry.

## 6. Không đặt Consumer trước Supplier

Một chuỗi như:

~~~text
writeAudit: Consumer<AuditRecord>
nextEvent:  Supplier<Event>

"writeAudit|nextEvent"
~~~

không có ý nghĩa “ghi audit rồi chuyển kết quả sang Supplier”. Consumer không trả output, Supplier lại không nhận input. Hai bước này không nối dữ liệu với nhau.

Nếu mục tiêu là chạy hai hành động tuần tự mà không truyền giá trị, hãy viết một workflow tường minh:

~~~java
Consumer<String> audit = System.out::println;
Supplier<String> nextEvent = () -> "EVT-9";

Runnable workflow = () -> {
    audit.accept("starting");
    String event = nextEvent.get();
    System.out.println("next: " + event);
};
~~~

Đây là **orchestration**, không phải Function composition tuần tự dựa trên kiểu đầu ra/đầu vào. Việc viết code chủ động như vậy giúp người đọc hiểu chính xác hành động nào diễn ra và vì sao.

## 7. Hai Supplier không tự ghép thành một pipeline tuyến tính

Xét:

~~~text
orders:   Supplier<Order>
payments: Supplier<Payment>

"orders|payments"
~~~

`payments` không có cổng nhận `Order` từ `orders`. Vì vậy, cách viết này không biểu diễn pipeline “lấy order rồi xử lý bằng payment”.

### 7.1. Nếu muốn kết hợp kết quả từ hai nguồn

Hãy tự mô hình hóa nguồn tổng hợp:

~~~java
import java.util.function.Supplier;

record Pair<A, B>(A left, B right) {}

Supplier<String> orderId = () -> "ORD-42";
Supplier<Long> amount = () -> 125_000L;

Supplier<Pair<String, Long>> combined = () ->
        new Pair<>(orderId.get(), amount.get());

System.out.println(combined.get());
// Pair[left=ORD-42, right=125000]
~~~

Hai Supplier được **gọi riêng** và kết quả được gộp rõ ràng vào `Pair`. Đây là cách triển khai Java tùy chỉnh, không phải `orders|payments` theo mô hình nối cổng.

### 7.2. Nếu muốn dùng đầu ra của nguồn thứ nhất để truy vấn nguồn thứ hai

Nguồn thứ hai lúc này phải là Function:

~~~java
Supplier<String> orderId = () -> "ORD-42";

Function<String, Long> findAmount =
        id -> id.equals("ORD-42") ? 125_000L : 0L;

Supplier<Long> amount =
        () -> findAmount.apply(orderId.get());
~~~

Với Spring Cloud Function, nếu hai bean có tên `orderId` và `findAmount`, biểu thức `"orderId|findAmount"` mới mô tả luồng truyền dữ liệu.

## 8. Hai Consumer không tự nối theo kiểu truyền output

Giả sử có:

~~~text
save:  Consumer<Order>
audit: Consumer<Order>

"save|audit"  ← không có dữ liệu đầu ra từ save cho audit
~~~

Vì `save.accept` trả `void`, không thể xem `audit` như một bước tiêu thụ kết quả của `save`. Tuy nhiên, **Java hỗ trợ `Consumer.andThen`** để lần lượt gọi hai Consumer **với cùng input**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> events = new ArrayList<>();

Consumer<String> save =
        id -> events.add("SAVE:" + id);

Consumer<String> audit =
        id -> events.add("AUDIT:" + id);

Consumer<String> saveAndAudit = save.andThen(audit);
saveAndAudit.accept("ORD-42");

System.out.println(events);
// [SAVE:ORD-42, AUDIT:ORD-42]
~~~

Kết quả vẫn là `Consumer<String>`. Cả hai đều nhận `"ORD-42"`, chứ không có giá trị nào được truyền từ kết quả của `save` sang `audit`.

**Trong Spring Cloud Function:** không nên mặc định `FunctionCatalog.lookup("save|audit")` có cùng ý nghĩa hay được hỗ trợ như `save.andThen(audit)` trên mọi phiên bản. Khi cần hai tác dụng phụ theo thứ tự, cách rõ ràng là đăng ký **một Consumer bean tổng hợp** sử dụng `andThen` của Java hoặc viết orchestration riêng.

Ví dụ:

~~~java
@Bean
public Consumer<Order> saveAndAudit(
        @Qualifier("save") Consumer<Order> save,
        @Qualifier("audit") Consumer<Order> audit) {

    return save.andThen(audit);
}
~~~

Đoạn này là một method trong lớp `@Configuration` có kiểu `Order` và các bean `save`, `audit` đã được khai báo; `@Qualifier` thuộc `org.springframework.beans.factory.annotation.Qualifier`. Khi đó có thể chọn tên `saveAndAudit` làm bước Consumer cuối.

## 9. Consumer ở giữa pipeline là dấu hiệu cần xem lại

Đây là lỗi hay gặp khi tạo chuỗi có nhiều bước:

~~~text
parseOrder|saveOrder|notifyCustomer
~~~

Giả sử:

~~~text
parseOrder:      Function<String, Order>
saveOrder:       Consumer<Order>
notifyCustomer:  Function<Order, String>
~~~

Sau `parseOrder` là `Order`; `saveOrder` nhận được nó, nhưng không trả `Order` tiếp. Vì vậy `notifyCustomer` **không có input từ bước trước**.

Cũng cần tránh:

~~~text
supplier|consumer|function
function|consumer|supplier
supplier|consumer|consumer
~~~

Với mô hình pipeline tuyến tính, sau Consumer không còn output cho bước sau. Nếu `Supplier|Consumer` tạo thành `Runnable` thì Runnable cũng không có cổng ra để nối tiếp.

### 9.1. Cách sửa bằng một Consumer điểm cuối

Nếu nghiệp vụ cần vừa lưu vừa audit, hãy gộp hai hành động trong **một** Consumer cuối:

~~~text
parseOrder:     Function<String, Order>
saveAndAudit:   Consumer<Order>

"parseOrder|saveAndAudit"
               ⇒ Consumer<String>
~~~

Nếu cần thêm bước xác thực có output là `Order`, đặt nó **trước** Consumer:

~~~text
parseOrder|validateOrder|saveAndAudit
~~~

với chữ ký:

~~~text
parseOrder:     String → Order
validateOrder:  Order → Order
saveAndAudit:   Order → void
~~~

Không nên tự ý đổi một `Consumer` thành `Function<Order,Order>` chỉ để có “output”, trừ khi hàm đó thực sự có hợp đồng nghiệp vụ rõ ràng về việc trả lại Order và hành vi khi side effect thất bại.

## 10. Đúng thứ tự loại hàm nhưng sai kiểu trung gian

Thứ tự `Function → Function → Consumer` có thể hợp lý **về hình dạng**, nhưng vẫn sai nếu kiểu đầu ra và đầu vào không khớp.

Giả sử:

~~~text
parseOrder:       Function<String, Order>
validateOrder:    Function<Order, Boolean>
saveOrder:        Consumer<Order>
~~~

Chuỗi:

~~~text
parseOrder|validateOrder|saveOrder
~~~

không có hợp đồng nối tự nhiên, bởi `validateOrder` trả `Boolean` nhưng `saveOrder` nhận `Order`. Kết quả Boolean không còn chứa dữ liệu Order để lưu.

### 10.1. Sửa kiểu kết quả của validation

Nếu validation chỉ có mục tiêu chặn dữ liệu sai, có thể định nghĩa nó thành `Function<Order, Order>`:

~~~java
record Order(String sku, int quantity) {}

Function<Order, Order> validateOrder = order -> {
    if (!order.sku().matches("SKU-[0-9]+")
            || order.quantity() <= 0) {
        throw new IllegalArgumentException("Don hang khong hop le");
    }
    return order;
};
~~~

Khi đó hợp đồng:

~~~text
String → Order → Order → void
~~~

phù hợp cho `parseOrder|validateOrder|saveOrder`, với giả thiết các bean được đăng ký đúng tên trong catalog.

Một lựa chọn khác là dùng kiểu `ValidationResult<Order>`, sau đó có Function xử lý kết quả validation và trích ra Order đã hợp lệ trước khi lưu. Không ép `Boolean` thành `Order` hoặc bỏ qua trạng thái không hợp lệ.

### 10.2. Khớp kiểu nhưng sai ý nghĩa

~~~text
extractCustomerId: Function<Order, String>
sendEmail:         Consumer<String>
~~~

Cả hai đều dùng `String` nhưng `sendEmail` có thể hiểu đó là email trong khi dữ liệu là mã khách hàng. Pipeline không hỏng vì generic, song vẫn **sai nghiệp vụ**.

Hãy định nghĩa các kiểu tường minh nếu thích hợp:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

Với `Function<Order, CustomerId>` và `Consumer<EmailAddress>`, trình biên dịch Java có thể giúp phát hiện việc truyền nhầm khi ghép bằng code.

## 11. Ví dụ Spring Cloud Function: sai rồi sửa

Xây dựng một ứng dụng nhận đơn hàng ở dạng `"SKU-42,2"`, sau đó kiểm tra và lưu/audit. Một trường hợp sai thường gặp là cố nối hai Consumer liên tiếp bằng dấu `|` như thể Consumer đầu trả dữ liệu cho Consumer sau.

### 11.1. Định nghĩa bean và mô hình dữ liệu

Dùng Java 17 và Spring Boot:

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record Order(String sku, int quantity) {}

    public static final class Ledger {
        private final Queue<Order> saved =
                new ConcurrentLinkedQueue<>();
        private final Queue<Order> audited =
                new ConcurrentLinkedQueue<>();

        public void save(Order order) {
            saved.add(order);
        }

        public void audit(Order order) {
            audited.add(order);
        }

        public List<Order> savedOrders() {
            return List.copyOf(saved);
        }

        public List<Order> auditedOrders() {
            return List.copyOf(audited);
        }
    }

    @Bean
    public Ledger ledger() {
        return new Ledger();
    }

    @Bean
    public Function<String, Order> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Can dinh dang SKU,quantity");
            }

            String sku = parts[0].trim();
            int quantity = Integer.parseInt(parts[1].trim());
            return new Order(sku, quantity);
        };
    }

    @Bean
    public Function<Order, Order> validateOrder() {
        return order -> {
            if (!order.sku().matches("SKU-[0-9]+")
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Don hang khong hop le");
            }
            return order;
        };
    }

    @Bean
    public Consumer<Order> saveOrder(Ledger ledger) {
        return ledger::save;
    }

    @Bean
    public Consumer<Order> auditOrder(Ledger ledger) {
        return ledger::audit;
    }

    @Bean
    public Consumer<Order> saveAndAudit(
            @Qualifier("saveOrder") Consumer<Order> save,
            @Qualifier("auditOrder") Consumer<Order> audit) {

        return save.andThen(audit);
    }
}
~~~

Các bean function được đăng ký theo tên method: `parseOrder`, `validateOrder`, `saveOrder`, `auditOrder`, `saveAndAudit`. Bean `Ledger` chỉ là nơi lưu kết quả minh họa, không phải Function/Supplier/Consumer.

### 11.2. Chuỗi dễ nhầm: hai Consumer nối liên tiếp

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|saveOrder|auditOrder"
~~~

Về cổng dữ liệu, chuỗi này không có output từ `saveOrder` cho `auditOrder`. Không nên coi đó là phép nối hai tác dụng phụ hợp lệ chỉ vì Java có `Consumer.andThen`.

### 11.3. Chuỗi được sửa: Function → Function → Consumer

Đổi thành:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|saveAndAudit"
~~~

Bảng hợp đồng:

| Bước | Kiểu nhận | Kiểu trả |
|---|---|---|
| `parseOrder` | `String` | `Order` |
| `validateOrder` | `Order` | `Order` |
| `saveAndAudit` | `Order` | `void` |
| Pipeline tổng thể | `String` | `void` — `Consumer<String>` |

Tra cứu và thực thi từ Java:

~~~java
import java.util.function.Consumer;
import org.springframework.cloud.function.context.FunctionCatalog;

Consumer<String> pipeline =
        catalog.lookup("parseOrder|validateOrder|saveAndAudit");

if (pipeline == null) {
    throw new IllegalStateException("Khong tim thay order pipeline");
}

pipeline.accept("SKU-42,2");
~~~

Khi thành công, ledger nhận một đơn hàng đã được validate ở cả hai danh sách saved và audited. Đây là hành vi **của một Consumer bean tổng hợp có chủ đích**, chứ không suy đoán hai Consumer nối qua output.

### 11.4. Lưu ý về tác dụng phụ

`saveAndAudit` gọi `save` rồi `audit`. Nếu `save` thành công mà `audit` thất bại, dữ liệu đã lưu không tự rollback. Trong production, phải có quy tắc giao dịch/idempotency hoặc cơ chế xử lý lỗi phù hợp. Composition và `Consumer.andThen` không tự cung cấp transaction phân tán.

## 12. Những biểu thức sai liên quan Supplier và Runnable

Một `Supplier` được đặt đầu chuỗi có thể ghép với các Function để sinh dữ liệu mới:

~~~text
generateOrder|validateOrder
Supplier<Order> + Function<Order,Order>
                       ⇒ Supplier<Order>
~~~

Một `Supplier` ghép cuối cùng với Consumer có thể tạo hành vi `Runnable`:

~~~text
generateOrder|saveOrder
Supplier<Order> + Consumer<Order>
                       ⇒ Runnable
~~~

Nhưng không nên viết:

~~~text
generateOrder|saveOrder|auditOrder
~~~

rồi kỳ vọng `auditOrder` nhận output của `saveOrder`. Hợp đồng sau `saveOrder` đã là **không input/không output**.

Nếu muốn vừa lưu vừa audit, có thể dùng `"generateOrder|saveAndAudit"`, trong đó `saveAndAudit` là một Consumer tổng hợp như ở ví dụ trước.

Cũng không thể nối một `Function` trực tiếp **sau `Runnable`** bằng cơ chế output → input; `Runnable.run()` trả `void` và không cung cấp dữ liệu để biến đổi tiếp.

## 13. Message, chuyển đổi payload và reactive không tự sửa thứ tự sai

### 13.1. Message<T> khác T

Trong một hệ thống sự kiện, có thể có các bước:

~~~text
Function<Message<String>, Message<Order>>
Consumer<Message<Order>>
~~~

`Message<T>` chứa payload và headers. Nếu Consumer yêu cầu `Message<Order>` mà Function chỉ trả `Order`, hai chữ ký Java không giống nhau. Spring Cloud Function hoặc adapter có thể cung cấp conversion/wrapper trong một số trường hợp, nhưng **không nên dùng khả năng chuyển đổi đó để biện minh cho thứ tự sai**.

Ví dụ, đặt Consumer ở trước Function vẫn không tạo output chỉ vì payload ở dạng Message. Cần kiểm thử serialization, content-type, headers và conversion ở ranh giới adapter trên phiên bản thực tế.

### 13.2. Kiểu reactive phải xét toàn bộ Publisher

Các chữ ký:

~~~text
Function<Flux<String>, Flux<Order>>
Consumer<Flux<Order>>
~~~

có thể nối trong Java theo generic, vì kết quả của Function là đúng kiểu Consumer nhận. Nhưng:

~~~text
Function<String, Order>
Consumer<Flux<Order>>
~~~

không phải cặp có kiểu nối trực tiếp: `Order` khác `Flux<Order>`. Một số adapter/framework có cơ chế adaptation imperative/reactive theo ngữ cảnh, nên cần kiểm thử, không chỉ đọc kiểu phần tử `Order` rồi kết luận chắc chắn.

Quan trọng hơn, reactive Publisher có thể được xử lý **lười**: thời điểm gọi Function để tạo Flux khác với thời điểm subscriber thực sự nhận phần tử. Dấu `|` chỉ mô tả thứ tự composition, không bảo đảm các phần tử chạy trên một thread hoặc rằng mọi tác dụng phụ đã hoàn tất khi tạo Publisher.

### 13.3. Không nhầm định nghĩa với adapter

`spring.cloud.function.definition` chọn tên chuỗi cho Spring Cloud Function/adapter. Nó **không tự mở HTTP endpoint, tạo input/output binding hoặc kích hoạt Runnable**. Một pipeline có thứ tự và kiểu hợp lệ vẫn có thể không hoạt động vì thiếu starter hoặc cấu hình HTTP, sự kiện, serverless.

Ngược lại, một adapter có khả năng chuyển payload không nên được xem như công cụ tự sửa những chuỗi có Consumer ở giữa hoặc Supplier ở cuối.

## 14. Kiểm thử để phát hiện thứ tự không hợp lệ

### 14.1. Unit test Java: Function chạy trước Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerOrderTest {

    @Test
    void transformsBeforeConsuming() {
        List<String> trace = new ArrayList<>();

        Function<String, Integer> parse = raw -> {
            trace.add("parse");
            return Integer.parseInt(raw);
        };

        Consumer<Integer> save = number ->
                trace.add("save:" + number);

        Consumer<String> pipeline =
                raw -> save.accept(parse.apply(raw));

        pipeline.accept("42");

        assertEquals(List.of("parse", "save:42"), trace);
    }
}
~~~

Kiểm thử trên xác nhận dòng dữ liệu của phép ghép hợp lệ `Function → Consumer` và ngăn hiểu nhầm rằng Consumer tạo kết quả cho bước sau.

### 14.2. Unit test: Function lỗi thì Consumer chưa chạy

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class CompositionFailureTest {

    @Test
    void failedParseStopsConsumer() {
        AtomicInteger saved = new AtomicInteger();

        Function<String, Integer> parse = Integer::parseInt;
        Consumer<Integer> sink =
                value -> saved.incrementAndGet();

        Consumer<String> pipeline =
                raw -> sink.accept(parse.apply(raw));

        assertThrows(NumberFormatException.class,
                () -> pipeline.accept("invalid"));

        assertEquals(0, saved.get());
    }
}
~~~

### 14.3. Integration test với FunctionCatalog

Một ứng dụng Spring Boot có lớp chính sau nằm trong package `example.functions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Có thể kiểm tra pipeline được sửa từ mục 11:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = OrderApplication.class)
class CompositionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderFunctions.Ledger ledger;

    @Test
    void correctOrderResolvesAndRuns() {
        Consumer<String> pipeline =
                catalog.lookup(
                    "parseOrder|validateOrder|saveAndAudit");

        assertNotNull(pipeline);
        pipeline.accept("SKU-42,2");

        List<OrderFunctions.Order> expected =
                List.of(new OrderFunctions.Order("SKU-42", 2));

        assertEquals(expected, ledger.savedOrders());
        assertEquals(expected, ledger.auditedOrders());
    }
}
~~~

Test cần dependency Spring Cloud Function và Spring Boot Test phù hợp. Nếu context hoặc ledger được dùng chung giữa các test, hãy cách ly hoặc reset dữ liệu giữa các lần kiểm thử.

### 14.4. Có nên assert chuỗi sai luôn trả null?

**Không nên.** Tùy phiên bản Spring Cloud Function, một biểu thức không hợp lệ có thể bị từ chối ngay khi `lookup`, ném ngoại lệ, trả `null` hoặc chỉ bộc lộ lỗi khi thực thi. Nếu viết test âm, hãy kiểm tra hành vi **của đúng phiên bản đang chạy**; không hard-code rằng tất cả chuỗi sai đều nhất định trả `null`.

Điều cần chứng minh trong test âm là một biểu thức sai không được chấp nhận như pipeline nghiệp vụ hợp lệ, và không được tạo side effect ngoài dự kiến. Nếu thử một chuỗi có thể gọi Consumer, hãy dùng store/spy được cô lập để phát hiện thao tác sai.

## 15. Checklist chẩn đoán chuỗi ghép sai

Khi gặp lỗi trong `catalog.lookup("A|B|C")` hoặc cấu hình `spring.cloud.function.definition`, kiểm tra theo trình tự:

| Câu hỏi | Cần xác nhận |
|---|---|
| Tên bean đúng chưa? | `@Bean`, tên explicit, component scan, catalog |
| Có Supplier nằm sau một bước khác không? | Supplier không có cổng input |
| Có Consumer nằm trước bước khác không? | Consumer không tạo output |
| Kiểu trung gian nối được không? | `Output(A)` có thể dùng cho `Input(B)`? |
| Ý nghĩa dữ liệu có đúng không? | Order khác Receipt, ID khác email |
| Hợp đồng tổng thể là gì? | `Function`, `Supplier`, `Consumer` hay `Runnable` |
| Có phụ thuộc conversion không? | Message/payload/reactive phải kiểm thử trên runtime |
| Có adapter thật chưa? | HTTP endpoint, binder, serverless handler và cấu hình |
| Nếu có side effect, có xử lý retry/trùng chưa? | Idempotency, transaction, logging, lỗi |

Không nên sửa nhanh bằng cách thay toàn bộ generic thành `Object` hoặc ép `String`. Các cách này thường che giấu lỗi và khiến chúng phát sinh muộn khi chạy thật.

## 16. Bài tập tự luyện

**Bài 1 — Sắp xếp lại thứ tự.** Cho `fetch: Supplier<String>` và `normalize: Function<String,String>`. Chuỗi `normalize|fetch` có điểm nào sai? Viết thứ tự hợp lệ và xác định kiểu tổng thể.

**Bài 2 — Consumer ở giữa.** Cho `parse: Function<String,Order>`, `save: Consumer<Order>` và `format: Function<Order,String>`. Vì sao `parse|save|format` không phải pipeline tuyến tính hợp lệ? Hãy đưa ra hai cách đáp ứng yêu cầu vừa lưu vừa định dạng.

**Bài 3 — Validation làm mất dữ liệu.** Có `parse: String → Order`, `check: Order → Boolean`, `save: Consumer<Order>`. Vì sao `parse|check|save` sai kiểu? Viết chữ ký cho bước validation mới giữ lại Order hợp lệ.

**Bài 4 — Hai Consumer.** Có `audit: Consumer<Order>` và `notify: Consumer<Order>`. Hãy dùng `Consumer.andThen` trong Java tạo một Consumer tổng hợp, rồi giải thích nó khác gì với ý tưởng truyền output từ `audit` sang `notify`.

**Bài 5 — Hai Supplier.** Có `orderId: Supplier<String>` và `lookupAmount: Supplier<Long>`. Vì sao `orderId|lookupAmount` không truyền ID cho bước sau? Nếu `lookupAmount` cần dùng ID, hãy thay nó bằng một giao diện Java thích hợp.

**Bài 6 — Runnable.** Hợp đồng tổng thể của `Supplier<Order>|Consumer<Order>` là gì? Nêu phương thức gọi đúng và giải thích vì sao không được nối thêm Function sau Consumer.

**Bài 7 — Adapter.** `catalog.lookup("parseOrder|saveAndAudit")` chạy được trong Java nhưng adapter message không có output. Điều đó có nhất thiết là lỗi không? Nêu điều cần kiểm tra ở phía binder và hợp đồng Consumer.

**Bài 8 — Test âm.** Hãy viết một test xác minh rằng input `"SKU-42,0"` bị từ chối bởi `validateOrder` và `saveAndAudit` chưa tạo side effect. Vì sao không nên chỉ kiểm tra `lookup` có trả `null` cho chuỗi sai?

### Gợi ý đáp án

- **Bài 1:** `fetch|normalize` tạo `Supplier<String>`; Supplier không nhận dữ liệu từ bước đứng trước.
- **Bài 2:** Có thể định dạng trước khi gọi Consumer phù hợp, hoặc viết workflow rõ ràng tự giữ Order/kết quả để vừa lưu vừa trả.
- **Bài 3:** `Boolean` không phải `Order`; dùng `Function<Order,Order>` xác thực rồi trả Order hoặc một mô hình kết quả có bước chuyển về Order.
- **Bài 4:** `Consumer<Order> both = audit.andThen(notify);`; cả hai nhận cùng Order.
- **Bài 5:** Đổi thành `Function<String,Long> lookupAmount` để nhận order ID làm input.
- **Bài 6:** `Runnable`, gọi `run()`; Consumer trả void nên không có giá trị cho Function sau.
- **Bài 7:** Không nhất thiết; Consumer không tạo output nghiệp vụ. Kiểm tra input binding, acknowledgement và khả năng adapter hỗ trợ definition.
- **Bài 8:** Test gọi pipeline hợp lệ với dữ liệu sai, dùng spy/store xác minh chưa lưu; hành vi lỗi của chuỗi tên sai phụ thuộc framework.

## 17. Ghi nhớ

- Một pipeline theo dấu `|` chỉ hợp lý khi **đầu ra của bước trước** có thể đi vào **đầu vào của bước sau**.
- `Supplier` không có input nên thường là **nguồn ở đầu**; `Consumer` không có output nên thường là **điểm cuối**.
- Các chuỗi như `Function|Supplier`, `Consumer|Function`, `Consumer|Supplier`, `Supplier|Supplier` hoặc `Function|Consumer|Function` không mô tả luồng truyền output → input hợp lệ.
- `Consumer.andThen` của Java có thể ghép **hai hành động với cùng input**, nhưng không có nghĩa Consumer trước trả dữ liệu cho Consumer sau qua `|`.
- Thứ tự đúng vẫn có thể sai vì generic hoặc ngữ nghĩa nghiệp vụ; kiểm tra **mọi kiểu trung gian** và vai trò của từng bước.
- `FunctionCatalog.lookup(...)` và `spring.cloud.function.definition` không thay thế kiểm thử runtime hoặc cấu hình adapter HTTP, sự kiện, serverless.
- Đối với Consumer và Runnable có tác dụng phụ, luôn thiết kế rõ retry, lỗi và idempotency thay vì trông chờ composition tự xử lý.
