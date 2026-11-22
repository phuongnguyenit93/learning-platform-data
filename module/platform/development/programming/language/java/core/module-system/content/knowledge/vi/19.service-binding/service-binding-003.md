# Root service consumer ảnh hưởng graph trong JPMS

Trong Java Platform Module System (JPMS), một module có thể sử dụng service mà không khai báo dependency trực tiếp vào từng implementation. Module tiêu thụ khai báo `uses`, module cung cấp khai báo `provides ... with ...`. Cơ chế **service binding** dùng những khai báo đó để mở rộng tập module được resolve: khi một module trong graph cần một service, các module provider phù hợp có thể được đưa vào configuration cùng dependency của chúng.

Điểm khởi đầu của quá trình này là **root modules**. Vì vậy, nếu một root module là service consumer, các service mà nó khai báo có thể làm graph lớn hơn. Cần hiểu rõ quan hệ giữa root, `requires`, `uses`, `provides` và tùy chọn `--bind-services` để dự đoán chính xác module nào sẽ có mặt trong runtime image.

## 1. Bốn khái niệm cần phân biệt

- **Root module**: module được chọn làm điểm bắt đầu khi resolve. Với `jlink`, root thường được chỉ định bằng `--add-modules`.
- **Service consumer**: module cần một abstraction/service và khai báo `uses ten.day.du.ServiceType` trong `module-info.java`.
- **Service provider**: module triển khai service và khai báo `provides ten.day.du.ServiceType with ten.day.du.ProviderClass`.
- **Service binding**: bước resolve bổ sung các module provider có thể quan sát được cho những service được các module trong graph sử dụng, sau đó resolve dependency của các provider đó.

Ví dụ, ứng dụng `com.acme.app` gọi service `Codec`. Ứng dụng chỉ phụ thuộc vào API `com.acme.codec.api`; nó không cần biết implementation JSON nằm trong module `com.acme.codec.json`.

~~~text
Root: com.acme.app
    |
    +-- requires --> com.acme.codec.api
    |
    +-- uses Codec
             |
             +-- service binding tìm thấy provider
                         |
                         +--> com.acme.codec.json
                                  |
                                  +-- requires --> com.acme.codec.api
~~~

Quan hệ `requires` và quan hệ service binding có ý nghĩa khác nhau. `requires` tạo readability dependency theo quy tắc JPMS. `uses` ghi nhận nhu cầu service để quá trình binding tìm provider; nó không có nghĩa consumer phải `requires` từng module provider, cũng không tự làm package implementation được export cho consumer.

## 2. Khai báo service consumer và provider

Giả sử dự án có ba module:

1. `com.acme.codec.api` chứa interface service.
2. `com.acme.codec.json` cung cấp implementation JSON.
3. `com.acme.app` sử dụng service.

### Module API

Cấu trúc:

~~~text
modules/
└── com.acme.codec.api/
    ├── module-info.java
    └── com/acme/codec/spi/Codec.java
~~~

`module-info.java`:

~~~java
module com.acme.codec.api {
    exports com.acme.codec.spi;
}
~~~

Interface service:

~~~java
package com.acme.codec.spi;

public interface Codec {
    String name();
    byte[] encode(String value);
}
~~~

Module API export package chứa interface để consumer và provider có thể đọc và triển khai kiểu service.

### Module provider

`module-info.java` của provider:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Implementation:

~~~java
package com.acme.codec.json;

