# ModuleNotFoundException và module path sai

Trong Java Platform Module System (JPMS), một lỗi phổ biến khi biên dịch hoặc chạy ứng dụng modular là **“module not found”**: chương trình yêu cầu một named module nhưng công cụ không tìm thấy module đó trong các nguồn module đang xét. Lỗi có thể xảy ra vì `--module-path` sai, JAR được đặt trên classpath thay vì module path, tên trong `requires` khác tên module thực tế, hoặc cấu hình runtime không giống cấu hình lúc compile.

**Lưu ý về tên lỗi:** `ModuleNotFoundException` thường là cách gọi mô tả hoặc tên exception tự định nghĩa của thư viện; đây **không phải tên một exception chuẩn của JPMS trong `java.base`**. Trong Java chuẩn, khi chạy ứng dụng modular bạn thường thấy `java.lang.module.FindException` kèm thông điệp `Module ... not found`. Khi dùng `javac`, thông báo thường là `error: module not found: ...`, không nhất thiết là exception được ném ra từ chương trình.

Bài này tập trung vào cách xác định **module nào thực sự thiếu, thiếu ở giai đoạn nào, và đường dẫn nào phải sửa**, thay vì thêm các tùy chọn JVM theo cảm tính.

## 1. Phân biệt module name, package name và tên JAR

Ba tên sau không nhất thiết giống nhau:

    JAR filename: money-utils-2.3.0.jar
    Module name:  com.example.money
    Package:      com.example.money.api

Descriptor của thư viện có thể khai báo:

    module com.example.money {
        exports com.example.money.api;
    }

Ứng dụng cần thư viện này thì khai báo:

    module com.example.app {
        requires com.example.money;
    }

`requires` nhận **module name**, không nhận tên file JAR, Maven artifactId hay package name. Ví dụ sau là sai nếu không tồn tại module có đúng tên `money-utils`:

    module com.example.app {
        requires money.utils;
    }

Dấu gạch nối trong filename thường không được dùng trực tiếp trong tên module; với automatic module, JDK có quy tắc suy ra tên riêng. Luôn xác định tên thực tế bằng descriptor thay vì đoán từ artifact filename.

## 2. Lỗi xảy ra ở compile time hay runtime?

| Tình huống | Thông báo thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| `javac` không tìm thấy module trong `requires` | `error: module not found: com.example.money` | Module path của compiler, tên module |
| Java launcher không tìm thấy module gốc hoặc dependency | `java.lang.module.FindException: Module ... not found` | Module path của launcher, root module và dependency |
| Chương trình gọi `ModuleFinder.find(name)` nhưng không có module | `Optional.empty()` | Finder đã trỏ vào đúng thư mục/JAR chưa? |
| Module có nhưng package chưa export | `package ... is not visible`, hoặc lỗi access tại runtime | `requires`, `exports`, module readability |
| Class không tìm thấy sau khi module đã resolve | `ClassNotFoundException` hoặc `NoClassDefFoundError` | Class loader, class/package thật, classpath/module path |

Không gộp tất cả thành `ModuleNotFoundException`. Ví dụ, `ClassNotFoundException` nói về **class**, còn `FindException` trong quá trình resolve thường nói về **module**.

## 3. Module path là gì?

**Module path** là nguồn các module mà compiler, launcher hoặc API `ModuleFinder` có thể quan sát. Nó có thể chứa:

- Một thư mục chứa các **modular JAR**.
- Một thư mục chứa nhiều **exploded modules** (thư mục module đã biên dịch, mỗi module có `module-info.class`).
- Đường dẫn trực tiếp tới một modular JAR hoặc automatic-module JAR, tùy cách dùng công cụ.
- Nhiều vị trí được phân cách theo quy tắc path separator của hệ điều hành.

Ví dụ cấu trúc:

    project/
      libs/
        money-utils-2.3.0.jar
      out/
        com.example.app/
          module-info.class
          com/example/app/Main.class

Lệnh chạy có thể là:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

Trên **Windows**, dấu phân cách đường dẫn là `;`; trên **Linux/macOS**, dùng `:`:

    java --module-path "out:libs" -m com.example.app/com.example.app.Main

Tùy hệ điều hành và shell, hãy đặt toàn bộ module path trong dấu ngoặc kép nếu có khoảng trắng hoặc dấu phân cách dễ bị shell diễn giải.

