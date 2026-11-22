# Chi phí reflection, bộ nhớ đệm và quản lý class loader trong Java annotation

Trong Java, annotation có retention `RUNTIME` là metadata có thể được đọc qua reflection. Frameworks thường dựa vào annotation để xây route, validate object, map entity, phân quyền hoặc đăng ký handler. Vấn đề hiệu năng không nằm ở riêng ký hiệu `@Something` được viết trong source, mà thường nằm ở **việc quét và diễn giải annotation lặp lại**, số lượng phần tử phản chiếu, chiến lược cache và vòng đời của các lớp do nhiều class loader nạp.

Một thiết kế đúng cần giải quyết đồng thời ba câu hỏi:

1. **Reflection thực hiện việc gì và có đang nằm trên hot path không?**
2. **Có thể chuẩn hóa metadata thành cấu trúc bất biến rồi lưu theo class hoặc theo registry không?**
3. **Bộ nhớ đệm có giữ mạnh Class/Method/ClassLoader của plugin sau khi plugin đã đóng không?**

Bài học sử dụng Java 17+ để tạo một cache dựa trên `ClassValue`, quan sát việc quét một lần trong tình huống tuần tự, xóa và tính lại cache, rồi chứng minh hai lớp **trùng tên nhưng khác class loader** là hai kiểu khác nhau. Không suy diễn benchmark hoặc khả năng class unloading từ một bài test chức năng.

## 1. Nguồn chi phí của annotation reflection

Xét:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String value();
}

class Service {
    @Route("/check")
    public void check() {}
}
~~~

Một ứng dụng có thể lấy đường dẫn bằng:

~~~java
var method = Service.class.getDeclaredMethod("check");
var route = method.getDeclaredAnnotation(Route.class);
String path = route.value();
~~~

Đây là **đoạn mã minh họa đặt trong một method có xử lý NoSuchMethodException**; ví dụ đầy đủ có ở mục 7.

Các bước khác nhau có những chi phí khác nhau:

| Công việc | API thường dùng | Điều cần xem xét |
| --- | --- | --- |
| Resolve một phương thức | `Class.getMethod`, `getDeclaredMethod` | Tìm tên/chữ ký; kết quả phụ thuộc declared/inherited semantics |
| Quét mọi phương thức | `getMethods`, `getDeclaredMethods` | Số lượng thành viên, mảng kết quả, bridge/synthetic methods |
| Đọc một annotation | `getAnnotation`, `getDeclaredAnnotation` | Retention, vị trí, annotation present hoặc absent |
| Lấy nhiều annotations cùng loại | `getAnnotationsByType` | Repeatable container và các phần tử trả về |
| Đọc type annotations | `getAnnotatedType` và `AnnotatedType` | Duyệt type use, generic arguments, nested types |
| Diễn giải thành cấu hình | Parse route/validation/policy | Chi phí nghiệp vụ của framework, kiểm tra trùng/xung đột |
| Gọi reflective method | `Method.invoke` | Là hoạt động khác với **đọc annotation**, có access checks |

**Không đúng** nếu khẳng định mọi `getAnnotation` đều đọc lại file `.class` từ ổ đĩa; JVM/JDK có thể cache và tối ưu reflection internals. Nhưng ứng dụng vẫn có thể lãng phí CPU và allocation nếu cứ gọi `getDeclaredMethods()`, duyệt hàng trăm phương thức rồi xây lại cùng route table ở mỗi HTTP request.

Ngược lại, nếu framework chỉ quét metadata một lần khi bootstrap, một cache tầng thứ hai có thể gần như không mang lại lợi ích. Hãy đo nơi thật sự tiêu tốn CPU, allocations và GC.

### Không có chuyện annotation tự chạy mỗi lần gọi method

`@Route("/check")` là metadata. Nó **không tự thêm dispatch code** vào method `check()` hay khiến JVM gọi `getAnnotation` mỗi lần `check()` chạy. Chỉ framework hoặc ứng dụng **chủ động đọc và xử lý** annotation mới tạo ra công việc reflection.

Tương tự, compiler annotation processing và runtime reflection là hai thời điểm khác nhau. Annotation retention `SOURCE` có thể được processor dùng ở compile time nhưng không còn để runtime reflection đọc.

