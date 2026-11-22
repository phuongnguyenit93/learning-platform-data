# Module có tên, module tự động và module không tên trong hệ thống plugin

## 1. Tại sao phải phân biệt ba loại module?

Trong Java 9+ (JPMS), một plugin JAR có thể chạy như một **explicit named module**, **automatic module** hoặc thuộc **unnamed module**, tùy nội dung JAR và nơi đặt nó khi khởi chạy. Sự khác biệt này quyết định cách đọc dependency, xuất package, phát hiện dịch vụ qua `ServiceLoader` và tạo các `ModuleLayer` để nạp plugin ở runtime.

| Loại | Nơi đặt | Cách xác định module | Đặc điểm |
|---|---|---|---|
| Explicit named module | Module path hoặc module layer | `module-info.class` | Có `requires`, `exports`, `opens`, `uses`, `provides` rõ ràng |
| Automatic module | Module path | JAR không có descriptor, có thể có `Automatic-Module-Name` | Có tên, export/open mọi package, đọc rộng các module đã resolve |
| Unnamed module | Class path | Không có tên; mỗi class loader có unnamed module của nó | Không khai báo module descriptor; code class path chạy theo mô hình truyền thống |

**Lưu ý:** JAR không có `module-info.class` không mặc nhiên là automatic module. Nếu nó chỉ nằm trên class path, các class thường thuộc unnamed module của loader nạp chúng. Chỉ chuyển JAR sang module path mới cho nó khả năng được xem là automatic module.

## 2. Named module và quan hệ dependency

Với explicit named module, nguồn `module-info.java` khai báo contract của module. Ví dụ module API dùng chung:

```java
module demo.api {
    exports demo.api;
}
```

Module host sử dụng service:

```java
module demo.host {
    requires demo.api;
    uses demo.api.GreetingService;
}
```

Module plugin cung cấp provider:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.GreetingService
        with demo.plugin.VietnameseGreeting;
}
```

`requires` tạo quan hệ đọc một module; `exports` cho phép module khác truy cập các **public** type của package được export; `opens` phục vụ deep reflection theo quy tắc JPMS. `uses` và `provides` là các directive cho Java SPI. Host không cần import lớp `VietnameseGreeting`, và package chứa implementation thường không cần export.

Đọc được module không đồng nghĩa mọi package bên trong module đó đều accessible. `exports` cũng không biến package-private thành public. `opens` không phải cách thay thế `exports` cho truy cập bytecode thông thường.

### 2.1. Module resolution và service binding

JVM resolve graph từ root modules, `requires` và các cơ chế bổ sung. Không phải JAR nào xuất hiện trên module path cũng chắc chắn được resolve. Trong các ứng dụng dùng `ServiceLoader`, service binding có thể đưa provider modules thích hợp vào graph; cũng có thể dùng `--add-modules` để chỉ rõ module root khi khởi chạy.

Với named module dùng `ServiceLoader.load(GreetingService.class)`, cần khai báo `uses demo.api.GreetingService;`. Provider explicit named module khai báo `provides`; chỉ đặt file `META-INF/services` trong named module mới không đủ thay cho module descriptor.

## 3. Thực hành Java 17+: ba named module độc lập

Cấu trúc dự án:

```text
project/
└── src/
    ├── demo.api/
    │   ├── module-info.java
    │   └── demo/api/GreetingService.java
    ├── demo.host/
    │   ├── module-info.java
    │   └── demo/host/Main.java
    └── demo.plugin/
        ├── module-info.java
        └── demo/plugin/VietnameseGreeting.java
```

Ba file `module-info.java` chính là các descriptor ở phần trước. Bổ sung mã nguồn sau.

`src/demo.api/demo/api/GreetingService.java`:

```java
package demo.api;

public interface GreetingService {
    String greet(String name);
}
```

`src/demo.host/demo/host/Main.java`:

```java
package demo.host;

import demo.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        boolean found = false;
        for (GreetingService service : ServiceLoader.load(GreetingService.class)) {
            found = true;
            System.out.println(service.greet("Java"));
        }
        if (!found) System.out.println("Không có provider");
    }
}
```

`src/demo.plugin/demo/plugin/VietnameseGreeting.java`:

```java
package demo.plugin;

import demo.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String greet(String name) {
        return "Xin chào " + name;
    }
}
```

Biên dịch bằng JDK 17+ với shell POSIX, từ thư mục `project/`:

```bash
mkdir -p mods dist
javac -encoding UTF-8 --module-source-path src -d mods \
  $(find src -name '*.java')
jar --create --file dist/demo.api.jar -C mods/demo.api .
jar --create --file dist/demo.host.jar -C mods/demo.host .
jar --create --file dist/demo.plugin.jar -C mods/demo.plugin .
java --module-path dist --add-modules demo.plugin \
  --module demo.host/demo.host.Main
