# Phân tích dữ liệu văn bản bằng Scanner và xuất báo cáo bằng Formatter

## 1. Bài toán: từ dòng văn bản đến một báo cáo có kiểm chứng

Ta nhận dữ liệu bán hàng ở dạng văn bản, mỗi dòng mô tả một mặt hàng trong một lần ghi nhận:

```text
PEN 3 12.50
BOOK 2 45.00
```

Mục tiêu:

1. Dùng `Scanner` để tách dòng và đọc các trường có kiểu.
2. Kiểm tra đủ trường, đúng định dạng và đúng giới hạn dữ liệu.
3. Giữ riêng dòng hợp lệ và lỗi, kèm số dòng gốc.
4. Tính tổng số lượng và tổng giá trị từ các dòng hợp lệ.
5. Dùng `Formatter` để tạo bảng có căn cột và định dạng số thống nhất.
6. Đọc được từ chuỗi mẫu hoặc tệp UTF-8 mà không sửa logic phân tích.

Luồng xử lý:

```text
Nguồn văn bản
    ↓ Scanner đọc từng dòng
Bỏ dòng trống / chú thích toàn dòng
    ↓ Scanner đọc từng trường của một dòng
Kiểm tra toàn bộ dòng
    ├── hợp lệ → đối tượng dữ liệu → tính toán
    └── sai    → thông báo lỗi có số dòng
    ↓
Formatter tạo báo cáo
```

Điểm quan trọng: dữ liệu phải được kiểm tra trước khi tính vào tổng. Việc in được một bảng đẹp không chứng minh dữ liệu đầu vào đã được đọc đúng.

## 2. Định nghĩa định dạng trước khi viết parser

Định dạng bài thực hành là văn bản phân tách bằng khoảng trắng, **không phải CSV**:

```text
CODE QUANTITY UNIT_PRICE
```

| Trường/quy tắc | Hợp đồng của ví dụ |
| --- | --- |
| CODE | 1–12 ký tự ASCII: bắt đầu bằng A–Z, tiếp theo là A–Z, 0–9, dấu gạch dưới hoặc gạch ngang |
| QUANTITY | Số nguyên dương, không có dấu hay dấu phân nhóm, tối đa 1.000.000 |
| UNIT_PRICE | Không âm, có 1–7 chữ số phần nguyên và tối đa 2 chữ số sau dấu chấm |
| Khoảng trắng | Một hoặc nhiều khoảng trắng/tab được dùng để tách trường |
| Dòng trống | Bỏ qua |
| Chú thích | Dòng sau khi bỏ khoảng trắng đầu/cuối bắt đầu bằng `#` thì bỏ qua |
| Trường thừa | Từ chối toàn bộ dòng |
| Thiếu/sai trường | Từ chối toàn bộ dòng và ghi lỗi |
| Mã lặp | Vẫn là các bản ghi riêng, không tự gộp |

Ví dụ hợp lệ: `PEN 3 12.50`, `ERASER 5 3.2`, `FREE 1 0`.

Ví dụ không hợp lệ: số lượng 0, giá `8,50`, giá `1e3`, giá có ba chữ số phần lẻ hoặc có token thừa.

Đơn vị giá trị trong bài là đơn vị minh họa; không có quy tắc thuế, giảm giá hay chuyển đổi tiền tệ. Nếu cần tên sản phẩm chứa khoảng trắng hoặc một định dạng CSV có dấu ngoặc kép, phải định nghĩa/đổi parser phù hợp, không chỉ thay delimiter rồi mặc định mọi trường hợp đã đúng.

## 3. Chương trình hoàn chỉnh

Mã dùng Java 17+ với `record` và text block để phần mô hình dữ liệu/mẫu ngắn gọn; `Scanner` và `Formatter` vẫn đảm nhiệm đúng vai trò chính.

Lưu thành `TextSalesReport.java`:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Formatter;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;
import java.util.regex.Pattern;

