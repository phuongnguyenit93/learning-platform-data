# Kiểm thử method validation và khác biệt với gọi đối tượng Java trực tiếp

**Method validation** là cơ chế kiểm tra ràng buộc Bean Validation trên **tham số và giá trị trả về của một phương thức**, chẳng hạn `@NotBlank String sku`, `@Min(1) int quantity` hoặc `@NotNull` trên return value. Trong một ứng dụng Spring Boot, annotation có vẻ luôn hiện diện ở service nhưng không có nghĩa mọi cách gọi Java đều tự kiểm tra dữ liệu. Kết quả test có thể khác nhau hoàn toàn giữa:

- `new InventoryService().reserve(" ", 0)`: lời gọi **đối tượng Java thuần**, không đi qua AOP proxy; annotation không tự được thực thi.
- `@Autowired InventoryService service; service.reserve(" ", 0)`: lời gọi **Spring-managed bean proxy**, có thể được `MethodValidationPostProcessor` chặn và kiểm tra nếu đã cấu hình đúng, ví dụ class gắn `@Validated`.
- `this.reserve(" ", 0)` bên trong chính `InventoryService`: **self-invocation**, thường gọi thẳng target object và bỏ qua advice của Spring AOP.
- `MockMvc.perform(post(...))`: HTTP request được Spring MVC deserialize, kiểm `@Valid @RequestBody` hoặc **MVC built-in method validation** theo signature controller; đây **không phải** một lời gọi Java thuần.
- `validator.validate(object)` hoặc `validator.forExecutables().validateParameters(...)`: **chạy validation một cách tường minh**, kể cả khi object chưa được Spring quản lý.

Bài Knowledge thuộc nhóm **Tích hợp bổ sung** của **Spring Boot - testing**, tập trung đúng vào câu hỏi **“Kiểm thử method validation và khác biệt với gọi đối tượng Java trực tiếp”**. Ví dụ đầy đủ sử dụng **Java 17, Spring Boot 3.5, Spring Framework 6.2, Jakarta Validation và JUnit Jupiter**. Bộ test so sánh direct-new với Spring AOP proxy, kiểm input/output/nested constraints, tự gọi phương thức nội bộ, và phân biệt exception của **service method validation** với **Spring MVC validation**. Không cần database, Docker hoặc API bên ngoài.

> **Kết luận nền tảng:** annotation không giống một lệnh `if` được Java tự động thực thi. Bạn cần **cơ chế kích hoạt validation phù hợp với entry point**; test bỏ qua entry point đó có thể pass dù production fail, hoặc ngược lại.

## 1. Khái niệm method validation theo Jakarta Bean Validation

Jakarta Bean Validation mô tả nhiều loại constraint:

- **Bean/property constraints:** trên field, getter, record component hoặc type-use, ví dụ `record ReservationRequest(@NotBlank String sku, @Min(1) int quantity)`. Được kiểm khi gọi `Validator.validate(request)` hoặc framework kích hoạt object validation.
- **Executable parameter constraints:** trên tham số method/constructor, ví dụ `reserve(@NotBlank String sku, @Min(1) int quantity)`. Cần thực thi `ExecutableValidator.validateParameters(...)` hoặc interceptor/framework tương ứng.
- **Return-value constraints:** trên method return type, ví dụ `@NotBlank public String reference(...)`. Cần kiểm return value sau khi method đã chạy; với proxy/service có thể throw sau khi method thực thi.
- **Cascaded validation:** `@Valid ReservationRequest request` yêu cầu kiểm constraints **bên trong request object** ở boundary nơi validation được kích hoạt; chỉ đặt `@Valid` không tự khiến một Java call bình thường kiểm object.
- **Groups:** Bean Validation có group `Default` và các marker interfaces; Spring `@Validated(Group.class)` có thể chọn groups cho method validation; `@Valid` đơn thuần không phải selector groups.
- **Cross-parameter constraints:** custom constraint áp trên tổ hợp nhiều tham số, cần validator chuyên dụng; không nên giả vờ `@Min` trên một tham số tự kiểm tương quan hai tham số.
- **Composed constraints:** annotation tùy biến gom nhiều constraints, vẫn cần engine validation và metadata phù hợp.

Ví dụ signature:

```java
@Validated
@Service
public class InventoryService {
    public String reserve(
            @NotBlank String sku,
            @Min(1) int quantity) {
        return "R:" + sku + ":" + quantity;
    }

    @NotBlank
    public String reference(@NotBlank String sku) {
        return sku.equals("unavailable") ? "" : "ref:" + sku;
    }
}
```

Đây chỉ là **snippet**, chưa đủ imports/dependencies; ví dụ runnable nằm ở phần 6. Khi gọi qua Spring proxy, input invalid có thể bị chặn **trước method body**, còn return invalid được phát hiện **sau method body**. Nếu method tạo side effect trước khi bị phát hiện return-value invalid, không được suy rằng exception tự rollback mọi resource; cần transaction boundary/cleanup riêng.

### Bean validation khác executable validation

```text
Bean object:
  ReservationRequest(sku="", quantity=0)
          |
          +-- validator.validate(request)
                      -> violations trên bean properties

Method call:
  inventory.reserve("", 0)
          |
          +-- Java direct invocation -> method chạy, KHÔNG auto check
          |
          +-- Spring proxy -> MethodValidationInterceptor
                                -> validateParameters(...)
                                -> target method
                                -> validateReturnValue(...)
                                -> caller nhận result hoặc exception
```

Một test `validator.validate(dto)` chứng minh **DTO constraints có hiệu lực**, nhưng **không chứng minh** `@Validated` proxy được áp dụng cho service. Một test gọi Spring proxy chứng minh service interception, nhưng **không tự chứng minh** HTTP request được Spring MVC deserialize và phản hồi 400 đúng. Hai loại test trả lời những câu hỏi khác nhau.

## 2. Vì sao `new Service()` khác `@Autowired Service`?

