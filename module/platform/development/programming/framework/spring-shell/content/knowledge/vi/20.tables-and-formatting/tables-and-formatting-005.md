# Chia dòng, cắt gọn hoặc phân trang theo quyết định của ứng dụng

Một bảng CLI thường phải hiển thị dữ liệu có độ dài rất khác nhau. Mã đơn hàng ngắn, tên khách hàng có thể dài, còn mô tả hoặc địa chỉ có thể chiếm nhiều dòng. Nếu mọi cột đều giữ chiều rộng theo nội dung dài nhất, bảng dễ vượt khỏi màn hình. Nếu cắt mọi giá trị theo một giới hạn chung, người dùng có thể mất thông tin quan trọng.

Spring Shell 3.3 cung cấp API bảng trong package `org.springframework.shell.table` để định dạng dữ liệu theo chiều rộng terminal. Ứng dụng có thể chọn cách chia dòng theo dấu phân cách, đặt chiều rộng cố định hoặc cung cấp `TextWrapper` riêng để cắt gọn nội dung. Với tập dữ liệu lớn, phân trang là quyết định ở tầng ứng dụng hoặc service: API bảng nhận một `TableModel` để hiển thị, còn ứng dụng quyết định lấy trang nào và bao nhiêu dòng.

Bài này tập trung vào bốn chiến lược:

- **Chia dòng (wrap):** giữ toàn bộ nội dung và hiển thị thành nhiều dòng trong cùng ô.
- **Cắt gọn (truncate):** giới hạn chiều rộng và thay phần bị bỏ bằng dấu ba chấm hoặc ký hiệu khác.
- **Không chia dòng (no-wrap):** giữ nội dung trên một dòng; chỉ phù hợp khi cột có giá trị ngắn hoặc bảng đủ rộng.
- **Phân trang (pagination):** lấy một phần bản ghi theo trang, hiển thị vị trí hiện tại và cho phép người dùng yêu cầu trang tiếp theo.

Sau bài này, bạn có thể:

- Hiểu quy trình định dạng, tính chiều rộng, chia dòng và căn chỉnh của Spring Shell Table.
- Dùng `AutoSizeConstraints` và `DelimiterTextWrapper` để chia dòng theo từ.
- Chọn một cột bằng `CellMatchers` và áp dụng chiến lược riêng.
- Dùng `AbsoluteWidthSizeConstraints` để giới hạn chiều rộng cột.
- Dùng `NoWrapSizeConstraints` khi cần giữ nguyên dòng.
- Tự triển khai `TextWrapper` để cắt gọn và thêm dấu ba chấm.
- Phân trang dữ liệu ở service và hiển thị trang hiện tại trong command.
- Chọn kích thước trang hợp lý và xử lý trang rỗng hoặc trang vượt giới hạn.

> Các ví dụ sử dụng API bảng Spring Shell 3.3.x. Không nhầm API bảng legacy trong `org.springframework.shell.table` với package table của Spring Shell 4.x.

## 1. Spring Shell định dạng bảng theo những bước nào?

`Table` được tạo từ `TableModel` chứa dữ liệu thô. Khi render, framework áp dụng các chiến lược theo thứ tự:

1. **Formatter:** chuyển giá trị thành văn bản. Ví dụ, số được định dạng theo locale hoặc map được chuyển thành các dòng key-value.
2. **Size constraints:** tính chiều rộng phù hợp cho từng ô/cột dựa trên dữ liệu và chiều rộng tổng.
3. **Text wrapper:** chia dòng hoặc cắt nội dung theo chiều rộng đã tính.
4. **Aligner:** căn lề ngang và dọc để các ô tạo thành bảng dễ đọc.

Các bước có thể được tùy chỉnh theo từng cell bằng `CellMatcher`. Ví dụ, cột mô tả có thể được chia dòng trong khi cột ID được giữ trên một dòng hoặc cắt gọn.

~~~mermaid
flowchart TD
    A[TableModel: dữ liệu thô] --> B[Formatter]
    B --> C[SizeConstraints]
    C --> D[TextWrapper]
    D --> E[Aligner]
    E --> F[Table.render: chuỗi bảng]
    G[CellMatcher] -.-> B
    G -.-> C
    G -.-> D
    G -.-> E
