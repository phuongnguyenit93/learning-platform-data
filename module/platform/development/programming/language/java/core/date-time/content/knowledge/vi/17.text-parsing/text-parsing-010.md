# Thiết kế đầu vào không mơ hồ và kiểm tra toàn bộ chuỗi

## Một lần phân tích thành công chưa chắc đã đọc đúng dữ liệu

Chuỗi `03/06/2024` có thể được hiểu là ngày 3 tháng 6 hoặc ngày 6 tháng 3. Cả hai đều là ngày hợp lệ. Nếu ứng dụng lần lượt thử `dd/MM/uuuu` rồi `MM/dd/uuuu`, kết quả phụ thuộc thứ tự thử, không phụ thuộc ý định của người nhập.

Một lỗi khác là nhận `2024-02-29junk` vì bộ phân tích đã đọc được đoạn ngày ở đầu. Đọc được một tiền tố không chứng minh toàn bộ giá trị đầu vào phù hợp.

Thiết kế tốt cần đồng thời trả lời ba câu hỏi:

1. Chuỗi được phép mang cấu trúc và ý nghĩa nào?
2. Những ký tự nào của đầu vào phải được đọc và kiểm tra?
3. Giá trị sau khi đọc có hợp lệ theo lịch và theo nghiệp vụ không?

Bài này dùng ngày học để xây dựng một hợp đồng rõ ràng, sau đó minh họa sự khác nhau giữa đọc toàn bộ chuỗi, đọc một phần và chỉ đọc các trường chưa phân giải.

## 1. Hợp đồng đầu vào cần rõ hơn một chuỗi mẫu

Một hợp đồng dữ liệu là quy định để bên gửi và bên nhận cùng hiểu một giá trị. Với ngày học, có thể thống nhất:

| Thuộc tính | Quy định của ví dụ |
| --- | --- |
| Ý nghĩa | Một ngày theo lịch ISO, không có giờ hay múi giờ |
| Cấu trúc | Năm–tháng–ngày, ví dụ `2024-06-03` |
| Độ rộng | Năm đúng 4 chữ số, tháng và ngày đúng 2 chữ số |
| Chữ số | ASCII `0..9` |
| Dấu phân cách | Dấu gạch ngang ASCII `-` |
| Khoảng trắng | Không nhận ở đầu, cuối hay bên trong |
| Phần dư | Không nhận bất kỳ ký tự dư nào |
| Hợp lệ theo lịch | Phải là ngày tồn tại, không tự điều chỉnh |
| Phạm vi nghiệp vụ | Năm từ 2000 đến 2099, bao gồm hai đầu |
| Giá trị thiếu | `null` và chuỗi rỗng đều bị từ chối |

Khoảng năm ở đây là quy tắc minh họa của ứng dụng, không phải giới hạn chung của Java.

Một thông báo kiểu “hãy nhập ngày đúng định dạng” vẫn để người dùng tự đoán. Hướng dẫn “nhập ngày theo năm-tháng-ngày, ví dụ 2024-06-03” giúp cả người dùng lẫn bên tích hợp biết chính xác điều được mong đợi.

Với trường mang ý nghĩa khác, hợp đồng cũng phải đổi. Một mốc nộp bài toàn cầu có thể cần ngày giờ kèm offset; một ngày sinh thường chỉ cần ngày. Đừng thêm giờ mặc định hay múi giờ máy chủ chỉ để biến mọi đầu vào thành cùng một kiểu.

## 2. Loại bỏ sự mơ hồ từ nguồn, không đoán bằng thứ tự mẫu

Những nguồn mơ hồ thường gặp:

| Đầu vào | Thông tin chưa rõ |
| --- | --- |
| `03/06/2024` | Tháng trước hay ngày trước? |
| `03/06/24` | Thế kỷ nào? |
| `08:30` | Giờ của ngày nào, ở đâu, theo hệ nào? |
| `2024-06-03T08:30` | Giờ địa phương hay một thời điểm cần offset/vùng? |
| Tên tháng dạng chữ | Theo ngôn ngữ nào? |
| Một số nguyên làm mốc thời gian | Đơn vị giây hay mili giây, mốc gốc nào? |

