# Lộ trình học từ module descriptor đến custom ModuleLayer

Java Platform Module System (JPMS) đưa cấu trúc module vào nền tảng Java từ JDK 9. Để học JPMS vững, nên đi từ mô tả module trong file module-info.java, hiểu cách compiler và JVM phân giải các module, sau đó mới chuyển sang dịch vụ và tạo ModuleLayer bằng API. Trình tự này giúp mỗi khái niệm mới dựa trên một mô hình đã hiểu, thay vì bắt đầu ngay với custom class loader hoặc các API cấu hình phức tạp.

Mục tiêu của lộ trình là có thể đọc và thiết kế module descriptor, biên dịch và chạy một ứng dụng modular, giải thích được module graph, dùng ServiceLoader, rồi nạp một nhóm module plugin vào một ModuleLayer riêng khi ứng dụng cần mở rộng ở runtime.

## 1. Bản đồ tổng thể

Một ứng dụng modular có thể được nhìn theo chuỗi xử lý sau:

~~~text
module-info.java và mã nguồn
          |
          v
Compiler kiểm tra dependency và quyền truy cập
          |
          v
Module descriptor trong module đã biên dịch
          |
          v
ModuleFinder tìm các module trên module path
          |
          v
Module resolution tạo Configuration / module graph
          |
          v
ModuleLayer định nghĩa module và gắn với class loader
          |
          v
Ứng dụng sử dụng class, reflection hoặc ServiceLoader
~~~

Các khái niệm có liên hệ nhưng đảm nhiệm những vai trò khác nhau:

- **Module descriptor** mô tả tên module, dependency, package được export hoặc open, và các service module sử dụng hoặc cung cấp.
- **Module path** là nơi tìm các module có thể tham gia vào quá trình phân giải.
- **Module resolution** xác định tập module cần thiết và quan hệ đọc giữa chúng.
- **ModuleLayer** là một miền runtime chứa các module đã được định nghĩa, có quan hệ cha với các layer khác.
- **ClassLoader** nạp định nghĩa class. Một layer có thể gắn các module với một class loader hoặc với các class loader được chọn theo chiến lược khác.

Đừng đồng nhất module với package, JAR hoặc class loader. Package là cách tổ chức tên và class; JAR là một định dạng đóng gói; module là đơn vị phụ thuộc và đóng gói API ở cấp nền tảng; class loader là cơ chế nạp class trong JVM.

## 2. Chặng 1 — Nắm mô hình module và ranh giới encapsulation

Trước khi viết descriptor, hãy hiểu vấn đề JPMS giải quyết. Với classpath truyền thống, thư viện thường được ghép thành một danh sách tìm kiếm. Package và class có thể bị truy cập rộng hơn dự định, dependency khó được mô tả rõ ở cấp nền tảng và việc trùng class có thể gây lỗi khó truy tìm.

JPMS bổ sung các ranh giới ở cấp module:

- Một **named module** có tên và descriptor.
- Một module có thể khai báo module khác mà nó cần đọc bằng directive **requires**.
- Package chỉ được module khác truy cập như API công khai khi được export phù hợp.
- Reflection sâu vào package có thể cần package được open.
- Các service có thể được khai báo bằng **uses** và **provides**.

Module có tên thường được tìm trên module path. Các class và JAR đặt trên classpath thuộc unnamed module của class loader tương ứng. Java vẫn hỗ trợ classpath, vì vậy một ứng dụng có thể chuyển đổi từng phần, nhưng khi đã chạy trên module path thì các quy tắc đọc module và truy cập package sẽ được áp dụng.

Ở chặng này, hãy tự trả lời được ba câu hỏi:

1. Package nào thuộc module nào?
2. Module nào cần đọc module nào?
3. Package nào là API công khai, package nào cần được giữ đóng?

## 3. Chặng 2 — Đọc và viết module descriptor

File module-info.java nằm ở gốc source của một module. Ví dụ:

~~~java
module com.example.billing {
    requires java.logging;

    exports com.example.billing.api;
    opens com.example.billing.model;
}
~~~

Descriptor trên khai báo module tên **com.example.billing**, phụ thuộc vào module nền tảng **java.logging**, export package API và open package model cho cơ chế reflection phù hợp.

Các directive cần học theo thứ tự sau:

| Directive | Ý nghĩa | Câu hỏi thiết kế |
| --- | --- | --- |
| requires | Khai báo module dependency mà module hiện tại cần đọc | Module này cần kiểu hoặc API từ module nào? |
| requires transitive | Truyền khả năng đọc dependency tới module phụ thuộc vào module hiện tại | Dependency nào là một phần của API mà người dùng module phải đọc? |
| requires static | Dependency cần khi biên dịch nhưng có thể không hiện diện ở runtime | Có dependency tùy chọn nào chỉ cần cho compile-time? |
| exports | Cho phép module khác truy cập các kiểu public trong package được export | Package nào là API công khai? |
| exports ... to | Chỉ export package cho một số module được nêu tên | Có API nào chỉ dành cho một nhóm module tin cậy? |
| opens | Cho phép truy cập sâu bằng reflection vào package | Framework có cần đọc hoặc ghi field, constructor không public? |
| opens ... to | Chỉ mở package cho một số module | Framework nào thực sự cần quyền reflection? |
| uses | Khai báo module tiêu thụ một service | Module này cần tìm implementation của service nào? |
| provides ... with | Khai báo implementation cung cấp cho service | Module này cung cấp implementation nào? |

Một số điểm cần nhớ:

- **requires** tạo quan hệ đọc module; nó không tự export mọi package của dependency.
- **exports** cho phép truy cập các kiểu public của package đã nêu, nhưng không đồng nghĩa với mở mọi thành viên private cho reflection.
- **opens** phục vụ deep reflection; nó không phải cách thay thế cho exports khi mã nguồn module khác cần gọi API public theo cách thông thường.
- **requires transitive** nên dùng khi kiểu từ dependency xuất hiện trong API công khai của module hiện tại và người dùng API cần đọc dependency đó.
- **requires static** vẫn tạo dependency khi biên dịch. Ứng dụng phải bảo đảm dependency có mặt nếu runtime thực sự cần nó.
- Một module không thể export một phần package theo từng class. Ranh giới export được khai báo ở cấp package.

Hãy luyện bằng cách tạo hai module nhỏ: module API export một package chứa một class public; module ứng dụng requires module API và gọi class đó. Sau đó xóa exports hoặc requires để quan sát lỗi compiler. Bài tập này cho thấy JPMS kiểm tra quan hệ đọc và quyền truy cập ngay trong quá trình biên dịch.

## 4. Chặng 3 — Biên dịch và chạy trên module path

Sau khi hiểu descriptor, hãy học cách tổ chức source tree và dùng Java launcher. Với hai module:

~~~text
project/
└── src/
    ├── com.example.greeting.api/
    │   ├── module-info.java
    │   └── com/example/greeting/api/Greeting.java
    └── com.example.greeting.app/
        ├── module-info.java
        └── com/example/greeting/app/Main.java
~~~

Descriptor của module API:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Descriptor của module ứng dụng:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;
}
~~~

Biên dịch cả hai module từ thư mục project:

~~~bash
javac -d out --module-source-path src -m com.example.greeting.api,com.example.greeting.app
~~~

Sau khi biên dịch, thư mục out chứa các thư mục module đã biên dịch. Chạy ứng dụng:

~~~bash
java --module-path out -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Ở đây:

- **--module-source-path** cho compiler biết cấu trúc thư mục chứa source của nhiều module.
- **-m** khi biên dịch chọn các module cần biên dịch.
- **-d** chỉ định nơi ghi kết quả.
- **--module-path** cho Java launcher biết nơi tìm module đã biên dịch hoặc JAR modular.
- **-m module/class** chọn module và class main để khởi chạy.

Đường dẫn module source phải khớp với tên module trong cấu trúc source. Khi module đã được đóng gói thành JAR, JAR đó cũng có thể đặt trên module path. Một JAR có descriptor module rõ ràng là explicit module; JAR cũ không có descriptor có thể được xử lý như automatic module khi đặt trên module path. Automatic module hữu ích trong quá trình chuyển đổi, nhưng không nên xem nó là thiết kế đích cho mọi dependency.

Hãy chạy cùng ví dụ trên classpath và module path để nhận ra khác biệt. Trên classpath, package không được export theo descriptor và quan hệ requires không được dùng để tạo module graph. Trên module path, compiler và JVM áp dụng các quy tắc JPMS.

