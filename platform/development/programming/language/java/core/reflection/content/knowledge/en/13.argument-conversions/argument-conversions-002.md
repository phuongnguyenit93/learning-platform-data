# Unboxing và widening primitive khi gọi `Method.invoke` hoặc `Constructor.newInstance`

Khi gọi một phương thức hay constructor qua Java Reflection, tham số mà ứng dụng cung cấp đi qua một API nhận **`Object` hoặc `Object...`**, trong khi chữ ký gốc có thể đòi `int`, `long`, `double` hoặc các kiểu primitive khác. Java Reflection có quy tắc chuyển đổi tương ứng để đưa các đối số runtime vào đúng formal parameter của phương thức/constructor đích:

1. Nếu formal parameter là primitive, đối số phù hợp thường là một **wrapper object** như `Integer`, `Byte`, `Character`. Reflection có thể **unbox** wrapper thành primitive.
2. Sau khi unbox, Reflection có thể thực hiện **widening primitive conversion** — ví dụ `byte → long` hoặc `int → double`.
3. Reflection **không thực hiện narrowing primitive conversion** như `long → int` hoặc `double → long`, ngay cả khi giá trị thực tế trông có vẻ vừa phạm vi đích.
4. Khi số lượng đối số, receiver, quyền truy cập hoặc kiểu dữ liệu không phù hợp, Reflection phát sinh exception thích hợp; đặc biệt chuyển đổi đối số không hợp lệ thường gây `IllegalArgumentException` **trước khi body của method/constructor được thực thi**.

Hai API trọng tâm:

~~~java
Object result = method.invoke(receiver, arg1, arg2);
Object created = constructor.newInstance(arg1, arg2);
~~~

Đây là các biểu thức minh họa: `method` phải là `java.lang.reflect.Method`, `constructor` phải là `java.lang.reflect.Constructor<?>`; các reflection checked exceptions cần được xử lý. Bài học phân biệt rõ **kiểu formal khai báo**, **kiểu runtime của đối số**, **unboxing**, **widening**, và các lỗi dễ gặp khi dùng API varargs.

## 1. Bối cảnh: primitive, wrapper và API nhận `Object...`

Primitive không phải object, nhưng Java có wrapper tương ứng:

| Primitive | Wrapper | Ví dụ object |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 5)` |
| `short` | `Short` | `Short.valueOf((short) 5)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(5)` |
| `long` | `Long` | `Long.valueOf(5L)` |
| `float` | `Float` | `Float.valueOf(2.5f)` |
| `double` | `Double` | `Double.valueOf(2.5)` |

Ví dụ lời gọi source:

~~~java
someMethod.invoke(receiver, 5, 2.5);
~~~

Tại **lời gọi tới `invoke(Object, Object...)`**, biểu thức `5` và `2.5` được Java compiler **boxing** thành các object có kiểu tương ứng `Integer` và `Double` để đưa vào mảng `Object[]`. Sau đó, khi Reflection gọi **phương thức đích**, các wrapper có thể được **unbox** và **widen** theo chữ ký formal thực tế.

Cần phân biệt ba lớp:

- **Compile time của mã gọi Reflection:** compiler nhìn thấy `invoke(Object, Object...)` hay `newInstance(Object...)`, chứ không tự chọn overload của method đích dựa trên từng argument.
- **Runtime argument matching:** Reflection kiểm tra số lượng formal parameters, kiểu tham số và giá trị object thật, rồi áp dụng chuyển đổi được phép.
- **Invocation của body đích:** chỉ xảy ra nếu các kiểm tra và phép chuyển đổi cần thiết thành công; exception bên trong body được xử lý theo cơ chế `InvocationTargetException`.

`Constructor.newInstance` không phải `Class.newInstance()`. Trong Java hiện đại, nên dùng `getDeclaredConstructor(...).newInstance(...)` hoặc `getConstructor(...).newInstance(...)`; `Class.newInstance()` đã deprecated.

## 2. Unboxing trong Reflection thực sự là gì?

Giả sử phương thức đích:

~~~java
public static void record(int code) { /* ... */ }
~~~

Đây là phương thức minh họa, cần đặt trong class Java. Nếu ta tra được `Method` cho `record(int)`, các đối số sau tương thích:

~~~java
method.invoke(null, Integer.valueOf(7)); // Integer unbox -> int
method.invoke(null, Byte.valueOf((byte) 7)); // Byte unbox -> byte, widen -> int
method.invoke(null, Character.valueOf('A')); // Character unbox -> char, widen -> int
~~~

`null` receiver ở đây hợp lệ vì `record` là **static method**. Với instance method, receiver phải là object phù hợp kiểu khai báo method; truyền `null` receiver gây `NullPointerException`.

Điểm quan trọng: Reflection **không phải** một converter tổng quát. Nó không parse `"7"` thành `int`, không gọi `Number.intValue()` cho mọi subtype của `Number` và không chọn “kiểu số gần nhất” theo giá trị.

~~~java
method.invoke(null, "7");      // Sai kiểu -> IllegalArgumentException
method.invoke(null, null);     // Cú pháp mơ hồ do varargs; nên ép kiểu rõ nghĩa.
method.invoke(null, (Object) null); // Một đối số null cho int -> IllegalArgumentException
~~~

Trong lời gọi trực tiếp `method.invoke(null, null)`, Java có thể hiểu `null` là **cả mảng `Object[]` của varargs** và compiler cảnh báo; do đó dùng `(Object) null` hoặc `new Object[] { null }` khi chủ ý truyền **một null argument**. Với một method đích có một primitive parameter, null không thể unbox và Reflection báo `IllegalArgumentException`.

### Wrapper phải khớp kiểu nguyên thủy nguồn

Với formal type `int`, `Integer`, `Byte`, `Short` và `Character` đều có lộ trình unbox rồi widen hợp lệ. Nhưng `Long` và `Double` không có lộ trình widening về `int`:

~~~java
method.invoke(null, Long.valueOf(7L));   // Không có long -> int widening
method.invoke(null, Double.valueOf(7.0)); // Không có double -> int widening
~~~

Cả hai đều không hợp lệ dù giá trị số học là 7. Muốn “ép hẹp” có chủ đích, ứng dụng phải quyết định rõ chính sách tràn số/độ chính xác và **chuyển đổi trước khi gọi Reflection**.

## 3. Bảng widening primitive được phép

Java cho phép **identity** (giữ nguyên primitive type) và các hướng *widening primitive conversion* sau:

| Primitive nguồn sau unbox | Primitive đích cho phép ngoài chính nó |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có kiểu primitive rộng hơn |
| `boolean` | Không chuyển đổi số; chỉ tương thích `boolean` |

Ví dụ nếu formal parameter là `double`, có thể đưa `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float` hoặc `Double` sau các chuyển đổi tương ứng. Nếu formal parameter là `char` thì `Character` mới khớp trong số các wrapper primitive này; `Byte`/`Short` không widen thành `char`.

**Widening không đồng nghĩa luôn bảo toàn chính xác giá trị số học.** Chẳng hạn `long → float` có thể mất một phần độ chính xác biểu diễn; tuy vậy phép widening vẫn được Java cho phép. Reflection tuân thủ quy tắc kiểu, không chặn một phép widening chỉ vì có nguy cơ mất precision.

### Chỉ unbox rồi widen, không “widen wrapper”

`Integer` **không** là subtype của `Long` và Reflection không tự áp chuỗi `Integer → int → long → Long` để điền formal parameter **`Long`**:

~~~java
public static void boxed(Long value) { /* ... */ }
~~~

Nếu truyền `Integer.valueOf(5)` cho formal parameter `Long`, lời gọi Reflection không phù hợp. Formal parameter là reference type `Long`, nên phép hợp lệ cơ bản là tương thích tham chiếu; **không có conversion giữa hai wrapper class khác nhau chỉ vì primitive tương ứng có widening**.

Ngược lại, nếu formal parameter là reference `Number` hoặc `Object` thì `Integer` có thể được truyền bằng **widening reference**:

~~~java
public static void accept(Number value) { /* ... */ }
~~~

`Integer` là subclass của `Number`; không cần unbox để gọi `accept(Number)`. Đây là lý do phải luôn đọc **formal parameter type** trước khi kết luận một conversion có áp dụng hay không.

## 4. `Method.invoke`: xác định formal parameter và chuyển đổi đối số

Ví dụ method đích:

~~~java
public String describe(int code, double score, boolean enabled) {
    return code + "," + score + "," + enabled;
}
~~~

Nếu nằm trong class `Target`, ta tra `Method` bằng **đúng** formal parameter types:

~~~java
Method describe = Target.class.getMethod(
        "describe", int.class, double.class, boolean.class);
~~~

`getMethod`/`getDeclaredMethod` **không tự tìm method theo wrapper type hoặc chọn overload bằng widening**. Ví dụ, `getMethod("describe", Integer.class, Double.class, Boolean.class)` không phải cách tìm method có descriptor `(int, double, boolean)`. Phải truyền các `Class` đúng với chữ ký method.

Sau khi đã lấy `Method`, đối số runtime mới được unbox/widen:

~~~java
Object value = describe.invoke(
        target,
        Character.valueOf('A'), // char -> int (giá trị mã ký tự 65)
        Integer.valueOf(7),     // int -> double (7.0)
        Boolean.TRUE            // boolean -> boolean
);
~~~

`target` phải là instance của class khai báo `describe` (hoặc subtype tương thích). `Method.invoke` trả `Object`: nếu method trả primitive, Reflection sẽ **box** kết quả thành wrapper; nếu trả `void`, kết quả là `null`; nếu trả reference, nhận chính object kết quả theo ngữ nghĩa method.

### Những gì `Method.invoke` không tự làm

- Không đổi `String` sang primitive bằng parsing.
- Không tự làm narrowing `double → int` hay `long → short`.
- Không tự gọi một overload khác khi argument hiện tại không phù hợp.
- Không tự biến `Integer[]` thành `int[]` hoặc chuyển từng phần tử array. Một tham số mảng `int[]` phải nhận chính một object mảng kiểu tương thích.
- Không tự “sửa” kiểu generic bị erasure; nếu method nhận `List<Integer>` thì runtime parameter class vẫn thường là `List.class` và việc đúng loại phần tử cần được kiểm tra riêng.

## 5. `Constructor.newInstance` dùng quy tắc chuyển đổi tương tự

Giả sử constructor:

~~~java
public Target(long count, double amount) {
    this.count = count;
    this.amount = amount;
}
~~~

Với một class `Target` thích hợp, lấy constructor theo chữ ký formal:

~~~java
Constructor<Target> ctor =
        Target.class.getConstructor(long.class, double.class);
~~~

Khi tạo object:

~~~java
Target target = ctor.newInstance(
        Byte.valueOf((byte) 5), // byte -> long
        Float.valueOf(1.25f)    // float -> double
);
~~~

Hợp lệ vì `Byte` unbox thành `byte` rồi widen đến `long`; `Float` unbox thành `float` rồi widen đến `double`. Nếu chuyển đối số đầu thành `Double.valueOf(5.0)`, formal type vẫn là `long` nên **không thể dùng narrowing `double → long`**; `newInstance` ném `IllegalArgumentException` mà không chạy body constructor tương ứng.

Cách tra constructor:

- `getConstructor(Class<?>...)` tìm **public constructor** phù hợp.
- `getDeclaredConstructor(Class<?>...)` tìm constructor khai báo trên class (kể cả private); việc tìm thấy metadata không tự cấp quyền gọi. Nếu constructor không accessible, có thể gặp `IllegalAccessException`; với named modules, khả năng `setAccessible` còn phụ thuộc export/open.
- Tham số constructor cần có số lượng chính xác; `Constructor.newInstance` không tự chọn overload dựa trên argument value.
- Constructor của non-static inner class có thể có tham số ẩn biểu diễn instance enclosing class; cần hiểu descriptor thật khi dùng Reflection.

`Constructor.newInstance` trả object mới thuộc class khai báo constructor. Nó **không** trả giá trị primitive, nên không có bước boxing của *return value* như ở `Method.invoke`.

## 6. Ví dụ chạy hoàn chỉnh (Java 17+)

Tạo file duy nhất tên **`ReflectiveConversionDemo.java`**. Chương trình quan sát đồng thời:

- Wrapper `Byte` được unbox/widen tới constructor formal `long`.
- Wrapper `Float` được unbox/widen tới constructor formal `double`.
- Wrapper `Character` được unbox/widen tới method formal `int`.
- Wrapper `Integer` được unbox/widen tới method formal `double`.
- `Long → int`, `Double → long` và `null → int` bị từ chối.
- Tham số `int[]` được đưa vào như một `Object` duy nhất.
- Method trả `int` được Reflection box thành `Integer`; exception do target tự ném được bọc bằng `InvocationTargetException`.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveConversionDemo {
    public static final class Target {
        final long count;
        final double amount;

        public Target(long count, double amount) {
            this.count = count;
            this.amount = amount;
        }

        public String describe(int code, double score, boolean enabled) {
            return count + "," + amount + "," + code + "," + score + "," + enabled;
        }

        public static int sum(int[] values) {
            int total = 0;
            for (int value : values) total += value;
            return total;
        }

        public static void fail(int value) {
            throw new IllegalStateException("inside");
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Target> ctor = Target.class.getConstructor(long.class, double.class);
        Target target = ctor.newInstance(Byte.valueOf((byte) 5), Float.valueOf(1.25f));
        Method describe = Target.class.getMethod(
                "describe", int.class, double.class, boolean.class);

        Object result = describe.invoke(
                target, Character.valueOf('A'), Integer.valueOf(7), Boolean.TRUE);
        System.out.println("invoke: " + result);

        Method sum = Target.class.getMethod("sum", int[].class);
        Object answer = sum.invoke(null, (Object) new int[] {1, 2, 3});
        System.out.println("primitive return: " + answer + " (" + answer.getClass().getSimpleName() + ")");

        try {
            describe.invoke(target, Long.valueOf(65L), Integer.valueOf(7), Boolean.TRUE);
        } catch (IllegalArgumentException e) {
            System.out.println("Long to int: " + e.getClass().getSimpleName());
        }

        try {
            describe.invoke(target, null, Integer.valueOf(7), Boolean.TRUE);
        } catch (IllegalArgumentException e) {
            System.out.println("null to int: " + e.getClass().getSimpleName());
        }

        try {
            ctor.newInstance(Double.valueOf(5.0), Float.valueOf(1.25f));
        } catch (IllegalArgumentException e) {
            System.out.println("Double to long: " + e.getClass().getSimpleName());
        }

        try {
            Target.class.getMethod("fail", int.class).invoke(null, Integer.valueOf(9));
        } catch (InvocationTargetException e) {
            System.out.println("target threw: " + e.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Lệnh biên dịch/chạy (JDK 17 trở lên):

~~~bash
javac --release 17 -Xlint:all ReflectiveConversionDemo.java
java ReflectiveConversionDemo
~~~

**Stdout chính xác** (đã biên dịch với `--release 17 -Xlint:all` và chạy thành công):

~~~text
invoke: 5,1.25,65,7.0,true
primitive return: 6 (Integer)
Long to int: IllegalArgumentException
null to int: IllegalArgumentException
Double to long: IllegalArgumentException
target threw: IllegalStateException
~~~

Giải thích theo thứ tự:

1. `Byte(5)` đi vào constructor `long` và `Float(1.25)` vào `double`: hai chuỗi unbox + widen hợp lệ, object `Target` được khởi tạo.
2. `Character('A')` được unbox thành `char` và widen tới `int` cho giá trị mã ký tự `65`; `Integer(7)` thành `double 7.0`; `Boolean.TRUE` hợp kiểu `boolean`.
3. Phương thức `sum` nhận **một `int[]`**; kết quả kiểu primitive `int` có giá trị `6` được Reflection trả về qua `Object` dưới dạng `Integer`.
4. `Long → int`, `null → int` và `Double → long` không thỏa conversion nên bị từ chối bằng `IllegalArgumentException`.
5. `fail` nhận đối số `Integer(9)` hợp lệ, chạy body và ném `IllegalStateException`. Chính **`Method.invoke` bọc exception target** trong `InvocationTargetException`; chương trình in tên kiểu của `getCause()`.

Đừng suy từ các dòng `IllegalArgumentException` rằng method body đích đã chạy: chúng là lỗi **argument matching/conversion**. Trong khi đó, dòng `target threw` chứng minh body đã chạy và phát sinh ngoại lệ.

## 7. Thiết kế lớp chuyển đổi dữ liệu trước khi gọi Reflection

Trong các framework hoặc chương trình nạp phương thức theo cấu hình, dữ liệu nhập thường ở dạng `String`, JSON value hay kiểu số tổng quát. Nếu cần chuyển `"42"` sang `int`, hoặc `Long(42)` sang `int`, hãy thực hiện ở **lớp adaptation/validation riêng**, rồi mới gọi Reflection:

1. Lấy formal types qua `method.getParameterTypes()` hoặc `constructor.getParameterTypes()`.
2. Kiểm tra số lượng argument và xử lý varargs theo descriptor thật; chuyển dữ liệu có chính sách rõ ràng.
3. Với narrowing, kiểm tra phạm vi, phép làm tròn và mất precision trước khi tạo wrapper đích; ví dụ `Math.toIntExact(long)` có thể từ chối giá trị vượt miền `int`.
4. Đưa object/wrapper hay array tương thích vào `invoke` / `newInstance`; xử lý `IllegalArgumentException` cho mismatch, `InvocationTargetException` cho lỗi phát sinh từ target.
5. Đảm bảo truy cập đúng constructor/method và tuân thủ module access, không tự mở private internals ngoài nhu cầu.

Ví dụ **đoạn chuyển đổi ứng dụng**, không thuộc tự động Reflection:

~~~java
long input = 42L;
int checked = Math.toIntExact(input); // Rõ ràng chấp nhận giá trị vừa miền int.
method.invoke(receiver, Integer.valueOf(checked)); // Dành cho method nhận int.
~~~

Với numeric domain cần độ chính xác cao hoặc dữ liệu tài chính, quy tắc kiểu `double` và float widening chưa đủ để đảm bảo số học mong muốn; cần chọn mô hình dữ liệu/validation phù hợp (chẳng hạn `BigDecimal` khi có yêu cầu chính xác thập phân).

## Tài liệu tham khảo

- [Java SE 21 — `java.lang.reflect.Method.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)).
- [Java SE 21 — `java.lang.reflect.Constructor.newInstance`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
- [Java Language Specification §5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2), [§5.1.8 — Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [§5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3).