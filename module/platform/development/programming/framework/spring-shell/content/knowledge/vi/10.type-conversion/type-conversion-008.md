# Chuyển đổi thủ công trong phương thức xử lý khi cần hợp đồng rõ ràng

Spring Shell thường chuyển dữ liệu người dùng nhập thành kiểu tham số Java trước khi gọi phương thức command. Với những kiểu phổ biến như số, boolean hoặc enum, cơ chế chuyển đổi của Spring có thể đáp ứng trực tiếp. Tuy nhiên, có những command cần kiểm soát chính xác cách diễn giải đầu vào: định dạng ngày riêng, tên trạng thái có alias, số thập phân theo một quy ước cố định hoặc chuỗi cần chuẩn hóa theo nghiệp vụ.

Trong các trường hợp đó, có thể khai báo tham số nhận dữ liệu thô dưới dạng `String`, sau đó chuyển đổi ngay trong phương thức xử lý hoặc một hàm trợ giúp mà phương thức đó gọi. Cách này giúp hợp đồng CLI được thể hiện rõ: người dùng nhập dạng nào, ứng dụng hiểu ra sao và thông báo gì khi dữ liệu sai.

Bài học sử dụng annotation declarative của Spring Shell 4.x và API theo tài liệu 4.0.4.

## 1. Khi nào nên chuyển đổi trong command handler?

Hãy phân biệt hai tình huống:

- **Chuyển đổi thông thường:** người dùng nhập `42`, tham số command có kiểu `int count`. Spring Shell và Spring ConversionService có thể chuyển chuỗi đầu vào thành số nguyên trước khi gọi phương thức.
- **Chuyển đổi theo hợp đồng riêng:** người dùng nhập `15/03/2026`, `in-progress` hoặc `12.50%`. Ứng dụng cần quy định rõ định dạng và ý nghĩa, nên nhận `String` rồi tự phân tích.

Ví dụ:

| Đầu vào | Kiểu tham số | Cách xử lý |
|---|---|---|
| `--count=12` | `int count` | Để Spring Shell chuyển đổi |
| `--enabled=true` | `boolean enabled` | Để Spring Shell chuyển đổi |
| `--date=2026-03-15` | `LocalDate date` | Dùng chuyển đổi mặc định nếu định dạng mặc định phù hợp |
| `--date=15/03/2026` | `String rawDate` | Tự parse bằng formatter đã quy ước |
| `--status=in-progress` | `String rawStatus` | Tự ánh xạ alias sang enum/domain |
| `--rate=12.50` | `String rawRate` | Tự parse bằng `BigDecimal` và kiểm tra scale/miền giá trị |

Chuyển đổi thủ công có ích khi command cần một hợp đồng đầu vào cụ thể, nhưng không nên biến mọi tham số thành `String`. Nếu kiểu Java và định dạng mặc định đã phù hợp, để framework chuyển đổi sẽ giúp chữ ký phương thức thể hiện đúng kiểu dữ liệu và giảm mã xử lý lặp lại.

## 2. Luồng xử lý khi nhận dữ liệu thô

Khi tham số command được khai báo là `String`, luồng xử lý có thể mô tả như sau:

```text
Người dùng nhập command
          |
          v
Spring Shell phân tích tên command,
option và argument
          |
          v
Binding tham số String
          |
          v
Phương thức command được gọi
          |
          v
Chuẩn hóa đầu vào
          |
          v
Parse String thành kiểu đích
          |
          v
Kiểm tra quy tắc nghiệp vụ
          |
          v
Gọi application service
          |
          v
Trả kết quả hoặc báo lỗi
```

Các bước này có mục đích riêng:

1. **Phân tích cú pháp:** xác định giá trị thuộc option hay argument nào.
2. **Chuẩn hóa:** xử lý khoảng trắng, chữ hoa/chữ thường hoặc quy ước đầu vào nếu hợp đồng cho phép.
3. **Parse:** chuyển biểu diễn văn bản sang kiểu dữ liệu như `BigDecimal`, `LocalDate` hoặc enum.
4. **Validation:** kiểm tra giá trị đã chuyển đổi có nằm trong miền hợp lệ hay không.
5. **Thực thi:** chỉ gọi nghiệp vụ khi dữ liệu đã đạt các điều kiện cần thiết.

