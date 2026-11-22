# Chọn interface cho vai trò chung của các lớp không cùng họ

Một interface giúp các lớp có quan hệ kế thừa khác nhau cùng đảm nhiệm một **vai trò chung**. Ta chọn interface khi muốn một đoạn mã làm việc với một khả năng hoặc hợp đồng ổn định, bất kể đối tượng thực tế thuộc lớp nào. Ví dụ, một hóa đơn và một phiếu hỗ trợ không cần có cùng lớp cha nghiệp vụ để đều có thể cung cấp một dòng báo cáo.

Ý tưởng cốt lõi là: **mã gọi phụ thuộc vào vai trò mà nó cần, còn từng lớp tự chịu trách nhiệm thực hiện vai trò đó**. Interface tạo ra ranh giới rõ giữa điều người dùng của đối tượng có thể yêu cầu và cách mỗi lớp đáp ứng yêu cầu ấy.

## 1. Interface biểu diễn vai trò, không phải họ hàng lớp

Giả sử ứng dụng có các kiểu **Invoice**, **SupportTicket** và **UserAccount**. Chúng mô hình hóa các khái niệm khác nhau; ép chúng kế thừa cùng một lớp chỉ để dùng chung một method có thể tạo ra quan hệ phân loại không đúng với nghiệp vụ.

Nếu nhiều đối tượng có thể cung cấp một dòng tóm tắt để đưa vào báo cáo, hãy mô tả vai trò đó bằng interface:

~~~java
public interface Reportable {
    String reportLine();
}
~~~

Hợp đồng trên nói rằng mọi đối tượng **Reportable** phải cung cấp một chuỗi báo cáo. Interface không quy định chuỗi được tạo bằng cách nào, dữ liệu nào được lưu, hoặc lớp triển khai có những method riêng nào. Mỗi lớp hiện thực hóa hợp đồng theo dữ liệu và quy tắc của chính nó.

Lớp triển khai dùng từ khóa **implements** và phải cung cấp các method trừu tượng được yêu cầu:

~~~java
final class Invoice implements Reportable {
    @Override
    public String reportLine() {
        return "Invoice ...";
    }
}

final class SupportTicket implements Reportable {
    @Override
    public String reportLine() {
        return "Ticket ...";
    }
}
~~~

Đoạn trên minh họa cấu trúc; method trả chuỗi cố định chỉ để thấy chữ ký. Ví dụ chạy đầy đủ ở phần tiếp theo sẽ sử dụng dữ liệu thật của từng đối tượng.

**Invoice** và **SupportTicket** không cần kế thừa lẫn nhau hay chia sẻ một lớp cha nghiệp vụ. Chúng chỉ cam kết cùng thực hiện vai trò **Reportable**. Mỗi lớp vẫn có thể có constructor, field, method và quy tắc riêng.

## 2. Ví dụ Java 17+ có thể chạy

Lưu nội dung sau vào tệp **ReportableDemo.java**. Ví dụ có hai lớp miền độc lập và một dịch vụ chỉ biết interface.

~~~java
import java.util.List;

interface Reportable {
    String reportLine();
}

final class Invoice implements Reportable {
    private final String number;
    private final long totalCents;

    Invoice(String number, long totalCents) {
        this.number = number;
        this.totalCents = totalCents;
    }

    @Override
    public String reportLine() {
        return "Invoice " + number + ": " + totalCents + " cents";
    }
}

final class SupportTicket implements Reportable {
    private final int id;
    private final String status;

    SupportTicket(int id, String status) {
        this.id = id;
        this.status = status;
    }

    @Override
    public String reportLine() {
        return "Ticket #" + id + ": " + status;
    }
}

final class ReportPrinter {
    static void printAll(List<? extends Reportable> items) {
        for (Reportable item : items) {
            System.out.println(item.reportLine());
        }
    }
}

