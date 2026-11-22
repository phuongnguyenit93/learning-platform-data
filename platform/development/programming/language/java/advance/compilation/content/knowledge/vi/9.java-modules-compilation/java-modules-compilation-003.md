# module-info.java với requires và exports trong Java

Từ Java 9, Java Platform Module System (JPMS) cho phép chương trình khai báo rõ **module**, những module phụ thuộc và những package được công khai làm API. Tệp `module-info.java` là *module declaration*: nó mô tả ranh giới giữa các thành phần lớn hơn package và được trình biên dịch xử lý để kiểm tra quyền truy cập.

Hai từ khóa trung tâm là:

- **`requires`:** module hiện tại cần đọc module nào để có thể dùng những kiểu được công khai phù hợp của module đó.
- **`exports`:** module hiện tại cho phép package nào của mình được sử dụng qua các module boundary theo các quy tắc truy cập thông thường của Java.

Một module `A` viết `requires B;` **không** được dùng mọi class trong `B`: `B` còn phải export package chứa class muốn dùng, và class/member phải có quyền truy cập phù hợp. Ngược lại, `B` viết `exports p;` không tự làm mọi module khác đọc được `B`. Hiểu đồng thời **readability**, **exports** và **Java access modifiers** là chìa khóa để sửa lỗi JPMS.

Bài này sử dụng Java 17+ với ví dụ hoàn chỉnh gồm hai module, phân biệt `requires`, `requires transitive`, `requires static`, `exports ... to`, và giải thích quan hệ với module path, classpath, reflection cùng lỗi thường gặp.

## 1. Module khác package và JAR thế nào?

- **Package** tổ chức namespace cho class, interface, record, enum, annotation; ví dụ `com.example.greetings.api`.
- **Named module** là một đơn vị có tên riêng, sở hữu các package, khai báo các module dependency và bề mặt API qua module descriptor.
- **`module-info.java`** là source mô tả *explicit named module*; khi biên dịch, compiler tạo `module-info.class`.
- **Modular JAR** là JAR có module descriptor. Một JAR bình thường có thể chạy trên classpath mà không cần descriptor. JAR không có descriptor khi đưa lên module path có thể trở thành *automatic module* trong những điều kiện phù hợp.
- **Module path** cho công cụ biết vị trí các module; **classpath** là cơ chế tìm class truyền thống. Chúng có cách giải quyết dependency khác nhau.

Ví dụ một module có hai package:

```text
Module com.example.greetings
    com.example.greetings.api
        Greeting.java
    com.example.greetings.internal
        Formatter.java
```

Thông thường chỉ package `api` cần được công khai. Dù `Formatter` là `public class`, nếu package `internal` không export, một named module khác không thể tự import và sử dụng lớp này qua module boundary.

Trong nhiều dự án build, một module có mã nguồn ở `src/main/java/module-info.java`. Khi thử nhiều module bằng `javac` trực tiếp, có thể bố trí `src/<module-name>/module-info.java`; đây là layout minh họa tương thích với `--module-source-path src`.

## 2. Cấu trúc của module descriptor

Một tệp `module-info.java` hợp lệ:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Một module tiêu thụ có descriptor riêng:

```java
module com.example.app {
    requires com.example.greetings;
}
```

Những điều cần ghi nhớ:

1. Descriptor dùng từ khóa `module`, theo sau là tên module và khối chỉ thị; **không có** `package ...;` hoặc class `ModuleInfo`.
2. `module-info.java` đặt ở gốc phần source của module, không đặt một bản riêng trong từng package.
3. Tên module thường dùng dạng tên miền đảo ngược, nhưng **không bắt buộc phải trùng tên package**.
4. `exports` nhận **tên package cụ thể**, không nhận tên class. Export `com.example.greetings` **không tự export** `com.example.greetings.api`.
5. `requires` nhận **tên module**, không nhận tên package hay tên file JAR.
6. Phần lớn module không cần khai báo `requires java.base;`: Java tự cung cấp quan hệ đọc `java.base` theo quy tắc ngôn ngữ.

Các tệp source Java bình thường nằm trong các package của module và khai báo `package` như thường lệ. Khi compile, `module-info.class` nằm ở gốc output của module.

## 3. Ba điều kiện để truy cập một kiểu từ module khác

Nếu module `com.example.app` muốn dùng `com.example.greetings.api.Greeting`:

| Điều kiện | Trách nhiệm |
| --- | --- |
| Module `com.example.greetings` được resolve và observable | Module path và cấu hình công cụ |
| `com.example.app` đọc được `com.example.greetings` | `requires`, `requires transitive` hoặc quan hệ readability hợp lệ |
| `com.example.greetings` export package `com.example.greetings.api` tới app | `exports`, bao gồm qualified exports nếu có |
| Type/member cho phép truy cập | `public`, `protected`, package-private, `private` theo JLS |

Ba bước đầu liên quan JPMS; bước cuối vẫn là kiểm tra quyền truy cập của ngôn ngữ Java. Có module và biết tên package không có nghĩa bất kỳ kiểu nào cũng truy cập được.

Sơ đồ ý tưởng:

```text
com.example.app                 com.example.greetings
┌──────────────────┐  requires  ┌──────────────────────────┐
│ Main             │ ─────────▶ │ exports ...api           │
│ import Greeting  │            │ api.Greeting (public)    │
└──────────────────┘            │ internal.Formatter       │
                                │   (không export)         │
                                └──────────────────────────┘
```

Mũi tên `requires` biểu thị quan hệ phụ thuộc/readability. `exports` là chính sách của module bên cung cấp, **không** tự tạo mũi tên ngược hay đưa mọi package vào API.

## 4. Ví dụ Java 17+ đầy đủ gồm hai named module

Tạo cấu trúc file ở thư mục dự án `module-lab`:

```text
module-lab/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/example/greetings/
    │       ├── api/Greeting.java
    │       └── internal/Formatter.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

### File 1: src/com.example.greetings/module-info.java

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Package `api` được export; `internal` giữ kín ở ranh giới module.

### File 2: src/com.example.greetings/com/example/greetings/api/Greeting.java

```java
package com.example.greetings.api;

import com.example.greetings.internal.Formatter;

public final class Greeting {
    private Greeting() {}

    public static String hello(String name) {
        return Formatter.format(name);
    }
}
```

`Greeting` là public API. Nó gọi sang `internal.Formatter` vì hai package ở **cùng module**. Không cần `exports internal` cho giao tiếp nội bộ.

### File 3: src/com.example.greetings/com/example/greetings/internal/Formatter.java

```java
package com.example.greetings.internal;

public final class Formatter {
    private Formatter() {}

    public static String format(String name) {
        return "Hello, " + name + "!";
    }
}
```

Class này được cố ý khai báo `public` nhưng package không export, để quan sát **strong encapsulation** của JPMS. `public` chỉ là một trong các điều kiện được truy cập xuyên module.

### File 4: src/com.example.app/module-info.java

```java
module com.example.app {
    requires com.example.greetings;
}
```

### File 5: src/com.example.app/com/example/app/Main.java

```java
package com.example.app;

import com.example.greetings.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.hello("Lan"));
    }
}
```

### Biên dịch

Chạy từ thư mục `module-lab`. Tạo thư mục `mods` trước (ví dụ dùng `mkdir mods`). Dùng lệnh một dòng sau trên Java 17+:

```bash
javac -encoding UTF-8 --module-source-path src -d mods --module com.example.greetings,com.example.app
```

Giải thích:

- `--module-source-path src` sử dụng bố cục `src/<module-name>/...` để tìm nguồn nhiều module.
- `--module` (viết tắt `-m`) chọn hai module cần biên dịch.
- `-d mods` ghi class vào thư mục output theo từng module.
- `-encoding UTF-8` làm rõ charset của tệp Java.

Sau compile, output chứa:

```text
mods/
    com.example.greetings/
        module-info.class
        com/example/greetings/api/Greeting.class
        com/example/greetings/internal/Formatter.class
    com.example.app/
        module-info.class
        com/example/app/Main.class