## 2. Chọn dữ liệu nào để cache

Với `Service.check()`, có ít nhất ba chiến lược.

**Cache Method:**

~~~java
Map<MethodKey, java.lang.reflect.Method> handlers;
~~~

Có thể tránh lookup lại method nhưng các `Method` vẫn mang quan hệ đến `Class` khai báo, parameter types và potentially class loader. Nếu cache static ở nơi sống lâu, việc giữ `Method` của plugin có thể kéo dài vòng đời class loader.

**Cache annotation object:**

~~~java
Map<MethodKey, Route> routes;
~~~

Có thể tránh đọc annotation lần nữa, nhưng đối tượng annotation và kiểu annotation của nó cũng thuộc runtime class-loading context. Hơn nữa, method/annotation proxy không phải lúc nào là metadata business nhẹ nhất.

**Cache metadata đã chuẩn hóa:**

~~~java
Map<MethodKey, String> routePaths;
~~~

Khi framework chỉ cần một URL path, một chuỗi bất biến là đủ. Cách này không bắt buộc giữ annotation proxy; còn nếu consumer cần gọi method, registry handler vẫn phải quản lý method/instance thích hợp.

Trong các đoạn trên, `MethodKey` là kiểu **minh họa do ứng dụng định nghĩa**, ví dụ một record giữ tên và kiểu tham số. Chúng chưa phải chương trình độc lập.

### Đừng dùng method name làm key khi có overload

`run()` và `run(String)` là hai methods khác nhau, có thể được gắn annotation khác nhau. Nếu key chỉ là `"run"`, một entry có thể ghi đè entry còn lại. Với framework thật, cần khóa theo signature đã resolve hoặc một định danh domain có nghĩa rõ ràng.

### Cache cả kết quả không có annotation

Nếu method `ping()` không được gắn `@Route`, bạn vẫn muốn tránh quét lại nó mỗi request. Một cách là map bất biến chỉ chứa các entries thật; `!routes.containsKey("ping")` cho biết method không có route trong scan hiện tại. Trong dữ liệu tổng quát có thể dùng `Optional` hoặc sentinel riêng.

`Map.copyOf(...)` **không chấp nhận khóa/giá trị null**. Đừng lưu `null` để biểu đạt negative result vào loại map này.

## 3. Vì sao cache tĩnh có thể giữ class loader

Ví dụ rủi ro:

~~~java
static final java.util.concurrent.ConcurrentHashMap<
        Class<?>, java.util.List<java.lang.reflect.Method>> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

Đây là **đoạn minh họa chống chỉ định cho cache global sống lâu trong hệ thống reload plugins**, không phải lệnh khởi tạo luôn luôn sai. `ConcurrentHashMap` giữ key/value bằng **strong references**. Nếu trong key có `Class<?>` của plugin và trong value có `Method` của plugin, tồn tại đường tham chiếu:

~~~text
Static cache thuộc class loader sống lâu
    |
    +--> strong key: Class<?> của plugin
    |       |
    |       +--> defining ClassLoader
    |
    +--> strong value: Method của plugin
            |
            +--> declaring Class và các kiểu liên quan
~~~

Khi plugin được redeploy, việc không còn business objects không đủ để đảm bảo loader cũ được unload nếu static cache vẫn giữ nó. Kết quả có thể là class loaders cũ tích tụ và metaspace tăng.

**Chú ý:** class unloading phụ thuộc reachability và GC; không phải cứ gọi `System.gc()` hoặc `URLClassLoader.close()` là JVM phải unload ngay. Điều cần điều tra là toàn bộ reference graph và lifetime của ứng dụng.

### WeakHashMap không tự sửa mọi vòng tham chiếu

Một cách sửa dễ nhầm:

~~~java
java.util.WeakHashMap<Class<?>, java.util.List<java.lang.reflect.Method>> cache;
~~~

`WeakHashMap` giữ **weak keys**, nhưng values vẫn được giữ mạnh. Nếu value chứa `Method` có đường liên hệ tới declaring class, ta có thể gặp:

~~~text
Map --> value (Method) --> declaring Class (cũng là key)
~~~

