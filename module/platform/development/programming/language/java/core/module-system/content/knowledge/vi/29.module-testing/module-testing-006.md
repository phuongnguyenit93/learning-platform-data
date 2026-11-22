# Test ServiceLoader với provider module

## 1. Mục tiêu của bài kiểm thử

Trong Java Platform Module System (JPMS), **ServiceLoader** là cơ chế chuẩn để consumer tìm những implementation của một service type mà không phải phụ thuộc trực tiếp vào class provider. Consumer chỉ cần service interface, còn provider module khai báo cung cấp implementation thông qua module descriptor.

Khi test ServiceLoader trong một ứng dụng modular, cần kiểm tra nhiều điều hơn việc tạo được object:

- Service interface được đặt ở module API và export đúng package.
- Consumer hoặc test module có khai báo **uses** cho service type.
- Provider module khai báo **provides ... with ...** hợp lệ.
- Provider module được phân giải vào module graph hoặc module layer cần kiểm thử.
- ServiceLoader dùng đúng layer/class loader để tìm provider.
- Provider trả về đúng hành vi theo hợp đồng.
- Test không giả định thứ tự provider.
- Trường hợp không có provider hoặc provider cấu hình sai được xử lý có chủ đích.

Ví dụ ở bài này sử dụng **Java 17 trở lên**, một service contract TextFormatter, hai provider module và một named test module có main method tự kiểm tra kết quả. Cách này không cần thư viện test ngoài, giúp thấy rõ cơ chế JPMS trước khi chuyển sang JUnit.

## 2. Phân biệt ba vai trò trong service loading

Mô hình có ba loại module:

**API module** định nghĩa service type mà cả consumer và provider cùng tham chiếu.

**Provider module** triển khai service type và đăng ký provider trong module-info.java.

**Consumer/test module** tuyên bố sử dụng service bằng uses rồi truy vấn ServiceLoader.

Sơ đồ:

~~~text
com.acme.format.tests
    | requires
    v
com.acme.format.api
    ^               ^
    | requires      | requires
    |               |
com.acme.format.upper    com.acme.format.reverse
    | provides                | provides
    +------ TextFormatter ----+
                ^
                |
       ServiceLoader discovery
~~~

Test module không cần requires trực tiếp com.acme.format.upper hoặc com.acme.format.reverse. Chính tính độc lập đó là điều cần xác nhận: consumer chỉ dựa vào service contract, còn provider có thể thay đổi độc lập.

Có thể có nhiều implementation cùng cung cấp một service. Vì vậy, unit/integration test phải kiểm tra theo định danh hoặc behavior, không dùng giả định provider đầu tiên luôn là một implementation cụ thể.

## 3. Cấu trúc dự án

Sắp xếp source như sau:

~~~text
service-test/
├── src/
│   ├── com.acme.format.api/
│   │   ├── module-info.java
│   │   └── com/acme/format/api/TextFormatter.java
│   ├── com.acme.format.upper/
│   │   ├── module-info.java
│   │   └── com/acme/format/upper/UpperFormatter.java
│   └── com.acme.format.reverse/
│       ├── module-info.java
│       └── com/acme/format/reverse/ReverseFormatter.java
├── test-src/
│   └── com.acme.format.tests/
│       ├── module-info.java
│       └── com/acme/format/tests/
│           ├── ServiceDiscoveryTest.java
│           └── NoProviderTest.java
├── mods/
└── test-mods/
~~~

Mỗi thư mục module chứa module-info.java ở gốc. Các class thuộc package riêng, tránh split package giữa named modules.

Đặt code production trong src và code kiểm thử trong test-src để dễ tách artifact. Module tests được biên dịch vào test-mods, không đưa class kiểm thử vào JAR production.

## 4. Định nghĩa service API

Tạo file src/com.acme.format.api/module-info.java:

~~~java
module com.acme.format.api {
    exports com.acme.format.api;
}
~~~

Tạo service type:

~~~java
package com.acme.format.api;

public interface TextFormatter {
    String name();

    String format(String text);
}
~~~

