# Đặt tên bean và sử dụng dependency injection

Trong **SPRING_CLOUD_FUNCTION**, một **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>** thường được đăng ký thành Spring bean. Tên bean giúp **FunctionCatalog** nhận diện logic nào cần chạy; **dependency injection (DI)** giúp logic nhận repository, service, cấu hình và các thành phần hỗ trợ mà không cần tự tạo chúng. Hai cơ chế này quyết định một hàm có thể được tìm thấy, kiểm thử và tái sử dụng qua HTTP, sự kiện hoặc môi trường serverless một cách nhất quán hay không.

Bài thuộc chương **Mô hình hàm**. Trọng tâm là cách đặt tên bean rõ ràng, khai báo và tiêm phụ thuộc đúng, phân biệt tên bean với tên lớp/phương thức Java, lựa chọn hàm trong ứng dụng nhiều bean và tránh lỗi về vòng đời, phụ thuộc vòng hoặc trạng thái dùng chung.

## 1. Spring bean là gì trong mô hình hàm?

**Spring bean** là một đối tượng được Spring application context quản lý. Bean có thể là:

- **Bean nghiệp vụ**: service tính báo giá, repository, lớp truy cập cấu hình, bộ chuẩn hóa dữ liệu.
- **Bean chức năng**: một đối tượng triển khai **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>**.
- **Bean hạ tầng**: message converter, clock, HTTP client hoặc một thành phần hỗ trợ khác.

Một đối tượng Java chỉ được tạo bằng **new** chưa mặc nhiên trở thành Spring bean. Khi đăng ký bean, Spring biết cách khởi tạo, kết nối phụ thuộc và quản lý vòng đời của đối tượng.

~~~mermaid
flowchart LR
    A["PriceBook (bean)"] --> B["QuoteService (bean)"]
    B --> C["createQuote (Function bean)"]
    D["Spring ApplicationContext"] -. "khởi tạo và inject" .-> A
    D -. "khởi tạo và inject" .-> B
    D -. "khởi tạo và inject" .-> C
    C --> E["FunctionCatalog"]
    E --> F["HTTP / Stream / Serverless adapter"]
~~~

Spring Cloud Function tập trung vào **bean chức năng**: tìm các bean có kiểu thích hợp, đăng ký trong **FunctionCatalog**, sau đó để adapter gọi theo tên được chọn. Đặt tên ổn định và kiểm soát phụ thuộc ngay từ khi xây dựng bean làm cho phần xử lý nghiệp vụ độc lập với giao thức.

## 2. Đặt tên bean bằng @Bean

