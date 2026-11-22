# `Class.getModule()` và thông tin `java.lang.Module`

Từ Java 9, mỗi lớp hoặc interface đang chạy đều gắn với một mô-đun trong Java Platform Module System (JPMS). API `Class.getModule()` trả về đối tượng `java.lang.Module` đại diện cho mô-đun chứa kiểu đó. Từ đối tượng này, chương trình có thể kiểm tra tên mô-đun, descriptor, module layer, class loader, package và các quan hệ đọc/exports/opens đang có tại runtime.

`Module` còn cung cấp một số phương thức để bổ sung quan hệ mô-đun trong lúc chạy, chẳng hạn `addReads`, `addExports` và `addOpens`. Các thay đổi này phục vụ tích hợp động và framework; chúng không sửa file `module-info.class` đã biên dịch.

## 1. `Class.getModule()` trả về điều gì?

Cú pháp:

```java
Module module = SomeClass.class.getModule();
```

Phương thức trả về module mà lớp hoặc interface đó là thành viên. Ví dụ:

```java
Module stringModule = String.class.getModule();
Module appModule = Main.class.getModule();

System.out.println(stringModule.getName());
System.out.println(appModule.getName());
```

`String` thuộc module `java.base`; `Main` thuộc module ứng dụng nếu được biên dịch và chạy như một named module.

### Kiểu mảng và kiểu nguyên thủy

Class object của kiểu mảng thuộc cùng module với kiểu thành phần. Các kiểu nguyên thủy thuộc `java.base`:

```java
String.class.getModule();       // java.base
String[].class.getModule();     // java.base
int.class.getModule();          // java.base
```

Đây là thông tin về module tại runtime. `getModule()` không đọc tên package hay tên class để tự suy ra module.

## 2. Named module và unnamed module

JPMS có hai trường hợp thường gặp:

- **Named module** có tên và module descriptor. Nó thường được khai báo bằng `module-info.java` và được đưa lên module path hoặc nằm trong runtime image.
- **Unnamed module** chứa các lớp được nạp từ classpath bởi một class loader. Mỗi class loader có unnamed module riêng; các lớp trên classpath không trở thành một named module chỉ vì chúng nằm trong một JAR.

Ví dụ kiểm tra:

```java
Module module = Main.class.getModule();

System.out.println("name = " + module.getName());
System.out.println("named = " + module.isNamed());
System.out.println("descriptor = " + module.getDescriptor());
System.out.println("layer = " + module.getLayer());
```

Với named module, `getName()` trả về tên module, `isNamed()` là `true`, `getDescriptor()` trả về descriptor và `getLayer()` thường trả về module layer chứa module đó.

Với unnamed module, `getName()`, `getDescriptor()` và `getLayer()` trả về `null`; `isNamed()` là `false`. Không nên gọi `getDescriptor().name()` mà không kiểm tra `getDescriptor()` trước.

## 3. Các thông tin quan trọng của `java.lang.Module`

`Module` là đối tượng runtime. Những phương thức sau thường được dùng khi kiểm tra cấu trúc mô-đun:

| Phương thức | Thông tin trả về |
| --- | --- |
| `getName()` | Tên module; `null` nếu là unnamed module |
| `isNamed()` | Module có phải named module hay không |
| `getDescriptor()` | `ModuleDescriptor` của named module; `null` với unnamed module |
| `getClassLoader()` | Class loader của module; `null` nếu dùng bootstrap class loader |
| `getLayer()` | `ModuleLayer` chứa module; `null` nếu module không thuộc layer |
| `getPackages()` | Tập tên package thuộc module, kể cả package không export |
| `canRead(other)` | Module hiện tại có readability tới `other` hay không |
| `isExported(packageName, other)` | Package có được export cho module đích hay không |
| `isOpen(packageName, other)` | Package có được mở cho reflection sâu từ module đích hay không |

`getPackages()` liệt kê package thuộc module, không có nghĩa tất cả package đó đều là API công khai. Muốn kiểm tra quyền truy cập từ một module khác, cần xem thêm `isExported` hoặc `isOpen`.

### Đọc descriptor bằng `getDescriptor()`

`ModuleDescriptor` cung cấp cấu hình tĩnh đã khai báo của named module, ví dụ:

- Tên và phiên bản module.
- Các dependency `requires`.
- Package được `exports` hoặc `opens`.
- Service mà module `uses`.
- Service implementation mà module `provides`.

Ví dụ:

```java
Module module = Main.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    System.out.println("module = " + descriptor.name());
    descriptor.requires().forEach(requirement ->
            System.out.println("requires " + requirement.name()));
}
```

Descriptor mô tả các directive đã biên dịch. Những quan hệ được bổ sung động bằng API `Module` hoặc tùy chọn launcher không được ghi ngược vào `module-info.class`.

## 4. Kiểm tra quan hệ giữa các module

Ba nhóm phương thức sau trả lời ba câu hỏi khác nhau:

### `canRead(Module other)` — readability

```java
boolean readable = appModule.canRead(otherModule);
```

Kết quả cho biết module hiện tại có thể đọc module đích trong module graph hay không. Mọi named module đều có dependency ngầm định tới `java.base`, nên `appModule.canRead(String.class.getModule())` thường là `true`.

Readability là điều kiện của module graph; nó không tự export package và không tự mở quyền reflection sâu.

### `isExported(String packageName, Module other)` — truy cập API công khai

```java
boolean exported = libraryModule.isExported("com.example.api", appModule);
```

Kết quả `true` nghĩa là package được export cho module đích (unqualified hoặc qualified export phù hợp). Đây là quyền truy cập package theo quy tắc module; mã vẫn phải tuân thủ các quy tắc truy cập Java như `public`, `protected`, package-private và `private`.

### `isOpen(String packageName, Module other)` — reflection sâu

```java
boolean open = libraryModule.isOpen("com.example.model", appModule);
```

Kết quả `true` nghĩa là package được mở cho module đích để dùng reflection sâu vào các thành viên không `public`. `opens` có mục đích khác `exports`: export công bố API cho mã sử dụng; open cho phép reflection sâu ở runtime.

| Câu hỏi | API kiểm tra | Directive liên quan |
| --- | --- | --- |
| Module A có thể đọc module B? | `canRead(B)` | `requires` |
| Module B có công bố package cho A? | `isExported(package, A)` | `exports` |
| Module B có mở package cho reflection sâu từ A? | `isOpen(package, A)` | `opens` |

## 5. Ví dụ hoàn chỉnh: đọc thông tin module lúc chạy

Ví dụ này chạy như named module. Nó kiểm tra module của ứng dụng, module nền tảng `java.base`, package `java.lang` và descriptor của ứng dụng.

### Cấu trúc thư mục

```text
src/
└── com.example.moduleinfo/
    ├── module-info.java
    └── com/example/moduleinfo/Main.java
```

`src/com.example.moduleinfo/module-info.java`:

```java
module com.example.moduleinfo {
    requires java.logging;
    exports com.example.moduleinfo;
}
```

`src/com.example.moduleinfo/com/example/moduleinfo/Main.java`:

```java
package com.example.moduleinfo;

import java.lang.module.ModuleDescriptor;

public class Main {
    public static void main(String[] args) {
        Module app = Main.class.getModule();
        Module base = String.class.getModule();

        System.out.println("app name = " + app.getName());
        System.out.println("app named = " + app.isNamed());
        System.out.println("base name = " + base.getName());
        System.out.println("app reads java.base = " + app.canRead(base));
        System.out.println("java.lang exported to app = "
                + base.isExported("java.lang", app));
        System.out.println("java.lang open to app = "
                + base.isOpen("java.lang", app));
        System.out.println("app package present = "
                + app.getPackages().contains("com.example.moduleinfo"));
        System.out.println("app layer is boot = "
                + (app.getLayer() == ModuleLayer.boot()));

        ModuleDescriptor descriptor = app.getDescriptor();
        System.out.println("descriptor name = " + descriptor.name());
        System.out.println("requires java.logging = "
                + descriptor.requires().stream().anyMatch(requirement ->
                        requirement.name().equals("java.logging")));
    }
}
```

Biên dịch và chạy từ thư mục chứa `src/`:

```bash
mkdir -p out
javac --module-source-path src -d out -m com.example.moduleinfo
java --module-path out --module com.example.moduleinfo/com.example.moduleinfo.Main
```

