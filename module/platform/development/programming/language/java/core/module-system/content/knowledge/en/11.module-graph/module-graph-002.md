# Configuration resolve module graph

Java Platform Module System (JPMS) không chỉ cần biết tên các module và dependency được khai báo. Trước khi một ứng dụng modular chạy, Java phải xác định chính xác những module nào tham gia cấu hình và cách chúng phụ thuộc vào nhau. Quá trình đó được gọi là **module resolution**.

Kết quả resolution được biểu diễn bằng một đối tượng `Configuration`. Configuration chứa tập module đã được giải quyết cùng các quan hệ dependency của chúng. Từ cấu hình này, Java có thể tạo một `ModuleLayer` để nạp và chạy các module trong một môi trường runtime cụ thể.

Hiểu cách resolve module graph giúp bạn phân tích vì sao một module được đưa vào ứng dụng, vì sao dependency bị thiếu, và cách tạo cấu hình module động cho plugin hoặc extension.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích module resolution và vai trò của module graph.
- Phân biệt root modules với các dependency được tìm thấy gián tiếp.
- Hiểu vai trò của `ModuleFinder`, `Configuration` và `ModuleLayer`.
- Sử dụng `Configuration.resolve()` để giải quyết một tập module.
- Phân biệt `resolve()` với `resolveAndBind()` khi có ServiceLoader.
- Đọc lỗi resolution và kiểm tra cấu hình bằng công cụ JDK.

## 1. Module graph và module resolution

Một ứng dụng modular gồm nhiều named module. Mỗi module có thể khai báo dependency bằng `requires` trong `module-info.java`.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Và module service:

~~~java
module com.acme.service {
    requires com.acme.model;
}
~~~

Đồ thị dependency có hướng:

~~~text
com.acme.app ──requires──> com.acme.service
                                  |
                                  └──requires──> com.acme.model
~~~

Khi ứng dụng khởi chạy với module `com.acme.app` làm module gốc, Java phải tìm module app, service và model. Tập hợp các module được tìm thấy và các quan hệ dependency hợp lệ tạo thành module graph của cấu hình đó.

**Module resolution** là quá trình xác định tập module cần thiết và kiểm tra các dependency để tạo ra cấu hình hợp lệ.

Resolution không đơn thuần là tìm một file JAR. Nó còn phải xác định module name, giải quyết dependency đệ quy, kiểm tra các ràng buộc của module system và xây dựng tập module có thể tham gia cấu hình.

## 2. Root modules và dependency closure

### 2.1. Root module là điểm bắt đầu

Root module là module được chọn làm điểm bắt đầu cho quá trình resolution.

Khi chạy ứng dụng bằng launcher:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Module `com.acme.app` là root module được chỉ định bởi tùy chọn `-m`.

Khi biên dịch nhiều module bằng `javac`, tùy chọn `-m` cũng xác định các module gốc cần biên dịch:

~~~bash
javac --module-source-path src -d out -m com.acme.app
~~~

Các module mà app yêu cầu sẽ được tìm tiếp trong quá trình resolution.

Có thể bổ sung root module bằng tùy chọn `--add-modules`:

~~~bash
java --module-path mods --add-modules com.acme.plugin -m com.acme.app/com.acme.app.Main
~~~

Lúc này `com.acme.plugin` cũng được đưa vào tập root module để resolution, cùng với module app được chọn làm main module.

Tùy chọn `--add-modules` còn hỗ trợ các giá trị đặc biệt như `ALL-MODULE-PATH` và `ALL-SYSTEM`. Chỉ sử dụng chúng khi ứng dụng thực sự cần đưa toàn bộ nhóm module tương ứng vào cấu hình.

### 2.2. Dependency closure

Sau khi xác định root modules, Java lần theo các chỉ thị `requires` để tìm dependency cần thiết.

Ví dụ:

~~~text
Roots:
  com.acme.app

Dependency declarations:
  app     requires service
  service requires model
  model   requires java.base
~~~

Tập module được giải quyết có thể gồm:

~~~text
com.acme.app
com.acme.service
com.acme.model
java.base
~~~

Tập hợp này là dependency closure bắt đầu từ các root module: các module cần thiết được tìm thấy bằng cách lần theo dependency.

Một module có thể được giải quyết vào configuration dù root module không khai báo trực tiếp `requires` tới nó. Điều đó xảy ra khi module nằm trong chuỗi dependency của một module khác.

Tuy nhiên, **được giải quyết vào configuration không đồng nghĩa mọi root module đều đọc được module đó**. Khả năng đọc còn phụ thuộc vào quan hệ `requires` và modifier `transitive`. Đây là điểm cần phân biệt khi phân tích module graph và readability graph.

### 2.3. Module quan sát được

Để một module được giải quyết, Java phải có khả năng tìm thấy module đó trong các nguồn module phù hợp. Tập các module có thể được tìm thấy được gọi là các module observable trong ngữ cảnh resolution.

Các nguồn phổ biến:

- Module hệ thống của JDK.
- Thư mục hoặc JAR trên module path.
- Module finder được cung cấp qua API.
- Các cấu hình cha khi tạo configuration mới.

Một module có thể có mặt trên ổ đĩa nhưng không thuộc tập module observable của lần resolution hiện tại nếu đường dẫn hoặc module finder không đưa nó vào phạm vi tìm kiếm.

## 3. ModuleFinder: tìm module để resolution

API `java.lang.module.ModuleFinder` biểu diễn nguồn có thể tìm module.

Tạo finder từ thư mục:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
~~~

Tạo finder cho module hệ thống:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();
~~~

Tìm một module theo tên:

~~~java
Optional<ModuleReference> reference =
    finder.find("com.acme.app");
~~~

Nếu tìm thấy, `ModuleReference` đại diện cho module và cung cấp thông tin descriptor cùng nội dung module để các bước tiếp theo xử lý.

Các thành phần liên quan:

| API | Vai trò |
|---|---|
| `ModuleFinder.of(path)` | Tìm module trong các vị trí được chỉ định |
| `ModuleFinder.ofSystem()` | Tìm module hệ thống của runtime |
| `ModuleReference` | Đại diện cho một module được tìm thấy |
| `ModuleDescriptor` | Mô tả tên module, requires, exports, opens, uses và provides |

ModuleFinder chỉ giúp tìm module. Nó không tự giải quyết toàn bộ dependency graph. Việc đó thuộc về `Configuration.resolve()` hoặc `resolveAndBind()`.

## 4. Configuration: kết quả của module resolution

`java.lang.module.Configuration` đại diện cho một cấu hình module đã được giải quyết.

Configuration chứa:

- Tập các `ResolvedModule` có trong cấu hình.
- Quan hệ dependency giữa các module đã giải quyết.
- Các configuration cha mà cấu hình hiện tại phụ thuộc vào.

Một số API thường dùng:

~~~java
Configuration configuration = ModuleLayer.boot().configuration();

Set<ResolvedModule> modules = configuration.modules();

Optional<ResolvedModule> app =
    configuration.findModule("com.acme.app");
~~~

Các phương thức trên giúp kiểm tra tập module và tìm module theo tên sau khi resolution thành công.

Configuration là đối tượng bất biến. Sau khi được tạo, không thể thêm hoặc xóa dependency trực tiếp khỏi đối tượng đó. Muốn có cấu hình khác, cần thực hiện một lần resolution mới.

### 4.1. Configuration.resolve()

Phương thức `resolve()` giải quyết các root module và dependency của chúng.

Ví dụ:

~~~java
Path modsPath = Path.of("mods");

ModuleFinder finder = ModuleFinder.of(modsPath);

Configuration parent = ModuleLayer.boot().configuration();

Configuration configuration = parent.resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

Ý nghĩa các tham số:

- `finder`: nguồn module bổ sung cần tìm, ở đây là thư mục `mods`.
- `ModuleFinder.of()`: finder bổ sung rỗng sau các configuration cha.
- `Set.of("com.acme.app")`: tập root module bắt đầu resolution.
- `parent`: configuration cha, thường là configuration của boot layer.

