# Mô hình API, annotation và ngữ cảnh ảnh hưởng kết quả

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích tại sao **kết quả kiểm tra tự động** phụ thuộc không chỉ vào đoạn mã được kiểm tra, mà còn vào **hợp đồng API, annotation, cấu hình công cụ và ngữ cảnh thực thi**.
2. Phân biệt kiểm tra được thực hiện bởi **trình biên dịch**, **công cụ phân tích tĩnh**, **annotation processor**, **framework lúc chạy** và **test tích hợp**.
3. Xác định điều một annotation **khẳng định**, **hướng dẫn** hoặc **thực sự được thực thi**, tránh nhầm metadata với bảo đảm hành vi.
4. Thiết kế mô hình dữ liệu API và miền nghiệp vụ để lỗi định dạng, giá trị, trạng thái và quyền được kiểm tra tại đúng ranh giới.
5. Viết test Java/JUnit cho cả hợp đồng của mô hình và đường đi qua framework, đồng thời nhận diện **false positive**, **false negative** và chỗ thiếu ngữ cảnh.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu các thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Kiểm tra tự động**, chúng ta quan tâm đến cách công cụ giúp phát hiện sai lệch sớm và nhất quán.

Một dòng Java có thể được trình biên dịch chấp nhận, công cụ phân tích tĩnh báo cảnh báo, unit test vượt qua nhưng API vẫn trả kết quả sai khi chạy với cấu hình thật. Điều này không nhất thiết có nghĩa công cụ “hỏng”. Có thể mỗi công cụ đang thấy **một mô hình khác nhau của chương trình** và chỉ kiểm tra những thuộc tính nằm trong phạm vi của nó.

**Ý chính:** Annotation và tên phương thức không tự biến một lời hứa thành bảo đảm. Muốn tin kết quả kiểm tra, cần biết **ai đọc hợp đồng, đọc ở thời điểm nào, ở ranh giới nào và kiểm chứng điều gì**.

## 1. “Mô hình API” nghĩa là gì trong kiểm tra tự động?

Một API không chỉ gồm tên phương thức và kiểu tham số. Nó còn có **ngữ nghĩa, tiền điều kiện, hậu điều kiện, lỗi và tác dụng phụ**.

Ví dụ về một lời gọi tìm sản phẩm:

~~~java
interface ProductCatalog {
    java.util.Optional<Product> findBySku(String sku);
}
~~~

Chữ ký cho biết:
- Đầu vào là một **String**.
- Đầu ra là một **Optional<Product>**.
- Người gọi phải xử lý khả năng không có kết quả.

Nhưng chữ ký chưa nói rõ:
- **sku = null** có được phép không?
- SKU có phân biệt hoa/thường không?
- Giá trả về có đơn vị tiền gì?
- Truy vấn có thể gọi HTTP/DB và timeout không?
- Dữ liệu có thể cũ do cache không?
- Có được gọi đồng thời không?
- Khi dịch vụ phụ thuộc lỗi, API trả Optional.empty hay ném ngoại lệ?

Nếu người viết code giả định **Optional.empty()** cũng biểu thị lỗi mạng, một lỗi hạ tầng có thể bị ngụy trang thành “sản phẩm không tồn tại”. Nếu công cụ phân tích chỉ biết kiểu Optional, nó không thể tự phát hiện mọi sai lệch ngữ nghĩa này.

### Các tầng của mô hình

| Tầng mô hình | Điều mô tả | Ví dụ | Ai có thể kiểm tra? |
| --- | --- | --- | --- |
| **Kiểu Java** | Kiểu tham số, kết quả, khả năng gọi phương thức | **String**, **Optional<Product>** | Trình biên dịch |
| **Hợp đồng null/miền giá trị** | Giá trị được phép và bất biến | SKU không rỗng, quantity dương | Static analyzer có cấu hình, validator, unit test |
| **Hợp đồng giao thức** | JSON field, HTTP status, header, schema | **product_code**, HTTP 404, phiên bản API | Serializer, API contract/integration test |
| **Hợp đồng hành vi** | Kết quả và tác dụng phụ với từng tình huống | Không gửi lệnh thanh toán cho đơn lỗi | Unit/integration test và code review |
| **Hợp đồng vận hành** | Timeout, retry, transaction, cache, đồng thời | Gọi DB trong transaction, deadline 2 giây | Framework/runtime, test tích hợp và quan sát |
| **Hợp đồng bảo mật** | Chủ thể nào được phép làm gì trên tài nguyên nào | Chỉ chủ đơn được hủy đơn | Kiểm tra quyền và test API |

Cùng một đoạn mã có thể **đạt** tầng kiểm tra kiểu nhưng **không đạt** tầng hợp đồng nghiệp vụ. Bài học không khuyến khích một công cụ duy nhất đảm nhiệm tất cả, mà giúp thiết kế **nhiều lớp kiểm chứng có mục đích**.

## 2. Một annotation có thể mang nhiều loại ý nghĩa

**Annotation** trong Java gắn metadata lên lớp, phương thức, field, tham số, kiểu sử dụng hoặc phần tử khác theo khai báo của annotation. Tác dụng thực tế phụ thuộc vào **định nghĩa annotation** và **công cụ/framework có đọc nó hay không**.

Ví dụ:

~~~java
@Override
public String toString() {
    return "example";
}
~~~

**@Override** yêu cầu trình biên dịch kiểm tra phương thức thực sự ghi đè hoặc triển khai một phương thức thích hợp. Nhưng **@Override không quy định nội dung toString() có diễn đạt đúng đối tượng hay không**.

Một ví dụ khác:

~~~java
@Deprecated
public void oldOperation() {
    // ...
}
~~~

**@Deprecated** giúp công cụ và trình biên dịch cảnh báo khi phần tử bị dùng theo những điều kiện tương ứng. Nó không tự ngăn phương thức được gọi, xóa phương thức cũ hoặc bảo đảm mã thay thế tồn tại.

### Phân loại theo bên thực thi