```

### Chạy

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Stdout chính xác:

```text
Hello, Lan!
```

Trong cú pháp `--module <module>/<main-class>`, phần trước dấu gạch chéo là **tên module**, phần sau là **tên binary class** chứa `main`. Đó không phải đường dẫn vật lý tới file `.class`.

Lệnh này hoạt động tương đương trên Windows, macOS và Linux vì module path chỉ chứa **một entry** `mods`; không có dấu phân cách nhiều entry. Nếu có nhiều đường dẫn, Windows dùng dấu `;` còn macOS/Linux dùng dấu `:`.

Để kết quả rõ ràng, nên chạy lab từ output sạch. Nếu dùng class file còn sót từ lần trước, sẽ khó kết luận lỗi xuất phát từ descriptor hiện tại hay artifact cũ.

## 5. Thiếu requires: module không đọc dependency

Dùng bản sao lab để thử, sửa `src/com.example.app/module-info.java` thành:

```java
module com.example.app {
}
```

Giữ nguyên `Main.java` có `import com.example.greetings.api.Greeting;`. Đây là một **trường hợp cố ý gây lỗi biên dịch**. Dù `Greeting` là `public` và package đã được module thư viện export, module app không khai báo quan hệ đọc đến greetings.

Diagnostic thường có ý nghĩa:

```text
package com.example.greetings.api is not visible
(module com.example.app does not read module com.example.greetings)
```

Đây là thông điệp **minh họa ý nghĩa**, không phải một stdout/stderr cố định cho mọi JDK. Tùy cách compile, thông báo chính xác có thể khác.

Sửa hợp lệ bằng cách khôi phục:

```java
module com.example.app {
    requires com.example.greetings;
}
```

`import` chỉ hỗ trợ dùng tên ngắn trong mã nguồn, không thay thế quan hệ module readability. Tên type có thể được compiler biết nhưng vẫn không hợp lệ nếu module hiện tại không đọc module sở hữu nó.

## 6. Thiếu exports: package không được mở như API

Tiếp tục với một bản sao độc lập, giữ `requires com.example.greetings;` trong app nhưng thay descriptor thư viện thành:

```java
module com.example.greetings {
}
```

Lúc này app đọc được module greetings nhưng **không có quyền dùng package `api`** theo cơ chế truy cập thông thường. Diagnostic thường nhắc `package ... is not visible` do module cung cấp không export package sang app.

Một thử nghiệm khác: khôi phục `exports com.example.greetings.api;` nhưng ở app thử import:

```java
import com.example.greetings.internal.Formatter;
```

Đây cũng là trường hợp không hợp lệ: `internal` không được export, dù `Formatter` là `public class`. Không nên giải quyết bằng cách export mọi package; mục tiêu thiết kế là app gọi API ổn định `Greeting` và không phụ thuộc implementation `Formatter`.

Một chi tiết khác: trong exported package, một class khai báo không có `public` vẫn không trở thành public với module khác. `exports` không nâng visibility của những symbol package-private.

## 7. exports cả package và qualified exports

Cú pháp không giới hạn:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Nó cho phép các module đọc greetings truy cập những kiểu và member hợp lệ của package `api`.

Nếu cần chỉ cho một số module cụ thể:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    exports com.example.greetings.internal to com.example.testing;
}
```

Đây là **qualified export**. Module `com.example.testing` có thể dùng public type trong `internal` **nếu chính nó cũng đọc được** greetings. Các module khác không có export tương ứng.

So sánh:

| Descriptor của provider | Kết quả |
| --- | --- |
| Không export package `p` | Package `p` không có ordinary cross-module public API access |
| `exports p;` | Export tới mọi module có readability thích hợp |
| `exports p to m1, m2;` | Export riêng tới module có tên `m1`, `m2` khi chúng đọc provider |

`exports com.example.greetings;` **không** export `com.example.greetings.api`: Java không có quy tắc “export package thì export tất cả subpackage”.

Tên module đích trong qualified exports cần chính xác. Export tới một module không tự thêm `requires` trong module đó, cũng không cho truy cập class/package-private của package đã export.

## 8. requires transitive và phụ thuộc có mặt trong public API

Giả sử hệ thống có ba module:

```text
com.example.app
      |
      v
com.example.facade
      |
      v
com.example.model
```

Module model:

```java
module com.example.model {
    exports com.example.model.api;
}
```

Module facade công bố API sử dụng các kiểu `User` từ model:

```java
module com.example.facade {
    requires transitive com.example.model;
    exports com.example.facade.api;
}
```

Module app:

```java
module com.example.app {
    requires com.example.facade;
}
```

**`requires transitive`** cho phép module đọc facade cũng được thêm quan hệ đọc tới model theo quy tắc JPMS. Điều này hữu ích nếu API của facade có method nhận/trả các type từ model.

Đừng hiểu transitive là “facade tự export lại mọi class của model”. Model vẫn phải export package chứa `User`; type/member vẫn tuân thủ access control.

Đối chiếu:

- `requires com.example.model;`: facade đọc model; app đọc facade **không tự** đọc model.
- `requires transitive com.example.model;`: facade đọc model và lan truyền readability tới các module đọc facade.

