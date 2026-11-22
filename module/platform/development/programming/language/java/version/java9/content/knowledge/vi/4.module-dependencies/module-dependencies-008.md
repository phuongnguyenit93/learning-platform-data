# Giới hạn tập mô-đun và bổ sung mô-đun gốc trong JPMS

Trong Java Platform Module System (JPMS), JVM xử lý hai câu hỏi riêng: **module nào có thể được tìm thấy** và **module nào được đưa vào module graph khi khởi động**. Tùy chọn `--limit-modules` giới hạn tập module có thể quan sát (observable modules). Tùy chọn `--add-modules` bổ sung module gốc (root modules) để resolver bắt đầu phân giải thêm module cùng các dependency của chúng.

Hiểu rõ sự khác nhau này giúp tạo module graph gọn hơn, khởi chạy module plugin hoặc module hỗ trợ không được nhắc trực tiếp trong `requires`, và chẩn đoán lỗi thiếu module. Hai tùy chọn này có từ Java 9 và vẫn được hỗ trợ trong các JDK hiện hành.

## 1. Observable modules, root modules và module graph

Trước khi dùng hai tùy chọn, cần phân biệt ba khái niệm:

- **Observable module:** module mà module finder có thể tìm thấy trong runtime image, module path hoặc nguồn module tương ứng. Module phải observable thì resolver mới có thể chọn nó.
- **Root module:** module được chọn làm điểm bắt đầu của quá trình phân giải. Khi khởi chạy bằng `-m`, module ứng dụng được chỉ định là root ban đầu. `--add-modules` bổ sung các root khác.
- **Resolved module graph:** tập module được resolver đưa vào module layer, gồm các root và những dependency cần thiết của chúng. Quan hệ `requires` được giải quyết theo đồ thị này.

Ví dụ, ứng dụng `com.acme.app` có `requires java.logging`. Khi chạy ứng dụng, `com.acme.app` là root ban đầu; resolver tiếp tục đưa `java.logging` và các dependency cần thiết của nó vào graph. Một module `com.acme.extra` có thể được tìm thấy trên module path nhưng vẫn chưa được resolve nếu không phải root và không được kéo vào bởi dependency hoặc quy tắc service binding.

Đồ thị khái niệm:

```text
Root ban đầu: com.acme.app
        |
        | requires java.logging
        v
   java.logging
        |
        v
    java.base

Module com.acme.extra có thể observable trên module path
nhưng chưa được resolve nếu không được chọn làm root.
```

`--limit-modules` điều chỉnh tập observable modules. `--add-modules` điều chỉnh tập root modules. Giới hạn một module trong tập observable không tự biến nó thành root.

## 2. Giới hạn tập module bằng `--limit-modules`

Cú pháp:

```shell
java --limit-modules module[,module...] <các tùy chọn khác>
```

`--limit-modules` giới hạn universe các module có thể quan sát vào những module được liệt kê cùng các dependency bắc cầu của chúng. Các dependency cần thiết vẫn được giữ lại để những module được chọn có thể hoạt động.

Ví dụ:

```shell
java --module-path mods \
     --limit-modules java.base,java.logging,com.acme.app,com.acme.extra \
     -m com.acme.app/com.acme.app.Main
```

Trong ví dụ, runtime chỉ xem xét tập module được nêu và dependency của chúng. Nếu `com.acme.app` cần `java.logging`, dependency này vẫn nằm trong tập observable. Những module không thuộc tập giới hạn hoặc dependency của chúng sẽ không thể được resolver chọn trong lần chạy đó.

### Tác dụng và giới hạn

- Thu hẹp module universe mà ứng dụng có thể quan sát, giúp phát hiện dependency ngoài dự kiến hoặc kiểm tra ứng dụng với một tập module được kiểm soát.
- Danh sách nhận **tên module**, phân cách bằng dấu phẩy; không phải tên package, tên JAR hay đường dẫn thư mục.
- Module tự viết phải có thể tìm thấy qua `--module-path` hoặc nguồn module hợp lệ khác. Chỉ ghi tên module trong `--limit-modules` không tạo ra module đó.
- Các dependency bắc cầu của module được liệt kê vẫn được đưa vào tập observable, kể cả khi không ghi riêng từng dependency trong danh sách.
- Module bị loại khỏi tập observable không thể được bổ sung lại làm root bằng `--add-modules` trong cùng lần chạy.

`--limit-modules` không chỉnh sửa `module-info.java`, không thay đổi quan hệ `requires` của module và không xóa JAR khỏi ổ đĩa. Đây là cấu hình cho module universe của lần khởi chạy.

## 3. Bổ sung module gốc bằng `--add-modules`

Cú pháp:

```shell
java --add-modules module[,module...] <các tùy chọn khác>
```

`--add-modules` yêu cầu resolver thêm các module được chỉ định vào tập root, bên cạnh root ban đầu. Từ các root này, resolver tiếp tục giải quyết dependency cần thiết.

