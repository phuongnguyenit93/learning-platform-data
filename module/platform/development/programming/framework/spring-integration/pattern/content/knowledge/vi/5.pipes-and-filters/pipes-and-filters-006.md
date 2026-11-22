# Đặt validation gần nơi nhận dữ liệu

Trong kiến trúc **Pipes and Filters**, dữ liệu đi qua một chuỗi các bước độc lập: mỗi *filter* nhận một thông điệp, xử lý một trách nhiệm và chuyển kết quả qua *pipe* tới bước kế tiếp. Với **Spring Integration**, các pipe thường là `MessageChannel`, còn các bước xử lý có thể là `Filter`, `Transformer`, `Router`, `Service Activator` hoặc các endpoint khác.

Một nguyên tắc quan trọng khi thiết kế chuỗi này là **đặt validation gần nơi dữ liệu đi vào hệ thống hoặc đi qua một ranh giới tin cậy**. Dữ liệu sai nên bị phát hiện khi còn ở đầu luồng, trước khi tiêu tốn tài nguyên cho những bước tốn kém hoặc tạo tác động nghiệp vụ như ghi cơ sở dữ liệu, gọi API, gửi email hay cập nhật trạng thái.

Bài học thuộc chương **Pipes and filters**, module **SPRING_INTEGRATION_PATTERN**. Module tập trung triển khai Enterprise Integration Patterns với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và quan sát các nhánh xử lý. Tại đây, validation được xem như một phần của hợp đồng thông điệp và cách tổ chức luồng, không chỉ là vài câu lệnh `if`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao nên kiểm tra dữ liệu sớm, ngay sau bước tiếp nhận và giải mã phù hợp.
2. Phân biệt validation **cú pháp**, **cấu trúc/schema**, **ngữ nghĩa**, **quy tắc nghiệp vụ**, **quyền truy cập** và các kiểm tra ở bước downstream.
3. Chọn đúng công cụ trong Spring Integration: `Filter` để chấp nhận/từ chối, `Transformer` để chuẩn hóa, `Router` để phân nhánh và exception/error flow để báo lỗi.
4. Dùng Jakarta Bean Validation trong một endpoint và xử lý message bị từ chối qua `discardChannel`.
5. Giữ đúng metadata như `tenantId`, `traceId`, `correlationId` khi thông điệp đi qua validation.
6. Kiểm thử cả đường thành công, đường reject, lỗi parse và tình huống dữ liệu không hợp lệ không được đi tới handler có side effect.
7. Xây dựng chiến lược quan sát, phân loại lỗi và retry an toàn.

## 2. Validation gần đầu vào nghĩa là gì?

Một luồng xử lý đơn hàng có thể bắt đầu từ HTTP Gateway, AMQP/Kafka inbound adapter, JMS, file polling adapter hoặc một `MessagingGateway` trong ứng dụng. Dù nguồn nào, dữ liệu nhận được cũng cần đi qua một loạt ranh giới:

~~~mermaid
flowchart LR
    SRC["HTTP / MQ / File / Gateway"] --> LIMIT["Giới hạn kích thước + parse"]
    LIMIT --> STRUCT["Kiểm tra schema / kiểu dữ liệu"]
    STRUCT --> VALID["Validation đầu vào"]
    VALID -->|Hợp lệ| NORM["Transformer: chuẩn hóa"]
    NORM --> ROUTE{"Router"}
    ROUTE --> A["Handler A"]
    ROUTE --> B["Handler B"]
    VALID -->|Không hợp lệ| REJECT["Reject / discard channel"]
    LIMIT -->|Lỗi parse| ERROR["Error response / error flow"]
    STRUCT -->|Không đạt| ERROR
~~~

Đặt validation gần nơi nhận **không có nghĩa mọi kiểm tra đều phải chạy trước mọi phép chuyển đổi**. Chẳng hạn, JSON dạng chuỗi phải được parse thành DTO trước khi có thể áp dụng annotation `@NotBlank` hay `@DecimalMin`. Một pipeline hợp lý thường là:

1. **Admission / resource limits:** giới hạn request body, message size, timeout, định dạng chấp nhận được; tránh đọc dữ liệu vô hạn.
2. **Decode / parse:** chuyển bytes hoặc JSON thành biểu diễn có kiểu; lỗi parse dừng tại ranh giới nhận.
3. **Structural validation:** kiểm tra trường bắt buộc, kiểu, giới hạn độ dài, định dạng mã.
4. **Trust / access validation:** xác định nguồn tin cậy và quyền của caller, tenant, channel hoặc principal; không tin header có thể bị client giả mạo.
5. **Normalize:** chuẩn hóa chuỗi, timezone, mã vùng hoặc đơn vị; quy định rõ chuẩn hóa trước hay sau từng loại validation.
6. **Semantic validation:** kiểm tra quan hệ giữa các trường, khoảng giá trị, điều kiện logic mà không cần gọi hệ thống ngoài.
7. **Routing / business processing:** đưa dữ liệu hợp lệ tới những nhánh cần thiết; có thể còn các kiểm tra nghiệp vụ phụ thuộc trạng thái hiện tại.

**Nguyên tắc:** kiểm tra càng gần nguồn càng tốt đối với bất biến có thể xác minh tại đó; kiểm tra lại khi thông điệp đi vào một **ranh giới tin cậy mới** hoặc cần xác nhận điều kiện nghiệp vụ chưa tồn tại ở đầu vào.

### 2.1. Vì sao đặt validation sớm?

| Nếu kiểm tra sớm | Nếu phát hiện muộn |
|---|---|
| Handler phía sau nhận cấu trúc dữ liệu nhất quán | Mỗi handler phải tự đoán kiểu hoặc lặp logic |
| Dừng trước bước ghi DB hoặc gọi API tốn kém | Phát hiện sau khi đã có side effect khó hoàn tác |
| Phản hồi lỗi cụ thể cho nguồn gửi | Lỗi xuất hiện xa nguồn, khó xác định nguyên nhân |
| Giảm số đường code phải xử lý dữ liệu hỏng | Mỗi nhánh phải có thêm trường hợp dữ liệu sai |
| Có thể đo riêng tỷ lệ message bị reject | Dữ liệu lỗi bị trộn vào lỗi nghiệp vụ/hạ tầng |

