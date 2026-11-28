# Kiểu số, Boolean, enum và quy tắc biểu diễn

Khi Spring Shell nhận một command, các token người dùng nhập ban đầu đều là văn bản. Trước khi gọi method Java, Spring Shell chuyển các giá trị đó sang kiểu của tham số đã khai báo, chẳng hạn `int`, `BigDecimal`, `boolean` hoặc một kiểu `enum`. Bước này được gọi là **type conversion** (chuyển đổi kiểu).

Chuyển đổi kiểu giúp command nhận dữ liệu có cấu trúc và hạn chế việc parse thủ công trong từng method. Tuy nhiên, người thiết kế CLI cần quy định rõ cách viết số, giá trị Boolean và tên enum để lời gọi dễ đoán, nhất quán giữa các môi trường. Bài viết tập trung vào annotation API của Spring Shell 4.x, cách biểu diễn dữ liệu, lỗi chuyển đổi và cách mở rộng khi định dạng mặc định không đáp ứng nghiệp vụ.

## 1. Từ token văn bản đến tham số Java

Quá trình xử lý một command có thể chia thành các bước:

```text
Người dùng nhập command
        |
        v
Spring Shell parser tách command, option và argument
        |
        v
Đọc chuỗi giá trị của từng tham số
        |
        v
ConversionService chuyển String sang kiểu Java đích
        |
        v
Kiểm tra ràng buộc (nếu command có validation)
        |
        v
Gọi command method với các giá trị đã bind
```

Ví dụ command khai báo tham số số nguyên:

```java
@Command(name = "user-show", description = "Show a user")
public String showUser(@Argument(index = 0) long userId) {
    return "User id: " + userId;
}
```

Khi người dùng nhập `user-show 42`, token `42` được chuyển thành giá trị `long` trước khi gọi `showUser`. Method nhận một số nguyên đã chuyển đổi, không phải chuỗi `"42"`.

Phân biệt ba khái niệm:

- **Parsing command:** xác định token nào là command, positional argument hoặc option.
- **Type conversion:** chuyển chuỗi giá trị thành kiểu Java tương ứng.
- **Validation:** kiểm tra giá trị đã chuyển đổi có nằm trong quy tắc nghiệp vụ hay không.

Ví dụ `500` có thể chuyển đổi thành `int` thành công, nhưng vẫn không hợp lệ nếu nghiệp vụ chỉ cho phép số lượng từ `1` đến `100`. Chuyển đổi kiểu không thay thế validation.

## 2. Chọn kiểu số phù hợp

Spring Shell có thể bind các giá trị số vào kiểu Java tương ứng thông qua cơ chế chuyển đổi của Spring. Nên chọn kiểu dựa trên miền giá trị và độ chính xác mà nghiệp vụ yêu cầu.

| Kiểu Java | Dùng khi | Lưu ý |
|---|---|---|
| `int` / `Integer` | Số nguyên có phạm vi vừa phải, số lượng, số trang | Có giới hạn 32-bit; kiểm tra tràn số |
| `long` / `Long` | Identifier số hoặc bộ đếm lớn hơn `int` | Có giới hạn 64-bit |
| `BigInteger` | Số nguyên có độ lớn tùy ý | Không có giới hạn cố định như `long` |
| `float` / `double` | Giá trị đo lường, tính toán gần đúng | Biểu diễn nhị phân có thể làm tròn |
| `BigDecimal` | Tiền tệ, tỷ lệ hoặc số thập phân cần độ chính xác | Phù hợp cho phép tính thập phân chính xác hơn `double` |

Ví dụ command nhận số lượng và giá:

```java
import java.math.BigDecimal;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class PriceCommands {

    @Command(name = "price-calculate", description = "Calculate a line total")
    public String calculate(
            @Option(longName = "quantity", defaultValue = "1") int quantity,
            @Option(longName = "unit-price", required = true) BigDecimal unitPrice) {

        BigDecimal total = unitPrice.multiply(BigDecimal.valueOf(quantity));
        return "Total: " + total.toPlainString();
    }
}
```

Lời gọi:

```text
shell:>price-calculate --unit-price=12.50
Total: 12.50

shell:>price-calculate --quantity=3 --unit-price=12.50
Total: 37.50
```

`quantity` được chuyển sang `int`; `unit-price` được chuyển sang `BigDecimal`. `required = true` yêu cầu người dùng cung cấp giá; `defaultValue` của `quantity` được dùng khi không có option.

### Quy tắc biểu diễn số

Đối với CLI được gọi từ terminal hoặc script, nên chọn một định dạng số ổn định, độc lập với ngôn ngữ hiển thị của máy:

- Dùng dấu chấm `.` làm dấu phân cách phần thập phân, ví dụ `12.50`.
- Không chèn dấu phân cách hàng nghìn vào giá trị số, ví dụ dùng `12000` thay cho `12,000` hoặc `12.000`.
- Dùng dấu `-` cho số âm khi nghiệp vụ cho phép, ví dụ `--adjustment=-2.5`.
- Ghi rõ đơn vị bằng tên option hoặc một option riêng, ví dụ `--timeout-seconds=30`.
- Không dùng chuỗi hiển thị đã định dạng theo locale làm đầu vào máy nếu chưa có converter xử lý định dạng đó.

Ví dụ:

```text
price-calculate --unit-price=12500.75
report-query --min-score=8.5
job-start --timeout-seconds=30
```

Giá trị `12,50` thường không phải biểu diễn thập phân portable cho `BigDecimal` theo quy tắc số thông dụng của Java. Nếu người dùng cần nhập số theo locale, chẳng hạn dấu phẩy thập phân, hãy triển khai converter có locale xác định và ghi rõ quy tắc đó trong help. Tránh tự đoán locale từ máy đang chạy vì cùng một script có thể cho kết quả khác nhau giữa các môi trường.

### Tránh sai số khi xử lý tiền

`float` và `double` biểu diễn số thực theo dạng nhị phân. Nhiều phân số thập phân như `0.1` không có biểu diễn nhị phân hữu hạn chính xác, vì vậy kết quả phép tính có thể xuất hiện sai số làm tròn.

Với tiền hoặc giá trị cần kiểm soát số chữ số thập phân, dùng `BigDecimal`:

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);
```

Tạo `BigDecimal` từ chuỗi đầu vào giúp giữ chính xác giá trị thập phân đã nhập. Không nên dùng `new BigDecimal(19.95)` nếu mục tiêu là giữ chính xác biểu diễn thập phân `19.95`, vì literal `double` đã được biểu diễn nhị phân trước khi chuyển sang `BigDecimal`.

## 3. Xử lý Boolean như cờ hoặc giá trị tường minh

Boolean có hai trạng thái logic: `true` và `false`. Trong CLI, một Boolean option thường được dùng làm cờ bật tính năng, ví dụ `--verbose`, `--force` hoặc `--dry-run`.

Ví dụ:

```java
@Command(name = "backup-create", description = "Create a backup")
public String createBackup(
        @Option(longName = "dry-run", defaultValue = "false") boolean dryRun,
        @Option(longName = "verify", defaultValue = "true") boolean verify) {

    return "dryRun=" + dryRun + ", verify=" + verify;
}
```

Từ Spring Shell 4.0.1, parser mặc định hỗ trợ Boolean option ở dạng cờ không kèm giá trị. Một số lỗi liên quan đến cờ Boolean trong subcommand và khi kết hợp với positional arguments được sửa ở 4.0.2; vì vậy nên dùng ít nhất 4.0.2 nếu CLI có các trường hợp này. Ví dụ:

```text
shell:>backup-create
dryRun=false, verify=true

shell:>backup-create --dry-run
dryRun=true, verify=true

shell:>backup-create --dry-run=false --verify=false
dryRun=false, verify=false
```

Khi option có mặt dưới dạng cờ `--dry-run`, parser đặt giá trị là `true`. Khi cần thể hiện rõ `false`, truyền giá trị tường minh như `--dry-run=false`. Cách viết này dễ đọc trong script và tránh phụ thuộc vào vị trí một token `true` hoặc `false` rời.

### `boolean` và `Boolean`

Hai kiểu này khác nhau ở khả năng biểu diễn giá trị vắng mặt:

| Kiểu | Đặc điểm | Cách dùng thường gặp |
|---|---|---|
| `boolean` | Kiểu primitive, luôn có giá trị `true` hoặc `false` | Cờ bật/tắt có mặc định rõ ràng |
| `Boolean` | Kiểu wrapper, có thể nhận `null` trong Java | Khi cần phân biệt trạng thái chưa được cung cấp với true/false |

Với command thông thường, `boolean` cùng `defaultValue` tường minh là lựa chọn đơn giản. Nếu nghiệp vụ cần ba trạng thái như “không chỉ định”, “bật” và “tắt”, có thể dùng `Boolean` và thiết kế rõ hành vi khi option bị bỏ qua. Hãy kiểm thử trường hợp vắng mặt trên đúng phiên bản Spring Shell thay vì mặc định coi `null` tương đương `false`.

Không nên dùng Boolean option để biểu diễn nhiều chế độ loại trừ lẫn nhau. Ví dụ thay vì kết hợp `--csv`, `--json` và `--xml`, hãy dùng một option enum `--format=CSV` để bảo đảm chỉ có một lựa chọn.

## 4. Chuyển chuỗi thành enum

Enum phù hợp khi tham số chỉ được nhận một tập giá trị hữu hạn, ví dụ định dạng xuất file, mức log hoặc môi trường triển khai. Dùng enum giúp command method nhận được một trong các giá trị đã định nghĩa thay vì một chuỗi tùy ý.

Ví dụ:

```java
public enum OutputFormat {
    CSV,
    JSON,
    XML
}
```

Khai báo command:

```java
@Command(name = "report-export", description = "Export a report")
public String export(
        @Option(longName = "format", defaultValue = "CSV") OutputFormat format) {
    return "Export format: " + format;
}
```

Lời gọi:

```text
shell:>report-export
Export format: CSV

