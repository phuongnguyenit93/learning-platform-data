# Xác thực dữ liệu ở ranh giới trước khi chạy nghiệp vụ

## 1. Mục tiêu bài học

Spring Cloud Function cho phép đóng gói logic trong `Supplier`, `Function` và `Consumer`, đăng ký qua `FunctionCatalog` và ghép thành pipeline để gọi từ Java, HTTP, hệ thống sự kiện hoặc môi trường serverless. Tuy nhiên, khả năng tái sử dụng đó cũng tạo ra một thách thức: **cùng một hàm có thể nhận đầu vào từ nhiều nguồn với mức độ tin cậy khác nhau**.

Một HTTP client có thể gửi JSON thiếu trường, một message có thể chứa payload sai phiên bản, còn một serverless trigger có thể được kích hoạt lại bằng dữ liệu cũ. Nếu nghiệp vụ tính giá, ghi database hoặc phát sự kiện trước khi kiểm tra đầu vào, các lỗi có thể gây tác dụng phụ không mong muốn và khó khôi phục.

Trong chương **Độ tin cậy**, bài này tập trung vào **xác thực dữ liệu tại ranh giới đầu vào trước khi chạy nghiệp vụ**. Sau bài học, bạn có thể:

- Phân biệt xác thực dữ liệu (validation), giải mã/chuyển kiểu (deserialization/conversion) và kiểm tra quyền truy cập (authorization).
- Thiết kế pipeline `normalize → validate → business → side effect` với kiểu Java rõ ràng.
- Sử dụng Jakarta Bean Validation một cách **tường minh** trong Function bean.
- Hiểu vì sao không thể chỉ thêm `@Valid` vào DTO rồi mặc định `FunctionCatalog` tự kiểm tra.
- Phân loại lỗi input, lỗi quy tắc nghiệp vụ, lỗi hạ tầng và chọn cách xử lý retry phù hợp.
- Bảo vệ Consumer có tác dụng phụ trước dữ liệu sai, dữ liệu bị gửi lại và các trường hợp cạnh tranh.
- Kiểm thử riêng validation, toàn pipeline trong `FunctionCatalog` và adapter HTTP/message/serverless.

> Ví dụ sử dụng Java 17, Spring Boot 3+ và namespace `jakarta.validation`. Với dự án dùng Spring Boot/Spring Cloud Function phiên bản khác, cần chọn dependency, namespace và cơ chế adapter tương thích. Các ví dụ validation trong bài được **gọi chủ động** từ Function, không dựa vào một hành vi xác thực ngầm chưa được kiểm chứng.

## 2. “Ranh giới” nằm ở đâu?

Ranh giới không chỉ là HTTP controller. Với Spring Cloud Function, input có thể đến từ nhiều đường:

~~~text
HTTP JSON ─────────┐
                   |
Kafka/Rabbit event ├──> Adapter / converter
                   |            |
Serverless event ──┤            v
                   |       Input DTO / Message<T>
Java caller ───────┘            |
                                v
                        normalizeInput
                                |
                                v
                        validateInput
                                |
                                v
                         businessLogic
                                |
                                v
                   Consumer / persist / publish
~~~

Ta thường có ít nhất ba lớp kiểm tra:

1. **Lớp vận chuyển/chuyển đổi:** request hoặc message có đọc được không? JSON có hợp lệ? Kiểu số/chuỗi có đúng? Payload có vượt giới hạn kích thước?
2. **Lớp DTO/validation:** trường bắt buộc có tồn tại? Giá trị có đúng mẫu? Độ dài/số lượng có nằm trong ngưỡng?
3. **Lớp nghiệp vụ:** người dùng có quyền thực hiện không? SKU có được bán? Số lượng có đáp ứng hạn mức hoặc tồn kho hiện tại? Đơn có bị xử lý trùng?

Không nên gộp các nhóm thành một khối “validate” mơ hồ. **Authorization** và xác thực danh tính nằm ở lớp bảo mật thích hợp; Bean Validation không thể thay thế kiểm tra quyền.

### 2.1. Ví dụ phân loại lỗi

| Input hoặc tình huống | Lớp phát hiện chính | Ví dụ hướng xử lý |
|---|---|---|
| JSON không parse được | Converter/HTTP adapter | Từ chối trước khi vào Function |
| Trường `quantity` không có | DTO validation | Lỗi thiếu trường |
| `quantity = -3` | DTO validation | Lỗi giới hạn giá trị |
| `sku = "??"` | DTO validation | Lỗi định dạng |
| SKU đúng mẫu nhưng đã ngừng bán | Nghiệp vụ | Từ chối theo quy tắc hiện hành |
| Request hợp lệ nhưng user không có quyền | Security/authorization | Từ chối truy cập |
| Database timeout khi ghi | Hạ tầng | Có thể retry theo chính sách |
| Cùng mã đơn hàng nhưng nội dung khác | Nhất quán/idempotency | Conflict, không ghi đè âm thầm |

Những lỗi đầu vào **không thể tự trở nên đúng nhờ retry** nếu payload giữ nguyên. Cần phân biệt chúng với lỗi I/O tạm thời.

## 3. Vì sao phải kiểm tra trước nghiệp vụ?

Giả sử pipeline không kiểm tra dữ liệu:

~~~text
Input → calculatePrice → saveQuote → validateOrder
~~~

Nếu `quantity = 0`, bước `saveQuote` có thể đã ghi giá trị sai trước khi `validateOrder` ném ngoại lệ. Nếu hệ thống message retry sau lỗi, tác dụng phụ có thể lặp lại.

Thiết kế an toàn hơn:

~~~text
Input → normalize → validate → calculatePrice → saveQuote
                         |                          |
                         | lỗi: dừng trước ghi      | side effect
                         v                          v
                      Từ chối                 Idempotent storage
~~~

