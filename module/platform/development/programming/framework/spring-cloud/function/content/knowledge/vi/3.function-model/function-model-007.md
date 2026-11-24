# Hàm không phụ thuộc Spring và lớp điều hợp bên ngoài

Một mục tiêu quan trọng của **SPRING_CLOUD_FUNCTION** là viết logic nghiệp vụ bằng **Supplier**, **Function** hoặc **Consumer** mà không buộc logic đó biết ai đang gọi mình: HTTP endpoint, message broker, scheduler hay serverless runtime. Có thể triển khai logic bằng **Java thuần**, sau đó dùng một **lớp điều hợp (adapter)** để đăng ký nó thành Spring bean và kết nối với **FunctionCatalog**. Nhờ vậy, cùng một phép tính hay quy tắc nghiệp vụ có thể được gọi trực tiếp trong unit test, dùng qua HTTP hoặc xử lý sự kiện mà không phải viết lại.

Bài thuộc chương **Mô hình hàm**, tập trung vào **ranh giới phụ thuộc**: những gì nên nằm trong hàm nghiệp vụ độc lập với Spring, những gì nên nằm ở adapter và cách đưa hai phần lại với nhau bằng dependency injection.

## 1. Hiểu đúng “hàm không phụ thuộc Spring”

Một lớp nghiệp vụ được xem là không phụ thuộc Spring khi mã nguồn và hợp đồng của lớp không cần sử dụng API của Spring để thực thi. Ví dụ, lớp có thể dùng:

- Kiểu dữ liệu Java như **String**, **BigDecimal**, **record** hoặc **List**.
- **java.util.function.Function<T, R>**, **Supplier<T>** hoặc **Consumer<T>**.
- Constructor để nhận các phụ thuộc được mô tả bằng interface Java thuần.
- Những thư viện nghiệp vụ trung lập với framework khi thực sự cần.

Trong phần lõi đó, không cần **@Component**, **@Service**, **@Bean**, **ApplicationContext**, **HttpServletRequest**, **Message** của Spring Messaging hoặc API của broker.

~~~mermaid
flowchart LR
    A["HTTP request"] --> D["HTTP adapter"]
    B["Broker event"] --> E["Stream adapter"]
    C["Serverless invocation"] --> F["Serverless adapter"]
    D --> G["FunctionCatalog"]
    E --> G
    F --> G
    G --> H["Function<T, R> Java thuần"]
    H --> I["Kết quả R"]
~~~

**Không phụ thuộc Spring không có nghĩa là không có phụ thuộc nào.** Logic vẫn có thể cần chính sách tính thuế, đồng hồ hoặc một cổng truy cập dữ liệu. Điểm quan trọng là **hợp đồng của các phụ thuộc này thuộc về phần lõi hoặc Java**, còn cách tạo và kết nối phụ thuộc thuộc về môi trường bên ngoài.

Đặc biệt, tránh hiểu rằng chỉ cần trả về một đối tượng **Function** là ứng dụng tự có endpoint HTTP, kết nối Kafka và handler serverless. Mỗi cơ chế gọi cần **adapter, dependency và cấu hình** phù hợp.

## 2. Phân biệt hàm nghiệp vụ, adapter và hạ tầng

Có thể nhìn hệ thống theo ba lớp trách nhiệm:

| Thành phần | Trách nhiệm | Những thứ nên biết |
| --- | --- | --- |
| **Lõi nghiệp vụ** | Kiểm tra quy tắc, tính toán, biến đổi input thành output | DTO/record, interface Java, quy tắc nghiệp vụ |
| **Lớp điều hợp Spring** | Tạo bean, inject dependency, chọn tên Function, ánh xạ metadata khi cần | Spring configuration, FunctionCatalog, Message |
| **Adapter giao thức/hạ tầng** | Nhận/gửi HTTP, event, serverless invocation, chuyển đổi dữ liệu | HTTP, binder, broker, runtime, serialization |

Hướng phụ thuộc mong muốn:

~~~mermaid
flowchart TB
    A["HTTP / Stream / Serverless adapter"] --> B["Spring Function binding"]
    B --> C["Lõi Java thuần"]
    D["Adapter cơ sở dữ liệu hoặc API"] --> E["Interface cổng của lõi"]
    C --> E
~~~

Adapter **biết** các kiểu dữ liệu của lõi để chuyển tiếp lời gọi; lõi **không cần biết** adapter nào sẽ được triển khai.

Mô hình này thường được mô tả bằng khái niệm **ports and adapters**. Spring Cloud Function cung cấp một điểm tích hợp thuận tiện cho các chức năng Java, nhưng vẫn cần thiết kế rõ các cổng và ranh giới dữ liệu để giữ tính độc lập thực chất.

