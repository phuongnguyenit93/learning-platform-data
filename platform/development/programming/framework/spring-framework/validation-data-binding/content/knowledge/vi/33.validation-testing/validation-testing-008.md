# Kiểm thử thời gian với ClockProvider hoặc đồng hồ cố định trong Spring Validation

## 1. Vấn đề: một bài test hôm nay đúng nhưng ngày mai sai

Hãy xét DTO cho phép đặt lịch:

```java
public record BookingRequest(
        @Future Instant startsAt) {
}
```

Đây là fragment, cần import `jakarta.validation.constraints.Future` và `java.time.Instant`. Hôm nay một bài test truyền `startsAt=2030-01-15T12:00:00Z` có thể hợp lệ, nhưng khi thời gian thực vượt mốc đó, cùng một input sẽ thất bại. Một test khác dùng `LocalDate.now()` để dựng dữ liệu có thể chập chờn ngay thời điểm đổi ngày, đặc biệt trên CI chạy múi giờ khác máy lập trình viên.

Các nguồn gây test không ổn định thường gồm:

- Dùng `Instant.now()`, `LocalDate.now()` hoặc `System.currentTimeMillis()` trực tiếp bên trong logic hoặc assertions.
- Thời điểm hiện tại tiến lên trong lúc test chuẩn bị request, validation và service chạy.
- `@Future`/`@Past` so sánh với đồng hồ của Jakarta Validation, còn business service so sánh với một đồng hồ khác.
- JVM mặc định dùng múi giờ khác nhau tại local, CI và môi trường triển khai.
- Test thời điểm đúng ranh giới “hôm nay”, “trong tương lai” hoặc “đủ 30 phút trước khi bắt đầu” nhưng không xác định rõ liệu ranh giới là inclusive hay exclusive.
- Hai phép kiểm tra ở những tầng khác nhau gọi `now()` tại các thời điểm không đồng nhất, tạo lỗi không tái hiện được.
- Một thư viện cấu hình temporal tolerance hoặc ClockProvider đặc thù, còn test chỉ thay `Clock` bean của Spring.
- Code test can thiệp múi giờ mặc định toàn JVM, ảnh hưởng những test đang chạy song song.

**Giải pháp:** đưa “hiện tại” vào hệ thống như một dependency rõ ràng. Với các Jakarta temporal constraints, dùng `jakarta.validation.ClockProvider`; với business code dùng `java.time.Clock` được inject. Trong test, tạo `Clock.fixed(...)` và bảo đảm cả validator lẫn service sử dụng đồng hồ ấy.

Bài thuộc nhóm **Kiểm thử** của module **Spring Framework — validation-data-binding**, dùng Java 17+, Jakarta Validation 3, Spring Framework 6 và Spring Boot 3.x. Ví dụ có unit tests, MockMvc integration tests, ngày theo UTC và kiểm chứng ranh giới.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | API | Vai trò |
| --- | --- | --- |
| Đồng hồ Java | `java.time.Clock` | Cung cấp instant hiện tại và múi giờ; dùng trong business logic và tests |
| Đồng hồ Jakarta Validation | `jakarta.validation.ClockProvider` | Cung cấp `Clock` cho temporal constraints như `@Past` và `@Future` |
| Khởi tạo validator | `jakarta.validation.Configuration#clockProvider(...)` hoặc customizer của Boot | Gắn ClockProvider với `ValidatorFactory` thực sự dùng để validation |

### 2.1. java.time.Clock

`Clock` là abstraction tích hợp trong Java, có các factory methods:

```java
Clock realClock = Clock.systemUTC();

Clock frozenClock = Clock.fixed(
        Instant.parse("2030-01-15T12:00:00Z"),
        ZoneOffset.UTC
);

Instant now = frozenClock.instant();
LocalDate today = LocalDate.now(frozenClock);
```

Đây là fragment Java với imports `java.time.*`.

- `Clock.systemUTC()` lấy thời gian hệ thống, zone UTC.
- `Clock.systemDefaultZone()` lấy thời gian hệ thống với zone mặc định JVM.
- `Clock.fixed(instant, zone)` luôn trả cùng một instant, lý tưởng để kiểm thử deterministic.
- `Clock.offset(baseClock, duration)` dịch thời gian của base clock; nếu base là system clock, thời gian **vẫn trôi**, không phải frozen.
- `Clock.tick(baseClock, duration)` có thể làm tròn thời gian theo tick duration; nếu base trôi, đây cũng **không phải** một đồng hồ cố định.

Trong test yêu cầu giá trị giống nhau tuyệt đối qua nhiều phép gọi, dùng `Clock.fixed`.

### 2.2. Jakarta ClockProvider

`ClockProvider` là interface:

```java
@FunctionalInterface
public interface ClockProvider {
    Clock getClock();
}
```

Đây là **chữ ký rút gọn** để giải thích API, không phải mã cần tự khai báo; interface thật nằm trong `jakarta.validation.ClockProvider`. Nó cung cấp `Clock` cho validators thời gian. Implementation phải **thread-safe** vì validator factory/validator được dùng đồng thời, và `getClock()` không được trả null.

Cấu hình mặc định theo Jakarta Bean Validation là đồng hồ hệ thống với default time zone. Khi test không ghi đè, các annotation sẽ đánh giá dựa vào thời gian hiện tại thật, do đó phụ thuộc ngày chạy và môi trường.

### 2.3. Bốn annotation thời gian phổ biến

| Constraint | Điều kiện với reference time | Ranh giới |
| --- | --- | --- |
| `@Past` | Giá trị nằm **trước** hiện tại | Strict, không gồm hiện tại |
| `@PastOrPresent` | Giá trị ở trước **hoặc tại** hiện tại | Inclusive |
| `@Future` | Giá trị nằm **sau** hiện tại | Strict, không gồm hiện tại |
| `@FutureOrPresent` | Giá trị ở sau **hoặc tại** hiện tại | Inclusive |

Các annotation hỗ trợ những kiểu thời gian tiêu chuẩn như `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, `YearMonth` (phạm vi cụ thể do Jakarta Validation spec quy định).

**Điểm quan trọng:** khái niệm “present” là tương đối theo kiểu dữ liệu. Với `LocalDate`, **cả ngày hôm nay** được coi là hiện tại; với `YearMonth`, cả tháng hiện tại được coi là hiện tại. Không diễn giải `@Future LocalDate` như “bất kỳ thời điểm nào lớn hơn hiện tại trong ngày hôm nay”; nó yêu cầu **ngày sau ngày hiện tại** theo zone của ClockProvider.

### 2.4. Null không đồng nghĩa lỗi thời gian

Với Bean Validation, các temporal constraints thường coi `null` là hợp lệ để tách yêu cầu hiện diện khỏi điều kiện thời gian. Nếu input bắt buộc, kết hợp:

```java
@NotNull
@Future
private Instant startsAt;
```

Đây là fragment field, cần imports `jakarta.validation.constraints.NotNull` và `Future`. Nếu chỉ có `@Future`, một value null có thể **không tạo violation**. Đừng dùng một assertion “missing field bị từ chối” làm bằng chứng `@Future` tự bao hàm `@NotNull`.

## 3. ClockProvider lấy "now" từ đâu trong pipeline Spring MVC?

Với JSON request:

```text
POST /bookings
Content-Type: application/json
            |
            v
