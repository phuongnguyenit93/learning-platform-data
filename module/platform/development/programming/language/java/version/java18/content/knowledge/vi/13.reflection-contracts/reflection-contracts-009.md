# Boxing, unboxing và primitive widening được phép khi gọi qua reflection

> **Phạm vi:** Bài thuộc chương **Hợp đồng reflection** của module `JAVA_VERSION_JAVA18`. Trong nhóm kiến thức Java 18 còn hữu ích trên các JDK hiện đại, JEP 416 thay đổi cách JDK triển khai core reflection dựa trên method handles; **hợp đồng chuyển đổi đối số của** `Method.invoke`, `Constructor.newInstance` **và truy cập** `Field` vẫn phải được hiểu theo API công khai. Bài này tập trung vào boxing, unboxing, primitive widening, những phép chuyển đổi bị từ chối, và cách kiểm chứng bằng ví dụ có thể chạy. Không dùng API nội bộ hoặc giả định về triển khai legacy.

## 1. Ba giai đoạn dễ nhầm khi gọi động

Giả sử ta có phương thức:

~~~java
public long add(long amount) {
    return amount + 10;
}
~~~

Khi gọi thông thường bằng `add(5)`, compiler biết `5` là `int` và có thể áp dụng chuyển đổi `int → long`. Khi gọi bằng reflection:

~~~java
Method method = target.getClass().getMethod("add", long.class);
Object result = method.invoke(target, Integer.valueOf(5));
~~~

cần phân biệt ba bước độc lập:

1. **Tra cứu thành viên:** `getMethod("add", long.class)` yêu cầu đúng kiểu tham số được **khai báo**, ở đây là `long`. API này không tìm overload bằng cách thử widening.
2. **Truyền đối số:** `Method.invoke` nhận `Object...`. `Integer.valueOf(5)` là một object được truyền vào; reflection có thể **unbox `Integer` thành `int` rồi primitive widen `int → long`** để phù hợp tham số `long`.
3. **Nhận kết quả:** Vì phương thức đích trả `long`, `Method.invoke` **boxing** kết quả thành `Long` trước khi trả về dưới kiểu tham chiếu `Object`.

~~~text
Tra cứu đúng chữ ký            Truyền giá trị                Kết quả
getMethod("add", long.class)   Integer(5)                    long 15
              |                    |                           |
              v                    v                           v
        Method hợp lệ         unbox int = 5             boxing Long(15)
                                   |
                                   v
                           widen int -> long
                                   |
                                   v
                              add(5L)
~~~

Một lời gọi reflection **không tự quyết định overload tốt nhất** theo đối số runtime. Ta phải lấy đúng `Method` hoặc `Constructor` trước, sau đó API mới kiểm tra khả năng chuyển các giá trị được truyền sang kiểu tham số đã chọn.

## 2. Boxing, unboxing và widening là gì?

**Boxing** là chuyển giá trị primitive thành object của wrapper tương ứng: `int → Integer`, `long → Long`, `boolean → Boolean`. **Unboxing** là chiều ngược lại: lấy giá trị primitive từ object wrapper, như `Integer → int`.

Các cặp primitive và wrapper:

| Primitive | Wrapper | Ví dụ |
|---|---|---|
| `boolean` | `Boolean` | `Boolean.valueOf(true)` |
| `byte` | `Byte` | `Byte.valueOf((byte) 3)` |
| `short` | `Short` | `Short.valueOf((short) 3)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(3)` |
| `long` | `Long` | `Long.valueOf(3L)` |
| `float` | `Float` | `Float.valueOf(3.0f)` |
| `double` | `Double` | `Double.valueOf(3.0d)` |

Các phương thức reflection như `Method.invoke(Object, Object...)` nhận **đối số dạng object**. Nếu ta viết `invoke(target, 3)`, chính Java tại **vị trí gọi** đã boxing literal `3` thành `Integer` để truyền qua tham số `Object...`. Reflection nhận object đó và, nếu phương thức đích cần `long`, tiếp tục thực hiện unboxing và widening được phép.

### 2.1. Primitive widening hợp lệ

