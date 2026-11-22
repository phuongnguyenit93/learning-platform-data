# getContextClassLoader và setContextClassLoader trong Java

## 1. Mục tiêu và vấn đề thực tế

Trong Java, một lớp thường được nạp thông qua ClassLoader liên quan đến lớp đang yêu cầu nạp, hoặc thông qua loader truyền tường minh cho API. Tuy nhiên, nhiều framework/API cần nạp **implementation của ứng dụng/plugin** từ đoạn code thư viện vốn được định nghĩa bởi loader cấp trên. Chỉ dùng loader định nghĩa thư viện có thể không nhìn thấy các lớp/plugin mà ứng dụng đưa vào.

Java giải quyết một phần nhu cầu này bằng **Thread Context ClassLoader (TCCL)** — một tham chiếu `ClassLoader` gắn với **mỗi đối tượng `Thread`**. Hai API trọng tâm:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(otherLoader);
~~~

- `getContextClassLoader()`: đọc ClassLoader ngữ cảnh hiện được gắn với thread.
- `setContextClassLoader(ClassLoader)`: đặt/thay thế ClassLoader ngữ cảnh của thread.
- Cả hai là **instance methods trên `Thread`**, không phải static methods của `ClassLoader`. `Thread.currentThread()` chỉ chọn thread đang thực thi.
- TCCL là **gợi ý/ngữ cảnh cho những API chủ động sử dụng nó**. Gán TCCL **không tự nạp một class**, **không đổi defining loader** của class đã được định nghĩa và **không tự thêm JAR vào JVM classpath**.

**Mục tiêu hoàn thành bài:** phân biệt TCCL với defining loader và parent delegation; đọc và thay đổi TCCL an toàn; biết lúc nào API thật sự dùng TCCL; hiểu thread inheritance và thread pools; biên dịch/chạy ví dụ Java 17+ với `URLClassLoader` và khôi phục loader bằng `finally`.

## 2. TCCL khác ClassLoader định nghĩa lớp ở đâu?

### 2.1. Ba loại thông tin phải tách biệt

| Khái niệm | Câu hỏi trả lời | Cách quan sát |
|---|---|---|
| **Defining loader** của `SomeType` | Loader nào thực sự định nghĩa runtime class `SomeType`? | `SomeType.class.getClassLoader()` |
| **Parent** của loader | Loader này ủy quyền cho loader nào theo mô hình delegation? | `loader.getParent()` |
| **Thread context loader** | Code đang chạy trong thread này được cung cấp loader ngữ cảnh nào? | `Thread.currentThread().getContextClassLoader()` |

Một ứng dụng có thể có:

~~~text
Application ClassLoader  (L_app)
  |  định nghĩa demo.app.Launcher
  |  định nghĩa interface demo.api.Plugin
  |
  +-- Child URLClassLoader (L_plugin)
         định nghĩa demo.plugin.Implementation

main thread:
  context ClassLoader = L_plugin  (được set tạm thời)

demo.app.Launcher.class.getClassLoader() = L_app (không đổi)
Implementation.class.getClassLoader()   = L_plugin
main.getContextClassLoader()            = L_plugin (trong phạm vi tạm thời)
~~~

Ba phép so sánh có thể cùng đúng mà không mâu thuẫn. **TCCL thuộc thread, không phải thuộc `Class<?>`**. Tên gọi “context loader” cũng không có nghĩa đây là loader **cha** của các loader khác.

### 2.2. Tại sao cần TCCL?

Ví dụ, một thư viện SPI chạy trong một class do platform/application loader định nghĩa muốn tìm implementations do plugin loader nạp. Nếu thư viện chỉ sử dụng defining loader của chính nó, nó có thể không thấy plugin. Thư viện có thể **hỏi thread đang gọi** xem loader ngữ cảnh nào được ứng dụng thiết lập, rồi dùng loader đó tìm provider.

Sơ đồ điều khiển:

~~~text
App gọi thư viện SPI
  -> thư viện đọc Thread.currentThread().getContextClassLoader()
  -> thư viện dùng ClassLoader được cung cấp để tra provider
  -> ứng dụng/plugin chỉ định loader chứa provider tương ứng

TCCL = cầu nối ngữ cảnh khám phá lớp, không phải lệnh đổi định danh lớp.
~~~