HttpMessageConverter (Jackson) tạo BookingRequest
            |
            v
@Valid / Spring MVC validation adapter
            |
            v
Jakarta Validator từ ValidatorFactory
            |
            +-- ClockProvider.getClock()
            |
            +-- @Future / @Past / @FutureOrPresent
            |
            v
MethodArgumentNotValidException nếu constraint lỗi
            |
            v
RestControllerAdvice đổi thành HTTP 400
```

Nếu validation thành công, controller mới gọi service. Service có thể có điều kiện riêng như “đặt lịch phải trước thời gian bắt đầu ít nhất 30 phút”. Nếu service tự gọi `Instant.now()` thì **ClockProvider không tự điều khiển giá trị đó**; cần inject `Clock` vào service.

### Một Clock cho hai nơi

Thiết kế mong muốn:

```text
                Clock bean
                 /      \
                v        v
       ClockProvider   BookingService
             |             |
             v             v
       @Future/@Past   lead-time rule
```

Trong test, thay bean `Clock` bằng `Clock.fixed(...)`; cả validator và service nhận cùng nguồn thời gian. Trong production, bean `Clock.systemUTC()` cung cấp thời gian thực.

**Lưu ý về scope:** cấu hình ClockProvider trên một `ValidatorFactory` chỉ tác động các validators lấy clock từ factory đó. Nó không đổi `Clock.systemUTC()`, `Instant.now()`, một `ValidatorFactory` khác, database `CURRENT_TIMESTAMP` hoặc hệ thống bên ngoài.

## 4. Những phép so sánh phải xác định ranh giới rõ ràng

Chọn instant cố định:

```text
Reference now = 2030-01-15T12:00:00Z
Zone = UTC
Today = 2030-01-15
```

Kết quả dự kiến, **nếu không cấu hình temporal tolerance**:

| Constraint và kiểu | Input | Kết quả |
| --- | --- | --- |
| `@Future Instant` | `2030-01-15T11:59:59Z` | Sai |
| `@Future Instant` | `2030-01-15T12:00:00Z` | Sai: bằng hiện tại |
| `@Future Instant` | `2030-01-15T12:00:01Z` | Đúng |
| `@Past Instant` | `2030-01-15T11:59:59Z` | Đúng |
| `@Past Instant` | `2030-01-15T12:00:00Z` | Sai: bằng hiện tại |
| `@PastOrPresent Instant` | `2030-01-15T12:00:00Z` | Đúng |
| `@FutureOrPresent Instant` | `2030-01-15T12:00:00Z` | Đúng |
| `@Future LocalDate` | `2030-01-15` | Sai: hôm nay |
| `@Future LocalDate` | `2030-01-16` | Đúng |
| `@Past LocalDate` | `2030-01-14` | Đúng |
| `@Past LocalDate` | `2030-01-15` | Sai |
| `@FutureOrPresent LocalDate` | `2030-01-15` | Đúng |
| `@PastOrPresent YearMonth` | `2030-01` | Đúng |

Mốc **2030-01-15** ở đây chỉ là một fixture cho bài học, không phải thời gian thực hôm nay. Việc cố định mốc này giúp test không hết hạn.

### @Future không phải quy tắc "ít nhất 30 phút trước"

Với `@Future`, thời điểm sau `now` một giây là hợp lệ. Nhưng nghiệp vụ có thể yêu cầu đặt trước ít nhất 30 phút:

```java
Instant deadline = clock.instant().plus(Duration.ofMinutes(30));

if (request.startsAt().isBefore(deadline)) {
    throw new BookingTooSoonException();
}
```

Đây là fragment service. Nó cho phép **đúng 30 phút** và từ chối nhỏ hơn 30 phút. Nếu yêu cầu là **hơn 30 phút**, thay `isBefore(deadline)` bằng `!isAfter(deadline)`. Hãy ghi rõ semantics của dấu bằng; không để lỗi off-by-one phụ thuộc cách diễn đạt tiếng Việt.

## 5. Thiết lập ClockProvider khi kiểm thử Jakarta Validator trực tiếp

Không cần Spring context để test một constraint thuần:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2030-01-15T12:00:00Z"),
        ZoneOffset.UTC
);

try (ValidatorFactory factory = Validation
        .byDefaultProvider()
        .configure()
        .clockProvider(() -> fixed)
        .buildValidatorFactory()) {

    Validator validator = factory.getValidator();
    // validator.validate(dto)
}
```

Đoạn là fragment, cần imports `java.time.*` và `jakarta.validation.*`. Jakarta `Configuration#clockProvider(...)` nhận `ClockProvider`. Factory được đóng sau test để giải phóng resources.

**Tại sao tốt hơn sleep?** Không phụ thuộc tốc độ máy, tốc độ CI, scheduling hoặc thời điểm hệ thống đổi ngày. Test có thể xác định chính xác input ngay trước, bằng và ngay sau mốc.

### Không nhầm hai loại Validator

- `jakarta.validation.Validator` có `validate(...)` trả `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator` dùng `supports(...)` và `validate(Object, Errors)`.
- `LocalValidatorFactoryBean` trong Spring tích hợp cả Jakarta validation và Spring validation adapter.

Khi đang dùng `Validation.buildDefaultValidatorFactory()` thủ công, đừng nghĩ nó tự thay validator đang được MVC dùng trong application context. Đó là một factory riêng; muốn MockMvc dùng đồng hồ cố định, phải cấu hình factory/validator của Spring MVC.

## 6. Tích hợp với Spring Boot: ValidationConfigurationCustomizer

Trong Spring Boot 3.x có `org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer`. Khi có Bean Validation provider và Boot auto-configuration, bean này cho phép tùy biến `jakarta.validation.Configuration<?>` trước khi xây `ValidatorFactory`.

Ví dụ khái niệm:

```java
@Bean
ValidationConfigurationCustomizer useClock(Clock clock) {
    return config -> config.clockProvider(() -> clock);
}
```

Nếu ứng dụng đăng ký một `Clock` bean duy nhất và validator được Boot tự cấu hình thông thường, cách này giúp built-in temporal constraints dùng clock được inject.

