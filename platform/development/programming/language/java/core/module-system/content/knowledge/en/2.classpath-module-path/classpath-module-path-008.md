# Chẩn đoán lỗi khi trộn classpath với module path

Khi ứng dụng Java vừa dùng thư viện truyền thống qua **classpath** vừa dùng **Java Platform Module System (JPMS)** qua **module path**, lỗi thường xuất hiện ở lúc biên dịch, lúc khởi động hoặc khi truy cập một lớp bằng reflection. Bài này hướng dẫn đọc thông báo lỗi, xác định lớp/module thực sự được nạp và chọn cách sửa ít rủi ro nhất trên Java 9 trở lên.

## 1. Hiểu đúng hai đường dẫn trước khi tìm lỗi

| Khái niệm | Classpath (`--class-path` hoặc `-cp`) | Module path (`--module-path` hoặc `-p`) |
| --- | --- | --- |
| Đơn vị được JVM nhìn thấy | Các lớp thuộc **unnamed module** của class loader tương ứng | Named module có `module-info.class`; JAR không có descriptor có thể thành **automatic module** |
| Khai báo phụ thuộc | Không cần `requires` | Named module dùng `requires tên.module;`; module còn phải được **resolve** |
| Quy tắc truy cập | Không có ranh giới `exports` nội bộ giữa các JAR classpath | Có quy tắc **readability** (module nào đọc được module nào) và **exports** (package nào được sử dụng công khai) |
| Reflection vào thành phần không public | Phụ thuộc quyền truy cập Java/reflection và cơ chế module của đích | Có thêm yêu cầu **opens** hoặc `--add-opens` đối với deep reflection |
| Cách chạy chính | `java -cp ... com.example.Main` | `java -p ... -m ten.module/com.example.Main` |

Một JAR được chuyển từ classpath sang module path **không còn mang cùng cơ chế truy cập**. JAR có descriptor trở thành named module; JAR thông thường trên module path thường trở thành automatic module với tên suy ra từ manifest hoặc tên file. Ngược lại, khi đặt JAR có `module-info.class` lên classpath, các lớp của nó hoạt động theo cơ chế classpath và descriptor không điều khiển module như khi ở module path.

Ba câu hỏi phải trả lời theo đúng thứ tự:

1. **Resolution:** Module chứa lớp cần dùng đã được tìm và đưa vào cấu hình module lúc compile/run chưa?
2. **Readability:** Module gọi có đọc được module cung cấp lớp không?
3. **Accessibility:** Package có được `exports` cho truy cập thông thường, hoặc `opens` cho deep reflection không?

Một lớp tồn tại trong JAR vẫn có thể không dùng được nếu một trong ba điều kiện trên chưa thỏa.

## 2. Quy trình chẩn đoán nhanh

**Bước 1 — Xác định lỗi ở giai đoạn nào.** Ghi lại nguyên lệnh `javac` hoặc `java`, phiên bản JDK, stack trace đầu tiên và cách chạy (IDE, Maven, Gradle, dòng lệnh). Đừng chỉ nhìn câu thông báo cuối cùng.

```bash
java -version
javac -version
```

**Bước 2 — Xác định điểm vào ứng dụng.** Lệnh có `-m ten.module/com.example.Main` là chạy một named module. Lệnh có `-cp ... com.example.Main` chạy main theo classpath. Có thể đồng thời khai báo `-p` và `-cp`, nhưng **khai báo cả hai không có nghĩa tất cả module/JAR tự động nhìn thấy nhau**.

**Bước 3 — Xác nhận JAR được xem là loại module nào.**

```bash
jar --describe-module --file libs/example-lib.jar
```

Đầu ra có descriptor và các `requires`/`exports` cho biết JAR modular. Nếu báo automatic module hoặc derived automatic module, hãy ghi chính xác tên module mà công cụ hiển thị; đừng đoán từ tên file. Kiểm tra bên trong JAR khi cần:

```bash
jar --list --file libs/example-lib.jar
```

**Bước 4 — Quan sát module thực sự được resolve.**

```bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
java --validate-modules --module-path mods
java --list-modules
```

