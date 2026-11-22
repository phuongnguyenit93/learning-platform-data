# Module không được tìm thấy, package trùng và lỗi phân giải JPMS

Khi một ứng dụng Java chuyển từ classpath truyền thống sang Java Platform Module System (JPMS), lỗi có thể xảy ra ngay trước khi phương thức `main` được gọi. Những thông báo như `Module com.acme.core not found`, `module X reads package p from both A and B`, hoặc `ResolutionException` thường liên quan đến **module discovery, resolution, readability, exports và package ownership**, chứ không nhất thiết do một lỗi trong logic nghiệp vụ.

Trong một đợt **Java Advance Compatibility Migration**, điều này đặc biệt quan trọng. Một bộ thư viện chạy nhiều năm trên classpath Java 8 có thể chứa các package trùng, duplicate classes hoặc plugin JAR không có descriptor. Khi đưa chúng lên module path của Java 17/21, Java launcher áp dụng quy tắc JPMS rõ ràng hơn và các xung đột từng bị classpath che giấu có thể lộ ra.

Bài học giải thích chi tiết nguyên nhân, cách đọc thông báo lỗi, công cụ `java`, `javac`, `jar`, `jdeps`, các ví dụ tái hiện, hướng sửa an toàn và ma trận kiểm thử migration. Mục tiêu không chỉ là làm mất exception, mà là xây dựng một **module graph có thể giải thích, đóng gói và tái tạo trên môi trường đích**.

## 1. Bắt đầu từ mô hình JPMS

JPMS phân biệt một số bước:

1. **Discovery:** tìm các module definitions có thể quan sát từ JDK runtime image và application module path.
2. **Resolution:** chọn các root modules và các dependency mà descriptor yêu cầu.
3. **Readability:** quyết định module nào được đọc module nào.
4. **Accessibility:** quyết định package được export hoặc open cho module/caller nào.
5. **Class loading và reflection:** nạp class và truy cập thành viên khi ứng dụng chạy.

Sơ đồ:

~~~text
Application JARs + JDK runtime modules
                   |
                   v
           Module discovery
                   |
                   v
   Roots + requires -> Module resolution
                   |
                   v
       Readability / exports checks
                   |
                   v
          Module graph hợp lệ
                   |
                   v
     Class loading, services, reflection
                   |
                   v
               main()
~~~

Không phải mọi lỗi trong chuỗi trên đều có cách sửa giống nhau.

### 1.1. Observable, resolved, readable và accessible

| Trạng thái | Câu hỏi | Dấu hiệu |
|---|---|---|
| Observable | Module finder có nhìn thấy definition của module không? | Có JAR đúng trên module path hoặc system module không? |
| Resolved | Module đã được chọn vào graph chưa? | Là root hoặc là dependency được kéo vào không? |
| Readable | Module A có đọc module B không? | Có readability edge thích hợp không? |
| Accessible | A có được dùng package của B không? | B có export package cho A không? |

Ví dụ module `com.acme.metrics` có JAR đặt tại `lib/` nhưng không phải root hoặc dependency của module app. Nó có thể **observable nhưng chưa được resolved**. Một module đã resolved cũng có thể không được module khác đọc, hoặc package của nó không được export.

Không nên dùng các khái niệm này như từ đồng nghĩa.

## 2. Ba loại module khi nâng Java

### 2.1. Explicit named module

Một module có `module-info.java`:

~~~java
module com.acme.orders {
    requires java.sql;
    requires com.acme.catalog;
    exports com.acme.orders.api;
}
~~~

Compiler tạo `module-info.class`. Khi artifact được tìm qua module path và resolve, nó là named module có dependency và access rules tường minh.

### 2.2. Automatic module

Một thư viện JAR chưa có module descriptor có thể trở thành **automatic module** khi đặt trên module path.

Tên của nó được xác định từ:

- Manifest attribute `Automatic-Module-Name`, nếu được khai báo hợp lệ.
- Tên file JAR được suy ra theo quy tắc JPMS, nếu thiếu attribute.

Automatic module hỗ trợ quá trình chuyển đổi legacy libraries, có readability/exports rộng hơn explicit module trong những trường hợp thích hợp. Nhưng automatic module **không tự giải quyết split package**, duplicate module name hay class binary incompatibility.

### 2.3. Unnamed module

Class được nạp theo classpath truyền thống thuộc unnamed module gắn với class loader. Đối với mã ở unnamed module, các quy tắc truy cập khác named modules và cơ chế classpath vẫn hoạt động.

Điểm quan trọng: một explicit named module **không thể khai báo `requires unnamed`** để lấy dependency từ classpath. Nếu một JAR được đặt trên classpath thay vì module path, hãy thiết kế ranh giới phù hợp thay vì ghi một dependency không tồn tại trong descriptor.

### 2.4. System module

JDK cung cấp các module như `java.base`, `java.logging`, `java.sql`. Một runtime image tùy chỉnh qua `jlink` có thể chỉ chứa một tập nhỏ hơn. Vì thế ứng dụng có thể chạy trên full JDK nhưng báo thiếu system module trong runtime image.

## 3. Classpath và module path là hai cách vận hành khác nhau

Classpath:

~~~bash
java -cp "lib/*:app.jar" com.acme.app.Main
~~~

Module path:

~~~bash
java --module-path "mods:lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Trên Windows, dùng dấu `;` để phân tách entries trong path list, thay cho `:` trên Unix-like systems.

Khi chuyển từ `-cp` sang `--module-path`, ứng dụng không chỉ đổi đường dẫn tìm JAR. JVM sẽ tạo module graph và áp dụng module access rules.

### 3.1. Các option liên quan

