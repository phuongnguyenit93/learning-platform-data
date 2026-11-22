# Module path và vai trò của module-info.java trong JPMS

Từ Java 9, Java Platform Module System (JPMS) bổ sung một mô hình module có tên, khai báo dependency và kiểm soát package được công khai. Khi chạy ứng dụng theo JPMS, JVM có thể tìm module trên **module path**, đọc mô tả module và xây dựng một đồ thị module có quan hệ đọc rõ ràng.

Hai thành phần cần hiểu cùng nhau là:

- **Module path**: nơi Java tìm các module cần thiết cho compile hoặc runtime.
- **`module-info.java`**: file mô tả danh tính module, module mà nó cần, package mà nó công khai, package mở cho reflection và các service mà nó sử dụng hoặc cung cấp.

Module path không chỉ là một cách viết khác của classpath. Classpath tập hợp class và resource theo cơ chế truyền thống; module path giúp JVM nhận diện ranh giới module và áp dụng quy tắc đọc, xuất package và truy cập. Một project có thể dùng module path, classpath hoặc kết hợp cả hai trong quá trình chuyển đổi.

## 1. JPMS giải quyết vấn đề gì?

Trước JPMS, ứng dụng Java thường đặt JAR và thư mục class trên classpath. Classpath không có mô tả dependency chính thức giữa các thư viện. JVM tìm class theo các vị trí trên classpath và classloader; package có thể bị trùng giữa nhiều JAR, còn việc thư viện nào được dùng thường phải suy ra từ build script hoặc cấu hình runtime.

JPMS đưa vào mô hình module với ba khả năng chính:

1. **Dependency tường minh**: module khai báo module khác mà nó cần đọc bằng `requires`.
2. **Encapsulation**: module chỉ công khai những package được khai báo bằng `exports`; package khác được giữ nội bộ.
3. **Service binding**: module khai báo service cần dùng và provider cung cấp thông qua `uses` và `provides`.

Một module có tên và descriptor. JVM dùng descriptor cùng module path để giải quyết module graph trước khi chạy ứng dụng.

~~~text
Module path
    |
    v
Module finder
Tìm module và đọc descriptor
    |
    v
Module resolution
Chọn root modules và dependency closure
    |
    v
Module graph
requires / readability
    |
    v
Access checks
exports / opens
    |
    v
Application execution
~~~

JPMS không thay thế hoàn toàn dependency manager như Gradle. Gradle vẫn có nhiệm vụ tải dependency, chọn version, xây dựng classpath/module path cho task và đóng gói artifact. JPMS bổ sung mô hình module ở cấp Java platform.

## 2. Module path là gì?

**Module path** là đường tìm kiếm mà Java compiler và JVM sử dụng để tìm các module. Module path có thể chứa:

- Modular JAR có `module-info.class`.
- Exploded module: thư mục chứa nội dung một module và descriptor ở gốc.
- Automatic module: JAR không có descriptor tường minh nhưng được đặt trên module path và được Java xem như module tự động.
- Các vị trí module khác được hỗ trợ bởi module finder của môi trường Java.

Khi biên dịch, module path thường được truyền qua tùy chọn `--module-path` hoặc viết ngắn là `-p`. Khi chạy ứng dụng, JVM cũng nhận module path để tìm các module cần thiết.

Ví dụ:

~~~shell
javac --module-path mods -d out ...
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Trong ví dụ này, `mods` là vị trí chứa module dependency. Cờ `-m` yêu cầu chạy module `com.example.app` và main class `com.example.app.Main`.

### Module path không phải một thư mục đặc biệt bắt buộc

Tên `mods` chỉ là ví dụ. Module path là một hoặc nhiều path entry do người chạy cung cấp. Có thể đặt module JAR ở thư mục `lib`, `modules`, `build/modules` hoặc một vị trí khác.

Trên Windows, dấu phân cách giữa nhiều path entry thường là dấu chấm phẩy (`;`); trên Linux/macOS thường là dấu hai chấm (`:`). Nên để công cụ build hoặc script tạo path phù hợp với hệ điều hành.

Module path có thể chứa nhiều module. Khi cần chạy một module, Java tìm module có tên tương ứng, đọc descriptor và tiếp tục tìm các module mà descriptor yêu cầu.

### Module path và nơi lưu JAR không phải cùng một khái niệm

Một JAR có thể nằm trong Gradle dependency cache, thư mục `libs/` của repository hoặc một thư mục triển khai. Nó chỉ tham gia module path khi task/lệnh Java đưa file đó vào module path và Java nhận diện được nó như một module.

