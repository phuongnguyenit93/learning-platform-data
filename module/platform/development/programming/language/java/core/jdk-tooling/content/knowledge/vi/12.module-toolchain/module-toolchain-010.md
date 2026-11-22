# Kiểm tra module graph trong Java

## 1. Module graph là gì?

Trong Java Platform Module System (JPMS), module graph là đồ thị mô tả các module và quan hệ đọc giữa chúng. Mỗi module là một nút; một chỉ thị `requires` trong `module-info.java` tạo quan hệ từ module khai báo phụ thuộc tới module được yêu cầu.

Ví dụ:

~~~text
com.example.app
       |
       | requires
       v
com.example.base
       |
       | requires (mandated)
       v
java.base
~~~

Trong sơ đồ này, `com.example.app` đọc được `com.example.base` vì khai báo `requires com.example.base;`. Module base và app đều đọc `java.base` theo quy tắc mặc định của JPMS.

Module graph giúp trả lời các câu hỏi:

- Ứng dụng cần những module nào để biên dịch và chạy?
- Quan hệ `requires` nào trực tiếp, quan hệ nào được truyền qua `requires transitive`?
- Module nào đang được phân giải từ module path?
- Có module bị thiếu, trùng tên hoặc xung đột package không?
- Có thể tạo runtime image nhỏ gọn với tập module nào?
- Một thư viện cũ đang phụ thuộc vào module JDK hoặc API nội bộ nào?

Cần phân biệt **module graph** với classpath. Classpath tìm lớp và JAR trong unnamed module; module graph thể hiện các named module, descriptor, quyền đọc và quy tắc đóng gói của JPMS.

## 2. Module resolution và readability

Khi khởi chạy ứng dụng dạng module, Java launcher xác định tập module gốc (root modules), sau đó phân giải các phụ thuộc cần thiết theo các chỉ thị trong module descriptor.

Các quy tắc quan trọng:

- Module chính được chỉ định bằng `-m` hoặc `--module` là một root module.
- `--add-modules` bổ sung module vào tập root cần phân giải.
- `requires` yêu cầu module hiện tại đọc module được nêu tên.
- `requires transitive` truyền khả năng đọc tới module phụ thuộc của module được yêu cầu.
- `requires static` cần thiết khi biên dịch nhưng có thể không bắt buộc khi chạy.
- `java.base` được mọi module đọc ngầm; không cần khai báo `requires java.base`.
- Service binding có thể bổ sung module cung cấp service khi quá trình khởi chạy hoặc liên kết bật cơ chế phân giải service phù hợp.

Một module có thể được tìm thấy trên module path nhưng vẫn không được phân giải nếu nó không thuộc tập root và không phải dependency được kéo vào từ root. Vì vậy, danh sách module quan sát được và tập module thực sự được resolve là hai khái niệm khác nhau.

Quá trình phân giải còn kiểm tra tính nhất quán của module graph, bao gồm tên module, phụ thuộc bắt buộc, package được export và các xung đột theo quy tắc JPMS.

## 3. Ví dụ hai module để quan sát graph

Tạo cấu trúc dự án:

~~~text
module-graph-demo/
├── src/
│   ├── com.example.base/
│   │   ├── module-info.java
│   │   └── com/example/base/Base.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── mods/
~~~

Module base, tệp `src/com.example.base/module-info.java`:

~~~java
module com.example.base {
    exports com.example.base;
}
~~~

Tệp `src/com.example.base/com/example/base/Base.java`:

~~~java
package com.example.base;

public class Base {
    public static String value() {
        return "base";
    }
}
~~~

Module app, tệp `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.base;
}
~~~

Tệp `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.base.Base;

public class Main {
    public static void main(String[] args) {
        System.out.println(Base.value());
    }
}
~~~

Biên dịch cả hai module bằng JDK 17 trở lên:

~~~bash
mkdir -p mods
javac --release 17 --module-source-path src -d mods --module com.example.base,com.example.app
~~~

Cây output:

~~~text
mods/
├── com.example.base/
│   ├── module-info.class
│   └── com/example/base/Base.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Chạy module ứng dụng:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
base
~~~

