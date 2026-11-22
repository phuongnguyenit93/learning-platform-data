# Cô lập nhiều phiên bản thư viện giữa các plugin bằng ClassLoader

## 1. Bài toán: hai plugin cần hai bản thư viện có cùng tên lớp

Giả sử ứng dụng host chạy hai plugin:

- **Plugin A** được biên dịch với thư viện `lib.Versioned` bản 1, method `value()` trả `"v1:legacy"`.
- **Plugin B** được biên dịch với thư viện `lib.Versioned` bản 2, method `value()` trả `"v2:modern"`.
- Cả hai đều triển khai interface `api.Plugin` do host cung cấp.

Nếu toàn bộ class được nạp bởi một application class loader duy nhất, cùng binary name `lib.Versioned` không thể đồng thời đại diện cho **hai định nghĩa class khác nhau trong chính loader đó**. Một bản có thể bị dùng thay bản kia; các plugin có thể cho ra kết quả sai hoặc gặp `NoSuchMethodError`/`LinkageError` khi API không tương thích.

Java cho phép cô lập các runtime classes nhờ class loaders riêng:

```text
                       Host / Application loader
                       └── api.Plugin (shared API)
                          /                    \
                         /                      \
                Plugin loader A            Plugin loader B
                ├── plugin.Implementation   ├── plugin.Implementation
                └── lib.Versioned (v1)      └── lib.Versioned (v2)
```

Ở ví dụ này, hai class `lib.Versioned` có **cùng binary name nhưng khác defining class loader**, nên là hai runtime types khác nhau. Ngược lại, cả hai implementation đều dùng **cùng** `api.Plugin` được định nghĩa ở loader chung. Đây là mô hình cốt lõi của **version isolation** trong hệ plugin.

**Mục tiêu không phải ép mọi thứ tách biệt.** Cần cô lập *implementation và thư viện phụ thuộc có phiên bản khác nhau*, nhưng **chia sẻ ổn định interface/DTO/contract đi qua ranh giới host–plugin**.

## 2. Cơ sở JVM: cùng tên lớp chưa đủ tạo cùng kiểu

Theo JVMS, một runtime class/interface được nhận diện bởi:

**Binary name + defining class loader**

Ví dụ:

```text
("lib.Versioned", loaderA) != ("lib.Versioned", loaderB)
("api.Plugin",    appLoader) == ("api.Plugin",    appLoader)
```

Điều này có nghĩa:

- `Class<?> versionA = loaderA.loadClass("lib.Versioned")` và `versionB = loaderB.loadClass("lib.Versioned")` có thể có `getName()` giống nhau.
- Nếu thực sự do loaderA và loaderB định nghĩa riêng, `versionA == versionB` là `false`.
- Một object thuộc `lib.Versioned` của loaderA không tự nhiên cast được thành `lib.Versioned` của loaderB.
- Static fields của hai runtime classes này độc lập; một singleton bằng static field trong thư viện có thể là **một singleton cho mỗi defining loader**, không phải một singleton toàn JVM.
- Một loader thứ ba có thể ủy quyền tới một trong hai loader và nhận chính `Class<?>` của parent, chứ không tự động tạo bản sao.

**Defining loader** là nơi thực sự định nghĩa class; **initiating loader** là loader được JVM ghi nhận đã khởi xướng yêu cầu nạp/resolve class ấy. `clazz.getClassLoader()` phản ánh defining loader đối với class thông thường, không đơn giản trả về object đã gọi `loadClass` gần nhất.

### Tại sao cùng bytes vẫn có thể là hai kiểu?

Ngay cả nếu hai plugin chứa class files byte-for-byte giống nhau, khi hai loaders khác nhau thực sự định nghĩa cùng binary name, JVM vẫn tạo **hai class identities**. Class loading là một phần của hệ thống kiểu Java, không chỉ là cơ chế tìm file.

Ngược lại, hai loaders có tên giống nhau (`getName()` bằng nhau) vẫn có thể là hai objects/defining loaders khác nhau. Loader name là nhãn chẩn đoán, không là khóa định danh runtime class.

## 3. Đâu là shared API, đâu là private dependency?

Hãy quyết định kiến trúc trước khi chọn parent delegation:

| Nhóm class | Nơi nên định nghĩa thông thường | Lý do |
|---|---|---|
| `java.lang.*`, thư viện lõi JVM | Built-in loaders phù hợp | Các plugin dùng chung nền tảng runtime |
| `api.Plugin` và DTO/interface dùng qua host boundary | Shared API loader của host | Host và plugin cần **cùng runtime type identity** |
| `plugin.Implementation` | Plugin loader tương ứng | Có thể có cùng binary name giữa nhiều plugin mà vẫn tách biệt |
| `lib.Versioned` bản 1 | Plugin A loader | Độc lập bản 2 |
| `lib.Versioned` bản 2 | Plugin B loader | Độc lập bản 1 |
| Thư viện thật sự dùng chung và tương thích | Common parent loader nếu đã thống nhất version | Giảm bản sao và tránh classloader leak |
| Thư viện riêng hoặc có nguy cơ xung đột version | Loader riêng của từng plugin | Cho phép version khác nhau cùng tồn tại |

