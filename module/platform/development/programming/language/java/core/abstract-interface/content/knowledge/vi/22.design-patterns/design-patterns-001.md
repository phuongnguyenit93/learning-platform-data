# Template Method trong Java: quy trình cố định và các bước abstract

## 1. Ý tưởng chính

**Template Method** là mẫu thiết kế hành vi (behavioral design pattern) dùng khi nhiều lớp cần thực hiện cùng một quy trình tổng thể, nhưng một vài bước bên trong quy trình khác nhau tùy loại đối tượng. Lớp cha định nghĩa thứ tự các bước trong một phương thức khuôn mẫu; các lớp con cung cấp cách thực hiện những bước được giao cho chúng.

Ví dụ, nhiều loại báo cáo đều cần chuẩn bị dữ liệu, xử lý dữ liệu, in tiêu đề, rồi xuất kết quả. Thứ tự này là quy tắc chung và không nên bị mỗi lớp con tự ý đảo lộn. Tuy nhiên, cách lấy dữ liệu hoặc tính toán nội dung có thể thay đổi giữa báo cáo doanh thu và báo cáo tồn kho. Template Method giữ quy trình chung ở một nơi và cho phép các lớp con tùy biến đúng những điểm đã thiết kế.

Tên “Template Method” nói đến phương thức chứa bộ khung thuật toán. Trong Java, phương thức đó thường là một phương thức instance được khai báo `final` trong abstract class, còn các bước thay đổi được khai báo thành phương thức `abstract` hoặc các hook có triển khai mặc định.

## 2. Cấu trúc của mẫu thiết kế

Một Template Method thường có ba thành phần:

- **Lớp cha (abstract class):** sở hữu thuật toán tổng thể và định nghĩa các bước theo đúng thứ tự.
- **Template method:** phương thức gọi lần lượt các bước; thường là `final` để lớp con không ghi đè và phá vỡ thứ tự quy trình.
- **Các bước có thể tùy biến:** phương thức abstract bắt buộc lớp con cài đặt, cùng với hook có hành vi mặc định mà lớp con có thể ghi đè khi cần.

Sơ đồ gọi điển hình:

~~~text
Client
  |
  v
ConcreteClass.templateMethod()   (được kế thừa từ AbstractClass)
  |
  +--> stepA()                   (có thể là bước cố định)
  +--> requiredStep()            (abstract, do lớp con cài đặt)
  +--> optionalHook()            (có mặc định, có thể ghi đè)
  +--> stepB()                   (bước cố định)
~~~

Điểm quan trọng là **lớp cha điều khiển luồng gọi**. Lớp con chỉ cung cấp hành vi tại những điểm mở rộng mà lớp cha công bố. Nếu lớp con được phép thay thế toàn bộ template method, hợp đồng về trình tự chung sẽ yếu đi.

## 3. Ví dụ Java 17 chạy được

Ví dụ dưới đây tạo một quy trình xuất báo cáo. Mọi báo cáo đều in phần mở đầu, thu thập dữ liệu, tính toán, rồi in phần kết thúc. Lớp cha giữ nguyên thứ tự đó; lớp con chỉ cung cấp cách lấy dữ liệu và cách tính tổng.

~~~java
abstract class ReportGenerator {
    // Template Method: giữ nguyên trình tự của toàn bộ quy trình.
    public final void generateReport() {
        printHeader();
        String data = collectData();
        String result = calculate(data);
        afterCalculation(result); // Hook tùy chọn
        printFooter();
    }

    private void printHeader() {
        System.out.println("=== REPORT START ===");
    }

    protected abstract String collectData();

    protected abstract String calculate(String data);

    // Hook có hành vi mặc định; lớp con không bắt buộc ghi đè.
    protected void afterCalculation(String result) {
        System.out.println("Result prepared");
    }

    private void printFooter() {
        System.out.println("=== REPORT END ===");
    }
}

final class SalesReport extends ReportGenerator {
    @Override
    protected String collectData() {
        return "10,20,30";
    }

