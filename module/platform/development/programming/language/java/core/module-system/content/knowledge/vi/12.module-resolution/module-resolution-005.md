# Parent configuration trong quá trình resolve

Trong Java Platform Module System (JPMS), một ứng dụng có thể phân giải module theo nhiều giai đoạn. Ví dụ, host khởi động trước với một tập module nền tảng và module API, sau đó mới nạp plugin. Khi phân giải plugin, Java cần biết những module nào đã được giải quyết ở giai đoạn trước để có thể tái sử dụng dependency thay vì tìm và định nghĩa lại chúng.

Đó là vai trò của **parent configuration** trong quá trình resolution. Một `Configuration` con giữ tham chiếu tới configuration cha, sử dụng các module đã có ở cha để thỏa mãn dependency của module mới, đồng thời phân giải thêm những module được tìm thấy từ các `ModuleFinder` được cung cấp.

Parent configuration là nền tảng cho mô hình nhiều tầng của JPMS: module dùng chung nằm trong cấu hình cha; module bổ sung như plugin được phân giải trong cấu hình con; sau đó một `ModuleLayer` được tạo để định nghĩa các module mới ở runtime.

## 1. Configuration là gì?

`java.lang.module.Configuration` biểu diễn kết quả của quá trình phân giải module. Nó chứa các module đã được resolution chọn, các dependency giữa chúng và một hoặc nhiều parent configuration.

Configuration là metadata của module graph đã phân giải. Nó chưa phải là các module object đang chạy trong JVM. Để định nghĩa module vào runtime, ứng dụng dùng `ModuleLayer` từ configuration đó.

Có thể hình dung:

```text
ModuleFinder(s)
     |
     | khám phá module
     v
Configuration.resolve(...)
     |
     | tạo module graph đã phân giải
     v
Configuration
     |
     | ModuleLayer.defineModules...
     v
ModuleLayer và các Module runtime
```

Ba khái niệm có trách nhiệm khác nhau:

- `ModuleFinder` tìm module từ runtime image, thư mục module hoặc JAR.
- `Configuration` xác định module nào cần thiết và dependency được đáp ứng ra sao.
- `ModuleLayer` định nghĩa các module đã phân giải trong runtime và gắn chúng với class loader.

Không phải cứ tìm thấy một JAR là module đó đã được phân giải. Nó cần được chọn bởi resolution, trực tiếp như root hoặc gián tiếp như dependency.

## 2. Parent configuration là gì?

Một configuration có thể có một hoặc nhiều parent configuration. Parent chứa module graph đã được phân giải trước đó. Khi phân giải một configuration mới, resolver có thể dùng các module trong parent để đáp ứng dependency của module mới.

Ví dụ một ứng dụng plugin:

```text
Boot Configuration
       |
       v
Host Configuration
       |
       v
Plugin Configuration
```

Host configuration có thể chứa module API dùng chung. Plugin configuration chứa module plugin được nạp sau. Nếu plugin khai báo `requires com.example.host.api;`, resolver có thể dùng module API đã có trong parent configuration.

Điều này giúp tránh việc mỗi plugin phải mang theo một bản sao module API và tránh định nghĩa lại cùng một module trong nhiều layer.

Một configuration con không phải bản sao đầy đủ của configuration cha. Nó có các module được phân giải trong chính nó và tham chiếu tới parent configuration(s). Có thể xem cấu trúc cha qua:

```java
Configuration configuration = ModuleLayer.boot().configuration();

for (Configuration parent : configuration.parents()) {
    System.out.println(parent);
}
```

Với configuration con, `parents()` cho biết các configuration cha trực tiếp. Quan hệ này là cơ sở để resolution tra cứu module đã có trước đó.

## 3. Parent configuration được dùng khi nào?

Parent configuration đặc biệt hữu ích trong các tình huống phân giải theo từng giai đoạn:

- Host application được khởi động trước, plugin được nạp sau.
- Một runtime layer chứa API và dịch vụ dùng chung.
- Nhiều nhóm module cần tái sử dụng dependency nền tảng đã được định nghĩa.
- Ứng dụng tạo nhiều plugin layer độc lập nhưng cùng dùng một module API.
- Công cụ cần phân giải một nhóm module mới dựa trên module graph đã tồn tại.

