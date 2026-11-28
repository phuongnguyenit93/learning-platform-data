# Tách bảng dễ đọc khỏi định dạng xuất dữ liệu có cấu trúc

Một command có thể cần hiển thị danh sách cho người đang nhìn terminal và đồng thời cung cấp dữ liệu cho script hoặc hệ thống khác. Hai nhu cầu này dùng cùng một tập dữ liệu nhưng cần cách biểu diễn khác nhau:

- **Bảng terminal** ưu tiên khả năng đọc: tiêu đề cột, căn lề, đường viền, xuống dòng và độ rộng phù hợp với màn hình.
- **JSON hoặc CSV** ưu tiên cấu trúc ổn định: tên trường, kiểu dữ liệu, quy tắc escape và khả năng được chương trình khác phân tích.

Không nên lấy chuỗi đã định dạng thành bảng rồi cố chuyển nó thành JSON hoặc CSV. Hãy giữ dữ liệu ở dạng có cấu trúc, sau đó chọn bộ trình bày phù hợp với mục đích sử dụng.

Bài học dùng Spring Shell 4.0.4 làm mốc chính, đồng thời nêu khác biệt API bảng giữa dòng 3.3 và 4.x.

## 1. Vì sao cần tách dữ liệu khỏi cách hiển thị?

Giả sử command `project list` trả về danh sách project:

| ID | Tên | Trạng thái |
|---:|---|---|
| 101 | billing | ACTIVE |
| 102 | inventory | PAUSED |
| 103 | customer-portal | ACTIVE |

Bảng trên phù hợp để đọc trực tiếp. Nhưng nếu một pipeline cần lấy danh sách project để tạo báo cáo, nó cần dữ liệu có cấu trúc như:

JSON:

```json
[
  {
    "id": 101,
    "name": "billing",
    "status": "ACTIVE"
  },
  {
    "id": 102,
    "name": "inventory",
    "status": "PAUSED"
  },
  {
    "id": 103,
    "name": "customer-portal",
    "status": "ACTIVE"
  }
]
```

CSV:

```csv
id,name,status
101,billing,ACTIVE
102,inventory,PAUSED
103,customer-portal,ACTIVE
```

Nếu command chỉ trả về chuỗi có dấu `|`, khoảng trắng và đường viền, script phải tự phân tích các ký tự trình bày. Việc đó dễ hỏng khi độ rộng terminal, tên cột hoặc kiểu đường viền thay đổi.

Nên giữ ba lớp trách nhiệm:

1. **Nguồn dữ liệu:** truy vấn và trả về danh sách đối tượng có kiểu.
2. **Bộ trình bày:** chuyển dữ liệu thành bảng dành cho terminal.
3. **Bộ tuần tự hóa:** chuyển dữ liệu thành JSON hoặc CSV để lưu trữ và trao đổi.

Một tập dữ liệu có thể có nhiều cách biểu diễn mà không cần thay đổi logic truy vấn.

## 2. Giữ dữ liệu ở dạng có cấu trúc

Ví dụ DTO dùng chung cho các cách xuất:

```java
public record ProjectRow(
    long id,
    String name,
    String status
) {
}
```

Application service trả về dữ liệu:

```java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class ProjectQueryService {

    public List<ProjectRow> findAll() {
        return List.of(
            new ProjectRow(101, "billing", "ACTIVE"),
            new ProjectRow(102, "inventory", "PAUSED"),
            new ProjectRow(103, "customer-portal", "ACTIVE")
        );
    }
}
```

DTO này không chứa ký tự đường viền, khoảng trắng căn lề hay chuỗi màu ANSI. `id` vẫn là số nguyên; tên và trạng thái vẫn là dữ liệu văn bản.

Không nên tạo dữ liệu ngay từ đầu thành chuỗi đã định dạng như:

```java
String row = String.format(
    "%-8s %-24s %-12s",
    project.id(),
    project.name(),
    project.status()
);
```

Nếu dùng chuỗi này làm dữ liệu nguồn, bộ xuất JSON không còn biết `id` vốn là số hay trạng thái là một trường riêng. Giữ DTO hoặc domain projection có kiểu sẽ giúp mỗi bộ xuất quyết định cách biểu diễn phù hợp.

Với dữ liệu phức tạp, có thể tạo DTO xuất riêng để công bố một hợp đồng ổn định cho JSON/CSV. Không nhất thiết phải tuần tự hóa trực tiếp toàn bộ domain entity, vì entity có thể chứa quan hệ nội bộ hoặc trường không nên công khai.