Module graph tối thiểu của ví dụ có cạnh `com.example.app → com.example.base` và cạnh mặc định tới `java.base`. Các ví dụ tiếp theo dùng cùng cấu trúc này.

## 4. Xem module graph lúc khởi động bằng `--show-module-resolution`

Tùy chọn `--show-module-resolution` yêu cầu Java launcher in thông tin về các module được phân giải trong quá trình khởi chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Với ví dụ trên, các dòng quan trọng có dạng:

~~~text
root com.example.app file:/.../mods/com.example.app/
com.example.app requires com.example.base file:/.../mods/com.example.base/
base
~~~

Output thực tế còn có thể liệt kê nhiều module hệ thống và các quan hệ `binds` do service binding. Số lượng dòng phụ thuộc phiên bản JDK, tập root và service provider có thể được phân giải.

Ý nghĩa các dạng dòng thường gặp:

- `root`: module được đưa trực tiếp vào tập root.
- `requires`: module được phân giải vì một module khác khai báo phụ thuộc.
- `binds`: module được bổ sung thông qua quá trình liên kết service provider.

Dùng tùy chọn này khi cần biết JVM thực sự phân giải module nào và module được tìm thấy từ vị trí nào. Nó đặc biệt hữu ích khi ứng dụng chạy trên máy phát triển nhưng không chạy trong môi trường đóng gói hoặc runtime image.

Trên PowerShell, có thể lọc các dòng liên quan đến module ứng dụng:

~~~powershell
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main 2>&1 | Select-String "root com.example.app|com.example.app requires|com.example.base"
~~~

Trên Linux/macOS:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main 2>&1 | grep -E "root com.example.app|com.example.app requires|com.example.base"
~~~

Đây là output chẩn đoán; đừng dùng nó làm danh sách dependency ổn định nếu chưa kiểm tra module graph bằng công cụ phân tích tĩnh.

## 5. Kiểm tra module graph bằng `jdeps --check`

`jdeps` là công cụ phân tích phụ thuộc trong JDK. Với named module, `--check` giúp so sánh module descriptor đã khai báo với các phụ thuộc suy ra từ bytecode.

Chạy:

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Output gồm các phần tương tự:

~~~text
com.example.app
  [Module descriptor]
    requires com.example.base;
    requires mandated java.base;
  [Suggested module descriptor for com.example.app]
    requires com.example.base;
    requires mandated java.base;
  [Transitive reduced graph for com.example.app]
    requires com.example.base;
    requires mandated java.base;
~~~

Ba phần có ý nghĩa:

- **Module descriptor:** những phụ thuộc được khai báo trong `module-info.java`.
- **Suggested module descriptor:** phụ thuộc mà phân tích bytecode cho thấy module có thể cần khai báo.
- **Transitive reduced graph:** đồ thị sau khi loại bỏ các cạnh đọc đã được suy ra thông qua quan hệ `requires transitive`.

`jdeps --check` còn có thể chỉ ra qualified export không được sử dụng. Nếu descriptor khai báo nhiều `exports package to ...`, hãy kiểm tra cảnh báo để biết package nào không được module đích sử dụng.

Kết quả phân tích tĩnh phụ thuộc vào bytecode và module path được cung cấp. Nó không thể suy ra mọi dependency được nạp động bằng reflection, tên lớp tạo từ chuỗi hoặc cấu hình bên ngoài.

## 6. Liệt kê dependency của module

`jdeps` cung cấp nhiều mức xem dependency. Chỉ định module path và module gốc:

~~~bash
# Liệt kê module phụ thuộc
jdeps --module-path mods --module com.example.app --list-deps

# Liệt kê graph đã rút gọn
jdeps --module-path mods --module com.example.app --list-reduced-deps

# In danh sách module dạng CSV
jdeps --module-path mods --module com.example.app --print-module-deps
~~~

Với ví dụ hai module, output có dạng:

~~~text
com.example.base
java.base
~~~

Lệnh `--print-module-deps` in danh sách phân tách bằng dấu phẩy, ví dụ:

~~~text
com.example.base,java.base
~~~

Phân biệt các tùy chọn:

| Tùy chọn | Kết quả |
|---|---|
| `--list-deps` | Liệt kê dependency module được phân tích, gồm các dependency được suy ra theo quá trình phân tích. |
| `--list-reduced-deps` | Liệt kê dependency sau khi bỏ các cạnh đọc được ngụ ý bởi `requires transitive`. |
| `--print-module-deps` | In danh sách rút gọn dạng phân tách bằng dấu phẩy, phù hợp làm đầu vào cho `jlink --add-modules`. |

Trong graph lớn, danh sách reduced có thể ngắn hơn đáng kể vì một module có thể đọc module khác thông qua cạnh transitive. Khi cần xem quan hệ đầy đủ, hãy dùng `--list-deps`; khi cần xác định root modules cho runtime image, `--print-module-deps` thường thuận tiện hơn.

## 7. Xuất graph thành DOT để trực quan hóa

Để tạo file graph có thể xem bằng Graphviz, dùng `--dot-output`:

~~~bash
jdeps --module-path mods --module com.example.app --dot-output graph-out
~~~

Công cụ tạo các file DOT trong thư mục chỉ định, thường gồm file cho từng module và file tổng quan `summary.dot`. Với ví dụ, file module có các cạnh dạng:

~~~dot
digraph "com.example.app" {
    "com.example.app" -> "com.example.base (com.example.base)";
    "com.example.app" -> "java.io (java.base)";
    "com.example.app" -> "java.lang (java.base)";
}
~~~

File DOT biểu diễn dependency tìm được từ bytecode; một cạnh có thể hướng tới package trong module chứa package đó. Vì thế, file graph chi tiết có thể hiển thị package như `java.io` và `java.lang`, còn file `summary.dot` tổng hợp ở cấp module.

Nếu đã cài Graphviz, có thể chuyển DOT thành SVG:

~~~bash
dot -Tsvg graph-out/summary.dot -o module-graph.svg
~~~

Hoặc tạo PNG:

~~~bash
dot -Tpng graph-out/summary.dot -o module-graph.png
~~~

Graphviz là công cụ riêng, không đi kèm JDK. Nếu không cài Graphviz, file DOT vẫn là văn bản có thể đọc hoặc đưa vào công cụ trực quan hóa khác.

Dùng graph tổng quan để xem quan hệ giữa module. Dùng graph chi tiết khi cần truy nguyên package/class nào tạo ra dependency.

## 8. Kiểm tra module được quan sát và descriptor

Java launcher có một số tùy chọn giúp xem module trên module path và thông tin descriptor.

Liệt kê các module có thể quan sát:

~~~bash
java --module-path mods --list-modules
~~~

Mô tả một module cụ thể:

~~~bash
java --module-path mods --describe-module com.example.app
~~~

Với module app, thông tin chính sẽ tương tự:

~~~text
com.example.app
requires java.base mandated
requires com.example.base
contains com.example.app
~~~

`--list-modules` hữu ích khi xác nhận module path đã được cấu hình và launcher nhìn thấy module. `--describe-module` cho biết module khai báo `requires`, `exports`, `opens`, `uses`, `provides` và package nào được chứa, tùy module.

Có thể kiểm tra descriptor của một modular JAR bằng `jar`:

~~~bash
jar --describe-module --file app.jar
~~~

Đối với module đã biên dịch trong thư mục, dùng `java --describe-module` với module path tương ứng. Không suy ra tên module chỉ từ tên file JAR; hãy đọc module descriptor hoặc dùng công cụ mô tả.

## 9. Kiểm tra lỗi và xung đột bằng `--validate-modules`

Tùy chọn `--validate-modules` yêu cầu launcher xác thực các module quan sát được rồi kết thúc:

~~~bash
java --module-path mods --validate-modules
~~~

Khi tất cả module hợp lệ, lệnh thường kết thúc với exit code 0 và không in thông báo lỗi. Nếu có xung đột hoặc descriptor không hợp lệ, launcher in chẩn đoán và trả mã thoát khác 0.

Các vấn đề có thể gặp:

- Hai module cùng tên trong các phần tử module path.
- Module bắt buộc không tồn tại.
- Xung đột package hoặc split package giữa named modules.
- Descriptor hoặc quan hệ phụ thuộc không hợp lệ.
- Module không thể được phân giải theo các quy tắc JPMS.