Tuy nhiên, không nên dồn các truy vấn phụ thuộc trạng thái, như “số dư hiện tại có đủ không”, vào ingress nếu chúng cần nhất quán giao dịch ngay tại thời điểm ghi. Những kiểm tra này nên được thực hiện lại ở ranh giới nghiệp vụ có transaction thích hợp.

## 3. Phân loại các lớp validation

Giả sử hệ thống nhận lệnh đặt hàng:

~~~json
{
  "orderId": "order-1001",
  "amount": 120.50,
  "region": "north",
  "customerEmail": "buyer@example.com"
}
~~~

Có thể tách trách nhiệm thành:

| Lớp | Ví dụ kiểm tra | Vị trí phù hợp | Cách xử lý khi thất bại |
|---|---|---|---|
| Giới hạn tài nguyên | Body vượt giới hạn; cấu trúc lồng quá sâu | Adapter / HTTP server / decoder | Reject trước khi đưa vào luồng |
| Cú pháp | JSON lỗi, số ở dạng không parse được | Decoder / message converter | Lỗi parse; gửi phản hồi phù hợp |
| Schema / cấu trúc | Thiếu `orderId`, `amount` không phải số | DTO binding / Bean Validation | Reject message theo hợp đồng |
| Giá trị/định dạng | `amount` không dương, `region` sai danh sách | Validator gần đầu vào | Reject hoặc báo lỗi validation |
| Bảo mật / nguồn tin cậy | Caller không được gửi cho tenant này | Authentication / authorization tại ranh giới | Deny, audit phù hợp |
| Ngữ nghĩa liên trường | `deliveryDate` trước `createdAt` | Validator thuần dữ liệu | Reject |
| Nghiệp vụ theo trạng thái | Hàng tồn kho đủ; trạng thái đơn cho phép sửa | Handler nghiệp vụ/transaction | Business rejection với lý do |
| Điều kiện tại hệ thống ngoài | API đối tác có chấp nhận yêu cầu? | Integration adapter/outbound | Lỗi tích hợp, retry hoặc bù trừ có kiểm soát |

Một `@Email` có thể kiểm tra **hình thức** email, không chứng minh hộp thư tồn tại hay người dùng sở hữu nó. Tương tự, `@DecimalMin("0.01")` xác nhận khoảng giá trị tại thời điểm validate, không chứng minh tính hợp lệ của giao dịch thanh toán.

## 4. Xác định hợp đồng message ở đầu vào

Giữa hai component, cần có hợp đồng rõ ràng về **payload**, **headers** và **lỗi**.

Ví dụ:

~~~text
input channel: orders.received
payload: OrderRequest
headers:
  traceId: String?            # dùng để quan sát, có thể được sinh nội bộ
  tenantId: String            # gắn từ ngữ cảnh đã xác thực
  sourceSystem: String?       # nguồn gửi nếu được xác nhận
output thành công: orders.accepted
output bị từ chối: orders.rejected
lỗi parse/exception: error flow hoặc phản hồi của adapter/gateway
~~~

Dấu `?` trong ví dụ trên có nghĩa trường có thể vắng mặt; đây là quy ước tài liệu, không phải cú pháp Java.

**Không dùng header do client tự khai báo làm bằng chứng đã xác thực.** Ví dụ, client gửi `tenantId=shop-admin` không có nghĩa caller được xử lý dữ liệu của tenant đó. Inbound adapter hoặc một lớp security phải xác định principal và tenant được phép, sau đó chỉ đưa thông tin đã tin cậy vào vùng xử lý nội bộ.

### 4.1. Message ID và correlation

- `MessageHeaders.ID` là ID một message instance; message mới có thể có ID mới.
- `traceId` giúp theo dõi các bước; có thể do hạ tầng tracing quản lý hoặc ứng dụng tạo theo hợp đồng.
- `correlationId` / `businessCorrelationId` liên kết nhiều message thuộc cùng một nghiệp vụ hoặc nhóm của Splitter/Aggregator.
- `errorChannel` và `replyChannel` là các header điều khiển đường lỗi/phản hồi trong các luồng tương ứng.

Validation cần bảo toàn metadata cần thiết trên **cả nhánh thành công và nhánh reject** để hệ thống giải thích được message nào, nguồn nào bị từ chối. Khi reject có thể lưu mã lỗi và một số trường an toàn, nhưng tránh log toàn bộ payload nếu chứa dữ liệu cá nhân hoặc bí mật.

## 5. Biểu diễn dữ liệu đầu vào bằng DTO và Jakarta Bean Validation

Trong hệ thống Java 17+ dùng Spring Framework 6 / Spring Boot 3+, Jakarta Bean Validation dùng namespace `jakarta.validation.*`. Thư viện triển khai (ví dụ Hibernate Validator) phải có trên classpath; với Spring Boot thường bổ sung starter validation phù hợp.

Một DTO minh họa:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record OrderRequest(
        @NotBlank
        @Size(max = 64)
        String orderId,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal amount,

        @NotBlank
        @Size(max = 24)
        String region,

        @NotBlank
        @Email
        String customerEmail
) {}
~~~

Giải thích:

- `@NotBlank` từ chối `null`, chuỗi rỗng hoặc toàn khoảng trắng.
- `@Size(max=...)` hạn chế độ dài biểu diễn, nhưng **không thay thế giới hạn kích thước request ở tầng transport**.
- `@NotNull` và `@DecimalMin` bảo vệ trường tiền; `BigDecimal` thích hợp hơn `double` cho nhiều bài toán tiền tệ.
- `@Email` là kiểm tra hình thức email; có thể cần chính sách domain chặt hơn tùy ứng dụng.
- `record` giúp định nghĩa payload thuận tiện và không có setter. Nếu record chứa collection hoặc object mutable, vẫn cần defensive copy ở nơi thích hợp.

