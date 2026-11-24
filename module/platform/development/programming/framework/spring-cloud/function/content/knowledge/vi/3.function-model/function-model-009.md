# Thiết kế hợp đồng đầu vào đầu ra và xử lý dữ liệu không hợp lệ

Trong **SPRING_CLOUD_FUNCTION**, hàm nghiệp vụ có thể được gọi qua HTTP, sự kiện hoặc môi trường serverless mà không phải viết lại logic. Điều kiện để tái sử dụng an toàn là **hợp đồng dữ liệu** phải đủ rõ: hàm nhận kiểu gì, trường nào bắt buộc, giá trị nào hợp lệ, trả kết quả nào và xử lý ra sao khi dữ liệu không đáp ứng yêu cầu.

Bài thuộc chương **Mô hình hàm**, tập trung thiết kế hợp đồng đầu vào/đầu ra cho **Supplier<T>**, **Function<T, R>** và **Consumer<T>**, phân biệt lỗi chuyển đổi dữ liệu với lỗi nghiệp vụ, xây dựng chính sách validation, xử lý exception/kết quả từ chối và kiểm thử ở cả phần lõi lẫn adapter. **FunctionCatalog** và **composition** được dùng để nối các hàm theo kiểu dữ liệu, còn adapter chịu trách nhiệm ánh xạ input, output và lỗi sang giao thức cụ thể.

## 1. Hợp đồng hàm gồm những gì?

Chữ ký **Function<T, R>** nói rằng một lời gọi **apply(T input)** trả về **R**, nhưng chỉ kiểu generic chưa đủ để mô tả toàn bộ hợp đồng.

Một hợp đồng hoàn chỉnh cần xác định:

1. **Hình dạng đầu vào:** tên trường, kiểu, đơn vị đo, trường bắt buộc/tùy chọn và định dạng.
2. **Điều kiện hợp lệ:** miền giá trị, quan hệ giữa các trường, trạng thái nghiệp vụ cho phép.
3. **Hành vi khi thành công:** kết quả trả về, ý nghĩa từng trường và bất biến được bảo đảm.
4. **Hành vi khi từ chối:** mã lỗi ổn định, trường gây lỗi, thông điệp dành cho người gọi và chính sách xử lý.
5. **Tác dụng phụ:** hàm có ghi dữ liệu, gửi thông điệp hay không; điều kiện idempotency nếu có.
6. **Phiên bản và khả năng tương thích:** hệ thống cũ xử lý được dữ liệu mới hay không.
7. **Ranh giới giao thức:** HTTP status, message headers, retry hoặc serverless error envelope được định nghĩa ở đâu.

Ví dụ:

~~~text
QuoteRequest(requestId, sku, quantity)
          │
          ▼
 Function<QuoteRequest, Quote>
          │
          ├── Thành công: Quote(requestId, sku, quantity, unitPrice, subtotal)
          │
          └── Từ chối: mã lỗi và nguyên nhân được xác định trước
~~~

**Hợp đồng nghiệp vụ không đồng nghĩa với hợp đồng HTTP.** Một **Function<QuoteRequest, Quote>** không cần biết URL hay HTTP status. Adapter HTTP có thể chuyển request thành **QuoteRequest** và chuyển lỗi thành response; binder sự kiện có thể xử lý lỗi theo retry/dead-letter; adapter serverless có cơ chế báo lỗi riêng.

## 2. Chọn hợp đồng phù hợp với Supplier, Function và Consumer

| Mô hình | Chữ ký | Hợp đồng đầu vào | Hợp đồng đầu ra | Khi dữ liệu sai |
| --- | --- | --- | --- | --- |
| **Supplier<R>** | () → R | Không nhận đối số nghiệp vụ | Giá trị R được tạo/cung cấp | Lỗi cấu hình/nguồn dữ liệu có thể khiến **get()** thất bại |
| **Function<T, R>** | T → R | T có schema và quy tắc validation | R có schema và bảo đảm kết quả | Có thể ném exception hoặc trả kiểu kết quả từ chối được thiết kế rõ |
| **Consumer<T>** | T → void | T cần được xác thực trước side effect | Không có kết quả nghiệp vụ | Có thể ném exception để adapter nhận biết, hoặc dùng cơ chế từ chối theo hợp đồng |

**Function<T, R>** phù hợp cho logic biến đổi dữ liệu. Nếu input gồm nhiều thông tin, gói chúng trong **record/DTO** thay vì dùng một Map không có schema rõ ràng.

Ví dụ:

~~~java
public record QuoteRequest(
    String requestId,
    String sku,
    Integer quantity
) {}

public record Quote(
    String requestId,
    String sku,
    int quantity,
    java.math.BigDecimal unitPrice,
    java.math.BigDecimal subtotal
) {}
~~~

Hai kiểu giúp phân biệt rõ **input** với **output**. Dùng **Integer** thay cho **int** ở quantity đầu vào cho phép phát hiện trường thiếu dưới dạng **null**, thay vì vô tình đồng nhất trường thiếu và số 0 sau chuyển đổi.

**Record chỉ làm các field reference bất biến**, không tự kiểm tra nghiệp vụ. Một record có thể được tạo với chuỗi rỗng, quantity âm hoặc quantity null. Nếu record chứa List/Map mutable, bản thân nội dung của collection cũng chưa trở thành bất biến.

## 3. Phân chia ba lớp kiểm tra dữ liệu

Khi một request hoặc event đi vào ứng dụng, cần tách các loại lỗi khác nhau:

~~~mermaid
flowchart TD
    A["HTTP JSON / Message bytes / Serverless event"] --> B{"Đọc và chuyển đổi được?"}
    B -- "Không" --> C["Lỗi định dạng hoặc conversion"]
    B -- "Có" --> D["DTO / record T"]
    D --> E{"Hợp lệ theo contract?"}
    E -- "Không" --> F["Lỗi validation"]
    E -- "Có" --> G{"Được phép theo quy tắc nghiệp vụ?"}
    G -- "Không" --> H["Từ chối nghiệp vụ"]
    G -- "Có" --> I["Thực thi Function"]
    I --> J["Output R"]
~~~

### 3.1. Lỗi cấu trúc và chuyển đổi

