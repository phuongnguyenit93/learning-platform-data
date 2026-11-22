# Tạo module-info.java cho ứng dụng

Khi chuyển một ứng dụng Java từ **classpath** sang Java Platform Module System (JPMS), bước quan trọng là tạo file `module-info.java` để khai báo danh tính module, những module ứng dụng cần đọc và các package hoặc service mà ứng dụng muốn công bố. File này được gọi là **module descriptor**.

Thêm `module-info.java` không chỉ là một thay đổi cú pháp. Ứng dụng chuyển từ mô hình classpath, nơi nhiều package được tìm qua một không gian nạp class rộng, sang mô hình **named modules** với ranh giới rõ ràng. Vì vậy, cần khảo sát dependency, chọn ranh giới module, bổ sung descriptor và kiểm thử cách chạy trên module path.

Bài hướng dẫn này trình bày quy trình từ ứng dụng Java thông thường đến một modular JAR chạy được bằng `java --module-path`.

## 1. Module descriptor giải quyết việc gì?

Một descriptor tối thiểu:

```java
module com.acme.app {
}
```

Khi biên dịch, `javac` tạo `module-info.class`. Nếu được đóng gói trong JAR, artifact có thể được nhận diện là **explicit named module** khi đặt trên module path.

Module descriptor cho JVM và các công cụ biết:

- **Tên module**, ví dụ `com.acme.app`.
- **Dependency** được đọc bằng `requires`.
- **Package API** mà module khác được phép truy cập bằng `exports`.
- **Package cho deep reflection** bằng `opens`.
- **Service consumer** bằng `uses`.
- **Service provider** bằng `provides ... with ...`.

Descriptor không liệt kê từng file JAR, không thay thế công cụ quản lý dependency và không tự đưa dependency bị thiếu vào module path. Nó mô tả quan hệ module; build tool và lệnh chạy vẫn phải cung cấp các artifact tương ứng.

## 2. Xác định ứng dụng đang có những dependency nào

Trước khi tạo descriptor, hãy phân loại các dependency của ứng dụng:

| Nhóm | Ví dụ | Cách xử lý khi modular hóa |
|---|---|---|
| API chuẩn Java SE | Logging, JDBC, XML, HTTP Client | Khai báo `requires java.logging`, `java.sql`... nếu thực sự dùng |
| Thư viện đã có module-info | Modular JAR của nhóm phát triển hoặc bên thứ ba | Dùng tên module mà descriptor công bố |
| JAR không có descriptor | Thư viện cũ trên classpath | Có thể hoạt động như automatic module trên module path trong giai đoạn chuyển đổi |
| Annotation processor | Lombok, processor sinh mã | Cấu hình processor path/module path ở build time, không tự động thêm làm dependency runtime |
| Framework dùng reflection | ORM, JSON serializer, dependency injection | Xác định package cần `opens` cho đúng module framework |
| Service provider | JDBC driver, plugin, codec | Kiểm tra `uses`, `provides` và cơ chế đưa provider vào graph |

Dùng `jdeps` để khảo sát dependency tĩnh:

```shell
jdeps --summary --recursive --class-path "libs/*" app.jar
```

Nếu ứng dụng đã có modular JAR và module path, có thể kiểm tra bằng:

```shell
jdeps --module-path mods --check com.acme.app
```

`jdeps` hữu ích để nhận diện dependency giữa package và module, nhưng không phát hiện đầy đủ những dependency chỉ được dùng qua reflection, `Class.forName`, cấu hình framework hoặc service discovery. Kết hợp kết quả phân tích tĩnh với dependency tree của Maven/Gradle và hiểu biết về những tính năng chạy thật.

## 3. Chọn tên module và vị trí module-info.java

Tên module thường theo quy ước reverse-DNS, ví dụ:

```text
com.acme.app
com.acme.core
com.acme.greeting
```

Tên module cần ổn định vì module khác có thể khai báo `requires` tới tên đó. Không nên đổi tên module chỉ để phù hợp với một cấu trúc thư mục tạm thời.

Với ứng dụng gồm một module, có thể tổ chức source:

```text
src/
├── module-info.java
└── com/
    └── acme/
        └── app/
            └── Main.java
```

Với dự án Maven hoặc Gradle theo quy ước thông dụng, descriptor của phần chính thường đặt ở:

```text
src/main/java/module-info.java
```

Không đặt `module-info.java` bên trong package `com.acme.app`. Descriptor khai báo module ở cấp module source root, chứ không phải một class thuộc package.

Nếu dự án có nhiều named modules trong cùng một source tree dùng `--module-source-path`, mỗi module có thư mục root và descriptor riêng. Mỗi named module cần một `module-info.java` tương ứng.

## 4. Viết requires theo dependency thực tế

Giả sử ứng dụng dùng một thư viện greeting và Java Logging:

```java
import com.acme.greeting.Greeter;
import java.util.logging.Logger;
```

Descriptor ứng dụng có thể là:

```java
module com.acme.app {
    requires com.acme.greeting;
    requires java.logging;
}
```

`requires com.acme.greeting` cho phép module ứng dụng đọc module greeting. `requires java.logging` cho phép ứng dụng dùng các package thuộc module logging khi chúng được export.

`java.base` là dependency ngầm định của mọi named module, nên không cần ghi `requires java.base;`.

Quan trọng: `requires` **không tự cho phép dùng mọi package** của module phụ thuộc. Module được yêu cầu vẫn phải export package chứa các kiểu public cần dùng. Nếu import một kiểu từ package internal không export, compiler sẽ chặn truy cập dù `requires` đã đúng.

### requires, requires transitive và requires static

Có ba dạng thường gặp:

```java
requires com.acme.greeting;
requires transitive com.acme.api;
requires static com.acme.annotations;
```

- `requires M;`: module hiện tại đọc được `M`.
- `requires transitive M;`: ngoài việc đọc `M`, các module đọc module hiện tại còn được hưởng readability tới `M`. Thường dùng khi public API của thư viện lộ kiểu từ `M`.
- `requires static M;`: dependency bắt buộc ở compile time nhưng là tùy chọn ở runtime. Phù hợp với một số annotation/API compile-only, nếu thiết kế thực sự không cần chúng khi chạy.

Không thêm `transitive` cho mọi dependency chỉ vì tiện. Đối với module ứng dụng không được dùng như thư viện, phần lớn dependency thông thường chỉ cần `requires`.

## 5. Ví dụ hoàn chỉnh với hai module

Ví dụ gồm thư viện `com.acme.greeting` và ứng dụng `com.acme.app`.

Cấu trúc source:

```text
project/
├── src-lib/
│   ├── module-info.java
│   └── com/acme/greeting/Greeter.java
└── src-app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Descriptor thư viện:

```java
// src-lib/module-info.java
module com.acme.greeting {
    exports com.acme.greeting;
}
```

Code thư viện:

```java
// src-lib/com/acme/greeting/Greeter.java
package com.acme.greeting;

public final class Greeter {
    private Greeter() {
    }

