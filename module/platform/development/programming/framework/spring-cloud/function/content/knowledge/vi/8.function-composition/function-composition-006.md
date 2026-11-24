# Ghép Function với Consumer

## 1. Mục tiêu bài học

Spring Cloud Function cho phép phát triển logic nghiệp vụ dưới dạng `Supplier`, `Function` và `Consumer` có thể tái sử dụng, độc lập với việc logic được gọi từ Java, HTTP, sự kiện hay nền tảng serverless. Trong chương **Ghép hàm**, trường hợp **Function kết thúc bằng Consumer** đặc biệt hữu ích khi dữ liệu cần được chuẩn hóa, xác thực rồi chuyển đến một hành động cuối, như ghi nhận đơn hàng hoặc phát sự kiện.

Ví dụ về luồng xử lý:

~~~text
Dữ liệu đầu vào A
      |
      v
Function<A, B>  --apply(A)--> B
      |
      v
Consumer<B>     --accept(B)--> hành động cuối, không trả giá trị
~~~

Hành vi tổng thể là **`Consumer<A>`**: nhận một giá trị kiểu `A`, biến đổi thành `B`, rồi chuyển `B` cho Consumer. Trong Java thuần, ta có thể biểu diễn bằng `input -> sink.accept(transform.apply(input))`. Spring Cloud Function còn hỗ trợ ghép các function bean được đăng ký trong `FunctionCatalog` theo tên.

Sau bài học, bạn có thể:

- Nhận biết hợp đồng kiểu `Function<A, B>` và `Consumer<B>`, cùng phương thức `apply`/`accept`.
- Dự đoán thứ tự xử lý, thời điểm phát sinh tác dụng phụ và kiểu của pipeline đã ghép.
- Viết phép ghép trong Java thuần, sau đó ghép các bean bằng `FunctionCatalog.lookup("transform|sink")`.
- Chọn pipeline với `spring.cloud.function.definition` và hiểu sự khác biệt giữa cấu hình logic và adapter HTTP/message/serverless.
- Phân biệt `Consumer.andThen` với phép ghép `Function → Consumer`.
- Kiểm thử kết quả biến đổi, việc Consumer được gọi, xử lý lỗi và rủi ro khi có retry.

## 2. Hai giao diện và hợp đồng đầu vào/đầu ra

### 2.1. Function biến đổi dữ liệu và trả kết quả

Giao diện Java `java.util.function.Function<T, R>` có phương thức:

~~~java
R apply(T input);
~~~

Ví dụ:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> normalize =
        value -> value.trim().toUpperCase(Locale.ROOT);

String result = normalize.apply("  ord-42  ");
System.out.println(result); // ORD-42
~~~

Function trên nhận một `String` và trả về `String` mới. Nó chưa thực hiện thao tác ghi dữ liệu hay gửi sự kiện.

### 2.2. Consumer nhận dữ liệu để thực hiện hành động

Giao diện `java.util.function.Consumer<T>` có phương thức:

~~~java
void accept(T value);
~~~

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> received = new ArrayList<>();
Consumer<String> record = received::add;

record.accept("ORD-42");
System.out.println(received); // [ORD-42]
~~~

`Consumer.accept(...)` **không trả một giá trị nghiệp vụ**. Giá trị kiểu `boolean` từ `List.add` không trở thành đầu ra của Consumer; phương thức tham chiếu được sử dụng trong ngữ cảnh `Consumer<String>` với kết quả bị bỏ qua. Với ứng dụng thật, Consumer thường gửi lệnh, ghi database, ghi log hoặc phát thông điệp.

### 2.3. Ghép Function với Consumer tạo hợp đồng gì?

Nếu có:

~~~text
transform: Function<A, B>
sink:      Consumer<B>
~~~

thì phần tử cuối nhận `B` do `transform` tạo ra. Luồng đã ghép không có giá trị trả về:

~~~text
Consumer<A> composite

composite.accept(a):
    b = transform.apply(a)
    sink.accept(b)
~~~

| Thành phần | Đầu vào | Đầu ra | Phương thức |
|---|---|---|---|
| `Function<A, B>` | `A` | `B` | `apply(A)` |
| `Consumer<B>` | `B` | `void` | `accept(B)` |
| Function nối Consumer | `A` | Không có | `accept(A)` |

Đây là trường hợp **terminal composition**: Consumer thường được đặt ở **cuối** luồng vì sau `accept` không còn giá trị `B` để đưa sang một Function tiếp theo.

## 3. Ghép trong Java thuần

Giả sử ứng dụng nhận mã đơn hàng có thể chứa khoảng trắng và chữ thường, rồi ghi lại mã đã chuẩn hóa:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;

public class FunctionConsumerExample {

    public static void main(String[] args) {
        Function<String, String> normalize =
                value -> value.trim().toUpperCase(Locale.ROOT);

        List<String> acceptedOrders = new ArrayList<>();
        Consumer<String> save = acceptedOrders::add;

        Consumer<String> pipeline = raw ->
                save.accept(normalize.apply(raw));

        pipeline.accept("  ord-42  ");

        System.out.println(acceptedOrders); // [ORD-42]
    }
}
~~~