Ví dụ API an toàn qua boundary:

```java
package api;

public interface Plugin {
    String run();
}
```

Chữ ký `String run()` dùng kiểu nền tảng `java.lang.String` do runtime thống nhất, không ép host phải hiểu `lib.Versioned` thuộc plugin A hay B.

**Không nên để shared API của host có kiểu trả về/tham số là thư viện private của plugin**, chẳng hạn:

```java
// Tránh thiết kế kiểu này ở shared API:
lib.Versioned run();
```

Đây là khai báo minh họa, không phải chương trình độc lập. Nếu host và plugin resolve `lib.Versioned` qua hai loaders có định nghĩa khác nhau, JVM có thể gặp **loading constraint violation** ở field/method descriptor khi liên kết, hoặc host không có đúng class cần để biên dịch/chạy.

Thay vào đó, truyền qua boundary các **shared interfaces/DTO**, primitive/String, hoặc dữ liệu được chuyển đổi ở ranh giới như JSON/byte arrays với schema/versioning rõ ràng. Chuyển dữ liệu không đồng nghĩa tự động làm mọi version API tương thích: vẫn cần quản lý schema và hành vi.

## 4. Parent-first có khi đã đủ để cô lập hai thư viện

`URLClassLoader` kế thừa chiến lược `loadClass` mặc định: thông thường **parent-first**. Khi loader con cần một tên class, nó kiểm tra class đã có, hỏi parent, rồi mới tìm trong URLs của chính nó nếu parent không tìm được.

Có thể cô lập các thư viện khác phiên bản bằng **hai URLClassLoader objects riêng** mà **không cần override `loadClass`**, miễn:

1. Class path của **parent không chứa** những class private như `lib.Versioned`.
2. Mỗi plugin loader có đường dẫn riêng chứa phiên bản thư viện tương ứng.
3. Shared API `api.Plugin` được định nghĩa bởi parent và được plugin loaders ủy quyền về cùng định nghĩa.

```text
Parent (classpath: out/api + out/host)
     không có lib.Versioned
          |                         |
          v                         v
Plugin A URLClassLoader      Plugin B URLClassLoader
  out/plugin-a/                out/plugin-b/
  lib.Versioned v1             lib.Versioned v2

Yêu cầu lib.Versioned:
  A -> parent không có -> A tự định nghĩa v1
  B -> parent không có -> B tự định nghĩa v2

Yêu cầu api.Plugin:
  A -> parent trả API chung
  B -> parent trả API chung
```

**Đây thường là điểm bắt đầu dễ bảo trì nhất**: cô lập class path riêng cho mỗi plugin, không phức tạp hóa thuật toán tải lớp nếu không cần.

### Khi nào parent-first không đủ?

Nếu host application class path đã chứa `lib.Versioned` bản 1, parent của cả hai plugin có thể trả về bản 1 **trước khi** plugin B có cơ hội tìm bản 2 trong thư mục riêng.

Hệ quả:

- Plugin B có thể chạy với behavior của v1 thay vì v2.
- Nếu B được biên dịch để gọi method chỉ có ở v2 nhưng runtime nhận v1, có thể gặp `NoSuchMethodError` khi symbolic reference được resolve.
- Lỗi không phụ thuộc việc plugin B có file v2 trong JAR: **parent đã trả class cùng tên trước**.

Cách giải quyết ưu tiên: **không đặt private, versioned library trên class path của parent**. Nếu kiến trúc bắt buộc parent chứa thư viện xung đột, có thể cần **selective child-first** cho namespace private; không nên đảo thứ tự cho tất cả package một cách tùy tiện.

## 5. Demo Java 17 chạy được: hai phiên bản, hai URLClassLoader, một shared API

Bài demo sử dụng hai bản class **cùng binary name `lib.Versioned`** nhưng source/bytecode khác nhau. Chúng được biên dịch vào **hai output directories riêng**, sau đó nạp bởi hai loader objects. Host chỉ thấy shared API.

### 5.1. Cấu trúc file nguồn

Tạo cây thư mục:

```text
src/
  api/
    Plugin.java
  plugin-a/
    lib/
      Versioned.java
    plugin/
      Implementation.java
  plugin-b/
    lib/
      Versioned.java
    plugin/
      Implementation.java
  host/
    PluginHost.java
```

**File `src/api/Plugin.java`:**

```java
package api;

public interface Plugin {
    String run();
}
```

**File `src/plugin-a/lib/Versioned.java`:**

```java
package lib;

public final class Versioned {
    public String value() {
        return "v1:legacy";
    }
}
```

**File `src/plugin-a/plugin/Implementation.java`:**

```java
package plugin;

import api.Plugin;
import lib.Versioned;

public final class Implementation implements Plugin {
    @Override
    public String run() {
        return new Versioned().value();
    }
}
```

