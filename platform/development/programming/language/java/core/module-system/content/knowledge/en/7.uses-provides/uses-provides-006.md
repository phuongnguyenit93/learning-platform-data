# Provider module không export implementation package

Java Platform Module System (JPMS) cho phép một module công bố dịch vụ mà không phải công khai package chứa class triển khai dịch vụ đó. Đây là một điểm quan trọng của cơ chế **ServiceLoader**: module tiêu thụ biết hợp đồng dịch vụ, module cung cấp đăng ký implementation bằng chỉ thị **provides ... with ...**, còn package implementation có thể giữ kín bằng cách không khai báo **exports**.

Cách tổ chức này tách API khỏi implementation. Người dùng dịch vụ phụ thuộc vào interface ổn định; nhà cung cấp có thể thay class triển khai hoặc cấu trúc package nội bộ mà không buộc module tiêu thụ tham chiếu trực tiếp đến các class đó.

## 1. Ba vai trò trong một kiến trúc dịch vụ

Một ứng dụng modular dùng service provider thường có ba vai trò:

- **Service API module** định nghĩa interface hoặc abstract service type và export package API.
- **Provider module** cài đặt service và đăng ký implementation trong module descriptor bằng **provides**.
- **Consumer module** khai báo **uses** để cho biết nó cần dịch vụ và tìm provider bằng **ServiceLoader**.

Luồng phụ thuộc có dạng:

~~~text
             requires
Consumer -----------------> Service API
    |                           ^
    | uses Service              | implements
    v                           |
 ServiceLoader             Provider module
                                |
                                | provides API with Implementation
                                v
                      internal implementation package
                      (not exported)
~~~

Consumer cần biết interface dịch vụ, nhưng không cần biết tên class triển khai hoặc package nội bộ của provider. Provider phụ thuộc vào service API để triển khai hợp đồng. Việc đăng ký provider được thực hiện qua module descriptor.

## 2. Tạo service API module

Giả sử dịch vụ cần cung cấp lời chào. Tạo module **com.acme.greeter.api** với cấu trúc:

~~~text
src/
└── com.acme.greeter.api/
    ├── module-info.java
    └── com/acme/greeter/api/GreetingService.java
~~~

Descriptor:

~~~java
module com.acme.greeter.api {
    exports com.acme.greeter.api;
}
~~~

Interface dịch vụ:

~~~java
package com.acme.greeter.api;

public interface GreetingService {
    String greet(String name);
}
~~~

Package API phải được export để các module consumer và provider có thể tham chiếu interface **GreetingService** trong mã nguồn. Đây là hợp đồng công khai của dịch vụ; nó không chứa class triển khai cụ thể.

Nên giữ API nhỏ và ổn định. Các module tiêu thụ chỉ cần phụ thuộc vào những kiểu được công bố trong package này, nhờ vậy provider có thể thay đổi nội bộ mà không làm lộ cấu trúc implementation.

## 3. Tạo provider module với package implementation kín

Tạo module **com.acme.greeter.provider**:

~~~text
src/
└── com.acme.greeter.provider/
    ├── module-info.java
    └── com/acme/greeter/provider/internal/
        └── VietnameseGreetingService.java
~~~

Descriptor provider:

~~~java
module com.acme.greeter.provider {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.provider.internal.VietnameseGreetingService;
}
~~~

Class triển khai:

~~~java
package com.acme.greeter.provider.internal;

import com.acme.greeter.api.GreetingService;

public final class VietnameseGreetingService
        implements GreetingService {

    public VietnameseGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Điểm cần chú ý là descriptor provider **không có** dòng:

~~~java
exports com.acme.greeter.provider.internal;
~~~

Package **com.acme.greeter.provider.internal** vẫn là package nội bộ của provider module. Class triển khai có thể là **public** và có public constructor không tham số để đáp ứng quy tắc provider class của ServiceLoader, nhưng các module khác không thể import class này qua module boundary vì package chưa được export.

Chỉ thị **provides ... with ...** đăng ký class implementation làm provider cho service type đã nêu. JPMS và ServiceLoader sử dụng khai báo này để phát hiện và tạo provider. Việc đăng ký không yêu cầu export package implementation.

## 4. Tạo consumer module

Consumer chỉ cần biết service API. Cấu trúc:

~~~text
src/
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Descriptor:

~~~java
module com.acme.app {
    requires com.acme.greeter.api;
    uses com.acme.greeter.api.GreetingService;
}
~~~

**requires** cho phép consumer đọc module chứa interface dịch vụ. **uses** khai báo rằng module này tiêu thụ service type **GreetingService**. Chỉ thị **uses** không phải dependency đến một provider cụ thể.

Lớp main tìm và gọi các provider:

~~~java
package com.acme.app;

import com.acme.greeter.api.GreetingService;

import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java Module System" : args[0];

        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService service : loader) {
            System.out.println(service.greet(name));
        }
    }
}
~~~

