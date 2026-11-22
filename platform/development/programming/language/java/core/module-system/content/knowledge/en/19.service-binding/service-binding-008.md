# Kiểm tra provider bị thiếu sau khi đóng gói

## 1. Vì sao provider có thể biến mất sau khi đóng gói?

Java Service Provider Interface (SPI) cho phép một module hoặc ứng dụng sử dụng một service mà không phụ thuộc trực tiếp vào implementation cụ thể. Với Java Platform Module System (JPMS), service consumer khai báo \`uses\`, còn module cung cấp implementation khai báo \`provides ... with ...\` trong \`module-info.java\`.

Một chương trình có thể chạy đúng trong IDE nhưng không tìm thấy provider sau khi đóng gói vì môi trường chạy đã thay đổi: module path trở thành classpath, file \`module-info.class\` không còn trong JAR cuối, resource \`META-INF/services\` bị loại bỏ khi tạo fat JAR, provider module không được đưa vào runtime image, hoặc class provider không thể khởi tạo.

Khi điều tra, hãy tách ba giai đoạn:

1. **Khai báo và đóng gói:** artifact cuối có metadata hoặc service configuration cần thiết không?
2. **Khám phá provider:** \`ServiceLoader\` có nhìn thấy provider trong module layer hoặc class loader đang dùng không?
3. **Khởi tạo provider:** provider đã được tìm thấy nhưng có lỗi khi nạp class, gọi constructor hoặc gọi provider method không?

Thông báo “không có provider” và \`ServiceConfigurationError\` thường chỉ ra hai giai đoạn khác nhau. Đừng vội sửa dependency trước khi xác định provider mất ở giai đoạn nào.

## 2. Xác định ứng dụng đang chạy theo JPMS hay classpath

Đây là bước đầu tiên vì hai cơ chế đăng ký provider khác nhau.

- **Named module trên module path:** metadata \`provides\` trong \`module-info.class\` đăng ký provider. Consumer phải khai báo \`uses\`.
- **Ứng dụng trên classpath:** \`ServiceLoader\` tìm file cấu hình \`META-INF/services/<tên-đầy-đủ-của-service>\`. File chứa tên đầy đủ của từng implementation, mỗi tên trên một dòng.
- **Modular JAR được đặt trên classpath:** JVM xử lý JAR đó như JAR thông thường; \`module-info.class\` không được dùng để tạo module. Nếu cần discovery theo classpath, artifact phải có \`META-INF/services\`.

Ví dụ, một ứng dụng được khởi chạy bằng:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

đang chạy theo module path. Nếu chuyển sang:

~~~bash
java -cp "app.jar:provider.jar:spi.jar" com.acme.app.Main
~~~

thì các JAR được xử lý trên classpath. Trên Windows, dấu phân cách classpath là dấu chấm phẩy (\`;\`) thay vì dấu hai chấm (\`:\`).

Không suy luận chế độ chạy chỉ từ việc file có đuôi \`.jar\`. Hãy xem chính xác lệnh khởi chạy hoặc cấu hình container/service đang chạy trong môi trường triển khai.

## 3. Đăng ký provider đúng trong module-info.java

Giả sử ứng dụng có ba module:

- \`com.acme.spi\` chứa interface service.
- \`com.acme.json\` cung cấp implementation.
- \`com.acme.app\` sử dụng service.

### 3.1. Module chứa service

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Interface service:

~~~java
package com.acme.spi;

public interface Formatter {
    String format(String value);
}
~~~

Package chứa service phải được export để các module consumer và provider có thể tham chiếu kiểu \`Formatter\`.

### 3.2. Module provider

~~~java
module com.acme.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
            with com.acme.json.JsonFormatter;
}
~~~

Implementation:

~~~java
package com.acme.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String value) {
        return "\"" + value + "\"";
    }
}
~~~

Module provider phải đọc được module chứa service, vì vậy nó khai báo \`requires com.acme.spi\`. Chỉ thị \`provides\` phải dùng đúng tên service và tên lớp provider đầy đủ.

Với provider class thông thường, lớp phải là public và có public constructor không tham số. JPMS cũng hỗ trợ provider method: lớp provider public có thể khai báo phương thức \`public static\` tên chính xác là \`provider\`, không nhận tham số và trả về kiểu tương thích với service. Khi dùng provider method, lớp khai báo phương thức không bắt buộc phải trực tiếp implement interface service.

Package implementation không cần export chỉ để \`ServiceLoader\` sử dụng provider đã khai báo bằng \`provides\`. Chỉ export package đó nếu ứng dụng cần truy cập public API của implementation trực tiếp.

### 3.3. Module consumer

~~~java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
~~~

Consumer phải khai báo \`uses\` cho service mà nó nạp bằng \`ServiceLoader\`. Nếu thiếu chỉ thị này, lời gọi \`ServiceLoader\` từ named module có thể thất bại với \`ServiceConfigurationError\`, dù provider JAR đã có mặt.

Mã sử dụng service:

~~~java
package com.acme.app;

import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loader =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loader) {
            System.out.println(formatter.getClass().getName());
            System.out.println(formatter.format("hello"));
        }
    }
}
~~~

Nếu vòng lặp không chạy lần nào, loader không tìm thấy provider phù hợp trong phạm vi discovery đang dùng. Nếu vòng lặp ném \`ServiceConfigurationError\`, hãy đọc nguyên nhân gốc: class không tồn tại, không tương thích kiểu, constructor/provider method sai hoặc lỗi khởi tạo.

## 4. Kiểm tra artifact sau khi build

Hãy kiểm tra chính JAR đã được triển khai, không chỉ thư mục output trong IDE hoặc build directory trước bước đóng gói cuối.

### 4.1. Kiểm tra descriptor của modular JAR

Dùng lệnh:

~~~bash
jar --describe-module --file mods/com.acme.json.jar
~~~

Descriptor của provider phải thể hiện module name và chỉ thị \`provides\`, ví dụ:

~~~text
com.acme.json
requires com.acme.spi
provides com.acme.spi.Formatter with com.acme.json.JsonFormatter
~~~

Kiểm tra consumer:

~~~bash
jar --describe-module --file mods/com.acme.app.jar
~~~

Kết quả cần có \`uses com.acme.spi.Formatter\` và dependency tới module chứa service.

Nếu \`jar --describe-module\` báo không có module descriptor và suy ra automatic module, artifact cuối không còn descriptor tường minh như mong đợi. Kiểm tra cấu hình đóng gói để chắc chắn \`module-info.class\` được giữ lại và JAR đang được đặt trên module path.

### 4.2. Kiểm tra class và file trong JAR

Liệt kê nội dung provider JAR:

~~~bash
jar --list --file mods/com.acme.json.jar
~~~

Xác nhận có:

- \`module-info.class\` ở gốc JAR đối với modular JAR.
- File class của provider, ví dụ \`com/acme/json/JsonFormatter.class\`.
- Các class phụ thuộc cần thiết để khởi tạo provider.

Với ứng dụng classpath, kiểm tra file service configuration:

~~~bash
jar --list --file provider.jar
~~~

Artifact phải chứa resource có đường dẫn chính xác:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

Nội dung file:

~~~text
com.acme.json.JsonFormatter
~~~

Tên service trong đường dẫn và tên implementation trong nội dung phải là tên đầy đủ, phân biệt chữ hoa/chữ thường. Nếu có nhiều provider, mỗi provider được ghi trên một dòng.

### 4.3. Kiểm tra fat JAR và shaded JAR

Một lỗi phổ biến là nhiều dependency cùng chứa resource \`META-INF/services\`, nhưng bước tạo fat JAR chỉ giữ lại resource của một dependency hoặc ghi đè file trước đó. Khi đó provider có thể hoạt động trong IDE nhưng biến mất trong JAR hợp nhất.

Cấu hình đóng gói phải **merge** các file service configuration cùng đường dẫn, giữ lại tất cả provider hợp lệ và loại bỏ dòng trùng nếu công cụ hỗ trợ. Ví dụ:

- Gradle Shadow Plugin có thao tác \`mergeServiceFiles()\`.
- Maven Shade Plugin có transformer \`ServicesResourceTransformer\`.

Sau khi thay đổi cấu hình, hãy kiểm tra lại resource trong artifact cuối bằng \`jar --list\` và đọc nội dung file service configuration đã được đóng gói. Chỉ thấy một dependency provider trong cây dependency không chứng minh resource đăng ký provider đã có trong JAR.

## 5. Kiểm tra module có được resolve lúc khởi chạy không

Khi chạy ứng dụng modular, module provider phải được tìm thấy trên module path và được đưa vào module layer đang dùng.

Chạy với tùy chọn hiển thị quá trình phân giải:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Đọc output để xác nhận:

- Module consumer được resolve.
- Module chứa service được resolve.
- Module provider xuất hiện trong kết quả service binding.
- Không có lỗi module thiếu, module trùng tên hoặc dependency không thể resolve.

JPMS có cơ chế service binding: trong quá trình resolve, provider module quan sát được trên module path có thể được bổ sung khi module đã resolve khai báo \`uses\` service tương ứng. Vì vậy, việc consumer có \`uses\` và provider có \`provides\` là hai phần của cùng một cấu hình.

Để chẩn đoán, có thể yêu cầu launcher đưa toàn bộ module trên module path vào tập root:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules ALL-MODULE-PATH \
     --module com.acme.app/com.acme.app.Main
~~~

Nếu provider chỉ xuất hiện khi dùng \`--add-modules ALL-MODULE-PATH\`, hãy kiểm tra lại service binding và descriptor của consumer/provider. Đây là cách khoanh vùng nguyên nhân; không nhất thiết phải giữ tùy chọn này trong lệnh production.

Có thể kiểm tra tính hợp lệ của các module trên module path bằng:

~~~bash
java --validate-modules --module-path mods
~~~

Lệnh này giúp phát hiện một số vấn đề về cấu trúc và dependency module trước khi chạy ứng dụng.

## 6. Trường hợp dùng jlink hoặc custom ModuleLayer

### 6.1. Runtime image được tạo bằng jlink

Nếu ứng dụng được đóng gói thành runtime image, provider module phải tồn tại trong image cuối. Chỉ có JAR trên máy build không có nghĩa module đó đã được đưa vào image.

Khi cần liên kết các service provider và dependency của chúng vào image, dùng tùy chọn \`--bind-services\`:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.app \
  --bind-services \
  --output runtime-image
~~~

Sau khi tạo image, kiểm tra danh sách module:

~~~bash
runtime-image/bin/java --list-modules
~~~

Trên Windows, dùng \`runtime-image\\bin\\java.exe --list-modules\` và điều chỉnh dấu phân cách module path theo hệ điều hành. Xác nhận module provider có trong image. Nếu không dùng \`--bind-services\`, hãy chủ động đưa module provider vào tập module được liên kết khi kiến trúc ứng dụng yêu cầu.

### 6.2. Provider được nạp trong ModuleLayer riêng

Plugin có thể được nạp vào một \`ModuleLayer\` do ứng dụng tạo. Khi đó, tìm provider trong boot layer không đồng nghĩa với tìm provider trong layer plugin.

Dùng overload nhận layer:

~~~java
ModuleLayer pluginLayer = /* layer đã tạo cho plugin */;
ServiceLoader<Formatter> loader =
        ServiceLoader.load(pluginLayer, Formatter.class);

for (Formatter formatter : loader) {
    System.out.println(formatter.format("hello"));
}
~~~

Đảm bảo module chứa service API được chia sẻ đúng giữa ứng dụng và plugin layer. Nếu mỗi layer hoặc class loader nạp một bản sao khác nhau của interface service, hai kiểu có cùng tên đầy đủ vẫn có thể là hai kiểu Java khác nhau và provider không tương thích với \`Class\` service mà consumer truyền vào.

## 7. Chương trình kiểm tra descriptor và provider lúc runtime

Có thể viết một tiện ích nhỏ để liệt kê các chỉ thị provider mà \`ModuleFinder\` đọc được từ module path:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectServiceDeclarations {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        for (ModuleReference reference : finder.findAll()) {
            ModuleDescriptor descriptor = reference.descriptor();

            descriptor.provides().forEach(provides -> {
                System.out.printf(
                        "%s provides %s with %s%n",
                        descriptor.name(),
                        provides.service(),
                        provides.providers());
            });

            descriptor.uses().forEach(service -> {
                System.out.printf(
                        "%s uses %s%n",
                        descriptor.name(),
                        service);
            });
        }
    }
}
~~~

Tiện ích này đọc metadata của module tìm thấy trên module path, không khởi tạo provider. Nó trả lời câu hỏi “JAR có khai báo provider không?”, nhưng chưa chứng minh provider có thể được khởi tạo trong runtime thực tế.

Để kiểm tra discovery và khởi tạo, chạy đoạn code \`ServiceLoader\` trong chính ứng dụng với cùng module path, module layer và class loader như môi trường production. Nếu cần ghi nhận lỗi rõ ràng:

~~~java
try {
    for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
        System.out.println("Loaded: " + formatter.getClass().getName());
    }
} catch (java.util.ServiceConfigurationError error) {
    error.printStackTrace();
}
~~~

Không nuốt \`ServiceConfigurationError\` rồi trả về danh sách rỗng; thông tin lỗi thường chỉ ra provider class hoặc cấu hình nào đang hỏng.

## 8. Các nguyên nhân thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Không có provider trên module path | Consumer thiếu \`uses\` hoặc provider thiếu \`provides\` | Dùng \`jar --describe-module\` kiểm tra cả hai descriptor. |
| Provider JAR không xuất hiện khi resolve | JAR không nằm trên module path hoặc provider module không được resolve | Kiểm tra lệnh launch, \`--show-module-resolution\` và thử \`--add-modules ALL-MODULE-PATH\` để khoanh vùng. |
| Chạy trong IDE được nhưng fat JAR không thấy provider | Resource \`META-INF/services\` bị ghi đè hoặc bỏ khi merge | Kiểm tra resource trong JAR cuối; cấu hình merge service files cho plugin đóng gói. |
| Chạy bằng \`-m\` được nhưng chạy bằng \`-cp\` mất provider | \`module-info.class\` không được áp dụng trên classpath | Bổ sung \`META-INF/services\` cho cách chạy classpath hoặc giữ lệnh chạy trên module path. |
| \`ServiceConfigurationError\`: provider không tìm thấy class | Class provider không có trong artifact hoặc tên lớp sai | Kiểm tra \`jar --list\`, tên package và class được đóng gói. |
| \`ServiceConfigurationError\`: provider không phải subtype | Provider implement một bản sao khác của service API hoặc khai báo sai kiểu | Dùng chung một module/JAR API; loại bản sao SPI trùng khỏi fat JAR và classpath. |
| Provider được tìm thấy nhưng khởi tạo thất bại | Thiếu public no-arg constructor, provider method sai chữ ký hoặc dependency runtime bị thiếu | Kiểm tra constructor/provider method và đọc nguyên nhân gốc trong stack trace. |
| Provider hoạt động ở boot layer nhưng mất trong plugin | Đang tìm provider ở sai ModuleLayer | Gọi \`ServiceLoader.load(pluginLayer, Service.class)\` với layer chứa provider. |
| Provider có trên máy build nhưng mất trong runtime image | jlink không liên kết module provider | Kiểm tra \`java --list-modules\` trong image; cân nhắc \`jlink --bind-services\`. |

Ngoài các nguyên nhân trên, hãy kiểm tra tên service có thống nhất tuyệt đối giữa consumer và provider hay không. Tên module, tên package, tên service và tên provider là các giá trị khác nhau; không dùng tên file JAR thay cho tên module hoặc tên class.

## 9. Quy trình điều tra ngắn gọn

Khi lỗi chỉ xuất hiện sau khi đóng gói, thực hiện lần lượt:

1. Ghi lại chính xác lệnh khởi chạy và xác định đang dùng module path hay classpath.
2. Chạy \`jar --describe-module\` trên provider JAR và consumer JAR nếu dùng JPMS.
3. Chạy \`jar --list\` trên artifact cuối để xác nhận provider class, \`module-info.class\` hoặc \`META-INF/services\` thực sự có mặt.
4. Dùng \`--show-module-resolution\` để xem provider module có được resolve hay không.
5. Chạy \`ServiceLoader\` trong đúng runtime production và ghi nhận \`ServiceConfigurationError\` đầy đủ nếu có.
6. Nếu ứng dụng dùng jlink hoặc plugin layer, kiểm tra module provider đã nằm trong runtime image/layer và dùng đúng overload của \`ServiceLoader\`.

Kết quả của mỗi bước giúp khoanh vùng chính xác: khai báo bị mất, resource/class không được đóng gói, module không được resolve, loader đang tìm ở sai phạm vi hay provider không thể khởi tạo. Sửa đúng tầng gây lỗi rồi kiểm tra lại artifact cuối bằng cùng lệnh triển khai thực tế.
