# Thiết kế kiểu API dùng chung tại ranh giới nhiều loader

Khi một ứng dụng Java có nhiều **class loader** — chẳng hạn host ứng dụng và những loader riêng cho plugin — một lớp có tên `api.Greeter` có thể xuất hiện ở nhiều nơi. Điều quan trọng là: **hai class có cùng binary name nhưng do hai defining loader khác nhau định nghĩa không phải cùng một kiểu ở thời gian chạy**. Đặc tính này quyết định trực tiếp cách thiết kế API dùng chung, gọi callback, truyền DTO, xử lý exception và nạp phiên bản plugin.

**Mục tiêu của bài:** tạo một ranh giới host–plugin mà cả hai phía dùng **cùng đối tượng `Class<?>`** cho contract cần chia sẻ, trong khi implementation và dependency riêng vẫn có thể được định nghĩa trong loader của plugin. Từ nguyên tắc này, ta sẽ thiết kế dependency, chọn parent/delegation, kiểm chứng bằng `==`/`isAssignableFrom`, xem lỗi thường gặp và chạy các ví dụ Java 17+.

## 1. Vấn đề gốc: "cùng tên" chưa đủ để là "cùng kiểu"

Theo mô hình JVM, một reference class/interface ở runtime được định danh bởi cặp:

```text
(binary name, defining class loader)
```

Ví dụ cùng có binary name `api.Greeter`:

```text
AppLoader     defines api.Greeter   → type A
PluginLoader  defines api.Greeter   → type B

A.getName().equals(B.getName())    → true
A == B                              → false
```

Vì thế, một object implements `api.Greeter` phiên bản B **không tự động** là instance của `api.Greeter` phiên bản A. JVM kiểm tra danh tính runtime type; nó không so tên gói hay chữ ký source rồi đoán rằng hai loại có thể ép kiểu cho nhau.

Hậu quả thường gặp:

- `ClassCastException`: object plugin không cast được sang interface host dù thông báo nhìn như `api.Greeter cannot be cast to api.Greeter`.
- `Class.isAssignableFrom(...)` trả `false` dù hai class có tên và method giống nhau.
- `ServiceLoader` hoặc reflection tìm được implementation, nhưng host không chấp nhận nó là subtype của service interface đã biết.
- Method/field signature đi qua hai loader nhận các class cùng tên nhưng khác identity; JVM có thể phát hiện xung đột **loading constraints** và báo `LinkageError`.
- DTO, exception, callback type hoặc enum không tương thích ở runtime vì một phía sử dụng bản định nghĩa khác.

**Quy tắc thiết kế:** *Những kiểu xuất hiện trong hợp đồng trao đổi giữa host và plugin phải được xác định rõ loader sở hữu và được cả hai phía resolve về cùng runtime type.* Không nhất thiết mọi class của hai phía dùng chung; chỉ những **boundary types** cần chung identity.

## 2. Xác định đâu là contract, đâu là implementation

Hãy chia nhiệm vụ của một plugin thành ba vùng:

```text
                  HOST APPLICATION
           ┌──────────────────────────────┐
           │ host orchestration / UI       │
           │ registry, lifecycle, config   │
           └──────────────┬───────────────┘
                          │
                   SHARED API
           ┌──────────────▼───────────────┐
           │ api.Greeter                  │
           │ api.Request / api.Response   │
           │ api.PluginException          │
           │ api.PluginContext (callback)  │
           └──────────────▲───────────────┘
                          │
                   PLUGIN INSTANCE
           ┌──────────────┴───────────────┐
           │ impl.PluginGreeter           │
           │ plugin-private dependencies  │
           │ optional resource/config     │
           └──────────────────────────────┘
```

Ở đây:

- **Host** điều phối, cung cấp API dùng chung và là bên sử dụng kết quả.
- **Shared API** chứa kiểu mà cả host lẫn plugin cần biết. Đây là một **hợp đồng ổn định**, nên thường nằm trong một artifact nhỏ và được định nghĩa bởi **loader chung/ancestor**.
- **Plugin implementation** nằm trong artifact riêng. Loader riêng được quyền định nghĩa các class implementation, miễn là những tham chiếu đến shared API resolve về class mà host đang sử dụng.
- **Plugin-private dependencies** là các thư viện triển khai nội bộ. Tùy thiết kế có thể cách ly phiên bản; nếu một type từ thư viện riêng xuất hiện trong method signature public xuyên boundary, nó lại trở thành một phần của contract và cần chính sách riêng.

Một mốc quan trọng: "shared" ở đây nói về **định danh class tại runtime**, không nhất thiết là "hai bên có hai bản sao cùng tệp JAR". Hai bản JAR có bytes y hệt nhau nhưng bị hai loader tự `defineClass` riêng vẫn có thể tạo hai runtime types khác nhau.

## 3. Nguyên tắc kiến trúc: API chung do một loader được cả hai phía sử dụng

Thiết kế thông dụng nhất là **parent-first cho shared API**:

```text
                     host/application loader
                       defines api.Greeter
                                ▲
                     parent/delegation
                                │
                     plugin URLClassLoader
                      defines impl.PluginGreeter
                                │
               uses api.Greeter defined above
```

Khi `PluginGreeter` khai báo `implements api.Greeter`, plugin loader phải **ủy quyền** việc tìm `api.Greeter` về loader đã định nghĩa interface cho host. Kết quả mong muốn:

```java
Class<?> contract = api.Greeter.class;
Class<?> pluginClass = pluginLoader.loadClass("impl.PluginGreeter");

boolean canUse = contract.isAssignableFrom(pluginClass);
```

Đoạn trên là **snippet minh họa**, cần `pluginLoader` và các lớp tương ứng được khai báo. Nếu ranh giới được cấu hình đúng, `canUse == true`.

Chọn loader chung không nhất thiết luôn là `ClassLoader.getSystemClassLoader()`. Trong application server, môi trường OSGi hoặc module layer tùy biến, host API có thể nằm ở loader chuyên biệt. Điều bất biến cần bảo vệ là: **plugin và host cùng dùng một `Class<?>` cho mỗi type trong contract**.