Ví dụ request không phải JSON hợp lệ hoặc trường **quantity** là một object thay vì số. Adapter/converter có thể không tạo được **QuoteRequest**; lúc đó **apply(...)** thậm chí chưa được gọi.

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": {"value": 3}
}
~~~

Hành vi cụ thể còn phụ thuộc trình chuyển đổi JSON, cấu hình ép kiểu và kiểu Java. Không nên mặc định mọi converter đều từ chối/ép kiểu giống nhau.

### 3.2. Lỗi validation theo hợp đồng

Payload có thể deserialize thành record nhưng vẫn không hợp lệ:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 0
}
~~~

Giá trị **quantity = 0** đúng kiểu **Integer** nhưng vi phạm điều kiện “số lượng phải từ 1 đến 1000”. Đây là validation nghiệp vụ/đầu vào, không phải lỗi parse JSON.

### 3.3. Từ chối theo trạng thái nghiệp vụ

Một request có cấu trúc hợp lệ nhưng mã hàng không được hỗ trợ, sản phẩm ngừng bán hoặc kho hết hàng. Lỗi này khác với **quantity** sai kiểu và khác với database mất kết nối.

Ví dụ trong bài: **sku = "UNKNOWN"** hợp lệ về cú pháp nhưng không có trong bảng giá mẫu. Hàm sẽ báo từ chối bằng mã **UNKNOWN_SKU**. Khi triển khai thực tế cần quy định rõ trường hợp này được biểu diễn thành lỗi API hay kết quả nghiệp vụ như “không báo giá được”.

## 4. Xác định schema: tên trường, kiểu, đơn vị và giới hạn

Trước khi viết code, hãy lập bảng hợp đồng cho ví dụ báo giá.

| Trường | Kiểu | Bắt buộc | Ràng buộc và ý nghĩa |
| --- | --- | --- | --- |
| **requestId** | String | Có | Mã tương quan nghiệp vụ không rỗng; tối đa 64 ký tự |
| **sku** | String | Có | Mã sản phẩm; trim và chuẩn hóa uppercase; chỉ dùng chữ, số, dấu gạch nối; tối đa 24 ký tự |
| **quantity** | Integer | Có | Số lượng nguyên từ **1** tới **1000** |
| **unitPrice** (output) | BigDecimal | Có khi thành công | Giá từ nguồn nội bộ; đơn vị tiền và số chữ số thập phân theo chính sách ứng dụng |
| **subtotal** (output) | BigDecimal | Có khi thành công | **quantity × unitPrice**, chưa gồm thuế/phí khác |

**Đơn vị đo là một phần của schema.** Một trường **weight** cần ghi rõ gram hay kilogram; trường **amount** cần nêu tiền tệ và cách làm tròn. Trong ví dụ, bảng giá mẫu là số nguyên theo đơn vị tiền giả định của hệ thống, nhằm tập trung vào hợp đồng Function. Một sản phẩm thanh toán thực tế cần mô hình tiền tệ và chính sách làm tròn chặt chẽ hơn.

Quy định cách xử lý chuỗi cũng cần rõ ràng: nếu có trim hoặc đổi chữ hoa, làm điều đó nhất quán; nếu requestId là định danh phân biệt hoa/thường, không tự đổi chữ hoa chỉ vì sku được chuẩn hóa.

## 5. Ví dụ Java 17+: một Function có validation tường minh

Ứng dụng sau minh họa **Function<QuoteRequest, Quote>**, một dịch vụ tính giá dùng dữ liệu nội bộ và hai loại lỗi có mã rõ ràng.