public class TextSalesReport {
    private static final String SAMPLE = """
            # code quantity unitPrice
            PEN 3 12.50
            BOOK 2 45.00
            BAD 0 10.00
            ERASER 5 3.20
            MARKER 1 8,50
            EXTRA 1 2.00 trailing
            """;

    private static final Pattern CODE =
            Pattern.compile("[A-Z][A-Z0-9_-]{0,11}");
    private static final Pattern QUANTITY =
            Pattern.compile("[1-9][0-9]{0,6}");
    private static final Pattern PRICE =
            Pattern.compile("[0-9]{1,7}(?:\\.[0-9]{1,2})?");

    record Item(String code, int quantity, BigDecimal unitPrice) {
        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Parsed(List<Item> items, List<String> errors) {}

    static Item parseLine(String text) {
        try (Scanner fields = new Scanner(text).useLocale(Locale.ROOT)) {
            if (!fields.hasNext(CODE)) {
                throw new IllegalArgumentException("INVALID_CODE");
            }
            String code = fields.next();

            if (!fields.hasNext(QUANTITY)) {
                throw new IllegalArgumentException("INVALID_QUANTITY");
            }
            int quantity = fields.nextInt();
            if (quantity > 1_000_000) {
                throw new IllegalArgumentException("QUANTITY_OUT_OF_RANGE");
            }

            if (!fields.hasNext(PRICE)) {
                throw new IllegalArgumentException("INVALID_PRICE");
            }
            BigDecimal price = fields.nextBigDecimal();
            if (fields.hasNext()) {
                throw new IllegalArgumentException("EXTRA_FIELD");
            }
            return new Item(code, quantity, price);
        }
    }

    // Phuong thuc nay nhan quyen dong Reader duoc truyen vao.
    static Parsed parse(Reader source) throws IOException {
        List<Item> items = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        try (Scanner lines = new Scanner(source)) {
            int lineNumber = 0;
            while (lines.hasNextLine()) {
                lineNumber++;
                String text = lines.nextLine().strip();
                if (text.isEmpty() || text.startsWith("#")) {
                    continue;
                }
                try {
                    items.add(parseLine(text));
                } catch (IllegalArgumentException ex) {
                    errors.add("line " + lineNumber + ": " + ex.getMessage());
                }
            }
            if (lines.ioException() != null) {
                throw lines.ioException();
            }
        }
        return new Parsed(List.copyOf(items), List.copyOf(errors));
    }

    static String report(Parsed parsed) {
        StringBuilder text = new StringBuilder();
        BigDecimal total = BigDecimal.ZERO;
        long totalQuantity = 0;
        try (Formatter out = new Formatter(text, Locale.ROOT)) {
            out.format("%-12s %8s %14s %18s%n",
                    "CODE", "QTY", "UNIT_PRICE", "AMOUNT");
            for (Item item : parsed.items()) {
                out.format("%-12s %8d %14.2f %18.2f%n",
                        item.code(), item.quantity(),
                        item.unitPrice(), item.amount());
                totalQuantity += item.quantity();
                total = total.add(item.amount());
            }
            out.format("ACCEPTED=%d REJECTED=%d%n",
                    parsed.items().size(), parsed.errors().size());
            out.format("TOTAL_QTY=%d TOTAL_AMOUNT=%.2f%n",
                    totalQuantity, total);
            for (String error : parsed.errors()) {
                out.format("%s%n", error);
            }
        }
        return text.toString();
    }

