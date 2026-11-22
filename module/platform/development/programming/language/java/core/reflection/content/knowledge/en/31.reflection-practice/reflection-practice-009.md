# So sánh gọi trực tiếp, Method.invoke và MethodHandle trong Java

Trong Java, cùng một method có thể được gọi bằng nhiều cách: **gọi trực tiếp** bằng cú pháp Java thông thường, **gọi phản chiếu** qua `java.lang.reflect.Method.invoke(...)` hoặc **gọi động có chữ ký kiểu** qua `java.lang.invoke.MethodHandle`. Cả ba có thể dẫn đến cùng một hành vi nghiệp vụ, nhưng khác nhau ở thời điểm kiểm tra kiểu, cách tìm method, xử lý giá trị primitive, quyền truy cập, exception và cơ hội tối ưu hóa.

Đây là một bài thực hành trong Java Core – Reflection. Mục tiêu không phải kết luận rằng một API luôn nhanh nhất, mà là **hiểu khi nào mỗi cách phù hợp và quan sát chính xác hành vi trên Java 17+**.

## 1. Ba cơ chế ở một cái nhìn

Giả sử có class:

```java
class Calculator {
    int add(int a, int b) {
        return a + b;
    }
}
```

Đây là đoạn minh họa, không phải chương trình hoàn chỉnh.

### A. Gọi trực tiếp

```java
Calculator calculator = new Calculator();
int result = calculator.add(3, 4);
```

Compiler biết `Calculator`, tên method, số lượng và kiểu đối số. Nếu đổi tên method hoặc truyền đối số không phù hợp, thông thường lỗi được phát hiện khi biên dịch lại. Với instance method có dispatch động, JVM vẫn chọn implementation được override phù hợp ở runtime; “gọi trực tiếp” **không đồng nghĩa** mọi lời gọi được quyết định cứng tại compile time.

### B. Reflection qua Method.invoke

```java
Method method = Calculator.class.getDeclaredMethod(
        "add", int.class, int.class);
Object result = method.invoke(new Calculator(), 3, 4);
```

Đoạn minh họa giả định có import `java.lang.reflect.Method`, method được truy cập hợp lệ và xử lý checked exception. `getDeclaredMethod(...)` dùng **tên dưới dạng chuỗi** và đúng kiểu tham số để lấy metadata. Sau đó `invoke(...)` mới thực sự gọi method. Kết quả kiểu `int` được **boxing** thành `Integer` vì `Method.invoke` trả `Object`.

### C. MethodHandle

```java
MethodHandle handle = MethodHandles.lookup().findVirtual(
        Calculator.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
int result = (int) handle.invokeExact(new Calculator(), 3, 4);
```

Đoạn minh họa cần import `java.lang.invoke.*` và xử lý `Throwable`. `findVirtual` tìm instance method có **return type là `int`** và **hai tham số `int`**. `MethodHandle` chưa gắn receiver nên khi gọi, `Calculator` là đối số đầu tiên. `invokeExact` đòi hỏi kiểu tĩnh tại call site khớp chính xác kiểu handle; kết quả là `int`, không cần đi qua một kết quả `Object` do API trả về như `Method.invoke`.

Lưu ý: MethodHandle cũng có thể dùng để tìm constructor, getter/setter, static method, default method và xây tổ hợp lời gọi bằng các phép thích nghi handle. Ví dụ trong bài tập trung vào lời gọi method thường gặp.

## 2. So sánh chi tiết

