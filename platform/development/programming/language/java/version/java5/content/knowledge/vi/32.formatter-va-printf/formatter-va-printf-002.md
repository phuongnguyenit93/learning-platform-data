# String.format, PrintStream.printf và Formatter

## 1. Cùng ngôn ngữ định dạng, khác nơi nhận kết quả

Giả sử cần biểu diễn một mặt hàng theo mẫu:

```text
item=pen, quantity=003, price=12.50
```

Ta có dữ liệu như tên, số lượng và giá; mẫu quyết định cách dữ liệu được đưa vào chuỗi. Trong Java, `String.format`, `PrintStream.printf` và `Formatter` cùng sử dụng cú pháp định dạng kiểu printf.

Điểm khác nhau quan trọng nằm ở câu hỏi **kết quả đi đâu và ai quản lý đích ghi**:

| API | Kết quả đi đâu? | Giá trị phương thức trả về |
| --- | --- | --- |
| `String.format(...)` | Một String mới | `String` đã định dạng |
| `PrintStream.printf(...)` | Luồng xuất, ví dụ `System.out` | Chính `PrintStream` đó |
| `Formatter.format(...)` | Đích của Formatter, chẳng hạn StringBuilder | Chính `Formatter` đó |

Ba cách không phải ba kiểu cú pháp thay thế nhau. Chúng là ba cách sử dụng bộ quy tắc định dạng với những nhu cầu lưu trữ và xuất dữ liệu khác nhau.

Các API được đưa vào từ Java 5 vẫn có giá trị trong Java hiện đại. Bài dùng ví dụ Java 17 trở lên, với locale chỉ định rõ khi kết quả cần ổn định.

## 2. Đọc mẫu định dạng cơ bản

Một mẫu có thể trộn văn bản thường với những chỉ dẫn bắt đầu bằng dấu phần trăm:

```java
"item=%s, quantity=%03d, price=%.2f"
```

Giải thích:

| Chỉ dẫn | Ý nghĩa trong ví dụ |
| --- | --- |
| `%s` | Biểu diễn đối số dưới dạng chuỗi |
| `%d` | Biểu diễn số nguyên thập phân |
| `%03d` | Số nguyên có độ rộng tối thiểu ba, đệm số không khi phù hợp |
| `%.2f` | Số theo dạng thập phân cố định với hai chữ số sau dấu thập phân |
| `%n` | Xuống dòng theo nền tảng |
| `%%` | Dấu phần trăm thật |

Các chỉ dẫn như `%s` và `%d` thông thường dùng lần lượt các đối số truyền vào. `%%` và `%n` không tiêu thụ đối số.

Độ rộng là mức tối thiểu, không phải giới hạn cắt bớt số. `%03d` với `12345` không biến thành ba chữ số. Độ chính xác và cờ có quy tắc khác nhau tùy loại chuyển đổi; không áp dụng máy móc `%.2f` cho một chuỗi.

Ví dụ trên đủ để so sánh ba API. Muốn dùng các nhóm chuyển đổi ngày giờ, chỉ số đối số hay cờ nâng cao, cần kiểm tra hợp đồng của Formatter tương ứng.

## 3. String.format: tạo giá trị để dùng tiếp

```java
String description = String.format(
        Locale.ROOT,
        "item=%s, quantity=%03d, price=%.2f",
        "pen", 3, new BigDecimal("12.50"));
```

Đoạn minh họa cần import `java.util.Locale` và `java.math.BigDecimal`.

`description` là String mới. Lời gọi không tự in ra màn hình. Người gọi có thể trả chuỗi từ phương thức, đưa vào một đối tượng kết quả, nối với nội dung khác hoặc kiểm tra bằng phép so sánh chuỗi.

Nếu viết:

```java
String.format(Locale.ROOT, "count=%d", 5);
```

mà không dùng kết quả, bạn đã tạo chuỗi nhưng chưa làm gì với nó. Đây là khác biệt với `System.out.printf`.

String là bất biến. Việc tạo kết quả không sửa chuỗi mẫu hoặc đối tượng số được truyền vào. Định dạng là việc tạo cách biểu diễn, không phải đổi kiểu dữ liệu gốc.

Chọn cách này khi phần việc cần một giá trị văn bản hơn là tác dụng phụ ghi ra một nơi cụ thể. Đừng tạo một chuỗi trung gian bằng String.format chỉ để ngay lập tức ghi nó nếu printf đã thể hiện nhu cầu trực tiếp và không cần giữ bản chuỗi.

## 4. PrintStream.printf: định dạng rồi ghi ra luồng xuất

