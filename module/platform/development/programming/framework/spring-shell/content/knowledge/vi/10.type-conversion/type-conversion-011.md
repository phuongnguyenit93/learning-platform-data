# Thông báo lỗi chuyển đổi kèm tên tùy chọn và ví dụ hợp lệ

Khi người dùng nhập sai giá trị cho một option, thông báo lỗi cần giúp họ sửa ngay dòng lệnh. Một thông báo hữu ích nên chỉ rõ tên option, giá trị hoặc định dạng được yêu cầu và ít nhất một ví dụ hợp lệ. Chẳng hạn, thay vì chỉ báo “không thể chuyển chuỗi sang ngày”, CLI nên nói rõ `--from` phải theo định dạng `yyyy-MM-dd`, ví dụ `2026-11-26`.

Spring Shell 4.x kết hợp cơ chế chuyển đổi kiểu của Spring Framework với Bean Validation. Bean Validation có thể tự hiển thị tên option cùng thông điệp ràng buộc. Với lỗi chuyển đổi xảy ra trước khi phương thức command được gọi, cần thiết kế lớp đầu vào phù hợp để giữ được ngữ cảnh của option. Bài học này trình bày cách phân loại lỗi, tạo thông báo có thể hành động và kiểm thử nội dung lỗi.

## 1. Một thông báo lỗi chuyển đổi tốt cần có gì?

Hãy xem người dùng gọi:

~~~text
report --from=26/11/2026 --limit=abc
~~~

Một lỗi chung như `Conversion failed` không cho biết người dùng phải sửa phần nào. Thông báo tốt nên có các thành phần:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Tên option | Xác định vị trí cần sửa | `--from` |
| Giá trị hoặc loại dữ liệu mong đợi | Nói rõ định dạng được chấp nhận | Ngày theo `yyyy-MM-dd` |
| Ví dụ hợp lệ | Cho người dùng một mẫu có thể sao chép | `--from=2026-11-26` |
| Phạm vi hợp lệ | Nêu giới hạn nếu có | `--limit` là số nguyên từ 1 đến 500 |
| Hành động tiếp theo | Hướng dẫn cách sửa | Đổi giá trị và chạy lại command |

Ví dụ thông báo:

~~~text
--from: phải có dạng yyyy-MM-dd (ví dụ: 2026-11-26).
--limit: phải là số nguyên từ 1 đến 500 (ví dụ: 25).
~~~

Giữ thông báo ngắn, gắn với option cụ thể và tránh hiển thị stack trace cho lỗi nhập liệu thông thường.

## 2. Xác định lỗi xảy ra ở giai đoạn nào

Một dòng lệnh đi qua nhiều bước. Vị trí lỗi quyết định cách bổ sung tên option và ví dụ hợp lệ:

~~~mermaid
flowchart TD
    A[Người dùng nhập command] --> B[CommandParser phân tích cú pháp]
    B --> C[Chuyển đổi String sang kiểu Java]
    C --> D[Bean Validation]
    D --> E[Phương thức command]
    E --> F[Kiểm tra quy tắc nghiệp vụ]
    F --> G[Service và kết quả]
~~~

| Giai đoạn | Ví dụ lỗi | Cách tạo thông báo |
|---|---|---|
| Parsing | Thiếu giá trị sau `--limit` hoặc sai cú pháp option | Sửa cú pháp và trợ giúp command |
| Type conversion | `abc` không chuyển được thành `Integer` | Giữ đầu vào dưới dạng `String` để xác thực định dạng trước khi parse, hoặc dùng converter có thông điệp rõ |
| Bean Validation | Chuỗi không khớp định dạng ngày | Đặt `message` trên constraint; Spring Shell tự gắn tên option vào lỗi |
| Kiểm tra nghiệp vụ | Ngày hợp lệ về cú pháp nhưng không được phép trong báo cáo | Ném lỗi có tên option, quy tắc và ví dụ |
| Thực thi | Service không truy cập được dữ liệu | Xử lý như lỗi nghiệp vụ hoặc lỗi hệ thống, không mô tả nhầm thành lỗi chuyển đổi |

Điểm quan trọng: khi tham số được khai báo kiểu `Integer`, `LocalDate` hoặc kiểu miền tùy chỉnh, Spring phải chuyển chuỗi đầu vào trước khi gọi phương thức command. Nếu chuyển đổi thất bại, phần thân phương thức và các constraint trên tham số chưa có cơ hội chạy. Vì thế, `@Min` có thể kiểm tra một số nguyên đã chuyển đổi, nhưng không thể tự mô tả tốt trường hợp người dùng nhập `abc` vào một tham số `Integer`.

