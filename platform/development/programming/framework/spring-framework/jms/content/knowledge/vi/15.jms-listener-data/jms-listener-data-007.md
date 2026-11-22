# Kiểm tra payload bằng @Valid và Validator trong Spring JMS listener

## 1. Vì sao message đến broker chưa có nghĩa payload hợp lệ?

Trong Spring JMS, `@JmsListener` nhận message được gửi từ một ứng dụng, một phiên bản phần mềm khác hoặc một hệ thống tích hợp. Dù broker gửi message thành công, **nội dung không nhất thiết đúng định dạng hay hợp lệ cho nghiệp vụ**. Những tình huống thường gặp:

- JSON thiếu `orderId` hoặc chứa chuỗi rỗng.
- `quantity=0`, âm hoặc lớn hơn giới hạn hợp đồng.
- Địa chỉ giao hàng thiếu `city`, mã quốc gia sai quy tắc.
- Producer gửi schema cũ, sai kiểu dữ liệu hoặc field mới chưa được hỗ trợ.
- Message đã được broker redeliver sau lỗi nhưng handler chưa từng kiểm tra dữ liệu.
- Input hợp lệ về mặt cú pháp nhưng sai quy tắc như vượt hạn mức, đơn hàng không tồn tại hoặc trùng command ID.

**Bean Validation** (Jakarta Validation, thường dùng Hibernate Validator) cho phép khai báo những ràng buộc dữ liệu phổ biến ngay trên **DTO dùng ở biên listener**. Spring Messaging có thể áp dụng các constraint đó lên tham số payload có `@Valid`, trước khi gọi logic nghiệp vụ.

Ví dụ:

```java
@JmsListener(destination = "demo.validation.orders")
public void receive(@Payload @Valid OrderCommand command) {
    // Chỉ đến đây nếu payload đã được convert và vượt qua
    // các Bean Validation constraints đã cấu hình.
    orderService.placeOrder(command);
}
```

Đây là **mảnh method minh họa**, không phải class chạy độc lập: cần DTO có constraints, `MessageConverter` nếu body là JSON, Bean Validation provider và **Validator được liên kết với listener method adapter**.

### 1.1. Pipeline xử lý

```text
JMS Broker
    |
    v
MessageListenerContainer (Consumer/Session)
    |
    v
JMS Message (TextMessage / BytesMessage / ...)
    |
    +--> JMS MessageConverter: body -> Java DTO
    |         |
    |         +--> lỗi JSON/type/converter -> conversion failure
    |
    v
Spring Messaging argument resolver: @Payload
    |
    v
Validator: @Valid / @Validated và constraints trên DTO
    |
    +--> có violations -> MethodArgumentNotValidException
    |                      handler nghiệp vụ chưa được gọi
    |
    v
@JmsListener method
    |
    v
Business validation / authorization / transaction / side effects
    |
    v
Container quyết định ACK/commit hoặc rollback theo cấu hình
```

**Điểm mấu chốt:** `@Valid` **không tự giải mã JSON**, `MessageConverter` **không tự xác nhận nghiệp vụ**, và JMS broker **không tự áp dụng Bean Validation trên payload**. Cần cả ba tầng: chuyển đổi, kiểm tra cấu trúc và kiểm tra nghiệp vụ.

## 2. Các thành phần và import cần nhớ

