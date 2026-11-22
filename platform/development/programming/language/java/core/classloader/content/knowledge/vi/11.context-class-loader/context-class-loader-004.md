# Lựa chọn loader tường minh thay vì phụ thuộc ngầm vào luồng

## 1. Tại sao phải chọn ClassLoader?

Trong JVM, một class được định danh bởi **binary name và defining class loader**. Hai class cùng tên `com.example.Plugin` có thể là hai runtime types khác nhau nếu do hai defining loaders khác nhau định nghĩa. Vì vậy, câu hỏi “nạp class nào?” luôn có thêm phần “nạp **qua loader nào**?”.

Java cung cấp **thread context class loader (TCCL)** qua `Thread.currentThread().getContextClassLoader()`. TCCL giúp code thư viện/framework tìm implementation và resources theo ngữ cảnh thread đang chạy, nhất là khi implementation nằm ở loader con mà thư viện ở loader cha không tự nhìn thấy. Tuy nhiên, giá trị đó **thay đổi được**, được gắn với thread và có thể khác khi code chạy trong executor, callback, application server hoặc plugin runtime.

Khi biết rõ class, resource hoặc provider thuộc artifact/module/plugin nào, nên cân nhắc **chọn loader tường minh** và truyền nó cho API:

```java
ClassLoader pluginLoader = /* loader do plugin manager cung cấp */;
Class<?> implementation =
        Class.forName("com.example.PluginImpl", false, pluginLoader);
```

Đây là **mã minh họa**, cần thay `pluginLoader` bằng một biến đã được khai báo thực tế. `false` không yêu cầu initialization; loader phải thấy được class được hỏi. Tư tưởng là đưa dependency về loader vào input của component thay vì suy đoán từ TCCL hiện tại.

> TCCL không sai. Nó thích hợp khi framework **cố ý định nghĩa lookup theo context của thread**. Vấn đề là dùng nó như một mặc định vô thức khi thực chất đã có loader sở hữu đúng định nghĩa cần dùng.

## 2. TCCL khác defining loader như thế nào?

| Khái niệm | Lấy từ đâu? | Ý nghĩa |
|---|---|---|
| **Defining loader** | `SomeType.class.getClassLoader()` | Loader định nghĩa runtime class `SomeType`; đã định nghĩa thì identity không đổi |
| **TCCL** | `Thread.currentThread().getContextClassLoader()` | Loader được gắn với ngữ cảnh thread, có thể được thay đổi |
| **System loader** | `ClassLoader.getSystemClassLoader()` | Loader hệ thống theo cấu hình JVM; không tự động chứa mọi plugin |
| **Loader truyền tường minh** | Biến `loader` do caller/factory cung cấp | Quyết định đường tra cứu riêng cho yêu cầu |
| **Bootstrap loader** | Thường biểu diễn bằng `null` tại các API dành cho nó | Cơ chế nạp class nền tảng của JVM |

Đổi TCCL không làm `SomeType.class.getClassLoader()` thay đổi, không định nghĩa lại class đã có và không biến object thuộc loader A thành object thuộc loader B.

Ví dụ:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
ClassLoader custom = new ClassLoader(old) { };

