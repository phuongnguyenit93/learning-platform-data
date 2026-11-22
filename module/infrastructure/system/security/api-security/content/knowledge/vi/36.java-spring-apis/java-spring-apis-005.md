# Jackson allowlist polymorphic type

Polymorphic deserialization cho phép Jackson tạo một trong nhiều subtype dựa trên discriminator trong JSON. Cách này hữu ích khi API nhận nhiều loại command hoặc event có cấu trúc chung, chẳng hạn `email` và `sms` cùng là một loại notification request. Tuy nhiên, nếu client được tự chọn class cần khởi tạo, payload có thể điều khiển object graph theo cách ngoài dự kiến và mở rộng bề mặt tấn công.

Với Java/Spring API, hãy coi type metadata trong request là dữ liệu không đáng tin cậy. Chỉ cho phép những subtype đã được công bố rõ trong contract, dùng logical type ID ổn định và DTO riêng cho từng use case. Tránh bật default typing toàn cục hoặc để JSON chọn tên class Java. Type allowlist giới hạn kiểu object Jackson có thể tạo; nó không thay thế authentication, function authorization, object authorization, validation hay kiểm soát side effect.

## 1. Polymorphic deserialization là gì?

Giả sử endpoint gửi notification nhận hai dạng request:

```json
{
  "kind": "email",
  "to": "user@example.test",
  "subject": "Invoice ready",
  "body": "Your invoice is ready."
}
```

```json
{
  "kind": "sms",
  "phoneNumber": "+12025550123",
  "message": "Your invoice is ready."
}
```

Hai payload có cấu trúc khác nhau nhưng cùng thuộc một contract `NotificationCommand`. Jackson cần biết payload tương ứng với subtype nào để tạo object Java đúng kiểu. Trường `kind` là discriminator: một giá trị logic do API quy định, ví dụ `email` hoặc `sms`.

Polymorphism thường được dùng cho:

- Event envelope có nhiều event type.
- Command API có nhiều loại thao tác được mô tả trong contract.
- Notification, payment method hoặc integration configuration có các biến thể hợp lệ.
- Response model có nhiều subtype khi serialize ra JSON.

Chỉ bật polymorphism khi API thực sự cần nhiều biến thể. Nếu endpoint chỉ nhận một loại dữ liệu, DTO cụ thể đơn giản và dễ kiểm soát hơn.

## 2. Rủi ro khi client điều khiển class được khởi tạo

Jackson có thể đọc type metadata để quyết định subtype. Cách cấu hình nguy hiểm là cho phép client gửi tên class Java hoặc bật default typing rộng trên ObjectMapper dùng để đọc request bên ngoài.

Ví dụ payload không nên được chấp nhận:

```json
{
  "@class": "some.package.InternalImplementation",
  "value": "untrusted"
}
```

Nếu deserializer được cấu hình cho phép class tùy ý, payload có thể yêu cầu tạo object ngoài contract. Tùy class, thư viện và object graph, quá trình khởi tạo/deserialization có thể kích hoạt setter, constructor, callback hoặc hành vi phụ thuộc dữ liệu. Kể cả khi không có gadget chain để thực thi code, attacker vẫn có thể tạo object không mong đợi, vượt qua validation hoặc làm tăng chi phí xử lý.

Các cấu hình cần tránh với input không tin cậy:

- `JsonTypeInfo.Id.CLASS`: type ID là tên class đầy đủ.
- `JsonTypeInfo.Id.MINIMAL_CLASS`: type ID vẫn gắn với tên class theo dạng rút gọn.
- `ObjectMapper.activateDefaultTyping(...)` trên mapper dùng cho public API mà không có giới hạn chặt.
- API deprecated `enableDefaultTyping(...)` hoặc cấu hình tương đương được bật toàn cục.
- `Object`, `Serializable`, `Map<String, Object>` hoặc collection generic rộng làm kiểu đích cho dữ liệu command nhạy cảm.
- Validator cho phép cả package lớn hoặc mọi subtype của một base type chung mà không đánh giá từng class.

