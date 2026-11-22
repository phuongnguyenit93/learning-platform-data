# Khi nào chọn `Method`, `MethodHandle` hoặc `VarHandle` trong Java Reflection

## 1. Bài toán: một thành viên Java, ba cách làm việc khác nhau

Khi chương trình đã biết kiểu và phương thức cần gọi ở lúc biên dịch, cách đơn giản nhất thường là **gọi trực tiếp** qua kiểu Java hoặc interface. Nhưng framework, công cụ ánh xạ dữ liệu, bộ xử lý biểu thức, thư viện serialization hoặc hệ thống plugin đôi khi chỉ biết tên lớp, tên phương thức hoặc tên trường dữ liệu (*field*) trong lúc chạy. Khi đó Java cung cấp các công cụ khác nhau:

- `java.lang.reflect.Method`: đối tượng **mô tả một phương thức** để kiểm tra metadata (tên, tham số, annotation, modifiers...) và có thể gọi bằng `invoke`.
- `java.lang.invoke.MethodHandle`: một **tham chiếu có thể gọi** đến phương thức, constructor hoặc thao tác khác với kiểu lời gọi được biểu diễn rõ bằng `MethodType`. Phù hợp khi đã phân giải mục tiêu và cần tổ chức lời gọi động có kiểu, biến đổi chữ ký hoặc tái sử dụng.
- `java.lang.invoke.VarHandle`: tham chiếu có kiểu đến **vị trí chứa giá trị** như field hoặc phần tử mảng, với các chế độ đọc/ghi và một số phép **nguyên tử/đồng bộ bộ nhớ**. Phù hợp khi bài toán thực sự là truy cập biến, đặc biệt trong mã đồng thời.

Ba công cụ không phải ba phiên bản có thể thay thế trực tiếp. Nếu cần *khám phá metadata*, `Method` là điểm khởi đầu tự nhiên. Nếu cần *gọi một hành vi đã chọn*, `MethodHandle` cung cấp cách gọi và phối hợp linh hoạt. Nếu cần *đọc/ghi hoặc cập nhật nguyên tử một biến*, `VarHandle` diễn tả trực tiếp bài toán đó.

> Quy tắc đầu tiên: nếu mã ứng dụng đã biết chính xác API và có thể gọi trực tiếp an toàn, hãy ưu tiên lời gọi Java bình thường. Reflection chỉ có ích khi chương trình phải lựa chọn hoặc thao tác động ở runtime.

## 2. Bảng quyết định nhanh

| Câu hỏi chính | `Method` | `MethodHandle` | `VarHandle` |
| --- | --- | --- | --- |
| Đối tượng này mô tả gì? | Metadata của **phương thức** | Mục tiêu **có thể gọi** với `MethodType` | **Vị trí biến** và các chế độ truy cập |
| Lấy bằng cách nào? | `Class.getMethod` / `getDeclaredMethod` | `MethodHandles.Lookup.findVirtual`, `findStatic`, `unreflect`... | `Lookup.findVarHandle`, `findStaticVarHandle`, `arrayElementVarHandle`... |
| Thao tác chính | `invoke(receiver, Object...)` | `invokeExact(...)` / `invoke(...)` | `get`, `set`, `getVolatile`, `compareAndSet`, `getAndAdd`... |
| Có truy vấn annotation, tên và modifiers? | **Có**, qua API Reflection | **Không** như một `Method`; có thông tin kiểu lời gọi | Không dùng để khám phá annotation của field |
| Kiểu tham số/giá trị trả về | Đi qua `Object`, boxing/unboxing khi cần | Kiểu lời gọi rõ trong `MethodType` và call site | Kiểu tọa độ và giá trị của variable access mode |
| Xử lý ngoại lệ từ phương thức đích | `Method.invoke` gói ngoại lệ đích trong `InvocationTargetException` | Ngoại lệ của đích truyền ra trực tiếp theo luồng thực thi | Lỗi phụ thuộc access mode, kiểu và thao tác |
| Hữu ích cho đồng bộ bộ nhớ/CAS? | Không phải mục đích của `Method` | Có thể gọi mã đồng bộ có sẵn, không tự cung cấp CAS cho field | **Có**, các access mode hỗ trợ ngữ nghĩa bộ nhớ và cập nhật nguyên tử |
| Tình huống tiêu biểu | Framework duyệt annotation rồi gọi phương thức hiếm khi | Bộ gọi động tái sử dụng, adapter cho phương thức đã tìm | Bộ đếm, trạng thái, truy cập field/mảng cần quy tắc concurrent rõ ràng |

