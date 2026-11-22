# JAR không có module descriptor trên module path trong Java

Một JAR không chứa `module-info.class` nhưng được đặt trên **module path** sẽ được JPMS xem là một **automatic module** (mô-đun tự động). JVM và các công cụ Java tạo một module descriptor ngầm từ tên JAR hoặc thuộc tính `Automatic-Module-Name` trong manifest. Nhờ đó, một ứng dụng dùng named module có thể khai báo `requires` tới thư viện cũ mà chưa cần sửa chính JAR đó.

Điểm cần phân biệt ngay từ đầu: cùng một JAR nếu đặt trên **classpath** thì thuộc unnamed module, không phải automatic module. Vị trí nạp JAR quyết định cách JPMS nhìn nhận nó.

## 1. JAR không có descriptor được xử lý thế nào?

JPMS có thể gặp ba dạng thư viện:

| Dạng JAR | Vị trí | Cách Java nhìn nhận |
|---|---|---|
| Explicit modular JAR | Module path | Có module descriptor thật, thường là `module-info.class`. |
| JAR không có descriptor | Module path | Automatic module, descriptor được suy ra khi tìm module. |
| JAR không có descriptor | Classpath | Các lớp thuộc unnamed module của class loader; không có tên automatic module để dùng trong `requires`. |

Automatic module là cơ chế chuyển tiếp giúp thư viện chưa được modularize tham gia module graph. JAR vẫn giữ nguyên nội dung bytecode cũ; module descriptor được suy ra khi công cụ Java tìm JAR trên module path.

`Automatic-Module-Name` trong manifest chỉ cung cấp tên module ổn định. Thuộc tính này không phải `module-info.class` và không biến JAR thành explicit module.

## 2. Tên của automatic module

JPMS xác định tên theo thứ tự ưu tiên:

1. Nếu manifest có thuộc tính `Automatic-Module-Name`, dùng giá trị đó làm tên module.
2. Nếu không có thuộc tính này, suy ra tên từ tên file JAR.

### Dùng `Automatic-Module-Name`

Ví dụ manifest của thư viện:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy

```

Với JAR tên `legacy-greeting-2.4.1.jar`, tên module vẫn là `com.acme.legacy`, không phụ thuộc tên file. Nhà phát hành thư viện nên đặt tên này ổn định giữa các phiên bản để ứng dụng không phải thay `requires` khi JAR được đổi tên hoặc nâng version.

Thuộc tính cần có giá trị là tên module hợp lệ, dùng các thành phần Java identifier phân cách bằng dấu chấm. Tránh tên chung chung dễ trùng với thư viện khác.

### Suy ra tên từ tên file

Nếu manifest không có `Automatic-Module-Name`, công cụ Java suy ra tên từ tên JAR. Quy tắc chính:

- Bỏ phần mở rộng `.jar`.
- Nhận diện hậu tố phiên bản ở cuối tên, tách phiên bản khỏi tên module.
- Thay các ký tự không phải chữ hoặc số bằng dấu chấm.
- Gộp nhiều dấu chấm liên tiếp thành một và bỏ dấu chấm ở đầu/cuối.

Ví dụ:

| Tên JAR | Tên automatic module suy ra |
|---|---|
| `legacy-greeting-2.4.1.jar` | `legacy.greeting` |
| `http-client-5.3.jar` | `http.client` |
| `acme-json.jar` | `acme.json` |

Không nên dựa lâu dài vào tên suy ra từ file. Đổi cách đặt tên artifact có thể làm đổi module name, khiến directive `requires` không còn khớp. Với thư viện do mình phát hành, nên công bố `Automatic-Module-Name` ngay cả trước khi bổ sung descriptor thật.

## 3. Đặc điểm của automatic module

Automatic module giúp thư viện cũ tham gia module graph mà không phải sửa mã nguồn. Tuy nhiên, descriptor ngầm có các đặc điểm rộng hơn một explicit module:

- **Các package của JAR được export.** Module khác có readability phù hợp có thể truy cập kiểu `public` trong các package của automatic module. JAR không có `module-info.class` để giới hạn package nào được export.
- **Automatic module có thể đọc các module khác trong module universe.** Điều này giúp thư viện cũ tiếp tục hoạt động khi dependency của nó được đặt trên module path, dù JAR cũ không khai báo từng `requires`.
- **Consumer là named module vẫn cần `requires`.** Để import và sử dụng kiểu trong automatic module, module tiêu thụ phải khai báo tên automatic module trong `module-info.java`.
- **Không có ranh giới API chi tiết.** JAR chưa khai báo `exports`, `opens`, `uses`, `provides` hoặc các dependency rõ ràng bằng module descriptor của chính nó.
- **Không tự động trở thành root chỉ vì nằm trên module path.** Module phải được kéo vào module graph qua dependency hoặc được chọn làm root, ví dụ bằng `--add-modules ALL-MODULE-PATH`.

Việc export mọi package giúp tương thích, nhưng làm giảm encapsulation. Khi có thể sửa thư viện, explicit module với các directive cụ thể là lựa chọn tốt hơn cho thiết kế dài hạn.

## 4. Dùng automatic module từ một named module

Giả sử có JAR cũ cung cấp lớp:

```java
package com.acme.legacy;

