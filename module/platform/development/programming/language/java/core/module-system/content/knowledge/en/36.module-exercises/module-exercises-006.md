# Dùng jdeps để chuyển ứng dụng classpath sang module graph

## 1. Mục tiêu của quá trình chuyển đổi

Ứng dụng Java chạy trên classpath thường phụ thuộc vào nhiều JAR, nhưng các dependency không được khai báo trong module descriptor. Khi chuyển sang Java Platform Module System (JPMS), cần xác định:

- Ứng dụng và từng thư viện phụ thuộc vào module/package nào.
- JAR nào đã là explicit module, JAR nào là automatic module và JAR nào vẫn chưa modular.
- Module descriptor cần những directive `requires`, `exports`, `uses` và `provides` nào.
- Có split package, dependency thiếu hoặc sử dụng JDK internal API hay không.
- Những dependency động nào không thể suy ra chỉ từ bytecode.

Công cụ `jdeps` phân tích dependency tĩnh của class files và JAR, giúp xây dựng bức tranh ban đầu về module graph. Nó không tự động chuyển toàn bộ ứng dụng thành một hệ thống modular hoàn chỉnh. Nhà phát triển vẫn phải thiết kế ranh giới module, xác nhận dependency runtime và kiểm thử ứng dụng sau khi chuyển đổi.

## 2. Chuẩn bị đầu vào

Giả sử ứng dụng cũ có cấu trúc:

```text
legacy-app/
├── app.jar
├── lib/
│   ├── customer-api.jar
│   ├── json-engine.jar
│   └── logging.jar
└── config/
    └── application.properties
```

Ứng dụng được chạy bằng classpath:

```bash
java -cp "app.jar:lib/*" com.acme.app.Main
```

Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy:

```powershell
java -cp "app.jar;lib/*" com.acme.app.Main
```

Trước khi phân tích, cần thu thập đúng các JAR được triển khai trong môi trường thật. Không chỉ phân tích file app.jar nếu ứng dụng còn phụ thuộc vào thư viện được nạp từ thư mục plugin hoặc cấu hình bên ngoài.

Nên lưu lại:

- JDK version dùng để build và chạy.
- Danh sách JAR cùng phiên bản và checksum.
- Lệnh khởi chạy hiện tại, bao gồm classpath và JVM options.
- Các cấu hình plugin, reflection, service provider và class name được nạp động.
- Những package mà ứng dụng công khai cho module hoặc thư viện khác.

Đây là baseline để so sánh trước và sau khi modular hóa.

## 3. Bước 1: xem dependency tổng quan với jdeps

Chạy `jdeps --summary` để xem các dependency ở mức module/package tổng quát:

```bash
jdeps --summary app.jar
```

Nếu thư viện nằm trên classpath riêng, truyền chúng bằng `--class-path`:

```bash
jdeps --class-path "lib/*" --summary app.jar
```

Output minh họa:

```text
app.jar -> java.base
app.jar -> java.logging
app.jar -> customer.api
app.jar -> json.engine
```

Tên hiển thị phụ thuộc vào loại artifact và khả năng ánh xạ dependency của jdeps. Khi dependency chưa phải module, công cụ có thể hiển thị tên JAR hoặc package thay vì một named module đã được xác định.

Cách đọc:

- `java.base`: module nền tảng mà hầu hết Java code đều phụ thuộc.
- `java.logging`: ứng dụng tham chiếu API logging thuộc module này.
- `customer.api`, `json.engine`: dependency ứng dụng cần được xác định artifact và module name cụ thể.

`--summary` hữu ích để có cái nhìn nhanh. Khi cần biết class nào tạo ra dependency, dùng chế độ verbose ở các bước sau.

## 4. Bước 2: lần theo dependency bắc cầu

Một thư viện có thể phụ thuộc vào nhiều thư viện khác. Dùng `--recursive` để phân tích dependency theo chiều sâu:

```bash
jdeps --recursive --class-path "lib/*" --summary app.jar
```

Ví dụ:

```text
app.jar -> java.base
app.jar -> customer-api.jar
customer-api.jar -> java.base
customer-api.jar -> json-engine.jar
json-engine.jar -> java.base
```

Kết quả minh họa cho thấy dependency không chỉ nằm ở app.jar. Khi chuyển sang module path, các module dependency bắc cầu cũng cần được cung cấp và resolve.

