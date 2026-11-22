# Chọn abstract class khi cần trạng thái và quy trình dùng chung

## 1. Ý tưởng chính

Trong Java, nên cân nhắc abstract class khi một nhóm lớp có quan hệ cùng loại, cần giữ dữ liệu theo từng đối tượng và phải thực hiện một quy trình chung. Lớp trừu tượng có thể cung cấp trường dữ liệu, constructor, các phương thức đã cài đặt và những phương thức trừu tượng để lớp con hoàn thiện phần khác biệt.

Ví dụ, nhiều loại báo cáo có thể cùng có tiêu đề, cùng kiểm tra đầu vào, cùng tạo phần đầu và phần tổng kết, nhưng trình bày từng mục theo cách khác nhau. Một abstract class có thể giữ tiêu đề và định nghĩa trình tự tạo báo cáo; các lớp con chỉ quyết định cách trình bày mỗi mục.

Cụm “trạng thái và quy trình dùng chung” là dấu hiệu để xem xét abstract class, không phải quy tắc tuyệt đối. Chọn nó khi phần chung thực sự thuộc về một họ lớp và giúp mô hình dễ hiểu hơn.

## 2. Abstract class cung cấp những gì?

Một abstract class có thể kết hợp các khả năng sau:

- **Trạng thái theo từng instance:** có trường instance để lưu dữ liệu chung, chẳng hạn tiêu đề, cấu hình hoặc thông tin cần cho các bước xử lý. Mỗi đối tượng vẫn có giá trị riêng.
- **Khởi tạo và bất biến:** constructor kiểm tra dữ liệu đầu vào và thiết lập trạng thái hợp lệ. Trường **private final** phù hợp với dữ liệu được gán một lần.
- **Hành vi dùng chung:** các phương thức cụ thể cài đặt phần logic mà mọi lớp con đều cần.
- **Điểm mở rộng:** phương thức trừu tượng yêu cầu lớp con cung cấp phần hành vi khác nhau.
- **Quy trình được kiểm soát:** phương thức cụ thể có thể gọi các bước chung theo một thứ tự rõ ràng. Nếu trình tự không được phép thay đổi ở lớp con, có thể khai báo phương thức đó là **final**.

Không thể tạo instance trực tiếp từ abstract class. Một lớp con cụ thể phải hoàn thiện các phương thức trừu tượng còn thiếu. Constructor của lớp cha vẫn chạy thông qua lời gọi **super(...)** khi tạo đối tượng lớp con.

Abstract class có thể triển khai interface và có thể chứa cả phương thức cụ thể lẫn phương thức trừu tượng. Java chỉ cho một lớp kế thừa trực tiếp từ một lớp cha, nên cần cân nhắc giới hạn kế thừa đơn khi thiết kế hệ thống.

## 3. Phân biệt abstract class, interface và composition

| Nhu cầu | Lựa chọn nên cân nhắc |
| --- | --- |
| Nhiều lớp cùng chia sẻ trạng thái instance và cách khởi tạo | Abstract class |
| Nhiều lớp cần tuân theo một hợp đồng, nhưng không cần chung trạng thái hoặc quy trình | Interface |
| Các lớp cần dùng chung một khả năng nhưng không thuộc cùng một họ kế thừa | Interface hoặc composition |
| Muốn cố định các bước của thuật toán và để lớp con tùy biến một vài bước | Abstract class với Template Method |
| Muốn thay đổi thuật toán hoặc thành phần cộng tác linh hoạt khi chạy | Composition, chẳng hạn truyền một đối tượng chiến lược vào constructor |

Interface vẫn có thể chứa **default** method và **static** method. Tuy nhiên, interface không có trường instance để lưu trạng thái riêng của từng đối tượng; các trường được khai báo trong interface là hằng **public static final**. Vì vậy, khi cần mỗi đối tượng mang trạng thái chung được khởi tạo qua constructor, abstract class thường phù hợp hơn.

Đừng chọn abstract class chỉ để tránh viết vài dòng trùng lặp. Nếu các lớp không có quan hệ “là một loại của” rõ ràng, hoặc cần kết hợp nhiều khả năng độc lập, interface và composition thường giữ thiết kế linh hoạt hơn.

## 4. Ví dụ chạy được với Java 17+

Ví dụ sau tạo báo cáo có tiêu đề và phần tổng kết dùng chung. Báo cáo dạng gạch đầu dòng và báo cáo đánh số chỉ khác cách trình bày từng mục.

Tạo file **Main.java** với toàn bộ nội dung sau:

~~~java
import java.util.List;
import java.util.Objects;

abstract class ReportGenerator {
    private final String title;