`System.out` là một `PrintStream`, nên có thể viết:

```java
System.out.printf(Locale.ROOT, "count=%d%n", 5);
```

Lời gọi định dạng dữ liệu rồi ghi vào đích của PrintStream đó. Nó không tự thêm xuống dòng nếu mẫu không có ký tự xuống dòng hoặc `%n`.

Kiểu trả về là `PrintStream`, không phải String:

```java
// SAI về kiểu: printf không trả String.
String text = System.out.printf("count=%d", 5);
```

Đoạn trên là ví dụ lỗi biên dịch có chủ ý; không đưa vào chương trình chạy được.

`PrintStream.format` là cách gọi tương đương về tác dụng định dạng của printf. Ví dụ:

```java
System.out.format(Locale.ROOT, "count=%d%n", 5);
```

Tên printf thường giúp người đọc nhận ra mục đích xuất theo mẫu. Chọn tên nhất quán với mã xung quanh.

PrintStream biến ký tự thành byte theo cấu hình mã hóa của nó. Locale quyết định các chi tiết biểu diễn theo vùng; mã hóa quyết định cách ký tự được đưa ra byte. Hai thiết lập giải quyết hai vấn đề khác nhau.

Với lỗi I/O, PrintStream có cơ chế cờ lỗi được kiểm tra qua `checkError()`, khác với một số luồng ghi ném IOException trực tiếp. Lỗi mẫu định dạng vẫn có thể ném ngoại lệ không được kiểm tra; không kết luận rằng printf “không bao giờ ném lỗi” chỉ vì nó dùng PrintStream.

## 5. Formatter: quản lý một đích định dạng qua nhiều lần ghi

`Formatter` là đối tượng thực hiện việc định dạng. Nó phù hợp khi muốn gắn một đích với locale rồi thực hiện nhiều lời gọi:

```java
StringBuilder output = new StringBuilder();
try (Formatter formatter = new Formatter(output, Locale.ROOT)) {
    formatter.format("count=%d", 5);
    formatter.format("; status=%s", "ready");
}
String text = output.toString();
```

Cần import `java.util.Formatter`.

Hai lần format nối vào cùng StringBuilder; lần sau không xóa nội dung lần trước. `formatter.format` trả Formatter để có thể nối lời gọi:

```java
formatter.format("count=%d", 5)
         .format("; status=%s", "ready");
```

Đây là đoạn tương đương để đặt bên trong phạm vi Formatter đang mở, không phải chương trình độc lập.

Nếu tạo `new Formatter()` không chỉ định đích, nó dùng một bộ đệm nội bộ có thể lấy biểu diễn qua `toString()`. Khi đã có StringBuilder bên ngoài, dùng chính StringBuilder đó để giữ và đọc kết quả thường rõ ràng hơn.

Một Formatter đã đóng không được dùng tiếp để format; thao tác đó ném `FormatterClosedException`. Không xem close như lệnh chỉ “xóa bộ đệm để viết tiếp”.

Formatter có trạng thái, có thể ghi nhiều lần và không được mặc định là an toàn khi nhiều luồng cùng dùng. Dùng đối tượng cục bộ hoặc cơ chế đồng bộ/quyền sở hữu phù hợp nếu cần chia sẻ.

## 6. Ví dụ chạy được: cùng dữ liệu qua ba API

Lưu thành `FormatDestinationsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Formatter;
import java.util.Locale;

public class FormatDestinationsDemo {
    public static void main(String[] args) {
        String pattern = "item=%s, quantity=%03d, price=%.2f";
        BigDecimal price = new BigDecimal("12.50");

        String created = String.format(
                Locale.ROOT, pattern, "pen", 3, price);
        System.out.println("string=" + created);

        System.out.printf(Locale.ROOT,
                "printf=item=%s, quantity=%03d, price=%.2f%n",
                "pen", 3, price);

        StringBuilder destination = new StringBuilder();
        try (Formatter formatter =
                     new Formatter(destination, Locale.ROOT)) {
            formatter.format(pattern, "pen", 3, price);
            formatter.format("; status=%s", "ready");
        }
        System.out.println("formatter=" + destination);

        System.out.println("root="
                + String.format(Locale.ROOT, "%.2f", price));
        System.out.println("germany="
                + String.format(Locale.GERMANY, "%.2f", price));
        System.out.printf(Locale.ROOT, "progress=%d%%%n", 80);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 FormatDestinationsDemo.java
java FormatDestinationsDemo
```

Stdout theo các dòng:

```text
string=item=pen, quantity=003, price=12.50
printf=item=pen, quantity=003, price=12.50
formatter=item=pen, quantity=003, price=12.50; status=ready
root=12.50
germany=12,50
progress=80%
```

`%n` dùng dấu xuống dòng của nền tảng, vì vậy byte kết thúc dòng có thể khác giữa Windows và hệ thống khác; nội dung các dòng như trên.

Chương trình chứng minh ba điểm:

1. String.format trả giá trị; cần println để thấy giá trị đó ở console.
2. printf ghi trực tiếp; không cần tạo biến String chứa toàn bộ kết quả.
3. Formatter giữ một đích qua nhiều lần gọi; kết quả tích lũy trong StringBuilder vẫn đọc được sau khi Formatter đóng.

StringBuilder không phải tài nguyên Closeable, nên đóng Formatter trong ví dụ không làm mất quyền đọc StringBuilder.

Hai dòng locale dùng cùng một giá trị tiền nhưng dấu thập phân khác nhau. Định dạng hai chữ số không tự quyết định đơn vị tiền, quy tắc thuế hay quy tắc làm tròn nghiệp vụ.

## 7. Locale phải là một quyết định có chủ ý

Các overload không nhận locale có thể dùng locale mặc định của môi trường cho việc định dạng. Kết quả có thể khác giữa máy phát triển, máy CI và máy người dùng.

Với nội dung phục vụ người dùng, chọn locale của người dùng hoặc yêu cầu hiển thị. Với văn bản kỹ thuật cần dấu thập phân ổn định, `Locale.ROOT` thường là lựa chọn rõ ràng.

Không sửa locale mặc định toàn tiến trình chỉ để một phép kiểm thử đi qua nếu có thể truyền locale trực tiếp. Thay đổi toàn cục ảnh hưởng các phần việc khác và có thể gây xung đột khi test chạy song song.

Ngay cả khi chỉ định locale, Formatter không trở thành bộ tuần tự hóa cho mọi giao thức. JSON, CSV, SQL hay URL có quy tắc thoát ký tự và cấu trúc riêng. Dùng công cụ tương ứng cho từng định dạng, không chỉ chọn một mẫu rồi mặc định dữ liệu đã an toàn để đưa vào giao thức.

Ví dụ, `%s` không thoát dấu nháy cho JSON, không tham số hóa SQL và không bảo vệ đầu vào HTML.

## 8. Mẫu và đối số được kiểm tra chủ yếu lúc chạy

Ba API nhận danh sách đối số linh hoạt qua varargs. Một lời gọi có thể biên dịch nhưng không khớp chuyển đổi khi thực thi:

```java
String.format(Locale.ROOT, "%d", "12");
```

Chuỗi `"12"` không được tự phân tích thành số nguyên cho `%d`. Lời gọi ném `IllegalFormatConversionException`.

Thiếu đối số:

```java
String.format(Locale.ROOT, "%s:%d", "item");
```

sẽ ném `MissingFormatArgumentException`.

Các loại chuyển đổi, cờ, độ rộng và độ chính xác không hợp lệ cũng có những ngoại lệ thuộc hệ `IllegalFormatException`. Đây thường là lỗi của mẫu hoặc của cách ghép dữ liệu, nên nên phát hiện bằng kiểm thử và sửa, thay vì bắt rồi âm thầm bỏ toàn bộ thông báo.

Chương trình kiểm chứng hai trường hợp, lưu thành `FormatFailureDemo.java`:

```java
import java.util.IllegalFormatException;
import java.util.Locale;

public class FormatFailureDemo {
    private static void showFailure(String pattern, Object... values) {
        try {
            String.format(Locale.ROOT, pattern, values);
            throw new AssertionError("Formatting should have failed");
        } catch (IllegalFormatException e) {
            System.out.println(e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        showFailure("%d", "12");
        showFailure("%s:%d", "item");
    }
}
```

Chạy:

```shell
javac --release 17 FormatFailureDemo.java
java FormatFailureDemo
```

Stdout:

```text
IllegalFormatConversionException
MissingFormatArgumentException
```

Không đưa toàn bộ văn bản không tin cậy vào vị trí mẫu:

```java
// Mẫu do chương trình kiểm soát; input là dữ liệu.
System.out.printf("%s%n", input);
```

Đây là đoạn minh họa cần một biến input có sẵn. Nó tránh việc các dấu phần trăm trong input bị hiểu thành chỉ dẫn định dạng. Nó không tự xử lý mọi vấn đề khác của dữ liệu như ký tự xuống dòng trong log; những yêu cầu đó cần quy tắc riêng.