Hợp đồng có hai method:

- name() trả về định danh ổn định của provider.
- format(text) chuyển đổi một chuỗi theo quy tắc của provider.

Định danh này phục vụ lựa chọn và kiểm tra provider. Trong hệ thống thực tế, API có thể khai báo thêm metadata, cấu hình và quy tắc xử lý lỗi, nhưng nên giữ hợp đồng nhỏ và độc lập với implementation.

Package com.acme.format.api được export vì cả provider và consumer cần tham chiếu TextFormatter. Nếu API package không được export, provider khác module không thể implement type thông thường bằng code Java.

## 5. Viết provider module thứ nhất

Tạo src/com.acme.format.upper/module-info.java:

~~~java
module com.acme.format.upper {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.upper.UpperFormatter;
}
~~~

Implementation:

~~~java
package com.acme.format.upper;

import com.acme.format.api.TextFormatter;
import java.util.Locale;

public final class UpperFormatter implements TextFormatter {

    public UpperFormatter() {
    }

    @Override
    public String name() {
        return "upper";
    }

    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

Module provider cần requires module API vì implementation dùng TextFormatter. Chỉ thị provides đăng ký implementation cho service.

Package com.acme.format.upper **không phải export** cho test module. Test chỉ cần biết interface; ServiceLoader và module system xử lý việc truy cập provider theo metadata service.

Provider class trong ví dụ là public, có public constructor không tham số và implement đúng TextFormatter. Đây là cách đăng ký provider class phổ biến. Named module cũng có thể dùng provider method trong những tình huống factory, nhưng không cần cho ví dụ này.

## 6. Viết provider module thứ hai

Descriptor của src/com.acme.format.reverse/module-info.java:

~~~java
module com.acme.format.reverse {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.reverse.ReverseFormatter;
}
~~~

Implementation:

~~~java
package com.acme.format.reverse;

import com.acme.format.api.TextFormatter;

public final class ReverseFormatter implements TextFormatter {

    public ReverseFormatter() {
    }

    @Override
    public String name() {
        return "reverse";
    }

    @Override
    public String format(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

Lúc này hai named modules cùng provide TextFormatter nhưng không cùng chứa package. Mỗi provider chỉ cần requires module API, không cần biết hoặc phụ thuộc provider còn lại.

Cùng một service type có thể có nhiều provider. Thêm provider thứ ba chỉ cần một module mới đăng ký provides đúng cách, nếu module đó được đưa vào layer đang sử dụng.

## 7. Tạo named test module có uses

Descriptor của test module ở test-src/com.acme.format.tests/module-info.java:

~~~java
module com.acme.format.tests {
    requires com.acme.format.api;
    uses com.acme.format.api.TextFormatter;
}
~~~

Hai chỉ thị thực hiện hai công việc riêng:

- requires com.acme.format.api cho phép test module đọc service contract.
- uses com.acme.format.api.TextFormatter thông báo test module là service consumer.

Việc có requires không thay thế uses. Trong named module, khi code gọi ServiceLoader cho một service type, caller module cần khai báo uses cho service đó theo quy định của API.

Đáng chú ý, descriptor không có:

~~~text
requires com.acme.format.upper;
requires com.acme.format.reverse;
~~~

Test đang kiểm tra discovery thông qua service metadata, không kiểm tra liên kết trực tiếp tới implementation. Nếu thêm requires tới từng provider chỉ để kiểm thử thì đã làm yếu tính linh hoạt của SPI.

## 8. Kiểm thử provider discovery và behavior

Tạo ServiceDiscoveryTest.java trong package com.acme.format.tests:

~~~java
package com.acme.format.tests;

import com.acme.format.api.TextFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.Set;

public final class ServiceDiscoveryTest {

    public static void main(String[] args) {
        ServiceLoader<TextFormatter> loader =
                ServiceLoader.load(
                        ModuleLayer.boot(),
                        TextFormatter.class
                );

        Map<String, TextFormatter> providers = new HashMap<>();

        for (TextFormatter service : loader) {
            TextFormatter old =
                    providers.putIfAbsent(service.name(), service);

            if (old != null) {
                throw new AssertionError(
                        "Duplicate provider name: " + service.name()
                );
            }

            System.out.println(
                    service.name() + " from module "
                    + service.getClass().getModule().getName()
            );
        }

        Set<String> expected = Set.of("upper", "reverse");

        if (!providers.keySet().equals(expected)) {
            throw new AssertionError(
                    "Expected providers " + expected
                    + ", actual " + providers.keySet()
            );
        }

        assertEquals(
                "HELLO",
                providers.get("upper").format("hello")
        );

        assertEquals(
                "cba",
                providers.get("reverse").format("abc")
        );

        System.out.println("ServiceLoader integration test passed");
    }

    private static void assertEquals(
            String expected, String actual
    ) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + actual
            );
        }
    }
}
~~~