Hãy đọc dòng `pipeline.accept("  ord-42  ")` theo thứ tự:

1. `normalize.apply("  ord-42  ")` tạo `"ORD-42"`.
2. `save.accept("ORD-42")` thêm chuỗi vào danh sách.
3. `pipeline.accept(...)` hoàn tất với kiểu trả về `void`.

Việc **khởi tạo lambda** `pipeline` chưa gọi `normalize` hoặc `save`. Hai bước được gọi khi thực thi `accept(...)`.

### 3.1. Helper generic để tái sử dụng phép ghép

Java không cung cấp sẵn `Function.andThen(Consumer)`. Nếu cần tái sử dụng mô hình này, có thể viết một helper:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

public final class FunctionConsumerComposition {

    private FunctionConsumerComposition() {}

    public static <A, B> Consumer<A> combine(
            Function<? super A, ? extends B> transform,
            Consumer<? super B> sink) {

        return value -> sink.accept(transform.apply(value));
    }
}
~~~

Sử dụng:

~~~java
Function<String, Integer> parseAmount =
        text -> Integer.parseInt(text.trim());

Consumer<Number> showNumber =
        number -> System.out.println("So luong: " + number);

Consumer<String> parseAndShow =
        FunctionConsumerComposition.combine(
                parseAmount, showNumber);

parseAndShow.accept(" 12 "); // So luong: 12
~~~

Ở đây, `parseAmount` trả `Integer`, còn `showNumber` nhận `Number`. Hai kiểu tương thích vì `Integer` là kiểu con của `Number`. Generic `? super B` cho phép Consumer nhận một kiểu cha phù hợp của kết quả.

### 3.2. Vì sao không gọi function.andThen(consumer)?

Đây là **lỗi biên dịch**:

~~~java
Function<String, Integer> parse = Integer::parseInt;
Consumer<Integer> print = System.out::println;

// Không biên dịch: andThen trên Function yêu cầu một Function,
// còn print là Consumer.
// Function<String, ?> invalid = parse.andThen(print);
~~~

`Function.andThen` và `Function.compose` nhận các `Function`. `Consumer` có phương thức `andThen` riêng để nối **hai Consumer cùng nhận một loại dữ liệu phù hợp**, nhưng không có `compose` giống `Function`.

Bạn có thể tạo một `Function<Integer, Void>` trả `null` sau khi gọi Consumer, song điều đó biến hành động cuối thành một hàm có kết quả giả `Void`. Với mục tiêu nhận dữ liệu rồi thực hiện tác dụng phụ, `Consumer<String>` và lời gọi `accept` biểu đạt hợp đồng rõ ràng hơn.

## 4. Phân biệt Function → Consumer và Consumer.andThen

Hai phép ghép dễ nhầm nhau:

| Biểu thức | Ý nghĩa | Hợp đồng đầu ra |
|---|---|---|
| `Function<A, B>` nối `Consumer<B>` | Biến đổi `A → B` rồi tiêu thụ `B` | `Consumer<A>` |
| `consumer1.andThen(consumer2)` | Cho **cùng một đầu vào** vào hai Consumer theo thứ tự | `Consumer<T>` |
| `function1.andThen(function2)` | Biến đổi dữ liệu qua hai Function | `Function<A, C>` |

Ví dụ `Consumer.andThen`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> events = new ArrayList<>();

Consumer<String> log = text -> events.add("LOG:" + text);
Consumer<String> audit = text -> events.add("AUDIT:" + text);

Consumer<String> both = log.andThen(audit);
both.accept("ORD-42");

System.out.println(events);
// [LOG:ORD-42, AUDIT:ORD-42]
~~~

Ở ví dụ này, `audit` nhận **cùng chuỗi `"ORD-42"`** mà `log` nhận. Giá trị trả về của `log` không được chuyển sang `audit`, vì cả hai đều là `Consumer`.

Trong khi đó, `normalize → save` có chuyển dữ liệu **đã biến đổi** từ Function sang Consumer.

> Nếu Consumer thứ nhất ném ngoại lệ khi chạy đồng bộ, Consumer thứ hai trong `andThen` không được gọi bình thường. Ghép hai tác dụng phụ bằng `andThen` cũng không tự tạo transaction hoặc cơ chế rollback.

## 5. Ví dụ nghiệp vụ đầy đủ trong Spring Cloud Function

Một ứng dụng tiếp nhận dữ liệu đơn hàng dạng chuỗi, ví dụ `" ord-42 , 2 "`. Ta muốn:

1. Chuẩn hóa chữ và khoảng trắng.
2. Phân tích chuỗi thành đối tượng đơn hàng có kiểu rõ ràng.
3. Ghi nhận đối tượng đã chuẩn hóa vào một nơi lưu kết quả.

Sơ đồ:

~~~text
" ord-42 , 2 "                  String
      |
      v
