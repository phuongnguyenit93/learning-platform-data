# Đóng gói runtime bằng jlink với module công cụ và service binding cần thiết

Một ứng dụng Java có thể chạy ổn trong môi trường phát triển vì máy cài **đầy đủ JDK**, nhưng thất bại khi triển khai bằng một **custom runtime image** tạo từ `jlink`. Những triệu chứng thường gặp gồm: `ToolProvider.getSystemJavaCompiler()` trả `null`, không có JShell hoặc một công cụ cần thiết, `ServiceLoader` không tìm được provider, hoặc module phụ thuộc biến mất khỏi ảnh runtime. Nguyên nhân không nhất thiết do code sai: **ảnh được liên kết chỉ chứa các module đã được chọn và các phụ thuộc/provider được resolver đưa vào lúc tạo ảnh**.

Bài này hướng dẫn cách **chọn module gốc, giữ đúng các module công cụ (`jdk.compiler`, `jdk.jshell` và module liên quan), dùng `--bind-services` để liên kết provider cần thiết, kiểm chứng bằng chương trình Java 17 có thể chạy**, rồi kiểm soát dung lượng và tính tương thích khi triển khai.

**Thông điệp cốt lõi:** `jlink` là bước **đóng gói module graph thành một Java runtime image riêng**, không phải một lệnh “copy nguyên JDK”. `requires` mô tả dependency, `uses`/`provides` mô tả dịch vụ; **module chứa implementation hoặc service provider có thể không thuộc graph nếu không được root hoặc service binding lựa chọn**.

## 1. Runtime image, JDK, JRE và jlink khác nhau ở đâu?

| Khái niệm | Ý nghĩa |
|---|---|
| **JDK đầy đủ** | Bộ phát triển gồm JVM, standard modules, công cụ như `javac`, `jar`, `jlink`, `jdeps`, `jshell` tùy bản phân phối |
| **Custom runtime image** | Thư mục gồm `bin/java`, thư viện JVM, module image và những thành phần linker chọn; được tạo bằng `jlink` |
| **`java.base`** | Module nền tảng luôn cần cho runtime Java |
| **Application module** | Module do dự án định nghĩa trong `module-info.java`, ví dụ `demo.host` |
| **Tool module** | Module chứa API/implementation liên quan công cụ, ví dụ `jdk.compiler` hoặc `jdk.jshell` |
| **Service provider module** | Module khai báo `provides Service with Implementation` và được ứng dụng tìm bằng `ServiceLoader` |
| **Module path** | Tập `.jmod`, modular JAR hoặc dạng module phù hợp mà `jlink` dùng để tìm module lúc liên kết |
| **Service binding** | Quá trình bổ sung các provider module của dịch vụ được `uses` bởi những module trong graph, cùng các dependency tương ứng |

Trong quá trình build:

```text
JDK jmods + modular application JARs
                   |
                   v
     --module-path + --add-modules
                   |
           resolve requires
                   |
        (tùy chọn --bind-services)
                   |
      tìm provider qua uses/provides
                   |
          graph đã được resolve
                   |
                   v
                 jlink
                   |
                   v
       Custom runtime image/
         bin/java, lib/modules,...
                   |
                   v
       Chạy java -m module/main
                   |
            Self-test + smoke test
```

`jlink` có mặt trong JDK hiện đại; thông thường nó liên kết **JDK modules và modular application modules**, không chấp nhận dùng một JAR chỉ có automatic module name như thể đó là một explicit module hoàn chỉnh. Nếu một thư viện ngoài chỉ là automatic module hoặc một JAR classpath, phải quyết định đóng gói lại/đưa ra runtime classpath/module path bên ngoài, chứ không mặc nhiên coi nó là đầu vào link hợp lệ.

Một runtime image tạo với JDK 24 mang runtime **JDK 24**, dù source ứng dụng được biên dịch bằng `javac --release 17`. `--release 17` điều chỉnh mức ngôn ngữ/API/bytecode của class; nó **không biến jlink của JDK 24 thành trình tạo JDK 17 runtime**. Muốn image chạy Java 17, hãy build bằng **toolchain JDK 17 phù hợp với nền tảng đích**.

## 2. Cách jlink xác định tập module sẽ nằm trong image

Một lệnh đơn giản:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host \
      --output image
```

Lệnh dùng cú pháp shell Linux/macOS. `mlib` là thư mục chứa modular JAR của ứng dụng; trên Windows, dấu phân tách module path là **chấm phẩy**. `demo.host` là module gốc; `jlink` xét các `requires` trong descriptor để đưa vào các module cần thiết. `java.base` được đưa vào theo cơ chế module system.

**Điểm khác nhau giữa các quan hệ:**

- `requires some.module;`: đây là **phụ thuộc có tên** mà module system cần giải quyết để xây graph.
- `uses com.example.Service;`: module nói rằng nó **sử dụng một service**; điều đó không có nghĩa mọi provider của service tự động được đưa vào image ở chế độ link mặc định.
- `provides com.example.Service with com.example.Impl;`: một module **cung cấp provider**, nhưng phải có lý do để module provider này được đưa vào graph: là root, là dependency được chọn hoặc được thêm nhờ service binding.
- `--bind-services`: yêu cầu linker liên kết các service provider module cùng phụ thuộc của chúng theo cấu hình/module path, có thể làm graph và dung lượng image **lớn hơn đáng kể**.

### 2.1. Root module phải phản ánh runtime cần chạy

Ví dụ một ứng dụng gồm:

```text
demo.host
  requires demo.spi
  requires java.compiler
  uses demo.spi.GreetingService

