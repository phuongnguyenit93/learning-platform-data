# Formattable và tùy biến biểu diễn đối tượng

## 1. Khi toString chưa diễn đạt đủ nhu cầu

Một đối tượng sản phẩm có thể cần hai cách hiển thị:

```text
Dạng đầy đủ: p7 - Tea 50%
Dạng gọn:    p7
```

Nếu chỉ có `toString()`, đối tượng chỉ đưa ra một biểu diễn chung mà không nhận trực tiếp yêu cầu độ rộng, căn lề, giới hạn nội dung hay locale từ mẫu định dạng.

`Formattable` cho phép một kiểu tham gia vào cơ chế Formatter khi được định dạng bằng `%s` hoặc `%S`. Formatter chuyển các yêu cầu liên quan cho đối tượng, còn đối tượng chịu trách nhiệm tạo và ghi biểu diễn phù hợp.

Đây là một hợp đồng tùy biến cho hệ định dạng kiểu printf. Nó không làm đối tượng tự biến thành chuỗi trong mọi ngữ cảnh và không thay thế một bộ tuần tự hóa dữ liệu.

Formattable được giới thiệu từ Java 5 và vẫn còn dùng trong Java hiện đại. Bài dùng chương trình Java 17 trở lên, không cần framework hoặc API nội bộ.

## 2. Formatter gọi đối tượng như thế nào?

Với một đối tượng thường:

```java
String text = String.format(Locale.ROOT, "%s", object);
```

Formatter sử dụng cách biểu diễn chuỗi theo hợp đồng chuyển đổi s. Khi đối tượng thực hiện Formattable, nó chuyển sang gọi:

```java
void formatTo(
        Formatter formatter,
        int flags,
        int width,
        int precision);
```

Phương thức không trả String. Nó phải ghi kết quả vào Formatter được truyền vào hoặc đích của Formatter đó.

Có thể hình dung:

```text
String.format / printf / Formatter.format
                 ↓ nhận đối tượng Formattable tại %s hoặc %S
             formatTo(...)
                 ↓ đọc yêu cầu và tạo biểu diễn
             ghi vào đúng đích
```

Khi dùng cùng kiểu qua những API khác nhau, đích có thể là bộ đệm chuỗi, console hoặc một nơi ghi khác. Nếu formatTo luôn gọi System.out, kết quả sẽ chạy ra console dù người gọi đang muốn tạo một String. Đó là lỗi vi phạm vai trò của phương thức.

## 3. Bốn tham số của formatTo

### Formatter: ngữ cảnh và đích ghi

`formatter` cho phép sử dụng:

- `formatter.locale()` để lấy locale của ngữ cảnh định dạng.
- `formatter.format(...)` để định dạng tiếp những phần không gây đệ quy.
- `formatter.out()` khi cần truy cập Appendable của đích.

Đối tượng không sở hữu Formatter của người gọi. Không close nó trong formatTo và không tự quyết định đóng luồng xuất bên dưới.

### flags: tập bit, không phải một mã đơn

Các cờ liên quan nằm trong FormattableFlags:

| Hằng | Nguồn từ mẫu | Yêu cầu |
| --- | --- | --- |
| `LEFT_JUSTIFY` | `-` | Căn trái, đệm khoảng trắng phía sau |
| `UPPERCASE` | `S` | Tạo biểu diễn chữ hoa theo locale |
| `ALTERNATE` | `#` | Dùng dạng thay thế do kiểu tự quy định |

Nhiều cờ có thể đồng thời tồn tại. Phải kiểm tra bằng phép toán bit:

```java
boolean alternate =
        (flags & FormattableFlags.ALTERNATE) != 0;
```

Không dùng `flags == ALTERNATE` như cách tổng quát để kiểm tra cờ, vì khi có thêm một bit khác, phép so sánh bằng sẽ không còn nhận ra yêu cầu dạng thay thế.

### width: độ rộng tối thiểu

`width == -1` nghĩa là không có độ rộng tối thiểu được chỉ định.