| Tiêu chí | Gọi trực tiếp | `Method.invoke` | `MethodHandle` |
|---|---|---|---|
| Xác định method | Symbol Java trong mã nguồn | Tra cứu đối tượng `Method`, thường bằng tên chuỗi | Tra cứu hoặc chuyển đổi thành handle có `MethodType` |
| Kiểm tra kiểu | Compiler kiểm tra lời gọi | `invoke` kiểm tra receiver và đối số ở runtime | `invokeExact` yêu cầu chữ ký call site trùng chính xác; `invoke` có thể thích nghi |
| Kiểu trả về | Khai báo của method, ví dụ `int` | `Object`, primitive bị boxing, `void` là `null` | Kiểu trả về trong `MethodType`, ví dụ `int` |
| Receiver instance | Viết `receiver.method(...)` | Đối số đầu tiên của `Method.invoke` | Có thể là đối số đầu của `findVirtual` handle hoặc được bind sẵn |
| Chữ ký | Theo mã nguồn, có overload resolution | Thường `getMethod(name, paramTypes...)` | `MethodType` có kiểu trả về và các kiểu tham số |
| Exception từ method đích | Ném theo luồng Java thông thường | Bọc trong `InvocationTargetException` | MethodHandle invocation thông thường ném trực tiếp exception từ target |
| Access control | Theo luật Java trong source và runtime | Reflection kiểm tra access/module; có API thử mở quyền | `Lookup` có quyền theo lookup class/module; access kiểm tra khi tạo handle |
| Đổi tên method | Compiler thường bắt usage source cũ | Chuỗi cũ có thể thất bại khi chạy | Chuỗi dùng trong lookup cũng có thể thất bại khi chạy |
| Chuyển đổi đối số | Quy tắc Java compiler áp dụng cho lời gọi nguồn | Boxing/unboxing và primitive widening hợp lệ theo Reflection, không narrowing tùy ý | `invokeExact` không tự chuyển đổi; `invoke`/adapters hỗ trợ chuyển đổi hợp lệ |
| Phù hợp | Logic ứng dụng thông thường | Framework cần metadata, introspection, gọi linh hoạt | Framework/runtime cần lời gọi động theo kiểu, combinators và tối ưu hóa |

**Điểm then chốt:** MethodHandle không “lấy mất tính động” của Reflection. Khi dùng `findVirtual(Class, String, MethodType)`, bạn vẫn có tên method bằng chuỗi và vẫn có thể gặp lỗi lookup sau refactor. Ưu điểm chủ yếu là **mô hình invocation có kiểu rõ ràng và khả năng tổ hợp/adaptation**, không phải loại bỏ mọi rủi ro liên kết runtime.

## 3. Quá trình từ lookup đến invocation

Phân biệt hai bước độc lập:

```text
                  CHỌN METHOD                       THỰC THI
Gọi trực tiếp:  symbol/compiler               -> invokevirtual/invokestatic...
Reflection:     Class.getMethod(...)           -> Method.invoke(...)
MethodHandle:   Lookup.findVirtual/findStatic  -> invokeExact/invoke/...
                    |                                  |
               thông tin thành viên              chạy nghiệp vụ thật
```

Các API `Class.getMethod(...)` hay `Lookup.findVirtual(...)` dùng để tìm thành viên, **không tự gọi method nghiệp vụ**. Chỉ bước invocation mới thực hiện logic target. Việc tải/resolve lớp hoặc kiểm tra quyền khi lookup vẫn có thể gây lỗi và hoạt động JVM khác; không nên suy rằng lookup hoàn toàn vô tác động trong mọi môi trường.

### `Method.invoke` là phương thức trên một đối tượng metadata

Một `Method` là metadata của method khai báo. Để gọi instance method:

```java
Object value = method.invoke(receiver, arg1, arg2);
```

- `receiver` phải là instance tương thích với declaring class của method.
- Với static method, tham số receiver bị bỏ qua theo API; thường truyền `null` để minh bạch.
- Với method không tham số, có thể truyền không đối số, hoặc đối số mảng thích hợp.
- `Method.invoke` khai báo `Object` là kiểu trả về; cần cast/unbox khi muốn dùng kiểu cụ thể.
- Nếu invoked method ném exception, `invoke` ném `InvocationTargetException` chứa lỗi gốc trong `getCause()`.

