# Điều kiện loại trừ nhau hoặc phải đi cùng nhau do ứng dụng thiết kế

Một command Spring Shell có thể nhận nhiều option riêng lẻ nhưng ý nghĩa của chúng thường phụ thuộc lẫn nhau. Ví dụ, người dùng có thể chọn xác thực bằng mật khẩu hoặc token, nhưng không được truyền cả hai; khoảng thời gian báo cáo cần có cả ngày bắt đầu và ngày kết thúc; hoặc khi chọn định dạng CSV thì mới được chỉ định dấu phân cách. Đây là các quy tắc kiểm tra trên **tổ hợp tham số**.

Các annotation như `@NotBlank`, `@Min` hoặc `@Pattern` kiểm tra từng giá trị. Chúng không tự mô tả đầy đủ quan hệ giữa nhiều option. Để bảo đảm command nhận được một bộ tham số nhất quán, ứng dụng cần xác định rõ quy tắc kết hợp và kiểm tra chúng trước khi thực hiện nghiệp vụ.

## 1. Nhận diện các dạng quan hệ giữa tham số

Có một số dạng quy tắc thường gặp:

| Dạng quy tắc | Ý nghĩa | Ví dụ |
|---|---|---|
| Loại trừ nhau (at most one) | Không được truyền đồng thời hai hay nhiều giá trị trong một nhóm | Chọn `--username` hoặc `--token`, nhưng có thể không chọn cả hai |
| Chính xác một (exactly one) | Phải truyền đúng một trong các lựa chọn | Bắt buộc dùng một trong `--username` và `--token` |
| Đi cùng nhau (both or neither) | Hoặc truyền đủ cả cặp, hoặc bỏ qua cả cặp | `--from` và `--to` |
| Phụ thuộc một chiều | Có A thì bắt buộc phải có B; có B không nhất thiết cần A | Có `--proxy` thì phải có `--proxy-port` |
| Nhóm đầy đủ (all or none) | Một nhóm nhiều tham số phải được truyền đầy đủ hoặc bỏ qua toàn bộ | `--client-id`, `--client-secret`, `--tenant` |
| Điều kiện theo giá trị | Sự hợp lệ của một option phụ thuộc giá trị option khác | `--delimiter` chỉ có ý nghĩa khi `--format csv` |

Trước khi viết validator, hãy xác định chính xác quy tắc. “Loại trừ nhau” có thể chỉ có nghĩa không được chọn đồng thời, hoặc có nghĩa phải chọn đúng một. Hai yêu cầu này khác nhau khi người dùng không truyền option nào.

## 2. Biểu diễn quy tắc bằng logic đơn giản

Đặt `A` và `B` là trạng thái một option có giá trị hợp lệ hay không. Có thể biểu diễn các quy tắc phổ biến như sau:

| Quy tắc | Biểu thức | Kết quả được chấp nhận |
|---|---|---|
| Không được có cả hai | `!(A && B)` | Không có option nào hoặc chỉ có một option |
| Phải có đúng một | `A ^ B` | Chỉ A hoặc chỉ B |
| Cả hai hoặc không có | `A == B` | Cả A và B, hoặc không có cả hai |
| A yêu cầu B | `!A || B` | Không có A, hoặc có cả A và B |
| Cả ba hoặc không có | `count(A, B, C) == 0 || count(A, B, C) == 3` | Không có giá trị nào hoặc có đủ ba |

Trong Java, `^` trên hai biểu thức boolean là phép XOR: kết quả `true` khi hai giá trị khác nhau. Với nhiều lựa chọn, hãy đếm số giá trị đã được cung cấp thay vì viết chuỗi điều kiện khó đọc.

### Ví dụ: chọn đúng một phương thức xác thực

Giả sử command chấp nhận `--username` hoặc `--token`, và yêu cầu phải có đúng một:

```java
boolean hasUsername = username != null && !username.isBlank();
boolean hasToken = token != null && !token.isBlank();

if (hasUsername == hasToken) {
    throw new IllegalArgumentException(
            "Hãy truyền đúng một trong --username hoặc --token");
}
```

