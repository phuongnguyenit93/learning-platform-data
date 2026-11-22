# Nhà cung cấp qua constructor hoặc phương thức provider

## 1. Nhà cung cấp dịch vụ trong JPMS

Java Platform Module System (JPMS) hỗ trợ mô hình dịch vụ thông qua hai directive trong module descriptor:

- **uses**: module tiêu thụ khai báo service type mà nó cần.
- **provides ... with ...**: module cung cấp khai báo service type và các provider type tương ứng.

Ở thời điểm chạy, ứng dụng thường dùng **java.util.ServiceLoader** để tìm và lấy các implementation của service. Cách này giúp module ứng dụng phụ thuộc vào hợp đồng API, còn module triển khai có thể được bổ sung hoặc thay thế độc lập.

Một provider trong named module có thể được tạo theo một trong hai cách:

1. **Public no-argument constructor**: provider class trực tiếp triển khai service và có constructor public không tham số.
2. **Public static provider method**: provider class khai báo phương thức public static tên chính xác là `provider`, không có tham số và trả về một đối tượng có kiểu là service type hoặc subtype của service type.

Hai cơ chế này đều được JPMS hỗ trợ hiện nay. Provider method đặc biệt hữu ích khi việc tạo implementation cần một factory, cần ẩn lớp triển khai hoặc không muốn provider class phải có constructor public.

## 2. Các thành phần của mô hình dịch vụ

Một ứng dụng dùng JPMS service thường có bốn thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Service API | Khai báo interface hoặc abstract class mà ứng dụng cần |
| Consumer module | Khai báo `uses` và gọi `ServiceLoader` |
| Provider module | Khai báo `provides ... with ...` trong `module-info.java` |
| Provider type | Tạo implementation qua constructor hoặc phương thức `provider()` |

Luồng hoạt động:

1. Consumer khai báo service type bằng `uses`.
2. Provider module khai báo service type và provider type bằng `provides`.
3. Khi module graph được phân giải với service binding, các provider phù hợp có thể được đưa vào configuration.
4. Consumer gọi `ServiceLoader.load(ServiceType.class)`.
5. ServiceLoader tìm các provider trong module layer phù hợp và tạo provider instance khi ứng dụng duyệt kết quả.

Consumer chỉ cần biết service API. Nó không cần import provider class hoặc khai báo `requires` trực tiếp tới từng provider module.

## 3. Cách 1 — Provider class dùng public no-argument constructor

Đây là cách đơn giản khi implementation là một class thông thường và có thể tạo bằng constructor không tham số.

### 3.1. Service API

Giả sử service có interface:

~~~java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

Module API export package chứa service type:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Consumer và provider đều cần đọc module API này.

### 3.2. Provider implementation

Provider class phải:

- Là class public.
- Triển khai service interface hoặc kế thừa service type.
- Có constructor public không tham số.
- Có thể được khai báo trong module descriptor của provider.

Ví dụ:

~~~java
package com.example.greeting.constructor;

import com.example.greeting.api.GreetingService;

