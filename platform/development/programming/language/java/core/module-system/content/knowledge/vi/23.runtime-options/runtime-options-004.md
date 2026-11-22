# --add-modules: thêm Observable Module vào tập Root

Trong Java Platform Module System (JPMS), một module có thể nằm trên module path nhưng chưa được đưa vào module graph của ứng dụng. Khi đó JVM có thể tìm thấy module ấy, nhưng module chưa được resolve và chưa xuất hiện trong ModuleLayer đang chạy.

Tùy chọn dòng lệnh `--add-modules` cho phép chỉ định thêm các module làm **root modules** khi JVM phân giải module graph. Đây là cách yêu cầu runtime resolve một module observable dù module chính không khai báo `requires` trực tiếp tới nó.

Điểm cần nhớ: **observable**, **root** và **resolved** là ba trạng thái liên quan nhưng không đồng nghĩa. `--add-modules` tác động tới tập root dùng để resolve module graph. Nó không tự cấp quyền readability, không export package và cũng không mở package cho deep reflection.

## 1. Observable Module là gì?

Một module được xem là observable khi runtime có thể tìm thấy mô tả module đó thông qua các nguồn module đang cấu hình. Những nguồn phổ biến gồm:

- Các system modules đi kèm JDK.
- Các module nằm trên application module path được truyền qua `--module-path`.
- Các module nằm trên upgrade module path nếu ứng dụng có cấu hình nguồn này.

Ví dụ, thư mục `mods` có thể chứa hai module:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/Main.class
└── com.example.plugin/
    ├── module-info.class
    └── com/example/plugin/PluginMarker.class
~~~

Khi chạy với:

~~~shell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Runtime có thể tìm thấy cả `com.example.app` và `com.example.plugin`. Tuy nhiên, nếu `com.example.app` không khai báo `requires com.example.plugin`, module plugin không nhất thiết được đưa vào graph chỉ vì nó đang nằm trên module path.

Nói cách khác:

- **Observable**: runtime có thể tìm thấy module.
- **Root**: module được chọn làm điểm bắt đầu của quá trình resolution.
- **Resolved**: module đã được đưa vào graph sau khi JVM phân giải các root và những dependency cần thiết.

Module path xác định nơi tìm module. `--add-modules` xác định thêm module nào cần được đưa vào tập root.

## 2. Cú pháp và ý nghĩa của --add-modules

Cú pháp:

~~~shell
java --add-modules <module>(,<module>)* ...
~~~

Có thể chỉ định một module hoặc nhiều module, phân cách bằng dấu phẩy:

~~~shell
java --module-path mods --add-modules com.example.plugin,com.example.metrics --module com.example.app/com.example.app.Main
~~~

JVM sẽ thêm các module được chỉ định vào tập root, sau đó resolve chúng cùng với dependency được khai báo bằng `requires`.

Ngoài tên module cụ thể, tùy chọn này hỗ trợ ba selector đặc biệt:

| Giá trị | Ý nghĩa |
| --- | --- |
| `ALL-DEFAULT` | Thêm toàn bộ module thuộc tập default root modules |
| `ALL-SYSTEM` | Thêm toàn bộ system modules |
| `ALL-MODULE-PATH` | Thêm toàn bộ module observable tìm thấy trên module path |

Ví dụ:

~~~shell
# Thêm một module cụ thể
java --module-path mods --add-modules com.example.plugin --module com.example.app/com.example.app.Main

# Thêm tất cả module trên module path
java --module-path mods --add-modules ALL-MODULE-PATH --module com.example.app/com.example.app.Main

# Thêm toàn bộ system modules
java --add-modules ALL-SYSTEM --module com.example.app/com.example.app.Main
~~~

Khi chỉ cần một plugin hoặc một module hỗ trợ cụ thể, nên ghi tên module đó. `ALL-MODULE-PATH` có thể khiến nhiều module không cần thiết tham gia resolution và làm lộ ra các xung đột cấu hình vốn chưa xuất hiện trước đó.

## 3. Root module ảnh hưởng đến quá trình resolution như thế nào?

Quá trình resolution bắt đầu từ tập root modules. Với mỗi root, JVM tiếp tục xem xét các dependency được khai báo qua `requires`, rồi đưa các module cần thiết vào graph.

Giả sử có các quan hệ:

~~~text
com.example.app
    └── requires com.example.api

com.example.plugin
    └── requires com.example.api

com.example.api
    └── requires java.base
~~~

Nếu `com.example.app` là root, JVM resolve app cùng các dependency cần thiết của nó. Module plugin có thể vẫn chỉ là observable module nếu không có quan hệ nào khiến nó được resolve.

Khi thêm:

~~~shell
--add-modules com.example.plugin
~~~

`com.example.plugin` trở thành một root bổ sung. JVM resolve plugin và các dependency của plugin. Kết quả là module graph có thể chứa cả app, plugin, api và java.base.

