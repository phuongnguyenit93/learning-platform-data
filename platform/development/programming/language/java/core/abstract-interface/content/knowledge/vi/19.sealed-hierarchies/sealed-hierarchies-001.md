# Sealed hierarchy trong Java 17: kiểm soát các kiểu con trực tiếp

## 1. Vấn đề mà sealed giải quyết

Trong thiết kế hướng đối tượng, đa hình cho phép một biến có kiểu cha tham chiếu đến nhiều kiểu con. Tuy nhiên, có những mô hình nghiệp vụ mà tập kiểu con hợp lệ cần được giới hạn rõ ràng. Ví dụ, một biểu thức có thể chỉ là số hoặc phép cộng; một khoản thanh toán có thể chỉ thuộc một số loại đã được hệ thống công nhận.

Nếu dùng một class hoặc interface thông thường, bất kỳ mã nào đáp ứng điều kiện truy cập và kế thừa đều có thể khai báo thêm kiểu con. Điều đó đôi khi làm mô hình khó kiểm soát: mã xử lý có thể gặp một kiểu ngoài dự kiến, các quy tắc nghiệp vụ bị phân tán, hoặc API công khai vô tình cho phép mở rộng mà tác giả không định hỗ trợ.

Java 17 chuẩn hóa **sealed classes và sealed interfaces** để giới hạn tập kiểu được phép kế thừa hoặc triển khai trực tiếp một kiểu. Từ khóa `sealed` thể hiện rằng kiểu cha có một danh sách các kiểu con trực tiếp được cho phép. Danh sách đó được khai báo bằng `permits`, hoặc được trình biên dịch suy ra trong trường hợp hợp lệ.

Sealed không loại bỏ đa hình. Nó cho phép tiếp tục dùng một kiểu cha chung trong khi đặt ra ranh giới rõ ràng cho cây kế thừa. Từng nhánh sau đó có thể đóng hoàn toàn, tiếp tục giới hạn bằng sealed, hoặc mở rộng tự do bằng non-sealed.

## 2. Cú pháp cơ bản

~~~java
public sealed class Shape
        permits Circle, Rectangle {
    // Trạng thái và hành vi chung của Shape
}

public final class Circle extends Shape {
    // Nhánh này không cho phép kế thừa tiếp
}

public non-sealed class Rectangle extends Shape {
    // Nhánh này cho phép các kiểu khác kế thừa tiếp
}
~~~

Đây là ví dụ minh họa cú pháp và cần đặt các kiểu public trong những tệp tương ứng nếu sử dụng đúng nguyên dạng. Một sealed class có thể là abstract hoặc concrete. Khi khai báo abstract, ta vẫn giới hạn được các kiểu có quyền kế thừa nó, nhưng không thể khởi tạo trực tiếp kiểu cha.

Các từ khóa có ý nghĩa khác nhau:

- `sealed`: kiểu này giới hạn những kiểu được phép kế thừa hoặc triển khai trực tiếp.
- `permits`: liệt kê những kiểu con trực tiếp được cho phép.
- `final`: kiểu con này không thể có lớp con tiếp theo.
- `non-sealed`: mở lại nhánh kế thừa tại kiểu con này; các kiểu khác có thể kế thừa hoặc triển khai nó theo quy tắc thông thường.
- `sealed` trên một kiểu con: tiếp tục đặt giới hạn cho thế hệ kiểu con kế tiếp.

Một kiểu con trực tiếp được phép của sealed class phải là `final`, `sealed` hoặc `non-sealed`. Record vốn đã là kiểu final ngầm định, vì vậy một record có thể trực tiếp triển khai sealed interface mà không cần ghi từ khóa `final`.

## 3. Kiểm soát kiểu con trực tiếp, không phải mọi hậu duệ

Tác dụng cốt lõi của sealed là kiểm soát **các kiểu con trực tiếp**. Cây kế thừa nhiều tầng vẫn có thể tồn tại; quy tắc của từng nhánh quyết định cây đó tiếp tục mở rộng như thế nào.

~~~java
sealed class Message permits EmailMessage, SystemMessage {
}

final class EmailMessage extends Message {
}

non-sealed class SystemMessage extends Message {
}

class AlertMessage extends SystemMessage {
}
~~~

Trong ví dụ này:

- `Message` chỉ cho phép `EmailMessage` và `SystemMessage` kế thừa trực tiếp.
- `EmailMessage` là final, nên không thể có lớp con.
- `SystemMessage` là non-sealed, nên nhánh này được mở lại. `AlertMessage` có thể kế thừa `SystemMessage`, nhưng không vì thế mà trở thành một kiểu con trực tiếp được liệt kê của `Message`.

Nếu thay `SystemMessage` bằng một kiểu con sealed, kiểu con đó phải có danh sách các kiểu được phép mở rộng nó. Như vậy, sealed cho phép giới hạn cây kế thừa ở nhiều tầng, trong khi non-sealed mở một nhánh cụ thể. Không thể đồng thời khai báo cùng một class là final, sealed và non-sealed; chúng là những lựa chọn loại trừ nhau cho khả năng kế thừa của kiểu đó.