public final class ConstructorGreetingProvider
        implements GreetingService {

    public ConstructorGreetingProvider() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Constructor public không tham số là điểm quan trọng. ServiceLoader dùng constructor này để tạo instance khi provider được yêu cầu.

### 3.3. Khai báo provides

File `module-info.java` của module triển khai:

~~~java
module com.example.greeting.constructor {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.constructor.ConstructorGreetingProvider;
}
~~~

Cấu trúc directive:

~~~java
provides <service-type>
    with <provider-type>;
~~~

Trong đó:

- `service-type` là interface hoặc abstract class được consumer sử dụng.
- `provider-type` là class triển khai service và có public no-argument constructor.

Module provider cần `requires` module chứa service type để biên dịch implementation.

## 4. Cách 2 — Provider class dùng phương thức public static provider()

JPMS cũng cho phép provider class có phương thức factory thay cho constructor public không tham số.

Phương thức này phải đáp ứng các điều kiện:

- Tên phương thức chính xác là **provider**.
- Phương thức có modifier **public static**.
- Không nhận tham số.
- Kiểu trả về là service type hoặc một subtype có thể gán cho service type.
- Provider class phải là class public để được khai báo trong `provides`.

Provider class không bắt buộc phải triển khai service interface. Nó cũng không cần public no-argument constructor khi có provider method hợp lệ.

### 4.1. Ví dụ provider method

~~~java
package com.example.greeting.factory;

import com.example.greeting.api.GreetingService;

public final class FactoryGreetingProvider {

    private FactoryGreetingProvider() {
    }

    public static GreetingService provider() {
        return name -> "Welcome, " + name;
    }
}
~~~

Ở ví dụ này:

- `FactoryGreetingProvider` không implements `GreetingService`.
- Constructor của class là private.
- Phương thức `provider()` là public static và không có tham số.
- Phương thức trả về một đối tượng `GreetingService`, ở đây là lambda.

Vì interface chỉ có một abstract method nên có thể dùng lambda để tạo implementation. Nếu service có nhiều abstract method, provider method có thể trả về một class triển khai đầy đủ service đó.

### 4.2. Khai báo provides cho provider method

File `module-info.java`:

~~~java
module com.example.greeting.factory {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.factory.FactoryGreetingProvider;
}
~~~

Trong directive `provides`, vẫn khai báo tên provider class. ServiceLoader sẽ gọi phương thức `provider()` để lấy đối tượng service.

Điểm cần phân biệt: `with` luôn chỉ tới provider type được đăng ký. Với cách dùng constructor, provider type chính là implementation. Với provider method, provider type có thể chỉ đóng vai trò factory và đối tượng được trả về mới là implementation thực tế.

## 5. So sánh hai cách tạo provider

| Tiêu chí | Constructor | Provider method |
|---|---|---|
| Provider class implements service | Có | Không bắt buộc |
| Cách tạo instance | Public no-argument constructor | Public static `provider()` |
| Tham số tạo instance | Không có | Không có |
| Return type | Không áp dụng | Service type hoặc subtype |
| Constructor public không tham số | Bắt buộc | Không bắt buộc nếu có provider method hợp lệ |
| Có thể ẩn implementation class | Hạn chế hơn | Có thể trả về implementation khác |
| Phù hợp | Implementation đơn giản, khởi tạo trực tiếp | Cần factory, chọn implementation hoặc đóng gói cách tạo đối tượng |

Nếu provider class khai báo provider method hợp lệ, ServiceLoader sử dụng phương thức này để lấy service instance. Nếu không có provider method, cơ chế tạo provider dựa trên public no-argument constructor.

Nên dùng constructor khi implementation đơn giản và không cần logic tạo đối tượng. Nên dùng provider method khi cần kiểm soát quá trình tạo service hoặc muốn tách provider type khỏi implementation type.

## 6. Ví dụ hoàn chỉnh với hai provider

Ví dụ gồm bốn module:

~~~text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/api/GreetingService.java
├── com.example.greeting.constructor/
│   ├── module-info.java
│   └── com/example/greeting/constructor/ConstructorGreetingProvider.java
├── com.example.greeting.factory/
│   ├── module-info.java
│   └── com/example/greeting/factory/FactoryGreetingProvider.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 6.1. Module API

File `src/com.example.greeting.api/module-info.java`:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

File `src/com.example.greeting.api/com/example/greeting/api/GreetingService.java`:

~~~java
package com.example.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

### 6.2. Module provider dùng constructor

File `src/com.example.greeting.constructor/module-info.java`:

~~~java
module com.example.greeting.constructor {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.constructor.ConstructorGreetingProvider;
}
~~~

File `src/com.example.greeting.constructor/com/example/greeting/constructor/ConstructorGreetingProvider.java`:

~~~java
package com.example.greeting.constructor;

import com.example.greeting.api.GreetingService;

public final class ConstructorGreetingProvider
        implements GreetingService {

    public ConstructorGreetingProvider() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 6.3. Module provider dùng provider method

File `src/com.example.greeting.factory/module-info.java`:

~~~java
module com.example.greeting.factory {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.factory.FactoryGreetingProvider;
}
~~~

File `src/com.example.greeting.factory/com/example/greeting/factory/FactoryGreetingProvider.java`:

~~~java
package com.example.greeting.factory;

import com.example.greeting.api.GreetingService;

public final class FactoryGreetingProvider {

    private FactoryGreetingProvider() {
    }

    public static GreetingService provider() {
        return name -> "Welcome, " + name;
    }
}
~~~

### 6.4. Module consumer

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greeting.api;

    uses com.example.greeting.api.GreetingService;
}
~~~

Consumer khai báo `uses` vì nó gọi ServiceLoader để tìm các implementation của GreetingService.

Consumer không cần khai báo:

~~~java
requires com.example.greeting.constructor;
requires com.example.greeting.factory;
~~~

Việc tìm provider được thực hiện qua cơ chế service binding khi các module provider có mặt trên module path và module graph được phân giải phù hợp.

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader.load(GreetingService.class)
            .stream()
            .map(provider -> provider.get().greet("Linh"))
            .sorted()
            .forEach(System.out::println);
    }
}
~~~