Tương tự, file JAR nằm trong module path không có nghĩa tất cả class trong JAR được nạp ngay khi ứng dụng bắt đầu. Module resolution xác định các module cần thiết; classloader nạp class theo nhu cầu thực thi.

## 3. Classpath và module path khác nhau như thế nào?

Hai cơ chế có thể cùng tồn tại, nhưng có quy tắc khác nhau.

| Khía cạnh | Classpath | Module path |
|---|---|---|
| Đơn vị được tìm | Class, resource và package từ thư mục/JAR | Module có tên hoặc automatic module |
| Mô tả dependency | Không có descriptor JPMS bắt buộc | Module descriptor khai báo `requires` |
| Ranh giới package | Không có ranh giới module tường minh | Package thuộc một module |
| Công khai package | Theo cơ chế class access truyền thống | Module cần `exports` package cho consumer |
| Reflection | Không có ranh giới module tương ứng | `opens` điều khiển deep reflection |
| Dependency graph | Thường do build tool và runtime classpath quyết định | JVM giải quyết module graph từ descriptor và root modules |
| Tính đóng gói | Package nội bộ không được JPMS bảo vệ | Package không export được giữ kín với module khác |

### Classpath tạo unnamed module

Các class trên classpath được xem là thuộc về **unnamed module** của classloader tương ứng. Unnamed module không có `module-info.java` và không khai báo dependency theo JPMS.

Mô hình này giúp ứng dụng và thư viện cũ tiếp tục chạy trong Java hiện đại. Tuy nhiên, unnamed module không có khả năng encapsulation package như named module.

Một ứng dụng truyền thống có thể chạy như sau:

~~~shell
java -cp "lib/*;app-classes" com.example.app.Main
~~~

Đây là ví dụ cho Windows; trên Linux/macOS, dấu phân cách classpath thường là `:`. Các class được tìm qua classpath và thuộc unnamed module.

### Named module cần khai báo khả năng đọc

Một named module thường chỉ đọc những module được kết nối vào module graph theo quy tắc JPMS, chẳng hạn thông qua `requires`. Module không tự động đọc mọi module trên module path chỉ vì các JAR nằm cùng thư mục.

Điều này giúp dependency rõ ràng và giới hạn khả năng truy cập. Nó cũng giải thích vì sao một class có thể tồn tại trong một JAR nhưng code của named module vẫn không được phép sử dụng package đó: module có thể chưa đọc module chứa class hoặc package chưa được export.

### Có thể dùng classpath và module path cùng lúc

Trong giai đoạn chuyển đổi, ứng dụng có thể có named module trên module path và thư viện cũ trên classpath. Tuy nhiên, named module không tự động đọc unnamed module. Nếu cần truy cập classpath từ named module, có thể phải dùng tùy chọn như `--add-reads com.example.app=ALL-UNNAMED`, đồng thời cân nhắc việc chuyển thư viện đó sang module phù hợp.

Không nên dùng các tùy chọn mở rộng quyền như giải pháp lâu dài cho mọi dependency. Chúng hữu ích trong quá trình chuyển đổi hoặc tích hợp có chủ đích; về lâu dài, nên xác định rõ module descriptor và module path của ứng dụng.

## 4. module-info.java là gì?

`module-info.java` là file nguồn khai báo module descriptor. File này nằm ở gốc source root của module, bên ngoài các package Java.

Ví dụ cấu trúc:

~~~text
src/
  main/
    java/
      module-info.java
      com/
        example/
          app/
            Main.java
          app/
            api/
              GreetingService.java
~~~

Trong một module source set, `module-info.java` không nằm trong `com/example/...`. Khi biên dịch, Java compiler tạo `module-info.class` ở gốc output của module. Khi đóng gói thành modular JAR, descriptor nằm ở gốc JAR.

Ví dụ nội dung descriptor:

~~~java
module com.example.app {
    requires java.net.http;
    requires com.example.shared;

    exports com.example.app.api;
}
~~~

Đoạn này khai báo:

- Tên module là `com.example.app`.
- Module cần đọc `java.net.http`.
- Module cần đọc `com.example.shared`.
- Package `com.example.app.api` được công khai cho module khác.

Tên module thường dùng dạng phân cấp tương tự tên miền đảo ngược, ví dụ `com.example.orders`. Tên module là định danh JPMS; nó không bắt buộc giống tên project Gradle, Maven artifact ID hoặc tên file JAR.

### module-info.java không chứa mã nghiệp vụ

Module descriptor chỉ mô tả cấu trúc module và quan hệ của nó. Nó không phải nơi viết class Java, thuật toán hay xử lý request.