Không phải mọi polymorphic payload đều nguy hiểm. Rủi ro phụ thuộc type resolver, danh sách subtype, class có thể được tạo và cách ứng dụng dùng object sau khi deserialize. Nhưng public API không nên để client quyết định tên class Java cần khởi tạo.

## 3. Dùng logical type ID với `JsonTypeInfo.Id.NAME`

Với API nhận JSON từ client, cách tiếp cận rõ ràng là khai báo tập subtype hợp lệ bằng `@JsonSubTypes` và dùng `JsonTypeInfo.Id.NAME`. JSON chỉ chứa tên logic do contract định nghĩa, không chứa tên class hoặc package Java.

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(value = EmailCommand.class, name = "email"),
        @JsonSubTypes.Type(value = SmsCommand.class, name = "sms")
})
public interface NotificationCommand {
}
```

Các subtype là DTO cụ thể:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record EmailCommand(
        @NotBlank @Email @Size(max = 254) String to,
        @NotBlank @Size(max = 160) String subject,
        @NotBlank @Size(max = 10_000) String body
) implements NotificationCommand {
}

public record SmsCommand(
        @NotBlank @Size(max = 30) String phoneNumber,
        @NotBlank @Size(max = 1_000) String message
) implements NotificationCommand {
}
```

Với cấu hình này, JSON dùng `"kind":"email"` hoặc `"kind":"sms"`. Jackson chỉ có thể resolve những logical ID đã đăng ký cho base type. Một class name như `some.package.InternalImplementation` không tự trở thành subtype hợp lệ chỉ vì client gửi nó trong `kind`.

`Id.NAME` là lựa chọn an toàn hơn cho public contract, nhưng vẫn cần kiểm tra subtype registry thực tế. Các module, mix-in hoặc `registerSubtypes(...)` khác có thể bổ sung subtype. Giữ danh sách đăng ký nhỏ, review mọi thay đổi và không tự động scan cả package để đăng ký tất cả class.

## 4. Không dùng tên class Java làm API contract

Logical ID như `email`, `sms`, `invoice-paid` hoặc `bank-transfer` tách contract bên ngoài khỏi tên class triển khai bên trong.

Lợi ích:

- Có thể đổi tên hoặc di chuyển class mà không làm client phải thay payload.
- Không để client biết package, cấu trúc module hoặc class nội bộ.
- Dễ review subtype nào được phép xuất hiện trong từng API.
- Có thể version hóa logical ID theo contract khi schema thay đổi không tương thích.
- Không tạo cơ chế class loading từ dữ liệu request.

Không đặt type ID theo convention tự động từ class name nếu convention đó làm lộ tên package hoặc khiến mọi class mới vô tình được chấp nhận. Type ID là một phần của API contract, cần được quản lý như enum/operation name.

## 5. Unknown type phải bị từ chối

Nếu request gửi `kind` không có trong allowlist, Jackson cần báo lỗi deserialization. Không cấu hình `defaultImpl` thành một subtype có quyền rộng chỉ để request cũ tiếp tục hoạt động.

Ví dụ payload không hợp lệ:

```json
{
  "kind": "admin-command",
  "operation": "grant-all"
}
```

Các nguyên tắc:

- Giữ `DeserializationFeature.FAIL_ON_INVALID_SUBTYPE` bật.
- Không dùng `defaultImpl` cho command/event nhạy cảm trừ khi fallback là một kiểu an toàn, có contract rõ và không làm thay đổi ý nghĩa nghiệp vụ.
- Không âm thầm chuyển unknown type thành `Object`, `Map` hoặc một subtype có quyền cao.
- Map lỗi type ID sang response `400 Bad Request` hoặc lỗi contract phù hợp; không trả stack trace/classpath cho client.
- Ghi nhận metric/audit an toàn để phát hiện client cũ hoặc hành vi dò subtype, nhưng không log raw payload nhạy cảm.

