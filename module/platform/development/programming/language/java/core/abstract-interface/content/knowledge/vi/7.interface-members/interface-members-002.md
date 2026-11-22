# Phương thức abstract ngầm định public trong Java interface

## 1. Quy tắc ngôn ngữ

Một phương thức được khai báo trong interface mà không có thân và không dùng modifier dành cho phương thức có thân sẽ mặc nhiên là **public abstract**. Hai từ khóa có thể được viết rõ hoặc lược bỏ mà không đổi ý nghĩa.

~~~java
interface Formatter {
    String format(String text);
}
~~~

Khai báo trên tương đương với:

~~~java
interface Formatter {
    public abstract String format(String text);
}
~~~

**public** khiến phương thức trở thành phần công khai của hợp đồng. **abstract** cho biết interface chỉ nêu chữ ký, còn cách xử lý được cung cấp bởi lớp cụ thể hoặc bởi một triển khai phù hợp được kế thừa. Dấu chấm phẩy kết thúc khai báo vì không có thân phương thức.

## 2. Vì sao lớp triển khai phải dùng public?

Một lớp cụ thể thực hiện hợp đồng này phải cung cấp phương thức có chữ ký tương thích và không được giảm quyền truy cập.

~~~java
interface Printer {
    void print(String message);
}

final class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println(message);
    }
}
~~~

Ví dụ sau không hợp lệ:

~~~java
class BrokenPrinter implements Printer {
    @Override
    void print(String message) {
        System.out.println(message);
    }
}
~~~

Trong class, phương thức không ghi modifier truy cập là package-private. Quy tắc ngầm định public chỉ áp dụng cho phương thức abstract trong interface; nó không tự nâng quyền truy cập của phương thức trong class. Dùng protected hoặc private cũng không thể đáp ứng hợp đồng public.

Lớp được khai báo abstract có thể hoãn một số triển khai. Khi tạo lớp cụ thể, mọi phương thức abstract còn thiếu phải được đáp ứng bằng triển khai hợp lệ.

## 3. Quan sát modifier bằng reflection

Lưu mã sau trong tệp **InterfaceAbstractDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Locale;

interface Formatter {
    String format(String text);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}

public class InterfaceAbstractDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Formatter formatter = new UppercaseFormatter();
        System.out.println(formatter.format("java"));

        Method method = Formatter.class.getDeclaredMethod("format", String.class);
        System.out.println(Modifier.toString(method.getModifiers()));
        System.out.println(Modifier.isPublic(method.getModifiers()));
        System.out.println(Modifier.isAbstract(method.getModifiers()));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac InterfaceAbstractDemo.java
java InterfaceAbstractDemo
~~~

Kết quả:

~~~text
JAVA
public abstract
true
true
~~~

Reflection xác nhận modifier thực tế của phương thức được khai báo trong interface. Lời gọi formatter.format("java") vẫn chạy phần triển khai của đối tượng UppercaseFormatter; interface quy định hợp đồng, còn dynamic dispatch chọn phần override theo đối tượng thực.

## 4. So với phương thức abstract trong abstract class

| Khai báo | Quyền truy cập khi bỏ modifier | Nơi có thể cung cấp triển khai |
| --- | --- | --- |
| Phương thức abstract trong interface | public | Class cụ thể hoặc triển khai tương thích được kế thừa |
| Phương thức abstract trong class | package-private | Class con, tuân theo quyền truy cập đã khai báo |

~~~java
interface Task {
    void execute();             // public abstract
}

abstract class BaseTask {
    abstract void execute();    // package-private abstract
}
~~~

Phương thức trong BaseTask có thể được class con cùng package override mà giữ package-private; nếu muốn class con ở package khác có thể triển khai, thiết kế quyền truy cập của class cha cần phù hợp, chẳng hạn protected hoặc public. Interface không cho phép dùng protected cho phương thức của nó.

## 5. Hai trường hợp cần hiểu đúng

**Phương thức tương ứng với Object.** Một class cụ thể có thể đã kế thừa public equals(Object), hashCode() hoặc toString() từ Object. Phương thức kế thừa phù hợp có thể đáp ứng khai báo interface tương ứng; không phải lúc nào class cũng cần viết lại một bản override riêng.

**Functional interface.** Các phương thức default, static và private có thân không làm tăng số hợp đồng abstract cần triển khai. Những phương thức tương ứng với public methods của Object được xử lý theo quy tắc riêng khi xác định functional interface.

~~~java
@FunctionalInterface
interface Validator {
    boolean isValid(String text);

    default boolean isNonEmpty(String text) {
        return text != null && isValid(text);
    }
}
~~~

Lambda có thể cung cấp isValid; phương thức default vẫn có sẵn. Để phân biệt chi tiết các loại phương thức có thân, xem bài phân loại phương thức trong interface.

## 6. Lỗi thường gặp

| Lỗi | Vì sao | Cách sửa |
| --- | --- | --- |
| Khai báo protected hoặc private abstract method trong interface | Phương thức abstract của interface là public | Bỏ modifier không hợp lệ hoặc thiết kế helper private có thân từ Java 9 |
| Bỏ public khi triển khai trong class | Phương thức class trở thành package-private | Ghi public rõ ràng |
| Cho rằng mọi phương thức interface đều abstract | default, static và private có thân là các dạng khác | Xem cả modifier và việc có thân hay không |
| Cho rằng tên tham số khác làm thay đổi hợp đồng | Tên tham số không quyết định việc override | So sánh tên phương thức, tham số, kiểu trả về và quy tắc ngoại lệ |

### Tự kiểm tra

1. Khai báo **void run();** trong interface có modifier nào? **public abstract**.
2. Lớp cụ thể implements interface có thể viết **void run() {}** không? **Không**, vì đó là package-private.
3. Lớp abstract có thể hoãn triển khai không? **Có**, miễn lớp vẫn được khai báo abstract và lớp cụ thể sau cùng hoàn thiện hợp đồng.
4. **default void log() {}** có phải phương thức abstract không? **Không**, nó có thân và là phương thức instance công khai.

Điểm cần nhớ: modifier public vẫn có hiệu lực dù không xuất hiện trong mã nguồn. Khi triển khai interface, hãy đáp ứng đúng hợp đồng công khai và dùng @Override để trình biên dịch phát hiện chữ ký sai.