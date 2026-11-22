# Đồ thị phụ thuộc đầy đủ và module thừa

Trong Java Platform Module System (JPMS), **module graph** là đồ thị các module đã được giải quyết cho một cấu hình chạy hoặc một module layer. Đồ thị này hình thành từ các module gốc (root modules), những directive phụ thuộc như `requires` và các quy tắc service binding. Nó không đồng nghĩa với toàn bộ JAR đang nằm trong thư mục module path.

Vì vậy, khi phân tích một ứng dụng module hóa, cần phân biệt ba tập hợp:

- **Module có thể quan sát:** module mà module finder có thể tìm thấy từ module path và các nguồn module được cấu hình.
- **Module được giải quyết:** module thực sự được đưa vào cấu hình sau khi bắt đầu từ các root và lần theo dependency/service binding.
- **Module không cần thiết hoặc module thừa:** module có thể quan sát hoặc thậm chí đã được đưa vào cấu hình, nhưng ứng dụng không thực sự cần cho chức năng đang xét.

Phân biệt đúng các tập hợp này giúp tìm dependency bị thiếu, phát hiện module không cần thiết, giảm phạm vi runtime image và tránh thêm tùy chọn khiến cấu hình chạy lớn hơn dự kiến.

## 1. Module graph gồm những gì?

Có thể hình dung module graph là một tập hợp nút và quan hệ đọc module:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.api
~~~

Trong ví dụ, `com.acme.app` phụ thuộc trực tiếp vào `com.acme.service`. Module service phụ thuộc vào `com.acme.api` và truyền khả năng đọc dependency đó cho module sử dụng nó bằng `requires transitive`.

Khi ứng dụng được khởi chạy với `com.acme.app` làm module chính, JVM giải quyết module app và các dependency bắt buộc của nó. Các module cần thiết được kéo vào cấu hình theo quan hệ phụ thuộc. Kết quả không chỉ là danh sách JAR; đó là cấu hình module có các quan hệ readability được xác định theo JPMS.

Readability và quyền truy cập package là hai điều kiện khác nhau. Một module có thể đọc module khác nhưng vẫn không truy cập được kiểu trong package chưa được export. Vì thế, khi đọc graph cần kiểm tra cả quan hệ module lẫn các directive `exports`/`opens`.

## 2. Root modules quyết định điểm bắt đầu

Resolution bắt đầu từ một tập hợp **root modules**. Với cách chạy ứng dụng module hóa:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Module `com.acme.app` là root được chỉ định. JVM đọc descriptor của module này, tìm các module mà nó yêu cầu và tiếp tục lần theo dependency của chúng.

Ví dụ các descriptor:

~~~java
// com.acme.app
module com.acme.app {
    requires com.acme.service;
}
~~~

~~~java
// com.acme.service
module com.acme.service {
    requires transitive com.acme.api;
}
~~~

~~~java
// com.acme.api
module com.acme.api {
    exports com.acme.api;
}
~~~

Nếu cả ba module có thể được tìm thấy, graph sẽ chứa app, service và api. Module api được kéo vào vì service yêu cầu nó. Không cần thêm từng dependency vào lệnh chạy nếu chúng đã được khai báo chính xác và có thể được tìm thấy.

Với ứng dụng chạy main class trên classpath, root modules có thể được bổ sung bằng `--add-modules`:

~~~bash
java --module-path mods \
     --add-modules com.acme.service \
     -cp out \
     com.acme.app.Main
~~~

Tùy chọn này yêu cầu module service làm root bổ sung. Các dependency của service tiếp tục được giải quyết theo descriptor của chúng.

## 3. Module path có thể chứa module không nằm trong graph

Giả sử thư mục có nhiều JAR:

~~~text
mods/
├── com.acme.api.jar
├── com.acme.service.jar
├── com.acme.metrics.jar
├── com.acme.debug.tools.jar
└── com.acme.unused.adapter.jar
~~~

Nếu ứng dụng chỉ yêu cầu service và service chỉ yêu cầu api, graph có thể chỉ cần:

~~~text
com.acme.app
    └── com.acme.service
            └── com.acme.api
