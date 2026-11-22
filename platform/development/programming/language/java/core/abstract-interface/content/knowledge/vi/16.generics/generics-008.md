# Type erasure, bridge method và quan hệ ghi đè trong Java

## 1. Ba khái niệm liên quan

Generics giúp compiler kiểm tra kiểu ở mã nguồn. Java triển khai generic chủ yếu bằng **type erasure**: type parameter được xóa hoặc thay bằng kiểu xóa của bound khi tạo bytecode. Kế thừa generic có thể khiến chữ ký ở mã nguồn và descriptor JVM khác nhau; compiler sinh **bridge method** khi cần để lời gọi đa hình vẫn đến đúng implementation.

- **Type erasure** quy định kiểu của type variable và generic type sau khi biên dịch.
- **Overriding** được xác định theo quy tắc ngôn ngữ Java và quan hệ kế thừa generic.
- **Bridge method** là phương thức tổng hợp do compiler sinh để giữ tương thích giữa chữ ký đã xóa và implementation cụ thể.

Bridge method thường không có trong mã nguồn do lập trình viên viết. Không tự khai báo bridge để sửa một chữ ký generic sai.

## 2. Type erasure hoạt động thế nào?

| Khai báo nguồn | Kiểu xóa minh họa |
| --- | --- |
| List&lt;String&gt; | List |
| Map&lt;String, Integer&gt; | Map |
| T với &lt;T&gt; không bound | Object |
| T với &lt;T extends Number&gt; | Number |
| T với &lt;T extends Number & Comparable&lt;T&gt;&gt; | Number, là bound đầu tiên |

Ví dụ:

~~~java
class Box<T> {
    private T value;