Hai trường hợp không hợp lệ là không truyền cả hai và truyền cả hai. Nếu yêu cầu chỉ là “không được dùng đồng thời”, điều kiện phải đổi thành:

```java
if (hasUsername && hasToken) {
    throw new IllegalArgumentException(
            "Không được truyền đồng thời --username và --token");
}
```

Tránh dùng từ “loại trừ nhau” trong thông báo hoặc tài liệu thiết kế nếu chưa xác định người dùng có được phép bỏ qua toàn bộ lựa chọn hay không.

## 3. Kiểm tra một cặp option phải đi cùng nhau

Một bộ lọc thời gian thường cần cả ngày bắt đầu và ngày kết thúc. Người dùng có thể không lọc theo thời gian, nhưng nếu đã truyền một đầu thì phải truyền đầu còn lại.

```java
boolean hasFrom = from != null && !from.isBlank();
boolean hasTo = to != null && !to.isBlank();

if (hasFrom != hasTo) {
    throw new IllegalArgumentException(
            "--from và --to phải được truyền cùng nhau");
}
```

Điều kiện `hasFrom != hasTo` chỉ sai khi một bên có và bên còn lại không có. Nếu cả hai cùng vắng mặt hoặc cùng có mặt, điều kiện đi qua. Sau bước kiểm tra cặp, ứng dụng vẫn cần xác nhận ngày bắt đầu không sau ngày kết thúc.

```java
if (hasFrom && LocalDate.parse(from).isAfter(LocalDate.parse(to))) {
    throw new IllegalArgumentException("--from phải trước hoặc bằng --to");
}
```

Trong ứng dụng thực tế, có thể nhận `LocalDate` trực tiếp nếu shell ConversionService hỗ trợ kiểu đó, hoặc parse chuỗi theo định dạng đã công bố. Dù dùng cách nào, hãy tách kiểm tra “có đủ cặp hay không” khỏi kiểm tra “giá trị của cặp có hợp lệ hay không”.

## 4. Kiểm tra nhóm nhiều tham số

Một cấu hình kết nối có thể yêu cầu đủ ba option `--client-id`, `--client-secret` và `--tenant`. Có thể đếm số giá trị có nội dung:

```java
int provided = 0;
provided += hasText(clientId) ? 1 : 0;
provided += hasText(clientSecret) ? 1 : 0;
provided += hasText(tenant) ? 1 : 0;

if (provided != 0 && provided != 3) {
    throw new IllegalArgumentException(
            "--client-id, --client-secret và --tenant phải được truyền cùng nhau");
}
```

Hàm `hasText` có thể dùng chung:

```java
private static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

Đếm số trường có giá trị giúp quy tắc dễ mở rộng khi nhóm có nhiều hơn hai option. Nếu nhóm có nhiều trường nhưng có những tổ hợp hợp lệ riêng, hãy mô tả các tổ hợp đó rõ ràng hoặc dùng validator chuyên biệt thay vì cố nhồi mọi quy tắc vào một biểu thức số học.

## 5. Kiểm tra điều kiện phụ thuộc một chiều

Không phải mọi quan hệ đều đối xứng. Ví dụ, `--proxy` yêu cầu `--proxy-port`, nhưng người dùng có thể truyền một port mặc định hoặc port cấu hình ở nơi khác mà không dùng proxy.

```java
boolean hasProxy = hasText(proxy);
boolean hasProxyPort = proxyPort != null;

if (hasProxy && !hasProxyPort) {
    throw new IllegalArgumentException(
            "Khi dùng --proxy, cần truyền thêm --proxy-port");
}
```

Nếu port chỉ có ý nghĩa khi có proxy, có thể kiểm tra chiều ngược lại:

```java
if (!hasProxy && hasProxyPort) {
    throw new IllegalArgumentException(
            "Không dùng --proxy-port khi chưa truyền --proxy");
}
```

Chỉ thêm điều kiện thứ hai khi nghiệp vụ thật sự yêu cầu hai tham số phải đi cùng nhau. Nếu port có thể cấu hình độc lập, không nên từ chối trường hợp đó.

## 6. Điều kiện phụ thuộc vào giá trị của option

Một số quy tắc không chỉ phụ thuộc vào sự hiện diện của tham số mà còn phụ thuộc giá trị của chúng. Ví dụ, `--delimiter` chỉ có ý nghĩa với định dạng `csv`; với `json`, option này phải bị từ chối.

```java
boolean hasDelimiter = hasText(delimiter);