**File `src/plugin-b/lib/Versioned.java`:**

```java
package lib;

public final class Versioned {
    public String value() {
        return "v2:modern";
    }
}
```

**File `src/plugin-b/plugin/Implementation.java`:**

```java
package plugin;

import api.Plugin;
import lib.Versioned;

public final class Implementation implements Plugin {
    @Override
    public String run() {
        return new Versioned().value();
    }
}
```

Lưu ý hai cặp `lib.Versioned` và `plugin.Implementation` đều **cùng package + class name**, nhưng được biên dịch riêng cho hai plugin. Shared interface `api.Plugin` chỉ có **một** source/output chung.

### 5.2. Host chọn loader rõ ràng

**File `src/host/PluginHost.java`:**

```java
package host;

import api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginHost {
    private static URL pluginUrl(String directory)
            throws Exception {
        return Path.of(directory).toUri().toURL();
    }

    private static Plugin create(URLClassLoader loader)
            throws Exception {
        Class<?> implementation =
                Class.forName("plugin.Implementation", true, loader);
        Object instance =
                implementation.getDeclaredConstructor().newInstance();
        return (Plugin) instance;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader shared = Plugin.class.getClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                        new URL[]{pluginUrl("out/plugin-a")}, shared);
             URLClassLoader loaderB = new URLClassLoader(
                        new URL[]{pluginUrl("out/plugin-b")}, shared)) {

            Plugin a = create(loaderA);
            Plugin b = create(loaderB);

            Class<?> libA = loaderA.loadClass("lib.Versioned");
            Class<?> libB = loaderB.loadClass("lib.Versioned");

            System.out.println("Plugin A: " + a.run());
            System.out.println("Plugin B: " + b.run());

            System.out.println("Libraries have same name: "
                    + libA.getName().equals(libB.getName()));
            System.out.println("Libraries have different identity: "
                    + (libA != libB));
            System.out.println("Plugin types have different identity: "
                    + (a.getClass() != b.getClass()));

            System.out.println("A library defined by A: "
                    + (libA.getClassLoader() == loaderA));
            System.out.println("B library defined by B: "
                    + (libB.getClassLoader() == loaderB));

            System.out.println("Both share API: "
                    + (a.getClass().getInterfaces()[0] == Plugin.class
                       && b.getClass().getInterfaces()[0] == Plugin.class));
        }
    }
}
```

Giải thích thiết kế:

- `shared` là defining loader của `api.Plugin` trên class path thông thường. Hai plugin loaders nhận nó làm **parent**.
- `URLClassLoader` được cấu hình bằng thư mục riêng đã chứa class files của plugin. URL trỏ vào **thư mục**, không phải mọi file `.class` riêng lẻ.
- Host **không đưa `out/plugin-a` hoặc `out/plugin-b` lên chính application class path**, nên parent không tự thấy private `lib.Versioned` và `plugin.Implementation`.
- `Class.forName(..., true, loader)` chọn đúng plugin loader và yêu cầu initialization của implementation, rồi reflection tạo object qua public zero-arg constructor ngầm định.
- Hai objects đều implement interface `api.Plugin` của parent; phép cast trong `create` hợp lệ. Nếu vô tình đóng gói API copy và child-first cho namespace `api.*`, phép cast này có thể không hợp lệ.
- Khối `try-with-resources` đóng `URLClassLoader` khi kết thúc phạm vi; việc đóng **không tự làm JVM unload mọi class ngay lập tức**.

### 5.3. Biên dịch hai phiên bản tách biệt

Tại thư mục gốc chứa `src`, chạy lần lượt:

```bash
mkdir -p out/api out/plugin-a out/plugin-b out/host

javac -d out/api src/api/Plugin.java

javac -cp out/api -d out/plugin-a \
  src/plugin-a/lib/Versioned.java \
  src/plugin-a/plugin/Implementation.java

javac -cp out/api -d out/plugin-b \
  src/plugin-b/lib/Versioned.java \
  src/plugin-b/plugin/Implementation.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api:out/host" host.PluginHost
```

Đối với **Windows PowerShell**, dùng class path separator `;`, và trình bày các lệnh trên một dòng:

```powershell
New-Item -ItemType Directory -Force out/api,out/plugin-a,out/plugin-b,out/host

javac -d out/api src/api/Plugin.java

javac -cp out/api -d out/plugin-a src/plugin-a/lib/Versioned.java src/plugin-a/plugin/Implementation.java

javac -cp out/api -d out/plugin-b src/plugin-b/lib/Versioned.java src/plugin-b/plugin/Implementation.java

javac -cp out/api -d out/host src/host/PluginHost.java

java -cp "out/api;out/host" host.PluginHost
```

**Quan trọng:** Lệnh chạy `java` **chỉ** đưa `out/api` và `out/host` vào application class path. Nếu thêm `out/plugin-a` vào class path của host, parent có thể tìm thấy v1 sớm và làm sai mục tiêu kiểm thử.

### 5.4. Stdout dự kiến

