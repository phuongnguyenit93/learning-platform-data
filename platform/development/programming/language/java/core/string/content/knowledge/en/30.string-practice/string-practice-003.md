# Ghép báo cáo văn bản bằng `StringBuilder` hoặc `StringJoiner`

## Mục tiêu bài thực hành

Trong chương trình Java, báo cáo văn bản có thể gồm tiêu đề, các dòng dữ liệu, bảng căn cột, ghi chú, tổng cộng và danh sách tên hoặc trạng thái. Hai công cụ trong `java.lang` và `java.util` hỗ trợ các dạng ghép này:

- `StringBuilder` phù hợp khi bạn **xây dựng chuỗi theo nhiều bước**, xen kẽ văn bản cố định, các trường dữ liệu, điều kiện, tiêu đề, newline và những dòng được định dạng.
- `StringJoiner` phù hợp khi bạn **ghép một danh sách phần tử** bằng một dấu phân cách thống nhất, có thể thêm tiền tố (`prefix`) và hậu tố (`suffix`).

Sau bài học, bạn sẽ tự tạo báo cáo bán hàng có cột, số lượng và tổng tiền; tạo phần danh sách người phụ trách bằng `StringJoiner`; xử lý danh sách rỗng/`null`; kiểm soát newline, locale và escaping; cuối cùng chọn công cụ phù hợp với từng phần của báo cáo.

## 1. Hiểu vai trò của hai API

### `StringBuilder`: xây dựng nội dung theo thứ tự

`StringBuilder` giữ một dãy ký tự thay đổi được. Bạn có thể thêm giá trị bằng `append()`, chèn bằng `insert()`, thay đoạn bằng `replace()` hoặc chỉnh độ dài. `append()` trả về chính builder để viết chuỗi lời gọi:

```java
StringBuilder report = new StringBuilder();
report.append("BAO CAO").append('\n');
report.append("So muc: ").append(3).append('\n');
String result = report.toString();
```

`result` chứa:

```text
BAO CAO
So muc: 3
```

Trong ví dụ này, `'\n'` là xuống dòng LF có chủ đích. Nếu báo cáo là văn bản dùng nội bộ trên hệ điều hành hiện tại, bạn có thể dùng `System.lineSeparator()`; nếu báo cáo cần so sánh chính xác giữa các môi trường hoặc được truyền qua giao thức yêu cầu LF, hãy quy định rõ `"\n"`.

Builder có `length()` (số đơn vị mã UTF-16 đang chứa) và `capacity()` (khả năng chứa trước khi cần mở rộng). Nó **không tự căn cột**, tự thêm dấu phân cách giữa các phần tử hay tự escaping dữ liệu. Bạn phải viết quy tắc trình bày.

### `StringJoiner`: một phần tử, một dấu phân cách

`StringJoiner` có constructor:

```java
new StringJoiner(delimiter)
new StringJoiner(delimiter, prefix, suffix)
```

Ví dụ:

```java
import java.util.StringJoiner;

StringJoiner names = new StringJoiner(", ", "[", "]");
names.add("An").add("Binh").add("Chi");
System.out.println(names); // [An, Binh, Chi]
```

Dấu `", "` chỉ xuất hiện **giữa** các phần tử; không có dấu phẩy thừa ở cuối. `prefix` và `suffix` bao quanh toàn bộ kết quả. Đối tượng `StringJoiner` cũng có `length()`, `setEmptyValue()`, `merge()` và `toString()`.

`StringJoiner` thích hợp với tên thành viên, các nhãn, danh sách mã, một dòng CSV đã escaped từng trường, hoặc những dòng/bản ghi được tách bởi newline cố định. Nó không có API căn cột, tính tổng tiền hoặc tự quản lý các khối nội dung phức tạp.

### So sánh trước khi chọn

