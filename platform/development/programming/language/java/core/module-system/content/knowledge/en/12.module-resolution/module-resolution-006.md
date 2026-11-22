# Missing module và missing package

Khi làm việc với Java Platform Module System (JPMS), hai lỗi thường gặp có tên gần giống nhau nhưng xuất phát từ hai giai đoạn khác nhau: **missing module** nghĩa là module được yêu cầu không được tìm thấy hoặc không thể đưa vào module graph; **missing package** nghĩa là mã nguồn không tìm thấy package cần dùng, hoặc package có tồn tại nhưng module hiện tại không được phép truy cập package đó.

Phân biệt đúng hai loại lỗi giúp chọn cách sửa chính xác. Thêm JAR vào đúng module path có thể giải quyết lỗi thiếu module; khai báo `requires` hoặc `exports` có thể giải quyết lỗi readability và package visibility. Những thao tác này không thay thế cho nhau.

## 1. Module và package không phải một khái niệm

Một **module** là đơn vị đóng gói có tên, dependency và ranh giới truy cập. Named module thường khai báo các thông tin đó trong `module-info.java`.

    module com.example.billing {
        requires com.example.money;
        exports com.example.billing.api;
    }

Một module có thể chứa nhiều package, ví dụ:

    com.example.billing.api
    com.example.billing.internal
    com.example.billing.persistence

Package là đơn vị tổ chức kiểu Java. Module là đơn vị lớn hơn, sở hữu các package và quyết định package nào được module khác truy cập.

Vì vậy:

- Module name như `com.example.money` không nhất thiết trùng package name.
- Một module có thể chứa nhiều package.
- Package không tự trở thành module chỉ vì tên package có nhiều dấu chấm.
- `exports` công bố package; nó không làm module được tìm thấy hoặc được resolve.

## 2. Missing module: module được yêu cầu không tìm thấy

Giả sử module ứng dụng khai báo:

    module com.example.app {
        requires com.example.money;
    }

Khi biên dịch hoặc chạy, JPMS cần tìm một module có tên `com.example.money`. Nếu module đó không có trong các nguồn module mà công cụ đang tìm kiếm, quá trình tìm hoặc resolve module có thể thất bại với lỗi dạng:

    java.lang.module.FindException:
        Module com.example.money not found, required by com.example.app

Nguyên nhân thường gặp:

- JAR của module chưa được đưa vào module path.
- Đường dẫn module path trỏ sai thư mục hoặc sai file.
- Tên module trong `requires` không khớp tên trong `module-info.class`.
- JAR là thư viện cũ trên classpath nhưng ứng dụng lại khai báo `requires` tới nó.
- Module provider hoặc dependency gián tiếp bị thiếu ở runtime.
- Build và runtime sử dụng module path khác nhau.

Điểm cần nhớ: `requires` tham chiếu **module name**, không tham chiếu tên JAR hay Maven/Gradle coordinate. Một file `money-library-1.0.jar` có thể khai báo module name `com.example.money`; tên JAR và tên module không nhất thiết giống nhau.

## 3. Kiểm tra module có được tìm thấy hay không

Có thể dùng `jar --describe-module` để xem module descriptor của một JAR:

    jar --describe-module --file libs/money-library.jar

Nếu JAR là explicit module, kết quả hiển thị tên module được khai báo. Với automatic module, tên có thể được suy ra từ tên JAR hoặc thuộc tính `Automatic-Module-Name` trong manifest.

Có thể liệt kê các module trong JDK hiện tại:

    java --list-modules

Có thể yêu cầu launcher kiểm tra module path:

    java --module-path mods --validate-modules

Với chương trình Java, `ModuleFinder` có thể kiểm tra module name trong một đường dẫn:

    ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

    Optional<ModuleReference> reference =
            finder.find("com.example.money");

    if (reference.isEmpty()) {
        throw new IllegalStateException("Module not found");
    }

Nếu finder không tìm thấy module, hãy kiểm tra vị trí JAR/exploded module, tên module thực tế và cấu hình module path trước khi chỉnh sửa package hoặc source code.

## 4. Module path và classpath là hai nguồn khác nhau

Với ứng dụng dùng named modules, dependency cần được đưa vào module path để JPMS có thể tìm module tương ứng.

Ví dụ biên dịch:

    javac --module-path libs
          --module-source-path src
          -d out
          -m com.example.app

Chạy:

    java --module-path "out;libs"
         -m com.example.app/com.example.app.Main

Trên Windows, dấu phân cách giữa các phần tử của module path là dấu chấm phẩy; trên Linux và macOS, dùng dấu hai chấm.

Nếu chỉ đặt thư viện vào classpath:

    java -cp "app.jar;libs/*" com.example.app.Main