| Thành phần | Package / vai trò | Ghi nhớ |
| --- | --- | --- |
| `@JmsListener` | `org.springframework.jms.annotation.JmsListener` | Đánh dấu phương thức nhận thông điệp |
| `@Payload` | `org.springframework.messaging.handler.annotation.Payload` | Xác định tham số nhận body đã convert |
| `@Valid` | `jakarta.validation.Valid` | Kích hoạt Bean Validation trên đối tượng payload nếu có Validator |
| `@Validated` | `org.springframework.validation.annotation.Validated` | Biến thể Spring, có thể chọn validation groups |
| `@NotNull` | `jakarta.validation.constraints.NotNull` | Giá trị không được null |
| `@NotBlank` | `jakarta.validation.constraints.NotBlank` | `CharSequence` không null và chứa ký tự không phải whitespace |
| `@Size` | `jakarta.validation.constraints.Size` | Độ dài/size collection, string, array, map |
| `@Min` / `@Max` | `jakarta.validation.constraints.Min/Max` | Giới hạn các giá trị số nguyên hỗ trợ |
| `@Positive` | `jakarta.validation.constraints.Positive` | Số dương, không tính 0 |
| `@Pattern` | `jakarta.validation.constraints.Pattern` | Kiểm tra chuỗi theo regex |
| `jakarta.validation.Validator` | Jakarta Validation API | `validate(object)` trả `Set<ConstraintViolation<T>>` |
| `org.springframework.validation.Validator` | Spring validation API | `supports(Class<?>)`, `validate(Object, Errors)` |
| `LocalValidatorFactoryBean` | `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Cầu nối triển khai cả Spring Validator và Jakarta Validator |
| `DefaultMessageHandlerMethodFactory` | `org.springframework.messaging.handler.annotation.support` | Cấu hình argument resolution và Validator cho listener method |
| `JmsListenerConfigurer` | `org.springframework.jms.annotation` | Tùy chỉnh listener endpoint registrar |
| `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` | Đặt `MessageHandlerMethodFactory` được dùng cho endpoints |

**Quan trọng với Spring Boot 3+/Spring Framework 6+:** dùng package `jakarta.validation.*` và `jakarta.jms.*`; không trộn `javax.validation.*` / `javax.jms.*` từ thư viện cũ. Các annotation constraint chỉ là API; cần **Bean Validation provider** (thường Hibernate Validator, qua `spring-boot-starter-validation`) để thực thi.

### 2.1. `@Valid` khác `@NotBlank`

- `@Valid` là **dấu hiệu yêu cầu validate đối tượng**, không trực tiếp định nghĩa một constraint.
- `@NotBlank`, `@NotNull`, `@Min`, `@Size`, `@Pattern` là **constraint cụ thể trên field/record component/property**.
- Đặt `@Valid` mà DTO không có constraint sẽ không tự suy ra “sai nghiệp vụ”.
- Đặt constraint trên DTO nhưng **không đăng ký Validator cho handler factory** có thể khiến validation ở biên listener không diễn ra theo cấu hình mong muốn.
- `@Valid` trên field kiểu object lồng nhau giúp **cascade** validation đến nested DTO khi thuộc tính đó không null.

## 3. Thiết kế DTO đầu vào có constraints rõ ràng

Giả sử queue nhận lệnh đặt hàng:

```json
{
  "orderId": "order-42",
  "quantity": 2,
  "shipping": {
    "city": "Ha Noi",
    "countryCode": "VN"
  }
}
```

Schema hợp đồng của bài học:

| Field | Constraint | Ý nghĩa |
| --- | --- | --- |
| `orderId` | `@NotBlank`, `@Size(max=64)` | Không rỗng; tránh khóa dài bất thường |
| `quantity` | `@NotNull`, `@Min(1)`, `@Max(500)` | Số lượng trong dải 1–500 |
| `shipping` | `@NotNull`, `@Valid` | Phải có địa chỉ và validate nested fields |
| `shipping.city` | `@NotBlank`, `@Size(max=100)` | Thành phố có tên |
| `shipping.countryCode` | `@NotBlank`, `@Pattern("[A-Z]{2}")` | Hai chữ cái viết hoa theo hợp đồng demo |

Java 17 record:

```java
package com.example.jms;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderCommand(
        @NotBlank @Size(max = 64) String orderId,
        @NotNull @Min(1) @Max(500) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {
    public record ShippingAddress(
            @NotBlank @Size(max = 100) String city,
            @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
    ) {}
}
```

### 3.1. Vì sao quantity dùng `Integer`, không dùng `int`?

Khi JSON thiếu một trường, converter có thể gán giá trị mặc định cho primitive; với `int`, giá trị `0` dễ bị nhầm là “có cung cấp số 0” thay vì “trường không tồn tại”. `Integer` cho phép thấy null và `@NotNull` báo vi phạm. Dùng `@Min(1)` chặn 0 và số âm; `@Max(500)` chặn số quá lớn.

**Lưu ý:** hai khái niệm *trường absent* và *trường có explicit null* có thể đều thành `null` khi Jackson map vào record. Nếu hợp đồng phải phân biệt chặt chẽ hai trường hợp, hãy dùng JSON Schema validation/`JsonNode` hay custom deserializer ở lớp protocol; `@NotNull` một mình không phân biệt hai trường hợp đó.

### 3.2. Vì sao cần `@NotNull @Valid ShippingAddress shipping`?

`@Valid` trên nested field **không** có nghĩa field bắt buộc phải tồn tại. Bean Validation **không cascade vào null**. Vì vậy:

```java
@Valid ShippingAddress shipping
```

khi `shipping == null` thường không tạo lỗi nested validation. Để yêu cầu có địa chỉ, cần:

```java
@NotNull @Valid ShippingAddress shipping
```

Khi `shipping` có mặt, `@Valid` yêu cầu tiếp tục kiểm tra `city` và `countryCode`. Nếu quên nested `@Valid`, nhiều provider sẽ không kiểm tra constraints bên trong object lồng nhau khi validate root DTO.

### 3.3. `@NotNull`, `@NotEmpty`, `@NotBlank` không tương đương

| Giá trị | `@NotNull` | `@NotEmpty` với String | `@NotBlank` với String |
| --- | --- | --- | --- |
| `null` | Lỗi | Lỗi | Lỗi |
| `""` | Hợp lệ | Lỗi | Lỗi |
| `"   "` | Hợp lệ | Hợp lệ | Lỗi |
| `"order-42"` | Hợp lệ | Hợp lệ | Hợp lệ |

`@NotBlank` hợp với mã đơn hàng/chuỗi bắt buộc. `@NotNull` phù hợp cho số lượng hoặc object. `@NotEmpty` dùng cho collection/map/array/chuỗi cần không rỗng nhưng không tự coi whitespace là blank. Tùy version/provider, những constraints áp lên **sai Java type** có thể gây `UnexpectedTypeException`, không phải một violation thông thường.

## 4. @Payload @Valid hoạt động ở đâu trong Spring JMS?

Method:

```java
@JmsListener(destination = "orders.commands")
public void receive(@Payload @Valid OrderCommand command) {
    // business logic
}
```

Spring JMS tạo một listener endpoint và container, sau đó sử dụng listener method adapter. Bên trong quá trình **argument resolution**, `PayloadMethodArgumentResolver` nhận Java payload đã chuyển đổi, kiểm tra có annotation `@Valid`/`@Validated`, rồi gọi Validator phù hợp.

Nếu có violations, Spring Messaging thường ném:

```text
org.springframework.messaging.handler.annotation.support
    .MethodArgumentNotValidException
```

Lỗi có thể được bọc bởi listener adapter/container thành exception bên ngoài; khi phân loại lỗi nên kiểm tra **root cause** và framework version thay vì chỉ so đúng class ở tầng ngoài cùng.

### 4.1. Không được nhầm với validation trong Spring MVC

Trong MVC, nhiều ứng dụng đã quen controller:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderCommand command) { ... }
```

Đó là cơ chế nhận **HTTP request**. `@JmsListener` không đi qua MVC argument resolvers, không dùng `@RequestBody` và không tự trả HTTP 400. Validation JMS cần hạ tầng listener method adapter và cách xử lý lỗi riêng.

Đặc biệt, việc Spring MVC/Boot có global Validator cho web **không phải bằng chứng** listener adapter đang dùng đúng Validator. Spring Framework cho phép cấu hình tường minh `DefaultMessageHandlerMethodFactory#setValidator(...)`, được giới thiệu ở phần tiếp theo.

### 4.2. Các lỗi xảy ra ở những tầng khác nhau

| Lớp | Ví dụ lỗi | Handler nghiệp vụ được gọi? |
| --- | --- | --- |
| JMS transport/broker | Queue không tồn tại, thiếu quyền, mất kết nối | Không |
| JMS/JSON conversion | JSON sai cú pháp, `_type` không hợp lệ, kiểu field không convert được | Không |
| Argument resolution | Không xác định payload/missing required content | Không |
| Bean Validation | `orderId=""`, `quantity=0`, `shipping.city=""` | Không khi Validator đã cấu hình |
| Business rule | `orderId` đã được xử lý, khách hàng bị khóa, số lượng vượt tồn kho hiện tại | Có thể được gọi, rồi code nghiệp vụ từ chối |
| Database/integration | DB timeout, downstream unavailable | Có thể đã vào handler, nhưng lỗi về sau |

**Không coi JSON parse thành công là Bean Validation thành công; và không coi Bean Validation thành công là quyết định nghiệp vụ thành công.**

## 5. Nối Validator vào JMS listener method adapter

Cách cấu hình minh bạch, theo Spring Framework reference:

1. Có Bean Validation provider trên classpath.
2. Có bean `org.springframework.validation.Validator` (ví dụ `LocalValidatorFactoryBean`).
3. Tạo `DefaultMessageHandlerMethodFactory`, gọi `setValidator(validator)`.
4. Cấu hình `JmsListenerConfigurer` dùng factory đó qua `JmsListenerEndpointRegistrar`.

Ví dụ **mảnh cấu hình minh họa**:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@Configuration
public class JmsValidationConfig implements JmsListenerConfigurer {
    private final Validator validator;

    public JmsValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        DefaultMessageHandlerMethodFactory methodFactory =
                new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

**Lưu ý quan trọng về lifecycle:** đoạn trên chỉ minh họa ý tưởng; `DefaultMessageHandlerMethodFactory` thực tế thực hiện `InitializingBean`, nên nên **đăng ký nó làm Spring bean để framework gọi `afterPropertiesSet()`**, hoặc tự khởi tạo đúng lifecycle trước khi dùng. Project hoàn chỉnh ở phần 8 sử dụng một bean `DefaultMessageHandlerMethodFactory` riêng, để tránh lỡ bỏ qua bước setup argument resolvers.

### 5.1. Hai interface Validator

**Jakarta Validation `jakarta.validation.Validator`:**

```java
Set<ConstraintViolation<OrderCommand>> violations =
        jakartaValidator.validate(order);
```

Trả về tập violations để code chủ động quyết định xử lý. Hợp khi validation thủ công ngoài listener argument resolver, cần xuất danh sách lỗi đã được lọc.

**Spring `org.springframework.validation.Validator`:**

```java
@Override
public boolean supports(Class<?> candidate) { ... }

@Override
public void validate(Object target, Errors errors) { ... }
```

Đây là API mà `DefaultMessageHandlerMethodFactory#setValidator(...)` yêu cầu. `LocalValidatorFactoryBean` thực hiện cả hai giao diện, kết nối constraints của Jakarta với API lỗi (`Errors`, `BindingResult`) của Spring.

**Không inject nhầm** `jakarta.validation.Validator` rồi truyền nó trực tiếp vào method chỉ nhận `org.springframework.validation.Validator`: chúng không là cùng một interface. Inject `LocalValidatorFactoryBean` hoặc bean Spring Validator thích hợp.

### 5.2. Tự tạo Spring Validator cho quy tắc chuyên biệt

Một custom Validator có thể kiểm tra rules không sẵn có trong Jakarta constraints:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

final class OrderPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderCommand.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderCommand command = (OrderCommand) target;
        if (command.quantity() != null && command.quantity() > 100) {
            errors.rejectValue(
                    "quantity", "order.quantity.tooLargeForChannel",
                    "Quantity exceeds channel limit");
        }
    }
}
```

Đây là snippet class minh họa với `OrderCommand` ở cùng package. Nếu thay thế validator handler bằng **chỉ** custom class trên, các constraint `@NotBlank`, `@Min`, `@Valid` nested **không tự được thực thi** bởi nó. Muốn kết hợp cả Jakarta constraints và custom logic, cần một validator tổng hợp/delegate đúng cách, hoặc đặt business rule trong service sau Bean Validation.

Với quy tắc động phụ thuộc database, tồn kho, hạn mức khách hàng hay quyền, đặt ở **business service** thường rõ hơn vì validation ở biên nên deterministic, không chứa hàng loạt truy vấn mạng/DB.

## 6. @Validated và validation groups

`@Valid` không chọn groups; thông thường kiểm tra nhóm `Default`. Nếu một DTO dùng chung cho hai ngữ cảnh có các ràng buộc khác nhau, Spring hỗ trợ `@Validated(Group.class)` với custom validation groups.

Ví dụ (mảnh code minh họa):

```java
interface CreateOrder {}
interface UpdateOrder {}