public class ReportableDemo {
    public static void main(String[] args) {
        List<Reportable> items = List.of(
            new Invoice("INV-42", 12_500L),
            new SupportTicket(17, "OPEN")
        );

        ReportPrinter.printAll(items);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac ReportableDemo.java
java ReportableDemo
~~~

Đầu ra:

~~~text
Invoice INV-42: 12500 cents
Ticket #17: OPEN
~~~

Điểm quan trọng nằm ở **ReportPrinter**: nó không cần kiểm tra **instanceof Invoice**, **instanceof SupportTicket**, hoặc ép kiểu về lớp cụ thể. Vòng lặp chỉ gọi **reportLine()** qua kiểu **Reportable**. Khi chương trình chạy, Java chọn phần triển khai đúng theo lớp thực tế của mỗi đối tượng; đó là đa hình.

Nếu sau này thêm **UserAccount implements Reportable**, dịch vụ in báo cáo vẫn có thể xử lý đối tượng mới mà không cần thêm nhánh điều kiện hay sửa **ReportPrinter**. Điều này chỉ đúng khi lớp mới thực sự đáp ứng ý nghĩa của hợp đồng báo cáo.

## 3. Vì sao cách này hữu ích?

- **Giảm phụ thuộc vào lớp cụ thể.** Dịch vụ chỉ cần biết khả năng được cung cấp, nên thay đổi cách triển khai ít lan sang mã gọi.
- **Kết hợp các kiểu không cùng nhánh kế thừa.** Một danh sách hoặc method có thể tiếp nhận nhiều lớp khác nhau miễn là chúng có cùng vai trò.
- **Dễ mở rộng.** Lớp mới có thể tham gia hợp đồng mà không phải thay đổi tất cả nơi đang sử dụng hợp đồng ấy.
- **Dễ kiểm thử.** Có thể tạo một triển khai giả của interface để kiểm tra dịch vụ mà không phải dựng toàn bộ hệ thống thật.
- **Cho phép một lớp có nhiều vai trò.** Java chỉ cho một lớp kế thừa trực tiếp một lớp cha, nhưng lớp có thể **implements** nhiều interface. Chẳng hạn, một kiểu có thể vừa **Reportable** vừa thực hiện một vai trò **Exportable** nếu cả hai đều có ý nghĩa với nó.

Interface vì vậy thường hữu ích ở ranh giới giữa các thành phần: dịch vụ nhận một vai trò, repository cung cấp hợp đồng truy cập dữ liệu, hoặc một bộ xử lý chấp nhận các đối tượng có chung khả năng.

## 4. Chọn hợp đồng đủ nhỏ và đúng nghĩa

Tên interface nên nói rõ **vai trò hoặc khả năng** mà đối tượng cam kết cung cấp. Ví dụ: **Reportable**, **Closeable**, **Comparable&lt;T&gt;** hoặc một interface nghiệp vụ như **Refundable**. Tránh đặt tên quá chung chung như **Common**, **Helper** hoặc **Data** nếu tên đó không làm rõ hợp đồng.

Trước khi tạo interface, hãy xác định:

1. Đoạn mã gọi cần yêu cầu hành động hoặc thông tin nào?
2. Các lớp dự kiến triển khai có thể đáp ứng cùng một ý nghĩa của method đó không?
3. Chữ ký method có đủ rõ về tham số, kiểu trả về và điều kiện lỗi không?
4. Có khả năng nhiều lớp hoặc nhiều thành phần sẽ cần vai trò này không?
5. Hợp đồng có thể ổn định khi phần triển khai thay đổi không?

Một interface tốt thể hiện được điều bên gọi có quyền trông đợi. Nếu **reportLine()** được quy định là trả về một dòng báo cáo có thể hiển thị cho người dùng, mọi lớp triển khai nên đáp ứng ý nghĩa đó. Nếu một lớp trả về chuỗi rỗng trong khi lớp khác trả về một thông báo lỗi không liên quan, chúng có thể đang bị ép vào một hợp đồng không phù hợp.

Không cần tạo interface cho mọi lớp. Nếu hiện chỉ có một triển khai, không có ranh giới cần thay thế hoặc đa hình, và hợp đồng chưa có giá trị riêng, một method thông thường có thể đơn giản hơn. Hãy tạo interface khi nó thể hiện một vai trò có ý nghĩa, hỗ trợ thay thế triển khai, hoặc giúp giảm phụ thuộc trong thiết kế.

## 5. Interface hay abstract class?

| Nhu cầu | Nên cân nhắc |
| --- | --- |
| Các lớp không cùng họ cần cung cấp cùng một khả năng | Interface |
| Các lớp cần chung một hợp đồng nhưng có cách triển khai khác nhau | Interface |
| Nhiều lớp cùng chia sẻ trạng thái instance, constructor hoặc code triển khai nền tảng | Abstract class |
| Muốn một lớp có thể kết hợp nhiều vai trò độc lập | Interface |
| Muốn biểu diễn một quan hệ phân loại có trạng thái và hành vi chung | Có thể dùng abstract class, nếu quan hệ đó đúng với mô hình miền |

Interface không có trạng thái instance thông thường và không có constructor. Field được khai báo trong interface là hằng số **public static final**; method trừu tượng mặc định là **public**. Một abstract class có thể giữ field instance, constructor, method **protected** và phần triển khai dùng chung. Một lớp có thể kế thừa một abstract class và đồng thời triển khai nhiều interface.

Đừng chọn interface chỉ vì “dùng interface luôn tốt hơn”. Hãy chọn dựa trên quan hệ thực tế và trách nhiệm cần biểu diễn. Nếu hai lớp không có chung trạng thái hay nền tảng triển khai, nhưng có cùng một khả năng, interface thường là ranh giới phù hợp.

## 6. Một vài chi tiết Java cần nhớ

- **Triển khai method phải đủ khả năng truy cập.** Method trừu tượng trong interface là **public**, nên method triển khai phải là **public**; không thể giảm xuống package-private hoặc **protected**.
- **Một interface có thể mở rộng interface khác.** **interface AdvancedReportable extends Reportable** có thể bổ sung hợp đồng; lớp triển khai interface con phải đáp ứng cả các method trừu tượng được kế thừa.
- **Một lớp có thể triển khai nhiều interface.** Điều này cho phép kết hợp các vai trò độc lập, nhưng không nên thêm interface mà lớp không thể thực hiện đúng ý nghĩa.
- **Interface có thể có default và static method.** **default** phù hợp với hành vi mặc định có ý nghĩa chung cho mọi lớp triển khai; **static** thuộc về interface. Từ Java 9, interface cũng có thể có **private** method để chia sẻ logic nội bộ giữa các method của chính interface.
- **Cẩn thận với nhiều default method trùng chữ ký.** Nếu một lớp nhận các triển khai mặc định xung đột từ nhiều interface, lớp đó phải giải quyết xung đột bằng cách tự triển khai method.
- **Interface không tự bảo đảm hành vi đúng.** Trình biên dịch kiểm tra chữ ký, nhưng người thiết kế và kiểm thử vẫn phải bảo đảm mỗi lớp tôn trọng ý nghĩa của hợp đồng.

## 7. Những lỗi thiết kế thường gặp

- **Dùng lớp cha chỉ để gom những lớp không cùng bản chất.** Nếu các lớp chỉ chia sẻ một khả năng, ép chúng vào cùng một cây kế thừa có thể làm sai mô hình miền. Hãy xem xét interface theo vai trò.
- **Đưa quá nhiều method không liên quan vào một interface.** Lớp chỉ cần một phần hợp đồng sẽ bị buộc triển khai các method không có ý nghĩa. Tách thành các interface nhỏ theo vai trò cụ thể.
- **Đặt tên theo chi tiết triển khai.** Tên như **UsesArrayList** gắn hợp đồng với cách cài đặt. Tên như **Reportable** thể hiện điều bên gọi có thể làm.
- **Kiểm tra lớp cụ thể ở khắp nơi.** Nhiều nhánh **instanceof** thường là dấu hiệu đoạn mã có thể làm việc qua một interface chung; tuy vậy, chỉ trừu tượng hóa khi các nhánh thực sự có chung ý nghĩa.
- **Dùng default để che giấu khác biệt nghiệp vụ.** Một triển khai mặc định không phù hợp cho mọi lớp có thể làm hợp đồng khó hiểu. Chỉ chia sẻ hành vi khi nó đúng về mặt ngữ nghĩa.
- **Tạo interface chỉ để đổi tên một method.** Nếu không có vai trò, hợp đồng, ranh giới thay thế hoặc lợi ích đa hình nào, interface mới có thể chỉ làm tăng số kiểu cần hiểu.

Khi xem xét thiết kế, hãy thử hỏi: “Nếu thêm một lớp mới không cùng họ với các lớp hiện tại nhưng có cùng khả năng, đoạn mã gọi có thể dùng nó mà không cần biết lớp cụ thể không?” Nếu có, một interface theo vai trò có thể là hợp đồng đúng. Nếu câu trả lời là không vì các lớp không thật sự cùng ý nghĩa, hãy điều chỉnh hợp đồng thay vì ép chúng vào cùng một interface.

## 8. Checklist áp dụng

- [ ] Interface có tên thể hiện rõ vai trò chung.
- [ ] Các lớp triển khai thực sự đáp ứng cùng ý nghĩa của hợp đồng.
- [ ] Bên gọi phụ thuộc vào interface thay vì ép kiểu về lớp cụ thể.
- [ ] Method có chữ ký rõ, mức truy cập đúng và mô tả lỗi phù hợp.
- [ ] Interface không gom các trách nhiệm không liên quan.
- [ ] Không tạo abstraction chỉ để phòng xa khi chưa có lợi ích thiết kế cụ thể.
- [ ] Ví dụ kiểm thử hoặc chạy thử chứng minh nhiều lớp không cùng họ được xử lý qua cùng một hợp đồng.

Hãy xem interface như một cam kết có ý nghĩa: các lớp có thể khác nhau về dữ liệu và cách hoạt động, nhưng đều cung cấp đúng vai trò mà bên gọi cần.