# uses khai báo service consumer

## 1. Service consumer và vai trò của uses

Java Platform Module System (JPMS) hỗ trợ mô hình **service** để một module có thể sử dụng chức năng do module khác cung cấp mà không phải phụ thuộc trực tiếp vào class triển khai cụ thể.

Trong mô hình này có ba thành phần:

- **Service type**: interface hoặc abstract class mô tả hợp đồng mà các implementation phải tuân theo.
- **Service consumer**: module cần sử dụng chức năng và khai báo chỉ thị uses cho service type.
- **Service provider**: module cung cấp implementation và đăng ký nó bằng chỉ thị provides ... with ....

Chỉ thị **uses** trong module descriptor khai báo rằng module hiện tại là consumer của một service type:

~~~java
module com.acme.application {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

Khai báo này cho biết module ứng dụng cần service GreetingService. Nó không chỉ định implementation nào sẽ được dùng và cũng không tạo requires trực tiếp tới từng module provider.

Nhờ vậy, consumer phụ thuộc vào hợp đồng service ổn định. Provider có thể được thay thế hoặc bổ sung mà không cần sửa mã consumer, miễn là implementation tuân thủ hợp đồng và được đăng ký hợp lệ.

## 2. uses khác requires như thế nào?

Hai chỉ thị có mục đích khác nhau:

- **requires** tạo quan hệ đọc giữa module hiện tại và module khác. Consumer cần requires module chứa service type để có thể tham chiếu interface hoặc abstract class trong mã nguồn.
- **uses** khai báo nhu cầu sử dụng một service type. Nó cho phép cơ chế service loading biết module nào đang tiêu thụ service và là một phần của hợp đồng module.

Ví dụ:

~~~java
module com.acme.application {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

Consumer cần requires com.acme.greeting.api vì GreetingService là type nằm trong module API. Consumer không cần requires com.acme.greeting.provider chỉ để tìm implementation.

Quan hệ khái quát:

~~~text
com.acme.application
    | requires
    v
com.acme.greeting.api
    |
    | exports package chứa GreetingService
    v
GreetingService (service contract)

com.acme.greeting.application
    | uses GreetingService
    |
    | ServiceLoader tìm provider
    v
Provider được đăng ký bởi module triển khai
~~~

uses không thay thế requires tới module chứa service type. Ngược lại, requires module API cũng không tự khai báo rằng consumer muốn sử dụng service qua ServiceLoader.

## 3. Khai báo service type trong module API

Service type nên là một hợp đồng nhỏ, ổn định và được đặt trong package công khai của module API.

Ví dụ cấu trúc:

~~~text
src/
└── com.acme.greeting.api/
    ├── module-info.java
    └── com/acme/greeting/api/
        └── GreetingService.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.api {
    exports com.acme.greeting.api;
}
~~~

Service interface:

~~~java
package com.acme.greeting.api;

public interface GreetingService {
    String greet(String name);
}
~~~

Module API export package để consumer và provider có thể tham chiếu GreetingService. Module API không cần biết implementation nào sẽ được nạp.

Service type cũng có thể là abstract class nếu hợp đồng cần kế thừa trạng thái hoặc hành vi dùng chung. Tuy nhiên, interface thường phù hợp hơn cho một điểm mở rộng service vì nó tách hợp đồng khỏi implementation.

Một service contract tốt nên:

- Chỉ chứa những method mà consumer thực sự cần.
- Dùng kiểu dữ liệu công khai và ổn định trong chữ ký method.
- Hạn chế phụ thuộc vào package nội bộ của provider.
- Định nghĩa rõ ý nghĩa tham số, kết quả và lỗi có thể phát sinh.
- Tránh để consumer phải biết class triển khai hoặc cách khởi tạo provider.

## 4. Consumer khai báo uses và gọi ServiceLoader

Consumer khai báo phụ thuộc tới module API và service mà nó sử dụng:

~~~text
src/
└── com.acme.greeting.consumer/
    ├── module-info.java
    └── com/acme/greeting/consumer/
        └── Main.java
~~~

Module descriptor:

~~~java
module com.acme.greeting.consumer {
    requires com.acme.greeting.api;
    uses com.acme.greeting.api.GreetingService;
}
~~~

Mã consumer dùng ServiceLoader để tìm các implementation:

~~~java
package com.acme.greeting.consumer;

import com.acme.greeting.api.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;

        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet("Phuong"));
        }

        if (!found) {
            System.out.println("Chưa có GreetingService provider");
        }
    }
}
~~~