Với Java đồng bộ, khi Function validation ném ngoại lệ, các bước phía sau không chạy bình thường. Điều này không thay thế transaction hoặc idempotency, nhưng làm **giảm phạm vi tác dụng phụ khi input sai**.

### 3.1. “Kiểm tra sớm” không có nghĩa kiểm tra mọi thứ hai lần

Một client có thể có validation giao diện để người dùng nhận lỗi sớm, nhưng **server phải kiểm tra lại** vì client và payload không đáng tin cậy.

Mặt khác, việc kiểm tra cú pháp trên cùng đối tượng qua nhiều lớp không nên bị nhân bản vô nghĩa. Hãy phân định trách nhiệm: converter xác nhận cấu trúc; Function validation xác nhận hợp đồng DTO; business kiểm tra các điều kiện cần trạng thái hiện tại.

## 4. Thiết kế hợp đồng đầu vào

Ví dụ dịch vụ tạo báo giá nhận JSON tương ứng với:

~~~json
{
  "orderId": "  ord-42 ",
  "sku": " sku-7 ",
  "quantity": 2
}
~~~

Yêu cầu:

- `orderId` sau chuẩn hóa có dạng `ORD-<1 đến 10 chữ số>`.
- `sku` sau chuẩn hóa có dạng `SKU-<1 đến 10 chữ số>`.
- `quantity` là số nguyên trong khoảng 1 đến 100.
- Không dùng dữ liệu chưa được kiểm tra để tính tiền hoặc ghi dữ liệu.

Ta sử dụng ba kiểu domain:

~~~text
OrderRequest (dữ liệu adapter nhận)
       |
       v
ValidatedOrder (đã qua validation)
       |
       v
Quote (kết quả nghiệp vụ)
~~~

Dùng kiểu trung gian giúp tránh nhầm `Function<OrderRequest,Quote>` với hàm chỉ được phép nhận đầu vào đã được xác thực.

## 5. Khai báo DTO với Jakarta Bean Validation

Ví dụ dùng record trong Java 17:

~~~java
package example.functions;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public final class OrderModels {

    private OrderModels() {}

    public record OrderRequest(
            @NotBlank
            @Pattern(regexp = "ORD-[0-9]{1,10}")
            String orderId,

            @NotBlank
            @Pattern(regexp = "SKU-[0-9]{1,10}")
            String sku,

            @NotNull
            @Min(1)
            @Max(100)
            Integer quantity) {}

    public record ValidatedOrder(
            String orderId,
            String sku,
            int quantity) {}

    public record Quote(
            String orderId,
            String sku,
            int quantity,
            long totalVnd) {}
}
~~~

Các annotation có vai trò khác nhau:

| Annotation | Ràng buộc | Trường ví dụ |
|---|---|---|
| `@NotBlank` | Chuỗi không null, không chỉ toàn khoảng trắng | `orderId`, `sku` |
| `@Pattern` | Chuỗi phù hợp regex; giá trị null được constraint này bỏ qua | `orderId`, `sku` |
| `@NotNull` | Giá trị phải có | `quantity` |
| `@Min(1)` | Ít nhất 1 | `quantity` |
| `@Max(100)` | Nhiều nhất 100 | `quantity` |

`quantity` dùng `Integer` thay vì `int` để thể hiện trường có thể **thiếu** sau deserialize (null). Nếu dùng primitive `int`, một số cơ chế binding có thể đưa giá trị mặc định 0, khiến việc phân biệt “thiếu trường” và “người gửi nhập 0” khó hơn.

Regex trong ví dụ cố ý đơn giản và có giới hạn. Trên dữ liệu lớn hoặc regex phức tạp, cần giới hạn kích thước payload trước khi kiểm tra và tránh những biểu thức có nguy cơ gây tiêu tốn CPU.

### 5.1. Annotation không tự chạy chỉ vì object tồn tại

Việc tạo:

~~~java
OrderModels.OrderRequest request =
        new OrderModels.OrderRequest("BAD", "SKU-7", 2);
~~~

**không tự động ném lỗi** chỉ vì record có `@Pattern`. Constraint chỉ được đánh giá khi một cơ chế validation thực sự gọi `Validator.validate(...)`, hoặc khi framework được cấu hình để gọi validation tại đúng ranh giới.

Tương tự, không nên mặc định `FunctionCatalog.lookup(...).apply(request)` sẽ tự xem annotation và từ chối input. Trong bài này, ta **đăng ký một Function validation riêng và gọi Validator tường minh**.

## 6. Bổ sung dependency validation đúng phiên bản

Với Spring Boot 3+ (Java 17 trở lên), thông thường dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Starter cung cấp cơ chế Jakarta Bean Validation và implementation phù hợp với phiên bản Boot được quản lý bởi BOM. Ứng dụng vẫn cần Spring Cloud Function context/starter tương thích để có `FunctionCatalog`.

Nếu dự án cũ dùng `javax.validation`, không tự chuyển sang `jakarta.validation` mà bỏ qua tương thích Spring Boot/Spring Framework. Phải dùng một bộ phiên bản nhất quán.

Lưu ý: một số ứng dụng chỉ có `spring-cloud-function-context` nhưng không có Spring Web. Chúng vẫn có thể dùng `Validator` trực tiếp; validation không yêu cầu nhất thiết phải có HTTP controller.

## 7. Tách chuẩn hóa và validation thành hai Function

Dữ liệu raw có thể chứa khoảng trắng/chữ thường. Ta muốn **chuẩn hóa có chủ đích trước**, rồi kiểm tra theo định dạng canonical.

~~~text
OrderRequest("  ord-42 ", " sku-7 ", 2)
                     |
                     v
normalizeOrderRequest
                     |
                     v
OrderRequest("ORD-42", "SKU-7", 2)
                     |
                     v
validateOrderRequest
                     |
                     v
ValidatedOrder("ORD-42", "SKU-7", 2)
~~~

