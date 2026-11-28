# Hiển thị bảng kết quả có thể thích ứng độ rộng terminal

Một command liệt kê bản phát hành có thể chạy trên nhiều môi trường: terminal rộng của lập trình viên, cửa sổ terminal hẹp trong IDE, SSH session, container hoặc pipeline CI. Nếu luôn in cùng một bảng với sáu cột, kết quả có thể bị tràn dòng, mất cột hoặc khó đọc khi terminal chỉ rộng 60 ký tự. Nếu chỉ hiển thị ba cột, người dùng terminal rộng lại thiếu thông tin cần thiết.

Trong bài thực hành này, ta xây dựng command deployment list để hiển thị danh sách bản phát hành. Bảng sẽ thay đổi số cột theo chiều rộng terminal: terminal rộng hiển thị đầy đủ thông tin, terminal vừa ẩn cột ít quan trọng, terminal hẹp chỉ giữ thông tin chính và terminal rất hẹp chuyển sang dạng tóm tắt từng dòng.

Ứng dụng dùng Spring Shell 4.0.4 và JLine. Ta đọc chiều rộng từ JLine Terminal, cho phép người dùng ghi đè bằng option --width, tạo dữ liệu bảng bằng TableModelBuilder và render bằng TableBuilder.

## 1. Kết quả cần đạt

Command sau khi hoàn thành có thể được gọi như sau:

~~~text
deployment list
deployment list --width 120
deployment list --width 80
deployment list --width 45
~~~

Kết quả thay đổi theo chiều rộng:

| Chiều rộng | Cách trình bày |
|---:|---|
| Từ 120 cột | ID, ứng dụng, trạng thái, môi trường, người triển khai và revision |
| 90–119 cột | ID, ứng dụng, trạng thái và môi trường |
| 60–89 cột | ID, ứng dụng và trạng thái |
| Dưới 60 cột | Mỗi bản phát hành thành một dòng tóm tắt |

Người dùng vẫn chạy cùng một command. Logic chọn layout nằm trong renderer, không rải điều kiện độ rộng khắp command handler.

## 2. Kiến trúc của bài thực hành

Tách phần truy vấn dữ liệu, quyết định layout và tích hợp terminal thành các trách nhiệm riêng:

~~~mermaid
flowchart LR
    A["deployment list"] --> B["DeploymentCommands"]
    B --> C["JLine Terminal"]
    B --> D["DeploymentQuery"]
    D --> E["DeploymentRow list"]
    E --> F["DeploymentTableRenderer"]
    C --> G["Effective width"]
    G --> F
    F --> H["TableModelBuilder"]
    H --> I["TableBuilder"]
    I --> J["Table.render(width)"]
    J --> K["Command output"]
~~~

- DeploymentQuery lấy dữ liệu nghiệp vụ.
- DeploymentCommands nhận option và lấy chiều rộng terminal.
- DeploymentTableRenderer chọn số cột và dựng bảng.
- TableModelBuilder tạo các hàng dữ liệu.
- TableBuilder cấu hình border và quy tắc hiển thị.
- Table.render(width) tạo chuỗi cuối cùng theo chiều rộng đã chọn.

Cách chia này giúp có thể kiểm thử renderer mà không cần khởi động terminal hoặc kết nối database.

## 3. Chuẩn bị dependency Spring Shell 4.0.4

Trong Spring Shell 4, phần tích hợp JLine được tách khỏi core. API bảng ASCII của phiên bản này nằm trong package org.springframework.shell.jline.tui.table và được cung cấp qua module spring-shell-jline.

Nếu ứng dụng đã dùng starter có JLine thì không cần thêm dependency trùng. Nếu ứng dụng chỉ dùng spring-shell-core, hãy thêm module JLine:

~~~groovy
dependencies {
    implementation("org.springframework.shell:spring-shell-core")
    implementation("org.springframework.shell:spring-shell-jline")
}
~~~

Sử dụng dependency management hoặc BOM tương ứng với Spring Shell 4.0.4 để các module có cùng phiên bản.

Không trộn package bảng cũ org.springframework.shell.table với API 4.x trong org.springframework.shell.jline.tui.table. Migration guide của Spring Shell 4 ghi rõ module table đã được gộp vào module JLine.

## 4. Đọc chiều rộng terminal bằng JLine

