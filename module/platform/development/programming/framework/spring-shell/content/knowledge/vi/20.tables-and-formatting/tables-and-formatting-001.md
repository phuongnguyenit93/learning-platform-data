# Khi nào dùng bảng văn bản cho kết quả CLI

Một command CLI thường trả về danh sách bản ghi, trạng thái tác vụ hoặc kết quả truy vấn. Bảng văn bản là cách trình bày phù hợp khi người dùng cần so sánh nhiều bản ghi có cùng các trường, chẳng hạn mã dự án, tên, trạng thái và thời điểm cập nhật. Các cột thẳng hàng giúp mắt quét dữ liệu nhanh và nhận ra khác biệt giữa các dòng.

Tuy nhiên, bảng không phải định dạng tốt cho mọi kết quả. Một giá trị đơn, đoạn mô tả dài, cấu trúc lồng nhau hoặc dữ liệu cần chuyển tiếp cho chương trình khác thường phù hợp hơn với văn bản ngắn, dạng khóa-giá trị, JSON hoặc CSV. Hãy chọn cách hiển thị theo người đọc và mục đích sử dụng đầu ra.

## 1. Bảng văn bản giải quyết vấn đề gì?

Bảng văn bản đặt các bản ghi cùng cấu trúc thành hàng và các thuộc tính thành cột. Người dùng có thể:

- Quét nhanh danh sách và tìm bản ghi theo mã hoặc tên.
- So sánh các trường cùng loại giữa nhiều bản ghi.
- Nhận biết trạng thái, số lượng, thời gian hoặc mức độ khác nhau.
- Đọc kết quả ngay trong terminal mà không cần mở công cụ khác.

Ví dụ, command `project list` có thể hiển thị:

```text
+------+-----------+------------+---------------------+
| ID   | Dự án     | Trạng thái | Cập nhật            |
+------+-----------+------------+---------------------+
| P101 | catalog   | READY      | 2026-11-26 09:10:00 |
| P102 | checkout  | BUILDING   | 2026-11-26 09:12:30 |
| P103 | inventory | FAILED     | 2026-11-26 09:14:05 |
+------+-----------+------------+---------------------+
3 dự án
```

Mỗi hàng là một dự án; mỗi cột giữ cùng một ý nghĩa cho tất cả hàng. Người vận hành có thể nhìn cột Trạng thái để tìm dự án lỗi mà không phải đọc ba đoạn mô tả riêng biệt.

## 2. Khi nào nên chọn bảng?

Dùng bảng khi phần lớn các điều kiện sau đúng:

1. Kết quả có nhiều bản ghi cùng một cấu trúc.
2. Người đọc cần so sánh các thuộc tính theo hàng hoặc theo cột.
3. Số cột có thể giữ ở mức vừa phải.
4. Nội dung từng ô ngắn hoặc có thể rút gọn mà không làm mất ý nghĩa.
5. Người đọc chủ yếu xem kết quả trực tiếp trong terminal.

Các tình huống thường phù hợp:

| Command | Dữ liệu | Vì sao bảng hữu ích |
| --- | --- | --- |
| `user list` | ID, tên, vai trò, trạng thái | Dễ so sánh tài khoản và tìm trạng thái |
| `job list` | Mã job, loại, trạng thái, thời gian bắt đầu | Dễ nhận biết job đang chạy hoặc thất bại |
| `project list` | Mã, tên, nhánh, phiên bản build | Các bản ghi có cùng trường |
| `cache stats` | Tên cache, số entry, hit rate, dung lượng | Dễ so sánh chỉ số giữa các cache |
| `config profiles` | Profile, nguồn cấu hình, trạng thái kích hoạt | Dễ nhìn profile nào đang bật |
| `test results` | Tên nhóm, passed, failed, skipped, duration | Dễ so sánh kết quả kiểm thử |