Việc chuẩn hóa không được âm thầm che các lỗi quan trọng. Ví dụ không tự cắt bớt chuỗi quá dài hoặc sửa một mã SKU sai thành mã khác để “cho qua validation”. Chỉ áp dụng những phép chuẩn hóa được hợp đồng nghiệp vụ cho phép.

### 7.1. Kiểu lỗi validation tường minh

~~~java
package example.functions;

import java.util.List;

public class InvalidOrderException extends RuntimeException {

    private final List<String> violations;

    public InvalidOrderException(List<String> violations) {
        super("Order request khong hop le");
        this.violations = List.copyOf(violations);
    }

    public List<String> violations() {
        return violations;
    }
}
~~~

Lỗi này đại diện cho input không hợp lệ theo hợp đồng DTO. Không dùng nó để che timeout database hoặc lỗi bảo mật. Khi trả thông tin lỗi cho bên ngoài, chỉ công bố dữ liệu thích hợp, tránh đưa raw payload, token hoặc nội dung nhạy cảm vào response/log.

### 7.2. Cấu hình Function bean

~~~java
package example.functions;

import java.util.List;
import java.util.Locale;
import java.util.function.Function;

import jakarta.validation.Validator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class OrderFunctions {

    private static String canonical(String input) {
        return input == null
                ? null
                : input.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<OrderRequest, OrderRequest> normalizeOrderRequest() {
        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        List.of("body: required"));
            }

            return new OrderRequest(
                    canonical(input.orderId()),
                    canonical(input.sku()),
                    input.quantity());
        };
    }

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrderRequest(
            Validator validator) {

        return input -> {
            if (input == null) {
                throw new InvalidOrderException(
                        List.of("body: required"));
            }

            List<String> errors = validator.validate(input)
                    .stream()
                    .map(v -> v.getPropertyPath()
                            + ": " + v.getMessage())
                    .sorted()
                    .toList();

            if (!errors.isEmpty()) {
                throw new InvalidOrderException(errors);
            }

            return new ValidatedOrder(
                    input.orderId(),
                    input.sku(),
                    input.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> new Quote(
                order.orderId(),
                order.sku(),
                order.quantity(),
                Math.multiplyExact(
                        order.quantity(), 125_000L));
    }
}
~~~

Giả định `Validator` được đăng ký trong Spring context bởi cấu hình validation tương thích. Dòng `validator.validate(input)` là điểm **thực thi validation**; không phải chỉ có annotation trên DTO.

Sau khi validation thành công, pipeline nhận `ValidatedOrder`. Java chuyển từ `Integer` sang `int` tại bước dựng object; vì `@NotNull` đã được kiểm tra trước nên giá trị không null trong đường chạy thành công.

### 7.3. Thứ tự không thể đổi tùy ý

Nếu đặt `validateOrderRequest` trước `normalizeOrderRequest`, input `" ord-42 "` sẽ không khớp regex canonical dù nghiệp vụ cho phép khoảng trắng ngoài. Nếu đặt `calculateQuote` trước validation, nó không có hợp đồng nhận `OrderRequest` và có thể chạy trên dữ liệu sai.

Thứ tự mong muốn là:

~~~text
normalizeOrderRequest
        |
        v
validateOrderRequest
        |
        v
calculateQuote
~~~

Đầu ra của từng bước phải phù hợp đầu vào bước kế tiếp; `String`, `OrderRequest`, `ValidatedOrder` và `Quote` không thể hoán đổi chỉ vì có field tương tự nhau.

## 8. Quy tắc nghiệp vụ động vẫn phải được kiểm tra

Bean Validation rất hữu ích cho hợp đồng DTO nhưng không thể thay thế toàn bộ nghiệp vụ.

Ví dụ: SKU `SKU-7` đúng regex nhưng hiện đang bị ngừng bán; `quantity=20` nằm trong khoảng 1..100 nhưng kho chỉ còn 4. Các dữ kiện này phụ thuộc trạng thái hiện tại của hệ thống.

Một cách phân tách:

~~~text
Adapter / deserialize
         |
normalizeOrderRequest
         |
validateOrderRequest          (ràng buộc DTO)
         |
loadCatalogOrInventory         (đọc dữ liệu ngoài)
         |
decideOrder                   (quy tắc nghiệp vụ từ snapshot)
         |
persist / publish             (tác dụng phụ)
~~~

Nếu validation phụ thuộc dữ liệu ngoài, đừng tuyên bố nó là một Function thuần chỉ vì có chữ ký `Function<T,R>`. Khi có thể, đưa snapshot dữ liệu vào một kiểu input rõ ràng và giữ bước ra quyết định xác định.

### 8.1. Authorization không phải Bean Validation

Một request có `orderId` và `sku` hợp lệ vẫn có thể được gửi bởi người dùng không có quyền thao tác. Security phải xác minh identity/authorization tại ranh giới tin cậy thích hợp.

Không nên đưa access token vào regex DTO rồi coi là kiểm tra quyền. Cũng không dựa duy nhất vào giá trị `userId` do client cung cấp để quyết định ownership; danh tính đáng tin phải được xác nhận bởi cơ chế authentication/authorization.

## 9. Ghép các Function với FunctionCatalog

Spring Cloud Function đăng ký các Function bean theo tên. Với các bean ở mục 7, pipeline tính báo giá có thể được tra cứu:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote quote(OrderRequest request) {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return pipeline.apply(request);
    }
}
~~~

Luồng được thực thi từ trái qua phải:

~~~text
OrderRequest
    |
    v
normalizeOrderRequest    Function<OrderRequest,OrderRequest>
    |
    v
validateOrderRequest     Function<OrderRequest,ValidatedOrder>
    |
    v
calculateQuote           Function<ValidatedOrder,Quote>
    |
    v
Quote
~~~

Kết quả cho input `new OrderRequest(" ord-42 "," sku-7 ",2)` là một `Quote` có `orderId="ORD-42"`, `sku="SKU-7"`, `quantity=2` và `totalVnd=250000`.