Bộ constraint chỉ là **phần đầu**. Nếu business chỉ cho phép `NORTH` hoặc `SOUTH`, hãy quyết định rõ thứ tự chuẩn hóa `region`, rồi kiểm tra enum/allowed values. Đừng cho phép một chuỗi tùy ý chỉ vì nó không rỗng.

### 5.1. Không tạo ValidatorFactory cho mỗi message

Trong Spring, nên dùng một bean `Validator` được quản lý vòng đời:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean orderValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

`LocalValidatorFactoryBean` triển khai giao diện Jakarta `Validator` và thích hợp để inject trong component. Không tạo `Validation.buildDefaultValidatorFactory()` liên tục trong mỗi lời gọi message handler vì thiết lập factory có chi phí và vòng đời tài nguyên riêng.

## 6. Chặn message không hợp lệ bằng Filter

`Filter` là lựa chọn khi câu hỏi của một bước chỉ là **“message này có được đi tiếp không?”**. Một method dùng `@Filter` có thể nhận payload và trả `boolean`:

~~~java
import jakarta.validation.Validator;

import org.springframework.integration.annotation.Filter;

public class OrderAdmissionFilter {

    private final Validator validator;

    public OrderAdmissionFilter(Validator validator) {
        this.validator = validator;
    }

    @Filter(
            inputChannel = "orders.received",
            outputChannel = "orders.accepted",
            discardChannel = "orders.rejected")
    public boolean accept(OrderRequest request) {
        return validator.validate(request).isEmpty();
    }
}
~~~

Khi class này được đăng ký thành Spring bean và annotation processing của Spring Integration được bật:

- `true`: input message được chuyển tiếp tới `orders.accepted`.
- `false`: message bị từ chối và gửi tới `orders.rejected` nhờ `discardChannel`.
- Không cần tự tạo một message mới cho nhánh thành công hoặc reject trong ví dụ này.

**Quan trọng:** `Filter` chuyển tiếp **message** đã nhận, không tự biến payload thành DTO khác. Nếu muốn sửa/chuẩn hóa payload, hãy dùng `Transformer` trước hoặc sau Filter tùy contract.

### 6.1. Vì sao phải có discardChannel?

Theo hành vi mặc định, Filter có thể **bỏ message bị từ chối** nếu không cấu hình discard channel và không bật exception khi reject. Một luồng thanh toán/đơn hàng không nên âm thầm bỏ dữ liệu quan trọng mà không có cách giải thích cho nguồn gửi.

~~~mermaid
flowchart LR
    A["orders.received"] --> F{"Filter: constraints OK?"}
    F -->|true| V["orders.accepted"]
    F -->|false| X["orders.rejected"]
    V --> H["Business processing"]
    X --> D["Audit / reject response / dead-letter policy"]
~~~

Nhánh reject có thể ghi log có kiểm soát, tăng metric, tạo phản hồi lỗi hoặc chuyển sang dead-letter theo chính sách của hệ thống. Nếu muốn cung cấp **danh sách lỗi theo field**, một method `boolean` đơn giản không chuyển kèm lý do; hãy tạo một cấu trúc `ValidationResult`, dùng validator có kết quả chi tiết hoặc chuyển lỗi qua exception/error flow như mục sau.

### 6.2. throwExceptionOnRejection có ý nghĩa khác discard

Có thể cấu hình `throwExceptionOnRejection = "true"` trong annotation `@Filter` hoặc thiết lập tương đương trong DSL/config. Khi Filter reject:

- Mặc định `throwExceptionOnRejection=false`: message được discard hoặc chuyển sang discard channel nếu đã cấu hình.
- Nếu bật `true`: Filter ném `MessageRejectedException`; khi có discard channel, theo hành vi `MessageFilter`, message vẫn có thể được gửi tới discard channel **rồi** exception được ném.
- Exception ở flow đồng bộ có thể lan về caller; ở flow bất đồng bộ sẽ đi theo cơ chế error handling áp dụng tại channel/endpoint.

Đừng bật cùng lúc discard và throw chỉ vì nghĩ “an toàn hơn”; điều đó có thể khiến cùng một lần reject tạo **hai dấu vết xử lý** (nhánh discard và exception), cần tránh double-count hoặc phản hồi trùng.

## 7. Khi validation cần báo lỗi chi tiết thay vì boolean

Có hai nhu cầu khác nhau:

1. **Loại message có chủ đích**: ví dụ event không thuộc loại cần xử lý, Filter với discard là tự nhiên.
2. **Báo dữ liệu sai hợp đồng đầu vào**: ví dụ trường tiền không hợp lệ trong request bắt buộc phải xác thực, nên trả một lỗi có ý nghĩa cho caller hoặc chuyển vào validation error flow.

Trong tình huống thứ hai, có thể đặt validation trong một endpoint không cho message đi tiếp khi lỗi. Ví dụ dùng Transformer trả payload ban đầu nếu hợp lệ:

~~~java
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

import org.springframework.integration.annotation.Transformer;

public class StrictOrderValidator {

    private final Validator validator;

    public StrictOrderValidator(Validator validator) {
        this.validator = validator;
    }

    @Transformer(
            inputChannel = "orders.parsed",
            outputChannel = "orders.checked")
    public OrderRequest requireValid(OrderRequest request) {
        var violations = validator.validate(request);

        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        return request;
    }
}
~~~

Class này cần được đăng ký Spring bean. Khi không hợp lệ, transformer ném exception; **không có message hợp lệ** đi đến `orders.checked`. Khi hợp lệ, transformer trả payload và framework xây dựng message đầu ra, thông thường truyền headers đầu vào theo cấu hình.

