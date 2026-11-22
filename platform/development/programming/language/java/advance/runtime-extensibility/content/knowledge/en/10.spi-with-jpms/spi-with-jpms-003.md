# Khai báo requires, exports và uses phía sử dụng dịch vụ trong JPMS

## 1. Bài toán: module tiêu thụ SPI cần khai báo những gì?

Java Platform Module System (JPMS) cho phép một ứng dụng khám phá các implementation của một Service Provider Interface (SPI) mà không cần import trực tiếp class implementation. Một service thường là interface hoặc abstract class; module khác công bố provider thông qua `provides ... with ...`, còn module sử dụng tìm provider bằng `java.util.ServiceLoader`.

Khi viết một **explicit named module** làm consumer, có ba directive dễ bị nhầm:

- **`requires tên.module;`**: module consumer *đọc được* module chứa kiểu service hoặc dependency khác.
- **`exports tên.package;`**: module *sở hữu package* cho phép module khác truy cập các kiểu `public` của package đó. Nếu SPI ở một module riêng, chính **module SPI** export package interface; consumer chỉ export package của mình khi công khai API cho module khác.
- **`uses tên.package.Service;`**: module consumer khai báo nó sẽ *tìm provider của service* qua `ServiceLoader`.

Ba directive này làm ba việc khác nhau. `requires` không đăng ký một service consumer, `uses` không làm module API tự động readable, còn `exports` không tự tìm hoặc khởi tạo bất kỳ provider nào.

Ở phía provider, khai báo tương ứng là:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.HelloGreeting;
}
~~~

Consumer **thường không cần** `requires demo.provider;`. Đây là yếu tố quan trọng giúp đổi hoặc bổ sung implementation mà không buộc mã consumer phụ thuộc module triển khai cụ thể.

## 2. Ai sở hữu directive nào?

Giả sử có bốn module:

| Module | Trách nhiệm | Directive chủ yếu |
|---|---|---|
| `demo.spi` | Định nghĩa hợp đồng `GreetingService` | `exports demo.spi;` |
| `demo.host` | Consumer trực tiếp gọi `ServiceLoader`; đồng thời cung cấp API cho app | `requires demo.spi;`, `uses demo.spi.GreetingService;` và `exports demo.host.api;` |
| `demo.provider` | Định nghĩa implementation và đăng ký provider | `requires demo.spi;`, `provides ... with ...;` |
| `demo.app` | Module ứng dụng gọi API công khai của host | `requires demo.host;` |

Quan hệ khái niệm:

~~~text
demo.app
    |
    | requires
    v
demo.host ---requires----> demo.spi
    |                         |
    | uses                    | exports demo.spi
    +-- demo.spi.GreetingService
                              ^
                              |
demo.provider --requires------+
    |
    +-- provides demo.spi.GreetingService
                  with demo.provider.HelloGreeting
~~~

Các mũi tên `requires` là quan hệ **module readability**. Cặp `uses`/`provides` thể hiện **hợp đồng khám phá dịch vụ**, không tạo quan hệ import implementation từ host sang provider.

Cần xác định chính xác **module nào chứa lời gọi `ServiceLoader`**, không chỉ module nào chứa phương thức `main`. Nếu `demo.app` gọi `GreetingEngine.run()` nhưng code bên trong `GreetingEngine` ở `demo.host` mới gọi `ServiceLoader.load(...)`, thì `uses` thuộc `demo.host`.

## 3. `requires`: consumer đọc module chứa API

Descriptor ví dụ:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

`requires demo.spi;` xác lập dependency từ `demo.host` tới `demo.spi`. Khi module graph được resolve, consumer có thể đọc module SPI. Để import được `demo.spi.GreetingService`, còn cần package `demo.spi` được module sở hữu **export** cho consumer và interface có quyền truy cập phù hợp (ở đây là `public`).

**`requires` không giống `uses`.** Một module đọc được service interface vẫn chưa khai báo quyền sử dụng `ServiceLoader` cho interface đó. Ngược lại, directive `uses` không thay thế `requires` khi service nằm ở module khác và consumer cần truy cập type đó.