| Nhóm annotation | Ví dụ | Bên xử lý thường gặp | Điều không được suy diễn |
| --- | --- | --- | --- |
| **Được trình biên dịch hiểu** | **@Override**, **@SuppressWarnings** | Java compiler và một số công cụ liên quan | Không kiểm tra mọi yêu cầu nghiệp vụ |
| **Metadata vòng đời/retention** | **@Retention**, **@Target** | Compiler và cơ chế annotation/reflection | Không tự gọi một validator |
| **Kiểm tra ràng buộc dữ liệu** | **@NotNull**, **@NotBlank**, **@Min**, **@Valid** | Jakarta Bean Validation khi được kích hoạt | Không có nghĩa mọi đối tượng đều luôn được validate |
| **Ánh xạ giao thức** | **@JsonProperty** của Jackson | Object mapper được cấu hình để đọc annotation | Không tự bảo đảm client dùng đúng schema |
| **Giao dịch/khía cạnh** | **@Transactional** của Spring | Transaction infrastructure/proxy được cấu hình | Không bảo đảm mọi lời gọi tới phương thức đều đi qua proxy |
| **Ánh xạ dữ liệu lưu trữ** | **@Column(nullable = false)** của JPA | ORM/schema tooling tùy cấu hình | Không chứng minh database hiện có ràng buộc tương ứng |
| **Phân tích null/kiểu mở rộng** | Một số annotation nullness của thư viện | Static analyzer hỗ trợ cùng mô hình | Không mặc nhiên được Java compiler chuẩn thực thi |
| **Sinh mã** | Annotation dùng bởi annotation processor | Processor trong quá trình build | Không bảo đảm mã sinh đã chạy đúng ở runtime |
| **Kiểm thử** | **@Test** của JUnit Jupiter | JUnit engine/discovery và runner | Không bảo đảm test được phát hiện/chạy nếu cấu hình runner sai |

**Một tên annotation không phải hợp đồng độc lập với môi trường.** Ví dụ, **@NotNull** có thể đến từ các package khác nhau với trình xử lý và ngữ nghĩa khác nhau. Khi review phải biết **import nào**, **công cụ nào** và **phạm vi áp dụng nào**.

## 3. Retention, target và đường đi của annotation

Java định nghĩa một số **retention policy** phổ biến:

- **SOURCE:** metadata phục vụ mã nguồn/biên dịch, không được lưu lại trong class file để truy vấn lúc chạy.
- **CLASS:** annotation có thể được ghi trong class file, nhưng không mặc định sẵn qua reflection ở runtime.
- **RUNTIME:** annotation được giữ để cơ chế reflection tại runtime có thể nhìn thấy.

**@Target** xác định annotation có thể gắn ở đâu, chẳng hạn **TYPE**, **METHOD**, **FIELD**, **PARAMETER**, **RECORD_COMPONENT** hoặc **TYPE_USE**, tùy định nghĩa.

Ví dụ tự tạo:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiresAudit {
    String action();
}

final class AccountCommands {
    @RequiresAudit(action = "TRANSFER")
    void transfer() {
        // Ví dụ phương thức; chưa có mã ghi audit.
    }
}
~~~

Tại runtime, reflection có thể tìm **@RequiresAudit** trên phương thức. Nhưng **không có đoạn mã nào tự động ghi audit chỉ vì annotation xuất hiện**. Muốn ràng buộc này có tác dụng, cần có cơ chế intercept hoặc thành phần thực thi đọc metadata và kiểm tra/ghi nhận hành vi. Nếu không, annotation chỉ là lời mô tả.

### Annotation không đồng nghĩa code đã được kiểm tra

Một chuỗi suy luận sai thường gặp:

1. “Tôi đã thêm **@NotNull**.”
2. “Vậy chương trình không thể có null.”
3. “Nếu test xanh, mọi đường vào đều an toàn.”

Ở bước 2 và 3, người viết đã bỏ qua **ai kiểm tra** và **khi nào kiểm tra**. Với Jakarta Bean Validation, đối tượng chỉ được kiểm tra khi một **validator** được gọi hoặc một framework tích hợp được cấu hình kích hoạt quá trình ấy.

~~~mermaid
flowchart LR
    A[Annotation trên mã] --> B{Có bên xử lý?}
    B -- Không --> C[Chỉ là metadata hoặc dấu hiệu]
    B -- Có --> D{Xử lý ở giai đoạn nào?}
    D --> E[Compiler / static analysis]
    D --> F[Annotation processor]
    D --> G[Runtime framework / reflection]
    E --> H[Kết quả kiểm tra trong phạm vi công cụ]
    F --> H
    G --> H
~~~

Mỗi nhánh có giới hạn riêng. Trình biên dịch không biết nội dung của một bảng giá lúc 14 giờ; validator không tự chứng minh một transaction đã commit; test đơn vị với stub không kiểm tra JSON serializer thật.

## 4. API boundary: DTO và mô hình miền có nhiệm vụ khác nhau

Trong một dịch vụ đặt hàng, dữ liệu đầu vào có thể đi qua:

~~~mermaid
flowchart LR
    A[JSON request] --> B[Deserializer]
    B --> C[API DTO]
    C --> D[Validation tại ranh giới]
    D --> E[Application service]
    E --> F[Mô hình miền / bất biến]
    F --> G[Repository / API ngoài]
    G --> H[Database / Service]
~~~

**API DTO** mô tả hình dạng dữ liệu ở ranh giới HTTP: tên trường, kiểu và ràng buộc cơ bản. **Mô hình miền** bảo vệ những điều kiện đúng đắn không được phép bị bỏ qua, bất kể đối tượng được tạo từ HTTP, message broker, job nền hay code nội bộ.

Nếu mọi bất biến chỉ tồn tại ở annotation của controller, một job nền tạo domain object trực tiếp có thể đi vòng qua validation. Ngược lại, chỉ kiểm tra trong domain constructor vẫn chưa giải quyết được lỗi JSON mapping, tên trường API, HTTP status hay giới hạn kích thước request.

### Ví dụ Jakarta Bean Validation cho DTO

Giả sử API chấp nhận một mã SKU bắt buộc và số lượng từ 1 đến 100:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) @Max(100) Integer quantity) {
}
~~~

Các ràng buộc có ý nghĩa khác nhau:

| Annotation | Kiểm tra chính | Điểm cần chú ý |
| --- | --- | --- |
| **@NotNull** | Giá trị không được null | Không cấm chuỗi rỗng hoặc chỉ toàn khoảng trắng |
| **@NotBlank** | Chuỗi ký tự có ít nhất một ký tự không phải whitespace theo validator | Dành cho chuỗi, không phải mọi kiểu dữ liệu |
| **@NotEmpty** | Container/chuỗi phù hợp không null và không rỗng | Không mặc nhiên cấm chuỗi chỉ có khoảng trắng |
| **@Min(1)** | Số không nhỏ hơn 1 | Trong Bean Validation, **null được xem là hợp lệ** cho constraint này; cần ghép **@NotNull** nếu bắt buộc |
| **@Max(100)** | Số không lớn hơn 100 | Không tự quyết định số lượng tối đa theo tồn kho thực |
| **@Size(...)** | Kích thước của kiểu được hỗ trợ trong phạm vi validator | Không đồng nhất với giới hạn byte hay số ký tự hiển thị |
| **@Pattern(...)** | Chuỗi khớp một biểu thức chính quy | Không xác nhận SKU có trong catalog |
| **@Valid** | Yêu cầu validate theo tầng đối tượng lồng nhau | Phải có quá trình validation được kích hoạt |