Spring method validation cho bean thường dựa trên **Spring AOP proxy**: Spring quản lý object và `MethodValidationPostProcessor` gắn interceptor cho những bean đủ điều kiện. Với Spring Boot 3.5 có Bean Validation implementation như Hibernate Validator trên classpath (thường qua `spring-boot-starter-validation`), Boot tự cấu hình method validation; target class cần đánh dấu `@Validated` để được áp dụng AOP-based method validation.

```text
Lời gọi Java thuần                         Lời gọi qua Spring
---------------------------------          ----------------------------------
new InventoryService()                     ApplicationContext
         |                                       |
         v                                       v
      target object                          inventoryService proxy
         |                                       |
         +-- reserve("", 0)                     +-- invoke reserve("", 0)
                 |                                   |
                 +-- không interceptor                +-- pre-validate parameters
                 |                                   |
                 +-- "R::0"                          +-- ConstraintViolationException
```

**Khi Bean Validation chưa được cấu hình** (thiếu provider, thiếu starter hoặc thiếu `@Validated` ở target type), kể cả object Spring-managed cũng có thể không được method-validate. Đừng kết luận chỉ cần `@Autowired` là đủ: test phải xác minh cả bean advice/proxy và observed behavior.

### 2.1. `@Validated` của Spring khác `@Valid` của Jakarta

| Annotation | Ý nghĩa thông thường | Ví dụ |
|---|---|---|
| `@Validated` ở class service | Dấu hiệu AOP method validation nên áp dụng cho target bean; có thể khai báo groups | `@Service @Validated class InventoryService` |
| `@NotBlank` trực tiếp trên tham số method | Constraint đối với argument thực tế | `reserve(@NotBlank String sku)` |
| `@Min(1)` trên primitive/boxed number | Giá trị phải không nhỏ hơn 1 | `reserve(@Min(1) int quantity)` |
| `@NotBlank` trên method return value | Ràng buộc giá trị trả về | `@NotBlank String reference(...)` |
| `@Valid` trên method parameter | Cascade constraints của nested object | `reserveRequest(@Valid ReservationRequest request)` |
| `@Valid` trên `@RequestBody` của MVC | Kích hoạt argument validation tại MVC binding boundary | `create(@Valid @RequestBody ReservationRequest r)` |
| `@Validated(Group.class)` | Chọn validation groups tại Spring boundary | `@Validated(Create.class)` hoặc type-level |
| `@NotNull` | Giá trị không được null; khác `@NotBlank` cho String | `@NotNull ReservationRequest request` |

**`@Valid` không phải một constraint annotation tự thân.** Với parameter `@Valid ReservationRequest request` mà **không có `@NotNull`**, null không bị coi là vi phạm chỉ vì `@Valid`; nếu business yêu cầu non-null, bổ sung `@NotNull`. Method body vẫn có thể ném `NullPointerException` nếu dereference null; đó là lỗi Java, không phải violation của `@Valid`.

### 2.2. AOP proxy và giới hạn

- **Caller phải gọi qua proxy**. `this.reserve(...)` trong method khác cùng target thường bỏ qua proxy.
- **CGLIB class proxy** có hạn chế với class/method `final` hoặc `private`, vì không thể override các member như thông thường. JDK dynamic proxy áp dụng cho interface methods; chọn cấu hình phù hợp và không cố dựa vào method private.
- **Bean qua `new` hoặc Mockito mock** không được Spring tự bọc; test mock trả exception khi được lập trình như vậy nhưng không chứng minh thật sự có method validation.
- **Parameter annotations** phải được thấy qua provider/metadata thích hợp. Với interface và implementation, chú ý Jakarta Validation rules về kế thừa method constraints; không tự ý tăng preconditions ở override nếu provider coi là vi phạm.
- **Self-invocation** thường bypass cả method validation, `@Transactional`, `@Async` advice khi dùng proxy-based Spring AOP.
- **AspectJ weaving** khác proxy-based AOP và có semantics self-invocation khác; ví dụ bài này dùng Boot AOP proxy thông thường.

Nếu một test tạo `new InventoryService()` rồi thấy phương thức nhận `quantity=0` không lỗi, đó **không phải bằng chứng validation sai**. Nó chỉ chứng minh bạn đã gọi target bằng đường không có interceptor.

## 3. Ngoại lệ nào có thể xuất hiện?

### Service `@Validated` qua proxy

Spring Framework `MethodValidationInterceptor` có hai chế độ quan trọng:

1. **Mặc định kiểu truyền thống:** vi phạm constraint được báo bằng `jakarta.validation.ConstraintViolationException`, chứa `Set<ConstraintViolation<?>>`.
2. **Adapted violations:** khi cấu hình `MethodValidationPostProcessor.setAdaptConstraintViolations(true)`, có thể báo `org.springframework.validation.method.MethodValidationException` với cấu trúc `MethodValidationResult`.

Trong ví dụ Boot 3.5 mặc định, test service kỳ vọng **`ConstraintViolationException`**. Đừng khẳng định đây là lớp exception bất biến cho mọi application: có thể có custom post-processor, AOP interceptor, REST layer exception translation hoặc thư viện validation khác.

### Spring MVC có đường validation riêng

Kể từ Spring Framework **6.1**, Spring MVC hỗ trợ **built-in method validation** cho `@RequestMapping` handler methods (không cần AOP để kiểm các direct constraints trên handler signature). Theo tài liệu Spring Framework 6.2:

- `@Valid @RequestBody ReservationRequest request` với constraints ở DTO, và **không có direct method-level constraint khác**: lỗi thông thường là **`MethodArgumentNotValidException`**, HTTP **400 Bad Request**.
- `@RequestParam @Min(1) int quantity` hoặc constraint trực tiếp trên handler method parameter/return value: sử dụng **MVC method validation**, lỗi thường là **`HandlerMethodValidationException`**, HTTP 400 cho input violation; return violation thường phản ánh lỗi server.
- Nếu một handler có **cả** `@RequestParam @Min(...)` lẫn `@Valid @RequestBody`, method validation thường **supersedes** validation riêng từng body parameter; exception có thể là `HandlerMethodValidationException` ngay cả khi lỗi nằm trong nested DTO.
- Nếu đặt `@Validated` **ở class-level controller**, Spring có thể đi theo **AOP method validation cũ** thay vì MVC built-in; tài liệu Framework 6.2 khuyến nghị **bỏ class-level `@Validated` trên controller** để dùng cơ chế mới.
- Nếu `@RequestBody` có `BindingResult`/`Errors` ngay sau, hành vi exception có trường hợp khác; không suy mọi lỗi đều ném ra controller advice.
- MVC exception mapping/HTTP status có thể bị `@ControllerAdvice` hoặc custom handlers thay đổi; cần assert theo cấu hình thực tế.