Một ví dụ có hợp đồng rõ ràng là `ServiceLoader.load(ServiceType.class)`: overload tiện ích này sử dụng TCCL của thread hiện tại. Nhưng **không phải mọi API nạp lớp của Java đều đọc TCCL**; hãy kiểm tra đúng overload đang gọi.

## 3. `Thread.getContextClassLoader()`

Chữ ký:

~~~java
public ClassLoader getContextClassLoader()
~~~

API trả về ClassLoader ngữ cảnh của **đối tượng Thread được gọi**. Trong code đang chạy, ta thường dùng:

~~~java
Thread current = Thread.currentThread();
ClassLoader tccl = current.getContextClassLoader();
~~~

Các điểm cần nhớ:

1. **Không mặc định luôn bằng application/system loader.** Ở thread ứng dụng chính khi chạy Java thông thường, TCCL ban đầu thường là loader dùng nạp ứng dụng. Nhưng framework, server, thread pool, chương trình nhúng hoặc code khác có thể đã thay giá trị.
2. **Không mặc định bằng defining loader của lớp gọi.** `Library.class.getClassLoader()` và `Thread.currentThread().getContextClassLoader()` có thể khác nhau.
3. **Giá trị `null` là hợp lệ.** Theo `Thread` API, `null` ở TCCL diễn đạt ý nghĩa dùng system class loader (hoặc bootstrap nếu không có system loader) đối với API theo hợp đồng tương ứng. Không được mặc định dùng `tccl.loadClass(...)` khi `tccl == null`.
4. **Đọc TCCL không nạp lớp.** Đây là thao tác lấy tham chiếu, không phải `loadClass`.
5. **Các chính sách bảo mật lịch sử có thể tác động.** Trong môi trường có SecurityManager, `getContextClassLoader()` có thể ném `SecurityException` nếu caller không có quyền phù hợp. SecurityManager bị deprecate trong Java 17; không nên dùng nó làm trọng tâm cho ứng dụng mới.

Ví dụ kiểm tra an toàn:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
if (tccl == null) {
    System.out.println("Thread đang dùng context loader mặc định theo hợp đồng API");
} else {
    System.out.println("TCCL hiện tại là: " + tccl.getClass().getName());
}
~~~

Đoạn trên **chỉ là mã minh họa trong một phương thức**, không phải tệp độc lập. Không nên dùng chuỗi `toString()` hoặc tên class loader để xác lập danh tính runtime; dùng so sánh tham chiếu `==` khi phù hợp.

## 4. `Thread.setContextClassLoader(ClassLoader)`

Chữ ký:

~~~java
public void setContextClassLoader(ClassLoader cl)
~~~

Hàm này **gán** context ClassLoader cho **Thread nhận lời gọi**. Gọi trên thread hiện tại:

~~~java
Thread current = Thread.currentThread();
current.setContextClassLoader(pluginLoader);
~~~

Không có thao tác kiểm tra class/JAR trong `setContextClassLoader`. Chỉ khi code sau đó gọi API **sử dụng TCCL**, chẳng hạn `ServiceLoader.load(MyService.class)` hoặc `Class.forName(name, false, current.getContextClassLoader())`, loader mới có thể được dùng để tìm lớp.

### 4.1. Có thể đặt trên Thread khác không?

Về mặt API, `someThread.setContextClassLoader(cl)` thao tác trên chính đối tượng `someThread`, không bắt buộc phải là current thread. Nhưng thay đổi TCCL của thread đang chạy nơi khác làm tăng nguy cơ race condition, hiểu sai ngữ cảnh và lỗi bảo mật. Hướng phổ biến là **thread tự thiết lập ngữ cảnh của nó** khi thực hiện tác vụ, hoặc cấu hình đúng `ThreadFactory`/executor tại biên tạo thread.

### 4.2. Truyền `null` có ý nghĩa gì?

`current.setContextClassLoader(null)` là hợp lệ theo Java `Thread` API; `null` thể hiện system loader (hoặc bootstrap dự phòng) theo hợp đồng của context loader. Nhưng nếu code riêng của bạn làm:

~~~java
Thread.currentThread().getContextClassLoader().loadClass("demo.Widget");
~~~