Vì key còn reachable mạnh qua value, chỉ đổi strong map key sang weak key **không đảm bảo** loader được giải phóng. `WeakHashMap` cũng không tự thread-safe; concurrency vẫn là vấn đề riêng. Không suy luận từ tên cấu trúc dữ liệu mà bỏ qua object reference graph.

Các reference roots khác ngoài cache như thread-local, callback, event listener, executor task, MBean hoặc static registry cũng có thể giữ plugin cũ.

## 4. ClassValue: liên kết metadata với từng Class

`java.lang.ClassValue<T>` (có từ Java 7) cho phép liên kết lazy computed metadata với `Class<?>` mà không cần global static map có strong Class keys.

~~~java
private static final ClassValue<Metadata> META = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return scan(type);
    }
};
~~~

Đây là **đoạn minh họa**, giả định `Metadata` và `scan(type)` đã được định nghĩa. Mục 7 dùng một chương trình chạy được với `ClassValue<Map<String,String>>`.

Cơ chế chính:

- `get(type)` trả metadata đã gắn cho class nếu có; nếu chưa có thì yêu cầu `computeValue(type)`.
- Việc gắn giá trị vào class là đồng bộ theo contract API, nhưng trong trường hợp nhiều threads cùng truy vấn lần đầu, **`computeValue` có thể chạy hơn một lần**. Không viết code dựa trên giả định side effect luôn xảy ra đúng một lần.
- `remove(type)` xóa liên kết để lần `get(type)` kế tiếp có thể tính lại.
- `ClassValue` thường phù hợp để cache metadata per-class trong môi trường có class loaders được unload, bởi không cần một map static mạnh của framework liệt kê mọi `Class<?>` từng gặp.
- Giá trị nên immutable hoặc có thread-safety contract rõ. `Map.copyOf(...)` giúp tạo map bất biến (nhưng không tự đóng băng mọi object lồng bên trong).

**Không cam kết `ClassValue` loại bỏ mọi loader leak**: nếu cache value bị copy sang static map khác, một thread-local giữ handler, hoặc plugin đăng ký callback không unregister, loader vẫn có thể bị giữ mạnh.

### Khi nào nên dùng ClassValue?

- Cần scan annotation theo `Class<?>` cho mapper/validator/route generator.
- Nhiều lần tái sử dụng metadata từ cùng một class.
- Ứng dụng có nhiều class loaders hoặc các class do plugins tạo, muốn hạn chế việc static cache pinning class keys.
- Metadata gắn chủ yếu với **định nghĩa class**, không thay đổi theo mỗi request.

Nếu annotation được xử lý **một lần ở bootstrap** rồi registry quản lý trong cùng lifecycle ứng dụng, có thể không cần thêm `ClassValue`. Thiết kế đơn giản hơn đôi khi tốt hơn.

## 5. Cache semantics và invalidation

### Khóa cache phải phù hợp với câu hỏi

Một `Class<?>` là khóa hợp lý cho metadata tĩnh riêng của một class. Nhưng nếu kết quả còn phụ thuộc vào tenant, locale, policy runtime, cấu hình môi trường hoặc phiên bản plugin, **class-only key có thể không đủ**.

Tách hai tầng là một giải pháp:

1. **Per-class structural metadata:** danh sách methods, annotations, element values và các signatures cố định — cache với `ClassValue` hoặc registry scoped.
2. **Runtime policy/config:** route enablement, user permissions, tenant-specific flags — cache theo version/tenant/config hoặc resolve trong request path theo một quy tắc riêng.

Đừng lưu kết quả security policy đã tính cho user A vào cache chỉ theo `Class<?>` rồi dùng lại cho user B.

### Khác nhau giữa declared, inherited và repeatable annotations

`getDeclaredAnnotation` không tìm annotation class ở superclass. `Class.getAnnotation` có thể tìm class annotation gắn `@Inherited` theo quy tắc riêng. `getAnnotationsByType` mở repeatable container. Annotation trên method **không tự được kế thừa vào overriding method** bởi `@Inherited`.

Một cache lưu kết quả `getDeclaredMethods` khác về ý nghĩa với cache lưu `getMethods`. Khi cache metadata, hãy công bố rõ quy tắc quét và bảo đảm code xây cache dùng đúng API.

### Khi cần làm mới metadata