record OrderPatch(
        @NotNull(groups = UpdateOrder.class) String orderId,
        @NotNull(groups = CreateOrder.class) Integer quantity
) {}
```

Một method listener có thể yêu cầu nhóm:

```java
@JmsListener(destination = "orders.create")
public void create(@Payload @Validated(CreateOrder.class)
                   OrderPatch patch) {
    // ...
}
```

Điều kiện: Validator dùng trong `DefaultMessageHandlerMethodFactory` hiểu validation hints/groups (ví dụ `LocalValidatorFactoryBean`). Khi có groups, những constraint chỉ thuộc `Default` sẽ **không tự được thực thi** trừ khi bạn chọn `Default` hay cấu hình group sequence; phải thiết kế groups cẩn thận.

**Không phải giải pháp tốt để dùng một DTO cho mọi loại command.** Nếu `CreateOrder` và `UpdateOrder` có schema khác nhau rõ rệt, hai DTO contract riêng thường đơn giản hơn nhiều validation groups chồng chéo.

## 7. Nested validation, collections và giới hạn

Với object lồng nhau, `@Valid` kích hoạt validation cascade:

```java
record BatchCommand(
        @NotNull String batchId,
        @NotEmpty java.util.List<@Valid OrderCommand> orders
) {}
```

Đây là snippet minh họa; cần imports của Bean Validation annotations. `@NotEmpty` kiểm tra list không rỗng; `@Valid` ở type argument yêu cầu validate từng `OrderCommand` trong list theo Bean Validation container element support.

Tuy nhiên validator không tự giới hạn kích thước payload JSON thô hay nesting depth trước khi deserialize. Nếu một message chứa mười triệu phần tử, deserialize có thể đã làm cạn bộ nhớ **trước** khi `@Size(max=...)` chạy. Với dữ liệu không tin cậy, cần:

- Giới hạn message size ở broker/producer và tầng deserializer.
- Dùng `@Size(max=...)` cho collection đã parse, nhưng không coi đó là lớp bảo vệ duy nhất.
- Giới hạn string length, count, numeric range, nested depth.
- Tránh deserialize class tùy ý từ `_type` do sender kiểm soát; dùng stable type IDs và type mappings/trusted packages.
- Theo dõi thời gian decode, memory và errors theo event type/schema version.

### 7.1. Collection có thể chứa null

`List<@Valid OrderCommand>` không tự cấm phần tử null. Nếu không cho phép null elements, có thể đặt:

```java
List<@NotNull @Valid OrderCommand> orders
```

và bật Bean Validation provider hỗ trợ container element constraints. Với nested DTO, `@Valid` không thay thế `@NotNull`, tương tự `shipping` ở ví dụ đầu bài.

## 8. Project runnable: Spring Boot 3.5.7 + Java 17+ + Artemis + Bean Validation

Demo này cho thấy:

- Producer dùng `JmsTemplate.convertAndSend` gửi `OrderCommand` dưới dạng JSON trong `TextMessage`.
- Spring `MappingJackson2MessageConverter` chuyển JSON thành `OrderCommand` ở consumer.
- `JmsListenerConfigurer` đăng ký một **Spring `Validator` thực sự** với `DefaultMessageHandlerMethodFactory`.
- `@JmsListener` gọi `receive(@Payload @Valid OrderCommand command)`.
- Handler đánh dấu một payload hợp lệ vào tracker; runner chờ tối đa 10 giây và in một dòng ổn định.
- Test riêng không cần broker minh họa payload sai bị chặn **trước khi Java handler method được gọi**.

### 8.1. Yêu cầu môi trường

- JDK 17+ và Maven 3.9+.
- Docker để chạy Apache ActiveMQ Artemis tại localhost port `61616`.
- Có thể tải dependencies Maven và Docker image.
- Không có ứng dụng khác tiêu thụ queue `demo.validation.orders` trong cùng broker lab.

Credentials dưới đây chỉ cho **thực hành local**; tuyệt đối không dùng ở production.

### 8.2. Khởi chạy Artemis

```bash
docker run --rm -d --name jms-validation-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-validation-broker
```

Đợi broker sẵn sàng. Broker demo thường có auto-create queue theo cấu hình image; nếu môi trường không auto-create, cần provision queue/address và cấp quyền. Project chạy trên host sẽ kết nối `tcp://localhost:61616`; nếu app chạy trong container khác, cần dùng hostname/network phù hợp.

