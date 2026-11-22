# 18.3. Tạo DynamicLinker từ DynamicLinkerFactory và tích hợp vào bootstrap

## Mục tiêu học tập

Bài học thuộc **Java Advance – dynamic-runtime**, phần **18. Dynalink**. Sau bài này, bạn có thể:

- Trình bày mối quan hệ giữa `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`, `Operation`, `RelinkableCallSite` và `GuardedInvocation`.
- Tạo một linker dùng `DynamicLinkerFactory.createLinker()`; hiểu cấu hình linker ưu tiên, linker dự phòng, class loader dùng để khám phá linker, ngưỡng relink không ổn định và đồng bộ khi cập nhật call site.
- Xây dựng bootstrap method với chữ ký quen thuộc `(MethodHandles.Lookup, String, MethodType) -> CallSite`, chuẩn hóa tên operation và type trước khi giao call site cho Dynalink.
- Tạo `SimpleRelinkableCallSite` với `CallSiteDescriptor` và gọi `dynamicLinker.link(callSite)` đúng trình tự.
- Hiểu **lazy linking**: `link` ban đầu gắn đường gọi để thực hiện liên kết khi có **đối số runtime đầu tiên**, rồi gọi linker thích hợp; guard thất bại có thể gây relink.
- Dùng `StandardOperation.GET/SET`, `StandardNamespace.PROPERTY/ELEMENT` và `NamedOperation` để mô tả thao tác mà không viết chuỗi operation tùy tiện trong tầng linker.
- Tạo linker tùy chỉnh bằng `GuardingDynamicLinker` và đặt nó trước default `BeansLinker` với `setPrioritizedLinker`; trả `null` khi không nhận kiểu/operation để fallback xử lý.
- Phân biệt chương trình **gọi bootstrap thủ công để học Dynalink** và một **lệnh `invokedynamic` thật trong class file**; biết điều gì phải do compiler/bytecode generator đảm nhiệm.
- Chẩn đoán lỗi mismatch `MethodType`, access, guard sai, unsupported operation, cache thrashing, stale target và rủi ro khi định nghĩa runtime ngôn ngữ động.

**Môi trường:** JDK 17 trở lên có module `jdk.dynalink`. Ba ví dụ Java 17 được kiểm tra bằng `javac --release 17` và `java`, không cần thư viện bên ngoài. Nếu xây ứng dụng dạng named Java module, khai báo `requires jdk.dynalink;` trong `module-info.java`. Các chương trình minh họa bên dưới chạy trên **classpath**, nên lệnh ngắn không cần file module-info.

## 1. Vấn đề mà Dynalink giải quyết

Một ngôn ngữ động có biểu thức:

~~~text
value.name
~~~

Nhưng tại thời điểm biên dịch, `value` có thể là:

- Một Java bean có `getName()`;
- Một đối tượng của runtime ngôn ngữ riêng;
- Một Map hoặc một object có quy tắc truy cập property/element;
- Một implementation mà type chỉ biết khi thực thi.

Tại mỗi vị trí gọi, runtime muốn:

1. Biết **thao tác** cần làm (ví dụ lấy property `name`).
2. Xem **đối tượng runtime thực tế** và chọn cách xử lý thích hợp.
3. Gắn MethodHandle thực thi, tốt nhất với một **guard** báo khi nào liên kết còn hợp lệ.
4. Khi type/shape thay đổi, liên kết lại mà vẫn giữ ý nghĩa của cùng vị trí gọi.

Dynalink trong module `jdk.dynalink` là thư viện hỗ trợ phối hợp quá trình đó. Nó cung cấp cách mô tả operation, lựa chọn guarding linker và cập nhật call site. Nó **không phải compiler hoặc bytecode generator**: việc tạo một lệnh `invokedynamic` trong classfile là trách nhiệm của compiler/tool riêng.

### 1.1. Bức tranh tổng thể

~~~text
Compiler / interpreter của ngôn ngữ động
             |
             | tạo CallSiteDescriptor từ Lookup + Operation + MethodType
             v
Bootstrap method
             |
             | new SimpleRelinkableCallSite(descriptor)
             v
       DynamicLinker.link(callSite)
             |
             | đặt target khởi đầu: relink-and-invoke
             v
Lần gọi đầu tiên với đối số runtime (receiver)
             |
             | Dynalink hỏi các GuardingDynamicLinker theo thứ tự
             v
  prioritized -> autodiscovered -> fallback/BeansLinker
             |
             | GuardedInvocation { invocation, guard, ... }
             v
 RelinkableCallSite lưu phương án gọi có guard
             |
             +------ guard true ------> gọi MethodHandle đã liên kết
             |
             +------ guard false -----> relink cho type/shape mới
~~~

Khi dùng Dynalink đúng, **factory** chỉ cần tạo/linker lúc setup runtime; **bootstrap** tạo call site theo từng vị trí thao tác; **DynamicLinker** điều phối; **guarding linkers** biết cụ thể cách gọi object.

### 1.2. Vai trò từng lớp

| Thành phần | Vai trò | Thứ KHÔNG nên nhầm |
| --- | --- | --- |
| `DynamicLinkerFactory` | Cấu hình và tạo `DynamicLinker` | Không phải CallSite hay bootstrap method |
| `DynamicLinker` | Điều phối linker, thiết lập relink cho các call site | Không trực tiếp là MethodHandle của business method |
| `CallSiteDescriptor` | Chứa `Lookup`, `Operation` và `MethodType` bất biến của call site | Không chứa receiver runtime |
| `Operation` | Diễn tả GET/SET/CALL/NEW... và namespace/name | Không chỉ là chuỗi tùy ý |
| `RelinkableCallSite` | CallSite có thể nhận target mới từ Dynalink | Không phải `ConstantCallSite` |
| `SimpleRelinkableCallSite` | Chiến lược lưu **một** guarded invocation hiện tại (monomorphic) | Không cache vô hạn các type |
| `ChainedCallSite` | Chiến lược lưu một chuỗi guarded invocations (polymorphic) | Không phải lựa chọn luôn tốt nhất |
| `GuardingDynamicLinker` | Đề xuất liên kết cho receiver/operation có thể xử lý | Trả `null` nếu không nhận, không ép chiếm mọi lời gọi |
| `GuardedInvocation` | Kết hợp invocation handle, guard và invalidation tùy chọn | Không phải chỉ một MethodHandle vô điều kiện |
| `BeansLinker` | Fallback thông dụng để thao tác trên Java objects | Không tự biết toàn bộ semantics của ngôn ngữ tùy chỉnh |

## 2. Tạo DynamicLinker bằng factory

Code cốt lõi:

~~~java
// Fragment: có import jdk.dynalink.DynamicLinkerFactory/DynamicLinker.
DynamicLinkerFactory factory = new DynamicLinkerFactory();
DynamicLinker linker = factory.createLinker();
~~~

Factory tạo linker theo cấu hình **tại thời điểm `createLinker()`**. Cấu hình một factory đã xong không có nghĩa mọi DynamicLinker tạo trước đó lập tức biến đổi. Thường nên dựng, cấu hình, rồi tạo một linker và dùng lại cho nhiều call sites trong runtime.

Tạo linker mặc định đủ để thử **Java objects** vì `DynamicLinkerFactory` mặc định có fallback `BeansLinker` nếu người dùng không tự cấu hình danh sách fallback khác. Điều này là điểm khởi đầu tốt: không cần viết `GuardingDynamicLinker` ngay khi mục tiêu chỉ là đọc Java bean property.

### 2.1. Một cấu hình thực tế hơn

~~~java
// Fragment: được sử dụng bên trong createLinker() của ví dụ đầy đủ.
DynamicLinkerFactory factory = new DynamicLinkerFactory();
factory.setSyncOnRelink(true);
factory.setUnstableRelinkThreshold(4);
DynamicLinker linker = factory.createLinker();
~~~

Ý nghĩa:

- `setSyncOnRelink(true)` khiến DynamicLinker gọi cơ chế `MutableCallSite.syncAll` sau khi relink theo contract. Mục tiêu là hỗ trợ publication/visibility của target mới trong môi trường nhiều thread; **không** biến state của receiver thành thread-safe.
- `setUnstableRelinkThreshold(4)` đặt ngưỡng để site sau một số lần relink được xem là “unstable”, nhờ đó các linker có thể được thông báo qua `LinkRequest.isCallSiteUnstable()` và chọn cách xử lý phù hợp. Không phải giới hạn “chỉ cho relink tối đa 4 lần”.
- Mặc định của ngưỡng này là **8** nếu không cấu hình; giá trị **0** có nghĩa không bao giờ đánh dấu call site unstable theo cấu hình đó.
- `createLinker()` trả `DynamicLinker` có pipeline đã thiết lập.

Trong bài thực hành, các thiết lập này giúp thấy code đúng chỗ. **Không suy ra hiệu năng tốt hơn chỉ vì bật sync hoặc hạ threshold**. Mức tối ưu phụ thuộc workload, phân bố receiver types, chiến lược guard và concurrency.

### 2.2. Linker ưu tiên và fallback

Framework có object model riêng thường đăng ký một `GuardingDynamicLinker`:

~~~java
// Fragment: customLinker thực thi GuardingDynamicLinker.
factory.setPrioritizedLinker(customLinker);
DynamicLinker linker = factory.createLinker();
~~~

Dynalink hỏi các nhóm linker theo thứ tự quy định: **prioritized**, các linker được **tự động khám phá** qua class loader/service provider, rồi **fallback**. Với mặc định thường có `BeansLinker` ở cuối để xử lý Java objects.

Điều quan trọng là **return null để nhường đường** khi custom linker không hiểu operation hoặc receiver. Nếu custom linker trả một `GuardedInvocation` sai cho type không thuộc quyền của nó, các linker Java fallback không còn được hỏi và call site có thể hoạt động sai.

### 2.3. Các cấu hình factory nên biết

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `setPrioritizedLinker(linker)` / `setPrioritizedLinkers(...)` | Đặt linker cho object model của runtime ở phía trước | Linker custom nên kiểm tra operation và receiver |
| `setFallbackLinkers(...)` | Chỉ định danh sách fallback | Danh sách rỗng có thể loại bỏ BeansLinker mặc định |
| `setClassLoader(loader)` | ClassLoader để phát hiện `GuardingDynamicLinkerExporter` | Mặc định sử dụng context class loader của thread khi createLinker |
| `getAutoLoadingErrors()` | Xem lỗi khi autoloading trong lần `createLinker()` gần nhất | Hữu ích khi deployment/service provider không được tìm thấy |
| `setSyncOnRelink(true/false)` | Đồng bộ publication sau relink | Không đồng bộ hóa state của object mục tiêu |
| `setUnstableRelinkThreshold(n)` | Đánh dấu site unstable sau đủ số lần relink | Không phải “khóa site” sau n lần |
| `setPrelinkTransformer(...)` | Tùy biến guarded invocation ngay trước khi gắn vào call site | Nâng cao; mặc định đã thích ứng kiểu qua LinkerServices |
| `setAutoConversionStrategy(...)` | Bổ sung chiến lược chuyển đổi kiểu ở tầng linker | Không phải cast tùy tiện bỏ qua type safety |
| `setInternalObjectsFilter(...)` | Filter các đối tượng nội bộ trong handle phù hợp language runtime | Cần hiểu rõ boundary của ngôn ngữ |

**Đừng cấu hình `setFallbackLinkers` bằng danh sách rỗng trong ví dụ Java-bean đơn giản**, vì sẽ bỏ đi cơ chế cần thiết để đọc Java property qua BeansLinker. Nếu muốn tự kiểm soát fallback, hãy tạo và đăng ký rõ linker tương ứng.

## 3. Mô tả operation: từ tên bootstrap sang CallSiteDescriptor

`CallSiteDescriptor` ghi:

1. `MethodHandles.Lookup`: context caller và quyền truy cập thích hợp.
2. `Operation`: bản chất thao tác động.
3. `MethodType`: chữ ký cố định tại vị trí dynamic call.

Một descriptor như sau:

~~~java
// Fragment: caller và type được nhận từ bootstrap method.
Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("name");
CallSiteDescriptor descriptor =
        new CallSiteDescriptor(caller, operation, type);
~~~

Diễn giải là: **lấy property có tên "name" của receiver**. `Operation.withNamespace` gắn `StandardNamespace.PROPERTY` vào GET; `named("name")` đóng băng tên property trong descriptor thay vì nhận nó từ operand runtime.

### 3.1. Vì sao GET cần namespace?

`StandardOperation.GET` dùng để lấy giá trị từ một namespace do object model định nghĩa. Với Dynalink, GET/SET phải gắn vào namespace thích hợp:

| Namespace tiêu biểu | Ý nghĩa |
| --- | --- |
| `StandardNamespace.PROPERTY` | Property/bean property/field semantics |
| `StandardNamespace.ELEMENT` | Phần tử có index/key, như Map/list/array theo quy tắc linker |
| `StandardNamespace.METHOD` | Tra method như một thuộc tính callable, theo object model và linker |

Không có quy tắc rằng “mọi object đều hỗ trợ cả ba namespace theo cùng cách”. Linker riêng cho từng ngôn ngữ có thể có lookup semantics khác nhau. Tài liệu của `jdk.dynalink` chỉ cung cấp chuẩn biểu diễn operation, không định nghĩa một object model thống nhất cho mọi runtime.

### 3.2. Named GET và unnamed GET có signature khác nhau

| Operation | Signature logic | Ví dụ |
| --- | --- | --- |
| `GET.withNamespace(PROPERTY)` | `(receiver,name) -> value` | Tên property là operand runtime |
| `GET.withNamespace(PROPERTY).named("name")` | `(receiver) -> value` | Tên được giữ trong descriptor |
| `SET.withNamespace(ELEMENT)` | `(receiver,key,value) -> void` | Key từ operand runtime |
| `SET.withNamespace(ELEMENT).named("id")` | `(receiver,value) -> void` | Key cố định "id" |
| `CALL` | `(callable,receiver,args...) -> value` | Cần callable object và receiver theo contract của Dynalink |
| `NEW` | `(constructor,args...) -> value` | Tạo instance qua callable constructor |

Hai tham số `receiver`/`name` là **vị trí động theo contract**, không nói rằng mọi tham số nhất thiết là `Object.class` trong MethodType. Bạn có thể chọn kiểu cụ thể, miễn linker và conversions hỗ trợ. Trong ví dụ, dùng `Object` để một site nhận nhiều runtime classes.

### 3.3. Operation là dữ liệu cấu trúc, không nên parse bừa

Ví dụ bootstrap nhận `name="getName"`; trong code, ta dùng một bảng mapping cố định chuyển nó thành:

~~~java
// Fragment:
if (!name.equals("getName")) {
    throw new IllegalArgumentException("Unknown operation: " + name);
}
Operation operation = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("name");
~~~

Đây là chính sách của **language runtime**: tên symbolic tại invokedynamic call site không tự mang đầy đủ semantics của Dynalink. Runtime phải quy định mapping từ name/static bootstrap args sang `Operation` một cách kiểm tra được.

Tránh cho input bên ngoài chỉ định tên property/method tùy ý mà không qua policy. `BeansLinker` truy cập Java members theo semantics/visibility của nó; không xem named operation là permission check.

## 4. Tích hợp vào bootstrap method

Một bootstrap method thông dụng cho invokedynamic có dạng:

~~~java
// Chữ ký tham khảo, không phải toàn bộ chương trình:
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type) {
    ...
}
~~~

Khi JVM liên kết một `invokedynamic` instruction, nó cung cấp ngữ cảnh caller, symbolic name, MethodType của site và các static bootstrap arguments khác (nếu bytecode quy định). Bootstrap **phải trả một CallSite** có target/type đáp ứng yêu cầu của JVM.

Đường đi với Dynalink:

~~~text
JVM liên kết invokedynamic
    |
    | Lookup caller, symbolic name, MethodType
    v
Runtime.bootstrap(caller,name,type)
    |
    | parse/validate operation
    v
new CallSiteDescriptor(caller,operation,type)
    |
    v
new SimpleRelinkableCallSite(descriptor)
    |
    v
dynamicLinker.link(callSite)
    |
    v
return CallSite cho JVM
    |
    v
Lần invoke thật đầu tiên -> Dynalink liên kết với receiver thực tế
~~~

