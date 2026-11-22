# So sánh lambda với anonymous class trong cùng bài toán

Lambda expression và anonymous class đều cho phép cung cấp một triển khai tại chỗ cho một kiểu đích trong Java. Khi làm việc với functional interface, cả hai có thể thực hiện cùng một nhiệm vụ và cho ra kết quả giống nhau. Khác biệt nằm ở cú pháp, phạm vi của từ khóa this, khả năng khai báo trạng thái riêng và loại interface mà mỗi cách có thể triển khai.

Bài này so sánh hai cách viết trong cùng bài toán kiểm tra một chuỗi có nội dung hay không, sau đó dùng một ví dụ ngắn để làm rõ sự khác nhau về this. Các ví dụ hoàn chỉnh dùng Java 17; lambda và functional interface có từ Java 8.

## 1. Bài toán chung: kiểm tra chuỗi hợp lệ

Giả sử chương trình cần một quy tắc xác định chuỗi có giá trị sử dụng được hay không. Quy tắc trả về true khi chuỗi khác null và không rỗng hoặc chỉ chứa khoảng trắng. Java có sẵn functional interface Predicate&lt;T&gt; với phương thức trừu tượng test(T), phù hợp cho bài toán này.

Có thể triển khai cùng quy tắc bằng lambda:

~~~java
Predicate<String> validator =
        text -> text != null && !text.isBlank();
~~~

Hoặc bằng anonymous class:

~~~java
Predicate<String> validator = new Predicate<String>() {
    @Override
    public boolean test(String text) {
        return text != null && !text.isBlank();
    }
};
~~~

Cả hai biến đều có kiểu Predicate&lt;String&gt;, nên client gọi validator.test(text) theo cùng một cách. Lambda rút gọn phần cú pháp bao quanh phương thức; anonymous class thể hiện tường minh một lớp vô danh triển khai interface và ghi đè phương thức test.

## 2. Chương trình hoàn chỉnh để so sánh

Lưu mã sau thành tệp LambdaVsAnonymousDemo.java:

~~~java
import java.util.function.Predicate;

public class LambdaVsAnonymousDemo {
    private final String name = "outer";

    public static void main(String[] args) {
        Predicate<String> lambdaValidator =
                text -> text != null && !text.isBlank();

        Predicate<String> anonymousValidator = new Predicate<>() {
            @Override
            public boolean test(String text) {
                return text != null && !text.isBlank();
            }
        };

        String[] samples = {"Java", "", "   "};
        for (String sample : samples) {
            System.out.println("'" + sample + "' -> lambda="
                    + lambdaValidator.test(sample) + ", anonymous="
                    + anonymousValidator.test(sample));
        }

        new LambdaVsAnonymousDemo().compareThis();
    }

    private void compareThis() {
        Runnable lambda =
                () -> System.out.println("lambda this=" + this.name);

        Runnable anonymous = new Runnable() {
            private final String name = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous this=" + this.name);
                System.out.println("outer via qualified this="
                        + LambdaVsAnonymousDemo.this.name);
            }
        };

        lambda.run();
        anonymous.run();
    }
}
~~~

Biên dịch và chạy:

~~~text
javac LambdaVsAnonymousDemo.java
java LambdaVsAnonymousDemo
~~~

Kết quả stdout chính xác:

~~~text
'Java' -> lambda=true, anonymous=true
'' -> lambda=false, anonymous=false
'   ' -> lambda=false, anonymous=false
lambda this=outer
anonymous this=anonymous
outer via qualified this=outer
~~~

Ba dòng đầu cho thấy hai cách triển khai cùng quy tắc và cho kết quả giống nhau với chuỗi có nội dung, chuỗi rỗng và chuỗi chỉ có khoảng trắng. Ba dòng sau minh họa một khác biệt ngữ nghĩa quan trọng: lambda dùng this của đối tượng bao quanh, còn this bên trong anonymous class trỏ đến chính đối tượng vô danh đó.

Trong ví dụ, cú pháp new Predicate<>() dùng toán tử diamond với anonymous class, được hỗ trợ từ Java 9. Nếu cần tương thích với Java 8, hãy viết new Predicate&lt;String&gt;() đầy đủ kiểu tham số.

## 3. Khác biệt về cú pháp và kiểu đích

Lambda có dạng tổng quát gồm danh sách tham số, mũi tên và thân biểu thức hoặc khối lệnh. Khi kiểu tham số có thể suy ra từ kiểu đích, thường không cần khai báo kiểu tường minh.

~~~java
Predicate<String> hasText = text -> !text.isBlank();
Predicate<String> hasTextExplicit =
        (String text) -> !text.isBlank();
~~~

Anonymous class dùng biểu thức new để khai báo một lớp không có tên, đồng thời tạo một instance của lớp đó. Phần thân có thể khai báo các trường, phương thức và khối khởi tạo, nhưng phương thức cần thiết của interface phải được triển khai theo đúng chữ ký.

