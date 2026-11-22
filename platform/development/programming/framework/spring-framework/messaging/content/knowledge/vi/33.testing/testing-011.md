# Kiểm thử tương thích schema, phân quyền và dữ liệu không hợp lệ

> Phạm vi: kiểm thử hợp đồng message trong Spring Framework Messaging, đặc biệt với RSocket và Project Reactor. Mục tiêu là phát hiện thay đổi schema làm hỏng consumer, bảo đảm chỉ principal có quyền mới gọi được route, và từ chối payload sai cấu trúc hoặc vi phạm quy tắc nghiệp vụ trước khi tạo side effect.

## 1. Vì sao phải kiểm thử ba lớp riêng?

Một message đi qua nhiều bước: nhận frame hoặc message, xác thực và phân quyền, giải mã payload, kiểm tra hợp đồng, validate dữ liệu, rồi mới chạy nghiệp vụ. Mỗi bước có loại lỗi và ranh giới kiểm thử khác nhau.

- **Tương thích schema** trả lời: producer và consumer ở hai phiên bản khác nhau có hiểu cùng một message không?
- **Phân quyền** trả lời: danh tính đã xác thực có được phép gọi route hoặc thực hiện hành động này không?
- **Validation dữ liệu** trả lời: payload có đúng cấu trúc, trường bắt buộc, kiểu, miền giá trị và invariant nghiệp vụ không?

Không gộp mọi trường hợp lỗi thành một bài test “message thất bại”. Nếu test chỉ xác nhận rằng request có lỗi, một consumer có thể từ chối schema mới vì lỗi parse, hoặc từ chối user đúng quyền vì lỗi validation, nhưng bài test vẫn xanh. Mỗi test phải xác nhận nguyên nhân và kết quả mong đợi.

Một luồng kiểm tra thông thường:

1. Transport nhận payload và metadata.
2. Spring Security xác thực và áp dụng chính sách truy cập cho RSocket exchange/route.
3. Codec giải mã dữ liệu thành đối tượng Java.
4. Message argument resolver kiểm tra payload được đánh dấu `@Valid` hoặc `@Validated`.
5. Handler gọi service; service tiếp tục kiểm tra quyền nghiệp vụ và invariant cần thiết.
6. Kết quả hoặc lỗi được chuyển về requester theo hợp đồng giao tiếp.

Trong RSocket, data và metadata là hai phần riêng. Metadata có thể chứa route hoặc security token; data mang payload. Vì vậy, test payload JSON và test metadata xác thực phải bao phủ cả hai phần. RSocket hỗ trợ Request-Response, Request-Stream, Channel và Fire-and-Forget; test phải dùng đúng interaction model của handler. Một lệnh Fire-and-Forget chỉ xác nhận message đã được gửi, không chứng minh handler đã xử lý thành công.

## 2. Kiểm thử tương thích schema

### 2.1. Tương thích là quan hệ giữa producer và consumer

Không chỉ kiểm tra một JSON có deserialize được thành DTO hiện tại hay không. Cần kiểm tra những tổ hợp phiên bản mà hệ thống thực sự phải hỗ trợ.

| Producer | Consumer | Câu hỏi kiểm thử |
|---|---|---|
| Phiên bản cũ | Consumer mới | Consumer mới có đọc được message đã lưu từ trước không? |
| Phiên bản mới, thêm field tùy chọn | Consumer cũ | Consumer cũ có bỏ qua field mới theo chính sách đã công bố không? |
| Phiên bản mới | Consumer mới | Consumer mới có hiểu field, kiểu và ngữ nghĩa mới không? |
| Phiên bản phá vỡ tương thích | Consumer cũ | Consumer cũ có từ chối rõ ràng thay vì diễn giải sai không? |
| Payload replay từ kho lưu trữ | Consumer hiện tại | Message lịch sử có còn được giải mã và xử lý đúng không? |

Với một thay đổi tương thích như thêm field tùy chọn, consumer cũ thường cần bỏ qua field chưa biết, còn consumer mới cần chấp nhận việc field mới vắng mặt trong message cũ. Điều này phải là chính sách có chủ đích của serializer và schema, không nên dựa vào mặc định ngẫu nhiên của thư viện.