**Đừng chọn chỉ theo khẩu hiệu “API mới luôn nhanh hơn”.** Chi phí phụ thuộc dạng gọi, việc tái sử dụng kết quả tra cứu, sự tối ưu của JVM, tần suất thao tác và mức độ cạnh tranh giữa các thread. Nếu hiệu năng là yêu cầu thực tế, hãy đo trong điều kiện tương ứng.

## 3. `Method`: cần thông tin về phương thức và lời gọi động đơn giản

### 3.1. Điều `Method` làm tốt

`Class.getMethod(name, parameterTypes...)` tra cứu phương thức `public` phù hợp (kể cả phương thức `public` được kế thừa theo quy tắc API). `Class.getDeclaredMethod(...)` tra cứu phương thức khai báo **trực tiếp** trong lớp, bất kể modifier, nhưng không tự tìm trong superclass. Kết quả là `Method`, có thể dùng để:

- Đọc `getName()`, `getParameterTypes()`, `getReturnType()`, `getModifiers()`, `getDeclaringClass()`.
- Xem annotation với `getAnnotations()` hoặc `getAnnotation(...)`, xem metadata generic khi cần.
- Chọn đúng phương thức trong framework dựa trên quy ước hay annotation.
- Gọi phương thức qua `invoke(target, args...)` nếu có quyền truy cập.

Ví dụ **fragment**, giả định lớp `Service` công khai có phương thức `public String greet(String name)`:

~~~java
Method method = Service.class.getMethod("greet", String.class);
Object result = method.invoke(service, "Minh");
String message = (String) result;
~~~

Cần `import java.lang.reflect.Method;`, biến `service` có kiểu phù hợp, và xử lý `ReflectiveOperationException` cùng ngoại lệ liên quan quyền truy cập. Đối với phương thức instance, đối số đầu tiên của `invoke` là **receiver**; với static method, có thể truyền `null`. Kết quả primitive được **boxing** thành wrapper tương ứng; phương thức trả `void` cho kết quả `null`.

### 3.2. Chi phí và lỗi cần hiểu

- Mỗi lần `Method.invoke` nhận đối số trong mảng `Object[]` (dạng varargs); boxing/unboxing và chuyển kiểu có thể phát sinh. API tự kiểm tra receiver/arguments và có thể ném `IllegalArgumentException` nếu sai.
- Nếu phương thức đích ném ngoại lệ, `Method.invoke` ném `InvocationTargetException`; **ngoại lệ gốc** nằm ở `getCause()`.
- `getDeclaredMethod` tìm được private method **không đồng nghĩa** với việc được quyền gọi. Java kiểm tra quyền truy cập; `setAccessible(true)` có thể bị từ chối bởi ranh giới module. Khi có thể, thiết kế API công khai hoặc cấu hình `opens` phù hợp thay vì tìm cách phá quyền truy cập.
- Không nên gọi `getMethod`/`getDeclaredMethod` lặp lại trong một vòng lặp nóng nếu đã biết chính xác phương thức; có thể lưu `Method` đã được phân giải.

**Khi nên chọn:** mã cần metadata hoặc phải gọi một số phương thức dựa trên cấu hình/annotation, tần suất không cao và độ đơn giản quan trọng hơn khả năng tối ưu bộ gọi động.

## 4. Kiểm tra kiểu và quyền trước khi chọn cơ chế
Khi đã chọn đích, `MethodHandle` được lấy qua `MethodHandles.Lookup` và có chữ ký `handle.type()`. Với `findVirtual`, kiểu dùng để tra cứu mô tả phương thức chưa có receiver, còn handle kết quả nhận receiver ở đối số đầu; `invokeExact` yêu cầu khớp cả tham số **và kiểu trả về** tại call site. `Method` cho phép khám phá annotation; khi cần gọi lặp, có thể chuyển metadata thành handle bằng `Lookup.unreflect(method)` sau khi kiểm tra quyền.

`VarHandle` cần `varType()` cùng `coordinateTypes()` (receiver cho instance field; không tọa độ cho static field; mảng và chỉ số cho phần tử mảng). `getAndAdd` trả giá trị cũ trước phép cộng; `compareAndSet` trả boolean. Các phép thường `get`/`set` không tự đồng bộ giữa thread và hai phép riêng lẻ không hợp thành phép tăng nguyên tử.

