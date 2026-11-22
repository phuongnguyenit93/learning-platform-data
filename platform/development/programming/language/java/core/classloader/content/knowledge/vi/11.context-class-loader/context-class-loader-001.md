# Thread Context ClassLoader (TCCL) là gì?

## 1. Khái niệm và mục đích

**Thread Context ClassLoader (TCCL)** là một tham chiếu `ClassLoader` **được gắn với từng đối tượng `Thread`**, để code đang chạy trong thread đó có thể hỏi: “Trong ngữ cảnh công việc hiện tại, nên dùng class loader nào để tìm class và resource động?”

API trọng tâm:

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Thread.currentThread().setContextClassLoader(loader);
```

TCCL **không phải** một loại `ClassLoader` mới, cũng không phải trường static chung cho mọi thread. Nó là **một tham chiếu có thể đọc/thay đổi trên mỗi Thread**. ClassLoader được gắn vào TCCL vẫn có chính sách nạp của chính nó, chẳng hạn parent-first hoặc child-first tùy implementation.

TCCL ra đời để giải quyết một tình huống phổ biến trong ứng dụng lớn:

- **Framework hoặc thư viện lõi** được định nghĩa bởi loader cha (hoặc loader nền tảng).
- **Plugin, JDBC driver, service provider, thư viện của ứng dụng con** nằm trong loader con.
- Theo **ủy quyền parent-first**, loader cha không thể tự động nhìn xuống toàn bộ class mà loader con định nghĩa.
- Framework cần tìm implementation thuộc **ngữ cảnh ứng dụng/thread gọi nó**, thay vì chỉ tìm trong classpath của chính framework.

TCCL tạo ra một **đường truyền ngữ cảnh từ code phía ứng dụng đến framework**, giúp framework chọn một loader thích hợp khi cần tìm plugin.

Ví dụ khái niệm:

```text
Application / plugin code
   └── đang chạy trên Thread T
       └── TCCL = PluginLoader
                  │
                  ▼
Framework code / ServiceLoader
   └── đọc Thread.currentThread().getContextClassLoader()
       └── dùng PluginLoader tìm provider, resource
           └── PluginLoader có thể thấy các class riêng của plugin
```

**Điểm phải nhớ:** TCCL **chỉ có tác dụng khi API/framework chủ động sử dụng nó**. Java không tự động thay defining loader của mọi class, hay chuyển mọi lời gọi `Class.forName(...)` sang TCCL chỉ vì thread đã có TCCL mới.

## 2. Phân biệt ba loader thường bị nhầm

Cùng trong một dòng code, ba nguồn `ClassLoader` có thể khác nhau:

```java
ClassLoader defining =
        SomeClass.class.getClassLoader();

ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();
```

Đây là **trích đoạn API**; `SomeClass` phải là class cụ thể trong chương trình, không phải một định danh có sẵn trong JDK.

| Khái niệm | Đến từ đâu? | Vai trò |
|---|---|---|
| Defining loader của `SomeClass` | `SomeClass.class.getClassLoader()` | Đã **định nghĩa runtime class** SomeClass |
| TCCL của thread hiện tại | `Thread.currentThread().getContextClassLoader()` | Loader mà **ngữ cảnh thực thi hiện tại muốn API chọn**, khi API hỗ trợ |
| System class loader | `ClassLoader.getSystemClassLoader()` | Loader hệ thống của ứng dụng theo cấu hình runtime |

Điểm tinh tế:

1. TCCL **không cần bằng** defining loader của class đang thực thi.
2. Thay TCCL **không đổi** defining loader của các class đã nạp; class identity vẫn phụ thuộc binary name và defining loader.
3. TCCL có thể trỏ tới custom loader, `URLClassLoader`, một loader ứng dụng, hoặc `null`. Theo hợp đồng `Thread`, giá trị `null` biểu diễn **system class loader (hoặc bootstrap nếu không có system loader)** cho ngữ cảnh thread. **Đừng đánh đồng** giá trị `null` ở TCCL với ý nghĩa `loader=null` trong **`Class.forName(name, initialize, loader)`**, vì overload đó chỉ định **bootstrap** khi `loader=null`.
4. System class loader không bắt buộc có cùng phạm vi nhìn thấy class với loader plugin, đặc biệt trong container có nhiều ứng dụng con.

Ví dụ một thư viện `engine.Framework` do loader cha định nghĩa có thể gọi:

```java
// Trong code framework:
ClassLoader appLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> implementation =
        Class.forName("my.plugin.Provider", false, appLoader);
