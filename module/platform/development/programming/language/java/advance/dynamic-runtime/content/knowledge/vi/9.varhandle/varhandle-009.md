# 9.9 withInvokeExactBehavior, withInvokeBehavior và chuyển sang MethodHandle

## 1. Tổng quan và mục tiêu

`VarHandle` trong `java.lang.invoke` là đối tượng tham chiếu có kiểu mạnh đến **một biến** hoặc **một họ biến**: instance field, static field, phần tử mảng, hoặc vùng dữ liệu do factory thích hợp tạo ra. Khác với một method thông thường, VarHandle có nhiều **access mode**: `get`, `set`, `getVolatile`, `setRelease`, `compareAndSet`, `getAndAdd`… Mỗi mode có chữ ký runtime riêng.

Bài này đi sâu ba API:

- **`withInvokeExactBehavior()`:** tạo một VarHandle cùng tham chiếu đến các biến cũ nhưng yêu cầu **chữ ký lời gọi khớp chính xác** với access-mode type.
- **`withInvokeBehavior()`:** tạo VarHandle cùng biến đích nhưng cho phép **chuyển kiểu tương thích** theo semantics của `MethodHandle.invoke`.
- **`toMethodHandle(VarHandle.AccessMode)`:** chuyển một thao tác access mode thành **MethodHandle đã bind VarHandle**, phù hợp để ghép vào pipeline động.

Các API `withInvokeExactBehavior`, `withInvokeBehavior`, `hasInvokeExactBehavior` được bổ sung từ **Java 16** và hoạt động trên **Java 17+**. `VarHandle` cùng phương thức `toMethodHandle` xuất hiện từ Java 9.

Sau bài học, bạn có thể giải thích chính xác `WrongMethodTypeException`, phân biệt quyền truy cập và lỗi chữ ký, xác định `MethodType` cho GET/SET/CAS của instance/static/array, chuyển VarHandle thành MethodHandle đúng cách, và tránh hiểu lầm rằng exact behavior làm tăng mức đồng bộ bộ nhớ.

## 2. Bản chất chữ ký: variable type, coordinate types và access mode

VarHandle không chỉ trỏ tới kiểu dữ liệu `T` mà còn định nghĩa các **tọa độ (coordinates)** cần truyền để chọn chính xác biến đích:

- `vh.varType()`: kiểu biến `T`; ví dụ `int.class`.
- `vh.coordinateTypes()`: các kiểu tham số xác định vị trí biến; ví dụ `Counter.class` cho instance field, hoặc `int[].class` và `int.class` cho phần tử mảng.
- `vh.accessModeType(mode)`: `MethodType` mô tả **chữ ký của thao tác** `mode`, gồm tọa độ, các giá trị bổ sung và kiểu trả về.
- `vh.isAccessModeSupported(mode)`: cho biết thao tác cụ thể có được hỗ trợ trên biến đó không.

Nếu biến kiểu `T` có tọa độ `CT1,...,CTn` thì:

```text
AccessMode.GET:             (CT1,...,CTn)T
AccessMode.SET:             (CT1,...,CTn,T)void
AccessMode.GET_AND_ADD:     (CT1,...,CTn,T)T         [nếu hỗ trợ]
AccessMode.COMPARE_AND_SET: (CT1,...,CTn,T,T)boolean [nếu hỗ trợ]
```

Ví dụ với biến kiểu `int`:

| Nguồn VarHandle | `coordinateTypes()` | Kiểu GET | Kiểu SET | Kiểu COMPARE_AND_SET |
| --- | --- | --- | --- | --- |
| Instance field `Counter.value` | `[Counter]` | `(Counter)int` | `(Counter,int)void` | `(Counter,int,int)boolean` |
| Static field `total` | `[]` | `()int` | `(int)void` | `(int,int)boolean` |
| Phần tử `int[]` | `[int[], int]` | `(int[],int)int` | `(int[],int,int)void` | `(int[],int,int,int)boolean` |

**Điểm cần nắm:** receiver instance object là một **tọa độ**, không phải một VarHandle khác. Static field không cần receiver; array element cần **array và index**. Thứ tự tham số và kiểu trả về là một phần của contract.

Access-mode methods như `get(Object... args)` hay `set(Object... args)` có chữ ký **signature-polymorphic**. Compiler ghi lại kiểu thực của đối số và kiểu kết quả ở **call site**; JVM đối chiếu descriptor đã biên dịch với access-mode type. Vì vậy `(int) vh.get(counter)` và `(long) vh.get(counter)` có hai return descriptor khác nhau dù cùng đọc một trường int.

## 3. `withInvokeBehavior()`: chuyển kiểu tương thích

Cú pháp:

```java
VarHandle flexible = original.withInvokeBehavior();
boolean exact = flexible.hasInvokeExactBehavior(); // false
```

Đoạn trên minh họa khi `original` là VarHandle hợp lệ và đã import `java.lang.invoke.VarHandle`. API trả một view dùng **cùng biến đích**, với cơ chế kiểm tra kiểu như `MethodHandle.invoke`: call-site descriptor được **adapt** về access-mode type khi phép chuyển phù hợp với quy tắc `asType`.

Ví dụ biến kiểu `int`:

- Truyền `short` khi SET có thể chuyển `short → int`.
- Đọc `int` vào call site mong đợi `long` có thể chuyển `int → long`.
- Truyền `long` để ghi `int` **không** được mặc nhiên thu hẹp kiểu, vì narrowing primitive không phải một phép chuyển tự động an toàn được `asType` cho phép.
- Reference cast/unbox/box có thể được hỗ trợ khi tương thích nhưng vẫn có thể ném `ClassCastException` hoặc `NullPointerException` tùy giá trị.
- Chế độ này **không** làm biến mất tọa độ hoặc chấp nhận số lượng tham số sai tùy ý; `WrongMethodTypeException` vẫn xuất hiện khi không thể adapt.

Theo đặc tả Java 17, access-mode invocation của VarHandle **mặc định** có invoke behavior. Gọi `withInvokeBehavior()` giúp bạn công bố rõ semantics và bảo đảm `hasInvokeExactBehavior() == false`. Nếu VarHandle hiện tại đã ở invoke behavior, phương thức trả lại chính VarHandle đó.

Đây là cơ chế chuyển đổi **ở ranh giới lời gọi**, không phải thay kiểu lưu trữ của field hay chuyển `SET` thành atomic update.

## 4. `withInvokeExactBehavior()`: kiểm tra khớp chữ ký tuyệt đối

Cú pháp:

```java
VarHandle exact = original.withInvokeExactBehavior();
boolean strict = exact.hasInvokeExactBehavior(); // true
```

Lúc gọi access mode trên `exact`, descriptor ở call site **phải trùng** `exact.accessModeType(mode)`. Ví dụ `Counter.value` là instance field int có các chữ ký:

```text
GET -> (Counter)int
SET -> (Counter,int)void
```

Do đó:

```java
// Trích đoạn trong phương thức đã có Counter c và VarHandle exact:
exact.set(c, 8);                   // (Counter,int)void: đúng
int n = (int) exact.get(c);        // (Counter)int: đúng
// exact.set(c, (short) 8);        // (Counter,short)void: sai
// long wrong = (long) exact.get(c);  // (Counter)long: sai
```

Hai câu bị comment có thể ném `WrongMethodTypeException` **khi gọi**, không phải khi tạo VarHandle. Mặc dù `short` có thể widen thành int theo Java, invoke-exact **không thực hiện** conversion ấy. Return descriptor cũng cần đúng: `int → long` phải nằm **ngoài lời gọi**, chẳng hạn:

```java
int x = (int) exact.get(c);
long widened = x; // Java widening sau khi lời gọi exact đã thành công
```

**Lưu ý với return value:** khi access mode GET trả int, việc gọi `exact.get(c)` như một statement không lấy kết quả có thể khiến call site mang return type `void`, không trùng `int`. Hãy dùng cast/assignment thể hiện chính xác kiểu trả về.

Bảng so sánh:

| Thuộc tính | `withInvokeBehavior()` | `withInvokeExactBehavior()` |
| --- | --- | --- |
| `hasInvokeExactBehavior()` | `false` | `true` |
| `short` ghi vào `int` | Có thể widen thành int | Không khớp nên ném `WrongMethodTypeException` |
| Lấy `int` thành `long` | Có thể widen kết quả | Không khớp return descriptor |
| Số tọa độ | Vẫn phải đủ/đúng vị trí | Vẫn phải đủ/đúng vị trí |
| Thao tác nguyên tử/memory ordering | Không đổi | Không đổi |
| Quyền truy cập field | Không được cấp thêm | Không được cấp thêm |
| Dùng khi | API động cần chuyển kiểu hợp lệ | Pipeline cố định chữ ký, fail sớm nếu sai contract |

Các biến thể là **view cùng tập biến**, không tự sao chép dữ liệu. VarHandle không cho phép người dùng thay đổi trạng thái hành vi quan sát được của object gốc; việc tạo view exact không khiến view flexible trước đó tự biến thành exact.

## 5. Ví dụ Java 17 số 1 — so sánh gọi linh hoạt và gọi exact