Cả hai đều cần ngữ cảnh kiểu phù hợp. Lambda chỉ dùng được khi kiểu đích là functional interface: interface có đúng một phương thức trừu tượng theo quy tắc Java, sau khi tính đến các phương thức tương ứng với public của Object và các phương thức default hoặc static. Annotation @FunctionalInterface không bắt buộc, nhưng giúp compiler báo lỗi nếu interface không còn thỏa điều kiện.

Anonymous class có thể triển khai một interface không phải functional interface, vì nó có thể định nghĩa nhiều phương thức trừu tượng. Nó cũng có thể kế thừa một lớp cụ thể và ghi đè các phương thức của lớp đó. Lambda không thể thay thế trực tiếp những trường hợp này.

Ví dụ, interface sau có hai phương thức trừu tượng:

~~~java
interface AuditAction {
    void record(String event);
    void flush();
}
~~~

Anonymous class có thể cung cấp cả hai phương thức:

~~~java
AuditAction action = new AuditAction() {
    @Override
    public void record(String event) {
        System.out.println("record: " + event);
    }

    @Override
    public void flush() {
        System.out.println("flush");
    }
};
~~~

Không thể viết một lambda duy nhất để triển khai AuditAction, bởi không có một phương thức trừu tượng duy nhất làm hợp đồng hàm đích. Nếu API được thiết kế để nhận lambda, hãy tạo một functional interface với một thao tác chính và tách các trách nhiệm khác sang API phù hợp.

## 4. Khác biệt của this và phạm vi tên

Lambda không tạo ra một phạm vi this mới. Khi thân lambda tham chiếu this, nó đang nói đến đối tượng của lớp bao quanh. Điều này giúp lambda đọc trường hoặc gọi phương thức của đối tượng bên ngoài một cách tự nhiên.

Anonymous class có phạm vi đối tượng riêng. Bên trong phương thức của anonymous class, this tham chiếu instance vô danh. Muốn truy cập đối tượng bao quanh, có thể dùng cú pháp OuterClass.this, trong đó OuterClass là tên lớp bao quanh.

Trong chương trình trên:

- Lambda in lambda this=outer vì this.name là trường của LambdaVsAnonymousDemo.
- Anonymous class khai báo trường name riêng có giá trị anonymous; vì vậy this.name trong run() truy cập trường của anonymous class.
- LambdaVsAnonymousDemo.this.name truy cập tường minh trường name của đối tượng bên ngoài.

Đây là khác biệt ngữ nghĩa, không chỉ là khác biệt về số dòng code. Khi chuyển một anonymous class thành lambda hoặc ngược lại, hãy kiểm tra mọi tham chiếu this, super, các trường cùng tên và lời gọi phương thức. Một phép chuyển đổi máy móc có thể làm thay đổi hành vi nếu mã ban đầu dựa vào đối tượng this của anonymous class.

## 5. Trạng thái, trường và phương thức bổ sung

Anonymous class có thể khai báo các trường instance, khối khởi tạo và phương thức bổ sung. Ví dụ ở trên khai báo trường name riêng bên trong anonymous class. Những thành viên này thuộc về instance vô danh và có thể được sử dụng bởi các phương thức của nó.

Lambda không khai báo một lớp mới theo cú pháp nguồn, nên không thể chứa khai báo trường instance hay phương thức thành viên riêng như phần thân của anonymous class. Nếu cần trạng thái có vòng đời riêng, nhiều thao tác liên quan hoặc một API có nhiều phương thức, hãy cân nhắc anonymous class, lớp có tên hoặc một lớp riêng.

Lambda vẫn có thể đọc các biến cục bộ trong phạm vi bao quanh, miễn là chúng là final hoặc effectively final. Quy tắc capture này cũng áp dụng cho anonymous class. Effectively final nghĩa là biến được gán một lần và không bị gán lại sau đó.

~~~java
String prefix = "event: ";
Predicate<String> hasPrefix =
        text -> text != null && text.startsWith(prefix);
~~~

Ví dụ hợp lệ vì prefix không bị gán lại. Nếu chương trình gán prefix một giá trị khác sau khi tạo lambda, mã sẽ không biên dịch. Với cả lambda lẫn anonymous class, khi cần thay đổi trạng thái theo thời gian, thường nên đóng gói trạng thái vào một đối tượng có trách nhiệm rõ ràng thay vì cố sửa biến cục bộ đã capture.

## 6. Khi nào nên dùng từng cách?

Ưu tiên lambda khi biểu diễn một hành động đơn giản thông qua functional interface, chẳng hạn Predicate, Function, Consumer, Supplier, Comparator hoặc một interface hàm do ứng dụng định nghĩa. Lambda giúp tập trung vào logic cần thực hiện và giảm phần cú pháp triển khai.

Anonymous class phù hợp khi cần triển khai nhiều phương thức trừu tượng, thêm trạng thái riêng, ghi đè nhiều hành vi hoặc sử dụng một lớp vô danh làm kiểu con của lớp cụ thể. Nó cũng có thể giúp làm rõ cấu trúc khi triển khai phức tạp hơn một biểu thức ngắn.

