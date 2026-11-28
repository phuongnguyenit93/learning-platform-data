# asType(): tạo adapter tường minh, chuyển đổi reference, boxing, unboxing và primitive widening

> **Chương:** MethodHandle  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Hiểu cách `MethodHandle.asType(MethodType)` tạo adapter có kiểu gọi mới, chuyển đổi từng đối số và giá trị trả về theo hợp đồng JDK; thực hành reference cast, boxing, unboxing, primitive widening và xử lý `void`; phân biệt lỗi khi tạo adapter với lỗi lúc gọi.
>
> **Phạm vi hiện đại:** `MethodHandle` và `asType` có từ Java 7, không phải tính năng mới của Java 18. JEP 416 (Java 18) tái triển khai core reflection trên nền method handles; bài này học **API công khai vẫn dùng trên JDK hiện đại**, không sử dụng kỹ thuật nội bộ/legacy.

## 1. Tình huống: một MethodHandle có kiểu khác với kiểu API của caller

Giả sử hệ thống có một method Java:

~~~java
static long twice(long value) {
    return value * 2;
}
~~~

Một `MethodHandle` tìm thấy method trên sẽ có kiểu:

~~~text
(long)long
~~~

Nhưng mã gọi của ứng dụng chỉ có `int`, hoặc một framework truyền giá trị đóng hộp `Integer` và muốn nhận về `Object`.

Ta cần phân biệt ba giải pháp:

1. **Sửa giá trị trước khi gọi:** code bên ngoài tự chuyển đổi.
2. **Gọi `invoke`:** JVM có thể thích nghi kiểu call site theo các quy tắc `asType`.
3. **Tạo adapter với `asType(newType)`:** chủ động công bố một `MethodHandle` mới có kiểu thích hợp, rồi có thể gọi nó bằng `invokeExact`.

Ví dụ ý tưởng:

~~~text
Target handle:     (long)long
       |
       | asType((int)long)
       v
Adapter handle:    (int)long
       |
       | caller truyền int = 21
       v
Adapter đổi int -> long, gọi target, trả long = 42
~~~

`asType` không thay đổi method Java gốc. Nó tạo **một handle thích nghi** để caller nhìn thấy kiểu khác, nhưng các conversion vẫn có giới hạn.

## 2. Nắm vững MethodType trước khi học asType

`java.lang.invoke.MethodType` mô tả chính xác kiểu của một method handle: loại trả về và danh sách loại tham số theo thứ tự.

~~~java
import java.lang.invoke.MethodType;

MethodType original = MethodType.methodType(long.class, long.class);
MethodType desired = MethodType.methodType(long.class, int.class);

System.out.println(original); // (long)long
System.out.println(desired);  // (int)long
~~~

Cú pháp `methodType(returnType, parameterTypes...)` luôn đặt **kiểu trả về đầu tiên** trong lời gọi factory, mặc dù `toString()` hiển thị theo dạng `(parameters)return`.

Ví dụ:

| Lời gọi | Chuỗi dạng MethodType | Nghĩa |
|---|---|---|
| `methodType(int.class, int.class)` | `(int)int` | Nhận `int`, trả `int` |
| `methodType(long.class, int.class)` | `(int)long` | Nhận `int`, trả `long` |
| `methodType(Object.class, Integer.class)` | `(Integer)Object` | Nhận `Integer`, trả `Object` |
| `methodType(void.class, String.class)` | `(String)void` | Nhận `String`, không trả giá trị |
| `methodType(String.class)` | `()String` | Không có tham số, trả `String` |

`MethodType` là immutable. `MethodHandle.type()` trả về kiểu hiện tại của handle. Cần quan sát cả kiểu **trước** và **sau** adapter, không chỉ nhìn tên method đích.

### 2.1. MethodHandle là tham chiếu có kiểu, không phải Method reflection

`MethodHandle` là đối tượng gọi được với kiểu đã xác định. Nó khác `java.lang.reflect.Method`:

- `Method.invoke` nhận receiver và danh sách `Object...`; argument/return là các giá trị được xử lý theo cơ chế reflection.
- `MethodHandle.invokeExact` liên kết theo **kiểu call site chính xác**.
- `MethodHandle.invoke` chấp nhận một số sai khác kiểu bằng chuyển đổi theo `asType`.
- `MethodHandle.asType` cho phép tạo adapter tường minh và quan sát `adapter.type()`.

`asType` là API được định nghĩa từ Java 7; đừng nhầm nó với công việc tái triển khai reflection thuộc JEP 416 của Java 18.

## 3. Hợp đồng của asType(newType)

Phương thức:

~~~java
public final MethodHandle asType(MethodType newType)
~~~

Khi thành công, nó trả về một `MethodHandle` có:

~~~java
adapter.type().equals(newType) // true
~~~

Khi `newType.equals(original.type())`, tài liệu API quy định trả lại chính `original` thay vì tạo adapter mới.

Với handle có **fixed arity**, số tham số của hai kiểu cần giống nhau. Adapter thực hiện quy trình logic:

1. Nhận danh sách đối số có kiểu `newType.parameterType(i)`.
2. Chuyển đổi từng đối số sang kiểu `original.type().parameterType(i)`.
3. Gọi handle gốc bằng các đối số đã chuyển.
4. Chuyển đổi giá trị trả về từ `original.type().returnType()` sang `newType.returnType()`.
5. Trả kết quả cho caller.

Đây là chuỗi chuyển đổi *pairwise*: một tham số mới tương ứng một tham số cũ, không tự đổi thứ tự, thêm tham số hay gom mảng đối số. Trường hợp variable-arity collector có quy tắc đặc biệt, được nói riêng ở phần sau.

### 3.1. Hướng chuyển đổi rất quan trọng

| Vị trí | Hướng chuyển đổi |
|---|---|
| Đối số truyền vào | `newType parameter` → `original parameter` |
| Kết quả trả về | `original return` → `newType return` |

Vì vậy, một handle gốc nhận `long` hoàn toàn có thể được thích nghi để **nhận `int`**: caller cung cấp `int`, adapter widening `int -> long` rồi gọi target.

