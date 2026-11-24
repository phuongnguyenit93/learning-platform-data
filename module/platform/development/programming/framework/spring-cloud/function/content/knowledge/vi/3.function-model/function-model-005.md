# Khai báo hàm bằng lambda, method reference và lớp triển khai

Trong **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ có thể được viết bằng **lambda expression**, **method reference** hoặc **lớp triển khai một functional interface**. Cả ba cách đều có thể tạo ra bean kiểu **Supplier<T>**, **Function<T, R>** hoặc **Consumer<T>** để Spring Cloud Function đăng ký trong **FunctionCatalog**. Sau đó, cùng một logic có thể được gọi qua HTTP, xử lý sự kiện qua Spring Cloud Stream hoặc chạy bằng adapter serverless phù hợp, miễn là hợp đồng dữ liệu và cấu hình tích hợp tương ứng được đáp ứng.

Bài thuộc chương **Mô hình hàm**. Mục tiêu là hiểu khi nào nên chọn mỗi cách khai báo, viết được mã Java đúng kiểu, đặt tên bean ổn định, kiểm thử độc lập với giao thức và tránh những lỗi thường gặp khi ứng dụng có nhiều hàm.

## 1. Ba cách viết, một hợp đồng chức năng

Spring Cloud Function xây dựng trên các functional interface quen thuộc của **java.util.function**:

| Interface | Phương thức chính | Hợp đồng | Vai trò |
| --- | --- | --- | --- |
| **Supplier<T>** | **T get()** | () → T | Tạo hoặc cung cấp dữ liệu |
| **Function<T, R>** | **R apply(T input)** | T → R | Biến đổi dữ liệu |
| **Consumer<T>** | **void accept(T input)** | T → void | Xử lý dữ liệu, thường có tác dụng phụ |

Mỗi interface có đúng một phương thức trừu tượng, nên có thể biểu diễn bằng lambda hoặc method reference. Một lớp cũng có thể **implements** interface để cung cấp cách triển khai tường minh.