~~~

Các JAR metrics, debug tools và unused adapter có thể được tìm thấy trên module path nhưng không được đưa vào cấu hình nếu chúng không phải root và không được dependency hoặc service binding kéo vào.

Điều này có nghĩa:

- Có file JAR trên module path không đồng nghĩa module đã được resolve.
- Module không nằm trong graph không thể được giả định là có thể dùng trong layer hiện tại.
- Thêm một module làm root có thể khiến module đó và dependency của nó tham gia cấu hình.
- Cần quan sát graph thực tế thay vì suy luận từ danh sách file trong thư mục.

Một module “thừa” có thể chỉ là module không được sử dụng trong lần chạy hiện tại. Nếu module được thêm làm root hoặc được service binding kéo vào, nó có thể trở thành một phần của graph dù ứng dụng không gọi API của nó trực tiếp.

## 4. requires và các kiểu dependency

Các directive `requires` ảnh hưởng trực tiếp tới dependency graph.

### requires thông thường

~~~java
module com.acme.service {
    requires com.acme.api;
}
~~~

Module service cần đọc module api. Nếu dependency bắt buộc không thể được tìm thấy, resolution có thể thất bại trước khi ứng dụng chạy.

### requires transitive

~~~java
module com.acme.service {
    requires transitive com.acme.api;
}
~~~

Module đọc service cũng được truyền khả năng đọc api. Chỉ dùng `transitive` khi API public của service làm lộ kiểu thuộc api và người sử dụng service thực sự cần đọc module đó.

### requires static

~~~java
module com.acme.annotations.integration {
    requires static com.acme.annotations;
}
~~~

Dependency static bắt buộc có khi biên dịch nhưng có thể vắng mặt khi chạy. Nếu module được yêu cầu có mặt trong cấu hình runtime, quan hệ đọc được thiết lập theo quy tắc JPMS. Nếu nó vắng mặt, riêng directive `requires static` không bắt buộc runtime resolution phải thất bại.

Không nên dùng `requires static` cho dependency mà đường thực thi bắt buộc phải nạp lớp khi chạy. Nếu code gọi chức năng cần dependency đó, thiếu lớp vẫn có thể gây lỗi ở runtime.

## 5. Service binding có thể kéo thêm module vào graph

JPMS hỗ trợ service provider thông qua `uses` và `provides ... with ...`. Khi resolution thực hiện service binding, module cung cấp service phù hợp có thể được đưa vào cấu hình.

Ví dụ module ứng dụng:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

Module provider:

~~~java
module com.acme.formatter.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.formatter.json.JsonFormatter;
}
~~~

Provider có thể được kéo vào graph trong quá trình service binding. Với Java launcher, tùy chọn `--bind-services` yêu cầu resolution thực hiện binding:

~~~bash
java --module-path mods \
     --bind-services \
     -m com.acme.app/com.acme.app.Main
~~~

Do đó, một module không xuất hiện trong chuỗi `requires` trực tiếp vẫn có thể tham gia graph nếu nó cung cấp service phù hợp và service binding được thực hiện. Khi kiểm tra module thừa, phải tính cả service provider thay vì chỉ tìm dependency tĩnh.

Không phải cứ có một JAR provider trên module path là nó tự động được đưa vào mọi graph. Hãy kiểm tra `uses`, `provides`, module có thể quan sát và tùy chọn service binding của lần chạy.

## 6. Thêm tất cả module trên module path có thể làm graph lớn hơn

Tùy chọn `--add-modules` cho phép bổ sung root modules. Có thể chỉ định từng module:

~~~bash
java --module-path mods \
     --add-modules com.acme.metrics,com.acme.debug.tools \
     -m com.acme.app/com.acme.app.Main
~~~

Hoặc yêu cầu tất cả module quan sát được trên module path làm root:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     -m com.acme.app/com.acme.app.Main
~~~

`ALL-MODULE-PATH` khiến tất cả module có thể quan sát được trên module path được thêm làm root. Đây là cách hữu ích cho một số tình huống kiểm thử hoặc khám phá, nhưng có thể kéo thêm module và dependency vào graph mà ứng dụng không cần.