~~~

`TableBuilder` mặc định dùng `toString()` để định dạng, cố gắng sử dụng chiều rộng có sẵn, chia dòng tại dấu cách và căn trái. Đây là lựa chọn hợp lý cho bảng đơn giản. Khi dữ liệu có cột dài hoặc nhiều loại giá trị, nên chỉ định chiến lược cho những cột cần cách xử lý khác.

## 2. Chọn chiến lược theo loại dữ liệu

| Dữ liệu | Chiến lược thường phù hợp | Lý do |
|---|---|---|
| Mô tả, ghi chú, địa chỉ | Wrap | Người dùng cần đọc toàn bộ nội dung |
| ID, mã đơn hàng, mã giao dịch | No-wrap hoặc truncate | Giá trị thường cần được nhận diện nhanh và không nên bị tách tùy tiện |
| URL, token tham chiếu dài | Truncate hoặc hiển thị riêng | Một chuỗi dài không có dấu cách có thể làm cột tràn |
| Ngày giờ, trạng thái, số lượng | No-wrap | Giá trị ngắn, cấu trúc ổn định |
| Danh sách hàng trăm hoặc hàng nghìn dòng | Pagination | Giữ output gọn và giảm lượng dữ liệu cần truy vấn |
| Nội dung nhiều dòng có cấu trúc | Wrap tùy chỉnh | Cần giữ ranh giới dòng hoặc dấu phân cách riêng |

Hãy cân nhắc mức độ quan trọng của phần nội dung bị ẩn. Mô tả có thể chia thành nhiều dòng; mã định danh nếu bị cắt thì cần có cách xem giá trị đầy đủ, chẳng hạn command `customer show --id ...`. Với dữ liệu cần sao chép chính xác, không nên chỉ hiển thị một chuỗi đã bị rút gọn.

## 3. Chia dòng theo từ với DelimiterTextWrapper

`DelimiterTextWrapper` triển khai `TextWrapper` và chia nội dung tại ranh giới từ. Mặc định, dấu phân cách là khoảng trắng. Có thể truyền một ký tự khác nếu nội dung có quy ước phân tách phù hợp.

Ví dụ dữ liệu:

~~~text
ID    Tên       Mô tả
101   Hoa       Khách hàng đăng ký gói dịch vụ doanh nghiệp và cần hỗ trợ nhập dữ liệu ban đầu
102   Minh      Đang chờ xác nhận thanh toán
~~~

Khi chiều rộng cột mô tả bị giới hạn, nội dung có thể được hiển thị thành nhiều dòng thay vì kéo cả bảng rộng ra:

~~~text
+-----+-------+------------------------------+
| ID  | Tên   | Mô tả                        |
+-----+-------+------------------------------+
| 101 | Hoa   | Khách hàng đăng ký gói dịch  |
|     |       | vụ doanh nghiệp và cần hỗ    |
|     |       | trợ nhập dữ liệu ban đầu     |
| 102 | Minh  | Đang chờ xác nhận thanh toán |
+-----+-------+------------------------------+
~~~

Ví dụ cấu hình một cột:

~~~java
import org.springframework.shell.table.AbsoluteWidthSizeConstraints;
import org.springframework.shell.table.ArrayTableModel;
import org.springframework.shell.table.CellMatchers;
import org.springframework.shell.table.DelimiterTextWrapper;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;

Object[][] rows = {
        {"ID", "Tên", "Mô tả"},
        {"101", "Hoa",
                "Khách hàng đăng ký gói dịch vụ doanh nghiệp và cần hỗ trợ nhập dữ liệu ban đầu"},
        {"102", "Minh", "Đang chờ xác nhận thanh toán"}
};

TableBuilder builder = new TableBuilder(new ArrayTableModel(rows));

builder.on(CellMatchers.column(2))
        .addSizer(new AbsoluteWidthSizeConstraints(30))
        .addWrapper(new DelimiterTextWrapper())
        .and();

Table table = builder.build();
String rendered = table.render(70);
~~~