Nếu tham số được khai báo trực tiếp là `int`, `LocalDate` hoặc một kiểu khác, chuyển đổi tự động có thể thất bại trước khi phương thức command được gọi. Khi muốn tự quyết định thông báo và quy tắc parse, hãy nhận `String` ở biên CLI.

## 3. Chuyển chuỗi số thập phân bằng BigDecimal

Giả sử command áp dụng mức giảm giá theo phần trăm. Hợp đồng CLI quy định người dùng nhập số thập phân dùng dấu chấm, trong khoảng từ 0 đến 100:

```text
invoice discount --rate=12.50
```

Có thể nhận chuỗi thô và chuyển sang `BigDecimal`:

```java
import java.math.BigDecimal;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class InvoiceCommands {

    @Command(
        name = "invoice discount",
        description = "Áp dụng tỷ lệ giảm giá cho hóa đơn"
    )
    public String discount(
            @Option(longName = "rate", required = true)
            String rawRate) {

        BigDecimal rate = parseRate(rawRate);

        return "Discount rate: " + rate.toPlainString() + "%";
    }

    private BigDecimal parseRate(String rawRate) {
        if (rawRate == null || rawRate.isBlank()) {
            throw new IllegalArgumentException(
                "Tỷ lệ giảm giá không được để trống"
            );
        }

        String normalizedRate = rawRate.trim();
        if (!normalizedRate.matches("[+-]?\\d+(\\.\\d{1,2})?")) {
            throw new IllegalArgumentException(
                "Tỷ lệ phải là số thập phân dùng dấu chấm và tối đa hai chữ số sau dấu chấm"
            );
        }

        final BigDecimal rate;

        try {
            rate = new BigDecimal(normalizedRate);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Tỷ lệ phải là số thập phân dùng dấu chấm, ví dụ 12.50",
                ex
            );
        }

        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException(
                "Tỷ lệ giảm giá phải nằm trong khoảng từ 0 đến 100"
            );
        }

        return rate;
    }
}
```

Ví dụ ném `IllegalArgumentException` để dừng command ngay khi đầu vào sai. Trong ứng dụng thực tế, hãy cấu hình chính sách xử lý lỗi hoặc mapper phù hợp để thông báo dễ hiểu và mã thoát phản ánh đúng thất bại. Nếu script cần nhận biết lỗi, không nên bắt lỗi parse rồi trả về một chuỗi thông thường như thể command đã thành công.

Một số đầu vào:

| Đầu vào | Kết quả |
|---|---|
| `--rate=12.50` | Chấp nhận, giá trị `12.50` |
| `--rate=0` | Chấp nhận |
| `--rate=100` | Chấp nhận |
| `--rate=120` | Từ chối vì vượt giới hạn |
| `--rate=-5` | Từ chối vì nhỏ hơn 0 |
| `--rate=twelve` | Từ chối vì không parse được |
| `--rate=12.500` | Từ chối vì có quá hai chữ số thập phân |
| `--rate=12,50` | Từ chối vì hợp đồng dùng dấu chấm thập phân |
| `--rate=` | Từ chối vì giá trị rỗng |

Dùng `BigDecimal` cho dữ liệu tiền tệ hoặc tỷ lệ thập phân cần độ chính xác. Không nên chuyển qua `double` rồi mới tạo `BigDecimal`, vì biểu diễn nhị phân của `double` có thể làm phát sinh sai số.

Nếu command cần tính số tiền giảm, hãy xác định rõ quy tắc làm tròn:

Import `java.math.RoundingMode` ở đầu file. Sau khi đã có biến `total` và `rate`, biểu thức tính có thể viết như sau:

```java
BigDecimal discountAmount = total
    .multiply(rate)
    .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
```

`RoundingMode.HALF_UP` chỉ là một lựa chọn minh họa. Ứng dụng phải dùng quy tắc làm tròn phù hợp với nghiệp vụ và công bố nhất quán trong các luồng xử lý.

## 4. Chuyển ngày theo định dạng do ứng dụng quy định

Một command có thể yêu cầu ngày theo định dạng `dd/MM/uuuu`:

```text
report generate --from=15/03/2026
```