Lưu file **`VarHandleBehaviorDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleBehaviorDemo {
    static final class Counter {
        int value;
    }

    public static void main(String[] args) throws Throwable {
        VarHandle base = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        VarHandle flexible = base.withInvokeBehavior();
        VarHandle exact = base.withInvokeExactBehavior();

        Counter c = new Counter();

        System.out.println("flexible exact? "
                + flexible.hasInvokeExactBehavior());
        System.out.println("exact exact? "
                + exact.hasInvokeExactBehavior());
        System.out.println("same variable type: "
                + (exact.varType() == flexible.varType()));
        System.out.println("get type: "
                + exact.accessModeType(VarHandle.AccessMode.GET));
        System.out.println("set type: "
                + exact.accessModeType(VarHandle.AccessMode.SET));

        flexible.set(c, (short) 7);
        System.out.println("flexible short set: "
                + (int) flexible.get(c));

        long widened = (long) flexible.get(c);
        System.out.println("flexible long get: " + widened);

        try {
            exact.set(c, (short) 8);
            System.out.println("unexpected success");
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact short set: rejected");
        }

        exact.set(c, 8);
        System.out.println("exact int set: "
                + (int) exact.get(c));

        try {
            long unexpected = (long) exact.get(c);
            System.out.println("unexpected long: " + unexpected);
        } catch (WrongMethodTypeException expected) {
            System.out.println("exact long get: rejected");
        }

        System.out.println("base unchanged mode: "
                + base.hasInvokeExactBehavior());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 VarHandleBehaviorDemo.java
java VarHandleBehaviorDemo
```

Stdout:

```text
flexible exact? false
exact exact? true
same variable type: true
get type: (Counter)int
set type: (Counter,int)void
flexible short set: 7
flexible long get: 7
exact short set: rejected
exact int set: 8
exact long get: rejected
base unchanged mode: false
```

Giải thích:

1. `findVarHandle` tìm đúng field và kiểm tra quyền ở lúc tạo; mode behavior **không** quyết định field có tồn tại hay không.
2. `flexible.set(c, (short) 7)` dùng call site `(Counter,short)void`, được widen thành `(Counter,int)void`. `(long) flexible.get(c)` cũng được widen return type.
3. `exact.set(c, (short) 8)` và `(long) exact.get(c)` không trùng descriptor chính xác nên bị từ chối.
4. `exact.set(c, 8)` và `(int) exact.get(c)` thành công, sửa/đọc chính field mà flexible tham chiếu.
5. `base.hasInvokeExactBehavior()` không bị thay đổi do tạo view `exact`.

Vì chương trình chạy một thread, kết quả cố định. Trong code nhiều thread, việc chọn exact không làm thay đổi những memory semantics vốn có của access mode GET/SET.

## 6. `toMethodHandle(AccessMode)`: chuyển thao tác thành MethodHandle đã bind

Cú pháp:

```java
MethodHandle read = vh.toMethodHandle(VarHandle.AccessMode.GET);
```

API tạo `MethodHandle` **đã gắn với chính VarHandle `vh` và mode GET**. Về hành vi, nó tương đương tạo invoker exact cho `vh.accessModeType(GET)`, rồi bind đối số VarHandle đầu tiên; implementation có thể tối ưu khác.

**Chữ ký kết quả bằng `vh.accessModeType(mode)`**, không có đối số VarHandle thừa:

| Nguồn biến | `GET` handle | `SET` handle | `COMPARE_AND_SET` handle |
| --- | --- | --- | --- |
| Instance field `int Counter.value` | `(Counter)int` | `(Counter,int)void` | `(Counter,int,int)boolean` |
| Static field `int total` | `()int` | `(int)void` | `(int,int)boolean` |
| Array element `int[]` | `(int[],int)int` | `(int[],int,int)void` | `(int[],int,int,int)boolean` |

Ví dụ với array:

```java
VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
MethodHandle get = vh.toMethodHandle(VarHandle.AccessMode.GET);
boolean same = get.type().equals(
        vh.accessModeType(VarHandle.AccessMode.GET)); // true
```

Đoạn trên là minh họa nằm trong phương thức đã import `MethodHandles`, `VarHandle` và `MethodHandle`. VarHandle của `int[]` dùng coordinate types `(int[],int)`, nên GET handle có kiểu `(int[],int)int`.

### 6.1. Sau khi chuyển đổi: hai phương thức invoke của MethodHandle vẫn độc lập

**Đây là điểm quan trọng nhất khi kết hợp hai API:**

- `withInvokeBehavior()` / `withInvokeExactBehavior()` quyết định việc gọi **access-mode method trực tiếp trên VarHandle** như `vh.get(...)`, `vh.set(...)`.
- `MethodHandle.invoke(...)` có conversion phù hợp theo contract của MethodHandle.
- `MethodHandle.invokeExact(...)` **luôn exact** theo `mh.type()`, dù `mh` được tạo từ một VarHandle flexible.