Hệ quả có thể gồm:

- Tăng số module phải resolve và kiểm tra.
- Làm lộ xung đột module hoặc split package vốn chưa xuất hiện trong cấu hình nhỏ hơn.
- Kéo thêm provider vào cấu hình khi service binding được thực hiện.
- Làm runtime image hoặc môi trường chạy có phạm vi lớn hơn cần thiết.
- Khiến dependency thực tế khó phân biệt vì nhiều module được thêm chủ động làm root.

Trong cấu hình production, nên chọn root modules theo chức năng cần chạy. Không dùng `ALL-MODULE-PATH` như cách chữa chung cho lỗi thiếu dependency; trước hết hãy xác định module nào thực sự cần thiết.

## 7. Giới hạn tập module có thể quan sát

`--limit-modules` giới hạn tập module mà module resolution có thể quan sát. Ví dụ:

~~~bash
java --module-path mods \
     --limit-modules java.base,java.logging,com.acme.app \
     -m com.acme.app/com.acme.app.Main
~~~

Danh sách này giới hạn các module có thể được dùng trong cấu hình. Nếu một dependency bắt buộc không thuộc tập được phép quan sát, resolution có thể thất bại với lỗi không tìm thấy module.

Tùy chọn này hữu ích khi muốn thử nghiệm một cấu hình nhỏ hoặc kiểm tra một ứng dụng có vô tình phụ thuộc vào module ngoài dự kiến hay không. Tuy nhiên, cần tính cả dependency bắc cầu và module provider nếu cấu hình sử dụng service binding.

`--limit-modules` không phải thao tác xóa JAR hoặc xóa module khỏi thư mục. Nó điều chỉnh phạm vi module finder/resolution cho tiến trình được khởi chạy.

## 8. Phát hiện module thừa bằng công cụ JDK

### Quan sát resolution thực tế

Dùng `--show-module-resolution`:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Output giúp xác định module nào được resolve, module nào là root và dependency được tìm thấy từ đâu. Khi so sánh cấu hình có và không có `--add-modules` hoặc `--bind-services`, có thể thấy module nào được thêm vào graph.

### Phân tích dependency bằng jdeps

`jdeps` phân tích dependency ở cấp bytecode và có thể giúp xác định các module mà ứng dụng cần:

~~~bash
jdeps --module-path mods \
      --print-module-deps \
      app.jar
~~~

Hoặc xem danh sách dependency chi tiết hơn:

~~~bash
jdeps --module-path mods \
      --list-deps \
      app.jar
~~~

Các lệnh này hỗ trợ phân tích dependency tĩnh từ bytecode. Chúng có thể không phát hiện đầy đủ các dependency được nạp động bằng reflection, tên lớp tạo từ cấu hình, plugin hoặc cơ chế service ở runtime. Cần kết hợp kết quả với cấu hình triển khai và kiểm thử các đường chạy thực tế.

### Kiểm tra descriptor của một JAR

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

Lệnh này hiển thị tên module và các directive được đóng gói. Nó giúp phân biệt module nào khai báo dependency trực tiếp, package nào được export và module nào là automatic module. Kết quả mô tả descriptor không tự chứng minh module đó đã tham gia graph của một tiến trình cụ thể.

## 9. Module graph và runtime image với jlink

Khi tạo custom runtime image, `jlink` sử dụng module graph để xác định module cần có trong image. Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --output runtime-image
~~~

`--add-modules com.acme.app` chọn module gốc; dependency closure của nó được đưa vào image. Nếu thêm các root không cần thiết, image có thể chứa nhiều module hơn dự kiến.

Có thể kết hợp service binding khi cần đưa các provider module phù hợp vào image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.acme.app \
      --bind-services \
      --output runtime-image
~~~

Khi tối ưu image, hãy xác định rõ root module và các provider thực sự cần. Một dependency được nạp động hoặc tên lớp được tạo từ cấu hình có thể không được công cụ phân tích bytecode nhận diện; phải kiểm thử image đã tạo với các tính năng mà ứng dụng triển khai.

