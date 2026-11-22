# Vì sao API nền tảng cần nhìn thấy cách triển khai của ứng dụng?

Một framework hoặc API nền tảng thường **định nghĩa hợp đồng (interface/SPI)**, trong khi ứng dụng, plugin hoặc nhà cung cấp thư viện **cung cấp cách triển khai (provider)**. Nếu thư viện nằm trong loader cha nhưng provider nằm ở loader con, cơ chế **parent-first class loading** thông thường không tự cho loader cha nhìn xuống class của loader con.

Ví dụ: thư viện định nghĩa `Greeting`, ứng dụng triển khai `HelloGreeting`. Thư viện cần khám phá và gọi implementation mà bản thân nó không biết lúc biên dịch. Với cơ chế chỉ hỏi parent, lớp ở cha có thể tìm các class của chính nó, nhưng **không tự động tìm được** những provider chỉ nằm trong loader ứng dụng/plugin.

Đó là một lý do tồn tại của **thread context class loader (TCCL)**: mã thư viện/khung chạy trên một thread có thể chủ động hỏi “loader ứng dụng muốn dùng để khám phá implementation trong tác vụ này là loader nào?”. Những API như `ServiceLoader.load(Service.class)` có hợp đồng sử dụng TCCL để giải quyết nhu cầu đó.

Bài thuộc nhóm **Loader ngữ cảnh** của Java core – classloader. Trọng tâm là vì sao API nền tảng cần nhìn thấy implementation của ứng dụng, đường đi của lời gọi, điểm khác nhau giữa **defining loader**, **parent loader** và **TCCL**, ví dụ Java 17+ chạy được, giới hạn trong môi trường module/plugin, cùng các lỗi thường gặp.

## 1. Bài toán thiết kế: API ở “trên”, implementation ở “dưới”

Một hệ thống mở rộng được thường tách hai vai trò:

- **API/service contract:** interface, abstract class hoặc bộ quy tắc chung mà framework công bố, ví dụ `java.sql.Driver`, `java.util.spi.*` hoặc một interface do host ứng dụng định nghĩa.
- **Provider/implementation:** class cụ thể triển khai hợp đồng ấy, ví dụ driver của hãng cơ sở dữ liệu, provider mã hóa, serializer, logging implementation, plugin.
- **Discovery/factory:** thành phần cần tìm hoặc khởi tạo provider theo cấu hình/module metadata mà không phụ thuộc cứng vào tên class cụ thể ngay lúc biên dịch API.

Cây delegation điển hình:

```text
                     [Bootstrap loader]
                              ^
                              |
                       [Platform loader]
                              ^
                              |
                  [Application/System loader]
                              ^
                              |
                       [Plugin loader]
                       plugin.HelloGreeting
```

Mũi tên trên biểu thị **child có thể nhờ parent tìm class**, không có nghĩa parent tự động có thể truy cập mọi class do child định nghĩa.

Nếu `host.LibraryDiscovery` do system loader định nghĩa, còn `plugin.HelloGreeting` chỉ nằm trong plugin loader con, lời gọi:

```java
Class.forName("plugin.HelloGreeting")
```

nếu viết *ngay trong `host.LibraryDiscovery`* sẽ mặc định bắt đầu từ **defining loader của `LibraryDiscovery`**. Nó không tự suy luận rằng một plugin đang gọi vào method ấy và cần đổi loader theo call stack. Điều này có thể khiến lớp provider không tìm được dù plugin loader thực sự có bytecode của nó.

**Mâu thuẫn cần giải quyết:** mã nền tảng/host cần khám phá implementation do ứng dụng cung cấp, nhưng parent-first loader không có cơ chế tổng quát “hỏi ngược mọi loader con”.

## 2. TCCL giải quyết bài toán theo cách nào?

Mỗi `Thread` trong Java có một **context class loader** có thể đọc hoặc thay đổi:

```java
ClassLoader current = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(someLoader);
```

Đây là **đoạn minh họa**, giả định `someLoader` đã tồn tại. TCCL là **trạng thái của thread**, không phải thuộc tính toàn cục cho JVM và không phải một cạnh mới trong `ClassLoader.getParent()`.

Đường gọi của framework:

```text
Host/framework định nghĩa interface Service
               |
               | application khởi động request / plugin
               v
Thread context loader = PluginLoader
               |
               | Host API gọi ServiceLoader.load(Service.class)
               v
ServiceLoader hỏi TCCL để tìm provider metadata
               |
               v
PluginLoader tìm META-INF/services/... và provider class
               |
               v
Provider class do PluginLoader định nghĩa
               |
               +-- provider implements Service do parent định nghĩa
               |
               v
Framework nhận Service và gọi method của interface chung
```

**Điểm cốt lõi:** TCCL cho phép *code nằm ở loader cha chủ động yêu cầu loader con tìm implementation*. Nó không làm mọi code trong loader cha tự nhiên nhìn thấy class của loader con, không sửa parent chain, không chuyển defining loader của những class đã nạp.

Một điều đặc biệt cần biết từ Java 17 API:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
```

Overload này tương đương về lựa chọn loader với:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(
                Greeting.class,
                Thread.currentThread().getContextClassLoader());
```

Đây là **đoạn minh họa**, giả định interface `Greeting` đã khai báo. Cơ chế lựa chọn TCCL là hợp đồng cụ thể của `ServiceLoader.load(Class)`, **không phải quy tắc tự động của mọi phương thức Java**.

## 3. Vì sao parent loader không chủ động tìm xuống child?

Trong cơ chế mặc định `ClassLoader.loadClass`, loader lần lượt kiểm tra class đã load, hỏi parent, rồi mới thử `findClass` của chính mình. Parent không có danh sách ổn định tất cả child loader vì:

1. Ứng dụng có thể tạo nhiều plugin loaders một cách động.
2. Hai plugin có thể định nghĩa **cùng tên class** nhưng muốn giữ namespace/version độc lập.
3. Framework có thể chạy nhiều tenant hoặc ứng dụng trên cùng JVM với context khác nhau.
4. Parent có thể được nạp sớm hơn nhiều so với các plugin và không biết các implementation sẽ xuất hiện sau đó.
5. Nếu parent tự tra mọi child mà không có hợp đồng, nó có thể chọn nhầm provider hoặc lộ ranh giới class không mong muốn.

Ví dụ:

```text
                   [App/system loader]
                     /           \
                    v             v
              [PluginLoader A] [PluginLoader B]
               demo.Provider   demo.Provider
```

Hai `demo.Provider` có thể là hai class **khác nhau**, vì danh tính runtime của class là **binary name + defining loader**. Chọn provider B cho một request của A sẽ sai, dù class có cùng tên.

TCCL cho phép chính **ngữ cảnh thực thi** chọn một loader cụ thể khi API discovery có chủ đích sử dụng nó. Cơ chế này hữu ích cho request-scoped, plugin-scoped hoặc container-scoped discovery.

Tuy nhiên, **TCCL không phải sandbox bảo mật**: nó là một tham chiếu tới loader được chọn. API dùng loader đó vẫn phải tuân theo Java/module access và ranh giới trust.

## 4. Ví dụ chạy được Java 17+: framework cha khám phá provider của plugin con

Ta xây dựng một ví dụ có thể biên dịch/chạy bằng JDK 17 trở lên. Gồm:

- `api.Greeting`: interface chung do **system loader** định nghĩa.
- `lib.Discovery`: code thư viện **chỉ ở system loader**, khám phá provider qua `ServiceLoader`.
- `plugin.HelloGreeting`: implementation **chỉ được plugin loader định nghĩa**.
- `main.Launcher`: ứng dụng chủ động đặt TCCL = plugin loader cho khoảng thời gian discovery.
- `META-INF/services/api.Greeting`: file khai báo provider theo **Service Provider Interface (SPI)** trên classpath.

### 4.1 Cấu trúc thư mục

Tạo cây sau trong `tccl-demo`:

```text
tccl-demo/
├── src/
│   ├── api/Greeting.java
│   ├── lib/Discovery.java
│   └── main/Launcher.java
├── plugin-src/
│   └── plugin/HelloGreeting.java
├── host-out/                           (output của host)
└── plugin-out/
    └── META-INF/
        └── services/
            └── api.Greeting           (file text chứa tên provider)
```

**Tạo đủ thư mục trước** khi biên dịch. File `plugin-out/META-INF/services/api.Greeting` phải có đúng tên binary của service interface; nội dung là tên binary của provider, không phải tên file `.class`.

### 4.2 Interface chung

File `src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String greet();
}
```

Interface này sẽ được nạp bởi **system loader**; cả library và plugin đều tham chiếu đúng một `Class<api.Greeting>`.

### 4.3 Code thư viện/framework

