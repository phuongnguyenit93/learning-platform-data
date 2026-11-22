# Khai báo lại trong JShell và ảnh hưởng tới đoạn mã phụ thuộc

## 1. Snippet và quan hệ phụ thuộc trong JShell

JShell là môi trường tương tác của JDK, cho phép nhập từng khai báo, biểu thức hoặc câu lệnh và tiếp tục sử dụng chúng trong cùng một phiên. Mỗi đơn vị nhập được quản lý như một **snippet**. Những loại snippet thường gặp gồm:

- Khai báo biến.
- Khai báo phương thức.
- Khai báo lớp, interface, enum hoặc record.
- Khai báo import.
- Biểu thức và câu lệnh thực thi.

Một snippet có thể phụ thuộc vào snippet khác. Ví dụ, phương thức calculate có thể gọi phương thức missing; lớp Order có thể khai báo một trường kiểu Customer. Nếu dependency chưa tồn tại, JShell có thể giữ snippet ở trạng thái có thể khôi phục. Khi dependency được khai báo, JShell đánh giá lại những snippet bị ảnh hưởng và cập nhật trạng thái của chúng.

Cần phân biệt ba tình huống:

1. **Khai báo lại**: nhập một khai báo mới trùng với khai báo đã có để cập nhật snippet.
2. **Thay đổi giá trị**: gán giá trị mới cho biến đã tồn tại. Đây là một thao tác thực thi, không phải lúc nào cũng là thay thế khai báo biến.
3. **Dependency thay đổi**: khai báo mà snippet khác tham chiếu bị thay thế, bị loại bỏ hoặc được bổ sung. JShell có thể đánh giá lại snippet phụ thuộc và thay đổi trạng thái của chúng.

## 2. Khai báo lại biến và giá trị của đoạn mã phụ thuộc

Khi khai báo lại một biến cùng tên, JShell thay thế snippet khai báo biến cũ. Giá trị của một biến khác đã được tính từ trước không tự động được tính lại.

Ví dụ trong một phiên JShell:

~~~text
jshell> int price = 100;
price ==> 100

jshell> int total = price * 2;
total ==> 200

jshell> int price = 150;
price ==> 150

jshell> total
total ==> 200
~~~

Sau khi khai báo lại price, giá trị hiện tại của price là 150. total vẫn là 200 vì phép nhân đã được thực hiện khi khai báo total. JShell không lưu biểu thức price * 2 như một công thức tự động cập nhật theo giá trị của price.

Muốn tính lại total, hãy đánh giá lại biểu thức:

~~~text
jshell> int total = price * 2;
total ==> 300

jshell> total
total ==> 300
~~~

Một phép gán cũng có thể cập nhật giá trị biến mà không khai báo lại kiểu:

~~~text
jshell> price = 175;
price ==> 175
~~~

Dù dùng phép gán hay khai báo lại, các giá trị đã được tính và lưu ở những biến khác vẫn cần được tính lại khi muốn cập nhật kết quả. Không nên nhầm dependency ở mức khai báo với một hệ thống tự động tính toán phản ứng theo dữ liệu.

## 3. Khai báo lại phương thức có cùng chữ ký

Khi nhập lại một phương thức có cùng chữ ký, JShell thay thế định nghĩa phương thức trước đó. Những phương thức gọi nó vẫn có thể sử dụng phần thân mới khi được gọi lần tiếp theo.

Ví dụ:

~~~text
jshell> int fee(int base) {
   ...>     return base + 10;
   ...> }
|  created method fee(int)

jshell> int finalPrice(int base) {
   ...>     return fee(base);
   ...> }
|  created method finalPrice(int)

jshell> finalPrice(100)
$1 ==> 110

jshell> int fee(int base) {
   ...>     return base + 20;
   ...> }
|  modified method fee(int)

jshell> finalPrice(100)
$2 ==> 120
~~~

finalPrice không cần khai báo lại. Phần thân của nó gọi fee(int), và lần gọi mới sẽ sử dụng định nghĩa fee vừa được cập nhật.

