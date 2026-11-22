# 12.2. ConstantCallSite và đích gọi cố định

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **MethodHandle** (một handle gọi được), **CallSite** (điểm liên kết giữ target handle) và **ConstantCallSite** (điểm liên kết có target vĩnh viễn).
- Tạo một `ConstantCallSite` từ `MethodHandle` và kiểm chứng `type()`, `getTarget()`, `dynamicInvoker()`.
- Giải thích đúng nghĩa của chữ **constant**: *target handle/reference không đổi*; kết quả chạy và dữ liệu bên trong method đích **không bắt buộc bất biến**.
- Hiểu vì sao `setTarget(...)` luôn bị cấm, kể cả khi method mới có chữ ký tương thích.
- Mô tả vai trò của `ConstantCallSite` khi JVM liên kết lệnh `invokedynamic` qua bootstrap method, bao gồm điều kiện khớp `MethodType`.
- Nhận diện những lỗi thường gặp: `NullPointerException` khi target null, `WrongMethodTypeException` khi call site/handle không khớp, lỗi từ bootstrap hook và quyền truy cập khi tạo handle.
- Biết trường hợp nào nên dùng `MutableCallSite` hoặc `VolatileCallSite` thay vì cố đổi target của một `ConstantCallSite`.

## 1. Bối cảnh: MethodHandle, CallSite và invokedynamic khác nhau thế nào?

Trong Java, `MethodHandle` là đối tượng tham chiếu tới một phép toán có thể gọi: method, constructor, thao tác trường, hoặc một tổ hợp adapter. Mỗi handle mang một **`MethodType`**, gồm danh sách kiểu tham số và kiểu trả về.

Ví dụ, handle cho `static int add(int, int)` có kiểu:

~~~text
(int,int)int
~~~

Handle là **đích thực thi**. Tuy nhiên, `invokedynamic` trong bytecode không lưu trực tiếp tên method Java đích như một lời gọi `invokestatic` thông thường. Nó có bước **liên kết động** do JVM và bootstrap method thực hiện; kết quả linkage thường là một `CallSite`.

Một cách nhìn:

~~~text
Lệnh invokedynamic trong bytecode
             |
             | liên kết bằng bootstrap method
             v
           CallSite
             |
             | getTarget()
             v
         MethodHandle
             |
             v
       Thao tác thực thi
~~~

Các phần tử giữ vai trò riêng:

| Thành phần | Nó biểu diễn | Điều gì có thể ổn định hoặc thay đổi? |
| --- | --- | --- |
| `MethodHandle` | Một đối tượng có thể gọi được, mang `MethodType` | Handle là một giá trị; logic phía sau handle vẫn có thể đọc trạng thái thay đổi |
| `CallSite` | Điểm liên kết giữa dynamic invocation và target handle | Tùy subclass mà target có thể cố định hoặc được đổi |
| `ConstantCallSite` | CallSite với **target vĩnh viễn** | Target không được đổi sau khi construction xong |
| `MutableCallSite` | CallSite có target được cập nhật | Có thể `setTarget`; cần lưu ý publication giữa thread |
| `VolatileCallSite` | CallSite có target được cập nhật với ngữ nghĩa volatile | Hữu ích khi cần quan sát cập nhật liên luồng theo hợp đồng API |

**Quan trọng:** `CallSite` không phải là `java.lang.reflect.Method`. `Method` cung cấp Reflection metadata và phép `invoke` riêng; `CallSite` gắn với cơ chế `java.lang.invoke` và liên kết lời gọi.

### 1.1. “Constant” ở cấp độ nào?

`ConstantCallSite` **không** đồng nghĩa:

- Method đích phải là `static final`.
- Phương thức đích phải trả một hằng số.
- Các đối số được đóng băng.
- Mọi lần gọi phải trả cùng kết quả.
- Lời gọi sẽ không có side effects.
- JIT chắc chắn inline, hoặc mỗi lần gọi có chi phí bằng zero.

Nó chỉ bảo đảm **giá trị target MethodHandle của call site là cố định**. Khi target trỏ đến hàm `add`, `add(6,7)` và `add(10,20)` vẫn cho hai kết quả khác nhau. Nếu target được bind vào một receiver có field thay đổi, kết quả có thể đổi dù target handle chưa hề đổi.

## 2. API cốt lõi của ConstantCallSite

Trong Java SE 17, lớp nằm tại `java.lang.invoke.ConstantCallSite`, là subclass của `CallSite`. Constructor thông thường:

~~~java
// Chữ ký API dùng để tra cứu, không phải đoạn code độc lập:
public ConstantCallSite(MethodHandle target);
~~~

Một đối tượng `MethodHandle` **khác null** là điều kiện bắt buộc. Nếu target bằng `null`, constructor ném `NullPointerException`.

Các phương thức người dùng thường cần:

| API | Giá trị/hành vi | Ghi chú |
| --- | --- | --- |
| `site.type()` | `MethodType` của target | Có cả kiểu trả về |
| `site.getTarget()` | Target handle được ấn định khi xây dựng | Không đổi sau khi constructor hoàn tất |
| `site.dynamicInvoker()` | Trả về **chính permanent target** | Với `ConstantCallSite`, không phải wrapper để mỗi lần gọi tra target mới |
| `site.setTarget(handle)` | Luôn ném `UnsupportedOperationException` | Không thể relink, kể cả handle mới có cùng `MethodType` |