Điểm cần nhớ: **`DynamicLinker.link` nhận một `RelinkableCallSite`, không nhận một `ConstantCallSite`**. `ConstantCallSite` có target bất biến; Dynalink cần quyền cập nhật target khi guard không hợp lệ.

### 4.1. Mẫu bootstrap đúng

~~~java
// Fragment: LINKER đã tạo sẵn, parseOperation(name) do runtime định nghĩa.
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name, MethodType type) {
    Operation op = parseOperation(name);
    CallSiteDescriptor desc = new CallSiteDescriptor(caller, op, type);
    return LINKER.link(new SimpleRelinkableCallSite(desc));
}
~~~

`DynamicLinker.link(callSite)` gắn **relink-and-invoke handle** ban đầu rồi trả lại chính callSite đã được thiết lập. Nó **chưa cần biết receiver cụ thể** khi bootstrap chỉ được gọi với Lookup/name/type. Receiver xuất hiện sau, tại **lần thực thi đầu tiên** của call site.

Đây là khác biệt giữa:
- **bootstrap/link call site**: chuẩn bị cơ chế.
- **runtime guard linking**: chọn phương án cho receiver thực.
- **invoke business operation**: chạy handle đã liên kết.

### 4.2. Vì sao nên giữ một DynamicLinker tái sử dụng?

Trong ví dụ hoàn chỉnh, `LINKER` là `private static final` và được tạo một lần:

~~~java
// Fragment:
private static final DynamicLinker LINKER = makeLinker();
~~~

Nhiều bootstrap calls có thể dùng cùng DynamicLinker để tạo **các call site riêng** cho nhiều vị trí bytecode. Việc có một linker chung **không** đồng nghĩa mọi vị trí gọi dùng cùng một `CallSite` hoặc cùng receiver cache.

Trong runtime có nhiều plugin/language environments hoặc classloaders, có thể cần một DynamicLinker theo context classloader/module runtime, tránh trộn linker discovery không tương thích. Quản lý cache/lifetime là trách nhiệm ứng dụng.

## 5. Ví dụ hoàn chỉnh 1: factory mặc định, bootstrap và Java beans