## 5. Chặng 4 — Hiểu module resolution và module graph

Module path chỉ cung cấp các vị trí để tìm module. Nó không có nghĩa mọi module nằm ở đó đều tự động được nạp. Khi khởi chạy một ứng dụng modular, JVM bắt đầu từ module gốc, đọc các directive requires và tìm dependency theo module path hoặc các module nền tảng. Quá trình đó tạo ra một cấu hình đã phân giải.

Module graph mô tả các module và quan hệ đọc giữa chúng. Nó giúp trả lời:

- Module nào thực sự tham gia vào ứng dụng?
- Dependency nào được yêu cầu trực tiếp hoặc gián tiếp?
- Module nào đọc được module nào?
- Vì sao một package public vẫn không truy cập được từ một module cụ thể?

Một vài lệnh hữu ích khi điều tra:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

~~~bash
jar --describe-module --file libs/example.jar
~~~

~~~bash
jdeps --module-path mods --module com.example.app
~~~

Lệnh đầu hiển thị thông tin phân giải module khi khởi chạy. Lệnh thứ hai đọc descriptor của một JAR. Lệnh thứ ba phân tích dependency của module. Các lệnh này giúp kiểm tra giả thuyết về dependency trước khi chuyển sang API runtime.

Ở chặng này, hãy phân biệt rõ **module path** với **module graph**: module path là nguồn tìm kiếm; module graph là kết quả quan hệ module được phân giải cho một cấu hình cụ thể.

## 6. Chặng 5 — Hiểu exports, opens và reflection

Một module có thể đọc module khác nhưng vẫn không truy cập được một package nếu package đó không được export. Đây là cơ chế encapsulation quan trọng của JPMS.

Ví dụ, module A khai báo:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module B có thể requires module A và sử dụng public type trong package api. Tuy nhiên, package com.example.domain.internal không được export nên module B không thể dùng các class public trong package đó như một API module thông thường.

Framework dùng reflection có thể cần truy cập constructor, field hoặc method không public. Trong trường hợp này, package tương ứng có thể cần được open:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.persistence;
}
~~~

Cần chọn đúng directive theo nhu cầu:

- Mã nguồn module khác gọi public API: dùng **exports**.
- Framework cần deep reflection: dùng **opens**.
- Chỉ một framework cần reflection: cân nhắc **opens ... to** để giới hạn module được cấp quyền.

Các tùy chọn như **--add-exports** và **--add-opens** trên dòng lệnh có thể giúp tương thích với thư viện cũ hoặc phục vụ chẩn đoán. Chúng nên được xem là biện pháp triển khai có chủ đích, không phải cách thay thế lâu dài cho descriptor được thiết kế đúng.

## 7. Chặng 6 — Dùng service và ServiceLoader

Service là bước chuyển từ dependency tĩnh sang khả năng tìm implementation theo hợp đồng. Module tiêu thụ khai báo **uses**; module cung cấp implementation khai báo **provides ... with**.

Ví dụ, module API định nghĩa service:

~~~java
package com.example.greeting.api;

public interface GreetingProvider {
    String message();
}
~~~

Descriptor của module API:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
~~~

Module ứng dụng sử dụng service:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingProvider;
}
~~~

Module plugin cung cấp implementation:

~~~java
module com.example.greeting.hello {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingProvider
        with com.example.greeting.hello.HelloGreetingProvider;
}
~~~

Ứng dụng có thể tìm provider bằng ServiceLoader:

~~~java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.message());
}
~~~

ServiceLoader tách hợp đồng API khỏi implementation. Module ứng dụng chỉ phụ thuộc vào service API; các module provider có thể được thêm hoặc thay thế theo cấu hình triển khai. Đây là nền tảng hữu ích cho kiến trúc plugin, adapter hoặc các implementation có thể lựa chọn.

Hãy xác nhận ba điều trước khi debug service:

1. Module tiêu thụ đã khai báo uses cho service.
2. Module provider đã khai báo provides với implementation hợp lệ.
3. Các module liên quan đã được phân giải và nằm trong phạm vi layer mà ServiceLoader đang tìm kiếm.