Chú ý: tên bean trong biểu thức `lookup` là chuỗi ký tự nên compiler không kiểm tra được tên có tồn tại hay generic giữa mọi bước. Integration test cần xác nhận chuỗi bằng chính Spring context sử dụng trong ứng dụng.

## 10. Đặt Consumer có tác dụng phụ sau validation

Giả sử hệ thống cần lưu báo giá. Nên tách một port cho side effect:

~~~java
package example.functions;

import example.functions.OrderModels.Quote;

public interface QuoteSink {
    void save(Quote quote);
}
~~~

Đăng ký Consumer:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteSinkFunctions {

    @Bean
    public Consumer<Quote> saveQuote(QuoteSink sink) {
        return sink::save;
    }
}
~~~

Khi đó, pipeline ghi dữ liệu là:

~~~text
normalizeOrderRequest|validateOrderRequest|calculateQuote|saveQuote
        ⇒ Consumer<OrderRequest>
~~~

`saveQuote` chạy **sau** khi validation và tính toán thành công. Nó không trả `Quote`, nên không thể nối Function phía sau rồi kỳ vọng Consumer chuyển tiếp output.

### 10.1. Một implementation đơn giản để kiểm thử

~~~java
package example.functions;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import example.functions.OrderModels.Quote;

@Component
public class InMemoryQuoteSink implements QuoteSink {

    private final ConcurrentHashMap<String, Quote> records =
            new ConcurrentHashMap<>();

    @Override
    public void save(Quote quote) {
        Quote old = records.putIfAbsent(
                quote.orderId(), quote);

        if (old != null && !old.equals(quote)) {
            throw new IllegalStateException(
                    "Cung orderId nhung quote khac nhau");
        }
    }

    public Quote find(String orderId) {
        return records.get(orderId);
    }

    public int size() {
        return records.size();
    }

