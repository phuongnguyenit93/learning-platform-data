# Chuyển đổi payload và kiểm tra bằng @Valid hoặc @Validated

Tài liệu này tập trung vào controller STOMP dùng Spring Messaging. Khi client gửi một STOMP message tới một method có @MessageMapping, Spring lấy payload, chuyển payload sang kiểu Java của tham số, chạy Bean Validation nếu tham số được đánh dấu phù hợp, rồi mới gọi method. Hiểu đúng thứ tự này giúp phân biệt lỗi JSON/kiểu dữ liệu với lỗi dữ liệu không thỏa điều kiện nghiệp vụ.

## 1. Luồng xử lý payload trong STOMP

Một message đi vào controller theo các bước chính:

1. Client gửi STOMP SEND frame qua WebSocket. Frame có destination và thường có content-type mô tả định dạng body.
2. Spring giải mã frame thành một Spring Message, đưa message vào clientInboundChannel và định tuyến destination tới method @MessageMapping tương ứng.
3. Bộ phân giải tham số lấy payload. Với tham số được đánh dấu @Payload, Spring dùng kiểu tham số làm kiểu đích. Nếu không có annotation nào khác xử lý tham số, payload cũng được giả định theo mặc định; viết @Payload tường minh thường giúp chữ ký method dễ đọc hơn.
4. MessageConverter chuyển dữ liệu thô sang kiểu Java đích. Ví dụ, JSON được chuyển thành CreateOrderCommand bằng một JSON converter như MappingJackson2MessageConverter.
5. Nếu tham số có @Valid hoặc @Validated và Spring có Validator hoạt động, Spring kiểm tra các constraint trên object vừa chuyển đổi.
6. Nếu chuyển đổi và validation đều thành công, Spring gọi method controller. Giá trị trả về có thể được chuyển đổi thành payload outbound và gửi tới broker theo destination mặc định hoặc @SendTo/@SendToUser.

Vì vậy, conversion xảy ra trước validation. Validator kiểm tra object Java đã được tạo; nó không sửa JSON sai cú pháp hoặc tự chuyển chuỗi không hợp lệ thành số.

## 2. Payload conversion và content-type

Trong STOMP, @Payload có vai trò lấy body của message và chuyển body sang kiểu tham số. Converter được chọn dựa trên payload, kiểu đích và thông tin content type. Với JSON, client nên gửi content-type:application/json và body có cấu trúc khớp với DTO.

Ví dụ một STOMP SEND frame gửi tới application destination:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"customerId":"C-001","quantity":2,"note":"Giao giờ hành chính"}
~~~

Nếu cấu hình application destination prefix là /app, phần destination còn lại là /orders.create được so khớp với @MessageMapping("/orders.create"). Đây là destination của application handler; /topic và /queue thường được dùng cho các destination broker mà client subscribe.

Một cấu hình tối thiểu:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Cấu hình trên minh họa endpoint và destination prefix. Ứng dụng thực tế cần cấu hình origin, xác thực, phân quyền và broker phù hợp với môi trường triển khai. Converter JSON phải có mặt trong danh sách converter được cấu hình; trong cấu hình Spring phổ biến, Jackson có thể được dùng thông qua MappingJackson2MessageConverter.

## 3. Bật Bean Validation

Với Spring Boot, có thể thêm các starter sau (version được quản lý bởi Spring Boot dependency management):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

spring-boot-starter-validation đưa Bean Validation API và một provider tương thích vào classpath. Nếu dùng Spring Framework trực tiếp, cần dependency messaging/websocket phù hợp, thư viện JSON nếu dùng JSON, Jakarta Validation API và một implementation như Hibernate Validator. Chỉ có annotation API mà không có provider thì chưa đủ để thực thi các constraint.

Trong cấu hình STOMP chuẩn, Spring tìm Validator tùy chỉnh trước, sau đó có thể dùng validator MVC sẵn có, hoặc tạo OptionalValidatorFactoryBean nếu tìm thấy implementation Bean Validation trên classpath. Nếu không có validator phù hợp, cấu hình mặc định có thể dùng no-op Validator; khi đó @Valid/@Validated xuất hiện trong chữ ký nhưng constraint không thực sự được kiểm tra. Nếu tự tạo message handler, argument resolver hoặc factory riêng, phải bảo đảm Validator được truyền vào cấu hình đó.