public final class LegacyGreeting {
    private LegacyGreeting() {
    }

    public static String message(String name) {
        return "Hello from a plain JAR, " + name + "!";
    }
}
```

Thư viện được biên dịch và đóng gói thành `legacy-greeting-2.4.1.jar`, không có `module-info.class`, nhưng manifest chứa:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy

```

Đặt JAR vào thư mục module path:

```text
workspace/
├── mods/
│   └── legacy-greeting-2.4.1.jar
└── src/
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

Module ứng dụng khai báo dependency bằng tên automatic module:

**`src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.legacy;
}
```

**`src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.legacy.LegacyGreeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(LegacyGreeting.message("Ada"));
    }
}
```

### Biên dịch và chạy

Giả sử JAR nằm trong `mods/` và chạy các lệnh từ thư mục `workspace/`:

```shell
javac --module-path mods --module-source-path src -d mods -m com.acme.app
java --module-path mods -m com.acme.app/com.acme.app.Main
```

Ở lệnh biên dịch, `--module-path mods` giúp compiler tìm automatic module trong JAR. `--module-source-path src` chỉ source của named module ứng dụng. `-m com.acme.app` chọn module cần biên dịch; đầu ra được đặt vào `mods/` cùng module path để lệnh chạy tìm thấy cả ứng dụng và thư viện.

Stdout:

```text
Hello from a plain JAR, Ada!
```

Ví dụ đã được kiểm tra trên JDK 24.0.2. JAR thư viện không có descriptor, `jar --describe-module` nhận diện nó là automatic module tên `com.acme.legacy`, và named consumer biên dịch/chạy thành công.

## 5. Nếu không có `Automatic-Module-Name`

Giả sử cùng thư viện được đóng gói thành `legacy-greeting-2.4.1.jar` nhưng không có thuộc tính tên module trong manifest. Tên suy ra là `legacy.greeting`.

Module consumer khi đó phải khai báo:

```java
module com.acme.app {
    requires legacy.greeting;
}
```

Tên trong `requires` phải khớp kết quả suy ra. Không được tự lấy `artifactId`, tên package hoặc tên class làm module name nếu chúng khác kết quả của quy tắc suy ra.

Để xem chính xác tên mà JDK nhận diện, chạy:

```shell
jar --describe-module --file mods/legacy-greeting-2.4.1.jar
```

Với JAR không có descriptor và không có `Automatic-Module-Name`, output mẫu:

```text
No module descriptor found. Derived automatic module.