## 3. Ví dụ lõi Java thuần: tính báo giá có thuế

Giả sử một dịch vụ cần nhận mã báo giá và số tiền trước thuế, sau đó trả về tiền thuế và tổng tiền. Đây là một biến đổi rõ ràng:

~~~text
QuoteRequest(orderId, netAmount)
          |
          v
Function<QuoteRequest, Quote>
          |
          v
Quote(orderId, netAmount, taxAmount, total)
~~~

Để tập trung vào kiến trúc, ví dụ dùng **thuế suất cố định 10%** do adapter cung cấp bằng cấu hình. Trong ứng dụng thật, thuế suất có thể phụ thuộc loại hàng, khu vực hoặc thời điểm hiệu lực; các quy tắc này cần một mô hình nghiệp vụ và nguồn dữ liệu thích hợp.

### 3.1. Một tệp Java chỉ chứa logic nghiệp vụ

Tệp **QuoteCore.java**:

~~~java
package example.core;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.function.Function;

public final class QuoteCore {

    private QuoteCore() {
    }

    public record QuoteRequest(
        String orderId,
        BigDecimal netAmount
    ) {}

    public record Quote(
        String orderId,
        BigDecimal netAmount,
        BigDecimal taxAmount,
        BigDecimal total
    ) {}

    public record TaxPolicy(BigDecimal rate) {
        public TaxPolicy {
            if (rate == null
                    || rate.signum() < 0
                    || rate.compareTo(BigDecimal.ONE) > 0) {
                throw new IllegalArgumentException(
                    "Tax rate must be between 0 and 1");
            }
        }
    }

    public static final class Calculator
            implements Function<QuoteRequest, Quote> {

        private final TaxPolicy policy;

        public Calculator(TaxPolicy policy) {
            if (policy == null) {
                throw new IllegalArgumentException(
                    "TaxPolicy is required");
            }
            this.policy = policy;
        }

        @Override
        public Quote apply(QuoteRequest request) {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.netAmount() == null
                    || request.netAmount().signum() < 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            BigDecimal net;
            try {
                net = request.netAmount().setScale(
                    2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                    "Amount must have at most two decimal places", ex);
            }

            BigDecimal tax = net.multiply(policy.rate())
                .setScale(2, RoundingMode.HALF_UP);

            return new Quote(
                request.orderId(),
                net,
                tax,
                net.add(tax)
            );
        }
    }
}
~~~

Điều cần nhận ra:

1. Mã lõi chỉ import **java.math** và **java.util.function**.
2. **Calculator** implement **Function<QuoteRequest, Quote>**, nên có thể gọi **apply(...)** trực tiếp.
3. **TaxPolicy** đến từ constructor, không đến từ **@Autowired**, **Environment** hoặc thuộc tính Spring.
4. Mỗi lời gọi tạo một **Quote** mới; không sửa một đối tượng trạng thái dùng chung.
5. Quy tắc làm tròn minh họa được nêu tường minh: đầu vào phải biểu diễn chính xác tới hai chữ số thập phân; tiền thuế làm tròn **HALF_UP** tới hai chữ số.

Lớp **QuoteCore** là nơi gom các kiểu của ví dụ để có thể sao chép trong một tệp. Trong dự án lớn, **QuoteRequest**, **Quote**, **TaxPolicy** và **Calculator** thường được tách thành các tệp riêng, vẫn thuộc package lõi và không cần thư viện Spring.

## 4. Chạy lõi Java mà không khởi động Spring

Vì **Calculator** là một lớp Java bình thường, có thể tạo và gọi trực tiếp:

~~~java
package example.core;

import java.math.BigDecimal;

public class PlainJavaDemo {
    public static void main(String[] args) {
        QuoteCore.TaxPolicy policy =
            new QuoteCore.TaxPolicy(new BigDecimal("0.10"));

        QuoteCore.Calculator calculator =
            new QuoteCore.Calculator(policy);

        QuoteCore.Quote quote = calculator.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        System.out.println(quote.total()); // 110.00
    }
}
~~~

Không có ApplicationContext, HTTP server, broker hay function adapter trong đoạn mã này. Đây là bằng chứng trực tiếp rằng quy tắc tính thuế **không bắt buộc** phải chạy dưới Spring.

Một đặc điểm hữu ích là **đầu vào và đầu ra vẫn là Java record có kiểu rõ ràng**. Adapter chỉ cần biết cách tạo **QuoteRequest** từ giao thức bên ngoài và cách biểu diễn **Quote** trong phản hồi.

