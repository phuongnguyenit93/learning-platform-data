# Đánh đổi giữa kế thừa triển khai và composition, delegation

Khi nhiều kiểu có hành vi chung, Java cho phép tái sử dụng mã bằng **kế thừa triển khai** hoặc bằng **composition kết hợp delegation**. Cả hai đều có thể giảm trùng lặp, nhưng chúng tạo ra mối liên kết khác nhau giữa các thành phần. Chọn đúng cách phụ thuộc vào quan hệ miền nghiệp vụ, mức độ cần thay đổi hành vi và độ ổn định của phần triển khai được tái sử dụng.

- **Kế thừa triển khai (implementation inheritance):** lớp con kế thừa trạng thái và phương thức đã có từ lớp cha, có thể dùng lại hoặc ghi đè hành vi.
- **Composition:** một đối tượng chứa hoặc giữ tham chiếu đến đối tượng khác để hợp thành hành vi của nó.
- **Delegation:** một đối tượng chuyển một phần công việc cho đối tượng được nó giữ tham chiếu. Delegation thường là cách composition sử dụng thành phần bên trong.

Composition và delegation thường xuất hiện cùng nhau: đối tượng ngoài giữ một formatter, logger hoặc policy rồi ủy quyền tác vụ tương ứng cho thành phần đó.

## 1. Kế thừa triển khai: tái sử dụng qua lớp cha

Một lớp cơ sở có thể cung cấp quy trình chung, còn lớp con tùy biến một bước thông qua phương thức abstract hoặc ghi đè phương thức có sẵn. Ví dụ, một lớp thông báo có thể giữ quy trình chuẩn bị thông điệp, trong khi lớp con định nghĩa cách định dạng nội dung.

Ưu điểm:

- Mã dùng chung nằm ở một nơi; lớp con có thể kế thừa trực tiếp các phương thức và trạng thái được phép truy cập.
- Mô hình rõ ràng khi quan hệ thực sự là một dạng chuyên biệt của kiểu cơ sở.
- Template Method có thể cố định trình tự xử lý ở lớp cha và cho phép lớp con tùy biến những bước đã xác định.

Đánh đổi:

- Quan hệ giữa lớp con và lớp cha khá chặt. Thay đổi phương thức được kế thừa có thể ảnh hưởng đến mọi lớp con, kể cả lớp đang phụ thuộc vào chi tiết triển khai ngầm.
- Lớp con thường bị ràng buộc bởi một lớp cha duy nhất. Java không hỗ trợ kế thừa triển khai từ nhiều lớp.
- Ghi đè có thể phá vỡ giả định của lớp cha nếu hợp đồng không được thiết kế rõ ràng. Phương thức protected và các trạng thái có thể thay đổi cũng có thể tạo ra nhiều phụ thuộc khó thấy.
- Hành vi được chọn chủ yếu qua kiểu của lớp con; thay đổi một chính sách cho từng đối tượng thường đòi hỏi thêm lớp con hoặc cấu trúc điều kiện.

Kế thừa triển khai hữu ích khi các kiểu thật sự chia sẻ một khái niệm cơ sở ổn định, và lớp cha có thể định nghĩa một hợp đồng nhất quán cho tất cả lớp con.

## 2. Composition và delegation: ghép hành vi từ thành phần

Với composition, đối tượng ngoài giữ một đối tượng khác làm thành phần. Thay vì kế thừa cách định dạng từ lớp cha, bộ chuẩn bị thông báo có thể giữ một đối tượng triển khai interface MessageFormatter và ủy quyền việc định dạng cho nó.

Ưu điểm:

- Mối liên kết thường lỏng hơn: đối tượng ngoài phụ thuộc vào interface nhỏ thay vì một lớp triển khai cụ thể.
- Có thể chọn thành phần khi khởi tạo đối tượng, thuận tiện cho cấu hình, dependency injection và kiểm thử bằng fake hoặc stub.
- Có thể kết hợp nhiều hành vi độc lập, ví dụ formatter, retry policy, logger và transport, mà không tạo ra một cây kế thừa lớn.
- Có thể tái sử dụng một thành phần ở những lớp không có quan hệ kế thừa với nhau.

Đánh đổi:

- Cần khai báo và truyền các thành phần phụ thuộc; một đối tượng có thể có nhiều trường và constructor hơn.
- Delegation có thể tạo thêm phương thức chuyển tiếp. Nếu lớp ngoài chỉ lặp lại toàn bộ API của thành phần, nó có thể trở thành lớp bọc dư thừa.
- Cần quyết định rõ ai sở hữu vòng đời, cấu hình và xử lý lỗi của thành phần.
- Composition không tự động bảo đảm thiết kế tốt: nếu đối tượng giữ quá nhiều phụ thuộc hoặc điều phối quá nhiều việc, nó vẫn có thể trở nên khó bảo trì.