### 8.3. Cấu trúc project

```text
jms-payload-validation/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/jms/
    │       ├── ValidationApplication.java
    │       ├── OrderCommand.java
    │       ├── ValidatedOrderListener.java
    │       ├── ReceiptTracker.java
    │       └── JmsListenerValidationConfigurer.java
    └── test/
        └── java/com/example/jms/
            └── ValidationResolutionTest.java
```

### 8.4. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-payload-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Các starter có vai trò riêng:

- Artemis starter: JMS API, Spring JMS, Artemis client/connection.
- JSON starter: Jackson và `ObjectMapper`.
- Validation starter: Jakarta Validation API và Hibernate Validator triển khai constraints.
- Test starter: JUnit 5, Spring Test và các thư viện test phổ biến.

Không tự gộp tất cả logic vào `@Valid`: converter chỉ giải mã; Validator thực thi constraints; service tự quyết định business semantics.

### 8.5. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

Đây là cấu hình lab không có TLS và dùng mật khẩu demo. Khi triển khai thật, dùng biến môi trường hoặc secret manager, TLS, ACL theo destination, không commit credential production vào source.

### 8.6. `OrderCommand.java` — DTO đã khai báo constraints

```java
package com.example.jms;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderCommand(
        @NotBlank @Size(max = 64) String orderId,
        @NotNull @Min(1) @Max(500) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {
    public record ShippingAddress(
            @NotBlank @Size(max = 100) String city,
            @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
    ) {}
}
```

Đây là **transport DTO**, không phải JPA entity. Nested `@Valid` quan trọng: nó yêu cầu kiểm tra cả `city` và `countryCode`.

### 8.7. `ValidationApplication.java` — cấu hình Jackson JMS converter và runner

```java
package com.example.jms;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@SpringBootApplication
@EnableJms
public class ValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }

    @Bean
    MessageConverter jsonJmsMessageConverter(ObjectMapper objectMapper) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setObjectMapper(objectMapper);
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(
                "order.command.v1", OrderCommand.class));
        return converter;
    }

    @Bean
    DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            Validator validator) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();
        factory.setValidator(validator);
        return factory;
    }

    @Bean
    CommandLineRunner runDemo(JmsTemplate template,
                              ReceiptTracker tracker) {
        return args -> {
            OrderCommand command = new OrderCommand(
                    "order-42",
                    2,
                    new OrderCommand.ShippingAddress("Ha Noi", "VN")
            );

            template.convertAndSend("demo.validation.orders", command);

            if (!tracker.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for a validated order");
            }

            System.out.println("Accepted payload: " + tracker.result());
        };
    }
}
```

**Giải thích:**

1. `MappingJackson2MessageConverter` biến `OrderCommand` thành JSON `TextMessage` và ngược lại.
2. `_type` là một **JMS property** chứa stable alias `order.command.v1`; mapping giải quyết từ alias sang `OrderCommand.class`. Nếu không map type ID, converter có thể phát raw Java class name, khiến wire format phụ thuộc vào class nội bộ.
3. Spring Boot gắn bean `MessageConverter` vào `JmsTemplate` và default JMS listener container factory trong luồng auto-config thông thường.
4. Bean `DefaultMessageHandlerMethodFactory` được Spring khởi tạo (`InitializingBean`) rồi được `JmsListenerConfigurer` bên dưới cung cấp cho registrar. `setValidator(validator)` kích hoạt validation của payload argument resolver.
5. Runner chỉ gửi một message **hợp lệ**, để tránh demo bị poison-message redelivery loop. Nó chờ tracker tối đa 10 giây rồi in output.
6. Không có lời gọi tới DB; đây là ví dụ kiểm tra dữ liệu ở listener boundary, không phải xử lý đơn hàng production.

### 8.8. `JmsListenerValidationConfigurer.java` — liên kết handler method factory

```java
package com.example.jms;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;

@Configuration
public class JmsListenerValidationConfigurer
        implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public JmsListenerValidationConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

Điểm cần lưu ý: đây là **factory để resolve tham số phương thức `@JmsListener`**, **khác với** `DefaultJmsListenerContainerFactory` quản lý connection/session/ack/retry. Nếu chỉ cấu hình `MessageConverter` mà không cung cấp `Validator` cho method factory trong trường hợp cần validate, `@Valid` có thể không chặn dữ liệu sai như kỳ vọng.

### 8.9. `ValidatedOrderListener.java` — kiểm tra trước khi xử lý

```java
package com.example.jms;

