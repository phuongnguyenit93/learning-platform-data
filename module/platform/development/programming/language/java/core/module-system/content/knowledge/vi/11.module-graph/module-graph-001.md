# Root modules và tập module ban đầu

## 1. Module path không đồng nghĩa với tập module đã được nạp

Khi chạy một ứng dụng JPMS, thư mục module path có thể chứa rất nhiều modular JAR. Tuy nhiên, việc một JAR xuất hiện trên module path chỉ có nghĩa module system có thể tìm thấy nó. Module đó chưa chắc đã thuộc cấu hình module đang chạy.

Cần phân biệt ba khái niệm:

- **Observable module**: module mà các `ModuleFinder` đang dùng có thể tìm thấy, chẳng hạn module trên system module path hoặc application module path.
- **Root module**: module được chọn làm điểm bắt đầu cho quá trình phân giải.
- **Resolved module**: module đã được đưa vào `Configuration` sau khi module system phân giải các root và dependency liên quan.

Module resolution bắt đầu từ một tập root module. Từ tập ban đầu đó, module system lần theo các chỉ thị `requires` để tìm và đưa dependency cần thiết vào cấu hình. Vì vậy, không phải mọi module có trên đĩa đều tự động được phân giải.

Ví dụ module path có:

~~~text
mods/
  com.acme.app.jar
  com.acme.api.jar
  com.acme.impl.jar
  com.acme.tools.jar
~~~

Nếu ứng dụng chỉ khai báo:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

thì `com.acme.app` và dependency `com.acme.api` được đưa vào graph cùng các dependency tiếp theo của chúng. `com.acme.impl` và `com.acme.tools` không tự động trở thành module đã phân giải chỉ vì chúng nằm trong thư mục `mods`.

## 2. Root module là điểm bắt đầu của module resolution

Root module là module mà quá trình resolution bắt đầu từ đó. Nó không phải một loại module riêng và cũng không phải khái niệm module cha trong cấu trúc thư mục.

Với một ứng dụng được khởi chạy theo tên module:

~~~bash
java --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

module `com.acme.app` là root module chính của ứng dụng. Module system đọc descriptor của nó, tìm các module được yêu cầu, rồi tiếp tục xử lý dependency của những module đó.

Có thể bổ sung root module bằng tùy chọn `--add-modules`:

~~~bash
java --module-path mods \
  --add-modules com.acme.plugin \
  --module com.acme.app/com.acme.app.Main
~~~

Trong ví dụ này, cả `com.acme.app` và `com.acme.plugin` đều là điểm bắt đầu của quá trình resolution. Plugin được đưa vào cấu hình dù ứng dụng chính không khai báo `requires com.acme.plugin`.

Cách này hữu ích khi ứng dụng cần module được nạp để dùng qua reflection, registry riêng hoặc một cơ chế plugin khác mà dependency không được thể hiện bằng `requires` trực tiếp.

## 3. Tập module ban đầu được hình thành như thế nào?

Tập root ban đầu phụ thuộc cách ứng dụng được khởi chạy và những tùy chọn mà người chạy cung cấp.

### Khởi chạy modular application

Khi dùng `-m` hoặc `--module` để chỉ định main module, module được chỉ định là root. Các module bổ sung có thể được đưa vào bằng `--add-modules`.

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Trong trường hợp này, không cần đưa mọi module trong `mods` vào root set. Các dependency được khai báo sẽ được phân giải từ main module.

### Khởi chạy ứng dụng trên classpath

Khi chạy ứng dụng truyền thống bằng classpath, mã ứng dụng thuộc unnamed module. Để mã classpath có thể sử dụng các API module phù hợp, launcher mặc định chọn làm root các observable module export ít nhất một package unconditionally (không giới hạn bằng qualified export).

Điều này có nghĩa một module chỉ export package cho một module cụ thể không tự động được chọn làm default root chỉ vì nó có mặt trên module path.