`--show-module-resolution` giúp nhìn tập root module và các dependency được chọn khi khởi động. `--validate-modules` hỗ trợ phát hiện một số xung đột trên module path. `--list-modules` liệt kê các module hệ thống/đang được quan sát bởi launcher với lựa chọn tương ứng; nó không thay thế việc đọc resolution của chính lệnh chạy ứng dụng.

**Bước 5 — Kiểm tra class/module được nạp từ đâu.** Nếu nghi trùng bản JAR, kiểm tra dependency tree của build và dùng class-loading log trên Java 9+:

```bash
java -Xlog:class+load=info --module-path mods -m com.example.app/com.example.app.Main
```

Tìm tên lớp nghi vấn trong log để thấy nguồn nạp thực tế. Dùng lọc log khi ứng dụng quá lớn.

## 3. Bảng nhận diện lỗi và hướng xử lý

| Triệu chứng tiêu biểu | Nguyên nhân cần kiểm tra | Hướng sửa ưu tiên |
| --- | --- | --- |
| `module not found: foo.bar` khi `javac` | `requires foo.bar` nhưng không có module phù hợp trên module path biên dịch, hoặc tên module không khớp | Đưa đúng module/JAR lên `--module-path` và kiểm tra tên bằng `jar --describe-module` |
| `java.lang.module.FindException: Module foo.bar not found` | Module bị thiếu lúc chạy, dù có thể đã có lúc compile | Đồng bộ module path runtime với artifact thực tế; xem graph bằng `--show-module-resolution` |
| `package ... is not visible`; “module ... does not read ...” | Thiếu `requires`, thiếu `--add-modules` hoặc quan hệ readability | Xác định module nguồn, thêm `requires` hợp lệ; với code classpath dùng `--add-modules` khi cần |
| `package ... is not visible`; “does not export ...” | Module đã được đọc nhưng package không được export | Dùng API thuộc package được `exports`; sửa descriptor nếu sở hữu module |
| `IllegalAccessError` có nhắc `does not export` | Runtime có lớp nhưng truy cập không hợp lệ theo JPMS | Căn chỉnh descriptor, phiên bản JAR và đường dẫn runtime; chỉ cân nhắc `--add-exports` khi cần tương thích |
| `InaccessibleObjectException`: “does not opens ...” | Framework dùng deep reflection vào package chưa mở | Sử dụng `opens`/`open module` ở module mình sở hữu hoặc `--add-opens` có giới hạn |
| `ClassNotFoundException` / `NoClassDefFoundError` | Lớp hoặc một dependency gián tiếp không nằm trong cấu hình runtime; có thể module chưa resolve | Đối chiếu classpath/module path khi chạy, dependency tree và class-load log |
| `ResolutionException`; “reads package ... from both ...” | Split package: hai module cung cấp cùng package cho một module đọc | Loại bản trùng, nâng/căn chỉnh thư viện, hoặc tái cấu trúc package |
| `FindException`; “Unable to derive module descriptor” | JAR legacy không phù hợp làm automatic module (ví dụ tên package hoặc phụ thuộc có vấn đề) | Kiểm tra `jar --describe-module`, nội dung JAR và bản thư viện thích hợp |
| `NoClassDefFoundError: ...` chỉ xảy ra trong IDE/test | Classpath/module path của IDE, runner hoặc test khác lệnh chạy chuẩn | So sánh lệnh launch thực tế và cấu hình test runner, không chỉ nhìn pom/build script |

Không kết luận chỉ dựa trên tên exception. Phần **“module X does not read Y”**, **“does not export P to X”**, **“does not opens P to X”** trong thông báo mới chỉ đúng bước bị chặn.

## 4. Ví dụ tối thiểu: hai named module chạy đúng

Giả sử có cấu trúc sau:

```text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/Greeter.java
  com.example.app/
    module-info.java
    com/example/app/Main.java
```

File `src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

File `src/com.example.greeter/com/example/greeter/Greeter.java`:

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() {}
    public static String greet() {
        return "Xin chào JPMS";
    }
}
```

File `src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.greeter;
}
```

File `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
```

Biên dịch và chạy từ thư mục gốc dự án:

```bash
javac -d mods/com.example.greeter src/com.example.greeter/module-info.java src/com.example.greeter/com/example/greeter/Greeter.java
javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
java --module-path mods -m com.example.app/com.example.app.Main
```

Kết quả mong đợi:

```text
Xin chào JPMS
```

Ở đây `mods` là thư mục chứa hai thư mục module dạng exploded. Nếu bỏ `--module-path mods` lúc biên dịch ứng dụng, dòng `requires com.example.greeter;` không được giải quyết và phát sinh `module not found`. Nếu bỏ cùng tùy chọn lúc chạy, launcher không tìm được module ứng dụng hoặc dependency của nó.

## 5. Tình huống A: chương trình classpath gọi thư viện module path

Tạo chương trình truyền thống tại `legacy/LegacyMain.java`:

```java
import com.example.greeter.Greeter;

public class LegacyMain {
    public static void main(String[] args) {
        System.out.println(Greeter.greet());
    }
}
```

Nếu thư viện `com.example.greeter` nằm ở `mods`, chỉ thêm `--module-path mods` thường **chưa đủ** để root-module resolution chọn module thư viện cho một main nằm trên classpath. Nêu module cần resolve rõ ràng khi biên dịch và khi chạy:

```bash
javac --module-path mods --add-modules com.example.greeter -d out-legacy legacy/LegacyMain.java
java --module-path mods --add-modules com.example.greeter --class-path out-legacy LegacyMain
```

`--add-modules com.example.greeter` đưa thư viện vào tập root modules để lớp trong unnamed module có thể dùng package được export. Nếu còn lỗi `does not export`, thay đổi `--add-modules` không mở được package bị ẩn: cần xem `exports` của module thư viện.

Khi chạy code classpath với nhiều JAR:

```bash
# Linux/macOS: ngăn cách nhiều mục classpath bằng dấu hai chấm
java -cp "out-legacy:libs/dependency.jar" LegacyMain

# Windows: dùng dấu chấm phẩy
java -cp "out-legacy;libs/dependency.jar" LegacyMain
```

Dấu phân cách classpath khác nhau giữa hệ điều hành. `--module-path` nhiều phần tử cũng tuân theo dấu phân cách đường dẫn tương ứng. Ví dụ phía trên về JPMS chỉ có một mục đường dẫn nên dùng chung được.

## 6. Tình huống B: named module cần dùng thư viện legacy

Giả sử ứng dụng có `module-info.java` và cần thư viện `legacy-util-1.0.jar` vốn chưa khai báo module.

**Cách chuyển tiếp thường phù hợp:** đặt JAR legacy trên module path để nó trở thành **automatic module** (nếu JAR hợp lệ), lấy tên module chính xác từ:

```bash
jar --describe-module --file libs/legacy-util-1.0.jar
```

Nếu công cụ xác nhận tên `legacy.util`, module ứng dụng có thể khai báo:

```java
module com.example.app {
    requires com.example.greeter;
    requires legacy.util;
}
```

Và đặt cả các module ứng dụng lẫn JAR thư viện trên module path:

```bash
# Minh họa phần đường dẫn; đặt các mục theo hệ điều hành
java --module-path "mods;libs/legacy-util-1.0.jar" -m com.example.app/com.example.app.Main
```

Ví dụ lệnh vừa rồi dùng dấu `;` theo Windows; Linux/macOS dùng `:`. Tên `legacy.util` chỉ là **ví dụ**, không được đưa vào `requires` trước khi kiểm tra JAR thật. Tên automatic module suy ra từ file có thể thay đổi khi đổi tên artifact; với thư viện do mình quản lý, thêm `Automatic-Module-Name` trong manifest giúp ổn định tên trong thời gian chuyển tiếp. Automatic module không có cùng mức đóng gói nghiêm ngặt với explicit module và vẫn có thể gặp split package, module naming hoặc lỗi phụ thuộc.

