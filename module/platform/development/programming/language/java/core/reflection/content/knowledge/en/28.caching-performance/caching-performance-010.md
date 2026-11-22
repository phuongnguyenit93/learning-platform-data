# Chi tiết triển khai reflection có thể thay đổi giữa các phiên bản JDK

## 1. Phân biệt hợp đồng API với cơ chế nội bộ của JDK

Trong Java, **core reflection** là tập API chuẩn như `java.lang.Class`, `java.lang.reflect.Method`, `Constructor`, `Field`, `AccessibleObject`. Ứng dụng dùng API để khám phá thông tin về kiểu và thao tác lên các thành viên ở runtime. Chẳng hạn:

```java
Method add = Counter.class.getMethod("add", int.class);
Object result = add.invoke(counter, 2);
```

Đây là fragment cần có `Counter`, `counter` và import `java.lang.reflect.Method`. Hợp đồng quan trọng là tìm đúng phương thức, kiểm tra quyền truy cập, kiểm tra đối số, thực thi method, trả kết quả và báo ngoại lệ theo Javadoc. **Cách JDK chuyển lời gọi phản chiếu thành thao tác JVM không nằm trong cam kết ổn định của public API.**

Một JDK có thể dùng native entry, lớp hỗ trợ được sinh động, `MethodHandle`, `VarHandle`, JIT intrinsics hoặc cơ chế khác. Những chi tiết ấy được quyền thay đổi miễn là tiếp tục đáp ứng đặc tả Java SE, trừ khi bản nâng cấp còn có thay đổi API/semantics được công bố riêng. Vì vậy:

- Có thể kỳ vọng `Method.invoke`, `Field.get` và `Constructor.newInstance` thực hiện đúng hành vi theo **Javadoc của phiên bản mục tiêu**.
- Không nên giả định đường gọi nội bộ, tên lớp như `DelegatingMethodAccessorImpl`, tên field private của JDK hoặc ngưỡng tối ưu hóa là một giao diện công khai.
- Không suy ra rằng cùng một lời gọi reflection luôn có cùng thời gian thực thi trên JDK khác nhau, hoặc ngay giữa các giai đoạn warm-up của cùng một JVM.
- Không đồng nhất việc thay đổi implementation với thay đổi ý nghĩa API; một lần nâng JDK vẫn cần test regression để xác nhận behavior và performance thực tế.

Bài học này thuộc chủ đề **cache và hiệu năng**: hiểu lịch sử thay đổi triển khai reflection sẽ giúp thiết kế cache, đánh giá benchmark và lập kế hoạch nâng JDK chính xác hơn.

## 2. Một ví dụ có thật: JEP 416 trong JDK 18