Test làm ba loại kiểm tra:

1. **Discovery**: có đúng hai provider theo danh sách tên kỳ vọng.
2. **Uniqueness**: không có hai provider trùng tên logic.
3. **Contract behavior**: upper và reverse thực hiện đúng phép biến đổi.

Không dùng iterator().next() để coi provider đầu tiên là upper, vì thứ tự provider không phải hợp đồng ưu tiên nghiệp vụ. Dùng Set và Map làm test không phụ thuộc thứ tự duyệt.

Trong ví dụ, ServiceLoader.load(ModuleLayer.boot(), service) chỉ tìm provider trong boot layer và các layer tổ tiên liên quan theo quy tắc API. Đối với plugin layer tự tạo, nên truyền layer của plugin thay vì mặc định boot layer.

## 9. Biên dịch production modules

Từ thư mục service-test, biên dịch ba module production:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.format.api,com.acme.format.upper,com.acme.format.reverse
~~~

Output:

~~~text
mods/
├── com.acme.format.api/
│   ├── module-info.class
│   └── com/acme/format/api/TextFormatter.class
├── com.acme.format.upper/
│   ├── module-info.class
│   └── com/acme/format/upper/UpperFormatter.class
└── com.acme.format.reverse/
    ├── module-info.class
    └── com/acme/format/reverse/ReverseFormatter.class
~~~

Đây là ba exploded modules. Mỗi module có descriptor riêng và package riêng. Khi đưa thư mục mods lên module path, Java launcher có thể tìm chúng theo tên module.

Nếu sử dụng modular JAR thay vì exploded modules, hãy kiểm tra mỗi JAR có module-info.class ở gốc. Kiểm tra thông tin provides bằng lệnh jar --describe-module.

## 10. Biên dịch named test module

Biên dịch test module dựa trên module API đã có trong mods:

~~~bash
javac --module-source-path test-src \
      --module-path mods \
      -d test-mods \
      -m com.acme.format.tests
~~~

Ở đây:

- --module-source-path test-src tìm module-info.java và source test.
- --module-path mods cung cấp service API và các module production đã biên dịch.
- -d test-mods giữ test output riêng biệt.
- -m com.acme.format.tests chọn đúng named test module.

Bởi vì test module chỉ import TextFormatter, nó không cần import UpperFormatter hoặc ReverseFormatter; các provider được tìm ở runtime.

Test module cũng có module-info.class tại gốc thư mục test-mods/com.acme.format.tests.

## 11. Chạy test với provider modules được phân giải

Một module có mặt trên module path chưa chắc đã được phân giải thành root/module của boot layer trong mọi cấu hình. Để bài kiểm thử có điều kiện rõ ràng, đưa provider modules vào root set một cách tường minh:

~~~bash
java --module-path mods:test-mods \
     --add-modules com.acme.format.upper,com.acme.format.reverse \
     --module com.acme.format.tests/com.acme.format.tests.ServiceDiscoveryTest
~~~

Trên Windows:

~~~powershell
java --module-path "mods;test-mods" --add-modules com.acme.format.upper,com.acme.format.reverse --module com.acme.format.tests/com.acme.format.tests.ServiceDiscoveryTest
~~~

