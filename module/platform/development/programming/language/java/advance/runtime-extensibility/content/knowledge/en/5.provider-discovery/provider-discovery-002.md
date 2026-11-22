# Phạm vi của `ServiceLoader.loadInstalled` và khác biệt với provider của ứng dụng

## 1. Vấn đề: “installed” không có nghĩa là “đã thêm vào ứng dụng”

`ServiceLoader` là API Java để **khám phá provider** của một service (thường là interface hoặc abstract class). Provider có thể nằm trong JDK/runtime, trong dependency của ứng dụng, trên application module path hoặc trong plugin JAR mà ứng dụng tự nạp. Việc provider “có mặt” ở đâu quyết định phương thức tìm kiếm phù hợp.

Trong Java 17+, `ServiceLoader.loadInstalled(Service.class)` có ý nghĩa **rất hẹp**: tạo `ServiceLoader` sử dụng **platform class loader**. Theo hợp đồng API, nó chỉ tìm các provider được cài đặt vào môi trường chạy Java theo phạm vi của loader này; **provider chỉ đặt trên application classpath hoặc application module path không được tìm thấy bằng phương thức này**.

Hai biểu thức sau tương đương:

~~~java
ServiceLoader.loadInstalled(MyService.class);

ServiceLoader.load(
    MyService.class,
    ClassLoader.getPlatformClassLoader()
);
~~~

Trong khi đó:

~~~java
ServiceLoader.load(MyService.class);
~~~

sử dụng **thread context class loader (TCCL)** tại thời điểm gọi, thường là application/system class loader khi ứng dụng chạy theo cách thông thường. Vì thế, `load` thường tìm được các provider của ứng dụng mà `loadInstalled` cố ý bỏ qua.

> **Điểm mấu chốt:** `loadInstalled` **không** mang nghĩa “quét mọi dependency đã cài bằng Maven/Gradle”, “quét mọi JAR đang chạy”, “quét thư mục plugins/” hoặc “tự tìm mọi provider của ứng dụng”. Nó là một lựa chọn **phạm vi class loader** cụ thể.

## 2. Class loader nào được sử dụng?

Với một cấu hình khởi động thông thường, quan hệ ủy quyền thường được hình dung như sau:

~~~text
Bootstrap class loader (thường biểu diễn bằng null)
          |
Platform class loader
          |
Application/System class loader
          |
Custom/plugin class loader (nếu ứng dụng tạo, thường parent-first)
~~~

Đây là sơ đồ trực quan về quan hệ parent thường gặp, không phải quy tắc duy nhất cho mọi custom class loader. Với JPMS, `ServiceLoader` còn có quy tắc tìm provider từ **named modules** và **module layers**; không nên chỉ suy từ thứ tự tìm class của mô hình cũ.

- **Bootstrap:** tải các class nền tảng thiết yếu; trong Java có thể nhận diện loader của một class bằng `Class#getClassLoader()`, có thể trả `null`.
- **Platform:** `ClassLoader.getPlatformClassLoader()`, cung cấp phần lớn class thuộc các platform modules thích hợp; **không phải** application/system loader.
- **Application/System:** `ClassLoader.getSystemClassLoader()`, thường là loader của mã ứng dụng khởi chạy bằng `java -cp`; cũng có vai trò đối với named modules của ứng dụng trong boot layer.
- **TCCL:** `Thread.currentThread().getContextClassLoader()`, là một thuộc tính của thread. Giá trị này **có thể thay đổi theo thread/framework**, nên không nên mặc định mọi lời gọi `load(Service.class)` sẽ dùng system loader.
- **Custom/plugin loader:** ứng dụng tạo để đưa JAR vào khả năng tìm class; muốn `ServiceLoader` tìm provider theo loader này thì ứng dụng phải chọn overload phù hợp.

Với Java 17+, có thể tóm tắt:

| Lời gọi | Nguồn tìm kiếm chính | Provider trên application classpath | Provider của named module ứng dụng |
|---|---|---|---|
| `ServiceLoader.load(S.class)` | TCCL của thread hiện tại | Có, **nếu** TCCL nhìn thấy cấu hình service và provider | Có, nếu phạm vi loader/module layer cho phép |
| `ServiceLoader.load(S.class, loader)` | Loader chỉ định và cơ chế khám phá provider tương ứng | Có, nếu loader nhìn thấy | Có, theo quy tắc named module và layer liên quan của loader |
| `ServiceLoader.loadInstalled(S.class)` | **Platform class loader** | **Không** | **Không** với các provider nằm trên application module path |
| `ServiceLoader.load(layer, S.class)` | Named modules trong `layer` và các parent layers | **Không** tìm provider ở unnamed module/classpath | Có, nếu named module đã được resolve trong layer được duyệt |

