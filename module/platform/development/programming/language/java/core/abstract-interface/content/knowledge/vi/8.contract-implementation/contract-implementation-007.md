# Triển khai hợp đồng tường minh bằng phương thức có @Override

Trong Java, **@Override** là annotation đặt trên khai báo phương thức để compiler xác nhận rằng phương thức thực sự override một phương thức kế thừa hoặc triển khai một phương thức được khai báo trong interface. Nó thể hiện ý định và giúp phát hiện sai chữ ký ngay khi biên dịch.

Java không có cú pháp riêng để tạo một bản triển khai interface tách biệt theo tên interface như một số ngôn ngữ khác. Ở đây, “tường minh” nghĩa là viết rõ phương thức triển khai và đánh dấu **@Override**.

## 1. Ví dụ hoàn chỉnh

Chương trình sau minh họa cả triển khai interface và override phương thức đã có thân trong lớp cha. Lưu thành **OverrideDemo.java**:

~~~java
public class OverrideDemo {
    interface Formatter {
        String format(String value);
    }

    static class BasicFormatter implements Formatter {
        @Override
        public String format(String value) {
            return value.trim();
        }
    }

    static final class BracketFormatter extends BasicFormatter {
        @Override
        public String format(String value) {
            return "[" + super.format(value) + "]";
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new BracketFormatter();
        System.out.println(formatter.format(" Java "));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OverrideDemo.java
java OverrideDemo
~~~

Kết quả:

~~~text
[Java]
~~~

**BasicFormatter.format()** đáp ứng hợp đồng của interface. **BracketFormatter.format()** override phương thức có thân của lớp cha và dùng **super.format(value)** để tái sử dụng xử lý trim. Dù biến **formatter** có kiểu tĩnh là interface, lúc chạy Java gọi implementation của **BracketFormatter** theo đối tượng thực tế.

## 2. Annotation kiểm tra điều gì?

| @Override giúp compiler kiểm tra | @Override không làm |
| --- | --- |
| Phương thức có quan hệ override/implement hợp lệ với kiểu cha hoặc interface | Không tự sinh phần thân phương thức |
| Phát hiện nhầm tên, sai kiểu tham số hoặc một overload bị tưởng nhầm là override | Không thay đổi mức truy cập thành public |
| Phát hiện ý định override một phương thức không thể override | Không tự gọi phương thức lớp cha |
| Thể hiện rõ ý định với người đọc và công cụ phân tích | Không chứng minh logic đáp ứng đầy đủ ý nghĩa nghiệp vụ |

Về mặt cú pháp, annotation không bắt buộc cho mọi phương thức override hợp lệ. Tuy nhiên, nên dùng nó thường xuyên: nếu chữ ký thay đổi ở interface hoặc superclass, compiler có thể chỉ ra các phương thức không còn override đúng như dự định.

## 3. Phân biệt override và overload

Đoạn sau được cố ý viết sai:

~~~java
interface Printer {
    void print(String value);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(Object value) {
        System.out.println(value);
    }
}
~~~

Hợp đồng yêu cầu **print(String)** nhưng lớp lại khai báo **print(Object)**. Hai phương thức khác kiểu tham số nên không có quan hệ override. **@Override** khiến compiler báo lỗi ngay tại khai báo; nếu xóa annotation, lớp concrete vẫn chưa triển khai **print(String)** nên vẫn không hợp lệ.

Tên biến tham số không ảnh hưởng chữ ký: **print(String text)** có thể triển khai **print(String value)**. Thay đổi kiểu tham số, số lượng tham số hoặc thứ tự kiểu tham số có thể tạo overload khác. Kiểu trả về cũng không thể được dùng riêng để phân biệt hai overload; kiểu trả về của phương thức override phải tuân theo quy tắc tương thích của Java.

## 4. Dùng @Override với các loại phương thức khác nhau

- **Triển khai phương thức abstract của interface:** khai báo phương thức có thân và giữ đúng chữ ký, kiểu trả về cùng mức truy cập public mà hợp đồng yêu cầu.
- **Hoàn thiện phương thức abstract từ superclass:** đánh dấu phương thức cụ thể để compiler xác nhận nó hoàn thành đúng khai báo abstract.
- **Thay đổi hành vi của phương thức concrete trong superclass:** có thể override nếu phương thức không final, private hoặc static theo cách khiến quan hệ override không hợp lệ.
- **Override default method:** có thể dùng annotation khi muốn thay hành vi mặc định của interface. Nếu nhiều default method xung đột, lớp cần giải quyết xung đột theo quy tắc Java.
- **Phương thức chỉ được kế thừa mà không khai báo lại:** không có chỗ để gắn annotation. Không cần viết lại phương thức chỉ để thêm @Override.

Annotation không làm một phương thức static trở thành instance method, không cho phép override phương thức final và không khiến phương thức private của lớp cha trở thành phương thức có thể override. Khi muốn gọi logic lớp cha, phải viết lời gọi **super.method(...)** tường minh.

## 5. Quy trình triển khai an toàn

1. Đọc khai báo interface hoặc superclass để biết chính xác phương thức cần triển khai.
2. Viết đúng tên và kiểu tham số, kiểu trả về tương thích, cùng quyền truy cập cần thiết.
3. Đặt **@Override** trước phương thức và biên dịch. Nếu compiler báo không override được, hãy kiểm tra chữ ký thay vì xóa annotation để che lỗi.
4. Viết phần thân thực hiện hành vi được hợp đồng yêu cầu. Annotation chỉ kiểm tra quan hệ kiểu, không xác minh kết quả nghiệp vụ.
5. Kiểm thử cả lời gọi qua biến kiểu interface/superclass lẫn các trường hợp biên của hành vi cụ thể.

## 6. Tự kiểm tra

**Câu 1.** Interface **Converter** khai báo **String convert(String value)**. Phương thức **public String convert(String input)** có thể triển khai nó không?

**Đáp án:** có; tên tham số không tham gia chữ ký.

**Câu 2.** Phương thức **public Object convert(String value)** có thể override khai báo trên không?

**Đáp án:** không; kiểu trả về Object rộng hơn String nên không đáp ứng quy tắc tương thích kiểu trả về.

**Câu 3.** Nếu bỏ @Override khỏi một phương thức có sai kiểu tham số, compiler có tự coi nó là override không?

**Đáp án:** không. Annotation không tạo quan hệ override; việc thiếu annotation cũng không sửa được phương thức còn thiếu.

**Ghi nhớ:** viết phương thức cụ thể để đáp ứng hợp đồng, rồi dùng @Override để compiler kiểm tra ý định. Annotation phát hiện lỗi quan hệ phương thức sớm, còn tính đúng đắn về hành vi vẫn phải được đánh giá riêng.