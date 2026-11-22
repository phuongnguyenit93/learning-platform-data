# URLClassLoader: Chọn parent và phạm vi phụ thuộc được kế thừa

Khi tạo một `java.net.URLClassLoader` để nạp plugin hoặc JAR động, hai thông số quan trọng nhất là **danh sách URL của chính loader** và **parent class loader**. Danh sách URL cho biết loader con có thể tự tìm class/resource ở những nguồn nào; parent cho biết những class/resource nào nó có thể tiếp cận thông qua **delegation**. Với chiến lược **parent-first mặc định**, parent còn quyết định **phiên bản dependency nào được chọn trước** khi plugin JAR chứa một class trùng tên.

Bài học tập trung vào cách chọn parent của `URLClassLoader` trên **Java 17+**, phạm vi phụ thuộc nhìn thấy qua parent, ranh giới host–plugin, cách tránh xung đột phiên bản và các bài thực hành chạy được. “Kế thừa phụ thuộc” ở đây **không phải** Java `extends`, không tự copy JAR từ parent sang child và không có nghĩa child sở hữu mọi class nó tìm thấy.

## 1. Hai nguồn class của một URLClassLoader

Constructor thường dùng:

```java
URLClassLoader pluginLoader =
        new URLClassLoader(pluginUrls, parentLoader);
```

Đây là **snippet**, cần biến `pluginUrls` và `parentLoader` đã khai báo. Nó xác lập:

1. **Child URL roots** (`pluginUrls`): các URL của thư mục class hoặc JAR để child tìm khi parent không tìm được. `URLClassLoader.findClass` sử dụng các nguồn này.
2. **Parent object** (`parentLoader`): một instance `ClassLoader` mà `URLClassLoader` thường hỏi trước thông qua `ClassLoader.loadClass`.
3. **Class identity:** nếu parent trả về `Class<?>`, child dùng chính class đó. Child **không define bản sao** chỉ vì URL của child cũng có cùng binary name.
4. **Phạm vi lookup:** `pluginLoader.getURLs()` liệt kê URL riêng của child, không hợp nhất URL hay dependency của parent.
5. **Định danh parent:** `pluginLoader.getParent()` cho biết object parent, không phải Java superclass của `URLClassLoader`.

Đây là mô hình nạp lớp mặc định:

```text
pluginLoader.loadClass("feature.Service")
                │
                ▼
findLoadedClass(name)
     ├── đã biết ──► trả Class<?> có sẵn
     └── chưa
          │
          ▼
parent.loadClass(name)
     ├── tìm thấy ──► trả Class<?> do parent/ancestor định nghĩa
     └── không thấy
          │
          ▼
pluginLoader.findClass(name)
     ├── tìm trong URL của child ──► define và trả Class<?>
     └── thất bại ──► ClassNotFoundException
```

JVM còn có verification, linking, initialization và runtime module semantics riêng; sơ đồ không khẳng định mọi class loader tùy biến đều parent-first. Nhưng đây là cách suy nghĩ đúng cho `URLClassLoader` sử dụng triển khai `loadClass` chuẩn.

## 2. Parent không phải superclass Java

`URLClassLoader` kế thừa Java class `SecureClassLoader`, rồi `ClassLoader`. Đó là **type hierarchy**:

```text
Object
  └── ClassLoader
        └── SecureClassLoader
              └── URLClassLoader
```

Tuy nhiên, `new URLClassLoader(urls, hostLoader)` tạo một object `URLClassLoader` có parent **trỏ đến object `hostLoader`**. `hostLoader` có thể là instance của built-in application loader hoặc một subclass không liên quan đến `URLClassLoader` trong type hierarchy.

```text
hostLoader : ClassLoader instance
          ▲
          │ pluginLoader.getParent() == hostLoader
          │
pluginLoader : URLClassLoader instance
```

Do đó:

- `pluginLoader.getClass().getSuperclass()` trả Java superclass **`SecureClassLoader.class`**.
- `pluginLoader.getParent()` trả **loader object được chọn** ở constructor.
- `pluginLoader.loadClass("api.Plugin")` trả `Class<?>` được tìm thấy, nhưng `returnedClass.getClassLoader()` mới giúp xác định **defining loader** của class được trả về.
- Parent được lựa chọn theo **hợp đồng API/dependency visibility**, không theo Java `extends`.

Đặc biệt trong kiến trúc plugin, parent và Java superclass giải quyết hai vấn đề hoàn toàn khác nhau: **ủy quyền lookup** và **kế thừa implementation methods**.

## 3. Các lựa chọn parent trên JDK hiện đại

