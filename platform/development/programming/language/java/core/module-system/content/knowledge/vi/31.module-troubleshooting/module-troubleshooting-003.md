# ResolutionException do graph không hợp lệ

Khi biên dịch hoặc chạy một ứng dụng sử dụng Java Platform Module System (JPMS), Java không chỉ tìm các file JAR. Nó còn **resolve module graph**: chọn những module cần thiết, nối dependency qua `requires`, xác định readability, kiểm tra package được export và bảo đảm tập module có thể cùng tồn tại theo các quy tắc của JPMS.

Nếu các module có thể được tìm thấy nhưng **không thể tạo thành một graph hợp lệ**, quá trình resolve có thể thất bại với `java.lang.module.ResolutionException`. Một triệu chứng thường gặp là hai module cùng export một package cho một module tiêu thụ; một module khác không thể đọc cùng package đó từ hai nguồn mâu thuẫn.

Bài này giải thích bản chất của lỗi, phân biệt nó với các lỗi module khác, minh họa xung đột package, chỉ ra các nguồn gây lỗi như `requires transitive`, automatic module và service binding, rồi trình bày quy trình chẩn đoán và sửa thiết kế.

## 1. ResolutionException là gì?

`ResolutionException` nằm trong package `java.lang.module` và biểu thị lỗi được phát hiện khi giải quyết cấu hình module.

Một cách nhìn tổng quát:

~~~text
Module path / system modules / parent configuration
                       │
                       ▼
                 Tìm module
                       │
                       ▼
              Chọn root modules
                       │
                       ▼
             Resolve dependency
                       │
                       ▼
        Kiểm tra tính hợp lệ module graph
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
      Graph hợp lệ          Graph không hợp lệ
            │                     │
            ▼                     ▼
     Configuration       ResolutionException
            │
            ▼
       ModuleLayer
~~~

Trong API, quá trình resolve có thể diễn ra khi sử dụng:

~~~java
Configuration child = parentConfiguration.resolve(
    beforeFinder,
    afterFinder,
    rootModules
);
~~~

hoặc:

~~~java
Configuration child = Configuration.resolve(
    beforeFinder,
    parentConfigurations,
    afterFinder,
    rootModules
);
~~~

Java launcher cũng phải thực hiện module resolution trước khi khởi chạy một ứng dụng modular với `java --module ...`.

**Có module trên module path không đồng nghĩa graph hợp lệ.** Bộ resolver còn phải bảo đảm các quan hệ giữa chúng không vi phạm quy tắc module.

## 2. Phân biệt ResolutionException với lỗi khác

Các lỗi liên quan đến JPMS thường có tên gần nhau nhưng xảy ra ở những giai đoạn khác nhau:

| Lỗi | Ý nghĩa điển hình | Hướng điều tra |
| --- | --- | --- |
| `FindException` | Không tìm thấy module cần thiết hoặc phát sinh vấn đề khi khám phá module | Module path, module name, artifact và dependency thiếu |
| `ResolutionException` | Các module có mặt nhưng không tạo được module graph hợp lệ | Readability, export xung đột, dependency graph |
| `LayerInstantiationException` | Graph đã resolve nhưng việc định nghĩa module vào layer thất bại | Class loader mapping, package conflict trong layer, parent layer |
| `IllegalAccessError` | Runtime truy cập kiểu/member không được cho phép | `exports`, access modifier và runtime options |
| `InaccessibleObjectException` | Reflection không được phép vượt qua module encapsulation | `opens`, target module và `--add-opens` |
| `ClassNotFoundException` | Class loader không tìm được class yêu cầu | Classpath/module path, tên class và class loader |

Thông điệp quan trọng: **không phải mọi lỗi có chữ “module” đều là `ResolutionException`**. Ví dụ JAR có tên module trùng nhau, module bị thiếu hoặc file JAR hỏng có thể dẫn đến lỗi ở bước khám phá module. Cần đọc đúng loại exception và nguyên văn thông báo thực tế.

