# @Past, @PastOrPresent, @Future và @FutureOrPresent trong Jakarta Validation

> **Module:** Spring Framework – validation-data-binding  
> **Chủ đề cha:** Ràng buộc chuẩn  
> **Phạm vi:** Bốn constraint thời gian chuẩn thuộc `jakarta.validation.constraints`, cách so sánh với “hiện tại”, các kiểu dữ liệu hỗ trợ, `ClockProvider`, tích hợp vào Spring MVC và cách kiểm thử ổn định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích chính xác ý nghĩa của `@Past`, `@PastOrPresent`, `@Future`, `@FutureOrPresent` và điểm khác nhau ở **ranh giới hiện tại**.
- Chọn constraint phù hợp cho ngày sinh, ngày kết thúc, ngày bắt đầu hiệu lực, lịch hẹn và thời hạn.
- Hiểu vì sao `LocalDate` được so sánh theo **ngày**, còn `Instant` được so sánh theo **thời điểm**, với mốc “now” do `ClockProvider` quyết định.
- Không nhầm kiểm tra tính hợp lệ của **giá trị thời gian** với việc chuyển chuỗi ngày thành kiểu Java.
- Kiểm tra được giá trị `null`, các múi giờ khác nhau, trường hợp sát ranh giới và dữ liệu đã hết hạn khi xử lý.
- Viết ví dụ Java 17+ kiểm thử xác định bằng đồng hồ cố định, và dùng các constraint này trong Spring MVC.

## 2. Khái niệm: bốn constraint dựa trên quan hệ với hiện tại

Các annotation nằm trong package:

```java
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
```

Tất cả đều là **constraint của Jakarta Validation**, không phải annotation riêng của Spring. Provider (thường là Hibernate Validator trong Spring Boot) thực hiện so sánh; annotation bản thân nó chỉ cung cấp metadata để validator chạy khi được kích hoạt.

| Annotation | Điều kiện với giá trị khác null | Bao gồm hiện tại? | Tình huống thường gặp |
| --- | --- | --- | --- |
| `@Past` | Giá trị **trước** hiện tại | Không | Sự kiện đã xảy ra trước hôm nay, thời điểm đã hoàn thành |
| `@PastOrPresent` | Giá trị **trước hoặc bằng** hiện tại | Có | Ngày sinh không được sau hôm nay, ngày ghi nhận đến hiện tại |
| `@Future` | Giá trị **sau** hiện tại | Không | Thời điểm chạy job phải ở tương lai, lịch hẹn phải bắt đầu sau bây giờ |
| `@FutureOrPresent` | Giá trị **sau hoặc bằng** hiện tại | Có | Ngày bắt đầu hiệu lực từ hôm nay, hạn xử lý không sớm hơn hôm nay |

Mô hình trực quan với `now` là mốc tham chiếu:

```text
Thời gian:  quá khứ  ----------  NOW  ----------  tương lai

@Past                  < NOW
@PastOrPresent        <= NOW
@Future                 > NOW
@FutureOrPresent       >= NOW

Riêng giá trị null: cả 4 constraint đều coi là hợp lệ.
```

Ký hiệu `<`, `<=`, `>`, `>=` ở đây diễn tả quan hệ thời gian, **không có nghĩa mọi kiểu Java đều trực tiếp gọi toán tử số học**. Provider sẽ dùng validator tương ứng với kiểu dữ liệu.

### 2.1. Hiện tại không phải lúc nào cũng là một nano giây

Giả sử đồng hồ kiểm tra đang ở **2026-11-05 15:00:00** tại `Asia/Ho_Chi_Minh`:

| Kiểu giá trị | Giá trị được coi là hiện tại | Diễn giải |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | Toàn bộ **ngày** 5/11 được xem là ngày hôm nay |
| `YearMonth` | `2026-11` | **Cả tháng** 11 là tháng hiện tại |
| `Year` | `2026` | **Cả năm** 2026 là năm hiện tại |
| `LocalDateTime` | `2026-11-05T15:00:00` | So sánh đến mức ngày và giờ địa phương theo đồng hồ tham chiếu |
| `Instant` | `2026-11-05T08:00:00Z` | So sánh các thời điểm trên trục thời gian UTC |

Do đó, `@Future LocalDate` **không chấp nhận hôm nay**, kể cả hôm nay vẫn còn nhiều giờ; còn `@FutureOrPresent LocalDate` **chấp nhận hôm nay**. Với `@Future Instant`, thời điểm phải **muộn hơn** thời điểm kiểm tra, không chỉ khác ngày.

Trong đặc tả, ý nghĩa của từ “present” được định nghĩa **tương ứng với kiểu dữ liệu**; đây là lý do cần chọn kiểu Java đúng ngay từ đầu.

## 3. Khác nhau ở ranh giới: có và không có `OrPresent`

Ví dụ các giá trị `LocalDate` khi `today = 2026-11-05`:

| Giá trị | `@Past` | `@PastOrPresent` | `@Future` | `@FutureOrPresent` |
| --- | --- | --- | --- | --- |
| `2026-11-04` | Đạt | Đạt | Không đạt | Không đạt |
| `2026-11-05` | Không đạt | Đạt | Không đạt | Đạt |
| `2026-11-06` | Không đạt | Không đạt | Đạt | Đạt |
| `null` | Đạt | Đạt | Đạt | Đạt |

Lựa chọn sai một chữ `OrPresent` có thể thay đổi nghiệp vụ:

- Ngày sinh `LocalDate` có thể là hôm nay: dùng `@PastOrPresent`.
- Ngày bắt đầu hiệu lực cho phép có hiệu lực **hôm nay**: dùng `@FutureOrPresent`.
- Lịch hẹn phải đặt cho **ngày mai trở đi**: dùng `@Future LocalDate`.
- Lịch hẹn phải sau **thời điểm hiện tại** ngay trong cùng ngày: dùng `@Future Instant`, `OffsetDateTime` hoặc kiểu có ngữ nghĩa thời điểm rõ ràng; `LocalDate` không đủ thông tin.

Hai thuộc tính chung quan trọng của bốn annotation là `message`, `groups`, `payload`. Không có thuộc tính `zone`, `timezone`, `pattern` hay `inclusive` để chỉnh trực tiếp trên annotation; muốn điều chỉnh nguồn thời gian tham chiếu, sử dụng `ClockProvider`.

## 4. Khai báo trên DTO đúng mục đích

### 4.1. Ngày sinh và ngày hiệu lực

```java
import java.time.LocalDate;

import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;

public record CustomerRegistration(
        @NotNull
        @PastOrPresent
        LocalDate birthDate,

        @NotNull
        @FutureOrPresent
        LocalDate validFrom) {
}
```

Đây là **DTO minh họa**, chưa phải ứng dụng độc lập.

- `birthDate` bắt buộc và không được vượt quá hôm nay; ngày hôm nay vẫn hợp lệ.
- `validFrom` bắt buộc và không thể là ngày trước hôm nay; hôm nay hợp lệ.
- `@NotNull` rất quan trọng vì `@PastOrPresent` và `@FutureOrPresent` **không tự cấm null**.

Khi yêu cầu sinh nhật của người dùng phải thuộc quá khứ ít nhất một ngày, thay `@PastOrPresent` bằng `@Past`. Tuy nhiên, nếu phải kiểm tra **đủ 18 tuổi**, `@Past` hoàn toàn chưa đủ: phải có quy tắc tính tuổi dựa trên `LocalDate` và ngày hiện tại ở timezone nghiệp vụ.

### 4.2. Thời điểm có giờ, phút và múi giờ

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.Past;

public record MeetingRequest(
        @Future Instant beginsAt,
        @Past OffsetDateTime recordedAt) {
}
```

Khi biểu diễn một thời điểm tuyệt đối, `Instant` thường là lựa chọn đơn giản: nó không bị mơ hồ bởi timezone client. `OffsetDateTime` mang offset của thời gian cục bộ; nếu cần cả tên vùng và quy tắc DST, xem `ZonedDateTime`.

Đoạn code trên chỉ khai báo constraint. Nó không thay thế logic xem lịch của nhiều người có trùng nhau không, thời lượng cuộc họp có hợp lệ không, hay user có quyền đặt lịch không.

### 4.3. Các kiểu chuẩn được hỗ trợ

Theo Jakarta Validation, bốn constraint hỗ trợ các nhóm kiểu dưới đây:

| Họ kiểu | Ví dụ | Lưu ý khi chọn |
| --- | --- | --- |
| Legacy | `java.util.Date`, `Calendar` | Có ngữ nghĩa thời điểm; `Calendar` mang timezone; cần cảnh giác khi nhận dữ liệu ngày thuần |
| Thời điểm | `Instant`, `OffsetDateTime`, `ZonedDateTime` | Phù hợp khi so sánh một thời điểm trên trục thời gian |
| Ngày/giờ cục bộ | `LocalDate`, `LocalDateTime`, `LocalTime` | Không mang offset riêng; cần timezone của `ClockProvider` để xác định “now” |
| Độ hạt lịch khác | `Year`, `YearMonth`, `MonthDay` | “Hiện tại” theo độ hạt tương ứng, không phải luôn một instant |
| Calendar không theo ISO | `HijrahDate`, `JapaneseDate`, `MinguoDate`, `ThaiBuddhistDate` | Khi thật sự dùng lịch tương ứng |

**Không** đặt bốn constraint trực tiếp lên `String` chứa ngày, `Long` timestamp hay kiểu số khác rồi trông đợi provider tự parse. Nếu constraint không có validator hỗ trợ kiểu được khai báo, quá trình kiểm tra có thể ném `UnexpectedTypeException` (một loại `ConstraintDeclarationException`/validation error do kiểu không tương thích), thay vì trả một violation dữ liệu thông thường.

Ví dụ cần tránh:

```java
@Future
private String scheduledAt; // Không phải temporal type được hỗ trợ.
```

Cách đúng là chuyển chuỗi đầu vào thành kiểu thời gian phù hợp **trước**, rồi mới validate.

## 5. “Now” đến từ đâu? `ClockProvider`

Jakarta Validation không yêu cầu mỗi validator tự gọi `LocalDate.now()` hoặc `Instant.now()`. Các validator thời gian lấy mốc hiện tại từ **`jakarta.validation.ClockProvider`** gắn với `ValidatorFactory` hoặc `Validator`.

```java
import java.time.Clock;
import jakarta.validation.ClockProvider;

public final class FixedClockProvider implements ClockProvider {

    private final Clock clock;