## 5. Lớp điều hợp: đăng ký hàm thuần thành Spring bean

Spring Cloud Function cần một **Spring bean chức năng** để đăng ký vào **FunctionCatalog**. Lớp điều hợp thực hiện việc này mà không phải thêm annotation Spring vào **QuoteCore**.

Tệp **QuoteFunctionConfiguration.java** nằm ở phần ứng dụng Spring:

~~~java
package example.adapter.spring;

import java.math.BigDecimal;
import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QuoteFunctionConfiguration {

    @Bean
    QuoteCore.TaxPolicy taxPolicy(
            @Value("${app.tax-rate:0.10}") String rawRate) {
        return new QuoteCore.TaxPolicy(new BigDecimal(rawRate));
    }

    @Bean("calculateQuote")
    Function<QuoteCore.QuoteRequest, QuoteCore.Quote>
            calculateQuote(QuoteCore.TaxPolicy policy) {
        return new QuoteCore.Calculator(policy);
    }

    @Bean("formatQuote")
    Function<QuoteCore.Quote, String> formatQuote() {
        return quote -> quote.orderId()
            + ": " + quote.total().toPlainString();
    }
}
~~~

Để Spring Boot quét được lớp cấu hình, đặt lớp này dưới package được quét hoặc import tường minh trong ứng dụng khởi động. Ví dụ entrypoint:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FunctionApplication {
    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }
}
~~~

Với cấu trúc **example.FunctionApplication**, Spring Boot mặc định quét các package con như **example.adapter.spring**. **QuoteCore** không cần component scan: đây là mã Java được cấu hình Spring tạo bằng **new QuoteCore.Calculator(policy)**.

Trong đoạn cấu hình:

- **@Value** thuộc adapter, đọc chuỗi cấu hình **app.tax-rate**; lõi chỉ nhận **TaxPolicy**.
- **@Bean("calculateQuote")** đặt tên hàm rõ ràng để các adapter tra cứu.
- **Function<QuoteRequest, Quote>** giữ thông tin generic; framework có thể dựa vào kiểu này để thực hiện conversion.
- **formatQuote** là bước xử lý khác, dùng khi cần kết hợp hàm; nó không thay đổi mã tính thuế.

Có thể cấu hình thuế suất:

~~~yaml
app:
  tax-rate: "0.10"

spring:
  cloud:
    function:
      definition: calculateQuote
~~~

**Lưu ý:** khi một ứng dụng có nhiều bean Function như **calculateQuote** và **formatQuote**, chọn **spring.cloud.function.definition** tường minh để adapter biết hàm cần sử dụng. Thuộc tính **app.tax-rate** chỉ là cấu hình ví dụ do ứng dụng tự định nghĩa, không phải thuộc tính đặc biệt của Spring Cloud Function.

## 6. Dependency injection nằm ở đâu?

**Dependency injection (DI)** cung cấp đối tượng mà một lớp cần, thay vì buộc lớp tự khởi tạo phụ thuộc. Trong ví dụ:

~~~text
app.tax-rate = "0.10"
       |
       v
Spring @Bean taxPolicy
       |
       v
new QuoteCore.Calculator(policy)
       |
       v
Spring @Bean("calculateQuote")
       |
       v
FunctionCatalog
~~~

Đây là **constructor injection bằng Java thuần**, được nối dây bằng Spring bên ngoài. Calculator không cần biết ai gọi constructor; một bài unit test cũng có thể cấp **TaxPolicy** theo cách tương tự.

Đặt đoạn tạo **TaxPolicy** ở adapter có một lợi ích quan trọng: khi thay cấu hình từ YAML sang biến môi trường, configuration server hoặc secret store, **QuoteCore** có thể giữ nguyên. Nếu quy tắc thuế thay đổi về bản chất, mới cần điều chỉnh logic nghiệp vụ hoặc mô hình chính sách tương ứng.

Không nên đọc trực tiếp **System.getenv(...)** bên trong **apply(...)** hay inject **Environment** vào lõi chỉ để lấy tax rate. Điều đó làm logic phụ thuộc cấu hình lúc chạy, khó tái hiện kết quả và khó kiểm thử riêng.

## 7. Đặt tên bean và FunctionCatalog

Spring Cloud Function phát hiện các bean **Supplier**, **Function** và **Consumer**, rồi cung cấp cách tra cứu qua **FunctionCatalog**. Tên **calculateQuote** là tên bean do annotation **@Bean** quy định; nó không nhất thiết trùng tên lớp **QuoteCore.Calculator**.