**Trường hợp không thể chuyển thư viện lên module path:** Một named module không thể viết `requires ALL-UNNAMED;` hay `requires ten.jar.tren.classpath;` để khai báo phụ thuộc vào unnamed module. Có thể dùng giải pháp tương thích đặc biệt với `--add-reads com.example.app=ALL-UNNAMED`, kết hợp classpath chứa JAR legacy, ở cả giai đoạn cần thiết của compile/run; nhưng cấu hình này nên được xem như bước chuyển đổi tạm thời vì làm suy yếu ranh giới module và dễ bị quên trong IDE/test/production.

## 7. Tình huống C: nhầm `exports`, `opens` và `--add-reads`

Ba quyền khác nhau:

- `requires com.example.lib;`: named module **đọc** module `com.example.lib`; nó không tự xuất mọi package của thư viện.
- `exports com.example.api;`: cho module khác dùng các kiểu `public` trong package đó theo quy tắc thông thường. Có thể giới hạn: `exports com.example.internal to com.example.client;`.
- `opens com.example.model;`: cho phép deep reflection vào package, ví dụ framework đọc field/constructor không public, theo các kiểm tra truy cập tương ứng. Có thể giới hạn: `opens com.example.model to com.example.framework;`.

Ví dụ một framework trên classpath phản ánh vào package `java.lang` và gặp lỗi `InaccessibleObjectException`. Với trường hợp thật sự buộc tương thích, một phương án launch tạm thời là:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar" com.example.Main
```

Đối với quyền truy cập thông thường vào package không export, cơ chế tương thích khác là:

```bash
java --add-exports ten.module/com.example.internal=ALL-UNNAMED -cp "app.jar" com.example.Main
```

Đừng dùng `--add-exports` để chữa lỗi reflection cần `opens`, hoặc dùng `--add-opens` để chữa lỗi không tìm thấy module. Khi nguồn module do mình sở hữu, cập nhật `module-info.java` chính xác thường bền vững hơn. Với JDK internals, ưu tiên API được hỗ trợ và phiên bản framework mới; các cờ tương thích có thể không còn thích hợp sau nâng JDK.

## 8. Tình huống D: dependency bị nhân đôi hoặc split package

Ví dụ `lib-old.jar` và `lib-new.jar` cùng chứa package `com.vendor.util`; khi cả hai là named/automatic modules trên module path và một module đọc cả hai, JPMS có thể từ chối resolution vì **split package**. Tương tự, một JAR được khai báo ở cả classpath và module path có thể gây nhầm lẫn về nguồn lớp được nạp hoặc phiên bản dependency.

Hãy tìm dấu vết theo thứ tự:

1. Chạy `jar --describe-module --file ...` với các JAR nghi vấn để biết tên module.
2. Chạy `jar --list --file ...` để kiểm tra các package xuất hiện trong từng JAR.
3. Đọc dependency tree/đường dẫn launch thực tế, đặc biệt khi framework tự tạo đường dẫn.
4. Giữ một bản dependency nhất quán; loại JAR trùng hoặc điều chỉnh phiên bản ở build tool.
5. Nếu hai module thật sự cùng chứa một package cần dùng, tái cấu trúc/shading theo chủ đích hoặc dùng phiên bản thư viện JPMS-ready; đừng chỉ thêm `--add-reads`.

Classpath có cơ chế chọn lớp theo thứ tự tìm kiếm, còn JPMS kiểm soát package/module ở giai đoạn resolution. Vì vậy cùng tập JAR có thể “chạy được trên classpath” nhưng lỗi khi chuyển sang module path; đây là tín hiệu cần xử lý dependency, không phải chỉ đổi cờ JVM.

## 9. Tình huống E: chạy được ở CLI, lỗi trong IDE, test hoặc khi đóng gói

Đừng suy luận cấu hình runtime từ thành công biên dịch. Kiểm tra **lệnh Java thực tế** mà IDE, JUnit/test plugin, Maven hoặc Gradle sinh ra:

- Main class đang được chạy bằng `-cp` hay `-m`? Có nhầm chuyển named module thành chương trình classpath không?
- `--module-path`, `--class-path`, `--add-modules`, `--add-opens` có xuất hiện đầy đủ trong **lệnh chạy và lệnh test** không?
- Có khác phiên bản JDK giữa terminal, IDE, CI và production không?
- Test có sử dụng `--patch-module` hoặc classpath riêng khiến các lớp test và module ứng dụng nằm ở cấu hình khác không?
- Các JAR chạy thực tế có đúng phiên bản và cùng tên module như lúc biên dịch không?

Các bản chạy `jlink` chỉ chứa module được đưa vào image và module phụ thuộc phù hợp; khi đóng gói, xác minh module cần thiết đã được đưa vào image. Với ứng dụng chạy trực tiếp, xem `--show-module-resolution` để biết chính xác graph mà launcher chọn.

## 10. Chọn giải pháp theo kiến trúc dự án

| Kiến trúc hiện tại | Cấu hình nên ưu tiên | Điểm cần kiểm tra |
| --- | --- | --- |
| Ứng dụng và thư viện đều là named modules | `--module-path`; `requires` và `exports` đầy đủ | Tên module, graph, split package |
| Main ở classpath, thư viện ở module path | `-cp` cho main, `-p` cho thư viện, `--add-modules` khi thư viện chưa được resolve | Package cần dùng phải export |
| Main named module, thư viện JAR legacy | Chuyển JAR phù hợp sang automatic module; sau đó khai báo `requires` | Tên automatic module, dependency bắc cầu, split package |
| Ứng dụng hoàn toàn legacy chưa có nhu cầu JPMS | Giữ cấu hình classpath thống nhất trong giai đoạn chuyển đổi | Tránh vô tình đưa một phần dependency sang `-p` |
| Framework dùng reflection vào named module | `opens` package cần thiết, có thể giới hạn đích | Quyền reflection khác quyền import kiểu `public` |

**Thứ tự sửa khuyến nghị:** đúng artifact và version → đúng classpath/module path → đúng module name và root modules → đúng `requires`/readability → đúng `exports`/`opens` → chỉ sau cùng mới cân nhắc cờ tương thích. Mỗi lần chỉ thay đổi một nguyên nhân có bằng chứng từ message hoặc module-resolution log.

## 11. Bộ lệnh thực hành để lưu lại khi điều tra

```bash
# JDK hiện đang dùng
java -version
javac -version