Ví dụ Java thuần: cùng phép chuẩn hóa mã bằng ba cú pháp.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class ThreeWaysJavaDemo {
    static class CodeNormalizer {
        String normalize(String input) {
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    static class NormalizeCodeFunction
            implements Function<String, String> {
        @Override
        public String apply(String input) {
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        // 1. Lambda expression
        Function<String, String> lambda =
            input -> input.trim().toUpperCase(Locale.ROOT);

        // 2. Method reference tới phương thức đã có
        CodeNormalizer normalizer = new CodeNormalizer();
        Function<String, String> reference = normalizer::normalize;

        // 3. Lớp triển khai Function
        Function<String, String> implementation =
            new NormalizeCodeFunction();

        System.out.println(lambda.apply(" ab-12 "));         // AB-12
        System.out.println(reference.apply(" ab-12 "));      // AB-12
        System.out.println(implementation.apply(" ab-12 ")); // AB-12
    }
}
~~~

Ba dạng trên tương đương về **mục đích** nhưng khác nhau ở cách tổ chức mã: lambda viết logic tại chỗ; method reference trỏ tới phương thức sẵn có; lớp triển khai đặt hợp đồng, phụ thuộc và phương thức **apply** trong một kiểu Java riêng.

**Điểm phân biệt quan trọng:** biểu thức **normalizer::normalize** tạo một đối tượng hàm để gọi *sau này*, còn **normalizer.normalize(input)** là lời gọi phương thức ngay tại thời điểm thực thi biểu thức. Hai cách không thể thay thế cho nhau khi khai báo bean.

## 2. Chuẩn bị bài toán: tính báo giá từ yêu cầu đặt hàng

Xét một ứng dụng nhận thông tin gồm **orderId**, **quantity** và **unitPrice**, sau đó tính **subtotal**. Ta muốn cùng phép biến đổi xuất hiện dưới ba hình thức khai báo, để người đọc nhìn thấy sự khác biệt ở cú pháp và tổ chức mã.

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["Function<QuoteRequest, Quote>"]
    B --> C["Quote"]
    D["Lambda"] -.-> B
    E["Method reference"] -.-> B
    F["Lớp implements Function"] -.-> B
~~~

Hợp đồng dữ liệu:

- **QuoteRequest** là input kiểu Java rõ ràng, gồm mã đơn, số lượng và đơn giá.
- **Quote** là output, gồm mã đơn và tổng tiền.
- Cả ba kiểu bean đều gọi chung một **QuoteCalculator** để đảm bảo **quy tắc nghiệp vụ giống nhau**; sự khác biệt chỉ nằm ở hình thức khai báo.
- Dùng **BigDecimal** thay vì **double** để tránh sai số biểu diễn nhị phân khi thao tác với số tiền. Ứng dụng thực vẫn cần quy định tiền tệ và làm tròn.

**Lưu ý nghiệp vụ:** ví dụ nhận **unitPrice** từ input để minh họa cấu trúc Function. Với hệ thống bán hàng thực tế, giá tính tiền phải được đối chiếu với nguồn giá có thẩm quyền; không nên tin hoàn toàn giá do client gửi.

## 3. Ví dụ Spring Boot đầy đủ với cả ba cách khai báo

Đoạn mã dưới đây dùng **Java 17+**, Spring Boot và Spring Cloud Function ở các phiên bản tương thích. Mỗi cách là một bean **Function<QuoteRequest, Quote>** có tên riêng, để người học có thể chọn và thử từng bean.

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }

    // Hợp đồng input và output.
    public record QuoteRequest(
        String orderId,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record Quote(
        String orderId,
        BigDecimal subtotal
    ) {}

    // Logic nghiệp vụ dùng chung cho ba cách khai báo.
    public static final class QuoteCalculator {
        public Quote calculate(QuoteRequest request) {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.quantity() <= 0
                    || request.unitPrice() == null
                    || request.unitPrice().signum() < 0) {
                throw new IllegalArgumentException("Invalid quote request");
            }

            BigDecimal subtotal = request.unitPrice()
                .multiply(BigDecimal.valueOf(request.quantity()));

            return new Quote(request.orderId(), subtotal);
        }
    }

    // Cách 3: lớp Java triển khai interface Function.
    public static final class QuoteFunction
            implements Function<QuoteRequest, Quote> {

        private final QuoteCalculator calculator;

        public QuoteFunction(QuoteCalculator calculator) {
            this.calculator = calculator;
        }

        @Override
        public Quote apply(QuoteRequest request) {
            return calculator.calculate(request);
        }
    }

    @Bean
    QuoteCalculator quoteCalculator() {
        return new QuoteCalculator();
    }

    // Cách 1: lambda expression.
    @Bean
    Function<QuoteRequest, Quote> quoteLambda(
            QuoteCalculator calculator) {
        return request -> calculator.calculate(request);
    }

    // Cách 2: method reference của đối tượng được inject.
    @Bean
    Function<QuoteRequest, Quote> quoteMethodRef(
            QuoteCalculator calculator) {
        return calculator::calculate;
    }

    // Cách 3: tạo đối tượng của lớp implements Function.
    @Bean
    Function<QuoteRequest, Quote> quoteClass(
            QuoteCalculator calculator) {
        return new QuoteFunction(calculator);
    }
}
~~~

Đây là **một ứng dụng có ba bean cùng hợp đồng kiểu** nhưng ba tên khác nhau: **quoteLambda**, **quoteMethodRef** và **quoteClass**. Chúng có thể cùng tồn tại trong Spring context; khi sử dụng adapter HTTP hoặc Spring Cloud Stream, cần **chọn tường minh** hàm được expose/bind để tránh cấu hình mơ hồ.

Một lần gọi với input:

~~~json
{
  "orderId": "ORD-1001",
  "quantity": 3,
  "unitPrice": 120000
}
~~~

sẽ cho cùng kết quả về nghiệp vụ:

~~~json
{
  "orderId": "ORD-1001",
  "subtotal": 360000
}
~~~

Mỗi Function gọi **QuoteCalculator.calculate(...)**. Nếu quantity bằng 0, đơn giá âm hoặc mã đơn trống, calculator ném **IllegalArgumentException** trước khi trả về kết quả.

## 4. Cách 1 — Lambda expression trong @Bean

Cách khai báo lambda trong ví dụ chính:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteLambda(
        QuoteCalculator calculator) {
    return request -> calculator.calculate(request);
}
~~~

**Lambda** có dạng **(tham số) -> biểu thức** hoặc **(tham số) -> { khối lệnh }**. Kiểu Java của tham số và kết quả được suy ra từ target type, ở đây là **Function<QuoteRequest, Quote>**.

Ví dụ lambda có nhiều dòng xử lý:

~~~java
Function<String, String> normalize = text -> {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("Empty code");
    }

    return text.trim().toUpperCase(java.util.Locale.ROOT);
};
~~~

Khi nào nên dùng lambda?

- Logic ngắn, trực tiếp và dễ đọc tại nơi khai báo.
- Hàm chỉ cần dùng một hoặc vài dependency được inject vào phương thức **@Bean**.
- Không cần một lớp riêng với API công khai hay nhiều phương thức nội bộ.

Điểm cần lưu ý:

1. **@Bean** chạy khi Spring khởi tạo bean, nhưng **phần thân lambda** thường chỉ chạy khi adapter hoặc người gọi thực sự gọi **apply(...)**. Vì thế **return request -> calculator.calculate(request)** khác với tính sẵn một kết quả tại lúc khởi tạo.
2. Lambda có thể **capture** các biến bên ngoài như **calculator**. Đối tượng được capture vẫn cần an toàn khi nhiều request đồng thời truy cập.
3. Không nên nhét quá nhiều nhánh nghiệp vụ, lời gọi I/O hoặc xử lý lỗi phức tạp trong một lambda dài; tách sang service hoặc lớp chuyên trách thường dễ bảo trì hơn.
4. **Function.apply(...)** không khai báo checked exception. Nếu logic có API ném checked exception, phải xử lý hoặc chuyển đổi lỗi có chủ đích, không thể bỏ qua quy tắc của Java.

Không nên xem lambda là mặc nhiên **pure function**. Một lambda gọi database hoặc thay đổi biến dùng chung vẫn có tác dụng phụ; tính an toàn phụ thuộc logic bên trong, không phụ thuộc cú pháp.

## 5. Cách 2 — Method reference từ phương thức đã có

Method reference có dạng **::**, tạo một hàm trỏ tới phương thức hoặc constructor phù hợp với functional interface đích.

~~~java
@Bean
Function<QuoteRequest, Quote> quoteMethodRef(
        QuoteCalculator calculator) {
    return calculator::calculate;
}
~~~

Phương thức **QuoteCalculator.calculate(QuoteRequest)** nhận đúng **QuoteRequest** và trả **Quote**, nên tham chiếu này tương thích với **Function<QuoteRequest, Quote>**.

Các dạng method reference thông dụng:

| Dạng | Ví dụ Java | Target type minh họa |
| --- | --- | --- |
| **Static method** | **Integer::parseInt** | Function<String, Integer> |
| **Phương thức của instance có sẵn** | **calculator::calculate** | Function<QuoteRequest, Quote> |
| **Phương thức instance của một kiểu** | **String::trim** | Function<String, String> |
| **Constructor reference** | **ArrayList::new** | Supplier<ArrayList<String>> |

Ví dụ Java thuần:

~~~java
import java.util.ArrayList;
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, Integer> parseNumber = Integer::parseInt;
Function<String, String> trimText = String::trim;
Supplier<ArrayList<String>> listFactory = ArrayList::new;

int number = parseNumber.apply("42");
String trimmed = trimText.apply(" a ");
ArrayList<String> values = listFactory.get();
~~~

Đối với **String::trim**, receiver (đối tượng String) được truyền như tham số của Function. Đối với **calculator::calculate**, receiver đã là **calculator** và chỉ còn tham số **QuoteRequest** cần cung cấp.

Method reference đặc biệt phù hợp khi:

- Một service đã có phương thức với chữ ký chính xác.
- Muốn tái sử dụng phương thức nghiệp vụ trong API, batch job, test và Spring Cloud Function.
- Lambda chỉ đơn giản gọi một phương thức khác, ví dụ **input -> service.process(input)**.

Cần tránh hai lỗi phổ biến. Thứ nhất, **return calculator.calculate(...)** là lời gọi tính toán, không phải một function reference. Thứ hai, khi phương thức bị overload hoặc chữ ký trả về không khớp, trình biên dịch có thể không xác định được method reference phù hợp; hãy kiểm tra target type hoặc tạo lambda rõ ràng.

**Method reference không làm nghiệp vụ tự động nhanh hơn lambda.** Nên chọn cách diễn đạt dễ hiểu và đúng hợp đồng kiểu; hiệu năng thực tế phụ thuộc vào logic, I/O và đặc điểm runtime.

## 6. Cách 3 — Lớp implements Function<T, R>

Một lớp triển khai tường minh phương thức **apply(...)**:

~~~java
public static final class QuoteFunction
        implements Function<QuoteRequest, Quote> {

    private final QuoteCalculator calculator;

    public QuoteFunction(QuoteCalculator calculator) {
        this.calculator = calculator;
    }

    @Override
    public Quote apply(QuoteRequest request) {
        return calculator.calculate(request);
    }
}
~~~

Trong ví dụ chính, lớp được tạo thành bean qua:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteClass(
        QuoteCalculator calculator) {
    return new QuoteFunction(calculator);
}
~~~

Ưu điểm của lớp riêng:

- Có thể đặt tên thể hiện trách nhiệm, mô tả hợp đồng và tái sử dụng trong nhiều ngữ cảnh.
- Dễ thêm constructor injection, phương thức nội bộ, kiểm tra điều kiện và tài liệu mã.
- Kiểm thử trực tiếp bằng **new QuoteFunction(calculator)** mà không cần Spring context.
- Thuận tiện khi logic dài, cần thêm nhiều dependency hoặc có quy tắc xử lý lỗi rõ ràng.

