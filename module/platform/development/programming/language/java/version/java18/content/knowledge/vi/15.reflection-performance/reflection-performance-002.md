# Phân biệt thay đổi triển khai reflection với hợp đồng API công khai được duy trì

> **Chương:** Reflection và hiệu năng  
> **Bối cảnh:** Java 18 giới thiệu JEP 416, tái triển khai core reflection dựa trên method handles. Các khái niệm và hợp đồng công khai trong bài vẫn cần được đối chiếu với Javadoc của phiên bản JDK thực tế khi nâng cấp.

## 1. Hai lớp cần phân biệt khi đọc tin về reflection

Reflection là công cụ cho phép chương trình Java tìm và thao tác với lớp, phương thức, constructor, field tại runtime. Từ Java 18, **JEP 416 — Reimplement Core Reflection with Method Handles** thay đổi cách JVM *triển khai bên trong* các thao tác phản chiếu cốt lõi. Điều này hữu ích cho bảo trì JDK và có thể thay đổi đặc điểm tối ưu hóa của JIT.

Thay đổi này **không bắt buộc ứng dụng đổi từ `Method.invoke(...)` sang `MethodHandle`**, cũng không tự tạo ra một bộ hợp đồng API hoàn toàn mới. Lớp `java.lang.reflect.Method`, `Constructor`, `Field` và các phương thức công khai tiếp tục là điểm vào mà framework và chương trình sử dụng.

Hãy tách hai câu hỏi:

1. **Hợp đồng công khai (what):** tra cứu thành viên theo tên và chữ ký ra sao; ai được truy cập; gọi với receiver/đối số nào hợp lệ; kết quả và ngoại lệ được quy định thế nào?
2. **Cách triển khai và hiệu năng (how):** JDK dùng cơ chế nội bộ nào để phục vụ lời gọi; JIT tối ưu hóa trường hợp nào; chi phí phụ thuộc vào tính ổn định của metadata và đặc điểm workload thế nào?

Ứng dụng có thể dựa vào **hợp đồng được tài liệu API bảo đảm**. Ứng dụng không nên dựa vào tên lớp nội bộ trong stack trace, hình dạng bytecode do runtime sinh ra, số nanosecond cố định hoặc giả định về chiến lược tối ưu hóa của một bản JDK.

## 2. Điều gì thực sự thay đổi trong Java 18?

JEP 416 tái cấu trúc việc triển khai các thành viên reflection thuộc `java.lang.reflect` để, sau giai đoạn khởi tạo JVM, các thao tác chủ yếu được thực hiện trên nền **method handles**. Trước thay đổi này, JDK từng có nhiều con đường triển khai nội bộ. Những chi tiết lịch sử đó chỉ giúp hiểu động cơ đơn giản hóa JDK; không nên tái sử dụng các cơ chế nội bộ cũ trong ứng dụng hiện đại.

```text
Mã ứng dụng / thư viện
        |
        v
Class.getMethod / getConstructor / getField
        |
        v
Method.invoke / Constructor.newInstance / Field.get, set
        |
        v
   Triển khai core reflection trong JDK
   (được tái cấu trúc bởi JEP 416)
        |
        v
    Cơ chế runtime / method handles / JIT
```

Sơ đồ biểu diễn **ranh giới trách nhiệm**, không phải cam kết rằng mọi lời gọi reflection đều có chính xác một đường đi nội bộ. JVM có thể có logic đặc biệt lúc khởi động và thay đổi cách tối ưu theo phiên bản.

| Cấp độ | Ví dụ | Mức độ nên phụ thuộc |
| --- | --- | --- |
| API công khai | `Method.invoke`, `Constructor.newInstance`, `Field.getInt`, `Class.getDeclaredMethod` | Có, theo Javadoc và đặc tả của JDK đang dùng |
| Quy tắc ngôn ngữ/module | Kiểu tham số, kiểm tra quyền, `exports`/`opens`, ngoại lệ phản chiếu | Có, khi đã xác định rõ môi trường và điều kiện |
| Chi tiết triển khai | Lớp accessor bên trong JDK, chuỗi stack trace nội bộ, việc sinh mã hoặc đường dẫn tối ưu | Không; có thể đổi mà không đổi hợp đồng công khai |
| Kết quả hiệu năng | `ns/op`, mức tăng giảm theo JDK, cấu hình và workload | Chỉ là số liệu đo trên môi trường xác định; không phải bảo đảm API |