| Option | Mục đích |
|---|---|
| `--module-path`, `-p` | Đặt vị trí tìm application modules |
| `--module`, `-m` | Chỉ định module/main class để khởi chạy |
| `--add-modules` | Thêm root modules khi resolution |
| `--limit-modules` | Giới hạn tập module được phép quan sát |
| `--add-reads` | Bổ sung readability edge có chủ đích |
| `--add-exports` | Export package bổ sung khi có lý do |
| `--add-opens` | Cho phép deep reflection bổ sung |
| `--show-module-resolution` | Hiển thị quá trình resolution khi launch |
| `--list-modules` | Liệt kê system modules trong runtime |
| `--describe-module` | Mô tả một module mà launcher tìm thấy |

Dùng `java --help` và `javac --help` của **đúng JDK target** để kiểm tra cú pháp hỗ trợ. Các option chỉ giải quyết từng tầng; không thể dùng `--add-opens` để tạo một module bị thiếu.

## 4. Lỗi Module not found ở compile time

Một descriptor:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Nếu compiler không tìm được `com.acme.catalog`, thường có thông báo tương tự:

~~~text
module-info.java:2: error: module not found: com.acme.catalog
    requires com.acme.catalog;
                     ^
~~~

Các nguyên nhân:

1. Dependency JAR chưa được tải hoặc build.
2. Compiler `--module-path` thiếu thư mục/JAR.
3. Module name thực tế khác tên ghi trong `requires`.
4. JAR đang nằm trên classpath thay vì module path.
5. Dependency thuộc multi-module build nhưng output module chưa được tạo.
6. Tập module observable bị giới hạn bởi cấu hình compiler.
7. Artifact hoặc module descriptor không hợp lệ.

Đừng bắt đầu bằng cách sửa Java source code tiêu thụ API. Hãy xác minh **tên module** và **compile module path**.

## 5. Lỗi Module not found lúc khởi chạy

Thông báo thường gặp:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException:
  Module com.acme.catalog not found, required by com.acme.app
~~~

JVM cần resolve `com.acme.app`, trong descriptor có `requires com.acme.catalog`, nhưng module finder không thấy module được yêu cầu trong tập module observable của runtime launch.

Cần kiểm tra:

- Lệnh `java` thực tế được systemd/Windows service/Docker chạy.
- Thư mục hiện tại và các relative paths.
- JAR có được copy vào image/distribution không.
- `--module-path` có dùng đường dẫn đúng và có quote không.
- Module JAR có tên/module descriptor mong đợi không.
- Có `--limit-modules` làm module không observable không.
- Có dependency transitive khác bị thiếu không.
- Runtime có phải custom `jlink` image thiếu system modules không.

Một JAR nằm trên disk chưa chắc đã nằm trên module path của process.

## 6. Quy trình chẩn đoán module not found

### Bước 1 — Ghi lệnh compile và launch thật

Ví dụ:

~~~bash
java --module-path "dist/mods:dist/lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Ghi đường dẫn tuyệt đối nếu cần. Một lỗi phổ biến là script chạy từ thư mục khác nên `dist/lib` trỏ tới vị trí không tồn tại.

### Bước 2 — Xem manifest/descriptor của JAR

~~~bash
jar --describe-module --file dist/lib/catalog-client.jar
~~~

Công cụ cho biết explicit module hoặc thông tin automatic module tương ứng. Không suy đoán tên module từ Maven groupId, artifactId hoặc class package root.

### Bước 3 — Liệt kê module path entries

Kiểm tra JAR file names, versions, content và module names. Một distribution có thể vô tình copy `catalog-1.0.jar` nhưng compile với `catalog-2.0.jar`.

### Bước 4 — Quan sát resolution

~~~bash
java --show-module-resolution \
  --module-path "dist/mods:dist/lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Khi resolution fail rất sớm, output có thể chưa đủ chi tiết; kết hợp kiểm tra `module-info.java` và JARs cụ thể.

### Bước 5 — Tối giản module graph

Thử dùng đúng root module và tập dependencies tối thiểu. Nếu một thư mục chứa nhiều JAR thừa, loại chúng khỏi bản chạy thử để xác định module name hoặc split-package conflict.

### Bước 6 — Lưu bằng chứng

~~~text
JDK vendor/build:
Launch command:
Working directory:
Module path:
Root module:
module-info descriptors:
JAR names and hashes:
Exception and stack trace:
~~~

Những thông tin này giúp tái hiện lỗi trên CI và môi trường production.

## 7. Ví dụ tối thiểu với hai explicit modules

Cấu trúc dự án:

~~~text
src/
├── com.acme.catalog/
│   ├── module-info.java
│   └── com/acme/catalog/Catalog.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Module thư viện:

~~~java
module com.acme.catalog {
    exports com.acme.catalog;
}
~~~

Class thư viện:

~~~java
package com.acme.catalog;

public final class Catalog {
    public static String name() {
        return "catalog";
    }
}
~~~

Module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.catalog.Catalog;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Catalog.name());
    }
}
~~~

Dùng module source path:

~~~bash
javac --module-source-path src \
  -d out \
  -m com.acme.catalog,com.acme.app
~~~

Khởi chạy:

~~~bash
java --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

Lệnh trên áp dụng cho modular source tree đúng cấu trúc. Nếu chỉ mang riêng source `com.acme.app` sang project khác mà không cung cấp compiled artifact `com.acme.catalog` qua module path hoặc source module path, compiler có thể báo module not found.

### 7.1. Kiểm tra output

~~~text
out/
├── com.acme.catalog/
│   ├── module-info.class
│   └── com/acme/catalog/Catalog.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Có hai exploded modules trong output root. Khi đóng gói thành JARs, hãy xác nhận mỗi archive có đúng module-info và classes của module tương ứng.

## 8. Module name khác artifactId và tên JAR

Ví dụ Maven dependency:

~~~xml
<dependency>
  <groupId>com.acme.platform</groupId>
  <artifactId>catalog-client</artifactId>
  <version>2.4.0</version>
</dependency>
~~~