### Vì sao không chỉ kiểm tra `getName()`?

`getName()` trả binary name. Hai class từ hai loaders đều có thể trả `"api.Greeter"`. Kiểm tra hiệu quả:

```java
hostApiClass == pluginApiClass
hostApiClass.isAssignableFrom(pluginImplementationClass)
hostApiClass.getClassLoader()
pluginApiClass.getClassLoader()
```

Hãy kiểm tra cả **danh tính class** và **loader định nghĩa**. `getClassLoader() == null` có thể biểu diễn bootstrap loader, không phải lỗi.

## 4. Thực hành A — một shared interface, host và plugin dùng chung

Ví dụ hoàn chỉnh dưới đây được thiết kế để chạy trên **JDK 17+**, không cần framework. Ta chủ động biên dịch API, plugin và host vào **các thư mục riêng**, rồi chỉ đưa **API + host** lên application classpath lúc chạy. Plugin implementation sẽ được tải từ thư mục riêng bằng `URLClassLoader`.

Cấu trúc:

```text
shared-api-lab/
├── src/
│   ├── api/
│   │   └── api/
│   │       └── Greeter.java
│   ├── plugin/
│   │   └── impl/
│   │       └── PluginGreeter.java
│   └── host/
│       └── host/
│           └── HostMain.java
├── shared-out/      (tạo bởi javac)
├── plugin-out/      (tạo bởi javac)
└── host-out/        (tạo bởi javac)
```

**Tệp `src/api/api/Greeter.java`:**

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

**Tệp `src/plugin/impl/PluginGreeter.java`:**

```java
package impl;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    public PluginGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp `src/host/host/HostMain.java`:**

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class HostMain {
    public static void main(String[] args) throws Exception {
        URL pluginLocation =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader hostLoader = HostMain.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                 new URLClassLoader(new URL[] { pluginLocation }, hostLoader)) {
            Class<?> implementation =
                    pluginLoader.loadClass("impl.PluginGreeter");
            Class<?> pluginApi = implementation.getInterfaces()[0];

            System.out.println("plugin defined locally: " +
                    (implementation.getClassLoader() == pluginLoader));
            System.out.println("same API Class: " +
                    (pluginApi == Greeter.class));
            System.out.println("assignable: " +
                    Greeter.class.isAssignableFrom(implementation));

            Object instance =
                    implementation.getDeclaredConstructor().newInstance();
            Greeter service = (Greeter) instance;
            System.out.println("result: " + service.greet("Java"));
        }
    }
}
```

Từ thư mục `shared-api-lab`, biên dịch bằng JDK 17+:

```sh
javac --release 17 -d shared-out src/api/api/Greeter.java
javac --release 17 -cp shared-out -d plugin-out src/plugin/impl/PluginGreeter.java
javac --release 17 -cp shared-out -d host-out src/host/host/HostMain.java
```

Chạy trên **Windows PowerShell/CMD**, nơi classpath dùng dấu `;`:

```powershell
java -cp "host-out;shared-out" host.HostMain
```

Trên **Linux/macOS**, thay dấu `;` bằng `:`:

```sh
java -cp "host-out:shared-out" host.HostMain
```

**Stdout chuẩn của chương trình trên cấu hình đã nêu:**

```text
plugin defined locally: true
same API Class: true
assignable: true
result: Hello, Java
```

### Vì sao ví dụ A thành công?

1. Khi compile `PluginGreeter`, compiler thấy `api.Greeter` từ `shared-out`; class file ghi tham chiếu tới `api.Greeter`.
2. Runtime application classpath chỉ có `host-out` và `shared-out`. Application/host loader nạp `host.HostMain` và `api.Greeter`.
3. `pluginLoader` nhận **hostLoader làm parent** và chỉ có URL tới `plugin-out`. Nó tìm `impl.PluginGreeter` bằng `findClass`/`defineClass` của `URLClassLoader`, nên implementation thuộc plugin loader.
4. Khi cần `api.Greeter` cho `implements`, plugin loader tuân theo parent-first và nhận **cùng interface `Class<?>`** đã có ở host. Điều này làm `pluginApi == Greeter.class` đúng.
5. Object `PluginGreeter` là subtype runtime thật của `api.Greeter` mà host biết, vì thế `Greeter.class.isAssignableFrom(implementation)` đúng và ép kiểu `(Greeter)` thành công.
6. Host không cần compile-time dependency đến `impl.PluginGreeter`; nó chỉ có compile-time dependency đến API. Đây là điểm quan trọng để thay plugin implementation độc lập.

**Phạm vi bài thực hành:** URL từ `Path.of("plugin-out")` phụ thuộc **working directory**. Lệnh cần chạy đúng từ `shared-api-lab`. Ví dụ giữ đơn giản, chưa có cơ chế discovery, quản lý phiên bản, security boundary, exception translation hay quản lý vòng đời phức tạp.

## 5. Thực hành B — cùng interface name nhưng hai defining loaders

Bây giờ giữ nguyên **`Greeter.java`** và **`PluginGreeter.java`** ở thực hành A, nhưng cố tình cho plugin loader nhìn thấy **bản sao API** trong `shared-out` trong khi **parent** chỉ là platform loader.