Ví dụ, host có module:

```java
module com.example.host.api {
    exports com.example.host.api;
}
```

Plugin khai báo:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
}
```

Khi resolve plugin, parent configuration cung cấp module `com.example.host.api`. Plugin không cần đóng gói một bản sao module API trong thư mục plugin. Module API được tham chiếu từ parent configuration và có thể được dùng để thỏa mãn dependency.

## 4. API resolve của Configuration

Một configuration đã có thể được dùng làm parent để phân giải thêm module. Phương thức instance thường dùng là:

```java
Configuration childConfiguration =
        parentConfiguration.resolve(
                beforeFinder,
                afterFinder,
                roots
        );
```

Các tham số:

- `beforeFinder`: tìm module từ nguồn này trước khi tìm trong parent configurations.
- `afterFinder`: tìm module từ nguồn này sau khi tìm trong parent configurations.
- `roots`: tên các module root cần phân giải cho configuration mới.

Phương thức instance dùng configuration hiện tại làm parent. Kết quả là configuration mới có các module được phân giải trong giai đoạn hiện tại cùng liên kết tới parent configuration.

Ngoài phương thức instance, có phương thức static nhận danh sách parent configuration:

```java
Configuration childConfiguration =
        Configuration.resolve(
                beforeFinder,
                List.of(parentConfiguration),
                afterFinder,
                roots
        );
```

Dạng static hữu ích khi cần chỉ định nhiều parent configuration hoặc muốn kiểm soát rõ tập parent. Với một parent đơn, phương thức instance thường dễ đọc hơn.

### 4.1. Vì sao có beforeFinder và afterFinder?

Resolution có thể tìm module từ ba nơi theo thứ tự:

1. Finder được truyền ở vị trí `beforeFinder`.
2. Các parent configuration.
3. Finder được truyền ở vị trí `afterFinder`.

Thứ tự này quan trọng khi cùng một tên module có thể xuất hiện ở nhiều nguồn. Finder trước parent có độ ưu tiên khám phá trước; finder sau parent chỉ được xét sau khi resolver đã tìm trong các parent configuration.

Trong cấu hình plugin thông thường, thường muốn tái sử dụng module đã có ở parent. Có thể truyền finder plugin ở vị trí `beforeFinder` hoặc `afterFinder` tùy chính sách chọn module. Ví dụ phổ biến:

```java
Configuration pluginConfiguration =
        hostConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.alpha")
        );
```

Ở đây:

- `pluginFinder` tìm các module plugin.
- `ModuleFinder.of()` là finder rỗng cho nguồn sau parent.
- `hostConfiguration` là parent configuration.
- `com.example.plugin.alpha` là root module.

Với cách này, plugin finder được xét trước parent configuration. Nếu hệ thống cần ưu tiên module đã có ở parent khi trùng tên, cần thiết kế nguồn finder và thứ tự tìm kiếm phù hợp, đồng thời tránh cung cấp hai phiên bản cùng tên trong cùng cấu hình.

## 5. Resolution sử dụng module trong parent như thế nào?

Giả sử parent configuration đã có:

```text
com.example.host.api
java.base
java.logging
```

Finder plugin có:

```text
com.example.plugin.alpha
com.example.plugin.beta
```

Plugin alpha có descriptor:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
    requires java.logging;
}
```

Khi resolver xử lý root `com.example.plugin.alpha`, nó kiểm tra các dependency:

- `com.example.host.api` đã có trong parent configuration nên có thể được dùng để thỏa mãn dependency.
- `java.logging` nếu đã có trong parent configuration cũng có thể được dùng từ parent.
- Các dependency chưa có trong parent sẽ tiếp tục được tìm ở các finder theo thứ tự resolution.

Kết quả child configuration chứa module plugin mới và các dependency mới cần phân giải. Module đã có ở parent vẫn thuộc parent configuration, không bị sao chép thành một module khác chỉ vì child cần đọc nó.

