# Validation tại ranh giới nhận thông điệp trong Spring RSocket

## Mục tiêu

Khi một peer gửi request qua RSocket, ứng dụng nhận được dữ liệu từ một ranh giới tin cậy khác. Payload có thể giải mã thành đúng kiểu Java nhưng vẫn chứa dữ liệu không hợp lệ: chuỗi rỗng, số âm, danh sách thiếu phần tử hoặc trường lồng nhau sai quy tắc. Validation tại ranh giới nhận thông điệp giúp từ chối dữ liệu đó trước khi gọi logic nghiệp vụ.

Trong Spring Framework, luồng này được triển khai qua `RSocketMessageHandler`, các phương thức `@MessageMapping`, bộ giải mã payload và `PayloadMethodArgumentResolver`. Có thể dùng Jakarta Bean Validation với `@Valid` hoặc Spring `@Validated`, miễn là handler được cấu hình một `Validator` thực sự.

## 1. Validation nằm ở đâu trong luồng RSocket?

Một request đi qua các bước khái quát sau:

1. RSocket nhận frame và tách data cùng metadata.
2. Spring xác định route và phương thức `@MessageMapping` phù hợp.
3. Decoder trong `RSocketStrategies` chuyển bytes của phần data thành kiểu Java được khai báo.
4. `PayloadMethodArgumentResolver` tạo đối số `@Payload` và chạy validation nếu tham số được đánh dấu `@Valid` hoặc `@Validated`.
5. Nếu payload hợp lệ, Spring mới gọi phương thức handler.
6. Handler chạy nghiệp vụ và tạo kết quả hoặc lỗi theo hợp đồng tương tác RSocket.

Điểm quan trọng là validation diễn ra sau khi payload được giải mã thành object và trước khi logic trong phương thức handler chạy. Vì vậy có hai nhóm lỗi khác nhau:

- **Lỗi giao thức hoặc giải mã:** frame sai cấu trúc, metadata không đọc được, JSON sai cú pháp hoặc không thể chuyển thành kiểu Java. Decoder có thể phát sinh lỗi trước khi Bean Validation chạy.
- **Lỗi ràng buộc dữ liệu:** payload đã giải mã thành object nhưng vi phạm các constraint như `@NotBlank`, `@Positive` hoặc `@Size`. Spring Messaging báo lỗi validation bằng `MethodArgumentNotValidException`.

RSocket protocol validation và Bean Validation cũng có mục đích khác nhau. Protocol validation bảo vệ tính hợp lệ của frame; Bean Validation kiểm tra ý nghĩa và cấu trúc dữ liệu ở cấp ứng dụng. Một payload hợp lệ về mặt frame vẫn có thể không hợp lệ về mặt nghiệp vụ.

## 2. `@Valid`, `@Validated` và constraint

Đặt annotation validation trên tham số payload của handler:

~~~java
@MessageMapping("orders.create")
public Mono<OrderAccepted> create(
        @Payload @Valid CreateOrder command) {
    // ...
}
~~~

- `@Valid` là annotation Jakarta (`jakarta.validation.Valid`). Nó yêu cầu validation theo nhóm mặc định và cho phép cascade validation vào object hoặc phần tử lồng nhau đã đánh dấu `@Valid`.
- `@Validated` thuộc Spring (`org.springframework.validation.annotation.Validated`). Ngoài việc kích hoạt validation, nó cho phép chỉ định validation group, ví dụ `@Validated(OnCreate.class)`.
- `@Payload` làm rõ tham số lấy dữ liệu từ phần data của message. Với `@MessageMapping`, annotation này có thể được lược bỏ nếu kiểu tham số không khớp với một loại đối số được Spring hỗ trợ khác; ghi tường minh thường dễ đọc và bảo trì hơn.

Một DTO có thể dùng các constraint phổ biến:

