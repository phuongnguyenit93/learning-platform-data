# Phân biệt quy tắc tra cứu phương thức với quy tắc chuyển đổi đối số khi gọi bằng Reflection

Trong Java Reflection, **tìm một phương thức** và **gọi phương thức đã tìm thấy** là hai giai đoạn có quy tắc kiểu dữ liệu khác nhau:

1. **Tra cứu:** `Class.getMethod(name, parameterTypes...)` hoặc `Class.getDeclaredMethod(name, parameterTypes...)` xác định một `Method` theo **tên và danh sách kiểu tham số được khai báo**, trong phạm vi public/declared phù hợp. Kiểu tham số truyền cho hàm tra cứu là các đối tượng `Class<?>`. Java không tự tìm overload bằng phép chuyển đổi `byte -> long`, boxing `int -> Integer`, hoặc quan hệ kế thừa `Integer -> Number`.
2. **Gọi:** Khi đã có đối tượng `Method`, `Method.invoke(receiver, args...)` thực hiện kiểm tra quyền truy cập, receiver, số đối số và **khả năng chuyển đổi đối số thực tế** sang các kiểu formal parameter. Trong những điều kiện phù hợp, Reflection cho phép **unboxing** giá trị wrapper sang primitive, **widening primitive conversion**, và gán một đối tượng reference cho kiểu tham chiếu tương thích. Nó không cho phép narrowing primitive conversion.

Sự khác biệt này giải thích vì sao `getMethod("work", byte.class)` không tìm được `work(long)`, trong khi `getMethod("work", long.class).invoke(obj, Byte.valueOf((byte) 7))` có thể chạy thành công.

## 1. Giai đoạn tra cứu: chọn phương thức theo khai báo

Ví dụ một lớp có hai overload:

```java
class Service {
    public void process(int value) {}
    public void process(long value) {}
}
```

Đây là đoạn mã minh họa định nghĩa lớp. Với `Service.class`:

```java
Method intMethod = Service.class.getMethod("process", int.class);
Method longMethod = Service.class.getMethod("process", long.class);
```

Hai lời gọi yêu cầu chính xác `process(int)` và `process(long)`. Nếu thay `int.class` hoặc `long.class` bằng `byte.class`, `getMethod` không chọn “ứng viên gần nhất” để tiện cho caller. Nếu không có `process(byte)`, kết quả là **`NoSuchMethodException`**.

**Kiểu trong lệnh tra cứu là kiểu formal parameter**, không phải một đối số runtime đang được chuẩn bị truyền vào phương thức. Vì vậy:

- `int.class` khác `Integer.class`: không có boxing/unboxing để tìm phương thức.
- `long.class` khác `int.class`: không có widening để tìm phương thức.
- `Number.class` khác `Integer.class`: tra cứu không tự thay kiểu trong danh sách tham số dựa trên kế thừa.
- `String[].class` khác `String.class`: tham số varargs khai báo `String...` có kiểu mảng `String[]` trong metadata.
- Thứ tự và **số lượng** tham số đều cần đúng: `calculate(int, long)` khác `calculate(long, int)`.

### getMethod và getDeclaredMethod khác nhau về phạm vi

| API | Phương thức được tra cứu |
| --- | --- |
| `getMethod(name, parameterTypes...)` | Các phương thức `public` có thể nhìn thấy qua kiểu đang xét, bao gồm phương thức kế thừa phù hợp |
| `getDeclaredMethod(name, parameterTypes...)` | Phương thức được khai báo trực tiếp tại chính class/interface ấy, kể cả `private` hoặc package-private; không duyệt lên superclass |

Cả hai vẫn dùng tên và danh sách kiểu tham số khai báo để tìm method, không thực hiện overload resolution như khi compiler xử lý một lời gọi Java thông thường. `getDeclaredMethod` có thể **lấy metadata** của private method, nhưng lấy được metadata không tự cấp quyền `invoke`; quyền truy cập được xét sau.