`--validate-modules` kiểm tra tập module quan sát được theo module path hiện tại. Nó không thay thế việc chạy ứng dụng hoặc kiểm tra hành vi runtime. Một ứng dụng vẫn có thể lỗi khi chạy vì dependency được nạp động, file cấu hình thiếu hoặc logic chương trình sai.

Dùng nó như một bước kiểm tra module path trước khi chạy hoặc tạo runtime image.

## 10. Kiểm tra tùy chọn khởi chạy bằng `--dry-run`

`--dry-run` yêu cầu Java launcher tạo VM và nạp lớp main nhưng không gọi phương thức `main`:

~~~bash
java --module-path mods --dry-run -m com.example.app/com.example.app.Main
~~~

Lệnh hữu ích để xác nhận:

- Tên module và lớp main có hợp lệ không.
- Module path có đủ module cần thiết không.
- Module graph có thể được phân giải không.
- Các tùy chọn launcher/JVM có được chấp nhận không.

Vì phương thức `main` không được thực thi, lệnh không in `base` trong ví dụ. Nếu khởi tạo VM hoặc nạp lớp main thất bại, launcher vẫn báo lỗi.

`--dry-run` khác `--validate-modules`:

| Tùy chọn | Mục tiêu |
|---|---|
| `--validate-modules` | Kiểm tra tất cả module quan sát được và kết thúc. |
| `--dry-run` | Thử tạo VM và nạp lớp main với cấu hình chạy thực tế, nhưng không thực thi main. |
| `--show-module-resolution` | In chi tiết các module được phân giải trong lúc khởi động. |

Có thể kết hợp dry run với module resolution:

~~~bash
java --show-module-resolution --dry-run --module-path mods -m com.example.app/com.example.app.Main
~~~

Đây là cách nhanh để kiểm tra cấu hình launch trước khi chạy ứng dụng có tác dụng phụ.

## 11. Từ module graph tới runtime image với `jlink`

`jlink` tạo runtime image chứa module ứng dụng và các module nền tảng cần thiết. Module graph quyết định tập module được phân giải và đưa vào image.

Trước tiên, lấy danh sách module phụ thuộc từ `jdeps`:

~~~bash
jdeps --module-path mods --module com.example.app --print-module-deps
~~~

Sau đó dùng module ứng dụng làm root để `jlink` tự phân giải dependency bắc cầu:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

Chạy launcher của runtime image:

~~~bash
./runtime-image/bin/app
~~~

Trên Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

Stdout:

~~~text
base
~~~

Có thể dùng danh sách từ `jdeps --print-module-deps` làm root list khi muốn kiểm soát tập module:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.base,java.base --output runtime-image
~~~

Tuy nhiên, trong ứng dụng thực tế, dùng module ứng dụng làm root thường giúp `jlink` giải quyết dependency graph theo descriptor. Đừng chỉ sao chép danh sách package hoặc class vào `--add-modules`; tùy chọn này nhận tên module.

## 12. Phân tích dependency của JAR chưa modular hóa

Một JAR cũ không có `module-info.class` vẫn có thể được phân tích bằng `jdeps`. Đây là bước hữu ích trước khi chuyển thư viện sang JPMS.

Liệt kê dependency module của JAR:

~~~bash
jdeps --multi-release 17 --print-module-deps lib/legacy-library.jar
~~~

Nếu cần tạo module descriptor mẫu:

~~~bash
jdeps --multi-release 17 --generate-module-info generated-modules lib/legacy-library.jar
~~~

Công cụ tạo thư mục chứa `module-info.java` được gợi ý dựa trên dependency tĩnh. Hãy đọc và chỉnh sửa descriptor trước khi dùng trong sản phẩm, vì phân tích bytecode không thể biết đầy đủ ý định thiết kế API, dependency reflection hoặc service configuration.

Nếu thư viện là open module, có thể dùng `--generate-open-module`. Với JAR có nhiều phiên bản class, chọn đúng phiên bản bằng `--multi-release` để phân tích phần bytecode tương ứng.

Đối với dependency được nạp qua reflection hoặc tên lớp lấy từ cấu hình, hãy kiểm tra thủ công và bổ sung module cần thiết. Không dùng `--ignore-missing-deps` chỉ để làm cho báo cáo trông sạch; cần hiểu và giải quyết dependency bị thiếu.

