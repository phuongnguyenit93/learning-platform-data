# Thay đổi package bảng khi tích hợp vào JLine ở 4.x

Khi nâng Spring Shell từ 3.x lên 4.x, các lớp tạo bảng vẫn giữ vai trò quen thuộc nhưng package và module chứa chúng đã thay đổi. Các API từng nằm trong **org.springframework.shell.table** của module **spring-shell-table** được chuyển sang **org.springframework.shell.jline.tui.table** trong module **spring-shell-jline**.

Thay đổi này gắn với việc Spring Shell 4 tách JLine khỏi module core. **spring-shell-core** không còn phụ thuộc JLine; ứng dụng muốn dùng JLine console phải khai báo module JLine. Vì thư viện bảng được tích hợp vào module này, ứng dụng dùng Table API cũng cần dependency phù hợp.

Bài này tập trung vào việc di chuyển import, cập nhật dependency và tiếp tục tạo bảng bằng **TableModel**, **TableModelBuilder**, **TableBuilder** và **Table** trong Spring Shell 4.x.

## 1. Điều gì thay đổi trong Spring Shell 4?

Trong Spring Shell 3.x, API bảng được đóng gói riêng:

~~~text
Module: spring-shell-table
Package: org.springframework.shell.table
~~~

Từ Spring Shell 4, module bảng được gộp vào module tích hợp JLine:

~~~text
Module: spring-shell-jline
Package: org.springframework.shell.jline.tui.table
~~~

Đây là thay đổi về vị trí module và namespace Java. Các lớp chính như **Table**, **TableBuilder**, **TableModel**, **TableModelBuilder**, **BorderStyle** và **Tables** vẫn là các thành phần của Spring Shell, nhưng được import từ package mới.

| Thành phần | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Artifact chứa API bảng | spring-shell-table | spring-shell-jline |
| Package API bảng | org.springframework.shell.table | org.springframework.shell.jline.tui.table |
| Package của Table | org.springframework.shell.table.Table | org.springframework.shell.jline.tui.table.Table |
| Package của TableBuilder | org.springframework.shell.table.TableBuilder | org.springframework.shell.jline.tui.table.TableBuilder |
| Package của TableModel | org.springframework.shell.table.TableModel | org.springframework.shell.jline.tui.table.TableModel |
| Package của TableModelBuilder | org.springframework.shell.table.TableModelBuilder | org.springframework.shell.jline.tui.table.TableModelBuilder |
| Package của BorderStyle | org.springframework.shell.table.BorderStyle | org.springframework.shell.jline.tui.table.BorderStyle |

Spring Shell 4 cũng tách JLine khỏi core. Core có thể chạy bằng **SystemShellRunner** và Java Console mà không cần JLine. Nếu cần JLine console hoặc Table API của Spring Shell, hãy thêm **spring-shell-jline**.

## 2. Cập nhật dependency

### 2.1. Gradle

Trong dự án Spring Shell 3.x, dependency bảng thường được khai báo riêng:

~~~gradle
dependencies {
    implementation("org.springframework.shell:spring-shell-table")
}
~~~

Khi chuyển sang Spring Shell 4.x, bỏ dependency module cũ và khai báo module JLine:

~~~gradle
dependencies {
    implementation("org.springframework.shell:spring-shell-jline")
}
~~~

### 2.2. Maven

Với Maven, dependency ở Spring Shell 4.x có dạng:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
~~~

Hãy dùng Spring Shell BOM hoặc dependency management của Spring Boot để quản lý phiên bản đồng bộ. Không tự chọn một phiên bản JLine riêng nếu Spring Shell đã quản lý phiên bản tương thích.

Spring Shell 4 dựa trên Spring Framework 7 và hỗ trợ Spring Boot 4 trở lên. Nếu ứng dụng còn ở Spring Boot 3, cần lập kế hoạch nâng nền tảng trước khi chuyển toàn bộ sang Spring Shell 4.

### 2.3. Core không tự kéo JLine vào nữa

Trong Spring Shell 3, ứng dụng có thể vô tình nhận được JLine thông qua dependency bắc cầu. Sang 4.x, không nên dựa vào điều đó:

- **spring-shell-core** cung cấp command model và shell core, không phụ thuộc JLine.
- **spring-shell-jline** cung cấp tích hợp JLine và các API bảng của Spring Shell.
- Module **spring-shell-table** riêng không còn là nơi khai báo API bảng trong kiến trúc 4.x.

Nếu ứng dụng chỉ dùng console chuẩn của JDK và không cần Table API của Spring Shell, có thể không thêm module JLine. Nếu cần bảng từ package mới, phải có **spring-shell-jline** trên classpath.

## 3. Chuyển import từ 3.x sang 4.x

Với các lớp bảng, quy tắc di chuyển chính là đổi package gốc:

~~~java
// Spring Shell 3.x
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModel;
import org.springframework.shell.table.TableModelBuilder;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.BorderSpecification;
import org.springframework.shell.table.CellMatcher;
import org.springframework.shell.table.Formatter;
import org.springframework.shell.table.Aligner;
import org.springframework.shell.table.SizeConstraints;
import org.springframework.shell.table.TextWrapper;
import org.springframework.shell.table.Tables;
~~~

~~~java
// Spring Shell 4.x
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;
import org.springframework.shell.jline.tui.table.TableModelBuilder;
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.BorderSpecification;
import org.springframework.shell.jline.tui.table.CellMatcher;
import org.springframework.shell.jline.tui.table.Formatter;
import org.springframework.shell.jline.tui.table.Aligner;
import org.springframework.shell.jline.tui.table.SizeConstraints;
import org.springframework.shell.jline.tui.table.TextWrapper;
import org.springframework.shell.jline.tui.table.Tables;
~~~

Các lớp khác trong package bảng cũng theo quy tắc tương tự, gồm **ArrayTableModel**, **BeanListTableModel**, **CellMatchers**, **AbsoluteWidthSizeConstraints**, **AutoSizeConstraints**, **NoWrapSizeConstraints**, **MapFormatter**, **SimpleHorizontalAligner** và **SimpleVerticalAligner**.

Không đổi package của các lớp này sang **org.jline**. Package mới vẫn thuộc Spring Shell; phần **jline.tui** cho biết API bảng nằm trong module tích hợp JLine.

## 4. Tạo bảng bằng TableModelBuilder và TableBuilder

Mô hình bảng tách dữ liệu khỏi cách trình bày:

- **TableModel** cung cấp số hàng, số cột và giá trị tại từng ô.
- **TableModelBuilder** giúp tạo TableModel theo từng hàng và từng giá trị.
- **TableBuilder** cấu hình viền, formatter, kích thước, wrapping và alignment.
- **Table** giữ model cùng các chiến lược trình bày và tạo chuỗi kết quả bằng render.

Ví dụ sau dùng package mới của Spring Shell 4:

~~~java
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;
import org.springframework.shell.jline.tui.table.TableModelBuilder;
import org.springframework.stereotype.Component;

@Component
public class ProjectTableFactory {

    public String renderProjects() {
        TableModel model = new TableModelBuilder<String>()
                .addRow()
                    .addValue("ID")
                    .addValue("Tên dự án")
                    .addValue("Trạng thái")
                .addRow()
                    .addValue("42")
                    .addValue("Learning Platform")
                    .addValue("Đang chạy")
                .addRow()
                    .addValue("57")
                    .addValue("CLI Toolkit")
                    .addValue("Đang kiểm thử")
                .build();

        Table table = new TableBuilder(model)
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        return table.render(100);
    }
}
~~~

**TableModelBuilder** tạo một hàng mới bằng **addRow()**; các lời gọi **addValue()** tiếp theo điền giá trị cho hàng đó. **build()** trả về TableModel. Sau đó, **TableBuilder** nhận model, thêm viền cho header và tạo Table.

Phương thức **render(100)** nhận tổng chiều rộng khả dụng tính theo cột ký tự. Giá trị này cần được chọn theo terminal hoặc bố cục mà ứng dụng muốn hỗ trợ. Không giả định bảng tự biết chiều rộng cửa sổ nếu ứng dụng không truyền thông tin đó.

## 5. Dùng bảng trong command Spring Shell 4