## 3. Ví dụ cơ bản: hai module export cùng một package

Giả sử hai thư viện độc lập đều đặt public class vào package `com.acme.common`.

Module thứ nhất:

~~~java
// com.acme.left/module-info.java
module com.acme.left {
    exports com.acme.common;
}
~~~

~~~java
// com.acme.left/com/acme/common/Left.java
package com.acme.common;

public final class Left {
    public static String value() {
        return "left";
    }
}
~~~

Module thứ hai:

~~~java
// com.acme.right/module-info.java
module com.acme.right {
    exports com.acme.common;
}
~~~

~~~java
// com.acme.right/com/acme/common/Right.java
package com.acme.common;

public final class Right {
    public static String value() {
        return "right";
    }
}
~~~

Ứng dụng yêu cầu cả hai:

~~~java
// com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.left;
    requires com.acme.right;
}
~~~

Sơ đồ:

~~~text
                  com.acme.app
                   /        \
                  /          \
     requires left            requires right
            │                       │
            ▼                       ▼
     com.acme.left            com.acme.right
            │                       │
            └── exports com.acme.common ──┘
                         ▲
                    Xung đột
~~~

`com.acme.app` đọc cả hai module, và cả hai cùng export package `com.acme.common` cho nó. JPMS không thể xem `com.acme.common` là một API package duy nhất có nguồn rõ ràng đối với app.

Thông báo runtime có thể tương tự:

~~~text
Error occurred during initialization of boot layer
java.lang.module.ResolutionException:
Modules com.acme.left and com.acme.right
export package com.acme.common to module com.acme.app
~~~

Đây là thông báo minh họa; thứ tự module và câu chữ cụ thể có thể khác theo JDK hoặc graph đang resolve.

Trong project xây từ source, `javac` có thể phát hiện xung đột ngay khi biên dịch module consumer. Khi đó lỗi xuất hiện ở compile-time thay vì đợi tới Java launcher. **Dù phát hiện ở giai đoạn nào, nguyên nhân thiết kế vẫn là graph có hai nguồn export xung đột cho cùng một consumer.**

## 4. Vì sao split package làm graph khó hợp lệ?

**Split package** nghĩa là cùng một tên package xuất hiện trong nhiều module khác nhau.

Ví dụ:

~~~text
library-one.jar
└── com/acme/common/Alpha.class

library-two.jar
└── com/acme/common/Beta.class
~~~

Nếu hai JAR được biến thành named module và cùng công bố package `com.acme.common`, khả năng xung đột phụ thuộc vào quan hệ module, cách package được export và cách layer/class loader được tạo.

Đối với module consumer, hai package export cùng tên từ hai module mà consumer đọc là một nguồn `ResolutionException` điển hình. Không nên suy rộng rằng **bất kỳ hai JAR trùng package ở bất kỳ đâu trên đĩa** đều lập tức tạo chính xác exception này: Java còn phải quan sát, chọn và resolve các module liên quan. Một số xung đột package có thể bị phát hiện ở giai đoạn định nghĩa layer và biểu hiện bằng exception khác.

Nguyên tắc thiết kế cho explicit modules là **mỗi package nên có một chủ sở hữu rõ ràng trong module graph**. Không dùng package name trùng chỉ để gom nhóm class theo convention của tổ chức.

Cách sửa thường là đổi package và phân tách trách nhiệm:

~~~text
com.acme.left.api
com.acme.right.api
~~~

hoặc đưa API dùng chung vào một module độc lập:

~~~text
com.acme.shared.api
        ▲      ▲
        │      │
com.acme.left  com.acme.right
        ▲      ▲
        └──┬───┘
       com.acme.app
~~~

Cách thứ hai phù hợp nếu hai thư viện thực sự cần cùng một bộ kiểu API, thay vì mỗi thư viện sở hữu một bản class có cùng tên package.

## 5. requires transitive có thể làm xung đột lan tới consumer

Một module có thể chỉ khai báo dependency trực tiếp tới hai module API, nhưng vẫn đọc một số dependency khác **gián tiếp** qua `requires transitive`.