Trong overload ba tham số, configuration hiện tại làm configuration cha. Khi cần nhiều configuration cha, có thể dùng overload nhận danh sách `parents`:

~~~java
Configuration configuration = Configuration.resolve(
    finder,
    List.of(ModuleLayer.boot().configuration()),
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

Kết quả là configuration mới chứa các module được giải quyết từ root và dependency của chúng, cùng với quan hệ tới configuration cha.

### 4.2. Finder trước và sau configuration cha

API resolution cho phép cung cấp finder trước và sau danh sách configuration cha:

~~~java
Configuration configuration = parent.resolve(
    beforeFinder,
    afterFinder,
    roots
);
~~~

Về nguyên tắc, các nguồn này xác định thứ tự tìm module trong quá trình resolution:

- Finder trước được xét trước các configuration cha.
- Configuration cha cung cấp những module đã có trong layer cha.
- Finder sau được xét sau configuration cha.

Cơ chế này hữu ích khi tạo configuration có nguồn module bổ sung hoặc khi cần kiểm soát cách các module được tìm thấy trong một hệ thống nhiều layer. Không nên dùng nó để che giấu việc trùng module name hoặc thay thế một cấu hình dependency không nhất quán.

### 4.3. Đọc kết quả resolution

Sau khi resolve thành công:

~~~java
for (ResolvedModule module : configuration.modules()) {
    System.out.println(module.name());
}
~~~

Có thể kiểm tra một module cụ thể:

~~~java
configuration.findModule("com.acme.service")
    .ifPresent(module ->
        System.out.println(module.name())
    );
~~~

Nếu root module hoặc dependency không thể tìm thấy, resolution có thể ném `ResolutionException`. Nếu module name không hợp lệ, cấu hình có xung đột hoặc dependency graph vi phạm ràng buộc, quá trình tạo configuration cũng có thể thất bại.

## 5. resolve() và resolveAndBind()

Ngoài `resolve()`, Configuration còn có `resolveAndBind()`.

Hai phương thức có mục đích gần nhau nhưng khác nhau ở service binding:

| Phương thức | Hành vi |
|---|---|
| `resolve()` | Giải quyết root modules và các dependency theo requires |
| `resolveAndBind()` | Giải quyết dependency và thực hiện thêm service binding để tìm provider phù hợp |

Service binding liên quan đến `ServiceLoader` và các khai báo `uses`, `provides` trong module descriptor.

Ví dụ module app tiêu thụ service:

~~~java
module com.acme.app {
    uses com.acme.spi.GreetingProvider;
}
~~~

Module provider:

~~~java
module com.acme.greeting.impl {
    requires com.acme.spi;

    provides com.acme.spi.GreetingProvider
        with com.acme.greeting.impl.DefaultGreetingProvider;
}
~~~

Nếu ứng dụng cần tự động đưa các module provider phù hợp vào cấu hình dựa trên service mà các module đã resolved sử dụng, có thể dùng `resolveAndBind()`.

Điều này đặc biệt hữu ích với plugin và service provider. Provider được tìm trong các module finder có liên quan và các dependency của provider cũng có thể được giải quyết.

Không phải mọi ứng dụng đều cần service binding. Nếu module graph đã được xác định đầy đủ bằng các root và requires, `resolve()` thường là đủ.

## 6. Configuration khác ModuleLayer như thế nào?

Hai khái niệm này thường được dùng cùng nhau nhưng không giống nhau.

- **Configuration** mô tả module graph đã được giải quyết.
- **ModuleLayer** là một lớp cấu hình runtime chứa các module đã được định nghĩa và liên kết với class loader.

Có thể hình dung:

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
Resolved module graph
    |
    v
ModuleLayer.defineModules(...)
    |
    v
Runtime modules + class loaders
~~~

Configuration trả lời câu hỏi module nào đã được giải quyết và phụ thuộc ra sao. ModuleLayer trả lời câu hỏi các module đó được nạp và tổ chức thế nào trong runtime.

Boot layer là layer ban đầu do JVM launcher tạo ra. Các module hệ thống và module ứng dụng được giải quyết khi khởi động nằm trong cấu hình tương ứng của boot layer.

### 6.1. Tạo layer mới cho plugin

Một ứng dụng có thể tạo module layer mới để nạp plugin mà không cần đặt toàn bộ plugin vào boot layer.

Ví dụ khung mã:

~~~java
Path pluginPath = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration parent = ModuleLayer.boot().configuration();

Configuration cf = parent.resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin")
);

ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        cf,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