Mã nghiệp vụ vẫn nằm trong các class/interface thuộc package của module. `module-info.java` khai báo package nào được công khai và module cần những module nào để biên dịch/chạy.

### Một module có một descriptor chính

Một named module có một descriptor được dùng để xác định tên và các directive của module. Trong source project thông thường, file là `module-info.java`. Khi compile, descriptor trở thành `module-info.class`.

JAR không có `module-info.class` vẫn có thể được dùng trên classpath hoặc được xem là automatic module khi đặt trên module path. Việc một thư viện không có descriptor không có nghĩa Java không thể sử dụng nó; cách Java xử lý phụ thuộc vị trí và metadata của JAR.

## 5. Các directive trong module-info.java

Module descriptor hỗ trợ các directive để mô tả dependency, package access và service.

| Directive | Mục đích |
|---|---|
| `requires` | Khai báo module dependency và khả năng đọc module đó |
| `requires transitive` | Cho phép consumer của module hiện tại đọc tiếp dependency này |
| `requires static` | Dependency cần khi compile nhưng có thể không hiện diện ở runtime |
| `exports` | Công khai package cho module khác |
| `exports ... to` | Chỉ công khai package cho một số module được chỉ định |
| `opens` | Cho phép deep reflection vào package |
| `opens ... to` | Chỉ mở package cho một số module |
| `open module` | Mở tất cả package của module cho deep reflection |
| `uses` | Khai báo module sử dụng một service |
| `provides ... with` | Khai báo provider cho một service |

### requires: khai báo module dependency

Ví dụ:

~~~java
module com.example.app {
    requires java.net.http;
    requires com.example.shared;
}
~~~

Module `com.example.app` cần đọc hai module được khai báo. Nếu module cần thiết không thể được tìm thấy hoặc không được giải quyết, compile/run có thể thất bại với lỗi module resolution.

`java.base` được mọi module yêu cầu ngầm định, nên thường không cần viết `requires java.base;`.

`requires` xác định quan hệ giữa các module trong JPMS. Nó không tự tải dependency từ Maven Central hoặc repository khác. Việc tìm và tải artifact vẫn do build tool hoặc cơ chế phân phối đảm nhiệm.

### requires transitive: truyền khả năng đọc cho consumer

Dùng `requires transitive` khi module công khai API phụ thuộc vào kiểu từ module khác và muốn consumer đọc được dependency đó thông qua module hiện tại.

~~~java
module com.example.library {
    requires transitive com.example.publicmodel;
    exports com.example.library.api;
}
~~~

Giả sử public API của `com.example.library` sử dụng kiểu từ `com.example.publicmodel`. Consumer yêu cầu `com.example.library` có thể đọc `com.example.publicmodel` thông qua quan hệ transitive.

Đây là cơ chế readability của JPMS. Nó có vai trò tương tự ý tưởng dependency API được công khai ở build tool, nhưng không nên coi `requires transitive` và Gradle `api` là hai khai báo thay thế nhau. Gradle configuration và JPMS descriptor làm việc ở hai lớp khác nhau; project cần cấu hình phù hợp cho cả dependency resolution lẫn module graph.

### requires static: dependency compile-time tùy chọn ở runtime

`requires static` khai báo dependency cần để biên dịch module nhưng có thể không có trong runtime configuration:

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

Directive này hữu ích cho một số annotation hoặc công cụ chỉ cần trong compile-time. Nếu code runtime thực sự cần class từ module đó, việc vắng mặt ở runtime vẫn có thể gây lỗi khi class được sử dụng.

`requires static` không tự động đưa JAR vào module path; build vẫn phải cung cấp dependency ở compile time và quyết định có đưa nó vào runtime hay không.

## 6. exports: công khai package cho module khác

JPMS áp dụng encapsulation ở cấp package. Một package thuộc named module chỉ có thể được module khác truy cập theo cách thông thường nếu package đó được export.

Ví dụ:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Module công khai package `com.example.catalog.api`. Các class public trong package đó có thể được module đọc module này sử dụng theo quy tắc Java access control.

Các package khác như `com.example.catalog.internal` không tự động được công khai chỉ vì nằm trong cùng JAR.

### exports không tự export subpackage

Nếu khai báo:

~~~java
exports com.example.catalog.api;
~~~

thì chỉ package `com.example.catalog.api` được export. Package `com.example.catalog.api.internal` là package khác và không tự động được export.

Khi thiết kế API, hãy công khai đúng package mà consumer cần. Giữ package implementation/internal ở trạng thái không export giúp giảm phụ thuộc ngoài và cho phép thay đổi nội bộ mà ít ảnh hưởng consumer hơn.