    @Override
    protected String calculate(String data) {
        int total = 0;
        for (String part : data.split(",")) {
            total += Integer.parseInt(part);
        }
        return "Sales total = " + total;
    }

    @Override
    protected void afterCalculation(String result) {
        System.out.println(result);
    }
}

public class Main {
    public static void main(String[] args) {
        ReportGenerator report = new SalesReport();
        report.generateReport();
    }
}
~~~

Lưu toàn bộ mã vào tệp `Main.java`, sau đó chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Kết quả stdout chính xác:

~~~text
=== REPORT START ===
Sales total = 60
=== REPORT END ===
~~~

Luồng gọi diễn ra như sau:

1. `main` gọi `generateReport()` trên một đối tượng SalesReport thông qua biến có kiểu ReportGenerator.
2. Template method in tiêu đề trước khi yêu cầu dữ liệu.
3. Lời gọi `collectData()` và `calculate(data)` được dispatch đến phần triển khai trong SalesReport.
4. Hook `afterCalculation(result)` cũng được dispatch động và in kết quả.
5. Lớp cha in phần kết thúc, vì vậy lớp con không thể bỏ qua bước này bằng cách ghi đè template method.

Trong ví dụ này, các phương thức `printHeader()` và `printFooter()` là private vì chúng là chi tiết cố định của lớp cha. Hai bước abstract là protected để các lớp con có thể cài đặt chúng. Template method là public final để client có thể gọi và lớp con không thể thay đổi thứ tự toàn bộ thuật toán.

## 4. Vì sao dùng các bước abstract?

Một bước abstract biểu thị hành vi mà mọi lớp con cụ thể bắt buộc phải cung cấp. Nếu lớp cha không thể xác định một triển khai hợp lý chung, khai báo abstract làm rõ rằng thiếu bước đó là một triển khai chưa hoàn chỉnh.

Ví dụ, một lớp cha `DataImporter` có thể định nghĩa template `importData()` theo thứ tự: đọc nguồn, phân tích nội dung, kiểm tra dữ liệu, rồi lưu kết quả. Việc đọc CSV và đọc JSON có thể khác nhau, nên `readSource()` hoặc `parse()` có thể là bước abstract. Các thao tác chung như ghi log hay đo thời gian có thể được triển khai trực tiếp trong lớp cha.

Không nên biến mọi dòng lệnh thành phương thức abstract. Chỉ mở rộng những bước thực sự cần khác nhau giữa các lớp con. Nếu quá nhiều bước được tùy biến, quy trình chung sẽ khó hiểu và các lớp con có thể tạo ra những biến thể không còn tuân theo mục đích ban đầu.

Một lớp có ít nhất một phương thức abstract phải được khai báo abstract. Lớp abstract có thể chứa cả phương thức đã triển khai, trường dữ liệu, constructor và phương thức abstract; nó không thể được khởi tạo trực tiếp bằng `new`. Lớp con cụ thể phải cài đặt mọi phương thức abstract còn thiếu, nếu không lớp con đó cũng phải được khai báo abstract.

## 5. Hook: điểm mở rộng không bắt buộc

Hook là phương thức được lớp cha cung cấp với hành vi mặc định. Lớp con có thể ghi đè hook khi cần thêm hành vi, nhưng không bắt buộc phải làm vậy. Trong ví dụ, `afterCalculation(result)` mặc định in một thông báo; SalesReport ghi đè để in kết quả tính toán.

Hook hữu ích cho các điểm như:

- chạy bước kiểm tra bổ sung trước hoặc sau thuật toán;
- thêm log hoặc thông tin chẩn đoán;
- cho phép lớp con quyết định có thực hiện một hành động tùy chọn hay không;
- điều chỉnh một phần nhỏ của quy trình mà không thay thế toàn bộ template method.

Hook không nhất thiết phải là phương thức không tham số. Nó có thể nhận dữ liệu hoặc trả về giá trị nếu hợp đồng thiết kế yêu cầu. Tuy vậy, cần ghi rõ khi nào hook được gọi và kết quả của hook có ảnh hưởng đến các bước tiếp theo hay không.