Trong Java, **method signature không bao gồm kiểu trả về**. Chữ ký phương thức được xác định bởi tên phương thức, các tham số kiểu và danh sách kiểu tham số. Kiểu trả về và danh sách throws không dùng để phân biệt overload. Vì vậy, không thể tạo hai overload chỉ bằng cách thay đổi kiểu trả về.

Nếu muốn thay đổi phần triển khai nhưng giữ nguyên cách gọi, hãy giữ nguyên tên và kiểu tham số. Khi chữ ký giữ nguyên, các đoạn mã phụ thuộc vẫn có thể gọi phương thức theo hợp đồng cũ và nhận phần triển khai mới.

## 4. Overload khác với khai báo lại

Hai phương thức có cùng tên nhưng khác danh sách kiểu tham số là hai overload. Thêm overload mới không đồng nghĩa với việc thay thế phương thức cũ.

~~~java
int twice(int value) {
    return value * 2;
}

int twice(long value) {
    return (int) value * 3;
}
~~~

Hai phương thức cùng tồn tại:

- twice(3) chọn overload nhận int và trả về 6.
- twice(3L) chọn overload nhận long và trả về 9.

Khi một phương thức phụ thuộc gọi twice(3), trình biên dịch chọn overload phù hợp với kiểu đối số. Thêm overload long không làm lời gọi đang truyền int tự chuyển sang overload long.

Các quy tắc quan trọng:

- Khác danh sách tham số có thể tạo overload.
- Khác kiểu trả về nhưng cùng tên và cùng kiểu tham số không tạo overload hợp lệ.
- Khi cập nhật phần thân của một phương thức, giữ nguyên chữ ký để thay thế đúng khai báo đang có.
- Khi thêm overload, kiểm tra các lời gọi hiện tại để hiểu quy tắc chọn phương thức và tránh lời gọi trở nên mơ hồ.

## 5. Khi dependency bị loại bỏ hoặc chưa được khai báo

Xét một phương thức gọi một phương thức khác chưa tồn tại:

~~~java
int calculate() {
    return missing();
}
~~~

JShell có thể nhận diện đây là một khai báo phương thức nhưng chưa thể sử dụng nó bình thường vì thiếu missing. Snippet có thể ở trạng thái RECOVERABLE_DEFINED.

Khi khai báo dependency:

~~~java
int missing() {
    return 42;
}
~~~

JShell cập nhật trạng thái của calculate thành VALID. Những event được trả về khi đánh giá khai báo missing có thể chứa cả event của phương thức mới và event cho calculate được khôi phục.

Nếu loại bỏ dependency bằng /drop, các snippet phụ thuộc có thể quay lại trạng thái có thể khôi phục. Ví dụ:

1. Khai báo missing.
2. Khai báo calculate gọi missing.
3. Dùng /drop với ID của snippet missing.
4. Kiểm tra trạng thái calculate: dependency không còn nên calculate chuyển sang RECOVERABLE_DEFINED.
5. Khai báo lại missing với chữ ký tương thích.
6. JShell đánh giá lại calculate và đưa nó về VALID.

Với dependency là kiểu dữ liệu, trạng thái có thể khác. Ví dụ:

~~~java
class Order {
    Customer customer;
}
~~~

Nếu Customer chưa tồn tại, khai báo Order có thể ở trạng thái RECOVERABLE_NOT_DEFINED. Khi khai báo class Customer xuất hiện, JShell có thể khôi phục Order về VALID.

Điểm cần nhớ là snippet phụ thuộc được khôi phục theo khai báo mà nó cần. Việc thêm một dependency không tự động làm mọi giá trị đã tính trong phiên thay đổi.

## 6. Các trạng thái của snippet

JShell API biểu diễn trạng thái bằng Snippet.Status. Các trạng thái thường cần nhận biết:

| Trạng thái | Ý nghĩa |
|---|---|
| VALID | Snippet hợp lệ và có thể được sử dụng |
| RECOVERABLE_DEFINED | Khai báo đã được nhận diện nhưng còn tham chiếu chưa giải quyết; có thể khôi phục khi dependency xuất hiện |
| RECOVERABLE_NOT_DEFINED | Snippet chưa tạo được định nghĩa có thể sử dụng vì còn dependency chưa giải quyết |
| REJECTED | Snippet bị từ chối do lỗi không thể khôi phục chỉ bằng cách bổ sung dependency |
| OVERWRITTEN | Snippet cũ đã bị khai báo mới thay thế |
| DROPPED | Snippet đã bị loại bỏ khỏi trạng thái phiên |

Hai trạng thái recoverable không có nghĩa là đoạn mã đã chạy thành công. Chúng cho biết JShell có thể đánh giá lại snippet khi dependency cần thiết được cung cấp.

OVERWRITTEN và DROPPED cũng khác nhau:

- OVERWRITTEN xuất hiện khi một khai báo mới thay thế snippet cũ, chẳng hạn khai báo lại phương thức cùng chữ ký.
- DROPPED xuất hiện khi người dùng chủ động loại bỏ snippet bằng lệnh /drop hoặc API tương ứng.

Có thể dùng /list để xem các snippet hiện tại và /list -all để xem cả những snippet đã bị ghi đè hoặc loại bỏ.

## 7. Theo dõi thay đổi bằng SnippetEvent

JShell API trả về danh sách SnippetEvent từ phương thức eval và drop. Danh sách này có thể chứa snippet vừa được nhập cùng những snippet phụ thuộc có trạng thái thay đổi.

Các thành phần quan trọng:

- **snippet()**: snippet mà event mô tả.
- **previousStatus()**: trạng thái trước khi event xảy ra.
- **status()**: trạng thái sau khi event xảy ra.
- **isSignatureChange()**: cho biết chữ ký của snippet có thay đổi hay không.
- **causeSnippet()**: snippet gây ra thay đổi phụ thuộc, nếu có.
- **value()**: giá trị kết quả của snippet thực thi, nếu có.
- **exception()**: ngoại lệ phát sinh khi đánh giá snippet, nếu có.

Ví dụ, khi khai báo phương thức phụ thuộc vào một phương thức chưa tồn tại, event đầu tiên cho biết phương thức mới đang ở trạng thái RECOVERABLE_DEFINED. Khi dependency xuất hiện, danh sách event có thể chứa một event khác cho snippet phụ thuộc, với chuyển trạng thái RECOVERABLE_DEFINED sang VALID và causeSnippet trỏ tới khai báo dependency.

isSignatureChange() giúp phân biệt thay đổi chữ ký với thay đổi phần triển khai. Ví dụ, khi chỉ sửa phần thân của fee(int) và giữ nguyên chữ ký, JShell thay thế snippet cũ nhưng không xem đó là thay đổi chữ ký. Khi thay đổi chữ ký của một khai báo, các snippet tham chiếu tới khai báo đó cần được kiểm tra lại.

## 8. Ví dụ hoàn chỉnh với JShell API

Chương trình sau tạo một phiên JShell, khai báo phương thức có dependency chưa tồn tại, bổ sung dependency, gọi phương thức rồi loại bỏ dependency. Chương trình in trạng thái của snippet sau từng bước.

Tệp InspectDependencies.java:

~~~java
import jdk.jshell.JShell;

public class InspectDependencies {
    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            var declaration = shell.eval(
                    "int calculate() { return missing(); }"
            );

            System.out.println(
                    "Before dependency: "
                    + shell.status(declaration.get(0).snippet())
            );

            var dependency = shell.eval(
                    "int missing() { return 42; }"
            );

            System.out.println(
                    "After dependency: "
                    + shell.status(declaration.get(0).snippet())
            );

            var result = shell.eval("calculate()");
            System.out.println(
                    "calculate() = " + result.get(0).value()
            );

            shell.drop(dependency.get(0).snippet());

            System.out.println(
                    "After drop: "
                    + shell.status(declaration.get(0).snippet())
            );
        }
    }
}
~~~