## 3. Tạo bảng terminal bằng TableModel và TableBuilder

Spring Shell cung cấp API bảng dạng ASCII để hiển thị dữ liệu theo cột. Hai thành phần cơ bản là:

- `TableModel`: mô tả số hàng, số cột và giá trị tại từng ô.
- `TableBuilder`: tạo `Table` từ model, đồng thời cấu hình đường viền, căn lề, kích thước và cách ngắt dòng.

Trong Spring Shell 4.x, API bảng thuộc package `org.springframework.shell.jline.tui.table` và module `spring-shell-jline`. Ví dụ dưới đây dùng API 4.x:

```java
import java.util.List;

import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;
import org.springframework.shell.jline.tui.table.TableModelBuilder;

public class ProjectTableRenderer {

    public Table render(List<ProjectRow> projects) {
        TableModelBuilder<String> modelBuilder =
            new TableModelBuilder<>();

        modelBuilder
            .addRow()
            .addValue("ID")
            .addValue("Tên")
            .addValue("Trạng thái");

        for (ProjectRow project : projects) {
            modelBuilder
                .addRow()
                .addValue(Long.toString(project.id()))
                .addValue(project.name())
                .addValue(project.status());
        }

        TableModel model = modelBuilder.build();

        return new TableBuilder(model)
            .addHeaderBorder(BorderStyle.fancy_light)
            .build();
    }
}
```

`TableModelBuilder` thêm hàng bằng `addRow()` và thêm giá trị vào hàng hiện tại bằng `addValue(...)`. Hàng đầu tiên trong ví dụ là tiêu đề; các hàng tiếp theo chứa dữ liệu project.

`TableBuilder` có thể cấu hình nhiều kiểu đường viền:

| Phương thức | Tác dụng |
|---|---|
| `addOutlineBorder(style)` | Vẽ đường viền bao quanh bảng |
| `addHeaderBorder(style)` | Vẽ viền ngoài và đường phân cách tiêu đề |
| `addFullBorder(style)` | Vẽ đường viền cho từng ô |
| `addInnerBorder(style)` | Vẽ đường phân cách bên trong |
| `addHeaderAndVerticalsBorders(style)` | Vẽ viền ngoài, tiêu đề và đường dọc giữa cột |

Một số kiểu `BorderStyle` có sẵn gồm `oldschool`, `fancy_light`, `fancy_heavy`, `fancy_double` và `air`. Chọn kiểu phù hợp với font và terminal mục tiêu; kiểu dùng ký tự box-drawing có thể hiển thị khác nhau trên một số môi trường.

### 3.1. Để Spring Shell render bảng theo chiều rộng terminal

Trong Spring Shell 4.x, `Table` triển khai `TerminalSizeAware`. Khi command trả về đối tượng `Table`, result handler tương ứng có thể gọi `render(...)` theo chiều rộng terminal hiện tại.

Ví dụ command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;
import org.springframework.shell.jline.tui.table.Table;

@Component
public class ProjectCommands {

    private final ProjectQueryService projectQueryService;
    private final ProjectTableRenderer tableRenderer;

    public ProjectCommands(
            ProjectQueryService projectQueryService,
            ProjectTableRenderer tableRenderer) {
        this.projectQueryService = projectQueryService;
        this.tableRenderer = tableRenderer;
    }