`--module-path` (viết ngắn `-p`) **khác** `--class-path` (hoặc `-cp`). JAR nằm trên classpath thường được nạp vào unnamed module, không trở thành named module có thể được nhắc đến bằng `requires`.

## 4. Ví dụ dự án hai module chạy đúng

Giả sử có hai source modules:

    src/
      com.example.money/
        module-info.java
        com/example/money/api/Money.java
      com.example.app/
        module-info.java
        com/example/app/Main.java

`src/com.example.money/module-info.java`:

    module com.example.money {
        exports com.example.money.api;
    }

`src/com.example.money/com/example/money/api/Money.java`:

    package com.example.money.api;

    public final class Money {
        private Money() {}

        public static String currency() {
            return "VND";
        }
    }

`src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.money;
    }

`src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.money.api.Money;

    public class Main {
        public static void main(String[] args) {
            System.out.println(Money.currency());
        }
    }

Biên dịch các module từ thư mục dự án:

    javac --module-source-path src -d out -m com.example.money,com.example.app

Chạy ứng dụng:

    java --module-path out -m com.example.app/com.example.app.Main

Kết quả:

    VND

Vì `out` chứa hai exploded modules, Java launcher có thể tìm `com.example.app` và dependency `com.example.money`.

Nếu lệnh chạy dùng đường dẫn sai:

    java --module-path wrong-directory -m com.example.app/com.example.app.Main

launcher không tìm được module gốc và có thể báo:

    java.lang.module.FindException:
        Module com.example.app not found

Nếu chỉ cung cấp module app mà thiếu module money, launcher có thể báo thiếu module phụ thuộc:

    java.lang.module.FindException:
        Module com.example.money not found, required by com.example.app

Hai thông báo cùng nhóm nhưng chỉ ra hai vị trí cần kiểm tra khác nhau: **module gốc** hoặc **dependency**.

## 5. Vì sao compile thành công nhưng chạy thất bại?

Compiler và Java launcher là hai công cụ có cấu hình riêng. Ví dụ compile dùng:

    javac --module-path libs -d out ...

nhưng runtime lại chạy:

    java --module-path out -m com.example.app/com.example.app.Main

Nếu `com.example.money` chỉ nằm trong `libs` mà không có trong `out`, runtime không có đủ nguồn module để resolve dependency. Việc class files đã được biên dịch trước đó không làm thư viện xuất hiện trong module path của launcher.

Một lỗi quen thuộc khác:

- IDE cấu hình module path tự động khi chạy trong IDE.
- Script shell chỉ đưa application JAR vào runtime path.
- CI hoặc Docker image bỏ sót một thư mục `libs`.
- Test runner chạy với classpath/module path khác production.
- Dùng đường dẫn tương đối nhưng thư mục làm việc khi chạy khác thư mục lúc build.

Cách sửa là xác định **module path thực tế của đúng tiến trình đang lỗi**, không chỉ nhìn vào dependency khai báo trong build file.

## 6. Dùng jar --describe-module để xác định tên thật

Lệnh quan trọng nhất khi nghi ngờ tên module:

    jar --describe-module --file libs/money-utils-2.3.0.jar

Với explicit modular JAR, công cụ mô tả descriptor, gồm module name, `requires`, `exports` và metadata khác.

Nếu JAR chưa có `module-info.class`, khi đặt trên module path nó có thể trở thành **automatic module**. Tên của automatic module được lấy từ manifest `Automatic-Module-Name` nếu có, hoặc suy ra từ tên JAR theo quy tắc JDK.

Vì thế, đừng mặc định:

    requires money.utils;

chỉ vì file tên `money-utils-2.3.0.jar`. Hãy xem tên mà công cụ báo rồi dùng đúng tên đó trong `requires`.

Nếu artifact có nhiều phiên bản trên module path, kiểm tra xem chúng có tạo **trùng module name** hoặc làm module resolution không rõ ràng. Đừng giải quyết bằng cách đổi bừa `requires` sang package name.

## 7. Module path trỏ sai thư mục cấp cha/cấp con

Cấu trúc exploded modules thường là:

    out/
      com.example.money/
        module-info.class
        com/example/money/api/Money.class
      com.example.app/
        module-info.class
        com/example/app/Main.class

