# Class path, module path và các dạng module

Khi nâng cấp Java, đặc biệt từ các ứng dụng trước Java 9 sang JDK hiện đại, không thể chỉ thay JDK rồi giữ nguyên cách đóng gói và nạp thư viện mà không hiểu **class path** và **module path**. Hai cơ chế có thể cùng tồn tại trong một tiến trình JVM, nhưng chúng áp dụng các quy tắc khác nhau về nhận diện mã, giải quyết phụ thuộc, khả năng đọc module, quyền truy cập package và reflection.

**Class path** là mô hình truyền thống: ứng dụng nạp các class từ thư mục hoặc JAR, phần lớn thuộc các *unnamed module*. **Module path** là đầu vào cho Java Platform Module System (JPMS): JVM và các công cụ Java tìm và giải quyết *named module*, từ đó tạo một module graph có quan hệ đọc/được đọc và các ranh giới truy cập rõ ràng. Một JAR bình thường khi đặt trên module path có thể trở thành *automatic module*, nhưng khi đặt trên class path nó vẫn thuộc unnamed module. Vì thế **cùng một JAR, đặt ở hai vị trí khác nhau có thể có vai trò khác nhau**.

Mục tiêu của bài là phân biệt chính xác các cơ chế trên, nhận diện các dạng module trong JPMS và biết cách thiết kế một lộ trình Java compatibility migration mà không tạo ra lỗi class loading, split package, module resolution hoặc reflective access.

## 1. Class path và module path giải quyết hai bài toán khác nhau

### 1.1. Class path: tìm class/resource theo đường dẫn

Trước khi có JPMS, chương trình thường được chạy như sau:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Tùy chọn `-cp` (hoặc `-classpath`, `--class-path`) cung cấp danh sách thư mục và JAR để class loader tìm class/resource. Trên Linux/macOS, các phần tử class path thường được phân cách bằng dấu `:`; trên Windows dùng dấu `;`:

```powershell
java -cp "app.jar;lib/*" com.example.Main
```

Dấu `*` trong class path wildcard được launcher mở rộng để đưa các JAR trong thư mục vào class path theo quy tắc của Java launcher. Thứ tự và xung đột class/resource vẫn cần kiểm soát; không nên dựa vào wildcard để có dependency resolution ổn định.

Class path truyền thống không có khái niệm `requires`, `exports` hay module graph cho mỗi JAR. Nếu một thư viện nằm trên class path và class loader có thể thấy nó, code có thể tham chiếu các public type phù hợp theo quy tắc truy cập của Java. Không có một ranh giới module riêng cho từng JAR đặt trên class path.

Tuy nhiên, điều đó **không có nghĩa class path được bỏ qua mọi quy tắc bảo vệ của JDK hiện đại**. Từ Java 9, Java runtime cũng được tổ chức thành module. Package thuộc named module của JDK có thể không export/open cho ứng dụng class path; đặc biệt strong encapsulation ở JDK hiện đại không thể vượt qua chỉ bằng việc đặt ứng dụng trên class path.

### 1.2. Module path: tìm module và xây dựng module graph

Một ứng dụng modular có thể chạy bằng:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

Ở đây:

- `--module-path` (viết ngắn `-p`) cho module finder biết nơi tìm các module.
- `mods` có thể chứa modular JAR hoặc thư mục module đã biên dịch theo cấu trúc phù hợp.
- `-m` (hoặc `--module`) xác định module khởi chạy, và có thể chỉ định main class sau dấu `/`.
- JVM giải quyết một tập module gồm root module và các phụ thuộc theo quy tắc JPMS, thay vì mặc định coi tất cả JAR trong module path là một tập class phẳng.

Một module có tên có thể công bố: module cần module nào, package nào được truy cập công khai, package nào cho phép reflection sâu và service nào được tiêu thụ/cung cấp.

Điều quan trọng: **có mặt trên module path không đồng nghĩa chắc chắn đã được resolved vào module graph**. Tùy cách khởi chạy và root modules, một JAR có thể nằm trên đường dẫn nhưng không được đọc hoặc thậm chí không tham gia graph. Khi gỡ lỗi, cần phân biệt “module file tồn tại” với “module được resolved” và “module được readable/exported”.

### 1.3. So sánh ở mức vận hành

| Tiêu chí | Class path | Module path |
|---|---|---|
| Đối tượng cốt lõi | Class, JAR và resource | Named module (explicit/automatic) |
| Đơn vị cấu hình | Danh sách path/JAR | Module descriptor hoặc automatic module name |
| Quan hệ phụ thuộc | Không khai báo qua JPMS giữa các JAR class path | `requires`, `requires transitive`, `requires static` |
| Truy cập API | Chủ yếu dựa vào visibility/class loader | Còn phải xét readability và `exports` |
| Reflection sâu | Không có ranh giới module riêng giữa các JAR class path; vẫn chịu ranh giới JDK named modules | Cần `opens` hoặc quyền mở package phù hợp |
| Xung đột package | Nhiều JAR có thể cùng chứa một package, dễ có shadowing | Split package giữa các named module đã resolved thường bị từ chối |
| Nạp thư viện không có descriptor | Thuộc unnamed module | Có thể trở thành automatic module |
| Đầu vào launch | `-cp` + main class | `-p` + `-m` / module main class |
| Mục tiêu migration | Tiếp tục chạy hệ thống legacy | Tạo ranh giới module rõ và kiểm soát phụ thuộc |

## 2. Tên, descriptor và module identity

JPMS có nhiều thuật ngữ dễ bị nhầm:

- **Package:** nhóm kiểu Java có cùng tên package, ví dụ `com.example.catalog.api`.
- **Class binary name:** tên nhị phân của class, ví dụ `com.example.catalog.api.Product`.
- **Module name:** tên module được JPMS dùng, ví dụ `com.example.catalog`.
- **Module descriptor:** khai báo `module-info.java` hoặc `module-info.class`.
- **Module graph:** tập named module đã resolved và các quan hệ readability/exports được xác định.
- **Class loader:** thành phần định nghĩa class lúc runtime; class identity gồm binary name và defining class loader.