Ví dụ `mh = vh.withInvokeBehavior().toMethodHandle(GET)` có kiểu `(int[],int)int`. Gọi `mh.invoke(data, (short) 1)` có thể widen index từ short sang int. Nhưng `mh.invokeExact(data, (short) 1)` **không khớp**, vẫn ném `WrongMethodTypeException`.

Tương tự, lấy `mh` từ `vh.withInvokeExactBehavior()` không khiến `mh.invoke(...)` mất khả năng chuyển kiểu của chính nó. Exact behavior của VarHandle **không thay đổi chữ ký hay semantics của API invoke/invokeExact ở MethodHandle**.

### 6.2. Không truyền thêm VarHandle sau khi đã bind

Sai:

```java
// Mã minh họa SAI khi get đã từ vh.toMethodHandle(GET):
// int x = (int) get.invokeExact(vh, data, 1);
```

Đúng:

```java
// Mã minh họa ĐÚNG khi get.type() là (int[],int)int:
int x = (int) get.invokeExact(data, 1);
```

Dù `get` truy cập biến thông qua một VarHandle, chính object VarHandle đã được **bind bên trong** method handle. Chỉ những coordinate types của biến còn lại trong chữ ký. Mã trên là trích đoạn, cần biến `get` và mảng `data` đã khai báo.

## 7. Ví dụ Java 17 số 2 — chuyển GET, SET, GET_AND_ADD, COMPARE_AND_SET

Lưu file **`VarHandleBridgeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;

public class VarHandleBridgeDemo {
    public static void main(String[] args) throws Throwable {
        int[] data = {10, 20};
        VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);

        MethodHandle get =
                vh.toMethodHandle(VarHandle.AccessMode.GET);
        MethodHandle set =
                vh.toMethodHandle(VarHandle.AccessMode.SET);
        MethodHandle add =
                vh.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);
        MethodHandle cas =
                vh.toMethodHandle(VarHandle.AccessMode.COMPARE_AND_SET);

        System.out.println("coords: " + vh.coordinateTypes());
        System.out.println("get type: " + get.type());
        System.out.println("set type: " + set.type());
        System.out.println("add type: " + add.type());
        System.out.println("cas type: " + cas.type());
        System.out.println("accessModeType agrees: "
                + get.type().equals(
                        vh.accessModeType(VarHandle.AccessMode.GET)));

        System.out.println("get exact: "
                + (int) get.invokeExact(data, 1));
        set.invokeExact(data, 1, 25);
        System.out.println("set exact: " + data[1]);

        System.out.println("get invoke short index: "
                + (int) get.invoke(data, (short) 1));

        try {
            int ignored = (int) get.invokeExact(data, (short) 1);
            System.out.println("unexpected: " + ignored);
        } catch (WrongMethodTypeException expected) {
            System.out.println("mh invokeExact short index: rejected");
        }

        System.out.println("getAndAdd previous: "
                + (int) add.invokeExact(data, 1, 5));
        System.out.println("compareAndSet success: "
                + (boolean) cas.invokeExact(data, 1, 30, 31));
        System.out.println("final value: " + data[1]);

        VarHandle exactVH = vh.withInvokeExactBehavior();
        MethodHandle exactGet =
                exactVH.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("same mh type after exact: "
                + exactGet.type().equals(get.type()));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 VarHandleBridgeDemo.java
java VarHandleBridgeDemo
```

Stdout:

```text
coords: [class [I, int]
get type: (int[],int)int
set type: (int[],int,int)void
add type: (int[],int,int)int
cas type: (int[],int,int,int)boolean
accessModeType agrees: true
get exact: 20
set exact: 25
get invoke short index: 25
mh invokeExact short index: rejected
getAndAdd previous: 25
compareAndSet success: true
final value: 31
same mh type after exact: true
```

**Phân tích output:**

- `coords: [class [I, int]` là cách `Class.toString()` biểu diễn `int[].class` (ký hiệu JVM `[I`) và `int.class`. Đây là tọa độ **mảng + index**, không phải những giá trị mảng cụ thể.
- GET handle đọc phần tử index 1: 20. SET handle ghi 25 vào cùng vị trí.
- `get.invoke(data, (short) 1)` thành công nhờ conversion của **MethodHandle.invoke**; `get.invokeExact(data, (short) 1)` bị từ chối vì index bắt buộc là int.
- `GET_AND_ADD` tăng phần tử từ 25 lên 30, trả giá trị cũ **25**. CAS kỳ vọng 30, đổi thành 31 và trả true.
- `exactVH.toMethodHandle(GET)` có kiểu giống `vh.toMethodHandle(GET)`; behavior của VarHandle không đổi chữ ký của MethodHandle được tạo.