~~~mermaid
flowchart LR
    A["QuoteCore.Calculator"] --> B["@Bean calculateQuote"]
    B --> C["FunctionCatalog"]
    C --> D["HTTP adapter"]
    C --> E["Stream adapter"]
    C --> F["Serverless adapter"]
~~~

Một lớp Spring có thể tra cứu tên hàm qua catalog:

~~~java
package example.adapter.spring;

import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class QuoteInvoker {

    private final FunctionCatalog catalog;

    public QuoteInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public QuoteCore.Quote invoke(QuoteCore.QuoteRequest input) {
        Function<QuoteCore.QuoteRequest, QuoteCore.Quote> fn =
            catalog.lookup("calculateQuote");

        if (fn == null) {
            throw new IllegalStateException(
                "Function 'calculateQuote' not found");
        }

        return fn.apply(input);
    }
}
~~~

**QuoteInvoker** là mã của adapter Spring và có thể sử dụng constructor injection. **QuoteCore.Calculator** không cần biết **FunctionCatalog** tồn tại.

Catalog có thể cung cấp **wrapper** hỗ trợ conversion, composition và xử lý message; không nên ép đối tượng tra cứu về kiểu lớp **Calculator**. Bên trong logic Java thuần, vẫn có thể dùng trực tiếp **Calculator.apply(...)** như đã minh họa.

## 8. Dùng cùng hàm qua HTTP

Để đưa hàm **calculateQuote** ra HTTP, ứng dụng cần adapter web tương thích. Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Phiên bản Spring Cloud Function/Spring Boot cần được quản lý bằng bộ phiên bản tương thích với dự án. Khi ứng dụng dùng cổng mặc định **8080** và cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
~~~

có thể gửi:

~~~bash
curl -i -X POST http://localhost:8080/calculateQuote \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-101","netAmount":100.00}'
~~~

Ví dụ kết quả JSON:

~~~json
{
  "orderId": "ORD-101",
  "netAmount": 100.00,
  "taxAmount": 10.00,
  "total": 110.00
}
~~~

Dòng xử lý là:

~~~text
HTTP JSON body
  -> Web adapter / message conversion
  -> QuoteRequest
  -> FunctionCatalog: calculateQuote
  -> Calculator.apply(QuoteRequest)
  -> Quote
  -> JSON response
~~~

Trong lõi không có **HttpServletRequest**, **ResponseEntity**, route hoặc status code. Các chi tiết đó thuộc HTTP adapter. Nếu **apply(...)** ném **IllegalArgumentException**, không nên mặc định adapter sẽ trả mã HTTP 400 trong mọi phiên bản; ứng dụng cần kiểm tra và thiết kế error mapping phù hợp.

**Ranh giới có trách nhiệm riêng:** converter nhận JSON hợp lệ về mặt cú pháp, còn **Calculator** thực hiện validation nghiệp vụ. Một JSON có số tiền âm có thể deserialize thành **QuoteRequest** hợp lệ về mặt kiểu Java nhưng sẽ bị Calculator từ chối theo quy tắc nghiệp vụ.

## 9. Dùng cùng hàm qua sự kiện với Spring Cloud Stream

Nếu ứng dụng cần nhận sự kiện yêu cầu báo giá rồi phát sự kiện kết quả, có thể giữ nguyên **QuoteCore** và **QuoteFunctionConfiguration**, thay cách tích hợp bằng Spring Cloud Stream cùng binder thích hợp.

Ví dụ cấu hình:

~~~yaml
app:
  tax-rate: "0.10"

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

Ở đây:

- **calculateQuote-in-0** là input binding của Function.
- **calculateQuote-out-0** là output binding.
- **destination** định danh đích logic của broker.
- Cần dependency Spring Cloud Stream, binder tương ứng, broker khả dụng và cấu hình kết nối.

~~~mermaid
flowchart LR
    A["Topic/Queue quote-requests"] --> B["Stream binder"]
    B --> C["QuoteRequest"]
    C --> D["calculateQuote.apply"]
    D --> E["Quote"]
    E --> F["Stream binder"]
    F --> G["Topic/Queue quote-results"]
~~~

Điều thay đổi là **lớp adapter**, định dạng message và cấu hình vận hành. Đoạn **Calculator.apply(...)** không thay đổi. Từ góc nhìn nghiệp vụ, nó vẫn thực hiện phép biến đổi **QuoteRequest → Quote**.

Đừng nhầm **thay adapter** với **đảm bảo giao nhận**. Khi dùng broker, message có thể bị gửi lại do retry hoặc redelivery; cơ chế ack, dead-letter, partition và ordering phụ thuộc binder. Với phép tính thuần ở ví dụ, việc tính lại cùng input ít gây rủi ro hơn một Consumer ghi database hoặc gọi hệ thống thanh toán. Nếu biến Function thành hàm có tác dụng phụ, cần kiểm soát idempotency và giao dịch riêng.

