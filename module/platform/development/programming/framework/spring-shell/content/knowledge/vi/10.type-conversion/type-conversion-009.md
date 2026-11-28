# Phân biệt lỗi cú pháp, lỗi chuyển kiểu và lỗi miền giá trị

## 1. Ba lớp lỗi khác nhau

Khi người dùng nhập dữ liệu cho một command, chuỗi đầu vào phải đi qua nhiều bước trước khi nghiệp vụ được thực thi. Một lỗi có thể xuất hiện vì câu lệnh không đúng cú pháp, vì chuỗi không chuyển được sang kiểu Java hoặc vì giá trị đã chuyển đổi không thỏa mãn quy tắc nghiệp vụ.

Ba loại lỗi này cần được phân biệt:

| Loại lỗi | Điều gì xảy ra? | Ví dụ |
|---|---|---|
| **Lỗi cú pháp** (syntax error) | Parser không thể hiểu cấu trúc câu lệnh hoặc không tìm thấy thành phần được gọi. | Gõ `product shwo`, thiếu giá trị cho option bắt buộc hoặc đặt dấu nháy không cân bằng. |
| **Lỗi chuyển đổi kiểu** (type conversion error) | Câu lệnh được phân tích, nhưng một token không thể chuyển sang kiểu tham số Java. | `--limit=abc` trong khi tham số là `int`; `--date=2026-02-30` trong khi tham số là `LocalDate`. |
| **Lỗi miền giá trị** (domain validation error) | Dữ liệu đã có kiểu đúng, nhưng giá trị không được nghiệp vụ chấp nhận. | `--limit=0` khi giới hạn phải từ 1 đến 1000; ngày kết thúc nằm trước ngày bắt đầu. |

Ví dụ, với command `report run --limit=100`:

- Nếu viết `report rn --limit=100`, shell không tìm thấy command `report rn`: lỗi cú pháp hoặc tra cứu command.
- Nếu viết `report run --limit=abc`, parser nhận được option `limit`, nhưng chuỗi `abc` không thể chuyển thành số nguyên: lỗi chuyển đổi.
- Nếu viết `report run --limit=0`, chuyển đổi sang `int` thành công, nhưng giá trị 0 không nằm trong miền cho phép: lỗi validation.

Phân loại đúng giúp chọn đúng nơi xử lý và tạo thông báo có ích. Không nên dùng một thông báo chung “dữ liệu không hợp lệ” cho cả ba trường hợp.

## 2. Luồng xử lý từ token đến nghiệp vụ

Trong Spring Shell 4.x, dòng lệnh được parser phân tích thành command, option và argument. Khi command được tìm thấy, framework ánh xạ các giá trị đầu vào vào tham số phương thức. Quá trình ánh xạ có thể cần chuyển chuỗi thành kiểu Java; các ràng buộc Bean Validation sau đó được kiểm tra trước khi thân phương thức command chạy.

~~~mermaid
flowchart TD
    A[Người dùng nhập dòng lệnh] --> B[Parser đọc cú pháp]
    B --> C{Cấu trúc hợp lệ?}
    C -->|Không| S[Lỗi cú pháp / trợ giúp]
    C -->|Có| D[Tra cứu command và option]
    D --> E[Chuyển String sang kiểu Java]
    E --> F{Chuyển đổi thành công?}
    F -->|Không| T[Lỗi chuyển đổi kiểu]
    F -->|Có| G[Bean Validation]
    G --> H{Ràng buộc hợp lệ?}
    H -->|Không| V[Lỗi miền giá trị / validation]
    H -->|Có| I[Thực thi phương thức command]
    I --> J[Service kiểm tra quy tắc nghiệp vụ]
    J --> K[Kết quả và trạng thái thực thi]
~~~

Thứ tự trên là mô hình khái niệm. Một số kiểm tra có thể được thực hiện ở parser, adapter hoặc trong code nghiệp vụ tùy cách khai báo command. Điều quan trọng là hiểu một token có thể thất bại ở các giai đoạn khác nhau.

## 3. Lỗi cú pháp: parser không hiểu câu lệnh