Trong cấu trúc này, module path thường trỏ đến **`out`**, nơi chứa các thư mục module:

    java --module-path out -m com.example.app/com.example.app.Main

Nếu bạn trỏ nhầm module path tới một thư mục con không đúng ngữ cảnh của lệnh đang chạy, module gốc hoặc dependency có thể không được tìm theo cách mong muốn.

Với các JAR đặt trong:

    libs/
      money-utils-2.3.0.jar
      logging-api.jar

module path thường trỏ đến **`libs`**:

    java --module-path libs ...

Không nên giả định tùy chọn module path tìm đệ quy trong mọi thư mục con. Nếu cấu trúc có nhiều tầng `libs/vendor/...`, hãy đưa đúng vị trí chứa các module vào module path.

## 8. Đừng nhầm classpath với module path

Một lỗi cấu hình:

    java --module-path out --class-path libs/money-utils-2.3.0.jar -m com.example.app/com.example.app.Main

Nếu `com.example.app` khai báo `requires com.example.money`, JAR `money-utils-2.3.0.jar` trên classpath không thỏa mãn dependency named module đó.

Cấu hình cần xét:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

Dùng `out:libs` trên Linux/macOS.

Đối với ứng dụng legacy chưa modularize, chạy toàn bộ bằng classpath có thể hợp lệ:

    java -cp "app.jar;libs/*" com.example.app.Main

Nhưng khi khởi chạy theo `-m`, Java dùng module system để resolve named modules. Hai mô hình không phải lúc nào cũng hoán đổi bằng cách chuyển một dấu `-cp` sang `-p`.

## 9. Khi JAR chưa có module-info.java

JAR cũ được đặt trên classpath thường thuộc unnamed module. Khi chuyển chính JAR đó lên module path, nó có thể được coi là **automatic module**.

Ví dụ:

    libs/
      legacy-money-1.0.jar

Đặt trên module path:

    java --module-path "out;libs" -m com.example.app/com.example.app.Main

Nếu source app khai báo:

    module com.example.app {
        requires legacy.money;
    }

tên `legacy.money` chỉ đúng nếu JDK thực sự gán tên đó cho JAR. Dùng:

    jar --describe-module --file libs/legacy-money-1.0.jar

để kiểm tra.

Automatic module giúp chuyển đổi từng bước, nhưng không xử lý mọi vấn đề: package trùng giữa các named modules, thiếu dependency, version artifact hoặc class loader vẫn có thể gây lỗi riêng. Khi có thể, hãy cung cấp tên module ổn định bằng explicit descriptor hoặc `Automatic-Module-Name`.

## 10. Module có mặt nhưng chưa được resolve

Một module xuất hiện trên module path không phải lúc nào cũng tham gia runtime module graph.

Ví dụ một plugin module nằm trong `plugins`, nhưng ứng dụng không có dependency tĩnh và không đưa plugin vào root set. Module có thể được tìm thấy trên module path nhưng chưa được resolve vào layer mà chương trình đang sử dụng.

Có thể bổ sung root module trong những trường hợp phù hợp:

    java --module-path "out;plugins" --add-modules com.example.plugin -m com.example.app/com.example.app.Main

`--add-modules` yêu cầu module được đưa vào root set của quá trình resolve. Nó không tạo ra module đang thiếu; module `com.example.plugin` vẫn phải có trên module path hoặc nguồn module phù hợp.

Nếu plugin được nạp vào **module layer riêng**, cần kiểm tra `ModuleFinder`, configuration và cách layer được định nghĩa; chỉ sửa module path của launcher không nhất thiết đủ cho loader riêng.

## 11. Công cụ chẩn đoán của JDK

Một số lệnh hữu ích:

**Xem module descriptor của JAR:**

    jar --describe-module --file libs/money-utils-2.3.0.jar

**Liệt kê các module có thể quan sát với cấu hình đường dẫn:**

    java --module-path libs --list-modules

**Kiểm tra module path theo khả năng xác minh của launcher:**

    java --module-path libs --validate-modules

**Hiển thị quá trình module resolution:**

    java --module-path "out;libs" --show-module-resolution -m com.example.app/com.example.app.Main

**Xem dependency của một JAR:**

    jdeps --module-path libs --print-module-deps app.jar