Không nên chỉ thêm module được ứng dụng import trực tiếp rồi bỏ qua dependency của thư viện. Module graph phải chứa toàn bộ dependency cần thiết để các module được resolve.

Nếu output không đủ rõ, xem dependency theo class:

```bash
jdeps --recursive -verbose:class --class-path "lib/*" app.jar
```

Output minh họa:

```text
com.acme.app.Main -> com.acme.customer.Customer
com.acme.app.Main -> java.util.logging.Logger
com.acme.customer.Repository -> com.acme.json.JsonReader
```

Từ class nguồn và class đích, có thể xác định package nào cần được export, module nào cần được đọc và dependency nào đang được sử dụng thực tế.

## 5. Bước 3: xác định module name của từng JAR

Trước khi viết `module-info.java`, cần biết tên module của các dependency.

Dùng:

```bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/json-engine.jar
jar --describe-module --file lib/logging.jar
```

Có ba trường hợp phổ biến:

1. **Explicit named module:** JAR có `module-info.class`; tên module và directive được khai báo rõ.
2. **Automatic module:** JAR không có descriptor nhưng được đặt trên module path; tên module được suy ra từ tên JAR hoặc khai báo bằng `Automatic-Module-Name` trong manifest.
3. **Classpath library:** JAR nằm trên classpath và thuộc unnamed module của class loader tương ứng.

Ví dụ manifest có thể chứa:

```text
Automatic-Module-Name: com.acme.customer
```

Tên automatic module ổn định sẽ giúp các module khác khai báo `requires com.acme.customer` mà không phụ thuộc vào việc tên file JAR thay đổi nhẹ giữa các phiên bản.

Không được nhầm tên artifact Maven, tên file JAR, package name và module name. Hãy lấy module name từ descriptor hoặc kết quả `jar --describe-module`.

## 6. Bước 4: kiểm tra dependency tới JDK internal API

Ứng dụng cũ đôi khi sử dụng class thuộc package nội bộ của JDK, chẳng hạn `sun.*` hoặc `com.sun.*`. Những API này không phải public Java API ổn định và có thể bị chặn hoặc thay đổi giữa các phiên bản JDK.

Kiểm tra bằng:

```bash
jdeps --jdk-internals app.jar
```

Nếu có dependency tới internal API, output sẽ chỉ ra class nguồn và API liên quan. Hãy tìm public API thay thế trước khi modular hóa.

Không nên dùng `--add-exports` như giải pháp dài hạn nếu dependency có thể được thay bằng API được hỗ trợ. Nếu cần giải pháp tạm thời để tương thích, phải ghi rõ module/package, giới hạn phạm vi và kế hoạch loại bỏ.

## 7. Bước 5: tạo module descriptor cho thư viện cũ

Với JAR chưa có `module-info.class`, `jdeps` có thể đề xuất descriptor:

```bash
jdeps --generate-module-info generated-modules lib/customer-api.jar
```

Với nhiều JAR, chạy lần lượt cho từng artifact để dễ xem và kiểm soát kết quả.

Công cụ có thể tạo cấu trúc tương tự:

```text
generated-modules/
└── com.acme.customer/
    └── module-info.java
```

Descriptor được sinh có thể chứa các directive `requires` và `exports` dựa trên dependency tĩnh mà công cụ phát hiện.

Đọc và chỉnh sửa descriptor trước khi sử dụng. `jdeps` không biết đầy đủ ý định thiết kế API của thư viện, và có thể không suy ra được:

- Package nào thực sự là API công khai.
- Package nào chỉ là implementation nội bộ.
- Service type mà module sử dụng qua `ServiceLoader`.
- Provider được đăng ký qua `META-INF/services`.
- Class được nạp qua reflection hoặc cấu hình.
- Dependency chỉ xuất hiện ở một đường chạy động.

Không nên export tất cả package chỉ để làm cho compilation thành công. Chỉ export package cần thiết cho consumer.

Nếu thư viện cần reflective access sâu cho framework, hãy xem xét `opens` riêng cho package và module đích thay vì export rộng toàn bộ implementation.

## 8. Bước 6: viết module-info.java cho ứng dụng

Giả sử dependency đã được xác định:

- `customer-api` cung cấp package `com.acme.customer`.
- `json-engine` cung cấp package `com.acme.json`.
- Ứng dụng dùng logging của JDK.