Bảng nói về **khả năng phát hiện**, không cam kết có provider. Ngay cả khi chọn đúng overload, `ServiceLoader` cần metadata đăng ký provider, module được resolve, type tương thích và quyền truy cập phù hợp.

### Tên gọi dễ gây hiểu nhầm

- “JAR được cài vào ứng dụng” không đồng nghĩa “installed provider” của `loadInstalled`.
- “Provider thuộc boot layer” không đồng nghĩa “provider thuộc platform loader”: boot layer có thể chứa module ứng dụng được định nghĩa bởi application loader.
- “JAR đã nằm trên module path” không tự đảm bảo module đó **được resolve**; có thể cần `requires`, `--add-modules` hoặc cơ chế liên kết khác.
- “Provider có trong thư mục plugin” không có nghĩa class loader đang dùng đã được cấu hình để đọc thư mục ấy.

## 3. Provider của ứng dụng được khai báo thế nào?

### 3.1. Provider trên classpath (unnamed module)

Một service kiểu:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

có thể có implementation trong JAR hoặc thư mục classpath. Provider đăng ký qua resource:

~~~text
META-INF/services/demo.spi.GreetingService
~~~

Nội dung file là tên class implementation (mỗi dòng một tên):

~~~text
demo.impl.LocalGreetingService
~~~

`ServiceLoader.load(GreetingService.class)` thường tìm file này qua TCCL. `ServiceLoader.load(GreetingService.class, loader)` tìm thông qua loader được chỉ định. Ngược lại, `loadInstalled` không tìm resource/provider chỉ có trên application classpath.

Lưu ý: chỉ **implements interface** chưa đủ để được phát hiện; cần metadata hợp lệ. Ngược lại, resource cấu hình provider có mặt nhưng class provider không thể được loader tải, hoặc không tương thích với service, có thể khiến việc duyệt thất bại với `ServiceConfigurationError`.

### 3.2. Provider trên application module path (named module)

Đối với named module, service và provider được khai báo bằng `module-info.java`:

~~~java
// Module host / consumer
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

~~~java
// Module provider
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.LocalGreetingService;
}
~~~

`uses` khai báo module cần khám phá service; `provides ... with ...` khai báo provider. Provider module cần được **resolve** vào module graph. `ServiceLoader.load(...)` hoặc `load(ModuleLayer.boot(), ...)` có thể tìm provider này nếu điều kiện tương ứng thỏa mãn, nhưng `loadInstalled` vẫn bỏ qua các provider chỉ hiện diện trên **application module path**.

Với caller là explicit named module, thiếu `uses` cho service có thể làm lời gọi `ServiceLoader` ném `ServiceConfigurationError`. Không nên xử lý lỗi này bằng cách chuyển bừa sang `loadInstalled`.

## 4. Ví dụ chạy được: provider ứng dụng trên classpath

Ví dụ này sử dụng Java 17+, chỉ có **một provider**, nên đầu ra có thứ tự ổn định. Nó minh họa ngay cùng một service: `load` thấy provider, `loadInstalled` không thấy.

Tạo thư mục như sau:

~~~text
demo-classpath/
  src/
    demo/
      spi/
        GreetingService.java
      impl/
        LocalGreetingService.java
      App.java
  out/
    META-INF/
      services/
        demo.spi.GreetingService
~~~

`src/demo/spi/GreetingService.java`:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

`src/demo/impl/LocalGreetingService.java`:

~~~java
package demo.impl;

import demo.spi.GreetingService;

public final class LocalGreetingService implements GreetingService {
    @Override
    public String greet() {
        return "Xin chao tu ung dung";
    }
}
~~~

`src/demo/App.java`:

~~~java
package demo;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        System.out.println("context=" + names(
                ServiceLoader.load(GreetingService.class)));

        System.out.println("system=" + names(ServiceLoader.load(
                GreetingService.class, ClassLoader.getSystemClassLoader())));

        System.out.println("installed=" + names(
                ServiceLoader.loadInstalled(GreetingService.class)));

        System.out.println("platform=" + names(ServiceLoader.load(
                GreetingService.class, ClassLoader.getPlatformClassLoader())));
    }

    private static String names(ServiceLoader<GreetingService> services) {
        return services.stream()
                .map(provider -> provider.type().getName())
                .toList()
                .toString();
    }
}
~~~

