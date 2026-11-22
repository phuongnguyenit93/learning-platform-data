# Lớp trừu tượng thực thi một phần interface trong Java

Một abstract class có thể nhận hợp đồng từ interface rồi triển khai những phần dùng chung, để các lớp con cụ thể hoàn thiện những hành vi còn phụ thuộc loại đối tượng. Nghĩa vụ chưa thực hiện vẫn tồn tại trong hệ phân cấp; chỉ lớp concrete cuối cùng mới phải có cách triển khai hợp lệ cho tất cả phương thức abstract còn thiếu.

## 1. Ví dụ hoàn chỉnh: lớp nền chia sẻ phần xử lý chung

Chương trình Java 17 sau minh họa interface định nghĩa hợp đồng, abstract class giữ trạng thái và logic dùng chung, còn concrete subclass cung cấp hành vi chuyên biệt. Lưu thành **PartialImplementationDemo.java**:

~~~java
import java.util.Objects;

public class PartialImplementationDemo {
    interface ReportJob {
        void validate();
        String generate();
        void audit(String result);

        default String kind() {
            return "report";
        }
    }

    abstract static class AbstractReportJob implements ReportJob {
        private final String reportName;

        protected AbstractReportJob(String reportName) {
            this.reportName = Objects.requireNonNull(reportName, "reportName");
        }

        @Override
        public final void validate() {
            if (reportName.isBlank()) {
                throw new IllegalArgumentException("reportName is blank");
            }
            System.out.println("validated: " + reportName);
        }

        @Override
        public void audit(String result) {
            System.out.println("audit: " + reportName + " -> " + result);
        }

        protected final String reportName() {
            return reportName;
        }

        // generate() vẫn chưa có thân; abstract class có thể trì hoãn.
    }

    static final class CsvReportJob extends AbstractReportJob {
        CsvReportJob(String reportName) {
            super(reportName);
        }

        @Override
        public String generate() {
            return reportName() + ": csv ready";
        }
    }

