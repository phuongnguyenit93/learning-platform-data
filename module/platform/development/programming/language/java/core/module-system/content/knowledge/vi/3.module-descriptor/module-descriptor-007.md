# Descriptor tĩnh và module graph runtime

Trong Java Platform Module System (JPMS), **module descriptor** mô tả hợp đồng và các phụ thuộc mà một module khai báo; **module graph runtime** là đồ thị các module thực tế được JVM giải quyết cho một lần chạy. Hai khái niệm liên quan chặt chẽ nhưng không đồng nhất: descriptor là metadata được đóng gói cùng module, còn graph được hình thành khi JVM kết hợp các descriptor với module có thể tìm thấy, module gốc được chọn và cấu hình khởi chạy.

Hiểu sự khác nhau này giúp giải thích vì sao một module có thể biên dịch thành công nhưng chạy thất bại, vì sao một thư viện có trong module path vẫn chưa chắc được đưa vào cấu hình runtime, và vì sao các tùy chọn như `--add-modules` hoặc `--add-reads` có thể thay đổi hành vi chạy mà không sửa file `module-info.java`.

## 1. Module descriptor là mô tả tĩnh

Một named module thường khai báo descriptor trong file nguồn `module-info.java`. Khi biên dịch, `javac` tạo file nhị phân `module-info.class`. File này nằm ở gốc modular JAR và được JVM đọc khi giải quyết module.

Ví dụ descriptor của một thư viện:

~~~java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service.api;
    uses com.acme.service.spi.Engine;
}
~~~

Descriptor trên khai báo các thông tin có tính tĩnh:

- Tên module là `com.acme.service`.
- Module phụ thuộc vào `com.acme.api` và truyền khả năng đọc dependency này cho module sử dụng nó bằng `requires transitive`.
- Package `com.acme.service.api` là API được export.
- Module sử dụng service có kiểu `com.acme.service.spi.Engine`.

Descriptor có thể chứa các directive khác như `requires static`, `exports ... to ...`, `opens`, `provides ... with ...`. Những khai báo này mô tả yêu cầu, quyền truy cập và quan hệ service của module.

Descriptor không lưu danh sách tất cả JAR đang có trên máy, không ghi lại module nào đã được JVM nạp trong một tiến trình cụ thể, cũng không chứa module graph runtime hoàn chỉnh. Nó là đầu vào để công cụ biên dịch và JVM giải quyết cấu hình.

## 2. Module graph runtime là gì?

Khi khởi chạy ứng dụng theo module path, JVM tìm các module có thể quan sát được, chọn các module gốc (root modules), rồi lần theo các directive phụ thuộc để giải quyết cấu hình. Kết quả là một tập hợp module đã được giải quyết cùng các quan hệ đọc module giữa chúng.

Có thể hình dung đơn giản:

~~~text
module descriptor (.class)
        |
        |  module path + root modules + runtime options
        v
module resolution
        |
        v
resolved configuration / module graph
        |
        v
module layer trong JVM
        |
        v
class loading, access checks và execution
~~~

Trong graph, module là các nút. Các quan hệ `requires` tạo ra quan hệ đọc module (readability) theo quy tắc JPMS. Module được chọn làm root sẽ kéo theo các module cần thiết theo dependency graph. Những module chỉ tình cờ nằm trong thư mục module path nhưng không thuộc cấu hình được giải quyết có thể không trở thành thành viên của layer đang chạy.

Module graph gắn với cấu hình và module layer cụ thể. Một ứng dụng có thể tạo thêm module layer trong runtime; vì thế không phải mọi module có mặt trong toàn bộ tiến trình đều nhất thiết thuộc boot layer ban đầu.

## 3. Ví dụ: từ các descriptor đến graph runtime

Giả sử có ba module:

~~~text
com.acme.api
    exports com.acme.api

com.acme.service
    requires transitive com.acme.api
    exports com.acme.service.api

com.acme.app
    requires com.acme.service
~~~

Descriptor tương ứng có thể viết như sau:

~~~java
// com.acme.api/module-info.java
module com.acme.api {
    exports com.acme.api;
}
~~~

~~~java
// com.acme.service/module-info.java
module com.acme.service {
    requires transitive com.acme.api;
    exports com.acme.service.api;
}
~~~

~~~java
// com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.service;
}
~~~

Biên dịch cả ba module với JDK 21:

~~~bash
javac --module-source-path src -d out \
      -m com.acme.api,com.acme.service,com.acme.app
~~~

Khởi chạy module ứng dụng:

~~~bash
java --module-path out \
     -m com.acme.app/com.acme.app.Main
~~~

Khi `com.acme.app` là module chính được khởi chạy, nó là root của cấu hình ứng dụng. JVM giải quyết `com.acme.service` vì ứng dụng khai báo `requires com.acme.service`. Module service lại yêu cầu `com.acme.api`, do đó module API cũng được đưa vào graph.

Quan hệ đọc có ý nghĩa như sau:

- `com.acme.service` đọc `com.acme.api` vì có `requires transitive com.acme.api`.
- `com.acme.app` đọc `com.acme.service` vì có `requires com.acme.service`.
- `com.acme.app` cũng đọc `com.acme.api` vì dependency của service được khai báo `transitive`.

Nếu đổi directive trong module service thành `requires com.acme.api` thông thường, `com.acme.app` không tự động có quyền đọc `com.acme.api` chỉ vì nó đọc service. Nếu mã của ứng dụng cần import kiểu từ API module, ứng dụng nên khai báo dependency trực tiếp hoặc service phải công khai quan hệ phụ thuộc bằng `requires transitive` khi phù hợp với hợp đồng API.

Đọc module và truy cập package là hai bước khác nhau. Dù `com.acme.app` đọc được `com.acme.api`, ứng dụng chỉ truy cập được các kiểu public trong package đã được module API export cho ứng dụng theo quy tắc JPMS.

## 4. Cách JVM hình thành cấu hình runtime

Có thể xem quá trình giải quyết module theo các bước:

1. **Xác định nguồn module:** JVM lấy module từ module path, runtime image của JDK và các nguồn module khác được cấu hình.
2. **Chọn root modules:** module chính được khởi chạy và các root bổ sung được chọn bởi tùy chọn runtime.
3. **Theo dependency:** JVM đọc các directive `requires` của root và những module được kéo vào, rồi tìm module tương ứng.
4. **Giải quyết service khi được yêu cầu:** quá trình service binding có thể đưa các module cung cấp service phù hợp vào cấu hình.
5. **Tạo module layer:** các module đã giải quyết được định nghĩa trong layer để JVM nạp lớp và thực thi chương trình.

Nếu một dependency bắt buộc không thể tìm thấy hoặc graph có xung đột, quá trình giải quyết có thể thất bại trước khi lớp main được chạy. Ví dụ thường gặp là `FindException: Module ... not found`.

### Root module và module có thể quan sát

Module path là nơi JVM tìm module, không phải cam kết rằng mọi module trong đó đều được đưa vào graph. Root modules quyết định điểm bắt đầu của quá trình resolution. Với cách chạy `-m module/class`, module được chỉ định là module ứng dụng chính.

Tùy chọn `--add-modules` bổ sung root modules:

~~~bash
java --module-path mods \
     --add-modules com.acme.tools \
     -m com.acme.app/com.acme.app.Main
~~~

Trong ví dụ, `com.acme.tools` được yêu cầu làm root bổ sung ngay cả khi module ứng dụng không có dependency `requires` trực tiếp tới nó. Module vẫn phải tìm thấy được và graph phải hợp lệ.

Tùy chọn `--limit-modules` giới hạn tập module có thể quan sát trong quá trình resolution. Nó hữu ích khi muốn giới hạn cấu hình runtime, nhưng phải bảo đảm các dependency cần thiết vẫn nằm trong tập module được phép quan sát.

## 5. Descriptor và các tùy chọn runtime tác động khác nhau

Descriptor là metadata được đóng gói trong module. Một số tùy chọn JVM có thể điều chỉnh graph hoặc quyền truy cập trong một lần chạy mà không thay đổi descriptor đã biên dịch.

| Thành phần | Vai trò |
|---|---|
| `requires` | Khai báo dependency bắt buộc của module |
| `requires transitive` | Truyền khả năng đọc dependency tới module phụ thuộc vào module hiện tại |
| `requires static` | Dependency cần khi biên dịch nhưng có thể vắng mặt khi chạy |
| `--add-modules` | Thêm module làm root để giải quyết |
| `--limit-modules` | Giới hạn tập module có thể quan sát |
| `--add-reads` | Bổ sung quan hệ đọc module trong cấu hình runtime |
| `--add-exports` | Bổ sung quyền truy cập tới package export cho module đích |
| `--add-opens` | Mở package cho deep reflection ở runtime |
| `--bind-services` | Yêu cầu resolution thực hiện service binding để tìm các provider module phù hợp |