Tệp **QuoteContractApplication.java**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteContractApplication.class, args);
    }

    public record QuoteRequest(
        String requestId,
        String sku,
        Integer quantity
    ) {}

    public record Quote(
        String requestId,
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal subtotal
    ) {}

    // Input không đáp ứng hợp đồng của Function.
    public static final class InvalidQuoteRequestException
            extends IllegalArgumentException {

        private final String code;
        private final String field;

        public InvalidQuoteRequestException(
                String code, String field, String message) {
            super(message);
            this.code = code;
            this.field = field;
        }

        public String code() {
            return code;
        }

        public String field() {
            return field;
        }
    }

    // Input hợp lệ về cấu trúc nhưng bị từ chối theo nghiệp vụ.
    public static final class QuoteRejectedException
            extends RuntimeException {

        private final String code;

        public QuoteRejectedException(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static final class PriceCatalog {
        private final Map<String, BigDecimal> prices;

        public PriceCatalog(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal findPrice(String sku) {
            return prices.get(sku);
        }
    }

    public static final class QuoteService {
        private final PriceCatalog catalog;

        public QuoteService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        public Quote calculate(QuoteRequest request) {
            if (request == null) {
                throw invalid("REQUEST_REQUIRED", "request",
                    "Quote request must not be null");
            }

            String requestId = requiredText(
                request.requestId(), "requestId", 64);

            String sku = requiredText(request.sku(), "sku", 24)
                .toUpperCase(Locale.ROOT);

            if (!sku.matches("[A-Z0-9-]{1,24}")) {
                throw invalid("INVALID_SKU", "sku",
                    "SKU contains unsupported characters");
            }

            Integer quantity = request.quantity();
            if (quantity == null
                    || quantity < 1
                    || quantity > 1000) {
                throw invalid("INVALID_QUANTITY", "quantity",
                    "Quantity must be between 1 and 1000");
            }

            BigDecimal unitPrice = catalog.findPrice(sku);
            if (unitPrice == null) {
                throw new QuoteRejectedException(
                    "UNKNOWN_SKU", "Product is not available for quoting");
            }

            BigDecimal subtotal = unitPrice.multiply(
                BigDecimal.valueOf(quantity));

            return new Quote(
                requestId, sku, quantity, unitPrice, subtotal);
        }

        private static String requiredText(
                String value, String field, int maxLength) {

            if (value == null || value.isBlank()) {
                throw invalid("REQUIRED_FIELD", field,
                    "Field must not be blank");
            }

            String normalized = value.trim();
            if (normalized.length() > maxLength) {
                throw invalid("FIELD_TOO_LONG", field,
                    "Field exceeds maximum length");
            }

            return normalized;
        }

        private static InvalidQuoteRequestException invalid(
                String code, String field, String message) {
            return new InvalidQuoteRequestException(
                code, field, message);
        }
    }

    @Bean
    PriceCatalog priceCatalog() {
        return new PriceCatalog(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    QuoteService quoteService(PriceCatalog catalog) {
        return new QuoteService(catalog);
    }

    @Bean("calculateQuote")
    Function<QuoteRequest, Quote> calculateQuote(
            QuoteService service) {
        return service::calculate;
    }
}
~~~

**Những quyết định quan trọng:**

- Input có **Integer quantity** để tách trường thiếu khỏi giá trị 0.
- **requiredText(...)** xác thực chuỗi không rỗng, chuẩn hóa trim và giới hạn độ dài.
- **sku** được chuẩn hóa với **Locale.ROOT** để tránh kết quả phụ thuộc locale máy chạy.
- **QuoteService** không tham chiếu trực tiếp tới HTTP request, Kafka message hay handler serverless.
- **PriceCatalog** giữ bảng giá bất biến; unitPrice không phải dữ liệu do client tự khai báo.
- **InvalidQuoteRequestException** mang **code** và **field** để adapter xây response có cấu trúc.
- **QuoteRejectedException** biểu thị trường hợp request hợp lệ về cấu trúc nhưng không thể đáp ứng quy tắc nghiệp vụ.
- **calculateQuote** là bean **Function<QuoteRequest, Quote>** được Spring Cloud Function nhận diện qua FunctionCatalog.

Các lớp exception được khai báo riêng để giữ ví dụ dễ đọc. Với hệ thống lớn, nên tách các kiểu hợp đồng, exception và service vào package thích hợp.

### 5.1. Ví dụ đầu vào hợp lệ

~~~json
{
  "requestId": "REQ-101",
  "sku": " book ",
  "quantity": 2
}
~~~

Kết quả dự kiến:

~~~json
{
  "requestId": "REQ-101",
  "sku": "BOOK",
  "quantity": 2,
  "unitPrice": 85000,
  "subtotal": 170000
}
~~~

**QuoteService** trim **sku**, chuẩn hóa sang uppercase, tra giá BOOK và tính **2 × 85000 = 170000**. Kết quả không mang thông tin HTTP hay broker.

### 5.2. Input thiếu hoặc sai

| Đầu vào | Điều kiện lỗi | Mã lỗi do ví dụ phát ra |
| --- | --- | --- |
| **request = null** | Không có object | **REQUEST_REQUIRED** |
| **requestId = ""** | Trường bắt buộc rỗng | **REQUIRED_FIELD** |
| **sku = "A B"** | Ký tự không được phép | **INVALID_SKU** |
| **quantity = null** | Thiếu trường bắt buộc | **INVALID_QUANTITY** |
| **quantity = 0** | Dưới giới hạn | **INVALID_QUANTITY** |
| **quantity = 1001** | Trên giới hạn | **INVALID_QUANTITY** |
| **sku = "UNKNOWN"** | Không có trong bảng giá | **UNKNOWN_SKU** |

Đây là **mã lỗi của ví dụ ứng dụng**, không phải mã lỗi định sẵn của Spring Cloud Function. Với payload bị converter từ chối trước khi có QuoteRequest, lỗi thuộc adapter và có thể không phải một trong các mã trên; ứng dụng nên có error contract riêng cho lỗi parse/conversion.

## 6. Tách validation khỏi serialization và framework

Một JSON hợp lệ không bảo đảm là một yêu cầu nghiệp vụ hợp lệ. Tương tự, deserialize thành **QuoteRequest** không mặc nhiên gọi validation, trừ khi adapter hoặc ứng dụng đã được cấu hình làm việc đó.

Một số ứng dụng dùng **Jakarta Bean Validation**:

~~~java
public record QuoteRequestWithConstraints(
    @jakarta.validation.constraints.NotBlank
    String requestId,

    @jakarta.validation.constraints.NotBlank
    String sku,

    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Min(1)
    @jakarta.validation.constraints.Max(1000)
    Integer quantity
) {}
~~~

Annotation diễn tả một phần quy tắc ở mức trường, nhưng **chỉ thêm annotation không bảo đảm một bean Function được gọi qua mọi adapter sẽ tự validate trước apply()**. Cần cơ chế gọi validator ở ranh giới phù hợp (ví dụ HTTP controller với **@Valid** và hạ tầng validation hoặc validator được inject ở lớp điều hợp).

Ngoài ra, validation dựa trên annotation chưa giải quyết mọi quy tắc:

- SKU có tồn tại trong nguồn dữ liệu hiện hành hay không.
- Quantity có thể đặt được ở trạng thái kho hiện tại không.
- Hai trường có tương quan hợp lệ không.
- Yêu cầu có được phép thực hiện ở trạng thái đơn hàng hiện tại không.

Có thể kết hợp validation ở **adapter** cho ràng buộc hình dạng và validation ở **lõi nghiệp vụ** cho các bất biến bắt buộc. Nhưng những quy tắc quan trọng không nên chỉ tồn tại trong HTTP controller, nếu cùng Function còn được gọi qua broker/serverless.

## 7. Hai chiến lược báo lỗi: exception và kết quả tường minh

Một Function có ít nhất hai cách biểu diễn việc không thể tạo output thành công.

### 7.1. Ném exception

Như **QuoteService.calculate(...)**:

~~~java
throw new InvalidQuoteRequestException(
    "INVALID_QUANTITY", "quantity",
    "Quantity must be between 1 and 1000"
);
~~~

Ưu điểm: dễ giữ chữ ký **Function<QuoteRequest, Quote>** và ngắt luồng xử lý ngay khi hợp đồng bị vi phạm. Nhược điểm: adapter phải ánh xạ exception phù hợp; một exception không tự cung cấp HTTP status hoặc chính sách retry.

Nên dùng loại exception và mã lỗi tường minh cho các lỗi dự kiến, tránh để client phải phân tích **getMessage()** như một định danh ổn định.

### 7.2. Trả kết quả thành công/từ chối trong cùng một hợp đồng

Khi yêu cầu từ chối là một nhánh nghiệp vụ bình thường, có thể thiết kế một kiểu kết quả gồm hai trạng thái:

~~~java
public sealed interface QuoteDecision
        permits QuoteAccepted, QuoteDeclined {}

public record QuoteAccepted(
    QuoteContractApplication.Quote quote
) implements QuoteDecision {}

public record QuoteDeclined(
    String code,
    String field,
    String message
) implements QuoteDecision {}
~~~

Và một Function chuyển kết quả:

~~~java
Function<
    QuoteContractApplication.QuoteRequest,
    QuoteDecision> decide = request -> {
    try {
        return new QuoteAccepted(service.calculate(request));
    } catch (QuoteContractApplication.InvalidQuoteRequestException ex) {
        return new QuoteDeclined(
            ex.code(), ex.field(), ex.getMessage());
    } catch (QuoteContractApplication.QuoteRejectedException ex) {
        return new QuoteDeclined(
            ex.code(), null, ex.getMessage());
    }
};
~~~

Đoạn trên minh họa các kiểu **QuoteDecision**, **QuoteAccepted**, **QuoteDeclined** nằm trong cùng package hoặc được import phù hợp, và biến **service** đã được cung cấp. Với kiểu kết quả đa hình, cần có schema/serializer rõ ràng; không mặc định mọi converter của Spring Cloud Function tự serialize/deserialize **sealed interface** giống nhau.

| Chiến lược | Phù hợp với | Cần quan tâm |
| --- | --- | --- |
| **Exception** | Input sai, lỗi không thể tiếp tục, lỗi hạ tầng | Phân loại, ánh xạ theo adapter, retry đúng nhóm |
| **Result/Decision tường minh** | Từ chối là kết quả nghiệp vụ dự kiến | Schema output thể hiện các nhánh, phiên bản và cách consumer xử lý |
| **Trả null** | Hiếm khi nên là lựa chọn mặc định | Dễ gây mơ hồ với rỗng/lỗi và không nhất quán giữa adapter |

**Không dùng null để thay thế mọi lỗi.** Một output null có thể có ý nghĩa khác nhau khi trả qua HTTP, stream hay composition, và dễ làm hàm kế tiếp gặp **NullPointerException**. Nếu “không tìm thấy” là kết quả dự kiến, hãy đặt tên và biểu diễn trạng thái đó rõ ràng bằng kiểu hoặc contract thích hợp.

## 8. Adapter HTTP quyết định status và error response

Với Spring Cloud Function Web starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

và cấu hình chọn bean:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
~~~

khi ứng dụng chạy trên cổng 8080 mặc định, có thể gọi:

~~~bash
curl -i -X POST http://localhost:8080/calculateQuote \
  -H "Content-Type: application/json" \
  -d '{"requestId":"REQ-101","sku":"BOOK","quantity":2}'
~~~

Adapter có thể chuyển JSON thành **QuoteRequest**, gọi **FunctionCatalog** rồi serialize **Quote**. Nhưng **IllegalArgumentException** hoặc **QuoteRejectedException** không tự bảo đảm trả HTTP 400, 422 hay một error JSON cụ thể. Cần kiểm thử behavior phiên bản adapter đang chạy và bổ sung lớp HTTP mapping khi hợp đồng API đòi hỏi cấu trúc lỗi ổn định.

Ví dụ API error contract do ứng dụng tự định nghĩa:

~~~json
{
  "code": "INVALID_QUANTITY",
  "field": "quantity",
  "message": "Quantity must be between 1 and 1000"
}
~~~

Một chính sách HTTP có thể là:

| Loại tình huống | Mã HTTP thường cân nhắc | Diễn giải |
| --- | --- | --- |
| JSON sai cú pháp/không deserialize | **400 Bad Request** | Request không đọc được |
| Thiếu trường hoặc giá trị không hợp lệ | **400 Bad Request** hoặc **422 Unprocessable Content** | Chọn nhất quán với hợp đồng API |
| Mã SKU hợp lệ nhưng không thể báo giá | **404** hoặc **422** theo API contract | Tùy có xem SKU là tài nguyên truy vấn hay từ chối nghiệp vụ |
| Lỗi database/service tạm thời | **5xx** | Không nên công khai nội dung exception hạ tầng |
| Thành công | **2xx** | Trả payload **Quote** |

Bảng mô tả **chính sách thiết kế**, không khẳng định Spring Cloud Function Web mặc định trả các mã này.

### 8.1. Ví dụ một HTTP adapter chủ động ánh xạ lỗi

Nếu cần kiểm soát rõ status và error body, có thể tạo một controller riêng của ứng dụng ở **/api/quotes**, gọi **QuoteService**. Ví dụ này dùng Spring MVC và không thay thế endpoint tự sinh **/calculateQuote** của Spring Cloud Function Web.

~~~java
package example.function;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteHttpAdapter {

    private final QuoteContractApplication.QuoteService service;

    public QuoteHttpAdapter(
            QuoteContractApplication.QuoteService service) {
        this.service = service;
    }

    public record ApiError(
        String code,
        String field,
        String message
    ) {}

    @PostMapping
    public QuoteContractApplication.Quote calculate(
            @RequestBody QuoteContractApplication.QuoteRequest request) {
        return service.calculate(request);
    }

    @ExceptionHandler(
        QuoteContractApplication.InvalidQuoteRequestException.class)
    public ResponseEntity<ApiError> invalid(
            QuoteContractApplication.InvalidQuoteRequestException ex) {
        return ResponseEntity.badRequest().body(
            new ApiError(ex.code(), ex.field(), ex.getMessage()));
    }

    @ExceptionHandler(
        QuoteContractApplication.QuoteRejectedException.class)
    public ResponseEntity<ApiError> rejected(
            QuoteContractApplication.QuoteRejectedException ex) {
        return ResponseEntity.unprocessableEntity().body(
            new ApiError(ex.code(), null, ex.getMessage()));
    }
}
~~~

Ở đây, controller làm nhiệm vụ **dịch lỗi nghiệp vụ sang HTTP**, còn **QuoteService** vẫn nhận/đưa ra Java DTO. Ví dụ chưa xử lý riêng các lỗi parse JSON xảy ra **trước** khi controller gọi service; hệ thống thực có thể dùng một **@RestControllerAdvice** chung để chuẩn hóa những lỗi đó.

Không nên đặt logic ánh xạ HTTP code trong **Function.apply(...)** nếu vẫn muốn triển khai cùng một hàm qua broker hoặc serverless.

## 9. Sự kiện: dữ liệu không hợp lệ liên quan trực tiếp tới retry

Với Spring Cloud Stream và binder thích hợp, có thể dùng cùng **Function<QuoteRequest, Quote>** để nhận message đầu vào và phát message đầu ra:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
    stream:
      bindings:
        calculateQuote-in-0:
          destination: quote-requests
        calculateQuote-out-0:
          destination: quote-results
~~~

Cấu hình trên cần Spring Cloud Stream, binder cụ thể, broker và các thuộc tính kết nối. Với mỗi message, framework thực hiện conversion tới **QuoteRequest**, gọi Function và gửi **Quote** nếu xử lý thành công.

Vấn đề đặc thù là **một sự kiện lỗi có thể được giao lại**. Lỗi thiếu field cố định thường không biến mất sau retry, trong khi lỗi database tạm thời có thể phục hồi.

~~~mermaid
flowchart TD
    A["Message từ broker"] --> B{"Chuyển đổi và validate"}
    B -- "Input lỗi vĩnh viễn" --> C["Reject / dead-letter / error event"]
    B -- "Hợp lệ" --> D["Function.apply"]
    D --> E{"Kết quả"}
    E -- "Thành công" --> F["Publish Quote"]
    E -- "Lỗi tạm thời" --> G["Retry có giới hạn + backoff"]
    E -- "Từ chối nghiệp vụ" --> H["Kênh kết quả từ chối hoặc lỗi theo contract"]
~~~

| Nhóm lỗi | Retry tự động có ích? | Hướng xử lý thường dùng |
| --- | --- | --- |
| JSON không deserialize được | Thường không nếu payload giữ nguyên | Dead-letter/quarantine, theo dõi và sửa nguồn |
| Quantity không hợp lệ | Thường không | Báo lỗi có mã, từ chối hoặc dead-letter |
| UNKNOWN_SKU | Tùy nghiệp vụ có dữ liệu thay đổi hay không | Từ chối nghiệp vụ hoặc quy trình làm giàu dữ liệu |
| Database timeout | Có thể | Retry giới hạn, backoff, circuit breaker/timeout khi phù hợp |
| Broker mất kết nối lúc publish | Có thể | Dựa vào chính sách binder, bảo đảm không nhân đôi tác dụng phụ |

**Không có một quy tắc retry/dead-letter chung cho mọi binder.** Kafka, RabbitMQ và các adapter khác có cơ chế acknowledgment, retry, error channel và dead-letter khác nhau. Phải kiểm thử chính xác binder và cấu hình phiên bản đang dùng.

Nếu muốn mọi bản tin được xử lý thành một **kết quả nghiệp vụ** kể cả trường hợp bị từ chối, có thể đổi output thành **QuoteDecision** hoặc một DTO kết quả có trạng thái rõ ràng. Khi đó message có thể được coi là xử lý thành công về mặt giao nhận ngay cả khi nghiệp vụ trả “declined”; cần có bên nhận hiểu nhánh này. Đây là một **quyết định hợp đồng**, không phải thủ thuật xử lý exception.

## 10. Serverless: lỗi cũng phải có hợp đồng

Trong môi trường serverless, adapter có thể chuyển event thành **QuoteRequest**, gọi **calculateQuote** rồi chuyển output về định dạng runtime yêu cầu.

~~~text
Cloud event
  -> Serverless adapter / conversion
  -> QuoteRequest
  -> calculateQuote.apply(...)
  -> Quote hoặc exception
  -> Runtime result / error mapping
~~~

Một lỗi validation được báo bằng exception có thể khiến runtime hoặc dịch vụ trigger thực hiện retry, tùy mô hình gọi đồng bộ hay bất đồng bộ. Vì thế cần phân biệt rõ:

- **Lỗi vĩnh viễn:** dữ liệu sai không tự sửa được qua retry.
- **Lỗi tạm thời:** tài nguyên phụ thuộc gián đoạn, có thể phục hồi.
- **Từ chối nghiệp vụ:** việc từ chối có phải là kết quả bình thường hay một thất bại cần hệ thống điều phối biết?

**Handler, event envelope, status và retry tùy nền tảng**; bản thân Function không quyết định chúng. Giữ logic validation chung bên trong service, nhưng thiết kế wrapper serverless nhận biết code lỗi để ánh xạ đúng hợp đồng kích hoạt.

## 11. Message<T> và header: metadata không thay thế payload contract

Một **Message<T>** có **payload** và **headers**. Với Spring Cloud Function, có thể khai báo **Function<Message<QuoteRequest>, Message<Quote>>** nếu logic điều hợp cần đọc metadata.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

// Đặt trong lớp cấu hình ứng dụng có QuoteService đã được Spring inject.
@Bean("calculateQuoteMessage")
Function<
    Message<QuoteContractApplication.QuoteRequest>,
    Message<QuoteContractApplication.Quote>>
        calculateQuoteMessage(
            QuoteContractApplication.QuoteService service) {

    return incoming -> {
        QuoteContractApplication.Quote quote =
            service.calculate(incoming.getPayload());

        var output = MessageBuilder.withPayload(quote);

        Object correlation =
            incoming.getHeaders().get("correlationId");
        if (correlation != null) {
            output.setHeader("correlationId", correlation);
        }

        return output.build();
    };
}
~~~

Ví dụ này là **phương thức @Bean** cần đặt trong một lớp cấu hình Spring thích hợp (không phải một file Java độc lập ở cấp top-level). **QuoteService** vẫn xử lý payload; wrapper đọc header và quyết định chỉ truyền tiếp metadata cần thiết.

Các điểm cần nhớ:

- Header **correlationId** giúp liên hệ log và truy vết, **không thay** các trường bắt buộc **requestId**, **sku**, **quantity** của payload.
- Không lấy thông tin phân quyền từ một header do client tự khai báo nếu chưa được tầng bảo mật xác thực.
- Không mặc định HTTP headers, Kafka headers và serverless metadata ánh xạ giống nhau.
- Không cố sửa trực tiếp **MessageHeaders** vì map đầu vào có thể là read-only; tạo Message mới.
- Không copy tất cả header khi chưa có lý do. Header nội bộ hoặc thông tin nhạy cảm có thể không được phép chuyển tiếp.

Ngoài kiểu **Message<T>**, Spring Cloud Function còn hỗ trợ kiểu BiFunction/BiConsumer lấy **payload** và **Map headers** ở các trường hợp phù hợp. Map headers là metadata giao thức, không phải một payload nghiệp vụ thứ hai.

## 12. Composition phải thống nhất cả kiểu dữ liệu và lỗi

Spring Cloud Function hỗ trợ ghép các hàm theo tên qua **FunctionCatalog**. Giả sử thêm bean:

~~~java
@Bean("formatQuote")
Function<QuoteContractApplication.Quote, String> formatQuote() {
    return quote -> quote.requestId() + ":"
        + quote.subtotal().toPlainString();
}
~~~

**formatQuote** nhận đúng **Quote** do **calculateQuote** trả về. Có thể chọn:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote|formatQuote
~~~

Dòng dữ liệu:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["calculateQuote"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

Nếu **calculateQuote** ném exception, **formatQuote** sẽ không nhận được **Quote** để xử lý trong đường gọi thông thường. Nếu chuyển sang chiến lược **QuoteDecision**, hàm kế tiếp phải nhận **QuoteDecision** hoặc một dạng kết quả có cấu trúc, không thể giữ chữ ký **Function<Quote, String>** mà kỳ vọng framework tự hiểu nhánh lỗi nghiệp vụ.

Một hợp đồng composition tốt quy định:

1. Đầu ra **R** của bước trước có tương thích đầu vào **T** của bước sau không?
2. Null hoặc kết quả trống có được phép không?
3. Exception ở mỗi bước được xử lý ở đâu?
4. Những header cần thiết có được giữ qua từng bước không?
5. Đầu ra của pipeline cuối phù hợp với adapter đang expose/bind không?

**Không trộn lỗi nghiệp vụ với chuyển đổi kiểu.** Nếu dữ liệu vi phạm contract, nên báo đúng lỗi/nhánh từ chối, thay vì hy vọng message converter sẽ tự chuyển một object sai thành kiểu đầu vào mà hàm tiếp theo cần.

## 13. Hợp đồng với các luồng reactive

Với Project Reactor, một Function có thể xử lý publisher:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

Function<Flux<QuoteContractApplication.QuoteRequest>,
         Flux<QuoteContractApplication.Quote>> reactiveQuotes =
    requests -> requests.map(service::calculate);
~~~

Trong ví dụ, **service** là một **QuoteService** đã được cung cấp bằng dependency injection. Các thao tác validation chạy trên từng phần tử khi Flux được subscribe.

**Điểm cần thận trọng:** nếu **service.calculate(...)** ném exception bên trong **map(...)**, publisher thường phát **onError** và luồng kết thúc, trừ khi pipeline được thiết kế xử lý lỗi phù hợp. Điều này khác với kỳ vọng “một message sai thì chỉ bỏ message đó và tiếp tục tất cả message sau”.

Nếu yêu cầu xử lý lỗi riêng từng phần tử, có thể chuyển về kiểu kết quả tường minh:

~~~java
Function<Flux<QuoteContractApplication.QuoteRequest>,
         Flux<QuoteDecision>> decisions =
    requests -> requests.map(request -> {
        try {
            return (QuoteDecision) new QuoteAccepted(
                service.calculate(request));
        } catch (QuoteContractApplication.InvalidQuoteRequestException ex) {
            return new QuoteDeclined(
                ex.code(), ex.field(), ex.getMessage());
        } catch (QuoteContractApplication.QuoteRejectedException ex) {
            return new QuoteDeclined(
                ex.code(), null, ex.getMessage());
        }
    });
~~~

Ví dụ **QuoteDecision** là kiểu nghiệp vụ đã định nghĩa ở phần 7; đoạn code không tự triển khai retry hoặc xử lý lỗi hạ tầng. Việc chọn bắt lỗi nào để biểu diễn thành kết quả phải dựa trên contract, tránh bắt mọi **Exception** rồi biến lỗi hệ thống thành một sự kiện “đã xử lý thành công” giả tạo.

Ngoài ra, không phải mọi adapter hỗ trợ **Flux** theo cùng cách. Subscription, backpressure, converter và ánh xạ lỗi theo HTTP streaming hoặc binder stream cần được xác minh với phiên bản tích hợp thực tế.

## 14. Bảo đảm hợp đồng khi có tác dụng phụ hoặc retry

Mặc dù ví dụ **calculateQuote** chỉ tính toán, nhiều Function hoặc Consumer trong dự án thực tế vừa validate vừa ghi database/gửi sự kiện.

Một quy tắc quan trọng: **kiểm tra dữ liệu trước tác dụng phụ, nhưng vẫn phải có chiến lược khôi phục khi tác dụng phụ chỉ hoàn tất một phần.**

~~~text
Nhận OrderPaidEvent
  -> Chuyển đổi và validate
  -> Kiểm tra idempotency key
  -> Ghi trạng thái/giao dịch
  -> Phát thông điệp hoặc gửi notification
~~~

Các yêu cầu nên xác định trong contract:

- **Event ID** là định danh ổn định của sự kiện nghiệp vụ, không phụ thuộc số lần broker giao lại.
- **Idempotency:** cùng event ID được xử lý lại có làm tăng số lần ghi hoặc thu tiền không?
- **Transaction:** thao tác ghi nào cần nguyên tử; có cần unique constraint không?
- **Side effect bên ngoài:** database thành công nhưng gửi thông báo thất bại thì xử lý ra sao?
- **Retry:** lỗi nào có thể thử lại, giới hạn số lần và backoff.
- **Kết quả cho caller:** Consumer không trả output nghiệp vụ; trạng thái xử lý được phản ánh qua hệ thống lưu trữ hoặc cơ chế lỗi của adapter.

Không dùng **Map trong bộ nhớ của một singleton** làm cơ chế idempotency bền vững giữa nhiều replica. Với hệ thống phân tán, thường cần unique constraint, khóa nghiệp vụ, giao dịch hoặc mô hình outbox tùy yêu cầu.

## 15. Thiết kế hợp đồng có khả năng tiến hóa

Khi một Function được gọi qua nhiều giao thức, thay đổi DTO là thay đổi **contract**. Cần xác định tính tương thích trước khi triển khai.

| Thay đổi | Nguy cơ | Cách làm thận trọng |
| --- | --- | --- |
| Thêm trường output tùy chọn | Client cũ có thể từ chối trường lạ | Kiểm tra serializer và hợp đồng consumer |
| Thêm trường input bắt buộc | Client cũ không gửi trường đó | Version contract hoặc có chính sách chuyển đổi/backward compatibility |
| Đổi **quantity** từ số sang chuỗi | Message cũ có thể không deserialize | Tạo version mới hoặc migration rõ ràng |
| Đổi đơn vị từ gram sang kilogram | Dữ liệu vẫn parse được nhưng ý nghĩa sai | Đổi tên trường/schema hoặc version; không âm thầm đổi đơn vị |
| Đổi tên mã lỗi | Client dựa trên code cũ xử lý sai | Coi error code là một phần API contract |
| Đổi kiểu output thành **QuoteDecision** | Client mong Quote có thể không hiểu nhánh kết quả | Thỏa thuận schema/consumer và test tương thích |
| Đổi tên bean Function | Endpoint/binding/definition có thể trỏ tên cũ | Cập nhật cấu hình triển khai và integration test |

Một hợp đồng dữ liệu có thể được mô tả bằng JSON Schema, OpenAPI hoặc schema của hệ thống sự kiện. Nhưng **kiểu Java và schema truyền tải không hoàn toàn giống nhau**: nullability, số thập phân, thời gian và field mặc định cần được kiểm tra theo serializer đang sử dụng.

Nếu broker áp dụng schema registry, cần chính sách compatibility cho các phiên bản producer và consumer. Với HTTP, có thể version endpoint hoặc media type khi thay đổi phá vỡ hợp đồng. Với serverless, cần kiểm tra event envelope do runtime/trigger cung cấp.

## 16. Kiểm thử unit: từng loại input và mã lỗi

Một Function đúng phải xử lý **trường hợp hợp lệ** và **trường hợp bị từ chối** theo hợp đồng. Unit test của service độc lập với web server và broker.

Ví dụ JUnit 5:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;

class QuoteContractApplicationTest {

    private final QuoteContractApplication.QuoteService service =
        new QuoteContractApplication.QuoteService(
            new QuoteContractApplication.PriceCatalog(
                Map.of("BOOK", new BigDecimal("85000"))
            )
        );

    @Test
    void validInputReturnsNormalizedQuote() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-101", " book ", 2);

        var result = service.calculate(input);

        assertEquals("BOOK", result.sku());
        assertEquals(2, result.quantity());
        assertEquals(new BigDecimal("170000"), result.subtotal());
    }

    @Test
    void missingQuantityIsRejectedWithStableCode() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-102", "BOOK", null);

        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(input)
        );

        assertEquals("INVALID_QUANTITY", error.code());
        assertEquals("quantity", error.field());
    }

    @Test
    void zeroQuantityIsRejected() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-103", "BOOK", 0);

        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(input)
        );

        assertEquals("INVALID_QUANTITY", error.code());
    }

    @Test
    void unknownSkuIsBusinessRejection() {
        var input = new QuoteContractApplication.QuoteRequest(
            "REQ-104", "UNKNOWN", 1);

        var error = assertThrows(
            QuoteContractApplication.QuoteRejectedException.class,
            () -> service.calculate(input)
        );

        assertEquals("UNKNOWN_SKU", error.code());
    }

    @Test
    void nullRequestIsRejectedBeforeAnyProcessing() {
        var error = assertThrows(
            QuoteContractApplication.InvalidQuoteRequestException.class,
            () -> service.calculate(null)
        );

        assertEquals("REQUEST_REQUIRED", error.code());
    }
}
~~~