import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class ValidatedOrderListener {

    private final ReceiptTracker tracker;

    public ValidatedOrderListener(ReceiptTracker tracker) {
        this.tracker = tracker;
    }

    @JmsListener(
            id = "validated-orders",
            destination = "demo.validation.orders"
    )
    public void accept(@Payload @Valid OrderCommand command) {
        // Chỉ chạy nếu argument đã được convert và Bean Validation pass.
        tracker.accepted(command.orderId(), command.quantity());
    }
}
```

Nếu payload có `quantity=0`, Bean Validation tạo violation `quantity`, argument resolver ném lỗi trước khi gọi `accept` (khi factory/validator được cấu hình đúng). Nếu JSON sai cú pháp, lỗi chuyển đổi sẽ xảy ra **sớm hơn** và không được tính là một violation từ `@Min`.

### 8.10. `ReceiptTracker.java` — giữ kết quả demo thread-safe

```java
package com.example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public final class ReceiptTracker {

    private final AtomicReference<String> result =
            new AtomicReference<>();
    private final CountDownLatch latch = new CountDownLatch(1);

    public void accepted(String orderId, int quantity) {
        result.set(orderId + " x " + quantity);
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String result() {
        return result.get();
    }
}
```

Dùng `AtomicReference` và `CountDownLatch` để thread listener công bố kết quả cho thread runner an toàn. Demo có một message. Với hệ thống thực, không dùng một latch duy nhất cho mọi request và không dùng memory tracker thay cho DB/outbox.

### 8.11. Chạy và stdout kỳ vọng

Từ thư mục project có `pom.xml`:

```bash
mvn spring-boot:run
```

Khi Artemis sẵn sàng, queue đã được tạo và listener nhận message hợp lệ trước 10 giây, chương trình in dòng nghiệp vụ:

```text
Accepted payload: order-42 x 2
```

Có log khởi động Spring/Artemis khác trên stdout. Vì runner đợi `CountDownLatch`, dòng trên chỉ xuất hiện sau khi listener đánh dấu message hợp lệ. Không phụ thuộc vào thứ tự lập lịch của listener thread.

Dừng broker sau khi thực hành:

```bash
docker stop jms-validation-broker
```

**Giới hạn của demo:** chỉ gửi valid payload, không có JDBC, DLQ/retry policy, TLS, secret manager, metrics production hoặc idempotent database handler. Phần tiếp theo cung cấp unit test cho invalid payload mà không phát poison message vào broker.

## 9. Unit test: chứng minh cả constraints và @Valid ở argument resolver

Một test không cần broker có thể kiểm tra **hai tầng**:

1. Jakarta Validator phát hiện đủ các constraint violations, kể cả nested `shipping`.
2. `DefaultMessageHandlerMethodFactory` dùng Validator đó khiến `@Payload @Valid` **chặn việc gọi method** cho payload không hợp lệ.

Điều này chặt chẽ hơn chỉ gọi `validator.validate(dto)` và khẳng định nhầm rằng Spring đã wire Validator vào listener.

### 9.1. `src/test/java/com/example/jms/ValidationResolutionTest.java`

```java
package com.example.jms;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.messaging.handler.annotation.support
        .MethodArgumentNotValidException;
import org.springframework.messaging.handler.invocation.InvocableHandlerMethod;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ValidationResolutionTest {

    @Test
    void invalidNestedPayloadIsRejectedBeforeHandlerRuns()
            throws Exception {
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        try {
            OrderCommand invalid = new OrderCommand(
                    "",
                    0,
                    new OrderCommand.ShippingAddress("", "vn")
            );

            Set<String> invalidPaths = validator.validate(invalid)
                    .stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of(
                    "orderId",
                    "quantity",
                    "shipping.city",
                    "shipping.countryCode"
            ), invalidPaths);

            DefaultMessageHandlerMethodFactory factory =
                    new DefaultMessageHandlerMethodFactory();
            factory.setValidator(validator);
            factory.afterPropertiesSet();

            ReceiptTracker tracker = new ReceiptTracker();
            ValidatedOrderListener handler =
                    new ValidatedOrderListener(tracker);

            Method method = ValidatedOrderListener.class
                    .getMethod("accept", OrderCommand.class);
            InvocableHandlerMethod invocable =
                    factory.createInvocableHandlerMethod(handler, method);

            var message = MessageBuilder.withPayload(invalid).build();

            assertThrows(
                    MethodArgumentNotValidException.class,
                    () -> invocable.invoke(message)
            );
            assertNull(tracker.result());
        } finally {
            validator.destroy();
        }
    }
}
```

Lệnh chạy:

```bash
mvn test
```

Kết quả kỳ vọng: test **pass** khi Hibernate Validator/JUnit/Spring dependencies hiện diện và mã biên dịch. Bộ field vi phạm gồm đúng bốn đường dẫn:

```text
orderId
quantity
shipping.city
shipping.countryCode
```

`Set` **không có thứ tự**, nên test so hai sets, không assert thứ tự error messages. Dòng `tracker.result()==null` cho thấy handler không được gọi trong đường đi qua argument resolver của bài test.

**Ranh giới kiểm chứng:** test không khởi tạo JMS listener container và không kết nối Artemis. Nó chứng minh config của method resolver và constraints cho một DTO; integration test với broker cần được thêm nếu phải xác nhận JMS conversion, transaction/ack/rollback và DLQ đúng như production.

### 9.2. Bài kiểm tra mở rộng

Người học có thể viết thêm:

- `OrderCommand("order-42", 2, ShippingAddress("Ha Noi", "VN"))` → violations rỗng.
- `OrderCommand(null, 2, ...)` → `orderId` lỗi.
- `OrderCommand("order-42", null, ...)` → `quantity` lỗi `@NotNull`.
- `OrderCommand("order-42", 2, null)` → `shipping` lỗi `@NotNull`.
- `OrderCommand("order-42", 501, ...)` → `quantity` lỗi `@Max`.
- `countryCode="vn"` → `shipping.countryCode` lỗi pattern.
- JSON `quantity:"two"` → lỗi **deserialization/conversion**, trước khi Bean Validation.
- `_type` không nằm trong allowed type mappings → lỗi conversion/type resolution.

Không phụ thuộc vào **thứ tự lỗi** hay thông điệp tiếng Anh cố định vì provider/locale có thể thay đổi.

## 10. Kiểm tra thủ công bằng Validator khi không dùng @Payload @Valid

Không phải mọi consumer đều dùng annotation-driven argument resolution. Ví dụ một handler raw `jakarta.jms.TextMessage` tự parse JSON, hoặc logic nhận từ một hệ thống event khác, có thể cần gọi Jakarta Validator trực tiếp:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

// Mảnh code trong một service đã được inject Validator:
Set<ConstraintViolation<OrderCommand>> violations =
        jakartaValidator.validate(command);

if (!violations.isEmpty()) {
    // Ghi log đã loại dữ liệu nhạy cảm; quyết định reject/quarantine.
    throw new IllegalArgumentException(
            "Invalid command fields: " + violations.size()
    );
}
```