Tạo thêm **`src/host/host/BrokenBoundary.java`**:

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class BrokenBoundary {
    public static void main(String[] args) throws Exception {
        URL pluginLocation =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        URL apiLocation =
                Path.of("shared-out").toAbsolutePath().toUri().toURL();

        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { pluginLocation, apiLocation },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> implementation =
                    isolated.loadClass("impl.PluginGreeter");
            Class<?> apiSeenByPlugin =
                    implementation.getInterfaces()[0];

            System.out.println("same API name: " +
                    apiSeenByPlugin.getName().equals(Greeter.class.getName()));
            System.out.println("same API Class: " +
                    (apiSeenByPlugin == Greeter.class));
            System.out.println("assignable: " +
                    Greeter.class.isAssignableFrom(implementation));

            Object instance =
                    implementation.getDeclaredConstructor().newInstance();
            try {
                Greeter service = (Greeter) instance;
                System.out.println(service.greet("Java"));
            } catch (ClassCastException e) {
                System.out.println("cast failed: " +
                        e.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch bằng lại đúng shared API; không thêm plugin lên host classpath:

```sh
javac --release 17 -cp shared-out -d host-out src/host/host/BrokenBoundary.java
```

Chạy trên Windows:

```powershell
java -cp "host-out;shared-out" host.BrokenBoundary
```

Hoặc Linux/macOS:

```sh
java -cp "host-out:shared-out" host.BrokenBoundary
```

**Stdout chuẩn:**

```text
same API name: true
same API Class: false
assignable: false
cast failed: ClassCastException
```

**Vì sao thất bại?**

- Host loader định nghĩa `api.Greeter` từ application classpath.
- `isolated` sử dụng **platform loader làm parent**. Trong cách chạy này platform loader không tìm class tự tạo `api.Greeter` trong application classpath. Do URL của `isolated` bao gồm `shared-out`, chính `isolated` định nghĩa **một bản `api.Greeter` thứ hai**.
- Plugin implementation `impl.PluginGreeter` implements bản API do `isolated` định nghĩa, không phải bản API từ host loader.
- Tên cùng là `api.Greeter`, song hai `Class<?>` khác identity. Vì thế kiểu implementation không assignable với interface host và lệnh cast thất bại.

Đây là ví dụ **cố ý hỏng** để làm rõ class identity; nó **không phải mẫu thiết kế plugin đúng**. Không cần sửa `extends` của `PluginGreeter` để cứu cast. Cần làm cho cả host và plugin resolve `api.Greeter` qua **cùng loader sở hữu shared API** — như cấu hình parent ở thực hành A.

### "Nếu hai JAR giống hệt nhau thì sao?"

Kết quả vẫn có thể thất bại. Class identity đến từ cặp **binary name + defining loader**, không lấy hash nội dung file để tự gộp runtime types. Ngay cả bytecode bằng nhau từng byte, hai lần `defineClass` bởi hai loader vẫn tạo hai runtime classes khác nhau.

## 6. Thực hành C — hai plugin loaders, một contract và hai implementation types riêng

Cùng một **`PluginGreeter.class`** có thể được định nghĩa độc lập bởi hai loader instances, nhưng **cả hai implementation vẫn là subtype của cùng API** nếu hai loader cùng delegation contract về host.

Tạo `src/host/host/TwoPlugins.java`:

```java
package host;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class TwoPlugins {
    public static void main(String[] args) throws Exception {
        URL location =
                Path.of("plugin-out").toAbsolutePath().toUri().toURL();
        ClassLoader sharedParent = Greeter.class.getClassLoader();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] { location }, sharedParent);
             URLClassLoader second = new URLClassLoader(
                     new URL[] { location }, sharedParent)) {

            Class<?> one = first.loadClass("impl.PluginGreeter");
            Class<?> two = second.loadClass("impl.PluginGreeter");

            System.out.println("same implementation name: " +
                    one.getName().equals(two.getName()));
            System.out.println("same implementation Class: " + (one == two));
            System.out.println("first matches API: " +
                    Greeter.class.isAssignableFrom(one));
            System.out.println("second matches API: " +
                    Greeter.class.isAssignableFrom(two));

            Greeter a = (Greeter) one.getDeclaredConstructor().newInstance();
            Greeter b = (Greeter) two.getDeclaredConstructor().newInstance();
            System.out.println(a.greet("A"));
            System.out.println(b.greet("B"));
        }
    }
}
```

Biên dịch (giữ `shared-out` và `plugin-out` từ thực hành A):

```sh
javac --release 17 -cp shared-out -d host-out src/host/host/TwoPlugins.java
```

Chạy trên Windows:

```powershell
java -cp "host-out;shared-out" host.TwoPlugins
```

Trên Linux/macOS:

```sh
java -cp "host-out:shared-out" host.TwoPlugins
```

**Stdout chuẩn:**

```text
same implementation name: true
same implementation Class: false
first matches API: true
second matches API: true
Hello, A
Hello, B
```

Điều này cho thấy **API identity dùng chung** và **implementation isolation** có thể tồn tại đồng thời:

```text
                   Host API Loader
                 defines api.Greeter
                      ▲      ▲
                      │      │
              PluginLoader 1  PluginLoader 2
                  │                │
      defines impl.PluginGreeter   defines impl.PluginGreeter
      (implementation type #1)    (implementation type #2)

PluginLoader1.impl.PluginGreeter != PluginLoader2.impl.PluginGreeter

nhưng cả hai đều implements cùng HostLoader.api.Greeter
```

Với nhiều plugin instances, có thể dễ dàng tạo các đối tượng implementation riêng và giao tiếp qua contract chung. Điều đó không làm plugin code an toàn trước rủi ro, không miễn trừ nhu cầu quản lý loader lifecycle và không bảo đảm isolate mọi static state hay native library theo cách giống tiến trình riêng.

## 7. Quy tắc đóng gói artifact: contract đi một đường, implementation đi đường khác

Trong bản triển khai thực tế có thể có:

```text
plugins/
  shared-api.jar           # bản dùng chung do host kiểm soát
  host-app.jar             # code orchestration của host
  plugin-a.jar             # implementation A
  plugin-b.jar             # implementation B
```

Điểm quyết định không phải tên file. Hãy xác định **dependency ownership**:

| Artifact/type | Bên sở hữu class identity | Vì sao |
| --- | --- | --- |
| `api.Plugin`, `api.PluginContext` | Loader dùng chung được host và plugin delegation tới | Plugin objects phải assignable về interface host; callback parameter phải cùng type. |
| `api.Request`, `api.Response` | Thường loader chung, hoặc dùng dạng trao đổi độc lập class identity | DTO cần truyền qua ranh giới một cách an toàn. |
| `api.PluginException` | Loader chung nếu host phải `catch` type này | Exception type là một phần của boundary contract. |
| `impl.PluginA` | Loader của plugin A | Implementation được phép thay độc lập với host. |
| `impl.PluginB` | Loader của plugin B | Có thể cô lập class/static state/dependency với A. |
| Thư viện triển khai nội bộ | Plugin loader, nếu không rò qua contract | Hỗ trợ các plugin dùng những phiên bản dependency khác nhau. |
| Java SE classes | Bootstrap/platform loaders theo JDK | Các type như `String` hoặc `List` là platform types chung, nhưng generic type arguments có thể chứa app/plugin-specific classes. |

**Khuyến nghị build:** Plugin **compile against** shared API nhưng runtime wiring bảo đảm API được resolve từ loader chung. Nếu artifact plugin đóng gói kèm API để dễ build, vẫn cần cơ chế loại bản sao khỏi phần nạp động hoặc đảm bảo chính sách delegation ưu tiên shared API; đừng để plugin child-first tự định nghĩa lại nó.

Với Gradle/Maven, có thể dùng cấu hình dependency compile-time phù hợp để tránh đóng gói trùng shared API vào plugin distribution. Tuy nhiên tên cấu hình như `compileOnly` hoặc `provided` chỉ giải quyết **artifact packaging**; đúng class identity còn phụ thuộc runtime loader graph và cách các loader resolve class.

### Làm sao biết một thư viện phải là shared hay private?

Đặt câu hỏi: **Kiểu từ thư viện ấy có xuất hiện tại ranh giới public mà cả host và plugin cần tương tác qua JVM type system không?**

- Nếu `api.Plugin.execute(Request)` nhận `api.Request`, kiểu `Request` là boundary type.
- Nếu `PluginGreeter` dùng `org.example.json.InternalParser` chỉ trong phương thức private, parser có thể là plugin-private dependency.
- Nếu `api.Plugin.execute(com.vendor.JsonNode)` sử dụng một `JsonNode` ngoài shared API, **phiên bản và identity của `JsonNode` phải được thiết kế chung**, hoặc cần đổi boundary về DTO có nguồn sở hữu rõ ràng.
- Nếu host truyền `java.util.Map<String, Object>`, lớp `Map` là platform type chung nhưng các giá trị `Object` có thể chứa instance plugin-private. Điều này làm contract có vẻ trung lập mà vẫn tiềm ẩn lỗi cast hoặc lifecycle.

**Độ rộng ranh giới càng nhỏ và rõ, nguy cơ leak các kiểu implementation càng ít.**

## 8. Thiết kế một API contract đủ ổn định

Một interface chung có thể được tổ chức như sau:

```java
package api;

public interface Plugin {
    String id();

    Result execute(Request request, PluginContext context);
}
```

Ví dụ trên là **một đoạn minh họa về API thiết kế**, không tự biên dịch cho đến khi khai báo thêm `Request`, `Result` và `PluginContext`. Nó thể hiện ba nhóm dữ liệu thường có trong plugin API:

1. **Thông tin nhận dạng/chức năng**: `id()`, version hoặc capability metadata.
2. **Dữ liệu vào/ra**: request/response được định nghĩa trong shared API.
3. **Callback/facade do host cung cấp**: `PluginContext` cho plugin truy cập những khả năng host cố ý công khai.

### DTO: lớp Java hay dữ liệu trung lập?

Có hai hướng:

**A. Shared DTO Java types.** Host và plugin dùng chung `api.Request`, `api.Result` từ cùng defining loader. Ưu điểm: kiểm tra kiểu compile-time và runtime trực tiếp. Nhược điểm: thay đổi binary API cần kế hoạch version và compatibility; DTO chỉ dùng được khi mỗi bên có cùng class identity.

**B. Protocol trung lập với class loader.** Dùng JSON, byte array, protobuf, message schema hoặc record dữ liệu qua giao diện chuyển đổi được định nghĩa rõ. Ưu điểm: giảm phụ thuộc runtime class identity của payload nội bộ, có thể nối sang plugin chạy trong tiến trình khác. Nhược điểm: cần validation, schema evolution và xử lý lỗi deserialize. Dù payload là bytes/JSON, những Java types ở biên giới **gọi API trực tiếp** (ví dụ interface xử lý `byte[]`) vẫn phải có identity tương thích.

### Exception qua ranh giới

Nếu contract khai báo `throws api.PluginException`, host chỉ có thể catch đúng runtime exception subtype mà nó biết khi plugin dùng cùng class identity của `api.PluginException`. Nếu plugin định nghĩa bản sao cùng tên qua loader khác, catch clause theo kiểu host **không tự bắt bản sao đó**.

Trong thực tế nên thống nhất rõ:

- Checked exception có phải một phần của contract không?
- Runtime exception từ thư viện private có được truyền xuyên boundary, hay được plugin adapter ánh xạ thành lỗi chuẩn?
- Có cần error code, message, causal chain và redaction để host không phụ thuộc plugin implementation?
- Plugin ném `LinkageError`, `OutOfMemoryError` hay lỗi nghiêm trọng khác thì host vận hành thế nào?

Với API public, tránh đưa những type triển khai dễ biến động trực tiếp vào method signature.

### Callback phải đi qua cùng shared API

Nếu host truyền một object implements `api.PluginContext`, plugin sẽ cast và gọi nó. Để callback an toàn, hai phía phải thấy đúng `api.PluginContext` runtime type. Nếu plugin tải riêng bản sao của context interface, lỗi identity xuất hiện ngay ở chiều **host → plugin**, dù chiều trả về plugin object đã được xử lý.

## 9. Method signatures, binary compatibility và loading constraints

Một API contract là **binary contract**. JVM liên kết method/field references bằng tên và **descriptor**; descriptor chứa parameter types và return type theo định dạng JVM.

Ví dụ method Java:

```java
api.Result execute(api.Request request)
```

Phần descriptor khái niệm:

```text
(Lapi/Request;)Lapi/Result;
```

Nếu host compile theo bản API có `execute(Request):Result` nhưng plugin hoặc runtime có signature khác, lỗi có thể là `NoSuchMethodError`, `AbstractMethodError` hoặc loại `LinkageError` phù hợp tùy thay đổi và thời điểm sử dụng.

**Loading constraints** bảo vệ type safety khi các method signature đi qua loaders khác nhau. Ví dụ host và plugin có method cùng descriptor đòi hỏi `api.Request` phải cùng identity nhưng loader mapping lại định nghĩa hai kiểu khác nhau; JVM có thể từ chối liên kết với một `LinkageError` do loader constraint violation. Không nên "sửa" bằng reflection ép gọi method theo tên: vi phạm identity vẫn tồn tại.

### Nâng version API phải có chính sách

Một vài nguyên tắc thực tế:

- Đừng thay đổi return type, parameter types, static/instance hoặc xóa method được plugin cũ sử dụng rồi kỳ vọng binary compatibility tự giữ.
- Thêm abstract method vào interface có thể làm implementation đã biên dịch từ API cũ thiếu implementation khi method mới được gọi; những thay đổi tưởng là source-compatible có thể tạo lỗi runtime.
- Thêm `default` method có thể hỗ trợ một số trường hợp tiến hóa interface, nhưng cũng có nguy cơ xung đột default methods giữa interfaces; cần thử trên các plugin versions hỗ trợ.
- Nếu thay đổi contract lớn, có thể dùng API version riêng, adapter hoặc lifecycle migration thay vì cố chia sẻ nhiều bản `api.Plugin` có cùng binary name trong cùng một ranh giới.
- Dùng integration tests tải **JAR plugin đã phát hành** qua class loader thực tế, không chỉ compile cả host và plugin lại từ source mới nhất.

**Quan trọng:** Hai thư viện có cùng Java API ở source-level không đảm bảo tương thích binary ở runtime khi class files được xây từ các phiên bản khác nhau.

## 10. Thiết kế loader graph và delegation policy

Một kiến trúc plugin phải mô tả được:

```text
                Shared/Host API Loader
                  │  api.*, JDK types
                  ▲
                  │ parent-first cho api.*
          ┌───────┴────────┐
          │                │
      Plugin A           Plugin B
      impl.a.*           impl.b.*
      libs A             libs B
```

Sơ đồ diễn tả mục tiêu **shared API từ parent**, **implementation riêng tại child**. Trên một số nền tảng, shared API do một loader riêng định nghĩa và host cũng sử dụng loader đó; trên kiến trúc khác có thể dùng application loader.

### Parent-first

Mẫu mặc định của `ClassLoader.loadClass` thường thử parent trước rồi mới `findClass`. Nó phù hợp nếu shared API nằm ở parent và plugin không có tên lớp collision ngoài ý muốn. Tuy nhiên parent-first cho **mọi class** có thể khiến plugin không tải được version thư viện private mà nó cần khi host có một class cùng tên.

### Child-first có ngoại lệ cho shared API

Một số hệ thống tự viết `loadClass` để ưu tiên implementation/dependency của plugin, nhưng **dành các package contract và JDK classes cho parent**. Đây là thiết kế có thể dùng, nhưng phải tính đến:

- `java.*` không được tự ý định nghĩa trong loader application.
- API packages phải được ủy quyền nhất quán, kể cả types gián tiếp trong signatures.
- `findLoadedClass`, khóa nạp lớp, tính đồng thời và nguy cơ circular loading cần xử lý.
- Package sealing, signed JAR và module accessibility có thể giới hạn cách định nghĩa classes.
- Resource lookup có thể có chính sách riêng; loader tìm đúng class chưa chắc tìm đúng resource.
- Native libraries và static state có giới hạn isolation khác với Java class namespace.

**Không viết child-first loader chỉ để "sửa" một `ClassCastException`** mà chưa kiểm tra nguyên nhân bản sao của API. Trong nhiều trường hợp, sửa parent graph và dependency placement đơn giản, dễ kiểm thử hơn.

### Vì sao platform loader chưa chắc đủ?

`ClassLoader.getPlatformClassLoader()` nhìn thấy platform classes nhưng không mặc nhiên nhìn thấy shared API của ứng dụng trong unnamed application classpath. Ví dụ B cố ý chọn platform parent để tách khỏi host API. Nếu plugin phải nhận interface do host định nghĩa, parent nên là loader nhìn thấy interface ấy hoặc cơ chế bridging phải rõ ràng.

**Parent của loader là quan hệ object**, không phải kế thừa Java: `new URLClassLoader(urls, hostLoader)` truyền một instance, quyết định delegation. Java class của plugin loader không cần `extends` Java class của host loader.

## 11. JPMS, module layers và khả năng truy cập

Từ Java 9, module là một chiều khác của Java runtime. Class loader, module resolution và module access không thể được coi là một thứ.

Các câu hỏi cần tách:

1. **Module nào chứa shared API?** Ví dụ named module `com.example.plugin.api` hoặc package ở unnamed module.
2. **Module đó được resolve vào layer nào?** Có module trên path không có nghĩa nó đã được resolve.
3. **Module nào đọc module nào?** Named module caller phải có readability phù hợp (thường qua `requires`).
4. **Package nào được export?** Public class không tự động có thể truy cập nếu package không export.
5. **Loader nào định nghĩa mỗi class?** Hai module hay layers có thể dùng các loaders khác nhau; tránh giả định cùng tên module chắc chắn là cùng type.
6. **Có dùng reflection sâu không?** Cần xem `opens` và quyền truy cập tương ứng, không chỉ `exports`.

Ví dụ module descriptor cho một artifact shared API:

```java
module com.example.plugin.api {
    exports api;
}
```

Đây là **module-info.java minh họa**, không phải source độc lập chạy ngay với các thư mục classpath của thực hành A–C. Một plugin named module tiêu thụ API sẽ khai báo `requires com.example.plugin.api;` khi phù hợp. Ở môi trường JPMS thực tế, thiết kế module layer và loader mapping phải giữ cùng contract class identity; chỉ ghi `requires` không tự xử lý việc định nghĩa nhiều bản cùng class trong những loaders khác nhau.

**Sự khác nhau cốt lõi:** loader nhìn thấy class bytes **chưa chắc** module code được phép gọi class ấy do `exports`/readability. Ngược lại, module graph hợp lệ **chưa chắc** loại bỏ các xung đột của plugin dependencies ngoài graph.

## 12. ServiceLoader và việc tìm implementation

`ServiceLoader` là một cơ chế Java hỗ trợ nạp các **service providers**, thường được dùng để tìm plugin. Nó không thay thế nguyên tắc shared class identity.

Ví dụ:

```java
ServiceLoader<Greeter> providers = ServiceLoader.load(Greeter.class);
```

Đây là **snippet minh họa**; cần import `java.util.ServiceLoader` và `api.Greeter`. Provider phải được khai báo hợp lệ trong `META-INF/services/api.Greeter` khi dùng classpath, hoặc `provides ... with ...` trong named module, và phải thuộc những loader/layer mà `ServiceLoader` truy cập. Overload `ServiceLoader.load(Class<S>)` sử dụng **thread context class loader** trong ngữ cảnh thông thường.

Có ba điểm thường gây lỗi:

- **Provider được phát hiện không đồng nghĩa type hợp lệ**: instance vẫn phải là subtype của **đúng `Greeter.class`** mà host truyền cho `ServiceLoader`.
- **TCCL không phải parent loader**: `Thread.currentThread().getContextClassLoader()` có thể trỏ tới plugin loader, system loader hoặc giá trị framework cấu hình. Đặt TCCL chỉ đổi discovery context, không đổi định nghĩa một class đã được nạp.
- **Provider metadata có thể đúng nhưng class thiếu dependency**: runtime có thể phát sinh `ServiceConfigurationError` cùng nguyên nhân sâu hơn như `ClassNotFoundException`, `LinkageError` hoặc provider constructor lỗi.

Khi dùng `ServiceLoader.load(Greeter.class, pluginLoader)`, plugin loader phải nhìn **đúng shared API `Greeter.class`** và nạp provider hợp lệ. Nếu đang dùng named modules, cần hiểu thêm phiên bản `ServiceLoader.load(layer, service)` và phạm vi provider trong module layer.

## 13. Reflection, method handles và các kiểu bị "rò" qua boundary

Reflection có thể gọi method bằng tên, nhưng JVM vẫn có các quy tắc access, assignability và class identity. Ví dụ:

```java
Class<?> type = pluginLoader.loadClass("impl.PluginGreeter");
Object plugin = type.getDeclaredConstructor().newInstance();
```

Đây là snippet minh họa có thể đặt vào method `throws Exception` khi đã khai báo `pluginLoader`. Nếu `plugin` implements bản sao interface do loader khác định nghĩa, cast ở host vẫn thất bại.

Các nguy cơ cần quan sát:

- **Method parameter types:** `getMethod("execute", Request.class)` phải match **đúng `Class<?>` của `Request`** mà method thực sự khai báo. Cùng tên không đủ.
- **Return types:** một `api.Result` của plugin loader không tự là `api.Result` của host loader.
- **Array types:** `api.Result[]` cũng phụ thuộc defining loader của component type; hai array types với component runtime khác nhau không hoán đổi được.
- **Enums và records:** các kiểu này vẫn là Java class runtime có defining loader; các giá trị không tự đồng nhất qua bản sao loaders.
- **Exceptions:** catch clause Java được kiểm tra theo runtime type; exception class cùng tên nhưng khác defining loader không được bắt theo kiểu host.
- **Annotations:** nếu một plugin class mang annotation `api.Extension` do plugin loader định nghĩa riêng, reflection host dùng `api.Extension.class` có thể không nhận cùng annotation type.
- **Proxy và method handles:** generated proxy classes và handle signatures phải tuân thủ khả năng nhìn thấy/access của loader liên quan; không thể giả định cùng tên interface giải quyết mọi thứ.
- **Java generics:** type erasure không bỏ mọi type checks. `List<PluginDto>` có runtime raw `List` chung nhưng object bên trong vẫn có defining loader identity riêng.

Một API "chỉ dùng `Object`" đôi khi che vấn đề đến lúc host cast nội dung payload. Nên dùng DTO contract rõ ràng hoặc định dạng trao đổi độc lập cùng validation tại boundary.

## 14. Quản lý vòng đời loader và tránh giữ plugin mãi trong bộ nhớ

Một plugin loader thường tồn tại cùng các đối tượng/class do nó định nghĩa. Để unload class loader có thể cần giải phóng các tham chiếu giữ sống loader, classes và instances; GC/runtime quyết định thời điểm và khả năng unloading.

Các nguồn tham chiếu dễ bỏ sót:

- Host registry còn lưu plugin instance, `Class<?>`, `Method` hoặc `MethodHandle` của plugin.
- Một static field ở host giữ object plugin hoặc listener được plugin đăng ký.
- Thread pool hoặc thread context class loader vẫn trỏ tới plugin loader.
- Timer/task, callbacks, `ThreadLocal`, metrics registry hoặc logger lưu plugin classes/instances.
- `ServiceLoader` instance/cache hoặc framework cache còn giữ provider/plugin implementation.
- Một thư viện private của plugin tạo non-daemon thread chưa được stop.

`URLClassLoader.close()` đóng các tài nguyên mà loader quản lý (chẳng hạn JAR đang mở); **không bảo đảm JVM unload mọi class ngay** và không tự đóng những thread hay object plugin tạo ra. Cần plugin lifecycle `start/stop/close` có hợp đồng rõ, unregister callbacks, dừng background work, xoá registry và dọn TCCL có kiểm soát.

Khi host giữ một interface contract trong loader chung, bản thân interface đó có thể sống suốt ứng dụng — điều này bình thường. Điều cần tránh là shared API hoặc registry vô tình giữ tham chiếu cứng tới mọi plugin instance sau khi unload.

## 15. Debug khi thấy `ClassCastException` hoặc `LinkageError` tại boundary

**Bước 1: xác định hai kiểu đang so sánh.** Đừng chỉ đọc binary name từ exception; thu thập `Class<?>` thật ở hai phía.

Một helper có thể đặt trong ứng dụng khi có cả host API class và plugin implementation class:

```java
static void inspect(Class<?> hostApi, Class<?> implementation) {
    System.out.println("host API: " + hostApi.getName());
    System.out.println("host loader: " + hostApi.getClassLoader());
    System.out.println("impl: " + implementation.getName());
    System.out.println("impl loader: " + implementation.getClassLoader());
    System.out.println("assignable: " +
            hostApi.isAssignableFrom(implementation));
    for (Class<?> api : implementation.getInterfaces()) {
        System.out.println("implemented: " + api.getName());
        System.out.println("interface loader: " + api.getClassLoader());
        System.out.println("same interface: " + (api == hostApi));
    }
}
```

Đây là **method minh họa**, cần đặt trong class và gọi với types phù hợp; không phải tệp `.java` độc lập. `getInterfaces()` chỉ liệt kê trực tiếp interfaces được class khai báo, vì vậy với hierarchy phức tạp hãy xem thêm superclass và superinterfaces.

**Bước 2: đọc runtime dependency/loader graph.** Kiểm tra thư mục/JAR của shared API có xuất hiện cả ở host và plugin không, parent cụ thể của loader, cùng chiến lược parent-first/child-first. **Không chỉ xóa file trùng** nếu loader vẫn không có kênh tìm shared API.

**Bước 3: xem bytecode/binary descriptors.** Dùng `javap -verbose` và `javap -s` cho các class trong artifact **đang được chạy**, không chỉ source mới nhất:

```sh
javap -classpath shared-out -s api.Greeter
javap -classpath plugin-out -v impl.PluginGreeter
javap -classpath host-out -v host.HostMain
```

Các lệnh áp dụng cho kết quả thực hành A; nội dung output có thể dài và thay đổi theo javac/JDK. `javap` cho thấy class-file references và signatures; nó không tự nói **defining loader nào sẽ được JVM chọn** trong runtime thực tế.

**Bước 4: logging class loading.** Trên HotSpot hỗ trợ Unified Logging:

```sh
java -Xlog:class+load=info -cp "host-out;shared-out" host.HostMain
```

Lệnh dùng classpath **Windows** để nhất quán ví dụ; Linux/macOS thay `;` bằng `:`. Log chứa nguồn class bytes và thông tin loading giúp xác định artifact nào được sử dụng. Kết hợp với `Class.getClassLoader()` để biết identity thật; thời điểm class loading không đồng nghĩa initialization hay resolution hoàn tất.

**Bước 5: phân loại lỗi thay vì chữa theo cảm tính.**

| Triệu chứng | Khả năng cần xem | Hướng sửa chính |
| --- | --- | --- |
| `ClassCastException` với cùng binary name | Hai defining loaders tạo bản sao API | Chia sẻ một contract loader, sửa delegation/packaging. |
| `isAssignableFrom` bằng `false` | Implementation không implements đúng runtime interface | Đọc interface `Class<?>` từ plugin, loader chain, version contract. |
| `ServiceConfigurationError` | Provider không là subtype service, cấu hình service sai, constructor hoặc dependency lỗi | So service `Class<?>`, TCCL/ServiceLoader loader, provider metadata. |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary API không khớp lúc chạy | So descriptors của host/plugin/runtime JAR; version tương thích. |
| `AbstractMethodError` | Implementation runtime thiếu method mà call site yêu cầu | Kiểm tra interface evolution/ABI và plugin được compile từ version nào. |
| `LinkageError` liên quan loader constraint | Signature type identity xung đột giữa loaders | Kiểm tra shared types lồng trong parameter/return và loader delegation. |
| `IllegalAccessError` / `InaccessibleObjectException` | Package/module access/opens không đủ | Sửa module descriptor/exports/opens và luồng reflection hợp lệ. |
| `ClassNotFoundException` | Loader được hỏi không nhìn thấy class | Parent chain, URL/module/layer, runtime packaging. |
| `NoClassDefFoundError` | Class cần dùng không thể được định nghĩa/sử dụng hoặc initialization từng thất bại | Tìm `Caused by`, runtime dependencies, initializer. |

`ClassNotFoundException` khi dùng `loadClass` là checked exception của API lookup; `NoClassDefFoundError` là `LinkageError` có thể xảy ra ở một thời điểm khác khi bytecode cần class. Không đánh đồng chúng.

## 16. Checklist thiết kế trước khi phát hành plugin

Trước khi chọn cách nạp, kiểm tra theo thứ tự:

1. **Liệt kê mọi boundary types.** Interface, DTO, exception, annotation, enum, callback, collections chứa giá trị bên thứ ba, types trong descriptors.
2. **Chỉ định một defining loader hợp lệ cho từng shared type.** Host và mọi plugin liên quan phải resolve về cùng `Class<?>` đó.
3. **Vẽ loader graph.** Loader nào là parent/ancestor của loader nào, có child-first hay ngoại lệ package nào?
4. **Đảm bảo packaging tương ứng.** Shared API được phân phối/version rõ, plugin không vô tình định nghĩa bản sao; implementation được đặt trên plugin path.
5. **Tách dependency riêng.** Không để private dependency type rò qua public contract khi không có kế hoạch chia sẻ identity.
6. **Kiểm tra binary compatibility.** Host API version và các plugin artifacts đã phát hành có hợp đồng version cụ thể.
7. **Kiểm tra JPMS nếu dùng modules.** Readability, exports, opens, layer và defining loader thật.
8. **Kiểm tra discovery.** `ServiceLoader`/TCCL biết được provider, và provider assignable vào service type của host.
9. **Kiểm tra lifecycle.** Có start/stop, cleanup callback/thread/resource và đóng loader thích hợp.
10. **Chạy integration tests qua loaders thật.** Đừng chỉ test với plugin classes trực tiếp trên system classpath, vì cách đó có thể vô tình loại bỏ boundary cần thử.

### Test tối thiểu nên có

Một kiểm thử integration có giá trị phải thực sự tạo plugin loader với classpath tách biệt như ví dụ A; tải plugin theo binary name và khẳng định:

```java
assert api.Plugin.class.isAssignableFrom(implementationClass);
assert implementationClass.getClassLoader() == pluginLoader;
```

Đây là các assertion **minh họa**, không phải code JUnit hoàn chỉnh. Nếu source thuộc module hoặc framework khác, assertion thứ hai có thể phải điều chỉnh cho thiết kế loader cụ thể; assertion về contract identity mới là điều quan trọng. Test thêm các trường hợp plugin dùng JAR API trùng, mismatch version, missing dependency và vòng đời unload khi áp dụng.

## 17. Những ngộ nhận cần tránh

- **"Cùng package và class name thì JVM sẽ tự chia sẻ kiểu."** Sai: defining loader là một phần của runtime type identity.
- **"Thêm `api.jar` vào cả host và plugin classpath là đủ."** Chưa đủ: nếu mỗi loader tự define bản sao, identity tách rời.
- **"Plugin phải kế thừa cùng Java superclass loader với host để cast thành công."** Sai: inheritance của loader implementation class không quyết định contract identity.
- **"Plugin được child-first nên mọi class phải được nạp ở child."** Không nên: shared API thường cần ngoại lệ delegation về loader chung.
- **"Interface dùng chung đúng rồi thì mọi DTO đều an toàn."** Chưa chắc: mọi kiểu lộ ra ở boundary cũng cần thống nhất hoặc được chuyển qua protocol trung lập.
- **"Reflection giải quyết được xung đột class loader."** Sai: việc lấy class/method qua reflection không xoá access/type constraints.
- **"`ServiceLoader` luôn thấy tất cả plugins."** Không: discovery phụ thuộc TCCL, loader/layer, service metadata và khả năng assignability.
- **"`URLClassLoader.close()` khiến mọi plugin class biến mất ngay."** Không: unloading còn phụ thuộc reachability và GC.
- **"Một bản shared API dùng được mãi, không cần versioning."** Sai: việc sửa binary signatures có thể làm plugin cũ không còn liên kết.
- **"Nếu hai plugin dùng dependency cùng version thì phải dùng chung tất cả classes."** Không: mỗi plugin có thể định nghĩa implementation/dependency riêng, miễn các **shared boundary types** tuân thủ identity.

## 18. Câu hỏi tự kiểm tra

**1. JVM dùng yếu tố nào để phân biệt hai reference types cùng tên?** Binary name và defining class loader.

**2. Vì sao `api.Greeter` bản host và bản plugin không thể tự cast cho nhau?** Hai loader định nghĩa hai interface `Class<?>` khác nhau, khiến runtime assignability thất bại dù tên/source giống.

**3. Muốn một plugin implementation assignable với host interface, cần điều kiện gì?** Plugin phải dùng đúng runtime interface mà host dùng trong quan hệ `implements`, thường qua shared parent/delegation.

**4. Vì sao trong thực hành A `PluginGreeter` thuộc plugin loader nhưng `Greeter` được dùng chung?** URLClassLoader tự định nghĩa class implementation từ `plugin-out`, còn contract từ `shared-out` được host loader cung cấp qua parent-first.

**5. Vì sao thực hành B cố ý thất bại dù `Greeter.java` vẫn giống nhau?** Plugin loader dùng platform parent rồi tự định nghĩa API từ `shared-out`, tạo bản sao interface khác host identity.

**6. Hai plugin loaders khác nhau có thể cùng dùng một API mà implementation khác nhau?** Có. Cả hai delegation tới một shared API loader, trong khi tự định nghĩa implementation riêng.

**7. `List<Object>` trong contract có bảo đảm không rò types riêng?** Không. Giá trị trong collection có thể là plugin-private classes; các cast ở host vẫn có thể thất bại.

**8. Vì sao đổi return type có thể phá plugin binary compatibility?** JVM method descriptor bao gồm return type. Bên gọi đã compile chứa symbolic reference theo descriptor cũ.

**9. TCCL liên quan gì tới shared API?** Một số cơ chế discovery như `ServiceLoader` dùng TCCL để tìm provider, nhưng TCCL không tự gộp hai class identities.

**10. Điều gì cần thử trước khi phát hành một plugin API revision?** Test plugin JAR đã biên dịch từ version cũ qua loader graph thực tế, bao gồm subtype checks và method invocations qua mọi boundary types.

## 19. Tài liệu tham khảo để xác minh

- [Java Virtual Machine Specification, Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, defining/initiating loader, class identity, loading constraints và linking.
- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, `getParent` và class loader contracts.
- [Java SE 17 `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): tạo loader từ URL và đóng loader.
- [Java SE 17 `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getInterfaces`, `isAssignableFrom` và runtime types.
- [Java SE 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery trên classpath/module path và context loader.
- [Java SE 17 `Module` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): mô hình module readability và access.

**Nguyên tắc kết thúc:** thiết kế nhiều class loaders thành công khi **hợp đồng dùng chung có một danh tính runtime mà mọi bên đều nhìn thấy**, còn implementation có thể giữ namespace riêng. Hãy kiểm tra `Class<?>` thực, defining loader, method descriptors, module access và loader graph — thay vì chỉ so sánh package name hoặc nội dung JAR.