demo.provider
  requires demo.spi
  provides demo.spi.GreetingService with demo.provider.HelloProvider
```

Nếu chỉ root `demo.host`, module `demo.spi` và `java.compiler` có thể được kéo vào qua `requires`, nhưng `demo.provider` **không** tự đi vào chỉ vì có file JAR trên module path. Khi dùng `--bind-services`, linker có thể nhận ra `demo.host` dùng service `demo.spi.GreetingService`, tìm `demo.provider` và đưa nó vào image.

**Không nên bật tất cả module bằng `ALL-MODULE-PATH` một cách máy móc** để chữa lỗi thiếu provider: làm thế làm mất mục tiêu tối giản và có thể đưa mã không mong muốn vào image. Nên bắt đầu từ module gốc rõ ràng, kiểm tra dependency rồi bổ sung công cụ/provider có chủ đích.

## 3. Các module công cụ cần hiểu và chọn có chủ đích

| Module | Chức năng chính | Khi nào cần đưa vào image? |
|---|---|---|
| `java.base` | API Java nền tảng | Có mặt theo cơ chế module, không cần tự xử lý riêng |
| `java.compiler` | API chuẩn `javax.tools.JavaCompiler`, `ToolProvider`, `DiagnosticCollector` | Ứng dụng biên dịch động hoặc dùng compiler SPI/API; thường được kéo bởi `requires java.compiler` |
| **`jdk.compiler`** | Implementation `javac` của JDK, system compiler/provider và công cụ liên quan | Khi image cần **thật sự biên dịch Java** bằng `ToolProvider.getSystemJavaCompiler()` hoặc chạy `javac` |
| **`jdk.jshell`** | JShell API và công cụ REPL của JDK | Khi ứng dụng dùng `jdk.jshell.JShell` hoặc muốn phân phối tính năng JShell |
| `java.scripting` | API JSR 223 `javax.script` | Khi host dùng `ScriptEngine`/`Bindings`; **không** đồng nghĩa có JavaScript engine |
| `jdk.jdeps` | Công cụ phân tích module/dependency như `jdeps` | Nếu muốn dùng công cụ phân tích trong môi trường đó; thường chỉ cần ở pipeline build |
| `jdk.jlink` | Công cụ liên kết runtime image | Nếu cần chạy thao tác liên kết ở môi trường đó; thường chỉ cần trong build JDK |
| `jdk.jartool` | Công cụ thao tác JAR như `jar` | Thường chỉ cần ở build stage, không nhất thiết trong runtime image |
| `jdk.javadoc` | Công cụ sinh Javadoc | Thường chỉ cần ở build/docs stage |
| `jdk.zipfs` | FileSystemProvider cho ZIP/JAR qua NIO FileSystem API | Cần khi code dùng `FileSystems.newFileSystem` cho ZIP hoặc một dependency yêu cầu provider đó |

**Phân biệt API với implementation:**

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Compiler implementation is missing");
}
```

Đây là đoạn minh họa **trong một method**, không phải chương trình độc lập. Nó có thể biên dịch vì module chứa API `java.compiler` hiện diện, nhưng `compiler` vẫn có thể `null` nếu image không có một implementation phù hợp, điển hình là khi thiếu `jdk.compiler`. Vì thế **chỉ có `java.compiler` chưa đủ** cho yêu cầu biên dịch mã Java trong runtime.

**Một điểm về JShell:** Không phải cứ có `java.compiler` là đã có `jdk.jshell`. Nếu ứng dụng dùng `JShell` theo kiểu tĩnh, descriptor của host cần `requires jdk.jshell;` để module system kéo dependency vào. Nếu host quyết định sử dụng JShell bằng cấu hình/reflection hoặc cần phân phối công cụ JShell, hãy thêm `jdk.jshell` tường minh và kiểm thử trên image thật. Khi chạy example dưới đây, `jdk.jshell` được đưa vào như root tùy chọn và kiểm chứng bằng `ModuleLayer.boot().findModule(...)`.

Các bản JDK/image có thể cung cấp **launcher** tương ứng cho tool module (ví dụ `bin/javac`, `bin/jshell`); cần kiểm tra file thực tế trong `bin` của image được tạo, không chỉ suy đoán từ tên module. Trên JDK 24 kiểm thử, đưa `jdk.compiler` và `jdk.jshell` vào image cũng tạo các launcher tương ứng. Không nên mang build tools vào production image nếu môi trường thực thi không cần chúng.

### 3.1. java.scripting không mang kèm JavaScript engine