JLine cung cấp interface org.jline.terminal.Terminal. Spring Shell JLine auto-configuration đăng ký một bean Terminal để command có thể inject qua constructor.

Terminal cung cấp getWidth() và getHeight(). Đối với bài này, ta cần getWidth() để biết số cột đang hiển thị.

~~~java
import org.jline.terminal.Terminal;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    private final Terminal terminal;

    DeploymentCommands(Terminal terminal) {
        this.terminal = terminal;
    }
}
~~~

Nếu ứng dụng chỉ dùng Spring Shell core mà không có JLine module, bean Terminal không có sẵn. Hãy kiểm tra dependency trước khi điều tra lỗi injection.

Không dùng System.console() để thay thế JLine Terminal trong ứng dụng đã chọn JLine. Hai API này thuộc hai mô hình nhập xuất khác nhau.

## 5. Xác định chiều rộng hiệu lực

Chiều rộng có thể lấy từ terminal hoặc được truyền trực tiếp bằng option. Option hữu ích khi:

- Người dùng muốn ép bảng hiển thị ở một kích thước cụ thể.
- Test cần kiểm tra layout 45, 70, 90 hoặc 120 cột một cách lặp lại.
- CI hoặc script không có terminal tương tác.
- Log được lưu vào artifact và cần kết quả có chiều rộng cố định.

Quy tắc chọn chiều rộng:

1. Nếu người dùng truyền --width, dùng giá trị đó.
2. Nếu không, lấy Terminal.getWidth().
3. Nếu terminal trả về giá trị không hợp lệ, dùng fallback 100.
4. Giới hạn giá trị trong khoảng hợp lý để tránh layout bất thường.

~~~java
private static final int DEFAULT_WIDTH = 100;
private static final int MIN_WIDTH = 24;
private static final int MAX_WIDTH = 200;

private int resolveWidth(int requestedWidth) {
    if (requestedWidth != -1 && requestedWidth < MIN_WIDTH) {
        throw new IllegalArgumentException(
                "Chiều rộng phải từ 24 cột trở lên.");
    }

    int width = requestedWidth > 0
            ? requestedWidth
            : terminal.getWidth();

    if (width <= 0) {
        width = DEFAULT_WIDTH;
    }

    return Math.min(width, MAX_WIDTH);
}
~~~

Giá trị -1 có nghĩa là tự lấy từ terminal. Giá trị 0 hoặc nhỏ hơn -1 là input không hợp lệ. Nếu terminal không báo được kích thước, ứng dụng dùng fallback thay vì tạo bảng với chiều rộng bằng 0.

## 6. Tạo model cho dữ liệu bản phát hành

Ví dụ một dòng dữ liệu có các trường:

~~~java
record DeploymentRow(
        long id,
        String application,
        String status,
        String environment,
        String owner,
        String revision) {
}
~~~

Một service truy vấn trả về danh sách mới nhất:

~~~java
import java.util.List;

interface DeploymentQuery {

    List<DeploymentRow> findLatest();
}
~~~

Trong ứng dụng thực tế, implementation có thể gọi repository, REST API hoặc database. Renderer chỉ nhận danh sách DeploymentRow và không cần biết dữ liệu đến từ đâu.

Ví dụ dữ liệu:

~~~java
List<DeploymentRow> rows = List.of(
        new DeploymentRow(
                1042, "api-gateway", "SUCCESS", "production",
                "release-bot", "a13f9c2d"),
        new DeploymentRow(
                1041, "billing-worker", "FAILED", "staging",
                "nguyen-an", "e82b710a"),
        new DeploymentRow(
                1040, "customer-portal", "SUCCESS", "production",
                "tran-minh", "8c0b51ef")
);
~~~

## 7. Thiết kế các profile hiển thị

Không nên chỉ thu nhỏ mọi cột bằng một tỷ lệ cố định. Khi terminal hẹp, người dùng cần giữ thông tin quan trọng nhất.

Ta dùng bốn profile:

| Profile | Cột | Lý do |
|---|---|---|
| Full | ID, ứng dụng, trạng thái, môi trường, người triển khai, revision | Dành cho terminal rộng |
| Medium | ID, ứng dụng, trạng thái, môi trường | Ẩn người triển khai và revision |
| Compact table | ID, ứng dụng, trạng thái | Giữ ba trường cốt lõi |
| Single-line | ID, ứng dụng rút gọn, trạng thái | Dành cho terminal rất hẹp |