Với cấu hình Java, **@Bean** đăng ký giá trị trả về của phương thức làm một bean:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class SimpleFunctions {

    @Bean
    Function<String, String> normalizeCode() {
        return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Trong trường hợp không ghi tên tường minh, tên bean mặc định là **normalizeCode**, trùng tên phương thức **@Bean**. Khi application context chứa bean này, Spring Cloud Function có thể đăng ký tên **normalizeCode** trong FunctionCatalog.

Có thể chọn tên cụ thể bằng tham số của annotation:

~~~java
@Bean("productCodeNormalizer")
Function<String, String> normalizeCode() {
    return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

Ở cách viết này:

- **Tên phương thức Java**: **normalizeCode**.
- **Tên bean được đăng ký**: **productCodeNormalizer**.
- **Tên dùng để chọn hàm trong FunctionCatalog/adapter**: **productCodeNormalizer**.

**Không suy tên endpoint hoặc tên hàm từ tên lớp chứa @Bean.** Chính tên bean đã đăng ký mới là định danh cần đối chiếu với cấu hình Spring Cloud Function.

Spring cũng cho phép khai báo nhiều tên cho một bean, ví dụ **@Bean({"productCodeNormalizer", "normalizeAlias"})**: tên đầu là tên chính, các tên sau là alias ở cấp Spring container. Tuy nhiên, khi dùng alias để expose FunctionCatalog hoặc adapter, nên kiểm thử việc tra cứu theo alias trên phiên bản thư viện đang chạy. Trong tài liệu và cấu hình triển khai, ưu tiên **một tên chính rõ ràng**.

## 3. Ví dụ thực tế: đưa dịch vụ tính báo giá vào Function

Giả sử ứng dụng nhận một yêu cầu chứa mã sản phẩm và số lượng. **PriceBook** là nguồn đơn giá do hệ thống quản lý; **QuoteService** kiểm tra yêu cầu rồi tính thành tiền. Bean **createQuote** biến logic của service thành hàm có thể được Spring Cloud Function gọi.

Đầu vào và đầu ra:

~~~text
QuoteRequest(requestId, sku, quantity)
             |
             v
     Function<QuoteRequest, Quote>
             |
             v
Quote(requestId, sku, quantity, unitPrice, total)
~~~

Ví dụ mã Java 17+ trong một tệp **NamedFunctionsApplication.java**:

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
public class NamedFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(NamedFunctionsApplication.class, args);
    }

    // DTO của hợp đồng hàm.
    public record QuoteRequest(
        String requestId,
        String sku,
        int quantity
    ) {}

    public record Quote(
        String requestId,
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal total
    ) {}

    // Ví dụ nguồn giá trong bộ nhớ.
    public static final class PriceBook {
        private final Map<String, BigDecimal> prices;

        public PriceBook(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal priceOf(String sku) {
            BigDecimal price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU: " + sku);
            }
            return price;
        }
    }

    // Service nghiệp vụ, không cần biết HTTP hay broker.
    public static final class QuoteService {
        private final PriceBook priceBook;

        public QuoteService(PriceBook priceBook) {
            this.priceBook = priceBook;
        }

        public Quote quote(QuoteRequest request) {
            if (request == null
                    || request.requestId() == null
                    || request.requestId().isBlank()
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            String sku = request.sku()
                .trim().toUpperCase(Locale.ROOT);
            BigDecimal unitPrice = priceBook.priceOf(sku);
            BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
            );

            return new Quote(
                request.requestId(),
                sku,
                request.quantity(),
                unitPrice,
                total
            );
        }
    }

    @Bean
    PriceBook priceBook() {
        return new PriceBook(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    QuoteService quoteService(PriceBook priceBook) {
        return new QuoteService(priceBook);
    }

    // Tên method là quoteFromService;
    // tên Function bean chính thức là createQuote.
    @Bean("createQuote")
    Function<QuoteRequest, Quote> quoteFromService(
            QuoteService quoteService) {
        return quoteService::quote;
    }

    @Bean("renderQuote")
    Function<Quote, String> renderQuote() {
        return quote -> quote.requestId() + ":"
            + quote.total().toPlainString();
    }
}
~~~

Tại đây, Spring tạo **PriceBook**, chuyển nó cho **QuoteService**, rồi tiêm **QuoteService** vào phương thức tạo bean Function. **createQuote** không tự gọi **new QuoteService(...)** và cũng không cần biết **PriceBook** được xây dựng thế nào.

Khi gọi hàm **createQuote** với:

~~~json
{
  "requestId": "REQ-001",
  "sku": "book",
  "quantity": 3
}
~~~

kết quả nghiệp vụ là:

~~~json
{
  "requestId": "REQ-001",
  "sku": "BOOK",
  "quantity": 3,
  "unitPrice": 85000,
  "total": 255000
}
~~~

**PriceBook** trong bài chỉ là dữ liệu mẫu trong bộ nhớ. Với sản phẩm thật, giá phải được lấy từ nguồn có thẩm quyền, có chính sách hiệu lực và quy tắc tiền tệ/làm tròn cụ thể. Hợp đồng Function không thay thế những yêu cầu nghiệp vụ đó.

## 4. Dependency injection hoạt động như thế nào?

Trong ví dụ, **Spring** giải quyết phụ thuộc dựa trên kiểu của tham số phương thức **@Bean**:

~~~java
@Bean
QuoteService quoteService(PriceBook priceBook) {
    return new QuoteService(priceBook);
}

@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService quoteService) {
    return quoteService::quote;
}
~~~

Spring hiểu cần có một bean kiểu **PriceBook** trước khi tạo **QuoteService**. Tương tự, cần có **QuoteService** trước khi tạo bean **createQuote**.

~~~mermaid
flowchart LR
    A["@Bean PriceBook"] --> B["@Bean QuoteService(PriceBook)"]
    B --> C["@Bean createQuote(QuoteService)"]
    C --> D["FunctionCatalog: createQuote"]
    D --> E["apply(QuoteRequest)"]
~~~

Có ba cách tiêm phụ thuộc thường gặp:

| Cách DI | Minh họa | Đánh giá |
| --- | --- | --- |
| **Constructor injection** | **QuoteService(PriceBook priceBook)** | Ưu tiên cho phụ thuộc bắt buộc; dễ tạo đối tượng để kiểm thử |
| **Tham số phương thức @Bean** | **quoteFromService(QuoteService service)** | Phù hợp khi khai báo một Function từ service hiện có |
| **Field injection** | **@Autowired private PriceBook priceBook** | Có thể sử dụng nhưng khiến phụ thuộc ít rõ ràng và khó kiểm thử trực tiếp hơn |

Với class chỉ có một constructor, Spring có thể tự dùng constructor đó để tiêm phụ thuộc mà không cần **@Autowired**. **@Bean** methods cũng có thể khai báo tham số để Spring cấp giá trị. Các bean không nhất thiết phải được tạo theo thứ tự xuất hiện trong file Java; Spring dựa vào đồ thị phụ thuộc.

### Vì sao DI tốt hơn tự tạo phụ thuộc trong hàm?

Ví dụ cần tránh:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteWithHiddenDependency() {
    QuoteService service = new QuoteService(
        new PriceBook(Map.of("BOOK", new BigDecimal("85000")))
    );
    return service::quote;
}
~~~

Code này buộc Function vào cách xây dựng **PriceBook**. Khi cần repository thật, cache, tracing, cấu hình giá hoặc mock để kiểm thử, phải chỉnh ngay trong phương thức tạo Function.

DI cho phép thay **PriceBook** hoặc **QuoteService** ở ranh giới cấu hình, tách trách nhiệm tạo đối tượng khỏi trách nhiệm biến đổi **QuoteRequest → Quote**.

**Lưu ý:** ví dụ trên dùng **@Bean** nhận dependency; nó hoàn toàn có thể nhận repository, gateway hoặc client do Spring quản lý. Không nhất thiết phải tạo mọi dependency dưới dạng class tường minh nếu chỉ cần một bean cấu hình nhỏ.

## 5. Constructor injection với @Component

Ngoài phương thức **@Bean**, có thể tạo một lớp triển khai **Function** và đánh dấu **@Component**.

Ví dụ một lớp riêng trong package **example.function**:

~~~java
package example.function;

import java.util.function.Function;
import org.springframework.stereotype.Component;

@Component("createQuote")
public final class CreateQuoteFunction
        implements Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> {

    private final NamedFunctionsApplication.QuoteService service;

    public CreateQuoteFunction(
            NamedFunctionsApplication.QuoteService service) {
        this.service = service;
    }

    @Override
    public NamedFunctionsApplication.Quote apply(
            NamedFunctionsApplication.QuoteRequest request) {
        return service.quote(request);
    }
}
~~~

Spring sẽ nhận diện **@Component("createQuote")** nếu class nằm trong phạm vi component scan và đưa **QuoteService** vào constructor. Lớp này vẫn là Function có tên **createQuote**, giống mục đích của phương thức **@Bean("createQuote")**.

**Chọn một trong hai hình thức đăng ký.** Khi sử dụng **@Component("createQuote")**, hãy bỏ phương thức **@Bean("createQuote")** tương ứng trong ví dụ chính. Nếu để cả hai, ứng dụng có thể gặp lỗi trùng tên bean hoặc hành vi phụ thuộc cấu hình cho phép ghi đè bean, vốn không nên dùng như một cơ chế chọn triển khai.

Nếu không đặt tên trong **@Component**, tên bean mặc định thường được suy từ tên lớp theo quy tắc của Spring (chẳng hạn **CreateQuoteFunction → createQuoteFunction**). Với tên dành cho adapter hoặc tài liệu API, khai báo tường minh sẽ giảm phụ thuộc vào quy tắc suy tên.

## 6. Phân biệt tên lớp, tên phương thức, tên bean và function definition

Trong ví dụ chính, bốn khái niệm có thể khác nhau:

| Khái niệm | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| Tên lớp chứa cấu hình | **NamedFunctionsApplication** | Tổ chức mã Java |
| Tên phương thức tạo bean | **quoteFromService** | Định nghĩa factory method trong Java |
| Tên bean chức năng | **createQuote** | Định danh trong Spring container và FunctionCatalog |
| Function definition | **createQuote** | Chọn hàm hoặc chuỗi hàm để adapter sử dụng |

Chọn hàm bằng cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
~~~

Không dùng **quoteFromService** làm definition nếu bean đã được đặt tên tường minh là **createQuote**. Việc tên có cùng chữ “quote” không khiến framework tự tìm ra quan hệ thay thế.

Trong một ứng dụng có nhiều Function, Supplier hoặc Consumer, khai báo **spring.cloud.function.definition** rõ ràng giúp tránh chuyện adapter phải suy đoán hàm nào cần được expose hoặc bind.

Đổi tên bean là thay đổi **định danh tích hợp**: cấu hình HTTP, binding sự kiện, composition hoặc serverless handler có thể đang tham chiếu tên cũ. Với dự án đã triển khai, nên xem đổi tên function như thay đổi hợp đồng vận hành và kiểm thử nơi sử dụng.

## 7. Tra cứu bean chức năng qua FunctionCatalog

Spring Cloud Function quản lý việc tra cứu các bean chức năng qua **FunctionCatalog**. Một lớp Spring có thể nhận catalog bằng constructor injection rồi gọi hàm theo tên.

~~~java
package example.function;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class QuoteInvoker {
    private final FunctionCatalog catalog;

    public QuoteInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public NamedFunctionsApplication.Quote run(
            NamedFunctionsApplication.QuoteRequest request) {

        Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> function =
                catalog.lookup("createQuote");

        if (function == null) {
            throw new IllegalStateException(
                "Function 'createQuote' not found");
        }

        return function.apply(request);
    }
}
~~~

Ở đây, **QuoteInvoker** nhận **FunctionCatalog** từ Spring; catalog tra cứu bean đã đăng ký dưới tên **createQuote**. Nếu tên sai hoặc bean không được đăng ký, lời gọi **lookup(...)** có thể không trả được hàm mong muốn.

Đối tượng trả từ catalog có thể được framework **bọc để hỗ trợ conversion, composition và message handling**. Không nên ép nó về lớp cụ thể **CreateQuoteFunction** hay giả định cùng identity với đối tượng bean ban đầu.

**Phân biệt hai kiểu DI:**

- Inject **QuoteService** vào bean Function: cung cấp phụ thuộc cho **logic nghiệp vụ**.
- Inject **FunctionCatalog** vào adapter hoặc lớp điều phối: cung cấp cơ chế **chọn logic theo tên**.

Hai kiểu bổ trợ nhau. Ứng dụng nhỏ có thể gọi Function bean được inject trực tiếp; những thành phần cần tra cứu linh hoạt theo định nghĩa thường dùng FunctionCatalog.

## 8. Nhiều bean cùng kiểu: @Qualifier và @Primary

Khi ứng dụng có nhiều bean cùng một kiểu, DI theo kiểu đơn thuần có thể trở nên mơ hồ.

Giả sử ta bổ sung thêm một cách expose cùng QuoteService trong ví dụ chính:

~~~java
@Bean("previewQuote")
Function<QuoteRequest, Quote> previewQuote(QuoteService service) {
    return service::quote;
}
~~~

Bây giờ có ít nhất hai bean cùng kiểu **Function<QuoteRequest, Quote>**:

~~~text
createQuote  : Function<QuoteRequest, Quote>
previewQuote : Function<QuoteRequest, Quote>
~~~

Nếu một lớp khác muốn inject trực tiếp **một** Function cùng kiểu, hãy đặt **@Qualifier**:

~~~java
package example.function;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public class QuoteUseCase {

    private final Function<
        NamedFunctionsApplication.QuoteRequest,
        NamedFunctionsApplication.Quote> calculator;

    public QuoteUseCase(
            @Qualifier("createQuote")
            Function<
                NamedFunctionsApplication.QuoteRequest,
                NamedFunctionsApplication.Quote> calculator) {
        this.calculator = calculator;
    }

    public NamedFunctionsApplication.Quote execute(
            NamedFunctionsApplication.QuoteRequest input) {
        return calculator.apply(input);
    }
}
~~~

**@Qualifier("createQuote")** chọn bean cụ thể trong Spring DI; **spring.cloud.function.definition=createQuote** lại chọn hàm cho cơ chế tích hợp của Spring Cloud Function.

**@Primary** có thể giúp Spring chọn ứng viên mặc định khi inject theo kiểu nếu có nhiều bean phù hợp. Nhưng **@Primary không thay thế function definition** và không nên dùng nó để suy đoán endpoint/binding nào được chọn.

### Cách xử lý khi có nhiều implementation

| Tình huống | Cách giải quyết |
| --- | --- |
| Hai service cùng interface được inject vào một class | Sử dụng **@Qualifier**, hoặc **@Primary** nếu có default đúng nghĩa |
| Nhiều Function cùng generic input/output | Đặt tên bean rõ ràng; dùng **@Qualifier** khi inject trực tiếp |
| Adapter cần expose đúng một Function | Cấu hình **spring.cloud.function.definition** |
| Muốn lựa chọn implementation theo môi trường | Dùng profile/conditional bean có kiểm soát, và kiểm tra bean thực tế được đăng ký |
| Cần chạy liên tiếp hai Function | Dùng composition, bảo đảm đầu ra/đầu vào tương thích |

**Đừng đánh đồng tên bean với biến Java.** Đặt tên biến **createQuote** trong constructor không bảo đảm giải quyết đúng mọi trường hợp ambiguity; qualifier tường minh là lựa chọn dễ đọc, đặc biệt khi dự án được refactor.

## 9. Composition phụ thuộc tên bean và hợp đồng kiểu

Khi có **createQuote** và **renderQuote** từ ví dụ chính, có thể cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote|renderQuote
~~~

Điều này biểu diễn pipeline:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["createQuote"]
    B --> C["Quote"]
    C --> D["renderQuote"]
    D --> E["String"]
~~~

Bước đầu nhận **QuoteRequest** và trả **Quote**; bước thứ hai nhận **Quote** và trả **String**. Kết quả từ yêu cầu minh họa là chuỗi **REQ-001:255000**.

Spring Cloud Function có thể tra cứu definition dạng composition qua catalog:

~~~java
Function<
    NamedFunctionsApplication.QuoteRequest,
    String> pipeline =
        catalog.lookup("createQuote|renderQuote");

if (pipeline == null) {
    throw new IllegalStateException("Pipeline not found");
}

String text = pipeline.apply(
    new NamedFunctionsApplication.QuoteRequest(
        "REQ-001", "BOOK", 3
    )
);
// "REQ-001:255000"
~~~

Ví dụ này đặt trong ngữ cảnh đã có **FunctionCatalog catalog** do Spring inject cùng các import cần thiết; không phải một file Java độc lập.

**Quy tắc quan trọng:** tên trong composition phải là tên bean hợp lệ, và kiểu output của bước trước phải tương thích với kiểu input của bước tiếp theo. Dependency injection giúp mỗi bean có đủ service cần dùng, nhưng **không tự giải quyết** việc ghép hai kiểu dữ liệu không phù hợp.

Nếu đổi tên bean **renderQuote** thành **formatQuote**, cấu hình pipeline cũng cần đổi. Đây là lý do nên coi tên bean chức năng như một phần của hợp đồng triển khai.

## 10. HTTP: tên bean xác định hàm được expose

Với Spring Cloud Function Web adapter, có thể dùng starter Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Ứng dụng cần Spring Boot/Spring Cloud có phiên bản tương thích, cùng cấu hình web phù hợp. Khi chọn:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
~~~

và chạy ứng dụng tại cổng **8080** mặc định, có thể gọi:

~~~bash
curl -i -X POST http://localhost:8080/createQuote \
  -H "Content-Type: application/json" \
  -d '{"requestId":"REQ-001","sku":"book","quantity":3}'
~~~

Adapter chuyển JSON thành **QuoteRequest**, tìm **createQuote** và gọi **apply(request)**. Kết quả **Quote** có thể được serialize thành JSON.

~~~text
HTTP POST /createQuote
  -> JSON conversion
  -> FunctionCatalog.lookup("createQuote")
  -> createQuote.apply(QuoteRequest)
  -> Quote
  -> HTTP response
~~~

**Tên URL, quy tắc chọn function và cách ánh xạ lỗi** do adapter quyết định, vì vậy cần kiểm tra cấu hình thật. Một **IllegalArgumentException** từ QuoteService không mặc định bảo đảm HTTP 400 trong mọi phiên bản hoặc cấu hình. Logic **QuoteService.quote(...)** nên độc lập với controller, request header hoặc response code.

Không cần tiêm **HttpServletRequest** vào QuoteService chỉ để dùng cùng logic qua HTTP và broker. Các dependency phục vụ nghiệp vụ như price repository hoặc clock vẫn có thể inject bình thường; metadata của một lời gọi riêng nên được truyền qua input/message thích hợp.

## 11. Spring Cloud Stream: cùng bean, tên binding khác

Với **Spring Cloud Stream** và binder phù hợp, cùng bean **createQuote** có thể nhận một sự kiện và xuất kết quả qua broker:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
    stream:
      bindings:
        createQuote-in-0:
          destination: quote-requests
        createQuote-out-0:
          destination: quote-results
~~~

- **createQuote-in-0** là input binding của Function **createQuote**.
- **createQuote-out-0** là output binding.
- **destination** là tên đích logic; ứng dụng còn cần binder, broker và cấu hình kết nối.
- **QuoteService** và **PriceBook** vẫn được Spring inject khi tạo bean, không phụ thuộc message đến từ đâu.

~~~mermaid
flowchart LR
    A["Broker: quote-requests"] --> B["Stream binder"]
    B --> C["createQuote bean"]
    D["QuoteService + PriceBook"] --> C
    C --> E["Broker: quote-results"]
~~~

Khi dùng **composition**, tên binding và quy tắc đặt tên có thể phụ thuộc định nghĩa chuỗi hàm và phiên bản thư viện; không nên dùng nguyên **createQuote-in-0/out-0** mà thiếu xác minh sau khi đổi definition.

**Tác dụng phụ và retry** vẫn là mối quan tâm riêng. Dù bean được DI đúng, broker có thể gửi lại event và môi trường có nhiều instance. Nếu logic ghi dữ liệu hoặc gọi hệ thống ngoài, cần idempotency và transaction ở tầng phù hợp. Thay **@Bean** bằng **@Component** không làm thay đổi đặc tính giao nhận thông điệp.

## 12. Serverless: dependency injection và vòng đời thực thi

Khi đóng gói Spring Cloud Function cho một môi trường serverless, runtime adapter có thể nhận event, chọn function bean và gọi nó. Phần mã:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService quoteService) {
    return quoteService::quote;
}
~~~

vẫn sử dụng mô hình DI của Spring; code nghiệp vụ không cần tự tạo service mỗi lần có invocation.

Tuy nhiên, vòng đời của instance serverless phụ thuộc nền tảng: ứng dụng có thể được khởi tạo lại, tái sử dụng giữa các invocation hoặc chạy song song trên nhiều instance. Không nên coi một field trong singleton bean là nơi lưu giữ trạng thái nghiệp vụ lâu dài.

Cần xác minh **handler**, packaging, dependency, trigger, quyền truy cập và cách chọn tên Function theo adapter đang dùng. Tên **createQuote** trong catalog là một thành phần của cấu hình, nhưng không phải mọi nền tảng serverless tự động sử dụng nó làm tên handler công khai.

## 13. Vòng đời bean và thread safety

Mặc định, phần lớn bean ứng dụng Spring là **singleton trong một application context**. Bean **createQuote** và service được inject có thể được tái sử dụng qua nhiều lần gọi. Vì vậy:

- Ưu tiên **service stateless** và DTO/record bất biến.
- Không lưu request hiện tại vào field của QuoteService.
- Không dựa vào bộ nhớ của singleton để phối hợp nhiều replica.
- Với phụ thuộc là client hay repository có trạng thái, tuân thủ contract thread safety của thành phần đó.

Ví dụ nên tránh:

~~~java
public final class UnsafeQuoteService {
    private String lastRequestId; // Trạng thái dùng chung.

    public void remember(String requestId) {
        lastRequestId = requestId;
    }

    public String lastRequestId() {
        return lastRequestId;
    }
}
~~~

Nếu nhiều HTTP request hoặc message được xử lý đồng thời, field có thể bị ghi đè trước khi một lời gọi đọc xong. Constructor injection không tự biến đối tượng mutable thành thread safe.

**Thời điểm tạo bean cũng khác thời điểm gọi hàm:**

~~~java
@Bean("currentTime")
java.util.function.Supplier<java.time.Instant> currentTime(
        java.time.Clock clock) {
    return clock::instant; // Gọi khi Supplier.get() được kích hoạt.
}
~~~

Bean Supplier được tạo trong lúc khởi tạo context; giá trị thời gian được lấy khi **get()** chạy. Ngược lại, nếu gọi **clock.instant()** trước rồi trả lambda giữ giá trị đó, các lần gọi sau có thể nhận thời gian cũ.

## 14. Những lỗi DI thường gặp

### 14.1. Gọi trực tiếp phương thức @Bean để lấy dependency

Một lỗi dễ xuất hiện khi refactor:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService() {
    QuoteService service = quoteService(priceBook());
    return service::quote;
}
~~~

Đoạn này gọi factory method như phương thức Java thông thường. Hành vi liên quan đến bean container có thể khác tùy cách cấu hình lớp (**@Configuration** có proxy hoặc **proxyBeanMethods = false**), và sẽ khó đọc hơn khi mục tiêu chỉ là inject dependency.

Cách rõ ràng là **nhận bean qua tham số**:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService service) {
    return service::quote;
}
~~~

