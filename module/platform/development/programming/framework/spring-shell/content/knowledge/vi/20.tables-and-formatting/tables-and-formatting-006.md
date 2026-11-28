# TableBuilder và bộ kết xuất trong môđun bảng tương ứng phiên bản

Spring Shell cung cấp môđun bảng để trình bày danh sách dữ liệu theo hàng và cột trong terminal. Thay vì tự nối chuỗi và căn khoảng trắng, ứng dụng tạo một `TableModel`, cấu hình `TableBuilder`, rồi để `Table` tính chiều rộng, xuống dòng, căn lề và vẽ đường viền.

Bài học tập trung vào API bảng của Spring Shell 3.1.x, đồng thời chỉ rõ package và cách trả kết quả khác nhau ở Spring Shell 4.0.4. Đây là điểm cần kiểm tra trước khi sao chép import hoặc ví dụ từ một phiên bản khác: các lớp có tên gần như giống nhau nhưng package đã thay đổi, và `Table` không còn được xử lý như kết quả tự thích ứng chiều rộng terminal theo cùng cách ở 3.x.

## 1. Khi nào nên dùng TableBuilder?

Một command thường trả về danh sách đối tượng. Ví dụ, command liệt kê dự án có thể cần hiển thị mã, tên, trạng thái và số tác vụ:

~~~text
ID     Project          Status     Tasks
101    inventory-api    ACTIVE     12
102    billing-worker   PAUSED      4
103    catalog-web      ACTIVE      8
~~~

Nếu tự định dạng bằng `String.format()` hoặc nối dấu cách, ứng dụng phải tự xử lý:

- Độ dài khác nhau của từng giá trị.
- Cột có nội dung dài.
- Terminal có chiều rộng thay đổi.
- Nội dung chứa nhiều dòng.
- Căn trái, căn giữa hoặc căn phải.
- Đường viền giữa các ô.
- Giá trị `null` và cách hiển thị số, ngày tháng.

`TableBuilder` cung cấp các chiến lược để giải quyết những việc này. Ứng dụng tập trung vào dữ liệu và quy tắc hiển thị, còn bảng chịu trách nhiệm bố trí nội dung theo chiều rộng được cung cấp.

## 2. Mô hình dữ liệu và bộ dựng bảng

Trong Spring Shell 3.1.x, các API bảng thuộc package `org.springframework.shell.table`.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `TableModel` | Hợp đồng truy cập dữ liệu theo hàng và cột |
| `ArrayTableModel` | Mô hình dựa trên mảng hai chiều |
| `BeanListTableModel<T>` | Mô hình dựa trên danh sách Java bean |
| `TableModelBuilder<T>` | Tạo mô hình bảng theo từng hàng và giá trị |
| `TableBuilder` | Cấu hình đường viền và chiến lược hiển thị |
| `Table` | Kết quả bảng đã được cấu hình, có thể render |
| `CellMatcher` / `CellMatchers` | Chọn ô, hàng, cột hoặc kiểu dữ liệu để áp dụng cấu hình |
| `Formatter` | Chuyển giá trị thành một hoặc nhiều dòng văn bản |
| `SizeConstraints` | Quyết định chiều rộng tối thiểu và tối đa của ô |
| `TextWrapper` | Ngắt hoặc xử lý văn bản theo chiều rộng ô |
| `Aligner` | Căn lề nội dung theo chiều rộng và chiều cao ô |

Luồng tạo bảng:

~~~mermaid
flowchart TD
    A["Dữ liệu ứng dụng"] --> B["TableModel"]
    B --> C["TableBuilder"]
    C --> D["CellMatcher chọn vùng ô"]
    D --> E["Formatter"]
    E --> F["SizeConstraints"]
    F --> G["TextWrapper"]
    G --> H["Aligner"]
    H --> I["BorderStyle"]
    I --> J["Table"]
    J --> K["render(totalAvailableWidth)"]
    K --> L["Chuỗi bảng hiển thị"]
~~~

`TableBuilder` mặc định sử dụng `toString()` để định dạng giá trị, chiến lược kích thước cố gắng dùng không gian khả dụng, ngắt dòng theo dấu cách và căn trái. Có thể thay đổi từng chiến lược cho một nhóm ô cụ thể bằng `CellMatcher`.

## 3. Tạo TableModel bằng TableModelBuilder

`TableModelBuilder<T>` phù hợp khi dữ liệu đã được chuẩn bị thành các giá trị theo từng ô. Mỗi lần gọi `addRow()` bắt đầu một hàng mới; các lần gọi `addValue()` tiếp theo thêm giá trị vào hàng đó.

Ví dụ tạo bảng dự án:

~~~java
import org.springframework.shell.table.TableModel;
import org.springframework.shell.table.TableModelBuilder;