Trong thực tế, `jdeps` cần dependency đúng để phân tích hoàn chỉnh. Đừng dùng tùy chọn bỏ qua dependency thiếu rồi kết luận mọi dependency đã đủ.

Ngoài ra, nên chạy lệnh từ **thư mục làm việc thực tế của CI hoặc container**. Một đường dẫn tương đối như `libs` có thể hợp lệ trên máy phát triển nhưng không tồn tại ở runtime image.

## 12. ModuleFinder: tìm module bằng Java code

Nếu cần kiểm tra module path bằng chương trình Java, dùng `java.lang.module.ModuleFinder`:

    import java.lang.module.ModuleFinder;
    import java.lang.module.ModuleReference;
    import java.nio.file.Path;
    import java.util.Optional;

    public final class CheckModule {
        public static void main(String[] args) {
            ModuleFinder finder =
                    ModuleFinder.of(Path.of("libs"));

            Optional<ModuleReference> result =
                    finder.find("com.example.money");

            if (result.isEmpty()) {
                System.out.println("Module not found in libs");
                return;
            }

            ModuleReference reference = result.get();
            System.out.println(reference.descriptor().name());
            System.out.println(reference.location());
        }
    }

`find(...)` trả về `Optional.empty()` nếu không tìm thấy module mang tên được yêu cầu. Nó không tự ném một exception tên `ModuleNotFoundException` chỉ vì `Optional` rỗng.

Một finder có thể ném `FindException` trong các tình huống lỗi khi tìm hoặc xử lý module content, chẳng hạn artifact trên module path không hợp lệ. Vì vậy, hãy phân biệt “không có module với tên này” và “không thể xử lý một module artifact”.

`ModuleFinder.of(Path.of("libs"))` chỉ tìm trong nguồn mà bạn chỉ định; nó không tự quét mọi dependency của Maven, mọi classpath hoặc mọi plugin directory của ứng dụng.

## 13. FindException, ResolutionException và lỗi package

Ba nhóm lỗi khác nhau:

- `FindException`: lỗi tìm module hoặc resolve module vì module bắt buộc không tìm thấy, hoặc vấn đề về module content.
- `ResolutionException`: một cấu hình module không thể resolve hợp lệ, chẳng hạn các quan hệ package/readability không tương thích.
- `LayerInstantiationException`: lỗi khi định nghĩa module layer theo class loader mapping, có thể liên quan việc nhiều module chia package trên cùng class loader.

Nếu thông báo nêu `Module com.example.money not found`, tập trung vào module path và tên module.

Nếu thông báo nêu một package vừa xuất hiện trong module này vừa trong module khác, vấn đề có thể là **split package** hoặc xung đột module graph; thêm module path không phải là giải pháp đủ.

Nếu module đã tồn tại nhưng một package không được export cho caller, cần kiểm tra `requires`, `exports`, `opens` tùy tình huống. `--add-opens` không biến module đang thiếu thành module hiện hữu.

## 14. Tại sao --add-exports và --add-opens không sửa module thiếu?

Các tùy chọn sau giải quyết các vấn đề về **quyền truy cập**:

    --add-reads
    --add-exports
    --add-opens

Chúng không tải JAR từ repository, không đổi đường dẫn tương đối sai thành đúng, không tự giải quyết tên module không tồn tại.

Ví dụ lỗi:

    java.lang.module.FindException:
        Module com.example.money not found,
        required by com.example.app

Không nên sửa bằng:

    --add-opens=com.example.money/com.example.money.internal=ALL-UNNAMED

Tùy chọn này giả định đã có module `com.example.money`; nó chỉ điều chỉnh khả năng reflection cho một package thuộc module nguồn.

Thứ tự đúng là:

1. Bảo đảm artifact `com.example.money` tồn tại.
2. Đưa đúng artifact/module vào module path.
3. Xác nhận tên module được JVM nhận diện.
4. Resolve module graph thành công.
5. Chỉ sau đó xử lý lỗi exports/opens nếu còn.

## 15. Với Maven: kiểm tra compile và runtime dependency

Trong dự án Maven, một dependency có thể nằm trong cấu hình compile nhưng không có ở runtime vì scope, profile hoặc cách đóng gói distribution.

Ví dụ dependency thư viện:

    <dependency>
      <groupId>com.example</groupId>
      <artifactId>money-utils</artifactId>
      <version>2.3.0</version>
    </dependency>