Nhờ --add-modules, cả upper và reverse được phân giải vào boot layer. Test gọi ServiceLoader.load(ModuleLayer.boot(), TextFormatter.class) nên có thể khám phá provider của các module đó.

Đầu ra minh họa:

~~~text
upper from module com.acme.format.upper
reverse from module com.acme.format.reverse
ServiceLoader integration test passed
~~~

Thứ tự hai dòng provider có thể khác nhau. Điều quan trọng là Set tên provider và hành vi đã được xác minh.

Phân biệt rõ **module path** với **resolved modules**: JAR xuất hiện trên module path không phải lời đảm bảo mọi module trong thư mục đều tham gia module graph. Trong test integration cần cố định cấu hình module roots/module layer để kết quả tái lập được.

## 12. Test khi không có provider

Cần xác minh consumer xử lý được tình huống không có implementation.

Tạo NoProviderTest.java:

~~~java
package com.acme.format.tests;

import com.acme.format.api.TextFormatter;
import java.util.ServiceLoader;

public final class NoProviderTest {

    public static void main(String[] args) {
        ServiceLoader<TextFormatter> loader =
                ServiceLoader.load(
                        ModuleLayer.boot(),
                        TextFormatter.class
                );

        if (loader.iterator().hasNext()) {
            throw new AssertionError(
                    "Expected no provider in isolated test layer"
            );
        }

        System.out.println("No-provider test passed");
    }
}
~~~

Test này chỉ hợp lệ khi layer đang được kiểm tra **không chứa provider module**. Vì vậy, cần chuẩn bị một module path fixture không có upper/reverse. Ví dụ trên Linux/macOS, sau khi compile:

~~~bash
mkdir -p only-api-mods
cp -R mods/com.acme.format.api only-api-mods/
~~~

Chạy với thư mục only-api-mods và test-mods, không đưa mods đầy đủ lên module path:

~~~bash
java --module-path only-api-mods:test-mods \
     --module com.acme.format.tests/com.acme.format.tests.NoProviderTest
~~~

Kết quả mong đợi:

~~~text
No-provider test passed
~~~

Trên Windows có thể tạo thư mục tương ứng và copy exploded module com.acme.format.api bằng File Explorer hoặc PowerShell, sau đó dùng dấu chấm phẩy phân cách module path.

Không gọi test no-provider trên module path chứa cả provider modules rồi coi kết quả rỗng là đảm bảo. Module resolution và service binding có thể đưa provider vào boot layer. Fixture âm tính cần **thực sự cách ly** provider artifacts.

## 13. Test chỉ một provider

Ngoài test hai provider và test không có provider, có thể kiểm tra cấu hình chỉ một implementation.

Chuẩn bị fixture module path chỉ chứa API module và upper module; rồi chạy test dành riêng cho single-provider scenario. Với test này, Set kỳ vọng là:

~~~java
Set<String> expected = Set.of("upper");
~~~

Mục đích:

- Xác nhận consumer không cần biết provider reverse.
- Xác nhận module descriptor của upper đăng ký đúng service.
- Xác nhận behavior upper ổn định.
- Phát hiện dependency vô tình kéo thêm provider ngoài mong muốn.

Trong môi trường build nhiều profile, chẳng hạn test, staging và production, việc kiểm thử cùng service contract với các provider set khác nhau giúp phát hiện lỗi cấu hình phân phối trước khi deploy.

## 14. Provider method và cách kiểm thử

Trong named module, provider có thể được tạo từ **provider class** hoặc từ một static method tên provider của class được nêu trong mệnh đề provides.

Ví dụ module descriptor:

~~~java
module com.acme.format.special {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.special.FormatterFactory;
}
~~~

Provider method:

~~~java
package com.acme.format.special;

import com.acme.format.api.TextFormatter;

public final class FormatterFactory {

    private FormatterFactory() {
    }

    public static TextFormatter provider() {
        return new ConfiguredFormatter();
    }
}
~~~

Trong đó ConfiguredFormatter là implementation phù hợp của TextFormatter thuộc module provider. Khi test, cần bảo đảm:

- Module được phân giải vào layer cần kiểm thử.
- Mệnh đề provides đúng service type.
- Method provider có chữ ký hợp lệ và trả về instance phù hợp.
- Việc tạo provider không ném exception.
- Behavior của instance đáp ứng contract.

ServiceLoader.Provider.type() có thể biểu diễn type theo cơ chế cung cấp provider, nên nếu cần kiểm tra implementation thật, hãy kiểm tra instance nhận được từ Provider.get() thay vì giả định class được khai báo sau with luôn chính là runtime class của object.

## 15. Kiểm tra descriptor và metadata provides

Nếu ServiceLoader trả về kết quả rỗng, một bước chẩn đoán nhanh là kiểm tra module descriptor:

~~~bash
javap -v -p mods/com.acme.format.upper/module-info.class
~~~

Với modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.format.upper.jar
~~~

Những thông tin cần xem:

- Tên module có đúng com.acme.format.upper không?
- Có requires com.acme.format.api không?
- Có provides com.acme.format.api.TextFormatter with ... không?
- Provider class có tồn tại và đúng tên package không?

Kiểm tra descriptor của test module:

~~~bash
javap -v -p test-mods/com.acme.format.tests/module-info.class
~~~

Trong đó phải có uses com.acme.format.api.TextFormatter. Nếu test module thiếu uses, việc gọi ServiceLoader từ named module có thể phát sinh ServiceConfigurationError.

Không nhầm **service contract có thể import** với **service đã được provider đăng ký**: requires/exports giúp truy cập type; uses/provides giúp mô tả quan hệ service.

## 16. ServiceLoader và service binding

Có hai bước khác nhau:

1. **Module resolution/service binding** quyết định provider modules nào được đưa vào module configuration.
2. **ServiceLoader** truy vấn layer/class loader và tạo instance của provider khi code duyệt service.

Khi tự tạo module layer, Configuration.resolve(...) phân giải roots và requires, còn Configuration.resolveAndBind(...) có thể bổ sung các module cung cấp service theo uses/provides.

Trong integration test dùng module layer động, nên xây dựng fixture theo cách tường minh và kiểm tra danh sách module của configuration trước khi gọi ServiceLoader.load(layer, ServiceType.class).

Ví dụ truy vấn provider tại một layer được truyền vào:

~~~java
public static void verifyLayer(ModuleLayer layer) {
    ServiceLoader<TextFormatter> services =
            ServiceLoader.load(layer, TextFormatter.class);

    for (TextFormatter service : services) {
        System.out.println(
                service.name() + " -> "
                + service.getClass().getModule().getName()
        );
    }
}
~~~

Method trên là đoạn mã bên trong một class đang import TextFormatter, ServiceLoader và ModuleLayer. Nếu caller là named module, descriptor của caller cần có uses cho service type.

**Service binding không đồng nghĩa provider được khởi tạo.** Resolution chuẩn bị module graph; instance provider chỉ được tạo khi ServiceLoader thực sự yêu cầu.

## 17. Test provider load thất bại

Một provider cấu hình sai có thể gây **ServiceConfigurationError** khi ServiceLoader phát hiện hoặc khởi tạo provider.

Các trường hợp cần test âm tính:

- Provider module khai báo tên class sau with không tồn tại.
- Implementation không thực hiện service contract.
- Constructor hoặc provider method ném exception.
- Provider method trả về null hoặc type không phù hợp.
- Dependency runtime của provider bị thiếu.
- Service type bị nạp thành hai bản Class khác nhau qua các class loader.

Trong named module, nhiều lỗi mô tả provider không hợp lệ có thể được phát hiện ngay khi biên dịch descriptor/provider. Để tạo fixture lỗi runtime, cần kiểm soát cách đóng gói hoặc điều kiện runtime, không nên cố tình đưa source không biên dịch được vào test bình thường.

Consumer có thể xử lý theo chính sách:

~~~java
try {
    for (TextFormatter formatter :
            ServiceLoader.load(TextFormatter.class)) {
        System.out.println(formatter.name());
    }
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException(
            "Service provider configuration failed", error
    );
}
~~~