Ví dụ, trong giai đoạn chuyển đổi một ứng dụng cũ, có thể cấp quyền đọc từ named module tới unnamed module:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Tùy chọn này bổ sung quan hệ readability cho lần chạy đó. Nó không ghi ngược một directive mới vào `module-info.class`. Tương tự, `--add-exports` và `--add-opens` điều chỉnh quyền truy cập khi khởi chạy, nhưng không làm thay đổi descriptor trong JAR.

Nên xem các tùy chọn trên là cấu hình runtime có chủ đích, công cụ tương thích hoặc chẩn đoán. Nếu một quan hệ là yêu cầu ổn định của module, hãy thể hiện nó trong descriptor khi JPMS hỗ trợ directive tương ứng.

## 6. requires static và khác biệt giữa compile-time với runtime

`requires static` thường được dùng cho dependency hỗ trợ biên dịch, ví dụ annotation hoặc API chỉ cần ở một số chế độ chạy:

~~~java
module com.acme.domain {
    requires static com.acme.annotations;
    exports com.acme.domain.api;
}
~~~

Khi biên dịch, module `com.acme.annotations` phải có thể được tìm thấy để giải quyết kiểu và annotation mà mã nguồn sử dụng. Khi chạy, dependency static có thể không hiện diện. Nếu module đó có mặt trong cấu hình runtime, quan hệ đọc tương ứng vẫn được thiết lập theo quy tắc JPMS; nếu vắng mặt, chỉ riêng directive `requires static` không buộc runtime phải thất bại.

Điều này không có nghĩa mọi dependency đều có thể khai báo static. Nếu mã thực thi cần nạp lớp của dependency để chạy một chức năng, việc thiếu module hoặc lớp đó vẫn có thể dẫn đến lỗi khi đường thực thi được gọi. Hãy phân biệt dependency chỉ phục vụ biên dịch với dependency cần thiết cho hành vi runtime.

## 7. Service binding có thể làm graph runtime mở rộng

Descriptor hỗ trợ service bằng hai directive:

- `uses` khai báo module tiêu thụ một service.
- `provides ... with ...` khai báo module cung cấp implementation.

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

Việc provider có trên module path không đồng nghĩa nó luôn được đưa vào mọi graph. Khi resolution thực hiện service binding, các module cung cấp service được yêu cầu có thể được kéo vào cấu hình. Với Java launcher, tùy chọn `--bind-services` yêu cầu hành vi binding này:

~~~bash
java --module-path mods \
     --bind-services \
     -m com.acme.app/com.acme.app.Main
~~~

Khi dùng `ServiceLoader`, cần kiểm tra cả khai báo `uses`, `provides`, sự hiện diện của provider module và cách cấu hình runtime thực hiện service binding. Điều này giúp tránh giả định rằng chỉ cần chép JAR provider vào thư mục `mods` là implementation chắc chắn được khám phá.

## 8. Quan sát module graph ở runtime

JDK cung cấp các công cụ để xem module được giải quyết và kiểm tra cấu hình thực tế.

### Hiển thị quá trình resolution

Thêm `--show-module-resolution` vào lệnh chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

JVM sẽ in thông tin về các module được giải quyết và quan hệ phụ thuộc mà nó phát hiện. Đây là cách nhanh để xác định module nào được đưa vào cấu hình và dependency được tìm từ nguồn nào.

### Kiểm tra module bằng công cụ jar

Để xem descriptor được đóng gói trong một JAR:

~~~bash
jar --describe-module --file mods/com.acme.service.jar
~~~

Lệnh này mô tả module mà JAR khai báo. Nó giúp kiểm tra metadata tĩnh của JAR, nhưng không thay thế việc quan sát graph của một tiến trình chạy cụ thể.

### Quan sát boot layer từ Java code

Có thể xem các module trong boot layer bằng API:

~~~java
import java.util.Comparator;

public class ModuleGraphInspection {
    public static void main(String[] args) {
        ModuleLayer.boot()
            .modules()
            .stream()
            .map(Module::getName)
            .sorted(Comparator.naturalOrder())
            .forEach(System.out::println);
    }
}
~~~