TableModel model = new TableModelBuilder<String>()
        .addRow()
            .addValue("ID")
            .addValue("Project")
            .addValue("Status")
            .addValue("Tasks")
        .addRow()
            .addValue("101")
            .addValue("inventory-api")
            .addValue("ACTIVE")
            .addValue("12")
        .addRow()
            .addValue("102")
            .addValue("billing-worker")
            .addValue("PAUSED")
            .addValue("4")
        .addRow()
            .addValue("103")
            .addValue("catalog-web")
            .addValue("ACTIVE")
            .addValue("8")
        .build();
~~~

Hàng đầu tiên là hàng tiêu đề. Khi sử dụng `addHeaderBorder()`, Spring Shell vẽ đường viền bao quanh bảng và phân cách hàng đầu tiên.

`TableModelBuilder` không tự hiểu tên thuộc tính của đối tượng. Ứng dụng cần quyết định thứ tự cột và chuyển mỗi giá trị sang kiểu phù hợp trước khi thêm vào mô hình.

### 3.1. Tạo mô hình từ mảng hai chiều

Nếu dữ liệu đã có sẵn trong mảng hai chiều, có thể dùng `ArrayTableModel`:

~~~java
import org.springframework.shell.table.ArrayTableModel;
import org.springframework.shell.table.TableModel;

Object[][] rows = {
        {"ID", "Project", "Status"},
        {"101", "inventory-api", "ACTIVE"},
        {"102", "billing-worker", "PAUSED"}
};

TableModel model = new ArrayTableModel(rows);
~~~

Mỗi phần tử mảng ngoài là một hàng; mỗi phần tử mảng trong là một ô. Các hàng nên có cùng số cột để tạo bảng dễ đọc và tránh dữ liệu thiếu cột.

`ArrayTableModel` thuận tiện cho dữ liệu nhỏ, cố định hoặc đã được chuyển đổi sẵn. Với dữ liệu được thu thập từng bước, `TableModelBuilder` thường dễ đọc hơn.

### 3.2. Tạo mô hình từ danh sách Java bean

Nếu dữ liệu là danh sách đối tượng có getter theo quy ước JavaBean, có thể dùng `BeanListTableModel`:

~~~java
import java.util.List;

import org.springframework.shell.table.BeanListTableModel;
import org.springframework.shell.table.TableModel;

public class ProjectRow {

    private final String id;
    private final String name;
    private final String status;