Module name thực tế có thể là `com.acme.catalog.client`. Nếu `module-info.java` ghi:

~~~java
requires catalog.client;
~~~

thì có thể báo lỗi dù file `catalog-client-2.4.0.jar` tồn tại.

Nguồn tên module theo thứ tự liên quan:

1. Tên trong explicit `module-info.class` nếu JAR đã modularize.
2. `Automatic-Module-Name` cho non-modular JAR, khi có.
3. Tên suy ra từ file JAR đối với automatic module còn lại.

Đặc biệt, derived automatic module name có thể thay đổi khi rename JAR hoặc đổi convention version filename. Với dependency dùng lâu dài trên module path, cần lựa chọn module naming ổn định.

## 9. Duplicate module name khác module not found

Ví dụ runtime distribution:

~~~text
lib/
├── client-api-1.9.jar
└── client-api-2.4.jar
~~~

Nếu cả hai định nghĩa cùng module name `com.acme.client.api`, module finder có thể báo lỗi về duplicate modules trong một nguồn tìm module.

JPMS không tự chọn “phiên bản mới nhất” dựa trên version suffix trong tên file. Nó không thay thế cơ chế Maven/Gradle dependency mediation.

Hướng xử lý:

- Chọn một version được hỗ trợ.
- Loại bản trùng khỏi runtime bundle.
- Kiểm tra plugins/service wrapper không copy cả bản cũ.
- Kiểm tra shading hoặc packaging không tạo module name collision.
- Xác minh effective runtime module path, không chỉ dependency declarations.

Không thêm cả hai bản để “dự phòng”: việc đó có thể biến lỗi thiếu dependency thành duplicate module error.

## 10. Module có mặt nhưng chưa được resolved

Giả sử:

~~~text
mods/
├── com.acme.app.jar
└── com.acme.metrics.jar
~~~

Nếu `com.acme.app` không `requires com.acme.metrics` và metrics không được thêm làm root hay dependency theo đường graph khác, JAR metrics có thể nằm trên module path nhưng **không xuất hiện trong resolved graph**.

Có những tình huống cần thêm root module:

~~~bash
java --module-path mods \
  --add-modules com.acme.metrics \
  --module com.acme.app/com.acme.app.Main
~~~

Nhưng `--add-modules` chỉ có tác dụng nếu module đó **observable** và không gây conflict. Nó không sửa tên sai hoặc tự giải quyết split packages.

### 10.1. ALL-MODULE-PATH không phải phương án sửa mặc định

Trong những hoàn cảnh hỗ trợ, `--add-modules ALL-MODULE-PATH` yêu cầu đưa các module observable trên module path thành roots. Điều này có thể làm graph kéo thêm các thư viện không liên quan và tạo conflict package/name mới.

Đừng đưa mọi module vào graph nếu ứng dụng chỉ cần vài modules rõ ràng.

## 11. requires, transitive và static

Ví dụ:

~~~java
module com.acme.report {
    requires com.acme.core;
    requires transitive com.acme.api;
    requires static com.acme.annotations;

    exports com.acme.report.api;
}
~~~

- `requires com.acme.core`: dependency trực tiếp/readability của module này.
- `requires transitive com.acme.api`: khi module khác đọc `com.acme.report`, readability với `com.acme.api` có thể được truyền theo quy tắc JPMS.
- `requires static com.acme.annotations`: module cần tại compile time, có thể vắng khi runtime; code sử dụng class tùy chọn vẫn phải xử lý khi module vắng.

`requires static` không phải cách giấu một runtime dependency bắt buộc. Nếu feature thật sự gọi class không có tại runtime, vẫn có thể gặp lỗi class loading/linkage.

### 11.1. Readability chưa đủ để truy cập mọi class

Ngay cả khi module A đọc B, package chưa được B export cho A vẫn không phải Java API accessible. Phải kiểm tra cả **`requires` và `exports`**.

## 12. --limit-modules có thể khiến dependency không observable

Một launch configuration có thể dùng:

~~~bash
java --limit-modules java.base,com.acme.app \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

`--limit-modules` có cơ chế giới hạn universe observable modules dựa trên các module và closure liên quan theo quy tắc Java launcher; hệ quả là một module khác có thể không còn được phép tham gia resolution, dù JAR của nó có trên disk.

Khi module not found chỉ xảy ra trong một launcher nhưng không xảy ra với lệnh `java` thủ công, hãy tìm cả `--limit-modules` ở startup scripts, IDE hoặc CI options.

Không loại `--limit-modules` mà chưa hiểu lý do bảo mật/packaging nó được thêm vào; trước hết xác định dependency nào cần thuộc tập module được phép.

## 13. Split package là gì?

**Split package** là tình huống có cùng một Java package name được định nghĩa bởi nhiều thành phần JAR/module.

Ví dụ:

~~~text
util-a.jar
└── com/acme/common/UtilA.class

util-b.jar
└── com/acme/common/UtilB.class
~~~

Cả hai chứa package `com.acme.common` dù class names khác nhau.

Trên classpath, cách bố trí này đôi khi hoạt động vì class loader có thể tìm classes từ nhiều JAR. Trên module path, JPMS phân biệt package ownership theo module và có quy tắc ngăn một module đọc cùng package từ những nguồn module xung đột.

### 13.1. Không phải mọi duplicate package tạo cùng một lỗi

Cần phân biệt:

- Hai named modules export cùng package và một module thứ ba đọc cả hai.
- Hai JAR cùng package nhưng nằm trong các loaders/layers được cô lập.
- Một named module và một unnamed module có cùng package name.
- Hai versions cùng chứa cả class name và package name giống nhau.
- Shaded JAR gộp classes vào một module duy nhất.

Kết quả phụ thuộc graph, exports, readability và class loader identity. Vì thế không nên dùng câu “mọi split package đều luôn báo cùng một exception” để chẩn đoán.