**Cảnh báo varargs:** bản thân `Method.invoke(Object, Object...)` là một Java varargs API. Nếu truyền array làm **một tham số của method đích**, cần chuẩn bị đúng mảng `Object[]` chứa một phần tử, tránh compiler trải nhầm array thành danh sách tham số của `invoke`. Đây là vấn đề ở lớp gọi Reflection, không phải thay đổi signature của target.

### `MethodHandle` là điểm gọi có kiểu

`MethodHandle.type()` trả về một `MethodType` gồm return type và danh sách tham số **của chính handle**. Với instance method `int add(int,int)`, kết quả `findVirtual` chưa bind receiver có dạng:

```text
(Calculator,int,int)int
```

Đối số đầu tiên là receiver; hai đối số còn lại là tham số Java của method đích. Dùng `bindTo(calculator)` sẽ biến handle đó thành:

```text
(int,int)int
```

Khi đó caller không truyền receiver nữa. Binding làm thay đổi **chữ ký handle**, không sửa class hoặc tạo một method mới trong class đích.

Cũng cần phân biệt:

- `findVirtual(...)`: tìm virtual instance method; handle cần receiver và có virtual dispatch phù hợp.
- `findStatic(...)`: tìm static method; handle **không có receiver**.
- `findConstructor(...)`: handle biểu diễn thao tác tạo đối tượng; kiểu trả về handle là class mới tạo.
- `Lookup.unreflect(Method)`: có thể tạo MethodHandle từ `Method`, nhưng vẫn chịu điều kiện quyền truy cập phù hợp.
- `invokeExact(...)`: call site phải có tham số **và return type** trùng chính xác với `handle.type()`.
- `invoke(...)`: có thể áp dụng thích nghi kiểu theo `asType` trong các chuyển đổi được hỗ trợ; không thể coi là chuyển mọi kiểu tùy ý.
- `invokeWithArguments(...)`: giao diện linh hoạt lấy danh sách đối số như `Object`; thích hợp tiện ích/framework, nhưng không nên dùng để suy ra hiệu năng của `invokeExact`.
- Các combinator như `asType`, `bindTo`, `filterArguments`, `insertArguments` cho phép xây đường gọi phù hợp mà không cần viết wrapper method thông thường cho mọi trường hợp.

## 4. Ví dụ Java 17+ hoàn chỉnh, có output kiểm chứng

Chương trình bên dưới dùng một `Calculator` có instance method, static method và một method cố tình ném lỗi. Nó đối chiếu kết quả khi gọi trực tiếp, Reflection, MethodHandle chưa bind/bound, `invokeWithArguments`, đồng thời kiểm tra **hai kiểu lỗi khác nhau**.

