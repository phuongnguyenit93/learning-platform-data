# So sánh cùng một ca biên giữa reflection, handle chính xác và handle có adapter

## 1. Mục tiêu và bối cảnh

Trong chương **Lookup và adapter** của mô-đun Java 18, chúng ta sẽ dùng **cùng một phương thức đích, cùng một receiver và cùng dữ liệu đầu vào** để so sánh ba đường gọi:

1. **Core reflection:** `java.lang.reflect.Method.invoke(...)`.
2. **Method handle chính xác:** `MethodHandle.invokeExact(...)` trên handle trực tiếp lấy qua `MethodHandles.Lookup`.
3. **Method handle có adapter:** tạo handle mới bằng `asType(...)`, rồi gọi `invokeExact(...)` trên handle đã chuyển đổi.

Bài học kiểm chứng các hợp đồng API còn có hiệu lực trên JDK hiện đại. JEP 416 của Java 18 chuyển phần triển khai core reflection sang cơ chế dựa trên method handles, nhưng **không biến ba cách gọi trên thành cùng một hợp đồng**. Sự khác biệt về kiểu tại điểm gọi, receiver, chuyển đổi đối số, kiểu trả về và xử lý ngoại lệ vẫn phải được hiểu rõ.

Sau bài học, bạn có thể:

- Xác định chính xác `MethodType` của handle trước và sau khi tạo adapter.
- Giải thích vì sao `Method.invoke` nhận được `Integer` cho tham số đích `long`, trong khi `invokeExact` trực tiếp yêu cầu `long` ở điểm gọi.
- Tạo adapter `(Counter,Integer)Long` từ handle `(Counter,long)long` để xử lý cùng giá trị `Integer`.
- Dự đoán ngoại lệ tại đúng tầng: tìm member, kiểm tra chữ ký, chuyển đổi đối số, và thực thi phương thức đích.
- Chỉ ra trường hợp ba đường gọi có cùng **kết quả nghiệp vụ** nhưng khác **giao diện và đường thực thi**.

> **Giới hạn kiến thức:** Chỉ sử dụng `java.lang.reflect` và `java.lang.invoke` được hỗ trợ trên JDK từ Java 18 trở lên. Các kết quả hành vi dưới đây xuất phát từ hợp đồng API. Không suy ra kết luận hiệu năng từ số lần in kết quả của chương trình minh họa.

## 2. Chọn một ca biên cụ thể

Giả sử lớp `Counter` có phương thức instance:

~~~java
public long add(long delta) {
    return Math.addExact(base, delta);
}
~~~

Phương thức **nhận một `long` nguyên thủy**, nhưng nguồn dữ liệu động (ví dụ một framework đọc tham số từ registry) lại trả về **`Integer.valueOf(2)`**.

Ta đặt:

~~~text
Receiver:      Counter(base = 40)
Dữ liệu vào:   Integer.valueOf(2)
Tham số đích:  long delta
Kết quả đúng:  42 (kiểu nguyên thủy long ở phương thức đích)
~~~

Đây là ca biên có ý nghĩa vì `Integer` khác `long`:

- Reflection có thể **unbox `Integer` thành `int`, rồi widening `int` thành `long`** theo chuyển đổi được phép của `Method.invoke`.
- Handle trực tiếp có kiểu `(Counter,long)long`. Lời gọi `invokeExact` với `Integer` **không khớp**, dù giá trị là số `2`.
- Adapter được tạo hợp lệ bằng `asType` có thể nhận `Integer`, thực hiện chuyển đổi được phép, rồi đóng hộp `long` trả về thành `Long`.

Chúng ta cũng thử hai nhánh từ **chính phương thức này**: truyền `null` cho tham số nguyên thủy và làm `Math.addExact` tràn số. Nhờ dùng chung target, có thể phân biệt lỗi của **lớp chuyển đổi** với lỗi do **phần thân phương thức**.

## 3. Ba hình dạng lời gọi