Tham số được nhận dưới dạng `String`, sau đó parse bằng `DateTimeFormatter`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    private static final DateTimeFormatter INPUT_DATE_FORMAT =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Command(
        name = "report generate",
        description = "Tạo báo cáo từ ngày được chỉ định"
    )
    public String generate(
            @Option(longName = "from", required = true)
            String rawDate) {

        LocalDate fromDate = parseDate(rawDate);

        return "Generating report from " + fromDate;
    }

    private LocalDate parseDate(String rawDate) {
        if (rawDate == null || rawDate.isBlank()) {
            throw new IllegalArgumentException(
                "Ngày bắt đầu không được để trống"
            );
        }

        try {
            return LocalDate.parse(rawDate.trim(), INPUT_DATE_FORMAT);
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                "Ngày phải có định dạng dd/MM/yyyy, ví dụ 15/03/2026",
                ex
            );
        }
    }
}
```

`ResolverStyle.STRICT` yêu cầu ngày thực sự hợp lệ theo lịch. Vì vậy, ngày như `31/02/2026` sẽ bị từ chối thay vì tự điều chỉnh sang một ngày khác.

Trong pattern của `DateTimeFormatter`, `uuuu` biểu diễn năm theo lịch (proleptic year) và phù hợp với việc parse ngày nghiêm ngặt. Không nên dùng `yyyy` một cách máy móc trong formatter strict, vì `yyyy` là year-of-era và có thể cần thông tin era để resolve đầy đủ.

Đầu vào:

| Giá trị | Kết quả |
|---|---|
| `15/03/2026` | Parse thành `LocalDate` |
| `01/01/2025` | Parse thành `LocalDate` |
| `31/02/2026` | Từ chối vì ngày không tồn tại |
| `2026-03-15` | Từ chối vì sai định dạng đã công bố |
| `15-03-2026` | Từ chối vì sai dấu phân cách |

Nếu hợp đồng CLI dùng ISO-8601, hãy cân nhắc dùng trực tiếp `LocalDate.parse(rawDate)` với định dạng ISO thay vì tự tạo formatter. Chỉ dùng parse thủ công khi muốn hỗ trợ một định dạng cụ thể khác hoặc cần thông báo lỗi theo ngôn ngữ nghiệp vụ.

## 5. Ánh xạ chuỗi sang enum khi CLI có alias

Chuyển đổi tự động sang enum thường dựa trên tên hằng enum. Tuy nhiên, giao diện CLI có thể cần tên dễ đọc hoặc alias khác với tên trong mã Java.

Giả sử ứng dụng có enum:

```java
public enum ExportFormat {
    CSV,
    JSON,
    YAML
}
```

Người dùng muốn nhập `yml` như alias của `YAML`, hoặc dùng chữ thường:

```text
data export --format=yml
data export --format=json
```

Có thể đặt hàm ánh xạ trong lớp command. Ví dụ sau cho thấy cả tham số nhận chuỗi thô và hàm chuyển đổi:

```java
import java.util.Locale;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DataCommands {

    @Command(name = "data export")
    public String export(
            @Option(longName = "format", required = true)
            String rawFormat) {

        ExportFormat format = parseFormat(rawFormat);
        return "Export format: " + format;
    }

    private ExportFormat parseFormat(String rawFormat) {
        if (rawFormat == null || rawFormat.isBlank()) {
            throw new IllegalArgumentException(
                "Định dạng xuất dữ liệu không được để trống"
            );
        }

        return switch (rawFormat.trim().toLowerCase(Locale.ROOT)) {
            case "csv" -> ExportFormat.CSV;
            case "json" -> ExportFormat.JSON;
            case "yaml", "yml" -> ExportFormat.YAML;
            default -> throw new IllegalArgumentException(
                "Định dạng không hợp lệ. Chọn một trong: csv, json, yaml, yml"
            );
        };
    }
}
```

Dùng `Locale.ROOT` khi chuẩn hóa các token kỹ thuật không phụ thuộc ngôn ngữ người dùng. Không nên dùng locale mặc định của máy để chuyển chữ hoa/chữ thường cho các mã CLI, vì cùng một đầu vào có thể cho kết quả khác nhau trên môi trường khác nhau.

Ánh xạ thủ công cũng giúp kiểm soát alias và thông báo lỗi. Khi thêm một định dạng mới, hãy cập nhật cả enum, hàm parse và danh sách giá trị hợp lệ trong help.

## 6. Chuẩn hóa chuỗi trước khi chuyển đổi

Đầu vào có thể chứa khoảng trắng ở hai đầu hoặc cách viết không thống nhất. Nếu hợp đồng cho phép bỏ qua khoảng trắng và không phân biệt chữ hoa/chữ thường, hãy chuẩn hóa trước khi parse.

Ví dụ:

Enum dùng trong ví dụ:

```java
public enum ProjectStatus {
    NEW,
    IN_PROGRESS,
    COMPLETED
}
```

Trong lớp command đã import `java.util.Locale`, helper có thể ánh xạ alias như sau:

```java
private ProjectStatus parseStatus(String rawStatus) {
    if (rawStatus == null || rawStatus.isBlank()) {
        throw new IllegalArgumentException("Mã trạng thái không được để trống");
    }

    String code = rawStatus.trim().toLowerCase(Locale.ROOT);
    return switch (code) {
        case "new" -> ProjectStatus.NEW;
        case "in-progress", "in_progress" -> ProjectStatus.IN_PROGRESS;
        case "done", "completed" -> ProjectStatus.COMPLETED;
        default -> throw new IllegalArgumentException(
            "Trạng thái không được hỗ trợ: " + rawStatus
        );
    };
}
```

Không chuẩn hóa tùy tiện dữ liệu có ý nghĩa phân biệt chữ hoa/chữ thường, chẳng hạn password, token, mã định danh phân biệt hoa thường hoặc nội dung tự do. Chuẩn hóa phải là một phần của hợp đồng đầu vào đã công bố.

## 7. Phân biệt parse và validation

Parse và validation thường xảy ra gần nhau nhưng trả lời hai câu hỏi khác nhau:

- **Parse:** chuỗi có thể được chuyển thành kiểu dữ liệu đích không?
- **Validation:** giá trị đã chuyển đổi có thỏa điều kiện được phép không?

Ví dụ với ngày bắt đầu báo cáo:

| Đầu vào | Parse | Validation nghiệp vụ |
|---|---|---|
| `15/03/2026` | Thành công | Có thể hợp lệ |
| `31/02/2026` | Thất bại | Chưa đến bước validation |
| `15/03/2026` nhưng lớn hơn ngày hiện tại | Thành công | Có thể bị từ chối theo quy tắc báo cáo |
| `01/01/1900` | Thành công | Có thể bị từ chối nếu hệ thống không hỗ trợ dữ liệu quá cũ |

Tương tự, chuỗi `-5` có thể parse thành số nguyên thành công, nhưng bị validation từ chối nếu tham số phải dương.

Nên giữ hai loại lỗi riêng biệt trong mã nguồn và thông báo:

- Lỗi định dạng: “Ngày phải có định dạng dd/MM/yyyy”.
- Lỗi miền giá trị: “Ngày bắt đầu không được nằm trong tương lai”.

Thông báo cụ thể giúp người dùng sửa đúng vấn đề. Không nên dùng một thông báo chung như “Invalid input” cho mọi lỗi.

## 8. Giữ hàm chuyển đổi nhỏ và dễ kiểm thử

Nếu logic parse chỉ phục vụ một command, có thể đặt trong private method của lớp command. Nếu nhiều command hoặc service cần cùng một quy tắc, hãy chuyển hàm đó sang một thành phần dùng chung.

Ví dụ tách parser thành lớp riêng:

```java
import java.math.BigDecimal;

