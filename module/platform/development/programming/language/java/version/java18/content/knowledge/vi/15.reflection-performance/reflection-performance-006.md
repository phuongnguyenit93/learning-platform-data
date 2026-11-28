# Member lưu trong static final và giới hạn khi suy rộng kết quả tối ưu sang mọi ứng dụng

> **Chương:** Reflection và hiệu năng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Hiểu vì sao JEP 416 khuyến nghị giữ các đối tượng `Method`, `Constructor` và `Field` ổn định trong field `static final` để hỗ trợ tối ưu của JIT; phân biệt lợi thế có thể có với bảo đảm hiệu năng; xây dựng ví dụ và đo bằng JMH; biết khi nào caching phù hợp, khi nào nên dùng cơ chế động hoặc API truy cập trực tiếp.
>
> **Phạm vi hiện đại:** Tập trung vào hợp đồng reflection công khai và hành vi tối ưu có thể đo trên JDK đang triển khai. Không sử dụng triển khai reflection cũ, option đã vô hiệu hóa hoặc API nội bộ làm khuyến nghị cho ứng dụng mới.

## 1. Bối cảnh: hiệu năng reflection thay đổi ra sao từ Java 18?

Reflection cung cấp ba kiểu đối tượng biểu diễn thành viên của class:

- `java.lang.reflect.Method`: gọi một method qua `invoke`.
- `java.lang.reflect.Constructor`: tạo đối tượng qua `newInstance`.
- `java.lang.reflect.Field`: đọc/ghi field qua `get`, `getInt`, `set` và các accessor khác.

Những API này có từ trước Java 18. **JEP 416** không bổ sung `Method.invoke()` hay một loại `Method` mới. JEP này **tái triển khai core reflection** trên nền method handles và các cơ chế liên quan, thay vì duy trì nhiều cơ chế gọi phản chiếu độc lập.

Điểm đáng chú ý trong mục hiệu năng của JEP 416: JIT có thể tối ưu mạnh hơn khi biết rõ đối tượng `Method`, `Constructor` hoặc `Field` ở call site là một giá trị ổn định. Vì vậy, JEP khuyến nghị lưu các đối tượng ấy trong các field `static final` *khi thành viên cần truy cập đã được biết trước và có thể cache ổn định*.

Điều này **không** có nghĩa:

1. Mọi lệnh `Method.invoke()` tự động nhanh ngang lời gọi Java trực tiếp.
2. Mọi đối tượng `Method` nằm trong `static final` sẽ luôn được compiler constant-fold.
3. Tất cả thư viện reflection phải chuyển sang `static final` dù thành viên chỉ được xác định lúc chạy.
4. Mọi JDK, CPU, hình dạng call site và workload cho cùng tỷ lệ tăng tốc.
5. Reflection có thể bỏ qua access control, module boundary hoặc chi phí boxing chỉ nhờ cache member.

Bài này phân biệt **khuyến nghị tạo điều kiện cho tối ưu** với **kết quả đo có điều kiện**.

## 2. static final đang giữ cái gì?

Xét:

~~~java
private static final Method UPDATE =
        Profile.class.getMethod("update", int.class);
~~~

`static final` ở đây nằm trên **biến tham chiếu có kiểu `Method`**. Nó không có nghĩa method `Profile.update` là `static` hoặc `final`.

Có ít nhất ba khái niệm dễ bị trộn lẫn:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Reflective object được giữ cố định | `private static final Method M = ...` | Tham chiếu tới metadata method được cache |
| Modifier của method đích | `public final int update(...)` | Một thuộc tính của method Java được phản chiếu |
| Modifier của field đích | `private static final int LIMIT = 10` | Field thuộc class đích; có thể là compile-time constant |

`static final Method` có thể phản chiếu một **instance method không final**. `static final Field` có thể đại diện cho một **instance field có thể thay đổi**. Hai lớp modifier không liên quan trực tiếp đến nhau.

Ví dụ:

~~~java
public class Account {
    public int balance;

    public int add(int delta) {
        balance += delta;
        return balance;
    }
}
~~~

Một class khác có thể cache:

~~~java
private static final Field BALANCE_FIELD = /* lookup Account.balance */;
private static final Method ADD_METHOD = /* lookup Account.add */;
~~~

`BALANCE_FIELD` và `ADD_METHOD` là các tham chiếu metadata được giữ cố định. Chúng **không** làm `Account.balance` thành `final` hoặc `Account.add` thành `static`.

### 2.1. Không phải constant variable theo ngôn ngữ Java

Theo JLS, *constant variable* chỉ là một field `final` kiểu primitive hoặc `String` được khởi tạo bằng constant expression đủ điều kiện. `Method`, `Field` và `Constructor` là object reference; không phải Java compile-time constant variables.

Vì vậy, nói “JIT có thể constant-fold một `static final Method`” là mô tả **khả năng tối ưu của runtime**, không phải tuyên bố rằng `javac` đã đưa một object `Method` vào constant pool dưới dạng constant expression.