### Qualified exports

Có thể chỉ công khai package cho một số module:

~~~java
module com.example.catalog {
    exports com.example.catalog.spi to com.example.plugin.one, com.example.plugin.two;
}
~~~

Đây là **qualified export**. Chỉ những module được liệt kê mới được truy cập package qua cơ chế export của module descriptor.

Cách này hữu ích khi có API nội bộ dành cho một số module tích hợp. Tuy nhiên, danh sách consumer làm tăng sự ràng buộc giữa các module; chỉ dùng khi có nhu cầu kiến trúc rõ ràng.

## 7. opens: cho phép deep reflection

`exports` và `opens` giải quyết hai nhu cầu khác nhau.

- `exports` cho phép truy cập các public type/member của package theo quy tắc Java.
- `opens` cho phép framework hoặc code khác dùng reflection sâu hơn, kể cả truy cập member không public theo quyền được JPMS cấp.

Một số framework serialization, dependency injection hoặc ORM cần reflection để đọc/ghi field hoặc gọi constructor không public. Trong named module, package có thể cần được mở cho module framework tương ứng.

Ví dụ:

~~~java
module com.example.orders {
    requires com.fasterxml.jackson.databind;

    exports com.example.orders.api;
    opens com.example.orders.model to com.fasterxml.jackson.databind;
}
~~~

Package API được export để module khác gọi. Package model được mở cho Jackson để framework có thể thực hiện reflection cần thiết.

### Qualified opens

Directive `opens ... to` giới hạn quyền reflection cho một số module cụ thể:

~~~java
opens com.example.orders.model to com.example.orm;
~~~

Điều này thu hẹp phạm vi mở package so với việc mở toàn bộ module.

### open module

Có thể mở toàn bộ package của module cho deep reflection:

~~~java
open module com.example.legacy.integration {
    requires com.example.framework;
}
~~~

Với `open module`, các package được mở cho reflection. Không cần thêm từng directive `opens` bên trong open module; nếu chỉ một số package cần reflection, dùng `opens` riêng sẽ giới hạn quyền tốt hơn.

`open module` không có nghĩa mọi package được export như API công khai. Reflection access và compile-time package visibility là hai khái niệm riêng.

## 8. uses và provides: kết nối ServiceLoader

JPMS hỗ trợ cơ chế service provider để module sử dụng một interface/service mà không phải phụ thuộc trực tiếp vào implementation cụ thể.

Ví dụ, module ứng dụng sử dụng service:

~~~java
module com.example.checkout {
    requires com.example.payment.api;
    uses com.example.payment.api.PaymentProvider;
}
~~~

Module provider triển khai service:

~~~java
module com.example.payment.card {
    requires com.example.payment.api;

    provides com.example.payment.api.PaymentProvider
        with com.example.payment.card.CardPaymentProvider;
}
~~~

Ứng dụng có thể tìm provider qua `ServiceLoader`:

~~~java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.process();
}
~~~

Tên interface, phương thức và class ở đây là ví dụ minh họa. Trong project thực tế, service API và provider implementation cần được đặt ở package/module phù hợp.

Directive `uses` khai báo service mà module cần. Directive `provides` khai báo implementation được cung cấp. Cơ chế này giúp ứng dụng phụ thuộc vào abstraction và cho phép provider được thêm hoặc thay thế qua module path mà không phải sửa code gọi service.

## 9. Module resolution và module graph

Khi khởi chạy một named module, Java cần xác định các module gốc (root modules), sau đó giải quyết các dependency được khai báo qua `requires`.

Ví dụ:

~~~text
Root module: com.example.app
        |
        +--> requires com.example.orders
        |         |
        |         +--> requires com.example.shared
        |
        +--> requires java.net.http
~~~

Module graph có thể gồm:

- Root module được chỉ định để chạy hoặc được thêm bằng tùy chọn module tương ứng.
- Các module cần thiết được kéo vào qua chuỗi `requires`.
- Các module nền tảng của JDK được tìm trong runtime image/module system.
- Module provider cần thiết cho service binding theo cấu hình và cơ chế khởi chạy.

Nếu một module bắt buộc không tìm thấy, module resolution thất bại trước khi ứng dụng chạy bình thường. Nếu hai module có tên trùng hoặc cấu hình có package conflict không hợp lệ, quá trình giải quyết cũng có thể thất bại.

### Module path có thể chứa nhiều module hơn graph được resolve

Một thư mục module path có thể có nhiều JAR hơn số module cuối cùng được đưa vào graph. Java tìm module theo yêu cầu và root modules; sự hiện diện vật lý của một JAR trên module path không đồng nghĩa module đó luôn được resolve hoặc class trong đó được load.