Với validation thủ công, **code của bạn** phải tự quyết định cách báo lỗi, mapping paths, retry/DLQ; framework không tự suy ra quy tắc vận hành.

### 10.1. Không để validate thủ công thành việc làm lặp vô ích

Nếu đã cấu hình đúng `@Payload @Valid`, tránh gọi lại toàn bộ `validator.validate(command)` ngay dòng đầu của listener chỉ để có cùng set lỗi. Chỉ gọi thêm khi:

- Cần groups khác dựa trên eventType/version.
- Cần validate một object trung gian khác sau mapping.
- Cần kiểm tra cross-field rule không được khai báo thành constraint.
- Cần xử lý dữ liệu raw/đường đi ngoài `@JmsListener`.

Đối với business validation có truy vấn DB, tách service rõ để dễ transaction/retry và unit test.

## 11. Validation failure sẽ khiến broker làm gì?

**Đây là phần thường bị hiểu sai nhất.** Validation fail tạo exception ở listener method adapter, nhưng việc broker **ACK, rollback, redeliver hay DLQ** phụ thuộc container, session/transaction, provider và broker policy; `@Valid` **không có nghĩa tự đưa message vào DLQ**.

### 11.1. Khi listener dùng transacted JMS session

Với `DefaultMessageListenerContainer` hoặc factory cấu hình `sessionTransacted=true`, nếu exception đi tới container thì một lần nhận thường bị rollback; broker có thể **redeliver message** theo redelivery policy.

```text
Receive invalid payload
      |
      v
Conversion / @Valid fails
      |
      v
Container sees exception
      |
      +--> rollback transacted Session
      |
      +--> broker redelivery policy
               |
               +--> retry bounded -> vẫn lỗi -> DLQ/quarantine
               +--> retry không giới hạn -> poison message loop
```

**`@Valid` không làm message biến mất an toàn.** Một message có `quantity=0` không tự sửa được chỉ nhờ gửi lại sau 10 ms. Nếu cứ rollback mãi không có max-delivery-attempts/DLQ policy, có thể tạo vòng lặp, làm tắc queue hoặc tiêu tốn CPU/log.

Nên phân loại lỗi **permanent** (malformed JSON, schema không hỗ trợ, constraint violation không thể tự hồi phục) và lỗi **transient** (broker/DB/network tạm thời). Thiết kế retry, dead-letter address/queue, alert và replay tool có kiểm soát.

### 11.2. AUTO_ACKNOWLEDGE không phải bảo đảm “lỗi thì luôn retry”

Với JMS `AUTO_ACKNOWLEDGE`, acknowledgement phụ thuộc loại container/đường đi nhận và thời điểm provider xác nhận. Không dựa vào giả định rằng mọi exception khi parse/validate sẽ khiến message quay lại queue. Spring Framework khuyến nghị transacted session khi cần độ tin cậy. Trong Spring Boot, default factory có thể bật `sessionTransacted` theo auto-config; nếu thay bằng custom factory, phải kiểm tra cấu hình **thực tế**.

Ví dụ cấu hình một factory dành cho reliable listener:

```java
// Mảnh code tùy chọn, không thuộc project demo ở phần 8.
@Bean("validatedTransactedFactory")
DefaultJmsListenerContainerFactory validatedFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory, ConnectionFactoryUnwrapper.unwrapCaching(
                    connectionFactory));
    factory.setSessionTransacted(true);
    return factory;
}
```

Đoạn trên cần imports từ `jakarta.jms.ConnectionFactory`, Spring JMS và Spring Boot JMS configurer/unwrapper, cũng như bean context phù hợp. Nếu dùng tên `validatedTransactedFactory`, set `containerFactory="validatedTransactedFactory"` trên `@JmsListener` tương ứng.

### 11.3. Cách xử lý invalid payload trong production

Lựa chọn thường gặp:

- **Từ chối có kiểm soát:** ném lỗi được phân loại để broker chuyển vào DLQ sau số lần delivery giới hạn.
- **Quarantine riêng:** chuyển message sang destination lỗi kèm metadata error code/schema version và ACK message gốc **theo một transaction nhất quán**.
- **Lưu audit lỗi, không log PII:** ghi eventId/JMSMessageID/constraint path, không lộ toàn body hay stacktrace có secrets.
- **Replay sau sửa:** chỉ replay message khi đã sửa upstream payload/schema, đúng version và có idempotency.
- **Alert theo tỷ lệ:** đột biến `MethodArgumentNotValidException` có thể là producer mới deploy không tương thích.

Không chọn `@JmsListener` method **bắt rồi nuốt exception** khi validation thực ra xảy ra **trước khi method được gọi**. Để can thiệp loại lỗi này, cần cấu hình container `ErrorHandler`, error channel/interceptor hoặc cơ chế broker DLQ thích hợp, tùy công nghệ. Không mong một `try/catch` *bên trong method* bắt được exception của argument resolver trước khi method chạy.

## 12. @Valid chưa đủ cho schema và nghiệp vụ

### 12.1. Kiểm tra contract/schema

`@Valid` trên DTO có thể xác thực nhiều quy tắc field, nhưng không nhất thiết phân biệt:

- Field bị viết sai tên nếu Jackson bỏ qua unknown properties.
- JSON có extra property trái hợp đồng nhưng object vẫn parse được.
- Producer `schemaVersion=2` gửi tới consumer v1 mà converter chỉ bỏ qua field mới.
- Content-Type không đúng, thiếu `_type` hoặc type-id mạo danh.
- Thiếu `JMSCorrelationID`, `eventId`, `schemaVersion` là header/property ngoài DTO.
- Giới hạn JSON nesting/body size trước khi deserialization.

Cần thêm schema validation, allowed type mappings, contract version checks, broker ACL, giới hạn message size và kiểm tra header. DTO chỉ chứa những field public cần thiết; không deserialize trực tiếp JPA entity hoặc class tùy ý từ `_type`.

### 12.2. Kiểm tra nghiệp vụ cần transaction/idempotency

Giả sử `quantity=2` và `orderId="order-42"` hợp lệ về mặt Bean Validation, nhưng order đã được xử lý hoặc tồn kho chỉ còn 1. Đó là business validation: nên nằm ở service có quyền truy cập kho dữ liệu, transaction boundary và idempotency policy.

```text
DTO constraints pass
       |
       v
BusinessService:
  verify idempotency/businessCommandId
  verify current inventory/state
  update database transaction
  publish result/outbox if required
```

Không thể biến `@Min(1)` thành kiểm tra tồn kho thực tế. Nếu fail vì business state không đổi bằng retry, cần reject; nếu fail tạm thời vì DB outage, cần retry có giới hạn. Chỉ dùng `@Valid` không bảo đảm exactly-once processing.