- Framework có policy/config động được kết hợp với annotation metadata.
- Class được redefine/retransform thông qua instrumentation (tùy phạm vi, quy tắc và mục đích).
- Registry rebuild sau deploy/reload plugin.
- Ứng dụng muốn chủ động thay đổi cấu trúc metadata đã diễn giải.

`ClassValue.remove(type)` là công cụ invalidation rõ ràng. Trong ví dụ, nó cho phép minh họa việc chạy lại scan. Đừng gọi remove trên mọi request, nếu không bạn đã triệt tiêu lợi ích reuse.

### Access checks và module boundaries

Đọc metadata bằng reflection **khác** gọi một private method. Có thể lấy một đối tượng `Method` nhưng vẫn không có quyền `invoke` nếu Java access checks/JPMS không cho phép. Cache `Method` không bypass được `setAccessible` rules hoặc module encapsulation.

Không nên vì lỗi truy cập mà tự động mở mọi module bằng `--add-opens`. Framework cần tài liệu hóa các gói phải `opens` và tối thiểu hóa mức quyền. `MethodHandles.Lookup` có thể là lựa chọn trong một số thiết kế nhưng vẫn cần tuân thủ access control.

## 6. Class loader identity: cùng tên không phải cùng Class

Java runtime type identity liên quan đến **binary name và defining class loader**. Hai `Class<?>` có cùng `getName()` nhưng được định nghĩa bởi hai loaders khác nhau có thể là **hai kiểu riêng biệt**.

Ví dụ:

~~~java
Class<?> a = PluginType.class;
Class<?> b = Class.forName("PluginType", false, isolatedLoader);
System.out.println(a == b);
~~~

Đây là **đoạn minh họa**; `isolatedLoader` giả định đã được tạo phù hợp. Có thể in `false` dù cả hai classes tên `PluginType`. Vì vậy cache global kiểu:

~~~java
Map<String, Metadata> byClassName;
~~~

có thể bị **collision giữa plugins** nếu chỉ dùng `class.getName()`. Nếu cache được scope hoàn toàn dưới một loader/phiên bản thì key tên có thể đủ trong phạm vi đó, nhưng cache chung cho nhiều loaders phải xét đúng identity.

Ngược lại, chỉ đổi `String` key sang `Class<?>` key trong một static `ConcurrentHashMap` lại tăng nguy cơ giữ loader cũ. Cần giải quyết **identity lẫn lifetime**.

### URLClassLoader không phải công cụ chứng minh unloading

Trong chương trình bên dưới, tạo một `URLClassLoader` riêng rồi gọi `Class.forName(..., false, isolated)`. Đây là test **type identity**, không phải test rằng class loader đã được GC. `URLClassLoader.close()` đóng những resource do loader quản lý nhưng không bảo đảm tất cả objects/classes được unload ngay.

## 7. Ví dụ hoàn chỉnh Java 17: ClassValue và hai class loaders

Lưu toàn bộ vào file **ReflectionCacheDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route { String value(); }

class Service {
    @Route("/check")
    public void check() {}
    public void ping() {}
}

class PluginType {}

public class ReflectionCacheDemo {
    private static final AtomicInteger SCANS = new AtomicInteger();
    private static final ClassValue<Map<String, String>> ROUTES =
            new ClassValue<>() {
                @Override protected Map<String, String> computeValue(Class<?> type) {
                    SCANS.incrementAndGet();
                    Map<String, String> found = new TreeMap<>();
                    for (Method method : type.getDeclaredMethods()) {
                        Route route = method.getDeclaredAnnotation(Route.class);
                        if (route != null) found.put(method.getName(), route.value());
                    }
                    return Map.copyOf(found);
                }
            };