Tương tự, module graph được resolve không đồng nghĩa mọi class của mọi module đều được khởi tạo hoặc thực thi. Resolution và class loading là hai giai đoạn khác nhau.

### Chọn root module

Khi chạy một module chính:

~~~shell
java --module-path mods -m com.example.app/com.example.app.Main
~~~

`com.example.app` là module được yêu cầu chạy. JVM giải quyết các module mà nó cần thông qua descriptor.

Có thể bổ sung module root bằng `--add-modules` khi cần module không được kéo vào qua dependency thông thường, ví dụ một module service provider hoặc module bổ sung được ứng dụng yêu cầu theo cấu hình.

## 10. Modular JAR và automatic module

### Modular JAR

Một modular JAR chứa `module-info.class` ở gốc JAR. Descriptor này xác định tên module và các directive.

Có thể kiểm tra descriptor bằng công cụ `jar`:

~~~shell
jar --describe-module --file build/libs/catalog.jar
~~~

Lệnh này hiển thị mô tả module mà Java đọc từ JAR. Nếu JAR là modular JAR, thông tin descriptor được sử dụng để xác định module name, requires, exports và các directive liên quan.

### Automatic module

Nhiều thư viện cũ chưa có `module-info.class`. Khi đặt một JAR như vậy trên module path, Java có thể coi nó là **automatic module**.

Tên automatic module được xác định ưu tiên từ thuộc tính manifest `Automatic-Module-Name` nếu có; nếu không, Java suy ra tên từ tên file JAR theo quy tắc đặt tên module.

Automatic module giúp thư viện cũ tham gia module path trong giai đoạn chuyển đổi. Tuy nhiên, nó không cung cấp encapsulation rõ như explicit named module:

- Các package của automatic module được export theo cơ chế automatic module.
- Automatic module có khả năng đọc rộng các module khác.
- Tên module suy ra từ tên file có thể không ổn định nếu file bị đổi tên.
- API và dependency chưa được mô tả rõ bằng descriptor do tác giả thư viện cung cấp.

Nếu xây dựng một thư viện mới hoặc có thể kiểm soát việc phát hành thư viện, nên cân nhắc cung cấp module descriptor rõ ràng. Với thư viện bên thứ ba, kiểm tra `Automatic-Module-Name` và thông tin module thực tế trước khi viết `requires`.

### Tên automatic module và tên artifact

Không nên đoán module name từ Maven/Gradle coordinates. Artifact ID, tên file JAR và module name là các định danh khác nhau. Hãy dùng `jar --describe-module` hoặc metadata của thư viện để xác định module name chính xác.

## 11. Ví dụ một ứng dụng gồm hai module

Giả sử ứng dụng có hai module:

- `com.example.shared`: chứa kiểu dữ liệu và API dùng chung.
- `com.example.app`: chứa main class và sử dụng shared.

Cấu trúc source:

~~~text
src/
  com.example.shared/
    module-info.java
    com/example/shared/Message.java
  com.example.app/
    module-info.java
    com/example/app/Main.java
~~~

Module shared:

~~~java
module com.example.shared {
    exports com.example.shared;
}
~~~

Class trong shared:

~~~java
package com.example.shared;

public class Message {
    public String text() {
        return "Hello from a module";
    }
}
~~~

Module app:

~~~java
module com.example.app {
    requires com.example.shared;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.shared.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Message().text());
    }
}
~~~

Ở đây, `com.example.app` khai báo `requires com.example.shared`, còn module shared export package chứa class `Message`. Hai điều kiện này cho phép app đọc module shared và truy cập public class trong package đã export.

Nếu bỏ `requires`, app không có readability edge phù hợp. Nếu bỏ `exports`, module app có thể đọc module shared nhưng không được truy cập package chưa công khai.

## 12. Biên dịch và chạy bằng javac/java

Với cấu trúc multi-module như trên, có thể biên dịch từ thư mục gốc của source:

~~~shell
javac --module-source-path src -d out -m com.example.shared,com.example.app
~~~

Trong đó:

- `--module-source-path src` chỉ ra cây thư mục chứa source của các module.
- `-d out` chỉ định thư mục output.
- `-m` chọn các module cần biên dịch.

Sau khi compile, thư mục output có thể có dạng:

~~~text
out/
  com.example.shared/
    module-info.class
    com/example/shared/Message.class
  com.example.app/
    module-info.class
    com/example/app/Main.class
~~~

Chạy ứng dụng:

~~~shell
java --module-path out -m com.example.app/com.example.app.Main
~~~