Spring sẽ cung cấp đúng bean đã được quản lý. Không nên dựa vào gọi nội bộ phương thức **@Bean** như cơ chế DI chính.

### 14.2. Không tìm thấy bean phụ thuộc

Nếu constructor hoặc phương thức **@Bean** yêu cầu **QuoteService**, nhưng application context không có bean tương ứng, Spring thường không thể tạo phụ thuộc và có thể thất bại lúc khởi động.

Cần kiểm tra:

1. Có **@Bean** hoặc **@Component/@Service** đăng ký QuoteService hay chưa?
2. Với **@Component**, class có nằm trong phạm vi quét của Spring hay không?
3. Có bị loại bởi **@Profile**, **@Conditional** hoặc cấu hình môi trường không?
4. Có nhiều bean cùng kiểu mà thiếu **@Qualifier** không?

### 14.3. Phụ thuộc vòng

~~~text
ServiceA cần ServiceB
ServiceB lại cần ServiceA
~~~

Constructor injection sẽ bộc lộ thiết kế phụ thuộc vòng; nhiều ứng dụng Spring Boot mặc định không chấp nhận circular references. Nên tách trách nhiệm hoặc đưa phần dùng chung sang service thứ ba. Không nên chữa bằng cách tùy tiện đổi toàn bộ sang field injection hoặc bật cho phép phụ thuộc vòng.