## 10. Dùng cùng hàm trong môi trường serverless

Một adapter serverless có thể nhận invocation từ nền tảng, chuyển event thành input phù hợp và gọi Function trong catalog:

~~~text
Serverless event
   -> runtime adapter
   -> QuoteRequest
   -> FunctionCatalog.lookup("calculateQuote")
   -> Calculator.apply(...)
   -> Quote
   -> kết quả do runtime adapter chuyển đổi
~~~

Logic trong **QuoteCore** vẫn không cần import API của AWS Lambda hoặc một nhà cung cấp khác. Tuy vậy, việc chạy thực tế phụ thuộc nền tảng:

- Handler/adapter và dependency của runtime.
- Cách đóng gói và khởi tạo Spring application context.
- Quy tắc map event payload, timeout và giới hạn tài nguyên.
- Cách chọn function definition và chuyển đổi output.
- Quyền truy cập các dịch vụ bên ngoài nếu Function cần I/O.

Một instance serverless có thể được tái sử dụng hoặc tạo mới, và nhiều invocation có thể chạy trên các instance khác nhau. Do đó, không lưu trạng thái nghiệp vụ lâu dài trong biến của Calculator, dù Spring bean có scope singleton trên một instance.

## 11. Composition: một adapter cho nhiều bước Java thuần

Spring Cloud Function cho phép ghép hàm bằng tên, miễn là đầu ra của bước trước tương thích với đầu vào bước sau.

Ở ví dụ, **calculateQuote** nhận **QuoteRequest** và trả **Quote**, còn **formatQuote** nhận **Quote** và trả **String**:

~~~text
QuoteRequest
  -> calculateQuote
  -> Quote
  -> formatQuote
  -> String
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote|formatQuote
~~~

Từ input **ORD-101**, **100.00**, kết quả là chuỗi **ORD-101: 110.00**.

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["calculateQuote"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

Ở đây, **formatQuote** nằm trong Spring configuration như một lambda nhưng hoàn toàn có thể được tách thành một **Function<Quote, String>** Java thuần khác khi logic định dạng phức tạp hơn hoặc cần tái sử dụng độc lập.

Điểm quan trọng là **composition không yêu cầu các hàm con phải biết đến FunctionCatalog**. Catalog nối chúng theo tên và kiểu đầu vào/đầu ra. Khi dùng Stream, tên binding cho một composition có thể khác tên của một hàm đơn lẻ; cần kiểm tra naming convention của binder và framework đang sử dụng.

## 12. Khi cần metadata của thông điệp, adapter xử lý thế nào?

Logic nghiệp vụ thuần thường chỉ cần **payload**. Với HTTP hoặc broker, message có thể có thêm **headers** như correlation ID, event type, tracing metadata hoặc content type.

Nếu một yêu cầu nghiệp vụ thực sự cần correlation ID để tạo output, có hai lựa chọn chính:

1. **Biến dữ liệu cần thiết thành một phần input nghiệp vụ rõ ràng** nếu correlation ID là một phần hợp đồng của use case.
2. **Đọc và chuyển metadata ở adapter** nếu nó chỉ phục vụ logging, tracing hoặc routing kỹ thuật.

Ví dụ adapter Spring có thể nhận **Message<QuoteRequest>**, gọi lõi, rồi tạo một **Message<Quote>** mới có correlation ID cần truyền tiếp:

~~~java
package example.adapter.spring;

import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
public class QuoteMessageConfiguration {

    @Bean("calculateQuoteMessage")
    Function<Message<QuoteCore.QuoteRequest>,
             Message<QuoteCore.Quote>>
            calculateQuoteMessage(
                @Qualifier("calculateQuote")
                Function<QuoteCore.QuoteRequest, QuoteCore.Quote>
                    calculator) {

        return input -> {
            QuoteCore.Quote quote =
                calculator.apply(input.getPayload());

            var builder = MessageBuilder.withPayload(quote);

            Object correlation =
                input.getHeaders().get("correlationId");
            if (correlation != null) {
                builder.setHeader("correlationId", correlation);
            }

            return builder.build();
        };
    }
}
~~~

Đây là **bean adapter bổ sung**, không yêu cầu thay một dòng nào trong **QuoteCore**. Khi có nhiều bean Function, phải chọn chính xác **calculateQuote** hoặc **calculateQuoteMessage** trong **spring.cloud.function.definition** theo nhu cầu triển khai.

Không nên mặc định toàn bộ HTTP header hoặc broker header được bảo toàn qua mọi adapter. Tránh copy các header nhạy cảm không có mục đích nghiệp vụ, và không dùng header do client gửi làm bằng chứng phân quyền nếu chưa được hệ thống xác thực tin cậy.

## 13. Nếu nghiệp vụ cần database hoặc gửi sự kiện thì sao?

Lõi có thể cần lấy dữ liệu ngoài hoặc tạo tác dụng phụ. Khi đó **không phụ thuộc Spring** vẫn khả thi nhờ **interface (port)**. Lõi định nghĩa thao tác nó cần; adapter bên ngoài cung cấp implementation.

Ví dụ một Consumer ghi nhật ký kiểm toán. Phần lõi Java thuần:

~~~java
package example.core;

import java.util.function.Consumer;

public final class AuditCore {

    private AuditCore() {
    }

    public record AuditEvent(
        String eventId,
        String message
    ) {}

    // Cổng nằm ở phía lõi: mô tả nhu cầu, không mô tả JDBC/Kafka.
    public interface AuditSink {
        void save(AuditEvent event);
    }

    public static final class AuditConsumer
            implements Consumer<AuditEvent> {

        private final AuditSink sink;

        public AuditConsumer(AuditSink sink) {
            this.sink = java.util.Objects.requireNonNull(sink);
        }

        @Override
        public void accept(AuditEvent event) {
            if (event == null
                    || event.eventId() == null
                    || event.eventId().isBlank()) {
                throw new IllegalArgumentException("Invalid audit event");
            }

            sink.save(event);
        }
    }
}
~~~

Lớp điều hợp Spring đăng ký implementation cho cổng và tạo Consumer:

~~~java
package example.adapter.spring;

import java.util.function.Consumer;

import example.core.AuditCore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    AuditCore.AuditSink auditSink() {
        // Adapter demo: thay bằng repository/transaction trong thực tế.
        return event -> System.out.println(
            "AUDIT " + event.eventId() + ": " + event.message());
    }

    @Bean("recordAudit")
    Consumer<AuditCore.AuditEvent> recordAudit(
            AuditCore.AuditSink sink) {
        return new AuditCore.AuditConsumer(sink);
    }
}
~~~