`ScriptEngineManager` thuộc `java.scripting` nhưng **Nashorn JavaScript engine đã bị gỡ khỏi JDK từ Java 15**. Vì thế thêm `java.scripting` vào image Java 17+ chỉ bảo đảm có API JSR 223; `getEngineByName("JavaScript")` vẫn có thể trả `null`. Engine ngoài JDK cần được chọn, đóng gói và cấu hình quyền host access riêng.

Tương tự, một service provider được cài bằng module bên ngoài **không tự xuất hiện** vì Java API `ServiceLoader` có sẵn trong `java.base`. Cần provider đúng và visibility phù hợp.

## 4. jlink và service binding: dùng --bind-services có ý nghĩa gì?

Cơ chế provider theo JPMS sử dụng ba thành phần:

```java
// module-info.java ở module sử dụng dịch vụ
uses demo.spi.GreetingService;

// module-info.java ở module cung cấp dịch vụ
provides demo.spi.GreetingService
        with demo.provider.HelloProvider;
```

Đây là hai **mệnh đề descriptor minh họa**, không thể đặt trực tiếp trong thân class Java. Trong chương trình thực tế, mỗi mệnh đề thuộc `module-info.java` của module tương ứng.

Một ứng dụng có thể dùng:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.message());
}
```

Đây là đoạn minh họa trong class đã import `java.util.ServiceLoader` và `demo.spi.GreetingService`. Với module đã được link vào boot layer, loader tìm provider theo quan hệ module và service visibility tương ứng.

**Không có `--bind-services`:** link mặc định dựa vào roots và dependencies. Module chỉ đóng vai trò provider nhưng không được root/dependency có thể **không nằm trong image**, nên `ServiceLoader` không tìm được provider ấy.

**Có `--bind-services`:** `jlink` bổ sung service provider modules và dependency cần thiết từ module path, tùy graph/module visibility. Điều này hữu ích cho các provider của ứng dụng và cả provider chuẩn JDK (ví dụ provider cho công cụ, xử lý locale/crypto/encoding tùy hệ thống). Cũng vì vậy, nó **không có nghĩa “chỉ bind đúng provider tôi đang nghĩ tới”**: image có thể chứa **nhiều module hơn dự kiến**.

### 4.1. Khi nào nên bật service binding?

Bật khi:

- Host sử dụng `ServiceLoader` để phát hiện plugin/provider mà module provider chưa là dependency tĩnh/root.
- Ảnh JDK tùy biến cần service provider của JDK cho tác vụ cụ thể.
- Bạn đã kiểm soát module path, danh tính provider và kết quả graph, đồng thời chấp nhận kích thước image tăng.

Không nên bật bừa:

- Khi module path còn chứa provider thử nghiệm, provider không tin cậy hoặc không muốn phát hành.
- Khi yêu cầu runtime image tối giản cực kỳ chặt và provider chỉ cần một vài implementation cố định.
- Khi kiến trúc chủ ý **nạp plugin ngoài image lúc runtime**: `--bind-services` chạy **lúc build image**, không thay cho cơ chế nạp plugin/layer mới sau khi JVM đã chạy.

Có hai lựa chọn hợp lệ khi provider bắt buộc:

1. **Root provider rõ ràng** trong `--add-modules` (dễ cố định tập module nhưng cần quản lý danh sách).
2. **Dùng `--bind-services`** để resolver tự bổ sung provider từ module path (linh hoạt nhưng phải audit output graph và phạm vi provider).

Dù chọn cách nào, **service binding không quyết định provider nào sẽ được ưu tiên khi nhiều implementation cùng khả dụng**. Ứng dụng phải định nghĩa policy chọn provider theo ID/version/priority/khả năng, không xem thứ tự `ServiceLoader` là hợp đồng nghiệp vụ xuyên môi trường.

## 5. Ví dụ Java 17 chạy được: image có compiler và service provider

Ví dụ dựng ba **explicit modules** rồi tạo **hai image**:

- Image A: có `demo.host` và `jdk.compiler`, **không bật service binding**, không yêu cầu `jdk.jshell`.
- Image B: có `demo.host`, `jdk.compiler`, `jdk.jshell`, **bật `--bind-services`**.
- Cả hai dùng cùng ba modular JAR trên module path, gồm cả `demo.provider.jar`, để chứng minh: **có JAR ở module path không đồng nghĩa provider được link vào image**.
- Host dùng `ToolProvider.getSystemJavaCompiler()` và `ServiceLoader<GreetingService>`, rồi kiểm tra module hiện diện ở boot layer.

### 5.1. Cấu trúc mã nguồn

```text
project/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.host/
      module-info.java
      demo/host/Main.java
    demo.provider/
      module-info.java
      demo/provider/HelloProvider.java
```

Tệp `src/demo.spi/module-info.java`:

```java
module demo.spi {
    exports demo.spi;
}
```

Tệp `src/demo.spi/demo/spi/GreetingService.java`:

```java
package demo.spi;

public interface GreetingService {
    String message();
}
```

Tệp `src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.spi;
    requires java.compiler;
    uses demo.spi.GreetingService;
}
```

Tệp `src/demo.host/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.GreetingService;
import java.util.ServiceLoader;
import javax.tools.ToolProvider;