Lỗi cú pháp xuất hiện trước khi giá trị được chuyển sang kiểu tham số. Một số trường hợp thường gặp:

- Tên command hoặc subcommand không tồn tại.
- Tên option không được khai báo.
- Thiếu giá trị cho option cần giá trị.
- Thiếu argument bắt buộc hoặc truyền token không đúng vị trí.
- Dấu nháy không cân bằng hoặc cách viết token không đúng cú pháp.

Ví dụ command:

~~~java
@Component
class ReportCommands {

    @Command(name = "report run", description = "Chạy báo cáo")
    public String run(
            @Option(longName = "format", required = true) String format,
            @Option(longName = "limit", defaultValue = "100") int limit) {
        return "Tạo báo cáo";
    }
}
~~~

Các lệnh sau có vấn đề ở cú pháp hoặc cấu trúc đầu vào:

~~~text
report rn --format=csv
report run --format
report run --unknown=value --format=csv
~~~

Lệnh đầu gọi sai tên command. Lệnh thứ hai có tên option nhưng không có giá trị. Lệnh thứ ba sử dụng option không được khai báo. Thông báo thực tế phụ thuộc parser và result handler của phiên bản Spring Shell đang dùng; nên kiểm tra nội dung `help report run` để xác nhận cú pháp được công bố.

Trong Spring Shell 4.x, `@Option` khai báo option có tên; `@Argument` khai báo dữ liệu theo vị trí. Tên command và option nên được mô tả rõ trong `@Command`, `@Option` và `@Argument` để trợ giúp có thể chỉ dẫn người dùng sửa lệnh.

## 4. Lỗi chuyển đổi kiểu: token đúng cấu trúc nhưng sai định dạng

Sau khi parser nhận diện một option hoặc argument, Spring Shell phải chuyển giá trị văn bản sang kiểu Java mà phương thức yêu cầu. Ví dụ:

~~~java
@Command(name = "report run")
public String run(
        @Option(longName = "limit") int limit,
        @Option(longName = "date") LocalDate date,
        @Option(longName = "format") OutputFormat format) {
    return "...";
}
~~~

Đầu vào sau có cấu trúc hợp lệ, nhưng giá trị không chuyển được:

~~~text
report run --limit=one-hundred --date=2026-02-30 --format=csvv
~~~

Nguyên nhân:

- `one-hundred` không biểu diễn một giá trị `int`.
- `2026-02-30` không phải ngày lịch hợp lệ nên không tạo được `LocalDate`.
- `csvv` không khớp hằng số nào của enum `OutputFormat`.

Ví dụ enum:

~~~java
public enum OutputFormat {
    CSV,
    JSON
}
~~~

Với enum, giá trị nhập phải khớp quy tắc chuyển đổi được cấu hình. Không nên giả định rằng mọi tên đều được tự động chuyển sang chữ hoa hoặc chấp nhận bí danh. Nếu muốn hỗ trợ `csv`, `CSV` và `comma-separated`, hãy định nghĩa converter có quy tắc rõ ràng.

### Các kiểu dữ liệu phổ biến

Spring Framework cung cấp hệ thống chuyển đổi cho các kiểu dữ liệu thông dụng. Spring Shell sử dụng `ConversionService` để chuyển dữ liệu command sang kiểu tham số.

| Kiểu Java | Ví dụ đầu vào | Lưu ý |
|---|---|---|
| `String` | `--name=Lan` | Nhận văn bản; validation vẫn có thể cần kiểm tra rỗng hoặc độ dài. |
| `int`, `long` | `--limit=50` | Phải là số nguyên nằm trong miền biểu diễn của kiểu. |
| `BigDecimal` | `--price=125000.50` | Dùng cho số thập phân cần độ chính xác; cần quy định dấu thập phân và đơn vị. |
| `boolean` | `--enabled=true` | Chuyển thành `true` hoặc `false`; cú pháp flag cũng được hỗ trợ theo parser của phiên bản. |
| `LocalDate` | `--date=2026-11-26` | Khi shell `ConversionService` có converter tương ứng, thường dùng dạng ISO `yyyy-MM-dd`; ngày không tồn tại gây lỗi chuyển đổi. |
| Enum | `--format=JSON` | Chỉ chấp nhận giá trị có thể ánh xạ tới hằng số enum. |
| Mảng hoặc collection | `--tag=java --tag=spring` hoặc argument nhiều giá trị | Cần khai báo đúng kiểu phần tử và arity theo cú pháp command. |