| Tiêu chí | Lambda | Anonymous class |
|---|---|---|
| Kiểu đích | Bắt buộc là functional interface | Có thể là interface thường hoặc lớp có thể kế thừa |
| Số phương thức cần triển khai | Một phương thức hàm | Có thể triển khai nhiều phương thức |
| Cú pháp | Thường ngắn gọn, kiểu tham số có thể được suy ra | Tường minh với new và phần thân lớp |
| this | this của phạm vi bao quanh | this của instance vô danh |
| Trường instance và phương thức bổ sung | Không khai báo trực tiếp trong thân lambda | Có thể khai báo trong anonymous class |
| Capture biến cục bộ | Biến phải final hoặc effectively final | Cùng quy tắc |
| Phù hợp nhất | Một hành động hoặc phép biến đổi | Triển khai có nhiều thành viên hoặc trạng thái riêng |

Không nên kết luận rằng lambda luôn nhanh hơn hoặc luôn dùng ít bộ nhớ hơn anonymous class. Cách triển khai ở runtime và tối ưu hóa của JVM phụ thuộc ngữ cảnh; lựa chọn nên dựa trên hợp đồng API, tính đúng đắn, khả năng đọc hiểu và đo đạc thực tế nếu hiệu năng là vấn đề.

## 7. Các lỗi thường gặp khi chuyển đổi

- **Dùng lambda cho interface có nhiều phương thức trừu tượng:** không có một functional method duy nhất để lambda triển khai. Hãy dùng anonymous class hoặc thiết kế lại API.
- **Quên kiểm tra this:** lambda dùng this của lớp bao quanh, trong khi anonymous class có this riêng. Kiểm tra các tham chiếu this và tên trường trùng nhau.
- **Gán lại biến đã capture:** biến cục bộ được dùng trong lambda hoặc anonymous class phải là final hoặc effectively final.
- **Bỏ sót phần thân của phương thức:** khi chuyển anonymous class sang lambda, giữ nguyên logic, điều kiện, thứ tự tác dụng phụ và cách xử lý exception.
- **Cho rằng hai cách luôn tương đương:** chúng có thể thực hiện cùng kết quả trong một bài toán đơn giản, nhưng khác về phạm vi this, thành viên lớp và kiểu đích.
- **Dùng anonymous class khi lambda đủ rõ:** với một thao tác đơn giản, phần cú pháp lớp dài có thể che khuất logic chính.
- **Dùng lambda khi cần một đối tượng có nhiều trách nhiệm:** nếu có nhiều phương thức, trạng thái riêng hoặc hành vi phức tạp, một lớp có tên có thể dễ kiểm thử và bảo trì hơn.

## 8. Quy trình so sánh và kiểm thử

Khi chuyển một đoạn code từ anonymous class sang lambda hoặc ngược lại, hãy làm theo quy trình:

1. Xác định kiểu đích và phương thức mà client thực sự gọi.
2. Viết hai triển khai với cùng điều kiện đầu vào, logic và kết quả kỳ vọng.
3. Chạy cả hai trên các trường hợp bình thường, đầu vào rỗng, null nếu API cho phép, và các trường hợp biên có ý nghĩa.
4. So sánh tác dụng phụ, exception, thứ tự gọi phương thức và việc capture biến.
5. Kiểm tra đặc biệt this, trường cùng tên và phương thức được kế thừa.
6. Biên dịch với phiên bản Java mục tiêu để phát hiện cú pháp hoặc API không được hỗ trợ.

Trong ví dụ kiểm tra chuỗi, cả hai triển khai trả về cùng kết quả cho ba đầu vào đã thử. Ví dụ this cho thấy tại sao việc so sánh chỉ dựa trên kết quả của một bài toán đơn giản là chưa đủ để kết luận hai cấu trúc luôn thay thế được cho nhau.

## 9. Bài tập tự luyện

1. Thay Predicate&lt;String&gt; bằng một functional interface tự định nghĩa có phương thức boolean isValid(String text). Viết cả lambda và anonymous class, sau đó kiểm thử cùng bộ dữ liệu.
2. Tạo một interface có hai phương thức trừu tượng. Triển khai bằng anonymous class và giải thích vì sao không thể dùng một lambda trực tiếp.
3. Thêm một biến cục bộ được capture vào cả hai cách triển khai. Xác minh rằng việc gán lại biến đó sau khi khai báo sẽ gây lỗi biên dịch.
4. Trong anonymous class, khai báo một trường trùng tên với trường của lớp ngoài. So sánh this.field với OuterClass.this.field.
5. Chuyển một anonymous class hiện có sang lambda và liệt kê những khác biệt cần kiểm tra trước khi chấp nhận thay đổi.

Cách chọn đúng bắt đầu từ hợp đồng mà client cần: nếu đó là một thao tác duy nhất của functional interface, lambda thường là lựa chọn gọn và rõ; nếu cần nhiều phương thức, trạng thái riêng hoặc phạm vi đối tượng this độc lập, anonymous class hoặc lớp có tên thể hiện ý định chính xác hơn.