**Điểm mấu chốt:** "reflection được triển khai trên method handles" là thông tin về kiến trúc JDK. "Ứng dụng gọi `Method.invoke` theo quy tắc nào" mới là nội dung hợp đồng dùng để viết kiểm thử tương thích.

## 3. Các hợp đồng công khai vẫn cần kiểm chứng

### 3.1. Tìm thành viên là bước riêng với gọi thành viên

| API | Điều cần kiểm chứng | Ca biên có ý nghĩa |
| --- | --- | --- |
| `Class.getMethod(name, types...)` | Tìm method public theo chữ ký, có xét thành viên kế thừa khi phù hợp | Sai tên/kiểu tham số dẫn đến `NoSuchMethodException` |
| `Class.getDeclaredMethod(name, types...)` | Tìm method do lớp khai báo, gồm cả non-public | Tìm được private method **không có nghĩa** được phép gọi |
| `Class.getConstructor(types...)` | Tìm public constructor theo kiểu tham số | Constructor không được kế thừa; sai chữ ký dẫn đến `NoSuchMethodException` |
| `Class.getDeclaredConstructor(types...)` | Tìm constructor khai báo trực tiếp với mọi mức truy cập | Constructor private vẫn chịu kiểm tra quyền khi gọi |
| `Class.getField(name)` / `getDeclaredField(name)` | Phân biệt public field có thể kế thừa và field do lớp khai báo | `NoSuchFieldException`, quyền truy cập và field ẩn (field hiding) |

Đối với method và constructor, kiểu tham số khi **tìm kiếm** phải đúng theo chữ ký: tìm `int.class` không giống tìm `Integer.class`. Việc boxing, unboxing hoặc mở rộng kiểu nguyên thủy có thể hợp lệ khi **gọi** nhưng không làm thay đổi quy tắc tra cứu.

### 3.2. `Method.invoke(...)`

- Method instance cần receiver thuộc kiểu phù hợp; method static không dùng receiver và có thể truyền `null`.
- Runtime kiểm tra số lượng, kiểu đối số và quyền truy cập. Đối số nguyên thủy có thể được unbox và mở rộng kiểu nguyên thủy theo quy tắc của API.
- Giá trị trả về kiểu nguyên thủy được đóng gói thành wrapper tương ứng; method trả `void` cho kết quả reflection là `null`.
- Nếu *mã method đích* ném ngoại lệ, `Method.invoke` bọc ngoại lệ đó trong `InvocationTargetException`; lấy `getCause()` để kiểm tra lỗi thật.
- Sai đối số thường gây `IllegalArgumentException` ở lớp reflection; thiếu quyền gây `IllegalAccessException`. Hai nhóm lỗi này khác nguyên nhân, không nên gom thành một.

### 3.3. `Constructor.newInstance(...)`

`Constructor.newInstance` tạo đối tượng bằng constructor được chọn theo chữ ký. Nó có thể ném `InstantiationException` với lớp không thể khởi tạo như abstract class, `IllegalAccessException` khi thiếu quyền, `IllegalArgumentException` khi đối số không phù hợp và `InvocationTargetException` khi constructor đã chạy nhưng tự ném lỗi.

Đối với mã mới, sử dụng `getDeclaredConstructor(...).newInstance(...)` hoặc factory/constructor bình thường phù hợp với quyền truy cập; không dùng `Class.newInstance()` đã được đánh dấu deprecated vì cách lan truyền ngoại lệ không phù hợp với mô hình reflection hiện đại.

### 3.4. `Field.get(...)` và `Field.set(...)`

Field instance yêu cầu receiver phù hợp, trong khi field static có thể dùng receiver `null`. Các biến thể như `getInt`, `setInt` giúp nêu rõ kiểu nguyên thủy, còn `get`/`set` làm việc với giá trị đối tượng và quy tắc chuyển đổi tương ứng. Ghi sai kiểu hoặc dùng receiver không phù hợp gây lỗi theo hợp đồng API; quyền đọc và ghi vẫn được kiểm tra.

Đừng xây dựng tối ưu hóa trên việc sửa `final` field bằng reflection. Với dữ liệu bất biến, dùng constructor, factory hoặc API công khai để thiết lập giá trị. JEP 416 không biến các field private/final của JDK thành nơi có thể tùy ý truy cập hoặc ghi.