Tạo file `out/META-INF/services/demo.spi.GreetingService` với **đúng** nội dung:

~~~text
demo.impl.LocalGreetingService
~~~

Từ thư mục `demo-classpath/`, dùng Bash (Linux/macOS hoặc Git Bash):

~~~bash
mkdir -p out/META-INF/services

printf '%s\n' 'demo.impl.LocalGreetingService' \
  > out/META-INF/services/demo.spi.GreetingService

javac -d out \
  src/demo/spi/GreetingService.java \
  src/demo/impl/LocalGreetingService.java \
  src/demo/App.java

java -cp out demo.App
~~~

Đầu ra với thiết lập ví dụ này:

~~~text
context=[demo.impl.LocalGreetingService]
system=[demo.impl.LocalGreetingService]
installed=[]
platform=[]
~~~

**Giải thích từng dòng:**

1. `context`: `load(S.class)` dùng TCCL. Java launcher thông thường gán system/application loader làm TCCL, nên nó tìm được resource `META-INF/services/...` ở `out`.
2. `system`: truyền tường minh system class loader, vẫn tìm được provider.
3. `installed`: dùng platform class loader. Provider chỉ có trên application classpath nên kết quả rỗng.
4. `platform`: dùng chính platform loader một cách tường minh; kết quả giống `loadInstalled`, chứng minh tính tương đương của hai lời gọi.

`stream().map(provider -> provider.type().getName())` ở đây liệt kê **loại provider** mà không gọi `Provider.get()` để tạo instance. Nếu muốn gọi hành vi provider, duyệt các đối tượng `GreetingService` bằng `iterator()` hoặc gọi `Provider.get()`.

**Điều kiện quan trọng của đầu ra:** phải đặt file descriptor vào `out/META-INF/services/` trước khi chạy và dùng classpath `out`; ví dụ dùng một provider ứng dụng tự định nghĩa, không giả định JDK có provider cài sẵn cho service này. Nếu file `META-INF/services/...` thiếu, cả `context` và `system` cũng sẽ rỗng.

Trên Windows CMD/PowerShell, lệnh `javac` nhiều dòng cần chuyển thành một dòng hoặc cú pháp xuống dòng của shell tương ứng. Ví dụ trên dùng một phần tử classpath nên không phát sinh khác biệt dấu `:`/`;`.

## 5. Ví dụ chạy được: provider ứng dụng trên module path

Không chỉ classpath: `loadInstalled` cũng **không** dùng để khám phá provider nằm trên application module path. Ví dụ này dùng ba named modules, để tách service API khỏi host và provider.

Cây thư mục:

~~~text
demo-modules/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.provider/
      module-info.java
      demo/provider/LocalGreetingService.java
    demo.host/
      module-info.java
      demo/host/Main.java
~~~

`src/demo.spi/module-info.java`:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

`src/demo.spi/demo/spi/GreetingService.java`:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

`src/demo.provider/module-info.java`:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.LocalGreetingService;
}
~~~

`src/demo.provider/demo/provider/LocalGreetingService.java`:

~~~java
package demo.provider;

import demo.spi.GreetingService;

public final class LocalGreetingService implements GreetingService {
    @Override
    public String greet() {
        return "Xin chao tu module ung dung";
    }
}
~~~

`src/demo.host/module-info.java`:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

`src/demo.host/demo/host/Main.java`:

~~~java
package demo.host;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        System.out.println("load=" + names(
                ServiceLoader.load(GreetingService.class)));

        System.out.println("installed=" + names(
                ServiceLoader.loadInstalled(GreetingService.class)));

        System.out.println("bootLayer=" + names(
                ServiceLoader.load(ModuleLayer.boot(), GreetingService.class)));
    }

    private static String names(ServiceLoader<GreetingService> loader) {
        return loader.stream()
                .map(p -> p.type().getName())
                .toList()
                .toString();
    }
}
~~~

Biên dịch và chạy tại `demo-modules/` trên Bash:

~~~bash
mkdir -p mods
javac --module-source-path src -d mods \
  $(find src -type f -name '*.java')

java --module-path mods \
  --add-modules demo.provider \
  --module demo.host/demo.host.Main
~~~

Đầu ra:

~~~text
load=[demo.provider.LocalGreetingService]
installed=[]
bootLayer=[demo.provider.LocalGreetingService]
~~~