Consumer không import **VietnameseGreetingService**, không gọi constructor của implementation và không cần khai báo **requires com.acme.greeter.provider**. Nó làm việc với interface và để ServiceLoader tìm provider đã đăng ký trong module layer.

## 5. Biên dịch và chạy ví dụ

Từ thư mục dự án, biên dịch cả ba module bằng JDK 21:

~~~bash
javac -d out --module-source-path src \
    -m com.acme.greeter.api,com.acme.greeter.provider,com.acme.app
~~~

Có thể biên dịch trên một dòng trong terminal nếu môi trường không hỗ trợ dấu nối dòng như ví dụ.

Khi chạy, provider module phải được phân giải vào module layer cùng với consumer. Với các module provider nằm trên module path, dùng tùy chọn **--bind-services** để yêu cầu launcher phân giải các module cung cấp dịch vụ mà những module đã chọn sử dụng:

~~~bash
java --module-path out --bind-services \
    --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Xin chào, Java Module System!
~~~

Nếu provider không được đưa vào module layer, ServiceLoader không thể phát hiện nó trong layer đó. **--bind-services** hỗ trợ launcher liên kết các provider trên module path cho service mà module gốc khai báo **uses**. Trong cấu hình module layer tự tạo bằng API, ứng dụng hoặc bootstrap code cần thực hiện service binding phù hợp khi resolve configuration.

Điểm quan trọng là consumer không cần compile-time dependency vào provider module. Provider được chọn thông qua service contract và cơ chế binding của module system.

## 6. Vì sao implementation package không cần export?

Trong cách gọi class thông thường, một module khác muốn import kiểu từ package của provider phải đọc module provider và package đó phải được export. Tuy nhiên, ServiceLoader dùng metadata đăng ký provider trong module descriptor để tìm implementation.

JPMS cho phép provider class được khai báo trong **provides ... with ...** dù package chứa class không export. Cơ chế service provider là một điểm tích hợp được module system hỗ trợ trực tiếp; nó không yêu cầu công khai implementation package thành API.

Điều này mang lại một số lợi ích:

- **Ẩn chi tiết triển khai:** consumer không thể import class implementation qua module boundary.
- **Tự do thay đổi nội bộ:** provider có thể đổi class, chia package hoặc tái cấu trúc implementation mà không đổi service API.
- **Giảm coupling:** consumer chỉ phụ thuộc interface, không phụ thuộc nhà cung cấp cụ thể.
- **Hỗ trợ nhiều provider:** nhiều module có thể đăng ký implementation cho cùng một service type.
- **Kiểm soát bề mặt API:** chỉ package contract được export; package nội bộ vẫn được encapsulate.

Đừng nhầm việc class provider được khai báo **public** với việc package chứa nó đã được export. Modifier **public** điều khiển khả năng truy cập theo Java language access rules; module descriptor tiếp tục kiểm soát package visibility qua module boundary.

## 7. Quy tắc đối với provider class

Với provider class truyền thống được khai báo trong **provides ... with ...**, class phải là public và có public constructor không tham số để ServiceLoader có thể tạo instance:

~~~java
public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Class có thể nằm trong package không export. Provider module chỉ cần khai báo:

~~~java
provides com.acme.greeter.api.GreetingService
    with com.acme.greeter.provider.internal.DefaultGreetingService;
~~~

Một lựa chọn khác là dùng provider method. Class provider được liệt kê trong descriptor có thể khai báo một phương thức **public static provider()** không tham số, trả về service type hoặc subtype:

~~~java
package com.acme.greeter.provider.internal;

import com.acme.greeter.api.GreetingService;

public final class GreetingProviderFactory {
    private GreetingProviderFactory() {
    }

    public static GreetingService provider() {
        return new VietnameseGreetingService();
    }
}
~~~

Descriptor khi đó tham chiếu factory:

~~~java
provides com.acme.greeter.api.GreetingService
    with com.acme.greeter.provider.internal.GreetingProviderFactory;
~~~

Provider method hữu ích khi việc tạo service cần factory, cấu hình hoặc chọn implementation. Package factory vẫn có thể không export. Khi dùng provider method, lớp được khai báo trong **with** không cần trực tiếp implement service type; ServiceLoader gọi provider method theo quy tắc của nó.

## 8. Nhiều provider cho cùng một service

JPMS cho phép nhiều module cung cấp cùng một service API. Ví dụ:

~~~java
module com.acme.greeter.english {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.english.internal.EnglishGreetingService;
}
~~~

Và provider tiếng Việt:

~~~java
module com.acme.greeter.vietnamese {
    requires com.acme.greeter.api;

    provides com.acme.greeter.api.GreetingService
        with com.acme.greeter.vietnamese.internal.VietnameseGreetingService;
}
~~~

Mỗi provider giữ implementation package riêng tư. Consumer vẫn chỉ khai báo:

~~~java
uses com.acme.greeter.api.GreetingService;
~~~