| Parent | Những gì child có thể nhìn thấy qua delegation | Dùng khi nào |
| --- | --- | --- |
| `ClassLoader.getSystemClassLoader()` | Java platform classes cùng các class/dependency mà **system loader thực sự thấy** | Plugin cần host SDK/SPI hoặc code trên application classpath |
| `HostApi.class.getClassLoader()` | Namespace của loader **định nghĩa shared API** (và những gì nó thấy) | Plugin phải tương thích với interface, DTO, exception do host dùng |
| `ClassLoader.getPlatformClassLoader()` | Platform classes từ JDK và ancestor | Plugin có dependency riêng và không mặc định dùng application classpath |
| `null` | Cơ chế tra cứu của **bootstrap** trong `ClassLoader` mặc định | Chỉ khi thực sự muốn parent là bootstrap và chấp nhận phạm vi hẹp |
| Custom shared loader | Những classes/resources mà loader chung quản lý | Application server, plugin SDK chuyên biệt, nhiều tầng class loader |

Cần phân biệt:

- **System parent** là thuận tiện, nhưng có thể khiến dependency của **host** thắng dependency cùng tên của **plugin**.
- **Platform parent** phù hợp khi plugin chỉ cần Java platform API và JAR riêng. Nhưng nó không tự biết một interface như `com.myapp.spi.Plugin` do application loader định nghĩa.
- **`null` parent** không có nghĩa child không tìm được `java.lang.String`: lớp này thường được bootstrap định nghĩa. Tuy nhiên từ Java 9, **không phải mọi platform class đều nhất thiết do bootstrap định nghĩa**, nên parent platform thường phù hợp hơn khi cần đầy đủ platform APIs.
- **Host API loader** có thể khác system loader trong container/framework. Dùng `HostApi.class.getClassLoader()` làm điểm neo khi mục tiêu là chia sẻ **đúng runtime interface**.

Parent là **đối tượng tham chiếu**. Khi đổi parent giữa hai URLClassLoader instances, bạn không đổi Java superclass của chúng; bạn đổi **đường lookup** và khả năng tương thích.

## 4. Constructor nào chọn parent mặc định?

Javadoc Java 17 có các dạng:

```java
new URLClassLoader(urls);
new URLClassLoader(urls, parent);
new URLClassLoader("plugin-A", urls, parent);
```

Đây là syntax minh họa. Những điều đáng nhớ:

- `URLClassLoader(URL[] urls)` sử dụng **system class loader làm parent**.
- `URLClassLoader(URL[] urls, ClassLoader parent)` dùng **đúng loader object** truyền vào, kể cả `null`.
- `URLClassLoader(String name, URL[] urls, ClassLoader parent)` hỗ trợ đặt tên loader để quan sát/diagnostics. Tên `"plugin-A"` không phải binary name, không tự tạo package riêng và không ảnh hưởng delegation order.
- Một số overloads hỗ trợ `URLStreamHandlerFactory`. Chúng không cần thiết để nạp class từ file/JAR URLs bình thường.
- Dùng `try-with-resources` khi ứng dụng sở hữu loader và muốn đóng những JAR handles đúng lúc; `close()` không làm class đã nạp tự động unload ngay lập tức.

**Không bỏ trống parent argument theo thói quen** nếu yêu cầu chính của module là **cô lập phụ thuộc**. Constructor một tham số đã chọn system parent và có thể làm phạm vi lookup lớn hơn dự định.

## 5. Thực hành A — ba parent với cùng URL array rỗng

Ví dụ này chứng minh rằng dù child **không có URL nào**, nó vẫn có thể nhìn thấy class thông qua parent.

Cây tệp:

```text
parent-scope-lab/
└── src/demo/ParentScopeDemo.java
```

Nội dung `src/demo/ParentScopeDemo.java`:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;