    public static void main(String[] args) throws Exception {
        Map<String, String> first = ROUTES.get(Service.class);
        Map<String, String> second = ROUTES.get(Service.class);
        System.out.println("routes=" + new TreeMap<>(first));
        System.out.println("sameCache=" + (first == second));
        System.out.println("scans=" + SCANS.get());
        System.out.println("pingPresent=" + first.containsKey("ping"));
        System.out.println("annotationPresent=" +
                Service.class.getDeclaredMethod("check").isAnnotationPresent(Route.class));

        ROUTES.remove(Service.class);
        System.out.println("afterRemove=" + new TreeMap<>(ROUTES.get(Service.class)));
        System.out.println("scansAfterRemove=" + SCANS.get());

        URL location = PluginType.class.getProtectionDomain()
                .getCodeSource().getLocation();
        try (URLClassLoader isolated =
                     new URLClassLoader(new URL[]{location}, null)) {
            Class<?> other = Class.forName("PluginType", false, isolated);
            System.out.println("sameName=" +
                    (other.getName().equals(PluginType.class.getName())));
            System.out.println("sameClass=" + (other == PluginType.class));
            System.out.println("differentLoader=" +
                    (other.getClassLoader() != PluginType.class.getClassLoader()));
        }
    }
}
~~~

Ở file này, `Service`, `PluginType` và `Route` là package-private; chỉ `ReflectionCacheDemo` là public. Không cần thêm file source cho `PluginType` vì javac biên dịch tất cả khai báo top-level trong file.

### Lệnh biên dịch/chạy

Từ thư mục chứa file, dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d out ReflectionCacheDemo.java
java -cp out ReflectionCacheDemo
~~~

**Stdout thực tế (đã biên dịch và chạy với `--release 17`):**

~~~text
routes={check=/check}
sameCache=true
scans=1
pingPresent=false
annotationPresent=true
afterRemove={check=/check}
scansAfterRemove=2
sameName=true
sameClass=false
differentLoader=true
~~~

### Giải thích sáu dòng đầu: cache và việc quét

- `routes={check=/check}`: scan tìm `@Route("/check")` và tạo mapping bất biến.
- `sameCache=true`: hai lần `ROUTES.get(Service.class)` trong demo tuần tự, không invalidation, trả **cùng value object**.
- `scans=1`: `computeValue` chạy một lần trong demo **tuần tự**; không là bảo đảm chính xác một lần dưới race.
- `pingPresent=false`: method không annotate không có route; lookup sau scan không cần reflection.
- `annotationPresent=true`: `@Route` được đọc đúng trên `Method check()`.
- `afterRemove={check=/check}` và `scansAfterRemove=2`: sau `remove`, metadata của Service được tạo lại.

### Giải thích ba dòng cuối: class loader identity

- `sameName=true`: cả hai `Class<?>` tên `PluginType`.
- `sameClass=false`: chúng là hai runtime types khác nhau.
- `differentLoader=true`: một được nạp trong application loader, class kia trong `URLClassLoader` có parent `null`.
- `PluginType.class.getProtectionDomain().getCodeSource().getLocation()` trỏ vào output `out` trong setup này; loader mới có thể tìm `PluginType.class` từ đó.
- `try-with-resources` đóng `URLClassLoader` khi rời khối; đây là **resource cleanup**, không phải chứng minh loader đã unload.

Ví dụ dùng tên method làm key chỉ vì `Service` có hai method tên khác nhau. Khi làm thật với overload, phải đổi key. Đối với plugin jar phức tạp, còn phải xử lý delegation, packages, module layers, resources và security policy.

## 8. Đo hiệu năng thay vì phỏng đoán

**Functional correctness test ở mục 7 không phải benchmark hiệu năng**. Một phép đo tốt cần:

1. **Xác định workload:** số class, số methods, số annotations và số truy vấn lặp theo request.
2. **Baseline rõ ràng:** đo chi phí resolve method, get annotation và biến đổi metadata, tách khỏi I/O/DB/network.
3. **Warmup JVM:** JIT và reflection internals có thể thay đổi đáng kể giữa lần đầu và lần lặp.
4. **Tránh dead-code elimination:** sử dụng kết quả benchmark thực sự; có thể dùng JMH với `Blackhole`.
5. **Đo allocations/GC:** một cache có thể giảm CPU nhưng tăng footprint, thời gian startup hoặc memory retention.
6. **Đo p95/p99 và concurrency:** nhất là nếu nhiều threads cùng truy vấn cache ở lần đầu.
7. **Thử class-loader reload:** nếu hỗ trợ plugin reload, đo cả số loaders còn reachable/metaspace và latency sau nhiều chu kỳ.
8. **Không suy ra multiplier cố định:** kết quả phụ thuộc JDK, CPU, annotation structure và thiết kế framework.