Một command có thể trả về chuỗi bảng đã render:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class ProjectCommands {

    private final ProjectTableFactory tableFactory;

    ProjectCommands(ProjectTableFactory tableFactory) {
        this.tableFactory = tableFactory;
    }

    @Command(
            name = "project-list",
            description = "Hiển thị danh sách dự án."
    )
    public String list() {
        return tableFactory.renderProjects();
    }
}
~~~

Command chỉ chịu trách nhiệm gọi thành phần tạo bảng và trả nội dung đã render. Có thể tách việc lấy dữ liệu vào application service rồi truyền danh sách kết quả vào factory để dễ kiểm thử.

Nếu command cần ghi nhiều phần output theo thời gian, có thể dùng **CommandContext.outputWriter()**. Với kết quả bảng đơn lẻ, trả về String thường gọn hơn và tránh việc vừa ghi writer vừa trả về cùng nội dung.

## 6. Các chiến lược định dạng vẫn có trong package mới

API bảng hỗ trợ nhiều bước xử lý để chuyển dữ liệu thành các dòng hiển thị:

| Thành phần | Vai trò |
|---|---|
| **Formatter** | Chuyển giá trị thô thành nội dung văn bản của ô |
| **SizeConstraints** | Xác định độ rộng tối thiểu và tối đa của ô |
| **TextWrapper** | Chia hoặc cắt nội dung khi ô bị giới hạn chiều rộng |
| **Aligner** | Căn trái, giữa, phải hoặc căn dọc nội dung |
| **CellMatcher** | Chọn các ô hoặc cột áp dụng chiến lược |
| **BorderStyle** | Chọn kiểu ký tự dùng để vẽ viền |
| **BorderSpecification** | Xác định các cạnh viền được áp dụng cho ô |

Khi tạo **TableBuilder** chỉ với model, chiến lược mặc định sẽ:

- Dùng **toString()** để định dạng giá trị.
- Cố gắng sử dụng phần không gian tối đa cho các ô.
- Tách dòng tại khoảng trắng khi cần xác định kích thước.
- Wrap văn bản theo dấu cách.
- Căn trái nội dung.

Đây là mặc định hữu ích cho bảng đơn giản. Với dữ liệu phức tạp, hãy chỉ định formatter, size constraint, wrapper hoặc aligner riêng cho những ô cần cách hiển thị khác.

## 7. Chọn kiểu viền phù hợp với terminal

**BorderStyle** cung cấp các kiểu viền có sẵn:

| Kiểu | Đặc điểm | Khi nên dùng |
|---|---|---|
| **oldschool** | Dùng ký tự ASCII phổ biến như pipe và dấu gạch ngang | Terminal hạn chế font hoặc môi trường không chắc hỗ trợ box drawing |
| **fancy_light** | Dùng ký tự box drawing nét mảnh | Giao diện terminal hiện đại |
| **fancy_heavy** | Dùng ký tự box drawing nét đậm | Muốn nhấn mạnh đường viền |
| **fancy_double** | Dùng đường viền đôi | Bảng cần phân tách trực quan rõ |
| **air** | Dùng khoảng trắng để tách cột | Bảng gọn, ít đường kẻ |

Ví dụ:

~~~java
Table table = new TableBuilder(model)
        .addHeaderBorder(BorderStyle.fancy_light)
        .build();
~~~

Kiểu fancy dùng ký tự Unicode box drawing. Hãy kiểm tra font, encoding và terminal emulator mục tiêu. Nếu môi trường chạy không hiển thị được các glyph đó, dùng **oldschool** để giữ khả năng đọc.

## 8. Giới hạn chiều rộng và wrapping

Table API render bảng với chiều rộng được truyền vào:

~~~java
String output = table.render(80);
~~~

Chiều rộng cần tính đến cả nội dung, khoảng đệm và ký tự viền. Nếu đặt quá nhỏ, nội dung có thể bị wrap thành nhiều dòng; nếu quá lớn, bảng có thể tràn khỏi terminal.

Một số lưu ý:

- **AutoSizeConstraints** cố gắng tìm khoảng rộng phù hợp và có thể tách dòng theo khoảng trắng.
- **NoWrapSizeConstraints** giữ nguyên dòng dài nhất, có thể làm bảng rộng hơn terminal.
- **AbsoluteWidthSizeConstraints** đặt chiều rộng cố định cho ô.
- **TextWrapper** quyết định nội dung được wrap hoặc crop như thế nào.
- Nội dung không có dấu cách, như URL hoặc mã dài, có thể không wrap theo cách người dùng mong muốn.

Khi bảng hiển thị văn bản tiếng Việt, cần kiểm thử với dấu Unicode và font terminal thực tế. Độ rộng hiển thị của ký tự không luôn bằng số UTF-16 code unit của Java String. Tránh tự căn lề bằng **String.length()** trước khi đưa dữ liệu vào Table API.

## 9. Chuyển đổi code cũ theo từng bước

Khi nâng một dự án đang dùng Spring Shell 3.x, thực hiện lần lượt:

1. Nâng nền tảng tương thích lên Spring Boot 4 và Spring Framework 7 theo yêu cầu của Spring Shell 4.
2. Bỏ dependency **spring-shell-table** cũ.
3. Thêm **spring-shell-jline** nếu ứng dụng cần JLine hoặc Table API.
4. Đổi import từ **org.springframework.shell.table** sang **org.springframework.shell.jline.tui.table**.
5. Giữ nguyên tên lớp bảng và rà soát các import của mọi kiểu được dùng, kể cả formatter, matcher, aligner và size constraint.
6. Biên dịch lại để phát hiện những lớp hoặc package còn sót.
7. Chạy kiểm thử bảng với dữ liệu rỗng, dữ liệu dài, Unicode và chiều rộng terminal khác nhau.
8. Kiểm tra runner mà ứng dụng sử dụng; Spring Shell 4 có **SystemShellRunner** dùng Java Console và **JLineShellRunner** dùng module JLine.

Ví dụ thay đổi import thường gặp:

~~~diff
- import org.springframework.shell.table.Table;
- import org.springframework.shell.table.TableBuilder;
- import org.springframework.shell.table.TableModelBuilder;
+ import org.springframework.shell.jline.tui.table.Table;
+ import org.springframework.shell.jline.tui.table.TableBuilder;
+ import org.springframework.shell.jline.tui.table.TableModelBuilder;
~~~

Không cần viết lại toàn bộ logic dựng model chỉ vì package thay đổi. Trước tiên, cập nhật dependency và import; sau đó mới xử lý những khác biệt API khác mà compiler hoặc kiểm thử chỉ ra.

## 10. Lỗi thường gặp khi chuyển package

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy package org.springframework.shell.table | Code còn import package 3.x | Đổi sang org.springframework.shell.jline.tui.table |
| Không tìm thấy artifact spring-shell-table | Module bảng đã được gộp vào module JLine | Dùng spring-shell-jline |
| Table API không có trên classpath | Chỉ khai báo spring-shell-core | Thêm spring-shell-jline nếu cần API bảng |
| Import từ org.jline không biên dịch | Nhầm package Spring Shell table với API JLine trực tiếp | Import các lớp bảng từ org.springframework.shell.jline.tui.table |
| Code dùng SystemShellRunner nhưng không có Table API | Core không kéo JLine vào | Thêm module JLine hoặc chọn thư viện bảng khác |
| Bảng tràn terminal | Truyền render width quá lớn hoặc dùng NoWrapSizeConstraints | Tính width theo terminal và chọn wrapper phù hợp |
| Nội dung dài không xuống dòng | Chuỗi không có ranh giới từ hoặc dùng no-wrap | Cung cấp TextWrapper phù hợp hoặc giới hạn nội dung |
| Bảng có ký tự viền thành ô vuông | Font hoặc terminal thiếu glyph box drawing | Dùng BorderStyle.oldschool hoặc kiểm tra font |
| Cột căn sai với tiếng Việt | Đo chuỗi bằng số code unit | Dùng Table API và kiểm tra độ rộng hiển thị trên terminal |
| Bảng hiển thị nội dung object không mong muốn | Formatter mặc định gọi toString() | Đăng ký Formatter riêng cho kiểu dữ liệu đó |

## 11. Kiểm thử sau khi nâng cấp