Khi dùng `invokeExact`, kiểu return cũng phải đúng: `(int) get.invokeExact(...)` với GET int, `(boolean) cas.invokeExact(...)` với CAS; SET trả void nên được gọi như một statement.

## 8. Ví dụ Java 17 số 3 — static field và read-only final field

`toMethodHandle` không tự biến một mode không được hỗ trợ thành thao tác hợp lệ. `VarHandle.isAccessModeSupported(mode)` cần được kiểm tra riêng: với field `final`, GET được phép nhưng các mode ghi/atomic update như SET không được hỗ trợ.

Tạo file **`VarHandleBoundaryDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleBoundaryDemo {
    static int total = 4;

    static final class Record {
        final int code = 42;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle totalVH = lookup.findStaticVarHandle(
                VarHandleBoundaryDemo.class, "total", int.class);
        MethodHandle load =
                totalVH.toMethodHandle(VarHandle.AccessMode.GET);
        MethodHandle update =
                totalVH.toMethodHandle(VarHandle.AccessMode.GET_AND_ADD);

        System.out.println("static coordinates: "
                + totalVH.coordinateTypes().size());
        System.out.println("static get type: " + load.type());
        System.out.println("static add type: " + update.type());
        System.out.println("static before: " + (int) load.invokeExact());
        System.out.println("static previous: "
                + (int) update.invokeExact(3));
        System.out.println("static after: " + (int) load.invokeExact());

        VarHandle finalVH = lookup.findVarHandle(
                Record.class, "code", int.class);
        System.out.println("final GET supported: "
                + finalVH.isAccessModeSupported(VarHandle.AccessMode.GET));
        System.out.println("final SET supported: "
                + finalVH.isAccessModeSupported(VarHandle.AccessMode.SET));

        MethodHandle readFinal =
                finalVH.toMethodHandle(VarHandle.AccessMode.GET);
        System.out.println("final code: "
                + (int) readFinal.invokeExact(new Record()));

        try {
            MethodHandle writeFinal =
                    finalVH.toMethodHandle(VarHandle.AccessMode.SET);
            writeFinal.invokeExact(new Record(), 9);
            System.out.println("unexpected");
        } catch (UnsupportedOperationException expected) {
            System.out.println("final write: unsupported");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 VarHandleBoundaryDemo.java
java VarHandleBoundaryDemo
```

Stdout:

```text
static coordinates: 0
static get type: ()int
static add type: (int)int
static before: 4
static previous: 4
static after: 7
final GET supported: true
final SET supported: false
final code: 42
final write: unsupported
```

**Giải thích:**

- Static field `total` không cần receiver, nên GET handle là `()int`, GET_AND_ADD handle là `(int)int`; tham số duy nhất của GET_AND_ADD là **delta**. Nó trả giá trị cũ 4, sau đó total là 7.
- Với `Record.code`, GET vẫn có chữ ký `(Record)int` vì cần receiver; field `final` được đọc bình thường.
- Dù có thể mô tả kiểu SET hợp lệ về cú pháp `(Record,int)void`, mode SET không được hỗ trợ với final field. Khi invoke sẽ gặp `UnsupportedOperationException`, **không phải** `WrongMethodTypeException` do sai chữ ký.

Không dùng `withInvokeBehavior` hay `withInvokeExactBehavior` để cố phá quy tắc final. Các view đó không mở quyền truy cập bị cấm hoặc biến field read-only thành writable.

## 9. So sánh với `varHandleInvoker` và `varHandleExactInvoker`

Ngoài `toMethodHandle` còn có hai factory ở lớp `MethodHandles`:

- `varHandleExactInvoker(mode, methodType)` tạo MethodHandle điều phối access mode với **chữ ký exact**.
- `varHandleInvoker(mode, methodType)` tạo MethodHandle điều phối với **invoke behavior**, có thể thích ứng chữ ký theo quy tắc API.

Khác biệt quan trọng là **binding**:

| API | Có bind một VarHandle cụ thể? | Tham số đầu tiên của handle |
| --- | --- | --- |
| `vh.toMethodHandle(GET)` | Có | Tọa độ đầu tiên, nếu có |
| `MethodHandles.varHandleExactInvoker(GET, type)` | Chưa | `VarHandle`, rồi đến tọa độ |
| `MethodHandles.varHandleInvoker(GET, type)` | Chưa | `VarHandle`, rồi đến tọa độ |

Ví dụ `vh` cho phần tử `int[]` có GET type `(int[],int)int`. `vh.toMethodHandle(GET)` cho handle nhận **2 tham số** (mảng, index); invoker chưa bind nhận **3 tham số** (VarHandle, mảng, index).