public final class ParentScopeDemo {
    private static void inspect(String label, URLClassLoader child)
            throws ClassNotFoundException {
        System.out.println(label + " urls=" + child.getURLs().length);
        System.out.println(label + " JDK=" +
                (child.loadClass("java.lang.String") == String.class));

        try {
            boolean visible =
                    child.loadClass("demo.ParentScopeDemo")
                            == ParentScopeDemo.class;
            System.out.println(label + " app=" + visible);
        } catch (ClassNotFoundException e) {
            System.out.println(label + " app=false");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = ParentScopeDemo.class.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader viaApp =
                    new URLClassLoader(new URL[0], app);
             URLClassLoader viaPlatform =
                    new URLClassLoader(new URL[0], platform);
             URLClassLoader viaBootstrap =
                    new URLClassLoader(new URL[0], null)) {
            inspect("app-parent", viaApp);
            inspect("platform-parent", viaPlatform);
            inspect("bootstrap-parent", viaBootstrap);
        }
    }
}
```

Biên dịch/chạy từ thư mục `parent-scope-lab`:

```sh
javac --release 17 -d out src/demo/ParentScopeDemo.java
java -cp out demo.ParentScopeDemo
```

**Stdout trên OpenJDK/HotSpot 17+ thông thường với `-cp out`:**

```text
app-parent urls=0
app-parent JDK=true
app-parent app=true
platform-parent urls=0
platform-parent JDK=true
platform-parent app=false
bootstrap-parent urls=0
bootstrap-parent JDK=true
bootstrap-parent app=false
```

**Đọc kết quả:**

1. `viaApp` có parent là loader nạp class demo từ `-cp out`. Child tìm được `demo.ParentScopeDemo` **qua parent**, dù `getURLs().length == 0`.
2. `viaPlatform` thấy `java.lang.String` nhưng không thấy class demo do application loader quản lý. Child cũng không có URL riêng nên thất bại khi tìm class demo.
3. `viaBootstrap` vẫn thấy `java.lang.String` vì bootstrap nạp lớp cốt lõi này. Nó không tìm class demo.
4. Không một child nào tự define class demo trong trường hợp tìm được qua parent. Kiểm tra `Class<?>.getClassLoader()` sẽ chỉ ra loader thực sự đã định nghĩa class.

**Nguyên tắc:** `getURLs()` không phải “effective dependency list”. Nó chỉ mô tả nguồn riêng của child.

## 6. Parent-first có thể khiến bản JAR cũ của host thắng bản mới của plugin

Giả sử:

```text
Application loader:
    deps/Version.class   → trả về "host"

Child URLs:
    plugin-out/extension/Feature.class
    pluginlib-out/deps/Version.class → trả về "plugin"
```

Nếu plugin nạp `extension.Feature` qua child và `Feature` gọi `deps.Version.value()`, loader child thường hỏi parent trước. Khi parent có class `deps.Version`, JVM liên kết method reference tới **bản parent**. Điều này không thay đổi ngay cả khi pluginlib URL chứa class có cùng tên và source khác.

Hệ quả:

- Plugin có thể chạy **đúng bytecode** nhưng kết quả khác bản mà tác giả plugin mong đợi.
- Nếu method/field signature thay đổi giữa host và plugin compile-time versions, runtime có thể báo `NoSuchMethodError` hoặc `NoSuchFieldError`.
- Parent-first có ích với **shared API identity** nhưng có thể không phù hợp với thư viện **plugin-private** có version trùng tên.
- Không nên sửa mọi lỗi bằng child-first vô điều kiện: nếu loader plugin tự định nghĩa bản sao của interface host, host có thể không cast được plugin instance.

## 7. Thực hành B — cùng plugin bytes, kết quả đổi khi chỉ thay parent

Cấu trúc file:

```text
dependency-choice-lab/
└── src/
    ├── hostlib/deps/Version.java
    ├── pluginlib/deps/Version.java
    ├── plugin/extension/Feature.java
    └── host/demo/DependencyChoiceDemo.java
```

**`src/hostlib/deps/Version.java`:**

```java
package deps;

public final class Version {
    public static String value() {
        return "host";
    }
}
```

**`src/pluginlib/deps/Version.java`:**

```java
package deps;

public final class Version {
    public static String value() {
        return "plugin";
    }
}
```

Đây là **hai phiên bản thay thế** cùng binary name `deps.Version`; phải compile thành hai thư mục riêng.

**`src/plugin/extension/Feature.java`:**

```java
package extension;

import deps.Version;

public final class Feature {
    public String readVersion() {
        return Version.value();
    }
}
```

**`src/host/demo/DependencyChoiceDemo.java`:**

```java
package demo;

