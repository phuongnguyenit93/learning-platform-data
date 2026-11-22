# Chữ ký phương thức và điều kiện ghi đè trong Java

Ghi đè (*method overriding*) cho phép lớp con cung cấp cách thực hiện riêng cho một phương thức instance được kế thừa hoặc một hợp đồng từ interface. Khi lời gọi được thực hiện qua kiểu cha, Java có thể chọn phần thân của lớp con tại runtime. Để xác định một override hợp lệ, trước hết cần phân biệt **chữ ký phương thức** với toàn bộ khai báo phương thức.

## 1. Chữ ký phương thức gồm những gì?

Theo Java Language Specification, chữ ký chủ yếu được xác định bởi tên phương thức, các tham số kiểu của phương thức generic và kiểu các tham số hình thức theo thứ tự. Với generic, việc chuyên biệt hóa kiểu và quan hệ *subsignature* có thể ảnh hưởng đến việc hai khai báo có tương ứng hay không.

| Thành phần khai báo | Có phân biệt chữ ký? | Ghi chú |
| --- | --- | --- |
| Tên phương thức | Có | read và load khác nhau. |
| Số lượng, thứ tự và kiểu tham số | Có | find(String) khác find(Object). |
| Tên biến tham số | Không | send(String text) và send(String message) cùng chữ ký. |
| Kiểu trả về | Không | Chỉ đổi return type không tạo overload. |
| Modifier như public, final, static | Không | Có thể ảnh hưởng tính hợp lệ của override. |
| Mệnh đề throws | Không | Vẫn phải tuân thủ quy tắc ngoại lệ khi override. |
| String... so với String[] | Không | Varargs dùng kiểu mảng làm kiểu tham số. |

*Method descriptor* của JVM có chứa kiểu trả về, nhưng đó là khái niệm bytecode khác với chữ ký Java source dùng khi xét overload.

## 2. Điều kiện cơ bản của một override

Một khai báo ở lớp con cần thỏa các điều kiện chính sau:

1. Có quan hệ kế thừa hoặc thực hiện interface phù hợp; phương thức phải thực sự được phép kế thừa/ghi đè.
2. Tên và danh sách kiểu tham số phải tạo chữ ký tương ứng theo quy tắc Java.
3. Kiểu trả về phải tương thích. Primitive phải giữ nguyên kiểu; kiểu tham chiếu có thể dùng kiểu con trong trường hợp covariant return.
4. Quyền truy cập không được thu hẹp so với phương thức bị ghi đè.
5. Không được mở rộng checked exception theo cách hợp đồng cha không cho phép.
6. Không thể override phương thức final; static dùng cơ chế hiding, còn private không được kế thừa để override.
7. Lớp con concrete phải triển khai các phương thức abstract còn hiệu lực.

Các bài tiếp theo tập trung riêng vào từng nhóm quy tắc: phân biệt override/overload/hiding, visibility, return type, exception, modifier, annotation, varargs và lời gọi super.

## 3. Ví dụ chạy được: kiểu tham chiếu và đối tượng thực tế

~~~java
public class OverrideBasics {
    public static void main(String[] args) {
        Message parentView = new DetailedMessage();
        System.out.println(parentView.text());
        System.out.println(parentView.describe());
    }
}

class Message {
    public String text() {
        return "base";
    }

    public String describe() {
        return "Message: " + text();
    }
}

class DetailedMessage extends Message {
    @Override
    public String text() {
        return "child";
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac OverrideBasics.java
java OverrideBasics
~~~

Kết quả:

~~~text
child
Message: child
~~~

Biến parentView có kiểu khai báo Message, nên compiler kiểm tra lời gọi theo API nhìn thấy ở kiểu đó. Đối tượng thực là DetailedMessage, vì vậy lời gọi instance text() dispatch đến override. Ngay cả Message.describe() được kế thừa cũng gọi DetailedMessage.text() khi chạy trên đối tượng này.

## 4. Cách tránh một override vô tình thành phương thức mới

Nếu lớp cha có process(String) mà lớp con viết process(Object), đó thường là overload, không phải override. Chương trình vẫn có thể biên dịch nhưng lời gọi qua kiểu cha không chọn phương thức mới chỉ vì đối tượng thực là lớp con.

Hãy dùng @Override trên phương thức có ý định ghi đè. Nếu chữ ký không tương ứng, compiler sẽ báo lỗi thay vì để sai khác đó âm thầm tồn tại.

**Ghi nhớ:** chữ ký xác định phương thức nào đang được so sánh; các quy tắc về kế thừa, kiểu trả về, quyền truy cập, checked exception và modifier quyết định khai báo đó có phải override hợp lệ hay không.