Lưu file **DynalinkBootstrapDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBootstrapDemo {
    public static final class Customer {
        private final String name;
        public Customer(String name) { this.name = name; }
        public String getName() { return name; }
    }

    public static final class Employee {
        private final String name;
        public Employee(String name) { this.name = name; }
        public String getName() { return name; }
    }

    private static final DynamicLinker LINKER = makeLinker();

    private static DynamicLinker makeLinker() {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setSyncOnRelink(true);
        factory.setUnstableRelinkThreshold(4);
        return factory.createLinker();
    }

    // Signature phù hợp mô hình invokedynamic bootstrap.
    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String name, MethodType type) {
        if (!name.equals("getName")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }
        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY).named("name");
        CallSiteDescriptor descriptor = new CallSiteDescriptor(caller, operation, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor));
    }

    public static void main(String[] args) throws Throwable {
        MethodType siteType = MethodType.methodType(Object.class, Object.class);
        CallSite site = bootstrap(MethodHandles.lookup(), "getName", siteType);
        MethodHandle invoker = site.dynamicInvoker();

        System.out.println("siteType=" + site.type());
        System.out.println("callSiteClass=" + site.getClass().getSimpleName());
        System.out.println("customer1="
                + (Object) invoker.invokeExact((Object) new Customer("Mai")));
        System.out.println("customer2="
                + (Object) invoker.invokeExact((Object) new Customer("An")));
        System.out.println("employee="
                + (Object) invoker.invokeExact((Object) new Employee("Binh")));
        System.out.println("customer3="
                + (Object) invoker.invokeExact((Object) new Customer("Hoa")));
        try {
            bootstrap(MethodHandles.lookup(), "missing", siteType);
        } catch (IllegalArgumentException ex) {
            System.out.println("badOperation=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy trên **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkBootstrapDemo.java
java DynalinkBootstrapDemo
~~~

**Stdout chính xác**:

~~~text
siteType=(Object)Object
callSiteClass=SimpleRelinkableCallSite
customer1=Mai
customer2=An
employee=Binh
customer3=Hoa
badOperation=IllegalArgumentException
~~~

### 5.1. Giải thích luồng lần đầu

`bootstrap(...)` tạo descriptor:

~~~text
lookup      = MethodHandles.lookup() của caller minh họa
operation   = GET PROPERTY named "name"
method type = (Object)Object
~~~

Trả về `SimpleRelinkableCallSite` đã đưa qua `LINKER.link`. Tại thời điểm này, code **chưa truyền** `Customer("Mai")` vào bootstrap.

Lời gọi đầu:

~~~java
// Fragment từ main:
Object value = (Object) invoker.invokeExact((Object) new Customer("Mai"));
~~~

đưa receiver runtime kiểu `Customer` vào call site. Dynalink chọn linker phù hợp; mặc định `BeansLinker` có thể đọc public JavaBean-style getter `Customer.getName()`. Kết quả là `Mai`.

### 5.2. Lời gọi cùng type và khác type

Lần thứ hai là `Customer("An")`, cùng runtime class với lần đầu; nếu guard cho class vẫn hợp lệ, call site có thể tái sử dụng guarded invocation đã liên kết.

Lần thứ ba là `Employee("Binh")`, runtime type khác. Với `SimpleRelinkableCallSite`, guard kiểu cũ có thể không chấp nhận, nên Dynalink chọn đường liên kết mới; `Employee.getName()` vẫn trả một giá trị hợp lệ. Lần thứ tư quay về `Customer("Hoa")` và có thể relink thêm lần nữa.

**Không nên cài test dựa trên một số lượng relink cố định** trừ khi bạn đang kiểm soát chính GuardingDynamicLinker và thuật toán guard. Một cache có thể tối ưu theo receiver type/shape. Mục tiêu của test này là kiểm tra **hành vi** của cả hai loại Java object, không định nghĩa internals của BeansLinker.

### 5.3. Vì sao dùng `(Object)Object`?

CallSiteDescriptor chứa `MethodType.methodType(Object.class,Object.class)`. Đây là kiểu của **dynamic operation GET named property**:

~~~text
(receiver Object) -> result Object
~~~

Dù actual getter trả `String`, BeansLinker/DynamicLinker có thể thích ứng return type để phù hợp signature của site. Đoạn Java gọi `invokeExact` ghi cast `(Object)` ở cả tham số và result **để descriptor tại call site trùng hoàn toàn**.

Đừng viết:

~~~java
// Fragment CỐ Ý SAI khi invoker có type (Object)Object:
String x = (String) invoker.invokeExact((Object) new Customer("Mai"));
~~~

Trong Java source, cast kết quả trực tiếp sang `String` tạo call-site return type mong đợi `String` và có thể ném `WrongMethodTypeException`, vì handle của site trả `Object`. Đúng là **lấy Object trước**, rồi cast sang String sau nếu bạn biết contract:

~~~java
// Fragment hợp lệ:
Object raw = (Object) invoker.invokeExact((Object) new Customer("Mai"));
String x = (String) raw;
~~~

### 5.4. Mã Java gọi bootstrap thủ công có phải invokedynamic không?

**Không.** Ví dụ dùng Java source để gọi `bootstrap(...)` trong `main`, rồi gọi `site.dynamicInvoker()`. Nó tạo một **free-floating Dynalink call site**, đủ để kiểm thử factory, descriptor, linker và relink.

Để sử dụng **`invokedynamic` thật** trong class file, compiler hoặc bộ sinh bytecode phải emit instruction có bootstrap method handle trỏ tới `DynalinkBootstrapDemo.bootstrap`, symbolic name phù hợp và MethodType `(Object)Object` (hoặc kiểu được hỗ trợ). Khi JVM chạy instruction đó, nó gọi bootstrap theo protocol classfile. Dynalink **không viết class file thay bạn**.

Đây là phân biệt bắt buộc khi học chủ đề “tích hợp vào bootstrap”: **mô hình bootstrap đúng** chưa đồng nghĩa demo Java source đã chứa một custom invokedynamic opcode.

## 6. Từ `DynamicLinker.link` đến guarded invocation và relink

Dynalink không nhất thiết biết type của receiver lúc bootstrap. Sau khi site được gắn relink-and-invoke, lần gọi đầu với receiver cho phép thư viện thực hiện:

1. Tạo `LinkRequest` chứa descriptor, đối số thực tế và thông tin site (ví dụ unstable state).
2. Hỏi `GuardingDynamicLinker` đầu tiên có thể xử lý.
3. Nhận `GuardedInvocation` với invocation MethodHandle và guard MethodHandle tương ứng.
4. Thích ứng type nếu cần qua `LinkerServices` và prelink transformer.
5. Đưa guarded invocation vào `RelinkableCallSite`.
6. Chạy operation; các lần sau qua guard để quyết định có dùng target hiện tại hay relink.

### 6.1. GuardedInvocation chứa những gì?

| Thành phần | Vai trò |
| --- | --- |
| Invocation handle | Thực hiện operation trên receiver/arguments phù hợp |
| Guard handle | Trả boolean; nếu sai thì liên kết hiện tại không phù hợp |
| `SwitchPoint` tùy chọn | Cho phép invalidation ngoài luồng, ví dụ shape cache hoặc cấu hình thay đổi |
| Exception invalidation tùy chọn | Chọn loại lỗi khi xuất hiện cần làm mất hiệu lực liên kết |
| Fallback relink-and-invoke | Đường quay về Dynalink để chọn phương án mới khi guard/invalidation không còn hợp lệ |

Một `GuardedInvocation` không guard/invalidation có thể hợp lệ **vô điều kiện**. Với dynamic object model nhiều types, việc trả invocation vô điều kiện cho một receiver-specific method thường sai: type khác đi vào target có thể gây `ClassCastException` thay vì được relink theo thiết kế.

### 6.2. SimpleRelinkableCallSite và ChainedCallSite

`SimpleRelinkableCallSite` sử dụng **monomorphic inline cache**: thường chỉ giữ một guarded invocation tại một thời điểm. Nếu nhận liên tiếp `Customer` rồi `Employee` rồi `Customer`, nó có thể phải relink nhiều lần do guard type thay đổi.

`ChainedCallSite` sử dụng **polymorphic inline cache**: giữ một chuỗi guarded invocations có giới hạn. Khi receiver khớp một guard đã lưu, call site có thể không phải hỏi lại linker. Trong Java 17, Dynalink cung cấp cả hai trong `jdk.dynalink.support`.

So sánh:

| Tiêu chí | SimpleRelinkableCallSite | ChainedCallSite |
| --- | --- | --- |
| Phương án cached điển hình | Một | Nhiều |
| Đơn giản | Cao | Chuỗi guard phức tạp hơn |
| Call site thường chỉ gặp một type | Phù hợp | Có thể không cần |
| Call site gặp vài type luân phiên | Có thể thrash/relink | Thường đáng thử |
| Bảo đảm nhanh hơn trong mọi trường hợp | Không | Không |
| Kiểu call site cố định | Có | Có |

**Không đoán hiệu năng chỉ từ tên.** Một chain dài có chi phí kiểm tra guard; một monomorphic site có thể rất hiệu quả khi receiver ổn định. Đo trong workload thật với JMH/profiler và quan sát tỷ lệ relink.

### 6.3. Relink không thay MethodType của site

Dù target MethodHandle được thay để hỗ trợ type receiver mới, **`CallSite.type()` vẫn giữ nguyên**. Ví dụ site của bài luôn là `(Object)Object`; đường gọi cho Customer và Employee phải được thích ứng về đúng chữ ký này.

Đây là lý do `CallSiteDescriptor` chứa `MethodType` bất biến của vị trí gọi. Relink là thay **implementation target**, không phải thay signature của bytecode call site.

## 7. Linker ngôn ngữ riêng: ưu tiên custom, fallback cho Java objects

Khi object model riêng không tuân JavaBeans, `BeansLinker` không thể tự đoán nội dung private trong object. Ta có thể cung cấp một `GuardingDynamicLinker` riêng và dùng nó **trước** fallback.

Một ví dụ: object `Box` có một chuỗi nội bộ `value`, chỉ có method package-private `text()`, không có `getName()` public. Runtime muốn phép `GET PROPERTY "name"` trên Box trả text; trên Java bean Person thì vẫn gọi `getName()`.

Đây là vai trò lý tưởng của:

~~~java
// Fragment:
factory.setPrioritizedLinker(boxLinker);
DynamicLinker linker = factory.createLinker();
~~~

Linker phải kiểm tra cả **Operation** và **receiver**; nếu không thuộc loại cần xử lý thì return `null` để fallback tiếp tục.

## 8. Ví dụ hoàn chỉnh 2: custom GuardingDynamicLinker có guard

Lưu file **DynalinkCustomLinkerDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkCustomLinkerDemo {
    public static final class Box {
        private final String value;
        public Box(String value) { this.value = value; }
        String text() { return value; }
    }

    public static final class Person {
        private final String name;
        public Person(String name) { this.name = name; }
        public String getName() { return name; }
    }

    private static int customLinks;
    private static final Operation GET_NAME =
            StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY)
                    .named("name");

    private static Object nameFromBox(Object receiver) {
        return ((Box) receiver).text();
    }

    private static boolean isBox(Object receiver) {
        return receiver instanceof Box;
    }

    private static DynamicLinker createLinker() {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodHandle invocation = lookup.findStatic(
                    DynalinkCustomLinkerDemo.class, "nameFromBox",
                    MethodType.methodType(Object.class, Object.class));
            MethodHandle guard = lookup.findStatic(
                    DynalinkCustomLinkerDemo.class, "isBox",
                    MethodType.methodType(boolean.class, Object.class));

            GuardingDynamicLinker boxLinker = (request, services) -> {
                if (!GET_NAME.equals(request.getCallSiteDescriptor().getOperation())
                        || !(request.getReceiver() instanceof Box)) {
                    return null;
                }
                customLinks++;
                return new GuardedInvocation(invocation, guard);
            };

            DynamicLinkerFactory factory = new DynamicLinkerFactory();
            factory.setPrioritizedLinker(boxLinker);
            factory.setSyncOnRelink(true);
            return factory.createLinker();
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static final DynamicLinker LINKER = createLinker();

    public static CallSite bootstrap(MethodHandles.Lookup caller, String name,
                                     MethodType type) {
        if (!"getName".equals(name)) {
            throw new IllegalArgumentException("Unsupported: " + name);
        }
        CallSiteDescriptor descriptor = new CallSiteDescriptor(caller, GET_NAME, type);
        return LINKER.link(new SimpleRelinkableCallSite(descriptor));
    }

    public static void main(String[] args) throws Throwable {
        MethodType type = MethodType.methodType(Object.class, Object.class);
        CallSite site = bootstrap(MethodHandles.lookup(), "getName", type);
        MethodHandle invoke = site.dynamicInvoker();
        System.out.println("beforeLink=" + customLinks);
        System.out.println("box1="
                + (Object) invoke.invokeExact((Object) new Box("alpha")));
        System.out.println("afterBoxLink=" + (customLinks > 0));
        System.out.println("box2="
                + (Object) invoke.invokeExact((Object) new Box("beta")));
        System.out.println("person="
                + (Object) invoke.invokeExact((Object) new Person("Mai")));
        System.out.println("box3="
                + (Object) invoke.invokeExact((Object) new Box("gamma")));
        System.out.println("linkCountPositive=" + (customLinks > 0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkCustomLinkerDemo.java
java DynalinkCustomLinkerDemo
~~~

**Stdout chính xác**:

~~~text
beforeLink=0
box1=alpha
afterBoxLink=true
box2=beta
person=Mai
box3=gamma
linkCountPositive=true
~~~

### 8.1. Tại sao trước lần invoke, customLinks bằng 0?

Trong `createLinker()`, ta tạo MethodHandles và đăng ký lambda `GuardingDynamicLinker`; trong `bootstrap(...)`, `LINKER.link(...)` mới tạo và gắn đường đi **relink-and-invoke**. Chưa có đối số runtime thuộc `Box`, nên custom linker chưa tạo `GuardedInvocation` cho Box.

Dòng `beforeLink=0` là bằng chứng thực hành về **lazy link** trong demo. Sau lần invoke với Box đầu, `afterBoxLink=true` cho thấy `getGuardedInvocation` đã được hỏi ít nhất một lần.

Không dùng counter này để kết luận rằng mọi site/VM bắt buộc có đúng một lời gọi linker: một guard miss, invalidation hoặc chiến lược cache có thể khiến callback được hỏi nhiều lần.

### 8.2. Vì sao custom linker phải trả null cho Person?

Code kiểm tra:

~~~java
// Fragment từ GuardingDynamicLinker lambda:
if (!GET_NAME.equals(request.getCallSiteDescriptor().getOperation())
        || !(request.getReceiver() instanceof Box)) {
    return null;
}
~~~

Nếu operation không đúng hoặc receiver không phải `Box`, linker nhường quyền cho phần tiếp theo của pipeline. `Person` là Java bean public có `getName()`, nên default `BeansLinker` có thể xử lý. Output `person=Mai` chứng minh custom + fallback cùng làm việc trên **một call site**.

Một lỗi nghiêm trọng là viết linker luôn trả một invocation chỉ chấp nhận Box, kể cả khi receiver là Person. Khi đó linker ưu tiên “nuốt” thao tác, gây lỗi cast hoặc hành vi sai thay vì fallback.

### 8.3. Invocation và guard phải tương thích chữ ký

Trong demo:

~~~text
Call site:   (Object)Object
Invocation:  (Object)Object   -> nameFromBox(receiver)
Guard:       (Object)boolean  -> isBox(receiver)
~~~

`GuardedInvocation(invocation,guard)` phù hợp vì guard quyết định khi nào invocation được dùng. Với receiver là Box, method nhận giá trị Box. Khi receiver đổi sang Person, guard false; Dynalink có thể relink bằng BeansLinker.

Không trả guard luôn true nếu invocation cast receiver sang Box. Không tạo guard có chữ ký trả `Object` hoặc có số tham số không tương thích rồi mong Dynalink tự hiểu.

### 8.4. Tại sao các helper method có thể là private?

`nameFromBox` và `isBox` là private static methods của chính class demo. `MethodHandles.lookup()` được gọi trong đúng class có quyền tạo MethodHandle đến chúng. Linker giữ **MethodHandle đã có quyền**, rồi dùng nó trong GuardedInvocation; caller bên ngoài không tự nhiên được quyền tạo handle mới tới private method đó.

Trong runtime thật, việc xuất bản handle và Lookup là vấn đề capability/security. Không lộ quyền truy cập private không cần thiết qua API của ngôn ngữ động.

## 9. Property và element: bổ sung hoạt động GET/SET có tên

Không phải mọi GET/SET là JavaBean property. Dynalink có `StandardNamespace.ELEMENT` và chuẩn named operation, hữu ích cho Map hoặc cấu trúc index.

Ví dụ diễn giải:

~~~java
// Fragment: get element "id" trên một receiver object.
Operation readId = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT).named("id");
MethodType readType = MethodType.methodType(Object.class, Object.class);

// Fragment: set element "id" với một value object.
Operation writeId = StandardOperation.SET
        .withNamespace(StandardNamespace.ELEMENT).named("id");
MethodType writeType =
        MethodType.methodType(void.class, Object.class, Object.class);
~~~

Ở đây:

- `GET ELEMENT named "id"` có một receiver operand, không cần key argument runtime.
- `SET ELEMENT named "id"` nhận receiver và value; tên key nằm trong descriptor.
- Return type SET là `void` theo contract của standard operation.
- Với `Map<String,Object>` Java, default BeansLinker biết cách xử lý element access theo quy tắc có sẵn.

## 10. Ví dụ hoàn chỉnh 3: bootstrap cho named Map element GET/SET

Lưu file **DynalinkMapOperationsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkMapOperationsDemo {
    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    private static CallSite bootstrap(MethodHandles.Lookup caller, String name,
                                      MethodType type) {
        Operation operation = switch (name) {
            case "getId" -> StandardOperation.GET
                    .withNamespace(StandardNamespace.ELEMENT).named("id");
            case "setId" -> StandardOperation.SET
                    .withNamespace(StandardNamespace.ELEMENT).named("id");
            default -> throw new IllegalArgumentException(name);
        };
        return LINKER.link(new SimpleRelinkableCallSite(
                new CallSiteDescriptor(caller, operation, type)));
    }

    public static void main(String[] args) throws Throwable {
        Map<String, Object> values = new HashMap<>();
        values.put("id", "initial");
        CallSite get = bootstrap(MethodHandles.lookup(), "getId",
                MethodType.methodType(Object.class, Object.class));
        CallSite set = bootstrap(MethodHandles.lookup(), "setId",
                MethodType.methodType(void.class, Object.class, Object.class));
        MethodHandle reader = get.dynamicInvoker();
        MethodHandle writer = set.dynamicInvoker();

        System.out.println("getType=" + get.type());
        System.out.println("setType=" + set.type());
        System.out.println("before="
                + (Object) reader.invokeExact((Object) values));
        writer.invokeExact((Object) values, (Object) "updated");
        System.out.println("after="
                + (Object) reader.invokeExact((Object) values));
        System.out.println("mapValue=" + values.get("id"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 DynalinkMapOperationsDemo.java
java DynalinkMapOperationsDemo
~~~

**Stdout chính xác**:

~~~text
getType=(Object)Object
setType=(Object,Object)void
before=initial
after=updated
mapValue=updated
~~~

### 10.1. Điểm cần đọc từ ví dụ Map

`bootstrap` xây dựng **hai descriptors với hai MethodType khác nhau**, tương ứng read và write. Cả hai dùng cùng `LINKER` nhưng có **hai CallSite riêng**: một cho GET, một cho SET.

`writer.invokeExact((Object) values, (Object) "updated")` có return type `void`, đúng với `SET ELEMENT named "id"`. Sau khi write, reader dùng site GET đọc được giá trị mới. Biến Map thực sự đã thay đổi, vì `values.get("id")` cho cùng giá trị.

Nếu bỏ `named("id")` mà vẫn giữ signature hai tham số của SET, bạn sẽ đưa thiếu key operand theo contract `SET ELEMENT` (lúc không đặt tên, signature cần receiver + key + value). Đây là một trong những lỗi dễ gặp nhất khi tự viết bootstrap parser.

### 10.2. Không phải cứ thấy Map là phải dùng PROPERTY

Đối với Map, `ELEMENT` phù hợp hơn nếu semantics của ngôn ngữ là tra bằng key. `PROPERTY` được thiết kế cho property-style access; có thể có những hành vi giao nhau tùy linker, nhưng **không nên dựa vào sự trùng hợp** khi thiết kế language contract.

Khi xây một DSL/ngôn ngữ động, hãy quyết định rõ `obj.name` và `obj["name"]` có cùng semantics không. Nếu không, parse chúng thành operations/namespaces khác nhau, test nhất quán với Map/list/bean và object model tùy chỉnh.

## 11. Invokedynamic thật: bootstrap được gọi bởi ai?

Ba demo trên đều gọi `bootstrap(...)` **trực tiếp** trong Java main, rồi `dynamicInvoker()`. Đây là **thử nghiệm Dynalink thực sự** nhưng **không phát custom invokedynamic bytecode**.

Để JVM tự gọi bootstrap:

1. Compiler hoặc bytecode generator tạo class file có instruction `invokedynamic` ở vị trí operation động.
2. Instruction có **symbolic name**, **method descriptor** và tham chiếu tới một entry trong `BootstrapMethods`.
3. Bootstrap method handle phải trỏ tới phương thức phù hợp, ví dụ `DynalinkBootstrapDemo.bootstrap` trả `CallSite`.
4. JVM thực hiện linkage của vị trí invokedynamic theo JVMS: đưa `Lookup`, name, `MethodType` và static args cho bootstrap khi cần.
5. Bootstrap dựng `CallSiteDescriptor`/`RelinkableCallSite`, gọi `DynamicLinker.link` rồi trả site.
6. Khi instruction được thực thi với receiver runtime, target khởi đầu thực hiện relink-and-invoke rồi đi vào target được chọn.

Sơ đồ classfile mang tính minh họa:

~~~text
Constant pool:
    CONSTANT_InvokeDynamic [bootstrap #N, "getName", "(Ljava/lang/Object;)Ljava/lang/Object;"]

BootstrapMethods:
    #N MethodHandle REF_invokeStatic RuntimeBootstrap.bootstrap(
           MethodHandles.Lookup, String, MethodType)CallSite

Code:
    aload receiver
    invokedynamic getName:(Ljava/lang/Object;)Ljava/lang/Object;
    ... dùng Object kết quả
~~~

**Sơ đồ không phải cú pháp Java source hay bản javap copy nguyên văn.** Nó mô tả ý nghĩa của classfile; index/offset phụ thuộc công cụ emit bytecode. Muốn xem actual custom invokedynamic cần tạo classfile bằng compiler/bytecode library hoặc công cụ sinh bytecode rồi dùng `javap -v -c` kiểm tra.

### 11.1. CallSiteDescriptor không chỉ là ba tham số “cho đẹp”

Khi relink xảy ra **sau bootstrap**, Dynalink cần biết operation và caller context ban đầu, không được tự đoán lại bằng một chuỗi object class name. Descriptor lưu các thông tin bất biến:

- `Lookup` (quyền/lookup context của caller);
- `Operation` (GET PROPERTY named..., SET ELEMENT..., custom operation...);
- `MethodType` (signature mà target ở mọi lần relink phải thỏa).

Đây là lý do không nên viết một call site chỉ chứa `MethodHandle` “nửa đúng” rồi tự gọi `setTarget` rời rạc mà không giữ descriptor. Dynalink cung cấp protocol relink để dùng đúng ngữ cảnh.

### 11.2. Một vị trí bytecode khác một DynamicLinker instance

Một `DynamicLinker` có thể phục vụ **nhiều** call sites. Mỗi vị trí `invokedynamic` được JVM liên kết và có CallSite của nó; site có target/cache riêng. Mọi site có thể cùng thao tác GET "name" nhưng gặp receiver types khác nhau.

Không nên đặt một `CallSite` static duy nhất rồi dùng cho tất cả AST nodes/bytecode sites nếu semantics hoặc cache cần tách. Trong interpreter, có thể giữ **một call site cho mỗi AST node**; trong bytecode compiler, JVM có địa điểm liên kết tương ứng instruction.

### 11.3. Bootstrap có chạy ở mỗi lần gọi không?

Không. Bootstrap tham gia **dynamic linkage** khi JVM liên kết vị trí invokedynamic. Sau khi liên kết thành công, các lần thực thi dùng CallSite target. **Guard miss có thể gây Dynalink relink**, nhưng không có nghĩa JVM lại gọi bootstrap từ đầu cho mỗi receiver mới.

Đây là hai giai đoạn khác nhau:

~~~text
JVM bootstrap linkage: tạo CallSite một lần cho vị trí cần liên kết.
Dynalink runtime relink: cập nhật target của CallSite khi guard không còn phù hợp.
~~~

Nếu bạn tự gọi bootstrap trong Java code nhiều lần, bạn chủ động tạo nhiều free-floating sites; điều đó không chứng minh JVM chạy bootstrap lặp lại ở cùng instruction.

## 12. Giữ chữ ký đúng: MethodType và invokeExact

CallSiteDescriptor có `MethodType` bất biến. Với named GET PROPERTY "name":

~~~java
// Fragment:
MethodType type = MethodType.methodType(Object.class, Object.class);
~~~

là một receiver Object và return Object. Với named SET ELEMENT "id":

~~~java
// Fragment:
MethodType type = MethodType.methodType(void.class, Object.class, Object.class);
~~~

là receiver, value rồi return void. `CallSite` mới được tạo đúng type đó. Mọi target do linker/transformer đưa vào cần phù hợp type của site.

### 12.1. Ba loại mismatch dễ gặp

**(1) Sai số lượng tham số khi thêm NamedOperation.** Nếu `name` đã cố định trong operation, không còn một operand name khi thực thi.

**(2) Sai return type tại `invokeExact`.** Ngay cả khi thực tế Java getter trả `String`, handle site có type `(Object)Object`. Một biểu thức ép kiểu trực tiếp khiến compiler mong String có thể sai; lấy Object rồi cast sau.

**(3) Sai static/instance hoặc kiểu receiver.** Nếu custom invocation MethodHandle chỉ chấp nhận `Box` nhưng site cần `(Object)Object`, linker's guard/adaptation phải xử lý đúng. Trả handle incompatible mà không adapt có thể dẫn đến `WrongMethodTypeException` hoặc lỗi khi relink.

Các phép chuyển đổi của `LinkerServices` có vai trò thích ứng type, nhưng không có quyền sửa mọi yêu cầu type không hợp lệ. Khi debug, in `site.type()`, `descriptor.getMethodType()` và `MethodHandle.type()` của invocation/guard.

### 12.2. Return null và lỗi unsupported operation không giống nhau

`GuardingDynamicLinker.getGuardedInvocation` trả `null` khi **linker cụ thể** không xử lý request; Dynalink sẽ thử các linker khác. Nếu **không linker nào** xử lý được, thao tác động có thể báo lỗi tại lúc link/invoke tùy tình huống, chẳng hạn `NoSuchDynamicMethodException` hoặc exception của runtime.

Trong bootstrap parser của demo, `name="missing"` bị chủ động từ chối sớm bằng `IllegalArgumentException` **trước khi giao Dynalink**. Không đồng nhất lỗi parser do chúng ta chọn với lỗi linker không tìm được operation trong runtime.

## 13. Cách nâng cấp cache từ monomorphic sang polymorphic

Trong ví dụ có Customer/Employee hoặc Box/Person, site nhận nhiều loại receiver. `SimpleRelinkableCallSite` dễ hiểu nhưng nếu receiver types luân phiên nhiều, có thể liên tục bỏ liên kết cũ.

Đối với runtime có vài type thường gặp, có thể thử:

~~~java
// Fragment thay call-site implementation, giữ descriptor và linker:
return LINKER.link(new jdk.dynalink.support.ChainedCallSite(descriptor));
~~~

`ChainedCallSite` duy trì nhiều guarded invocations trong một chuỗi có giới hạn và cố gắng dùng phương án phù hợp trước khi gọi fallback. Cần xem tài liệu version cụ thể cho giới hạn chain và invalidation policy; **không tự chọn chain length tùy tiện**.

Ưu nhược:

- Ít relinks hơn với một số workload có vài receiver types.
- Tăng chi phí kiểm tra chuỗi guard khi không có type match ngay đầu.
- Có thể tăng retention của MethodHandles, classes hoặc dynamic shapes trong cache.
- Khi unstable relink threshold bị vượt, một linker có thể chuyển sang chiến lược ít chuyên biệt hơn, tùy implementation.
- Concurrency vẫn phải được cân nhắc với `setSyncOnRelink` và policy publication.

Một benchmark cần thực tế: tần suất type, số sites, độ dài chain, guard cost và warmup. Không biến “Chained luôn tốt hơn Simple” thành một quy tắc.

## 14. Tự động khám phá linker và liên thông nhiều ngôn ngữ

`DynamicLinkerFactory.setClassLoader` cho biết class loader dùng để tìm các `GuardingDynamicLinkerExporter` thông qua service-loading. Điều này hữu ích khi nhiều language runtimes cùng JVM và muốn link các object của nhau.

Ở mức khái niệm:

~~~text
Runtime A:
  prioritized linker của A
  + autodiscovered linker của B, C...
  + fallback BeansLinker
        |
        v
 DynamicLinker dùng chung trong runtime A
        |
        v
 object thuộc model B -> linker của B có thể liên kết
~~~

Tài liệu nhấn mạnh quyền chủ động của caller đối với class loader/service providers. Trong ứng dụng dùng plugin class loaders, nếu một service exporter không được nạp vì visibility/module metadata, kiểm tra `getAutoLoadingErrors()` và context classloader tại lúc `createLinker()`.

Không mặc định discovery hoạt động chỉ vì có một JAR trên disk. Cần cấu hình service provider, classloader/module layer phù hợp. Cũng không tự động tin mọi exporter chỉ vì ServiceLoader tìm thấy: xem nó như **code có thể chạy trong tiến trình**, cần kiểm soát dependency và trust.

### 14.1. Prioritized, autodiscovered và fallback phải có nghĩa

Linker language runtime ưu tiên nên là **narrow specialist**:
- Chỉ nhận đúng loại operation liên quan tới ngôn ngữ.
- Chỉ nhận receiver thuộc object model của nó.
- Trả `GuardedInvocation` có guard tương thích để kiểm tra receiver ở lời gọi sau.
- Return `null` ngay khi không xử lý được.

Fallback `BeansLinker` đem lại Java interoperability. Nhưng một object model khác Java cần linker riêng; không nên mong `BeansLinker` tự hiểu các member private hoặc dynamic dictionary semantics đặc thù.

## 15. Concurrency, visibility và quản lý vòng đời

### 15.1. Vì sao setSyncOnRelink thường quan trọng với nhiều thread?

`SimpleRelinkableCallSite` là một dạng relinkable mutable call site. Khi target thay đổi, Java Memory Model và cơ chế publication quyết định các thread khác quan sát cập nhật thế nào. `DynamicLinkerFactory.setSyncOnRelink(true)` có tác dụng yêu cầu đồng bộ theo cơ chế `MutableCallSite.syncAll` sau khi relink.

Điều này **không** có nghĩa:
- Toàn bộ thao tác runtime đều atomic.
- Guard tự bảo vệ mọi dữ liệu mutable của receiver.
- Mọi thao tác trên Map trong demo đều thread-safe.
- Không thể có hai thread cùng gây relink.
- Không bao giờ cần khóa/synchronization cho object model riêng.

Tùy bài toán, có thể cần thiết kế publication của state, guard checks và invalidation. Đừng thay policy concurrency chỉ bằng một boolean mà không hiểu data sharing thực tế.

### 15.2. Thay đổi shape có thể cần SwitchPoint

Với Java bean type cố định, guard type có thể đủ. Nhưng ngôn ngữ động có object shape/shape version có thể đổi **trên cùng runtime class**. Guard chỉ kiểm tra `instanceof DynamicObject` có thể tiếp tục true dù property layout đã đổi.

Một linker nâng cao có thể gắn `SwitchPoint` vào `GuardedInvocation`, invalidation khi schema/shape không còn hợp lệ, để call site buộc relink. Không bắt buộc mọi custom linker có SwitchPoint; bạn cần nó khi điều kiện hợp lệ không thể chỉ mô tả bằng receiver type/guard đơn giản.

### 15.3. Cache giữ runtime classes và handles

Một `DynamicLinker`, `CallSite` hoặc `GuardedInvocation` có thể giữ reference tới các `MethodHandle`, Class objects, class loaders và runtime descriptors. Nếu ứng dụng có plugin hot-reload, đừng giữ cache static của mọi phiên bản vô hạn. Thiết kế vòng đời clear references/weak keys khi phù hợp; đồng thời bảo đảm không làm mất liên kết đang được các thread sử dụng.

## 16. Logging, lỗi và an toàn API

### 16.1. Không log mọi receiver trong linker

`getGuardedInvocation` có thể chạy trên đường relink nhạy cảm hiệu năng. Gọi `receiver.toString()` có thể:
- Làm lộ thông tin;
- Có side effects;
- Ném exception của object model;
- Gây lại các thao tác động và recursion ở logger.

Nên log operation, type và lý do relink bằng metadata an toàn. Khi quan sát production, dùng sampling và đo tần suất relink thay vì in toàn bộ arguments.

### 16.2. Xử lý lỗi theo giai đoạn

| Giai đoạn | Triệu chứng | Điều cần kiểm tra |
| --- | --- | --- |
| Factory setup | Service exporter không tải được | ClassLoader, provider configuration, `getAutoLoadingErrors()` |
| Bootstrap parser | `IllegalArgumentException` do tên operation không hỗ trợ | Mapping symbolic name -> Operation |
| Descriptor creation | Type không đúng số operand theo operation | Named vs unnamed, receiver/name/value |
| Initial link | Site không phải `RelinkableCallSite` | Dùng SimpleRelinkable/Chained, không ConstantCallSite |
| First runtime invoke | Không có linker nhận operation/receiver | prioritized/fallback và operation namespace |
| Custom linker | `WrongMethodTypeException`, `ClassCastException` | Invocation/guard signatures, adaptation, receiver |
| Guard miss | Relink rất nhiều | Guard quá hẹp, cache strategy đơn dạng, nhiều types luân phiên |
| Shape changes | Target dùng layout cũ | Guard/switchpoint/invalidation policy |
| Multithread | Các thread quan sát behavior không nhất quán | Publication target, `syncAll`, state concurrency |
| Code security | Callable method ngoài policy | Lookup quyền cao, operation validation, trust boundary |

Một lỗi phổ biến là “bắt tất cả Throwable rồi trả null”: nó xóa mất khác biệt giữa **linker không nhận operation** (return null là hợp đồng) và **linker nhận operation nhưng bản thân code lỗi** (cần xử lý exception như một bug/contract failure). Custom linker nên có chiến lược chẩn đoán rõ ràng.

### 16.3. Đừng cho operation name trở thành đường truy cập tùy ý

Bootstrap method có thể nhận `name` và static args đến từ class file/linker, hoặc code interpreter có thể truyền dữ liệu từ AST. Nếu người dùng tạo được name/receiver tùy ý, bạn cần chính sách truy cập API rõ ràng. Chỉ cấu hình một `BeansLinker` không tạo permission sandbox cho object do người dùng gửi.

Tách “cho phép đọc property A trong DSL” khỏi “đối tượng Java có public getter B”. Có thể dùng mapping whitelist tên operation và giới hạn object models/types trước khi đưa vào Dynalink.

## 17. Một số ngộ nhận cần sửa ngay

**Ngộ nhận 1: `DynamicLinkerFactory` là một bootstrap method.** Sai. Factory cấu hình và tạo DynamicLinker. Bootstrap dùng linker đó để dựng/link CallSite.

**Ngộ nhận 2: `LINKER.link(site)` đã liên kết xong tới một method của Customer.** Chưa nhất thiết. Dynalink gắn đường relink-and-invoke, còn receiver thực tế đến ở lần gọi đầu.

**Ngộ nhận 3: Có `invokedynamic` thì method bootstrap tự được gọi mỗi lần invoke.** Sai. JVM linkage khác với Dynalink relinking về sau.

**Ngộ nhận 4: Dùng `ConstantCallSite` cũng được vì nó extends CallSite.** Sai với `DynamicLinker.link`: API nhận `RelinkableCallSite`, cần cập nhật target cho guard miss.

**Ngộ nhận 5: `GET PROPERTY` đồng nhất `GET ELEMENT`.** Sai. Namespaces mang semantics khác nhau, tùy linker.

**Ngộ nhận 6: `NamedOperation` vẫn cần truyền key ở mỗi lần gọi.** Sai. Tên đã cố định trong descriptor; signature loại bỏ operand name của GET/SET.

**Ngộ nhận 7: Custom linker phải ném lỗi nếu receiver không thuộc nó.** Không. Nếu không xử lý, **trả null** để nhường cho linker khác. Ném lỗi hợp lệ khi chính policy yêu cầu reject hay có lỗi thật, nhưng không phải default fallback behavior.

**Ngộ nhận 8: Guard chỉ kiểm tra type sẽ luôn đúng khi object shape mutable.** Không. Shape/property mapping có thể đổi với cùng class; cân nhắc guard mạnh hơn hoặc invalidation.

**Ngộ nhận 9: `setSyncOnRelink(true)` tự làm mọi object thread-safe.** Không. Nó liên quan publication khi relink, không thay `HashMap` thành concurrent map.

**Ngộ nhận 10: `SimpleRelinkableCallSite` cache mọi class đã gặp.** Không. Nó là monomorphic; nếu cần polymorphic inline cache hãy xem `ChainedCallSite`.

**Ngộ nhận 11: In ra `site.type()` giống `(Object)Object` nghĩa target Java getter bắt buộc trả Object.** Không. Getters có thể trả String/int; linker thích ứng target về call-site type.

**Ngộ nhận 12: Demo gọi `bootstrap(...)` thủ công đã chứng minh class chứa custom `invokedynamic`.** Không. Nó chứng minh pipeline Dynalink chạy được. Để thật sự có opcode, phải emit bytecode và đọc qua `javap`.

## 18. Checklist thiết kế bootstrap Dynalink trong dự án thật

1. **Định nghĩa operation model.** Viết tài liệu DSL: GET/SET PROPERTY/ELEMENT, CALL/NEW, named/unnamed, quyền truy cập.
2. **Thiết lập classloader/module context.** Nếu plugin linkers cần auto-discovery, cấu hình đúng loader và kiểm tra lỗi khi tạo linker.
3. **Tạo DynamicLinkerFactory một lần cho context.** Cấu hình `setPrioritizedLinker`/fallback/sync/threshold có căn cứ.
4. **Gọi createLinker, lưu DynamicLinker.** Không new factory/linker cho mỗi dynamic invocation.
5. **Viết bootstrap method đúng protocol.** `Lookup`, name, `MethodType`; validate name/args.
6. **Map symbolic name sang Operation có kiểm soát.** Dùng `StandardOperation`, `StandardNamespace`, `NamedOperation` hoặc custom operation có tài liệu.
7. **Tạo CallSiteDescriptor.** Lưu caller lookup + operation + immutable type.
8. **Chọn RelinkableCallSite.** Simple nếu monomorphic, Chained nếu cần polymorphic; không dùng ConstantCallSite.
9. **Gọi dynamicLinker.link(callSite) và trả CallSite.** Đừng tự ghi target cuối cùng rồi bỏ mất relink callback.
10. **Viết custom GuardingDynamicLinker đúng domain.** Kiểm tra receiver+operation, return null khi không xử lý, guard phù hợp.
11. **Đo lazy link/relink.** Test lần đầu, cùng type, khác type, quay lại type cũ, invalidation khi shape đổi.
12. **Kiểm tra MethodType.** Named GET/SET có số operand khác unnamed; `invokeExact` cần cả return type.
13. **Test BeansLinker fallback.** Ví dụ Java bean public getter và Map element; tránh cấu hình fallback rỗng ngoài ý muốn.
14. **Concurrency/lifetime.** Xem `setSyncOnRelink`, mutable state, classloader unloading và cache eviction.
15. **Test custom invokedynamic riêng.** Nếu dự án sinh bytecode, kiểm tra `javap -v -c`: bootstrap index, name/descriptor và MethodHandle bootstrap.
16. **Không đoán performance.** Dùng profiler/JMH, đo relink frequency, guard cost, chain cache và hot path.

## 19. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `DynamicLinkerFactory` tạo `CallSite` luôn không?

**Đáp án:** Không. Factory tạo `DynamicLinker`; bootstrap tạo `CallSiteDescriptor` và `RelinkableCallSite`, rồi giao cho `DynamicLinker.link`.

**Câu 2.** Tại sao có thể gọi `link(site)` trước khi biết receiver thực tế?

**Đáp án:** `link` gắn đường relink-and-invoke ban đầu. Receiver xuất hiện ở lần runtime call đầu tiên; lúc đó Dynalink hỏi linker để chọn `GuardedInvocation` phù hợp.

**Câu 3.** Muốn đọc JavaBean property "name" cố định, Operation nào phù hợp?

**Đáp án:** `StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name")`.

**Câu 4.** Named GET PROPERTY có method type bao nhiêu tham số khi chỉ có receiver?

**Đáp án:** Một receiver, ví dụ `(Object)Object`. Tên property đã được giữ trong NamedOperation nên không còn argument name.

**Câu 5.** Custom linker gặp receiver Person không phải Box thì nên làm gì?

**Đáp án:** Trả `null` nếu không xử lý, để các linker còn lại như BeansLinker có thể xử lý.

**Câu 6.** Guard `(Object)boolean` và invocation `(Object)Object` có tương thích call site `(Object)Object` không?

**Đáp án:** Có. Guard được dùng để quyết định có thể dùng invocation, còn invocation trả Object theo call-site type.

**Câu 7.** `SimpleRelinkableCallSite` giữ nhiều guarded invocations không?

**Đáp án:** Nó dùng monomorphic cache, chỉ giữ một phương án hiện tại. `ChainedCallSite` có thể giữ một chuỗi phương án nếu cần.

**Câu 8.** `setUnstableRelinkThreshold(4)` có làm lần relink thứ năm bị từ chối không?

**Đáp án:** Không. Nó ảnh hưởng thông báo unstable khi site được relink đủ nhiều, không cấm relink tiếp.

**Câu 9.** Có thể dùng `ConstantCallSite` với `DynamicLinker.link` không?

**Đáp án:** Không. `DynamicLinker.link` nhận `RelinkableCallSite`, không phải bất kỳ CallSite nào. ConstantCallSite không cho thay target.

**Câu 10.** Nếu code Java source tự gọi `bootstrap(...)`, đã có custom invokedynamic instruction chưa?

**Đáp án:** Chưa. Đó là free-floating call site minh họa. Bytecode generator/compiler phải emit `invokedynamic` trỏ bootstrap thì JVM mới gọi bootstrap theo linkage protocol.

**Câu 11.** `setSyncOnRelink(true)` bảo đảm gì?

**Đáp án:** Yêu cầu đồng bộ publication target sau relink bằng cơ chế `MutableCallSite.syncAll` theo API; không bảo đảm thread safety cho object state hay Map không đồng bộ.

**Câu 12.** Hai vị trí GET name cùng dùng một DynamicLinker có cùng CallSite không?

**Đáp án:** Không bắt buộc. Một linker có thể phục vụ nhiều call sites; mỗi vị trí linked operation có site/cache riêng.

**Câu 13.** `GET ELEMENT named "id"` và `SET ELEMENT named "id"` trong demo có MethodType nào?

**Đáp án:** GET `(Object)Object`; SET `(Object,Object)void`, vì tên key đã được cố định và SET cần receiver + value.

**Câu 14.** Vì sao `getGuardedInvocation` không nên trả invocation vô điều kiện cho mọi type khi code bên trong cast về Box?

**Đáp án:** Khi receiver khác Box, lời gọi có thể gặp `ClassCastException` thay vì được relink. Cần guard bảo vệ liên kết hoặc từ chối request bằng null khi không thuộc domain.

**Câu 15.** Khi nào nên thêm `SwitchPoint` vào GuardedInvocation?

**Đáp án:** Khi liên kết có thể mất hiệu lực do thay đổi ngoài guard, chẳng hạn object layout/shape hoặc cấu hình runtime thay đổi dù receiver class vẫn giữ nguyên.

## Ghi nhớ

- **`DynamicLinkerFactory` tạo `DynamicLinker`; bootstrap tạo `CallSiteDescriptor` và `RelinkableCallSite`; `DynamicLinker.link` gắn cơ chế liên kết.**
- **Liên kết ban đầu là lazy.** Receiver runtime tới ở lần invoke, lúc đó các `GuardingDynamicLinker` được hỏi; guard sai có thể yêu cầu relink.
- **Operation phải đúng semantics và MethodType.** `GET/SET` cần namespace; named operation đã giữ tên nên giảm một operand.
- **`SimpleRelinkableCallSite` là monomorphic; `ChainedCallSite` là polymorphic.** Chọn theo type distribution, không theo phỏng đoán.
- **Đăng ký custom linker bằng `setPrioritizedLinker`** và return null cho receiver/operation không được hỗ trợ để fallback `BeansLinker` làm việc.
- **Tách JVM bootstrap linkage và Dynalink runtime relinking.** Gọi bootstrap bằng Java source không tự tạo opcode `invokedynamic`.
- **Chú ý concurrency, privilege, classloader và invalidation.** Dynalink giúp kết nối operation động, nhưng không thay nhiệm vụ kiểm soát security, state và hiệu năng của runtime.

## Tài liệu tham khảo

- Java SE 17, **jdk.dynalink module overview**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html
- Java SE 17, **DynamicLinkerFactory**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html
- Java SE 17, **DynamicLinker**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html
- Java SE 17, **CallSiteDescriptor**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/CallSiteDescriptor.html
- Java SE 17, **StandardOperation** và **StandardNamespace**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html
- Java SE 17, **Operation** (withNamespace/named): https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/Operation.html
- Java SE 17, **SimpleRelinkableCallSite**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html
- Java SE 17, **ChainedCallSite**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html
- Java SE 17, **GuardedInvocation**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html
- Java SE 17, **GuardingDynamicLinker**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html
- Java Virtual Machine Specification SE 17, **invokedynamic instruction**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
