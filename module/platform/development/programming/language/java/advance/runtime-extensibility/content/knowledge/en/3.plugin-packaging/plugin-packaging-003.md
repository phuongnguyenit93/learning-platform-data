# Classpath, module path và thư mục plugin do ứng dụng quản lý

Trong Java, cả ba khái niệm đều liên quan đến việc tìm và sử dụng mã đã biên dịch, nhưng chúng trả lời **ba câu hỏi khác nhau**:

- **Classpath:** JVM hoặc class loader tìm các lớp và tài nguyên theo những đường dẫn nào?
- **Module path:** hệ thống module Java (JPMS) tìm những module nào để giải quyết quan hệ phụ thuộc, quyền truy cập và cấu hình module?
- **Thư mục plugin do ứng dụng quản lý:** ứng dụng đặt gói mở rộng ở đâu, phát hiện chúng lúc nào và quyết định nạp, khởi tạo, vô hiệu hóa hoặc thay thế chúng ra sao?

Một thư mục tên `plugins/` không tự trở thành classpath hay module path. Ứng dụng có thể dùng chính các JAR trong thư mục đó để tạo `ClassLoader` hoặc `ModuleLayer` mới; lúc ấy thư mục là **quy ước triển khai do ứng dụng sở hữu**, còn class loader hoặc JPMS mới là cơ chế nạp mã.

## 1. So sánh nhanh

| Tiêu chí | Classpath (`-cp` / `--class-path`) | Module path (`-p` / `--module-path`) | Thư mục plugin do ứng dụng quản lý |
|---|---|---|---|
| Bản chất | Danh sách thư mục và JAR có lớp/tài nguyên | Danh sách vị trí chứa module Java | Vị trí lưu các gói mở rộng theo quy ước của ứng dụng |
| Ai diễn giải? | Java launcher, compiler và class loader | Bộ giải quyết module của JPMS và module layer | Mã khởi động, bộ quét và bộ quản lý plugin của ứng dụng |
| Đơn vị chính | Class, package, resource; mã trên classpath thuộc unnamed module của class loader tương ứng | Named module với tên, phụ thuộc và quy tắc truy cập; có thể có automatic module | Gói plugin với ID, phiên bản, metadata, trạng thái và vòng đời do ứng dụng định nghĩa |
| Khả năng nhìn thấy | Phụ thuộc class loader và quy tắc delegation, không có ranh giới `exports` của named module giữa các JAR classpath | Phụ thuộc module được resolve, `requires`, `exports`, `opens` và layer | Phụ thuộc loader/layer mà ứng dụng tự tạo, API được chia sẻ và chính sách đăng ký |
| Phát hiện plugin tự động? | Không; thêm JAR vào classpath không mặc nhiên tạo đối tượng plugin | Không; đặt module lên module path không có nghĩa ứng dụng đã kích hoạt plugin | Chỉ khi ứng dụng tự quét, kiểm tra, nạp và đăng ký |
| Thay đổi sau khi JVM chạy | Classpath launcher không tự cập nhật; có thể tạo class loader riêng | Boot layer không tự nạp thêm module; có thể tạo layer mới | Có thể hỗ trợ cài/gỡ/nạp lại, nếu ứng dụng thiết kế vòng đời phù hợp |
| Trường hợp điển hình | Ứng dụng và thư viện Java truyền thống | Ứng dụng/module dùng JPMS để mô tả và kiểm soát liên kết | IDE, hệ thống tích hợp, ứng dụng desktop/server có cơ chế mở rộng |

**Lưu ý:** một JAR có thể nằm vật lý trong `plugins/`, nhưng được nạp bằng `URLClassLoader` theo kiểu classpath, hoặc được tìm bằng `ModuleFinder` và resolve thành named module. **Tên thư mục không quyết định cơ chế nạp.**

## 2. Classpath: đường tìm class và resource

Ví dụ trên Linux/macOS, khởi chạy một ứng dụng không modular:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

`-cp` khai báo các đường dẫn để Java launcher thiết lập classpath. Dấu `:` phân tách đường dẫn trên Linux/macOS; Windows dùng `;`. Wildcard `lib/*` bao gồm các JAR trực tiếp trong `lib`, không quét đệ quy thư mục con. Cách chạy `java -jar app.jar` sử dụng entry point trong manifest và bỏ qua tùy chọn `-cp` của launcher; classpath bổ sung, nếu cần, phải được xử lý theo quy tắc manifest hoặc cách khởi chạy khác.