    public ProjectRow(String id, String name, String status) {
        this.id = id;
        this.name = name;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getStatus() {
        return status;
    }
}

List<ProjectRow> projects = List.of(
        new ProjectRow("101", "inventory-api", "ACTIVE"),
        new ProjectRow("102", "billing-worker", "PAUSED"));

TableModel model = new BeanListTableModel<>(
        projects, "id", "name", "status");
~~~

Danh sách tên thuộc tính xác định những cột được đưa vào bảng và thứ tự hiển thị. Cách này giảm mã ánh xạ khi dữ liệu đã là bean.

Một constructor khác nhận `LinkedHashMap<String, Object>` để khai báo hàng tiêu đề. Dùng `LinkedHashMap` khi cần giữ thứ tự tiêu đề và ánh xạ rõ ràng tên cột với giá trị tương ứng.

Không đưa toàn bộ thuộc tính của entity vào bảng theo mặc định nếu command chỉ cần một vài trường. Chọn rõ các cột sẽ giúp output ngắn, tránh vô tình hiển thị dữ liệu nội bộ và giảm chi phí định dạng.

## 4. Tạo bảng bằng TableBuilder

Sau khi có `TableModel`, tạo bảng bằng `TableBuilder`:

~~~java
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModel;

Table table = new TableBuilder(model)
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

`build()` trả về `Table`. Đường viền có thể được chọn tùy môi trường terminal:

| Phương thức | Kết quả |
|---|---|
| `addOutlineBorder(style)` | Vẽ viền ngoài của toàn bảng |
| `addHeaderBorder(style)` | Vẽ viền ngoài và phân cách hàng đầu |
| `addFullBorder(style)` | Vẽ viền quanh từng ô |
| `addHeaderAndVerticalsBorders(style)` | Vẽ viền ngoài, hàng đầu và đường dọc giữa cột |
| `addInnerBorder(style)` | Vẽ đường ngang và dọc bên trong, không vẽ viền ngoài |

Một số `BorderStyle` phổ biến:

- `oldschool`: dùng ký tự ASCII đơn giản như `|` và `-`, tương thích rộng.
- `fancy_light`: dùng ký tự khung Unicode nét mảnh.
- `fancy_double`: dùng ký tự khung Unicode nét đôi.
- `air`: dùng khoảng trắng để tạo khoảng cách giữa các cột.

Ví dụ dùng viền đầy đủ:

~~~java
Table table = new TableBuilder(model)
        .addFullBorder(BorderStyle.oldschool)
        .build();
~~~

Nếu terminal hoặc font không hỗ trợ tốt ký tự khung Unicode, `oldschool` là lựa chọn an toàn. Nếu cần output dễ đọc trong log hoặc pipeline, viền ASCII thường ít gây vấn đề mã hóa hơn.

## 5. Chọn ô cần tùy biến bằng CellMatchers

Không phải mọi ô đều cần cùng cách định dạng. Ví dụ, cột mã dự án có thể căn trái, cột số lượng căn phải, còn cột mô tả cần giới hạn chiều rộng.

`CellMatchers` cung cấp các factory method:

| Matcher | Phạm vi |
|---|---|
| `table()` | Tất cả ô trong bảng |
| `row(rowIndex)` | Tất cả ô trong một hàng |
| `column(columnIndex)` | Tất cả ô trong một cột |
| `at(rowIndex, columnIndex)` | Một ô cụ thể |
| `ofType(clazz)` | Các ô có giá trị thuộc kiểu được chỉ định |

Chỉ số hàng và cột dùng trong mô hình bắt đầu từ `0`. Nếu hàng đầu tiên là tiêu đề, hàng dữ liệu đầu tiên có chỉ số `1`.

Ví dụ căn phải cột số lượng:

~~~java
import org.springframework.shell.table.CellMatchers;
import org.springframework.shell.table.SimpleHorizontalAligner;

Table table = new TableBuilder(model)
        .addHeaderBorder(BorderStyle.oldschool)
        .on(CellMatchers.column(3))
            .addAligner(SimpleHorizontalAligner.right)
            .and()
        .build();
~~~

`on(matcher)` trả về `TableBuilder.CellMatcherStub`. Sau khi thêm một hoặc nhiều chiến lược, gọi `and()` để quay lại builder và tiếp tục cấu hình.

Có thể áp dụng cấu hình cho một ô cụ thể:

~~~java
Table table = new TableBuilder(model)
        .on(CellMatchers.at(1, 2))
            .addAligner(SimpleHorizontalAligner.center)
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Ví dụ này căn giữa ô ở hàng `1`, cột `2`. Hãy chọn matcher hẹp nhất đáp ứng yêu cầu để tránh làm thay đổi những cột không liên quan.

## 6. Bốn chiến lược định dạng nội dung

Bảng thực hiện nhiều bước để chuyển giá trị thô thành nội dung có thể hiển thị. Hiểu từng bước giúp lựa chọn đúng API.

| Chiến lược | Trách nhiệm | API |
|---|---|---|
| Formatter | Chuyển giá trị thành dòng văn bản | `Formatter` |
| Sizer | Xác định chiều rộng ô | `SizeConstraints` |
| Wrapper | Ngắt hoặc xử lý dòng theo chiều rộng | `TextWrapper` |
| Aligner | Căn nội dung trong vùng ô | `Aligner` |

### 6.1. Formatter

`Formatter.format(Object)` trả về `String[]`, tức một giá trị có thể được biểu diễn thành một hoặc nhiều dòng. Formatter chỉ tạo biểu diễn văn bản ban đầu; wrapper và aligner vẫn có thể thay đổi cách hiển thị sau đó.

Mặc định, `TableBuilder` dùng `toString()`. Có thể gắn formatter cho các ô theo kiểu dữ liệu:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

import org.springframework.shell.table.CellMatchers;
import org.springframework.shell.table.Formatter;

Formatter currencyFormatter = value -> new String[] {
        NumberFormat.getCurrencyInstance(Locale.US)
                .format((BigDecimal) value)
};

Table table = new TableBuilder(model)
        .on(CellMatchers.ofType(BigDecimal.class))
            .addFormatter(currencyFormatter)
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Ví dụ trên định dạng các ô chứa `BigDecimal` thành tiền tệ theo locale Hoa Kỳ. Trong ứng dụng thực tế, chọn locale theo yêu cầu sản phẩm và tránh định dạng số tiền bằng cách nối chuỗi thủ công.

`DefaultFormatter` là formatter mặc định, sử dụng `Object.toString()` và tách nội dung theo ký tự xuống dòng. `MapFormatter` chuyên xử lý cặp key-value, mỗi mapping được biểu diễn thành một dòng.

### 6.2. SizeConstraints

Sizer quyết định chiều rộng tối thiểu và tối đa của một ô trong tổng chiều rộng bảng.

Một số lựa chọn:

| Sizer | Hành vi |
|---|---|
| `AutoSizeConstraints` | Ước lượng chiều rộng tối thiểu và tối đa, có thể tách theo khoảng trắng |
| `AbsoluteWidthSizeConstraints(width)` | Ép chiều rộng cố định theo số ký tự |
| `NoWrapSizeConstraints` | Dùng chiều dài dòng lớn nhất, không cố thu hẹp để wrap |
| `KeyValueSizeConstraints` | Tính kích thước phù hợp cho hiển thị key-value |

Ví dụ giới hạn cột mô tả ở 24 ký tự:

~~~java
import org.springframework.shell.table.AbsoluteWidthSizeConstraints;
import org.springframework.shell.table.CellMatchers;

Table table = new TableBuilder(model)
        .on(CellMatchers.column(2))
            .addSizer(new AbsoluteWidthSizeConstraints(24))
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Chiều rộng cố định giúp bảng ổn định, nhưng nội dung dài sẽ cần wrapper để hiển thị. Nếu dùng `NoWrapSizeConstraints`, cột có thể rộng hơn terminal và làm output tràn ngang.

### 6.3. TextWrapper

Wrapper nhận nội dung đã được format và chiều rộng cột, sau đó trả về các dòng đã ngắt hoặc xử lý để vừa với ô.

`DelimiterTextWrapper` hỗ trợ ngắt dòng theo ranh giới từ. `KeyValueTextWrapper` phối hợp với các chiến lược key-value để căn dấu phân cách.

Ví dụ cấu hình wrapper theo cột:

~~~java
import org.springframework.shell.table.CellMatchers;
import org.springframework.shell.table.DelimiterTextWrapper;

Table table = new TableBuilder(model)
        .on(CellMatchers.column(2))
            .addWrapper(new DelimiterTextWrapper())
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Nên kiểm tra dữ liệu có chuỗi dài không chứa dấu cách, chẳng hạn URL hoặc mã định danh. Một wrapper ngắt theo từ có thể không chia được token dài theo cách mong muốn. Với những trường này, cân nhắc rút gọn nội dung hoặc cung cấp command xem chi tiết.

### 6.4. Aligner

Aligner căn văn bản trong ô sau khi kích thước và chiều cao đã được xác định.

`SimpleHorizontalAligner` hỗ trợ:

- `left`
- `center`
- `right`

`SimpleVerticalAligner` hỗ trợ căn trên, giữa hoặc dưới.

Ví dụ căn phải cột số và căn giữa tiêu đề:

~~~java
import org.springframework.shell.table.CellMatchers;
import org.springframework.shell.table.SimpleHorizontalAligner;

Table table = new TableBuilder(model)
        .on(CellMatchers.row(0))
            .addAligner(SimpleHorizontalAligner.center)
            .and()
        .on(CellMatchers.column(3))
            .addAligner(SimpleHorizontalAligner.right)
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Trong bảng có hàng tiêu đề và nhiều kiểu dữ liệu, thường nên căn trái văn bản, căn phải số và dùng căn giữa có chọn lọc. Cách này giúp mắt so sánh giá trị theo cột nhanh hơn.

## 7. Kết hợp nhiều chiến lược trên một vùng ô

Một `CellMatcherStub` có thể nhận nhiều chiến lược trước khi gọi `and()`:

~~~java
Table table = new TableBuilder(model)
        .on(CellMatchers.column(2))
            .addSizer(new AbsoluteWidthSizeConstraints(24))
            .addWrapper(new DelimiterTextWrapper())
            .addAligner(SimpleHorizontalAligner.left)
            .and()
        .on(CellMatchers.column(3))
            .addAligner(SimpleHorizontalAligner.right)
            .and()
        .addHeaderBorder(BorderStyle.oldschool)
        .build();
~~~

Cấu hình này giới hạn cột mô tả, wrap nội dung theo từ và căn trái; cột số lượng được căn phải.

Thứ tự tư duy khi thiết kế:

1. Chọn ô nào cần áp dụng cấu hình.
2. Xác định cách chuyển dữ liệu thành văn bản.
3. Chọn giới hạn chiều rộng.
4. Chọn cách wrap hoặc crop.
5. Chọn căn ngang và căn dọc.
6. Chọn đường viền tổng thể.

Một formatter tạo chuỗi quá dài có thể làm sizer phải cấp nhiều không gian. Một wrapper ngắt theo khoảng trắng có thể không phù hợp với dữ liệu dạng mã. Hãy phối hợp các chiến lược dựa trên loại nội dung thật.

## 8. Tùy biến đường viền

Ngoài các phương thức đường viền tổng thể, `TableBuilder` có `paintBorder(BorderStyle, int)` để áp dụng border theo một `BorderSpecification`.

`BorderSpecification` định nghĩa các phần có thể vẽ:

- `TOP`, `BOTTOM`
- `LEFT`, `RIGHT`
- `INNER_VERTICAL`, `INNER_HORIZONTAL`
- `OUTLINE`, `INNER`, `FULL`, `NONE`

Ví dụ các phương thức tổng thể dễ đọc và thường đủ cho CLI:

~~~java
Table headerOnly = new TableBuilder(model)
        .addHeaderBorder(BorderStyle.oldschool)
        .build();

Table fullGrid = new TableBuilder(model)
        .addFullBorder(BorderStyle.oldschool)
        .build();

Table verticalColumns = new TableBuilder(model)
        .addHeaderAndVerticalsBorders(BorderStyle.oldschool)
        .build();
~~~

Không cần vẽ đường viền quanh từng ô nếu bảng chỉ có vài cột và người dùng cần đọc nhanh. `addHeaderBorder()` thường tạo phân cấp thị giác đủ rõ mà không làm output quá dày.

## 9. Cấu hình hiển thị Map dạng key-value

Khi dữ liệu là một `Map`, đôi khi không cần bảng nhiều cột mà cần danh sách key-value được căn theo dấu phân cách.

`Tables.configureKeyValueRendering(builder, delimiter)` cài đặt formatter, sizer, wrapper và aligner phù hợp cho kiểu dữ liệu này.

Ví dụ:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModelBuilder;
import org.springframework.shell.table.Tables;

Map<String, Object> values = new LinkedHashMap<>();
values.put("Project", "inventory-api");
values.put("Environment", "staging");
values.put("Replicas", 3);

TableModelBuilder<Object> modelBuilder = new TableModelBuilder<>();
modelBuilder.addRow().addValue(values);

TableBuilder builder = new TableBuilder(modelBuilder.build());
Table table = Tables.configureKeyValueRendering(builder, " = ")
        .build();
~~~

Helper này phù hợp khi một ô chứa map và muốn trình bày các cặp key-value thành nhiều dòng. Với danh sách bản ghi có cùng schema, hãy dùng bảng nhiều cột thay vì ép dữ liệu thành map.

## 10. Render bảng theo chiều rộng terminal trong Spring Shell 3.x

Trong Spring Shell 3.1.x, `Table` triển khai `TerminalSizeAware`. Interface này cho phép kết quả command tự render theo chiều rộng terminal mà Spring Shell cung cấp.

`TerminalSizeAwareResultHandler` là result handler dành cho kiểu kết quả này. Nó lấy kích thước terminal và gọi `render(terminalWidth)` để in kết quả.

Vì vậy, command annotation có thể trả trực tiếp `Table`:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModel;

@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod("List projects.")
    public Table listProjects() {
        TableModel model = projectService.toTableModel();

        return new TableBuilder(model)
                .addHeaderBorder(BorderStyle.oldschool)
                .build();
    }
}
~~~