**Không dùng `return null` từ Transformer để loại message:** Transformer của Spring Integration yêu cầu kết quả hợp lệ và có thể ném `MessageTransformationException` nếu trả null. Nếu ý định là lọc, dùng Filter; nếu ý định là báo lỗi, ném exception có kiểm soát.

### 7.1. Lưu ý về exception

Trong flow thực tế, exception từ transformer có thể được bọc trong một `MessagingException` hoặc exception chuyên biệt của endpoint. Khi xử lý lỗi, nên kiểm tra **cause chain** để phân biệt `ConstraintViolationException` với lỗi hệ thống, thay vì chỉ so tên exception ngoài cùng.

Không nhất thiết phải công khai toàn bộ thông tin `ConstraintViolation`. Danh sách lỗi có thể chứa thuộc tính hoặc rejected value nhạy cảm; ở API boundary nên ánh xạ sang mã lỗi/field hợp lệ và trả nội dung cần thiết cho client.

### 7.2. Một mô hình khác: ValidationResult

Nếu hệ thống cần ghi nhận lỗi mà không dùng exception làm control flow, có thể tạo kết quả tường minh:

~~~java
import java.util.List;

public record ValidationIssue(
        String field,
        String code
) {}

public record ValidationResult<T>(
        T value,
        List<ValidationIssue> issues
) {
    public boolean valid() {
        return issues.isEmpty();
    }
}
~~~

Một bước validation thuần dữ liệu trả `ValidationResult<OrderRequest>`, sau đó Router chọn nhánh `accepted` hoặc `rejected` theo `valid()`. Khi đó hai nhánh có thể quan sát lỗi dạng có cấu trúc, dễ làm metric và phản hồi API. Đổi lại, mọi downstream phải hiểu contract mới hoặc phải có Transformer chuyển về payload nghiệp vụ sau nhánh accepted.

## 8. Cấu hình một chuỗi Pipes and Filters bằng Java DSL

Java DSL có thể thể hiện trực tiếp một chuỗi: nhận message, lọc, chuẩn hóa rồi chuyển tới bước sau.

~~~java
import java.util.Locale;

import jakarta.validation.Validator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderIngressFlowConfiguration {

    @Bean
    IntegrationFlow orderIngressFlow(Validator validator) {
        return IntegrationFlow.from("orders.received")
                .filter(OrderRequest.class,
                        req -> validator.validate(req).isEmpty(),
                        endpoint -> endpoint
                                .discardChannel("orders.rejected"))
                .transform(OrderRequest.class, req ->
                        new OrderRequest(
                                req.orderId().trim(),
                                req.amount(),
                                req.region().trim()
                                        .toUpperCase(Locale.ROOT),
                                req.customerEmail().trim()))
                .channel("orders.normalized")
                .get();
    }
}
~~~

Giả định `OrderRequest` đã được decode thành công trước khi vào `orders.received` và các trường string đã qua `@NotBlank` nên có giá trị không null tại bước transform. Cấu hình này minh họa **hai trách nhiệm riêng**: Filter kiểm tra hợp đồng đầu vào, Transformer tạo payload chuẩn hóa. Nếu contract cho phép chuỗi có khoảng trắng xung quanh và validation phải dùng giá trị đã canonicalize, có thể đặt một Transformer **an toàn, không làm thay đổi ý nghĩa** trước Filter; khi đó cần xác định rõ dữ liệu ban đầu nào vẫn được lưu để audit.

Lựa chọn thứ tự không đơn thuần là thẩm mỹ:

- **Validate rồi normalize:** phù hợp khi format gốc phải đúng theo hợp đồng chính xác (ví dụ chữ hoa bắt buộc).
- **Normalize rồi validate:** phù hợp khi đầu vào cho phép nhiều biểu diễn tương đương (ví dụ `" north "` và `"NORTH"`), với điều kiện normalization không che giấu dữ liệu xấu.
- **Validate → normalize → validate lại một số invariant:** phù hợp khi normalization có thể làm thay đổi độ dài, phạm vi hoặc tính hợp lệ của dữ liệu.

### 8.1. Không đồng nhất Filter với cơ chế security

Một `Filter` xử lý message chỉ là một bước trong integration flow, không thay thế authentication, authorization, rate limiting hoặc input size limit tại HTTP/Kafka/AMQP boundary. Ví dụ kiểm tra user có quyền đọc đơn hàng hay không thường cần security context đã xác thực; authorization phải chạy trước các side effect và tại điểm dữ liệu có thể bị truy cập.

## 9. Đặt validation sát ranh giới và giữ nghiệp vụ đúng vị trí

Khái niệm “gần nơi nhận dữ liệu” nên hiểu theo **ranh giới của luồng tin cậy**, không chỉ là bước đầu tiên sau API.

~~~mermaid
flowchart TB
    A["External HTTP request"] --> A1["Giới hạn / parse / validate / authorize"]
    A1 --> B["Internal message flow"]
    B --> C["Business transaction: kiểm tra trạng thái hiện tại"]
    C --> D["Outbound adapter"]
    D --> E["External partner response"]
    E --> E1["Parse và validate response"]
    E1 --> F["Tiếp tục nghiệp vụ"]
~~~

Ví dụ:

- HTTP ingress phải kiểm tra request chưa đáng tin cậy.
- Service xử lý thanh toán vẫn cần kiểm tra quy tắc nghiệp vụ sát transaction, dù DTO đã hợp lệ.
- Khi nhận phản hồi từ service ngoài, **phải validate response tại ranh giới mới**; không vì đã validate request ban đầu mà mặc nhiên tin toàn bộ dữ liệu nhận về.
- Với các sự kiện đọc từ broker, consumer nên validate tối thiểu contract/version của message, đặc biệt khi nhiều producer có thể thay đổi schema.
- Với message được Splitter tạo ra, cần xác nhận invariant của từng phần trước side effect tương ứng, kể cả khi message gốc đã được kiểm tra ở ingress.

