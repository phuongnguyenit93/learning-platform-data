# 19.2 Tách giai đoạn khám phá và kiểm tra khỏi đường thực thi lặp lại

Trong runtime Java, một hệ thống dùng Reflection, `MethodHandle`, `VarHandle`, annotation hoặc plugin thường phải thực thi một thao tác nhiều nghìn lần, trong khi **tên phương thức, chữ ký, metadata và chính sách ánh xạ** gần như không đổi giữa các request. Nếu mọi lần thực thi đều quét annotation, tìm lại member, kiểm tra modifier, xây `MethodType` rồi chọn adapter, ta lặp lại một công việc vốn chỉ phụ thuộc vào **cấu trúc chương trình**.

Giải pháp là tách rõ:

> **Khám phá (discovery) → kiểm tra hợp đồng ổn định (validation) → chuẩn bị (link/prepare) → công bố kế hoạch (publish) → thực thi nhiều lần (execute).**

Kết quả của giai đoạn chuẩn bị thường là một **execution plan bất biến**: một object chứa `MethodHandle` đã chọn, converter, descriptor và metadata đã xác thực. Đường gọi nóng (hot path) nhận dữ liệu của request, kiểm tra những điều kiện **thực sự thay đổi theo request**, rồi dùng plan đã có.

Điều này giúp phát hiện lỗi cấu hình sớm, giảm công việc lặp và làm rõ quyền truy cập. Tuy nhiên, **không có bảo đảm cố định rằng MethodHandle nhanh hơn mọi cách Reflection**; chi phí phải được đo với JDK, CPU và workload cụ thể. Đây là bài Knowledge cho chủ đề **19. Thiết kế và hiệu năng** trên Java 17+, với hai chương trình đầy đủ đã được biên dịch và kiểm tra output.

## 1. Phân biệt chi phí chuẩn bị với chi phí thực thi

| Hoạt động | Ví dụ | Khi nào thực hiện? |
| --- | --- | --- |
| Khám phá cấu trúc | `getDeclaredMethods()`, đọc annotation, tìm getter, duyệt fields và record components | Khi tạo descriptor/plan hoặc schema thay đổi |
| Kiểm tra hợp đồng cố định | Đúng owner, name, overload, static/instance, parameter types, return type, modifier, quyền truy cập | Trước khi công bố plan |
| Chuẩn bị đường gọi | `Lookup.unreflect`, `findVirtual`, `findStatic`, `asType`, `permuteArguments`, gắn converter | Một lần cho mỗi key/version thích hợp |
| Công bố và cache | `ClassValue`, `ConcurrentHashMap`, immutable registry, `AtomicReference` | Khi plan hợp lệ và sẵn sàng |
| Thực thi | Input validation, authorization hiện hành, decode, `invokeExact`, serialize kết quả, target exception | Mỗi request cần thiết |

Không nên hiểu “validate một lần” là được bỏ mọi kiểm tra ở hot path. **Validation có hai lớp**:

- **Ổn định theo cấu trúc**: route `total` duy nhất, method nhận đúng hai `int` và trả `int`, Lookup có quyền, schema có converter hợp lệ. Có thể đưa ra bước `prepare`.
- **Biến đổi theo request**: số tiền âm, người dùng bị thu hồi quyền, token hết hạn, object hiện tại null, hạn mức giao dịch, trạng thái mutable và payload quá lớn. **Vẫn phải kiểm tra mỗi lượt** hoặc theo giao thức trạng thái hợp lệ.

Trong một hệ thống an toàn, việc tái sử dụng plan **không đồng nghĩa tái sử dụng kết quả authorization của người dùng trước**.

### 1.1. Một kiến trúc hai pha dễ kiểm tra

```text
MODULE / SCHEMA / ROUTE DEFINITION
                |
        [ DISCOVER METADATA ]
                |
        [ VALIDATE CONTRACT ]
                |
        [ BUILD TYPED HANDLES ]
                |
        [ IMMUTABLE PLAN ]
                |
        [ SAFE PUBLICATION ]
                |
        +-------+-------+--------+
        |       |       |        |
      Req1    Req2    Req3     ReqN
        |       |       |        |
     validate current data / current permission
        |       |       |        |
        +---- plan.execute(...) ----+
                       |
                   target logic
```

Giai đoạn prepare có thể diễn ra ở startup, khi mở plugin, trên cache miss có khóa phù hợp hoặc lúc nạp một revision mới. Không nhất thiết phải prepare **mọi** route ngay khi khởi động, nếu chỉ một tập nhỏ được dùng. Điều quan trọng là **mỗi lần chạy lặp lại không vô cớ phải discovery toàn bộ từ đầu**.

## 2. Anti-pattern: tìm member trên mọi request

Xét một service `Checkout` có method instance `int total(int units,int unitPrice)`. Một dispatcher có thể viết:

```java
static int callEveryTime(Object service, int units, int unitPrice)
        throws ReflectiveOperationException {
    Method member = service.getClass().getDeclaredMethod(
            "total", int.class, int.class);
    Object value = member.invoke(service, units, unitPrice);
    return (Integer) value;
}
```

Đây là một **method minh họa**, cần import `java.lang.reflect.Method`, chưa phải chương trình độc lập.

Với mỗi lời gọi, đoạn code tìm lại method theo tên, thực hiện đường Reflection với `Object`/boxing và có thể gặp lỗi cấu hình ngay giữa lúc xử lý request. Nếu hệ thống còn phải đọc annotations, tìm converter hoặc chọn overload, công việc lặp lại nhiều hơn. Lỗi do target ném qua `Method.invoke` được bọc trong `InvocationTargetException`, cũng cần xử lý riêng.