Một package không tự động là module. Một Maven group ID hay Gradle project name cũng không tự động trở thành module name. Một JAR có thể chứa nhiều package, và một module có thể được tạo từ một JAR hoặc thư mục module đã biên dịch.

Với hệ thống dùng class loader tùy chỉnh, một class cùng binary name được nạp bởi hai defining class loader khác nhau vẫn có thể là hai type không tương thích với nhau. Vì thế, JPMS không thay thế việc hiểu class loader hierarchy; nó bổ sung một lớp tổ chức và access control.

## 3. Unnamed module: mã đang nằm trên class path

### 3.1. Một class path JAR không trở thành named module

Giả sử:

```text
lib/
  legacy-utils.jar
  jdbc-helper.jar
app/
  Main.class
```

Lệnh:

```bash
java -cp "app:lib/*" com.example.Main
```

đưa các class từ `app` và những JAR class path vào các unnamed module tương ứng với defining class loader. Trong cấu hình launcher đơn giản, phần lớn class của application class loader nằm cùng unnamed module của loader đó.

Không nên diễn đạt thành “chỉ có một unnamed module toàn JVM”: mỗi class loader có unnamed module riêng. Điều này quan trọng với application server, plugin framework, test runner và custom class loader.

### 3.2. Khả năng đọc và truy cập của unnamed module

Unnamed module là cơ chế tương thích cho mã chưa modular hóa:

- Có thể đọc những module mà quy tắc JPMS cho phép trong runtime, bao gồm các named module đã resolved.
- Package trong unnamed module được export và open cho các module khác về mặt mô hình JPMS.
- Nhưng một **explicit named module không tự động đọc unnamed module**. Đây là hướng tương tác thường gây khó khăn khi chuyển một ứng dụng thành named module.

Việc package của unnamed module được coi là mở không có nghĩa ứng dụng có thể reflection sâu vào bất kỳ package nào trong JDK. Các package thuộc named module của JDK vẫn được kiểm soát bằng `exports`/`opens` và các quy tắc strong encapsulation.

### 3.3. Khi nào nên tiếp tục dùng class path?

Giữ class path có thể là lựa chọn hợp lý khi:

- Ứng dụng có nhiều thư viện legacy, chưa có module descriptor và phụ thuộc vào classpath scanning.
- Framework hoặc plugin cần cơ chế class loading động chưa tương thích tốt với modularization.
- Nhóm đang ưu tiên nâng JDK trước khi chia lại module boundary.
- Các lớp truy cập reflection, bytecode generation, agent hoặc dependency phức tạp chưa được kiểm kê.

Không có yêu cầu bắt buộc mọi ứng dụng chạy trên Java 17/21 phải tự chuyển sang named module. JDK hiện đại vẫn hỗ trợ class path. Migration từ Java 8 lên Java 17/21 và migration từ class path sang module path là hai quyết định khác nhau; có thể tách thành hai giai đoạn để giảm rủi ro.

## 4. Explicit named module: module có `module-info.java`

### 4.1. Module descriptor cơ bản

Một explicit module có descriptor ở source:

```java
module com.example.catalog {
    requires java.sql;

    exports com.example.catalog.api;
}
```

Các directive có ý nghĩa:

- `module com.example.catalog`: định danh named module.
- `requires java.sql`: khai báo phụ thuộc module `java.sql`.
- `exports com.example.catalog.api`: cho module khác có quyền truy cập các public type/member của package được export theo những quy tắc visibility thông thường.

Package `com.example.catalog.internal` không được export sẽ là implementation detail ngay cả khi class bên trong là `public`. Từ module khác, `public` không đủ nếu package không được export cho caller.

Module descriptor nằm trong `module-info.class` ở artifact sau compile. Khi JAR có descriptor thích hợp và được đặt trên module path, nó là explicit named module.

### 4.2. Qualified exports: chỉ mở API cho module được chỉ định

Có thể giới hạn export:

```java
module com.example.catalog {
    exports com.example.catalog.api;

    exports com.example.catalog.spi
        to com.example.catalog.testkit;
}
```

Với ví dụ trên, package `api` được export cho mọi module có khả năng đọc `com.example.catalog`. Package `spi` chỉ được export cho named module `com.example.catalog.testkit`.

Qualified export không phải một dạng mã hóa dữ liệu hay sandbox bảo mật hoàn chỉnh. Nó là ranh giới truy cập ở mức ngôn ngữ/JVM module, giúp kiểm soát phụ thuộc và giữ API nội bộ.

### 4.3. `opens` dành cho deep reflection

Framework serialization, dependency injection và ORM thường cần truy cập field hoặc constructor không public bằng reflection. JPMS phân biệt:

- `exports`: cung cấp quyền truy cập thông thường tới public API của package.
- `opens`: cho phép deep reflection vào package trong phạm vi module được nêu.
- `open module`: mở tất cả package của module cho deep reflection, thường là lựa chọn rộng hơn cần cân nhắc.

Ví dụ:

```java
module com.example.orders {
    requires com.fasterxml.jackson.databind;

    exports com.example.orders.api;
    opens com.example.orders.model
        to com.fasterxml.jackson.databind;
}
```

Package `model` có thể không được export như API compile time, nhưng cho phép Jackson thực hiện deep reflection. Cần dùng đúng module name của framework trong environment thực tế, không suy đoán từ Maven artifact ID.

`exports` không thay `opens` cho mọi loại deep reflection, và `opens` không đồng nghĩa public compile-time API cho module khác. Một package có thể vừa export vừa open nếu cả hai mục đích đều cần.

### 4.4. `requires transitive` và `requires static`

Ví dụ:

```java
module com.example.catalog.api {
    requires transitive com.example.types;
    requires static java.compiler;

    exports com.example.catalog.api;
}
```

- `requires transitive`: thể hiện phụ thuộc được truyền tiếp về readability; các module đọc `com.example.catalog.api` có thể đọc `com.example.types` theo quy tắc JPMS. Phù hợp khi API public dùng type của module phụ thuộc và muốn consumer có thể sử dụng mà không khai báo dependency trực tiếp ở mọi nơi.
- `requires static`: phụ thuộc cần được kiểm tra tại compile time nhưng có thể không hiện diện khi chạy, thường gặp với annotation hoặc thư viện chỉ phục vụ compile.

