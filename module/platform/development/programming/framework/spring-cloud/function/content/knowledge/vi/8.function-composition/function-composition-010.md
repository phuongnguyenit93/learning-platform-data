# Tách kiểm tra, biến đổi và nghiệp vụ thành các hàm dùng lại

## 1. Mục tiêu bài học

Một dịch vụ nhận đơn hàng có thể phải chuẩn hóa dữ liệu đầu vào, phân tích cú pháp, xác thực quy tắc, tính giá và tạo kết quả. Nếu gom mọi bước vào một phương thức lớn, thay đổi một quy tắc dễ ảnh hưởng các phần còn lại, còn kiểm thử thường phải chuẩn bị toàn bộ hệ thống.

Spring Cloud Function hướng tới việc **biểu diễn logic nghiệp vụ bằng các thành phần nhỏ có thể tái sử dụng**, đặc biệt là `Supplier<T>`, `Function<T,R>` và `Consumer<T>`. Mỗi thành phần có hợp đồng rõ ràng, có thể đăng ký vào `FunctionCatalog` và ghép thành một pipeline. Logic không phải biết được gọi qua HTTP, sự kiện hay môi trường serverless; tầng adapter đảm nhiệm việc kết nối với các giao thức đó.

Chủ đề của bài thuộc chương **Ghép hàm**: **tách kiểm tra, biến đổi và nghiệp vụ thành các hàm dùng lại**.

Sau bài học, bạn có thể:

- Nhận diện các loại trách nhiệm nên tách khỏi một phương thức xử lý lớn.
- Thiết kế hợp đồng dữ liệu rõ ràng tại ranh giới giữa các hàm.
- Khai báo và tái sử dụng các `Function` bean trong Spring.
- Ghép theo tên bằng `FunctionCatalog.lookup(...)` và chọn pipeline qua `spring.cloud.function.definition`.
- Đặt `Consumer` có tác dụng phụ ở vị trí thích hợp, không trộn việc ghi dữ liệu vào mọi bước biến đổi.
- Viết unit test cho từng quy tắc và integration test cho toàn pipeline.
- Áp dụng cùng các hàm ở nhiều luồng HTTP, messaging hoặc serverless khi adapter phù hợp được cấu hình.

## 2. Khi mọi thứ nằm trong một hàm lớn

Xét một hàm nhận chuỗi đơn hàng `"sku-42,2"`, chuẩn hóa, kiểm tra, tính giá rồi trả chuỗi kết quả:

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> handleOrder = raw -> {
    String input = raw.trim().toUpperCase(Locale.ROOT);
    String[] parts = input.split(",", -1);

    if (parts.length != 2) {
        throw new IllegalArgumentException("Sai dinh dang");
    }

    String sku = parts[0].trim();
    int quantity = Integer.parseInt(parts[1].trim());

    if (!sku.matches("SKU-[0-9]+") || quantity <= 0) {
        throw new IllegalArgumentException("Don hang khong hop le");
    }

    long total = Math.multiplyExact(quantity, 125_000L);

    return sku + " x " + quantity + " = " + total + " VND";
};
~~~

Hàm này không sai chỉ vì dài, nhưng nó đồng thời làm nhiều việc:

1. Chuẩn hóa chuỗi.
2. Phân tích cú pháp input.
3. Kiểm tra quy tắc nghiệp vụ.
4. Tính tiền.
5. Định dạng kết quả.

Nếu một chức năng khác chỉ muốn **tính số tiền dưới dạng số**, nó vẫn phải đi qua logic tạo chuỗi. Nếu cần đổi cách định dạng, một test liên quan đến định giá có thể cũng bị ảnh hưởng. Nếu thêm bước ghi sự kiện ngay bên trong, việc thử logic thuần lại phụ thuộc vào broker hoặc database.

Cách cải thiện là chia thành những hàm nhỏ, có ý nghĩa và ranh giới dữ liệu tường minh.

## 3. Ba loại trách nhiệm cần phân biệt

Trong thực tế, “kiểm tra”, “biến đổi” và “nghiệp vụ” có thể cùng xuất hiện trong một service, nhưng chúng trả lời các câu hỏi khác nhau.

| Nhóm trách nhiệm | Câu hỏi chính | Ví dụ | Hợp đồng điển hình |
|---|---|---|---|
| Chuẩn hóa/biến đổi | Dữ liệu có hình thức và cấu trúc nào? | Trim, viết hoa SKU, parse CSV | `String → OrderDraft` |
| Kiểm tra/validation | Dữ liệu này có thỏa điều kiện không? | SKU đúng mẫu, số lượng dương | `OrderDraft → ValidatedOrder` |
| Logic nghiệp vụ | Với dữ liệu hợp lệ, cần tính hoặc quyết định gì? | Tính báo giá, chiết khấu, thuế | `ValidatedOrder → Quote` |
| Biểu diễn kết quả | Giao diện cần nhận định dạng gì? | `Quote → String` hoặc JSON | `Quote → String` |
| Tác dụng phụ | Cần làm gì với kết quả? | Lưu, phát thông điệp, audit | `Consumer<Quote>` |

Đó là cách phân loại để thiết kế; không phải quy định rằng mọi bước đều phải có một bean riêng. Chỉ tách khi ranh giới **có tên gọi rõ, có giá trị tái sử dụng hoặc kiểm thử độc lập**. Tránh chia thành quá nhiều hàm không mang ý nghĩa chỉ để tăng số lượng bean.

### 3.1. Validation không nhất thiết phải trả Boolean

Một hàm `Function<OrderDraft, Boolean>` có thể kiểm tra tính hợp lệ nhưng trả về Boolean sẽ làm mất đối tượng đơn hàng tại điểm nối kế tiếp:

~~~text
OrderDraft ──validate:Boolean──> Boolean
                                   |
                                   X
                             calculateQuote cần OrderDraft
~~~

Khi cần tiếp tục pipeline, có thể viết:

~~~text
OrderDraft ──validate──> ValidatedOrder ──calculateQuote──> Quote
~~~

