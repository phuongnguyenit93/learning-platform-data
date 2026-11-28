# ServiceLoader, service provider và nhu cầu bind service trong runtime

## 1. Service và service provider giải quyết vấn đề gì?

Trong một ứng dụng có thể có nhiều implementation cho cùng một chức năng: nhiều bộ mã hóa, driver cơ sở dữ liệu, bộ chuyển đổi tài liệu hoặc nhà cung cấp bảo mật. Nếu lớp ứng dụng gọi trực tiếp từng implementation, mã ứng dụng sẽ phụ thuộc vào tên lớp cụ thể và phải thay đổi khi thêm hoặc thay provider.

Java cung cấp cơ chế Service Provider Interface (SPI) để tách hợp đồng khỏi implementation:

- **Service:** một interface hoặc lớp trừu tượng mô tả khả năng mà ứng dụng cần.
- **Service provider:** implementation cung cấp khả năng đó.
- **ServiceLoader:** API tìm và nạp provider ở runtime.

Ứng dụng chỉ tham chiếu service contract. Provider có thể được triển khai trong named module hoặc được đóng gói thành JAR trên classpath. Cơ chế này hữu ích cho plugin, driver và kiến trúc mở rộng.

`ServiceLoader` là API ổn định từ các phiên bản Java cũ. Từ Java 9, JPMS bổ sung cách khai báo service và provider trong module descriptor bằng `uses` và `provides`. `jlink --bind-services` dùng thông tin service trong module graph để liên kết provider module vào runtime image.

## 2. Khai báo service contract

Ví dụ một ứng dụng cần các bộ tạo codec. Service contract có thể là:

~~~java
package com.example.codec.api;

public interface CodecFactory {
    String format();
    byte[] encode(byte[] input);
}
~~~

Interface này thuộc module API riêng:

~~~java
module com.example.codec.api {
    exports com.example.codec.api;
}
~~~

Module export package API để module ứng dụng và provider có thể tham chiếu kiểu `CodecFactory`. Interface không cần biết provider nằm ở đâu hoặc có bao nhiêu implementation.

## 3. Khai báo provider trong module descriptor

Một provider dạng module khai báo service mà nó cung cấp bằng directive `provides ... with ...`.

Ví dụ module cung cấp codec cho định dạng PNG:

~~~java
package com.example.codec.png;

import com.example.codec.api.CodecFactory;

public final class PngCodecFactory implements CodecFactory {
    public PngCodecFactory() {
    }

    @Override
    public String format() {
        return "png";
    }

    @Override
    public byte[] encode(byte[] input) {
        // Ví dụ minh họa: phần mã hóa thực tế do thư viện xử lý.
        return input.clone();
    }
}
~~~

Module descriptor:

~~~java
module com.example.codec.png {
    requires com.example.codec.api;
    provides com.example.codec.api.CodecFactory
            with com.example.codec.png.PngCodecFactory;
}
~~~

Các điểm cần nhớ:

- Provider module phải có mặt trên module path khi giải quyết module graph.
- Directive `provides` ghi rõ service type và provider type.
- Provider class thông thường phải là kiểu public, cụ thể và có public constructor không tham số; module cũng có thể khai báo provider method `public static provider()` theo quy tắc của `ServiceLoader`.
- Package chứa implementation provider thường không cần export. Ứng dụng làm việc qua service contract, giúp provider giữ kín chi tiết triển khai.

Không khai báo provider module như một dependency `requires` thông thường của ứng dụng chỉ để tìm provider. Service binding được thiết kế để ứng dụng phụ thuộc vào service contract và phát hiện implementation thông qua `ServiceLoader`.

## 4. Khai báo ứng dụng sử dụng service

Module ứng dụng cần đọc module API và khai báo service bằng directive `uses`:

~~~java
module com.example.imageapp {
    requires com.example.codec.api;
    uses com.example.codec.api.CodecFactory;
}
~~~

`requires` cho phép ứng dụng tham chiếu interface `CodecFactory`. `uses` khai báo rằng module sẽ tìm provider cho service đó.