Lưu thành **`InvocationComparisonDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationComparisonDemo {
    public static class Calculator {
        private final int offset;
        public Calculator(int offset) { this.offset = offset; }
        public int add(int left, int right) { return offset + left + right; }
        public int risky(int denominator) {
            if (denominator == 0) throw new IllegalArgumentException("zero");
            return offset / denominator;
        }
        public static String describe(String label, int value) {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) throws Throwable {
        Calculator calculator = new Calculator(10);
        System.out.println("direct: " + calculator.add(3, 4));

        Method method = Calculator.class.getMethod("add", int.class, int.class);
        Object reflected = method.invoke(calculator, 3, 4);
        System.out.println("reflection: " + reflected + " ("
                + reflected.getClass().getSimpleName() + ")");

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle virtual = lookup.findVirtual(
                Calculator.class, "add",
                MethodType.methodType(int.class, int.class, int.class));
        int exact = (int) virtual.invokeExact(calculator, 3, 4);
        System.out.println("handle exact: " + exact);
        System.out.println("unbound type: " + virtual.type());

        MethodHandle bound = virtual.bindTo(calculator);
        System.out.println("bound type: " + bound.type());
        int boundValue = (int) bound.invokeExact(3, 4);
        System.out.println("handle bound: " + boundValue);
        Object generic = bound.invokeWithArguments(3, 4);
        System.out.println("handle generic: " + generic);

        MethodHandle staticHandle = lookup.findStatic(
                Calculator.class, "describe",
                MethodType.methodType(String.class, String.class, int.class));
        String label = (String) staticHandle.invokeExact("sum", 17);
        System.out.println("static handle: " + label);

        try {
            method.invoke(calculator, "3", 4);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "reflection wrong argument: IllegalArgumentException");
        }
        try {
            long wrong = (long) bound.invokeExact(3, 4);
            System.out.println("unreachable: " + wrong);
        } catch (WrongMethodTypeException e) {
            System.out.println(
                    "handle wrong signature: WrongMethodTypeException");
        }

        Method risky = Calculator.class.getMethod("risky", int.class);
        try {
            risky.invoke(calculator, 0);
        } catch (InvocationTargetException e) {
            System.out.println("reflection target error: "
                    + e.getCause().getClass().getSimpleName());
        }
        MethodHandle riskyHandle = lookup.findVirtual(
                Calculator.class, "risky",
                MethodType.methodType(int.class, int.class));
        try {
            int unused = (int) riskyHandle.invokeExact(calculator, 0);
            System.out.println("unreachable: " + unused);
        } catch (IllegalArgumentException e) {
            System.out.println("handle target error: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 InvocationComparisonDemo.java
java InvocationComparisonDemo
```

**Stdout thực tế của chương trình trên:**

```text
direct: 17
reflection: 17 (Integer)
handle exact: 17
unbound type: (Calculator,int,int)int
bound type: (int,int)int
handle bound: 17
handle generic: 17
static handle: sum=17
reflection wrong argument: IllegalArgumentException
handle wrong signature: WrongMethodTypeException
reflection target error: IllegalArgumentException
handle target error: IllegalArgumentException
```

Ví dụ đã được biên dịch với `javac --release 17` và chạy để đối chiếu stdout; không yêu cầu phụ thuộc ngoài JDK.

### Đọc từng kết quả

1. `Calculator(10).add(3, 4)` trả `10 + 3 + 4 = 17` ở cả ba đường gọi hợp lệ.
2. Reflection trả `Object` mang giá trị runtime `Integer(17)`. Trong Java source, `invoke` nhận đối số primitive qua varargs `Object...`, nên cần boxing khi đóng gói đối số.
3. Handle chưa bind có chữ ký `(Calculator,int,int)int`. `invokeExact(calculator, 3, 4)` cần receiver và hai số nguyên `int`.
4. `bindTo(calculator)` cố định receiver; chữ ký trở thành `(int,int)int`.
5. `invokeWithArguments(3, 4)` nhận cách truyền linh hoạt, trả giá trị trong dạng `Object`, nên ở ví dụ nhận `17` qua `Object generic`.
6. `findStatic` có chữ ký `(String,int)String` và không nhận `Calculator` làm receiver.
7. Truyền chuỗi `"3"` cho Reflection method yêu cầu `int` bị từ chối với `IllegalArgumentException`. Reflection không tự parse văn bản thành số nguyên.
8. Dòng `long wrong = (long) bound.invokeExact(3, 4)` cố tình dùng **return type của call site là `long`**, nhưng handle trả `int`. Điều đó dẫn đến `WrongMethodTypeException`, kể cả khi đối số `int` đều đúng.
9. `risky(0)` thực sự ném `IllegalArgumentException`. Qua `Method.invoke`, lỗi target được bọc trong `InvocationTargetException`. Qua MethodHandle, lỗi target đi thẳng ra ngoài trong trường hợp này. Hai dòng cùng in tên `IllegalArgumentException` vì code chỉ in **cause hoặc exception thật**, không in lớp wrapper của Reflection.

## 5. Phân biệt invokeExact, invoke và invokeWithArguments