ServiceLoader là API chuẩn của Java để tìm và nạp các provider đã đăng ký. Consumer không cần tự quét classpath, tự tìm tên class implementation hoặc gọi constructor của một class cụ thể.

Trong named module, module gọi ServiceLoader phải khai báo uses cho service type. Nếu thiếu uses, việc tải service có thể thất bại với ServiceConfigurationError vì module chưa khai báo nhu cầu sử dụng service đó.

Có thể duyệt tất cả provider bằng vòng lặp như ví dụ trên. ServiceLoader tải provider theo nhu cầu khi duyệt, nên không nhất thiết khởi tạo tất cả implementation ngay tại thời điểm gọi load.

## 5. Provider đăng ký implementation bằng provides

Module provider phụ thuộc vào module API vì implementation phải triển khai GreetingService:

~~~text
src/
└── com.acme.greeting.provider/
    ├── module-info.java
    └── com/acme/greeting/provider/impl/
        └── VietnameseGreetingService.java
~~~

Module descriptor đăng ký implementation:

~~~java
module com.acme.greeting.provider {
    requires com.acme.greeting.api;

    provides com.acme.greeting.api.GreetingService
        with com.acme.greeting.provider.impl.VietnameseGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.greeting.provider.impl;

import com.acme.greeting.api.GreetingService;

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

Chỉ thị provides ... with ... nằm trong module descriptor của provider. Nó đăng ký rằng module này cung cấp implementation cho service type đã nêu.

Với provider class theo cách triển khai thông thường, class implementation phải public, không abstract và có public constructor không tham số để ServiceLoader có thể tạo instance. Java cũng hỗ trợ provider method public static tên provider trong provider class; cách này hữu ích khi việc tạo service cần factory hoặc cấu hình riêng.

Package chứa implementation không cần export chỉ để ServiceLoader tìm provider của named module. Consumer chỉ cần biết service type công khai; chi tiết implementation vẫn có thể được giữ bên trong module provider.

## 6. Quan hệ giữa ba module

Một ví dụ đầy đủ có ba module độc lập:

~~~text
com.acme.greeting.api
    exports com.acme.greeting.api
    └── GreetingService

com.acme.greeting.provider
    requires com.acme.greeting.api
    provides GreetingService with VietnameseGreetingService

com.acme.greeting.consumer
    requires com.acme.greeting.api
    uses GreetingService
    └── Main -> ServiceLoader
~~~

Điểm quan trọng là consumer và provider cùng phụ thuộc vào API module, nhưng không phụ thuộc trực tiếp vào nhau:

- API module sở hữu service contract.
- Consumer module khai báo nhu cầu qua uses.
- Provider module đăng ký implementation qua provides.
- ServiceLoader kết nối consumer với các provider có sẵn trong môi trường module layer.

Có thể có nhiều provider cho cùng một service type. Consumer có thể duyệt tất cả, chọn theo metadata hoặc áp dụng chính sách riêng. Không nên dựa vào thứ tự provider được tìm thấy nếu thứ tự đó không phải một phần của hợp đồng ứng dụng.

## 7. Biên dịch và chạy ví dụ modular

Với cấu trúc nguồn đặt trong các thư mục module như trên, có thể biên dịch cả ba module bằng:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.greeting.api,com.acme.greeting.consumer,com.acme.greeting.provider
~~~

Sau khi biên dịch, thư mục mods có các thư mục module tương ứng:

~~~text
mods/
├── com.acme.greeting.api/
├── com.acme.greeting.consumer/
└── com.acme.greeting.provider/
~~~

Chạy consumer:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.greeting.consumer/com.acme.greeting.consumer.Main
~~~

Trong quá trình phân giải module, Java có thể thực hiện service binding để đưa các module provider phù hợp vào cấu hình khi chúng nằm trên module path và cung cấp service mà module đã phân giải sử dụng. Tùy cấu hình chạy và module layer tự tạo, có thể cần bổ sung provider module làm root hoặc cấu hình rõ các module cần đưa vào layer.

Tùy chọn --show-module-resolution giúp quan sát module nào được phân giải và hỗ trợ chẩn đoán khi provider không xuất hiện như mong đợi.

## 8. ServiceLoader và module layer

ServiceLoader không chỉ làm việc với boot layer. Ứng dụng có thể tạo module layer riêng để nạp plugin hoặc nhóm provider độc lập.

Khi đã có một ModuleLayer, có thể tìm service trong layer đó:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Cách này hữu ích khi ứng dụng cần nạp plugin sau khi khởi động, tách nhóm provider theo module layer hoặc kiểm soát vòng đời của cấu hình module.

Cần phân biệt:

- Module layer chứa cấu hình module đã được phân giải.
- ServiceLoader tìm provider được đăng ký trong phạm vi layer hoặc class loader tương ứng với overload được sử dụng.
- Việc một JAR nằm trên đĩa không tự đảm bảo provider sẽ được nhìn thấy trong layer đang truy vấn.

Khi tự tạo layer, cần xác định module root, module finder, configuration và class loader đúng với thiết kế plugin. Nếu provider không được tìm thấy, hãy kiểm tra layer mà ServiceLoader đang truy vấn và xem provider module đã được đưa vào cấu hình layer chưa.

## 9. Nhiều provider và xử lý trường hợp không có provider

Một service có thể có nhiều implementation:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

Nếu ứng dụng cần chọn đúng một provider, hãy xác định chính sách chọn rõ ràng. Ví dụ, có thể dùng cấu hình ứng dụng để chọn provider theo tên hoặc đặc tính nghiệp vụ, thay vì phụ thuộc thứ tự duyệt.

Nếu không tìm thấy provider, ServiceLoader không nhất thiết ném lỗi chỉ vì danh sách rỗng. Consumer nên quyết định hành vi phù hợp: dùng fallback, bỏ qua chức năng tùy chọn hoặc báo lỗi cấu hình nếu service là bắt buộc.

Khi duyệt provider, các lỗi cấu hình hoặc lỗi tạo instance có thể xuất hiện dưới dạng ServiceConfigurationError. Cần xem nguyên nhân gốc, chẳng hạn provider class không hợp lệ, thiếu constructor phù hợp, không triển khai service type hoặc dependency của provider không có trong runtime.

## 10. Service trên classpath và META-INF/services

Mô hình service có trước JPMS vẫn hoạt động với ứng dụng classpath. Khi consumer và provider nằm trên classpath, consumer thường không khai báo uses trong module descriptor vì classpath thuộc unnamed module.

Provider truyền thống đăng ký bằng file cấu hình:

~~~text
META-INF/services/com.acme.greeting.api.GreetingService
~~~

Nội dung file liệt kê tên đầy đủ của từng implementation, mỗi dòng một provider:

~~~text
com.acme.greeting.provider.impl.VietnameseGreetingService
com.acme.greeting.provider.impl.EnglishGreetingService
~~~

Consumer vẫn có thể dùng:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);
~~~