Với thay đổi phá vỡ tương thích, tăng major/schema version theo quy ước của hệ thống và từ chối version chưa hỗ trợ. Không tự đoán schema mới bằng cách deserialize theo DTO cũ.

### 2.2. Những thay đổi cần kiểm thử

- Thêm field tùy chọn và field bắt buộc.
- Bỏ field hoặc đổi tên field.
- Đổi kiểu, ví dụ số thành chuỗi hoặc timestamp thành epoch.
- Đổi đơn vị hoặc ý nghĩa nghiệp vụ nhưng giữ nguyên tên field.
- Thay đổi quy tắc null, default hoặc enum.
- Thay đổi cấu trúc lồng nhau, collection hoặc kiểu generic.
- Thay đổi cách serialize thời gian, decimal, UUID và dữ liệu nhị phân.
- Payload cũ được lưu trong database, outbox, broker hoặc dead-letter queue.
- Consumer chạy đồng thời với nhiều producer version trong thời gian rolling deployment.

Thêm field thường có thể tương thích về mặt cấu trúc, nhưng không tự động tương thích về ngữ nghĩa. Ví dụ, thêm `currency` là an toàn khi consumer cũ có thể bỏ qua và consumer mới có default/validation rõ ràng. Đổi `amount` từ “trước thuế” sang “sau thuế” mà không đổi tên hoặc version là thay đổi phá vỡ hợp đồng dù JSON vẫn parse được.

### 2.3. Dùng fixture cố định

Lưu các message đại diện trong `src/test/resources/contracts/`, ví dụ:

- `order-created-v1.json`: payload do producer cũ phát.
- `order-created-v1-with-note.json`: cùng schema version, có field tùy chọn mới.
- `order-created-v2-breaking.json`: version mới với thay đổi không tương thích.
- `order-created-invalid.json`: JSON hợp lệ về cú pháp nhưng thiếu hoặc sai dữ liệu nghiệp vụ.

Fixture nên được review như một phần của API contract. Không tạo fixture bằng chính serializer của class đang test rồi chỉ deserialize lại ngay lập tức; cách đó có thể che giấu thay đổi vì producer và consumer cùng thay đổi theo một hướng sai.

### 2.4. Test tương thích với Jackson 3

Ví dụ sau dùng Jackson 3, là JSON mapper mặc định trong Spring Boot 4.x. Mapper được cấu hình rõ để cho phép consumer cũ bỏ qua field bổ sung. DTO V1 không có field `note`; DTO V2 có field này nhưng chấp nhận dữ liệu cũ khi field vắng mặt.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import static org.junit.jupiter.api.Assertions.*;

class MessageSchemaCompatibilityTests {

    private final JsonMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    record OrderCreatedV1(String orderId, BigDecimal total) {}

    record OrderCreatedV2(
        String orderId,
        BigDecimal total,
        String note
    ) {}

    private static final String V1 = """
        {
          "schemaVersion": 1,
          "messageId": "evt-1001",
          "occurredAt": "2026-11-07T14:00:00Z",
          "data": {
            "orderId": "ORD-1001",
            "total": 125000.00
          }
        }
        """;

    private static final String V1_WITH_OPTIONAL_FIELD = """
        {
          "schemaVersion": 1,
          "messageId": "evt-1002",
          "occurredAt": "2026-11-07T14:01:00Z",
          "data": {
            "orderId": "ORD-1002",
            "total": 99000.00,
            "note": "gift wrap"
          }
        }
        """;

    private static final String V2_BREAKING = """
        {
          "schemaVersion": 2,
          "messageId": "evt-2001",
          "occurredAt": "2026-11-07T14:02:00Z",
          "data": {
            "id": "ORD-2001",
            "total": "125000.00"
          }
        }
        """;

    @Test
    void newConsumerReadsMessageFromOldProducer() throws Exception {
        JsonNode envelope = mapper.readTree(V1);

        assertSupportedVersion(envelope.get("schemaVersion").asInt());

        OrderCreatedV2 data = mapper.readValue(
            envelope.get("data").toString(),
            OrderCreatedV2.class
        );

        assertEquals("ORD-1001", data.orderId());
        assertEquals(0, data.total().compareTo(new BigDecimal("125000.00")));
        assertNull(data.note());
    }