Với JDK 17+ và cấu trúc sạch như trên:

```text
Plugin A: v1:legacy
Plugin B: v2:modern
Libraries have same name: true
Libraries have different identity: true
Plugin types have different identity: true
A library defined by A: true
B library defined by B: true
Both share API: true
```

**Phân tích:** 

1. Cả hai `Versioned.value()` tồn tại với cùng tên class, nhưng trả hai phiên bản hành vi khác nhau. Đây là bằng chứng mỗi plugin dùng class của riêng nó.
2. `libA.getName().equals(libB.getName())` là `true` vì hai class có binary name bằng nhau.
3. `libA != libB` là `true` vì runtime identity khác theo defining loader. Chính đó là isolation mà ứng dụng cần.
4. `a.getClass() != b.getClass()` là `true`: implementation cùng binary name cũng được nạp riêng.
5. `libA.getClassLoader() == loaderA` và `libB.getClassLoader() == loaderB` chứng minh loader nào **định nghĩa** hai thư viện.
6. Hai class implementation đều triển khai chính xác `api.Plugin` từ loader chung; kết quả `Both share API: true` cho thấy boundary hợp lệ.

Ví dụ cố ý **không** dùng static final compile-time constant để đại diện version, vì Java compiler có thể inline những constant values và khiến output không còn chứng minh lớp `lib.Versioned` được nạp từ đâu.

## 6. Khi cần selective child-first cho thư viện private

Trên nhiều platform, host hoặc một dependency của host đã đặt `lib.Versioned` vào parent class path. Parent-first lúc này làm plugin B nhận version từ parent, dù đã có JAR riêng.

Một phương án là tạo **child-first chỉ với package private**. Với các package như `java.*`, shared API `api.*`, logging contract và các kiểu giao tiếp host, vẫn ưu tiên parent.

Khung code minh họa:

```java
import java.net.URL;
import java.net.URLClassLoader;

public class SelectivePluginLoader extends URLClassLoader {
    public SelectivePluginLoader(String name, URL[] urls,
                                 ClassLoader parent) {
        super(name, urls, parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        if (!name.startsWith("lib.privatecopy.")) {
            return super.loadClass(name, resolve);
        }

        synchronized (getClassLoadingLock(name)) {
            Class<?> c = findLoadedClass(name);
            if (c == null) {
                try {
                    c = findClass(name); // ưu tiên plugin URL
                } catch (ClassNotFoundException missingLocally) {
                    c = super.loadClass(name, false); // có thể fallback
                }
            }

            if (resolve) {
                resolveClass(c);
            }
            return c;
        }
    }
}
```

Đây là **một class có thể biên dịch trong `SelectivePluginLoader.java`**, nhưng chỉ là mẫu chính sách, chưa thay thế ví dụ phần 5. Prefix `lib.privatecopy.` cần đổi cho đúng namespace được plugin sở hữu; ví dụ demo dùng `lib.Versioned`, nên nếu muốn áp dụng vào demo phải đổi điều kiện package cho phù hợp và quản lý cả các class phụ thuộc liên quan.

Các lưu ý rất quan trọng:

- Luôn dùng `findLoadedClass` dưới `getClassLoadingLock(name)` trước khi tự tìm/định nghĩa; tránh nỗ lực `defineClass` lặp trong cùng loader.
- Đừng áp dụng child-first bừa bãi cho `java.*`, `javax.*` hoặc shared API `api.*`.
- **Fallback parent** có thể đánh mất tính cô lập nghiêm ngặt nếu private dependency không có ở plugin nhưng parent có version khác. Trong kiến trúc đòi version isolation tuyệt đối, có thể **không fallback** cho namespace private.
- Một package prefix quá rộng có thể vô tình cô lập cả SPI interface/DTO mà host cần dùng chung.
- Nhiều class trong cùng thư viện có references lẫn nhau; chỉ isolate một class trong một thư viện nhiều class thường **không đủ**. Hãy xét cả dependency graph/transitive dependencies.
- Class-loader constraints, package sealing, JPMS boundaries và access rules vẫn áp dụng.
- Nếu library dùng resource lookup, native code hoặc context class loader, việc đổi class lookup order chưa chắc làm mọi dependency/resource cũng đi đúng phiên bản.

**Khuyến nghị:** trước khi override `loadClass`, thử cách đơn giản hơn: giữ private versioned libs **ngoài parent class path** và cung cấp riêng cho từng `URLClassLoader`. Override chỉ khi có lý do rõ ràng và bộ test class identity.

## 7. Khi nào cô lập phiên bản không còn là ranh giới an toàn?

Version isolation hoạt động tốt khi thư viện private **ở bên trong plugin**, không lộ những object thuộc runtime class riêng của plugin qua shared host boundary.

### Lỗi: trả trực tiếp object của private library

Xét host API:

```java
// Minh họa một API gây lệ thuộc vào private lib:
package api;

public interface Converter {
    lib.Versioned convert(lib.Versioned input);
}
```