Hai modifier không phải bản sao của Maven scope hoặc Gradle configuration. Cần hiểu cả module graph lẫn dependency graph của build tool. Module có thể được khai báo trong build file nhưng chưa được resolved khi chạy, hoặc ngược lại.

### 4.5. `open module` không phải một dạng module mới về identity

Có thể khai báo:

```java
open module com.example.legacy.bridge {
    requires java.sql;
    exports com.example.legacy.bridge.api;
}
```

Đây vẫn là **explicit named module**. Từ khóa `open` làm tất cả package trong module mở cho deep reflection. Nó không tự export các package chưa export thành compile-time API. Không thể viết thêm directive `opens` tường minh bên trong `open module` vì tất cả package đã được mở.

Trong migration, có thể dùng `open module` như giải pháp chuyển tiếp cho framework cần reflection rộng, rồi thu hẹp dần sang `opens ... to ...` khi đã biết module cần truy cập. Việc mở rộng toàn bộ package nên là quyết định có chủ đích.

## 5. Automatic module: JAR không có descriptor trên module path

### 5.1. Một JAR legacy có thể được JPMS đặt tên

Giả sử thư viện `common-tools.jar` không chứa `module-info.class`. Khi đặt vào class path:

```bash
java -cp "app:lib/common-tools.jar" com.example.Main
```

nó thuộc unnamed module của class loader.

Nhưng khi cùng JAR đó nằm trên module path:

```bash
java --module-path lib -m com.example.app/com.example.app.Main
```

module finder có thể xem nó là một **automatic module** (nếu JAR hợp lệ và có tên module xác định). Automatic module có **tên** để module khác có thể khai báo `requires`, nhưng không có descriptor `module-info.class` do nhà cung cấp viết.

### 5.2. Tên automatic module đến từ đâu?

JPMS có thể lấy module name từ:

1. Thuộc tính `Automatic-Module-Name` trong `META-INF/MANIFEST.MF`.
2. Nếu không có, tên được suy ra từ file name của JAR theo quy tắc của module finder, thường loại phần version và chuẩn hóa tên.

Ví dụ manifest:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.commons
```

Khi đó module có tên ổn định `com.example.commons` dù JAR chưa chứa module descriptor.

**Không nên phụ thuộc vào tên tự suy ra từ file JAR** nếu xây API modular lâu dài. Khi tên file/artifact hoặc quy tắc đóng gói đổi, module name có thể thay đổi và làm `requires` của consumer không còn khớp. Nên xác minh bằng công cụ và ưu tiên tên công bố ổn định của nhà cung cấp.

### 5.3. Quyền truy cập của automatic module

Automatic module được thiết kế để thuận tiện cho migration:

- Có tên module và tham gia module graph.
- Có thể được named module khác tham chiếu bằng `requires <module-name>`.
- Export và open các package của nó theo quy tắc automatic module.
- Có tính readability linh hoạt để tương tác với các named module và class path legacy.
- Có thể được suy ra từ JAR đã tồn tại mà chưa cần sửa source.

Đây là **cầu nối**, không phải tương đương với một explicit module được thiết kế tốt. Automatic module không có ranh giới package export/open tinh chỉnh như `module-info.java` và vẫn có thể gặp lỗi split package, class conflict, tên module không ổn định hoặc dependency chưa được resolved.

### 5.4. Automatic module không giải quyết mọi dependency legacy

Một automatic module có thể phụ thuộc vào các class từ unnamed module; điều này phù hợp với mô hình chuyển tiếp. Nhưng việc module finder/resolution nạp được automatic module không chứng minh mọi dependency ngoài module path đều có mặt ở runtime.

Với cấu hình lai, cần kiểm tra toàn bộ:

- Class path chứa thư viện legacy nào.
- Module path chứa named/automatic module nào.
- Root module nào được resolved.
- Automatic module được gán tên nào.
- Named consumer có đọc đúng module đó không.
- Automatic module có gọi tới class không thể truy cập qua class loader hoặc thiếu dependency không.

Không nên biến toàn bộ thư mục `lib/` thành module path trong một bước rồi kết luận hệ thống sẽ tự thích nghi. Một số JAR cũ có split package hoặc metadata không phù hợp và có thể làm resolution thất bại.

## 6. Các dạng module trong JPMS: bảng tổng hợp

| Dạng | Có tên? | Có `module-info.class`? | Vị trí thường gặp | Export/open package | Use case |
|---|---|---|---|---|---|
| Explicit named module | Có | Có | Module path hoặc runtime image | Theo descriptor | API/ứng dụng được modular hóa |
| Automatic module | Có | Không | JAR trên module path | Theo quy tắc automatic module, rộng hơn explicit | Cầu nối từ JAR legacy |
| Unnamed module | Không | Không | Class path | Theo mô hình unnamed module | Ứng dụng và thư viện legacy |
| Open module | Có | Có, dùng `open module` | Module path | Tất cả package mở cho deep reflection; export theo descriptor | Framework cần reflection rộng |
| System/JDK module | Có | Descriptor do JDK cung cấp | Runtime image | Theo descriptor của JDK | `java.base`, `java.sql`, `java.logging`... |

Lưu ý phân loại: `open module` là **một kiểu khai báo explicit named module**, còn “system module” mô tả nguồn/module của runtime JDK, không phải kiểu module thứ tư thay thế named/automatic/unnamed. Module JDK có thể được khai báo explicit và hiện diện sẵn trong runtime image. Một số công cụ còn dùng các khái niệm module layer, module finder và upgrade module path; đó là cơ chế tổ chức/tra cứu, không nên nhầm với loại module của từng JAR.

### 6.1. Module `java.base`

Mọi named module có quan hệ đọc bắt buộc tới `java.base`, nơi chứa các API nền tảng như `java.lang`, `java.util` và `java.io`. Không cần viết `requires java.base;` trong descriptor thông thường.

Các module JDK khác, ví dụ `java.sql`, `java.xml`, `java.net.http`, được sử dụng bằng quan hệ module phù hợp. Không nên cho rằng mọi module JDK đều tự động được resolved trong mọi cách khởi chạy. Cần đọc cấu hình root modules và module graph thực tế.

## 7. Module resolution, readability và accessibility

Ba bước này giải thích vì sao “JAR đã nằm trên disk” nhưng ứng dụng vẫn lỗi.

### 7.1. Resolution: module có nằm trong graph không?

Khi JVM khởi chạy ứng dụng modular, hệ thống xác định root modules rồi resolve các module được yêu cầu (và các quan hệ phục vụ dịch vụ khi áp dụng). Module không được tìm thấy có thể gây lỗi trước khi main method chạy:

```text
java.lang.module.FindException:
    Module com.example.catalog not found, required by com.example.app