    public Map<String, Quote> snapshot() {
        return Map.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

`putIfAbsent` giúp tránh tạo hai bản ghi với cùng `orderId` trong một instance JVM, và phát hiện conflict khi cùng key có payload khác. Đây chỉ là ví dụ in-memory; **không có persistence, unique constraint nhiều replica hay transaction với broker**.

### 10.2. Thử gọi pipeline Consumer

~~~java
import java.util.function.Consumer;

import example.functions.OrderModels.OrderRequest;

Consumer<OrderRequest> pipeline = catalog.lookup(
        "normalizeOrderRequest|validateOrderRequest"
        + "|calculateQuote|saveQuote");

if (pipeline == null) {
    throw new IllegalStateException("Thieu consumer pipeline");
}

pipeline.accept(new OrderRequest(" ord-42 ", " sku-7 ", 2));
~~~

Dữ liệu được xác thực trước khi ghi. Nếu gọi với `quantity=0`, `validateOrderRequest` ném `InvalidOrderException` và `saveQuote` chưa được gọi trong luồng đồng bộ.

## 11. Thế nào là “đủ validation”?

Một sai lầm thường gặp là cho rằng vài annotation giải quyết toàn bộ vấn đề dữ liệu.

### 11.1. Các khía cạnh thường cần kiểm tra

| Khía cạnh | Ví dụ | Nơi phù hợp |
|---|---|---|
| Cấu trúc payload | JSON parse được, đúng kiểu | Converter/adapter |
| Giá trị bắt buộc | Không thiếu `orderId`, `quantity` | DTO validation |
| Giới hạn kích thước | Body size, chuỗi dài bất thường | Gateway/adapter + DTO |
| Định dạng | `ORD-42`, `SKU-7` | DTO validation |
| Khoảng giá trị | `1 <= quantity <= 100` | DTO validation |
| Ràng buộc chéo | Ngày kết thúc không trước ngày bắt đầu | Custom validator hoặc nghiệp vụ |
| Quy tắc động | Hàng còn bán, tồn kho đủ | Business service |
| Quyền truy cập | Khách này có quyền tạo đơn không? | Authentication/authorization |
| Chống gửi trùng | Cùng `orderId` / idempotency key | Storage/transaction |

Các phép kiểm tra tối thiểu cần được áp dụng ở **mọi đường vào** có thể đưa dữ liệu chưa tin cậy tới nghiệp vụ. Đừng chỉ validate HTTP controller nếu cùng Function còn được gọi từ Kafka hoặc serverless.

### 11.2. Null, trường thiếu và sai kiểu khác nhau

Nếu JSON chứa `"quantity": "abc"`, converter có thể thất bại trước khi tạo `OrderRequest`. Nếu không có trường `quantity`, DTO có thể được tạo với `quantity=null` rồi `@NotNull` phát hiện.

Nếu JSON có `"quantity": 0`, DTO tạo được nhưng `@Min(1)` phát hiện. Ba tình huống này xảy ra ở các tầng khác nhau và có thể cần mã lỗi/quan sát riêng.

### 11.3. Các trường lồng nhau

Nếu request có object con, `@Valid` trên một field lồng nhau có thể yêu cầu validator thực hiện validation dạng cascade khi gọi `Validator.validate(...)` trên object cha.

Tuy nhiên, `@Valid` là **chỉ dẫn cascade**, không phải bằng chứng rằng Spring Cloud Function tự kích hoạt validation. Cần kiểm tra rõ cơ chế đang gọi `Validator` ở đâu, kể cả khi các object lồng nhau được tạo từ JSON.

## 12. Lỗi nên có hợp đồng rõ ràng

Trong ví dụ, `InvalidOrderException` chứa danh sách vi phạm. Điều quan trọng là **phân loại lỗi trước khi áp dụng retry**:

| Lỗi | Ví dụ | Có nên retry nguyên payload? |
|---|---|---|
| Payload không đọc được | JSON sai cú pháp | Thường không |
| DTO không hợp lệ | Thiếu `quantity`, SKU sai mẫu | Thường không |
| Quy tắc nghiệp vụ từ chối | SKU không còn bán | Tùy chính sách; không retry vô hạn |
| Không được phép | User không có quyền | Không dùng retry như cách bỏ qua bảo mật |
| Lỗi tạm thời | Database timeout | Có thể, nếu thao tác idempotent |
| Conflict idempotency | Cùng `orderId` nhưng payload khác | Thường báo conflict |
| Không rõ commit đã thành công | Mất ack/response | Kiểm tra trạng thái hoặc retry idempotent |

Nếu một Consumer bắt mọi exception rồi bỏ qua, adapter có thể coi xử lý thành công và xác nhận message dù dữ liệu chưa được lưu. Hãy để lỗi được truyền hoặc ánh xạ rõ theo policy, không nuốt âm thầm.

## 13. HTTP: phân biệt validation của Function và của controller

Với một REST controller tự gọi `QuoteService`, có thể kiểm soát pipeline đầu vào rõ ràng:

~~~java
package example.functions;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@RestController
@RequestMapping("/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping
    public Quote quote(@RequestBody OrderRequest request) {
        return service.quote(request);
    }
}
~~~

Ở đây **chính `validateOrderRequest` trong pipeline** gọi `Validator`. Controller không cần dựa vào `@Valid` trên tham số để thực hiện cùng validation. Nếu chọn validation ngay ở controller bằng `@Valid @RequestBody`, phải biết đường vào message/serverless có thực hiện cùng ràng buộc hay không.

Một cách ánh xạ lỗi từ `InvalidOrderException` sang HTTP 400:

~~~java
package example.functions;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<Map<String, Object>> invalidOrder(
            InvalidOrderException ex) {

        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(Map.of(
                        "code", "INVALID_ORDER",
                        "violations", ex.violations()));
    }
}
~~~

Response minh họa có dạng:

~~~json
{
  "code": "INVALID_ORDER",
  "violations": ["quantity: must be greater than or equal to 1"]
}
~~~

Thông điệp validation thực tế phụ thuộc provider và locale, nên client **không nên phụ thuộc chính xác vào câu chữ**. API production nên có mã lỗi ổn định, giới hạn dữ liệu được công bố và xử lý riêng trường hợp JSON parse thất bại (ví dụ lỗi ở `HttpMessageNotReadableException` trước khi Function chạy).

### 13.1. HTTP adapter có thể khác controller tùy chỉnh

Spring Cloud Function có web adapter riêng khi ứng dụng dùng starter tương ứng. Cơ chế công bố endpoint, chuyển đổi request/response và ánh xạ exception có thể khác với ví dụ `@RestController` tự viết.

Không mặc định `@RestControllerAdvice` của ví dụ sẽ quản lý tất cả adapter hoặc tự động áp dụng cho handler serverless. Phải test đúng đường gọi đang triển khai.

## 14. Sự kiện: xử lý poison message trước side effect

Trong Spring Cloud Stream, input có thể là message từ broker. Payload JSON có thể bị lỗi khi deserialize, hoặc deserialize được thành DTO nhưng không đáp ứng constraint.

~~~text
Broker Message
      |
      v
Binder / message converter
      |
      v
OrderRequest
      |
      v
normalizeOrderRequest
      |
      v
validateOrderRequest
      |
      +--- invalid → error policy / DLQ / quan sát
      |
      v
calculateQuote → saveQuote
      |
      v
Ack theo chính sách binder
~~~

Một **poison message** là thông điệp liên tục làm xử lý thất bại, ví dụ sai schema hoặc dữ liệu không thể sửa tự động. Nếu cấu hình retry vô hạn, nó có thể gây vòng lặp lỗi hoặc cản trở các message hợp lệ.

Cần phân loại lỗi invalid-payload và lỗi tạm thời, rồi quyết định bỏ, cách ly vào dead-letter hoặc phản hồi khác theo yêu cầu. Khả năng DLQ, retry, cách cấu hình ack và binding phụ thuộc broker/binder/version; không được suy diễn từ `FunctionCatalog`.

### 14.1. Message headers và schemaVersion

Nếu adapter dùng `Message<OrderRequest>`, headers có thể chứa `eventId`, `schemaVersion`, correlation ID hoặc thông tin từ transport. Khi kiểm tra:

- Chỉ tin những headers thực sự được bảo vệ/đảm bảo bởi hệ thống.
- Kiểm tra phiên bản schema trước khi diễn giải dữ liệu theo một hợp đồng mới.
- Bảo toàn correlation ID cần thiết cho quan sát, tránh phát tán dữ liệu nhạy cảm.
- Có idempotency theo định danh sự kiện hoặc khóa nghiệp vụ để xử lý redelivery.

`OrderRequest` và `Message<OrderRequest>` có generic khác nhau. Nếu Function cần headers, phải khai báo hợp đồng phù hợp hoặc có bước adapter tách payload một cách tường minh; không giả định mọi header tự được giữ qua mọi kiểu composition.

## 15. Serverless: validation phải chạy ở mỗi invocation

Một handler serverless có thể nhận event từ HTTP, queue, scheduler hoặc event bus. Điều kiện chạy, conversion và retry có thể khác nhau nhưng quy tắc chung vẫn là:

~~~text
Event → Deserialize → Validate → Business → Side effect
~~~

Không tin rằng sự kiện được gọi bởi một cloud service khác thì chắc chắn đúng schema. Event có thể là bản cũ, bị thay đổi, thiếu field hoặc được giao lại sau lỗi.

Nếu handler gọi lại cùng Function bean, nên dùng **một bước validation chung** để tránh chênh lệch quy tắc giữa HTTP và serverless. Cách thông báo lỗi ra nền tảng phụ thuộc adapter, trigger và cấu hình retry của nhà cung cấp.

### 15.1. Đừng dùng retry để chữa lỗi validation

Nếu message có `quantity=-1`, retry cùng payload sẽ tiếp tục sai. Retry hợp lý hơn với lỗi kết nối tạm thời, và vẫn phải bảo vệ side effect bằng idempotency.

## 16. Khi cần validation chéo các trường

Annotation mức field giải quyết nhiều ràng buộc cơ bản. Nhưng các điều kiện như “`endAt` phải sau `startAt`” hoặc “nếu `type=EXPRESS` thì số lượng tối đa là 10” liên quan nhiều trường.

Có thể viết một Function riêng theo domain:

~~~java
import java.util.function.Function;

record ShippingRequest(
        String type,
        int packageCount) {}

Function<ShippingRequest, ShippingRequest> checkShippingRule =
        request -> {
            if ("EXPRESS".equals(request.type())
                    && request.packageCount() > 10) {
                throw new IllegalArgumentException(
                        "EXPRESS toi da 10 kien");
            }
            return request;
        };
~~~

Hàm trả lại input đã kiểm tra để pipeline sau vẫn có dữ liệu. Nếu quy tắc phải truy vấn kho hoặc quyền truy cập, nó không còn là validation thuần; cần thiết kế dependency, transaction hoặc snapshot phù hợp.

### 16.1. Không chuyển mọi validation thành Boolean

Nếu `validateOrder` trả `Boolean`, Function tiếp theo muốn nhận `ValidatedOrder` sẽ không có dữ liệu đầu vào. Nên trả đối tượng đã qua kiểm tra, hoặc một kiểu kết quả có cấu trúc và có Function giải quyết trạng thái lỗi trước khi thực thi nghiệp vụ.

## 17. Reactive: validate trước khi tạo side effect

Trong ứng dụng reactive, có thể nâng các Function xử lý từng giá trị thành một pipeline `Flux`:

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

Function<OrderRequest, OrderRequest> normalize =
        orderFunctions.normalizeOrderRequest();

Function<OrderRequest, ValidatedOrder> validate =
        orderFunctions.validateOrderRequest(validator);

Function<ValidatedOrder, Quote> calculate =
        orderFunctions.calculateQuote();

Function<Flux<OrderRequest>, Flux<Quote>> pipeline =
        flux -> flux
                .map(normalize)
                .map(validate)
                .map(calculate);
~~~

`orderFunctions` là instance/cấu hình đã được cung cấp cùng `Validator` là dependency hiện diện trong Spring context. Dữ liệu mỗi phần tử đi theo thứ tự normalize → validate → calculate.

Với Reactor, mapper có thể được gọi khi subscriber yêu cầu dữ liệu. Nếu validation ném `InvalidOrderException`, nó thường thành tín hiệu `onError`; luồng mặc định kết thúc khi gặp lỗi không được xử lý.

### 17.1. Một phần tử sai có thể dừng cả Flux

~~~java
Flux<OrderRequest> inputs = Flux.just(
        new OrderRequest("ORD-42", "SKU-7", 2),
        new OrderRequest("BAD", "SKU-7", 2),
        new OrderRequest("ORD-43", "SKU-8", 2));
~~~

Nếu không có chính sách lỗi riêng từng phần tử, `"BAD"` có thể làm luồng dừng trước khi xử lý `ORD-43`. Việc bỏ qua, cách ly hoặc tiếp tục từng message là quyết định nghiệp vụ và adapter, không tự xuất hiện khi dùng `map`.

### 17.2. Side effect trong reactive cần thêm bảo vệ

Nếu gọi repository ngay trong `doOnNext` hoặc một mapper được retry/resubscribe, thao tác ghi có thể lặp. Dù validation ở trước, **duplicate hợp lệ** vẫn có thể tạo side effect trùng.

Với I/O blocking, tránh gọi trực tiếp trong event-loop; với I/O reactive, dùng client và operator phù hợp, kiểm soát concurrency, backpressure và tín hiệu lỗi. Validation không thay thế idempotency hoặc transaction.

## 18. Test validation bằng Java/JUnit

Test các ràng buộc trước khi thêm broker hoặc controller. Với starter Jakarta Validation, có thể tạo một `Validator` trong unit test:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.ValidatedOrder;

class OrderValidationTest {