Bảng đặc biệt có ích cho danh sách có thứ tự hoặc kết quả tổng hợp. Nếu người dùng cần tìm một dòng cụ thể, hãy sắp xếp theo trường hữu ích như tên, thời gian hoặc trạng thái; đừng dựa vào thứ tự tình cờ từ database.

## 3. Khi nào không nên dùng bảng?

Không chọn bảng chỉ vì dữ liệu có thể chia thành nhiều trường. Hãy dùng cách trình bày khác khi cấu trúc bảng làm kết quả khó đọc hơn:

| Tình huống | Cách trình bày phù hợp hơn | Lý do |
| --- | --- | --- |
| Một kết quả đơn như `Build thành công` | Một câu ngắn | Không có nhiều hàng để so sánh |
| Một cấu hình có vài thuộc tính | Dạng khóa-giá trị | Mỗi thuộc tính có thể có giá trị dài và khác kiểu |
| Đoạn log hoặc mô tả nhiều dòng | Văn bản nhiều dòng | Không nên ép văn bản tự do vào ô bảng |
| JSON lồng nhau hoặc object phức tạp | JSON có thụt lề | Giữ được cấu trúc và quan hệ lồng nhau |
| Dữ liệu cần pipe sang `jq`, `awk` hoặc chương trình khác | JSON hoặc CSV | Bảng có viền và khoảng trắng không phải giao thức dữ liệu |
| Hàng nghìn bản ghi | Phân trang, lọc hoặc xuất tệp | In toàn bộ bảng làm terminal khó sử dụng |
| Quá nhiều cột hoặc giá trị rất dài | Chọn cột, hiển thị chi tiết theo ID | Bảng bị tràn chiều rộng hoặc phải xuống dòng quá nhiều |

Ví dụ, command `system status` trả một đối tượng đơn thường dễ đọc hơn ở dạng:

```text
Application : inventory-api
Environment : staging
Version     : 2.8.1
Health      : UP
Uptime      : 3 days, 4 hours
```

Nếu trả một thông báo đơn giản, hãy dùng câu trực tiếp:

```text
Đã tạo bản backup backup-2026-11-26.zip
```

Không tạo một bảng chỉ có một hàng dữ liệu và hai cột nếu cách trình bày khóa-giá trị hoặc câu thông báo dễ hiểu hơn.

## 4. Chọn bảng, khóa-giá trị, JSON hay CSV

Các định dạng phục vụ những người đọc khác nhau:

| Định dạng | Người đọc chính | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| Bảng văn bản | Người vận hành terminal | Dễ quét và so sánh bản ghi | Không phù hợp để parse tự động |
| Khóa-giá trị | Người đọc một cấu hình hoặc một đối tượng | Dễ đọc trường có giá trị dài | So sánh nhiều bản ghi kém trực quan |
| JSON | Chương trình, script, API và người cần cấu trúc đầy đủ | Giữ kiểu dữ liệu và cấu trúc lồng nhau | Dài hơn và khó quét bằng mắt nếu nhiều trường |
| CSV | Spreadsheet và công cụ xử lý bảng | Dễ nhập vào Excel hoặc công cụ dữ liệu | Không biểu diễn tốt cấu trúc lồng nhau; cần xử lý dấu phẩy và dấu nháy |
| Văn bản thuần | Người đọc thông báo hoặc log | Gọn, dễ ghi log và tìm kiếm | Khó so sánh các bản ghi cùng cấu trúc |

Nếu command vừa phục vụ người dùng terminal vừa phục vụ automation, hãy hỗ trợ một option định dạng rõ ràng, ví dụ:

```text
project list --format table
project list --format json
project list --format csv
```

Có thể đặt `table` làm mặc định khi chạy tương tác và yêu cầu người gọi automation chỉ định `json` hoặc `csv`. Dù chọn mặc định nào, định dạng phải được công bố trong help và giữ ổn định để script không phải đoán.

