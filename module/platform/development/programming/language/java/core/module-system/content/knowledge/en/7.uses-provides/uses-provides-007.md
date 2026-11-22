# Provider nhiều implementation và thứ tự

Java Platform Module System (JPMS) tích hợp cơ chế service provider để một module công bố implementation của một service, còn module khác sử dụng service mà không cần phụ thuộc trực tiếp vào từng class triển khai. Cơ chế này thường được gọi qua `ServiceLoader`.

Một service có thể có một implementation hoặc nhiều implementation. Nhiều provider có thể được khai báo trong cùng một module, hoặc được cung cấp từ nhiều module khác nhau. Khi có nhiều provider, ứng dụng cần hiểu cách Java khám phá chúng và tự định nghĩa chính sách chọn provider phù hợp.

Điểm quan trọng là **module descriptor khai báo provider nào tồn tại; nó không phải nơi định nghĩa thứ tự ưu tiên nghiệp vụ**. Nếu ứng dụng cần chọn implementation mặc định, hãy biểu diễn tiêu chí đó bằng API hoặc cấu hình rõ ràng.

## 1. Service, consumer và provider

Giả sử ứng dụng cần chuyển đổi dữ liệu sang nhiều định dạng. Ta định nghĩa một service interface:

~~~java
package com.example.format.spi;

public interface Formatter {
    String format(String input);
}
~~~

Interface `Formatter` là hợp đồng mà các implementation phải tuân theo. Module chứa API service có thể khai báo:

~~~java
module com.example.format.api {
    exports com.example.format.spi;
}
~~~

Module consumer sử dụng service bằng directive `uses`:

~~~java
module com.example.app {
    requires com.example.format.api;

    uses com.example.format.spi.Formatter;
}
~~~

Directive `uses` nói rằng module ứng dụng cần tìm các provider của `Formatter`. Nó không chỉ rõ implementation cụ thể và cũng không tạo dependency trực tiếp tới module provider.

Một provider module khai báo implementation bằng `provides ... with ...`:

~~~java
module com.example.format.json {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.json.JsonFormatter;
}
~~~

Class triển khai:

~~~java
package com.example.format.json;

import com.example.format.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
~~~

Provider class cần đáp ứng quy tắc của service provider, chẳng hạn có public no-argument constructor như ví dụ trên. JPMS cũng hỗ trợ provider method theo quy tắc của `ServiceLoader`; khi sử dụng cách đó, class được nêu sau `with` cung cấp phương thức static `provider()` trả về service type.

Consumer không cần import hoặc gọi trực tiếp `JsonFormatter`. Nó chỉ làm việc với interface `Formatter`.

## 2. Nhiều provider trong cùng một module

Một module có thể cung cấp nhiều implementation cho cùng một service. Liệt kê nhiều provider class trong cùng directive `provides`, phân cách bằng dấu phẩy:

~~~java
module com.example.format.builtin {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter with
        com.example.format.builtin.JsonFormatter,
        com.example.format.builtin.XmlFormatter,
        com.example.format.builtin.TextFormatter;
}
~~~

Ba class trên đều phải thực hiện hợp đồng `Formatter` và đáp ứng quy tắc provider của Java.

Cấu trúc source có thể như sau:

~~~text
com.example.format.builtin/
├── module-info.java
└── com/example/format/builtin/
    ├── JsonFormatter.java
    ├── XmlFormatter.java
    └── TextFormatter.java
~~~

Package chứa implementation không cần được export chỉ để `ServiceLoader` khám phá provider đã khai báo trong descriptor. Module vẫn có thể giữ các class triển khai bên trong package nội bộ, chỉ công bố service interface từ module API.

Nhiều provider trong một module hữu ích khi các implementation được phát hành, kiểm thử và quản lý cùng một đơn vị triển khai.

## 3. Nhiều module cùng cung cấp một service

Một service cũng có thể được mở rộng bằng các provider module độc lập. Ví dụ:

~~~text
application
    │
    ├── com.example.format.api
    │
    ├── com.example.format.json
    │
    ├── com.example.format.xml
    │
    └── com.example.format.csv
~~~

Mỗi module provider có descriptor riêng:

~~~java
// module com.example.format.json
module com.example.format.json {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.json.JsonFormatter;
}
~~~

~~~java
// module com.example.format.xml
module com.example.format.xml {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.xml.XmlFormatter;
}
~~~

~~~java
// module com.example.format.csv
module com.example.format.csv {
    requires com.example.format.api;

    provides com.example.format.spi.Formatter
        with com.example.format.csv.CsvFormatter;
}
~~~

Consumer chỉ cần biết module API:

~~~java
module com.example.app {
    requires com.example.format.api;

    uses com.example.format.spi.Formatter;
}
~~~