| Đường gọi | Điểm kích hoạt | Lỗi mặc định thường gặp | Đối chứng |
|---|---|---|---|
| `new InventoryService().reserve(" ", 0)` | Không có validation interceptor | Không báo ConstraintViolationException tự động | Java unit test raw object |
| `@Autowired InventoryService.reserve(" ", 0)` | Spring method validation proxy | `ConstraintViolationException` | `@SpringBootTest` + bean được inject |
| `service.reserveRequest(@Valid dto)` | Cascaded executable validation qua proxy | `ConstraintViolationException` | DTO invalid trên method |
| `validator.validate(dto)` | Explicit Jakarta Validator | Trả `Set<ConstraintViolation<T>>` | Không tự throw |
| `validator.forExecutables().validateParameters(...)` | Explicit ExecutableValidator | Trả violations | Chạy được với raw `new` |
| `MockMvc POST @Valid @RequestBody dto` | MVC argument validation | `MethodArgumentNotValidException` | 400, controller chưa chạy |
| `MockMvc GET @RequestParam @Min int` | MVC built-in method validation | `HandlerMethodValidationException` | 400, controller chưa chạy |
| `MockMvc POST có @Min + @Valid body` | MVC method validation | `HandlerMethodValidationException` | 400 và các lỗi theo parameter |

**Không hardcode “service method validation = HTTP 400”.** Service layer ném Java exception; nếu xảy ra trong HTTP request, status phụ thuộc exception handling của ứng dụng. Trong bài code, MVC validate input **trước khi gọi service**, nên response 400 có cơ chế riêng; production cần error contract nhất quán và không lộ nội bộ.

## 4. Đặt mục tiêu kiểm thử trước khi chọn công cụ

| Mục tiêu | Dạng test nên chọn | Có test proxy thật không? |
|---|---|---|
| Kiểm algorithm của method với input đã biết | Unit test `new Service()` | **Không** |
| Kiểm metadata constraint trên DTO | Inject `jakarta.validation.Validator` hoặc xây validator factory | Chỉ test Bean Validation trực tiếp |
| Kiểm `@Validated` service parameter/return constraints | `@SpringBootTest` inject bean, gọi public method qua proxy | **Có** |
| Kiểm self-invocation limitation | Bean proxy gọi method A không có constraint, A gọi `this.B(...)` | Có, để chứng minh bypass |
| Kiểm bean validation groups | Bean validation + Spring context groups tests | Có nếu dùng `@Validated` |
| Kiểm JSON binding + DTO validation + response 400 | `MockMvc` hoặc HTTP integration test | MVC mechanism |
| Kiểm MVC direct method constraints | Spring MVC 6.1+ với `@RequestParam @Min` và `MockMvc` | MVC built-in, **không cần AOP controller** |
| Kiểm controller advice/external API status | `@SpringBootTest`/`@WebMvcTest` với security/filters config thích hợp | Tùy bean graph/slice |
| Kiểm JPA/transaction rollback sau validation | DB integration test + đúng transaction boundary | Khác mục tiêu đơn thuần validation |

Một **unit test chỉ gọi Java trực tiếp** rất hữu ích cho business algorithm; không nên bắt nó chịu trách nhiệm chứng minh AOP. Tương tự, một test `MockMvc` trả 400 có thể chứng minh **MVC binding**, nhưng chưa chứng minh proxy validation của một service khác được gọi ngoài HTTP entry point.

## 5. Thiết kế demo và cây thư mục

Ứng dụng minh họa:

- `ReservationRequest` là Java record với `@NotBlank sku` và `@Min(1) quantity`.
- `InventoryService` là Spring `@Service @Validated` với `reserve` có constraints trực tiếp, `reserveRequest(@Valid ReservationRequest)` để cascade, `reference` có return-value constraint, và `reserveViaSelfCall` cố ý gọi `this.reserve(...)`.
- `OrderController` **không gắn class-level `@Validated`**. POST `/api/orders` dùng `@Valid @RequestBody`; GET `/api/orders/preview` dùng `@RequestParam @Min(1)`; POST `/api/orders/combined` dùng **cả** `@RequestParam @Min(1)` và `@Valid @RequestBody`.
- `InventoryMethodValidationTest` chứng minh direct object bypass và Spring proxy enforce.
- `OrderControllerValidationTest` dùng MockMvc kiểm 400/201, hai exception khác nhau và direct invocation của controller bypass MVC.

```text
method-validation-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodvalidation/
    │   ├── MethodValidationDemoApplication.java
    │   ├── ReservationRequest.java
    │   ├── InventoryService.java
    │   └── OrderController.java
    └── test/java/com/example/methodvalidation/
        ├── InventoryMethodValidationTest.java
        └── OrderControllerValidationTest.java
```

**Phạm vi:** ví dụ không có DB, không xác thực người dùng và không yêu cầu API bên ngoài, nhằm cô lập ranh giới giữa Java call, method proxy và MVC. Không dùng Java agent/weaving để làm lời gọi raw `new` được tự động validate.

## 6. Mã nguồn runnable Java 17 + Spring Boot 3.5

### 6.1. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-validation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

**Tại sao cần cả validation lẫn AOP?** `spring-boot-starter-validation` cung cấp Jakarta Bean Validation implementation (Hibernate Validator); `spring-boot-starter-aop` bảo đảm AOP infrastructure cho Spring method validation proxy; `spring-boot-starter-web` cung cấp MVC/MockMvc integration. `spring-boot-starter-test` mang JUnit Jupiter, AssertJ và Spring test utilities.