Về hành vi, `toMethodHandle(mode)` tương đương một exact invoker cho `vh.accessModeType(mode)` đã được bind với `vh` (có thể được JVM tối ưu khác). Nó thuận tiện khi pipeline cần gọi **một biến/nguồn dữ liệu đã chọn**. Invoker chưa bind phù hợp khi một bộ điều phối chung cần nhận nhiều VarHandle có chữ ký tương thích.

**Không nhầm hai lớp API:** `withInvokeExactBehavior` đổi semantics của **VarHandle access-mode invocation**, còn `MethodHandle.invokeExact` là quy tắc riêng của **MethodHandle**. Cả hai cùng khái niệm “exact” nhưng tác động lên hai loại lời gọi khác nhau.

### 9.1. Vì sao không dùng Reflection `Method.invoke` trên `VarHandle.get`?

Các access-mode methods được biểu diễn đặc biệt trong bytecode. Nếu bạn phản chiếu `VarHandle.class.getDeclaredMethod("get", Object[].class)` rồi cố `Method.invoke`, đó **không** tương đương cú pháp signature-polymorphic `vh.get(...)`. Javadoc mô tả phản chiếu access-mode methods như các phương thức thay thế nhằm mục đích trình bày; gọi theo cơ chế Reflection thường dẫn đến `UnsupportedOperationException`.

Để dùng VarHandle trong hệ thống động, nên gọi trực tiếp access-mode method hoặc lấy `MethodHandle` qua `toMethodHandle` hay invoker tương ứng. Không dùng Reflection của phương thức `get` trên chính lớp `VarHandle` làm một workaround.

## 10. Ghép MethodHandle sau chuyển đổi

Khi đã có một handle từ VarHandle, bạn có thể dùng các combinator:

- `insertArguments` để **bind tọa độ**, ví dụ array và index;
- `filterArguments` để biến đổi input trước khi đi vào thao tác SET;
- `filterReturnValue` để biến đổi kết quả GET;
- `guardWithTest` để chọn nhánh đọc/ghi hoặc fallback;
- `asType` để làm rõ chuyển đổi có thể chấp nhận tại một ranh giới của pipeline.

Ví dụ **trích đoạn minh họa**, giả định `read` là MethodHandle `(int[],int)int` ở mục 7 và `data` là `int[]`:

```java
MethodHandle getIndexZero = MethodHandles.insertArguments(
        read, 0, data, 0);
// getIndexZero.type() là ()int
int first = (int) getIndexZero.invokeExact();
```

`insertArguments` đã bind **tham chiếu mảng và chỉ số 0**, không bind giá trị phần tử. Nếu phần tử index 0 đổi, lần gọi `getIndexZero` sau có thể đọc giá trị mới theo memory semantics của mode GET. Chữ ký cuối thành `()int`.

**Đừng nhầm** việc bind tọa độ với việc sao chép một snapshot dữ liệu. MethodHandle giữ capability truy cập mảng đã bind; object mảng vẫn có thể thay đổi và cần quản lý đồng thời khi chia sẻ nhiều thread.

## 11. Exact behavior không phải một chế độ đồng bộ bộ nhớ

VarHandle có các access mode với memory semantics riêng:

- `GET`/`SET`: đọc/ghi plain.
- `GET_OPAQUE`/`SET_OPAQUE`: opaque access với bảo đảm tương ứng.
- `GET_ACQUIRE`/`SET_RELEASE`: acquire/release ordering.
- `GET_VOLATILE`/`SET_VOLATILE`: volatile semantics.
- `COMPARE_AND_SET`/`GET_AND_ADD`: các atomic update khi biến hỗ trợ.

**`withInvokeExactBehavior` không biến `GET` thành `GET_VOLATILE`**, và `toMethodHandle(GET)` không tạo atomic read-modify-write. Để có volatile read dưới dạng MethodHandle, chọn **`toMethodHandle(AccessMode.GET_VOLATILE)`**.

Việc ghép adapter vào `MethodHandle` cũng không tự nâng memory ordering. Nếu thuật toán concurrency đòi release/acquire hoặc CAS, chọn đúng mode và kiểm thử trên nhiều thread theo Java Memory Model.

Ngược lại, exact type checking có thể giúp phát hiện **lỗi chữ ký**, nhưng không bảo đảm tránh **data race**, lỗi index, receiver null hoặc access mode bị unsupported. Đó là các loại hợp đồng khác nhau.

## 12. Phân biệt lỗi: kiểu, hỗ trợ mode và quyền truy cập

