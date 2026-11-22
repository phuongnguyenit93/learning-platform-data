# Phân biệt loader được yêu cầu với loader thực sự định nghĩa lớp

## 1. Tình huống dễ gây nhầm lẫn

Giả sử ứng dụng có một `ClassLoader` con tên `PluginLoader`:

```java
Class<?> type = pluginLoader.loadClass("com.example.api.Service");
```

Một cách hiểu sai thường gặp là: “Vì đã gọi `pluginLoader.loadClass(...)` nên `Service` được định nghĩa bởi `pluginLoader`.” Trên thực tế, `PluginLoader` có thể **ủy quyền** yêu cầu cho loader cha; loader cha tìm thấy hoặc đã nạp `Service` và trả về **chính định nghĩa lớp của cha**. Loader con chỉ nhận kết quả trả về.

Do đó cần tách ba khái niệm:

1. **Loader được yêu cầu** (*requested loader*): đối tượng `ClassLoader` được gọi để xử lý yêu cầu, chẳng hạn `pluginLoader` ở ví dụ trên.
2. **Loader khởi xướng việc nạp** (*initiating loader*, thuật ngữ JVMS): loader được JVM ghi nhận là bên khởi xướng việc nạp một class/interface cụ thể, có thể được thỏa mãn nhờ ủy quyền cho loader khác. Thuật ngữ này liên quan đến trạng thái nạp và các ràng buộc liên kết trong JVM.
3. **Loader định nghĩa lớp** (*defining loader*): loader thực sự xác lập định nghĩa runtime của class từ dữ liệu nhị phân (thường đi qua `defineClass`), hoặc bootstrap loader do JVM đảm nhiệm đối với các lớp nền tảng. **Đây là loader tham gia định danh kiểu runtime.**

Trong luồng thao tác phổ biến, loader ban đầu được gọi là loader yêu cầu, và việc ủy quyền có thể khiến defining loader nằm ở cha. Không nên đồng nhất khái niệm *initiating loader* trong đặc tả với “bất cứ đối tượng nào có phương thức `loadClass` được gọi trong stack trace”: cần dùng đúng thuật ngữ khi phân tích cơ chế JVM.

### Một quy tắc quan sát đáng nhớ

```java
Class<?> c = requestedLoader.loadClass("some.package.Type");
ClassLoader defining = c.getClassLoader();
```

- `requestedLoader` là nơi lập trình viên gửi yêu cầu.
- `c.getClassLoader()` trả về **defining loader** theo Java API; `null` nghĩa là lớp được bootstrap loader định nghĩa.
- Hai giá trị **có thể khác nhau** mà chương trình vẫn hoàn toàn đúng.
- Với class do bootstrap định nghĩa, không có đối tượng Java `ClassLoader` thông thường để so sánh với `null`.

Các đoạn trên là minh họa, giả định các biến tương ứng đã tồn tại.

## 2. Vì sao requested loader có thể khác defining loader?
Khi kế thừa `ClassLoader.loadClass` mặc định, child kiểm tra `findLoadedClass(name)`, hỏi parent (hoặc bootstrap nếu parent là `null`), rồi mới gọi `findClass(name)` nếu parent không tìm thấy. Vì vậy một lời gọi `child.loadClass("api.Service")` có thể trả **chính `Class<?>` do parent định nghĩa**, không tạo lớp mới ở child.
```text
requested child → parent tìm được api.Service → trả Class của parent
requested child → parent không tìm thấy → child.findClass → có thể define tại child
```
Đường đi này là mặc định; custom loader hoặc JPMS có thể thay đổi chính sách. Khi debug, phân biệt đường gọi `loadClass` với `result.getClassLoader()` (defining loader). `loadClass` không tự yêu cầu initialization.

## 3. Bảng so sánh: nơi nhận yêu cầu, nơi tìm lớp và nơi định nghĩa