public final class Main {
    public static void main(String[] args) {
        String message = ServiceLoader.load(GreetingService.class)
                .findFirst()
                .map(GreetingService::message)
                .orElse("none");

        System.out.println("service=" + message);
        System.out.println("compiler="
                + (ToolProvider.getSystemJavaCompiler() != null));
        System.out.println("jdk.compiler="
                + ModuleLayer.boot()
                    .findModule("jdk.compiler").isPresent());
        System.out.println("jdk.jshell="
                + ModuleLayer.boot()
                    .findModule("jdk.jshell").isPresent());
    }
}
```

Tệp `src/demo.provider/module-info.java`:

```java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
            with demo.provider.HelloProvider;
}
```

Tệp `src/demo.provider/demo/provider/HelloProvider.java`:

```java
package demo.provider;

import demo.spi.GreetingService;

public final class HelloProvider implements GreetingService {
    @Override
    public String message() {
        return "hello-provider";
    }
}
```

**Vì sao tách ba module?** `demo.spi` giữ contract chung, `demo.host` là consumer và `demo.provider` là implementation không có `requires` ngược từ host. Nếu host khai báo `requires demo.provider;`, ví dụ sẽ không còn kiểm chứng đúng ý nghĩa của service binding.

`ServiceLoader.load(GreetingService.class).findFirst()` ở đây chỉ dùng để in **một provider duy nhất của demo**. Trong ứng dụng có nhiều provider, không chọn bằng `findFirst()` nếu chưa có chính sách thứ tự.

### 5.2. Biên dịch thành các explicit modules

Từ thư mục `project`, trên JDK 17 trở lên:

```bash
javac --release 17 --module-source-path src -d out \
      -m demo.host,demo.provider
```

Đây là lệnh Linux/macOS; trên PowerShell có thể viết **một dòng**:

```powershell
javac --release 17 --module-source-path src -d out -m demo.host,demo.provider
```

`javac` biên dịch `demo.spi` là module phụ thuộc, nên thư mục `out` chứa cả ba module.

Đóng gói thành modular JAR (lệnh `jar` chạy từng dòng trên mọi hệ điều hành):

```bash
mkdir -p mlib
jar --create --file mlib/demo.spi.jar -C out/demo.spi .
jar --create --file mlib/demo.host.jar -C out/demo.host .
jar --create --file mlib/demo.provider.jar -C out/demo.provider .
```

Trên Windows PowerShell, tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force mlib | Out-Null
```

Sau đó dùng ba lệnh `jar --create ...` phía trên. Bước này rất quan trọng: `jlink` làm việc với **explicit module descriptors** trong các modular JAR. Không dựa vào JAR không có `module-info.class` chỉ được suy ra automatic module để mong linker hoạt động.

### 5.3. Tạo hai image trên Linux/macOS

Với `JAVA_HOME` trỏ đến thư mục **JDK đầy đủ** chứa `jmods`:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler \
      --output img-min \
      --strip-debug --no-header-files --no-man-pages

jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler,jdk.jshell \
      --bind-services \
      --output img-bound \
      --strip-debug --no-header-files --no-man-pages

./img-min/bin/java -m demo.host/demo.host.Main
./img-bound/bin/java -m demo.host/demo.host.Main
```

### 5.4. Tạo hai image trên Windows PowerShell

Thư mục `jmods` nằm trong JDK, các modular JAR ở `mlib`. Khác với Unix, Windows dùng dấu **`;`** để phân tách module path:

```powershell
$modulePath = "$env:JAVA_HOME\jmods;mlib"

jlink --module-path $modulePath --add-modules demo.host,jdk.compiler --output img-min --strip-debug --no-header-files --no-man-pages

jlink --module-path $modulePath --add-modules demo.host,jdk.compiler,jdk.jshell --bind-services --output img-bound --strip-debug --no-header-files --no-man-pages

