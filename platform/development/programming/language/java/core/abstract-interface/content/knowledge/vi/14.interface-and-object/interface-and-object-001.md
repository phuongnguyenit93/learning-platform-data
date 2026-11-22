# Quan hệ giữa interface và các phương thức public của Object trong Java

Một biến có kiểu interface vẫn có thể gọi các phương thức public instance quen thuộc của java.lang.Object, dù interface không khai báo chúng tường minh. Quy tắc này thuộc về kiểm tra kiểu của Java; nó không có nghĩa interface kế thừa class Object.

## 1. Kiểu khai báo và kiểu runtime giải quyết hai câu hỏi khác nhau

~~~java
interface Named {
    String name();
}

final class Person implements Named {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public String toString() {
        return "Person(" + name + ")";
    }
}
~~~

Với các kiểu trên, đoạn sau hợp lệ:

~~~java
Named person = new Person("Lan");
System.out.println(person.name());
System.out.println(person.toString());
System.out.println(person.equals(person));
System.out.println(person.hashCode());
System.out.println(person.getClass().getSimpleName());
~~~

Java xét hai điều:

1. **Compile time:** kiểu khai báo Named cho phép gọi name() vì interface khai báo phương thức đó. Lời gọi toString(), equals(), hashCode() và getClass() cũng hợp lệ theo quy tắc về phương thức public instance của Object.
2. **Runtime:** đối tượng thật là Person. Nếu Person override một instance method có thể override, lời gọi sẽ chạy implementation của Person. getClass() là final nên trả về lớp runtime thực tế.

Đây là lý do cùng một object có thể được truy cập qua biến Named hoặc Object mà vẫn chạy Person.toString(). Kiểu khai báo quyết định phương thức nào có thể gọi; dynamic dispatch chọn implementation cho instance method có thể override.

Interface không được viết cú pháp extends Object vì extends của interface chỉ nhận interface khác. Với interface không có direct superinterface, Java quy định các chữ ký public instance method thích hợp của Object như thành viên abstract ngầm định, trừ khi đã có khai báo tương thích. Interface con nhận thành viên thông qua quy tắc kế thừa interface.

## 2. Những phương thức Object nào có thể gọi?

| Phương thức | Gọi qua biến interface? | Điều cần nhớ |
| --- | --- | --- |
| toString(), equals(Object), hashCode() | Có | Hành vi có thể do lớp triển khai override; equals và hashCode phải giữ hợp đồng nhất quán |
| getClass() | Có | Là final, trả về lớp runtime; không thể override |
| wait(), wait(long), wait(long, int) | Có về mặt kiểu | Có thể ném InterruptedException; phải tuân thủ quy tắc monitor |
| notify(), notifyAll() | Có về mặt kiểu | Cần sở hữu monitor của object khi gọi |
| clone() | Không tự động | Object.clone() là protected, không phải public method được interface tự động phơi bày |

Một lời gọi hợp lệ khi biên dịch vẫn có thể thất bại lúc chạy. Ví dụ, wait() hoặc notify() ngoài ngữ cảnh sở hữu monitor phù hợp có thể ném IllegalMonitorStateException. Với wait(), code còn phải xử lý InterruptedException. Quy tắc kiểu không thay thế yêu cầu đồng bộ hóa.

Cloneable cũng không khai báo clone(). Nếu interface muốn yêu cầu API sao chép công khai, nó phải tự khai báo phương thức public thích hợp và lớp triển khai phải đáp ứng hợp đồng đó; các bài về clone đi sâu vào trường hợp này.

## 3. Điều quy tắc này không có nghĩa

Một interface không làm mọi API của runtime class trở nên khả dụng. Nếu Person có method internalDetail() mà Named không khai báo, caller không thể gọi person.internalDetail() chỉ vì object runtime là Person. Các public method tương ứng của Object là trường hợp đặc biệt do ngôn ngữ định nghĩa.

Tương tự, getClass() hữu ích để chẩn đoán hoặc dùng reflection, nhưng không nên thay cho một hợp đồng nghiệp vụ. So sánh task.getClass() với một class cụ thể có thể khiến code phụ thuộc implementation, proxy hoặc class runtime do lambda sinh ra. Nếu cần hành vi chung, khai báo method đó trong interface; nếu cần phân nhánh theo subtype, xác định rõ phạm vi và điều kiện.

## 4. Khai báo tường minh và giới hạn của default method

Interface có thể khai báo tường minh chữ ký abstract tương thích:

~~~java
interface Identified {
    String id();
    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

Những khai báo này không tạo thuật toán equals, hashCode hay toString. Lớp triển khai có thể thừa hưởng implementation public phù hợp từ Object hoặc override nó theo ngữ nghĩa riêng.

Interface không được cung cấp default implementation override-equivalent với phương thức non-private của Object. Vì vậy, khai báo default toString(), default equals(Object) hoặc default hashCode() là lỗi biên dịch. Giới hạn này được phân tích ở bài kế tiếp; không nên lặp lại nó bằng cách cho rằng interface có thể “thắng” Object qua cơ chế default method.

## 5. Vì sao các chữ ký Object không làm mất tính functional interface?

Khi xác định phương thức chức năng duy nhất (SAM), Java không tính các public instance method tương ứng với Object thành những nhiệm vụ lambda bổ sung.

~~~java
@FunctionalInterface
interface Task {
    void run();
    boolean equals(Object other);
    String toString();
}

public class Main {
    public static void main(String[] args) {
        Task task = () -> System.out.println("Running");
        task.run();
    }
}
~~~

Chương trình in:

~~~text
Running
~~~

Task vẫn có một phương thức chức năng là run(). Nếu thêm một abstract method độc lập như stop(), interface không còn là functional interface theo quy tắc SAM.

## 6. Cách phân tích một lời gọi

Khi gặp reference.method(...) với reference có kiểu interface:

1. Kiểm tra method có trong interface, superinterface hoặc nhóm chữ ký Object được Java công nhận hay không.
2. Kiểm tra kiểu tham số, kiểu trả về và quyền truy cập; đừng suy ra mọi API của runtime class đều hiện ra.
3. Xác định method có thể override hay final.
4. Với instance method có thể override, theo dõi implementation của đối tượng runtime.
5. Với wait/notify, kiểm tra cả quy tắc monitor và xử lý ngoại lệ; lời gọi hợp lệ khi biên dịch không bảo đảm mọi ngữ cảnh runtime đều hợp lệ.

Tự kiểm tra:
- Vì sao Named không cần extends Object để gọi toString()? Vì Java có quy tắc riêng cho các public instance method thích hợp của Object.
- Có thể gọi protected clone() chỉ nhờ biến có kiểu interface không? Không.
- Nếu lớp runtime override toString(), lời gọi qua biến interface dùng bản nào? Bản override của lớp runtime.
- getClass() có thể override không? Không, vì method này final.

Điểm cốt lõi: interface xác định tập hành vi mà mã gọi được phép dùng; lớp thực tế cung cấp implementation cho các instance method có thể override. Các quy tắc đặc biệt của Object không biến interface thành lớp con của Object.