| Tình huống | Loader nhận yêu cầu đầu tiên | Loader thực sự định nghĩa | Kết quả |
| --- | --- | --- | --- |
| Child yêu cầu một class API đã có ở application loader | Child | Application loader | Nhận lại cùng `Class` do parent định nghĩa |
| Child yêu cầu `java.lang.String` | Child | Bootstrap loader | `String.class.getClassLoader() == null` |
| Parent không có plugin class, child có JAR chứa class đó | Child | Child, nếu `findClass` định nghĩa thành công | Child thực sự sở hữu định nghĩa plugin class |
| Hai child cùng hỏi parent về một class | Child A và Child B | Parent | Hai kết quả có thể là cùng đối tượng `Class<?>` |
| Hai child độc lập tự định nghĩa cùng binary name | Child A và Child B | A và B tương ứng | Hai kiểu runtime khác nhau |
| Child-first loader ưu tiên bản thư viện riêng | Child | Thường child đối với package được ưu tiên | Có thể tồn tại song song với bản ở parent; cần kiểm soát ranh giới API |

**Không thể suy luận defining loader từ:** vị trí đặt JAR, tên biến `pluginLoader`, giá trị `Thread.currentThread().getContextClassLoader()`, hay một lời gọi `ClassLoader.getSystemClassLoader()`. Phải xem class thực tế trả về và cách nó được định nghĩa.

## 4. Java 17+: thực nghiệm yêu cầu ở child nhưng định nghĩa tại parent

Ví dụ đầy đủ sử dụng một class `SharedApi` được tải trong ứng dụng và một `ProbeLoader` làm loader con. `ProbeLoader` không tự có đường tìm class; nó thử `findClass` chỉ khi parent không thể thỏa mãn yêu cầu. Đây là cách làm rõ parent-first bằng số lần gọi `findClass`.

Lưu `RequestedVsDefiningLoaderDemo.java`:

```java
public class RequestedVsDefiningLoaderDemo {

    public static final class SharedApi {
        public String message() {
            return "shared";
        }
    }

    static final class ProbeLoader extends ClassLoader {
        int localFindCalls;

        ProbeLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            localFindCalls++;
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = SharedApi.class.getClassLoader();
        ProbeLoader child = new ProbeLoader(appLoader);

        Class<?> result = child.loadClass(SharedApi.class.getName());

        System.out.println("requestedIsDefining="
                + (child == result.getClassLoader()));
        System.out.println("sameRuntimeClass="
                + (result == SharedApi.class));
        System.out.println("findClassCalls=" + child.localFindCalls);
        System.out.println("stringFromBootstrap="
                + (child.loadClass("java.lang.String")
                        .getClassLoader() == null));

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();
        try {
            thread.setContextClassLoader(child);
            System.out.println("tcclIsChild="
                    + (thread.getContextClassLoader() == child));
            System.out.println("tcclDefinesSharedApi="
                    + (result.getClassLoader() == child));
        } finally {
            thread.setContextClassLoader(previous);
        }
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac RequestedVsDefiningLoaderDemo.java
java RequestedVsDefiningLoaderDemo
```

Stdout của chương trình khi chạy bình thường:

```text
requestedIsDefining=false
sameRuntimeClass=true
findClassCalls=0
stringFromBootstrap=true
tcclIsChild=true
tcclDefinesSharedApi=false
```

Giải thích từng kết quả:

1. `requestedIsDefining=false`: mặc dù gọi `child.loadClass(...)`, `SharedApi` vẫn do loader ứng dụng (parent trong ví dụ) định nghĩa.
2. `sameRuntimeClass=true`: giá trị trả về chính là `RequestedVsDefiningLoaderDemo.SharedApi.class`, không phải “bản copy” của class.
3. `findClassCalls=0`: parent đã xử lý thành công nên loader con không cần thử định nghĩa ở `findClass`.
4. `stringFromBootstrap=true`: ngay cả khi child nhận yêu cầu, `java.lang.String` được bootstrap loader định nghĩa.
5. `tcclIsChild=true` cho biết **thread context class loader** đã được đặt thành child, nhưng `tcclDefinesSharedApi=false` vì đổi TCCL không làm thay đổi defining loader của class đã nạp.