Các module provider được đưa vào module path và module graph phù hợp. Khi service loader tìm provider trong module layer, nó có thể khám phá các provider được khai báo bởi các module trong layer đó.

Cách tổ chức này cho phép bổ sung một định dạng mới bằng cách thêm provider module mà không buộc consumer thay đổi dependency trực tiếp tới class triển khai. Consumer vẫn cần module API và cấu hình triển khai cần đưa provider module vào môi trường chạy.

## 4. Khám phá provider bằng ServiceLoader

Consumer sử dụng `ServiceLoader` để tìm các implementation:

~~~java
package com.example.app;

import com.example.format.spi.Formatter;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loader =
            ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loader) {
            System.out.println(formatter.format("hello"));
        }
    }
}
~~~

`ServiceLoader.load(Formatter.class)` tạo service loader cho service type. Việc tìm và khởi tạo provider diễn ra lười (lazy): provider được khám phá và khởi tạo khi ứng dụng duyệt iterator hoặc yêu cầu instance.

Một số điểm cần nhớ:

- Consumer khai báo `uses Formatter` trong module descriptor.
- Provider module khai báo `provides Formatter with ...`.
- Consumer chỉ phụ thuộc vào service API, không cần `requires` từng provider module.
- Provider được tạo khi được yêu cầu; không nên giả định tất cả provider đã được khởi tạo ngay lúc tạo `ServiceLoader`.
- Một `ServiceLoader` lưu cache những provider đã tải. Có thể gọi `reload()` để xóa cache và cho phép tìm lại provider.
- `ServiceLoader` không được thiết kế để nhiều thread cùng sửa hoặc duyệt một instance một cách không đồng bộ; nếu cần dùng đồng thời, hãy quản lý việc tạo và chia sẻ instance phù hợp.

Nếu ứng dụng dùng custom `ModuleLayer` cho plugin, có thể tìm service trong layer cụ thể:

~~~java
ServiceLoader<Formatter> loader =
    ServiceLoader.load(pluginLayer, Formatter.class);
~~~

Cách này hữu ích khi plugin được nạp vào module layer riêng. `ServiceLoader.load(Formatter.class)` và `ServiceLoader.load(layer, Formatter.class)` có phạm vi tìm provider khác nhau; hãy chọn đúng layer chứa các provider cần sử dụng.

Với provider trên classpath theo cơ chế cũ, Java có thể đọc file cấu hình `META-INF/services/<tên-service>`. Trong named module, cách khai báo tiêu chuẩn là directive `provides` trong `module-info.java`.

## 5. Thứ tự khám phá không phải thứ tự ưu tiên

Khi có nhiều provider, vòng lặp sau có thể trả về nhiều implementation:

~~~java
for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
    // xử lý từng provider
}
~~~

Tuy nhiên, không nên dùng provider xuất hiện đầu tiên như một quy tắc chọn implementation mặc định nếu ứng dụng chưa định nghĩa chính sách đó.

Module descriptor không có thuộc tính như `priority = 1` cho directive `provides`. Danh sách class sau `with` chỉ khai báo các provider của service; thứ tự khai báo hoặc thứ tự khám phá không phải hợp đồng ưu tiên nghiệp vụ mà ứng dụng nên dựa vào.

Ví dụ, nếu ứng dụng cần chọn JSON formatter làm mặc định, đừng dựa vào việc `JsonFormatter` tình cờ được trả về đầu tiên. Hãy biểu diễn ưu tiên trong service API, metadata hoặc cấu hình ứng dụng.

Có ba tình huống cần phân biệt:

1. **Duyệt tất cả provider:** thứ tự không quan trọng nếu mọi implementation đều được xử lý độc lập.
2. **Chọn một provider:** cần chính sách chọn rõ ràng, ví dụ cấu hình tên provider hoặc mức ưu tiên.
3. **Chạy nhiều provider theo pipeline:** cần định nghĩa thứ tự pipeline trong ứng dụng, không suy ra thứ tự từ descriptor.

## 6. Định nghĩa priority trong service API

Nếu ứng dụng cần xếp hạng provider, có thể thêm phương thức ưu tiên vào service interface:

~~~java
package com.example.format.spi;

public interface Formatter {
    String format(String input);

    // Số nhỏ hơn có mức ưu tiên cao hơn.
    default int priority() {
        return 100;
    }
}
~~~

Provider có thể override mức ưu tiên:

~~~java
public final class JsonFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }

    @Override
    public int priority() {
        return 10;
    }
}
~~~

~~~java
public final class XmlFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "<value>" + input + "</value>";
    }

    @Override
    public int priority() {
        return 20;
    }
}
~~~

Consumer có thể lấy provider rồi sắp xếp theo policy:

~~~java
List<Formatter> formatters =
    ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .sorted(
            Comparator.comparingInt(Formatter::priority)
                .thenComparing(p -> p.getClass().getName())
        )
        .toList();