```

Cách gỡ lỗi: kiểm tra file/JAR có nằm đúng module path, module name có đúng và launcher đã nhận đường dẫn chưa. Đừng chỉ nhìn artifactId hoặc file name rồi đoán module name.

### 7.2. Readability: module gọi có đọc module đích không?

Ví dụ:

```java
module com.example.app {
    requires com.example.catalog;
}
```

Module `com.example.app` có quan hệ đọc `com.example.catalog`. Nếu không có quan hệ readability phù hợp, mã trong explicit named module không thể tham chiếu trực tiếp API của named module khác chỉ vì JAR của nó cùng nằm trên module path.

Điều này khác class path, nơi JAR không có descriptor phân ranh giới phụ thuộc.

### 7.3. Accessibility: package có được export hoặc open không?

Ngay cả khi module A đọc module B, class `public` nằm trong package không được export từ B vẫn không trở thành public API của A. Compiler có thể báo package “not visible”, hoặc một binary xây với cấu hình khác có thể gặp `IllegalAccessError`.

Nếu framework dùng deep reflection, vấn đề thường là package không được open cho module đang làm reflection, dẫn đến `InaccessibleObjectException` khi cố gọi `setAccessible(true)`.

Có thể hình dung:

```text
Module được tìm thấy?
      |
      v
Module đã resolved trong graph?
      |
      v
Caller có đọc target module?
      |
      v
Target package có export/open phù hợp?
      |
      v
Java visibility, class loader và runtime linkage hợp lệ?
      |
      v
Lời gọi/reflective access mới thực sự hoạt động.
```

Mỗi tầng có lỗi và biện pháp khắc phục khác nhau. Bổ sung `requires` không tự động mở private field cho reflection; bổ sung `opens` không thay việc thiếu module khi resolution.

## 8. Ví dụ đầy đủ: thư viện và ứng dụng explicit module

Giả sử tạo hai module có cấu trúc:

```text
src/
  catalog/
    module-info.java
    com/example/catalog/api/ProductCatalog.java
  store/
    module-info.java
    com/example/store/Main.java
```

### 8.1. Module thư viện `com.example.catalog`

File `src/catalog/module-info.java`:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

File `src/catalog/com/example/catalog/api/ProductCatalog.java`:

```java
package com.example.catalog.api;

public final class ProductCatalog {
    private ProductCatalog() {
    }

    public static String findName(long id) {
        return "Product-" + id;
    }
}
```

### 8.2. Module ứng dụng `com.example.store`

File `src/store/module-info.java`:

```java
module com.example.store {
    requires com.example.catalog;
}
```

File `src/store/com/example/store/Main.java`:

```java
package com.example.store;

import com.example.catalog.api.ProductCatalog;

public class Main {
    public static void main(String[] args) {
        System.out.println(ProductCatalog.findName(42L));
    }
}
```

### 8.3. Biên dịch và chạy

Ví dụ trên Linux/macOS khi có JDK hỗ trợ JPMS:

```bash
mkdir -p mods/com.example.catalog mods/com.example.store

javac -d mods/com.example.catalog \
    src/catalog/module-info.java \
    src/catalog/com/example/catalog/api/ProductCatalog.java

javac --module-path mods -d mods/com.example.store \
    src/store/module-info.java \
    src/store/com/example/store/Main.java

java --module-path mods \
    -m com.example.store/com.example.store.Main
```

Dự kiến output:

```text
Product-42
```

Trong ví dụ này, thư mục `mods` chứa hai exploded module. Compiler của `store` cần module path chỉ tới `mods` để tìm `com.example.catalog`. Ứng dụng cần `requires com.example.catalog` vì code trực tiếp dùng API từ module đó. Library cần `exports com.example.catalog.api` để consumer có thể gọi public class.

Trên Windows, thay đường dẫn/cách xuống dòng phù hợp với PowerShell hoặc chạy từng lệnh trên một dòng. Các lệnh trong bài nhằm minh họa cơ chế; trong dự án thực tế cần dùng build tool và cấu trúc source set đã được quản lý.

### 8.4. Điều gì xảy ra nếu không export package?

Nếu xóa dòng `exports com.example.catalog.api;` khỏi module thư viện nhưng vẫn giữ `requires` ở application, module vẫn có thể được tìm thấy và đọc. Tuy nhiên, `Main.java` không được phép dùng `ProductCatalog` vì package không export.

Đây là lỗi accessibility, không phải lỗi thiếu JAR. Giải pháp phù hợp là quyết định package đó có thực sự là API công khai; nếu có, export nó có chủ đích. Không nên đổi cả module thành open module để chữa lỗi compile-time export.

## 9. Chạy ứng dụng class path dùng thư viện trên module path

Một migration phổ biến giữ main application trên class path nhưng chuyển một số thư viện sang named/automatic module. Ví dụ:

```bash
java --module-path "mods:lib/modular.jar" \
     --add-modules com.example.catalog \
     -cp app.jar \
     com.example.Main
```

Ở đây `--add-modules com.example.catalog` dùng để bảo đảm module đó là root module được đưa vào resolution trong tình huống launcher không tự resolve nó theo cấu hình hiện tại. Cú pháp path separator trên Windows phải thay phù hợp.

Nếu `com.example.Main` trên class path sử dụng package được export từ `com.example.catalog`, lời gọi có thể hoạt động khi module đã resolved và các điều kiện accessibility đáp ứng.

Không phải mọi named module trên module path đều tự động accessible với ứng dụng class path trong mọi chế độ launch. Hãy dùng:

```bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.example.catalog \
     -cp app.jar com.example.Main