Hai phương thức `getTarget()` và `dynamicInvoker()` của `ConstantCallSite` là `final`, và việc gọi chúng khi protected constructor chưa hoàn thành có quy tắc đặc biệt sẽ xét ở mục 8.

Ví dụ minh họa:

~~~java
// Fragment: lookup có quyền truy cập method add và binary là đúng MethodType.
MethodHandle addHandle = lookup.findStatic(Example.class, "add", binary);
ConstantCallSite site = new ConstantCallSite(addHandle);
MethodHandle fixed = site.getTarget();
MethodHandle invoker = site.dynamicInvoker();
~~~

Đây là **fragment**, không phải chương trình độc lập. Cần biết class `Example`, `lookup`, `binary` và xử lý checked exceptions. Ví dụ chạy được hoàn chỉnh ở mục 4.

### 2.1. Vì sao dynamicInvoker() là target trực tiếp?

Với `MutableCallSite`, ý nghĩa của dynamic invoker là **đi qua target hiện tại**, vì target có thể bị thay. Với `ConstantCallSite`, target **không bao giờ đổi**, nên `dynamicInvoker()` có thể trả về trực tiếp MethodHandle đã lưu.

Với site bình thường đã được xây dựng thành công:

~~~java
// Fragment, so sánh danh tính reference của hai MethodHandle.
boolean same = site.dynamicInvoker() == site.getTarget();
~~~

Giá trị là `true` theo đặc tả `ConstantCallSite`. Nhưng **không** lấy kết luận đó áp cho mọi subclass `CallSite`; các call site có thể đổi target phải dùng cơ chế quan sát target mới.

### 2.2. type() là gì?

`CallSite.type()` trả `MethodType` của target. `ConstantCallSite` nhận kiểu ấy từ handle ban đầu. Ví dụ:

~~~text
MethodHandle:       (int,int)int
ConstantCallSite:   type() = (int,int)int
dynamicInvoker():   (int,int)int
~~~

Một `MethodType` bao gồm **kiểu trả về**. Với `MethodHandle.invokeExact`, call-site descriptor phải trùng **cả kiểu tham số và kiểu trả về** với kiểu handle. Chỉ truyền đúng số tham số là chưa đủ.

### 2.3. Vì sao setTarget không được phép?

`ConstantCallSite.setTarget(MethodHandle ignore)` được định nghĩa là **luôn ném `UnsupportedOperationException`**, bất kể handle đề nghị là gì. Nó **không** thử đổi target rồi rollback, cũng **không** cho phép đổi sang handle có cùng chữ ký.

~~~java
// Fragment: multiplyHandle có thể cùng kiểu (int,int)int với addHandle.
try {
    site.setTarget(multiplyHandle);
} catch (UnsupportedOperationException ex) {
    // ConstantCallSite không cho phép thay target.
}
~~~

Đừng bắt ngoại lệ rồi giả định target đã đổi. Lần gọi sau vẫn thực thi **target cũ**.

Nếu yêu cầu nghiệp vụ thực sự cần thay logic đích, phải **thiết kế từ đầu** với một loại call site mutable phù hợp, hoặc tạo một `ConstantCallSite` *mới* rồi thay nơi giữ reference tới nó. Việc thay một reference bên ngoài không làm call site cũ bị relink.

## 3. Sơ đồ vòng đời của một ConstantCallSite

~~~text
1. Chọn MethodType và tra cứu MethodHandle
               |
               v
2. new ConstantCallSite(target)
               |
               v
   target được cố định trong site
               |
               +----> type()      -> kiểu target
               |
               +----> getTarget() -> target đã cố định
               |
               +----> dynamicInvoker() -> cùng target
               |
               v
3. Gọi MethodHandle nhiều lần
               |
               v
   Kết quả phụ thuộc đối số / trạng thái của target
               |
               v
4. setTarget(other) -> UnsupportedOperationException
               |
               v
   Target cũ vẫn được giữ nguyên
~~~

`ConstantCallSite` có thể tồn tại độc lập với bytecode `invokedynamic`; đối tượng như vậy đôi khi được gọi là một *free-floating call site*. Tạo object bằng `new ConstantCallSite(...)` **không tự biến** một lời gọi Java source nào đó thành opcode `invokedynamic`. Để hiểu liên kết bytecode thật, cần xét bootstrap method ở mục 7.

## 4. Chương trình Java 17+: target cố định, getTarget, dynamicInvoker và lỗi thay target

