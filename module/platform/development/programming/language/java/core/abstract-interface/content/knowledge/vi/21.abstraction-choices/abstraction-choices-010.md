# Tránh constant interface và cây kế thừa chỉ để tái sử dụng mã

Trong Java, interface và abstract class là công cụ để mô hình hóa hợp đồng, hành vi chung và quan hệ kiểu. Tuy nhiên, dùng interface chỉ để gom hằng số hoặc tạo một cây kế thừa chỉ nhằm lấy lại vài dòng mã thường khiến thiết kế khó hiểu, khó thay đổi và dễ tạo phụ thuộc ngoài ý muốn.

Hai nguyên tắc cần ghi nhớ:

- **Không dùng constant interface:** đừng bắt một lớp `implements` interface chỉ để tham chiếu các hằng số được khai báo trong interface đó.
- **Ưu tiên composition (kết hợp đối tượng) hơn inheritance (kế thừa) khi mục tiêu chỉ là tái sử dụng mã:** hãy dùng quan hệ kế thừa khi kiểu con thực sự có thể thay thế kiểu cha và tuân thủ hợp đồng của kiểu cha.

Điều này không có nghĩa là tránh mọi interface hoặc mọi kế thừa. Interface mô tả hành vi mà nhiều kiểu có thể cung cấp; abstract class có thể chứa trạng thái và triển khai chung khi có quan hệ trừu tượng phù hợp. Vấn đề nằm ở việc chọn công cụ chỉ vì tiện lấy hằng số hoặc dùng lại mã, thay vì phản ánh đúng ý nghĩa của mô hình.

## 1. Constant interface là gì?

Trong Java, các trường được khai báo trong interface mặc nhiên là `public static final`. Vì vậy, interface có thể được viết để chứa các hằng số:

~~~java
public interface HttpConstants {
    int DEFAULT_TIMEOUT_SECONDS = 30;
    int MAX_RETRIES = 3;
}
~~~

Cách này trở thành **constant interface anti-pattern** khi một lớp triển khai interface chỉ để dùng trực tiếp các tên hằng số:

~~~java
// Không nên thiết kế theo cách này.
class HttpClient implements HttpConstants {
    void connect() {
        int timeout = DEFAULT_TIMEOUT_SECONDS;
        // ...
    }
}
~~~

`HttpClient` không phải là một loại `HttpConstants`. Nó chỉ cần dùng một vài giá trị cấu hình, nhưng `implements` lại làm cho các hằng số trở thành một phần của API kiểu và tạo cảm giác rằng lớp có quan hệ kiểu với interface.

Các vấn đề chính:

- **Sai ý nghĩa của quan hệ kiểu:** `implements` nên biểu thị lớp cung cấp hành vi theo hợp đồng của interface.
- **Làm rò rỉ chi tiết triển khai:** hằng số có thể xuất hiện trong API công khai của lớp triển khai, dù người dùng lớp không cần biết nguồn gốc của chúng.
- **Tăng phụ thuộc không cần thiết:** lớp gắn với interface chỉ vì các giá trị dùng chung, khiến việc đổi tên hoặc tổ chức lại hằng số có thể ảnh hưởng nhiều nơi.
- **Khó thay đổi thiết kế:** một interface nên được thiết kế quanh hành vi và hợp đồng; nhóm hằng số thường không cung cấp một hợp đồng hành vi hữu ích.

Đặc biệt, việc lớp triển khai interface để truy cập hằng số không mang lại lợi ích đa hình. Không có hành vi nào được thay thế qua interface; mục tiêu chỉ là rút ngắn cách viết tên hằng số.

## 2. Các cách tổ chức hằng số tốt hơn

Chọn nơi đặt hằng số theo ý nghĩa của dữ liệu, phạm vi sử dụng và quyền sở hữu của nó.

### Cách A: Đặt hằng số trong lớp liên quan

Nếu giá trị chỉ có ý nghĩa đối với một lớp, hãy đặt nó ngay trong lớp đó:

~~~java
public final class HttpClient {
    private static final int DEFAULT_TIMEOUT_SECONDS = 30;
    private static final int MAX_RETRIES = 3;

    public void connect() {
        int timeout = DEFAULT_TIMEOUT_SECONDS;
        // Sử dụng timeout khi kết nối.
    }
}
~~~

