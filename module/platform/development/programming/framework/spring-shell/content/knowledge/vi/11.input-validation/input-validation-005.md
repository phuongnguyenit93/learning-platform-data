# Ràng buộc chéo giữa nhiều tùy chọn

Một command có thể nhận nhiều option mà từng giá trị riêng lẻ đều hợp lệ, nhưng tổ hợp của chúng lại không hợp lệ. Ví dụ `--from` và `--to` đều là ngày hợp lệ nhưng ngày kết thúc lại đứng trước ngày bắt đầu; `--username` có giá trị nhưng `--password` bị bỏ trống; hoặc người dùng truyền đồng thời hai nguồn dữ liệu loại trừ lẫn nhau.

Đây là **ràng buộc chéo** (cross-field hoặc cross-option validation). Với Spring Shell 4.x, có thể kiểm tra trực tiếp trong command method, gom các option thành một đối tượng rồi dùng Bean Validation, hoặc dùng cross-parameter constraint của Jakarta Bean Validation khi cần kiểm tra chữ ký method. Điều quan trọng là hoàn tất kiểm tra tổ hợp trước khi thực hiện thao tác có side effect như ghi file, cập nhật cơ sở dữ liệu hoặc gửi yêu cầu đến hệ thống khác.

## 1. Ràng buộc chéo là gì?

Validation từng tham số kiểm tra một giá trị độc lập. Ràng buộc chéo kiểm tra quan hệ giữa hai hoặc nhiều giá trị.

| Loại ràng buộc | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Thứ tự | `--from`, `--to` | Ngày kết thúc không đứng trước ngày bắt đầu |
| Cặp phụ thuộc | `--username`, `--password` | Nếu có username thì phải có password và ngược lại |
| Loại trừ lẫn nhau | `--file`, `--stdin` | Chỉ được chọn một nguồn đầu vào |
| Ít nhất một giá trị | `--email`, `--phone` | Phải cung cấp ít nhất một kênh liên hệ |
| Giới hạn tổng hợp | `--cpu`, `--memory` | Tổng tài nguyên yêu cầu không vượt quota |
| Quan hệ min/max | `--min-price`, `--max-price` | Giá trị nhỏ nhất không lớn hơn giá trị lớn nhất |
| Phụ thuộc vào cờ | `--encrypt`, `--key-file` | Bật mã hóa thì phải cung cấp file khóa |

Ví dụ, mỗi option trong lệnh sau đều có thể chuyển đổi thành `LocalDate` thành công:

```text
report-export --from=2026-12-20 --to=2026-12-01
```

Nhưng tổ hợp ngày này không tạo thành một khoảng thời gian hợp lệ. `@Past`, `@Future` hoặc một constraint đơn tham số không thể diễn đạt đầy đủ quan hệ giữa hai ngày. Cần một bước kiểm tra cả hai giá trị cùng lúc.

## 2. Phân biệt kiểm tra từng option và kiểm tra tổ hợp

Giả sử command tìm kiếm nhận hai giới hạn:

```text
product-search --min-price=100 --max-price=500
```

Có thể kiểm tra từng option bằng các constraint độc lập:

```java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "product-search", description = "Search products")
public String search(
        @Option(longName = "min-price") @DecimalMin("0.00") BigDecimal minPrice,
        @Option(longName = "max-price") @DecimalMin("0.00") BigDecimal maxPrice) {
    // Search products
    return "Searching products";
}
```

Hai constraint `@DecimalMin` chỉ bảo đảm mỗi giá trị không âm. Chúng vẫn chấp nhận `--min-price=500 --max-price=100`, dù khoảng giá không hợp lệ.

Có thể phân loại quy tắc thành hai tầng:

1. **Validation từng tham số:** kiểu dữ liệu, giá trị bắt buộc, độ dài, miền số, định dạng hoặc phần tử enum.
2. **Validation tổ hợp:** quan hệ giữa các option, trạng thái phụ thuộc, lựa chọn loại trừ và quy tắc nghiệp vụ tổng hợp.

Nên giữ constraint đơn giản ở tham số gần với dữ liệu mà nó kiểm tra. Đưa quy tắc cần nhiều giá trị vào một nơi có thể nhìn thấy đầy đủ các giá trị đó.