### 14.4. Trùng tên bean

Nếu hai phương thức cùng đăng ký **@Bean("createQuote")**, Spring có thể từ chối khởi động khi không cho phép bean-definition overriding. Cần đặt tên khác nhau hoặc chỉ giữ một implementation theo profile có kiểm soát.

### 14.5. Dùng @Primary để chọn function cho HTTP

**@Primary** hỗ trợ DI trong Spring container khi có nhiều ứng viên, nhưng không thay thế quy tắc chọn function của Spring Cloud Function. Khi ứng dụng có nhiều hàm, hãy cấu hình **spring.cloud.function.definition** rõ ràng và kiểm thử endpoint hoặc binding tương ứng.

## 15. Đặt tên bean cho code dễ bảo trì

Một số quy ước thực tế:

| Chủ đề | Gợi ý | Ví dụ |
| --- | --- | --- |
| Tên Function | Dùng động từ mô tả phép biến đổi | **createQuote**, **normalizeOrder** |
| Tên Supplier | Diễn tả nguồn dữ liệu | **loadConfiguration**, **generateHeartbeat** |
| Tên Consumer | Diễn tả hành động xử lý | **recordAudit**, **sendNotification** |
| Tên helper service | Diễn tả trách nhiệm nghiệp vụ | **QuoteService**, **PriceBook** |
| Tên trong cấu hình | Khớp tên bean, ổn định qua lần triển khai | **spring.cloud.function.definition: createQuote** |
| Composition | Biểu đạt luồng từ trái sang phải | **createQuote|renderQuote** |