Ở đây:

- `ServiceLoader.load(GreetingService.class)` yêu cầu tìm provider của service.
- `stream()` trả về các đối tượng `ServiceLoader.Provider`.
- `provider.get()` tạo hoặc lấy service instance tương ứng.
- `sorted()` giúp kết quả ví dụ có thứ tự ổn định, không phụ thuộc thứ tự phát hiện provider.

## 7. Biên dịch và chạy ví dụ

Mở terminal tại thư mục chứa `src`.

Biên dịch cả bốn module bằng JDK hiện hành, đồng thời giới hạn API đích ở Java 17:

~~~bash
javac --release 17 --module-source-path src -d out -m com.example.greeting.api,com.example.greeting.constructor,com.example.greeting.factory,com.example.app
~~~

Cấu trúc output:

~~~text
out/
├── com.example.greeting.api/
│   ├── module-info.class
│   └── com/example/greeting/api/GreetingService.class
├── com.example.greeting.constructor/
│   ├── module-info.class
│   └── com/example/greeting/constructor/ConstructorGreetingProvider.class
├── com.example.greeting.factory/
│   ├── module-info.class
│   └── com/example/greeting/factory/FactoryGreetingProvider.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Chạy ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello, Linh
Welcome, Linh
~~~

Ví dụ đã được biên dịch với `javac --release 17` và chạy thành công trên JDK 24.0.2. Kết quả xác nhận ServiceLoader tìm được cả provider dùng constructor lẫn provider dùng phương thức provider().

## 8. Service binding và module graph

Khi chạy ứng dụng modular, các module provider cần có mặt trên module path hoặc trong module layer phù hợp.

Với launcher Java, quá trình phân giải module có service binding. Nếu module gốc khai báo `uses` một service, các module observable khai báo `provides` service tương ứng có thể được bổ sung vào configuration.

Có thể quan sát quá trình này bằng:

~~~bash
java --show-module-resolution --module-path out -m com.example.app/com.example.app.Main
~~~

Trong output, tìm các dòng tương tự:

~~~text
com.example.app binds com.example.greeting.factory
com.example.app binds com.example.greeting.constructor
~~~

Tên module và thứ tự các dòng phụ thuộc môi trường JDK và các module đang có trên module path.

Nếu tự tạo module layer bằng Java API, dùng `Configuration.resolveAndBind(...)` khi muốn phân giải kèm service binding. `Configuration.resolve(...)` chỉ xử lý quan hệ phân giải thông thường và không thực hiện bước service binding tương tự.

## 9. Package provider có cần exports không?

Module service provider không cần export package chứa provider type chỉ để ServiceLoader tìm và tạo provider.

Trong ví dụ:

- Module API export package `com.example.greeting.api`, vì consumer phải đọc interface GreetingService.
- Module constructor không export package `com.example.greeting.constructor`.
- Module factory không export package `com.example.greeting.factory`.

Các provider vẫn được tìm thấy thông qua directive `provides`. Nhờ đó implementation có thể được giữ kín bên trong module, còn consumer chỉ nhìn thấy hợp đồng service đã export.

Không nên export package triển khai nếu module khác không cần sử dụng trực tiếp các class trong package đó.

## 10. Provider method và provider constructor trong classpath

