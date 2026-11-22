# Xử lý không có dịch vụ hoặc ServiceConfigurationError

## 1. Mục tiêu

Java Service Provider Interface (SPI) cho phép ứng dụng tìm implementation được cung cấp độc lập với module hoặc thư viện gọi nó. JDK cung cấp java.util.ServiceLoader để khám phá provider tại runtime.

Khi dùng SPI, cần phân biệt hai tình huống:

- **Không có provider:** không tìm thấy implementation nào được đăng ký. Việc duyệt ServiceLoader kết thúc bình thường và không có phần tử.
- **Cấu hình provider bị lỗi:** provider được khai báo nhưng không thể đọc, nạp, kiểm tra hoặc khởi tạo đúng cách. ServiceLoader có thể ném ServiceConfigurationError.

Không có provider có thể là trạng thái hợp lệ nếu tính năng là tùy chọn. ServiceConfigurationError thường chỉ ra lỗi đóng gói, classpath/module path, class loader hoặc implementation và cần được ghi nhận như lỗi cấu hình triển khai.

## 2. ServiceLoader hoạt động như thế nào?

ServiceLoader tìm implementation của một service interface hoặc abstract class. Ứng dụng phụ thuộc vào contract của service; provider cung cấp implementation cụ thể.

Ví dụ service contract:

~~~java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Ứng dụng có thể tìm provider mà không import trực tiếp lớp implementation:

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.greet("Java"));
}
~~~

Các đặc điểm cần nhớ:

- Provider được khám phá và khởi tạo lazy khi ứng dụng duyệt iterator hoặc stream.
- ServiceLoader lưu cache các provider đã nạp trong chính instance của nó.
- Nhiều provider có thể cùng đăng ký một service.
- ServiceLoader không bảo đảm an toàn khi nhiều thread cùng truy cập một instance. Hãy tạo instance riêng hoặc đồng bộ hóa quyền truy cập nếu cần.
- load(Class) dùng context class loader của thread hiện tại cho cơ chế tìm provider theo class loader. Có thể truyền class loader rõ ràng bằng load(Class, ClassLoader).
- Với plugin trong ModuleLayer riêng, dùng load(ModuleLayer, Class) để khám phá provider trong layer đó.

Không nên giả định lời gọi load đã kiểm tra toàn bộ provider. Nhiều lỗi chỉ xuất hiện khi provider được duyệt hoặc khởi tạo.

## 3. Trường hợp không tìm thấy provider

Nếu không có provider nào được đăng ký, iterator của ServiceLoader không có phần tử. hasNext() trả về false và vòng lặp kết thúc bình thường. Đây không phải lỗi và không tự động tạo ra ServiceConfigurationError.

Ứng dụng cần quyết định ý nghĩa của trạng thái này:

- Nếu service là tùy chọn, có thể tắt chức năng liên quan, dùng fallback hoặc thông báo cho người dùng.
- Nếu service là bắt buộc, nên dừng khởi tạo tính năng hoặc báo lỗi cấu hình rõ ràng.
- Nếu service được nạp từ plugin, có thể hiển thị thông báo rằng chưa cài plugin tương ứng.

Ví dụ kiểm tra provider đầu tiên:

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

Iterator<GreetingService> providers = loader.iterator();

if (!providers.hasNext()) {
    System.out.println("No provider found");
    return;
}

GreetingService service = providers.next();
System.out.println(service.greet("Java"));
~~~

Nếu không có provider, output là:

~~~text
No provider found
~~~

Không nên dùng catch ServiceConfigurationError để xử lý trường hợp không có provider. Hai trạng thái có nguyên nhân và cách khắc phục khác nhau.

## 4. ServiceConfigurationError là gì?

ServiceConfigurationError là một lớp con của Error trong java.util. ServiceLoader dùng nó để báo các lỗi liên quan đến cấu hình hoặc nạp provider.

Các nguyên nhân thường gặp:

- File cấu hình provider sai định dạng hoặc chứa tên lớp không hợp lệ.
- Provider được khai báo nhưng class không tồn tại trên classpath/module path.
- Provider không thể được nạp bởi class loader đang dùng.
- Lớp provider không tương thích với service type.
- Provider không đáp ứng quy tắc khởi tạo của cơ chế đăng ký đang dùng.
- Constructor hoặc provider method phát sinh lỗi trong lúc tạo implementation.
- Module khai báo uses/provides sai hoặc module provider không nằm trong module layer được tìm kiếm.

Vì ServiceConfigurationError kế thừa Error, catch Exception sẽ không bắt được lỗi này. Nếu ứng dụng cần chuyển lỗi cấu hình SPI thành thông báo ở ranh giới khởi tạo, hãy bắt chính xác ServiceConfigurationError.

Lỗi có thể xuất hiện trong các thao tác lazy như iterator.hasNext(), iterator.next(), stream traversal hoặc Provider.get(). Vì vậy, đặt try/catch quanh toàn bộ đoạn duyệt và khởi tạo provider. Chỉ bắt lỗi quanh lệnh ServiceLoader.load thường là chưa đủ.

## 5. Mẫu xử lý cả hai tình huống

Ví dụ dưới đây xử lý riêng trường hợp không có provider và trường hợp cấu hình provider bị lỗi:

~~~java
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class GreetingServiceDiscovery {
    private GreetingServiceDiscovery() {
    }

    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

        try {
            Iterator<GreetingService> providers = loader.iterator();

            if (!providers.hasNext()) {
                System.out.println("NO_PROVIDER");
                return;
            }

            GreetingService service = providers.next();
            System.out.println(service.greet("Java"));
        } catch (ServiceConfigurationError error) {
            System.out.println(
                "CONFIG_ERROR: " + error.getClass().getSimpleName()
            );
        }
    }
}
~~~

Kết quả tùy theo môi trường:

| Cấu hình | Kết quả |
|---|---|
| Không có provider được đăng ký | NO_PROVIDER |
| Có provider hợp lệ | Hello, Java! |
| Provider được khai báo nhưng không thể nạp | CONFIG_ERROR: ServiceConfigurationError |

Đoạn code bắt lỗi ở cả hasNext() và next() vì provider có thể được kiểm tra hoặc khởi tạo tại một trong hai thời điểm. Nếu service có nhiều provider và ứng dụng duyệt tất cả, hãy đặt toàn bộ vòng lặp trong cùng vùng try/catch.

Không nên chuyển ServiceConfigurationError thành trạng thái không có provider bằng cách trả về danh sách rỗng. Việc đó che giấu lỗi triển khai và khiến ứng dụng khó chẩn đoán.

## 6. Đăng ký provider trên classpath

Với cơ chế classpath truyền thống, provider được khai báo trong file có tên chính xác bằng fully qualified name của service:

~~~text
META-INF/services/com.acme.spi.GreetingService
~~~

Nội dung file là tên đầy đủ của từng provider class, mỗi provider trên một dòng:

~~~text
com.acme.impl.EnglishGreetingService
com.acme.impl.FrenchGreetingService
~~~

Các dòng trống và comment bắt đầu bằng dấu # được bỏ qua. File phải nằm trong thư mục META-INF/services ở một thư mục hoặc JAR có trên classpath.

Provider class cho cơ chế classpath phải là lớp concrete, tương thích với service type và có public no-argument constructor. Ví dụ:

~~~java
package com.acme.impl;

import com.acme.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Khi đóng gói JAR, kiểm tra file dịch vụ vẫn nằm đúng vị trí:

~~~bash
jar --list --file greeting-provider.jar
~~~

Danh sách entry cần có META-INF/services/com.acme.spi.GreetingService và class provider. Nếu file dịch vụ bị thiếu trong JAR cuối cùng, ServiceLoader sẽ không tìm thấy provider dù file có tồn tại trong thư mục source của dự án.