File `src/lib/Discovery.java`:

```java
package lib;

import api.Greeting;
import java.util.ServiceLoader;

public final class Discovery {
    private Discovery() { }

    public static void inspect() {
        long fromParent = ServiceLoader.load(
                Greeting.class, Greeting.class.getClassLoader())
                .stream().count();

        long fromContext = ServiceLoader.load(Greeting.class)
                .stream().count();

        System.out.println("parent provider count=" + fromParent);
        System.out.println("context provider count=" + fromContext);

        for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
            System.out.println(greeting.greet());
        }
    }
}
```

Giải thích:

- `Greeting.class.getClassLoader()` là system loader trong chương trình này. Khi truyền rõ loader đó, discovery **không thấy** provider chỉ ở plugin child loader.
- `ServiceLoader.load(Greeting.class)` chọn **TCCL của thread hiện tại**.
- `stream().count()` đếm provider types phát hiện được, **không yêu cầu gọi `greet()` hoặc tạo instance để đếm**. Vòng `for` sau đó thực sự instantiate provider khi cần.

### 4.4 Provider trong plugin

File `plugin-src/plugin/HelloGreeting.java`:

```java
package plugin;

import api.Greeting;

public final class HelloGreeting implements Greeting {
    public String greet() {
        return "Hello from plugin";
    }
}
```

File văn bản `plugin-out/META-INF/services/api.Greeting`:

```text
plugin.HelloGreeting
```

Đường dẫn và nội dung phải khớp **chính xác**. Nếu file metadata thiếu, `ServiceLoader` sẽ không phát hiện provider từ classpath theo cơ chế SPI này. Nếu provider khai báo sai tên hoặc không implement interface chung, có thể gặp `ServiceConfigurationError` khi duyệt provider.

### 4.5 Chương trình khởi động và đặt TCCL

File `src/main/Launcher.java`:

```java
package main;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import lib.Discovery;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin-out").toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[]{pluginUrl}, ClassLoader.getSystemClassLoader())) {

            ClassLoader original =
                    Thread.currentThread().getContextClassLoader();

            System.out.println("provider visible to system=" +
                    isVisible("plugin.HelloGreeting",
                            ClassLoader.getSystemClassLoader()));

            Thread.currentThread().setContextClassLoader(pluginLoader);
            try {
                Discovery.inspect();
            } finally {
                Thread.currentThread().setContextClassLoader(original);
            }
        }
    }

    private static boolean isVisible(String name, ClassLoader loader) {
        try {
            loader.loadClass(name);
            return true;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }
}
```

Chú ý:

- `pluginLoader` có parent là system loader để **dùng chung interface `api.Greeting`**, còn `plugin.HelloGreeting` chỉ có trong `plugin-out`.
- `isVisible(...)` kiểm tra system loader có tự load provider không, trước khi TCCL được thay đổi.
- `setContextClassLoader` chỉ thay context của thread, **không tạo lại `Discovery` hoặc thay đổi defining loader** của class ấy.
- `finally` khôi phục loader cũ; `try-with-resources` đóng `URLClassLoader` sau khi tác vụ xong. Đóng loader không tự giải phóng class ngay lập tức nếu nơi khác vẫn giữ tham chiếu đến loader/class/provider.

### 4.6 Biên dịch và chạy

Từ **thư mục `tccl-demo`**:

```bash
javac --release 17 -d host-out src/api/Greeting.java src/lib/Discovery.java src/main/Launcher.java
javac --release 17 -cp host-out -d plugin-out plugin-src/plugin/HelloGreeting.java
java -cp host-out main.Launcher
```

Các lệnh `javac` và `java` trên hoạt động theo cùng cách ở Windows/Linux/macOS vì mỗi lần chỉ cần một root. Cần tạo `host-out`, `plugin-out` và file `META-INF/services/api.Greeting` như hướng dẫn trước đó.

Stdout đã được kiểm tra bằng biên dịch `javac --release 17` và chạy chương trình:

```text
provider visible to system=false
parent provider count=0
context provider count=1
Hello from plugin
```

Phân tích:

1. `provider visible to system=false`: host/system loader không tìm provider của child; đó là **chiều nhìn thấy bất đối xứng** trong parent delegation.
2. `parent provider count=0`: thư viện chỉ dùng loader của service interface thì không tìm thấy metadata/provider trong `plugin-out`.
3. `context provider count=1`: TCCL đã trỏ vào `pluginLoader`, nên `ServiceLoader` tìm được `META-INF/services/api.Greeting` rồi xác định provider.
4. `Hello from plugin`: provider được instantiate và gọi qua interface `api.Greeting`, một kiểu chung do parent định nghĩa.

