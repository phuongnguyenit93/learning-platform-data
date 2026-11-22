# Khám phá dịch vụ bằng `ServiceLoader` trong hệ mô-đun Java

`ServiceLoader` là API chuẩn của Java để tìm và nạp các implementation của một dịch vụ (service) tại runtime. Trong JPMS, cơ chế này được tích hợp với module descriptor: module tiêu thụ khai báo `uses`, module cung cấp khai báo `provides ... with ...`. Nhờ vậy, ứng dụng có thể sử dụng một hợp đồng API chung mà không cần phụ thuộc trực tiếp vào từng module triển khai.

Mô hình này phù hợp với plugin, driver, bộ chuyển đổi định dạng, backend lưu trữ, bộ xử lý và các thành phần có thể thay thế. Module ứng dụng chỉ biết interface dịch vụ; module provider có thể được thêm, thay thế hoặc đóng gói riêng miễn là tuân thủ hợp đồng.

## 1. Các thành phần của một dịch vụ

Một thiết kế dịch vụ thường có ba vai trò:

1. **Service API:** interface hoặc abstract class công khai mô tả hợp đồng mà các implementation phải tuân theo.
2. **Service provider:** class triển khai hợp đồng và được đăng ký trong module descriptor.
3. **Service consumer:** module tìm provider và sử dụng thông qua API `ServiceLoader`.

Ví dụ với dịch vụ chào hỏi:

```text
com.acme.greeter.api
    └── com.acme.greeter.api.Greeter

com.acme.greeter.provider
    └── com.acme.greeter.provider.FriendlyGreeter

com.acme.app
    └── com.acme.app.Main
```

Module API định nghĩa kiểu `Greeter`. Module provider triển khai kiểu đó. Module ứng dụng chỉ phụ thuộc vào API và yêu cầu dịch vụ `Greeter`; nó không cần biết tên class `FriendlyGreeter`.

## 2. Khai báo consumer bằng `uses`

Module gọi `ServiceLoader` phải khai báo dịch vụ mà nó sử dụng trong `module-info.java`:

```java
module com.acme.app {
    requires com.acme.greeter.api;
    uses com.acme.greeter.api.Greeter;
}
```

`requires` tạo readability tới module chứa service type để consumer có thể biên dịch và tham chiếu `Greeter`. `uses` khai báo rằng module cần tìm implementation của service đó tại runtime.

Với named module, thiếu `uses` có thể khiến `ServiceLoader` báo `ServiceConfigurationError` khi cố tạo hoặc duyệt service loader. `uses` không thêm dependency trực tiếp tới module provider và cũng không tự làm provider trở thành một phần của module graph.

Một module có thể khai báo nhiều chỉ thị `uses`, mỗi chỉ thị cho một service type. Một service type cũng có thể được nhiều module consumer sử dụng.

## 3. Đăng ký provider bằng `provides ... with ...`

Module chứa implementation khai báo provider trong `module-info.java`:

```java
module com.acme.greeter.provider {
    requires com.acme.greeter.api;
    provides com.acme.greeter.api.Greeter
        with com.acme.greeter.provider.FriendlyGreeter;
}
```

Ý nghĩa:

- `requires com.acme.greeter.api` cho phép provider đọc và triển khai service interface.
- `provides` chỉ ra service type mà module cung cấp.
- `with` liệt kê một hoặc nhiều provider class trong module đó.

Provider class theo cách khai báo constructor phải là class `public` và có constructor không tham số `public`. Java cũng hỗ trợ provider method: provider class có thể khai báo một phương thức `public static` tên `provider`, không có tham số và trả về một implementation tương thích với service type. Cách này hữu ích khi việc tạo implementation cần factory hoặc khi kiểu triển khai không nên được tạo trực tiếp bởi consumer.

Package chứa provider class không bắt buộc phải `exports`. `ServiceLoader` có thể nạp provider đã được module descriptor đăng ký mà không biến package triển khai thành API công khai. Đây là cách giữ chi tiết implementation bên trong module.

## 4. Service API và provider class

Service type nên là hợp đồng nhỏ, ổn định, không phụ thuộc vào class triển khai cụ thể. Ví dụ:

```java
package com.acme.greeter.api;

public interface Greeter {
    String greet(String name);
}
```