Kiểm thử cần xác nhận cả dependency, model và kết quả hiển thị:

1. **Dependency:** ứng dụng biên dịch với spring-shell-jline và không còn phụ thuộc module spring-shell-table cũ.
2. **Imports:** tất cả lớp bảng được tham chiếu từ package mới.
3. **Model:** số hàng, số cột và giá trị từng ô đúng với dữ liệu đầu vào.
4. **Header:** viền header và thứ tự cột được giữ như mong muốn.
5. **Empty data:** bảng rỗng hoặc chỉ có header hiển thị theo quy tắc của ứng dụng.
6. **Null:** ô null không gây lỗi formatter và có cách hiển thị nhất quán.
7. **Long text:** nội dung dài được wrap hoặc crop đúng.
8. **Unicode:** tiếng Việt, combining mark và ký tự ngoài BMP không làm lệch cột.
9. **Terminal width:** kiểm tra nhiều giá trị render width, bao gồm cửa sổ hẹp.
10. **Border style:** kiểm tra oldschool và kiểu fancy trên terminal mục tiêu.
11. **Command integration:** command trả về hoặc ghi đúng chuỗi bảng, không trộn thông báo ngoài ý muốn.
12. **Runner:** xác nhận ứng dụng dùng đúng runner và dependency JLine đã được nạp khi cần.

Nên giữ một số test đầu ra chuẩn cho những bảng quan trọng. Khi nâng phiên bản Spring Shell hoặc JLine, so sánh kết quả để phát hiện thay đổi về wrapping, border hoặc alignment.

## 12. Checklist migration

- [ ] Đã chuyển dependency từ spring-shell-table sang spring-shell-jline.
- [ ] Đã cập nhật mọi import của org.springframework.shell.table.
- [ ] Đã kiểm tra các lớp Table, TableBuilder, TableModel và TableModelBuilder.
- [ ] Đã kiểm tra BorderStyle, BorderSpecification và CellMatcher.
- [ ] Đã kiểm tra Formatter, Aligner, SizeConstraints và TextWrapper.
- [ ] Đã dùng Spring Shell dependency management để giữ phiên bản tương thích.
- [ ] Đã chọn SystemShellRunner hoặc JLineShellRunner theo nhu cầu.
- [ ] Đã kiểm tra render width và wrapping.
- [ ] Đã kiểm tra font và Unicode box drawing.
- [ ] Đã chạy test trên dữ liệu thực tế và terminal mục tiêu.

Điểm cốt lõi của migration là API bảng vẫn thuộc Spring Shell, nhưng đã chuyển vào module tích hợp JLine. Khi dependency và package được cập nhật đúng, phần lớn code dựng model và cấu hình TableBuilder có thể tiếp tục được sử dụng; phần còn lại cần được xác minh bằng biên dịch và kiểm thử trên terminal thật.

## Tài liệu tham khảo

- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — module spring-shell-table được gộp vào spring-shell-jline và package bảng được chuyển sang org.springframework.shell.jline.tui.table.
- [Spring Shell 4.0.4 API — Package org.springframework.shell.jline.tui.table](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/package-summary.html) — danh sách lớp và interface của API bảng mới.
- [Spring Shell 4.0.3 API — Table](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html) — model và phương thức render theo chiều rộng khả dụng.
- [Spring Shell 4.0.3 API — TableBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html) — cấu hình border và xây dựng Table.
- [Spring Shell 4.0.4 API — TableModelBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModelBuilder.html) — thêm hàng, thêm giá trị và tạo TableModel.
- [Spring Shell 4.0.4 API — BorderStyle](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BorderStyle.html) — các kiểu viền ASCII và Unicode box drawing.
- [Spring Shell 4.0.3 API — Tables](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Tables.html) — tiện ích cấu hình bảng, bao gồm hiển thị Map dạng key-value.
- [Spring Shell 4.0.3 API — TableModel](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModel.html) — hợp đồng truy xuất số hàng, số cột và giá trị ô.
- [Spring Shell 4.0.3 API — TableBuilder CellMatcherStub](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.CellMatcherStub.html) — tùy chỉnh formatter, aligner, wrapper và size constraint theo ô.
