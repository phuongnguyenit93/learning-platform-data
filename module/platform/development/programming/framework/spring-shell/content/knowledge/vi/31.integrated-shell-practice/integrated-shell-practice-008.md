# Cung cấp cả đầu ra cho người đọc và đầu ra cho script

Một CLI tốt cần phục vụ hai cách sử dụng. Người vận hành muốn xem bảng gọn, dễ quét trên terminal; script hoặc pipeline cần dữ liệu có cấu trúc, ổn định và không chứa ký tự trang trí. Ta có thể đáp ứng cả hai bằng một command, miễn là tách dữ liệu khỏi cách trình bày và công bố rõ định dạng đầu ra.

Bài thực hành xây dựng command `catalog list` cho ứng dụng Spring Shell. Command đọc cùng một danh sách mặt hàng rồi trả về bảng terminal, JSON hoặc CSV theo option `--format`. Bài dùng Spring Shell 3.3.x, Spring Boot 3.x và JDK 17+; phần cuối nêu điểm cần đổi khi chuyển sang Spring Shell 4.

## 1. Kết quả cần đạt

Sau khi hoàn thành, người dùng có thể chạy command theo ba cách:

```text
catalog list
catalog list --format=json
catalog list --format=csv
```

Khi chạy trong REPL, định dạng mặc định là bảng:

```text
┌────┬───────────────┬──────────┬───────────┐
│ ID │ Tên           │ Trạng thái│ Số lượng  │
├────┼───────────────┼──────────┼───────────┤
│ 42 │ Keyboard      │ ACTIVE   │ 18        │
│ 57 │ Monitor       │ ACTIVE   │ 6         │
│ 63 │ USB-C Hub     │ PAUSED   │ 0         │
└────┴───────────────┴──────────┴───────────┘
```

Khi chạy cho script, chọn JSON:

```json
[
  {
    "id": "42",
    "name": "Keyboard",
    "status": "ACTIVE",
    "quantity": 18
  },
  {
    "id": "57",
    "name": "Monitor",
    "status": "ACTIVE",
    "quantity": 6
  },
  {
    "id": "63",
    "name": "USB-C Hub",
    "status": "PAUSED",
    "quantity": 0
  }
]
```

Hoặc CSV:

```csv
id,name,status,quantity
42,Keyboard,ACTIVE,18
57,Monitor,ACTIVE,6
63,USB-C Hub,PAUSED,0
```

Một nguồn dữ liệu, ba cách biểu diễn. Script không phải phân tích đường viền ASCII hoặc căn lề của bảng.

## 2. Phác thảo kiến trúc

Tách trách nhiệm thành các phần nhỏ:

| Thành phần | Trách nhiệm |
|---|---|
| `CatalogService` | Lấy danh sách mặt hàng và áp dụng quy tắc nghiệp vụ |
| `CatalogItem` | DTO có kiểu, làm hợp đồng dữ liệu đầu ra |
| `CatalogOutputFormatter` | Chuyển DTO thành Table, JSON hoặc CSV |
| `CatalogCommands` | Nhận option, chọn định dạng và trả kết quả cho Spring Shell |
| Result handlers | Render kết quả command ra console |
| Exception resolver | Chuyển lỗi định dạng thành thông báo và exit code |

Command không tự truy vấn dữ liệu ba lần. Nó gọi service một lần, sau đó chọn formatter. Khi đổi kiểu bảng hoặc schema JSON, logic truy vấn vẫn giữ nguyên.

## 3. Dependency và phạm vi phiên bản

Ví dụ dùng Spring Shell 3.3.x. Ứng dụng cần starter Spring Shell, module bảng và Jackson. Quản lý phiên bản qua Spring Boot parent hoặc BOM để các thư viện Jackson tương thích với nhau.

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-table</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-csv</artifactId>
    </dependency>