Unknown property và unknown subtype là hai vấn đề khác nhau. `FAIL_ON_INVALID_SUBTYPE` kiểm soát subtype không resolve được; nó không quyết định cách xử lý field lạ bên trong một subtype đã hợp lệ. Hãy quy định riêng chính sách unknown field theo contract. Với command nhạy cảm, strict schema thường dễ kiểm soát hơn việc âm thầm bỏ qua field ngoài dự kiến.

## 6. Cấu hình Jackson trong Spring Boot

Nếu ứng dụng dùng Spring Boot, nên tùy chỉnh mapper do Boot quản lý thay vì tự tạo một `ObjectMapper` mới cho từng controller. Điều này giữ lại module và cấu hình framework đang cần.

Ví dụ bật rõ hành vi từ chối subtype không hợp lệ:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonSecurityConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictSubtypeHandling() {
        return builder -> builder.featuresToEnable(
                DeserializationFeature.FAIL_ON_INVALID_SUBTYPE);
    }
}
```

Ví dụ này chỉ làm rõ chính sách unknown subtype. Nó không tự tạo allowlist cho mọi class; allowlist nằm ở metadata `Id.NAME` và registry subtype cụ thể. Kiểm tra cấu hình thực tế của ứng dụng để bảo đảm không có customizer hoặc module khác bật default typing rộng sau đó.

Không gọi `activateDefaultTyping(...)` trên mapper dùng cho request public. Nếu một định dạng nội bộ legacy thực sự cần default typing, hãy tách mapper đó khỏi HTTP input mapper, giới hạn đúng base type/subtype bằng validator hẹp, không dùng `Object` tùy tiện và có test âm tính cho mọi type ngoài danh sách. Việc có `PolymorphicTypeValidator` không tự động làm một cấu hình default typing rộng trở nên an toàn.

## 7. Không bật default typing toàn cục để giải quyết một DTO

Default typing có thể thuận tiện khi ứng dụng muốn Jackson thêm type metadata cho nhiều kiểu object mà không cần annotation trên từng base type. Nhưng khi mapper được dùng chung cho request bên ngoài, phạm vi áp dụng rộng khiến khó xác định tất cả type có thể được tạo.

Tránh các mẫu sau trên mapper đọc HTTP request:

```java
// Không dùng cho untrusted public API input.
objectMapper.activateDefaultTyping(
        permissiveValidator,
        ObjectMapper.DefaultTyping.NON_FINAL);