Nếu nội dung ngắn hơn độ rộng, cài đặt cần thêm khoảng trắng theo hướng căn lề. Nội dung dài hơn độ rộng không tự bị cắt bớt chỉ vì có width.

### precision: giới hạn nội dung trước khi đệm

`precision == -1` nghĩa là không có giới hạn độ chính xác được chỉ định.

Với biểu diễn kiểu chuỗi, precision giới hạn phần nội dung; sau đó mới đệm để đạt width. Vì vậy một kết quả có thể dài hơn precision do có khoảng trắng đệm.

Precision bằng không là một trường hợp hợp lệ: phần nội dung có thể rỗng, sau đó vẫn có thể có đệm theo width. Không viết thuật toán mặc định rằng precision luôn lớn hơn không.

## 4. Dạng thay thế phải có ý nghĩa do kiểu quy định

`%#s` không có một ý nghĩa chung như “thêm dấu nháy” hoặc “in dạng JSON”. Với Formattable, chính lớp quyết định ý nghĩa đó.

Trong bài:

- `%s`: mã sản phẩm và nhãn.
- `%#s`: chỉ mã sản phẩm.

Quy ước cần được ghi rõ để người dùng kiểu biết nên chọn mẫu nào. Không dùng dạng thay thế để đưa thêm dữ liệu nhạy cảm mà người gọi khó nhận ra từ mẫu.

Một String thông thường không hỗ trợ yêu cầu `#` của chuyển đổi s. Nếu gọi `%#s` với kết quả toString đã chuyển thành String, bạn không còn truyền đối tượng Formattable nữa; đó là trường hợp không hợp lệ.

Dạng thay thế cũng không nên làm thay đổi trạng thái sản phẩm. Một lần hiển thị phải là thao tác quan sát theo quy ước, không phải lệnh sửa nghiệp vụ.

## 5. Ví dụ chạy được: sản phẩm có hai cách hiển thị

Chương trình dùng record bất biến và kiểm tra các ràng buộc cơ bản. Nó chọn thứ tự:

1. Chọn dạng thường hoặc thay thế.
2. Chuyển chữ hoa nếu được yêu cầu.
3. Giới hạn phần nội dung.
4. Đệm theo độ rộng và hướng căn.
5. Ghi chuỗi đã tạo vào đích.

Lưu thành `CustomObjectFormatDemo.java`:

```java
import java.util.Formattable;
import java.util.FormattableFlags;
import java.util.Formatter;
import java.util.IllegalFormatFlagsException;
import java.util.IllegalFormatPrecisionException;
import java.util.IllegalFormatWidthException;
import java.util.Locale;
import java.util.Objects;

public class CustomObjectFormatDemo {
    record ProductView(String code, String label) implements Formattable {
        ProductView {
            Objects.requireNonNull(code);
            Objects.requireNonNull(label);
        }

        @Override
        public void formatTo(
                Formatter formatter,
                int flags,
                int width,
                int precision) {
            Objects.requireNonNull(formatter);

            int supported = FormattableFlags.LEFT_JUSTIFY
                    | FormattableFlags.UPPERCASE
                    | FormattableFlags.ALTERNATE;
            if ((flags & ~supported) != 0) {
                throw new IllegalFormatFlagsException(
                        Integer.toString(flags));
            }
            if (width < -1) {
                throw new IllegalFormatWidthException(width);
            }
            if (precision < -1) {
                throw new IllegalFormatPrecisionException(precision);
            }

            boolean alternate =
                    (flags & FormattableFlags.ALTERNATE) != 0;
            boolean uppercase =
                    (flags & FormattableFlags.UPPERCASE) != 0;
            boolean left =
                    (flags & FormattableFlags.LEFT_JUSTIFY) != 0;

            String text = alternate ? code : code + " - " + label;
            if (uppercase) {
                Locale locale = formatter.locale();
                text = text.toUpperCase(
                        locale == null ? Locale.ROOT : locale);
            }

            if (precision >= 0 && text.length() > precision) {
                int end = precision;
                if (end > 0
                        && Character.isHighSurrogate(text.charAt(end - 1))
                        && Character.isLowSurrogate(text.charAt(end))) {
                    end--;
                }
                text = text.substring(0, end);
            }

            String padding = " ".repeat(
                    Math.max(0, width - text.length()));
            String rendered = left ? text + padding : padding + text;
            formatter.format("%s", rendered);
        }

        @Override
        public String toString() {
            return "ProductView[" + code + "]";
        }
    }

    private static void show(String name, String pattern, Object value) {
        System.out.println(name + "=|"
                + String.format(Locale.ROOT, pattern, value) + "|");
    }

    public static void main(String[] args) {
        ProductView product = new ProductView("p7", "Tea 50%");

        show("normal", "%s", product);
        show("alternate", "%#s", product);
        show("upper", "%S", product);
        show("right", "%18s", product);
        show("shortLeft", "%-18.8s", product);
        show("shortCode", "%#.1s", product);
        show("empty", "%.0s", product);
        show("asString", "%s", product.toString());

        ProductView unicode =
                new ProductView("x", "\uD83D\uDE80test");
        show("safeCut", "%.5s", unicode);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 CustomObjectFormatDemo.java
java CustomObjectFormatDemo
```