### 3.5. Quy tắc truy cập, module và tính đóng gói

`getDeclared*` cho phép **khám phá** thành viên trong lớp, nhưng việc gọi hoặc sửa thông qua reflection cần quyền hợp lệ. `AccessibleObject.canAccess(receiver)` quan sát khả năng truy cập hiện tại; `trySetAccessible()` có thể trả `false` nếu không được phép mở quyền.

Với Java Platform Module System (JPMS), public API trong package được `exports` có thể được dùng theo các quy tắc truy cập phù hợp; truy cập sâu vào member non-public qua reflection thường cần package được `opens` cho module gọi. Khả năng truy cập phụ thuộc cả mức truy cập Java và quan hệ module.

Ví dụ minh họa ý nghĩa của `opens` trong module do chính bạn quản lý:

```java
module example.model {
    exports example.model.api;
    opens example.model.internal to example.framework;
}
```

Đây chỉ là ví dụ `module-info.java`: các package và module được nêu phải tồn tại thật khi dùng. Không giả định mọi package trong `java.base` đều có thể mở tùy ý. Đổi kiến trúc core reflection không gỡ bỏ strong encapsulation.

## 4. Thực hành: kiểm chứng hành vi thay vì soi lớp nội bộ

Tệp dưới đây chỉ sử dụng API Java công khai, không phụ thuộc vào tên accessor bên trong JDK. Nó kiểm chứng tra cứu, gọi method, constructor, field, trường hợp đối số sai, ngoại lệ đích và quyền truy cập riêng tư của một fixture cục bộ.

Tạo `ReflectionContractCheck.java` (không khai báo `package`) với nội dung:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Objects;

public final class ReflectionContractCheck {
    @FunctionalInterface
    interface Action {
        void run() throws Exception;
    }

    static void require(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    static void equal(Object actual, Object expected) {
        require(Objects.equals(actual, expected),
                "expected=" + expected + ", actual=" + actual);
    }

    static <T extends Throwable> T expect(
            Class<T> type, Action action) throws Exception {
        try {
            action.run();
        } catch (Throwable actual) {
            if (type.isInstance(actual)) return type.cast(actual);
            throw new AssertionError("expected=" + type.getName()
                    + ", actual=" + actual.getClass().getName(), actual);
        }
        throw new AssertionError("expected exception " + type.getName());
    }

    public static void main(String[] args) throws Exception {
        Constructor<Sample> ctor = Sample.class.getConstructor(int.class);
        Sample target = ctor.newInstance(10);
        equal(target.value, 10);

        Method increment = Sample.class.getMethod("increment", int.class);
        equal(increment.invoke(target, Integer.valueOf(2)), 12);
        equal(increment.getReturnType(), int.class);

        expect(NoSuchMethodException.class,
                () -> Sample.class.getMethod("increment", Integer.class));
        expect(IllegalArgumentException.class,
                () -> increment.invoke(target, "2"));

        Method explode = Sample.class.getMethod("explode");
        InvocationTargetException wrapped = expect(
                InvocationTargetException.class,
                () -> explode.invoke(target));
        require(wrapped.getCause() instanceof IllegalStateException,
                "method target exception type");
        equal(wrapped.getCause().getMessage(), "target-failed");

        Field field = Sample.class.getField("value");
        equal(field.getInt(target), 10);
        field.setInt(target, 99);
        equal(target.value, 99);
        expect(IllegalArgumentException.class,
                () -> field.set(target, "ninety-nine"));

        Method hidden = Sample.class.getDeclaredMethod("secret");
        require(!hidden.canAccess(target), "private access initially denied");
        require(hidden.trySetAccessible(), "fixture private access opened");
        equal(hidden.invoke(target), "fixture-only");

        System.out.println("status=PASS java=" + Runtime.version());
    }
}

// Top-level class khác, không cùng nest với ReflectionContractCheck.
class Sample {
    public int value;

    public Sample(int value) {
        this.value = value;
    }

    public int increment(int amount) {
        return value + amount;
    }

    public void explode() {
        throw new IllegalStateException("target-failed");
    }