**Vì sao khác nhau?**

- `demo.provider` được đặt trong application module path và được **resolve** nhờ `--add-modules demo.provider`. `module-info.java` cung cấp metadata `provides`; host khai báo `uses`.
- `load(S.class)` chạy với TCCL mặc định trong ví dụ và khám phá được provider module ứng dụng.
- `load(ModuleLayer.boot(), S.class)` duyệt named modules trong boot layer và parent layers. Vì provider đã được resolve vào boot layer nên được tìm thấy. Overload này **không** tìm provider trong unnamed modules/classpath.
- `loadInstalled(S.class)` chọn **platform class loader**, không nhận provider application module path chỉ vì provider đã có mặt trong boot layer.

Chú ý phân biệt **boot layer** với **bootstrap/platform class loader**: hai khái niệm là phạm vi module graph và cơ chế tải class, không thay thế cho nhau. Một module ứng dụng có thể nằm trong boot layer mà vẫn không thuộc phạm vi khám phá của `loadInstalled`.

Nếu bỏ `--add-modules demo.provider` và không có cách khác khiến module provider được resolve, đừng mặc định module provider đã tham gia graph chỉ vì file của nó nằm trong `mods/`. Trình chọn roots và service binding ảnh hưởng kết quả.

## 6. Muốn khám phá plugin được nạp lúc chạy thì dùng gì?

Một ứng dụng có thư mục `plugins/` có thể tự quét JAR, tạo loader/layer phù hợp và dùng overload khám phá provider tương ứng. `loadInstalled` **không** quét thư mục này và **không** tạo class loader mới.

### Plugin JAR kiểu classpath

Nếu host nạp JAR bằng `URLClassLoader` và API service `GreetingService` được cung cấp bởi parent loader chung:

~~~java
// Ví dụ đoạn mã tích hợp, không phải chương trình độc lập.
// pluginUrls là URL[] của các plugin JAR đã được host kiểm tra.
try (URLClassLoader pluginLoader =
             new URLClassLoader(pluginUrls,
                                GreetingService.class.getClassLoader())) {
    ServiceLoader<GreetingService> discovered =
            ServiceLoader.load(GreetingService.class, pluginLoader);

    for (GreetingService provider : discovered) {
        System.out.println(provider.greet());
    }
}
~~~

Cần import `java.net.URLClassLoader` và `java.util.ServiceLoader`, đồng thời dùng API chung và `pluginUrls` đã được cấu hình. Host thực tế phải giữ loader sống khi provider còn hoạt động; `close()` chỉ nên thực hiện sau khi dừng plugin và giải phóng tài nguyên.

Ưu tiên chỉ định loader tường minh khi provider thuộc plugin riêng. Nếu dùng `load(S.class)` mà TCCL đang là loader khác, việc không thấy plugin là điều có thể xảy ra. Việc tự đổi TCCL có thể cần trong một số framework, nhưng phải phục hồi trạng thái cũ bằng `finally` và xem xét tác động đến mã khác cùng thread.

### Plugin là named module trong module layer mới

Nếu host resolve plugin vào một `ModuleLayer` do ứng dụng tạo:

~~~java
// Đoạn mã tích hợp, giả định pluginLayer đã được tạo và
// GreetingService là API chung mà host và plugin cùng dùng.
ServiceLoader<GreetingService> discovered =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Overload `load(layer, service)` chỉ khám phá provider trong **named modules** của layer và các layer cha; không thay thế việc đọc `META-INF/services` ở các JAR thuộc unnamed modules. Host phải kiểm soát module resolution, API chung, dependencies, class identity và vòng đời plugin.

### So sánh mục đích

| Yêu cầu | Cách phù hợp |
|---|---|
| Tìm provider có trong classpath của ứng dụng | `ServiceLoader.load(S.class)` khi TCCL đúng, hoặc `load(S.class, applicationLoader)` |
| Tìm provider trong JAR nạp bởi custom loader | `ServiceLoader.load(S.class, pluginLoader)` |
| Tìm provider của named module trong layer đã có | `ServiceLoader.load(layer, S.class)` |
| Cố ý giới hạn việc tìm ở các provider “installed” có thể thấy qua platform loader | `ServiceLoader.loadInstalled(S.class)` |
| Quét thư mục, kiểm tra phiên bản, cài/gỡ, cách ly và thay plugin | **Plugin manager của ứng dụng**; dùng các overload trên như một bước của quá trình |