## 4. Sealed interface cũng giới hạn tập kiểu triển khai

Sealed áp dụng cho cả class và interface. Với sealed interface, danh sách `permits` có thể chứa class triển khai trực tiếp hoặc interface con trực tiếp. Các kiểu được phép phải tuân theo quy tắc tương ứng: class triển khai trực tiếp cần là final, sealed hoặc non-sealed; interface con cần là sealed hoặc non-sealed vì interface không thể là final.

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

Hai record trên đều final ngầm định. Do đó, chúng là các lá đóng của phân cấp `Result`: mã bên ngoài không thể tạo một record khác kế thừa từ Success hoặc Failure, và không thể thêm một kiểu triển khai trực tiếp tùy ý cho Result.

Sealed interface hữu ích khi một API cần biểu diễn một tập trường hợp đã biết. Ví dụ, kết quả xử lý có thể là thành công hoặc thất bại; một lệnh có thể thuộc một số loại được xác định; một sự kiện miền có thể nằm trong một tập kiểu được quản lý. Mã gọi vẫn có thể nhận giá trị qua interface chung, còn tác giả API kiểm soát được các kiểu được phép xuất hiện trực tiếp trong phân cấp.

## 5. Ví dụ Java 17 chạy được

Chương trình dưới đây dùng sealed interface để biểu diễn hai loại thanh toán. Các record là kiểu con trực tiếp được phép và cung cấp dữ liệu bất biến cho từng trường hợp.

~~~java
import java.math.BigDecimal;

sealed interface Payment permits CardPayment, CashPayment {
}

record CardPayment(String lastFour) implements Payment {
}

record CashPayment(BigDecimal amount) implements Payment {
}

public class PaymentDemo {
    public static void main(String[] args) {
        Payment card = new CardPayment("4242");
        Payment cash = new CashPayment(new BigDecimal("12.50"));

        printPayment(card);
        printPayment(cash);
    }

    private static void printPayment(Payment payment) {
        if (payment instanceof CardPayment card) {
            System.out.println("Card ending in " + card.lastFour());
        } else if (payment instanceof CashPayment cash) {
            System.out.println("Cash amount: " + cash.amount().toPlainString());
        } else {
            throw new IllegalStateException(
                    "Unexpected payment type: " + payment.getClass().getName());
        }
    }
}
~~~

Lưu toàn bộ chương trình vào tệp `PaymentDemo.java`, sau đó biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac PaymentDemo.java
java PaymentDemo
~~~

Kết quả stdout:

~~~text
Card ending in 4242
Cash amount: 12.50
~~~

Ở đây, biến `payment` có kiểu khai báo Payment nhưng có thể tham chiếu đến CardPayment hoặc CashPayment. Phương thức `printPayment` dùng pattern matching cho `instanceof`, một tính năng đã được hoàn thiện từ Java 16. Nhánh cuối vẫn phòng vệ trước kiểu ngoài dự kiến ở cấp chạy; sealed giúp trình biên dịch biết tập kiểu con trực tiếp hợp lệ, nhưng chuỗi `if/else` không tự được trình biên dịch xác nhận là đầy đủ.

Pattern matching cho `switch` vẫn là tính năng preview trong Java 17. Không nên dùng cú pháp type-pattern switch như thể nó đã là cú pháp chuẩn không cần cờ preview của Java 17. Ví dụ trên chỉ dùng cú pháp Java 17 thông thường và không yêu cầu bật preview.

## 6. Quy tắc của permits và vị trí khai báo

Thông thường, viết rõ danh sách các kiểu con trực tiếp:

~~~java
sealed interface Command permits StartCommand, StopCommand {
}
~~~

Tên trong `permits` phải xác định các kiểu con trực tiếp được cho phép. Khai báo danh sách không tự tạo các kiểu đó; chúng phải thực sự tồn tại và kế thừa hoặc triển khai đúng kiểu cha. Trình biên dịch kiểm tra các quan hệ này.

Trong trường hợp tất cả kiểu con trực tiếp được khai báo trong cùng compilation unit, có thể bỏ `permits` để trình biên dịch suy ra danh sách. Ví dụ khái niệm:

~~~java
sealed interface Command {
}

final class StartCommand implements Command {
}

final class StopCommand implements Command {
}
~~~

Khi sử dụng dạng suy luận, hãy giữ các khai báo kiểu con trực tiếp trong cùng tệp nguồn với kiểu sealed để trình biên dịch có thể suy ra tập cho phép. Nếu các kiểu nằm ở những tệp khác, hãy khai báo `permits` rõ ràng.

Các kiểu con được phép còn phải tuân thủ ranh giới module/package của Java:

- Trong named module, kiểu sealed và các kiểu con được phép phải thuộc cùng module; chúng có thể nằm ở các package khác nhau trong module đó.
- Khi chạy trong unnamed module, kiểu sealed và các kiểu con được phép phải thuộc cùng package.

Những quy tắc này làm cho tập kiểu con được phép có thể được kiểm tra ở thời điểm biên dịch và giúp tránh một kiểu ở module hoặc package không phù hợp tự ý mở rộng phân cấp.

## 7. So sánh final, sealed và non-sealed