Dependency này không tự bảo đảm mọi script chạy bằng `java -m` đều đưa JAR vào `--module-path`. Khi chạy JAR bằng lệnh tự viết, phải quản lý đường dẫn đến các JAR thực tế.

Cần kiểm tra:

- Phiên bản JDK được dùng bởi Maven compiler/test/runtime.
- Tên module thực tế trong JAR và `requires`.
- Scope `provided`, `runtime`, `test` và ảnh hưởng lên bộ artifact được đóng gói.
- Plugin đóng gói application distribution có copy đủ JAR vào thư mục runtime không.
- Maven Surefire/Failsafe chạy test trên classpath hay module path và có khác sản phẩm không.

Có thể xem dependency tree của Maven trong môi trường có plugin phù hợp:

    mvn dependency:tree

Nhưng dependency tree chỉ cho biết Maven resolve artifact nào; để chứng minh runtime module path đúng, vẫn cần xem lệnh launcher hoặc log của tiến trình Java thực tế.

## 16. Với Gradle: tách module dependencies và launcher args

Gradle Java plugin có thể suy luận module path cho source có module descriptor khi được cấu hình:

    plugins {
        id 'java'
    }

    java {
        modularity.inferModulePath = true
    }

Dependency ví dụ:

    dependencies {
        implementation 'com.example:money-utils:2.3.0'
    }

Cấu hình trên hữu ích trong build, nhưng nếu deploy bằng script Java riêng thì script phải có module path tương ứng.

Với Gradle Application plugin, nên xem main module, main class và tập runtime dependencies mà task khởi chạy được cấu hình để dùng. Một task test có thể chạy theo cấu hình khác task ứng dụng.

Đừng đoán rằng bật `modularity.inferModulePath` sẽ tự sửa một Docker entrypoint hoặc CI shell script đã ghi cố định `-p out`.

## 17. Kiểm tra đường dẫn tương đối và môi trường triển khai

Nhiều lỗi không nằm ở Java source mà ở filesystem:

- Người chạy đứng sai working directory.
- Dùng dấu `;` trên Linux/macOS hoặc dấu `:` trên Windows.
- Tên thư mục trong script khác với tên thư mục sau khi build.
- JAR bị bỏ sót khi đóng gói container.
- File JAR có phiên bản khác với file dùng lúc compile.
- Thư mục được mount ở đường dẫn khác.
- Module nằm trong archive chưa giải nén ở hình thức mà launcher không hỗ trợ như mong muốn.
- Một wildcard hoặc biến môi trường không được shell diễn giải như người viết kỳ vọng.

Để khắc phục, trước tiên in đường dẫn mà quy trình triển khai thực sự dùng. Sau đó kiểm tra xem thư mục hoặc JAR còn tồn tại và chứa đúng `module-info.class` hoặc automatic module được JVM nhận diện.

Khi script sử dụng `--module-path "out:libs"`, hãy xác nhận các thư mục `out` và `libs` là tương đối so với working directory hiện tại, không phải mặc định tương đối với vị trí file `.jar`.

## 18. Trường hợp --limit-modules và module hệ thống

Một module có thể có mặt trong JDK hoặc module path nhưng bị loại khỏi tập module quan sát được do cấu hình giới hạn.

Ví dụ `--limit-modules` giới hạn các module mà quá trình resolution có thể quan sát, tùy theo tập module được chỉ định và closure dependency. Nếu cấu hình giới hạn vô tình loại module cần thiết, chương trình có thể gặp lỗi giống như module bị thiếu.

Điều này cũng có thể xảy ra khi chạy một runtime image tùy biến được tạo bằng `jlink` mà thiếu module nền tảng cần dùng.

Do đó, nếu lỗi liên quan module JDK như `java.sql`, `java.xml` hoặc một module chuẩn khác, đừng lập tức tìm JAR bên thứ ba. Hãy kiểm tra phiên bản JDK/runtime image, danh sách module thực sự hiện diện và các tùy chọn giới hạn module của launcher.

## 19. Quy trình chẩn đoán ngắn theo từng bước

Khi gặp lỗi module not found, thực hiện theo trình tự:

**Bước 1 — Ghi lại lỗi chính xác.**

Ví dụ:

    java.lang.module.FindException:
        Module com.example.money not found,
        required by com.example.app