thì các JAR trên classpath thuộc unnamed module của class loader tương ứng. Named module không thể khai báo `requires` tới unnamed module vì unnamed module không có tên.

Một JAR cũ không có `module-info.class` có thể được đặt trên module path để trở thành automatic module. Khi đó nó có tên module và có thể được named module yêu cầu bằng `requires`. Cần xác định đúng tên automatic module thay vì đoán từ tên artifact.

## 5. Missing package: package không có hoặc không truy cập được

Một lỗi package có thể xuất hiện ngay cả khi module chứa thư viện đã được tìm thấy.

Ví dụ source code:

    import com.example.money.Currency;

Nếu compiler báo:

    package com.example.money does not exist

thì package mà source đang import không được tìm thấy trong các module hoặc thư viện mà compilation đang nhìn thấy. Có thể package name bị viết sai, module chứa package không nằm trong cấu hình biên dịch, hoặc package thực tế có tên khác.

Một trường hợp khác là package tồn tại nhưng không được export. Ví dụ module thư viện có:

    module com.example.money {
        // Không export com.example.money.internal
    }

Trong khi ứng dụng viết:

    import com.example.money.internal.CurrencyParser;

Compiler có thể báo package không visible, kèm thông tin package thuộc module nào và module đó không export package cho ứng dụng.

Đây không phải lỗi thiếu JAR: module có thể đã được tìm thấy, nhưng package chưa được công bố theo module descriptor.

## 6. Readability và exports phải cùng phù hợp

Để module A truy cập kiểu public trong package của module B, thông thường cần hai điều kiện:

1. Module A có readability tới module B, trực tiếp qua `requires` hoặc được truyền qua `requires transitive`.
2. Module B export package chứa kiểu đó cho module A, bằng `exports` thông thường hoặc qualified exports phù hợp.

Ví dụ module thư viện:

    module com.example.money {
        exports com.example.money.api;
    }

Module ứng dụng:

    module com.example.app {
        requires com.example.money;
    }

Ứng dụng có thể import:

    import com.example.money.api.Currency;

Nhưng không thể import kiểu trong package chưa export:

    import com.example.money.internal.CurrencyParser;

Thêm `requires com.example.money;` không tự export mọi package. Ngược lại, thêm `exports com.example.money.api;` cũng không giúp ứng dụng truy cập package nếu module ứng dụng không đọc module chứa package đó.

## 7. Phân biệt các thông báo lỗi thường gặp

| Thông báo hoặc tình huống | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| `FindException: Module X not found` | Module X không được tìm thấy trong nguồn module | Module path, tên module, artifact và dependency gián tiếp |
| `module not found: X` khi biên dịch | Compiler không tìm thấy module X được yêu cầu | `--module-path`, tên module và vị trí JAR |
| `package p does not exist` | Package không có trong các nguồn mà compiler đang xét hoặc tên package sai | Package declaration, module/JAR chứa package, cấu hình compilation |
| `package p is not visible` | Package có thể thuộc một module đã biết nhưng không được truy cập theo module graph hoặc exports | `requires`, `requires transitive`, `exports` |
| `module A does not read module B` | A chưa có readability tới B | Dependency trong `module-info.java` hoặc cấu hình readability |
| `does not export package p to module A` | B không công bố package p cho A | `exports p` hoặc `exports p to A` |
| `ClassNotFoundException` | Chương trình yêu cầu class bằng tên nhưng class loader không tìm thấy | Runtime module path/classpath, tên class và loader |
| `NoClassDefFoundError` | JVM không thể tìm hoặc định nghĩa class cần thiết tại runtime | Dependency runtime, module resolution và lỗi khởi tạo class trước đó |

Thông báo cụ thể có thể khác giữa `javac`, Java launcher, IDE và build tool. Hãy đọc toàn bộ thông báo, đặc biệt phần ghi tên module chứa package hoặc module đang yêu cầu dependency.

## 8. Một quy trình chẩn đoán theo thứ tự

Khi gặp lỗi module hoặc package, hãy kiểm tra theo trình tự sau:

**Bước 1 — Xác định giai đoạn lỗi.**

- Lỗi xuất hiện khi compile `module-info.java` hoặc source?
- Lỗi xuất hiện khi launcher resolve module?
- Lỗi xuất hiện khi class loader nạp class?
- Lỗi xuất hiện khi reflection truy cập thành viên?

Không nên xử lý lỗi compile bằng tùy chọn runtime hoặc xử lý lỗi reflection bằng cách thêm JAR.

**Bước 2 — Xác định module name thực tế.**

Chạy:

    jar --describe-module --file libs/dependency.jar

Đối chiếu tên hiển thị với tên trong `requires`. Đừng mặc định Maven artifact, tên JAR và module name là một.