Đây là phiên bản thu nhỏ của nhu cầu thật trong plugin engine, service-provider mechanism và ứng dụng có nhiều class loader.

**Nếu bỏ dòng `setContextClassLoader(pluginLoader)`**, trong cách chạy này `ServiceLoader.load(Greeting.class)` sẽ thường dùng system loader mặc định của main thread; kết quả `context provider count=0` và không có dòng chào plugin. Không cần giả định mọi thread/runtime có TCCL mặc định giống nhau để hiểu quy tắc: quan trọng là **loader nào đang là TCCL lúc gọi**.

## 5. Đặc tả quan trọng: không phải API nào cũng đọc TCCL

So sánh:

| API / thao tác | Loader được chọn | Có tự yêu cầu khởi tạo class đích? |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | **TCCL hiện tại** | Discovery có thể lazy; instantiate provider khi duyệt/`get()` |
| `ServiceLoader.load(Service.class, loader)` | Loader được truyền rõ | Provider được instantiate theo nhu cầu của lần duyệt |
| `ServiceLoader.loadInstalled(Service.class)` | **Platform loader** | Chỉ tìm những provider “installed” phù hợp, không tự tìm provider application classpath |
| `ServiceLoader.load(layer, Service.class)` | **ModuleLayer** truyền vào | Discovery trong layer và parent layers theo quy tắc module |
| `Class.forName("pkg.Impl")` | **Defining loader của class gọi `forName`** | **Có**, nếu class đích chưa initialize |
| `Class.forName("pkg.Impl", false, loader)` | Loader được truyền | Không yêu cầu initialize class đích ngay |
| `someLoader.loadClass("pkg.Impl")` | Loader được gọi và delegation của nó | Không tự yêu cầu initialize |
| `Class.getResourceAsStream(...)` | Theo class và module/resource rules | Không tự chọn TCCL chỉ vì method được gọi |

Hai mẫu quan trọng:

```java
Class<?> type = Class.forName("plugin.HelloGreeting");
// Không tự dùng TCCL chỉ vì plugin context đang tồn tại.

ClassLoader context = Thread.currentThread().getContextClassLoader();
Class<?> selected = Class.forName(
        "plugin.HelloGreeting", true, context);
// Dùng loader được chọn rõ ràng.
```

Đây là đoạn minh họa, không phải file chạy độc lập. `Class.forName(String)` là API **caller-sensitive**: loader mặc định của nó là defining loader của **class chứa lệnh gọi**, không phải lớp gọi framework ở xa trong stack và không phải TCCL.

**TCCL chỉ có tác dụng với API chủ động đọc nó**. Không được kết luận “đổi TCCL sẽ sửa mọi `ClassNotFoundException`” hoặc “mọi API nền tảng đều truy vấn TCCL”.

## 6. SPI giúp tách hợp đồng khỏi implementation

Mục tiêu thiết kế là **dependency inversion** ở tầng triển khai:

```text
Framework/API -----------------> Service interface
                                      ^
                                      |
                              Provider implements
                                      |
                              Application/plugin
```

Mã nền tảng phụ thuộc vào **hợp đồng ổn định**. Ứng dụng cung cấp provider mà framework không cần biết tên implementation khi compile. **Discovery metadata** giúp runtime biết nhà cung cấp nào đã triển khai interface đó.

Một SPI classpath theo Java SE thông thường dùng:

```text
META-INF/services/<fully.qualified.ServiceInterface>
```

và nội dung chứa mỗi tên provider trên một dòng. Trong ví dụ, đúng file:

```text
META-INF/services/api.Greeting
```

chứa:

```text
plugin.HelloGreeting
```

Trên Java 17, `ServiceLoader` hỗ trợ cả **unnamed modules / classpath provider-configuration files** và **named modules có `provides`**. TCCL giúp chọn miền loader trong nhiều trường hợp, nhưng module system còn bổ sung quy tắc tìm provider theo layer/readability.

### ServiceLoader thực sự làm gì?