Thứ tự ưu tiên cột:

1. ID: xác định bản ghi.
2. Ứng dụng: xác định đối tượng.
3. Trạng thái: biết kết quả.
4. Môi trường: biết nơi triển khai.
5. Người triển khai và revision: thông tin bổ sung.

Khi chiều rộng giảm, bỏ các cột bổ sung trước. Không bỏ trạng thái hoặc ID vì đây là hai trường quan trọng khi điều tra sự cố.

## 8. Xây dựng DeploymentTableRenderer

Renderer nhận danh sách và chiều rộng. Nó chọn profile, tạo model rồi render.

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModelBuilder;
import org.springframework.stereotype.Component;

@Component
class DeploymentTableRenderer {

    private static final int FULL_WIDTH = 120;
    private static final int MEDIUM_WIDTH = 90;
    private static final int TABLE_WIDTH = 60;

    String render(List<DeploymentRow> rows, int terminalWidth) {
        int width = Math.max(24, Math.min(terminalWidth, 200));

        if (rows.isEmpty()) {
            return "Không có bản phát hành nào.";
        }

        if (width < TABLE_WIDTH) {
            return renderSingleLine(rows, width);
        }

        boolean includeEnvironment = width >= MEDIUM_WIDTH;
        boolean includeDetails = width >= FULL_WIDTH;

        TableModelBuilder<Object> model = new TableModelBuilder<>();

        addHeader(model, includeEnvironment, includeDetails);

        for (DeploymentRow row : rows) {
            addDeployment(model, row, includeEnvironment, includeDetails);
        }

        Table table = new TableBuilder(model.build())
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        return table.render(width);
    }

    private void addHeader(
            TableModelBuilder<Object> model,
            boolean includeEnvironment,
            boolean includeDetails) {

        model.addRow()
                .addValue("ID")
                .addValue("Ứng dụng")
                .addValue("Trạng thái");

        if (includeEnvironment) {
            model.addValue("Môi trường");
        }

        if (includeDetails) {
            model.addValue("Người triển khai")
                    .addValue("Revision");
        }
    }

    private void addDeployment(
            TableModelBuilder<Object> model,
            DeploymentRow row,
            boolean includeEnvironment,
            boolean includeDetails) {

        model.addRow()
                .addValue(row.id())
                .addValue(clip(row.application(), 28))
                .addValue(row.status());

        if (includeEnvironment) {
            model.addValue(clip(row.environment(), 16));
        }

        if (includeDetails) {
            model.addValue(clip(row.owner(), 18))
                    .addValue(clip(row.revision(), 12));
        }
    }

    private String renderSingleLine(
            List<DeploymentRow> rows,
            int width) {

        int applicationWidth = Math.max(1, width - 19);

        return rows.stream()
                .map(row -> "#" + clip(String.valueOf(row.id()), 6)
                        + " " + clip(row.application(), applicationWidth)
                        + " [" + clip(row.status(), 8) + "]")
                .collect(Collectors.joining(System.lineSeparator()));
    }

    private static String clip(String value, int maxCodePoints) {
        if (value == null || value.isBlank()) {
            return "";
        }

        String normalized = value.replaceAll("\\s+", " ").trim();
        int length = normalized.codePointCount(0, normalized.length());

        if (length <= maxCodePoints) {
            return normalized;
        }

        if (maxCodePoints <= 1) {
            return "…";
        }

        int end = normalized.offsetByCodePoints(0, maxCodePoints - 1);
        return normalized.substring(0, end) + "…";
    }
}
~~~

Đây là renderer dùng cho một bảng kết quả có cấu trúc ổn định. Nếu thêm cột mới, hãy cập nhật cả header và dữ liệu theo cùng một điều kiện để số cột luôn khớp nhau.

## 9. Hiểu TableModelBuilder và TableBuilder

TableModelBuilder tạo model theo từng hàng. Mỗi lần gọi addRow() bắt đầu một hàng; các lần addValue() tiếp theo thêm giá trị cho các cột của hàng đó.

Ví dụ:

~~~java
TableModelBuilder<Object> model = new TableModelBuilder<>();

model.addRow()
        .addValue("ID")
        .addValue("Ứng dụng")
        .addValue("Trạng thái");

model.addRow()
        .addValue(1042)
        .addValue("api-gateway")
        .addValue("SUCCESS");