</dependencies>
```

`spring-shell-table` cung cấp API `TableModel` và `TableBuilder` của Spring Shell 3.3. `jackson-dataformat-csv` bổ sung serializer CSV; phiên bản Jackson cần được quản lý đồng bộ với dependency management của Spring Boot.

Nếu chỉ cần JSON, có thể bỏ dependency CSV và nhánh `csv`. Không nên tự ghim một phiên bản Jackson khác với phiên bản mà BOM của ứng dụng đang quản lý.

## 4. Khai báo DTO và nguồn dữ liệu

Dùng một DTO có kiểu cho cả ba định dạng:

```java
public record CatalogItem(
    String id,
    String name,
    String status,
    int quantity
) {
}
```

Service trả về cùng danh sách cho mọi cách trình bày:

```java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public List<CatalogItem> findAll() {
        return List.of(
            new CatalogItem("42", "Keyboard", "ACTIVE", 18),
            new CatalogItem("57", "Monitor", "ACTIVE", 6),
            new CatalogItem("63", "USB-C Hub", "PAUSED", 0)
        );
    }
}
```

Trong ứng dụng thực tế, `findAll()` có thể đọc từ database hoặc API. Service nên trả về dữ liệu đã được lọc và sắp xếp theo quy tắc nghiệp vụ; formatter chỉ quyết định cách hiển thị.

Không đưa ký tự đường viền, mã màu ANSI hoặc khoảng trắng căn lề vào DTO. `quantity` vẫn là số nguyên để JSON giữ kiểu number; bảng có thể chuyển nó thành văn bản khi render.

## 5. Tạo formatter cho bảng terminal

Spring Shell 3.3 có API bảng trong package `org.springframework.shell.table`. `TableModelBuilder` mô tả hàng và cột; `TableBuilder` tạo đối tượng `Table` để result handler render.

```java
import java.util.List;

import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModelBuilder;
import org.springframework.stereotype.Component;

@Component
public class CatalogOutputFormatter {

    public Table toTable(List<CatalogItem> items) {
        TableModelBuilder<String> model =
            new TableModelBuilder<>();

        model.addRow()
            .addValue("ID")
            .addValue("Tên")
            .addValue("Trạng thái")
            .addValue("Số lượng");

        if (items.isEmpty()) {
            model.addRow()
                .addValue("—")
                .addValue("Không có dữ liệu")
                .addValue("—")
                .addValue("0");
        }
        else {
            for (CatalogItem item : items) {
                model.addRow()
                    .addValue(item.id())
                    .addValue(item.name())
                    .addValue(item.status())
                    .addValue(Integer.toString(item.quantity()));
            }
        }

        return new TableBuilder(model.build())
            .addHeaderBorder(BorderStyle.fancy_light)
            .build();
    }
}
```

Hàng đầu tiên là tiêu đề; mỗi mặt hàng tạo thành một hàng tiếp theo. `addHeaderBorder(...)` tạo đường viền ngoài và đường phân cách phần tiêu đề.

Khi command trả về `Table`, result handler tương ứng của Spring Shell có thể render theo chiều rộng terminal. Trong unit test, có thể gọi `table.render(80)` để cố định chiều rộng khi so sánh output.

Bảng được thiết kế để người đọc terminal quét nhanh. Không dùng nó làm định dạng dữ liệu cho chương trình khác.

## 6. Thêm bộ xuất JSON

Spring Boot cung cấp `ObjectMapper` đã được cấu hình theo dependency của ứng dụng. Inject mapper thay vì tạo một mapper mới ở mỗi lần chạy command:

```java
import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public class CatalogJsonFormatter {

    private final ObjectMapper objectMapper;

    public CatalogJsonFormatter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String toJson(List<CatalogItem> items)
            throws JsonProcessingException {
        return objectMapper
            .writerWithDefaultPrettyPrinter()
            .writeValueAsString(items);
    }
}
```

Jackson tuần tự hóa danh sách DTO thành mảng JSON. Trường `quantity` giữ kiểu số; các trường chuỗi vẫn là chuỗi. Pretty printing chỉ thêm khoảng trắng và xuống dòng để người đọc dễ xem, không đổi cấu trúc JSON.

Trong pipeline cần tiết kiệm dung lượng, có thể dùng `objectMapper.writeValueAsString(items)` trực tiếp để tạo JSON một dòng. Không thêm dòng tiêu đề như `Kết quả:` trước JSON vì khi redirect, file đầu ra sẽ không còn là JSON hợp lệ.

## 7. Thêm bộ xuất CSV

CSV phù hợp với dữ liệu dạng hàng/cột phẳng. Dùng schema để cố định tên và thứ tự cột:

```java
import java.util.List;

import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;
import org.springframework.stereotype.Component;

@Component
public class CatalogCsvFormatter {

    private final CsvMapper csvMapper;