**Không truyền kiểu trả về vào `getMethod` hay `getDeclaredMethod`.** Kết quả `getReturnType()` là metadata đọc được *sau khi tra cứu*. Với một số class file có bridge methods hoặc các method có cùng tên/danh sách tham số mà khác kiểu trả về, API có quy tắc lựa chọn riêng theo độ cụ thể của kiểu trả về; do đó công cụ phân tích bytecode nâng cao còn cần kiểm tra `Method.isBridge()` và `isSynthetic()`. Điều này không biến tra cứu Reflection thành cơ chế tự ép kiểu đối số.

### Đừng nhầm với overload resolution lúc biên dịch

Với mã Java thông thường:

```java
byte b = 7;
new Service().process(b);
```

Đây là đoạn mã trong ngữ cảnh có `Service` ở trên. **Compiler** xét các overload có thể áp dụng theo Java Language Specification; trường hợp `process(int)` và `process(long)` ở đây, nó chọn `process(int)` vì `int` là ứng viên cụ thể hơn cho `byte`.

Reflection không được truyền một biểu thức `b` vào `getMethod` để compiler tự chọn. Người dùng Reflection **phải quyết định method cần lấy** bằng `Class<?>...` trước, rồi `invoke` trên method đã được chọn.

## 2. Giai đoạn gọi: Method.invoke thực hiện conversion cho đối số

Cú pháp chính:

```java
Object result = method.invoke(receiver, arg1, arg2);
```

Đây là đoạn mã minh họa, giả định đã có `Method method`, `receiver`, `arg1`, `arg2` hợp lệ; code cần xử lý các ngoại lệ Reflection.

`Method.invoke(Object obj, Object... args)` có hai loại tham số ở tầng Reflection:

- `obj` là **receiver** của instance method; đối với static method, receiver bị bỏ qua nên thường truyền `null`.
- `args` là các giá trị dùng cho các formal parameter của method. Số lượng giá trị phải phù hợp, và mỗi giá trị phải chuyển đổi được sang kiểu formal parameter tương ứng.

Vì `invoke` nhận `Object...`, khi truyền giá trị primitive trực tiếp trong mã Java gọi `invoke`, **compiler sẽ boxing giá trị đó** để đưa vào mảng `Object[]`. Sau đó `Method.invoke` xử lý đối tượng wrapper và áp dụng các conversion được cho phép để chuyển sang kiểu tham số primitive của phương thức đích.

Ví dụ, nếu `method` đại diện cho `process(long)`, các cách gọi sau đều có thể hợp lệ về kiểu:

```java
method.invoke(receiver, Byte.valueOf((byte) 7));
method.invoke(receiver, Integer.valueOf(8));
method.invoke(receiver, Long.valueOf(9L));
```

Chúng có thể dùng giá trị wrapper `Byte`, `Integer`, `Long` vì việc unboxing và, nếu cần, widening primitive đưa chúng tới `long`. Nhưng `Double` hoặc `Float` không thể được truyền tới tham số `long` qua narrowing.

Điều quan trọng là **`invoke` không tìm lại overload khác** khi nhận đối số. Nếu `Method` đã chỉ tới `process(long)`, chính phương thức đó được gọi (có xét dynamic dispatch đối với override), dù trong cùng lớp còn `process(int)` phù hợp hơn với một kiểu giá trị nào đó.

## 3. Ví dụ Java 17+ đầy đủ: chứng minh tra cứu và gọi khác nhau

Tạo tệp `ReflectionLookupDemo.java`:

```java
import java.lang.reflect.Method;

public class ReflectionLookupDemo {
    public static class Service {
        public String describe(int v) {
            return "int:" + v;
        }

        public String describe(long v) {
            return "long:" + v;
        }

        public String accept(Number value) {
            return "Number:" + value;
        }

        public String join(String... values) {
            return String.join("/", values);
        }

        public int twice(int value) {
            return value * 2;
        }
    }

    public static void main(String[] args) throws Exception {
        Service s = new Service();
        Class<?> type = Service.class;

        Method m = type.getMethod("describe", long.class);
        System.out.println(
                "lookup(long)=" + m.getParameterTypes()[0].getSimpleName()
        );

        try {
            type.getMethod("describe", byte.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup(byte)=not found");
        }

        System.out.println(
                "invoke Byte->long=" + m.invoke(s, Byte.valueOf((byte) 7))
        );
        System.out.println(
                "invoke Integer->long=" + m.invoke(s, Integer.valueOf(8))
        );

        try {
            m.invoke(s, Double.valueOf(9.0));
        } catch (IllegalArgumentException e) {
            System.out.println("invoke Double->long=rejected");
        }

        Method n = type.getMethod("accept", Number.class);
        System.out.println(
                "invoke Integer->Number=" + n.invoke(s, Integer.valueOf(5))
        );

        try {
            type.getMethod("accept", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup accept(Integer)=not found");
        }

        Method v = type.getMethod("join", String[].class);
        System.out.println(
                "join(array)=" + v.invoke(s, (Object) new String[] {"a", "b"})
        );

        try {
            v.invoke(s, "a", "b");
        } catch (IllegalArgumentException e) {
            System.out.println("join(elements)=rejected");
        }

        Method twice = type.getMethod("twice", int.class);
        Object result = twice.invoke(s, Integer.valueOf(11));
        System.out.println(
                "return=" + result
                + ",type=" + result.getClass().getSimpleName()
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ReflectionLookupDemo.java
java ReflectionLookupDemo
```

Đầu ra:

```text
lookup(long)=long
lookup(byte)=not found
invoke Byte->long=long:7
invoke Integer->long=long:8
invoke Double->long=rejected
invoke Integer->Number=Number:5
lookup accept(Integer)=not found
join(array)=a/b
join(elements)=rejected
return=22,type=Integer
```

Phân tích:

1. `getMethod("describe", long.class)` tìm đúng overload `describe(long)`. `getMethod("describe", byte.class)` **không** tự áp dụng `byte -> int` hay `byte -> long`; cả hai vẫn là kiểu tham số khác `byte`.
2. Sau khi đã lấy đúng `describe(long)`, `invoke` với `Byte` hoặc `Integer` thành công nhờ unboxing cộng widening; method được chọn vẫn là overload nhận **`long`**, như chuỗi `long:7` và `long:8` chứng minh.
3. `Double` không phù hợp với formal parameter `long`; `invoke` ném `IllegalArgumentException`, chương trình bắt và in thông báo rõ ràng.
4. `getMethod("accept", Number.class)` tìm chính xác method khai báo `Number`, nhưng `invoke` nhận `Integer` vì đó là subtype phù hợp. Tra cứu với `Integer.class` lại không chọn thay `accept(Number)`.
5. Tham số `String... values` của method `join` được phản chiếu dưới dạng **`String[]`**. `invoke(s, (Object) new String[] {"a","b"})` đưa một đối số mảng vào method và trả `a/b`; `invoke(s, "a", "b")` đưa hai đối số riêng nên bị từ chối vì method chỉ khai báo **một** formal parameter kiểu `String[]`.
6. `twice(int)` trả kiểu primitive `int`, nhưng `Method.invoke` trả về `Object`, vì vậy giá trị trả về được **boxing** thành `Integer`. Đây là **quy tắc kết quả của invoke**, khác với việc chọn method và chuyển đổi đối số.

Ví dụ chủ động bắt hai loại lỗi khác nhau: `NoSuchMethodException` phát sinh khi **tra cứu không khớp**, còn `IllegalArgumentException` phát sinh khi đã có `Method` nhưng **đối số gọi không phù hợp**.

## 4. Quy trình chọn method và gọi đúng

Khi tạo công cụ gọi method động, hãy tách hẳn quyết định *chọn phương thức* khỏi bước *thực hiện phép gọi*:

1. **Xác định phạm vi:** tìm chỉ method declared hay cả public methods được kế thừa; kiểm tra ngữ cảnh module/quyền truy cập.
2. **Chọn method đích:** dựa trên tên và danh sách **formal parameter types**. Nếu phải tự xử lý overload, hãy xác định chính sách ứng viên và mức ưu tiên conversion; đừng phụ thuộc thứ tự `getMethods()`.
3. **Chuẩn bị receiver:** `null` cho static method hoặc instance phù hợp cho instance method.
4. **Chuẩn bị đối số:** số lượng khớp formal parameters; primitive nhận wrapper có thể unbox/widen; reference nhận object assignment-compatible hoặc `null`; formal varargs của method đích nhận một mảng thích hợp.
5. **Gọi `invoke` và xử lý lỗi:** phân biệt tra cứu sai, không có quyền, conversion không hợp lệ, và exception từ method đích.
6. **Xử lý kết quả:** `invoke` trả `Object`; primitive result được boxing, `void` trả `null`. Nếu cần kiểu cụ thể, cast/kiểm tra trước khi dùng.

Khi implement một overload resolver riêng, cần cân nhắc `null` với nhiều reference overload, interface/superclass distances, primitive widening, boxing/unboxing, varargs và ambiguity. Java compiler có quy tắc chọn overload tương đối phức tạp; Reflection không tự “chạy lại compiler” với đối số runtime, nên việc viết một resolver thủ công chỉ từ `getName()` và `getParameterCount()` rất dễ chọn sai.

## 5. Câu hỏi tự kiểm tra

1. Lớp chỉ khai báo `work(long)`. `getMethod("work", int.class)` có tìm được không? **Không.** Tra cứu yêu cầu formal parameter `long.class` chính xác.
2. Sau khi có `Method` của `work(long)`, có thể `invoke` với `Integer.valueOf(3)` không? **Có.** `Integer` unbox thành `int`, rồi widening sang `long`.
3. Có thể `invoke` với `Double.valueOf(3.0)` cho `work(long)` không? **Không.** `double -> long` là narrowing.
4. Method khai báo `save(Number)`. Tra cứu bằng `Integer.class` có tìm được không? **Không.** Phải tìm `Number.class`; sau đó mới có thể invoke với `Integer`.
5. Method khai báo `String... names`. Kiểu để tra cứu là gì? **`String[].class`**.
6. Có thể dùng `invoke(receiver, "A", "B")` để tự động gói thành `String[]` cho method đích varargs không? **Không.** Cần một đối số mảng.
7. Nếu method đích ném `IllegalStateException`, `invoke` báo qua ngoại lệ nào? **`InvocationTargetException`**; kiểm tra `getCause()`.
8. Nếu method đích trả `int`, kiểu của `Method.invoke` là gì? **`Object`**, chứa `Integer` đã boxing. Method đích trả `void` thì `invoke` trả `null`.

## 6. Tài liệu tham khảo

- [Oracle Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): tài liệu `getMethod`, `getDeclaredMethod`, kiểu tham số, phạm vi và quy tắc tra cứu.
- [Oracle Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): tài liệu `invoke`, khả năng chuyển đổi đối số, varargs, return boxing và ngoại lệ.
- [Java Language Specification SE 21 — §5.1 Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html): widening/narrowing primitive, boxing/unboxing và những ngữ cảnh conversion.
- [Java Language Specification SE 21 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): cơ chế chọn overload trong **lời gọi Java thông thường**, giúp phân biệt với tra cứu Reflection.

**Ghi nhớ:** `Class.getMethod/getDeclaredMethod` tìm **khai báo khớp tên và kiểu tham số**, còn `Method.invoke` kiểm tra và **chuyển đổi các đối số thật** trong giới hạn được API cho phép. Trộn hai giai đoạn sẽ dẫn đến `NoSuchMethodException`, `IllegalArgumentException` hoặc chọn sai overload.