Điểm khác biệt:

- `final` cấm gán lại field tham chiếu theo quy tắc Java.
- `static` gắn field với class, không với instance.
- JIT có thể nhận ra giá trị tham chiếu ổn định ở các call site thích hợp.
- Khả năng JIT nhìn xuyên qua access path và inline code vẫn phụ thuộc profile, compilation tier và implementation.

### 2.2. final không làm reflective object bất biến toàn phần

`final` bảo vệ **tham chiếu trong holder**, không đóng băng tất cả trạng thái của reflective object. Ví dụ, `AccessibleObject.trySetAccessible()` có thể cập nhật accessible flag nếu quyền module cho phép.

Do đó không dựa vào `static final` để suy ra object miễn nhiễm với thay đổi trạng thái hoặc mọi thread có thể tùy ý bật/tắt access flag mà không có vấn đề thiết kế. Cách đơn giản là cache các member public được truy cập hợp lệ và không liên tục thay đổi accessible flag.

## 3. JEP 416 đã khuyến nghị gì?

Trong phần hiệu năng, JEP 416 nhấn mạnh rằng lưu `Method`, `Constructor` và `Field` vào `static final` giúp HotSpot JIT có cơ hội **constant-fold** reference. Với reference đã được xác định, compiler có thể đi sâu hơn vào đường gọi dựa trên method handle/var handle, chuyên biệt hóa và inline các bước liên quan.

### 3.1. Đặt số liệu đúng bối cảnh lịch sử

JEP 416 trình bày một nhóm **microbenchmark** của thời điểm đề xuất:

| Trường hợp được JEP 416 so sánh | Quan sát trong microbenchmark của JEP | Không được suy diễn |
|---|---|---|
| Các reflective object giữ trong `static final` | Triển khai mới đo nhanh hơn triển khai cũ khoảng **43–57%** trong nhóm benchmark này | Mọi ứng dụng sẽ nhanh hơn 43–57% |
| `Field` object không thể constant-fold | Một số trường hợp đo **chậm hơn 51–77%** so với triển khai cũ | Trên mọi JDK mới, mọi field access đều chậm hơn 51–77% |
| Member lấy từ field không hằng hoặc mảng | Kết quả thay đổi theo dạng truy cập và độ đa hình | Mọi mảng hoặc instance field đều chắc chắn chậm |

Đây là **bằng chứng về tính nhạy với cách lưu và truy cập reflective object**, không phải bảng dự báo hiệu năng cho JDK hiện tại. Các tỷ lệ đến từ microbenchmark của JEP 416, không áp dụng như SLA hay bảo đảm API.

Từ JDK 22, triển khai core reflection cũ đã bị loại bỏ. Option từng dùng để thử nhánh cũ, `-Djdk.reflect.useDirectMethodHandle=false`, đã trở thành **no-op**. Trên JDK hiện đại, không thể dùng option này để tái lập so sánh cũ/mới như ở thời điểm Java 18.

### 3.2. “Có thể được JIT tối ưu” khác “luôn nhanh hơn”

JIT chỉ tối ưu đường gọi mà nó biên dịch và có đủ thông tin. Kết quả có thể khác nếu:

- Code chạy ít lần, chưa đủ nóng để JIT biên dịch.
- Member được thay đổi liên tục hoặc chọn động theo request.
- Call site truy cập nhiều loại member hoặc nhiều receiver khác nhau.
- Compiler không chứng minh được một đường truy cập dẫn tới một object ổn định.
- Phần lớn thời gian nằm trong code method đích, I/O hoặc lock, không nằm trong reflection dispatch.
- GC, allocation, access checks, class initialization hoặc cache miss chi phối.
- JVM flags, JDK build, CPU và workload không giống benchmark gốc.

Vì vậy, `static final` là **một lựa chọn thiết kế có cơ sở** cho những member cố định, không phải “cờ tăng tốc” bảo đảm.

## 4. JIT nhìn một member ổn định khác gì member động?

Có hai mô hình:

~~~text
A. Target member cố định

  static final Method M = lookupOnce()
            |
            v
      cùng object M
            |
       M.invoke(target, args)
            |
     JIT có thể chuyên biệt hóa call site

B. Target member thay đổi lúc chạy

  Map/array/field mutable/request metadata
            |
            v
       chọn Method M1/M2/...
            |
       M.invoke(target, args)
            |
     JIT cần xử lý đường gọi rộng hơn
~~~

Ở mô hình A, compiler có thể nhận ra target ổn định. Ở mô hình B, runtime có thể cần định tuyến giữa nhiều reflective members hoặc nhiều kiểu target.

**Nhưng:** một giá trị trong instance field, mảng hoặc map vẫn có thể được JIT tối ưu nếu profile và đường truy cập cho phép. Ngược lại, `static final` không bảo đảm chắc chắn inlining. Không dùng câu “mảng luôn chậm” hay “static final luôn nhanh nhất” làm định luật Java.

### 4.1. Khác nhau giữa cache lookup và tối ưu invoke