Khi Spring Shell xử lý kết quả, `TerminalSizeAwareResultHandler` render bảng theo kích thước terminal hiện tại. Không cần gọi `toString()` hoặc tự in từng dòng trong command method.

### 10.1. Render thủ công để kiểm thử

Có thể gọi `render(width)` trực tiếp nếu muốn kiểm tra output hoặc cần dùng bảng bên ngoài shell:

~~~java
Table table = new TableBuilder(model)
        .addHeaderBorder(BorderStyle.oldschool)
        .build();

String rendered = table.render(80);
System.out.println(rendered);
~~~

Chiều rộng `80` là số cột ký tự dành cho bảng. Trong kiểm thử, dùng chiều rộng cố định giúp kết quả lặp lại giữa các máy.

## 11. Khác biệt API bảng giữa Spring Shell 3.x và 4.x

Đây là điểm quan trọng nhất khi dùng tài liệu hoặc ví dụ theo phiên bản.

| Thành phần | Spring Shell 3.1.x–3.3.x | Spring Shell 4.0.4 |
|---|---|---|
| Package của bảng | `org.springframework.shell.table` | `org.springframework.shell.jline.tui.table` |
| `TableBuilder` | `org.springframework.shell.table.TableBuilder` | `org.springframework.shell.jline.tui.table.TableBuilder` |
| `TableModel` | `org.springframework.shell.table.TableModel` | `org.springframework.shell.jline.tui.table.TableModel` |
| `CellMatchers` | `org.springframework.shell.table.CellMatchers` | `org.springframework.shell.jline.tui.table.CellMatchers` |
| `BorderStyle` | `org.springframework.shell.table.BorderStyle` | `org.springframework.shell.jline.tui.table.BorderStyle` |
| Kết quả `Table` | Triển khai `TerminalSizeAware` | Có phương thức `render(int)` trả về `String`; không triển khai `TerminalSizeAware` |
| Cách trả kết quả từ command | Có thể trả `Table` để shell tự render theo terminal | Thường gọi `table.render(width)` và trả chuỗi |