## 10. Ví dụ phân biệt module cần thiết và module thừa

Giả sử ứng dụng có dependency:

~~~text
com.acme.app
    requires com.acme.service

com.acme.service
    requires com.acme.api

com.acme.api
    exports com.acme.api
~~~

Module path có thêm:

~~~text
com.acme.metrics
com.acme.debug.tools
com.acme.unused.adapter
~~~

Nếu không có dependency hoặc service binding kéo các module phụ vào, graph tối thiểu có thể là:

~~~text
com.acme.app
    └── com.acme.service
            └── com.acme.api
~~~

Khi chạy với `--add-modules ALL-MODULE-PATH`, các module metrics, debug tools và unused adapter cũng được thêm làm root. Khi đó, graph lớn hơn dù mã ứng dụng không trực tiếp dùng chúng.

Cách phân tích:

1. Chạy cấu hình bình thường với `--show-module-resolution`.
2. Ghi lại module được resolve.
3. Chạy `jdeps` để phân tích dependency bytecode.
4. Xem descriptor và service declaration của các module bổ sung.
5. Kiểm tra các plugin hoặc tính năng nạp động có cần module đó không.
6. Chỉ loại bỏ module khỏi cấu hình khi đã xác nhận không có đường chạy nào cần nó.

Module không có dependency bytecode trực tiếp vẫn có thể cần cho service provider, plugin hoặc reflection. Vì vậy, không nên xóa một module chỉ dựa trên việc `jdeps` không liệt kê nó.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| `FindException: Module ... not found` | Module bắt buộc không thể quan sát hoặc bị giới hạn bởi `--limit-modules` | Kiểm tra module path, tên module và tập module được phép |
| Module có trong thư mục nhưng không có trong resolution output | Không phải root, không được dependency kéo vào hoặc service binding chưa chạy | Kiểm tra root, `requires`, `uses`/`provides` và `--bind-services` |
| Lỗi split package khi thêm ALL-MODULE-PATH | Các module bổ sung tạo xung đột package | Thu hẹp root modules và kiểm tra package của từng JAR |
| Runtime image thiếu plugin/provider | Phân tích dependency tĩnh không nhận ra đường nạp động hoặc service binding | Bổ sung root/provider cần thiết và kiểm thử image |
| Ứng dụng chạy với IDE nhưng lỗi khi chạy bằng launcher | IDE có thể cấu hình thêm module path, root hoặc JVM options | So sánh lệnh chạy thực tế và output `--show-module-resolution` |

## 12. Quy trình tối ưu graph

Khi cần tìm module thừa hoặc làm runtime image nhỏ hơn, hãy làm theo quy trình:

1. Xác định module ứng dụng là root.
2. Đọc toàn bộ `requires` và các dependency bắc cầu.
3. Xem module provider cần thiết qua `uses`/`provides`.
4. Chạy `--show-module-resolution` để quan sát graph thực tế.
5. Dùng `jdeps` để tìm dependency bytecode và đối chiếu với reflection/plugin/runtime config.
6. Thử cấu hình root tối thiểu, tránh thêm `ALL-MODULE-PATH` nếu không cần.
7. Dùng `--limit-modules` hoặc `jlink` khi muốn kiểm tra/tạo tập module giới hạn.
8. Chạy kiểm thử chức năng trên cấu hình cuối cùng để xác nhận không bỏ sót module nạp động hoặc provider.

## 13. Ghi nhớ

Module graph được hình thành từ root modules, dependency và service binding. Module path chỉ cung cấp các module có thể được tìm thấy; nó không tự động đưa tất cả module vào cấu hình. `--add-modules ALL-MODULE-PATH` có thể thêm mọi module quan sát được làm root, còn `--limit-modules` giới hạn tập module có thể quan sát.

Để xác định module thừa, hãy kết hợp `--show-module-resolution`, `jdeps`, descriptor và hiểu biết về plugin/reflection/service của ứng dụng. Chỉ giữ graph cần thiết cho các tính năng thực tế; kiểm thử lại runtime image và các đường chạy động trước khi phát hành.