Khi ứng dụng chưa dùng named module và đặt thư viện trên classpath, ServiceLoader vẫn hỗ trợ provider configuration file:

~~~text
META-INF/services/com.example.greeting.api.GreetingService
~~~

File này chứa tên đầy đủ của từng provider class, mỗi provider trên một dòng. Cơ chế classpath provider sử dụng public no-argument constructor.

Provider method `public static provider()` là cơ chế được khai báo thông qua `provides ... with ...` trong named module descriptor. Vì vậy, nếu muốn dùng provider method, hãy đóng gói module với `module-info.class` và chạy trên module path.

Hai cách đều được Java hỗ trợ; chọn cách phù hợp với mô hình triển khai của ứng dụng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy provider | Thiếu directive `provides`, provider module không có trên module path hoặc service binding không đưa module vào layer | Kiểm tra descriptor, module path và module layer |
| Consumer không dùng được ServiceLoader trong named module | Thiếu directive `uses` trong module consumer | Khai báo `uses service.type;` |
| Provider constructor không được gọi thành công | Provider class không public hoặc thiếu public no-argument constructor | Kiểm tra visibility và constructor |
| Provider method không được nhận diện | Tên method sai, method không public/static, có tham số hoặc return type không tương thích | Dùng đúng chữ ký `public static ServiceType provider()` |
| Provider method trả về null | Factory method không tạo được service instance hợp lệ | Trả về implementation hợp lệ; xử lý cấu hình lỗi rõ ràng |
| Provider class không implements service nhưng bị khai báo constructor style | Provider không có provider method nên không đáp ứng dạng constructor | Implement service và cung cấp public no-arg constructor, hoặc viết provider method |
| Không truy cập được service type | Module API chưa export package chứa service | Export package API cần cho consumer |
| Consumer phải requires từng provider module | Nhầm quan hệ API với quan hệ service | Consumer dùng `requires` API và `uses` service; provider tự khai báo `provides` |
| ServiceLoader báo lỗi cấu hình | Provider type hoặc provider method không hợp lệ, hoặc quá trình tạo provider thất bại | Đọc nguyên nhân gốc trong `ServiceConfigurationError` và kiểm tra descriptor/provider |

Nếu provider không có mặt, ServiceLoader có thể trả về tập provider rỗng. Nếu descriptor hoặc provider implementation không hợp lệ, quá trình duyệt provider có thể ném `ServiceConfigurationError`. Cần phân biệt tình huống không có provider với tình huống provider tồn tại nhưng không thể khởi tạo.

## 12. Nguyên tắc thiết kế

- Đặt service interface trong module API riêng và export đúng package API.
- Consumer khai báo `uses`; không phụ thuộc trực tiếp vào class triển khai.
- Provider module khai báo `requires` service API và `provides` provider type.
- Dùng public no-argument constructor khi provider là implementation trực tiếp, đơn giản.
- Dùng public static `provider()` khi cần factory hoặc muốn tách provider type khỏi implementation type.
- Giữ package triển khai ở trạng thái đóng; chỉ export khi có nhu cầu API thực sự.
- Đưa các provider module vào module path hoặc module layer mà ứng dụng phân giải.
- Kiểm thử trường hợp có nhiều provider, không giả định thứ tự phát hiện provider.
- Kiểm tra cả descriptor, service binding và kết quả ServiceLoader khi triển khai.

## 13. Tóm tắt

Một named module cung cấp service có thể đăng ký provider theo hai cách:

- **Constructor:** provider class public, implements service và có public no-argument constructor.
- **Provider method:** provider class public, có public static `provider()` không tham số, trả về service type hoặc subtype. Provider class không bắt buộc implements service và không cần public no-argument constructor.

Trong cả hai trường hợp, module provider khai báo `provides`, còn module consumer khai báo `uses`. ServiceLoader chịu trách nhiệm tìm và lấy các implementation trong module layer thích hợp.

## Tài liệu tham khảo

- [ServiceLoader — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ServiceLoader.html) — quy tắc provider constructor, provider method và cách tải service.
- [Module Declaration — Java Language Specification](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7) — cú pháp `uses` và `provides` trong module descriptor.
- [Java Compiler — javac](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html) — biên dịch các named module bằng module source path và module path.