Với **Integer** thay vì **int**, thiếu trường **quantity** có thể được biểu diễn bằng null để **@NotNull** phát hiện sau khi mapping, tùy cách cấu hình deserializer. Nếu dùng **int** và dữ liệu bị bỏ trống, việc binding có thể cho ra giá trị mặc định hoặc lỗi mapping tùy cơ chế; không nên suy diễn một hành vi mà chưa thử trên cấu hình thật.

**Lưu ý:** Jakarta Bean Validation cung cấp đặc tả và API; cần một **provider** phù hợp trên classpath, chẳng hạn Hibernate Validator, và cần gọi validator hoặc dùng tích hợp framework. Đoạn code trên **không tự kiểm tra khi chỉ gọi constructor**.

## 5. Thực thi validator: kết quả phụ thuộc điểm gọi

Unit test sau kiểm tra các ràng buộc bằng validator thật thay vì chỉ nhìn annotation:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

class CreateOrderRequestValidationTest {

    @Test
    void rejectsMissingOrOutOfRangeFields() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            CreateOrderRequest input =
                    new CreateOrderRequest(" ", 0);

            var violations = validator.validate(input);

            assertEquals(2, violations.size());
            assertTrue(violations.stream().anyMatch(v ->
                    v.getPropertyPath().toString().equals("sku")));
            assertTrue(violations.stream().anyMatch(v ->
                    v.getPropertyPath().toString().equals("quantity")));
        }
    }

    @Test
    void allowsValidShapeButDoesNotCheckBusinessCatalog() {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            CreateOrderRequest input =
                    new CreateOrderRequest("UNKNOWN-SKU", 2);

            assertTrue(validator.validate(input).isEmpty());
        }
    }
}
~~~

Mã kiểm thử cần có **JUnit Jupiter**, **Jakarta Validation API** và **provider hỗ trợ** trong cấu hình build. Bài học này không chạy build và không giả định dự án đã cài các thư viện đó.

Test thứ nhất xác nhận hai ràng buộc DTO. Test thứ hai cố ý cho thấy **validation đúng định dạng chưa xác nhận SKU tồn tại**; việc tra catalog cần thực hiện ở tầng nghiệp vụ/tích hợp thích hợp.

Một sai sót cần tránh là nghĩ rằng:

~~~java
new CreateOrderRequest("", 0);
~~~

sẽ tự ném lỗi chỉ vì record component có annotation. Nếu constructor không chứa kiểm tra riêng, Java vẫn có thể tạo record; lỗi chỉ xuất hiện khi **validator thực sự được gọi** hoặc một framework thực thi validation tại ranh giới.

## 6. Domain invariants: bảo vệ giá trị ngay cả khi không đi qua HTTP

Mô hình miền có thể đặt các bất biến thiết yếu trong constructor hoặc factory. Điều đó bổ sung cho API validation, chứ không bắt buộc sao chép toàn bộ quy tắc ở mọi nơi.

~~~java
import java.util.Objects;

record OrderCommand(String sku, int quantity) {
    OrderCommand {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be from 1 to 100");
        }
    }
}

final class CreateOrderMapper {
    static OrderCommand toCommand(CreateOrderRequest request) {
        Objects.requireNonNull(request, "request");
        // Kiểm tra lại để không phụ thuộc hoàn toàn vào
        // việc một framework đã gọi Bean Validation.
        if (request.quantity() == null) {
            throw new IllegalArgumentException("quantity is required");
        }
        return new OrderCommand(request.sku(), request.quantity());
    }
}
~~~

**OrderCommand** không thể được tạo với quantity = 0 thông qua constructor này. Đây là một bảo đảm ở mức Java, bất kể nguồn đến là REST API, message hoặc unit test. Trong khi đó, **CreateOrderRequest** vẫn phục vụ mapping và báo lỗi hợp lý ở ranh giới API.

Đây không phải lời khuyên lặp lại mọi kiểm tra ở mọi lớp. Nên phân vai:

- **Deserializer và DTO validation:** kiểm tra cấu trúc, trường bắt buộc, giới hạn format để trả lỗi đầu vào rõ ràng.
- **Domain model:** bảo vệ những bất biến **luôn phải đúng** với đối tượng.
- **Application service:** xác nhận trạng thái hiện tại, quyền, tồn kho và điều kiện liên quan tới dữ liệu đang thay đổi.
- **Adapter và database:** tham số hóa truy vấn, kiểm soát transaction và thực thi ràng buộc lưu trữ.

Một annotation **@Valid** không thể thay thế transaction hoặc điều kiện cập nhật tồn kho nguyên tử. Tất cả các lớp trên có thể cần phối hợp để đảm bảo kết quả đáng tin cậy.

## 7. Khi framework nhận request: cùng DTO nhưng đường thực thi khác nhau

Ví dụ minh họa với **Spring MVC** và Jakarta Bean Validation:

~~~java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
final class OrderController {
    private final OrderApplicationService service;

    OrderController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        OrderCommand command = CreateOrderMapper.toCommand(request);
        return service.create(command);
    }
}
~~~

**OrderApplicationService** và **OrderResponse** là các thành phần ứng dụng giả định, được lược bỏ khỏi ví dụ. Mã cần được đặt trong dự án có Spring MVC cùng tích hợp Bean Validation phù hợp; không phải ví dụ chỉ dùng JDK.

Ở đường đi HTTP thông thường đã được cấu hình đúng, framework có thể:
1. Đọc request body theo converter tương ứng.
2. Mapping JSON vào **CreateOrderRequest**.
3. Kích hoạt Bean Validation do **@Valid**.
4. Trả lỗi đầu vào theo cơ chế xử lý lỗi nếu có vi phạm.
5. Chỉ gọi logic controller/application khi dữ liệu qua ranh giới hợp lệ.

Nhưng nếu một đoạn code nội bộ gọi trực tiếp:

~~~java
controller.create(new CreateOrderRequest(" ", 0));
~~~

thì **không nên giả định** lời gọi Java trực tiếp đó sẽ tự đi qua toàn bộ pipeline MVC. Việc tạo DTO hay gọi method trực tiếp không đồng nghĩa framework đã kích hoạt validator.

### Những yếu tố thay đổi kết quả