try {
    thread.setContextClassLoader(custom);
    // TCCL của thread là custom;
    // class chứa đoạn code vẫn có defining loader như trước.
} finally {
    thread.setContextClassLoader(old);
}
```

Đây là đoạn minh họa dùng Java 17; mỗi thread giữ TCCL của chính nó. TCCL của thread mới mặc định kế thừa từ thread tạo ra nó nếu không có thiết lập riêng; nó không tự đổi theo parent khi parent đã tạo thread con.

### Vì sao TCCL tồn tại?

Trong **parent delegation** thường gặp, loader con có thể hỏi parent nạp lớp; code do parent định nghĩa không tự nhìn xuống tất cả các class riêng của loader con. Một thư viện nền tảng có thể cần nạp provider do ứng dụng cung cấp mà không có tham chiếu trực tiếp tới loader ứng dụng. TCCL cho phép code ấy lấy loader theo ngữ cảnh.

Đây là ý nghĩa của `ServiceLoader.load(Service.class)`: overload tiện lợi này dùng TCCL. Nó không có nghĩa mọi API reflection/class loading đều tự động dùng TCCL.

## 3. API nào dùng loader nào?

| API | Nguồn quyết định lookup |
|---|---|
| `Class.forName("com.example.Foo")` | **Defining loader của class gọi**, đồng thời yêu cầu initialization |
| `Class.forName("com.example.Foo", false, chosen)` | Loader `chosen` được truyền tường minh |
| `chosen.loadClass("com.example.Foo")` | Loader `chosen` và chiến lược delegation của nó |
| `Foo.class` | Class literal được compiler/JVM liên kết theo ngữ cảnh class hiện tại |
| `Foo.class.getClassLoader()` | Chỉ **đọc defining loader** của runtime type `Foo` |
| `ServiceLoader.load(FooService.class)` | **TCCL** của thread hiện tại |
| `ServiceLoader.load(FooService.class, chosen)` | Loader `chosen` dùng cho việc tìm provider |
| `ServiceLoader.load(layer, FooService.class)` | `ModuleLayer` được chỉ định (và các layer cha theo API) |
| `chosen.getResourceAsStream("config/a.yml")` | Resource lookup qua loader `chosen` |

**Hai điểm hay nhầm:**

1. `Class.forName(String)` không mặc nhiên đọc `Thread.currentThread().getContextClassLoader()`. Theo Java SE 17, overload một tham số tương đương `Class.forName(name, true, currentLoader)`, trong đó `currentLoader` là defining loader của **class gọi**.
2. `ServiceLoader.load(Class<S>)` **có dùng TCCL**; nó tương đương `ServiceLoader.load(service, Thread.currentThread().getContextClassLoader())`.

Vì vậy, chỉ thấy method tên `load` hoặc `forName` là chưa đủ; phải kiểm tra overload thật và contract của API.

### Không tự suy diễn ý nghĩa của null

`null` có ngữ nghĩa **khác nhau** ở các API:

- `Class.forName(name, false, null)`: tìm qua **bootstrap loader**.
- `ClassLoader.getParent() == null`: trong class loader delegation phổ biến, parent API biểu diễn bootstrap.
- `SomeClass.class.getClassLoader() == null`: với ordinary class như `java.lang.String`, defining loader là bootstrap trên JDK thông thường; primitive/void/array có quy tắc riêng.
- `Thread.getContextClassLoader() == null`: tài liệu `Thread` quy định `null` biểu thị **system loader** hoặc bootstrap nếu không có system loader.
- `ServiceLoader.load(service, null)`: tài liệu `ServiceLoader` quy định sử dụng **system loader**, hoặc bootstrap nếu system loader không khả dụng.

Không truyền một loader nullable qua nhiều API với giả định tất cả đều dùng bootstrap. Nếu một anchor class được bootstrap định nghĩa và `getClassLoader()` trả `null`, phải xem lại contract cụ thể của API nhận giá trị ấy.

## 4. Khi dùng TCCL ngầm gây lỗi gì?

Giả sử một library có hàm:

```java
static Class<?> locate(String name)
        throws ClassNotFoundException {
    ClassLoader loader =
            Thread.currentThread().getContextClassLoader();
    return Class.forName(name, false, loader);
}
```

Đây là snippet minh họa phải đặt trong class. Đầu vào `name` giống nhau nhưng kết quả có thể khác:

- Thread chính thường có application loader và tìm thấy class của app.
- Thread được container quản lý có thể mang loader khác; class không tìm thấy.
- Worker thread của executor được tạo từ trước có thể giữ TCCL không liên quan đến request hiện tại.
- Một plugin đổi TCCL trước khi gọi library, làm cùng binary name resolve theo plugin.
- Unit test runner hoặc agent có thể tạo thread với TCCL khác môi trường production.
- Nếu TCCL `null` và code chuyển thẳng sang `Class.forName(name,false,null)`, lookup bị giới hạn theo quy tắc bootstrap của API đó.

Phụ thuộc vào TCCL là **dependency ẩn gắn với thread state**. Logic khó tái hiện và kiểm thử khi chuyển execution sang thread khác.

### TCCL không tự sửa type identity

Nếu loader A và B cùng định nghĩa `api.Message`, kết quả của `A.loadClass("api.Message")` và `B.loadClass("api.Message")` có thể là hai `Class<?>` khác nhau. Hai runtime types đó không tự tương thích chỉ vì cùng binary name.

Đặt TCCL theo A hoặc B có thể ảnh hưởng lookup, nhưng không biến hai class thành một. Với host/plugin chia sẻ interface hoặc DTO, nên định nghĩa **shared API** ở một loader chung và để các plugin resolve về cùng runtime class identity.

## 5. Quy tắc chọn explicit loader theo chủ sở hữu

### 5.1. Class thuộc cùng thư viện với API anchor

Nếu thư viện chứa class `com.example.lib.Helper`, có thể chọn loader của một class đã biết thuộc thư viện:

```java
ClassLoader libraryLoader = LibraryAnchor.class.getClassLoader();
Class<?> helper = Class.forName(
        "com.example.lib.Helper", false, libraryLoader);