## 14. Ví dụ tái hiện lỗi package trùng

Module A:

~~~java
module com.acme.util.a {
    exports com.acme.common;
}
~~~

Class A:

~~~java
package com.acme.common;

public final class UtilA {
    public static String value() {
        return "A";
    }
}
~~~

Module B:

~~~java
module com.acme.util.b {
    exports com.acme.common;
}
~~~

Class B:

~~~java
package com.acme.common;

public final class UtilB {
    public static String value() {
        return "B";
    }
}
~~~

Ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.util.a;
    requires com.acme.util.b;
}
~~~

Compiler/resolver có thể báo:

~~~text
module com.acme.app reads package com.acme.common
  from both com.acme.util.a and com.acme.util.b
~~~

Dù không trùng tên class, package `com.acme.common` được hai module export tới cùng một reader. Vấn đề nằm ở **package boundary và readability**, không phải tên class `UtilA`/`UtilB`.

### 14.1. Vì sao không giải quyết bằng đổi một class?

Đổi `UtilB` thành `HelperB` vẫn để module B export package `com.acme.common`. Cần thay package ownership, module composition hoặc dependency topology.

## 15. Các cách sửa split package

### 15.1. Đưa package về một module owner

Nếu package thật sự là API chung, gộp classes vào một module hợp lệ:

~~~text
com.acme.common.module
└── com/acme/common/
    ├── UtilA.class
    └── UtilB.class
~~~

Các modules khác chỉ `requires com.acme.common.module`. Đây là mô hình dễ lý giải khi nhóm có quyền sửa source/packaging.

### 15.2. Phân tách package theo trách nhiệm

Nếu A và B có ownership khác nhau:

~~~text
com.acme.util.a
com.acme.util.b
~~~

Đổi package đòi cân nhắc public API compatibility, reflection, serialization, resource paths, generated code và các consumers bên ngoài.

### 15.3. Loại dependencies bị lặp

Nếu split package đến từ hai versions của một thư viện, chọn một version trong runtime distribution. Tìm nguyên nhân vì sao cả hai xuất hiện: copy thủ công, fat JAR, transitive dependency hoặc container-provided library.

### 15.4. Thiết kế bridge cho legacy libraries

Nếu một library chưa thể modularize và có nhiều package trùng, có thể giữ nó trong classpath ở giai đoạn chuyển đổi, nhưng phải thiết kế ranh giới với named modules. Không thể chỉ viết `requires unnamed`.

### 15.5. ClassLoader hoặc ModuleLayer isolation

Với plugin system cần chạy những dependencies không tương thích, có thể dùng loaders/layers hoặc processes riêng. Tuy nhiên:

- Shared API/SPI types phải có class identity đúng.
- Module layer có resolution và package constraints riêng.
- Service discovery, TCCL, resources và memory leaks cần test.
- Isolation không giải quyết graph đang yêu cầu cùng một module đọc hai exports xung đột.

Đây là giải pháp thiết kế plugin platform, không phải mẹo chữa một distribution copy thừa JAR.

## 16. Duplicate class và split package khác nhau

Hai JAR có thể chứa:

~~~text
com/acme/common/Util.class
~~~

Đó là **duplicate class name**. Nếu chỉ trùng package nhưng không trùng binary class name, vẫn có thể là split package.

| Tình huống | Có class trùng? | Có package trùng? |
|---|---:|---:|
| JAR A chứa `p.A`, JAR B chứa `p.B` | Không | Có |
| JAR A/B cùng chứa `p.A` | Có | Có |
| JAR A chứa `a.X`, JAR B chứa `b.Y` | Không | Không |

Duplicate classes trên classpath có thể gây shadowing và `NoSuchMethodError` nếu một version bị nạp khác lúc compile. Trong JPMS, conflict có thể xuất hiện sớm hơn ở resolution/readability.

Đừng chỉ dùng một công cụ duplicate-class checker rồi kết luận package structure đã phù hợp JPMS.

## 17. Automatic modules dễ làm lộ split package legacy

Hai thư viện legacy:

~~~text
legacy-api.jar
  com/vendor/common/Client.class

legacy-impl.jar
  com/vendor/common/ClientImpl.class
~~~

Trên classpath có thể không vấn đề. Khi đặt cả hai trên module path, mỗi JAR thành automatic module với package exports/readability rộng, và conflict có thể xuất hiện nếu app cần đọc chúng theo module graph.

Không tạo `module-info.java` cho mỗi JAR rồi giữ nguyên package trùng. Điều đó không sửa ownership.

Các phương án:

- Chờ nhà cung cấp phát hành bản modularized có cấu trúc phù hợp.
- Loại một artifact thừa nếu có.
- Gộp packages có kiểm soát thành một module trong phạm vi giấy phép.
- Chuyển mã thuộc quyền sở hữu sang package riêng.
- Giữ classpath legacy và tách modernization JPMS thành giai đoạn khác.

## 18. Tìm các package trùng trong JAR

Với từng JAR:

~~~bash
jar --list --file lib/util-a.jar
jar --list --file lib/util-b.jar
~~~

Những entry:

~~~text
com/acme/common/UtilA.class
com/acme/common/UtilB.class
~~~

cho thấy cùng package path. Với nhiều artifacts, có thể viết công cụ phân tích archive để nhóm class entries theo package và module name.

Cần xử lý đúng:

- `META-INF` không phải Java application package.
- `module-info.class` là module descriptor.
- `META-INF/versions/N` có ý nghĩa riêng trong multi-release JAR.
- Shaded JAR có thể chứa metadata/service descriptors ngoài classes.
- Trùng package trong archive list không đủ kết luận graph fail; vẫn phải xem exports/readability/layers.

Chỉ phân tích artifact copies ở môi trường được phép; không giải nén lên thư mục production rồi vô tình ghi đè files.