JVM tìm module `com.example.app` trong `out`, đọc descriptor, giải quyết `com.example.shared` và chạy main class.

### Khi có dependency module bên ngoài

Giả sử ứng dụng cần một thư viện modular JAR nằm trong `mods`. Có thể compile với module path đó:

~~~shell
javac --module-path mods --module-source-path src -d out -m com.example.app
~~~

Khi chạy, module path cần chứa cả output của module nội bộ và dependency bên ngoài:

~~~shell
java --module-path "out;mods" -m com.example.app/com.example.app.Main
~~~

Dòng path dùng dấu `;` minh họa cho Windows. Trên Linux/macOS, các path entry thường được phân tách bằng dấu `:`.

Nếu compile hoặc run không tìm thấy module, kiểm tra tên module thực tế, vị trí JAR, descriptor, module path và các module mà descriptor yêu cầu.

## 13. Tạo và kiểm tra modular JAR

Sau khi biên dịch, có thể đóng gói nội dung một module thành JAR. Ví dụ, nếu output của module là `out/com.example.shared`:

~~~shell
jar --create --file mods/com.example.shared.jar -C out/com.example.shared .
~~~

Lệnh này đóng gói nội dung module output. Vì `module-info.class` nằm ở gốc thư mục output, nó sẽ nằm ở gốc JAR.

Kiểm tra:

~~~shell
jar --describe-module --file mods/com.example.shared.jar
jar --list --file mods/com.example.shared.jar
~~~

Lệnh đầu hiển thị module descriptor; lệnh sau liệt kê nội dung archive.

Một JAR chỉ trở thành modular JAR tường minh khi có descriptor hợp lệ. Chỉ đặt tên file theo module hoặc tạo thư mục tên module không thay thế được `module-info.class`.

## 14. Tích hợp module path với Gradle

Gradle quản lý dependency và cấu hình task. Khi dùng Java plugin với source code có `module-info.java`, Gradle có thể suy luận module path cho các task Java phù hợp dựa trên cấu trúc project và dependency.

Ví dụ cấu hình:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

`modularity.inferModulePath` điều khiển việc Gradle suy luận module path cho các task Java. Khi bật, Gradle có thể phân loại dependency phù hợp để đưa vào module path thay vì chỉ tạo một classpath truyền thống.

### Những gì Gradle và JPMS chịu trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| Gradle dependency configuration | Khai báo dependency, version và phạm vi compile/runtime/test |
| Gradle dependency resolution | Chọn component, version và variant; tải artifact |
| Gradle Java task | Thiết lập compiler/runtime arguments và classpath/module path |
| `module-info.java` | Khai báo module name, requires, exports, opens và service directives |
| Java module resolution | Tìm module, giải quyết `requires` và xây dựng module graph |
| JVM classloader | Nạp class/resource khi code hoặc framework cần |

Gradle có thể tải một JAR thành công nhưng JPMS vẫn báo lỗi nếu module name không đúng, module descriptor thiếu `requires`, package chưa export hoặc module path không được thiết lập phù hợp.

Ngược lại, descriptor có thể viết đúng nhưng Gradle chưa resolve được dependency vì repository, version hoặc configuration sai. Khi debug, cần xác định lỗi thuộc lớp dependency resolution của Gradle hay module resolution của Java.

### Kiểm tra module name của dependency

Với JAR có sẵn:

~~~shell
jar --describe-module --file path/to/library.jar
~~~

Dùng kết quả để xác định module name chính xác trong `requires`. Không dùng tọa độ dependency hoặc tên file làm module name nếu chưa kiểm tra.

### Gradle project nhiều module

Một build Gradle nhiều project không tự động là một ứng dụng JPMS nhiều module. Hai khái niệm này khác nhau:

- Gradle project/subproject là đơn vị cấu hình/build.
- JPMS module là đơn vị module Java được mô tả bằng module descriptor.

Một Gradle subproject có thể tạo modular JAR, nhưng cũng có thể chỉ tạo JAR truyền thống. Một Gradle project cũng có thể chứa nhiều source set hoặc artifact tùy cấu hình. Muốn dùng JPMS, cần cấu hình Java source/module descriptor và task phù hợp; chỉ dùng `include 'app', 'shared'` trong settings không tự tạo quan hệ `requires`.