Một công cụ quản lý plugin thường cần phân biệt rõ **phát hiện JAR**, **nạp mã**, **khám phá service**, **khởi tạo provider**, **đăng ký vào host**, **dừng và giải phóng**. `ServiceLoader` giải quyết phần khám phá/khởi tạo provider theo metadata, không cung cấp đầy đủ vòng đời cài đặt plugin.

## 7. Vì sao vẫn có tên `loadInstalled`? Góc nhìn từ Java 8 sang Java 9+

Ở JDK 8 và cũ hơn, Java có **extension mechanism** (ví dụ thư mục `jre/lib/ext`). Cách diễn giải “installed provider” thời đó gắn với extension class loader và các extension JAR được cài vào runtime.

Từ JDK 9, extension mechanism đã bị loại bỏ, runtime Java được tổ chức theo module. `loadInstalled` **vẫn tồn tại**, nhưng trong Java 17+ nó được mô tả bằng **platform class loader**:

~~~java
ClassLoader.getPlatformClassLoader()
~~~

Vì thế cần tránh hai suy luận sai:

1. **Không** sao chép JAR vào `JAVA_HOME/lib/ext` hay cấu hình `java.ext.dirs` để “cài provider” trên JDK mới. Cơ chế extension cũ không còn được hỗ trợ; với thư viện ứng dụng cần khai báo classpath/module path hoặc dùng plugin manager.
2. **Không** xem `loadInstalled` như danh sách tất cả provider được tải bởi JVM. Nó giới hạn cách tìm theo platform loader; trong một ứng dụng Java bình thường, kết quả có thể rỗng ngay cả khi `load(S.class)` trả về provider đang hoạt động.

Tên “installed” là thuật ngữ API có lịch sử; quyết định kỹ thuật phải dựa vào hợp đồng class loader hiện tại, không dựa vào nghĩa thông thường của từ “installed”.

## 8. Cơ chế tìm kiếm lazy, cache và lỗi

Các overload của `ServiceLoader` trước hết **tạo đối tượng loader dịch vụ**. Provider được tìm và/hoặc khởi tạo **theo nhu cầu** trong quá trình duyệt `iterator()`, `stream()`, `findFirst()` hoặc `Provider.get()`. Điều này có các hệ quả:

- Đã gọi `loadInstalled(S.class)` mà chưa duyệt thì chưa thể kết luận chính xác số provider được tìm thấy. Khi thử nghiệm, cần duyệt kết quả.
- `stream()` trả `ServiceLoader.Provider<S>` để có thể xem `type()` rồi chọn provider; `get()` mới lấy hoặc tạo instance. `iterator()` trực tiếp trả instance provider.
- `ServiceLoader` giữ cache các provider đã tải. `reload()` xóa **cache của chính đối tượng ServiceLoader**, không tự đưa JAR mới vào classpath, không biến platform loader thành application loader, không tự thay đổi module graph và không tự unload class.
- Thứ tự provider trong named modules không được cam kết thống nhất giữa các module; hệ thống có nhiều provider không nên chọn một provider chỉ theo “phần tử đầu tiên” nếu thứ tự là yêu cầu nghiệp vụ.
- Không thấy provider và **lỗi provider** là hai tình huống khác nhau: trường hợp đầu có thể trả danh sách rỗng; descriptor sai, class thiếu, constructor/provider method không hợp lệ hoặc lỗi khởi tạo có thể ném `ServiceConfigurationError` khi duyệt.
- `ServiceLoader` và provider không nên được chia sẻ tùy tiện giữa các thread khi đồng thời thay đổi cache. Thiết kế việc khởi tạo, reload và quản lý instance theo vòng đời riêng của ứng dụng.

Lỗi phổ biến là thử `reload()` khi nguyên nhân thực sự là **sai phạm vi class loader**. Với provider chỉ nằm trên application classpath/module path, gọi `reload()` trên một đối tượng tạo từ `loadInstalled` vẫn không giúp tìm được provider đó.

## 9. Chẩn đoán khi `loadInstalled` trả về rỗng