Các hằng số `private` không trở thành một phần của API công khai. Người bảo trì cũng dễ xác định giá trị thuộc về lớp nào.

### Cách B: Dùng lớp tiện ích không thể khởi tạo

Khi nhiều lớp thực sự cần dùng chung một nhóm hằng số thuộc cùng một miền, có thể dùng lớp `final` với constructor riêng:

~~~java
public final class HttpDefaults {
    private HttpDefaults() {
        // Không cho phép khởi tạo lớp chứa hằng số.
    }

    public static final int DEFAULT_TIMEOUT_SECONDS = 30;
    public static final int MAX_RETRIES = 3;
}
~~~

Lớp dùng giá trị qua tên đầy đủ:

~~~java
int timeout = HttpDefaults.DEFAULT_TIMEOUT_SECONDS;
~~~

Tên `HttpDefaults` cho biết giá trị thuộc nhóm cấu hình HTTP; nó không giả vờ rằng lớp sử dụng các hằng số là một kiểu con của một hợp đồng nào đó.

Không nên biến một lớp chứa hằng số thành nơi tập hợp mọi giá trị của toàn bộ ứng dụng. Nếu các hằng số thuộc những miền khác nhau, hãy đặt chúng gần kiểu hoặc cấu hình sở hữu chúng. Nếu giá trị thay đổi theo môi trường hoặc cần được kiểm thử, truyền cấu hình vào đối tượng thường tốt hơn việc đọc một hằng số toàn cục.

### Cách C: Dùng enum cho một tập lựa chọn hữu hạn

Nếu dữ liệu đại diện cho một tập giá trị có ý nghĩa và được xác định trước, hãy cân nhắc `enum` thay vì các số nguyên hoặc chuỗi rời rạc:

~~~java
enum RetryMode {
    NONE,
    FIXED_DELAY,
    EXPONENTIAL_BACKOFF
}
~~~

`enum` cho phép kiểu hóa các lựa chọn và dùng `switch` rõ nghĩa. Tuy nhiên, enum không phải cách thay thế cho mọi hằng số; một giá trị số như thời gian chờ vẫn có thể phù hợp với trường `static final` hoặc cấu hình có kiểu.

### Cách D: Static import khi giúp mã dễ đọc

Java hỗ trợ static import:

~~~java
import static java.lang.Math.PI;
~~~

Sau đó có thể dùng `PI` thay vì `Math.PI`. Static import hữu ích khi tên nguồn đã rõ và việc lặp lại tên lớp gây nhiễu. Với hằng số ứng dụng, hãy dùng có chừng mực: nếu tên đơn lẻ không cho biết giá trị đến từ đâu, cách viết `HttpDefaults.DEFAULT_TIMEOUT_SECONDS` thường dễ hiểu hơn.

Static import chỉ thay đổi cách viết tên trong mã nguồn; nó không giải quyết thiết kế constant interface nếu lớp vẫn triển khai interface chỉ để truy cập hằng số.

## 3. Khi nào interface thực sự phù hợp?

Interface nên mô tả một hợp đồng hành vi hoặc khả năng mà các kiểu khác nhau có thể cung cấp. Ví dụ, một chương trình có thể cần nhiều chính sách giảm giá nhưng đều phải trả lời câu hỏi: “Với số tiền này, mức giảm là bao nhiêu?”

~~~java
import java.math.BigDecimal;

interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}
~~~

Interface này có một phương thức trừu tượng, nên có thể được triển khai bằng các lớp khác nhau hoặc biểu đạt bằng lambda khi kiểu đích được xác định. Nó có mục đích rõ ràng: bên gọi phụ thuộc vào hợp đồng tính giảm giá mà không phải biết cách tính cụ thể.

Ngược lại, một interface chỉ có `int TIMEOUT = 30;` không xác định hành vi mà lớp triển khai phải cung cấp. Đừng thêm `implements` chỉ để tránh viết tên lớp trước hằng số.

Interface vẫn có thể khai báo trường hằng số khi hằng số đó là một phần có chủ đích của hợp đồng và có ý nghĩa với người sử dụng interface. Nguyên tắc cần tránh là dùng interface làm namespace tiện lợi cho các giá trị không liên quan đến hợp đồng hành vi.

## 4. Vì sao không nên tạo cây kế thừa chỉ để tái sử dụng mã?