Không phải mọi kiểu đều có thể chuyển đổi theo cách mong muốn chỉ nhờ khai báo kiểu tham số. Với kiểu miền riêng, định dạng đặc biệt hoặc quy tắc nhập liệu riêng, hãy bổ sung converter.

Với các kiểu ngày giờ, hãy xác nhận định dạng và converter thực sự được đăng ký trong shell `ConversionService` của ứng dụng. Không suy ra rằng mọi ứng dụng Spring đều có cùng tập formatter chỉ vì chúng cùng dùng Spring Framework.

## 5. Lỗi miền giá trị: chuyển đổi thành công nhưng dữ liệu không hợp lệ

Một giá trị có thể chuyển đổi hoàn toàn hợp lệ về mặt kỹ thuật nhưng vẫn vi phạm quy tắc nghiệp vụ. Ví dụ `0` là một số nguyên hợp lệ, `2027-01-01` là ngày hợp lệ và `JSON` là hằng số enum hợp lệ. Tuy nhiên, mỗi command có thể đặt thêm giới hạn.

Spring Shell tích hợp Bean Validation để kiểm tra các annotation trên tham số trước khi gọi phương thức command. Ví dụ:

Để dùng các constraint Jakarta như `@Min`, `@Max`, `@NotBlank` và `@Positive`, ứng dụng Spring Boot cần có implementation Bean Validation trên classpath. Thông thường có thể thêm dependency `spring-boot-starter-validation`.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(name = "report run", description = "Chạy báo cáo")
    public String run(
            @Option(longName = "name", required = true)
            @NotBlank String name,
            @Option(longName = "limit", defaultValue = "100")
            @Min(1) @Max(1000) int limit,
            @Option(longName = "workers", defaultValue = "1")
            @Positive int workers) {

        return "Báo cáo " + name + ": limit=" + limit
                + ", workers=" + workers;
    }
}
~~~

Trong ví dụ:

- `@NotBlank` yêu cầu tên báo cáo có ít nhất một ký tự không phải khoảng trắng.
- `@Min(1)` và `@Max(1000)` giới hạn `limit` trong khoảng từ 1 đến 1000.
- `@Positive` yêu cầu `workers` lớn hơn 0.

Các lệnh dưới đây đều có thể được phân tích và chuyển kiểu, nhưng một số lệnh vi phạm validation:

~~~text
report run --name="   " --limit=10 --workers=1
report run --name=daily --limit=0 --workers=1
report run --name=daily --limit=5000 --workers=1
report run --name=daily --limit=10 --workers=0
~~~

Thông báo validation mặc định của Spring Shell có thể chỉ ra tham số và constraint không được thỏa mãn, ví dụ:

~~~text
The following constraints were not met:
    --limit: must be greater than or equal to 1
Error while executing command report run: USAGE_ERROR
~~~

Câu chữ cụ thể phụ thuộc constraint, phiên bản và cách hiển thị kết quả. Nên giữ thông tin lỗi gắn với tham số để người dùng biết phải sửa option nào.

### Quy tắc nghiệp vụ cần service kiểm tra

Không phải mọi quy tắc đều phù hợp với Bean Validation trên tham số. Những điều kiện phụ thuộc dữ liệu hiện có hoặc nhiều trường đầu vào thường thuộc service nghiệp vụ.

Ví dụ:

- Mã sản phẩm đúng định dạng nhưng không tồn tại trong kho.
- Ngày kết thúc lớn hơn ngày bắt đầu, nhưng cần so sánh hai tham số với nhau.
- Số lượng hợp lệ về mặt số học nhưng vượt số lượng còn có thể đặt.
- Người dùng hiện tại không có quyền thực hiện thao tác trên tài nguyên.