- Chọn loader khi tạo `ServiceLoader`, sau đó duyệt provider từ thông tin module/SPI.
- Thường **lazy**: việc gọi `ServiceLoader.load` chưa có nghĩa đã instantiate mọi implementation.
- Tìm provider classes và kiểm tra hợp đồng service phù hợp.
- Tạo instance provider khi iteration hoặc `Provider.get()` yêu cầu.
- Có cache cho các provider đã được nạp/thực thể hóa trong từng đối tượng `ServiceLoader`; `reload()` xóa cache của đối tượng.
- **Không thread-safe** nếu chia sẻ cùng đối tượng `ServiceLoader` cho nhiều thread mà không đồng bộ.

Sự khác biệt giữa “tìm thấy provider metadata”, “nạp class provider” và “khởi tạo instance provider” là quan trọng để hiểu thời điểm side effect xảy ra.

## 7. Thực tế: API nền tảng nào có nhu cầu nhìn thấy implementation của ứng dụng?

Một số mẫu thường gặp:

**Service Provider Interface (SPI):** `java.util.ServiceLoader` là ví dụ rõ nhất với hợp đồng `load(Class)` dùng TCCL. Service interface có thể do Java SE, một thư viện hoặc host ứng dụng định nghĩa; provider ở JAR/plugin ứng dụng.

**JDBC driver:** API JDBC và `DriverManager` là phần nền tảng; JDBC driver là thư viện của nhà cung cấp. Các driver hiện đại có thể được phát hiện thông qua cơ chế service-provider `java.sql.Driver`. Tuy nhiên, `DriverManager` còn áp dụng quy tắc class loader/access và cơ chế khởi tạo riêng; không được suy từ ví dụ SPI rằng **mọi code gọi JDBC luôn đơn giản dùng TCCL trực tiếp**. Khi debug phải kiểm tra tài liệu Java/JDBC và cấu hình runtime.

**JAXP XML parser/transformer:** API factory nền tảng có thể cần chọn provider do ứng dụng cung cấp; factory lookup có nhiều nguồn (system properties, service configuration, default provider, v.v.). Hãy xem hợp đồng cụ thể của từng factory, đừng mặc định tất cả lookup luôn dùng một loader.

**Application servers, dependency injection, plugin frameworks:** một container có thể chạy mã framework từ shared parent loader nhưng cần nạp component triển khai trong loader ứng dụng. Container thường quản lý TCCL ở ranh giới request/deployment/lifecycle để các API discovery có thể thấy đúng vùng ứng dụng.

**Logging bindings và serializers:** các thư viện chọn provider dựa trên service metadata hoặc cơ chế riêng. Với từng thư viện, phải kiểm tra nó **có dùng TCCL hay không**, vì không có quy tắc JVM bắt buộc mọi factory phải tuân theo cùng cách discovery.

Điểm chung không phải “API cấp cao phải trực tiếp phụ thuộc các lớp thấp hơn”, mà là **API cần cơ chế tìm plugin/provider đúng phạm vi** dù nơi định nghĩa API và nơi cung cấp implementation có thể dùng các loader khác nhau.

## 8. Thread context không tự theo công việc bất đồng bộ
Thread mới thông thường thừa hưởng TCCL ở **thời điểm tạo**, trong khi executor có thể tái sử dụng worker được tạo từ trước. Vì thế một lời gọi discovery trong worker có thể nhìn provider khác với lời gọi trên submitter, dù dùng cùng `ServiceLoader.load(service)`. Nếu cần ngữ cảnh plugin cụ thể, truyền `ClassLoader` tường minh hoặc gán/khôi phục ngay bên trong task với `try/finally`. Đừng giữ `ServiceLoader` của plugin A trong một static cache dùng cho nhiều ứng dụng; cache và worker đều có thể kéo dài vòng đời loader. Các bài về thread inheritance và pool cung cấp code trace riêng.
## 9. Vì sao loader cha và plugin cần dùng chung interface?

Xét hai phiên bản:

**Đúng thiết kế:**

```text
[Host/system loader]:  api.Greeting
        ^
        |
[Plugin child loader]: plugin.HelloGreeting implements api.Greeting
```

Plugin loader nhờ parent nạp `api.Greeting`. Cả host và plugin thấy **cùng một đối tượng `Class<api.Greeting>`**. `ServiceLoader<Greeting>` có thể cast provider về `Greeting`.

**Sai thiết kế:**

```text
[Host/system loader]: api.Greeting (bản A)
[Plugin child loader]: api.Greeting (bản B), plugin.HelloGreeting
```