## 3. Cách đơn giản: kiểm tra trực tiếp trong command method

Nếu quy tắc chỉ được dùng bởi một command và có ít nhánh, kiểm tra trực tiếp là cách dễ đọc nhất.

Ví dụ command xuất báo cáo theo khoảng ngày:

```java
import java.time.LocalDate;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(name = "report-export", description = "Export a report")
    public String export(
            @Option(longName = "from", required = false) LocalDate from,
            @Option(longName = "to", required = false) LocalDate to) {

        if ((from == null) != (to == null)) {
            throw new IllegalArgumentException(
                    "Provide both --from and --to, or omit both.");
        }

        if (from != null && to.isBefore(from)) {
            throw new IllegalArgumentException(
                    "--to must be on or after --from.");
        }

        // Call the report service only after validating the option pair.
        return "Exporting report";
    }
}
```

Lời gọi hợp lệ:

```text
report-export
report-export --from=2026-12-01 --to=2026-12-20
```

Trong ví dụ này, `LocalDate` được nhập theo định dạng ISO `yyyy-MM-dd`, ví dụ `2026-12-01`. Hãy công bố định dạng ngày trong `description` hoặc help để người dùng không phải đoán.

Lời gọi không hợp lệ:

```text
report-export --from=2026-12-01
report-export --to=2026-12-20
report-export --from=2026-12-20 --to=2026-12-01
```

Biểu thức `(from == null) != (to == null)` phát hiện trường hợp chỉ có một trong hai option được cung cấp. Kiểm tra `to.isBefore(from)` chỉ chạy khi cả hai ngày đều có giá trị, vì vậy không phát sinh lỗi do dereference `null`.

Ưu điểm của cách này là dễ hiểu và không cần tạo thêm constraint. Khi cùng một quy tắc được dùng ở nhiều command hoặc cần thông báo lỗi có cấu trúc, hãy tách quy tắc ra một đối tượng riêng.

## 4. Gom các option thành một đối tượng để kiểm tra cùng nhau

Một cách tổ chức dễ mở rộng là tạo request object chứa các option liên quan. Đối tượng này biểu diễn một bộ lựa chọn hoàn chỉnh của command, ví dụ `DateRangeOptions`, `SearchFilter` hoặc `ImportOptions`.

Ví dụ record:

```java
import java.time.LocalDate;

public record DateRangeOptions(
        LocalDate from,
        LocalDate to) {
}
```

Command nhận các option rồi tạo record:

```java
@Command(name = "report-export", description = "Export a report")
public String export(
        @Option(longName = "from") LocalDate from,
        @Option(longName = "to") LocalDate to) {

    DateRangeOptions options = new DateRangeOptions(from, to);
    validateDateRange(options);

    return reportService.export(options);
}
```

Lợi ích của request object:

- Đặt tên cho một nhóm option có quan hệ với nhau.
- Có thể kiểm tra tổ hợp mà không phụ thuộc trực tiếp vào chữ ký command method.
- Dùng lại quy tắc trong nhiều command hoặc trong service.
- Dễ viết unit test cho các tổ hợp hợp lệ và không hợp lệ.

Đối tượng này nên chứa dữ liệu đầu vào và quy tắc kiểm tra. Tránh đưa logic ghi file hoặc gọi API vào validator của nó.

## 5. Dùng class-level constraint của Bean Validation

Jakarta Bean Validation hỗ trợ constraint ở cấp class. Constraint này nhận toàn bộ đối tượng nên có thể so sánh nhiều thuộc tính cùng lúc. Đây là lựa chọn phù hợp khi muốn khai báo quy tắc tổ hợp bằng annotation và dùng lại ở nhiều nơi.