Ba cách dùng MethodHandle không thể hoán đổi một cách tùy ý.

### invokeExact: ràng buộc chặt kiểu tĩnh tại call site

```java
MethodHandle h = MethodHandles.lookup().findStatic(
        Integer.class, "sum",
        MethodType.methodType(int.class, int.class, int.class));
int value = (int) h.invokeExact(2, 3);
```

Đây là đoạn minh họa riêng, yêu cầu xử lý `Throwable`, và `Integer.sum(int,int)` là static method. Trình biên dịch Java gán cho call site chữ ký gồm hai `int` và kết quả `int`. Nếu viết `Object value = h.invokeExact(2, 3)`, return type ở call site sẽ là `Object` và **không khớp** handle trả `int`, dẫn đến `WrongMethodTypeException` khi chạy. Ép kiểu `(int)` ở mã nguồn có ý nghĩa thật đối với kiểu tĩnh được ghi tại call site; nó không phải cast trang trí.

### invoke: có thể thích nghi nhưng vẫn có giới hạn

```java
int value = (int) h.invoke(2, 3);
```

`invoke` không bắt buộc khớp tuyệt đối như `invokeExact` và có thể vận dụng quy tắc conversion thích hợp của MethodHandle. Tuy nhiên không phải mọi khác biệt đều được hỗ trợ, và chi phí/thành công tùy loại chuyển đổi. Có thể dùng `h.asType(desiredMethodType)` khi cần tạo adapter có chữ ký mục tiêu rõ ràng.

### invokeWithArguments: thuận tiện cho danh sách runtime

```java
Object value = h.invokeWithArguments(2, 3);
```

Đoạn này hữu dụng cho framework có danh sách đối số dạng `Object[]` hoặc `List<?>`. Nó thường có nhiều công việc thích nghi/đóng gói hơn một lời gọi `invokeExact` với kiểu ổn định, nên không nên dùng kết quả đo của nó để suy ra hiệu năng tối đa của MethodHandle.

Cả ba snippet này giả định `h` nằm trong phạm vi phù hợp, có imports liên quan và exception được xử lý. Một chương trình đầy đủ đã có ở mục 4.

## 6. Boxing, primitive và overload là nguồn lỗi phổ biến

### Method.invoke

Giả sử method đích có chữ ký `int sum(int,int)`:

- `Method.invoke(target, 2, 3)` cho phép primitive arguments được boxing trước khi đi qua `Object...`; Reflection thực hiện chuyển đổi tương thích để gọi method đích.
- Trả về `int` được boxing thành `Integer` ở lớp kết quả `Object`.
- Nếu method đích trả `void`, kết quả `Method.invoke` là `null`.
- Passing `null` vào tham số primitive không hợp lệ.
- Truyền `Integer` khi tham số yêu cầu `long` có thể được unbox và primitive widening theo quy tắc Reflection; truyền `Long` khi yêu cầu `int` không tự narrowing. Truyền `String` không tự parse thành số.

### getMethod lookup phải khớp kiểu tham số

```java
Method m = Calculator.class.getMethod("add", int.class, int.class);
```

`getMethod("add", Integer.class, Integer.class)` **không tương đương**, dù Java source có autoboxing. Phần lookup bằng `getMethod` không thực hiện overload resolution linh hoạt như compiler. MethodHandle lookup còn thêm **return type** vào `MethodType`.

### Lưu ý generic và array

Java generic phần lớn bị xóa kiểu ở bytecode (type erasure), nên Reflection và MethodHandle lookup dựa trên kiểu runtime đã erased, không phải tham số kiểu `List<String>` như symbol độc lập. MethodHandle có combinator cho array spreading/collecting; khi một method nhận `int[]` hoặc `Object[]`, hãy kiểm tra chữ ký handle và cách truyền varargs để không nhầm một mảng đối số với một đối số là mảng.

