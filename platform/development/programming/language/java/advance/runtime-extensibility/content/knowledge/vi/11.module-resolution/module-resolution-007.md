# Xử lý FindException, ResolutionException, thiếu phụ thuộc và package xung đột trong JPMS

## 1. Module resolution là bước gì?

Trong Java Platform Module System (JPMS), đặt JAR lên **module path** chưa đủ để chương trình chạy. Java phải tìm module bằng tên, xây dựng tập module được chọn, giải quyết quan hệ \`requires\`/service binding và kiểm tra tính nhất quán của module graph. Chỉ sau khi cấu hình hợp lệ, runtime mới định nghĩa module/layer và ứng dụng mới bắt đầu chạy.

Quá trình này có thể thất bại ngay trước khi gọi \`main()\`:

- **\`java.lang.module.FindException\`**: module finder không tìm được module được yêu cầu hoặc không thể đọc/nhận diện module artifact trong một số trường hợp.
- **\`java.lang.module.ResolutionException\`**: có vấn đề khi resolver xây module graph hoặc phát hiện cấu hình module không nhất quán, ví dụ package visibility xung đột.
- **Thiếu dependency**: module tên trong \`requires\` không có trong tập module có thể tìm thấy; thường biểu hiện bằng \`FindException\`, không phải lúc nào cũng có exception độc lập.
- **Package xung đột (split package)**: cùng một package thuộc nhiều module được resolved trong cùng điều kiện không hợp lệ; có thể phát hiện ở compilation/resolution hoặc khi định nghĩa layer, tùy tình huống.

Các lỗi trên khác lỗi **\`ClassNotFoundException\`**, **\`NoClassDefFoundError\`** hoặc **\`IllegalAccessError\`** phát sinh sau đó khi nạp/link/sử dụng class. Không nên dùng một biện pháp chữa mọi lỗi.

## 2. Quy trình phân giải module ở mức khái niệm

\`\`\`text
Module path / system modules
          |
          v
ModuleFinder xác định module artifacts và descriptors
          |
          v
Root modules (--module / --add-modules / layer roots)
          |
          v
Resolve requires và service binding khi áp dụng
          |
          v
Kiểm tra graph: module tồn tại, readability, exports, xung đột
          |
          v
Configuration -> ModuleLayer -> chạy main()
\`\`\`

Trong lệnh \`java --module-path mods --module app.host/app.Main\`, \`app.host\` là root module. Các quan hệ \`requires\` được lần theo để giải quyết dependencies. Một module chỉ có mặt trên module path nhưng không được giải quyết vào graph thì chưa chắc tham gia runtime.

**Bước đầu khi lỗi:** đọc thông điệp đầy đủ, xác định module root, module bị yêu cầu, đường dẫn vật lý của artifact và loại lỗi; đừng đoán rằng chỉ cần thêm \`--add-modules ALL-MODULE-PATH\`.

## 3. Ví dụ Java 17+: thiếu module gây FindException

Tạo hai named modules, module \`demo.app\` phụ thuộc \`demo.api\`.

Cấu trúc:

\`\`\`text
demo/
  src/
    demo.api/
      module-info.java
      api/Message.java
    demo.app/
      module-info.java
      app/Main.java
\`\`\`

\`src/demo.api/module-info.java\`:

\`\`\`java
module demo.api {
    exports api;
}
\`\`\`

\`src/demo.api/api/Message.java\`:

\`\`\`java
package api;

public final class Message {
    private Message() {}

    public static String value() {
        return "JPMS OK";
    }
}
\`\`\`

\`src/demo.app/module-info.java\`:

\`\`\`java
module demo.app {
    requires demo.api;
}
\`\`\`

\`src/demo.app/app/Main.java\`:

\`\`\`java
package app;

import api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.value());
    }
}
\`\`\`

Tại thư mục \`demo\`, trên shell bash và JDK 17+:

\`\`\`bash
javac --module-source-path src -d mods --module demo.api,demo.app
java --module-path mods --module demo.app/app.Main
\`\`\`

Kết quả:

\`\`\`text
JPMS OK
\`\`\`

Giờ đóng gói chỉ module ứng dụng và cố tình bỏ dependency:

\`\`\`bash
mkdir -p broken
jar --create --file broken/demo.app.jar -C mods/demo.app .
java --module-path broken --module demo.app/app.Main
\`\`\`

Lệnh chạy thất bại trước \`main()\`. Thông điệp điển hình:

\`\`\`text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module demo.api not found, required by demo.app
\`\`\`

Thông điệp/định dạng lỗi có thể phụ thuộc phiên bản JDK/launcher, nhưng nội dung chính là thiếu \`demo.api\`. Để khắc phục, đưa **đúng modular JAR** của \`demo.api\` vào module path:

\`\`\`bash
jar --create --file broken/demo.api.jar -C mods/demo.api .
java --module-path broken --module demo.app/app.Main
\`\`\`

Output trở lại:

\`\`\`text
JPMS OK
\`\`\`

Khi thiếu module, **không sửa bằng \`--add-exports\` hoặc \`--add-opens\`**: hai cờ này liên quan quyền truy cập package, không tạo artifact \`demo.api\` chưa có.

## 4. Hiểu FindException theo nhóm nguyên nhân

Các nguyên nhân cần tách:

| Nhóm | Dấu hiệu | Kiểm tra | Hướng sửa |
| --- | --- | --- | --- |
| Module không tồn tại trên observable module path | \`Module X not found, required by Y\` | \`--module-path\`, thư mục/JAR thực tế | Bổ sung artifact đúng tên |
| Tên module khác tên mong đợi | \`requires example.api\` nhưng JAR khai báo \`example.contract\` | \`jar --describe-module\` | Đồng bộ \`module-info.java\` và module name |
| Artifact không phải module hợp lệ | Lỗi khi đọc/parse \`module-info.class\` hoặc JAR | \`jar --list\`, \`jar --describe-module\` | Build lại JAR, kiểm tra bytecode/module descriptor |
| Có nhiều module trùng tên trên đường tìm kiếm | Module finder/cấu hình chọn nhầm artifact | Kiểm tra module path và cách launcher/layer chọn finder | Loại bỏ trùng lặp, xác định một nguồn module rõ ràng |
| Module được yêu cầu chỉ có ở classpath | Named module không resolve dependency từ unnamed module như một module có tên | So sánh \`-cp\` và \`--module-path\` | Đưa dependency vào đúng module path hoặc thay thiết kế |

\`FindException\` không đồng nghĩa với “file JAR không tồn tại”: JAR có thể có trên đĩa nhưng tên module sai, không nằm trên module path hiệu lực, hoặc không được \`ModuleFinder\` nhìn thấy theo cấu hình đang chạy.

### Xác minh tên module thực sự

\`\`\`bash
jar --describe-module --file path/to/library.jar
\`\`\`

Với explicit modular JAR, kết quả chứa tên từ \`module-info.class\`. Với non-modular JAR đặt trên module path, Java có thể coi đó là **automatic module**: tên được suy ra từ \`Automatic-Module-Name\` trong manifest nếu có, hoặc từ filename theo quy tắc automatic module naming. Không đoán tên từ Maven coordinates; cần kiểm tra output công cụ.

\`jar --list --file path/to/library.jar\` xác minh cấu trúc archive. Nếu dùng multi-release JAR, phải kiểm tra khả năng tương thích với phiên bản Java đích và versioned module descriptor tương ứng.

## 5. ResolutionException: module graph không nhất quán

\`ResolutionException\` xuất hiện khi các ràng buộc phân giải module không thể thỏa mãn. Một tình huống quan trọng là **hai module khác nhau cùng cung cấp package mà module đọc được theo cách tạo ra xung đột**.

Ví dụ thiết kế sai:

\`\`\`text
module demo.alpha
  exports shared;
  shared/A.class

module demo.beta
  exports shared;
  shared/B.class

module demo.app
  requires demo.alpha;
  requires demo.beta;
\`\`\`

Ứng dụng không thể đồng thời đọc hai module export cùng package \`shared\` theo cấu hình này. Compiler hoặc resolver có thể báo package conflict. Không nên “fix” bằng cách thay đổi thứ tự module path hoặc hy vọng module đầu tiên thắng. **Named modules không hoạt động như classpath first-match cho package export xung đột.**

Giải pháp chuẩn: đặt các package khác nhau, ví dụ \`alpha.shared\` và \`beta.shared\`, hoặc thiết kế một module API chung và cho hai provider implement API từ module đó. Nếu cả hai JAR chứa các class của *cùng một thư viện* trong một package, cần hợp nhất/sắp xếp ownership đúng, thay vì ngẫu nhiên giữ cả hai trên module path.

## 6. Ví dụ package conflict khi hai module cùng export package

Đây là ví dụ *cố ý sai* để hiểu lỗi; các tệp là minh họa chứ không thể compile cả graph như một ứng dụng hợp lệ.

\`demo.alpha/module-info.java\`:

\`\`\`java
module demo.alpha {
    exports shared;
}
\`\`\`

\`demo.alpha/shared/Alpha.java\`:

\`\`\`java
package shared;
public final class Alpha {}
\`\`\`

\`demo.beta/module-info.java\`:

\`\`\`java
module demo.beta {
    exports shared;
}
\`\`\`

\`demo.beta/shared/Beta.java\`:

\`\`\`java
package shared;
public final class Beta {}
\`\`\`

\`demo.app/module-info.java\`:

\`\`\`java
module demo.app {
    requires demo.alpha;
    requires demo.beta;
}
\`\`\`

Nếu module \`demo.app\` đọc cả \`demo.alpha\` lẫn \`demo.beta\`, package \`shared\` được export từ hai nguồn khác nhau. Trình biên dịch \`javac\` có thể báo lỗi kiểu \`module demo.app reads package shared from both demo.alpha and demo.beta\`. Khi xây configuration programmatically hoặc gặp graph sai ở runtime, lỗi thuộc nhóm resolution/consistency.

**Cách sửa:** tổ chức tên package và module boundaries để module consumer chỉ thấy một chủ sở hữu cho package đó. Ví dụ \`demo.alpha\` export \`alpha.shared\`, còn \`demo.beta\` export \`beta.shared\`. Đổi package phải cập nhật source, imports, metadata và build artifact nhất quán.

### Cẩn trọng với automatic modules

Automatic modules thường export tất cả packages và có readability rộng. Khi chuyển một thư viện legacy sang module path, các split packages đã sống được trên classpath có thể trở thành xung đột resolution. Hãy kiểm tra package names bên trong từng JAR, không chỉ tên module. Tránh dùng automatic module như giải pháp lâu dài cho hệ thống có nhiều phụ thuộc trùng package.

## 7. Lỗi package khác: cùng package trong một module layer

Bên cạnh việc hai module cùng export package mà consumer đọc, còn có ràng buộc khi định nghĩa modules trong classloader: một classloader không thể định nghĩa cùng một package thuộc hai named modules trong layer theo cách vi phạm ràng buộc loader/package mapping. API \`ModuleLayer.defineModulesWithOneLoader\` và \`defineModulesWithManyLoaders\` có ràng buộc khác nhau về mapping classloader và có thể phát hiện cấu hình không hợp lệ sau resolution. Vì vậy khi kiểm tra package conflicts, phân biệt:

1. **Resolution/readability conflict:** graph bị coi là không nhất quán.
2. **Definition/classloader conflict:** cấu hình layer không thể định nghĩa với chiến lược classloader đã chọn.
3. **Build/source conflict:** compiler từ chối \`split package\` hoặc package được export từ nhiều nguồn.
4. **Classpath collision:** nhiều JAR trong unnamed module có class cùng fully qualified name; classpath thường lấy một theo loader lookup, làm lỗi bị che giấu nhưng không an toàn.

Không suy ra rằng mọi tình huống hai JAR chứa cùng package đều ném đúng \`ResolutionException\`. Kết quả phụ thuộc module graph, exports, loader strategy và giai đoạn kiểm tra.

## 8. Công cụ chẩn đoán khi phân giải thất bại

### Bước 1: in lệnh chạy và môi trường

Ghi lại nguyên văn lệnh \`java\`, \`javac\`/Maven/Gradle và các giá trị:

- JDK version: \`java -version\`.
- Root module: \`--module module.name/main.Class\`.
- Module path: \`--module-path path1:path2\` trên Unix; dấu phân cách path là \`;\` trên Windows.
- \`--add-modules\`, \`--limit-modules\`, \`--patch-module\`, \`--upgrade-module-path\` nếu có.
- Command line khác nhau giữa IDE/tests và distribution.

### Bước 2: kiểm tra artifact

\`\`\`bash
jar --describe-module --file dist/your-module.jar
jar --list --file dist/your-module.jar
\`\`\`

Không đưa tên giả định vào \`requires\` nếu descriptor cho thấy tên khác. Kiểm tra \`module-info.class\` thực sự tồn tại và đúng JDK target.

### Bước 3: xem graph được resolver chấp nhận

Khi **resolution thành công**, launcher có thể in thông tin resolution:

\`\`\`bash
java --show-module-resolution --module-path dist --module app.host/app.Main
\`\`\`

Thay \`app.host/app.Main\` bằng root thực. Với graph đang lỗi, output có thể dừng tại lỗi nên không bảo đảm in đủ thông tin; đây là công cụ chẩn đoán, không phải cách khắc phục.

\`jdeps\` hỗ trợ phân tích dependencies tĩnh:

\`\`\`bash
jdeps --module-path dist --check app.host
\`\`\`

Cần lưu ý \`jdeps\` không phát hiện mọi dependency được tải động qua reflection, \`ServiceLoader\` hay tên class lấy từ cấu hình. Khi có SPI, test nạp plugin thật trên module path sau build.

### Bước 4: xác định module finder và root set

Nếu ứng dụng tự tạo module layer:

\`\`\`java
ModuleFinder finder = ModuleFinder.of(pluginDirectory);
Configuration config = ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(), java.util.Set.of("demo.plugin"));
\`\`\`

Đây là đoạn minh họa trong method có biến \`Path pluginDirectory\` và các import \`java.lang.module.Configuration\`, \`java.lang.module.ModuleFinder\`. \`resolve\` có thể ném \`FindException\`/\`ResolutionException\`, trước khi module layer được định nghĩa. Đảm bảo \`finder\` thấy module đúng tên, parent configuration có module hợp đồng cần thiết, và root set là tên module chứ không phải tên JAR.

### Bước 5: thay đổi ít nhất có thể rồi kiểm tra lại

Sau khi xác định nguyên nhân, chỉ thay đổi chính xác module path, descriptor hoặc package ownership tương ứng; không thêm một loạt cờ mở quyền cho mọi module. Build sạch và thử lại lệnh giống production.

## 9. Xử lý lỗi bằng code khi tự tạo module layer

Khi ứng dụng cho phép tải plugin module động, có thể xử lý lỗi phân giải ở boundary để trả diagnostics rõ ràng. Ví dụ (đặt trong một class có \`Path pluginDir\` hợp lệ):

\`\`\`java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolutionException;
import java.util.Set;

public final class Resolver {
    public static Configuration resolve(Path pluginDir, String rootName) {
        ModuleFinder finder = ModuleFinder.of(pluginDir);
        Configuration parent = ModuleLayer.boot().configuration();
        try {
            return parent.resolve(finder, ModuleFinder.of(), Set.of(rootName));
        } catch (FindException ex) {
            throw new IllegalArgumentException(
                    "Cannot find module/dependency for " + rootName, ex);
        } catch (ResolutionException ex) {
            throw new IllegalStateException(
                    "Inconsistent module graph for " + rootName, ex);
        }
    }
}
\`\`\`

Để biên dịch đoạn trên như một class độc lập, cần thêm \`import java.nio.file.Path;\`. Đây là skeleton minh họa, không phải app runnable end-to-end; thực tế cần định nghĩa layer và loader strategy sau khi có \`Configuration\`.

**Lưu ý:** \`FindException\` và \`ResolutionException\` đều là unchecked exceptions. Không nên bắt \`RuntimeException\` chung rồi mặc định đổi thành “plugin missing” vì điều đó làm mất phân biệt lỗi tìm module, graph conflict và lỗi runtime khác. Giữ cause và log module path/root names (không log dữ liệu nhạy cảm) để vận hành xử lý được.

## 10. Phân biệt với lỗi access và lỗi loading sau resolution

| Lỗi | Thời điểm thường gặp | Câu hỏi cần hỏi |
| --- | --- | --- |
| \`FindException\` | Tìm module/resolve dependency | Module có được finder nhìn thấy không? Tên đúng không? |
| \`ResolutionException\` | Resolver kiểm tra graph | Có split package, export/readability conflicts hoặc graph constraints? |
| \`LayerInstantiationException\` | Tạo module layer/định nghĩa classloaders | Loader mapping có thể định nghĩa package/module này không? |
| \`IllegalAccessError\` | Link/sử dụng class sau resolution | Package có được export tới module gọi không? |
| \`InaccessibleObjectException\` | Deep reflection ở runtime | Package có được opens phù hợp không? |
| \`ClassNotFoundException\` | Tìm class bằng tên/classloader | Class có trong module/artifact và đúng loader/layer không? |
| \`NoClassDefFoundError\` | Link/load class được tham chiếu | Class hay dependency của nó bị thiếu hoặc không thể initialize? |
| \`ServiceConfigurationError\` | Khám phá/khởi tạo service provider | \`uses\`/\`provides\`, provider contract, resolution/layer có đúng không? |

Bảng là định hướng chẩn đoán, không phải quy tắc tuyệt đối về mọi tình huống.

\`--add-exports\` làm thay đổi khả năng truy cập public types trong package, \`--add-opens\` hỗ trợ deep reflection, còn \`--add-reads\` thay đổi readability của module. **Không cờ nào tự tạo module artifact thiếu hoặc sửa split package trong module graph**. Những cờ này nên là phương án tương thích có phạm vi rõ, không phải công cụ “bật hết” để giấu lỗi phân giải.

## 11. Một tình huống thực tế: chuyển thư viện từ classpath sang module path

Một ứng dụng có thể hoạt động trên classpath vì các JAR được nạp theo classpath order. Khi chuyển sang JPMS:

1. Xác định explicit modules và automatic modules trong tất cả JAR.
2. Kiểm tra tên module thật, tránh phụ thuộc tên file theo phỏng đoán.
3. Phát hiện duplicated packages giữa JAR, đặc biệt package \`javax.*\`/\`jakarta.*\`, shaded dependencies và thư viện đã đổi tên artifact.
4. Tách API chung ra một module rõ ràng; không để nhiều module sở hữu cùng package API.
5. Nếu có automatic modules, thay dần bằng modularized dependencies hoặc điều chỉnh cách đóng gói để tránh split package.
6. Chạy \`jdeps\`, smoke test \`java --module-path\` và kiểm tra \`ServiceLoader\`/reflection trong runtime thật.
7. Đảm bảo build không vô tình đưa \`module-info.class\` bị cũ hoặc JAR sai variant lên module path.

Tránh “sửa” split package bằng cách đưa một bản thư viện lên classpath và bản còn lại lên module path mà không xem lại class identity và API contract. Cách này có thể né một lỗi trước mắt nhưng tạo lỗi khó chẩn đoán hơn.

## 12. Checklist xử lý sự cố JPMS

- [ ] Đọc toàn bộ stacktrace và xác định chính xác loại lỗi.
- [ ] Xác minh root module, module path, JDK version và tên module từ descriptor.
- [ ] Kiểm tra dependency trong \`requires\` có thực sự observable/resolved.
- [ ] So sánh tên module automatic và explicit; không đoán theo Maven artifactId.
- [ ] Kiểm tra package ownership và split packages của các module cùng graph.
- [ ] Phân biệt compilation, resolution, layer definition và runtime class loading.
- [ ] Với layer động, xác nhận \`ModuleFinder\`, parent configuration và root module set đúng.
- [ ] Không dùng \`--add-reads\`, \`--add-exports\`, \`--add-opens\` để thay cho module artifact còn thiếu.
- [ ] Build sạch và chạy artifact phát hành thật trên module path.
- [ ] Viết negative tests cho trường hợp thiếu module và package conflict để ngăn tái phát.

**Kết luận:** \`FindException\` thường hướng tới vấn đề **tìm module hoặc dependency**, còn \`ResolutionException\` hướng tới **module graph không nhất quán**. Cách xử lý đúng là xác định root, module finder, module names, dependency edges và package ownership; sửa nguyên nhân ở mô hình module hoặc artifact thay vì vá mù bằng classpath hay cờ truy cập.