### Bước 1: Khai báo annotation

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = DateRangeValidator.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateRange {

    String message() default
            "--from and --to must be provided together, and --to must not precede --from";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

`@Target(ElementType.TYPE)` cho phép đặt annotation trên class hoặc record. `validatedBy` chỉ định validator thực hiện quy tắc. Ba thuộc tính `message`, `groups` và `payload` là các thành phần chuẩn của custom Bean Validation constraint.

### Bước 2: Gắn constraint lên request object

```java
import java.time.LocalDate;

@ValidDateRange
public record DateRangeOptions(
        LocalDate from,
        LocalDate to) {
}
```

### Bước 3: Viết validator kiểm tra cả hai trường

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, DateRangeOptions> {

    @Override
    public boolean isValid(
            DateRangeOptions value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        boolean onlyOneDateProvided =
                (value.from() == null) != (value.to() == null);

        if (onlyOneDateProvided) {
            return reject(context,
                    "Provide both --from and --to, or omit both.");
        }

        if (value.from() != null && value.to().isBefore(value.from())) {
            return reject(context,
                    "--to must be on or after --from.");
        }

        return true;
    }

    private boolean reject(
            ConstraintValidatorContext context,
            String message) {
        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(message)
                .addConstraintViolation();
        return false;
    }
}
```

Validator xử lý ba trường hợp:

| `from` | `to` | Kết quả |
|---|---|---|
| `null` | `null` | Hợp lệ: người dùng không lọc theo ngày |
| Có giá trị | `null` hoặc ngược lại | Không hợp lệ: phải cung cấp cả cặp |
| `2026-12-01` | `2026-12-20` | Hợp lệ: ngày kết thúc không trước ngày bắt đầu |
| `2026-12-20` | `2026-12-01` | Không hợp lệ: thứ tự ngày bị đảo |

Nếu nghiệp vụ yêu cầu bắt buộc cả hai ngày, có thể thêm `@NotNull` lên từng component của record. Class-level constraint vẫn kiểm tra quan hệ thứ tự giữa hai ngày.

## 6. Gọi `Validator` trước khi thực hiện nghiệp vụ

Spring Boot có thể cấu hình Bean Validation thông qua provider như Hibernate Validator. Với ứng dụng Boot, thêm dependency `spring-boot-starter-validation`, sau đó inject `jakarta.validation.Validator` vào command bean.

Ví dụ:

```java
import java.time.LocalDate;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    private final Validator validator;
    private final ReportService reportService;

    public ReportCommands(Validator validator, ReportService reportService) {
        this.validator = validator;
        this.reportService = reportService;
    }

    @Command(name = "report-export", description = "Export a report")
    public String export(
            @Option(longName = "from") LocalDate from,
            @Option(longName = "to") LocalDate to) {

        DateRangeOptions options = new DateRangeOptions(from, to);
        Set<ConstraintViolation<DateRangeOptions>> violations =
                validator.validate(options);

        if (!violations.isEmpty()) {
            String message = violations.stream()
                    .map(ConstraintViolation::getMessage)
                    .collect(Collectors.joining("; "));
            throw new InvalidCommandOptionsException(message);
        }

        return reportService.export(options);
    }
}
```

`validator.validate(options)` chạy class-level constraint và trả về tập hợp vi phạm. Nếu có vi phạm, command dừng trước khi gọi `reportService.export`. Đây là điểm quan trọng: không bắt đầu thao tác có side effect khi bộ option chưa hợp lệ.

Ngoài class-level constraint, request object có thể chứa constraint đơn thuộc tính như `@NotNull`, `@Positive`, `@Size` hoặc `@Pattern`. Khi gọi `validator.validate(options)`, Bean Validation kiểm tra cả constraint trên thuộc tính lẫn constraint ở cấp class.

## 7. Trả lỗi validation rõ ràng và mã thoát phù hợp

Nên dùng một exception riêng cho tổ hợp option sai để phân biệt lỗi người dùng nhập với lỗi thực thi bất ngờ:

```java
public class InvalidCommandOptionsException extends RuntimeException {

    public InvalidCommandOptionsException(String message) {
        super(message);
    }
}
```

Trong Spring Shell 4, có thể khai báo `ExitStatusExceptionMapper` bean và gắn nó vào command bằng thuộc tính `exitStatusExceptionMapper`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper commandValidationMapper() {
        return exception -> {
            if (exception instanceof InvalidCommandOptionsException) {
                return new ExitStatus(
                        ExitStatus.USAGE_ERROR.code(), exception.getMessage());
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
```

Gắn mapper vào command:

```java
@Command(
        name = "report-export",
        description = "Export a report",
        exitStatusExceptionMapper = "commandValidationMapper")
public String export(
        @Option(longName = "from") LocalDate from,
        @Option(longName = "to") LocalDate to) {
    // Giữ nguyên bước tạo DateRangeOptions, gọi Validator và dừng nếu có lỗi.
    // Chỉ gọi reportService.export(...) sau khi tổ hợp đã hợp lệ.
    return "Report export accepted";
}
```