## 7. Access control, lỗi tra cứu và exception

### Quyền truy cập không tự biến mất khi dùng Reflection

- Gọi trực tiếp chịu access rule từ mã nguồn, package, module và tính hợp lệ ở runtime.
- `Class.getDeclaredMethod` **có thể tìm thấy** private method, nhưng điều đó không đồng nghĩa `Method.invoke` được phép gọi.
- `Method.setAccessible(true)` / `trySetAccessible()` có thể cho phép deep reflection **chỉ khi các quy tắc module/package cho phép**. Việc dùng bừa bãi có thể bị từ chối hoặc làm thiết kế khó kiểm soát.
- `MethodHandles.lookup()` tạo `Lookup` có quyền gắn với lớp gọi. `findVirtual`, `findStatic` và `unreflect` kiểm tra các điều kiện tiếp cận tương ứng.
- Với private members, `MethodHandles.privateLookupIn(...)` là lựa chọn có kiểm tra quyền và điều kiện mở package phù hợp, không phải cách vượt mọi module encapsulation.

**Không được coi Reflection hay MethodHandle là phương tiện vượt phân quyền.** Chúng là cơ chế gọi code trong những giới hạn runtime và module. Lúc thiết kế plugin/tool runner, việc gọi method nào còn cần allowlist và authorization ở mức ứng dụng.

### Tra cứu lỗi và gọi lỗi là hai nhóm riêng

| Tình huống | Reflection | MethodHandle |
|---|---|---|
| Tên method sai | `NoSuchMethodException` lúc `getMethod`/`getDeclaredMethod` | `NoSuchMethodException` lúc `Lookup.find...` |
| Không truy cập được | `IllegalAccessException` / `InaccessibleObjectException` tùy bước | `IllegalAccessException` lúc lookup hoặc chuyển handle |
| Receiver sai | Thường `IllegalArgumentException` tại `Method.invoke` | Lỗi liên quan mismatch kiểu/receiver tùy cơ chế invoke |
| Đối số không khớp | `IllegalArgumentException` tại `Method.invoke` | `WrongMethodTypeException` ở call site không thích hợp hoặc conversion-related exception |
| Method đích ném lỗi | `InvocationTargetException` bao lỗi gốc | Thường ném trực tiếp lỗi gốc từ target |
| Lớp đích khởi tạo thất bại | Có thể thấy `ExceptionInInitializerError`/lỗi liên quan | Cũng có thể gặp lỗi initialization, tùy lúc method đích được gọi |

Không nên bắt mọi `Exception` rồi báo “method không tồn tại”. Phân biệt lookup/permission/type mismatch với lỗi nghiệp vụ của target. Khi log exception từ `Method.invoke`, xem `InvocationTargetException.getCause()` nhưng vẫn nên giữ thông tin wrapper/context khi chẩn đoán.

## 8. Hiệu năng: so sánh đúng cách, tránh kết luận tuyệt đối

Thứ tự “gọi trực tiếp nhanh hơn MethodHandle nhanh hơn Reflection” đôi khi là một kinh nghiệm phổ biến, **không phải định luật cho mọi JDK và tình huống**.

Những yếu tố phải xem:

1. **JIT và inlining:** compiler có thể tối ưu lời gọi trực tiếp rất tốt khi biết target; MethodHandle với handle ổn định cũng có cơ hội tối ưu hóa mạnh. Reflection trong các JDK hiện đại cũng đã được cải tiến, không thể dựa mãi trên một benchmark cũ.
2. **Chi phí lookup:** nếu lấy `Method`/`MethodHandle` mới ở **mỗi vòng lặp**, bạn đang đo cả discovery và invocation, không chỉ chi phí gọi.
3. **Kiểu đối số và boxing:** Reflection phải đi qua giao diện `Object...`; `invokeWithArguments` cũng có chuyển đổi/đóng gói. Một benchmark trả `Object` và benchmark trả `int` chưa chắc so sánh cùng lượng công việc.
4. **Monomorphic vs megamorphic call sites:** số loại target và khả năng JVM biết trước handle ảnh hưởng rất lớn đến tối ưu hóa.
5. **Workload thật:** khi method đích thực hiện I/O, database, tính toán lớn hoặc network, overhead dispatch có thể nhỏ hơn nhiều so với công việc thực.
6. **JDK/runtime version và warmup:** JVM cần warmup; kết quả có thể khác trên Java 17, 21 hoặc JDK tương lai và giữa các triển khai.
7. **Benchmark dead-code elimination:** nếu không sử dụng kết quả, JIT có thể loại bỏ phần việc, khiến số đo vô nghĩa.