Có thể dùng hook boolean để cho phép bỏ qua một bước tùy chọn, nhưng nên bảo đảm trạng thái đó không làm hỏng bất biến của thuật toán. Nếu một bước bắt buộc phải xảy ra, hãy giữ nó cố định trong template method hoặc dùng phương thức abstract để buộc lớp con cung cấp hành vi cần thiết.

## 6. Quyền kiểm soát luồng gọi và dynamic dispatch

Template Method thể hiện nguyên tắc “Hollywood”: lớp cha gọi đến lớp con ở những điểm mở rộng đã xác định. Client chỉ cần gọi một phương thức cấp cao như `generateReport()`; client không cần tự điều phối từng bước.

Khi template method gọi một phương thức instance có thể ghi đè, Java chọn triển khai theo kiểu thực tế của đối tượng tại thời điểm chạy (dynamic dispatch). Vì vậy, lời gọi `collectData()` bên trong ReportGenerator vẫn chạy phương thức SalesReport khi đối tượng thực tế là SalesReport.

Nên khai báo template method là `final` khi việc giữ nguyên thứ tự bước là một phần quan trọng của hợp đồng. Nếu có lý do thực sự để lớp con thay đổi toàn bộ thuật toán, hãy xem xét một thiết kế khác hoặc cân nhắc rõ việc không dùng final. Không nên thêm final máy móc khi lớp cha được thiết kế chủ đích cho phép thay đổi thuật toán tổng thể.

Template method thường là phương thức instance, không phải static, vì các bước tùy biến cần dispatch đến đối tượng lớp con. Các phương thức static không được ghi đè theo cơ chế đa hình instance nên không phù hợp làm các bước tùy biến kiểu này.

## 7. Xử lý lỗi, tài nguyên và thứ tự bước

Khi quy trình có thể thất bại, hãy xác định rõ hành vi khi một bước ném exception. Theo cách gọi tuần tự thông thường, nếu một bước ném exception và exception không được bắt tại chỗ, các bước tiếp theo sẽ không chạy. Ví dụ, nếu `collectData()` thất bại, `calculate()`, hook và `printFooter()` sẽ bị bỏ qua trong triển khai cơ bản.

Nếu quy trình bắt buộc phải giải phóng tài nguyên hoặc chạy thao tác kết thúc ngay cả khi có lỗi, dùng cấu trúc như try/finally hoặc try-with-resources ở lớp cha. Đừng giả định rằng template method tự động chạy mọi bước sau lỗi. Việc log lỗi, rollback, đóng kết nối hoặc phát thông báo thất bại phải là phần được thiết kế rõ ràng.

Cũng cần tránh gọi các phương thức có thể ghi đè từ constructor của lớp cha. Trong lúc constructor lớp cha chạy, lớp con có thể chưa khởi tạo xong các trường của mình; một lời gọi động đến phương thức lớp con khi đó có thể quan sát trạng thái chưa sẵn sàng. Hãy bắt đầu template method sau khi đối tượng đã được khởi tạo hoàn chỉnh, thường thông qua một lời gọi rõ ràng từ client hoặc một phương thức điều phối phù hợp.

## 8. Khi nào nên dùng Template Method?

Mẫu này phù hợp khi:

- Có một thuật toán hoặc quy trình chung với thứ tự bước ổn định.
- Một số bước thay đổi giữa các biến thể, nhưng thứ tự và phần điều phối cần được dùng chung.
- Muốn buộc các lớp con triển khai những bước bắt buộc thông qua phương thức abstract.
- Muốn cung cấp các điểm mở rộng tùy chọn bằng hook mà không nhân bản toàn bộ thuật toán.

Các ví dụ thường gặp gồm quy trình nhập dữ liệu, tạo báo cáo, xử lý tệp, kiểm tra đầu vào, pipeline xử lý, và các quy trình kiểm thử có bước chuẩn bị/thực thi/dọn dẹp chung. Trong từng trường hợp, chỉ nên dùng mẫu khi cấu trúc thuật toán thật sự ổn định và các khác biệt có thể được thể hiện bằng những bước nhỏ, rõ ràng.

## 9. Hạn chế và so sánh với Strategy