Khi dùng custom ModuleLayer, cần chọn đúng overload của ServiceLoader để tìm provider trong layer mong muốn. Lệnh **ServiceLoader.load(ServiceType.class)** gắn với ngữ cảnh class loader thông thường; **ServiceLoader.load(layer, ServiceType.class)** cho phép tìm provider trong một layer và các layer cha của nó.

## 8. Chặng 7 — Từ module graph tới ModuleLayer

Khi một ứng dụng cần nạp plugin hoặc nhóm module độc lập trong lúc đang chạy, chỉ đặt tất cả JAR lên module path lúc khởi động có thể chưa đủ. JPMS cung cấp API để tìm descriptor, phân giải module và định nghĩa module trong một layer mới.

Các thành phần quan trọng:

- **ModuleFinder** tìm module descriptor trong một hoặc nhiều vị trí, ví dụ thư mục plugin hoặc tập JAR.
- **Configuration** biểu diễn kết quả phân giải module: module nào được chọn và dependency của chúng.
- **ModuleLayer** định nghĩa các module từ configuration vào JVM và liên kết chúng với layer cha.
- **defineModulesWithOneLoader** tạo layer trong đó các module mới dùng chung một class loader được tạo theo API.
- **defineModules** cho phép cung cấp chiến lược ánh xạ module tới class loader tùy chỉnh khi kiến trúc cần kiểm soát chi tiết hơn.

Trình tự cơ bản là:

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
ModuleLayer.defineModulesWithOneLoader(...)
    |
    v
ServiceLoader.load(layer, ServiceType.class)
~~~

Ví dụ, ứng dụng đã chạy trong boot layer và muốn nạp plugin từ thư mục plugins:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.greeting.hello")
    );

ModuleLayer pluginLayer =
    parent.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

Ở đây, **ModuleFinder.of(Path.of("plugins"))** tìm các module trong thư mục plugin. Lời gọi **resolve** sử dụng configuration của parent làm bối cảnh, tìm module gốc được yêu cầu và các dependency cần thiết. Sau đó **defineModulesWithOneLoader** định nghĩa các module đã phân giải trong layer con.

Để ví dụ hoạt động, plugin phải có descriptor hợp lệ, tên module gốc phải khớp, module API mà plugin requires phải đọc được từ parent hoặc từ tập module được tìm thấy, và thư mục plugins phải chứa đúng JAR hoặc cấu trúc module. Module API của service nên được định nghĩa ở layer cha để ứng dụng và plugin cùng tham chiếu một kiểu service.

Sau khi tạo layer, tìm provider trong layer đó:

~~~java
ServiceLoader<GreetingProvider> providers =
    ServiceLoader.load(pluginLayer, GreetingProvider.class);

for (GreetingProvider provider : providers) {
    System.out.println(provider.message());
}
~~~

Đoạn mã minh họa ý tưởng nạp plugin, không phải một hệ thống plugin hoàn chỉnh. Ứng dụng thực tế cần xử lý lỗi khi thiếu module, sai phiên bản API, provider không khởi tạo được hoặc plugin không tương thích. Nếu plugin có dependency riêng, các dependency đó cũng phải có thể được phân giải từ module path được cung cấp.

## 9. Chặng 8 — Tạo custom ModuleLayer có kiểm soát

Sau khi chạy được ví dụ dùng một loader, hãy tìm hiểu khi nào cần custom class loader. Một layer có thể dùng một loader chung cho tất cả module trong layer, hoặc chiến lược ánh xạ loader khác khi cần cô lập việc nạp class theo nhóm plugin.

Trước khi viết custom loader, hãy xác định yêu cầu thực tế:

- Các plugin có cần dùng chung một bản API do parent layer cung cấp không?
- Plugin có thể có thư viện nội bộ trùng tên với plugin khác không?
- Có cần nạp hoặc gỡ nhóm plugin theo vòng đời riêng không?
- Có cần kiểm soát rõ module nào được nhìn thấy từ module nào không?
- Việc dùng loader chung có đủ cho yêu cầu triển khai không?

Nếu cần ánh xạ loader theo module, API **ModuleLayer.defineModules(Configuration, List<ModuleLayer>, Function<String, ClassLoader>)** cho phép cung cấp hàm chọn class loader theo tên module. Hàm này phải trả về class loader phù hợp cho từng module trong configuration. ModuleLayer vẫn chịu trách nhiệm định nghĩa module và thiết lập quan hệ layer; class loader thực hiện việc nạp class theo chiến lược được cung cấp.