## 13. Tìm dependency bị thiếu và JDK internal API

Một module graph có thể phân giải được nhưng thư viện vẫn có tham chiếu tới class không có trong module path. `jdeps` hỗ trợ tìm các trường hợp này:

~~~bash
jdeps --module-path mods --missing-deps app.jar
~~~

Với JAR hoặc thư mục classpath, cung cấp classpath phụ thuộc phù hợp để kết quả phản ánh môi trường build/runtime thực tế.

Để tìm phụ thuộc vào API nội bộ của JDK:

~~~bash
jdeps --jdk-internals app.jar
~~~

API nội bộ không phải API công khai ổn định và có thể bị đóng hoặc thay đổi giữa các phiên bản Java. Khi thấy kết quả, hãy ưu tiên thay bằng API chuẩn. Nếu chưa thể thay ngay, kiểm tra cảnh báo và giới hạn phiên bản runtime được hỗ trợ.

Các tùy chọn liên quan:

- `--api-only` chỉ phân tích dependency xuất hiện trong chữ ký public/protected của public class.
- `--recursive` phân tích dependency runtime theo cách đệ quy.
- `--require module.name` lọc dependency theo tên module.
- `--package package.name` lọc dependency theo package.
- `--ignore-missing-deps` bỏ qua cảnh báo dependency thiếu; chỉ dùng khi đã có lý do rõ ràng.

## 14. Điều chỉnh root set và module universe

Module graph có thể thay đổi tùy root module và tập module mà runtime được phép quan sát.

| Tùy chọn | Tác dụng |
|---|---|
| `--add-modules` | Thêm một hoặc nhiều module vào tập root. Có thể dùng `ALL-DEFAULT`, `ALL-SYSTEM` hoặc `ALL-MODULE-PATH` theo mục tiêu. |
| `--limit-modules` | Giới hạn tập module có thể quan sát khi phân giải. |
| `--upgrade-module-path` | Cung cấp module thay thế cho module có thể nâng cấp trong runtime image. |
| `--module-path` | Chỉ định nơi tìm modular JAR hoặc exploded module. |
| `--bind-services` của `jlink` | Bổ sung service provider module và các dependency của chúng trong quá trình link. |

Ví dụ thêm module tùy chọn vào root set:

~~~bash
java --module-path mods --add-modules com.example.base -m com.example.app/com.example.app.Main
~~~

Ví dụ giới hạn module universe:

~~~bash
java --limit-modules java.base,com.example.base,com.example.app --module-path mods -m com.example.app/com.example.app.Main
~~~

Chỉ dùng `--limit-modules` khi đã biết đầy đủ module ứng dụng cần thiết. Giới hạn quá chặt có thể khiến một dependency hoặc provider không còn được quan sát và làm quá trình phân giải thất bại.

Nếu ứng dụng sử dụng `ServiceLoader`, kiểm tra cả `uses` và `provides` trong module descriptor. Khi tạo runtime image, cân nhắc `jlink --bind-services` để đưa provider module cần thiết vào image.

## 15. Quy trình kiểm tra module graph trong CI

Một pipeline có thể chạy các bước sau sau khi biên dịch module:

~~~bash
# 1. Kiểm tra module descriptor và dependency graph
jdeps --module-path mods --check com.example.app

# 2. Liệt kê module phụ thuộc
jdeps --module-path mods --module com.example.app --list-deps

# 3. Tạo danh sách root module cho runtime image
jdeps --module-path mods --module com.example.app --print-module-deps

# 4. Kiểm tra tất cả module quan sát được
java --module-path mods --validate-modules

# 5. Xác nhận cấu hình launch có thể nạp main class
java --module-path mods --dry-run -m com.example.app/com.example.app.Main

# 6. Chạy ứng dụng và quan sát module resolution khi cần
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Trong CI, nên:

- Cố định JDK/toolchain và module path.
- Build từ thư mục output sạch để tránh class file cũ.
- Lưu báo cáo `jdeps` hoặc DOT graph làm artifact khi cần review dependency.
- Kiểm tra thay đổi trong `module-info.java` như thay đổi API/dependency contract.
- Chạy kiểm thử trên runtime image nếu sản phẩm phát hành bằng `jlink`.
- Không tự động bỏ qua dependency thiếu hoặc cảnh báo API nội bộ.
- Kiểm tra service binding nếu ứng dụng dùng `ServiceLoader`.