Đừng dùng bảng có viền như định dạng truyền dữ liệu. Khoảng trắng có thể thay đổi theo độ rộng terminal, nội dung và phiên bản formatter; ANSI color hoặc ký tự Unicode cũng có thể làm chương trình đọc đầu ra thất bại.

## 5. Chọn cột có giá trị cho người đọc

Một bảng tốt chỉ giữ những cột hỗ trợ quyết định hoặc thao tác tiếp theo. Với `project list`, các cột `ID`, `Tên`, `Trạng thái` và `Cập nhật` có thể đủ. Những trường như mô tả dài, cấu hình chi tiết, stack trace và nội dung file nên được xem bằng command khác.

Ví dụ:

```text
project list
project show --id P103
project logs --id P103
```

`project list` cho cái nhìn tổng quan; `project show` cung cấp thông tin chi tiết; `project logs` trả nội dung dài. Cách phân chia này giúp bảng không phải chứa toàn bộ dữ liệu của domain.

Khi chọn cột:

- Đưa định danh dễ dùng lên đầu để người đọc có thể gọi command chi tiết.
- Đặt tên cột ngắn nhưng đủ nghĩa; tránh các tên nội bộ khó hiểu.
- Dùng một cột cho một khái niệm; không gộp nhiều giá trị không liên quan vào cùng ô.
- Đưa trạng thái hoặc kết quả quan trọng vào vị trí dễ quét.
- Giữ thứ tự cột ổn định giữa các lần gọi command.
- Không hiển thị dữ liệu nhạy cảm như token, mật khẩu hoặc khóa bí mật.

Nếu có nhiều thuộc tính, hãy cung cấp option chọn cột hoặc một command chi tiết. Tránh thêm cột chỉ vì thuộc tính đó có sẵn trong entity.

## 6. Giữ bảng vừa với chiều rộng terminal

Terminal có chiều rộng hữu hạn. Một bảng có 12 cột, mỗi cột dài 30 ký tự, thường không thể đọc được trên cửa sổ terminal thông thường. Spring Shell có cơ chế tính kích thước cột, wrap nội dung và căn chỉnh; `Table` nhận chiều rộng khả dụng khi render.

Nên áp dụng các quy tắc:

- Giới hạn số cột hiển thị mặc định.
- Đặt chiều rộng hợp lý cho ID, trạng thái, số lượng và thời gian.
- Rút gọn mô tả dài bằng dấu ba chấm khi có thể truy cập đầy đủ qua command chi tiết.
- Wrap văn bản chỉ khi các dòng tiếp tục vẫn dễ xác định thuộc ô nào.
- Không để URL, hash hoặc chuỗi không có điểm ngắt làm bảng nở quá rộng.
- Kiểm thử ở terminal hẹp và rộng, ví dụ 80 và 120 cột.

`TableBuilder` của Spring Shell cung cấp các chiến lược sizing và wrapping. Mặc định, formatter chuyển giá trị bằng `toString()`, sizing tận dụng chiều rộng có sẵn và có thể chia dòng tại khoảng trắng, text wrapper wrap theo dấu cách, còn aligner căn trái. Nếu dữ liệu chứa chuỗi dài không có khoảng trắng, mặc định này có thể không tạo được bảng gọn; hãy rút gọn dữ liệu hoặc cấu hình sizing/wrapper phù hợp.

Đừng cắt ID, trạng thái hoặc số liệu theo cách làm mất khả năng nhận diện. Nếu phải rút gọn một giá trị, giữ phần đủ phân biệt và cung cấp command xem đầy đủ.

## 7. Căn chỉnh và định dạng từng loại dữ liệu

Các cột có kiểu dữ liệu khác nhau nên có cách hiển thị khác nhau:

| Kiểu dữ liệu | Cách trình bày gợi ý |
| --- | --- |
| Tên, mô tả ngắn | Căn trái |
| Số lượng, phần trăm, dung lượng | Căn phải hoặc căn theo dấu thập phân |
| Ngày giờ | Dùng một định dạng thống nhất, nêu múi giờ khi cần |
| Boolean | Dùng nhãn rõ như `Có/Không` hoặc `Enabled/Disabled` |
| Enum trạng thái | Dùng nhãn ngắn, nhất quán và không phụ thuộc màu |
| Giá trị thiếu | Dùng dấu `-` hoặc `Chưa có`; phân biệt với số 0 |

Không nên chỉ dùng màu để truyền trạng thái. Người dùng có thể chạy terminal không hỗ trợ màu, lưu output vào file hoặc đọc bằng công cụ hỗ trợ. Hãy hiển thị `FAILED`, `READY`, `DISABLED` hoặc nhãn tương đương bằng chữ; màu chỉ là tín hiệu bổ sung.

Đối với ngày giờ, chọn một múi giờ và định dạng rõ ràng. Nếu các bản ghi đến từ nhiều vùng, hiển thị offset hoặc chuẩn hóa về UTC để tránh so sánh nhầm. Với số liệu, công bố đơn vị ngay trong tiêu đề hoặc giá trị, chẳng hạn `Dung lượng (MB)` và `Thời gian (ms)`.

## 8. Tạo bảng với Spring Shell 4.x

Spring Shell 4.x cung cấp `TableModel`, `ArrayTableModel`, `BeanListTableModel`, `TableBuilder` và `Table`. `TableModel` mô tả số hàng, số cột và giá trị ở từng ô; `TableBuilder` áp dụng formatter, sizing, wrapping, alignment và đường viền; `Table.render(totalAvailableWidth)` tạo chuỗi kết quả.

Ví dụ sau tạo bảng dự án. Hàng đầu tiên trong mảng là tiêu đề:

```java
import org.springframework.shell.jline.tui.table.ArrayTableModel;
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableModel;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

    @Command(name = "project list", description = "Liệt kê dự án.")
    public String list() {
        Object[][] rows = {
            {"ID", "Tên", "Trạng thái", "Dung lượng"},
            {"P101", "catalog", "READY", "12 MB"},
            {"P102", "checkout", "BUILDING", "18 MB"},
            {"P103", "inventory", "FAILED", "9 MB"}
        };

        TableModel model = new ArrayTableModel(rows);
        Table table = new TableBuilder(model)
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        return table.render(100);
    }
}
```

Trong ví dụ, `ArrayTableModel` nhận mảng theo thứ tự hàng. `addHeaderBorder` tạo đường viền ngoài và nhấn mạnh hàng đầu tiên. `oldschool` dùng ký tự ASCII đơn giản, phù hợp với terminal có hỗ trợ Unicode hạn chế. Nếu terminal hiển thị box-drawing characters tốt, có thể chọn `BorderStyle.fancy_light` để có đường viền Unicode.

Chiều rộng `100` trong ví dụ là giá trị minh họa. Trong ứng dụng thực tế, hãy lấy chiều rộng terminal hoặc giới hạn theo cấu hình của ứng dụng rồi truyền vào `render`. Nếu command có thể chạy trong môi trường không có terminal thật, hãy chọn chiều rộng fallback và kiểm thử output ở chế độ non-interactive.

Khi dữ liệu là danh sách bean, `BeanListTableModel` cho phép chọn những property cần hiển thị và thứ tự của chúng. Điều này hữu ích khi entity có nhiều thuộc tính nhưng bảng chỉ nên đưa ra một số cột:

```java
import org.springframework.shell.jline.tui.table.BeanListTableModel;
import org.springframework.shell.jline.tui.table.TableModel;

TableModel model = new BeanListTableModel<>(
        projects,
        "id",
        "name",
        "status"
);
```

Chỉ chọn những property có ý nghĩa với người đọc. Không đưa toàn bộ field của entity vào bảng theo mặc định.