Khai báo bằng **@Bean** là một cách đăng ký lớp đã triển khai interface. Một lựa chọn khác là tạo lớp top-level **implements Function<QuoteRequest, Quote>**, đánh dấu **@Component("quoteComponent")** rồi để component scanning đăng ký bean, với điều kiện lớp nằm trong phạm vi quét của Spring. Chỉ dùng **một** cách đăng ký cho cùng tên bean; không đồng thời khai báo **@Component("quoteClass")** và một **@Bean quoteClass(...)** khác rồi dựa vào cơ chế ghi đè bean.

### So sánh ba cách trên cùng một bài toán

| Tiêu chí | Lambda | Method reference | Lớp triển khai |
| --- | --- | --- | --- |
| Cú pháp | **request -> ...** | **calculator::calculate** | **implements Function** |
| Nơi đặt logic | Trong lambda hoặc hàm được gọi | Trong phương thức đã có | Trong **apply(...)** và phương thức hỗ trợ |
| Phù hợp nhất | Xử lý ngắn, đơn giản | Service có chữ ký khớp | Xử lý dài, nhiều trách nhiệm nội bộ |
| Dependency injection | Qua phương thức **@Bean** và biến capture | Inject instance rồi tham chiếu method | Constructor injection hoặc **@Bean** |
| Kiểm thử | Gọi **apply** | Kiểm thử phương thức đích và **apply** | Tạo instance rồi gọi **apply** |
| Tên hàm trong catalog | Tên bean đăng ký | Tên bean đăng ký | Tên bean đăng ký |

Không có yêu cầu phải chọn một kiểu cú pháp duy nhất cho mọi bean trong module. Dùng lambda cho glue code ngắn, method reference để tái sử dụng service sẵn có và lớp triển khai khi bản thân hàm có trách nhiệm đủ lớn để mang tên riêng.

## 7. Vì sao phải khai báo kiểu generic rõ ràng?

Spring Cloud Function cần biết kiểu input/output để nhiều adapter quyết định cách chuyển đổi dữ liệu. Ví dụ:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteLambda(
        QuoteCalculator calculator) {
    return request -> calculator.calculate(request);
}
~~~

Chữ ký trên mô tả **QuoteRequest → Quote**. Nếu thay bằng kiểu thô:

~~~java
// Tránh khai báo thiếu generic trong ứng dụng thực:
@Bean
@SuppressWarnings("rawtypes")
Function ambiguousFunction() {
    return value -> value;
}
~~~

Java vẫn có thể chấp nhận kiểu thô, nhưng thông tin **T** và **R** bị mất hoặc suy giảm, khiến cơ chế chuyển đổi của framework khó biết DTO cần tạo. Để adapter HTTP hoặc message converter xử lý JSON ổn định, ưu tiên các generic cụ thể, các DTO/record có cấu trúc rõ ràng và kiểm thử serialization.

Các biến thể cũng cần đúng interface:

~~~java
@Bean
java.util.function.Supplier<String> greeting() {
    return () -> "hello";
}

@Bean
java.util.function.Consumer<String> printAudit() {
    return System.out::println;
}
~~~

**greeting** là Supplier; **printAudit** là Consumer. Chúng có thể được Spring Cloud Function phát hiện dưới dạng bean chức năng, nhưng cách kích hoạt qua HTTP hoặc Stream khác Function vì một hàm không nhận input, còn một hàm không tạo output. **System.out::println** chỉ thích hợp minh họa; ứng dụng thực nên sử dụng hệ thống logging hoặc audit phù hợp.

## 8. Đặt tên và đăng ký với FunctionCatalog

Spring Cloud Function tìm các bean chức năng trong Spring application context và đưa chúng vào **FunctionCatalog**. Trong ví dụ:

~~~text
quoteLambda      : Function<QuoteRequest, Quote>
quoteMethodRef   : Function<QuoteRequest, Quote>
quoteClass       : Function<QuoteRequest, Quote>
~~~

Dù cách triển khai Java khác nhau, adapter chọn hàm theo **tên bean**, không theo việc đó là lambda, method reference hay instance của lớp.

Khi có nhiều function, nên chọn một hàm rõ ràng:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteMethodRef
~~~

Đổi **quoteMethodRef** thành **quoteLambda** hoặc **quoteClass** nếu muốn thử một phương án khác. Tên trong definition phải khớp với bean thực tế. Có thể đặt tên tường minh ngay trong khai báo:

~~~java
@Bean("quoteApi")
Function<QuoteRequest, Quote> quoteForApi(
        QuoteCalculator calculator) {
    return calculator::calculate;
}
~~~

Trong trường hợp này, tên bean được đăng ký là **quoteApi**. Đây là ví dụ **một bean khác**, không phải tên thay thế tự động cho bean **quoteMethodRef** đã khai báo trước đó.

### Tra cứu hàm theo tên

Một lớp được Spring quản lý có thể nhận **FunctionCatalog** bằng constructor injection:

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

    public QuoteApplication.Quote quote(
            QuoteApplication.QuoteRequest input) {

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> function =
            catalog.lookup("quoteMethodRef");

        if (function == null) {
            throw new IllegalStateException("Quote function not found");
        }

        return function.apply(input);
    }
}
~~~

**QuoteInvoker** là lớp riêng trong cùng package **example.function** với **QuoteApplication**. Catalog có thể trả về hàm đã được framework bọc để phục vụ conversion và composition; vì thế không được giả định kết quả tra cứu luôn có kiểu lớp cụ thể **QuoteFunction**. Unit test nghiệp vụ có thể gọi bean trực tiếp, còn integration test nên xác nhận đường gọi qua catalog hoạt động theo hợp đồng thực tế.

## 9. Gọi hàm qua HTTP mà không thay đổi logic

Để dùng adapter web, dự án cần dependency phù hợp, ví dụ với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Giả sử sử dụng cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteMethodRef
~~~

Khi ứng dụng chạy trên cổng **8080** mặc định và adapter web hoạt động, có thể thử:

~~~bash
curl -i -X POST http://localhost:8080/quoteMethodRef \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-1001","quantity":3,"unitPrice":120000}'
~~~

Phản hồi minh họa:

~~~json
{
  "orderId": "ORD-1001",
  "subtotal": 360000
}
~~~

Dòng dữ liệu:

~~~mermaid
flowchart LR
    A["HTTP POST /quoteMethodRef"] --> B["JSON → QuoteRequest"]
    B --> C["FunctionCatalog"]
    C --> D["quoteMethodRef.apply(request)"]
    D --> E["Quote"]
    E --> F["JSON response"]
~~~

Logic **QuoteCalculator.calculate** vẫn độc lập với đường dẫn HTTP, HTTP headers hay framework controller. Cách mapping lỗi, mã trạng thái và chuyển đổi JSON thuộc về adapter và cấu hình ứng dụng. Ví dụ **IllegalArgumentException** không tự đảm bảo phản hồi **HTTP 400** nếu chưa thiết kế hoặc kiểm tra cơ chế xử lý lỗi tương ứng.

Nếu đổi definition sang **quoteLambda** hoặc **quoteClass**, vẫn dùng cùng payload và kết quả dự kiến; chỉ cần gọi đúng endpoint mà adapter expose theo tên hàm.

## 10. Composition không phụ thuộc cách khai báo

Các bean đều implement **Function<T, R>**, nên có thể tham gia **composition** theo quy tắc đầu ra của bước trước tương thích với đầu vào của bước sau.

Thêm bean định dạng kết quả vào **QuoteApplication**:

~~~java
@Bean
Function<Quote, String> formatQuote() {
    return quote -> quote.orderId() + ":"
        + quote.subtotal().toPlainString();
}
~~~

Khi dùng **Function** với mã trong lớp **QuoteApplication**, kiểu **Quote** được nhận diện trực tiếp vì là record lồng bên trong lớp. Cấu hình chuỗi:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteClass|formatQuote
~~~