normalizeOrderInput              Function<String, String>
      |
      | "ORD-42 , 2"
      v
parseOrder                       Function<String, OrderCommand>
      |
      | OrderCommand("ORD-42", 2)
      v
saveOrder                        Consumer<OrderCommand>
      |
      v
Ghi nhận đơn hàng; không có giá trị trả về
~~~

Để chạy ví dụ mà không cần database, sử dụng một kho lưu **trong bộ nhớ**. Đây chỉ là adapter thử nghiệm giúp quan sát side effect, không phải thiết kế lưu trữ bền vững.

### 5.1. Khai báo bean với các kiểu tương thích

Ví dụ Java 17 và Spring Boot:

~~~java
package example.functions;

import java.util.List;
import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderCommand(String orderId, int quantity) {}

    public static final class ReceivedOrderStore {
        private final Queue<OrderCommand> orders =
                new ConcurrentLinkedQueue<>();

        public void save(OrderCommand order) {
            orders.add(order);
        }

        public List<OrderCommand> snapshot() {
            return List.copyOf(orders);
        }
    }

    @Bean
    public ReceivedOrderStore receivedOrderStore() {
        return new ReceivedOrderStore();
    }

    @Bean
    public Function<String, String> normalizeOrderInput() {
        return raw -> raw.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, OrderCommand> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Dinh dang can la orderId,quantity");
            }

            String orderId = parts[0].trim();
            int quantity = Integer.parseInt(parts[1].trim());

            if (!orderId.matches("ORD-[0-9]+")
                    || quantity <= 0) {
                throw new IllegalArgumentException(
                        "Ma don hang/so luong khong hop le");
            }

            return new OrderCommand(orderId, quantity);
        };
    }

    @Bean
    public Consumer<OrderCommand> saveOrder(
            ReceivedOrderStore store) {
        return store::save;
    }
}
~~~

Các tên function bean do `@Bean` tạo ra là `normalizeOrderInput`, `parseOrder` và `saveOrder`. Bean `ReceivedOrderStore` chỉ là phụ thuộc của Consumer; nó **không phải Function/Consumer/Supplier được định nghĩa để ghép**.

| Tên bước | Loại | Đầu vào | Đầu ra |
|---|---|---|---|
| `normalizeOrderInput` | Function | `String` | `String` |
| `parseOrder` | Function | `String` | `OrderCommand` |
| `saveOrder` | Consumer | `OrderCommand` | `void` |
| Pipeline đầy đủ | Consumer hợp thành | `String` | `void` |

`normalizeOrderInput` và `parseOrder` xử lý dữ liệu; `saveOrder` là **điểm cuối có tác dụng phụ**. Việc tách biệt này cho phép kiểm thử logic chuẩn hóa/phân tích mà không phải truy cập storage thật.

### 5.2. Ghép theo tên bằng FunctionCatalog.lookup

Khi có Spring Cloud Function trên classpath và các bean được ứng dụng đăng ký, `FunctionCatalog` có thể được inject vào service:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

@Service
public class OrderIngestionService {

    private final FunctionCatalog catalog;

    public OrderIngestionService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public void receive(String rawOrder) {
        Consumer<String> pipeline =
                catalog.lookup(
                    "normalizeOrderInput|parseOrder|saveOrder");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay pipeline tiep nhan don hang");
        }

        pipeline.accept(rawOrder);
    }
}
~~~

`FunctionCatalog.lookup(...)` ở đây trả về một luồng xử lý có hợp đồng **`Consumer<String>`** theo chuỗi ghép được hỗ trợ. Vì vậy, lời gọi đúng là `pipeline.accept(rawOrder)`.

Đoạn sử dụng mẫu trong Spring:

~~~java
orderIngestionService.receive(" ord-42 , 2 ");

// Store nhận:
// new OrderFunctions.OrderCommand("ORD-42", 2)
~~~

Để quan sát thực tế, có thể inject `OrderFunctions.ReceivedOrderStore` và gọi `snapshot()`. Sau lời gọi trên, danh sách chứa bản ghi `OrderCommand("ORD-42", 2)`.

### 5.3. Lớp khởi động ứng dụng

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

Đặt các lớp trong cùng package `example.functions` (hoặc các package được component scan) và khai báo dependency Spring Cloud Function phù hợp với phiên bản Spring Boot của dự án.

**Lưu ý:** Kho lưu `ReceivedOrderStore` chỉ giữ dữ liệu trong bộ nhớ, mất khi khởi động lại. Trong ứng dụng thật, Consumer có thể gọi repository hoặc producer để lưu/phát sự kiện, kèm xử lý lỗi và idempotency phù hợp.

## 6. Cấu hình composition bằng spring.cloud.function.definition

Khi adapter cần sử dụng một pipeline theo tên, ta có thể chỉ định:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrderInput|parseOrder|saveOrder"
~~~