Với mô hình này, bước validation **trả đối tượng đã qua kiểm tra** hoặc ném lỗi nếu không hợp lệ. Kiểu `ValidatedOrder` giúp thể hiện ranh giới trạng thái dữ liệu.

Một thiết kế khác là trả `ValidationResult<OrderDraft>` có thông tin lỗi để bước sau quyết định xử lý. Chọn cách nào tùy hợp đồng lỗi của ứng dụng, không mặc định mọi bài toán phải dùng exception.

## 4. Thiết kế pipeline trước khi viết code

Với đơn hàng dạng text, ta thiết kế:

~~~text
Input String: " sku-42, 2 "
              |
              v
normalizeInput                  Function<String,String>
              |
              v
"SKU-42, 2"
              |
              v
parseOrder                      Function<String,OrderDraft>
              |
              v
OrderDraft("SKU-42", 2)
              |
              v
validateOrder                   Function<OrderDraft,ValidatedOrder>
              |
              v
ValidatedOrder("SKU-42", 2)
              |
              v
calculateQuote                  Function<ValidatedOrder,Quote>
              |
              v
Quote("SKU-42", 2, 250000)
              |
              +----------------------------+
              |                            |
              v                            v
formatQuote                    auditQuote
Function<Quote,String>         Consumer<Quote>
              |                            |
              v                            v
"SKU-42 x 2 = 250000 VND"      Ghi nhận kết quả
~~~

Phần chung **normalize → parse → validate → calculate** có thể tạo một `Function<String, Quote>`. Từ đó ta chọn **nhánh trả văn bản** hoặc **nhánh ghi nhận** mà không viết lại các bước lõi.

### 4.1. Bảng hợp đồng dữ liệu

| Bước | Nhận | Trả | Ghi chú |
|---|---|---|---|
| `normalizeInput` | `String` | `String` | Chuẩn hóa dấu cách, chữ hoa |
| `parseOrder` | `String` | `OrderDraft` | Kiểm tra cú pháp cơ bản |
| `validateOrder` | `OrderDraft` | `ValidatedOrder` | Kiểm tra quy tắc nghiệp vụ |
| `calculateQuote` | `ValidatedOrder` | `Quote` | Tính tổng tiền |
| `formatQuote` | `Quote` | `String` | Chuyển kết quả thành text |
| `auditQuote` | `Quote` | `void` | Tác dụng phụ |

Cần xem **kiểu đầu ra của từng bước**, không chỉ đầu vào/đầu ra toàn pipeline. Hai hàm cùng dùng `String` vẫn có thể không phù hợp về ý nghĩa, chẳng hạn một bên tạo customer ID còn bên kia tưởng đó là email.

## 5. Xây dựng các kiểu dữ liệu có ý nghĩa

Ví dụ dùng Java 17 với `record`:

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderDraft(String sku, int quantity) {}

    public record ValidatedOrder(String sku, int quantity) {}

    public record Quote(String sku, int quantity, long totalVnd) {}
}
~~~

Tại sao dùng ba record mà không truyền cùng một `Map<String, Object>`?

- `OrderDraft` biểu diễn dữ liệu đã parse nhưng **chưa bảo đảm hợp lệ theo nghiệp vụ**.
- `ValidatedOrder` biểu diễn dữ liệu đã vượt qua bước kiểm tra.
- `Quote` là kết quả tính toán, có thêm tổng tiền.

Mỗi record tạo một hợp đồng tĩnh. Nếu vô tình nối `Function<OrderDraft, Quote>` sau một hàm trả `String`, Java generic giúp phát hiện lỗi khi ghép trực tiếp trong code.

Tên kiểu không tự bảo đảm dữ liệu an toàn nếu caller có thể tùy ý tạo `ValidatedOrder`. Trong bài, chỉ bước `validateOrder` được kỳ vọng tạo kiểu đó trong pipeline. Ở ứng dụng thực, có thể kiểm soát bất biến bằng constructor/factory của domain nếu cần.

## 6. Khai báo các hàm tái sử dụng trong Spring

Từng hàm nghiệp vụ được đăng ký như một bean riêng. Ví dụ sau đủ để chạy khi được đặt trong Spring Boot application có dependency Spring Cloud Function thích hợp.

~~~java
package example.functions;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

@Configuration
public class OrderFunctions {

    @Bean
    public Function<String, String> normalizeInput() {
        return raw -> {
            if (raw == null) {
                throw new IllegalArgumentException(
                        "Du lieu dau vao khong duoc null");
            }
            return raw.trim().toUpperCase(Locale.ROOT);
        };
    }