Lỗi provider không nên bị nuốt hoàn toàn nếu tính năng yêu cầu service bắt buộc. Ghi rõ module, provider name và cause giúp chẩn đoán.

## 18. Không kiểm tra provider theo thứ tự

Một sai lầm phổ biến:

~~~java
TextFormatter first = ServiceLoader
        .load(TextFormatter.class)
        .iterator()
        .next();

assert "upper".equals(first.name());
~~~

Đoạn này phụ thuộc thứ tự provider và giả định luôn có ít nhất một provider. Thứ tự có thể thay đổi khi module path, packaging hoặc layer thay đổi.

Cách phù hợp hơn:

- Thu thập provider theo một key ổn định.
- Kiểm tra tập key tìm được.
- Phát hiện trùng key khi contract yêu cầu duy nhất.
- Kiểm tra từng behavior thông qua interface.
- Nếu nghiệp vụ có thứ tự ưu tiên, định nghĩa policy riêng thay vì dựa trên thứ tự ServiceLoader.

Ví dụ có thể dùng Map<String, TextFormatter> hoặc Set<String>. Với provider bắt buộc, báo lỗi rõ ràng khi Set rỗng thay vì gọi next() mù.

## 19. Test với JUnit và framework runner

Khi chuyển sang JUnit 5, các assertion ở ví dụ trên có thể được viết bằng @Test và Assertions.

Ví dụ:

~~~java
@Test
void discoversExpectedProviders() {
    Set<String> names = new HashSet<>();

    ServiceLoader.load(
            ModuleLayer.boot(),
            TextFormatter.class
    ).forEach(provider -> names.add(provider.name()));

    assertEquals(Set.of("upper", "reverse"), names);
}
~~~

Đây là phần thân test method; cần import Test, HashSet, Set, ServiceLoader, TextFormatter và assertEquals. Tên module JUnit API thường là org.junit.jupiter.api, nhưng cấu hình engine/launcher và module path phụ thuộc phiên bản JUnit và build tool.

Với named test module, descriptor cần requires những test framework modules mà code import, đồng thời có thể cần qualified opens nếu runner thực hiện deep reflection. Nếu test được patch vào production module, có thể cần --add-reads/--add-opens trong cấu hình test riêng.

Không thêm dependency JUnit vào production module-info.java chỉ để chạy test nếu nó không phải dependency runtime thực sự của ứng dụng.

## 20. TCCL và ServiceLoader.load(service)

Có hai cách gọi đáng phân biệt:

~~~java
ServiceLoader<TextFormatter> viaContextLoader =
        ServiceLoader.load(TextFormatter.class);

ServiceLoader<TextFormatter> viaLayer =
        ServiceLoader.load(
                ModuleLayer.boot(),
                TextFormatter.class
        );
~~~

Overload load(service) sử dụng thread context class loader (TCCL) và quy tắc provider discovery tương ứng. Trong ứng dụng container hoặc plugin, TCCL có thể khác giữa các thread.

Overload nhận ModuleLayer giúp test kiểm soát rõ layer được truy vấn. Tuy vậy, kết quả vẫn phụ thuộc provider modules nào đã được phân giải vào layer đó.

Khi test ServiceLoader trong thread pool:

- Không giả định TCCL của worker giống thread tạo test nếu framework không cam kết.
- Nếu thay đổi TCCL, khôi phục giá trị cũ trong finally.
- Không chia sẻ cùng một ServiceLoader cho nhiều thread nếu không có đồng bộ phù hợp.
- Dùng layer tường minh khi bài kiểm thử nhằm xác nhận service registry của một module layer cụ thể.

## 21. Những lỗi thường gặp

**Không thấy provider dù JAR nằm trên module path**

Module provider có thể chưa được phân giải vào layer đang truy vấn. Dùng --add-modules cho fixture xác định, hoặc kiểm tra service binding/module layer theo cách ứng dụng tạo configuration.

**Consumer không khai báo uses**