Hoặc trong `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeOrderInput|parseOrder|saveOrder
~~~

Dấu `|` xác định thứ tự **normalize → parse → save**. `saveOrder` ở cuối nên toàn pipeline chỉ **tiêu thụ input**, không trả một kết quả nghiệp vụ.

Phân biệt:

- `catalog.lookup("normalizeOrderInput|parseOrder|saveOrder")`: code Java tra cứu pipeline để gọi bằng `accept(...)`.
- `spring.cloud.function.definition`: chọn tên pipeline cho adapter/integration sử dụng.
- Adapter HTTP, Spring Cloud Stream hoặc serverless: quyết định cách đưa input vào pipeline và xử lý việc không có payload kết quả.

Thuộc tính `definition` **không tự tạo endpoint HTTP hoặc binding với broker** nếu ứng dụng chưa có adapter và cấu hình tương ứng.

### 6.1. Consumer là điểm cuối trong pipeline

Trong ứng dụng, các pipeline sau có hành vi khác nhau:

~~~text
normalizeOrderInput|parseOrder
    Function<String, OrderCommand>

normalizeOrderInput|parseOrder|saveOrder
    Consumer<String>
~~~

Thêm `saveOrder` làm bước cuối thay đổi hợp đồng tổng thể từ **có dữ liệu trả về** sang **không có giá trị trả về**.

Một biểu thức `"saveOrder|parseOrder"` không diễn tả luồng hợp lệ thông thường: `saveOrder` nhận `OrderCommand` và trả `void`, nên không có đối tượng đầu ra để `parseOrder` xử lý.

Spring Cloud Function hỗ trợ nhiều dạng composition trong những trường hợp nhất định, nhưng **đừng giả định Consumer có thể đặt ở giữa rồi được tiếp nối bằng Function bất kỳ**. Nếu muốn vừa lưu lại vừa tạo phản hồi, cần thiết kế pipeline/kiến trúc rõ ràng, không giả định Consumer tự cung cấp dữ liệu cho bước tiếp theo.

## 7. Tương thích kiểu Java và tương thích nghiệp vụ

Giả sử:

~~~text
parse:     Function<String, OrderCommand>
save:      Consumer<OrderCommand>
~~~

Đây là cặp phù hợp: `parse` tạo `OrderCommand` và `save` nhận `OrderCommand`.

Ngược lại:

~~~text
parse:     Function<String, OrderCommand>
sendEmail: Consumer<EmailAddress>
~~~

Không thể nối trực tiếp theo generic Java vì `OrderCommand` không phải `EmailAddress`. Cần một Function trung gian có ý nghĩa, ví dụ `extractEmail: Function<OrderCommand, EmailAddress>`, hoặc thiết kế lại bước xử lý.

### 7.1. Khớp kiểu không đồng nghĩa khớp ý nghĩa

Hai bước cùng dùng `String` vẫn có thể không hợp về mặt nghiệp vụ:

~~~text
extractCustomerId: Function<Order, String>
sendEmail:         Consumer<String> // hiểu String là địa chỉ email
~~~

Chuỗi trên có thể chạy nhưng Consumer nhận **mã khách hàng**, không phải email. Khi thiết kế domain, có thể dùng record tường minh:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

Nhờ đó, `Function<Order, CustomerId>` không thể bị ghép nhầm với `Consumer<EmailAddress>` khi viết Java generic trực tiếp.

### 7.2. Ghép theo tên cần kiểm thử runtime

Trong Java thuần, lỗi kiểu thường bị phát hiện lúc biên dịch:

~~~java
Function<String, Integer> parseInt = Integer::parseInt;
Consumer<Boolean> storeFlag = value -> {};

// Không biên dịch: Integer không dùng được như Boolean.
// Consumer<String> bad = raw -> storeFlag.accept(parseInt.apply(raw));
~~~

Trong Spring Cloud Function, chuỗi `"parseInt|storeFlag"` chỉ là văn bản được phân giải bởi catalog ở runtime. Việc code nhận một `Consumer<String>` từ `lookup` chưa chứng minh tên bean và các kiểu trung gian tương thích.

Khi tra cứu và khi thực thi, các lỗi có thể gồm không tìm thấy bean, kiểu không phù hợp, chuyển đổi payload thất bại hoặc logic nội bộ ném ngoại lệ. Nên viết integration test thật với Spring context.

### 7.3. Tránh ép kiểu tùy tiện

Có thể cố ép mọi giá trị về `Object` hoặc `String` để các bước trông có vẻ tương thích, nhưng làm vậy khiến compiler mất cơ hội phát hiện lỗi. Trước khi nối một Consumer mới, hãy viết bảng hợp đồng: **kiểu được tạo ra**, **ý nghĩa dữ liệu**, **kiểu Consumer chấp nhận** và **hành động Consumer thực hiện**.

## 8. Consumer và tác dụng phụ: cần chú ý gì?

Consumer thường là điểm đầu tiên của pipeline thực hiện một hành động làm thay đổi thế giới bên ngoài: ghi cơ sở dữ liệu, phát message, gửi yêu cầu API hoặc tạo log audit. Vì không có đầu ra, người gọi không nhận lại một object để biết điều gì đã xảy ra ngoài cách Consumer trả về bình thường hoặc ném ngoại lệ.

### 8.1. Thứ tự xảy ra trước và sau hành động

Với composition đồng bộ:

~~~text
Input → validate → transform → save
~~~

Nếu `validate` thất bại, `save` không được gọi. Nếu `save` thất bại, các bước `validate` và `transform` có thể đã chạy, và tác dụng phụ ở những bước trước (nếu có) không tự rollback.

Bởi vậy, nên tổ chức những kiểm tra dữ liệu có thể thực hiện mà không tác động trạng thái **trước** Consumer cuối; các tác dụng phụ quan trọng cần cơ chế bảo đảm riêng khi nghiệp vụ yêu cầu.

### 8.2. Retry và nguy cơ xử lý trùng

Giả sử Consumer đã ghi thành công vào database nhưng adapter không nhận được xác nhận trước khi xảy ra lỗi mạng. Khi message được retry, Consumer có thể chạy lại với cùng dữ liệu.

Composition **không tự cung cấp** exactly-once, giao dịch phân tán hoặc idempotency. Tùy hệ thống, có thể dùng:

- Khóa nghiệp vụ duy nhất, ví dụ `orderId`, và thao tác ghi có kiểm tra trùng.
- Upsert hoặc điều kiện chuyển trạng thái được quản lý tại repository.
- Giao dịch/outbox khi cần nhất quán giữa cập nhật database và phát sự kiện.
- Chính sách retry, dead-letter và acknowledgment phù hợp với adapter.

Phần này cần xem cùng ngữ nghĩa delivery của broker, không nên kết luận chỉ dựa trên việc `Consumer.accept(...)` không ném ngoại lệ.

### 8.3. Thread safety của Consumer bean

Một Consumer được đăng ký thành Spring bean có thể được gọi nhiều lần, và trong một số môi trường, các lời gọi có thể đồng thời. Vì vậy, không lưu trạng thái mutable không đồng bộ trong lambda dùng chung nếu chưa có cơ chế bảo vệ. Ví dụ `ArrayList` trong Java thuần dùng cho một lần kiểm thử là hợp lý, nhưng không thích hợp làm nơi lưu dữ liệu cho nhiều request song song. Ví dụ `ReceivedOrderStore` ở trên dùng `ConcurrentLinkedQueue` để minh họa thao tác thread-safe cơ bản.

## 9. Xử lý lỗi và dữ liệu đặc biệt

### 9.1. Ngoại lệ ở Function khiến Consumer không được gọi

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

Function<String, Integer> parse = Integer::parseInt;

List<Integer> stored = new ArrayList<>();
Consumer<Integer> save = stored::add;

Consumer<String> pipeline =
        raw -> save.accept(parse.apply(raw));

pipeline.accept("12");

try {
    pipeline.accept("invalid");
} catch (NumberFormatException expected) {
    System.out.println("So luong khong hop le");
}

System.out.println(stored); // [12]
~~~

`parse.apply("invalid")` ném `NumberFormatException` trước khi `save.accept(...)` được gọi, nên danh sách không có phần tử mới.

### 9.2. Ngoại lệ từ Consumer vẫn lan ra người gọi

~~~java
Function<String, String> normalize = String::trim;

Consumer<String> failingSink = value -> {
    throw new IllegalStateException("Luu du lieu that bai");
};

Consumer<String> pipeline =
        raw -> failingSink.accept(normalize.apply(raw));

// pipeline.accept("  ORD-42  ") ném IllegalStateException.
~~~

Việc chuẩn hóa đã hoàn thành trước khi Consumer ném lỗi, nhưng phép ghép không có bước tự động phục hồi. Cách adapter thông báo lỗi qua HTTP, message hoặc handler serverless phụ thuộc cấu hình tích hợp.

### 9.3. Null không tự được hiểu là bỏ qua dữ liệu

~~~java
Function<String, String> sometimesNull =
        value -> value.isBlank() ? null : value;

Consumer<String> printUpper =
        value -> System.out.println(value.toUpperCase());

Consumer<String> pipeline =
        raw -> printUpper.accept(sometimesNull.apply(raw));

// pipeline.accept("") dẫn tới NullPointerException.
~~~

`Consumer` có thể nhận `null` ở tầng kiểu tham chiếu Java, nhưng phần lớn logic nghiệp vụ cần hợp đồng rõ ràng cho dữ liệu thiếu. Nếu muốn bỏ qua dữ liệu rỗng, hãy dùng điều kiện được định nghĩa tường minh hoặc mô hình kết quả có trạng thái (ví dụ `Optional`), thay vì giả định composition sẽ tự bỏ qua.

### 9.4. Consumer không có kết quả trả về

Không thể lấy kết quả từ `accept` như từ `apply`:

~~~java
Consumer<String> audit = System.out::println;

// Không biên dịch vì accept trả void.
// String result = audit.accept("ORD-42");
~~~

Muốn trả thông tin sau khi thực thi hành động, hãy thiết kế một `Function<T, R>` trả kết quả rõ ràng hoặc một quy trình orchestration phù hợp. Không nên ép kiểu `Void` hay thêm `return null` chỉ để né sự khác biệt giữa hai hợp đồng.

## 10. Trường hợp Message và headers

Khi đưa pipeline sang sự kiện, bên cạnh payload còn có headers như content-type, correlation ID và metadata vận chuyển. Hai chữ ký sau khác nhau:

~~~text
Function<String, OrderCommand>
Consumer<OrderCommand>
~~~

và:

~~~text
Function<Message<String>, Message<OrderCommand>>
Consumer<Message<OrderCommand>>
~~~

`Message<T>` bao gồm payload cùng headers. Nếu Consumer cần headers để audit hoặc định tuyến, hãy định nghĩa hợp đồng phù hợp hoặc thiết kế bước chuyển đổi tường minh.

Ví dụ tạo message mới từ object:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Function<OrderFunctions.OrderCommand,
         Message<OrderFunctions.OrderCommand>> toMessage =
        order -> MessageBuilder
                .withPayload(order)
                .setHeader("source", "order-ingestion")
                .build();
~~~

Một Consumer nhận message:

~~~java
import java.util.function.Consumer;
import org.springframework.messaging.Message;

Consumer<Message<OrderFunctions.OrderCommand>> auditMessage =
        message -> System.out.println(
                message.getHeaders().get("source")
                + ": " + message.getPayload().orderId());
~~~

Dòng dữ liệu có thể mô tả:

~~~text
Function<String, OrderCommand>
             |
             v
Function<OrderCommand, Message<OrderCommand>>
             |
             v
Consumer<Message<OrderCommand>>
             ⇒ Consumer<String>
~~~

Trong Spring Cloud Function, adapter có thể có cơ chế chuyển đổi payload và làm việc với `Message` theo type metadata. Tuy nhiên, không nên mặc định mọi header tự được giữ qua các Function hoặc mọi payload tự biến thành POJO đúng ý nghĩa. Khi tích hợp broker, hãy kiểm thử với message thật, kiểu payload, serialization và metadata quan trọng.

## 11. Trường hợp reactive Consumer

Với Reactor, hợp đồng kiểu có thể dựa trên cả `Flux`:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;

import reactor.core.publisher.Flux;

Function<Flux<String>, Flux<Integer>> parseNumbers =
        flux -> flux.map(String::trim)
                    .map(Integer::parseInt);

Consumer<Flux<Integer>> printNumbers =
        flux -> flux.subscribe(System.out::println);

Consumer<Flux<String>> pipeline =
        source -> printNumbers.accept(parseNumbers.apply(source));
~~~

Ở mức generic Java, `Function<Flux<String>, Flux<Integer>>` nối được với `Consumer<Flux<Integer>>`. Khi gọi:

~~~java
pipeline.accept(Flux.just(" 4 ", " 9 "));
~~~

`Flux` là luồng **lazy**: các phép `map` chỉ thực hiện khi có subscription. Ví dụ trên dùng `subscribe` tường minh để minh họa. Trong ứng dụng production, gọi `subscribe` tùy tiện có thể làm khó quản lý lỗi, backpressure và vòng đời luồng; cần tuân theo mô hình subscription của framework và adapter đang dùng.

Không nên coi `Function<String, Integer>` và `Consumer<Flux<Integer>>` là hai bước có generic tương thích trực tiếp chỉ vì mỗi phần tử cuối là `Integer`. Hợp đồng đầu vào của Consumer là `Flux<Integer>`, không phải `Integer`.

### 11.1. Consumer imperative và reactive khác nhau về cách kích hoạt

- `Consumer<OrderCommand>` nhận một `OrderCommand` cho mỗi lần `accept`.
- `Consumer<Flux<OrderCommand>>` nhận **một Publisher**; nhiều bản ghi có thể được xử lý khi Publisher phát phần tử.
- Spring Cloud Function/adapter có thể điều chỉnh cách kích hoạt và subscription tùy phiên bản, vì vậy không nên giả định từng message luôn tương ứng một lời gọi `accept` trên reactive Consumer.

Khi kết nối với Spring Cloud Stream, cần kiểm tra hợp đồng framework phiên bản hiện tại, chính sách xử lý lỗi, retry, backpressure và cách subscription được quản lý.

## 12. Function → Consumer trong các môi trường gọi

Một pipeline có cùng logic Java có thể được gắn với nhiều môi trường, nhưng cơ chế kích hoạt và phản hồi khác nhau.

| Môi trường | Dữ liệu đi vào | Ý nghĩa khi Consumer hoàn thành |
|---|---|---|
| Java nội bộ | Code gọi `pipeline.accept(input)` | Phương thức hoàn tất, không trả object |
| HTTP adapter | Adapter nhận request/body và ánh xạ sang Consumer theo hỗ trợ phiên bản | Phản hồi HTTP do adapter quyết định, không có giá trị nghiệp vụ từ Consumer |
| Sự kiện/Stream | Message từ input binding của binder | Consumer đã được gọi; ack/retry phụ thuộc framework/broker |
| Serverless | Event được handler/adapter chuyển thành input | Cách phản hồi/thông báo lỗi tùy nền tảng và adapter |

Ví dụ một consumer kết thúc bằng `saveOrder` thường phù hợp với việc nhận message **đầu vào** từ broker. Vì nó không tạo giá trị `R`, không nên mặc định sẽ có một output binding chứa kết quả nghiệp vụ như `Function<T,R>`.

Sơ đồ tổng quan:

~~~text
HTTP body / Event payload / Java input
                |
                v
          Adapter phù hợp
                |
                v
      Function<String, String>
                |
                v
      Function<String, OrderCommand>
                |
                v
      Consumer<OrderCommand>
                |
                v
        Database / log / side effect
~~~

Hình này mô tả khả năng tái sử dụng logic. Để triển khai thật, cần dependency, cấu hình serializer, mapping message, handler, retry, kết nối database/broker và kiểm thử adapter tương ứng. `spring.cloud.function.definition` chỉ chọn tên pipeline.

## 13. Kiểm thử pipeline

### 13.1. Unit test xác minh thứ tự và dữ liệu chuyển đến Consumer

Với Java thuần và JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerOrderTest {

    @Test
    void transformRunsBeforeSinkAndPassesResult() {
        List<String> calls = new ArrayList<>();

        Function<String, Integer> length = raw -> {
            calls.add("transform");
            return raw.trim().length();
        };

        List<Integer> received = new ArrayList<>();
        Consumer<Integer> sink = value -> {
            calls.add("sink");
            received.add(value);
        };

        Consumer<String> pipeline =
                raw -> sink.accept(length.apply(raw));

        pipeline.accept("  Java  ");

        assertEquals(List.of("transform", "sink"), calls);
        assertEquals(List.of(4), received);
    }
}
~~~

Test kiểm tra **cả thứ tự gọi lẫn dữ liệu Consumer nhận**, mạnh hơn việc chỉ kiểm tra rằng một lời gọi không ném ngoại lệ.

### 13.2. Unit test bảo đảm lỗi bước trước chặn Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerFailureTest {

    @Test
    void parseFailureDoesNotCallSink() {
        Function<String, Integer> parse = Integer::parseInt;

        List<Integer> saved = new ArrayList<>();
        Consumer<Integer> sink = saved::add;

        Consumer<String> pipeline =
                raw -> sink.accept(parse.apply(raw));

        assertThrows(NumberFormatException.class,
                () -> pipeline.accept("invalid"));

        assertEquals(List.of(), saved);
    }
}
~~~

Với tình huống side effect thực tế, nên bổ sung kiểm thử lỗi trong Consumer, lời gọi trùng và chính sách retry ở tầng phù hợp.

### 13.3. Integration test tra cứu qua FunctionCatalog

Cần một Spring Boot context chứa `OrderFunctions`, `OrderApplication` và dependency Spring Cloud Function:

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
class OrderCompositionIntegrationTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private OrderFunctions.ReceivedOrderStore store;

    @Test
    void functionAndConsumerComposeByName() {
        Consumer<String> pipeline = catalog.lookup(
                "normalizeOrderInput|parseOrder|saveOrder");

        assertNotNull(pipeline);
        pipeline.accept(" ord-42 , 2 ");

        assertEquals(
                List.of(new OrderFunctions.OrderCommand(
                        "ORD-42", 2)),
                store.snapshot());
    }
}
~~~

Kiểm thử này xác nhận **tên được tra cứu**, **thứ tự biến đổi**, **kiểu đầu ra của các bước Function** và **tác dụng phụ quan sát được của Consumer** trong môi trường Spring.

Nếu ứng dụng có nhiều test dùng chung Spring context, nên cô lập hoặc xóa dữ liệu của kho thử nghiệm giữa các test. Khi chuyển sang database thật, sử dụng fixture/test container hoặc phương án isolation phù hợp.

### 13.4. Kiểm thử với adapter

Khi chạy qua HTTP, sự kiện hoặc serverless, nên kiểm tra thêm:

- Adapter thực sự chọn pipeline từ `spring.cloud.function.definition`.
- Input raw được deserialize đúng kiểu `String` hoặc POJO mà bước đầu tiên nhận.
- Dữ liệu lỗi không làm Consumer thực hiện side effect.
- Retry/duplicate không tạo bản ghi trùng trái với yêu cầu nghiệp vụ.
- Adapter truyền/ghi nhận correlation ID và headers theo thiết kế.
- Response/ack và error handling của môi trường không phụ thuộc giả định rằng `Consumer.accept` trả một kết quả.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| `function.andThen(consumer)` không biên dịch | `Function.andThen` nhận Function, không nhận Consumer | Tạo `Consumer<A>` bằng lambda hoặc dùng composition của catalog |
| Gọi `pipeline.apply(...)` thất bại | Pipeline kết thúc bằng Consumer | Tra cứu hợp đồng `Consumer<A>` và gọi `accept(...)` |
| `"saveOrder|parseOrder"` không hợp lệ | Consumer không tạo đầu ra cho Function sau | Đặt Consumer ở cuối pipeline |
| `catalog.lookup(...)` không tìm thấy | Tên bean sai, chưa được đăng ký | Kiểm tra `@Bean`, dependency, component scan |
| Pipeline được tra cứu nhưng runtime lỗi | Kiểu/dữ liệu trung gian không phù hợp | Test `accept(...)` với giá trị thật |
| Không có output message | Consumer không có kết quả nghiệp vụ | Thiết kế theo mô hình input-only hoặc tạo Function trả kết quả khi cần |
| Một đơn hàng được lưu nhiều lần | Retry/đầu vào trùng, Consumer không idempotent | Dùng khóa nghiệp vụ, trạng thái xử lý, chính sách retry |
| Không thấy side effect | Adapter chưa gọi pipeline hoặc Consumer thất bại | Kiểm tra definition, binding, logs, lỗi và integration test |

## 15. Bài tập thực hành

**Bài 1 — Ghép Java thuần.** Cho `Function<String, Integer> parse = Integer::parseInt` và `Consumer<Integer> save` ghi vào danh sách. Viết một `Consumer<String>` gọi đúng hai bước. Với input `"21"`, xác định danh sách cuối cùng.

**Bài 2 — Ghép ba bước.** Có `trim: Function<String, String>`, `parse: Function<String, Integer>` và `save: Consumer<Integer>`. Hãy viết lambda tạo pipeline tổng thể và biểu thức Spring Cloud Function ghép theo tên. Đầu vào `" 7 "` sẽ đến Consumer ở dạng nào?

**Bài 3 — Phân biệt hai loại andThen.** Tại sao `Function<String,Integer>.andThen(Consumer<Integer>)` không biên dịch trong Java? Hãy viết một ví dụ `Consumer<Integer>.andThen(Consumer<Integer>)` và giải thích có hay không việc truyền đầu ra từ Consumer trước sang Consumer sau.

**Bài 4 — Kiểu trung gian.** Một hàm `parseOrder: Function<String, OrderCommand>` muốn nối với `sendEmail: Consumer<EmailAddress>`. Hãy đề xuất bước trung gian và lý do cần hợp đồng kiểu nghiệp vụ cụ thể.

**Bài 5 — Tình huống lỗi.** Trong pipeline `normalizeOrderInput|parseOrder|saveOrder`, điều gì xảy ra khi input là `"ORD-42,0"` hoặc `"ORD-42,abc"`? `saveOrder` có được gọi không? Nêu một kiểm thử chứng minh.

**Bài 6 — Sự kiện và retry.** Consumer lưu đơn hàng vào database. Sau khi lưu thành công, kết nối với broker bị lỗi trước lúc xác nhận message. Nếu broker gửi lại, có thể xảy ra chuyện gì? Đề xuất cách xử lý trùng theo `orderId`.

### Gợi ý đáp án

- **Bài 1:** `Consumer<String> combined = input -> save.accept(parse.apply(input));`; danh sách có `21`.
- **Bài 2:** `raw -> save.accept(parse.apply(trim.apply(raw)))`; tên ghép `"trim|parse|save"`; Consumer nhận `Integer` có giá trị `7`.
- **Bài 3:** `andThen` của Function yêu cầu Function; `Consumer.andThen` gửi cùng đầu vào lần lượt cho hai Consumer, không truyền kết quả.
- **Bài 4:** Chẳng hạn `extractEmail: Function<OrderCommand, EmailAddress>`.
- **Bài 5:** Lỗi ở `parseOrder` dừng chuỗi trước `saveOrder`; kiểm tra kho nhận vẫn rỗng.
- **Bài 6:** Có thể lưu trùng; dùng ràng buộc unique key hoặc xử lý idempotent theo `orderId`, phối hợp retry/ack đúng thiết kế.

## 16. Ghi nhớ

- `Function<A, B>` tạo kết quả `B`; `Consumer<B>` nhận `B` và không trả giá trị nghiệp vụ.
- Ghép theo thứ tự **Function → Consumer** tạo hành vi của `Consumer<A>`: `input -> sink.accept(transform.apply(input))`.
- Java `Function.andThen` không nhận `Consumer`; `Consumer.andThen` là phép ghép **hai Consumer** cùng dùng đầu vào.
- Spring Cloud Function cho phép ghép theo tên, ví dụ `catalog.lookup("normalizeOrderInput|parseOrder|saveOrder")`; pipeline này được gọi bằng `accept(...)`.
- Đặt Consumer ở cuối chuỗi biến đổi và kiểm tra cả **kiểu trung gian lẫn ý nghĩa dữ liệu** trước khi tạo side effect.
- Khi triển khai qua HTTP, sự kiện hoặc serverless, cần adapter và cơ chế xử lý lỗi/ack/retry phù hợp; composition không tự bảo đảm giao dịch hay chống trùng.