```

```java
// Không bật legacy default typing toàn cục.
objectMapper.enableDefaultTyping();
```

Thay vào đó:

- Đặt polymorphic annotation trên đúng base DTO cần nhiều subtype.
- Khai báo từng subtype được phép bằng logical name.
- Dùng DTO cụ thể cho field thay vì `Object` hoặc base type quá rộng.
- Tách mapper cho serialization nội bộ khỏi mapper nhận request nếu nhu cầu thật sự khác nhau.
- Kiểm tra mọi module, mix-in và custom deserializer có thể thay đổi type resolution.

Nếu hệ thống cần serialize cache/message nội bộ có type metadata, không tái sử dụng cấu hình đó cho public API chỉ vì cả hai cùng dùng Jackson.

## 8. Allowlist phải áp dụng ở mọi polymorphic boundary

Một base type được bảo vệ không có nghĩa mọi nested field đều an toàn. Ví dụ `NotificationCommand` có thể chứa `Attachment`, `DeliveryOptions` hoặc `TemplateConfig` là các base type polymorphic khác.

Hãy inventory mọi điểm polymorphic:

- Request root type.
- Nested property.
- Collection element, map value và generic wrapper.
- Event envelope và payload bên trong.
- DTO dùng chung giữa REST, message queue và file import.
- Mix-in hoặc subtype đăng ký bằng module.

Với mỗi base type, xác định rõ danh sách subtype và nơi registry được tạo. Tránh một base type chung như `BaseObject` được dùng cho nhiều domain khác nhau. Nếu một subtype chỉ hợp lệ trong một endpoint, đừng tự động cho phép nó trong mọi endpoint chỉ vì cùng kế thừa một class.

Ví dụ envelope nên có payload kiểu cụ thể thay vì `Object`:

```java
public record EventEnvelope<T>(
        String eventId,
        String eventType,
        Instant occurredAt,
        T data
) {
}
```

Ở mỗi consumer, bind `T` vào DTO event đã biết. Tránh deserialize `data` thành `Object` rồi để code phía sau tự diễn giải class hoặc map theo field do caller gửi.

## 9. Không dùng polymorphic type để quyết định quyền

Allowlist trả lời câu hỏi “payload được phép biểu diễn loại dữ liệu nào?”. Authorization trả lời “caller được phép thực hiện hành động nào trên dữ liệu nào?”. Hai quyết định này độc lập.

Ví dụ `RefundCommand` có thể là subtype hợp lệ trong contract, nhưng không có nghĩa mọi user đều được refund. Server vẫn phải:

1. Xác thực principal hoặc workload identity.
2. Kiểm tra permission chức năng như `payments:refund`.
3. Kiểm tra quyền trên payment/order cụ thể và tenant scope.
4. Kiểm tra trạng thái payment, giới hạn amount, approval và quy tắc chống duplicate.
5. Thực hiện side effect idempotently và ghi audit.

Không dùng `instanceof AdminCommand` hoặc type ID `admin` làm bằng chứng user có quyền admin. Client có thể chọn một subtype trong allowlist; server mới quyết định caller có được dùng chức năng đó hay không.

## 10. Dùng DTO riêng, không deserialize trực tiếp JPA entity

Không nên nhận entity domain/JPA làm request type. Entity thường có quan hệ lồng nhau, field nội bộ, trạng thái persistence và method không thuộc API contract. Polymorphic deserialization trên entity có thể mở rộng object graph và tạo mass assignment.

Hãy dùng command DTO:

```java
public record UpdateProfileCommand(
        @NotBlank @Size(max = 80) String displayName,
        @Email @Size(max = 254) String email
) {
}
```

Không để client gửi trực tiếp `tenantId`, `ownerId`, `role`, `isAdmin`, `approved`, `createdAt` hoặc persistence relationship nếu đó là field do server quản lý. Lấy principal/tenant từ security context và map những field được phép cập nhật một cách tường minh.

Nếu subtype có field nhạy cảm, chỉ đưa vào DTO dành cho endpoint và permission tương ứng. Không dùng một DTO đa năng chứa mọi field rồi trông chờ service bỏ qua field không phù hợp.

## 11. Validation sau khi Jackson tạo subtype

Type allowlist không thay thế Bean Validation. Sau khi Jackson resolve subtype, ứng dụng cần kiểm tra dữ liệu của subtype đó:

- Field bắt buộc, format, length và range.
- Nested object bằng `@Valid`.
- Collection size và element constraints.
- Enum/value domain được công bố.
- Cross-field rule, ví dụ `to` và `templateId` không được đồng thời xuất hiện nếu contract không cho phép.
- Business invariant và quyền trên object ở service/domain layer.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/notifications")
@RequiredArgsConstructor
class NotificationController {
    private final NotificationService notificationService;

    @PostMapping
    @PreAuthorize("hasAuthority('SCOPE_notifications:send')")
    ResponseEntity<Void> send(
            @Valid @RequestBody NotificationCommand command,
            @AuthenticationPrincipal Jwt jwt) {

        notificationService.send(jwt.getSubject(), command);
        return ResponseEntity.accepted().build();
    }
}
```