Với Spring Boot 3.x phải dùng **`jakarta.validation.*`**, không dùng import `javax.validation.*` từ thế hệ Boot 2 cũ. Java 17 đáp ứng baseline; Boot parent quản lý phiên bản Spring Framework/Security/Test phù hợp. Nếu dự án dùng Boot 4, kiểm module/artifact changes thay vì copy imports/dependencies từ bài này một cách mù quáng.

### 6.2. Ứng dụng chính

File **`src/main/java/com/example/methodvalidation/MethodValidationDemoApplication.java`**:

```java
package com.example.methodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodValidationDemoApplication.class, args);
    }
}
```

Đặt các classes dưới package này để Spring component scan tìm thấy `InventoryService` và `OrderController`. Test cùng package để Spring Boot tự tìm `@SpringBootConfiguration` mà không cần chỉ định `classes` thủ công.

### 6.3. DTO có bean constraints

File **`src/main/java/com/example/methodvalidation/ReservationRequest.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReservationRequest(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
```

Trong Java 17 record, constraints trên components phù hợp với Bean Validation; Hibernate Validator kiểm giá trị của các properties. `@NotBlank` loại null, chuỗi rỗng và chuỗi chỉ có khoảng trắng; `@Min(1)` loại quantity 0, số âm. Lưu ý `@Min` không giới hạn giá trị tối đa, và `@NotBlank` không kiểm quy cách SKU; validation rules thực tế có thể thêm `@Size`/`@Pattern`/business constraints.

### 6.4. Service có method constraints và một ca self-invocation

File **`src/main/java/com/example/methodvalidation/InventoryService.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class InventoryService {

    public String reserve(
            @NotBlank String sku,
            @Min(1) int quantity) {

        return "R:" + sku + ":" + quantity;
    }

    @NotBlank
    public String reference(@NotBlank String sku) {
        if ("unavailable".equals(sku)) {
            return "";
        }
        return "ref:" + sku;
    }

    public String reserveRequest(
            @Valid ReservationRequest request) {

        return reserve(request.sku(), request.quantity());
    }

    // Ví dụ cố ý minh họa self-invocation bypass proxy.
    public String reserveViaSelfCall(
            String sku, int quantity) {

        return this.reserve(sku, quantity);
    }
}
```

`@Validated` đánh dấu target bean cho AOP method validation. Trong `reserveViaSelfCall`, method public **không có constraint trực tiếp**, nên khi caller gọi qua proxy, interceptor không phát hiện lỗi trên parameters của outer method. Sau đó `this.reserve(...)` chạy **trên target**, bỏ qua proxy, nên inner constraints không được kiểm tự động. Đây là minh họa giới hạn proxy chứ **không phải mã nghiệp vụ nên giữ trong production**.

`reserveRequest(@Valid ReservationRequest request)` cho phép kiểm nested constraints qua executable validation nếu được gọi **qua proxy**. Vì `@Valid` không ép non-null, ứng dụng thực nên thêm `@NotNull` nếu contract cấm null. Khi gọi `new InventoryService().reserveRequest(...)` trực tiếp, cả bean constraints nested đều không chạy, vì chỉ có annotation và không có framework invocation.

`reference("unavailable")` trả `""` có chủ ý để minh họa **return-value constraint**. Service method body đã chạy xong rồi proxy mới phát hiện `@NotBlank` không đạt; nếu method đã ghi DB/gọi ngoại hệ, cần transaction/compensation logic riêng, không coi method validation là undo.

### 6.5. Controller MVC có hai đường validation

File **`src/main/java/com/example/methodvalidation/OrderController.java`**:

```java
package com.example.methodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final InventoryService inventory;

    public OrderController(InventoryService inventory) {
        this.inventory = inventory;
    }

    @PostMapping
    public ResponseEntity<String> create(
            @Valid @RequestBody ReservationRequest request) {

        String id = inventory.reserve(
                request.sku(), request.quantity());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(id);
    }

    @GetMapping("/preview")
    public String preview(
            @RequestParam @Min(1) int quantity) {

        return "preview:" + quantity;
    }

    @PostMapping("/combined")
    public ResponseEntity<String> createCombined(
            @RequestParam @Min(1) int priority,
            @Valid @RequestBody ReservationRequest request) {

        String id = inventory.reserve(
                request.sku(), request.quantity());
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body("P:" + priority + ":" + id);
    }
}
```

**Không gắn class-level `@Validated` cho controller này.** Spring Framework 6.2 MVC built-in method validation thấy direct constraint `@Min(1)` trên request parameter của `preview` và `createCombined`. Trong khi đó `create` chỉ có `@Valid @RequestBody` trên DTO (không có direct method constraint trên handler), nên `MethodArgumentNotValidException` là đường exception tiêu biểu khi body sai.

Controller là Spring bean, nhưng **một lời gọi Java trực tiếp** `new OrderController(new InventoryService()).create(new ReservationRequest("", 0))` không đi qua MVC argument resolution/validation, cũng không đi qua Spring service proxy; vì vậy có thể tạo response 201 dù input không hợp lệ. Không đưa direct invocation test này vào production acceptance suite như bằng chứng HTTP endpoint cho phép dữ liệu sai.

### 6.6. Service integration tests: kiểm raw Java và Spring proxy

File **`src/test/java/com/example/methodvalidation/InventoryMethodValidationTest.java`**:

```java
package com.example.methodvalidation;

import java.lang.reflect.Method;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class InventoryMethodValidationTest {

    @Autowired
    private InventoryService springService;

    @Autowired
    private Validator validator;

    @Test
    void directNewDoesNotRunMethodValidation() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reserve(" ", 0))
                .isEqualTo("R: :0");
    }

    @Test
    void springManagedServiceIsAopProxy() {
        assertThat(AopUtils.isAopProxy(springService))
                .isTrue();
    }

    @Test
    void springProxyRejectsBlankSku() {
        assertThatThrownBy(() ->
                springService.reserve(" ", 2))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(1);
                });
    }

    @Test
    void springProxyRejectsQuantityZero() {
        assertThatThrownBy(() ->
                springService.reserve("BOOK-1", 0))
                .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    void springProxyReportsBothParameterViolations() {
        assertThatThrownBy(() ->
                springService.reserve(" ", 0))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(2);
                });
    }

    @Test
    void validArgumentsPassSpringMethodValidation() {
        assertThat(springService.reserve("BOOK-1", 3))
                .isEqualTo("R:BOOK-1:3");
    }

    @Test
    void selfInvocationDoesNotCrossValidationProxy() {
        assertThat(
                springService.reserveViaSelfCall(" ", 0))
                .isEqualTo("R: :0");
    }

    @Test
    void proxyValidatesReturnValueAfterMethodCall() {
        assertThatThrownBy(() ->
                springService.reference("unavailable"))
                .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    void directNewDoesNotValidateReturnValue() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reference("unavailable"))
                .isEqualTo("");
    }

    @Test
    void proxyCascadesValidNestedRequest() {
        ReservationRequest invalid =
                new ReservationRequest("", 0);

        assertThatThrownBy(() ->
                springService.reserveRequest(invalid))
                .isInstanceOf(ConstraintViolationException.class)
                .satisfies(error -> {
                    var violations =
                            ((ConstraintViolationException) error)
                                    .getConstraintViolations();
                    assertThat(violations).hasSize(2);
                });
    }

    @Test
    void directObjectCallBypassesCascadedValidation() {
        InventoryService raw = new InventoryService();

        assertThat(raw.reserveRequest(
                new ReservationRequest("", 0)))
                .isEqualTo("R::0");
    }

    @Test
    void explicitBeanValidatorWorksOnRawRecord() {
        ReservationRequest invalid =
                new ReservationRequest("", 0);

        Set<ConstraintViolation<ReservationRequest>> errors =
                validator.validate(invalid);

        assertThat(errors).hasSize(2);
    }

    @Test
    void executableValidatorChecksRawMethodManually()
            throws Exception {

        InventoryService raw = new InventoryService();
        Method method = InventoryService.class.getMethod(
                "reserve", String.class, int.class);

        var violations = validator.forExecutables()
                .validateParameters(
                        raw, method, new Object[] {" ", 0});

        assertThat(violations).hasSize(2);
    }

    @Test
    void executableValidatorCanCheckRawReturnValue()
            throws Exception {

        InventoryService raw = new InventoryService();
        Method method = InventoryService.class.getMethod(
                "reference", String.class);

        var violations = validator.forExecutables()
                .validateReturnValue(
                        raw, method, "");

        assertThat(violations).hasSize(1);
    }

    @Test
    void validReturnValueFromProxyPasses() {
        assertThat(springService.reference("BOOK-1"))
                .isEqualTo("ref:BOOK-1");
    }
}
```

**15 phương thức `@Test` trong class này**: 3 test raw object/raw return/cascade không bị intercept, test Spring proxy và input violations, test return-value violation, test self-invocation, 3 test explicit Jakarta Validator/executable validator và valid path. Các negative cases mong nhận exception được xem là PASS khi exception đúng, không phải lỗi JUnit.

#### Vì sao test không phụ thuộc message exception?

Tên tham số trong `ConstraintViolation.getPropertyPath()` có thể khác nếu Java compiler không bật `-parameters` hoặc provider dùng metadata khác. Ví dụ dùng `hasSize(1/2)` và exception type, không assert nguyên văn “reserve.sku must not be blank”. Trong dự án thật có thể kiểm constraint descriptor annotation type/property path theo rules đã biết, nhưng tránh phụ thuộc text bản địa hóa của Hibernate Validator.

#### Tại sao dùng `@SpringBootTest(webEnvironment=NONE)`?

Context có cả Spring-managed `InventoryService`, MethodValidationPostProcessor/Bean Validation provider, và AOP infrastructure, nhưng không khởi động HTTP servlet server. Đây là boundary phù hợp để chứng minh **service proxy** mà không tốn chi phí MockMvc/HTTP khi không cần. Nếu một project có nhiều auto configs và muốn test gọn hơn, có thể dùng `ApplicationContextRunner` với cấu hình Validation/AOP chính xác; đừng tự giảm context tới mức bỏ mất post-processor đang muốn test.

### 6.7. MockMvc integration tests: object validation và MVC method validation

File **`src/test/java/com/example/methodvalidation/OrderControllerValidationTest.java`**:

```java
package com.example.methodvalidation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validRequestBodyProduces201() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":3}
                        """))
                .andExpect(status().isCreated())
                .andExpect(content().string("R:BOOK-1:3"));
    }

    @Test
    void invalidRequestBodyProducesMethodArgumentNotValid()
            throws Exception {

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                MethodArgumentNotValidException.class));
    }

    @Test
    void onlyQuantityInvalidStillGetsBodyValidation400()
            throws Exception {

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                MethodArgumentNotValidException.class));
    }

    @Test
    void directRequestParamConstraintUsesMvcMethodValidation()
            throws Exception {

        mvc.perform(get("/api/orders/preview")
                .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                HandlerMethodValidationException.class));
    }

    @Test
    void validRequestParamProduces200() throws Exception {
        mvc.perform(get("/api/orders/preview")
                .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string("preview:2"));
    }

    @Test
    void directConstraintOnHandlerSupersedesBodyValidation()
            throws Exception {

        mvc.perform(post("/api/orders/combined")
                .param("priority", "0")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(result -> assertThat(
                        result.getResolvedException())
                        .isInstanceOf(
                                HandlerMethodValidationException.class));
    }

    @Test
    void combinedHandlerValidArgumentsProduce201() throws Exception {
        mvc.perform(post("/api/orders/combined")
                .param("priority", "2")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"BOOK-1","quantity":3}
                        """))
                .andExpect(status().isCreated())
                .andExpect(content().string("P:2:R:BOOK-1:3"));
    }

    @Test
    void directJavaControllerCallDoesNotRunMvcValidation() {
        OrderController rawController =
                new OrderController(new InventoryService());

        ResponseEntity<String> response =
                rawController.create(
                        new ReservationRequest("", 0));

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody())
                .isEqualTo("R::0");
    }
}
```