```

Đây là mã minh họa: cần `LibraryAnchor` và `Helper` tồn tại. Cách này giảm phụ thuộc vào TCCL của worker hoặc HTTP request.

### 5.2. Implementation do plugin manager nạp

Nếu implementation thuộc plugin, **loader do plugin manager quản lý** mới là lựa chọn rõ ràng:

```java
public final class PluginFactory {
    private final ClassLoader implementationLoader;

    public PluginFactory(ClassLoader implementationLoader) {
        this.implementationLoader =
                java.util.Objects.requireNonNull(implementationLoader);
    }

    public Class<?> loadType(String binaryName)
            throws ClassNotFoundException {
        return Class.forName(binaryName, false, implementationLoader);
    }
}
```

Class này có thể lưu ở `PluginFactory.java`. Constructor thể hiện rõ dependency. Test có thể truyền loader thử nghiệm; khi plugin đóng, registry/factory có thể được giải phóng theo lifecycle.

Nếu plugin implementation sử dụng shared interface, cấu hình parent/delegation để implementation và host nhìn cùng runtime class của interface. Explicit loader chỉ đảm bảo đường lookup **được xác định**, không bỏ qua Java access checks, JPMS hoặc loading constraints.

### 5.3. Resource đi cùng một library

Nếu resource do cùng artifact với `LibraryAnchor` sở hữu, có thể dùng:

```java
try (java.io.InputStream in =
             LibraryAnchor.class.getResourceAsStream(
                     "/config/defaults.properties")) {
    if (in == null) {
        throw new java.io.FileNotFoundException("Resource missing");
    }
    // Đọc dữ liệu cấu hình.
}
```

Đoạn này cần đặt trong method khai báo `throws IOException` hoặc xử lý exception. Nếu resource do plugin sở hữu thì hãy dùng đúng `pluginLoader.getResourceAsStream(...)` thay vì anchor của host. Với named modules, resource encapsulation và quy tắc mở package vẫn được áp dụng.

### 5.4. Service provider trong hệ module

Nếu provider sống trong `ModuleLayer` được ứng dụng tạo và quản lý, có thể dùng:

```java
java.util.ServiceLoader<MyService> providers =
        java.util.ServiceLoader.load(layer, MyService.class);