Cách giải quyết là chọn biểu diễn được thống nhất, cung cấp nhãn kiểu/định dạng khi cần, và giữ đủ dữ liệu có ý nghĩa. Ví dụ hai nguồn cũ dùng hai thứ tự khác nhau nên được nhận biết bằng cấu hình nguồn hoặc phiên bản giao diện; không nên để từng giá trị tự “chọn” mẫu bằng cách thử may rủi.

Nếu đang chuyển đổi hệ thống và bắt buộc nhận nhiều mẫu, cần xác định rõ tập mẫu và chính sách khi nhiều mẫu đều đọc được nhưng cho kết quả khác nhau. Một lựa chọn an toàn về mặt ý nghĩa là từ chối giá trị mơ hồ và yêu cầu nguồn gửi dạng chuẩn. `parseBest` hay chuỗi `try/catch` không tự tìm được ý định của người gửi.

Định dạng hiển thị vẫn có thể thân thiện theo ngôn ngữ. Giao diện có thể cho chọn ngày bằng lịch rồi gửi một biểu diễn chuẩn; cách hiển thị và hợp đồng truyền dữ liệu không bắt buộc giống nhau.

## 3. Phân biệt bốn lớp kiểm tra

```text
Chuỗi thô
   ↓ chính sách null / rỗng / khoảng trắng
Cấu trúc được phép
   ↓ chữ số, dấu phân cách, độ rộng, toàn bộ đầu vào
Ngày hợp lệ
   ↓ kết hợp năm–tháng–ngày phải tồn tại
Quy tắc nghiệp vụ
   ↓ khoảng năm, ngày được đăng ký, thời hạn...
Giá trị có kiểu được ứng dụng sử dụng
```

Bốn lớp không thay thế nhau:

- Biểu thức chính quy `[0-9]{4}-[0-9]{2}-[0-9]{2}` khớp cả `2023-02-29` và `2024-99-99`; nó chưa kiểm tra lịch.
- Chế độ phân giải `STRICT` kiểm tra ngày tồn tại, nhưng không tự biết sản phẩm chỉ cho năm 2000..2099.
- Đọc một ngày hợp lệ ở đầu chuỗi chưa loại bỏ ký tự dư.
- Tự cắt chuỗi về 10 ký tự có thể làm mất bằng chứng đầu vào sai.

Đối với dạng ISO chuẩn mà hợp đồng không có các giới hạn văn bản bổ sung, `LocalDate.parse(text)` thường đã đủ đơn giản. Lớp kiểm tra cấu trúc riêng chỉ cần khi hợp đồng còn quy định chính xác chữ số, độ rộng hay tập ký tự như ví dụ trong bài.

## 4. Chương trình hoàn chỉnh: hợp đồng rõ ràng và phép kiểm tra đầy đủ

Lưu dưới tên `UnambiguousDateInputDemo.java`. Chương trình dùng Java 17 trở lên:

```java
import java.text.ParsePosition;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnambiguousDateInputDemo {
    private static final Pattern DATE_SHAPE =
            Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");

    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    static LocalDate parseCourseDate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Ngay hoc khong duoc null");
        }
        if (!DATE_SHAPE.matcher(raw).matches()) {
            throw new IllegalArgumentException(
                    "Ngay hoc phai dung dang nam-thang-ngay, vi du 2024-06-03");
        }

        LocalDate date = LocalDate.parse(raw, DATE);
        if (date.getYear() < 2000 || date.getYear() > 2099) {
            throw new IllegalArgumentException("Nam hoc phai trong 2000..2099");
        }
        return date;
    }

    private static void show(String label, String raw) {
        try {
            System.out.println(label + "=" + parseCourseDate(raw));
        } catch (DateTimeParseException | IllegalArgumentException ex) {
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        show("valid", "2024-02-29");
        show("invalidCalendarDate", "2023-02-29");
        show("wrongWidth", "2024-2-9");
        show("leadingSpace", " 2024-02-29");
        show("trailingText", "2024-02-29junk");
        show("slashDate", "03/06/2024");
        show("outsideBusinessRange", "2100-01-01");
        show("empty", "");
        show("missing", null);

        DateTimeFormatter dayFirst =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter monthFirst =
                DateTimeFormatter.ofPattern("MM/dd/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        String ambiguous = "03/06/2024";
        System.out.println("dayFirst=" + LocalDate.parse(ambiguous, dayFirst));
        System.out.println("monthFirst=" + LocalDate.parse(ambiguous, monthFirst));

        String extra = "2024-02-29junk";
        ParsePosition position = new ParsePosition(0);
        TemporalAccessor prefix = DATE.parse(extra, position);

        System.out.println("prefixDate=" + LocalDate.from(prefix));
        System.out.println("consumed=" + position.getIndex());
        System.out.println("remaining=" + extra.substring(position.getIndex()));
        System.out.println("consumedWholeInput="
                + (position.getIndex() == extra.length()));

        try {
            LocalDate.parse(extra, DATE);
            System.out.println("fullParseAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("fullParseRejected");
        }

        ParsePosition syntaxPosition = new ParsePosition(0);
        TemporalAccessor syntaxOnly =
                DATE.parseUnresolved("2023-02-29", syntaxPosition);

        System.out.println("syntaxOnlyReadInvalid=" + (syntaxOnly != null));
        System.out.println("syntaxOnlyConsumed=" + syntaxPosition.getIndex());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 UnambiguousDateInputDemo.java
java UnambiguousDateInputDemo
```

Stdout:

```text
valid=2024-02-29
invalidCalendarDate=REJECTED
wrongWidth=REJECTED
leadingSpace=REJECTED
trailingText=REJECTED
slashDate=REJECTED
outsideBusinessRange=REJECTED
empty=REJECTED
missing=REJECTED
dayFirst=2024-06-03
monthFirst=2024-03-06
prefixDate=2024-02-29
consumed=10
remaining=junk
consumedWholeInput=false
fullParseRejected
syntaxOnlyReadInvalid=true
syntaxOnlyConsumed=10
```

Chương trình tự in `REJECTED` để stdout tập trung vào hành vi, không phụ thuộc toàn văn thông báo ngoại lệ của một bản JDK.

## 5. Vì sao hàm nhập ngày trong ví dụ kiểm tra đủ?

### Kiểm tra đúng toàn bộ cấu trúc

`DATE_SHAPE.matcher(raw).matches()` yêu cầu khớp toàn bộ đầu vào của matcher mới tạo. Nó khác `find()`, vốn tìm một đoạn con khớp mẫu. Không cần thêm neo chỉ để thực hiện việc khớp toàn bộ trong lời gọi này. [Tài liệu `Matcher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html)

Vì vậy, các đầu vào có khoảng trắng, chữ dư, dấu gạch chéo hoặc độ rộng sai bị từ chối trước khi phân tích lịch.

### Kiểm tra ngày thực sự tồn tại

`LocalDate.parse(raw, DATE)` tạo đúng kiểu ngày mà ứng dụng cần. Mẫu dùng `uuuu` để có trường năm trực tiếp, và `ResolverStyle.STRICT` để ngày 29/02/2023 không bị chuyển thành một ngày khác.

Các phương thức phân tích đầy đủ yêu cầu toàn bộ chuỗi được đọc; trong chương trình, `LocalDate.parse(extra, DATE)` từ chối phần đuôi `junk`. [Tài liệu `LocalDate.parse`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence,java.time.format.DateTimeFormatter)), [tài liệu phân tích đầy đủ](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parse(java.lang.CharSequence))

### Kiểm tra phạm vi sản phẩm cho phép

Sau khi có ngày, hàm kiểm tra năm. Ngày `2100-01-01` tồn tại theo lịch nhưng không thuộc phạm vi của ví dụ, nên vẫn bị từ chối.

Trong ứng dụng thực, có thể bổ sung điều kiện như không trước ngày mở đăng ký. Các quy tắc đó nên làm việc trên giá trị có kiểu sau khi đã xác nhận đầu vào hợp lệ, thay vì so sánh chuỗi ngày tùy tiện.

## 6. Khi dùng `ParsePosition`, trách nhiệm kiểm tra phần dư thuộc về bạn

Biến thể `formatter.parse(text, position)` được thiết kế để hỗ trợ phân tích từ vị trí chỉ định và có thể dừng trước cuối chuỗi. Trong chương trình, bộ phân tích đọc được ngày đầu tiên, cập nhật vị trí thành `10` và để lại `junk`. [Tài liệu `DateTimeFormatter.parse` có vị trí](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parse(java.lang.CharSequence,java.text.ParsePosition))

`ParsePosition.getIndex()` là vị trí ngay sau ký tự cuối đã đọc; `getErrorIndex()` cung cấp vị trí lỗi nếu được đặt. [Tài liệu `ParsePosition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html)