Nếu plugin định nghĩa **một bản `api.Greeting` khác** bằng child-first loader hoặc package shading không phù hợp, `plugin.HelloGreeting` không nhất thiết assignable tới interface của host dù cả hai interface có cùng tên. Khi discovery, có thể nhận `ServiceConfigurationError: provider ... not a subtype`, `ClassCastException` hoặc lỗi linkage/access tương ứng.

Java identity của type là **binary name + defining loader**, không phải chỉ tên và nội dung file. Khi thiết kế SPI:

1. Đặt **service interface và shared DTO/API contract** vào loader chung, thường parent của plugin loaders.
2. Chỉ để các **implementation/dependencies riêng** ở plugin loaders.
3. Không đóng gói bản sao API chung vào mỗi plugin theo cách khiến plugin tự define lại class ấy.
4. Kiểm tra module exports/opens và API version khi runtime là named modules.

**TCCL không sửa được lỗi identity giữa hai bản service interface.** Nó chỉ quyết định loader bắt đầu discovery của những API dùng TCCL.

## 10. Với JPMS, TCCL không phải câu trả lời cho mọi module

Từ Java 9, service providers có thể khai báo trong `module-info.java`:

```java
// Module m.spi
module m.spi {
    exports api;
}
```

```java
// Module m.plugin
module m.plugin {
    requires m.spi;
    provides api.Greeting with plugin.HelloGreeting;
}
```

```java
// Module m.app
module m.app {
    requires m.spi;
    uses api.Greeting;
}
```

Đây là **ba tệp minh họa độc lập**, mỗi block thuộc `module-info.java` trong module tương ứng; không ghép ba block vào một file. Một module muốn dùng `ServiceLoader` trong named-module code thường cần khai báo `uses` tương ứng; provider có `provides ... with ...` và phù hợp constructor/provider method theo contract API.