## 15. Các lỗi JPMS thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `module not found` | Module không có trên module path hoặc tên module sai | Kiểm tra path, JAR và `jar --describe-module` |
| `module does not read` / package không visible | Thiếu `requires` hoặc readability edge | Kiểm tra descriptor và module graph |
| Package không được export | Module đích không export package cần truy cập | Thêm `exports` phù hợp nếu đó là API |
| Reflection bị từ chối | Package chưa được mở cho framework | Dùng `opens` có phạm vi phù hợp |
| `FindException` hoặc module resolution failure | Module trùng tên, dependency thiếu hoặc cấu hình module path không hợp lệ | Kiểm tra module path và descriptor |
| Split package | Nhiều named module chứa cùng package trong cùng module configuration | Tách package hoặc tổ chức lại module |
| Automatic module name không tìm thấy | Đoán sai tên module từ artifact ID/file name | Kiểm tra descriptor/manifest bằng `jar` |
| Compile được nhưng runtime thiếu module | Compile module path và runtime module path khác nhau | So sánh cấu hình compile/run |
| Test lỗi truy cập reflective | Test framework cần mở package cho reflection | Xem test runtime/module configuration và mở package có giới hạn |

### Split package

Một package không nên bị chia sẻ giữa nhiều named module trong cùng module configuration. Nếu hai modular JAR cùng chứa package `com.example.shared`, module resolution có thể thất bại vì split package.

Classpath truyền thống thường cho phép cùng package xuất hiện ở nhiều JAR, nhưng điều đó có thể tạo vấn đề class shadowing và phụ thuộc thứ tự classpath. Khi chuyển sang JPMS, cần tổ chức package rõ ràng để mỗi package thuộc một module phù hợp.

### Lỗi package chưa export và lỗi reflection là hai việc khác nhau

Nếu code khác module muốn gọi public class trong package, module sở hữu package cần `exports`. Nếu framework cần truy cập private field hoặc constructor bằng deep reflection, package có thể cần `opens`.

Không nên thêm `open module` cho mọi lỗi truy cập. Mở toàn bộ package làm giảm encapsulation. Hãy xác định module framework cần truy cập và chỉ mở package cần thiết.

## 16. Các tùy chọn mở rộng khi chuyển đổi ứng dụng cũ

Java cung cấp một số tùy chọn dòng lệnh để điều chỉnh module graph hoặc quyền truy cập. Chúng có ích trong giai đoạn chuyển đổi và tích hợp.

| Tùy chọn | Tác dụng |
|---|---|
| `--add-modules` | Thêm module vào tập root modules cần resolve |
| `--add-reads` | Bổ sung quan hệ readability |
| `--add-exports` | Export một package cho module được chỉ định |
| `--add-opens` | Mở package cho deep reflection |
| `--patch-module` | Bổ sung/patch nội dung vào một module hiện có |

Ví dụ:

~~~shell
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED ...
~~~

Tùy chọn này mở package `com.example.app.model` của module `com.example.app` cho code thuộc unnamed module để reflection. Nó thường được dùng khi một framework cũ chạy trên classpath cần reflection vào named module.

Các tùy chọn này thay đổi quyền truy cập hoặc module graph lúc chạy. Chúng không thay thế việc khai báo module descriptor đúng và không nên được thêm tràn lan. Khi có thể, hãy sửa module descriptor hoặc cấu hình dependency để mô tả quan hệ cần thiết một cách rõ ràng.

## 17. Thiết kế module-info.java có chủ đích

Một descriptor tốt nên công khai API tối thiểu và khai báo đúng dependency.

Ví dụ:

~~~java
module com.example.orders {
    requires java.net.http;
    requires transitive com.example.money.api;

    exports com.example.orders.api;
    opens com.example.orders.persistence to com.example.orm;

    uses com.example.orders.spi.PaymentProvider;
}
~~~

Có thể đọc descriptor theo từng phần:

- `requires java.net.http`: module dùng API HTTP client của JDK.
- `requires transitive com.example.money.api`: public API của module phụ thuộc kiểu từ money API và muốn consumer đọc được module đó.
- `exports com.example.orders.api`: công khai package API.
- `opens ... to com.example.orm`: cho ORM reflection vào package persistence.
- `uses ...`: module tìm provider cho service PaymentProvider.

Nếu module tự cung cấp provider, thêm directive `provides ... with ...` tương ứng.

### Nguyên tắc tổ chức

- Mỗi module nên có trách nhiệm có thể giải thích rõ.
- Chỉ export package mà consumer thực sự cần.
- Giữ implementation package không export.
- Dùng `requires transitive` khi dependency thực sự là một phần của API compile mà consumer cần đọc.
- Dùng `opens` cho reflection có chủ đích; tránh mở toàn bộ module nếu chỉ một package cần thiết.
- Dùng service abstraction để giảm phụ thuộc trực tiếp vào provider implementation.
- Kiểm tra module name của dependency bên ngoài thay vì đoán.
- Phân biệt Gradle dependency graph với JPMS module graph.