shell:>report-export --format=JSON
Export format: JSON
```

Khi chuyển đổi theo tên hằng enum, giá trị phải tương ứng với một hằng đã khai báo. Nên công bố tên canonical rõ ràng trong help, ví dụ `CSV`, `JSON`, `XML`; không dựa vào chuỗi mô tả thân thiện như `comma separated` trừ khi đã triển khai converter riêng.

### Enum và chữ hoa/chữ thường

Không nên để người dùng phải đoán quy tắc chữ hoa/chữ thường. Hãy chọn một biểu diễn canonical và kiểm tra cách converter của phiên bản Spring Shell đang dùng xử lý chữ hoa/chữ thường. Cách an toàn nhất cho ví dụ mặc định là dùng đúng tên hằng enum như `JSON` hoặc `CSV`.

Nếu muốn CLI chấp nhận cả `json`, `JSON` và `Json`, hãy chuẩn hóa đầu vào bằng converter tùy chỉnh. Đừng tự viết nhiều nhánh `if` trong mọi command chỉ để xử lý chữ hoa/chữ thường.

Spring Shell 4 cung cấp `EnumCompletionProvider` để gợi ý các giá trị enum khi người dùng tự hoàn thành option. Nhờ vậy, danh sách lựa chọn có thể được khám phá ngay trong prompt thay vì người dùng phải nhớ tên hằng.

## 5. Một command kết hợp số, Boolean và enum

Ví dụ sau kết hợp ba kiểu dữ liệu thường gặp trong một command xuất báo cáo:

```java
import java.math.BigDecimal;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

enum ReportFormat {
    CSV,
    JSON
}

@Component
public class ReportCommands {

    @Command(name = "report-export", description = "Export a report")
    public String export(
            @Option(longName = "limit", defaultValue = "100") int limit,
            @Option(longName = "ratio", defaultValue = "1.0") BigDecimal ratio,
            @Option(longName = "format", defaultValue = "CSV") ReportFormat format,
            @Option(longName = "verbose", defaultValue = "false") boolean verbose) {

        return "limit=" + limit
                + ", ratio=" + ratio.toPlainString()
                + ", format=" + format
                + ", verbose=" + verbose;
    }
}
```

Lời gọi:

```text
shell:>report-export
limit=100, ratio=1.0, format=CSV, verbose=false