**Đừng tự kết luận `getDeclaredMethod` “luôn rất chậm”.** JVM có cache/JIT; Reflection trên Java 18+ còn được triển khai lại trên MethodHandle theo JEP 416. Điều có thể khẳng định chắc chắn về thiết kế là **hệ thống đang yêu cầu làm lại bước khám phá trên mỗi call**, dù member/metadata vẫn như cũ.

### 2.1. Ba mức cải thiện

1. **Ít thay đổi nhất:** tìm `Method` một lần, giữ trong plan và tiếp tục dùng `Method.invoke`. Đã loại bỏ lặp discovery.
2. **Kiểu mạnh hơn:** từ `Method` đã kiểm tra, gọi `Lookup.unreflect(method)` hoặc `findVirtual` một lần; lưu `MethodHandle` rồi dùng `invokeExact` ở đường gọi typed.
3. **Cần pipeline:** tiền xây converter, validator, selector và các method-handle adapters cùng một plan, dùng lại nguyên chuỗi cho nhiều request.

Mức 3 chỉ nên làm nếu độ phức tạp và workload đủ biện minh. Một lời gọi Java trực tiếp với kiểu tĩnh có sẵn đôi khi tốt hơn việc dựng bộ dispatcher động.

## 3. Kết quả của chuẩn bị: một execution plan có hợp đồng rõ ràng

Một plan được công bố nên đáp ứng:

- **Đã chọn đúng mục tiêu**: tên method, chữ ký, overload, receiver, static/instance và declaring class rõ.
- **Quyền truy cập đã được cấp hợp lệ**: không phụ thuộc `setAccessible(true)` tùy tiện; dùng `Lookup` đúng caller/module.
- **Đã so khớp `MethodType`**: danh sách parameter types và return type đúng; với method instance, receiver là tham số đầu.
- **Adapter đã cố định**: nếu cần `asType`, `bindTo`, `insertArguments` hoặc `permuteArguments` thì chuẩn bị trước khi publish.
- **Immutable về cấu trúc**: plan giữ target, revision, converter và metadata cùng một version; không sửa các field đó từng phần.
- **Còn được kiểm tra dữ liệu runtime**: một plan đúng type vẫn phải từ chối input xấu và authorization sai.
- **Có lifecycle**: gắn với schema/classloader/generation, có chính sách invalidate khi code hoặc policy thay đổi.

Đặc biệt, **một `MethodHandle` không chứa mọi giá trị đầu vào**. Nó chứa liên kết tới phép tính; runtime vẫn phải cung cấp receiver và những đối số của request. Nếu bind một receiver vào handle, plan sẽ gắn với **một instance cụ thể**, điều này có thể sai khi request cần một receiver khác.

### 3.1. Lỗi nên lộ sớm

Giả sử bộ định tuyến cấu hình `route="total"` và yêu cầu type `(Checkout,int,int)int` nhưng implementation đã đổi sang `total(String)`. Đó là **lỗi cấu hình/schema** nên fail lúc khởi tạo plan. Nếu builder lẳng lặng bỏ qua lỗi rồi chờ request thật đầu tiên gọi sai, lỗi về thiết kế sẽ lẫn với lỗi dữ liệu người dùng.

Nếu cho phép prepare **lazy**, cần cache kết quả thành công và quản lý chính sách lỗi/retry. Không nên để mỗi request tự thử lại một discovery lỗi mà không có giới hạn hoặc chẩn đoán.

## 4. Ví dụ Java 17+ đầy đủ: annotation scan một lần, nhiều lần invokeExact

Chương trình này dùng Reflection **cho khám phá**, xác minh member rồi tạo `MethodHandle`. `Plan.execute` không quét annotations và không tìm tên method. Bộ đếm `SCANS` minh họa sự tách biệt; nó **không phải benchmark thời gian**.

Tạo file **`PreparedDispatchDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class PreparedDispatchDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Route { String value(); }

    public static final class Checkout {
        @Route("total")
        public int total(int units, int unitPrice) { return units * unitPrice; }
        @Route("info")
        public String info(String item) { return "item=" + item; }
    }

    private static final AtomicInteger SCANS = new AtomicInteger();
    private static final MethodType EXPECTED = MethodType.methodType(
            int.class, Checkout.class, int.class, int.class);

    record Plan(String route, MethodHandle handle) {
        Plan {
            if (!handle.type().equals(EXPECTED))
                throw new IllegalArgumentException("wrong handle type");
        }
        int execute(Checkout service, int units, int unitPrice) throws Throwable {
            if (service == null || units < 0 || unitPrice < 0)
                throw new IllegalArgumentException("invalid request");
            return (int) handle.invokeExact(service, units, unitPrice);
        }
    }

    static Plan prepare(String route) throws IllegalAccessException {
        SCANS.incrementAndGet();
        List<Method> methods = Arrays.stream(Checkout.class.getDeclaredMethods())
                .filter(m -> {
                    Route annotation = m.getAnnotation(Route.class);
                    return annotation != null && annotation.value().equals(route);
                }).toList();
        if (methods.size() != 1)
            throw new IllegalArgumentException("route must be unique");
        Method method = methods.get(0);
        if (!Modifier.isPublic(method.getModifiers())
                || Modifier.isStatic(method.getModifiers())
                || method.getReturnType() != int.class
                || !Arrays.equals(method.getParameterTypes(),
                        new Class<?>[] { int.class, int.class }))
            throw new IllegalArgumentException("unsupported signature");
        MethodHandle handle = MethodHandles.lookup().unreflect(method);
        return new Plan(route, handle);
    }

    public static void main(String[] args) throws Throwable {
        Checkout service = new Checkout();
        Plan plan = prepare("total");
        System.out.println("planType=" + plan.handle().type());
        System.out.println("call1=" + plan.execute(service, 2, 5));
        System.out.println("call2=" + plan.execute(service, 3, 7));
        System.out.println("scans=" + SCANS.get());
        try {
            prepare("info");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getClass().getSimpleName());
        }
        System.out.println("scansAfterRejected=" + SCANS.get());
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac --release 17 PreparedDispatchDemo.java
java PreparedDispatchDemo
```