| Modifier | Khả năng kế thừa | Khi nên dùng |
|---|---|---|
| `final` | Không cho phép kiểu con kế thừa tiếp. | Một kiểu lá đã hoàn chỉnh, không cần mở rộng. |
| `sealed` | Chỉ các kiểu được phép mới được kế thừa hoặc triển khai trực tiếp. | Cần một tập kiểu con có kiểm soát. |
| `non-sealed` | Mở lại khả năng kế thừa tại nhánh này. | Muốn giới hạn các nhánh trực tiếp của cha nhưng cho phép một nhánh được mở rộng tự do. |

Chọn modifier theo hợp đồng mà API muốn công bố. Dùng final khi một kiểu cần đóng hoàn toàn. Dùng sealed khi các kiểu con hợp lệ đã được xác định và nên được kiểm soát. Dùng non-sealed khi cần một điểm mở rộng có chủ đích bên trong phân cấp sealed.

Sealed không thay thế modifier truy cập như public, protected hoặc private. Quyền truy cập quyết định mã nào có thể nhìn thấy hoặc sử dụng kiểu; sealed quyết định kiểu nào được phép trở thành kiểu con trực tiếp. Hai nhóm quy tắc giải quyết hai vấn đề khác nhau và cùng có thể áp dụng cho một API.

## 8. Lợi ích và giới hạn trong thiết kế

**Lợi ích chính** là làm rõ ranh giới của mô hình miền. Khi tập kiểu con trực tiếp được kiểm soát, người đọc API biết những trường hợp nào được tác giả hỗ trợ. Việc thêm một trường hợp mới vào phân cấp cũng trở thành thay đổi có chủ đích, thay vì một kiểu triển khai bất kỳ có thể xuất hiện từ mã bên ngoài.

Sealed cũng hỗ trợ phân tích đầy đủ trường hợp trong các tính năng ngôn ngữ hiểu phân cấp sealed, chẳng hạn pattern matching cho switch ở các phiên bản Java hỗ trợ tính năng đó. Tuy nhiên, không nên nhầm lợi ích này với việc mọi cấu trúc điều kiện đều được trình biên dịch chứng minh là đầy đủ. Một chuỗi if/else như ví dụ trên vẫn có thể cần nhánh dự phòng.

**Giới hạn cần cân nhắc** là sealed tạo ra ràng buộc mở rộng. Nếu thiết kế thư viện vốn cần cho bên thứ ba tự do thêm triển khai, việc đóng danh sách kiểu con có thể không phù hợp. Trong thư viện đã phát hành, thay đổi danh sách kiểu con được phép cũng có thể ảnh hưởng đến mã nguồn hoặc binary của người dùng tùy cách phân cấp được sử dụng. Vì vậy, hãy quyết định ranh giới mở rộng ngay khi thiết kế API và ghi rõ các nhánh nào là mở, nhánh nào là đóng.

Không dùng sealed chỉ vì có thể dùng. Nó có giá trị khi giới hạn kiểu con phản ánh quy tắc nghiệp vụ hoặc hợp đồng API thực sự. Với một abstraction cần được mở rộng tùy ý, class hoặc interface thông thường có thể là lựa chọn phù hợp hơn.

## 9. Lỗi thường gặp

- **Quên khai báo cách xử lý kế thừa của kiểu con trực tiếp.** Một class được permits cần là final, sealed hoặc non-sealed. Record là final ngầm định; interface con không thể khai báo final.
- **Nhầm permits với danh sách mọi hậu duệ.** permits chỉ liệt kê kiểu con trực tiếp. Các thế hệ tiếp theo được kiểm soát bởi modifier trên từng nhánh.
- **Đặt kiểu con ngoài module/package được phép.** Kiểm tra quy tắc named module hoặc unnamed module khi compiler báo lỗi về vị trí kiểu con.
- **Dùng non-sealed nhưng mong nhánh đó vẫn đóng.** non-sealed chủ ý mở lại kế thừa tại nhánh được đánh dấu.
- **Cho rằng sealed tự động làm mọi xử lý switch đầy đủ trên Java 17.** Pattern matching cho switch ở Java 17 còn là preview; cần dùng đúng phiên bản và tùy chọn biên dịch nếu chủ động thử tính năng preview.
- **Cho rằng sealed là cơ chế phân quyền truy cập.** Nó giới hạn kiểu con hợp lệ; nó không thay thế kiểm soát truy cập, xác thực hoặc phân quyền ở tầng ứng dụng.

## 10. Ghi nhớ

Java 17 sealed class/interface giới hạn những kiểu có thể kế thừa hoặc triển khai trực tiếp một kiểu cha. Danh sách đó được nêu bằng `permits` hoặc được suy ra khi các kiểu con trực tiếp nằm trong cùng compilation unit. Mỗi nhánh trực tiếp tiếp tục quyết định khả năng mở rộng: final đóng nhánh, sealed tiếp tục giới hạn, còn non-sealed mở nhánh trở lại. Cơ chế này giữ được tính đa hình trong khi làm cho ranh giới của phân cấp kiểu rõ ràng và có thể kiểm tra khi biên dịch.