Chỉ số cột trong ví dụ bắt đầu từ 0: cột 0 là ID, cột 1 là Tên và cột 2 là Mô tả. `AbsoluteWidthSizeConstraints(30)` đặt chiều rộng cột mô tả là 30 ký tự; `DelimiterTextWrapper` chia nội dung theo dấu cách và trả về các dòng đã đệm đủ chiều rộng.

`Table.render(70)` yêu cầu render trong chiều rộng tổng 70. Ứng dụng nên lấy chiều rộng terminal thực tế hoặc chọn giới hạn phù hợp với môi trường chạy; nếu đặt chiều rộng lớn hơn terminal, bảng vẫn có thể tràn màn hình.

### Chia theo dấu phân cách khác

Với nội dung có dấu gạch nối, có thể cấu hình:

~~~java
new DelimiterTextWrapper('-')
~~~

Điều này hữu ích với mã hoặc chuỗi có cấu trúc theo dấu gạch nối. Hãy chọn delimiter mà việc ngắt tại đó không làm mất ý nghĩa dữ liệu. Không nên chia tùy tiện một mã định danh mà người dùng cần sao chép nguyên vẹn.

### Giới hạn của wrap theo từ

`DelimiterTextWrapper` chia tại ranh giới từ. Một token không có dấu cách, chẳng hạn URL dài hoặc mã hash, có thể không được chia như mô tả thông thường. Với nội dung đó, hãy chọn delimiter phù hợp, cắt gọn bằng wrapper riêng hoặc hiển thị chi tiết ở một command khác.

## 4. Chọn cell hoặc cột bằng CellMatchers

`CellMatchers` cung cấp các matcher thường dùng:

| Matcher | Phạm vi |
|---|---|
| `CellMatchers.table()` | Tất cả ô |
| `CellMatchers.column(2)` | Mọi ô trong cột có chỉ số 2 |
| `CellMatchers.row(0)` | Mọi ô trong dòng có chỉ số 0 |
| `CellMatchers.at(1, 2)` | Một ô tại dòng 1, cột 2 |
| `CellMatchers.ofType(String.class)` | Ô có giá trị thuộc kiểu được chỉ định |

Ví dụ: giữ hàng tiêu đề theo chiều rộng tự nhiên, còn cột mô tả có giới hạn:

~~~java
TableBuilder builder = new TableBuilder(new ArrayTableModel(rows));

builder.on(CellMatchers.column(2))
        .addSizer(new AbsoluteWidthSizeConstraints(30))
        .addWrapper(new DelimiterTextWrapper())
        .and();

builder.on(CellMatchers.row(0))
        .addSizer(new NoWrapSizeConstraints())
        .and();
~~~

Một matcher có thể được dùng để thêm formatter, sizer, wrapper hoặc aligner. Khi nhiều matcher cùng áp dụng lên một ô, hãy kiểm tra thứ tự và sự tương thích của các chiến lược. Ví dụ, wrapper có thể chia nội dung thành nhiều dòng trong khi aligner quyết định cách căn các dòng đó trong ô.

## 5. Không chia dòng với NoWrapSizeConstraints

`NoWrapSizeConstraints` tính chiều rộng dựa trên dòng dài nhất của ô. Chiến lược này giữ nguyên một dòng, không cố ép cột vào khoảng nhỏ bằng cách chia tại dấu cách.

Ví dụ:

~~~java
builder.on(CellMatchers.column(0))
        .addSizer(new NoWrapSizeConstraints())
        .and();
~~~

No-wrap phù hợp với cột có giá trị ngắn và ổn định như trạng thái, mã ngắn hoặc số lượng. Nếu cột có chuỗi dài, chiều rộng tự nhiên có thể làm toàn bộ bảng rộng hơn terminal.

`NoWrapSizeConstraints` là chiến lược tính kích thước; nó không phải cơ chế phân trang và cũng không tự cắt nội dung. Nếu muốn giới hạn chiều rộng nhưng không chia dòng, cần dùng chiều rộng cố định cùng một `TextWrapper` có hành vi cắt gọn.

## 6. Cắt gọn với chiều rộng cố định và TextWrapper riêng

Spring Shell cung cấp interface `TextWrapper` để tùy chỉnh cách chia hoặc cắt văn bản theo chiều rộng ô. Trong các wrapper tích hợp của package bảng 3.3, `DelimiterTextWrapper` chia theo ranh giới từ và `KeyValueTextWrapper` hỗ trợ định dạng key-value. Nếu cần dấu ba chấm, có thể triển khai wrapper riêng.