| Ngữ cảnh | Điều cần kiểm tra | Rủi ro khi bỏ qua |
| --- | --- | --- |
| **HTTP qua Spring MVC** | Có converter, provider validation, **@Valid** và handler lỗi phù hợp không? | Dữ liệu đi qua API nhưng constraint không được kiểm tra |
| **Gọi phương thức trực tiếp trong unit test** | Test có gọi validator hay domain constructor không? | Test xanh khi đường HTTP thực bị cấu hình sai hoặc ngược lại |
| **Message consumer** | Có bước validation ở handler hay mapper không? | Nhánh bất đồng bộ bỏ qua kiểm tra ở controller |
| **Scheduled job** | Dữ liệu từ DB/nguồn cũ có được kiểm chứng khi cần không? | Xử lý trạng thái sai hoặc schema cũ |
| **Internal API giữa module** | Có cùng hợp đồng miền, lỗi và quyền không? | Module bỏ qua bất biến khi tự dựng object |
| **Legacy data migration** | Có dữ liệu không còn hợp lệ với quy tắc hiện tại không? | Batch bị lỗi hoặc âm thầm sửa sai dữ liệu |

**Cùng một annotation trên DTO có thể được nhìn thấy ở mọi nơi nhưng chỉ có tác dụng ở những nơi được cấu hình thực thi nó.** Kết quả unit test, API test và job test có thể khác nhau nếu đường xử lý không tương đương.

## 8. Mô hình JSON và cấu hình serializer làm thay đổi hợp đồng API

Giả sử Java dùng **productCode**, nhưng API công khai dùng trường JSON **product_code**:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

record ProductResponse(
        @JsonProperty("product_code") String productCode,
        @JsonProperty("unit_price_vnd") long unitPriceVnd) {
}
~~~

Trong một Jackson ObjectMapper có bật xử lý annotation phù hợp, metadata này giúp ánh xạ tên trường theo wire format.

Nhưng một unit test chỉ gọi:

~~~java
new ProductResponse("SP-01", 120000L);
~~~

không chứng minh JSON thực tế sẽ là:

~~~json
{
  "product_code": "SP-01",
  "unit_price_vnd": 120000
}
~~~

Muốn bảo vệ hợp đồng JSON, cần **serialization test** dùng cấu hình ObjectMapper tương ứng với ứng dụng, hoặc **API integration/contract test** ở ranh giới HTTP.

### Những thay đổi cấu hình có thể ảnh hưởng

- **Naming strategy:** snake_case hay camelCase.
- **Null inclusion:** trường null được bỏ qua hay xuất hiện.
- **Unknown properties:** payload có trường lạ bị từ chối hay bỏ qua.
- **Number coercion:** chuỗi số hoặc số thập phân được chấp nhận/ép kiểu như thế nào.
- **Date/time:** định dạng, múi giờ và cách diễn giải thời điểm.
- **Polymorphic typing:** cơ chế đọc/ghi subtype và phạm vi các kiểu được phép.
- **Module/configuration:** hỗ trợ record, Java time, custom serializer/deserializer.

Không nên dựa vào cấu hình mặc định mà không kiểm chứng, nhất là với API công khai hoặc kết quả được hệ thống khác tiêu thụ.

### Test cần xem cả trường hợp ngược

Một serializer test chỉ kiểm tra xuất JSON chưa chắc chứng minh **đọc JSON vào Java** đúng, nhất là khi có constructor ràng buộc, trường null hoặc chính sách từ chối dữ liệu. Với API nhận dữ liệu, cần test cả **deserialize → validate → map vào miền** và phản hồi lỗi theo hợp đồng.

Khi đổi tên trường công khai, code Java có thể vẫn biên dịch và unit test vẫn xanh nhưng client cũ bị phá. Đó là một lỗi **tương thích API**, không phải lỗi cú pháp Java.

## 9. Annotation mô tả khác annotation bảo đảm

### 9.1. OpenAPI và tài liệu API

Những annotation dùng để tạo tài liệu API có thể mô tả trường bắt buộc, ví dụ và mô hình response. Nhưng **tài liệu được sinh ra không mặc nhiên khiến server từ chối request sai**. Muốn thực thi cần validator, logic ứng dụng hoặc cơ chế kiểm tra runtime tương ứng.

Nếu tài liệu ghi **quantity ≥ 1**, trong khi code chỉ kiểm tra **quantity != null**, hệ thống có hai mô hình không thống nhất. Cần test/đối chiếu tài liệu và hành vi thực.

### 9.2. JPA mapping và ràng buộc database

Ví dụ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
class CustomerEntity {
    @Id
    private Long id;

    @Column(nullable = false, length = 100)
    private String displayName;

    // Constructor/getter/setter lược bỏ.
}
~~~

**@Column(nullable = false, length = 100)** khai báo metadata ánh xạ. Nó có thể ảnh hưởng schema được tạo tùy cấu hình và provider, nhưng **không chứng minh** database production đã có ràng buộc tương ứng, nhất là khi schema được quản lý bởi migration riêng.

Nếu database thật không có **NOT NULL** hoặc đã chứa dữ liệu cũ không hợp lệ, kết quả của một kiểm tra chỉ đọc entity có thể khác so với kiểm tra trực tiếp trên database. Ngược lại, database có thể có ràng buộc mạnh hơn annotation và từ chối dữ liệu mà unit test với fake repository đã chấp nhận.

**Cần tách ba câu hỏi:** Entity khai báo gì? Schema thực tế có gì? Hành vi khi ghi/đọc thực sự như thế nào?

### 9.3. Nullness annotations

Một số thư viện cung cấp **@Nullable**, **@NonNull**, **@NullMarked** hoặc các annotation gần nghĩa. Chúng có thể được IDE, static analyzer hoặc framework hiểu theo những mô hình khác nhau.

Không nên khẳng định mọi Java compiler đều từ chối lời gọi vi phạm annotation nullness. Java 17 kiểm tra hệ kiểu chuẩn nhưng **không có một cơ chế kiểm tra nullness phổ quát cho mọi bộ annotation bên ngoài**. Khi chọn công cụ nullness, phải xem:
- Bộ annotation và phiên bản nào được hỗ trợ.
- Phạm vi mặc định: package, class, method hay type use.
- Cách suy luận giá trị trả về của API thư viện.
- Cảnh báo nào được bật và có chặn build không.
- Có test runtime hoặc bất biến constructor bổ sung không.

Đôi khi static analyzer thấy một annotation nhưng không suy luận được hành vi của thư viện hoặc đường reflection. Đây là giới hạn của mô hình, không thể được giải quyết chỉ bằng cách thêm nhiều annotation.

## 10. @Transactional và ngữ cảnh gọi phương thức

Một ví dụ điển hình về **annotation có hiệu lực phụ thuộc đường gọi** là **@Transactional** trong Spring.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class PaymentWorkflow {
    @Transactional
    public void recordPayment() {
        // Ghi trạng thái giao dịch.
    }

    public void process() {
        recordPayment(); // Lời gọi nội bộ (self-invocation).
    }
}
~~~