Nếu mã trong named module gọi `ServiceLoader.load(CodecFactory.class)` mà module descriptor thiếu `uses`, việc tìm provider sẽ thất bại với `ServiceConfigurationError`. Đây là lỗi cấu hình module, không phải lỗi thiếu module trong runtime image.

## 5. Tìm và sử dụng provider bằng ServiceLoader

Ứng dụng lấy provider thông qua service contract:

~~~java
package com.example.imageapp;

import com.example.codec.api.CodecFactory;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<CodecFactory> loader =
                ServiceLoader.load(CodecFactory.class);

        boolean found = false;
        for (CodecFactory factory : loader) {
            found = true;
            System.out.println("Provider: " + factory.getClass().getName());
            System.out.println("Format: " + factory.format());
        }

        if (!found) {
            System.out.println("Không tìm thấy codec provider");
        }
    }
}
~~~

`ServiceLoader` tìm provider khi ứng dụng duyệt iterator hoặc stream. Việc nạp thường được thực hiện lười; tạo đối tượng `ServiceLoader` không có nghĩa tất cả provider đã được khởi tạo ngay.

Nếu cần xem metadata hoặc lọc provider trước khi khởi tạo, có thể dùng `stream()`:

~~~java
ServiceLoader<CodecFactory> loader =
        ServiceLoader.load(CodecFactory.class);

loader.stream()
        .filter(provider -> provider.type().getSimpleName().contains("Png"))
        .map(ServiceLoader.Provider::get)
        .forEach(factory -> System.out.println(factory.format()));
~~~

Ứng dụng cần xử lý trường hợp không có provider và lỗi cấu hình provider. Khi duyệt provider, `ServiceLoader` có thể ném `ServiceConfigurationError` nếu khai báo hoặc khởi tạo provider không hợp lệ. Không nên giả định luôn có đúng một provider; thiết kế service nên cho phép chọn provider theo tính năng hoặc chất lượng triển khai.

## 6. Provider đóng gói trên classpath

SPI không bắt buộc mọi provider phải là named module. Một provider có thể được đóng gói trong JAR trên classpath. Khi đó, Java nhận diện provider qua file cấu hình trong thư mục `META-INF/services`.

Với service `com.example.codec.api.CodecFactory`, JAR provider chứa file:

~~~text
META-INF/services/com.example.codec.api.CodecFactory
~~~

Nội dung file UTF-8, mỗi provider class trên một dòng:

~~~text
com.example.codec.png.PngCodecFactory
~~~

Provider được khai báo trong file này phải là lớp public, cụ thể và có public constructor không tham số để `ServiceLoader` có thể khởi tạo theo cơ chế classpath.

Ứng dụng classpath có thể tìm provider bằng cùng API:

~~~java
ServiceLoader<CodecFactory> loader =
        ServiceLoader.load(CodecFactory.class);
~~~

Điểm khác biệt là cách khai báo provider:

| Kiểu triển khai | Cách khai báo provider |
| --- | --- |
| Named module | Directive `provides Service with Provider` trong `module-info.java` |
| JAR trên classpath | File `META-INF/services/<tên-đầy-đủ-của-service>` |

JAR provider trên classpath và provider module là hai cách triển khai SPI khác nhau. Với JAR classpath, provider và các dependency của nó phải được phân phối cùng ứng dụng và nằm trong classpath mà launcher sử dụng.

## 7. Service binding và vai trò của jlink --bind-services

Khi tạo runtime image tối giản, `jlink` bắt đầu từ các module roots được chọn bằng `--add-modules`, sau đó giải quyết dependency module. Nếu một provider module chỉ được tìm qua `ServiceLoader`, nó có thể không nằm trong dependency `requires` trực tiếp của ứng dụng.

Tùy chọn `jlink --bind-services` yêu cầu công cụ liên kết các module cung cấp service cùng dependency của chúng theo service binding. Module consumer cần khai báo `uses`; provider module cần khai báo `provides`; các provider phải quan sát được trên module path.