import org.springframework.stereotype.Component;

@Component
public class RateParser {

    public BigDecimal parsePercentage(String rawValue) {
        if (rawValue == null || rawValue.isBlank()) {
            throw new IllegalArgumentException(
                "Tỷ lệ không được để trống"
            );
        }

        final BigDecimal value;

        try {
            value = new BigDecimal(rawValue.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "Tỷ lệ phải là số thập phân hợp lệ",
                ex
            );
        }

        if (value.signum() < 0
                || value.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException(
                "Tỷ lệ phải nằm trong khoảng từ 0 đến 100"
            );
        }

        return value;
    }
}
```

Command chỉ điều phối:

```java
@Component
public class PricingCommands {

    private final RateParser rateParser;

    public PricingCommands(RateParser rateParser) {
        this.rateParser = rateParser;
    }

    @Command(name = "pricing set-rate")
    public String setRate(
            @Option(longName = "rate", required = true)
            String rawRate) {

        BigDecimal rate = rateParser.parsePercentage(rawRate);
        return "Rate: " + rate.toPlainString();
    }
}
```

Cách tổ chức này giúp kiểm thử parser mà không cần khởi động shell. Command handler cũng dễ đọc hơn vì tập trung vào luồng sử dụng dữ liệu.

## 9. Khi nào nên dùng Converter hoặc ConversionService?

Chuyển đổi thủ công trong command handler phù hợp khi quy tắc chỉ phục vụ một command hoặc gắn chặt với hợp đồng CLI của command đó. Nếu cùng một kiểu dữ liệu được nhận ở nhiều command và nhiều thành phần, việc lặp lại hàm parse sẽ tạo ra các cách diễn giải không thống nhất.

Khi cần tái sử dụng, cân nhắc:

- **Spring `Converter<S, T>`:** phù hợp với một phép chuyển đổi rõ ràng từ kiểu nguồn sang kiểu đích.
- **`ConverterFactory<S, T>`:** phù hợp khi cần chuyển đổi cho một họ kiểu đích, ví dụ các kiểu enum.
- **`GenericConverter`:** dùng khi cần thông tin kiểu nguồn/đích hoặc hỗ trợ nhiều cặp kiểu phức tạp.
- **`ConversionService`:** API để gọi các converter đã đăng ký từ bất kỳ thành phần nào cần chuyển đổi.

Spring Shell sử dụng cơ chế chuyển đổi của Spring khi binding tham số command. API của `MethodInvokerCommandAdapter` nhận một `ConfigurableConversionService` để chuyển đổi tham số phương thức. Vì vậy, nếu muốn một kiểu tùy chỉnh được binding tự động ở nhiều command, converter đăng ký trong Spring context thường là hướng phù hợp hơn.

| Nhu cầu | Hướng xử lý |
|---|---|
| Chỉ một command chấp nhận định dạng `dd/MM/uuuu` | Nhận `String` và parse trong handler |
| Nhiều command cùng nhận một loại mã định danh | Tạo `Converter<String, ProjectId>` |
| Nhiều kiểu enum có quy tắc ánh xạ chung | Cân nhắc `ConverterFactory` |
| Cần parse dữ liệu theo ngữ cảnh riêng của từng lệnh | Giữ logic trong handler hoặc application service |
| Cần gọi chuyển đổi từ nhiều tầng ứng dụng | Inject `ConversionService` và gọi `convert(...)` |

Không nên tạo custom converter chỉ để thay một phép `Integer.parseInt` đơn giản ở một command. Ngược lại, cũng không nên sao chép một quy tắc định danh hoặc định dạng dùng chung vào nhiều handler.

## 10. Kiểm thử các trường hợp chuyển đổi

Hàm chuyển đổi thủ công nên được kiểm thử với cả đầu vào hợp lệ và không hợp lệ. Một bảng trường hợp giúp tránh chỉ kiểm tra happy path:

| Nhóm | Đầu vào thử | Kỳ vọng |
|---|---|---|
| Số thập phân | `12.50` | Parse thành `BigDecimal` |
| Số thập phân | `abc` | Báo lỗi định dạng |
| Số thập phân | `-1` | Parse thành công, validation từ chối |
| Số thập phân | Chuỗi rỗng | Báo lỗi bắt buộc |
| Ngày | `15/03/2026` | Parse thành công |
| Ngày | `31/02/2026` | Báo lỗi ngày không tồn tại |
| Ngày | `2026-03-15` | Báo lỗi nếu hợp đồng yêu cầu `dd/MM/uuuu` |
| Enum alias | `yml` | Ánh xạ thành `YAML` |
| Enum alias | `JSON` | Chuẩn hóa rồi ánh xạ thành `JSON` |
| Enum alias | `toml` | Báo danh sách định dạng được hỗ trợ |

Có thể viết unit test trực tiếp cho parser:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class RateParserTests {

    private final RateParser parser = new RateParser();

    @Test
    void parsesValidPercentage() {
        assertEquals(
            new BigDecimal("12.50"),
            parser.parsePercentage(" 12.50 ")
        );
    }

    @Test
    void rejectsInvalidNumber() {
        assertThrows(
            IllegalArgumentException.class,
            () -> parser.parsePercentage("twelve")
        );
    }

    @Test
    void rejectsPercentageAboveMaximum() {
        assertThrows(
            IllegalArgumentException.class,
            () -> parser.parsePercentage("120")
        );
    }
}
```