## 19. Package conflict gián tiếp qua requires transitive

Ví dụ module app chỉ trực tiếp yêu cầu một facade:

~~~java
module com.acme.app {
    requires com.acme.facade;
    requires com.vendor.beta;
}
~~~

Facade:

~~~java
module com.acme.facade {
    requires transitive com.vendor.alpha;
}
~~~

Nếu `com.vendor.alpha` và `com.vendor.beta` đều export `com.vendor.common` cho app, conflict có thể xuất hiện **dù app không trực tiếp ghi `requires com.vendor.alpha`**.

Khi chẩn đoán, cần xét:

- Direct `requires` của app.
- Transitive readability từ modules trung gian.
- Automatic modules.
- Root modules do `--add-modules`.
- Service binding/module layer configuration khi có.

Không chỉ xóa một dòng `requires` trong app và cho rằng conflict đã biến mất nếu module vẫn được đọc qua đường khác.

## 20. Package tồn tại nhưng không visible

Một module có:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Class nội bộ:

~~~java
package com.acme.catalog.internal;

public final class InternalParser {
}
~~~

Consumer `com.acme.app` có thể đọc module catalog nhưng không được truy cập package internal. Lỗi compile:

~~~text
package com.acme.catalog.internal is not visible
  (package is declared in module com.acme.catalog,
   which does not export it)
~~~

Đây không phải module missing và không phải split package.

Hướng sửa ưu tiên là dùng API package được export. Nếu module tác giả chủ động cung cấp SPI cho một host, có thể dùng qualified export:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    exports com.acme.catalog.spi
        to com.acme.plugin.host;
}
~~~

Không export toàn bộ internal packages chỉ để “làm hết lỗi” khi chưa xác nhận API contract.

## 21. opens khác exports

Framework như ORM, dependency injection, serializer hoặc test runner có thể cần deep reflective access.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.orm;

    exports com.acme.app.api;
    opens com.acme.app.entities to com.acme.orm;
}
~~~

- `exports` cho phép truy cập public types/members của package qua quy tắc module access.
- `opens` cho phép deep reflection trong phạm vi được khai báo.
- `--add-opens` là một escape hatch dùng cho runtime/configuration có lý do rõ.

Nếu lỗi là `InaccessibleObjectException`, module graph có thể đã được resolved hoàn toàn. Thêm JAR mới không khắc phục vấn đề reflection và còn có thể tạo duplicate module/package.

Không sử dụng `--add-opens java.base/...=ALL-UNNAMED` diện rộng khi chỉ cần nâng một thư viện không tương thích.

## 22. jlink runtime image có thể thiếu system module

Một ứng dụng khai báo:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

Full JDK thường có `java.sql`. Nhưng một custom image tạo bằng `jlink` có thể thiếu module đó nếu tập modules trong image không khớp với ứng dụng thực tế.

Kiểm tra:

~~~bash
/opt/app/runtime/bin/java --list-modules
~~~

So với JDK build:

~~~bash
java --list-modules
~~~

Nếu custom image không chứa system module cần thiết, chỉ thêm application JAR vào `--module-path` không làm module đó xuất hiện. Phải điều chỉnh cách tạo runtime image và test bản image cuối.

### 22.1. jdeps hỗ trợ nhưng không thấy tất cả phụ thuộc động

~~~bash
jdeps --print-module-deps app.jar
~~~

`jdeps` phân tích static dependencies, có thể giúp chọn modules cho runtime image. Nó không nhất thiết thấy reflection, ServiceLoader, plugin code và các features chỉ load theo cấu hình động.

Nên bổ sung integration tests trên image thật với những luồng ít được dùng, không chỉ startup smoke test.

## 23. ServiceLoader và provider modules

Với named modules, `ServiceLoader` có thể dùng `uses`/`provides` trong module descriptors.

Host:

~~~java
module com.acme.payment.host {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProvider;
}
~~~

Provider:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProvider
        with com.acme.payment.card.CardProvider;
}
~~~

Module provider cần được tìm thấy và được đưa vào layer/module configuration phù hợp theo cách launch hoặc API resolution của hệ thống. Những lỗi liên quan gồm:

- Provider module không observable.
- Provider chưa được resolved vào layer cần thiết.
- `uses`/`provides` hoặc metadata không đúng.
- Provider class không implement cùng runtime SPI type.
- ClassLoader/module-layer identity sai.
- Descriptor `META-INF/services` của legacy plugin bị mất sau shading.

### 23.1. Không thấy provider khác Module not found

Ứng dụng có thể launch hoàn toàn bình thường nhưng `ServiceLoader` tìm thấy 0 provider. Đó có thể là lỗi service binding/registration/visibility chứ không phải boot-layer `FindException`.

Cần test provider discovery và callback thực tế; chỉ kiểm tra JAR nằm trong thư mục `plugins` là chưa đủ.

## 24. ClassLoader identity và plugin systems

JVM phân biệt class identity theo binary name **và defining class loader**. Một plugin JAR có thể vô tình đóng kèm bản sao SPI API:

~~~text
HostClassLoader:
    com.acme.spi.PaymentProvider

PluginClassLoader:
    com.acme.spi.PaymentProvider
~~~

Hai type cùng tên nhưng được định nghĩa bởi loaders khác nhau. Khi host cast plugin về SPI type của host có thể xảy ra `ClassCastException`.

Cách giảm rủi ro:

- Chia sẻ SPI API từ một loader được thiết kế chung.
- Cô lập implementation dependencies khi cần.
- Không bundle bản SPI API không phù hợp vào plugin.
- Test ServiceLoader/TCCL/module layer đúng như production.
- Kiểm tra plugin load/reload và resource cleanup.

Không nên quy tất cả những lỗi `ClassCastException` kiểu này thành split package. Đây là vấn đề identity và class loader topology, dù package trùng cũng có thể là dấu hiệu.