    @Test
    void normalizesBeforeCheckingConstraints() {
        try (ValidatorFactory factory =
                    Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            OrderFunctions functions = new OrderFunctions();

            Function<OrderRequest, OrderRequest> normalize =
                    functions.normalizeOrderRequest();

            Function<OrderRequest, ValidatedOrder> validate =
                    functions.validateOrderRequest(validator);

            ValidatedOrder result = validate.apply(
                    normalize.apply(new OrderRequest(
                            " ord-42 ", " sku-7 ", 2)));

            assertEquals(
                    new ValidatedOrder("ORD-42", "SKU-7", 2),
                    result);
        }
    }

    @Test
    void rejectsMissingOrInvalidQuantity() {
        try (ValidatorFactory factory =
                    Validation.buildDefaultValidatorFactory()) {

            Function<OrderRequest, ValidatedOrder> validate =
                    new OrderFunctions()
                            .validateOrderRequest(
                                    factory.getValidator());

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", null)));

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", 0)));

            assertThrows(InvalidOrderException.class,
                    () -> validate.apply(new OrderRequest(
                            "ORD-42", "SKU-7", 101)));
        }
    }
}
~~~

Bộ test dùng provider Jakarta Validation trên classpath. Các test này chứng minh `Validator` thực sự chạy; không cần Spring Boot context để kiểm tra quy tắc DTO.

### 18.1. Kiểm tra danh sách lỗi, không dựa vào thứ tự provider

Constraint có thể được trả về theo thứ tự không xác định. Trong ví dụ Function đã `sorted()` nên kết quả ổn định hơn, nhưng lời nhắn provider có thể thay đổi theo locale.

Một test tốt có thể kiểm tra field hoặc error code dựa trên cấu trúc, thay vì so sánh nguyên văn câu thông báo. Đối với API công khai, nên định nghĩa mã lỗi ổn định.

## 19. Integration test FunctionCatalog và chặn side effect

Tạo lớp ứng dụng Spring Boot trong package `example.functions`:

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

Với `OrderFunctions`, `QuoteSinkFunctions`, `InMemoryQuoteSink` và Spring Cloud Function context có trên classpath, ta kiểm tra pipeline đã ghép theo tên:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.OrderRequest;
import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class OrderCatalogValidationTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    InMemoryQuoteSink sink;