Trong **Spring transaction management dùng proxy** thông thường, một lời gọi bên ngoài đi qua proxy có thể được advice giao dịch bao quanh. Nhưng lời gọi **this.recordPayment()** hoặc gọi trực tiếp **recordPayment()** từ một method khác trong cùng đối tượng thường **không đi qua proxy**, nên không thể mặc nhiên coi annotation trên recordPayment được áp dụng cho riêng lời gọi nội bộ đó.

Không được suy ra rằng ví dụ luôn chạy ngoài mọi transaction: nếu **process()** đã được gọi bên trong một transaction hiện hữu thì recordPayment có thể tham gia transaction đó. Cần xác định chính xác **transaction bắt đầu tại đâu và có bao quanh đường thực thi nào**.

Đây là ví dụ cho thấy:
- Static inspection thấy **@Transactional** chưa đủ để kết luận transaction được mở ở mọi trường hợp.
- Unit test gọi trực tiếp phương thức thường không kiểm tra cơ chế proxy.
- Integration test với Spring context và transaction manager thích hợp có thể kiểm chứng ranh giới thực tế.

Có thể thay đổi cấu trúc để gọi qua một service được Spring quản lý ở ranh giới phù hợp, hoặc chọn cơ chế transaction rõ ràng. Không nên sửa bằng cách thêm annotation tràn lan mà chưa hiểu đường gọi.

**Lưu ý:** Các framework hoặc chế độ weaving khác có thể có cơ chế xử lý khác. Hãy kiểm tra cấu hình đang sử dụng thay vì suy từ một quy tắc chung ngoài ngữ cảnh.

## 11. Annotation processor, code generation và mô hình phân tích

Không phải annotation nào cũng được đọc khi ứng dụng chạy. Một số được xử lý **trong build** để sinh thêm Java source hoặc hỗ trợ biên dịch.

Ví dụ phổ biến:
- Processor tạo class triển khai mapper.
- Công cụ sinh builder hoặc metadata.
- Annotation phục vụ dependency injection có processor tạo mã.
- Framework hoặc plugin có khả năng thay đổi mô hình AST/bytecode trong quá trình build.

Điều này tạo thêm các câu hỏi:

1. **Processor đã được cấu hình và thực thi chưa?**
2. **Mã sinh ra có cùng hợp đồng API như mã nguồn mong đợi không?**
3. **Static analyzer đọc source ban đầu, source đã sinh hay bytecode?**
4. **IDE và CI có dùng cùng phiên bản processor/plugin không?**
5. **Build incremental hoặc cache có làm kết quả khác với build sạch không?**

Nếu một công cụ không hiểu cách mã được sinh hoặc biến đổi, nó có thể báo **false positive** (“không tìm thấy phương thức”, “field chưa khởi tạo”), hoặc **false negative** vì không nhìn thấy logic thực thi được thêm về sau.

Không nên sửa tay các file sinh tự động để làm cảnh báo biến mất: thay đổi có thể bị ghi đè khi tái tạo. Hãy kiểm tra cấu hình processor và đặt quy tắc kiểm tra ở **nguồn sinh hoặc artifact phù hợp**.

## 12. False positive và false negative: kết quả phải được diễn giải

Một cảnh báo kiểm tra tự động không phải phán quyết tuyệt đối; một lượt kiểm tra “PASS” cũng không có nghĩa hệ thống không còn lỗi.

### False positive (dương tính giả)

Công cụ báo có vấn đề nhưng theo **hợp đồng và đường thực thi thực**, vấn đề không tồn tại.

Ví dụ:
- Analyzer không biết một factory luôn trả đối tượng không null nên cảnh báo dereference.
- Analyzer không hiểu một thư viện đảm bảo đầu vào đã được kiểm tra.
- Cấu hình sai phiên bản Java/framework khiến công cụ mô hình hóa không đúng.

Cách xử lý không nên là tắt toàn bộ quy tắc ngay lập tức. Hãy:
1. Xác minh cảnh báo trong ngữ cảnh thật.
2. Tìm cách viết rõ hợp đồng để công cụ hiểu hơn.
3. Cấu hình model/library annotations đúng nếu công cụ hỗ trợ.
4. Chỉ suppress **phạm vi nhỏ nhất** khi có giải thích và bằng chứng.

### False negative (âm tính giả)

Công cụ không báo lỗi nhưng hệ thống có rủi ro thật.

Ví dụ:
- DTO có **@NotNull**, nhưng một đường xử lý message không kích hoạt validator.
- Static analyzer thấy **@Transactional** nhưng không xét self-invocation qua proxy.
- Unit test chỉ khởi tạo DTO trực tiếp, không thử JSON mapping thật.
- Repository fake chấp nhận dữ liệu mà database thật từ chối.
- Analyzer không mô hình được reflection hoặc một plugin thay đổi bytecode.

Để giảm âm tính giả, cần **test đúng ranh giới** và bổ sung các kỹ thuật kiểm tra ở tầng khác.

### Bảng phân biệt

| Triệu chứng | Giả thuyết có thể có | Cần kiểm chứng |
| --- | --- | --- |
| Compiler PASS nhưng request lỗi | Sai ràng buộc runtime hoặc API contract | Test HTTP mapping, validation, nghiệp vụ |
| Unit test PASS nhưng integration test FAIL | Fake/mock khác phụ thuộc thật | Adapter, schema, cấu hình, transaction |
| Static analyzer báo null dù code chạy ổn | Thiếu nullness model hoặc đường đảm bảo | Contract, phạm vi annotation, cấu hình tool |
| API test PASS với JSON mẫu nhưng client lỗi | Thay đổi field, version hoặc coercion | Consumer contract và payload thật |
| Annotation hiện diện nhưng không có hiệu lực | Thiếu provider/hook/proxy hoặc đường gọi không qua framework | Kiểm tra wiring và test runtime |
| CI FAIL nhưng IDE không báo | Khác version, ruleset, build profile hoặc classpath | Đồng bộ môi trường và cấu hình |
| CI PASS nhưng job nền sai dữ liệu | Job đi đường không được test | Kiểm tra message/batch boundary và invariants |

## 13. Khi nào dùng @SuppressWarnings?

Java cung cấp **@SuppressWarnings** để yêu cầu công cụ được hỗ trợ bỏ qua một số loại cảnh báo. Tuy nhiên, **nó không làm cho mã nguy hiểm trở nên an toàn**. Một số analyzer riêng có cơ chế suppression độc lập với javac.

Ví dụ, khi buộc dùng API đã deprecated để giữ tương thích tạm thời:

~~~java
final class LegacyAdapter {

    @SuppressWarnings("deprecation")
    String readLegacyValue(LegacyClient client) {
        // Cầu nối tương thích trong thời gian chuyển đổi API.
        return client.oldRead();
    }
}
~~~