if (hasDelimiter && !"csv".equalsIgnoreCase(format)) {
    throw new IllegalArgumentException(
            "--delimiter chỉ dùng được khi --format là csv");
}
```

Nếu delimiter là tùy chọn trong CSV, hãy kiểm tra giá trị delimiter có đúng một ký tự hoặc nằm trong tập được hỗ trợ. Nếu format là enum, so sánh enum trực tiếp sẽ an toàn hơn so sánh chuỗi tự do.

Các quy tắc có điều kiện thường nên được đặt gần nơi ứng dụng quyết định hành vi theo cấu hình. Đừng biến một option thành vô nghĩa bằng cách âm thầm bỏ qua nó; hãy từ chối hoặc ghi rõ rằng giá trị đó không được áp dụng.

## 7. Kiểm tra trực tiếp trong command

Với command nhỏ, có ít quy tắc, kiểm tra trực tiếp trong method là cách dễ hiểu. Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(name = "report export", description = "Xuất báo cáo")
    public String export(
            @Option(longName = "from") String from,
            @Option(longName = "to") String to,
            @Option(longName = "format", defaultValue = "csv") String format,
            @Option(longName = "delimiter") String delimiter) {

        boolean hasFrom = hasText(from);
        boolean hasTo = hasText(to);
        if (hasFrom != hasTo) {
            throw new IllegalArgumentException(
                    "--from và --to phải được truyền cùng nhau");
        }

        if (hasText(delimiter) && !"csv".equalsIgnoreCase(format)) {
            throw new IllegalArgumentException(
                    "--delimiter chỉ dùng được khi --format là csv");
        }

        return "Đang xuất báo cáo";
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
```

Các ví dụ gọi:

```text
report export
report export --from 2026-01-01 --to 2026-01-31
report export --format csv --delimiter ";"
```

Các ví dụ không hợp lệ:

```text
report export --from 2026-01-01
report export --format json --delimiter ";"
```

Khi số lượng tham số hoặc quy tắc tăng lên, method command sẽ khó đọc. Khi đó hãy chuyển dữ liệu đã bind thành một object biểu diễn yêu cầu và tách phần validation ra khỏi command.

## 8. Dùng DTO để kiểm tra quy tắc ở cấp đối tượng

Một DTO gom các option có liên quan vào một cấu trúc có tên. Ví dụ:

```java
public record ExportOptions(
        String from,
        String to,
        String username,
        String token,
        String format,
        String delimiter) {
}
```

Command nhận các option rồi tạo DTO:

```java
ExportOptions options = new ExportOptions(
        from, to, username, token, format, delimiter);
```

Lúc này, ứng dụng có thể kiểm tra toàn bộ object một lần. Cách này phù hợp khi:

- Nhiều command dùng chung một nhóm quy tắc.
- Quy tắc cần được kiểm thử độc lập với parser và terminal.
- Cấu hình cần được truyền sang service hoặc lưu lại như một request.
- Muốn dùng Jakarta Bean Validation với class-level constraint.

DTO chỉ là nơi gom dữ liệu. Việc tạo DTO không tự kích hoạt validation; ứng dụng phải gọi validator hoặc dùng một integration layer đã được cấu hình để làm việc đó.

## 9. Dùng class-level constraint với Jakarta Bean Validation

Spring Shell tích hợp Bean Validation và tự động kiểm tra các constraint được đặt trên tham số command trước khi gọi command. Tài liệu Spring Shell 4.0.4 mô tả rõ việc áp dụng constraint trên command parameters. Với quy tắc cần nhìn nhiều trường cùng lúc, có thể dùng class-level constraint trên DTO và gọi `jakarta.validation.Validator.validate(dto)` một cách tường minh.