    public static void main(String[] args) throws IOException {
        Reader source = args.length == 0
                ? new StringReader(SAMPLE)
                : Files.newBufferedReader(
                        Path.of(args[0]), StandardCharsets.UTF_8);
        Parsed parsed = parse(source);
        System.out.print(report(parsed));
    }
}
```

Biên dịch và chạy dữ liệu mẫu:

```shell
javac --release 17 -encoding UTF-8 TextSalesReport.java
java TextSalesReport
```

Stdout:

```text
CODE              QTY     UNIT_PRICE             AMOUNT
PEN                 3          12.50              37.50
BOOK                2          45.00              90.00
ERASER              5           3.20              16.00
ACCEPTED=3 REJECTED=3
TOTAL_QTY=10 TOTAL_AMOUNT=143.50
line 4: INVALID_QUANTITY
line 6: INVALID_PRICE
line 7: EXTRA_FIELD
```

Đối chiếu phép tính:

```text
PEN    : 3 × 12.50 = 37.50
BOOK   : 2 × 45.00 = 90.00
ERASER : 5 ×  3.20 = 16.00

Tổng số lượng = 3 + 2 + 5 = 10
Tổng giá trị  = 37.50 + 90.00 + 16.00 = 143.50
```

Dòng `BAD`, `MARKER` và `EXTRA` không đóng góp vào tổng. Chúng không được “đọc tạm một phần” rồi vẫn cộng số lượng/giá.

## 4. Vì sao dùng Scanner theo hai tầng?

### Tầng đọc dòng

Scanner ngoài chỉ dùng `hasNextLine()` và `nextLine()`. Mỗi lần đọc tăng số dòng trước khi quyết định bỏ qua chú thích hoặc dòng trống.

Nhờ vậy, lỗi `line 6` luôn chỉ dòng vật lý thứ 6 trong đầu vào, không phải bản ghi thứ 6 sau khi lọc.

Không trộn `nextInt()` trên scanner ngoài với `nextLine()` rồi quên phần cuối dòng còn lại. Cách đọc theo dòng giúp cô lập lỗi: thiếu giá ở dòng hiện tại không kéo trường từ dòng sau lên để lấp vào.

### Tầng đọc trường

Scanner trong chỉ nhận một chuỗi đã là một dòng. Delimiter mặc định là khoảng trắng; nó có thể đọc các trường bằng `next()`, `nextInt()` và `nextBigDecimal()`.

Các lời gọi `hasNext(Pattern)` kiểm tra token kế tiếp có khớp toàn bộ dạng được phép hay không, chưa tiêu thụ token đó. Khi đạt điều kiện, lời gọi `next...` mới lấy giá trị.

Ví dụ kiểm tra số lượng có hai lớp:

1. Regex bảo đảm hình thức số nguyên dương gồm chữ số ASCII theo hợp đồng.
2. Giá trị số phải không vượt 1.000.000.

Regex giới hạn tối đa 7 chữ số, nên giá trị mà `nextInt()` đọc ở đây nằm trong miền `int`. Nếu bỏ giới hạn hình thức này, phải kiểm tra thêm khả năng đọc bằng `hasNextInt()` hoặc xử lý trường hợp vượt miền kiểu.

Scanner có các quy tắc delimiter, locale và chuyển kiểu riêng; xem [Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html).

### Không mắc kẹt ở token sai

Nếu chỉ viết vòng lặp kiểu `while (scanner.hasNext())` rồi bắt `InputMismatchException` nhưng không tiêu thụ token sai, chương trình có thể gặp lại đúng token ấy mãi.

Trong mẫu, khi một dòng sai, scanner của dòng bị đóng và parser chuyển sang dòng tiếp theo. Vì mỗi dòng là một đơn vị độc lập, không có vòng thử lại vô hạn trên cùng token.

## 5. Locale của đầu vào phải tường minh

Scanner được đặt `Locale.ROOT` để việc đọc số không phụ thuộc locale mặc định của máy chạy.

Tuy nhiên, locale chỉ là một phần hợp đồng. Scanner có thể chấp nhận những cách viết số rộng hơn định dạng đơn giản mà ứng dụng mong muốn. Do đó mẫu còn kiểm tra token giá bằng:

```java
Pattern.compile("[0-9]{1,7}(?:\\.[0-9]{1,2})?")
```

Trong chuỗi Java, `\\.` tạo regex `\.`, nghĩa là dấu chấm tường minh. Nếu viết dấu chấm không escape trong regex, nó có ý nghĩa ký tự bất kỳ và làm kiểm tra sai.

Nhờ kiểm tra hình thức trước khi đọc:

- `12.50` được chấp nhận.
- `12,50` bị từ chối.
- `1e3` bị từ chối dù một bộ đọc số tổng quát có thể hiểu dạng số mũ.
- `1.234` bị từ chối thay vì đọc rồi âm thầm làm tròn.

Không gọi `replace(',', '.')` cho mọi đầu vào mà chưa xác định quy tắc. Chuỗi có dấu phân nhóm và dấu thập phân có thể trở nên mơ hồ. Nếu cần định dạng số Việt Nam, hãy đổi hợp đồng, locale và kiểm tra hình thức cùng nhau.

Locale và charset cũng khác nhau: locale điều khiển quy tắc số, còn UTF-8 điều khiển cách byte của tệp trở thành ký tự.

## 6. Tính bằng BigDecimal trước, định dạng sau

Giá được đọc thẳng bằng `nextBigDecimal()`, không đi qua `double`.

```java
BigDecimal amount =
        unitPrice.multiply(BigDecimal.valueOf(quantity));
```

Mẫu chỉ có phép nhân với số lượng nguyên và phép cộng các giá trị có tối đa hai chữ số phần lẻ, nên các phép tính có thể giữ kết quả thập phân chính xác theo dữ liệu đó. Không cần chuyển qua số thực nhị phân rồi mới tạo `BigDecimal`.

Không dùng:

```java
new BigDecimal(0.1)
```

để biểu diễn chính xác văn bản `"0.1"`: đối số ở đây đã là một giá trị `double`. Nếu tạo từ văn bản thì dùng dạng chuỗi hoặc đọc trực tiếp như trong mẫu. Xem [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

`Formatter` chỉ quyết định cách hiển thị. Nó không thay thế quy tắc tính toán hoặc làm tròn nghiệp vụ. Nếu sau này thêm thuế/tỉ lệ/chiết khấu, cần xác định thời điểm và chế độ làm tròn rõ ràng trước khi xuất báo cáo.

Cũng không cộng những chuỗi đã format như `"37.50"`. Giữ dữ liệu có kiểu cho đến bước trình bày cuối cùng.

## 7. Đọc cú pháp Formatter trong báo cáo

Chuỗi định dạng của dòng dữ liệu:

```java
"%-12s %8d %14.2f %18.2f%n"
```

| Thành phần | Ý nghĩa trong ví dụ |
| --- | --- |
| `%-12s` | Chuỗi, căn trái trong độ rộng tối thiểu 12 |
| `%8d` | Số nguyên thập phân, căn phải trong độ rộng tối thiểu 8 |
| `%14.2f` | Số thập phân dạng cố định với 2 chữ số phần lẻ, độ rộng tối thiểu 14 |
| `%18.2f` | Cột thành tiền rộng hơn, cùng 2 chữ số phần lẻ |
| `%n` | Xuống dòng phù hợp nền tảng |

`Formatter` hỗ trợ trực tiếp `BigDecimal` cho dạng số thích hợp; không cần đổi giá thành `double` chỉ để dùng `%f`. Xem [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

Các độ rộng là **tối thiểu**, không phải giới hạn cắt dữ liệu. Nếu giá trị dài hơn độ rộng, Formatter vẫn in dài hơn. Mẫu chọn cột phù hợp với giới hạn mã/số lượng/giá của đầu vào, nhưng không có nghĩa một format string tự kiểm soát dữ liệu quá dài.

`Locale.ROOT` ở Formatter giữ dấu chấm trong báo cáo mẫu. Nếu đổi locale xuất, số có thể hiển thị khác; dữ liệu tính toán bên trong vẫn là `BigDecimal`.

Lưu ý kiểu đối số:

- `%d` dành cho kiểu số nguyên tương thích, không dùng cho `BigDecimal`.
- `%.2f` định dạng số có phần thập phân thích hợp, không dùng cho một chuỗi giá chưa được phân tích.
- Số lượng hoặc kiểu đối số sai có thể tạo ngoại lệ định dạng; không “chữa” bằng cách chuyển mọi giá trị thành chuỗi tùy tiện.

Trong mẫu, format string là hằng số do chương trình sở hữu, dữ liệu đi qua đối số `%s`/`%d`/`%f`. Không lấy nguyên một dòng dữ liệu ngoài làm format string.

## 8. Đọc tệp UTF-8 và quản lý tài nguyên

Tạo `sales.txt` mã hóa UTF-8 với nội dung:

```text
ITEM 2 0.10
# Ghi chú tiếng Việt
ITEM2 1 1.05
BAD 1000001 1.00
```

Chạy:

```shell
java TextSalesReport sales.txt
```

Stdout:

```text
CODE              QTY     UNIT_PRICE             AMOUNT
ITEM                2           0.10               0.20
ITEM2               1           1.05               1.05
ACCEPTED=2 REJECTED=1
TOTAL_QTY=3 TOTAL_AMOUNT=1.25
line 4: QUANTITY_OUT_OF_RANGE
```

Chương trình mở tệp bằng `Files.newBufferedReader(..., StandardCharsets.UTF_8)`, rồi giao quyền đóng Reader cho `parse()`. Scanner ngoài đóng nguồn đọc khi kết thúc. Quyền sở hữu này được ghi ngay trên phương thức để nơi gọi không hiểu nhầm nguồn vẫn còn dùng được.

Nếu truyền `System.in` vào một Scanner, đóng Scanner có thể đóng luôn nguồn nhập đó; ứng dụng lớn cần xác định ai sở hữu nguồn trước khi dùng try-with-resources.

Một chi tiết dễ bỏ sót: Scanner có thể xem lỗi I/O từ nguồn đọc như kết thúc đầu vào và giữ ngoại lệ để đọc bằng `ioException()`. Mẫu kiểm tra ngoại lệ này sau vòng lặp; nếu nguồn bị lỗi, nó ném lỗi lên thay vì xuất một báo cáo có vẻ hoàn chỉnh từ dữ liệu bị đọc dở.

Cách mở Reader và charset được mô tả trong [Files.newBufferedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)).

Tệp đầu vào nên đúng hợp đồng UTF-8 của bài; nếu có ký tự BOM ở đầu, cần quyết định xử lý tường minh thay vì trông chờ parser mã hàng tự bỏ nó.

## 9. Tạo báo cáo trong bộ nhớ rồi chọn nơi xuất

`report()` trả một `String`, không ghi thẳng vào tệp hay console. Nhờ vậy có thể kiểm tra nội dung, gửi ra console hoặc lưu UTF-8 mà không lặp lại logic định dạng.

Ví dụ tích hợp lưu tệp sau khi đã có `parsed`:

```java
Files.writeString(
        Path.of("report.txt"),
        report(parsed),
        StandardCharsets.UTF_8);
```

Đây là đoạn tích hợp bên trong chương trình có các import tương ứng. Lệnh ghi sẽ tạo hoặc ghi đè tệp theo hành vi mặc định; ứng dụng thực tế phải chọn vị trí/chính sách ghi đúng nhu cầu.

Formatter trong mẫu ghi vào `StringBuilder`, nên đóng nó không đóng `System.out`. Nếu Formatter ghi trực tiếp vào một nguồn có thể đóng hoặc một tệp, cần quản lý vòng đời và lỗi ghi phù hợp. Với output có I/O, kiểm tra đường báo lỗi của Formatter thay vì mặc định không có ngoại lệ tại chỗ nghĩa là mọi byte đã được ghi thành công.

`%n` tạo ký tự xuống dòng theo nền tảng. Bố cục hiển thị như mẫu, nhưng byte newline có thể khác giữa Windows và hệ điều hành khác; nếu yêu cầu tệp có định dạng byte cố định, phải quy định newline riêng.

## 10. Chính sách lỗi và giới hạn của bản thực hành

Chương trình đang dùng chính sách **bỏ dòng sai, báo lỗi và tiếp tục**, không phải “gặp lỗi đầu tiên thì dừng”. Hai chính sách đều có thể phù hợp, nhưng phải chọn rõ.

Nếu muốn dừng ngay, có thể chuyển lỗi dòng thành ngoại lệ chứa số dòng thay vì thêm vào danh sách lỗi. Không nên giữ nguyên báo cáo có tổng từ một phần dữ liệu rồi gọi nó là kết quả đầy đủ mà không nêu trạng thái.

Các giới hạn cần hiểu:

- Scanner tiện cho phân tích văn bản vừa phải, nhưng regex và chuyển kiểu có chi phí; dữ liệu rất lớn có thể cần cách đọc chuyên dụng hơn.
- Mẫu giữ toàn bộ bản ghi hợp lệ và lỗi trong bộ nhớ để dễ xem/kiểm thử.
- Đọc một dòng không tự giới hạn chiều dài dòng; với đầu vào không kiểm soát cần thêm ngân sách tệp/dòng/số bản ghi tại biên nhập.
- Bài không xử lý CSV có ngoặc kép, trường nhiều dòng hoặc tên sản phẩm chứa khoảng trắng.
- Không dùng chung một Scanner/Formatter cho nhiều luồng mà không có quy tắc đồng bộ thích hợp.
- Số dòng hợp lệ không phải số mã hàng khác nhau.

Bảng tự kiểm tra:

| Dữ liệu đầu vào | Kết quả cần có |
| --- | --- |
| Dòng đúng với nhiều khoảng trắng/tab | Đọc đúng 3 trường |
| Dòng trống hoặc chú thích toàn dòng | Bỏ qua nhưng vẫn giữ đúng số dòng cho lỗi sau |
| Số lượng 0, âm hoặc vượt 1.000.000 | Từ chối |
| Giá có dấu phẩy, số mũ hoặc hơn 2 chữ số phần lẻ | Từ chối theo hợp đồng hiện tại |
| Thiếu giá hoặc có token thừa | Không cộng một phần dữ liệu vào tổng |
| Giá 0.10 và phép tính tổng | Giữ số thập phân chính xác theo mô hình BigDecimal |
| Tệp rỗng | Báo 0 dòng nhận, 0 dòng lỗi và tổng 0.00 |
| Lỗi đọc nguồn | Báo lỗi I/O thay vì coi là EOF bình thường |

Bài tập:

1. Thêm một dòng `PEN 2 12.50` và kiểm tra chương trình tăng số bản ghi, số lượng và tổng giá trị thế nào.
2. Chuyển yêu cầu sang gộp theo CODE. Cần định nghĩa gì khi cùng mã xuất hiện với hai đơn giá khác nhau?
3. Đổi locale xuất sang một locale dùng dấu phẩy thập phân, rồi giải thích vì sao locale đầu vào không bắt buộc phải đổi theo.
4. Viết một ca đầu vào có dòng đúng, dòng sai ở giữa và dòng đúng phía sau; kiểm tra lỗi không làm parser bỏ mất dòng cuối.

Mục tiêu của bài là nối được ba trách nhiệm: phân tích cú pháp bằng Scanner, tính toán trên dữ liệu có kiểu và trình bày bằng Formatter. Giữ ba bước riêng giúp báo cáo vừa dễ đọc vừa có thể kiểm chứng.