Cùng **AuditConsumer** có thể dùng với một adapter ghi JDBC, gọi REST hoặc gửi message, miễn adapter đó thực hiện hợp đồng **AuditSink**. Logic ở lõi không phải import các lớp Spring Data, HTTP client hoặc Kafka.

**Tách phụ thuộc không tự giải quyết tác dụng phụ.** Consumer có thể được gọi lại cùng event sau retry; nếu lưu database, nên có **idempotency key**, **unique constraint**, transaction hoặc outbox theo nhu cầu. Việc in console chỉ là minh họa, không phải kho audit bền vững.

## 14. Thiết kế ranh giới lỗi giữa lõi và adapter

Một hàm nghiệp vụ có thể từ chối input hoặc phát hiện trạng thái không hợp lệ. Ví dụ **QuoteCore.Calculator** ném **IllegalArgumentException** khi số tiền âm hoặc vượt quy tắc độ chính xác.

Adapter chịu trách nhiệm diễn giải lỗi cho từng giao thức:

| Lỗi từ lõi | HTTP adapter | Stream adapter | Serverless adapter |
| --- | --- | --- | --- |
| Input sai hợp đồng | Có thể ánh xạ thành lỗi client như 400 nếu cấu hình tương ứng | Có thể reject, bỏ qua hoặc chuyển dead-letter tùy chính sách | Trả lỗi theo event contract/runtime |
| I/O tạm thời lỗi | Có thể trả lỗi server, timeout hoặc retry ở lớp phù hợp | Có thể retry và backoff theo binder | Có thể báo thất bại để trigger áp dụng retry |
| Quy tắc nghiệp vụ không thỏa | Trả lỗi có cấu trúc theo API contract | Xác định event lỗi hoặc trạng thái xử lý | Trả kết quả/lỗi theo hợp đồng use case |

**Không hard-code mã HTTP, tên Kafka topic hoặc runtime error envelope trong lõi** chỉ vì adapter hiện tại cần chúng. Nếu yêu cầu nghiệp vụ phức tạp, có thể tạo exception hoặc result type riêng trong lõi rồi để adapter ánh xạ sang cơ chế phù hợp.

Không có quy tắc mặc định rằng **IllegalArgumentException** từ Function chắc chắn trở thành HTTP 400. Cần kiểm tra cơ chế xử lý lỗi của adapter thật và viết integration test tương ứng.