Ví dụ:

~~~java
module com.acme.first.api {
    requires transitive com.vendor.first.model;
    exports com.acme.first.api;
}
~~~

~~~java
module com.acme.second.api {
    requires transitive com.vendor.second.model;
    exports com.acme.second.api;
}
~~~

Nếu `com.vendor.first.model` và `com.vendor.second.model` cùng export package `com.vendor.common`, consumer:

~~~java
module com.acme.app {
    requires com.acme.first.api;
    requires com.acme.second.api;
}
~~~

có thể gặp xung đột khi graph làm cho nó đọc cả hai model modules.

Sơ đồ:

~~~text
com.acme.app
├── requires com.acme.first.api
│   └── requires transitive com.vendor.first.model
│       └── exports com.vendor.common
└── requires com.acme.second.api
    └── requires transitive com.vendor.second.model
        └── exports com.vendor.common
~~~

Chỉ nhìn hai dòng `requires` trong app có thể không phát hiện ra gốc vấn đề. Khi chẩn đoán, phải theo cả đường dependency được truyền readability, không chỉ dependency khai báo trực tiếp.

Không nên tự đổi mọi `requires transitive` thành `requires` để che lỗi. Nếu public API của module trung gian trả về kiểu từ dependency, `transitive` có thể là một phần thiết kế đúng. Cần sửa package ownership hoặc kiến trúc API trước khi thay đổi readability.

## 6. Một module đọc package từ dependency và package của chính nó

Không chỉ hai dependency với nhau mới có thể gây xung đột.

Nếu module `com.acme.app` tự chứa package `com.acme.shared`, trong khi nó đọc một module khác export cùng package đó, JPMS cũng có các ràng buộc để tránh một module vừa sở hữu package vừa nhìn thấy định nghĩa trùng từ nguồn khác.

Ví dụ khái niệm:

~~~text
com.acme.app
├── classes: com.acme.shared.LocalType
└── requires com.acme.lib
                  └── exports com.acme.shared
~~~

Đây là dấu hiệu cần xem lại ranh giới package và việc đóng gói class. Với module build theo chuẩn, package public API dùng chung nên được đặt tại một module sở hữu, không “copy” class của dependency vào module consumer.

Nếu cùng source được package vào nhiều JAR qua shading hoặc plugin build, hãy kiểm tra artifact cuối cùng chứ không chỉ cấu trúc source.

## 7. Automatic module có thể làm xung đột xuất hiện

Một JAR không có `module-info.class` khi đặt trên module path có thể được Java nhìn nhận là **automatic module**.

Ví dụ:

~~~text
mods/
├── legacy-utils-1.0.jar
├── other-utils-2.0.jar
└── com.acme.app.jar
~~~

Automatic modules có cơ chế readability và exports thuận tiện cho quá trình migration. Khi đưa nhiều legacy JAR lên module path, những package trước đây cùng tồn tại trên classpath có thể bộc lộ vấn đề split package.

Ví dụ hai JAR legacy đều chứa:

~~~text
com/legacy/util/Helper.class
~~~

Nếu cả hai trở thành modules và cùng nằm trong graph mà một module tiêu thụ đọc chúng, xung đột package có thể ngăn resolution hoặc gây lỗi ở bước layer definition, tùy cấu hình.

Vì vậy, khi chuyển từ classpath sang module path:

1. Kiểm tra tên automatic modules được suy ra.
2. Kiểm tra các package mỗi JAR chứa.
3. Loại bỏ class trùng và dependency không cần thiết.
4. Ưu tiên bản thư viện có explicit module descriptor và package ownership rõ ràng.
5. Không giả định một bộ JAR hoạt động tốt trên classpath sẽ mặc nhiên thành một module graph hợp lệ.

Để xem tên module của artifact:

~~~bash
jar --describe-module --file mods/legacy-utils-1.0.jar
~~~

Nếu output cho biết đây là automatic module, cần lưu ý tên module có thể phụ thuộc manifest `Automatic-Module-Name` hoặc tên JAR.

