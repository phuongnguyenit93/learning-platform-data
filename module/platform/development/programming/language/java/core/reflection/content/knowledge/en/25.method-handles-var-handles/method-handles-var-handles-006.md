# `MethodHandle.invoke`, `invokeExact` và khác biệt chuyển đổi đối số

## 1. Mục tiêu bài học

`java.lang.invoke.MethodHandle` là một tham chiếu có kiểu tới một thao tác có thể gọi, như phương thức, constructor hoặc truy cập field. Mỗi handle có **`MethodType` riêng**. Khi gọi handle, điều quan trọng là chữ ký tại điểm gọi (call site) có khớp chữ ký của handle không.

Bài học giúp bạn:

- Đọc `handle.type()` để biết chính xác kiểu đối số, số lượng tham số và kiểu trả về.
- Dùng đúng `invokeExact(...)` (khớp hoàn toàn) và `invoke(...)` (có thể chuyển đổi kiểu).
- Giải thích boxing/unboxing, widening kiểu số, cast tham chiếu và lỗi chuyển đổi.
- Nhận diện vì sao **kiểu trả về tại call site** cũng khiến `invokeExact` thất bại.
- Chủ động xây dựng adapter với `asType(...)` khi muốn đổi chữ ký.
- Phân biệt `MethodHandle` với access mode của `VarHandle`.

Các ví dụ dưới đây chạy trên Java 17+ mà không cần thư viện ngoài.

## 2. `MethodType` là hợp đồng của MethodHandle

Ví dụ có phương thức:

```java
public static long sum(long a, long b) {
    return a + b;
}
```

Tạo handle tới phương thức tĩnh đó bằng `MethodHandles.Lookup.findStatic` (đoạn dưới được đặt trong lớp `MethodHandleInvokeDemo` có phương thức `sum`):

```java
MethodHandle sum = MethodHandles.lookup().findStatic(
        MethodHandleInvokeDemo.class, "sum",
        MethodType.methodType(long.class, long.class, long.class));
System.out.println(sum.type()); // (long,long)long
```

`MethodType.methodType(returnType, parameterTypes...)` nhận kiểu **kết quả đầu tiên**, sau đó là từng kiểu tham số. `(long,long)long` nghĩa là nhận `long, long` và trả `long`. `MethodType` không lưu tên phương thức, chỉ mô tả kiểu cần thiết để gọi.

**Hai kiểu cần phân biệt:**

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Target type** | Chữ ký thực tế của handle, xem qua `sum.type()` |
| **Call-site type** | Chữ ký phát sinh từ kiểu tĩnh của các biểu thức đối số và kiểu kết quả mà code tại điểm gọi mong đợi |

`invoke` và `invokeExact` là các phương thức **signature-polymorphic**: mỗi lời gọi được biên dịch với kiểu đối số và kiểu trả về thực tế tại đó. Dù khai báo API trông như `Object...`, lời gọi thông thường không tự đóng gói đối số vào `Object[]` theo cơ chế Java varargs. JVM kiểm tra chữ ký phát sinh từ bytecode.

## 3. `invokeExact` yêu cầu khớp chính xác, không chuyển đổi

Với handle `(long,long)long`, đây là lời gọi đúng:

```java
long answer = (long) sum.invokeExact(10L, 20L); // 30
```

Điểm gọi có kiểu `(long,long)long`, trùng hoàn toàn với `sum.type()`.

Ngược lại:

```java
long answer = (long) sum.invokeExact(10, 20L);
```

Lời gọi trên vẫn **biên dịch được** vì đây là API signature-polymorphic, nhưng khi chạy sẽ ném `WrongMethodTypeException`: số `10` có kiểu `int`; `invokeExact` không tự widen `int` thành `long`. Cách sửa: đổi thành `10L` hoặc `(long) 10`.

### Kiểu kết quả cũng phải khớp

```java
Object result = sum.invokeExact(10L, 20L);
```

Đoạn này cũng ném `WrongMethodTypeException`. Dù giá trị `long` có thể boxing thành `Long` ở nhiều ngữ cảnh Java khác, `invokeExact` không tự động boxing kết quả cho call site yêu cầu `Object`.

Ba trường hợp thường nhầm:

- `long x = (long) sum.invokeExact(10L, 20L);`: đúng; kiểu kết quả được yêu cầu là `long`.
- `Object x = sum.invokeExact(10L, 20L);`: sai; call site yêu cầu kiểu kết quả `Object`.
- `sum.invokeExact(10L, 20L);` viết thành câu lệnh độc lập: call site kỳ vọng `void`, nên cũng sai nếu handle trả `long`.