Không cần áp dụng một tiền tố kỹ thuật giống nhau cho tất cả tên bean. Đặt tên ngắn, có ý nghĩa nghiệp vụ và nhất quán với endpoint, binder hoặc handler sẽ giúp người vận hành tra cứu và chẩn đoán dễ hơn.

Nếu đổi tên bean sau khi đã triển khai, rà soát những nơi tham chiếu: **application.yml**, các cấu hình binding, tài liệu tích hợp, HTTP URL, code gọi catalog và kiểm thử. Tên bean là một phần giao diện vận hành, ngay cả khi tên phương thức Java có thể được đổi bằng IDE một cách an toàn.

## 16. Kiểm thử DI và tên bean

Có thể kiểm thử **logic nghiệp vụ không cần Spring** bằng cách tự dựng phụ thuộc:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class NamedFunctionsUnitTest {

    private final NamedFunctionsApplication.PriceBook book =
        new NamedFunctionsApplication.PriceBook(Map.of(
            "BOOK", new BigDecimal("85000")
        ));

    private final NamedFunctionsApplication.QuoteService service =
        new NamedFunctionsApplication.QuoteService(book);

    @Test
    void functionUsesInjectedService() {
        Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> fn =
                new NamedFunctionsApplication()
                    .quoteFromService(service);

        var quote = fn.apply(
            new NamedFunctionsApplication.QuoteRequest(
                "REQ-001", "book", 3
            )
        );

        assertEquals("BOOK", quote.sku());
        assertEquals(0,
            new BigDecimal("255000").compareTo(quote.total()));
    }

    @Test
    void invalidRequestDoesNotProduceQuote() {
        var fn = new NamedFunctionsApplication()
            .quoteFromService(service);

        assertThrows(IllegalArgumentException.class,
            () -> fn.apply(
                new NamedFunctionsApplication.QuoteRequest(
                    "REQ-002", "BOOK", 0
                )
            ));
    }
}
~~~