Có thể bổ sung module cần thiết bằng `--add-modules` nếu ứng dụng classpath cần truy cập nó.

### java.base luôn là root

`java.base` là module nền tảng chứa các API cốt lõi như `java.lang`, `java.util` và nhiều kiểu cơ bản. Mọi named module đều đọc `java.base`, và module này luôn được xem là root trong quá trình resolution. Không cần khai báo `requires java.base` trong từng descriptor.

## 4. requires mở rộng tập module đã phân giải

Giả sử có ba module:

~~~text
com.acme.app
  requires com.acme.service

com.acme.service
  requires com.acme.domain

com.acme.domain
  (không có dependency ứng dụng)
~~~

Khi `com.acme.app` là root, module system phân giải theo chuỗi:

1. Bắt đầu với root `com.acme.app`.
2. Đọc descriptor và tìm `com.acme.service`.
3. Đưa `com.acme.service` vào graph, sau đó đọc descriptor của nó.
4. Tìm và đưa `com.acme.domain` vào graph.
5. Tiếp tục cho tới khi không còn dependency bắt buộc nào cần được phân giải.

Kết quả là tập module đã phân giải chứa app, service, domain và các dependency nền tảng cần thiết.

Một cạnh `requires` tạo dependency và readability trực tiếp từ module khai báo tới module được yêu cầu. `requires transitive` còn làm cho các module đọc module trung gian cũng đọc được dependency được truyền qua API.

Ví dụ:

~~~java
module com.acme.service {
    requires transitive com.acme.domain;
}
~~~

Nếu app chỉ khai báo `requires com.acme.service`, app có readability tới cả service và domain. Tuy nhiên, `requires transitive` không phải một root module mới; nó ảnh hưởng đến readability của những module phụ thuộc vào service. Domain vẫn được đưa vào cấu hình thông qua dependency của service.

## 5. Module tùy chọn và requires static

Một module có thể khai báo dependency tùy chọn ở runtime:

~~~java
module com.acme.reporting {
    requires static com.acme.pdf.api;
}
~~~

`requires static` yêu cầu module có mặt khi biên dịch. Ở runtime, nếu module tùy chọn không được cung cấp thì module system có thể tiếp tục mà không phân giải dependency đó. Nếu module có mặt và được tìm thấy, nó có thể được phân giải như dependency.

Cần lưu ý:

- `requires static` không tự thêm một module không liên quan vào root set.
- Nếu module tùy chọn không có mặt, mã chạy không được giả định rằng các lớp của nó luôn tồn tại.
- Nếu tính năng thực sự cần module đó, ứng dụng phải bảo đảm module được cung cấp và được phân giải trong cấu hình tương ứng.
- Nếu dependency chỉ được tải qua tên lớp hoặc reflection, hãy kiểm tra root set và runtime configuration thay vì chỉ dựa vào việc JAR nằm trong thư mục.

## 6. Dùng --add-modules để chọn root bổ sung

Tùy chọn launcher:

~~~bash
--add-modules module[,module...]
~~~

cho phép thêm một hoặc nhiều module vào root set. Các module phải quan sát được qua các module finder và có thể được phân giải cùng dependency của chúng.

Ví dụ thêm hai module:

~~~bash
java --module-path mods \
  --add-modules com.acme.plugin,com.acme.metrics \
  -m com.acme.app/com.acme.app.Main
~~~

Các tên đặc biệt sau cũng có thể dùng với `--add-modules`:

| Giá trị | Ý nghĩa |
|---|---|
| `ALL-DEFAULT` | Thêm toàn bộ default root modules |
| `ALL-SYSTEM` | Thêm toàn bộ system modules quan sát được |
| `ALL-MODULE-PATH` | Thêm tất cả module được tìm thấy trên module path |

Ví dụ:

~~~bash
java --module-path mods \
  --add-modules ALL-MODULE-PATH \
  -m com.acme.app/com.acme.app.Main
~~~

