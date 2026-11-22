# Tách giao diện dịch vụ khỏi phần triển khai trong Java Module System

Trong một ứng dụng có nhiều module, module sử dụng một khả năng thường không nên phụ thuộc trực tiếp vào class triển khai cụ thể. Ví dụ, ứng dụng cần gửi thông báo nhưng có thể chọn nhà cung cấp gửi qua email, SMS hoặc một hệ thống khác. Nếu ứng dụng import trực tiếp lớp EmailNotifier, việc thay đổi sang nhà cung cấp khác sẽ kéo theo thay đổi mã nguồn và dependency của ứng dụng.

JPMS hỗ trợ mô hình này bằng cơ chế dịch vụ (services):

- **Service interface / Service Provider Interface (SPI):** hợp đồng mà bên sử dụng và bên triển khai cùng biết.
- **Service consumer:** module cần sử dụng dịch vụ; khai báo directive **uses**.
- **Service provider:** module cung cấp một hoặc nhiều implementation; khai báo directive **provides ... with ...**.
- **ServiceLoader:** API của JDK tìm và nạp implementation phù hợp tại runtime.

Khi tách các vai trò này, consumer chỉ phụ thuộc vào hợp đồng dịch vụ. Provider có thể được thêm, thay thế hoặc loại bỏ mà không cần sửa mã nguồn consumer, miễn là implementation vẫn tuân thủ SPI.

## 1. Kiến trúc dịch vụ gồm những module nào?

Một thiết kế điển hình có ba module:

| Module | Trách nhiệm | Phụ thuộc chính |
|---|---|---|
| com.example.greeting.api | Định nghĩa service interface và công bố package chứa hợp đồng | java.base |
| com.example.greeting.english | Cung cấp implementation cho service interface | Module API |
| com.example.app | Sử dụng dịch vụ thông qua ServiceLoader | Module API |

Quan hệ phụ thuộc:

~~~text
                  +----------------------------+
                  | com.example.greeting.api   |
                  | GreetingService (SPI)      |
                  +-------------+--------------+
                                ^
                                |
                    +-----------+-----------+
                    |                       |
        +-----------+-----------+   +-------+----------------+
        | com.example.app       |   | com.example.greeting   |
        | uses GreetingService  |   | .english               |
        | ServiceLoader         |   | provides implementation|
        +-----------------------+   +------------------------+
~~~

Consumer và provider cùng phụ thuộc vào module API. Consumer không cần khai báo requires com.example.greeting.english và không cần import lớp EnglishGreeting. Module system tìm provider thông qua khai báo provides khi phân giải các module cần thiết cho dịch vụ.

Đây là điểm cốt lõi của thiết kế: **phụ thuộc vào abstraction (hợp đồng), không phụ thuộc vào implementation cụ thể**.

## 2. Service interface (SPI) là hợp đồng chung

Service interface nên nằm trong một package công khai của module API. Interface mô tả những thao tác mà consumer cần, không chứa chi tiết nội bộ của một provider cụ thể.

Ví dụ:

~~~java
package com.example.greeting.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Consumer chỉ cần biết phương thức greet. Provider có thể dùng thư viện, giao thức, cấu hình hoặc thuật toán riêng để tạo lời chào.

Module API khai báo:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.spi;
}
~~~

Directive exports cho phép các module đọc com.example.greeting.api import và sử dụng kiểu GreetingService.

Một SPI tốt thường có các đặc điểm:

- Tên và chữ ký phương thức phản ánh khả năng mà consumer cần.
- Kiểu tham số và kiểu trả về thuộc API công khai hoặc các kiểu nền tảng ổn định.
- Không để lộ lớp implementation, cấu hình nội bộ hay dependency riêng của provider.
- Quy định rõ ý nghĩa kết quả, lỗi có thể phát sinh và cách quản lý tài nguyên nếu dịch vụ cần đóng/mở kết nối.
- Giữ hợp đồng ổn định để provider độc lập có thể triển khai và nâng cấp.

Nếu service cần nhiều thao tác hoặc dữ liệu đầu vào phức tạp, hãy thiết kế các kiểu request/response trong package API. Tránh đưa kiểu chỉ tồn tại trong module provider vào chữ ký của SPI, vì điều đó buộc consumer phải phụ thuộc vào implementation.

## 3. Consumer khai báo uses

Module consumer cần khai báo service mà nó muốn sử dụng:

~~~java
module com.example.app {
    requires com.example.greeting.api;
    uses com.example.greeting.spi.GreetingService;
}
~~~

Hai directive có mục đích khác nhau:

- requires com.example.greeting.api tạo quan hệ đọc tới module chứa service interface. Consumer có thể import GreetingService.
- uses com.example.greeting.spi.GreetingService khai báo rằng module này tìm và sử dụng các provider của service đó.

uses không chỉ là một ghi chú tài liệu. Nó là một phần của module descriptor để module system hỗ trợ cơ chế service binding và để ServiceLoader hoạt động đúng trong named module.

Consumer không khai báo tên provider cụ thể trong requires. Nếu phải import EnglishGreeting hoặc khai báo requires tới module provider, consumer sẽ phụ thuộc trực tiếp vào implementation và mất lợi ích thay thế provider.

## 4. Provider khai báo provides ... with ...

Module cung cấp implementation khai báo service và lớp triển khai:

~~~java
module com.example.greeting.english {
    requires com.example.greeting.api;

    provides com.example.greeting.spi.GreetingService
        with com.example.greeting.english.EnglishGreeting;
}
~~~

Directive provides có cấu trúc:

~~~java
provides service.Interface with provider.Implementation;
~~~

Ý nghĩa:

- Phần sau provides là kiểu service mà provider triển khai.
- Phần sau with là một hoặc nhiều lớp provider được khai báo, phân tách bằng dấu phẩy.
- Module provider phải đọc được module chứa service interface, thường bằng requires.
- Package chứa lớp provider không cần được export chỉ để ServiceLoader phát hiện provider qua khai báo module.

Đối với provider class trong named module, lớp provider phải đáp ứng quy tắc của JPMS: có thể cung cấp public no-argument constructor để tạo instance và triển khai service; hoặc khai báo public static no-argument method tên provider trả về kiểu service. Cách dùng constructor là cách đơn giản và phổ biến trong ví dụ bên dưới.

Implementation:

~~~java
package com.example.greeting.english;

import com.example.greeting.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Package com.example.greeting.english không cần xuất hiện trong directive exports. Consumer không import EnglishGreeting; module system và ServiceLoader chịu trách nhiệm tìm và tạo provider theo khai báo provides.

Giữ package implementation không export giúp provider tự do thay đổi class nội bộ mà không biến các class đó thành API công khai.

## 5. Consumer tìm provider bằng ServiceLoader

ServiceLoader là API chuẩn trong module java.base. Consumer có thể tìm provider mà không biết tên lớp triển khai:

~~~java
package com.example.app;

import com.example.greeting.spi.GreetingService;

import java.util.Iterator;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        Iterator<GreetingService> providers = loader.iterator();

        if (!providers.hasNext()) {
            throw new IllegalStateException(
                    "No GreetingService provider found"
            );
        }

        GreetingService greeting = providers.next();
        System.out.println(greeting.greet("Ada"));
    }
}
~~~

Các bước chính:

1. ServiceLoader.load(GreetingService.class) tạo loader để tìm provider cho service interface.
2. iterator() cung cấp cách duyệt các provider.
3. hasNext() kiểm tra xem có provider nào được tìm thấy hay không.
4. next() lấy instance provider.
5. Consumer gọi phương thức trên interface GreetingService; mã consumer không cần biết lớp cụ thể là EnglishGreeting.

Việc phát hiện và khởi tạo provider có tính lazy: provider thường chỉ được nạp khi consumer duyệt tới nó. Nếu không có provider, consumer nên quyết định hành vi phù hợp, chẳng hạn báo lỗi cấu hình, dùng chức năng dự phòng hoặc bỏ qua tính năng tùy chọn.

### 5.1. Module descriptor của consumer

File module-info.java của ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeting.api;
    uses com.example.greeting.spi.GreetingService;
}
~~~

Consumer chỉ biết API module. Nếu provider được thay bằng FrenchGreeting, consumer không phải sửa import hoặc module descriptor.

### 5.2. Lấy nhiều provider

Một service có thể có nhiều implementation. Consumer có thể duyệt tất cả:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.greet("Ada"));
}
~~~

Không nên dựa vào thứ tự provider để biểu thị mức ưu tiên. Nếu ứng dụng cần chọn một provider cụ thể, hãy định nghĩa quy tắc lựa chọn trong API hoặc metadata riêng, ví dụ theo cấu hình, thuộc tính provider hoặc khả năng được công bố.

Từ Java 9, ServiceLoader còn có stream() và ServiceLoader.Provider để kiểm tra kiểu provider trước khi tạo instance. Cách này hữu ích khi ứng dụng cần lọc provider theo class hoặc metadata trước khi gọi get().

Ví dụ:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
        .filter(provider ->
                provider.type().getSimpleName().startsWith("English"))
        .map(ServiceLoader.Provider::get)
        .forEach(service ->
                System.out.println(service.greet("Ada")));