**Lợi ích lớn khi test:** chỉ cần thay `Clock` bean bằng phiên bản fixed trong test context; `ValidationConfigurationCustomizer` tham chiếu cùng Clock bean đó, và service cũng nhận nó qua constructor.

**Giới hạn quan trọng:**

- Customizer tác động factory do **Boot validation auto-configuration** tạo. Nếu app khai báo một `LocalValidatorFactoryBean` độc lập và bỏ qua Boot auto-config, cần cấu hình clock trên chính factory ấy.
- `@WebMvcTest` có test slice và bean scanning riêng; đừng suy rằng mọi @Configuration và Clock bean production luôn được import. Cần test wiring rõ.
- `MockMvcBuilders.standaloneSetup(...)` không tải Boot application context; phải truyền validator tùy biến cho standalone khi cần.
- Nếu app dùng nhiều `ValidatorFactory`, một customizer không tự điều khiển mọi factory.
- Cấu hình customizer trong **test-only profile** không được vô tình chảy vào production.

### Cách cấu hình trực tiếp LocalValidatorFactoryBean

Trong Spring Framework 6.x, `LocalValidatorFactoryBean#setConfigurationInitializer(...)` cho phép can thiệp vào Bean Validation Configuration:

```java
LocalValidatorFactoryBean factory =
        new LocalValidatorFactoryBean();

factory.setConfigurationInitializer(
        config -> config.clockProvider(() -> fixedClock));

factory.afterPropertiesSet();
// factory.validate(dto) hoặc dùng làm Spring Validator.
factory.destroy();
```

Đây là fragment với biến `fixedClock` đã tồn tại, không phải bean production hoàn chỉnh. Khi tự quản lý lifecycle, cần đóng/destroy. Trong Spring context, bean lifecycle thường do container quản lý.

**Tránh tạo hai bean ValidatorFactory cạnh tranh:** nếu khai báo một bean tùy biến, phải xác nhận Spring MVC thật sự dùng nó. Test trực tiếp factory vẫn pass trong khi MVC dùng factory mặc định thì không có giá trị chứng minh parity.

## 7. Project runnable: Spring MVC booking với một đồng hồ cho validation và service

Ta xây một ứng dụng Maven nhỏ sử dụng:

- `Clock.systemUTC()` trong production.
- `ValidationConfigurationCustomizer` để biến Clock thành `ClockProvider` cho Jakarta temporal validation.
- `@Valid @RequestBody` với `@Future`, `@FutureOrPresent`, `@Past` và `@NotNull`.
- Một business rule: lịch phải đặt trước **ít nhất 30 phút**.
- `@SpringBootTest + @AutoConfigureMockMvc` thay Clock bằng `Clock.fixed(...)` tại test context.
- Một unit test riêng xây `ValidatorFactory` từ Jakarta Configuration và ClockProvider, kiểm tra các ranh giới.
- Error response dùng mã ổn định cho validation và business error, không copy raw exception.

**Chủ ý đơn giản hóa:** không có database, kho lịch thực tế, xác thực hay kiểm tra chỗ trống. Một response 201 trong demo chỉ xác nhận việc đánh giá constraint/lead-time theo clock. Production cần transaction, availability/business concurrency và authorization riêng.

### 7.1. Cấu trúc thư mục

```text
clock-validation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ClockValidationApplication.java
    │   ├── ClockConfiguration.java
    │   ├── BookingRequest.java
    │   ├── BookingService.java
    │   ├── BookingController.java
    │   └── ApiErrorAdvice.java
    └── test/java/demo/
        ├── TemporalConstraintUnitTest.java
        └── BookingMvcTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>clock-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

Spring Boot parent quản lý versions của Spring MVC, Jackson Java Time và Hibernate Validator. `spring-boot-starter-validation` cần được khai báo để có Bean Validation implementation.

### 7.3. src/main/java/demo/ClockValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClockValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ClockValidationApplication.class, args);
    }
}
```

### 7.4. src/main/java/demo/ClockConfiguration.java

```java
package demo;

import java.time.Clock;

import org.springframework.boot.autoconfigure.validation
        .ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock applicationClock() {
        // Chọn UTC có chủ đích, tránh phụ thuộc JVM timezone.
        return Clock.systemUTC();
    }

    @Bean
    public ValidationConfigurationCustomizer
            validationClockCustomizer(Clock clock) {
        // Jakarta ClockProvider là functional interface.
        return configuration ->
                configuration.clockProvider(() -> clock);
    }
}
```

Đây là **cấu hình production**, tự động được quét vì cùng package `demo`. Import `ValidationConfigurationCustomizer` có thể viết trên một dòng trong IDE (ở đây xuống dòng giữa qualified package và class hợp lệ về Java lexical whitespace sau dấu chấm). Nếu công cụ format code không chấp nhận style đó, có thể gộp thành một dòng import duy nhất.

Đường truyền cấu hình:

1. Boot tạo bean `Clock applicationClock` trả thời gian thực UTC.
2. Boot tạo `ValidationConfigurationCustomizer` nhận Clock qua DI.
3. Boot dùng customizer để đăng ký `ClockProvider` cho Bean Validation factory mà Spring MVC sử dụng.
4. BookingService cũng được inject cùng một Clock.
5. Trong test, `@Primary Clock` cố định được chọn thay Clock production.

Không dùng `TimeZone.setDefault(...)` hoặc sửa global JVM timezone cho test, vì các thay đổi này có thể làm những test khác bị ảnh hưởng.

### 7.5. src/main/java/demo/BookingRequest.java

```java
package demo;

import java.time.Instant;
import java.time.LocalDate;

import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;

public record BookingRequest(

        @NotBlank
        String guestName,

        @NotNull
        @Future
        Instant startsAt,

        @NotNull
        @FutureOrPresent
        LocalDate checkInDate,

        @NotNull
        @Past
        LocalDate birthDate
) {
}
```

Ba kiểu điều kiện:

- `@Future Instant startsAt`: instant bắt đầu phải **sau** ClockProvider instant.
- `@FutureOrPresent LocalDate checkInDate`: ngày nhận phòng không được trước **ngày hiện tại trong zone của ClockProvider**.
- `@Past LocalDate birthDate`: ngày sinh phải trước **ngày hiện tại**, không chấp nhận ngày hôm nay.
- `@NotNull` bổ sung cho từng field bắt buộc vì temporal constraints không dùng để yêu cầu field có giá trị.
- `@NotBlank` bắt buộc guestName có nội dung.

Trong ứng dụng thực tế, có thể không cần cả `startsAt` và `checkInDate` trên cùng request; ví dụ giữ chúng để so sánh Instant và LocalDate khi test. Nếu hệ thống yêu cầu ngày phải nhất quán với Instant và hotel timezone, cần **cross-field business validation** riêng.