.\img-min\bin\java.exe -m demo.host/demo.host.Main
.\img-bound\bin\java.exe -m demo.host/demo.host.Main
```

**Yêu cầu chạy:** không phải chỉ chạy `java` từ PATH, mà phải dùng chính executable `bin/java` **nằm trong image**. Nếu không, bạn có thể vô tình kiểm thử bằng full JDK thay vì custom runtime và không phát hiện module đã bị bỏ.

### 5.5. Kết quả chính xác đã kiểm tra

Image A **không** có service binding:

```text
service=none
compiler=true
jdk.compiler=true
jdk.jshell=false
```

Image B **có** service binding và JShell module:

```text
service=hello-provider
compiler=true
jdk.compiler=true
jdk.jshell=true
```

Các kết quả được kiểm tra với JDK 24, trong đó Java source được biên dịch bằng `--release 17`. Cùng mã Java và cùng tính năng `jlink`/JPMS được hỗ trợ trên JDK 17+, nhưng tên/phiên bản các module nền tảng và chính sách các runtime khác cần được xác nhận theo toolchain thực tế.

**Phân tích kết quả:**

1. `service=none` của image A: `demo.provider.jar` hiện diện ở **module path lúc link**, nhưng `demo.provider` không được root hay kéo vào qua `requires`, nên **không tồn tại trong image A**.
2. `service=hello-provider` của image B: `--bind-services` đưa provider module vào graph vì consumer có `uses demo.spi.GreetingService;` và provider có `provides ... with ...;`.
3. `compiler=true` ở cả hai: `jdk.compiler` đã được chọn làm root tool module, nên `ToolProvider.getSystemJavaCompiler()` tìm được implementation.
4. `jdk.compiler=true`: kiểm tra runtime module presence, không chỉ việc Java source host có thể import `javax.tools`.
5. `jdk.jshell=false/true`: minh họa một **tool module không nằm trong dependency graph tĩnh của host** sẽ không tự xuất hiện trừ khi có lý do được đưa vào graph.

Có thể kiểm tra những module thực sự đóng trong image B:

```bash
./img-bound/bin/java --list-modules
```

Trên Windows:

```powershell
.\img-bound\bin\java.exe --list-modules
```

Trong danh sách đã kiểm tra có `demo.host`, `demo.spi`, `demo.provider`, `java.compiler`, `jdk.compiler` và `jdk.jshell`. Danh sách thực tế **còn nhiều module JDK khác** do dependencies và service binding; không nên mong đúng sáu module đó.

## 6. Kiểm tra công cụ trong image: module tồn tại chưa đủ

Khi cần compiler thực sự ở runtime (ví dụ biên dịch đoạn Java do người dùng nhập):

1. Dùng `bin/java --list-modules` để xác nhận `jdk.compiler` và `java.compiler` có trong image.
2. Gọi `ToolProvider.getSystemJavaCompiler()` **bằng Java chạy từ image**; phải khác `null`.
3. Thử biên dịch một lớp test nhỏ bằng `JavaCompiler` và `DiagnosticCollector` theo hợp đồng thật.
4. Kiểm tra đường output là writable và `--release` được compiler runtime hỗ trợ.
5. Nếu ứng dụng cần lệnh `javac`/`jshell` để chạy trực tiếp, kiểm tra các launcher trong `bin` và chạy smoke test.
6. Đối với JShell API, thử khởi tạo/đánh giá snippet trong môi trường đã cấu hình; chỉ thấy `jdk.jshell` trong `--list-modules` chưa bảo đảm process/remote execution/hệ điều hành phù hợp với mọi ứng dụng.

**Lưu ý về compiler:** `jdk.compiler` là implementation nằm trong image, nhưng một bản Java runtime bị bỏ module này có thể vẫn có API `java.compiler` và biên dịch source host thành công ở build stage. Cần test `ToolProvider` **trên image được phân phối**, không trên JDK developer.

**Lưu ý về JShell:** JShell thường cần runtime hỗ trợ thực thi snippet và cơ chế giao tiếp với execution engine; nếu sandbox/container hạn chế process hoặc network nội bộ, chức năng có thể thất bại dù module đã link. Không mở rộng quyền OS chỉ để “sửa JShell” mà không đánh giá threat model.

### 6.1. Tool module trong runtime khác tool ở build stage

Nếu mục đích duy nhất là **đóng gói app** trước khi phát hành, `jlink`, `jdeps`, `jar` hay `javadoc` nên ở **build environment**. Runtime image production không nhất thiết cần `jdk.jlink`, `jdk.jdeps`, `jdk.jartool` hoặc `jdk.javadoc`.

Nếu sản phẩm thật sự hỗ trợ biên dịch Java hoặc JShell tại runtime, mới đưa các implementation/module cần thiết vào ảnh và chấp nhận chi phí dung lượng/attack surface tương ứng. Chọn **theo tính năng**, không đưa tất cả công cụ vào “cho chắc”.

## 7. jdeps, --suggest-providers và cách kiểm soát graph

### 7.1. jdeps giúp tìm dependency tĩnh

Trong pipeline build có thể dùng `jdeps` để xem dependency của modular JAR:

```bash
jdeps --module-path mlib --print-module-deps --module demo.host
```

Đây là lệnh phân tích chạy bằng **JDK build**, với `mlib` chứa các modular JAR. Tập module được in phản ánh phân tích tĩnh; **không tự bao gồm mọi module được load qua reflection, ServiceLoader, script engine hoặc cấu hình động**. Nó là điểm khởi đầu tốt để chọn roots, không phải cơ chế chứng minh runtime image đã đầy đủ.

**Quy trình chọn tool modules sau jdeps:**

- Nếu code dùng `javax.tools.JavaCompiler`, xác nhận `java.compiler` trong dependency graph.
- Nếu cần compiler implementation lúc chạy, thêm `jdk.compiler` vào root hoặc bảo đảm nó được linker đưa vào, rồi kiểm tra `getSystemJavaCompiler()`.
- Nếu cần `jdk.jshell.JShell`, xác nhận module tương ứng được thêm vào image.
- Nếu dùng `ServiceLoader`, kiểm tra `uses`/`provides` và chọn cách thêm provider: explicit roots hay `--bind-services`.
- Nếu các thư viện sử dụng JDK service provider khác qua reflection, thêm smoke test tương ứng (encoding, locale, TLS/crypto, filesystem provider, logging, management) theo đúng tính năng.

### 7.2. --suggest-providers để khảo sát provider

Một số bản `jlink` có tùy chọn `--suggest-providers` để gợi ý những module cung cấp một service trên module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --suggest-providers demo.spi.GreetingService
```