Trong ví dụ:

1. ModuleFinder tìm plugin trong thư mục `plugins`.
2. Configuration.resolve giải quyết root module `com.acme.plugin` cùng dependency.
3. ModuleLayer tạo layer runtime mới có boot layer làm cha.
4. Các module mới được định nghĩa bằng một class loader chung trong layer đó.

Đây là kỹ thuật nền tảng cho kiến trúc plugin modular. Ứng dụng thực tế còn cần xác định cách tìm provider, quản lý vòng đời plugin, xử lý lỗi và giao tiếp qua API ổn định.

## 7. Tùy chọn launcher ảnh hưởng đến module graph

Khi chạy ứng dụng, một số tùy chọn có thể ảnh hưởng đến root module hoặc tập module observable.

### 7.1. --module-path

Chỉ định vị trí chứa các module:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Module path là nguồn để Java tìm các module cần giải quyết.

### 7.2. --add-modules

Bổ sung module gốc ngoài module chính:

~~~bash
java --module-path mods --add-modules com.acme.plugin -m com.acme.app/com.acme.app.Main
~~~

Module được thêm trở thành root cho resolution. Từ đó, dependency của module này cũng được tìm theo các khai báo tương ứng.

### 7.3. --limit-modules

Giới hạn tập module hệ thống có thể quan sát trong cấu hình:

~~~bash
java --limit-modules java.base,java.logging --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Tùy chọn này hữu ích khi muốn tạo runtime image hoặc môi trường chạy với tập module nhỏ hơn. Nếu module cần thiết bị loại khỏi tập observable, resolution có thể thất bại.

### 7.4. --show-module-resolution

Hiển thị thông tin các module được giải quyết:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Đây là cách nhanh để kiểm tra root và dependency khi ứng dụng không chạy như dự kiến.

## 8. Lỗi thường gặp khi resolve module graph

### 8.1. Module not found

Nguyên nhân thường gặp:

- Module name trong requires không khớp.
- Module không có trong module path hoặc finder.
- JAR được đặt trên classpath thay vì module path.
- Filename suy ra automatic module name khác tên đã dùng trong descriptor.

Cách xử lý: kiểm tra tên bằng `jar --describe-module` và xác nhận module path trong lệnh biên dịch hoặc chạy.

### 8.2. Cyclic dependence

Ví dụ:

~~~text
A requires B
B requires C
C requires A
~~~

Named module dependency graph không được có chu trình. Hãy tìm dependency ngược và tách API hoặc abstraction chung sang module thứ ba nếu phù hợp.

### 8.3. Module name conflict

Nếu nhiều nguồn cung cấp module cùng tên, Java có thể không xác định được module reference duy nhất hoặc báo lỗi khi resolve. Kiểm tra module path, module finder và các configuration cha để tránh đưa nhiều bản thay thế cùng tên vào cấu hình.

### 8.4. Package conflict hoặc split package

Một package được phân tán giữa nhiều named module có thể tạo ra xung đột trong cấu hình module, đặc biệt khi các module được đọc cùng nhau hoặc được định nghĩa trong cùng một layer/class loader.

Khi gặp lỗi split package, xác định module nào đang chứa package trùng và cân nhắc hợp nhất package vào một module hoặc thay đổi ranh giới package. Không dùng thêm requires để xử lý một xung đột package.