## 9. Quản lý đích ghi và việc đóng

Quyền sở hữu tài nguyên quan trọng hơn việc một lớp có AutoCloseable hay không.

Nếu một Formatter sở hữu tệp hoặc một đích Closeable mà chính mã đó tạo, try-with-resources giúp nhả tài nguyên đúng lúc. Nhưng đóng Formatter cũng có thể đóng đích Closeable bên dưới.

Vì vậy cần cẩn thận với:

```java
// Thận trọng: đóng formatter có thể đóng System.out.
try (Formatter formatter = new Formatter(System.out, Locale.ROOT)) {
    formatter.format("done%n");
}
```

Đây là ví dụ cảnh báo về quyền sở hữu, không phải mẫu nên sao chép để in console. `System.out` thường là tài nguyên dùng chung của tiến trình; đóng nó có thể ảnh hưởng những phần việc còn muốn in tiếp.

Với console, `System.out.printf` thường là cách trực tiếp và không cần tự đóng luồng dùng chung. Với StringBuilder, Formatter có thể đóng trong phạm vi cục bộ như chương trình đầy đủ.

Phân biệt thêm:

- Định dạng thành công chưa nhất thiết đồng nghĩa dữ liệu đã tới thiết bị vật lý.
- Flush là đẩy dữ liệu đệm theo hợp đồng đích, khác với close.
- Khi đích có thể ném IOException, Formatter có cơ chế lưu lỗi I/O gần nhất để đọc bằng `ioException()`; đừng suy ra chỉ từ việc format không ném rằng việc ghi chắc chắn đã thành công.
- Charset của đích cần phù hợp khi ghi ký tự ra byte. Locale không sửa lỗi mã hóa tiếng Việt.

Những điểm này giúp chọn API theo vòng đời đích ghi thay vì chỉ chọn vì cú pháp ngắn.

## 10. Chọn cách dùng cho từng tình huống

| Tình huống | Lựa chọn thường rõ nhất |
| --- | --- |
| Cần trả một thông báo đã định dạng từ phương thức | String.format |
| Cần xuất một dòng theo mẫu vào PrintStream đã có | printf hoặc format của PrintStream |
| Cần nhiều lần định dạng vào cùng Appendable và locale | Formatter |
| Chỉ cần nối một nhãn đơn giản với một giá trị | Cân nhắc phép nối chuỗi nếu dễ đọc hơn |
| Cần tạo tài liệu theo cấu trúc như JSON | Dùng bộ tạo/tuần tự hóa đúng định dạng |

Không có yêu cầu mọi chuỗi phải dùng Formatter. Hãy dùng mẫu khi việc kiểm soát cách biểu diễn số, căn lề, thứ tự hoặc cấu trúc văn bản làm mã dễ đọc hơn.

Nếu chạy trong vòng lặp lớn, phân biệt chi phí tạo giá trị và chi phí ghi I/O. Đừng mặc định một cách nhanh hơn trong mọi tình huống; đo đúng đường sử dụng thực tế nếu hiệu năng quan trọng. Việc giữ một Formatter để dùng lại cũng đưa thêm trạng thái và yêu cầu quản lý vòng đời, không chỉ là tối ưu miễn phí.

## 11. Tự kiểm tra

1. String.format có tự in kết quả không?
2. printf trả String hay PrintStream?
3. Hai lần format trên cùng Formatter có tự thay nội dung lần trước không?
4. Vì sao nên chỉ định locale trong test cần stdout ổn định?
5. Vì sao `String.format("%d", "12")` không phải cách chuyển chuỗi sang số?
6. Có nên đóng Formatter đang bọc System.out chỉ vì nó AutoCloseable không?

Đáp án:

1. Không; nó trả String.
2. Trả chính PrintStream.
3. Không; nó ghi tiếp theo đích.
4. Tránh phụ thuộc locale mặc định của môi trường.
5. Định dạng không tự phân tích chuỗi theo chuyển đổi số nguyên đó.
6. Cần xét quyền sở hữu; đóng có thể ảnh hưởng luồng xuất dùng chung.

Khi lựa chọn giữa ba API, xác định trước kết quả là một giá trị cần giữ, một lần ghi ra luồng hay một chuỗi các lần ghi cùng đích. Sau đó chọn locale, mẫu và cách quản lý tài nguyên tương ứng.

## Tài liệu đối chiếu

- [Formatter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): cú pháp, locale, đích ghi và lỗi.
- [String — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): các overload format trả chuỗi.
- [PrintStream — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintStream.html): printf, format và cơ chế lỗi luồng xuất.