Command có thể gọi service và nhận lỗi nghiệp vụ có kiểu riêng:

~~~java
@Command(name = "booking create")
public String create(
        @Option(longName = "start", required = true) LocalDate start,
        @Option(longName = "end", required = true) LocalDate end) {

    if (end.isBefore(start)) {
        throw new InvalidBookingPeriodException(
                "Ngày kết thúc phải bằng hoặc sau ngày bắt đầu");
    }

    bookingService.create(start, end);
    return "Đã tạo đặt chỗ";
}
~~~

Trong ứng dụng lớn, nên đưa kiểm tra khoảng ngày vào service hoặc đối tượng miền để các giao diện khác cũng dùng chung quy tắc. Ví dụ trên chỉ minh họa việc một lỗi miền có thể xuất hiện sau khi cả hai giá trị đã chuyển thành `LocalDate`.

## 6. Khi nào cần viết custom Converter?

Nếu kiểu dữ liệu đích là kiểu chuẩn như `int`, `BigDecimal`, `LocalDate` hoặc enum thông thường, hãy tận dụng converter mặc định. Tạo converter riêng khi:

- Tham số command là value object hoặc kiểu miền riêng.
- Định dạng đầu vào khác quy tắc chuyển đổi mặc định.
- Cần chuẩn hóa giá trị trước khi tạo đối tượng, ví dụ bỏ khoảng trắng hoặc chuẩn hóa chữ hoa.
- Cần chuyển một chuỗi có cấu trúc thành một kiểu dữ liệu cụ thể.

Spring Framework định nghĩa `Converter<S, T>` để chuyển từ kiểu nguồn `S` sang kiểu đích `T`. Converter nhận nguồn khác null và nên ném `IllegalArgumentException` khi giá trị nguồn không hợp lệ. Converter được dùng chung trong ứng dụng nên cần an toàn luồng và không lưu trạng thái thay đổi theo từng lần gọi.

### Ví dụ chuyển chuỗi thành ProductCode

Giả sử mã sản phẩm có dạng `PRD-` theo sau bởi sáu ký tự chữ hoa hoặc chữ số. Tạo value object:

~~~java
package com.example.inventory;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null || !value.matches("PRD-[A-Z0-9]{6}")) {
            throw new IllegalArgumentException(
                    "Mã sản phẩm phải có dạng PRD-XXXXXX");
        }
    }
}
~~~

Tạo converter:

~~~java
package com.example.inventory;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class ProductCodeConverter implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProductCode(normalized);
    }
}
~~~

Sau đó sử dụng kiểu `ProductCode` trực tiếp trong command:

~~~java
package com.example.inventory;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    private final ProductService productService;

    public ProductCommands(ProductService productService) {
        this.productService = productService;
    }

    @Command(name = "product show", description = "Hiển thị sản phẩm")
    public String show(
            @Option(longName = "code", required = true) ProductCode code) {

        Product product = productService.findByCode(code)
                .orElseThrow(() -> new ProductNotFoundException(code));

        return product.name();
    }
}
~~~

Khi người dùng gọi `product show --code=prd-a1b2c3`, converter chuẩn hóa chuỗi thành `PRD-A1B2C3`, sau đó tạo `ProductCode`. Nếu chuỗi không đúng mẫu, constructor từ chối và quá trình chuyển đổi thất bại. Nếu mã đúng mẫu nhưng không có sản phẩm tương ứng, service ném `ProductNotFoundException`: đây là lỗi nghiệp vụ, không phải lỗi chuyển đổi.

`Product`, `ProductService` và `ProductNotFoundException` là các kiểu miền của ứng dụng ví dụ; cần định nghĩa chúng trong project thực tế.

Trong Spring Shell 4.x, shell dùng `ConversionService` riêng để chuyển dữ liệu command. `ShellConversionServiceSupplier` là extension point cung cấp conversion service cho shell; với ứng dụng Spring Boot, auto-configuration cung cấp supplier mặc định. Các custom converter dùng với command annotation được hỗ trợ từ Spring Shell 4.0.3; lỗi khiến converter bean không được áp dụng cho `@Command` đã được sửa ở phiên bản này. Nên dùng bản 4.0.3 trở lên, ưu tiên bản ổn định mới nhất phù hợp với Spring Boot của dự án.