shell:>report-export --limit=25 --ratio=0.85 --format=JSON --verbose
limit=25, ratio=0.85, format=JSON, verbose=true
```

Ở đây, mỗi option có một kiểu và một default rõ ràng. Giá trị được chuyển đổi trước khi command method chạy, vì vậy code trong method làm việc với `int`, `BigDecimal`, `ReportFormat` và `boolean` thay vì tự parse chuỗi.

## 6. Xử lý giá trị không chuyển đổi được

Chuyển đổi thất bại khi văn bản đầu vào không thể biểu diễn bằng kiểu đích. Ví dụ:

| Kiểu đích | Giá trị nhập | Vấn đề |
|---|---|---|
| `int` | `abc` | Không phải số nguyên |
| `int` | `999999999999` | Vượt phạm vi của `int` |
| `BigDecimal` | `12,50` | Dùng dấu phân cách không theo định dạng đã chọn |
| `boolean` | `yes` | Không phải biểu diễn Boolean mà command công bố |
| `OutputFormat` | `YAML` | Không có hằng `YAML` trong enum |

Khi conversion thất bại, Spring Shell không thể gọi method với tham số kiểu đích như đã khai báo. Người dùng cần nhận được thông báo cho biết option/argument nào sai và giá trị nào cần sửa.

Để giảm lỗi:

- Đặt `description` cho option và argument, nêu kiểu hoặc miền giá trị nếu cần.
- Dùng `defaultValue` hợp lệ và cùng định dạng với kiểu đích.
- Chọn tên option có đơn vị, ví dụ `--timeout-seconds` thay vì `--timeout` nếu đơn vị có thể gây nhầm lẫn.
- Với số có giới hạn, kết hợp conversion với validation như `@Min`, `@Max` hoặc kiểm tra nghiệp vụ trong service.
- Với enum, cung cấp danh sách lựa chọn hợp lệ trong help hoặc completion.
- Không bắt lỗi parse rồi âm thầm thay bằng `0`, `false` hoặc một enum mặc định nếu việc đó có thể làm command thực hiện sai tác vụ.

## 7. Mở rộng bằng Spring `Converter`

Khi kiểu dữ liệu nghiệp vụ không có converter mặc định, có thể tạo converter riêng. Spring Framework cung cấp `Converter<S, T>` để chuyển từ kiểu nguồn `S` sang kiểu đích `T`. Spring Shell 4 dùng cơ chế chuyển đổi kiểu của Spring cho tham số command; các bản Spring Shell 4.0.3 trở lên đã sửa lỗi đăng ký custom converter với annotation-based `@Command`.

Ví dụ ứng dụng có mã sản phẩm theo định dạng `PRD-1234`:

```java
public record ProductCode(String value) {
}
```

Converter:

```java
import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class ProductCodeConverter implements Converter<String, ProductCode> {

    private static final Pattern FORMAT = Pattern.compile("PRD-\\d{4}");

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!FORMAT.matcher(normalized).matches()) {
            throw new IllegalArgumentException(
                    "Product code must use the format PRD-1234");
        }
        return new ProductCode(normalized);
    }
}
```

Command nhận trực tiếp kiểu `ProductCode`:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    @Command(name = "product-show", description = "Show a product")
    public String show(@Argument(index = 0) ProductCode productCode) {
        return "Product code: " + productCode.value();
    }
}
```

Người dùng nhập:

```text
shell:>product-show prd-1234
Product code: PRD-1234
```

Converter chuẩn hóa chữ hoa/chữ thường, kiểm tra định dạng và tạo đối tượng `ProductCode`. Command method không cần lặp lại logic parse này.

Một converter nên:

- Có một trách nhiệm chuyển đổi rõ ràng.
- Kiểm tra cú pháp đầu vào và báo lỗi có ý nghĩa.
- Tránh giữ state thay đổi theo từng lần gọi; converter có thể được dùng đồng thời bởi nhiều command.
- Không truy cập cơ sở dữ liệu hoặc thực hiện tác vụ có side effect chỉ để chuyển đổi chuỗi.
- Chuẩn hóa `toString()` hoặc biểu diễn dữ liệu của kiểu đích để log và thông báo lỗi dễ hiểu.

## 8. Dùng `ConversionService` khi cần chuyển đổi chủ động

`ConversionService` là API thống nhất của Spring để kiểm tra khả năng chuyển đổi và thực hiện conversion. Ngoài việc Spring Shell dùng conversion khi bind tham số, ứng dụng có thể inject `ConversionService` vào service để chuyển đổi dữ liệu ở một nơi khác.

Ví dụ:

```java
import org.springframework.core.convert.ConversionService;
import org.springframework.stereotype.Service;

@Service
public class ImportService {

    private final ConversionService conversionService;

    public ImportService(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public ProductCode parseProductCode(String rawValue) {
        return conversionService.convert(rawValue, ProductCode.class);
    }
}
```

`Converter` phù hợp khi cần định nghĩa một phép chuyển đổi cụ thể. `ConversionService` phù hợp khi code cần hỏi `canConvert(...)` hoặc chuyển đổi giữa nhiều kiểu bằng một API chung. Với các trường hợp phức tạp hơn, Spring còn có `ConverterFactory` và `GenericConverter`; chỉ nên dùng chúng khi `Converter<S, T>` đơn giản không đủ đáp ứng.

## 9. Phân biệt conversion với validation

Conversion trả lời câu hỏi: “Chuỗi này có thể trở thành kiểu Java được khai báo không?”. Validation trả lời câu hỏi: “Giá trị sau khi chuyển đổi có hợp lệ theo quy tắc ứng dụng không?”.

