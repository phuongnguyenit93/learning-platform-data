# Giới hạn số dòng để không làm terminal hoặc bộ kiểm thử quá tải

Một command liệt kê dữ liệu có thể trả về hàng nghìn bản ghi. Nếu in toàn bộ kết quả vào terminal, người dùng khó tìm thông tin cần thiết, output bị đẩy khỏi vùng scrollback và thời gian render tăng lên. Nếu command được gọi qua `ShellTestClient`, toàn bộ nội dung màn hình cũng được giữ lại để kiểm tra, khiến test chậm và tốn bộ nhớ khi dữ liệu quá lớn.

Giải pháp là giới hạn dữ liệu ngay từ truy vấn, hiển thị theo trang và nói rõ còn bao nhiêu kết quả hoặc cách xem phần tiếp theo. Chỉ giới hạn số dòng sau khi đã tải toàn bộ dữ liệu không giải quyết được chi phí truy vấn và bộ nhớ. Với dữ liệu lớn, cần phân trang ở repository/database hoặc xuất ra file theo luồng riêng.

## Vì sao phải giới hạn output?

Một bảng có 5 cột và 2.000 dòng có thể tạo ra hàng chục nghìn dòng terminal khi nội dung ô bị wrap. Điều đó ảnh hưởng cả người dùng lẫn ứng dụng:

- Người dùng phải cuộn qua quá nhiều output để tìm một bản ghi.
- Prompt và kết quả command trước bị đẩy xa khỏi vùng dễ quan sát.
- Terminal emulator phải xử lý nhiều ký tự, đường viền, màu và wrapping.
- Test phải capture và giữ một lượng output lớn dù chỉ cần xác minh một vài dòng.
- Log của CI/CD phình to, làm khó việc tìm lỗi và có thể chạm giới hạn lưu trữ.
- Nếu service tải tất cả bản ghi trước khi cắt bớt, database, heap và mạng vẫn phải chịu chi phí của toàn bộ tập dữ liệu.

Giới hạn output là một phần của hợp đồng CLI. Người dùng cần biết command đang hiển thị bao nhiêu bản ghi, cách lấy trang kế tiếp và cách xuất toàn bộ dữ liệu khi thật sự cần.

## Phân biệt số dòng, chiều cao terminal và kích thước output

Ba giới hạn này có liên quan nhưng không giống nhau:

| Khái niệm | Đơn vị | Điều được kiểm soát |
|---|---|---|
| Số bản ghi hiển thị | Rows | Số mục dữ liệu trong bảng |
| Chiều cao terminal | Terminal lines | Số dòng có thể nhìn thấy trong viewport hiện tại |
| Kích thước output | Characters/bytes | Lượng dữ liệu được tạo, ghi, capture hoặc lưu |

Một bản ghi có mô tả dài có thể wrap thành nhiều dòng. Vì vậy, 10 bản ghi không nhất thiết chỉ chiếm 10 dòng terminal. Ngược lại, terminal cao 24 dòng không có nghĩa command tự động chỉ được in 24 dòng; terminal có thể có scrollback dài hơn viewport.

Spring Shell `Table.render(totalAvailableWidth)` nhận chiều rộng khả dụng để tính kích thước và wrapping của bảng. API này không nhận giới hạn chiều cao hoặc số dòng dữ liệu. `TableModel` cung cấp `getRowCount()`, `getColumnCount()` và `getValue(...)`; số dòng thực tế phụ thuộc dữ liệu trong model. Do đó, hãy giới hạn danh sách trước khi tạo `TableModel` và render bảng.

## Chọn giới hạn mặc định và giới hạn tối đa

Một command list nên có:

- Kích thước trang mặc định nhỏ, đủ để người dùng quét nhanh.
- Giới hạn tối đa do ứng dụng kiểm soát.
- Cách chuyển sang trang tiếp theo hoặc trang trước.
- Thông báo rõ khi còn kết quả.
- Một command export riêng nếu người dùng cần toàn bộ dữ liệu.

Ví dụ chính sách cho command `customer-list`:

| Tham số | Giá trị ví dụ | Ý nghĩa |
|---|---:|---|
| `--page` | `0` | Trang đầu tiên, đánh số từ 0 trong API |
| `--size` | `10` | Mặc định hiển thị 10 bản ghi |
| Giới hạn `--size` | `50` | Từ chối yêu cầu lớn hơn 50 |
| `hasNext` | `true/false` | Cho biết còn trang kế tiếp |

Các con số trên là chính sách minh họa, không phải giới hạn cố định của Spring Shell. Hãy chọn giá trị dựa trên độ rộng cột, chiều cao terminal mục tiêu, độ dài nội dung và thời gian truy vấn. Bảng có nhiều cột hoặc ô thường xuyên wrap nên có trang nhỏ hơn.

Không nên âm thầm đổi `--size=5000` thành 50 mà không báo cho người dùng. Có thể từ chối bằng validation hoặc hiển thị rõ kích thước hiệu lực. Ví dụ dưới đây dùng `@Max(50)` để từ chối yêu cầu vượt giới hạn.

## Phân trang tại tầng truy vấn

Hãy để database hoặc repository chỉ trả về một trang. Với Spring Data, có thể dùng `Pageable` và `Slice`:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
class CustomerQueryService {

    private final CustomerRepository repository;

    CustomerQueryService(CustomerRepository repository) {
        this.repository = repository;
    }

    Slice<CustomerRow> findPage(int page, int size) {
        var pageable = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Direction.ASC, "id"));
        return repository.findByActiveTrue(pageable);
    }
}
```

Repository khai báo một truy vấn có phân trang:

```java
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

interface CustomerRepository extends Repository<Customer, Long> {

    Slice<CustomerRow> findByActiveTrue(Pageable pageable);
}
```

`CustomerRow` có thể là projection hoặc DTO chứa các cột cần hiển thị, ví dụ `id`, `name`, `status`. Truy vấn cần có thứ tự ổn định như `id ASC`; nếu không có sort ổn định, các trang có thể trùng hoặc bỏ sót bản ghi khi dữ liệu thay đổi.

### Vì sao dùng Slice thay vì lấy tất cả rồi subList?

Đoạn code sau chỉ giới hạn phần hiển thị, nhưng đã tải toàn bộ dữ liệu trước đó:

```java
// Không nên với tập dữ liệu lớn.
List<Customer> all = repository.findAll();
List<Customer> visible = all.subList(0, Math.min(10, all.size()));
```

Nó vẫn tốn bộ nhớ theo tổng số bản ghi, có thể tải quan hệ không cần thiết và tạo áp lực lên database/network.

Với `Slice`, Spring Data chỉ lấy lượng dữ liệu cần cho trang và xác định có trang tiếp theo hay không. `Page` cũng cung cấp tổng số bản ghi và số trang, nhưng thường cần thêm count query. Nếu command chỉ cần biết còn dữ liệu hay không, `Slice` thường phù hợp hơn.

Nếu không dùng Spring Data, hãy thực hiện giới hạn tương đương trong truy vấn SQL, JDBC hoặc API nguồn dữ liệu. Không gọi `findAll()` rồi mới cắt list ở command.

## Command Spring Shell hiển thị một trang

Ví dụ sau dùng Spring Shell 4.x annotation model. Command giới hạn kích thước trang bằng Bean Validation, lấy một `Slice` từ service và chỉ render những bản ghi của trang hiện tại.

Ví dụ giả định ứng dụng đã có Bean Validation provider và Spring Shell validation support được cấu hình để các constraint trên tham số command được thực thi.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;
import org.springframework.data.domain.Slice;

@Component
class CustomerCommands {

    private final CustomerQueryService customerQueryService;

    CustomerCommands(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @Command(name = "customer-list", description = "Liệt kê khách hàng theo trang")
    public void list(
            @Option(longName = "page", defaultValue = "0")
            @Min(0) int page,
            @Option(longName = "size", defaultValue = "10")
            @Min(1) @Max(50) int size,
            CommandContext context) {

        Slice<CustomerRow> result = customerQueryService.findPage(page, size);
        var writer = context.outputWriter();

        writer.printf("Trang %d: hiển thị %d bản ghi%s%n",
                page + 1,
                result.getNumberOfElements(),
                result.hasNext() ? " — còn dữ liệu, dùng --page " + (page + 1) : "");

        for (CustomerRow row : result.getContent()) {
            writer.printf("%-12s %-28s %-12s%n",
                    row.id(),
                    shorten(row.name(), 26),
                    row.status());
        }
        writer.flush();
    }

    private String shorten(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value == null ? "" : value;
        }
        return value.substring(0, maxLength - 1) + "…";
    }
}
```