### Converter, ConverterFactory và GenericConverter

Spring Framework có ba SPI chính:

| SPI | Khi phù hợp |
|---|---|
| `Converter<S, T>` | Một kiểu nguồn và một kiểu đích cụ thể, ví dụ `String` sang `ProductCode`. |
| `ConverterFactory<S, R>` | Một kiểu nguồn chuyển sang nhiều kiểu đích thuộc cùng một hệ phân cấp, ví dụ factory tạo converter cho các kiểu enum. |
| `GenericConverter` | Cần hỗ trợ nhiều cặp kiểu hoặc cần xem `TypeDescriptor` của nguồn và đích để quyết định cách chuyển. |

Ưu tiên `Converter` cho trường hợp đơn giản. Chỉ dùng `ConverterFactory` hoặc `GenericConverter` khi có nhu cầu thực tế về hệ phân cấp kiểu hoặc nhiều cặp chuyển đổi.

## 7. Không trộn chuyển đổi kiểu với tra cứu nghiệp vụ

Converter nên tập trung vào việc biến đổi biểu diễn đầu vào thành một đối tượng có kiểu. Không nên dùng converter như nơi thực hiện toàn bộ nghiệp vụ.

Ví dụ, chuyển `PRD-A1B2C3` thành `ProductCode` là chuyển đổi kiểu. Tìm sản phẩm trong database để xác nhận mã có tồn tại là kiểm tra nghiệp vụ. Nếu đặt truy vấn database trong converter, việc chuyển đổi có thể phát sinh I/O bất ngờ, khó kiểm thử và khó phân biệt lỗi định dạng với lỗi không tìm thấy dữ liệu.

Một luồng dễ bảo trì:

1. Parser kiểm tra cấu trúc câu lệnh.
2. Converter tạo kiểu Java từ chuỗi.
3. Bean Validation kiểm tra constraint cục bộ trên giá trị.
4. Service xác nhận quy tắc cần dữ liệu hệ thống hoặc nhiều đối tượng.
5. Command trình bày kết quả và ánh xạ lỗi phù hợp.

## 8. Xử lý và trình bày lỗi nhất quán

Thông báo lỗi nên cho biết đầu vào nào gây lỗi, lý do và cách sửa. Có thể tổ chức theo mẫu:

~~~text
Lỗi: --limit phải là số nguyên.
Cách sửa: report run --limit=100
Trợ giúp: help report run
~~~

Một số gợi ý theo loại lỗi:

| Loại lỗi | Nội dung nên hiển thị |
|---|---|
| Cú pháp | Tên command/option/argument không đúng và cú pháp hợp lệ. |
| Chuyển đổi | Tên tham số, kiểu mong đợi và định dạng ví dụ. |
| Validation | Tên tham số và constraint bị vi phạm, ví dụ giới hạn min/max. |
| Nghiệp vụ | Đối tượng hoặc quy tắc không thỏa mãn, kèm hành động tiếp theo nếu có. |

Với lỗi validation, Spring Shell có thể hiển thị tên option và constraint chưa được đáp ứng. Với lỗi trong lúc thực thi, có thể dùng `ExitStatusExceptionMapper` để ánh xạ exception sang `ExitStatus` phù hợp. Tuy nhiên, mapper chỉ xử lý ngoại lệ đi qua giai đoạn thực thi command; lỗi parser hoặc lỗi chuyển đổi có thể phát sinh trước khi thân phương thức chạy. Vì vậy, không nên giả định một mapper ở command sẽ bắt được mọi lỗi cú pháp và conversion.

Không đưa stack trace, mật khẩu, token, thông tin kết nối hoặc dữ liệu nhạy cảm vào thông báo dành cho người dùng. Ghi chi tiết kỹ thuật vào log với mức độ phù hợp.

## 9. Kiểm thử ba loại lỗi