## 25. ModuleLayer động và lỗi ResolutionException

Một số hệ thống nạp plugin vào child layers:

~~~text
Boot Layer
    |
    +-- Host API modules
    |
    v
Plugin Layer A
    +-- plugin-a modules

Plugin Layer B
    +-- plugin-b modules
~~~

Khi gọi các API như `ModuleFinder`, `Configuration.resolve` hoặc `ModuleLayer.defineModulesWithOneLoader`, lỗi resolution có thể phát sinh lúc plugin được nạp, không phải lúc JVM khởi động.

Cần xem:

1. Finder có tìm thấy module artifact không?
2. Module name được yêu cầu có đúng không?
3. Parent layer/configuration có modules cần thiết không?
4. Module graph có split packages không?
5. Loader mapping có vi phạm package constraints không?
6. Shared API module được định nghĩa ở layer nào?
7. ServiceLoader đang dò layer/loader nào?

Một lỗi khi tạo child layer không được sửa chỉ bằng thay `--module-path` cho boot layer nếu code tạo child finder từ đường dẫn khác.

## 26. --patch-module và các trường hợp kiểm thử

`--patch-module` cho phép bổ sung class/resources vào một module trong các trường hợp đặc biệt, thường gặp ở testing.

Ví dụ:

~~~bash
java --patch-module com.acme.app=build/test-classes \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Nó có thể giúp một số test frameworks chạy test classes trong module đang được kiểm thử. Tuy nhiên:

- Không phải cơ chế dependency resolution của Maven/Gradle.
- Không tự sửa graph có module name sai.
- Có thể che khác biệt giữa test và production.
- Không nên dùng để ghép tùy tiện toàn bộ packages từ nhiều module đang xung đột.

Cần chạy smoke trên **distribution không có test-only patches** trước khi phát hành.

## 27. Maven: dependency graph không phải JPMS graph

Một POM có thể có:

~~~xml
<dependency>
  <groupId>com.acme</groupId>
  <artifactId>catalog-api</artifactId>
  <version>2.4.0</version>
</dependency>
~~~

Điều đó cho phép Maven resolve artifact, nhưng compiler/runtime vẫn cần đúng module name và module path configuration.

Kiểm tra:

- `module-info.java` có nằm trong source root phù hợp không?
- Maven Compiler Plugin hỗ trợ JDK target và module-aware compile không?
- Test plugins chạy test trên module path hay classpath?
- Dependency versions thực tế có trùng package/module names không?
- Build reactor có tạo đầy đủ modular artifacts không?
- Annotation processors/generated code có thêm packages trùng không?
- Distribution có copy đủ runtime modules không?

Lệnh:

~~~bash
./mvnw dependency:tree
~~~

giúp thấy Maven dependency resolution, nhưng không thay thế `jar --describe-module` hay runtime `--show-module-resolution`.

### 27.1. Một bẫy test

JUnit tests có thể pass khi Maven test plugin dùng classpath hoặc test-specific module flags, trong khi production chạy named modules theo cấu hình khác. Cần có kiểm thử launch đúng topology production.

## 28. Gradle: inferModulePath không tự sửa split packages

Một project Java Gradle có thể dùng:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

Cấu hình này được hỗ trợ ở những Gradle versions phù hợp và giúp Gradle suy luận cách dùng module path cho tasks liên quan. Nó **không tạo descriptor đúng**, không đổi automatic module names và không giải quyết duplicate packages.

Cần xem riêng:

- `compileJava` module path.
- `test` và test-specific reflective access.
- `runtimeClasspath` và distribution copy.
- Gradle Wrapper và JDK toolchain compatibility.
- Module-aware test execution và packaging.
- Third-party Gradle plugins/annotation processors.

Các lệnh phân tích dependency:

~~~bash
./gradlew dependencies

./gradlew dependencyInsight \
  --dependency catalog-api \
  --configuration runtimeClasspath
~~~

Không suy từ một dependency report rằng module graph đã hợp lệ.

## 29. Shading, fat JAR và nested archives

Shading có thể hợp nhất classes của nhiều JAR thành một archive, nhưng phải xét:

- Duplicate `module-info.class`.
- Nhiều packages cùng tên.
- `META-INF/services` cần merge.
- JAR signatures bị thay đổi khi archive được sửa.
- Automatic module metadata và Multi-Release entries.
- License/NOTICE và resource conflicts.

Một Spring Boot executable JAR thường có nested JARs trong `BOOT-INF/lib` và loader riêng. Nó không tương đương một thư mục explicit named modules trên module path của Java launcher.

Không kết luận “đã modularize” chỉ vì source có `module-info.java` nếu production thực tế vẫn chạy bằng framework loader/classpath layout khác. Cần kiểm tra **artifact cuối và mode launch**.

## 30. Java agents và reflective frameworks có thể gây lỗi khác

Sau nâng JDK, một agent APM hoặc ORM library cũ có thể báo:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
java.lang.UnsupportedClassVersionError
~~~

Những lỗi này không nhất thiết bắt nguồn từ module resolution. Ví dụ:

- `InaccessibleObjectException`: package không mở cho deep reflection.
- `UnsupportedClassVersionError`: classfile vượt runtime hỗ trợ.
- `NoSuchMethodError`: version dependency không khớp.
- `FindException: Module ... not found`: module không observable/resolve được.

Bảng phân loại đúng tầng giúp tránh sửa descriptor hoặc thêm JAR không cần thiết.

## 31. Lệnh JDK hữu ích khi điều tra

### 31.1. Xác định JDK runtime

~~~bash
java -version
java --list-modules
~~~

`--list-modules` liệt kê modules của runtime image hiện tại, không thay thế inventory application modules.

### 31.2. Đọc module descriptor trong JAR

~~~bash
jar --describe-module --file lib/catalog.jar
~~~

Rất hữu ích với automatic module name và explicit descriptors.

