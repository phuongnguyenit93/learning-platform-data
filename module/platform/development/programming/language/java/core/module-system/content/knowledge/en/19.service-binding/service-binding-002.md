# resolveAndBind và khác biệt với resolve

## 1. Bối cảnh: module resolution và service binding

Java Platform Module System (JPMS) cần xây dựng một **module graph** trước khi tạo module layer và chạy ứng dụng. Bắt đầu từ một hoặc nhiều root module, bộ phân giải tìm các module mà root yêu cầu trực tiếp hoặc gián tiếp thông qua directive `requires`. Quá trình này gọi là **module resolution**.

Trong ứng dụng có dùng Service Provider Interface (SPI), một module có thể khai báo `uses` để tiêu thụ một service, trong khi module khác khai báo `provides ... with ...` để cung cấp implementation. Provider có thể không xuất hiện trong chuỗi `requires` của consumer. Nếu chỉ giải quyết các dependency thông thường, module provider có thể không được đưa vào module graph.

JPMS cung cấp hai phương thức trên `Configuration` để lựa chọn cách giải quyết:

- `resolve(...)`: giải quyết root modules và dependency theo `requires`.
- `resolveAndBind(...)`: thực hiện resolution như trên, đồng thời chạy **service binding** để bổ sung các module cung cấp service mà module trong graph khai báo `uses`.

Service binding giải quyết tình huống consumer cần một dịch vụ nhưng không nên phụ thuộc trực tiếp vào module triển khai dịch vụ đó.

## 2. Ví dụ về ba module

Giả sử có ba module:

- `com.acme.spi`: định nghĩa service interface `Formatter`.
- `com.acme.app`: ứng dụng consumer, sử dụng `Formatter`.
- `com.acme.provider.json`: provider cung cấp implementation `JsonFormatter`.

Service contract trong SPI:

```java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
```

Module descriptor của SPI:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Module descriptor của consumer:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

Consumer phụ thuộc vào SPI để tham chiếu interface và khai báo `uses` để thông báo rằng nó cần tìm các provider của service type này.

Implementation trong provider:

```java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
```

Module descriptor của provider:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Provider phụ thuộc vào SPI để triển khai contract và khai báo `provides` để đăng ký implementation. Consumer không khai báo `requires com.acme.provider.json`; đây chính là điểm giúp provider có thể được thay thế hoặc bổ sung độc lập.

## 3. Khác biệt giữa resolve và resolveAndBind

Cả hai phương thức đều bắt đầu từ root modules, tìm các module cần thiết theo `requires`, kiểm tra tính nhất quán của module graph và trả về một `Configuration` mới.

| Nội dung | `resolve(...)` | `resolveAndBind(...)` |
|---|---|---|
| Giải quyết root modules | Có | Có |
| Giải quyết dependency `requires` | Có | Có |
| Xét directive `uses` để tìm provider | Không thực hiện service binding | Có |
| Bổ sung module provider phù hợp vào graph | Không tự bổ sung chỉ vì có `provides` | Có, nếu provider quan sát được trong quá trình resolution |
| Phù hợp với | Graph chỉ cần dependency tường minh | Ứng dụng cần tự động liên kết các SPI provider |

Giả sử root là `com.acme.app` và các module được đặt trong cùng một module finder:

**Với `resolve(...)`:**

- Root `com.acme.app` được đưa vào graph.
- `com.acme.spi` được đưa vào graph vì consumer khai báo `requires com.acme.spi`.
- `com.acme.provider.json` không được thêm chỉ vì nó có `provides com.acme.spi.Formatter`.

**Với `resolveAndBind(...)`:**

- Các bước resolution thông thường vẫn diễn ra.
- Bộ phân giải thấy `com.acme.app` khai báo `uses com.acme.spi.Formatter`.
- Nếu tìm thấy provider module phù hợp và quan sát được, nó bổ sung `com.acme.provider.json` vào graph.
- Dependency của provider cũng được giải quyết. Nếu module mới được thêm lại khai báo `uses` service khác, service binding tiếp tục xét các service đó cho đến khi không còn module phù hợp cần thêm.

Vì vậy, `resolveAndBind` có thể tạo graph lớn hơn `resolve`. Kích thước graph thực tế phụ thuộc vào root modules, dependency, các directive service và những module mà các finder/parent configurations cung cấp cho bộ phân giải.

## 4. Ví dụ gọi hai phương thức Configuration