Nếu dependency không có trong parent và cũng không tìm thấy từ finder, resolution thất bại. Đây là lỗi module graph, không phải lỗi import trong mã nguồn.

## 6. Ví dụ đầy đủ: resolve plugin từ host configuration

Giả sử host API đã được biên dịch thành exploded module trong thư mục `mods`, còn plugin JAR nằm trong `plugins`.

Cấu trúc:

```text
application/
├── mods/
│   └── com.example.host.api/
│       ├── module-info.class
│       └── com/example/host/api/HostService.class
└── plugins/
    └── com.example.plugin.alpha.jar
```

Module host API:

```java
module com.example.host.api {
    exports com.example.host.api;
}
```

Module plugin:

```java
module com.example.plugin.alpha {
    requires com.example.host.api;
}
```

### Bước 1: Tạo parent configuration

Có thể bắt đầu từ boot configuration và phân giải host API:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder hostFinder =
        ModuleFinder.of(Path.of("mods"));

Configuration hostConfiguration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        hostFinder,
                        ModuleFinder.of(),
                        Set.of("com.example.host.api")
                );
```

Host configuration dùng boot configuration làm parent. Root là module host API; các dependency của host API được resolution từ parent hoặc finder.

### Bước 2: Khám phá plugin

```java
ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));
```

Finder này tìm các module trong thư mục plugin. Nó có thể nhận diện modular JAR và automatic module theo quy tắc module path.

### Bước 3: Resolve plugin dựa trên parent configuration

```java
Configuration pluginConfiguration =
        hostConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.alpha")
        );
```

Ở bước này, `hostConfiguration` là parent. Khi plugin khai báo `requires com.example.host.api;`, resolver có thể đáp ứng dependency từ parent configuration.

### Bước 4: Kiểm tra kết quả

```java
pluginConfiguration.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);
```

`modules()` trả về các module được phân giải trực tiếp trong configuration hiện tại. Các module thuộc parent không được lặp lại như module mới trong tập này. Muốn xem parent, dùng `parents()`.

## 7. Parent configuration và parent ModuleLayer liên hệ ra sao?

Configuration là kết quả resolution; ModuleLayer là runtime structure được định nghĩa từ configuration.

Khi định nghĩa layer con, layer cha phải tương ứng với parent configuration đã dùng để resolve. Cách thông thường là gọi phương thức trên parent layer:

```java
ModuleLayer hostLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        hostConfiguration,
                        ClassLoader.getSystemClassLoader()
                );

ModuleLayer pluginLayer =
        hostLayer.defineModulesWithOneLoader(
                pluginConfiguration,
                ClassLoader.getSystemClassLoader()
        );
```

Ở đây:

- `hostLayer` được tạo từ host configuration, với boot layer làm parent.
- `pluginLayer` được tạo từ plugin configuration, với host layer làm parent.
- Plugin layer có thể tham chiếu module API đã được định nghĩa trong host layer khi dependency đã được resolve đúng.

Không nên resolve plugin từ một parent configuration rồi định nghĩa nó dưới một layer không tương ứng. Parent configuration và parent layer cần khớp với nhau để module graph runtime nhất quán.

## 8. Parent configuration không tự cấp readability

Đây là điểm cần nhớ khi debug.

Giả sử module `com.example.plugin.alpha` nằm trong child configuration và `com.example.host.api` nằm trong parent configuration. Quan hệ parent không tự động khiến plugin đọc host API.

Plugin vẫn cần:

```java
requires com.example.host.api;
```

Ngoài ra, module host API phải export package chứa kiểu plugin muốn dùng:

```java
exports com.example.host.api;
```

Hai điều kiện có vai trò riêng:

- Parent configuration giúp resolver tìm thấy module API đã phân giải trước đó.
- `requires` tạo quan hệ readability từ plugin tới API.
- `exports` cho phép plugin truy cập package API theo quy tắc JPMS.

Readability không đồng nghĩa với quyền truy cập mọi package. Một module có thể đọc module khác nhưng vẫn không truy cập được package chưa export hoặc chưa mở cho reflection.

## 9. Nhiều parent configurations

JPMS hỗ trợ configuration có nhiều parent. Điều này hữu ích khi một layer mới cần tái sử dụng module từ nhiều nhánh layer đã được phân giải độc lập.

Ví dụ cấu trúc:

```text
             Boot Configuration
               /           \
              v             v
       Data Configuration  UI Configuration
               \           /
                v         v
             Plugin Configuration