## 8. Module path chứa nhiều phiên bản cùng một module

Một lỗi dependency phổ biến khác là đặt nhiều phiên bản của cùng thư viện lên module path:

~~~text
mods/
├── com.acme.data-1.0.jar
└── com.acme.data-2.0.jar
~~~

Nếu cả hai cùng công bố module name `com.acme.data`, bộ tìm module có thể báo vấn đề khám phá/tên module trùng. Tùy công cụ và cách tổ chức module path, đó có thể là `FindException` hoặc lỗi module path khác, **không nhất thiết là `ResolutionException`**.

Điều cần làm:

- Xác định phiên bản nào thực sự được chọn bởi dependency management.
- Tránh copy toàn bộ các version của cùng một artifact vào thư mục `mods`.
- Kiểm tra manifest hoặc descriptor để biết tên module thực tế.
- Đồng bộ dependency giữa Maven/Gradle và thư mục phân phối.
- Đừng chỉ đổi tên file JAR: explicit module name nằm trong `module-info.class`, không đổi theo filename.

Việc duy trì nhiều phiên bản của module trong những `ModuleLayer` riêng là một bài toán khác. Nó cần cấu hình layer/class loader có chủ đích và không thể giải quyết chỉ bằng cách đưa hai JAR cùng tên module vào một thư mục module path thông thường.

## 9. Service binding làm graph có thêm module

Khi dùng `Configuration.resolveAndBind(...)`, JPMS có thể đưa thêm provider modules phù hợp vào kết quả resolve.

Ví dụ:

~~~java
Configuration config = parentConfiguration.resolveAndBind(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.app")
);
~~~

Nếu `com.acme.app` khai báo:

~~~java
module com.acme.app {
    uses com.acme.spi.Plugin;
}
~~~

và module path có nhiều provider, service binding có thể kéo provider modules cùng dependency của chúng vào graph. Điều đó có thể làm lộ xung đột package vốn không xuất hiện khi chỉ resolve root modules ban đầu.

Sơ đồ:

~~~text
com.acme.app
    │ uses Plugin
    ▼
Service binding
    ├── com.acme.provider.a
    │    └── requires com.vendor.common.a
    └── com.acme.provider.b
         └── requires com.vendor.common.b
~~~

Nếu graph bổ sung làm một module đọc hai nguồn export trùng package, resolver có thể báo lỗi.

Không nên kết luận ngay rằng service loader “bị hỏng”. Cần xem provider nào đã được thêm, dependency nào được kéo theo và package nào xung đột.

Khi plugin architecture lớn dần, định nghĩa rõ provider discovery, root modules và module layer boundary sẽ giúp giảm xung đột bất ngờ.

## 10. Đọc thông báo ResolutionException có hệ thống

Ví dụ lỗi:

~~~text
java.lang.module.ResolutionException:
Modules vendor.alpha and vendor.beta export package
com.vendor.common to module com.acme.app
~~~

Tách thông báo thành ba thành phần:

- **Consumer:** `com.acme.app`, module bị ảnh hưởng bởi xung đột.
- **Nguồn A:** `vendor.alpha`, một module export package.
- **Nguồn B:** `vendor.beta`, module còn lại export cùng package.
- **Package:** `com.vendor.common`, tên gây mâu thuẫn.

Thông tin cần thu thập:

~~~text
Consumer module:       com.acme.app
Conflicting package:   com.vendor.common
Exporter 1:            vendor.alpha
Exporter 2:            vendor.beta
Root modules:          ...
Module path:           ...
Java version:          ...
~~~

Thông báo lỗi là đầu mối, không phải lúc nào cũng là toàn bộ nguyên nhân. Ví dụ consumer chỉ phụ thuộc trực tiếp vào `com.acme.api`, còn dependency `requires transitive` kéo hai export trùng vào graph. Do đó cần truy nguồn từ consumer tới exporters.

