# Vì sao `getMethod` không tự giải overload như trình biên dịch?

## 1. Hai thao tác có mục đích khác nhau

**Overload (nạp chồng phương thức)** là nhiều phương thức cùng tên nhưng khác danh sách kiểu tham số. Với lời gọi `obj.send(value)` trong mã Java, **trình biên dịch** phải xác định một overload thích hợp dựa trên kiểu *tại thời điểm biên dịch* của đối số và quy tắc của ngôn ngữ.

Ngược lại, `Class.getMethod(String name, Class<?>... parameterTypes)` là API Reflection để **tra cứu một phương thức public có tên và danh sách kiểu tham số khai báo được chỉ rõ**. Những `Class<?>` truyền vào mô tả chữ ký phương thức **cần tìm**; chúng không phải dữ liệu đầu vào để tự chọn overload.

Giả sử có `send(int)` và `send(long)`:

- `send((short) 7)` trong mã nguồn chọn `send(int)`, nhờ chuyển đổi mở rộng kiểu nguyên thủy (`short` sang `int`).
- `SomeClass.class.getMethod("send", short.class)` chỉ tìm đúng `send(short)`. Nếu không khai báo chữ ký ấy, nó ném `NoSuchMethodException`, dù `send(int)` nhận được giá trị `short` khi gọi trực tiếp.

**Tra cứu chữ ký chính xác** và **giải lời gọi overload** là hai bài toán khác nhau.

## 2. Trình biên dịch giải overload như thế nào?

Trình biên dịch có thông tin về tên phương thức, số lượng đối số, **kiểu tĩnh của từng biểu thức**, những phương thức có thể nhìn thấy, thông tin generic và ngữ cảnh lời gọi. Theo Java Language Specification, quy trình chọn phương thức có những giai đoạn chính:

1. Thử các phương thức với số tham số cố định, **chưa cần boxing/unboxing**, nhưng có thể dùng widening primitive (`short → int`) hoặc widening reference (`Integer → Number`).
2. Nếu chưa tìm được phương thức áp dụng được, xét thêm boxing/unboxing và các phép chuyển đổi được cho phép trong lời gọi.
3. Nếu vẫn chưa được, xét lời gọi `varargs` theo dạng số đối số biến đổi.
4. Ở giai đoạn đầu tiên có ứng viên phù hợp, chọn overload *most specific* theo quy tắc Java; nếu không chọn duy nhất được, báo lỗi **ambiguous**.

Quy tắc thực tế còn xét kế thừa, generic type inference và khả năng truy cập; không thể thay bằng mỗi phép `Class.isAssignableFrom()`.

**Kiểu tĩnh không luôn giống kiểu runtime.** Nếu có `send(Object)`, `send(String)` và khai báo `Object x = "hello";`, lời gọi `send(x)` được biên dịch sang `send(Object)`, vì kiểu tĩnh của `x` là `Object`. Trong khi đó, `x.getClass()` trả `String.class`: dùng lớp runtime để đoán overload có thể cho kết quả khác trình biên dịch.

## 3. `Class.getMethod` so khớp những gì?

Dạng API:

~~~java
Method method = SomeClass.class.getMethod(
    "methodName",
    FirstParameterType.class,
    SecondParameterType.class
);
~~~

Đây là đoạn **minh họa cú pháp**, không phải chương trình Java hoàn chỉnh. `getMethod` so khớp **tên** và **các kiểu tham số khai báo theo đúng thứ tự**. Không thực hiện chuyển đổi kiểu, không xem giá trị đối số, không tự chọn overload “gần nhất”. Ví dụ:

| Tra cứu | Kết quả yêu cầu |
| --- | --- |
| `getMethod("send", int.class)` | Chính xác `send(int)`. |
| `getMethod("send", Integer.class)` | Chính xác `send(Integer)`, khác `send(int)`. |
| `getMethod("send", Number.class)` | Chính xác `send(Number)`, không tự chuyển sang `send(Object)`. |
| `getMethod("batch", String[].class)` | Khớp `batch(String...)`, vì tham số varargs thực chất là mảng. |
| `getMethod("batch", String.class, String.class)` | Không khớp `batch(String...)`, dù mã nguồn có thể gọi `batch("a", "b")`. |