Một thông điệp “đã validate” không đồng nghĩa mọi quyết định tương lai sẽ đúng mãi. Tồn kho, quyền và trạng thái giao dịch có thể thay đổi sau khi validation đầu vào hoàn tất.

## 10. Header, correlation và bảo toàn thông tin chẩn đoán

Đặt validation đầu flow giúp hệ thống phát hiện lỗi sớm, nhưng chỉ hữu ích khi có thể truy vết message và lý do từ chối.

Ví dụ message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> input = MessageBuilder
        .withPayload(new OrderRequest(
                "order-1001",
                new java.math.BigDecimal("120.50"),
                "north",
                "buyer@example.com"))
        .setHeader("traceId", "trace-1001")
        .setHeader("tenantId", "shop-a") // giả định do lớp auth nội bộ gắn
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

Khi Filter chuyển message sang `orders.accepted` hoặc `orders.rejected`, các headers của message vẫn có thể được downstream đọc. Nếu tự tạo **Message** mới trong Transformer để chuẩn hóa hoặc tạo `ValidationResult`, cần chủ động mang theo những headers được phép giữ:

~~~java
Message<OrderRequest> normalized = MessageBuilder
        .withPayload(new OrderRequest(
                input.getPayload().orderId().trim(),
                input.getPayload().amount(),
                input.getPayload().region().trim().toUpperCase(),
                input.getPayload().customerEmail().trim()))
        .setHeader("traceId",
                input.getHeaders().get("traceId"))
        .setHeader("businessCorrelationId",
                input.getHeaders().get("businessCorrelationId"))
        .build();
~~~

Trong Spring Integration, Transformer trả **payload** và Transformer trả **Message hoàn chỉnh** có quy tắc header propagation khác nhau. Trả payload thường để framework tạo message và truyền headers hợp lệ; trả Message nghĩa là code đã xác định message đầu ra. Vì vậy, khi đổi cách viết validation/normalization endpoint, phải kiểm thử riêng metadata.

**Không dùng `id` của message làm business correlation** xuyên retry hoặc transform; message ID có thể khác khi tạo message mới. Đồng thời, không đưa secret, token hoặc toàn bộ dữ liệu cá nhân vào `headers` chỉ để hỗ trợ log.

## 11. Phân biệt reject, lỗi dữ liệu và lỗi hệ thống

Một flow hoàn chỉnh cần quy định rõ các đường thất bại.

| Tình huống | Ví dụ | Xử lý điển hình | Có nên retry tự động? |
|---|---|---|---|
| Parse failure | JSON thiếu dấu ngoặc | Bad request / error event | Không, nếu dữ liệu không thay đổi |
| Validation reject | `amount=0` | Discard/reject channel hoặc response 4xx nếu dùng HTTP | Không |
| Authorization reject | Tenant không được phép | Deny + security audit | Không, trừ khi context thay đổi hợp lệ |
| Domain conflict | Đơn đã hủy, không thể thanh toán | Business error | Tùy hợp đồng, thường không retry mù |
| Transient infrastructure | DB timeout, gateway 503 | Retry có giới hạn, backoff, circuit breaker | Có thể, nếu idempotent |
| Programmer error | NPE trong code | Error flow, điều tra, alert | Không tự sửa bằng retry vô hạn |

Lưu ý: HTTP status như `400` hoặc `422` là **quy ước ở HTTP adapter/API**, không phải kết quả tự động của `Filter`. Tương tự, `discardChannel` không mặc định ghi vào broker hay dead-letter queue; nó chỉ chuyển message theo topology bạn cấu hình.

### 11.1. Filter từ chối không nhất thiết làm send() thất bại

Trong chế độ mặc định, Filter có thể reject một message mà lời gọi gửi ở đầu flow vẫn được xem là đã giao cho endpoint. Do đó, **`send()==true` không đồng nghĩa đơn hàng đã được chấp nhận về mặt nghiệp vụ**. Nếu Gateway/API cần trả kết quả reject rõ ràng, hãy thiết kế một đường reply/error riêng, không suy diễn từ giá trị boolean của `MessageChannel.send()`.

### 11.2. Error channel hoạt động khác discard channel

- **Discard channel:** nhận message bị Filter từ chối theo một quyết định chọn/lọc có chủ đích.
- **Error channel:** nơi lỗi của hệ thống messaging/handler có thể được gửi, đặc biệt trong luồng bất đồng bộ hoặc thông qua cơ chế error handling được cấu hình.
- **Exception trong flow đồng bộ:** có thể được ném về thread caller; không có nghĩa cứ khai báo error channel là mọi lỗi đồng bộ tự được chuyển sang đó.
- **Rejected event:** một sự kiện nghiệp vụ do ứng dụng tạo ra với mã lỗi/giải thích, phù hợp nếu cần xử lý phản hồi theo domain.

Chọn đúng nhánh dựa trên ý nghĩa, rồi kiểm thử topology thực. Nếu muốn log lỗi có cấu trúc, hãy ghi mã `VALIDATION_FAILED`, loại message, nguồn và correlation ID; tránh log cả payload raw.

## 12. Cập nhật và mở rộng hợp đồng validation

Khi có nhiều producer và consumer, schema có thể thay đổi theo thời gian:

- Bổ sung field **optional** có default rõ ràng sẽ ít gây gián đoạn hơn đổi kiểu field bắt buộc.
- Có thể dùng `schemaVersion` hoặc cơ chế schema registry để định tuyến validation theo phiên bản.
- Không chấp nhận mọi field lạ một cách mù quáng khi yêu cầu bảo mật cần whitelist; quy tắc unknown fields tùy định dạng và converter.
- Kiểm thử tương thích giữa producer v1/v2 và validator consumer ở các ranh giới.
- Không biến một lỗi version cố định thành retry vô hạn; định tuyến tới quarantine/reject với đầy đủ thông tin để replay sau khi cập nhật hợp đồng.

Ví dụ, ở phiên bản v2 yêu cầu `currency` nhưng v1 không có: có thể đặt default theo chính sách đã phê duyệt, chuyển đổi một cách có kiểm soát hoặc đưa v1 vào flow riêng. Đừng tự suy ra đơn vị tiền tệ từ `amount`.