Ví dụ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;providers" --add-modules com.example.imageapp --bind-services --strip-debug --no-header-files --no-man-pages --output build\runtime
~~~

Trong lệnh này:

1. `com.example.imageapp` là module root.
2. `uses com.example.codec.api.CodecFactory` cho biết service mà ứng dụng cần.
3. Provider module có directive `provides` cho service đó và nằm trong `providers`.
4. `--bind-services` liên kết provider module phù hợp cùng dependency của chúng vào runtime image.

Không cần liệt kê thủ công từng provider nếu service binding có thể tìm thấy provider từ module path. Nếu ứng dụng chọn implementation bằng tên lớp từ cấu hình mà không dùng SPI, `--bind-services` không thể suy ra lựa chọn đó; cần thêm module tương ứng bằng `--add-modules`.

## 8. Tìm provider có sẵn trên module path

JDK cung cấp tùy chọn `jlink --suggest-providers` để gợi ý module cung cấp một service type:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;providers" --suggest-providers com.example.codec.api.CodecFactory
~~~

Kết quả cho biết các module quan sát được có khai báo provider cho service được yêu cầu. Đây là công cụ hỗ trợ kiểm tra module path trước khi tạo runtime image.

Nếu không thấy provider:

- Kiểm tra provider JAR có trên module path hay chỉ có trên classpath.
- Kiểm tra module descriptor có directive `provides` đúng service type không.
- Kiểm tra module API chứa service type có được đưa vào module path không.
- Kiểm tra tên service và tên provider có khớp package/module thực tế không.

`--suggest-providers` chỉ gợi ý provider mà công cụ quan sát được. Nó không thay thế test `ServiceLoader` trên runtime image cuối cùng.

## 9. Thay đổi mặc định của jpackage từ JDK 25

Đây là điểm cần chú ý khi chuyển ứng dụng giữa các JDK hiện đại. Trước JDK 25, `jpackage` tự tạo runtime image có service bindings. Bắt đầu từ JDK 25, runtime image do `jpackage` tạo không còn tự động bao gồm service bindings.

Vì vậy, một ứng dụng modular sử dụng provider module qua `ServiceLoader` có thể hoạt động khi đóng gói bằng JDK cũ nhưng không tìm thấy provider sau khi chuyển sang `jpackage` JDK 25+ nếu không bật service binding.

Để yêu cầu `jpackage` chuyển `--bind-services` cho `jlink`, dùng `--jlink-options`:

~~~powershell
jpackage --type app-image --name ImageApp --module-path "mods;providers" --module com.example.imageapp/com.example.imageapp.Main --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" --dest dist
~~~

Khi chỉ định `--jlink-options`, hãy giữ lại các tùy chọn tối ưu mặc định mà bạn cần. Ví dụ trên giữ `--strip-native-commands`, `--strip-debug`, `--no-man-pages`, `--no-header-files` và bổ sung `--bind-services`.

Nếu đã tự tạo runtime bằng `jlink --bind-services`, truyền runtime đó cho `jpackage --runtime-image`. Trong trường hợp này `jpackage` sử dụng runtime image có sẵn; service binding phải được thực hiện ở bước `jlink`.

Không nên dựa vào hành vi mặc định của `jpackage` ở JDK cũ khi triển khai bằng JDK 25 trở lên. Hãy khai báo service binding tường minh và kiểm thử ứng dụng sau đóng gói.

## 10. Service provider trên classpath không được jlink bind như provider module

`jlink --bind-services` làm việc với service provider được khai báo trong module descriptor và quan sát được trên module path. Nó không đọc mọi file `META-INF/services` trong các JAR classpath để biến các JAR đó thành module provider trong runtime image.

Nếu provider là JAR classpath:

- Đưa JAR provider vào thư mục input của `jpackage`.
- Đảm bảo file `META-INF/services` được giữ nguyên trong JAR.
- Đảm bảo launcher đưa JAR đó vào classpath.
- Kiểm thử `ServiceLoader.load(Service.class)` bằng launcher của application image.