Các điểm quan trọng:

1. Khi không khai báo `module-info.java` và đặt JAR trên classpath, lớp thuộc **unnamed module** của class loader đã định nghĩa lớp đó. Các package trong những JAR như vậy không tạo ra module boundary riêng theo từng JAR.
2. JVM không có một kho class toàn cục duy nhất. `ClassLoader` tìm class theo tên nhị phân; đa số loader chuẩn dùng cơ chế ủy quyền cho parent trước. Hai loader khác nhau có thể định nghĩa hai lớp **cùng tên** nhưng JVM vẫn xem chúng là **hai kiểu khác nhau**.
3. Thư viện JAR có mặt trên classpath chỉ làm mã của nó có thể được tìm thấy. Ứng dụng vẫn phải gọi API, quét annotation, dùng `ServiceLoader` hoặc có cơ chế khác để tạo và đăng ký thành phần.
4. Đổi `java.class.path` bằng `System.setProperty` sau khi JVM đã chạy **không tự cập nhật** những loader hiện hữu. Với plugin nạp lúc runtime, ứng dụng thường tạo loader riêng.
5. `ServiceLoader` trên classpath tìm file descriptor `META-INF/services/<tên-interface-đầy-đủ>`. Mỗi dòng hợp lệ trong file chứa tên đầy đủ của lớp provider. Classpath và `ServiceLoader` làm hai việc khác nhau: một bên cho phép tìm class, bên kia tìm nhà cung cấp dịch vụ theo hợp đồng.

### Khi nào classpath hợp lý?

Dùng classpath khi phụ thuộc đã biết từ lúc triển khai, bạn không cần quy tắc module JPMS và ứng dụng có mô hình build/runtime truyền thống. Classpath đơn giản để triển khai nhưng dễ gặp trùng thư viện, xung đột phiên bản và tình trạng nhiều thành phần cùng thấy các package mà lẽ ra nên che giấu.

## 3. Module path: nơi JPMS tìm và resolve named module

Từ Java 9, Java Platform Module System (JPMS) cho phép mô tả một module bằng `module-info.java`. Ví dụ một API công khai:

~~~java
module com.example.greeting.api {
    exports com.example.api;
}
~~~

Một module plugin phụ thuộc vào API và cung cấp implementation:

~~~java
module com.example.greeting.plugin {
    requires com.example.greeting.api;
    provides com.example.api.GreetingPlugin
        with com.example.plugin.HelloPlugin;
}
~~~

Một module host dùng service này:

~~~java
module com.example.greeting.host {
    requires com.example.greeting.api;
    uses com.example.api.GreetingPlugin;
}
~~~

Đây là **các descriptor minh họa cho phương án JPMS**, tách biệt với ví dụ classpath có thể chạy ở mục 5. Với dự án đã biên dịch thành các modular JAR trong `mods/`, lệnh khởi chạy có thể có dạng:

~~~bash
java --module-path mods \
     --add-modules com.example.greeting.plugin \
     --module com.example.greeting.host/com.example.host.Main
~~~

Lệnh này giả định `com.example.host.Main` là điểm vào hợp lệ và đã có đủ modular JAR. `--add-modules` đưa module plugin vào tập module root được resolve; việc đặt JAR trong `mods/` đơn thuần không đảm bảo nó đã được resolve hoặc được ứng dụng sử dụng.

Hiểu bốn khái niệm sau:

- **Resolve/readability:** JPMS chọn các module tham gia graph; `requires` khai báo phụ thuộc module. Một named module chỉ đọc những module mà graph cho phép.
- **Exports:** `exports package` cho phép module khác truy cập những kiểu `public` trong package đó theo quy tắc JPMS. Một kiểu `public` trong package không export không tự trở thành API công khai cho module khác.
- **Opens:** `opens package` cho phép deep reflection theo phạm vi khai báo; khác với `exports`. Một framework dùng reflection có thể cần `opens` mà không cần package đó được export cho mọi consumer.
- **Service binding:** `uses` và `provides ... with ...` là cách mô tả nhà dùng và nhà cung cấp service trong named module. `ServiceLoader` có thể dùng thông tin này sau khi các module liên quan được resolve.

