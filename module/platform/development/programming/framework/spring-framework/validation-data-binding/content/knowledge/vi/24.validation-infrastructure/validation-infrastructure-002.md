# ClockProvider cho ràng buộc thời gian trong Spring Framework (Jakarta Validation)

## 1. Vấn đề: “bây giờ” lấy từ đâu?

Khi dùng `@Past`, `@PastOrPresent`, `@Future` hoặc `@FutureOrPresent` để kiểm tra ngày giờ, chương trình phải có một mốc **hiện tại (now)**. Nếu các validator trực tiếp dựa vào đồng hồ máy chủ, cùng một input có thể hợp lệ lúc chạy test nhưng không hợp lệ vài giây sau; việc triển khai trên máy chủ có múi giờ khác cũng có thể làm các giá trị chỉ có **ngày** thay đổi kết quả ở thời điểm sát nửa đêm.

Jakarta Bean Validation giải quyết việc này thông qua **`jakarta.validation.ClockProvider`**: một hợp đồng cung cấp `java.time.Clock` để các ràng buộc thời gian xác định “hiện tại”. Spring Framework tích hợp Jakarta Validation thông qua `LocalValidatorFactoryBean`, nên có thể cấu hình chung một nguồn đồng hồ cho các thao tác xác thực do Spring quản lý.

Các mục tiêu thực hành:

- Hiểu cách `ClockProvider` tác động tới bốn annotation thời gian và ranh giới quá khứ/hiện tại/tương lai.
- Chủ động chọn mốc thời gian và múi giờ cho môi trường chạy, batch xử lý hoặc bài kiểm thử.
- Viết ví dụ Java 17 chạy với đồng hồ cố định để xác minh kết quả ổn định.
- Kết nối `ClockProvider` với validator của Spring, đồng thời phân biệt cấu hình toàn ứng dụng và từng `Validator` riêng.

Ví dụ dùng package **`jakarta.validation.*`**, phù hợp hệ Spring Framework 6 / Spring Boot 3 và Jakarta Validation 3.x. Dự án Spring 5 / Boot 2 dùng namespace cũ **`javax.validation.*`** và cần chọn dependency theo cùng thế hệ; tránh trộn hai namespace.

## 2. Các constraint dùng mốc “hiện tại”

| Annotation | Điều kiện hợp lệ | Giá trị bằng hiện tại có hợp lệ? |
| --- | --- | --- |
| `@Past` | Giá trị nằm trong quá khứ | Không |
| `@PastOrPresent` | Giá trị trong quá khứ hoặc hiện tại | Có |
| `@Future` | Giá trị nằm trong tương lai | Không |
| `@FutureOrPresent` | Giá trị trong tương lai hoặc hiện tại | Có |

**Điểm cần hiểu:** “hiện tại” phụ thuộc vào **kiểu dữ liệu** được kiểm tra.

- Với `Instant`, mốc so sánh là một thời điểm trên trục UTC; ví dụ `2030-06-15T10:00:00Z`.
- Với `LocalDate`, “hôm nay” là **ngày lịch** tính theo `Clock` và múi giờ của nó. Mọi thời điểm trong cùng ngày được xem là cùng ngày khi so sánh dạng `LocalDate`.
- Với `LocalDateTime`, giá trị là ngày giờ địa phương **không mang thông tin offset/zone**; provider dùng múi giờ trong `Clock` để xác định local “now” tương ứng.
- Với `Year` hay `YearMonth`, độ lớn của đơn vị so sánh lần lượt là năm hoặc tháng. Ví dụ, `@FutureOrPresent` trên `Year` có thể chấp nhận toàn bộ năm hiện tại.
- Với `OffsetDateTime` hoặc `ZonedDateTime`, giá trị có offset/zone; cân nhắc sử dụng những kiểu này hoặc `Instant` nếu hệ thống cần biểu diễn thời điểm thực tế trên nhiều múi giờ.

Các constraint thời gian chuẩn cũng có thể dùng cho một số kiểu lịch sử như `java.util.Date`, `Calendar` và các kiểu `java.time` được đặc tả hỗ trợ. Không giả định rằng kiểu ngày giờ tự tạo bất kỳ cũng được hỗ trợ.

**`null` được xem là hợp lệ** với những constraint thời gian chuẩn này. Muốn một trường bắt buộc có giá trị, hãy kết hợp `@NotNull`:

```java
@NotNull
@Future
private Instant startsAt;
```

Đoạn trên chỉ minh họa khai báo một field; nếu `startsAt == null`, `@NotNull` mới là constraint tạo lỗi.

## 3. Hợp đồng `ClockProvider` và các mức cấu hình

API chuẩn có cấu trúc đơn giản:

```java
package jakarta.validation;

public interface ClockProvider {
    java.time.Clock getClock();
}
```

`getClock()` phải trả về một `Clock` khác `null`, và implementation phải an toàn khi nhiều luồng truy cập. `java.time.Clock` cung cấp cả **thời điểm hiện tại** và **múi giờ**. Validator dùng đồng hồ được trả về để đánh giá các constraint thời gian. Một implementation mặc định của Jakarta Validation sử dụng thời gian hệ thống và múi giờ mặc định khi cần.

Một số lựa chọn đồng hồ:

| Cách tạo `Clock` | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `Clock.systemDefaultZone()` | Giờ thực, zone mặc định JVM | Chương trình chỉ vận hành tại một zone đã kiểm soát |
| `Clock.systemUTC()` | Giờ thực, zone UTC | Backend lưu trữ và so sánh instant theo UTC |
| `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` | Giờ thực, zone Việt Nam | Quy tắc theo ngày lịch của thị trường Việt Nam |
| `Clock.fixed(instant, zone)` | Một instant không thay đổi, tại zone đã chọn | Unit/integration test, chạy lại batch theo ngày logic |
| `Clock.offset(base, duration)` | Đồng hồ dịch so với `base` | Kiểm tra luồng nghiệp vụ với thời gian mô phỏng |

`ClockProvider` có thể được cấu hình ở các phạm vi sau:

1. **`ValidatorFactory`:** đặt mặc định cho những `Validator` lấy từ factory đó bằng `Configuration#clockProvider(...)`.
2. **`Validator` cụ thể:** ghi đè qua `factory.usingContext().clockProvider(...).getValidator()`; các validator khác từ factory không bị đổi nguồn thời gian.
3. **`ConstraintValidator` tự định nghĩa:** đọc cùng mốc hiện tại qua `ConstraintValidatorContext#getClockProvider()` thay vì gọi `LocalDate.now()` trực tiếp.

Cùng một `ValidatorFactory` có thể tạo nhiều `Validator` với `ClockProvider` khác nhau. Tuy nhiên, **không thay đổi đồng hồ chia sẻ theo từng HTTP request** trong một singleton mà không có thiết kế an toàn cho concurrent requests.

### Phân biệt `ClockProvider` với các cách lấy thời gian khác

`ClockProvider` **không thay thế toàn bộ đồng hồ của JVM**. Nó không tự thay đổi kết quả của `Instant.now()`, `LocalDate.now()` trong code nghiệp vụ, `CURRENT_TIMESTAMP` tại database, cơ chế scheduling của Spring hoặc timestamp do hệ thống bên ngoài cấp. Để nhất quán, hãy inject cùng một `Clock` vào code nghiệp vụ cần tính “now”; phần Jakarta Validation lấy đồng hồ qua provider đã cấu hình.

## 4. Ví dụ Java 17 chạy độc lập: cố định thời gian và múi giờ

Ví dụ xác thực một lịch đặt chỗ, trong đó:

- `startsAt` phải là một `Instant` tương lai nghiêm ngặt;
- `bookedFor` có thể là ngày hiện tại hoặc ngày tương lai;
- `birthday` phải là ngày quá khứ;
- `finishedAt` có thể là thời điểm hiện tại hoặc trước đó.

Ta cố định **now = 2030-06-15 10:00:00 UTC** và thử lại cùng input với “ngày mai”, sau đó thay đổi zone để quan sát `LocalDate`.

Cấu trúc dự án:

```text
clock-provider-demo/
├── pom.xml
└── src/main/java/ClockProviderDemo.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>clock-provider-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ClockProviderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` là một implementation Jakarta Validation; `jakarta.el` cung cấp nền tảng nội suy thông điệp mặc định. Chương trình không cần Spring để quan sát chính xác hành vi của API chuẩn.

### 4.2. `src/main/java/ClockProviderDemo.java`

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.stream.Collectors;

public class ClockProviderDemo {
    private static final Instant NOW =
            Instant.parse("2030-06-15T10:00:00Z");