Module API cần export package chứa interface để consumer và provider có thể đọc kiểu công khai:

```java
module com.acme.greeter.api {
    exports com.acme.greeter.api;
}
```

Provider triển khai hợp đồng:

```java
package com.acme.greeter.provider;

import com.acme.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Module provider chỉ cần `requires` API module và `provides` service. Không cần export package `com.acme.greeter.provider` nếu không có API công khai nào khác cần package này.

## 5. Tìm provider bằng `ServiceLoader`

Consumer có thể tìm provider đầu tiên như sau:

```java
package com.acme.app;

import com.acme.greeter.api.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader.load(Greeter.class)
                .findFirst()
                .ifPresentOrElse(
                        greeter -> System.out.println(greeter.greet("Ada")),
                        () -> System.out.println("No Greeter provider found"));
    }
}
```

`ServiceLoader.load(Greeter.class)` tạo loader cho service type. `findFirst()` tìm provider đầu tiên; kết quả là `Optional`, vì vậy chương trình phải quyết định hành vi khi không có provider.

Các cách duyệt khác:

```java
for (Greeter greeter : ServiceLoader.load(Greeter.class)) {
    System.out.println(greeter.greet("Ada"));
}
```

Hoặc dùng `stream()` để làm việc với metadata của provider trước khi tạo instance:

```java
ServiceLoader.load(Greeter.class)
        .stream()
        .forEach(provider -> {
            System.out.println(provider.type().getName());
            Greeter greeter = provider.get();
            System.out.println(greeter.greet("Ada"));
        });
```

`ServiceLoader` nạp và khởi tạo provider theo nhu cầu khi duyệt. `Provider.type()` cho phép xem kiểu provider trước khi gọi `Provider.get()` để tạo instance. Không nên giả định mọi provider đã được khởi tạo ngay khi gọi `ServiceLoader.load(...)`.

## 6. Cách JPMS tìm provider khi khởi chạy

Trong named module, provider được đăng ký bằng `provides` trong module descriptor. Khi module consumer là root và khai báo `uses`, quá trình phân giải module có service binding sẽ tìm các provider module phù hợp trên module path và đưa chúng vào module graph.

Vì thế, consumer không cần khai báo `requires com.acme.greeter.provider` chỉ để tìm service. Module provider có thể được bind vào graph do service binding, trong khi dependency trực tiếp của ứng dụng vẫn là service API.

Luồng khái niệm:

```text
com.acme.app
    | requires
    v
com.acme.greeter.api
    ^
    | requires
com.acme.greeter.provider

com.acme.app -- uses Greeter
com.acme.greeter.provider -- provides Greeter with FriendlyGreeter
```

Để quan sát resolver, có thể chạy:

```shell
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
```

Trong output, dòng tương tự `com.acme.app binds com.acme.greeter.provider` cho biết provider module được bind nhờ service binding. Output còn có thể chứa nhiều dòng bind của các service hệ thống do JDK cung cấp.

## 7. Ví dụ hoàn chỉnh với ba named module

Ví dụ sau gồm API, provider và ứng dụng. Provider package không được export; ứng dụng chỉ khai báo `requires` API cùng `uses` service.

Cấu trúc source:

```text
workspace/
└── src/
    ├── com.acme.greeter.api/
    │   ├── module-info.java
    │   └── com/acme/greeter/api/Greeter.java
    ├── com.acme.greeter.provider/
    │   ├── module-info.java
    │   └── com/acme/greeter/provider/FriendlyGreeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

**1. `src/com.acme.greeter.api/module-info.java`:**

```java
module com.acme.greeter.api {
    exports com.acme.greeter.api;
}
```

**2. `src/com.acme.greeter.api/com/acme/greeter/api/Greeter.java`:**

```java
package com.acme.greeter.api;

public interface Greeter {
    String greet(String name);
}
```

**3. `src/com.acme.greeter.provider/module-info.java`:**

```java
module com.acme.greeter.provider {
    requires com.acme.greeter.api;
    provides com.acme.greeter.api.Greeter
        with com.acme.greeter.provider.FriendlyGreeter;
}
```

**4. `src/com.acme.greeter.provider/com/acme/greeter/provider/FriendlyGreeter.java`:**