## 3. Dùng Bean Validation để tự gắn tên option vào thông báo

Spring Shell tích hợp Bean Validation. Các constraint đặt trên tham số command được kiểm tra trước khi phương thức thực thi. Khi vi phạm, Spring Shell hiển thị tên option cùng thông điệp constraint. Tài liệu chính thức minh họa kết quả dạng:

~~~text
The following constraints were not met:
    --password: size must be between 8 and 40
Error while executing command change-password: USAGE_ERROR
~~~

Để tự viết nội dung hướng dẫn, đặt thuộc tính `message` trên constraint. Với dữ liệu văn bản như ngày hoặc số nguyên, có thể nhận giá trị dưới dạng `String`, kiểm tra hình dạng bằng `@Pattern`, rồi chuyển sang kiểu Java sau khi đầu vào đã qua kiểm tra.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import jakarta.validation.constraints.Pattern;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(
            name = "report",
            description = "Tạo báo cáo theo ngày",
            help = "Usage: report --from=<yyyy-MM-dd> [--limit=<number>]"
    )
    public String report(
            @Option(
                    longName = "from",
                    required = true,
                    description = "Ngày bắt đầu theo yyyy-MM-dd"
            )
            @Pattern(
                    regexp = "\\d{4}-\\d{2}-\\d{2}",
                    message = "phải có dạng yyyy-MM-dd (ví dụ: 2026-11-26)"
            )
            String fromText,

            @Option(
                    longName = "limit",
                    defaultValue = "20",
                    description = "Số bản ghi từ 1 đến 500"
            )
            @Pattern(
                    regexp = "\\d+",
                    message = "phải là số nguyên dương từ 1 đến 500 (ví dụ: 25)"
            )
            String limitText) {

        LocalDate from;
        try {
            from = LocalDate.parse(fromText);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException(
                    "Option --from phải là ngày lịch hợp lệ theo dạng "
                    + "yyyy-MM-dd (ví dụ: --from=2026-11-26).",
                    exception
            );
        }

        int limit;
        try {
            limit = Integer.parseInt(limitText);
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(
                    "Option --limit phải là số nguyên từ 1 đến 500 "
                    + "(ví dụ: --limit=25).",
                    exception
            );
        }

        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException(
                    "Option --limit phải nằm trong khoảng 1 đến 500 "
                    + "(ví dụ: --limit=25)."
            );
        }

        return "Tạo báo cáo từ " + from + ", giới hạn " + limit + " bản ghi.";
    }
}
~~~

Trong ứng dụng, thêm implementation Bean Validation tương ứng, ví dụ dependency `spring-boot-starter-validation` khi dùng Spring Boot.

Khi người dùng nhập `--limit=abc`, constraint trên tham số `String` có thể chạy và đưa ra lỗi gắn với `--limit`. Nếu nhập `--limit=900`, chuỗi vẫn đúng hình dạng số; bước kiểm tra miền giá trị trong phương thức tạo thông báo cụ thể cho giới hạn 1 đến 500.

`@Pattern` chỉ kiểm tra hình dạng chuỗi. Biểu thức ngày `\\d{4}-\\d{2}-\\d{2}` vẫn cho phép các chuỗi như `2026-19-45`. Cần chuyển bằng `LocalDate.parse()` để kiểm tra ngày lịch thực sự.

## 4. Phân biệt lỗi định dạng và lỗi giá trị

Một giá trị có thể đúng định dạng nhưng không hợp lệ về miền hoặc quy tắc nghiệp vụ:

| Option | Đúng hình dạng | Giá trị hợp lệ | Ví dụ lỗi |
|---|---|---|---|
| `--from` | `yyyy-MM-dd` | Ngày lịch có thật | `2026-19-45` |
| `--limit` | Chỉ gồm chữ số | Số nguyên từ 1 đến 500 | `900` |
| `--format` | Chuỗi văn bản | `csv` hoặc `json` | `xml` |
| `--port` | Chỉ gồm chữ số | Số nguyên từ 1 đến 65535 | `70000` |

Nên tách việc kiểm tra thành hai bước:

1. Kiểm tra cú pháp hoặc hình dạng bằng Bean Validation.
2. Chuyển sang kiểu Java và kiểm tra miền giá trị bằng code hoặc constraint phù hợp.