Đường xử lý:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["quoteClass"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

Kết quả từ input ví dụ là chuỗi **ORD-1001:360000**. Có thể thay **quoteClass** bằng **quoteLambda** hoặc **quoteMethodRef**, miễn là mỗi bean vẫn trả về **Quote**.

Composition không kiểm tra tên cú pháp Java. Nó dựa trên **hợp đồng kiểu** và cơ chế wrapper/conversion của Spring Cloud Function. Vì thế một **Function<QuoteRequest, Quote>** không thể ghép trực tiếp với **Function<OtherRequest, String>** chỉ nhờ có hai bean cùng là Function.

**Lưu ý cấu hình:** không dùng đồng thời hai giá trị **spring.cloud.function.definition** khác nhau trong cùng một cấu hình hiệu lực mà không có quy tắc ghi đè rõ ràng; hãy chọn một hàm hoặc một pipeline cho adapter.

## 11. Dùng cùng hàm trong luồng sự kiện hoặc serverless

Với **Spring Cloud Stream** và binder phù hợp (Kafka, RabbitMQ hoặc binder khác), một **Function<QuoteRequest, Quote>** có thể nhận sự kiện đầu vào rồi phát kết quả ra một đích khác.

Ví dụ cấu hình cho bean **quoteClass**:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteClass
    stream:
      bindings:
        quoteClass-in-0:
          destination: quote-requests
        quoteClass-out-0:
          destination: quote-results
~~~

**quoteClass-in-0** là binding đầu vào, **quoteClass-out-0** là binding đầu ra của Function. Đây chỉ là cấu hình định tuyến; ứng dụng còn cần dependency Spring Cloud Stream, binder, broker và kết nối đúng.

Trong môi trường này, phần biến đổi vẫn có thể được triển khai bằng lambda, method reference hoặc lớp triển khai; input và output trở thành message payload do binder/converter xử lý. Sự kiện gửi lại, thay đổi schema, retry, partition hoặc transaction là những vấn đề của hệ thống tích hợp, không tự được giải quyết bằng việc đổi cú pháp khai báo Function.

Tương tự, một adapter **serverless** có thể biến event của runtime thành input, tra cứu tên hàm và gọi nó. Việc packaging, handler, trigger, timeout, quyền truy cập và ánh xạ dữ liệu tùy nền tảng. **Cùng mã QuoteCalculator** có thể được tái sử dụng; phần tích hợp vẫn cần cấu hình riêng.

~~~text
                 +-- HTTP adapter --------+
QuoteRequest ----|-- Stream input --------|--> FunctionCatalog
                 +-- Serverless adapter --+          |
                                                    v
                                quoteLambda / quoteMethodRef / quoteClass
                                                    |
                                                    v
                                                  Quote
~~~

Sơ đồ chỉ thể hiện khả năng **chọn từng adapter**, không hàm ý tất cả cùng chạy khi chỉ thêm một dependency.

## 12. Nếu logic cần Message hoặc header thì sao?

Ba cách khai báo không giới hạn Function ở DTO thuần. Nếu cần đọc hoặc sửa metadata, có thể dùng **Message<T>** trong generic signature.

Ví dụ Function bổ sung trong lớp **QuoteApplication**:

~~~java
@Bean
Function<
        org.springframework.messaging.Message<QuoteRequest>,
        org.springframework.messaging.Message<Quote>>
        quoteMessage(QuoteCalculator calculator) {

    return input -> org.springframework.messaging.support.MessageBuilder
        .withPayload(calculator.calculate(input.getPayload()))
        .copyHeaders(input.getHeaders())
        .setHeader("processedBy", "quoteMessage")
        .build();
}
~~~

Đây là **lambda** nhận Message và trả Message. Cách triển khai tương tự có thể là:

- **Method reference** đến một phương thức service có chữ ký **Message<Quote> process(Message<QuoteRequest> input)**.
- **Lớp implements Function<Message<QuoteRequest>, Message<Quote>>** với phương thức **apply(...)**.

Cần cân nhắc chỉ copy những header cần thiết; không mặc định mọi header kỹ thuật hoặc header do client tự gửi được truyền tiếp sang broker hay hệ thống bên ngoài. Với Function chỉ xử lý payload, adapter thường có cơ chế chuyển đổi thông điệp tương ứng; chỉ đưa **Message** vào chữ ký nghiệp vụ khi cần kiểm soát metadata.

## 13. Vòng đời bean, trạng thái và xử lý đồng thời

Các bean singleton thường được Spring tạo một lần rồi sử dụng cho nhiều lời gọi. Điều này áp dụng cho cả lambda, method reference và lớp triển khai.

Ví dụ không an toàn khi nhiều thread gọi đồng thời:

~~~java
@Bean
Function<String, Integer> unsafeCounter() {
    int[] count = {0};
    return input -> ++count[0];
}
~~~

Biến **count** bị capture và có thể cập nhật đồng thời mà không đồng bộ; ngoài ra state nằm trong một instance nên không nhất quán giữa nhiều replica. Nếu yêu cầu là xử lý dữ liệu độc lập, hãy giữ hàm **stateless**. Nếu nghiệp vụ cần trạng thái dùng chung, chọn cơ chế đồng thời và lưu trữ thích hợp; việc đổi sang lớp implements Function không tự khắc phục race condition.

Trong **QuoteApplication**, các bean dùng một **QuoteCalculator** không có mutable state. Mỗi lời gọi tạo **Quote** mới từ input nên thích hợp để tái sử dụng đồng thời.

Một lỗi khác là tính sẵn kết quả ở thời điểm khởi tạo:

~~~java
@Bean
java.util.function.Supplier<java.time.Instant> startupTime() {
    java.time.Instant value = java.time.Instant.now();
    return () -> value;
}
~~~

Supplier trên luôn trả thời điểm lúc tạo bean. Khi muốn lấy thời gian ở **mỗi lần get()**, viết:

~~~java
@Bean
java.util.function.Supplier<java.time.Instant> currentTime() {
    return java.time.Instant::now;
}
~~~

Ví dụ này cho thấy **vị trí thực thi** quan trọng hơn hình thức lambda hay method reference. Với thời gian cần unit test ổn định, có thể inject **Clock** và dùng **clock::instant**.

## 14. Lỗi thường gặp khi khai báo bean chức năng

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Spring không tìm thấy tên hàm | Đặt tên bean và **function.definition** không khớp | Kiểm tra **@Bean**, tên method và definition |
| Có nhiều bean nên adapter chọn sai hoặc không rõ hàm | Chưa chọn function definition | Cấu hình rõ tên hoặc composition |
| Method reference không biên dịch | Chữ ký, số tham số, kiểu trả về hoặc overload không khớp | Kiểm tra target type, thử lambda rõ ràng |
| JSON không chuyển thành DTO | Generic bị mất, payload/content type không hợp lệ | Khai báo **Function<Input, Output>** cụ thể, kiểm tra converter |
| Bean được tạo nhưng logic chạy sớm bất ngờ | Gọi service ngay khi tạo bean thay vì trả lambda/reference | Phân biệt **service.method(...)** và **service::method** |
| Unit test Java qua nhưng HTTP lỗi | Chưa kiểm tra adapter, conversion hoặc mapping exception | Thêm integration test ở ranh giới thật |
| Hai tên bean trùng nhau | Vừa **@Component** vừa **@Bean** cùng tên | Dùng một cách đăng ký hoặc đặt tên phân biệt |
| Lỗi khi nhiều request đồng thời | Lambda capture state mutable hoặc class có field thay đổi | Dùng logic stateless, immutable, đồng bộ đúng mức |
| Chuyển sang Stream nhưng không thấy message | Chưa có binder/broker, sai binding hoặc definition | Kiểm tra dependency, destination, in-0/out-0 |
| Muốn Consumer tạo output nhưng không có kết quả | Chọn **Consumer<T>** có chữ ký void | Chọn **Function<T, R>** nếu cần dữ liệu đầu ra |

**Đừng đánh giá sự đúng đắn dựa vào code ngắn hơn.** Một method reference một dòng vẫn có thể gọi một phương thức chứa I/O chặn, side effect hoặc logic phức tạp. Kiểu khai báo chỉ quyết định cách biểu diễn một hành vi; hành vi và chính sách lỗi nằm ở implementation.

## 15. Kiểm thử ba cách khai báo

Unit test của hàm nên gọi **apply(...)** trực tiếp. Với ví dụ **QuoteApplication**, ta có thể kiểm tra ba cách trả kết quả giống nhau và cùng tuân thủ quy tắc validation.

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class QuoteApplicationTest {

    private final QuoteApplication app = new QuoteApplication();

    private final QuoteApplication.QuoteCalculator calculator =
        app.quoteCalculator();

    private QuoteApplication.QuoteRequest request(int quantity) {
        return new QuoteApplication.QuoteRequest(
            "ORD-1001", quantity, new BigDecimal("120000")
        );
    }

    @Test
    void threeDeclarationsReturnTheSameBusinessResult() {
        var input = request(3);
        var expected = new QuoteApplication.Quote(
            "ORD-1001", new BigDecimal("360000")
        );

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> lambda =
            app.quoteLambda(calculator);

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> methodRef =
            app.quoteMethodRef(calculator);

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> classBased =
            app.quoteClass(calculator);

        assertEquals(expected, lambda.apply(input));
        assertEquals(expected, methodRef.apply(input));
        assertEquals(expected, classBased.apply(input));
    }

    @Test
    void invalidQuantityIsRejectedByAllThree() {
        var invalid = request(0);

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteLambda(calculator).apply(invalid));

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteMethodRef(calculator).apply(invalid));

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteClass(calculator).apply(invalid));
    }
}
~~~