Cả ba cơ chế đều có kiểm tra quyền. Với member private xuyên named module, `privateLookupIn` cần lookup nguồn có quyền phù hợp và package đích mở đúng module, nên hãy chọn API public khi có thể.

## 5. Ví dụ Java 17+ chạy độc lập: cùng chương trình, ba vai trò

Tạo tệp `ChoosingMemberAccessDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ChoosingMemberAccessDemo {
    public static class Counter {
        private int count;

        public int twice(int x) {
            return x * 2;
        }

        public void fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();

        // Method: tra cứu metadata và gọi phương thức phản chiếu.
        Method reflected = Counter.class.getMethod("twice", int.class);
        System.out.println("Method name=" + reflected.getName());
        int fromMethod = (Integer) reflected.invoke(counter, 3);
        System.out.println("Method result=" + fromMethod);

        // MethodHandle: gọi phương thức đã phân giải với kiểu chính xác.
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle twice = lookup.findVirtual(
                Counter.class,
                "twice",
                MethodType.methodType(int.class, int.class));
        int fromHandle = (int) twice.invokeExact(counter, 4);
        System.out.println("MethodHandle result=" + fromHandle);

        // VarHandle: truy cập field instance và cập nhật nguyên tử.
        VarHandle count = lookup.findVarHandle(
                Counter.class, "count", int.class);
        System.out.println("VarHandle initial=" + (int) count.get(counter));
        count.set(counter, 10);
        boolean updated = count.compareAndSet(counter, 10, 15);
        int oldValue = (int) count.getAndAdd(counter, 5);
        int current = (int) count.getVolatile(counter);
        System.out.println("CAS success=" + updated);
        System.out.println("getAndAdd previous=" + oldValue);
        System.out.println("VarHandle current=" + current);

        // VarHandle có thể truy cập cả phần tử mảng.
        VarHandle elements = MethodHandles.arrayElementVarHandle(int[].class);
        int[] numbers = {1};
        int previousElement = (int) elements.getAndAdd(numbers, 0, 4);
        System.out.println("array previous=" + previousElement
                + ", current=" + numbers[0]);

        // Cùng một lỗi đích, hai cơ chế ném ngoại lệ khác nhau.
        Method failMethod = Counter.class.getMethod("fail");
        try {
            failMethod.invoke(counter);
        } catch (InvocationTargetException ex) {
            System.out.println("Method exception wrapper="
                    + ex.getClass().getSimpleName());
            System.out.println("Method cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        MethodHandle failHandle = lookup.findVirtual(
                Counter.class, "fail", MethodType.methodType(void.class));
        try {
            failHandle.invokeExact(counter);
        } catch (IllegalStateException ex) {
            System.out.println("MethodHandle exception="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Vì `Counter` và lớp chứa `main` là **nestmates**, `MethodHandles.lookup()` trong lớp ngoài có thể tìm field `private count` của lớp lồng bên trong. Ví dụ này không có nghĩa Lookup của một lớp bất kỳ được quyền truy cập mọi field private ở nơi khác.

Lệnh biên dịch và chạy:

~~~bash
javac ChoosingMemberAccessDemo.java
java ChoosingMemberAccessDemo
~~~

Kết quả:

~~~text
Method name=twice
Method result=6
MethodHandle result=8
VarHandle initial=0
CAS success=true
getAndAdd previous=15
VarHandle current=20
array previous=1, current=5
Method exception wrapper=InvocationTargetException
Method cause=IllegalStateException
MethodHandle exception=IllegalStateException
~~~

Những điểm cần quan sát:

1. `Method` cung cấp metadata `getName()` và thực hiện `invoke`. Kết quả trả qua `Object` nên ở đây phải chuyển từ wrapper `Integer` về `int`.
2. `MethodHandle` giữ kiểu lời gọi (`Counter`, `int`) → `int`. Kết quả `8` đến từ `twice(4)` chứ không liên quan field `count`.
3. `VarHandle` trỏ đến chính field `count`. `compareAndSet` đổi `10` thành `15`; `getAndAdd` trả giá trị cũ `15` rồi cập nhật thành `20`.
4. `arrayElementVarHandle` lấy một VarHandle dùng tọa độ (`int[]`, chỉ số `int`), cho phép thao tác nguyên tử trên một phần tử mảng.
5. Phương thức `fail()` ném cùng `IllegalStateException` nhưng `Method.invoke` bọc lỗi trong `InvocationTargetException`, còn handle truyền ngoại lệ từ đích trực tiếp ra.

Đây là ví dụ đơn luồng để kiểm chứng API và stdout. Nó **không phải benchmark** và cũng không chứng minh tính đúng đắn của một thuật toán đa luồng chỉ qua một lần chạy.

## 6. Quyền truy cập và module: chọn đúng API chưa đủ

Ba API đều chịu mô hình truy cập Java. Sự khác nhau nằm ở **cách phát hiện và nơi kiểm tra quyền**:

- `Method` có thể tìm private method bằng `getDeclaredMethod`. Lúc `invoke`, quyền truy cập vẫn được kiểm tra; `trySetAccessible` trả `false` khi không thể nới quyền, còn `setAccessible(true)` có thể ném `InaccessibleObjectException`.
- `MethodHandle` thường được lấy qua `Lookup.findVirtual` / `findStatic`; quyền truy cập được đánh giá dựa trên đối tượng `Lookup` tại thời điểm tìm kiếm. `publicLookup()` và `lookup()` không tương đương.
- `VarHandle` được tìm qua `Lookup.findVarHandle` / `findStaticVarHandle`; quyền truy cập field cũng tuân theo `Lookup` và giới hạn của module.
- `MethodHandles.privateLookupIn(target, callerLookup)` có thể tạo Lookup đủ quyền với một target cụ thể khi **người gọi có quyền thích hợp và module đích cho phép mở package**. Với một named module khác, điều kiện `opens` phải được thỏa; không mặc định được quyền đọc/ghi private members của mọi module.

Ví dụ dùng `privateLookupIn` khi package đích được mở hợp lệ:

~~~java
MethodHandles.Lookup privateLookup = MethodHandles.privateLookupIn(
        Target.class, MethodHandles.lookup());
MethodHandle handle = privateLookup.findVirtual(
        Target.class, "hidden", MethodType.methodType(void.class));
~~~

*Fragment này giả định `Target` tồn tại và có instance method `private void hidden()`. Vẫn phải truyền instance `Target` khi gọi handle, xử lý `IllegalAccessException` / `NoSuchMethodException` lúc tra cứu và `Throwable` khi gọi.*

Một `VarHandle` tham chiếu field `final` có thể cho phép đọc nhưng **không hỗ trợ thao tác ghi/cập nhật** phù hợp. Việc lấy được handle không có nghĩa gọi `set` hay CAS sẽ thành công: truy cập không được hỗ trợ sẽ ném `UnsupportedOperationException`. Với `Method`, tên field không liên quan: nếu cần metadata field, dùng `java.lang.reflect.Field`; nếu cần thao tác nguyên tử với field, xem `VarHandle`.

## 7. Khi có cả `Method` và `MethodHandle`

Nhiều framework phải **khám phá trước, gọi sau**, nên kết hợp hai API là hợp lý:

~~~java
Method discovered = SomeApi.class.getMethod("process", String.class);
MethodHandle callable = MethodHandles.lookup().unreflect(discovered);
~~~

Đây là fragment giả định `SomeApi` tồn tại và method có thể truy cập từ Lookup hiện tại. `unreflect` chuyển metadata thành callable handle, nhưng **không tự mở khóa truy cập**. Nếu cần annotation, giữ `discovered` để truy vấn. Nếu cần gọi nhiều lần, giữ `callable` để tránh tra cứu lặp.

Một handle cho phương thức instance vẫn nhận receiver trừ khi được **bind** vào một đối tượng:

~~~java
MethodHandle bound = callable.bindTo(apiInstance);
~~~

`bindTo` cố định đối số đầu tiên là receiver (khi kiểu handle phù hợp). Sau đó lời gọi nhận các đối số còn lại. Cần phân biệt rõ `MethodType` của handle **trước và sau khi bind**, và đừng trộn `invokeExact` với những call site dùng sai kiểu kết quả.

### Không thay `VarHandle` bằng `MethodHandle` một cách máy móc

`Lookup.findGetter` / `findSetter` cũng tạo được `MethodHandle` để đọc/ghi field khi hợp lệ. Nhưng một getter-handle bình thường không tự cung cấp `compareAndSet` hay các chế độ `getAcquire`, `setRelease`, `getVolatile`. Nếu yêu cầu là bộ nhớ và cập nhật nguyên tử của một vị trí dữ liệu, hãy dùng `VarHandle` hoặc abstraction đồng thời phù hợp.

`VarHandle.toMethodHandle(AccessMode)` còn có thể tạo `MethodHandle` cho một access mode cụ thể khi cần tích hợp vào pipeline gọi động. **Ngữ nghĩa truy cập** vẫn đến từ access mode của `VarHandle`, không phải do bất kỳ `MethodHandle` nào cũng có thuộc tính đó.

## 8. Chọn theo tình huống dự án

| Tình huống | Lựa chọn đầu tiên | Lý do |
| --- | --- | --- |
| Biết interface/phương thức từ source code và gọi thường xuyên | Gọi Java trực tiếp | Dễ đọc, compiler kiểm tra kiểu, dễ refactor |
| Quét phương thức có annotation `@Route` / `@Test` / `@Handler` | `Method` | API truy vấn metadata khai báo |
| Cấu hình chỉ định method bằng tên, chỉ gọi vài lần | `Method` | Đơn giản; không cần thêm tầng adapter |
| Framework chọn handler một lần rồi gọi lặp lại ở nhiều request | `MethodHandle` (có thể tra cứu bằng `Method` trước) | Kiểu gọi rõ; hỗ trợ adapter/combination, có tiềm năng JVM tối ưu |
| Dynamic invocation phải đổi/bind/reorder tham số | `MethodHandle` | `asType`, `bindTo`, các combinator |
| Đọc annotation của field và chính sách serialization | `Field` để khám phá metadata | `VarHandle` không thay API metadata |
| Cập nhật field `int` bằng CAS hoặc lấy giá trị cũ rồi cộng | `VarHandle` hoặc `AtomicInteger` | Có primitive atomic access mode, không cần tự dựng read-modify-write |
| Truy cập phần tử mảng bằng thuật toán đồng thời | `arrayElementVarHandle` | Có các access mode trên phần tử mảng |
| Muốn thay đổi value của một field `final` | Thiết kế lại trạng thái | `VarHandle` không cho ghi field `final` chỉ vì tìm được handle |
| Cần xây khóa, hàng đợi, cấu trúc đồng thời phức tạp | Cấu trúc `java.util.concurrent` đã kiểm chứng trước | Dễ duy trì hơn thuật toán dùng CAS/memory ordering tự viết |

**Cùng một hệ thống có thể sử dụng cả ba:** `Method` khám phá annotation; `MethodHandle` thực hiện lời gọi; `VarHandle` quản lý trạng thái điều phối của framework. Quyết định phụ thuộc trách nhiệm của từng đoạn mã.

## 9. Hiệu năng: hiểu đúng trước khi tối ưu

Một lựa chọn có thể ảnh hưởng đến tốc độ nhưng không thể kết luận từ tên API:

1. **Tra cứu và thực thi là hai giai đoạn khác nhau.** So sánh “`getMethod` rồi `invoke` mỗi vòng lặp” với “một `MethodHandle` đã cache” là so sánh hai chiến lược khác nhau; hãy tách chi phí tra cứu khỏi chi phí gọi.
2. **Loại call site quan trọng.** `MethodHandle.invokeExact` với kiểu ổn định có tiềm năng tối ưu tốt, nhưng pipeline adapter, lời gọi đa hình, boxing, visibility và warmup JVM làm kết quả thay đổi.
3. **VarHandle access modes có chi phí và ý nghĩa khác nhau.** `getVolatile` hoặc CAS thường có chi phí đồng bộ/atomic khác `get`. Không dùng chế độ yếu hơn chỉ để có kết quả benchmark đẹp nếu thuật toán yêu cầu memory ordering mạnh hơn.
4. **Đo với JMH khi đây là nút thắt hiệu năng thực tế.** Có warmup, đủ lượt đo, tránh JVM loại bỏ tính toán, đo nhiều thread nếu ứng dụng cạnh tranh tài nguyên. Không suy từ một ví dụ chạy một lần thành kết luận tổng quát “MethodHandle luôn nhanh hơn Method”.

Đặc biệt, nếu mục tiêu chỉ là một bộ đếm an toàn đồng thời, sử dụng `AtomicInteger` với `incrementAndGet()` thường rõ nghĩa và giảm nguy cơ sai khi viết mã đồng thời bằng `VarHandle`.

## 10. Lỗi và ngộ nhận thường gặp

**“MethodHandle chỉ là Method đổi tên.”** Sai. `Method` lưu metadata của khai báo, trong khi `MethodHandle` là một callable có kiểu lời gọi, có thể được bind/adapt/combine. Có thể chuyển `Method` thành handle nhưng vai trò khác nhau.

**“MethodHandle.invokeExact sẽ tự đổi int thành long nếu cần.”** Sai. `invokeExact` đòi hỏi kiểu chính xác, kể cả kiểu kết quả; dùng `invoke`/`asType` khi quy tắc chuyển đổi phù hợp.

**“Tìm được private Method/VarHandle thì chắc chắn gọi hoặc ghi được.”** Sai. Quyền truy cập, module và các access mode được hỗ trợ đều có giới hạn riêng.

**“VarHandle.get rồi VarHandle.set là thao tác tăng nguyên tử.”** Sai. Hai thao tác riêng lẻ có thể bị xen giữa bởi thread khác. Dùng `getAndAdd`, CAS loop hợp lệ hoặc abstraction đồng thời phù hợp.

**“Chỉ cần sử dụng volatile là mọi trạng thái gồm nhiều field tự nhất quán.”** Sai. Volatile/CAS tác động lên biến được dùng và quan hệ bộ nhớ theo memory model; bất biến liên quan nhiều biến còn phải được thiết kế.

**“Bắt InvocationTargetException cho MethodHandle.invokeExact.”** Thường là sai trọng tâm. Lớp bọc này là đặc trưng của `Method.invoke` khi phương thức đích ném; MethodHandle chuyển ngoại lệ của đích ra trực tiếp.

**“Cứ thay mọi Method bằng MethodHandle thì sẽ nhanh hơn.”** Không có bảo đảm như vậy. Cache đích, kiểu call site, JVM, môi trường triển khai và số lượng lời gọi quyết định hiệu quả thực tế.

## 11. Tự kiểm tra

1. Bạn cần tìm mọi phương thức gắn một annotation của controller. API nào phù hợp? **`Method`**, vì cần metadata.
2. Sau khi chọn một handler theo annotation, server sẽ gọi handler nhiều lần. Có thể tối ưu cấu trúc như thế nào? **Giữ `Method` để phân tích metadata rồi tạo/cache `MethodHandle` dùng khi gọi; đo hiệu năng nếu cần.**
3. Bạn muốn tăng `int counter` một cách nguyên tử từ nhiều thread. `MethodHandle.findGetter` có đủ không? **Không.** Cân nhắc `VarHandle.getAndAdd` hoặc `AtomicInteger`.
4. Một `Method` dùng `invoke` gọi phương thức đích ném `IllegalStateException`. Nên tìm nguyên nhân gốc ở đâu? **`InvocationTargetException.getCause()`.**
5. Với `MethodHandle.invokeExact`, tại sao gán kết quả vào biến kiểu khác có thể lỗi? **Kiểu kết quả tại call site là phần của chữ ký phải khớp.**
6. `VarHandle` có hỗ trợ `getAndAdd` cho mọi field không? **Không.** Phụ thuộc loại biến và access mode; kiểm tra API/hỗ trợ.
7. Nếu xử lý một map thường, không có truy cập động hay yêu cầu atomic custom, cần một trong ba công cụ trên không? **Thường không.** Ưu tiên API Java trực tiếp và cấu trúc đồng thời cấp cao khi cần.

## 12. Kết luận và tài liệu tham khảo

Hãy xác định **bài toán đang là gì** trước khi chọn công cụ: cần biết *phương thức nào* và annotation gì thì dùng `Method`; cần *gọi hành vi đã chọn* với một chữ ký rõ, có thể thích nghi thì dùng `MethodHandle`; cần *truy cập/cập nhật biến* với chế độ bộ nhớ hoặc CAS thì dùng `VarHandle`. Luôn kiểm tra quyền truy cập, kiểu lời gọi, xử lý ngoại lệ và tính đúng đắn khi có nhiều thread. Khi code tĩnh đủ rõ, lời gọi Java trực tiếp hoặc API đồng thời cấp cao vẫn là lựa chọn nên cân nhắc đầu tiên.

Tài liệu chính thức:

- [Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — `java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 21 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 21 — `java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)