```java
package com.acme.greeter.provider;

import com.acme.greeter.api.Greeter;

public final class FriendlyGreeter implements Greeter {
    public FriendlyGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

**5. `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.greeter.api;
    uses com.acme.greeter.api.Greeter;
}
```

**6. `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.greeter.api.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader.load(Greeter.class)
                .findFirst()
                .ifPresentOrElse(
                        greeter -> System.out.println(greeter.greet("Ada")),
                        () -> System.out.println("No Greeter provider found"));
    }
}
```

### Biên dịch

Chạy từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.greeter.api,com.acme.greeter.provider,com.acme.app
```

Lệnh này biên dịch ba module vào `out/`. `com.acme.app` không khai báo `requires com.acme.greeter.provider`; provider được tìm qua service binding.

### Chạy

```shell
java --module-path out -m com.acme.app/com.acme.app.Main
```

Stdout:

```text
Hello, Ada!
```

Ví dụ đã được biên dịch và chạy trên JDK 24.0.2. Module provider được resolver bind vào graph nhờ `uses`/`provides`, dù consumer không khai báo dependency trực tiếp tới provider module.

## 8. Nhiều provider và lựa chọn implementation

Một service có thể có nhiều provider. Module provider có thể đăng ký nhiều class trong cùng một directive:

```java
provides com.acme.greeter.api.Greeter with
        com.acme.greeter.provider.FriendlyGreeter,
        com.acme.greeter.provider.FormalGreeter;
```

Hoặc nhiều module khác nhau cùng cung cấp một service. Consumer có thể duyệt tất cả provider và áp dụng quy tắc lựa chọn theo cấu hình ứng dụng, môi trường, khả năng hoặc metadata riêng.

Không nên phụ thuộc vào thứ tự provider được phát hiện để quyết định implementation mặc định. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy biểu diễn ưu tiên bằng metadata hoặc cấu hình rõ ràng của ứng dụng rồi sắp xếp theo quy tắc đó.

Ví dụ duyệt các provider:

```java
ServiceLoader.load(Greeter.class)
        .forEach(greeter -> System.out.println(greeter.greet("Ada")));
```

## 9. Dùng `ServiceLoader` với `ModuleLayer` riêng

Ứng dụng có thể tạo module layer riêng để nạp plugin độc lập với boot layer. Khi service provider nằm trong layer tùy chỉnh, hãy dùng overload nhận `ModuleLayer`:

```java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(pluginLayer, Greeter.class);
```

Overload này tìm provider trong layer được chỉ định và các parent layer của nó. Nó phù hợp với kiến trúc plugin có vòng đời nạp riêng, nơi các module provider được resolve vào một layer không thuộc boot layer.

Đừng mặc định `ServiceLoader.load(Greeter.class)` sẽ tìm provider trong mọi layer do ứng dụng tự tạo. Truyền đúng layer khi biết provider thuộc layer nào. Khi tạo layer, cần bảo đảm module API được chia sẻ đúng cách với layer plugin để service type mà consumer và provider nhìn thấy là cùng một kiểu.

## 10. ServiceLoader trên classpath và module path

JPMS module descriptor là cách đăng ký provider trực tiếp cho named modules:

- Consumer named module: `uses com.acme.greeter.api.Greeter;`.
- Provider named module: `provides com.acme.greeter.api.Greeter with ...;`.

Java vẫn hỗ trợ cấu hình provider cho ứng dụng chạy trên classpath hoặc thư viện không phải explicit named module bằng tệp `META-INF/services/<tên-đầy-đủ-của-service>`. Tệp này chứa tên đầy đủ của từng provider class, mỗi dòng một provider. Đây là cơ chế tương thích của `ServiceLoader`; với named module, ưu tiên khai báo `uses` và `provides` trong `module-info.java` để module graph thể hiện rõ quan hệ dịch vụ.

