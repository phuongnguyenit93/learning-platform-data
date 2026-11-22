# Phân biệt core reflection với `java.lang.invoke`

## 1. Hai API cùng làm việc với thành phần Java tại runtime nhưng có vai trò khác nhau

**Core reflection** là tập API chủ yếu trong `java.lang.Class` và `java.lang.reflect` (`Method`, `Constructor`, `Field`, `Parameter`, `Modifier`, `RecordComponent`...). Nó phù hợp khi chương trình cần **khám phá metadata** của một kiểu: tìm phương thức, trường, constructor, annotation, tham số, modifier, kiểu generic; sau đó có thể gọi phương thức, tạo đối tượng hoặc đọc/ghi trường qua các đối tượng metadata.

**`java.lang.invoke`** cung cấp các đối tượng thao tác được định kiểu như `MethodHandle`, `VarHandle`, cùng `MethodHandles.Lookup`, `MethodType`, `CallSite` và các công cụ kết hợp handle. Nó phù hợp khi đã xác định thao tác cần thực hiện và muốn **biểu diễn lời gọi hoặc quyền truy cập dưới dạng handle có chữ ký cụ thể**, dễ kết hợp/chuyển đổi cho dynamic invocation; `VarHandle` còn hỗ trợ các chế độ truy cập bộ nhớ và thao tác nguyên tử.

Chúng có phần giao nhau, nhưng không phải API thay thế toàn bộ cho nhau: `MethodHandle` không cung cấp kho metadata annotation/generic như `Method`, còn `Method` không thay thế các access mode và compare-and-set của `VarHandle`. Cả hai vẫn tuân thủ kiểm soát truy cập của ngôn ngữ và hệ thống module.

| Câu hỏi | Core reflection | `java.lang.invoke` |
| --- | --- | --- |
| Đối tượng chính | `Class<?>`, `Method`, `Constructor<?>`, `Field` | `MethodHandle`, `VarHandle`, `MethodType`, `MethodHandles.Lookup` |
| Tìm thành viên | `getMethod`, `getDeclaredMethods`, `getDeclaredField`… | `Lookup.findVirtual`, `findStatic`, `findConstructor`, `findVarHandle`… |
| Khám phá annotation/generic/parameter | Mạnh và trực tiếp qua metadata | Không phải nhiệm vụ chính; thường dùng reflection nếu cần |
| Gọi method | `Method.invoke(receiver, Object...)` | `handle.invokeExact(...)`, `handle.invoke(...)`, `invokeWithArguments(...)` |
| Tạo instance | `Constructor.newInstance(Object...)` | Constructor `MethodHandle` có chữ ký kiểu `(args)Instance` |
| Trường | `Field.get/set` cùng các biến thể primitive | `VarHandle.get/set`, CAS, atomic update, memory ordering |
| Kiểu tại điểm gọi | Tham số/giá trị trả về đi qua `Object`, có boxing/unboxing | `MethodType` và chữ ký tại điểm gọi, đặc biệt nghiêm ngặt với `invokeExact` |
| Ngoại lệ do method đích ném | `Method.invoke` gói trong `InvocationTargetException` | `MethodHandle` truyền trực tiếp ngoại lệ của đích |
| Quyền truy cập | Java access checks, `setAccessible` trong giới hạn module | Quyền nằm ở `Lookup`; tra cứu handle phải thỏa access checks |

## 2. Core reflection: khám phá trước, gọi qua đối tượng metadata

Ví dụ đoạn code đặt trong một phương thức (chưa phải chương trình độc lập):

```java
Method method = String.class.getMethod("substring", int.class);
Object answer = method.invoke("java", 2);
System.out.println(answer); // va
```

`getMethod` tìm phương thức public theo **tên và các kiểu tham số**, còn `Method.invoke` yêu cầu receiver với phương thức instance. Kết quả có kiểu biên dịch `Object` dù `substring` khai báo trả `String`; đối số nguyên thủy `2` được boxing trong lời gọi varargs. Với phương thức `static`, receiver truyền cho `Method.invoke` có thể là `null`.