Giả sử hai lớp cần cùng một đoạn xử lý. Ta có thể tạo một lớp cha để đặt đoạn mã đó vào rồi cho cả hai lớp kế thừa. Cách làm này có vẻ tiết kiệm mã, nhưng kế thừa còn tạo ra một quan hệ kiểu: lớp con được xem là một dạng của lớp cha và phải giữ được hợp đồng của lớp cha.

Nếu hai lớp chỉ tình cờ có chung vài bước thực hiện nhưng không có quan hệ “là một”, việc đưa chúng vào cùng cây kế thừa có thể tạo mô hình sai.

Những rủi ro thường gặp:

- **Quan hệ kiểu sai:** lớp con có thể không đáp ứng kỳ vọng của người dùng lớp cha.
- **Phụ thuộc vào chi tiết triển khai:** lớp con có thể dựa vào trường `protected`, thứ tự gọi phương thức hoặc trạng thái nội bộ của lớp cha.
- **Lớp cha thay đổi gây hỏng lớp con:** một thay đổi tưởng như vô hại ở lớp cha có thể làm hành vi lớp con khác đi.
- **Khó kết hợp nhiều khả năng:** Java chỉ cho một lớp trực tiếp kế thừa một lớp khác, nên việc dùng cây kế thừa để ghép các tính năng độc lập nhanh chóng bị hạn chế.
- **Khó kiểm thử:** lớp con thường cần khởi tạo và tuân thủ trạng thái của lớp cha, dù phần tái sử dụng chỉ là một thao tác nhỏ.

Kế thừa phù hợp khi có quan hệ “là một” thực sự, lớp con có thể thay thế lớp cha ở nơi lớp cha được yêu cầu và hợp đồng vẫn đúng. Tái sử dụng mã là lợi ích có thể có của kế thừa, nhưng không đủ để tự nó biện minh cho quan hệ kế thừa.

## 5. Ưu tiên composition và delegation

**Composition** nghĩa là một đối tượng chứa hoặc nhận một đối tượng khác để sử dụng chức năng của nó. **Delegation** (ủy quyền) là việc một đối tượng chuyển một phần công việc cho đối tượng thành phần đó.

Ví dụ, thay vì cho `CheckoutService` kế thừa một lớp giảm giá chỉ để lấy phương thức tính toán, hãy để dịch vụ nhận một `DiscountPolicy`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}

final class NoDiscountPolicy implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return BigDecimal.ZERO.setScale(2);
    }
}

final class TenPercentDiscount implements DiscountPolicy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}

final class CheckoutService {
    private final DiscountPolicy discountPolicy;

    CheckoutService(DiscountPolicy discountPolicy) {
        this.discountPolicy = discountPolicy;
    }

    BigDecimal totalFor(BigDecimal subtotal) {
        BigDecimal discount = discountPolicy.discountFor(subtotal);
        return subtotal.subtract(discount);
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        BigDecimal subtotal = new BigDecimal("100.00");
        CheckoutService checkout =
                new CheckoutService(new TenPercentDiscount());

        BigDecimal total = checkout.totalFor(subtotal);
        System.out.println("Subtotal: " + subtotal);
        System.out.println("Discount: "
                + subtotal.subtract(total).setScale(2));
        System.out.println("Total: " + total);
    }
}
~~~

Lưu đoạn mã trong tệp **CompositionDemo.java**, sau đó biên dịch và chạy với Java 17 trở lên:

~~~bash
javac CompositionDemo.java
java CompositionDemo
~~~

Kết quả stdout:

~~~text
Subtotal: 100.00
Discount: 10.00
Total: 90.00
~~~

Trong ví dụ này, `CheckoutService` không phải là một loại `TenPercentDiscount`; dịch vụ **có một** chính sách giảm giá. Nó chỉ gọi phương thức qua interface `DiscountPolicy`. Có thể thay chính sách giảm giá mà không cần tạo lớp con mới của `CheckoutService`.

Constructor nhận chính sách từ bên ngoài cũng giúp kiểm thử dễ hơn: có thể truyền `NoDiscountPolicy` hoặc một chính sách kiểm thử để kiểm tra kết quả. Trong ứng dụng thực tế, nên xác thực các giá trị đầu vào theo yêu cầu miền nghiệp vụ, chẳng hạn xử lý `null` và không cho phép subtotal âm nếu nghiệp vụ không chấp nhận chúng.