Một phép đo nghiêm túc nên dùng **JMH (Java Microbenchmark Harness)**, có warmup, nhiều lần đo, fork JVM và consumer/return value để giữ công việc quan sát được. Dùng cùng implementation và dữ liệu, **cache** method và handle nếu đó là cách ứng dụng thật hoạt động, tách riêng phép đo lookup. Sau đó mới so sánh latency/throughput kèm JDK và cấu hình JVM.

Nếu cần đo quyết định kiến trúc, đừng benchmark `Method.invoke` với target làm I/O trong khi nhánh khác chỉ cộng hai số. Cũng không nên khuyên chuyển mọi code sang MethodHandle chỉ vì một microbenchmark. Khả năng bảo trì và tính rõ ràng của code thường quan trọng hơn vài nanosecond trong nghiệp vụ bình thường.

## 9. Khi nào nên chọn cách nào?

| Nhu cầu | Gợi ý |
|---|---|
| Gọi method đã biết rõ ở compile time | **Gọi trực tiếp**, ưu tiên interface/method reference rõ ràng |
| Framework cần liệt kê annotation, method, generic metadata | **Reflection metadata**; gọi qua `Method.invoke` nếu cần tính linh hoạt |
| Runtime xây call chain động, cần adapters/combinators có kiểu | **MethodHandle** |
| Chạy cùng một method động nhiều lần với cấu trúc ổn định | Cân nhắc **cache MethodHandle** và đánh giá bằng benchmark thật |
| Input là tên class/method từ config | Reflection hoặc Lookup đều cần **validate allowlist, schema, quyền** |
| Code dùng proxy, serializer, DI hoặc RPC | Chọn công cụ theo framework và API contract, không chỉ theo lý thuyết tốc độ |
| Logic thông thường có API ổn định | Không thêm Reflection/MethodHandle nếu lời gọi trực tiếp đã đơn giản và phù hợp |

Một thực hành hay là tách giai đoạn **discovery** (đọc `Method`/annotation hoặc tìm `MethodHandle`) và **execution** (gọi thật). Khám phá metadata không nên tự chạy nghiệp vụ. Chỉ sau khi kiểm tra schema và quyền, executor mới thực hiện `invoke`.

## 10. Những lỗi người học thường gặp

- **Nhầm Reflection với MethodHandle:** `Method` là đối tượng metadata với API `invoke(Object,Object...)`; `MethodHandle` là callable với `MethodType`, có thể bind/adapt/combine. Chúng không phải cùng một abstraction.
- **Quên receiver của `findVirtual`:** handle ban đầu thường có receiver là đối số đầu tiên. `bindTo` mới cố định đối tượng.
- **Cho rằng `invokeExact` tự widening `int` thành `long`:** Không; cả return type của call site cũng phải khớp.
- **Cho rằng `Method.invoke` trả `int`:** API luôn trả `Object`; primitive được boxing.
- **Bỏ quên `InvocationTargetException`:** Reflection wrapper che cause thực sự nếu không mở ra.
- **Tra cứu bằng kiểu wrapper thay primitive:** `int.class` khác `Integer.class` khi lookup.
- **Bỏ qua access/module rules:** Tìm thấy private method không đồng nghĩa có quyền thực thi nó.
- **Tạo method/handle mới mỗi lần gọi rồi đo tốc độ:** Số liệu trộn lookup cost và invocation cost.
- **Tin rằng handle luôn nhanh hơn:** Cần test thực nghiệm trên JDK và workload thực tế.
- **Đổi tên method mà quên chuỗi runtime:** `getMethod("oldName",...)` và `findVirtual(...,"oldName",...)` đều có thể hỏng sau refactor nếu string không được cập nhật.