**Primitive widening** chuyển giá trị sang primitive khác có phạm vi loại số rộng hơn theo hợp đồng ngôn ngữ. Bảng sau là các đích widening (không tính trường hợp giữ nguyên kiểu):

| Kiểu nguồn | Các kiểu đích widening được phép |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có |
| `boolean` | Không có; chỉ tương thích `boolean` |

Ví dụ: `Byte(3)` có thể unbox thành `byte` rồi widen thành `long` cho một tham số kiểu `long`. `Character('A')` có thể unbox thành `char` rồi widen thành `int`, nhận giá trị mã số `65`. Nhưng `short → char`, `double → long` và `boolean → int` **không** phải widening hợp lệ.

**Widening không đồng nghĩa luôn giữ nguyên độ chính xác.** `int → float` và `long → float/double` có thể làm tròn vì định dạng số thực dấu chấm động không biểu diễn chính xác mọi giá trị nguyên lớn. Java vẫn cho phép chuyển đổi đó; ứng dụng tài chính hoặc xử lý dữ liệu chính xác cần tự kiểm tra quy tắc nghiệp vụ.

### 2.2. Không có chuyển đổi wrapper này thành wrapper khác

`Integer` và `Long` đều kế thừa `Number`, nhưng **không có quan hệ kế thừa giữa** `Integer` **và** `Long`.

~~~java
public static void takeLongWrapper(Long value) { }
public static void takeLongPrimitive(long value) { }
~~~

Giả sử đã tìm được đúng hai đối tượng `Method`:

~~~java
Method wrapper = Demo.class.getMethod("takeLongWrapper", Long.class);
Method primitive = Demo.class.getMethod("takeLongPrimitive", long.class);

// Hợp lệ: Integer -> int -> long.
primitive.invoke(null, Integer.valueOf(7));

// Không hợp lệ: Integer không phải Long.
wrapper.invoke(null, Integer.valueOf(7)); // IllegalArgumentException
~~~

`Demo` ở đây là lớp minh họa có các phương thức public static được khai báo phía trên. Khi cần một `Long` cho tham số tham chiếu `Long`, ứng dụng phải **chủ động** chuyển giá trị, ví dụ `Long.valueOf(integer.longValue())`, trước khi gọi.

Ngược lại, `Integer` là subtype của `Number` và `Object`, nên một tham số khai báo `Number` hoặc `Object` có thể nhận `Integer` qua **widening reference**. Đây là quy tắc tương thích kiểu tham chiếu, khác với primitive widening.

## 3. Hợp đồng chuyển đổi ở từng API reflection

| Thao tác | Đầu vào | Chuyển đổi được hỗ trợ | Kết quả |
|---|---|---|---|
| `Method.invoke(receiver, args...)` | `Object[]` chứa các đối số | Kiểm tra tương thích reference; unboxing wrapper và primitive widening nếu formal parameter là primitive | Primitive return được boxing thành wrapper; `void` cho `null` |
| `Constructor.newInstance(args...)` | `Object[]` chứa các đối số | Tương tự `Method.invoke` đối với tham số constructor | Trả object vừa tạo |
| `Field.set(receiver, value)` | Một `Object` | Tương thích reference hoặc unboxing rồi primitive widening đối với primitive field | Ghi giá trị trường nếu có quyền và trường cho phép |
| `Field.get(receiver)` | Object chứa field (hoặc `null` cho static field) | Primitive field được boxing thành wrapper tương ứng | Trả `Object` |
| `Field.setInt(receiver, intValue)` | `int` đã xác định ở vị trí gọi | Giữ nguyên `int` hoặc widen đến kiểu primitive của field nếu hợp lệ | Ghi field, không có bước truyền wrapper |
| `Field.getLong(receiver)` | Object chứa field | Đọc primitive field có thể widen sang `long` | Trả primitive `long` |

**Hai điều kiện luôn phải kiểm tra:** chuyển đổi kiểu hợp lệ **và** quyền truy cập đối với thành viên. Có thể chuyển đổi đúng mà vẫn bị `IllegalAccessException`; một field final cũng có những giới hạn riêng khi ghi.