Đoạn mã sau chỉ minh họa chỗ sử dụng API, chưa phải chương trình độc lập:

~~~java
import demo.spi.GreetingService;

public final class ConsumerHelper {
    public static String describe(GreetingService provider) {
        return provider.id();
    }
}
~~~

Nếu module consumer không đọc được `demo.spi`, compiler không thể dùng `GreetingService` theo cách trên. Thêm JAR chứa interface vào module path **không tự bỏ qua** quy tắc readability.

### Không `requires` provider chỉ để tìm service

Trong thiết kế mở rộng, host nên phụ thuộc **hợp đồng API**. Viết:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

thay vì tự động thêm:

~~~java
module demo.host {
    requires demo.spi;
    requires demo.provider;
    uses demo.spi.GreetingService;
}
~~~

`requires demo.provider` chỉ hợp lý nếu host thực sự cần đọc module đó như một dependency trực tiếp. Việc đặt nó vào descriptor chỉ vì có provider có thể buộc host biết tên implementation, tạo coupling không cần thiết và gây khó khi thay plugin.

### `requires transitive`

Khi module host xuất một API mà chữ ký public của nó tham chiếu đến kiểu trong module SPI, host có thể muốn các client đọc được SPI thông qua host:

~~~java
module demo.host {
    requires transitive demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

Module khác có `requires demo.host;` khi ấy cũng đọc `demo.spi` theo quan hệ transitive. **Không cần** `requires transitive` cho mọi dependency: nếu public API của host chỉ trả `String` hoặc `void`, và không phơi bày kiểu SPI, `requires demo.spi` thường là lựa chọn gọn hơn.

`requires static` dành cho phụ thuộc bắt buộc lúc compile time nhưng có thể vắng ở runtime; không nên dùng nó để “tùy chọn hóa” module chứa service type mà ứng dụng chắc chắn cần khi thực thi.

## 4. `exports`: module sở hữu package mở public API

Giả sử service interface nằm ở `demo.spi/demo/spi/GreetingService.java`. Chỉ **module `demo.spi`** sở hữu package `demo.spi`, vì vậy nó mới có thể khai báo:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

Directive này cho phép module khác truy cập các kiểu `public` trong package `demo.spi` khi có readability thích hợp. Nó không biến class package-private thành public, không mở private fields cho deep reflection và không bảo đảm provider được nạp.

### Vì sao `exports` có thể xuất hiện ở module consumer?

Nếu consumer cũng công bố một API cho module ứng dụng:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

thì `exports demo.host.api;` là cách host cho phép `demo.app` import class `demo.host.api.GreetingEngine`. Điều này **khác** với export interface SPI. Consumer không thể tự export `demo.spi` nếu package đó thuộc một module khác.

Nếu `demo.host` chỉ là module chạy độc lập và không cung cấp API cho module ngoài, có thể bỏ `exports demo.host.api;` khi package không được module khác dùng. Việc service discovery trong chính host vẫn vận hành nếu `requires`/`uses` và cấu hình provider đều đúng.

### Qualified exports

Để chỉ cấp quyền cho một số named modules, module API có thể khai báo:

~~~java
module demo.spi {
    exports demo.spi to demo.host, demo.provider;
}
~~~

`exports ... to ...` chỉ mở truy cập public package cho các module được liệt kê. Nếu dự án có provider của bên thứ ba mà tên module chưa biết trước, export có giới hạn kiểu này có thể làm việc mở rộng khó hơn.

Phân biệt:

- `exports package;`: public API thông thường cho các module được phép đọc.
- `exports package to module1, module2;`: public API cho những module cụ thể.
- `opens package;` hoặc `opens ... to ...;`: phục vụ deep reflection theo quy tắc JPMS, không đồng nghĩa export.
- `provides Service with Implementation;`: thông báo provider cho `ServiceLoader`; **không yêu cầu export package implementation** chỉ vì consumer cần khám phá nó.

Với SPI, package implementation của provider thường nên được giữ nội bộ. Consumer giao tiếp qua interface được export từ module API, thay vì import thẳng implementation.

## 5. `uses`: đánh dấu module thực hiện service lookup

Trong descriptor của module có code gọi `ServiceLoader`:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

Tên sau `uses` là **tên kiểu service**, chẳng hạn `demo.spi.GreetingService`, **không** phải tên module `demo.spi` và cũng **không** phải class `demo.provider.HelloGreeting`.

Ví dụ API:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.id());
}
~~~