Lưu file **ConstantSiteBasicsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteBasicsDemo {
    static int add(int x, int y) { return x + y; }
    static int multiply(int x, int y) { return x * y; }

    static final class Multiplier {
        int factor = 2;
        int apply(int n) { return n * factor; }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType binary = MethodType.methodType(int.class, int.class, int.class);
        MethodHandle addHandle = lookup.findStatic(
                ConstantSiteBasicsDemo.class, "add", binary);
        MethodHandle multiplyHandle = lookup.findStatic(
                ConstantSiteBasicsDemo.class, "multiply", binary);

        ConstantCallSite site = new ConstantCallSite(addHandle);
        MethodHandle invoker = site.dynamicInvoker();
        CallSite general = site;
        System.out.println("type=" + site.type());
        System.out.println("targetSame=" + (site.getTarget() == addHandle));
        System.out.println("invokerSameTarget=" + (invoker == site.getTarget()));
        System.out.println("viaTarget=" + (int) site.getTarget().invokeExact(6, 7));
        System.out.println("viaInvoker=" + (int) invoker.invokeExact(6, 7));
        System.out.println("viaCallSite=" + (int) general.dynamicInvoker().invokeExact(6, 7));

        try {
            site.setTarget(multiplyHandle);
        } catch (UnsupportedOperationException ex) {
            System.out.println("setTarget=" + ex.getClass().getSimpleName());
        }
        System.out.println("afterSetAttempt=" + (int) invoker.invokeExact(6, 7));

        try {
            long wrong = (long) invoker.invokeExact(6, 7);
            System.out.println(wrong);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongReturn=" + ex.getClass().getSimpleName());
        }

        try {
            new ConstantCallSite(null);
        } catch (NullPointerException ex) {
            System.out.println("nullTarget=" + ex.getClass().getSimpleName());
        }

        Multiplier receiver = new Multiplier();
        MethodHandle bound = lookup.findVirtual(
                Multiplier.class, "apply",
                MethodType.methodType(int.class, int.class)).bindTo(receiver);
        ConstantCallSite stateSite = new ConstantCallSite(bound);
        MethodHandle stable = stateSite.dynamicInvoker();
        System.out.println("boundType=" + stateSite.type());
        System.out.println("beforeStateChange=" + (int) stable.invokeExact(9));
        receiver.factor = 3;
        System.out.println("afterStateChange=" + (int) stable.invokeExact(9));
        System.out.println("stillSameTarget=" + (stable == stateSite.getTarget()));
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 ConstantSiteBasicsDemo.java
java ConstantSiteBasicsDemo
~~~

Stdout:

~~~text
type=(int,int)int
targetSame=true
invokerSameTarget=true
viaTarget=13
viaInvoker=13
viaCallSite=13
setTarget=UnsupportedOperationException
afterSetAttempt=13
wrongReturn=WrongMethodTypeException
nullTarget=NullPointerException
boundType=(int)int
beforeStateChange=18
afterStateChange=27
stillSameTarget=true
~~~

### 4.1. Ba đường gọi cho cùng target

`getTarget()` trả `addHandle`, `dynamicInvoker()` cũng là handle đó. Dù biến được khai báo là `ConstantCallSite` hay được upcast thành `CallSite`, implementation thực tế vẫn là `ConstantCallSite`.

~~~text
site.getTarget()                ─┐
site.dynamicInvoker()          ─┼─> add(int,int)int
((CallSite) site).dynamicInvoker() ┘
~~~

Trong ví dụ, cả ba đều trả **13** cho `(6,7)`. Các phép so sánh `==` cũng chứng minh danh tính MethodHandle là cùng một reference, không chỉ đơn thuần “hai method có cùng logic”.

### 4.2. Bất biến sau nỗ lực thay target

`multiplyHandle` có cùng kiểu `(int,int)int` với `addHandle`. Điều đó **không** giúp `setTarget` được phép. Lời gọi:

~~~java
// Fragment:
site.setTarget(multiplyHandle);
~~~

ném `UnsupportedOperationException`; sau khi bắt lỗi, `invoker.invokeExact(6,7)` vẫn cho **13**, chứ không phải **42**.

Đừng suy luận rằng `setTarget` sẽ chỉ thất bại nếu chữ ký mới sai. **Trong ConstantCallSite, thao tác sửa target hoàn toàn bị cấm.**

### 4.3. Lỗi kiểu trả về của invokeExact

Handle `add` có kiểu `(int,int)int`. Biểu thức:

~~~java
// Fragment có chủ đích sai return type tại call site:
long wrong = (long) invoker.invokeExact(6, 7);
~~~

tạo call-site descriptor mong `long` thay vì `int`. `invokeExact` **không tự nới kiểu** từ `int` sang `long` tại đường gọi đó; ví dụ bắt được `WrongMethodTypeException`. Nếu muốn conversion hợp lệ, cần dùng `invoke` hoặc tạo adapter `asType` phù hợp, và vẫn phải hiểu descriptor tại call site.

### 4.4. Constructor cần target không null

`new ConstantCallSite(null)` ném `NullPointerException`. Không có khái niệm “site chưa có target, sau đó sẽ set sau” với constructor công khai này. Nếu cần thiết kế liên kết target đặc biệt gắn với chính site, API có một **protected constructor với hook**, trình bày ở mục 8.

## 5. “Target cố định” không có nghĩa “kết quả cố định”

Phần cuối chương trình định nghĩa receiver:

~~~java
static final class Multiplier {
    int factor = 2;
    int apply(int n) { return n * factor; }
}
~~~

Handle được tạo từ method `apply(int)` rồi **bindTo(receiver)**:

~~~java
// Fragment từ chương trình ở trên:
MethodHandle bound = lookup.findVirtual(
        Multiplier.class, "apply",
        MethodType.methodType(int.class, int.class)).bindTo(receiver);
ConstantCallSite stateSite = new ConstantCallSite(bound);
~~~

Ban đầu:

~~~text
receiver.factor = 2
fixedHandle.invokeExact(9) -> 18
~~~

Sau khi cùng chương trình đổi:

~~~text
receiver.factor = 3
fixedHandle.invokeExact(9) -> 27
~~~

`stateSite.getTarget()` vẫn giữ cùng MethodHandle. Bất biến của `ConstantCallSite` là **không thay handle được lưu**, không phải đóng băng heap object được handle tham chiếu.

Phân biệt bốn lớp trạng thái:

| Thứ gì có thể thay đổi? | Với ConstantCallSite |
| --- | --- |
| **Reference tới target handle của site** | **Không** |
| **Các đối số truyền vào handle** | Có |
| **Trạng thái của receiver mà handle bind tới** | Có, nếu object và logic cho phép |
| **Kết quả/side effect của method đích** | Có thể thay đổi |
| **Kiểu của call site `type()`** | Không |

**Lưu ý liên luồng:** Ví dụ đổi `factor` từ cùng một thread. Nếu receiver được chia sẻ giữa các thread, việc đọc/ghi trạng thái đó vẫn phải tuân thủ Java Memory Model và cơ chế đồng bộ phù hợp. Một `ConstantCallSite` **không biến field được bind thành volatile**, cũng không tạo đồng bộ giữa các thread.

### 5.1. Có thể “thay đích” gián tiếp bằng target có nhánh không?

Có thể thiết kế **một MethodHandle cố định** nhưng bên trong nó gọi một dispatcher đọc cấu hình rồi tự chọn logic A/B. Khi cấu hình thay đổi, **hành vi** của dispatcher có thể đổi mà **target handle của ConstantCallSite** vẫn nguyên. Đó là thay đổi *bên trong thao tác*, không phải relink CallSite.

Nếu thực sự cần một call site có target thay đổi để tối ưu inline cache hoặc chuyển thuật toán tại runtime, sử dụng `MutableCallSite`/`VolatileCallSite` sẽ thể hiện ý đồ rõ ràng hơn thay vì giấu retargeting vào dispatcher không có hợp đồng tương đương.

## 6. Vì sao một target cố định hữu ích?

Trong một liên kết được sử dụng lặp lại nhiều lần, tính bất biến của target giúp đơn giản hóa việc suy luận:

1. Không có giao thức `setTarget` để cập nhật điểm liên kết.
2. Không cần cơ chế publication riêng cho **việc thay target**, vì target không thay.
3. `ConstantCallSite.dynamicInvoker()` trả thẳng permanent target, thay vì phải tra current target mỗi lần.
4. JVM có thể có cơ hội tối ưu khi biết liên kết ổn định, tùy call site, MethodHandle chain và JIT.

Nhưng **đừng cam kết** rằng `ConstantCallSite` luôn nhanh hơn mọi `MutableCallSite` một hệ số xác định, hoặc mọi phép gọi của nó được inline. Hiệu năng phụ thuộc chữ ký, adapter, ổn định type profile, thời gian warmup, phương thức đích và workload.

Một tình huống hợp lý: hệ thống đã biết tại thời điểm liên kết rằng operation `upper` luôn ánh xạ tới một handle duy nhất. Hệ thống có thể trả một `ConstantCallSite` và không cần infrastructure cập nhật target về sau.

Một tình huống không hợp lý: ứng dụng muốn **hot swap** cách xử lý sau mỗi gói cấu hình. Cố dùng `setTarget` của `ConstantCallSite` là sai ngay theo hợp đồng API.

## 7. ConstantCallSite ở ranh giới invokedynamic và bootstrap method

Khi JVM xử lý một lệnh `invokedynamic` trong bytecode, nó liên kết call site dựa trên **bootstrap method** được mô tả ở constant pool/BootstrapMethods attribute và bộ tham số liên kết của call site.

Dạng bootstrap method tiêu biểu:

~~~java
// Chữ ký minh họa (có thể có thêm static bootstrap arguments):
static CallSite bootstrap(MethodHandles.Lookup caller,
                          String name,
                          MethodType siteType) throws Throwable;
~~~

- `caller` là `Lookup` đại diện ngữ cảnh liên kết do JVM cung cấp.
- `name` là tên động được biểu diễn trong bytecode, có thể dùng để chọn operation.
- `siteType` là kiểu yêu cầu tại **vị trí `invokedynamic`**, không chỉ kiểu thực tế của một method Java bất kỳ.
- Bootstrap chọn/điều chỉnh target handle, rồi trả một `CallSite`.
- Nếu trả `ConstantCallSite`, liên kết đó **vĩnh viễn gắn với target** đã trả; không thể relink bằng `setTarget`.

Đây là sơ đồ khái niệm:

~~~text
invokedynamic "upper" (String)String
                    |
                    | Bootstrap Lookup, name="upper", type=(String)String
                    v
            bootstrap(...)
                    |
                    | findStatic("upper", (String)String)
                    v
            MethodHandle target
                    |
                    v
           new ConstantCallSite(target)
                    |
                    v
    JVM dùng liên kết bất biến cho call site này
~~~

Nếu handle được chọn không trùng `siteType`, bootstrap có thể sử dụng **`asType`** khi conversion hợp lệ; nếu không thể điều chỉnh kiểu, quá trình chuẩn bị liên kết thất bại. `ConstantCallSite` **không tự sửa** chữ ký sai.

### 7.1. Chương trình Java 17+: gọi một bootstrap method theo cách minh họa

Lưu file **ConstantSiteLinkDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteLinkDemo {
    private static String upper(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name,
                                     MethodType siteType)
            throws ReflectiveOperationException {
        if (!name.equals("upper")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }
        MethodHandle target = caller.findStatic(
                ConstantSiteLinkDemo.class, "upper",
                MethodType.methodType(String.class, String.class));
        return new ConstantCallSite(target.asType(siteType));
    }

    public static void main(String[] args) throws Throwable {
        MethodType wanted = MethodType.methodType(String.class, String.class);
        CallSite linked = bootstrap(MethodHandles.lookup(), "upper", wanted);
        System.out.println("linked.type=" + linked.type());
        System.out.println("linked.class=" + linked.getClass().getSimpleName());
        MethodHandle invoker = linked.dynamicInvoker();
        System.out.println("first=" + (String) invoker.invokeExact("hello"));
        System.out.println("second=" + (String) invoker.invokeExact("java"));

        try {
            bootstrap(MethodHandles.lookup(), "missing", wanted);
        } catch (IllegalArgumentException ex) {
            System.out.println("badName=" + ex.getClass().getSimpleName());
        }
        try {
            MethodType impossible = MethodType.methodType(String.class, int.class);
            bootstrap(MethodHandles.lookup(), "upper", impossible);
        } catch (WrongMethodTypeException ex) {
            System.out.println("badType=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 ConstantSiteLinkDemo.java
java ConstantSiteLinkDemo
~~~

Stdout:

~~~text
linked.type=(String)String
linked.class=ConstantCallSite
first=HELLO
second=JAVA
badName=IllegalArgumentException
badType=WrongMethodTypeException
~~~

**Giới hạn của ví dụ:** Code Java source **tự gọi `bootstrap(...)`**, rồi trực tiếp gọi `dynamicInvoker()`. Nó **không phát ra một lệnh `invokedynamic` tùy chỉnh**. Phải phân biệt **mô phỏng logic liên kết** (ví dụ này) với **JVM thực sự liên kết một opcode invokedynamic** (bytecode do compiler hoặc bộ sinh bytecode tạo ra).

### 7.2. Vì sao bootstrap phải khớp type?

`wanted` là `(String)String`, đúng kiểu của handle `upper`; do đó `target.asType(wanted)` hợp lệ. Site nhận đúng kiểu, `dynamicInvoker` cũng là handle mang kiểu ấy và `invokeExact("hello")` trả `HELLO`.

Nhánh `badName` minh họa lỗi do **quy tắc nghiệp vụ** trong bootstrap: không có operation `missing`, nên code chủ động ném `IllegalArgumentException`.

Nhánh `badType` đòi target kiểu `(int)String`. Không có phép chuyển đổi `int` vào tham số `String` theo quy tắc `MethodHandle.asType`, nên ném `WrongMethodTypeException`.

Điểm phân biệt:

- **Sai tên operation** là lỗi lựa chọn target theo policy của bootstrap.
- **Sai MethodType** là lỗi liên kết/chuyển đổi chữ ký.
- **Lỗi quyền lookup** có thể đến từ `Lookup.findStatic` hoặc các thao tác lookup khác.
- Khi **JVM** thực sự xử lý `invokedynamic`, các lỗi bootstrap/linkage có thể được biểu diễn qua **`BootstrapMethodError`** (hoặc các lỗi liên quan theo JVMS), không nhất thiết là exception trực tiếp mà đoạn Java gọi bootstrap thủ công in ra.

Không tự kết luận rằng mọi lỗi trong handler đều là `WrongMethodTypeException`; ngoại lệ từ method đích sau khi đã liên kết thành công là một câu chuyện khác.

### 7.3. Bootstrap được gọi lại ở mỗi lần invoke không?

Khi một vị trí invokedynamic đã liên kết thành công, JVM duy trì linkage của vị trí đó; lời gọi sau sử dụng liên kết, không phải một vòng tìm tên method và chạy logic bootstrap ở **mỗi lần gọi**.

Với `ConstantCallSite`, target của vị trí liên kết là vĩnh viễn. Nếu target được thực thi với các input khác nhau, các input không khiến site relink. Nếu cần một liên kết tự cập nhật target, cần loại call site cho phép cập nhật, không phải `ConstantCallSite`.

**Không đồng nhất** “một lần liên kết vị trí bytecode” với “toàn ứng dụng có đúng một site”. Nhiều vị trí bytecode, class loader hoặc ngữ cảnh liên kết có thể có nhiều call site riêng, kể cả cùng một tên động.

## 8. Protected constructor: tạo target bằng createTargetHook

Ngoài constructor công khai nhận handle, `ConstantCallSite` có một **protected constructor**:

~~~java
// Chữ ký API tham khảo:
protected ConstantCallSite(MethodType targetType,
                           MethodHandle createTargetHook) throws Throwable;
~~~

Nó dành cho subclass cần tạo target trong quá trình khởi tạo, đặc biệt khi target phải được **bind vào chính đối tượng CallSite**.

Theo hợp đồng, constructor gọi hook như:

~~~text
(MethodHandle) createTargetHook.invoke(this)
~~~

Hook phải trả về `MethodHandle` có **MethodType chính xác bằng `targetType`**. Trong thời gian hook chạy, đối tượng ConstantCallSite **chưa khởi tạo xong**:

- Có thể gọi `site.type()` để biết kiểu mà site sẽ có.
- Gọi `site.getTarget()` hoặc cố dùng target, kể cả `dynamicInvoker()`, khi chưa hoàn tất sẽ ném `IllegalStateException`.
- Không được để target chưa khởi tạo rồi trả về từ constructor thành công.
- Hook có thể bỏ qua site và trả một handle tĩnh; nhưng trường hợp chính đáng thường là cần binding phức tạp cho subclass.

Protected constructor này **không** làm target trở nên mutable. Sau khi xây dựng, site vẫn cố định vĩnh viễn.

### 8.1. Chương trình Java 17+: quan sát trạng thái chưa khởi tạo

Lưu file **ConstantSiteHookDemo.java**:

~~~java
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class ConstantSiteHookDemo {
    static int doubleIt(int value) { return value * 2; }

    static MethodHandle makeTarget(ConstantCallSite site)
            throws ReflectiveOperationException {
        System.out.println("hook.type=" + site.type());
        try {
            site.getTarget();
        } catch (IllegalStateException ex) {
            System.out.println("hook.uninitialized=" + ex.getClass().getSimpleName());
        }
        return MethodHandles.lookup().findStatic(
                ConstantSiteHookDemo.class, "doubleIt",
                MethodType.methodType(int.class, int.class));
    }

    static MethodHandle makeWrongTarget(ConstantCallSite site)
            throws ReflectiveOperationException {
        return MethodHandles.lookup().findStatic(
                ConstantSiteHookDemo.class, "doubleIt",
                MethodType.methodType(int.class, int.class));
    }

    static final class HookedSite extends ConstantCallSite {
        HookedSite(MethodType type, MethodHandle factory) throws Throwable {
            super(type, factory);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle factory = lookup.findStatic(
                ConstantSiteHookDemo.class, "makeTarget",
                MethodType.methodType(MethodHandle.class, ConstantCallSite.class));
        MethodType wanted = MethodType.methodType(int.class, int.class);
        HookedSite site = new HookedSite(wanted, factory);
        System.out.println("final.type=" + site.type());
        System.out.println("result=" + (int) site.dynamicInvoker().invokeExact(21));

        MethodHandle mismatchFactory = lookup.findStatic(
                ConstantSiteHookDemo.class, "makeWrongTarget",
                MethodType.methodType(MethodHandle.class, ConstantCallSite.class));
        try {
            new HookedSite(MethodType.methodType(long.class, long.class),
                    mismatchFactory);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongHookTarget=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstantSiteHookDemo.java
java ConstantSiteHookDemo
~~~

Stdout:

~~~text
hook.type=(int)int
hook.uninitialized=IllegalStateException
final.type=(int)int
result=42
wrongHookTarget=WrongMethodTypeException
~~~

### 8.2. Phân tích protected hook

1. `HookedSite` là subclass nên được gọi constructor `protected`.
2. `factory` là handle nhận một `ConstantCallSite` và trả `MethodHandle`.
3. Trong hook, `site.type()` hoạt động và trả `(int)int`, nhưng `site.getTarget()` báo `IllegalStateException` vì target chưa hoàn tất.
4. Hook trả handle tới `doubleIt(int)` có kiểu **đúng `(int)int`**, nên constructor hoàn thành và `invokeExact(21)` trả **42**.
5. Thử dùng `targetType=(long)long` nhưng hook trả `(int)int` bị **`WrongMethodTypeException`**. Đây là lỗi ràng buộc kiểu **khi tạo site**, không phải lỗi ở lời gọi sau.

### 8.3. Các trường hợp lỗi khác từ hook

Javadoc mô tả những trường hợp quan trọng:

| Tình huống ở hook | Lỗi có thể xảy ra |
| --- | --- |
| Hook không thể được gọi với tham số phù hợp | `WrongMethodTypeException` |
| Hook trả handle có `MethodType` không bằng targetType | `WrongMethodTypeException` |
| Hook trả `null` | `NullPointerException` |
| Hook trả object không phải `MethodHandle` | `ClassCastException` |
| Hook ném ngoại lệ khác | Ngoại lệ từ hook có thể lan ra theo hợp đồng |
| Dùng `getTarget/dynamicInvoker` trước khi constructor hoàn tất | `IllegalStateException` |

Vì protected hook chạy khi object còn trong quá trình khởi tạo, tránh **để lộ `this`** cho thread hoặc thành phần khác. Việc binding có thể làm được nhưng không thay thế quy tắc an toàn xây dựng object.

**Đánh giá thực tế:** Phần lớn code ứng dụng chỉ cần constructor công khai `new ConstantCallSite(target)`. Dùng protected hook khi có yêu cầu kỹ thuật cụ thể; độ phức tạp khởi tạo cao hơn và có thêm rủi ro về trạng thái chưa hoàn chỉnh.

## 9. So sánh ba loại CallSite

| Thuộc tính | `ConstantCallSite` | `MutableCallSite` | `VolatileCallSite` |
| --- | --- | --- | --- |
| Target có thể đổi sau construction? | **Không** | **Có** | **Có** |
| `setTarget` | Luôn ném `UnsupportedOperationException` | Hợp lệ với target có cùng MethodType | Hợp lệ với target có cùng MethodType |
| `dynamicInvoker()` | Trả permanent target trực tiếp | Theo dõi target hiện tại của site | Theo dõi target hiện tại với volatile semantics |
| Mục đích điển hình | Liên kết cố định, target không bao giờ relink | Cập nhật target qua runtime | Cập nhật target với visibility liên luồng rõ ràng |
| Giao thức publication cho target mới | Không cần, vì không có target mới | Cần tuân theo quy tắc `MutableCallSite`, có thể dùng `syncAll` khi thích hợp | Theo quy tắc volatile của API |

Đừng chọn `ConstantCallSite` chỉ vì từ “dynamic” trong `invokedynamic`. “Liên kết động” nói về **thời điểm/cách chọn target**, không nhất thiết target sẽ **thay đổi** trong suốt thời gian chạy.

Ví dụ: một bootstrap có thể chọn implementation dựa vào tên và signature **lúc liên kết**, rồi không thay nữa; `ConstantCallSite` rất phù hợp. Ngược lại, một runtime có speculative inline cache cần cập nhật dispatcher khi kiểu receiver thay đổi có thể cần call site mutable.

### 9.1. MutableCallSite và VolatileCallSite không làm kiểu tùy ý đổi

Dù target có thể đổi, `CallSite.type()` vẫn bất biến. Một `MutableCallSite` kiểu `(int,int)int` không được đổi trực tiếp thành target `(String)String`. Muốn thay logic mà giữ shape, hãy làm adapter có cùng `MethodType` trước khi `setTarget`.

Điều này giúp mỗi vị trí invokedynamic có **một call-site type ổn định** theo bytecode descriptor, trong khi implementation cụ thể bên dưới có thể thay đổi ở những loại call site cho phép.

## 10. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `new ConstantCallSite(null)` ném lỗi | Target không được phép null | Tạo MethodHandle hợp lệ trước khi xây site |
| `setTarget(...)` bị `UnsupportedOperationException` | Site là constant, **không mutable** | Chọn đúng loại CallSite từ đầu; không retry |
| `invokeExact` gặp `WrongMethodTypeException` | Descriptor tại call site không trùng `MethodType`, kể cả return type | In `site.type()`, sửa cast/signature hoặc dùng adapter hợp lệ |
| `findStatic`/`findVirtual` bị `NoSuchMethodException` | Tên/chữ ký đích không chính xác | Đối chiếu method name, arity và return type |
| Lookup bị `IllegalAccessException` | Context lookup không có quyền với member | Dùng API/public lookup phù hợp; không cố vượt module bằng site |
| Bootstrap trả target sai kiểu | Không khớp `siteType` khi liên kết | Dùng `asType` khi phép chuyển đổi hợp lệ, nếu không thì sửa bootstrap contract |
| Hook trả null/sai loại | Hook không thỏa constructor contract | Trả MethodHandle đúng kiểu, không dùng placeholder |
| Hook dùng getTarget quá sớm | ConstantCallSite đang xây dựng | Chỉ dùng `type()` trong giai đoạn hook khi cần |
| Target vẫn giữ nguyên nhưng kết quả khác | Input hoặc trạng thái bên trong method đích thay đổi | Kiểm tra logic của target, không quy lỗi cho relinking |
| Lời gọi có exception nghiệp vụ | Method đích ném exception | Xử lý error theo contract của method đích, phân biệt với linkage |
| Test in kết quả không như mong đợi sau `setTarget` | Giả định phép set thành công | Với ConstantCallSite, set luôn thất bại và target cũ vẫn giữ |

Một checklist debug ngắn:

~~~text
1. site.getClass() có đúng ConstantCallSite?
2. site.type() có bằng chữ ký call site đang đòi?
3. site.getTarget().type() có tương đương site.type()?
4. MethodHandle được tạo từ lookup có đúng quyền và đúng method?
5. Lệnh invokeExact có đúng kiểu trả về ở Java call site?
6. Có đang mong thay target vốn không thể thay?
7. Target có đọc một object/field đang thay đổi không?
8. Nếu là invokedynamic thực: bootstrap đã trả site/type hợp lệ chưa?
~~~

Với `ConstantCallSite` được xây dựng thành công theo constructor công khai, `site.type()` và `site.getTarget().type()` luôn tương ứng. Nếu nhận dữ liệu không hợp lệ hoặc kết quả không mong muốn, nên kiểm tra **chuỗi adapter, input và trạng thái method đích** trước.

## 11. Bảo mật, concurrency và hiệu năng

### 11.1. ConstantCallSite không cấp quyền truy cập mới

`MethodHandles.Lookup` phải có quyền tra cứu/khởi tạo method handle đích theo quy tắc Java và module. `ConstantCallSite` chỉ giữ target đã nhận; nó **không tự cấp phép** vào private member. Nếu một bootstrap tìm method private không đúng quyền, lỗi có thể xảy ra tại **lookup/linking**, trước khi có site hợp lệ.

Tương tự, không nhận tên class/method tùy ý từ input không đáng tin rồi gọi `findStatic` cho tất cả. Hệ thống plugin nên định nghĩa allowlist các operation và policy access rõ ràng.

### 11.2. Thread safety và state của target

Bản thân target reference không đổi; điều đó giúp liên kết ổn định giữa thread. Nhưng một target đọc `Map`, field hoặc một object thay đổi thì các quy tắc thread safety **vẫn áp dụng cho dữ liệu đó**. Ví dụ `Multiplier.factor` của chương trình không dùng volatile/synchronization, nên khi nhiều thread tham gia sẽ cần thiết kế đồng bộ phù hợp.

**Không đánh đồng:** “constant call site” với “immutable computation”. Kết quả có thể đọc clock, truy cập network, tăng counter, hoặc phụ thuộc state, dù target handle cố định.

### 11.3. Có thể khẳng định nhanh hơn mọi kiểu gọi khác không?

Không. `ConstantCallSite` tạo cơ hội tối ưu nhờ liên kết vĩnh viễn, nhưng không có một overhead cố định cho mọi workload. Nếu bạn muốn đánh giá hiệu năng:

- Tạo method handle, adapter và call site **ngoài vòng lặp đo** nếu ứng dụng làm như vậy.
- Dùng JMH hoặc benchmark có warmup/blackhole để tránh JIT loại công việc.
- So sánh **cùng hành vi**, cùng dữ liệu và cùng return type.
- Đừng lấy một kết quả của ví dụ tính 6+7 làm bằng chứng hiệu năng.
- Xem cả hiệu năng và nhu cầu relink: một `ConstantCallSite` không thể thay target, dù nhanh.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `ConstantCallSite` có làm cho method đích luôn trả một kết quả giống nhau không?

**Đáp án:** Không. Nó giữ **target MethodHandle cố định**; method đích vẫn nhận input và có thể đọc state thay đổi.

**Câu 2.** Có thể dùng `site.setTarget(newHandle)` khi newHandle có cùng `MethodType` không?

**Đáp án:** Không. Với `ConstantCallSite`, `setTarget` luôn ném `UnsupportedOperationException`, kể cả type trùng.

**Câu 3.** `site.dynamicInvoker()` có luôn là một wrapper đọc `getTarget()` mỗi lần không?

**Đáp án:** Không. Với `ConstantCallSite`, nó trả **permanent target trực tiếp**. Với loại mutable, dynamic invoker mới phải quan sát target hiện tại theo hợp đồng.

**Câu 4.** Tại sao `long x = (long) handle.invokeExact(6,7)` có thể lỗi khi handle thực là `(int,int)int`?

**Đáp án:** Vì kiểu trả về tại call site là `long`, khác `int` của MethodHandle. `invokeExact` yêu cầu trùng cả return type.

**Câu 5.** Protected hook có thể gọi `getTarget()` trong lúc constructor đang chạy không?

**Đáp án:** Không. Target chưa hoàn tất nên `getTarget()` ném `IllegalStateException`; `type()` thì được phép gọi.

**Câu 6.** Bootstrap được gọi thủ công trong Java code có chứng minh bytecode đang dùng `invokedynamic` không?

**Đáp án:** Không. Đó chỉ là mô phỏng quy tắc liên kết. `invokedynamic` thực là opcode trong bytecode do compiler hoặc tool tạo.

**Câu 7.** Hai ConstantCallSite khác nhau cùng chứa một MethodHandle thì có phải một site duy nhất?

**Đáp án:** Không. Chúng là hai object CallSite riêng. Chúng có thể có cùng target reference và cùng kiểu, nhưng danh tính site vẫn khác.

**Câu 8.** Khi nào `MutableCallSite` hoặc `VolatileCallSite` hợp lý hơn?

**Đáp án:** Khi yêu cầu **cập nhật target sau khi liên kết**. Chọn mutable/volatile theo mô hình publication và concurrency, không cố thay ConstantCallSite.

**Câu 9.** Cần type `(String)String` nhưng bootstrap trả target `(int)String`. ConstantCallSite có tự hợp thức hóa nó không?

**Đáp án:** Không. Target phải tương ứng type liên kết. Nếu không có conversion `asType` hợp lệ thì cần sửa bootstrap hoặc lựa chọn target.

**Câu 10.** Nếu target handle bind vào receiver có state thay đổi, tính thread-safe của receiver do ai đảm bảo?

**Đáp án:** Do thiết kế state và đồng bộ của code ứng dụng. ConstantCallSite không thay đổi Java Memory Model.

## Tóm tắt nhanh

- `ConstantCallSite` là **CallSite với target vĩnh viễn**.
- Constructor thường dùng: `new ConstantCallSite(target)` với `target != null`.
- `getTarget()` và `dynamicInvoker()` trên `ConstantCallSite` trả permanent MethodHandle; `type()` phản ánh chữ ký target.
- `setTarget(...)` **luôn thất bại** bằng `UnsupportedOperationException`.
- **Target không đổi khác với kết quả không đổi.** Cùng handle có thể tạo các giá trị khác nhau theo input và state.
- Khi liên kết `invokedynamic`, bootstrap phải trả `CallSite` phù hợp `MethodType`; chọn `ConstantCallSite` khi không cần relink.
- Protected constructor với hook hỗ trợ tạo target trong giai đoạn khởi tạo; không được dùng target khi site còn dang dở.
- Cần target có thể cập nhật? Dùng `MutableCallSite` hoặc `VolatileCallSite`, không dùng `ConstantCallSite`.

## Tài liệu tra cứu

- Java SE 17, **ConstantCallSite** (constructor, `getTarget`, `setTarget`, `dynamicInvoker`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html
- Java SE 17, **CallSite** (khái niệm, type cố định, mutable/volatile và invokedynamic): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, **MethodHandle** (`invoke`, `invokeExact`, `asType`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java Virtual Machine Specification SE 17, chương **invokedynamic** và dynamic linkage: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