## 15. Kiểm thử lõi mà không cần Spring

Lợi ích lớn của hàm độc lập là có thể kiểm thử nhanh và chính xác bằng JUnit mà không khởi động application context. Ví dụ:

~~~java
package example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class QuoteCoreTest {

    private final QuoteCore.Calculator calculator =
        new QuoteCore.Calculator(
            new QuoteCore.TaxPolicy(new BigDecimal("0.10"))
        );

    @Test
    void calculatesTaxAndTotal() {
        QuoteCore.Quote result = calculator.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        assertEquals(new BigDecimal("100.00"), result.netAmount());
        assertEquals(new BigDecimal("10.00"), result.taxAmount());
        assertEquals(new BigDecimal("110.00"), result.total());
    }

    @Test
    void rejectsNegativeNetAmount() {
        assertThrows(IllegalArgumentException.class,
            () -> calculator.apply(
                new QuoteCore.QuoteRequest(
                    "ORD-102", new BigDecimal("-1.00")
                )
            ));
    }

    @Test
    void rejectsExcessFractionalDigits() {
        assertThrows(IllegalArgumentException.class,
            () -> calculator.apply(
                new QuoteCore.QuoteRequest(
                    "ORD-103", new BigDecimal("1.234")
                )
            ));
    }
}
~~~

Trong unit test, chính bài test tạo **TaxPolicy**. Việc đó không phá vỡ ý tưởng DI: constructor injection là một kỹ thuật Java, còn Spring chỉ là một cách cung cấp đối tượng ở runtime.

Với **AuditConsumer**, có thể dùng một fake **AuditSink** để quan sát tác dụng phụ:

~~~java
package example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AuditCoreTest {

    @Test
    void delegatesToPort() {
        List<AuditCore.AuditEvent> captured = new ArrayList<>();
        AuditCore.AuditSink sink = captured::add;

        AuditCore.AuditConsumer consumer =
            new AuditCore.AuditConsumer(sink);

        consumer.accept(
            new AuditCore.AuditEvent("evt-001", "created")
        );

        assertEquals(1, captured.size());
        assertEquals("evt-001", captured.get(0).eventId());
    }
}
~~~

Test này bảo đảm lõi gọi đúng cổng. Nó **không kiểm thử** độ bền của database hoặc việc gửi event thật; những phần đó cần integration test với adapter tương ứng.

## 16. Kiểm thử ranh giới Spring và giao thức

Unit test Java chưa xác nhận Spring tìm đúng bean hoặc chuyển JSON/message thành kiểu dự kiến. Vì vậy nên có kiểm thử tích hợp tập trung vào adapter thực sự sử dụng.

Ví dụ kiểm thử **FunctionCatalog** với ứng dụng Spring Boot:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import example.core.QuoteCore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class QuoteFunctionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogInvokesCoreFunction() {
        Function<QuoteCore.QuoteRequest, QuoteCore.Quote> fn =
            catalog.lookup("calculateQuote");

        assertNotNull(fn);

        QuoteCore.Quote result = fn.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        assertEquals(new BigDecimal("110.00"), result.total());
    }
}
~~~

Kiểm thử này cần dự án có **Spring Boot Test**, Spring Cloud Function và các dependency phù hợp trên test classpath. Nó chỉ xác nhận đường gọi qua **FunctionCatalog** trong application context.

Nếu tích hợp qua HTTP, bổ sung kiểm thử POST thật với JSON, content type và lỗi input. Nếu tích hợp qua Stream, kiểm tra conversion, binding, retry và tình huống gửi lại. Nếu triển khai serverless, kiểm tra event mapping và handler theo runtime. Không nhất thiết dựng tất cả adapter nếu sản phẩm chỉ sử dụng một loại giao thức.

## 17. Những lỗi kiến trúc thường gặp