### 12.3. Cross-field constraints

Một số quy tắc phụ thuộc **nhiều field** (ví dụ `deliveryDate >= orderDate`, hoặc `currency` phù hợp `amount`). Có thể tạo custom Jakarta Bean Validation annotation/`ConstraintValidator` cho class-level constraint. Khi validation group và metadata phức tạp, cần ghi code error stable và test từng nhánh.

Đừng lạm dụng validator như một workflow engine: custom constraint có side effect (ghi DB/gửi HTTP) dễ gây retry bất ngờ vì Bean Validation có thể được gọi nhiều lần từ nhiều nơi.

## 13. Thread safety, performance và bảo mật

### 13.1. Validator và listener concurrency

`@JmsListener` thường chạy trong container có concurrency. Một listener singleton có thể được gọi đồng thời. Bean Validation providers được thiết kế để `Validator` sử dụng lại theo hướng thread-safe sau khi tạo, còn **business handler mutable state** phải tự quản lý.

- Không giữ trạng thái “message hiện tại” trong field của listener.
- Không dùng bộ đếm `int` trên singleton mà không đồng bộ.
- Đừng tự tạo `ValidatorFactory` mới cho **mỗi message**: khởi tạo provider/metadata tốn kém, nên quản lý nó bằng Spring lifecycle.
- Không cache `ConstraintViolation` chứa object đang validate qua nhiều message.
- Rà soát custom `ConstraintValidator` nếu nó dùng mutable state/chung resource.

### 13.2. Thông điệp lỗi có thể chứa dữ liệu nhạy cảm

Khi validation fail, `ConstraintViolation#getInvalidValue()` có thể chứa payload value nhạy cảm. Không in toàn bộ violations, raw JSON, địa chỉ khách hàng hoặc credentials vào logs mặc định. Nên ghi:

```text
event=payload_rejected
destination=demo.validation.orders
errorCode=ORDER_VALIDATION_FAILED
fields=orderId,quantity
schemaVersion=1
```

Nếu cần correlation giữa producer và consumer, dùng event ID/correlation ID phù hợp nhưng tránh dùng IDs có dữ liệu cá nhân trong metrics labels (cardinality). Broker ACL và TLS là lớp riêng; validation không thay xác thực/ủy quyền.

### 13.3. Giới hạn tài nguyên

Validate một DTO nhỏ thường rẻ, nhưng có thể tốn kém nếu:

- Payload chứa danh sách lớn hàng trăm nghìn item.
- Custom validator truy cập DB/external service cho mỗi field.
- Constraint regex gây backtracking trên chuỗi input dài.
- Message decoder tạo object graph rất lớn trước khi validation.

Thiết kế limit, batching, deadline, backpressure, concurrency và monitoring trước khi tăng số listeners. Đối với dữ liệu không tin cậy, giới hạn ở phía broker/deserializer trước khi gọi Bean Validation.

## 14. Bảng so sánh: @Valid, Validator và kiểm tra nghiệp vụ

| Cơ chế | Kích hoạt | Kiểm tra tốt nhất | Hạn chế |
| --- | --- | --- | --- |
| `@Valid` trên `@Payload` | Argument resolver + configured Validator | Constraints trên DTO và nested object | Không decode JSON, không kiểm tra DB state |
| `@Validated(Group.class)` | Spring validation hints/groups | Quy tắc khác nhau theo ngữ cảnh | Có thể bỏ sót Default group |
| Jakarta `Validator#validate` | Code gọi thủ công | DTO ở bất kỳ tầng nào | Code tự xử lý violations/errors |
| Spring `Validator#validate(target, errors)` | Code hoặc handler factory gọi | Custom validation theo Errors | Không tự chạy Jakarta constraints nếu custom validator không delegate |
| JSON Schema/contract validator | Protocol boundary/decoder | Required, unknown fields, types, schema versions | Không thay business invariants |
| Business service validation | Transaction và domain layer | Tồn kho, quyền, trạng thái hiện tại, idempotency | Có side effects/IO; cần retry/transaction strategy |
| JMS broker ACL/transport policy | Broker/configuration | Auth, destination rights, delivery settings | Không hiểu business DTO |

Đặt một ranh giới rõ: **decode** → **contract/Bean Validation** → **business validation** → **commit/ack**.

## 15. Những lỗi phổ biến và cách xử lý

| Lỗi | Triệu chứng | Hướng giải quyết |
| --- | --- | --- |
| Dùng `javax.validation.Valid` với Boot 3 | Không tương thích Jakarta/compile lỗi | Dùng `jakarta.validation.Valid` |
| Thiếu validation provider | Constraints không hoạt động, lỗi provider initialization | Thêm `spring-boot-starter-validation` |
| Có `@Valid` nhưng không set Validator cho handler factory | Invalid DTO vẫn tới handler hoặc không kiểm tra như mong đợi | Dùng `JmsListenerConfigurer` + `DefaultMessageHandlerMethodFactory#setValidator` |
| Không khởi tạo `DefaultMessageHandlerMethodFactory` theo lifecycle | Argument resolvers chưa được setup | Khai báo bean/đảm bảo `afterPropertiesSet()` |
| Chỉ khai `@Valid` mà không có constraints | Không phát hiện dữ liệu sai | Thêm đúng `@NotBlank`, `@Min`, ... |
| Không có `@Valid` trên nested field | `shipping.city=""` vẫn không bị kiểm tra | Dùng `@NotNull @Valid` trên nested object |
| Chỉ đặt `@Valid` mà quên `@NotNull` | Null object nested không báo lỗi | Đặt `@NotNull` |
| Dùng `@NotNull` cho String bắt buộc | Chuỗi rỗng/spaces vẫn pass | Dùng `@NotBlank` |
| Dùng `int` với field required | Missing field có thể thành 0 | Dùng `Integer` + `@NotNull` và schema |
| DTO JSON chưa có MessageConverter phù hợp | Conversion error trước validation | Cấu hình JSON converter/target type/type ID |
| Jackson type ID là Java FQCN | Producer refactor làm mất tương thích | Dùng stable alias + whitelist mapping |
| Chỉ bật validator trong MVC | JMS listener có cấu hình riêng | Kiểm tra JMS method factory |
| Dùng `@Validated(Group)` mà quên Default | Một số constraint không chạy | Chọn groups/group sequence rõ |
| Bắt validation error bên trong method `@JmsListener` | Method chưa được gọi, không bắt được | Cấu hình container error handling/DLQ |
| Auto retry invalid message mãi | Poison-message loop, spam logs | Bounded retry, DLQ/quarantine |
| Coi `@Valid` như broker ACL/security | Input giả vẫn tới queue | TLS/auth/ACL và schema validation |
| Log `getInvalidValue()` đầy đủ | Rò PII/secrets | Log field path và error code có sanitization |
| Dùng @Valid thay inventory check | DTO pass nhưng business sai | Validate trong domain service |
| Tạo ValidatorFactory mỗi message | Tốn CPU/memory | Dùng bean được quản lý bởi Spring |
| Trộn JS/JSON type coercion | Số/string không còn đúng schema | Schema validation + converter được kiểm soát |