Kết quả `stdout` đã được kiểm tra:

```text
planType=(Checkout,int,int)int
call1=10
call2=21
scans=1
rejected=IllegalArgumentException
scansAfterRejected=2
```

### 4.1. Những bước chỉ thuộc prepare

`prepare("total")`:

1. Gọi `Checkout.class.getDeclaredMethods()`.
2. Đọc `@Route` và chọn **đúng một** method tương ứng; không dựa vào thứ tự mảng Reflection.
3. Kiểm tra method public, không static, trả `int` và nhận hai `int`; route khác chữ ký sẽ bị từ chối.
4. Gọi `MethodHandles.lookup().unreflect(method)` để tạo capability có quyền hợp lệ.
5. Dùng record `Plan` xác nhận handle.type() là `(Checkout,int,int)int`.

`Checkout.total` là instance method, do đó receiver `Checkout` là **tham số đầu** của handle. Nếu method là static, handle sẽ **không** có receiver. Khi hỗ trợ overload, cần key rõ ràng gồm name, parameter types, return type và policy; `getDeclaredMethods()` không hứa hẹn thứ tự và có thể chứa synthetic/bridge methods.

### 4.2. Những bước vẫn thuộc execute

`execute` kiểm tra service không null, số lượng và đơn giá không âm rồi gọi:

```java
return (int) handle.invokeExact(service, units, unitPrice);
```

Kết quả trả về là primitive `int`; không scan annotations, không tạo `MethodType` hoặc tìm overload lại. Hai lần gọi `execute` làm `SCANS` vẫn bằng **1**. Sau đó chương trình thử `prepare("info")` thêm một lần, scan và từ chối signature `(String)String`, nên `scansAfterRejected=2` — **không phải** hai lần execute đã scan.

Ví dụ đơn giản hóa bộ định tuyến: chỉ hỗ trợ một contract duy nhất. Production router đa dạng type có thể trả plan theo từng route/signature. Điểm chính là **mỗi plan chỉ gắn với contract đã được xác minh**, không phải mọi route có cùng kiểu.

### 4.3. Vì sao có `handle.type()`?

`MethodType` biểu diễn chữ ký JVM của handle. Kiểu `(Checkout,int,int)int` khác `(Object,int,int)Object` dù Java có thể cast/box ở biên. Nếu caller viết:

```java
Object result = handle.invokeExact(service, units, unitPrice);
```

thì call site kỳ vọng return type `Object`, **không khớp `int`**, dẫn tới `WrongMethodTypeException`. Đây là đoạn minh họa phụ thuộc các biến `handle`, `service`, `units` và `unitPrice` đã có; không phải một chương trình độc lập.

Nếu cần adapter nhận `Object`, bạn có thể tạo `handle.asType(...)` đúng cách **một lần khi chuẩn bị**. Nhưng boxing, cast và kiểm tra runtime vẫn có thể xảy ra; việc tạo adapter không làm mọi conversion miễn phí.

## 5. Giảm các phép thích nghi lặp lại

`MethodHandle` có các combinators/adapter. Khi sơ đồ mapping cố định, nên chuẩn bị ở cùng nơi với lookup.

| Nhu cầu | API | Thực hiện trước hot path |
| --- | --- | --- |
| Chọn method | `findVirtual` / `findStatic` / `unreflect` | Tìm mục tiêu và kiểm tra quyền |
| Chọn field | `findGetter`, `unreflectGetter`, `VarHandle` | Chọn field, loại static/final, mode |
| Khớp type của API đích | `asType`, `explicitCastArguments` | Thiết kế conversion theo hợp đồng |
| Đổi vị trí hoặc lặp đối số | `permuteArguments` | Xây bảng index ánh xạ một lần |
| Gắn đối số/cấu hình cố định | `bindTo`, `insertArguments` | Không cung cấp cùng giá trị mọi request |
| Filter đầu vào | `filterArguments` | Gắn converter/normalizer |
| Filter kết quả | `filterReturnValue` | Gắn result mapper |
| Bắt chước gọi theo Object[] | `asSpreader`, `invokeWithArguments` | Chỉ dùng khi thực sự cần giao diện động |

Ví dụ `handle` typed như ở `PreparedDispatchDemo`, nếu runtime API chỉ giao các giá trị `Object`, một adapter chuẩn bị trước có thể là:

```java
MethodHandle generic = handle.asType(
        MethodType.methodType(Object.class,
                Object.class, Object.class, Object.class));
```

Đoạn này minh họa API, cần `handle` đã chuẩn bị. `generic` có kiểu `(Object,Object,Object)Object`; khi chạy nó cast receiver và unbox hai số nguyên rồi box kết quả. Đây không phải bằng chứng nó nhanh hơn bản typed; nếu dữ liệu nguồn đã là primitive, giữ `invokeExact` typed có thể tránh những chuyển đổi đó.

**Không tạo lại adapter mỗi request chỉ vì cần cùng `MethodType`**, nhưng cũng không áp dụng một adapter quá rộng cho những type mismatch không hợp lệ. Hãy chuẩn bị và kiểm tra các kiểu chuyển đổi trước khi publish.

## 6. Caching phải dựa trên identity và phiên bản đúng

