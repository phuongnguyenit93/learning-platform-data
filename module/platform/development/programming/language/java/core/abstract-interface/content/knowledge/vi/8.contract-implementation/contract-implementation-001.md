# Triển khai đầy đủ các phương thức abstract còn thiếu trong Java

Một lớp Java **cụ thể** phải có cách triển khai hợp lệ cho mọi phương thức instance abstract còn hiệu lực từ các lớp cha và interface mà nó kế thừa. Phần triển khai có thể được khai báo ngay trong lớp hoặc được kế thừa từ một lớp cha phù hợp. Nếu lớp còn nghĩa vụ abstract chưa giải quyết, nó phải tiếp tục là lớp abstract; nếu không, trình biên dịch từ chối khai báo lớp.

Bài này tập trung vào cách xác định nghĩa vụ còn thiếu và chọn đúng nơi hoàn thành nó. Các quy tắc chuyên biệt về quyền truy cập, phương thức kế thừa, nhiều interface và kiểu trả về được phân tích sâu ở những bài tiếp theo trong cùng chương.

## 1. Phân biệt phương thức abstract và phương thức có thân

Một phương thức abstract chỉ công bố chữ ký, không cung cấp phần thân thực thi. Phương thức cụ thể có phần thân và có thể được gọi khi một đối tượng thực thi nó.

Ví dụ sau là chương trình Java 17 hoàn chỉnh, lưu vào **Main.java**:

~~~java
public class Main {
    abstract static class Shape {
        abstract double area();
    }

    static final class Circle extends Shape {
        private final double radius;

        Circle(double radius) {
            this.radius = radius;
        }

        @Override
        double area() {
            return Math.PI * radius * radius;
        }
    }