```

Snippet minh họa cần biến `layer` và interface `MyService`. Trong named modules, cần cấu hình `uses` và `provides` cùng các quan hệ module thích hợp; explicit loader không bỏ qua quy tắc JPMS.

## 6. Java 17 chạy độc lập: TCCL bị đổi nhưng explicit lookup vẫn đúng

Tạo file `ExplicitLoaderDemo.java`:

```java
public class ExplicitLoaderDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();
        ClassLoader app = ExplicitLoaderDemo.class.getClassLoader();
        ClassLoader isolated = new ClassLoader(null) { };

        try {
            thread.setContextClassLoader(isolated);
            System.out.println("TCCL is isolated: "
                    + (thread.getContextClassLoader() == isolated));

            boolean notFound = false;
            try {
                Class.forName("ExplicitLoaderDemo", false,
                        thread.getContextClassLoader());
            } catch (ClassNotFoundException expected) {
                notFound = true;
            }
            System.out.println("TCCL cannot find main: " + notFound);

            Class<?> viaExplicit =
                    Class.forName("ExplicitLoaderDemo", false, app);
            System.out.println("Explicit finds main: "
                    + (viaExplicit == ExplicitLoaderDemo.class));

            Class<?> viaCaller = Class.forName("ExplicitLoaderDemo");
            System.out.println("Caller forName finds main: "
                    + (viaCaller == ExplicitLoaderDemo.class));

            Class<?> viaBootstrap =
                    Class.forName("java.lang.String", false, null);
            System.out.println("Bootstrap finds String: "
                    + (viaBootstrap == String.class));

            System.out.println("Defining loader unchanged: "
                    + (viaExplicit.getClassLoader() == app));
        } finally {
            thread.setContextClassLoader(previous);
        }

        System.out.println("TCCL restored: "
                + (thread.getContextClassLoader() == previous));
    }
}
```

Chạy với JDK 17+, cấu hình class path thông thường:

```bash
javac ExplicitLoaderDemo.java
java ExplicitLoaderDemo
```

Stdout:

```text
TCCL is isolated: true
TCCL cannot find main: true
Explicit finds main: true
Caller forName finds main: true
Bootstrap finds String: true
Defining loader unchanged: true
TCCL restored: true
```

Giải thích:

1. `isolated` là custom loader có parent bằng `null`. Theo thuật toán mặc định, nó có thể ủy quyền tới bootstrap nhưng không tự đọc class ứng dụng trên application class path.
2. Truyền TCCL `isolated` cho `Class.forName` nên `ExplicitLoaderDemo` không được tìm thấy và `notFound` trở thành `true`.
3. Khi truyền `app` rõ ràng, lookup tìm cùng runtime class với `ExplicitLoaderDemo.class`.
4. Overload `Class.forName(String)` dùng loader của **class gọi**, nên không bị việc đổi TCCL làm lỗi.
5. `Class.forName(..., false, null)` minh họa bootstrap lookup của `String`.
6. `finally` phục hồi TCCL; đổi ngữ cảnh không đổi defining loader của `ExplicitLoaderDemo`.

**Điểm đáng nhớ:** cùng thread và cùng tên class nhưng chọn loader khác có thể tạo ra kết quả khác nhau. API nhận loader tường minh giúp caller kiểm soát được điều đó.

## 7. ServiceLoader: so sánh lookup theo TCCL và loader tường minh
`ServiceLoader` là ngoại lệ quan trọng: overload không nhận loader **cố ý** đọc TCCL. Khi biết plugin owner, ta có thể loại bỏ phụ thuộc vào trạng thái ambient của thread:

```java
// Snippet trong method; MyService và pluginLoader đã được khai báo.
ServiceLoader<MyService> ambient = ServiceLoader.load(MyService.class);
ServiceLoader<MyService> explicit =
        ServiceLoader.load(MyService.class, pluginLoader);
```

`ambient` phụ thuộc TCCL của **thread gọi**, còn `explicit` phụ thuộc chính loader truyền vào. Nếu TCCL của executor worker bị đổi, hai lời gọi có thể nhìn tập provider khác nhau. Descriptor `META-INF/services/<binary-service-name>` phải có thể được loader chỉ định tìm thấy; provider phải implement **cùng runtime service API** mà host dùng. Trong named modules có thêm `uses`/`provides` và overload nhận `ModuleLayer`. Đây là cách áp dụng nguyên tắc chọn loader ở phần 5 vào SPI; bài ServiceLoader cuối chương có project mẫu chạy đầy đủ.
## 8. Chọn loader tại ranh giới thread và executor
`new Thread` thường kế thừa TCCL tại lúc tạo. Một executor worker có thể sống lâu trước khi request được submit, nên TCCL của submitter **không** tự được truyền cho từng task. Ví dụ, nếu một plugin factory đã biết `pluginLoader`, nó có thể đưa loader đó vào constructor/parameter của task và gọi `Class.forName(name, false, pluginLoader)` thay vì dựa vào worker TCCL.

Nếu library bắt buộc sử dụng TCCL, đổi nó **bên trong worker đang thực thi** rồi restore `previous` trong `finally`. Không đổi TCCL của submitter rồi mặc định worker sẽ theo. Bài về thread inheritance, pool và finally trình bày wrapper/exception paths chi tiết.
## 9. Cách chuyển TCCL có trách nhiệm

Có những framework cũ chỉ đọc `Thread.currentThread().getContextClassLoader()` mà không có overload nhận loader. Khi đó nên dùng phạm vi hẹp:

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Gọi framework cố ý dùng TCCL ngay trong phạm vi này.
} finally {
    current.setContextClassLoader(previous);
}
```