    public CatalogCsvFormatter() {
        this.csvMapper = new CsvMapper();
    }

    public String toCsv(List<CatalogItem> items) throws Exception {
        CsvSchema schema = CsvSchema.builder()
            .addColumn("id")
            .addColumn("name")
            .addColumn("status")
            .addColumn("quantity")
            .build()
            .withHeader();

        return csvMapper
            .writer(schema)
            .writeValueAsString(items);
    }
}
```

`withHeader()` yêu cầu ghi dòng tiêu đề. Jackson CSV xử lý quote và escape giá trị chứa dấu phẩy, dấu nháy kép hoặc ký tự xuống dòng.

Không tự nối chuỗi bằng dấu phẩy. Tên mặt hàng như `Keyboard, Wireless` phải được quote đúng theo quy tắc CSV. Nếu schema có trường lồng nhau, hãy quyết định rõ cách làm phẳng thành cột thay vì dựa vào `toString()` của object.

Nếu muốn chia sẻ cấu hình CSV hoặc kiểm thử riêng, có thể đăng ký `CsvMapper` thành bean thay vì khởi tạo trong formatter. Ví dụ trên giữ mapper riêng cho thấy rõ phần serializer nào chịu trách nhiệm xuất CSV.

## 8. Chọn định dạng từ một command

Command truy vấn danh sách một lần rồi chọn formatter dựa trên `--format`:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CatalogCommands {

    private final CatalogService catalogService;
    private final CatalogOutputFormatter tableFormatter;
    private final CatalogJsonFormatter jsonFormatter;
    private final CatalogCsvFormatter csvFormatter;

    public CatalogCommands(
            CatalogService catalogService,
            CatalogOutputFormatter tableFormatter,
            CatalogJsonFormatter jsonFormatter,
            CatalogCsvFormatter csvFormatter) {
        this.catalogService = catalogService;
        this.tableFormatter = tableFormatter;
        this.jsonFormatter = jsonFormatter;
        this.csvFormatter = csvFormatter;
    }

    @ShellMethod(
        key = "catalog list",
        value = "Liệt kê mặt hàng theo định dạng được chọn."
    )
    public Object list(
            @ShellOption(
                value = "--format",
                defaultValue = "table"
            ) String rawFormat) throws Exception {

        List<CatalogItem> items = catalogService.findAll();

        return switch (rawFormat.trim().toLowerCase(Locale.ROOT)) {
            case "table" -> tableFormatter.toTable(items);
            case "json" -> jsonFormatter.toJson(items);
            case "csv" -> csvFormatter.toCsv(items);
            default -> throw new InvalidOutputFormatException(rawFormat);
        };
    }
}
```

Trong ví dụ, command dùng bộ annotation legacy của Spring Shell 3.3:

- `@ShellComponent` đánh dấu bean chứa command.
- `@ShellMethod` đăng ký command và mô tả ngắn.
- `@ShellOption` bind option `--format`; nếu người dùng không truyền, mặc định là `table`.

Command trả về `Table` cho định dạng bảng và `String` cho JSON/CSV. Spring Shell dùng result handler phù hợp với kiểu kết quả. Không gọi `System.out.println()` trong command để in thêm tiêu đề hoặc thông báo tiến độ, vì các dòng đó có thể làm hỏng dữ liệu mà script đang nhận.

## 9. Báo lỗi định dạng và trả exit code

Định dạng sai là lỗi đầu vào command. Hãy báo giá trị được hỗ trợ và trả exit code khác 0 trong chế độ non-interactive.

Exception riêng:

```java
public class InvalidOutputFormatException extends RuntimeException {

    public InvalidOutputFormatException(String format) {
        super(
            "Định dạng '" + format
                + "' không hợp lệ. Chọn table, json hoặc csv."
        );
    }
}
```

Trong Spring Shell 3.3, class `@ShellComponent` có thể khai báo method `@ExceptionResolver` để xử lý exception từ command:

```java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public CommandHandlingResult handleInvalidFormat(
        InvalidOutputFormatException exception) {

    return CommandHandlingResult.of(
        exception.getMessage(),
        2
    );
}
```

Đặt method này trong class `CatalogCommands` ở phần trước. `CommandHandlingResult` chứa thông điệp hiển thị và exit code. Ví dụ quy ước code `2` cho input không hợp lệ.