Spring Framework 6 trở lên dùng namespace Jakarta, ví dụ jakarta.validation.Valid và jakarta.validation.constraints.NotBlank. Spring Framework 5.x dùng namespace javax.validation tương ứng. Không trộn annotation API javax với provider/stack Jakarta hoặc ngược lại; hãy dùng namespace phù hợp với phiên bản Spring và dependency của dự án.

## 4. Khai báo constraint trên DTO

Nên nhận dữ liệu client bằng DTO chuyên biệt thay vì bind trực tiếp vào JPA entity hoặc object nội bộ. Constraint mô tả điều kiện dữ liệu ở biên nhận message.

~~~java
package com.example.messaging;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class CreateOrderCommand {

    @NotBlank(message = "customerId must not be blank")
    private String customerId;

    @NotNull(message = "quantity is required")
    @Positive(message = "quantity must be greater than 0")
    private Integer quantity;

    @Size(max = 200, message = "note must contain at most 200 characters")
    private String note;

    public CreateOrderCommand() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Các constraint thường dùng:

- @NotNull: giá trị không được null.
- @NotBlank: chuỗi phải khác null và có ít nhất một ký tự không phải khoảng trắng.
- @NotEmpty: chuỗi, collection hoặc map không được null và không được rỗng.
- @Size(min, max): giới hạn độ dài chuỗi hoặc kích thước collection/map.
- @Positive và @PositiveOrZero: kiểm tra số dương hoặc không âm.
- @Min và @Max: giới hạn giá trị số nguyên.
- @Email: kiểm tra định dạng email theo validator.
- @Pattern: kiểm tra chuỗi theo biểu thức chính quy.

Với trường số có thể bị bỏ qua trong JSON, wrapper như Integer thường hữu ích hơn int: khi client không gửi trường, Integer có thể là null để @NotNull phát hiện; int sẽ nhận giá trị mặc định 0 và không phân biệt được trường bị thiếu với trường được gửi là 0.

Constraint trên field hoặc getter đều có thể được Bean Validation đọc theo cấu hình provider. Hãy giữ một quy ước nhất quán trong DTO. Với object lồng nhau, đặt @Valid ở thuộc tính cần cascade validation, ví dụ:

~~~java
@NotNull
@Valid
private ShippingAddress address;
~~~

Nếu thiếu @Valid ở thuộc tính lồng nhau, validator có thể kiểm tra address không null nhưng không đi sâu kiểm tra các constraint bên trong ShippingAddress.

## 5. Dùng @Valid trên tham số @MessageMapping

@Valid là annotation chuẩn Jakarta Validation. Đặt nó trên tham số payload để yêu cầu Spring kiểm tra object sau khi conversion thành công.

~~~java
package com.example.messaging;

import jakarta.validation.Valid;
import java.util.List;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;

@Controller
public class OrderMessageController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(@Valid @Payload CreateOrderCommand command) {
        // Thực hiện use case sau khi payload đã qua validation.
        return new OrderCreated(command.getCustomerId(), command.getQuantity());
    }

    @MessageExceptionHandler(MethodArgumentNotValidException.class)
    @SendToUser("/queue/errors")
    public ValidationError handleInvalidPayload(MethodArgumentNotValidException ex) {
        BindingResult result = ex.getBindingResult();

        List<FieldViolation> violations = result == null
                ? List.of()
                : result.getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getDefaultMessage()))
                    .toList();

        return new ValidationError("INVALID_PAYLOAD", violations);
    }

    public record OrderCreated(String customerId, Integer quantity) {
    }

    public record FieldViolation(String field, String message) {
    }

    public record ValidationError(String code, List<FieldViolation> violations) {
    }
}
~~~

Khi client gửi message hợp lệ, controller được gọi và kết quả được gửi tới /topic/orders. Khi payload đã chuyển đổi được nhưng vi phạm constraint, Spring ném MethodArgumentNotValidException trong package org.springframework.messaging.handler.annotation.support; method create không được thực thi. Exception handler ở cùng controller có thể chuyển lỗi thành một response ổn định tới user destination /user/queue/errors. Client cần subscribe destination này để nhận lỗi.