Bài test thứ nhất kiểm tra phép biến đổi **QuoteRequest → Quote**; bài thứ hai kiểm tra input không hợp lệ. Cả hai chỉ kiểm thử **logic Java** và cách wiring của ba dạng chức năng.

Với ứng dụng thật, nên có thêm integration test phù hợp phạm vi triển khai:

1. Spring application context tạo đủ ba bean và **FunctionCatalog.lookup(...)** tra cứu được đúng tên.
2. Adapter HTTP chuyển JSON thành **QuoteRequest** và tạo response đúng định dạng.
3. Composition **quoteClass|formatQuote** nhận input và cho output kiểu String mong đợi.
4. Adapter Stream ánh xạ payload/schema và binding **in-0/out-0** theo broker đang dùng.
5. Error mapping, retry và metadata hoạt động theo hợp đồng kênh truyền tải.

Không cần chạy cả HTTP, broker và serverless khi một sản phẩm chỉ dùng một giao thức. Chọn kiểm thử tích hợp dựa trên những adapter thực sự triển khai.

## 16. Hướng dẫn chọn cách khai báo trong dự án

Có thể dùng các câu hỏi sau trước khi viết bean:

| Tình huống | Cách thường dễ bảo trì |
| --- | --- |
| Một biểu thức biến đổi ngắn, chỉ cần một dependency | Lambda |
| Service đã có phương thức xử lý đúng input/output | Method reference |
| Xử lý nhiều nhánh, nhiều helper, chính sách lỗi riêng | Lớp implements Function |
| Muốn tái sử dụng logic ngoài Spring Cloud Function | Method reference hoặc lớp độc lập, nhưng lambda gọi service cũng phù hợp |
| Cần kiểm thử riêng quy tắc nghiệp vụ | Tách logic thành service/POJO trước, rồi chọn cách khai báo phù hợp |
| Có nhiều function trong một ứng dụng | Đặt tên bean rõ ràng và cấu hình function definition |
| Muốn xử lý message metadata | Dùng generic **Message<T>** khi cần, bất kể cú pháp khai báo |