| Tiêu chí | `StringBuilder` | `StringJoiner` |
| --- | --- | --- |
| Đơn vị bổ sung | Một mẩu văn bản, số, ký tự hoặc đối tượng | Một phần tử dạng `CharSequence` |
| Dấu phân cách giữa các phần tử | Tự thêm bằng `append` hoặc điều kiện | Tự thêm khi `add` |
| Tiền tố/hậu tố cho cả danh sách | Tự ghép | Hỗ trợ ngay trong constructor |
| Báo cáo nhiều section, tiêu đề, dòng tổng | Linh hoạt và thường dễ đọc hơn | Có thể dùng cho từng danh sách trong section |
| Danh sách rỗng | Kết quả do logic của người viết quyết định | Có `setEmptyValue` |
| Căn cột/số/ngày | Kết hợp `String.format` hoặc `Formatter` | Định dạng phần tử trước khi gọi `add` |
| Đặt trước dung lượng | `new StringBuilder(initialCapacity)`, `ensureCapacity` | Không có constructor capacity công khai |
| An toàn khi nhiều luồng cùng chỉnh sửa | Không bảo đảm | Không bảo đảm |

Cả hai đều có thể tạo `String` cuối cùng. Đừng chọn công cụ theo giả định rằng một công cụ luôn nhanh hơn mọi trường hợp; cấu trúc dữ liệu và khối lượng ghép quyết định lựa chọn hợp lý.

## 2. Thiết kế đầu ra trước khi viết code

Giả sử báo cáo bán hàng cần những trường sau:

- Tiêu đề `BAO CAO BAN HANG`.
- Bảng có cột tên, số lượng, đơn giá, thành tiền.
- Mỗi dòng thành tiền bằng `quantity × unitPrice`.
- Tổng cộng của các dòng.
- Căn trái cho tên và căn phải cho số.
- Dấu chấm thập phân ổn định để ví dụ chạy giống nhau ở mọi máy.

Kết quả mong muốn:

```text
BAO CAO BAN HANG
-----------------
Ten       SL  Don gia Thanh tien
Sach       2    12.50      25.00
But        3     1.20       3.60
TONG: 28.60
```

Để số tiền có dạng thập phân chính xác, dùng `BigDecimal` thay vì dựa vào phép cộng `double` rồi hy vọng kết quả không gặp sai số biểu diễn nhị phân. Để định dạng số theo cách ổn định, dùng `Locale.ROOT`. Với ứng dụng thực tế, muốn hiển thị dấu phân nhóm hoặc ký hiệu tiền tệ theo quốc gia thì chọn locale theo yêu cầu sản phẩm.

## 3. Bài thực hành 1: báo cáo nhiều cột bằng `StringBuilder`

Lưu toàn bộ chương trình dưới tên **`SalesReportDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;

public class SalesReportDemo {
    record Sale(String name, int quantity, BigDecimal unitPrice) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Sach", 2, new BigDecimal("12.50")),
                new Sale("But", 3, new BigDecimal("1.20"))
        );

        StringBuilder report = new StringBuilder(256);
        report.append("BAO CAO BAN HANG\n");
        report.append("-----------------\n");
        report.append(String.format(
                Locale.ROOT,
                "%-8s %3s %8s %10s",
                "Ten", "SL", "Don gia", "Thanh tien"
        )).append('\n');

        BigDecimal total = BigDecimal.ZERO;

        for (Sale sale : sales) {
            BigDecimal amount = sale.unitPrice().multiply(
                    BigDecimal.valueOf(sale.quantity()));
            total = total.add(amount);

            report.append(String.format(
                    Locale.ROOT,
                    "%-8s %3d %8.2f %10.2f",
                    sale.name(),
                    sale.quantity(),
                    sale.unitPrice(),
                    amount
            )).append('\n');
        }

        report.append(String.format(
                Locale.ROOT, "TONG: %.2f", total)).append('\n');

        System.out.print(report.toString());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac SalesReportDemo.java
java SalesReportDemo
```

Stdout (nội dung các dòng):

```text
BAO CAO BAN HANG
-----------------
Ten       SL  Don gia Thanh tien
Sach       2    12.50      25.00
But        3     1.20       3.60
TONG: 28.60
```

### Giải thích từng điểm

**Mô hình dữ liệu.** `record Sale` chứa tên, số lượng và đơn giá. `BigDecimal` nhận từ chuỗi thập phân `"12.50"` và `"1.20"`; tránh khởi tạo giá trị tiền tệ từ literal `double` khi cần biểu diễn số thập phân đúng theo ý định.