Khi chuyển sang named modules, việc đăng ký provider được thể hiện rõ trong module-info.java bằng provides ... with ..., còn nhu cầu của consumer được thể hiện bằng uses. Đây là metadata có cấu trúc, giúp công cụ Java và module system hiểu quan hệ service mà không phải dựa hoàn toàn vào file cấu hình trong JAR.

Không nên đăng ký cùng một provider theo nhiều cách một cách tùy tiện. Hãy chọn mô hình phù hợp với cách đóng gói và class loader/module layer mà ứng dụng sử dụng.

## 11. Lỗi thường gặp khi dùng uses

**Consumer quên khai báo uses**

Module gọi ServiceLoader cho một service nhưng module descriptor không có uses tương ứng. Bổ sung đúng service type vào module-info.java của consumer.

**Consumer thiếu requires tới module API**

Consumer khai báo uses nhưng không đọc được module chứa service type. Bổ sung requires tới module API và bảo đảm module API export package chứa service type.

**Provider không khai báo provides**

Implementation class tồn tại trong JAR nhưng named module không đăng ký service bằng provides. Thêm provides ServiceType with ProviderImplementation vào module descriptor của provider.

**Provider module không được phân giải hoặc không nằm trong layer đang tìm kiếm**

Kiểm tra module path, module root, service binding và module layer được truyền cho ServiceLoader. Một provider ở layer khác sẽ không tự động xuất hiện trong mọi lần truy vấn.