Với classpath application, runtime image chứa các module JDK cần thiết; các JAR ứng dụng và provider vẫn nằm trong application image. `--bind-services` không thay thế việc đóng gói các JAR classpath.

Nếu provider được triển khai trong named module, đặt module trên module path và khai báo `provides`. Khi đó service binding có thể đưa provider module vào runtime image.

## 11. Kiểm tra runtime image và service discovery

Sau khi tạo runtime image, có thể xem module đã được liên kết:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Nếu dùng provider module, xác nhận tên module provider có trong danh sách. Tuy nhiên, việc module có mặt trong image chưa chứng minh `ServiceLoader` tìm thấy hoặc khởi tạo provider thành công.

Hãy chạy ứng dụng bằng chính runtime image:

~~~powershell
.\build\runtime\bin\java.exe -m com.example.imageapp/com.example.imageapp.Main
~~~

Kiểm tra:

- Module consumer có `uses` đúng service.
- Provider module có `provides` đúng service và implementation.
- Provider module được resolve và có trong runtime image.
- Constructor hoặc provider method khởi tạo thành công.
- Dependency của provider có mặt.
- Nếu dùng classpath provider, JAR và file `META-INF/services` có trong application image.
- Ứng dụng xử lý được trường hợp không có provider hoặc có nhiều provider.

Với plugin module được đặt trong module layer riêng, có thể dùng `ServiceLoader.load(layer, Service.class)` để tìm provider trong layer đó và các parent layer. API này tìm provider trong named modules của layer, không tìm provider trong unnamed module trên classpath.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ServiceConfigurationError` do module consumer | Thiếu directive `uses` | Bổ sung `uses` trong module descriptor |
| Không tìm thấy provider module | Thiếu directive `provides`, module không có trên module path hoặc runtime image | Kiểm tra descriptor, `--module-path` và `--bind-services` |
| Provider class không khởi tạo được | Constructor/provider method sai hoặc dependency thiếu | Kiểm tra provider type và dependency |
| Chạy bằng JDK đầy đủ được nhưng runtime image không được | Provider module không được bind khi tạo image | Dùng `jlink --bind-services` hoặc `jpackage --jlink-options` |
| Chuyển sang JDK 25+ thì mất provider | `jpackage` không còn bind service mặc định | Bổ sung `--bind-services` vào `--jlink-options` |
| Provider classpath không được tìm thấy | JAR không có trong classpath hoặc thiếu `META-INF/services` | Kiểm tra thư mục input, launcher và file service configuration |
| `ServiceLoader` không tìm provider trong plugin layer | Đang dùng overload với class loader hoặc layer không phù hợp | Chọn `ServiceLoader.load(layer, Service.class)` khi provider thuộc layer riêng |

## 13. Quy trình triển khai đề xuất

1. Xác định service contract và module export service API.
2. Khai báo `uses` trong module consumer.
3. Khai báo `provides ... with ...` trong từng provider module; với provider classpath, tạo file `META-INF/services`.
4. Đặt provider module trên module path hoặc provider JAR trên classpath theo mô hình triển khai.
5. Với runtime image modular, dùng `jlink --bind-services` nếu cần tự động liên kết provider module.
6. Với `jpackage` JDK 25+, truyền `--bind-services` qua `--jlink-options` nếu ứng dụng cần service binding.
7. Kiểm tra module list và chạy test `ServiceLoader` bằng runtime/application image thực tế.
8. Kiểm thử trường hợp không có provider, nhiều provider và provider khởi tạo lỗi.

**Ghi nhớ:** `ServiceLoader` tách service contract khỏi implementation; `uses` và `provides` mô tả quan hệ service trong JPMS; `jlink --bind-services` liên kết provider module cùng dependency của chúng vào runtime image. Provider JAR trên classpath dùng `META-INF/services` và phải được đóng gói riêng. Từ JDK 25, `jpackage` không còn tự bind service mặc định, vì vậy hãy bật `--bind-services` tường minh khi ứng dụng cần cơ chế này.

## Nguồn tham khảo chính thức

- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [JDK 25 Release Notes — jpackage service bindings](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