**Tính toán độc lập với trình bày.** `amount` được tính bằng `unitPrice.multiply(BigDecimal.valueOf(quantity))`; `total` được cộng dồn dưới dạng `BigDecimal`. Bạn chỉ định dạng tiền thành chuỗi khi đưa vào báo cáo, để các phép tính sau đó vẫn thao tác trên số.

**Căn cột.** Trong `"%-8s %3d %8.2f %10.2f%n"`:

- `%-8s`: chuỗi căn trái, độ rộng tối thiểu 8.
- `%3d`: số nguyên căn phải, độ rộng tối thiểu 3.
- `%8.2f`: số thập phân căn phải, độ rộng tối thiểu 8, hiển thị hai chữ số sau dấu thập phân.
- `%10.2f`: số thập phân tương tự, độ rộng tối thiểu 10.
- Sau mỗi phần đã định dạng, `append('\n')` thêm một dấu xuống dòng LF thống nhất.

**Độ rộng chỉ là tối thiểu.** Nếu `sale.name()` dài hơn 8 đơn vị định dạng, Formatter không cắt ngắn nó mặc định mà mở rộng trường. Bảng có thể mất căn thẳng hàng khi dữ liệu thực tế dài, chứa emoji, ký tự kết hợp hoặc ký tự có độ rộng màn hình khác nhau. Các width của `Formatter` không phải phép tính độ rộng cột trực quan của mọi terminal; khi cần bảng Unicode chuẩn chỉnh, cần thêm chính sách giới hạn/escape/đo độ rộng hiển thị hoặc công cụ chuyên dụng.

**Dung lượng khởi tạo 256.** Đây là ước lượng, không phải giới hạn độ dài báo cáo. Nếu báo cáo vượt capacity, builder tự mở rộng. Đối với báo cáo nhỏ, constructor mặc định `new StringBuilder()` cũng thường đủ. Khi dữ liệu có tổng kích thước dự đoán được, ước lượng theo tổng `length()` của các phần và phần định dạng giúp giảm mở rộng; tránh tạo capacity quá lớn.

**Dấu xuống dòng.** Chương trình này dùng `'\n'` ở **tất cả các dòng**, bao gồm sau `String.format`. Vì vậy kết quả trong bộ nhớ có LF ổn định giữa Windows và Unix, thuận tiện cho kiểm thử hoặc tệp yêu cầu LF. Nếu báo cáo cho terminal theo quy tắc nền tảng, có thể chọn `%n` hoặc `System.lineSeparator()` một cách nhất quán, nhưng không trộn các kiểu newline trong cùng định dạng đầu ra.

### Khi nào dùng `Formatter` trực tiếp với builder?

`String.format(...)` tạo một `String` trung gian rồi `append` nó vào builder. Với báo cáo lớn có rất nhiều dòng, có thể dùng `Formatter` để định dạng trực tiếp vào một `StringBuilder`:

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder out = new StringBuilder(256);
try (Formatter formatter = new Formatter(out, Locale.ROOT)) {
    formatter.format("%-8s %3d%n", "Sach", 2);
    formatter.format("%-8s %3d%n", "But", 3);
}
String report = out.toString();
```

Đây là **đoạn minh họa**, không phải file Java độc lập; nó có thể đặt trong một phương thức. `Formatter` nhận builder như một `Appendable` và ghi trực tiếp vào đó. `StringBuilder` không bị đóng bởi `Formatter.close()` vì bản thân nó không phải resource có `close()`. Dù vậy, việc tránh `String` trung gian không tự bảo đảm chương trình nhanh hơn trong mọi workload; hãy đo nếu đây là đường chạy quan trọng.

## 4. Bài thực hành 2: danh sách, tiền tố và hậu tố với `StringJoiner`

Lưu thành **`JoinerReportDemo.java`**:

```java
import java.util.StringJoiner;