Nếu file dịch vụ chứa tên lớp sai, lớp thiếu dependency hoặc provider không thể khởi tạo, lỗi có thể chỉ xuất hiện khi ứng dụng duyệt ServiceLoader.

## 7. Đăng ký provider bằng JPMS

Trong ứng dụng modular, service được khai báo trực tiếp trong module descriptor thay cho file META-INF/services.

Module chứa service API:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Module tiêu thụ service phải khai báo uses:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
~~~

Module cung cấp implementation phải khai báo provides:

~~~java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
~~~

Provider class:

~~~java
package com.acme.provider;

import com.acme.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Trong named module, provider class có thể sử dụng public no-argument constructor hoặc public static provider method theo quy tắc của ServiceLoader. Provider method cho phép module trả về implementation mà lớp provider không nhất thiết phải chính là lớp triển khai service. Phương thức phải có tên provider, là public static, không nhận tham số và trả về kiểu tương thích với service.

Ví dụ provider method:

~~~java
package com.acme.provider;

import com.acme.spi.GreetingService;

public final class GreetingProviderFactory {
    private GreetingProviderFactory() {
    }

    public static GreetingService provider() {
        return new EnglishGreetingService();
    }
}
~~~

Descriptor khi đó khai báo:

~~~java
provides com.acme.spi.GreetingService
    with com.acme.provider.GreetingProviderFactory;
~~~

Khi module ứng dụng gọi ServiceLoader.load(GreetingService.class), JPMS tìm provider được khai báo trong module layer phù hợp với module tiêu thụ. Module ứng dụng phải khai báo uses; module provider phải khai báo provides. Nếu tự tạo ModuleLayer để nạp plugin, hãy chỉ rõ layer bằng ServiceLoader.load(layer, GreetingService.class).

Không cần export package provider chỉ để ServiceLoader khám phá provider của một named module. Chỉ export package nếu module khác cần truy cập public API trong package đó.

## 8. ServiceLoader.stream và Provider

Ngoài iterator, ServiceLoader cung cấp stream() để duyệt các đối tượng Provider<S>. Provider cho phép xem kiểu provider trước khi khởi tạo implementation bằng Provider.get().

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

try {
    loader.stream().forEach(provider -> {
        Class<? extends GreetingService> type = provider.type();
        System.out.println("Provider type: " + type.getName());

        GreetingService service = provider.get();
        System.out.println(service.greet("Java"));
    });
} catch (ServiceConfigurationError error) {
    System.err.println("Cannot load service provider: " + error);
}
~~~

Provider.type() hữu ích khi cần lọc implementation theo metadata hoặc loại class trước khi tạo instance. Provider.get() mới thực sự yêu cầu instance; lỗi cấu hình hoặc khởi tạo có thể xuất hiện tại bước này.

Stream vẫn là lazy stream. Nếu cần bắt lỗi trong toàn bộ quá trình duyệt, hãy đặt try/catch quanh terminal operation như forEach, collect hoặc findFirst, không chỉ quanh lời gọi stream().

## 9. Fallback và chính sách lỗi

Fallback chỉ nên được dùng khi service thực sự tùy chọn và fallback đáp ứng đúng contract. Ví dụ:

~~~java
GreetingService service = discoverOptionalService()
    .orElseGet(DefaultGreetingService::new);
~~~

Nếu không tìm thấy provider, ứng dụng có thể dùng implementation mặc định. Tuy nhiên, nếu ServiceLoader ném ServiceConfigurationError, không nên âm thầm chuyển sang fallback như thể chưa có provider. Hãy ghi log đầy đủ và báo lỗi cấu hình, hoặc áp dụng chính sách khôi phục đã được thiết kế rõ.

Với service bắt buộc, có thể chuyển trạng thái không có provider thành lỗi nghiệp vụ cụ thể:

~~~java
if (!providers.hasNext()) {
    throw new IllegalStateException(
        "Required GreetingService provider is missing"
    );
}
~~~