Mapper giúp command trả thông tin lỗi cùng `ExitStatus` phù hợp. `ExitStatus` của Spring Shell biểu diễn trạng thái command; nó khác với JVM process exit code. Nếu command chạy non-interactive trong script hoặc CI, cần cấu hình và kiểm tra riêng cách trạng thái command được chuyển thành mã thoát của tiến trình.

Không nên trả một chuỗi thông báo lỗi như thể command đã thành công nếu automation cần phân biệt kết quả thành công và thất bại. Dùng exception có kiểu rõ ràng, mapper và mã thoát để caller có thể xử lý kết quả nhất quán.

## 8. Phân biệt class-level và cross-parameter constraint

Jakarta Bean Validation có hai cách diễn đạt ràng buộc nhiều giá trị:

| Cách | Đối tượng validator nhận | Cách dùng |
|---|---|---|
| Class-level constraint | Một object có nhiều thuộc tính | `@ValidDateRange` trên `DateRangeOptions` |
| Cross-parameter constraint | Mảng tham số của method hoặc constructor | Annotation đặt trên method, validator nhận `Object[]` |

Class-level constraint phù hợp khi command có thể tạo một request object từ nhiều option rồi kiểm tra object đó. Nó cũng giúp tái sử dụng quy tắc ở service hoặc nơi khác.

Cross-parameter constraint phù hợp khi quy tắc gắn trực tiếp với một chữ ký method, ví dụ ngày bắt đầu và ngày kết thúc của method `schedule(start, end)`. Validator phải được đánh dấu bằng `@SupportedValidationTarget(ValidationTarget.PARAMETERS)` và triển khai `ConstraintValidator<..., Object[]>`.