thì TCCL `null` khiến expression trên ném `NullPointerException`. Đừng tự diễn giải `null` như một loader object. Với API cho phép loader `null`, hãy đọc hợp đồng chính xác; ví dụ `Class.forName(name, initialize, null)` lại có nghĩa **bootstrap loader**, không giống cách `Thread` diễn đạt giá trị context mặc định.

### 4.3. Quyền truy cập

Ở môi trường Java 17 có SecurityManager, `setContextClassLoader` có thể kiểm tra quyền `RuntimePermission("setContextClassLoader")` và ném `SecurityException`. Điều này không có nghĩa Java mới luôn kiểm tra permission bằng SecurityManager; không nên coi cơ chế này là cơ chế sandbox đáng tin cậy cho code không tin cậy.

### 4.4. Mẫu thiết lập và khôi phục đúng

~~~java
Thread thread = Thread.currentThread();
ClassLoader oldLoader = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi những API thực sự dùng TCCL trong phạm vi này.
} finally {
    thread.setContextClassLoader(oldLoader);
}
~~~

Tại sao **phải có `finally`**?

- Nếu trong phạm vi xảy ra `RuntimeException`, loader ngữ cảnh vẫn phải được khôi phục.
- Thread pool thường dùng lại một worker thread cho nhiều request/tác vụ khác nhau. Loader cũ còn sót lại có thể làm tác vụ sau nhìn thấy provider/JAR của tác vụ trước.
- Một thread sống lâu giữ tham chiếu tới custom loader thông qua TCCL có thể cản trở garbage collection của plugin, deployment hoặc application cũ khi chúng cần được unload.

Nếu `setContextClassLoader(pluginLoader)` có thể ném lỗi **trước khi vào phạm vi thực thi**, đặt lệnh này trong khối `try` như ví dụ là một cách an toàn cho logic khôi phục; khi xử lý `SecurityException` hãy giữ nguyên nguyên nhân. Đừng “cố khôi phục” bằng cách ép mọi exception vào catch rỗng.

## 5. Khi nào TCCL thực sự được sử dụng?

### 5.1. API dùng TCCL: `ServiceLoader.load(service)`

Theo Javadoc Java 17, lời gọi:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);
~~~

tương đương về lựa chọn loader với:

~~~java
ServiceLoader<MyService> providers = ServiceLoader.load(
        MyService.class,
        Thread.currentThread().getContextClassLoader());
~~~

Đây là lý do cốt lõi của TCCL trong môi trường SPI/plugin: provider có thể do loader khác định nghĩa, còn **service interface** cần có type identity mà cả thư viện và plugin đều thống nhất.

**Mã trên là snippet minh họa, cần interface `MyService`**; không phải chương trình độc lập. Dữ liệu provider qua `META-INF/services/<binary-service-name>` dành cho classpath, hoặc qua `provides ... with ...` trong named module (tùy cách deploy/resolve).

Ba overload không giống nhau:

| API | Nguồn/loader dùng tìm provider |
|---|---|
| `ServiceLoader.load(S.class)` | **Context ClassLoader của current thread** |
| `ServiceLoader.load(S.class, explicitLoader)` | **Loader được truyền tường minh** |
| `ServiceLoader.load(layer, S.class)` | **ModuleLayer và các layer tổ tiên** theo hợp đồng JPMS |

Trong named modules, caller cũng phải tuân thủ yêu cầu `uses` với service khi API đòi hỏi; provider phải được khai báo và module resolve phù hợp. Thay đổi TCCL **không tự tạo module layer, không tự thêm `requires`, `uses` hoặc `provides`**.

### 5.2. API không tự đọc TCCL: `Class.forName(String)`

~~~java
Class<?> type = Class.forName("demo.plugin.Widget");
~~~

Theo `Class` Javadoc, overload một tham số dùng **defining loader của lớp đang gọi** (và yêu cầu initialization nếu cần), **không tự lấy TCCL**.

Nếu muốn chủ động dùng loader context:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("demo.plugin.Widget", false, tccl);
~~~

Ở đây **chính bạn đã truyền TCCL vào overload nhận loader**. Lưu ý: nếu `tccl == null` thì overload `Class.forName(String, boolean, ClassLoader)` coi đó là yêu cầu nạp bằng **bootstrap loader**; cần chọn chiến lược null phù hợp cho ứng dụng, không suy rằng nó luôn dùng system loader.