```

Output:

```text
Xin chào Java
```

Ở Windows, dùng `javac --module-source-path src -d mods` cùng danh sách đầy đủ file `.java` thay cho `find` và `$()` của POSIX shell. `--add-modules demo.plugin` buộc module provider tham gia graph trong ví dụ, giúp kết quả thực hành rõ ràng.

Kiểm tra mô tả module và quá trình resolve:

```bash
jar --describe-module --file dist/demo.plugin.jar
java --show-module-resolution --module-path dist \
  --add-modules demo.plugin --module demo.host/demo.host.Main
```

Đầu ra của `--show-module-resolution` thay đổi theo JDK; chỉ dùng để xem module nào đã được resolve và quan hệ giữa chúng.

Thử không cài plugin bằng cách giữ riêng hai JAR `demo.api.jar` và `demo.host.jar` trong thư mục module path mới, rồi chạy host **không** thêm `--add-modules demo.plugin`. Khi đó output sẽ là `Không có provider`.

## 4. Automatic module: chuyển đổi một JAR legacy

Một JAR truyền thống không chứa `module-info.class`, khi đặt trên module path, có thể được Java xử lý như automatic module. Nó có module name, export/open các package và có readability rộng để hỗ trợ migration. Tuy vậy nó **không có tính đóng gói chặt** giống explicit named module.

Để tên module ổn định, thêm thuộc tính vào `META-INF/MANIFEST.MF`:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
```

Nếu không khai báo `Automatic-Module-Name`, Java có thể suy ra tên từ file JAR; tên này dễ thay đổi khi đổi artifact. Dùng lệnh:

```bash
jar --describe-module --file legacy-plugin.jar
```

để kiểm tra tên automatic module thực tế. Nếu named host module dùng thư viện đó, có thể khai báo `requires com.example.legacy;` khi module thực sự nằm trên module path.

### 4.1. Provider của automatic module

Automatic module không viết `provides` bằng descriptor nguồn. Khi JAR có cấu hình service provider kiểu class path:

```text
META-INF/services/demo.api.GreetingService
```

và nội dung:

```text
legacy.plugin.LegacyGreeting
```

module system có thể suy ra service provider từ descriptor này. Provider vẫn cần là implementation hợp lệ, có thể nạp được, và module phải tham gia graph thích hợp. Việc tự động đọc thông tin SPI không có nghĩa mọi JAR trên module path tự trở thành plugin.

### 4.2. Giới hạn migration

Automatic module cho phép một giai đoạn chuyển tiếp khi các dependency cũ chưa có `module-info.class`, nhưng tên module, split package, service descriptor, dependency lồng nhau và mối quan hệ với unnamed module vẫn phải được kiểm tra. Khi thiết kế API plugin lâu dài, nên chuyển dần sang explicit named modules để ràng buộc được kiểm tra rõ ràng.

## 5. Unnamed module: class path truyền thống

Các class được load từ class path thường nằm trong unnamed module tương ứng với class loader. Module này không có tên để một explicit named module khai báo `requires`. Nó có thể đọc các named modules đã được resolve trong môi trường phù hợp; ngược lại named module không mặc định đọc unnamed module.

Chạy ứng dụng class path:

```bash
java -cp "host.jar:api.jar:plugin.jar" demo.host.Main
```

Trên Windows thay dấu `:` bằng `;`. Trong mô hình này, service descriptor `META-INF/services/<binary-name-của-service>` cho phép `ServiceLoader` khám phá provider từ class path.

Đặc biệt lưu ý: Một JAR đặt trên class path không tự tham gia module graph như named module, dù JAR có manifest `Automatic-Module-Name`. Cùng một JAR có thể được đối xử khác nhau giữa `-cp` và `--module-path`.

### 5.1. Named host sử dụng thư viện legacy

Nếu `demo.host` là named module nhưng lớp `legacy.Helper` chỉ xuất hiện trên class path, không thể chỉ thêm `legacy.jar` vào class path rồi coi nó là một module mà host có thể `requires`. Cách migration phổ biến là chuyển JAR đó lên module path, xác định tên automatic module và khai báo dependency tương ứng.

Tùy môi trường, `--add-reads` có thể làm ngoại lệ để vá quan hệ đọc tại runtime, nhưng không nên dùng làm cấu trúc mặc định cho hệ thống plugin.

### 5.2. Unnamed module và class loader

Mỗi class loader có unnamed module riêng. Nếu host và plugin dùng class loader khác nhau, class có cùng binary name được định nghĩa hai lần vẫn là hai kiểu khác nhau. Phải chia sẻ interface contract từ cùng loader hoặc module/layer tương thích để tránh `ClassCastException` và lỗi SPI.

## 6. Module path không đồng nghĩa plugin được nạp động

Module path khi JVM khởi động thường được dùng để xây dựng boot layer. Sao chép thêm plugin JAR vào thư mục sau thời điểm đó không khiến boot layer tự resolve module mới. Đối với hệ thống cài plugin lúc chạy, cần quy trình riêng:

1. Dùng `ModuleFinder.of(path)` tìm module trong thư mục/plugin JAR.
2. Resolve configuration từ parent layer với root modules và dependency rõ ràng.
3. Dùng `ModuleLayer.defineModulesWithOneLoader(...)` hoặc biến thể khác để tạo layer.
4. Tìm provider thông qua `ServiceLoader.load(layer, ServiceType.class)`.
5. Quản lý lifecycle, tài nguyên, lỗi, dependency và khả năng dừng plugin.

Ví dụ minh họa **không độc lập**, yêu cầu `parentLayer`, `finder`, `GreetingService` đã được định nghĩa:

```java
var configuration = parentLayer.configuration().resolveAndBind(
        finder, java.lang.module.ModuleFinder.of(),
        java.util.Set.of("demo.plugin"));

ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
        configuration, ClassLoader.getSystemClassLoader());

var providers = ServiceLoader.load(layer, GreetingService.class);
```

ModuleLayer cung cấp phạm vi resolution/loading; nó không tự động tạo sandbox bảo mật, unload classes ngay khi xóa JAR hoặc dừng các thread/tài nguyên mà plugin đã tạo.

## 7. ServiceLoader với ba loại module

| Khía cạnh | Explicit named module | Automatic module | Unnamed module |
|---|---|---|---|
| Consumer khai báo `uses` | Có trong `module-info.java` | Không có descriptor nguồn để viết `uses` | Không có descriptor |
| Provider khai báo `provides` | Có trong `module-info.java` | Thường qua `META-INF/services` | Qua `META-INF/services` |
| Khám phá qua `ServiceLoader` | Theo module graph, layer và đăng ký provider | Khi automatic module được resolve và có descriptor SPI | Theo class loader/class path và descriptor SPI |
| Tách implementation khỏi public API | Export API package, giữ implementation package nội bộ | Các package được export rộng | Không có export restriction theo module |

Trong môi trường thực tế, có thể phối hợp provider trên class path và module path, nhưng discovery phụ thuộc overload `ServiceLoader.load(...)`, context class loader, layer, module graph và cùng class identity của service API. Không nên giả định mọi cách phối hợp đều tự động hoạt động.

## 8. Vấn đề triển khai thường gặp

### Lỗi `ClassNotFoundException` hoặc thiếu provider

Kiểm tra class path/module path, root modules, `uses`, `provides`, file `META-INF/services`, tên provider, class loader và khả năng resolve các dependency. `ServiceLoader` có thể ném `ServiceConfigurationError` khi provider không hợp lệ hoặc không load được.

### Lỗi split package

Hai named modules cùng có package trùng nhau có thể không coexist trong cùng cách cấu hình layer/loader, hoặc gây lỗi resolution/access. Phân chia API, host và plugin thành namespace riêng; không chuyển một JAR legacy lên module path khi chưa kiểm tra package collision.

### `IllegalAccessError` và reflection

Named module có thể đọc module kia nhưng package cần thiết chưa được `exports`; deep reflection thường cần `opens` thích hợp. Automatic module mở rộng các package nhằm hỗ trợ migration, nhưng không nên coi đó là chính sách đóng gói lâu dài.

### Trùng API giữa class path và module path

Nếu hợp đồng `GreetingService` được nạp thành hai class khác nhau bởi các loader khác nhau, provider thực thi interface từ bản này không nhất thiết assignable cho interface host giữ. Giữ một bản contract được chia sẻ và kiểm tra `getClassLoader()`, `getModule()` khi chẩn đoán.

### Thứ tự provider

Đừng dựa vào thứ tự khám phá service làm thứ tự ưu tiên nghiệp vụ. Nếu cần chọn một plugin, dùng metadata/priority và tie-breaker rõ ràng, đồng thời xử lý trường hợp không có provider hoặc nhiều provider trùng capability.

## 9. Checklist kiểm chứng trước khi phát hành

- [ ] Contract là API JAR/module ổn định, không đóng gói trùng qua các loader.
- [ ] Named host khai báo `requires` và `uses` đúng dịch vụ.
- [ ] Explicit provider khai báo `provides` đúng implementation.
- [ ] Automatic/unnamed provider có `META-INF/services` đúng tên và nội dung.
- [ ] Tên automatic module được kiểm tra thực tế; không phụ thuộc vào tên suy đoán.
- [ ] Module graph resolve được và không có split package không hợp lệ.
- [ ] Public API package được export khi dùng JPMS; reflection có `opens` phù hợp.
- [ ] Đã thử có provider, không provider, nhiều provider, dependency thiếu và provider lỗi.
- [ ] Nếu hỗ trợ cài plugin lúc chạy, đã thử ModuleLayer riêng, class loader và lifecycle.

**Kết luận:** Named module cung cấp contract dependency và SPI rõ ràng; automatic module là cầu nối cho JAR legacy; unnamed module giữ cơ chế class path truyền thống. Khi xây dựng hệ thống plugin, phải chọn cấu trúc nhất quán cho contract, host và implementation, đồng thời kiểm chứng module resolution, loader identity và ServiceLoader trên runtime mục tiêu.