Hai bài test trên kiểm tra **QuoteService** và đối tượng Function. Chúng **chưa chứng minh** Spring đã đăng ký đúng tên bean hoặc inject dependency trong application context.

Cần bổ sung kiểm thử tích hợp cho trường hợp đó. Ví dụ với **spring-boot-starter-test** và Spring Cloud Function trên test classpath:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class FunctionRegistrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogFindsBeanByExplicitName() {
        assertNotNull(catalog.lookup("createQuote"));
        assertNotNull(catalog.lookup("renderQuote"));
    }
}
~~~

Kiểm thử này đảm bảo Spring context khởi tạo và FunctionCatalog có hai tên bean cần dùng. Để kiểm tra đầy đủ integration, nên gửi một input **QuoteRequest** qua hàm tra cứu và so sánh kết quả; nếu có HTTP hoặc Stream, thêm test cho JSON conversion, endpoint hoặc message binding thực tế.

Khi chỉ cần kiểm tra logic Java, unit test là đủ. Khi cần xác minh **bean discovery, tên hàm, DI và adapter**, integration test là phần không thể thay thế.

## 17. Bài tập thực hành

**Bài tập 1 — Tên mặc định và tên tường minh.** Khai báo hai bean Function kiểu **Function<String, String>**: bean đầu đặt theo tên phương thức **normalizeSku**, bean sau dùng **@Bean("normalizeExternalCode")** nhưng tên phương thức Java là **normalizeCode**. Dự đoán tên nào xuất hiện trong FunctionCatalog; viết integration test kiểm tra.