`ModuleLayer.boot().modules()` trả về các module thuộc boot layer. Tập hợp này hữu ích để quan sát cấu hình layer ban đầu, nhưng không đại diện cho mọi module có thể quan sát trên module path và cũng không bao gồm các module chỉ được định nghĩa trong custom layer khác.

Có thể kiểm tra một quan hệ readability cụ thể:

~~~java
Module appModule = ModuleGraphInspection.class.getModule();
Module apiModule = ModuleLayer.boot()
    .findModule("com.acme.api")
    .orElseThrow();

System.out.println(appModule.canRead(apiModule));
~~~

Kết quả `true` cho biết module chứa lớp đang chạy có thể đọc module API trong cấu hình hiện tại. Nếu module API không thuộc boot layer, cần tìm trong layer tương ứng thay vì giả định nó nằm trong boot layer.

## 9. Lỗi thường gặp khi phân tích graph runtime

| Triệu chứng | Nguyên nhân có thể gặp | Hướng kiểm tra |
|---|---|---|
| `FindException: Module ... not found` | Dependency bắt buộc không có trong các nguồn module được quan sát | Kiểm tra module path, tên module và `requires` |
| Module nằm trong thư mục `mods` nhưng không xuất hiện trong graph | Module không phải root và không được kéo vào bởi dependency hoặc service binding | Kiểm tra root, `requires`, `--add-modules` và `--bind-services` |
| Ứng dụng không đọc được một module dù JAR đã có | Module chưa được giải quyết vào cấu hình hoặc thiếu quan hệ readability | Kiểm tra graph, `requires` và `--add-reads` |
| Đọc được module nhưng không truy cập được kiểu | Package chưa được export cho module sử dụng | Kiểm tra `exports` hoặc `--add-exports` |
| Framework bị chặn khi reflection | Package chưa được mở cho deep reflection | Kiểm tra `opens` hoặc `--add-opens` |
| Biên dịch thành công nhưng runtime thiếu lớp | Dependency chỉ có ở compile-time hoặc thiếu module/lớp lúc chạy | Phân biệt `requires static` với dependency runtime thực sự cần |
| Provider service không được tìm thấy | Thiếu `uses`/`provides`, provider không quan sát được hoặc service binding chưa được thực hiện | Kiểm tra descriptor và `--bind-services` |

## 10. Quy trình chẩn đoán thực tế

Khi một ứng dụng module hóa chạy khác với dự kiến, hãy lần lượt kiểm tra:

1. **Đọc descriptor:** chạy `jar --describe-module` trên JAR của ứng dụng và các thư viện liên quan để xác nhận tên module, `requires`, `exports`, `opens`, `uses` và `provides`.
2. **Kiểm tra nguồn module:** xác nhận module path trỏ tới đúng thư mục/JAR và module bắt buộc có thể được quan sát.
3. **Kiểm tra root modules:** xác định module nào được khởi chạy và các root bổ sung qua `--add-modules`.
4. **Quan sát resolution:** chạy với `--show-module-resolution` để xem graph thực tế.
5. **Kiểm tra readability và export:** phân biệt lỗi không đọc được module với lỗi package chưa export.
6. **Kiểm tra service binding:** nếu dùng ServiceLoader, xác nhận provider được tìm thấy và binding được bật khi cấu hình cần nó.
7. **Đối chiếu runtime options:** kiểm tra các tùy chọn `--add-reads`, `--add-exports`, `--add-opens` hoặc `--limit-modules` có làm thay đổi cấu hình mong muốn không.

Không nên chỉ nhìn vào nội dung thư mục module path để kết luận một module đang hoạt động trong tiến trình. Cần xem cấu hình được giải quyết và layer thực tế.

## 11. Ghi nhớ

Module descriptor là **mô tả tĩnh** được biên dịch và đóng gói cùng module. Nó khai báo module muốn phụ thuộc vào đâu, công khai package nào và tham gia service như thế nào. Module graph runtime là **cấu hình thực tế** mà JVM tạo ra từ các descriptor, nguồn module có thể quan sát, root modules và tùy chọn khởi chạy.

Descriptor định hình những quan hệ mà module yêu cầu; runtime resolution quyết định module nào thực sự tham gia cấu hình của lần chạy. Khi cần tìm hiểu một module vì sao có hoặc không có trong tiến trình, hãy kiểm tra root modules, dependency graph, service binding và output của `--show-module-resolution` thay vì chỉ đọc riêng `module-info.java`.