Từ “cache MethodHandle” thường che đi câu hỏi quan trọng hơn: **đơn vị nào có thể dùng chung đúng một plan?**

| Đơn vị reuse | Key thường cần | Rủi ro nếu thiếu |
| --- | --- | --- |
| Route trong một module | `moduleRevision + routeId + signature` | Route cũ được dùng sau reload |
| Runtime type | `Class<?> + method descriptor` | Hai class loaders có cùng binary name bị trộn |
| Schema/serializer | `Class<?> + schemaVersion + converterPolicy` | Field mapping sai thế hệ |
| Tenant/policy | `tenantPolicyVersion + operation` | Trộn quyền hoặc converter của tenant |
| Plugin generation | `generationId + Class<?> + MethodType` | Cache giữ MethodHandle/loader cũ |
| Metadata bất biến theo class | `ClassValue<Descriptor>` | Không thấy được thay đổi ngoài class |

Class identity trong JVM **không chỉ là tên chuỗi**. Hai phiên bản `pkg.Service` được định nghĩa bởi hai defining class loaders khác nhau là **hai `Class<?>` khác nhau**. Một `MethodHandle` từ v1 không thể tùy ý thay bằng một handle v2 chỉ vì tên class giống nhau. Cache static vô hạn cũng có thể giữ method handle, class và classloader cũ sống lâu ngoài dự kiến.

### 6.1. `ClassValue` và compute race

Khi metadata chỉ phụ thuộc `Class<?>`, `ClassValue<T>` được thiết kế cho việc gắn giá trị tính toán với class:

```java
static final ClassValue<List<String>> METHODS = new ClassValue<>() {
    @Override protected List<String> computeValue(Class<?> type) {
        return Arrays.stream(type.getDeclaredMethods())
                .map(Method::getName).sorted().toList();
    }
};
// Lúc cần: List<String> names = METHODS.get(actualClass);
```

Đây là **đoạn minh họa**, cần import `List`, `Arrays` và `Method`; không phải file Java độc lập. Cache association theo class, không theo tên text.

Điểm kỹ thuật quan trọng trong tài liệu Java 17: nếu nhiều thread cùng `get(type)` lần đầu, **`computeValue` có thể được gọi nhiều lần cạnh tranh**. Một giá trị được cài atomically cho association; những giá trị tính thừa không nhất thiết được dùng. `remove` cũng có thể dẫn tới compute lại. Vì vậy mapping function nên **pure/idempotent**, không trực tiếp gửi email, thanh toán hay đăng ký resource chỉ được phép làm đúng một lần.

`ClassValue` giúp gắn cache theo class identity, nhưng **không tự xoá** mọi tham chiếu ngoài cache như static maps, threads hoặc loader references. Quản lý toàn bộ lifecycle của plugin vẫn cần thiết.

### 6.2. `ConcurrentHashMap.computeIfAbsent`

Với cache theo key phức hợp:

```java
record Key(Class<?> owner, String route, MethodType type, long revision) {}

ConcurrentHashMap<Key, ExecutionPlan> cache = new ConcurrentHashMap<>();
// Khung minh họa: cache.computeIfAbsent(key, k -> buildValidatedPlan(k));
```

Đoạn này minh họa cấu trúc và yêu cầu một lớp `ExecutionPlan`, `buildValidatedPlan` đã được định nghĩa; không phải chương trình độc lập. Trong code thực, value nên bất biến và chỉ được publish sau khi build thành công.

`computeIfAbsent` giúp phối hợp cài kết quả cho cùng key, nhưng mapping function không được tự sửa đệ quy map, nên ngắn gọn, và khi ném exception thì association không được cài, các request về sau có thể thử lại. Nếu build rất đắt hoặc cần timeout/cancellation, cân nhắc coordinator theo key với `CompletableFuture<Plan>` và error/retry policy.

**Không đánh đồng “mapping được cài một lần” với “tác dụng phụ bên ngoài được thực hiện exactly-once”** khi có exception, crash/restart hoặc nhiều process.

### 6.3. Invalidation và negative cache

- Khi schema đổi, plan cũ **không tự được tái xác minh**. Dùng revision trong key hoặc công bố generation mới.
- Khi một route không tồn tại, có thể **negative-cache lỗi cấu hình** có TTL/revision nếu hợp đồng cho phép; không cache thất bại vĩnh viễn khi plugin có thể được cập nhật.
- Khi module được unload, thả references tới `Class<?>`/`MethodHandle`/converter và ngừng in-flight tasks đúng cách.
- Nếu authorization phụ thuộc user hiện hành, **không** cache kết quả “user A được phép” như metadata tĩnh chỉ theo method.
- Giới hạn dung lượng cache; một metadata key quá nhiều trường và hàng triệu class loaders có thể biến tối ưu CPU thành rủi ro heap/metaspace.

## 7. Công bố một plan snapshot, không thay rời từng field

Tách chuẩn bị khỏi execute đặc biệt quan trọng khi hệ thống **reload cấu hình hoặc code** trong lúc có nhiều request.

Anti-pattern:

```java
// Hai volatile fields được update riêng: không tạo một transaction.
volatile MethodHandle activeHandle;
volatile String activeRevision;

// Writer
activeHandle = newHandle;
activeRevision = "v2";

// Reader
MethodHandle h = activeHandle;
String rev = activeRevision; // Có thể nhận hai version khác nhau.
```

Đoạn trên chỉ là minh họa, không phải file Java độc lập. Reader có thể quan sát `activeHandle` của v2 và `activeRevision` của v1 theo interleaving. Nếu plan còn nhiều converter/schema fields, nguy cơ “nửa v1, nửa v2” càng nghiêm trọng.