Dùng transitive khi dependency thuộc hợp đồng API, không phải để tránh suy nghĩ module nào thực sự có dependency nào.

## 9. requires static: dependency compile-time, runtime có thể tùy chọn

Ví dụ:

```java
module com.example.report {
    requires static com.example.annotations;
}
```

Ở đây `static` là modifier của **module dependence**, không liên quan static method/field của class. Nó có ý nghĩa:

- Module annotations cần hiện diện trong lúc **biên dịch** để compiler phân giải các type cần thiết.
- Module ấy **không bị yêu cầu bắt buộc để resolution lúc runtime** chỉ vì khai báo `requires static`.
- Nếu code thực tế sử dụng một class của annotations trong luồng chạy mà module ấy vắng mặt, lỗi class loading vẫn có thể xảy ra.

Một số dependency chỉ phục vụ annotation ở compile time phù hợp với lựa chọn này, nhưng không được coi `requires static` là phép “tự động loại bỏ dependency bất kỳ mà vẫn chạy được”.

Có thể gặp tổ hợp `requires static transitive` trong các thiết kế API phù hợp; cần hiểu đồng thời tính optional ở runtime và tính lan truyền readability của JLS.

| Chỉ thị | Có dependency compile-time | Có bắt buộc resolution runtime | Truyền readability tới downstream |
| --- | --- | --- | --- |
| `requires m;` | Có | Có theo quan hệ requires | Không tự động |
| `requires transitive m;` | Có | Có | Có |
| `requires static m;` | Có | Không bắt buộc | Không tự động |

## 10. java.base ngầm định và các module nền tảng khác

Hầu hết module có quan hệ ngầm tới `java.base`, nơi chứa những API phổ biến như `java.lang.String`, `java.util.List` hay `java.nio.file.Path`. Không cần thêm `requires java.base;` cho các ví dụ trong bài.

Nhưng không phải mọi package `java.*` nằm trong java.base. Ví dụ, muốn dùng JDBC:

```java
module com.example.database {
    requires java.sql;
}
```

Muốn dùng HTTP Client API của Java 11+, module có thể cần:

```java
module com.example.httpclient {
    requires java.net.http;
}
```

Đối với một API nền tảng bị compiler báo không thấy, hãy kiểm tra **module chứa API** và `requires` tương ứng. `import java.sql.Connection;` không thể thay thế `requires java.sql;` trong một explicit named module.

## 11. exports khác opens trong reflection

JPMS phân biệt ordinary Java access với **deep reflection**. `exports` làm public API của package khả dụng theo quy tắc ngôn ngữ; điều này không tự cho mọi framework truy cập private field bằng `setAccessible(true)`.