Kiểm thử cần xác nhận cả thông báo và việc command có được thực thi hay không. Với `@ShellTest`, `ShellTestClient` và `ShellAssertions`, có thể gửi câu lệnh và kiểm tra nội dung terminal. Nên tổ chức bộ kiểm thử theo từng lớp lỗi:

| Ca kiểm thử | Đầu vào | Kỳ vọng |
|---|---|---|
| Cú pháp | Gọi sai tên command | Không gọi phương thức nghiệp vụ; hiển thị lỗi tra cứu/help. |
| Cú pháp | Bỏ option bắt buộc hoặc thiếu giá trị | Hiển thị option cần cung cấp. |
| Chuyển đổi | `--limit=abc` với tham số `int` | Không gọi command; hiển thị lỗi chuyển kiểu. |
| Chuyển đổi | Ngày không tồn tại như `2026-02-30` | Không gọi command; hiển thị định dạng ngày không hợp lệ. |
| Chuyển đổi | Enum không có giá trị tương ứng | Báo giá trị không được hỗ trợ. |
| Validation | `--limit=0` với `@Min(1)` | Chuyển đổi thành công nhưng validation từ chối. |
| Validation | `--limit=1001` với `@Max(1000)` | Validation từ chối giá trị ngoài giới hạn. |
| Nghiệp vụ | Mã sản phẩm đúng định dạng nhưng không tồn tại | Converter thành công; service trả lỗi không tìm thấy sản phẩm. |

Với custom converter, cần kiểm thử riêng:

- Chuỗi hợp lệ được chuyển thành đúng value object.
- Chuỗi có khoảng trắng hoặc chữ thường được chuẩn hóa theo quy ước.
- Chuỗi sai định dạng ném exception phù hợp.
- Converter bean thực sự được sử dụng bởi command annotation trong phiên bản Spring Shell đang chạy.
- Lỗi không tìm thấy tài nguyên được phát hiện ở service, không bị nhầm thành lỗi chuyển đổi.

## 10. Quy trình chẩn đoán khi command báo lỗi

Khi một command không chạy như mong đợi, hãy kiểm tra theo thứ tự:

1. **Xác nhận cú pháp:** tên command, option, argument, dấu nháy và giá trị bắt buộc có đúng không?
2. **Kiểm tra kiểu tham số:** kiểu Java có khớp định dạng dữ liệu người dùng nhập không?
3. **Kiểm tra converter:** với kiểu riêng, converter có được đăng ký trong shell `ConversionService` và có xử lý đúng định dạng không?
4. **Kiểm tra validation:** giá trị đã chuyển đổi có thỏa `@Min`, `@Max`, `@NotBlank`, `@Pattern` hoặc constraint khác không?
5. **Kiểm tra nghiệp vụ:** dữ liệu có tồn tại, có trạng thái phù hợp và người gọi có quyền thực hiện không?
6. **Kiểm tra trạng thái lỗi:** exception phát sinh ở giai đoạn nào và đã được ánh xạ thành thông báo/mã thoát phù hợp chưa?

Trình tự này giúp khoanh vùng lỗi nhanh hơn. Ví dụ, nếu command method chưa được gọi, hãy kiểm tra parser, conversion và validation trước khi xem logic trong service.

## Kết luận

Lỗi cú pháp, lỗi chuyển đổi kiểu và lỗi miền giá trị xuất hiện ở các giai đoạn khác nhau của quá trình thực thi command. Parser xử lý cấu trúc câu lệnh; `ConversionService` chuyển token thành kiểu Java; Bean Validation và service kiểm tra các quy tắc giá trị. Với kiểu miền riêng, custom `Converter<String, T>` giúp chuẩn hóa và tạo đối tượng có kiểu. Hãy đặt mỗi quy tắc ở đúng tầng, đưa ra thông báo gắn với tham số gây lỗi và kiểm thử riêng từng loại lỗi để command Spring Shell dễ chẩn đoán và đáng tin cậy.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell 4.0.4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.0.4 API – Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Shell – Fix for custom converters with @Command annotations](https://github.com/spring-projects/spring-shell/pull/1353)
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)