`@Valid` kích hoạt validation trên subtype thực tế. Nếu subtype chứa nested DTO, đánh dấu nested property bằng `@Valid` và đặt constraint ở phần tử phù hợp. Controller/service vẫn phải kiểm tra object/tenant permission và trạng thái nghiệp vụ trước khi gửi notification.

Ví dụ dùng `@PreAuthorize` giả định ứng dụng đã bật method security bằng `@EnableMethodSecurity`. Nếu project chỉ dùng route-level rules trong `SecurityFilterChain`, hãy đặt scope check ở filter chain và giữ object/business authorization trong service.

Lưu ý thứ tự: Spring Security filter chain có thể chặn authentication và route-level permission trước khi MVC đọc body. Method security như `@PreAuthorize` chạy quanh lời gọi method sau khi MVC đã bind tham số, vì vậy body có thể đã được deserialize trước khi method authorization thực thi. Nếu cần từ chối sớm caller thiếu scope, cấu hình route authorization ở filter chain; không dùng polymorphic deserialization có side effect.

## 12. Không để constructor, setter hoặc deserializer tạo side effect

Deserialization là bước biến dữ liệu thành object, không phải thời điểm thực hiện nghiệp vụ. Các subtype DTO nên là object dữ liệu thuần:

- Constructor chỉ gán và kiểm tra dữ liệu cục bộ.
- Setter không gửi email, gọi HTTP, đọc file hoặc ghi database.
- Custom deserializer không gọi service hoặc truy cập network.
- Không khởi tạo process, thread hoặc tài nguyên lớn từ type metadata.
- Không gọi dependency injection container hoặc reflection để tìm bean theo giá trị client gửi.

Sau khi deserialize và validate, application service mới thực hiện nghiệp vụ sau khi authentication, authorization, tenant scope và business rules đã được kiểm tra. Cách tách này giảm nguy cơ payload tạo side effect ngay trong quá trình parse.

## 13. Giới hạn parser và kích thước payload

Ngay cả khi subtype được allowlist, payload vẫn có thể quá lớn hoặc lồng quá sâu. Đặt giới hạn ở nhiều lớp:

- HTTP request body size tại gateway/container trước khi đọc hết body.
- Maximum nesting depth, string length và number length nếu Jackson version hỗ trợ `StreamReadConstraints`.
- Collection size, map entries và nested object count theo contract.
- Timeout và concurrency cho endpoint deserialize payload lớn.
- Giới hạn số subtype/field được hỗ trợ và tránh dynamic classpath scan.
- Giới hạn file/multipart trước khi parse nếu payload nằm trong file.

`@Size` và Bean Validation chạy sau một phần quá trình parse; chúng không thay thế giới hạn stream/parser. Kiểm thử với phiên bản Jackson đang chạy vì API và default constraint có thể thay đổi theo version.

## 14. Test hợp lệ và test âm tính với ObjectMapper

Unit test cần chứng minh subtype được phép parse thành đúng class và subtype ngoài allowlist bị từ chối.

```java
class NotificationCommandDeserializationTest {
    private final ObjectMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_INVALID_SUBTYPE)
            .build();

    @Test
    void acceptsRegisteredEmailSubtype() throws Exception {
        String json = """
                {
                  "kind": "email",
                  "to": "user@example.test",
                  "subject": "Ready",
                  "body": "Your invoice is ready."
                }
                """;

        NotificationCommand command = mapper.readValue(
                json, NotificationCommand.class);

        assertInstanceOf(EmailCommand.class, command);
    }

    @Test
    void rejectsUnknownSubtype() {
        String json = """
                {"kind":"admin-command","operation":"grant-all"}
                """;

        assertThrows(InvalidTypeIdException.class,
                () -> mapper.readValue(json, NotificationCommand.class));
    }

    @Test
    void doesNotResolveJavaClassNameAsLogicalType() {
        String json = """
                {"kind":"com.example.internal.AdminCommand"}
                """;

        assertThrows(InvalidTypeIdException.class,
                () -> mapper.readValue(json, NotificationCommand.class));
    }
}
```

