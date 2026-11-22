# FindException khi resolve module

Trong Java Platform Module System (JPMS), một ứng dụng modular chỉ có thể khởi chạy khi Java tìm được các module cần thiết và xây dựng được module graph hợp lệ. Nếu quá trình **tìm module** thất bại, ứng dụng có thể gặp `java.lang.module.FindException`. Lỗi thường xuất hiện khi chạy bằng `java -m`, gọi `Configuration.resolve(...)` hoặc `Configuration.resolveAndBind(...)`, hoặc khi `ModuleFinder` đọc một nguồn module không hợp lệ.

Ví dụ thông báo thường gặp:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

Thông báo này không có nghĩa JVM không thể tìm một class đơn lẻ. Nó cho biết **module resolution** không tìm được một named module mà module graph cần dùng, hoặc module finder gặp sự cố khi đọc và nhận diện module.

Bài học này trình bày cách xác định module bị thiếu, nguồn tìm kiếm thực tế, nguyên nhân của `FindException` và quy trình sửa lỗi không làm suy yếu cấu trúc JPMS.

## 1. FindException thuộc giai đoạn nào?

Một chương trình modular trải qua nhiều bước:

~~~text
module-info.java
       |
       v
  javac biên dịch
       |
       v
module-info.class và modular JAR
       |
       v
ModuleFinder tìm module
       |
       v
Configuration.resolve / resolveAndBind
       |
       v
Module graph hợp lệ
       |
       v
ModuleLayer hoặc boot layer
       |
       v
Class loading và chạy main
~~~

`FindException` liên quan chủ yếu tới bước **ModuleFinder** và **resolution**: không tìm được module theo tên, hoặc không thể đọc metadata module cần thiết từ nguồn cung cấp.

Nên phân biệt:

- **Không tìm được module:** thường thấy `FindException`.
- **Đã tìm thấy module nhưng module graph mâu thuẫn:** thường thấy `ResolutionException`.
- **Module graph đã resolve nhưng tạo layer không hợp lệ:** có thể gặp `LayerInstantiationException`.
- **Module đã tạo nhưng không tìm thấy class lúc thực thi:** có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError`.
- **Provider service lỗi khi được khởi tạo:** có thể gặp `ServiceConfigurationError`.

Tên exception giúp khoanh vùng giai đoạn đầu tiên cần kiểm tra; không nên sửa classpath, module descriptor và code nghiệp vụ cùng lúc.

## 2. Ví dụ tối thiểu: một dependency module bị thiếu

Giả sử có hai named module:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/CatalogService.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Descriptor của module thư viện:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Descriptor của ứng dụng:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Main class:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Biên dịch các module:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.catalog,com.example.app
~~~

Khi biên dịch thành công, output thường là:

~~~text
mods/
├── com.example.catalog/
│   ├── module-info.class
│   └── com/example/catalog/api/CatalogService.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Chạy với module path bao gồm cả hai module:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Trường hợp này cho phép resolver tìm cả module app lẫn catalog.

Nếu sau đó đóng gói hoặc triển khai **chỉ module app** mà bỏ module catalog, chạy app với module path thiếu catalog có thể báo:

~~~text
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

Tên sau `Module` là dependency không tìm được. Tên sau `required by` là module trực tiếp khai báo dependency cần thiết đó.

**Hướng sửa:** đưa đúng artifact của `com.example.catalog` vào module path hoặc cập nhật dependency/module name nếu descriptor đã thay đổi. Không thêm `--add-exports` hay `--add-opens` để xử lý việc module chưa hề được tìm thấy.

## 3. Thiếu root module và thiếu dependency khác nhau thế nào?

Có hai kiểu thông báo quan trọng.

**Root module không được tìm thấy:**

~~~text
java.lang.module.FindException:
Module com.example.app not found
~~~

Đây là trường hợp tên module được chỉ định trực tiếp làm root, chẳng hạn `-m com.example.app`, nhưng module finder không thấy module đó từ các nguồn hiện tại.

Kiểm tra:

- Module app đã được biên dịch hoặc đóng gói chưa?
- `--module-path` có trỏ đúng thư mục hoặc modular JAR không?
- Tên trong `-m` có khớp tên module thực tế không?
- Đường dẫn có bị sai do working directory hoặc quoting không?

**Dependency của một module không được tìm thấy:**

~~~text
java.lang.module.FindException:
Module com.example.catalog not found, required by com.example.app
~~~

Ở đây resolver đã tìm được `com.example.app` và đọc descriptor của nó, nhưng `requires com.example.catalog;` không thể được thỏa mãn.

Kiểm tra module catalog trên module path trước khi sửa module app. Module được yêu cầu có thể nằm trong một JAR khác, một thư mục exploded module hoặc module runtime image của JDK.

Lưu ý: thông báo lỗi chỉ nêu mắt xích đang thiếu tại thời điểm resolver phát hiện. Một graph có thể thiếu nhiều module; sau khi sửa lỗi đầu tiên, resolver có thể báo lỗi kế tiếp.

## 4. Module path là nguồn đầu tiên cần đối chiếu

Cú pháp chạy named module:

~~~bash
java --module-path <module-path> \
     -m <module-name>/<main-class>
~~~

Dạng ngắn:

~~~bash
java -p <module-path> \
     -m <module-name>/<main-class>
~~~

Trên Linux/macOS, nhiều phần tử đường dẫn thường được phân cách bằng dấu hai chấm:

~~~bash
java --module-path "mods:lib:plugins" \
     -m com.example.app/com.example.app.Main
~~~

Trên Windows, đường dẫn được phân cách bằng dấu chấm phẩy:

~~~powershell
java --module-path "mods;lib;plugins" -m com.example.app/com.example.app.Main
~~~

Những lỗi cấu hình phổ biến:

1. Trỏ tới thư mục không tồn tại.
2. Trỏ nhầm sang source directory thay vì output chứa module đã biên dịch.
3. Chỉ thêm thư mục của app mà quên dependency.
4. Đặt JAR trên `--class-path` trong khi module khác khai báo `requires` tới nó.
5. Dùng dấu phân cách path không đúng hệ điều hành.
6. Chạy lệnh từ working directory khác nên relative path không còn đúng.
7. CI và IDE dùng hai module path khác nhau.

**Module path không phải classpath.** JAR trên classpath thuộc unnamed module; nó không tự trở thành named module có thể được tham chiếu bằng `requires com.example.catalog;`.

## 5. Kiểm tra module name thực tế

Tên file JAR không nhất thiết là tên module.

Ví dụ:

~~~text
lib/
├── catalog-utils-2.4.jar
└── catalog-api-1.0.jar
~~~

Một JAR explicit module có tên được khai báo trong `module-info.class`. Một JAR không có descriptor, khi được đặt trên module path, có thể trở thành **automatic module**; tên automatic module có thể đến từ `Automatic-Module-Name` trong manifest hoặc được suy ra từ tên file.

Dùng công cụ JDK để kiểm tra:

~~~bash
jar --describe-module --file lib/catalog-utils-2.4.jar
~~~

Kết quả có thể cho biết:

~~~text
com.example.catalog
requires java.base mandated
exports com.example.catalog.api
~~~

Nếu tên thực tế là `catalog.utils` nhưng descriptor của app yêu cầu `com.example.catalog`, resolver sẽ không coi hai tên là cùng một module.

Để xem nội dung JAR:

~~~bash
jar --list --file lib/catalog-utils-2.4.jar
~~~

Với explicit modular JAR, cần kiểm tra `module-info.class` có tồn tại ở vị trí phù hợp. Với automatic module, cần kiểm tra tên module suy ra có đúng với tên trong `requires` không.

Không nên sửa tên JAR ngẫu nhiên và kỳ vọng luôn sửa được dependency. Đối với explicit module, tên nằm trong descriptor, không phụ thuộc tên file.

## 6. ModuleFinder: kiểm tra khả năng tìm module trước khi resolve

Khi ứng dụng tạo module layer động, ta thường bắt đầu từ:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));
~~~

Có thể hỏi finder có nhận diện được một module cụ thể không:

~~~java
Optional<ModuleReference> reference =
    finder.find("com.example.catalog");

System.out.println("Found: " + reference.isPresent());
~~~

Nếu `reference.isEmpty()`, module đó không được finder hiện tại nhận diện dưới tên yêu cầu.

Có thể liệt kê các module được nhận diện:

~~~java
finder.findAll().stream()
    .map(ref -> ref.descriptor().name())
    .sorted()
    .forEach(System.out::println);
~~~

Cần imports:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Optional;
~~~

**Quan trọng:** `find` và `findAll` cũng có thể ném `FindException` nếu việc đọc nguồn module bị lỗi. Vì vậy, không phải trường hợp nào cũng chỉ nhận `Optional.empty()`; đôi khi chính finder không thể diễn giải artifact trong thư mục.

Ví dụ chẩn đoán có bắt exception:

~~~java
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

public final class InspectModules {
    public static void main(String[] args) {
        ModuleFinder finder =
            ModuleFinder.of(Path.of("plugins"));

        try {
            finder.findAll().stream()
                .map(ref -> ref.descriptor().name())
                .sorted()
                .forEach(System.out::println);
        } catch (FindException ex) {
            System.err.println(
                "Cannot inspect module source: " + ex.getMessage());
            ex.printStackTrace();
        }
    }
}
~~~

Class này giúp tách hai vấn đề: **finder không thể đọc nguồn** và **resolver tìm được nguồn nhưng thiếu dependency**.

## 7. Configuration.resolve và FindException

Khi xây dựng custom ModuleLayer, ví dụ:

~~~java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration parent =
    ModuleLayer.boot().configuration();

Configuration configuration;
try {
    configuration = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );
} catch (FindException ex) {
    System.err.println(
        "Module lookup failed: " + ex.getMessage());
    throw ex;
}
~~~

Các tham số cần hiểu:

- `finder` đầu tiên là nguồn tìm module trong nhóm ưu tiên trước parent.
- `parent` là configuration đã có ở layer cha.
- `ModuleFinder.of()` là finder rỗng dùng cho nguồn tìm kiếm sau parent.
- `Set.of("com.example.plugin")` là tập **root module** cần resolve.

Nếu root module hoặc một dependency bắt buộc không có trong tập module có thể quan sát từ các nguồn này, `FindException` có thể được ném.

Đừng chỉ kiểm tra `finder.find("com.example.plugin")` rồi kết luận mọi dependency đã đủ. Root có thể tồn tại nhưng `requires` của nó, hoặc `requires` của dependency bắc cầu, vẫn không resolve được.

## 8. Resolve thành công không đồng nghĩa đã tạo ModuleLayer

Quy trình dynamic module loading thường có hai giai đoạn:

~~~java
Configuration configuration =
    ModuleLayer.boot().configuration().resolve(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

Giai đoạn đầu tạo **configuration** đã resolve. Giai đoạn sau định nghĩa các module runtime và gắn class loader.

Nếu lỗi xuất hiện trong `resolve`, việc kiểm tra logic tạo class loader hoặc API trên `ModuleLayer` thường chưa giúp xác định nguyên nhân chính. Trước tiên, hãy đảm bảo module graph đã được resolver chấp nhận.

Ngược lại, nếu `resolve` thành công nhưng `defineModulesWithOneLoader` thất bại, cần xem nguyên nhân trong giai đoạn layer definition thay vì tự động coi đó là `FindException`.

## 9. Đọc dependency từ module descriptor

Một cách chẩn đoán hữu ích là in các directive `requires` của module tìm được:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("mods"));

finder.find("com.example.app").ifPresent(ref -> {
    var descriptor = ref.descriptor();

    System.out.println("Module: " + descriptor.name());
    descriptor.requires().forEach(req -> {
        System.out.println(
            "requires " + req.name() + " " + req.modifiers());
    });
});
~~~

Những dependency có thể là:

- `requires com.example.catalog;`: dependency thông thường.
- `requires transitive com.example.api;`: dependency được truyền tiếp về readability theo quy tắc JPMS.
- `requires static com.example.optional;`: dependency tại compile-time, nhưng không nhất thiết phải hiện diện khi chạy.

Với `requires static`, cần hiểu đúng: dependency có thể vắng mặt trong một lần resolution runtime. Không nên ép thêm module tùy chọn chỉ để loại bỏ một lỗi khác khi descriptor không thật sự yêu cầu sự hiện diện của nó. Tuy nhiên, nếu ứng dụng gọi class của optional dependency khi nó không được cung cấp, lỗi class loading vẫn có thể xảy ra ở giai đoạn sau.

Nếu `requires transitive` của module thư viện kéo theo một dependency thiếu, thông báo `required by` có thể chỉ tới module thư viện chứ không nhất thiết root app. Hãy lần theo chuỗi dependency thực tế thay vì chỉ xem module root.

## 10. Kiểm tra artifact trên module path

Cấu trúc triển khai thường gặp:

~~~text
deployment/
├── modules/
│   ├── com.example.app.jar
│   ├── com.example.catalog.jar
│   └── com.example.logging.jar
└── start.sh
~~~

Nếu start script trỏ tới `deployment/modules` khi working directory không phải `deployment`, relative path có thể được diễn giải sai.

Trên Linux/macOS, có thể kiểm tra:

~~~bash
pwd
ls -la modules
java --module-path modules \
     -m com.example.app/com.example.app.Main
~~~

Trong PowerShell:

~~~powershell
Get-Location
Get-ChildItem .\modules
java --module-path modules -m com.example.app/com.example.app.Main
~~~

Với JAR nghi ngờ:

~~~bash
jar --describe-module --file modules/com.example.catalog.jar
jar --list --file modules/com.example.catalog.jar
~~~

Hãy xác nhận:

1. File JAR thực sự tồn tại ở vị trí mà process nhìn thấy.
2. File không rỗng, bị cắt cụt hoặc hỏng.
3. Descriptor chứa đúng module name.
4. JAR cung cấp đúng module version/artifact dự kiến.
5. Dependency bắc cầu của nó cũng có mặt hoặc ở parent configuration.

Nếu dùng exploded module, kiểm tra thư mục có `module-info.class` và class files bên dưới đúng cấu trúc module.

## 11. Lỗi đọc module descriptor và modular JAR

`FindException` không chỉ xuất hiện khi thiếu một tên module. Nó cũng có thể xuất hiện khi module finder gặp một artifact mà nó không thể đọc hoặc diễn giải như module hợp lệ.

Một số tình huống:

- `module-info.class` bị hỏng hoặc descriptor không hợp lệ.
- Modular JAR bị cắt cụt, không đọc được hoặc không phải nội dung ZIP hợp lệ.
- Metadata module không phù hợp với runtime/tool đang dùng.
- Module path trỏ tới file hoặc thư mục không có nội dung module hợp lệ theo quy tắc mà finder kỳ vọng.
- Có sự cố I/O hoặc quyền đọc đối với nguồn module.

Thông báo thường có thể chứa phần như:

~~~text
java.lang.module.FindException:
Error reading module: ... 
~~~

Với một số nguyên nhân descriptor, exception gốc có thể được lồng trong cause chain. Do đó, hãy giữ stack trace và các `Caused by` thay vì chỉ trích dòng đầu tiên.

Ví dụ:

~~~java
try {
    ModuleFinder finder =
        ModuleFinder.of(Path.of("plugins"));

    finder.findAll();
} catch (FindException ex) {
    System.err.println(ex.getMessage());

    Throwable cause = ex.getCause();
    while (cause != null) {
        System.err.println("Caused by: " + cause);
        cause = cause.getCause();
    }
}
~~~

Không nên chỉ thêm một JAR bất kỳ cùng tên vào module path khi bản thực tế bị hỏng. Hãy sửa nguồn artifact, xác minh checksum hoặc build lại modular JAR từ input đáng tin cậy.

## 12. Version JDK và tính tương thích module descriptor

Nếu JAR được build bằng JDK mới hơn runtime đang sử dụng, có thể xuất hiện lỗi đọc class/descriptor hoặc lỗi định dạng class ở các giai đoạn khác nhau. Không phải mọi lỗi version đều là `FindException`, nhưng đây là một yếu tố cần kiểm tra khi module lookup bất thường.

Kiểm tra:

~~~bash
java -version
javac -version
jar --describe-module --file modules/com.example.catalog.jar
~~~

Trong hệ thống CI/CD, nên cố định Java toolchain/baseline phù hợp cho build và runtime. Không trộn artifact được build từ cấu hình JDK khác nhau mà không biết mức bytecode và API tối thiểu của chúng.

Nếu artifact dùng multi-release JAR, tên module và descriptor có thể phụ thuộc nội dung phù hợp với phiên bản runtime. Cần dùng đúng công cụ JDK và kiểm tra output mà môi trường triển khai thật sự nhìn thấy.

## 13. Automatic module và tên suy ra

Một JAR trên module path nhưng không có `module-info.class` có thể trở thành automatic module.

Ví dụ JAR:

~~~text
shared-utils-3.2.jar
~~~

Tên module automatic có thể được suy ra từ tên file (theo quy tắc của Java) hoặc lấy từ manifest `Automatic-Module-Name`.

Nếu app khai báo:

~~~java
module com.example.app {
    requires com.example.shared;
}
~~~

nhưng JAR trên module path lại có automatic module name khác, resolver sẽ không nhận diện dependency `com.example.shared` từ JAR đó.

Lệnh kiểm tra:

~~~bash
jar --describe-module --file lib/shared-utils-3.2.jar
~~~

Nếu kết quả báo tên khác, hãy chọn cách sửa phù hợp:

- Dùng đúng module name được artifact công bố nếu thiết kế chấp nhận automatic module.
- Chuyển thư viện thành explicit module có descriptor ổn định.
- Dùng artifact/version phù hợp có `Automatic-Module-Name` được định nghĩa nhất quán.
- Tránh đổi tên JAR tạm thời để giải quyết lỗi nếu điều đó tạo hợp đồng dependency không ổn định.

Khi migration từ classpath sang module path, quản lý module names là một phần quan trọng của thiết kế dependency.

## 14. --add-modules không tạo ra module bị thiếu

Tùy chọn `--add-modules` bổ sung module vào **root set** của resolution:

~~~bash
java --module-path mods \
     --add-modules com.example.catalog \
     -m com.example.app/com.example.app.Main
~~~

Nó không tải JAR từ Internet, không tự copy module dependency và không biến một tên không tồn tại thành module thật.

Nếu `com.example.catalog` không được finder nhìn thấy, chỉ thêm `--add-modules com.example.catalog` có thể làm lỗi xuất hiện sớm hơn hoặc cho ra thông báo thiếu root module.

Tương tự:

- `--add-reads` thay đổi readability trong hoàn cảnh phù hợp, không tạo module source mới.
- `--add-exports` mở quyền truy cập package, không tìm hoặc khôi phục JAR thiếu.
- `--add-opens` liên quan reflection sâu, không liên quan module lookup.
- `--module-path` mới là nơi cần kiểm tra khi resolver không thể tìm module artifact.

Chỉ sử dụng `--add-modules` khi module có thể tìm được và bạn thực sự cần bổ sung root cho lần resolve.

## 15. Service binding có thể làm lộ dependency thiếu

Khi ứng dụng sử dụng service trong JPMS, `Configuration.resolveAndBind(...)` có thể bổ sung provider module ngoài các dependency thông thường.

Ví dụ:

~~~java
Configuration configuration =
    ModuleLayer.boot().configuration().resolveAndBind(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(),
        Set.of("com.example.app")
    );
~~~

Một module app khai báo:

~~~java
module com.example.app {
    requires com.example.spi;

    uses com.example.spi.Converter;
}
~~~

Một module provider có thể khai báo:

~~~java
module com.example.provider.json {
    requires com.example.spi;
    requires com.example.json.core;

    provides com.example.spi.Converter
        with com.example.provider.json.JsonConverter;
}
~~~

Nếu service binding đưa provider `com.example.provider.json` vào configuration nhưng `com.example.json.core` không tìm được, quá trình resolve có thể báo `FindException` liên quan dependency của provider.

Vì vậy, khi lỗi chỉ xảy ra với `resolveAndBind` mà không xảy ra với `resolve`, hãy kiểm tra **các provider module được phát hiện** và toàn bộ dependency của chúng.

Không nên vô hiệu service binding một cách mù quáng nếu ứng dụng cần service. Thay vào đó, làm rõ module provider nào được đưa vào graph và bảo đảm các artifact của provider đầy đủ, tương thích.

## 16. Custom ModuleFinder và nguồn module không nằm trên filesystem

JPMS cho phép ứng dụng cung cấp `ModuleFinder` tùy biến, ví dụ đọc module từ repository hoặc bộ nhớ. Một custom finder cần trả về `ModuleReference` có descriptor hợp lệ và khả năng đọc nội dung module.

Khi ứng dụng dùng custom finder:

- `find(name)` cần trả về đúng module theo tên descriptor.
- `findAll()` cần công bố tập module khả dụng nhất quán.
- `ModuleReference.descriptor()` cần phản ánh đúng dependency và package thực tế.
- `ModuleReference.open()` phải cung cấp `ModuleReader` đọc được class và resources.
- Cần có chính sách version/tenant để tránh thay đổi tập module giữa các bước resolve.

Nếu repository có artifact nhưng finder trả về `Optional.empty()` vì mapping tên sai, resolver vẫn coi module là không tìm thấy. Nếu metadata descriptor bị lỗi, finder có thể ném `FindException` trước khi tạo configuration.

Đừng chỉ debug filesystem nếu ứng dụng sử dụng một custom source. Hãy quan sát chính logic của finder và danh sách module mà nó công bố.

## 17. FindException khác ResolutionException ra sao?

Hai exception này thường bị nhầm:

| Loại lỗi | Giai đoạn chủ yếu | Ví dụ |
|---|---|---|
| `FindException` | Tìm/đọc module | Root không tồn tại, dependency không tìm được, không đọc được descriptor |
| `ResolutionException` | Kiểm tra module graph đã tìm thấy | Module graph xung đột do nhiều module cung cấp package không tương thích |
| `LayerInstantiationException` | Định nghĩa runtime layer | Không thể áp dụng module configuration vào layer/loader |
| `ClassNotFoundException` | Nạp class theo tên | Loader không tìm thấy một class |
| `NoClassDefFoundError` | Link/load class lúc dùng | Class cần thiết không thể được định nghĩa hoặc nạp |
| `IllegalAccessError` | Runtime access check | Truy cập tới class/member bị chặn bởi Java/JPMS rules |

Ví dụ hai module đã có mặt đầy đủ nhưng đều khiến cùng một consumer đọc package trùng nhau, lỗi đó thiên về **module graph conflict**, không phải thiếu module artifact. Khi ấy, tăng `--module-path` bằng cách thêm nhiều JAR chưa chắc giúp; thậm chí làm xung đột phức tạp hơn.

Ngược lại, nếu thông báo là `Module X not found`, trước tiên hãy tìm đúng artifact có module name X.

## 18. Module path, classpath và các giới hạn root set

Một số tùy chọn runtime làm thay đổi tập module mà resolver có thể quan sát:

- `--module-path`: nơi tìm application modules.
- `--upgrade-module-path`: nơi cung cấp các module nâng cấp nếu môi trường cho phép.
- `--limit-modules`: giới hạn tập module có thể quan sát, có thể khiến module cần thiết trở nên không khả dụng.
- `--add-modules`: bổ sung roots mà resolver phải xét.
- `-m`: chỉ định named root module được khởi chạy.

Nếu một module có trên filesystem nhưng bị loại khỏi tập module quan sát do cách thiết lập giới hạn hoặc nguồn tìm kiếm, lỗi vẫn có thể là không tìm thấy từ góc nhìn resolver.

Ví dụ, khi debug `--limit-modules`, hãy thử một cấu hình kiểm tra không có giới hạn đó trong môi trường test để xác định liệu giới hạn đang ẩn dependency hay không. Không nên xóa vĩnh viễn chính sách giới hạn production nếu chưa hiểu mục tiêu vận hành hoặc bảo mật của nó.

Hãy phân biệt **module artifact tồn tại trên đĩa** với **module name được finder chọn và hiện diện trong lần resolution cụ thể**. Hai điều này không luôn tương đương.

## 19. JDK tools phục vụ chẩn đoán

Những lệnh hữu ích:

~~~bash
# Kiểm tra phiên bản Java
java -version
javac -version

# Kiểm tra descriptor và tên module
jar --describe-module --file lib/com.example.catalog.jar

# Kiểm tra class và module-info.class
jar --list --file lib/com.example.catalog.jar

# Liệt kê module của runtime image
java --list-modules

# In thông tin quá trình resolution khi khởi chạy
java --show-module-resolution \
     --module-path "mods:lib" \
     -m com.example.app/com.example.app.Main
~~~

Nếu muốn xem dependency giữa các module đã build, có thể dùng `jdeps` với module path phù hợp:

~~~bash
jdeps --module-path "mods:lib" \
      --check com.example.app
~~~

Các lệnh giúp xác định những thông tin khác nhau:

- `jar --describe-module`: artifact tự nhận có tên module gì và khai báo gì.
- `jar --list`: artifact có thực sự chứa class files/descriptor không.
- `java --list-modules`: runtime image hiện có module JDK nào.
- `--show-module-resolution`: giúp quan sát graph được launcher resolve nếu tiến trình tới được phần báo cáo phù hợp.
- `jdeps`: hỗ trợ kiểm tra dependency/đồ thị module ở mức artifact.

Nếu command line dài hoặc do build tool sinh ra, hãy log **lệnh/argument list thực tế** thay vì chỉ tin vào file cấu hình IDE hoặc Gradle/Maven.

## 20. Quy trình xử lý FindException theo thứ tự

Khi gặp `FindException`, thực hiện theo các bước sau:

1. **Đọc nguyên thông báo.** Xác định tên module sau `Module ... not found` và module ở phần `required by` nếu có.
2. **Ghi lại lệnh đang chạy.** Bao gồm Java version, working directory, module path, main module, `--add-modules` và các option giới hạn.
3. **Kiểm tra artifact thực tế.** Tệp/thư mục có ở đúng nơi JVM chạy không?
4. **Đọc module name bằng JDK tool.** Dùng `jar --describe-module`; không suy đoán theo tên file.
5. **Kiểm tra descriptor của module yêu cầu.** Directive `requires`, `requires transitive` hoặc `requires static` có đúng tên và ngữ nghĩa không?
6. **Kiểm tra dependency bắc cầu.** Module cần tìm có phụ thuộc vào module khác chưa được cung cấp không?
7. **Kiểm tra custom finder nếu có.** `find` và `findAll` có thấy đúng module name không?
8. **Nếu báo error reading module**, kiểm tra JAR, descriptor, I/O, checksum và cause chain.
9. **Nếu chỉ lỗi khi bind services**, kiểm tra provider module mới được resolve và dependency của chúng.
10. **Chạy lại với module path tối thiểu, tường minh.** Không thêm flags mở access không liên quan.
11. **Kiểm tra cả build và runtime.** Một module có thể có lúc compile nhưng thiếu ở môi trường deploy.
12. **Xác nhận module graph.** Chỉ sau khi resolution thành công mới debug class loading hoặc truy cập package.

Quy trình có thứ tự giúp tránh sửa sai tầng, chẳng hạn thay đổi `exports` khi artifact đang thiếu hoàn toàn.

## 21. Các trường hợp thực tế

### 21.1. Chạy từ IDE được nhưng chạy JAR thất bại

IDE có thể tự thêm dependency lên module path khi chạy. Script triển khai chỉ copy một modular JAR nên thiếu những dependency trực tiếp hoặc bắc cầu.

Cách xử lý là xem JVM args do IDE tạo, đối chiếu với command line production và đóng gói đầy đủ các module cần thiết.

### 21.2. Refactor tên module nhưng quên cập nhật requires

Trước đây:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Sau refactor thành:

~~~java
module com.example.catalog.core {
    exports com.example.catalog.api;
}
~~~

Nhưng app vẫn có:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Dù artifact mới tồn tại, resolver không có module tên cũ `com.example.catalog`. Cần cập nhật descriptor app và các dependency tương ứng hoặc giữ lại một module compatibility hợp lệ nếu chiến lược migration đòi hỏi.

### 21.3. Thư viện được đặt trên classpath

App yêu cầu named module `com.example.catalog` nhưng người triển khai chạy:

~~~bash
java -cp "lib/*" \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Nếu catalog JAR chỉ nằm trên classpath, resolver không thể thỏa mãn `requires com.example.catalog;` bằng JAR đó. Chuyển đúng artifact sang module path hoặc điều chỉnh kiến trúc phụ thuộc phù hợp; không mong classpath cung cấp named module.

### 21.4. Plugin tồn tại nhưng không nằm trong ModuleFinder

Ứng dụng dùng:

~~~java
ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins/active"));
~~~

Trong khi artifact được triển khai tại `plugins/available`. Dù JAR nằm trên đĩa, finder không tìm thấy nó từ thư mục `active`.

Đổi đường dẫn finder đúng nguồn dự kiến, hoặc có chính sách active plugin rõ ràng. Không sửa tên module chỉ vì cấu hình thư mục triển khai sai.

### 21.5. Provider service kéo theo một dependency mới

Một provider được thêm vào thư mục plugins có `requires com.example.codec;`. Nếu repository chưa triển khai module codec, `resolveAndBind` có thể thất bại dù root app vẫn không đổi. Kiểm tra dependency của provider và phạm vi tìm kiếm module.

## 22. Những cách xử lý sai thường gặp

**Thêm `--add-exports` để sửa module not found.** Export chỉ ảnh hưởng quyền truy cập package; không làm module xuất hiện.

**Thêm `--add-modules` cho một module không tồn tại.** Lựa chọn root không tạo ra artifact. Trước tiên phải đưa đúng module vào phạm vi finder.

**Chỉ sửa tên JAR.** Với explicit module, tên module đến từ descriptor; đổi filename không thay đổi tên module.

**Chuyển toàn bộ JAR sang classpath.** Điều này có thể loại bỏ module graph dự kiến và thay đổi mô hình encapsulation, không phải cách sửa tối thiểu khi dự án được thiết kế theo JPMS.

**Bỏ dòng `requires` để runtime hết báo lỗi.** Nếu app thật sự phụ thuộc API của module bị thiếu, xóa dependency có thể tạo lỗi compile hoặc runtime khác. Chỉ sửa descriptor khi quan hệ dependency không còn hợp lệ trong kiến trúc.

**Nuốt FindException rồi tiếp tục chạy plugin như thể đã resolve.** Nếu configuration chưa được tạo thành công, việc tiếp tục định nghĩa layer hoặc gọi service là không đáng tin cậy. Bắt exception để báo lỗi giàu ngữ cảnh rồi dừng hoặc chọn fallback đã được thiết kế.

**Nhầm FindException với ResolutionException.** Nếu module đã tìm được nhưng graph xung đột, cần phân tích package/readability và lựa chọn version chứ không chỉ kiểm tra JAR có tồn tại hay không.

**Sửa mọi cấu hình cùng lúc.** Điều chỉnh một biến theo từng bước: working directory, module path, module names, dependency, provider finder. Cách này giúp xác định nguyên nhân chính xác.

## 23. Checklist tự kiểm tra

1. Module root được chỉ định trong `-m` có nằm trên module path không?
2. Tên module trong descriptor có đúng với tên mà lệnh `java` và `requires` sử dụng không?
3. Module thiếu là root hay dependency của module khác?
4. Có `requires transitive` kéo theo dependency bắc cầu không?
5. Có đang nhầm `requires static` với dependency runtime bắt buộc không?
6. JAR là explicit module hay automatic module?
7. Có module nào chỉ được đặt trên classpath nên resolver không nhìn thấy không?
8. Java version ở máy build và runtime có tương thích với artifact không?
9. ModuleFinder có đọc được nguồn mà không ném FindException không?
10. Trong custom finder, tên module có trùng với descriptor.name() không?
11. Có `--limit-modules` hoặc cấu hình finder nào đang ẩn module cần thiết không?
12. `resolveAndBind` có đưa provider mới và dependency mới vào graph không?
13. Có giữ đủ stack trace và `Caused by` khi báo lỗi không?
14. Đã phân biệt lỗi finding với graph conflict và class loading chưa?
15. Lệnh triển khai production có đầy đủ module path mà IDE/CI đã dùng khi build không?

## 24. Kết luận

`java.lang.module.FindException` là tín hiệu rằng Java không thể **tìm hoặc đọc một module cần thiết** trong quá trình xây dựng module graph. Cách xử lý đúng không phải là mở rộng exports, chỉnh reflection hay thử nhiều JVM flags một cách ngẫu nhiên. Hãy bắt đầu từ **tên module trong thông báo**, tìm module bằng `ModuleFinder` hoặc `jar --describe-module`, kiểm tra module path, dependency trực tiếp/bắc cầu và trạng thái artifact. Nếu dùng dynamic `ModuleLayer` hoặc service binding, hãy kiểm tra cả finder và các provider được resolve.

Khi module được tìm thấy và descriptor hợp lệ, quá trình resolution mới có thể tiếp tục kiểm tra tính nhất quán của module graph. Phân biệt rõ những giai đoạn đó giúp sửa lỗi đúng nguyên nhân, bảo toàn cấu trúc module và vận hành ứng dụng JPMS đáng tin cậy.