    public static void main(String[] args) {
        ReportJob job = new CsvReportJob("Sales");

        System.out.println("kind: " + job.kind());
        job.validate();
        String result = job.generate();
        System.out.println("result: " + result);
        job.audit(result);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 PartialImplementationDemo.java
java PartialImplementationDemo
~~~

Kết quả:

~~~text
kind: report
validated: Sales
result: Sales: csv ready
audit: Sales -> Sales: csv ready
~~~

### Trách nhiệm của từng kiểu

- **ReportJob** mô tả những hành vi người gọi có thể dựa vào. Ba phương thức abstract tạo nghĩa vụ triển khai; **kind()** là default method đã có thân.
- **AbstractReportJob** triển khai **validate()** và **audit()**, giữ trạng thái **reportName**, đồng thời cung cấp helper protected cho lớp con. Nó hợp lệ dù chưa có thân cho **generate()**, vì chính lớp này được khai báo abstract.
- **CsvReportJob** là lớp concrete. Nó kế thừa hai phương thức đã có và chỉ cần cung cấp **generate()**. Sau khi constructor gọi **super(reportName)**, đối tượng cụ thể có thể được tạo bằng **new**.
- **validate()** được đánh dấu final để lớp con không bỏ qua quy tắc kiểm tra chung bằng cách override. **generate()** được để mở cho hành vi riêng của từng loại báo cáo.

## 2. Lớp abstract có thể triển khai bao nhiêu phần?

Một abstract class có thể triển khai **không phương thức nào, một phần hoặc tất cả** các phương thức abstract của interface. Từ khóa abstract không bắt buộc lớp phải chứa một phương thức abstract; ngay cả khi đã có đủ phần thân, lớp vẫn có thể được cố ý giữ lại làm lớp nền không cho tạo đối tượng trực tiếp.

| Tầng kiểu | Trách nhiệm |
| --- | --- |
| Interface | Công bố hợp đồng và những phương thức abstract cần có |
| Abstract class | Đặt trạng thái, constructor, helper và logic chung; có thể trì hoãn một số phương thức |
| Abstract subclass khác | Có thể hoàn thiện thêm một phần rồi tiếp tục để lại phần còn thiếu |
| Concrete subclass | Phải có triển khai hợp lệ cho tất cả nghĩa vụ abstract còn hiệu lực |

Không bắt buộc abstract class phải khai báo lại chữ ký của phương thức nó để lại. Ví dụ **AbstractReportJob** không cần viết lại **public abstract String generate()** để trình biên dịch biết phương thức vẫn còn thiếu. Có thể khai báo lại tường minh nếu muốn nhấn mạnh điểm mở rộng hoặc thêm tài liệu API; việc đó không tạo ra phần thân. Nếu khai báo lại một phương thức interface public, không được giảm mức truy cập xuống protected.

## 3. Khi nào cách thiết kế này hữu ích?

Cách làm này phù hợp khi nhiều lớp cùng một họ cần chia sẻ trạng thái, constructor, kiểm tra dữ liệu, thứ tự xử lý hoặc một phần thuật toán, nhưng vẫn có một bước chuyên biệt cho từng loại.

Ví dụ, các báo cáo CSV và JSON có thể cùng kiểm tra tên báo cáo và ghi audit, trong khi mỗi loại có cách sinh nội dung riêng. Đặt phần chung ở abstract class giúp các lớp con không phải sao chép và giảm nguy cơ chúng áp dụng các quy tắc chung không nhất quán.

Interface và abstract class giải quyết hai nhu cầu khác nhau:

- **Interface** cho phép client phụ thuộc vào khả năng mà một đối tượng cung cấp, đồng thời một lớp có thể triển khai nhiều interface.
- **Abstract class** phù hợp khi các lớp con cần chia sẻ trạng thái instance, constructor, phương thức protected hoặc một thuật toán có các bước cố định.
- **Default method** hữu ích cho hành vi mặc định không cần trạng thái instance của lớp nền. Nếu các interface cung cấp default method xung đột, cần xử lý theo quy tắc kế thừa Java.
- **Composition** thường hợp lý hơn nếu chỉ cần tái sử dụng một dịch vụ độc lập hoặc nếu việc kế thừa tạo liên kết quá chặt. Java chỉ cho một superclass trực tiếp.

## 4. Những lỗi cần tránh

**Lỗi 1 — Lớp chưa hoàn thiện nhưng quên abstract.** Nếu **AbstractReportJob** bị đổi thành class thông thường trong khi vẫn thiếu **generate()**, chương trình không biên dịch. Cần giữ abstract hoặc cung cấp phần thân phù hợp.

**Lỗi 2 — Nghĩ rằng concrete subclass phải viết lại mọi phương thức.** **CsvReportJob** không cần override **validate()** hoặc **audit()** chỉ để hoàn thành interface, vì các phương thức đó đã được kế thừa hợp lệ.

**Lỗi 3 — Dùng abstract class để né xung đột kiểu.** Nếu hai hợp đồng yêu cầu kiểu trả về không tương thích, việc chuyển lớp thành abstract không tự làm những khai báo xung đột trở nên hợp lệ. Cần phân tích và sửa hợp đồng kiểu.

**Lỗi 4 — Gọi phương thức có thể override từ constructor lớp cha.** Constructor của abstract class chạy trước khi phần khởi tạo riêng của subclass hoàn tất. Nếu constructor gọi hook có thể bị override, implementation của lớp con có thể đọc trạng thái chưa được khởi tạo đầy đủ. Constructor nên thiết lập và kiểm tra trạng thái của lớp mình; hãy gọi hành vi đa hình sau khi đối tượng được tạo xong.

**Lỗi 5 — Dồn logic riêng của subclass vào lớp nền.** Nếu abstract class phải kiểm tra loại lớp con để chọn nhánh xử lý, có thể trách nhiệm chưa được phân chia hợp lý. Cân nhắc một phương thức abstract rõ ràng, một interface nhỏ hơn hoặc composition.

## 5. Tự kiểm tra

**Câu 1.** Interface **Vehicle** khai báo **start()** và **stop()**. Abstract class **BaseVehicle** đã triển khai **start()**. Một lớp concrete **Car** kế thừa **BaseVehicle** cần làm gì?

**Đáp án:** cung cấp **stop()**, trừ khi có triển khai hợp lệ khác được kế thừa.

**Câu 2.** Abstract class đã triển khai mọi phương thức interface có bắt buộc bỏ từ khóa abstract không?

**Đáp án:** không. Nó vẫn có thể được giữ abstract để biểu diễn rằng chỉ lớp con cụ thể mới nên được khởi tạo.

**Câu 3.** Nếu một abstract class không khai báo lại phương thức interface còn thiếu, Java có quên nghĩa vụ đó không?

**Đáp án:** không. Nghĩa vụ vẫn tồn tại trong hệ phân cấp và được kiểm tra khi một lớp concrete được khai báo.

**Ghi nhớ:** abstract class là nơi phù hợp để triển khai phần chung và trì hoãn phần chuyên biệt. Chỉ lớp concrete mới phải giải quyết toàn bộ nghĩa vụ abstract còn hiệu lực; hãy thiết kế rõ phần nào được kế thừa, phần nào là điểm mở rộng.