Kết quả:

```text
app name = com.example.moduleinfo
app named = true
base name = java.base
app reads java.base = true
java.lang exported to app = true
java.lang open to app = false
app package present = true
app layer is boot = true
descriptor name = com.example.moduleinfo
requires java.logging = true
```

Kết quả cho thấy `java.lang` được export cho ứng dụng nhưng không mở cho reflection sâu. Đây là hai quyền khác nhau. `app.getLayer()` trỏ tới boot layer vì mô-đun ứng dụng được khởi chạy trong layer ban đầu.

## 6. Kiểm tra lớp chạy trên classpath

Đối với lớp chạy trên classpath, `Class.getModule()` trả về unnamed module của class loader đã nạp lớp đó.

```java
Module module = ClasspathMain.class.getModule();

System.out.println("name = " + module.getName());
System.out.println("named = " + module.isNamed());
System.out.println("descriptor = " + module.getDescriptor());
System.out.println("layer = " + module.getLayer());
```

Kết quả tiêu biểu:

```text
name = null
named = false
descriptor = null
layer = null
```

Điều này giúp framework phân biệt lớp thuộc named module với lớp đang chạy trong unnamed module. Không được giả định mọi kết quả `getModule()` đều có tên hoặc descriptor.

## 7. Thay đổi readability trong runtime bằng `Module.addReads()`

Ngoài việc đọc trạng thái module graph, `Module` có API để bổ sung một số quan hệ tại runtime:

- `addReads(other)`: thêm readability từ module hiện tại tới module đích.
- `addExports(packageName, other)`: export một package từ module hiện tại cho module đích.
- `addOpens(packageName, other)`: mở một package của module hiện tại cho reflection sâu từ module đích.
- `addUses(service)`: bổ sung service dependence cho module hiện tại.

Các phương thức này là caller-sensitive: mã gọi phải chạy trong chính module đang được thay đổi. Nếu một module khác cố gọi để thay đổi quan hệ của module đích, lời gọi có thể ném `IllegalCallerException`. Công cụ agent có `Instrumentation.redefineModule` để điều chỉnh các module khác theo quyền của instrumentation.

Những thay đổi động chỉ ảnh hưởng module graph và quyền truy cập của tiến trình hiện tại; chúng không sửa `module-info.java` hoặc JAR trên đĩa. Với cấu hình triển khai, các tùy chọn launcher như `--add-reads`, `--add-exports` và `--add-opens` cũng có thể bổ sung quan hệ khi khởi chạy.

### Ví dụ: thêm readability mà không khai báo `requires` tĩnh

Trong ví dụ này, ứng dụng không khai báo `requires com.example.library`. Module library được resolve riêng bằng `--add-modules`; ứng dụng thêm readability lúc chạy rồi dùng reflection tới một API đã export có giới hạn cho ứng dụng.

`src/com.example.library/module-info.java`:

```java
module com.example.library {
    exports com.example.library to com.example.app;
}
```

`src/com.example.library/com/example/library/Api.java`:

```java
package com.example.library;

public final class Api {
    private Api() { }

    public static String value() {
        return "loaded dynamically";
    }
}
```

`src/com.example.app/module-info.java`:

```java
module com.example.app {
}
```

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) throws Exception {
        Module app = Main.class.getModule();
        Module library = ModuleLayer.boot()
                .findModule("com.example.library")
                .orElseThrow(() -> new IllegalStateException("Library module not found"));

        System.out.println("reads before = " + app.canRead(library));
        app.addReads(library);
        System.out.println("reads after = " + app.canRead(library));

        Class<?> api = Class.forName("com.example.library.Api");
        System.out.println(api.getMethod("value").invoke(null));
    }
}
```

Biên dịch cả hai mô-đun:

```bash
mkdir -p out
javac --module-source-path src -d out -m com.example.library,com.example.app
```

Chạy ứng dụng và đưa library vào tập mô-đun cần resolve:

```bash
java --module-path out --add-modules com.example.library \
    --module com.example.app/com.example.app.Main