[**JEP 416 — Reimplement Core Reflection with Method Handles**](https://openjdk.org/jeps/416) được đưa vào **JDK 18**. Mục tiêu chính là đơn giản hóa việc bảo trì: triển khai core reflection dùng chung nền tảng với `java.lang.invoke`, giảm các đường mã nội bộ trùng lặp.

| Giai đoạn của OpenJDK | Mô hình triển khai đáng chú ý | Điều cần hiểu |
| --- | --- | --- |
| JDK 17 trở về trước (mô hình truyền thống) | Lời gọi `Method.invoke`/constructor reflective ban đầu có thể đi qua native accessor; sau một ngưỡng, hệ thống *inflation* sinh accessor bytecode hỗ trợ lặp gọi | Đây là **implementation detail**, không phải hợp đồng rằng số lần N luôn kích hoạt một lớp accessor cụ thể trên mọi JVM |
| JDK 18–21 | Core reflection được triển khai lại trên nền `MethodHandle` cho `Method`/`Constructor` và `VarHandle` cho `Field` | Người dùng tiếp tục gọi public API cũ; lớp nội bộ và đặc tính hiệu năng có thể khác |
| JDK 22 trở đi (OpenJDK) | Triển khai core reflection cũ đã được loại bỏ | Đừng dựa vào cờ tạm thời để quay lại legacy implementation; tài liệu JDK 22 xác nhận nó không còn tác dụng |

### Mô hình trước JDK 18: “inflation” là gì?

Trong một số triển khai HotSpot/OpenJDK trước JDK 18, lần gọi reflection đầu có thể đi qua accessor sử dụng mã native. Sau một số lần gọi, JDK có thể chuyển sang accessor sinh động bằng bytecode để tránh lặp đi qua native. Cơ chế này được gọi là *inflation*. Các lớp hỗ trợ nội bộ và cách chúng được JIT xử lý tạo ra chi phí warm-up, code generation và nhiều code path cần bảo trì.

Đó là lý do một số bài benchmark cũ quan sát thấy thời gian gọi reflection trước và sau warm-up khác nhau. **Không đưa kết luận này thành quy luật cố định của Java language**: threshold, tên property nội bộ, hiệu ứng tối ưu hóa và lựa chọn implementation tùy bản JDK/nhà cung cấp.

### Sau JEP 416: “dùng MethodHandle” có ý nghĩa gì?

Trong OpenJDK từ JDK 18, `Method.invoke` được hỗ trợ qua method handles, constructor invocation qua method handles và accessor của field qua var handles. Điều này **không có nghĩa** API `Method.invoke` biến thành `MethodHandle.invokeExact` đối với người dùng.

Các khác biệt ở public API vẫn tồn tại:

- `Method.invoke` tiếp tục nhận `Object...` và trả về `Object`; phương thức đích ném exception thì reflection bọc nguyên nhân trong `InvocationTargetException`.
- `MethodHandle.invokeExact` yêu cầu chữ ký tại call site khớp đúng `MethodType` của handle và ném trực tiếp ngoại lệ từ mục tiêu (trừ những lỗi khi bản thân handle được gọi sai).
- `Field.get/set` vẫn tuân theo kiểu, quyền truy cập và quy tắc chuyển đổi của reflection; `VarHandle` cung cấp thêm các access mode có ngữ nghĩa bộ nhớ/atomic khác nhau.
- `AccessibleObject` và kiểm tra quyền theo JPMS vẫn có hợp đồng riêng, không bị loại bỏ chỉ vì implementation nền dùng `java.lang.invoke`.

Tài liệu phát hành [Oracle JDK 18](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html) mô tả một số rủi ro tương thích đối với code **dựa vào chi tiết không được tài liệu hóa**. Chẳng hạn, code tự kiểm tra các lớp accessor nội bộ hoặc cố sửa trường `modifiers` private trong `Method`/`Field`/`Constructor` có thể bị ảnh hưởng. Đây là ví dụ rõ ràng về lý do tránh phụ thuộc JDK internals.

### Cờ tương thích cũ không phải giải pháp lâu dài

JEP 416 từng cung cấp system property `-Djdk.reflect.useDirectMethodHandle=false` làm phương án tạm để quay lại implementation cũ trong những bản JDK còn chứa nó. **JDK 22 đã loại bỏ implementation cũ và cờ trên trở thành no-op** theo [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html). Không dùng property này như cấu hình hiệu năng hoặc phương án khắc phục lâu dài trên các JDK hiện đại.

Nếu cần thử nghiệm hồi quy trên JDK 18–21, nên coi property đó là công cụ chẩn đoán *gắn với đúng phiên bản được hỗ trợ*, không là public contract. Các JDK khác nhà cung cấp có thể khác; luôn kiểm tra release notes của bản phân phối đang chạy.

## 3. Điều gì ổn định, điều gì có thể đổi?

### Hành vi được xác định qua public API

Các thao tác sau là điều ứng dụng nên dựa vào **theo Javadoc của JDK mục tiêu**:

- `Class#getMethod(name, parameterTypes)` tìm public method theo tên và kiểu tham số, hoặc ném `NoSuchMethodException` nếu không tìm thấy.
- `Method#invoke(receiver, args)` yêu cầu receiver phù hợp cho instance method; static method bỏ qua receiver; số lượng và kiểu argument phải tương thích.
- `Constructor#newInstance(args)` tạo instance theo constructor được chọn, với kiểm tra truy cập và đối số.
- `Field#get(receiver)`/`set(receiver, value)` đọc/ghi field theo quyền và kiểu; field `final` có hạn chế riêng.
- Khi code của method/constructor đích ném ngoại lệ, `Method.invoke`/`Constructor.newInstance` phản ánh ngoại lệ qua `InvocationTargetException`.
- Quyền truy cập phản chiếu được kiểm soát bởi ngôn ngữ Java và Java Platform Module System; `setAccessible(true)` không mặc nhiên vượt qua ranh giới module.

Những điều này đủ để ứng dụng tương tác với reflection mà không quan tâm accessor được gọi qua native, bytecode hay method handle ở bên trong.

### Chi tiết không nên lấy làm hợp đồng

| Giả định nội bộ | Tại sao nguy hiểm |
| --- | --- |
| Cụ thể lớp triển khai `MethodAccessor`/`FieldAccessor` | JEP 416 đã thay đường triển khai; một bản JDK có thể bỏ lớp nội bộ |
| Ngưỡng “inflation” hoặc property không được chuẩn hóa | Có thể bị đổi, bị bỏ hoặc hoàn toàn vô hiệu ở phiên bản sau |
| Thứ tự `getDeclaredMethods()`/`getDeclaredFields()` | Javadoc không cam kết thứ tự theo source; muốn kết quả ổn định phải sort có chủ đích |
| Cách `Method`/`Field` giữ internal cache/accessor | Layout private field và cache strategy có thể thay đổi |
| Một con số “reflection chậm hơn trực tiếp X lần” | Thay đổi theo JDK, workload, kiểu lời gọi, compiler, warm-up và cách giữ metadata |
| Private JDK package như `jdk.internal.reflect` | Không thuộc API Java SE công khai; còn bị giới hạn bởi module encapsulation |
| Stack trace luôn có cùng frame nội bộ | Thay đổi implementation có thể thay đổi helper frames; không parse theo tên class nội bộ |

Ngay cả khi public API ổn định, việc nâng JDK có thể mang theo thay đổi **được công bố** ở API, kiểm soát truy cập, cảnh báo hoặc behavior. Vì vậy kiểm tra compatibility phải đọc release notes và chạy test chứ không chỉ dựa vào câu “implementation detail”.

## 4. Ví dụ Java 17+: API công khai cho kết quả nhất quán

Chương trình sau dùng reflection để tạo object, gọi method, đọc/ghi field; dùng `ClassValue<Method>` làm **ví dụ cache metadata** theo class; và gọi cùng logic qua `MethodHandle` để thấy API ngoài khác nhau nhưng kết quả nghiệp vụ không thay đổi. Không đọc lớp private của JDK, không kiểm tra accessor internals và không dựa vào time measurement.

Lưu thành file **`ReflectionUpgradeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionUpgradeDemo {
    public static final class Counter {
        public int value;

        public Counter(int start) {
            value = start;
        }

        public int add(int delta) {
            return value += delta;
        }
    }

    // Cache metadata theo Class<?>; không cache giá trị của từng object.
    private static final ClassValue<Method> ADD = new ClassValue<>() {
        @Override
        protected Method computeValue(Class<?> type) {
            try {
                return type.getMethod("add", int.class);
            } catch (NoSuchMethodException e) {
                throw new IllegalStateException(e);
            }
        }
    };

    public static void main(String[] args) throws Throwable {
        Constructor<Counter> constructor =
                Counter.class.getConstructor(int.class);
        Counter counter = constructor.newInstance(5);

        Method method = ADD.get(Counter.class);
        Object result = method.invoke(counter, 2);

        Field field = Counter.class.getField("value");
        System.out.println("reflection invoke: " + result);
        System.out.println("reflection field: " + field.getInt(counter));
        System.out.println("metadata cached: "
                + (method == ADD.get(Counter.class)));

        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Counter.class,
                "add",
                MethodType.methodType(int.class, int.class));
        Counter other = new Counter(5);
        int fromHandle = (int) handle.invokeExact(other, 2);
        System.out.println("method handle: " + fromHandle);

        field.setInt(counter, 11);
        System.out.println("field after set: " + field.getInt(counter));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 ReflectionUpgradeDemo.java
java ReflectionUpgradeDemo
```

Stdout dự kiến:

```text
reflection invoke: 7
reflection field: 7
metadata cached: true
method handle: 7
field after set: 11
```

Ý nghĩa:

1. `Constructor.newInstance(5)` tạo `Counter(5)`; `Method.invoke(counter, 2)` cho kết quả `7`.
2. `ClassValue` lưu `Method` theo `Class<?>`. Hai lần `ADD.get(Counter.class)` trong cùng lần chạy trả cùng đối tượng metadata ở ví dụ này; không có `remove` hay thay đổi cache giữa hai lần đọc.
3. `MethodHandle` gọi `Counter.add` trên instance khác với chữ ký cụ thể `(Counter,int)int` và trả `7`.
4. `Field.setInt` thay giá trị trên instance thứ nhất thành `11` rồi `getInt` đọc lại `11`.
5. **Code không khẳng định hai cách gọi có cùng tốc độ**. Nó là regression test cho behavior công khai, có thể chạy lại trên nhiều JDK và so stdout.

Lệnh sau dùng để ghi nhận JDK đang chạy, nhưng phần output **phụ thuộc máy** nên không gộp vào stdout cố định ở trên:

```bash
java -version
javac -version
```

Nếu máy có nhiều JDK, đảm bảo `java` và `javac` dùng phiên bản mong muốn (qua `JAVA_HOME`/`PATH` hoặc đường dẫn tuyệt đối). Tham số `--release 17` đảm bảo biên dịch với API mục tiêu Java 17, **không tự biến JVM đang chạy thành JDK 17**.

## 5. Hiệu năng reflection phụ thuộc call site và mức độ “constant”

JEP 416 nêu một vấn đề quan trọng: khi đối tượng `Method`/`Constructor`/`Field` được JVM nhận diện là hằng tại vị trí dùng (ví dụ giữ trong `static final` và được compiler tối ưu phù hợp), triển khai mới có thể tối ưu tốt; khi metadata nằm trong dữ liệu động mà JIT không nhìn thấy như constant, đường gọi có thể kém hơn ở một số microbenchmark.

**Không hiểu nhầm `final` tự động làm mọi call site nhanh:** khả năng constant folding và inlining là quyết định của JVM/JIT, không cam kết ngôn ngữ. Không phải mọi cached `Method` đều trở thành hằng theo cách JIT cần; `ClassValue` là giải pháp cache metadata theo class, không tự đảm bảo tối ưu invocation tương tự một field `static final`.

Tách ít nhất bốn loại chi phí khi phân tích:

| Giai đoạn | Ví dụ | Điểm cần đo |
| --- | --- | --- |
| Khám phá member | `clazz.getMethod(...)`, `getDeclaredFields()` | Tần suất gọi, cache misses, classloader |
| Kiểm tra quyền/chuẩn hóa đối số | Receiver, access checks, boxing/unboxing | Loại access, chữ ký, số lượng argument |
| Thực thi lời gọi | `Method.invoke(...)`, `MethodHandle.invokeExact(...)`, direct method | JIT inlining, target polymorphism, loại method, call site |
| Đời sống metadata/cache | `ClassValue`, map theo `Class<?>` | Memory retention, module/classloader unload, cache invalidation |

Ví dụ sai điển hình khi benchmark:

```java
// Đo cả lookup lẫn invoke, không cô lập chi phí gọi:
for (int i = 0; i < count; i++) {
    Method method = type.getMethod("run");
    method.invoke(target);
}
```

Đây là fragment minh họa (cần biến `type`, `target`, `count` và xử lý exception). Kết quả được đo sẽ bao gồm lookup, có thể cộng thêm các ảnh hưởng từ cache của JDK, JIT và exception. Nếu muốn biết **chi phí invocation riêng**, đưa lookup ra ngoài phần đo; nhưng vẫn cần thử workload dynamic lookup nếu đó là hành vi thực tế của ứng dụng.

Dùng `MethodHandle` cũng không mặc nhiên nhanh hơn `Method.invoke`: các trường hợp typed/exact call và constant handle dễ được tối ưu hơn; dynamic handle, chuyển kiểu hoặc `invokeWithArguments` có thể phát sinh overhead. Lựa chọn API trước hết dựa theo semantic và quyền truy cập, sau đó benchmark nếu tốc độ thực sự quan trọng.

## 6. Cache metadata an toàn qua nhiều phiên bản JDK

Cache có giá trị khi cùng class và policy được dùng lặp lại, nhất là framework phải quét nhiều object. Tuy nhiên, **cách cache** phải tránh giữ classloader/plugin đã được unload.

### `ClassValue<T>`

`ClassValue<T>` gắn một giá trị tính theo đối tượng `Class<?>` và để runtime quản lý vòng đời cache gắn với class. Nó phù hợp cho metadata bất biến theo kiểu, ví dụ danh sách property đã chuẩn hóa hoặc `Method` tương ứng. Trong chương trình trên, `ClassValue<Method>` tránh phải tìm lại `getMethod("add", int.class)` mỗi lần.

Lưu ý: `ClassValue.computeValue` có thể được thực thi nhiều lần trong trường hợp cạnh tranh; thiết kế công việc tính toán như một thao tác **không side effect nguy hiểm**. Nếu policy thay đổi, giá trị cache cũng phải được invalidation hoặc key/cấu trúc cache phải gồm phiên bản policy. Không cache trường dữ liệu hoặc kết quả method theo `Class<?>` nếu giá trị thuộc từng instance.

### Map và ràng buộc classloader

`ConcurrentHashMap<Class<?>, AccessPlan>` thường nhanh và thuận tiện, nhưng key/value có thể giữ tham chiếu tới `Class<?>`, `Method`, `Field` hoặc `MethodHandle`, từ đó làm classloader không được GC sau hot reload/plugin unload. Cân nhắc `ClassValue`, bộ cache giới hạn vòng đời hoặc cơ chế weak-key phù hợp; xem cả **value có vòng tham chiếu về class hay không**.

### Không cache trạng thái không có trong hợp đồng

Không truy cập trường private của `Method` để giữ accessor nội bộ hoặc đoán threshold inflation. Sử dụng metadata công khai, và nếu cần gọi với kiểu cố định qua handle, xây/cấu hình handle bằng `MethodHandles.Lookup` với quyền hợp lệ. Lỗi reflection access có thể phụ thuộc module và caller context; không dùng kết quả cache đã thu dưới quyền khác như bằng chứng mọi caller đều được phép.

## 7. Cách benchmark reflection đúng khi nâng JDK

Đừng so một vòng lặp `System.nanoTime()` duy nhất trên JDK A và B rồi khẳng định JDK mới “nhanh/chậm hơn” dựa trên một con số. JIT, warm-up, garbage collection, CPU scaling và dead-code elimination dễ làm benchmark sai.

Một kế hoạch phù hợp:

1. Chốt **JDK vendor, build, kiến trúc CPU, OS, JVM flags** cho mỗi phép thử; ghi `java -version`.
2. Dùng **JMH** (Java Microbenchmark Harness) cho microbenchmark với fork, warm-up và đo lường rõ ràng; không lấy bài demo ở mục 4 làm benchmark.
3. Đo độc lập `lookup`, `invoke` và workload end-to-end. Có các case: member `static final`, metadata/handle nằm ở field instance, lookup theo class động, method 0/1/nhiều tham số, primitive/reference, public/private hợp lệ.
4. Không để JIT loại bỏ công việc: tiêu thụ kết quả bằng `Blackhole` hoặc trả giá trị hợp lệ theo hướng dẫn của JMH.
5. So kết quả throughput/latency kèm biến thiên giữa nhiều fork; quan sát cả allocation, GC, classloader retention và tốc độ cold startup nếu ứng dụng nhạy với chúng.
6. Chạy **functional regression tests** riêng: permission/JPMS, exception, varargs, conversion, field/constructor behavior. Microbenchmark không thay thế regression test.
7. Nếu có chênh lệch, tìm nguyên nhân bằng profiler/JFR và đổi thiết kế có cơ sở (ví dụ cache metadata hoặc chuẩn hóa call site). Không ép JVM bật lại cơ chế cũ không còn được hỗ trợ.

Không có con số “`Method.invoke` chậm X lần” nào đúng cho mọi JDK. JEP 416 trình bày số liệu của workload và bản JVM tại thời điểm JEP; đó là minh họa cho **trade-off** và lý do đo lại, không phải dự báo cố định cho mọi phiên bản sau.

## 8. Chẩn đoán khác biệt khi nâng JDK

Khi từ JDK 17 nâng lên JDK 21, 22 hoặc một phiên bản mới hơn, hãy phân loại thay đổi:

| Dấu hiệu | Có thể liên quan đến | Hướng xử lý |
| --- | --- | --- |
| Test về `Method.invoke` cùng tham số trả kết quả khác | Thay đổi app dependency/behavior, JDK bug hoặc giả định sai về contract | Viết test tối thiểu, so Javadoc của hai JDK và báo bug nếu có chứng cứ |
| `InaccessibleObjectException` hoặc access failure | Module boundaries, `opens` và quyền lookup | Chuyển sang API public hoặc cấp đúng quyền module, không đọc JDK internals |
| Stack trace xuất hiện frame `java.lang.invoke` mới | Implementation core reflection mới | Debug theo API và cause; không dùng tên helper frame làm điều kiện logic |
| Startup hoặc steady-state latency thay đổi | Chi phí initialization, JIT và loại call site | Dùng JFR/JMH, tách cold vs warmed case |
| System property legacy không còn hiệu quả trên JDK 22+ | Triển khai cũ đã bị loại bỏ | Bỏ workaround và kiểm tra đúng release notes |
| Plugin/hot reload không giải phóng classloader | Metadata cache giữ `Class<?>`/`Method` hoặc classloader | Đánh giá lifecycle cache, `ClassValue` hoặc weak-reference design |

Ví dụ: nếu framework dựa vào internal `MagicAccessorImpl`, thành công trên JDK cũ không chứng minh code là portable. Tìm cách biểu diễn cùng nghiệp vụ bằng `Method`, `Constructor`, `Field`, `MethodHandles.Lookup` hoặc public interfaces thay vì “sửa” bằng reflection vào chính private field của reflection implementation.

Nếu ứng dụng bị lỗi sau nâng JDK, ghi **đúng phiên bản của tất cả JVM chạy** (build container, test worker, IDE, production); xác minh dependencies hỗ trợ JDK đó và tạo minimal reproducer. Không thay đổi cờ VM ngẫu nhiên khi chưa cô lập nguyên nhân.

## 9. Lỗi thường gặp và câu hỏi tự kiểm tra

**Lỗi 1 — Đánh đồng JEP 416 với việc loại bỏ reflection:** JEP 416 là thay đổi cách triển khai **bên dưới** `java.lang.reflect`, không yêu cầu thay tất cả `Method.invoke` thành `MethodHandle`.

**Lỗi 2 — Coi `jdk.reflect.useDirectMethodHandle=false` là cấu hình hiệu năng ổn định:** đây là workaround tạm thời trong một số JDK sau JEP 416; JDK 22 đã loại bỏ implementation cũ.

**Lỗi 3 — Kết luận `ClassValue`/`static final` luôn đảm bảo nhanh hơn:** cache giảm chi phí discovery; JIT có thể tối ưu call site tùy điều kiện, không có cam kết performance tự động.

**Lỗi 4 — Dùng `getDeclaredMethods()` rồi tin vào thứ tự mặc định:** API không hứa sắp theo source. Muốn kết quả ổn định để sinh schema/test, tự sắp xếp.

**Lỗi 5 — Dùng private JDK fields, `sun.reflect.*` hoặc `jdk.internal.reflect.*` như public API:** có rủi ro biên dịch, access và behavior khi nâng JDK. Dùng public reflection/invoke APIs.

**Lỗi 6 — Chỉ chạy test hiệu năng mà bỏ test chức năng:** JIT benchmark không kiểm tra module access, exception wrapping, null receiver hay primitive conversion.

Tự trả lời:

1. JDK 18 có đổi cú pháp `Method.invoke` cho người dùng không? **Không; JEP 416 đổi implementation nội bộ.**
2. Nếu JDK 22 bỏ đường cũ thì `-Djdk.reflect.useDirectMethodHandle=false` còn khôi phục nó được không? **Không; cờ thành no-op.**
3. Framework gọi `Class.getDeclaredMethods()` rồi cần output ổn định thì nên làm gì? **Định nghĩa tiêu chí sắp xếp rõ ràng.**
4. Cache `Method` vào map là bảo đảm performance và không có memory leak phải không? **Không; cần kiểm tra workload và classloader lifecycle.**
5. Muốn so hai bản JDK về chi phí phản chiếu thì đo thế nào? **JMH với warm-up/forks, tách lookup/invoke, giữ workload và môi trường tương đương, kết hợp functional tests.**
6. Tại sao vẫn nên đọc Java SE Javadoc sau khi biết reflection dùng method handles? **Vì hợp đồng public API và implementation nền là hai tầng khác nhau.**

Tài liệu tham khảo:

- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416)
- [Oracle JDK 18 Release Notes — JEP 416](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html)
- [Oracle JDK 22 Release Notes — Remove the Old Core Reflection Implementation](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
- [Javadoc Method (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Javadoc ClassValue (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html)
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