# JAR modular hay automatic module? Tên module chính xác là gì?
jar --describe-module --file libs/example-lib.jar

# Kiểm tra file có trong JAR
jar --list --file libs/example-lib.jar

# Module-path có xung đột rõ ràng?
java --validate-modules --module-path mods

# Launcher resolve những module nào cho entry point?
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main

# Lớp nào được nạp và nạp từ đâu? (Java 9+)
java -Xlog:class+load=info --module-path mods -m com.example.app/com.example.app.Main

# Phân tích dependency của một JAR để hỗ trợ quá trình modular hóa
jdeps --recursive libs/example-lib.jar
```

Thay tên file/module và đường dẫn theo dự án thực. Nếu `jdeps` báo missing dependency, bổ sung đường dẫn thư viện cần thiết rồi chạy lại để có bức tranh phụ thuộc đầy đủ; `jdeps` phân tích dependency tĩnh, không thể chứng minh mọi tương tác qua reflection.

## 12. Câu hỏi tự kiểm tra khi gặp lỗi mới

1. JAR chứa lớp đang nằm trên classpath, module path, hay cả hai?
2. Khi kiểm tra bằng `jar --describe-module`, tên module và loại module thực tế là gì?
3. Module đích có được resolve không? Nếu không, cần thêm `requires`, chỉnh `-p` hay `--add-modules`?
4. Module gọi đã có quyền đọc module đích chưa?
5. Package cần import có được export tới module gọi không?
6. Nếu lỗi xảy ra trong reflection, package đích có được open tới đúng module/framework không?
7. Có bản JAR trùng, split package, hoặc khác cấu hình compile/runtime/test không?
8. Sau khi sửa, lệnh chạy thực tế có còn đúng khi đưa vào IDE, CI và bản deploy không?

Khi trả lời được tám câu hỏi này bằng thông báo lỗi, thông tin JAR và dòng lệnh thực tế, phần lớn lỗi trộn classpath/module path có thể được khoanh vùng thành **thiếu resolution, thiếu readability, thiếu exports/opens hoặc xung đột dependency**.