Trên Windows, thay dấu `:` trong module path bằng `;`. Đây là thao tác **khảo sát trong pipeline build**, không tạo image. `--suggest-providers` giúp phát hiện những provider có thể liên kết, nhưng **không thay cho validation/allowlist** về nhà cung cấp nào được phép triển khai. Luôn kiểm tra output thực tế của `--list-modules` sau khi link.

### 7.3. --launcher để tạo entry point tùy biến

Nếu muốn tạo launcher cho app, `jlink` có tùy chọn:

```text
--launcher tên=module[/mainClass]
```

Với module của demo:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler \
      --launcher greeting=demo.host/demo.host.Main \
      --output img-launcher
```

Sau đó, tùy OS, image có thể chạy bằng `img-launcher/bin/greeting` hoặc `img-launcher\bin\greeting.exe`. Lệnh `--launcher` **tạo điểm vào**, không tự thêm provider module chưa có trong graph: nếu cần provider hãy root hoặc dùng `--bind-services` như trên. Đừng nhầm application launcher do jlink tạo với các executable JDK tool như `javac` hoặc `jshell`.

## 8. --bind-services không phải cơ chế hot-plug plugin sau khi image được phát hành

Đây là ranh giới rất quan trọng trong module **runtime extensibility**.

**Service binding lúc build image:**

```text
Build time
  demo.host + demo.provider + JDK modules
      |
      | jlink --bind-services
      v
  Image chứa các modules đã link
      |
      | JVM khởi động từ image
      v
  ServiceLoader tìm provider thuộc module graph khả dụng
```

**Plugin được thêm sau khi JVM đã chạy:**

```text
Runtime
  image đang chạy, module graph đã được định nghĩa
      |
      | copy plugin-v2.jar vào thư mục
      v
  Module mới KHÔNG tự chui vào boot layer
      |
      | ModuleFinder + Configuration.resolve /
      | resolveAndBind + ModuleLayer.defineModules...
      v
  Layer mới + service loading theo layer/loader đó
```

`jlink` không theo dõi thư mục plugin. Việc thay/copy JAR sau khi đóng gói **không tái liên kết `lib/modules`** và cũng không tự động đưa provider vào boot layer. Với plugin không liên kết trong image, thiết kế runtime cần phân giải module mới thành `ModuleLayer` con phù hợp hoặc nạp qua cơ chế class loader/ServiceLoader cho classpath plugin theo đúng kiến trúc.

Chọn giữa hai cách:

- **Provider cố định, tin cậy, phát hành cùng sản phẩm**: link vào image; service binding hoặc explicit roots là cách hợp lý, dễ kiểm thử.
- **Provider được cài/cập nhật linh hoạt sau phát hành**: giữ module path/plugin artifacts ngoài image và có lifecycle manager để discover, resolve, load, validate, switch, close. Không dùng `--bind-services` như một lời hứa hot reload.

Cần chú ý: **một module trong image là thành phần runtime đã liên kết**, không phải một JAR rời có thể thay trực tiếp theo tên file. Việc “xóa/chỉnh” module từ image sau link không phải quy trình cập nhật plugin.

## 9. Đóng gói cho đúng hệ điều hành và đúng phiên bản Java

`jlink` tạo image gắn với **JDK và nền tảng target**: hệ điều hành, kiến trúc, native libraries và launchers. Đừng build image Windows rồi sao chép nguyên sang Linux và mong chạy được.

| Vấn đề | Quy tắc |
|---|---|
| JDK dùng để link | Cố định vendor, feature version và bản cập nhật trong CI |
| JDK 17 vs JDK 24 | Dùng **JDK 17 jlink** để tạo Java 17 runtime, **JDK 24 jlink** để tạo Java 24 runtime |
| `javac --release 17` | Đặt mức class/source/API, **không** quyết định version của runtime image |
| OS/CPU | Build bằng JDK toolchain cho target hoặc pipeline cross-target đã kiểm chứng |
| Đường phân tách module path | Linux/macOS: `:`; Windows: `;` |
| Input module | Ưu tiên explicit modular JAR có `module-info.class`; không tự giả định automatic JAR link được |
| Artifact integrity | Pin và xác minh JDK/toolchain, module JAR và dependency; lưu hash/checksum |
| Native dependencies | Cần test `java.library.path`, JNI, TLS/SSL, DNS, timezone, locale nếu ứng dụng dùng |
| Production deployment | Mang **nguyên image directory** và app resources phù hợp; dùng `image/bin/java` |
| Runtime flags | Tương thích module graph và JDK đích; `--add-modules` lúc chạy không thể làm xuất hiện một module chưa được link |

**Image nhỏ không đồng nghĩa image đúng.** Quy trình QA phải chạy trên image vừa build và kiểm tra mọi tính năng runtime cần thiết, không chỉ `java -version`.

### 9.1. Về module tool có khả năng phát triển/biên dịch runtime

Trước khi bỏ `jdk.compiler` để giảm dung lượng, phải kiểm tra đường chạy thật: ứng dụng có dùng `ToolProvider`, annotation processing, thư viện biên dịch biểu thức/DSL ra Java source, thư viện quản lý script hoặc test runtime nào không? Một số chức năng chỉ kích hoạt ở các cấu hình hiếm và không xuất hiện trong smoke test chính.

Với module công cụ, nên giữ một bảng đặc tả:

```text
feature: runtime-compile
requires: java.compiler (API), jdk.compiler (implementation)
probe: ToolProvider.getSystemJavaCompiler() != null