| Dấu hiệu | Nguyên nhân | Cách cải thiện |
| --- | --- | --- |
| Lõi import **@Component**, **ApplicationContext** hoặc HTTP request | Nghiệp vụ đã phụ thuộc framework | Di chuyển wiring và protocol mapping sang adapter |
| Unit test phải khởi động Spring mới tính được một phép toán | Lõi lấy cấu hình/phụ thuộc trực tiếp từ container | Dùng constructor injection với kiểu Java thuần |
| Bean Function không xuất hiện trong catalog | Chưa đăng ký bean, sai scan hoặc tên function | Kiểm tra **@Bean**, tên và **function.definition** |
| Thay từ HTTP sang Stream phải viết lại tính toán | Logic đọc request hay response trực tiếp | Định nghĩa **Function<T, R>** trên DTO/record và tách adapter |
| **Function** bị serialize sai | Generic đầu vào/đầu ra thiếu rõ ràng hoặc schema khác | Giữ generic cụ thể, kiểm thử conversion |
| Một lần gọi thành công nhưng Consumer ghi dữ liệu trùng | Retry/redelivery và thiếu idempotency | Khóa sự kiện nghiệp vụ, unique constraint và chính sách retry |
| Header bị mất khi qua composition | Chưa thiết kế truyền metadata | Tạo Message ở adapter và giữ header cần thiết |
| Kết quả khác nhau giữa hai instance | Lõi giữ mutable state trong singleton hoặc nhớ cache cục bộ sai | Dùng hàm stateless, kho chung hoặc cơ chế đồng thời đúng |
| Lỗi nghiệp vụ được biến thành status không mong muốn | Adapter thiếu error mapping | Viết mapping theo hợp đồng giao thức và integration test |
| Lõi phải biết chi tiết JDBC/Kafka | Cổng phụ thuộc vào implementation hạ tầng | Đặt interface ở ranh giới lõi, implementation ở adapter |

Một cách kiểm tra nhanh: **nếu xóa toàn bộ dependency Spring và chạy bài test của lõi, phép tính nghiệp vụ có còn thực hiện được không?** Nếu có, phần tính toán có khả năng đã giữ được ranh giới độc lập. Điều đó chưa đảm bảo kiến trúc hoàn hảo, nhưng là một phép thử thực tế hữu ích.

## 18. Bài tập thực hành

**Bài tập 1 — Tách logic khỏi Spring.** Viết một **Function<ShippingRequest, ShippingQuote>** Java thuần, nhận cân nặng và vùng giao hàng, trả phí vận chuyển. Sau đó tạo bean **@Bean("calculateShipping")** trong lớp cấu hình Spring. Viết unit test lõi mà không dùng **@SpringBootTest**.

**Bài tập 2 — Thay adapter.** Với **calculateQuote**, gọi thử qua HTTP POST và mô tả cấu hình Spring Cloud Stream để nhận **QuoteRequest** từ topic **quote-requests**, phát **Quote** tới **quote-results**. Chỉ ra những dòng trong **QuoteCore** cần thay đổi, nếu có, và lý do.

**Bài tập 3 — Composition.** Viết **Function<Quote, String>** thuần Java để định dạng chuỗi kết quả. Đăng ký nó bằng bean **formatQuote**, rồi cấu hình **calculateQuote|formatQuote**. Kiểm thử đầu ra thông qua FunctionCatalog.

**Bài tập 4 — Interface cho hạ tầng.** Tạo **Consumer<NotificationRequest>** nhận một **NotificationPort** thuần Java. Viết hai implementation: fake cho unit test và một adapter gửi thông báo ở lớp ngoài. Giải thích vì sao không nên inject trực tiếp HTTP client vào lõi chỉ để thực hiện use case.

**Bài tập 5 — Metadata.** Định nghĩa header **correlationId** cho một message đầu vào. Tạo adapter **Function<Message<QuoteRequest>, Message<Quote>>** gọi Calculator và truyền lại đúng correlationId. Kiểm thử trường hợp header thiếu mà lõi vẫn tính chính xác.

**Bài tập 6 — Chẩn đoán kiến trúc.** Một class **@Service** có method nhận **HttpServletRequest**, đọc **Environment**, tạo **KafkaTemplate** rồi tính tổng tiền. Hãy phân chia lại trách nhiệm thành DTO, Function Java thuần, interface cổng khi cần và các adapter để có thể tái sử dụng cùng phép tính qua HTTP và broker.

### Ghi nhớ

- **Hàm không phụ thuộc Spring** là hàm nghiệp vụ sử dụng hợp đồng Java và dữ liệu rõ ràng, có thể được gọi và kiểm thử độc lập với Spring container.
- **Lớp điều hợp bên ngoài** tạo Spring bean, inject phụ thuộc, đăng ký tên trong **FunctionCatalog**, chuyển đổi payload/message và kết nối HTTP, Stream hoặc serverless.
- Dùng **constructor injection và interface cổng** khi lõi cần chính sách, repository hoặc tác dụng phụ; không đưa chi tiết framework/hạ tầng vào logic tính toán.
- **Composition** nối các hàm theo tên và hợp đồng kiểu. Các adapter xử lý protocol, lỗi, metadata và retry theo môi trường triển khai.
- Unit test lõi kiểm tra **quy tắc nghiệp vụ**; integration test kiểm tra **wiring, tên bean, conversion và giao thức**. Cả hai cần thiết khi xây dựng một chức năng có thể tái sử dụng.