| Constraint | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi phải khác null và có ít nhất một ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi, collection, map hoặc mảng không được rỗng |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Positive`, `@PositiveOrZero` | Số phải dương hoặc không âm |
| `@Min`, `@Max` | Giới hạn giá trị số nguyên |
| `@Email` | Kiểm tra định dạng email ở mức cơ bản |
| `@Pattern` | Kiểm tra chuỗi theo regular expression |

Ví dụ DTO có validation lồng nhau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import java.util.List;

public class CreateOrder {

    @NotBlank
    private String customerId;

    @NotEmpty
    @Valid
    private List<OrderLine> items;

    // getters and setters
}

public class OrderLine {

    @NotBlank
    private String sku;

    @Positive
    private int quantity;

    // getters and setters
}
~~~

`@NotEmpty` yêu cầu danh sách `items` có phần tử. `@Valid` yêu cầu validator đi tiếp vào từng `OrderLine`, nhờ đó `sku` và `quantity` cũng được kiểm tra. Nếu chỉ có `@NotEmpty`, các constraint bên trong từng dòng hàng sẽ không tự động được cascade.

Có thể tạo constraint riêng bằng annotation `@Constraint` và một lớp triển khai `ConstraintValidator`. Dùng constraint cấp lớp khi quy tắc phụ thuộc nhiều trường, chẳng hạn ngày kết thúc phải sau ngày bắt đầu. Các quy tắc phụ thuộc dữ liệu đang lưu, quyền truy cập, tồn kho hoặc trạng thái hiện tại nên được kiểm tra trong service/domain layer; chúng không chỉ là validation hình thức của DTO.

## 3. Cấu hình Validator cho RSocketMessageHandler

Có annotation trên DTO là chưa đủ. Ứng dụng phải có Bean Validation provider trên classpath và phải cung cấp Spring `Validator` cho message handler.

Spring có `LocalValidatorFactoryBean`, một adapter triển khai cả `jakarta.validation.Validator` lẫn `org.springframework.validation.Validator`. Nó khởi tạo provider tìm thấy trên classpath, ví dụ Hibernate Validator.

Ví dụ cấu hình cho Spring Framework 6.x với Jackson 2:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RSocketConfiguration {

    @Bean
    LocalValidatorFactoryBean rSocketPayloadValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies,
            @Qualifier("rSocketPayloadValidator")
            org.springframework.validation.Validator validator) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setValidator(validator);
        return handler;
    }
}
~~~

Ở đây có hai cấu hình độc lập:

- `RSocketStrategies` cung cấp encoder/decoder để chuyển đổi giữa bytes và object. Hãy cấu hình codec phù hợp với MIME type và định dạng thực tế của peer.
- `RSocketMessageHandler.setValidator(...)` cung cấp validator dùng để kiểm tra các tham số `@Payload`.

Nếu dùng Spring Boot, có thể thêm `spring-boot-starter-validation` để đưa Bean Validation provider vào ứng dụng. Với ứng dụng Spring Framework thuần, cần có Jakarta Bean Validation API cùng một provider tương thích, chẳng hạn Hibernate Validator. `LocalValidatorFactoryBean` không tự cung cấp implementation nếu provider không có trên classpath.

**Lưu ý namespace và phiên bản:** Spring Framework 6.x trở lên dùng `jakarta.validation.*`; Spring Framework 5.3 dùng `javax.validation.*`. Không trộn annotation API với provider thuộc namespace khác. Ví dụ codec ở trên dùng Jackson 2, phù hợp với Spring Framework 6.x. Spring Framework 7.0 hỗ trợ Jackson 3 qua `JacksonJsonEncoder` và `JacksonJsonDecoder`; các lớp `Jackson2JsonEncoder` và `Jackson2JsonDecoder` đã bị deprecated để chuyển sang API mới. Hãy chọn cặp encoder/decoder theo phiên bản Spring và Jackson đang dùng. Cấu hình validator không phụ thuộc lựa chọn Jackson.

Nếu ứng dụng đã có `RSocketStrategies` hoặc `RSocketMessageHandler` do Spring Boot hay cấu hình chung tạo ra, hãy gắn validator vào đúng handler đang nhận request. Tạo một handler khác nhưng không được dùng làm responder sẽ không bảo vệ endpoint thực tế. Handler cũng phải được đăng ký làm responder, ví dụ qua `RSocketServer.create(handler.responder())` hoặc cơ chế auto-configuration đang dùng.

## 4. Handler kiểm tra payload trước nghiệp vụ

Ví dụ handler tạo đơn hàng:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderResponder {

    private final OrderService orderService;

    public OrderResponder(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(
            @Payload @Valid CreateOrder command) {

        return orderService.create(command);
    }
}
~~~

Khi peer gửi payload tương ứng:

~~~json
{
  "customerId": "customer-42",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
~~~

payload được giải mã thành `CreateOrder`, sau đó các constraint được kiểm tra. Chỉ khi validation thành công, Spring mới gọi `create` và `orderService.create`.

Nếu `customerId` là chuỗi rỗng hoặc `quantity` bằng 0, validation thất bại. Phương thức handler không được gọi, nên service không nhận lệnh sai định dạng. Đây là lợi ích chính của việc đặt validation ở ranh giới nhận message: mọi đường gọi handler đều đi qua cùng một bước kiểm tra.

Với validation group, khai báo nhóm trên constraint:

~~~java
public interface OnCreate {}

public class CreateOrder {

    @NotBlank(groups = OnCreate.class)
    private String customerId;

    // ...
}
~~~

và chọn nhóm tại tham số:

~~~java
@MessageMapping("orders.create")
public Mono<OrderAccepted> create(
        @Payload @Validated(OnCreate.class) CreateOrder command) {
    return orderService.create(command);
}
~~~

Nếu dùng `@Valid` thay cho `@Validated(OnCreate.class)`, validator chạy nhóm mặc định. Constraint chỉ khai báo cho `OnCreate` sẽ không được chạy trong lần validation đó.

## 5. Xử lý lỗi validation

Với payload không hợp lệ, Spring Messaging phát sinh:

`org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`

Đây là exception thuộc Spring Messaging. Đừng nhầm với `org.springframework.web.bind.MethodArgumentNotValidException` thường gặp trong Spring MVC; hai lớp nằm ở package khác nhau và thuộc hai luồng xử lý khác nhau.

Exception của Spring Messaging có thể chứa `BindingResult`, bao gồm lỗi cấp object và lỗi theo field. Có thể chuyển chúng thành cấu trúc lỗi ổn định cho client bằng `@MessageExceptionHandler`. Đặt phương thức xử lý sau vào cùng controller có `@MessageMapping`:

~~~java
public record FieldViolation(String field, String message) {}

public record ValidationError(
        String code,
        List<FieldViolation> violations) {}

@MessageExceptionHandler
public Mono<ValidationError> handleInvalidPayload(
        MethodArgumentNotValidException exception) {

    BindingResult result = exception.getBindingResult();

    List<FieldViolation> violations =
            result == null
                    ? List.of()
                    : result.getFieldErrors().stream()
                            .map(error -> new FieldViolation(
                                    error.getField(),
                                    error.getDefaultMessage()))
                            .toList();

    return Mono.just(
            new ValidationError("INVALID_PAYLOAD", violations));
}
~~~

Các record có thể đặt trong file riêng. Ví dụ trên lấy lỗi theo field; nếu có constraint cấp lớp, bổ sung `getGlobalErrors()` vào response. `@MessageExceptionHandler` cho phép xử lý exception trong controller và trả về kiểu kết quả theo cơ chế xử lý message.

Ví dụ trên minh họa cách biến lỗi thành payload ứng dụng. Hợp đồng phản hồi phải phù hợp với interaction type và client. Với Request-Response, client có thể nhận một đối tượng lỗi có cấu trúc. Nếu không ánh xạ exception, lỗi có thể làm interaction RSocket kết thúc bằng error. Fire-and-Forget không có response payload để trả về; khi đó cần quy định cách quan sát lỗi qua log, metric hoặc kênh báo lỗi riêng.

Khi tạo lỗi trả về client:

- Chỉ công khai mã lỗi, tên field và thông điệp đã được kiểm soát.
- Không gửi stack trace, dữ liệu nhạy cảm, giá trị payload nguyên bản hoặc chi tiết nội bộ của validator.
- Giữ cấu trúc lỗi nhất quán giữa các route để client dễ xử lý.
- Phân biệt lỗi giải mã với lỗi constraint để client biết nên sửa định dạng hay sửa giá trị.

## 6. Payload dạng stream và metadata

RSocket hỗ trợ các interaction có một payload hoặc nhiều payload. Trong annotated responder, `@MessageMapping` có thể nhận payload đồng bộ, `Mono<T>` hoặc `Flux<T>`; cardinality đầu vào và đầu ra quyết định interaction type. Resolver reactive của Spring cũng hỗ trợ validation khi tham số payload được đánh dấu `@Valid` hoặc `@Validated`.

Với channel hoặc stream, cần xác định rõ định dạng chuỗi dữ liệu mà decoder mong đợi, cách xử lý một phần tử không hợp lệ và việc dừng hay tiếp tục stream. Không nên chỉ kiểm thử một payload đơn rồi suy luận rằng luồng nhiều phần tử đã có hành vi lỗi đúng. Hãy kiểm thử cả phần tử hợp lệ, phần tử không hợp lệ ở giữa stream và hành vi kết thúc của interaction.

Payload và metadata là hai phần khác nhau của RSocket message:

- `@Payload` nhận phần data đã được decoder chuyển thành object.
- `@Header` và `@Headers` nhận các metadata đã được đăng ký và trích xuất thành header.
- `@Valid` trên DTO payload không tự động kiểm tra mọi metadata, route variable hoặc thông tin xác thực. Hãy kiểm tra chúng bằng cơ chế phù hợp, đồng thời xác thực danh tính và quyền truy cập ở lớp bảo mật.

Validation sau decode cũng không thay thế giới hạn kích thước frame, giới hạn bộ nhớ, timeout hoặc rate limit. Một payload quá lớn có thể tiêu tốn tài nguyên trước khi object được tạo để Bean Validation kiểm tra. Các giới hạn tài nguyên cần được đặt ở tầng transport, codec và vận hành.

## 7. Kiểm thử validation tại ranh giới

Nên kiểm thử ít nhất ba lớp:

1. **DTO:** gọi validator với object hợp lệ và không hợp lệ để xác nhận constraint, validation group và cascade validation hoạt động.
2. **Handler:** gửi payload không hợp lệ và xác nhận service không được gọi. Điều này chứng minh lỗi bị chặn trước logic nghiệp vụ.
3. **RSocket end-to-end:** dùng `RSocketRequester` gửi payload qua route thật, sau đó kiểm tra response lỗi hoặc error signal đúng theo hợp đồng đã thiết kế.

Một tình huống kiểm thử hữu ích:

- Payload hợp lệ: `customerId = "customer-42"`, `quantity = 2`; service được gọi.
- Payload sai: `customerId = " "`, `quantity = 0`; service không được gọi và client nhận lỗi `INVALID_PAYLOAD` hoặc error signal theo cấu hình.
- Payload sai cú pháp JSON: decoder báo lỗi; không được nhầm lỗi này với `MethodArgumentNotValidException`.
- Payload có phần tử lồng nhau sai: kiểm tra `@Valid` thực sự cascade tới từng phần tử.
- Payload stream có phần tử sai: kiểm tra chính xác hành vi của stream và interaction.

Không nên chỉ kiểm thử trực tiếp service hoặc gọi validator trong unit test rồi kết luận endpoint RSocket đã được bảo vệ. Cấu hình handler, decoder và validator phải cùng tham gia trong kiểm thử tích hợp.

## 8. Lỗi thường gặp

| Vấn đề | Nguyên nhân và cách khắc phục |
| --- | --- |
| Có `@Valid` nhưng dữ liệu sai vẫn lọt vào handler | Chưa cấu hình Bean Validation provider hoặc chưa gọi `RSocketMessageHandler.setValidator`; kiểm tra đúng handler đang được đăng ký làm responder |
| DTO ngoài được kiểm tra nhưng object lồng nhau thì không | Thiếu `@Valid` ở trường hoặc phần tử cần cascade |
| JSON sai cú pháp bị xử lý như lỗi constraint | Decoder thất bại trước Bean Validation; xử lý riêng lỗi chuyển đổi payload |
| Dùng nhầm exception của Spring MVC | Import exception trong package `org.springframework.messaging.handler.annotation.support` |
| Client đã validate nên server bỏ qua | Client không phải ranh giới tin cậy; server luôn phải kiểm tra dữ liệu nhận được |
| `@Valid` không kiểm tra route hoặc metadata | Annotation áp dụng cho object payload; kiểm tra header, route và thông tin bảo mật riêng |
| Dùng Bean Validation cho quy tắc phụ thuộc database | Kiểm tra trạng thái và quyền trong service/domain layer, có xử lý cạnh tranh và transaction phù hợp |
| Payload quá lớn vẫn làm tăng tải trước khi validation | Bean Validation chạy sau decode; cần giới hạn frame/payload và tài nguyên ở tầng thấp hơn |

## 9. Checklist triển khai

- [ ] Đã chọn DTO rõ ràng cho payload của từng route.
- [ ] Đã thêm constraint phù hợp và `@Valid` cho object lồng nhau.
- [ ] Đã có Bean Validation provider tương thích với phiên bản Spring.
- [ ] Đã cung cấp Spring `Validator` cho `RSocketMessageHandler` bằng `setValidator`.
- [ ] Decoder và MIME type khớp định dạng payload mà client gửi.
- [ ] Đã định nghĩa cách trả lỗi hoặc kết thúc interaction cho payload không hợp lệ.
- [ ] Đã kiểm thử cả lỗi constraint, lỗi decode và payload stream.
- [ ] Service không được gọi khi payload vi phạm constraint.
- [ ] Metadata, authorization và giới hạn tài nguyên được xử lý ở đúng tầng.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): annotated responders, `@MessageMapping`, payload và interaction cardinality.
- [MessageMappingMessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): `setValidator` và vai trò của reactive message handler.
- [PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/PayloadMethodArgumentResolver.html): giải mã payload và validation với `@Valid`/`@Validated`.
- [MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html): lỗi validation của Spring Messaging và `BindingResult`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): `LocalValidatorFactoryBean`, provider và constraint tùy chỉnh.