~~~

Trong ví dụ này:

- Priority nhỏ hơn đứng trước.
- Nếu hai provider có cùng priority, tên class là tiêu chí phụ để thứ tự kết quả ổn định.
- `Provider::get` khởi tạo instance; việc sắp xếp theo phương thức instance vì vậy sẽ tải các provider được duyệt.

Nếu thứ tự tên class không có ý nghĩa với sản phẩm, có thể thay tie-breaker bằng quy tắc nghiệp vụ khác hoặc từ chối trường hợp trùng priority. Ví dụ, ứng dụng yêu cầu chỉ có một provider ở mức ưu tiên cao nhất:

~~~java
List<Formatter> candidates =
    ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .toList();

Formatter selected = candidates.stream()
    .min(Comparator.comparingInt(Formatter::priority))
    .orElseThrow(() ->
        new IllegalStateException("No Formatter provider is available"));
~~~

Đoạn code này chọn provider có priority nhỏ nhất. Nếu nhiều provider cùng mức ưu tiên nhỏ nhất, `min` sẽ trả về một phần tử theo thứ tự duyệt hiện tại. Nếu tie là lỗi cấu hình, ứng dụng nên kiểm tra và báo lỗi khi có nhiều ứng viên cùng mức ưu tiên tốt nhất, thay vì chấp nhận kết quả phụ thuộc thứ tự khám phá.

## 7. Chọn provider bằng cấu hình

Không phải service nào cũng cần priority được mã hóa trong interface. Có thể để ứng dụng cấu hình provider mong muốn.

Ví dụ file cấu hình:

~~~properties
formatter.default=com.example.format.json.JsonFormatter
~~~

Consumer có thể lấy danh sách provider rồi chọn theo class name:

~~~java
String configuredName =
    System.getProperty("formatter.default");