Trong ví dụ, `page` bắt đầu từ 0 nhưng thông báo hiển thị cho người dùng bắt đầu từ 1. `size` mặc định là 10 và không vượt quá 50. `hasNext()` cho biết có trang tiếp theo mà không cần tải toàn bộ danh sách.

`shorten()` chỉ rút gọn phần tên để hạn chế một ô chiếm quá nhiều chiều ngang. Trong ứng dụng cần hỗ trợ Unicode rộng hoặc ký tự kết hợp, nên dùng bộ tính display width phù hợp terminal thay vì xem `String.length()` là số cột hiển thị chính xác.

## Render Table từ dữ liệu đã giới hạn

Nếu dùng table renderer của Spring Shell, hãy tạo model từ `result.getContent()` sau khi truy vấn đã phân trang. Ví dụ dưới đây dùng API Spring Shell 4.x:

```java
import java.util.List;

import org.springframework.shell.jline.tui.table.ArrayTableModel;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;

class CustomerTableRenderer {

    Table renderCustomerTable(List<CustomerRow> rows) {
        Object[][] data = new Object[rows.size() + 1][3];
        data[0] = new Object[] {"ID", "NAME", "STATUS"};

        for (int i = 0; i < rows.size(); i++) {
            CustomerRow row = rows.get(i);
            data[i + 1] = new Object[] {
                    row.id(),
                    shorten(row.name(), 26),
                    row.status()
            };
        }

        return new TableBuilder(new ArrayTableModel(data)).build();
    }

    private String shorten(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value == null ? "" : value;
        }
        return value.substring(0, maxLength - 1) + "…";
    }
}
```

Command có thể render bảng với một ngân sách chiều rộng đã xác định bởi adapter hoặc cấu hình ứng dụng:

```java
Table table = new CustomerTableRenderer().renderCustomerTable(result.getContent());
context.outputWriter().println(table.render(100));
context.outputWriter().flush();
```

Giá trị `100` là chiều rộng minh họa. Ứng dụng có thể lấy chiều rộng terminal qua thành phần terminal/presentation phù hợp với cấu hình đang dùng. Điều quan trọng với giới hạn số dòng là model chỉ nhận `result.getContent()`, không nhận toàn bộ dữ liệu.

Trong Spring Shell 3.x, table API nằm trong package `org.springframework.shell.table`. Trong Spring Shell 4.x, table API chuyển sang `org.springframework.shell.jline.tui.table`. Cần dùng package đúng phiên bản; nguyên tắc phân trang trước khi tạo `TableModel` không thay đổi.

## Thông báo phần dữ liệu chưa hiển thị

Không nên cắt bớt kết quả một cách im lặng. Người dùng cần biết:

- Có bao nhiêu bản ghi đang được hiển thị.
- Có trang tiếp theo hay không.
- Cú pháp để xem trang tiếp theo.
- Cách lấy toàn bộ dữ liệu nếu nghiệp vụ cho phép.

Ví dụ output:

```text
Trang 1: hiển thị 10 bản ghi — còn dữ liệu, dùng --page 1

ID           NAME                         STATUS
C001         Lan Nguyen                   ACTIVE
C002         Minh Tran                    ACTIVE
...
```

Nếu dùng `Page` và đã có tổng số, có thể hiển thị `Đang xem 1–10 trên 1.284 bản ghi`. Nếu dùng `Slice`, có thể chỉ nói `còn dữ liệu` để tránh count query. Không ghi tổng số ước lượng như một con số chính xác.

Khi không còn trang tiếp theo:

```text
Trang 4: hiển thị 6 bản ghi — đã đến cuối danh sách.
```