### 7.6. src/main/java/demo/BookingService.java

```java
package demo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    private final Clock clock;

    public BookingService(Clock clock) {
        this.clock = clock;
    }

    public record Receipt(
            String status,
            Instant acceptedAt,
            Instant startsAt) {
    }

    public static final class BookingTooSoon
            extends RuntimeException {
    }

    public Receipt book(BookingRequest request) {
        Instant now = clock.instant();

        Instant earliest =
                now.plus(Duration.ofMinutes(30));

        // Cho phép đúng 30 phút; chỉ từ chối sớm hơn.
        if (request.startsAt().isBefore(earliest)) {
            throw new BookingTooSoon();
        }

        return new Receipt(
                "ACCEPTED",
                now,
                request.startsAt()
        );
    }
}
```

**Đây là business validation, không phải @Future.** Nếu `startsAt=2030-01-15T12:00:01Z` với clock frozen ở `12:00:00Z`, Jakarta `@Future` sẽ pass, nhưng BookingService từ chối vì chưa đủ 30 phút.

Service không sử dụng `Instant.now()` tĩnh, nên cùng Clock bean được inject có thể điều khiển cả validation và logic nghiệp vụ. Điều này còn giúp test sau khi thay timezone, near-boundary và retry dễ tái lập.

Trong production, một service method có thể chạy **sau** khi MVC validation đã kiểm tra; thời gian thật tiến lên giữa hai bước. Đây là hành vi thực tế cần giải quyết bằng contract (ví dụ lead-time margin, lưu deadline đã chốt trong transaction), chứ không nên giả vờ hai phép kiểm tra luôn dùng cùng một instant. Fixed Clock giúp test logic, nhưng integration tests khác cần xác minh đặc điểm chạy thật khi phù hợp.

### 7.7. src/main/java/demo/BookingController.java

```java
package demo;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping("/bookings")
    public ResponseEntity<BookingService.Receipt> create(
            @Valid @RequestBody BookingRequest request) {

        BookingService.Receipt receipt =
                service.book(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

Controller không gọi `LocalDate.now()` hay `Instant.now()`. Nó chỉ nhận DTO, kích hoạt Bean Validation và giao nghiệp vụ cho service. Các trường hợp input sai constraint được xử lý qua `MethodArgumentNotValidException` trong Spring MVC; trường hợp request không decode được JSON được xử lý riêng bởi HTTP message converter.

### 7.8. src/main/java/demo/ApiErrorAdvice.java

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record ApiError(
            String code,
            String message,
            List<String> fields) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ApiError(
                        "TEMPORAL_INPUT_INVALID",
                        "Request has invalid fields",
                        fields
                ),
                headers,
                status
        );
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                new ApiError(
                        "UNREADABLE_BODY",
                        "Request body cannot be decoded",
                        List.of()
                ),
                headers,
                status
        );
    }

    @ExceptionHandler(BookingService.BookingTooSoon.class)
    public ResponseEntity<ApiError> tooSoon() {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "BOOKING_TOO_SOON",
                        "Book at least 30 minutes ahead",
                        List.of("startsAt")
                ));
    }
}
```

Ba loại lỗi **khác nhau**:

- `TEMPORAL_INPUT_INVALID`: một hoặc nhiều constraints trên BookingRequest thất bại, HTTP 400.
- `UNREADABLE_BODY`: JSON có lỗi cú pháp/kiểu mà Jackson không deserialize được, HTTP 400.
- `BOOKING_TOO_SOON`: request qua @Future nhưng không thỏa quy tắc lead time của service, HTTP 409 theo contract demo.

Không copy nguyên `FieldError#getRejectedValue()`, Java exception hoặc stack trace ra response. Production có thể tạo mã per-field như `START_MUST_BE_FUTURE`, `DATE_MUST_NOT_BE_PAST` và localized messages bằng `MessageSource`. Điều quan trọng của bài là ClockProvider tác động vào **kết quả validation**, không tự quyết định status/code.

## 8. Unit test ClockProvider: @Past và @Future có ranh giới deterministic