Stdout theo các dòng:

```text
normal=|p7 - Tea 50%|
alternate=|p7|
upper=|P7 - TEA 50%|
right=|      p7 - Tea 50%|
shortLeft=|p7 - Tea          |
shortCode=|p|
empty=||
asString=|ProductView[p7]|
safeCut=|x - |
```

Các vạch đứng giúp thấy rõ khoảng trắng đầu/cuối.

Dòng shortLeft giữ tám đơn vị ký tự của nội dung ASCII là `p7 - Tea`, rồi đệm mười khoảng trắng để đạt độ rộng mười tám. Dòng empty có precision bằng không nên không còn nội dung.

Dòng asString truyền một String đã được tạo bởi toString; nó không đi vào formatTo của ProductView nữa. Sự khác nhau với dòng normal chứng minh hai cơ chế là những hợp đồng riêng.

Dòng safeCut kiểm chứng chính sách không cắt đôi một cặp surrogate: nội dung bắt đầu `x - ` rồi đến ký tự tên lửa. Giới hạn năm đơn vị UTF-16 sẽ nằm giữa hai đơn vị của ký tự đó, nên cài đặt lùi điểm cắt và giữ bốn đơn vị đầu. Không bắt buộc phải dùng hết hạn mức precision nếu cần tránh tạo chuỗi lỗi.

## 6. Vì sao phần ghi cuối không gây đệ quy?

Trong cài đặt, dòng cuối là:

```java
formatter.format("%s", rendered);
```

`rendered` là một String đã tạo xong. Việc định dạng String này không gọi lại formatTo của ProductView.

Ngược lại, cách sau gây đệ quy:

```java
// SAI khi nằm trong formatTo của chính đối tượng.
formatter.format("%s", this);
```

Formatter lại thấy this là Formattable, gọi formatTo, rồi mã lại gọi Formatter theo cùng cách. Kết quả có thể là StackOverflowError.

Một lỗi khác:

```java
// SAI nếu text có thể chứa ký tự % từ dữ liệu.
formatter.format(text);
```

Ở đây text bị hiểu là mẫu mới. Nhãn trong ví dụ chứa `50%`; nó phải là dữ liệu, không phải chỉ dẫn định dạng. Dùng mẫu cố định `"%s"` và truyền text như đối số giữ đúng vai trò của hai thành phần.

Nếu muốn ghi trực tiếp qua out(), cần xử lý hợp đồng của Appendable, bao gồm khả năng IOException và cách báo lỗi. Với ví dụ đơn giản, ủy quyền phần ghi một String qua Formatter giúp tránh tự tạo thêm đường xử lý I/O.

## 7. Chữ hoa, locale và giới hạn nội dung