    @Test
    void oldConsumerIgnoresAnAddedOptionalField() throws Exception {
        JsonNode envelope = mapper.readTree(V1_WITH_OPTIONAL_FIELD);

        assertSupportedVersion(envelope.get("schemaVersion").asInt());

        OrderCreatedV1 data = mapper.readValue(
            envelope.get("data").toString(),
            OrderCreatedV1.class
        );

        assertEquals("ORD-1002", data.orderId());
        assertEquals(0, data.total().compareTo(new BigDecimal("99000.00")));
    }

    @Test
    void consumerRejectsAnUnsupportedBreakingVersion() throws Exception {
        JsonNode envelope = mapper.readTree(V2_BREAKING);

        assertThrows(
            UnsupportedSchemaVersionException.class,
            () -> assertSupportedVersion(envelope.get("schemaVersion").asInt())
        );
    }

    private static void assertSupportedVersion(int version) {
        if (version != 1) {
            throw new UnsupportedSchemaVersionException(version);
        }
    }

    static class UnsupportedSchemaVersionException extends RuntimeException {
        UnsupportedSchemaVersionException(int version) {
            super("Unsupported message schema version: " + version);
        }
    }
}
~~~

Ở ví dụ này, field `note` được thêm mà vẫn giữ `schemaVersion = 1` vì nó là field tùy chọn và chính sách tương thích cho phép cả hai phía đọc. Version 2 mô tả thay đổi phá vỡ hợp đồng nên consumer V1 từ chối trước khi cố gắng diễn giải payload. Trong hệ thống thực tế, quy tắc tăng version phải được định nghĩa thống nhất: có tổ chức tăng version cho mọi thay đổi schema, có tổ chức chỉ tăng major version cho thay đổi không tương thích.

Jackson 3 mặc định có chính sách khác Jackson 2 ở một số tính năng. Hãy cấu hình mapper dùng trong test giống mapper production; đừng dựa vào cấu hình mapper tự tạo khác với RSocket codec thực tế.

## 3. Kiểm thử phân quyền message

### 3.1. Authentication và authorization là hai kiểm tra khác nhau

- **Authentication** xác minh caller là ai, ví dụ kiểm tra JWT hoặc thông tin đăng nhập.
- **Authorization** quyết định principal đã xác thực có quyền thực hiện hành động trên route/tài nguyên cụ thể không.

Một JWT hợp lệ không có nghĩa caller được phép gọi mọi route. Cần kiểm tra cả token không hợp lệ, token hết hạn, principal không có authority, role sai và role đúng.

Không lấy user ID hoặc role từ payload làm bằng chứng quyền truy cập. Client có thể sửa payload. Danh tính và quyền phải đến từ SecurityContext/Authentication được Spring Security xác thực.

### 3.2. Phân quyền RSocket theo route

Spring Security hỗ trợ `authorizePayload` để áp dụng rule cho RSocket exchange. Các rule được xét theo thứ tự; rule đầu tiên khớp sẽ được áp dụng. Đặt rule cụ thể trước rule fallback và khóa mặc định.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.interceptor.PayloadSocketAcceptorInterceptor;
import org.springframework.security.config.Customizer;