Ví dụ sau cắt từng dòng theo chiều rộng cột và thêm dấu `...`. Đoạn minh họa dùng chuỗi ASCII để phép đo bằng `String.length()` dễ hiểu:

~~~java
import java.util.Arrays;
import org.springframework.shell.table.TextWrapper;

public class EllipsisTextWrapper implements TextWrapper {

    @Override
    public String[] wrap(String[] original, int columnWidth) {
        if (columnWidth < 1) {
            throw new IllegalArgumentException("columnWidth phải lớn hơn 0.");
        }

        return Arrays.stream(original)
                .map(line -> {
                    String value = line == null ? "" : line;
                    if (value.length() > columnWidth) {
                        value = columnWidth <= 3
                                ? value.substring(0, columnWidth)
                                : value.substring(0, columnWidth - 3) + "...";
                    }
                    return value + " ".repeat(columnWidth - value.length());
                })
                .toArray(String[]::new);
    }
}
~~~

Áp dụng wrapper:

~~~java
builder.on(CellMatchers.column(1))
        .addSizer(new AbsoluteWidthSizeConstraints(18))
        .addWrapper(new EllipsisTextWrapper())
        .and();
~~~

`AbsoluteWidthSizeConstraints(18)` cấp chiều rộng 18 cho cột; wrapper giữ mỗi dòng đúng chiều rộng đó và thay phần dư bằng `...`. Ví dụ này minh họa một chính sách cắt đơn giản; trong ứng dụng thực tế, có thể thay dấu ba chấm hoặc bổ sung cách hiển thị toàn bộ giá trị.

### Lưu ý về Unicode và độ rộng terminal

`String.length()` đếm đơn vị UTF-16, không phải số cột hiển thị trên terminal. Chữ có dấu tổ hợp, emoji, ký tự Đông Á và ký tự có độ rộng kép có thể làm phép cắt theo độ dài chuỗi lệch khỏi chiều rộng thực tế. Đoạn code trên phù hợp để minh họa với dữ liệu ASCII. Với dữ liệu tiếng Việt hoặc Unicode nói chung, hãy dùng phép đo độ rộng hiển thị theo terminal và cắt ở ranh giới code point/grapheme; không cắt giữa surrogate pair hoặc cụm ký tự kết hợp.

Nếu giá trị cần chính xác tuyệt đối, hãy hiển thị một phần để nhận diện và cung cấp command chi tiết để xem toàn bộ nội dung.

## 7. Phân biệt wrap, truncate và no-wrap

| Chiến lược | Giữ đủ nội dung? | Giữ một dòng? | Nguy cơ chính |
|---|---:|---:|---|
| Wrap | Có | Không | Bảng cao hơn, người dùng phải đọc nhiều dòng |
| Truncate | Không | Có | Nội dung bị ẩn; cần cách xem đầy đủ |
| No-wrap | Có | Có | Cột dài có thể làm bảng tràn chiều rộng |

Có thể kết hợp các chiến lược trong cùng bảng:

- ID: truncate hoặc no-wrap nếu độ dài được giới hạn.
- Tên: wrap hoặc truncate theo yêu cầu hiển thị.
- Mô tả: wrap để giữ toàn bộ nội dung.
- Trạng thái: no-wrap.
- Đường dẫn: truncate, kèm command `file show --path ...` để xem đầy đủ.

Không nên dùng wrap cho mọi cột. Một dòng mô tả có thể chia tốt ở dấu cách, nhưng ID hoặc URL bị chia giữa chừng sẽ khó sao chép và nhận diện.

## 8. Phân trang là trách nhiệm của ứng dụng

API bảng Spring Shell 3.3 tập trung vào mô hình dữ liệu và render theo chiều rộng. `TableModel` cung cấp số dòng, số cột và giá trị của từng ô; `Table.render(width)` tạo chuỗi bảng. API này không tự quyết định trang dữ liệu hiện tại, không truy vấn database theo offset và không cung cấp điều khiển trang tiếp theo.