Với ClassLoader API:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
if (tccl != null) {
    Class<?> type = tccl.loadClass("demo.plugin.Widget");
}
~~~

`loadClass` được gọi trên loader được bạn chọn; `ClassLoader.loadClass` không tự đổi “sang TCCL” nếu gọi trên loader khác. Đừng nhầm **API dùng loader truyền tường minh** với **API mặc định đọc context loader**.

### 5.3. Resource lookup cũng phụ thuộc API

Một framework đôi khi dùng:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
java.net.URL resource = tccl == null ? null
        : tccl.getResource("config/plugin.properties");
~~~

Điều này tìm resource bằng loader được chọn. Không nên suy từ `Thread.setContextClassLoader` rằng mọi lời gọi `SomeClass.class.getResource(...)` hoặc `ClassLoader.getSystemResource(...)` sẽ đổi cách tìm: mỗi API có quy tắc chọn loader và lookup riêng.

## 6. Ví dụ Java 17+ độc lập: plugin loader và TCCL

Ví dụ này kiểm chứng đồng thời:

1. Loader ứng dụng **không** tìm được plugin class bằng `Class.forName(String)`.
2. `URLClassLoader` con tìm/định nghĩa được plugin class.
3. `setContextClassLoader` đổi TCCL, cho phép code **chủ động truyền** TCCL vào `Class.forName(name, false, loader)` để tìm plugin.
4. Thread con được tạo trong phạm vi có TCCL mới **kế thừa** ngữ cảnh.
5. `finally` khôi phục TCCL; defining loader của lớp ứng dụng **không đổi**.

### 6.1. Cấu trúc thư mục

~~~text
demo/
  src/
    app/
      TcclDemo.java
    plugin/
      demo/
        plugin/
          Widget.java
  build/
    app/                  # classpath runtime của launcher
    plugin/               # class files chỉ cho URLClassLoader con
~~~

Chạy từ đúng thư mục `demo`. Không thêm `build/plugin` vào classpath system khi chạy; nếu không, minh họa cô lập loader sẽ không còn ý nghĩa.

### 6.2. Tệp `src/plugin/demo/plugin/Widget.java`

~~~java
package demo.plugin;

public final class Widget {
    public static String label() {
        return "plugin-ready";
    }
}
~~~

Plugin class không được compile cùng app. Trong ví dụ, app chỉ biết tên nhị phân `demo.plugin.Widget` tại runtime.

### 6.3. Tệp `src/app/TcclDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class TcclDemo {
    public static void main(String[] args) throws Exception {
        Thread current = Thread.currentThread();
        ClassLoader original = current.getContextClassLoader();
        ClassLoader defining = TcclDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { Path.of("build/plugin").toUri().toURL() },
                defining)) {

            System.out.println("parentIsApp="
                    + (pluginLoader.getParent() == defining));

            try {
                Class.forName("demo.plugin.Widget");
                System.out.println("defaultLookupMissing=false");
            } catch (ClassNotFoundException expected) {
                System.out.println("defaultLookupMissing=true");
            }

            Class<?> pluginClass = Class.forName(
                    "demo.plugin.Widget", false, pluginLoader);
            System.out.println("pluginDefinedByChild="
                    + (pluginClass.getClassLoader() == pluginLoader));

            try {
                current.setContextClassLoader(pluginLoader);
                System.out.println("contextInstalled="
                        + (current.getContextClassLoader() == pluginLoader));

                Class<?> selected = Class.forName(
                        "demo.plugin.Widget",
                        false,
                        current.getContextClassLoader());
                System.out.println("contextLookupMatches="
                        + (selected == pluginClass));

                Thread child = new Thread(() -> System.out.println(
                        "childInherited="
                        + (Thread.currentThread().getContextClassLoader()
                                == pluginLoader)));
                child.start();
                child.join();
            } finally {
                current.setContextClassLoader(original);
            }

            System.out.println("restored="
                    + (current.getContextClassLoader() == original));
            System.out.println("definingLoaderUnchanged="
                    + (TcclDemo.class.getClassLoader() == defining));
        }
    }
}
~~~

Chú ý:

- `defining` được lấy từ `TcclDemo.class` để làm parent cho loader mới. Parent-first delegation vẫn giữ khả năng tìm JDK và shared API classes.
- Plugin chỉ có trong `build/plugin` nên system loader không tìm ra `demo.plugin.Widget` khi gọi overload một tham số từ `TcclDemo`.
- `Class.forName("demo.plugin.Widget", false, pluginLoader)` dùng đúng loader con và không yêu cầu khởi tạo class.
- `Class.forName(..., false, current.getContextClassLoader())` **không tự phát hiện TCCL**; code đã truyền loader một cách tường minh.
- Thread con được **tạo sau khi context của thread chính được đặt**. Nó kế thừa reference đến cùng loader. Nếu thread con tiếp tục sống sau khi parent khôi phục TCCL, reference mà thread con giữ **không tự được khôi phục theo**.

### 6.4. Biên dịch và chạy

Trên Linux/macOS, từ thư mục `demo`:

~~~sh
mkdir -p build/app build/plugin
javac --release 17 -d build/plugin src/plugin/demo/plugin/Widget.java
javac --release 17 -d build/app src/app/TcclDemo.java
java -cp build/app TcclDemo
~~~

Trên Windows PowerShell, tạo thư mục output:

~~~powershell
New-Item -ItemType Directory -Force build/app, build/plugin | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Widget.java
javac --release 17 -d build/app src/app/TcclDemo.java
java -cp build/app TcclDemo
~~~

**Stdout chính xác**, đã biên dịch với `javac --release 17` và kiểm tra bằng JDK:

~~~text
parentIsApp=true
defaultLookupMissing=true
pluginDefinedByChild=true
contextInstalled=true
contextLookupMatches=true
childInherited=true
restored=true
definingLoaderUnchanged=true
~~~

### 6.5. Phân tích kết quả

| Output | Điều được chứng minh |
|---|---|
| `parentIsApp=true` | Loader con có `TcclDemo` defining loader làm parent |
| `defaultLookupMissing=true` | `Class.forName(String)` từ app **không tự dùng** TCCL/loader plugin và không tìm được plugin trong app loader |
| `pluginDefinedByChild=true` | Plugin class được loader con định nghĩa |
| `contextInstalled=true` | TCCL của current thread đã thay đổi |
| `contextLookupMatches=true` | Đọc TCCL và truyền vào overload nhận loader tìm đúng cùng `Class<?>` |
| `childInherited=true` | Thread mới kế thừa context loader của thread tạo ra nó |
| `restored=true` | `finally` khôi phục reference ban đầu |
| `definingLoaderUnchanged=true` | Thay TCCL **không đổi** loader đã định nghĩa `TcclDemo` |

**Điểm dễ nhầm:** thành công của `contextLookupMatches` không có nghĩa mọi class lookup giờ đều dùng loader con. Chỉ phép tìm đã **chọn/truyền loader con** mới dùng nó.

### 6.6. Ba biến thể kiểm tra

**Biến thể A — Không set TCCL:** bỏ `current.setContextClassLoader(pluginLoader);`. `Class.forName(..., current.getContextClassLoader())` sẽ dùng loader cũ; trong môi trường demo chuẩn không tìm được plugin và ném `ClassNotFoundException`. Đây là lỗi có chủ đích trong biến thể; không phải output của bản gốc.

**Biến thể B — Truyền loader tường minh:** vẫn giữ nguyên context ban đầu, nhưng gọi `Class.forName("demo.plugin.Widget", false, pluginLoader)`. Phép tìm **vẫn thành công** vì caller truyền đúng loader, cho thấy TCCL chỉ cần khi API/convention của bạn chọn sử dụng nó.

**Biến thể C — Tạo child thread trước khi set:** tạo `new Thread(...)` khi TCCL còn là `original`, sau đó mới `setContextClassLoader(pluginLoader)` và `start()` child. Theo quy tắc kế thừa mặc định của `Thread`, child đã nhận context lúc **được tạo**, không phải lúc bắt đầu `start()`. TCCL của child sẽ không tự nhảy theo giá trị mới của parent.