Các chiến lược bảng vẫn có tên và mục đích tương tự, nhưng import phải khớp package của dependency đang dùng.

### 11.1. Import trong Spring Shell 3.1.x

~~~java
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModel;
import org.springframework.shell.table.TableModelBuilder;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.CellMatchers;
~~~

### 11.2. Import trong Spring Shell 4.0.4

~~~java
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;
import org.springframework.shell.jline.tui.table.TableModelBuilder;
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.CellMatchers;
~~~

Không giữ import `org.springframework.shell.table.*` khi chuyển sang Spring Shell 4.0.4. IDE có thể tự động import một package cùng tên từ dependency khác; hãy kiểm tra fully qualified class name trong file.

### 11.3. Trả kết quả trong Spring Shell 4.0.4

Trong Spring Shell 4.0.4, `Table.render(int totalAvailableWidth)` trả về chuỗi đã định dạng. `Table` trong package mới không còn triển khai `TerminalSizeAware` như `Table` của 3.1.x.

Ví dụ:

~~~java
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;

public String listProjects() {
    TableModel model = projectService.toTableModel();

    Table table = new TableBuilder(model)
            .addHeaderBorder(BorderStyle.oldschool)
            .build();

    int terminalWidth = 100;
    return table.render(terminalWidth);
}
~~~

