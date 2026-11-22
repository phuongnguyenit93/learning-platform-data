# Kết hợp ghi đè generic và phương thức bridge

## Vì sao bytecode có thể có thêm một phương thức?

Một lớp có thể chỉ viết một phương thức trong mã nguồn nhưng reflection nhìn thấy hai phương thức cùng tên. Khi có generic hoặc kiểu trả về đồng biến, phương thức bổ sung có thể là **bridge**: mã cầu nối do trình biên dịch sinh để giữ hành vi đa hình phù hợp với các kiểu đã bị xóa và các mô tả phương thức ở mức JVM.

Bridge không phải logic nghiệp vụ thứ hai do tác giả tự thêm. Nó điều chỉnh lời gọi ở mức biểu diễn runtime rồi chuyển tiếp tới phương thức thực hiện.

Bài dùng `javac` với Java 17+ để đối chiếu mã nguồn, lời gọi thông thường, reflection và bytecode. Không cần viết raw type hay tắt cảnh báo để quan sát cơ chế.

## Ba góc nhìn của một hợp đồng generic

Xét khai báo `Mapper<I, O>` với phương thức `O map(I input)`, và lớp thực hiện `Mapper<String, Integer>`.

| Góc nhìn | Hình dạng phương thức trong ví dụ |
| --- | --- |
| Khai báo generic của interface | `O map(I)` |
| Hợp đồng đã thay đối số kiểu tại mức nguồn | `Integer map(String)` |
| Descriptor của phương thức interface sau xóa kiểu | Tham số `Object`, kết quả `Object` |

`I` và `O` không có cận tường minh nên bị xóa thành `Object`. Quy tắc này không làm trình biên dịch bỏ kiểm tra kiểu ở nguồn: một biến `Mapper<String, Integer>` vẫn yêu cầu đối số chuỗi khi gọi `map`. Xem [xóa kiểu trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6).

## Ví dụ hoàn chỉnh: ghi đè generic và bridge

Lưu tệp `GenericBridgeDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public final class GenericBridgeDemo {
    private GenericBridgeDemo() {
    }

    interface Mapper<I, O> {
        O map(I input);
    }

    static final class StringLength implements Mapper<String, Integer> {
        private int calls;

        @Override
        public Integer map(String input) {
            calls++;
            return input.length();
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        StringLength implementation = new StringLength();
        Mapper<String, Integer> typed = implementation;
        System.out.println("direct: " + implementation.map("abc"));
        System.out.println("throughInterface: " + typed.map("java"));

        Method[] methods = StringLength.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::isBridge));
        for (Method method : methods) {
            System.out.println(method.getReturnType().getSimpleName() + " "
                    + method.getName() + "("
                    + method.getParameterTypes()[0].getSimpleName() + ")"
                    + " bridge=" + method.isBridge()
                    + " synthetic=" + method.isSynthetic());
        }

        Method bridge = StringLength.class.getDeclaredMethod("map", Object.class);
        System.out.println("reflectiveBridge: " + bridge.invoke(implementation, "hello"));
        try {
            bridge.invoke(implementation, Integer.valueOf(7));
        } catch (InvocationTargetException ex) {
            System.out.println("wrongInputCause: "
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("bodyCalls: " + implementation.calls);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror GenericBridgeDemo.java
java GenericBridgeDemo
```

Stdout chính xác khi biên dịch ví dụ bằng `javac`:

```text
direct: 3
throughInterface: 4
Integer map(String) bridge=false synthetic=false
Object map(Object) bridge=true synthetic=true
reflectiveBridge: 5
wrongInputCause: ClassCastException
bodyCalls: 3
```

Chương trình chỉ có hai phương thức `map` được khai báo trong lớp thực hiện sau biên dịch. Nó sắp xếp theo `isBridge()` để in phương thức thường trước bridge, không dựa vào thứ tự tự nhiên của `getDeclaredMethods()`.

## `map(String)` thực sự ghi đè, không phải một overload ngẫu nhiên

`StringLength` thực hiện `Mapper<String, Integer>`. Sau khi thay đối số kiểu vào hợp đồng ở mức nguồn, phương thức cần thực hiện là `Integer map(String)`, nên `@Override` được trình biên dịch chấp nhận.

Không chỉ nhìn `map(Object)` sau xóa kiểu rồi kết luận `map(String)` là một overload không liên quan. Việc kiểm tra ghi đè có xét quan hệ generic của các khai báo. Xem [yêu cầu ghi đè trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3).

Ngược lại, nếu một interface không generic khai báo `Object map(Object)`, việc lớp con chỉ viết `Integer map(String)` không tự ghi đè hợp đồng đó. Nó đã thay tham số và không còn giữ cùng quan hệ hợp đồng như ví dụ generic.

## Bridge chuyển tiếp lời gọi như thế nào?