| Triệu chứng | Cần xác minh | Hành động phù hợp |
|---|---|---|
| `load(S.class)` có provider, `loadInstalled(S.class)` rỗng | Provider thuộc application classpath/module path? | Đây là khác biệt phạm vi bình thường; dùng `load` phù hợp |
| Cả hai đều rỗng | Metadata `META-INF/services` hay `provides` có đúng không? Module đã resolve chưa? | Kiểm tra descriptor, module graph và loader thực tế |
| `load(S.class)` không thấy provider trong plugin JAR | TCCL có nhìn thấy JAR và resource service không? | Truyền plugin loader tường minh hoặc thiết kế lại TCCL |
| `load(layer, S.class)` không thấy provider | Provider có nằm trong named module của layer hoặc parent layer không? | Resolve module vào đúng layer, kiểm tra `uses`/`provides` |
| Gặp `ServiceConfigurationError` | Service/implementation có tương thích? Constructor, provider method và module declarations hợp lệ? | Sửa cấu hình hoặc implementation; đọc nguyên nhân gốc của lỗi |
| Sau khi thay JAR vẫn thấy phiên bản cũ | Loader/layer và provider instance cũ còn tồn tại? | Dừng plugin, loại bỏ tham chiếu, tạo loader/layer mới và khởi tạo lại |
| Provider được tìm nhưng bị `ClassCastException` | Host/plugin có nạp hai bản sao của service API qua các loader khác nhau? | Đưa SPI chung vào loader/module cha phù hợp; kiểm soát class identity |

Một số giá trị hữu ích để log khi debug:

~~~java
System.out.println("TCCL: " +
        Thread.currentThread().getContextClassLoader());
System.out.println("system: " + ClassLoader.getSystemClassLoader());
System.out.println("platform: " + ClassLoader.getPlatformClassLoader());
System.out.println("service loader: " + GreetingService.class.getClassLoader());
~~~

Đây là đoạn mã minh họa, cần class `GreetingService` từ các ví dụ trước. Trong hệ thống thực tế cũng nên ghi **tên provider, module chứa provider, loader định nghĩa class và đường dẫn JAR** khi có thể. Log giúp xác định rõ provider đang ở phạm vi nào, thay vì đoán theo tên thư mục.

## 10. Bài tự kiểm tra

1. **Đã thêm dependency chứa provider vào Maven/Gradle và ứng dụng gọi được service. `loadInstalled` có bắt buộc tìm ra provider đó không?** Không. Dependency chỉ được đưa vào phạm vi ứng dụng thì `loadInstalled` không khám phá nó.
2. **Có thể viết `ServiceLoader.load(S.class, ClassLoader.getPlatformClassLoader())` để thay `loadInstalled(S.class)` không?** Có, đó là cách tương đương trong Java 17+.
3. **Vì sao `load(S.class)` có thể hoạt động ở luồng A nhưng không thấy provider ở luồng B?** Hai thread có thể có TCCL khác nhau, đặc biệt trong application server hoặc framework/plugin host.
4. **`load(ModuleLayer.boot(), S.class)` có luôn tương đương `loadInstalled(S.class)` không?** Không. Boot layer có thể chứa named module ứng dụng, còn `loadInstalled` dựa vào platform loader; hai phương thức khác phạm vi.
5. **Provider trong `plugins/hello.jar` có tự xuất hiện khi gọi `loadInstalled` không?** Không. Host phải nạp JAR hoặc module bằng loader/layer thích hợp rồi khám phá provider trong phạm vi đó.
6. **`ServiceLoader.reload()` có thể cài đặt JAR mới vào runtime không?** Không. Nó chỉ xóa cache provider của `ServiceLoader`; đường tìm class/module và lifecycle plugin do cơ chế khác quản lý.
7. **Với explicit named module của ứng dụng, `uses` có cần thiết không?** Có. Module dùng `ServiceLoader` phải khai báo `uses` cho service tương ứng theo hợp đồng JPMS.

**Ghi nhớ:** `loadInstalled` = khám phá với **platform class loader**, chủ đích bỏ qua provider thuộc phạm vi ứng dụng. Đối với provider trên classpath, application module path hoặc plugin loader/layer, hãy chọn `load` với TCCL, loader hoặc module layer tương ứng. Đừng dùng tên “installed” để suy luận rằng API sẽ tự quét tất cả provider mà ứng dụng triển khai.

## Tài liệu tham khảo

- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): đặc tả `load`, `loadInstalled`, `load(ModuleLayer, ...)`, cơ chế lazy/cache và lỗi provider.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getPlatformClassLoader()`, `getSystemClassLoader()` và quan hệ class loader.
- [Oracle JDK Migration Guide — Removed Extension Mechanism](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html): cơ chế `lib/ext` và `java.ext.dirs` đã bị loại bỏ từ Java 9.