Hai chi phí cần đo riêng:

1. **Tìm member:** gọi `Class.getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredConstructor`.
2. **Dùng member:** gọi `Method.invoke`, `Field.getInt`, `Constructor.newInstance`.

Cache metadata tránh lặp lại bước tìm member. `static final` còn có thể tạo điều kiện cho JIT chuyên biệt hóa **bước sử dụng** member.

Một benchmark lặp `getDeclaredMethod(...)` ở mỗi invocation đang đo cả lookup lẫn invoke; không thể dùng kết quả đó để kết luận riêng tác dụng constant-fold của `static final Method`.

## 5. Ví dụ Java đầy đủ: cache Constructor, Method và Field

Tạo file `MemberCacheDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class MemberCacheDemo {
    public static final class Profile {
        public int points;

        public Profile(int initialPoints) {
            this.points = initialPoints;
        }

        public int add(int delta) {
            points += delta;
            return points;
        }
    }

    // Các reflective object được tra cứu một lần khi class khởi tạo.
    private static final Constructor<Profile> CTOR;
    private static final Method ADD;
    private static final Field POINTS;

    static {
        try {
            CTOR = Profile.class.getConstructor(int.class);
            ADD = Profile.class.getMethod("add", int.class);
            POINTS = Profile.class.getField("points");
        } catch (ReflectiveOperationException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    // Hai cách giữ member khác để minh họa, không phải thước đo tốc độ.
    private final Method instanceFinalMethod = ADD;
    private Method mutableMethod = ADD;

    public int viaInstanceField(Profile target, int delta)
            throws ReflectiveOperationException {
        return (Integer) instanceFinalMethod.invoke(target, delta);
    }

    public int viaMutableField(Profile target, int delta)
            throws ReflectiveOperationException {
        return (Integer) mutableMethod.invoke(target, delta);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Profile profile = CTOR.newInstance(10);
        System.out.println("before=" + POINTS.getInt(profile));

        int after = (Integer) ADD.invoke(profile, 5);
        System.out.println("afterInvoke=" + after);
        System.out.println("afterField=" + POINTS.getInt(profile));

        MemberCacheDemo demo = new MemberCacheDemo();
        System.out.println("instanceFinal="
                + demo.viaInstanceField(profile, 1));
        System.out.println("mutable="
                + demo.viaMutableField(profile, 1));
    }
}
~~~

Biên dịch trên JDK hiện đại có hỗ trợ `--release 18`:

~~~shell
javac -encoding UTF-8 --release 18 -d out MemberCacheDemo.java
java -cp out MemberCacheDemo
~~~

Kết quả:

~~~text
before=10
afterInvoke=15
afterField=15
instanceFinal=16
mutable=17
~~~

Ví dụ cho thấy ba loại reflective object cùng có thể lưu ở `static final`. `ADD` là object `Method` mô tả **instance method**; khi gọi `ADD.invoke(profile, 5)` vẫn phải truyền receiver `profile`.

**Không được suy ra benchmark:** Kết quả ở trên chỉ xác minh hành vi chức năng. Không thể nhìn output hay dùng vài lần gọi `nanoTime` để tuyên bố cách cache nào nhanh hơn.

### 5.1. Vì sao dùng public member trong ví dụ?

`Profile` là public nested class; constructor, method và field đều public. Vì vậy demo không cần `setAccessible(true)`, `--add-opens` hoặc quyền deep reflection.

Khi đối tượng thuộc named module khác, vẫn cần xét `exports` và `opens` theo hợp đồng reflection. Caching không làm thay đổi quyền truy cập.

### 5.2. Lỗi tra cứu xảy ra lúc class initialization

Trong code trên, nếu đổi `"add"` thành tên method không tồn tại, phần static initializer sẽ ném `ExceptionInInitializerError` ngay khi class holder được khởi tạo.

Đây là một trade-off:

- **Ưu điểm:** phát hiện metadata cố định không đúng từ sớm, không tra cứu đi tra cứu lại.
- **Nhược điểm:** đường khởi tạo class có thể thất bại, ảnh hưởng startup hoặc lần sử dụng đầu tiên; cần biết cách ghi log nguyên nhân.

Không bắt `ReflectiveOperationException` rồi tiếp tục với `ADD = null` chỉ để class load thành công. Điều đó chuyển lỗi cấu hình rõ ràng thành `NullPointerException` muộn và khó chẩn đoán.

## 6. Mẫu static final cho method cố định

Với một method được biết ngay khi viết code, có thể tách phần lookup:

~~~java
private static final Method HANDLER = findHandler();

private static Method findHandler() {
    try {
        return Handler.class.getMethod("handle", String.class);
    } catch (NoSuchMethodException failure) {
        throw new ExceptionInInitializerError(failure);
    }
}
~~~

Ưu tiên `getMethod` cho public method được phép truy cập. Nếu thật sự cần member không public, đọc hợp đồng `getDeclaredMethod` và JPMS trước; không tự động bật accessibility như một thủ thuật hiệu năng.

Một điểm cần cân nhắc: nếu mã nguồn đã biết chính xác class và method, lời gọi trực tiếp:

~~~java
handler.handle(payload);
~~~

thường dễ hiểu, type-safe và có nhiều cơ hội tối ưu hơn reflection. Giữ reflection khi thực sự cần dynamic dispatch, adapter, annotation-driven framework hoặc metadata runtime.

### 6.1. Holder lazy initialization

Nếu member chỉ cần khi sử dụng một nhánh tính năng, có thể dùng holder class được khởi tạo khi truy cập lần đầu:

~~~java
public final class LazyHandler {
    private static final class Holder {
        static final Method HANDLE = findMethod();

        private static Method findMethod() {
            try {
                return Handler.class.getMethod("handle", String.class);
            } catch (NoSuchMethodException failure) {
                throw new ExceptionInInitializerError(failure);
            }
        }
    }

    public static Object invoke(Handler handler, String text)
            throws ReflectiveOperationException {
        return Holder.HANDLE.invoke(handler, text);
    }
}
~~~

Class `Handler` ở ví dụ là class của dự án có public method `handle(String)`. Đoạn code minh họa mô hình khởi tạo, không tự chứa định nghĩa `Handler`.

Holder giúp trì hoãn lookup đến lần dùng đầu tiên, nhưng không biến reflective invoke thành lời gọi không có chi phí. Cần cân nhắc cold-start latency ở yêu cầu đầu.

## 7. Lưu trong instance final, field mutable, mảng hoặc map

Các cấu trúc khác có đặc điểm riêng:

~~~java
private static final Method FIXED = findMethod();

private final Method perInstance = FIXED;
private Method mutable = FIXED;
private final Method[] methods = { FIXED };
private static final Map<String, Method> REGISTRY = createRegistry();
~~~

| Hình dạng lưu trữ | Điều Java bảo đảm | Điều cần đo |
|---|---|---|
| `static final Method` | Một biến tham chiếu gắn class, chỉ gán khi khởi tạo | JIT có specialization/inlining không |
| `final Method` instance | Không gán lại tham chiếu trên instance sau khởi tạo hợp lệ | Mức ổn định của call site khi có nhiều instance |
| `Method` mutable | Có thể đổi reference | Chi phí khi target thay đổi hoặc không |
| `Method[]` | Phần tử có thể được thay đổi dù array reference là final | Chi phí array access, profile của phần tử |
| `static final Map<String, Method>` | **Tham chiếu tới map** không được gán lại | `map.get`, lookup key, số target, mutation và cache behavior |

Đặc biệt, `static final Map` **không** làm mọi giá trị trong map trở thành compile-time constant hoặc JIT constant. Tương tự, `final Method[]` chỉ cố định tham chiếu array, không cố định từng slot.

Nếu framework thực sự phải chọn member theo schema/plugin/user input, registry có thể là mô hình đúng. Không làm hỏng cấu trúc API chỉ để nhồi mọi member vào `static final`.

### 7.1. Caching theo class hoặc theo schema

Một framework serializer/mapper thường nhận nhiều class bất kỳ. Không thể khai báo một field `static final` cho mọi class xuất hiện tại runtime.

Có thể thiết kế cache theo class:

~~~java
private static final ClassValue<Method> ACCESSORS =
        new ClassValue<>() {
            @Override
            protected Method computeValue(Class<?> type) {
                try {
                    return type.getMethod("value");
                } catch (NoSuchMethodException failure) {
                    throw new IllegalArgumentException(
                            "Missing public value() on " + type, failure);
                }
            }
        };
~~~

`ClassValue` hỗ trợ dữ liệu gắn với `Class` và có thể phù hợp trong một số hệ thống dùng nhiều classloader. Đây là cách **cache lookup động**, không phải bằng chứng JIT chắc chắn coi `ACCESSORS.get(type)` là một `Method` hằng.

Đọc `ClassValue` và yêu cầu thực tế trước khi dùng: ví dụ này chỉ hỗ trợ những type có public no-arg method `value()`. Trong một số framework, cache cần chứa nhiều property hoặc nhiều operation thay vì một method.

## 8. Đừng lẫn bộ nhớ cache với vòng đời classloader

Static field tồn tại theo vòng đời class đã được load. Một static cache trong framework có vòng đời dài có thể giữ reference tới reflective object của class được load bằng classloader ngắn hạn.

Đường tham chiếu thường gặp:

~~~text
Framework class (loader sống lâu)
     |
     v
static cache / registry
     |
     v
Method / Field / Constructor
     |
     v
Declaring Class
     |
     v
Plugin ClassLoader
~~~

Nếu cache giữ mạnh reference và không bao giờ loại bỏ entries, classloader của plugin có thể không được thu gom như mong đợi.

Điều này không chứng minh mọi `static final Method` gây leak. Một holder và declaring class được load/unload cùng nhau có vòng đời khác với global registry của framework chứa class thuộc child loader.

Hãy cân nhắc `ClassValue`, cache theo vòng đời plugin/schema, weak reference hoặc cơ chế eviction phù hợp. **Hiệu năng hot path** không nên đánh đổi bằng leak không giới hạn trong ứng dụng chạy dài.

## 9. Reflection invoke vẫn có những chi phí nào?

Ngay cả khi `Method` nằm trong `static final`, đường phản chiếu còn có thể bao gồm:

- Kiểm tra receiver và kiểu đối số tại runtime.
- Boxing/unboxing cho primitive khi gọi `Method.invoke`.
- Tạo hoặc xử lý mảng varargs `Object...`.
- Kiểm tra access control nếu accessible flag không suppress checks.
- Chuyển exception từ method đích sang `InvocationTargetException`.
- Dispatch qua hệ thống method handle/reflection ở một số call site.
- Khởi tạo class lần đầu, cache miss hoặc JIT warmup.

Không phải chi phí nào cũng xuất hiện giống nhau sau tối ưu, và không nên khẳng định JVM luôn allocation cho từng `invoke`. Escape analysis có thể loại bỏ một số allocation ở tình huống phù hợp.

### 9.1. Field.getInt và Field.get khác nhau

Với một field `int`:

~~~java
int a = field.getInt(target);
Object b = field.get(target);
~~~

`getInt` trả primitive `int`, trong khi `get` trả `Object` và có thể đòi boxing giá trị primitive. Dù reflective object được cache giống nhau, benchmark hai API có shape và allocation profile khác.

`Field.setInt`/`Field.getInt` hoặc `VarHandle` có thể phù hợp trong trường hợp cần truy cập primitive nhiều lần, nhưng quyền truy cập, semantics và nhu cầu atomic operation vẫn phải được cân nhắc theo API contract.

### 9.2. MethodHandle không tự động thắng reflection

`MethodHandle` có từ Java 7; `VarHandle` có từ Java 9. JEP 416 dùng những cơ chế này trong implementation core reflection, không có nghĩa code ứng dụng phải thay mọi reflection call bằng MethodHandle.

Với `MethodHandle.invokeExact`, call site có kiểu tĩnh chặt chẽ. Nếu handle ổn định và chữ ký phù hợp, JIT có cơ hội tối ưu tốt. Nhưng chuẩn bị handle, xử lý `MethodType`, quyền lookup và error behavior là những trade-off riêng.

Chọn API theo tính năng; đo hiệu năng của hot path thực tế trước khi chuyển đổi quy mô lớn.

## 10. Một so sánh chức năng với MethodHandle

Ví dụ gọi cùng instance method bằng reflection và method handle:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class HandleComparison {
    public static final class Counter {
        private int value;

        public int add(int delta) {
            return value += delta;
        }
    }

    private static final Method REFLECTED;
    private static final MethodHandle HANDLE;

    static {
        try {
            REFLECTED = Counter.class.getMethod("add", int.class);
            HANDLE = MethodHandles.publicLookup().findVirtual(
                    Counter.class,
                    "add",
                    MethodType.methodType(int.class, int.class));
        } catch (ReflectiveOperationException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter first = new Counter();
        Counter second = new Counter();

        int viaReflection = (Integer) REFLECTED.invoke(first, 2);
        int viaHandle = (int) HANDLE.invokeExact(second, 2);

        System.out.println(viaReflection);
        System.out.println(viaHandle);
    }
}
~~~

Kết quả:

~~~text
2
2
~~~

Trong `HANDLE.invokeExact(second, 2)`, kiểu của receiver và giá trị trả về phải khớp method type dự kiến. `Method.invoke` nhận `Object...` và áp dụng các quy tắc conversion khác. Hai lời gọi ở trên cùng làm tăng counter nhưng **không chứng minh tốc độ tương đương**.

Khi benchmark, cần đo cả lần lookup/khởi tạo handle nếu đó là phần thực của use case, hoặc bỏ phần lookup khỏi timed region cho cả hai nếu ứng dụng cache trước khi xử lý request.

## 11. Vì sao microbenchmark không phải số liệu end-to-end?

Giả sử một serializer xử lý một triệu property read nhưng chỉ chiếm 5% thời gian tổng của request. Ngay cả khi một kỹ thuật làm thao tác reflection nhanh hơn 2 lần, phần lớn request vẫn còn các bước parse, validation, compression, I/O và ghi network.

Ví dụ định lượng:

| Thành phần trong một request | Trước tối ưu |
|---|---:|
| Reflection/property access | 5 ms |
| Parse/validate/business logic | 45 ms |
| I/O và serialization khác | 50 ms |
| **Tổng** | **100 ms** |

Nếu reflection giảm từ 5 ms xuống 2,5 ms, tổng giả định mới là 97,5 ms, tương ứng cải thiện **2,5%** trên request này, không phải 50%.

Đây là **ví dụ giả định minh họa hiệu ứng Amdahl**, không phải kết quả benchmark thực tế. Điều kiện phản xạ có thể chiếm phần lớn hơn hoặc nhỏ hơn tùy workload.

Với hệ thống khác, những chi phí như cold-start, memory footprint, cache contention, JIT code cache, GC pressure hoặc classloader retention có thể quan trọng hơn throughput của một lần `Method.invoke`.

## 12. Thiết kế benchmark đúng để so sánh cách giữ Member

Để phân biệt hiệu năng giữa các cách cache, cần giữ những yếu tố khác gần nhau nhất:

1. Dùng cùng một target method/field và cùng công việc bên trong.
2. Tách thời gian lookup metadata khỏi invocation.
3. Tránh tạo dữ liệu test lớn hoặc log trong timed region.
4. Giữ target/object lifetime tương đương.
5. Dùng warmup cho JIT, chạy fork mới để tránh state của JVM.
6. Dùng đủ iteration và xem confidence/error chứ không chỉ score.
7. Tránh constant folding của **kết quả nghiệp vụ** làm benchmark không đo công việc thật.
8. Đo allocation rate và GC khi boxing/Object[] có thể ảnh hưởng.
9. Đo thêm cold-start, tail latency, throughput khi chúng quan trọng.
10. Ghi JDK vendor/version, VM flags, CPU, OS, container limits và phiên bản JMH.

Một vòng lặp thủ công:

~~~java
long begin = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    method.invoke(target, 1);
}
System.out.println(System.nanoTime() - begin);
~~~

**không phải** thước đo đáng tin để kết luận JEP 416 tối ưu bao nhiêu phần trăm. Kết quả bị ảnh hưởng bởi JIT warmup, compiler optimizations, allocation, exception, GC, loại method và cách dùng giá trị trả về. `System.nanoTime()` có thể đo thời gian, nhưng **không thay** một framework microbenchmark.

## 13. Ví dụ JMH: giữ cùng method, đổi vị trí lưu trữ

Ví dụ sau dùng JMH để tạo khung đo ba đường reflection và lời gọi trực tiếp. JMH là thư viện benchmarking riêng; phải thêm `jmh-core` và annotation processor `jmh-generator-annprocess` theo tài liệu JMH trước khi biên dịch. Không thể chỉ dùng một lệnh `javac` chuẩn mà chạy được annotation này nếu chưa cấu hình dependency.

File `MemberPlacementBenchmark.java`:

~~~java
import java.lang.reflect.Method;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class MemberPlacementBenchmark {
    public static final class Counter {
        private int value;

        public int add(int delta) {
            value += delta;
            return value;
        }
    }

    private static final Method CONSTANT = findAdd();

    private Method ordinary;
    private Method[] methods;
    private Counter target;

    private static Method findAdd() {
        try {
            return Counter.class.getMethod("add", int.class);
        } catch (NoSuchMethodException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    @Setup(Level.Trial)
    public void setup() {
        ordinary = findAdd();
        methods = new Method[] { findAdd() };
        target = new Counter();
    }

    @Benchmark
    public int direct() {
        return target.add(1);
    }

    @Benchmark
    public int reflectedStaticFinal() throws ReflectiveOperationException {
        return (Integer) CONSTANT.invoke(target, 1);
    }

    @Benchmark
    public int reflectedMutableField() throws ReflectiveOperationException {
        return (Integer) ordinary.invoke(target, 1);
    }

    @Benchmark
    public int reflectedArrayElement() throws ReflectiveOperationException {
        return (Integer) methods[0].invoke(target, 1);
    }
}
~~~

Trong bài, `Counter.add` cập nhật trạng thái để benchmark không chỉ cộng các constant độc lập. `@State(Scope.Thread)` tránh để các benchmark threads cùng tranh chấp một counter chung. Các annotation cho warmup/fork/measurement giúp thiết lập phép đo có tổ chức.

### 13.1. Đọc kết quả đúng cách

Không có con số “đúng” cố định cho bốn phương thức. Có thể:

- `reflectedStaticFinal` nhanh hơn trong một số JVM/cấu hình.
- `reflectedMutableField` hoặc `reflectedArrayElement` tiệm cận khi JIT profile thấy cùng target ổn định.
- `direct` có lợi thế từ lời gọi tĩnh rõ ràng và không phải đi qua reflection.
- Khác biệt thu nhỏ hoặc biến mất nếu target method làm nhiều công việc thật.

`@Fork(2)` không có nghĩa sai số bằng 0; hãy xem error bars, variation giữa forks và stability. Nếu kết quả bất thường, không đưa ra kết luận trước khi kiểm tra output, generated benchmark code và profiler.

### 13.2. Hạn chế của chính fixture JMH

Ví dụ `ordinary` và `methods[0]` cũng giữ cùng target method trong suốt từng trial. JIT có thể nhận diện profile ổn định cho cả hai. Đây là ưu điểm về sự công bằng khi so cùng thao tác, nhưng **không đại diện cho registry chọn member khác nhau ở mỗi request**.

Nếu hệ thống thật là đa hình, cần thêm benchmark có nhiều target method/type và cùng distribution như production. Khi so với `static final`, phải diễn giải rằng việc lựa chọn target động là một yêu cầu chức năng, không chỉ một thay đổi modifier.

Không dùng vòng đo này để kết luận logic bên trong JIT của mọi bản JDK; muốn hiểu inlining, cần profiler và số liệu của VM đang chạy.

## 14. Những biến làm kết quả đổi chiều

| Biến | Ảnh hưởng khả dĩ |
|---|---|
| Cold start / chưa đủ warmup | Không kịp chuyên biệt hóa đường gọi |
| Receiver có một runtime type | Dễ profile ổn định hơn trường hợp nhiều type |
| Nhiều method target ở cùng call site | Có thể làm khó inlining/chuyên biệt hóa |
| Field primitive so với object | Khác boxing, accessor và memory profile |
| Static so với instance target method | Khác receiver handling |
| Public member so với deep reflection | Khác access setup và JPMS constraints |
| Reflection lookup trong timed region | Đo thêm metadata discovery, làm sai mục tiêu |
| Target làm I/O hoặc computation nặng | Reflection dispatch chiếm tỷ trọng nhỏ |
| Caching theo classloader/plugin | Memory retention có thể quan trọng hơn throughput |
| JDK build/VM flags/hardware | Compiler heuristics và runtime behavior có thể khác |

Không đồng nhất correlation trong microbenchmark với lời giải thích cơ chế chính xác. Khi cần chứng minh lý do nhanh/chậm, dùng JFR, profiler, assembly/inlining diagnostics có kiểm soát thay vì suy luận chỉ từ `ns/op`.

## 15. Khi nào static final là lựa chọn hợp lý?

`static final Method`/`Field`/`Constructor` phù hợp nếu:

- Member được biết từ lúc viết code và hiếm khi thay đổi.
- Holder được dùng thường xuyên trong hot path.
- Không cần phân giải member khác nhau theo request.
- Classloader/module lifecycle tương thích với vòng đời holder.
- Bật quyền truy cập không phải thao tác ngẫu nhiên hoặc không cần thiết.
- Đã đo được rằng lookup/dispatch thực sự đáng tối ưu.

Ví dụ: adapter cho một API cố định, một bridge tới public method của dependency cụ thể, hoặc internal component luôn gọi cùng constructor.

**Ưu tiên:** giữ source code đơn giản, type-safe, không tạo abstraction reflection chỉ vì mong tăng tốc. Nếu có thể gọi trực tiếp thì không cần cache `Method`.

## 16. Khi nào không nên cưỡng ép static final?

Tránh thiết kế này khi:

- Thành viên được chọn từ cấu hình, schema hoặc plugin runtime.
- Class được load/unload độc lập theo plugin/tenant.
- Nhiều target có signature khác nhau và cần registry động.
- Lookup còn tùy permission/module boundary tại từng context.
- Ứng dụng chỉ gọi method vài lần, không có bottleneck.
- Cache static dài hạn có nguy cơ giữ classloader hoặc metadata không còn cần.
- Mã nguồn phải dùng reflection do generic framework: việc tách hàng nghìn field `static final` làm code kém bảo trì.

Trong các trường hợp này, cache thích hợp có thể là `ClassValue`, per-schema metadata, một registry có eviction hoặc cache theo thời hạn plugin. Cách lưu member đúng với domain còn quan trọng hơn lợi thế microbenchmark.

## 17. JEP 416 và giới hạn của so sánh trên JDK hiện đại

JEP 416 được triển khai từ Java 18. Một số chi tiết trình bày trong JEP là bối cảnh lịch sử của quá trình chuyển đổi implementation.

**Điểm vẫn áp dụng:**

- `Method`, `Constructor`, `Field` giữ hợp đồng reflection.
- Phương thức core reflection sử dụng nền tảng method handles/var handles ở JDK hiện đại.
- JIT có thể tối ưu tốt hơn khi target object ổn định.
- Benchmark thực tế là nguồn quyết định hiệu năng.
- Truy cập reflection vẫn phải tuân thủ language/module access rules.

**Không nên lấy làm khuyến nghị hiện nay:**

- Chạy nhánh reflection cũ bằng `-Djdk.reflect.useDirectMethodHandle=false`; option đã no-op từ JDK 22.
- Cố so sánh JDK hiện đại với implementation cũ như thể cả hai cùng có mặt trên JDK hiện tại.
- Dựa vào hook `sun.reflect`, `jdk.internal.reflect` hoặc bytecode hack để điều khiển đường gọi.
- Diễn giải một bảng JEP 416 thành kết luận hiệu năng cho mọi phiên bản JDK tương lai.

Khi viết báo cáo benchmark, ghi rõ **“số liệu lịch sử từ microbenchmark JEP 416”** nếu trích những tỷ lệ đó, thay vì gọi chúng là benchmark Java 27.

## 18. Checklist trước khi tối ưu reflection

- [ ] Biết rõ member được xác định cố định hay động.
- [ ] Phân biệt `static final` holder với modifier của member đích.
- [ ] Đã loại metadata lookup lặp lại không cần thiết.
- [ ] Không xem `static final Method` là compile-time constant theo JLS.
- [ ] Hiểu JIT có thể specialization/inlining nhưng không bảo đảm.
- [ ] Dùng lời gọi trực tiếp nếu không cần reflection.
- [ ] Không tự động dùng `setAccessible(true)` như mẹo tăng tốc.
- [ ] Kiểm tra `exports`/`opens` và access checks.
- [ ] Không sửa final field đích bằng reflection để “tối ưu”.
- [ ] Không dùng tùy chọn reflection legacy đã no-op trên JDK mới.
- [ ] Dùng JMH với warmup/forks/iterations và workload đại diện.
- [ ] Tách lookup cost, invocation cost và công việc của target.
- [ ] Có so sánh direct call khi cần baseline.
- [ ] Đo allocation/GC/throughput/tail latency nếu có ý nghĩa.
- [ ] Ghi JDK build, VM flags, CPU, OS, các dependency benchmark.
- [ ] Kiểm tra classloader lifetime và nguy cơ cache giữ object quá lâu.
- [ ] Không suy từ một điểm ns/op ra % tăng tốc toàn ứng dụng.
- [ ] Đã đo trên bản JDK và workload mà hệ thống thật chạy.

## 19. Bài tập thực hành

### Bài 1 — Phân biệt “static final Method” với “static method”

Dùng `MemberCacheDemo`, giải thích vì sao `ADD` nằm trong field `static final` nhưng `Profile.add` vẫn cần receiver instance.

**Tiêu chí đạt:** Chỉ ra chính xác modifier thuộc holder hay target.

### Bài 2 — Cache metadata một lần

Viết hai phiên bản: một phiên bản gọi `getMethod` mỗi lần xử lý, phiên bản còn lại cache `Method` ở field phù hợp.

**Tiêu chí đạt:** Nhận ra bạn đang tối ưu lookup cost; chưa được khẳng định % nhanh hơn nếu chưa benchmark.

### Bài 3 — Phân biệt static final, instance field và array

Dùng JMH sample, đo bốn case trên JDK được dự án hỗ trợ. Ghi fork variation/error bars.

**Tiêu chí đạt:** Báo cáo kết quả đo của môi trường thật, không sao chép tỷ lệ từ JEP 416 làm kết quả của bạn.

### Bài 4 — Tạo đa hình có kiểm soát

Mở rộng fixture thành hai hoặc ba target method cùng signature, chọn theo phân bố request được xác định. Đo khả năng chuyên biệt hóa khi call site có nhiều target.

**Tiêu chí đạt:** Kết luận có điều kiện và nêu rõ việc chọn target động tăng thêm chi phí thực.

### Bài 5 — Đánh giá tác động end-to-end

Giả sử reflection chiếm 5% request latency và riêng reflection nhanh hơn 2 lần. Ước lượng tổng latency mới.

**Gợi ý:** Theo ví dụ trước, 100 ms giảm xuống 97,5 ms.

**Tiêu chí đạt:** Không báo cáo tăng tốc 50% cho toàn request.

### Bài 6 — Classloader retention

Thiết kế một registry cho plugin classes có thể unload. So sánh một cache strong-reference toàn hệ thống với cache theo vòng đời plugin hoặc `ClassValue`.

**Tiêu chí đạt:** Có chính sách loại bỏ metadata và không chỉ tối ưu dispatch throughput.

## 20. Tài liệu chính thức

1. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): lý do tái triển khai, khuyến nghị `static final` và microbenchmark lịch sử.
2. [Oracle JDK 22 Release Notes — Old Core Reflection Implementation Removed](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html): xác nhận nhánh cũ đã bị loại bỏ, option `jdk.reflect.useDirectMethodHandle=false` không còn tác dụng.
3. [Method — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và quy tắc tham số/exception.
4. [Field — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html): accessor primitive/object, access controls và final fields.
5. [Constructor — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance` và constructor reflection.
6. [AccessibleObject — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): accessible flag, `canAccess`, `trySetAccessible` và module boundaries.
7. [MethodHandle — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): Method Handle invocation, `invokeExact` và call-site typing.
8. [ClassValue — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassValue.html): cache giá trị gắn với class.
9. [JLS `4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.12.4): định nghĩa constant variable, khác với `static final Method`.
10. [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): framework benchmark có warmup, forks và thống kê phép đo.

**Kết quả cần đạt:** Bạn có thể giải thích vì sao `Method`, `Field` và `Constructor` được cache trong `static final` có thể tạo điều kiện cho JIT tối ưu sau JEP 416, nhưng không khẳng định kết quả đó đúng cho mọi code path hoặc ứng dụng. Hãy chọn mô hình cache theo tính chất động/tĩnh của metadata, giữ đúng access/module semantics và dựa vào JMH cùng profiling workload thật khi đưa ra quyết định hiệu năng.