**LegacyClient** là kiểu giả định, được dùng để minh họa ý nghĩa suppression. Khi triển khai thật, cần:
- Ghi lý do vì sao chưa thể thay API cũ.
- Xác định phạm vi suppression nhỏ, tránh áp cho cả package nếu không cần.
- Có test bảo vệ hành vi tương thích.
- Theo dõi điều kiện gỡ suppression khi chuyển đổi xong.

Không nên suppress các cảnh báo về **lộ dữ liệu, truy cập quyền, truy vấn không tham số hoặc null nguy hiểm** chỉ để CI xanh khi chưa xác định được rủi ro và cách bảo vệ.

Nếu một rule tạo nhiều cảnh báo không có giá trị, nên xem lại **mô hình và cấu hình rule** thay vì bỏ mọi cảnh báo ở từng chỗ.

## 14. Thiết kế kiểm tra tự động theo tầng

Một cách hữu ích là ghép nhiều kiểm tra nhưng để mỗi kiểm tra trả lời **một câu hỏi cụ thể**.

~~~mermaid
flowchart TB
    A[Java source + API contracts] --> B[Compile / annotation processing]
    B --> C[Static analysis / lint]
    C --> D[Unit test / validator test]
    D --> E[API contract / serialization test]
    E --> F[Integration test với framework và DB]
    F --> G[CI báo kết quả và bằng chứng]
~~~

Đây là sơ đồ minh họa các lớp kiểm chứng, không bắt buộc pipeline phải luôn chạy tuần tự như vậy. Nhiều bước có thể chạy song song; điều quan trọng là **biết mỗi bước bao phủ rủi ro gì**.

| Lớp kiểm tra | Nên kiểm tra | Không đủ để chứng minh |
| --- | --- | --- |
| **javac** | Kiểu dữ liệu, cú pháp, override, một số annotation chuẩn | Giá trị từ HTTP hợp lệ hoặc transaction đúng |
| **Static analysis** | Luồng dữ liệu, pattern nguy hiểm, nullness khi được cấu hình | Toàn bộ hành vi khi dùng reflection/network |
| **Annotation processor** | Mã sinh hoặc metadata tại build | Hợp đồng nghiệp vụ của dữ liệu thực |
| **Bean Validation test** | Constraint hoạt động khi validator được gọi | Controller thực có kích hoạt validation hay không |
| **Domain unit test** | Bất biến và phép tính thuần | JSON wire format, DB transaction |
| **Serialization/API test** | Mapping request/response và mã lỗi ở ranh giới | Quyền/transaction trên dữ liệu thật nếu bị mock |
| **Integration test** | Wiring framework, transaction, ORM, DB, client | Mọi tải và điều kiện hiếm trên production |
| **Contract test với bên sử dụng/cung cấp** | Các bên thống nhất schema và một số ngữ nghĩa công bố | Không thay thế kiểm thử end-to-end và vận hành |
| **Security/resilience test** | Một số lỗi ngữ cảnh, quyền, timeout, retry | Không bảo đảm không tồn tại lỗ hổng khác |

### Cấu hình là một phần của kết quả

Để hiểu kết quả một check, cần biết:
- Java/JDK phiên bản nào.
- Compiler options, build profile và dependency version.
- Annotation processor nào chạy và có thành công không.
- Ruleset/static analyzer version, severity và suppression.
- Test engine và bộ lọc test, test nào thực sự được phát hiện.
- Bean Validation provider nào hiện diện.
- Spring/application context và cấu hình transaction, serialization.
- Database schema, migration và môi trường integration test.

Một lần “PASS” mà không biết **đã chạy những kiểm tra nào** ít có giá trị hơn báo cáo nêu rõ công cụ, cấu hình, số test được thực thi và phạm vi kiểm chứng.

## 15. Tình huống tổng hợp: API tạo đơn có annotation nhưng vẫn nhận sai dữ liệu

Một nhóm phát triển có API tạo đơn:

~~~java
record CreateOrderRequest(
        @NotNull String sku,
        @Min(1) Integer quantity) {
}
~~~

Controller gọi service tạo đơn; job nền cũng có thể gọi service đó trực tiếp. Sau một đợt triển khai, hệ thống xuất hiện các đơn thiếu SKU hoặc quantity không hợp lệ.

Nhóm xác nhận:
- Code đã biên dịch.
- Controller có annotation mapping HTTP.
- Unit test sử dụng DTO hợp lệ đều xanh.
- Một phần request có thể không qua đường MVC.
- Không có test cho DTO với chuỗi chỉ gồm khoảng trắng hoặc quantity null.
- Một số bản ghi được tạo từ job nền.

### Phân tích nguyên nhân khả dĩ

**Vấn đề 1 — @NotNull chưa phải @NotBlank.** Chuỗi **" "** không null, nên nếu nghiệp vụ cấm SKU rỗng/trắng thì **@NotNull** chưa diễn đạt đúng hợp đồng.

**Vấn đề 2 — @Min(1) cho phép null.** Nếu **quantity** là Integer, cần **@NotNull** nếu bắt buộc. Khi mapper/unboxing xử lý null ở bước khác, có thể xuất hiện lỗi hoặc hành vi không rõ.

**Vấn đề 3 — Không chắc validation đã chạy.** DTO có annotation nhưng nếu đường job nền gọi service trực tiếp mà không validate, ràng buộc ở controller không bảo vệ đường đó.

**Vấn đề 4 — Thiếu bất biến miền.** Nếu service có thể tạo đơn mà không kiểm tra SKU, quantity hoặc trạng thái sản phẩm, dữ liệu sai có thể vượt qua ranh giới nghiệp vụ.

**Vấn đề 5 — Test chỉ bao phủ dữ liệu hợp lệ.** Unit test xanh cho đường thành công chưa chứng minh đường lỗi, pipeline validation hay database constraints.

### Hướng xử lý có căn cứ

1. Viết rõ hợp đồng: SKU bắt buộc, không blank; quantity 1–100 hoặc theo giới hạn nghiệp vụ đã xác nhận.
2. Dùng constraint thích hợp ở DTO, nhưng **đảm bảo validator được kích hoạt** tại mọi đường tiếp nhận cần thiết.
3. Dùng domain constructor/factory bảo vệ bất biến cốt lõi, không phụ thuộc duy nhất vào Spring MVC.
4. Bổ sung unit test cho null, blank, zero, âm, vượt giới hạn.
5. Bổ sung API test qua HTTP để kiểm tra mapping, validation và response lỗi.
6. Bổ sung test cho job/consumer trực tiếp để bảo đảm chúng không đi vòng qua ranh giới hợp đồng.
7. Kiểm tra ràng buộc database nếu dữ liệu phải luôn đáp ứng invariant ở tầng lưu trữ.
8. Quan sát dữ liệu cũ và lập kế hoạch làm sạch nếu schema/logic trước đó từng nhận dữ liệu sai.