Cờ UPPERCASE yêu cầu phần cài đặt xử lý chữ hoa; không nên mặc định Formatter sẽ tự làm phần đó sau khi formatTo đã ghi.

Trong ví dụ, locale lấy từ formatter. Nếu ngữ cảnh không có locale, lớp chọn Locale.ROOT làm quy tắc dự phòng rõ ràng. Đây là một chính sách của cài đặt, giúp không vô tình phụ thuộc locale mặc định của máy.

Chuyển chữ hoa có thể thay đổi độ dài chuỗi trong một số ngôn ngữ. Vì vậy ví dụ thực hiện chuyển chữ hoa trước khi áp giới hạn precision, để kết quả nội dung cuối vẫn không vượt giới hạn đã chọn.

Không mặc định “một ký tự hiển thị” luôn bằng một char Java:

- Một code point ngoài miền cơ bản cần một cặp surrogate.
- Một chữ có dấu có thể được biểu diễn bằng ký tự gốc và dấu kết hợp.
- Một cụm biểu tượng có thể gồm nhiều code point.

Ví dụ dùng String.length và giới hạn theo đơn vị UTF-16, đồng thời tránh cắt đôi surrogate pair. Nó chưa bảo đảm không cắt giữa một cụm chữ hiển thị hoàn chỉnh. Nếu sản phẩm cần rút gọn văn bản theo đơn vị người đọc thấy, phải bổ sung quy tắc phân đoạn phù hợp và kiểm thử riêng.

Độ rộng cũng không cam kết số ô hiển thị trên mọi phông chữ hoặc thiết bị đầu cuối. Các ví dụ căn lề ASCII cho kết quả dễ đối chiếu; giao diện thực tế có thể cần bố cục khác.

## 8. Trách nhiệm kiểm tra và quản lý trạng thái

Formattable chịu trách nhiệm diễn giải và kiểm tra các tham số mà nó nhận. Trong đường gọi qua Formatter, nhiều lỗi mẫu đã được phát hiện trước khi gọi formatTo; phần kiểm tra trong ví dụ còn giúp lời gọi trực tiếp không đưa vào bit lạ hoặc width/precision nhỏ hơn -1.

Tuy nhiên, không cần tự phân tích lại toàn bộ ngôn ngữ mẫu bên trong formatTo. Phần cài đặt chỉ xử lý hợp đồng được chuyển đến nó.

Một vài nguyên tắc thực tế:

- Không lưu Formatter vào trường để dùng sau khi formatTo đã trả về; vòng đời đích thuộc người gọi.
- Không close hoặc tự flush đích dùng chung chỉ vì đã ghi xong một đối tượng.
- Không thay locale mặc định toàn tiến trình để thực hiện một lần định dạng.
- Không sửa trạng thái nghiệp vụ để ghi nhớ “lần hiển thị gần nhất”.
- Tránh dùng chung bộ đệm khả biến giữa các luồng nếu không có giao thức bảo vệ.

Record trong ví dụ chỉ chứa String bất biến và mọi biến tạo kết quả đều cục bộ. Điều đó giúp thao tác quan sát không tranh chấp trên bộ đệm riêng của ProductView. Nó không biến một Formatter dùng chung thành đối tượng an toàn giữa nhiều luồng.

Nếu đối tượng thật có trường khả biến, cần xác định ảnh chụp dữ liệu nhất quán trước khi tạo chuỗi. Không đọc nửa trạng thái cũ và nửa trạng thái mới rồi cho rằng Formattable tự cung cấp đồng bộ.

## 9. Khi nào nên dùng và khi nào nên chọn API khác?

Formattable hữu ích khi một kiểu cần tích hợp thường xuyên với hệ Formatter, có dạng thay thế rõ ràng và muốn người gọi điều khiển căn lề/độ chính xác qua mẫu.

Không phải mọi kiểu đều cần thực hiện giao diện này.