Formatter selected = ServiceLoader.load(Formatter.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(provider ->
        provider.getClass().getName().equals(configuredName))
    .findFirst()
    .orElseThrow(() ->
        new IllegalStateException(
            "Configured Formatter provider was not found: "
                + configuredName));
~~~

Trong hệ thống thực tế, nên đọc cấu hình từ nguồn cấu hình mà ứng dụng đang sử dụng, xác thực giá trị và báo lỗi rõ ràng nếu provider không tồn tại. Class name là một lựa chọn cấu hình đơn giản; hệ thống lớn có thể dùng provider id ổn định do service interface công bố để tránh phụ thuộc tên class.

Có thể chọn provider theo:

- ID ổn định do provider trả về.
- Mức ưu tiên hoặc capability.
- Định dạng đầu vào/đầu ra mà provider hỗ trợ.
- Cấu hình môi trường hoặc tenant.
- Quy tắc fallback khi provider chính không sẵn sàng.

Chính sách cần xác định rõ trường hợp không có provider, nhiều provider phù hợp hoặc provider bị lỗi khi khởi tạo.

## 8. ServiceLoader.Provider và stream

Ngoài iterator, `ServiceLoader` cung cấp `stream()` để truy cập các đối tượng mô tả provider:

~~~java
ServiceLoader<Formatter> loader =
    ServiceLoader.load(Formatter.class);

loader.stream().forEach(provider -> {
    Class<? extends Formatter> providerType = provider.type();
    System.out.println(providerType.getName());
});
~~~

`ServiceLoader.Provider` cho phép xem kiểu provider trước khi yêu cầu instance bằng `get()`. Điều này hữu ích khi ứng dụng cần lọc metadata hoặc kiểm tra class trước khi khởi tạo.

Ví dụ lọc provider theo annotation tùy biến:

~~~java
loader.stream()
    .filter(provider ->
        provider.type().isAnnotationPresent(PreferredFormatter.class))
    .map(ServiceLoader.Provider::get)
    .forEach(formatter ->
        System.out.println(formatter.format("hello")));
~~~

Annotation và quy tắc lọc là cơ chế do ứng dụng tự định nghĩa. JPMS không tự hiểu annotation `PreferredFormatter` và cũng không tự chọn provider được đánh dấu. Nếu dùng metadata, hãy duy trì contract rõ ràng và kiểm tra trường hợp không có hoặc có nhiều provider cùng được đánh dấu.

Lưu ý rằng `stream()` không có nghĩa mọi thao tác đều miễn phí: khi gọi `Provider.get()`, provider được khởi tạo. Nếu chỉ cần xem type, có thể sử dụng `Provider.type()` trước khi quyết định khởi tạo.

## 9. Lỗi thường gặp khi có nhiều provider

**Consumer quên khai báo `uses`.** Module consumer cần khai báo service type trong descriptor. Nếu thiếu, việc sử dụng service trong named module có thể thất bại khi service loader kiểm tra quyền sử dụng.

**Provider module không nằm trong module layer đang tìm kiếm.** Descriptor có `provides` đúng nhưng module provider chưa được đưa vào module path hoặc custom layer tương ứng. Hãy kiểm tra cấu hình runtime và layer được truyền cho `ServiceLoader`.

**Provider class không đáp ứng quy tắc khởi tạo.** Kiểm tra class provider có public no-argument constructor phù hợp hoặc provider method hợp lệ hay không.

**Provider không triển khai đúng service.** Kiểm tra kiểu trả về của provider method hoặc quan hệ kế thừa/implements giữa implementation và service interface.

**Consumer phụ thuộc trực tiếp vào implementation.** Nếu consumer chỉ cần service, hãy để consumer phụ thuộc vào module API và khai báo `uses`. Dependency trực tiếp tới từng provider làm giảm tính mở rộng của SPI.

**Dựa vào thứ tự provider được trả về.** Nếu nghiệp vụ yêu cầu một implementation mặc định, hãy dùng priority hoặc cấu hình rõ ràng.

**Nhiều provider cùng priority nhưng ứng dụng không định nghĩa tie-breaker.** Kết quả lựa chọn có thể không ổn định hoặc không phản ánh mong muốn. Hãy chọn một quy tắc phụ hoặc báo lỗi khi có xung đột.

**Khởi tạo tất cả provider dù chỉ cần một.** `stream().map(Provider::get)` sẽ khởi tạo những provider được duyệt. Nếu có nhiều plugin nặng, hãy lọc metadata trước khi gọi `get()` khi có thể, hoặc thiết kế registry/lifecycle riêng.

## 10. Kiểm tra service provider trong modular JAR

Có thể kiểm tra descriptor của provider module sau khi đóng gói:

~~~bash
jar --describe-module --file build/libs/format-json.jar
~~~

Thông tin module cần thể hiện service được cung cấp, ví dụ:

~~~text
provides com.example.format.spi.Formatter
    with com.example.format.json.JsonFormatter
~~~

Với module chứa nhiều provider, phần `provides` cần liệt kê các implementation tương ứng.

Khi chạy, cần bảo đảm:

- Module API có mặt và được resolve.
- Consumer module khai báo `uses` đúng service type.
- Provider module được đưa vào module layer đang được tìm kiếm.
- Các dependency của provider cũng được resolve.
- Service interface và provider implementation tương thích cùng phiên bản.

Nếu sử dụng plugin layer, hãy kiểm tra layer được tạo ra có chứa các module provider dự kiến. Việc một modular JAR tồn tại trên đĩa không có nghĩa nó tự động được thêm vào mọi module layer.

## 11. Khi nào nên dùng nhiều provider?

Nhiều provider phù hợp khi một service có nhiều implementation thay thế được, chẳng hạn:

- Nhiều định dạng serializer/deserializer.
- Nhiều driver hoặc adapter cho hệ thống bên ngoài.
- Nhiều chiến lược lưu trữ.
- Nhiều bộ xử lý theo loại dữ liệu.
- Plugin được cài đặt độc lập theo môi trường triển khai.

Nếu các implementation không cùng thực hiện một hợp đồng ổn định hoặc có vòng đời hoàn toàn khác nhau, hãy cân nhắc thiết kế API service riêng thay vì gom tất cả vào một service interface quá rộng.

Service provider giúp giảm phụ thuộc trực tiếp giữa consumer và implementation. Khi có nhiều provider, trách nhiệm chọn một provider hoặc điều phối nhiều provider thuộc về chính sách của ứng dụng. Module descriptor chỉ khai báo quan hệ service; nó không thay thế registry, cấu hình hoặc quy tắc ưu tiên của sản phẩm.

## 12. Tự kiểm tra

Khi thiết kế service có nhiều implementation, hãy trả lời:

1. Service interface nằm trong module API nào và package đó đã được export chưa?
2. Consumer module đã khai báo `uses` đúng service type chưa?
3. Mỗi provider module đã khai báo `provides ... with ...` chưa?
4. Có nhiều provider trong cùng một module hay nhiều module provider độc lập?
5. Provider có constructor hoặc provider method hợp lệ không?
6. Runtime đang tìm trong boot layer hay custom module layer nào?
7. Ứng dụng cần duyệt tất cả provider, chọn một provider hay chạy theo pipeline?
8. Nếu cần chọn một provider, priority, ID hoặc cấu hình nào quyết định kết quả?
9. Nếu hai provider có cùng mức ưu tiên hoặc không có provider, ứng dụng xử lý thế nào?

Khi phân biệt được khai báo provider, cơ chế khám phá của `ServiceLoader` và chính sách lựa chọn của ứng dụng, bạn có thể mở rộng hệ thống bằng nhiều implementation mà vẫn giữ consumer ít phụ thuộc và hành vi lựa chọn rõ ràng.