## 6. Dấu hiệu cây kế thừa được tạo chỉ để dùng lại mã

Khi rà soát một lớp `Base*` có nhiều lớp con, đừng chỉ đếm số dòng được chia sẻ. Hãy kiểm tra các câu hỏi gắn trực tiếp với anti-pattern:

1. **Có hợp đồng thay thế thật không?** Nếu client nhận kiểu lớp cha, liệu mọi lớp con có giữ cùng ý nghĩa của các phương thức công khai? Nếu không, quan hệ kế thừa có thể sai dù mã được dùng lại.
2. **Phần tái sử dụng có phải chỉ là tiện ích không?** Nếu lớp cha chỉ có vài hàm định dạng, tính toán hoặc kết nối không gắn với một họ kiểu, hãy cân nhắc helper có phạm vi thích hợp hoặc một đối tượng cộng tác.
3. **Lớp con có phụ thuộc chi tiết nội bộ không?** Việc phải truy cập hàng loạt trường `protected`, gọi `super` theo thứ tự ngầm định hoặc override để vô hiệu hóa logic là dấu hiệu thiết kế mong manh.
4. **Các khả năng có thay đổi độc lập không?** Nếu thêm một phương thức xử lý buộc tạo nhiều lớp con cho mọi tổ hợp, composition với interface theo vai trò có thể làm ranh giới thay đổi rõ ràng hơn.

Composition cũng có chi phí: thêm dependency, constructor và đôi khi lớp chuyển tiếp. Chọn nó khi thành phần có trách nhiệm riêng; nếu chỉ có một hàm thuần nhỏ, helper đơn giản có thể đủ. Với quan hệ “là một” thực sự và một quy trình chung ổn định, kế thừa vẫn là lựa chọn hợp lý.

## 7. Liskov Substitution Principle và hợp đồng của lớp cha

Nguyên tắc thay thế Liskov (LSP) nói rằng đối tượng của kiểu con phải có thể dùng ở nơi yêu cầu kiểu cha mà không phá vỡ những kỳ vọng hợp lệ của bên gọi.

Ví dụ, nếu một lớp cha quy định phương thức `save()` luôn lưu dữ liệu thành công hoặc ném ngoại lệ đã được tài liệu hóa, lớp con không nên âm thầm bỏ qua thao tác lưu chỉ vì muốn tái sử dụng một phương thức tiện ích khác. Việc kế thừa kéo theo trách nhiệm tuân thủ hợp đồng của lớp cha, bao gồm các điều kiện đầu vào, kết quả, bất biến và hành vi có thể quan sát.

Nếu hai lớp chỉ cần chung một hàm định dạng hoặc thuật toán, có thể chuyển phần đó sang một helper có phạm vi hợp lý hoặc một đối tượng dịch vụ riêng. Điều này tránh buộc lớp này phải trở thành lớp con của lớp kia khi chúng không có quan hệ thay thế hợp lệ.

## 8. Abstract class vẫn hữu ích khi có triển khai chung phù hợp

Không nên hiểu “ưu tiên composition” là cấm abstract class. Abstract class có ích khi các lớp con thực sự thuộc cùng một họ khái niệm và chia sẻ trạng thái hoặc một phần thuật toán theo hợp đồng rõ ràng.

Ví dụ, một abstract class `FileProcessor` có thể định nghĩa quy trình chung `process()` và yêu cầu lớp con cung cấp các bước `read()` hoặc `transform()`. Đây là thiết kế kiểu template method: lớp cha kiểm soát quy trình chung, lớp con tùy chỉnh các bước được thiết kế để mở rộng.

Ngược lại, nếu một lớp chỉ kế thừa `BaseUtilities` để lấy một phương thức `formatDate()`, trong khi nó không phải là một loại của `BaseUtilities`, hãy cân nhắc đặt thao tác định dạng trong một lớp hoặc dịch vụ riêng và gọi nó. Đừng tạo các lớp cha tổng quát kiểu `BaseEverything` chỉ để gom nhiều hàm không liên quan.

## 9. Cách chọn giải pháp theo tình huống