### 31.3. Mô tả module theo launcher

~~~bash
java --module-path mods \
  --describe-module com.acme.catalog
~~~

Cho biết thông tin module tìm thấy trong module path được cấu hình.

### 31.4. Quan sát resolution

~~~bash
java --show-module-resolution \
  --module-path "mods:lib" \
  --module com.acme.app/com.acme.app.Main
~~~

Lưu output để so các môi trường.

### 31.5. Phân tích static dependencies

~~~bash
jdeps --module-path "mods:lib" --summary app.jar

jdeps --module-path "mods:lib" --check com.acme.app

jdeps --jdk-internals app.jar
~~~

Cú pháp và lựa chọn phù hợp cần đối chiếu `jdeps --help` của JDK target. `jdeps` không nhất thiết nhận diện reflective/dynamic dependencies.

### 31.6. Xem contents và bytecode

~~~bash
jar --list --file app.jar
javap -verbose -classpath app.jar com.acme.app.Main
~~~

Dùng để xác nhận class tồn tại, package path, classfile version. Chúng không tự chứng minh module readability.

## 32. Test matrix migration JPMS

Một kế hoạch regression có thể gồm:

| Trục | Tổ hợp cần thử |
|---|---|
| JDK | JDK cũ đang hỗ trợ, JDK mục tiêu |
| Launch mode | Classpath, module path nếu đều được hỗ trợ |
| Dependency | Baseline versions, target versions |
| Module type | Explicit, automatic và legacy classpath bridge |
| Runtime image | Full JDK/JRE phù hợp, custom jlink nếu có |
| Packaging | Modular JAR, distribution, framework executable JAR |
| Plugins | Không plugin, một plugin, nhiều plugins |
| Platform | Linux/Windows/container theo cam kết |
| Tests | Compile, resolution, service discovery, reflection, integration |
| Rollback | Old artifact/runtime với cấu hình/dữ liệu còn phù hợp |

Không bắt buộc mọi ô phải pass. Mục tiêu là có bằng chứng cho **những tổ hợp tổ chức cam kết hỗ trợ** và chặn cấu hình sai trước production.

### 32.1. Smoke test cần chạy đúng lệnh production

Ví dụ:

~~~bash
java --module-path "dist/mods:dist/lib" \
  --show-module-resolution \
  --module com.acme.app/com.acme.app.Main
~~~

Một unit test chạy bằng IDE classpath chưa đủ bằng chứng ứng dụng production sẽ resolve modules đúng.

## 33. Một ca migration cụ thể từ Java 8 lên Java 21

Ứng dụng legacy:

~~~text
lib/
├── app.jar
├── legacy-api.jar
├── legacy-impl.jar
└── logging.jar
~~~

Nó chạy:

~~~bash
java -cp "lib/*" com.acme.app.Main
~~~

Đội dự án tạo descriptor:

~~~java
module com.acme.app {
    requires legacy.api;
    requires legacy.impl;
    requires java.logging;
}
~~~

và đổi launcher:

~~~bash
java --module-path lib \
  --module com.acme.app/com.acme.app.Main
~~~

Các lỗi có thể xuất hiện theo chuỗi:

1. `module legacy.api not found` vì tên automatic module thực tế khác.
2. Sau khi sửa tên, `reads package com.vendor.common from both ...` vì legacy-api và legacy-impl cùng package.
3. Sau khi sửa split package, không tìm provider vì ServiceLoader/module registration chưa đúng.
4. Sau khi provider nạp được, framework reflection vào entity package bị chặn.
5. Sau khi mở package đúng phạm vi, app thiếu runtime JDBC driver do distribution copy thiếu dependency.

Một chiến lược có kiểm soát:

**Bước 1:** lưu lệnh classpath baseline, dependency versions và artifact checksums.

**Bước 2:** inventory module names bằng `jar --describe-module`, phân biệt automatic và explicit.

**Bước 3:** chốt runtime dependency versions; loại JAR trùng.

**Bước 4:** sửa ownership của split packages hoặc chọn bridge hợp lệ.

**Bước 5:** viết descriptors `requires`/`exports`/`opens`/`uses`/`provides` đúng kiến trúc.

**Bước 6:** xác nhận build/test tooling chạy trên JDK mới với module path.

**Bước 7:** tạo distribution đủ modules và dependencies, không dựa cache máy developer.

**Bước 8:** kiểm tra resolution trên artifact cuối.

**Bước 9:** chạy integration tests với resources, JDBC, plugins, reflection và external services.

**Bước 10:** có rollback artifact/runtime/launcher rõ ràng.

Không thêm hàng loạt flags một cách không kiểm soát khi mỗi lần lại xuất hiện một lỗi ở tầng khác.

## 34. Khi nào nên giữ classpath trước, modularize sau?

Không phải nâng JDK nào cũng buộc ứng dụng chuyển sang JPMS named modules. Nếu framework/dependency vẫn hỗ trợ classpath, có thể chia:

~~~text
Java 8 + classpath
       |
       | Chỉ đổi runtime, toolchain và compatibility fixes
       v
Java 21 + classpath
       |
       | Sau khi ổn định, thiết kế module boundaries
       v
Java 21 + explicit JPMS modules
~~~

Lợi ích:

- Tách lỗi JDK/runtime khỏi lỗi module graph.
- Dễ so behavior và test compatibility.
- Không buộc sửa tất cả split packages đồng thời.
- Có thời gian trao đổi với vendor của thư viện legacy.
- Dễ rollback một giai đoạn thay vì cả hai.

Nếu sản phẩm thực sự yêu cầu `jlink`/named modules hoặc plugin layers, cần lập lộ trình JPMS; không trì hoãn vô thời hạn mà không có ownership.

## 35. Bảng chẩn đoán nhanh