Chú ý import MethodArgumentNotValidException từ Spring Messaging như ví dụ. Đây là exception khác package với exception cùng tên trong Spring Web MVC. Đừng import nhầm org.springframework.web.bind.MethodArgumentNotValidException khi xử lý lỗi tham số của STOMP message.

## 6. Khác nhau giữa @Valid và @Validated

| Annotation | Nguồn | Cách dùng chính |
| --- | --- | --- |
| @Valid | Jakarta Validation | Kích hoạt validation theo group mặc định; cũng dùng để cascade validation vào object lồng nhau |
| @Validated | Spring Framework | Kích hoạt validation và cho phép chỉ định validation group hoặc dùng annotation tổng hợp |

Nếu chỉ cần kiểm tra các constraint thuộc group mặc định, dùng @Valid là lựa chọn đơn giản:

~~~java
@MessageMapping("/orders.create")
public void create(@Valid @Payload CreateOrderCommand command) {
    // ...
}
~~~

Khi một DTO có quy tắc khác nhau theo thao tác, có thể khai báo group và dùng @Validated:

~~~java
public interface OnCreate {
}

public class CreateOrderCommand {

    @NotBlank(groups = OnCreate.class)
    private String customerId;

    @NotNull(groups = OnCreate.class)
    @Positive(groups = OnCreate.class)
    private Integer quantity;

    // Constructor/getter/setter
}
~~~

~~~java
@MessageMapping("/orders.create")
public void create(
        @Validated(OnCreate.class) @Payload CreateOrderCommand command) {
    // Chỉ tiếp tục khi các constraint thuộc OnCreate đã đạt.
}
~~~

Các constraint được gán riêng cho OnCreate sẽ không tự động chạy khi chỉ dùng @Valid theo group mặc định. Khi dùng group, hãy bảo đảm method chọn đúng group và các constraint được gán đúng group. Nếu muốn một constraint chạy ở nhiều group, khai báo nhiều group cho constraint đó. Với object lồng nhau, vẫn cần @Valid trên thuộc tính để cascade; group sẽ được truyền theo quy tắc group conversion của Bean Validation nếu có cấu hình.

## 7. Phân biệt lỗi conversion và lỗi validation

Hai nhóm lỗi xảy ra ở hai thời điểm khác nhau:

| Tình huống | Kết quả |
| --- | --- |
| JSON sai cú pháp | MessageConverter không tạo được DTO; thường là lỗi conversion như MessageConversionException |
| JSON có quantity là chuỗi không thể chuyển thành Integer | Conversion thất bại trước validation |
| JSON hợp lệ, quantity = -2 | DTO được tạo; @Positive thất bại và phát sinh MethodArgumentNotValidException |
| JSON hợp lệ, customerId là chuỗi rỗng | DTO được tạo; @NotBlank thất bại |
| Tất cả trường hợp lệ | Controller method được gọi |

Ví dụ body sau là JSON hợp lệ và có thể chuyển thành DTO, nhưng không hợp lệ theo constraint:

~~~json
{
  "customerId": " ",
  "quantity": -2,
  "note": "Kiểm tra dữ liệu"
}
~~~

Trong ví dụ này, @NotBlank và @Positive phát hiện lỗi. Ngược lại, nếu quantity là "hai" trong khi DTO khai báo Integer, converter không thể tạo object đúng kiểu; Bean Validation chưa có object hợp lệ để kiểm tra. Có thể viết @MessageExceptionHandler riêng cho MessageConversionException nếu muốn trả lỗi định dạng thống nhất, nhưng không nên gộp lỗi parse/convert với lỗi constraint thành cùng một thông báo kỹ thuật.

## 8. Xử lý lỗi và thiết kế response

Với STOMP, lỗi validation không tự động trở thành HTTP 400 như một số luồng @RequestBody trong Spring MVC. Hãy quyết định cách phản hồi phù hợp với giao thức ứng dụng:

- Dùng @MessageExceptionHandler để xử lý exception từ method message handler.
- Dùng @SendToUser("/queue/errors") nếu lỗi cần trả về queue riêng của user/session; client thường subscribe /user/queue/errors.
- Trả mã lỗi ổn định và danh sách field/message có thể hiển thị. Không gửi stack trace, SQL, tên lớp nội bộ hoặc chi tiết nhạy cảm cho client.
- Nếu muốn xử lý lỗi conversion, đăng ký handler riêng cho MessageConversionException và trả mã như INVALID_MESSAGE_FORMAT.
- Nếu cần xử lý lỗi ở nhiều controller, cân nhắc cơ chế advice được Spring Messaging hỗ trợ trong phiên bản đang dùng; kiểm tra phạm vi exception handler thực tế thay vì giả định handler trong một controller áp dụng toàn ứng dụng.

Nội dung lỗi mặc định của Bean Validation có thể thay đổi theo provider, locale và message bundle. Trong API ổn định, nên định nghĩa message hoặc error code phù hợp, rồi ánh xạ sang response DTO của ứng dụng.

## 9. Lỗi thường gặp và cách kiểm tra

1. Annotation có nhưng dữ liệu sai vẫn lọt qua: kiểm tra provider Bean Validation có trên classpath không, namespace jakarta/javax có đúng phiên bản không, và Validator có thực sự được gắn vào message handler/resolver không.
2. Chỉ @Valid trên tham số mà object con không được kiểm tra: thêm @Valid trên thuộc tính lồng nhau; đồng thời bảo đảm object con có constraint.
3. @Validated không chạy constraint mong muốn: kiểm tra group trên annotation và group được truyền vào @Validated. Constraint thuộc Default không tự động chạy khi chỉ yêu cầu một custom group riêng.
4. JSON không map vào DTO: kiểm tra STOMP content-type, converter hỗ trợ MIME type, tên thuộc tính JSON, kiểu dữ liệu và constructor/accessor của DTO.
5. Validation không bắt trường bị thiếu: dùng wrapper type kết hợp @NotNull nếu cần phân biệt null với giá trị mặc định của primitive.
6. Client không nhận được lỗi: kiểm tra @MessageExceptionHandler có xử lý đúng exception, response được gửi tới đúng destination và client đã subscribe /user/queue/errors.
7. Dùng trực tiếp entity làm payload: tránh để client điều khiển các trường nội bộ như id, owner, role hoặc trạng thái. Dùng command DTO và kiểm tra quyền ở service.

## 10. Kiểm thử

Nên kiểm thử riêng conversion, validation và đường trả lỗi:

- Payload hợp lệ: controller được gọi đúng một lần và kết quả được gửi tới destination mong đợi.
- Thiếu customerId hoặc gửi chuỗi chỉ có khoảng trắng: @NotBlank thất bại.
- Thiếu quantity: @NotNull thất bại.
- quantity bằng 0 hoặc số âm: @Positive thất bại.
- note vượt quá giới hạn: @Size thất bại.
- JSON sai cú pháp hoặc quantity không chuyển được sang Integer: conversion handler được gọi, validation handler không được coi là nguyên nhân.
- DTO có object lồng nhau: constraint bên trong chỉ được kiểm tra khi cascade bằng @Valid.
- Validation group: chỉ các constraint thuộc group đã chọn được áp dụng theo cấu hình.
- Lỗi validation: response có code ổn định, field lỗi và thông báo phù hợp; không lộ thông tin nội bộ.

Validation ở client chỉ hỗ trợ trải nghiệm nhập liệu. Server vẫn phải kiểm tra mọi payload vì client có thể bỏ qua hoặc giả mạo kiểm tra phía giao diện. Bean Validation cũng không thay thế xác thực, phân quyền hay quy tắc nghiệp vụ cần truy vấn dữ liệu; các điều kiện như người gửi có quyền sửa đơn hàng hay đơn hàng còn ở trạng thái cho phép cập nhật phải được kiểm tra ở service/domain layer.

## 11. Tài liệu tham khảo

- [Annotated Controllers — Spring Framework, STOMP](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html): các tham số được hỗ trợ trong @MessageMapping, chuyển đổi payload và hỗ trợ @Valid/@Validated.
- [PayloadMethodArgumentResolver — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html): cách resolver chuyển đổi và validate payload.
- [MethodArgumentNotValidException — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html): exception và BindingResult của lỗi validation trong Spring Messaging.
- [AbstractMessageBrokerConfiguration — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/messaging/simp/config/AbstractMessageBrokerConfiguration.html): cách cấu hình Validator cho payload của message handler.
- [Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html): nền tảng Validator và validation trong Spring.