public class JoinerReportDemo {
    public static void main(String[] args) {
        StringJoiner people = new StringJoiner(", ", "Phu trach: ", ".");
        people.add("An").add("Binh").add("Chi");
        System.out.println(people);

        StringJoiner empty = new StringJoiner(", ", "Phu trach: ", ".");
        System.out.println("empty-default=" + empty);
        empty.setEmptyValue("Phu trach: (chua co).");
        System.out.println("empty-custom=" + empty);

        StringJoiner tasks = new StringJoiner(
                "\n", "MUC CONG VIEC\n", "\nKET THUC");
        tasks.add("1. Doc du lieu");
        tasks.add("2. Tao bao cao");
        System.out.println(tasks);
    }
}
```

Chạy:

```bash
javac JoinerReportDemo.java
java JoinerReportDemo
```

Stdout:

```text
Phu trach: An, Binh, Chi.
empty-default=Phu trach: .
empty-custom=Phu trach: (chua co).
MUC CONG VIEC
1. Doc du lieu
2. Tao bao cao
KET THUC
```

Khi chưa gọi `add()`, `StringJoiner` trả về `prefix + suffix` mặc định: trường hợp trên là `"Phu trach: ."`, dù chưa có người nào. `setEmptyValue` cho phép dùng một chuỗi thay thế **chỉ khi joiner vẫn trống**. Sau khi có phần tử, giá trị được tạo từ `prefix + elements-with-delimiter + suffix`; `setEmptyValue` không tự chèn phần tử.

`StringJoiner.length()` đo độ dài dạng chuỗi hiện tại, bao gồm prefix/suffix hoặc empty value tương ứng. Đừng dùng `StringJoiner.length() == 0` để xác nhận "chưa add phần tử": joiner chưa thêm phần tử nhưng có prefix/suffix vẫn có độ dài lớn hơn 0. Với luồng xử lý tự viết, bạn có thể giữ bộ đếm mục riêng nếu cần biết số phần tử.

### Mỗi phần tử có thể là một dòng đã định dạng

Nếu mỗi bản ghi được tạo trước thành một dòng `String` hoàn chỉnh, `StringJoiner("\n")` có thể nối các dòng mà không cần kiểm tra phần tử đầu/ cuối:

```java
StringJoiner rows = new StringJoiner("\n");
rows.add("Sach,2,25.00");
rows.add("But,3,3.60");

String body = rows.toString(); // hai dòng, không có newline sau dòng cuối
```

Ngược lại, với báo cáo nhiều section cần các ký tự khác nhau ở đầu/cuối từng khối hoặc các dòng tổng, `StringBuilder` thường làm cấu trúc hiển thị rõ hơn. Có thể **kết hợp**: `StringJoiner` sinh một dòng nhãn, rồi `StringBuilder` append dòng đó vào báo cáo chính.

## 5. Kết hợp cả hai trong một báo cáo

Một báo cáo có thể gồm: tiêu đề, nội dung chính, tổng cộng và danh sách người phụ trách. Sử dụng builder cho bố cục chung và joiner cho nhóm phần tử đồng nhất:

```java
import java.util.List;
import java.util.StringJoiner;

public class MixedReportDemo {
    public static void main(String[] args) {
        List<String> reviewers = List.of("An", "Binh", "Chi");
        StringJoiner reviewerList = new StringJoiner(", ");
        reviewers.forEach(reviewerList::add);

        StringBuilder report = new StringBuilder();
        report.append("BAO CAO\n");
        report.append("So nguoi duyet: ").append(reviewers.size()).append('\n');
        report.append("Nguoi duyet: ").append(reviewerList).append('\n');

        System.out.print(report);
    }
}
```

Chạy:

```bash
javac MixedReportDemo.java
java MixedReportDemo
```

Stdout:

```text
BAO CAO
So nguoi duyet: 3
Nguoi duyet: An, Binh, Chi
```

Ở đây `StringJoiner` loại bỏ nhu cầu tự theo dõi dấu phẩy giữa các tên; `StringBuilder` quyết định thứ tự section, nhãn và newline. Với một danh sách đơn giản đã có sẵn, `String.join(", ", reviewers)` còn ngắn gọn hơn, nhưng khi cần xây dựng từng phần tử, tiền tố/hậu tố hoặc giá trị đặc biệt cho danh sách trống, `StringJoiner` thường tiện hơn.

## 6. Phần tử `null`, dữ liệu rỗng và thứ tự đầu vào

### Giá trị `null` không tự động bị bỏ qua

`StringBuilder.append((String) null)` thêm văn bản `"null"`. `StringJoiner.add(null)` cũng thêm biểu diễn `"null"`. `String.join` với phần tử `null` có thể đưa chữ `"null"` vào kết quả. Đây là hành vi của API, không nhất thiết là cách ứng dụng muốn mô tả dữ liệu thiếu.

Thay vì mặc định in `null` trong báo cáo, hãy **đặt chính sách hiển thị**:

```java
String rawName = null;
String safeName = rawName == null ? "(khong co ten)" : rawName;