## 7. Thread mới và executor thay đổi ngữ cảnh như thế nào?
Thread mới thông thường thừa hưởng TCCL tại thời điểm **construction**. Do đó, nếu tạo child trong lúc TCCL tạm là plugin loader, child vẫn có thể giữ reference ấy sau khi parent đã khôi phục. Thread pool lại tái sử dụng worker, nên set TCCL ở submitter không bảo đảm tác vụ chạy với loader đó. Khi cần, gói task và thực hiện lấy previous → set plugin loader → chạy → restore trong `finally` trên **worker**; hoặc truyền explicit loader cho API phù hợp. Không đóng plugin loader khi task/provider còn sử dụng nó. Hai bài dành riêng cho inheritance và thread pool cung cấp ví dụ độc lập và các chính sách `ThreadFactory`.
## 8. Giới hạn của hai API và lỗi cần phòng
`setContextClassLoader` không tạo sandbox bảo mật, không bổ sung JAR vào classpath, không đổi module readability/exports/opens và không làm `Class.forName(String)` tự chọn TCCL. Code dùng `getContextClassLoader()` phải xét kết quả `null` trước khi gọi instance method; ý nghĩa `null` khi truyền cho `Class.forName(String, boolean, ClassLoader)` khác quy ước của `Thread`. Nếu code đọc/đặt TCCL bị `SecurityException` trong runtime có cơ chế kiểm soát quyền tương ứng, cần giữ nguyên nguyên nhân và không coi context đã thay đổi thành công. Tránh cache một TCCL của tenant/plugin trong singleton lâu sống.
## 9. So sánh các tình huống

| Biểu thức/tình huống | Có dùng TCCL tự động? | Kết luận |
|---|---|---|
| `Thread.currentThread().getContextClassLoader()` | Đây là thao tác **đọc TCCL** | Trả loader context hoặc `null` |
| `Thread.currentThread().setContextClassLoader(loader)` | Đây là thao tác **gán TCCL** | Không tự load class |
| `SomeType.class.getClassLoader()` | **Không** | Trả defining loader của class |
| `Class.forName("p.Type")` | **Không** | Dựa vào defining loader của caller theo Javadoc |
| `Class.forName("p.Type", false, tccl)` | **Có**, vì **caller truyền** nó | Dùng loader explicit, không yêu cầu khởi tạo |
| `tccl.loadClass("p.Type")` | **Có**, vì gọi trên loader đó | Nếu tccl null cần xử lý trước |
| `ServiceLoader.load(Service.class)` | **Có** | Overload tiện ích lấy TCCL hiện tại |
| `ServiceLoader.load(Service.class, loader)` | **Không tự lấy** | Dùng loader argument |
| `ServiceLoader.load(layer, Service.class)` | **Không theo TCCL mặc định** | Tra provider trong module layer theo API |
| `new Thread(task)` | **Có kế thừa** theo mặc định | Nhận context từ thread tạo lúc construction |
| `executor.submit(task)` | **Không bảo đảm inherit** context thread gửi | Task có thể dùng worker thread được tạo từ trước |

Tại những API dùng TCCL, nếu đã set loader trên thread chính nhưng lại gọi API trên **thread khác**, nó sẽ đọc TCCL **của thread khác**, không đọc “biến global context” của process.

## 10. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| `ServiceLoader` không tìm thấy provider | TCCL hiện tại không nhìn thấy provider config/class, hoặc service metadata/module configuration thiếu | Kiểm tra provider path, `META-INF/services`/`provides`, loader thực tế, `uses` |
| `Class.forName("plugin.X")` thất bại dù set TCCL | Overload một tham số **không tự đọc TCCL** | Dùng overload nhận loader tường minh nếu phù hợp |
| Plugin A chạy được, plugin B gọi sau lại dùng A | Thread pool quên restore context hoặc cache ServiceLoader dùng loader cũ | Bọc task bằng `try/finally`, giới hạn cache theo scope |
| Child thread không thấy loader mới | Thread đã được **tạo trước** khi parent set TCCL, hoặc framework set context riêng | Kiểm tra thời điểm tạo, `ThreadFactory` và worker logic |
| Có `NullPointerException` tại `getContextClassLoader().loadClass(...)` | TCCL có thể null | Kiểm tra null, chọn loader fallback theo contract |
| `ClassCastException` dù class names giống nhau | Hai defining loaders tạo hai runtime types khác nhau | Dùng shared API types từ loader thống nhất |
| `IllegalAccessError` hoặc module access error | Không phải chỉ lỗi loader; có thể do runtime package/JPMS access | Kiểm tra defining loaders, module readability, `exports`/`opens` |
| Plugin không unload sau redeploy | Thread/caches còn giữ loader cũ | Restore TCCL, stop tasks, dọn caches/resource |
| `SecurityException` khi get/set TCCL | Quyền theo môi trường SecurityManager cũ hoặc chính sách framework | Ghi nguyên cause, theo quyền và API hiện hành |