## 9. Khác biệt package của API bảng giữa 3.x và 4.x

API bảng có thay đổi package khi nâng cấp:

| Thành phần | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| `Table` | `org.springframework.shell.table.Table` | `org.springframework.shell.jline.tui.table.Table` |
| `TableModel` | `org.springframework.shell.table.TableModel` | `org.springframework.shell.jline.tui.table.TableModel` |
| `ArrayTableModel` | `org.springframework.shell.table.ArrayTableModel` | `org.springframework.shell.jline.tui.table.ArrayTableModel` |
| `BeanListTableModel` | `org.springframework.shell.table.BeanListTableModel` | `org.springframework.shell.jline.tui.table.BeanListTableModel` |
| `TableBuilder` | `org.springframework.shell.table.TableBuilder` | `org.springframework.shell.jline.tui.table.TableBuilder` |
| `BorderStyle` | `org.springframework.shell.table.BorderStyle` | `org.springframework.shell.jline.tui.table.BorderStyle` |

Với Spring Shell 3.3/3.4, các lớp trên thuộc package `org.springframework.shell.table`. Với Spring Shell 4.x, chúng chuyển sang package `org.springframework.shell.jline.tui.table`. Khi nâng cấp, cập nhật import và kiểm tra dependency cung cấp phần JLine/TUI tương ứng; không trộn các lớp table từ hai package trong cùng một đoạn code.

Phần lựa chọn nội dung cột, độ rộng, dữ liệu rút gọn và định dạng cho người đọc vẫn là quyết định thiết kế của command, bất kể dùng package 3.x hay 4.x.

## 10. Bảng rỗng, phân trang và kết quả lớn

Một bảng không có hàng dữ liệu không nên chỉ in tiêu đề và đường viền. Hãy hiển thị trạng thái rỗng có ý nghĩa:

```text
Không tìm thấy dự án phù hợp với bộ lọc hiện tại.
```

Với danh sách lớn, đừng tải và render mọi bản ghi chỉ để tạo bảng. Cung cấp:

- `--limit` để giới hạn số hàng.
- `--page` hoặc `--offset` để xem trang tiếp theo.
- `--sort` để sắp xếp theo trường được hỗ trợ.
- `--filter` để giảm số bản ghi cần đọc.
- `--format json` hoặc `--format csv` để xuất toàn bộ dữ liệu khi cần.

Ví dụ:

```text
project list --status FAILED --limit 20
project list --sort updatedAt --direction desc --limit 20
project list --format csv
```

Khi có phân trang, hiển thị tổng số bản ghi hoặc vị trí trang nếu backend cung cấp thông tin đó. Đừng tự tính tổng bằng cách tải tất cả dữ liệu nếu điều đó làm command chậm hoặc tốn bộ nhớ.

## 11. Bảo đảm bảng không làm hỏng automation

Output dạng bảng hướng đến con người. Nếu một script gọi command rồi phân tích output bằng cách tách cột theo dấu `|`, việc thay đổi độ rộng, border, màu hoặc nội dung sẽ làm script dễ hỏng.

Đối với command được dùng trong CI/CD hoặc script:

- Giữ một định dạng máy đọc được như JSON hoặc CSV.
- Công bố option định dạng và schema đầu ra.
- Không trộn thông báo tiến trình vào stdout nếu stdout được dùng làm dữ liệu.
- Đưa thông báo chẩn đoán ra stderr hoặc logger theo quy ước của ứng dụng.
- Giữ tên trường, thứ tự cột CSV, kiểu dữ liệu và cách biểu diễn null ổn định.
- Kiểm thử output bằng dữ liệu có dấu phẩy, dấu nháy, newline, Unicode và giá trị null.

CSV phải được escape đúng quy tắc: trường chứa dấu phẩy, dấu nháy hoặc xuống dòng cần được đặt trong dấu nháy kép và dấu nháy kép bên trong phải được nhân đôi. JSON nên giữ số và boolean dưới đúng kiểu thay vì chuyển tất cả thành chuỗi.