    public static String sayHello(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Descriptor ứng dụng:

```java
// src-app/module-info.java
module com.acme.app {
    requires com.acme.greeting;
    requires java.logging;
}
```

Main class:

```java
// src-app/com/acme/app/Main.java
package com.acme.app;

import com.acme.greeting.Greeter;
import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info(Greeter.sayHello("JPMS"));
    }
}
```

Đáng chú ý: ứng dụng **không cần export** package `com.acme.app` chỉ để JVM chạy `Main.main` với `-m`. Export package chỉ cần khi module khác phải truy cập API public của package đó.

## 6. Biên dịch, đóng gói và chạy ứng dụng

Ví dụ sau dùng command line, phù hợp khi chạy từ thư mục `project`. Tạo các thư mục `build/library`, `build/app` và `mods` trước khi biên dịch.

Biên dịch thư viện:

```shell
javac -d build/library \
  src-lib/module-info.java \
  src-lib/com/acme/greeting/Greeter.java
```

Đóng gói modular JAR của thư viện:

```shell
jar --create --file mods/com.acme.greeting.jar \
  -C build/library .
```

Biên dịch ứng dụng với module path trỏ tới thư viện:

```shell
javac --module-path mods -d build/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

Đóng gói ứng dụng:

```shell
jar --create --file mods/com.acme.app.jar \
  -C build/app .
```

Chạy bằng module path:

```shell
java --module-path mods \
  --module com.acme.app/com.acme.app.Main
```

Trên Windows, dấu `\` cuối dòng trong ví dụ shell không phải cú pháp nối dòng cho PowerShell/cmd; hãy chạy thành một dòng hoặc dùng cú pháp xuống dòng tương ứng. Nếu module path chứa nhiều thư mục/JAR, dấu phân cách là `:` trên Linux/macOS và `;` trên Windows.

Có thể kiểm tra descriptor sau khi đóng gói:

```shell
jar --describe-module --file mods/com.acme.app.jar
jar --describe-module --file mods/com.acme.greeting.jar
```

Đầu ra giúp xác nhận tên module, dependency và package exports của đúng artifact cuối cùng.

## 7. exports dành cho thư viện; không phải package nào cũng cần export

Module chỉ nên export các package mà module khác cần sử dụng như public API.

Ví dụ:

```java
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

Implementation có thể ở `com.acme.greeting.internal` mà không export. Một public class trong package internal vẫn không tự trở thành API mà module khác truy cập được.

Nếu ứng dụng chia thành module UI, service và data, mỗi module thư viện nên công bố đúng package API. Module chứa logic khởi động, CLI hoặc entry point thường không cần export toàn bộ package nội bộ.

Qualified export dành cho trường hợp chỉ một module cụ thể cần API:

```java
module com.acme.greeting {
    exports com.acme.greeting.integration to com.acme.app;
}
```

Cách này chỉ cấp quyền truy cập package cho `com.acme.app`, không phải mọi module.

## 8. opens dành cho framework dùng deep reflection

Framework ORM, serializer hoặc dependency-injection container có thể truy cập constructor/field không public qua reflection. Khi chuyển sang named module, hành vi reflection từng hoạt động trên classpath có thể bị chặn bởi strong encapsulation.

Ví dụ:

```java
module com.acme.app {
    requires com.acme.greeting;

    opens com.acme.app.model to com.acme.json;
}
```

Ở đây `com.acme.json` là tên **module thực tế** của framework trong ví dụ, không phải tên package. Khi triển khai, thay bằng module name được framework sử dụng.

Phân biệt:

- `exports P;` cho phép module khác sử dụng các kiểu public của package `P` theo quyền Java thông thường.
- `opens P;` mở package `P` cho deep reflection ở runtime.
- `opens P to M;` chỉ mở package `P` cho module `M`.
- `open module X { ... }` mở toàn bộ package của module, thường quá rộng cho ứng dụng muốn đóng gói chặt.

Không dùng `opens` thay cho `exports` khi một module khác cần import và gọi public API. Ngược lại, `exports` không tự cho phép framework đọc field private bằng deep reflection.

## 9. Khai báo service consumer và provider

JPMS tích hợp cơ chế `ServiceLoader` với module descriptor. Nếu ứng dụng dùng một SPI được định nghĩa trong module API:

```java
package com.acme.spi;

public interface ReportExporter {
    void export(String report);
}
```

Module ứng dụng khai báo nhu cầu:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.ReportExporter;
}
```

Ứng dụng có thể gọi:

```java
ServiceLoader<ReportExporter> exporters =
    ServiceLoader.load(ReportExporter.class);

for (ReportExporter exporter : exporters) {
    exporter.export("Báo cáo");
}
```

Một provider ở module khác khai báo:

```java
module com.acme.export.csv {
    requires com.acme.spi;