Ví dụ ứng dụng khởi chạy bằng `-m com.acme.app/com.acme.app.Main`, nhưng cần một module hỗ trợ `com.acme.extra` có trên module path dù ứng dụng không khai báo `requires com.acme.extra`:

```shell
java --module-path mods \
     --add-modules com.acme.extra \
     -m com.acme.app/com.acme.app.Main
```

`com.acme.extra` được resolve thành root bổ sung. Điều này làm module xuất hiện trong module layer, nhưng **không tự tạo readability edge từ `com.acme.app` tới `com.acme.extra`**. Nếu mã nguồn của `com.acme.app` cần import kiểu công khai từ `com.acme.extra`, module ứng dụng vẫn phải khai báo `requires com.acme.extra;` trong `module-info.java` (hoặc dùng một cơ chế truy cập phù hợp khác).

### Các tên đặc biệt

`--add-modules` hỗ trợ các giá trị đặc biệt sau:

| Giá trị | Ý nghĩa |
|---|---|
| `ALL-DEFAULT` | Tất cả observable modules export ít nhất một package theo cách unqualified. |
| `ALL-SYSTEM` | Tất cả observable system modules. |
| `ALL-MODULE-PATH` | Tất cả module tìm thấy trên module path. |

Ví dụ:

```shell
java --module-path mods --add-modules ALL-MODULE-PATH -m com.acme.app/com.acme.app.Main
```

Lệnh này thêm tất cả module trên module path làm root. Nó hữu ích khi cần đưa nhiều module plugin hoặc module mở rộng vào graph, nhưng có thể làm graph lớn hơn đáng kể. Khi chỉ cần một vài module, nêu tên cụ thể giúp kiểm soát tập root rõ ràng hơn.

`ALL-DEFAULT`, `ALL-SYSTEM` và `ALL-MODULE-PATH` là giá trị của `--add-modules`; không dùng chúng như tên module thông thường trong `module-info.java`.

## 4. Kết hợp `--limit-modules` và `--add-modules`

Hai tùy chọn có thể dùng cùng nhau:

```shell
java --module-path mods \
     --limit-modules java.base,java.logging,com.acme.app,com.acme.extra \
     --add-modules com.acme.extra \
     -m com.acme.app/com.acme.app.Main
```

Trình tự tư duy:

1. `--limit-modules` xác định module universe có thể quan sát.
2. Module được chỉ định bởi `-m` là root ban đầu.
3. `--add-modules` thêm `com.acme.extra` làm root bổ sung, miễn là module này vẫn observable và có thể tìm thấy.
4. Resolver phân giải các root cùng dependency cần thiết để tạo module graph.

Nếu `com.acme.extra` không nằm trong tập observable sau khi áp dụng giới hạn, hoặc không có trên module path, resolver không thể thêm nó thành root và ứng dụng sẽ thất bại khi khởi tạo module layer.

## 5. Ví dụ chạy được: giới hạn module universe và thêm root

Ví dụ gồm hai module độc lập:

- `com.acme.app` là ứng dụng chính và khai báo `requires java.logging`.
- `com.acme.extra` là module mở rộng, không được `com.acme.app` yêu cầu trực tiếp.

Cấu trúc source:

```text
workspace/
└── src/
    ├── com.acme.app/
    │   ├── module-info.java
    │   └── com/acme/app/Main.java
    └── com.acme.extra/
        ├── module-info.java
        └── com/acme/extra/Extra.java
```

**Module ứng dụng — `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires java.logging;
}
```

**Lớp chạy — `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import java.util.logging.Level;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger.getLogger(Main.class.getName()).setLevel(Level.OFF);

        boolean extraResolved =
                ModuleLayer.boot().findModule("com.acme.extra").isPresent();

        System.out.println("com.acme.extra resolved: " + extraResolved);
    }
}
```

**Module mở rộng — `src/com.acme.extra/module-info.java`:**

```java
module com.acme.extra {
    exports com.acme.extra;
}
```

**Lớp module mở rộng — `src/com.acme.extra/com/acme/extra/Extra.java`:**

```java
package com.acme.extra;

public final class Extra {
    private Extra() {
    }

    public static String name() {
        return "extra";
    }
}
```

### Biên dịch

Chạy từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.app,com.acme.extra
```

Lệnh này biên dịch hai module vào `out/`. `com.acme.app` có dependency tới `java.logging`; `com.acme.extra` không phải dependency của ứng dụng.

### Chạy khi chỉ giới hạn tập observable

```shell
java --module-path out \
     --limit-modules java.base,java.logging,com.acme.app,com.acme.extra \
     -m com.acme.app/com.acme.app.Main
```

Stdout:

```text
com.acme.extra resolved: false
```

`com.acme.extra` nằm trong tập observable do được nêu trong `--limit-modules`, nhưng chưa phải root và không được kéo vào bởi dependency của `com.acme.app`. Vì vậy module này chưa có trong boot layer.

### Chạy khi bổ sung module mở rộng làm root

```shell
java --module-path out \
     --limit-modules java.base,java.logging,com.acme.app,com.acme.extra \
     --add-modules com.acme.extra \
     -m com.acme.app/com.acme.app.Main