Nhưng handle gốc nhận `int` thường **không** thể được thích nghi để nhận `long` bằng `asType`: muốn đưa `long` vào target `int` phải narrowing `long -> int`, không phải primitive widening.

## 4. Bảng quy tắc chuyển đổi của asType

Các phép chuyển đổi chính theo Javadoc `MethodHandle.asType`:

| Từ | Sang | Quy tắc | Ví dụ |
|---|---|---|---|
| Cùng kiểu | Cùng kiểu | Không đổi | `int -> int` |
| Reference | Reference | Reference cast; có thể kiểm tra tại runtime | `Object -> String`, `String -> Object` |
| Primitive | Primitive | Widening primitive theo Java method invocation | `byte -> int`, `int -> long`, `float -> double` |
| Primitive | Reference | Boxing rồi có thể widening reference | `int -> Integer`, `int -> Number`, `long -> Object` |
| Reference | Primitive | Unboxing rồi có thể widening primitive | `Integer -> int`, `Integer -> long`, `Object chứa Integer -> long` |
| Giá trị trả về bất kỳ | `void` | Bỏ giá trị trả về | `int -> void` |
| Trả về `void` | Reference | Đưa vào `null` | `void -> String` |
| Trả về `void` | Primitive | Đưa vào giá trị zero tương ứng | `void -> int` cho `0`, `void -> boolean` cho `false` |

Cần đọc bảng theo **hướng dữ liệu thực tế**. Với argument, hướng là tham số adapter sang tham số target. Với return, hướng là kết quả target sang kết quả adapter.

`boolean` không widening thành các numeric primitive hoặc ngược lại. Các conversion như `long -> int`, `double -> float` và `int -> short` là **primitive narrowing**, không được `asType` dùng như primitive-to-primitive conversion thông thường.

### 4.1. Không phải mọi reference conversion đều được xác minh ngay

Hai reference types có thể được kết nối qua cast ngay cả khi không có quan hệ subtype trực tiếp. Vì giá trị runtime có thể là `null` hoặc object phù hợp trong một số trường hợp, adapter có thể được tạo rồi đến lúc gọi mới phát hiện không cast được.

Ví dụ adapter nhận `Object` và target cần `String` có thể được tạo thành công. Truyền `"Java"` thì hợp lệ; truyền `Integer.valueOf(7)` thì phát sinh `ClassCastException` khi invoke.

### 4.2. Reference-to-primitive phải có khả năng unbox

Không phải mọi reference type đều có thể chuyển sang primitive trong `asType`.

- `Integer -> int`: có.
- `Integer -> long`: unbox `int` rồi widening lên `long`.
- `Object -> int`: adapter có thể tạo; object runtime phải chứa wrapper phù hợp.
- `String -> int`: không có phép unbox hợp lệ; `asType` không parse nội dung `"123"` thành số.

Khi một conversion bắt buộc không thể thiết lập, `asType` ném `WrongMethodTypeException`.

## 5. Ví dụ primitive widening: int sang long