Một giải pháp chỉ là **thêm annotation rồi chạy lại một test hợp lệ** có thể khiến lỗi lặp lại. Chất lượng ở đây nằm ở chỗ các **đường thực thi khác nhau cùng được bảo vệ bởi hợp đồng rõ ràng**.

## 16. Case study ngắn: annotation transaction gây cảm giác an toàn giả

Một người viết:

~~~java
@Service
class InventoryService {
    public void confirm() {
        saveReservation();
        publishEvent();
    }

    @Transactional
    public void saveReservation() {
        // Ghi DB.
    }

    private void publishEvent() {
        // Gửi sự kiện ngoài DB.
    }
}
~~~

Người review thấy **@Transactional** và kết luận hai bước **saveReservation** và **publishEvent** sẽ hoặc cùng thành công hoặc cùng rollback. Kết luận này chưa được chứng minh, bởi:

- **confirm()** gọi **saveReservation()** từ bên trong cùng đối tượng; với proxy mode thông thường, lời gọi này không kích hoạt advice transaction riêng cho saveReservation.
- Một sự kiện được gửi tới broker hoặc HTTP API bên ngoài thường **không tự tham gia transaction database**, ngay cả khi code nằm trong phương thức đang có transaction.
- Nếu phát sự kiện thất bại sau khi DB đã ghi, có thể tồn tại trạng thái không nhất quán giữa DB và bên nhận.
- Unit test mock repository/publisher có thể không biểu diễn những lỗi ở ranh giới đó.

Giải pháp cần xuất phát từ **hợp đồng đảm bảo phát sự kiện** và ranh giới thực tế: kiểm tra transaction có hiệu lực ở đâu, dùng integration test và cân nhắc **transactional outbox** hoặc cơ chế phù hợp khi cần đảm bảo phát hành. Thêm annotation mà không hiểu đường gọi không tự giải quyết bài toán nhất quán.

## 17. Quy trình điều tra một kết quả kiểm tra tự động bất ngờ

Khi công cụ báo lỗi sai hoặc bỏ sót lỗi, thay vì sửa vội, hãy làm theo trình tự:

### Bước 1 — Xác định tuyên bố của kiểm tra

Công cụ đang khẳng định điều gì? “Có thể null”, “sai tên property”, “constraint không được thỏa”, “transaction không kích hoạt” hay “test thất bại”?

Đừng gộp mọi loại cảnh báo thành “mã không tốt”.

### Bước 2 — Đọc hợp đồng gốc

Kiểu Java là gì? Annotation thuộc package nào? Giá trị hợp lệ theo miền nghiệp vụ là gì? API có ràng buộc null, lỗi và tác dụng phụ ra sao?

### Bước 3 — Tìm bên thực thi

Đó là javac, static analyzer, annotation processor, Bean Validation provider, Spring proxy, Jackson ObjectMapper hay JUnit engine? Bên này chạy ở **compile time**, **test time** hay **runtime**?

### Bước 4 — Truy lại đường gọi

Dữ liệu đến từ HTTP, message hay job? Phương thức được gọi qua proxy hay gọi trực tiếp? Mapping/validation có được kích hoạt trong đường đi thực không?

### Bước 5 — Kiểm tra môi trường và cấu hình

Phiên bản dependency, Java, build options, provider, feature flag và schema DB có giống môi trường nơi lỗi xuất hiện không?

### Bước 6 — Tái hiện bằng test ở đúng tầng

Nếu lỗi thuộc JSON mapping, test serializer/controller. Nếu liên quan transaction, test với context và DB thích hợp. Nếu là bất biến thuần, test constructor và domain method. Nếu là API tích hợp, dùng contract test phù hợp.

### Bước 7 — Sửa nguyên nhân, rồi đánh giá hiệu lực

Cần thêm validation ở ranh giới, sửa mô hình nullness, làm rõ contract, thay cấu trúc gọi proxy, cập nhật schema hay chỉ chỉnh một suppression quá rộng? Sau khi sửa, xác minh cả đường thành công và đường lỗi.

## 18. Bảng kiểm dành cho code review và CI

Khi thấy một PR thêm/sửa API hoặc annotation, hãy hỏi:

1. **Annotation nào được thêm, thuộc thư viện và phiên bản nào?**
2. **Ai là bên xử lý**, ở compile, test hay runtime? Có cấu hình bắt buộc nào không?
3. **Nó thực sự kiểm tra điều gì**, và điều gì không kiểm tra? Ví dụ null khác blank, định dạng khác tồn tại.
4. **Mọi đường vào** (REST, message, batch, nội bộ) có cùng yêu cầu bất biến không?
5. **DTO và domain** phân vai ra sao; có lỗ hổng khi code tạo domain object trực tiếp không?
6. **Tên trường JSON, kiểu số, ngày giờ và null** có tương thích với client hiện có không?
7. **Đường gọi framework** có đúng ranh giới proxy, transaction và serialization không?
8. **Có test âm tính** cho dữ liệu lỗi và đường không qua framework không?
9. **Có test tích hợp** cho những bảo đảm mà mock/fake không thể đại diện không?
10. **Cảnh báo bị suppress** có lý do và phạm vi nhỏ không?
11. **CI có chạy cùng ruleset, processor, provider** như môi trường được dùng để đánh giá không?
12. **Báo cáo PASS có bằng chứng** cho số kiểm tra đã thực thi và phạm vi bao phủ hay không?

Nếu quá nhiều câu trả lời phụ thuộc vào “framework thường tự làm”, đó là dấu hiệu cần kiểm thử ranh giới thực tế, không chỉ bổ sung annotation trong mã nguồn.

## 19. Bài tập tự luyện

### Bài tập 1 — Phân biệt annotation và hiệu lực

Một record nhận:

~~~java
record AccountInput(
        @NotNull String ownerName,
        @Min(0) Integer balance) {
}
~~~

Hãy trả lời:
1. Chuỗi rỗng có bị **@NotNull** cấm không?
2. **balance = null** có bị **@Min(0)** cấm không?
3. Tạo record bằng **new AccountInput(...)** có tự kích hoạt Bean Validation không?
4. Nếu nghiệp vụ yêu cầu tên không blank và số dư bắt buộc, bạn sẽ sửa annotation thế nào?
5. Nếu số dư phải lấy từ database chứ không phải từ client, validation có đủ để bảo vệ tính đúng đắn không?

**Gợi ý:** Xem sự khác nhau giữa không-null, không-blank và giới hạn số. Chữ ký DTO và annotation chưa giải quyết quyền quyết định số dư.