```

Stdout:

```text
com.acme.extra resolved: true
```

Lần chạy này `com.acme.extra` là root bổ sung nên xuất hiện trong `ModuleLayer.boot()`. Ứng dụng vẫn không có readability tới package `com.acme.extra`; ví dụ chỉ kiểm tra module đã được resolve hay chưa.

Ví dụ đã được biên dịch và chạy trên JDK 24.0.2. Cùng một tập observable tạo ra kết quả `false` khi không thêm root và `true` khi dùng `--add-modules com.acme.extra`.

## 6. Kiểm tra module universe và module graph

Các tùy chọn chẩn đoán hữu ích:

| Lệnh | Công dụng |
|---|---|
| `java --list-modules` | Liệt kê các observable modules và kết thúc. |
| `java --show-module-resolution ...` | In thông tin resolver về root và các dependency được phân giải khi khởi động. |
| `java --module-path mods --describe-module com.acme.extra` | Xem descriptor, package export và dependency của một module. |
| `java --validate-modules` | Kiểm tra tính nhất quán của các module có thể quan sát rồi kết thúc. |
| `java --dry-run ...` | Tạo VM và nạp main class nhưng không chạy thân phương thức `main`; hữu ích để kiểm tra cấu hình khởi động. |

Ví dụ:

```shell
java --module-path out \
     --limit-modules java.base,java.logging,com.acme.app,com.acme.extra \
     --list-modules
```

`--list-modules` cho biết module nào observable. Nó không khẳng định mọi module được liệt kê đã được resolve vào boot layer. Để kiểm tra graph thực tế, dùng `--show-module-resolution` hoặc truy vấn `ModuleLayer.boot()` như ví dụ trước.

## 7. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Kết quả | Cách xử lý |
|---|---|---|
| Nghĩ `--limit-modules` tự resolve mọi module trong danh sách. | Module có thể observable nhưng chưa nằm trong module graph. | Thêm module cần thiết bằng `--add-modules` hoặc khai báo `requires`. |
| Dùng `--add-modules` cho module không observable. | Resolver không tìm thấy module hoặc không thể tạo boot layer. | Đảm bảo module có trong module path và không bị loại bởi `--limit-modules`. |
| Nghĩ `--add-modules` tự cấp quyền đọc module cho ứng dụng. | Mã ứng dụng không thể import hoặc truy cập kiểu của module chỉ vì nó đã được resolve. | Khai báo `requires` nếu ứng dụng cần readability tới module đó. |
| Liệt kê thiếu dependency trong `--limit-modules` và nghĩ dependency sẽ bị loại. | Dependency bắc cầu cần thiết vẫn có thể xuất hiện trong observable universe. | Hiểu rằng tùy chọn giữ module được nêu cùng dependency của chúng. |
| Dùng `ALL-MODULE-PATH` khi chỉ cần một module plugin. | Nhiều module không cần thiết trở thành root. | Dùng tên module cụ thể để kiểm soát graph. |
| Nhầm `--list-modules` với danh sách module đã resolve. | Chẩn đoán sai vì module observable chưa chắc là root. | Dùng `--show-module-resolution` hoặc `ModuleLayer.boot().findModule(...)`. |
| Cho rằng `--limit-modules` làm nhỏ JDK đã cài. | Dung lượng runtime image không đổi. | Nếu cần runtime image tùy chỉnh, dùng `jlink` và chỉ định root modules cho image. |

## 8. Checklist sử dụng

- Xác định module ứng dụng khởi chạy và các root mặc định trước khi thêm module.
- Dùng `--limit-modules` để giới hạn module universe theo module cần thiết cùng dependency của chúng.
- Đảm bảo module muốn thêm làm root vẫn observable và tìm thấy được trên module path.
- Dùng `--add-modules` cho module cần được resolve dù không được kéo vào qua `requires`.
- Chỉ dùng `ALL-MODULE-PATH`, `ALL-SYSTEM` hoặc `ALL-DEFAULT` khi thực sự cần toàn bộ nhóm tương ứng.
- Nhớ rằng root bổ sung không tự tạo readability edge; khai báo `requires` nếu mã cần đọc API của module.
- Kiểm tra observable set bằng `--list-modules` và graph thực tế bằng `--show-module-resolution` hoặc `ModuleLayer.boot()`.
- Chạy thử với đúng module path và giới hạn dự kiến triển khai để phát hiện dependency bị thiếu.

## Tài liệu tham khảo

- [Java Launcher — `--add-modules`, `--limit-modules` and module options (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java Language Specification — Module Declarations and Dependences (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html)
- [Java Platform Module System — `ModuleLayer` API (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [The `javac` Command — Module Source Path (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