Ví dụ giả định `NotificationCommand`, `EmailCommand` và `SmsCommand` được khai báo như phần trước và test dùng cùng Jackson version/cấu hình với ứng dụng. Nếu project có custom module hoặc mix-in, hãy inject ObjectMapper thực tế thay vì chỉ test một mapper mới mặc định.

## 15. Test qua Spring MVC và xác minh không có side effect

Unit test ObjectMapper chưa chứng minh HTTP message converter của Spring dùng cùng cấu hình. Thêm integration test qua endpoint:

```java
@WebMvcTest(NotificationController.class)
@Import(JacksonSecurityConfiguration.class)
class NotificationControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    NotificationService notificationService;

    @Test
    void unknownSubtypeIsRejectedBeforeServiceInvocation() throws Exception {
        mockMvc.perform(post("/api/notifications")
                        .with(jwt().authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_notifications:send")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"kind":"internal-admin","operation":"grant-all"}
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(notificationService);
    }
}
```

Đây là ví dụ khung; thêm import và cấu hình test phù hợp với phiên bản Spring Security/Jackson của project. Kết quả mong đợi là lỗi contract `400`, không gọi service và không có side effect. Nếu ứng dụng dùng `@ControllerAdvice`, bảo đảm exception mapping không biến lỗi subtype thành `500` hoặc trả stack trace.

Thêm test route authorization để xác minh caller thiếu scope bị chặn trước khi xử lý body. Nếu test dùng `jwt()` của Spring Security Test, nó tạo principal giả lập và không kiểm tra chữ ký JWT thực; authentication token thật cần được test ở security integration layer riêng.

## 16. Ma trận test polymorphic type

| Tình huống | Kết quả mong đợi |
|---|---|
| Logical ID hợp lệ (`email`) | Tạo đúng subtype đã đăng ký |
| Logical ID hợp lệ khác (`sms`) | Tạo đúng subtype tương ứng |
| Type ID không biết | Từ chối; không fallback sang kiểu rộng |
| Java fully-qualified class name | Từ chối vì không phải logical ID đã đăng ký |
| `@class`/type property khác contract | Không được diễn giải thành class tùy ý |
| Thiếu discriminator | Từ chối nếu contract yêu cầu subtype rõ ràng |
| Discriminator có kiểu sai | Từ chối validation/deserialization |
| Nested polymorphic type ngoài allowlist | Từ chối ở đúng nested boundary |
| Subtype đăng ký qua module/mix-in ngoài dự kiến | Test phát hiện registry mở rộng và fail |
| Field lạ trong subtype hợp lệ | Xử lý theo strict schema policy đã công bố |
| Field nhạy cảm như `tenantId` hoặc `isAdmin` | Không bind vào server-managed state |
| Caller thiếu function permission | Bị chặn; không thực hiện service action |
| Caller có permission nhưng sai object/tenant | Bị object authorization từ chối |
| Payload lớn hoặc nesting sâu | Bị giới hạn trước khi cạn tài nguyên |
| Subtype constructor/deserializer có side effect | Thiết kế/test bảo đảm không có side effect khi parse |

## 17. Khi nào cần `PolymorphicTypeValidator`?

`PolymorphicTypeValidator` được dùng khi Jackson cần quyết định type nào được phép trong một số cấu hình polymorphic/default typing. Với public JSON API, explicit `Id.NAME` và subtype registry hẹp thường dễ review hơn và không cần bật default typing toàn cục.

Nếu phải duy trì một định dạng legacy dùng class-based type metadata:

- Tách ObjectMapper legacy khỏi mapper đọc public HTTP request.
- Giới hạn base type cụ thể và chỉ cho phép subtype class chính xác đã được kiểm kê.
- Từ chối mọi class ngoài allowlist; tránh rule cho phép cả package hoặc mọi subtype.
- Không cho payload chọn class loader, module hoặc package.
- Giới hạn object graph, nesting, bytes và collection size.
- Kiểm tra mọi class được allowlist không có constructor/setter/deserialization hook nguy hiểm.
- Pin Jackson version, theo dõi advisory và có test âm tính cho type ngoài danh sách.