### 15.1. Cách debug khi @Valid không chạy

1. Xác minh message **thực sự tới** listener method của bean được scan.
2. Xác minh Spring Boot/Spring Framework version dùng namespace Jakarta.
3. Kiểm tra dependency validation provider và bean `org.springframework.validation.Validator`.
4. Kiểm tra `JmsListenerConfigurer` được Spring quét và `setMessageHandlerMethodFactory(...)` thực thi.
5. Kiểm tra factory có `setValidator(validator)` và đã khởi tạo đúng.
6. Kiểm tra signature có `@Payload @Valid OrderCommand`, không chỉ nhận raw `TextMessage`.
7. Kiểm tra DTO có constraints và nested `@Valid`.
8. Gửi valid payload trước; sau đó kiểm thử invalid **trong unit/integration environment có DLQ policy**, tránh đầu độc broker production.
9. Đọc root cause của exception: `MessageConversionException` khác `MethodArgumentNotValidException`.
10. Kiểm tra listener container transaction, broker redelivery attempts, DLQ.

### 15.2. Khi có lỗi deserialize nhưng không có violation

Ví dụ JSON:

```json
{"orderId":"order-42","quantity":"not-a-number","shipping":{"city":"Ha Noi","countryCode":"VN"}}
```

Nếu Jackson không thể convert `"not-a-number"` thành `Integer`, nó ném lỗi **trước** Bean Validation. Sửa bằng contract/schema converter error handling; không kỳ vọng `@Min` báo lỗi. Nếu muốn reject numeric strings thay vì cho coercion, phải cấu hình Jackson coercion/schema policy tường minh, vì behavior khác nhau theo phiên bản và config.

## 16. Checklist triển khai production

- [ ] Có bean `Validator` đúng Spring/Jakarta và Bean Validation provider.
- [ ] `@JmsListener` nhận `@Payload @Valid` đúng DTO type.
- [ ] `DefaultMessageHandlerMethodFactory` được đăng ký và gọi `setValidator(...)`.
- [ ] `MessageConverter` giải mã đúng JMS body, type ID và JSON schema version.
- [ ] DTO có constraints required/length/range/format, nested `@Valid`, `@NotNull`.
- [ ] Các field nullable/absent/empty/default được định nghĩa trong contract.
- [ ] Nếu dùng `@Validated`, group composition đúng và có test.
- [ ] Conversion failures tách khỏi validation failures và business errors.
- [ ] Không deserialize Java class tùy ý từ producer-controlled type ID.
- [ ] Không gửi raw entity/JPA proxy làm public payload.
- [ ] Có max message size/nesting/collection limits và security checks.
- [ ] Container transaction/ack/recovery config được kiểm tra với broker thực.
- [ ] Invalid permanent messages vào DLQ/quarantine với bounded redelivery; có alert.
- [ ] Business side effects idempotent, không nhầm validation với exactly-once.
- [ ] Unit test constraints + resolver; integration test với Artemis cho converter/ACK/DLQ.
- [ ] Logs chỉ chứa error codes/paths đã lọc, không lộ body/PII/secrets.
- [ ] Validation latency, error rate, queue backlog, DLQ và throughput được theo dõi.

## 17. Câu hỏi ôn tập

**1. @Valid có tự parse JSON thành Java DTO không?**  
Không. JMS `MessageConverter` thực hiện bước chuyển đổi; `@Valid` kích hoạt validation của DTO đã convert.

**2. Vì sao phải cài `spring-boot-starter-validation`?**  
Để có Jakarta Validation provider thực thi các constraints thay vì chỉ có annotation API.

**3. Tại sao `@Valid` trong @JmsListener có thể không chạy dù MVC đã chạy?**  
Vì JMS dùng handler method factory và argument resolver riêng. Cần Validator được nối đúng qua `DefaultMessageHandlerMethodFactory`.

**4. Thiếu shipping nhưng khai `@Valid ShippingAddress shipping` có lỗi không?**  
Không tự động. `@Valid` không cascade vào null; dùng `@NotNull @Valid`.

**5. Đặt `@NotBlank` và `@NotNull` khác nhau ở đâu?**  
`@NotNull` chỉ reject null; `@NotBlank` còn reject chuỗi rỗng hoặc chỉ có whitespace.

**6. Lỗi JSON quantity="abc" là lỗi gì?**  
Thông thường là conversion/deserialization error trước validation, không phải violation `@Min`.

**7. Loại lỗi nào thường xảy ra khi constraints trên @Payload thất bại?**  
`MethodArgumentNotValidException` trong Spring Messaging, có thể bị wrapper trong listener invocation.

**8. Spring Validator và Jakarta Validator có phải một interface không?**  
Không. `LocalValidatorFactoryBean` có thể làm cầu nối giữa hai API.

**9. @Validated có ích khi nào?**  
Khi cần validation groups như Create/Update. Phải chọn nhóm đúng; không dùng tùy tiện khiến bỏ sót Default group.

**10. Nếu một message sai constraint được retry nhiều lần, nó có tự trở nên hợp lệ không?**  
Không. Permanent validation failures thường cần DLQ/quarantine thay vì retry vô hạn.

**11. @Valid có đảm bảo exactly-once processing hoặc không mất message không?**  
Không. Đó là trách nhiệm của transaction, ack, broker redelivery, idempotency và policy vận hành.

**12. Unit test validator có thay integration test Artemis không?**  
Không. Unit test kiểm tra constraints/argument resolver; broker test cần để kiểm tra JSON conversion, delivery, transaction và DLQ thực.

## 18. Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — Annotation-driven JMS Listener Endpoints: @Valid và DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
2. [Spring Framework 6.2 — DefaultMessageHandlerMethodFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
3. [Spring Framework 6.2 — PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html)
4. [Spring Framework 6.2 — MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html)
5. [Spring Framework — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
6. [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
7. [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
8. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
9. [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
10. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
11. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)