Ví dụ với ngày:

~~~java
LocalDate parseFromDate(String rawValue) {
    try {
        return LocalDate.parse(rawValue);
    } catch (DateTimeParseException exception) {
        throw new IllegalArgumentException(
                "Option --from phải là ngày lịch hợp lệ theo dạng "
                + "yyyy-MM-dd (ví dụ: --from=2026-11-26).",
                exception
        );
    }
}
~~~

Ví dụ với số:

~~~java
int parseLimit(String rawValue) {
    final int limit;
    try {
        limit = Integer.parseInt(rawValue);
    } catch (NumberFormatException exception) {
        throw new IllegalArgumentException(
                "Option --limit phải là số nguyên từ 1 đến 500 "
                + "(ví dụ: --limit=25).",
                exception
        );
    }

    if (limit < 1 || limit > 500) {
        throw new IllegalArgumentException(
                "Option --limit phải nằm trong khoảng 1 đến 500 "
                + "(ví dụ: --limit=25)."
        );
    }
    return limit;
}
~~~

Các hàm trên nhận tên option trong nội dung thông báo. Có thể dùng lại cách viết này khi nhiều command cần cùng một quy tắc, hoặc chuyển thành helper chuyên biệt cho từng loại dữ liệu.

## 5. Khi nào nên nhận String thay vì kiểu đích?

Chọn kiểu tham số dựa trên trải nghiệm lỗi mong muốn:

| Cách khai báo | Ưu điểm | Hạn chế |
|---|---|---|
| `@Option Integer limit` | Code command nhận được số đã chuyển đổi | Chuỗi không phải số thất bại trước khi vào phương thức |
| `@Option String limit` + `@Pattern` + parse | Có thể gắn lỗi định dạng với tên option và ví dụ | Phải tự chuyển kiểu và kiểm tra miền giá trị |
| `@Option LocalDate from` | Phương thức nhận trực tiếp ngày | Lỗi parse ngày có thể không chứa hướng dẫn theo nghiệp vụ |
| `@Option String from` + `LocalDate.parse` | Có thể kiểm soát định dạng và ví dụ cụ thể | Cần tự xử lý lỗi chuyển đổi và ngày không hợp lệ |

Nếu cần thông báo lỗi theo đúng tên option, giữ giá trị đầu vào ở dạng `String` là cách dễ kiểm soát. Sau khi xác thực, chuyển nó sang kiểu Java trước khi gọi service.

`ConversionFailedException` của Spring Framework cung cấp kiểu nguồn, kiểu đích và giá trị gây lỗi. Nó không có thuộc tính riêng cho tên option của Spring Shell. Vì vậy, nếu giao diện cần chỉ rõ `--limit` hoặc `--from` cùng ví dụ hợp lệ, hãy bổ sung ngữ cảnh đó ở lớp command/validation.

Với kiểu đơn giản và lỗi chuyển đổi mặc định đã đủ rõ, vẫn có thể khai báo kiểu đích trực tiếp:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "count")
public String count(
        @Option(longName = "limit", defaultValue = "20")
        @Min(value = 1, message = "phải lớn hơn hoặc bằng 1")
        @Max(value = 500, message = "không được vượt quá 500")
        Integer limit) {
    return "Limit: " + limit;
}
~~~

Trong ví dụ này, `@Min` và `@Max` kiểm tra giá trị Integer đã được chuyển đổi. Nếu người dùng nhập `--limit=abc`, lỗi chuyển đổi xảy ra trước validation. Khi yêu cầu sản phẩm bắt buộc hiển thị ví dụ hợp lệ cho cả đầu vào không phải số, dùng `String` kết hợp `@Pattern` và parse thủ công.

## 6. Converter tùy chỉnh và giới hạn về ngữ cảnh option

Spring Framework cung cấp `Converter<S, T>` để chuyển một kiểu nguồn sang kiểu đích. Converter nhận giá trị nguồn qua phương thức `convert(S source)` và có thể ném `IllegalArgumentException` khi dữ liệu không hợp lệ.

Ví dụ converter cho một kiểu định dạng báo cáo:

~~~java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

enum ReportFormat {
    CSV, JSON
}

@Component
class StringToReportFormatConverter
        implements Converter<String, ReportFormat> {

    @Override
    public ReportFormat convert(String source) {
        try {
            return ReportFormat.valueOf(
                    source.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "Định dạng báo cáo không hợp lệ; giá trị hỗ trợ là "
                    + "csv hoặc json (ví dụ: --format=csv).",
                    exception
            );
        }
    }
}
~~~