    @Bean
    public Function<String, OrderDraft> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);

            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Can dinh dang SKU,quantity");
            }

            String sku = parts[0].trim();
            int quantity;
            try {
                quantity = Integer.parseInt(parts[1].trim());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Quantity phai la so nguyen", ex);
            }

            return new OrderDraft(sku, quantity);
        };
    }

    @Bean
    public Function<OrderDraft, ValidatedOrder> validateOrder() {
        return draft -> {
            if (draft == null
                    || draft.sku() == null
                    || !draft.sku().matches("SKU-[0-9]+")
                    || draft.quantity() <= 0
                    || draft.quantity() > 100) {
                throw new IllegalArgumentException(
                        "SKU hoac quantity khong hop le");
            }

            return new ValidatedOrder(
                    draft.sku(), draft.quantity());
        };
    }

    @Bean
    public Function<ValidatedOrder, Quote> calculateQuote() {
        return order -> {
            long unitPriceVnd = 125_000L;
            long totalVnd = Math.multiplyExact(
                    order.quantity(), unitPriceVnd);

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

**Quy tắc của ví dụ:** SKU có dạng `SKU-<số>`; số lượng nằm trong khoảng từ 1 đến 100; đơn giá cố định 125.000 VND. Đây là mô hình đơn giản phục vụ bài học, không phải hệ thống báo giá hoàn chỉnh với thuế, khuyến mại hoặc tồn kho.

### 6.1. Mỗi bean có tên và nhiệm vụ rõ ràng

Khi dùng `@Bean` mà không chỉ định tên, Spring thường đặt tên bean trùng với tên phương thức. Các tên là:

~~~text
normalizeInput
parseOrder
validateOrder
calculateQuote
formatQuote
~~~

`FunctionCatalog` có thể tra cứu chúng qua tên. Nếu dùng `@Bean("myName")`, tên đăng ký là `myName` chứ không phải mặc định tên method.

Tách theo tên cho phép chọn các tổ hợp khác nhau bằng cấu hình. Tuy nhiên, code nghiệp vụ không nên tùy ý tra cứu và gọi mọi tên từ input không đáng tin cậy; nếu cần chọn pipeline động, hãy kiểm soát danh sách được phép.

### 6.2. Biên giới của từng bước

**`normalizeInput`** nên giải quyết vấn đề hình thức dữ liệu, không tính tiền hoặc lưu đơn.

**`parseOrder`** nhận cú pháp đúng và tạo dữ liệu có cấu trúc. Nó vẫn có thể ném lỗi khi không thể parse số lượng, nhưng không cần biết giá, tồn kho hay quy tắc khuyến mại.

**`validateOrder`** kiểm tra các bất biến nghiệp vụ. Nó không truy vấn database trong ví dụ này và không thay đổi dữ liệu bên ngoài.

**`calculateQuote`** chỉ nhận đầu vào đã xác thực và tính `Quote`; không có trách nhiệm dựng HTTP response.

**`formatQuote`** biến kết quả domain thành chuỗi. Nếu bên nhận muốn JSON hoặc Message, không cần thay đổi phép tính giá.

## 7. Ghép bằng Java thuần: trình biên dịch kiểm tra generic

Không cần `FunctionCatalog` để hiểu nguyên lý composition. Trong Java, có thể dùng `andThen`:

~~~java
import java.util.function.Function;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

OrderFunctions config = new OrderFunctions();

Function<String, String> normalize = config.normalizeInput();
Function<String, OrderDraft> parse = config.parseOrder();
Function<OrderDraft, ValidatedOrder> validate =
        config.validateOrder();
Function<ValidatedOrder, Quote> price =
        config.calculateQuote();
Function<Quote, String> format = config.formatQuote();

Function<String, String> fullPipeline =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price)
                .andThen(format);

System.out.println(fullPipeline.apply(" sku-42, 2 "));
// SKU-42 x 2 = 250000 VND
~~~

Đoạn trên minh họa ghép Java thuần bằng cách tạo instance `OrderFunctions` để lấy các lambda stateless. Trong ứng dụng Spring, không cần gọi trực tiếp các method `@Bean` để tra cứu function; `FunctionCatalog` hoặc dependency injection sẽ dùng bean do Spring quản lý.

### 7.1. Chọn các đoạn ghép có thể tái sử dụng

Không nhất thiết lần nào cũng chạy toàn bộ pipeline:

~~~java
Function<String, ValidatedOrder> parseValidated =
        normalize.andThen(parse).andThen(validate);

Function<String, Quote> quoteOrder =
        parseValidated.andThen(price);

Function<String, String> quoteAsText =
        quoteOrder.andThen(format);
~~~

Ba kết quả này có mục tiêu khác nhau:

| Pipeline | Đầu vào | Đầu ra | Trường hợp sử dụng |
|---|---|---|---|
| `parseValidated` | `String` | `ValidatedOrder` | Kiểm tra và chuẩn hóa |
| `quoteOrder` | `String` | `Quote` | Tính giá và trả object |
| `quoteAsText` | `String` | `String` | Tạo kết quả văn bản |

Một logic chuẩn hóa được dùng lại trong cả ba mà không phải viết ba bản sao.

### 7.2. Cú pháp compose đổi cách đọc, không đổi hợp đồng

`andThen` đọc theo thứ tự thực thi:

~~~java
normalize.andThen(parse).andThen(validate)
~~~

Còn `compose` đặt Function chạy trước trong đối số:

~~~java
Function<String, ValidatedOrder> same =
        validate.compose(parse).compose(normalize);
~~~

Hai cách đều tạo thứ tự `normalize → parse → validate`. Khi thiết kế một chuỗi nhiều bước, `andThen` hoặc tên ghép `A|B|C` thường dễ đọc theo luồng dữ liệu hơn.

## 8. Ghép theo tên với FunctionCatalog.lookup

Spring Cloud Function cho phép tra cứu một function hoặc một biểu thức ghép từ các bean đã đăng ký.

Ví dụ service:

~~~java
package example.functions;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Service;

import example.functions.OrderModels.Quote;

@Service
public class QuoteService {

    private final FunctionCatalog catalog;

    public QuoteService(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public Quote quote(String rawOrder) {
        Function<String, Quote> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay quote pipeline");
        }

        return pipeline.apply(rawOrder);
    }

    public String quoteAsText(String rawOrder) {
        Function<String, String> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder"
                    + "|calculateQuote|formatQuote");

        if (pipeline == null) {
            throw new IllegalStateException(
                    "Khong tim thay text pipeline");
        }

        return pipeline.apply(rawOrder);
    }
}
~~~

Cần một Spring context có `OrderFunctions` và Spring Cloud Function context phù hợp để `FunctionCatalog` được inject.

Dấu `|` biểu diễn pipeline **từ trái sang phải**:

~~~text
normalizeInput → parseOrder → validateOrder
               → calculateQuote → formatQuote
~~~

Chữ ký đầu ra của `lookup` trong code Java phải phù hợp với **hợp đồng tổng thể của chuỗi tên**, không chỉ generic mà người viết muốn. Một tên sai hoặc cặp kiểu không phù hợp có thể chỉ bộc lộ lỗi khi tra cứu hoặc thực thi ở runtime.

### 8.1. Vì sao vẫn cần kiểm thử catalog?