```

Có thể dùng overload static của `Configuration.resolve`:

```java
Configuration pluginConfiguration =
        Configuration.resolve(
                pluginFinder,
                List.of(dataConfiguration, uiConfiguration),
                ModuleFinder.of(),
                Set.of("com.example.plugin.dashboard")
        );
```

Resolver có thể dùng các module trong parent configurations để thỏa mãn dependency của plugin.

Tuy nhiên, nhiều parent làm cấu trúc phức tạp hơn. Cần bảo đảm không có xung đột tên module và các parent configuration có thể cùng tham gia một configuration graph hợp lệ. Nếu cùng một module name xuất hiện ở nhiều parent với nội dung hoặc identity không tương thích, resolution có thể thất bại hoặc cấu trúc layer không đáp ứng thiết kế mong muốn.

## 10. resolve và resolveAndBind khi có parent

Configuration có hai nhóm phương thức resolution thường gặp:

- `resolve(...)` xử lý các root và dependency được khai báo bằng `requires`.
- `resolveAndBind(...)` làm thêm service binding dựa trên `uses` và `provides`.

Nếu plugin sử dụng ServiceLoader và muốn provider module được tìm tự động trong các nguồn có thể quan sát, có thể dùng:

```java
Configuration pluginConfiguration =
        hostConfiguration.resolveAndBind(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.plugin.host")
        );
```

Service binding có thể bổ sung provider module và dependency của provider vào child configuration. Các module đã có trong parent configuration vẫn có thể được dùng để thỏa mãn dependency.

Cần phân biệt việc provider được tìm thấy với việc provider được khởi tạo. Resolution đưa module provider vào configuration; ModuleLayer định nghĩa module; ServiceLoader mới thực hiện việc tìm và khởi tạo provider theo phạm vi loader hoặc layer được chọn.

## 11. Cách quan sát parent configuration và module graph

Một số API giúp kiểm tra cấu trúc configuration:

| API | Ý nghĩa |
|---|---|
| `Configuration.parents()` | Các parent configuration trực tiếp |
| `Configuration.modules()` | Module được phân giải trong configuration hiện tại |
| `Configuration.findModule(name)` | Tìm module trong configuration graph |
| `Configuration.resolve(...)` | Phân giải root và dependency |
| `Configuration.resolveAndBind(...)` | Resolution kèm service binding |
| `ModuleLayer.configuration()` | Configuration dùng để định nghĩa layer |
| `ModuleLayer.parents()` | Parent layer runtime |
| `ModuleLayer.modules()` | Module được định nghĩa trực tiếp trong layer |
| `Module.canRead(other)` | Kiểm tra readability giữa hai module runtime |

Ví dụ kiểm tra parent và module hiện tại:

```java
System.out.println("Child modules:");

pluginConfiguration.modules().stream()
        .map(resolved -> resolved.name())
        .sorted()
        .forEach(System.out::println);

System.out.println("Parent configurations:");