Ví dụ phần khai báo validator:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = ConsistentRangeParametersValidator.class)
@Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
@Retention(RetentionPolicy.RUNTIME)
public @interface ConsistentRangeParameters {
    String message() default "--to must be on or after --from";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator:

```java
import java.time.LocalDate;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ConsistentRangeParametersValidator
        implements ConstraintValidator<ConsistentRangeParameters, Object[]> {

    @Override
    public boolean isValid(Object[] values, ConstraintValidatorContext context) {
        if (values == null || values.length != 2) {
            throw new IllegalArgumentException("Expected from and to parameters");
        }

        LocalDate from = (LocalDate) values[0];
        LocalDate to = (LocalDate) values[1];

        if (from == null || to == null) {
            return from == null && to == null;
        }
        return !to.isBefore(from);
    }
}
```

Gắn annotation lên method và gọi `ExecutableValidator` tường minh:

```java
import java.lang.reflect.Method;
import java.time.LocalDate;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

@Command(name = "report-export", description = "Export a report")
@ConsistentRangeParameters
public String export(
        @Option(longName = "from") LocalDate from,
        @Option(longName = "to") LocalDate to) throws NoSuchMethodException {

    Method method = ReportCommands.class.getMethod(
            "export", LocalDate.class, LocalDate.class);
    Set<ConstraintViolation<ReportCommands>> violations =
            validator.forExecutables().validateParameters(
                    this, method, new Object[] { from, to });

    if (!violations.isEmpty()) {
        throw new InvalidCommandOptionsException(
                violations.iterator().next().getMessage());
    }

    return reportService.export(new DateRangeOptions(from, to));
}
```

Spring Shell 4 tự động áp dụng Bean Validation cho các annotation trên **tham số command**. Tài liệu Option Validation của Spring Shell 4 không cam kết tự chạy constraint đặt trên method declaration. Vì vậy, không nên chỉ gắn cross-parameter annotation lên method `@Command` rồi mặc định cho rằng Shell sẽ gọi nó.

Nếu chọn cross-parameter constraint, hãy chủ động gọi `ExecutableValidator.validateParameters(...)` với method và mảng giá trị tương ứng, hoặc dùng class-level constraint trên request object như ví dụ trước. Với phần lớn command, request object thường dễ đọc và dễ kiểm thử hơn.

## 9. Các mẫu ràng buộc chéo thường gặp

### Hai option loại trừ lẫn nhau

Ví dụ command nhập dữ liệu từ file hoặc stdin:

```java
public record InputOptions(String file, Boolean stdin) {
}
```

Quy tắc:

- Không có cả hai: không có nguồn dữ liệu.
- Có cả hai: người dùng chọn hai nguồn cùng lúc.
- Chỉ có một: lựa chọn hợp lệ.

Điều kiện logic:

```java
boolean valid = (file != null) ^ Boolean.TRUE.equals(stdin);
```

`^` là XOR: chỉ đúng khi đúng một vế đúng. Nếu `stdin` có thể được truyền rõ ràng là `false`, hãy xác định `false` có được xem như “không chọn stdin” hay không.

### Một option yêu cầu option khác

Ví dụ xác thực tài khoản:

```java
boolean valid = (username == null) == (password == null);
```

Biểu thức này cho phép cả hai cùng vắng mặt hoặc cùng có mặt. Nếu chỉ có một giá trị, tổ hợp không hợp lệ. Nếu nghiệp vụ chỉ yêu cầu “có username thì phải có password”, dùng điều kiện một chiều:

```java
boolean valid = username == null || password != null;
```

### Min và max

```java
boolean valid = minPrice == null
        || maxPrice == null
        || minPrice.compareTo(maxPrice) <= 0;
```

Nếu nghiệp vụ yêu cầu phải có cả hai giá trị, kiểm tra sự hiện diện trước rồi mới so sánh. Với `BigDecimal`, dùng `compareTo` để so sánh giá trị số; `equals` còn xét cả scale nên `10.0` và `10.00` có thể không bằng nhau theo `equals`.

### Option bật tính năng yêu cầu option cấu hình

Ví dụ `--encrypt` yêu cầu `--key-file`:

```java
boolean valid = !encrypt || keyFile != null;
```

Nếu `encrypt` là `true`, `keyFile` phải có. Nếu `encrypt` là `false`, key file có thể vắng mặt.

## 10. Cẩn thận với default value và giá trị vắng mặt

Ràng buộc chéo thường cần biết option nào đã được cung cấp. Nếu đặt `defaultValue`, command nhận giá trị sau khi áp dụng default; lúc đó có thể không phân biệt được người dùng nhập giá trị hay hệ thống tự điền.

Ví dụ, nếu `--format` mặc định là `CSV`, command nhận `CSV` ở cả hai trường hợp:

```text
report-export
report-export --format=CSV
```

Nếu quy tắc chỉ cần giá trị cuối cùng thì default không gây vấn đề. Nếu quy tắc cần biết người dùng có chủ động chọn option hay không, hãy cân nhắc:

- Không khai báo default cho option đó; dùng wrapper type như `Boolean`, `Integer` hoặc `LocalDate` để biểu diễn giá trị vắng mặt.
- Xác định rõ `false`, `null` và “không được cung cấp” có ý nghĩa khác nhau hay không.
- Nếu cần phân biệt giá trị được nhập với giá trị mặc định, lấy thông tin presence từ command context hoặc một lớp binding phù hợp, thay vì suy luận chỉ từ giá trị Java.

Tránh dùng primitive như `boolean` hoặc `int` khi quy tắc cần phân biệt vắng mặt với `false` hoặc `0`; primitive luôn có giá trị mặc định của Java và có thể làm mất thông tin presence.

## 11. Kiểm thử ràng buộc chéo

Mỗi quy tắc cần có ca hợp lệ và ca không hợp lệ. Với khoảng ngày, có thể xây dựng ma trận:

| `--from` | `--to` | Kỳ vọng |
|---|---|---|
| Không có | Không có | Hợp lệ nếu cả hai option là bộ lọc tùy chọn |
| Có | Không có | Không hợp lệ |
| Không có | Có | Không hợp lệ |
| `2026-12-01` | `2026-12-20` | Hợp lệ |
| `2026-12-01` | `2026-12-01` | Hợp lệ nếu cho phép cùng ngày |
| `2026-12-20` | `2026-12-01` | Không hợp lệ |

Ngoài kết quả validation, cần xác nhận:

1. Command hiển thị thông báo có thể hành động, chỉ ra option cần sửa.
2. Service không được gọi khi tổ hợp option không hợp lệ.
3. Không ghi file, cập nhật database hoặc gọi API trước bước cross-validation.
4. Default value không che khuất việc người dùng bỏ qua option nếu presence là một phần của quy tắc.
5. Mã thoát phù hợp khi command chạy non-interactive.
6. Nhiều vi phạm có thể được tổng hợp thành một thông báo dễ đọc.

Có thể unit test class-level validator bằng `Validator.validate()` với các record khác nhau. Sau đó viết kiểm thử tích hợp Spring Shell để xác nhận option được bind đúng, validation được gọi và command không thực hiện side effect khi dữ liệu sai.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ dùng `@Min` và `@Max` cho từng option | Từng giá trị hợp lệ nhưng quan hệ giữa chúng sai | Bổ sung class-level hoặc cross-option validation |
| Gọi service trước khi kiểm tra tổ hợp | Có thể tạo side effect với dữ liệu không hợp lệ | Validate toàn bộ option trước thao tác nghiệp vụ |
| Đặt quá nhiều điều kiện trong command method | Khó đọc và khó tái sử dụng | Tách request object và validator |
| Dùng method-level cross-parameter annotation nhưng không gọi validator | Constraint có thể không được thực thi bởi tích hợp tự động của Spring Shell 4 | Gọi `ExecutableValidator` tường minh hoặc validate DTO |
| Dùng default khi cần biết option có được nhập hay không | Mất thông tin presence | Bỏ default hoặc kiểm tra presence từ context |
| Dùng primitive cho option có trạng thái vắng mặt | Không phân biệt được `null` với `false`/`0` | Dùng wrapper type và quy định semantics |
| Dùng `BigDecimal.equals` cho quan hệ số học | Giá trị bằng nhau nhưng scale khác nhau bị xem là khác | Dùng `compareTo` cho so sánh số |
| Validator truy cập database hoặc gọi dịch vụ bên ngoài | Validation chậm, có side effect và khó test | Giữ constraint thuần; kiểm tra nghiệp vụ bên ngoài theo một bước rõ ràng |

## 13. Checklist trước khi thực thi command

- [ ] Đã liệt kê các quan hệ giữa những option trong command.
- [ ] Đã tách constraint đơn tham số khỏi constraint tổ hợp.
- [ ] Đã chọn cách kiểm tra phù hợp: điều kiện trực tiếp, request object hoặc cross-parameter constraint.
- [ ] Nếu dùng Bean Validation, đã thêm provider phù hợp và inject `Validator`.
- [ ] Class-level constraint kiểm tra toàn bộ thuộc tính liên quan.
- [ ] Không giả định Spring Shell 4 tự chạy method-level cross-parameter constraint.
- [ ] Đã kiểm tra `null`, default, `false`, `0` và trường hợp chỉ cung cấp một phần option.
- [ ] Đã kiểm tra tổ hợp trước khi gọi service có side effect.
- [ ] Thông báo lỗi chỉ rõ cách sửa tổ hợp option.
- [ ] Đã ánh xạ lỗi đầu vào sang trạng thái/mã thoát phù hợp cho script và CI.
- [ ] Đã có unit test cho validator và integration test cho command.

## Tài liệu tham khảo

1. [Spring Shell 4 – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) – Bean Validation tự động trên tham số command và ví dụ constraint đơn tham số.
2. [Spring Shell 4 – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html) – `ExitStatusExceptionMapper`, thông báo lỗi và trạng thái command.
3. [Spring Framework – Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) – cấu hình `Validator`, class-level/custom constraint và method validation.
4. [Hibernate Validator – Cross-parameter constraints](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-cross-parameter-constraints) – validator nhận mảng tham số và `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`.
5. [Hibernate Validator – Class-level constraints](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#section-class-level-constraints) – constraint kiểm tra nhiều thuộc tính của một object.

Ràng buộc chéo bảo đảm một command chỉ thực hiện tác vụ khi toàn bộ lựa chọn tạo thành một tổ hợp hợp lệ. Hãy kiểm tra các option cùng nhau trước khi gọi service, dùng request object khi quy tắc cần tái sử dụng và giữ thông báo lỗi đủ rõ để người dùng biết phải sửa lựa chọn nào.