legacy.greeting@2.4.1 automatic
requires java.base mandated
contains com.acme.legacy
```

Output này xác nhận tên module là `legacy.greeting`; phiên bản được nhận diện riêng từ hậu tố file.

## 6. Automatic module khác unnamed module

Đây là nhầm lẫn thường gặp khi chuyển ứng dụng từ classpath sang module path:

| Nội dung | JAR trên classpath | JAR trên module path |
|---|---|---|
| Module chứa lớp | Unnamed module | Automatic module nếu không có descriptor. |
| Tên module | Không có tên module tường minh; `Module.getName()` trả `null`. | Có tên suy ra hoặc từ `Automatic-Module-Name`. |
| Dùng `requires` | Named module không thể khai báo `requires` tới unnamed module. | Named module có thể khai báo `requires <automatic-module-name>`. |
| Encapsulation | Không có ranh giới package theo explicit module descriptor. | Các package của automatic module được export rộng rãi. |

Ví dụ, nếu JAR chỉ được thêm vào classpath, directive `requires com.acme.legacy;` không thể dùng để truy cập nó. Để named module sử dụng dependency qua module graph, JAR phải được đặt trên module path và có thể tìm thấy như một module.

Không nên đặt cùng một thư viện đồng thời trên classpath và module path trong một ứng dụng nếu không có lý do rõ ràng. Việc nạp cùng lớp qua các module/class loader khác nhau có thể gây nhầm lẫn về kiểu, identity và cấu hình runtime.

## 7. Khi nào automatic module được đưa vào module graph?

Việc JAR có mặt trên module path chỉ làm module trở nên observable; điều đó không đồng nghĩa module luôn được resolve vào graph.

Automatic module được resolve khi:

- Một named module đã resolve khai báo `requires` tới nó.
- Nó được chọn làm root bằng `--add-modules`.
- Nó được đưa vào qua một cơ chế phân giải module phù hợp khác trong lần khởi chạy.

Nếu ứng dụng cần nạp các plugin automatic module không được nhắc trực tiếp trong `requires`, có thể thêm toàn bộ module trên module path làm root:

```shell
java --module-path mods --add-modules ALL-MODULE-PATH -m com.acme.app/com.acme.app.Main
```

`ALL-MODULE-PATH` có thể đưa nhiều module không cần thiết vào graph. Khi biết tên module plugin, ưu tiên `--add-modules com.acme.plugin.one,com.acme.plugin.two` để kiểm soát root rõ ràng.

`--add-modules` chỉ yêu cầu resolve module. Nó không tự tạo một directive `requires` trong source và không thay thế readability cần thiết để mã ứng dụng import kiểu từ module đó.

## 8. Hạn chế và lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| `module not found` khi biên dịch. | JAR không nằm trên module path, đường dẫn sai hoặc tên trong `requires` không khớp. | Kiểm tra `--module-path` và dùng `jar --describe-module` để xác định module name. |
| `package ... is not visible`. | Named consumer chưa có readability tới automatic module. | Thêm `requires` với đúng module name vào `module-info.java`. |
| Đổi version JAR làm lỗi `requires`. | Tên module suy ra phụ thuộc vào tên file. | Công bố `Automatic-Module-Name` ổn định hoặc chuyển sang explicit descriptor. |
| Hai JAR có cùng module name. | Manifest hoặc tên file tạo ra tên automatic module trùng nhau. | Đổi module name để duy nhất; kiểm tra tất cả JAR trên module path. |
| Split package hoặc lỗi phân giải module. | Cùng package xuất hiện trong nhiều named/automatic modules. | Tổ chức lại package để mỗi package thuộc một module rõ ràng. |
| Package nội bộ bị truy cập rộng. | Automatic module export tất cả package. | Tạo explicit module descriptor và chỉ export API cần thiết. |
| Module không xuất hiện trong runtime graph. | JAR chỉ observable nhưng chưa được resolve. | Dùng `requires` hoặc `--add-modules` phù hợp. |
| Không tạo được custom runtime image với JAR automatic. | `jlink` yêu cầu các module có descriptor tường minh. | Chuyển dependency thành explicit module trước khi đưa vào runtime image. |

Automatic module là cầu nối migration, không phải cơ chế encapsulation hoàn chỉnh. Không nên dựa vào việc mọi package đều được export như một cam kết API lâu dài.

## 9. Kiểm tra JAR và lập kế hoạch chuyển đổi

### Kiểm tra module name và descriptor

```shell
jar --describe-module --file mods/legacy-greeting-2.4.1.jar
```

Lệnh này cho biết JAR có descriptor thật hay là automatic module, tên module, phiên bản và các package mà công cụ nhận diện.

### Kiểm tra dependency và gợi ý descriptor

`jdeps` có thể phân tích dependency và hỗ trợ tạo module descriptor mẫu:

```shell
jdeps --print-module-deps --module-path mods legacy-greeting-2.4.1.jar
jdeps --generate-module-info generated-modules legacy-greeting-2.4.1.jar
```

Kết quả của `jdeps` là đầu vào để phân tích, không phải cam kết rằng descriptor được tạo có thể dùng ngay. Cần kiểm tra package export, dependency, service `uses`/`provides`, reflection và các API nội bộ trước khi đóng gói lại JAR.

### Lộ trình chuyển từ automatic sang explicit module

1. Xác định module name ổn định bằng `Automatic-Module-Name`.
2. Phân tích package và dependency bằng `jar --describe-module` và `jdeps`.
3. Tạo `module-info.java` với các `requires`, `exports`, `opens`, `uses` và `provides` cần thiết.
4. Giữ module name trùng với `Automatic-Module-Name` đã công bố để consumer không phải đổi `requires`.
5. Biên dịch và chạy thử trên module path; kiểm tra cả API công khai lẫn framework cần reflection.
6. Khi descriptor đã hoàn chỉnh, phát hành explicit modular JAR và kiểm tra các consumer thực tế.

## 10. Checklist khi dùng JAR không có descriptor

- Xác định JAR đang nằm trên classpath hay module path.
- Nếu nằm trên module path và không có descriptor, xác định đúng automatic module name.
- Ưu tiên `Automatic-Module-Name` ổn định; không phụ thuộc tên file nếu có thể kiểm soát manifest.
- Dùng `jar --describe-module` để xác minh tên mà JDK thực sự nhận diện.
- Khai báo `requires` đúng tên automatic module trong named consumer.
- Đảm bảo JAR và các dependency cần thiết có trên module path.
- Kiểm tra xung đột module name, split package và các package được export rộng.
- Dùng `--add-modules` chỉ khi cần thêm automatic module làm root ngoài dependency graph.
- Nếu cần `jlink` hoặc encapsulation rõ ràng, lập kế hoạch chuyển JAR thành explicit module.

## Tài liệu tham khảo

- [Java Platform Module System — ModuleFinder API (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [Java Platform Module System — ModuleDescriptor API (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [The `jar` Command — Describe a Module (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The `java` Command — Module Path and Root Modules (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The `jdeps` Command — Dependency Analysis and Module Info Generation (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