### Checklist tối thiểu trước khi thay TCCL

1. Có thực sự cần TCCL hay API đã nhận loader tường minh?
2. Plugin loader có chứa class/resource/provider cần tìm, và có đúng parent không?
3. Thiết lập sẽ ảnh hưởng **thread nào**, có thread pool hay thread con nào kế thừa không?
4. Đã chụp context cũ của **chính thread đang chạy** chưa?
5. Đã khôi phục trong `finally` kể cả khi code ném exception chưa?
6. Có cache/static field hoặc worker lâu sống giữ reference tới loader/plugin không?
7. Có điều kiện access/module nào cần xử lý độc lập không?

## 11. Bài tập và câu hỏi kiểm tra

1. So sánh `SomeType.class.getClassLoader()` và `Thread.currentThread().getContextClassLoader()`. Khi nào chúng có thể khác nhau?
2. `Thread.setContextClassLoader` có đổi loader đã định nghĩa `SomeType` không?
3. Tại sao `Class.forName(String)` vẫn không tìm được `Widget` ở ví dụ dù loader con có bytecode?
4. Câu lệnh nào trong ví dụ đã chủ động **truyền TCCL** tới API nạp lớp?
5. Vì sao `ServiceLoader.load(MyService.class)` thường được dùng trong bài toán SPI/plugin?
6. `ServiceLoader.load(MyService.class, explicitLoader)` có phải tự động đọc TCCL không?
7. Nếu thread cha đổi TCCL **sau khi** đã tạo thread con nhưng **trước khi** gọi `child.start()`, thread con mặc định giữ loader nào?
8. Vì sao set TCCL ở thread gửi `executor.submit(...)` không bảo đảm task thấy context mới?
9. Điều gì có thể sai nếu plugin loader bị để lại trong TCCL của worker thread sau khi task kết thúc?
10. `getContextClassLoader() == null` có hợp lệ không? Vì sao không được lập tức gọi `.loadClass(...)` trên giá trị đó?
11. Nêu tình huống mà loader được truyền tường minh an toàn và dễ hiểu hơn chỉnh TCCL.
12. Một `ClassCastException` khi giao tiếp giữa host và plugin có thể liên quan defining loaders như thế nào?
13. Giải thích tại sao khối `finally` vẫn cần thiết khi API nạp class hoặc provider có thể ném exception.
14. Muốn unload plugin, chỉ gọi `URLClassLoader.close()` có bảo đảm tất cả class cũ được GC ngay không?
15. Nếu API nạp lớp không dùng TCCL, chỉ thay TCCL có tác dụng gì đối với API đó?

**Tiêu chí hoàn thành:** tự chạy ví dụ và giải thích đủ tám dòng output; phân biệt defining loader, parent và TCCL; nêu đúng API có/không đọc context; sử dụng `try/finally` để tránh rò ngữ cảnh trong thread pool và hiểu quy tắc kế thừa của `new Thread`.

## 12. Tài liệu chuẩn

- [Java SE 17 — `Thread.getContextClassLoader` và `Thread.setContextClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): khai báo phương thức, cơ chế kế thừa và `null`, quyền truy cập.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overload `load(service)` dùng TCCL, overload tường minh/layer, lưu ý cache/provider.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): cách chọn loader của overload một tham số và ba tham số.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation và `loadClass`.
- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loader theo URL, đóng resource và vòng đời sử dụng.

Bài áp dụng cho Java 17+; ví dụ đã chạy với compiler `--release 17`. Với phiên bản JDK và framework mới, hãy tham khảo hợp đồng API tương ứng, đặc biệt quanh SecurityManager, module layers và các loại threads mới.