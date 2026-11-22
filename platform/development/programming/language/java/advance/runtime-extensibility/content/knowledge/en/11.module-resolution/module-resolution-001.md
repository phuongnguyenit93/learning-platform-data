# Tìm module trong thư mục plugin bằng ModuleFinder

## 1. ModuleFinder giải quyết bài toán nào?

Trong ứng dụng Java hỗ trợ plugin, host có thể nhận thêm các JAR chứa **Java Platform Module System (JPMS)** module. Trước khi quyết định tạo \`ModuleLayer\` và kích hoạt plugin, host cần biết trong thư mục plugin có những module nào, tên gì, phiên bản gì và chúng khai báo các dependency/service nào.

API \`java.lang.module.ModuleFinder\` của Java 9+ phục vụ bước **tìm kiếm module có thể quan sát được**. Với \`ModuleFinder.of(Path... entries)\`, ứng dụng tạo một finder từ các đường dẫn đến JAR, exploded module hoặc thư mục chứa module.

Ví dụ:

\`\`\`java
Path pluginDir = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(pluginDir);
\`\`\`

Sau đó \`finder.findAll()\` trả về tập \`ModuleReference\` tìm được; mỗi reference chứa \`ModuleDescriptor\` và vị trí module khi có thể xác định.

**Ranh giới quan trọng:** \`ModuleFinder\` chỉ phục vụ *khám phá*. Nó không tự thực thi class plugin, không lập \`ModuleLayer\`, không khởi tạo service provider, cũng không tự tạo graph module đã giải quyết. Để kiểm tra dependency và tạo layer cần thêm các bước với \`Configuration.resolve(...)\` và \`ModuleLayer.defineModulesWithOneLoader(...)\` hoặc cơ chế tương đương.

## 2. ModuleFinder có thể tìm những dạng module nào?

Các loại cần phân biệt:

| Dạng | Ví dụ | Nhận diện/ý nghĩa |
|---|---|---|
| Explicit module | JAR có \`module-info.class\` | Tên, \`requires\`, \`exports\`, \`uses\`, \`provides\` do descriptor khai báo |
| Exploded module | Thư mục chứa \`module-info.class\` và class/resource | Có thể dùng khi build/development hoặc runtime có bố cục phù hợp |
| Automatic module | JAR hợp lệ không có \`module-info.class\` trên module path | Java suy ra tên module; có thể dùng \`Automatic-Module-Name\` trong manifest để ổn định tên |
| Không phải module hợp lệ | Tệp bị hỏng hoặc cách đặt không thể suy ra tên hợp lệ | Finder/descriptor có thể từ chối bằng exception |

**Automatic module không tương đương explicit module.** Java suy ra descriptor với những quy tắc đặc biệt, nên việc dựa vào automatic module lâu dài có thể gây bất ngờ ở tên và khả năng đóng gói. Nếu thiết kế plugin chạy qua JPMS, explicit module thường giúp khai báo contract/dependency rõ ràng hơn.

Đặt \`ModuleFinder.of(pluginDir)\` với một thư mục chứa JAR khác với truyền một đường dẫn tới chính file JAR; cả hai đều là hình thức được API hỗ trợ. Finder tìm các module ở những entry được cung cấp, không phải công cụ quét đệ quy mọi thư mục con theo ý muốn của ứng dụng. Nếu quy ước packaging dùng nhiều cấp thư mục, host phải tự xây danh sách đường dẫn hợp lệ trước khi tạo finder.

## 3. Quy trình khám phá plugin theo JPMS

Một quy trình dễ kiểm tra:

\`\`\`text
Thư mục plugins/
      |
      v
Xác minh path, quyền, dung lượng, nguồn artifact
      |
      v
ModuleFinder.of(pluginDir)
      |
      v
finder.findAll() -> ModuleReference
      |
      v
Đọc ModuleDescriptor: name, version, requires, uses, provides
      |
      v
Chọn roots + kiểm tra allowlist / policy
      |
      v
Configuration.resolve(...) -> dependency graph
      |
      v
ModuleLayer + class loader + ServiceLoader
      |
      v
Khởi tạo / health check / kích hoạt plugin
\`\`\`

Không nên coi \`findAll()\` là danh sách plugin có quyền chạy: một module có thể chỉ là thư viện dependency, không khai báo service provider hoặc không đáp ứng hợp đồng plugin. Mặt khác, mô-đun chứa provider có thể phụ thuộc các module khác và cần được phân giải trước khi dùng.

Một \`ModuleReference\` hữu ích cho preflight nhưng metadata có thể do người phát hành tự khai báo. Để cho phép chạy code bên thứ ba, host còn phải kiểm tra nguồn gốc, tính toàn vẹn/chữ ký artifact và chính sách tin cậy. Class loader và JPMS exports không tạo sandbox bảo mật cho mã không tin cậy.

## 4. Ví dụ Java 17+: liệt kê module trong thư mục plugins

Tạo file **\`ModuleFinderDemo.java\`**:

\`\`\`java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;

public class ModuleFinderDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ModuleFinderDemo <plugin-directory>");
            System.exit(2);
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isDirectory(dir)) {
            System.err.println("Not a directory: " + dir);
            System.exit(2);
        }

        ModuleFinder finder = ModuleFinder.of(dir);
        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ModuleFinderDemo::printModule);
    }

    private static void printModule(ModuleReference reference) {
        ModuleDescriptor d = reference.descriptor();
        System.out.println("name=" + d.name());
        System.out.println("version=" +
                d.version().map(Object::toString).orElse("<none>"));
        System.out.println("automatic=" + d.isAutomatic());
        System.out.println("location=" +
                reference.location().map(Object::toString).orElse("<unknown>"));
        System.out.println("requires=" +
                d.requires().stream()
                        .map(ModuleDescriptor.Requires::name)
                        .sorted()
                        .toList());
        System.out.println("provides=" +
                d.provides().stream()
                        .map(ModuleDescriptor.Provides::service)
                        .sorted()
                        .toList());
    }
}
\`\`\`

Chương trình sắp xếp tên module và danh sách phụ thuộc để phần kết quả dễ đọc hơn. Nó sử dụng các API chuẩn của Java 17, chưa tải class plugin hay khởi tạo provider. \`ModuleFinder.of\` hoặc \`findAll\` có thể phát sinh \`FindException\` khi gặp module không hợp lệ hay xung đột; ứng dụng thực tế nên bắt, ghi log chính xác và từ chối gói được kiểm tra.

### Tạo một explicit module mẫu

Tạo cấu trúc:

\`\`\`text
src/
└── demo.greeting/
    ├── module-info.java
    └── demo/
        └── greeting/
            └── Greeting.java
\`\`\`

Nội dung **\`src/demo.greeting/module-info.java\`**:

\`\`\`java
module demo.greeting {
    exports demo.greeting;
}
\`\`\`

Nội dung **\`src/demo.greeting/demo/greeting/Greeting.java\`**:

\`\`\`java
package demo.greeting;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Hello from plugin module";
    }
}
\`\`\`

Từ thư mục dự án, tạo \`plugins\` rồi chạy:

\`\`\`bash
mkdir plugins
javac -d mods/demo.greeting src/demo.greeting/module-info.java src/demo.greeting/demo/greeting/Greeting.java
jar --create --file plugins/demo.greeting.jar --module-version 1.0.0 -C mods/demo.greeting .
javac ModuleFinderDemo.java
java ModuleFinderDemo plugins
\`\`\`

Với **chỉ một JAR mẫu** trong thư mục, kết quả có dạng:

\`\`\`text
name=demo.greeting
version=1.0.0
automatic=false
location=file:///.../plugins/demo.greeting.jar
requires=[java.base]
provides=[]
\`\`\`

Dòng \`location\` phụ thuộc đường dẫn thực trên máy và có thể hiển thị khác theo hệ điều hành. Các dòng còn lại phản ánh descriptor của module mẫu. Trong module \`demo.greeting\`, \`java.base\` là dependency ngầm định của JPMS.

Lệnh \`javac\` ở trên phù hợp khi chạy từ thư mục chứa \`src\`; tạo các thư mục đầu ra sẽ do công cụ biên dịch/JAR xử lý khi điều kiện filesystem phù hợp. Với PowerShell hoặc môi trường không hỗ trợ \`mkdir\` như trên, tạo thư mục bằng lệnh tương ứng.

### Automatic module

Nếu đặt một JAR Java hợp lệ không chứa \`module-info.class\` vào cùng \`plugins\`, finder có thể tạo automatic module từ nó. Tên module được xác định từ \`Automatic-Module-Name\` hoặc suy ra từ tên file JAR theo quy tắc JPMS. Đừng lấy tên file tùy ý rồi mặc nhiên cho rằng đó là tên module chuẩn.

Ví dụ một manifest có:

\`\`\`text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacyplugin

\`\`\`

Thì module suy ra có tên \`com.example.legacyplugin\` (nếu JAR đáp ứng yêu cầu nhận diện). Dùng tên cố định giúp tránh việc đổi tên JAR hoặc thêm phiên bản vào filename làm thay đổi module name và phá vỡ \`requires\`.

## 5. Đọc và đánh giá ModuleDescriptor

\`ModuleDescriptor\` mô tả các đặc tính JPMS:

- \`name()\`: tên module, là khóa chọn roots cho resolver.
- \`version()\`: phiên bản module tùy chọn; không tự tạo chính sách nâng cấp hay bảo đảm tương thích.
- \`requires()\`: các module dependency và modifier như \`TRANSITIVE\`, \`STATIC\`.
- \`exports()\`: package công khai cho module khác theo quy tắc JPMS.
- \`opens()\`: package mở cho reflective access (khi có).
- \`uses()\`: tên service mà module tiêu thụ.
- \`provides()\`: service và lớp provider do module cung cấp.
- \`isAutomatic()\` và \`isOpen()\`: thông tin về kiểu descriptor.

Ví dụ plugin provider khai báo:

\`\`\`java
module demo.csvplugin {
    requires com.example.plugin.api;
    provides com.example.plugin.api.Exporter
        with demo.csv.CsvExporter;
}
\`\`\`

Đây là mẫu **module descriptor minh họa**, chỉ biên dịch khi các module, interface và class được nhắc tới tồn tại. Finder có thể phát hiện metadata \`provides\` mà chưa cần khởi tạo \`CsvExporter\`. Sau bước phân giải và tạo layer, \`ServiceLoader.load(layer, Exporter.class)\` có thể dùng để khám phá service provider trong layer theo hợp đồng.

**Không đồng nhất \`exports\` và \`provides\`:** \`exports\` điều khiển khả năng module khác truy cập public types trong package; \`provides\` công bố một triển khai service. Package chứa implementation có thể không cần export ra bên ngoài để được dùng thông qua cơ chế service.

## 6. Từ ModuleFinder tới phân giải dependency

Một danh sách module được tìm thấy chưa chắc tạo thành cấu hình hợp lệ. Java dùng \`Configuration\` và resolver để lập graph.

Ví dụ tích hợp:

\`\`\`java
// Đoạn tích hợp; module names, pluginFinder và parentLayer
// được ứng dụng xác định trước.
Configuration configuration =
        parentLayer.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("demo.greeting")
        );
\`\`\`

\`resolve\` tìm các module roots và phụ thuộc của chúng qua các finder và parent configuration theo quy tắc JPMS. Kết quả có thể thất bại nếu thiếu module được yêu cầu, có xung đột hoặc graph vi phạm điều kiện ràng buộc. \`ModuleFinder.of()\` không có tham số tạo finder rỗng; cách dùng finder trước/sau phải dựa trên chính sách của host.

Sau khi resolve, ứng dụng có thể định nghĩa layer:

\`\`\`java
// Đoạn tích hợp; configuration và parentLayer đã có.
ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
);
\`\`\`

**Cẩn thận về class loader:** lời gọi trên tạo loader phù hợp cho modules trong layer theo cơ chế của JPMS, dùng parent loader chỉ định. Không mặc định rằng một module layer đồng nghĩa sandbox hoặc mỗi plugin có class loader riêng. Nếu cần cô lập dependency/đổi phiên bản plugin, phải thiết kế layer, loader, API chung và lifecycle tương thích từ đầu.

Một kiểu tối thiểu của quy trình nhiều plugin:

1. Chọn roots từ danh sách module đã được phép kích hoạt.
2. Kiểm tra plugin module có \`requires\` đúng API chung.
3. Resolve trên parent layer và finder đã chọn, xử lý lỗi bằng lý do rõ ràng.
4. Tạo layer/loader rồi khám phá provider qua service API.
5. Đánh giá provider compatibility và khởi tạo với lifecycle kiểm soát.

Đừng đưa mọi module tìm thấy thành root nếu thư mục chứa cả dependency không phải plugin. Root nên xuất phát từ metadata/allowlist hoặc hợp đồng service do host xác định.

## 7. Lưu ý khi thư mục có nhiều JAR và module trùng tên

Một thư mục plugin có thể có hai bản phát hành cùng module name, chẳng hạn \`demo.greeting-1.0.jar\` và \`demo.greeting-2.0.jar\`. Đừng giả định \`ModuleFinder\` sẽ chọn “phiên bản mới nhất” theo chính sách ứng dụng. Finder cần ánh xạ tên module duy nhất để giải quyết; trường hợp module trùng hoặc mơ hồ có thể khiến \`FindException\` hoặc hành vi tìm thấy không đáp ứng mong muốn.

Host nên xây quy trình staging:

- Kiểm tra artifact và tên module trước khi đưa vào tập được phép.
- Chọn một bản version hợp lệ cho mỗi module name theo chính sách rõ ràng.
- Đặt module cần dùng vào thư mục snapshot/đường dẫn không bị thay đổi đồng thời.
- Tạo finder từ tập đường dẫn đã chuẩn hóa và chỉ resolve với tập được chọn.
- Báo lỗi khi thiếu dependency hoặc xung đột version, thay vì tự lấy JAR đầu tiên tình cờ xuất hiện.

\`ModuleDescriptor.version()\` là thông tin tùy chọn. JPMS resolution **không tự giải quyết version range kiểu Maven/Gradle** và không tự tải các thư viện thiếu từ repository. Việc chọn bản phát hành, kiểm tra tương thích và bố trí đường dẫn nằm ở hệ thống quản lý plugin/build/deployment của ứng dụng.

## 8. Plugin module mới không tự xuất hiện trong layer đang chạy

Giả sử host đã tạo một \`ModuleFinder\` từ \`plugins/\` rồi tạo \`ModuleLayer\`. Khi chép thêm JAR vào thư mục, **layer đã tạo không tự cập nhật**. Cần chủ động khám phá lại trạng thái thư mục, xây finder/cấu hình thích hợp và tạo một layer mới hoặc một cơ chế chuyển đổi khác được thiết kế riêng.

Lưu ý tính nhất quán:

- Đừng xóa/ghi đè JAR ngay khi class loader đang sử dụng.
- Tránh TOCTOU giữa lúc kiểm tra manifest/module descriptor và lúc resolve/load.
- Không dùng phiên bản cũ và mới lẫn nhau trong một request nếu contract không cho phép.
- Quản lý callback, thread, service instance và class loader để tránh giữ module/plugin cũ.
- Tùy mô hình layer và các tham chiếu còn sống, việc thu hồi lớp/module phụ thuộc khả năng garbage collection; không có lệnh JPMS đơn giản “unload module ngay lập tức”.

ModuleFinder phục vụ **khám phá snapshot**; hot reload là tính năng cấp hệ thống plugin với yêu cầu vòng đời riêng.

## 9. Bảo mật và độ tin cậy của metadata

Không được coi module tìm thấy trong thư mục là đáng tin chỉ vì có \`module-info.class\` hợp lệ. Metadata có thể khai báo tên, service hoặc dependency do nhà phát hành kiểm soát, nhưng nó không xác minh người phát hành.

Quy trình an toàn cần kết hợp:

- Nguồn artifact/allowlist đáng tin, quyền ghi thư mục chặt chẽ và kiểm tra integrity/chữ ký theo chính sách.
- Giới hạn kích thước file, số entry và tài nguyên phân tích JAR.
- Kiểm tra tên module, package, dependency và khả năng cung cấp service dự kiến.
- Bảo vệ đường dẫn/đối tượng file khỏi bị thay thế giữa kiểm tra và sử dụng.
- Không chạy bytecode plugin chưa được phê duyệt trong cùng JVM nếu không đáp ứng yêu cầu tin cậy.

JPMS cung cấp cấu trúc module, khả năng đọc module và kiểm soát truy cập ở mức ngôn ngữ/runtime. Nó **không phải biện pháp sandbox tin cậy** cho mã bên thứ ba độc hại. Khi yêu cầu cô lập quyền mạnh, cân nhắc process/container riêng và giao thức trao đổi rõ ràng.

## 10. Những lỗi thường gặp

- Gọi \`ModuleFinder.of(dir)\` rồi nghĩ module đã được nạp hoặc service tự kích hoạt.
- Dùng \`findAll()\` để lấy tất cả JAR như plugin mà không phân biệt module dependency.
- Coi automatic module và explicit module có cùng mức độ khai báo contract.
- Dựa vào thứ tự \`Set<ModuleReference>\` để chọn plugin/phiên bản.
- Quên rằng module path không quét đệ quy mọi nhánh thư mục.
- Giả định module descriptor phiên bản tự giải quyết dải tương thích.
- Đóng gói trùng module hoặc để thư mục plugin đổi trong lúc resolve.
- Không kiểm tra service \`provides\`, dependency API hoặc metadata tin cậy trước kích hoạt.
- Tưởng cập nhật file trong thư mục sẽ cập nhật \`ModuleLayer\` đã tạo.
- Tưởng module layer riêng hoàn toàn ngăn được mã không tin cậy tác động host.

## 11. Checklist thực hành

Trước khi sử dụng module tìm được từ một thư mục plugin:

1. **Xác định đường dẫn:** thư mục có thật và chứa các module/JAR theo layout dự kiến?
2. **Khám phá:** \`ModuleFinder.of(...)\` và \`findAll()\` có thành công không?
3. **Đọc descriptor:** tên, phiên bản, \`requires\`, \`uses\`, \`provides\` có hợp đồng rõ không?
4. **Chọn roots:** module nào là plugin thật, module nào chỉ là dependency?
5. **Kiểm tra xung đột:** duplicate name/version, thiếu API/module, automatic module có tên không ổn định?
6. **Kiểm tra tin cậy:** nguồn artifact, integrity, quyền truy cập, khả năng bị thay file?
7. **Resolve:** configuration được tạo không lỗi và dùng đúng parent layer/finder?
8. **Define layer:** loader/API chung được bố trí đúng, tránh class identity conflict?
9. **Kích hoạt:** chỉ tạo provider sau validation và có lifecycle, log, rollback.
10. **Cập nhật:** nếu hỗ trợ hot reload, có snapshot, drain và xử lý service cũ không?

**Ghi nhớ:** \`ModuleFinder\` trả lời câu hỏi **“có những module nào ở các đường dẫn này?”**. \`Configuration.resolve\` trả lời **“chúng có tạo được dependency graph hợp lệ không?”**. \`ModuleLayer\` và \`ServiceLoader\` mới giúp host đưa provider vào thực thi theo kiến trúc đã chọn.