## 11. Tự kiểm tra

**Câu 1.** `Method.invoke(calculator, 3, 4)` gọi method trả `int`. Biến nhận là `Object` sẽ chứa kiểu nào?

Một `Integer` đã boxing giá trị `int`, giả sử method thực thi thành công.

**Câu 2.** Vì sao `findVirtual(Calculator.class, "add", methodType(int.class,int.class,int.class))` có kiểu handle `(Calculator,int,int)int`?

Vì virtual method cần **receiver** đầu tiên ở call site của handle, trước hai tham số của method gốc. `MethodType` truyền vào `findVirtual` mô tả signature Java của method **không tính receiver**, còn handle trả về có thêm receiver.

**Câu 3.** Có `Method` từ `getMethod` nghĩa là method đã chạy?

Không. Lookup trả metadata; `Method.invoke` mới yêu cầu thực thi.

**Câu 4.** Vì sao `long x = (long) bound.invokeExact(3,4)` lỗi dù có thể đổi một giá trị `int` sang `long` trong Java bình thường?

Vì `invokeExact` đòi hỏi **return type của call site là `int`** theo kiểu handle. Khai báo/cast sang `long` ngay tại call site làm chữ ký yêu cầu khác và ném `WrongMethodTypeException`. Nếu muốn chuyển đổi, nhận `int` trước rồi widening trong Java: `int tmp = (int) bound.invokeExact(3,4); long x = tmp;`, hoặc dùng adapter hợp lệ.

**Câu 5.** Khi method đích ném `IllegalArgumentException`, khác biệt nổi bật giữa Reflection và MethodHandle?

`Method.invoke` bọc target exception trong `InvocationTargetException`, còn invocation qua MethodHandle thông thường ném trực tiếp exception của target. Cần phân biệt lỗi thực thi với lỗi lookup/chữ ký.

**Câu 6.** Cách nào luôn nhanh nhất?

Không có đáp án cố định cho mọi JDK và ứng dụng. Với method đã biết tĩnh, thường ưu tiên direct call vì rõ ràng và compiler kiểm tra kiểu; nếu yêu cầu động, thử Reflection/MethodHandle theo chức năng, dùng JMH đo trên môi trường tương ứng.

## Tài liệu tham khảo

- Java SE 17 API: [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) — metadata, `invoke`, access, `InvocationTargetException`.
- Java SE 17 API: [`java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) — `invokeExact`, `invoke`, adapters.
- Java SE 17 API: [`java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — `findVirtual`, `findStatic`, `unreflect`, kiểm tra quyền.
- Java SE 17 API: [`java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html) — chữ ký kiểu của handle.
- [OpenJDK JMH](https://github.com/openjdk/jmh) — microbenchmark cho JVM; đo đúng workload và cấu hình thực tế.
- Java Language Specification §15.12 (method invocation), JVM Specification §6.5 (lệnh invoke), §5 (loading/linking/initialization).

**Ghi nhớ:** **Gọi trực tiếp** có cú pháp rõ và compiler kiểm tra kiểu; **`Method.invoke`** gọi động qua metadata, đối số/kết quả có giao diện `Object` và bọc exception đích; **`MethodHandle`** có chữ ký `MethodType`, hỗ trợ lời gọi kiểu chặt, binding và adaptation. Chọn theo nhu cầu và hành vi thực tế trước khi tối ưu hiệu năng.