import deps.Version;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class DependencyChoiceDemo {
    private static URL directory(String name) throws Exception {
        return Path.of(name).toAbsolutePath().toUri().toURL();
    }

    private static String call(URLClassLoader loader) throws Exception {
        Class<?> feature = loader.loadClass("extension.Feature");
        Object instance = feature.getDeclaredConstructor().newInstance();
        return (String) feature.getMethod("readVersion").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL[] pluginUrls = {
                directory("plugin-out"),
                directory("pluginlib-out")
        };

        System.out.println("host direct=" + Version.value());
        ClassLoader app = DependencyChoiceDemo.class.getClassLoader();

        try (URLClassLoader appParent =
                    new URLClassLoader(pluginUrls, app);
             URLClassLoader platformParent =
                    new URLClassLoader(
                            pluginUrls,
                            ClassLoader.getPlatformClassLoader())) {

            System.out.println("app-parent feature=" + call(appParent));
            System.out.println("platform-parent feature=" +
                    call(platformParent));

            System.out.println("app uses host Class=" +
                    (appParent.loadClass("deps.Version") == Version.class));
            System.out.println("plugin copy differs=" +
                    (platformParent.loadClass("deps.Version")
                            != Version.class));
        }
    }
}
```

**Biên dịch** từ `dependency-choice-lab`:

```sh
javac --release 17 -d hostlib-out src/hostlib/deps/Version.java
javac --release 17 -d pluginlib-out src/pluginlib/deps/Version.java
javac --release 17 -cp pluginlib-out -d plugin-out src/plugin/extension/Feature.java
javac --release 17 -cp hostlib-out -d host-out src/host/demo/DependencyChoiceDemo.java
```

**Chạy trên Windows PowerShell/CMD**:

```powershell
java -cp "host-out;hostlib-out" demo.DependencyChoiceDemo
```

**Chạy trên Linux/macOS**:

```sh
java -cp "host-out:hostlib-out" demo.DependencyChoiceDemo
```

**Stdout dự kiến trên JDK 17+ với đúng thư mục chạy:**

```text
host direct=host
app-parent feature=host
platform-parent feature=plugin
app uses host Class=true
plugin copy differs=true
```

**Giải thích cẩn thận:**

1. Host application classpath gồm `host-out` và `hostlib-out`, **không có `plugin-out`**.
2. Cả hai child `URLClassLoader` nhận cùng URL array với `plugin-out` và `pluginlib-out`. Mỗi child tự định nghĩa `extension.Feature` vì parent của chúng không có class này.
3. Với **app parent**, yêu cầu `deps.Version` được parent giải quyết trước: kết quả là bản `"host"` trên host classpath.
4. Với **platform parent**, platform không thấy class tùy biến `deps.Version` ở application classpath. Child đọc `pluginlib-out` và dùng bản `"plugin"`.
5. `fromParent == Version.class` là cùng runtime type ở nhánh app; nhánh platform có class `deps.Version` khác identity.
6. Trong ví dụ, hai versions cùng có `public static String value()` để output có thể quan sát mà không làm phát sinh lỗi binary compatibility. Nếu signatures khác, lỗi liên kết có thể xuất hiện khi gọi method.

**Vấn đề cốt lõi:** Chỉ thay parent mà không thay plugin bytes đã thay đổi dependency binding. Đây là lý do cấu hình parent phải là **quyết định thiết kế có chủ đích**, không phải thông số ngẫu nhiên.

## 8. Phạm vi được kế thừa không phải là bản sao classpath hay Maven dependencies

“Parent chứa dependency” có thể mang nhiều nghĩa:

| Khái niệm | Quyết định điều gì? | Có tự động được copy vào child? |
| --- | --- | --- |
| `javac -cp ...` | Compiler nhìn thấy type nào khi biên dịch | Không |
| `java -cp ...` | Application/system loader có thể tra cứu nguồn nào lúc chạy | Không |
| Parent chain | Child có thể ủy quyền tra cứu những class nào | Không |
| `URLClassLoader.getURLs()` | URL roots riêng của child | Không chứa các URL của parent |
| Maven/Gradle transitive graph | Artifact nào được build/resolve theo cấu hình build tool | Không tự nạp vào `URLClassLoader` |
| Module `requires`/JPMS readability | Module nào được phép đọc module nào | Không tương đương parent chain |

Nếu một plugin compile với `api.Shared` và `lib.Helper` nhưng runtime parent chỉ cung cấp `api.Shared`, child URL chỉ chứa plugin JAR, thì **`lib.Helper` có thể vẫn thiếu**. Compiler thành công không bảo đảm URL loader nhìn thấy đủ dependency ở runtime.

URL tới một **thư mục chứa JAR files** cũng không tự động quét hết JAR trong đó: muốn cho loader thấy từng JAR, thường phải đưa **URL của mỗi JAR** vào array, hoặc có cơ chế khác quản lý classpath.

## 9. Lựa chọn parent dựa trên shared API identity

Host thường định nghĩa một contract như:

```java
package api;

public interface Plugin {
    String execute();
}
```

Nếu host tải `api.Plugin` bằng application loader, còn plugin chọn platform parent rồi **tự nạp một bản sao** `api.Plugin` trong URL của mình, JVM có thể có hai interface khác nhau:

```text
HostLoader    defines api.Plugin   → Class A
PluginLoader  defines api.Plugin   → Class B

A.getName().equals(B.getName())    → true
A == B                              → false
A.isAssignableFrom(PluginImpl.class) → false
    (nếu PluginImpl implements B thay vì A)