Một mẫu thiết kế dễ hiểu là **giữ quy tắc nghiệp vụ trong service thuần**, rồi tạo bean Function bằng lambda hoặc method reference để expose service đó. Khi một hàm trở nên đủ phức tạp, lớp triển khai độc lập có thể giúp tổ chức logic rõ hơn. Không có yêu cầu ép mọi dự án dùng một kiểu duy nhất.

## 17. Bài tập thực hành

**Bài tập 1 — So sánh cú pháp.** Tạo ba bean **normalizeLambda**, **normalizeReference** và **normalizeClass** cùng kiểu **Function<String, String>** để chuẩn hóa chuỗi mã sản phẩm. Viết unit test dùng cùng ba input để so sánh kết quả và lỗi.

**Bài tập 2 — Dependency injection.** Tạo service **TaxCalculator** có phương thức **TaxQuote calculate(TaxRequest request)**. Expose qua **TaxCalculator::calculate** ở bean Function, và giải thích sự khác biệt giữa **calculator::calculate** với **request -> calculator.calculate(request)**.

**Bài tập 3 — FunctionCatalog.** Khai báo ba bean cùng input/output. Dùng **catalog.lookup("normalizeReference")** rồi gọi **apply(...)**. Thử đổi tên bean hoặc definition sai và mô tả biểu hiện lỗi.

**Bài tập 4 — Composition.** Tạo thêm **Function<TaxQuote, String>** để định dạng kết quả, cấu hình **calculateTax|formatTax**. Viết sơ đồ kiểu dữ liệu đầu vào/đầu ra của từng bước và kiểm thử pipeline qua catalog.

**Bài tập 5 — Từ HTTP sang sự kiện.** Chọn một trong ba bean tính báo giá, chạy thử HTTP POST rồi mô tả cách cấu hình Spring Cloud Stream để nhận và phát message. Xác định những thứ phải thay đổi ở tầng adapter và giải thích vì sao logic **QuoteCalculator** vẫn dùng được.

**Bài tập 6 — Xử lý đồng thời.** Tạo một lambda capture biến đếm mutable rồi phân tích vì sao có race condition nếu hai thread gọi **apply(...)**. Đề xuất cách loại bỏ state hoặc dùng concurrency control đúng khi trạng thái là yêu cầu nghiệp vụ.

### Ghi nhớ

- **Lambda**, **method reference** và **lớp implements Function** là ba cách biểu diễn logic theo cùng hợp đồng **Function<T, R>** trong Java.
- Spring Cloud Function quản lý các đối tượng đó khi chúng được đăng ký làm bean chức năng; **FunctionCatalog** và adapter chọn theo **tên bean**, không theo cú pháp.
- Duy trì **kiểu generic cụ thể** để hỗ trợ conversion, composition và kiểm thử; dùng **spring.cloud.function.definition** khi cần chỉ định hàm hoặc pipeline.
- Chọn cách khai báo dựa trên độ phức tạp và khả năng bảo trì. **Không có hình thức nào tự bảo đảm stateless, thread safety, idempotency hoặc xử lý lỗi**.
- Cùng logic có thể chạy qua **HTTP**, **Spring Cloud Stream** hoặc **serverless** khi có dependency, adapter và cấu hình đúng; phần nghiệp vụ nên độc lập với giao thức.