Ứng dụng cần chọn trang trước khi tạo `TableModel`:

~~~mermaid
flowchart TD
    A[Người dùng gọi orders --page 0 --size 20] --> B[Command kiểm tra page và size]
    B --> C[Service truy vấn dữ liệu của trang]
    C --> D[Trả items và totalElements]
    D --> E[Tạo TableModel từ items]
    E --> F[Render bảng]
    F --> G[Hiển thị trang hiện tại và tổng số trang]
    G --> H[Người dùng yêu cầu trang tiếp theo]
    H --> A
~~~

Ví dụ command:

~~~text
orders list --page 0 --size 20
orders list --page 1 --size 20
orders list --page 2 --size 20
~~~

Trong ví dụ này, page bắt đầu từ 0. Trang 0 chứa các mục đầu tiên, trang 1 chứa nhóm tiếp theo. Cần ghi rõ quy ước này trong help của command để người dùng không nhầm với cách đánh số trang bắt đầu từ 1.

### Giới hạn kích thước trang

Không nên để người dùng yêu cầu kích thước tùy ý. Ví dụ:

- Mặc định 20 dòng.
- Tối thiểu 1 dòng.
- Tối đa 100 dòng.

Giới hạn này bảo vệ thời gian truy vấn và kích thước output. Mức cụ thể tùy vào độ rộng mỗi dòng, chi phí lấy dữ liệu và môi trường terminal.

## 9. Truy vấn trang ở service thay vì tải toàn bộ dữ liệu

Với dữ liệu nhỏ đã có trong bộ nhớ, ứng dụng có thể dùng `subList` để lấy một phần danh sách. Với bảng lớn, hãy truyền page/size xuống service và để database trả đúng phần dữ liệu cần hiển thị. Không tải hàng chục nghìn bản ghi về JVM chỉ để cắt ra 20 dòng.

Một hợp đồng service đơn giản:

~~~java
import java.util.List;

public record PageResult<T>(
        List<T> items,
        long totalElements,
        int page,
        int size) {

    public long totalPages() {
        return totalElements == 0
                ? 0
                : totalElements / size + (totalElements % size == 0 ? 0 : 1);
    }
}
~~~

Service:

~~~java
public interface OrderQueryService {
    PageResult<Order> findOrders(int page, int size);
}
~~~

Service cần truy vấn database với offset/limit hoặc cơ chế cursor, sau đó trả đúng các dòng của trang cùng tổng số bản ghi phù hợp.

Command kiểm tra đầu vào và hiển thị thông tin trang:

~~~java
@ShellMethod(key = "orders list", value = "Liệt kê đơn hàng theo trang.")
public String list(
        @ShellOption(value = "--page", defaultValue = "0") int page,
        @ShellOption(value = "--size", defaultValue = "20") int size) {

    if (page < 0) {
        throw new IllegalArgumentException("page phải lớn hơn hoặc bằng 0.");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size phải nằm trong khoảng 1 đến 100.");
    }

    PageResult<Order> result = orderService.findOrders(page, size);
    String table = orderTableRenderer.render(result.items());
    if (result.totalElements() == 0) {
        return "Không có đơn hàng phù hợp.";
    }
    if (result.items().isEmpty()) {
        return "Trang được yêu cầu vượt quá trang cuối. Tổng số trang: "
                + result.totalPages();
    }

    return table + System.lineSeparator()
            + "Trang " + (result.page() + 1)
            + " / " + result.totalPages()
            + " — tổng " + result.totalElements() + " đơn hàng";
}
~~~

`orderTableRenderer` chịu trách nhiệm tạo bảng từ danh sách trang hiện tại. Khi `totalElements` bằng 0, hiển thị thông báo không có dữ liệu; khi `page` vượt quá trang cuối, có thể trả trang rỗng kèm tổng số trang hoặc báo người dùng chọn trang hợp lệ.

### Offset pagination và cursor pagination

Offset pagination phù hợp với danh sách thông thường và cho phép người dùng yêu cầu trực tiếp trang số N. Với dữ liệu rất lớn hoặc thay đổi liên tục, offset cao có thể tốn chi phí và kết quả có thể dịch chuyển giữa các lần truy vấn.