| Thuộc tính | Reflection | Handle chính xác | Handle có adapter |
| --- | --- | --- | --- |
| Đối tượng dùng để gọi | `Method` | `MethodHandle` lấy qua `findVirtual` | `MethodHandle` mới từ `direct.asType(...)` |
| Đối số receiver | Tham số `obj` riêng của `Method.invoke` | Tham số thứ nhất trong `MethodType` | Vẫn là tham số thứ nhất trong ví dụ này |
| Chữ ký thao tác nhận `delta` | `Method.invoke(Object,Object...)`; member khai báo `add(long)` | `(Counter,long)long` | `(Counter,Integer)Long` |
| Đầu vào `Integer.valueOf(2)` | Hợp lệ qua unboxing + widening | Sai nếu gọi `invokeExact` với `Integer` | Hợp lệ qua chuyển đổi của `asType` |
| Giá trị trả về ở bên gọi | `Object` chứa `Long` | `long` | `Long` |
| Lỗi do phần thân `add` ném | Được bọc trong `InvocationTargetException` | Truyền ra theo cơ chế method handle | Truyền ra theo cơ chế method handle |
| Tra cứu/kiểm tra quyền | Lấy `Method` và kiểm tra theo hợp đồng reflection | `Lookup.findVirtual` kiểm tra quyền khi tạo handle | Dùng handle đã tạo hợp lệ, `asType` không cấp thêm quyền |

Đừng nhầm **kiểu khai báo của phương thức đích** với **kiểu tại điểm gọi**. Cả ba cuối cùng đều hướng tới `Counter.add(long)`. Điểm khác biệt nằm ở giao diện gọi bao quanh nó.

### Dòng chảy của cùng một giá trị

~~~text
Counter(40) + Integer(2)
            |
            +--> Method.invoke(counter, Integer(2))
            |      Integer -> int -> long
            |      Counter.add(2L) -> long 42 -> Long -> Object
            |
            +--> direct.invokeExact(counter, 2L)
            |      Chu ky phai dung: (Counter,long)long
            |      Counter.add(2L) -> long 42
            |
            +--> adapted.invokeExact(counter, Integer(2))
                   Chu ky adapter: (Counter,Integer)Long
                   Integer -> int -> long
                   Counter.add(2L) -> long 42 -> Long
~~~

Sơ đồ là mô hình chuyển đổi có thể quan sát theo hợp đồng; nó **không** khẳng định JVM nhất thiết tạo các đối tượng trung gian hoặc thực hiện mỗi bước bằng một lệnh máy riêng. JIT có thể tối ưu những bước mà ngữ nghĩa cho phép.

## 4. Ví dụ Java hoàn chỉnh dùng cùng một phương thức đích