Exit code có ý nghĩa khi chạy non-interactive. Trong REPL, người dùng nhận thông báo lỗi rồi tiếp tục sử dụng shell; một lỗi ở command không nhất thiết kết thúc phiên shell. Thành công thường trả code `0`, còn lỗi không được xử lý có thể nhận code mặc định của Spring Shell.

Không dùng exit code để mã hóa toàn bộ nội dung lỗi. Hãy giữ thông báo dễ hiểu cho người đọc và mã ổn định cho script.

## 10. Cấu hình chế độ interactive, non-interactive và script

Spring Shell 3.3 có ba runner:

- `InteractiveShellRunner`: mở REPL để người dùng nhập nhiều command.
- `NonInteractiveShellRunner`: chạy command truyền từ command line rồi kết thúc.
- `ScriptShellRunner`: chạy theo cơ chế script.

Từ Spring Shell 3.3, chỉ `NonInteractiveShellRunner` được bật mặc định. Nếu ứng dụng cần REPL hoặc script runner, hãy bật rõ trong cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
  main:
    banner-mode: "off"
```

Cấu hình trên cho phép ứng dụng hỗ trợ cả ba cách chạy. Khi khởi động không truyền command, người dùng có thể vào REPL; khi truyền command như `catalog list --format=json`, ứng dụng chạy command non-interactive.

Lưu ý rằng runner non-interactive và built-in command `script` là hai khái niệm liên quan nhưng không đồng nhất. Built-in `script` đọc một file chứa các command, mỗi dòng một command; có thể gọi trong REPL bằng:

```text
script --file /absolute/path/to/catalog-commands.txt
```

Nội dung file script ví dụ:

```text
// Xuất dữ liệu máy đọc
catalog list --format=json
catalog list --format=csv
```

Nếu script được dùng để chuẩn bị môi trường tương tác, built-in command rất tiện. Nếu mục tiêu là tạo một file JSON duy nhất cho pipeline, chạy trực tiếp command non-interactive và redirect stdout sẽ dễ kiểm soát hơn.

## 11. Chạy command và chuyển kết quả cho script

Sau khi đóng gói thành executable JAR, chạy từng định dạng:

```bash
java -jar catalog-cli.jar catalog list --format=table
java -jar catalog-cli.jar catalog list --format=json
java -jar catalog-cli.jar catalog list --format=csv
```

Redirect JSON vào file:

```bash
java -jar catalog-cli.jar catalog list --format=json > catalog.json
```

Trong Bash, đọc exit code ngay sau lệnh:

```bash
java -jar catalog-cli.jar catalog list --format=json > catalog.json
status=$?
if [ "$status" -ne 0 ]; then
  echo "Không thể xuất catalog, exit code: $status" >&2
  exit "$status"