Ngoài unit test cho hàm parse, nên có kiểm thử command để xác nhận option được binding vào tham số `String` và lỗi được hiển thị theo chính sách ứng dụng. Hai lớp kiểm thử này xác minh hai ranh giới khác nhau.

## 11. Các lỗi thường gặp

**Nhận kiểu đích rồi lại parse lần nữa.** Nếu tham số đã là `int`, `BigDecimal` hoặc `LocalDate`, Spring Shell đã thực hiện binding trước khi gọi handler. Không cần chuyển đổi lại từ chính kiểu đó.

**Nhận String nhưng không công bố định dạng.** Người dùng không biết nên nhập `2026-03-15` hay `15/03/2026`. Ghi rõ định dạng trong `description`, `help` và thông báo lỗi.

**Dùng double cho số tiền.** Sai số dấu phẩy động có thể ảnh hưởng đến kết quả tính toán. Dùng `BigDecimal` khi cần độ chính xác thập phân.

**Dùng formatter mặc định của máy.** Cùng một chuỗi có thể được hiểu khác nhau theo locale. Quy định rõ dấu thập phân, thứ tự ngày/tháng/năm và locale.

**Dùng formatter không strict.** Ngày sai có thể bị điều chỉnh hoặc diễn giải ngoài ý muốn. Dùng `ResolverStyle.STRICT` khi hợp đồng yêu cầu ngày lịch hợp lệ.