Phần `finally` khôi phục TCCL để tránh rò ngữ cảnh sang những thao tác khác trên cùng thread, nhất là khi dùng thread pool.

### Điều gì xảy ra nếu gọi một tên không có ở parent?

Vì `ProbeLoader.findClass` chỉ tăng bộ đếm rồi ném `ClassNotFoundException`, yêu cầu như `child.loadClass("example.Missing")` sẽ đi hết parent, thử `findClass` ở child, rồi thất bại. Khi đó `localFindCalls` tăng lên. Với tên `SharedApi`, parent tìm thấy trước nên nhánh `findClass` **không** chạy.

Vì vậy, **có gọi `loadClass` không đồng nghĩa có gọi `defineClass`**; hoạt động cục bộ chỉ xảy ra khi thuật toán nạp chọn tới nơi định nghĩa lớp.

## 5. Khi nào loader được yêu cầu cũng chính là defining loader?

Để thấy trường hợp ngược lại, ta có thể tạo một class chỉ tồn tại trong thư mục JAR/classes riêng của plugin, rồi yêu cầu `URLClassLoader` nạp nó. Khi parent không tìm được, `URLClassLoader` tìm bytecode qua URL và tự định nghĩa class.

Chương trình sau dùng `JavaCompiler` của JDK để tạo class thử nghiệm tạm trong một thư mục riêng, sau đó dùng `URLClassLoader` với parent là platform loader. Không cần tải thư viện bên ngoài.