Reflection hữu ích khi chưa biết cấu trúc kiểu lúc biên dịch. Ví dụ framework kiểm tra annotation để ánh xạ HTTP route, công cụ serialize cần đọc field/generic type, test runner quét method có annotation, hoặc trình khám phá class liệt kê constructor và modifier. `getMethods()` chỉ lấy các public method (kể cả được kế thừa), còn `getDeclaredMethods()` lấy method khai báo trực tiếp trong class, bất kể modifier nhưng không lấy method kế thừa. Tìm thấy thành viên private **không đồng nghĩa có quyền gọi**.

Các ràng buộc cần nhớ:

- `Method.invoke` có thể thực hiện các chuyển đổi được reflection cho phép, như unboxing và một số widening primitive; nó không ép kiểu tùy ý.
- `Method.invoke` gói exception do code đích ném vào `InvocationTargetException`; lấy `getCause()` để xem lỗi gốc. Lỗi tra cứu và lỗi truy cập phát sinh theo các nhánh ngoại lệ khác.
- `Field.getInt`/`setInt` thao tác với trường `int` mà không cần tự ép `Object`; tuy nhiên `Field` không tự cung cấp compare-and-set nguyên tử và các access mode của `VarHandle`.
- `setAccessible(true)` không luôn thành công: strong encapsulation của Java Platform Module System vẫn đặt giới hạn.

## 3. `MethodHandle`: tham chiếu lời gọi có chữ ký rõ ràng

Một `MethodHandle` biểu diễn một phép gọi có kiểu. `MethodType` mô tả chính xác danh sách tham số và kiểu trả về của handle; `handle.type()` cho biết chữ ký **sau khi handle được tạo**, không nhất thiết giống chữ ký khai báo ban đầu của method.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle substring = lookup.findVirtual(
        String.class, "substring", MethodType.methodType(String.class, int.class));
System.out.println(substring.type()); // (String,int)String
String answer = (String) substring.invokeExact("java", 2);
System.out.println(answer); // va
```

Đây là fragment cần đặt trong method khai báo `throws Throwable` (hoặc bắt exception) và import `java.lang.invoke.*`. Đối với `findVirtual`, `MethodType.methodType(String.class, int.class)` mô tả **method đích** `substring(int) -> String`; handle thu được có thêm receiver `String` ở vị trí đầu tiên, nên kiểu thực tế là `(String,int)String`.

Những cách tạo handle thường dùng:

| Phương thức `Lookup` | Phép gọi thu được |
| --- | --- |
| `findVirtual(Owner.class, name, methodType)` | Instance method; receiver đứng đầu tham số của handle |
| `findStatic(Owner.class, name, methodType)` | Static method; không có receiver |
| `findConstructor(Owner.class, methodType(void.class, ...))` | Gọi constructor; handle trả về instance `Owner` |
| `findGetter` / `findSetter` | Handle thao tác trường tương ứng, theo quyền lookup |
| `unreflect(Method)` / `unreflectConstructor(Constructor)` | Chuyển đối tượng reflection thành handle nếu có quyền cần thiết |
| `findSpecial(...)` | Lời gọi mang ngữ nghĩa `invokespecial`, cần ngữ cảnh và quyền đặc biệt |

Các phương thức kết hợp như `bindTo(receiver)`, `asType(newType)`, `filterArguments` hoặc `guardWithTest` có thể tạo handle mới từ handle đang có. Điều này hữu ích trong bộ điều phối lời gọi động khi muốn chuẩn bị đường gọi một lần rồi tái sử dụng.

**`invokeExact` và `invoke` khác nhau ở việc khớp chữ ký:**

- `invokeExact`: chữ ký tại call site, gồm receiver, số lượng, kiểu tham số **và kiểu trả về**, phải khớp chính xác `handle.type()`; sai sẽ gây `WrongMethodTypeException`. Vì thế thường phải ép kiểu kết quả, ví dụ `int n = (int) handle.invokeExact(obj, 3);`.
- `invoke`: cho phép các chuyển đổi theo quy tắc `asType` khi tương thích, chẳng hạn boxing/unboxing và reference cast phù hợp. Nó vẫn kiểm tra kiểu, không tự biến mọi `Object` thành kiểu tùy ý.
- `invokeWithArguments`: chấp nhận danh sách đối số động thông qua `Object`/`List`, tiện khi chưa có signature tĩnh nhưng thêm overhead và chuyển đổi; không phải lúc nào cũng nên dùng.

Ví dụ `MethodHandle` xử lý target exception trực tiếp, không tự đóng gói nó trong `InvocationTargetException` như `Method.invoke`. Khi thiết kế API public, không nhất thiết lan truyền `throws Throwable` khắp ứng dụng; có thể bắt/ánh xạ lỗi tại lớp adapter.

## 4. `VarHandle`: truy cập biến có semantics bộ nhớ/atomic

`VarHandle` mô tả quyền truy cập một **biến**: instance field, static field hoặc phần tử mảng. Khác `Field`, nó có các nhóm access mode và có thể tham gia thuật toán đồng bộ không khóa khi loại biến và access mode hỗ trợ. Một handle có kiểu giá trị (`varType()`) và danh sách tọa độ (`coordinateTypes()`); ví dụ instance field `Counter.value` có kiểu giá trị `int` và tọa độ `Counter`, còn phần tử `int[]` có tọa độ `int[]` cùng chỉ số `int`.

| Nhóm access mode | Ví dụ | Ý nghĩa chủ đạo |
| --- | --- | --- |
| Plain | `get`, `set` | Truy cập thông thường, không yêu cầu ordering bổ sung cho đồng bộ giữa thread |
| Opaque | `getOpaque`, `setOpaque` | Ordering yếu hơn acquire/release, nhưng có tính nhất quán riêng của opaque access |
| Acquire / Release | `getAcquire`, `setRelease` | Công bố/tiếp nhận dữ liệu theo ordering acquire/release khi phối hợp đúng |
| Volatile | `getVolatile`, `setVolatile` | Ngữ nghĩa truy cập volatile trong Java Memory Model |
| Atomic | `compareAndSet`, `compareAndExchange`, `getAndSet`, `getAndAdd` | Thao tác read-modify-write nguyên tử, với ngữ nghĩa ordering cụ thể theo access mode |

**Không phải mọi mode đều hỗ trợ cho mọi biến.** Chẳng hạn `getAndAdd` không có ý nghĩa cho mọi kiểu reference; dùng `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` nếu cần kiểm tra động. Với field `final`, các mode ghi hay cập nhật nguyên tử không được hỗ trợ. Không suy luận rằng `get` hay `set` thông thường bảo đảm đồng bộ giữa thread; chọn mode và thiết kế happens-before phù hợp.

Đối với mảng, có thể tạo handle mà không có field:

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
int[] values = {4, 8};
boolean swapped = element.compareAndSet(values, 1, 8, 9);
System.out.println(swapped + ", " + values[1]); // true, 9
```