Muốn bỏ qua kết quả thì có thể gán vào một biến `long` phù hợp. `invokeExact` phải khớp **arity, kiểu mọi tham số và kiểu trả về**; không có ép kiểu ngầm theo nghĩa của `invoke`.

## 4. `invoke`: có thể thích nghi chữ ký bằng `asType`

Nếu call-site type trùng target type, `invoke` hoạt động như `invokeExact`. Khi khác, `invoke` thử thích nghi handle tương đương `handle.asType(callSiteType)` rồi thực thi. JVM có thể thực hiện tối ưu mà không tạo một adapter hữu hình.

```java
long answer = (long) sum.invoke(10, 20L); // 30
```

Call site có kiểu `(int,long)long`. `invoke` cho phép chuyển `int` sang `long` trước khi gọi `sum`.

Ví dụ khác:

```java
Object result = sum.invoke(10, 20);
System.out.println(result.getClass().getSimpleName()); // Long
```

Hai tham số `int` được widen thành `long`; kết quả primitive `long` được boxing thành `Long` để dùng như `Object`.

Các chuyển đổi điển hình có thể xảy ra khi `invoke` thích nghi kiểu gồm: primitive widening (ví dụ `int -> long`); boxing/unboxing giữa primitive và wrapper; cast giữa các reference type (có kiểm tra tại runtime); chuyển đổi kết quả tương thích. Các phép này tuân theo các quy tắc của `MethodHandle.asType`, **không phải phép chuyển đổi dữ liệu tùy ý**.

| Tình huống (target là kiểu ghi bên phải) | `invokeExact` | `invoke` |
| --- | --- | --- |
| `long` -> `long` | Được | Được |
| `int` -> `long` | `WrongMethodTypeException` | Có thể widen |
| `Integer` -> `int` | Sai kiểu tĩnh | Có thể unbox |
| `Object` chứa `String` -> `String` | Sai kiểu tĩnh | Có thể cast lúc chạy |
| `long` trả về -> `Object` tại call site | Sai kiểu trả về | Có thể boxing |
| Chuỗi `"123"` -> `long` | Sai kiểu | Không tự parse chuỗi |
| Thiếu hoặc thừa đối số | Sai | Sai cho handle có arity cố định |

**Lưu ý:** handle dạng *varargs collector* có thêm quy tắc thu gom đối số cuối. Với handle thông thường, `invoke` không tự thêm hoặc bỏ tham số; cần adapter phù hợp cho các thay đổi như vậy.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo tệp `MethodHandleInvokeDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleInvokeDemo {
    public static long sum(long a, long b) {
        return a + b;
    }

    public static String decorate(String text) {
        return "[" + text + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle sum = lookup.findStatic(
                MethodHandleInvokeDemo.class, "sum",
                MethodType.methodType(long.class, long.class, long.class));
        System.out.println(sum.type());

        long exact = (long) sum.invokeExact(10L, 20L);
        long flexible = (long) sum.invoke(10, 20L);
        Object boxed = sum.invoke(10, 20);
        System.out.println("exact=" + exact);
        System.out.println("invoke=" + flexible);
        System.out.println("boxed=" + boxed.getClass().getSimpleName());

        MethodHandle adapted = sum.asType(
                MethodType.methodType(long.class, int.class, long.class));
        long adaptedExact = (long) adapted.invokeExact(10, 20L);
        System.out.println("adaptedExact=" + adaptedExact);

        try {
            long ignored = (long) sum.invokeExact(10, 20L);
            System.out.println(ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("exact arguments mismatch");
        }

        try {
            Object ignored = sum.invokeExact(10L, 20L);
            System.out.println(ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("exact return mismatch");
        }

        MethodHandle decorate = lookup.findStatic(
                MethodHandleInvokeDemo.class, "decorate",
                MethodType.methodType(String.class, String.class));
        System.out.println((String) decorate.invoke((Object) "Java"));
        try {
            String ignored = (String) decorate.invoke((Object) Integer.valueOf(7));
            System.out.println(ignored);
        } catch (ClassCastException e) {
            System.out.println("bad runtime argument");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac MethodHandleInvokeDemo.java
java MethodHandleInvokeDemo
```

Kết quả chính xác đã kiểm chứng:

```text
(long,long)long
exact=30
invoke=30
boxed=Long
adaptedExact=30
exact arguments mismatch
exact return mismatch
[Java]
bad runtime argument
```