## 13. Validation và hiệu năng trong hệ thống có tải cao

Validation gần ingress tiết kiệm chi phí cho những message bị loại sớm, nhưng bản thân nó cũng tiêu tốn CPU/bộ nhớ. Một số nguyên tắc:

1. Giới hạn **kích thước bytes và độ phức tạp parse** trước khi cấp phát DTO lớn.
2. Dùng validator bean dùng chung, tránh khởi tạo factory cho từng message.
3. Tách kiểm tra thuần dữ liệu nhanh khỏi kiểm tra cần I/O; đưa truy vấn DB hoặc API vào bước có timeout/cache và transaction phù hợp.
4. Đừng chạy lại cùng một validation tốn kém ở mọi handler khi các bước cùng thuộc một trust boundary và contract đã được bảo toàn.
5. Sau khi qua ranh giới hệ thống/nguồn mới, kiểm tra lại phần contract cần tin cậy.
6. Dùng metric như `accepted_count`, `validation_reject_count`, `decode_failure_count`, `error_count` và latency theo giai đoạn, nhưng tránh đưa ID người dùng thành metric label có cardinality lớn.
7. Nếu pipeline async, hạn chế concurrency và kích thước queue; validation không tự tạo backpressure hay bảo đảm delivery.

Ở hệ thống an toàn, việc từ chối một request quá lớn **trước khi parse** là bổ sung cần thiết cho Bean Validation. `@Size(max=64)` trên `orderId` không thể bảo vệ server khỏi một body hàng trăm MB đang được đọc.

## 14. Kiểm thử tích hợp qua channel thực

Có hai lớp kiểm thử khác nhau:

- **Unit test của Validator:** kiểm tra danh sách constraint cho `OrderRequest` cụ thể.
- **Integration test của flow:** gửi một `Message<OrderRequest>` qua `orders.received`, xác nhận message hợp lệ tới `orders.accepted`, message bị từ chối tới `orders.rejected`, headers được bảo toàn, và nhánh nghiệp vụ không nhận dữ liệu sai.