Khi custom `ModuleLayer` chứa provider modules, lựa chọn thuận tiện thường là:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(pluginLayer, Greeting.class);
```

Đây là đoạn minh họa với `pluginLayer` là đối tượng `ModuleLayer` đã tạo. Overload này tìm provider ở layer và ancestor layers, không dùng classpath provider trong unnamed modules như một cơ chế tương đương hoàn toàn.

Đồng thời, `ServiceLoader.load(service, loader)` có thể tìm provider trong named modules gắn với loader và một số module layers liên quan theo quy tắc đặc tả. Vì vậy “TCCL = một loader” **không luôn đồng nghĩa chỉ tìm đúng một named module**. Trong JPMS, phải xét **module layer, uses/provides, package/module mapping** chứ không chỉ sơ đồ parent loader.

Các class đã load được cũng chưa chắc có thể truy cập mọi thành viên: module readability, exports, opens và access modifiers vẫn có hiệu lực. Service provider discovery không bỏ qua module access.

## 11. Các giới hạn thiết kế quan trọng

| Vấn đề | Giải thích đúng | Cách xử lý |
| --- | --- | --- |
| `Class.forName(name)` không thấy plugin | Nó dùng loader của **class caller**, không tự đọc TCCL | Dùng overload truyền loader hoặc SPI hợp đồng hóa |
| Parent loader không thấy class của child | Parent-first delegation theo chiều child → parent, không tự tìm xuống | Cho API discovery chủ động dùng TCCL/loader/module layer |
| `ServiceLoader` không tìm provider | Thiếu `META-INF/services`, sai loader, sai module declarations hoặc không có provider | Kiểm tra cấu hình SPI/module và loader khi iteration |
| Provider bị `ServiceConfigurationError` | Sai tên class, không assignable, constructor/provider method không hợp lệ hoặc lỗi instantiate | Đọc cause, so Class identity và metadata SPI |
| “Provider visible” nhưng cast lỗi | Plugin tự define bản API interface trùng tên | Đặt API ở loader chung, dùng đúng parent delegation |
| Quên restore TCCL sau request | Thread pool giữ loader cũ, định tuyến sai provider/leak | `try/finally`, quản lý lifecycle |
| Muốn retry provider sau cài plugin mới | `ServiceLoader` có cache theo instance, module/classloader lifecycle ảnh hưởng phát hiện | Tạo loader/ServiceLoader phù hợp hoặc gọi `reload()` khi có ý nghĩa |
| Có provider trong named module nhưng app không thấy | `ModuleLayer`, `uses`, `provides` hoặc module accessibility chưa đúng | Dùng overload layer/loader phù hợp, kiểm tra module graph |
| Đổi TCCL để sửa mọi lỗi loader | Chỉ hiệu lực với API dùng TCCL; không đổi bytecode/linking đã thực hiện | Xác định chính xác API lookup và caller |
| Dùng plugin loader để chạy mã không đáng tin | TCCL/loader không phải sandbox toàn diện | Áp dụng biện pháp isolation và trust phù hợp |

### Vì sao không nên cache `ServiceLoader` toàn JVM?

Theo Java 17 ServiceLoader API, `ServiceLoader.load(service)` dùng TCCL lúc tạo loader. Nếu server có nhiều ứng dụng cùng JVM nhưng khác TCCL, một `ServiceLoader` được cache toàn cục có thể giữ providers của ứng dụng A trong khi phục vụ B, hoặc giữ tham chiếu khiến class loader của A không được giải phóng. Tùy use case, nên scope cache theo deployment/request/module layer, quản lý lifecycle và tránh static references sống lâu hơn plugin.

Khi reload code động, chỉ `ServiceLoader.reload()` không thay thế các class đã được JVM định nghĩa trong một loader. Để có namespace phiên bản mới thực sự, framework có thể cần loader/plugin layer mới và giải phóng tham chiếu cũ.

## 12. Debug khi API ở parent không thấy implementation ở child
Phân tích theo ba trục độc lập: **visibility** (class/resource có thật sự nằm trong namespace của loader dùng tìm?), **identity** (provider và host có chia sẻ cùng runtime interface?) và **discovery** (descriptor/module declaration/overload `ServiceLoader` có đúng không?). Ghi các giá trị `Greeting.class.getClassLoader()`, `Thread.currentThread().getContextClassLoader()` và `provider.getClass().getClassLoader()` ngay ở code gọi, kiểm tra classpath của host **không vô tình chứa provider**. Với JPMS, xem `uses`/`provides` và `ModuleLayer`. Nếu lời gọi chạy qua executor, lấy thông tin từ worker thực tế. `ServiceConfigurationError` chỉ ra lỗi cấu hình/provider, khác với kết quả discovery rỗng.
## 13. Các ngộ nhận thường gặp

| Ngộ nhận | Sự thật |
| --- | --- |
| “Loader cha luôn thấy mọi class của con.” | Parent-first cho child hỏi parent; chiều ngược không mặc định tồn tại. |
| “API nền tảng biết tất cả plugin vì chúng cùng JVM.” | Nó cần cơ chế discovery và lựa chọn loader/module phù hợp. |
| “Đổi TCCL làm mọi `Class.forName(String)` dùng plugin loader.” | Không; `Class.forName(String)` dùng defining loader của caller. |
| “TCCL là parent mới của loader ứng dụng.” | Không; nó chỉ là tham chiếu loader trên thread. |
| “TCCL được lưu trong `Class<?>` của provider.” | Không; class có **defining loader** riêng, không bị thay bởi TCCL. |
| “Gọi `ServiceLoader.load` nghĩa là tất cả provider đã được instantiate.” | Discovery có thể lazy; iteration/`Provider.get()` mới thực hiện nhiều bước. |
| “Provider trùng tên class với interface bên host là đủ.” | Không; class identity cần đúng defining loader, nhất là API interface chung. |
| “Một static cache `ServiceLoader` dùng tốt cho mọi plugin.” | Có thể sai provider scope hoặc rò rỉ loader khi undeploy. |
| “TCCL cung cấp security isolation.” | Không; cần kiểm soát quyền/cô lập ở kiến trúc thích hợp. |
| “Java 17 có JPMS thì không cần TCCL nữa.” | TCCL vẫn dùng trong các SPI API; `ModuleLayer` cũng cung cấp discovery theo layer khi phù hợp. |

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao system loader thường không load được class mà plugin loader con tự định nghĩa?

**Đáp án:** Parent delegation mặc định theo chiều child → parent. Parent không tự có danh sách class của child và cũng không tự search toàn bộ child loaders.

**2.** `ServiceLoader.load(Greeting.class)` chọn loader nào trong Java 17?

**Đáp án:** Theo API, chọn **TCCL của thread gọi**. Nó tương đương `ServiceLoader.load(Greeting.class, Thread.currentThread().getContextClassLoader())` về chọn loader.

**3.** Vì sao `Discovery.inspect()` trong ví dụ vẫn tìm được plugin, dù `Discovery` được system loader định nghĩa?

**Đáp án:** `Discovery` gọi `ServiceLoader.load(Greeting.class)`, API này chọn TCCL. `Launcher` đã đặt TCCL thành plugin loader nên metadata và provider của plugin được tìm thấy, dù defining loader của `Discovery` không đổi.

**4.** Có thể dùng `Class.forName("plugin.HelloGreeting")` thay `ServiceLoader.load` mà kỳ vọng cùng kết quả khi đổi TCCL không?

**Đáp án:** Không mặc định. `Class.forName(String)` chọn defining loader của class chứa call site. Nếu muốn chỉ định plugin loader phải dùng overload `Class.forName(name, initialize, pluginLoader)`.

**5.** Vì sao cần đặt `api.Greeting` ở parent/shared loader?

**Đáp án:** Host và plugin phải dùng **cùng định nghĩa interface**. Nếu mỗi loader tự define một bản, cùng tên binary vẫn có thể là hai kiểu JVM khác nhau; provider không assignable tới service type phía host.

**6.** Có nên giữ TCCL của plugin A trên một thread pool worker khi request A kết thúc không?

**Đáp án:** Không. Request B có thể dùng nhầm provider của A và giữ tham chiếu tới plugin A. Khôi phục context cũ bằng `finally`.

**7.** Java module `m.app` dùng `ServiceLoader` thì khi nào cần khai báo `uses api.Greeting;`?

**Đáp án:** Trong named-module code, nếu module dùng service type đó để khám phá providers theo `ServiceLoader`, module declaration cần khai báo `uses` tương ứng. Provider module khai báo `provides ... with ...` phù hợp.

**8.** Nếu TCCL là `null`, các API `ServiceLoader.load(service)` và `Class.forName(name, true, null)` có cùng nghĩa loader không?

**Đáp án:** Không. Theo `ServiceLoader`, loader `null` biểu thị system loader (nếu có, fallback bootstrap). Với overload `Class.forName` có tham số `ClassLoader`, `null` là bootstrap loader.

**9.** Trong ví dụ nếu bỏ SPI descriptor nhưng giữ class provider, `ServiceLoader` sẽ thấy provider không?

**Đáp án:** Không qua cơ chế classpath `META-INF/services` của ví dụ. Class có thể tồn tại nhưng ServiceLoader không biết provider nào cần xét. Nếu dùng named modules, declaration `provides` là cơ chế khác.

**10.** API nền tảng có nên chủ động quét mọi plugin loader trong JVM không?

**Đáp án:** Không nên. Namespace/version, isolation và lifecycle khác nhau. Cần cơ chế discovery theo **context/loader/module layer** cụ thể; TCCL là một cách diễn đạt context đó khi API hỗ trợ.

## 15. Tóm tắt quy trình suy luận

Khi API nền tảng không thấy implementation ứng dụng, hãy hỏi:

1. **Interface/service** nằm ở loader/module nào, và implementation nằm ở đâu?
2. **Mã discovery** dùng `Class.forName`, `ServiceLoader` hay factory mechanism nào? API đó đọc **caller loader**, **TCCL**, **loader truyền vào**, hay **ModuleLayer**?
3. **TCCL tại thread đang chạy thật sự** là gì? Có executor/thread pool đổi ngữ cảnh không?
4. **Provider metadata** đã được đóng gói đúng (`META-INF/services` hoặc `provides`) chưa?
5. Host và provider có dùng **cùng class identity** cho service interface không?
6. Có **module access**, lifecycle/cache hoặc initialization error che khuất nguyên nhân không?

Tóm lại: **API nền tảng cần thấy cách triển khai của ứng dụng vì một hợp đồng mở chỉ hữu ích khi runtime tìm và gọi được provider do ứng dụng cung cấp.** Parent-first bảo vệ thứ tự delegation nhưng không tự tạo chiều nhìn xuống. **TCCL cung cấp lựa chọn loader theo ngữ cảnh của thread** cho các API như `ServiceLoader`, trong khi các hệ module/loader khác có thể dùng những cơ chế tường minh khác.

Nguồn chuẩn:

- [`java.util.ServiceLoader` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overload dùng TCCL, cách khai báo provider, khám phá ở module/classpath, lazy loading, cache/lifecycle.
- [`java.lang.Thread` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader` và kế thừa context.
- [`java.lang.ClassLoader` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation và defining loader.
- [`java.lang.Class` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `Class.forName` và loader được chọn.