```

Điều này có thể gây `ClassCastException` dù hai bản API có cùng source. Type identity ở JVM là **(binary name, defining loader)**.

**Thiết kế đúng:** shared API của host và plugin phải được nạp thành **cùng `Class<?>`**, thường bằng parent/delegation tới loader chung. Implementation và thư viện private có thể nằm dưới loader riêng nếu không làm hỏng types đi qua ranh giới.

Một interface không phải boundary type duy nhất: DTO, callback, exception, annotation, method parameter/return type, enum và class trong reflective signatures cũng có thể cần identity chung.

## 10. Thực hành C — implementation riêng nhưng contract từ parent

Tạo cấu trúc:

```text
shared-api-lab/
└── src/
    ├── api/api/Plugin.java
    ├── plugin/impl/EchoPlugin.java
    └── host/demo/SharedApiDemo.java
```

**`src/api/api/Plugin.java`:**

```java
package api;

public interface Plugin {
    String execute();
}
```

**`src/plugin/impl/EchoPlugin.java`:**

```java
package impl;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    @Override
    public String execute() {
        return "plugin ready";
    }
}
```

**`src/host/demo/SharedApiDemo.java`:**

```java
package demo;

import api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class SharedApiDemo {
    public static void main(String[] args) throws Exception {
        URL source =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader apiOwner = Plugin.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { source }, apiOwner)) {

            Class<?> implementation =
                    pluginLoader.loadClass("impl.EchoPlugin");
            Class<?> contract = implementation.getInterfaces()[0];

            System.out.println("implementation from child=" +
                    (implementation.getClassLoader() == pluginLoader));
            System.out.println("API shared=" + (contract == Plugin.class));
            System.out.println("assignable=" +
                    Plugin.class.isAssignableFrom(implementation));

            Plugin service = (Plugin) implementation
                    .getDeclaredConstructor()
                    .newInstance();
            System.out.println("result=" + service.execute());
        }
    }
}
```

Biên dịch trong `shared-api-lab`:

```sh
javac --release 17 -d api-out src/api/api/Plugin.java
javac --release 17 -cp api-out -d plugin-out src/plugin/impl/EchoPlugin.java
javac --release 17 -cp api-out -d host-out src/host/demo/SharedApiDemo.java
```

Chạy trên **Windows**:

```powershell
java -cp "host-out;api-out" demo.SharedApiDemo
```

Hoặc trên **Linux/macOS**:

```sh
java -cp "host-out:api-out" demo.SharedApiDemo
```

**Stdout dự kiến với cấu hình đã nêu:**

```text
implementation from child=true
API shared=true
assignable=true
result=plugin ready
```

`impl.EchoPlugin` chỉ có trong `plugin-out` nên được child định nghĩa. `api.Plugin` được host API loader tìm qua parent, do đó `EchoPlugin` thực sự implements cùng interface mà host sử dụng; cast hợp lệ.

Nếu đưa `plugin-out` lên host application classpath, parent-first có thể khiến implementation cũng được host nạp. **Không làm vậy trong thí nghiệm** vì mục đích là kiểm tra identity của child và parent riêng biệt.

## 11. Muốn cô lập lib private nhưng vẫn chia sẻ API thì sao?

Một mô hình plugin tốt thường muốn:

- **Parent-first cho `api.*` và Java platform types:** bảo vệ shared runtime identity.
- **Plugin-private cho `impl.*` và một số `vendor.*`:** cho phép phiên bản dependency khác nhau.
- **Có cơ chế xử lý collision rõ ràng:** tránh cùng một binary name được dùng vô tình ở hai nơi.
- **Chú ý signature biên giới:** nếu `api.Plugin.execute(vendor.JsonNode)` dùng library type, `JsonNode` đã thành một phần của boundary; không thể tùy tiện mỗi bên có một bản khác identity.

`URLClassLoader` với `loadClass` mặc định là **parent-first**, không có switch constructor “child-first for vendor package”. Muốn chính sách phức tạp, có thể viết custom loader override `loadClass`, nhưng đó là công việc khó: phải giữ `findLoadedClass`, khóa nạp lớp, tránh race, loading constraints, các tên `java.*` và chính sách module/resource. Cách đơn giản hơn khi có thể là **thiết kế lại shared/API dependency placement** để parent chỉ giữ contract thật sự cần chia sẻ.

Đừng cố đặt mọi dependency trong plugin JAR và đổi parent thành `null` ngay; việc đó có thể khiến `api.Plugin` không còn cùng runtime type với host.

## 12. Parent và resources: gần nhau nhưng không hoàn toàn đồng nhất

`URLClassLoader` có các phương thức:

```java
URL found = loader.getResource("config/settings.properties");
URL local = loader.findResource("config/settings.properties");
URL[] ownSources = loader.getURLs();
```

Đây là **snippet**: cần `loader` kiểu `URLClassLoader` và import `java.net.URL`.

- `getResource` theo cơ chế lookup của loader có thể trả resource từ parent trước.
- `findResource` của `URLClassLoader` tìm resource trong nguồn riêng của loader, không sử dụng parent theo cách `getResource` mặc định.
- `getURLs` chỉ mô tả URL roots đã được cấu hình cho child, không liệt kê URL parent.
- `getResourceAsStream` đọc resource thành stream (hoặc `null` nếu không tìm được), nên cần kiểm tra `null` và đóng stream.
- Resource trong named module có thể chịu encapsulation riêng; cùng loader nhìn thấy class không bảo đảm đọc được mọi resource không mở package.

Nếu cả host và plugin đều có `config/settings.properties`, parent-first resource lookup có thể khiến bản host được chọn. Hãy dùng `getResource`/`getResources` để kiểm tra thực tế và đặt namespace resource rõ ràng, thay vì xem đó là lỗi `ClassLoader.loadClass`.

**TCCL** (`Thread.currentThread().getContextClassLoader()`) cũng không tự bằng `loader.getParent()`. Một framework có thể dùng TCCL cho `ServiceLoader` discovery, nhưng chọn parent của `URLClassLoader` không tự thay đổi TCCL trên thread.

## 13. Đường dẫn URL chính xác và đóng gói dependency

Đối với thư mục output:

```java
URL classes =
        Path.of("plugin-out").toAbsolutePath().toUri().toURL();