Giải pháp: **gói tất cả metadata và handle đã validated trong một object bất biến**, rồi công bố **một reference** qua `AtomicReference` hoặc volatile field. Reader lấy **một snapshot duy nhất** cho cả lời gọi.

## 8. Ví dụ Java 17+ đầy đủ: chuyển v1→v2 bằng AtomicReference

Tạo file **`VersionedPlanDemo.java`**:

```java
import java.lang.invoke.*;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

public class VersionedPlanDemo {
    public static String oldLogic(String text) {
        return "v1:" + text.toUpperCase(Locale.ROOT);
    }
    public static String newLogic(String text) {
        return "v2:" + text.toLowerCase(Locale.ROOT);
    }
    record Plan(String revision, MethodHandle handle) {
        Plan {
            MethodType expected = MethodType.methodType(String.class, String.class);
            if (!handle.type().equals(expected))
                throw new IllegalArgumentException("wrong type");
        }
        String run(String text) throws Throwable {
            if (text == null) throw new IllegalArgumentException("null text");
            return (String) handle.invokeExact(text);
        }
    }
    static Plan prepare(String revision) throws ReflectiveOperationException {
        String member = switch (revision) {
            case "v1" -> "oldLogic";
            case "v2" -> "newLogic";
            default -> throw new IllegalArgumentException("unknown revision");
        };
        MethodHandle target = MethodHandles.lookup().findStatic(
                VersionedPlanDemo.class, member,
                MethodType.methodType(String.class, String.class));
        return new Plan(revision, target);
    }
    static final class Router {
        private final AtomicReference<Plan> current;
        Router(Plan initial) { current = new AtomicReference<>(initial); }
        String call(String input) throws Throwable {
            Plan snapshot = current.get();
            return snapshot.run(input);
        }
        Plan snapshot() { return current.get(); }
        void publish(Plan ready) { current.set(ready); }
    }
    public static void main(String[] args) throws Throwable {
        Router router = new Router(prepare("v1"));
        Plan previous = router.snapshot();
        System.out.println("before=" + router.call("MiXeD"));
        router.publish(prepare("v2"));
        System.out.println("after=" + router.call("MiXeD"));
        System.out.println("oldSnapshot=" + previous.run("MiXeD"));
        System.out.println("currentRevision=" + router.snapshot().revision());
        System.out.println("type=" + router.snapshot().handle().type());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 VersionedPlanDemo.java
java VersionedPlanDemo
```

Kết quả `stdout` chính xác:

```text
before=v1:MIXED
after=v2:mixed
oldSnapshot=v1:MIXED
currentRevision=v2
type=(String)String
```

**Diễn giải:**

1. `prepare("v1")` chọn method trong một tập tên **whitelist** (không lấy tên tùy ý từ user), tạo handle `(String)String` và kiểm tra kiểu trước khi công bố.
2. Mỗi `Router.call` chỉ đọc `current.get()` **một lần**, dùng plan snapshot; không phải tra method lại mỗi request.
3. Writer xây và xác minh **v2 trước** khi `publish`. Nếu prepare fail, v1 vẫn đang được dùng.
4. `AtomicReference.set` công bố reference cùng các fields đã khởi tạo. Reader dùng một revision+handle nhất quán, không đọc chúng từ hai volatile fields rời.
5. `previous.run` vẫn nhận xử lý theo v1 dù v2 đã active; điều này cho phép request bắt đầu trước reload hoàn thành, với điều kiện lifecycle cho phép.
6. Chương trình một thread này minh họa cấu trúc an toàn; một hệ thống có **nhiều writers** còn cần CAS, kiểm tra revision monotonically increasing hoặc coordinator để không publish v1 sau v2.

**Không mặc định object bất biến là không thể giữ state mutable.** `MethodHandle` bản thân immutable, nhưng method đích có thể đọc static state, receiver mutable hoặc resource bên ngoài. Plan bảo đảm metadata/handle không bị trộn, **không** thay thế đồng bộ cho dữ liệu nghiệp vụ bên dưới.

### 8.1. Quy trình reload nên rõ ràng

```text
v1 ACTIVE
   |
   +-- chuẩn bị v2 ngoài hot path
   |      discover -> validate -> build adapters -> immutable plan
   |
   +-- atomic publish v2
   |      new requests use v2
   |      in-flight v1 requests may finish using old snapshot
   |
   +-- retire v1 after usage drains
          release handles, loaders, listeners and resources
```

Khi authorization bị thu hồi, chính sách có thể yêu cầu **ngăn cả in-flight v1**, tùy mức độ bảo mật. Snapshot để tối ưu method lookup không phải lý do trì hoãn kiểm tra quyền nghiệp vụ.

## 9. MethodHandle và quyền truy cập: capability phải được giữ kín

`Lookup` kiểm tra khả năng truy cập khi tạo `MethodHandle`. Sau đó code giữ handle có thể gọi underlying member theo capability đã được cấp mà không cần sở hữu Lookup ban đầu. Đây là một tính chất mạnh và hữu ích để tách prepare khỏi execute, nhưng cũng là rủi ro nếu cache không có access policy.

- Builder tin cậy có thể dùng Lookup có quyền để tìm private members theo quy định module.
- Chỉ công bố handle/plan cho những caller được phép sử dụng operation đó.
- **Không** đưa full-privilege Lookup hoặc private handles vào registry public mà plugin không đáng tin có thể đọc.
- Dữ liệu runtime vẫn cần authorization; `hasFullPrivilegeAccess()` hoặc một member access check không chứng minh user cuối có quyền nghiệp vụ.
- Nếu quyền thay đổi, invalidation/guard ở điểm invoke phải bảo vệ phù hợp. Plan không được biến thành “vé vĩnh viễn” vượt cơ chế thu hồi.
- Một handle từ class loader của v1 không được gán vào plan v2 chỉ vì tên class và method trông giống nhau.