Không trộn hai cơ chế một cách tùy tiện. Xác định artifact là named module hay classpath JAR rồi dùng đúng cách đăng ký tương ứng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy provider. | Provider module không có trên module path, không có `provides`, hoặc không được resolve vào layer đang tìm kiếm. | Kiểm tra module descriptor, module path và module layer. |
| `ServiceConfigurationError` nói consumer không khai báo `uses`. | Named module gọi `ServiceLoader` nhưng thiếu directive `uses` cho service type. | Thêm `uses` vào module descriptor của consumer. |
| `ServiceConfigurationError` khi tạo provider. | Provider class không đáp ứng yêu cầu constructor/provider method hoặc khởi tạo provider thất bại. | Kiểm tra provider class, constructor công khai, provider method và exception gốc. |
| Provider không biên dịch được. | Provider module không đọc service API module. | Thêm `requires` tới module chứa service type. |
| Consumer không import được service interface. | Package chứa service type chưa export hoặc consumer thiếu readability. | Export package trong API module và khai báo `requires` ở consumer. |
| Consumer cố import provider class nhưng không được. | Provider package không export; đây thường là chủ đích để ẩn implementation. | Consumer nên dùng service interface; chỉ export provider package nếu nó thực sự là API công khai. |
| Không thấy provider trong plugin layer. | Dùng loader mặc định thay vì loader của layer chứa provider. | Dùng `ServiceLoader.load(pluginLayer, ServiceType.class)`. |
| Chỉ thấy một provider dù có nhiều implementation. | Code gọi `findFirst()` và dừng sau provider đầu tiên. | Duyệt iterator/stream nếu cần tất cả provider. |
| Lỗi xảy ra khi duyệt provider. | Provider được khởi tạo lazy và lỗi chỉ xuất hiện khi instance được yêu cầu. | Kiểm tra stack trace tại `iterator`, `Provider.get()` hoặc thao tác sử dụng provider. |

`ServiceConfigurationError` là lỗi cấu hình/nạp dịch vụ của `ServiceLoader`; hãy giữ lại nguyên nhân lồng nhau để phân biệt lỗi thiếu khai báo, không tìm thấy class và lỗi trong constructor của provider.

## 12. Hiệu năng, vòng đời và an toàn khi sử dụng

- **Lazy loading:** provider được phát hiện và khởi tạo theo nhu cầu. Tránh giả định mọi provider đã được tạo ngay khi lấy `ServiceLoader`.
- **Caching:** một `ServiceLoader` giữ cache các provider đã được nạp. Gọi `reload()` để xóa cache và cho phép tìm lại provider; thao tác này không tự cài đặt lại module hoặc thay đổi module layer.
- **Thread safety:** `ServiceLoader` không được thiết kế để dùng đồng thời từ nhiều thread mà không có đồng bộ. Nếu cần truy cập đồng thời, hãy quản lý việc khởi tạo/duyệt loader và chia sẻ provider theo chính sách thread-safe của ứng dụng.
- **Provider side effects:** constructor hoặc provider method có thể chạy khi provider được khởi tạo. Giữ khởi tạo nhẹ, tránh side effect toàn cục và giải phóng tài nguyên đúng vòng đời.
- **Tin cậy provider:** provider code chạy với quyền của tiến trình. Chỉ đưa module/JAR từ nguồn đáng tin cậy vào module path; `ServiceLoader` là cơ chế khám phá, không phải sandbox bảo mật.
- **Hợp đồng ổn định:** service API nên hạn chế phụ thuộc vào implementation và cân nhắc tương thích nhị phân khi nâng phiên bản API.

## 13. Checklist triển khai

- Service type là interface/abstract class có hợp đồng rõ ràng và nằm trong package được export.
- Consumer named module khai báo `requires` service API và `uses` đúng service type.
- Provider module khai báo `requires` service API và `provides ... with ...` đúng class.
- Provider đáp ứng yêu cầu public constructor không tham số hoặc provider method hợp lệ.
- Provider package chỉ export khi consumer thực sự cần API công khai từ package đó.
- Provider module có thể được tìm thấy và resolve trong module layer đang sử dụng.
- Dùng `ServiceLoader.load(service)` cho layer mặc định; dùng `ServiceLoader.load(layer, service)` cho layer plugin cụ thể.
- Xử lý trường hợp không có provider, nhiều provider và lỗi khởi tạo provider.
- Kiểm thử trên module path thật và kiểm tra module resolution khi cần.

## Tài liệu tham khảo

- [Java API — `ServiceLoader` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Service Providers and `provides` Directives (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/specs/jls/jls-7.html)
- [Java Launcher — Module Resolution and Service Binding (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Java API — `ModuleLayer` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.html)