```

Kết quả:

```text
reads before = false
reads after = true
loaded dynamically
```

`--add-modules` làm cho library được resolve và có thể tìm thấy trong boot layer. Nó không tự tạo readability từ app tới library; lời gọi `app.addReads(library)` mới thêm cạnh đọc trong runtime. Package được export qualified cho `com.example.app`, nên sau khi có readability, ứng dụng có thể truy cập public API qua reflection.

Ví dụ này minh họa thay đổi runtime. Trong ứng dụng thông thường, nên khai báo `requires` tĩnh nếu dependency là một phần bắt buộc của thiết kế; chỉ dùng `addReads` khi thật sự cần liên kết động.

## 8. ModuleLayer và vị trí module trong runtime

`ModuleLayer` là một tập các mô-đun đã được resolve cùng quan hệ phụ thuộc của chúng. `ModuleLayer.boot()` trả về boot layer chứa các mô-đun hệ thống được resolve khi runtime khởi động.

`Module.getLayer()` cho biết module thuộc layer nào. Từ layer, có thể tìm module theo tên:

```java
ModuleLayer layer = ModuleLayer.boot();
Module javaSql = layer.findModule("java.sql")
        .orElseThrow(() -> new IllegalStateException("java.sql is unavailable"));

System.out.println(javaSql.getName());
```

Module layer tùy chỉnh có thể được tạo khi ứng dụng nạp plugin hoặc nhóm mô-đun độc lập. Khi làm việc với plugin, nên xem cả module name, layer, class loader và các quan hệ đọc/exports/opens thay vì chỉ so sánh tên class.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getName()` trả về `null` | Lớp thuộc unnamed module | Kiểm tra `isNamed()` trước khi dùng tên module |
| `getDescriptor()` trả về `null` | Unnamed module không có module descriptor | Kiểm tra null trước khi truy cập descriptor |
| `canRead()` là `true` nhưng không truy cập được class | Readability không đồng nghĩa package đã export | Kiểm tra `isExported` và quy tắc truy cập Java |
| `isExported()` là `true` nhưng reflection sâu thất bại | Export không thay thế `opens` | Kiểm tra `isOpen` hoặc cấu hình `opens` có phạm vi phù hợp |
| `addReads()` ném `IllegalCallerException` | Mã gọi không chạy trong module đang được sửa | Thực hiện thay đổi từ chính module đó hoặc dùng cơ chế instrumentation phù hợp |
| `findModule()` không tìm thấy module | Module chưa được resolve vào layer đang tìm | Kiểm tra module path và tùy chọn root như `--add-modules` |
| Package xuất hiện trong `getPackages()` nhưng không import được | Package có thể không được export | Kiểm tra descriptor và `isExported` |

## 10. Nguyên tắc sử dụng

1. Dùng `SomeClass.class.getModule()` để xác định module thực sự chứa lớp tại runtime.
2. Kiểm tra `isNamed()` trước khi giả định module có tên hoặc descriptor.
3. Dùng `getDescriptor()` để đọc cấu hình tĩnh của named module; không nhầm nó với các thay đổi runtime.
4. Dùng `canRead`, `isExported` và `isOpen` cho ba câu hỏi khác nhau: readability, API visibility và deep reflection.
5. Ưu tiên khai báo dependency, exports và opens rõ ràng trong `module-info.java` cho kiến trúc ổn định.
6. Dùng các API `addReads`, `addExports`, `addOpens`, `addUses` cho tình huống runtime có chủ đích và kiểm soát phạm vi.
7. Khi phát triển hệ thống plugin, kiểm tra cả `ModuleLayer` và class loader vì chúng ảnh hưởng cách module được nạp và tìm thấy.

## Ghi nhớ

- `Class.getModule()` là điểm bắt đầu để tìm module của một class hoặc interface tại runtime.
- `java.lang.Module` cung cấp tên, descriptor, class loader, layer, package và trạng thái quan hệ mô-đun.
- Unnamed module có `name`, `descriptor` và `layer` là `null`.
- `canRead`, `isExported` và `isOpen` kiểm tra readability, export và mở reflection.
- API `addReads`/`addExports`/`addOpens` có thể bổ sung quan hệ trong runtime nhưng không sửa descriptor đã biên dịch.

## Tài liệu tham khảo

- [Java SE 17 API — `Class.getModule()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule())
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 API — `ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 17 API — `ModuleDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html)