Table table = new TableBuilder(model.build())
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

TableBuilder cấu hình cách bảng được vẽ. Các API thường dùng:

| API | Mục đích |
|---|---|
| TableBuilder(TableModel) | Tạo builder từ model |
| addHeaderBorder(style) | Viền ngoài và đường viền dưới header |
| addOutlineBorder(style) | Chỉ vẽ viền ngoài |
| addFullBorder(style) | Vẽ viền quanh từng ô |
| on(CellMatcher) | Chọn các ô cần áp dụng formatter, sizer hoặc wrapper |
| build() | Tạo Table |
| Table.render(width) | Render với tổng chiều rộng được cung cấp |

Mặc định, TableBuilder dùng toString() để chuyển giá trị thành text, cố gắng phân bổ tối đa chiều rộng cho các ô và wrap nội dung tại dấu cách. Điều này phù hợp với các cột chứa mô tả bằng câu hoặc cụm từ.

## 10. Render theo chiều rộng thực tế

Sau khi có Table, gọi render(width) với chiều rộng đã xác định. API nhận tổng chiều rộng có thể sử dụng và trả về chuỗi kết quả.

~~~java
Table table = new TableBuilder(model.build())
        .addHeaderBorder(BorderStyle.oldschool)
        .build();

String output = table.render(terminalWidth);
~~~

Không cần tự tính độ rộng từng cột trong trường hợp thông thường. Table xử lý size constraints, wrapping và alignment.

Tuy nhiên, renderer vẫn cần chọn số cột hợp lý. Một bảng có tám cột không thể trở nên dễ đọc chỉ bằng cách thu nhỏ từng cột xuống vài ký tự.

## 11. Tích hợp renderer vào command Spring Shell

Command nhận option width, lấy dữ liệu và gọi renderer.

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    private final Terminal terminal;
    private final DeploymentQuery deploymentQuery;
    private final DeploymentTableRenderer renderer;

    DeploymentCommands(
            Terminal terminal,
            DeploymentQuery deploymentQuery,
            DeploymentTableRenderer renderer) {
        this.terminal = terminal;
        this.deploymentQuery = deploymentQuery;
        this.renderer = renderer;
    }

    @Command(
            name = "deployment list",
            description = "Liệt kê các bản phát hành gần đây")
    public String list(
            @Option(
                    longName = "width",
                    defaultValue = "-1",
                    description = "Ép chiều rộng bảng; -1 dùng chiều rộng terminal")
            int requestedWidth) {

        if (requestedWidth != -1 && requestedWidth < 24) {
            throw new IllegalArgumentException(
                    "Option width phải bằng -1 hoặc từ 24 trở lên.");
        }

        int width = requestedWidth > 0
                ? requestedWidth
                : terminal.getWidth();

        if (width <= 0) {
            width = 100;
        }

        return renderer.render(deploymentQuery.findLatest(), width);
    }
}
~~~

Command method trả về String. Spring Shell xử lý kết quả command và in chuỗi ra terminal. Renderer không tự ghi trực tiếp vào System.out, nên có thể kiểm thử độc lập và không phụ thuộc stream toàn cục.

## 12. Quan sát kết quả ở các kích thước khác nhau

Ví dụ với terminal rộng 130 cột:

~~~text
+------+----------------+------------+-------------+------------------+------------+
| ID   | Ứng dụng       | Trạng thái | Môi trường  | Người triển khai | Revision   |
+------+----------------+------------+-------------+------------------+------------+
| 1042 | api-gateway    | SUCCESS    | production  | release-bot      | a13f9c2d   |
| 1041 | billing-worker | FAILED     | staging     | nguyen-an        | e82b710a   |
| 1040 | customer-portal| SUCCESS    | production  | tran-minh        | 8c0b51ef   |
+------+----------------+------------+-------------+------------------+------------+
~~~

Ở 100 cột, renderer bỏ hai cột phụ:

~~~text
+------+----------------+------------+-------------+
| ID   | Ứng dụng       | Trạng thái | Môi trường  |
+------+----------------+------------+-------------+
| 1042 | api-gateway    | SUCCESS    | production  |
| 1041 | billing-worker | FAILED     | staging     |
| 1040 | customer-portal| SUCCESS    | production  |
+------+----------------+------------+-------------+
~~~

Ở 70 cột, bảng chỉ giữ ba cột quan trọng:

~~~text
+------+----------------+------------+
| ID   | Ứng dụng       | Trạng thái |
+------+----------------+------------+
| 1042 | api-gateway    | SUCCESS    |
| 1041 | billing-worker | FAILED     |
| 1040 | customer-portal| SUCCESS    |
+------+----------------+------------+
~~~

Ở 45 cột, chuyển sang một dòng cho mỗi bản phát hành:

~~~text
#1042 api-gateway [SUCCESS]
#1041 billing-worker [FAILED]
#1040 customer-portal [SUCCESS]
~~~

Các ví dụ trên minh họa layout mong muốn. Độ rộng thực tế từng cột còn phụ thuộc dữ liệu và quy tắc sizing/wrapping của Table.

## 13. Xử lý ô có nội dung dài

TableBuilder mặc định wrap text ở dấu cách. Ví dụ mô tả:

~~~text
This deployment includes the latest security patches
~~~

có thể được chia thành nhiều dòng trong cùng một ô khi cột hẹp.

Nhưng chuỗi không có dấu cách như commit hash, URL hoặc UUID không thể wrap theo ranh giới từ thông thường. Có ba cách xử lý:

- Rút gọn giá trị trong cột, ví dụ chỉ hiển thị 12 ký tự đầu của revision.
- Dùng cột riêng và cho phép người dùng xem chi tiết bằng command khác.
- Cấu hình TextWrapper riêng nếu nghiệp vụ cần chia một chuỗi dài thành nhiều đoạn.

Trong ví dụ, hàm clip rút gọn application, owner và revision trước khi đưa vào model. Hàm dùng code point để không cắt giữa một surrogate pair của Unicode.

Lưu ý: code point không đồng nghĩa với độ rộng hiển thị terminal. Ký tự CJK, emoji và combining mark có thể chiếm số cột khác nhau. Nếu ứng dụng phải tính chiều rộng thủ công cho nhiều ngôn ngữ, hãy dùng API đo cột hiển thị của JLine thay vì chỉ dùng String.length().

## 14. Chọn border phù hợp với terminal

Spring Shell cung cấp nhiều BorderStyle:

| BorderStyle | Đặc điểm |
|---|---|
| oldschool | Ký tự ASCII đơn giản, tương thích rộng |
| fancy_light | Ký tự box-drawing Unicode mảnh |
| fancy_heavy | Ký tự box-drawing Unicode đậm |
| fancy_double | Đường viền kép |
| air | Khoảng cách giữa cột, ít đường viền |

Trong ví dụ, dùng oldschool để output dễ đọc trong terminal cũ, log và môi trường không đảm bảo font Unicode.

Nếu sản phẩm yêu cầu giao diện đẹp hơn và môi trường triển khai hỗ trợ Unicode, có thể chuyển sang fancy_light. Hãy kiểm tra font, encoding và terminal emulator trên các hệ điều hành được hỗ trợ.

## 15. Chạy command trong CI hoặc không có TTY

Một CI runner có thể không cung cấp terminal tương tác. JLine Terminal vẫn có thể tồn tại nhưng chiều rộng trả về không phải lúc nào cũng có giá trị hữu ích.

Đó là lý do command có hai cơ chế:

- Đọc chiều rộng từ Terminal.getWidth() khi có kích thước hợp lệ.
- Cho phép truyền --width để ép chiều rộng khi chạy script hoặc test.

Ví dụ:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
java -jar deployment-cli.jar deployment list --width 100
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar deployment-cli.jar deployment list --width 100
~~~

Không nên giả định CI luôn có chiều rộng 80. Cũng không nên dùng bảng trình bày làm định dạng trao đổi dữ liệu giữa các job. Nếu bước tiếp theo cần đọc dữ liệu, hãy cung cấp JSON hoặc CSV riêng.

## 16. Giữ output bảng ổn định trong script

Bảng là output dành cho con người. Để script chạy ổn định:

- Chỉ dùng một width đã chọn trước.
- Dùng profile CI để tắt interactive mode.
- Không để prompt hoặc animation xen vào kết quả.
- Giữ border style và thứ tự cột nhất quán.
- Không dùng nội dung bảng làm input cho bước xử lý tiếp theo.
- Ghi log diagnostics ra stderr hoặc logging system phù hợp.

Ví dụ:

~~~bash
java -jar deployment-cli.jar deployment list --width 100 > deployment-list.txt
~~~