Composition phù hợp khi một đối tượng cần một khả năng có thể thay thế, khi các khả năng thay đổi độc lập, hoặc khi không có quan hệ “là một” tự nhiên giữa đối tượng ngoài và thành phần.

## 3. Ví dụ Java 17+: cùng mục tiêu, hai cách tổ chức

Chương trình dưới đây tạo thông điệp theo hai cách. Trong nhánh kế thừa, lớp con cung cấp bước định dạng cho quy trình chung ở lớp cha. Trong nhánh composition, lớp Notifier giữ MessageFormatter và ủy quyền bước định dạng cho nó.

Lưu toàn bộ mã vào tệp **NotifierDemo.java**:

~~~java
import java.util.Objects;

interface MessageFormatter {
    String format(String recipient, String message);
}

// Option 1: implementation inheritance.
abstract class InheritanceNotifier {
    protected abstract String format(String recipient, String message);

    public final String prepare(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");
        return "SEND " + format(recipient, message);
    }
}

final class PlainTextInheritanceNotifier extends InheritanceNotifier {
    @Override
    protected String format(String recipient, String message) {
        return "to=" + recipient + "; body=" + message;
    }
}

// Option 2: composition and delegation through an interface.
final class PlainTextFormatter implements MessageFormatter {
    @Override
    public String format(String recipient, String message) {
        return "to=" + recipient + "; body=" + message;
    }
}

final class BracketFormatter implements MessageFormatter {
    @Override
    public String format(String recipient, String message) {
        return "[" + recipient + "] " + message;
    }
}

final class ComposedNotifier {
    private final MessageFormatter formatter;

    public ComposedNotifier(MessageFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter, "formatter");
    }

    public String prepare(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");
        // Delegate formatting to the injected component.
        return "SEND " + formatter.format(recipient, message);
    }
}