Với `Method.invoke`, lời gọi method đích ném exception sẽ được bọc `InvocationTargetException`; với `MethodHandle.invokeExact`, exception từ target truyền ra trực tiếp. Điều này cũng nên được quyết định ở boundary execute thay vì mỗi request đoán exception nào là “lookup failed”.

## 10. Áp dụng cho VarHandle, Reflection serializer và runtime compilation

### 10.1. VarHandle và field mapping

Một mapper/serializer có thể khám phá `Field` hoặc `RecordComponent` và converter một lần rồi tạo descriptor bất biến:

```text
Class<?> / schemaVersion
    |
    +-- inspect fields, types, annotations
    +-- validate ordering / accessibility / converters
    +-- create MethodHandle getters and/or VarHandles
    +-- descriptor = immutable array/list of accessors
                          |
                       request object
                          |
                validate values, read/write
                          |
                       output
```

Nếu một object có 30 fields và được serialize một triệu lần, không nên mặc định gọi `getDeclaredFields` một triệu lần. Nhưng **cache VarHandle không làm mọi truy cập tự đồng bộ**: `get`, `getAcquire`, `getVolatile` và các atomic access modes có ngữ nghĩa khác nhau. Chọn mode theo Java Memory Model, không theo mong muốn “nhanh nhất”.

Với field `final`, setter có thể bị từ chối; nếu dữ liệu bất biến, khởi tạo qua constructor/factory thay vì cố sửa field. Với generic types, metadata `Class<?>` (raw/erased) không đủ thay thế `Type` và annotations; phải xác minh converter theo schema.

### 10.2. invokedynamic và CallSite

`invokedynamic` đã thể hiện ý tưởng hai giai đoạn: bootstrap tạo `CallSite` lúc liên kết, các lần gọi về sau đi qua CallSite target. Tách discovery/bootstrap khỏi repeated execution có thể giảm chi phí dispatch. Nhưng:

- Bootstrap có thể được JVM chạy **cạnh tranh** trong quá trình liên kết; không đặt side effect once-only trong bootstrap mà không có giao thức idempotent.
- `MutableCallSite` có thể đổi target sau khi liên kết; việc chuyển target cần chính sách visibility/synchronization phù hợp (ví dụ `MutableCallSite.syncAll`).
- Nếu dùng `VolatileCallSite`, sự quan sát target có volatile semantics, nhưng việc đổi classloader/plan liên quan phải được quản lý đồng bộ.
- Một CallSite không tự kiểm tra authorization của user ở mỗi lần target được invoke; runtime boundary vẫn cần logic đó.

### 10.3. Biên dịch động và generated class loaders

Khi hệ thống tự tạo bytecode bằng `JavaCompiler` hoặc định nghĩa hidden classes, việc chuẩn bị có thể tốn rất nhiều: parse source, compile, verify, load, link, tìm method. Những bước ấy càng nên **tách khỏi request execution**, chuẩn bị artifact và plan theo generation. Một failure trước publish không được làm hỏng generation đang hoạt động.

Lưu ý: class identity phụ thuộc defining loader; hot reload nên dùng **bundle + loader generation** mới. Không nên cố định nghĩa lại cùng binary name trong loader đã dùng hoặc đổi tệp `.class` và kỳ vọng JVM tự cập nhật. Giữ API chung ở parent loader nếu cần truyền object giữa các generation.

## 11. Khi nào cache không đáng giá?

Tách giai đoạn không có nghĩa tạo mọi cache có thể nghĩ ra:

- Method chỉ dùng **một lần** và code hiện hành đủ đơn giản.
- Lookup đã được JVM/JDK tối ưu, chi phí chỉ chiếm phần rất nhỏ tổng request.
- Tập class/schema quá lớn nhưng phần lớn không bao giờ được gọi, làm preload tốn startup và memory.
- Key hoặc policy thay đổi gần như mỗi request, cache hit rất thấp.
- Cache kéo dài tuổi thọ class loaders, `MethodHandle`, resources hoặc thread; chi phí memory/GC vượt thời gian tiết kiệm.
- Adapter `Object...` tạo boxing/spread đáng kể so với lời gọi type-safe trực tiếp.
- Việc dùng generic dispatcher khiến code khó debug hơn một lời gọi Java có type tĩnh.

Khi có thể, **lời gọi Java trực tiếp** vẫn là điểm tham chiếu đơn giản để xem có cần cơ chế dynamic invocation không.

## 12. Mô hình chi phí và cách đo đúng

Ký hiệu:

- `D`: discovery + validation + prepare một plan.
- `L`: chi phí discovery/validation lặp mỗi request nếu chưa tách.
- `E`: chi phí execute qua plan đã có.
- `R`: chi phí invoke khi mỗi lần vừa lookup vừa gọi.
- `N`: số lần gọi trong vòng đời plan.

Mô hình bậc một:

```text
Không có plan:   T_naive(N) ~ N * (L + R)
Có plan:         T_ready(N) ~ D + N * E

Lợi ích giả định ~ N * (L + R - E) - D
```

Nếu `N` lớn, `L` đáng kể và `E` hợp lý, amortization có thể có lợi. Nếu `N` nhỏ hoặc setup/cache miss thường xuyên, không chắc. Thực tế cần thêm chi phí cache lookup, allocation, lock, JIT warmup, GC, class loader retention và tail latency.