@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(RSocketSecurity rsocket) {
        rsocket
            .authorizePayload(authorize -> authorize
                .route("orders.create").hasRole("ORDER_WRITER")
                .route("orders.read").hasRole("ORDER_READER")
                .anyRequest().denyAll()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

Cấu hình JWT cần có `ReactiveJwtDecoder` phù hợp với issuer hoặc khóa xác minh của hệ thống. Nếu dùng Simple Authentication, cấu hình `simpleAuthentication` và encoder tương ứng thay cho `jwt`.

Trong ví dụ:

- `orders.create` chỉ dành cho principal có authority `ROLE_ORDER_WRITER`.
- `orders.read` chỉ dành cho principal có authority `ROLE_ORDER_READER`.
- Request khác bị từ chối theo chính sách allowlist.
- Exchange không khớp rule nào bị từ chối.

Không quên phân quyền cả các request phụ như channel hoặc metadata push nếu chúng có thể gây tác dụng phụ. Rule `anyRequest` chỉ khớp payload thuộc loại request; `anyExchange` là fallback rộng hơn.

### 3.3. Credentials ở SETUP hay ở từng request?

RSocket có thể xác thực khi mở connection hoặc khi gửi từng request:

- Nếu một connection chỉ thuộc về một user, authentication ở SETUP có thể phù hợp.
- Nếu nhiều user dùng chung một connection đến service, credentials cần được gắn vào từng request để server phân biệt principal của từng user.
- Một số hệ thống xác thực cả client/service ở SETUP và user cuối ở từng request.

Test phải mô phỏng đúng mô hình thực tế. Nếu production gửi token trong request metadata nhưng test chỉ xác thực ở SETUP, test chưa bao phủ đường đi credentials thật.

Ví dụ gửi bearer token trong request metadata:

~~~java
MimeType authenticationMimeType = MimeType.valueOf(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
);

BearerTokenMetadata token = new BearerTokenMetadata(jwt);

Mono<OrderAccepted> response = requester
    .route("orders.create")
    .metadata(token, authenticationMimeType)
    .data(command)
    .retrieveMono(OrderAccepted.class);
~~~

Nếu credentials được gửi ở SETUP, dùng `setupMetadata(token, authenticationMimeType)` khi tạo requester. Không ghi token vào log hoặc fixture được commit vào repository.

### 3.4. Test reactive method security

Phân quyền route và phân quyền service là hai lớp khác nhau. Có thể bảo vệ service bằng `@PreAuthorize` để tránh một caller nội bộ hoặc một đường gọi khác bỏ qua rule của route.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class OrderCommandService {

    @PreAuthorize("hasAuthority('orders:write')")
    Mono<String> create(String orderId) {
        return Mono.just(orderId);
    }
}
~~~

Bật reactive method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Test quyền bằng `@WithMockUser` và `StepVerifier`:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
    MethodSecurityConfiguration.class,
    OrderCommandService.class
})
class OrderCommandServiceSecurityTests {

    @Autowired
    OrderCommandService service;

    @Test
    void anonymousCallerIsDenied() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(authorities = "orders:read")
    void readerCannotCreateOrder() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(authorities = "orders:write")
    void writerCanCreateOrder() {
        StepVerifier.create(service.create("ORD-1001"))
            .expectNext("ORD-1001")
            .verifyComplete();
    }
}
~~~

Với reactive method security, security context được truyền qua Reactor Context. Dùng `StepVerifier` để subscribe publisher trong test. Không gọi `block()` trước khi kiểm tra security context vì thao tác đó có thể làm mất ngữ cảnh mà test cần xác minh.

`@WithMockUser` ở trên kiểm thử method security. Nó không tự kiểm thử JWT decoder, RSocket metadata, `PayloadSocketAcceptorInterceptor` hoặc route matcher. Những thành phần đó cần test tích hợp qua một RSocket server và requester thật.

## 4. Kiểm thử dữ liệu không hợp lệ

### 4.1. Phân biệt lỗi cú pháp, lỗi schema và lỗi nghiệp vụ

| Loại lỗi | Ví dụ | Lớp phát hiện |
|---|---|---|
| JSON/codec không hợp lệ | JSON thiếu dấu ngoặc, số không thể chuyển thành kiểu đích | Decoder/MessageConverter |
| Sai cấu trúc schema | Thiếu field bắt buộc, sai kiểu, version không hỗ trợ | Schema/contract validation |
| Sai constraint dữ liệu | ID rỗng, amount âm, currency sai định dạng | Bean Validation |
| Sai invariant nghiệp vụ | Đơn hàng đã đóng, tài khoản không thuộc user | Domain/service validation |
| Sai quyền | Caller không có quyền tạo đơn hàng | Spring Security |

Một payload có thể là JSON hợp lệ nhưng vẫn không hợp lệ về nghiệp vụ. Ví dụ `{"orderId":"","amount":-10}` parse được thành object, nhưng không được phép đi vào service tạo đơn.

### 4.2. Bean Validation cho DTO message

Dùng Jakarta Bean Validation để mô tả ràng buộc ngay trên DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public record CreateOrder(
    @NotBlank
    String orderId,

    @NotNull
    @DecimalMin("0.01")
    BigDecimal amount,

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    String currency
) {
}
~~~