    @Command(name = "project list")
    public Table list() {
        var projects = projectQueryService.findAll();
        return tableRenderer.render(projects);
    }
}
```

Cách trả về `Table` cho phép Spring Shell xử lý phần render theo kích thước terminal. Nếu cần tự kiểm tra kết quả trong unit test, có thể gọi `table.render(80)` để cố định chiều rộng đầu ra.

### 3.2. Tùy chỉnh cách định dạng ô

`TableBuilder` hỗ trợ tùy chỉnh theo `CellMatcher`. Có thể áp dụng formatter, aligner, sizer hoặc text wrapper cho một cột hay nhóm ô phù hợp.

Một số nguyên tắc trình bày hữu ích:

- Căn phải cột số để người đọc dễ so sánh giá trị.
- Căn trái tên và mô tả.
- Giới hạn độ rộng cột chứa văn bản dài.
- Cho phép xuống dòng ở ranh giới từ khi cần.
- Chỉ hiển thị các cột phục vụ thao tác hiện tại.

Theo mặc định, builder dùng `toString()` để định dạng giá trị, tìm cách tận dụng không gian cột, ngắt dòng tại dấu cách và căn trái. Khi dữ liệu có định dạng riêng, hãy cấu hình rõ thay vì dựa vào `toString()`.

## 4. Xuất JSON từ cùng tập dữ liệu

JSON phù hợp khi dữ liệu có cấu trúc đối tượng, có thể chứa kiểu số, boolean, mảng và đối tượng lồng nhau. Đây là định dạng thuận tiện cho REST client, script, công cụ xử lý dữ liệu và pipeline.

Ví dụ dùng Jackson 2.x:

```java
import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public class ProjectJsonExporter {

    private final ObjectMapper objectMapper;

    public ProjectJsonExporter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String export(List<ProjectRow> projects)
            throws JsonProcessingException {

        return objectMapper
            .writerWithDefaultPrettyPrinter()
            .writeValueAsString(projects);
    }
}
```

Jackson đọc các trường của DTO và tuần tự hóa thành mảng JSON. `id` là số trong JSON vì thuộc tính Java có kiểu `long`; ứng dụng không phải phân tích lại chuỗi hiển thị trong bảng.

Nếu muốn output gọn cho máy đọc, dùng `writeValueAsString(...)` trực tiếp thay cho `writerWithDefaultPrettyPrinter()`. Pretty printing chỉ thay đổi khoảng trắng và xuống dòng, không thay đổi cấu trúc JSON.

Ví dụ trên dùng namespace Jackson 2 (`com.fasterxml.jackson...`). Nếu dự án Spring Boot 4 sử dụng Jackson 3, hãy dùng module và namespace Jackson 3 theo dependency management của dự án; không trộn các major version của Jackson trong cùng ứng dụng.

## 5. Xuất CSV từ cùng tập dữ liệu

CSV phù hợp với dữ liệu dạng bảng phẳng, thường được dùng trong spreadsheet, công cụ BI hoặc import/export hàng loạt.

Có thể dùng Jackson CSV để xác định thứ tự cột và hàng tiêu đề:

Ví dụ dưới đây cũng dùng Jackson 2.x, cùng major version với ví dụ JSON ở phần trước. Hãy dùng module CSV tương ứng với major version Jackson mà ứng dụng đang quản lý.

```java
import java.util.List;

import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

public class ProjectCsvExporter {

    private final CsvMapper csvMapper;

    public ProjectCsvExporter(CsvMapper csvMapper) {
        this.csvMapper = csvMapper;
    }

    public String export(List<ProjectRow> projects) throws Exception {
        CsvSchema schema = CsvSchema.builder()
            .addColumn("id")
            .addColumn("name")
            .addColumn("status")
            .build()
            .withHeader();

        return csvMapper
            .writer(schema)
            .writeValueAsString(projects);
    }
}
```

Schema xác định thứ tự cột `id`, `name`, `status` và `withHeader()` yêu cầu ghi dòng tiêu đề. Thư viện CSV xử lý việc quote và escape các giá trị chứa dấu phẩy, dấu nháy kép hoặc ký tự xuống dòng.

Không nên tự nối chuỗi bằng dấu phẩy:

```java
String csv = project.id() + ","
    + project.name() + ","
    + project.status();
```

Nếu tên project chứa dấu phẩy hoặc dấu nháy kép, dòng CSV có thể bị phân cột sai. Dùng thư viện CSV chuyên dụng và kiểm thử các giá trị có ký tự đặc biệt.

CSV là định dạng phẳng. Nếu dữ liệu có cấu trúc lồng nhau, hãy quyết định rõ cách chuyển thành cột, ví dụ `owner.name`, `owner.email`, hoặc xuất thành nhiều file liên quan. Đừng phụ thuộc vào `toString()` của object lồng nhau để tạo CSV.

## 6. Chọn định dạng bằng option của command

Có thể cung cấp một option `--format` để người dùng chọn cách biểu diễn. Command truy vấn dữ liệu một lần, sau đó chuyển dữ liệu sang renderer hoặc serializer tương ứng.

Ví dụ với Spring Shell 4.x:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectExportCommands {

    private final ProjectQueryService projectQueryService;
    private final ProjectTableRenderer tableRenderer;
    private final ProjectJsonExporter jsonExporter;
    private final ProjectCsvExporter csvExporter;

    public ProjectExportCommands(
            ProjectQueryService projectQueryService,
            ProjectTableRenderer tableRenderer,
            ProjectJsonExporter jsonExporter,
            ProjectCsvExporter csvExporter) {
        this.projectQueryService = projectQueryService;
        this.tableRenderer = tableRenderer;
        this.jsonExporter = jsonExporter;
        this.csvExporter = csvExporter;
    }

    @Command(name = "project list")
    public Object list(
            @Option(
                longName = "format",
                defaultValue = "table",
                description = "Định dạng: table, json hoặc csv"
            ) String rawFormat) throws Exception {

        List<ProjectRow> projects = projectQueryService.findAll();

        return switch (rawFormat.trim().toLowerCase(Locale.ROOT)) {
            case "table" -> tableRenderer.render(projects);
            case "json" -> jsonExporter.export(projects);
            case "csv" -> csvExporter.export(projects);
            default -> throw new IllegalArgumentException(
                "Định dạng không hợp lệ. Chọn table, json hoặc csv."
            );
        };
    }
}
```