Trước hết, thêm implementation Bean Validation vào ứng dụng Spring Boot nếu dự án chưa có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Định nghĩa annotation cho DTO:

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Documented
@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = ExportOptionsValidator.class)
public @interface ValidExportOptions {
    String message() default "Các tùy chọn xuất báo cáo không nhất quán";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Gắn annotation vào record:

```java
@ValidExportOptions
public record ExportOptions(
        String from,
        String to,
        String username,
        String token,
        String format,
        String delimiter) {
}
```

Validator kiểm tra nhiều trường trong cùng object:

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class ExportOptionsValidator
        implements ConstraintValidator<ValidExportOptions, ExportOptions> {

    @Override
    public boolean isValid(
            ExportOptions value,
            ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }

        boolean valid = true;
        boolean hasFrom = hasText(value.from());
        boolean hasTo = hasText(value.to());
        boolean hasUsername = hasText(value.username());
        boolean hasToken = hasText(value.token());

        boolean hasIncompletePeriod = hasFrom != hasTo;
        boolean hasInvalidAuthentication = hasUsername == hasToken;
        boolean hasInvalidDelimiter = hasText(value.delimiter())
                && !"csv".equalsIgnoreCase(value.format());

        if (hasIncompletePeriod || hasInvalidAuthentication || hasInvalidDelimiter) {
            context.disableDefaultConstraintViolation();
        }

        if (hasIncompletePeriod) {
            context.buildConstraintViolationWithTemplate(
                    "--from và --to phải được truyền cùng nhau")
                    .addPropertyNode(hasFrom ? "to" : "from")
                    .addConstraintViolation();
            valid = false;
        }

        if (hasInvalidAuthentication) {
            context.buildConstraintViolationWithTemplate(
                    "Hãy truyền đúng một trong --username hoặc --token")
                    .addPropertyNode("username")
                    .addConstraintViolation();
            valid = false;
        }

        if (hasInvalidDelimiter) {
            context.buildConstraintViolationWithTemplate(
                    "--delimiter chỉ dùng được khi --format là csv")
                    .addPropertyNode("delimiter")
                    .addConstraintViolation();
            valid = false;
        }

        return valid;
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
```

Trong ví dụ này, `hasFrom != hasTo` kiểm tra cặp ngày; `hasUsername == hasToken` bảo đảm chính xác một phương thức xác thực; và điều kiện cuối kiểm tra delimiter phụ thuộc format. `addPropertyNode` giúp thông báo gắn với trường liên quan trong DTO.

Gọi validator từ command hoặc service:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import java.util.Set;
import java.util.stream.Collectors;

Set<ConstraintViolation<ExportOptions>> violations = validator.validate(options);
if (!violations.isEmpty()) {
    String message = violations.stream()
            .map(v -> v.getPropertyPath() + ": " + v.getMessage())
            .collect(Collectors.joining("; "));
    throw new IllegalArgumentException("Tùy chọn không hợp lệ: " + message);
}
```

Trong ứng dụng, inject `Validator` từ Spring context vào command hoặc service. Sau validation thành công mới gọi service xuất báo cáo. Không log DTO chứa token hoặc bí mật xác thực; chỉ hiển thị tên trường và lý do từ chối.

## 10. Cross-parameter constraint và method validation

Jakarta Bean Validation còn định nghĩa *cross-parameter constraint*: một constraint đặt trực tiếp trên method hoặc constructor để kiểm tra mảng tham số cùng lúc. Ví dụ, một method nhận `from` và `to` có thể dùng constraint để bảo đảm ngày bắt đầu không sau ngày kết thúc.

Đây là khả năng của Jakarta Bean Validation, nhưng cần phân biệt với tích hợp tự động của Spring Shell. Tài liệu Spring Shell 4.0.4 mô tả tự động kiểm tra constraint đặt trên command parameters. Không nên mặc định rằng mọi cross-parameter constraint đặt trên method command đều được Spring Shell gọi tự động.

Nếu chọn cách này, ứng dụng phải kích hoạt executable validation thông qua `ExecutableValidator.validateParameters(...)` hoặc một method-validation interceptor đã được cấu hình. Ví dụ ý tưởng:

```java
import jakarta.validation.Validator;
import jakarta.validation.executable.ExecutableValidator;

import java.lang.reflect.Method;
import java.util.Set;

ExecutableValidator executableValidator = validator.forExecutables();
Method method = ReportCommands.class.getMethod(
        "export", String.class, String.class);

Object[] values = { from, to };
Set<ConstraintViolation<ReportCommands>> violations =
        executableValidator.validateParameters(this, method, values);
```

Constraint tùy chỉnh phải khai báo validator nhắm tới `ValidationTarget.PARAMETERS` bằng `@SupportedValidationTarget`. Cách này phù hợp khi cần mô tả contract của method, nhưng phức tạp hơn DTO class-level validation. Với command CLI, DTO cộng với `Validator.validate(dto)` thường dễ kiểm thử và dễ đọc hơn.

## 11. Chọn nơi đặt quy tắc

Không phải mọi điều kiện đều cần custom annotation. Chọn cách triển khai theo phạm vi sử dụng:

| Cách làm | Phù hợp khi | Ưu điểm |
|---|---|---|
| Kiểm tra trực tiếp trong command | Một command, một vài điều kiện ngắn | Dễ hiểu, ít cấu hình |
| Hàm validator riêng | Nhiều command dùng chung quy tắc đơn giản | Tái sử dụng mà không cần framework constraint |
| DTO và class-level constraint | Một nhóm tham số có nhiều quy tắc kết hợp | Có thể dùng Bean Validation, kiểm thử object độc lập |
| Cross-parameter constraint | Quy tắc thuộc contract của một method/constructor cụ thể | Mô tả trực tiếp quan hệ giữa các tham số method |
| Service/domain validation | Quy tắc ảnh hưởng tới nhiều giao diện hoặc phụ thuộc trạng thái nghiệp vụ | Không bị giới hạn trong CLI; có thể dùng lại từ API hoặc batch |

Các quy tắc liên quan tới trạng thái hệ thống, quyền người dùng, tài nguyên tồn tại hoặc giới hạn theo tenant nên được kiểm tra trong service/domain. Một command có thể từ chối sớm để đưa thông báo thân thiện, nhưng service vẫn phải bảo vệ invariant khi được gọi từ nơi khác.

## 12. Thông báo lỗi và thời điểm kiểm tra

Hãy kiểm tra tổ hợp tham số sau khi parser đã bind xong tất cả argument và option, nhưng trước khi thực hiện side effect như ghi file, gửi request hoặc cập nhật database.

Một thông báo hữu ích cần cho biết:

- Các option liên quan là những option nào.
- Người dùng cần truyền đủ, chỉ chọn một hay bỏ qua toàn bộ.
- Có điều kiện nào phụ thuộc giá trị của option khác không.
- Cách gọi hợp lệ tối thiểu là gì.

Ví dụ:

```text
Không hợp lệ: --from và --to phải được truyền cùng nhau.
Ví dụ hợp lệ: report export --from 2026-01-01 --to 2026-01-31
```

Với lỗi tổ hợp đầu vào, nên ánh xạ sang loại lỗi sử dụng command (`USAGE_ERROR`) nếu ứng dụng có cấu hình `ExitStatusExceptionMapper`. Điều này giúp script và CI phân biệt lỗi người dùng với lỗi thực thi hoặc lỗi hệ thống. Tránh đưa token, mật khẩu hoặc giá trị bí mật vào thông báo lỗi.

## 13. Kiểm thử các tổ hợp đầu vào

Không chỉ kiểm thử một trường hợp hợp lệ. Với hai option A và B, tối thiểu hãy kiểm tra đủ bốn tổ hợp:

| A | B | Quy tắc cả hai hoặc không có | Quy tắc chính xác một |
|---|---|---|---|
| Vắng mặt | Vắng mặt | Hợp lệ | Không hợp lệ |
| Có | Vắng mặt | Không hợp lệ | Hợp lệ |
| Vắng mặt | Có | Không hợp lệ | Hợp lệ |
| Có | Có | Hợp lệ | Không hợp lệ |

Với ba option, kiểm thử thêm từng trường hợp chỉ có một, chỉ có hai và có đủ cả ba. Với quy tắc phụ thuộc giá trị, kiểm tra từng nhánh giá trị, ví dụ format `csv`, `json`, giá trị không hỗ trợ và delimiter có/không.

Ví dụ kiểm thử DTO bằng Jakarta Validator:

```java
assertThat(validator.validate(
        new ExportOptions(null, null, "alice", null, "csv", null)))
        .isEmpty();

assertThat(validator.validate(
        new ExportOptions("2026-01-01", null, "alice", null, "csv", null)))
        .isNotEmpty();

assertThat(validator.validate(
        new ExportOptions(null, null, "alice", "secret", "csv", null)))
        .isNotEmpty();
```

Các assertion minh họa kiểm tra validator ở cấp object. Bổ sung kiểm thử tích hợp command để xác nhận option được bind đúng, lỗi được hiển thị và service nghiệp vụ không được gọi khi tổ hợp không hợp lệ.

## 14. Bài tập thực hành

Xây dựng command `connection test` nhận các option:

- `--url`: địa chỉ máy chủ, bắt buộc.
- `--username` và `--password`: phải đi cùng nhau.
- `--token`: loại trừ với cặp username/password.
- `--proxy` và `--proxy-port`: phải đi cùng nhau.

Yêu cầu:

1. Viết bảng quy tắc cho từng cặp và nhóm tham số.
2. Xác định `--token` và cặp username/password là quy tắc “chính xác một phương thức xác thực”.
3. Cài đặt validator để kiểm tra cặp username/password.
4. Kiểm tra `--token` không xuất hiện đồng thời với username hoặc password.
5. Kiểm tra `--proxy` và `--proxy-port` cùng có hoặc cùng vắng mặt.
6. Chỉ gọi service kiểm tra kết nối khi tất cả quy tắc đều hợp lệ.
7. Viết test cho trường hợp thiếu cả hai, có đúng một, có đủ cặp và truyền xung đột.
8. Bảo đảm thông báo lỗi không hiển thị password hoặc token.

**Kết quả cần nộp:** command, DTO hoặc validator, bảng tổ hợp đầu vào, kiểm thử cho các nhánh hợp lệ/không hợp lệ và bằng chứng service không được gọi khi validation thất bại.

## 15. Checklist thiết kế validation tổ hợp

- [ ] Đã phân biệt “không được có cả hai” với “phải có đúng một”.
- [ ] Đã xác định cặp nào phải đi cùng nhau và có được phép bỏ qua cả cặp không.
- [ ] Đã phân biệt phụ thuộc một chiều với quan hệ hai chiều.
- [ ] Đã kiểm tra điều kiện theo giá trị, không chỉ theo sự hiện diện của option.
- [ ] Quy tắc được thực thi sau khi bind tham số và trước side effect.
- [ ] Đã chọn đúng nơi đặt logic: command, validator, DTO hay service/domain.
- [ ] Nếu dùng Bean Validation, đã kích hoạt validation một cách tường minh cho DTO hoặc executable method.
- [ ] Không giả định Spring Shell tự động chạy cross-parameter constraint nếu chưa cấu hình integration.
- [ ] Thông báo lỗi nêu rõ các option liên quan và cách sửa.
- [ ] Không đưa mật khẩu, token hoặc dữ liệu bí mật vào log/thông báo lỗi.
- [ ] Đã kiểm thử toàn bộ tổ hợp quan trọng và xác nhận service không chạy khi input sai.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell Reference Documentation — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Jakarta Bean Validation 3.0 — Class-level and cross-parameter constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Bean Validation API — `ConstraintValidator`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator)
- [Jakarta Bean Validation API — `ExecutableValidator`](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executablevalidator)
- [Spring Framework Reference — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