**Phân tích:** `sum.invokeExact(10L, 20L)` có chữ ký đúng. `sum.invoke(10, 20L)` widen `int` thành `long`. Khi gán kết quả `invoke` cho `Object`, `long` được boxing nên tên lớp là `Long`. Hai lời gọi exact cố ý sai lần lượt ở tham số `int` và ở kiểu kết quả `Object`, nên đều phát sinh `WrongMethodTypeException`. Cuối cùng, `decorate.invoke((Object) "Java")` chuyển `Object` thành `String` thành công vì đối tượng thật là chuỗi; giá trị thật là `Integer` gây `ClassCastException` khi cast.

Chương trình dùng `main(String[] args) throws Throwable` bởi `MethodHandle.invoke` và `invokeExact` có chữ ký `throws Throwable`; ngoại lệ do phương thức đích ném có thể đi xuyên qua handle. Trong sản phẩm thật, hãy có chính sách xử lý ngoại lệ rõ ràng.

## 6. Tạo adapter với `asType` để gọi exact

Nếu ứng dụng thường xuyên gọi theo chữ ký `(int,long)long` nhưng handle gốc mang kiểu `(long,long)long`, có thể tạo một handle mới:

```java
MethodHandle adapted = sum.asType(
        MethodType.methodType(long.class, int.class, long.class));

System.out.println(adapted.type()); // (int,long)long
long answer = (long) adapted.invokeExact(10, 20L); // 30
```

`adapted.type()` đã là `(int,long)long` nên `invokeExact` trên adapter không cần chuyển đổi nữa tại call site. Bên trong adapter, giá trị `int` được widen thành `long` để chuyển tới handle gốc. MethodHandle là đối tượng bất biến; `sum.type()` vẫn giữ nguyên.

Chọn cách gọi theo yêu cầu: dùng `invokeExact` khi biết chữ ký chính xác và muốn lỗi mismatch được phát hiện rõ; dùng `invoke` khi cần các phép chuyển đổi tương thích; dùng `asType` để biểu diễn adapter rõ ràng, tái sử dụng cùng chữ ký mới. `MethodHandles.explicitCastArguments` cho các trường hợp cố ý cần quy tắc cast rộng hơn `asType`, nhưng phải kiểm soát nguy cơ mất dữ liệu.

**Không đánh đồng với** `invokeWithArguments(...)`: API này chấp nhận `Object[]` hoặc `List<?>` và gọi theo dạng tổng quát, phù hợp lúc phải lấy danh sách đối số động. Ví dụ sau là mảnh code trong chương trình ở mục 5:

```java
Object result = sum.invokeWithArguments(10L, 20L);
System.out.println(result); // 30
```

`invokeWithArguments` có đặc điểm boxing/unboxing và xử lý danh sách đối số; không yêu cầu exact như `invokeExact`.

## 7. Kiểu tĩnh và kiểu runtime khác nhau

`invokeExact` căn cứ vào **kiểu tĩnh của biểu thức tại điểm gọi**, không dựa vào lớp thật mà một biến `Object` đang trỏ tới.

```java
Object value = Long.valueOf(10L);
```

Đối với handle `(long,long)long`:

- `(long) sum.invokeExact(value, 20L)`: sai vì call site có đối số đầu tiên kiểu `Object`.
- `(long) sum.invoke(value, 20L)`: có thể thành công nhờ runtime cast/unboxing từ `Object` chứa `Long` sang `long`.
- `long unboxed = ((Long) value).longValue();` rồi `(long) sum.invokeExact(unboxed, 20L)`: khớp exact.

Điều này cũng áp dụng cho biến khai báo bằng interface hoặc superclass; việc gán một instance cụ thể không làm thay đổi kiểu tĩnh của biến. Với generic, Java dùng kiểu sau **erasure** trong chữ ký lời gọi.

Khi nhận kết quả, kiểu mong đợi cũng quan trọng. Trong nhiều bài toán, một cast ngay trên biểu thức gọi `(long) handle.invokeExact(...)` không đơn thuần là cast giá trị *sau* lời gọi; nó giúp xác định **chính kiểu trả về của call site**.

## 8. Các ngoại lệ thường gặp

| Ngoại lệ | Tình huống | Cách xử lý |
| --- | --- | --- |
| `WrongMethodTypeException` với `invokeExact` | Chữ ký call site khác `handle.type()`, kể cả phần trả về | So sánh arity, kiểu tham số và return, thêm cast hoặc đổi literal |
| `WrongMethodTypeException` với `invoke` | Không thể tạo thích nghi `asType` hợp lệ hoặc arity không hợp lệ | Dùng kiểu tương thích hoặc adapter đúng mục đích |
| `ClassCastException` với `invoke` | Adapter cho phép cast tham chiếu, nhưng đối tượng thật không có kiểu phù hợp | Kiểm tra kiểu runtime trước khi gọi |
| `NullPointerException` khi chuyển kiểu | Unboxing `null` sang primitive | Chặn giá trị null hoặc chọn hợp đồng nhận reference |
| Ngoại lệ từ phương thức đích | Target thật ném ngoại lệ | Xử lý theo hợp đồng target |