Trong ví dụ này, chiều rộng được truyền rõ ràng. Nếu ứng dụng cần thích ứng theo terminal hiện tại, lấy chiều rộng từ terminal API mà ứng dụng đang sử dụng và cung cấp giá trị dự phòng khi không có terminal tương tác. Không giả định `Table` 4.x sẽ tự được result handler render theo chiều rộng như 3.x.

Khi port code, giữ nguyên logic tạo model và cấu hình builder nếu API vẫn tương ứng; thay package import và điều chỉnh điểm trả kết quả theo hợp đồng của phiên bản mới.

## 12. Chọn chiều rộng và xử lý nội dung dài

Một bảng đẹp trên terminal 120 cột có thể khó đọc trên terminal 60 cột. Khi thiết kế:

- Giới hạn các cột mô tả dài.
- Căn phải cột số.
- Không hiển thị quá nhiều cột trong một command.
- Rút gọn mã định danh dài nếu có command xem chi tiết.
- Tránh dùng `NoWrapSizeConstraints` cho dữ liệu văn bản không giới hạn.
- Chọn `oldschool` nếu môi trường terminal không bảo đảm Unicode box drawing.

`AutoSizeConstraints` có thể ngắt theo dấu cách để tìm kích thước phù hợp. `AbsoluteWidthSizeConstraints` giúp cột có độ rộng ổn định. `NoWrapSizeConstraints` giữ nguyên dòng dài và có thể khiến bảng vượt quá chiều rộng terminal.

Nếu nội dung có URL, UUID hoặc chuỗi không có dấu cách, wrapper theo ranh giới từ có thể không chia dòng theo mong muốn. Hãy xử lý riêng trường dữ liệu đó, thay vì tăng toàn bộ chiều rộng bảng.

## 13. Bảng rỗng, giá trị null và dữ liệu lớn

Một số trường hợp cần được xử lý trước khi dựng bảng:

### 13.1. Danh sách rỗng

Nếu không có bản ghi, có thể trả thông báo rõ ràng thay vì tạo bảng không có hàng dữ liệu. Nếu muốn command luôn trả về `Table` trong 3.x, hãy dựng một hàng thông báo:

~~~java
if (projects.isEmpty()) {
    TableModel emptyModel = new TableModelBuilder<String>()
            .addRow()
                .addValue("Message")
            .addRow()
                .addValue("No projects found")
            .build();

    return new TableBuilder(emptyModel)
            .addHeaderBorder(BorderStyle.oldschool)
            .build();
}
~~~

Bảng rỗng là quyết định giao diện; không nhất thiết phải dựng một model không có hàng.

### 13.2. Giá trị null

`TableModel.getValue(row, column)` có thể trả về `null`. Cần quyết định cách hiển thị:

- Dùng dấu `-` cho giá trị không có.
- Dùng `N/A` nếu dữ liệu chưa được áp dụng.
- Dùng chuỗi rỗng nếu cột đã có tiêu đề và giá trị không quan trọng.

Có thể xử lý null trong dữ liệu view model trước khi đưa vào bảng hoặc dùng formatter riêng. Tránh để chuỗi `null` xuất hiện trong output nếu nó không có ý nghĩa với người dùng.

### 13.3. Dữ liệu lớn

Không nên dựng một bảng chứa hàng chục nghìn bản ghi chỉ để hiển thị trên terminal. Hãy cung cấp:

- Option lọc hoặc tìm kiếm.
- Phân trang bằng `--page` và `--size`.
- Giới hạn số dòng mặc định.
- Command xem chi tiết theo ID.
- Export CSV/JSON cho dữ liệu cần xử lý tự động.

`TableModel` truy cập dữ liệu theo chỉ số hàng và cột; nó không tự thay thế phân trang ở tầng repository. Hãy lấy đúng tập dữ liệu cần hiển thị trước khi xây dựng model.

## 14. Kiểm thử bảng

Nên kiểm thử model, cấu hình builder và kết quả render.

### 14.1. Kiểm thử render trực tiếp

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModelBuilder;

class ProjectTableTests {