public class NotifierDemo {
    public static void main(String[] args) {
        InheritanceNotifier inherited = new PlainTextInheritanceNotifier();
        System.out.println("Inheritance: "
                + inherited.prepare("alice", "hello"));

        ComposedNotifier plain = new ComposedNotifier(new PlainTextFormatter());
        System.out.println("Composition: "
                + plain.prepare("alice", "hello"));

        ComposedNotifier bracket = new ComposedNotifier(new BracketFormatter());
        System.out.println("Swapped formatter: "
                + bracket.prepare("bob", "welcome"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac NotifierDemo.java
java NotifierDemo
~~~

Stdout chính xác:

~~~text
Inheritance: SEND to=alice; body=hello
Composition: SEND to=alice; body=hello
Swapped formatter: SEND [bob] welcome
~~~

Hai dòng đầu tạo cùng định dạng đầu ra nhưng đi qua hai cấu trúc khác nhau. Với kế thừa, lớp con phải được tạo riêng cho biến thể triển khai. Với composition, có thể tạo một ComposedNotifier khác và cung cấp BracketFormatter mà không cần tạo lớp con mới của Notifier. Thành phần formatter được chọn khi khởi tạo; nếu cần thay đổi sau đó, hãy thiết kế cơ chế cấu hình hoặc thay thế rõ ràng thay vì ngầm làm đối tượng mutable.

Ví dụ cố ý giữ đơn giản để làm rõ quan hệ giữa các kiểu. Trong ứng dụng thực, quy trình chuẩn bị và gửi thông báo có thể cần kiểm tra địa chỉ, xử lý lỗi, mã hóa, ghi log và gọi mạng. Những trách nhiệm đó nên được phân chia theo hợp đồng và ranh giới phù hợp, thay vì dồn hết vào một lớp cơ sở hoặc một lớp điều phối lớn.

## 4. Delegation khác với kế thừa như thế nào?

Trong kế thừa, đối tượng lớp con cũng là một thể hiện của lớp cha; nó thừa hưởng API và có thể dùng những phương thức đã kế thừa. Lớp con có thể ghi đè phương thức để thay đổi hành vi đa hình.

Trong delegation, đối tượng ngoài có một tham chiếu đến đối tượng cộng tác và gọi phương thức của nó. Đối tượng ngoài không tự động có toàn bộ API của thành phần. Nó quyết định phần nào được cung cấp ra bên ngoài và có thể bổ sung điều phối, kiểm tra hoặc phối hợp nhiều thành phần.

Một interface thường là ranh giới hữu ích cho delegation vì bên gọi chỉ phụ thuộc vào hợp đồng. Tuy nhiên, interface không bắt buộc phải dùng cùng composition; một lớp có thể triển khai interface bằng kế thừa, bằng logic riêng hoặc bằng cách ủy quyền.

## 5. Bảng so sánh các đánh đổi

| Tiêu chí | Kế thừa triển khai | Composition và delegation |
|---|---|---|
| Quan hệ | Lớp con là một dạng của lớp cha | Đối tượng có hoặc sử dụng thành phần |
| Tái sử dụng | Kế thừa phương thức và trạng thái | Gọi hành vi của thành phần |
| Ghép nhiều hành vi | Bị giới hạn bởi một lớp cha; dễ phát sinh cây lớp | Có thể giữ nhiều thành phần độc lập |
| Thay đổi hành vi | Thường qua ghi đè hoặc lớp con khác | Thường qua cung cấp implementation khác |
| Mức phụ thuộc | Có thể chặt với chi tiết lớp cha | Có thể lỏng hơn nếu phụ thuộc interface |
| Độ phức tạp | Ít mã kết nối lúc đầu, nhưng cây lớp có thể phình to | Thêm constructor và đối tượng cộng tác, nhưng ranh giới rõ hơn |
| Kiểm thử | Có thể cần tạo lớp con hoặc kiểm thử cả lớp cơ sở | Có thể tiêm fake/stub qua interface |
| Phù hợp khi | Có quan hệ chuyên biệt thực sự và hợp đồng cơ sở ổn định | Hành vi cần thay thế, kết hợp hoặc thay đổi độc lập |

Không có cách nào luôn tốt hơn. Composition không loại bỏ mọi chi phí, và kế thừa không phải lúc nào cũng là thiết kế sai. Hãy đánh giá mức độ ổn định của hợp đồng, số lượng biến thể, khả năng cần phối hợp hành vi và mức độ phụ thuộc mà thay đổi trong tương lai có thể tạo ra.

## 6. Một số lỗi thiết kế thường gặp

- **Dùng kế thừa chỉ để lấy một phương thức tiện ích.** Nếu quan hệ “là một” không có ý nghĩa trong miền nghiệp vụ, hãy xem xét một thành phần hoặc phương thức tiện ích phù hợp.
- **Tạo lớp con cho mọi tổ hợp hành vi.** Khi số lớp tăng theo tích của nhiều lựa chọn độc lập, hãy cân nhắc ghép các thành phần thay vì tạo cây kế thừa cho từng tổ hợp.
- **Để lớp con phụ thuộc vào chi tiết nội bộ của lớp cha.** Quá nhiều trạng thái protected hoặc các phương thức gọi chéo làm việc thay đổi lớp cha trở nên rủi ro.
- **Ủy quyền toàn bộ API một cách máy móc.** Chỉ đưa ra những thao tác mà đối tượng ngoài thực sự cần cung cấp; nếu không có trách nhiệm nào ngoài chuyển tiếp, hãy cân nhắc dùng trực tiếp thành phần.
- **Ẩn phụ thuộc bằng cách tự khởi tạo bên trong.** Khi lớp tự tạo một implementation cụ thể, việc thay thế hoặc kiểm thử thường khó hơn. Truyền phụ thuộc qua constructor khi việc cấu hình và thay thế là yêu cầu thực tế.
- **Nhầm composition với sở hữu vòng đời tuyệt đối.** Một tham chiếu đến thành phần không tự nó quyết định ai sở hữu tài nguyên hoặc khi nào tài nguyên được đóng. Quy tắc vòng đời cần được xác định rõ, nhất là với file, kết nối và thread.

## 7. Quy trình chọn giải pháp

1. Xác định phần hành vi nào thực sự giống nhau và phần nào có khả năng thay đổi độc lập.
2. Nếu các kiểu có quan hệ chuyên biệt tự nhiên và cần một quy trình chung ổn định, xem xét lớp cơ sở với hợp đồng rõ ràng.
3. Nếu hành vi là một chính sách hoặc dịch vụ có thể thay thế, định nghĩa interface nhỏ rồi dùng composition và delegation.
4. Tránh để lớp con dựa vào chi tiết nội bộ không được cam kết của lớp cha; tránh để lớp điều phối trở thành một lớp bọc không có trách nhiệm.
5. Kiểm thử cả hành vi chung và biến thể: cùng đầu vào có kết quả mong đợi, thay implementation không làm thay đổi hợp đồng, và lỗi của thành phần được xử lý theo chính sách đã định.

Kế thừa triển khai tái sử dụng mã qua một quan hệ kiểu tương đối chặt. Composition và delegation tái sử dụng bằng cách ghép các cộng tác viên qua hợp đồng. Chọn dựa trên mối quan hệ và cách hệ thống cần thay đổi, rồi giữ cho hợp đồng đủ nhỏ để việc thay thế một triển khai không làm lan rộng thay đổi sang phần còn lại.