Không dùng `allowIfSubType("com.example." )` hoặc quy tắc package rộng như một giải pháp mặc định. Package có thể chứa class mới được thêm sau này mà chưa qua security review. Allowlist theo class cụ thể hẹp hơn, nhưng vẫn cần đánh giá từng class và base type.

## 18. Versioning và compatibility của logical type ID

Logical type ID là contract công khai. Khi đổi schema:

- Giữ ID cũ trong thời hạn tương thích nếu client vẫn gửi.
- Thêm ID mới có chủ đích; không tự động map mọi unknown type về subtype gần giống.
- Nếu cần chuyển đổi, map alias cũ sang subtype hiện hành bằng registry rõ ràng và test.
- Không tái sử dụng một ID cũ cho ý nghĩa nghiệp vụ khác.
- Ghi nhận client/version dùng type ID đã deprecated mà không log token hoặc payload nhạy cảm.
- Xóa ID cũ sau thời hạn sunset và kiểm tra traffic thực tế.

Một subtype được allowlist hôm nay không nên tự động có quyền truy cập hoặc capability mới chỉ vì implementation class được mở rộng sau này. Review thay đổi field, handler và side effect như một thay đổi API/security contract.

## 19. Checklist triển khai

- [ ] Chỉ bật polymorphic deserialization khi contract thực sự cần nhiều subtype.
- [ ] Public API dùng `JsonTypeInfo.Id.NAME` với logical type ID ổn định.
- [ ] `@JsonSubTypes` hoặc registry tương đương liệt kê rõ từng subtype hợp lệ.
- [ ] Không dùng `Id.CLASS`, `Id.MINIMAL_CLASS` hoặc default typing rộng cho untrusted request.
- [ ] Không dùng `defaultImpl` rộng để che unknown subtype.
- [ ] Giữ `FAIL_ON_INVALID_SUBTYPE` bật và map lỗi thành response an toàn.
- [ ] Review module, mix-in, custom deserializer và `registerSubtypes` có thể mở rộng registry.
- [ ] Mỗi nested polymorphic base type có allowlist riêng.
- [ ] Dùng DTO riêng, không deserialize trực tiếp JPA/domain entity hoặc `Object` tùy tiện.
- [ ] Constructor, setter và deserializer không tạo side effect hoặc gọi dependency.
- [ ] Bean Validation chạy trên subtype thực tế; nested object có `@Valid` và giới hạn kích thước.
- [ ] Authentication/route authorization, function permission, object permission và tenant scope được kiểm tra độc lập.
- [ ] HTTP body/parser limits được áp dụng trước khi parse; có giới hạn graph/depth/collection phù hợp.
- [ ] Có unit test ObjectMapper và integration test qua Spring message converter thực tế.
- [ ] Test unknown ID, class-name payload, nested type, registry drift, validation, authorization và side effect.
- [ ] Legacy default typing (nếu bắt buộc) dùng mapper tách biệt, validator hẹp và test version-specific.

## Kết luận

Jackson polymorphic deserialization chỉ nên tạo những subtype mà API chủ động công bố. Dùng `JsonTypeInfo.Id.NAME` cùng danh sách logical ID rõ ràng giúp tách contract khỏi tên class Java và tránh để payload chọn class tùy ý. Không bật default typing toàn cục cho public request; bảo vệ từng nested polymorphic boundary, dùng DTO thuần, từ chối unknown type, giới hạn parser và kiểm thử bằng đúng ObjectMapper/Spring message converter production. Sau khi deserialize, ứng dụng vẫn phải thực hiện validation, authentication, function/object authorization, tenant isolation và kiểm tra nghiệp vụ trước mọi side effect.