feature: interactive-java
requires: jdk.jshell + dependencies
probe: JShell creation and snippet evaluation

feature: provider-discovery
requires: service interfaces + selected provider modules
probe: ServiceLoader returns expected provider ID
```

Những dòng trên là **manifest ý tưởng**, không phải file cấu hình do `jlink` tự đọc. Manifest giúp giữ mối liên hệ giữa tính năng, module và smoke test khi thay đổi tập roots.

## 10. Dung lượng, attack surface và tính tái lập của image

`--strip-debug`, `--no-header-files` và `--no-man-pages` thường giúp loại dữ liệu không cần thiết khi phân phối, nhưng **không thay được việc chọn đúng module graph**.

`--bind-services` có thể kéo nhiều provider modules. Một lựa chọn cân bằng:

1. Tạo image không bind, kiểm tra những dịch vụ đang thiếu.
2. Xác định dịch vụ nào cần và provider nào thực sự được phép/được triển khai.
3. Thử image dùng explicit provider roots, hoặc `--bind-services` với module path đã lọc.
4. So sánh `--list-modules`, kích thước image, thời gian khởi động, tính năng và rủi ro của mỗi phương án.
5. Chốt một policy rõ ràng: không đưa provider thử nghiệm, không thêm module không được kiểm soát vào CI module path.

Cần phân biệt **service binding để đóng gói** với **chọn provider để thực thi**. Nếu module path có hai implementation cùng service, chúng có thể đều được link khi bind. Vì vậy mỗi pipeline nên test provider inventory và hành vi lựa chọn ứng dụng sau khi build.

Một runtime image cần có bằng chứng provenance để tái dựng: phiên bản JDK, options của `jlink`, module path, modules được liên kết, bản build của modular JAR, checksum và smoke test results. Đây cũng là cơ sở cho rollback và điều tra lỗi môi trường.

## 11. Những lỗi dễ gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ToolProvider.getSystemJavaCompiler() == null` | Image chỉ chứa `java.compiler` API, thiếu compiler implementation | Root/link `jdk.compiler`, kiểm tra trên image |
| `ClassNotFoundException` khi gọi JShell | Thiếu `jdk.jshell` hoặc đường module visibility không đúng | Thêm/require module, kiểm tra layer và loader |
| `ServiceLoader` không thấy provider | Provider JAR chỉ nằm trên build module path, chưa được link | Bật `--bind-services` hoặc explicit root provider |
| `ServiceConfigurationError` | Descriptor/provider constructor/access/dependency sai | Kiểm tra `module-info.java`, provider implementation và module graph |
| Có hai provider nhưng chỉ muốn một | `--bind-services` đã thêm nhiều provider | Kiểm soát module path, explicit roots hoặc selector nghiệp vụ |
| `jlink` báo automatic module | JAR không có explicit module descriptor | Chuyển thành modular JAR hoặc giữ ở classpath ngoài image theo thiết kế |
| Image link được nhưng plugin sau deploy không thấy | Nhầm build-time binding với runtime hot-plug | Tạo runtime loader/layer và discovery riêng |
| Java trên máy dev chạy nhưng image không | Đã dùng `java` từ full JDK hoặc thiếu module/provider | Gọi `image/bin/java` và `--list-modules` |
| Bản build tạo image sai version | Dùng JDK khác kỳ vọng; hiểu nhầm `--release` | Cố định JDK tạo image, kiểm tra `image/bin/java -version` |
| `bin/jshell` không chạy dù module có | Cấu hình runtime/launchers/OS hoặc dependency không phù hợp | Test executable và JShell API trên image thật |
| Script JavaScript engine trả `null` | Nhầm `java.scripting` với implementation JavaScript engine | Đóng gói engine ngoài JDK, kiểm tra JSR 223 provider |
| Lỗi TLS/locale/ZIP trên image nhỏ | Service/native provider chưa có hoặc module bị bỏ | Kiểm tra tính năng, root/bind provider cần thiết |
| Biên dịch động không ghi class file | Folder output read-only hoặc quyền process hạn chế | Chọn output dir tách biệt, quyền tối thiểu, log diagnostics |
| Image chạy khác OS | Native binaries của OS/arch build không tương thích | Build image cho target hoặc dùng pipeline target-specific |

### 11.1. Trình tự chẩn đoán có ít thao tác nhất