**8 phương thức `@Test` trong class MVC**. Bộ test so sánh:

- POST body invalid với `@Valid @RequestBody` → 400, loại `MethodArgumentNotValidException` (không có direct constraints khác trên method handler).
- GET direct method constraint `@RequestParam @Min(1)` → 400, loại `HandlerMethodValidationException`.
- POST combined với `@Min` trên query parameter và `@Valid` trên body → validation cấp method, loại `HandlerMethodValidationException`.
- Các đường valid → 200/201.
- Direct invocation tạo controller và service bằng `new` → không có MVC binder, validation hay Spring method proxy, nên response 201 dù DTO sai. Kết quả này **chỉ đúng cho direct Java call trong demo**, không phải endpoint HTTP hợp lệ.

**Tổng 23 JUnit tests** trong hai classes: 15 service + 8 MVC. Không dùng Mockito mock thay `InventoryService`: đó là một quyết định có chủ đích để tests thực sự chứng minh AOP behavior.

### 6.8. Lệnh chạy và cách đọc kết quả

Cần **JDK 17+**, Maven, không cần Docker:

```bash
mvn test
```

Hoặc chọn từng nhóm:

```bash
mvn -Dtest=InventoryMethodValidationTest test
mvn -Dtest=OrderControllerValidationTest test
```

Nếu có Maven Wrapper đã được thiết lập: `./mvnw test` trên Linux/macOS hoặc `mvnw.cmd test` trên Windows. Với project được tạo đúng cấu trúc và dependency, kỳ vọng **23 tests, 0 failures, 0 errors**. Đây là kết quả kỳ vọng từ assertions, **không phải log kết quả thực thi được tạo ra trong bài**. Mã được kiểm API và semantics dựa trên Spring Boot 3.5/Spring Framework 6.2, nhưng chưa thực thi Maven tại môi trường của bài viết.

Khi kết quả khác kỳ vọng, **đừng vội đổi exception assertions thành `Exception.class` cho test xanh**. Hãy kiểm Spring Boot version, Jakarta Validator provider, bean proxy, controller-level `@Validated`, test slice, ValidationPostProcessor và custom exception mapping.

## 7. Các tình huống không nên đánh đồng

### 7.1. Gọi trực tiếp từ unit test

```java
InventoryService service = new InventoryService();
String result = service.reserve(" ", 0);
```

Đây là Java code hợp lệ và thường trả `"R: :0"` trong demo. Nó kiểm logic của method mà **không đi qua Spring context**, nên **không chứng minh @NotBlank/@Min đã được thực thi**.

Nếu muốn unit test constraint mà không boot toàn bộ Spring:

```java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    var errors = validator.validate(
            new ReservationRequest("", 0));
    assertThat(errors).hasSize(2);
}
```

Đây là **snippet** cần imports Jakarta Validation `Validation`, `Validator`, `ValidatorFactory` và AssertJ; chỉ kiểm DTO constraints. Với executable validation của raw service, dùng `validator.forExecutables().validateParameters(target, method, args)` và `validateReturnValue(...)` như test đã minh họa. Không gọi `Validator.validate(service)` rồi giả định nó tự kiểm method signature: `validate(bean)` chủ yếu kiểm bean property constraints, không phải tự “thực hiện” mọi executable validation.

### 7.2. Self-invocation: service có proxy nhưng bên trong vẫn không validate

```java
public String reserveViaSelfCall(String sku, int quantity) {
    return this.reserve(sku, quantity);
}
```

Khi caller đi qua `springService.reserveViaSelfCall`, interceptor có thể thấy method outer; vì outer không có constraint, nó cho qua. Sau đó `this.reserve` gọi target trực tiếp, không qua proxy, nên inner `@NotBlank`/`@Min` bị bỏ qua.

**Hướng sửa được ưu tiên:** tách phương thức cần validate sang bean khác, và gọi qua bean Spring được inject; hoặc đưa validation vào boundary outer tương ứng, hoặc gọi explicit validator nếu framework proxy không phù hợp. **Không khuyến khích** làm code nghiệp vụ phụ thuộc `AopContext.currentProxy()` trừ khi có lý do rất rõ, vì nó làm tăng coupling và yêu cầu proxy exposure.

### 7.3. `@Valid` trên DTO không thay thế constraints của method

Một DTO record có `@NotBlank`/`@Min` được kiểm khi Spring MVC xử lý `@Valid @RequestBody`. Nhưng nếu service nhận **hai scalar parameters**, nó có thể cần constraint riêng trên `reserve(@NotBlank sku, @Min qty)` để bảo vệ callers **ngoài HTTP** (scheduled job, Kafka consumer, CLI adapter hoặc integration test).

Ngược lại, nếu service nhận `@Valid ReservationRequest`, proxy có thể cascade vào object. Với null, `@Valid` không đủ: thêm `@NotNull` khi yêu cầu input bắt buộc.

### 7.4. Parameter validation và return validation có thời điểm khác

- **Input constraint** fail ở proxy **trước** method body chạy: thường không có side effect bên trong method (trừ behavior khác từ interceptor/argument construction).
- **Return-value constraint** fail **sau** target method đã thực thi. Nếu method đã ghi DB và commit transaction độc lập hoặc gửi message trước lúc lỗi được phát hiện, exception không đủ để chứng minh mọi side effect được rollback.
- **Method groups** có thể làm một số constraints chỉ áp dụng theo nhóm. Test dùng `@Validated(Group.class)` phải biết group đang active và test cả positive/negative.
- **Cross-parameter validation** cần custom constraint theo chuẩn Bean Validation; test logic hai tham số riêng không tự chứng minh điều kiện như startDate <= endDate.

### 7.5. Final class/method, interface proxy và qualifier