| Nhu cầu | Hướng thường phù hợp |
| --- | --- |
| Một biểu diễn chung để xem nhanh đối tượng | toString |
| Một biểu diễn tùy biến trong mẫu %s/%S | Formattable |
| Hiển thị phức tạp phụ thuộc nhiều tùy chọn | Một bộ trình bày hoặc phương thức có tham số rõ ràng |
| Dữ liệu JSON/XML để trao đổi máy | Bộ tuần tự hóa đúng định dạng |
| Mã định danh ổn định | API lấy mã chuyên biệt |

Một mẫu như `%#-18.8S` ngắn gọn nhưng có thể khó đọc nếu quy ước của lớp không rõ. Khi số tùy chọn nghiệp vụ tăng, một API trình bày tường minh có thể dễ bảo trì hơn việc nhét nhiều nghĩa vào dấu # và precision.

Việc triển khai Formattable cũng không làm StringBuilder.append, phép nối chuỗi hoặc println tự sử dụng dạng tùy biến. Những ngữ cảnh đó vẫn theo hợp đồng chuyển thành chuỗi của chúng.

## 10. Kiểm thử phần cài đặt tùy biến

Nên có các ca kiểm thử theo những trục độc lập:

1. Dạng thường và dạng thay thế.
2. Chữ thường/chữ hoa, gồm một locale có quy tắc chữ hoa đáng chú ý nếu nằm trong phạm vi sản phẩm.
3. Có và không có width; nội dung ngắn hơn và dài hơn width.
4. Căn trái và căn phải.
5. Precision không có, bằng không, nhỏ hơn và lớn hơn nội dung.
6. Tổ hợp nhiều cờ thay vì chỉ kiểm tra từng cờ riêng.
7. Dữ liệu chứa dấu %, ký tự Unicode và dữ liệu đầu vào không hợp lệ.
8. Đích ghi khác console, để phát hiện cài đặt in nhầm ra System.out.

Khi kiểm tra căn lề, so sánh cả khoảng trắng; không trim trước khi đối chiếu. Khi kiểm tra Unicode, xác định rõ chính sách giới hạn theo UTF-16, code point hay cụm chữ để expected có căn cứ.

Một kiểm thử hữu ích nữa là truyền chính đối tượng và truyền kết quả toString của nó vào %s. Hai đường có thể khác nhau có chủ ý; điều đó giúp phát hiện việc vô tình chuyển đối tượng thành String quá sớm và làm mất khả năng tùy biến.

## 11. Tự kiểm tra

1. formatTo trả String hay ghi vào một đối tượng được truyền vào?
2. Vì sao phải kiểm tra flags bằng phép toán bit?
3. Ai quyết định ý nghĩa của %#s đối với một Formattable?
4. Vì sao gọi formatter.format("%s", this) bên trong formatTo là nguy hiểm?
5. Có nên đóng formatter của người gọi trong formatTo không?
6. Width có tự cắt chuỗi khi nội dung dài hơn không?
7. Thực hiện Formattable có làm println tự gọi formatTo không?

Đáp án:

1. Ghi vào Formatter/đích của Formatter; phương thức trả void.
2. Vì có thể có nhiều cờ đồng thời.
3. Chính lớp thực hiện Formattable.
4. Nó có thể gọi lại chính formatTo không có điểm dừng.
5. Không; quyền sở hữu thuộc người gọi.
6. Không; width là độ rộng tối thiểu.
7. Không; đây là hợp đồng riêng cho hệ Formatter.

Một phần cài đặt tốt tạo biểu diễn có quy ước rõ, tôn trọng cờ/giới hạn và ghi đúng đích, đồng thời giữ nguyên vòng đời tài nguyên của người gọi.

## Tài liệu đối chiếu

- [Formattable — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formattable.html): hợp đồng formatTo và trách nhiệm của phần cài đặt.
- [FormattableFlags — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/FormattableFlags.html): căn trái, chữ hoa và dạng thay thế.
- [Formatter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): chuyển đổi s/S và tích hợp đối tượng tùy biến.