fi
```

Trong PowerShell, dùng `$LASTEXITCODE` sau tiến trình Java:

```powershell
java -jar catalog-cli.jar catalog list --format=json > catalog.json
if ($LASTEXITCODE -ne 0) {
    throw "Không thể xuất catalog, exit code: $LASTEXITCODE"
}
```

Hãy truyền `--format=json` hoặc `--format=csv` một cách tường minh trong automation. Mặc định `table` được chọn để phục vụ người đang nhìn terminal; script nên khai báo rõ hợp đồng output mà nó cần.

## 12. Giữ stdout sạch và chuyển log sang stderr

Đây là điểm quan trọng nhất khi dùng command làm nguồn dữ liệu cho pipeline.

- **stdout** chứa đúng payload JSON hoặc CSV.
- **stderr** chứa log, cảnh báo, thông báo tiến độ và lỗi vận hành.
- Không in prompt, tiêu đề, màu ANSI hoặc dòng “Đang xử lý...” vào stdout khi xuất dữ liệu có cấu trúc.

Spring Boot mặc định ghi log ra console. Nếu script redirect stdout, log khởi động có thể bị ghi lẫn vào file dữ liệu tùy cấu hình logging. Chỉ giảm log level không bảo đảm stdout sạch. Với CLI có yêu cầu output machine-readable, cấu hình Logback chuyển console log sang stderr hoặc ghi log ra file.

Ví dụ `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <appender name="STDERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="WARN">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
```

Kết hợp `banner-mode: "off"` để tắt banner Spring Boot. Nếu ứng dụng cần ghi log chi tiết, giữ chúng ở stderr hoặc file log. Không dùng `System.out` để ghi log.

Sau khi cấu hình, kiểm tra bằng cách redirect stdout rồi parse file bằng JSON parser. Nếu file bắt đầu bằng dòng log hoặc banner, hợp đồng output vẫn chưa sạch.

## 13. Định nghĩa hợp đồng output ổn định

Khi script tiêu thụ JSON/CSV, tên field và thứ tự cột trở thành một phần của hợp đồng CLI.

Một số nguyên tắc:

- Dùng tên field rõ ràng, nhất quán; không thay tên `quantity` thành `stock` mà không cập nhật caller.
- Giữ kiểu JSON: số là number, trạng thái là string, giá trị thiếu có quy tắc rõ.
- CSV phải có header ổn định và thứ tự cột được công bố.
- Không đưa màu ANSI, đường viền hoặc thông báo trang trí vào JSON/CSV.
- Không định dạng số theo locale của máy khi xuất dữ liệu cho chương trình khác.
- Nếu schema thay đổi đáng kể, cân nhắc option version hoặc command version riêng.
- Không tuần tự hóa trực tiếp domain entity nếu entity chứa field nội bộ không thuộc hợp đồng CLI.

Bảng terminal có thể thay đổi độ rộng hoặc cách căn lề mà không làm script hỏng. JSON/CSV cần được xem như API công khai của ứng dụng.

## 14. Kiểm thử cả người đọc lẫn script

Kiểm thử formatter riêng và kiểm thử command ở cả hai cách chạy.

| Trường hợp | Kiểm tra |
|---|---|
| `--format=table` | Có tiêu đề, đủ hàng và cột; không thiếu dữ liệu |
| `--format=json` | Parse được thành JSON array; kiểu `quantity` là number |
| `--format=csv` | Header và thứ tự cột đúng; giá trị có dấu phẩy được escape |
| Không truyền format | Dùng mặc định `table` |
| Format không hỗ trợ | Có thông báo rõ và exit code 2 khi non-interactive |
| Danh sách rỗng | JSON là `[]`; CSV vẫn có header; bảng thể hiện trạng thái rỗng dễ hiểu |
| Redirect stdout | File không có banner, log, prompt hoặc thông báo phụ |
| Interactive REPL | Người dùng chạy được command nhiều lần và quay lại prompt |
| Non-interactive | Process kết thúc sau command và trả exit code phù hợp |

Ví dụ unit test JSON:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CatalogJsonFormatterTests {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void exportsTypedJsonArray() throws Exception {
        CatalogJsonFormatter formatter =
            new CatalogJsonFormatter(objectMapper);

        String json = formatter.toJson(List.of(
            new CatalogItem("42", "Keyboard", "ACTIVE", 18)
        ));

        JsonNode root = objectMapper.readTree(json);

        assertEquals(1, root.size());
        assertEquals("42", root.get(0).get("id").asText());
        assertEquals(18, root.get(0).get("quantity").asInt());
    }
}
```

Test trên xác minh dữ liệu có thể parse lại và giữ đúng kiểu. Với bảng, render ở chiều rộng cố định để kiểm tra header và nội dung. Với CSV, đọc ngược bằng `CsvMapper` hoặc parser CSV khác để xác minh escaping, thay vì chỉ so sánh chuỗi có dấu phẩy.

Ở tầng command, dùng `@ShellTest` và `ShellTestClient` để kiểm tra command được đăng ký, option được bind và nội dung trả về. Với chế độ non-interactive, bổ sung kiểm thử tiến trình thật để xác minh exit code và redirect stdout.

## 15. Những lỗi thường gặp

**Trả cùng một chuỗi cho mọi đối tượng sử dụng.** Bảng phù hợp với terminal nhưng khó parse. Thêm định dạng JSON/CSV có hợp đồng rõ ràng.

**Tạo dữ liệu riêng cho từng formatter.** Các output có thể không đồng nhất. Truy vấn một lần và dùng chung DTO.

**In JSON bằng `System.out.println()` rồi trả thêm kết quả command.** Output có thể bị lặp hoặc lẫn nội dung. Trả payload từ command và để Spring Shell result handler xử lý.

**Ghi log vào stdout.** File redirect sẽ không còn là JSON/CSV hợp lệ. Chuyển log sang stderr hoặc file.