Bộ kiểm thử xác minh logic, error code và field name của hợp đồng. Nó không tự chứng minh converter JSON, HTTP status hoặc retry của binder hoạt động như mong muốn.

### 16.1. Bổ sung các trường hợp ranh giới

Cần kiểm tra thêm:

- Quantity **1**, **1000** và **1001** để bao phủ biên.
- **requestId** chỉ chứa khoảng trắng; SKU có ký tự lạ hoặc quá 24 ký tự.
- SKU chuẩn hóa hoa/thường, khoảng trắng đầu/cuối.
- Giá sản phẩm có nhiều chữ số thập phân theo chính sách tiền tệ.
- Cùng input có tạo cùng output không, nếu logic được kỳ vọng thuần.
- Input null ở cấp root và từng field có được xử lý thống nhất không.
- Mã lỗi có ổn định qua các lần thay đổi thông điệp hiển thị không.

Không nên viết test chỉ lặp lại implementation mà không kiểm tra bất biến. Ví dụ **quantity = 0** phải bị từ chối vì hợp đồng nêu giới hạn từ 1, không phải đơn thuần vì code đang có điều kiện **quantity <= 0**.

## 17. Kiểm thử integration qua FunctionCatalog và adapter

Để xác minh tên bean **calculateQuote** và việc Spring Cloud Function tìm được hàm, có thể kiểm thử qua application context thật:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class QuoteContractCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogInvokesTypedFunction() {
        Function<
            QuoteContractApplication.QuoteRequest,
            QuoteContractApplication.Quote> fn =
                catalog.lookup("calculateQuote");

        assertNotNull(fn);

        var result = fn.apply(
            new QuoteContractApplication.QuoteRequest(
                "REQ-101", "BOOK", 2)
        );

        assertEquals(new BigDecimal("170000"), result.subtotal());
    }
}
~~~