Biên dịch và chạy trên JDK có module jdk.jshell:

~~~bash
javac --add-modules jdk.jshell InspectDependencies.java
java --add-modules jdk.jshell -cp . InspectDependencies
~~~

Stdout:

~~~text
Before dependency: RECOVERABLE_DEFINED
After dependency: VALID
calculate() = 42
After drop: RECOVERABLE_DEFINED
~~~

Ví dụ minh họa vòng đời của dependency: khai báo phụ thuộc được giữ ở trạng thái recoverable, chuyển sang VALID khi dependency xuất hiện, thực thi thành công, rồi trở lại trạng thái recoverable khi dependency bị loại bỏ.

Trong ứng dụng modular, cần khai báo module công cụ:

~~~java
module com.acme.jshell.inspector {
    requires jdk.jshell;
}
~~~

Đây là API để tích hợp JShell vào chương trình Java. Nếu chỉ muốn thử nghiệm tương tác, có thể chạy lệnh jshell trực tiếp từ JDK.

## 9. Các lệnh JShell hữu ích khi kiểm tra dependency

| Lệnh | Mục đích |
|---|---|
| /list | Liệt kê các snippet trong phiên |
| /list -all | Liệt kê cả snippet đã bị ghi đè hoặc loại bỏ |
| /vars | Liệt kê các biến |
| /methods | Liệt kê các phương thức |
| /types | Liệt kê các kiểu |
| /drop <snippet-id> | Loại bỏ snippet theo ID |
| /help | Xem trợ giúp |
| /exit | Kết thúc phiên |

Một quy trình kiểm tra thực tế:

1. Dùng /list để tìm snippet ID của khai báo cần sửa hoặc loại bỏ.
2. Xác định snippet nào đang gọi phương thức hoặc tham chiếu kiểu đó.
3. Nếu cập nhật phần thân phương thức, giữ nguyên chữ ký khi muốn các lời gọi hiện tại tiếp tục hoạt động.
4. Nếu thêm overload, kiểm tra kiểu đối số để xác định phương thức được chọn.
5. Nếu loại bỏ dependency, kiểm tra trạng thái các snippet phụ thuộc bằng JShell API hoặc nhập lại dependency tương thích.
6. Đánh giá lại biểu thức đã lưu kết quả khi cần tính toán lại giá trị.
7. Chạy lại các lời gọi quan trọng và xác nhận kết quả mới.

## 10. Lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Khai báo lại biến sẽ tự tính lại mọi biến phụ thuộc | Biến khác đã lưu kết quả cũ; cần đánh giá lại biểu thức nếu muốn cập nhật |
| Sửa phần thân phương thức bắt buộc phải khai báo lại mọi phương thức gọi nó | Khi chữ ký giữ nguyên, lời gọi tiếp theo có thể dùng phần thân mới |
| Thay kiểu trả về tạo ra overload | Kiểu trả về không thuộc method signature và không dùng để phân biệt overload |
| Thêm phương thức cùng tên luôn thay thế phương thức cũ | Khác danh sách tham số tạo overload; phương thức cũ vẫn có thể tồn tại |
| RECOVERABLE_DEFINED có nghĩa snippet đã chạy thành công | Snippet còn tham chiếu chưa giải quyết và chưa thể sử dụng bình thường |
| /drop chỉ xóa một dòng khỏi lịch sử | Lệnh loại bỏ snippet khỏi trạng thái phiên và có thể ảnh hưởng tới snippet phụ thuộc |
| Chỉ cần kiểm tra event của snippet vừa nhập | Danh sách event có thể chứa cả snippet phụ thuộc được đánh giá lại |

Khi khai báo lại trong JShell, hãy xác định đúng snippet cần thay đổi, phân biệt thay thế cùng chữ ký với overload, và theo dõi trạng thái những snippet phụ thuộc. JShell giúp phát hiện và khôi phục dependency ở mức khai báo; các giá trị đã tính trước vẫn cần được đánh giá lại khi muốn có kết quả mới.