Với ServiceConfigurationError, nên giữ nguyên cause khi chuyển thành lỗi ở tầng ứng dụng:

~~~java
catch (ServiceConfigurationError error) {
    throw new IllegalStateException(
        "GreetingService configuration is invalid",
        error
    );
}
~~~

Không bắt Throwable hoặc Error tổng quát để tiếp tục ứng dụng. Cách đó có thể nuốt cả lỗi nghiêm trọng của JVM như OutOfMemoryError. Chỉ bắt ServiceConfigurationError tại ranh giới phù hợp để xử lý lỗi SPI có chủ đích.

## 10. Cache, reload và class loader

ServiceLoader lưu cache các provider đã được nạp trong instance. Nếu ứng dụng cần khám phá lại provider sau khi thay đổi classpath hoặc cấu hình plugin, có thể gọi reload():

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

loader.reload();
~~~

reload() xóa cache provider; các lần duyệt sau sẽ khám phá lại provider. Nó không tự cài thêm JAR, sửa module path, thay đổi class loader hoặc làm cho một module không được resolve trở nên khả dụng.

Trong hệ thống plugin, cần chú ý context class loader của thread. Một provider có thể có mặt trong plugin class loader nhưng không được nhìn thấy bởi context class loader hiện tại. Có thể truyền class loader cụ thể:

~~~java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class, pluginClassLoader);
~~~

Đối với plugin chạy trong ModuleLayer riêng, dùng overload nhận ModuleLayer. Chọn đúng cơ chế discovery theo cách plugin được đóng gói; không trộn classpath, module path và class loader tùy ý.

## 11. Kiểm thử các tình huống

Một bộ kiểm thử SPI tối thiểu nên bao gồm:

1. Không có file dịch vụ hoặc module provider: xác nhận ứng dụng xử lý trạng thái không có provider theo chính sách.
2. Provider hợp lệ: xác nhận provider được tìm thấy, khởi tạo và gọi đúng.
3. Provider class không tồn tại: xác nhận ServiceConfigurationError được phát hiện.
4. Provider không tương thích với service type hoặc thiếu constructor cần thiết: xác nhận lỗi cấu hình được ghi nhận.
5. Nhiều provider: xác nhận ứng dụng xử lý đúng thứ tự và không giả định chỉ có một provider.
6. Module provider: xác nhận uses/provides và module path/module layer được cấu hình đúng.
7. Plugin class loader: xác nhận provider được nhìn thấy từ đúng context class loader.

Không nên chỉ kiểm tra ServiceLoader.load() vì việc nạp provider thường xảy ra khi duyệt iterator hoặc stream. Test phải thực hiện thao tác thực sự buộc ServiceLoader khám phá và khởi tạo provider.

## 12. Ví dụ chạy độc lập trên JDK 17+

Tạo các file sau:

~~~text
src/
├── com/acme/spi/GreetingService.java
├── com/acme/impl/EnglishGreetingService.java
└── com/acme/app/Main.java
resources-valid/
└── META-INF/services/
    └── com.acme.spi.GreetingService
resources-invalid/
└── META-INF/services/
    └── com.acme.spi.GreetingService
resources-empty/
~~~

Service interface:

~~~java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Provider implementation:

~~~java
package com.acme.impl;

import com.acme.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Ứng dụng:

~~~java
package com.acme.app;

import com.acme.spi.GreetingService;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

        try {
            Iterator<GreetingService> providers = loader.iterator();

            if (!providers.hasNext()) {
                System.out.println("NO_PROVIDER");
                return;
            }

            GreetingService service = providers.next();
            System.out.println(service.greet("Java"));
        } catch (ServiceConfigurationError error) {
            System.out.println(
                "CONFIG_ERROR: " + error.getClass().getSimpleName()
            );
        }
    }
}
~~~

File resources-valid/META-INF/services/com.acme.spi.GreetingService:

~~~text
com.acme.impl.EnglishGreetingService
~~~