| Triệu chứng | Tầng nghi ngờ | Bước đầu |
|---|---|---|
| `module not found: X` khi compile | Compiler module path/tên module | `module-info.java` và JAR descriptor |
| `FindException: Module X not found` | Runtime discovery | Runtime module path/artifact |
| Có JAR nhưng module chưa hoạt động | Root/resolution graph | `--show-module-resolution` |
| Two modules with same name | Duplicate artifact/module definitions | Chọn một runtime version |
| `reads package p from both A and B` | Split package/readability | Tìm package owners |
| `package p exists in another module` | Package ownership | Source/JAR entries |
| `package p is not visible` | Readability/exports | `requires` và `exports` |
| `InaccessibleObjectException` | Reflection openness | `opens`/library compatibility |
| `ServiceConfigurationError` | Provider registration/loader | `uses/provides`, service metadata |
| `ClassNotFoundException` | Dynamic loading/classpath | Loader và runtime dependency |
| `NoSuchMethodError` | Binary mismatch | JAR version thực được nạp |
| `ClassCastException` cùng tên class | Different defining loaders | Duplicate API JARs, plugin loader |
| Full JDK chạy, jlink image fail | Missing system modules | `--list-modules` trên image |
| CI pass, production fail | JDK/path/packaging khác | So command, artifact digest |

Không nên kết luận chỉ từ tên exception ngoài cùng. Xem stack trace, runtime version, module graph và artifact thực.

## 36. Các hiểu lầm phổ biến

**“JAR nằm trên module path tức đã resolved.”** Sai: observable khác resolved.

**“Module name trùng artifactId.”** Không chắc: cần kiểm tra descriptor/manifest.

**“Thêm `--add-modules` chữa mọi module not found.”** Không nếu module không observable hoặc tên sai.

**“`--add-opens` chữa module not found.”** Không: opens chỉ tác động reflective access.

**“Chỉ trùng class names mới là split package.”** Sai: cùng package name đã có thể gây conflict khi graph yêu cầu.

**“Automatic module giải quyết hết legacy classpath.”** Không: nó có thể làm lộ split packages và naming problems.

**“requires đồng nghĩa với access vào mọi class.”** Không: cần exports.

**“Maven/Gradle dependency tree là module graph.”** Không: build dependency selection và JPMS resolution có quy tắc khác nhau.

**“Dùng jlink chắc chắn giữ mọi system modules.”** Không: runtime image được tạo theo một tập modules.

**“Đã fix để startup thành công tức plugin cũng chạy.”** Chưa đủ: ServiceLoader, ModuleLayer, reflection và dynamic loading có thể lỗi muộn.

**“Nâng JDK luôn phải thêm module-info.java.”** Không: classpath vẫn là mô hình hợp lệ ở nhiều ứng dụng.

## 37. Checklist triển khai và điều tra

- [ ] Đã xác định JDK vendor/version và runtime image thực tế.
- [ ] Đã ghi đúng launcher command/working directory.
- [ ] Đã phân biệt classpath, module path và module-source-path.
- [ ] Đã kiểm tra module names bằng `jar --describe-module`.
- [ ] Đã biết dependencies nào là explicit/automatic/unnamed.
- [ ] Đã kiểm tra compile và runtime module paths riêng.
- [ ] Đã xác định root modules, `requires` và transitive readability.
- [ ] Đã xem `requires static` có thực sự optional khi runtime không.
- [ ] Đã kiểm tra `--add-modules`/`--limit-modules` trong scripts.
- [ ] Đã loại duplicate module versions/names.
- [ ] Đã xác định package ownership và split packages.
- [ ] Đã phân biệt duplicate class với duplicate package.
- [ ] Đã kiểm tra `exports`/`opens` và quyền truy cập phù hợp.
- [ ] Đã kiểm tra ServiceLoader `uses`/`provides`.
- [ ] Đã kiểm tra class loader/module layer khi có plugins.
- [ ] Đã kiểm tra annotation processor, agents, ORM/test reflection.
- [ ] Đã xác nhận full JDK hoặc jlink image có system modules cần thiết.
- [ ] Đã kiểm tra Maven/Gradle compiler/test/package configuration.
- [ ] Đã chạy production-like module resolution smoke test.
- [ ] Đã chạy integration tests trên artifact/runtime cuối.
- [ ] Đã ghi lại module graph/JAR hashes và exceptions.
- [ ] Đã có phương án rollback build artifact và launcher.
- [ ] Đã tránh để temporary `--add-opens`/`--patch-module` thành giải pháp vĩnh viễn không có owner.

## 38. Kết luận

Các lỗi **module không được tìm thấy**, **package trùng** và **JPMS module resolution** chỉ ra những vấn đề ở các tầng khác nhau. Một module có thể không observable; có mặt nhưng chưa resolved; được resolved nhưng không readable; hoặc readable nhưng không export/open package mà consumer cần. Hai modules có thể tạo conflict khi một reader thấy cùng package từ nhiều nguồn. Cùng lúc, classloader, plugin discovery và custom runtime image còn tạo ra những lỗi có biểu hiện tương tự nhưng nguyên nhân khác.

Cách xử lý đúng là bắt đầu từ **module names, artifact inventory và lệnh launch thật**, dùng `jar --describe-module` và `--show-module-resolution` để xác định graph, loại duplicate versions, xử lý package ownership, rồi kiểm tra exports/opens, ServiceLoader và dynamic layers. Không sửa bừa bằng cách thêm mọi JAR hoặc mở mọi package của JDK.

Trong Java Advance Compatibility Migration, khi điều kiện cho phép, hãy **nâng JDK và ổn định runtime trước, modularize sau trong một đợt có kiểm thử riêng**. Một hệ thống JPMS chỉ được xem là sẵn sàng khi module graph, deployment artifact và các luồng nghiệp vụ quan trọng được kiểm chứng trên đúng JDK và môi trường vận hành mục tiêu.