Với kết quả rỗng, thông báo rõ `Không tìm thấy bản ghi phù hợp` thay vì in bảng trống không giải thích.

## Chọn phân trang theo số trang hay cursor

Offset/page phù hợp với tập dữ liệu vừa phải và giao diện cần điều hướng tới trang cụ thể. Với tập dữ liệu rất lớn hoặc thay đổi liên tục, cursor/keyset pagination thường ổn định và hiệu quả hơn.

| Cách phân trang | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Offset/page | `page=3`, `size=10`; truy vấn bỏ qua 30 dòng rồi lấy 10 | Danh sách vừa phải, người dùng cần nhảy tới trang |
| Cursor/keyset | Gửi khóa cuối trang trước, ví dụ `after-id=C010`, rồi lấy các ID lớn hơn | Dữ liệu lớn, cập nhật thường xuyên, cần duyệt tuần tự |
| Stream/export | Đọc tuần tự theo batch và ghi ra file | Người dùng cần toàn bộ dữ liệu, không cần xem trên terminal |

Offset lớn có thể làm database phải bỏ qua nhiều bản ghi. Với cursor, dùng một khóa sắp xếp duy nhất hoặc tổ hợp khóa ổn định để không bỏ sót khi nhiều bản ghi có cùng giá trị sort. Cursor nên được tạo/kiểm tra ở service, không tin dữ liệu cursor tùy ý từ người dùng nếu nó có thể làm lộ phạm vi truy vấn.

## Giới hạn độ dài từng ô và tổng output

Giới hạn số bản ghi là cần thiết nhưng chưa đủ. Một bản ghi có thể chứa mô tả nhiều kilobyte hoặc xuống dòng. Hãy cân nhắc thêm:

- Giới hạn độ dài hiển thị cho từng cột.
- Chuẩn hóa hoặc escape newline/tab trong ô để không làm vỡ cấu trúc bảng.
- Chỉ chọn các cột cần thiết, không tải toàn bộ entity và quan hệ.
- Giới hạn tổng số ký tự hoặc byte khi command tạo output máy đọc.
- Đưa nội dung dài sang một command `show` riêng để người dùng xem chi tiết từng bản ghi.

Ví dụ, `customer-list` hiển thị ID, tên và trạng thái; người dùng gọi `customer-show --id C001` để xem địa chỉ, ghi chú và lịch sử dài. Cách này giữ bảng tổng quan gọn và tránh lặp nội dung lớn ở mọi dòng.

Nếu dữ liệu có newline, tab hoặc ANSI control characters do người dùng nhập, cần escape hoặc loại bỏ theo quy tắc hiển thị. Không để nội dung tự do làm chèn dòng giả, phá bảng hoặc tạo terminal control sequence ngoài ý muốn.

## Khi cần toàn bộ dữ liệu: dùng export thay vì in hết ra terminal

Nếu người dùng cần 100.000 bản ghi, terminal không phải đích phù hợp. Cung cấp command export riêng:

```text
customer-export --format csv --output customers.csv
```

Export nên đọc dữ liệu theo batch/cursor và ghi tuần tự ra file. Không gom toàn bộ dữ liệu thành một `List` hoặc một `String` lớn nếu không cần thiết. Hãy đóng writer/stream ở đúng nơi sở hữu tài nguyên, xử lý lỗi ghi file và báo số bản ghi đã xuất.

Nếu export thất bại giữa chừng, không báo `Xuất thành công`. Có thể ghi file tạm rồi đổi tên sau khi hoàn tất để tránh người dùng nhầm file một phần là file hoàn chỉnh. Với file lớn, nên ghi rõ vị trí file và trạng thái cuối cùng.

## Giới hạn output trong bộ kiểm thử Spring Shell

Spring Shell test support mô phỏng terminal để command có thể được gọi như người dùng nhập. Trong Spring Shell 3.4.x, terminal giả lập mặc định rộng 80 cột và cao 24 dòng. Có thể đổi bằng `spring.shell.test.terminal-width`, `spring.shell.test.terminal-height` hoặc thuộc tính `terminalWidth`/`terminalHeight` của `@ShellTest`.