Nếu đang đọc một trường độc lập và chủ động dùng API dạng này, cần bảo đảm:

- Vị trí bắt đầu là đúng điểm bắt đầu của trường, thường là `0`.
- Thao tác phân tích không thất bại và kết quả tạo được kiểu đích.
- Không có lỗi được báo.
- Vị trí cuối bằng độ dài trường nếu hợp đồng yêu cầu đọc hết.

Một khung minh họa cho biến thể có phân giải:

```java
ParsePosition position = new ParsePosition(0);
TemporalAccessor parsed = formatter.parse(text, position);

if (position.getErrorIndex() >= 0 || position.getIndex() != text.length()) {
    throw new IllegalArgumentException("Truong ngay con ky tu du hoac bi loi");
}
LocalDate date = LocalDate.from(parsed);
```

Đây là đoạn minh họa, giả định `formatter` đã được cấu hình và `text` không null; phương thức `parse` vẫn có thể ném ngoại lệ trước khi đến điều kiện. Nếu chỉ cần nhập một ngày độc lập, dùng trực tiếp `LocalDate.parse` thường dễ kiểm chứng hơn.

Phân tích một phần không phải lúc nào cũng sai. Nó hữu ích khi đọc cấu trúc lớn hơn có nhiều trường và dấu phân cách. Khi đó, bộ phân tích bao ngoài phải tiếp tục đọc và kiểm tra những phần còn lại. Sai sót là dùng thành công ở một đoạn làm bằng chứng cho toàn bộ trường hoặc toàn bộ bản ghi.

## 7. `parseUnresolved` không phải phép xác nhận ngày hợp lệ

Trong chương trình:

```text
syntaxOnlyReadInvalid=true
syntaxOnlyConsumed=10
```

xuất hiện với `2023-02-29`. `parseUnresolved` đọc các trường theo cú pháp nhưng chưa phân giải chúng thành ngày. Vì vậy, việc nhận được một đối tượng và đã đọc hết 10 ký tự chưa chứng minh tổ hợp năm–tháng–ngày tồn tại. [Tài liệu `parseUnresolved`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseUnresolved(java.lang.CharSequence,java.text.ParsePosition))

Đây là khác biệt giữa:

```text
Đọc được YEAR=2023, MONTH=2, DAY=29
                       ≠
Tạo được LocalDate hợp lệ
```

API mức thấp này phù hợp khi có lý do xử lý trường riêng. Đừng chỉ kiểm tra kết quả khác null rồi nhận dữ liệu vào hệ thống như ngày đã được kiểm chứng.

Cũng không nên gọi `LocalDate.from` trên một tập trường chưa phân giải rồi mặc định nó sẽ tự thực hiện toàn bộ quy trình của bộ định dạng. Với nhập liệu ngày thông thường, hãy để API phân tích đầy đủ trả về `LocalDate` đúng ngay từ ranh giới nhập.

## 8. Chuẩn hóa đầu vào cần là một quy tắc công khai

Có hai chính sách hợp lệ nhưng khác nhau:

- Giao thức yêu cầu chính xác: `2024-06-03` được nhận; ` 2024-06-03 ` bị từ chối.
- Biểu mẫu người dùng cho phép khoảng trắng ngoài cùng: ứng dụng chuẩn hóa theo quy tắc đã chọn rồi kiểm tra phần còn lại.

Điều quan trọng là quyết định trước và áp dụng nhất quán. Không tự `trim()`, xóa dấu phân cách, đổi thứ tự thành phần hay cắt chuỗi chỉ để một mẫu đang có đọc được.

Nếu cho phép chuẩn hóa, phân biệt:

```text
rawInput       = chuỗi nguồn gửi
normalizedInput = chuỗi sau quy tắc chuẩn hóa được phép
parsedValue    = ngày/giờ đã phân tích
```

Không cần lưu cả ba trong mọi hệ thống. Khi có nhu cầu truy vết, hãy xác định thông tin nào cần lưu và bảo vệ theo tính chất dữ liệu. Tuy nhiên, không gọi một phép biến đổi tùy tiện là “chuẩn hóa” nếu nó làm thay đổi nghĩa của đầu vào.

Với nhiều cách biểu diễn được phép, đầu ra chuẩn có thể khác văn bản ban đầu. Kiểm tra “định dạng lại có giống hệt chuỗi nguồn không” chỉ phù hợp khi hợp đồng thực sự yêu cầu dạng văn bản duy nhất; nó không thay thế kiểm tra ngày và quy tắc nghiệp vụ.

## 9. Thiết kế thông báo lỗi và kiểm chứng theo hợp đồng

Một hàm dùng trong sản phẩm nên phân biệt lỗi để người dùng sửa đúng chỗ, ví dụ:

| Loại lỗi | Phản hồi có ích |
| --- | --- |
| Thiếu giá trị | Yêu cầu nhập ngày học |
| Sai cấu trúc | Nêu dạng năm-tháng-ngày và ví dụ |
| Ngày không tồn tại | Giải thích tổ hợp ngày/tháng/năm không hợp lệ |
| Ngoài phạm vi | Nêu khoảng năm được cho phép |
| Mơ hồ do nhiều quy ước | Yêu cầu biểu diễn chuẩn hoặc xác nhận định dạng nguồn |
| Ký tự dư | Cho biết trường phải chứa đúng một giá trị ngày |

Tránh trả về ngày hiện tại, ngày mặc định hoặc `null` để che mọi lỗi. Những giá trị đó có thể đi tiếp vào xử lý nghiệp vụ và tạo dữ liệu sai khó phát hiện.

Khi kiểm chứng, lấy hợp đồng làm cơ sở thay vì chỉ thử những chuỗi đẹp:

- Một ngày bình thường và một ngày nhuận hợp lệ.
- Ngày không tồn tại, tháng vượt phạm vi.
- Tiền tố và hậu tố dư, kể cả khoảng trắng hoặc xuống dòng nếu bị cấm.
- Độ rộng sai, dấu phân cách khác, cấu trúc khác.
- Giá trị rỗng và null.
- Hai biên phạm vi được phép và giá trị ngay ngoài biên.
- Chuỗi dễ bị hiểu theo nhiều quy ước.

Những ca này cần xác nhận giá trị nhận được hoặc loại từ chối, không chỉ kiểm tra “hàm đã chạy”.

## 10. Tự thực hành

1. Vì sao thử `dd/MM/uuuu` trước `MM/dd/uuuu` không giải quyết được ý nghĩa của `03/06/2024`?
2. Chuỗi khớp biểu thức dạng ngày đã chắc tồn tại theo lịch chưa?
3. Một phép phân tích có `ParsePosition` dừng ở vị trí 10 trong chuỗi dài 14 ký tự có đủ cho một trường ngày độc lập không?
4. `parseUnresolved` đọc hết `2023-02-29` chứng minh được điều gì?
5. Vì sao phải kiểm tra phạm vi năm sau khi có `LocalDate`?

Gợi ý đáp án:

1. Cả hai mẫu đều có thể hợp lệ và tạo hai ngày khác nhau; cần hợp đồng hoặc thông tin nguồn rõ ràng.
2. Chưa; cấu trúc văn bản khác với tính hợp lệ của ngày.
3. Chưa; còn bốn ký tự chưa được kiểm tra theo hợp đồng trường.
4. Các trường đã được đọc theo cú pháp, chưa chứng minh chúng tạo được ngày.
5. Thư viện biết lịch; ứng dụng mới biết khoảng năm mà nghiệp vụ cho phép.

Hãy làm cho ý nghĩa đầu vào rõ từ thiết kế, dùng đúng API để đọc toàn bộ giá trị và giữ riêng các bước kiểm tra cấu trúc, lịch và nghiệp vụ.