    public void set(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
~~~

Với T không có bound, chữ ký đã xóa tương đương về mặt khái niệm với set(Object) và get() trả Object. Khi mã nguồn dùng Box&lt;String&gt;, compiler vẫn kiểm tra kiểu và chèn cast cần thiết ở nơi đọc. Điều này không có nghĩa compiler tạo một class runtime riêng cho Box&lt;String&gt;.

Class file có thể giữ metadata generic signature để Reflection và công cụ đọc khai báo tổng quát. Metadata đó không biến Box&lt;String&gt; và Box&lt;Integer&gt; thành hai lớp runtime khác nhau.

## 3. Vì sao override generic cần bridge method?

~~~java
class Node<T> {
    public void setData(T data) {
        // Lưu dữ liệu.
    }

    public T getData() {
        return null;
    }
}

final class IntegerNode extends Node<Integer> {
    @Override
    public void setData(Integer data) {
        System.out.println("integer=" + data);
    }

    @Override
    public Integer getData() {
        return 42;
    }
}
~~~

Ở mã nguồn, IntegerNode cố định T thành Integer và cung cấp setData(Integer), getData() trả Integer. Các override này hợp lệ sau khi áp dụng type argument của Node&lt;Integer&gt;.

Sau erasure, phương thức của Node có chữ ký dùng Object, trong khi implementation của IntegerNode nhận hoặc trả Integer. Compiler cần tạo bridge tương đương với các điểm vào setData(Object) và getData() trả Object. Bridge chuyển tiếp đến implementation cụ thể, đồng thời có thể cast đối số từ Object sang Integer.

Nếu lời gọi dùng kiểu generic hợp lệ, compiler bảo đảm đối số phù hợp. Nếu raw type được dùng để truyền giá trị sai kiểu, cast bên trong bridge có thể ném ClassCastException.

## 4. Ví dụ chạy được và quan sát bằng Reflection

Lưu toàn bộ mã vào **TypeErasureBridgeDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

class Node<T> {
    private T data;

    public void setData(T data) {
        this.data = data;
    }

    public T getData() {
        return data;
    }
}

final class IntegerNode extends Node<Integer> {
    @Override
    public void setData(Integer data) {
        System.out.println("set Integer: " + data);
        super.setData(data);
    }

    @Override
    public Integer getData() {
        return super.getData();
    }
}

public class TypeErasureBridgeDemo {
    public static void main(String[] args) {
        Node<Integer> node = new IntegerNode();
        node.setData(42);
        System.out.println("value=" + node.getData());

        Arrays.stream(IntegerNode.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .sorted(Comparator.comparing(Method::getName))
                .forEach(method -> {
                    String parameters = Arrays.stream(method.getParameterTypes())
                            .map(Class::getSimpleName)
                            .collect(Collectors.joining(", "));
                    System.out.println("bridge=" + method.getName()
                            + "(" + parameters + ") -> "
                            + method.getReturnType().getSimpleName());
                });
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac TypeErasureBridgeDemo.java
java TypeErasureBridgeDemo
~~~

Kết quả stdout:

~~~text
set Integer: 42
value=42
bridge=getData() -> Object
bridge=setData(Object) -> void
~~~

Biến node được khai báo là Node&lt;Integer&gt; nhưng trỏ đến IntegerNode. Lời gọi setData(42) đi qua đường dispatch đã xóa rồi tới implementation nhận Integer. Reflection lọc isBridge() và sắp xếp theo tên để kết quả ổn định; không nên dựa vào thứ tự mà getDeclaredMethods() trả về.

## 5. Bridge và kiểu trả về hiệp biến

Bridge cũng có thể xuất hiện khi kiểu trả về của override là subtype cụ thể hơn:

~~~java
class Animal {
    public Object create() {
        return new Object();
    }
}

final class Cat extends Animal {
    @Override
    public String create() {
        return "cat";
    }
}
~~~

Java cho phép Cat.create() override Animal.create() vì String là subtype của Object. Kiểu trả về nằm trong descriptor JVM, nên compiler có thể sinh bridge trả Object để lời gọi qua Animal vẫn đến implementation của Cat. Đây không phải overload: Java không cho khai báo hai phương thức trong cùng class chỉ khác kiểu trả về.

Bridge thường mang các cờ bytecode ACC_BRIDGE và ACC_SYNTHETIC. Reflection có thể kiểm tra isBridge() và isSynthetic(); không phải mọi synthetic method đều là bridge, và không phải mọi generic override đều cần bridge.

## 6. Những hệ quả cần nhớ

- Không thể overload hai phương thức chỉ khác type argument nếu sau erasure chữ ký trùng nhau. Bài về name clash phân tích các trường hợp và cách thiết kế lại.
- Không thể kiểm tra List&lt;String&gt; bằng instanceof như thể runtime biết type argument cụ thể; dùng List&lt;?&gt; nếu chỉ cần xác nhận đó là một List.
- Không thể tạo trực tiếp new T() hoặc new T[n] cho type variable chưa biết cụ thể.
- Static member không dùng trực tiếp type parameter của instance class; static generic method có thể khai báo tham số kiểu riêng.
- Raw type và unchecked cast có thể bỏ qua một phần kiểm tra compile time; chúng không làm object runtime tự kiểm tra type argument.

## 7. Cách điều tra khi thấy method lạ

1. Xác nhận quan hệ extends/implements và chữ ký override ở mã nguồn.
2. Tính erasure của type variable: T không bound thành Object; T extends X thường xóa thành X.
3. Dùng @Override để compiler xác minh quan hệ override dự kiến.
4. Nếu Reflection liệt kê method bất ngờ, kiểm tra isBridge() và isSynthetic().
5. Có thể dùng javap -p -c -v IntegerNode để xem descriptor, cờ ACC_BRIDGE/ACC_SYNTHETIC và lệnh chuyển tiếp.

Type erasure là cơ chế triển khai; bridge method là chi tiết compiler tạo ra để giữ đa hình. Hãy thiết kế và kiểm tra hợp đồng ở mức Java source, không phụ thuộc vào việc tự viết bridge.