    protected ReportGenerator(String title) {
        this.title = Objects.requireNonNull(title, "title");
        if (title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
    }

    public final String generate(List<String> items) {
        Objects.requireNonNull(items, "items");

        StringBuilder out = new StringBuilder();
        appendHeader(out);

        int index = 1;
        for (String item : items) {
            Objects.requireNonNull(item, "items must not contain null");
            appendItem(out, index, item);
            index++;
        }

        out.append("Total: ").append(items.size()).append(" items").append('\n');
        return out.toString();
    }

    private void appendHeader(StringBuilder out) {
        out.append(title).append('\n');
        out.append("-----").append('\n');
    }

    protected abstract void appendItem(StringBuilder out, int index, String item);
}

final class BulletReportGenerator extends ReportGenerator {
    BulletReportGenerator(String title) {
        super(title);
    }

    @Override
    protected void appendItem(StringBuilder out, int index, String item) {
        out.append("- ").append(item).append('\n');
    }
}

final class NumberedReportGenerator extends ReportGenerator {
    NumberedReportGenerator(String title) {
        super(title);
    }

    @Override
    protected void appendItem(StringBuilder out, int index, String item) {
        out.append(index).append(". ").append(item).append('\n');
    }
}

public class Main {
    public static void main(String[] args) {
        ReportGenerator bullets = new BulletReportGenerator("Fruits");
        ReportGenerator numbered = new NumberedReportGenerator("Tasks");

        System.out.println(bullets.generate(List.of("Apple", "Banana")));
        System.out.println(numbered.generate(List.of("Read", "Practice")));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~text
javac Main.java
java Main
~~~

Stdout chính xác:

~~~text
Fruits
-----
- Apple
- Banana
Total: 2 items

Tasks
-----
1. Read
2. Practice
Total: 2 items
~~~

Ví dụ chỉ tạo chuỗi báo cáo trong bộ nhớ; nó không ghi tệp ra đĩa. Có thể thay đầu ra chuỗi bằng thao tác I/O trong một ứng dụng thực tế, đồng thời xử lý lỗi I/O phù hợp.

## 5. Đọc ví dụ theo luồng thực thi

**Trạng thái và constructor.** **ReportGenerator** giữ **title** dưới dạng trường **private final**. Constructor nhận tiêu đề, từ chối **null** và chuỗi rỗng hoặc chỉ có khoảng trắng. Mọi lớp con gọi constructor bằng **super(title)**, nên quy tắc khởi tạo này không bị lặp lại.

**Quy trình dùng chung.** Phương thức **generate** kiểm tra danh sách, tạo bộ đệm, gọi **appendHeader**, duyệt từng mục, gọi **appendItem** rồi thêm tổng số mục. Cả hai lớp con đều sử dụng cùng quy trình đó.

**Điểm tùy biến.** **appendItem** là phương thức **protected abstract**. Lớp con bắt buộc cài đặt cách ghi một mục: **BulletReportGenerator** thêm dấu gạch đầu dòng, còn **NumberedReportGenerator** thêm số thứ tự.

**Giữ nguyên thứ tự các bước.** **generate** được khai báo **final**, nên lớp con không thể thay thế toàn bộ quy trình bằng một cách triển khai khác. Lớp con chỉ tùy biến bước được thiết kế để mở rộng. Đây là ví dụ của mẫu thiết kế Template Method.

**Đa hình.** Hai biến trong **main** đều có kiểu khai báo **ReportGenerator**, nhưng Java gọi phiên bản **appendItem** của đối tượng thực tế. Mã sử dụng không cần kiểm tra từng loại bằng **if** hoặc **switch**.

**Một tệp Java.** Chỉ **Main** là lớp **public**, nên các lớp còn lại có thể đặt cùng tệp **Main.java**. Trong dự án lớn, có thể tách mỗi lớp ra tệp riêng theo quy ước của dự án.

## 6. Template Method: khi nào nên cố định quy trình?

Template Method là cách thiết kế trong đó một phương thức cấp cao định nghĩa các bước của thuật toán, còn một hoặc nhiều phương thức được lớp con cài đặt để thay đổi chi tiết. Trong ví dụ, **generate** là phương thức khuôn mẫu và **appendItem** là điểm mở rộng.

Mẫu này hữu ích khi thứ tự các bước là một phần của quy tắc nghiệp vụ. Ví dụ, xử lý dữ liệu có thể luôn cần kiểm tra đầu vào, chuẩn hóa dữ liệu, xử lý từng phần và tổng hợp kết quả; các loại bộ xử lý chỉ khác cách xử lý từng phần.

Hãy dùng **final** cho phương thức khuôn mẫu khi lớp con thực sự không được thay đổi thứ tự hoặc bỏ qua bước bắt buộc. Nếu lớp con cần thay đổi toàn bộ thuật toán một cách hợp lệ, một phương thức **final** sẽ quá hạn chế; hãy cân nhắc interface chiến lược hoặc composition.

Tránh gọi phương thức có thể override từ constructor của abstract class. Khi constructor lớp cha chạy, lớp con có thể chưa khởi tạo xong các trường của nó. Gọi phương thức override ở giai đoạn này dễ khiến mã lớp con hoạt động trên trạng thái chưa hoàn chỉnh.

## 7. Quy tắc thiết kế trạng thái

- Giữ trường dữ liệu ở phạm vi **private** và cung cấp phương thức truy cập có chủ đích khi cần. Không dùng **protected** cho mọi trường chỉ để lớp con tiện sửa.
- Ưu tiên **final** cho dữ liệu cấu hình được thiết lập một lần. Điều này không tự làm đối tượng bất biến nếu trường chứa một đối tượng mutable, nhưng giúp ngăn việc gán lại tham chiếu.
- Xác thực dữ liệu trong constructor để mọi instance bắt đầu ở trạng thái hợp lệ.
- Tránh để lớp cha chứa trạng thái mutable không rõ quyền sở hữu, vì các lớp con có thể vô tình tạo ra cách cập nhật mâu thuẫn.
- Không đưa dữ liệu theo từng yêu cầu hoặc người dùng vào một trường **static** dùng chung nếu dữ liệu đó phải độc lập giữa các lần xử lý.
- Chỉ đưa trạng thái lên lớp cha khi nó thật sự có ý nghĩa đối với mọi lớp con. Nếu chỉ một loại báo cáo cần một trường, có thể để trường đó ở lớp con.

Trong ví dụ, tiêu đề là dữ liệu riêng của từng instance và không đổi sau khi khởi tạo. Bộ đệm và chỉ số là biến cục bộ trong **generate**, nên chúng không bị chia sẻ giữa các lần gọi.

## 8. Lỗi thường gặp

**Chọn abstract class khi không có quan hệ chung hợp lý.** Chỉ có một vài phương thức giống nhau chưa đủ để tạo quan hệ kế thừa. Nếu các lớp độc lập nhưng cần cùng khả năng, dùng interface hoặc đối tượng cộng tác có thể phù hợp hơn.

**Lặp lại quy trình ở mọi lớp con.** Nếu mọi lớp con đều kiểm tra đầu vào, tạo header và tính tổng theo cùng cách, hãy gom các bước đó vào lớp cha. Mỗi bước chỉ nên được override khi có lý do thiết kế rõ ràng.

**Cho phép lớp con sửa trực tiếp trạng thái chung.** Trường **protected** mutable khiến quy tắc của lớp cha khó kiểm soát. Ưu tiên trường **private**, phương thức rõ mục đích và các điểm mở rộng nhỏ.

**Để phương thức trừu tượng quá rộng.** Một hook nên biểu đạt đúng phần cần thay đổi. Nếu lớp con phải viết lại gần như toàn bộ thuật toán, abstract class có thể đang gom những lớp không thực sự chung quy trình.

**Dùng final ở mọi nơi.** **final** hữu ích để bảo vệ bất biến hoặc trình tự bắt buộc, nhưng không nên dùng máy móc. Xác định rõ phần nào phải ổn định và phần nào là điểm mở rộng hợp lệ.

**Gọi phương thức override từ constructor.** Tránh để constructor của lớp cha gọi phương thức có thể được lớp con thay thế; trạng thái lớp con có thể chưa sẵn sàng.

**Nhầm abstract class với interface.** Abstract class có thể giữ trạng thái instance và constructor. Interface mô tả hợp đồng mà nhiều kiểu có thể triển khai, kể cả khi chúng đã kế thừa những lớp cha khác nhau.

## 9. Checklist ra quyết định

Trước khi tạo abstract class, hãy tự hỏi:

1. Các lớp có thực sự là những biến thể của cùng một khái niệm không?
2. Chúng có cần cùng trạng thái instance hoặc cùng quy tắc khởi tạo không?
3. Có một quy trình chung mà mọi lớp con nên tuân thủ không?
4. Có thể xác định một vài điểm mở rộng rõ ràng thay vì cho phép lớp con thay đổi mọi thứ không?
5. Có thể dùng interface hoặc composition để chia sẻ khả năng mà không buộc các lớp vào một hệ thống kế thừa không cần thiết không?

Nếu câu trả lời cho các câu hỏi về trạng thái và quy trình chung là có, abstract class là lựa chọn đáng xem xét. Nếu nhu cầu chủ yếu là mô tả một hợp đồng, interface thường đủ. Khi cần thay đổi hành vi linh hoạt và kết hợp nhiều thành phần, composition thường giúp giảm sự phụ thuộc vào cấu trúc kế thừa.

Mục tiêu là đặt phần trạng thái và quy trình thực sự dùng chung vào một nơi, đồng thời giữ cho các lớp con chỉ chịu trách nhiệm về phần hành vi khác biệt của chúng.