Nếu cần output có thể parse:

~~~text
deployment export --format json > deployment-list.json
~~~

Hãy tạo một command export chuyên biệt hoặc một output mode có schema được tài liệu hóa. Không yêu cầu consumer tách cột từ ASCII table.

## 17. Xử lý danh sách rỗng và dữ liệu lớn

Nếu không có bản ghi, trả về thông báo ngắn thay vì dựng một bảng không có hàng:

~~~text
Không có bản phát hành nào.
~~~

Nếu có hàng nghìn bản ghi, không nên đưa tất cả vào một bảng duy nhất. Cần thêm pagination hoặc giới hạn số kết quả:

~~~text
deployment list --page 1 --size 20
deployment list --page 2 --size 20
~~~

Bảng nên hiển thị thông tin phân trang:

~~~text
Trang 1/12 — 20 bản ghi trong tổng số 231
~~~

Có thể cung cấp command xem chi tiết một bản ghi:

~~~text
deployment show --id 1042
~~~

Cách này giữ bảng gọn và cho phép người dùng xem dữ liệu dài khi cần.

## 18. Kiểm thử renderer theo chiều rộng

Vì renderer nhận width như một tham số, có thể kiểm thử layout mà không cần terminal thật.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;

class DeploymentTableRendererTests {

    private final DeploymentTableRenderer renderer =
            new DeploymentTableRenderer();

    private final List<DeploymentRow> rows = List.of(
            new DeploymentRow(
                    1042, "api-gateway", "SUCCESS", "production",
                    "release-bot", "a13f9c2d"));

    @Test
    void showsAllColumnsOnWideTerminal() {
        String output = renderer.render(rows, 130);

        assertThat(output)
                .contains("Môi trường")
                .contains("Người triển khai")
                .contains("Revision");
    }

    @Test
    void hidesDetailsOnMediumTerminal() {
        String output = renderer.render(rows, 100);

        assertThat(output)
                .contains("Môi trường")
                .doesNotContain("Người triển khai")
                .doesNotContain("Revision");
    }

    @Test
    void keepsOnlyCoreColumnsOnNarrowTerminal() {
        String output = renderer.render(rows, 70);

        assertThat(output)
                .contains("ID")
                .contains("Ứng dụng")
                .contains("Trạng thái")
                .doesNotContain("Môi trường");
    }

    @Test
    void usesSingleLineLayoutOnVeryNarrowTerminal() {
        String output = renderer.render(rows, 45);

        assertThat(output)
                .contains("#1042")
                .contains("api-gateway")
                .contains("SUCCESS")
                .doesNotContain("Revision");
    }
}
~~~

Các test này xác nhận quyết định layout. Nếu thay đổi ngưỡng width, test sẽ báo khi một cột bị ẩn hoặc xuất hiện sai profile.

## 19. Kiểm thử command qua ShellTestClient

Unit test của renderer chưa xác nhận option được bind đúng hoặc command gọi đúng service. Có thể thêm shell integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@SpringBootTest(classes = DeploymentApplication.class)
class DeploymentCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void acceptsExplicitWidthOption() throws Exception {
        var screen = client.sendCommand("deployment list --width 70");

        ShellAssertions.assertThat(screen)
                .containsText("api-gateway")
                .containsText("SUCCESS");
    }
}
~~~

Test này chạy command qua Spring context và ShellTestClient. Vì width được truyền tường minh, kết quả không phụ thuộc kích thước terminal của máy chạy test.

Trong test suite thực tế, cấu hình DeploymentQuery bằng fixture hoặc test bean để output có thể lặp lại.

## 20. Kiểm thử terminal thật và nhiều hệ điều hành

Ngoài test tự động, cần smoke test trên các môi trường triển khai:

| Môi trường | Điều cần kiểm tra |
|---|---|
| Terminal Linux 120 cột | Hiển thị đầy đủ các cột |
| Terminal macOS 80 cột | Tự bỏ các cột phụ |
| Windows Terminal | Unicode và border không bị lỗi |
| Terminal trong IDE 60 cột | Bảng compact vẫn đọc được |
| SSH session hẹp | Không tràn ngang ngoài dự kiến |
| Docker/CI không TTY | Fallback width hoạt động |
| Script với --width | Output có layout lặp lại |