Named module gọi ServiceLoader nhưng thiếu uses cho service type. Bổ sung uses trong module-info.java của consumer/test module.

**Provider không khai báo provides**

Implementation class có mặt không đủ. Named provider module phải khai báo provides ... with ... hợp lệ.

**Package chứa implementation không được export**

Điều này thường **không phải lỗi**. ServiceLoader không yêu cầu export provider implementation package chỉ để tạo service. Chỉ export package API chứa service contract khi consumer/provider cần import.

**Provider có nhiều bản service interface**

Nếu hai class loader định nghĩa riêng một service interface cùng tên, provider có thể không được xem là subtype đúng. Dùng chung API module/class loader để đảm bảo type identity.

**Test chỉ kiểm tra có ít nhất một provider**

Bài test như vậy có thể vượt qua dù thiếu provider quan trọng. Hãy kiểm tra tập provider mong đợi nếu test fixture xác định chính xác module set.

**No-provider test vẫn thấy implementation**

Có thể provider module đang nằm trong boot layer do root configuration hoặc service binding. Tạo module path fixture chỉ gồm API và test, không đưa provider artifacts vào.

**ServiceConfigurationError**

Kiểm tra descriptor, provider factory/constructor, dependency runtime và cause. Một provider lỗi có thể khiến iteration thất bại trước khi test thu thập hết các implementation.

**Test chạy với classpath khác module path**

META-INF/services của classpath và provides trong named module là hai cơ chế đăng ký khác nhau. Hãy xác nhận cách đóng gói của từng dependency và loader/layer mà ServiceLoader thực sự sử dụng.

## 22. Quy trình thực hành

1. Tạo service API trong một named module riêng và export package chứa service type.
2. Tạo ít nhất một provider module với requires API và provides ... with ....
3. Tạo named test module với requires API và uses service type.
4. Biên dịch production modules bằng javac --module-source-path.
5. Biên dịch test module với --module-path trỏ tới production artifacts.
6. Chạy test với module path chứa đúng fixture; dùng --add-modules để đưa provider modules mong muốn vào boot layer khi cần tính xác định.
7. Truy vấn ServiceLoader.load(ModuleLayer.boot(), ServiceType.class) hoặc load(layer, ...) nếu có layer riêng.
8. Kiểm tra provider identity, module name và behavior, không dựa vào thứ tự iteration.
9. Chuẩn bị fixture âm tính không có provider và kiểm tra kết quả rỗng.
10. Khi test thất bại, kiểm tra module-info.class, module resolution và module path trước khi sửa source implementation.

## 23. Ghi nhớ

- ServiceLoader chỉ tìm provider đã được đăng ký và có mặt trong phạm vi layer/class loader được truy vấn.
- Consumer named module khai báo uses; provider named module khai báo provides ... with ....
- Provider không cần export package implementation chỉ để được ServiceLoader khởi tạo.
- Test named module có thể chỉ requires service API, không requires provider modules.
- Module path chứa một artifact không đồng nghĩa module đó chắc chắn thuộc resolved module graph.
- --add-modules hữu ích để cố định provider set trong integration test.
- Test nên kiểm tra tập provider và behavior, không giả định thứ tự ServiceLoader.
- Test không có provider cần môi trường module path/layer thực sự không chứa provider.
- ServiceConfigurationError chỉ ra lỗi discovery/initialization, không nhất thiết là lỗi business method.
- Với plugin layer tự tạo, dùng ServiceLoader.load(layer, service) để kiểm tra đúng layer.
- TCCL tác động tới load(service); kiểm soát TCCL khi test chạy trên nhiều thread.
- Không đưa test dependency hoặc quyền reflective access rộng vào production descriptor nếu không cần.

**Kết luận:** Test ServiceLoader trong JPMS phải xác minh cả metadata **uses/provides**, module resolution, phạm vi provider discovery và behavior của implementation. Một test module độc lập dùng service API, provider fixture xác định và các assertion không phụ thuộc thứ tự sẽ giúp phát hiện lỗi đóng gói và cấu hình trước khi ứng dụng chạy thực tế.