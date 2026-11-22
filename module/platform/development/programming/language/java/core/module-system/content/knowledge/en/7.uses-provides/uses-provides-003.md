# Service interface và provider implementation

Trong Java, Service Provider Interface (SPI) là một cách thiết kế để một module công bố hợp đồng dịch vụ, còn module khác cung cấp phần triển khai hợp đồng đó. Module sử dụng dịch vụ chỉ phụ thuộc vào interface; nó không cần biết class cụ thể nào sẽ thực hiện công việc. Java Platform Module System (JPMS) hỗ trợ cơ chế này bằng hai directive `uses` và `provides`, kết hợp với API `ServiceLoader`.

Cách tổ chức này giúp thay provider mà không phải sửa consumer, cho phép nhiều implementation cùng tồn tại và giữ package triển khai ở trạng thái nội bộ. Những ví dụ quen thuộc gồm driver JDBC, logging backend, plugin, bộ mã hóa, bộ chuyển đổi định dạng và các adapter theo môi trường triển khai.

## 1. Phân biệt service interface, consumer và provider

Một thiết kế SPI thường có ba vai trò:

- **Service interface:** hợp đồng công khai mô tả khả năng mà ứng dụng cần, chẳng hạn `GreetingService`, `PaymentProcessor` hoặc `StorageProvider`.
- **Consumer:** module gọi service interface để thực hiện công việc. Consumer biết kiểu interface nhưng không phụ thuộc class implementation.
- **Provider:** module cung cấp một class thực thi service interface và đăng ký class đó với module system.

Luồng phụ thuộc có dạng:

```text
             +----------------------+
             |    Service API       |
             |  GreetingService     |
             +----------------------+
                    ^        ^
             requires|        |requires
                    |        |
          +---------+--+   +--+-------------+
          | Consumer   |   | Provider       |
          | uses SPI   |   | provides SPI  |
          +------------+   +----------------+
```

Cả consumer và provider đều phụ thuộc vào module chứa service interface. Consumer không cần `requires` module provider cụ thể. Module system và `ServiceLoader` tìm implementation đã đăng ký khi ứng dụng chạy.

## 2. Service interface là hợp đồng ổn định

Service interface nên thể hiện chức năng mà consumer cần, tránh để lộ chi tiết triển khai như thư viện nội bộ, cấu trúc dữ liệu riêng hoặc cách kết nối đến hệ thống bên ngoài.

Ví dụ:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

Trong module descriptor của module API, export package chứa interface:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Directive `exports` cho phép consumer import và gọi kiểu public `GreetingService`. Đây là API ở mức ngôn ngữ Java; nó không tự đăng ký implementation nào.

Một SPI tốt thường giữ hợp đồng nhỏ và tập trung. Nếu interface thay đổi không tương thích, tất cả provider cần được cập nhật hoặc có cơ chế tương thích ngược. Vì vậy, hãy xác định rõ tham số, giá trị trả về, exception và quy tắc vòng đời của service.

## 3. Provider implementation

Provider tạo class thực thi interface:

```java
package com.acme.provider.internal;

import com.acme.spi.GreetingService;

public class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Class provider là public và có public no-argument constructor để `ServiceLoader` có thể khởi tạo nó theo cơ chế constructor thông thường. Với provider khai báo bằng `provides` trong named module, package chứa implementation không cần export cho consumer. Consumer chỉ cần nhìn thấy service interface; việc tạo provider do cơ chế service loading đảm nhiệm.

Descriptor của module provider:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.EnglishGreetingService;
}
```

Directive `provides ... with ...` đăng ký implementation. Phần trước `with` là service type; phần sau là một hoặc nhiều provider class. Một module có thể đăng ký nhiều provider cho cùng một service.

Provider có thể cung cấp nhiều service khác nhau, miễn là các implementation thỏa mãn hợp đồng tương ứng và được khai báo trong descriptor.

## 4. Consumer khai báo uses

Module sử dụng service cần khai báo `uses` cho service type mà nó sẽ nạp:

```java
module com.acme.consumer {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

`requires com.acme.spi` tạo quan hệ readability để mã consumer có thể tham chiếu interface. `uses com.acme.spi.GreetingService` khai báo rằng module có nhu cầu tìm provider của service đó. Hai directive phục vụ hai mục đích riêng.

Consumer sử dụng `ServiceLoader`:

```java
package com.acme.consumer;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

        for (GreetingService service : loader) {
            System.out.println(service.greet("Java"));
        }
    }
}
```

Consumer chỉ làm việc với `GreetingService`. Nó không import `EnglishGreetingService`, không gọi constructor provider và không cần biết tên module provider. Khi provider được phát hiện, `ServiceLoader` tạo instance và trả về dưới kiểu interface.

Nếu không có provider nào được tìm thấy, vòng lặp không chạy. Ứng dụng cần quyết định rõ trường hợp service tùy chọn hay bắt buộc: có thể dùng implementation mặc định, thông báo cấu hình thiếu hoặc dừng với lỗi phù hợp.

## 5. Ví dụ hoàn chỉnh với ba module

Cấu trúc source:

```text
src/
├── com.acme.spi/
│   ├── module-info.java
│   └── com/acme/spi/GreetingService.java
├── com.acme.provider/
│   ├── module-info.java
│   └── com/acme/provider/internal/EnglishGreetingService.java
└── com.acme.consumer/
    ├── module-info.java
    └── com/acme/consumer/Main.java
```

Module API:

```java
// src/com.acme.spi/module-info.java
module com.acme.spi {
    exports com.acme.spi;
}
```

Module provider:

```java
// src/com.acme.provider/module-info.java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.EnglishGreetingService;
}
```

Module consumer:

```java
// src/com.acme.consumer/module-info.java
module com.acme.consumer {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

Biên dịch cả ba module từ thư mục chứa `src`:

```shell
javac --module-source-path src -d out \
    -m com.acme.spi,com.acme.provider,com.acme.consumer
```

Chạy consumer trên module path:

```shell
java --show-module-resolution --module-path out \
    --module com.acme.consumer/com.acme.consumer.Main
```

Khi phân giải cấu hình module, Java có thể tìm module provider quan sát được có khai báo `provides` cho service mà module gốc sử dụng và đưa provider phù hợp vào cấu hình. Vì vậy, consumer không phải khai báo dependency trực tiếp tới `com.acme.provider`. Tùy chọn `--show-module-resolution` giúp quan sát các module được phân giải khi khởi chạy.

Package `com.acme.provider.internal` không được export. Điều đó vẫn hợp lệ: provider implementation không phải API mà consumer gọi trực tiếp. Nếu muốn ứng dụng tham chiếu class provider trong mã nguồn, đó là một thiết kế khác và sẽ cần công khai package tương ứng.

## 6. Một service có thể có nhiều provider

SPI cho phép nhiều module cung cấp implementation cho cùng một interface. Ví dụ:

```java
module com.acme.provider.english {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.english.EnglishGreetingService;
}
```

```java
module com.acme.provider.vietnamese {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.vietnamese.VietnameseGreetingService;
}
```

Consumer có thể duyệt tất cả provider:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);

loader.stream()
    .map(ServiceLoader.Provider::get)
    .forEach(service ->
        System.out.println(service.greet("Java"))
    );
```

Không nên dựa vào thứ tự provider như một quy tắc ưu tiên ổn định. Nếu ứng dụng cần chọn một provider cụ thể, hãy thiết kế cơ chế lựa chọn tường minh, chẳng hạn thuộc tính cấu hình, metadata riêng hoặc phương thức nhận diện capability trên interface.

Nếu nhiều provider cùng được phát hiện, consumer phải quyết định liệu nó muốn dùng tất cả, chọn một provider theo cấu hình hay từ chối khi có nhiều lựa chọn. Tránh âm thầm lấy phần tử đầu tiên nếu thứ tự không phải một phần của hợp đồng.

## 7. ServiceLoader và provider method

Ngoài public no-argument constructor, named module có thể cung cấp provider thông qua public static provider method. Khi dùng cách này, provider class công khai một phương thức tên `provider` trả về service type:

```java
package com.acme.provider.internal;

import com.acme.spi.GreetingService;

public class GreetingProvider {
    public static GreetingService provider() {
        return new EnglishGreetingService();
    }
}
```

Module descriptor đăng ký provider class:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.internal.GreetingProvider;
}
```