### 8.5. Resolution thành công nhưng truy cập API thất bại

Một module có thể được giải quyết thành công nhưng mã nguồn vẫn không truy cập được package. Hãy kiểm tra thêm `exports`, qualified export và mức truy cập Java của kiểu/thành viên.

Resolution và package accessibility là các bước kiểm tra liên quan nhưng khác nhau.

## 9. Quy trình debug module graph

Khi ứng dụng báo lỗi module, thực hiện lần lượt:

1. Xác định root module đang được launcher hoặc compiler chọn.
2. Xác nhận module path và các module finder có chứa dependency cần thiết.
3. Kiểm tra tên module thực tế bằng `jar --describe-module` hoặc `java --list-modules`.
4. Đọc `module-info.java` của root và các dependency trực tiếp.
5. Lần theo requires để dựng dependency closure.
6. Kiểm tra chu trình, module trùng tên và package xung đột.
7. Dùng `--show-module-resolution` để quan sát cấu hình mà launcher tạo.
8. Nếu resolution thành công nhưng import thất bại, kiểm tra exports và quyền truy cập.
9. Nếu lỗi liên quan ServiceLoader, kiểm tra `uses`, `provides` và cân nhắc service binding.

Không nên mặc định mọi lỗi module đều do module path. Một lỗi có thể nằm ở tên module, root set, dependency descriptor, package export hoặc cấu hình service.

## 10. Nguyên tắc thiết kế module graph

- Chọn root module rõ ràng cho ứng dụng hoặc plugin.
- Khai báo dependency trực tiếp tại module thực sự cần nó.
- Giữ đồ thị dependency có hướng và không có chu trình.
- Dùng `requires transitive` chỉ khi dependency là một phần của hợp đồng API mà client cần đọc.
- Dùng `requires static` cho dependency compile time có thể vắng mặt ở runtime.
- Giữ module path nhất quán giữa compile, test và runtime.
- Phân biệt resolution với readability và package export.
- Dùng configuration và layer khi cần nạp nhóm module động hoặc plugin.
- Quan sát module resolution trước khi thay đổi module descriptor để tránh sửa sai nguyên nhân.

## 11. Tự kiểm tra

**Tình huống 1:** Module app khai báo `requires com.acme.service;`. Module nào phụ thuộc vào module nào?

**Trả lời:** App phụ thuộc vào service. Cạnh dependency có hướng từ app tới service.

**Tình huống 2:** Root module app yêu cầu service, service yêu cầu model. Vì sao model xuất hiện trong configuration?

**Trả lời:** Vì model nằm trong dependency closure của root app. Java phải giải quyết các dependency cần thiết của những module đã được chọn.

**Tình huống 3:** Model đã được resolve nhưng app không đọc model. Điều đó có mâu thuẫn không?

**Trả lời:** Không. Module được đưa vào configuration không đồng nghĩa mọi module khác đều đọc được nó. Quan hệ đọc cần xét requires và requires transitive.

**Tình huống 4:** Configuration.resolve() và ModuleLayer khác nhau thế nào?

**Trả lời:** Configuration mô tả module graph đã resolve; ModuleLayer định nghĩa các module đó trong runtime và gắn chúng với class loader.

**Tình huống 5:** Khi nào dùng resolveAndBind()?

**Trả lời:** Khi cần resolution có thêm bước tìm và đưa service provider phù hợp vào cấu hình dựa trên các service mà module đã resolved sử dụng.

**Tình huống 6:** Resolution thành công nhưng import package vẫn thất bại. Cần kiểm tra gì?

**Trả lời:** Kiểm tra package có được export cho module hiện tại không và kiểu/thành viên có đủ quyền truy cập Java không.

Khi đọc một module graph, hãy bắt đầu từ root module, lần theo từng cạnh requires để xác định dependency closure, sau đó phân biệt module đã được resolve, module được đọc và package được export. Đây là ba lớp thông tin giúp giải thích chính xác quá trình cấu hình và chạy ứng dụng modular.