Nếu exception xuất phát từ API `Configuration.resolve`, lưu lại cả `beforeFinder`, parent configurations, `afterFinder` và tập roots. Tên module và source finder là chìa khóa để tái tạo tình trạng.

## 11. Quy trình chẩn đoán bằng công cụ JDK

### Bước 1: xác định đúng Java đang dùng

~~~bash
java --version
javac --version
~~~

Nếu ứng dụng chạy trong runtime image tùy chỉnh, dùng chính executable của image đó. Module availability phụ thuộc runtime image đang chạy.

### Bước 2: kiểm tra module path thực tế

Ví dụ lệnh khởi chạy:

~~~bash
java \
  --module-path "mods:libs" \
  --module com.acme.app/com.acme.app.Main
~~~

Trên Windows, separator module path thường là dấu chấm phẩy thay vì dấu hai chấm:

~~~powershell
java --module-path "mods;libs" --module com.acme.app/com.acme.app.Main
~~~

Đảm bảo những đường dẫn thật sự được truyền tới launcher đúng như trong script/container.

### Bước 3: xem module có thể quan sát

~~~bash
java --module-path mods --list-modules
~~~

Lệnh này hỗ trợ xác định các module được tìm thấy. Nó không chứng minh graph đã resolve hợp lệ, bởi `--list-modules` không đồng nghĩa với việc khởi chạy toàn bộ root modules cùng một graph.

### Bước 4: kiểm tra descriptor từng JAR liên quan

~~~bash
jar --describe-module --file mods/vendor.alpha.jar
jar --describe-module --file mods/vendor.beta.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Xem tên module, `requires`, `requires transitive`, `exports` và service directives. Khi một JAR là automatic module, output của `jar --describe-module` cũng giúp xác định tên module mà Java sẽ dùng.

### Bước 5: quan sát quá trình resolve

~~~bash
java \
  --show-module-resolution \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Lệnh yêu cầu launcher in thông tin resolution. Nếu graph thất bại, output có thể cung cấp các root/dependency đã được xử lý trước lỗi. Không bảo đảm mọi module đều được in khi resolver dừng sớm; hãy kết hợp với descriptor và exception.

### Bước 6: phân tích dependency

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

`jdeps` có thể phân tích descriptor, dependency và mức readability theo khả năng của phiên bản JDK. Có thể tiếp tục kiểm tra các module trung gian có `requires transitive`.

Với artifact cụ thể:

~~~bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
~~~

Phân tích tĩnh là công cụ chẩn đoán bổ sung. Nó không đảm bảo nhìn thấy provider được chọn động, bytecode tạo lúc runtime hoặc mọi tương tác reflection.

## 12. Sửa xung đột bằng cách tái thiết kế package

Phương án bền vững nhất là làm rõ **module nào sở hữu package nào**.

Giả sử ban đầu:

~~~text
vendor.alpha → exports com.acme.common
vendor.beta  → exports com.acme.common
~~~

Nếu hai module chứa API không liên quan, đổi package:

~~~text
vendor.alpha → exports com.acme.alpha.api
vendor.beta  → exports com.acme.beta.api
~~~

Nếu chúng chia sẻ cùng kiểu API, tách module sở hữu chung:

~~~java
module com.acme.common.api {
    exports com.acme.common.api;
}
~~~

Rồi để hai module implementation phụ thuộc vào nó:

~~~java
module com.acme.alpha {
    requires com.acme.common.api;
    exports com.acme.alpha.api;
}
~~~

~~~java
module com.acme.beta {
    requires com.acme.common.api;
    exports com.acme.beta.api;
}
~~~

Cách này không chỉ giải quyết lỗi resolution. Nó còn ngăn các module khác biên dịch nhầm với hai bản type có cùng tên nhị phân nhưng thuộc hai artifact khác nhau.

Nếu conflict đến từ dependency bên thứ ba, ưu tiên tìm các phiên bản thư viện đã sửa split package hoặc công bố JPMS metadata hợp lệ trước khi tự sửa class của vendor.

## 13. Khi nào thay đổi requires transitive?