**Đừng tự đưa ra con số “nhanh hơn 10 lần” khi chưa benchmark.** Cả Reflection lẫn MethodHandle có nhiều tối ưu hóa tùy phiên bản JDK. JEP 416 thay phần triển khai Core Reflection từ JDK 18, nên kết quả trên JDK 17 không tự chuyển được sang JDK 21/26.

### 12.1. Ba phép đo khác nhau

1. **Cold path**: thời gian tạo plan, scan annotations, kiểm tra signature, load class, tạo adapter và tăng memory.
2. **Steady-state invoke-only**: đã có plan/Method cached, đưa input khác nhau, tiêu thụ output, đo allocation/throughput/latency. Đây là phép đo riêng phần gọi.
3. **End-to-end request**: route selection, cache access, validation current data, invoke, output. Đo p50/p95/p99 và GC trong workload tương đương production.

JMH là công cụ phù hợp cho microbenchmarks JVM nhờ warmup, forks và xử lý kết quả. Với tải production, cần thêm profiling/tracing và benchmark toàn hệ thống.

| Lỗi benchmark | Vì sao dễ gây sai |
| --- | --- |
| Nhét `getDeclaredMethod` mỗi lần trong case Reflection nhưng không có setup tương đương | Đo discovery+invoke, không phải chỉ invoke; hợp lệ nếu được ghi nhãn đúng |
| Đo lúc chưa warmup, không có fork | Kết quả chịu ảnh hưởng compilation/JIT và state trước test |
| Dùng input hằng, không tiêu thụ output | JVM có thể constant-fold, loại bỏ phép tính |
| In log/console trong hot loop | I/O che chênh lệch dispatch |
| So `invokeWithArguments` với direct typed call mà bỏ qua boxing | Đang đo hai hợp đồng gọi khác nhau |
| Đo một JDK rồi áp dụng cho tất cả releases | Reflection internals và JIT thay đổi |
| Không đo memory/cache hit/class loaders | Tối ưu CPU có thể gây memory leak hoặc cold-start regression |

**Đừng gán nhãn “performance improvement” cho việc chỉ thay API.** Nên định nghĩa trước metric thành công: giảm CPU cho dispatch ở p95, giảm allocations hay giảm cold startup? Nếu sau benchmark bottleneck thật nằm ở network/database, tối ưu lookup không giúp đáng kể.

## 13. Common failures: phát hiện sai ở giai đoạn đúng

| Hiện tượng | Nguyên nhân | Nơi xử lý |
| --- | --- | --- |
| `NoSuchMethodException` khi request đầu vào | Chưa khám phá/validate sớm | Builder/prepare |
| Chọn nhầm overload/synthetic bridge | Chọn theo thứ tự `getDeclaredMethods` hoặc chỉ theo name | Discovery/validation |
| `IllegalAccessException` khi unreflect | Lookup thiếu quyền hoặc module không mở phù hợp | Prepare; sửa thiết kế quyền |
| `WrongMethodTypeException` khi gọi | Chữ ký `invokeExact` tại call site không trùng handle type | Prepare check + compile-time callsite QA |
| `ClassCastException` ở adapter | Dữ liệu/runtime type không chuyển được | Per-request input validation và converter policy |
| Null/giá trị âm vẫn qua plan | Chuyển cả input validation sang startup | Execute |
| Lỗi phương thức đích bị nhầm lỗi lookup | Không tách exception chuẩn bị và exception runtime | Error boundary |
| Class khác loader nhưng cùng tên | Cache theo binary name String thiếu identity | Cache key/generation |
| Nhiều requests xây plan cùng key | Cache không đồng bộ hoặc side effect trong builder | Concurrent cache/initialization |
| Invalid config nhưng vẫn publish plan nửa xây | Thay fields rời hoặc xử lý exception sai | Build-before-publish atomic snapshot |
| User bị thu hồi quyền nhưng handle vẫn gọi được | Cache capability không kèm authorization phù hợp | Runtime permission/guard |
| Cache giữ loader cũ mãi | Static map/MethodHandle/threads giữ reference | Retirement/lifecycle |
| “Đã tối ưu” nhưng throughput thấp hơn | Adapter boxing, cache contention, startup, JIT | JMH + profile workload thật |

**Không catch `Throwable` rồi im lặng trả “missing route”.** Lỗi cấu hình, lỗi quyền, lỗi callsite type và exception do target ném có ý nghĩa khác nhau, nên đưa vào cơ chế báo lỗi riêng. Trong ví dụ, `main throws Throwable` chỉ để code dễ đọc.

## 14. Checklist review trước khi đưa vào production

1. **Ổn định:** thành phần nào phụ thuộc class/schema/revision, thành phần nào phụ thuộc request?
2. **Khám phá:** quét method/field/annotation mấy lần cho mỗi version? Có lọt vào hot path không?
3. **Chọn member:** key gồm class, tên, param types, return type, static/instance và class loader chưa?
4. **Type:** `handle.type()` đã được kiểm tra trước publish? Có đúng receiver và primitive return?
5. **Chuyển kiểu:** converter/adapter cần thiết đã được xây khi chuẩn bị, không phân tán ở nhiều request?
6. **Quyền:** Lookup có quyền hợp lệ? Private MethodHandle có bị rò sang plugin hay tenant khác?
7. **Input:** validation nào vẫn bắt buộc thực hiện mỗi request? Có thu hồi quyền/quota động?
8. **Cache:** ClassValue/CHM được dùng đúng concurrency semantics? Builder có side effect lặp được không?
9. **Identity:** hai class cùng binary name nhưng khác loader có bị gộp vào một cache entry?
10. **Publish:** plan chứa target+metadata/version thành **một immutable snapshot**? Reader lấy một snapshot duy nhất?
11. **Reload:** build v2 thất bại có để v1 hoạt động? Có policy xử lý nhiều writers cập nhật cùng lúc?
12. **Cleanup:** ai retire old plan, release loader, handles, resources, in-flight requests?
13. **Observability:** có phân biệt số lần prepare, hit/miss, execute count và latency của từng giai đoạn?
14. **Đo lường:** có microbenchmark steady-state lẫn end-to-end và cold startup trên JDK đích?
15. **Đơn giản:** có thể thay toàn bộ bằng lời gọi trực tiếp hoặc cached Method đơn giản hơn không?