**Bước 3 — Xác định package thực tế.**

Liệt kê nội dung JAR:

    jar --list --file libs/dependency.jar

Kiểm tra đường dẫn class, package declaration và tên đầy đủ của kiểu cần import. Ví dụ đường dẫn `com/example/money/api/Currency.class` tương ứng package `com.example.money.api`.

**Bước 4 — Kiểm tra module descriptor.**

Xác định module ứng dụng có `requires` module thư viện chưa; module thư viện có `exports` package cần thiết chưa. Nếu package chỉ cần reflection, kiểm tra `opens` thay vì thêm `exports` theo phản xạ.

**Bước 5 — So sánh cấu hình compile và runtime.**

Đảm bảo dependency xuất hiện ở cả module path của compiler và module path của launcher. Một dependency có thể tồn tại trong Gradle compile configuration nhưng bị thiếu khỏi runtime configuration.

**Bước 6 — Resolve và chạy lại.**

Dùng cùng bộ artifact và module path ở các bước kiểm tra. Nếu lỗi vẫn còn, đọc tên module hoặc package cụ thể trong thông báo mới để tiếp tục truy nguyên.

## 9. Các tùy chọn bổ sung không thay thế dependency bị thiếu

Một số tùy chọn JVM có thể điều chỉnh module graph hoặc quyền truy cập:

- `--add-modules`: thêm module vào tập module root cần resolve.
- `--add-reads`: bổ sung quan hệ readability giữa các module.
- `--add-exports`: export một package cho module đích ở runtime.
- `--add-opens`: mở package cho deep reflection ở runtime.
- `--patch-module`: bổ sung hoặc thay thế class/resource trong một module được chỉ định.

Các tùy chọn này hữu ích cho kiểm thử, migration hoặc cấu hình runtime đặc biệt. Chúng không tự tải một module hoặc class hoàn toàn không tồn tại. Nếu module X không có trên module path, `--add-reads A=X` không thể làm X xuất hiện. Nếu package không có trong bất kỳ module nào, `--add-exports` cũng không tạo ra package đó.

Với lỗi thiếu artifact, hãy sửa dependency resolution và module path trước. Chỉ dùng các tùy chọn mở rộng khi đã xác định chính xác vấn đề là readability, exports hoặc reflection.

## 10. Phân biệt exports và opens khi lỗi liên quan package

Hai directive thường bị nhầm:

    module com.example.money {
        exports com.example.money.api;
        opens com.example.money.internal;
    }

- `exports` cho phép module khác truy cập kiểu public của package theo quy tắc Java thông thường.
- `opens` cho phép deep reflection vào package ở runtime.
- `open module` mở toàn bộ package của module cho deep reflection.

Nếu compiler báo không thể import kiểu public trong package, hãy xem xét `requires` và `exports`. Nếu framework báo `InaccessibleObjectException` khi truy cập field private, hãy xem xét `opens`. Thêm `opens` không làm package có thể import từ source code.

## 11. Ví dụ tổng hợp: từ missing module đến missing package

Giả sử ứng dụng cần kiểu `Currency` từ thư viện `com.example.money`.

Module thư viện:

    module com.example.money {
        exports com.example.money.api;
    }

Ứng dụng:

    module com.example.app {
        requires com.example.money;
    }

Source:

    import com.example.money.api.Currency;

Nếu JAR thư viện chưa có trên module path, lỗi là missing module. Hãy đưa JAR vào module path và xác nhận tên module bằng `jar --describe-module`.

Nếu JAR đã có và module được tìm thấy, nhưng source đổi thành:

    import com.example.money.internal.CurrencyParser;

thì lỗi là package visibility nếu package internal không được export. Sửa import để dùng API công khai, hoặc thay đổi module descriptor của thư viện nếu package đó thực sự được thiết kế để trở thành API.

Hai bước chẩn đoán khác nhau: tìm thấy module trước, sau đó kiểm tra package có thể truy cập hay không.

## Ghi nhớ

- **Missing module:** module được yêu cầu không được tìm thấy hoặc không thể resolve. Kiểm tra module name, module path và dependency.
- **Missing package:** package không tồn tại trong nguồn đang xét, hoặc package không visible vì readability/exports. Kiểm tra package declaration, `requires` và `exports`.
- **Readability** và **exports** là hai điều kiện khác nhau để truy cập kiểu public từ module khác.
- **Opens** phục vụ deep reflection; nó không thay thế exports.
- Classpath, module path, compile configuration và runtime configuration có thể khác nhau; cần kiểm tra đúng giai đoạn phát sinh lỗi.

Khi xử lý lỗi JPMS, hãy xác định trước module có được tìm thấy không, sau đó mới kiểm tra package, readability và quyền export.