```

để xem những module được resolved và nguyên nhân được đưa vào graph.

## 10. Tương tác giữa explicit, automatic và unnamed module

### 10.1. Bảng định hướng dependency

| Caller | Callee | Điều kiện/hạn chế chính |
|---|---|---|
| Unnamed module | Unnamed module | Theo class loader/class path và Java visibility |
| Unnamed module | Explicit named module | Target cần resolved; package phải export phù hợp |
| Explicit named module | Explicit named module | Cần readability và package export/access phù hợp |
| Explicit named module | Automatic module | Có thể `requires` automatic module theo tên; cần tên ổn định và target được resolved |
| Explicit named module | Unnamed module | Không có `requires` tới unnamed module; cần thay đổi cấu trúc hoặc workaround có giới hạn |
| Automatic module | Named/unnamed module | Có mô hình readability linh hoạt nhằm hỗ trợ migration; vẫn cần dependency thực sự có mặt |

Bảng là mô hình định hướng. Runtime access cuối cùng vẫn chịu class loader, visibility, module graph và loại thao tác (truy cập public API hay deep reflection).

### 10.2. Vì sao explicit module không thể `requires` thư viện class path?

Một named module có descriptor:

```java
module com.example.app {
    requires com.example.legacy;
}
```

chỉ hợp lệ nếu module `com.example.legacy` có thể được tìm thấy như named module (explicit hoặc automatic). Một JAR để **chỉ trên class path** thuộc unnamed module nên không có module name để `requires`.

Có một số hướng migration:

1. Giữ application trên class path ở giai đoạn đầu.
2. Chuyển thư viện legacy JAR sang module path dưới dạng automatic module, kiểm tra tên và split packages.
3. Chọn phiên bản thư viện đã có explicit module descriptor.
4. Tạo adapter riêng nhằm cô lập dependency legacy.
5. Chỉ cân nhắc workaround launcher như `--add-reads ...=ALL-UNNAMED` khi thật sự cần và có kế hoạch gỡ bỏ.

Không nên coi `--add-reads` là cách thiết kế module lâu dài, vì nó tạo một quan hệ đặc biệt không được thể hiện trực tiếp trong descriptor nguồn và có thể khó tái lập giữa IDE, CI, test và production.

### 10.3. Mô hình chuyển tiếp từng tầng

Một hệ thống lớn có thể được tổ chức theo giai đoạn:

```text
Giai đoạn đầu:
  [Ứng dụng + mọi thư viện] -> class path / unnamed modules

Giai đoạn trung gian:
  [Ứng dụng legacy] -> class path
  [Thư viện modular/automatic] -> module path

Giai đoạn tiếp:
  [Ứng dụng explicit named module]
      -> [Thư viện explicit named module]
      -> [Thư viện automatic module]

Giai đoạn mục tiêu:
  [Các module có descriptor và module boundary rõ ràng]
```

Đây là một lộ trình khả thi, không phải yêu cầu bắt buộc cho mọi hệ thống. Nếu chi phí modularization lớn hơn lợi ích, vẫn có thể sử dụng class path trên JDK hiện đại và tập trung vào compatibility runtime.

## 11. Split packages và duplicate classes

### 11.1. Split package là gì?

Split package xảy ra khi các class thuộc cùng package được phân phối qua nhiều JAR/module. Ví dụ:

```text
legacy-api.jar
  com/example/shared/A.class

legacy-impl.jar
  com/example/shared/B.class
```

Trên class path truyền thống, cách đóng gói này có thể hoạt động nhưng vẫn dễ gây xung đột class/resource hoặc phụ thuộc vào thứ tự class loader tìm kiếm.

Trên module path, JPMS không cho phép các resolved named module chia sẻ cùng package theo cách gây xung đột trong cùng module layer. Một bộ thư viện từng chạy bằng class path có thể không thể chuyển nguyên trạng sang module path.

### 11.2. Triệu chứng khi migrate

Các lỗi có thể liên quan đến:

- Hai automatic module chứa chung package.
- Automatic module và explicit module chứa chung package.
- App module mới và module JDK/third-party có package trùng.
- Một bản thư viện trên class path và bản khác trên module path.
- Shaded JAR có package trùng mà không relocation đúng.

Không có cách sửa tổng quát bằng cách thêm `requires` hoặc `opens`. Cần xác định quyền sở hữu package và loại bỏ duplication: nâng thư viện, loại một artifact, relocate code trong quá trình build hoặc giữ hệ thống class path cho đến khi có cấu trúc modular thích hợp.

### 11.3. Duplicate class và class loader

Ngay cả khi không có split package theo nghĩa JPMS, hai JAR có thể cùng cung cấp một class binary name. Trên class path, class loader có thể chọn bản được tìm thấy theo quy tắc của loader, dẫn tới hành vi thay đổi theo thứ tự dependency. Với môi trường plugin, cùng một class có thể tồn tại ở nhiều loader làm xuất hiện `ClassCastException` dù tên class trông giống nhau.

Khi migration, xuất dependency graph cho compile/runtime, kiểm tra JAR thực tế và class loader, không chỉ nhìn version trong build file.

## 12. ServiceLoader trong hệ thống modular

### 12.1. Service contract và provider không nhất thiết phải cùng module

JPMS có directive:

- `uses <ServiceInterface>` trong module tiêu thụ service.
- `provides <ServiceInterface> with <Implementation>` trong module cung cấp implementation.

Ví dụ module tiêu thụ:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
```