    @Test
    void validPayloadIsNormalizedAndPriced() {
        Function<OrderRequest, Quote> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest|calculateQuote");

        assertNotNull(pipeline);

        Quote quote = pipeline.apply(
                new OrderRequest(" ord-42 ", " sku-7 ", 2));

        assertEquals(
                new Quote("ORD-42", "SKU-7", 2, 250_000L),
                quote);
    }

    @Test
    void invalidRequestDoesNotReachSaveQuote() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest"
                + "|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        assertThrows(InvalidOrderException.class,
                () -> pipeline.accept(
                    new OrderRequest("ORD-91", "SKU-7", 0)));

        assertNull(sink.find("ORD-91"));
    }

    @Test
    void repeatedValidRequestDoesNotDuplicateQuote() {
        Consumer<OrderRequest> pipeline = catalog.lookup(
                "normalizeOrderRequest|validateOrderRequest"
                + "|calculateQuote|saveQuote");

        assertNotNull(pipeline);

        OrderRequest request =
                new OrderRequest("ORD-92", "SKU-7", 2);

        pipeline.accept(request);
        pipeline.accept(request);

        assertEquals(
                new Quote("ORD-92", "SKU-7", 2, 250_000L),
                sink.find("ORD-92"));
    }
}
~~~

Các khóa test khác nhau làm ví dụ dễ đọc nhưng không thay thế chiến lược isolation khi nhiều test/context chạy song song. Kho in-memory chỉ kiểm tra hành vi trong JVM; để bảo đảm production, cần test unique constraint/transaction ở database thật.

### 19.1. Test âm phải kiểm tra cả không có side effect

Nếu test chỉ xác nhận `InvalidOrderException`, ta vẫn chưa biết một bước ghi có chạy trước khi exception phát sinh hay không. Vì vậy assertion `sink.find("ORD-91") == null` quan trọng: nó kiểm tra ranh giới validation thực sự chặn việc ghi dữ liệu sai.

## 20. Test ở ranh giới adapter

Unit test Function và integration test catalog **không thay thế** kiểm thử adapter.

| Ranh giới | Kịch bản test | Điều cần kiểm tra |
|---|---|---|
| HTTP | JSON sai cú pháp | Bị từ chối trước nghiệp vụ, status lỗi đúng |
| HTTP | `quantity=null` hoặc `0` | Có lỗi validation, không ghi |
| HTTP | Input hợp lệ với khoảng trắng | Chuẩn hóa rồi trả Quote đúng |
| Messaging | Payload không deserialize | Binder xử lý theo policy, không poison loop vô hạn |
| Messaging | DTO hợp lệ về schema nhưng sai rule | Không ghi, lỗi được phân loại |
| Messaging | Message giao lại | Idempotency, ack/retry và DLQ |
| Serverless | Event thiếu trường, event cũ | Validation chạy nhất quán |
| Reactive | Một phần tử sai giữa Flux | Tín hiệu lỗi/continuation đúng chính sách |
| Multi-instance | Cùng `orderId` từ hai worker | Storage bảo đảm uniqueness |

Với một request hợp lệ được gửi lại sau timeout, validation sẽ tiếp tục thông qua — và điều đó **đúng**. Việc ngăn xử lý trùng lúc này thuộc idempotency/transaction, không phải nhiệm vụ của Bean Validation.

## 21. Checklist khi thiết kế validation boundary

Trước khi đưa pipeline vào production, kiểm tra:

1. Mọi nguồn input chưa tin cậy có đi qua một bước validation chung hoặc cơ chế tương đương không?
2. Có phân biệt lỗi deserialize, lỗi DTO, lỗi nghiệp vụ và lỗi authorization không?
3. Constraint có xử lý trường thiếu/null, regex, độ dài và giới hạn giá trị không?
4. Có kiểm soát kích thước payload và độ phức tạp trước các phép parse/regex không?
5. Việc chuẩn hóa có được hợp đồng cho phép, và có chạy trước validation theo dự định không?
6. `Validator.validate(...)` có thực sự được gọi trong đường chạy FunctionCatalog không?
7. Phần business có dùng `ValidatedOrder` thay vì dữ liệu raw chưa kiểm tra không?
8. Consumer side effect có đặt sau validation và có kiểm tra duplicate không?
9. Dữ liệu invalid có chính sách không retry vô hạn, quan sát/đưa DLQ phù hợp không?
10. Với HTTP, mã lỗi và thông tin công bố có ổn định, không lộ dữ liệu nhạy cảm không?
11. Với message, schemaVersion, content-type và headers có được kiểm tra trên adapter thực tế không?
12. Đã có unit test, catalog integration test và adapter integration test chưa?

Validation sớm làm pipeline dễ dự đoán và giảm side effect sai, nhưng không thay thế security, transaction hoặc cơ chế hồi phục khi hạ tầng hỏng.