Ghi module thiếu (`com.example.money`) và module yêu cầu (`com.example.app`). Nếu compiler nêu `error: module not found`, ghi thêm lệnh `javac` đã chạy.

**Bước 2 — Xác nhận artifact thực sự có mặt.**

Kiểm tra JAR/đường dẫn trong build output, distribution, container hoặc môi trường CI.

**Bước 3 — Xác nhận tên module.**

Chạy:

    jar --describe-module --file libs/money-utils-2.3.0.jar

Đối chiếu tên module với `requires` và tùy chọn `-m`.

**Bước 4 — Xác nhận module path của đúng công cụ.**

Đừng trộn lệnh `javac`, JVM chạy test và JVM production. Chỉ sửa module path của tiến trình đang lỗi.

**Bước 5 — Quan sát resolution.**

Dùng:

    java --module-path "out;libs" --show-module-resolution -m com.example.app/com.example.app.Main

Thay path separator cho đúng hệ điều hành.

**Bước 6 — Phân loại lỗi tiếp theo.**

Nếu lỗi chuyển thành package not visible, split package, service provider không thấy hoặc classloader mismatch, xử lý theo loại mới. Không tiếp tục thêm JAR một cách vô hạn.

**Bước 7 — Chạy lại bằng chính cấu hình triển khai.**

Trên CI/Docker hoặc hệ thống vận hành, lệnh chạy cuối cùng mới là bằng chứng cấu hình module path đã được sửa.

## 20. Những nhầm lẫn thường gặp

- **Tưởng `ModuleNotFoundException` là exception chuẩn của JPMS.** Thông báo chuẩn thường là `FindException` hoặc lỗi compile `module not found`; tên `ModuleNotFoundException` có thể đến từ thư viện khác.
- **Tưởng module name và tên JAR giống nhau.** Cần đọc descriptor hoặc tên automatic module thực tế.
- **Tưởng JAR trên classpath thỏa mãn `requires`.** Named module được tìm trên module path, không phải từ unnamed module của classpath.
- **Tưởng module có mặt trên module path là chắc chắn đã resolve.** Resolution phụ thuộc root module, dependency và cấu hình.
- **Tưởng compile thành công đồng nghĩa runtime tìm được module.** Compiler và launcher có thể dùng đường dẫn khác nhau.
- **Tưởng mọi lỗi thiếu class là lỗi thiếu module.** `ClassNotFoundException` là lỗi ở cấp class/class loader.
- **Tưởng `--add-opens` có thể sửa `FindException: Module not found`.** Đây là tùy chọn reflection, không cấp module content.
- **Tưởng module path quét đệ quy mọi thư mục con.** Phải đưa vào đúng vị trí được công cụ nhận diện.
- **Tưởng path separator giống nhau trên mọi hệ điều hành.** Windows dùng dấu chấm phẩy; Linux/macOS dùng dấu hai chấm.
- **Tưởng `--list-modules` chứng minh module đã là dependency của app.** Nó giúp quan sát module, còn app có resolve module đó hay không phải xem module graph.
- **Tưởng có thể lờ đi `--limit-modules` hoặc custom runtime image.** Chúng có thể ảnh hưởng tập module quan sát được.

## Ghi nhớ

- Trong JPMS chuẩn, lỗi “module not found” thường xuất hiện qua `java.lang.module.FindException` ở runtime hoặc thông báo `error: module not found` của compiler.
- `requires` dùng **module name**; xác nhận bằng `jar --describe-module`.
- `--module-path` khác `--class-path`; một JAR trên classpath không tự trở thành named module.
- Chạy đúng đường dẫn cho **cả compilation lẫn runtime**; kiểm tra path separator và working directory.
- Dùng `java --show-module-resolution`, `java --validate-modules` và `ModuleFinder` để phân loại vấn đề.
- Khi module đã được tìm thấy, lỗi tiếp theo có thể là readability, exports/opens, split package hoặc class loading; hãy chẩn đoán lại theo thông báo mới.

Cách xử lý đáng tin cậy là xác nhận **tên module**, **artifact**, **vị trí**, **module graph** và **tiến trình thực sự bị lỗi**, theo đúng thứ tự. Khi module path được cấu hình nhất quán, lỗi “module not found” thường có thể được giải quyết mà không phải mở rộng quyền truy cập của các package hay sửa những phần code không liên quan.