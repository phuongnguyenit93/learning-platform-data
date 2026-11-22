# Vai trò của @Override trong phát hiện sai chữ ký phương thức

@Override thể hiện ý định rằng một phương thức đang override hoặc implement một phương thức hợp lệ từ kiểu cha. Compiler kiểm tra lời khẳng định này. Annotation không làm thay đổi dispatch runtime; giá trị của nó là bắt lỗi khi khai báo không đúng như lập trình viên dự định.

## 1. Lỗi điển hình: vô tình tạo overload

~~~java
class Parent {
    public void send(String text) {
        System.out.println("Parent: " + text);
    }
}

class Child extends Parent {
    public void send(Object text) {
        System.out.println("Child: " + text);
    }
}
~~~

send(Object) không override send(String) vì kiểu tham số khác nhau. Với Parent ref = new Child(); ref.send("hello"); kết quả vẫn là Parent: hello.

Nếu viết:

~~~java
class Child extends Parent {
    @Override
    public void send(Object text) {
        System.out.println("Child: " + text);
    }
}
~~~

compiler báo rằng phương thức không override/implement phương thức từ siêu kiểu. Khi ý định là override send(String), hãy sửa tham số cho khớp và giữ @Override.

## 2. Chữ ký và những thay đổi dễ nhầm

| Thay đổi ở lớp con | Có tạo override? |
| --- | --- |
| Đổi tên phương thức | Không |
| Đổi số lượng hoặc kiểu tham số | Không, thường tạo overload |
| Chỉ đổi tên biến tham số | Có thể; tên biến không thuộc chữ ký |
| Chỉ đổi return type | Không tạo overload; return type phải tương thích khi override |
| Chỉ đổi throws | Không tạo overload; checked exceptions vẫn bị kiểm tra |
| Khai báo cùng chữ ký với static hoặc private method của cha | Không phải override |
| Implement method của interface | Có thể dùng @Override |

Với generic, chữ ký cần được xét theo chuyên biệt hóa kiểu và quy tắc subsignature, không chỉ so hai dòng khai báo nguyên văn. Base&lt;T&gt;.accept(T) có thể được override bởi accept(String) khi subclass kế thừa Base&lt;String&gt;.

## 3. Ví dụ hợp lệ với class và interface

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println("In: " + message);
    }
}

class Animal {
    public Number amount() { return 1; }
    public void greet(String value) { }
}

class Dog extends Animal {
    @Override
    public Integer amount() { return 7; } // Covariant return
    public void greet(Object value) { }   // Overload mới, không dùng @Override
}
~~~

@Override dùng được cả khi triển khai interface lẫn khi override method từ class, kể cả method public của Object như toString(), equals(Object) và hashCode().

## 4. Điều annotation không làm

- Không cho phép override method final, private hoặc static.
- Không bỏ qua quy tắc visibility, return type hay checked exceptions.
- Không chứng minh nội dung phương thức đúng nghiệp vụ hoặc test đã đầy đủ.
- Không điều khiển runtime dispatch.

@Override có retention ở mức SOURCE, phục vụ kiểm tra biên dịch. Khi compiler báo “does not override or implement”, hãy kiểm tra tên, danh sách kiểu tham số, quan hệ extends/implements và modifier của method cha. Đừng xóa annotation để làm lỗi biến mất; trước hết xác minh rằng bạn thực sự muốn override chứ không muốn tạo overload mới.