**Mặc định dùng bảng trong script.** Script phải truyền `--format=json` hoặc `--format=csv`.

**Không công bố exit code.** Caller không thể phân biệt thành công và thất bại. Định nghĩa mã ổn định và kiểm tra ở Bash/PowerShell.

**Cho rằng bật interactive runner là đủ.** Spring Shell 3.3 chỉ bật non-interactive runner theo mặc định. Cấu hình runner phù hợp với cách ứng dụng được sử dụng.

**Tự ghép CSV.** Dấu phẩy, dấu nháy kép và xuống dòng có thể làm sai cột. Dùng thư viện CSV.

**Thay schema mà không cập nhật script.** Đổi tên field hoặc cột có thể phá caller. Xem output machine-readable như một hợp đồng API.

**Dùng màu terminal trong dữ liệu máy đọc.** ANSI escape code khiến parser hoặc file dữ liệu có ký tự lạ. Chỉ dùng màu ở lớp trình bày terminal.

## 16. Ghi chú khi chuyển sang Spring Shell 4

Code command trong bài dùng bộ annotation legacy của Spring Shell 3.3:

```java
@ShellComponent
@ShellMethod
@ShellOption
```

Bộ annotation legacy này đã bị loại bỏ trong Spring Shell 4. Khi nâng cấp, chuyển command sang mô hình annotation mới trong package `org.springframework.shell.core.command.annotation`, dùng `@Component` cho bean, `@Command` cho method và `@Option` cho tham số. Phần service, DTO, formatter JSON/CSV và hợp đồng output có thể giữ nguyên.

Spring Shell 4 cũng thay đổi runner và việc tích hợp JLine. Đọc migration guide theo phiên bản đích, rồi kiểm tra lại cấu hình interactive/non-interactive và test command. Không chỉ thay import mà giữ nguyên toàn bộ cấu hình runner 3.3.

## 17. Checklist hoàn tất bài thực hành

- [ ] Một service cung cấp dữ liệu có kiểu cho mọi định dạng.
- [ ] DTO không chứa chi tiết trình bày terminal.
- [ ] Command `catalog list` có option `--format`.
- [ ] `table` trả về `Table` để người đọc terminal xem.
- [ ] `json` trả về JSON parse được.
- [ ] `csv` trả về CSV có header và escaping đúng.
- [ ] Format không hợp lệ có thông báo và exit code phù hợp.
- [ ] Interactive runner được bật nếu ứng dụng cần REPL.
- [ ] Non-interactive command chạy được từ script hoặc CI.
- [ ] Script luôn chọn định dạng machine-readable rõ ràng.
- [ ] stdout chỉ chứa payload khi redirect dữ liệu.
- [ ] Log và thông báo vận hành được chuyển sang stderr hoặc file.
- [ ] Đã kiểm thử cả formatter, command và process exit code.
- [ ] Schema JSON/CSV được xem là hợp đồng ổn định với caller.

## 18. Tài liệu tham khảo chính thức

- [Spring Shell 3.3 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): interactive, non-interactive và script runners; trạng thái mặc định từ 3.3.
- [Spring Shell 3.3 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): tạo ứng dụng, khai báo command và chạy shell.
- [Spring Shell 3.3 — Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): `@ShellComponent`, `@ShellMethod` và `@ShellOption`.
- [Spring Shell 3.3 — Exception Handling](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html) và [Exception Resolving](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/resolving.html): thông báo lỗi và exit code.
- [Spring Shell 3.3 API — Result Handlers](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/result/package-summary.html): result handlers, handler cho `TerminalSizeAware` và xử lý kết quả.
- [Spring Shell 3.3 — Built-in Script Command](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/script.html): chạy nhiều command từ file.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): console logging, file logging và tùy chỉnh Logback.
- [Jackson Dataformats — CSV](https://github.com/FasterXML/jackson-dataformats-text/tree/2.x/csv): schema và tuần tự hóa CSV.

Bài thực hành hoàn tất khi cùng một command có thể phục vụ người vận hành bằng bảng dễ đọc và phục vụ script bằng JSON/CSV ổn định. Giữ dữ liệu ở dạng có kiểu, chọn formatter ở biên CLI, tách stdout khỏi log và công bố exit code để cả người dùng lẫn automation đều có thể sử dụng ứng dụng một cách dự đoán được.