Đây là đoạn minh họa trong module consumer: cần import `demo.spi.GreetingService` và `java.util.ServiceLoader`. Việc tạo `ServiceLoader` chưa nhất thiết đã tìm hoặc khởi tạo provider; việc duyệt thực hiện phần đáng kể công việc theo cơ chế lazy.

Theo hợp đồng Java 17, khi code trong **explicit named module** gọi `ServiceLoader`, module chứa lời gọi phải khai báo `uses` cho service. Nếu bỏ `uses` khỏi `demo.host` trong khi code vẫn gọi `ServiceLoader.load(GreetingService.class)`, lời gọi có thể gây `ServiceConfigurationError` do module caller không khai báo tiêu thụ service. Trong trường hợp đó, thêm `requires` hoặc `exports` không thay thế được `uses`.

### `uses` có tạo provider không?

Không. Directive `uses` không chỉ định implementation, không cài plugin và không tạo instance. Module provider phải có descriptor `provides ... with ...` hoặc metadata tương ứng trong mô hình provider khác; module provider phải nằm trong phạm vi module graph/layer được resolve và đường lookup phù hợp. `ServiceLoader` thực hiện discovery khi code chạy.

### Module có `main` luôn cần `uses`?

Không. `uses` thuộc module **trực tiếp sử dụng ServiceLoader cho service đó**. Nếu `demo.app` chỉ gọi `GreetingEngine.run()` thì nó không nhất thiết phải khai báo `uses`. Trong ví dụ đầy đủ sau, `demo.host` mới có lời gọi `ServiceLoader.load(...)` nên `uses` nằm trong `demo.host/module-info.java`.

## 6. Ví dụ Java 17+ hoàn chỉnh: bốn named modules

Ví dụ này làm rõ cả ba directive phía consumer và kiểm tra provider vẫn được khám phá mà host **không requires module implementation**. Mã nguồn có tám file.

### 6.1. Cấu trúc dự án

~~~text
jpms-spi-demo/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.host/
      module-info.java
      demo/host/api/GreetingEngine.java
    demo.provider/
      module-info.java
      demo/provider/HelloGreeting.java
    demo.app/
      module-info.java
      demo/app/Main.java
  mods/                   (tạo bằng javac)
~~~

### 6.2. Module SPI

**`src/demo.spi/module-info.java`**:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

**`src/demo.spi/demo/spi/GreetingService.java`**:

~~~java
package demo.spi;

public interface GreetingService {
    String id();
    String greet(String name);
}
~~~

Module API không cần biết consumer hoặc provider nào sẽ sử dụng. Vì API này dùng public interface cho các module khác, package của interface cần được export.

### 6.3. Module consumer/host

**`src/demo.host/module-info.java`**:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

Đây là ví dụ có **cả ba directive trong module consumer**: `requires` để đọc SPI, `uses` để được tìm provider, `exports` để cho module `demo.app` dùng API host.

**`src/demo.host/demo/host/api/GreetingEngine.java`**:

~~~java
package demo.host.api;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class GreetingEngine {
    private GreetingEngine() {}

    public static void run() {
        for (GreetingService service :
                ServiceLoader.load(GreetingService.class)) {
            System.out.println(
                    service.id() + " -> " + service.greet("Java"));
        }
    }
}
~~~