| Lỗi hoặc triệu chứng | Nguyên nhân | Xử lý phù hợp |
| --- | --- | --- |
| `WrongMethodTypeException` trên `exact.set(c, (short) 7)` | Exact mode không chấp nhận descriptor có short thay int. | Dùng int đúng kiểu hoặc chọn invoke behavior khi conversion hợp lệ. |
| `WrongMethodTypeException` khi lấy long từ GET int ở exact | Return descriptor không trùng. | Nhận int trước rồi widen bên ngoài lời gọi hoặc dùng invoke behavior. |
| `WrongMethodTypeException` trên `mh.invokeExact(data, (short)1)` | MethodHandle yêu cầu index int. | Dùng int; hoặc `mh.invoke` có conversion phù hợp. |
| `ClassCastException` khi chuyển reference | Call site đòi cast sang kiểu không tương thích giá trị runtime. | Kiểm tra data và type trước khi gọi. |
| `UnsupportedOperationException` khi ghi field final | SET mode không hỗ trợ trên final field. | Kiểm tra `isAccessModeSupported`; chọn cơ chế phù hợp. |
| `NoSuchFieldException` khi `findVarHandle` | Tên hoặc kiểu field không đúng. | Kiểm tra khai báo và field type. |
| `IllegalAccessException` khi `findVarHandle` | Lookup không đủ quyền theo Java access checks / JPMS. | Dùng Lookup hợp pháp; `opens`/API public khi phù hợp. |
| `NullPointerException` hoặc `ArrayIndexOutOfBoundsException` | Receiver/array null hoặc index sai. | Kiểm tra tọa độ và logic nghiệp vụ. |
| Thêm đối số VarHandle sau `toMethodHandle` | VarHandle đã được bind, làm sai chữ ký. | Truyền chỉ tọa độ/value theo `mh.type()`. |
| Đọc/ghi đúng kiểu nhưng sai kết quả giữa các thread | Mode không có memory ordering cần thiết hoặc data race. | Chọn đúng access mode và mô hình đồng bộ. |

**Một mẹo chẩn đoán hiệu quả:** in `vh.varType()`, `vh.coordinateTypes()`, `vh.accessModeType(mode)` và `mh.type()` trước khi ghép graph. Với mode cụ thể, kiểm tra `isAccessModeSupported(mode)`. Với lỗi lúc tạo VarHandle, xử lý `NoSuchFieldException`/`IllegalAccessException`; với lỗi lúc gọi, phân biệt `WrongMethodTypeException` và `UnsupportedOperationException`.

## 13. Thiết kế pipeline và bảo vệ capability

VarHandle được tạo từ `MethodHandles.Lookup.findVarHandle`, `findStaticVarHandle` hoặc factory phù hợp, và quyền truy cập member được kiểm tra **khi tạo**. Sau khi có VarHandle tham chiếu field private hợp lệ, việc chia sẻ VarHandle hoặc MethodHandle chuyển từ nó cho mã khác có thể trao quyền thực sự đọc/ghi field đó.

Do đó:

1. Không phát tán `VarHandle` private hoặc MethodHandle tới dữ liệu nhạy cảm cho plugin không tin cậy.
2. Nếu bên nhận chỉ cần GET, cân nhắc cung cấp **một API hẹp chỉ đọc** hoặc `toMethodHandle(GET)` thay vì toàn bộ VarHandle có SET/CAS.
3. Không xem invoke-exact behavior là sandbox; nó chỉ kiểm tra kiểu chặt hơn, không hạn chế quyền truy cập data.
4. Kiểm tra hỗ trợ mode khi xây graph, thay vì để UnsupportedOperationException xảy ra trong hot path.
5. Cache handle khi pipeline ổn định để giảm chi phí tạo lại; benchmark hiệu năng với workload thực tế, không suy đoán exact luôn nhanh hơn invoke.
6. Nếu chuyển VarHandle qua boundary module, điều kiện JPMS của lookup cần được giải quyết **lúc tạo handle**, không được bypass bằng toMethodHandle.

**Ví dụ ứng dụng:** một serializer động có thể dùng `toMethodHandle(GET)` rồi `filterReturnValue` để chuẩn hóa dữ liệu; một bộ đếm dùng `toMethodHandle(GET_AND_ADD)` để tạo node atomic increment. Trong cả hai, chữ ký và memory mode phải được mô hình hóa rõ ràng trước khi ghép.

## 14. Bài tập kiểm tra và gợi ý test

**Bài tập A — đổi kiểu an toàn khi vẫn exact:** Với `int` instance field, hãy dùng `exact.get(receiver)` để đọc thành int trước, sau đó chuyển thành long bằng Java:

```java
int x = (int) exact.get(receiver);
long y = x;
```