## 18. Quy trình xác định module path và descriptor

Khi một project sử dụng JPMS hoặc đang chuyển từ classpath, có thể lần theo các bước sau:

1. **Xác định module nguồn**: tìm `module-info.java` trong source root và đọc tên module.
2. **Xác định dependency**: liệt kê các directive `requires` và các service directive.
3. **Kiểm tra module name của JAR**: dùng `jar --describe-module` để xác định tên module thực tế.
4. **Xác định module path của compile**: xem compiler/task nhận module path nào và dependency nào được đưa vào đó.
5. **Xác định module path của runtime**: so sánh cấu hình chạy với cấu hình compile; không mặc định chúng giống nhau.
6. **Kiểm tra module graph**: xác định module bắt buộc có được tìm thấy và đọc đúng không.
7. **Kiểm tra exports/opens**: package cần truy cập đã export hoặc mở cho đúng module chưa.
8. **Kiểm tra artifact**: xác nhận modular JAR chứa `module-info.class` ở gốc và descriptor đúng như mong muốn.
9. **Kiểm tra class loading**: nếu module graph hợp lệ nhưng lỗi vẫn xảy ra, xem classloader, classpath/module path và thời điểm nạp class.

Một số lệnh hữu ích:

~~~shell
java --list-modules
jar --describe-module --file path/to/library.jar
javac --module-path mods --module-source-path src -d out -m com.example.app
java --module-path mods -m com.example.app/com.example.app.Main
~~~

`java --list-modules` liệt kê các module có trong runtime image/JDK hiện tại. Nó không liệt kê toàn bộ module của mọi project hoặc mọi JAR nằm trên máy.

## 19. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Module path chỉ là tên khác của classpath | Module path tìm module có descriptor/automatic-module semantics và tham gia module resolution |
| Mọi JAR trên module path đều là explicit named module | JAR không có descriptor có thể được xem là automatic module |
| `module-info.java` là nơi viết code Java | Đây là descriptor khai báo cấu trúc và quyền truy cập của module |
| `requires` tải dependency từ repository | `requires` mô tả module readability; Gradle/repository cung cấp artifact |
| `exports` và `opens` giống nhau | `exports` công khai API; `opens` cấp quyền deep reflection |
| Export một package đồng nghĩa export subpackage | Mỗi package phải được export riêng nếu cần |
| Một Gradle subproject tự động là một JPMS module | Gradle project và JPMS module là hai khái niệm khác nhau |
| JAR nằm trên module path nghĩa mọi class được nạp | Module resolution và class loading là hai giai đoạn khác nhau |
| Tên module luôn bằng artifact ID | Module name được khai báo trong descriptor hoặc suy ra theo quy tắc automatic module |
| `requires transitive` giống hoàn toàn Gradle `api` | Chúng làm việc ở hai lớp khác nhau: JPMS readability và Gradle dependency variant |
| `open module` là cách sửa mọi lỗi reflection | Nên mở đúng package cho đúng module cần reflection |
| Có `module-info.java` là build chắc chắn chạy theo module path | Compiler/runtime task phải được cấu hình và cung cấp module path phù hợp |

## 20. Bảng tra cứu nhanh

| Muốn biết... | Kiểm tra... |
|---|---|
| Module có tên gì? | Dòng `module ...` trong `module-info.java` hoặc `jar --describe-module` |
| Module cần module nào? | Các directive `requires` |
| Consumer có thể gọi package nào? | Các directive `exports` |
| Framework có thể reflection vào package nào? | Các directive `opens` hoặc `open module` |
| Module dùng service nào? | `uses` |
| Module cung cấp service nào? | `provides ... with ...` |
| JAR có phải modular JAR? | Có `module-info.class` ở gốc JAR |
| JAR cũ có tên automatic module nào? | Manifest `Automatic-Module-Name` hoặc `jar --describe-module` |
| Compiler/JVM tìm module ở đâu? | `--module-path` hoặc cấu hình task Gradle |
| Module nào được resolve? | Root module và closure của `requires` |
| Vì sao package không truy cập được? | Readability, `exports`, `opens` và classloader |

Module path cung cấp các module để Java tìm kiếm và giải quyết; `module-info.java` mô tả cách module tham gia hệ thống đó. Khi tách bạch hai phần, ta có thể xác định lỗi nằm ở việc Gradle chưa cung cấp đúng artifact, Java không tìm thấy module, module graph thiếu quan hệ đọc, package chưa được export/open hay runtime classloader không nạp được class.