Converter phù hợp để gom quy tắc chuyển đổi cho kiểu miền dùng lại ở nhiều nơi. Tuy nhiên, chữ ký `Converter<String, ReportFormat>` chỉ nhận chuỗi nguồn, không nhận tên option như `--format`. Vì vậy, converter dùng chung khó tạo thông báo có đúng tên option trong mọi command. Hãy đưa ví dụ giá trị hợp lệ vào thông điệp của kiểu miền; dùng Bean Validation hoặc parse tại command khi cần gắn tên option chính xác.

Khi dùng converter trong ứng dụng Spring Shell 4.x, đăng ký converter dưới dạng Spring bean và dùng phiên bản Spring Shell có hỗ trợ đúng mô hình command đang chạy. Bản 4.0.3 đã sửa lỗi converter tùy chỉnh không hoạt động với command khai báo bằng annotation.

## 7. Dùng ExitStatusExceptionMapper cho lỗi do command phát sinh

Khi command đã bắt đầu thực thi và tự phát hiện giá trị không hợp lệ, có thể dùng `ExitStatusExceptionMapper` để ánh xạ exception thành mã trạng thái và thông điệp thân thiện. Spring Shell hỗ trợ gắn mapper bằng tên bean trong `@Command`.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper usageErrorMapper() {
        return exception -> {
            if (exception instanceof IllegalArgumentException) {
                String message = exception.getMessage() == null
                        ? "Giá trị đầu vào không hợp lệ."
                        : exception.getMessage();
                return new ExitStatus(
                        ExitStatus.USAGE_ERROR.code(), message);
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Gắn mapper vào command:

~~~java
@Command(
        name = "report",
        exitStatusExceptionMapper = "usageErrorMapper"
)
public String report(
        @Option(longName = "from", required = true) String fromText) {

    LocalDate from = parseFromDate(fromText);
    return "Báo cáo từ " + from;
}
~~~

`ExitStatusExceptionMapper` xử lý exception phát sinh trong quá trình thực thi command. Không dùng nó để thay thế Bean Validation cho lỗi constraint, hoặc giả định nó có thể sửa mọi lỗi parsing và chuyển đổi xảy ra trước khi phương thức command được gọi. Đối với lỗi đầu vào ở giai đoạn validation, đặt thông điệp trực tiếp trên constraint để Spring Shell gắn tên option.

Mã trạng thái command cũng khác với mã thoát của tiến trình JVM. Mapper điều khiển `ExitStatus` của command; việc kết thúc tiến trình với mã phù hợp là phần cấu hình riêng của ứng dụng.

## 8. Viết thông điệp validation có ví dụ hợp lệ

Một số quy tắc khi viết thông điệp:

- Gọi đúng tên option bằng tiền tố `--` hoặc `-`.
- Nêu rõ kiểu dữ liệu hoặc định dạng cần có.
- Ghi ví dụ theo đúng cú pháp Spring Shell.
- Nêu miền hợp lệ nếu giá trị có giới hạn.
- Không đưa stack trace hoặc tên class Java vào thông báo dành cho người dùng.
- Không in token, mật khẩu hoặc dữ liệu nhạy cảm trong thông báo lỗi.

Ví dụ thông điệp:

| Option | Thông điệp nên dùng |
|---|---|
| `--from` | `phải có dạng yyyy-MM-dd (ví dụ: --from=2026-11-26)` |
| `--limit` | `phải là số nguyên từ 1 đến 500 (ví dụ: --limit=25)` |
| `--format` | `chỉ nhận csv hoặc json (ví dụ: --format=csv)` |
| `--port` | `phải là số nguyên từ 1 đến 65535 (ví dụ: --port=8080)` |
| `--output` | `phải là đường dẫn file hợp lệ (ví dụ: --output=reports/result.csv)` |

Nếu thông điệp đến từ Bean Validation, không cần lặp lại tên option trong thuộc tính `message` vì Spring Shell đã thêm tên option vào phần hiển thị. Có thể chỉ viết phần mô tả sau dấu hai chấm, ví dụ `phải là số nguyên từ 1 đến 500 (ví dụ: 25)`.

## 9. Kiểm thử nội dung thông báo lỗi

Kiểm thử command nên xác nhận thông báo có cả tên option và ví dụ hợp lệ. Ví dụ với `ShellTestClient`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = {
        ReportCommands.class,
        ShellErrorConfiguration.class
})
class ReportCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void reportsTheOptionNameAndValidDateExample() throws Exception {
        ShellScreen screen = client.sendCommand(
                "report --from=26/11/2026");

        ShellAssertions.assertThat(screen)
                .containsText("--from")
                .containsText("yyyy-MM-dd")
                .containsText("2026-11-26");
    }

    @Test
    void reportsTheOptionNameAndValidLimitExample() throws Exception {
        ShellScreen screen = client.sendCommand(
                "report --from=2026-11-26 --limit=abc");

        ShellAssertions.assertThat(screen)
                .containsText("--limit")
                .containsText("1 đến 500")
                .containsText("25");
    }
}
~~~

Nên có các trường hợp kiểm thử riêng:

1. Sai hình dạng chuỗi, chẳng hạn ngày `26/11/2026`.
2. Đúng hình dạng nhưng sai giá trị, chẳng hạn ngày `2026-19-45`.
3. Sai kiểu số, chẳng hạn `--limit=abc`.
4. Đúng kiểu nhưng vượt miền, chẳng hạn `--limit=900`.
5. Thiếu option bắt buộc.
6. Giá trị hợp lệ, để chắc chắn thông báo lỗi không xuất hiện nhầm.

Không chỉ kiểm tra rằng màn hình có chữ “error”. Hãy xác nhận chính xác option, định dạng hoặc miền giá trị và ví dụ mà người dùng có thể nhập lại.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lỗi chỉ ghi `Failed to convert` | Dùng tham số kiểu đích và phụ thuộc hoàn toàn vào lỗi chuyển đổi mặc định | Nhận `String`, kiểm tra bằng `@Pattern`, sau đó parse |
| `@Min` không báo lỗi cho `abc` theo cách mong muốn | Chuyển đổi sang số thất bại trước khi validation chạy | Kiểm tra hình dạng chuỗi trước khi chuyển sang số |
| Thông báo không có tên option | Lỗi được ném từ helper hoặc converter dùng chung | Gắn lỗi với tham số bằng Bean Validation hoặc thêm tên option vào thông điệp tại command |
| Regex chấp nhận ngày không tồn tại | Regex chỉ kiểm tra hình dạng, không kiểm tra lịch | Dùng `LocalDate.parse()` và bắt `DateTimeParseException` |
| Người dùng không biết giá trị hợp lệ | Message chỉ nói “invalid value” | Thêm định dạng, giới hạn và ví dụ |
| Mapper không xử lý lỗi validation | Mapper dành cho exception trong quá trình thực thi command | Dùng `message` của Bean Validation cho lỗi constraint |
| Stack trace làm rối terminal | Hiển thị exception kỹ thuật cho lỗi nhập liệu | Trả thông báo ngắn và giữ nguyên cause trong log nội bộ nếu cần |

## 11. Bài tập thực hành

Tạo command `user search` với hai option:

- `--created-after`: ngày theo định dạng `yyyy-MM-dd`, bắt buộc.
- `--limit`: số nguyên từ 1 đến 100, mặc định là 20.

Yêu cầu:

1. Nếu ngày không đúng định dạng, hiển thị tên `--created-after`, định dạng mong đợi và ví dụ `2026-11-26`.
2. Nếu ngày có hình dạng đúng nhưng không tồn tại, hiển thị thông báo ngày lịch không hợp lệ và ví dụ hợp lệ.
3. Nếu `--limit` không phải số nguyên, hiển thị tên option và ví dụ `--limit=25`.
4. Nếu `--limit` ngoài khoảng 1 đến 100, hiển thị giới hạn cùng ví dụ.
5. Viết `ShellTestClient` test cho ít nhất một lỗi định dạng, một lỗi miền giá trị và một trường hợp thành công.

Thử các lệnh:

~~~text
user search --created-after=26/11/2026
user search --created-after=2026-19-45
user search --created-after=2026-11-26 --limit=abc
user search --created-after=2026-11-26 --limit=500
user search --created-after=2026-11-26 --limit=25
~~~

## Tài liệu tham khảo

- [Spring Shell – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.3 Release Notes – Custom converter fix](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.3)
- [Spring Shell API – @Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell API – ExitStatusExceptionMapper](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework API – ConversionFailedException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/ConversionFailedException.html)
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)