Có thể so sánh trực tiếp hai configuration trong code:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Set;

public class ResolutionExample {
    private static void printModules(String title,
                                     java.lang.module.Configuration config) {
        System.out.println(title);
        config.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .forEach(name -> System.out.println("  " + name));
    }

    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        java.lang.module.Configuration parent =
                ModuleLayer.boot().configuration();

        Set<String> roots = Set.of("com.acme.app");

        java.lang.module.Configuration normal =
                parent.resolve(finder, ModuleFinder.of(), roots);

        java.lang.module.Configuration bound =
                parent.resolveAndBind(finder, ModuleFinder.of(), roots);

        printModules("resolve:", normal);
        printModules("resolveAndBind:", bound);
    }
}
```

Trong ví dụ:

- `ModuleFinder.of(Path.of("mods"))` tìm các module có trong thư mục `mods`, gồm ứng dụng, SPI và provider.
- `ModuleLayer.boot().configuration()` cung cấp configuration của boot layer làm parent.
- `Set.of("com.acme.app")` chỉ định root module.
- `ModuleFinder.of()` là finder rỗng cho tham số finder còn lại.
- `Configuration.modules()` trả về các module thuộc configuration mới; các module đã có trong parent configuration không được tính vào tập này.

Kết quả minh họa nếu provider chỉ được liên kết thông qua SPI:

```text
resolve:
  com.acme.app
  com.acme.spi

resolveAndBind:
  com.acme.app
  com.acme.provider.json
  com.acme.spi