Integration test cần phiên bản Spring Boot, Spring Cloud Function và Spring Boot Test tương thích. Khi hệ thống thật có adapter, nên kiểm tra riêng:

| Biên cần test | Ví dụ xác minh |
| --- | --- |
| **HTTP** | JSON đúng/sai kiểu, thiếu field, status và error JSON |
| **HTTP controller tự viết** | Error mapping của **InvalidQuoteRequestException** và **QuoteRejectedException** |
| **Stream** | Payload deserialize, input/output binding, retry và dead-letter khi message lỗi |
| **Serverless** | Event envelope, chuyển đổi input, output và lỗi handler |
| **Composition** | **calculateQuote|formatQuote** đi qua đúng kiểu, lỗi dừng đúng bước |
| **Message headers** | Chỉ correlationId cần thiết được giữ, không lộ header nhạy cảm |
| **Schema versioning** | Consumer cũ xử lý được payload mới theo chính sách đã cam kết |

Chỉ kiểm thử các adapter thực sự dùng trong sản phẩm. Không cần khởi tạo broker hoặc runtime serverless chỉ để chạy unit test của **QuoteService**.

## 18. Những lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân | Hướng giải quyết |
| --- | --- | --- |
| Request parse được nhưng vẫn làm hỏng nghiệp vụ | Chỉ kiểm tra JSON, chưa kiểm tra bất biến | Validation theo hợp đồng sau conversion |
| Trường thiếu bị coi là 0 | Dùng primitive khi cần phân biệt null | Dùng kiểu nullable/DTO phù hợp và kiểm tra |
| Output có lúc null, lúc object | Không định nghĩa nhánh “không có kết quả” | Dùng result type/exception có contract rõ |
| HTTP trả status không đúng mong muốn | Tin rằng exception tự được ánh xạ | Thiết kế HTTP adapter và test error mapping |
| Stream retry vô hạn một payload sai | Không phân biệt lỗi vĩnh viễn và tạm thời | Chính sách retry, DLQ, kết quả từ chối |
| Composition lỗi kiểu ở bước sau | Output không khớp input hoặc đổi sang result type | Mô tả và kiểm thử hợp đồng từng bước |
| Client xử lý sai sau khi nâng phiên bản | Đổi field, đơn vị hoặc error code phá vỡ tương thích | Quản lý schema/version và contract tests |
| Log lộ dữ liệu người dùng | Đưa toàn bộ raw payload/exception nội bộ vào message | Chỉ công khai thông điệp an toàn và log có kiểm soát |
| Cùng sự kiện tạo hai tác dụng phụ | Retry/redelivery và thiếu idempotency | Khóa sự kiện, unique constraint/transaction |
| API cho phép đơn giá do người gọi quyết định | Không xác minh dữ liệu quan trọng ở nguồn nội bộ | Tra giá tại service hoặc cổng dữ liệu tin cậy |
| DTO phụ thuộc HttpServletRequest/Kafka record | Trộn hợp đồng nghiệp vụ với giao thức | Dùng DTO Java thuần và adapter chuyển đổi |
| Validation chỉ ở controller HTTP | Stream/serverless gọi bỏ qua điều kiện | Giữ bất biến nghiệp vụ trong phần lõi hoặc validator dùng chung |