Java compiler có thể kiểm tra `normalize.andThen(parse)` vì hai biến có generic cụ thể. Với `catalog.lookup("normalizeInput|parseOrder")`, tên các bước là chuỗi ký tự; compiler không đọc được tên bean và kiểu thực của từng function qua chuỗi này.

Hãy kiểm tra:

- Bean đã được đăng ký đúng tên chưa?
- Thứ tự ghép có phù hợp không?
- Đầu ra từng bước có kết nối được với đầu vào bước sau không?
- Payload thực tế có đúng loại dữ liệu mà Java code giả định không?
- Lỗi có xảy ra ở bước nào và tác dụng phụ đã chạy chưa?

## 9. Chọn pipeline qua spring.cloud.function.definition

Khi muốn adapter sử dụng một logic cụ thể, ta có thể đặt trong `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote"
~~~

Hoặc `application.properties`:

~~~properties
spring.cloud.function.definition=normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
~~~

Giá trị cấu hình chọn **tên/tổ hợp hàm** mà phần tích hợp sẽ dùng, không phải định nghĩa thuật toán mới.

| Cách gọi | Vai trò |
|---|---|
| `FunctionCatalog.lookup(...)` | Code Java tra cứu function/pipeline theo tên |
| `spring.cloud.function.definition` | Chọn pipeline cho lớp tích hợp |
| HTTP adapter | Ánh xạ request/response với logic được công bố |
| Messaging adapter | Ánh xạ message/binding với logic |
| Serverless adapter | Ánh xạ event/handler với logic |

Chỉ đặt property `definition` **chưa tự cấu hình HTTP endpoint, topic broker, message converter hoặc serverless trigger**. Các adapter có quy ước/cấu hình riêng và có thể có giới hạn đối với những kiểu function được công bố.

### 9.1. Trả object thay vì text

Nếu bên nhận cần dữ liệu domain để serialize thành JSON, ta có thể chọn:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeInput|parseOrder|validateOrder|calculateQuote"
~~~

Pipeline khi đó có hợp đồng `Function<String, Quote>`. Đó là một ví dụ tái sử dụng logic tính giá mà không bắt buộc đi qua bước `formatQuote`.

Không nên giả định adapter sẽ tự giữ nguyên mọi header hoặc tự chuyển mọi POJO thành JSON đúng mong đợi. Kiểm thử serialization, content-type và thông tin kiểu là phần quan trọng của integration test.

## 10. Tách tác dụng phụ thành Consumer riêng

Tính giá thuần và việc ghi nhận báo giá là hai trách nhiệm khác nhau.

Nếu muốn audit một báo giá, ta có thể khai báo một Consumer nhận `Quote`, được đặt ở **cuối** một pipeline khác.

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.Quote;

@Configuration
public class QuoteAuditFunctions {

    public static final class QuoteLedger {
        private final Queue<Quote> entries =
                new ConcurrentLinkedQueue<>();

        public void append(Quote quote) {
            entries.add(quote);
        }

        public List<Quote> snapshot() {
            return List.copyOf(entries);
        }
    }

    @Bean
    public QuoteLedger quoteLedger() {
        return new QuoteLedger();
    }

    @Bean
    public Consumer<Quote> auditQuote(QuoteLedger ledger) {
        return ledger::append;
    }
}
~~~

`QuoteLedger` chỉ là nơi lưu tạm trong bộ nhớ để minh họa, không phải database, không có transaction hoặc chống trùng. Nó là một bean phụ thuộc của Consumer; chính `auditQuote` mới là function dùng trong composition.

### 10.1. Nhánh trả text và nhánh có side effect

Hai pipeline dùng chung phần tính giá:

~~~text
normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
        ⇒ Function<String,String>

normalizeInput|parseOrder|validateOrder|calculateQuote|auditQuote
        ⇒ Consumer<String>
~~~

Nhánh thứ hai kết thúc bằng Consumer nên được gọi qua `accept(...)`:

~~~java
import java.util.function.Consumer;

Consumer<String> auditPipeline =
        catalog.lookup(
            "normalizeInput|parseOrder|validateOrder"
            + "|calculateQuote|auditQuote");

if (auditPipeline == null) {
    throw new IllegalStateException("Thieu audit pipeline");
}

auditPipeline.accept("sku-42,2");
~~~

Không gọi `apply(...)` trên Consumer: `Consumer.accept` có kết quả `void`.

### 10.2. Tại sao không đặt Consumer vào giữa rồi tiếp tục định dạng?

Không nên kỳ vọng chuỗi:

~~~text
calculateQuote|auditQuote|formatQuote
~~~

tự truyền `Quote` từ `auditQuote` sang `formatQuote`: `auditQuote` trả `void` nên không có output cho bước sau.

Nếu nghiệp vụ bắt buộc vừa audit vừa trả văn bản, hãy thiết kế một orchestration tường minh hoặc Function có hợp đồng trả kết quả rõ ràng, đồng thời tính đến transaction và cách xử lý lỗi. Đừng giả định Consumer sinh ra dữ liệu cho Function tiếp theo.

## 11. Kiểm tra cú pháp và kiểm tra nghiệp vụ là hai ranh giới khác nhau

Trong ví dụ:

~~~text
String
  |
parseOrder
  |   Lỗi nếu thiếu dấu phẩy hoặc số lượng không parse được
  v
OrderDraft
  |
validateOrder
  |   Lỗi nếu SKU sai hoặc số lượng ngoài khoảng 1..100
  v
ValidatedOrder
~~~

Có hai loại lỗi khác nhau.

**Lỗi cấu trúc:** `"SKU-42"` thiếu trường số lượng, hoặc `"SKU-42,abc"` không parse được thành số. Bước `parseOrder` chịu trách nhiệm phát hiện.

**Lỗi quy tắc:** `"SKU-42,0"` parse được nhưng số lượng không hợp lệ. Bước `validateOrder` chịu trách nhiệm phát hiện.

Tách hai nhóm làm thông báo lỗi và test cụ thể hơn. Sau này, quy tắc “số lượng tối đa 100” đổi thành 200 thì chỉ cần sửa validation, không cần sửa parse hoặc định dạng.

### 11.1. Không phải lúc nào exception cũng là mô hình tối ưu

Ví dụ đơn giản dùng `IllegalArgumentException` để giữ bài học ngắn gọn. Nếu ứng dụng cần trả nhiều lỗi cùng lúc cho client, có thể dùng một kiểu kết quả:

~~~java
record ValidationError(String field, String message) {}
record ValidationResult<T>(
        T value,
        List<ValidationError> errors) {}
~~~

Đoạn trên là gợi ý thiết kế: để sử dụng thực tế cần import `java.util.List` và xây dựng quy tắc kiểm tra bất biến của `ValidationResult`.

Khi dùng `ValidationResult<T>`, bước tiếp theo phải biết cách xử lý trạng thái lỗi thay vì nhận trực tiếp `T`. Không thể nối `Function<OrderDraft, ValidationResult<OrderDraft>>` vào `Function<OrderDraft, Quote>` mà không có một bước trung gian thích hợp.

## 12. Đặt hàm dùng lại ở ranh giới hợp lý

Việc tách nhỏ không chỉ để viết được `A|B|C`. Nên có các tiêu chí:

1. **Một trách nhiệm mô tả được bằng tên.** `normalizeInput` rõ hơn `processStep1`.
2. **Hợp đồng kiểu tường minh.** `ValidatedOrder` giúp phân biệt dữ liệu trước/sau validation.
3. **Logic dùng lại được.** `calculateQuote` không phụ thuộc vào text HTTP request hay Kafka header.
4. **Kiểm thử độc lập.** Có thể thử `validateOrder` không cần database.
5. **Chi phí hợp lý.** Không tạo mười bean chỉ để bọc mười thao tác `String.trim` vô nghĩa khi chúng không có tên gọi nghiệp vụ.
6. **Tác dụng phụ rõ nơi thực hiện.** Phần tính toán nên tách khỏi nơi lưu/phát thông điệp khi có thể.
7. **Lỗi và observability rõ.** Mỗi bước có thể báo nguyên nhân thất bại mà không làm lẫn ranh giới adapter.

### 12.1. Hàm thuần và hàm có tác dụng phụ

Một hàm được gọi là *thuần* khi cùng input cho cùng output và không gây tác dụng phụ quan sát được. `calculateQuote` với đơn giá cố định trong bài gần với mô hình hàm thuần. Nhưng nếu hàm truy vấn giá thay đổi từ database, nó không còn thuần theo nghĩa đó, dù chữ ký Java vẫn là `Function<ValidatedOrder, Quote>`.

Do vậy, **chữ ký Function không tự bảo đảm tính thuần**. Hãy phân biệt kiểu giao diện Java với hành vi thật của implementation. Khi cần I/O, thiết kế dependency và cơ chế lỗi rõ ràng.

### 12.2. Không đưa chi tiết transport vào core

Tránh để `calculateQuote` phụ thuộc trực tiếp vào `HttpServletRequest`, `MessageHeaders`, tên topic hoặc một event AWS cụ thể. Các chi tiết đó nên được ánh xạ tại adapter để cùng phép tính dùng lại ở nhiều ngữ cảnh.

Ví dụ, một controller có thể chuyển HTTP body thành `String`, còn consumer message có thể lấy payload từ `Message<String>`. Cả hai đều có thể gọi một pipeline nghiệp vụ nhận `String` sau khi conversion được kiểm tra phù hợp.

## 13. Kết nối với Supplier và các nguồn dữ liệu

Có lúc ứng dụng không nhận input từ request mà **chủ động lấy một đơn hàng**. Khi đó, có thể dùng `Supplier<String>` làm nguồn cho pipeline:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

Supplier<String> pendingOrder =
        () -> "sku-42,2";

Function<String, String> quoteAsText =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price)
                .andThen(format);

Supplier<String> quoteSource =
        () -> quoteAsText.apply(pendingOrder.get());

System.out.println(quoteSource.get());
// SKU-42 x 2 = 250000 VND
~~~

Đây là ví dụ Java thuần ghép `Supplier<String>` với `Function<String,String>`. Trong Spring Cloud Function, khi các bean tương ứng được đăng ký và composition được hỗ trợ, biểu thức theo tên có thể là:

~~~text
pendingOrder|normalizeInput|parseOrder|validateOrder|calculateQuote|formatQuote
~~~

Hợp đồng tổng thể khi đó là một `Supplier<String>`. Phải kiểm tra trên phiên bản framework và adapter đang dùng, nhất là cách kích hoạt nguồn, lịch poll hoặc subscription.

### 13.1. Nếu kết thúc bằng Consumer?

Nếu nguồn `pendingOrder` được ghép tiếp tới `auditQuote` (sau các bước tạo `Quote`), toàn chuỗi có hành vi **`Runnable`**: không nhận input và không trả output.

~~~text
Supplier<String> → Function<String,Quote> → Consumer<Quote>
                                 ⇒ Runnable
~~~

Không nên mặc định mọi adapter sẽ tự lên lịch chạy hoặc tự bind một Runnable vào broker. Trong Java, cần lời gọi `run()`; trong hệ thống thực, cần cơ chế kích hoạt phù hợp.

## 14. Tái sử dụng giữa HTTP, sự kiện và serverless

Phần lõi của bài chỉ dùng các kiểu `String`, `OrderDraft`, `ValidatedOrder`, `Quote`. Vì vậy, cùng logic có thể được đặt sau nhiều adapter:

~~~text
HTTP Request ──────┐
                   │
Kafka/Event ───────┼─> Adapter / deserialize
                   │         |
Serverless Event ──┘         v
                        normalizeInput
                              |
                              v
                          parseOrder
                              |
                              v
                         validateOrder
                              |
                              v
                        calculateQuote
                              |
                +-------------+-------------+
                |                           |
                v                           v
           formatQuote                 auditQuote
                |                           |
                v                           v
        HTTP response / text       DB / event / audit
~~~

Sơ đồ là mô hình kiến trúc. Không có nghĩa chỉ cần cùng property `definition` là mọi adapter đồng thời hoạt động mà không cần cấu hình.

| Môi trường | Logic dùng lại | Phần adapter phải xử lý |
|---|---|---|
| HTTP | `Function<String,Quote>` hoặc `Function<String,String>` | Route, request body, status code, JSON/text serialization |
| Sự kiện | Các Function lõi và Consumer cuối | Input/output binding, content-type, headers, retry/ack |
| Serverless | Function tương ứng với kiểu event | Handler, trigger, mapping payload và response |
| Java nội bộ | FunctionCatalog hoặc bean được inject | Gọi `apply`/`accept` và xử lý ngoại lệ |

### 14.1. Không để conversion che lỗi hợp đồng

Một adapter có thể hỗ trợ chuyển đổi `Message<?>`, JSON hay payload về POJO. Nhưng không nên phụ thuộc vào việc chuyển đổi tự động để sửa một chuỗi ghép sai kiểu.

Ví dụ, `Function<OrderDraft,ValidatedOrder>` không thể được coi là `Function<Quote,ValidatedOrder>` chỉ vì cả hai là object có field giống nhau. Khi đổi transport, hãy kiểm tra ranh giới convert một cách chủ động.

### 14.2. Xử lý lỗi ngoài cùng

Trong Java, bước `parseOrder` có thể ném `IllegalArgumentException`. HTTP adapter có thể ánh xạ thành mã lỗi 4xx theo xử lý của ứng dụng; message adapter có thể retry hoặc đưa vào dead-letter; serverless adapter có thể báo lỗi invocation.

**Composition không tự quyết định chính sách xử lý lỗi của transport.** Core phải trả lỗi rõ và có hợp đồng nhất quán, còn adapter ánh xạ chúng vào cơ chế giao thức phù hợp.

## 15. Tái sử dụng từng bước với dữ liệu reactive

Nếu pipeline mới nhận `Flux<String>` thay vì từng `String`, không cần viết lại mọi quy tắc nghiệp vụ. Có thể nâng một `Function<String,Quote>` thành xử lý theo từng phần tử:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<String, Quote> quoteOne =
        normalize
                .andThen(parse)
                .andThen(validate)
                .andThen(price);

Function<Flux<String>, Flux<Quote>> quoteStream =
        flux -> flux.map(quoteOne);
~~~

Ở đây, `Quote` là `OrderModels.Quote` đã import vào ngữ cảnh code. `quoteOne` là hàm imperative trên một đơn hàng; `quoteStream` chỉ áp dụng nó trên từng phần tử.

Không nên nối trực tiếp `Function<String,Quote>` vào `Function<Flux<Quote>,Flux<String>>` bằng Java `andThen`: `Quote` khác `Flux<Quote>`. Bridge `map` tạo hợp đồng reactive tường minh.

### 15.1. Lỗi reactive và subscription

`Flux.map` thường chạy mapper khi có subscription. Nếu `quoteOne` ném lỗi cho một phần tử, Reactor chuyển lỗi mapper thành tín hiệu `onError`, và luồng thường kết thúc nếu không có xử lý lỗi phù hợp. Điều này khác việc `quoteOne.apply(raw)` ném ngoại lệ trực tiếp trong Java đồng bộ.

Không tùy tiện dùng `block()` trên event-loop. Nếu bước nghiệp vụ chứa I/O blocking, đưa nó vào `map` không biến I/O thành non-blocking; cần thiết kế scheduler hoặc sử dụng client reactive phù hợp.

Bài này chủ yếu nói về phân tách logic. Với chương trình reactive thật, cũng cần quan tâm đến thứ tự phần tử, backpressure, concurrency và chính sách lỗi từng phần tử.

## 16. Kiểm thử độc lập từng hàm

Một lợi ích lớn của thiết kế này là có thể kiểm thử quy tắc mà không cần khởi động Spring hoặc kết nối bên ngoài.

### 16.1. Unit test chuẩn hóa và parse

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;

class OrderFunctionsUnitTest {

    private final OrderFunctions functions =
            new OrderFunctions();

    @Test
    void normalizeAndParseProduceDraft() {
        Function<String, String> normalize =
                functions.normalizeInput();

        Function<String, OrderDraft> parse =
                functions.parseOrder();

        String value = normalize.apply(" sku-42, 2 ");

        assertEquals("SKU-42, 2", value);
        assertEquals(
                new OrderDraft("SKU-42", 2),
                parse.apply(value));
    }

    @Test
    void parserRejectsMissingOrNonNumericQuantity() {
        Function<String, OrderDraft> parse =
                functions.parseOrder();

        assertThrows(IllegalArgumentException.class,
                () -> parse.apply("SKU-42"));

        assertThrows(IllegalArgumentException.class,
                () -> parse.apply("SKU-42,abc"));
    }
}
~~~

Test không cần context, database hoặc broker. Khi quy tắc parse thay đổi, test tập trung vào chính bước đó.

### 16.2. Unit test validation riêng

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.OrderDraft;
import example.functions.OrderModels.ValidatedOrder;

class OrderValidationTest {

    private final Function<OrderDraft, ValidatedOrder> validate =
            new OrderFunctions().validateOrder();

    @Test
    void acceptsValidOrder() {
        assertEquals(
                new ValidatedOrder("SKU-42", 2),
                validate.apply(new OrderDraft("SKU-42", 2)));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(new OrderDraft("SKU-42", 0)));

        assertThrows(IllegalArgumentException.class,
                () -> validate.apply(new OrderDraft("SKU-42", 101)));
    }
}
~~~

Không cần kiểm tra phép tính giá để biết bước validation có đúng giới hạn 1..100 hay không.

### 16.3. Unit test tính giá riêng

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

import example.functions.OrderModels.ValidatedOrder;
import example.functions.OrderModels.Quote;

class QuoteCalculationTest {

    @Test
    void calculatesTotalFromValidatedOrder() {
        Function<ValidatedOrder, Quote> price =
                new OrderFunctions().calculateQuote();

        Quote actual = price.apply(
                new ValidatedOrder("SKU-42", 2));

        assertEquals(
                new Quote("SKU-42", 2, 250_000L),
                actual);
    }
}
~~~

Nhờ có kiểu `ValidatedOrder`, test tập trung vào tính toán với dữ liệu được xem là hợp lệ, thay vì lặp toàn bộ kiểm tra chuỗi và cú pháp.

## 17. Kiểm thử composition trong Spring Cloud Function

Unit test từng bước không đảm bảo rằng tên bean, thứ tự ghép và cấu hình Spring đã đúng. Để kiểm thử `FunctionCatalog`, cần một Spring application context có các bean tương ứng.

### 17.1. Lớp ứng dụng ví dụ

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

Đặt `OrderApplication` cùng package với `OrderFunctions`, `QuoteAuditFunctions` và `QuoteService` để có thể component scan mặc định, đồng thời khai báo dependency Spring Boot/Spring Cloud Function phù hợp.

### 17.2. Integration test tra cứu và thực thi

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class OrderPipelineCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void composesReusableStepsIntoQuote() {
        Function<String, Quote> quoteOrder =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        assertNotNull(quoteOrder);

        assertEquals(
                new Quote("SKU-42", 2, 250_000L),
                quoteOrder.apply(" sku-42, 2 "));
    }

    @Test
    void rejectsInvalidOrderBeforePricing() {
        Function<String, Quote> quoteOrder =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder|calculateQuote");

        assertNotNull(quoteOrder);

        assertThrows(IllegalArgumentException.class,
                () -> quoteOrder.apply("sku-42,0"));
    }
}
~~~

Khi thay `FunctionCatalog.lookup(...)` vào code Java, tên function là chuỗi được phân giải ở runtime. Integration test giúp phát hiện việc đổi tên method `@Bean`, thiếu bean, ghép sai thứ tự hoặc xử lý kiểu dữ liệu không như dự kiến.

### 17.3. Kiểm thử nhánh Consumer có side effect

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import example.functions.OrderModels.Quote;

@SpringBootTest(classes = OrderApplication.class)
class QuoteAuditCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    QuoteAuditFunctions.QuoteLedger ledger;

    @Test
    void auditReceivesCalculatedQuote() {
        Consumer<String> pipeline =
                catalog.lookup(
                    "normalizeInput|parseOrder|validateOrder"
                    + "|calculateQuote|auditQuote");

        assertNotNull(pipeline);
        pipeline.accept(" sku-42,2 ");

        assertTrue(ledger.snapshot().contains(
                new Quote("SKU-42", 2, 250_000L)));
    }
}
~~~

Trong ứng dụng thật, khi nhiều test dùng chung context hoặc cùng kho trạng thái, phải cô lập/reset dữ liệu. Test này chỉ chứng minh Consumer được gọi và dữ liệu vào kho minh họa; chưa chứng minh việc ghi database hoặc phát broker bền vững.

### 17.4. Lớp kiểm thử adapter vẫn cần thiết

Để triển khai qua HTTP hoặc hệ thống sự kiện, nên có thêm kiểm thử:

- Request/message có được ánh xạ sang đúng kiểu input không?
- `definition` có được adapter thực sự sử dụng không?
- Nội dung output, content-type, serializer có đúng không?
- Lỗi input được trả về qua HTTP hoặc message handling như mong đợi không?
- Retry có gây ghi trùng khi Consumer có tác dụng phụ không?
- Các headers/correlation ID quan trọng có được xử lý đúng không?

**Kiểm thử catalog xác minh logic ghép, không thay thế integration test HTTP/broker/serverless.**

## 18. Những lỗi thiết kế thường gặp

| Vấn đề | Vì sao chưa tốt | Hướng cải thiện |
|---|---|---|
| Một Function lớn làm hết mọi việc | Khó kiểm thử và tái sử dụng một phần | Tách normalize, parse, validate, calculate |
| `validateOrder` chỉ trả Boolean | Bước tiếp không còn `Order` để tính giá | Trả `ValidatedOrder` hoặc kiểu kết quả có dữ liệu |
| Mọi bước dùng `String` | Dễ ghép nhầm dữ liệu khác ý nghĩa | Dùng record domain rõ ràng |
| Function tính giá tự gọi HTTP response | Core gắn chặt giao thức | Đưa response mapping ra adapter |
| Function tính giá tự ghi database | Không thể test phép tính độc lập dễ dàng | Dùng Consumer hoặc orchestration riêng |
| Consumer đặt giữa pipeline rồi nối Function | Consumer không có output | Đưa Consumer cuối hoặc viết workflow |
| Thứ tự function bị đảo | Kiểu trung gian có thể không khớp | Viết sơ đồ/bảng hợp đồng trước |
| Tùy ý cast raw Function trong catalog | Che lỗi generic và chuyển lỗi tới runtime | Kiểm thử typed lookup và từng bước |
| Dùng `definition` như cấu hình transport | Property không tạo broker/HTTP route | Cấu hình adapter tương ứng |
| Function chứa mutable state dùng chung | Có thể lỗi khi concurrent invocation | Ưu tiên stateless, đồng bộ nếu có state |
| Bỏ qua retry khi có side effect | Có thể tạo dữ liệu trùng | Idempotency, transaction, unique key |

## 19. Checklist trước khi đưa pipeline vào sử dụng

Trước khi công bố một pipeline Spring Cloud Function, trả lời được các câu hỏi:

1. Từng bước có trách nhiệm rõ ràng và tên đúng nghiệp vụ không?
2. Input/output của mỗi bước có kiểu Java cụ thể, tránh `Object` không cần thiết không?
3. Bước validation có giữ lại dữ liệu cần cho nghiệp vụ kế tiếp không?
4. Logic tính toán có tránh phụ thuộc HTTP, broker, runtime serverless không?
5. Tác dụng phụ đã có nơi thực hiện và chính sách lỗi riêng chưa?
6. Tất cả function bean đã được Spring đăng ký với tên thực tế chưa?
7. `FunctionCatalog.lookup("A|B|C")` có tra cứu và thực thi đúng không?
8. Đầu ra tổng thể là `Function`, `Supplier`, `Consumer` hay `Runnable`?
9. Adapter đã được cấu hình và kiểm thử với payload/headers thật chưa?
10. Có kiểm tra lỗi, retry, concurrency và xử lý trùng khi cần không?

Không nhất thiết phải dùng đủ cả bốn dạng đầu ra trong một ứng dụng. Chọn pipeline đơn giản nhất phục vụ yêu cầu nghiệp vụ.

## 20. Bài tập thực hành

**Bài 1 — Tách một hàm lớn.** Một hàm `handlePayment` vừa trim input, parse số tiền, kiểm tra tiền dương, tính phí và ghi database. Hãy đề xuất tên, chữ ký của ít nhất bốn hàm độc lập và xác định hàm nào có tác dụng phụ.

**Bài 2 — Sửa validation.** Cho `parse: String → OrderDraft`, `check: OrderDraft → Boolean` và `price: ValidatedOrder → Quote`. Vì sao không nối trực tiếp cả ba bằng `|`? Viết chữ ký mới của bước validation.

**Bài 3 — Chọn nhiều cách sử dụng.** Với các bean `normalizeInput`, `parseOrder`, `validateOrder`, `calculateQuote`, `formatQuote`, hãy viết chuỗi `FunctionCatalog.lookup(...)` để có `Function<String,Quote>` và chuỗi khác để có `Function<String,String>`.

**Bài 4 — Ranh giới Consumer.** Đăng ký thêm `auditQuote: Consumer<Quote>`. Viết chuỗi ghép để tạo `Consumer<String>` và cho biết phương thức Java dùng để gọi pipeline đó. Vì sao không nối thêm `formatQuote` ở sau?

**Bài 5 — Lỗi phân loại.** Với input `"SKU-42,abc"`, `"SKU-42,0"` và `"SKU-42,2"`, hãy xác định bước nào xử lý lỗi hoặc tạo kết quả. Nêu kết quả cuối của trường hợp hợp lệ.

**Bài 6 — Cấu hình đa giao thức.** Cùng pipeline báo giá được dùng trong REST endpoint và service nhận sự kiện. Những phần nào có thể tái sử dụng, và những phần nào thuộc cấu hình adapter? Vì sao không chỉ đặt `spring.cloud.function.definition` là đủ?

**Bài 7 — Reactive.** Một luồng `Flux<String>` chứa nhiều đơn hàng. Viết bridge sử dụng `map` để tái sử dụng `Function<String,Quote>`, rồi mô tả lúc nào lỗi của phép tính có thể được phát qua `onError`.

**Bài 8 — Unit test và integration test.** Chọn hai test chỉ cần Java thuần và hai test cần Spring context/adapter. Giải thích mỗi lớp test phát hiện loại sai sót nào.

### Gợi ý đáp án

- **Bài 1:** Ví dụ `normalize: String→String`, `parse: String→PaymentDraft`, `validate: PaymentDraft→ValidatedPayment`, `calculateFee: ValidatedPayment→PaymentResult`, `persist: Consumer<PaymentResult>`.
- **Bài 2:** `Boolean` không chứa `ValidatedOrder`. Đổi thành `Function<OrderDraft,ValidatedOrder>` hoặc một kiểu kết quả rồi thêm bước chuyển dữ liệu phù hợp.
- **Bài 3:** `"normalizeInput|parseOrder|validateOrder|calculateQuote"` và chuỗi đó thêm `"|formatQuote"`.
- **Bài 4:** `"normalizeInput|parseOrder|validateOrder|calculateQuote|auditQuote"`; lấy `Consumer<String>` và gọi `accept(input)`. Consumer không trả Quote để nối bước sau.
- **Bài 5:** `abc` lỗi tại `parseOrder`; số lượng `0` lỗi tại `validateOrder`; `2` cho `Quote("SKU-42",2,250000)` và text `"SKU-42 x 2 = 250000 VND"`.
- **Bài 6:** Core và các function bean dùng chung; HTTP binding, message binding, serialization, error mapping, retry nằm ở adapter/integration.
- **Bài 7:** `Function<Flux<String>,Flux<Quote>> all = flux -> flux.map(quoteOne);`. Khi subscribe và phần tử gây lỗi được xử lý, luồng có thể phát `onError`.
- **Bài 8:** Unit test parse/validate và calculate; integration test catalog + adapter với payload, header, response/ack thật.

## 21. Ghi nhớ

- Tách **chuẩn hóa**, **phân tích**, **kiểm tra**, **tính toán** và **tác dụng phụ** theo ranh giới có ý nghĩa nghiệp vụ, không chỉ theo độ dài phương thức.
- Mỗi `Function<T,R>` nên có hợp đồng kiểu và trách nhiệm rõ. Dùng kiểu domain như `OrderDraft`, `ValidatedOrder` và `Quote` để biểu đạt trạng thái dữ liệu.
- Một pipeline có thể được ghép bằng `andThen` của Java hoặc bằng tên `A|B|C` qua `FunctionCatalog`; kiểm tra kiểu ở mọi điểm nối.
- Từ một tập function bean, có thể tạo nhiều pipeline: trả domain object, định dạng text hoặc kết thúc bằng Consumer để ghi nhận kết quả.
- `spring.cloud.function.definition` chọn logic cho adapter nhưng không tự cấu hình HTTP, sự kiện hoặc serverless.
- Kiểm thử từng hàm giúp khoanh vùng quy tắc; kiểm thử `FunctionCatalog` xác minh tên/thứ tự ghép; kiểm thử adapter xác minh giao thức, payload và xử lý lỗi.
- Phân tách hợp lý giúp cùng logic nghiệp vụ tái sử dụng qua nhiều ngữ cảnh mà không sao chép hoặc gắn cứng với transport.