~~~

Chỉ nên dùng lọc theo tên lớp khi đó là quy ước được kiểm soát trong ứng dụng. Nếu lựa chọn provider là yêu cầu nghiệp vụ, một thuộc tính hoặc phương thức rõ ràng trong SPI thường bền vững hơn tên implementation.

## 6. Ví dụ hoàn chỉnh với ba module

Ví dụ sau có một service interface, một provider và một consumer. Provider implementation không được export; consumer chỉ gọi interface qua ServiceLoader.

### 6.1. Cấu trúc thư mục

~~~text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/spi/
│       └── GreetingService.java
├── com.example.greeting.english/
│   ├── module-info.java
│   └── com/example/greeting/english/
│       └── EnglishGreeting.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        └── Main.java
~~~

### 6.2. Module API

File src/com.example.greeting.api/module-info.java:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.spi;
}
~~~

File src/com.example.greeting.api/com/example/greeting/spi/GreetingService.java:

~~~java
package com.example.greeting.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

### 6.3. Module provider

File src/com.example.greeting.english/module-info.java:

~~~java
module com.example.greeting.english {
    requires com.example.greeting.api;

    provides com.example.greeting.spi.GreetingService
        with com.example.greeting.english.EnglishGreeting;
}
~~~

File src/com.example.greeting.english/com/example/greeting/english/EnglishGreeting.java:

~~~java
package com.example.greeting.english;

import com.example.greeting.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Chú ý rằng module descriptor không có dòng exports com.example.greeting.english. Package implementation được giữ kín đối với truy cập Java thông thường từ module khác.

### 6.4. Module consumer

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeting.api;
    uses com.example.greeting.spi.GreetingService;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeting.spi.GreetingService;

import java.util.Iterator;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        Iterator<GreetingService> providers = loader.iterator();

        if (!providers.hasNext()) {
            throw new IllegalStateException(
                    "No GreetingService provider found"
            );
        }

        GreetingService greeting = providers.next();
        System.out.println(greeting.greet("Ada"));
    }
}
~~~

### 6.5. Biên dịch và chạy trên Java 17+

Từ thư mục chứa src, tạo thư mục đầu ra rồi biên dịch cả ba module:

~~~bash
mkdir -p out
javac -d out --module-source-path src -m com.example.greeting.api,com.example.greeting.english,com.example.app
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out --module-source-path src -m com.example.greeting.api,com.example.greeting.english,com.example.app
~~~

Chạy consumer trên module path:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả stdout:

~~~text
Hello, Ada!
~~~

Module provider được đặt trên module path cùng với module API và consumer. Khi module system phân giải ứng dụng có khai báo uses, provider module có khai báo provides phù hợp có thể được đưa vào cấu hình dịch vụ. Consumer không phải khai báo requires trực tiếp tới provider.

### 6.6. Thay provider mà không sửa consumer

Giả sử bổ sung module com.example.greeting.french với implementation:

~~~java
package com.example.greeting.french;

import com.example.greeting.spi.GreetingService;

public final class FrenchGreeting implements GreetingService {
    public FrenchGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Bonjour, " + name + "!";
    }
}
~~~

Module descriptor:

~~~java
module com.example.greeting.french {
    requires com.example.greeting.api;

    provides com.example.greeting.spi.GreetingService
        with com.example.greeting.french.FrenchGreeting;
}
~~~

Chỉ cần thêm module provider vào module path và cấu hình triển khai. Consumer vẫn dùng GreetingService và ServiceLoader; không cần import hoặc biết tên FrenchGreeting.

Nếu đồng thời đặt cả hai provider trên module path, ServiceLoader có thể trả về cả hai implementation. Consumer cần quy tắc chọn provider phù hợp thay vì giả định provider đầu tiên luôn là provider mong muốn.

## 7. Dùng ServiceLoader với classpath

JPMS không loại bỏ cách đăng ký service truyền thống trên classpath. Với ứng dụng hoặc thư viện chưa chuyển sang named module, provider có thể được đăng ký trong file cấu hình:

~~~text
META-INF/services/com.example.greeting.spi.GreetingService
~~~

Nội dung file là tên đầy đủ của từng lớp provider, mỗi lớp trên một dòng:

~~~text
com.example.greeting.english.EnglishGreeting
~~~

Sau đó consumer có thể dùng ServiceLoader.load(GreetingService.class) như bình thường, với service interface và provider nằm trên classpath phù hợp.

Cần phân biệt hai cơ chế:

| Môi trường | Cách khai báo provider |
|---|---|
| Named module | Directive provides Service with Provider trong module-info.java |
| Classpath | File META-INF/services/<tên-đầy-đủ-của-service> |