    provides com.acme.spi.ReportExporter
        with com.acme.export.csv.CsvReportExporter;
}
```

Module API cần export package chứa `ReportExporter`. Module provider không cần export implementation package chỉ để `ServiceLoader` khởi tạo provider.

Tách service interface, consumer và provider giúp ứng dụng giảm dependency tới implementation cụ thể. Tuy nhiên, provider module phải thực sự được đưa vào graph hoặc layer phù hợp, thông qua root modules hoặc service binding; `ServiceLoader` không tự tạo module từ một JAR chưa được resolve.

## 10. Đối phó với thư viện chưa modular hóa

Trong giai đoạn migration, nhiều thư viện bên thứ ba chỉ có JAR thông thường.

Khi đặt JAR không có `module-info.class` trên module path, Java có thể xử lý nó như **automatic module**: module được gán tên từ metadata hoặc tên artifact, export các package của JAR và có khả năng đọc rộng hơn explicit module.

Ví dụ:

```java
module com.acme.app {
    requires legacy.utilities;
}
```

Phải xác nhận `legacy.utilities` đúng là module name của artifact, không suy đoán từ Maven `artifactId` nếu chưa kiểm tra:

```shell
jar --describe-module --file libs/legacy-utils.jar
```

Một thư viện có thể khai báo tên ổn định bằng manifest `Automatic-Module-Name`; nếu không, tên tự suy ra từ tên file có thể thay đổi khi artifact được đổi tên.

Automatic module là bước trung gian hữu ích, nhưng không phải thay thế vĩnh viễn cho explicit module. Nó có tính đóng gói yếu và có thể gây khó khăn khi muốn tạo runtime image bằng `jlink`. Hãy ưu tiên thư viện có module descriptor rõ ràng khi kiến trúc cho phép.

Nếu một thư viện chỉ có thể chạy trên classpath, cần cân nhắc ranh giới migration: ứng dụng modular không nên mặc định rằng nó có thể khai báo `requires` tới classpath JAR. Việc trộn classpath và module path cần thiết kế rõ ràng, thay vì lặp lại cách chạy cũ và chỉ thêm `module-info.java`.

## 11. Tránh split package khi chia module

**Split package** xuất hiện khi cùng một package có class ở nhiều module khác nhau. Ví dụ:

```text
com.acme.api:
    com.acme.shared.Customer

com.acme.impl:
    com.acme.shared.CustomerMapper
```

Hai module cùng chứa `com.acme.shared`. Tùy graph và loader, việc này có thể dẫn đến lỗi vì một consumer đọc cùng package từ nhiều nguồn hoặc vì ràng buộc package ownership.

Cách sửa là tách package theo ranh giới module:

```text
com.acme.api:
    com.acme.api.Customer

com.acme.impl:
    com.acme.impl.CustomerMapper
```

Hoặc chuyển các class cùng một package thực sự phải gắn kết vào một module thống nhất.

Thêm `exports`, `opens` hoặc `--add-exports` không tự giải quyết split package; những cơ chế đó chỉ đổi quyền truy cập chứ không đổi package thuộc module nào.

Khi chia một ứng dụng lớn thành nhiều named modules, hãy xác định **mỗi package sẽ được một module nào sở hữu** trước khi tạo hàng loạt descriptor.

## 12. Chọn cách migration theo giai đoạn

Không nhất thiết chia toàn bộ ứng dụng thành nhiều module ngay lập tức. Một lộ trình thực tế có thể là:

**Giai đoạn 1 — Kiểm kê:** xác định các JAR đang dùng, dependency trực tiếp/bắc cầu, entry point, reflection, service providers và những thư viện chỉ cần ở build time.

**Giai đoạn 2 — Tạo một application module:** thêm `module-info.java` cho ứng dụng, khai báo `requires` và thử chuyển một tập dependency sang module path.

**Giai đoạn 3 — Xử lý dependency chưa modular:** ưu tiên modular JAR, chấp nhận automatic modules như bước chuyển tiếp khi phù hợp, phát hiện split packages và làm rõ module name ổn định.

**Giai đoạn 4 — Khắc phục encapsulation:** khai báo `exports` cho API cần công bố, `opens` cho framework thực sự cần reflection và `uses`/`provides` cho SPI.

**Giai đoạn 5 — Chạy kiểm thử thật:** compile, unit/integration tests, chạy `java -m`, kiểm tra module resolution và các code path dùng reflection/plugin.

**Giai đoạn 6 — Tối ưu triển khai:** sau khi graph ổn định, cân nhắc tạo runtime image bằng `jlink` nếu các module và kiểu dependency cho phép.

Migration theo giai đoạn giúp phân biệt lỗi do descriptor, lỗi do dependency, lỗi do reflection và lỗi ứng dụng vốn đã tồn tại.

## 13. Các lệnh hỗ trợ chẩn đoán

Kiểm tra các module có sẵn trong JDK:

```shell
java --list-modules
```

Xem descriptor module JDK:

```shell
java --describe-module java.logging
```

Xem descriptor của JAR đã đóng gói:

```shell
jar --describe-module --file mods/com.acme.app.jar
```

Theo dõi resolution của ứng dụng:

```shell
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Xem dependency bằng `jdeps`:

```shell
jdeps --module-path mods --check com.acme.app
```

Những lệnh này trả lời các câu hỏi khác nhau. `jar --describe-module` xem hợp đồng module được đóng gói; `--show-module-resolution` cho biết graph runtime; `jdeps` phân tích dependency tĩnh. Kết hợp chúng với thông báo lỗi cụ thể sẽ hữu ích hơn việc thêm bừa các cờ `--add-exports`.

## 14. Lỗi thường gặp sau khi thêm module-info.java

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| `module not found: com.acme.greeting` | Dependency không có trên module path hoặc tên module sai | Kiểm tra `--module-path`, descriptor và tên artifact |
| `package ... is not visible` | Chưa `requires` module hoặc package chưa được export | Kiểm tra readability và `exports` |
| `reads package ... from both ...` | Split package hoặc nhiều module cùng export một package tới consumer | Tách package, loại dependency trùng, hợp nhất artifact |
| `InaccessibleObjectException` | Framework cần deep reflection vào package chưa open | Mở đúng package cho đúng module framework |
| `ServiceConfigurationError` | Thiếu `uses`, provider declaration sai hoặc provider không hợp lệ | Kiểm tra descriptor consumer/provider |
| `ClassNotFoundException` trong plugin | Class/module không nằm trong loader hoặc layer mà code đang sử dụng | Kiểm tra module resolution và class loading |
| JAR chạy được trên classpath nhưng lỗi trên module path | Đổi semantics của package visibility, service discovery hoặc automatic module | Kiểm tra descriptor và cách deploy |
| `IllegalAccessError` khi chạy | Compile và runtime khác nhau về exports, module graph hoặc access modifier | Đồng bộ artifact và kiểm tra module access tại runtime |

Khi gặp lỗi, nên tìm **root cause đầu tiên** trong stack trace hoặc output compiler. Đừng sửa descriptor theo hướng mở toàn bộ package chỉ để một đường chạy tạm thời hoạt động.

## 15. module-info.java và công cụ build

Với Maven, `module-info.java` thường thuộc `src/main/java`, còn dependency nằm trong `pom.xml`. Plugin biên dịch phù hợp với JDK có thể phát hiện và biên dịch modular source khi dependency được tổ chức đúng.

Với Gradle, descriptor cũng thường nằm trong `src/main/java`. Hãy bảo đảm Java toolchain và cách suy luận module path của build được cấu hình tương thích với phiên bản Gradle đang dùng.

Có hai tầng cấu hình khác nhau:

1. **Build file** cho biết tọa độ artifact, version, repository và scope dependency.
2. **Module descriptor** cho biết tên module được đọc, package được export/open và service bindings.

Ví dụ, Maven dependency `com.acme:greeting-library:1.0` không có nghĩa tên JPMS module là `greeting-library`. Descriptor của JAR mới là nơi xác định module name.

Đối với annotation processors, dependency của processor thường phải được cấu hình ở annotation processor path/module path riêng, thay vì chỉ thêm `requires` vào application module.

## 16. Kiểm tra trước khi phát hành

Một application module sẵn sàng chuyển sang module path khi có thể xác nhận:

- `module-info.java` dùng tên module nhất quán và khai báo đúng dependency thực sự.
- Các modular JAR được phân phối với descriptor và module name như kỳ vọng.
- Không có split package gây xung đột trong graph.
- Package API được export có chủ đích; implementation package vẫn đóng gói.
- Framework cần reflection có `opens` thích hợp.
- Service consumer/provider có `uses` và `provides` tương ứng.
- Ứng dụng biên dịch và chạy bằng `java --module-path ... --module ...`.
- Bộ test thực sự bao phủ JDBC, reflection, serializer, plugin và các tính năng cấu hình động khi có.
- Build output và runtime dùng cùng dependency version, tránh trường hợp compile đúng nhưng runtime thiếu export hoặc API.
- Artifact cuối cùng được kiểm tra bằng `jar --describe-module` và graph bằng `--show-module-resolution`.

**Kết luận:** `module-info.java` là hợp đồng module của ứng dụng, không phải danh sách JAR. Bắt đầu bằng descriptor nhỏ, khai báo đúng `requires`, chỉ dùng `exports`/`opens` khi có nhu cầu thực và xác minh bằng quá trình biên dịch/chạy trên module path. Cách tiếp cận đó giúp chuyển ứng dụng từ classpath sang JPMS theo từng bước mà vẫn giữ ranh giới module dễ hiểu và dễ duy trì.