Các API introspection của JDK có thể đã cache nội bộ, nên phép đo đúng là so **toàn bộ đường đi business metadata trước và sau cache ứng dụng**, không nhất thiết so hai lời gọi API tách rời trong một vòng lặp bị JIT tối ưu.

### Có thể cache quá mức không?

Có. Nếu app ít class và chỉ quét một lần ở startup, thêm `ClassValue`, registry và invalidation có thể chỉ tăng complexity. Nếu cache giữ danh sách lớn `Method`/`Field` mà business chỉ dùng vài giá trị String, memory usage có thể cao hơn cần thiết.

Hãy chọn metadata nhỏ và đúng mục tiêu, không mặc định lưu nguyên bộ Java reflection objects.

## 9. Debug class loader leak trong ứng dụng dùng annotation

Dấu hiệu gợi ý gồm số class loaders cũ hoặc metaspace tăng qua các lần redeploy. Đây chỉ là **triệu chứng**, không tự chứng minh static reflection cache là nguyên nhân.

Quy trình:

1. Xác định loader nào tạo class của plugin và loader nào sở hữu static cache.
2. Duyệt reference graph: cache, thread locals, tasks, listeners, MBeans, callbacks, framework registries.
3. Tìm strong references tới `Class<?>`, `Method`, instance hoặc `ClassLoader` của plugin.
4. Kiểm tra `WeakHashMap` values có giữ ngược lại keys không.
5. Cân nhắc `ClassValue` hoặc per-plugin scoped registry; clear lifecycle data khi unload.
6. Unregister callbacks, stop threads/executors, close resources do plugin tạo.
7. Kiểm tra qua heap dump/JFR/class-loader statistics và nhiều lần reload; không xem một lần `System.gc()` là bằng chứng.

**Cần phân biệt** leak trong heap objects, class metadata/metaspace và một cache đang giữ dữ liệu hợp lệ do plugin vẫn còn hoạt động.

## 10. Thực hành thiết kế registry annotation

| Tình huống | Thiết kế gợi ý |
| --- | --- |
| Chỉ quét một lần khi bootstrap | Dựng registry bất biến, không cần nhiều lớp cache |
| Truy vấn metadata cùng class liên tục | `ClassValue<Metadata>` hoặc per-class cache vòng đời rõ |
| Có nhiều class loaders | Dựa vào `Class<?>` identity hoặc scope riêng loader, không chỉ class name |
| Có plugin hot reload | Ràng lifetime của cache với class/plugin; tránh static strong refs |
| Có method overload | Khóa theo signature, không dùng tên đơn |
| Có repeatable annotations | Dùng `getAnnotationsByType` theo chính sách rồi cache kết quả chuẩn hóa |
| Cần đọc inherited methods | Chọn rõ `getMethods` và policy annotation superclass/interface |
| Metadata tùy tenant/config | Tách structural metadata khỏi runtime policy |
| Cần gọi private method | Tuân thủ Java access checks và JPMS `opens` |
| Chưa rõ bottleneck | Đo trước, tối ưu sau |

Một thiết kế registry tốt không chỉ có cấu trúc cache mà phải có **contract**:

- **Build:** quét những annotated elements nào? Class, declared method, inherited method hay field?
- **Key:** `Class<?>`, method signature, class loader scope, tenant/config version?
- **Value:** immutable route info, constraint descriptors, Method/MethodHandle?
- **Concurrency:** compute may race; có cần exact-once side effect không?
- **Invalidation:** ai gọi `remove` hoặc clear, khi nào?
- **Lifecycle:** ai sở hữu registry, khi nào dispose/unregister?
- **Observability:** đếm số scans, cache hits/misses, allocations, retained loaders?

## 11. Các lỗi thường gặp

**Lỗi 1 — Cho rằng annotation tự làm runtime reflection tốn CPU mỗi lần gọi method.** Không. Chỉ consumer thực sự đọc/xử lý metadata mới tạo công việc đó.

**Lỗi 2 — Cho rằng cache mọi Method sẽ luôn nhanh hơn.** Cần đo; cache lớn có thể tăng memory và giữ loader cũ.