```

Đây là trích đoạn, cần khai báo `throws ClassNotFoundException` hoặc bắt exception. Framework **chủ động truyền TCCL** vào overload ba tham số. Nếu chỉ gọi `Class.forName("my.plugin.Provider")`, overload một tham số sẽ dùng loader của class **chứa lời gọi** (`engine.Framework`), không tự dùng TCCL.

## 3. Vì sao mô hình ủy quyền bình thường chưa đủ?

Với parent-first delegation, một loader con thường thử:

```text
findLoadedClass
     ↓ nếu chưa có
parent.loadClass
     ↓ nếu parent không tìm thấy
findClass của chính loader con
```

Quan hệ parent-child chủ yếu theo hướng **con ủy quyền lên cha**. Đó là thiết kế hữu ích để class API chung có danh tính nhất quán. Nhưng parent **không tự động ủy quyền ngược xuống mọi child**.

Ví dụ container chạy hai ứng dụng:

```text
                  Bootstrap / Platform
                         │
                 SharedFrameworkLoader
                   /             \
          ApplicationLoader-A   ApplicationLoader-B
             plugin.A             plugin.B
```

Nếu `SharedFrameworkLoader` có class `FrameworkRegistry` và class đó tự tìm `plugin.A` bằng loader của chính nó, có thể nhận `ClassNotFoundException`: loader cha **không thấy class chỉ nằm ở loader con A**.

Nếu một request của ứng dụng A được xử lý trên thread có TCCL = `ApplicationLoader-A`, `FrameworkRegistry` có thể đọc TCCL và yêu cầu A loader tìm provider thích hợp. Với request của B, TCCL có thể là `ApplicationLoader-B`.

Đây là mô hình **context-dependent discovery**. Nó hữu ích trong Java SPI, service provider, JDBC, logging/provider ecosystems, application server, test runner và một số hệ plugin.

**Nhưng TCCL không bảo đảm isolation hoặc bảo mật:** loader được chọn vẫn có quyền nhìn thấy những class/resource theo chính sách và quyền hiện có của nó. Việc lấy code từ plugin không tin cậy cần thêm kiểm soát nguồn bytecode, module, permission, API boundary và vòng đời loader.

## 4. Đọc và gán TCCL trong Thread

`Thread` cung cấp hai instance methods:

```java
public ClassLoader getContextClassLoader();
public void setContextClassLoader(ClassLoader cl);
```

Cách dùng:

```java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(chosenLoader);
    // Gọi framework/service discovery cần loader của ngữ cảnh này.
} finally {
    thread.setContextClassLoader(before);
}
```

Đây là **mẫu code trích đoạn**: `chosenLoader` do chương trình cung cấp. Dùng `try/finally` rất quan trọng vì thread có thể được dùng lại trong thread pool. Nếu để TCCL plugin A còn trên một worker rồi worker xử lý request B, request B có thể vô tình tìm class/resource của A.

### Tính chất phạm vi

- **Theo Thread:** thay TCCL của thread hiện tại không tự đổi TCCL của tất cả thread khác.
- **Có thể đọc/ghi:** các thành phần cùng sử dụng một thread có thể đọc và thay đổi TCCL; nó không phải trường immutable.
- **Không tự “scope” khi thoát method:** Java không tự restore TCCL sau khi method return. Chính code/framework đổi TCCL phải phục hồi đúng ngữ cảnh.
- **Có thể kế thừa:** thread mới thường nhận TCCL ban đầu từ thread tạo nó, với các quy tắc của `Thread`.
- **Không tự truyền qua mọi cơ chế bất đồng bộ:** thread pool có worker từ trước, nên TCCL ở lúc submit task không tự trở thành TCCL của worker chạy task đó.

### Chú ý về `null`

Tài liệu `Thread.getContextClassLoader()` cho phép trả `null`, có nghĩa ngữ cảnh dùng system class loader (hoặc bootstrap khi không có system). Tài liệu `setContextClassLoader(null)` cũng dùng quy ước tương ứng.

Tuy nhiên, nếu **mã của bạn** lấy TCCL và truyền thẳng vào API khác, cần đọc hợp đồng của **API nhận tham số loader**. Ví dụ `Class.forName(name, false, null)` sử dụng bootstrap loader. Vì vậy một framework muốn có fallback về system loader khi TCCL là `null` có thể cần triển khai rõ:

```java
// Trích đoạn: chủ động định nghĩa fallback phù hợp yêu cầu ứng dụng.
ClassLoader cl = Thread.currentThread().getContextClassLoader();
if (cl == null) {
    cl = ClassLoader.getSystemClassLoader();
}
Class<?> type = Class.forName("demo.Provider", false, cl);
```

Đừng dùng một giả định “`null` ở đâu cũng cùng nghĩa” khi ghép nhiều API.

## 5. Ví dụ chạy được 1: TCCL được kế thừa khi tạo thread

Tạo file `ThreadContextDemo.java`, chạy bằng Java 17+:

```java
public class ThreadContextDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread parent = Thread.currentThread();
        ClassLoader original = parent.getContextClassLoader();

        ClassLoader marker = new ClassLoader(original) {
        };

        parent.setContextClassLoader(marker);
        System.out.println("main uses marker: "
                + (parent.getContextClassLoader() == marker));

        // Tạo thread con khi TCCL của main đang là marker.
        Thread child = new Thread(() -> {
            ClassLoader inherited =
                    Thread.currentThread().getContextClassLoader();
            System.out.println("child inherited marker: "
                    + (inherited == marker));
        }, "child");

        // Phục hồi TCCL của main TRƯỚC KHI start thread con.
        parent.setContextClassLoader(original);
        System.out.println("main restored: "
                + (parent.getContextClassLoader() == original));

        child.start();
        child.join();
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadContextDemo.java
java ThreadContextDemo
```

Stdout:

```text
main uses marker: true
main restored: true
child inherited marker: true
```

**Phân tích:**

1. `marker` là một object `ClassLoader` mới có `original` làm parent. Chưa có class plugin nào được định nghĩa; object loader chỉ dùng làm dấu mốc.
2. `main` đổi TCCL sang `marker`.
3. Khi thực hiện `new Thread(...)`, thread con **nhận giá trị TCCL ban đầu** từ thread tạo theo quy tắc kế thừa mặc định. **Thời điểm tạo Thread** quan trọng; không cần đợi đến `start()` để chụp lại TCCL.
4. `main` trở về `original` trước `child.start()`. Thread con vẫn giữ tham chiếu `marker` mà nó nhận trước đó.
5. `child.join()` giúp thứ tự in stdout ổn định trong ví dụ này.

Trong ứng dụng sản xuất, nếu việc tạo thread hoặc chạy code có thể ném exception, hãy bảo đảm restore TCCL trong `finally` chứ không chỉ đặt restore sau một chuỗi lệnh bình thường.

### Có áp dụng với virtual thread không?

JDK 21+ giới thiệu virtual threads ở trạng thái chuẩn. Các API xây dựng thread có tùy chọn liên quan thừa kế inheritable thread-local/context state; không nên kết luận tất cả loại thread, thread builder, executor hay framework đều sao chép TCCL theo cùng một cách bất kể cấu hình. Bài này chọn `new Thread(...)` để minh họa hành vi rõ ràng và chạy được trên **Java 17**.

## 6. ServiceLoader dùng TCCL để tìm provider
Khi service API được định nghĩa ở host nhưng provider chỉ có trong plugin loader, `ServiceLoader.load(Greeting.class)` có thể dùng **TCCL hiện tại** để tìm provider. Đây là điểm nối giữa mô hình parent–child và cơ chế SPI. Ví dụ sau là đoạn minh họa trong một method, giả định host đã có interface `Greeting`, classpath plugin đã có `META-INF/services` tương ứng và biến `pluginLoader`:

```java
Thread current = Thread.currentThread();
ClassLoader before = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
        System.out.println(greeting.message());
    }
} finally {
    current.setContextClassLoader(before);
}
```

Provider phải triển khai **đúng runtime interface** mà host dùng; hai bản interface cùng binary name nhưng do loader khác nhau định nghĩa có thể không tương thích. File descriptor và provider code phải nằm trong vùng mà `pluginLoader` nhìn thấy. `ServiceLoader.load(Greeting.class, pluginLoader)` là lựa chọn tường minh khi không cần thay TCCL. Việc khám phá/khởi tạo provider có thể diễn ra lười khi duyệt, và provider khai báo sai có thể ném `ServiceConfigurationError`; không coi mọi lỗi là “không có provider”. Bài chuyên sâu ở mục cuối chương giải thích đầy đủ cấu trúc project, lệnh biên dịch, output, cache và JPMS.
## 7. ServiceLoader và TCCL: các overload không giống nhau

`ServiceLoader` có nhiều factory methods với phạm vi tìm khác nhau:

| API | Loader/ngữ cảnh tìm |
|---|---|
| `ServiceLoader.load(Service.class)` | **TCCL của thread hiện tại** |
| `ServiceLoader.load(Service.class, loader)` | **ClassLoader truyền tường minh** |
| `ServiceLoader.load(ModuleLayer layer, Service.class)` | Tìm provider trong module layer và các layer cha theo contract |
| `ServiceLoader.loadInstalled(Service.class)` | Provider được cài đặt qua platform loader và tổ tiên phù hợp, không phải loader plugin tùy ý |

TCCL không được suy rộng sang tất cả Java SPI. Mỗi thư viện/provider discovery API phải được kiểm tra riêng: API nào thật sự lấy `Thread.currentThread().getContextClassLoader()`, API nào dùng loader của caller, API nào dùng cấu hình service module/layer?

**Lưu ý về lazy loading:** `ServiceLoader.load(...)` tạo một service loader, nhưng provider có thể chỉ được tìm/nạp/khởi tạo khi iterator, `findFirst()` hoặc stream tiêu thụ chúng. Với một `ServiceLoader` đã tạo, thay TCCL về sau **không có nghĩa** đối tượng ServiceLoader cũ tự động chuyển sang loader mới. Hãy tạo service loader mới theo ngữ cảnh, hoặc dùng overload truyền loader tường minh nếu muốn tránh phụ thuộc TCCL.

Nếu tìm được service configuration nhưng provider class không thể nạp hoặc không implement đúng API runtime class, `ServiceLoader` có thể ném **`ServiceConfigurationError`** thay vì chỉ trả collection trống. Cần phân biệt “không có provider” với “provider được khai báo nhưng không hợp lệ”.

## 8. Quan hệ với ClassLoader.loadClass và Class.forName

Bảng đối chiếu:

| Biểu thức | Chọn loader thế nào? | Có tự yêu cầu khởi tạo class đích? |
|---|---|---|
| `Thread.currentThread().getContextClassLoader()` | Đọc ngữ cảnh của thread | Không nạp class đích |
| `loader.loadClass("p.X")` | Dùng chính `loader` gọi method | Không tự yêu cầu chạy `X.<clinit>` |
| `Class.forName("p.X")` | Defining loader của class **chứa lời gọi** | Có, nếu X chưa khởi tạo |
| `Class.forName("p.X", false, loader)` | Loader truyền tường minh | Không yêu cầu khởi tạo |
| `Class.forName("p.X", true, loader)` | Loader truyền tường minh | Có, nếu X chưa khởi tạo |
| `ServiceLoader.load(S.class)` | TCCL hiện tại | Provider loading/instantiation diễn ra theo việc duyệt service loader |

Đây là khác biệt lớn giữa **class-loading context** và **class initialization**. TCCL không chủ động chạy `<clinit>`; nó có thể **chọn loader** sẽ dùng nếu một API cần tìm class. Lệnh sau mới quyết định việc nạp/link/init theo hợp đồng của nó.

Đặc biệt, `Class.forName(name, boolean, loader)` khi `loader=null` chọn **bootstrap loader**, trong khi `Thread.getContextClassLoader()==null` mang quy ước **system-or-bootstrap context** của Thread API. Luôn xem hợp đồng từng API thay vì truyền `null` xuyên suốt mà không kiểm tra.

## 9. TCCL khi tạo thread và gửi việc vào executor
Với `new Thread(task)` thông thường, TCCL ban đầu của thread con được kế thừa **khi tạo đối tượng Thread**, không đợi `start()`. Đổi TCCL của thread cha sau khi đã tạo child không tự đổi giá trị của child (ví dụ độc lập ở phần 5).

Ngược lại, `executor.submit(task)` thường chạy công việc trên worker **đã tồn tại**; API không hứa chép TCCL của submitter sang worker ở mỗi lần submit. Nếu API bên trong task cần plugin loader, truyền loader như một dependency hoặc bọc `Runnable`/`Callable` để worker lưu previous → set desired → thực hiện → restore trong `finally`. Chính thread chạy task mới là nơi cần đọc và đổi TCCL.

Điều này áp dụng cả khi callback hoặc `CompletableFuture` chuyển execution sang một thread khác. Với virtual threads (Java 21+), cần xét cấu hình kế thừa của thread builder/factory và không nhầm TCCL của virtual thread với carrier thread. Bài “Truyền và kế thừa...” và “Thread pool...” phân tích thời điểm chụp ngữ cảnh, ví dụ pool và wrapper chạy được.
## 10. Vòng đời loader và rủi ro giữ plugin lâu hơn dự kiến
`Thread.contextClassLoader` là **tham chiếu mạnh**. Nếu worker sống lâu giữ TCCL của loader plugin đã ngừng hoạt động, loader ấy vẫn reachable; các class do nó định nghĩa chưa đủ điều kiện unload. Đây là một **đường giữ tham chiếu**, có thể xảy ra đồng thời với cache, `ThreadLocal`, callback hay task queue.

```text
host worker còn sống
  └── TCCL -> loader plugin cũ -> class / resource plugin