Đoạn này không phải thiết kế plugin an toàn. Khi host định nghĩa `Converter`, nó cần biết `lib.Versioned` trong chữ ký. Nếu plugin lại dùng bản khác của `lib.Versioned`, việc resolve các field/method descriptors hoặc method override có thể gây **loading constraint violation** và `LinkageError`.

### Mô hình tốt hơn

```java
package api;

public interface Converter {
    String convert(String input);
}
```

Giữ private library bên trong implementation:

```java
package plugin;

public class ConverterImpl implements api.Converter {
    @Override
    public String convert(String input) {
        // Chuyển đổi bằng versioned library chỉ plugin này nhìn thấy.
        return input.trim();
    }
}
```

Hai khối này là **các file riêng cần đặt theo package**, không phải một chương trình đơn file. `ConverterImpl` chỉ minh họa boundary, không tự chứng minh đã dùng một thư viện cụ thể. Ý tưởng là contract dùng những shared types được tất cả bên hiểu thống nhất.

Với payload phức tạp, có thể dùng DTO do loader chung định nghĩa, một API serialization có schema rõ ràng, hoặc interface adapter do host cung cấp. Nhưng JSON/serialization cũng có vấn đề version/compatibility riêng; không phải giải pháp miễn kiểm thử.

## 8. Parent-first, child-first và class identity trong bảng so sánh

| Thiết kế | Thư viện private có thể dùng version riêng? | Rủi ro |
|---|---|---|
| Một application class loader cho mọi plugin | Thường **không**, nếu cùng binary name với các bản khác nhau | Version conflict, `NoSuchMethodError` |
| Mỗi plugin `URLClassLoader`, parent không có private lib | **Có**, thường đủ với parent-first | Đường tìm class/resource phải đúng |
| Mỗi plugin loader, parent đã có private lib, parent-first | Thường bị version ở parent che khuất | Silent wrong version hoặc linkage error |
| Selective child-first cho private namespace | **Có thể**, nếu prefix và transitive deps được kiểm soát | Duplicate shared types, package/resource bugs |
| Child-first với mọi package, kể cả shared API | Không phải thiết kế an toàn | `ClassCastException`/`LinkageError`, vi phạm package rules |
| Shading/relocation đổi package/binary name cho dependency | Có thể chạy nhiều version cùng một loader | Quy trình build phức tạp, resource/reflection/service metadata cần cập nhật |
| Chạy mỗi plugin ở process/JVM riêng | Cách ly mạnh hơn class loader | Chi phí IPC/deployment và protocol compatibility |

**Shading/relocation** là lựa chọn khác: đổi binary name (ví dụ từ `lib.Versioned` sang `pluginA.shaded.lib.Versioned`) trong build artifact để loại bỏ collision tên. Nó không đồng nghĩa với classloader isolation và cần công cụ build xử lý reflection, serialized names, service files/resource references tương ứng.

**Nhiều process/JVM** thường phù hợp hơn khi yêu cầu isolation về an toàn hoặc fault containment. Classloader isolation **không phải security sandbox** và không cô lập hoàn toàn native state, process-wide system properties, static state của shared classes hoặc threads dùng chung.

## 9. ServiceLoader, TCCL và provider của từng plugin

Trong hệ plugin có nhiều versions, code host có thể dùng `ServiceLoader` để tìm implementations của shared interface `api.Plugin`.

API:

```java
java.util.ServiceLoader<api.Plugin> providers =
        java.util.ServiceLoader.load(api.Plugin.class, pluginLoader);
```

Trong snippet này, `pluginLoader` cần là loader của plugin mà host muốn tìm. Đây là **explicit loader**, tránh phụ thuộc vào `Thread.currentThread().getContextClassLoader()` khi host chạy trên worker pool.

Có thể bổ sung file resource trong **mỗi thư mục plugin**:

```text
out/plugin-a/META-INF/services/api.Plugin
out/plugin-b/META-INF/services/api.Plugin
```

Mỗi file chứa một dòng:

```text
plugin.Implementation
```

Khi đó `ServiceLoader.load(api.Plugin.class, loaderA)` có thể tìm provider của A; tương tự loaderB cho B. Shared `api.Plugin` phải do parent cung cấp để provider assignable với host.

**Cảnh báo:** `ServiceLoader.load(api.Plugin.class)` overload một tham số dùng **TCCL của thread hiện tại**. Trong thread pool, TCCL có thể trỏ vào plugin khác hoặc loader do container đặt. Nếu đã biết loader của plugin cần truy vấn, truyền nó tường minh.

Không tự động suy rằng `ServiceLoader` chỉ quét resource của child: cơ chế resource lookup có thể tuân parent và layer behavior. Nếu parent cũng quảng bá provider, có thể thấy cả providers do parent biết. Muốn kiểm soát chặt phạm vi provider, thiết kế discovery riêng hoặc classloader/resource policy phù hợp, test thực tế.

### TCCL dễ gây classloader leak