    static final class Reservation {
        @Future
        Instant startsAt;

        @FutureOrPresent
        LocalDate bookedFor;

        @Past
        LocalDate birthday;

        @PastOrPresent
        Instant finishedAt;

        Reservation(Instant startsAt, LocalDate bookedFor,
                    LocalDate birthday, Instant finishedAt) {
            this.startsAt = startsAt;
            this.bookedFor = bookedFor;
            this.birthday = birthday;
            this.finishedAt = finishedAt;
        }
    }

    static final class DateOnly {
        @Future
        LocalDate date;

        DateOnly(LocalDate date) {
            this.date = date;
        }
    }

    // Sắp xếp property path để stdout không phụ thuộc
    // vào thứ tự duyệt Set<ConstraintViolation<?>>.
    private static String invalidFields(Validator validator, Object bean) {
        return validator.validate(bean).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        Clock fixedUtc = Clock.fixed(NOW, ZoneOffset.UTC);

        try (ValidatorFactory factory =
                 Validation.byDefaultProvider()
                         .configure()
                         .clockProvider(() -> fixedUtc)
                         .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Reservation valid = new Reservation(
                    NOW.plusSeconds(1),
                    LocalDate.of(2030, 6, 15),
                    LocalDate.of(2000, 1, 1),
                    NOW
            );

            Reservation invalid = new Reservation(
                    NOW,                             // @Future: bằng now
                    LocalDate.of(2030, 6, 14),      // ngày hôm qua
                    LocalDate.of(2030, 6, 15),      // @Past: bằng hôm nay
                    NOW.plusSeconds(1)               // @PastOrPresent: tương lai
            );

            System.out.println("Valid: " + invalidFields(validator, valid));
            System.out.println("Invalid: " + invalidFields(validator, invalid));

            // Chỉ validator này dùng ngày logic 16/06/2030.
            Clock nextDayClock =
                    Clock.fixed(NOW.plusSeconds(24 * 60 * 60), ZoneOffset.UTC);
            Validator nextDayValidator = factory.usingContext()
                    .clockProvider(() -> nextDayClock)
                    .getValidator();
            System.out.println(
                    "Next day: " + invalidFields(nextDayValidator, valid)
            );

            // Cùng một instant, hai zone cho hai ngày lịch khác nhau.
            Instant nearMidnight =
                    Instant.parse("2030-06-15T23:30:00Z");
            Clock utc = Clock.fixed(nearMidnight, ZoneOffset.UTC);
            Clock hcm = Clock.fixed(
                    nearMidnight, ZoneId.of("Asia/Ho_Chi_Minh")
            );
            DateOnly june16 = new DateOnly(LocalDate.of(2030, 6, 16));

            Validator utcValidator = factory.usingContext()
                    .clockProvider(() -> utc)
                    .getValidator();
            Validator hcmValidator = factory.usingContext()
                    .clockProvider(() -> hcm)
                    .getValidator();

            System.out.println(
                    "Date at UTC: " + invalidFields(utcValidator, june16)
            );
            System.out.println(
                    "Date at HCM: " + invalidFields(hcmValidator, june16)
            );
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**stdout dự kiến của chương trình** (không tính log của Maven hoặc provider nếu được ghi vào luồng khác):

```text
Valid: []
Invalid: [birthday, bookedFor, finishedAt, startsAt]
Next day: [bookedFor, startsAt]
Date at UTC: []
Date at HCM: [date]
```

**Giải thích từng dòng:**

- `Valid: []`: bốn trường thỏa mãn bốn constraint tại đúng mốc `NOW`.
- `Invalid: [...]`: mỗi trường vi phạm một ranh giới. `@Future` **không chấp nhận** `startsAt == NOW`; `@Past` **không chấp nhận** ngày sinh trùng ngày hiện tại; `@PastOrPresent` không chấp nhận instant sau now.
- `Next day: [bookedFor, startsAt]`: chính đối tượng `valid` cũ không còn hợp lệ ở hai trường khi mốc logic chuyển sang 16/06. Các điều kiện khác vẫn hợp lệ. Việc ghi đè `ValidatorContext` không thay đổi validator mặc định của factory.
- `Date at UTC: []`: ở `2030-06-15T23:30:00Z`, ngày theo UTC vẫn là **15/06**; ngày `16/06` là tương lai.
- `Date at HCM: [date]`: cùng instant đó là **06:30 ngày 16/06** tại `Asia/Ho_Chi_Minh`; `@Future LocalDate` không chấp nhận chính ngày hiện tại.

Ví dụ trả ra **tên field đã được sort**, không phụ thuộc thứ tự không được bảo đảm của tập `ConstraintViolation`. Đồng hồ cố định khiến phép kiểm thử không phụ thuộc ngày chạy máy và đặc biệt ổn định quanh ranh giới ngày.

### Vì sao chọn cả `Instant` và `LocalDate`?

`Instant` thể hiện thời điểm tuyệt đối, thích hợp cho lịch phát hành, hạn chót UTC, token expiry hoặc thời điểm bắt đầu giao dịch. `LocalDate` thể hiện ngày lịch, thích hợp cho ngày sinh, ngày đặt lịch và ngày kinh doanh. Khi dùng `LocalDate`, quy tắc nghiệp vụ bắt buộc phải xác định **ngày của vùng nào** (UTC, người dùng hay chi nhánh); chỉ ghi “hôm nay” mà không chọn zone có thể gây lỗi.

Nếu input là `LocalTime` thuần, so sánh tương lai/quá khứ có thể không đúng ý tưởng “ngày mai lúc 01:00”, bởi dữ liệu không mang ngày. Dùng `LocalDateTime` với zone được quản lý rõ ràng, `ZonedDateTime` hoặc `Instant` tùy bản chất lịch hẹn.

## 5. Cấu hình `ClockProvider` trong Spring Framework

Spring cung cấp `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` để khởi tạo provider Jakarta Validation và đưa `Validator` vào ApplicationContext. Với Spring Framework 6.x, có thể tùy biến cấu hình factory bằng `setConfigurationInitializer(...)`.

Đoạn dưới đây **dành cho ứng dụng Spring đã có hỗ trợ Bean Validation** (ví dụ Spring Boot 3 với `spring-boot-starter-validation`), không phải chương trình Java độc lập:

```java
import java.time.Clock;
import java.time.ZoneId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class BeanValidationClockConfig {
    @Bean
    Clock applicationClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }

    @Bean
    LocalValidatorFactoryBean validator(Clock applicationClock) {
        LocalValidatorFactoryBean factory = new LocalValidatorFactoryBean();
        factory.setConfigurationInitializer(
                configuration -> configuration.clockProvider(
                        () -> applicationClock
                )
        );
        return factory;
    }
}
```

Ở đây:

1. `applicationClock` là một bean có thể inject vào service nghiệp vụ để tính ngày hiện tại nhất quán.
2. `LocalValidatorFactoryBean` đưa cùng đồng hồ vào các validator thời gian của Jakarta Validation.
3. Khi Spring MVC dùng đúng validator bean này để xử lý `@Valid @RequestBody` hoặc các lệnh validation khác, `@Past` và `@Future` sẽ tham chiếu `ClockProvider` đã cấu hình.
4. Trong môi trường test, có thể thay bean `Clock` bằng `Clock.fixed(...)` để mô phỏng ngày và thời điểm bất kỳ.

Ví dụ DTO trong ứng dụng Spring MVC:

```java
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;

public record CreateReservationRequest(
        @NotNull @Future Instant startsAt
) {}
```

Controller có thể nhận `@Valid @RequestBody CreateReservationRequest`. Khi `startsAt` không thuộc tương lai theo đồng hồ đã cấu hình, Jakarta Validation tạo `ConstraintViolation`; Spring MVC thường chuyển lỗi `@Valid @RequestBody` này thành HTTP 400 qua cơ chế xử lý validation mặc định. Hình dạng JSON lỗi phụ thuộc cấu hình exception handler của dự án.

**Lưu ý về đường đi cấu hình:** nếu dự án chủ động khai báo nhiều validator, custom MVC `WebMvcConfigurer#getValidator()` hoặc validator cho từng binder, phải xác định instance thực sự đang được dùng. Chỉ tồn tại một `Clock` bean hoặc một `ClockProvider` bean trong context **không mặc nhiên chứng minh** mọi validator đã được cấu hình sử dụng nó; đoạn code trên truyền provider vào factory tường minh.

### Khi nào cần override từng `Validator`?

Một batch xử lý lại giao dịch ngày 15/06 có thể cần xem mốc “hôm nay” là 15/06 dù máy chủ đã sang ngày 17/06. Trường hợp này, dùng `factory.usingContext().clockProvider(...)` như ví dụ độc lập để tạo một validator riêng với ngày logic phù hợp cho job. Tránh thay đổi trạng thái đồng hồ toàn ứng dụng khi có yêu cầu đồng thời từ nhiều tenant hoặc múi giờ.

## 6. Dùng trong constraint thời gian tùy chỉnh

Không phải mọi ràng buộc thời gian đều có sẵn annotation. Giả sử cần một ngày giao hàng **không được trước hai ngày kể từ hôm nay**. Trong `ConstraintValidator` của annotation tự định nghĩa, phải lấy đồng hồ từ context để tôn trọng cùng cấu hình test và production.

Đoạn mã sau là **phần thân minh họa của một `ConstraintValidator<YourConstraint, LocalDate>`**, không phải một class độc lập:

```java
@Override
public boolean isValid(
        LocalDate deliveryDate,
        ConstraintValidatorContext context) {

    if (deliveryDate == null) {
        return true; // Dùng @NotNull riêng nếu trường bắt buộc.
    }

    Clock clock = context.getClockProvider().getClock();
    LocalDate today = LocalDate.now(clock);
    LocalDate earliestAllowed = today.plusDays(2);

    return !deliveryDate.isBefore(earliestAllowed);
}
```

Import cần thiết: `java.time.Clock`, `java.time.LocalDate` và `jakarta.validation.ConstraintValidatorContext`. Ở các validator tự tạo, nếu gọi `LocalDate.now()` **không có tham số** thì bạn đã bỏ qua `ClockProvider`, khiến cùng một test có thể dùng hai mốc thời gian khác nhau. Nếu quy tắc là “48 giờ” chứ không phải “hai ngày lịch”, nên so sánh các `Instant`/`Duration` theo ngữ nghĩa thời lượng, không dùng `LocalDate.plusDays(2)`.

## 7. Phân biệt clock, zone, thời lượng và dung sai

### 7.1. Instant không đổi nhưng ngày lịch có thể khác

Một instant được UTC biểu diễn bởi `2030-06-15T23:30:00Z` tương đương 06:30 ngày 16/06 tại Việt Nam. Với `@Future` trên `Instant`, hai zone không làm thay đổi bản thân instant so sánh. Với `@Future` trên `LocalDate`, giá trị hiện tại **phụ thuộc zone**, nên kết quả có thể khác nhau như ví dụ.

Khi xây API đa quốc gia, cần nêu rõ “today” là theo người dùng, chi nhánh hay tổ chức. Không mặc định zone của máy chủ trùng với nghĩa nghiệp vụ.

### 7.2. Khác biệt giữa ngày và khoảng 24 giờ

`LocalDate.plusDays(1)` là **ngày lịch tiếp theo**. Trong các zone có daylight saving time, một ngày lịch có thể dài 23 hoặc 25 giờ. Trong khi đó, `Instant.plus(Duration.ofHours(24))` luôn thêm 24 giờ tuyệt đối. Hãy chọn kiểu dữ liệu đúng: “trước ngày làm việc tiếp theo” là quy tắc theo lịch; “hết hạn sau 24 giờ” là quy tắc theo thời lượng.

### 7.3. Dung sai khi máy chủ lệch đồng hồ

Trên hệ phân tán, request đến muộn vài mili giây và clock skew có thể khiến so sánh sát ranh giới thất bại. Hibernate Validator cung cấp mở rộng **temporal validation tolerance** (ví dụ API `temporalValidationTolerance(Duration.ofMillis(...))` hoặc property `hibernate.validator.temporal_validation_tolerance`), hỗ trợ cấu hình dung sai cho constraint thời gian. Đây là **tính năng của provider Hibernate Validator**, không phải thuộc tính của interface `ClockProvider` chuẩn, và không thay thế việc đồng bộ đồng hồ hay định nghĩa chính xác ranh giới nghiệp vụ.

## 8. Kiểm thử các cạnh quan trọng

Một bộ test cho DTO hoặc validator thời gian nên bao gồm:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Giá trị trước mốc một đơn vị nhỏ | `@Past` hợp lệ; `@Future` không hợp lệ |
| Giá trị **bằng** mốc | Constraint có `OrPresent` hợp lệ; constraint strict không hợp lệ |
| Giá trị sau mốc một đơn vị nhỏ | `@Future` hợp lệ; `@Past` không hợp lệ |
| `null` | Constraint thời gian không tạo lỗi; `@NotNull` tạo lỗi nếu có |
| Mốc gần 00:00 UTC | Kết quả `LocalDate` được xác định theo zone nghiệp vụ |
| Tính toán qua DST | Ngày lịch và 24 giờ được xử lý theo kiểu dữ liệu đúng |
| Job reprocess theo ngày logic | Validator riêng dùng đúng clock dù máy chủ đã sang ngày khác |
| Nhiều luồng / request đồng thời | Provider không bị đổi trạng thái hoặc rò clock giữa các yêu cầu |

Cách kiểm thử ổn định: dùng `Clock.fixed(Instant.parse("..."), ZoneId.of("..."))`; tạo dữ liệu biên bằng `plusSeconds(1)` / `minusSeconds(1)` hoặc `plusDays(1)` tùy kiểu. Không tạo test với `Instant.now()` rồi kỳ vọng một lần kiểm tra khác vẫn thấy cùng một “now”: đồng hồ hệ thống luôn chạy và ranh giới có thể trôi giữa hai lời gọi.

### Các lỗi thiết kế thường gặp

1. **Không cấu hình zone nhưng kiểm tra ngày:** `LocalDate` có thể khác hôm nay theo nghiệp vụ.
2. **Tự viết `LocalDate.now()` trong custom validator:** bỏ qua clock giả lập của test.
3. **Dùng `@Future` cho thời điểm được phép “ngay bây giờ”:** `@Future` strict; cân nhắc `@FutureOrPresent`.
4. **Quên `@NotNull`:** input thiếu ngày giờ vẫn qua constraint thời gian.
5. **Đăng ký một `Clock` bean và giả định validator tự dùng bean này:** cần cấu hình `ClockProvider` của factory/validator đang thực thi.
6. **Đổi global singleton theo request:** có thể gây kết quả sai giữa các luồng; dùng context riêng hoặc thiết kế dữ liệu/zone tường minh.
7. **Dùng `LocalTime` cho một lịch có ngày:** thiếu thông tin về ngày khiến “tương lai” có thể không đúng ngữ cảnh.
8. **Dùng `Clock.fixed` ở production mà không chủ định:** ngày giờ ngừng trôi; hầu hết dữ liệu thực tế cuối cùng sẽ sai điều kiện thời gian.
9. **Trộn Jakarta và javax API:** một annotation dùng sai namespace có thể không được stack hiện tại xử lý như mong đợi.
10. **Nhầm validation clock với database clock:** hai hệ thống có thể dùng mốc giờ khác nhau, gây race ở thao tác gần hạn chót.

## 9. Checklist áp dụng cho một dự án Spring

- [ ] Chọn ngữ nghĩa đúng: instant tuyệt đối, ngày lịch, tháng/năm hay thời lượng.
- [ ] Quy định zone cụ thể cho các quy tắc theo ngày.
- [ ] Chọn `@Past` / `@PastOrPresent` / `@Future` / `@FutureOrPresent` đúng ranh giới.
- [ ] Dùng `@NotNull` nếu input bắt buộc.
- [ ] Đưa đồng hồ vào `LocalValidatorFactoryBean` qua `setConfigurationInitializer`, hoặc cấu hình đúng `ValidatorFactory` ngoài Spring.
- [ ] Inject `Clock` cho business logic cần tính “now” và lấy clock từ context trong `ConstraintValidator` tự tạo.
- [ ] Kiểm thử bằng fixed clock, gồm các biên bằng mốc, sát nửa đêm, zone khác nhau và ngày logic của batch.
- [ ] Xác minh HTTP/API thực sự sử dụng validator đã cấu hình.

**Nguyên tắc cốt lõi:** `ClockProvider` làm cho “hiện tại” trong Jakarta Validation trở thành một dependency được kiểm soát. Bằng cách chọn `Clock`/zone rõ ràng, gắn đúng validator của Spring và kiểm thử với đồng hồ cố định, các ràng buộc thời gian sẽ có kết quả dễ giải thích và tái lập.

## Tài liệu tham khảo

- [Jakarta Validation Specification 3.1 — Temporal constraint validators và ClockProvider](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta Validation API 3.1 — ClockProvider](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ClockProvider.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Hibernate Validator — Reference Guide, ClockProvider and temporal validation tolerance](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/)