Lưu `LocalDefinitionDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class LocalDefinitionDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("loader-definition-");
        Path source = directory.resolve("sample/PluginType.java");
        Path compiled = directory.resolve("sample/PluginType.class");

        try {
            Files.createDirectories(source.getParent());
            Files.writeString(source,
                    "package sample; public class PluginType {}");

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("A JDK is required");
            }
            int exit = compiler.run(
                    null, null, null,
                    "-d", directory.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL url = directory.toUri().toURL();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[]{url},
                    ClassLoader.getPlatformClassLoader())) {

                Class<?> pluginType = pluginLoader.loadClass(
                        "sample.PluginType");
                Class<?> again = pluginLoader.loadClass(
                        "sample.PluginType");

                System.out.println("requestedIsDefining="
                        + (pluginType.getClassLoader() == pluginLoader));
                System.out.println("sameClassOnSecondRequest="
                        + (pluginType == again));
                System.out.println("parentDefinesPlugin="
                        + (pluginType.getClassLoader()
                                == ClassLoader.getPlatformClassLoader()));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(compiled);
            Files.deleteIfExists(directory.resolve("sample"));
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy:

```bash
javac LocalDefinitionDemo.java
java LocalDefinitionDemo
```

Stdout khi biên dịch thử nghiệm thành công:

```text
requestedIsDefining=true
sameClassOnSecondRequest=true
parentDefinesPlugin=false
```

Giải thích:

- Platform loader không có class `sample.PluginType` sinh ra trong thư mục tạm.
- `URLClassLoader` tiếp tục tìm trong URL của nó, đọc class file và định nghĩa lớp: lần này **requested loader = defining loader**.
- Gọi `loadClass` lần nữa với cùng loader và cùng binary name trả về cùng định nghĩa `Class`; không tạo một class thứ hai trong cùng loader.
- `close()` trên `URLClassLoader` chỉ giải phóng tài nguyên như JAR/file handle; không làm cho class đã định nghĩa lập tức biến mất. JVM chỉ có thể unload khi điều kiện reachability và lifecycle phù hợp.

**Điều kiện chạy:** phải dùng JDK có hệ thống compiler, không chỉ runtime không có `ToolProvider.getSystemJavaCompiler()`. Chương trình sử dụng API Java 17+ và dọn các file thử nghiệm sau khi đóng loader.

## 6. Đừng suy initiating loader chỉ từ lời gọi Java
Trong JVMS, *initiating loader* là vai trò được JVM ghi nhận trong quá trình loading; nó có thể khác defining loader khi delegation thành công. Nhưng không thể đếm mọi object `ClassLoader` xuất hiện trên call stack rồi tuyên bố tất cả đều là initiating loader. `Class.getClassLoader()` chỉ cho biết **defining loader**; không có API trên `Class` liệt kê toàn bộ initiating loaders.
`findLoadedClass(name)` trong subclass kiểm tra những lớp mà JVM đã ghi nhận đối với loader này, bao gồm những lớp nó initiate thông qua delegation. Đừng xem kết quả ấy như danh sách các lớp child đã tự đọc bytecode và define. Đối với ví dụ ở §4–5, bằng chứng quan sát chắc chắn là **đối tượng `Class<?>` trả về và defining loader của nó**.

## 7. Hậu quả ở ranh giới API plugin
Danh tính class runtime phụ thuộc **(binary name, defining loader)**. Nếu hai child tự định nghĩa `api.Event` từ cùng bytecode, chúng tạo hai runtime types; cast hoặc `instanceof` xuyên ranh giới có thể thất bại. Nếu cả hai nhờ parent tải cùng `api.Event`, chúng nhận một kiểu chung.
Khi thiết kế plugin, đặt API/SPI chung ở loader mà host và child đều có thể sử dụng; triển khai/plugin dependencies được nạp riêng khi cần. Đặc biệt kiểm tra các kiểu trong tham số và giá trị trả về: JVM có thể áp đặt *loading constraints* lúc linking. Hai lớp cùng chuỗi `package` nhưng khác defining loader cũng không mặc nhiên thuộc cùng runtime package, nên package-private access không tự được chia sẻ.
Trong debug, so `Class<?> == Class<?>` và `getClassLoader()` ở hai phía; việc tên class hay đường dẫn JAR giống nhau chưa đủ chứng minh type identity.

## 8. Các API dễ bị nhầm là defining loader

| API/thuộc tính | Thực sự cho biết điều gì |
| --- | --- |
| `requestedLoader.loadClass(name)` | Gửi yêu cầu tới loader này, có thể delegate; kết quả là `Class<?>` |
| `Class.forName(name, false, requestedLoader)` | Yêu cầu tìm lớp bằng loader được chỉ định mà không chủ động initialize; defining loader có thể khác |
| `clazz.getClassLoader()` | **Defining loader** của runtime `clazz`; `null` với bootstrap |
| `clazz.getModule()` | Module runtime của class; module không thay thế câu hỏi defining loader |
| `ClassLoader.getSystemClassLoader()` | System/application loader theo môi trường; không phải “loader của mọi class” |
| `Thread.currentThread().getContextClassLoader()` | Context loader do thread mang theo; hữu ích cho discovery SPI/resources nhưng không tự nói class hiện tại do ai định nghĩa |
| `ClassLoader.getParent()` | Parent được cấu hình cho delegation theo API; không phải bằng chứng parent đã định nghĩa class cụ thể |
| `clazz.getProtectionDomain().getCodeSource()` | Thông tin nguồn code khi có sẵn, có thể `null`; không phải danh tính loader |

Đặc biệt, việc đổi **thread context class loader (TCCL)** không đổi defining loader của bất kỳ class đã định nghĩa trước đó. TCCL chỉ ảnh hưởng các API hoặc thư viện **chủ động chọn** context loader khi tìm lớp, resource hoặc service provider.

Ví dụ minh họa ngắn:

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // API discovery có thể chọn TCCL để tra provider trong plugin.
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

Biến `pluginLoader` và các API discovery cần được chuẩn bị bởi ứng dụng; đoạn này chỉ minh họa mẫu khôi phục TCCL, không phải chương trình độc lập.

## 9. Khi chính sách lookup bị thay đổi
Một custom **child-first** loader có thể ưu tiên bytes riêng cho namespace plugin, nhưng kết quả vẫn phải được kiểm tra qua `result.getClassLoader()`: một số tên có thể delegate về parent, số khác do child định nghĩa. Chỉ chọn child-first cho namespace cần cô lập, bảo toàn core JDK types và shared API. Việc override `loadClass` còn đòi hỏi kiểm soát cache, khóa `getClassLoadingLock`, resolution và các ràng buộc JVM.

## 10. Chẩn đoán thực tế khi loader được yêu cầu khác loader định nghĩa

Khi thấy `ClassCastException`, `NoSuchMethodError`, `ServiceConfigurationError` hoặc behavior lạ trong plugin/container, có thể đi theo trình tự:

1. **Ghi chính xác binary name** đang được yêu cầu, đối tượng loader mà code gọi và đường dẫn code gây lỗi.
2. **Lấy đối tượng Class trả về** nếu quá trình nạp thành công. In `clazz.getName()` và `clazz.getClassLoader()`; nếu so sánh với một kiểu kỳ vọng, in loader của **cả hai bên**.
3. **Kiểm tra quan hệ parent và chính sách delegation.** Một `ChildLoader` có thể đang nhận bản API/lib của cha; loader cha không tự đọc được toàn bộ class riêng của con.
4. **Xem JAR/module thực sự chứa bytecode** tại runtime. `CodeSource` khi không `null` có thể hỗ trợ xác minh; một class cũng có thể đến từ module runtime không biểu diễn thành URL JAR.
5. **Log việc chọn lớp ở custom loader**, chú ý thời điểm `loadClass` nhận yêu cầu, khi nào delegate lên parent, khi nào `findClass` được gọi và khi nào `defineClass` thành công.
6. **Đọc toàn bộ cause của lỗi.** `ClassNotFoundException` thường gắn với API tìm lớp theo tên; `NoClassDefFoundError` có thể do thiếu phụ thuộc lúc liên kết/khởi tạo hoặc class đã khởi tạo lỗi; `LinkageError` có thể chỉ ra xung đột quan hệ loader.
7. **Nếu vấn đề xảy ra khi reload plugin**, so sánh defining loader cũ/mới và các tham chiếu còn giữ class/instance của loader cũ.
8. **Nếu ServiceLoader không tìm được provider**, phân biệt loader đang tìm provider, loader định nghĩa SPI và loader định nghĩa provider. Provider phải thực thi **chính** interface SPI host dùng, không phải một bản cùng tên được plugin tự định nghĩa.

Mẫu phương thức hỗ trợ có thể đặt trong class ứng dụng:

```java
static void describe(Class<?> type) {
    ClassLoader defining = type.getClassLoader();
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + defining);
    System.out.println("module=" + type.getModule().getName());

    java.security.ProtectionDomain pd = type.getProtectionDomain();
    java.security.CodeSource src = pd == null ? null : pd.getCodeSource();
    System.out.println("codeSource="
            + (src == null ? "<unknown>" : src.getLocation()));
}
```

Đây là **phương thức hỗ trợ**, không phải chương trình có `main`. `getModule().getName()` có thể trả về `null` cho unnamed module; `CodeSource` cũng có thể không tồn tại. String của class loader trong log hữu ích nhưng không bảo đảm là định danh duy nhất, ổn định qua các lần chạy.

Có thể kết hợp với công cụ JVM khi môi trường cho phép:

```bash
java -Xlog:class+load=info RequestedVsDefiningLoaderDemo
```

Tùy JVM và mức log, nguồn bytecode có thể hiện trong log; **đừng đồng nhất “source: file X” với defining loader**. Với tiến trình hỗ trợ attach, `jcmd <pid> VM.classloaders` giúp xem cấu trúc class loader; tham số và khả năng hỗ trợ phụ thuộc phiên bản JVM.

## 11. Những nhầm lẫn thường gặp

**“Gọi `child.loadClass` tức `child` định nghĩa class.”** Sai khi class do parent tìm thấy và trả về.

**“`getClassLoader()` trả về loader gần nhất trong call stack.”** Sai: nó trả về defining loader của runtime class.

**“Mọi class đều có ClassLoader object.”** Sai: `String.class.getClassLoader() == null` vì bootstrap loader không biểu diễn bằng một đối tượng Java như các loader thông thường.

**“Hai loader hỏi cùng tên sẽ nhận hai bản copy.”** Sai nếu cả hai delegate tới cùng một định nghĩa ở cha.

**“Hai loader đọc cùng một `.class` từ đĩa thì phải cùng kiểu.”** Sai nếu mỗi loader tự định nghĩa bytecode; runtime type identity còn xét defining loader.

**“TCCL bằng plugin loader tức SPI do plugin loader định nghĩa.”** Sai: TCCL có thể được dùng để tìm provider; SPI thường cần do loader chung định nghĩa.

**“Nhìn `getParent()` đủ để suy ra nơi định nghĩa mọi class.”** Sai: delegation có thể được tùy biến; phải xác minh kết quả thực tế.

**“Đổi loader sau đó có thể đổi defining loader của Class đang tồn tại.”** Sai: một `Class<?>` đã có defining loader gắn với định nghĩa runtime. Muốn định nghĩa mới, phải tạo được định nghĩa mới qua loader phù hợp.

## 12. Bài tập tự kiểm tra

**Câu 1.** `PluginLoader` gọi `loadClass("api.Plugin")`, parent đã định nghĩa `api.Plugin` và trả về. Ai là requested loader, ai là defining loader?

**Trả lời:** Requested loader là `PluginLoader`; defining loader là parent. `clazz.getClassLoader()` cho biết parent.

**Câu 2.** Hai plugin loader cùng delegate `api.Plugin` lên parent. Hai kết quả có phải cùng type identity không?

**Trả lời:** Có, nếu parent trả về cùng định nghĩa runtime `Class`. Khi ấy hai plugin có thể dùng chung SPI.

**Câu 3.** Hai loader tự định nghĩa `internal.Node` từ cùng file `.class`. Có thể cast instance của bản A sang bản B không?

**Trả lời:** Không. Runtime type identity khác vì defining loader khác dù binary name và bytecode giống nhau.

**Câu 4.** `Thread.currentThread().setContextClassLoader(pluginLoader)` có khiến một lớp đã được app loader định nghĩa chuyển sang plugin loader không?

**Trả lời:** Không. TCCL ảnh hưởng việc chọn loader ở một số API từ thời điểm đó; nó không thay đổi defining loader của class đã định nghĩa.

**Câu 5.** Khi gọi `child.loadClass("java.lang.String")`, `getClassLoader()` trả `null`. Có nghĩa việc loadClass thất bại không?

**Trả lời:** Không. `null` biểu thị bootstrap loader đã định nghĩa `String`.

**Câu 6.** App báo dùng phiên bản thư viện khác dự kiến dù plugin đã tạo `URLClassLoader` riêng. Kiểm tra đầu tiên là gì?

**Trả lời:** In defining loader và vị trí bytecode của class thư viện được nạp thực tế; kiểm tra có phải parent-first đã chọn bản ở loader cha trước hay không.

## 13. Kết luận

Để hiểu đúng một lời gọi nạp lớp, luôn tách hai câu hỏi: **“Loader nào được yêu cầu xử lý tên lớp?”** và **“Loader nào thực sự định nghĩa class trả về?”**. Parent delegation cho phép hai đáp án khác nhau một cách bình thường. Danh tính kiểu runtime, khả năng ép kiểu qua plugin và việc cô lập phụ thuộc được quyết định bởi **defining loader**, không đơn thuần bởi đối tượng mà ứng dụng đã gọi `loadClass`.

### Tài liệu chuẩn để đối chiếu

- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Class` API (`getClassLoader`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()
- Java Virtual Machine Specification 17, §5.3 *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification 17, §5.3.4 *Loading Constraints*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