Command trả về `Table` khi người dùng chọn `table`, còn hai định dạng xuất dữ liệu trả về `String`. Spring Shell chọn result handler dựa trên kiểu kết quả thực tế: `Table` được render theo khả năng terminal; chuỗi JSON/CSV được ghi ra output.

Cách gọi:

```text
project list
project list --format=table
project list --format=json
project list --format=csv
```

Nên giữ giá trị mặc định là `table` nếu command chủ yếu phục vụ người dùng trực tiếp. Trong job tự động, hãy yêu cầu caller chọn định dạng cụ thể để hợp đồng output rõ ràng.

## 7. Ghi output vào file và giữ stdout sạch

Trong chế độ non-interactive, có thể chuyển output của command sang file bằng redirection của hệ điều hành:

```bash
java -jar project-cli.jar project list --format=json > projects.json
java -jar project-cli.jar project list --format=csv > projects.csv
```

Nếu command hoặc wrapper hỗ trợ option `--output`, có thể ghi trực tiếp vào đường dẫn được chỉ định. Dù chọn cách nào, hãy phân biệt:

- **stdout:** chỉ chứa nội dung JSON hoặc CSV khi được dùng làm dữ liệu đầu ra.
- **stderr:** chứa log, cảnh báo, thông báo tiến độ và lỗi vận hành.

Ví dụ, nếu chương trình in dòng `Đang tải project...` vào stdout trước JSON, file được tạo bằng `>` sẽ không còn là JSON hợp lệ. Không thêm tiêu đề trang trí, bảng ASCII, mã màu ANSI hoặc thông báo hoàn tất vào luồng dữ liệu có cấu trúc.

Khi ghi file, nên dùng UTF-8 và xử lý rõ trường hợp file đích đã tồn tại. Với thao tác xuất dữ liệu có thể ghi đè file, hãy cung cấp option xác nhận hoặc quy tắc ghi đè rõ ràng.

## 8. Phân biệt Table, JSON, CSV và chuỗi thông thường

| Đặc điểm | Table terminal | JSON | CSV | Chuỗi `toString()` |
|---|---|---|---|---|
| Mục đích | Người đọc trên terminal | Trao đổi dữ liệu có cấu trúc | Trao đổi dữ liệu dạng bảng | Debug hoặc mô tả đơn giản |
| Tiêu đề cột | Có thể có | Tên field | Dòng header tùy chọn | Không có quy ước |
| Kiểu dữ liệu | Được chuyển thành văn bản để hiển thị | Có thể giữ number, boolean, object, array | Chủ yếu là giá trị văn bản theo cột | Phụ thuộc implementation |
| Căn lề/đường viền | Có | Không | Không | Không |
| Phụ thuộc chiều rộng terminal | Có thể có | Không | Không | Không |
| Phân tích tự động | Không nên dùng | Có | Có | Không có hợp đồng ổn định |
| Dữ liệu lồng nhau | Khó biểu diễn | Hỗ trợ tự nhiên | Cần làm phẳng | Không có quy tắc |

Không dùng bảng ASCII làm định dạng trao đổi dữ liệu. Cũng không xem `toString()` của DTO là hợp đồng xuất dữ liệu. Nếu một chương trình khác cần đọc kết quả, hãy chọn JSON hoặc CSV và định nghĩa schema phù hợp.

## 9. Cách chọn giữa JSON và CSV

Chọn JSON khi:

- Dữ liệu có quan hệ lồng nhau hoặc nhiều kiểu giá trị.
- Caller cần phân biệt số, boolean, chuỗi, null, mảng và object.
- Dữ liệu sẽ được truyền giữa các service hoặc API.
- Cần mở rộng schema mà không phải biến mọi trường thành cột phẳng.