Lệnh này yêu cầu resolution bắt đầu thêm từ tất cả module trên module path. Nó hữu ích cho một số môi trường thử nghiệm hoặc ứng dụng cần khám phá rộng module, nhưng không nên dùng như mặc định cho ứng dụng production nếu chỉ cần một số plugin cụ thể.

Khi đưa toàn bộ module path vào root set, các vấn đề như module trùng tên, split package hoặc dependency xung đột có thể làm resolution thất bại. Chọn root cụ thể thường giúp cấu hình dễ hiểu và ít phụ thuộc hơn.

## 7. Phân biệt ALL-DEFAULT, ALL-SYSTEM và ALL-MODULE-PATH

Ba giá trị đặc biệt phục vụ ba phạm vi khác nhau:

- `ALL-DEFAULT` liên quan tới tập root mặc định của launcher trong ngữ cảnh chạy hiện tại.
- `ALL-SYSTEM` chọn các module thuộc system module finder, bao gồm những module nền tảng không nhất thiết là default root.
- `ALL-MODULE-PATH` chọn module được tìm thấy trên application module path.

Ví dụ, một module ứng dụng có thể chỉ cần một module hệ thống nâng cao:

~~~bash
java --module-path mods \
  --add-modules jdk.crypto.ec \
  -m com.acme.app/com.acme.app.Main
~~~

Nếu muốn thêm toàn bộ module hệ thống, có thể dùng `ALL-SYSTEM`; nếu muốn thêm các module do ứng dụng đóng gói trên module path, dùng `ALL-MODULE-PATH`.

Không nên nhầm `ALL-SYSTEM` với `ALL-MODULE-PATH`: module hệ thống thuộc JDK, còn module path thường chứa module của ứng dụng hoặc thư viện bên thứ ba. Một module nằm trên module path không trở thành system module chỉ vì nó có mặt trong runtime.

## 8. Service provider có thể mở rộng graph bằng service binding

Một ứng dụng có thể khai báo service bằng `uses`, còn module provider đăng ký implementation bằng `provides ... with ...`.

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Nếu ứng dụng muốn module resolution liên kết service provider, launcher hỗ trợ:

~~~bash
java --bind-services --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Với service binding, module provider phù hợp có thể được đưa vào graph dù không phải dependency `requires` trực tiếp của root. Dependency của provider cũng tiếp tục được phân giải.

Trong API tạo module layer riêng, có thể dùng `Configuration.resolveAndBind(...)` thay cho `resolve(...)` khi cần liên kết provider tự động. Nếu chỉ dùng `resolve(...)`, đừng giả định mọi provider quan sát được đều được thêm vào graph.

Service binding không thay thế `uses`, `provides` hoặc việc cung cấp module trên module path. Consumer vẫn cần khai báo service mình sử dụng, provider cần khai báo implementation và artifact phải có mặt trong module finder phù hợp.

## 9. Module có trên module path nhưng không được phân giải

Đây là nguyên nhân thường gặp khi ứng dụng dùng plugin hoặc module tải theo tên:

- JAR có trong thư mục nhưng không thuộc dependency closure của root.
- Ứng dụng gọi `Class.forName` với tên lớp plugin nhưng module chứa lớp chưa được đưa vào configuration.
- Consumer khai báo `uses` nhưng provider không được liên kết vì chưa bật service binding hoặc layer được tạo theo cách không resolve-and-bind.
- Tên module truyền vào `--add-modules` không đúng với tên module thực tế.
- Module bị giới hạn khỏi tập observable bởi cấu hình launcher.

Nếu cần module luôn có mặt, hãy khai báo dependency `requires` khi đó là dependency thực sự, hoặc thêm module vào root set bằng `--add-modules`. Với SPI, dùng service binding phù hợp.

## 10. --limit-modules không giống --add-modules

`--add-modules` bổ sung root module. Ngược lại, `--limit-modules` giới hạn tập observable module mà launcher có thể xem xét.

Ví dụ:

~~~bash
java --limit-modules java.base,java.logging \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Nếu ứng dụng hoặc dependency cần module bị loại khỏi tập observable, quá trình resolution có thể thất bại với lỗi thiếu module.

Do đó:

- Dùng `--add-modules` khi cần mở rộng tập root.
- Dùng `--limit-modules` khi muốn thu hẹp tập module có thể quan sát, chẳng hạn tạo runtime nhỏ hơn hoặc kiểm tra dependency có thực sự cần thiết.
- Không dùng `--limit-modules` để cố đưa plugin vào graph; tùy chọn này có mục tiêu ngược lại.

## 11. Tự tạo module configuration và layer

Khi ứng dụng quản lý plugin bằng module layer riêng, code có thể chọn root rõ ràng:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("com.acme.plugin"));

ModuleLayer layer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

Trong ví dụ này:

- `ModuleFinder.of(Path.of("plugins"))` tìm module plugin.
- `Set.of("com.acme.plugin")` là root set cho configuration mới.
- `resolve(...)` phân giải root và dependency theo các chỉ thị `requires`.
- `defineModulesWithOneLoader(...)` tạo layer mới từ configuration đã phân giải.

Nếu muốn service provider được liên kết tự động, dùng overload `resolveAndBind(...)` thích hợp. Sau khi tạo layer, có thể tìm service từ layer đó bằng `ServiceLoader.load(layer, PaymentProcessor.class)`.

Một module layer có configuration riêng. Module đã được phân giải trong boot layer không tự động có nghĩa plugin ở layer con đã được tạo; hãy kiểm tra đúng layer mà ứng dụng tải class hoặc service.

## 12. Quan sát tập module được phân giải

Các lệnh sau giúp chẩn đoán:

~~~bash
java --list-modules
~~~

Liệt kê các module mà runtime quan sát được trong ngữ cảnh launcher.

~~~bash
java --show-module-resolution --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Hiển thị quá trình module resolution, bao gồm các module được chọn và quan hệ dependency được xử lý.

Để kiểm tra module name của một JAR:

~~~bash
jar --describe-module --file mods/com.acme.plugin.jar
~~~

Để phân tích dependency bytecode:

~~~bash
jdeps --print-module-deps --module-path mods app.jar
~~~

Khi đọc kết quả, phân biệt module quan sát được với module thực sự được phân giải. Một JAR có tên trong danh sách module không chứng minh module đó đã thuộc graph của ứng dụng đang chạy.

## 13. Quy trình chọn root module có thể dự đoán

Với ứng dụng modular thông thường:

1. Xác định main module và dùng nó làm root.
2. Khai báo dependency trực tiếp bằng `requires` trong descriptor.
3. Chỉ thêm `--add-modules` cho plugin hoặc module thực sự cần có mặt nhưng không được thể hiện qua dependency.
4. Nếu dùng SPI, khai báo `uses` và `provides`, sau đó bật service binding khi cấu hình yêu cầu.
5. Tránh thêm toàn bộ module path nếu chỉ cần vài module cụ thể.
6. Dùng `--show-module-resolution` để xác nhận graph thực tế.
7. Nếu tạo custom layer, ghi rõ root set và lựa chọn `resolve` hay `resolveAndBind`.

Cách chọn root minh bạch giúp tránh phụ thuộc ngầm vào module tình cờ có mặt trong môi trường phát triển. Build, test và production nên dùng module path cùng root selection tương ứng.

## Kết luận

Root module là tập hạt giống để JPMS bắt đầu module resolution. Từ các root, module system lần theo dependency `requires` để tạo graph đã phân giải. Module chỉ nằm trên module path chưa chắc được đưa vào graph; nếu ứng dụng cần module độc lập như plugin, hãy chọn nó làm root bằng `--add-modules` hoặc dùng service binding khi phù hợp.

Hiểu rõ observable modules, root modules và resolved modules giúp kiểm soát module configuration, thiết kế plugin layer và chẩn đoán lỗi thiếu module ở runtime.