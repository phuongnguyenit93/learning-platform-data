# Provider constructor và yêu cầu khởi tạo

Trong Java Platform Module System (JPMS), `uses` và `provides` mô tả quan hệ giữa module tiêu thụ một service và module cung cấp implementation của service đó. Khi `ServiceLoader` tìm thấy provider, nó cần một cách hợp lệ để tạo ra đối tượng phục vụ. Với provider được khai báo trong `module-info.java`, Java hỗ trợ hai cách: **public constructor không tham số** hoặc **public static provider() factory method**.

Hiểu rõ quy tắc khởi tạo giúp tránh lỗi `ServiceConfigurationError` khi module descriptor đã khai báo provider nhưng lớp provider không đáp ứng hợp đồng của `ServiceLoader`.

## 1. Provider là gì?

Giả sử ứng dụng phụ thuộc vào một abstraction:

    package com.example.spi;

    public interface GreetingService {
        String greet(String name);
    }

Module chứa interface này công bố service để các module khác có thể đọc:

    module com.example.spi {
        exports com.example.spi;
    }

Một module provider cung cấp implementation của `GreetingService`. Module tiêu thụ chỉ cần biết service interface; nó không cần phụ thuộc trực tiếp vào lớp triển khai cụ thể.

Trong JPMS, module provider khai báo:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.EnglishGreetingService;
    }

Directive `provides ... with ...` nói rằng module này cung cấp implementation cho service đã nêu. Tên sau `with` là provider class mà `ServiceLoader` sẽ sử dụng.

Module tiêu thụ khai báo:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.GreetingService;
    }

Directive `uses` thể hiện module app có nhu cầu tìm provider của service. Ứng dụng không cần khai báo `requires com.example.greeting.provider;` chỉ để gọi service theo cơ chế ServiceLoader.

## 2. Cách thứ nhất: public constructor không tham số