Ví dụ module có thể cho JSON framework phản chiếu vào một package:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.json;
}
```

- `exports ...api` cho ordinary access tới public API, nếu consumer reads module.
- `opens ...internal to com.example.json` cho phép deep reflection ở package internal theo điều kiện JPMS; nó **không biến package internal thành compile-time API** để module khác import tùy ý.
- Trong exported package, reflection thông thường vào public member có thể hợp lệ mà không cần deep opens; không đồng nhất mọi reflection với `opens`.
- `open module m { ... }` là một khai báo khác, mở package của module cho deep reflection, nhưng không tự export mọi package.

Lỗi `InaccessibleObjectException` của thư viện ORM/serialization thường dẫn tới kiểm tra `opens`; lỗi `package ... is not visible` của compiler thường dẫn tới kiểm tra `requires` và `exports`. Đó là hai lớp quyền khác nhau.

Các cờ như `--add-exports` và `--add-opens` dùng để mở rộng quyền trong ngữ cảnh compile/run cụ thể, hữu ích cho migration hoặc chẩn đoán; không nên sử dụng thường xuyên để hợp thức hóa việc ứng dụng phụ thuộc package internal.

## 12. Module path, classpath và automatic modules

Classpath và module path không chỉ khác tên cờ:

| | Classpath | Module path |
| --- | --- | --- |
| Cờ | `-cp` / `--class-path` | `-p` / `--module-path` |
| Đối tượng tìm kiếm | Class theo package/binary name | Module theo module name |
| Source descriptor | Không bắt buộc | Explicit module có `module-info.class` |
| Ranh giới | Access modifiers truyền thống | Thêm readability, exports/opens |
| Launcher | `java -cp ... Main` | `java -p mods -m module/package.Main` |

Class nằm trên classpath thường thuộc **unnamed module** theo class loader tương ứng. Named module không mặc nhiên đọc unnamed module; vì vậy thêm `module-info.java` vào một ứng dụng trước đây chỉ dùng `-cp` có thể khiến một số dependency trên classpath không còn truy cập được từ named module.

**Automatic module** thường là JAR không có descriptor được đặt trên module path. Nó có tên module tổng hợp từ manifest `Automatic-Module-Name` hoặc tên file và được JPMS cung cấp những quy tắc tương thích đặc biệt. Đó là một công cụ migration, không đồng nghĩa với explicit module được thiết kế ranh giới package cẩn thận.

Khi xây dựng thư viện mới, nên xác định tên module ổn định; khi phụ thuộc JAR legacy, kiểm tra module name thực tế thay vì đoán từ artifactId Maven.

## 13. Đóng gói và quan sát module descriptor

Sau khi biên dịch ví dụ hai module, có thể tạo modular JAR từ output của greetings (tạo thư mục `lib` trước):

```bash
jar --create --file lib/com.example.greetings.jar -C mods/com.example.greetings .
```

JAR này có `module-info.class` ở gốc và chứa các class dưới đúng package path. Có thể kiểm tra:

```bash
jar --describe-module --file lib/com.example.greetings.jar
```

Lệnh mô tả module name, requires, exports và các package theo thông tin thực có trong JAR. Không nên cố định nguyên văn output của lệnh cho mọi JDK.

Nếu muốn chạy ứng dụng bằng modular JAR đó, cần cấu hình module path chỉ có **một phiên bản greetings** được chọn rõ. Trong bài lab, `mods` vẫn chứa greetings. Đừng vô tình để nhiều bản cùng tên trên các entry khác nhau rồi mặc định rằng công cụ luôn chọn đúng phiên bản mong đợi.

Với cấu hình ban đầu, lệnh xác định nhất vẫn là:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

Các công cụ hỗ trợ chẩn đoán:

- `java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main`: quan sát module resolution trước khi chạy; log có thể đổi theo JDK.
- `jar --describe-module --file <path-to-jar>`: đọc descriptor hoặc mô tả automatic module nếu JAR không có descriptor.
- `jdeps --print-module-deps ...`: phân tích dependency bytecode theo cơ chế của công cụ; không thể suy ra mọi dependency reflection động.
- `javap -p mods/com.example.greetings/module-info.class`: xem metadata class file của descriptor.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `module not found: com.example.greetings` | Dependency module không có trên module path hoặc tên module sai | Kiểm tra `--module-path`, module name, modular JAR/source |
| `package ... is not visible` / `does not read` | Consumer thiếu quan hệ readability | Kiểm tra `requires` trong descriptor của consumer |
| `package ... is not visible` / `does not export` | Provider không export đúng package tới consumer | Kiểm tra `exports` hoặc qualified exports |
| `cannot find symbol` | Sai tên type, class không tồn tại hoặc context chưa hợp lệ | Kiểm tra import, package, module path, chữ ký, access |
| `InaccessibleObjectException` | Deep reflection bị chặn | Xác định caller/target module và `opens` cần thiết |
| Runtime lỗi module resolution | Module requirement bắt buộc không thỏa hoặc graph không hợp lệ | Kiểm tra đầy đủ runtime module path và descriptor |
| `NoClassDefFoundError` | Dependency cần khi chạy không load được; có thể liên quan `requires static` hoặc class version | Kiểm tra dependency và nguyên nhân gốc |
| Lỗi `UnsupportedClassVersionError` | JVM thấp hơn class-file version được build | Kiểm tra toolchain và `--release` |
| Hai module cùng package dẫn tới conflict | Split packages có thể phá các quy tắc module graph/định nghĩa package | Tách ownership package và rà soát module path |
| IDE chạy nhưng terminal lỗi | IDE thêm module path/cờ compiler khác | So lệnh `javac`, `java` và JDK thực tế |

Một lỗi “package not visible” có thể do **không đọc module** hoặc do **không export package**. Hãy đọc dòng giải thích cụ thể của `javac` trước khi sửa, đừng luôn thêm `exports` vào provider theo phản xạ.

Các nguyên tắc kiểm tra nhanh:

1. Tệp đang chạy thuộc named module hay classpath/unnamed module?
2. Tên module của dependency là gì, và có được resolve không?
3. Consumer có `requires` hoặc quan hệ readability cần thiết không?
4. Provider export đúng package (không phải package cha) tới consumer không?
5. Class/member có `public` hoặc quyền phù hợp không?
6. Lỗi liên quan ordinary access hay deep reflection?
7. Compile-time và runtime module path có chứa **cùng phiên bản** dependency không?

## 15. Khi nào nên dùng requires transitive hoặc qualified exports?

**Thư viện facade có public API phụ thuộc kiểu từ module model:** cân nhắc `requires transitive model` để consumer được hưởng readability cần thiết cho chữ ký API, miễn là model export package phù hợp.

**Thư viện cần gọi implementation module nội bộ nhưng không đưa kiểu của dependency vào API:** dùng `requires dependency` thông thường.

**Một package kỹ thuật chỉ dành cho module bạn kiểm soát:** `exports p to named.consumer;` có thể phù hợp, nhưng nếu package đó thực sự là implementation private thì nên giữ không export.

**Framework cần khởi tạo entity qua reflection sâu:** xét `opens p to framework.module;` thay vì `exports` đại trà; tên module của framework phải đúng với module path thực.

**Dependency chỉ cần khi compile như annotation:** xét `requires static` nhưng cần đánh giá xem runtime code có thực sự phụ thuộc type nào không.

Các modifier này diễn tả quan hệ kiến trúc. Chúng không phải các “mẹo tắt lỗi” có thể thay thế tùy ý.

## 16. Bài tập tự kiểm tra

**1.** `com.example.app` viết `requires com.example.greetings;`. Nếu module greetings không export package `api`, app import `Greeting` được không?

**Đáp án:** Không. Readability đã có nhưng package chưa export.

**2.** Module greetings có `exports com.example.greetings.api;`. Nếu app không có reads relation tới greetings, export có tự đủ để dùng `Greeting` không?

**Đáp án:** Không. Consumer cần đọc provider.

**3.** `exports com.example.greetings;` có tự export `com.example.greetings.api` không?

**Đáp án:** Không. Export chỉ áp dụng chính package được chỉ định.

**4.** Vì sao `Formatter` là `public` nhưng app không được import từ `internal`?

**Đáp án:** Package internal không export; modifier class không tự vượt qua module boundary.

**5.** Facade cung cấp API trả về kiểu `User` của model. Khai báo nào diễn đạt rằng consumer facade cũng cần readability tới model?

**Đáp án:** `requires transitive com.example.model;` trong facade, đồng thời model phải export package cần dùng.

**6.** `requires static com.example.annotations;` có đảm bảo thư viện annotations luôn hiện diện lúc chạy?

**Đáp án:** Không. Runtime resolution không bắt buộc chỉ vì requires static; code phụ thuộc thật vẫn có thể lỗi nếu type vắng.

**7.** Một framework cần đọc private field qua reflection. Chỉ `exports` package model có đủ không?

**Đáp án:** Không nhất thiết; deep reflection thường cần `opens` hoặc cơ chế quyền tương đương phù hợp.

**8.** Sau biên dịch bài lab, chạy lệnh nào và output nào?

**Đáp án:** `java --module-path mods --module com.example.app/com.example.app.Main`; in chính xác `Hello, Lan!`.

## 17. Kết luận và nguồn học chính thức

`module-info.java` tạo bản hợp đồng rõ ràng giữa các module. **`requires`** giúp mô tả dependency và readability; **`exports`** quyết định package nào là API xuyên module; `public` và các quy tắc Java vẫn giới hạn quyền truy cập của từng kiểu và member. `requires transitive` được dùng khi dependency cần lan tới consumer, `requires static` biểu diễn dependency bắt buộc khi compile nhưng tùy chọn lúc runtime, còn qualified exports chỉ chia sẻ package với những module được định danh.

Khi gặp lỗi, hãy tách ba câu hỏi: **module được tìm thấy và đọc được chưa, package được export chưa, và type/member có quyền hợp lệ chưa?** Khi nắm được thứ tự này, các diagnostic của `javac` trở nên dễ hiểu hơn và module descriptor có thể giữ đúng ranh giới kiến trúc.

Tài liệu tham khảo:

- [JLS Chapter 7 — Packages and Modules (`7.7)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html), định nghĩa module và `requires`/`exports`.
- [JDK 21 javac manual](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), đặc biệt `--module-source-path`, `--module-path`, `--module`.
- [JDK 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html), cách khởi chạy named module.
- [java.lang.module JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html), quy tắc resolution/readability.