Chọn CSV khi:

- Dữ liệu có cấu trúc hàng và cột rõ ràng.
- Người dùng cần mở bằng spreadsheet.
- Dữ liệu được nhập vào công cụ phân tích dạng bảng.
- Schema có số cột ổn định và không cần cấu trúc lồng nhau.

Chọn bảng terminal khi:

- Người vận hành cần xem nhanh danh sách.
- Cần căn lề, phân tách cột hoặc xuống dòng theo chiều rộng màn hình.
- Output chủ yếu phục vụ phiên shell tương tác.

Nếu cần cả ba, hãy giữ một DTO xuất ổn định và triển khai ba bộ chuyển đổi riêng.

## 10. Khác biệt API bảng giữa Spring Shell 3.3 và 4.x

Khi nâng cấp, cần cập nhật cả dependency và package import:

| Nội dung | Spring Shell 3.3.x | Spring Shell 4.x |
|---|---|---|
| Module bảng | `spring-shell-table` là module riêng | Được hợp nhất vào `spring-shell-jline` |
| Package | `org.springframework.shell.table` | `org.springframework.shell.jline.tui.table` |
| API chính | `TableModel`, `TableModelBuilder`, `TableBuilder`, `Table` | Cùng vai trò, package mới |
| Dependency khi tự lắp ghép | Thêm `spring-shell-table` | Thêm `spring-shell-jline` |
| Chạy chỉ với core | Có thể dùng module bảng riêng | Không có API bảng nếu không đưa module JLine vào classpath |

Ví dụ import trong 3.3:

```java
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModelBuilder;
```

Trong 4.x:

```java
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModelBuilder;
```

Spring Shell 4 tách JLine khỏi `spring-shell-core`. Nếu ứng dụng chỉ dùng `SystemShellRunner` và không có dependency `spring-shell-jline`, API bảng của module JLine cũng không có sẵn. Khi cần bảng ASCII, hãy thêm module JLine hoặc chọn một cách trình bày văn bản khác phù hợp với cấu hình dependency.

## 11. ResultHandler và khi nào cần tùy chỉnh

Spring Shell dùng `ResultHandlerService` để xử lý kết quả trả về từ command. Các `ResultHandler` chuyên biệt có thể xử lý kiểu kết quả cụ thể; ví dụ `Table` triển khai `TerminalSizeAware` để result handler hiển thị theo chiều rộng terminal.

Với một command có option `--format`, dispatch rõ ràng như ví dụ trên thường dễ hiểu và dễ kiểm thử. Nếu nhiều command trả về cùng một kiểu kết quả tùy chỉnh và cần cùng quy tắc trình bày, có thể cân nhắc đăng ký `ResultHandler<T>` riêng cho kiểu đó.

Không nên tạo custom result handler chỉ để tuần tự hóa mọi object thành JSON một cách âm thầm. Người gọi command cần biết output đang là bảng, JSON hay CSV; định dạng xuất nên được chọn rõ ràng trong hợp đồng command hoặc cấu hình ứng dụng.

## 12. Kiểm thử các bộ xuất

Tách renderer và serializer giúp kiểm thử từng phần độc lập.

Với bảng terminal, kiểm tra:

- Tiêu đề và thứ tự cột đúng.
- Hàng dữ liệu không bị thiếu.
- Giá trị null hoặc chuỗi dài được xử lý theo quy tắc trình bày.
- Bảng có thể render với chiều rộng terminal nhỏ và lớn.
- Ký tự Unicode hiển thị hợp lý trên môi trường mục tiêu.

Với JSON, kiểm tra:

- Kết quả parse lại được.
- Tên field và kiểu dữ liệu đúng.
- Giá trị null, số và chuỗi được bảo toàn.
- Không có log hoặc thông báo tiến độ chen vào stdout.

Với CSV, kiểm tra:

- Dòng header có đúng tên và thứ tự cột.
- Dữ liệu có dấu phẩy, dấu nháy kép và xuống dòng được escape đúng.
- Giá trị null và chuỗi rỗng có quy tắc phân biệt rõ.
- Số và ngày dùng quy ước không phụ thuộc locale của máy.

Không nên chỉ so sánh một bảng ASCII dài theo chuỗi cố định nếu kết quả phụ thuộc terminal width. Có thể gọi `render(80)` trong unit test để cố định chiều rộng, hoặc kiểm tra các thành phần quan trọng của output.