Đây là fragment cần import `java.lang.invoke.*`; `compareAndSet` dùng tọa độ `(array, index)` rồi tới expected/new value. Trong bài toán concurrency, tránh suy nghĩ rằng một CAS đơn lẻ bảo đảm mọi invariants của cấu trúc dữ liệu nhiều trường: còn cần phân tích tranh chấp, visibility, vòng lặp retry và trường hợp ABA nếu có.

## 5. Ví dụ Java 17+ hoàn chỉnh: cùng một lớp, ba cách tương tác

Lưu mã sau thành tệp **`ReflectionInvokeDemo.java`**. Ví dụ dùng một nested class `Counter` có constructor, instance method, static method và private field. Code ở cùng nest nên lookup có quyền truy cập private field trong ví dụ; với class nằm ở module/package khác phải xét lại access control.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionInvokeDemo {
    public static final class Counter {
        private int value;

        public Counter(int initial) { this.value = initial; }

        public int add(int delta) {
            value += delta;
            return value;
        }

        public static String format(String label, int value) {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) throws Throwable {
        // Core reflection: tìm metadata rồi gọi/đọc/ghi.
        Constructor<Counter> constructor = Counter.class.getConstructor(int.class);
        Counter a = constructor.newInstance(5);
        Method method = Counter.class.getMethod("add", int.class);
        Object reflectResult = method.invoke(a, 2);
        Field field = Counter.class.getDeclaredField("value");
        field.setAccessible(true);
        field.setInt(a, 9);
        System.out.println("reflect invoke: " + reflectResult);
        System.out.println("reflect field: " + field.getInt(a));

        // MethodHandle: tạo handle có chữ ký rõ ràng rồi gọi.
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle mhCtor = lookup.findConstructor(
                Counter.class, MethodType.methodType(void.class, int.class));
        Counter b = (Counter) mhCtor.invokeExact(10);
        MethodHandle mhAdd = lookup.findVirtual(
                Counter.class, "add", MethodType.methodType(int.class, int.class));
        int result = (int) mhAdd.invokeExact(b, 3);
        MethodHandle mhStatic = lookup.findStatic(
                Counter.class, "format",
                MethodType.methodType(String.class, String.class, int.class));
        String description = (String) mhStatic.invokeExact("counter", result);
        System.out.println("handle invokeExact: " + result);
        System.out.println("static handle: " + description);

        // VarHandle: truy cập field và cập nhật nguyên tử.
        VarHandle var = lookup.findVarHandle(Counter.class, "value", int.class);
        int before = (int) var.get(b);
        var.set(b, 20);
        boolean changed = var.compareAndSet(b, 20, 25);
        int previous = (int) var.getAndAdd(b, 5);
        System.out.println("var before: " + before);
        System.out.println("var CAS: " + changed);
        System.out.println("var getAndAdd previous: " + previous);
        System.out.println("var volatile read: " + (int) var.getVolatile(b));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ReflectionInvokeDemo.java
java ReflectionInvokeDemo
```

Stdout:

```text
reflect invoke: 7
reflect field: 9
handle invokeExact: 13
static handle: counter=13
var before: 13
var CAS: true
var getAndAdd previous: 25
var volatile read: 30
```

Diễn giải: biến `a` tăng từ `5` lên `7` bằng reflection rồi bị đặt thành `9`. Biến `b` được tạo qua constructor handle với `10`, tăng thành `13` qua instance method handle. `VarHandle` đọc `13`, đặt `20`, đổi có điều kiện `20 -> 25`, sau đó tăng `25 -> 30`; `getAndAdd` trả **giá trị cũ `25`**. Các thao tác chạy tuần tự để minh họa contract; ví dụ không tuyên bố chứng minh tính đúng đắn của thuật toán nhiều thread.

## 6. Lỗi thường gặp và câu hỏi tự kiểm tra

- Dùng `getDeclaredMethod` rồi nghĩ đã được phép gọi member private: **sai**; tìm thấy metadata và có quyền thực thi là hai bước riêng.
- Đưa toàn bộ tham số vào `Object[]` khi dùng `invokeExact` và kỳ vọng tự thích ứng: **sai**; kiểu tại call site phải khớp handle, hoặc chủ động dùng `asType`/`invoke`/`invokeWithArguments` theo mục đích.
- Nghĩ `MethodType` của `findVirtual` đã gồm receiver: **sai**; receiver xuất hiện trong kiểu của handle kết quả, còn `MethodType` truyền vào mô tả phương thức đích.
- Coi `VarHandle.set` thông thường và `setVolatile` là có semantics bộ nhớ như nhau: **sai**; ordering là một phần contract.
- Bỏ qua `Lookup`/JPMS hoặc xem `privateLookupIn` như cửa hậu tự động: **sai**; kiểm tra quyền vẫn được áp dụng.

Tự kiểm tra:

1. Muốn lấy annotation của một method chưa biết tên lúc biên dịch, dùng `Method` hay `MethodHandle`? **`Method`** qua core reflection.
2. Với `findVirtual` của method `int inc(int x)`, handle có cần tham số receiver không? **Có**, receiver đứng trước `int x`.
3. Muốn cập nhật một field `int` có điều kiện nguyên tử, dùng `Field.setInt` hay `VarHandle.compareAndSet`? **`VarHandle.compareAndSet`**.
4. Target ném `IOException`: `Method.invoke` và `invokeExact` biểu hiện giống hệt nhau không? **Không**; reflection gói target exception trong `InvocationTargetException`, method handle chuyển tiếp trực tiếp exception.
5. `VarHandle.getAndAdd(receiver, 5)` trả về gì? **Giá trị trước phép cộng**, khi mode đó được hỗ trợ.

Đọc thêm: [Javadoc `java.lang.reflect.Method` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [Javadoc `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html), [Javadoc `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), [Javadoc `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html), [JEP 416](https://openjdk.org/jeps/416).