Đôi khi vấn đề nảy sinh vì module API truyền readability không cần thiết cho consumer:

~~~java
module com.acme.facade {
    requires transitive com.vendor.legacy;
    exports com.acme.facade.api;
}
~~~

Nếu public API của `com.acme.facade` không để lộ kiểu thuộc `com.vendor.legacy` và consumer không cần đọc vendor module, có thể xem xét:

~~~java
module com.acme.facade {
    requires com.vendor.legacy;
    exports com.acme.facade.api;
}
~~~

Nhưng thay đổi này phải dựa trên hợp đồng API thực tế. Nếu method signature public dùng type từ `com.vendor.legacy`, việc xóa `transitive` có thể làm consumer mất readability cần thiết.

Trường hợp hai module thực sự cần cùng package API, việc hạ `transitive` không phải giải pháp dài hạn. Hãy sửa package ownership thay vì che mâu thuẫn bằng cách giảm tầm nhìn module.

## 14. Qualified exports không phải giải pháp tùy tiện

Một module có thể export package có giới hạn:

~~~java
exports com.vendor.internal to com.acme.adapter;
~~~

Qualified exports hữu ích khi package là integration API dành riêng cho một module. Nó có thể ảnh hưởng tới việc module consumer nào nhìn thấy package được export.

Tuy nhiên, đừng thay `exports p` thành `exports p to some.module` chỉ để né `ResolutionException` nếu `p` vốn là API công khai dành cho các consumer khác. Việc đó thay đổi hợp đồng thư viện và có thể làm ứng dụng khác không biên dịch được.

Các câu hỏi trước khi sửa:

- Package có thực sự là public API không?
- Module nào đang sử dụng public type trong package đó?
- Hai module có đang cung cấp cùng một API hay hai API trùng tên ngoài ý muốn?
- Có thể đổi package hoặc tách shared API module thay vì thu hẹp export không?

Cần sửa thiết kế đúng nguyên nhân, không tối ưu theo việc thông báo lỗi biến mất tạm thời.

## 15. Những JVM flags thường không giải quyết được vấn đề

Một số tùy chọn hay xuất hiện khi chẩn đoán JPMS:

| Tùy chọn | Chức năng | Lưu ý với ResolutionException |
| --- | --- | --- |
| `--add-modules` | Bổ sung root modules | Có thể làm nhiều module được resolve hơn, từ đó bộc lộ xung đột |
| `--limit-modules` | Giới hạn module observable | Có thể che tạm vấn đề nhưng cũng làm mất dependency cần thiết |
| `--add-reads` | Bổ sung quan hệ đọc module | Không sửa package ownership; có thể tạo thêm quan hệ đọc gây mâu thuẫn |
| `--add-exports` | Cấp quyền truy cập API public từ package chưa export | Không phải phép hợp nhất hai package trùng tên |
| `--add-opens` | Cho phép reflection sâu | Không giải quyết xung đột module graph khi resolve |
| `--patch-module` | Bổ sung/thay nội dung module đã tồn tại | Cần kiểm soát chặt package; không phải cách sửa thiết kế split package |

Ví dụ `--add-opens` được dùng cho `InaccessibleObjectException`, không phải cách khắc phục hai module cùng export package.

Không nên thử ngẫu nhiên các flag với hy vọng launcher bỏ qua lỗi. Nếu graph vi phạm ràng buộc của JPMS, thay đổi dependency hoặc package boundary mới là hướng bền vững.

## 16. ModuleLayer động: bắt và báo lỗi đúng lớp

Ứng dụng plugin thường resolve configuration bằng API:

~~~java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolutionException;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parentLayer = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

try {
    Configuration child = parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
    );

    ModuleLayer pluginLayer = parentLayer.defineModulesWithOneLoader(
        child,
        ClassLoader.getSystemClassLoader()
    );

    System.out.println(pluginLayer.modules());

} catch (FindException exception) {
    System.err.println("Module discovery failed: "
        + exception.getMessage());

} catch (ResolutionException exception) {
    System.err.println("Invalid module graph: "
        + exception.getMessage());
}
~~~