Một câu mô tả thiết kế tốt: **“Mỗi route được khám phá, kiểm tra và gắn handle khi build plan theo revision; mỗi request chỉ lấy snapshot, kiểm tra dữ liệu/quyền hiện hành rồi thực thi.”**

## 15. Bài tập tự kiểm tra

**Bài 1.** Một JSON serializer có 20 fields, đang đọc field annotations trên mọi object và kiểm tra `age >= 0`. Những thao tác nào chuyển sang prepare?

**Đáp án:** Khám phá fields/annotations, chọn converter, quyền field, mapping tên JSON và schema type có thể cache theo class/schema. Kiểm tra **giá trị `age`** vẫn chạy với từng object.

**Bài 2.** Method instance `int charge(int amount)` của `Account` được chuyển bằng `Lookup.unreflect`. Kiểu MethodHandle thông thường là gì?

**Đáp án:** `(Account,int)int`. Receiver xuất hiện đầu tiên; hãy validate handle.type khi prepare.

**Bài 3.** Hai calls `Plan.execute` trong `PreparedDispatchDemo` làm `SCANS` tăng mấy lần?

**Đáp án:** Không tăng lần nào. `SCANS` tăng khi gọi `prepare`, một lần cho `total` và lần nữa cho `info` bị từ chối.

**Bài 4.** Hai thread gọi `ClassValue.get(C.class)` đồng thời, mapping function viết một file ngoài JVM. Có chắc chỉ viết một lần?

**Đáp án:** Không. `computeValue` có thể chạy cạnh tranh; chỉ giá trị cache được cài được chọn. Tránh side effect không idempotent trong compute.

**Bài 5.** Hai plugin có class cùng tên `pkg.Widget` nhưng được nạp bởi hai class loaders khác nhau. Dùng `Map<String,MethodHandle>` theo tên có an toàn không?

**Đáp án:** Không đủ; có thể trả handle của generation sai. Key theo `Class<?>`/loader identity, signature và revision; quản lý cleanup.

**Bài 6.** Writer cập nhật `activeHandle` rồi `activeRevision` qua hai volatile fields. Reader có chắc nhận cả hai cùng version?

**Đáp án:** Không. Dùng một immutable plan chứa handle/revision và publish bằng một volatile/atomic reference.

**Bài 7.** Plan đã kiểm tra rằng method là public nhưng token của user bị thu hồi. Có thể bỏ token validation vì plan vẫn hợp lệ không?

**Đáp án:** Không. Member access là tính hợp lệ cấu trúc; authorization runtime là điều kiện biến đổi theo request.

**Bài 8.** Gọi `MethodHandles.lookup().unreflect(m)` một lần, sau đó dùng `invokeExact` nhưng ép kết quả `Object` trong khi handle trả `int`. Kết quả?

**Đáp án:** `WrongMethodTypeException` do callsite return type không khớp `MethodType`, dù method lookup được thực hiện đúng.

**Bài 9.** Một route chỉ được gọi duy nhất một lần khi startup. Có cần `ClassValue` và chuỗi adapters phức tạp không?

**Đáp án:** Không nhất thiết. Tối ưu chỉ hợp lý khi có reuse và chi phí có thể chứng minh lớn hơn chi phí prepare/cache/lifecycle.

**Bài 10.** Benchmark gọi Reflection gồm discovery mỗi iteration, MethodHandle đã chuẩn bị trước. Có được kết luận riêng `Method.invoke` chậm hơn `invokeExact`?

**Đáp án:** Không. Benchmark đang đo **per-request discovery + invoke** so với prepared invoke. Muốn đo chi phí invocation riêng, cache Method ở case Reflection và công bố rõ setup/callsite type, warmup, input và result.

## 16. Tài liệu tham khảo chính thức

- [Oracle JDK 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType` và access checking khi hình thành handle.
- [Oracle JDK 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVirtual`, `findStatic`, `unreflect`, caller/member access.
- [Oracle JDK 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): combinators và adapter methods.
- [Oracle JDK 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html): per-Class caching, concurrent `computeValue` và `remove`.
- [Oracle JDK 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `computeIfAbsent`, atomic map update và restrictions.
- [Oracle JDK 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): publication và việc lấy một snapshot reference.
- [Oracle JDK 17 — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): phân biệt access modes và memory effects; cache metadata không tự đồng bộ.
- [OpenJDK JEP 416](https://openjdk.org/jeps/416): Core Reflection được triển khai lại trên MethodHandles từ Java 18.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): phương pháp viết JVM microbenchmarks có warmup/forks/measurement.

**Tóm lại:** tách **khám phá và validation cấu trúc** khỏi đường thực thi lặp lại giúp hệ thống rõ ràng, kiểm soát lỗi sớm và tránh xử lý metadata không cần thiết. Hãy chuẩn bị typed MethodHandle/VarHandle/converter theo **đúng class + version**, publish plan bất biến một cách an toàn và chỉ gọi plan ở hot path. **Không** hoist dữ liệu validation hoặc authorization động; không trộn plan giữa class loaders; và **đo thực tế** trước khi khẳng định lợi ích tốc độ.