    public static void main(String[] args) {
        System.out.printf("%.2f%n", new Circle(2).area());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
12.57
~~~

**Circle** là lớp cụ thể vì đã triển khai phương thức **area()** mà nó kế thừa. Nếu bỏ phương thức này nhưng vẫn giữ **Circle** là lớp cụ thể, mã sẽ không biên dịch. Nếu **Circle** vẫn chưa biết cách tính diện tích vì nó chỉ là bước trung gian trong hệ phân cấp, có thể khai báo **abstract class Circle** để lớp con hoàn thiện sau.

## 2. Nghĩa vụ triển khai đến từ đâu?

Khi kiểm tra một lớp cụ thể, hãy xét toàn bộ hệ phân cấp chứ không chỉ nhìn các phương thức được viết ngay trong lớp:

- Các phương thức abstract được khai báo trong superclass và vẫn chưa có triển khai cụ thể.
- Các phương thức abstract mà interface trực tiếp hoặc gián tiếp yêu cầu.
- Những nghĩa vụ được để lại qua một hoặc nhiều lớp abstract trung gian.
- Những phương thức có cùng tên nhưng thực ra khác chữ ký; chúng không tự động hoàn thành nghĩa vụ của nhau.

Một abstract class có thể triển khai một phần, toàn bộ hoặc chưa triển khai phương thức abstract nào. Từ khóa **abstract** cho phép lớp trì hoãn nghĩa vụ; nó không làm nghĩa vụ đó biến mất. Trước khi một lớp có thể được tạo bằng **new**, mọi phương thức abstract còn thiếu phải được giải quyết.

Không phải mọi phương thức interface đều tạo nghĩa vụ triển khai mới. Một phương thức **default** đã có thân và thường được kế thừa; phương thức **static** hoặc **private** của interface không thay thế một phương thức instance abstract. Trường dữ liệu, constructor và một phương thức overload khác tham số cũng không thể thay thế chữ ký abstract đang còn thiếu.

## 3. Lỗi biên dịch và cách sửa

Đoạn dưới đây được cố ý viết sai: **HtmlContent** là lớp cụ thể nhưng chưa triển khai **render()**.

~~~java
abstract class Content {
    abstract String render();
}

class HtmlContent extends Content {
    // Chưa có render(), nên lớp cụ thể này không hợp lệ.
}
~~~

Có hai hướng sửa tùy ý định thiết kế.

**Hướng A — lớp đã đủ chức năng để tạo đối tượng:** triển khai phương thức còn thiếu.

~~~java
class HtmlContent extends Content {
    @Override
    String render() {
        return "<p>Hello</p>";
    }
}
~~~

**Hướng B — lớp chỉ là tầng trung gian:** khai báo lớp đó là abstract và để lớp cụ thể phía sau hoàn thiện phương thức.

~~~java
abstract class HtmlContent extends Content {
    // Có thể bổ sung trạng thái và hành vi chung ở đây.
}

final class WelcomePage extends HtmlContent {
    @Override
    String render() {
        return "<p>Welcome</p>";
    }
}
~~~

Đây là các phương án thay thế nhau; không đặt hai khai báo cùng tên vào cùng package để biên dịch.

## 4. Quy trình tìm phương thức còn thiếu

Khi gặp lỗi có ý nghĩa “class is not abstract and does not override an abstract method”, hãy kiểm tra theo thứ tự:

1. Xác định lớp được nêu trong lỗi và xác nhận lớp đó có chủ ý là concrete hay không.
2. Đọc các khai báo **extends** và **implements**, rồi liệt kê các phương thức abstract mà lớp nhận được từ hệ phân cấp.
3. Với từng phương thức, tìm một triển khai cụ thể đã có hoặc cần viết. Không bắt buộc sao chép lại phương thức đã được kế thừa hợp lệ.
4. So sánh chính xác tên, kiểu tham số, kiểu trả về, khả năng truy cập và ngoại lệ checked. Nếu cần triển khai phương thức interface thông thường, phương thức đó phải là public.
5. Dùng **@Override** trên phương thức mới để compiler phát hiện việc viết nhầm chữ ký. Nếu lớp vẫn còn nghĩa vụ chưa giải quyết, hãy triển khai thêm hoặc giữ lớp ở trạng thái abstract.
6. Sau khi mã biên dịch được, kiểm tra phần thân có thực hiện đúng ý nghĩa của hợp đồng hay không. Hết lỗi compiler mới chứng minh tính hợp lệ về kiểu.

## 5. Những nhầm lẫn cần tránh

- **Có phương thức cùng tên chưa chắc đã override.** Thêm hoặc đổi kiểu tham số có thể tạo overload và để lại phương thức abstract ban đầu.
- **Không phải lớp cụ thể nào cũng phải tự viết mọi phương thức.** Triển khai concrete được kế thừa có thể đã đáp ứng hợp đồng.
- **Khai báo abstract không phải lỗi thiết kế tự thân.** Đây là cách hợp lệ để chia trách nhiệm qua nhiều tầng kế thừa.
- **Không dùng thân giả để che nghĩa vụ.** Một phương thức chỉ ném UnsupportedOperationException có thể làm lớp biên dịch được nhưng vẫn không đáp ứng hành vi mà người gọi mong đợi.
- **Không nhầm phương thức default với abstract.** Default method có thân, nhưng xung đột giữa các default method vẫn có thể cần giải quyết tường minh.

## 6. Tự kiểm tra

**Câu 1.** Interface **Printer** khai báo **print()** và **close()**. Abstract class **BasePrinter** đã triển khai **close()**. Lớp concrete **ConsolePrinter** kế thừa **BasePrinter** phải làm gì?

**Đáp án:** triển khai **print()**, trừ khi có một implementation hợp lệ khác được kế thừa. Không cần viết lại **close()**.

**Câu 2.** Một abstract class đã triển khai mọi phương thức abstract có được tiếp tục khai báo abstract không?

**Đáp án:** có. Từ khóa abstract vẫn có thể thể hiện rằng lớp chỉ dùng làm lớp nền và không được khởi tạo trực tiếp.

**Câu 3.** Vì sao thêm một phương thức cùng tên nhưng nhận tham số khác không giải quyết lỗi thiếu phương thức abstract?

**Đáp án:** vì đó là overload; chữ ký cần được triển khai vẫn còn thiếu.

**Ghi nhớ:** một lớp concrete phải hoàn tất mọi nghĩa vụ phương thức abstract còn hiệu lực. Xác định đúng chữ ký và toàn bộ chuỗi kế thừa trước khi thêm phương thức, rồi kiểm tra riêng tính đúng đắn của hành vi.