```

Cần khôi phục TCCL cũ trong `finally`, ngừng/hủy công việc của plugin và dọn các reference do ứng dụng sở hữu. `URLClassLoader.close()` chỉ đóng tài nguyên liên quan, không ép GC unload class. Đừng reset bừa về `null` hoặc system loader: hãy restore đúng giá trị previous. Bài “Rò rỉ bộ nhớ...” chỉ ra quy trình unload, kiểm tra GC roots và các giới hạn của `System.gc()`.
## 11. An toàn và tính đúng đắn khi dùng TCCL

### 11.1. TCCL là lựa chọn lookup, không phải sandbox

`setContextClassLoader(pluginLoader)` không làm class của plugin tự an toàn hơn, không chặn reflection và không cấp quyền module/package. Nó chỉ làm một số API biết **nên hỏi loader nào**.

Không dùng TCCL làm bằng chứng đáng tin rằng một class được nạp từ nguồn hợp pháp. Provider class được trả về vẫn cần kiểm tra:

- Có triển khai đúng interface/API dùng chung và đúng runtime type không?
- Có được nạp từ JAR/nguồn mong muốn không?
- Có bị parent-first chọn một class khác cùng tên trước không?
- Có tương thích với module access và Java runtime version không?
- Có kiểm soát được constructor/provider initialization side effects không?

### 11.2. Trùng tên API giữa các loader

Giả sử `HostApi` được định nghĩa ở parent, nhưng một plugin loader child-first định nghĩa một bản `HostApi` khác cùng binary name. Provider implement bản API ở child có thể **không assignable** sang `HostApi.class` của host, dù hai class cùng tên trên màn hình. `ServiceLoader` có thể báo provider không phải subtype của service, hoặc code cast thất bại.

Thiết kế thông thường giữ **API giao tiếp chung ở parent**, plugin implementation ở child; chỉ override child-first cho các namespace plugin/private thật sự cần isolation.

### 11.3. Lỗi và cách báo cáo

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `ServiceLoader` không thấy provider | TCCL chưa trỏ đúng plugin loader, thiếu `META-INF/services` hoặc module `provides` | In TCCL, kiểm tra resource và module layer |
| `ClassNotFoundException` từ `Class.forName(name)` | API một tham số dùng loader của caller, không dùng TCCL | Chuyển sang overload truyền loader tường minh nếu phù hợp |
| `ServiceConfigurationError` | Provider class/constructor/service config sai, provider không assignable | Xem cause, provider binary name và class identity |
| `ClassCastException` | Host/plugin định nghĩa trùng API cùng tên qua loaders khác nhau | So `Class<?>` và `getClassLoader()` hai phía |
| Provider sai sau request trước | TCCL bị rò rỉ trên thread pool hoặc có service loader/cache cũ | Restore TCCL, làm rõ vòng đời cache |
| Không giải phóng được plugin khi redeploy | Thread sống lâu giữ TCCL plugin loader hoặc reference khác | Thread dumps, reference paths, close/unregister |
| `SecurityException` khi get/set TCCL | Môi trường legacy có SecurityManager kiểm tra quyền | Xem policy/runtime, không mặc định mọi JVM đều có manager hoạt động |

Đừng bắt `ServiceConfigurationError` rồi trả “không có provider” mà bỏ qua lỗi. Khi provider được khai báo nhưng không thể instantiate/load, đây là **cấu hình hỏng**, khác với không có provider được cung cấp.

## 12. Khi nào nên dùng TCCL, khi nào nên truyền ClassLoader tường minh?

| Thiết kế | Lựa chọn phù hợp |
|---|---|
| Framework chung gọi SPI trong ngữ cảnh request/application hiện tại | TCCL nếu đó là contract được framework/API thiết kế |
| Library tự quản lý plugin và biết chính xác loader | Truyền `ClassLoader` tường minh thường rõ hơn |
| Code có type biết lúc compile, không cần discovery động | Dùng trực tiếp `SomeType.class` hoặc new/type-safe API |
| Task qua executor có context riêng | Wrapper set/restore TCCL ở worker hoặc truyền context tường minh |
| Cần plugin isolation và unload/redeploy | Kiểm soát loader lifecycle, scope TCCL, tránh strong references |
| Ứng dụng JPMS với named modules | Xem thêm `ModuleLayer` và `ServiceLoader.load(layer, service)` |
| Không muốn thay đổi global state theo Thread | Ưu tiên overload nhận loader trực tiếp nếu API cung cấp |

TCCL đặc biệt hữu ích khi một API cấp thấp không nhận tham số loader nhưng cần khám phá implementation theo ứng dụng đang được xử lý. Nhưng vì là trạng thái **ambient** trên thread, nó làm hành vi khó đoán nếu context bị thay đổi ở nơi khác. Khi đã biết loader đúng và API có overload tường minh, truyền thẳng loader thường dễ test và dễ bảo trì hơn.

## 13. Phân biệt TCCL và các khái niệm liên quan

### 13.1. TCCL khác ThreadLocal

TCCL là một thuộc tính chuyên biệt của `Thread` và có API `getContextClassLoader`/`setContextClassLoader`. `ThreadLocal<T>` là cơ chế riêng cho dữ liệu thread-local bất kỳ. TCCL có một số hành vi kế thừa tương ứng với inheritable thread state, nhưng **không nên coi việc đặt TCCL giống hệt tự đặt một ThreadLocal bất kỳ**.

Hãy xem docs của `Thread` và `InheritableThreadLocal` khi thiết kế lan truyền context giữa platform threads, virtual threads hoặc executor.

### 13.2. TCCL khác defining loader của caller

TCCL phục vụ lựa chọn class/resource lookup theo ngữ cảnh thread. Defining loader của caller được cố định khi runtime class được định nghĩa. Đổi TCCL không đổi kết quả `Host.class.getClassLoader()` hay cho phép cast hai runtime classes trùng tên do loaders khác nhau định nghĩa.

### 13.3. TCCL khác module layer

Trong JPMS, module graph, readability, exports/opens và service declarations quyết định một phần khả năng tìm/truy cập provider. Một loader có thể định nghĩa nhiều modules. Chỉ đặt TCCL không bảo đảm service thuộc một module layer độc lập sẽ được tìm trong mọi trường hợp. Nếu kiến trúc tạo module layers riêng, hãy xét overload `ServiceLoader.load(layer, service)` và contract module `uses`/`provides`.

### 13.4. TCCL không tự khởi tạo lớp

Đọc, gán hoặc kế thừa TCCL **không chạy static initializer** của provider. Khi API thực sự nạp, resolve, instantiate hoặc gọi static method, Java mới áp dụng các điều kiện loading/linking/initialization theo đặc tả. Vì vậy nếu thấy `<clinit>` chạy sau `ServiceLoader.findFirst()`, nguyên nhân là **khám phá và instantiate provider**, không phải bản thân lời gọi `setContextClassLoader`.

## 14. Quy trình debug ngắn khi plugin không được tìm thấy
1. Xác định **thread thực sự thực thi** lời gọi tìm provider (đặc biệt khi qua executor).
2. Ghi nhận TCCL ngay tại nơi lookup, cùng defining loader của service interface.
3. Xác minh API sử dụng **TCCL**, loader do caller xác định, tham số loader tường minh hay `ModuleLayer`. `Class.forName(String)` không tự đọc TCCL.
4. Kiểm tra provider descriptor `META-INF/services/...` hoặc `provides`, đường dẫn JAR, shared type identity và chính sách parent delegation.
5. Phân biệt provider không tồn tại với `ServiceConfigurationError`, `ClassNotFoundException`, lỗi module access hoặc cast thất bại.
6. Kiểm tra `finally`, cache/service loader cũ và references còn lại khi redeploy.

Thử `ServiceLoader.load(service, pluginLoader)` để phân biệt lỗi chọn TCCL với lỗi visibility thực tế của plugin loader.
## 15. Câu hỏi tự kiểm tra

1. **TCCL là một subclass `ClassLoader` mới do JVM tạo cho mỗi thread?** Không; đó là tham chiếu `ClassLoader` trên `Thread`.
2. **`Thread.currentThread().setContextClassLoader(pluginLoader)` có đổi defining loader của `Host.class` không?** Không.
3. **Framework class do parent loader định nghĩa cần tìm provider ở child loader; TCCL hữu ích chỗ nào?** Framework có thể chủ động hỏi loader từ ngữ cảnh thread để tìm provider ở child.
4. **`ServiceLoader.load(MyService.class)` chọn loader theo cách nào?** Dùng TCCL của thread hiện tại.
5. **`Class.forName("p.Provider")` có tự dùng TCCL mới set không?** Không; dùng defining loader của caller theo contract overload một tham số.
6. **`Class.forName("p.Provider", false, tccl)` có tự chạy `Provider.<clinit>` không?** Không yêu cầu; `initialize=false`.
7. **Thread con nhận TCCL từ thời điểm `new Thread` hay `start`?** Với constructor mặc định, nó được kế thừa khi thread được tạo, không đợi đến `start`.
8. **Có thể đổi TCCL ở thread main rồi submit task vào thread pool và chắc worker dùng TCCL mới không?** Không; worker có thể đã tồn tại và có context riêng.
9. **Tại sao phải restore TCCL trong `finally`?** Tránh nhiễm ngữ cảnh giữa các task và giữ tham chiếu làm rò rỉ plugin loader.
10. **Nếu `getContextClassLoader() == null`, có thể truyền nguyên `null` vào `Class.forName(name,false,loader)` mà vẫn chắc dùng system loader không?** Không; `forName` dùng bootstrap khi loader null.
11. **Hai plugin loaders định nghĩa hai class API cùng binary name thì ServiceLoader/cast có thể gặp gì?** Type identity khác nhau, provider có thể không assignable, `ServiceConfigurationError` hoặc `ClassCastException`.
12. **Khi đã biết plugin loader và muốn tránh trạng thái ambient, nên dùng API gì?** Overload truyền loader tường minh nếu API có, ví dụ `ServiceLoader.load(service, pluginLoader)`.

## Tài liệu tham khảo chính thức

- [Java SE 21 — Thread.getContextClassLoader / setContextClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): ý nghĩa context ClassLoader, kế thừa từ thread tạo, cách lấy/đặt và `null`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): overload `load(service)` dùng TCCL, service-provider configuration, lazy discovery và `ServiceConfigurationError`.
- [Java SE 21 — Class.forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): phân biệt defining loader của caller với overload truyền explicit loader.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent-first delegation, `loadClass`, `findClass` và identity.
- [JLS — `12.2 Loading, `12.3 Linking, `12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): quan hệ nạp, liên kết và khởi tạo lớp.

**Tóm lại:** TCCL là **loader do ngữ cảnh Thread chỉ định** để API/framework có thể tìm class hoặc provider phù hợp với ứng dụng đang xử lý, đặc biệt khi implementation nằm trong loader con. Nó **không thay defining loader**, **không tự đổi chính sách nạp** và **không tự khởi tạo class**. Khi dùng, phải phân biệt hợp đồng từng API, truyền loader rõ ràng khi cần và luôn khôi phục TCCL sau một scope để tránh sai provider và rò rỉ ClassLoader.