```

Đây là snippet cần imports `java.net.URL` và `java.nio.file.Path`. `Path.toUri()` giúp tạo file URL hợp lệ, tránh ghép chuỗi `file:///...` sai khi tên thư mục có dấu cách.

Đối với JAR:

```java
URL jar = Path.of("plugins", "feature.jar")
        .toAbsolutePath().toUri().toURL();

URLClassLoader loader = new URLClassLoader(
        new URL[] { jar }, ClassLoader.getPlatformClassLoader());
```

Snippet chưa có vòng đời `close`, nên trong ứng dụng thực tế cần quản lý loader được tạo.

Kiểm tra:

1. URL tới directory phải trỏ đến **root của package layout**. Ví dụ `out/extension/Feature.class` tương ứng binary name `extension.Feature`, vậy URL phải trỏ `out/`.
2. URL tới JAR phải trỏ đúng **file JAR**, không chỉ thư mục đang chứa nhiều JAR mà ta nghĩ loader sẽ quét đệ quy.
3. Một JAR chỉ chứa implementation không tự cung cấp mọi transitive dependency. Runtime parent/URL khác phải nhìn thấy dependency cần thiết.
4. Nếu nhiều URL riêng của child chứa cùng class name, thứ tự tìm nguồn có thể tạo xung đột. Đóng gói tường minh và tránh duplicate lành mạnh hơn dựa vào thứ tự.
5. `getURLs()` cho biết URL riêng nhưng **không đủ** để xác định class nào parent đã chọn.
6. `URLClassLoader` phù hợp các nguồn classpath-style; chỉ đặt modular JAR vào URL không tự xây dựng một **JPMS module layer**.

## 14. Các lỗi thường gặp khi chọn parent sai

| Lỗi/triệu chứng | Điều cần xem | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException` | Parent và URL riêng đều không tìm tên class | Kiểm tra binary name, roots/JAR, parent, đường dẫn runtime |
| `NoClassDefFoundError` | Dependency cần lúc linking/initialization không được định nghĩa, hoặc init trước thất bại | Đọc `Caused by`, runtime JAR versions và initializer |
| `NoSuchMethodError` | Parent trả library cũ không có method descriptor mà plugin compile against | So `javap -s`, classpath parent, tránh version skew |
| `NoSuchFieldError` | Field name/descriptor ở runtime khác compile-time | So class files thực tế |
| `ClassCastException` dù tên interface giống | Host/plugin dùng hai definitions của shared API | In defining loaders; chia sẻ đúng `Class<?>` |
| `LinkageError` loader constraint violation | Signature xuyên loaders chứa types identity không tương thích | Kiểm tra toàn bộ boundary DTO/return/parameter types |
| `IllegalAccessError` | Runtime access/package/module restrictions | Kiểm tra visibility, JPMS readability/exports |
| Resource trả sai nội dung | Parent resource shadow child resource | `getResource`, `getResources`, resource namespace |
| `ServiceConfigurationError` | Service API/provider không cùng runtime identity hoặc lỗi provider | ServiceLoader/TCCL, runtime API, provider metadata |
| Plugin không unload | Host/threads/caches/TCCL giữ reference hoặc loader chưa được close | Quản lý lifecycle và giải phóng references |

**Không phải mọi lỗi trên xuất phát từ thiếu JAR.** Có lỗi do lookup, có lỗi do liên kết bytecode, có lỗi do type identity hoặc module access. Dùng loại exception/error và stacktrace để khoanh vùng.

## 15. Công cụ debug phạm vi phụ thuộc

Một đoạn helper cho class đã nạp:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defining loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

Đây là **method minh họa**, không phải chương trình độc lập. `getModule().getName()` có thể trả `null` cho unnamed module; đây là thông tin bình thường.

Có thể kiểm tra parent và URLs riêng:

```java
System.out.println("parent=" + pluginLoader.getParent());
System.out.println("urls=" +
        java.util.Arrays.toString(pluginLoader.getURLs()));