Khi chuyển thư viện sang JPMS, nên dùng descriptor module cho provider được đóng gói thành named module. File META-INF/services vẫn có vai trò tương thích với classpath và hệ sinh thái thư viện chưa modular hóa.

## 8. Vòng đời, lỗi và lưu ý khi dùng ServiceLoader

### 8.1. Không có provider

Nếu không tìm thấy provider, iterator không có phần tử. Consumer cần xử lý trường hợp này rõ ràng. Ví dụ có thể ném IllegalStateException, dùng implementation dự phòng hoặc thông báo rằng tính năng không được cấu hình.

### 8.2. Provider không hợp lệ hoặc không thể khởi tạo

ServiceLoader có thể ném ServiceConfigurationError khi cấu hình provider không hợp lệ, provider không thỏa điều kiện tạo instance hoặc quá trình nạp provider gặp lỗi. Hãy kiểm tra:

- Service type được khai báo trong uses có đúng không.
- Provider module có provides đúng service interface không.
- Provider module có đọc được module API không.
- Provider class có đáp ứng quy tắc constructor hoặc provider method không.
- Provider module có được đặt trên module path và được module system phân giải không.

### 8.3. ServiceLoader có trạng thái và cache

Một ServiceLoader lưu cache những provider đã được nạp trong vòng đời của loader. reload() xóa cache để loader có thể tìm lại provider theo cấu hình hiện tại.

ServiceLoader không được thiết kế để nhiều thread dùng chung mà không đồng bộ. Nếu cần truy cập đồng thời, hãy tạo loader riêng theo luồng hoặc đồng bộ hóa cách sử dụng phù hợp.

### 8.4. Không dùng tên implementation làm hợp đồng

Nếu consumer kiểm tra tên lớp EnglishGreeting, import class đó hoặc khai báo requires tới module provider, consumer lại bị gắn với implementation cụ thể.

Hãy đặt thông tin cần lựa chọn vào hợp đồng service hoặc cấu hình bên ngoài. Tên implementation nên là chi tiết có thể thay đổi.

### 8.5. Không export package provider chỉ để ServiceLoader tìm thấy

Trong named module, khai báo provides là cơ chế đăng ký provider. Package chứa provider class không cần được export cho consumer. Export package implementation sẽ mở rộng bề mặt API và khiến các module khác dễ phụ thuộc vào chi tiết nội bộ.

## 9. Khi nào nên tách service interface?

Mô hình dịch vụ phù hợp khi:

- Có nhiều implementation cho cùng một chức năng.
- Ứng dụng cần chọn provider theo môi trường hoặc cấu hình triển khai.
- Provider có thể được phát triển độc lập với consumer.
- Muốn thay thế thư viện hoặc tích hợp plugin mà không sửa mã consumer.
- Muốn module API nhỏ, ổn định và không kéo dependency của implementation vào ứng dụng.

Không cần dùng ServiceLoader cho mọi lời gọi nội bộ. Nếu ứng dụng luôn chỉ có một implementation cố định và không cần khả năng thay thế hoặc phát hiện provider, dependency trực tiếp có thể đơn giản hơn. Dùng service abstraction khi nó giải quyết nhu cầu mở rộng hoặc giảm phụ thuộc thực sự.

## 10. Checklist thiết kế dịch vụ JPMS

- [ ] Service interface nằm trong module API riêng hoặc package API được export.
- [ ] API không để lộ kiểu nội bộ của provider.
- [ ] Consumer khai báo requires tới module API.
- [ ] Consumer khai báo uses cho service interface.
- [ ] Provider khai báo requires tới module API.
- [ ] Provider khai báo provides ... with ... đúng service và implementation.
- [ ] Provider class đáp ứng quy tắc constructor hoặc provider method của JPMS.
- [ ] Package implementation không export nếu consumer không cần truy cập trực tiếp.
- [ ] Provider module có mặt trong module path/cấu hình triển khai.
- [ ] Consumer xử lý trường hợp không có provider và lỗi khởi tạo.
- [ ] Không giả định thứ tự provider nếu có nhiều implementation.
- [ ] Có kiểm thử chạy ứng dụng với provider mong đợi và khi provider vắng mặt.

## 11. Tài liệu tham khảo

- [Java SE 26 API — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): API phát hiện, duyệt và khởi tạo service provider.
- [Java Language Specification, Java SE 26 — Service Provider Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.4): quy tắc uses, provides và khai báo provider trong module descriptor.
- [Java Platform Module System — Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): cú pháp và ngữ nghĩa của module declaration.