**Bài tập 2 — Constructor injection.** Tạo **InventoryService** có method **InventoryView getInventory(InventoryRequest request)** và phụ thuộc **InventoryRepository**. Expose nó bằng bean **Function<InventoryRequest, InventoryView>** qua method reference, inject service qua tham số **@Bean**. Không tự gọi **new InventoryRepository(...)** trong lambda.

**Bài tập 3 — Nhiều bean cùng kiểu.** Tạo **Function<OrderRequest, OrderResult>** với tên **validateOrder** và **validateOrderStrict**. Viết một lớp dùng **@Qualifier("validateOrderStrict")** để inject đúng implementation, sau đó phân biệt việc chọn bằng @Qualifier và **spring.cloud.function.definition**.

**Bài tập 4 — Composition theo tên.** Viết **Function<InventoryView, String> renderInventory**, ghép với **getInventory** bằng definition **getInventory|renderInventory**. Giải thích vì sao đổi tên bean nhưng không đổi definition sẽ khiến quá trình tra cứu thất bại.

**Bài tập 5 — Đổi giao thức.** Giữ nguyên **QuoteService** và bean **createQuote**. Cấu hình adapter HTTP để gọi qua POST, rồi mô tả binding input/output cần có khi chuyển sang Spring Cloud Stream. Liệt kê những dependency của nghiệp vụ được Spring inject và những cấu hình chỉ thuộc về adapter.