Tạo file `PrimitiveWidening.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class PrimitiveWidening {
    public static long twice(long x) {
        return x * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                PrimitiveWidening.class,
                "twice",
                MethodType.methodType(long.class, long.class));

        MethodHandle adapter = target.asType(
                MethodType.methodType(long.class, int.class));

        System.out.println("target=" + target.type());
        System.out.println("adapter=" + adapter.type());

        long result = (long) adapter.invokeExact(21);
        System.out.println("result=" + result);
    }
}
~~~

Kết quả:

~~~text
target=(long)long
adapter=(int)long
result=42
~~~

Tại `invokeExact(21)`, literal `21` là `int` và cast `(long)` xác định kiểu trả về mong đợi tại call site là `long`. Vì `adapter.type()` là `(int)long`, chữ ký khớp hoàn toàn.

Target vẫn là `(long)long`. Adapter chuyển `int` sang `long`, gọi `twice` rồi trả `long`. Không có primitive narrowing.

### 5.1. Widening là một chiều, không tự đảo ngược

Giả sử target:

~~~java
static int triple(int x) {
    return x * 3;
}
~~~

Nếu `target.type()` là `(int)int`, yêu cầu:

~~~java
MethodType wrong = MethodType.methodType(int.class, long.class);
target.asType(wrong); // WrongMethodTypeException
~~~

Lý do: đối số mới là `long`, nhưng target đòi `int`. Bộ chuyển đổi phải làm `long -> int`, tức narrowing, nên yêu cầu không hợp lệ.

Ngược lại, kiểu mới `(byte)long` cũng cần xét **hai chiều**: đầu vào `long -> int` không được, còn kết quả `int -> byte` cũng không được. Không thể chỉ nhìn thấy một conversion hợp lệ rồi kết luận cả method type được chấp nhận.

## 6. Kiểm thử primitive widening với nhiều kiểu

Một số widening primitive tiêu biểu của Java:

| Nguồn | Có thể widening sang |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có primitive rộng hơn |
| `boolean` | Không có widening sang numeric |

Widening không có nghĩa mọi giá trị giữ được độ chính xác toán học tuyệt đối. Ví dụ `long -> float` là widening conversion theo JLS nhưng có thể mất precision vì `float` không biểu diễn chính xác mọi giá trị `long`.

### 6.1. Ví dụ từ int sang double

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class WidenToDouble {
    public static double square(double value) {
        return value * value;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                WidenToDouble.class,
                "square",
                MethodType.methodType(double.class, double.class));

        MethodHandle adapter = target.asType(
                MethodType.methodType(double.class, int.class));

        double result = (double) adapter.invokeExact(3);
        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
9.0
~~~

Ở đây argument `int -> double` là widening hợp lệ. Kết quả trả về của target vẫn là `double`.

## 7. Reference conversion: upcast và downcast kiểm tra lúc gọi

Target gốc:

~~~java
static String uppercase(String text) {
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

Target type là `(String)String`. Ta có thể tạo adapter tổng quát `(Object)Object`:

~~~java
MethodHandle general = target.asType(
        MethodType.methodType(Object.class, Object.class));
~~~

Hướng argument: `Object -> String` nên adapter thực hiện cast sang `String` khi gọi. Hướng return: `String -> Object`, là widening reference.

### 7.1. Đúng object runtime

~~~java
Object input = "java";
Object result = (Object) general.invokeExact(input);
System.out.println(result); // JAVA
~~~

Ở đây `input` được khai báo kiểu `Object`, phù hợp với tham số của `general`. Giá trị runtime thực tế là `String` nên cast thành công.

### 7.2. Sai object runtime

~~~java
Object input = Integer.valueOf(123);
Object result = (Object) general.invokeExact(input);
// ClassCastException khi adapter cố cast Integer sang String.
~~~

Việc tạo `general` có thể thành công; lỗi chỉ phát sinh khi truyền giá trị không tương thích. `asType` không có khả năng biết trước mọi giá trị runtime sẽ được truyền vào.

### 7.3. Trả về kiểu reference hẹp hơn

Một target trả `Object` có thể được thích nghi thành adapter trả `String`. Nhưng nếu target thực tế trả `Integer`, việc cast kết quả `Object -> String` sẽ thất bại sau khi target đã chạy.

Chú ý: reference cast khác logic parse hoặc format. `asType` không thể chuyển một `Integer` thành chuỗi `"123"` bằng cách gọi `toString()`; muốn chuyển đổi nội dung cần adapter riêng như `filterReturnValue`.

## 8. Boxing: primitive trở thành wrapper/reference

**Boxing** biến primitive thành object wrapper tương ứng:

- `int -> Integer`.
- `long -> Long`.
- `boolean -> Boolean`.
- Sau boxing, object có thể được widening reference, ví dụ `Integer -> Number` hoặc `Long -> Object`.

Tưởng tượng target có kiểu `(long)long`. Ta tạo adapter:

~~~java
MethodHandle boxed = target.asType(
        MethodType.methodType(Object.class, Integer.class));
~~~

Kiểu mới là `(Integer)Object`. Khi caller truyền một `Integer`:

1. `Integer` được unbox thành `int`.
2. `int` widening sang `long` để phù hợp target.
3. Target trả `long`.
4. `long` boxing thành `Long` rồi widening reference sang `Object`.

### 8.1. Ví dụ hoàn chỉnh

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BoxingAdapter {
    public static long doubleIt(long n) {
        return n * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                BoxingAdapter.class,
                "doubleIt",
                MethodType.methodType(long.class, long.class));

        MethodHandle adapter = target.asType(
                MethodType.methodType(Object.class, Integer.class));

        Object result = (Object) adapter.invokeExact(Integer.valueOf(9));

        System.out.println(adapter.type());
        System.out.println(result.getClass().getSimpleName());
        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
(Integer)Object
Long
18
~~~

**Điểm dễ nhầm:** Input wrapper là `Integer`, nhưng output wrapper là `Long` vì **kiểu primitive trả về của target là `long`**. `asType` không làm round-trip wrapper giữ nguyên loại khi hai phía có kiểu primitive khác nhau.

## 9. Unboxing: reference sang primitive

Unboxing đưa một wrapper thành primitive:

~~~text
Integer(7) -> int 7
Long(7)    -> long 7
Boolean.TRUE -> boolean true
~~~

Sau unboxing, `asType` có thể tiếp tục widening primitive. Một adapter có kiểu `(Object)int` có thể nhận object runtime là `Integer` để gọi target nhận `int`.

Ví dụ:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class UnboxingAdapter {
    public static int addOne(int value) {
        return value + 1;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle target = MethodHandles.lookup().findStatic(
                UnboxingAdapter.class,
                "addOne",
                MethodType.methodType(int.class, int.class));

        MethodHandle adapter = target.asType(
                MethodType.methodType(Integer.class, Object.class));

        Object boxed = Integer.valueOf(7);
        Integer result = (Integer) adapter.invokeExact(boxed);

        System.out.println(adapter.type());
        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
(Object)Integer
8
~~~

Hướng input: `Object` runtime chứa `Integer` → unbox `int` → target. Hướng output: target trả `int` → box `Integer`.

### 9.1. Null unboxing gây NullPointerException

~~~java
Object missing = null;
Integer result = (Integer) adapter.invokeExact(missing);
// NullPointerException khi cố unbox null.
~~~

Adapter `(Object)Integer` đã được tạo hợp lệ. Đây là lỗi **giá trị runtime**, không phải `WrongMethodTypeException` lúc tạo adapter.

### 9.2. Wrapper không phù hợp gây ClassCastException

~~~java
Object wrong = "7";
Integer result = (Integer) adapter.invokeExact(wrong);
// ClassCastException: String không phải wrapper có thể unbox thành int.
~~~

Đừng nhầm unboxing với parse số. Nếu muốn nhận chuỗi `"7"` và biến thành `int`, phải dùng logic như `Integer.parseInt` hoặc một `MethodHandle` filter phù hợp.

## 10. Unboxing rồi widening: nhìn cả kiểu tĩnh và kiểu runtime

Ví dụ target nhận `long`. Một adapter nhận `Number` có thể được tạo vì `Number` là supertype của các numeric wrappers; runtime có thể chứa wrapper unbox được rồi widening sang `long`.

| Giá trị runtime bên trong Number | Đưa vào target `long`? | Lý do |
|---|---|---|
| `Byte.valueOf((byte) 2)` | Có | unbox `byte`, widen `long` |
| `Short.valueOf((short) 2)` | Có | unbox `short`, widen `long` |
| `Integer.valueOf(2)` | Có | unbox `int`, widen `long` |
| `Long.valueOf(2L)` | Có | unbox `long` |
| `Float.valueOf(2F)` | Không | unbox `float` rồi cần narrowing `float -> long` |
| `Double.valueOf(2D)` | Không | unbox `double` rồi cần narrowing `double -> long` |

Ví dụ:

~~~java
MethodHandle longTarget = /* MethodHandle có type (long)long */;
MethodHandle numberAdapter = longTarget.asType(
        MethodType.methodType(long.class, Number.class));

Number valid = Integer.valueOf(5);
long first = (long) numberAdapter.invokeExact(valid); // Thành công.

Number invalid = Double.valueOf(5.5);
long second = (long) numberAdapter.invokeExact(invalid);
// ClassCastException tại runtime.
~~~

Đây là **đoạn trích minh họa**, chưa phải class tự chạy vì `longTarget` được giả định có sẵn. Trường hợp `Number` cho thấy tạo adapter thành công **không** có nghĩa mọi subtype của `Number` đều hợp lệ khi unbox.

Cũng không có cơ chế tự gọi `Number.longValue()` cho bất kỳ subtype tùy ý chỉ vì object kế thừa `Number`. Quy tắc là unboxing wrapper và widening primitive, không phải conversion nghiệp vụ tùy biến.

## 11. Chuyển đổi giá trị trả về: đi ngược hướng tham số

Nhắc lại:

~~~text
Incoming argument:    adapter type -> target type
Outgoing return:      target type  -> adapter type
~~~

Ví dụ một method gốc nhận và trả `int`:

~~~java
static int plusOne(int value) {
    return value + 1;
}
~~~

Ta có thể tạo adapter có type `(byte)long`:

~~~java
MethodHandle widened = target.asType(
        MethodType.methodType(long.class, byte.class));
~~~

Vì:

- Tham số adapter `byte` → target `int`: widening hợp lệ.
- Kết quả target `int` → adapter `long`: widening hợp lệ.

Khi gọi:

~~~java
byte input = 5;
long result = (long) widened.invokeExact(input);
System.out.println(result); // 6
~~~

**Lưu ý**: Việc adapter có return type `long` không có nghĩa target method thực sự trả `long`. Giá trị `int` được widen sau khi target trả về.

### 11.1. Một chiều không hợp lệ

Nếu target trả `long` và adapter yêu cầu trả `int`:

~~~java
MethodHandle longTarget = /* MethodHandle có type (long)long */;
longTarget.asType(MethodType.methodType(int.class, long.class));
// WrongMethodTypeException: cần long -> int ở return.
~~~

Kết quả `long` không được tự động cắt bớt thành `int` bởi `asType`.

### 11.2. Reference narrowing ở return

Target trả `Object`, adapter trả `String`:

~~~java
MethodHandle adapted = objectTarget.asType(
        MethodType.methodType(String.class, Object.class));
~~~

Nếu object thực tế mà target trả là `String` thì thành công. Nếu trả `Integer`, adapter ném `ClassCastException` khi chuyển return `Object -> String`.

## 12. Quy tắc riêng cho void return

`void` không biểu diễn giá trị nên conversion cho return có quy tắc đặc biệt:

| Target return | Adapter return | Hành vi |
|---|---|---|
| `int` | `void` | Bỏ giá trị `int` |
| `String` | `void` | Bỏ giá trị tham chiếu |
| `void` | `String` | Trả `null` |
| `void` | `Object` | Trả `null` |
| `void` | `int` | Trả `0` |
| `void` | `boolean` | Trả `false` |
| `void` | `double` | Trả `0.0` |

Ví dụ target không trả gì:

~~~java
public static void announce(String message) {
    System.out.println("announcement=" + message);
}
~~~

Tạo adapter có return `int`:

~~~java
MethodHandle target = MethodHandles.lookup().findStatic(
        Example.class,
        "announce",
        MethodType.methodType(void.class, String.class));

MethodHandle adapter = target.asType(
        MethodType.methodType(int.class, String.class));

int result = (int) adapter.invokeExact("ok");
System.out.println("returned=" + result);
~~~

Đoạn này giả định `Example` là class chứa method `announce(String)` và phần code ở method có quyền lookup thích hợp. Kết quả:

~~~text
announcement=ok
returned=0
~~~

**Không suy diễn** rằng target tự trả `0`. Adapter tạo default result để phù hợp return type được yêu cầu.

### 12.1. Khi muốn bỏ return

Một target có return `int` có thể thích nghi thành `void`:

~~~java
MethodHandle discard = intTarget.asType(
        MethodType.methodType(void.class, int.class));

discard.invokeExact(3); // Lời gọi statement có call-site return void.
~~~

Vì `invokeExact` là signature-polymorphic, câu lệnh standalone này có kiểu trả về `void`, khớp với adapter.

Không truyền `void.class` làm **parameter type** trong `MethodType`: `void` chỉ hợp lệ ở vị trí return.

## 13. Ba nhóm lỗi phải phân biệt

### 13.1. WrongMethodTypeException khi tạo adapter

Thường xảy ra khi cặp kiểu không có conversion hợp lệ hoặc số tham số của fixed-arity handle không khớp.

~~~java
MethodHandle target = /* Có type (int)int */;
target.asType(MethodType.methodType(int.class, long.class));
// Không có primitive widening long -> int: WrongMethodTypeException.
~~~

Ví dụ khác:

~~~java
target.asType(MethodType.methodType(int.class, int.class, int.class));
// Thêm một tham số so với target fixed-arity: WrongMethodTypeException.
~~~

`asType(null)` thì ném `NullPointerException` do `newType` là null, không phải mismatch về `MethodType`.

### 13.2. ClassCastException khi invoke

Adapter được tạo hợp lệ nhưng reference runtime không cast hoặc unbox thành kiểu target.

~~~java
MethodHandle adapter = stringTarget.asType(
        MethodType.methodType(Object.class, Object.class));

Object wrong = Integer.valueOf(7);
Object result = (Object) adapter.invokeExact(wrong);
// ClassCastException nếu stringTarget đòi String argument.
~~~

### 13.3. NullPointerException khi invoke

Adapter nhận wrapper hoặc reference, target cần primitive:

~~~java
Object missing = null;
int result = (int) unboxingAdapter.invokeExact(missing);
// NullPointerException khi unbox.
~~~

Một target method cũng có thể tự ném `NullPointerException` trong body. Khi chẩn đoán cần đọc stack trace để phân biệt lỗi do adapter unbox và lỗi nghiệp vụ của target.

### 13.4. WrongMethodTypeException ở invokeExact

Ngay cả khi adapter được tạo hợp lệ, `invokeExact` vẫn yêu cầu **call-site type khớp tuyệt đối** với `adapter.type()`.

Giả sử adapter có type `(int)long`:

~~~java
// Đúng:
long ok = (long) adapter.invokeExact(21);

// Sai: Java cast của kết quả khiến call-site return int:
int wrong = (int) adapter.invokeExact(21);
// WrongMethodTypeException — không phải narrowing tự động.
~~~

`invokeExact` không tự chèn `asType`. Muốn return `int` từ target `long`, phải có phép conversion hợp lệ riêng; `asType` không narrowing primitive.

### 13.5. Exception bên trong target

Nếu target method ném exception, method-handle invocation truyền exception đó theo hợp đồng. Không nhầm mọi exception khi invoke với conversion failure.

Khác với `Method.invoke` thường bọc exception do method đích ném trong `InvocationTargetException`, `MethodHandle.invokeExact`/`invoke` có thể truyền `Throwable` từ target trực tiếp. Khi viết code gọi handle cần có chiến lược xử lý exception rõ ràng.

## 14. So sánh asType, invoke và invokeExact

| API | Quy tắc chính | Khi dùng |
|---|---|---|
| `handle.asType(newType)` | Tạo adapter tường minh theo conversion được phép | Muốn công bố type mới ổn định |
| `handle.invokeExact(...)` | Call-site type phải đúng tuyệt đối | Type đã biết rõ, tối ưu đường gọi dễ dự đoán |
| `handle.invoke(...)` | JVM thích nghi kiểu như `asType` khi cần | Caller có call-site type khác nhưng hợp lệ |
| `handle.invokeWithArguments(...)` | Gọi generic từ danh sách `Object`/`List` | Bridge với dữ liệu biến động, đánh đổi kiểm tra runtime |

### 14.1. Ví dụ inexact invoke

Target có type `(long)long`:

~~~java
MethodHandle target = /* (long)long */;

long a = (long) target.invoke(5);
// Call-site là (int)long: có thể chuyển int -> long.

long b = (long) target.invokeExact(5);
// WrongMethodTypeException: target đòi long argument.
~~~

`invoke` hoạt động *như thể* JVM tạo adapter `asType` tạm thời. Implementation không bắt buộc tạo object adapter quan sát được. Vì vậy, không kết luận mỗi `invoke` luôn cấp phát một adapter mới.

### 14.2. Lợi ích của adapter explicit

Thay vì rải implicit conversion ở nhiều call site:

~~~java
long result = (long) target.invoke(5);
~~~

Ta có thể làm rõ hợp đồng một lần:

~~~java
MethodHandle intToLong = target.asType(
        MethodType.methodType(long.class, int.class));

long result = (long) intToLong.invokeExact(5);
~~~

Cách này phù hợp khi boundary giữa hai module/framework cần một chữ ký ổn định và có thể unit test conversion trước khi dùng rộng rãi.

### 14.3. Đừng quên return type của call site

Với `invokeExact`, cast ở expression xác định return type. Ví dụ một target có type `(int)int`:

~~~java
int answer = (int) target.invokeExact(7);
~~~

Nếu viết:

~~~java
Object answer = target.invokeExact(7);
~~~

call-site return là `Object`, không khớp `int` và có thể ném `WrongMethodTypeException`. Muốn boxing thành `Object` một cách rõ ràng, dùng adapter:

~~~java
MethodHandle boxedReturn = target.asType(
        MethodType.methodType(Object.class, int.class));

Object answer = (Object) boxedReturn.invokeExact(7);
~~~

## 15. asType không thay đổi số tham số hay thứ tự

Với fixed-arity handle có type `(int, int)int`, yêu cầu `asType((int)int)` không hợp lệ vì số tham số khác nhau.

`asType` cũng không có khả năng:

- Đổi thứ tự tham số.
- Cố định một tham số rồi bỏ khỏi chữ ký.
- Chèn giá trị mặc định vào danh sách đối số.
- Biến `Object[]` thành nhiều argument theo ý muốn nếu target không phải variable-arity collector.
- Tự parse `String` thành số, chuẩn hóa JSON hoặc ánh xạ một domain object sang object khác.

Những thao tác đó thuộc các adapter/combinator khác:

| Nhu cầu | API phù hợp |
|---|---|
| Gắn cố định tham số | `MethodHandles.insertArguments` hoặc `MethodHandle.bindTo` |
| Bỏ qua thêm tham số từ caller | `MethodHandles.dropArguments` |
| Đổi vị trí argument | `MethodHandles.permuteArguments` |
| Biến array thành các argument | `MethodHandle.asSpreader` |
| Gom các argument thành array | `MethodHandle.asCollector` |
| Biến đổi nội dung một argument | `MethodHandles.filterArguments` |
| Biến đổi kết quả | `MethodHandles.filterReturnValue` |
| Primitive narrowing/cast explicit khác với `asType` | `MethodHandles.explicitCastArguments` |

### 15.1. Ngoại lệ: variable-arity collector

Handle variable-arity có trailing array parameter và được đánh dấu có thể thu gom đối số. Với loại handle này, `asType` có thể phối hợp với cơ chế collector để thích nghi số đối số hoặc kiểu trailing argument theo quy tắc đặc biệt trong Javadoc.

Không từ đó suy ra **mọi** method handle cho phép thay arity. Với fixed-arity handle, số đối số vẫn phải bằng nhau. Khi cần behavior cố định, có thể dùng `asFixedArity()` trước khi xây dựng adapter, nếu phù hợp với API của bạn.

## 16. asType và explicitCastArguments khác nhau thế nào?

`MethodHandles.explicitCastArguments(target, newType)` cung cấp một bộ quy tắc conversion mô phỏng các phép cast tường minh mạnh hơn so với `asType`, trong đó có thể có primitive narrowing.

Ví dụ target trả `long`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle target = /* handle có type (long)long */;

MethodType desired = MethodType.methodType(int.class, long.class);

// Không được: cần long -> int ở return.
target.asType(desired); // WrongMethodTypeException.

// Adapter dùng explicit cast semantics; có thể narrowing long -> int.
MethodHandle narrowing =
        MethodHandles.explicitCastArguments(target, desired);
~~~

Trong ví dụ trên, `desired` giữ đối số `long`; chỉ kết quả cần ép `long -> int`. Đoạn code này là trích đoạn và cần khai báo target phù hợp trong class khi thử.

**Không thay tự động tất cả `asType` bằng `explicitCastArguments`.** Narrowing có thể làm mất dữ liệu hoặc thay đổi ngữ nghĩa. Chỉ dùng khi bạn thật sự muốn Java explicit cast semantics và đã kiểm tra phạm vi số liệu cần chấp nhận.

Với conversion nội dung như `String "42" -> int 42`, ngay cả explicit primitive cast cũng không phải parser. Hãy dùng `Integer.parseInt` hoặc filter thích hợp và xác định chính sách lỗi parsing.

## 17. Instance method, receiver và access control

Tới đây ví dụ chủ yếu dùng static methods. Với instance method, receiver xuất hiện như tham số đầu tiên của method handle nhận được qua `findVirtual`.

Ví dụ:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandle length = MethodHandles.publicLookup().findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class));
~~~

`length.type()` là:

~~~text
(String)int
~~~

Receiver `String` là tham số đầu tiên; khác cách gọi reflection `Method.invoke(receiver)`, method handle đã đưa receiver vào method type.

Tạo adapter tổng quát:

~~~java
MethodHandle generic = length.asType(
        MethodType.methodType(Integer.class, Object.class));

Object input = "abc";
Integer size = (Integer) generic.invokeExact(input);

System.out.println(size); // 3
~~~

Hướng chuyển đổi:

- Receiver `Object -> String`: cast lúc gọi.
- Result `int -> Integer`: boxing.

Nếu `input` là một `Integer` thay vì `String`, adapter ném `ClassCastException`. Nếu `input` là `null`, reference cast `null` sang `String` được phép nhưng lời gọi instance method trên null có thể ném `NullPointerException`.

### 17.1. asType không cấp thêm quyền truy cập

Quyền lấy handle qua `MethodHandles.Lookup.findStatic`, `findVirtual`, `findConstructor` hay `unreflect` được kiểm tra theo API lookup, visibility và JPMS.

Sau khi đã có handle hợp lệ, `asType` chỉ thích nghi chữ ký. Nó không biến private method của module khác thành public hoặc vượt `opens`/`exports`. Không dùng `asType` như công cụ bypass access control.

## 18. Một chương trình tổng hợp có thể chạy

File `AsTypeWorkshop.java` dưới đây dùng các method nhỏ để minh họa widening, reference cast, boxing/unboxing, `void` và ba loại lỗi phổ biến. Không cần thư viện ngoài JDK.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.Locale;

public class AsTypeWorkshop {

    private static long twice(long value) {
        return value * 2;
    }

    private static int plusOne(int value) {
        return value + 1;
    }

    private static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    private static void announce(String message) {
        System.out.println("announce=" + message);
    }

    private static MethodHandle find(String name, MethodType type)
            throws ReflectiveOperationException {
        return MethodHandles.lookup().findStatic(
                AsTypeWorkshop.class, name, type);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle twice = find(
                "twice", MethodType.methodType(long.class, long.class));

        // 1. Widening argument int -> long.
        MethodHandle widening = twice.asType(
                MethodType.methodType(long.class, int.class));
        long a = (long) widening.invokeExact(21);
        System.out.println("widen=" + a);

        // 2. Unbox Integer -> int -> long; box long -> Long -> Object.
        MethodHandle boxed = twice.asType(
                MethodType.methodType(Object.class, Integer.class));
        Object b = (Object) boxed.invokeExact(Integer.valueOf(9));
        System.out.println("box=" + b.getClass().getSimpleName() + ":" + b);

        // 3. Object -> String cast; String -> Object reference widening.
        MethodHandle upper = find(
                "upper", MethodType.methodType(String.class, String.class));
        MethodHandle generic = upper.asType(
                MethodType.methodType(Object.class, Object.class));

        Object input = "java";
        Object c = (Object) generic.invokeExact(input);
        System.out.println("reference=" + c);

        try {
            Object invalid = Integer.valueOf(7);
            Object ignored = (Object) generic.invokeExact(invalid);
            System.out.println(ignored);
        } catch (ClassCastException expected) {
            System.out.println("referenceError=ClassCastException");
        }

        // 4. Object -> int unboxing; int -> Integer boxing.
        MethodHandle plusOne = find(
                "plusOne", MethodType.methodType(int.class, int.class));
        MethodHandle unbox = plusOne.asType(
                MethodType.methodType(Integer.class, Object.class));

        Object seven = Integer.valueOf(7);
        Integer d = (Integer) unbox.invokeExact(seven);
        System.out.println("unbox=" + d);

        try {
            Object missing = null;
            Integer ignored = (Integer) unbox.invokeExact(missing);
            System.out.println(ignored);
        } catch (NullPointerException expected) {
            System.out.println("unboxError=NullPointerException");
        }

        // 5. Invalid narrowing at adaptation time: long -> int argument.
        try {
            plusOne.asType(MethodType.methodType(int.class, long.class));
        } catch (WrongMethodTypeException expected) {
            System.out.println("shapeError=WrongMethodTypeException");
        }

        // 6. Target void; adapter int gets zero as a return value.
        MethodHandle announce = find(
                "announce", MethodType.methodType(void.class, String.class));
        MethodHandle addResult = announce.asType(
                MethodType.methodType(int.class, String.class));

        int zero = (int) addResult.invokeExact("ok");
        System.out.println("voidResult=" + zero);
    }
}
~~~

Biên dịch bằng JDK hiện đại có khả năng tạo bytecode mục tiêu Java 18:

~~~shell
javac -encoding UTF-8 --release 18 -d out AsTypeWorkshop.java
java -cp out AsTypeWorkshop
~~~

Kết quả dự kiến:

~~~text
widen=42
box=Long:18
reference=JAVA
referenceError=ClassCastException
unbox=8
unboxError=NullPointerException
shapeError=WrongMethodTypeException
announce=ok
voidResult=0
~~~

Nếu một snippet chạy riêng khác biệt, hãy kiểm tra trước hết `adapter.type()` và kiểu tĩnh của đối số/giá trị trả về ở `invokeExact`. Đây là nguồn lỗi phổ biến hơn vấn đề phiên bản JDK.

### 18.1. Vì sao main khai báo throws Throwable?

Các lời gọi signature-polymorphic `MethodHandle.invoke` và `invokeExact` khai báo khả năng ném `Throwable` từ target hoặc adapter. Để demo ngắn, `main` dùng `throws Throwable`.

Trong ứng dụng thực tế, cần phân loại và xử lý lỗi tại boundary thích hợp thay vì để mọi `Throwable` lan rộng không kiểm soát.

## 19. Kiểm thử adapter bằng bảng case

Sau khi tạo adapter, đừng chỉ test trường hợp input “đẹp”. Một test matrix có thể gồm:

| Case | Adapter type | Giá trị đưa vào | Kết quả kỳ vọng |
|---|---|---|---|
| Widening | `(int)long` từ `(long)long` | `21` | `42L` |
| Primitive narrowing | Xin `(long)int` từ `(int)int` | Không cần invoke | `WrongMethodTypeException` khi `asType` |
| Reference cast hợp lệ | `(Object)Object` từ `(String)String` | Object chứa String | Thành công |
| Reference cast lỗi | Tương tự | Object chứa Integer | `ClassCastException` |
| Unbox thành công | `(Object)Integer` từ `(int)int` | Object chứa Integer | Thành công |
| Unbox null | Tương tự | `null` | `NullPointerException` |
| Unbox wrapper sai | Tương tự | Object chứa String | `ClassCastException` |
| Box và widen reference | `(Integer)Object` từ `(long)long` | Integer | Kết quả runtime là Long |
| Void to int | `(String)int` từ `(String)void` | String | `0` sau khi target chạy |
| Arity mismatch fixed | Target có một tham số, type mới có hai | Không cần invoke | `WrongMethodTypeException` |
| invokeExact mismatch | Adapter type `(int)long`, caller mong `int` | `int` | `WrongMethodTypeException` |

Trong unit test, so sánh chính xác `MethodType` bằng `equals`. Với exception, kiểm tra **thời điểm xảy ra**: khi tạo adapter hay khi gọi. Đừng chỉ catch chung `Throwable` rồi gộp mọi lỗi thành “cast thất bại”.

### 19.1. Kiểm tra adapter không đổi target gốc

~~~java
MethodHandle adapted = target.asType(newType);

System.out.println(target.type());  // Giữ nguyên type ban đầu.
System.out.println(adapted.type()); // Bằng newType.
~~~

`MethodHandle` immutable theo hợp đồng; adaptation không viết lại implementation hoặc metadata của method đích.

### 19.2. Cùng MethodType trả lại chính handle

~~~java
MethodHandle same = target.asType(target.type());

System.out.println(same == target); // true theo hợp đồng API.
~~~

Trường hợp này không thể dùng làm bằng chứng rằng mọi adaptation tạo hoặc không tạo allocation. Khi type khác, implementation có thể tái sử dụng hoặc cache adapter theo cách không cần người dùng biết.

## 20. Về hiệu năng: tạo adapter một lần khi có thể

`asType` biểu diễn một conversion pipeline. Khi một boundary API có type ổn định, ta có thể tạo adapter một lần rồi tái sử dụng:

~~~java
private static final MethodHandle ADAPTED = createAdaptedHandle();
~~~

Lợi ích thiết kế:

- Tập trung logic chuyển kiểu tại một nơi dễ kiểm thử.
- Không lặp quá trình xác định `MethodType` mỗi request.
- Giữ kiểu handle ổn định tại call site `invokeExact`.
- Giúp đo rõ chi phí adaptation setup và invocation hot path.

Tuy vậy, **không bảo đảm** `static final` làm mọi adapter nhanh hơn, hoặc `invoke` luôn tạo adapter mới mỗi lần. JIT có thể tối ưu/inlining tùy workload, profile và phiên bản JVM. JEP 416 có nhắc cơ hội tối ưu với reflective objects ổn định, nhưng không phải số liệu benchmark riêng cho mọi trường hợp `asType`.

Nếu cần tối ưu hệ thống thật, hãy dùng JMH và profiler, tách adaptation setup khỏi timed region khi ứng dụng setup một lần. Đồng thời tính chi phí boxing, cast runtime, polymorphism và công việc bên trong target.

Không dùng `System.nanoTime()` quanh vài lời gọi để kết luận % tăng tốc giữa `asType` và `invoke`.

## 21. Hợp đồng access, null và class loading

Khi dùng `MethodHandles.Lookup.findStatic` hoặc `findVirtual`, Java kiểm tra quyền truy cập tại thời điểm tạo handle. `asType` không cấp quyền truy cập thêm.

Một số điểm cần quan sát:

- Target method không public cần lookup đủ quyền; named module có thể giới hạn truy cập.
- Method handle có thể được truyền cho code khác; giữ handle là giữ một capability gọi operation đã được lookup cho phép.
- Reference cast có thể kiểm tra kiểu ở runtime; với class loader khác nhau, hai class cùng tên chưa chắc là cùng `Class`.
- `null` có thể qua reference cast, nhưng không thể unbox thành primitive.
- Adapter có thể tồn tại hợp lệ dù một số giá trị runtime chắc chắn gây `ClassCastException`.
- Adapter không validate nội dung dữ liệu nghiệp vụ; nếu cần parse, range check hay normalization, hãy dùng converter/filter được thiết kế riêng.
- Với primitive widening tới `float`/`double`, Java cho phép conversion nhưng có thể mất precision số học.

Tránh dùng API nội bộ trong `java.lang.invoke` để can thiệp trực tiếp vào call site hoặc né access checks. Các API `MethodHandle`, `MethodType` và `MethodHandles` công khai đã đủ cho các tình huống trong bài.

## 22. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `asType` được giới thiệu cùng JEP 416 | `asType` có từ Java 7; JEP 416 ở Java 18 tái triển khai core reflection |
| `newType` thay chữ ký của method Java gốc | Adapter có type mới; target giữ nguyên |
| `methodType(int.class, long.class)` là `(int)long` | Factory đặt return trước: đây là `(long)int` |
| Argument và return đổi theo cùng một chiều | Argument: new → old; return: old → new |
| Reference cast không thành công sẽ bị từ chối khi tạo adapter | Nhiều cast chỉ bị kiểm tra khi invoke |
| `Object -> int` có nghĩa parse String | Chỉ unboxing wrapper phù hợp, không parse text |
| Primitive widening luôn giữ chính xác mọi số | `long -> float` có thể mất precision |
| `long -> int` là widening | Đây là narrowing, thường không được `asType` chấp nhận |
| `Boolean -> int` hợp lệ như numeric wrapper | `boolean` không chuyển thành numeric primitive bằng `asType` |
| `null` có thể unbox thành 0 | Unboxing null gây `NullPointerException` |
| `asType` luôn đổi số lượng argument | Fixed-arity giữ nguyên arity; varargs collector có quy tắc riêng |
| `invokeExact` tự thích nghi theo `asType` | Nó yêu cầu call-site descriptor khớp tuyệt đối |
| `invoke` luôn cấp phát adapter mới | Implementation có thể tối ưu mà không tạo object adapter quan sát được |
| `asType` giúp gọi private method không được phép | Quyền lookup được kiểm tra riêng, adapter không mở access |
| Target trả `void` thì adapter không thể trả value | Return có thể được đặt thành null hoặc giá trị zero |
| Target `long` có thể tự narrowing thành `int` | Cần explicit cast semantics khác hoặc logic chuyển đổi riêng |

## 23. Bài tập thực hành

### Bài 1 — Xác định hướng conversion

Target có type `(long)double`. Bạn muốn caller truyền `int` và nhận `Object`.

**Yêu cầu:** Viết `MethodType` cho adapter và giải thích input conversion, output boxing. Không dùng `invokeExact` trước khi chắc chắn call-site type khớp adapter.

**Gợi ý:** Input `int -> long`; output `double -> Double -> Object`.

### Bài 2 — Nhận diện primitive narrowing bị từ chối

Target có type `(int)int`. Thử `asType` thành `(long)long`.

**Yêu cầu:** Chỉ ra tại sao không thành công dù `int -> long` ở return là hợp lệ. Xác định cặp không hợp lệ ở argument.

### Bài 3 — Reference cast tại runtime

Target `(String)String`, adapter `(Object)Object`.

**Yêu cầu:** Gọi bằng Object chứa String, Object chứa Integer và `null`. Phân biệt lỗi của adapter với lỗi target method khi nhận null.

### Bài 4 — Boxing/unboxing hai chiều

Target `(long)long`, adapter `(Integer)Object`.

**Yêu cầu:** Dự đoán wrapper type của input và output, in `result.getClass()` và giải thích vì sao output là `Long`.

### Bài 5 — void return conversion

Tạo target `(String)void`, dùng `asType` yêu cầu `(String)int`, `(String)boolean`, `(String)Object`.

**Yêu cầu:** Ghi giá trị mặc định mà mỗi adapter trả, đồng thời xác nhận body target vẫn được chạy.

### Bài 6 — Bảng lỗi có thời điểm

Viết test nhỏ tách các nhóm:

- `WrongMethodTypeException` khi tạo adapter do narrowing.
- `ClassCastException` khi cast reference runtime sai.
- `NullPointerException` khi unboxing null.
- `WrongMethodTypeException` khi call-site `invokeExact` không khớp.

**Tiêu chí đạt:** Không catch chung các lỗi và gộp thành một loại.

### Bài 7 — Chọn API đúng thay vì ép asType

Bạn cần chuyển chuỗi `"42"` thành `int` rồi gọi target `(int)int`.

**Yêu cầu:** Giải thích vì sao `asType` không tự parse, đề xuất `Integer.parseInt` hoặc `filterArguments`, xác định lỗi khi chuỗi không hợp lệ.

## 24. Checklist trước khi dùng asType trong dự án

- [ ] Biết chính xác `original.type()` và `newType`.
- [ ] Đếm đúng số tham số của fixed-arity handle.
- [ ] Đã xác định hướng conversion riêng cho argument và return.
- [ ] Chỉ dựa vào primitive widening khi dùng `asType`.
- [ ] Không nhầm boxing với parsing hoặc formatting.
- [ ] Kiểm tra null khi có unboxing.
- [ ] Có test runtime reference cast sai kiểu.
- [ ] Không suy luận adapter hợp lệ nghĩa mọi input runtime hợp lệ.
- [ ] `invokeExact` có parameter/return call-site type khớp adapter.
- [ ] Dùng `invoke` khi muốn implicit asType-compatible conversion có chủ đích.
- [ ] Chọn combinator khác khi cần thay arity/thứ tự/nội dung.
- [ ] Hiểu `void` return có thể bỏ hoặc tạo default value.
- [ ] Không dùng `asType` để bypass module/access control.
- [ ] Cache adapter khi type ổn định và đo nếu tối ưu hiệu năng.
- [ ] Đã kiểm tra Javadoc trên JDK đang triển khai.
- [ ] Phân biệt nguồn gốc Java 7 của `asType` với JEP 416 Java 18.

## 25. Tài liệu chính thức

1. [MethodHandle — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): hợp đồng `asType`, `invokeExact`, `invoke`, conversion và exception.
2. [MethodType — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodType.html): định nghĩa method descriptor, factory `methodType` và immutability.
3. [MethodHandles — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup, `explicitCastArguments` và argument/result combinators.
4. [MethodHandles.Lookup — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền truy cập khi tạo handle.
5. [WrongMethodTypeException — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): exception khi chữ ký không tương thích.
6. [Java Language Specification — `5.3 Method Invocation Conversion](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html#jls-5.3): primitive widening và method invocation conversions.
7. [Java Language Specification — `5.5 Casting Contexts](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html#jls-5.5): casting conversion và boxing/reference cast.
8. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh thay đổi implementation reflection trong Java 18, không thay thế public MethodHandle API.

**Kết quả cần đạt:** Bạn có thể đọc chính xác `MethodType`, dùng `asType` để tạo adapter có kiểu gọi mong muốn, giải thích reference casts, boxing, unboxing, primitive widening và `void`, đồng thời biết khi nào phát sinh `WrongMethodTypeException`, `ClassCastException` và `NullPointerException`. Đây là kỹ năng còn áp dụng trên JDK hiện đại, không phụ thuộc vào implementation reflection cũ.