    @Test
    void rendersHeaderAndRows() {
        var model = new TableModelBuilder<String>()
                .addRow()
                    .addValue("ID")
                    .addValue("Project")
                .addRow()
                    .addValue("101")
                    .addValue("inventory-api")
                .build();

        Table table = new TableBuilder(model)
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        String rendered = table.render(80);

        assertThat(rendered)
                .contains("ID")
                .contains("Project")
                .contains("inventory-api");
    }
}
~~~

Kiểm thử này gọi `render(80)` trực tiếp nên không phụ thuộc terminal đang chạy rộng bao nhiêu cột.

### 14.2. Kiểm thử căn lề và wrap

Nên thêm các trường hợp:

- Số lượng được căn phải.
- Tiêu đề được hiển thị đúng.
- Nội dung dài được wrap trong giới hạn đã đặt.
- Giá trị `null` được thay bằng ký hiệu đã chọn.
- Chuỗi Unicode và tiếng Việt hiển thị đúng trên terminal mục tiêu.
- Bảng không vượt chiều rộng dự kiến khi dữ liệu có token dài.

Không nên kiểm tra toàn bộ chuỗi có đường viền nếu mục tiêu test chỉ là dữ liệu. Border glyph có thể khác giữa `oldschool` và `fancy_light`. Hãy kiểm tra nội dung và các đặc tính bố cục quan trọng.

### 14.3. Kiểm thử tích hợp command

Ngoài unit test cho `Table`, cần kiểm tra command trả kết quả đúng:

- Spring Shell 3.x: command trả `Table`; result handler nhận `TerminalSizeAware`.
- Spring Shell 4.0.4: command trả chuỗi được tạo từ `table.render(width)`.
- Kiểm tra command với danh sách rỗng.
- Kiểm tra dữ liệu thực tế có cột dài và giá trị null.
- Kiểm tra output trong interactive terminal và non-interactive runner nếu cả hai đều được hỗ trợ.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biên dịch được `TableBuilder` | Import package của phiên bản khác | Dùng `org.springframework.shell.table` trong 3.x hoặc `org.springframework.shell.jline.tui.table` trong 4.0.4 |
| Command in ra tên class `Table` | Kết quả không được xử lý theo `TerminalSizeAware` | Kiểm tra phiên bản và kiểu trả về; 4.0.4 gọi `render(width)` |
| Cột số bị lệch | Mặc định mọi ô căn trái | Dùng `CellMatchers.column()` và `SimpleHorizontalAligner.right` |
| Bảng vượt chiều rộng terminal | Cột không giới hạn hoặc dùng `NoWrapSizeConstraints` | Dùng `AutoSizeConstraints`, fixed width và wrapper |
| Nội dung dài bị cắt hoặc khó đọc | Wrapper không phù hợp với kiểu dữ liệu | Chọn wrapper khác hoặc rút gọn dữ liệu |
| Hàng tiêu đề không phân biệt | Model không có hàng đầu tiên làm header hoặc chưa dùng header border | Thêm hàng tiêu đề và `addHeaderBorder()` |
| Một cấu hình ảnh hưởng cả bảng | Dùng `CellMatchers.table()` | Chọn `column`, `row`, `at` hoặc `ofType` |
| Thứ tự cột không đúng | Danh sách property không được khai báo rõ | Chỉ định `propertyNames` hoặc xây model theo thứ tự |
| Ký tự viền hiển thị lỗi | Terminal/font không hỗ trợ Unicode box drawing | Chọn `BorderStyle.oldschool` |
| Output quá lớn | Đưa toàn bộ kết quả truy vấn vào bảng | Phân trang hoặc giới hạn dữ liệu |
| Map hiển thị không căn | Chưa dùng formatter/sizer cho key-value | Dùng `Tables.configureKeyValueRendering()` |

## 16. Bài thực hành: bảng danh sách dự án

Tạo command `project list` hiển thị các dự án dưới dạng bảng.

Yêu cầu:

1. Tạo model với các cột `ID`, `Project`, `Status`, `Tasks`.
2. Dùng `TableModelBuilder` hoặc `BeanListTableModel`.
3. Dùng `TableBuilder` với `addHeaderBorder(BorderStyle.oldschool)`.
4. Căn phải cột `Tasks`.
5. Giới hạn chiều rộng cột `Project`.
6. Wrap nội dung dài theo ranh giới từ.
7. Xử lý danh sách rỗng bằng thông báo phù hợp.
8. Kiểm thử `table.render(80)`.
9. Tạo phiên bản 3.1.x trả `Table` trực tiếp.
10. Tạo phiên bản 4.0.4 dùng package mới và trả `table.render(width)`.

Kết quả mong đợi:

~~~text
+------+------------------+----------+-------+
| ID   | Project          | Status   | Tasks |
+------+------------------+----------+-------+
| 101  | inventory-api    | ACTIVE   |    12 |
| 102  | billing-worker   | PAUSED   |     4 |
| 103  | catalog-web      | ACTIVE   |     8 |
+------+------------------+----------+-------+
~~~

Có thể thay `oldschool` bằng `fancy_light` để so sánh giao diện trên terminal hỗ trợ Unicode.