## 19. Bài tập thực hành

**Bài tập 1 — Bảng hợp đồng.** Thiết kế **Function<ShippingRequest, ShippingQuote>** nhận mã yêu cầu, khối lượng và khu vực giao. Ghi rõ khối lượng tính theo gram hay kilogram, giới hạn min/max, các trường bắt buộc và điều kiện từ chối.

**Bài tập 2 — Phân loại lỗi.** Cho các trường hợp JSON sai cú pháp, quantity âm, SKU không tồn tại, database timeout và broker gửi lại event. Phân nhóm conversion, validation, business rejection, transient infrastructure và retry/redelivery; đề xuất hành vi HTTP/Stream phù hợp.

**Bài tập 3 — Error contract.** Định nghĩa **ApiError(code, field, message)** và ánh xạ các exception của QuoteService sang HTTP status trong controller riêng. Thêm kiểm thử với request quantity bằng 0 và SKU UNKNOWN.

**Bài tập 4 — Kết quả tường minh.** Chuyển bài toán báo giá sang **Function<QuoteRequest, QuoteDecision>**. Thiết kế JSON schema để consumer phân biệt **accepted** và **declined**, rồi giải thích điều gì sẽ thay đổi nếu hàm được phát kết quả qua broker.

**Bài tập 5 — Composition.** Thêm **Function<Quote, String> formatQuote** rồi cấu hình **calculateQuote|formatQuote**. Dự đoán bước nào chạy khi quantity không hợp lệ và viết unit test xác nhận formatQuote không chạy.