## 22. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| DTO có annotation nhưng dữ liệu sai vẫn qua | Không ai gọi Validator | Thêm bước validation tường minh hoặc xác nhận cơ chế @Valid của adapter |
| Input có chữ thường bị từ chối | Validate trước normalize | Xác định canonical format và chạy đúng thứ tự |
| Trường số lượng thiếu nhưng khó phân biệt | Dùng primitive `int` | Dùng `Integer` với `@NotNull` nếu cần phân biệt |
| `quantity="abc"` không tạo InvalidOrderException | Converter lỗi trước Function | Xử lý lỗi deserialize ở adapter |
| `saveQuote` chạy với dữ liệu sai | Validation không nằm trên mọi đường gọi | Đặt validation trước Consumer và test negative case |
| Broker retry mãi một message lỗi | Poison message không phân loại | Policy retry có giới hạn/DLQ/quarantine |
| Bị ghi hai lần dù validation thành công | Validation không xử lý duplicate | Idempotency key và uniqueness tại storage |
| Cùng key nhưng payload khác bị bỏ qua | Recorder không phát hiện conflict | So sánh nội dung/phiên bản và báo conflict |
| Client nhận chi tiết nội bộ trong lỗi | Expose raw exception hoặc payload | Mã lỗi ổn định, giới hạn chi tiết và log an toàn |
| Reactive lỗi xuất hiện muộn | Mapper chạy khi subscribe | Test bằng StepVerifier và error signal |

## 23. Bài tập tự luyện

**Bài 1 — Xác định ranh giới.** Với HTTP JSON chứa `quantity="abc"`, lỗi nên được phát hiện ở converter hay Bean Validation? Nếu quantity là `0` thì ở đâu?

**Bài 2 — Không tự động @Valid.** Vì sao chỉ khai báo `@NotNull` và `@Pattern` trên `OrderRequest` chưa đủ để đảm bảo `FunctionCatalog.lookup(...).apply(...)` luôn từ chối dữ liệu sai?

**Bài 3 — Thiết kế pipeline.** Sắp xếp `calculateQuote`, `normalizeOrderRequest` và `validateOrderRequest` theo thứ tự hợp lệ. Nêu hợp đồng đầu vào/đầu ra của toàn chuỗi.

**Bài 4 — Consumer và side effect.** Thêm `saveQuote: Consumer<Quote>` vào pipeline. Hợp đồng tổng thể thay đổi thế nào? Dùng phương thức nào để gọi, và vì sao không được nối Function sau Consumer?

**Bài 5 — DTO và null.** Vì sao `Integer quantity` hữu ích hơn `int quantity` khi client có thể bỏ trường quantity? Ràng buộc nào phát hiện thiếu giá trị?

**Bài 6 — Quy tắc động.** Một SKU đúng regex nhưng đã hết hàng. Bean Validation có đủ không? Hãy đề xuất nơi kiểm tra tồn kho và cách tránh race condition khi nhiều đơn cùng đặt.

**Bài 7 — HTTP so với message.** Một controller dùng `@Valid` nhưng một Kafka consumer không có validation. Rủi ro là gì? Đề xuất cách dùng chung validation.

**Bài 8 — Retry và poison message.** Nếu JSON từ broker có `orderId="BAD"` mãi mãi, retry liên tục có ích không? Hãy nêu một hướng cách ly/quan sát.

**Bài 9 — Test.** Viết một assertion bảo đảm input `quantity=0` bị từ chối và không tạo bản ghi `ORD-91` ở sink.

**Bài 10 — Reactive.** Một `Flux<OrderRequest>` chứa ba phần tử, phần tử giữa sai. Điều gì thường xảy ra khi dùng `map(validate)` mặc định? Hãy phân biệt cách xử lý riêng từng message với lỗi làm dừng cả Flux.

### Gợi ý đáp án

- **Bài 1:** Sai kiểu `"abc"` thường lỗi ở converter; `0` là giá trị đúng kiểu nhưng sai `@Min(1)`.
- **Bài 2:** Annotation là metadata; cần cơ chế gọi `Validator.validate(...)` hoặc validation integration được cấu hình rõ.
- **Bài 3:** `normalizeOrderRequest|validateOrderRequest|calculateQuote`, hợp đồng `Function<OrderRequest,Quote>`.
- **Bài 4:** Thêm `|saveQuote` tạo `Consumer<OrderRequest>` và gọi `accept(...)`; Consumer trả `void`.
- **Bài 5:** `Integer` cho phép biểu diễn null; `@NotNull` phát hiện thiếu quantity.
- **Bài 6:** Kiểm tra tồn kho ở tầng nghiệp vụ/storage, với cơ chế reservation/transaction phù hợp.
- **Bài 7:** Input qua Kafka có thể bỏ qua validation; đưa một Function validation chung trước nghiệp vụ trên mọi đường vào.
- **Bài 8:** Retry vô hạn không chữa dữ liệu sai; phân loại lỗi, quarantine/DLQ và cảnh báo vận hành.
- **Bài 9:** `assertThrows(InvalidOrderException.class, () -> pipeline.accept(invalid)); assertNull(sink.find("ORD-91"));`.
- **Bài 10:** Mapper lỗi thường phát `onError` và kết thúc Flux; muốn tiếp tục từng message phải thiết kế ranh giới lỗi/handling phù hợp.

## 24. Ghi nhớ

- **Xác thực đầu vào trước nghiệp vụ và side effect** giúp hạn chế việc ghi hoặc phát dữ liệu sai.
- Deserialize, Bean Validation, authorization và kiểm tra quy tắc nghiệp vụ là **các ranh giới khác nhau**, cần xử lý đúng trách nhiệm.
- Annotation như `@NotNull`, `@Pattern` hay `@Min` không tự chạy; trong Spring Cloud Function, cần bảo đảm có một cơ chế validation thực sự được gọi.
- Pipeline `normalize → validate → calculate → consume` làm rõ trạng thái dữ liệu và giữ Consumer có side effect ở cuối.
- `FunctionCatalog` và `spring.cloud.function.definition` giúp ghép/chọn hàm, không tự cung cấp kiểm soát security, retry, DLQ, transaction hoặc idempotency.
- Dữ liệu sai cố định thường không nên retry vô hạn. Dữ liệu hợp lệ bị gửi lại cần cơ chế chống trùng ở storage.
- Với HTTP, sự kiện, serverless và reactive, phải xác minh input/conversion, lỗi, headers, retry và tính an toàn của side effect trong **adapter thực tế**.