`GreetingEngine.run()` tìm provider của `GreetingService` bằng `ServiceLoader`. Trong trường hợp chạy ví dụ, nó có một implementation. Host phụ thuộc SPI, nhưng không import `demo.provider.HelloGreeting` và không `requires demo.provider`.

### 6.4. Module provider

**`src/demo.provider/module-info.java`**:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.HelloGreeting;
}
~~~

**`src/demo.provider/demo/provider/HelloGreeting.java`**:

~~~java
package demo.provider;

import demo.spi.GreetingService;

public final class HelloGreeting implements GreetingService {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

Module provider **cũng** cần đọc module SPI để implement interface. Nhưng nó không export package `demo.provider`: thông tin `provides ... with ...` đủ để JPMS/`ServiceLoader` nhận diện provider nếu module được resolve. Ví dụ dùng class public có constructor mặc định public, đáp ứng cách khởi tạo provider thông thường.

### 6.5. Module ứng dụng

**`src/demo.app/module-info.java`**:

~~~java
module demo.app {
    requires demo.host;
}
~~~

**`src/demo.app/demo/app/Main.java`**:

~~~java
package demo.app;

import demo.host.api.GreetingEngine;

public final class Main {
    public static void main(String[] args) {
        GreetingEngine.run();
    }
}
~~~

Ứng dụng dùng API công khai từ host, nên cần `requires demo.host;` và host cần `exports demo.host.api;`. Ứng dụng không gọi `ServiceLoader` trực tiếp, vì thế không cần `uses demo.spi.GreetingService;` trong descriptor của `demo.app`. API `GreetingEngine.run()` cũng không buộc `demo.app` import `GreetingService`, nên `demo.app` không cần `requires demo.spi;` cho ví dụ này.

### 6.6. Biên dịch và chạy

Chạy trong thư mục `jpms-spi-demo/` bằng Bash (Linux/macOS hoặc Git Bash trên Windows):

~~~bash
mkdir -p mods

javac --release 17 \
  --module-source-path src \
  -d mods \
  $(find src -type f -name '*.java')

java --module-path mods \
  --add-modules demo.provider \
  --module demo.app/demo.app.Main
~~~

Giải thích:

- `--release 17` kiểm tra mã và API tương thích Java 17.
- `--module-source-path src` cho `javac` biết thư mục mã nguồn gồm các module con.
- `-d mods` tạo output theo module, ví dụ `mods/demo.host/module-info.class`.
- `--module-path mods` cung cấp đường tìm named modules khi chạy.
- `--add-modules demo.provider` thêm provider làm root để bảo đảm module triển khai **được resolve** cho ví dụ; chỉ đặt module trên module path chưa đủ để kết luận nó đã được resolve.
- `--module demo.app/demo.app.Main` chọn entry point trong named module `demo.app`.

Đầu ra của chương trình:

~~~text
hello -> Xin chao, Java!
~~~

Đây là kết quả đã kiểm tra bằng cách biên dịch với `javac --release 17` và chạy trên OpenJDK 21. Có một provider nên thứ tự in không gây nhập nhằng. Chuỗi ví dụ dùng ASCII trong output cho tính nhất quán giữa các môi trường shell/terminal.

Trên Windows PowerShell, có thể tạo `mods` bằng `New-Item -ItemType Directory -Force mods`, rồi lập danh sách file `$sources = @(Get-ChildItem src -Recurse -Filter *.java | ForEach-Object FullName)` và gọi `javac --release 17 --module-source-path src -d mods $sources`. Lệnh `java --module-path mods --add-modules demo.provider --module demo.app/demo.app.Main` dùng được trong PowerShell.

### 6.7. Vì sao ví dụ cần đúng các directive?

- `demo.spi` export interface, nếu không host và provider không thể truy cập kiểu public của package theo JPMS.
- `demo.host` requires SPI, nếu không nó không đọc module chứa interface.
- `demo.host` uses service, nếu không việc gọi `ServiceLoader` trong explicit named module thiếu khai báo tiêu thụ service.
- `demo.host` exports API, nếu không `demo.app` không được import class `GreetingEngine` ở package đó.
- `demo.provider` provides implementation, nếu không `ServiceLoader` không có metadata đăng ký provider ở module này.
- `demo.app` requires host, vì ứng dụng cần truy cập module cung cấp `GreetingEngine`.

Tách các vai trò như vậy làm rõ sự khác nhau giữa **module API**, **module consumer**, **module provider** và **module entry point**.

## 7. Thử thay đổi từng directive để nhận diện lỗi

Hãy khôi phục bản chạy đúng trước khi thử tiếp thay đổi khác.

| Thử thay đổi | Kết quả cần hiểu |
|---|---|
| Xóa `requires demo.spi;` trong `demo.host` | Consumer không đọc được module chứa `GreetingService`; các tham chiếu/import tới service type sẽ lỗi khi biên dịch, nếu không có readability khác |
| Xóa `exports demo.spi;` trong `demo.spi` | Consumer/provider không được truy cập kiểu trong package SPI dù có `requires demo.spi;`; thường lỗi lúc biên dịch |
| Xóa `uses demo.spi.GreetingService;` trong `demo.host` | Consumer có thể vẫn biên dịch vì `requires` còn đó, nhưng lúc gọi `ServiceLoader` trong named module có thể ném `ServiceConfigurationError` |
| Xóa `exports demo.host.api;` trong `demo.host` | `demo.app` không được import public class `GreetingEngine` từ package không export; lỗi biên dịch |
| Xóa `provides ... with ...;` trong `demo.provider` | Module provider không còn đăng ký `HelloGreeting` cho service; nếu không có provider nào khác, không có implementation được khám phá |
| Bỏ `--add-modules demo.provider` lúc khởi chạy | Không được mặc định module provider đã resolve. Tùy launch/service binding, nó vẫn có thể được resolve bằng cơ chế khác; cần kiểm tra graph thực tế |
| Thêm `requires demo.provider;` vào host | Tạo dependency trực tiếp vào implementation module, không phải cách chung để đăng ký hoặc thay thế provider |

Điều quan trọng là phân biệt **lỗi biên dịch do readability/exports** với **lỗi service lookup do uses/provides hoặc phạm vi provider**. Sửa sai loại directive có thể làm một lỗi khác xuất hiện nhưng không giải quyết nguyên nhân.

## 8. Đọc graph, tìm provider và chọn overload phù hợp

Một chương trình có nhiều named modules sẽ trải qua các bước:

1. **Module discovery:** runtime thấy những module có thể truy cập từ module path, system modules hoặc nguồn khác.
2. **Resolution:** chọn module root, đi theo `requires` và các quy tắc khác để hình thành graph. Service binding có thể đưa thêm module provider vào graph tùy cách resolve. Trong ví dụ, `--add-modules demo.provider` đặt root rõ ràng.
3. **Layer/class loader:** các module đã resolve được đưa vào module layer, rồi runtime gán class loader thích hợp.
4. **Service discovery:** khi code consumer gọi `ServiceLoader`, nó tìm provider trong phạm vi loader/layer và metadata dịch vụ, sau đó tạo instance khi được yêu cầu.

Đoạn sau là **minh họa**, giả định đang ở `demo.host` và đã import `demo.spi.GreetingService` cùng `java.util.ServiceLoader`:

~~~java
ServiceLoader<GreetingService> fromTccl =
        ServiceLoader.load(GreetingService.class);

ServiceLoader<GreetingService> fromBootLayer =
        ServiceLoader.load(ModuleLayer.boot(), GreetingService.class);
~~~

- `ServiceLoader.load(service)` sử dụng **thread context class loader** tại thời điểm gọi. Thông thường khi chạy `main`, TCCL là application/system loader, nhưng framework hoặc host plugin có thể thay đổi.
- `ServiceLoader.load(layer, service)` tìm provider từ **named modules** của layer đã chỉ định và các parent layers; nó không tìm provider trong unnamed modules/classpath.
- Cả hai overload vẫn yêu cầu caller là explicit named module khai báo `uses` cho service.
- Không overload nào tạo JAR, copy file vào plugin directory hoặc tự bổ sung module vào graph đã tồn tại.

Khi thiết kế plugin được thêm lúc runtime, ứng dụng có thể tạo `ModuleLayer` riêng và dùng `ServiceLoader.load(pluginLayer, ServiceType.class)` sau khi resolve provider; phần này thuộc quản lý module layer và vòng đời plugin, không được tự động hoàn thành bởi một directive `uses`.

### Lazy discovery và lỗi có thể xuất hiện muộn

`ServiceLoader` có tính lazy: một số việc tìm/đọc metadata và tạo provider chỉ xảy ra khi duyệt iterator hoặc stream. Lỗi khai báo provider, class thiếu, provider không hợp lệ hoặc thất bại khởi tạo thường biểu hiện qua `ServiceConfigurationError` ở giai đoạn sử dụng loader dịch vụ. `reload()` xóa cache provider trong instance `ServiceLoader` đó, nhưng không thêm module vào graph, không viết `module-info.java` và không làm provider mới xuất hiện nếu phạm vi class loader/module layer vẫn sai.

Nếu có nhiều provider, đừng đặt quy tắc nghiệp vụ dựa vào thứ tự provider được tìm qua các named modules, vì thứ tự module trong layer không được API bảo đảm.

## 9. Các nhầm lẫn thường gặp

### Nhầm 1: consumer phải export interface SPI từ module của mình

Sai khi SPI thuộc module khác. Consumer chỉ export các package **do nó sở hữu**. Với ví dụ, `demo.spi` export `demo.spi`; `demo.host` export `demo.host.api` vì một ứng dụng khác gọi API host. Không chuyển `exports demo.spi;` sang `demo.host`.

### Nhầm 2: `uses` thay thế mọi `requires`

Sai. `uses` khai báo service dependence; khi consumer dùng kiểu service ở module API riêng, nó vẫn cần đọc module và được phép truy cập package. Hai khái niệm **module readability** và **service consumption** độc lập.

### Nhầm 3: `exports` là để `ServiceLoader` tìm provider class

Không cần export implementation package chỉ để dùng `provides ... with ...`. ServiceLoader sử dụng metadata provider/module phù hợp để tìm implementation. Export implementation ra ngoài còn tăng coupling và bộc lộ API nội bộ không cần thiết.

### Nhầm 4: module có `main` luôn là module cần `uses`

Không. Module gọi `ServiceLoader` thực tế mới cần khai báo service consumption. Một module ứng dụng có thể gọi API của một module khác; module thư viện bên trong mới là nơi `ServiceLoader.load` được thực thi.

### Nhầm 5: Java tìm provider ở mọi JAR trên module path

Không. Có mặt trên module path và được resolve vào configuration/module layer là hai việc khác nhau. Cần kiểm tra roots, quan hệ phụ thuộc và service binding. Với chương trình học, dùng `--add-modules provider.module` giúp làm rõ module provider được chọn.

### Nhầm 6: `requires transitive` luôn tốt hơn `requires`

Không. `requires transitive` làm module đọc module hiện tại cũng đọc phụ thuộc, là quyết định thiết kế API công khai; dùng quá nhiều sẽ để lộ dependency không cần thiết cho client.

### Nhầm 7: classpath provider và named-module provider khai báo giống hệt

Không hẳn. Với JAR trên classpath, cơ chế khai báo service provider thường dùng `META-INF/services/<fully-qualified-service-name>`. Với **explicit named module**, provider-side descriptor dùng `provides ... with ...`, consumer-side dùng `uses`. Đừng nhầm các cách triển khai hoặc mặc định thêm một file descriptor sẽ sửa được module descriptor thiếu `uses`.

## 10. Checklist thiết kế và chẩn đoán

Trước khi tìm lỗi runtime, hãy xác minh:

1. **Service API:** kiểu service có tồn tại ở package/module dự kiến và có quyền truy cập đúng không?
2. **Readability:** module consumer có `requires` module SPI (hoặc quan hệ đọc hợp lệ khác) không?
3. **Exports:** module sở hữu package service có `exports` cho consumer và provider không?
4. **Uses:** module có code gọi `ServiceLoader` đã khai báo `uses` đúng tên service chưa?
5. **Provides:** module implementation có `provides Service with Provider;` và provider hợp lệ không?
6. **Resolution:** module provider có được đưa vào graph/layer không, hay mới chỉ là một JAR nằm trên đĩa?
7. **Lookup:** overload `ServiceLoader.load` đang dùng TCCL, loader hoặc module layer nào?
8. **Instantiation:** có lỗi `ServiceConfigurationError` khi duyệt hoặc khởi tạo provider không?
9. **API design:** client của consumer có thật sự cần package export và phụ thuộc transitive nào không?

Sau khi biên dịch ví dụ, có thể xem descriptor bằng lệnh:

~~~bash
java --module-path mods --describe-module demo.host
java --module-path mods --describe-module demo.provider
~~~

Các mô tả sẽ cho phép kiểm tra `requires`, `exports`, `uses` hoặc `provides` của module liên quan; cách trình bày chi tiết có thể khác theo JDK. Khi thấy `ServiceLoader` trả kết quả rỗng, hãy kiểm tra module có resolve và provider có khai báo, trước khi cho rằng chính `uses` đã tự động tìm và cài provider.

## 11. Câu hỏi tự kiểm tra

1. **Module consumer `requires demo.spi`, nhưng thiếu `uses demo.spi.GreetingService`. Đã đủ điều kiện dùng `ServiceLoader` từ explicit named module chưa?** Chưa. Cần `uses` trong module gọi ServiceLoader.
2. **Module API có `exports demo.spi`, nhưng consumer không `requires demo.spi`. Consumer có đọc được service type theo cách thông thường không?** Không. Export không tự tạo readability.
3. **Provider có `provides` nhưng không export package implementation. Có thể được ServiceLoader tìm thấy không?** Có, nếu module provider được resolve và metadata hợp lệ; consumer không cần import implementation.
4. **Module `demo.app` gọi `GreetingEngine.run()`, còn `demo.host` gọi ServiceLoader. `uses` đặt ở đâu?** Ở `demo.host`.
5. **Module consumer có bắt buộc `exports` package không?** Không. Chỉ khi cần module khác truy cập API của consumer.
6. **Chỉ đặt module provider lên module path đã đủ để mọi cấu hình khởi chạy tìm được provider chưa?** Chưa; phải được resolve trong phạm vi được tìm kiếm.
7. **Khi nào cân nhắc `requires transitive`?** Khi muốn client của module hiện tại tự đọc dependency, thường do public API dùng các kiểu trong module phụ thuộc.
8. **Khác nhau giữa `requires` và `provides` là gì?** `requires` tạo phụ thuộc module/readability; `provides` đăng ký implementation cho một service.
9. **`ServiceLoader.reload()` có sửa được lỗi consumer thiếu `uses` hoặc provider chưa resolve không?** Không.

**Ghi nhớ:** consumer đọc **API module** qua `requires`, được phép dùng **service type** nhờ package `exports` của module sở hữu, và khai báo nhu cầu khám phá provider qua `uses`. Consumer `exports` package của chính mình chỉ khi cần cung cấp public API ra ngoài. Provider đăng ký implementation bằng `provides ... with ...`; module resolution và `ServiceLoader` nối các thành phần tại runtime.

## Tài liệu tham khảo

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): consumer `uses`, provider `provides`, loader/layer, lazy discovery và lỗi.
- [Java Language Specification 17, `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): cú pháp, readability, `requires`, `exports`, `uses` và `provides`.
- [Java SE 17 — java.lang.module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): resolution, module graph và service binding.