**Gộp parse và validation thành một nhánh khó đọc.** Hãy parse trước, sau đó kiểm tra miền giá trị để thông báo lỗi đúng nguyên nhân.

**Chuẩn hóa mọi chuỗi bằng lowercase.** Dữ liệu phân biệt hoa thường có thể bị thay đổi. Chỉ chuẩn hóa các token kỹ thuật mà hợp đồng cho phép.

**Bắt lỗi rồi tiếp tục với giá trị mặc định âm thầm.** Điều này có thể khiến command thực hiện sai thao tác. Nếu dữ liệu bắt buộc không hợp lệ, báo lỗi rõ ràng và dừng luồng xử lý.

**Lặp lại cùng quy tắc parse ở nhiều command.** Chuyển logic dùng chung sang helper, application service hoặc Spring Converter để giữ một cách diễn giải thống nhất.

## 12. Checklist chuyển đổi thủ công trong command handler

- [ ] Xác định rõ vì sao kiểu chuyển đổi mặc định chưa đáp ứng hợp đồng đầu vào.
- [ ] Khai báo tham số thô bằng `String` tại biên CLI.
- [ ] Công bố định dạng và ví dụ đầu vào trong mô tả/help.
- [ ] Chuẩn hóa chuỗi chỉ theo quy tắc đã công bố.
- [ ] Dùng API parse phù hợp với kiểu đích (`BigDecimal`, `LocalDate`, enum mapping...).
- [ ] Dùng formatter và locale tường minh khi xử lý ngày hoặc số theo định dạng riêng.
- [ ] Phân biệt lỗi parse với lỗi validation.
- [ ] Không dùng `double` cho phép tính tiền cần độ chính xác thập phân.
- [ ] Không thay thế đầu vào sai bằng giá trị mặc định một cách âm thầm.
- [ ] Tách hàm parse ra helper/service nếu cần tái sử dụng.
- [ ] Dùng Spring `Converter` khi cùng một quy tắc cần áp dụng ở nhiều command.
- [ ] Kiểm thử đầu vào hợp lệ, rỗng, sai định dạng và ngoài miền giá trị.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 4.0.4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): khai báo option/argument, binding tham số và validation command.
- [Spring Shell 4.0.4 — Option API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): thuộc tính `required`, `defaultValue`, `longName` và `shortName`.
- [Spring Shell 4.x — MethodInvokerCommandAdapter API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html): adapter gọi phương thức command và sử dụng `ConfigurableConversionService` cho chuyển đổi tham số.
- [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConverterFactory`, `GenericConverter` và `ConversionService`.
- [Java — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng và parse ngày giờ.
- [Java — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): biểu diễn và tính toán số thập phân chính xác.

Chuyển đổi thủ công phù hợp khi command cần kiểm soát định dạng, alias hoặc cách diễn giải riêng của đầu vào. Hãy nhận dữ liệu thô ở biên CLI, parse bằng API có quy tắc rõ ràng, kiểm tra nghiệp vụ sau khi parse và chỉ đưa logic sang converter dùng chung khi nhiều nơi thực sự cần cùng một phép chuyển đổi.