    private String secret() {
        return "fixture-only";
    }
}
```

Biên dịch và chạy trên JDK đang kiểm chứng:

```bash
javac ReflectionContractCheck.java
java ReflectionContractCheck
```

Nếu các điều kiện trên được đáp ứng, chương trình **dự kiến** in một dòng có dạng `status=PASS java=<phiên bản JDK>`. Đây là kỳ vọng của mã ví dụ, không phải kết quả benchmark hay log đã chạy trong tài liệu.

**Vì sao dùng hai top-level class?** Một nested class có thể cùng *nest* với mã kiểm thử và vì vậy được cấp quyền truy cập private theo quy tắc nestmate. Để kiểm chứng `canAccess` thực sự ban đầu trả `false`, fixture nằm ở top-level class khác. Phép thử chạy trên classpath trong **unnamed module**, nên `trySetAccessible()` được dùng trong phạm vi có thể mở quyền; không suy kết quả này cho các named module không `opens`.

Muốn so sánh JDK, chạy lại nguyên tệp trên từng JDK và ghi rõ phiên bản, mã thoát, ngoại lệ và kết quả; không `assert` tên lớp nội bộ, frame trong stack trace hay thời gian thực thi của đoạn code nhỏ này.

## 5. Hiệu năng: thay đổi triển khai không bảo đảm nhanh hơn ở mọi trường hợp

JEP 416 đưa reflection lên cơ chế method handles, tạo cơ hội tối ưu hóa tốt cho một số dạng sử dụng. Tuy nhiên, JIT có khả năng tối ưu hóa khác nhau tùy việc đối tượng `Method`, `Constructor` hay `Field` có thể được nhìn nhận như một **hằng số ổn định** hay thay đổi giữa các lần gọi. Kết quả còn chịu ảnh hưởng của phiên bản JDK, kiến trúc CPU, thời gian warmup, caching, kiểm tra quyền, boxing/unboxing và thân method đích.

Ví dụ, hai đoạn sau đều có thể hợp lệ về mặt nghiệp vụ nhưng biểu diễn workload khác nhau:

```java
// Tra cứu một lần: phản ánh cách framework lưu metadata.
Method method = Service.class.getMethod("execute", String.class);
for (String input : inputs) {
    method.invoke(service, input);
}

// Tra cứu trong vòng lặp: đo cả chi phí lookup mỗi lần.
for (String input : inputs) {
    Method method = Service.class.getMethod("execute", String.class);
    method.invoke(service, input);
}
```

Trong đoạn trên, `Service`, `service`, `inputs` là các biến/lớp minh họa. Khác biệt về kết quả đo không thể chỉ quy về "core reflection của JDK nào nhanh hơn" nếu chi phí tra cứu cũng đổi. Khi phân tích hiệu năng, cần xác định chính xác phần nào thuộc **lookup**, phần nào thuộc **invoke** và phần nào thuộc logic của method đích.

### 5.1. Ma trận yếu tố ảnh hưởng

| Yếu tố | Điều cần kiểm soát | Vì sao ảnh hưởng kết quả |
| --- | --- | --- |
| **Metadata** | Lưu `Method`/`Field`/`Constructor` hay tìm lại mỗi thao tác | Lookup có chi phí khác invoke |
| **Mức độ ổn định** | Cùng một member lặp lại hay luân phiên nhiều member | JIT có thể tối ưu tốt hơn khi đích gọi ổn định |
| **Kiểu dữ liệu** | Đối số nguyên thủy, đối tượng, số lượng tham số, kết quả `void` | Boxing/unboxing và chuyển đổi kiểu góp vào chi phí |
| **Quyền truy cập** | Public, private đã được phép mở, named module và `opens` | Kiểm tra quyền và điều kiện tiếp cận khác nhau |
| **Phần việc của method đích** | Hàm rất nhỏ hay nghiệp vụ có I/O, khóa, cấp phát | Phần việc đích có thể che khuất chi phí dispatch |
| **Trạng thái JVM** | Warmup, JIT compilation, GC, chạy nguội hay đã ổn định | Thời gian đầu và thời gian steady-state không tương đương |
| **Bản JDK/hệ máy** | Vendor, phiên bản, tùy chọn JVM, CPU và OS | Triển khai và tối ưu hóa có thể thay đổi |

Đặc biệt, một benchmark mà `Method` được giữ trong biến có thể thay đổi không nhất thiết cho JIT cùng cơ hội tối ưu như trường hợp metadata là tham chiếu **ổn định và có thể chứng minh là hằng**. Đây là một góc nhìn quan trọng khi đọc các kết quả đo liên quan JEP 416. Nó không mang nghĩa mọi `static final Method` đều chắc chắn nhanh hoặc mọi method lookup động đều chậm.

## 6. Thiết kế benchmark có thể lặp lại

Để đo hiệu năng microbenchmark trên JVM, **JMH (Java Microbenchmark Harness)** là công cụ phù hợp vì hỗ trợ warmup, nhiều lần đo, fork JVM và tổ chức trạng thái. JMH là công cụ độc lập, không phải thành phần tích hợp sẵn của JDK. Phần dưới cung cấp *mẫu benchmark*; cần cấu hình dependencies và annotation processor của JMH trong dự án benchmark thực tế trước khi chạy.

### 6.1. So sánh cùng một phép toán

```java
package bench;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Level;

@State(Scope.Thread)
public class InvocationBench {
    public static class Counter {
        public int addOne(int input) {
            return input + 1;
        }
    }

