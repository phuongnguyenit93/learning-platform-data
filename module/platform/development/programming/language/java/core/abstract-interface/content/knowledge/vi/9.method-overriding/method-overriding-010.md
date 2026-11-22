# Gọi triển khai lớp cha bằng super khi ghi đè phương thức trong Java

Trong override, lời gọi instance bình thường như this.run() có thể quay lại chính override. **super.run()** yêu cầu Java gọi implementation được tra cứu qua superclass, nhờ đó subclass có thể tái sử dụng logic nền tảng rồi mở rộng nó. super không tạo một đối tượng cha riêng: lời gọi vẫn thực hiện trên cùng đối tượng subclass.

## 1. Ví dụ: superclass gọi một hook có thể override

~~~java
public class SuperDispatchDemo {
    static class Parent {
        void run() {
            System.out.println("Parent.run");
            hook();
        }

        void hook() {
            System.out.println("Parent.hook");
        }
    }

    static class Child extends Parent {
        @Override
        void run() {
            System.out.println("Child.before");
            super.run();
            System.out.println("Child.after");
        }

        @Override
        void hook() {
            System.out.println("Child.hook");
        }
    }

    public static void main(String[] args) {
        new Child().run();
    }
}
~~~

~~~text
Child.before
Parent.run
Child.hook
Child.after
~~~

super.run() gọi phần thân Parent.run(). Nhưng lời gọi hook() bên trong thân đó vẫn là instance call bình thường trên cùng đối tượng Child, nên nó dispatch tới Child.hook(). Vì vậy, super chỉ ràng buộc lời gọi hiện tại; nó không tắt dynamic dispatch của mọi lời gọi phát sinh bên trong superclass.

## 2. Khi nào dùng super?

Dùng super.method(...) khi hợp đồng yêu cầu giữ lại hành vi cha, chẳng hạn thêm logging trước/sau, mở rộng kết quả hoặc thực hiện cleanup. Không phải override nào cũng cần gọi super: nếu lớp con thay thế thuật toán hoàn toàn, gọi superclass có thể tạo tác dụng phụ không mong muốn.

Một số điểm cần nhớ:

- Nếu superclass trực tiếp không override method, super.method() có thể gọi implementation được kế thừa từ tổ tiên.
- Không có cú pháp super.super.method() để bỏ qua tùy ý lớp trung gian.
- Không thể gọi thân abstract method qua super, vì method đó không có implementation.
- super không vượt luật truy cập và không dùng để gọi private helper của cha.
- super(...) gọi constructor superclass; super.method(...) gọi một phương thức. Đây là hai cú pháp khác nhau.

## 3. Interface default method

Khi muốn tái sử dụng một default method từ superinterface, cú pháp là **InterfaceName.super.method()** trong ngữ cảnh được Java cho phép.

~~~java
interface Greeter {
    default String greet(String name) {
        return "Hello, " + name;
    }
}

final class FriendlyGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return Greeter.super.greet(name) + "!";
    }
}
~~~

Greeter.super.greet(name) gọi thân default method của interface rồi thêm dấu chấm than. Khi class nhận hai default method xung đột từ các interface không liên quan và không có implementation concrete phù hợp từ superclass, class phải tự override để giải quyết xung đột. Nếu một interface kế thừa interface kia và override default method, phiên bản ở interface con có thể được chọn mà không cần override trong class. Trong override, `InterfaceName.super.method()` chỉ hợp lệ với superinterface thỏa các quy tắc Java; không thể tùy ý chọn mọi tổ tiên. Phương thức concrete được kế thừa từ superclass được ưu tiên hơn default method của interface.

## 4. Ngoại lệ và tác dụng phụ

Lời gọi super.method() chịu cùng quy tắc xử lý return value và exception như lời gọi method bình thường. Nếu superclass ném checked exception, override cần catch hoặc khai báo phù hợp; nếu gọi superclass tạo thay đổi trạng thái, ghi log hay I/O, subclass phải cân nhắc thứ tự và tránh thực hiện lặp.

Khi superclass bắt buộc một quy trình chung phải chạy đúng trình tự, có thể dùng *Template Method*: một method final điều phối quy trình và gọi các hook được subclass override. Cách này giảm phụ thuộc vào việc từng subclass có nhớ gọi super hay không.

**Ghi nhớ:** super chọn implementation superclass cho lời gọi hiện tại; những hook instance mà implementation đó tiếp tục gọi vẫn có thể dispatch tới subclass. Hãy lần theo toàn bộ đường gọi, exception và tác dụng phụ khi debug một override.