StringJoiner names = new StringJoiner(", ");
names.add(safeName);
```

Đây là đoạn minh họa trong một phương thức. Trong báo cáo nghiệp vụ, một giá trị thiếu có thể cần hiển thị `"N/A"`, để trống có chủ đích, hoặc gây lỗi validation; các lựa chọn này có ý nghĩa khác nhau.

Một phần tử rỗng `""` vẫn là **một phần tử đã được thêm**. Chẳng hạn joiner có phần tử rỗng và một phần tử `"B"` có thể trả về `", B"`. `setEmptyValue` không xử lý trường hợp đã `add("")`. Nếu muốn loại phần tử trống, lọc trước khi thêm:

```java
for (String name : namesFromInput) {
    if (name != null && !name.isBlank()) {
        joiner.add(name);
    }
}
```

Các biến `namesFromInput` và `joiner` được giả định đã khai báo. `isBlank()` khác `isEmpty()`: chuỗi toàn khoảng trắng Unicode cũng có thể được coi là blank. Không lọc khi vị trí trường rỗng có ý nghĩa, ví dụ trường thứ ba của một dòng CSV.

### Giữ thứ tự có ý nghĩa

`StringJoiner` tôn trọng thứ tự `add`. Nhưng nếu dữ liệu nguồn đến từ một collection không bảo đảm thứ tự như `HashSet` hoặc `HashMap`, báo cáo có thể có thứ tự khác nhau giữa các lần chạy. Khi yêu cầu báo cáo tái lập được, hãy sắp xếp hoặc dùng cấu trúc có thứ tự trước khi ghép; đừng kỳ vọng joiner tự sắp xếp.

Các giá trị dữ liệu được đưa trực tiếp vào báo cáo có thể chứa newline, tab hoặc dấu phân cách, khiến bố cục thay đổi. Nếu báo cáo được dùng để kiểm toán hoặc truyền dữ liệu có cấu trúc, hãy có chính sách escaping và validation rõ ràng.

## 7. Dấu phân cách không phải là escaping: ví dụ CSV

`StringJoiner(",")` chỉ thêm dấu phẩy giữa các phần tử. Nếu một trường chứa dấu phẩy, dấu ngoặc kép hoặc newline, việc `add(value)` nguyên xi **không tạo ra CSV hợp lệ**. Với CSV, mỗi ô phải được escaping theo quy tắc của định dạng: trường có dấu phẩy, ngoặc kép, LF hoặc CR nên được đặt trong ngoặc kép; ngoặc kép trong giá trị được nhân đôi.

Lưu chương trình **`CsvJoinerDemo.java`**:

```java
import java.util.StringJoiner;

public class CsvJoinerDemo {
    public static void main(String[] args) {
        String[] columns = {
                "An",
                "Ghi chu, quan trong",
                "Noi \"A\""
        };

        StringJoiner row = new StringJoiner(",");
        for (String value : columns) {
            row.add(csvCell(value));
        }

        System.out.println(row);
    }