ServiceLoader có thể trả về nhiều provider. Thứ tự provider không nên được dùng làm cơ chế chọn ngôn ngữ hoặc ưu tiên nghiệp vụ nếu ứng dụng cần một lựa chọn xác định. Hãy thêm metadata/cấu hình hoặc một lớp điều phối rõ ràng khi cần chọn provider cụ thể.

## 9. Provider module và consumer module không cần phụ thuộc trực tiếp nhau

Trong thiết kế service, provider module phụ thuộc vào service API; consumer module cũng phụ thuộc vào service API. Không cần tạo dependency trực tiếp từ consumer đến từng provider:

~~~text
com.acme.app
    requires com.acme.greeter.api
    uses GreetingService

com.acme.greeter.provider
    requires com.acme.greeter.api
    provides GreetingService with InternalImplementation
~~~

Nếu consumer khai báo **requires com.acme.greeter.provider** chỉ để gọi implementation, nó làm mất lợi ích thay thế provider và buộc ứng dụng biết chi tiết nhà cung cấp. Khi service contract đủ cho nhu cầu, hãy để ServiceLoader thực hiện discovery.

Trong hệ thống plugin, provider module có thể được cài đặt hoặc thêm vào module path theo cấu hình triển khai. Ứng dụng có thể mở rộng tập provider mà không phải thay đổi mã nguồn consumer, miễn là provider đáp ứng service contract và được resolve vào module layer.

## 10. Kiểm tra provider registration

Có thể kiểm tra descriptor của provider JAR:

~~~bash
jar --describe-module --file mods/com.acme.greeter.provider.jar
~~~

Kết quả cần thể hiện:

- Tên module provider.
- Dependency **requires com.acme.greeter.api**.
- Dòng **provides com.acme.greeter.api.GreetingService with ...**.
- Không có package implementation trong danh sách **exports**.

Có thể bật log phân giải module khi chạy:

~~~bash
java --show-module-resolution --module-path mods --bind-services \
    --module com.acme.app/com.acme.app.Main
~~~

Nếu ServiceLoader không tìm thấy provider, kiểm tra lần lượt:

1. Provider module có nằm trên module path hoặc trong nguồn module finder phù hợp không.
2. Module provider có được resolve vào cùng module layer với consumer không.
3. Consumer descriptor đã khai báo **uses** đúng service type chưa.
4. Provider descriptor đã khai báo **provides ... with ...** đúng tên service và implementation chưa.
5. Provider class có public constructor không tham số hoặc provider method hợp lệ không.
6. Provider có phụ thuộc đúng module service API và service type có cùng định danh module/class với consumer không.

Nếu class implementation bị lỗi package visibility khi consumer cố import trực tiếp, đó có thể là dấu hiệu consumer đang phụ thuộc vào implementation thay vì dùng service contract. Trong kiến trúc này, consumer không cần truy cập package nội bộ.

## 11. Phân phối và runtime image

Khi đóng gói các modular JAR, cần phát hành service API, consumer và các provider được chọn cho ứng dụng. Provider module có thể không nằm trong dependency khai báo trực tiếp của consumer, vì vậy cấu hình chạy và bước resolve cần bảo đảm các provider được liên kết.

Khi tạo runtime image bằng **jlink**, có thể dùng **--bind-services** để đưa các module provider cần thiết vào image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.acme.app \
    --bind-services \
    --output runtime
~~~

Trên Windows, module path dùng dấu chấm phẩy làm dấu phân cách:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --bind-services --output runtime
~~~

Chạy ứng dụng trong runtime image:

~~~bash
runtime/bin/java --module com.acme.app/com.acme.app.Main
~~~

Khi phân phối, hãy kiểm tra provider thật sự được resolve và service discovery hoạt động trong image cuối cùng. Một ứng dụng chạy thành công trong IDE chưa chứng minh rằng các provider đã được đưa vào gói phát hành.

## 12. Checklist thiết kế provider kín

Khi tạo service provider module, hãy kiểm tra:

- Service interface nằm trong package API được export từ service API module.
- Consumer khai báo **uses** đúng service type.
- Provider module khai báo **requires** service API module.
- Provider module đăng ký implementation bằng **provides ... with ...**.
- Provider class tuân thủ quy tắc public class/public no-arg constructor, hoặc dùng provider method hợp lệ.
- Package implementation không có **exports** nếu consumer không cần truy cập trực tiếp.
- Consumer không import implementation class và không khai báo dependency trực tiếp vào provider khi không cần.
- Provider module được resolve vào module layer khi chạy; dùng **--bind-services** khi launcher cần liên kết các provider trên module path.
- Runtime image hoặc gói phân phối cuối cùng chứa các provider cần thiết.

Một provider module tốt công bố service contract và giữ implementation package ở phạm vi nội bộ. **provides ... with ...** là cơ chế đăng ký chính thức cho phép ServiceLoader tìm implementation mà không cần export package chứa nó. Nhờ đó, consumer chỉ phụ thuộc API, provider có thể thay đổi cách triển khai và module system vẫn giữ được ranh giới đóng gói.