Các constraint có ý nghĩa:

- `@NotBlank`: chuỗi không null, không rỗng và có ký tự không phải whitespace.
- `@NotNull`: trường bắt buộc phải có giá trị.
- `@DecimalMin`: số tiền phải lớn hơn hoặc bằng ngưỡng chỉ định.
- `@Pattern`: currency có dạng ba chữ cái viết hoa trong ví dụ này.

Bean Validation không tự quyết định mọi quy tắc nghiệp vụ. Ví dụ amount có thể phải lớn hơn 0, nhưng giới hạn tối đa còn tùy loại tài khoản hoặc loại giao dịch; quy tắc đó có thể cần kiểm tra trong service.

### 4.3. Validate payload của @MessageMapping

Spring Messaging hỗ trợ validation khi tham số payload của handler được đánh dấu `@Valid` hoặc `@Validated`. Khi validation thất bại, `PayloadMethodArgumentResolver` phát sinh `MethodArgumentNotValidException`.

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class OrderRSocketController {

    private final OrderCommandService service;

    OrderRSocketController(OrderCommandService service) {
        this.service = service;
    }

    @MessageMapping("orders.create")
    Mono<OrderAccepted> create(@Valid @Payload CreateOrder command) {
        return service.create(command);
    }
}
~~~

Đảm bảo RSocket message handler được cấu hình với một Spring `Validator`/Bean Validation provider. Với handler tự cấu hình, `MessageMappingMessageHandler.setValidator(...)` là điểm cấu hình validator cho các tham số `@Payload`. Spring Boot có thể cung cấp infrastructure tương ứng khi dependency validation có mặt, nhưng custom handler cần được kiểm tra cấu hình thực tế.

Validation xảy ra ở ranh giới handler trước khi gọi service. Nếu dữ liệu không hợp lệ, không thực hiện ghi database, gửi event hoặc gọi hệ thống ngoài. Test nên kiểm tra cả lỗi được trả về và việc service không bị gọi.

### 4.4. Unit test constraint trực tiếp

Có thể kiểm thử DTO bằng Jakarta Validator mà không cần mở RSocket server:

~~~java
import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CreateOrderValidationTests {

    @Test
    void rejectsBlankIdNegativeAmountAndMalformedCurrency() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            CreateOrder invalid = new CreateOrder(
                " ",
                new BigDecimal("-10.00"),
                "US"
            );

            Set<String> invalidFields = validator.validate(invalid)
                .stream()
                .map(error -> error.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertTrue(invalidFields.contains("orderId"));
            assertTrue(invalidFields.contains("amount"));
            assertTrue(invalidFields.contains("currency"));
        }
    }
}
~~~

Test này xác minh constraint trên DTO. Nó chưa chứng minh Spring RSocket handler thực sự gắn validator vào argument resolver. Vì vậy vẫn cần ít nhất một integration test gửi payload không hợp lệ qua RSocket và xác nhận handler/service không tạo side effect.

## 5. Test tích hợp RSocket cho quyền và payload

Một integration test quan trọng nên khởi động RSocket server trên port riêng của test, kết nối bằng `RSocketRequester`, gửi metadata xác thực và gọi route như client production.

Dùng ma trận kiểm thử:

| Principal/token | Route | Kết quả mong đợi | Side effect |
|---|---|---|---|
| Không có token | `orders.create` | Bị từ chối | Service không được gọi |
| Token sai chữ ký/hết hạn | `orders.create` | Authentication thất bại | Service không được gọi |
| Role `ORDER_READER` | `orders.create` | Authorization bị từ chối | Không ghi đơn |
| Role `ORDER_WRITER` | `orders.create` | Request hợp lệ được xử lý | Tạo đúng một đơn |
| Role `ORDER_READER` | `orders.read` | Được phép đọc | Không có write side effect |
| Role hợp lệ | Route không khai báo | Bị từ chối theo fallback | Không gọi handler |
| Role `ORDER_WRITER` | `orders.create`, payload sai | Validation thất bại | Không ghi đơn |
| Role `ORDER_WRITER` | `orders.create`, payload đúng | Thành công | Ghi đúng dữ liệu |