import com.acme.codec.spi.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String name() {
        return "json";
    }

    @Override
    public byte[] encode(String value) {
        return ("\"" + value + "\"").getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Provider module cần đọc module API để tham chiếu interface. Package implementation không cần export chỉ để ServiceLoader tìm provider được khai báo trong descriptor. Với cách triển khai thông thường ở ví dụ này, provider class là public và có public no-argument constructor.

### Module consumer

`module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.codec.api;

    uses com.acme.codec.spi.Codec;
}
~~~

Mã sử dụng:

~~~java
package com.acme.app;

import com.acme.codec.spi.Codec;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader.load(Codec.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .forEach(codec -> System.out.println(codec.name()));
    }
}
~~~

Consumer chỉ phụ thuộc vào module API. Nó không khai báo `requires com.acme.codec.json`. Chính metadata `uses` và `provides` cho phép quá trình service binding tìm provider phù hợp.

## 3. Root module làm thay đổi graph như thế nào?

Quá trình resolve bắt đầu từ một tập root. Từ các root, JPMS tìm dependency được khai báo bằng `requires` và tiếp tục mở rộng graph theo các quy tắc resolve. Khi thực hiện service binding, hệ thống xét các service được khai báo bởi những module đã nằm trong graph, tìm các provider module có thể quan sát được, thêm chúng vào configuration và resolve dependency của chúng.

Với ví dụ trên, nếu `com.acme.app` là root:

1. `com.acme.app` được đưa vào graph.
2. Dependency `com.acme.codec.api` được resolve qua `requires`.
3. Consumer khai báo `uses com.acme.codec.spi.Codec`.
4. Service binding tìm module quan sát được khai báo `provides com.acme.codec.spi.Codec`.
5. `com.acme.codec.json` được thêm vào graph.
6. Dependency của provider, bao gồm `com.acme.codec.api`, được resolve.
7. Nếu provider module lại khai báo `uses` một service khác, quá trình binding có thể tiếp tục mở rộng graph.

Điều này tạo ra hiệu ứng dây chuyền. Một root service consumer có thể kéo theo provider, dependency của provider và provider của các service tiếp theo. Quá trình lặp lại cho đến khi không còn provider phù hợp nào cần được thêm.

Cần nhớ ba trường hợp:

- **Consumer nằm trong graph**: service mà module đó khai báo có thể kích hoạt việc tìm provider.
- **Consumer không nằm trong graph**: các chỉ thị `uses` của module đó không làm graph hiện tại phát sinh provider.
- **Provider được chỉ định làm root hoặc được yêu cầu trực tiếp**: provider được resolve do root/`requires`, ngay cả khi không có service binding.

Do đó, một provider có thể xuất hiện trong graph vì nhiều lý do: được chọn làm root, là dependency qua `requires`, hoặc được thêm qua service binding. Khi phân tích graph, hãy xác định đường đi khiến module xuất hiện thay vì chỉ nhìn thấy tên module trong kết quả cuối.

## 4. Service binding trong jlink

`jlink` tạo runtime image từ một tập module đã resolve. Tùy chọn `--add-modules` xác định các root module. Tùy chọn `--bind-services` yêu cầu công cụ liên kết các service provider module và dependency của chúng.

Ví dụ tạo runtime image cho ứng dụng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output runtime-app
~~~

Trong đó:

- `$JAVA_HOME/jmods` chứa JMOD của JDK đang dùng.
- `mods` chứa các module ứng dụng đã biên dịch, chẳng hạn modular JAR hoặc exploded module.
- `--add-modules com.acme.app` chọn consumer làm root.
- `--bind-services` cho phép provider của service mà graph sử dụng được thêm cùng dependency của provider.
- `--output runtime-app` là thư mục runtime image được tạo.

Với ba module ví dụ, graph liên kết có thể bao gồm:

~~~text
com.acme.app
com.acme.codec.api
com.acme.codec.json
java.base
...
~~~

Các module nền tảng khác sẽ phụ thuộc vào dependency thực tế của ứng dụng và provider.

### So sánh khi bỏ --bind-services

Nếu chạy:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-app
~~~

`jlink` vẫn resolve root và dependency theo `requires`. Nhưng provider không tự động được đưa vào chỉ vì consumer có `uses`. Nếu provider không phải root và cũng không được yêu cầu qua dependency thông thường, provider có thể vắng mặt trong image.

Khi ứng dụng gọi `ServiceLoader.load(Codec.class)`, không có provider trong runtime image thì ServiceLoader không thể tìm thấy implementation đó. Vì vậy, nếu ứng dụng dựa vào provider được phát hiện qua service binding, hãy xác nhận provider đã được đưa vào image.

Một cách khác là chỉ định provider như root:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app,com.acme.codec.json --output runtime-app
~~~

Lúc này provider được đưa vào do được chọn rõ ràng, không cần service binding để thêm chính provider đó. Tuy nhiên cách này buộc cấu hình triển khai phải biết tên implementation. Service binding phù hợp hơn khi muốn giữ consumer phụ thuộc vào API và để metadata provider quyết định implementation nào có thể tham gia.

## 5. Provider nào có thể được thêm vào?

Service binding chỉ có thể chọn provider mà công cụ resolve có thể quan sát được. Một module có khai báo `provides` nhưng nằm ngoài các module finder hoặc ngoài phạm vi module được phép quan sát thì không thể được thêm vào graph.

Các yếu tố cần kiểm tra:

- **Module path**: thư mục chứa modular JAR hoặc exploded module provider phải có trong `--module-path`.
- **Module descriptor**: provider phải khai báo đúng service type trong `provides`.
- **Service type**: consumer và provider phải tham chiếu cùng tên service type, đúng package và module API.
- **Root set**: phải có ít nhất một module trong graph khai báo `uses` service đó, trừ khi provider được đưa vào vì root hoặc dependency khác.
- **Module universe**: các giới hạn như `--limit-modules` có thể làm module provider không còn nằm trong tập module được phép resolve.
- **Dependency của provider**: các module cần thiết bởi `requires` trong provider cũng phải resolve được.

Nếu có nhiều module cùng cung cấp một service, service binding có thể thêm nhiều provider phù hợp vào graph. Cơ chế này không chọn một implementation duy nhất thay cho ứng dụng. Nếu nghiệp vụ cần ưu tiên provider cụ thể, hãy thiết kế chính sách chọn provider trong ứng dụng hoặc cấu hình tập module triển khai rõ ràng; đừng dựa vào thứ tự tình cờ của module.

## 6. Quan sát graph bằng công cụ JDK

Trước tiên, có thể yêu cầu jlink gợi ý provider cho một service type:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --suggest-providers com.acme.codec.spi.Codec
~~~

Lệnh này giúp kiểm tra các module trên module path có provider cho service được hỏi hay không. Nó là bước khảo sát; việc gợi ý không đồng nghĩa provider đã được đưa vào runtime image.

Sau khi tạo image, liệt kê module có trong runtime:

~~~bash
runtime-app/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
runtime-app/bin/java.exe --list-modules
~~~

Tìm module provider trong danh sách để xác nhận image có chứa nó. Có thể chạy ứng dụng bằng runtime image mới:

~~~bash
runtime-app/bin/java -m com.acme.app
~~~

Nếu cần xem module resolution khi khởi chạy một ứng dụng module path trong một runtime có sẵn các module tương ứng, dùng:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app
~~~

Đầu ra giúp quan sát root và dependency được resolve. Để kết luận một provider được thêm do service binding hay do `requires`, vẫn cần đối chiếu descriptor của consumer/provider và cách tạo runtime image.

## 7. So sánh resolve() và resolveAndBind() bằng Java API

Java API trong `java.lang.module` cho phép tạo configuration từ root module. Điểm khác biệt chính là `resolveAndBind()` thực hiện thêm bước service binding.

Ví dụ:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Set;

public class CompareResolution {
    public static void main(String[] args) {
        ModuleFinder applicationModules =
            ModuleFinder.of(Path.of("mods"));

        Configuration parent =
            ModuleLayer.boot().configuration();

        Set<String> roots = Set.of("com.acme.app");

        Configuration withoutBinding = parent.resolve(
            ModuleFinder.of(),
            applicationModules,
            roots
        );

        Configuration withBinding = parent.resolveAndBind(
            ModuleFinder.of(),
            applicationModules,
            roots
        );

        print("resolve()", withoutBinding);
        print("resolveAndBind()", withBinding);
    }

    private static void print(
            String label,
            Configuration configuration) {
        System.out.println("\n" + label);

        configuration.modules().stream()
            .map(ResolvedModule::name)
            .sorted(Comparator.naturalOrder())
            .forEach(System.out::println);
    }
}
~~~

Chạy chương trình từ một classpath phù hợp, với thư mục `mods` chứa các module ví dụ. Kết quả phụ thuộc module thực tế có trong module finder:

- `resolve()` resolve root và dependency theo `requires`.
- `resolveAndBind()` thực hiện resolve cùng service binding, vì vậy có thể xuất hiện thêm `com.acme.codec.json` và dependency của provider.

`configuration.modules()` trả về các module trong configuration vừa tạo; các module thuộc parent configuration không được liệt kê như module mới của configuration con. Đây là lý do danh sách in ra có thể không chứa toàn bộ module nền tảng đang chạy trong boot layer.

Hai phương thức không thay đổi file JAR hoặc descriptor. Chúng tạo kết quả resolve trong bộ nhớ để ứng dụng có thể xây dựng hoặc kiểm tra `ModuleLayer`.

## 8. Các lỗi thường gặp

**Consumer có `uses` nhưng provider không xuất hiện.** Kiểm tra bạn đang dùng `jlink --bind-services` hay chưa; provider có nằm trong module path không; descriptor có khai báo đúng service type không; và module consumer có thực sự nằm trong graph không.

**Đã dùng `--bind-services` nhưng vẫn không tìm thấy provider.** `--bind-services` không tự tìm module ở mọi thư mục trên máy. Kiểm tra module path, tên module và phạm vi module được phép quan sát. Kiểm tra thêm provider có được đóng gói thành modular JAR hoặc exploded module hợp lệ hay không.

**Provider xuất hiện dù không được dùng trực tiếp.** Provider có thể là root, là dependency của module khác hoặc được thêm bởi một consumer khác trong graph. Tìm tất cả root, các chỉ thị `requires`, `uses` và `provides` trước khi kết luận.

**Runtime image lớn hơn dự kiến.** Service binding có thể thêm nhiều provider cho cùng service, dependency của các provider và provider của service tiếp theo. Kiểm tra module nào đang khai báo `uses`, thu hẹp root set và module path, sau đó so sánh danh sách module trước/sau khi bật binding.

**Ứng dụng tìm thấy nhiều provider.** Đây là kết quả hợp lệ nếu nhiều module cùng cung cấp service. Dùng thuộc tính hoặc chính sách chọn provider ở tầng ứng dụng nếu chỉ một implementation được phép sử dụng.

**Nhầm `uses` với `requires`.** `uses` không tạo dependency compile-time vào implementation. Consumer cần `requires` module chứa service API; provider cần `requires` module API và khai báo `provides`. Service binding là cơ chế resolve provider vào configuration.

## 9. Thực hành

1. Tạo ba module `com.acme.codec.api`, `com.acme.codec.json` và `com.acme.app` theo ví dụ.
2. Đóng gói các module thành modular JAR hoặc chuẩn bị exploded module trong thư mục `mods`.
3. Chạy `jlink` với root `com.acme.app` và bật `--bind-services`. Dùng `java --list-modules` của runtime mới để xác nhận provider có trong image.
4. Tạo image thứ hai nhưng bỏ `--bind-services`. So sánh danh sách module và kết quả gọi `ServiceLoader`.
5. Tạo image thứ ba bằng cách thêm provider trực tiếp vào `--add-modules`. So sánh vì sao provider xuất hiện trong graph ở trường hợp này.
6. Dùng `--suggest-providers` để khảo sát provider có sẵn trên module path.
7. Chạy ví dụ `CompareResolution` để so sánh tập module giữa `resolve()` và `resolveAndBind()`.

Khi phân tích một graph có service binding, hãy bắt đầu từ root modules, theo các cạnh `requires`, rồi xét những service được các module trong graph khai báo bằng `uses`. Provider chỉ có thể được thêm nếu nằm trong tập module quan sát được. Với `jlink`, `--bind-services` biến các quan hệ service đó thành module được liên kết vào runtime image, vì vậy một root service consumer có thể quyết định đáng kể kích thước và thành phần của runtime được tạo.