Không phải dự án nào cũng cần lưu đồ thị DOT ở mỗi lần build. Với pipeline nhỏ, `jdeps --check`, `--validate-modules` và `--dry-run` thường đủ; chỉ xuất DOT khi cần review hoặc điều tra quan hệ phức tạp.

## 16. Lỗi thường gặp khi kiểm tra module graph

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `FindException: Module ... not found` | Module không có trên module path hoặc tên module sai. | Kiểm tra `--module-path`, `module-info.java` và tên module bằng `--describe-module`. |
| `ResolutionException` | Có dependency không thể phân giải hoặc module graph xung đột. | Chạy `--validate-modules`, `jdeps --check` và xem `--show-module-resolution`. |
| `package ... is not visible` | Module cung cấp chưa export package hoặc module gọi chưa đọc module đó. | Kiểm tra `exports` và `requires`. |
| `Package ... is declared in module ...` hoặc split package | Cùng package xuất hiện trong nhiều named module không tương thích. | Hợp nhất package về một module hoặc sửa cấu trúc module. |
| `jdeps --check` gợi ý descriptor khác | Descriptor khai báo thiếu hoặc thừa dependency so với bytecode được phân tích. | Đọc suggested descriptor, xác nhận dependency tĩnh và cập nhật `requires` có chủ đích. |
| `jdeps --missing-deps` báo class không tìm thấy | Thiếu JAR/module trên đường dẫn phân tích hoặc dependency được nạp động. | Bổ sung đúng module/JAR và kiểm tra các điểm nạp động. |
| `java --dry-run` thành công nhưng chạy thật thất bại | Lỗi xuất hiện trong `main`, khởi tạo class hoặc tác vụ runtime. | Chạy chương trình và đọc stack trace; dry run không thực thi `main`. |
| `--show-module-resolution` in quá nhiều dòng | Root set lớn hoặc nhiều service provider được bind. | Lọc output theo module cần điều tra; kiểm tra `--add-modules` và service binding. |
| `jlink` báo thiếu module | Root module hoặc module path chưa đầy đủ. | Dùng `jdeps --print-module-deps`, kiểm tra `--module-path` và chạy `jlink --verbose`. |
| Ứng dụng chạy trên JDK đầy đủ nhưng runtime image lỗi | Image thiếu module/provider hoặc cấu hình runtime khác môi trường phát triển. | Kiểm tra graph, cân nhắc `--bind-services`, rồi chạy kiểm thử trên image được tạo. |

## 17. Checklist kiểm tra module graph

- Mỗi named module có module descriptor hợp lệ và tên duy nhất.
- Các chỉ thị `requires`, `requires transitive`, `requires static` phản ánh đúng dependency.
- Package cần dùng giữa các module được export đúng phạm vi.
- Module path chứa đúng modular JAR hoặc exploded module.
- `jdeps --check` không còn dependency khai báo sai hoặc qualified export không dùng ngoài dự kiến.
- `jdeps --list-deps` và `--list-reduced-deps` đã được đọc theo mục đích phù hợp.
- `jdeps --missing-deps` không còn dependency bắt buộc bị thiếu.
- `java --validate-modules` hoàn tất thành công.
- `java --dry-run` nạp được module và main class.
- `--show-module-resolution` xác nhận module được resolve từ đúng nguồn.
- Service provider được kiểm tra nếu ứng dụng dùng `ServiceLoader`.
- `jlink` tạo runtime image thành công và image chạy được trên nền tảng đích.

Khi kiểm tra module graph, hãy bắt đầu bằng `jdeps --check` để đánh giá descriptor và dependency tĩnh, dùng `--show-module-resolution` để xem lựa chọn thực tế của launcher, rồi xác nhận module path bằng `--validate-modules` và `--dry-run`. Nếu cần xem quan hệ trực quan hoặc tạo runtime image, xuất DOT bằng `jdeps --dot-output` và dùng danh sách dependency đã kiểm tra làm đầu vào cho `jlink`.