for (Configuration parent : pluginConfiguration.parents()) {
    parent.modules().stream()
            .map(resolved -> resolved.name())
            .sorted()
            .forEach(System.out::println);
}
```

Lưu ý `Configuration.findModule(name)` có thể tìm trong configuration hiện tại và các parent configuration. Trong khi đó, `modules()` chỉ liệt kê module được phân giải trực tiếp trong configuration đó.

Để kiểm tra readability sau khi layer đã được định nghĩa, lấy hai `Module` object rồi gọi `canRead`:

```java
boolean readable = pluginModule.canRead(hostApiModule);
System.out.println(readable);
```

Đây là kiểm tra runtime thực tế. Nếu chỉ kiểm tra configuration, hãy xem dependency trong descriptor và kết quả resolution.

## 12. Lỗi thường gặp khi dùng parent configuration

**Dependency có trong thư mục nhưng resolution vẫn báo thiếu module.**

Finder có thể chưa trỏ tới đúng thư mục hoặc module chưa được phân giải vào parent configuration. Kiểm tra module path, tên module và tập root.

**Tưởng module trong parent tự động được đọc.**

Parent configuration giúp module được tìm thấy để thỏa mãn dependency, nhưng plugin vẫn cần `requires` để có readability.

**Dùng sai thứ tự beforeFinder và afterFinder.**

Finder trước parent được ưu tiên tìm trước; finder sau parent được xét sau. Nếu có module cùng tên ở nhiều nguồn, thứ tự này có thể làm thay đổi module được chọn. Tránh cung cấp nhiều bản cùng tên không cần thiết.

**Resolve child từ boot configuration thay vì host configuration.**

Nếu module API chỉ được phân giải trong host configuration, dùng boot configuration làm parent cho plugin sẽ không cung cấp module đó. Hãy resolve child từ đúng parent configuration.

**Định nghĩa layer với parent không khớp configuration.**

Configuration được resolve từ một parent graph nên được định nghĩa dưới layer tương ứng. Nếu ghép sai, cấu trúc runtime có thể không hợp lệ.

**Cho rằng parent layer cho phép truy cập package nội bộ.**

Readability và exports vẫn được kiểm tra. Nếu cần reflection sâu, cần opens riêng; parent relationship không bỏ qua encapsulation.

**Nhầm configuration với layer.**

Configuration mô tả module graph đã resolve. Layer chứa các module object được định nghĩa trong runtime và gắn với class loader. Một configuration chưa được dùng để define layer thì chưa tạo ra module runtime mới.

## 13. Nguyên tắc thiết kế parent configuration

Khi thiết kế hệ thống phân giải module theo nhiều giai đoạn:

1. **Đặt API dùng chung ở parent:** các interface và kiểu hợp đồng ổn định nên được phân giải trước plugin.
2. **Giữ dependency tường minh:** plugin khai báo `requires` tới module API mà nó thực sự sử dụng.
3. **Dùng đúng parent configuration:** child resolution cần dựa trên configuration tương ứng với parent layer dự định.
4. **Chọn finder có chủ đích:** quyết định nguồn module nào được ưu tiên trước parent và nguồn nào được tìm sau.
5. **Tránh trùng tên module:** chỉ có một module phù hợp cho mỗi tên trong configuration graph.
6. **Phân biệt resolution và definition:** resolve xong mới define layer; không coi finder là loader.
7. **Kiểm tra exports:** dependency có thể resolve nhưng package vẫn phải được export để mã nguồn truy cập.
8. **Dùng resolveAndBind khi cần service:** chỉ bật service binding khi mô hình provider yêu cầu.
9. **Quan sát configuration trước khi define layer:** kiểm tra root, module được phân giải và parent để dễ chẩn đoán.
10. **Giữ layer graph đơn giản:** chỉ tạo nhiều parent khi có yêu cầu tái sử dụng module thực sự.

## Kết luận

Parent configuration cung cấp module graph đã được phân giải ở giai đoạn trước để resolver dùng khi tạo configuration mới. Khi child module khai báo `requires` tới một module đã có trong parent, dependency có thể được đáp ứng từ parent thay vì tìm và phân giải một bản mới.

`Configuration.resolve` và `resolveAndBind` nhận finder, parent configuration và root module để xây dựng graph. Thứ tự tìm kiếm giữa `beforeFinder`, parent configurations và `afterFinder` có ý nghĩa khi nhiều nguồn chứa module cùng tên. Sau resolution, configuration con được dùng để định nghĩa layer con tương ứng.

Parent configuration không tự cấp readability hoặc quyền truy cập package. Plugin vẫn cần `requires`, module sở hữu cần `exports`, và các quy tắc access modifier của Java tiếp tục áp dụng. Hiểu rõ sự phân biệt giữa discovery, resolution, parent configuration và ModuleLayer giúp xây dựng plugin system có dependency rõ ràng, tái sử dụng module dùng chung và dễ kiểm tra hơn.