Provider module:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingService
        with com.example.provider.impl.DefaultGreetingService;
}
```

Module SPI:

```java
module com.example.spi {
    exports com.example.spi;
}
```

Implementation package không bắt buộc phải export chỉ để `ServiceLoader` tạo provider theo khai báo hợp lệ. Provider cần được tìm thấy và resolved theo service binding hoặc được đưa vào graph bằng cấu hình phù hợp.

Với JAR class path, service provider thường được khai báo trong file:

```text
META-INF/services/com.example.spi.GreetingService
```

nội dung là tên binary của provider class. Khi chuyển JAR từ class path sang module path, cần hiểu quy tắc đọc provider configuration của automatic module và chuyển đúng sang `provides` khi tạo explicit descriptor.

### 12.2. Lỗi service thường không phải do thiếu `requires`

Một provider JAR có thể nằm trên module path nhưng chưa được resolved, hoặc descriptor thiếu `provides`, hoặc provider class không hợp lệ. Khi đó `ServiceLoader` có thể không tìm thấy provider hoặc ném `ServiceConfigurationError`.

Quy trình kiểm tra: xác định module chứa service interface, provider module/name, descriptor, module graph, service binding và cách runtime khởi chạy. Không giả định chỉ copy JAR vào thư mục là đủ.

## 13. Class loading, reflection và module boundaries

### 13.1. Class loader vẫn tồn tại trong thế giới JPMS

Các cơ chế class loading của JVM như bootstrap, platform và application class loader vẫn vận hành. JPMS không làm class loader biến mất. Một module có thể được định nghĩa trong một layer và được gắn với class loader phù hợp; ứng dụng dùng container/plugin vẫn có thể tạo loader hoặc module layer riêng.

Cần phân biệt:

- **Module resolution:** xác định named module nào có trong graph.
- **Class loading:** tìm và định nghĩa class thực tế.
- **Readability:** module gọi có được đọc module đích không.
- **Accessibility:** package được export/open cho loại truy cập cần thiết không.
- **Linkage:** descriptor, class/interface hierarchy và binary API có khớp không.

Một lỗi `ClassNotFoundException` có thể do class loader không tìm thấy class; `FindException` có thể do module resolver không tìm thấy module; `IllegalAccessError` có thể do quyền truy cập; `NoSuchMethodError` có thể do binary API mismatch. Các lỗi này không nên được xử lý bằng cùng một workaround.

### 13.2. Reflection sâu là vùng rủi ro khi nâng JDK

Code như:

```java
Field field = SomeType.class.getDeclaredField("internalState");
field.setAccessible(true);
```

có thể thất bại nếu `SomeType` thuộc named module không open package cho caller, dẫn đến `InaccessibleObjectException`.

Với framework hiện đại, cần xác định module name của thư viện/framework phản chiếu và dùng `opens package to module` có chủ đích. Khi chưa modular hóa ứng dụng, JDK named modules vẫn có thể từ chối reflection vào package nội bộ.

Nếu buộc phải dùng launcher flag:

```bash
--add-opens java.base/java.lang=ALL-UNNAMED
```

cần ghi rõ vì sao, hệ thống nào cần quyền đó và kế hoạch loại bỏ. Flag trên chỉ minh họa cú pháp, **không phải cấu hình khuyến nghị áp dụng toàn hệ thống**. Từ JDK 17, dựa vào `--illegal-access` để mở rộng hàng loạt package nội bộ không còn là biện pháp phù hợp.

### 13.3. Tương thích API khác với tương thích module

Một JAR có thể có bytecode major version phù hợp JDK mục tiêu nhưng vẫn lỗi trên module path vì:

- Không có module cần `requires`.
- Package không được export hoặc open.
- Split package.
- Module name không đúng.
- Service provider không được resolved.
- Framework chỉ giả định class path scanning.
- Native/agent/tooling không hiểu module boundary.

Vì vậy, xác nhận bytecode/source target không đủ để khẳng định hệ thống JPMS tương thích. Cần test trực tiếp trong chính chế độ launch định phát hành.

## 14. Các tùy chọn công cụ JPMS cần biết

| Tùy chọn/công cụ | Mục đích | Lưu ý |
|---|---|---|
| `--module-path` / `-p` | Đường tìm module | Không đồng nghĩa resolve tất cả |
| `--module` / `-m` | Chạy main module | Khác chạy main class bằng `-cp` |
| `--add-modules` | Bổ sung root module khi resolution | Hữu ích với cấu hình lai |
| `--show-module-resolution` | In thông tin module được resolved | Giúp điều tra graph thực tế |
| `--list-modules` | Liệt kê các module có sẵn trong runtime | Không chứng minh application module được resolved |
| `--describe-module` | Xem descriptor của một module | Có thể dùng để hiểu exports/requires |
| `--add-reads` | Thêm cạnh readability lúc chạy | Workaround có giới hạn |
| `--add-exports` | Export thêm package tới module đích | Workaround cho API không export |
| `--add-opens` | Mở package thêm cho reflection | Không thay thế exports trong mọi ngữ cảnh |
| `--patch-module` | Bổ sung/thay class vào named module trong môi trường được phép | Chủ yếu dùng test/compatibility tooling |
| `jdeps` | Phân tích class/package/module dependency | Không thay thế runtime test |
| `jar --describe-module` | Xem mô tả module của JAR | Hữu ích cả với automatic module |
| `jlink` | Tạo custom runtime image từ các module hỗ trợ | Cần đánh giá dependency/automatic module |

### 14.1. Lệnh khảo sát thực tế

```bash
java --version
java --list-modules

jar --describe-module --file lib/example.jar

jdeps --summary app.jar
jdeps --print-module-deps app.jar

java --module-path mods \
     --show-module-resolution \
     -m com.example.app/com.example.app.Main
```

Các lệnh trên chỉ là công cụ khảo sát. `jdeps` suy luận phụ thuộc tĩnh và có giới hạn với reflection/dynamic loading; nó không biết mọi class sẽ được tải theo cấu hình runtime. Với JAR phụ thuộc ngoài, có thể cần cung cấp classpath/module path phù hợp cho `jdeps`.

### 14.2. Các override có tác dụng khác nhau

Ví dụ cú pháp:

```bash
--add-modules com.example.catalog
--add-reads com.example.app=ALL-UNNAMED
--add-exports java.base/jdk.internal.misc=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
```

Không nên dùng tất cả cùng lúc như một “gói sửa lỗi”. Mỗi flag tác động một lớp riêng:

- `--add-modules` hỗ trợ đưa module vào graph.
- `--add-reads` thay đổi readability.
- `--add-exports` cho phép truy cập package theo ranh giới export.
- `--add-opens` cho phép deep reflection vào package theo phạm vi được nêu.

Mỗi override cần có lý do, owner, kiểm thử và kế hoạch loại bỏ. Không để cấu hình chỉ tồn tại trên máy developer nhưng thiếu trong CI, container hoặc JVM production.

## 15. Tác động tới build tool, test và packaging

### 15.1. Gradle và Java toolchains

Một dự án Gradle có `module-info.java` có thể cần cấu hình nhận diện module path và dependency. Với các phiên bản Gradle hỗ trợ, ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.example.store'
    mainClass = 'com.example.store.Main'
}
```