### 8.1. src/test/java/demo/TemporalConstraintUnitTest.java

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TemporalConstraintUnitTest {

    private static final Instant NOW =
            Instant.parse("2030-01-15T12:00:00Z");

    private static final Clock FIXED =
            Clock.fixed(NOW, ZoneOffset.UTC);

    record Probe(
            @Past Instant occurredAt,
            @Future Instant dueAt,
            @FutureOrPresent LocalDate checkInDate,
            @PastOrPresent LocalDate historicalDay) {
    }

    private Set<String> invalidFields(Probe probe) {
        try (ValidatorFactory factory = Validation
                .byDefaultProvider()
                .configure()
                .clockProvider(() -> FIXED)
                .buildValidatorFactory()) {

            return factory.getValidator()
                    .validate(probe)
                    .stream()
                    .map(violation ->
                            violation.getPropertyPath().toString())
                    .collect(Collectors.toSet());
        }
    }

    @Test
    void exactNowFailsStrictPastAndFuture() {
        Probe probe = new Probe(
                NOW,
                NOW,
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 15));

        assertEquals(
                Set.of("occurredAt", "dueAt"),
                invalidFields(probe));
    }

    @Test
    void strictPastAndFutureAcceptOneSecondDistance() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 15));

        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void futureOrPresentDateAcceptsToday() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 14));

        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void yesterdayFailsFutureOrPresentDate() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 14),
                LocalDate.of(2030, 1, 14));

        assertEquals(
                Set.of("checkInDate"),
                invalidFields(probe));
    }

    @Test
    void tomorrowFailsPastOrPresentDate() {
        Probe probe = new Probe(
                NOW.minusSeconds(1),
                NOW.plusSeconds(1),
                LocalDate.of(2030, 1, 15),
                LocalDate.of(2030, 1, 16));

        assertEquals(
                Set.of("historicalDay"),
                invalidFields(probe));
    }

    @Test
    void nullIsValidForTemporalConstraintAlone() {
        Probe probe = new Probe(null, null, null, null);
        assertTrue(invalidFields(probe).isEmpty());
    }

    @Test
    void identicalInstantCanBeDifferentCalendarDay() {
        Instant nearMidnight =
                Instant.parse("2030-01-15T23:30:00Z");

        Clock utc = Clock.fixed(
                nearMidnight, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                nearMidnight,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                LocalDate.of(2030, 1, 15),
                LocalDate.now(utc));

        assertEquals(
                LocalDate.of(2030, 1, 16),
                LocalDate.now(hcm));
    }
}
```

**Bảy unit tests** trên không cần Spring context:

1. Bằng `now` không được `@Past` hoặc `@Future` chấp nhận.
2. Khoảng cách một giây đủ để thỏa strict constraints.
3. `@FutureOrPresent LocalDate` chấp nhận chính hôm nay.
4. Ngày hôm qua không thỏa `@FutureOrPresent`.
5. Ngày mai không thỏa `@PastOrPresent`.
6. Các temporal constraints riêng lẻ chấp nhận null; cần thêm `@NotNull` nếu bắt buộc.
7. Một instant có ngày địa phương khác nhau khi dùng UTC và `Asia/Ho_Chi_Minh`.

Tất cả đều dựa trên mốc `2030-01-15T12:00:00Z` hoặc instant khác được khai báo tường minh; không cần sleep, đồng hồ máy thật, thay system timezone hay tin vào thời gian CI.

**QA ranh giới:** ví dụ dùng ±1 giây thay vì ±1 nanosecond để không tạo test vô tình phụ thuộc precision của một temporal type hoặc provider. Nếu ứng dụng quan trọng đến độ chính xác nanosecond, bổ sung test precision theo data type, DB column và serializer thực tế.

## 9. MockMvc kiểm chứng Spring đã dùng Clock cố định

Unit test ở phần 8 tạo ValidatorFactory riêng, nên **chưa chứng minh** Bean Validation trong MVC dùng cấu hình đó. Phần này tạo một Spring Boot test context thật, thay Clock bean và gửi HTTP-like requests qua `MockMvc`.

### 9.1. src/test/java/demo/BookingMvcTest.java

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(BookingMvcTest.FixedClockConfig.class)
class BookingMvcTest {

    private static final Instant NOW =
            Instant.parse("2030-01-15T12:00:00Z");

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfig {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    Clock clock;

    private ResultActions submit(
            String startsAt, String checkIn, String birth)
            throws Exception {

        String body = """
                {
                  "guestName": "Lan",
                  "startsAt": "%s",
                  "checkInDate": "%s",
                  "birthDate": "%s"
                }
                """.formatted(startsAt, checkIn, birth);

        return mvc.perform(post("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    @Test
    void contextInjectsExactlyTheFixedClock() {
        org.junit.jupiter.api.Assertions.assertEquals(
                NOW, clock.instant());
    }

    @Test
    void futureTimeAndTodayDateAreAccepted()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("ACCEPTED"))
                .andExpect(jsonPath("$.acceptedAt")
                        .value("2030-01-15T12:00:00Z"));
    }

    @Test
    void strictFutureRejectsExactNow()
            throws Exception {
        submit("2030-01-15T12:00:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TEMPORAL_INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("startsAt")));
    }

    @Test
    void strictFutureRejectsOneSecondBefore()
            throws Exception {
        submit("2030-01-15T11:59:59Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("startsAt")));
    }

    @Test
    void futureOrPresentRejectsYesterday()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-14", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("checkInDate")));
    }

    @Test
    void strictPastRejectsBirthDateToday()
            throws Exception {
        submit("2030-01-15T13:00:00Z",
                "2030-01-15", "2030-01-15")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("birthDate")));
    }

    @Test
    void shortLeadTimePassesFutureButFailsBusiness()
            throws Exception {
        submit("2030-01-15T12:00:01Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_TOO_SOON"));
    }

    @Test
    void exactlyThirtyMinutesIsAllowed()
            throws Exception {
        submit("2030-01-15T12:30:00Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.startsAt")
                        .value("2030-01-15T12:30:00Z"));
    }

    @Test
    void oneSecondBeforeThirtyMinutesFails()
            throws Exception {
        submit("2030-01-15T12:29:59Z",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code")
                        .value("BOOKING_TOO_SOON"));
    }

    @Test
    void malformedInstantDoesNotBecomeTemporalViolation()
            throws Exception {
        submit("not-a-time",
                "2030-01-15", "2000-01-01")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void missingDateFailsNotNull()
            throws Exception {
        mvc.perform(post("/bookings")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "guestName": "Lan",
                              "startsAt": "2030-01-15T13:00:00Z",
                              "birthDate": "2000-01-01"
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("checkInDate")));
    }
}
```

**Mười một tests** trong Spring context chứng minh:

- Bean `Clock` test đúng fixed instant.
- `@Future` của Jakarta thực sự bị điều khiển bởi ClockProvider do Boot customizer cấu hình.
- `@FutureOrPresent` và `@Past` dùng ngày tương ứng UTC.
- JSON parsing failure tách khỏi Bean Validation failure.
- Service cũng dùng cùng Clock để kiểm tra 30 phút.
- Đúng ranh giới 30 phút được chấp nhận; trước ranh giới một giây bị từ chối.
- Thiếu `LocalDate` bắt buộc bị `@NotNull` phát hiện.

### Vì sao không chỉ thay TimeZone mặc định?

Đặt `TimeZone.setDefault(TimeZone.getTimeZone("UTC"))` trong test thay đổi **trạng thái toàn JVM**. Nó không freeze time; `ClockProvider` mặc định vẫn chạy theo giờ thật. Khi tests chạy song song, global state có thể khiến hành vi khác nhau. Thay bean Clock riêng của Spring context là cách có phạm vi rõ hơn.

### Có cần @DirtiesContext không?

Với ví dụ này, test dùng fixed clock immutable bean trong context có cấu hình `@Import` tường minh. Không cần thay state bean qua các method, nên thông thường không cần `@DirtiesContext`.

Nếu một suite **thay đổi Clock bean mutable trong runtime test** để “du hành thời gian” giữa test methods, bạn phải quản lý reset, test isolation, parallel execution và Spring context cache. Ưu tiên cố định clock per test class/context hoặc tạo factory riêng cho các case cần nhiều mốc.

## 10. Chạy project và quan sát kết quả

Cần JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

```bash
mvn -q clean test
```

**Kỳ vọng:** 7 unit tests + 11 MockMvc integration tests = **18 tests** pass, Maven exit code 0 khi dependencies và môi trường hợp lệ. Đây là kỳ vọng dựa trên code, **không phải kết quả một lần build đã thực sự chạy**; phải chạy test tại máy/CI để xác nhận.

Khởi động server với đồng hồ thời gian thực (UTC):

```bash
mvn spring-boot:run
```

Request minh họa ở thời điểm thực cần tạo `startsAt` trong tương lai hơn 30 phút. Nếu đang dùng shell POSIX với chương trình `date` phù hợp, bạn có thể tính thời gian tương ứng; không hard-code ngày 2030 trong request production mà giả định nó luôn ở tương lai.

**Cách xem response bằng MockMvc** an toàn hơn cho bài học này vì test cố định thời gian, không phụ thuộc ngày chạy. Một response kỳ vọng khi fixed test clock:

```json
{
  "status": "ACCEPTED",
  "acceptedAt": "2030-01-15T12:00:00Z",
  "startsAt": "2030-01-15T13:00:00Z"
}
```

Một response khi `startsAt` bằng chính `now`:

```json
{
  "code": "TEMPORAL_INPUT_INVALID",
  "message": "Request has invalid fields",
  "fields": ["startsAt"]
}
```

Một response khi `startsAt=2030-01-15T12:00:01Z`:

```json
{
  "code": "BOOKING_TOO_SOON",
  "message": "Book at least 30 minutes ahead",
  "fields": ["startsAt"]
}
```

**Không cố định raw validation messages của Hibernate Validator** trong assertions nếu API không làm chủ chúng. Lỗi `@Future` có thể được dịch bằng MessageSource hoặc thay đổi theo provider/version; test nên kiểm tra field name + stable application code + HTTP status.

## 11. Time zone: Instant, LocalDate và LocalDateTime khác nhau

### 11.1. Instant biểu diễn một thời điểm toàn cục

`Instant.parse("2030-01-15T12:00:00Z")` biểu diễn một instant cụ thể trên dòng thời gian. Khi đổi clock zone nhưng giữ instant, giá trị `clock.instant()` không đổi:

```java
Instant t = Instant.parse("2030-01-15T23:30:00Z");

Clock utc = Clock.fixed(t, ZoneOffset.UTC);
Clock hcm = Clock.fixed(
        t, ZoneId.of("Asia/Ho_Chi_Minh"));

assert utc.instant().equals(hcm.instant());
```

Đây là fragment Java. Múi giờ ảnh hưởng cách diễn giải ngày/giờ địa phương chứ không thay instant.

### 11.2. LocalDate phụ thuộc zone của Clock

Với instant `2030-01-15T23:30:00Z`:

```text
UTC:                 2030-01-15 23:30
Asia/Ho_Chi_Minh:    2030-01-16 06:30
```

Do vậy `LocalDate.now(Clock.fixed(t, UTC))` là ngày 15/01, nhưng với Asia/Ho_Chi_Minh là ngày 16/01. Nếu có `@FutureOrPresent LocalDate checkInDate`, một ngày `2030-01-15` có thể là “hôm nay” theo UTC nhưng **đã là hôm qua** tại TP.HCM.

Ứng dụng phải định nghĩa reference zone cho business rule:

- Hệ thống toàn cầu dựa trên instant tuyệt đối: UTC thường phù hợp.
- Check-in của khách sạn: múi giờ **của khách sạn** thường phù hợp hơn timezone server hoặc timezone browser.
- Ngày làm việc tại quốc gia: zone/cutoff do business policy định nghĩa.
- Đa tenant có zone khác nhau: một ClockProvider **global** với UTC không tự biểu diễn được “today” cho mọi tenant trong cùng request context.

### 11.3. LocalDateTime không chứa time zone/offset

`LocalDateTime.parse("2030-01-15T12:00:00")` biểu diễn ngày/giờ lịch mà **không** chỉ rõ múi giờ. Đừng coi nó tương đương `Instant.parse("2030-01-15T12:00:00Z")`. Một LocalDateTime cần được gắn zone theo rule rõ ràng mới xác định instant.

Nếu API nhận giờ hẹn toàn cầu, thường nên dùng `Instant` hoặc `OffsetDateTime`. Nếu nghiệp vụ cần giờ lịch tại một địa điểm, dùng `LocalDateTime + ZoneId` với quy tắc xử lý DST gaps/overlaps. Test phải bao gồm những ngày đổi giờ của khu vực có DST; UTC không có DST theo cùng cách.

### 11.4. Không sửa system-default timezone để “làm test xanh”

Nếu unit test phụ thuộc múi giờ máy CI, hãy inject `Clock.fixed(..., ZoneId.of(...))` và chỉ rõ `ZoneId`. Thay môi trường chạy cả JVM có thể vô tình khiến các test khác/third-party libraries đổi hành vi.

## 12. DST, leap day và những ranh giới cần kiểm thử

Không chỉ có ngày hôm nay:

| Trường hợp | Ví dụ | Test mong muốn |
| --- | --- | --- |
| Chính xác tại “now” | `@Future Instant = now` | Thất bại |
| Sau now một giây | `@Future Instant = now+1s` | Thành công |
| Ngày hôm nay | `@FutureOrPresent LocalDate` | Thành công |
| Ngày hôm qua | `@FutureOrPresent LocalDate` | Thất bại |
| Thời gian cuối ngày | 23:59:59 → 00:00:00 | Chuyển ngày đúng zone |
| Năm nhuận | 29/02/2028 | Không tự biến thành ngày sai |
| Ngày 31 cuối tháng | 31/01 → 01/02 | LocalDate/YearMonth chính xác |
| DST spring-forward | Giờ địa phương không tồn tại ở một zone | Xử lý gap có chủ đích |
| DST fall-back | Một giờ địa phương xuất hiện hai lần | Xử lý overlap/offset có chủ đích |
| Leap second | ISO time trong phạm vi Java hỗ trợ | Không tự giả lập `:60` là input hợp lệ |
| Clock skew giữa máy | Service A/B lệch vài giây | Policy về tolerance và dữ liệu tin cậy |

### Ví dụ xử lý một ngày theo ZoneId

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate targetDay = LocalDate.of(2030, 3, 31);

// Chuyển ranh giới ngày theo zone thật.
Instant dayStart = targetDay.atStartOfDay(zone).toInstant();
Instant nextDayStart = targetDay.plusDays(1)
        .atStartOfDay(zone).toInstant();

Duration dayLength =
        Duration.between(dayStart, nextDayStart);