    public FixedClockProvider(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Clock getClock() {
        return clock;
    }
}
```

Đây là **mảnh class minh họa**; bản Java 17 hoàn chỉnh ở mục 7 dùng lambda `() -> fixedClock` thay cho một class riêng.

- **Mặc định:** provider sử dụng thời gian hệ thống JVM và timezone mặc định khi cần chuyển sang local date/time.
- **Cấu hình riêng:** có thể cung cấp `Clock.fixed(...)`, `Clock.offset(...)`, hoặc `Clock.system(ZoneId...)` theo nhu cầu.
- **Test:** clock cố định khiến kết quả không biến đổi theo ngày/giờ thực lúc chạy CI.
- **Ứng dụng đa múi giờ:** timezone của clock tác động tới cách hiểu “hôm nay” cho `LocalDate`, `LocalDateTime` hoặc `LocalTime`; cần một chính sách timezone cụ thể.
- **Custom constraint:** có thể đọc `context.getClockProvider().getClock()` trong `ConstraintValidator` tự viết để đồng bộ cùng nguồn thời gian.

Tách biệt hai vấn đề: `ClockProvider` quyết định **mốc so sánh**, còn `@DateTimeFormat` và `@JsonFormat` quyết định **cách biểu diễn chuỗi** ở các đường xử lý khác nhau.

### 5.1. Ví dụ vùng giờ ảnh hưởng ngày hiện tại

Cùng một instant `2026-11-05T23:30:00Z`:

```text
UTC                 = 2026-11-05, 23:30
Asia/Ho_Chi_Minh    = 2026-11-06, 06:30
```

Nếu giá trị là `LocalDate.of(2026, 11, 5)`:

- Với clock ở UTC, đó là **hôm nay**, đạt `@PastOrPresent` và `@FutureOrPresent`.
- Với clock ở Asia/Ho_Chi_Minh, đó là **hôm qua**, đạt `@Past` và không đạt `@FutureOrPresent`.

Nếu kiểu dữ liệu là `Instant`, cùng một thời điểm có thứ tự trên timeline không thay đổi khi chuyển timezone. Hãy quyết định “hôm nay theo vùng nào?” ở biên ứng dụng, chứ không dựa vào timezone tình cờ trên một server khác.

## 6. Ranh giới bằng nhau và giá trị null

### 6.1. Kiểm tra khi bằng hiện tại

Với đồng hồ cố định:

```java
Instant now = fixedClock.instant();
```

Cùng một instant `now`:

- `@Past` **không đạt**, vì không trước mốc.
- `@PastOrPresent` **đạt**, vì bằng mốc.
- `@Future` **không đạt**, vì không sau mốc.
- `@FutureOrPresent` **đạt**, vì bằng mốc.

Trong ứng dụng đang chạy, việc tạo `Instant.now()` trước, rồi vài mili giây sau mới gọi validator, khiến giá trị đó đã là quá khứ. Bởi vậy **không** dùng request thật và kỳ vọng so sánh đúng tuyệt đối ở một thời điểm “now” đang chạy liên tục. Để kiểm thử toán tử biên, hãy cố định clock cho cả dữ liệu đầu vào và validator.

### 6.2. Cả bốn constraint đều chấp nhận `null`

Đây là nguyên tắc tiêu chuẩn:

```java
import java.time.LocalDate;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;

public record OptionalAndRequiredDates(
        @Future LocalDate optionalDeadline,
        @NotNull @Future LocalDate mandatoryDeadline) {}
```

- `optionalDeadline = null` hợp lệ theo `@Future`.
- `mandatoryDeadline = null` bị `@NotNull` từ chối, dù `@Future` không báo lỗi.
- Nếu request JSON không có một trường và Jackson tạo giá trị null, việc trường đó có lỗi còn phụ thuộc `@NotNull` và cơ chế deserialize tương ứng.

Mọi ràng buộc thời gian đều có thể kết hợp với `groups` để dùng theo từng ngữ cảnh. Nhưng group không thay thế `@NotNull`, cũng không làm annotation tự chạy khi đối tượng mới được tạo.

## 7. Chương trình Java 17+ chạy được: kiểm chứng cả bốn constraint

Ví dụ sau dùng **Jakarta Validation API + Hibernate Validator**. Kết quả hoàn toàn xác định vì `ValidatorFactory` được cấu hình bằng một `Clock.fixed`, tham chiếu tới **2026-11-05T08:00:00Z**, tương đương **15:00 tại Asia/Ho_Chi_Minh**.

### 7.1. Cấu trúc

```text
temporal-validation/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── temporal/
                    └── TemporalValidationDemo.java
```

Tệp `pom.xml` cho Java 17 và Hibernate Validator 8 (triển khai Jakarta Validation 3.0):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>temporal-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.1.Final</version>
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
    </plugins>
  </build>
</project>
```

Provider cung cấp các validator chuẩn; dependency EL phục vụ nội suy thông báo mặc định. Trong dự án Spring Boot hiện hữu, nên để BOM của Boot quản lý phiên bản thư viện thay vì chép các version cố định.

Tệp `src/main/java/example/temporal/TemporalValidationDemo.java`:

```java
package example.temporal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;

public final class TemporalValidationDemo {

    public record DateValues(
            @Past LocalDate beforeToday,
            @PastOrPresent LocalDate throughToday,
            @Future LocalDate afterToday,
            @FutureOrPresent LocalDate fromToday) {}

    public record InstantValues(
            @Past Instant strictlyBefore,
            @PastOrPresent Instant atOrBefore,
            @Future Instant strictlyAfter,
            @FutureOrPresent Instant atOrAfter) {}

    public record RequiredDeadline(
            @NotNull @Future LocalDate deadline) {}

    private static String invalidFields(Validator validator, Object value) {
        return validator.validate(value).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-11-05T08:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .clockProvider(() -> fixedClock)
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            LocalDate today = LocalDate.now(fixedClock);
            LocalDate yesterday = today.minusDays(1);
            LocalDate tomorrow = today.plusDays(1);
            Instant now = fixedClock.instant();

            DateValues valid = new DateValues(
                    yesterday, today, tomorrow, today);
            DateValues invalid = new DateValues(
                    today, tomorrow, today, yesterday);

            InstantValues exactBoundary = new InstantValues(
                    now, now, now, now);
            DateValues allNulls = new DateValues(
                    null, null, null, null);

            System.out.println("today=" + today);
            System.out.println("valid-date-count="
                    + validator.validate(valid).size());
            System.out.println("invalid-date-fields="
                    + invalidFields(validator, invalid));
            System.out.println("instant-boundary-fields="
                    + invalidFields(validator, exactBoundary));
            System.out.println("all-null-count="
                    + validator.validate(allNulls).size());
            System.out.println("required-null-count="
                    + validator.validate(new RequiredDeadline(null)).size());
        }
    }
}
```

Chạy ở thư mục `temporal-validation`:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.temporal.TemporalValidationDemo
```

**Các dòng stdout của chương trình** (không tính log Maven/provider):

```text
today=2026-11-05
valid-date-count=0
invalid-date-fields=afterToday,beforeToday,fromToday,throughToday
instant-boundary-fields=strictlyAfter,strictlyBefore
all-null-count=0
required-null-count=1
```

Phân tích kết quả:

1. Ngày địa phương của clock là `2026-11-05`, vì 08:00Z tương ứng 15:00 ở Việt Nam.
2. Trong `valid`: hôm qua đạt `@Past`, hôm nay đạt `@PastOrPresent`, ngày mai đạt `@Future`, hôm nay đạt `@FutureOrPresent`.
3. Trong `invalid`: mọi field cố tình đặt sai phía ranh giới; chương trình **sắp xếp tên field** vì `Set<ConstraintViolation>` không đảm bảo thứ tự.
4. Với `InstantValues` có bốn field cùng bằng `now`, **chỉ** `strictlyBefore` và `strictlyAfter` vi phạm; hai constraint có `OrPresent` cho phép bằng mốc.
5. Khi tất cả field null, bốn temporal constraint không tạo violation.
6. `@NotNull @Future` trên `deadline=null` tạo đúng một violation từ `@NotNull`; `@Future` không bị coi là lỗi.
7. `try-with-resources` đóng `ValidatorFactory` sau khi dùng. Trong Spring Boot, lifecycle của factory thường do framework quản lý.

**Lưu ý:** Ví dụ này chứng minh hành vi Jakarta Validation trực tiếp, không dựa vào server đang ở năm nào. `ClockProvider` được cấp khi tạo factory; nếu chỉ dùng `LocalDate.now(fixedClock)` để chuẩn bị dữ liệu nhưng validator sử dụng clock hệ thống, kết quả có thể khác.

## 8. Kiểm chứng bản chất “hôm nay” bằng Java thuần

Bạn có thể chạy ví dụ sau chỉ với JDK 17+, không cần Maven hay Jakarta Validation. Mục đích là **kiểm tra cơ sở thời gian** mà provider dùng, không thay thế việc chạy chương trình ở mục 7.

Tệp `ClockBoundaryCheck.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class ClockBoundaryCheck {
    public static void main(String[] args) {
        Instant sameInstant = Instant.parse("2026-11-05T23:30:00Z");
        Clock utc = Clock.fixed(sameInstant, ZoneId.of("UTC"));
        Clock hcm = Clock.fixed(
                sameInstant, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(LocalDate.now(utc));
        System.out.println(LocalDate.now(hcm));
        System.out.println(sameInstant);
    }
}
```

```bash
javac ClockBoundaryCheck.java
java ClockBoundaryCheck
```

Stdout:

```text
2026-11-05
2026-11-06
2026-11-05T23:30:00Z
```

Hai local date khác nhau vì timezone, trong khi `Instant` không đổi. Khi định nghĩa “hôm nay”, hãy xác định vùng giờ được dùng cho kiểm tra và hiển thị trong toàn hệ thống.

## 9. Tích hợp vào Spring MVC / Spring Boot

Trong Spring Boot 3.x (Spring Framework 6.x), các annotation sử dụng namespace `jakarta.validation`. Một dự án MVC điển hình cần:

```xml
<!-- Dependency fragment trong pom.xml đã dùng Spring Boot BOM/parent -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

`starter-validation` cung cấp các thành phần để Spring kích hoạt Jakarta Validation qua provider. Chỉ có `starter-web` không phải lúc nào cũng đủ. Khi sử dụng `@Valid` trên DTO request, framework kiểm tra các constraint sau khi dữ liệu được chuyển thành kiểu Java.

### 9.1. Ví dụ controller và DTO hoàn chỉnh

Trong một dự án Spring Boot 3.x Java 17+ có hai starter trên, đặt tệp `src/main/java/example/temporalweb/TemporalWebApplication.java`:

```java
package example.temporalweb;

import java.time.LocalDate;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.FutureOrPresent;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PastOrPresent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TemporalWebApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemporalWebApplication.class, args);
    }

    public record AccountDates(
            @NotNull
            @PastOrPresent
            LocalDate birthDate,

            @NotNull
            @FutureOrPresent
            LocalDate activeFrom) {}

    @RestController
    @RequestMapping("/accounts")
    public static class AccountController {

        @PostMapping("/dates")
        public Map<String, String> create(
                @Valid @RequestBody AccountDates request) {
            return Map.of(
                    "birthDate", request.birthDate().toString(),
                    "activeFrom", request.activeFrom().toString());
        }
    }
}
```

Đặt class tại package/path đã chỉ rõ và chạy server theo hệ build của dự án:

```bash
./mvnw spring-boot:run
```

Hoặc, với dự án Gradle:

```bash
./gradlew bootRun
```

**Lưu ý:** Các lệnh wrapper trên chỉ tồn tại nếu dự án thực sự có wrapper tương ứng; ví dụ ứng dụng phải được đưa vào một dự án Spring Boot đã cấu hình.

Các HTTP request minh họa, **giả sử thời điểm chạy nằm trong tháng 11 năm 2026** và timezone của validator nhất quán:

```bash
curl -i -X POST http://localhost:8080/accounts/dates -H "Content-Type: application/json" -d '{"birthDate":"2000-01-01","activeFrom":"2030-01-01"}'
curl -i -X POST http://localhost:8080/accounts/dates -H "Content-Type: application/json" -d '{"birthDate":"2030-01-01","activeFrom":"2000-01-01"}'
```

- Request thứ nhất hợp lệ, trả HTTP **200** với JSON có `birthDate` và `activeFrom` (thứ tự key không được cam kết).
- Request thứ hai vi phạm `@PastOrPresent` trên `birthDate` và `@FutureOrPresent` trên `activeFrom`, thường trả HTTP **400** trước khi phần thân controller thực thi.
- Payload lỗi HTTP cụ thể tùy cấu hình Spring Boot, `@ControllerAdvice`, Problem Details và handler hiện tại. Đừng giả định JSON lỗi nhất thiết có một cấu trúc cố định.

### 9.2. Hai bước khác nhau: parse rồi mới validate

```text
JSON request
  |
  v
Jackson HttpMessageConverter -> Java LocalDate
  |                                |
  | Sai cú pháp/kiểu               v
  +-- 400 do deserialize     Jakarta Validator / @Valid
                                   |
                                   | @PastOrPresent / @FutureOrPresent
                                   v
                            Controller xử lý
```

Ví dụ input `"birthDate":"not-a-date"` có thể lỗi **deserialize** trước khi constraint được đánh giá. Input `"birthDate":"2030-01-01"` là ngày hợp lệ về cú pháp, nhưng **không đạt ràng buộc thời gian** khi mốc hiện tại là năm 2026.

`@DateTimeFormat` điều khiển formatting/binding chuỗi từ query/path/form trong Spring; JSON `@RequestBody` thường do Jackson xử lý (có thể cấu hình `@JsonFormat`). Bốn annotation `@Past*`/`@Future*` không định nghĩa pattern chuỗi. Cũng không vì annotation tồn tại trên DTO mà `new AccountDates(...)` sẽ tự ném lỗi: phải thực thi validation.

Nếu cần trả lỗi có `field`, `code`, `message`, hãy chọn cách xử lý `MethodArgumentNotValidException`/error response phù hợp với ứng dụng. Không lộ dữ liệu nhạy cảm hoặc phụ thuộc thứ tự message mặc định của provider.

## 10. Cấu hình timezone nghiệp vụ trong Spring Boot

Với ứng dụng nhiều server hoặc người dùng nhiều vùng giờ, `LocalDate` là “ngày theo vùng nào?” nên được quyết định rõ. Trong Spring Boot **3.x**, có thể cấu hình `ClockProvider` cho Bean Validation bằng một `ValidationConfigurationCustomizer` bean.

Mảnh code đặt trong class `@Configuration` của dự án:

```java
import java.time.Clock;
import java.time.ZoneId;

import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TemporalValidationConfig {

    @Bean
    ValidationConfigurationCustomizer validationClock() {
        Clock clock = Clock.system(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        return configuration ->
                configuration.clockProvider(() -> clock);
    }
}
```

Đây là **class cấu hình cho dự án Spring Boot 3.x**, không phải ứng dụng chạy độc lập. Spring Boot dùng customizer khi tạo `ValidatorFactory` tự cấu hình. Khi cần test, có thể thay Clock bằng một bean/test configuration cung cấp `Clock.fixed(...)`.

**Điểm cần nhớ:** Cấu hình clock này phục vụ **temporal validation**. Nó không tự đổi timezone Jackson serialize, timezone mặc định JVM, timezone JDBC hay cách lưu cột timestamp trong database. Những cơ chế đó phải được kiểm soát riêng nếu bài toán yêu cầu.

Trong ứng dụng Spring Framework thuần (không có tiện ích Boot), `LocalValidatorFactoryBean#setConfigurationInitializer(...)` cho phép chỉnh cấu hình Jakarta Validation, bao gồm `clockProvider`. Không đăng ký song song nhiều ValidatorFactory tùy ý rồi mặc định cho rằng MVC sẽ dùng đúng instance bạn muốn; kiểm tra wiring thực tế của application context.

## 11. Kiểu thời gian nào phù hợp với từng ràng buộc nghiệp vụ?

### 11.1. Ngày sinh

```java
@NotNull
@PastOrPresent
private LocalDate birthDate;
```

Nếu chấp nhận sinh trong ngày hôm nay thì `@PastOrPresent` hợp lý. Nhưng “đủ tuổi” cần so tuổi dựa trên ngày sinh và ngày hiện tại; “không quá 120 tuổi” cũng không được bảo đảm bởi annotation này.

### 11.2. Thời điểm chạy tác vụ

```java
@NotNull
@Future
private Instant scheduledAt;
```

Nếu job phải chạy sau mốc hiện tại, `@Future` phù hợp để sàng lọc đầu vào. Tuy nhiên, có một **khoảng thời gian** giữa validation và thực thi. Một thời điểm hợp lệ khi nhận request có thể đã qua khi job được đưa vào queue hoặc commit. Do đó scheduler còn phải có chính sách khi deadline vượt qua, re-check khi xử lý và retry thích hợp.

### 11.3. Ngày bắt đầu hợp đồng

```java
@NotNull
@FutureOrPresent
private LocalDate effectiveFrom;
```

Nếu hợp đồng có thể bắt đầu **hôm nay**, `@FutureOrPresent` hợp lý. Nếu hợp đồng chỉ có thể bắt đầu từ ngày mai, chọn `@Future LocalDate`. Nhưng nếu quy tắc là “từ 09:00 hôm nay trở đi”, phải có kiểu chứa cả giờ và timezone; `LocalDate` không phân biệt 08:59 với 09:01.

### 11.4. Bản ghi đã hoàn thành

```java
@Past
private Instant completedAt;
```

Nếu `completedAt` có thể vừa bằng mốc xử lý, `@PastOrPresent` chính xác hơn về ngữ nghĩa. Nếu field này là optional khi chưa xong, cho null hợp lệ là chủ đích; nếu bắt buộc lúc đóng giao dịch thì thêm `@NotNull` ở DTO đóng giao dịch hoặc sử dụng validation group phù hợp.

### 11.5. Quan hệ giữa hai thời điểm

Các constraint built-in so sánh **mỗi giá trị với now**, không so sánh hai field với nhau:

```java
@FutureOrPresent LocalDate startDate;
@FutureOrPresent LocalDate endDate;
```

Hai trường trên có thể đều không trước hôm nay nhưng vẫn có `endDate < startDate`. Muốn bắt buộc `startDate <= endDate` thì phải thêm ràng buộc cấp class, custom validator hoặc xử lý ở service. Không chọn `@Future` trên endDate và kết luận endDate chắc chắn sau startDate.

## 12. Độ chính xác và trường hợp sát thời điểm hiện tại

### 12.1. `LocalDate` khác `Instant`

Giả sử hiện tại là `2026-11-05T15:00+07:00`:

- `@Future LocalDate.of(2026,11,5)` **không đạt** vì đó là ngày hiện tại.
- `@Future Instant.parse("2026-11-05T09:00:00Z")` **đạt** vì tương đương 16:00 tại Việt Nam, muộn hơn 15:00.
- `@PastOrPresent LocalDate.of(2026,11,5)` **đạt** vì cho phép ngày hôm nay.
- `@PastOrPresent Instant.parse("2026-11-05T09:00:00Z")` **không đạt** vì đó là thời điểm 16:00, muộn hơn mốc 15:00.

Mọi so sánh này giả định cùng một clock cố định 15:00 theo múi giờ đã cho.

### 12.2. `LocalTime` và `LocalDateTime` có giới hạn

`LocalTime` **không có ngày**. Nếu bạn muốn kiểm tra giờ hẹn **ngày mai** lúc 08:00, một `@Future LocalTime` riêng lẻ có thể đánh giá sai vì chỉ so với **giờ hiện tại hôm nay**. Với lịch hẹn thực, dùng `LocalDateTime` cùng ngữ cảnh timezone xác định, hoặc tốt hơn là `Instant`/`OffsetDateTime` khi request biểu diễn một thời điểm tuyệt đối.

`LocalDateTime` cũng **không mang zone/offset**. Cùng giá trị `2026-11-05T10:00` tại Tokyo và Hà Nội là hai instant khác nhau nếu được quy chiếu tới hai zone. Không giả định một `LocalDateTime` có thể so sánh toàn cầu nếu chưa xác định timezone nghiệp vụ.

### 12.3. Giờ mùa hè (DST)

Các vùng như `Europe/Paris` có các ngày đổi giờ; có local time không tồn tại hoặc bị lặp. `ZonedDateTime` mang zone rules, còn `Instant` loại bỏ nhập nhằng của một thời điểm tuyệt đối. Đừng đổi ngày/giờ client thành `LocalDateTime` rồi bỏ qua zone khi định lịch qua nhiều quốc gia.

### 12.4. Clock skew và thời gian xử lý

Trong hệ thống phân tán, đồng hồ của client và server có thể lệch vài mili giây hoặc vài giây. Constraint `@Future` trên timestamp sát thời điểm hiện tại có thể từ chối dù client nghĩ nó còn ở tương lai. Có các cách xử lý:

- Định nghĩa rõ server là nguồn thời gian chuẩn cho kiểm tra.
- Thiết kế API với biên an toàn, ví dụ yêu cầu thời điểm chạy cách hiện tại ít nhất 30 giây nếu nghiệp vụ cần.
- Đặt quy tắc dựa trên thời điểm server nhận yêu cầu; kiểm tra lại khi scheduling/dispatch.
- Hibernate Validator có cấu hình **temporal validation tolerance** (`temporalValidationTolerance(Duration)`) cho sai lệch nhỏ. Đây là **mở rộng của Hibernate Validator**, không phải thuộc tính chuẩn của bốn annotation; chỉ dùng khi hiểu rõ ảnh hưởng và đã test.

Không tự thêm một khoảng dung sai tùy ý rồi gọi đó là ngữ nghĩa chuẩn của `@FutureOrPresent` hoặc `@PastOrPresent`. Nếu quy tắc cần “trễ tối đa 5 phút” hay “phải sau 24 giờ”, thường nên viết validator hoặc service rule diễn đạt trực tiếp.

## 13. Nhóm kiểm tra, cascade và cơ chế kích hoạt

Mọi constraint Jakarta Validation có `groups` và mặc định thuộc `Default`. Ví dụ:

```java
import java.time.LocalDate;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

interface Submit {}

public record PublishRequest(
        @NotNull LocalDate preparedOn,
        @Future(groups = Submit.class) LocalDate publicationDate) {}
```

Các declaration trên là **mảnh minh họa**, không phải class Java chạy độc lập. Với `@Validated(Submit.class)` ở điểm Spring kích hoạt validation, constraint `@Future` thuộc nhóm `Submit` được đánh giá; `@NotNull` trên `preparedOn` chỉ ở `Default` **không tự được chạy** (trừ khi group inheritance/sequence được thiết kế tương ứng). Nếu muốn cả hai, chọn `@Validated({Default.class, Submit.class})` hoặc cấu trúc group được định nghĩa rõ.

Khi một DTO chứa bean con mang constraint thời gian:

```java
class Booking {
    @jakarta.validation.Valid
    private Schedule schedule;
}

class Schedule {
    @jakarta.validation.constraints.Future
    private java.time.Instant startsAt;
}
```

`@Valid` trên trường liên kết là chỉ thị **cascade**, để provider đi sâu kiểm tra bean con. Chỉ đặt `@Future` ở `Schedule.startsAt` không khiến nó tự chạy nếu validator chỉ nhìn tới bean `Booking` mà không cascade.

Trong Spring MVC:
- `@Valid @RequestBody Dto` hoặc `@Validated @RequestBody Dto` thường kích hoạt validation của DTO sau khi deserialize.
- `@Validated(Group.class)` cho phép chọn group nếu endpoint cần quy tắc riêng.
- `@ModelAttribute` kết hợp `BindingResult` đặt **ngay sau** tham số giúp xử lý lỗi binding/validation trong controller.
- Constraint trực tiếp trên tham số handler có thể kích hoạt **method validation tích hợp** của Spring MVC 6.1+; exception có thể khác với lỗi `@RequestBody` thường gặp. Đừng khẳng định mọi lỗi thời gian đều có chung một lớp exception.

Validation chỉ được thực thi khi tích hợp phù hợp được bật. Khởi tạo một DTO bằng `new` không tự kiểm tra annotation.

## 14. Kiểm thử ranh giới và test cases tối thiểu

Khi viết test cho temporal constraint, dùng clock cố định và bao phủ ít nhất các tình huống:

| Tình huống | Cần kiểm tra |
| --- | --- |
| Trước mốc `now` | `@Past`, `@PastOrPresent` đạt; hai constraint tương lai không đạt |
| Bằng `now` | Hai constraint strict thất bại; hai constraint `OrPresent` đạt |
| Sau `now` | `@Future`, `@FutureOrPresent` đạt; hai constraint quá khứ không đạt |
| Giá trị `null` | Cả bốn temporal constraint đạt; `@NotNull` mới quyết định bắt buộc |
| Ngày cuối tháng và năm nhuận | Parse và validate `2024-02-29`, `2026-02-29` (ngày không tồn tại) đúng giai đoạn |
| Hai timezone | Cùng instant, local date khác nhau khi vùng giờ vượt nửa đêm |
| Đúng kiểu temporal | `LocalDate`, `Instant` hoặc `OffsetDateTime` tương ứng với hợp đồng request |
| Sai kiểu/format trong HTTP | Tách lỗi parse/binding và lỗi constraint |
| Group và bean lồng nhau | Đúng group, `@Valid` cascade, không bỏ sót `Default` |
| Quy tắc đồng thời | Vào thời điểm validate hợp lệ, đến lúc ghi DB/job có thể đã quá hạn |

**Đừng viết test phụ thuộc `LocalDate.now()` thật** để khẳng định hôm qua/hôm nay/ngày mai bằng literal ngày cố định; test sẽ hỏng theo thời gian hoặc timezone trên CI. Nếu test qua Spring MVC, dùng test configuration cung cấp clock cố định và bảo đảm nó được nối vào **ValidatorFactory mà MVC đang sử dụng**.

## 15. Các lỗi phổ biến và hướng sửa

1. **Nhầm strict với inclusive.** `@Past`/`@Future` không nhận giá trị đúng bằng hiện tại. Nếu ngày hôm nay hợp lệ, xem `@PastOrPresent`/`@FutureOrPresent`.
2. **Dùng `@Future LocalDate` cho lịch hẹn còn vài giờ trong hôm nay.** Ngày hôm nay không phải tương lai đối với `LocalDate`; dùng kiểu chứa giờ và quy tắc timezone.
3. **Để field nullable mà tưởng annotation cấm null.** Cả bốn constraint cho phép null; kết hợp `@NotNull` khi bắt buộc.
4. **Đặt temporal constraint lên chuỗi.** Hãy deserialize/bind sang temporal type; lỗi sai kiểu có thể là exception cấu hình validator thay vì một lỗi dữ liệu thông thường.
5. **Quên thống nhất timezone.** Server khác zone có thể thấy hôm nay khác nhau khi cùng một instant.
6. **Tin `LocalDateTime` là một thời điểm UTC.** Nó không chứa zone/offset; chọn kiểu có ngữ nghĩa phù hợp.
7. **Test đúng bằng `Instant.now()` nhưng không cố định clock.** “Now” thay đổi giữa lúc dựng input và validate; dùng `Clock.fixed`.
8. **Đặt `@Past` trên ngày sinh rồi vô tình cấm sinh hôm nay.** Chọn điều kiện theo yêu cầu nghiệp vụ, không theo tên annotation.
9. **Cho rằng `@Future` đảm bảo timestamp còn trong tương lai đến tận lúc job chạy.** Đó là một kiểm tra tại thời điểm validation; cần chính sách thực thi riêng.
10. **Dùng `@FutureOrPresent` để khẳng định hai ngày đúng thứ tự.** Nó chỉ so từng ngày với now, không so hai field.
11. **Nhầm `@DateTimeFormat`/`@JsonFormat` là temporal validation.** Formatting xác định cách parse/print, bốn constraint quyết định quan hệ thời gian.
12. **Bắt một loại HTTP exception cho mọi lỗi.** Lỗi parse, Bean Validation và method validation có các đường xử lý khác nhau.
13. **Dựa vào thông báo mặc định để xây mã lỗi.** Dùng mã/field ổn định do ứng dụng quy định; message có thể được quốc tế hóa.
14. **Dùng `@Future` làm quy tắc an toàn duy nhất ở tầng DB.** Tính hợp lệ theo thời gian và trạng thái có thể thay đổi giữa các bước; vẫn cần ràng buộc/transaction phù hợp.

## 16. Bài tập tự luyện và đáp án

**Bài 1.** Một biểu mẫu sinh nhật nhận `LocalDate` và cho phép sinh hôm nay nhưng không được ngày mai. Cần constraint nào?

**Đáp:** `@PastOrPresent`. Nếu trường bắt buộc, thêm `@NotNull`.

**Bài 2.** Một hệ thống lên lịch dùng `Instant`; mốc xử lý phải ở sau đúng thời điểm hiện tại, không được bằng. Chọn gì?

**Đáp:** `@Future`. Nhưng cần thêm chính sách khi thời gian trôi qua trong queue.

**Bài 3.** Một hợp đồng chỉ nhận ngày bắt đầu từ **hôm nay trở đi** và lưu `LocalDate`. Annotation nào phù hợp?

**Đáp:** `@FutureOrPresent`; nếu bắt buộc, kết hợp `@NotNull`.

**Bài 4.** Với mốc `2026-11-05` và `LocalDate.of(2026,11,5)`, kết quả của bốn constraint?

**Đáp:** `@Past` không đạt; `@PastOrPresent` đạt; `@Future` không đạt; `@FutureOrPresent` đạt.

**Bài 5.** Vì sao cùng instant 23:30Z lại có thể là hôm nay ở UTC nhưng ngày mai ở Asia/Ho_Chi_Minh?

**Đáp:** Vì `LocalDate` phụ thuộc vùng giờ dùng chuyển instant thành ngày, và clock của validator mang zone. `Instant` không đổi.

**Bài 6.** Cho `@Future LocalDate deadline`, giá trị null hợp lệ không? Nếu API yêu cầu phải có deadline thì làm gì?

**Đáp:** Null hợp lệ theo `@Future`; thêm `@NotNull` để bắt buộc.

**Bài 7.** Cả `startDate` và `endDate` đều mang `@FutureOrPresent`. Có đảm bảo `startDate <= endDate` không?

**Đáp:** Không; hai constraint chỉ so với now. Cần quy tắc kiểm tra quan hệ giữa chúng.

**Bài 8.** Test `@Past Instant` với giá trị `Instant.now()` thất bại ngẫu nhiên. Cách kiểm thử tin cậy?

**Đáp:** Dùng một `Clock.fixed` cho validator và dữ liệu test, kiểm tra trước/bằng/sau mốc cố định.

**Bài 9.** Client gửi `"2026-13-40"` vào `LocalDate`. Đây là lỗi constraint `@Future`?

**Đáp:** Không. Chuỗi ngày không hợp lệ không thể deserialize thành `LocalDate`; lỗi thường xảy ra ở bước parse trước khi đánh giá constraint.

**Bài 10.** Cần kiểm tra “hợp đồng không được bắt đầu trước 09:00 ngày mai ở Hà Nội”. Có thể chỉ dùng `@FutureOrPresent LocalDate`?

**Đáp:** Không. Phải xây ngưỡng `ZonedDateTime`/`Instant` theo zone nghiệp vụ, rồi so sánh với quy tắc cụ thể; bốn constraint chỉ so với “now”, không biểu diễn một thời điểm ngưỡng tùy ý như vậy.

## 17. Ghi nhớ khi triển khai

- `@Past` và `@Future` **không bao gồm hiện tại**; `@PastOrPresent` và `@FutureOrPresent` **bao gồm hiện tại** theo ngữ nghĩa kiểu dữ liệu.
- Cả bốn constraint **chấp nhận null**. Dùng `@NotNull` nếu field bắt buộc.
- `ClockProvider` là nguồn của “now”; với `LocalDate`, zone quyết định ngày hiện tại.
- Dùng `LocalDate` cho **ngày thuần**, `Instant`/kiểu mang offset hoặc zone cho **thời điểm**. Không thể diễn đạt một thời điểm tương lai cụ thể chỉ bằng `LocalTime`.
- Lỗi parse/binding là một giai đoạn khác với lỗi constraint; Spring MVC cần kích hoạt validation qua `@Valid`/`@Validated`.
- Fixed clock tạo kiểm thử ranh giới đáng tin; logic kiểm tra deadline khi thực thi và so sánh hai field phải có thiết kế riêng.

### Tài liệu tham khảo chính thức

- Jakarta Validation 3.1 – `@Past`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Past
- Jakarta Validation 3.1 – `@PastOrPresent`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/PastOrPresent
- Jakarta Validation 3.1 – `@Future`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Future
- Jakarta Validation 3.1 – `@FutureOrPresent`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/FutureOrPresent
- Jakarta Validation 3.1 – `ClockProvider`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ClockProvider
- Jakarta Validation – specification, temporal validation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator 8 – ClockProvider và temporal tolerance: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring MVC – Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.3 – `ValidationConfigurationCustomizer`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html