**Provider implementation không hợp lệ**

Kiểm tra implementation có tương thích với service type và có cách tạo instance hợp lệ hay không. Với provider class thông thường, cần public class và public constructor không tham số; với provider method, kiểm tra phương thức provider public static không tham số và kiểu trả về phù hợp.

**Service type không phải API dùng chung**

Nếu package chứa service type không được export hoặc provider/consumer không đọc được module API, các module không thể cùng tham chiếu hợp đồng. Đặt service type trong package API được export và khai báo requires ở cả consumer lẫn provider.

**Consumer phụ thuộc trực tiếp vào implementation**

Nếu consumer import implementation class hoặc tự gọi constructor provider, tính thay thế của service bị mất. Consumer nên chỉ tham chiếu service type và dùng ServiceLoader để tìm provider.

## 12. Nguyên tắc thiết kế service consumer

Khi viết module consumer, nên áp dụng các nguyên tắc:

- Khai báo uses cho đúng service type mà module thực sự tiêu thụ.
- Chỉ requires module chứa service contract và những dependency trực tiếp khác mà mã cần.
- Không khai báo requires tới từng provider chỉ để dùng ServiceLoader.
- Định nghĩa hành vi rõ ràng khi không có provider hoặc có nhiều provider.
- Không giả định thứ tự provider là ổn định nếu không có hợp đồng quy định.
- Dùng module layer rõ ràng khi cần plugin có vòng đời hoặc phạm vi riêng.
- Giữ service type trong package API được export và hạn chế để lộ implementation detail.
- Xử lý ServiceConfigurationError để thông báo lỗi đăng ký provider có ý nghĩa.

Một consumer tốt biết nó cần chức năng nào và hợp đồng nào, nhưng không cần biết class cụ thể nào sẽ thực hiện chức năng đó.

## 13. Ghi nhớ

- uses khai báo service consumer trong module descriptor.
- requires tạo quan hệ đọc tới module chứa service type; uses khai báo nhu cầu sử dụng service.
- Provider đăng ký implementation bằng provides ServiceType with Implementation.
- ServiceLoader tìm và nạp provider, giúp consumer không phụ thuộc trực tiếp vào class triển khai.
- Package chứa service type cần được export để consumer và provider truy cập hợp đồng.
- Package implementation của provider có thể giữ không export.
- Named module cần khai báo uses; ứng dụng classpath truyền thống có thể đăng ký provider bằng META-INF/services.
- Module layer quyết định phạm vi provider có thể được tìm thấy khi dùng ServiceLoader với layer cụ thể.

Khi cần mở rộng ứng dụng bằng plugin hoặc nhiều implementation, hãy thiết kế service contract độc lập, khai báo uses ở consumer và provides ở provider. Cách tổ chức này giúp thay đổi implementation mà không phải sửa mã sử dụng service.