Provider method hữu ích khi việc tạo implementation cần factory, cấu hình hoặc một object không được tạo trực tiếp bằng constructor public. Class provider vẫn phải đáp ứng quy tắc provider method của `ServiceLoader`; phương thức phải là `public static`, không nhận tham số và trả về kiểu tương thích với service type.

Chỉ chọn provider method khi nó giải quyết nhu cầu khởi tạo cụ thể. Với implementation đơn giản, public no-argument constructor thường dễ hiểu hơn.

## 8. SPI trên classpath và file META-INF/services

Cơ chế service loading tồn tại trước JPMS. Khi provider được triển khai trên classpath, provider thường đăng ký bằng file cấu hình:

```text
META-INF/services/com.acme.spi.GreetingService
```

Nội dung file liệt kê tên đầy đủ của từng provider class, mỗi provider trên một dòng:

```text
com.acme.provider.internal.EnglishGreetingService
com.acme.provider.internal.VietnameseGreetingService
```

Consumer vẫn có thể sử dụng:

```java
ServiceLoader<GreetingService> loader =
    ServiceLoader.load(GreetingService.class);
```

Khi chạy trên classpath, provider được tìm qua cấu hình `META-INF/services` và class loader. Khi chạy dưới named module, provider có thể đăng ký trực tiếp bằng directive `provides` trong `module-info.java`, còn consumer khai báo `uses`.

Với thư viện cần hỗ trợ cả classpath lẫn module path, cần đóng gói và kiểm tra đúng metadata cho từng chế độ phân phối. Không nên giả định file `META-INF/services` và descriptor module luôn được xử lý giống nhau trong mọi kiểu đóng gói.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy provider | Module provider không được phân giải, thiếu `provides` hoặc metadata classpath sai | Kiểm tra module path và descriptor/JAR |
| Consumer báo lỗi khi gọi `ServiceLoader` | Named module chưa khai báo `uses` cho service type | Thêm `uses` vào descriptor consumer |
| Provider không được tạo | Provider class hoặc constructor/provider method không đáp ứng quy tắc | Kiểm tra public class, constructor hoặc provider method |
| Không biên dịch được service interface | Consumer thiếu `requires` module API hoặc package API chưa export | Kiểm tra module API và consumer descriptor |
| Consumer phụ thuộc trực tiếp implementation | Mã consumer import class provider cụ thể | Chuyển dependency về service interface |
| Có nhiều implementation nhưng chọn sai | Ứng dụng giả định thứ tự provider | Thêm chính sách chọn provider tường minh |

Có thể xem descriptor của từng JAR:

```shell
jar --describe-module --file provider.jar
jar --describe-module --file consumer.jar
```

Đối với provider modular, kiểm tra mục `provides`. Đối với consumer, kiểm tra mục `uses`. Nếu ứng dụng chạy trên module path, hãy xem thêm kết quả `--show-module-resolution` để biết provider module có thực sự tham gia cấu hình chạy hay không.

## 10. Nguyên tắc thiết kế SPI

- Đặt service interface trong module API riêng và export package chứa interface.
- Consumer khai báo `requires` tới API và `uses` service type.
- Provider khai báo `requires` tới API và `provides ... with ...` trong module descriptor.
- Giữ implementation trong package nội bộ; không export package provider nếu consumer không cần truy cập trực tiếp.
- Thiết kế interface nhỏ, ổn định, có quy định rõ về lifecycle, lỗi và thread-safety.
- Không dựa vào thứ tự provider để quyết định implementation được chọn.
- Nếu hỗ trợ classpath, cung cấp file `META-INF/services` đúng tên service interface.
- Kiểm tra module resolution và metadata của artifact trong chính môi trường triển khai.

SPI tách hợp đồng khỏi implementation. Khi consumer chỉ phụ thuộc service interface, provider có thể được thay thế, bổ sung hoặc phân phối riêng mà không làm consumer gắn chặt với class triển khai cụ thể. JPMS làm rõ quan hệ này bằng `uses` và `provides`, còn `ServiceLoader` đảm nhiệm việc khám phá và khởi tạo provider lúc chạy.