Một JAR không có `module-info.class` có thể được xử lý như **automatic module** khi đặt trên module path. Đây là cơ chế hỗ trợ chuyển đổi, nhưng tên module suy ra từ tên JAR có thể không ổn định; nên ưu tiên tên module được khai báo rõ khi thiết kế lâu dài.

**Module path không đồng nghĩa cơ chế hot plugin.** Boot layer được thiết lập lúc khởi động và không tự cập nhật khi bạn chép thêm file JAR. Với modular plugin được bổ sung lúc chạy, ứng dụng phải thực hiện các bước như tìm module bằng `ModuleFinder`, resolve `Configuration`, tạo `ModuleLayer` mới và khám phá service. Cách này cần xử lý tên module, quan hệ phụ thuộc, package và loader cẩn thận.

## 4. Thư mục plugin: quy ước triển khai và vòng đời của ứng dụng

Cấu trúc triển khai có thể là:

~~~text
my-app/
  app.jar
  lib/
    greeting-api.jar
  plugins/
    hello-plugin.jar
    reporting-plugin.jar
~~~

`plugins/` chỉ là một thư mục trên filesystem. Nếu chạy:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

thì các JAR ở `plugins/` **không nằm trong classpath của lệnh trên**. Chúng cũng không tự tham gia JPMS module graph. Muốn biến chúng thành plugin, host phải có giao thức cụ thể, chẳng hạn:

1. Định nghĩa **hợp đồng mở rộng** ổn định: interface/SPI, cấu hình, version API và quyền mà plugin được sử dụng.
2. Phát hiện JAR hoặc gói plugin trong thư mục; kiểm tra loại file, metadata, ID và phiên bản phù hợp.
3. Chọn cơ chế nạp: `URLClassLoader` cho plugin kiểu classpath; `ModuleFinder` và `ModuleLayer` cho plugin dạng named module.
4. Tìm implementation qua `ServiceLoader`, một entry point khai báo trong manifest hoặc giao thức riêng; kiểm tra provider hợp lệ.
5. Đăng ký, khởi động, theo dõi trạng thái, ngắt kết nối và giải phóng tài nguyên theo vòng đời do host quản lý.

Quy trình này giải thích vì sao **phát hiện file**, **nạp class**, **khởi tạo đối tượng** và **kích hoạt chức năng** là bốn sự kiện riêng biệt. Chép JAR vào thư mục chưa đủ để kết luận plugin đã chạy.

### Quan hệ giữa host, API và implementation