Ví dụ dạng kiểm thử cho một requester đã được tạo với token của user chỉ có quyền đọc:

~~~java
@Test
void readerCannotCreateOrder() {
    RSocketRequester readerRequester = requesterFor(readerToken);

    StepVerifier.create(
        readerRequester
            .route("orders.create")
            .data(validCreateOrder)
            .retrieveMono(OrderAccepted.class)
    )
    .expectError()
    .verify();

    verify(orderCommandService, never()).create(any());
}
~~~

`requesterFor` là helper của test để kết nối tới port test và gửi token theo đúng cách ứng dụng cấu hình: ở SETUP hoặc trong từng request metadata. Test đầy đủ cần khởi tạo server, decoder/encoder, token test hợp lệ, mock hoặc spy service và đóng requester/server sau mỗi test.

Không nên chỉ kiểm tra exception. Hãy xác nhận service không được gọi hoặc database không đổi khi caller bị từ chối. Điều này phát hiện trường hợp handler vô tình thực hiện side effect trước khi quyền được kiểm tra.

### 5.1. Kiểm thử payload không hợp lệ qua RSocket

Gửi một payload JSON hợp lệ về cú pháp nhưng vi phạm Bean Validation, ví dụ amount âm. Xác nhận:

- Request trả lỗi theo hợp đồng lỗi của ứng dụng.
- Lỗi có thể phân loại là validation failure.
- Handler/service không thực hiện thao tác ghi.
- Không trả lại stack trace, SQL, token hoặc thông tin nội bộ cho caller.

Sau đó gửi JSON sai cú pháp hoặc sai kiểu, ví dụ `amount` là object thay vì decimal. Lỗi này phát sinh ở bước decode/conversion, trước Bean Validation. Test riêng hai trường hợp để tránh biến lỗi giải mã thành thông báo “dữ liệu nghiệp vụ không hợp lệ” chung chung.

RSocket không trả HTTP status cho request như REST. Hãy kiểm tra RSocket error frame/application error code và error payload mà ứng dụng định nghĩa. Trong test client, exception có thể được wrap bởi lớp RSocket/Reactor; nên assert loại lỗi hoặc mã lỗi ổn định mà API cam kết, không phụ thuộc vào message text nội bộ dễ thay đổi.

## 6. Kiểm thử thứ tự và tính độc lập của các lớp

Các test cần chứng minh những điều sau:

- User thiếu quyền không thể tạo side effect dù payload đúng.
- User có quyền vẫn bị từ chối nếu payload sai.
- Payload hợp lệ không làm cho user thiếu quyền trở nên hợp lệ.
- Schema version không hỗ trợ bị từ chối rõ ràng, kể cả payload bên trong tình cờ parse được.
- Message bị retry/redelivery không tạo side effect trùng nếu nghiệp vụ yêu cầu idempotency.
- Lỗi validation không bị retry như lỗi mạng tạm thời.
- Lỗi authorization không bị chuyển thành fallback thành công.
- Error handler không làm lộ nội dung nhạy cảm của payload hoặc SecurityContext.

Không nhất thiết khóa chặt thứ tự nội bộ giữa mọi interceptor nếu framework có thể thay đổi. Hãy kiểm tra ranh giới bảo mật và hợp đồng observable: caller không được truy cập, service không chạy, dữ liệu không thay đổi, lỗi trả về đúng nhóm.

## 7. Tổ chức test suite

Nên chia test thành các nhóm có tốc độ và mục tiêu khác nhau:

1. **DTO unit tests**: Bean Validation, constructor invariant, enum, decimal, timestamp và giới hạn kích thước.
2. **Schema contract tests**: fixture producer cũ/mới, version hỗ trợ, field bổ sung, field bị bỏ và thay đổi không tương thích.
3. **Service authorization tests**: `@PreAuthorize`, quyền đọc/ghi, anonymous và principal sai authority.
4. **Handler tests**: `@MessageMapping`, `@Valid`, exception mapping và không gọi service khi validation fail.
5. **RSocket integration tests**: kết nối thật, route metadata, credentials, codec và error frame.
6. **Persistence/consumer tests**: deduplication, transaction rollback, retry, outbox và replay fixture lịch sử.