Không nên coi custom ModuleLayer là sandbox bảo mật. Module encapsulation và class loader giúp quản lý dependency, khả năng đọc và phạm vi nạp class, nhưng chúng không thay thế cơ chế bảo mật tiến trình, quyền hệ điều hành hoặc cô lập tài nguyên. Nếu plugin là mã không tin cậy, cần thiết kế ranh giới tiến trình hoặc cơ chế thực thi an toàn phù hợp.

Cũng cần nhớ rằng danh tính một class trong JVM phụ thuộc vào tên class và class loader định nghĩa nó. Hai plugin có thể nạp hai class cùng tên nhưng do hai loader khác nhau định nghĩa; chúng không tự động tương thích kiểu với nhau. Với API dùng chung, hãy để các module plugin đọc và sử dụng cùng module API từ parent layer.

## 10. Bài tập theo từng mốc

| Mốc | Bài tập | Bằng chứng hoàn thành |
| --- | --- | --- |
| 1. Mô hình | Vẽ hai module API và app, chỉ ra package và dependency | Giải thích được module nào reads module nào |
| 2. Descriptor | Viết requires, exports, opens và thử thay đổi từng directive | Dự đoán và giải thích được lỗi compile/access |
| 3. Build | Biên dịch và chạy ứng dụng hai module bằng javac/java | Lệnh build và run tái lập được |
| 4. Resolution | Dùng --show-module-resolution, jar --describe-module và jdeps | Xác định được module gốc và dependency |
| 5. Encapsulation | Thử truy cập package không export và reflection vào package không open | Phân biệt được lỗi truy cập thông thường với deep reflection |
| 6. Service | Tạo một service API và ít nhất hai provider | Thay provider mà không sửa code tiêu thụ |
| 7. ModuleLayer | Nạp một provider từ thư mục plugin vào layer con | ServiceLoader tìm thấy provider trong layer được chọn |
| 8. Custom loader | Thử ánh xạ loader riêng cho từng nhóm module nếu có yêu cầu | Giải thích được class identity và quan hệ parent layer |

## 11. Lỗi học tập và debug thường gặp

**Module not found** thường cho biết module gốc hoặc dependency không nằm trong vị trí tìm kiếm mà compiler/JVM đang sử dụng, tên module không khớp, hoặc module path trỏ nhầm thư mục.

**Package is not visible** thường liên quan đến module chưa requires module sở hữu package, hoặc package chưa được export cho module gọi.

**IllegalAccessException** hoặc lỗi reflection có thể cho biết package chưa được open theo cách framework cần. Kiểm tra descriptor của module sở hữu class và module thực hiện reflection.

**ServiceLoader không tìm thấy provider** cần được kiểm tra theo cả ba lớp: uses/provides, module resolution và layer/class loader mà ServiceLoader đang tìm kiếm.

**ClassCastException giữa các plugin** có thể xảy ra khi API bị nạp thành hai định nghĩa class khác nhau bởi hai loader. Đặt API dùng chung ở parent layer và để plugin requires module API đó.

Khi debug, hãy ghi lại tên module, module path, module gốc, layer được dùng và class loader định nghĩa kiểu liên quan. Những dữ kiện này giúp phân biệt lỗi descriptor, lỗi resolution và lỗi runtime class loading.

## 12. Tiêu chí hoàn thành lộ trình

Bạn đã nắm được lộ trình này khi có thể tự xây dựng một ứng dụng gồm module API, module ứng dụng và module provider; biên dịch, chạy và quan sát module graph; giải thích được vì sao exports khác opens; tìm service bằng ServiceLoader; và nạp provider từ thư mục plugin bằng một ModuleLayer con.

Ở mức nâng cao, bạn cần giải thích được vai trò riêng của ModuleFinder, Configuration, ModuleLayer và ClassLoader, đồng thời xác định được khi nào một loader chung là đủ và khi nào mới cần ánh xạ loader tùy chỉnh. Khi đã làm được điều đó, bạn có thể thiết kế hệ thống modular có plugin mà vẫn kiểm soát được dependency, API công khai và nguồn class được nạp.