Ví dụ `--quantity=500` chuyển đổi thành `int` hợp lệ, nhưng có thể vượt giới hạn nghiệp vụ. Dùng validation để kiểm tra miền giá trị:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class OrderCommands {

    @Command(name = "order-create", description = "Create an order")
    public String createOrder(
            @Option(longName = "quantity")
            @Min(1) @Max(100) int quantity) {
        return "Creating order with quantity " + quantity;
    }
}
```

Spring Shell 4 hỗ trợ Bean Validation cho tham số command khi ứng dụng có dependency validation phù hợp. Nếu validation chưa được cấu hình, có thể thực hiện kiểm tra nghiệp vụ trong service. Không nhầm việc chuyển được `"500"` thành `500` với việc số lượng `500` được phép trong nghiệp vụ.

## 10. Những lỗi thường gặp khi biểu diễn kiểu dữ liệu

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Số thập phân không parse được | Dùng dấu phẩy hoặc dấu phân cách hàng nghìn không nằm trong định dạng CLI | Công bố định dạng locale-neutral, ví dụ `12.50` |
| Kết quả tiền tệ có sai số | Dùng `double` cho phép tính thập phân cần chính xác | Dùng `BigDecimal` và khởi tạo từ chuỗi |
| Số nguyên bị từ chối | Giá trị vượt phạm vi `int` hoặc `long` | Chọn kiểu lớn hơn hoặc `BigInteger` |
| Boolean flag không hoạt động như mong đợi | Nhầm cờ có mặt với giá trị Boolean tường minh | Dùng `--verbose` để bật hoặc `--verbose=false` để tắt |
| Không phân biệt “chưa cung cấp” với `false` | Dùng `boolean` primitive cho nghiệp vụ cần ba trạng thái | Dùng `Boolean` và xác định rõ hành vi khi vắng mặt |
| Enum bị từ chối | Giá trị không khớp hằng enum đã khai báo | Dùng tên canonical hoặc converter chuẩn hóa |
| Giá trị mặc định không hợp lệ | `defaultValue` là chuỗi nhưng không chuyển được sang kiểu đích | Kiểm tra default theo cùng quy tắc với input |
| Command chứa logic parse lặp lại | Nhận mọi giá trị bằng `String` rồi parse trong từng method | Khai báo kiểu đích hoặc tạo converter dùng chung |
| Converter làm thay đổi dữ liệu ngoài dự kiến | Converter vừa chuyển đổi vừa thực hiện nghiệp vụ/side effect | Giữ converter thuần chuyển đổi và kiểm tra cú pháp |

## 11. Checklist thiết kế kiểu dữ liệu cho command

- [ ] Đã chọn kiểu Java theo miền giá trị và độ chính xác cần thiết.
- [ ] Dùng `BigDecimal` cho tiền và số thập phân cần độ chính xác.
- [ ] Đã thống nhất dấu thập phân, dấu âm, đơn vị và cách viết số.
- [ ] Boolean flag có default rõ ràng và phân biệt được cách bật/tắt.
- [ ] Đã quyết định có cần phân biệt trạng thái Boolean chưa được cung cấp hay không.
- [ ] Enum có danh sách hằng và tên canonical rõ ràng.
- [ ] Giá trị mặc định có thể chuyển đổi thành kiểu đích.
- [ ] Thông báo lỗi chỉ ra giá trị hoặc option không hợp lệ.
- [ ] Đã tách conversion khỏi validation nghiệp vụ.
- [ ] Custom converter được đăng ký thành Spring bean và đã kiểm thử với annotation-based command.
- [ ] Converter an toàn khi được dùng đồng thời và không tạo side effect.
- [ ] Đã kiểm tra command với giá trị hợp lệ, sai định dạng, vượt giới hạn và giá trị vắng mặt.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – quy tắc parser, option, argument và biểu diễn giá trị.
2. [Spring Shell 4 – `@Option` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) – `defaultValue`, `required`, `longName`, `shortName` và description.
3. [Spring Shell 4 – `EnumCompletionProvider` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/EnumCompletionProvider.html) – gợi ý giá trị enum trong command completion.
4. [Spring Framework – Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) – `Converter`, `ConverterFactory`, `GenericConverter` và `ConversionService`.
5. [Spring Shell 4 – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html) – Bean Validation trên tham số command và kiểm tra trước khi thực thi.
6. [Spring Shell releases](https://github.com/spring-projects/spring-shell/releases) – thay đổi theo phiên bản, bao gồm hỗ trợ Boolean option không có giá trị từ 4.0.1, sửa lỗi cờ Boolean trong subcommand ở 4.0.2 và sửa lỗi custom converter với `@Command` trong 4.0.3.

Hãy công bố một quy tắc biểu diễn ổn định cho từng kiểu dữ liệu. Dùng kiểu số phù hợp, Boolean có default rõ ràng và enum với các lựa chọn hữu hạn; khi định dạng nghiệp vụ khác quy tắc mặc định, hãy gom logic vào converter để mọi command xử lý cùng một cách.