Chạy unit test nhanh ở mỗi thay đổi; integration test chạy trong CI trước khi merge hoặc phát hành. Contract fixture nên được kiểm tra trong CI của cả producer lẫn consumer nếu hai dự án triển khai độc lập.

### 7.1. Dependency test cơ bản với Spring Boot 4.1.x

Một module Spring Boot có thể dùng dependency management của parent để đồng bộ phiên bản:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot 4 dùng Jackson 3 làm JSON mapper mặc định. Nếu ứng dụng còn dùng Jackson 2 hoặc custom codec, hãy dùng đúng mapper và decoder mà RSocket production đang sử dụng trong contract test. Test với một mapper riêng có cấu hình khác có thể cho kết quả sai lệch so với lúc chạy thật.

## 8. Lỗi thường gặp khi viết test

1. **Chỉ test serialize rồi deserialize cùng một DTO.** Cả hai phía cùng thay đổi nên không phát hiện producer/consumer lệch version. Dùng fixture cố định từ các version trước.
2. **Chỉ test happy path.** Bổ sung test thiếu token, role sai, version không hỗ trợ, JSON sai và constraint vi phạm.
3. **Dùng `@WithMockUser` để kết luận RSocket JWT hoạt động.** Annotation này mô phỏng security context cho method security; nó không test token metadata, JWT decoder hoặc RSocket interceptor.
4. **Chỉ assert có exception.** Assert loại lỗi/mã lỗi và xác nhận không có side effect.
5. **Tin field `userId` trong message.** Dùng principal đã xác thực để xác định người dùng; kiểm tra quyền trên tài nguyên theo server-side data.
6. **Bỏ qua field lạ mà không có chính sách.** Việc ignore unknown fields giúp tương thích additive nhưng có thể che typo. Cần contract test, schema validation và log/metric phù hợp.
7. **Kiểm tra quyền chỉ ở client.** Client UI có thể ẩn nút nhưng server vẫn phải enforce authorization.
8. **Dùng role rộng cho mọi route.** Tách quyền đọc, ghi, quản trị và quyền trên từng tài nguyên khi nghiệp vụ cần.
9. **Chỉ validate ở tầng transport.** Consumer nội bộ, replay hoặc batch job có thể gọi service mà không đi qua RSocket handler. Giữ invariant quan trọng ở service/domain boundary.
10. **Dùng message lỗi chứa toàn bộ payload.** Log an toàn bằng message ID, route, error category và field path; che hoặc bỏ dữ liệu nhạy cảm.

## 9. Checklist trước khi phát hành message contract

- [ ] Có fixture cho từng schema version còn được hỗ trợ.
- [ ] Consumer mới đọc được message cũ theo chính sách tương thích.
- [ ] Producer mới không làm consumer cũ lỗi khi chỉ thêm field tương thích.
- [ ] Consumer từ chối schema version không hỗ trợ.
- [ ] Có test cho JSON sai cú pháp, sai kiểu và field bắt buộc bị thiếu.
- [ ] Có test cho Bean Validation và invariant nghiệp vụ.
- [ ] Có test anonymous, token không hợp lệ, role sai và role đúng.
- [ ] Có integration test xác thực metadata trên RSocket route thật.
- [ ] Unauthorized request không gọi service hoặc tạo side effect.
- [ ] Invalid payload không ghi database, phát event hoặc gọi downstream.
- [ ] Retry/redelivery không gây xử lý trùng khi yêu cầu idempotency.
- [ ] Error response không lộ token, stack trace hoặc dữ liệu nhạy cảm.
- [ ] Test dùng cùng codec/mapper và security configuration với production.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, annotated responders, data và metadata.
- [Spring Framework Javadoc — PayloadMethodArgumentResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html): validation cho payload có `@Valid` hoặc `@Validated`, và `MethodArgumentNotValidException`.
- [Spring Framework Javadoc — MessageMappingMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): cấu hình Validator cho `@Payload`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Bean Validation và LocalValidatorFactoryBean.
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/rsocket.html): authentication metadata, route authorization và authorizePayload.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/7.0/reactive/test/method.html): test reactive method security với `@WithMockUser` và `StepVerifier`.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/): test support, JUnit Jupiter và các dependency kiểm thử.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3 và cấu hình JsonMapper.