Nếu host thread pool giữ `pluginLoader` qua `Thread.setContextClassLoader(pluginLoader)` rồi không phục hồi, loader đó có thể không được GC ngay cả sau khi plugin unload logic.

Mẫu an toàn khi framework bắt buộc dùng TCCL:

```java
Thread worker = Thread.currentThread();
ClassLoader before = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // Thực hiện lời gọi SPI/framework dùng TCCL.
} finally {
    worker.setContextClassLoader(before);
}
```

Đây là mã minh họa cần `pluginLoader` trong scope. Thay đổi/khôi phục phải xảy ra trên **thread thực sự chạy lookup**, không chỉ trên thread submit task.

## 10. Resources, JNI, module system và giới hạn cô lập

### 10.1. Resources không phải class

Nhiều thư viện dùng tài nguyên như `config.properties`, `META-INF/services/...`, XML hoặc native libraries. Class identity cô lập không đảm bảo resource lookup tự động dùng cùng loader:

- `SomeClass.class.getResourceAsStream(...)` liên quan tới class owner và resource path.
- `pluginLoader.getResourceAsStream(...)` dùng loader do caller chọn và các quy tắc tra cứu resource.
- `Thread.currentThread().getContextClassLoader().getResource(...)` phụ thuộc context thread, có thể trỏ nhầm plugin.

Khi debug “class đúng version nhưng cấu hình sai”, xem cả **resource lookup path**. Với URLClassLoader, resource URLs có thể bao gồm directories hoặc JARs; thứ tự URLs và parent delegation ảnh hưởng kết quả.

### 10.2. Native libraries không cô lập giống bytecode

Nếu hai Java libraries phụ thuộc chung JNI native library, khả năng nạp và chia sẻ native code chịu quy tắc `System.loadLibrary`/JVM và hệ điều hành. Không thể suy rằng hai `URLClassLoader` tự cung cấp hai namespace native độc lập như với Java class files.

Trên JVM, việc cố nạp cùng một native library bởi hai class loaders có thể gây `UnsatisfiedLinkError` trong các trường hợp tương ứng. Nếu thư viện có JNI hoặc singleton state ở mức process, cần xem xét cách thiết kế native dependency và khả năng tách process.

### 10.3. JPMS và ModuleLayer

Ví dụ `URLClassLoader` phần 5 sử dụng **class path**, nơi thư viện là unnamed module của loader tương ứng. Với **named modules**, loader parent không tự bỏ qua module readability/exports/opens; cần cấu hình module graph và có thể cân nhắc `ModuleLayer` riêng.

Có thể tạo module layers khác nhau cho plugin khi hệ thống được thiết kế modular, nhưng vẫn phải phân biệt class identity, API chia sẻ, split packages, service binding và module access.

### 10.4. Không coi class loader là security sandbox

Class loader tùy chỉnh không ngăn tuyệt đối plugin sửa system properties, tạo threads, tiêu thụ CPU/memory hay gọi API nền tảng mà code có quyền sử dụng. Để chạy code không tin cậy, cân nhắc cách ly bằng process/container với chính sách hệ thống phù hợp, không chỉ bằng child-first delegation.

## 11. Lifecycle: nạp, chạy, dừng và nạp lại plugin

Để hỗ trợ nhiều phiên bản song song hoặc reload:

1. **Tạo loader riêng** cho phiên bản plugin với class/resource sources cụ thể.
2. **Nạp implementation** và đưa object qua shared API.
3. **Dùng plugin** trong phạm vi đã xác định; không rò rỉ private `Class<?>` vào registry dài hạn.
4. **Dừng plugin**: hủy listeners/callbacks, shutdown executors, bỏ thread locals, đóng resources.
5. **Đóng URLClassLoader** khi không còn tác vụ dùng nguồn class/resource và bỏ references tới loader cùng các object/class của plugin.
6. **Nếu cần phiên bản mới**, thường tạo loader mới với class bytes/URLs của version mới.

Một object `ClassLoader` đã định nghĩa `lib.Versioned` không thể biến định nghĩa runtime cũ thành version mới bằng cách sửa file JAR phía dưới rồi gọi `loadClass` lại. Class đã được ghi nhận cho loader đó thường được tái sử dụng; nỗ lực `defineClass` lặp cùng binary name có thể gây `LinkageError`.

`URLClassLoader.close()` đóng các resources có thể đóng do loader quản lý và ngăn một số hoạt động lookup tiếp theo, nhưng **không tự unload class đã load** hoặc làm object đã tạo biến mất. Class unloading phụ thuộc reachability/classloader và chính sách VM.

### Những references thường cản unloading

- Thread còn chạy với TCCL của plugin.
- ThreadLocal chứa object/plugin class.
- Host static cache giữ `Class<?>`, `Method`, provider instance hoặc class loader.
- Event listener/callback chưa unregister.
- Executor, timer, scheduled task chưa shutdown.
- ServiceLoader/provider cache hoặc registry còn giữ plugin instances.

Quan sát JVM:

```bash
java -Xlog:class+load=info,class+unload=info -cp "out/api:out/host" host.PluginHost
```