    private static String csvCell(String value) {
        if (value == null) {
            return "";
        }

        boolean quote = value.indexOf(',') >= 0
                || value.indexOf('"') >= 0
                || value.indexOf('\n') >= 0
                || value.indexOf('\r') >= 0;

        if (!quote) {
            return value;
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
```

Chạy:

```bash
javac CsvJoinerDemo.java
java CsvJoinerDemo
```

Stdout:

```text
An,"Ghi chu, quan trong","Noi ""A"""
```

Trong ví dụ này, **escaping xảy ra trong `csvCell`**; `StringJoiner` chỉ nối những trường đã xử lý. Đây là phiên bản minh họa các quy tắc CSV phổ biến, không thay thế một thư viện CSV đã được kiểm chứng khi cần xử lý toàn bộ quy định định dạng, charset/BOM, các kiểu newline, quoting policy hoặc dữ liệu từ nguồn không tin cậy.

Tương tự, đừng tự xây dựng JSON bằng `StringBuilder.append("{\"name\":\"").append(value)...` khi có dữ liệu tùy ý; cần JSON serializer để xử lý dấu nháy, dấu gạch chéo và các ký tự điều khiển đúng quy tắc. Một bản báo cáo dễ đọc cho người xem và một payload dữ liệu có cấu trúc cần hợp đồng khác nhau.

## 8. Các lựa chọn định dạng ảnh hưởng kết quả báo cáo

### Quy ước newline và charset

Nếu kết quả chỉ in console, `System.out.print(report)` ghi nguyên chuỗi; `System.out.println(report)` thêm một newline ở cuối. Nếu báo cáo vốn đã kết thúc bằng newline, `println` có thể tạo một dòng trống không mong muốn. `%n` của `Formatter` dùng newline nền tảng, trong khi `"\n"` luôn là LF.

Khi ghi ra file text, nên chọn UTF-8 rõ ràng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("report.txt");
Files.writeString(path, report.toString(), StandardCharsets.UTF_8);
```

Đoạn trên là mã minh họa trong một phương thức có xử lý hoặc khai báo `IOException`. `report` được giả định đã có. Đầu nhận nên dùng cùng charset: `Files.readString(path, StandardCharsets.UTF_8)`. Ghi file không làm thay đổi nội dung `StringBuilder` ban đầu.

### Locale và số liệu

`String.format(Locale.ROOT, "%.2f", amount)` dùng kiểu hiển thị ổn định hơn cho ví dụ. Nếu báo cáo cho người dùng Việt Nam cần dấu nhóm, ký hiệu tiền và thông lệ địa phương, chọn `NumberFormat` hoặc `DecimalFormat` với locale thích hợp, đồng thời xác định rõ quy tắc làm tròn. Với báo cáo máy đọc, tốt nhất có giao thức tách biệt phần dữ liệu và phần hiển thị.

Với dữ liệu dạng bảng, `%-8s` chỉ quy định **chiều rộng tối thiểu của trường định dạng**, không phải độ rộng hiển thị chắc chắn của tiếng Việt, emoji hay tổ hợp ký tự. Nếu tên dài hơn cột, nó không bị cắt theo mặc định và có thể phá bố cục. Đừng coi bảng text căn cột là dữ liệu truyền không mơ hồ; nếu cần trao đổi giữa hệ thống, dùng CSV/JSON hoặc định dạng chuyên dụng.

### Giới hạn độ dài và dung lượng

Khi số dòng lớn, `StringBuilder` có thể phải mở rộng nhiều lần. Có thể ước lượng ban đầu theo số dòng và kích thước trung bình: `new StringBuilder(estimatedUnits)`, với `estimatedUnits` là số **đơn vị UTF-16**, không phải số byte UTF-8. Nếu không có ước lượng đáng tin, bắt đầu mặc định và chỉ tối ưu khi profiler/benchmark cho thấy cần thiết.

Không tạo toàn bộ báo cáo khổng lồ trong RAM nếu kích thước không được giới hạn. Với dữ liệu rất lớn, viết tuần tự ra `BufferedWriter` hoặc `OutputStream` sẽ phù hợp hơn. `StringBuilder` và `StringJoiner` phục vụ xây dựng một kết quả trong bộ nhớ; lựa chọn xuất trực tiếp là một bài toán tài nguyên khác.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tự `append(", ")` sau mọi phần tử | Dư dấu phẩy ở cuối | Dùng `StringJoiner` hoặc kiểm tra `i > 0` |
| Trộn `println`, `%n` và `\n` tùy tiện | Byte newline hoặc dòng trống không nhất quán | Quy định newline đầu ra một lần |
| Dùng `double` cho phép tính tiền quan trọng | Sai số nhị phân có thể tích lũy | Dùng `BigDecimal` và quy tắc làm tròn cụ thể |
| Tin rằng `StringJoiner` tự loại `null`/`""` | Xuất chữ `null` hoặc phần tử rỗng | Validate/lọc/ánh xạ theo chính sách |
| Ghép trường CSV chỉ bằng dấu phẩy | Dấu phẩy/ngoặc kép trong dữ liệu phá cấu trúc | Escape trường hoặc dùng thư viện CSV |
| Dùng dấu cách và `%8s` cho bảng Unicode tùy ý | Terminal có thể hiển thị lệch cột | Dùng chính sách đo/giới hạn chuỗi hoặc renderer bảng |
| Gọi `toString()` trong mỗi vòng lặp để nối tiếp | Tạo nhiều chuỗi trung gian | Giữ builder đến khi kết thúc |
| Không cố định thứ tự dữ liệu nguồn | Báo cáo thay đổi thứ tự ngoài ý muốn | Sắp xếp hoặc dùng collection có thứ tự |
| Dùng một builder được nhiều thread sửa đồng thời | Race condition, kết quả hỏng | Sở hữu riêng từng luồng/tác vụ hoặc đồng bộ thích hợp |

Cả `StringBuilder` lẫn `StringJoiner` đều là đối tượng mutable và **không thread-safe**. Với tác vụ tạo báo cáo độc lập, thường tốt nhất là tạo chúng như biến cục bộ trong phương thức. `StringBuffer` có các phương thức được đồng bộ hóa nhưng không tự giải quyết mọi logic truy cập đa bước; không cần chuyển sang nó khi không có nhu cầu chia sẻ.

## 10. Bài tập mở rộng

**Bài 1 — Chọn công cụ.** Một báo cáo chỉ cần dòng `"Tags: java, core, string"` từ danh sách tên tag động. Nên dùng công cụ nào? Nếu chưa có tag, cần hiển thị `"Tags: (trong)"` thì xử lý ra sao?

**Bài 2 — Báo cáo tổng hợp.** Bổ sung vào `SalesReportDemo` một cột `quantity` tổng cộng, rồi thêm dòng `"TONG SO LUONG: 5"` sau dòng tổng tiền. Giữ phép cộng số nguyên và tiền tệ riêng nhau.

**Bài 3 — Không mất vị trí cột.** Cho một mảng dữ liệu chứa `"A"`, `""` và `"C"`. Nếu đây là ba cột CSV, có nên lọc phần tử rỗng trước khi ghép không? Tại sao?

**Bài 4 — Thứ tự ổn định.** Danh sách tên lấy từ `HashSet`. Làm sao tạo chuỗi tag theo thứ tự từ điển để hai lần chạy cùng dữ liệu cho cùng kết quả?

**Bài 5 — Dự đoán chính xác đầu ra.** Đọc code:

```java
StringJoiner j = new StringJoiner(" | ", "<", ">");
System.out.println(j);
j.setEmptyValue("(empty)");
System.out.println(j);
j.add("x").add("y");
System.out.println(j);
```

Đáp án theo thứ tự:

```text
<>
(empty)
<x | y>
```

**Gợi ý:** (1) `StringJoiner(", ", "Tags: ", "")`; muốn hiển thị riêng trạng thái rỗng, gọi `setEmptyValue("Tags: (trong)")`. (2) Duy trì biến `int quantityTotal` và cập nhật trong vòng lặp. (3) Không, vì trường rỗng có vị trí hợp lệ và phải được giữ. (4) Sao chép sang `List` rồi `sort` hoặc dùng nguồn đã có thứ tự; xác định comparator phù hợp. (5) `setEmptyValue` chỉ tác động khi chưa thêm phần tử.

### Tài liệu tham khảo

- [`StringBuilder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`StringJoiner` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [`Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
- [`BigDecimal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