Tạo file `SameBoundaryDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class SameBoundaryDemo {

    public static final class Counter {
        private final long base;

        public Counter(long base) {
            this.base = base;
        }

        public long add(long delta) {
            return Math.addExact(base, delta);
        }
    }

    private static final Method REFLECTION;
    private static final MethodHandle DIRECT;
    private static final MethodHandle ADAPTED;

    static {
        try {
            // Chu ky cua method dich: long add(long).
            REFLECTION = Counter.class.getMethod("add", long.class);

            MethodHandles.Lookup lookup = MethodHandles.lookup();

            // Handle instance: receiver la tham so dau tien.
            DIRECT = lookup.findVirtual(
                    Counter.class,
                    "add",
                    MethodType.methodType(long.class, long.class));

            // Adapter cho dau vao Integer va dau ra Long.
            ADAPTED = DIRECT.asType(
                    MethodType.methodType(
                            Long.class, Counter.class, Integer.class));

        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter(40L);
        Integer delta = Integer.valueOf(2);

        System.out.println("direct type=" + DIRECT.type());
        System.out.println("adapted type=" + ADAPTED.type());

        // 1. Reflection: Integer -> int -> long; ket qua Object/Long.
        Object reflected = REFLECTION.invoke(counter, delta);
        System.out.println("reflection=" + reflected
                + " (" + reflected.getClass().getSimpleName() + ")");

        // 2. invokeExact: bat buoc dung long tai diem goi.
        long exact = (long) DIRECT.invokeExact(counter, 2L);
        System.out.println("exact=" + exact);

        // 3. invokeExact tren adapter: nhan Integer, tra Long.
        Long adapted = (Long) ADAPTED.invokeExact(counter, delta);
        System.out.println("adapted=" + adapted);

        // 4. Sai chu ky tai diem goi DIRECT: Integer va Long.
        try {
            Long impossible = (Long) DIRECT.invokeExact(counter, delta);
            System.out.println(impossible);
        } catch (WrongMethodTypeException expected) {
            System.out.println("direct mismatch=WrongMethodTypeException");
        }

        // 5. Null cho tham so primitive qua reflection.
        try {
            REFLECTION.invoke(counter, (Object) null);
        } catch (IllegalArgumentException expected) {
            System.out.println("reflection null=IllegalArgumentException");
        }

        // 6. Null cho adapter: loi khi unbox Integer thanh primitive.
        try {
            Long impossible = (Long) ADAPTED.invokeExact(
                    counter, (Integer) null);
            System.out.println(impossible);
        } catch (NullPointerException expected) {
            System.out.println("adapter null=NullPointerException");
        }

        // 7. Ca ba duong goi cung den phan than bi tran so.
        Counter overflow = new Counter(Long.MAX_VALUE);

        try {
            REFLECTION.invoke(overflow, Integer.valueOf(1));
        } catch (InvocationTargetException expected) {
            System.out.println("reflection target="
                    + expected.getCause().getClass().getSimpleName());
        }

        try {
            long impossible = (long) DIRECT.invokeExact(overflow, 1L);
            System.out.println(impossible);
        } catch (ArithmeticException expected) {
            System.out.println("exact target=ArithmeticException");
        }

        try {
            Long impossible = (Long) ADAPTED.invokeExact(
                    overflow, Integer.valueOf(1));
            System.out.println(impossible);
        } catch (ArithmeticException expected) {
            System.out.println("adapter target=ArithmeticException");
        }
    }
}
~~~

Chương trình chỉ dùng API tiêu chuẩn. Chạy trên JDK hiện đại hỗ trợ Java 18:

~~~sh
javac SameBoundaryDemo.java
java SameBoundaryDemo
~~~

Kết quả dự kiến:

~~~text
direct type=(Counter,long)long
adapted type=(Counter,Integer)Long
reflection=42 (Long)
exact=42
adapted=42
direct mismatch=WrongMethodTypeException
reflection null=IllegalArgumentException
adapter null=NullPointerException
reflection target=ArithmeticException
exact target=ArithmeticException
adapter target=ArithmeticException
~~~

Phần hiển thị `direct type`/`adapted type` do `MethodType.toString()` tạo ra. Chữ ký thực tế có thể kiểm tra chắc chắn hơn bằng các phép so sánh kiểu tại mục tiếp theo; không cần phân tích chuỗi để điều khiển chương trình.

### Tại sao có cùng kết quả `42`?

Đầu vào khác dạng biểu thức ở từng đường gọi, nhưng cùng tạo giá trị `long 2` khi phương thức đích bắt đầu thực thi. `Counter.add(2L)` tính `40 + 2`.

Lời gọi reflection trả `Object` chứa `Long` do phương thức đích có kiểu trả về nguyên thủy `long`. Handle exact giữ kết quả nguyên thủy `long`. Adapter đã được yêu cầu kiểu kết quả `Long`, vì vậy kết quả được boxing theo cơ chế thích nghi.

### Vì sao `DIRECT.invokeExact(counter, delta)` không chạy?

`DIRECT.type()` là `(Counter,long)long`. Nhưng trong biểu thức:

~~~java
Long impossible = (Long) DIRECT.invokeExact(counter, delta);
~~~

`delta` có kiểu tĩnh `Integer` và kết quả ở điểm gọi được yêu cầu là `Long`. Chữ ký tại điểm gọi không khớp cả **tham số** lẫn **kiểu kết quả** của handle. `invokeExact` không thực hiện các chuyển đổi để sửa lỗi đó và ném `WrongMethodTypeException`.

**Quan trọng:** nếu thay `delta` bằng `2L` nhưng vẫn yêu cầu kết quả `Long`:

~~~java
// Van sai kieu: (Counter,long)Long khac (Counter,long)long.
// Long boxed = (Long) DIRECT.invokeExact(counter, 2L);
~~~

Lời gọi exact vẫn sai vì **kiểu trả về**. Cách đúng là:

~~~java
long value = (long) DIRECT.invokeExact(counter, 2L);
~~~

## 5. Đọc `type()` trước khi gọi và sau khi tạo adapter

Ta không cần đoán chữ ký. `MethodHandle.type()` trả về một `MethodType` bất biến chứa danh sách kiểu tham số và kiểu kết quả.

Với ví dụ trên:

~~~java
MethodType expectedDirect = MethodType.methodType(
        long.class, Counter.class, long.class);

MethodType expectedAdapted = MethodType.methodType(
        Long.class, Counter.class, Integer.class);

if (!DIRECT.type().equals(expectedDirect)) {
    throw new IllegalStateException("Direct handle khong dung chu ky");
}

if (!ADAPTED.type().equals(expectedAdapted)) {
    throw new IllegalStateException("Adapter khong dung chu ky");
}
~~~

`MethodType.methodType(returnType, parameterTypes...)` luôn đặt **kiểu trả về trước**, rồi mới đến các kiểu tham số. Với method instance, receiver là tham số đầu tiên của handle trực tiếp (`Counter.class`); với method static, handle không có receiver instance.

### Adapter `asType` thay đổi điều gì?

Dòng tạo adapter:

~~~java
MethodHandle adapted = DIRECT.asType(
        MethodType.methodType(Long.class, Counter.class, Integer.class));
~~~

có thể hiểu theo hợp đồng như sau:

| Giai đoạn | Kiểu | Hành vi |
| --- | --- | --- |
| Điểm gọi adapter | `(Counter,Integer)Long` | Caller phải khớp chữ ký **mới** khi dùng `invokeExact` |
| Đối số nhận vào | `Integer` | Unboxing thành `int`, rồi widening thành `long` cho target |
| Method đích | `(Counter,long)long` | Chạy `Counter.add(long)` |
| Kết quả method đích | `long` | Boxing thành `Long` cho caller |
| Đối tượng `DIRECT` ban đầu | `(Counter,long)long` | **Không đổi** vì `asType` trả về handle khác |

Nếu `asType` không thể thiết lập chuyển đổi theo quy tắc API, nó ném `WrongMethodTypeException` ngay khi **tạo adapter**. Nếu adapter tạo được nhưng **giá trị runtime** không chuyển đổi được, lỗi có thể chỉ xuất hiện **khi gọi adapter**.

Không phải mọi chuyển đổi Java đều được `asType` hỗ trợ. Hãy kiểm tra hợp đồng của `MethodHandle.asType` trên JDK đang dùng, đặc biệt khi kết hợp kiểu tham chiếu, boxing/unboxing, mở rộng hoặc thu hẹp kiểu số.

## 6. Cùng một `null`, nguyên nhân lỗi ở tầng khác nhau

Trên target `Counter.add(long)`, không có giá trị `long` tương ứng với `null`. Nhưng cách ba API biểu diễn tham số khiến lỗi bộc lộ khác nhau.

### Reflection

~~~java
REFLECTION.invoke(counter, (Object) null);
~~~

Dòng trên cố truyền **một đối số null** tới tham số nguyên thủy `long`. `Method.invoke` không thể unbox `null` cho kiểu nguyên thủy, nên báo `IllegalArgumentException` trước khi method đích bắt đầu chạy.

Tại đây, cast `(Object) null` là có chủ ý: `Method.invoke` bản thân là phương thức varargs với `Object...`. Nếu truyền `(Object[]) null` làm đối số cuối cùng, nó được hiểu theo nghĩa khác là **mảng đối số null**, không phải một phần tử đối số null.

### Handle chính xác

`DIRECT` yêu cầu tham số thứ hai có kiểu **`long`**. Một điểm gọi exact dùng biến `Integer` hoặc `null` không đúng kiểu sẽ bị chặn bởi chữ ký tại điểm gọi; không tồn tại một giá trị `long null`.

~~~java
// Sai chu ky exact: Integer khac long.
// long invalid = (long) DIRECT.invokeExact(counter, (Integer) null);
~~~

Sai lệch này thuộc tầng **`WrongMethodTypeException`**, không phải lỗi nghiệp vụ trong `Counter.add`.

### Handle có adapter

`ADAPTED` yêu cầu `Integer`, nên điểm gọi exact chấp nhận biểu thức có **kiểu tĩnh `Integer`**, kể cả khi giá trị runtime là `null`:

~~~java
Long invalid = (Long) ADAPTED.invokeExact(
        counter, (Integer) null);
~~~

Chữ ký điểm gọi **khớp adapter**; nhưng quá trình unbox `Integer null` thành số nguyên thủy trước khi gọi target dẫn đến `NullPointerException`.

Đây là ví dụ rõ ràng cho sự khác biệt giữa:

- **Khớp kiểu tại điểm gọi:** `handle.type()` so với chữ ký mà compiler tạo.
- **Chuyển đổi giá trị runtime:** dữ liệu có chuyển được qua adapter hay không.
- **Thực thi method đích:** method có được chạy và có ném lỗi riêng hay không.

### Bảng lỗi với input `null`

| Đường gọi | Kiểu được chấp nhận tại điểm gọi | Tầng gây lỗi |
| --- | --- | --- |
| `REFLECTION.invoke(counter, (Object) null)` | Giao diện reflection nhận `Object` | `IllegalArgumentException` do không chuyển `null` sang `long` |
| `DIRECT.invokeExact(counter, (Integer) null)` với kết quả `long` | Không khớp `(Counter,long)long` | `WrongMethodTypeException` |
| `ADAPTED.invokeExact(counter, (Integer) null)` với kết quả `Long` | Khớp `(Counter,Integer)Long` | `NullPointerException` trong bước unboxing của adapter |

Cả ba tình huống đều không chạy được tới phép cộng của `Counter.add` với một `long` hợp lệ.

## 7. Cùng một ngoại lệ nghiệp vụ, cách truyền lỗi khác nhau

Mã `Math.addExact(base, delta)` được chọn để tạo ra ngoại lệ dễ kiểm chứng khi tràn số:

~~~java
Counter overflow = new Counter(Long.MAX_VALUE);
~~~

Với `delta = 1`, phép cộng vượt giới hạn `long` và `Math.addExact` ném `ArithmeticException`.

Ba đường gọi đều chuyển dữ liệu thành `long 1` trước khi chạy method đích, nên lỗi nghiệp vụ về bản chất là một.

**Reflection:**

~~~java
try {
    REFLECTION.invoke(overflow, Integer.valueOf(1));
} catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    // cause la ArithmeticException do Math.addExact nem.
}
~~~

Theo hợp đồng `Method.invoke`, ngoại lệ do **phần thân method đích** ném được bọc trong `InvocationTargetException`. Bên gọi cần truy cập `getCause()` để thấy nguyên nhân.

**Handle chính xác:**

~~~java
try {
    long value = (long) DIRECT.invokeExact(overflow, 1L);
} catch (ArithmeticException ex) {
    // Loi tu Math.addExact duoc truyen ra truc tiep.
}
~~~

**Handle có adapter:**

~~~java
try {
    Long value = (Long) ADAPTED.invokeExact(
            overflow, Integer.valueOf(1));
} catch (ArithmeticException ex) {
    // Van la loi cua method dich, khong tu boc InvocationTargetException.
}
~~~

Việc `asType` chuyển đổi đối số và kết quả **không biến adapter thành `Method.invoke`**. Adapter theo `java.lang.invoke` không tự thực hiện kiểu bọc `InvocationTargetException` của core reflection.

### Không gộp chung các nguồn lỗi

| Nguồn lỗi | Ví dụ | Cách phân tích |
| --- | --- | --- |
| Tìm không đúng member | `getMethod("add", Integer.class)` cho member khai báo `long` | `NoSuchMethodException` khi tìm method bằng sai kiểu; reflection không dò overload theo dữ liệu runtime |
| Tra cứu handle không có quyền | `Lookup.findVirtual` với private member không được phép | `IllegalAccessException` tại bước tạo handle; adapter không mở rộng quyền |
| Sai chữ ký exact | `DIRECT.invokeExact(counter, delta)` với `delta` kiểu `Integer` | `WrongMethodTypeException` trước khi method đích chạy |
| Dữ liệu không chuyển đổi được | `ADAPTED.invokeExact(counter, (Integer) null)` | `NullPointerException` khi unbox trước target |
| Phương thức đích ném lỗi | `Math.addExact(Long.MAX_VALUE, 1L)` | Reflection bọc trong `InvocationTargetException`; method handle truyền lỗi đích ra |
| Receiver không hợp lệ | Truyền receiver sai kiểu cho instance member | Xem hợp đồng từng API: `Method.invoke` khác cơ chế kiểu của handle |

Từ ba kịch bản **đầu vào hợp lệ – null – overflow**, người học có thể quan sát các tầng lỗi mà không cần thay đổi mục tiêu gọi.

## 8. `invokeExact`, `invoke` và `asType`: phân biệt đúng

Trong ví dụ, ta chủ động tạo một adapter bằng `asType` rồi gọi `invokeExact`. Có một lựa chọn khác là gọi `invoke(...)` trực tiếp trên handle gốc.

`MethodHandle.invoke(...)` có thể thích nghi chữ ký điểm gọi bằng các chuyển đổi được hỗ trợ, về nguyên tắc tương tự cơ chế `asType`. Vì thế, với handle `DIRECT` kiểu `(Counter,long)long`:

~~~java
Counter c = new Counter(40L);
Integer input = Integer.valueOf(2);

// Co the thich nghi Integer -> long va long -> Object.
Object result = DIRECT.invoke(c, input);
System.out.println(result); // 42
~~~

Trong khi đó:

~~~java
// Sai neu giu Integer va yeu cau Object tai invokeExact.
// Object result = DIRECT.invokeExact(c, input);
~~~

Điểm khác biệt:

| Cách | Đặc điểm | Khi nào cân nhắc |
| --- | --- | --- |
| `DIRECT.invokeExact(c, 2L)` | Kiểu tại điểm gọi khớp chính xác handle gốc | Caller biết chắc chữ ký và muốn giao diện kiểu chặt |
| `DIRECT.invoke(c, input)` | Có thể thích nghi ngay tại điểm gọi theo quy tắc hỗ trợ | Caller biết cơ chế chuyển đổi và muốn dùng `invoke` |
| `ADAPTED.invokeExact(c, input)` | Adapter đã được tạo rõ ràng với kiểu cố định mới | Framework chuẩn hóa handle về hợp đồng chung, muốn tái sử dụng adapter |
| `REFLECTION.invoke(c, input)` | Dùng metadata `Method` và giao diện reflection | Cần khám phá hoặc thao tác member bằng reflection |

Trong cả hai cách dùng `invoke` hoặc adapter, **không được suy ra mọi giá trị đều chuyển đổi được**. Một điểm gọi hợp lệ theo kiểu tĩnh vẫn có thể thất bại khi giá trị thực tế không thể unbox/cast.

Một nguyên tắc hữu ích: **nếu đã tạo adapter, hãy đọc lại `adapter.type()` và gọi theo chữ ký mới**. Nếu không tạo adapter, hãy đọc `direct.type()` để xác nhận kỳ vọng của `invokeExact`.

## 9. Quyền truy cập và receiver không bị adapter thay đổi

Ta dùng `Counter` public và `add` public để tách riêng bài toán chuyển đổi kiểu. Trong ứng dụng thực tế, việc tìm thành viên còn phải tuân thủ quyền truy cập Java và ranh giới module.

### Reflection

~~~java
Method method = Counter.class.getMethod("add", long.class);
~~~

`getMethod` tìm public method phù hợp. Với các member không public, `getDeclaredMethod` có thể trả metadata nhưng `invoke` vẫn phải tuân thủ kiểm tra truy cập; `trySetAccessible()` chỉ có thể bật suppression trong những điều kiện JPMS cho phép.

### Method Handle

~~~java
MethodHandle direct = MethodHandles.lookup().findVirtual(
        Counter.class,
        "add",
        MethodType.methodType(long.class, long.class));
~~~

`Lookup.findVirtual` kiểm tra tên/chữ ký và năng lực truy cập của `Lookup` **khi tạo handle**. `MethodHandle.asType` chỉ chuyển đổi giao diện gọi của **handle đã tồn tại**; nó không giúp truy cập private member mà lookup ban đầu không được phép tìm.

### Receiver vẫn là receiver

Vì `add` là instance method, handle trực tiếp có tham số đầu tiên kiểu `Counter`; adapter của chúng ta cũng giữ tham số đầu tiên là `Counter`:

~~~text
DIRECT:  (Counter,long)long
ADAPTED: (Counter,Integer)Long
~~~

`asType` ở đây chỉ đổi kiểu của `delta` và kết quả. Nó **không cố định receiver**. Nếu muốn gắn một receiver có sẵn, có thể dùng `bindTo(counter)` trên handle phù hợp; sau đó handle mới sẽ có chữ ký ít hơn một tham số và phải được kiểm tra lại bằng `type()`.

Reflection dùng tham số receiver riêng trong `Method.invoke`. Khi chuyển một phần mã từ reflection sang Method Handle, đây là điểm dễ gây sai số lượng và thứ tự đối số.

## 10. Cách kiểm chứng có kỷ luật trên JDK đang dùng

Bài học không yêu cầu benchmark, nhưng cần kiểm chứng **hành vi** thay vì suy đoán từ tên API.

Một quy trình thực tế:

1. Cố định **một** method đích và **một** receiver để tránh thay đổi nghiệp vụ trong khi so sánh.
2. Ghi `REFLECTION.getParameterTypes()` cùng `DIRECT.type()` và `ADAPTED.type()`; xác nhận `long.class` khác `Integer.class`.
3. Kiểm chứng đầu vào hợp lệ `Integer.valueOf(2)` để thấy cả ba đường gọi cho cùng kết quả số học.
4. Kiểm chứng sai chữ ký `invokeExact`; phân biệt lỗi do **method type** và lỗi chuyển đổi giá trị.
5. Kiểm chứng `null` để thấy reflection báo `IllegalArgumentException` còn adapter gặp `NullPointerException` khi unbox.
6. Kiểm chứng tràn số để so `InvocationTargetException.getCause()` với `ArithmeticException` truyền trực tiếp.
7. Nếu chạy trong named module hoặc truy cập thành viên không public, thêm phép thử về quyền lookup/`opens` riêng, tránh lẫn vào kết quả chuyển đổi.
8. Ghi rõ JDK runtime đang chạy, ví dụ `java -version`, khi báo cáo kết quả kiểm chứng.

### Nếu cần so sánh hiệu năng

JEP 416 của Java 18 cho biết core reflection dùng cơ chế dựa trên method handles trong phần triển khai JDK. Điều này **không** có nghĩa `Method.invoke` và `MethodHandle.invokeExact` có cùng hợp đồng, cũng không bảo đảm một API luôn nhanh hơn API khác.

Để đo tốc độ, hãy dùng phép thử microbenchmark phù hợp (thường là JMH), tách chi phí **tra cứu member**, **tạo adapter**, **gọi member**, **boxing/unboxing** và **phần thân method**. Cần warmup, fork và dữ liệu đủ đại diện. Ví dụ `SameBoundaryDemo` ở trên chỉ được thiết kế để so sánh **ngữ nghĩa và lỗi**.

## 11. Các kết luận dễ nhầm

| Nhận định | Điều đúng theo hợp đồng |
| --- | --- |
| “`Integer` truyền được vào reflection thì phải truyền được nguyên dạng vào `invokeExact`.” | Không. `invokeExact` cần chữ ký tại điểm gọi khớp `handle.type()`. |
| “Adapter `asType` sửa chữ ký của handle ban đầu.” | Không. Nó trả về handle khác; `DIRECT.type()` không đổi. |
| “`asType` tạo được rồi thì truyền bất cứ giá trị nào cũng thành công.” | Không. Giá trị runtime vẫn có thể lỗi khi unbox/cast, ví dụ `null`. |
| “Reflection bọc lỗi nào cũng trong `InvocationTargetException`.” | Không. Lỗi do **phần thân method đích** ném được bọc; lỗi receiver/đối số có thể xảy ra trực tiếp ở `invoke`. |
| “`invokeExact` phải tự unbox `Integer` vì method đích nhận `long`.” | Không. Phải gọi chính xác kiểu `long` hoặc tạo/gọi một đường thích nghi có chủ đích. |
| “Dùng `asType` sẽ bypass private access.” | Không. Quyền tạo handle đã được kiểm tra theo `Lookup`; adapter không cấp quyền mới. |
| “Ba lời gọi trả `42` nên chi phí và cơ chế thực thi giống nhau.” | Không. Kết quả nghiệp vụ giống nhau không nói gì về chi phí adapter, boxing, JIT hay đường triển khai. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `DIRECT.type()` là `(Counter,long)long`. Vì sao `Long x = (Long) DIRECT.invokeExact(counter, Integer.valueOf(2))` lỗi?

**Trả lời:** Chữ ký tại điểm gọi là `(Counter,Integer)Long`, không trùng `(Counter,long)long`. `invokeExact` báo `WrongMethodTypeException` mà không tự unbox/widen/box.

**Câu 2.** Vì sao `REFLECTION.invoke(counter, Integer.valueOf(2))` có thể trả `42`?

**Trả lời:** `Method.invoke` chấp nhận chuyển đổi từ `Integer` qua unboxing thành `int` và widening thành `long` cho tham số đích, rồi boxing kết quả `long` thành `Long` trong `Object` trả về.

**Câu 3.** Adapter `(Counter,Integer)Long` có bảo đảm `ADAPTED.invokeExact(counter, (Integer) null)` thành công không?

**Trả lời:** Không. Điểm gọi khớp **kiểu tĩnh**, nhưng giá trị `null` không thể unbox thành primitive, nên việc chuyển đổi của adapter gây `NullPointerException`.

**Câu 4.** Vì sao lỗi tràn số có tên giống nhau ở đầu ra của chương trình dù đường reflection dùng `InvocationTargetException`?

**Trả lời:** Chương trình lấy `getCause()` của `InvocationTargetException` để in tên ngoại lệ gốc. Method Handle truyền `ArithmeticException` do method đích ném trực tiếp ra cho bên gọi; tên ngoại lệ gốc đều là `ArithmeticException`.

**Câu 5.** Nếu dùng `bindTo(counter)` trên `DIRECT`, có thể gọi `invokeExact(counter, 2L)` trên handle mới không?

**Trả lời:** Không. Sau khi bind receiver, handle mới có kiểu `(long)long`; receiver đã được cố định và không còn là một tham số tại điểm gọi.

**Câu 6.** Có thể dùng `asType` để gọi private method mà `Lookup.findVirtual` đã từ chối không?

**Trả lời:** Không. Không có handle hợp lệ để chuyển đổi, và `asType` không cấp thêm quyền. Cần sửa thiết kế quyền truy cập hoặc sử dụng API public.

## Ghi nhớ

- **Cùng phương thức `Counter.add(long)` có thể cho cùng kết quả nghiệp vụ nhưng đi qua ba hợp đồng gọi khác nhau.**
- Reflection tự áp dụng một số chuyển đổi invocation và trả kết quả kiểu `Object`; lỗi từ method đích được bọc trong `InvocationTargetException`.
- `invokeExact` yêu cầu chữ ký điểm gọi khớp **đúng từng kiểu tham số và kiểu kết quả** trong `MethodHandle.type()`.
- `asType` tạo một **handle mới** với chữ ký khác khi chuyển đổi được hỗ trợ; giá trị runtime vẫn phải phù hợp khi gọi adapter.
- Hãy phân biệt rõ **lỗi tra cứu/quyền**, **lỗi kiểu điểm gọi**, **lỗi chuyển đổi dữ liệu** và **ngoại lệ trong method đích**.
- Java 18 với JEP 416 thay đổi triển khai core reflection; không xóa đi những khác biệt có thể quan sát của API reflection và Method Handle trên JDK hiện đại.

**Tài liệu đối chiếu:** [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416); Javadoc `java.lang.reflect.Method.invoke`, `java.lang.reflect.InvocationTargetException`; `java.lang.invoke.MethodHandle` (`invokeExact`, `invoke`, `asType`, `type`), `MethodType` và `MethodHandles.Lookup` trên đúng phiên bản JDK triển khai.