Trong trường hợp đang khảo sát, `javac` sinh phương thức có hình dạng runtime `Object map(Object)`. Phần thân tương đương về ý nghĩa với đoạn minh họa sau:

```java
// Minh họa logic do trình biên dịch sinh; không thêm vào lớp nguồn.
public Object map(Object input) {
    return map((String) input);
}
```

Bridge ép đối số sang `String` rồi gọi `Integer map(String)`. Kết quả `Integer` có thể được trả ra dưới dạng `Object` để phù hợp descriptor bị xóa.

Đoạn minh họa không phải lời khuyên tự viết bridge trong lớp `StringLength`. Trình biên dịch chịu trách nhiệm tạo các phương thức hỗ trợ cần thiết; tự thêm khai báo như vậy có thể gây xung đột chữ ký sau xóa kiểu.

Lời gọi thông thường qua `Mapper<String, Integer>` được biên dịch dựa trên hợp đồng generic nhưng liên kết tới phương thức interface có descriptor bị xóa. Bridge giúp chuyển tới đúng phần thực hiện cụ thể, bảo toàn hành vi đa hình.

Ở đầu ra, hai lời gọi đầu tiên và lần gọi bridge bằng reflection với `"hello"` đều đến phần thân `map(String)`, nên bộ đếm cuối cùng là `3`.

## Kiểm tra bằng `javap`

Sau khi biên dịch ví dụ, chạy:

```shell
javap -c -p -s 'GenericBridgeDemo$StringLength'
```

Dùng dấu nháy đơn như trên trong PowerShell hoặc shell hỗ trợ kiểu nháy đó để giữ nguyên `$` trong tên lớp lồng. Với Windows Command Prompt, dùng dấu nháy kép.

Kết quả chứa hai descriptor:

```text
map(String)  -> Integer
(Ljava/lang/String;)Ljava/lang/Integer;

map(Object)  -> Object
(Ljava/lang/Object;)Ljava/lang/Object;
```

Khối trên tóm lược tên và descriptor để dễ đối chiếu, không phải toàn bộ nguyên văn đầu ra `javap`. Trong phần code của bridge, cần thấy `checkcast` tới `java/lang/String`, rồi lệnh gọi phương thức `map` nhận `String` và trả `Integer`.

Descriptor phương thức của JVM chứa cả kiểu tham số và kiểu trả về. Điều đó khác với quy tắc chữ ký phương thức ở mức nguồn Java, nơi chỉ đổi kiểu trả về không đủ tạo overload hợp lệ. Xem [descriptor phương thức trong JVMS](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3.3).

Nếu muốn thấy các cờ bytecode của bridge, dùng thêm `-v` và tìm `ACC_BRIDGE` cùng `ACC_SYNTHETIC` trên phương thức tương ứng. Số thứ tự constant pool và bố cục chi tiết có thể thay đổi; không dùng chúng làm kết quả cố định của bài.

## Vì sao đối số sai gây lỗi trước phần thân nghiệp vụ?

Qua biến có kiểu `Mapper<String, Integer>`, lời gọi `typed.map(Integer.valueOf(7))` không hợp lệ và bị trình biên dịch từ chối.

Ví dụ cố ý dùng reflection để gọi phương thức bridge có tham số runtime là `Object`. Khi truyền `Integer`, phép kiểm tra tham số của lời gọi reflection chấp nhận nó ở vị trí `Object`, nhưng `checkcast String` bên trong bridge thất bại.

Do ngoại lệ xảy ra trong phương thức được gọi, reflection bọc nguyên nhân trong `InvocationTargetException`. Chương trình lấy `getCause()` và in `ClassCastException`. Xem [`InvocationTargetException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InvocationTargetException.html).

Bộ đếm `calls` không tăng cho lần gọi sai vì bridge chưa tới được phần thân `map(String)`. Đây là khác biệt với một lỗi do logic bên trong phần thân sau khi đã nhận được đối số hợp lệ.

Không dùng bridge như một API nới lỏng hợp đồng nhận mọi đối tượng. Chữ ký `Object` của nó là cơ chế thích ứng ở mức runtime, không phải ý định nghiệp vụ nhận một số nguyên thay cho chuỗi.

## Kiểu trả về đồng biến cũng có thể cần bridge

Bridge không chỉ xuất hiện khi phương thức có tham số generic. Một ví dụ không dùng generic cũng có thể sinh bridge do kiểu trả về đồng biến.

Lưu chương trình riêng trong `CovariantBridgeDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public final class CovariantBridgeDemo {
    private CovariantBridgeDemo() {
    }

    static class Parent {
        public Number value() {
            return Integer.valueOf(0);
        }
    }

    static final class Child extends Parent {
        @Override
        public Integer value() {
            return Integer.valueOf(7);
        }
    }

    public static void main(String[] args) {
        Parent reference = new Child();
        System.out.println("throughParent: " + reference.value());
        Method[] methods = Child.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::isBridge));
        for (Method method : methods) {
            System.out.println(method.getReturnType().getSimpleName()
                    + " value() bridge=" + method.isBridge());
        }
    }
}
```

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror CovariantBridgeDemo.java
java CovariantBridgeDemo
```