### Bài tập 2 — API contract và serializer

Java có field **createdAt** kiểu **Instant**; API đối tác yêu cầu trường **created_at** ở định dạng thời điểm ISO 8601 với offset rõ ràng.

Hãy xác định:
- Kiểm tra nào bảo vệ tên trường JSON?
- Kiểm tra nào bảo vệ định dạng giá trị thời gian?
- Có thể suy từ việc unit test tạo record thành công rằng đối tác nhận đúng dữ liệu không?
- Khi đổi ObjectMapper configuration, những test nào phải chạy lại?

**Gợi ý:** Serializer/API integration test có cấu hình thật quan trọng; đừng chỉ kiểm tra getter hoặc constructor.

### Bài tập 3 — Self-invocation và transaction

Một service có **@Transactional** trên phương thức **save()**, trong khi **execute()** cùng lớp gọi trực tiếp save(). Hãy mô tả vì sao không thể kết luận save được mở transaction trong proxy mode và cần test/cấu trúc nào để bảo vệ hợp đồng.

**Gợi ý:** Xác định đường đi qua proxy và khả năng tồn tại transaction bên ngoài, không chỉ đọc annotation.

### Bài tập 4 — Đọc cảnh báo nullness

Static analyzer báo “possibly null” ở đoạn:

~~~java
Product product = catalog.findBySku(sku).orElse(null);
return product.price();
~~~

Hãy cho biết:
- Vì sao cảnh báo có căn cứ?
- Tại sao thêm **@NotNull** vào tham số **sku** chưa giải quyết được?
- Có thể viết lại dùng **orElseThrow(...)** hoặc xử lý Optional ra sao?
- Những trường hợp nào cần test?

**Gợi ý:** Null có thể đến từ **kết quả tìm kiếm**, không chỉ từ tham số đầu vào.

### Bài tập 5 — Không có lỗi compile nhưng có lỗi hợp đồng

Một API đổi tên trường response **customerId** thành **customerCode**. Java vẫn biên dịch, unit test controller mock service đều xanh. Nhưng ứng dụng di động cũ không đọc được phản hồi.

Hãy đề xuất **consumer contract test**, kế hoạch tương thích và cách versioning/alias nếu cần. Giải thích vì sao đây không phải vấn đề có thể giải quyết chỉ bằng formatter hay static lint.

### Bài tập 6 — Chọn nơi kiểm tra

Một message consumer nhận đơn hàng với SKU không rỗng, số lượng dương và ID tài khoản. API HTTP đã dùng **@Valid** cho DTO, nhưng consumer gọi application service trực tiếp.

Hãy thiết kế ranh giới kiểm tra:
- Schema và validation ở consumer.
- Bất biến miền ở constructor/factory.
- Kiểm tra account/authorization/trạng thái ở application service.
- Ràng buộc lưu trữ và test tích hợp.

**Gợi ý:** Đừng dựa hoàn toàn vào annotation chỉ được kích hoạt tại REST controller.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Một annotation có **RetentionPolicy.RUNTIME** thì nó tự thực hiện kiểm tra lúc chạy?

*Trả lời:* Không. Nó chỉ có thể được nhìn thấy bởi cơ chế runtime thích hợp. Cần code/framework thực sự đọc và thực thi ngữ nghĩa mong muốn.

**Câu 2.** **@Min(1)** trên **Integer quantity** có thay được **@NotNull**?

*Trả lời:* Không. Theo Jakarta Bean Validation, **@Min** chấp nhận null; nếu quantity bắt buộc, cần một ràng buộc không-null cùng các ràng buộc khác.

**Câu 3.** Unit test gọi trực tiếp constructor của DTO có chứng minh validation trong Spring MVC hoạt động?

*Trả lời:* Không. Cần validator test hoặc test đi qua Spring MVC với cấu hình provider, mapping và xử lý lỗi tương ứng.

**Câu 4.** Static analysis không báo lỗi thì có thể coi annotation giao dịch được áp dụng ở mọi đường gọi?

*Trả lời:* Không. Ranh giới proxy, transaction context và cơ chế runtime có thể không được công cụ mô hình hóa đầy đủ.

**Câu 5.** Vì sao cùng một bộ annotation có thể cho kết quả khác giữa IDE và CI?

*Trả lời:* Vì khác JDK, plugin, processor, analyzer version, ruleset, dependency, cấu hình classpath hoặc test runner.

**Câu 6.** **@JsonProperty** có làm database tự tạo một cột cùng tên?

*Trả lời:* Không. Nó thuộc cơ chế mapping JSON của thư viện tương ứng, không phải định nghĩa schema database.

**Câu 7.** Nếu JPA entity có **@Column(nullable = false)**, đã chắc database production từ chối null?

*Trả lời:* Chưa. Cần kiểm tra schema/migration và ràng buộc thực tế của database, cũng như đường ghi dữ liệu.

**Câu 8.** Một unit test với mock repository xanh có thay integration test về transaction không?

*Trả lời:* Không. Mock không thực thi transaction, lock, constraint hoặc SQL mapping thật.

**Câu 9.** Nên làm gì trước khi suppress một cảnh báo static analyzer?

*Trả lời:* Hiểu cảnh báo, xác minh hợp đồng và ngữ cảnh, xem có thể làm rõ code/cấu hình hay không, rồi chỉ suppress phạm vi nhỏ với lý do nếu thật sự cần.

**Câu 10.** Điều gì khiến kết quả kiểm tra tự động có ý nghĩa với chất lượng mã?

*Trả lời:* Kết quả phải gắn với **một hợp đồng cụ thể**, một **công cụ/cơ chế thực thi xác định**, **ngữ cảnh đủ đại diện** và kiểm chứng rằng các rủi ro ngoài phạm vi đã được bao phủ ở tầng thích hợp.

## Ghi nhớ

**Mô hình API, annotation và ngữ cảnh cùng quyết định kết quả kiểm tra tự động.** Kiểu Java giúp compiler kiểm tra cú pháp và tương thích kiểu; annotation có thể là metadata, chỉ dẫn cho analyzer, đầu vào của processor hoặc ràng buộc được framework thực thi; cấu hình serializer, validator, proxy và database quyết định điều gì thực sự xảy ra trên đường chạy. Để mã đáng tin cậy, dễ hiểu và dễ thay đổi, hãy **mô tả hợp đồng rõ ràng, bảo vệ bất biến ở đúng ranh giới, kiểm tra cả đường vào và đường lỗi, đồng thời kết hợp static analysis với unit, contract và integration test**. Một lần kiểm tra **PASS** chỉ có giá trị khi ta biết rõ **nó đã kiểm tra điều gì và chưa kiểm tra điều gì**.