- Với JDK proxy, callers thường inject bean qua interface; cần hiểu constraints được khai báo ở interface/implementation theo quy tắc Jakarta Validation về method inheritance.
- Với CGLIB, class/method `final` không được override theo cách proxy interceptor thông thường; dùng class/method có thể được advised và giữ public signature.
- Nếu test dùng `new SomeService()`, không có Spring bean proxy, dù class có `@Component`/`@Validated`.
- Nếu bạn thêm `@Primary` hoặc tên bean khác, không tự giải quyết method validation; điều cần kiểm là **bean object caller thực sự nhận** và nó có interceptor đúng.

## 8. Sự khác nhau trong HTTP status và exception mapping

| Lỗi được phát hiện tại | Exception điển hình | Status mặc định/thường dùng | Lưu ý |
|---|---|---|---|
| MVC `@Valid @RequestBody` | `MethodArgumentNotValidException` | **400** | Validating DTO khi argument binding |
| MVC direct `@Min`/`@NotBlank` trên handler | `HandlerMethodValidationException` | **400** cho input | Return-value violation có thể được xử lý như server error |
| Spring service `@Validated` proxy | `ConstraintViolationException` | **Không phải tự nhiên 400 ở mọi context** | Exception từ service; cần error handler phù hợp |
| MethodValidationPostProcessor adapted mode | `MethodValidationException` | Tùy exception handling | Không giống luôn với ConstraintViolationException |
| Input JSON sai cú pháp | `HttpMessageNotReadableException` | **400** | Lỗi parse/deserialization, không phải constraint |
| Query String "abc" cho int | `MethodArgumentTypeMismatchException` | Thường **400** | Conversion error xảy ra trước/khác validation |
| Không có authentication/authorization | Security exceptions/handlers | 401/403 theo cấu hình | Không đồng nhất với method validation |
| Null dereference trong direct method | `NullPointerException` | 500 nếu không xử lý | Không phải tự động là @NotNull validation |

### ControllerAdvice nên xử lý theo lỗi thực tế