### Đối số `null`

Một tham số tham chiếu có thể nhận `null` nếu luật truy cập và chữ ký cho phép. Tham số primitive **không thể** nhận `null`:

~~~java
Method acceptLong = Demo.class.getMethod("takeLongPrimitive", long.class);

// Một đối số null, đích là long -> lỗi chuyển đổi:
acceptLong.invoke(null, new Object[] { null }); // IllegalArgumentException
~~~

Không nhầm `new Object[] { null }` (một đối số có giá trị null) với `(Object[]) null` truyền cho chính `invoke` (không cung cấp đối số nào). Với phương thức đích yêu cầu một tham số, trường hợp thứ hai thất bại vì thiếu đối số.

## 4. Tra cứu chữ ký cần chính xác, kể cả khi lời gọi cho phép widening

`Class.getMethod`, `getDeclaredMethod`, `getConstructor` và `getDeclaredConstructor` nhận các đối tượng `Class<?>` biểu thị **kiểu formal parameter chính xác**. Chúng không thực hiện overload resolution như compiler Java.

~~~java
public class SignatureExample {
    public void record(long value) { }
    public void record(Integer value) { }
}
~~~

~~~java
Class<SignatureExample> type = SignatureExample.class;

Method a = type.getMethod("record", long.class);
Method b = type.getMethod("record", Integer.class);

// Không có record(int): lệnh sau ném NoSuchMethodException.
type.getMethod("record", int.class);
~~~

Bất kể `Integer(4)` có thể gọi được overload `record(long)` qua unboxing + widening, việc tìm `getMethod("record", Integer.class)` vẫn trả đúng overload **nhận `Integer`** nếu overload đó tồn tại.

Trong hệ thống dispatch động, quy trình nên là:

1. Xác định danh sách phương thức ứng viên theo tên và số lượng tham số.
2. Đọc chữ ký bằng `getParameterTypes()`; áp dụng chính sách chọn overload rõ ràng cho ứng dụng.
3. Chọn một `Method` cụ thể; sau đó `invoke` mới kiểm tra đối số có chuyển đổi được theo chữ ký đã chọn hay không.
4. Nếu nhiều ứng viên cùng phù hợp, không dựa vào thứ tự trả về từ `getMethods()`; quy tắc chọn hoặc báo lỗi mơ hồ phải do ứng dụng quyết định.

`Class.getMethods()` **không cam kết thứ tự**. Việc “lấy phần tử đầu tiên có tên trùng” có thể dẫn đến hành vi không ổn định, nhất là khi API thêm overload.

## 5. Ví dụ chạy được: Constructor, Field và Method