Đoạn trên minh họa với `pluginLoader` đã được chọn. Các nguyên tắc:

- Lưu và phục hồi TCCL trên **cùng thread**.
- Không giữ TCCL của plugin sau khi hoàn thành công việc.
- Với nested calls, mỗi cấp thay đổi nên lưu giá trị **ngay trước** khi đổi, không tự mặc định context cũ là system loader.
- Nếu tác vụ chuyển thread hoặc asynchronous callback, scope này **không tự lan** sang thread khác.
- Trong server chạy lâu, thread pool, listener, cache hoặc TCCL còn reference tới plugin loader có thể cản garbage collection/class unloading sau redeploy.

Không nên “reset” TCCL bằng `setContextClassLoader(null)` sau mọi callback: đó không nhất thiết là giá trị trước đó, và `null` có semantics theo API `Thread`. Hãy khôi phục chính xác `previous`.

## 10. Plugin factory và dependency injection của loader

Thay vì để mỗi method đọc TCCL, có thể đưa loader vào constructor:

```java
public final class ProviderRegistry {
    private final ClassLoader providerLoader;

    public ProviderRegistry(ClassLoader providerLoader) {
        this.providerLoader =
                java.util.Objects.requireNonNull(providerLoader);
    }

    public <S> java.util.ServiceLoader<S> providers(Class<S> service) {
        return java.util.ServiceLoader.load(service, providerLoader);
    }
}
```

Code này có thể lưu thành `ProviderRegistry.java`. Registry biết loader nào quản lý providers; thread gọi không làm thay lựa chọn.

Lợi ích:

- **Dễ kiểm thử:** test truyền test loader hoặc loader riêng cho fixture.
- **Có thể tái hiện lỗi:** biết chính xác loader đã dùng trong log và stack trace.
- **Hợp với cấu trúc plugin:** mỗi plugin có owner/lifecycle riêng.
- **Tránh nhiễm chéo thread:** không cần đổi TCCL cho những API có explicit overload.
- **Hạn chế leak:** registry có thể được giải phóng cùng plugin thay vì bị lưu vô hạn trong static cache của host.

Nhưng explicit loader **không tự bảo đảm** loader đó nhìn thấy mọi class cần thiết. Cần thiết kế delegation đúng với shared API và các providers.

### Không chọn system loader một cách máy móc

`ClassLoader.getSystemClassLoader()` thường phù hợp với app đơn giản chạy `java -cp`. Trong application server, plugin manager, test runner hoặc runtime modules, implementation có thể nằm ngoài visibility của system loader.

Hãy dựa vào **artifact owner**: API anchor, loader do plugin manager giao, loader của module/layer, hoặc provider loader của registry. Đừng chỉ vì code chạy trong app mà thay mọi TCCL bằng system loader.

## 11. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng xử lý |
|---|---|---|
| Tin `Class.forName(name)` dùng TCCL | Overload một tham số dùng loader của class gọi | Dùng overload ba tham số để chọn loader |
| Gọi `ServiceLoader.load(service)` trong worker mà không xét context | Provider lookup phụ thuộc TCCL worker | Truyền loader tường minh khi có owner |
| Đổi TCCL ở thread submit và cho rằng worker thấy ngay | Worker có TCCL riêng, thường được tái sử dụng | Đặt/restore trong worker hoặc bỏ phụ thuộc TCCL |
| Không restore TCCL | Tác vụ sau có thể dùng context sai, giữ class loader cũ | Dùng `try/finally` |
| Khôi phục bằng `null` thay vì giá trị cũ | Null có contract riêng và có thể thay đổi behavior | Lưu `previous` và restore chính nó |
| Dùng `getSystemClassLoader()` cho mọi provider | Provider có thể do loader khác định nghĩa | Nhận loader từ plugin/module owner |
| Dùng loader của library API để tìm implementation ở child plugin | Parent không mặc định nhìn thấy child classes | Dùng plugin loader được truyền tường minh |
| Có hai bản shared interface cùng binary name | Runtime identities khác nhau | Định nghĩa shared API một lần ở common loader |
| Nghĩ explicit loader bỏ qua module access | JPMS và Java access vẫn áp dụng | Khai báo `uses`, `provides` và kiểm tra exports/opens |
| Giữ `Class<?>` hoặc `ServiceLoader` plugin trong singleton mãi | Reference có thể cản class unloading | Quản lý cache và registry theo plugin lifecycle |
| Coi `null` ở mọi API là bootstrap | `Class.forName`, `ServiceLoader`, `Thread` xử lý khác nhau | Đọc tài liệu từng overload |