```

Khi nghi phiên bản class bị chọn sai, dùng `javap` đọc **binary signatures** ở từng artifact:

```sh
javap -classpath hostlib-out -s deps.Version
javap -classpath pluginlib-out -s deps.Version
javap -classpath plugin-out -c -v extension.Feature
```

Lệnh trên áp dụng từ thư mục ví dụ B sau khi compile. `javap` xác minh bytecode đã tham chiếu symbol nào; nó **không** cho biết runtime đã chọn class nào từ parent. Kết hợp với `Class.getClassLoader()`.

Trên HotSpot hỗ trợ Unified Logging:

```sh
java -Xlog:class+load=info -cp "host-out:hostlib-out" demo.DependencyChoiceDemo
```

Ví dụ `-cp` dùng cú pháp Linux/macOS; Windows thay `:` bằng `;`. Log nạp lớp có thể dài và phụ thuộc runtime; nó giúp xem nguồn class bytes, nhưng không chứng minh class initialization hoặc method resolution đã hoàn tất.

## 16. Vòng đời URLClassLoader và đổi plugin

`URLClassLoader` triển khai `Closeable` và có thể dùng `try-with-resources` như các bài thực hành:

```java
try (URLClassLoader plugin = new URLClassLoader(urls, parent)) {
    Class<?> feature = plugin.loadClass("extension.Feature");
    // Dùng feature trong lúc loader còn phục vụ lookup.
}
```

Đây là snippet với `urls` và `parent` có sẵn. `close()` đóng các resource handles mà loader quản lý. **Không có nghĩa mọi class/object của plugin đã unload lập tức**.

Lưu ý:

- Một plugin đang chạy có thể cần lazy-load dependencies; **đừng close loader trước khi kết thúc vòng đời sử dụng plugin**.
- Host registry có thể đang giữ plugin objects, `Class<?>`, reflective `Method`, callbacks hoặc thread context class loader; những references này có thể giữ loader sống.
- Thay file JAR trên đĩa không tự thay thế `Class<?>` đã được định nghĩa trước đó.
- Reload nên tạo loader instance mới và plugin object mới, dừng instance cũ, giải phóng tham chiếu và kiểm tra contract API version.
- Shared API dùng chung qua parent nên ổn định qua vòng đời plugin; không tự định nghĩa lại bản sao contract mỗi lần reload.

## 17. Checklist chọn parent trước khi triển khai

1. Liệt kê tất cả **boundary types**: SPI, DTO, callback, exception, annotations và types trong method descriptors.
2. Xác định **defining loader thực** của shared API; đừng đoán system loader chỉ vì host đang chạy.
3. Liệt kê các **dependency private** và phiên bản host có thể trùng binary name.
4. Chọn parent (system, platform, bootstrap/null hay custom API loader) từ hai tập trên.
5. Kiểm tra child URL roots: directory/JAR URLs chính xác, có đủ các private dependency cần thiết.
6. Xác định parent-first có gây shadowing không; chỉ dùng custom child-first khi hiểu rõ rủi ro.
7. Integration test **plugin JAR qua loader thật**, không nhét plugin JAR lên application classpath khi mục tiêu là kiểm tra isolation.
8. Assert shared API identity bằng `isAssignableFrom` hoặc `Class<?> == Class<?>`, không chỉ `getName()`.
9. Quan sát resource URLs và TCCL nếu plugin có config/service discovery.
10. Kiểm tra JPMS module rules nếu ứng dụng dùng named modules.
11. Quản lý `close`, plugin lifecycle, callbacks, threads và references.
12. Không xem class loader là sandbox bảo mật cho code không đáng tin cậy.

### Test minh họa

```java
if (pluginLoader.getParent() != expectedParent) {
    throw new AssertionError("Wrong parent");
}
if (!SharedPluginApi.class.isAssignableFrom(implementationClass)) {
    throw new AssertionError("Wrong API identity");
}
```

Đây là snippet cần biến `pluginLoader`, `expectedParent`, `implementationClass` cùng kiểu `SharedPluginApi` có thật. Nếu implementation **bắt buộc** do child định nghĩa, có thể thêm `implementationClass.getClassLoader() == pluginLoader`; không áp dụng assertion ấy cho class được parent cung cấp theo thiết kế.

## 18. Những nhầm lẫn cần tránh

- **“`new URLClassLoader(urls)` mặc định parent là bootstrap.”** Sai: mặc định là system class loader.
- **“`getURLs()` rỗng nghĩa là loader không thể tìm class.”** Sai: delegation vẫn hoạt động.
- **“Parent có dependency v1, plugin URL chứa v2 thì v2 luôn thắng.”** Sai với parent-first mặc định.
- **“Parent được copy tất cả các JAR sang child.”** Sai: parent trả class từ namespace/logic của chính nó.
- **“Parent class loader là Java superclass của URLClassLoader.”** Sai: parent là object tham chiếu.
- **“Đổi parent sang platform sẽ giữ nguyên mọi host-defined SPI.”** Không mặc định; platform không phải application classpath loader.
- **“Parent null là giải pháp sandbox an toàn.”** Sai: class loader visibility không phải biên giới bảo mật đầy đủ.
- **“Cùng tên interface là đủ để host cast object plugin.”** Sai: runtime identity còn phụ thuộc defining loader.
- **“Maven compile được thì URLClassLoader chắc chắn thấy tất cả transitive dependencies.”** Sai: runtime classpath phải được cấu hình thực sự.
- **“URL trỏ vào thư mục plugin sẽ tự quét mọi JAR con.”** Không mặc định.
- **“`close()` xóa ngay classes đang sử dụng.”** Sai: garbage collection/unloading phụ thuộc references.
- **“Resource lookup và class lookup lúc nào cũng có cùng thứ tự/namespace.”** Phải kiểm tra API và loader thực tế.

## 19. Câu hỏi tự kiểm tra

**1. Constructor một tham số `URLClassLoader(urls)` chọn parent gì?** System class loader.

**2. Vì sao child URLs rỗng vẫn tìm được `java.lang.String`?** Child có thể ủy quyền cho parent/ancestor hoặc bootstrap.

**3. Vì sao cùng URL array nhưng app parent và platform parent cho kết quả khác ở ví dụ A?** Vì chúng có phạm vi class visibility khác nhau qua delegation.

**4. Parent chứa `deps.Version` v1, child URL chứa v2: bản nào thường được chọn?** Parent v1 với `loadClass` parent-first mặc định.

**5. Bản v1 thiếu method mà plugin yêu cầu có thể gây lỗi gì?** `NoSuchMethodError`, tùy binary mismatch và thời điểm symbol được sử dụng.

**6. `getURLs()` có phản ánh mọi JAR parent nhìn thấy không?** Không; nó chỉ trả URL riêng của child.

**7. Khi nào chọn platform loader?** Khi plugin cần Java platform APIs mà không mặc định thừa hưởng toàn application classpath, và shared API được thiết kế tách biệt.

**8. Nếu plugin bắt buộc implements `api.Plugin` do host định nghĩa, chọn parent thế nào?** Đảm bảo loader plugin giải quyết interface qua **đúng defining loader của shared API**.

**9. Hai class cùng binary name do hai loaders định nghĩa có cùng runtime type không?** Không, type identity gồm cả defining loader.

**10. Parent null có chắc nhìn thấy tất cả Java SE classes không?** Không trên Java 9+; một số platform classes không thuộc bootstrap.

**11. Parent object có phải superclass Java của URLClassLoader không?** Không; `getParent()` và `getSuperclass()` mô tả hai quan hệ khác nhau.

**12. `close()` có làm plugin unload tức thì không?** Không; cần giải phóng references và JVM quyết định class unloading.

## 20. Nguồn chuẩn và kết luận

- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructor parent, `getURLs`, `findClass`, `findResource`, `close`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, `getParent`, `getSystemClassLoader`, `getPlatformClassLoader`.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader` và `isAssignableFrom` khi kiểm tra type identity.
- [Java Virtual Machine Specification Java SE 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining/initiating loaders, runtime type identity, linking và loading constraints.
- [JDK 17 javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra method descriptors và bytecode để debug binary mismatch.

**Quy tắc nhớ:** `URLClassLoader` có **nguồn class riêng trong URL array**, nhưng **được nhìn thấy các dependency parent có thể cung cấp qua delegation**. Parent-first giúp chia sẻ hợp đồng API, đồng thời có thể khiến phiên bản host che phiên bản plugin. Chọn parent theo **shared API identity và private dependency boundaries**, sau đó kiểm thử chính xác loader nào định nghĩa từng class — không chỉ nhìn tên JAR hoặc tên class.