Đây là ví dụ hướng dẫn về cấu hình, không phải cam kết mọi plugin/version tự động hoạt động giống nhau. Nếu thư viện không modular, Gradle có thể xếp dependency lên classpath thay vì module path tùy metadata và cơ chế inference; hãy xác minh compiler args và runtime args thật.

Khi chuyển sang named module, cần kiểm tra:

- Task `compileJava`, `test` và `run`.
- Custom source set và integration test.
- Convention plugin, included build và annotation processor.
- `module-info.java` có nằm ở đúng source set không.
- Test framework có hỗ trợ JPMS/module path trên version đang dùng không.
- Application plugin có khởi chạy bằng module name và main class đúng không.

Một CI build thành công không chứng minh `java -m` trên container production cũng hoạt động nếu task test và runtime dùng classpath khác nhau.

### 15.2. Maven và các plugin

Trong Maven, cần kiểm tra Maven Compiler Plugin, Surefire/Failsafe, module path support, compiler release và cách test engine chạy. Ví dụ khai báo mức Java:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

`release` quản lý source/API/bytecode target, **không tự biến JAR thành explicit module**. Để modular hóa, cần descriptor, cách resolve module và test thật. Maven artifact coordinates cũng không tự quyết định tên JPMS module.

Rà soát parent POM, plugin management, test runtime, annotation processor và generated sources. Với dependency có `Automatic-Module-Name`, kiểm tra chính xác tên module trước khi viết `requires`.

### 15.3. Test và mocking framework

Unit test có thể được chạy trên classpath hoặc module path tùy plugin, version, cấu hình. Một application modular không nhất thiết có test JVM được launch modular giống production.

Những rủi ro phổ biến:

- Framework reflection vào package chưa open.
- Test code cần patch vào module ứng dụng.
- Test dependency là unnamed module nhưng test module không đọc nó.
- Bytecode manipulation và Java agent cần cấu hình tương thích.
- Test pass trên classpath nhưng fail khi đóng gói và chạy module path.

Nếu dùng `--patch-module`, `--add-opens` hay `--add-reads` cho test, ghi nhận rõ vì sao cấu hình test khác runtime. Không mang mọi workaround của test vào production vô điều kiện.

### 15.4. Uber JAR, shading và modular metadata

Shadow/shade có thể gộp nhiều JAR thành một artifact. Với modular JAR, việc gộp class từ các module khác nhau dưới một `module-info.class` đơn lẻ hoặc loại bỏ module descriptor có thể làm thay đổi module identity, exports, service provider và cách runtime nạp class.

Kiểm tra:

- Artifact cuối chứa `module-info.class` nào.
- Manifest có `Automatic-Module-Name` không.
- Có split package, duplicate class hoặc package bị relocate không.
- File `META-INF/services` có được merge đúng không.
- Multi-release JAR có giữ `META-INF/versions/...` và manifest phù hợp không.

Một JAR chạy trên classpath sau shading chưa chắc chạy được trên module path. Nên kiểm thử trực tiếp artifact cuối, không chỉ compile class rời.

### 15.5. Multi-release JAR và module path

Multi-release JAR có thể chứa class khác nhau dưới `META-INF/versions/N/`. Runtime Java chọn implementation phù hợp với phiên bản đang chạy theo quy tắc multi-release khi manifest bật tính năng. Điều này ảnh hưởng class loading và API thực thi, kể cả khi module name không đổi.

Khi phân tích module compatibility, kiểm tra manifest, descriptor được áp dụng theo runtime và những class được chọn trong từng JDK mục tiêu. Không giả định implementation ở JAR root luôn là implementation đang chạy.

## 16. Những lỗi thường gặp khi chuyển class path sang module path

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `Module ... not found` | Tên sai, module path thiếu, root dependency không có | `jar --describe-module`, `--module-path`, descriptor |
| Package “not visible” lúc compile | Caller không đọc module, hoặc package không export | `requires`, `exports`, qualified export |
| `IllegalAccessError` | Quyền truy cập module/class không khớp ở runtime | Readability/export và binary build/runtime |
| `InaccessibleObjectException` | Deep reflection vào package chưa open | `opens ... to ...` và caller module |
| `ServiceConfigurationError` | Provider thiếu, khai báo sai, chưa resolved hoặc không hợp lệ | `uses`/`provides`, META-INF/services, resolution |
| Split package/resolution fail | Hai named modules chứa package trùng | Kiểm kê JAR/module, thay cấu trúc dependency |
| `ClassNotFoundException` | Loader không thấy class hoặc provider cấu hình sai | Classpath/module path/class loader thực tế |
| `NoClassDefFoundError` | Class cần dùng không nạp được khi linkage/initialization | Jar contents, class loader, dependency, cause |
| `NoSuchMethodError` | Bytecode compile với binary API khác runtime | Descriptor và version JAR được nạp |
| Test pass nhưng `java -m` fail | Test và production launch khác chế độ | So sánh test JVM args và runtime command |
| Không truy cập thư viện legacy từ named module | Legacy JAR chỉ trên classpath/unnamed module | Chọn automatic module/adapter hoặc workaround có kiểm soát |
| `requires` bị lỗi sau đổi file JAR | Automatic module name bị suy ra từ tên file | Xác định tên module ổn định, dùng Automatic-Module-Name/explicit descriptor |

Không nên thêm hàng loạt flags chỉ để làm lỗi biến mất. Phải xác định tầng thất bại: module discovery, resolution, readability, export/open, class loader hay ABI. Một lỗi do method descriptor thay đổi không được sửa bằng `--add-opens`.

## 17. Lộ trình migration an toàn

### Bước 1: Chốt mục tiêu

Xác định migration nhằm:

- Chạy ứng dụng trên JDK mới nhưng giữ classpath.
- Đưa một số thư viện lên module path.
- Modular hóa hoàn toàn application.
- Xây custom runtime image bằng `jlink`.
- Cô lập các API nội bộ bằng module boundary.

Nếu chỉ cần nâng JDK từ 17 lên 21, không tự thêm mục tiêu modularization khi chưa có lợi ích và chi phí rõ ràng.

### Bước 2: Kiểm kê dependency và cơ chế class loading

Liệt kê JAR, dependency graph, module descriptor, Automatic-Module-Name, unnamed/automatic/explicit status, plugin/framework scanning và custom class loader.

Phải khảo sát đúng compile/runtime/test classpath, đặc biệt dependency bắc cầu. Một thư viện có thể hiện diện trong build nhưng bị thiếu trong runtime image.

### Bước 3: Kiểm tra split package và xung đột

Tìm package xuất hiện trong nhiều JAR, duplicate class, shaded dependency và các module name trùng nhau. Sửa package ownership trước khi chuyển hàng loạt sang module path.

### Bước 4: Chọn module boundary

Tạo module theo ranh giới API và phụ thuộc thực tế; quyết định package export/open. Tránh export toàn bộ package vì thuận tiện nếu đó là API nội bộ. Kiểm tra cycle giữa các module: JPMS không cho module graph có circular `requires` dependency theo cách vi phạm resolution.

### Bước 5: Làm việc với thư viện chưa modular

Ưu tiên version có explicit descriptor hoặc tên automatic module ổn định. Nếu chưa có, cân nhắc automatic module, giữ classpath hoặc tạo adapter. Đừng ép một library legacy nhiều split package lên module path khi chưa biết hệ quả.

### Bước 6: Cập nhật build, test và launcher

Đảm bảo compiler dùng module path, runtime launch `-m` đúng và module graph được resolve như thiết kế. Ghi rõ `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens` tạm thời.

### Bước 7: Kiểm tra reflection, services và resource

Chạy integration test cho DI, ORM, JSON, ServiceLoader, scanner, agent, JPA entity, configuration và dynamic plugins. Rà soát string-based class names, resource path và native/JNI nếu có.

### Bước 8: Chạy artifact cuối trên runtime thực

Test modular JAR hoặc packaged app giống production. So sánh module graph và dependency graph thực tế, ghi lại JDK vendor/build, container image, JVM args và checksum artifact.

### Bước 9: Phát hành từng bước và chuẩn bị rollback

Chọn canary/rolling/blue-green theo hệ thống. Nếu lỗi module resolution xuất hiện, rollback phải khôi phục đúng tập JAR, module path, classpath, launcher flags và runtime image, không chỉ khôi phục một class.

## 18. Hồ sơ và checklist bàn giao

### 18.1. Mẫu module inventory

| Module/artifact | Vị trí | Dạng | Module name | Cần module nào | API export/open | Ghi chú |
|---|---|---|---|---|---|---|
| `store-app` | Module path | Explicit named | `com.example.store` | `com.example.catalog` | Theo `module-info` | Main module |
| `catalog.jar` | Module path | Explicit named | `com.example.catalog` | `java.base` (implicit) | `com.example.catalog.api` | Thư viện nội bộ |
| `legacy-utils.jar` | Class path | Unnamed | Không có | Theo class loader | Mô hình unnamed | Chưa modular hóa |
| `third-party.jar` | Module path | Automatic | Xác minh từ JAR | Theo resolution | Rộng theo automatic module | Cần theo dõi tên ổn định |

Đây là bảng minh họa cấu trúc. Báo cáo thực tế phải ghi version, checksum, nguồn module name và câu lệnh build/runtime đã kiểm chứng.

### 18.2. Checklist kỹ thuật

- [ ] Đã phân biệt class path, module path và module graph.
- [ ] Đã xác định explicit named, automatic và unnamed module cho từng artifact.
- [ ] Đã xác minh tên automatic module bằng metadata/công cụ, không chỉ đoán từ tên JAR.
- [ ] Đã kiểm tra root modules và module resolution ở runtime.
- [ ] Đã khai báo `requires`/`requires transitive`/`requires static` có chủ đích.
- [ ] Đã kiểm tra `exports` cho public API và `opens` cho deep reflection.
- [ ] Đã rà soát module name của framework và qualified exports/opens.
- [ ] Đã xử lý split package và duplicate class.
- [ ] Đã phân tích dependency tới unnamed module trước khi modular hóa consumer.
- [ ] Đã xác minh ServiceLoader provider và module/service binding.
- [ ] Đã kiểm tra framework scanning, serializer, ORM, agent và plugin loader.
- [ ] Đã kiểm tra Gradle/Maven compiler/test/runtime args trên phiên bản thực tế.
- [ ] Đã kiểm tra shaded/multi-release/final JAR sau bước packaging.
- [ ] Đã chạy integration test với đúng chế độ launcher sẽ dùng ở production.
- [ ] Mọi `--add-reads`, `--add-exports`, `--add-opens` đều có lý do và owner.
- [ ] Đã lưu module inventory, command, artifact checksum, log và phương án rollback.

### 18.3. Tiêu chí hoàn thành

Một bước chuyển sang module path chỉ nên coi là có bằng chứng tương thích khi nhóm chứng minh được: module đúng được tìm thấy và resolved, caller đọc đúng dependency, package export/open đáp ứng nhu cầu, class loader và service provider thực sự hoạt động, test nghiệp vụ pass trên artifact cuối và build/runtime environment có thể tái lập.

**Tóm lại:** class path và module path không chỉ khác nhau ở tên tùy chọn của `java`. Class path giữ mô hình legacy dựa trên class loader và unnamed module; module path đưa JAR vào một module graph với quy tắc readability, exports, opens và resolution. Explicit named module là đích đến khi muốn ranh giới rõ ràng; automatic module là cầu nối; unnamed module vẫn là lựa chọn hợp lệ cho hệ thống chưa modular hóa. Hiểu đúng ba dạng này giúp nâng JDK hoặc chuyển kiến trúc Java mà không nhầm lỗi module với lỗi bytecode, dependency hay framework.