`getMethod` tìm các phương thức **public**, bao gồm phương thức public đủ điều kiện được kế thừa. `getDeclaredMethod` vẫn yêu cầu kiểu tham số chính xác, nhưng chỉ tìm phương thức khai báo ngay trong lớp/interface ấy, bao gồm cả thành viên không public. Không tìm thấy chữ ký thì ném `NoSuchMethodException`.

Với generic, Reflection nhìn chữ ký sau **type erasure**: phương thức `accept(List<String>)` thường phải tra bằng `List.class`; Java không có biểu thức `List<String>.class`. API `getMethod` cũng không nhận kiểu trả về làm tham số lựa chọn. Đôi khi compiler sinh bridge/synthetic methods; nếu duyệt danh sách phương thức, hãy xét `isBridge()` và `isSynthetic()`.

## 4. Chương trình Java 17+ minh họa đầy đủ

Lưu thành `ReflectionOverloadDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectionOverloadDemo {
    public void send(int value) {
        System.out.println("send(int): " + value);
    }

    public void send(long value) {
        System.out.println("send(long): " + value);
    }

    public void send(Integer value) {
        System.out.println("send(Integer): " + value);
    }

    public void send(Number value) {
        System.out.println("send(Number): " + value);
    }

    public void send(Object value) {
        System.out.println("send(Object): " + value);
    }

    public void batch(String... items) {
        System.out.println("batch: " + Arrays.toString(items));
    }

    public static void main(String[] args) throws Exception {
        ReflectionOverloadDemo target = new ReflectionOverloadDemo();
        short n = 7;

        // Compiler chọn overload từ kiểu tĩnh của lời gọi.
        target.send(n);
        target.send(Integer.valueOf(7));
        target.send((Number) Integer.valueOf(7));

        // Không có đúng chữ ký send(short).
        try {
            ReflectionOverloadDemo.class.getMethod("send", short.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Không có send(short)");
        }

        // Reflection yêu cầu ta chỉ rõ chữ ký.
        Method intMethod =
                ReflectionOverloadDemo.class.getMethod("send", int.class);
        intMethod.invoke(target, 7);

        Method numberMethod =
                ReflectionOverloadDemo.class.getMethod("send", Number.class);
        numberMethod.invoke(target, Integer.valueOf(7));

        try {
            ReflectionOverloadDemo.class.getMethod("send", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Không có send(String)");
        }

        // String... được khai báo dưới dạng String[].
        Method batchMethod =
                ReflectionOverloadDemo.class.getMethod("batch", String[].class);
        batchMethod.invoke(target, (Object) new String[]{"a", "b"});
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac ReflectionOverloadDemo.java
java ReflectionOverloadDemo
~~~

Stdout chính xác:

~~~text
send(int): 7
send(Integer): 7
send(Number): 7
Không có send(short)
send(int): 7
send(Number): 7
Không có send(String)
batch: [a, b]
~~~

Các quan sát:

- Biến `n` có kiểu `short`, nên lời gọi Java thường chọn `send(int)`, nhưng tra `getMethod("send", short.class)` vẫn thất bại.
- `int.class` khác `Integer.class`. Giá trị `7` khi truyền cho `Method.invoke(Object, Object...)` được boxing vào `Integer`, rồi Reflection có thể unboxing cho tham số `int` đã chọn.
- `numberMethod` đã cố định `send(Number)`. Truyền đối số `Integer` cho `invoke` không làm nó chuyển sang overload `send(Integer)`.
- `String... items` trở thành một tham số `String[]`. Ép `(Object) new String[]{...}` buộc lời gọi `invoke` nhận **một đối số là mảng** thay vì nhầm các phần tử với danh sách đối số của `invoke`.

## 5. Vì sao `Method.invoke` nhận được một số chuyển đổi?

Có hai bước khác nhau:

~~~text
Class.getMethod("send", int.class)
            |
            v
 Method đại diện send(int)     (đã chọn chính xác overload)
            |
            v
 method.invoke(target, value) (gọi Method đã chọn)
~~~

`Method.invoke` **không chạy overload resolution**. Nó chỉ kiểm tra/chuyển đổi các đối số so với kiểu tham số của **Method đang cầm**. Theo JDK, Reflection có thể unboxing và mở rộng kiểu nguyên thủy phù hợp khi thực thi; chuyển đổi thu hẹp kiểu nguyên thủy (*narrowing*) không hợp lệ dẫn tới `IllegalArgumentException`. Method đích có varargs cũng không khiến `Method.invoke` tự gom các đối số của người gọi theo cú pháp Java. Nếu chính phương thức đích ném ngoại lệ, Reflection thường bọc trong `InvocationTargetException`.

Do đó, `invoke` có thể gọi `send(int)` với một `Integer` chứa giá trị `7`, **nhưng `getMethod("send", Integer.class)` không vì thế mà tìm thành `send(int)`**.

## 6. Cách dùng đúng trong thực tế

**Khi đã biết API:** ghi rõ danh sách kiểu tham số khai báo. Phương thức nhận `int` thì dùng `int.class`; nhận `Number` thì `Number.class`; nhận `String...` thì `String[].class`. Sau đó gọi `invoke` với đúng số lượng đối số và giá trị tương thích.

**Khi phải điều phối từ dữ liệu động:** có thể duyệt `getMethods()`, lọc tên và tự xây bộ chọn overload. Tuy nhiên bộ chọn đủ chính xác phải hiểu primitive/wrapper, widening, reference hierarchy, `null`, varargs, generic/bridge methods và overload mơ hồ. Chỉ dùng `arg.getClass()` hay `isAssignableFrom()` là chưa đủ. Với JSON, HTTP hoặc cấu hình, cách dễ kiểm soát hơn là định nghĩa rõ tên thao tác và chữ ký hợp lệ trong hợp đồng dữ liệu.

**Khi dùng Method Handles:** `MethodHandles.Lookup.findVirtual` hay `findStatic` cũng đòi hỏi `MethodType` đã xác định; đây không phải bộ giải overload ngầm tương đương compiler.

### Những lỗi phổ biến

1. Dùng `Integer.class` để tìm `method(int)`, hoặc dùng `int.class` để tìm `method(Integer)`.
2. Lấy `arg.getClass()` như thể đó là kiểu tĩnh của biến: primitive bị boxing; đối số `null` không có `getClass()`.
3. Tìm `method(String...)` bằng nhiều `String.class` thay vì một `String[].class`.
4. Dùng `getMethod` để tìm `private` method. `getDeclaredMethod` có thể tìm phương thức khai báo không public, nhưng muốn gọi có thể cần quyền truy cập; `setAccessible` còn chịu giới hạn của Java Platform Module System.
5. Lấy “phương thức đầu tiên” từ `getMethods()`: thứ tự mảng không được dùng như thứ tự ưu tiên overload.

## 7. Câu hỏi tự kiểm tra

- Chỉ có `f(long)`: `f(3)` có biên dịch? **Có**, do `int → long`. Vậy `getMethod("f", int.class)` có tìm thấy không? **Không**, vì không hề có `f(int)`.
- Có `f(String)` và `f(Integer)`: `f(null)` có chọn được overload duy nhất? **Không**, lời gọi mơ hồ vì hai kiểu tham số này không có quan hệ đặc hiệu; Reflection phải chỉ rõ `String.class` hoặc `Integer.class`.
- Lấy `getMethod("f", String.class)` rồi gọi `invoke(instance, new Object[]{null})`: có thể chuyển sang `f(Integer)` không? **Không**. `Method` đã đại diện `f(String)`.

**Ghi nhớ:** compiler giải **lời gọi** dựa vào kiểu biểu thức và quy tắc Java; `getMethod` tra **chữ ký phương thức chính xác** từ danh sách `Class` bạn cung cấp. `invoke` chỉ thực thi phương thức đã được chọn.

### Đọc thêm tài liệu chuẩn

- [JDK 17: `Class.getMethod` và `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getMethod(java.lang.String,java.lang.Class...))
- [JDK 17: `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java Language Specification §15.12: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12)