File resources-invalid/META-INF/services/com.acme.spi.GreetingService:

~~~text
com.acme.impl.MissingGreetingService
~~~

Biên dịch từ thư mục dự án:

~~~bash
mkdir -p out resources-empty
javac --release 17 -d out \
  src/com/acme/spi/GreetingService.java \
  src/com/acme/impl/EnglishGreetingService.java \
  src/com/acme/app/Main.java
~~~

Chạy với cấu hình không có provider:

~~~bash
java -cp "out:resources-empty" com.acme.app.Main
~~~

Output:

~~~text
NO_PROVIDER
~~~

Chạy với provider hợp lệ:

~~~bash
java -cp "out:resources-valid" com.acme.app.Main
~~~

Output:

~~~text
Hello, Java!
~~~

Chạy với provider class không tồn tại:

~~~bash
java -cp "out:resources-invalid" com.acme.app.Main
~~~

Output:

~~~text
CONFIG_ERROR: ServiceConfigurationError
~~~

Trên Windows, classpath dùng dấu chấm phẩy thay cho dấu hai chấm:

~~~powershell
java -cp "out;resources-empty" com.acme.app.Main
java -cp "out;resources-valid" com.acme.app.Main
java -cp "out;resources-invalid" com.acme.app.Main
~~~

Ví dụ cố ý in tên loại lỗi thay vì toàn bộ thông báo, vì nội dung message có thể thay đổi theo JDK và nguyên nhân chi tiết. Trong ứng dụng thực tế, hãy log exception cùng stack trace và thông tin classpath/module layer để điều tra.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có provider | Thiếu file META-INF/services hoặc thiếu module provides | Kiểm tra artifact và cách đăng ký |
| ServiceConfigurationError: Provider not found | Tên provider trong file dịch vụ sai hoặc class thiếu trên classpath | Kiểm tra tên đầy đủ, dependency và class loader |
| Provider not a subtype | Provider class không implement service contract | Kiểm tra implements và phiên bản API |
| Provider could not be instantiated | Constructor/provider method sai hoặc khởi tạo phát sinh lỗi | Kiểm tra quy tắc constructor/provider method và cause |
| Module không tìm thấy service | Consumer thiếu uses hoặc provider thiếu provides | Kiểm tra module-info.java và module layer |
| Chạy được trong IDE nhưng không chạy trong JAR | File META-INF/services không được đóng gói hoặc runtime classpath khác | Kiểm tra JAR cuối cùng bằng jar --list |
| Plugin không được phát hiện | Context class loader hoặc ModuleLayer không đúng | Truyền đúng ClassLoader hoặc ModuleLayer |
| Lỗi chỉ xuất hiện khi duyệt | ServiceLoader nạp provider lazy | Bắt ServiceConfigurationError quanh iterator/stream traversal |

## 14. Checklist triển khai

- [ ] Service contract ổn định và độc lập với implementation.
- [ ] Provider class tuân thủ quy tắc constructor hoặc provider method.
- [ ] Classpath service file có đúng tên và vị trí META-INF/services.
- [ ] Với JPMS, consumer khai báo uses và provider khai báo provides.
- [ ] Module provider nằm trong module path hoặc ModuleLayer được tìm kiếm.
- [ ] Ứng dụng phân biệt rõ không có provider với cấu hình provider bị lỗi.
- [ ] try/catch bao phủ cả hasNext, next hoặc stream terminal operation.
- [ ] ServiceConfigurationError được ghi nhận cùng nguyên nhân gốc.
- [ ] Fallback chỉ được dùng cho service tùy chọn theo chính sách đã định.
- [ ] Test bao gồm provider hợp lệ, không có provider và provider lỗi.
- [ ] Không dùng một ServiceLoader instance đồng thời từ nhiều thread nếu không đồng bộ.

## Tài liệu tham khảo

- [ServiceLoader API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceConfigurationError API — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceConfigurationError.html)
- [The Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
- [The jar Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [Java Language Specification — Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html)