Quy trình tìm lỗi: đọc `handle.type()`; liệt kê **kiểu tĩnh** mỗi đối số; xác định kiểu trả về tại call site (cast hay sử dụng như câu lệnh `void`); kiểm tra khả năng chuyển đổi `asType`; cuối cùng kiểm tra giá trị runtime và ngoại lệ target. Đừng “sửa” bằng cách cast mọi thứ thành `Object` khi gọi `invokeExact`, vì cách này thường làm chữ ký càng sai.

Một handle `findVirtual` còn đòi hỏi receiver phù hợp ở **đối số đầu tiên** (ví dụ gọi `String.length` qua handle có chữ ký `(String)int`). Đừng bỏ quên receiver khi đếm arity.

## 9. Liên hệ với `VarHandle`

`VarHandle` cùng thuộc gói `java.lang.invoke` nhưng cách dùng thông thường là qua các **access mode** như `get`, `set`, `compareAndSet`, thay vì trực tiếp gọi `MethodHandle.invoke` hay `MethodHandle.invokeExact`. Access mode cũng dùng signature-polymorphic invocation và có quy tắc kiểm tra kiểu.

Trong Java 17, có thể tạo VarHandle với **exact behavior**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleBehaviorDemo {
    private static int number;

    public static void main(String[] args) throws ReflectiveOperationException {
        VarHandle handle = MethodHandles.lookup().findStaticVarHandle(
                VarHandleBehaviorDemo.class, "number", int.class);
        handle.set(7);
        System.out.println((int) handle.get());

        VarHandle exactBehavior = handle.withInvokeExactBehavior();
        exactBehavior.set(9);
        System.out.println((int) exactBehavior.get());
    }
}
```

Lưu thành `VarHandleBehaviorDemo.java`, chạy:

```bash
javac VarHandleBehaviorDemo.java
java VarHandleBehaviorDemo
```

Kết quả đã kiểm chứng:

```text
7
9
```

`withInvokeExactBehavior()` đặt chế độ kiểm tra **chữ ký chính xác của access mode**, không tạo ra MethodHandle mới. Muốn lấy MethodHandle ứng với một access mode, tìm hiểu `VarHandle.toMethodHandle(VarHandle.AccessMode)`.

## 10. Câu hỏi tự kiểm tra

1. Với handle `(long,long)long`, `(long) h.invokeExact(1, 2L)` chạy không? **Không**, đối số `1` là `int`. Dùng `1L`.
2. `Object x = h.invoke(1, 2)` có thể chạy không? **Có** khi phép thích nghi hợp lệ: widen hai `int` thành `long` và boxing kết quả `long` thành `Long`.
3. Vì sao `Object x = h.invokeExact(1L, 2L)` sai? **Kiểu kết quả `Object` của call site khác `long` của handle**.
4. `asType` có sửa `h` ban đầu không? **Không**; trả handle mới với chữ ký mới.
5. Vì sao `invoke` có thể ném `ClassCastException` dù adapter hợp lệ? **Giá trị runtime** không thỏa cast tham chiếu.
6. Nếu các đối số chỉ có sẵn trong `List<?>` tại runtime, nên tìm hiểu API nào? `invokeWithArguments(List<?>)`.
7. Lệnh `h.invokeExact(...)` được dùng như statement trong khi target trả `long` có thể thất bại vì đâu? Vì kiểu kết quả tại call site trở thành `void`.

## 11. Ghi nhớ và tài liệu tham khảo

- `invokeExact`: khớp 100% kiểu tại call site với `handle.type()`, gồm tham số **và return**.
- `invoke`: thích nghi chữ ký thông qua quy tắc `asType` nếu hợp lệ; không tự parse mọi dữ liệu.
- `asType`: tạo adapter có kiểu mới, giúp dùng `invokeExact` với chữ ký được chủ động xác định.
- `WrongMethodTypeException` là dấu hiệu cần kiểm tra kiểu của **cả hai phía**, còn `ClassCastException` thường liên quan giá trị reference ở runtime.
- `VarHandle` dùng access modes, có `withInvokeExactBehavior()` để chọn yêu cầu exact khi truy cập biến.

Tài liệu JDK 17 chính thức:

- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)