Tạo file `ReflectionWideningDemo.java`. Ví dụ sử dụng class public lồng nhau, tránh cần cấu hình module và chỉ dùng API Java được hỗ trợ trên JDK 18 trở lên.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionWideningDemo {

    public static class Counter {
        public long value;

        public Counter(long initial) {
            this.value = initial;
        }

        public long add(long delta) {
            value += delta;
            return value;
        }

        public void clear() {
            value = 0L;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        // 1. Constructor có formal parameter là long.
        Constructor<Counter> constructor =
                Counter.class.getConstructor(long.class);

        // Integer -> int -> long: hợp lệ khi newInstance.
        Counter counter = constructor.newInstance(Integer.valueOf(10));

        // 2. Field có kiểu khai báo long.
        Field value = Counter.class.getField("value");

        // Short -> short -> long: hợp lệ khi Field.set.
        value.set(counter, Short.valueOf((short) 20));

        Object fieldValue = value.get(counter);
        System.out.println(
                "Field.get: " + fieldValue + " ("
                        + fieldValue.getClass().getSimpleName() + ")");

        // 3. Method khai báo add(long).
        Method add = Counter.class.getMethod("add", long.class);

        // Byte -> byte -> long: hợp lệ khi Method.invoke.
        Object returned = add.invoke(counter, Byte.valueOf((byte) 3));

        System.out.println(
                "Method.invoke: " + returned + " ("
                        + returned.getClass().getSimpleName() + ")");

        // 4. void method có kết quả reflection là null.
        Method clear = Counter.class.getMethod("clear");
        System.out.println("Void return: " + clear.invoke(counter));

        // 5. double -> long là narrowing, không hợp lệ.
        try {
            add.invoke(counter, Double.valueOf(1.5));
            throw new AssertionError("Must reject double to long");
        } catch (IllegalArgumentException expected) {
            System.out.println("Rejected narrowing: "
                    + expected.getClass().getSimpleName());
        }

        // 6. Lookup không thực hiện widening/boxing.
        try {
            Counter.class.getMethod("add", Integer.class);
            throw new AssertionError("Method add(Integer) must not exist");
        } catch (NoSuchMethodException expected) {
            System.out.println("Lookup requires long.class");
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac -encoding UTF-8 ReflectionWideningDemo.java
java ReflectionWideningDemo
~~~

Kết quả mong đợi:

~~~text
Field.get: 20 (Long)
Method.invoke: 23 (Long)
Void return: null
Rejected narrowing: IllegalArgumentException
Lookup requires long.class
~~~

Giải thích cụ thể:

- `constructor.newInstance(Integer.valueOf(10))`: constructor đích yêu cầu `long`; reflection unbox `Integer` thành `int` và widen thành `long`.
- `value.set(counter, Short.valueOf((short) 20))`: field có kiểu `long`; giá trị wrapper được unbox thành `short` rồi widen thành `long`.
- `value.get(counter)`: field kiểu `long` được boxing thành `Long` khi trả về dưới dạng `Object`.
- `add.invoke(counter, Byte.valueOf((byte) 3))`: tham số `long` nhận `Byte` qua unboxing + widening. Phương thức trả `long` nên `invoke` trả `Long`.
- `clear.invoke(counter)`: phương thức đích trả `void`; kết quả của `Method.invoke` là `null`.
- `Double(1.5)` không thể truyền sang tham số `long` vì đó là **primitive narrowing**. Reflection từ chối trước khi thực thi phương thức đích.
- `getMethod("add", Integer.class)` không thể tìm `add(long)`: phương pháp tra cứu chữ ký yêu cầu đúng kiểu khai báo.

Ví dụ này minh họa hành vi trên thành viên `public`. Nó không cần `setAccessible(true)` và không phụ thuộc vào cách JDK cài đặt reflection bên trong.

## 6. Những chuyển đổi bị từ chối và lý do

Bảng giả định đã lấy được `Method` có một tham số như cột **Tham số đích**, và truyền vào `Object` như cột **Giá trị runtime**.

| Giá trị runtime | Tham số đích | Hợp lệ? | Giải thích |
|---|---|---|---|
| `Integer.valueOf(7)` | `long` | Có | `Integer → int → long` |
| `Character.valueOf('A')` | `int` | Có | `Character → char → int` |
| `Long.valueOf(7L)` | `float` | Có | `Long → long → float`, có thể mất độ chính xác |
| `Float.valueOf(1.5f)` | `double` | Có | `Float → float → double` |
| `Byte.valueOf((byte) 1)` | `char` | **Không** | `byte → char` không phải widening |
| `Double.valueOf(3.0)` | `long` | **Không** | `double → long` là narrowing, kể cả khi giá trị nhìn giống số nguyên |
| `Integer.valueOf(7)` | `Long` | **Không** | `Integer` không thể tự chuyển thành wrapper `Long` |
| `Integer.valueOf(7)` | `Number` | Có | Widening reference: `Integer` là subtype của `Number` |
| `Boolean.TRUE` | `int` | **Không** | `boolean` không widen thành kiểu số |
| `null` | `long` | **Không** | Primitive không nhận giá trị null |
| `null` | `Long` | Có | Kiểu tham chiếu có thể nhận null |
| `Long.valueOf(7)` | `long` | Có | Unboxing trực tiếp |

### Tại sao giá trị “vừa” kiểu hẹp hơn vẫn bị từ chối?

~~~java
public static void takeInt(int value) { }
~~~

Giả sử đã lấy được `Method` của `takeInt(int)`:

~~~java
Method m = Demo.class.getMethod("takeInt", int.class);
m.invoke(null, Long.valueOf(2L)); // IllegalArgumentException
~~~

Mặc dù số `2` có thể biểu diễn bởi `int`, kiểu **runtime** của object là `Long`. Reflection không thử kiểm tra khoảng giá trị để tự narrowing từ `long` xuống `int`. Nếu cần phép chuyển có chủ đích, code ứng dụng phải kiểm tra phạm vi rồi chuyển:

~~~java
long source = 2L;
int converted = Math.toIntExact(source); // lỗi ArithmeticException nếu tràn
m.invoke(null, Integer.valueOf(converted));
~~~

`Math.toIntExact` phù hợp khi ứng dụng muốn **từ chối** giá trị ngoài phạm vi `int`; nó không tự giải quyết mọi khác biệt ngữ nghĩa như chuyển số thực có phần lẻ. Ví dụ dùng lớp `Demo` giả định ở đoạn trước.

## 7. `Method.invoke` có varargs ở hai tầng khác nhau

Có hai cơ chế dễ bị đánh đồng:

1. `Method.invoke(Object receiver, Object... args)` là **API Java varargs**: compiler có thể đóng gói danh sách đối số của lời gọi `invoke` vào một `Object[]`.
2. Một **phương thức đích** được khai báo `String...` thực chất có tham số cuối kiểu mảng `String[]` trong metadata. Reflection yêu cầu truyền đúng một đối số mảng cho vị trí đó; `Method.invoke` không thay compiler thực hiện varargs packing cho phương thức đích.

Ví dụ:

~~~java
public static int count(String... names) {
    return names.length;
}
~~~

~~~java
Method count = Demo.class.getMethod("count", String[].class);

// Chuyển String[] thành một Object đơn lẻ trong args của invoke.
Object size = count.invoke(null, (Object) new String[] {"A", "B"});
System.out.println(size); // 2 (Integer được boxing từ int)
~~~

Nếu viết `count.invoke(null, new String[] {"A", "B"})`, Java có thể diễn giải `String[]` làm **mảng varargs cho chính `invoke`**, khiến phần tử `"A"`, `"B"` trở thành hai đối số riêng biệt. Kết quả không khớp một tham số `String[]` của phương thức đích. Ép kiểu `(Object)` bảo đảm truyền **một** đối số là mảng.

Một phương thức đích `void accept(int... values)` có tham số metadata là `int[].class`; không được trông chờ reflection tự chuyển ba wrapper `Integer` thành mảng `int[]`. Ứng dụng phải tạo mảng trước:

~~~java
Method accept = Demo.class.getMethod("accept", int[].class);
accept.invoke(null, (Object) new int[] {1, 2, 3});
~~~

Hai đoạn trong mục này giả định lớp `Demo` chứa các phương thức public static tương ứng; chúng nhằm minh họa truyền varargs, độc lập với file chạy hoàn chỉnh ở mục 5.

## 8. `Field.get/set` so với getter/setter theo primitive

API `Field` có các phương thức chuyên biệt như `getInt`, `getLong`, `setInt` và `setLong`. Chúng nhận hoặc trả giá trị primitive, tránh việc phải thao tác qua object wrapper ở chính API field, nhưng **vẫn phải tuân thủ** các quy tắc conversion.

Giả sử:

~~~java
public class Sample {
    public int count = 5;
    public long total = 0L;
}
~~~

~~~java
Sample sample = new Sample();
Field count = Sample.class.getField("count");
Field total = Sample.class.getField("total");

// int -> long hợp lệ khi đọc qua getLong.
long a = count.getLong(sample); // 5L

// setInt nhận int và có thể widen thành long của field đích.
total.setInt(sample, 12);
long b = total.getLong(sample); // 12L

// getInt không thể đọc field long vì long -> int là narrowing.
count.getInt(sample); // Hợp lệ: field count có kiểu int.
total.getInt(sample); // IllegalArgumentException
~~~

Nếu mục tiêu là `long`, `Field.setInt` có thể ghi `int` với widening; chiều ngược lại, `Field.setLong` không thể ghi vào `int` field. Hãy chọn `getXxx/setXxx` theo hợp đồng API, không suy từ cách tên phương thức nghe có vẻ tương đồng.

Với `Field.get` thông thường, primitive field được boxing thành wrapper **cùng kiểu trường**; `Field.get` không tự widen kết quả `int` sang `Long`:

~~~java
Object boxed = count.get(sample);
System.out.println(boxed.getClass() == Integer.class); // true
~~~

Muốn nhận `long` từ `int` field có thể dùng `count.getLong(sample)`, hoặc lấy `Integer` rồi chủ động chuyển đổi.

**Quyền truy cập và final:** Các phép chuyển đổi kiểu không cấp quyền ghi field `private` hoặc thay đổi `final`. Với dữ liệu nghiệp vụ, ưu tiên phương thức public đảm bảo validation, và chỉ dùng field reflection khi thực sự cần thiết và được phép.

## 9. Ngoại lệ do chuyển đổi khác ngoại lệ do code đích ném

Khi `Method.invoke` hoặc `Constructor.newInstance` xử lý lời gọi động, cần phân biệt hai nhóm lỗi:

| Tình huống | Ngoại lệ điển hình | Lúc nào xảy ra? |
|---|---|---|
| Số lượng đối số sai, wrapper không chuyển thành primitive được, narrowing không hợp lệ, receiver không phù hợp | `IllegalArgumentException` | Kiểm tra đối số trước khi thực thi thành công đích |
| Không có quyền gọi thành viên | `IllegalAccessException` | Kiểm tra quyền truy cập |
| Phương thức/constructor đích tự ném exception | `InvocationTargetException` | Sau khi thực sự gọi code đích; xem `getCause()` |
| Tra cứu không tìm được đúng chữ ký | `NoSuchMethodException` | Khi gọi `getMethod` hoặc `getConstructor` |
| Không có field đúng tên/phạm vi | `NoSuchFieldException` | Khi gọi `getField` hoặc `getDeclaredField` |

Ví dụ, `Double.valueOf(1.5)` được đưa cho `add(long)` gây `IllegalArgumentException` vì sai kiểu; phương thức `add` chưa được gọi. Nhưng nếu `add` thực sự chạy và ném `IllegalStateException`, `Method.invoke` sẽ bọc ngoại lệ của đích trong `InvocationTargetException`.

~~~java
try {
    Object value = method.invoke(target, arguments);
    System.out.println(value);
} catch (IllegalArgumentException conversionProblem) {
    System.err.println("Invalid receiver/arguments: "
            + conversionProblem.getMessage());
} catch (java.lang.reflect.InvocationTargetException callProblem) {
    Throwable cause = callProblem.getCause();
    System.err.println("Target method failed: " + cause);
}
~~~

Đoạn mã là mẫu minh họa, giả định `method`, `target`, `arguments` đã được khai báo và checked `IllegalAccessException` được xử lý ở tầng gọi hoặc khai báo `throws`. Khi ghi log trong hệ thống thật, đừng gộp hai trường hợp thành một thông báo “phương thức lỗi”; điều đó che mất nguyên nhân do dispatcher hay nghiệp vụ.

## 10. Các lưu ý còn áp dụng trên JDK hiện đại

### 10.1. Reflection không phá vỡ encapsulation của module

Primitive widening hợp lệ **không giúp** vượt qua giới hạn access control. Dù đối số đúng kiểu, việc gọi một phương thức không public hoặc public member trong package không được export phù hợp vẫn có thể thất bại. Khi cần deep reflection trong named module, cấu hình `opens` đúng package theo hợp đồng JPMS; `trySetAccessible()` có thể trả `false` nếu module không cho phép.

### 10.2. JEP 416 không thay hợp đồng chuyển đổi

Từ Java 18, JEP 416 tái triển khai core reflection dựa trên method handles. Đây là thay đổi **cách JDK triển khai**, không phải lời hứa rằng `Method.invoke` có luật ép kiểu giống mọi API của `java.lang.invoke.MethodHandle`. `MethodHandle.invokeExact` có yêu cầu kiểu chính xác ở call site; `MethodHandle.invoke` có các quy tắc thích nghi riêng. Khi chuyển từ reflection sang method handles vì hiệu năng hoặc kiến trúc, cần đọc lại hợp đồng API và kiểm thử, không lấy kết quả `Method.invoke` để suy ra mọi dạng chuyển đổi của method handles.

### 10.3. Widening số học có thể mất độ chính xác

~~~java
int original = 16_777_217;
float widened = original; // Java cho phép int -> float.

System.out.println(original);            // 16777217
System.out.println((int) widened);       // 16777216
~~~

Sự khác nhau này phát sinh từ biểu diễn `float`, không phải một lỗi riêng của reflection. Nếu method đích nhận `float` và reflection unbox `Integer` rồi widen thành `float`, vấn đề độ chính xác cũng tồn tại. Với dữ liệu cần bảo toàn chính xác, API nên chọn kiểu phù hợp ngay từ thiết kế, hoặc đưa vào kiểm tra riêng.

### 10.4. Tránh dispatcher tự đoán và ép kiểu âm thầm

Nếu input đến từ JSON, database hoặc CLI, object runtime có thể là `Integer`, `Long`, `Double`, `BigDecimal` hay `String` tùy thư viện. Không giả định một giá trị số “trông giống 1” luôn được reflection nhận cho mọi primitive. Lớp mapping nên công khai quy tắc chuyển đổi và kiểm tra overflow, phần thập phân, `null` trước khi đưa đối số vào `invoke`.

## 11. Bài thực hành và câu hỏi tự đánh giá

1. Cho `public void save(long id)`, vì sao `getMethod("save", Integer.class)` thất bại dù `Integer.valueOf(5)` gọi được `save(long)` qua `Method.invoke`?
2. `Character.valueOf('A')` có thể truyền vào phương thức nhận `int` hay `short` không? Giải thích theo bảng primitive widening.
3. Tại sao `Long.valueOf(3L)` không truyền được vào tham số `Integer` ngay cả khi giá trị `3` nằm trong phạm vi `int`?
4. Khi `Field.get` đọc field kiểu `int`, nó trả về wrapper gì? Vì sao muốn lấy primitive `long` có thể dùng `Field.getLong`?
5. `Method.invoke` trả về gì khi phương thức đích khai báo `void`? Khi đích trả `double`?
6. Vì sao `int → float` là phép widening hợp lệ nhưng có thể mất độ chính xác?
7. Có thể truyền ba đối số `Integer` riêng biệt cho method đích nhận `int...` bằng `Method.invoke` và chờ JDK tự đóng gói thành mảng không?
8. Phân biệt `IllegalArgumentException` do không chuyển được đối số với `InvocationTargetException` do code đích ném.
9. Khi gọi constructor nhận `long`, `Constructor.newInstance(Short.valueOf((short) 2))` có hợp lệ không? Vì sao?
10. Nếu module không mở package cho caller, primitive widening có khiến `Method.invoke` truy cập được private method hay không?

**Ghi nhớ:** Reflection **tra cứu chữ ký chính xác**, rồi mới áp dụng chuyển đổi được phép cho các đối số của **thành viên đã chọn**. Wrapper tương ứng có thể được unbox và primitive được widen theo bảng chuẩn; không có narrowing tự động, không có chuyển đổi `Integer → Long` như hai wrapper, và `null` không phù hợp primitive. Kết quả primitive của `Method.invoke` / `Field.get` được boxing, còn kết quả `void` của `invoke` là `null`. Những quy tắc này tiếp tục có hiệu lực trên JDK hiện đại.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Java SE 25: `Method.invoke`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 25: `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html).
- [Java SE 25: `Field.get/set` và các getter/setter primitive](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html).
- [Java SE 25: `Class.getMethod` / `getConstructor`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html).
- [Java Language Specification `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.2).
- [Java SE 25: `AccessibleObject` và kiểm soát truy cập reflection](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