## 17. Checklist triển khai

- [ ] Xác định chính xác phiên bản Spring Shell.
- [ ] Dùng đúng package của `TableBuilder`, `TableModel` và `Table`.
- [ ] Chọn mô hình dữ liệu phù hợp: `ArrayTableModel`, `TableModelBuilder` hoặc `BeanListTableModel`.
- [ ] Đặt hàng tiêu đề rõ ràng.
- [ ] Chọn `CellMatcher` đủ hẹp cho từng tùy biến.
- [ ] Định dạng số, ngày tháng và null theo quy tắc nhất quán.
- [ ] Chọn sizer và wrapper cho cột có nội dung dài.
- [ ] Căn phải số và căn trái văn bản.
- [ ] Chọn border tương thích terminal.
- [ ] Giới hạn số bản ghi hiển thị.
- [ ] Kiểm tra bảng ở chiều rộng terminal hẹp.
- [ ] Spring Shell 3.x: tận dụng `TerminalSizeAware` khi trả `Table`.
- [ ] Spring Shell 4.0.4: gọi `render(width)` và trả chuỗi.
- [ ] Có unit test cho render và integration test cho command.

## 18. Kết luận

`TableModel` mô tả dữ liệu theo hàng và cột; `TableBuilder` kết hợp formatter, sizing, wrapper, aligner và border để tạo `Table`. `CellMatchers` giúp áp dụng cấu hình đúng vùng ô, còn `Table.render(width)` cho phép kiểm thử hoặc render với chiều rộng xác định.

Trong Spring Shell 3.1.x, các lớp bảng thuộc `org.springframework.shell.table`; `Table` triển khai `TerminalSizeAware`, nên command có thể trả bảng để result handler render theo terminal. Trong Spring Shell 4.0.4, các lớp bảng chuyển sang `org.springframework.shell.jline.tui.table`; `Table.render(width)` trả chuỗi, vì vậy command cần gọi render với chiều rộng phù hợp.

Hãy kiểm tra package và hợp đồng kết quả theo đúng phiên bản dependency. Khi dữ liệu được chọn rõ ràng, cột có chiều rộng hợp lý và output được kiểm thử ở terminal thực tế, bảng sẽ giúp command dễ đọc mà vẫn hoạt động ổn định trong các môi trường CLI khác nhau.

## Tài liệu tham khảo

- [Spring Shell 3.1 API: `TableBuilder`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableBuilder.html)
- [Spring Shell 3.1 API: `Table`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/Table.html)
- [Spring Shell 3.1 API: `TableModel`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableModel.html)
- [Spring Shell 3.1 API: `TableModelBuilder`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableModelBuilder.html)
- [Spring Shell 3.1 API: `BeanListTableModel`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/BeanListTableModel.html)
- [Spring Shell 3.1 API: `CellMatchers`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/CellMatchers.html)
- [Spring Shell 3.1 API: `TableBuilder.CellMatcherStub`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableBuilder.CellMatcherStub.html)
- [Spring Shell 3.1 API: `Formatter`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/Formatter.html)
- [Spring Shell 3.1 API: `SizeConstraints`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/SizeConstraints.html)
- [Spring Shell 3.1 API: `TextWrapper`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TextWrapper.html)
- [Spring Shell 3.1 API: `BorderStyle`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/BorderStyle.html)
- [Spring Shell 3.1 API: `AbsoluteWidthSizeConstraints`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/AbsoluteWidthSizeConstraints.html)
- [Spring Shell 3.1 API: `DelimiterTextWrapper`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/DelimiterTextWrapper.html)
- [Spring Shell 3.1 API: `SimpleHorizontalAligner`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/SimpleHorizontalAligner.html)
- [Spring Shell 3.1 API: `Tables`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/Tables.html)
- [Spring Shell 3.1 API: `TerminalSizeAware`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/TerminalSizeAware.html)
- [Spring Shell 3.1 API: `TerminalSizeAwareResultHandler`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/result/TerminalSizeAwareResultHandler.html)
- [Spring Shell 4.0.4 API: `TableBuilder`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html)
- [Spring Shell 4.0.4 API: `Table`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html)
- [Spring Shell 4.0.4 API: `TableBuilder.CellMatcherStub`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.CellMatcherStub.html)
- [Spring Shell 4.0.4 API: `BeanListTableModel`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BeanListTableModel.html)
- [Spring Shell 4.0.4 API: `TableModelBuilder`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModelBuilder.html)
- [Spring Shell 4.0.4 API: `CellMatchers`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/CellMatchers.html)
- [Spring Shell 4.0.4 API: `BorderStyle`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BorderStyle.html)
- [Spring Shell 4.0.4 API: `SimpleHorizontalAligner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/SimpleHorizontalAligner.html)
- [Spring Shell 4.0.4 API: `Tables`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Tables.html)