    private final Counter counter = new Counter();
    private Method reflected;
    private MethodHandle handle;

    @Setup(Level.Trial)
    public void setup() throws ReflectiveOperationException {
        reflected = Counter.class.getMethod("addOne", int.class);
        handle = MethodHandles.lookup().findVirtual(
                Counter.class, "addOne",
                MethodType.methodType(int.class, int.class));
    }

    @Benchmark
    public int direct() {
        return counter.addOne(41);
    }

    @Benchmark
    public int reflectionCached() throws Exception {
        return (int) reflected.invoke(counter, 41);
    }

    @Benchmark
    public int methodHandleCached() throws Throwable {
        return (int) handle.invokeExact(counter, 41);
    }
}
```

Ba trường hợp trả cùng kết quả `42`, nhưng **không phải ba API có ngữ nghĩa giống hệt**: `Method.invoke` gồm kiểm tra/chuyển đổi đối số và bọc ngoại lệ từ code đích; `MethodHandle.invokeExact` yêu cầu kiểu lời gọi khớp chính xác và truyền ngoại lệ theo hợp đồng riêng. Vì vậy số đo là chi phí của **ba cách gọi cụ thể**, không đo thuần một thành phần nội bộ của JDK.

JMH sử dụng giá trị trả về từ `@Benchmark` để giảm nguy cơ phép đo bị tối ưu loại bỏ. Nếu benchmark thực hiện thao tác không có đầu ra quan sát được, có thể dùng `Blackhole` đúng mục đích. Đừng dùng `System.nanoTime()` bên trong một vòng lặp tự viết rồi kết luận trực tiếp từ số lần lặp quá nhỏ: biên dịch JIT, khởi tạo lớp, dead-code elimination và nhiễu hệ thống có thể làm kết quả sai lệch nghiêm trọng.

### 6.2. Tách chi phí lookup, invoke và đối tượng metadata

Trong một suite bổ sung, tạo các nhóm phép đo độc lập:

1. **Lookup only:** lặp lại `Class.getMethod(...)` với một chữ ký xác định và tiêu thụ kết quả.
2. **Invoke with cached metadata:** dùng một `Method` được tìm sẵn trong bước `@Setup`.
3. **Invoke with stable constant metadata:** khi kiến trúc cho phép, dùng tham chiếu bất biến có đường khởi tạo ổn định và mô tả rõ cách JIT nhìn thấy nó.
4. **Dynamic member selection:** thay đổi thành viên hợp lệ giữa các lần đo để đại diện cho framework chọn method theo dữ liệu đầu vào.
5. **Field access:** đo riêng `Field.getInt`/`setInt` và trường hợp trực tiếp tương đương; chỉ thêm `VarHandle` nếu thật sự cần so sánh lựa chọn API.

Không so sánh một case có lookup trong vòng lặp với case còn lại được cache rồi gán toàn bộ khác biệt cho JEP 416. Với case thay đổi member, cần bảo đảm các member có hành vi tương đương, dữ liệu đầu vào hợp lệ và đầu ra được tiêu thụ để phép đo không biến thành trường hợp tối ưu bỏ hết công việc.

### 6.3. Bản ghi kết quả nên có

| Thuộc tính | Ví dụ nội dung cần ghi |
| --- | --- |
| Môi trường | Vendor/JDK build, phiên bản Java, OS, CPU và tùy chọn JVM |
| Cấu hình đo | Số fork, warmup iteration, measurement iteration, thread, mode và đơn vị |
| Workload | `direct`, `reflectionCached`, `methodHandleCached`, thao tác cụ thể và kiểu dữ liệu |
| Cách giữ metadata | Lookup mỗi lần, cached instance, constant hoặc dynamic selection |
| Kết quả | Score, error/confidence interval do JMH báo và toàn bộ raw output |
| Điều kiện so sánh | Cùng input, cùng môi trường tải máy và tương ứng về chức năng |

Ví dụ **mẫu bảng trống**, không được xem là số liệu thực nghiệm:

| Phương án | JDK A (ns/op) | JDK B (ns/op) | Nhận xét |
| --- | ---: | ---: | --- |
| Direct | Chưa đo | Chưa đo | Baseline lời gọi thông thường |
| Reflection, metadata cache | Chưa đo | Chưa đo | Đo dispatch reflection sau lookup |
| MethodHandle, metadata cache | Chưa đo | Chưa đo | Có ngữ nghĩa lời gọi khác reflection |
| Reflection, chọn member động | Chưa đo | Chưa đo | Kiểm tra ảnh hưởng tính ổn định metadata |

Chỉ kết luận nhanh/chậm khi có số liệu đo đủ tin cậy và biết được workload có đại diện cho ứng dụng thực hay không. Kết quả của một microbenchmark không tự động dự đoán hiệu năng hệ thống có I/O, bộ nhớ đệm, phân luồng hoặc GC phức tạp.

## 7. Phân biệt `Method`, `MethodHandle` và `VarHandle`

| Tiêu chí | Core reflection | Method handles | Var handles |
| --- | --- | --- | --- |
| Điểm vào | `Method`, `Constructor`, `Field` | `MethodHandle`, `MethodHandles.Lookup` | `VarHandle`, tìm qua `MethodHandles.Lookup` |
| Mô hình | Metadata để khám phá và thao tác động | Đối tượng gọi có kiểu phương thức, hỗ trợ kết hợp handle | Truy cập biến với các access mode và semantics bộ nhớ rõ ràng |
| Thông tin lỗi | `InvocationTargetException` cho lỗi từ method/constructor đích | Ngoại lệ đích thường truyền trực tiếp qua lời gọi handle | Lỗi kiểu lời gọi/truy cập theo access mode của VarHandle |
| Quyền truy cập | Kiểm tra khi thao tác; quy tắc module và `AccessibleObject` | Quyền gắn với lookup và cách tạo handle; vẫn chịu quy tắc truy cập | Quyền gắn với lookup và field/array tương ứng; có access mode riêng |
| Có phải thay thế bắt buộc sau Java 18? | Không | Không | Không |

`MethodHandle` là **API công khai riêng** trong `java.lang.invoke`; việc JDK dùng method handles bên trong reflection không có nghĩa `Method.invoke` và `MethodHandle.invokeExact` trở thành tương đương 1:1. Khác biệt về tìm kiếm, chữ ký, kiểm tra kiểu và cách bọc ngoại lệ vẫn phải được tính đến nếu ứng dụng quyết định thay API.

Với một framework hiện có, lý do cân nhắc `MethodHandle` hoặc `VarHandle` thường là cần mô hình gọi/truy cập phù hợp và có bằng chứng benchmark cho workload cụ thể. Tránh đổi API chỉ vì kỳ vọng chung rằng một cơ chế chắc chắn nhanh hơn ở mọi JDK.

## 8. Những khẳng định dễ sai khi nâng cấp JDK

- **"Java 18 đã bỏ reflection cũ, phải dùng `MethodHandle`."** Sai. Core reflection công khai vẫn được hỗ trợ; JEP 416 nói về tái triển khai nền tảng.
- **"Đổi backend có nghĩa ngoại lệ và quy tắc truy cập cũng đổi."** Sai nếu không có thay đổi API được tài liệu hóa. Kiểm tra `Method.invoke`, `Constructor.newInstance`, `Field.get/set` bằng hành vi công khai, không nhìn stack trace nội bộ.
- **"Kết quả của Java 18 chắc chắn nhanh hơn mọi JDK khác."** Sai. Không có bảo đảm tốc độ cho mọi workload; kết quả phụ thuộc metadata, JIT và môi trường.
- **"`getDeclaredMethod` tìm thấy private method thì có thể gọi ngay."** Sai. Tìm kiếm và kiểm tra quyền truy cập là hai bước khác nhau.
- **"Nếu JDK triển khai reflection bằng method handles, đổi sang `invokeExact` chắc chắn tương đương."** Sai. Chữ ký và quy tắc ngoại lệ của hai API khác nhau.
- **"Có thể khẳng định tương thích chỉ vì chương trình biên dịch được."** Chưa đủ. Cần kiểm tra kết quả, kiểu ngoại lệ, quyền module, các ca biên và workload thật.
- **"Tối ưu hóa đã thấy trong một benchmark nhỏ là cam kết lâu dài."** Sai. Đó chỉ là quan sát gắn với cấu hình đo đã ghi lại.

## 9. Quy trình đánh giá khi nâng cấp từ một JDK sang JDK khác

1. **Chốt bề mặt API:** liệt kê các lời gọi `Class`, `Method`, `Constructor`, `Field`, `AccessibleObject` và nơi dùng `MethodHandle`/`VarHandle` nếu có.
2. **Viết bảng hợp đồng:** cho mỗi thao tác ghi member, kiểu receiver, kiểu tham số, kết quả mong đợi và ngoại lệ dự kiến; thêm ca thiếu quyền và ca sai chữ ký.
3. **Chạy kiểm thử hành vi:** chạy ví dụ kiểm chứng hoặc suite của dự án trên từng JDK với cùng cấu hình classpath/module path. Nếu có named module, ghi rõ `exports`/`opens`.
4. **Chụp cấu hình hiệu năng:** xác định lookup được cache hay lặp lại, member có ổn định không, workload đủ nóng hay gồm khởi động lạnh.
5. **Chạy benchmark đáng tin cậy:** dùng JMH, fork riêng, warmup và ghi log đầy đủ; đối chiếu với đo profiling của ứng dụng thật.
6. **Ra quyết định dựa trên mục tiêu:** nếu hợp đồng giữ nguyên nhưng benchmark biến động, kiểm tra nguyên nhân và ảnh hưởng thực tế trước khi cân nhắc đổi thiết kế.

Trong báo cáo, trình bày **hai kết luận riêng**: (a) tương thích hành vi công khai `PASS/FAIL` theo ca kiểm chứng; (b) hiệu năng tăng/giảm bao nhiêu theo kết quả đo đã được kiểm soát. Việc ghép hai kết luận thành một câu như "backend mới nhanh hơn nên API đã thay đổi" là sai phạm vi suy luận.

## 10. Câu hỏi tự kiểm tra

1. JEP 416 thay đổi điều gì ở triển khai core reflection và điều gì không được phép suy ra từ thay đổi đó?
2. Khi `Method.invoke` ném `InvocationTargetException`, bạn cần kiểm tra trường nào để biết lỗi thực sự từ method đích?
3. Vì sao `Class.getDeclaredMethod` và `Method.invoke` là hai giai đoạn có tiêu chí kiểm chứng khác nhau?
4. Nếu một benchmark tìm `Method` mỗi lần, còn benchmark khác cache `Method`, phép so sánh đang trộn những loại chi phí nào?
5. Tại sao `MethodHandle.invokeExact` không thể được xem là một phép thay thế hoàn toàn tương đương cho `Method.invoke`?
6. Khi kết quả hiệu năng đổi giữa hai JDK nhưng tất cả ca hợp đồng đều PASS, báo cáo nâng cấp nên diễn giải ra sao?

**Tài liệu chuẩn nên tra cứu với đúng phiên bản JDK:** JEP 416 (*Reimplement Core Reflection with Method Handles*); Javadoc `java.lang.Class`, `java.lang.reflect.Method`, `Constructor`, `Field`, `AccessibleObject`; và các API `java.lang.invoke.MethodHandle`, `MethodHandles`, `VarHandle`. Các phần công khai này tiếp tục là nền tảng kiểm chứng thích hợp trên JDK hiện đại, trong khi chi tiết triển khai và số liệu hiệu năng cần được quan sát lại theo từng runtime.