## 13. Các lỗi thường gặp

**Dùng chuỗi bảng làm nguồn dữ liệu JSON/CSV.** Khi thay đổi độ rộng hoặc border, parser bên ngoài có thể hỏng. Hãy tuần tự hóa DTO gốc.

**Dựa vào `Object.toString()` để xuất JSON.** `toString()` không bảo đảm tên field, kiểu dữ liệu hay schema ổn định. Dùng serializer có hợp đồng rõ ràng.

**Tự nối CSV bằng dấu phẩy.** Dữ liệu có dấu phẩy, dấu nháy kép hoặc xuống dòng sẽ làm sai cấu trúc. Dùng thư viện CSV.

**Dùng định dạng số theo locale trong file máy đọc.** Dấu phẩy thập phân hoặc phân cách hàng nghìn có thể bị hiểu sai. Dùng quy ước ổn định cho JSON/CSV; chỉ định dạng theo locale ở bảng terminal.

**Xuất object lồng nhau thành một chuỗi không có quy ước.** Với CSV, hãy làm phẳng thành cột rõ ràng; với JSON, giữ cấu trúc object/array.

**Đưa ANSI color code vào JSON/CSV.** Ký tự điều khiển có thể làm dữ liệu khó đọc hoặc phá công cụ phân tích. Chỉ dùng màu ở lớp trình bày terminal.

**Ghi log vào stdout khi xuất dữ liệu.** Redirection có thể tạo file JSON/CSV không hợp lệ. Dùng stderr cho log và thông báo vận hành.

**Quên dependency bảng khi nâng lên 4.x.** Module `spring-shell-table` đã được hợp nhất vào `spring-shell-jline`; cập nhật dependency và package import.

**Dùng bảng khi ứng dụng chỉ có core.** API bảng 4.x nằm trong module JLine. Nếu không muốn thêm module này, hãy dùng output văn bản đơn giản hoặc định dạng dữ liệu có cấu trúc.

## 14. Checklist triển khai

- [ ] Giữ dữ liệu truy vấn ở dạng DTO/domain projection có kiểu.
- [ ] Không đưa border, căn lề hoặc mã màu vào DTO.
- [ ] Dùng `TableModel` và `TableBuilder` cho bảng dành cho terminal.
- [ ] Cấu hình tiêu đề, đường viền, độ rộng và wrapping theo nhu cầu.
- [ ] Dùng JSON khi cần cấu trúc dữ liệu hoặc kiểu lồng nhau.
- [ ] Dùng CSV khi dữ liệu có schema hàng/cột phẳng.
- [ ] Dùng thư viện tuần tự hóa để xử lý escaping và kiểu dữ liệu.
- [ ] Cung cấp option `--format` với danh sách giá trị rõ ràng.
- [ ] Giữ stdout sạch khi xuất JSON/CSV.
- [ ] Ghi log và thông báo vận hành ra stderr.
- [ ] Cập nhật package và dependency bảng khi chuyển từ 3.3 lên 4.x.
- [ ] Kiểm thử riêng renderer, JSON serializer, CSV serializer và luồng command.
- [ ] Kiểm thử dữ liệu chứa Unicode, dấu phẩy, dấu nháy kép, xuống dòng và null.

## 15. Tài liệu tham khảo chính thức

- [Spring Shell 3.3 — Package `org.springframework.shell.table`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/package-summary.html): các kiểu `Table`, `TableModel`, `TableBuilder`, formatter và chiến lược căn lề.
- [Spring Shell 3.3 — TableBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TableBuilder.html): cách tạo bảng và cấu hình đường viền.
- [Spring Shell 4.x — TableBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html): API bảng trong package JLine của Spring Shell 4.
- [Spring Shell 4.x — Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html): render bảng theo chiều rộng được cung cấp.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): module `spring-shell-table` được hợp nhất vào `spring-shell-jline` và thay đổi package API.
- [Jackson Dataformats — CSV](https://github.com/FasterXML/jackson-dataformats-text/tree/2.x/csv): tuần tự hóa dữ liệu Java sang CSV và cấu hình schema.

Hãy truy vấn dữ liệu một lần, giữ nó ở dạng có cấu trúc và chọn cách biểu diễn tại biên CLI. Bảng ASCII phục vụ người đọc terminal; JSON và CSV phục vụ chương trình khác. Sự tách biệt này giúp giao diện có thể thay đổi mà không làm hỏng hợp đồng dữ liệu mà script hoặc hệ thống tích hợp đang sử dụng.