### Khi nào vẫn nên dùng TCCL?

TCCL là lựa chọn hợp lệ khi:

- Framework công khai hợp đồng “tìm implementation theo thread context”.
- Caller biết rõ thread nào chạy lookup và đặt đúng context.
- Có cơ chế **restore trong finally** và quản lý lifecycle.
- Không lấy một ServiceLoader theo TCCL của tenant này rồi cache dùng chung vô hạn cho tenant khác.
- Shared API có class identity nhất quán với provider loader.

Trong trường hợp đã biết loader cụ thể ngay khi xây dựng component, explicit loader thường dễ bảo trì hơn.

## 12. Bài tập tự kiểm tra

**Câu 1.** `Class.forName("example.Task")` có tự dùng TCCL không?

**Đáp án:** Không. Overload một tham số dùng loader của class gọi. Muốn truyền loader cụ thể, dùng `Class.forName(name, initialize, loader)`.

**Câu 2.** `ServiceLoader.load(MyService.class)` dùng loader nào?

**Đáp án:** TCCL của thread hiện tại theo contract Java 17. Overload `ServiceLoader.load(MyService.class, chosenLoader)` dùng loader chỉ định.

**Câu 3.** Vì sao cùng method có thể tìm thấy class ở main thread nhưng không thấy ở executor worker?

**Đáp án:** Nếu method chọn TCCL, mỗi thread có context khác nhau; worker có thể được tạo từ trước hoặc do container quản lý.

**Câu 4.** Khi dùng thư viện chỉ hỗ trợ TCCL, phải đổi context ở thread nào?

**Đáp án:** Thread thực sự gọi thư viện và thực hiện lookup, lưu giá trị cũ và restore trong `finally`.

**Câu 5.** Nếu `SomeClass.class.getClassLoader()` và TCCL khác nhau, điều gì xảy ra với defining loader của `SomeClass`?

**Đáp án:** Không thay đổi. Defining loader thuộc runtime class identity; TCCL chỉ là trạng thái lookup theo thread.

**Câu 6.** `Class.forName(name,false,null)` và `ServiceLoader.load(service,null)` có luôn cùng ý nghĩa không?

**Đáp án:** Không. Overload của `Class.forName` dùng bootstrap khi loader null; `ServiceLoader.load(service,null)` dùng system loader, hoặc bootstrap khi không có system loader.

**Câu 7.** Một plugin provider implements interface `api.Plugin` trùng binary name nhưng do loader riêng định nghĩa. Host có chắc cast sang `api.Plugin` của host được không?

**Đáp án:** Không. Cần cùng runtime interface identity, thường bằng cách các plugin ủy quyền shared API type cho common loader.

**Câu 8.** TCCL từ một plugin tồn tại trong worker thread pool sau khi plugin đã dừng có thể gây gì?

**Đáp án:** Có thể giữ loader và class metadata của plugin reachable, làm hot reload/unloading không giải phóng tài nguyên như kỳ vọng.

## 13. Ghi nhớ và tài liệu chính thức

- **TCCL** cung cấp loader theo ngữ cảnh thread; hữu ích cho SPI nhưng dễ thành dependency ẩn trong executor/server/plugin.
- **Explicit loader** là tham số/cấu hình thể hiện chính xác owner của class hoặc provider, hỗ trợ debug và kiểm thử.
- **Class.forName một tham số** dùng loader của class gọi; **ServiceLoader.load một tham số** dùng TCCL.
- **Đổi TCCL phải có phạm vi và restore**, đặc biệt với thread pool tái sử dụng worker.
- **Loader visibility khác runtime type identity**: provider phải dùng cùng shared API runtime types với host.
- **Null không đồng nghĩa nhau ở mọi API**; đọc contract của overload sử dụng.

Nguồn chính thức:

1. [Java SE 17 — Thread.getContextClassLoader và setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
2. [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
3. [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).
4. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
5. [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).