Đây là đoạn minh họa khi `exact` có access-mode type `(Receiver)int` và `receiver` có kiểu tọa độ chính xác. Không thay bằng `long y = (long) exact.get(receiver)` vì khi đó descriptor của chính access-mode invocation là `(Receiver)long` và có thể ném `WrongMethodTypeException`.

**Bài tập B — mảng và adapter:** Lấy GET MethodHandle từ `arrayElementVarHandle(int[].class)`. Xác minh `mh.type()` là `(int[],int)int`, bind mảng/index bằng `insertArguments`, kiểm tra kiểu thành `()int` và đọc lại sau khi sửa phần tử.

**Bài tập C — final field:** Tìm VarHandle tới `final int code`. Kiểm tra GET supported, SET unsupported. Dùng `toMethodHandle(GET)` đọc; giải thích tại sao mode behavior không thay đổi khả năng ghi.

**Bài tập D — chuyển từ exact sang flexible:** Dùng `exact.withInvokeBehavior()` rồi thử `set(c, (short)7)`. Chứng minh behavior trả về `false` qua `hasInvokeExactBehavior()`, trong khi VarHandle exact ban đầu vẫn giữ `true`.

Bộ test nên có ít nhất: tọa độ instance/static/array, descriptor GET/SET/CAS, short→int và int→long ở invoke, mismatch tại exact, `mh.invoke` khác `mh.invokeExact`, field final unsupported, và một access mode GET_VOLATILE để bảo đảm mode được giữ sau khi chuyển đổi.

## 15. Câu hỏi tự kiểm tra

**1. `withInvokeExactBehavior` có tạo ra biến mới không?**

Không. Nó tạo VarHandle view cùng tập biến nhưng kiểm tra descriptor call site theo access-mode type chính xác.

**2. Vì sao `flexible.set(c, (short)7)` có thể chạy nhưng `exact.set(c, (short)7)` thất bại với int field?**

Invoke behavior có thể widen short→int; exact behavior đòi tham số đúng int và ném `WrongMethodTypeException` nếu caller truyền short.

**3. `toMethodHandle(GET)` có nhận đối số VarHandle khi invoke không?**

Không. VarHandle đã được bind. MethodHandle chỉ nhận tọa độ; với int[] là mảng và index.

**4. Tạo MethodHandle từ VarHandle flexible có khiến `MethodHandle.invokeExact` tự chuyển kiểu không?**

Không. `MethodHandle.invokeExact` luôn đòi đúng `mh.type()`. `MethodHandle.invoke` mới áp dụng conversion tương thích.

**5. Static int field có `toMethodHandle(GET).type()` là gì?**

`()int`, vì static field không cần tọa độ receiver. Với instance int field sẽ là `(Receiver)int`.

**6. `withInvokeExactBehavior` có làm GET mạnh hơn GET_VOLATILE về memory ordering không?**

Không. Exact chỉ quyết định kiểm tra chữ ký. GET_VOLATILE là access mode riêng với volatile semantics.

**7. Vì sao `final` field vẫn đọc được nhưng SET ném `UnsupportedOperationException`?**

Vì VarHandle của final field chỉ hỗ trợ đọc và không cho các access mode ghi/cập nhật; không liên quan tới conversion ở call site.

## 16. Ghi nhớ

- **Invoke behavior:** có thể chuyển kiểu khi access-mode call theo quy tắc tương thích như `MethodHandle.invoke`.
- **Invoke-exact behavior:** descriptor của access-mode invocation phải **khớp chính xác** `accessModeType(mode)`.
- **`toMethodHandle(mode)`:** trả MethodHandle đã bind VarHandle và mode, kiểu bằng `accessModeType(mode)`; không thêm tham số VarHandle.
- **Hai trục kiểm tra kiểu độc lập:** behavior của VarHandle khi gọi trực tiếp khác việc chọn `invoke` / `invokeExact` trên MethodHandle.
- **Kiểm tra mode và memory semantics:** exact không tăng atomicity; GET/GET_VOLATILE/CAS có những semantics khác nhau.
- **Giữ an toàn quyền:** các view không nâng quyền nhưng capability VarHandle/MethodHandle đã được cấp có thể được chia sẻ; chỉ cấp quyền cần thiết.

### Tài liệu chính thức Java SE 17

- [VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html) — `withInvokeExactBehavior`, `withInvokeBehavior`, `hasInvokeExactBehavior`, `accessModeType`, `toMethodHandle`, `isAccessModeSupported`.
- [MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html) — `arrayElementVarHandle`, `Lookup.findVarHandle`, `varHandleExactInvoker` và `varHandleInvoker`.
- [MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) — `invoke`, `invokeExact`, `asType`, chữ ký tại call site.
- [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — kiểu tham số và kiểu trả về của MethodHandle.