Cursor pagination dùng một khóa ổn định, chẳng hạn `createdAt` kết hợp `id`, để lấy các bản ghi sau mục cuối của trang trước. Nó phù hợp với luồng dữ liệu liên tục hoặc danh sách lớn, nhưng thường không hỗ trợ nhảy thẳng tới trang số N. Command có thể nhận `--after <cursor>` hoặc trả cursor kế tiếp cho người dùng.

Chọn phương pháp theo cách người dùng duyệt dữ liệu. Không nên mặc định phân trang luôn là offset/limit nếu tập dữ liệu rất lớn hoặc thường xuyên thay đổi.

## 10. Phân trang tương tác và script

Trong interactive shell, có thể thiết kế command `orders browse` để hiển thị từng trang rồi hỏi người dùng:

~~~text
Trang 1 / 8
Hiển thị 20 đơn hàng

[n] Trang tiếp theo  [p] Trang trước  [q] Thoát
~~~

Với command chạy non-interactive hoặc được gọi từ script, không nên chờ phím bấm. Hãy nhận page/size qua option và trả kết quả của đúng trang. Cách này dễ tự động hóa:

~~~text
orders list --page 0 --size 50
orders list --page 1 --size 50
~~~

Nếu cần xuất toàn bộ dữ liệu, cung cấp command export riêng ghi ra CSV/JSON hoặc file khác. Không bắt người dùng tăng page size lên một giá trị rất lớn để lấy toàn bộ kết quả trong một lần.

## 11. Xử lý bảng rộng và dữ liệu dài

Ngay cả khi wrap hoặc truncate đúng, tổng chiều rộng của tất cả cột cộng border vẫn có thể vượt chiều rộng terminal. Một số cách giảm chiều rộng:

- Bỏ cột ít quan trọng khỏi bảng mặc định.
- Chỉ hiển thị các cột cần thiết cho thao tác hiện tại.
- Rút gọn tên header nhưng giữ nhãn dễ hiểu.
- Dùng chiều rộng cố định cho cột dài và wrap/truncate phù hợp.
- Cung cấp option `--columns` nếu người dùng cần chọn cột.
- Tạo command `show` để xem chi tiết một bản ghi.

Không nên cố nhồi mọi thuộc tính của entity vào một bảng. Bảng danh sách giúp so sánh nhanh; màn hình chi tiết hoặc command riêng giúp đọc nội dung dài.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Một cột làm bảng quá rộng | Dùng no-wrap hoặc chiều rộng tự động theo giá trị dài nhất | Đặt width, wrap hoặc truncate cho cột đó |
| Mô tả bị cắt giữa từ | Dùng wrapper không phù hợp hoặc cắt theo ký tự | Dùng `DelimiterTextWrapper` với dấu cách |
| URL không chia dòng | URL không có dấu cách | Dùng delimiter khác, wrapper cắt gọn hoặc command xem chi tiết |
| Bảng bị tràn dù từng cột đã giới hạn | Tổng chiều rộng cột, border và padding vượt terminal | Giảm số cột hoặc tính lại tổng width |
| Dấu ba chấm làm lệch cột | Wrapper không trả dòng có đúng `columnWidth` | Tuân thủ hợp đồng `TextWrapper.wrap()` và đệm khoảng trắng |
| Ký tự tiếng Việt/emoji bị cắt sai | `String.length()` không bằng độ rộng hiển thị terminal | Cắt theo display width và ranh giới code point/grapheme |
| Command tải quá nhiều bản ghi | Phân trang sau khi tải toàn bộ danh sách | Đẩy page/size xuống repository hoặc dùng cursor |
| Trang cuối hiển thị rỗng bất ngờ | Page index vượt tổng số trang hoặc dữ liệu thay đổi | Kiểm tra tổng số trang và xử lý trang vượt giới hạn |
| Dữ liệu trùng hoặc thiếu giữa các trang | Sắp xếp không ổn định khi dùng offset | Dùng thứ tự có khóa duy nhất hoặc cursor |
| Script bị dừng để chờ chọn trang | Command dùng prompt tương tác | Nhận page/size qua option trong non-interactive mode |

## 13. Checklist lựa chọn