Điều này hữu ích khi một ứng dụng cần runtime nhận diện module hỗ trợ, plugin hoặc module cung cấp một khả năng được chọn theo cấu hình. Ứng dụng có thể tìm module đã resolve qua ModuleLayer API.

## 4. Ví dụ: resolve một plugin không được requires trực tiếp

Ta tạo hai module độc lập. Module app không khai báo dependency tới plugin; module plugin vẫn có mặt trên module path.

Cấu trúc thư mục:

~~~text
src/
├── com.example.app/
│   ├── module-info.java
│   └── com/example/app/Main.java
└── com.example.plugin/
    ├── module-info.java
    └── com/example/plugin/PluginMarker.java
~~~

### Module plugin

File `src/com.example.plugin/module-info.java`:

~~~java
module com.example.plugin {
    exports com.example.plugin;
}
~~~

File `src/com.example.plugin/com/example/plugin/PluginMarker.java`:

~~~java
package com.example.plugin;

public final class PluginMarker {
    private PluginMarker() {
    }
}
~~~

Module plugin export package của nó để public API có thể được module đọc nó sử dụng. Việc export này độc lập với quyết định có resolve plugin hay không.

### Module app

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.util.Optional;

public class Main {

    public static void main(String[] args) {
        Module appModule = Main.class.getModule();

        Optional<Module> pluginModule =
            ModuleLayer.boot().findModule("com.example.plugin");

        System.out.println(
            "Plugin resolved: " + pluginModule.isPresent()
        );

        pluginModule.ifPresent(plugin ->
            System.out.println(
                "App reads plugin: " + appModule.canRead(plugin)
            )
        );
    }
}
~~~

Chương trình dùng `ModuleLayer.boot().findModule(...)` để kiểm tra plugin có thuộc boot layer hiện tại hay không. Nó dùng `Module.canRead(...)` để kiểm tra quan hệ readability từ app tới plugin.

### Biên dịch

Từ thư mục gốc của ví dụ, chạy:

~~~shell
javac -d mods/com.example.plugin src/com.example.plugin/module-info.java src/com.example.plugin/com/example/plugin/PluginMarker.java

javac --module-path mods -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
~~~

### Chạy không thêm root

~~~shell
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Kết quả mong đợi:

~~~text
Plugin resolved: false
~~~

Module plugin có thể được tìm thấy trên module path, nhưng chưa được resolve vào boot layer.

### Chạy với --add-modules

~~~shell
java --module-path mods --add-modules com.example.plugin --module com.example.app/com.example.app.Main
~~~

Kết quả mong đợi:

~~~text
Plugin resolved: true
App reads plugin: false
~~~

Plugin đã được resolve và xuất hiện trong boot layer. Tuy nhiên, app vẫn chưa đọc được plugin vì module app không khai báo `requires com.example.plugin` và cũng chưa có quyền readability tương đương.

Ví dụ này cho thấy `--add-modules` giải quyết việc đưa module vào graph; nó không tự tạo quan hệ readability giữa mọi module.

## 5. Phân biệt --add-modules với các tùy chọn module khác

Các tùy chọn JPMS thường xuất hiện cùng nhau nhưng giải quyết những vấn đề khác nhau:

| Tùy chọn | Vai trò |
| --- | --- |
| `--module-path` | Chỉ định nơi runtime tìm các module ứng dụng |
| `--add-modules` | Thêm module observable vào tập root để resolve |
| `--limit-modules` | Giới hạn tập module observable mà runtime có thể sử dụng |
| `--add-reads` | Bổ sung quan hệ readability giữa module nguồn và module đích |
| `--add-exports` | Export một package của module đích cho module được chỉ định |
| `--add-opens` | Mở package cho deep reflection từ module được chỉ định |

Có thể dùng đồng thời `--add-modules` và `--add-reads` khi cần cả hai điều kiện:

~~~shell
java \
  --module-path mods \
  --add-modules com.example.plugin \
  --add-reads com.example.app=com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

Sau khi chạy với hai tùy chọn trên, plugin được resolve và app có readability tới plugin. Nếu cần truy cập public type từ package của plugin, package đó vẫn phải được export theo quy tắc JPMS. Nếu cần deep reflection vào member không public, còn phải đáp ứng quy tắc opens.

Với ứng dụng được biên dịch thành named module, `--add-reads` khi chạy không thay thế cấu hình cần thiết ở thời điểm biên dịch. Nếu mã nguồn tham chiếu trực tiếp kiểu của module khác, hãy cấu hình module dependency đúng trong `module-info.java` hoặc cung cấp tùy chọn biên dịch phù hợp cho javac.

## 6. Kết hợp với --limit-modules

`--limit-modules` giới hạn tập module mà runtime coi là observable. Vì vậy, nó có thể làm cho một module không còn nằm trong tập có thể được resolve.

Ví dụ:

~~~shell
java \
  --module-path mods \
  --limit-modules java.base,com.example.app \
  --add-modules com.example.plugin \
  --module com.example.app/com.example.app.Main
~~~

Nếu `com.example.plugin` bị loại khỏi tập observable bởi giới hạn này, JVM không thể resolve module đó chỉ nhờ `--add-modules`. Tên module được thêm làm root phải tìm thấy được trong tập module runtime cho phép quan sát.

Khi gặp lỗi không tìm thấy module, hãy kiểm tra lần lượt:

1. Module đã được biên dịch hoặc đóng gói đúng chưa?
2. Module có nằm trong đường dẫn được truyền qua `--module-path` không?
3. Tên module có khớp với tên khai báo trong `module-info.java` không?
4. Có `--limit-modules` đang loại module đó khỏi tập observable không?
5. Các dependency bắt buộc của module có thể được tìm thấy và resolve không?

Nếu module không observable hoặc dependency không thể resolve, quá trình khởi động có thể thất bại với lỗi resolution, chẳng hạn `FindException` hoặc lỗi liên quan đến module không tìm thấy.

## 7. Khi nào nên dùng --add-modules?

Một số trường hợp thường gặp:

- **Plugin được chọn theo cấu hình:** plugin nằm trên module path nhưng không phải dependency bắt buộc của module chính. Có thể thêm plugin được chọn làm root khi khởi động.
- **Module cung cấp API hoặc dịch vụ tùy chọn:** ứng dụng muốn bảo đảm module hỗ trợ được resolve trước khi tra cứu trong ModuleLayer.
- **Công cụ kiểm thử hoặc chẩn đoán:** cần đưa module cụ thể vào graph để quan sát hoặc chạy một kịch bản kiểm thử.
- **Ứng dụng cần nhiều module trên module path:** có thể dùng `ALL-MODULE-PATH` khi chủ đích là resolve tất cả module observable trong đường dẫn đó.

Không nên dùng `ALL-MODULE-PATH` theo thói quen. Việc resolve mọi module có thể làm tăng phạm vi graph và khiến xung đột package, dependency hoặc cấu hình module xuất hiện sớm hơn.

Nếu module luôn là thành phần bắt buộc của ứng dụng, khai báo `requires` trong `module-info.java` thường diễn đạt dependency rõ ràng hơn. `--add-modules` phù hợp khi cần điều khiển tập root từ cấu hình khởi chạy.

## 8. Những nhầm lẫn thường gặp

1. **Module nằm trên module path thì chắc chắn đã được resolve:** module path chỉ cung cấp nguồn tìm kiếm; module có thể observable nhưng chưa nằm trong graph.
2. **--add-modules tự cấp quyền truy cập:** tùy chọn này thêm root cho resolution. Readability, exports và opens vẫn có quy tắc riêng.
3. **Root module chỉ resolve riêng nó:** JVM còn resolve các dependency cần thiết được khai báo qua `requires`.
4. **ALL-MODULE-PATH chỉ là một module có tên:** đây là selector đặc biệt đại diện cho các module observable trên module path.
5. **Có thể thêm module không tồn tại:** module phải observable trong cấu hình runtime; nếu không, resolution sẽ thất bại.
6. **Dùng --add-modules thay cho requires trong mọi trường hợp:** dependency bắt buộc nên được thể hiện trong module descriptor để kiến trúc dễ hiểu và kiểm tra.
7. **Plugin đã resolve nghĩa là app có thể gọi trực tiếp class của plugin:** app còn cần readability và package export phù hợp.

## 9. Quy trình chẩn đoán

Khi một module có trên module path nhưng không xuất hiện trong runtime graph, hãy kiểm tra theo thứ tự:

1. Xác nhận tên module bằng `module-info.java` hoặc metadata của JAR.
2. Xác nhận module path trỏ đúng thư mục hoặc JAR chứa module.
3. Kiểm tra module có bị giới hạn bởi `--limit-modules` không.
4. Thêm module cần thiết bằng `--add-modules <module>`.
5. Kiểm tra module đã được resolve bằng `ModuleLayer.boot().findModule(name)`.
6. Nếu cần module khác sử dụng API của nó, kiểm tra readability bằng `Module.canRead`.
7. Kiểm tra exports hoặc opens nếu thao tác cần quyền truy cập package tương ứng.

Quy trình này tách rõ lỗi tìm module, lỗi resolution và lỗi truy cập. Nhờ vậy, có thể xác định đúng tùy chọn runtime cần điều chỉnh.

## Kết luận

`--add-modules` bổ sung module observable vào tập root để JVM resolve module graph. Nó hữu ích khi cần đưa plugin, module hỗ trợ hoặc module tùy chọn vào runtime mà không khai báo dependency bắt buộc trong module chính. Hãy nhớ rằng resolve module chỉ bảo đảm module có mặt trong graph; readability, exports và opens vẫn phải được cấu hình theo nhu cầu truy cập thực tế.