Lỗi `ResolutionException` được phát hiện khi tạo `Configuration`. Nếu graph đã tạo thành công nhưng việc định nghĩa module vào class loader thất bại, đó là một giai đoạn khác và có thể xuất hiện `LayerInstantiationException`.

Khi chạy production, tránh nuốt lỗi và tiếp tục coi plugin đã nạp thành công. Nên ghi context như plugin directory, module roots, danh sách artifact đang được cấu hình, version JDK và module name bị báo lỗi.

Nếu resolver đang dùng parent configurations, nhớ rằng dependency có thể được thỏa mãn từ parent layer. Điều đó làm graph phụ thuộc cả module mới và module đã tồn tại ở parent, không chỉ vào JAR trong thư mục plugin.

## 17. Checklist sửa ResolutionException

Khi gặp thông báo graph không hợp lệ, có thể thực hiện theo trình tự:

1. **Ghi lại exception nguyên văn**, đặc biệt các module và package được nêu.
2. **Xác định Java executable** và runtime image đang dùng.
3. **Ghi lại chính xác module path** và root module khi khởi chạy.
4. **Kiểm tra artifact** bằng `jar --describe-module`.
5. **Phân biệt explicit/automatic module** trong tập dependency.
6. **Truy dependency trực tiếp và transitive** từ module bị ảnh hưởng.
7. **Tìm package trùng** trong hai module export cho cùng consumer.
8. **Kiểm tra service binding và plugin modules** nếu graph được resolve động.
9. **Sửa package/module ownership** hoặc thay dependency phiên bản phù hợp.
10. **Biên dịch lại descriptor và artifact** thay vì chỉ sửa JVM flags.
11. **Khởi chạy trên module path** và quan sát `--show-module-resolution`.
12. **Kiểm tra luồng plugin/runtime thực tế** để bảo đảm lỗi không còn phát sinh khi module khác được nạp sau khởi động.

Đối với hệ thống dùng Maven/Gradle, kiểm tra dependency tree cũng quan trọng. Một transitive dependency hoặc bản thư viện cũ được kéo vào từ plugin khác có thể tạo package trùng mà project chính không hề khai báo trực tiếp.

## 18. Mẫu báo cáo sự cố để đội phát triển phối hợp

Một báo cáo lỗi module resolution nên bao gồm:

~~~text
Symptom:
  java.lang.module.ResolutionException: ...

Java:
  java --version output

Launch:
  java --module-path ... --module ...

Root module:
  com.acme.app

Conflicting package:
  com.vendor.common

Modules exporting package:
  vendor.alpha
  vendor.beta

Observed dependency paths:
  app -> facade-a -> vendor.alpha
  app -> facade-b -> vendor.beta

Proposed fix:
  remove duplicate dependency /
  upgrade modular library /
  move shared API to one owning module
~~~

Nội dung có cấu trúc giúp tách nguyên nhân thiết kế khỏi triệu chứng môi trường. Khi xử lý hàng trăm artifact, việc biết **package nào bị export hai lần và consumer nào đọc cả hai** hữu ích hơn chỉ ghi “Java 17 không chạy”.

## Kết luận

`ResolutionException` phản ánh một thất bại ở bước **xây dựng module graph hợp lệ**. Trường hợp điển hình là một consumer đọc hai module cùng export một package, nhưng xung đột cũng có thể đến từ các đường dependency gián tiếp, automatic modules hoặc provider modules được thêm qua service binding.

Hãy bắt đầu từ **exception message**, xác định module consumer và package xung đột, rồi dùng `jar --describe-module`, `java --list-modules`, `java --show-module-resolution` và `jdeps` để truy graph. Giải pháp bền vững là làm rõ một chủ sở hữu cho mỗi package, loại dependency trùng và quản lý hợp đồng `requires`/`exports` phù hợp. Các flag dành cho reflective access không thay thế được việc sửa một graph thực sự không hợp lệ.