**Bài tập 6 — Phân tích lỗi.** Một ứng dụng có hai bean Function cùng kiểu, một lớp inject Function mà không có qualifier và cấu hình **spring.cloud.function.definition** lại trỏ tới tên method Java thay vì tên **@Bean**. Hãy xác định hai lỗi độc lập, sửa từng lỗi và thiết kế một integration test cho việc đăng ký tên.

### Ghi nhớ

- **Tên bean** là định danh quan trọng để Spring Cloud Function tra cứu và để adapter chọn hàm; **@Bean("name")** hoặc **@Component("name")** giúp cố định tên.
- **Dependency injection** cấp cho hàm các service, repository và cấu hình cần thiết thông qua constructor hoặc tham số **@Bean**; logic nghiệp vụ không phải tự khởi tạo dependency.
- **@Qualifier** và **@Primary** hỗ trợ chọn bean trong Spring DI, còn **spring.cloud.function.definition** chọn Function hoặc chuỗi Function cho cơ chế tích hợp.
- FunctionCatalog có thể bọc bean để hỗ trợ conversion và composition. Nên tra cứu bằng đúng tên và kiểm thử luồng gọi thực tế.
- DI đúng giúp giữ cùng logic nghiệp vụ tái sử dụng qua **HTTP, sự kiện và serverless**; vẫn cần kiểm soát thread safety, trạng thái, lỗi và ranh giới giao thức.