Module descriptor của ứng dụng có thể bắt đầu như sau:

```java
module com.acme.app {
    requires java.logging;
    requires com.acme.customer;
    requires com.acme.json;
}
```

Tên module trong `requires` phải khớp với tên module thực tế của dependency trên module path.

Nếu module khác cần truy cập public API của ứng dụng, hãy export package cần công khai:

```java
module com.acme.app {
    requires java.logging;
    requires com.acme.customer;
    requires com.acme.json;

    exports com.acme.app.api;
}
```

Không cần export package chứa main class hoặc implementation nếu không có module khác cần truy cập chúng.

### Phân biệt requires và exports

- `requires X`: module hiện tại đọc module X.
- `exports p`: module hiện tại cho phép module khác truy cập public API trong package p.
- `exports p to X`: chỉ export package cho module X.
- `requires transitive X`: truyền readability tới consumer của module hiện tại khi dependency là một phần public API.
- `requires static X`: dependency cần khi compile nhưng có thể không bắt buộc ở runtime theo quy tắc của directive.

Một lỗi thường gặp là thêm `exports` vào consumer trong khi dependency chưa export package của chính nó. Package phải được export bởi module sở hữu package đó.

## 9. Bước 7: chuyển ServiceLoader và META-INF/services

Ứng dụng classpath có thể đăng ký provider bằng file:

```text
META-INF/services/com.acme.spi.Formatter
```

File chứa tên đầy đủ của provider class, mỗi dòng một tên.

Khi chuyển provider thành named module, cần biểu diễn service bằng module descriptor:

Consumer:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

Provider:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Đảm bảo service interface nằm trong package được SPI module export. Provider cần triển khai đúng service type và tuân thủ yêu cầu khởi tạo của ServiceLoader.

Không giả định `jdeps` sẽ tự chuyển mọi file `META-INF/services` thành `uses`/`provides` chính xác. Hãy kiểm kê các file service và kiểm thử provider discovery sau khi chuyển đổi.

## 10. Bước 8: đặt dependency trên module path và biên dịch

Sau khi có descriptor, tổ chức source và dependency:

```text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    ├── com.acme.customer.jar
    ├── com.acme.json.jar
    └── com.acme.spi.jar
```

Biên dịch ứng dụng:

```bash
javac --module-path mods \\
  --module-source-path src \\
  -d out \\
  -m com.acme.app
```

Nếu module descriptor của các thư viện được sinh riêng, cần đóng gói lại JAR với `module-info.class` hoặc biên dịch module source tương ứng trước khi đưa vào module path.

Chạy ứng dụng:

```bash
java --module-path "mods:out" \\
  -m com.acme.app/com.acme.app.Main
```

Trên Windows, dấu phân cách module path là dấu chấm phẩy:

```powershell
java --module-path "mods;out" -m com.acme.app/com.acme.app.Main
```

Không đặt JAR chưa modular lên module path một cách tùy tiện rồi giả định nó hoạt động như trên classpath. Khi ở module path, JAR có thể trở thành automatic module và tham gia module resolution với các quy tắc khác.

## 11. Bước 9: kiểm tra module graph và dependency sau chuyển đổi

Dùng `jdeps` để kiểm tra descriptor:

```bash
jdeps --module-path mods --check com.acme.app
```

In dependency module:

```bash
jdeps --module-path mods \\
  --print-module-deps mods/com.acme.app.jar
```

Kiểm tra module graph khi chạy:

```bash
java --show-module-resolution \\
  --module-path "mods:out" \\
  -m com.acme.app/com.acme.app.Main
```

Validate tập module trên module path:

```bash
java --validate-modules \\
  --module-path mods \\
  --add-modules ALL-MODULE-PATH
```

Đọc output để xác nhận:

- Root module đúng với ứng dụng.
- Dependency `requires` được resolve từ đúng artifact.
- Không có module hoặc package xung đột.
- Provider cần thiết được bind và có thể được ServiceLoader tìm thấy.
- Không còn tham chiếu tới module/class bị thiếu.

`ALL-MODULE-PATH` hữu ích để validate toàn bộ module quan sát được trong thư mục kiểm tra. Không nhất thiết dùng nó làm root trong lệnh production nếu ứng dụng không cần resolve mọi module trên module path.