Template Method thường dùng kế thừa để thay đổi một số bước. Vì thế, lớp con gắn với cấu trúc của lớp cha và phải tuân thủ hợp đồng mà lớp cha quy định. Nếu có nhiều chiều biến đổi độc lập, số lượng lớp con có thể tăng và các bước tùy biến có thể trở nên khó phối hợp.

**Strategy** giải quyết một tình huống gần giống bằng composition: một đối tượng nhận hành vi có thể thay thế được thông qua một interface chiến lược. Điều này cho phép thay đổi thuật toán tại runtime và kết hợp các hành vi mà không cần tạo lớp con cho mọi tổ hợp. Đổi lại, Strategy có thể cần thêm các interface và đối tượng riêng.

| Tiêu chí | Template Method | Strategy |
|---|---|---|
| Cơ chế chính | Kế thừa và ghi đè một số bước | Composition và ủy quyền cho đối tượng chiến lược |
| Ai giữ thứ tự quy trình? | Template method trong lớp cha | Đối tượng điều phối gọi các chiến lược theo thiết kế |
| Phạm vi thay đổi | Một số bước trong thuật toán chung | Có thể thay thế cả một hành vi/thuật toán |
| Thay đổi hành vi lúc chạy | Thường hạn chế; dựa trên kiểu đối tượng và hook | Tự nhiên hơn vì có thể thay đối tượng chiến lược |
| Rủi ro thiết kế | Phân cấp kế thừa cứng, lớp con phụ thuộc lớp cha | Nhiều đối tượng/interface hơn và cần quản lý việc ủy quyền |

Chọn Template Method khi quy trình chung cần ổn định và các bước thay đổi là một phần tự nhiên của phân cấp kế thừa. Chọn Strategy khi cần hoán đổi thuật toán linh hoạt, ghép các hành vi hoặc tránh tạo thêm nhiều lớp con. Hai mẫu có thể kết hợp nếu quy trình vẫn cố định nhưng một bước cụ thể được ủy quyền cho một Strategy.

## 10. Lỗi thường gặp

- **Lặp lại toàn bộ quy trình trong từng lớp con.** Cách này nhân bản logic và dễ khiến thứ tự bước khác nhau theo thời gian. Hãy giữ phần chung trong template method.
- **Để lớp con ghi đè template method khi thứ tự là bất biến.** Cân nhắc dùng `final` để trình biên dịch ngăn việc ghi đè.
- **Đánh dấu mọi bước là abstract.** Những hành vi có triển khai chung nên được giữ ở lớp cha; chỉ tạo điểm mở rộng khi có lý do rõ ràng.
- **Dùng hook cho một bước bắt buộc.** Hook có mặc định thường có thể không được ghi đè. Nếu lớp con bắt buộc phải cung cấp hành vi, hãy dùng phương thức abstract.
- **Gọi template method từ constructor.** Các phương thức có thể ghi đè có thể chạy trước khi trạng thái lớp con được khởi tạo hoàn chỉnh.
- **Cho rằng các bước sau vẫn chạy khi một bước ném exception.** Trong luồng tuần tự cơ bản, exception chưa được xử lý sẽ ngắt quy trình. Hãy thiết kế finally hoặc try-with-resources nếu cần dọn dẹp.
- **Dùng kế thừa khi các hành vi cần thay đổi độc lập.** Khi cần hoán đổi thuật toán linh hoạt hoặc kết hợp nhiều biến thể, hãy đánh giá Strategy và composition.

## 11. Ghi nhớ

Template Method đặt bộ khung của một thuật toán trong lớp cha và giữ thứ tự các bước ở một nơi. Các phương thức abstract buộc lớp con cung cấp những bước bắt buộc; hook cho phép mở rộng hành vi với triển khai mặc định. Một template method thường được khai báo final để bảo vệ trình tự quy trình. Mẫu này phù hợp khi quy trình ổn định nhưng một số bước thay đổi; nếu cần thay thế thuật toán linh hoạt hoặc kết hợp hành vi độc lập, Strategy dựa trên composition có thể phù hợp hơn.