Đối với provider class được khai báo trong `provides`, cách truyền thống là có một constructor public không nhận tham số.

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class EnglishGreetingService implements GreetingService {

        public EnglishGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

Các điều kiện cần nhớ:

- Provider class phải là `public`.
- Provider class phải có constructor `public` không tham số.
- Provider class phải triển khai service type được khai báo trong `provides`.
- Constructor phải có thể được gọi để tạo provider; constructor chỉ nhận tham số không đáp ứng quy tắc này.

Nếu không khai báo constructor nào, Java tạo default constructor với mức truy cập tương ứng với class. Với một class `public`, default constructor cũng có mức truy cập `public`. Tuy nhiên, viết constructor tường minh giúp người đọc thấy rõ hợp đồng khởi tạo mà ServiceLoader yêu cầu.

Ví dụ sau không đáp ứng yêu cầu:

    public final class InvalidGreetingService implements GreetingService {

        private InvalidGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

Constructor private không phải public no-argument constructor, nên ServiceLoader không thể dùng cách khởi tạo provider truyền thống. Một constructor chỉ nhận tham số cũng không hợp lệ cho cách này.

## 3. ServiceLoader tạo provider khi nào?

Ứng dụng tìm provider bằng `ServiceLoader`:

    package com.example.app;

    import com.example.spi.GreetingService;
    import java.util.ServiceLoader;

    public class Main {
        public static void main(String[] args) {
            ServiceLoader<GreetingService> loader =
                    ServiceLoader.load(GreetingService.class);

            for (GreetingService service : loader) {
                System.out.println(service.greet("Phuong"));
            }
        }
    }

`ServiceLoader.load(...)` tạo đối tượng loader để tìm provider phù hợp. Việc phát hiện và khởi tạo provider diễn ra lười (lazy): provider được tạo khi chương trình duyệt kết quả hoặc yêu cầu provider tương ứng, chẳng hạn trong vòng lặp trên.

ServiceLoader lưu cache các provider đã được tìm thấy trong một loader. Nếu gọi `reload()`, cache bị xóa và loader sẽ tìm lại provider khi được duyệt lần tiếp theo.

Một provider constructor không được gọi chỉ vì ứng dụng khởi động hoặc vì module descriptor có dòng `provides`. Nó được gọi khi ServiceLoader thực sự cần tạo instance của provider.

## 4. Ví dụ đầy đủ với public no-argument constructor

Cấu trúc source:

    src/
    ├── com.example.spi/
    │   ├── module-info.java
    │   └── com/example/spi/GreetingService.java
    ├── com.example.greeting.provider/
    │   ├── module-info.java
    │   └── com/example/greeting/provider/EnglishGreetingService.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

File `src/com.example.spi/module-info.java`:

    module com.example.spi {
        exports com.example.spi;
    }

File `src/com.example.spi/com/example/spi/GreetingService.java`:

    package com.example.spi;

    public interface GreetingService {
        String greet(String name);
    }

File `src/com.example.greeting.provider/module-info.java`:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.EnglishGreetingService;
    }

File `src/com.example.greeting.provider/com/example/greeting/provider/EnglishGreetingService.java`:

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class EnglishGreetingService implements GreetingService {

        public EnglishGreetingService() {
        }

        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.spi;
        uses com.example.spi.GreetingService;
    }

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.spi.GreetingService;
    import java.util.ServiceLoader;

    public class Main {
        public static void main(String[] args) {
            ServiceLoader<GreetingService> loader =
                    ServiceLoader.load(GreetingService.class);

            loader.forEach(service ->
                    System.out.println(service.greet("Phuong")));
        }
    }

Biên dịch từ thư mục chứa `src`:

    javac --module-source-path src -d out
        -m com.example.spi,com.example.greeting.provider,com.example.app

Chạy ứng dụng và thêm provider module vào tập module được resolve:

    java --module-path out
        --add-modules com.example.greeting.provider
        -m com.example.app/com.example.app.Main

Kết quả:

    Hello, Phuong

Trong ví dụ, provider package không cần khai báo `exports`. Module descriptor đã khai báo provider bằng `provides`, còn ServiceLoader thực hiện việc nạp và khởi tạo provider theo cơ chế module service. Ứng dụng chỉ truy cập service interface đã được module SPI export.

## 5. Cách thứ hai: public static provider() factory method

Với provider được khai báo trong module descriptor, Java còn cho phép provider class cung cấp một phương thức factory có tên chính xác là `provider`.

Quy tắc của phương thức:

- Provider class phải là `public`.
- Phương thức phải là `public static`.
- Phương thức không nhận tham số.
- Kiểu trả về phải là service type hoặc một kiểu con có thể gán cho service type.
- ServiceLoader gọi phương thức này để lấy service instance thay vì gọi constructor của provider class.

Ví dụ:

    package com.example.greeting.provider;

    import com.example.spi.GreetingService;

    public final class GreetingProvider {

        private GreetingProvider() {
        }

        public static GreetingService provider() {
            return new EnglishGreetingService();
        }
    }

Ở đây, `GreetingProvider` không trực tiếp triển khai `GreetingService`. Nó đóng vai trò provider class và cung cấp instance thông qua `provider()`. Constructor của `GreetingProvider` có thể private vì ServiceLoader sử dụng factory method thay cho việc tạo instance của chính provider class.

Module descriptor:

    module com.example.greeting.provider {
        requires com.example.spi;

        provides com.example.spi.GreetingService
            with com.example.greeting.provider.GreetingProvider;
    }

`EnglishGreetingService` là implementation thật được factory trả về. Nó phải tương thích với kiểu `GreetingService`; cách tạo nó có thể do provider method kiểm soát.

Cách này hữu ích khi khởi tạo service cần cấu hình, chọn implementation, dùng cache hoặc xây dựng đối tượng theo một factory nội bộ. Provider method có thể đóng gói logic tạo instance mà không buộc ServiceLoader gọi constructor của provider class.

Lưu ý: provider method là cơ chế dành cho provider được khai báo bằng `provides` trong named module. Provider được khai báo trong file cấu hình `META-INF/services` trên classpath phải tuân theo quy tắc constructor public không tham số.

## 6. So sánh hai cách khởi tạo

| Tiêu chí | Public no-arg constructor | `provider()` factory method |
|---|---|---|
| Provider class | Public | Public |
| Điểm tạo service | Constructor của provider class | Phương thức factory |
| Chữ ký | Constructor public, không tham số | `public static`, không tham số, tên `provider` |
| Provider class phải implements service? | Có | Không bắt buộc nếu factory trả về service type phù hợp |
| Constructor provider class | Phải public và không tham số | Không được ServiceLoader gọi; có thể private |
| Trường hợp phù hợp | Implementation đơn giản, tạo trực tiếp | Cần điều khiển hoặc đóng gói logic khởi tạo |

Khi provider class vừa có constructor hợp lệ vừa có `provider()` hợp lệ, ServiceLoader sử dụng provider method theo hợp đồng của named-module provider. Hãy chọn một cách rõ ràng để người đọc hiểu điểm khởi tạo chính.

## 7. Provider trên classpath và file META-INF/services

Không phải mọi ứng dụng Java đều dùng named module. Trong ứng dụng classpath truyền thống, ServiceLoader tìm provider qua file cấu hình:

    META-INF/services/com.example.spi.GreetingService

Nội dung file ghi tên đầy đủ của từng provider class, mỗi provider trên một dòng:

    com.example.greeting.provider.EnglishGreetingService

Provider class được khai báo theo cách này phải triển khai service type và có constructor public không tham số. Cơ chế factory method `provider()` trong module descriptor không thay thế quy tắc constructor của provider được liệt kê trong file cấu hình classpath.

Do đó, khi chuyển một thư viện từ classpath sang named module, cần kiểm tra lại cách khai báo provider và hợp đồng khởi tạo. Một class chỉ có static `provider()` có thể phù hợp khi được khai báo bằng `provides` trong named module, nhưng không đáp ứng quy tắc provider class truyền thống trong `META-INF/services`.

## 8. Các lỗi khởi tạo thường gặp

ServiceLoader có thể ném `ServiceConfigurationError` khi phát hiện cấu hình provider không hợp lệ hoặc không thể tạo instance. Một số nguyên nhân thường gặp:

1. **Không có constructor public không tham số:** provider dùng cách constructor nhưng chỉ khai báo constructor private hoặc constructor có tham số.
2. **Provider class không public:** lớp được nêu sau `with` không có mức truy cập public.
3. **Sai service type:** provider constructor path không triển khai service được khai báo.
4. **Sai provider method:** method không tên `provider`, không public, không static, có tham số hoặc trả về kiểu không tương thích.
5. **Thiếu module provider trong cấu hình runtime:** module provider không có mặt hoặc không được resolve vào module layer đang tìm service.
6. **Thiếu `uses` ở module tiêu thụ:** module gọi ServiceLoader nhưng module descriptor không khai báo service tương ứng trong `uses`.
7. **Service type không được đọc:** module tiêu thụ không có readability tới module chứa service interface.
8. **Constructor hoặc factory ném exception:** provider được tìm thấy nhưng quá trình khởi tạo thất bại.

Khi gặp lỗi, hãy đọc thông báo `ServiceConfigurationError` để xác định provider nào gặp vấn đề, sau đó kiểm tra module descriptor và chữ ký constructor hoặc provider method tương ứng.

## Ghi nhớ

- Provider được khai báo trong named module bằng `provides Service with Provider;`.
- Provider class phải public.
- Cách constructor yêu cầu public constructor không tham số; provider class cũng phải triển khai service type.
- Named-module provider có thể dùng `public static provider()` không tham số và trả về service type tương thích; khi đó ServiceLoader dùng factory method.
- Provider khai báo trong `META-INF/services` trên classpath vẫn cần constructor public không tham số.
- ServiceLoader khởi tạo provider khi cần duyệt hoặc lấy provider, theo cơ chế lazy loading.

Khi thiết kế provider, hãy xác định rõ module đang cung cấp service, cách provider được khai báo và điểm khởi tạo nào được ServiceLoader sử dụng.