~~~text
Host/application
    |
    +-- Shared API / SPI: GreetingPlugin  (host/parent loader)
    |
    +-- Plugin manager: quét plugins/*.jar
            |
            +-- URLClassLoader hoặc ModuleLayer mới
                    |
                    +-- Plugin implementation
                    +-- Thư viện phụ thuộc của plugin (nếu được cung cấp)
~~~

API chung nên do host/parent loader hoặc module chung cung cấp. Nếu một plugin vô tình đóng gói **bản sao** của chính API này trong class loader riêng, hai kiểu có cùng tên vẫn có thể không tương thích, gây `ClassCastException` hoặc lỗi tương tự về định danh kiểu.

## 5. Ví dụ Java 17+: host tự nạp plugin JAR từ thư mục

Ví dụ dưới đây **chạy được** trên Java 17+ và không dùng JPMS. Host được biên dịch cùng API, nhưng implementation nằm trong JAR ở `plugins/`, không xuất hiện trên classpath khi khởi động host.

Cấu trúc mã nguồn ban đầu:

~~~text
demo/
  src/
    api/com/example/api/GreetingPlugin.java
    plugin/com/example/plugin/HelloPlugin.java
    host/com/example/host/Host.java
~~~

**Bước 1 — API chung** (`src/api/com/example/api/GreetingPlugin.java`):

~~~java
package com.example.api;

public interface GreetingPlugin {
    String id();
    String greet(String name);
}
~~~

**Bước 2 — implementation của plugin** (`src/plugin/com/example/plugin/HelloPlugin.java`):

~~~java
package com.example.plugin;

import com.example.api.GreetingPlugin;

public final class HelloPlugin implements GreetingPlugin {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

**Bước 3 — host liệt kê JAR, tạo loader và tìm provider** (`src/host/com/example/host/Host.java`):

~~~java
package com.example.host;

import com.example.api.GreetingPlugin;
import java.io.UncheckedIOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Stream;

public final class Host {
    public static void main(String[] args) throws Exception {
        Path pluginDir = Path.of("plugins");
        List<URL> jarUrls;

        try (Stream<Path> paths = Files.list(pluginDir)) {
            jarUrls = paths
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".jar"))
                    .sorted()
                    .map(p -> {
                        try {
                            return p.toUri().toURL();
                        } catch (MalformedURLException e) {
                            throw new UncheckedIOException(e);
                        }
                    })
                    .toList();
        }

        try (URLClassLoader loader = new URLClassLoader(
                jarUrls.toArray(URL[]::new),
                GreetingPlugin.class.getClassLoader())) {
            int count = 0;
            for (GreetingPlugin plugin
                    : ServiceLoader.load(GreetingPlugin.class, loader)) {
                System.out.println(plugin.id() + " -> " + plugin.greet("Java"));
                count++;
            }
            if (count == 0) {
                System.out.println("Không tìm thấy plugin.");
            }
        }
    }
}
~~~

Ở đây:

- `Files.list` chỉ **phát hiện file**; nó không nạp class.
- `URLClassLoader` đưa các JAR vào khả năng tìm class của loader plugin. Parent loader là loader của `GreetingPlugin`, giúp API dùng chung có cùng định danh kiểu.
- `ServiceLoader.load(GreetingPlugin.class, loader)` tìm cấu hình provider qua loader được chỉ định và tạo implementation khi duyệt. Nếu chỉ gọi overload mặc định dùng context class loader, kết quả có thể khác tùy thread đang chạy.
- `try-with-resources` đóng loader khi kết thúc quá trình duyệt. Trong hệ thống plugin thực tế, host giữ loader sống suốt thời gian plugin còn hoạt động rồi mới đóng.

**Bước 4 — biên dịch và đóng gói trên Bash (Linux/macOS hoặc Git Bash trên Windows)**. Chạy tại thư mục `demo/`:

~~~bash
mkdir -p build/api build/plugin build/host plugins

javac -d build/api src/api/com/example/api/GreetingPlugin.java
javac -cp build/api -d build/plugin src/plugin/com/example/plugin/HelloPlugin.java

mkdir -p build/plugin/META-INF/services
printf '%s\n' 'com.example.plugin.HelloPlugin' \
  > build/plugin/META-INF/services/com.example.api.GreetingPlugin

jar --create --file plugins/hello-plugin.jar -C build/plugin .

javac -cp build/api -d build/host src/host/com/example/host/Host.java
java -cp "build/api:build/host" com.example.host.Host
~~~

Kết quả chuẩn:

~~~text
hello -> Xin chào, Java!
~~~

Trên Windows khi dùng `java` hoặc `javac` trực tiếp trong PowerShell/CMD, ký tự phân tách classpath là `;`, ví dụ `java -cp "build/api;build/host" com.example.host.Host`. Các lệnh `mkdir -p` và `printf` trong đoạn trên dùng cú pháp Bash.

File `META-INF/services/com.example.api.GreetingPlugin` nằm **bên trong JAR plugin** và có nội dung đúng một dòng:

~~~text
com.example.plugin.HelloPlugin
~~~

Nếu bỏ file descriptor này, host vẫn có thể tìm class bằng loader nhưng `ServiceLoader` trong ví dụ sẽ không biết provider nào cần khởi tạo, nên in `Không tìm thấy plugin.`. Nếu thêm `plugins/hello-plugin.jar` trực tiếp vào `-cp` thì đó là triển khai theo classpath tĩnh, không còn minh họa cơ chế host tự quản lý thư mục plugin như trên.

### Những giới hạn có chủ ý của ví dụ

Ví dụ quét mỗi JAR trực tiếp trong `plugins/`, sử dụng **một loader chung cho tất cả plugin trong thư mục**, không quét đệ quy, không có cơ chế chữ ký, kiểm tra phiên bản, dependency resolution hay nạp lại khi file thay đổi. Nếu hai plugin mang các phiên bản xung đột của cùng một thư viện, loader chung vẫn có thể gây lỗi. Đây là bản mẫu để thấy rõ các bước nạp mã, chưa phải bộ quản lý plugin sản xuất.

## 6. Nếu plugin là named module thì khác gì?

Với JPMS, thay vì file `META-INF/services/...` trong JAR kiểu classpath, provider thường được khai báo qua `provides ... with ...` trong `module-info.java`; host là named module cần khai báo `uses`. Sau khi module plugin được **resolve vào một layer**, host có thể tìm provider bằng `ServiceLoader.load(layer, GreetingPlugin.class)`.

Khi nạp module runtime, các lớp API phải được thiết kế để host và plugin cùng tham chiếu tới đúng module API. Một hướng triển khai là:

~~~java
// Đoạn mô tả phần lõi của plugin manager modular;
// giả định API đã nằm trong boot layer và module plugin tồn tại.
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
Configuration config = ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(),
                 Set.of("com.example.greeting.plugin"));
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

ServiceLoader.load(layer, GreetingPlugin.class)
        .forEach(plugin -> System.out.println(plugin.id()));
~~~

Đây là **đoạn minh họa tích hợp**, không phải chương trình độc lập: cần import `java.lang.module.ModuleFinder`, `java.lang.module.Configuration`, `java.util.Set`, `java.util.ServiceLoader`, `java.nio.file.Path`, có `GreetingPlugin` từ module API, và JAR plugin phải có module descriptor hợp lệ. Nếu triển khai module mới, host phải kiểm soát roots, dependencies, tên module trùng, split packages và vòng đời layer. Một layer mới cũng **không tự sửa nội dung** của boot layer đã tồn tại.

Chọn `ModuleLayer` khi bạn cần ngữ nghĩa JPMS cho plugin và chấp nhận độ phức tạp giải quyết module. Chọn `URLClassLoader` khi plugin xây trên classpath/SPI và mô hình class loader đáp ứng đủ yêu cầu. Hai lựa chọn đều cần một **plugin manager** để quản lý lifecycle; riêng JPMS không cung cấp đầy đủ cơ chế cài đặt, nâng cấp hay gỡ plugin.

## 7. Dependency, isolation và cập nhật phiên bản

**Phụ thuộc chia sẻ:** API/SPI chung như `GreetingPlugin` nên có phiên bản tương thích và được nạp thống nhất. Plugin implementation có thể phụ thuộc thư viện riêng. Với parent-first `URLClassLoader`, class đã tồn tại ở parent thường được dùng trước, nên một dependency của host có thể lấn át phiên bản mà plugin mong muốn.

**Isolation:** tạo một loader/layer cho từng plugin có thể giảm xung đột giữa các implementation, nhưng cần thiết kế cách chia sẻ API, thông điệp, tài nguyên và phụ thuộc. Cơ chế child-first tùy chỉnh không phải giải pháp mặc định: nó có thể phá vỡ chia sẻ API và khiến class bị định nghĩa trùng. Với JPMS, package visibility và readability giúp kiểm soát liên kết nhưng không loại bỏ nhu cầu quản lý dependency và service contract.

**Nạp lại:** thay file JAR trên đĩa không thay thế những class đã được định nghĩa trong loader hiện hữu. Thông thường cần dừng plugin cũ, ngắt đăng ký và đóng tài nguyên, tạo loader/layer mới rồi khởi tạo plugin mới. Class loader cũ chỉ có thể được thu gom khi không còn tham chiếu tới class, instance, thread, listener, cache, static state hoặc tài nguyên của nó. `URLClassLoader.close()` đóng tài nguyên mở của loader; **không có nghĩa unload class ngay lập tức**.

**An toàn:** class loader và JPMS giúp tổ chức mã và kiểm soát một số khả năng truy cập, **không tạo sandbox bảo mật cho mã plugin tùy ý**. Plugin chạy cùng tiến trình có thể thực hiện hành vi nguy hiểm với quyền của tiến trình nếu host cho nó thực thi. Với plugin không tin cậy, cân nhắc tiến trình/container riêng, hợp đồng giao tiếp giới hạn, kiểm soát quyền hệ điều hành, xác thực nguồn cung và tài nguyên.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `ClassNotFoundException` | JAR không nằm trên đường tìm của **đúng loader** hoặc sai package/tên class | In đường dẫn JAR, kiểm tra nội dung bằng `jar tf`, xác định loader đang gọi |
| `NoClassDefFoundError` | Tìm thấy class chính nhưng thiếu dependency lúc liên kết/khởi tạo | Kiểm tra dependency của plugin và phạm vi nhìn thấy của loader/module |
| `ClassCastException` với hai class cùng tên | Host và plugin nạp bản sao API bằng hai loader khác nhau | Để hợp đồng chung tại parent/module API dùng chung; không đóng gói chồng API |
| `ServiceConfigurationError` | Sai descriptor `META-INF/services`, sai tên provider, provider không hợp lệ hoặc lỗi khi khởi tạo | Kiểm tra descriptor trong JAR, constructor/provider và liên kết module |
| `IllegalAccessError` / `InaccessibleObjectException` | Vi phạm ranh giới truy cập, thiếu `exports`/`opens` hoặc dùng deep reflection trái phép | Chỉnh module descriptor hoặc thiết kế API rõ ràng; không mở toàn bộ module chỉ để che lỗi |
| Không có provider dù JAR nằm trong `plugins/` | Host chưa quét/nạp, chưa đăng ký; module chưa resolve; hoặc thiếu service metadata | Theo dõi lần lượt **discover → load → resolve → instantiate → register** |
| Lỗi sau khi thay JAR đang chạy | Vẫn dùng loader/class/instance cũ, hoặc còn file handle và tài nguyên | Thiết kế lifecycle stop/close, tạo loader mới và loại bỏ tham chiếu cũ |

Một cách chẩn đoán hữu ích là ghi log **đường dẫn JAR, tên plugin, phiên bản, tên module nếu có, class loader đã định nghĩa provider và trạng thái đăng ký**. Điều này thường làm rõ vấn đề nhanh hơn việc thêm JAR vào mọi đường dẫn một cách thử-và-sai.

## 9. Chọn mô hình nào?

| Tình huống | Lựa chọn khởi đầu |
|---|---|
| Các thư viện là dependency cố định của một ứng dụng Java truyền thống | Classpath, dùng Maven/Gradle quản lý dependency |
| Ứng dụng muốn khai báo module rõ ràng và kiểm soát package public/reflective access | Module path và JPMS |
| Cần phân phối plugin độc lập, ứng dụng phát hiện khi khởi động hoặc đang chạy | Thư mục plugin + plugin manager + class loader/layer phù hợp |
| Plugin cần nạp/gỡ phiên bản mới mà không khởi động lại host | Plugin manager có lifecycle rõ ràng và loader/layer mới; kiểm soát tham chiếu/tài nguyên |
| Plugin đến từ bên thứ ba không đáng tin cậy | Tách tiến trình và quyền thực thi trước khi xét classpath hay JPMS |

Bạn cũng có thể **kết hợp** các cơ chế: host và SPI chạy trên classpath, JAR plugin nằm trong `plugins/` rồi được host nạp qua `URLClassLoader`; hoặc host modular trên module path, plugin manager tạo `ModuleLayer` riêng cho modular plugin. Câu hỏi thiết kế chính không phải “JAR nằm trong thư mục nào?”, mà là **ai phát hiện nó, loader/layer nào định nghĩa lớp, API nào được chia sẻ và ai quản lý vòng đời?**

## 10. Tự kiểm tra kiến thức

1. **Chép `weather.jar` vào `plugins/` rồi chạy lại `java -cp app.jar com.example.Main` có đủ để plugin hoạt động không?** Không. Host phải có logic quét thư mục, nạp JAR, tìm provider và đăng ký nó; hoặc phải cấu hình rõ ràng một cách nạp khác.
2. **Đưa một JAR lên `--module-path` có đảm bảo module của nó đã được resolve?** Không. Module graph phụ thuộc các root, quan hệ `requires`, service binding và tùy chọn khởi chạy như `--add-modules`.
3. **Có thể dùng `ServiceLoader` với classpath không?** Có. Khai báo provider qua `META-INF/services`, rồi sử dụng đúng class loader. Với named module, dùng `uses` và `provides` theo JPMS.
4. **Dùng một class loader cho nhiều JAR plugin có tương đương mỗi plugin được cô lập không?** Không. Chúng chia sẻ không gian định nghĩa class của loader đó; có thể đụng dependency và phiên bản.
5. **Gọi `close()` trên `URLClassLoader` có làm mọi class plugin biến mất ngay không?** Không. Loader và class chỉ có thể được thu gom khi không còn tham chiếu thích hợp; thread, instance hoặc cache còn giữ chúng sẽ ngăn điều đó.

**Ghi nhớ:** **classpath** là con đường tìm lớp/tài nguyên; **module path** là đầu vào cho cơ chế resolve và encapsulation của JPMS; **thư mục plugin** là vị trí triển khai mà ứng dụng chủ động biến thành thành phần chạy thông qua loader/layer, SPI và lifecycle.