Một lựa chọn tốt là dùng cùng một nguồn dữ liệu domain rồi có các renderer riêng:

```java
return switch (format) {
    case "table" -> renderTable(projects);
    case "json" -> renderJson(projects);
    case "csv" -> renderCsv(projects);
    default -> throw new IllegalArgumentException(
            "Format phải là table, json hoặc csv"
    );
};
```

Đây là pseudocode minh họa cách phân nhánh renderer; phần serialize JSON/CSV cần dùng thư viện và quy tắc escape phù hợp. Không nên lấy bảng đã render rồi cố chuyển ngược thành JSON hoặc CSV.

## 12. Kiểm thử khả năng đọc của bảng

Kiểm thử output không chỉ xác nhận command trả về đúng số hàng. Hãy kiểm tra cả cách bảng hiển thị khi nội dung thay đổi:

- Danh sách không có hàng.
- Một hàng và nhiều hàng.
- Tên dài, ID dài hoặc chuỗi không có khoảng trắng.
- Giá trị null, số 0 và chuỗi rỗng.
- Tiếng Việt có dấu và ký tự Unicode.
- Terminal hẹp và rộng.
- Trạng thái được biểu diễn bằng chữ khi tắt màu.
- Dữ liệu có chứa ký tự đặc biệt khi xuất CSV/JSON.
- Bảng có nhiều bản ghi nhưng chỉ render số hàng đã giới hạn.

Spring Shell cung cấp cấu hình terminal width cho `@ShellTest`; có thể đặt các chiều rộng khác nhau để phát hiện bảng bị tràn hoặc wrap khó đọc. Ví dụ:

```java
@ShellTest(properties = {
    "spring.shell.test.terminal-width=80",
    "spring.shell.test.terminal-height=24"
})
class ProjectCommandsTests {
    // Kiểm tra output của command ở terminal rộng 80 cột.
}
```

Ngoài kiểm thử tự động, hãy xem output thực tế trên terminal Windows, macOS hoặc Linux mà ứng dụng hỗ trợ. Cách terminal tính độ rộng ký tự Unicode và hiển thị box-drawing có thể khác nhau.

## 13. Checklist chọn bảng văn bản

- Dùng bảng khi có nhiều bản ghi đồng cấu trúc và người dùng cần so sánh.
- Chọn số cột vừa phải, có tên ngắn và dễ hiểu.
- Đưa ID lên vị trí dễ tìm để command chi tiết có thể dùng lại.
- Giữ thứ tự cột và cách biểu diễn trạng thái ổn định.
- Căn chỉnh số liệu, đơn vị và ngày giờ nhất quán.
- Không dựa vào màu sắc duy nhất để truyền trạng thái.
- Kiểm soát chiều rộng, wrap và rút gọn nội dung dài.
- Hiển thị thông báo rõ ràng khi không có dữ liệu.
- Phân trang hoặc lọc dữ liệu lớn trước khi render.
- Dùng JSON/CSV cho đầu ra máy đọc được.
- Tách renderer table khỏi dữ liệu nghiệp vụ.
- Kiểm thử Unicode, terminal width, output rỗng và chế độ automation.

## Tài liệu tham khảo

- [Spring Shell — Project features](https://spring.io/projects/spring-shell/)
- [Spring Shell 3.3 — Table package](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/package-summary.html)
- [Spring Shell 3.3 — TableBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TableBuilder.html)
- [Spring Shell 3.3 — TableModel API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TableModel.html)
- [Spring Shell 4.0.3 — Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html)
- [Spring Shell 4.0.3 — TableBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html)
- [Spring Shell 4.0.3 — BeanListTableModel API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BeanListTableModel.html)
- [Spring Shell 3.4 — Testing Settings](https://docs.spring.io/spring-shell/reference/3.4/testing/settings.html)