Ví dụ test với terminal 80x24:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest(terminalWidth = 80, terminalHeight = 24)
class CustomerListCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void displaysOnlyTheRequestedPage() throws Exception {
        ShellScreen screen = client.sendCommand("customer-list --page=0 --size=10");

        assertThat(screen.lines())
                .anyMatch(line -> line.contains("hiển thị 10 bản ghi"));
        assertThat(screen.lines())
                .anyMatch(line -> line.contains("C001"));
        assertThat(screen.lines())
                .noneMatch(line -> line.contains("C011"));
    }
}
```

`ShellTestClient.sendCommand()` trả về `ShellScreen`; `ShellScreen.lines()` cung cấp các dòng đang được kiểm tra. Test trên dùng fixture có ít nhất 11 khách hàng và xác nhận trang đầu chỉ hiển thị 10 bản ghi. Nên có test riêng cho trang tiếp theo, trang cuối và kết quả rỗng.

### Không dùng hàng nghìn dòng trong mọi ShellTest

Một test tích hợp nên dùng fixture nhỏ và có chủ đích. Không cần tạo 100.000 dòng chỉ để xác nhận command áp dụng `size=10`. Hãy kiểm tra service nhận đúng `Pageable` hoặc repository chỉ trả về đúng số bản ghi, rồi kiểm tra một integration test có kích thước vừa đủ.

Các test hiệu năng hoặc tải dữ liệu lớn nên chạy riêng, có giới hạn thời gian và bộ nhớ rõ ràng. Không dùng `ShellTestClient` làm benchmark cho việc render hàng trăm nghìn dòng; mục tiêu của nó là kiểm tra tương tác command và output trong terminal giả lập.

### Kiểm tra nhiều kích thước terminal

Một bảng vừa với 120 cột có thể wrap mạnh ở 80 cột. Hãy kiểm tra ít nhất terminal hẹp và terminal tiêu chuẩn:

```java
@ShellTest(terminalWidth = 60, terminalHeight = 18)
class NarrowTerminalTests {
    // Xác nhận cột quan trọng vẫn đọc được và output không vượt chính sách.
}
```

Chiều cao 24 dòng là kích thước terminal giả lập mặc định trong tài liệu Spring Shell 3.4.x, không phải giới hạn số dòng mà mọi command phải tuân theo. Test có thể đặt chiều cao khác để mô phỏng người dùng, nhưng command vẫn cần chính sách pagination riêng.

## Các kiểm thử cần có

| Trường hợp | Điều cần xác nhận |
|---|---|
| Không truyền `--page`/`--size` | Dùng trang 0 và kích thước mặc định |
| `--size` bằng 0 hoặc âm | Validation từ chối trước khi truy vấn |
| `--size` lớn hơn mức tối đa | Validation từ chối hoặc áp dụng chính sách có thông báo rõ |
| Trang đầu có trang tiếp theo | Summary hướng dẫn page tiếp theo |
| Trang cuối | Không báo còn dữ liệu |
| Trang vượt quá cuối | Output rỗng với thông báo rõ |
| Tập dữ liệu rỗng | Không render bảng gây hiểu nhầm |
| Một ô có nội dung rất dài | Cell được rút gọn/wrap theo chính sách |
| Dữ liệu có newline/tab | Bảng không bị vỡ cấu trúc |
| Dataset lớn | Repository chỉ lấy page/cursor, không gọi `findAll()` |
| Terminal hẹp | Nội dung quan trọng vẫn đọc được |
| ShellTest output | Screen chỉ chứa số dòng theo chính sách |
| Export lớn | Dữ liệu được stream/batch và file hoàn tất mới được công bố |

Nên kiểm tra cả số bản ghi được truy vấn và số bản ghi được render. Nếu chỉ kiểm tra output, service vẫn có thể đang tải toàn bộ database rồi mới cắt list.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Terminal in hàng nghìn dòng | Command lấy toàn bộ dữ liệu và render trực tiếp | Phân trang với `page`/`size` hoặc cursor |
| Heap vẫn tăng dù chỉ in 10 dòng | Gọi `findAll()` rồi `subList()` | Đẩy giới hạn xuống repository/database |
| Test chạy chậm hoặc giữ output rất lớn | Fixture và command tạo quá nhiều dòng trong ShellTestClient | Dùng fixture nhỏ, kiểm tra paging riêng, chạy performance test độc lập |
| Bảng vẫn dài dù số row ít | Ô có nội dung dài hoặc nhiều newline | Rút gọn cell, escape newline và giới hạn cột |
| Người dùng nghĩ dữ liệu đã đầy đủ | Cắt output nhưng không thông báo | In số dòng hiển thị và hướng dẫn trang tiếp theo/export |
| Trang bị trùng hoặc thiếu bản ghi | Sort không ổn định hoặc dữ liệu thay đổi giữa các lần gọi | Dùng sort key duy nhất; cân nhắc cursor/keyset pagination |
| Trang sâu truy vấn chậm | Offset quá lớn | Chuyển sang cursor/keyset hoặc export theo batch |
| Table renderer vẫn render tất cả dòng | Giới hạn width bị hiểu nhầm là giới hạn row | Giới hạn model data trước khi gọi `render(width)` |
| Test pass ở 120 cột nhưng vỡ ở máy người dùng | Chỉ kiểm tra một kích thước terminal | Test thêm width/height hẹp và kiểm tra wrap |
| Export tạo file một phần nhưng báo thành công | Không kiểm tra lỗi ghi hoặc công bố file quá sớm | Ghi file tạm, xác minh hoàn tất rồi đổi tên |

## Quy trình triển khai

1. Xác định command chỉ để xem nhanh hay cần xuất toàn bộ dữ liệu.
2. Chọn page size mặc định và hard maximum dựa trên chiều cao terminal, số cột và độ dài ô.
3. Validate page/size; không âm thầm nhận một giới hạn quá lớn.
4. Thực hiện pagination tại repository/database hoặc API nguồn dữ liệu.
5. Dùng thứ tự ổn định; chọn cursor/keyset nếu offset lớn hoặc dữ liệu thay đổi thường xuyên.
6. Chỉ tạo `TableModel` từ trang dữ liệu đã giới hạn.
7. In summary về số dòng và trạng thái còn dữ liệu; cung cấp cú pháp xem trang kế tiếp.
8. Giới hạn độ dài ô và escape nội dung có thể phá cấu trúc bảng.
9. Dùng command export riêng để stream toàn bộ dữ liệu ra file.
10. Kiểm thử page boundary, hard maximum, output line count, terminal dimensions và truy vấn dữ liệu thực sự có giới hạn.

Giới hạn số dòng ở tầng truy vấn, model và output giúp command giữ được tốc độ, terminal dễ đọc và test có kích thước ổn định. Người dùng vẫn có thể tiếp cận toàn bộ dữ liệu qua pagination hoặc export mà không phải tải và in toàn bộ kết quả trong một lần.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 API — Table](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html): `Table.render(int totalAvailableWidth)` nhận chiều rộng khả dụng để render.
- [Spring Shell 4.0.3 API — TableModel](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModel.html): hợp đồng `getRowCount()`, `getColumnCount()` và `getValue(...)`.
- [Spring Shell 4.0.3 API — ArrayTableModel](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/ArrayTableModel.html): table model được tạo từ mảng hai chiều theo hàng.
- [Spring Shell 4.0.3 API — TableBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html): cấu hình formatter, sizing, wrapping và alignment cho bảng.
- [Spring Shell 3.4.3 API — TableModel](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/table/TableModel.html): hợp đồng table model trong package 3.x.
- [Spring Shell 3.4 — Testing Settings](https://docs.spring.io/spring-shell/reference/3.4/testing/settings.html): terminal giả lập mặc định 80x24 và cách cấu hình width/height trong test.
- [Spring Shell 4.0.3 API — ShellTestClient](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html): gửi command và nhận output màn hình trong test.
- [Spring Shell 4.0.3 API — ShellScreen](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellScreen.html): truy cập các dòng output qua `lines()`.
- [Spring Shell — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html): ghi output qua `CommandContext.outputWriter()` và flush writer.