- **Một hằng số chỉ dùng trong một lớp:** đặt nó trong lớp đó, thường là `private static final`.
- **Một nhóm hằng số có chung miền:** cân nhắc lớp `final` với constructor riêng, hoặc một kiểu cấu hình phù hợp.
- **Một tập lựa chọn hữu hạn có ý nghĩa:** cân nhắc `enum`.
- **Nhiều lớp cần cùng một hợp đồng hành vi:** định nghĩa interface mô tả hành vi đó.
- **Các lớp cùng một họ, có quan hệ thay thế và triển khai chung rõ ràng:** cân nhắc abstract class hoặc lớp cha cụ thể.
- **Một lớp chỉ cần gọi lại một chức năng của thành phần khác:** dùng composition/delegation.
- **Một thuật toán thuần, nhỏ, không có trạng thái:** cân nhắc phương thức helper có phạm vi thích hợp; không cần dựng cây kế thừa chỉ để chia sẻ nó.

Trước khi thêm interface hoặc lớp cha, hãy tự hỏi: “Quan hệ kiểu này có đúng về mặt nghiệp vụ không? Người dùng có thể dựa vào hợp đồng này không? Nếu không cần tái sử dụng mã, tôi vẫn muốn mối quan hệ này tồn tại chứ?” Nếu câu trả lời cho câu hỏi cuối là không, composition hoặc một helper thường đáng xem xét hơn.

## 10. Lỗi thiết kế thường gặp

- **`implements` chỉ để truy cập hằng số:** chuyển hằng số vào lớp sở hữu hoặc một lớp cấu hình có tên rõ nghĩa.
- **Interface chỉ có trường dữ liệu nhưng tên gợi ý hợp đồng:** thiết kế interface quanh hành vi thực sự cần thiết; giữ hằng số riêng nếu chúng không thuộc hợp đồng.
- **Lớp cha “tiện ích” chứa mọi thứ:** tách các trách nhiệm độc lập thành thành phần nhỏ có tên mô tả đúng nhiệm vụ.
- **Kế thừa để tránh vài dòng trùng lặp:** đánh giá xem trùng lặp có thực sự cần loại bỏ không; nếu có, trích xuất phương thức hoặc dùng một thành phần có trách nhiệm rõ ràng.
- **Lớp con ghi đè để vô hiệu hóa hành vi lớp cha:** đây có thể là dấu hiệu lớp con không tuân thủ hợp đồng hoặc lớp cha có ranh giới trách nhiệm chưa phù hợp.
- **Dùng `protected` để mở trạng thái chỉ nhằm cho lớp con tái sử dụng:** cân nhắc đóng gói trạng thái và cung cấp một phương thức hoặc interface nhỏ thay vì để lớp con phụ thuộc vào chi tiết nội bộ.
- **Composition tạo quá nhiều lớp chuyển tiếp:** chỉ trích xuất thành phần khi nó có trách nhiệm hoặc điểm thay đổi riêng; giữ mã đơn giản khi một helper nhỏ đã đủ.

## 11. Quy trình rà soát thiết kế

1. Xác định lớp đang triển khai interface hoặc kế thừa lớp cha vì lý do gì: hợp đồng kiểu, tái sử dụng hành vi hay chỉ để truy cập hằng số.
2. Với constant interface, chuyển các giá trị về lớp sở hữu, lớp cấu hình hoặc kiểu miền thích hợp; cập nhật cách tham chiếu rõ ràng và bỏ `implements` không có ý nghĩa.
3. Với cây kế thừa dùng để tái sử dụng, kiểm tra quan hệ “là một”, hợp đồng thay thế và sự phụ thuộc của lớp con vào trạng thái hoặc chi tiết của lớp cha.
4. Nếu chỉ cần một khả năng, trích xuất interface hành vi nhỏ hoặc thành phần cụ thể và để lớp gọi nó qua composition/delegation.
5. Viết hoặc chạy kiểm thử cho hành vi trước và sau thay đổi, chú ý kết quả quan sát được và các trường hợp biên.
6. Đặt tên cho interface, abstract class, thành phần và hằng số theo vai trò thực tế của chúng; tránh các tên tổng quát che giấu trách nhiệm.

Thiết kế Java tốt dùng interface để mô tả hành vi, abstract class để chia sẻ triển khai trong một họ kiểu có ý nghĩa, và composition để phối hợp các khả năng độc lập. Tránh constant interface và cây kế thừa chỉ nhằm tái sử dụng mã giúp quan hệ giữa các lớp rõ ràng hơn, giảm phụ thuộc ngoài ý muốn và làm cho việc thay đổi, kiểm thử cũng như bảo trì dễ dàng hơn.