Lệnh minh họa cho HotSpot/JDK 17 trên Linux/macOS. Nó in nhiều events class loading/unloading, **không bảo đảm** thấy một dòng unload ngay khi `try-with-resources` đóng loader.

## 12. Chẩn đoán lỗi khi hai phiên bản không hoạt động như dự kiến

### Lỗi A: Hai plugin đều in giá trị của bản 1

Khả năng thường gặp:

- Parent class path đã có v1 và nạp trước hai children.
- Cả hai plugin loaders cùng trỏ vào một directory/JAR.
- Plugin B dùng TCCL hoặc class loader của A khi reflection/resource lookup.
- Library được **shaded** hoặc copied nhầm khi đóng gói.

Cách kiểm tra:

```java
System.out.println(libA.getName());
System.out.println(libA.getClassLoader());
System.out.println(libB.getClassLoader());
System.out.println(libA == libB);
```

Đoạn này minh họa cần biến `libA` và `libB` đã được lấy. Nếu `libA == libB` là true, cùng class runtime đang được dùng; vấn đề là **lookup/delegation**, không phải sự tồn tại của hai file riêng.

### Lỗi B: NoSuchMethodError hoặc NoSuchFieldError

Plugin được biên dịch dựa trên API của v2 nhưng runtime resolve về v1, nơi thiếu method/field tương ứng. Cần so sánh **runtime class source và defining loader** với class path lúc compile.

Nếu cần quan sát code thực tế trong class file:

```bash
javap -classpath out/plugin-a -p lib.Versioned
javap -classpath out/plugin-b -p lib.Versioned
```

Trong ví dụ demo, hai bản có cùng method signature nhưng khác behavior; với API thực tế, method descriptors có thể khác nhau. `javap` cho biết bytecode từ đường dẫn được chỉ định, **không tự chứng minh** runtime đã chọn bản đó.

### Lỗi C: ClassCastException giữa hai class có cùng tên

Có thể xảy ra khi host/plugin cố ép kiểu một object do loader A định nghĩa thành class cùng tên do loader B định nghĩa. Kiểm tra:

```java
System.out.println(typeA.getName().equals(typeB.getName()));
System.out.println(typeA == typeB);
```

Nếu tên giống nhau nhưng `Class<?>` khác nhau, vấn đề nằm ở runtime class identity. Không sửa bằng cách đổi loader name hoặc cast qua `Object`; cần thống nhất shared contract và adapter thích hợp.

### Lỗi D: LinkageError do loader constraint violation

JVM áp đặt loading constraints khi các types trong field/method descriptors ở ranh giới loader cần được hiểu nhất quán. Nếu host API và plugin tự định nghĩa hai bản `api.Message` có cùng tên, JVM có thể từ chối liên kết bằng `LinkageError` khi constraint không thỏa.

Giải pháp: để `api.Message` và các shared DTO được định nghĩa tại **common API loader**, tránh để private library types len vào API signature.

### Lỗi E: ClassNotFoundException hoặc NoClassDefFoundError

Không phải chỉ có vấn đề version. Plugin loader có thể thiếu transitive dependency, resource URL không hợp lệ hoặc parent không nhìn thấy shared contract.

- `ClassNotFoundException` thường xuất hiện khi lookup theo yêu cầu không thấy binary name.
- `NoClassDefFoundError` có thể phát sinh khi resolution/runtime cần class nhưng không tìm được hoặc class initialization trước đó thất bại.
- Không gộp hai loại lỗi thành “loader không chạy” mà bỏ qua stack trace.

### Lỗi F: ServiceLoader tìm sai provider

Kiểm tra xem overload sử dụng **explicit loader** hay **TCCL**, resource `META-INF/services/...` nằm ở plugin nào, provider có implement **cùng runtime shared API type** hay không, và có providers do parent hiển thị thêm không.

### Quy trình kiểm tra có hệ thống

1. Ghi binary name của class bị lỗi, compile-time dependency version và plugin owner.
2. Ghi `Class.getClassLoader()` của runtime class, đừng chỉ in `getName()`.
3. Kiểm tra URL/class path của parent và từng child.
4. Với shared API, so sánh trực tiếp `Class<?>` ở host và plugin.
5. Kiểm tra class bytes bằng `javap -classpath` và artifact inventory.
6. Nếu cần, bật `-Xlog:class+load=info` trên HotSpot để quan sát lookup; log format tùy VM và không chứng minh toàn bộ nguyên nhân nếu thiếu thêm phân tích.
7. Kiểm tra TCCL, SPI, resources và transitive dependencies.
8. Sửa ở **dependency ownership và delegation policy**, không chỉ xóa cache hoặc đổi tên file JAR.

## 13. Các sai lầm phổ biến