**Lỗi 3 — Dùng class name làm key chung cho nhiều class loaders.** Hai classes cùng tên nhưng khác defining loader có identity khác; cache có nguy cơ collision.

**Lỗi 4 — Dùng static ConcurrentHashMap<Class<?>, ...> mà quên lifecycle.** Strong keys có thể giữ toàn bộ class loader/plugin.

**Lỗi 5 — Thay bằng WeakHashMap rồi coi như leak đã hết.** Strong values có thể tham chiếu ngược tới weak keys.

**Lỗi 6 — Nghĩ ClassValue đảm bảo computeValue chỉ chạy đúng một lần.** Dưới concurrent initialization, nhiều lần tính có thể xảy ra; `remove` cũng kích hoạt tính lại.

**Lỗi 7 — Không có invalidation cho dữ liệu business có thể thay đổi.** Metadata class và cấu hình động cần những chiến lược cache khác nhau.

**Lỗi 8 — Nhầm annotation trực tiếp với annotation kế thừa/lặp.** `getDeclaredAnnotation`, `getAnnotation` và `getAnnotationsByType` có semantics khác nhau. Cache đúng API theo contract consumer.

**Lỗi 9 — Coi cache là cách vượt JPMS access control.** Không. `Method.invoke` trên member không public vẫn chịu access checks.

**Lỗi 10 — Thấy ClassLoader.close() thành công rồi kết luận đã unload.** Không. Đóng tài nguyên khác với GC class unloading; cần profiling/reference graph.

## 12. Câu hỏi tự kiểm tra

**1. Khi nào cache annotation có thể giúp?** Khi ứng dụng quét/diễn giải cùng metadata nhiều lần trên hot path và kết quả ổn định đủ để tái sử dụng.

**2. Vì sao cache `Method` trong một static singleton có thể giữ loader?** Vì Method tham chiếu class khai báo; đường strong references từ static cache có thể dẫn tới defining loader.

**3. WeakHashMap<Class<?>, List<Method>> có chắc không leak không?** Không; value giữ mạnh Method và có thể giữ lại chính Class dùng làm key.

**4. ClassValue khác static Map theo ý nào?** Liên kết lazy value với từng Class object, không cần một static map mạnh lưu mọi Class keys; phù hợp metadata per-class.

**5. `computeValue` đảm bảo chạy đúng một lần khi nhiều threads race không?** Không. Tính toán có thể thực hiện đồng thời, dù chỉ một giá trị được gắn vào cache.

**6. Vì sao `sameName=true` nhưng `sameClass=false`?** Hai class có cùng binary name nhưng được định nghĩa bởi hai class loaders khác nhau.

**7. Class-only cache có đúng cho metadata thay đổi theo tenant không?** Chưa đủ; cần tách cấu hình động hoặc thêm tenant/config-version dimension.

**8. Làm sao để cache hỗ trợ overload?** Key gồm method signature hoặc một định danh method không mơ hồ, không chỉ tên.

**9. Dùng `System.gc()` có chứng minh class loader đã unload không?** Không.

**10. Ví dụ `ReflectionCacheDemo` chứng minh gì và không chứng minh gì?** Nó chứng minh kết quả đọc annotation/cache/invalidation/type identity cụ thể, **không chứng minh tốc độ nhanh hơn theo một tỷ lệ cố định hoặc class loader đã được GC**.

## 13. Tài liệu chính thức

- Java SE 21 — **ClassValue**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html
- Java SE 21 — **Class và reflection APIs**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — **AnnotatedElement và repeatable annotations**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java SE 21 — **Method và AccessibleObject**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 21 — **ClassLoader** và **URLClassLoader**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 21 — **WeakHashMap**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html
- JVM Specification `5.3 — **Creation of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3

**Ghi nhớ:** cache annotation đúng là **cache đúng kết quả của một chính sách tra cứu** theo **vòng đời thích hợp**. Trước hết hiểu reflection đang quét gì, dữ liệu nào có thể chuẩn hóa bất biến, class identity nào làm khóa, và reference nào có thể giữ class loader cũ. `ClassValue` hữu ích cho per-class metadata; đo benchmark và kiểm tra class-loader lifecycle mới cho biết thiết kế tối ưu có thực sự đạt mục tiêu hay không.