Đoạn test dưới đây minh họa đầy đủ với Java 17+, JUnit Jupiter 5, Spring Integration và Spring Test. Nó không yêu cầu khởi động HTTP server.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@SpringJUnitConfig(classes = OrderIngressValidationTest.Config.class)
class OrderIngressValidationTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("orders.received")
        DirectChannel received() {
            return new DirectChannel();
        }

        @Bean("orders.accepted")
        QueueChannel accepted() {
            return new QueueChannel();
        }

        @Bean("orders.rejected")
        QueueChannel rejected() {
            return new QueueChannel();
        }

        @Bean
        LocalValidatorFactoryBean validator() {
            return new LocalValidatorFactoryBean();
        }

        @Bean
        Gate gate(Validator validator) {
            return new Gate(validator);
        }
    }

    static class Gate {
        private final Validator validator;

        Gate(Validator validator) {
            this.validator = validator;
        }

        @Filter(
                inputChannel = "orders.received",
                outputChannel = "orders.accepted",
                discardChannel = "orders.rejected")
        public boolean allow(OrderRequest payload) {
            return validator.validate(payload).isEmpty();
        }
    }

    @Autowired
    @Qualifier("orders.received")
    MessageChannel received;

    @Autowired
    @Qualifier("orders.accepted")
    PollableChannel accepted;

    @Autowired
    @Qualifier("orders.rejected")
    PollableChannel rejected;

    @Test
    void validOrderReachesAcceptedChannel() {
        OrderRequest input = new OrderRequest(
                "order-1001",
                new BigDecimal("120.50"),
                "NORTH",
                "buyer@example.com");

        assertTrue(received.send(
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> output = accepted.receive(1000);
        assertNotNull(output);
        assertEquals(input, output.getPayload());
        assertEquals("trace-1001", output.getHeaders().get("traceId"));
        assertNull(rejected.receive(0));
    }

    @Test
    void invalidOrderGoesToRejectChannel() {
        OrderRequest input = new OrderRequest(
                "order-1002",
                BigDecimal.ZERO,
                "NORTH",
                "buyer@example.com");

        received.send(
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1002")
                        .build());

        Message<?> discarded = rejected.receive(1000);
        assertNotNull(discarded);
        assertEquals(input, discarded.getPayload());
        assertEquals("trace-1002",
                discarded.getHeaders().get("traceId"));
        assertNull(accepted.receive(0));
    }
}
~~~

Ở đây, `OrderRequest` là record đã định nghĩa ở mục 5, `@Filter` nhận payload được decode và sử dụng `jakarta.validation.Validator`. Các `QueueChannel` được dùng **cho test** để quan sát output; trong ứng dụng thật, channel tiếp theo thường nối tới các endpoint nghiệp vụ và kênh rejected có handler xử lý riêng.

Kết quả mong đợi:

| Input | `orders.accepted` | `orders.rejected` |
|---|---|---|
| `amount=120.50` | Có một message | Không có |
| `amount=0` | Không có | Có một message |
| `orderId="   "` | Không có | Có một message |
| JSON không parse được | Không đi tới Filter vì lỗi ở bước decode | Xử lý bởi error flow của adapter/converter |

**Lưu ý:** test này xác minh việc phân nhánh của Filter, chưa kiểm thử HTTP status hay hệ thống broker. Nếu muốn chứng minh dữ liệu sai không gây side effect, bổ sung một handler sau `orders.accepted` có counter/fake repository và assert nó không được gọi khi message bị reject.

### 14.1. Kiểm thử Validator đơn lẻ

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

// Có thể dùng lại Config trong test trước.
@SpringJUnitConfig(classes = OrderIngressValidationTest.Config.class)
class OrderRequestValidatorTest {

    @Autowired
    Validator validator;

    @Test
    void zeroAmountIsInvalid() {
        OrderRequest order = new OrderRequest(
                "order-1002",
                BigDecimal.ZERO,
                "NORTH",
                "buyer@example.com");

        var violations = validator.validate(order);

        assertFalse(violations.isEmpty());
        assertTrue(violations.stream().anyMatch(v ->
                "amount".equals(v.getPropertyPath().toString())));
    }
}
~~~

Test unit validator cho thấy **tại sao** payload sai, còn test flow cho thấy **nó bị đưa đến đâu**. Hai loại test bổ sung cho nhau.

### 14.2. Kiểm thử thêm các đường lỗi

Trong môi trường có Gateway/adapter thực, nên bổ sung:

- Parser ném lỗi vì JSON không hợp lệ; không có lệnh ghi DB phía sau.
- Header `tenantId` do client đưa vào không thay được tenant được xác thực.
- Một message có phiên bản schema không hỗ trợ đi đến reject/quarantine.
- Exception từ endpoint validation được xử lý đúng trong cấu hình đồng bộ và bất đồng bộ.
- Có `traceId` ở cả nhánh accepted, rejected và error flow theo chính sách.
- Retry không lặp vô hạn trên lỗi dữ liệu cố định; transient error có giới hạn và idempotency.
- Payload lớn bị từ chối trước khi cấp phát cấu trúc object lớn.

## 15. Tình huống thực tế: nhận sự kiện từ nhiều nguồn

Một hệ thống đặt hàng nhận `OrderCreated` qua REST và Kafka. Dù payload sau decode có thể được ánh xạ về cùng `OrderRequest`, trust boundary của hai nguồn khác nhau.

~~~mermaid
flowchart TB
    H["HTTP adapter"] --> HV["Size / auth / parse / validate"]
    K["Kafka inbound"] --> KV["Schema / producer trust / parse / validate"]
    HV --> N["Normalized internal OrderRequest"]
    KV --> N
    N --> C["MessageChannel: orders.ready"]
    C --> R{"Router: region"}
    R --> A["Order handler NORTH"]
    R --> B["Order handler SOUTH"]
    A --> DB["Transactional business write"]
    B --> DB
    HV -->|reject| RJ["API error response"]
    KV -->|reject| Q["Quarantine / dead-letter policy"]
~~~

Điểm khác biệt:

- REST thường có **caller đang chờ phản hồi**. Khi validation fail, API adapter có thể trả lỗi rõ ràng như HTTP 400 hoặc 422 theo contract.
- Consumer Kafka không thể “trả HTTP 400” cho producer. Cần quyết định ack/offset, dead-letter topic, quarantine và replay theo chính sách của consumer/broker.
- Một lỗi parse cố định không nên retry vô hạn và chặn partition.
- Khi cả hai nguồn nhập vào luồng nội bộ, payload chuẩn hóa phải có contract nhất quán, nhưng thông tin xác thực và quyền truy cập phải được diễn giải đúng theo nguồn.
- Trước side effect, handler nghiệp vụ vẫn cần kiểm tra trạng thái hiện tại và bảo đảm tính toàn vẹn transaction.

Một mô hình triển khai thường gặp là tách **adapter-specific validation** (HTTP, broker) khỏi **common application validation** (DTO/invariant) rồi ghép ở channel nội bộ. Điều này giữ sự độc lập giữa framework giao tiếp và logic nghiệp vụ.

## 16. Các lỗi thường gặp

### 16.1. Validation đặt sau side effect

**Triệu chứng:** lệnh ghi DB hoặc gửi email đã chạy trước khi hệ thống biết `amount` không hợp lệ.

**Cách sửa:** đưa parse/structural validation lên ngay sau ingress; business invariants cần transaction được kiểm tra trước khi ghi trạng thái tương ứng.

### 16.2. Dùng Transformer để lọc bằng null

**Triệu chứng:** Transformer trả `null`, endpoint ném exception và message không được loại như mong đợi.

**Cách sửa:** dùng `Filter` với `discardChannel` cho hành vi reject bình thường; dùng exception nếu input vi phạm hợp đồng cần báo lỗi.

### 16.3. Filter reject nhưng không ai quan sát

**Triệu chứng:** một số đơn hàng không thấy downstream, producer tưởng đã gửi thành công.

**Cách sửa:** định nghĩa rejected channel, metric và cách trả kết quả cho caller; kiểm thử routing reject. Không suy diễn `MessageChannel.send()==true` là xử lý nghiệp vụ thành công.

### 16.4. Xem tất cả lỗi đều có thể retry

**Triệu chứng:** message có `amount=-1` được retry hàng trăm lần, chiếm queue.

**Cách sửa:** phân loại lỗi dữ liệu cố định, lỗi nghiệp vụ và lỗi tạm thời; chỉ retry những lỗi có triển vọng hồi phục, đặt backoff và số lần tối đa.

### 16.5. Dùng validation để thay thế authorization

**Triệu chứng:** payload có `tenantId` đúng format nhưng là tenant khác, khiến handler truy cập nhầm dữ liệu.

**Cách sửa:** xác minh principal/tenant từ ngữ cảnh đáng tin cậy, ràng buộc quyền trước side effect và tại transaction cần thiết.

### 16.6. Sao chép mù toàn bộ headers

**Triệu chứng:** metadata nhạy cảm hoặc header về payload version cũ được truyền sang nhánh không phù hợp.

**Cách sửa:** xác định header contract, sử dụng whitelist tại ranh giới tin cậy mới; kiểm tra quy tắc truyền header khi Transformer trả `Message` đầy đủ.

### 16.7. Duplicate validation và phụ thuộc dữ liệu mutable

**Triệu chứng:** ba handler chạy validation giống nhau, kết quả có thể khác vì payload bị mutate trong lúc xử lý bất đồng bộ.

**Cách sửa:** chuẩn hóa/validate trong bước chung trước fan-out, phát payload bất biến hoặc defensive copy; chỉ kiểm tra lại bất biến phụ thuộc ngữ cảnh của từng consumer.

## 17. Bài tập thực hành

**Bài 1 — Admission filter cơ bản.** Tạo `OrderRequest` với constraints như mục 5, cấu hình input channel `orders.received`, output `orders.accepted` và discard `orders.rejected`. Gửi ba message: hợp lệ, thiếu `orderId` và `amount=0`. Assert đường đi của từng message.

**Bài 2 — Validation result có mã lỗi.** Thay cách trả boolean bằng cấu trúc `ValidationResult`. Gắn các mã lỗi ổn định `ORDER_ID_REQUIRED`, `AMOUNT_TOO_SMALL` và `REGION_UNSUPPORTED`. Router phân nhánh theo `valid()`. Thử thêm một field mới và bảo đảm client cũ không nhận dữ liệu nhạy cảm trong response.

**Bài 3 — Parse error khác validation reject.** Gửi một chuỗi JSON sai cú pháp và một JSON đúng cú pháp nhưng thiếu `amount`. Xác định đoạn code chịu trách nhiệm cho từng lỗi và minh họa kết quả quan sát. Không coi parse failure là một Filter reject nếu message chưa được decode thành `OrderRequest`.

**Bài 4 — Correlation và tracing.** Gắn `traceId` cho message hợp lệ và bị từ chối, assert còn giữ được giá trị qua endpoint. Nếu Transformer trả một `Message` hoàn chỉnh, viết test chứng minh nó không tự giữ headers không được copy.

**Bài 5 — Hệ thống bất đồng bộ.** Đặt một `ExecutorChannel` sau validation. Thử message có lỗi cố định và một lỗi tạm thời ở handler khác; cấu hình retry cho lỗi thứ hai, đo số lần xử lý và giải thích đường đi của exception. Bảo đảm validation reject không bị retry lặp vô ích.

**Bài 6 — Kiểm thử ranh giới tin cậy.** Giả lập header `tenantId` do client gửi khác với tenant lấy từ principal đã xác thực. Chứng minh flow không sử dụng giá trị client cho quyết định truy cập. Bổ sung một nhánh nhận response từ đối tác và validate response trước khi update DB.

### Câu hỏi tự kiểm tra

1. Vì sao validation nên đặt trước Router/handler có side effect?
2. JSON parse error và Bean Validation failure khác nhau ở bước nào?
3. Khi nào Filter với discard channel thích hợp hơn exception?
4. Nếu Filter trả `false` mà không cấu hình discard, hệ thống quan sát message bị reject như thế nào?
5. Khi nào validation ở ingress vẫn chưa đủ để bảo đảm business invariant?
6. Vì sao `tenantId` đúng format không đồng nghĩa caller đã được cấp quyền?
7. Nếu Transformer trả `Message<?>` mà không copy headers, chuyện gì có thể xảy ra với trace/correlation?
8. Vì sao retry lỗi `amount=-1` là phản tác dụng?
9. Cần kiểm thử điều gì để khẳng định rejected message không chạm tới database?
10. Nếu Kafka consumer nhận schema không hỗ trợ, một đường quarantine/replay nên giữ metadata nào?

## 18. Checklist áp dụng

- [ ] Đã xác định các trust boundary và hợp đồng payload/header tại mỗi điểm nhận.
- [ ] Có giới hạn kích thước/timeouts ở adapter/decoder trước khi parse.
- [ ] DTO có validation phù hợp về null, kiểu, độ dài và khoảng giá trị.
- [ ] Validation/normalization đặt trước tác vụ tốn kém và side effect không cần thiết.
- [ ] Filter dùng cho quyết định chọn/loại; Transformer dùng để đổi payload; lỗi được phân loại riêng.
- [ ] Rejected message có đường xử lý và được đo lường, không bị bỏ im lặng ngoài ý muốn.
- [ ] Authorization dùng ngữ cảnh đáng tin cậy, không tin header do bên ngoài tự khai báo.
- [ ] Business invariants phụ thuộc state được kiểm tra tại transaction phù hợp.
- [ ] Header trace/correlation và metadata được phép được giữ xuyên validation và reject.
- [ ] Retry chỉ áp dụng cho lỗi có thể hồi phục, có idempotency và giới hạn.
- [ ] Test cả accepted, rejected, parse failure, authorization failure và error flow.
- [ ] Với nguồn Kafka/JMS/HTTP, đã xác định riêng hành vi ack, reply, dead-letter hoặc quarantine.
- [ ] Hệ thống giám sát tỷ lệ reject và lỗi mà không tiết lộ dữ liệu nhạy cảm.

## 19. Tổng kết

**Đặt validation gần nơi nhận dữ liệu** giúp một luồng Pipes and Filters giữ hợp đồng rõ ràng từ đầu: message hợp lệ đi tới các bước nghiệp vụ, còn message sai được phân loại và xử lý đúng điểm. Trong Spring Integration, `Filter` thích hợp cho hành vi accept/reject; `Transformer` tạo biểu diễn dữ liệu nhất quán; `Router` phân nhánh; còn exception/error flow phục vụ tình huống cần báo lỗi.

Nguyên tắc quan trọng là đặt **đúng loại kiểm tra ở đúng ranh giới**. Giới hạn tài nguyên và parse trước DTO, kiểm tra cấu trúc/ngữ nghĩa sớm, xác thực quyền từ nguồn tin cậy, và giữ business invariants phụ thuộc state sát transaction của chúng. Hãy đo lường các nhánh reject, bảo toàn trace/correlation phù hợp và kiểm thử cả hành vi thành công lẫn thất bại. Nhờ đó, Router, Filter, Transformer, Splitter/Aggregator, Gateway, retry và error channel có thể phối hợp trong luồng ít phụ thuộc, dễ quan sát và dễ mở rộng.

### Tài liệu tham khảo

- Spring Integration Reference — Message Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Framework Reference — Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Jakarta Bean Validation specification: https://jakarta.ee/specifications/bean-validation/