```

Đây là fragment. Có những ngày lịch ở zone DST có độ dài **không bằng 24 giờ**. Đừng lấy “start of day + Duration.ofHours(24)” làm ranh giới ngày tiếp theo khi nghiệp vụ nói theo ngày lịch của một vùng.

Ngày chuyển DST cụ thể thay đổi theo zone và năm; test phải dùng một vùng/năm đã được xác nhận bởi tzdb đang sử dụng, không bịa ngày chuyển giờ từ trí nhớ.

## 13. Custom ConstraintValidator đọc ClockProvider đúng cách

Một custom temporal constraint có thể lấy clock từ `ConstraintValidatorContext` thay vì gọi `Instant.now()` tĩnh:

```java
@Override
public boolean isValid(
        Instant value,
        ConstraintValidatorContext context) {

    if (value == null) {
        return true;
    }

    Clock clock = context.getClockProvider().getClock();
    Instant now = clock.instant();

    return value.isAfter(now);
}
```

Đây là **fragment** của một class `ConstraintValidator<MyFuture, Instant>` chưa được định nghĩa trong project runnable. Nó có hành vi giống một constraint strict future đơn giản, chưa hỗ trợ group, payload hoặc annotation metadata; không nên tạo custom annotation chỉ để thay `@Future` khi built-in đáp ứng yêu cầu.

**Ý nghĩa thiết kế:** một custom validator thời gian cần dùng `context.getClockProvider().getClock()` để hưởng cùng mốc do test khai báo. Nếu nó tự gọi `Instant.now()`, unit test với ClockProvider fixed có thể vẫn flaky.

### Các trường hợp không nên dùng constraint thuần

Một quy tắc “đặt phòng trước ít nhất 30 phút trừ khi caller là nhân viên” phụ thuộc actor, account tier hoặc trạng thái availability. Có thể viết custom constraint với DI, nhưng khi cần authorization, external I/O hoặc transaction, **service/domain rule** thường rõ hơn. Validation nên tập trung vào các điều kiện input có thể xác định, business service xử lý invariant và quyết định truy cập.

## 14. ClockProvider và temporal validation tolerance

Jakarta ClockProvider xác định thời điểm tham chiếu; Hibernate Validator còn hỗ trợ **temporal validation tolerance** như một extension của provider. Nó có thể chấp nhận một khoảng sai lệch nhỏ quanh ranh giới vì clock skew giữa các hệ thống.

Ví dụ fragment khi dùng Hibernate Validator API cụ thể:

```java
ValidatorFactory factory = Validation
        .byProvider(HibernateValidator.class)
        .configure()
        .temporalValidationTolerance(Duration.ofMillis(10))
        .clockProvider(() -> fixedClock)
        .buildValidatorFactory();
```

Đoạn này cần imports `org.hibernate.validator.HibernateValidator`, `jakarta.validation.Validation`, `ValidatorFactory`, `java.time.Duration` và một biến `fixedClock` đã định nghĩa. Đây **không phải API portable của mọi Jakarta Validation provider**; nó thuộc Hibernate Validator.

**Điểm cần chú ý:**

- Tolerance có thể làm thay đổi kết quả các input **ngay sát** ranh giới, kể cả input bằng/nhỉnh hơn/nhỉnh kém reference time tùy constraint và semantics.
- Nếu production bật tolerance nhưng unit test không bật, hai môi trường không đồng bộ.
- Tolerance không phải giải pháp thay cho timezone, business lead-time hoặc database race condition.
- Đừng thêm tolerance chỉ để che các test flaky. Trước hết hãy sử dụng fixed clock và định nghĩa boundary rõ.

Project runnable ở phần 7 **không bật tolerance** để các phép thử strict/inclusive có ý nghĩa trực tiếp.

## 15. @WebMvcTest, MockMvc standalone và cấu hình clock

### 15.1. @SpringBootTest

Bài runnable dùng:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(BookingMvcTest.FixedClockConfig.class)
class BookingMvcTest {
    // ...
}
```

Full context tải `ClockConfiguration` và `ValidationConfigurationCustomizer` của ứng dụng; test bổ sung bean fixed clock có `@Primary`. Do MVC và service cùng lấy Clock qua Spring DI, đây là phép thử cả **wiring** lẫn hành vi.

### 15.2. @WebMvcTest

Một MVC slice có thể chỉ tải controller, relevant web infrastructure và một tập auto-configuration. Nếu production `ClockConfiguration` không được tải theo test slice, phải import cấu hình production một cách tường minh hoặc cung cấp test validator đã cấu hình cùng ClockProvider:

```java
@WebMvcTest(BookingController.class)
@Import({
    ClockConfiguration.class,
    FixedClockTestConfig.class
})
class BookingSliceTest {
    // @MockitoBean BookingService service;
}
```

Đây là **fragment minh họa**, không thuộc project runnable vì `FixedClockTestConfig` chưa được khai báo ở đây và cách mocking dependency còn cần hoàn thiện. Ý nghĩa là **test slice không được giả định tự tải mọi @Configuration** từ full application context. Khi mock BookingService, slice có thể kiểm tra `@Future`/`@Past` nhưng không chứng minh logic 30 phút của service thật.

### 15.3. standaloneSetup

Với `MockMvcBuilders.standaloneSetup(...)`, infrastructure không tự tải Spring Boot validation customizer hoặc Clock bean của production. Bạn có thể truyền một `LocalValidatorFactoryBean` tùy biến bằng:

```java
LocalValidatorFactoryBean fixedValidator =
        new LocalValidatorFactoryBean();

fixedValidator.setConfigurationInitializer(
        c -> c.clockProvider(() -> fixedClock));
fixedValidator.afterPropertiesSet();

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new BookingController(
                new BookingService(fixedClock)))
        .setValidator(fixedValidator)
        .build();
```

Đây là **fragment** với imports cần thiết và biến `fixedClock` đã có. Nếu test tạo validator thủ công, hãy destroy nó sau khi dùng để tránh rò lifecycle resources.

**Rủi ro parity:** standalone chỉ chứng minh setup bạn tự dựng, không chứng minh Boot app thực sự dùng same clock. Giữ ít nhất một full-context MockMvc test cho những constraint có ý nghĩa như thời gian hết hạn, booking deadline, token expiry.

## 16. Các lỗi thường gặp

### 16.1. Test lấy ngày từ LocalDate.now() để so sánh

Sai:

```java
LocalDate expected = LocalDate.now();
```

Code chạy sát nửa đêm có thể tạo `expected` từ ngày cũ, trong khi validator chạy sau nửa đêm đã lấy ngày mới. Dùng `LocalDate.now(fixedClock)` và fixed ClockProvider.

### 16.2. Thay Clock bean nhưng @Future vẫn dùng thời gian thật

Đã inject `Clock` vào service nhưng chưa nối nó với ValidatorFactory thông qua `ValidationConfigurationCustomizer` hoặc `LocalValidatorFactoryBean`. Test service pass, MVC validation vẫn dùng ClockProvider mặc định. Cần kiểm chứng bằng **MockMvc request có startsAt bằng exact fixed now**.

### 16.3. Test tạo validator riêng nhưng MVC dùng bean khác

Một unit test với `Validation.byDefaultProvider().configure().clockProvider(...)` pass; điều đó chỉ chứng minh factory vừa tạo. Nếu MockMvc/full app dùng factory khác, provider fixed không có hiệu lực. Test integration bắt buộc dùng MVC infrastructure thật.

### 16.4. Dùng Thread.sleep() để chờ mốc

`Thread.sleep(...)` không tạo đồng hồ deterministic, lại làm test chậm và dễ thất bại trên CI. Dùng `Clock.fixed` để định nghĩa nhiều mốc riêng biệt. Chỉ kiểm thử scheduling thực sự mới cần cơ chế điều khiển thời gian/timer tương thích scheduler.