- Xác định người dùng cần đọc đầy đủ hay chỉ nhận diện nhanh giá trị.
- Dùng wrap cho mô tả và nội dung có thể chia theo từ.
- Dùng no-wrap cho cột ngắn, có độ dài ổn định.
- Dùng truncate cho ID/URL dài khi có cách xem chi tiết.
- Giới hạn chiều rộng cột bằng `AbsoluteWidthSizeConstraints` khi cần.
- Dùng `CellMatchers` để áp dụng chiến lược riêng cho từng cột/ô.
- Bảo đảm wrapper trả các dòng có chiều rộng đúng theo hợp đồng.
- Tính cả border và khoảng đệm khi chọn chiều rộng tổng.
- Đẩy phân trang xuống service/database cho tập dữ liệu lớn.
- Đặt giới hạn page size và xử lý trang rỗng/vượt giới hạn.
- Dùng thứ tự sắp xếp ổn định khi phân trang.
- Cung cấp cách xuất toàn bộ dữ liệu nếu người dùng cần xử lý ngoài terminal.
- Kiểm tra Unicode và độ rộng hiển thị trên terminal mục tiêu.

## 14. Bài tập thực hành

Tạo command `orders list` hiển thị danh sách đơn hàng:

1. Bắt đầu với các cột ID, khách hàng, trạng thái và mô tả.
2. Dùng `ArrayTableModel` và `TableBuilder` để dựng bảng.
3. Cấu hình cột mô tả rộng 30 ký tự và dùng `DelimiterTextWrapper`.
4. Cấu hình cột ID rộng 14 ký tự với một `TextWrapper` cắt gọn có dấu ba chấm.
5. Thử `NoWrapSizeConstraints` trên cột trạng thái và quan sát khi dữ liệu dài hơn dự kiến.
6. Thêm `--page` mặc định 0 và `--size` mặc định 20, giới hạn size tối đa 100.
7. Đẩy page/size xuống service để database chỉ trả các dòng của trang cần hiển thị.
8. Hiển thị số trang hiện tại, tổng số trang và tổng số đơn hàng.
9. Kiểm tra trường hợp không có dữ liệu, trang cuối ít dòng và page vượt giới hạn.
10. Chạy command trong interactive shell và qua script để xác nhận không có prompt chặn chế độ tự động.
11. Thử dữ liệu có dấu tiếng Việt, emoji và URL dài; ghi lại điểm cần xử lý theo display width.

Khi hoàn thành, giải thích vì sao wrap, truncate và pagination là ba quyết định khác nhau, và vì sao pagination nên được áp dụng trước khi tạo `TableModel`.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Package org.springframework.shell.table](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/package-summary.html): các thành phần xây dựng và render bảng.
- [Spring Shell 3.3 – TableBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TableBuilder.html): cấu hình formatter, sizer, wrapper, aligner và border.
- [Spring Shell 3.3 – Table API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/Table.html): render bảng theo chiều rộng tổng.
- [Spring Shell 3.3 – TextWrapper API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TextWrapper.html): hợp đồng chia dòng hoặc cắt nội dung theo chiều rộng ô.
- [Spring Shell 3.3 – DelimiterTextWrapper API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/DelimiterTextWrapper.html): chia dòng tại ranh giới từ hoặc delimiter chỉ định.
- [Spring Shell 3.3 – SizeConstraints API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/SizeConstraints.html): chiến lược tính kích thước cột.
- [Spring Shell 3.3 – AutoSizeConstraints API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/AutoSizeConstraints.html): tự tính chiều rộng theo ranh giới dấu cách.
- [Spring Shell 3.3 – AbsoluteWidthSizeConstraints API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/AbsoluteWidthSizeConstraints.html): cố định chiều rộng theo số ký tự.
- [Spring Shell 3.3 – NoWrapSizeConstraints API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/NoWrapSizeConstraints.html): chọn chiều rộng theo dòng dài nhất.
- [Spring Shell 3.3 – CellMatchers API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/CellMatchers.html): chọn cell, dòng, cột hoặc kiểu dữ liệu để áp dụng tùy chỉnh.
- [Spring Shell 3.3 – TableModel API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/table/TableModel.html): hợp đồng dữ liệu mà bảng sử dụng khi render.