Stdout chính xác khi biên dịch bằng `javac`:

```text
throughParent: 7
Integer value() bridge=false
Number value() bridge=true
```

`Child.value()` do tác giả viết trả `Integer`, hẹp hơn `Number` của cha. Phương thức bridge trả `Number` chuyển tiếp tới bản trả `Integer`, để lời gọi qua hợp đồng cha tiếp tục đến đúng hành vi.

Trong trường hợp này không cần ép một tham số từ `Object` sang `String` vì không có tham số. Không nên học thuộc rằng mọi bridge đều phải có cùng một mẫu `checkcast` ở đầu vào; nó phụ thuộc chữ ký cần thích ứng.

Cũng không kết luận rằng hai phương thức khác kiểu trả về trong bytecode là hai overload do lập trình viên được phép tự khai báo trong cùng lớp nguồn.

## Xử lý khi viết công cụ reflection

`getDeclaredMethods()` có thể trả về phương thức bridge và synthetic. Muốn kiểm tra một phương thức có phải bridge, dùng `Method.isBridge()`; `isSynthetic()` trả lời câu hỏi rộng hơn về thành phần tổng hợp. Xem [`Method.isBridge()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#isBridge()) và [các phương thức được liệt kê bởi `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getDeclaredMethods()).

Nếu đang dựng menu hành vi từ các phương thức do tác giả khai báo, có thể cần bỏ qua bridge để tránh đăng ký cùng hành vi hai lần. Nếu đang phân tích descriptor hoặc hành vi liên kết ở JVM, bridge lại là bằng chứng cần giữ.

Không mặc định rằng mọi synthetic method đều là bridge. Một công cụ cần nhận diện theo đúng cờ và mục tiêu phân tích, không chỉ dựa vào tên hoặc thấy có hai phương thức giống nhau.

Cũng không chỉ lọc theo tên phương thức: overload thật và bridge đều có thể cùng tên nhưng cần được diễn giải khác nhau. Tối thiểu phải xét tham số, kết quả, lớp khai báo và cờ bridge theo nhu cầu.

Nếu cần nối bridge tới phương thức do tác giả viết trong một framework, phải xác định quy tắc với generic, kế thừa và nhiều phương thức liên quan; ví dụ đơn giản không phải thuật toán tổng quát để chọn bất kỳ phương thức cùng tên nào.

## Những nhầm lẫn cần tránh

- **Cho rằng xóa kiểu làm mất đa hình:** bridge là một phần cơ chế giúp lời gọi vẫn đi tới bản thực hiện phù hợp.
- **Cho rằng `map(String)` chỉ là overload của hợp đồng generic:** phải xét hợp đồng sau thay đối số kiểu ở mức nguồn.
- **Tự viết thêm `map(Object)` để hỗ trợ trình biên dịch:** có thể làm khai báo xung đột; hãy để trình biên dịch sinh mã hỗ trợ.
- **Cho rằng bridge có thể nhận mọi dữ liệu vì tham số là `Object`:** phép ép bên trong vẫn có thể thất bại.
- **Cho rằng chỉ phương thức có generic mới sinh bridge:** ví dụ kiểu trả về đồng biến không generic cũng cho thấy bridge.

## Thực hành kiểm chứng

1. Đổi chuỗi trong lần gọi reflection từ `"hello"` sang `"bridge"`; kết quả độ dài thành `6`, số lần vào thân vẫn bằng `3`.
2. Thử gọi `typed.map(Integer.valueOf(7))` trong một tệp riêng để thấy lỗi kiểu xuất hiện khi biên dịch trước khi có lời gọi bridge.
3. Lọc `getDeclaredMethods()` theo `!method.isBridge()` và xác nhận chỉ còn phương thức `Integer map(String)` trong lớp thực hiện ở ví dụ này.
4. Trong ví dụ đồng biến, đổi kiểu trả về của phương thức con từ `Integer` về `Number`. Sau khi biên dịch lại, khác biệt descriptor kết quả biến mất và không cần bridge đồng biến trong lớp con đó.
5. Dùng `javap` để chỉ ra chỗ ép đối số của bridge generic và so sánh với bridge chỉ thích ứng kiểu trả về ở ví dụ thứ hai.

Người học cần nối được hợp đồng generic ở mức nguồn, descriptor sau xóa kiểu và phương thức bridge chuyển tiếp; đồng thời phân biệt phương thức do tác giả viết với mã hỗ trợ mà reflection có thể nhìn thấy.