| Nhầm lẫn | Sự thật |
|---|---|
| “Hai file JAR chứa cùng class name thì JVM luôn nạp cả hai.” | Một loader thường chỉ định nghĩa một runtime class cho một binary name; cần các defining loaders khác nhau hoặc relocation. |
| “Tạo hai URLClassLoader là chắc chắn có hai version.” | Nếu parent đã có class private, cả hai children parent-first có thể dùng chung version của parent. |
| “Child-first cho toàn bộ package là cách an toàn nhất.” | Có thể nhân bản shared API types và gây ClassCastException/LinkageError. |
| “Cùng bytes là cùng runtime type.” | Defining loader cũng quyết định class identity. |
| “Chỉ cần khác getName() của loader là đã cô lập.” | Loader name là nhãn, không quyết định lookup hay identity. |
| “Chữ ký host có thể thoải mái chứa plugin-private types.” | Đó là nơi loading constraints và incompatibility có thể phát sinh. |
| “Đóng URLClassLoader là class của nó unload ngay.” | Close không tự làm mọi Class<?>/object unreachable. |
| “TCCL luôn bằng loader của plugin đang chạy.” | TCCL thuộc thread, có thể bị framework/thread pool thay đổi. |
| “Classloader isolation cô lập cả JNI/process-wide state.” | Native/process-wide resources có lifecycle và hạn chế khác. |
| “NoSuchMethodError nghĩa class chưa được nạp.” | Class có thể đã nạp **sai phiên bản**, dẫn đến thiếu method theo descriptor kỳ vọng. |
| “ServiceLoader.load(service) luôn chỉ tìm provider của plugin đang xét.” | Nó dùng TCCL; muốn chọn plugin cụ thể, truyền loader tường minh và xét parent visibility. |

## 14. Bài tập tự kiểm tra

**Câu 1.** Hai loaders định nghĩa cùng `lib.Versioned` nhưng từ hai JAR khác nhau. Kết quả `classA.getName().equals(classB.getName())` và `classA == classB` thế nào?

**Đáp án:** Tên có thể bằng nhau, nhưng `Class<?>` khác nhau nếu defining loader khác nhau.

**Câu 2.** Plugin A và B đều parent-first. Parent không thấy `lib.Versioned`. Mỗi plugin URLClassLoader có version riêng. Có cần custom child-first mới dùng được cả hai version không?

**Đáp án:** Không. Khi parent không có class private, mỗi child tự tìm/định nghĩa phiên bản của mình là đủ.

**Câu 3.** Parent chứa `lib.Versioned` v1, plugin B chứa v2. Điều gì có thể xảy ra?

**Đáp án:** Parent-first có thể chọn v1 cho B, gây behavior sai hoặc `NoSuchMethodError` nếu v2 có method mới. Cần di chuyển private lib khỏi parent hoặc thiết kế selective child-first thích hợp.

**Câu 4.** Vì sao cả hai plugin trong ví dụ đều cast được sang `api.Plugin` của host?

**Đáp án:** Cả hai loader ủy quyền interface `api.Plugin` tới cùng defining loader của shared API; implementation classes khác nhau nhưng contract runtime identity được chia sẻ.

**Câu 5.** Host API khai `lib.Versioned convert(lib.Versioned)` có nguy cơ gì?

**Đáp án:** Private lib type bị rò qua boundary. Host/plugin có thể resolve thành runtime classes khác nhau, gây loading constraint violation hoặc lỗi cast/lookup. Nên dùng shared DTO/interface hoặc adapter.

**Câu 6.** `URLClassLoader.close()` có bảo đảm JVM thu hồi class metadata ngay không?

**Đáp án:** Không. Cần xét object/classloader reachability và GC/unloading; `close()` chủ yếu quản lý tài nguyên của loader.

**Câu 7.** Vì sao không dùng `static final String VERSION = "v2";` làm bằng chứng chắc chắn bản v2 được nạp?

**Đáp án:** Compile-time constants có thể bị inline tại nơi tham chiếu. Gọi instance method `value()` và kiểm tra defining loader rõ hơn.

**Câu 8.** ServiceLoader tìm provider sai plugin trong thread pool. Nên kiểm tra gì?

**Đáp án:** Overload dùng TCCL hay explicit loader, loader thực tế của worker, resource provider file, API type identity và parent visibility.

## 15. Ghi nhớ và tài liệu chính thức

**Tóm tắt ba nguyên tắc:**

1. **Cô lập thứ cần khác:** cho mỗi plugin một defining loader riêng đối với private dependencies có version khác nhau.
2. **Chia sẻ thứ cần tương thích:** để interface và DTO của host/plugin boundary được định nghĩa ở loader chung; tránh để private types đi qua method/field descriptors của shared API.
3. **Kiểm soát đường nạp và lifecycle:** ưu tiên parent-first với parent không chứa private lib; chỉ dùng selective child-first khi cần, truyền loader tường minh khi tìm provider, đóng tài nguyên và dọn references khi plugin dừng.

**Tài liệu tham khảo:**

- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, runtime class identity, loading constraints và resolution.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `defineClass`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): class/resource lookup qua URLs và `close()`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, explicit loader/TCCL và service configuration.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName()`, `getClassLoader()` và runtime type metadata.