## 12. Kiểm tra split package và dependency động

Classpath cũ có thể cho phép nhiều JAR cùng đóng góp class vào một package. Khi các JAR trở thành named hoặc automatic module, split package có thể khiến resolution thất bại.

Kiểm tra package trùng giữa các artifact trước khi modular hóa. Nếu có split package, cần gom package về một module sở hữu hoặc tách package theo trách nhiệm.

Ngoài dependency tĩnh, kiểm tra thêm:

- `Class.forName` và tên class lấy từ cấu hình.
- Reflection và framework scan annotation.
- JNI và native library.
- Plugin được tải từ thư mục ngoài module path.
- `ServiceLoader` và các file `META-INF/services`.
- Resource path, serialization và tên class được lưu trong dữ liệu.

`jdeps` phân tích tham chiếu tĩnh; nó không thể bảo đảm phát hiện đầy đủ các dependency được quyết định khi runtime.

## 13. Bảng lệnh jdeps thường dùng

| Mục tiêu | Lệnh |
|---|---|
| Tóm tắt dependency | `jdeps --summary app.jar` |
| Xem dependency bắc cầu | `jdeps --recursive --summary app.jar` |
| Xem class tạo dependency | `jdeps -verbose:class app.jar` |
| Xem module dependency | `jdeps --list-deps app.jar` |
| In danh sách module dependency | `jdeps --print-module-deps app.jar` |
| Tìm dependency bị thiếu | `jdeps --missing-deps app.jar` |
| Kiểm tra JDK internal API | `jdeps --jdk-internals app.jar` |
| Kiểm tra module descriptor | `jdeps --check com.acme.app --module-path mods` |
| Sinh module-info.java | `jdeps --generate-module-info generated-modules lib.jar` |

Khi phân tích JAR cần dependency bên ngoài, bổ sung `--class-path` hoặc `--module-path` phù hợp. Đừng dùng `--ignore-missing-deps` để che lỗi trong quá trình xác minh migration; nếu phải dùng để tiếp tục phân tích, hãy ghi nhận và xử lý riêng từng dependency bị thiếu.

## 14. Lộ trình migration an toàn

Có thể chia quá trình chuyển đổi thành các giai đoạn:

1. **Inventory:** thu thập JAR, version, module name, package, service provider và dependency runtime.
2. **Static analysis:** chạy `jdeps` ở mức summary, recursive và verbose; tìm JDK internal API và dependency thiếu.
3. **Dependency classification:** phân loại explicit module, automatic module và thư viện chỉ có trên classpath.
4. **Package ownership:** giải quyết split package và xác định package API/implementation.
5. **Descriptor authoring:** tạo hoặc chỉnh sửa `module-info.java`; xác nhận `requires`, `exports`, `uses`, `provides` và `opens`.
6. **Compile:** đưa dependency cần thiết lên module path và biên dịch các module.
7. **Runtime verification:** chạy với `--show-module-resolution`, test ServiceLoader, reflection và các plugin.
8. **Release validation:** chạy `jdeps --check`, `java --validate-modules` và integration test trên đúng tập artifact phát hành.
9. **Rollout:** triển khai theo từng môi trường, theo dõi lỗi và giữ khả năng rollback.

Không cần chuyển tất cả thư viện trong một lần. Có thể giữ một số thư viện legacy trên classpath trong giai đoạn chuyển tiếp, nhưng phải hiểu ranh giới unnamed module và named module; named module không đọc unnamed module theo mặc định.

## Ghi nhớ

- `jdeps` giúp khám phá dependency tĩnh, không tự động thiết kế module graph hoàn chỉnh.
- Dùng `--summary`, `--recursive`, `-verbose:class`, `--jdk-internals` và `--generate-module-info` theo từng bước.
- Xác định module name bằng `jar --describe-module`; không nhầm tên JAR với tên module.
- Review descriptor được sinh: đặc biệt `requires`, `exports`, `uses`, `provides` và `opens`.
- Kiểm tra split package, reflection, service provider và plugin động trước khi bỏ classpath.
- Biên dịch và chạy trên module path, sau đó kiểm tra bằng `jdeps --check`, `--show-module-resolution` và `--validate-modules`.
- Chỉ chấp nhận migration khi integration test xác nhận hành vi runtime tương đương.