Trong API production, có thể viết `@RestControllerAdvice` với handlers riêng cho `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `ConstraintViolationException` và dữ liệu không thể parse. Nhưng đừng gộp mọi `RuntimeException` thành 400: lỗi lập trình/DB/service vẫn cần được phân loại đúng.

Cùng một vi phạm business input có thể xuất hiện ở DTO layer, service layer hoặc provider layer. Thiết kế error response (problem details, code, field/path, correlation ID) phải nhất quán theo contract, không đưa class name/stack trace/giá trị nhạy cảm ra HTTP response. Khi test controller, kiểm cả **status + error schema**, không chỉ message của Hibernate Validator có thể bị localization thay đổi.

## 9. Spring MVC 6.1+: hiểu trước khi chuyển class-level `@Validated`

Trong Spring Framework 6.1+, MVC built-in method validation xử lý direct method constraints trên handler signature. Tài liệu Spring Framework 6.2 nêu rõ: để dùng built-in mechanism, **bỏ class-level `@Validated` khỏi controller**; nếu vẫn có, validation có thể được áp dụng qua AOP proxy thay vì MVC path.

Điều quan trọng:

1. **`@Valid` riêng lẻ không phải direct constraint.** Với body DTO, thường dẫn tới argument validation và `MethodArgumentNotValidException`.
2. Thêm **`@NotNull`** trực tiếp lên parameter handler có thể kích hoạt **method validation**, thay đổi exception type.
3. Một handler có `@Min` trên query param và `@Valid` trên body có thể báo `HandlerMethodValidationException` khi body nested invalid; vì method validation **bao trùm cả nested constraints**.
4. Test có `@ControllerAdvice` bắt `MethodArgumentNotValidException` nhưng không bắt `HandlerMethodValidationException` có thể có error response không nhất quán sau nâng cấp framework.
5. `BindingResult` ngay sau parameter có thể làm method được gọi trong những trường hợp errors chỉ có ở parameter có binding-result; đừng assert mọi @Valid luôn ném exception.
6. Với WebFlux, validation/exceptions tương tự về ý tưởng nhưng web stack/exception classes khác; không copy MockMvc test trực tiếp sang WebTestClient.

**Mục tiêu QA khi nâng cấp:** rà soát handler signatures, class-level `@Validated`, MVC exception handlers và tests. Không chỉ tìm annotation trong code rồi kết luận lỗi thuộc Bean Validation path nào.

## 10. Test slice và Mockito có thể làm mất validation như thế nào?

### `@WebMvcTest`

`@WebMvcTest(OrderController.class)` nạp MVC slice, có thể kiểm request binding và built-in MVC validation. Nhưng nếu controller inject `InventoryService` mà slice không tạo bean thật, test thường cung cấp mock (`@MockitoBean` hoặc setup phù hợp). Khi đó **service method validation proxy** có thể **không tồn tại** hoặc không đại diện production. Test slice pass với 400 ở DTO **không chứng minh** service proxy được validate. Cần một `@SpringBootTest` hoặc context riêng có post-processor cho service boundary.

### Mockito `mock(InventoryService.class)`

Mock không tự dùng Spring `MethodValidationPostProcessor`; nó thường trả giá trị mặc định hoặc behavior do test cấu hình. Nếu:

```java
InventoryService mock = Mockito.mock(InventoryService.class);
mock.reserve(" ", 0);
```

Đây là snippet (cần Mockito) và **không phải test method validation của service thật**. Mockito có thể được cấu hình throw ConstraintViolationException, nhưng điều đó chỉ test cách caller xử lý exception, không xác minh constraint annotations/provider.

### `@InjectMocks` hoặc gọi constructor raw

`@InjectMocks` tạo một target object và inject mocks, **không tự đảm bảo** Spring AOP proxy hay Jakarta validation chạy. Rất phù hợp với unit test algorithm nhưng không phù hợp nếu tiêu chí là `@Validated` interception. Cần test bằng **real Spring bean** qua context khi behavior mong đợi xuất phát từ Spring infrastructure.

## 11. Bẫy kiểm thử và cách phát hiện

| Sai lầm | Vì sao sai | Test nên làm |
|---|---|---|
| Gọi `new Service().method(invalid)` rồi mong annotation throw | Không có proxy/interceptor | Inject real bean và gọi qua Spring proxy |
| Chỉ assert service có `@Validated` bằng reflection | Metadata chưa chứng minh advice chạy | `AopUtils.isAopProxy` + invalid invocation |
| Bỏ `spring-boot-starter-validation` | Thiếu implementation Jakarta Validation | Thêm starter và kiểm provider/auto config |
| Bỏ AOP infrastructure | Không có proxy interception | Đảm bảo Spring AOP được cấu hình đúng |
| Self-invocation `this.validatedMethod` | Bỏ qua AOP proxy | Tách bean hoặc validate tại outer boundary |
| Class/method `final` trong CGLIB proxy | Không thể advise bằng override | Đổi design hoặc proxy phù hợp |
| `@Valid` được hiểu như `@NotNull` | Null không tự là violation | Thêm `@NotNull` khi contract yêu cầu |
| Chỉ validate DTO rồi nghĩ service được bảo vệ | DTO constraints khác executable constraints | Test `@Validated` bean proxy riêng |
| Truyền invalid DTO qua MockMvc rồi chỉ kiểm status | Không biết exception thuộc MVC argument hay method validation | Assert `getResolvedException()` type |
| Mọi HTTP 400 đều bị gọi là validation | Parse/type mismatch khác validation | Test JSON invalid, missing param, method constraints riêng |
| Dùng `@Validated` class-level controller với MVC 6.2 mà không xét advice | Có thể đổi validation path | Theo MVC built-in docs, remove nếu muốn path mới |
| Assert exception message nguyên văn | Hibernate Validator/localization/parameter names thay đổi | Assert type, constraint metadata, counts/path khi phù hợp |
| `ConstraintViolationException` bị map về 500 ngoài HTTP | Service exception không có implicit API status | Implement exception handling đúng business semantics |
| Return-value constraint bị throw nhưng đã tạo side effect | Lỗi phát hiện sau method body | Transaction/compensation và integration test side effects |
| Kiểm `isAopProxy` nhưng không gọi invalid method | Có thể proxy vì lý do khác như transaction | Assert error semantics của chính validation |
| Mockito thay real service bean | Mất validation behavior của target | Chạy integration test bean thật |
| Test chỉ positive input | Có thể service không validate gì mà vẫn pass | Thêm invalid parameter/return/nested cases |
| Test dùng `assertThrows(Exception.class)` | Quá rộng, che lỗi config/proxy khác | Assert đúng class/cause và số violations |
| Test chỉ @Valid request body | Không test method validation @RequestParam/return | Thêm MockMvc direct parameter constraint |
| Test thiếu provider khi upgrade Boot 2→3 | `javax` vs `jakarta` namespace khác | Chuyển imports và dependency version nhất quán |

## 12. Checklist trước khi kết luận method validation hoạt động

- [ ] Tôi xác định rõ entry point: raw Java call, Spring service proxy, MVC handler hay explicit Validator.
- [ ] Có Bean Validation provider và dependency đúng dòng Spring Boot.
- [ ] Dùng `jakarta.validation.*` với Boot 3.5.
- [ ] Service target có `@Validated` và method public có parameter/return constraints.
- [ ] Test gọi bean inject từ Spring context, không chỉ raw `new`.
- [ ] Negative test invalid argument cho thấy proxy thật sự ném violation.
- [ ] Test kiểm input valid vẫn thực thi method và trả output đúng.
- [ ] Test phân biệt violation tại parameter và tại return value.
- [ ] Có test `@Valid` nested DTO qua proxy hoặc explicit Validator.
- [ ] Không nhầm `@Valid` tự bác bỏ null; có `@NotNull` khi cần.
- [ ] Test self-invocation nếu code có internal calls tới method annotated.
- [ ] Không để class/method final/private chặn proxy advice mà không biết.
- [ ] Nếu dùng interface proxies, annotation/method inheritance tuân thủ Jakarta Validation.
- [ ] `@SpringBootTest(webEnvironment=NONE)` phù hợp khi chỉ test service method validation.
- [ ] Với MVC, đã test cả `@Valid @RequestBody` và direct `@Min`/`@NotBlank` trên handler.
- [ ] MVC controller không gắn class-level `@Validated` nếu muốn MVC built-in validation của Framework 6.1+.
- [ ] Test phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [ ] Cấu hình `@ControllerAdvice` xử lý đúng error schema/status khi có nhiều validation paths.
- [ ] Test không chỉ assert HTTP status 400 mà còn chứng minh đúng nguồn lỗi.
- [ ] Mockito mocks không được dùng làm bằng chứng Spring method validation proxy thật.
- [ ] Assertions không phụ thuộc message bản địa hóa hoặc thứ tự violations.
- [ ] Return-value violation được phân tích về side effects/transaction boundaries.
- [ ] Test thực thi bằng Maven/JUnit trên JDK 17+ và phiên bản Boot/framework đang dùng.
- [ ] Mọi kết luận ghi rõ phạm vi: raw object, proxy, MVC hay provider; không tổng quát hóa sai.

**Kết luận:** Kiểm thử **method validation** không phải là tìm xem method có `@NotBlank` hay `@Min` hay không, mà là chứng minh **constraint được thực thi tại entry point thực tế**. Lời gọi `new`/`this` thường bỏ qua proxy; Spring `@Validated` service qua AOP có thể phát `ConstraintViolationException`; Spring MVC 6.1+ kiểm controller theo cơ chế riêng với `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException`. Test chất lượng cần **đối chứng direct Java call và Spring-managed path**, kiểm input/return/nested constraints, và không nhầm HTTP 400 với mọi exception từ service.

### Tài liệu chính thức

- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — Java Bean Validation và Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @RequestBody validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MethodValidationInterceptor API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Spring Framework 6.2 — Spring AOP proxying and self invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