### 16.5. Quên @NotNull

`@Past`/`@Future` chấp nhận null. Nếu request thiếu field và business yêu cầu bắt buộc, thêm `@NotNull`.

### 16.6. Dùng @Future khi yêu cầu @FutureOrPresent

Với `LocalDate`, hôm nay không thỏa `@Future`; nếu cho phép ngày hôm nay, dùng `@FutureOrPresent`. Nếu business chỉ cho check-in sau cutoff 14:00 tại địa điểm, cần **rule domain theo zone và cutoff**, không chỉ một temporal annotation.

### 16.7. Dùng LocalDateTime như Instant

LocalDateTime không có offset và không xác định thời điểm toàn cục nếu thiếu ZoneId. Nhận `Instant`/`OffsetDateTime` khi API cần định danh instant. Nếu nhận giờ địa phương, làm rõ vùng và DST.

### 16.8. Thay timezone toàn JVM

`TimeZone.setDefault(...)` là global mutable state có thể ảnh hưởng tests song song. Inject Clock cố định với ZoneId tường minh; không dùng thay đổi global để “fix” bug một test.

### 16.9. Dùng @Future để xác nhận booking đã đủ lead time

`@Future` chỉ so strict với hiện tại, không bao hàm 30 phút, thanh toán, availability hoặc quyền. Dùng domain rule/test riêng.

### 16.10. Test không kiểm tra ranh giới bằng

Nếu chỉ test hai input cách nhau nhiều ngày, có thể không phát hiện bug exclusive/inclusive. Hãy kiểm tra **ngay trước, bằng và ngay sau** mốc.

### 16.11. Tin rằng DB CURRENT_TIMESTAMP cũng đã bị cố định

ClockProvider của Jakarta không thay đồng hồ DB. Nếu có query so sánh với `CURRENT_TIMESTAMP` hoặc trigger tạo timestamp, dùng database test setup/dialect phù hợp, không suy từ Spring Clock bean.

### 16.12. Chia sẻ mutable test clock giữa parallel tests

Một `MutableClock` cho phép set instant giữa các test có thể tạo race nếu dùng chung context. Ưu tiên immutable `Clock.fixed`; nếu cần mutable clock, bảo đảm isolation và reset, hoặc disable parallel execution cho những test liên quan.

### 16.13. Clock.systemUTC() vẫn là real time

`Clock.systemUTC()` chọn UTC zone, **không đóng băng thời gian**. Để deterministic, phải dùng `Clock.fixed(...)`, không chỉ đổi timezone.

### 16.14. Không xét độ chính xác thời gian và serialization

`Instant` hỗ trợ nanoseconds; database `TIMESTAMP` có thể lưu millisecond/microsecond, còn JSON serializer có chính sách format. Test yêu cầu exact nanoseconds phải hiểu precision của toàn pipeline. Với boundary 30 phút, dùng test ±1 giây đủ rõ.

## 17. Checklist QA cho bài kiểm thử thời gian

- [ ] Đã định nghĩa “now” là instant + zone có chủ đích.
- [ ] Unit tests dùng `Clock.fixed(...)`, không phụ thuộc real-time.
- [ ] Jakarta Validator được cấu hình `ClockProvider` từ fixed Clock.
- [ ] Spring Boot MVC factory dùng đúng `ValidationConfigurationCustomizer` hoặc `LocalValidatorFactoryBean`.
- [ ] Service dùng inject `Clock`, không gọi static `Instant.now()` nếu logic phải deterministic.
- [ ] Test `@Past`/`@Future` tại quá khứ, bằng now và tương lai.
- [ ] Test `@PastOrPresent`/`@FutureOrPresent` với ngày hôm nay.
- [ ] Có `@NotNull` cho temporal fields bắt buộc.
- [ ] Chọn `Instant` hay `LocalDate` theo semantics thực tế.
- [ ] Test timezone UTC và một zone địa phương phù hợp.
- [ ] Kiểm tra DST/gaps/overlaps nếu sản phẩm sử dụng địa phương có DST.
- [ ] Phân biệt JSON decoding error với constraint error.
- [ ] Tách business lead-time/eligibility khỏi `@Future`.
- [ ] Có integration test qua MockMvc, không chỉ test một ValidatorFactory riêng.
- [ ] Có test đúng ranh giới lead time và một chút trước/sau.
- [ ] Nếu dùng Hibernate temporal tolerance, cấu hình test giống runtime.
- [ ] Tránh thay default timezone/JVM time global.
- [ ] Không dùng sleep để né flaky validation tests.
- [ ] Không giả định ClockProvider kiểm soát clock của database hoặc external service.
- [ ] Nếu nhiều ValidatorFactory, xác nhận factory nào thực sự được MVC sử dụng.

## 18. Kết luận

**Kiểm thử thời gian với ClockProvider hoặc đồng hồ cố định** là cách chuyển một yếu tố không ổn định của môi trường — “bây giờ” — thành đầu vào kiểm soát được.

- `Clock.fixed(...)` tạo thời gian và zone nhất quán, giúp kiểm tra chính xác ranh giới.
- `ClockProvider` là cầu nối chính thức cho các constraint `@Past`, `@Future`, `@PastOrPresent` và `@FutureOrPresent`.
- `ValidationConfigurationCustomizer` hoặc `LocalValidatorFactoryBean` cho phép nối ClockProvider vào Bean Validation factory của Spring.
- Inject cùng `Clock` vào service để business rules như “phải đặt trước 30 phút” cũng deterministic.
- Unit test kiểm tra constraint riêng; MockMvc integration test chứng minh **cấu hình MVC thực tế** đã sử dụng fixed clock, tránh tình huống test pass nhưng runtime dùng đồng hồ khác.
- Timezone, LocalDate/Instant, null, tolerance, DST và database clock là những giới hạn cần được diễn đạt trong contract.

**Thông điệp quan trọng:** không thử làm cho test thời gian ổn định bằng cách “chọn một ngày đủ xa” hoặc “sleep thêm một giây”. Hãy **thiết kế đồng hồ như dependency**, cố định nó trong tests và kiểm tra đủ các ranh giới nghiệp vụ.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 — ClockProvider API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ClockProvider.html)
- [Jakarta Bean Validation 3.0 — Temporal constraints, ClockProvider và validation context](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Bean Validation 3.0 — Configuration#clockProvider](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html)
- [Spring Boot 3.4 — Validation Configuration Customizer](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
- [Spring Boot 3.4 — ValidationConfigurationCustomizer API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework 6.2 — Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework — MVC @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Hibernate Validator 8 — ClockProvider và temporal validation tolerance](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Java 17 — Clock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