```

Danh sách thực tế phụ thuộc vào nội dung thư mục module và các dependency khác. Có thể thêm module khác vào thư mục `mods` để quan sát cách service binding bổ sung provider tương ứng.

Hai phương thức là instance method của `Configuration`. Các tham số `before` và `after` là `ModuleFinder` tham gia tìm module trong quá trình resolution; khi thiết kế custom configuration, cần bảo đảm các module ứng dụng và provider nằm trong phạm vi mà các finder/parent configurations có thể quan sát.

## 5. Service binding không phải là khởi tạo provider

Một điểm quan trọng là `resolveAndBind` chỉ xây dựng configuration có chứa các module provider phù hợp. Nó **không gọi constructor provider, không chạy implementation và không tự tạo đối tượng service**.

Quy trình đầy đủ có các giai đoạn riêng:

1. Module descriptor khai báo `uses` và `provides`.
2. `resolveAndBind` giải quyết dependency và bổ sung provider module vào configuration.
3. Ứng dụng tạo `ModuleLayer` từ configuration.
4. Consumer dùng `ServiceLoader` để lấy các implementation trong layer và gọi hành vi của service.

Ví dụ phía consumer:

```java
import com.acme.spi.Formatter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Formatter> loaders =
                ServiceLoader.load(Formatter.class);

        for (Formatter formatter : loaders) {
            System.out.println(formatter.format("Java modules"));
        }
    }
}
```

Nếu provider đã nằm trong layer mà consumer sử dụng, `ServiceLoader` có thể tìm implementation đó. Nếu provider không được đưa vào layer, `ServiceLoader` không thể nạp nó từ layer đó chỉ vì một module khác có khai báo `provides` ở nơi khác.

Với một custom `ModuleLayer`, có thể dùng overload `ServiceLoader.load(layer, Formatter.class)` để chỉ rõ layer cần tìm provider. Việc tạo layer và việc nạp provider là các thao tác riêng biệt với resolution.

## 6. resolve vẫn có thể dùng ServiceLoader

Không nên hiểu rằng gọi `resolve` sẽ vô hiệu hóa SPI hoặc khiến `ServiceLoader` không hoạt động.

Nếu provider đã được đưa vào graph bằng một cách khác, chẳng hạn:

- Provider được chỉ định trực tiếp như một root module.
- Một module trong graph khai báo `requires` provider.
- Provider đã nằm trong parent layer phù hợp.

thì consumer vẫn có thể dùng `ServiceLoader` để tìm provider đó. Khác biệt là `resolve` không tự mở rộng graph để tìm provider chỉ dựa trên quan hệ `uses`/`provides`.

Ngược lại, `resolveAndBind` cũng không thể tìm provider nằm ngoài phạm vi quan sát của các `ModuleFinder` và parent configurations. Đặt JAR ở một thư mục bất kỳ trên máy không có nghĩa resolver tự động tìm thấy nó; module cần nằm trong nguồn tìm kiếm được cung cấp cho resolution.

## 7. Nhiều provider và service binding lặp

Một service có thể có nhiều provider. Nếu nhiều provider module phù hợp cùng có thể quan sát được, service binding có thể đưa nhiều module đó vào configuration. `resolveAndBind` không phải cơ chế chọn một provider duy nhất và cũng không xác định thứ tự ưu tiên nghiệp vụ cho ứng dụng.

Ví dụ có thêm:

```java
module com.acme.provider.xml {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.xml.XmlFormatter;
}
```

Khi cả hai provider module đều có thể được resolver quan sát, configuration được tạo bằng `resolveAndBind` có thể chứa cả `com.acme.provider.json` và `com.acme.provider.xml`.

Consumer cần tự quyết định cách sử dụng nhiều implementation: chạy tất cả, lọc theo metadata/cấu hình, chọn theo loại dữ liệu, hoặc báo lỗi nếu có nhiều lựa chọn trong khi chỉ mong đợi một provider. Không nên dựa vào thứ tự duyệt của `ServiceLoader` như một quy tắc ưu tiên ổn định.

Service binding có tính lan truyền: provider được thêm vào graph cũng có thể có dependency `requires` và directive `uses` riêng. Resolver tiếp tục xử lý các dependency và service liên quan cho đến khi đạt trạng thái ổn định.

## 8. Những giới hạn và lỗi cần kiểm tra

| Hiện tượng | Cách kiểm tra |
|---|---|
| `resolveAndBind` không đưa provider vào graph | Kiểm tra consumer có `uses` đúng service type; provider có `provides` đúng type; provider có nằm trong finder hoặc parent configuration có thể quan sát không |
| Provider không biên dịch | Kiểm tra `requires` tới SPI và package chứa service interface đã được export |
| `ServiceLoader` không trả về provider | Kiểm tra provider có thực sự nằm trong layer được tìm kiếm và consumer module đã khai báo `uses` |
| Configuration báo thiếu dependency | Kiểm tra các directive `requires` của root và của provider module, cũng như các finder được truyền vào |
| Có nhiều provider hơn dự kiến | Kiểm tra toàn bộ module có khai báo `provides` cho service type và quy tắc lựa chọn của consumer |

Nếu consumer là named module, directive `uses` là một phần của module descriptor. Gọi `ServiceLoader.load` từ module không khai báo sử dụng service tương ứng có thể gây `ServiceConfigurationError`.

Service binding của JPMS làm việc với module graph. Ứng dụng classpath/unnamed module có thể sử dụng cơ chế đăng ký truyền thống qua `META-INF/services`, nhưng đó không phải là việc `Configuration.resolveAndBind` quét toàn bộ classpath.

## 9. Chọn phương thức nào?

Dùng `resolve` khi module graph được xác định bởi các root và dependency `requires`, và ứng dụng chủ động kiểm soát provider bằng cách khác.

Dùng `resolveAndBind` khi ứng dụng muốn JPMS tự bổ sung các module cung cấp service cho những module đã khai báo `uses`. Đây là lựa chọn phù hợp cho hệ thống plugin hoặc kiến trúc SPI, nơi consumer phụ thuộc vào contract còn provider có thể được thêm độc lập.

Trước khi chọn, hãy xác định rõ:

- Các provider có được đặt trong module finder hoặc parent layer mà resolver quan sát không?
- Consumer đã khai báo đúng `uses` chưa?
- Provider đã khai báo đúng `provides ... with ...` chưa?
- Ứng dụng có chấp nhận nhiều provider hay cần một chính sách lựa chọn cụ thể?
- Bạn đang cần xây dựng configuration, tạo layer, hay thực sự nạp và gọi implementation? Đây là các bước khác nhau.

## Ghi nhớ

- `resolve` giải quyết root modules và dependency `requires`.
- `resolveAndBind` làm các bước đó rồi bổ sung provider module phù hợp theo quan hệ `uses`/`provides`.
- Provider chỉ được tìm thấy nếu nó nằm trong phạm vi module mà resolver có thể quan sát.
- Service binding xây dựng module graph; nó không tự khởi tạo provider.
- `ServiceLoader` thực hiện việc tìm và nạp implementation khi ứng dụng sử dụng service.
- `resolve` vẫn dùng được với `ServiceLoader` nếu provider đã có trong layer bằng một cách khác.