```text
1. Xác nhận image/bin/java -version
2. image/bin/java --list-modules
3. Kiểm tra modules jdk.compiler/jdk.jshell/provider
4. Gọi compiler probe / JShell probe / ServiceLoader probe
5. Đối chiếu root modules, module path và --bind-services
6. Kiểm tra artifact modular JAR và module-info.java
7. Chạy test trong cùng OS/container/runtime flags production
```

Nếu thiếu provider, đừng “chữa cháy” bằng việc thêm `--add-modules ALL-MODULE-PATH` vào production mà không review. Hãy xác định **dịch vụ và module bị thiếu** rồi sửa graph một cách có chủ đích.

## 12. Kiểm thử và triển khai custom runtime image

Bộ test nên bao gồm **khả năng khởi động** và **tính năng động** của ứng dụng:

| Trường hợp | Bằng chứng cần có |
|---|---|
| Build application modules | `javac --release 17` thành công với explicit `module-info.java` |
| JAR modular hợp lệ | `jar --describe-module --file mlib/demo.host.jar` đọc được descriptor |
| Image không bind services | `service=none` trong ví dụ, chứng minh provider không tự vào graph |
| Image có binding | `service=hello-provider` và `demo.provider` hiện diện |
| Compiler implementation | `getSystemJavaCompiler()!=null` trong image |
| JShell module | `jdk.jshell` có trong `--list-modules` và API hoạt động nếu ứng dụng cần |
| Module path theo OS | Separator chính xác, JDK `jmods` đúng bản build |
| Không có provider bị cài nhầm | Kiểm tra toàn bộ `--list-modules` và nguồn artifact |
| Runtime không có full JDK trên máy | App chạy chỉ với image và tài nguyên đã phát hành |
| Feature runtime compile | Biên dịch source ngắn, thu diagnostic và xác minh class output |
| Feature plugin động | Thêm provider ngoài image qua loader/layer đúng, không giả định build-time binding |
| Kiểm thử âm tính | Bỏ module/provider cần thiết phải có lỗi dễ chẩn đoán |
| Đóng gói đa OS | Chạy trong CI runner/container/VM của từng target |
| Bản vá JDK | Tạo lại image từ JDK cập nhật, không chỉ thay tệp `java` trong image |
| Rollback deployment | Có thể khôi phục nguyên image và app artifact tương thích |

**Điểm kiểm tra quan trọng:** một image được link và `java -version` thành công mới chứng minh JVM khởi động. Nó **chưa** chứng minh provider, compiler, JShell hay dynamic plugin manager hoạt động. Các phép thử theo tính năng là tiêu chí nghiệm thu.

## 13. Checklist để đưa jlink vào pipeline CI/CD

1. **Toolchain cố định:** dùng JDK có `jmods` đúng vendor/feature/update và nền tảng target.
2. **Phân tích module:** kiểm kê `requires`, `uses`, `provides`, reflection và service providers; dùng `jdeps` như nguồn gợi ý, không xem là danh sách hoàn chỉnh của dynamic loading.
3. **Modular artifacts:** biên dịch/package các module dự án có descriptor hợp lệ, kiểm tra version và supply chain.
4. **Root có chủ đích:** chọn module host và các tool modules thật sự cần ở runtime: `jdk.compiler` cho compiler, `jdk.jshell` cho JShell, các module khác theo từng tính năng.
5. **Service binding:** quyết định bật `--bind-services` hay root provider rõ ràng; kiểm soát module path và inventory provider được link.
6. **Đóng image:** dùng `jlink --module-path ... --add-modules ... --output ...` với tùy chọn kích thước khi phù hợp.
7. **Xác minh:** chạy `image/bin/java --list-modules`, compiler probe, ServiceLoader provider probe, JShell probe nếu cần.
8. **Kiểm tra isolation:** nếu hỗ trợ chạy script/mã người dùng không tin cậy, `jlink` không phải sandbox. Cần quyền OS/container, giới hạn CPU/RAM/network/filesystem và capability gateway.
9. **Triển khai:** phân phối nguyên image, chạy executable bên trong image, không dựa vào full JDK có sẵn trên server.
10. **Bảo trì:** cập nhật JDK bằng việc **build lại image**, chạy hồi quy và lưu thông tin provenance; kiểm tra tác động của `--bind-services` lên danh sách module qua từng bản build.

### Tài liệu Java chính thức

- [jlink tool — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html)
- [Java Platform Module System — JLS/Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [ModuleDescriptor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [JShell — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html)

**Kết luận:** tạo custom runtime bằng `jlink` không chỉ chọn `java.base` và module ứng dụng. Với tính năng biên dịch động cần bảo đảm **`jdk.compiler`**, với JShell cần **`jdk.jshell`**, và với kiến trúc service-based phải chọn cách đưa **provider modules** vào image bằng root tường minh hoặc **`--bind-services`**. Kiểm thử bằng chính `image/bin/java`, đối chiếu `--list-modules` và smoke test thực tế giúp image vừa gọn, vừa có đủ chức năng, vừa tránh nhầm lẫn giữa **đóng gói provider lúc build** và **nạp plugin mới lúc runtime**.