Thay đổi kích thước cửa sổ rồi chạy lại command để xác nhận renderer lấy width mới. Bảng đã in ra không tự vẽ lại khi người dùng thay đổi kích thước terminal; command cần được gọi lại.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không inject được Terminal | Thiếu spring-shell-jline hoặc JLine auto-configuration không hoạt động | Kiểm tra dependency và starter |
| Bảng luôn có cùng kích thước | Renderer dùng width cố định | Đọc Terminal.getWidth() hoặc nhận --width |
| Bảng tràn terminal | Quá nhiều cột hoặc chuỗi dài không có dấu cách | Chọn profile ít cột hơn và clip token dài |
| Header không khớp dữ liệu | Điều kiện thêm cột giữa header và row khác nhau | Dùng chung điều kiện includeEnvironment/includeDetails |
| Terminal trả width bằng 0 | Môi trường không có kích thước khả dụng | Dùng fallback và cho phép --width |
| Test chạy khác nhau giữa máy | Phụ thuộc width terminal thật | Truyền --width hoặc gọi renderer trực tiếp |
| Unicode border hiển thị sai | Font hoặc encoding không hỗ trợ box-drawing | Dùng BorderStyle.oldschool |
| Dữ liệu lớn làm output dài | Không có pagination hoặc limit | Thêm page/size và command show |
| Script không parse được output | ASCII table được dùng như dữ liệu máy đọc | Cung cấp JSON hoặc CSV riêng |

## 22. Bài tập thực hành tích hợp

Mở rộng command deployment list với các yêu cầu:

1. Thêm filter --environment để lọc theo môi trường.
2. Thêm --status để lọc theo trạng thái.
3. Thêm --page và --size để phân trang.
4. Giữ bốn profile hiển thị theo chiều rộng.
5. Ở terminal rộng, thêm cột thời điểm triển khai.
6. Ở terminal vừa, chỉ giữ ID, ứng dụng, trạng thái và môi trường.
7. Ở terminal hẹp, chuyển sang một dòng cho mỗi bản ghi.
8. Khi không có dữ liệu, hiển thị thông báo thay vì bảng rỗng.
9. Cho phép --width để test và chạy CI có kết quả ổn định.
10. Thêm command deployment show --id để xem đầy đủ chi tiết một bản ghi.
11. Thêm output JSON riêng cho pipeline.
12. Kiểm thử renderer ở các chiều rộng 45, 70, 100 và 130.

**Kết quả cần nộp:**

- DeploymentQuery và dữ liệu mẫu.
- DeploymentTableRenderer.
- DeploymentCommands với option width.
- Unit tests cho bốn profile.
- Shell test cho command.
- Bảng kết quả ở ít nhất ba kích thước terminal.
- Giải thích cách xử lý terminal không có TTY và output máy đọc.

## 23. Checklist trước khi hoàn thành

- [ ] Đã thêm spring-shell-jline nếu ứng dụng cần JLine table API.
- [ ] Đã dùng package org.springframework.shell.jline.tui.table của Spring Shell 4.
- [ ] Terminal được inject từ JLine auto-configuration.
- [ ] Chiều rộng terminal được kiểm tra trước khi render.
- [ ] Có fallback khi width không hợp lệ hoặc không khả dụng.
- [ ] Có option --width để ép kích thước trong test và CI.
- [ ] Header và row luôn có cùng số cột.
- [ ] Các profile rộng, vừa, hẹp và compact được kiểm thử.
- [ ] Nội dung dài được wrap hoặc rút gọn có chủ đích.
- [ ] Border style phù hợp với terminal mục tiêu.
- [ ] Danh sách rỗng có thông báo rõ ràng.
- [ ] Dữ liệu lớn có pagination hoặc giới hạn.
- [ ] Output máy đọc có JSON/CSV riêng.
- [ ] Test không phụ thuộc terminal thật của máy chạy.
- [ ] Đã smoke test trên Windows, Linux, macOS hoặc môi trường triển khai thực tế.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html)
- [Spring Shell 4.0.4 — TableBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html)
- [Spring Shell 4.0.4 — TableModelBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModelBuilder.html)
- [Spring Shell 4.0.4 — BorderStyle](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BorderStyle.html)
- [Spring Shell 4.0.4 — JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [Spring Shell 4.0.4 — Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [JLine — Terminal API](https://jline.github.io/javadoc/3.30/org/jline/terminal/Terminal.html)