**Bài tập 6 — Schema evolution.** Giả sử input cần thêm **currency**, trước đó client chỉ gửi requestId/sku/quantity. Thiết kế chiến lược tương thích ngược hoặc phiên bản mới; phân biệt thêm một trường tùy chọn với đổi đơn vị tiền không thông báo.

**Bài tập 7 — Stream lỗi dữ liệu.** Với input binding **calculateQuote-in-0**, hãy mô tả cách xử lý một event sai vĩnh viễn và một event tạm thời không thể truy vấn bảng giá. Xác định thông tin quan sát cần lưu cùng correlation ID và lý do không retry vô hạn.

**Bài tập 8 — Kiểm thử ranh giới.** Lập bộ test cho quantity = null, 0, 1, 1000, 1001; SKU rỗng, sai ký tự, không tồn tại; requestId vượt 64 ký tự. Phân biệt unit test service và integration test adapter.

### Ghi nhớ

- **Hợp đồng đầu vào/đầu ra** không chỉ là generic **T → R**, mà còn là schema, ràng buộc, ý nghĩa dữ liệu, error code và hành vi khi không xử lý được.
- **Conversion, validation và từ chối nghiệp vụ** là ba loại tình huống khác nhau; thiết kế và kiểm thử từng ranh giới.
- **Function<T, R>** có thể dùng exception hoặc result type rõ ràng. Không mặc định **null** là một kết quả lỗi an toàn.
- **HTTP, Stream và serverless** cùng gọi logic nghiệp vụ nhưng cách map lỗi, retry và trả kết quả thuộc adapter; cần xác minh theo môi trường thực tế.
- **FunctionCatalog và composition** nối các hàm theo tên và kiểu, vì vậy thay đổi error contract hoặc output type có thể tác động cả pipeline.
- Thiết kế lỗi, version schema và kiểm thử biên giúp một hàm có thể được tái sử dụng an toàn qua nhiều giao thức.
