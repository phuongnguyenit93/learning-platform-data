# Đánh giá ứng dụng classpath trước khi modular hóa

## 1. Tại sao cần đánh giá trước khi chuyển sang JPMS?

Java Platform Module System (JPMS) bổ sung ranh giới module rõ ràng cho ứng dụng Java: mỗi named module có descriptor, khai báo dependency qua requires, công bố package qua exports và quản lý quyền reflection sâu qua opens. Trong khi đó, một ứng dụng classpath truyền thống thường chỉ cần tập JAR cùng các class được đưa vào đường dẫn nạp lớp.

Chuyển từ classpath sang module path không phải thao tác đổi một tham số JVM. Nhiều điều mà classpath cho phép có thể không hợp lệ trong module graph, ví dụ:

- Các JAR khác nhau cùng chứa class thuộc một package.
- Mã của thư viện A truy cập class public nhưng thuộc package nội bộ của thư viện B.
- Hai thư viện tham chiếu qua lại mà chưa có ranh giới module rõ ràng.
- Framework dùng setAccessible(true) với constructor hoặc field private.
- Provider được tìm từ META-INF/services, cấu hình hoặc class name dạng chuỗi.
- Một số dependency chỉ xuất hiện ở runtime thông qua plugin, reflection hoặc class loader tùy chỉnh.
- Ứng dụng dùng các package nội bộ của JDK đã bị strong encapsulation.
- Build dùng fat JAR làm mất thông tin về từng thư viện và service descriptor.

Vì vậy, mục tiêu của giai đoạn đánh giá là tạo ra **bản đồ dependency và các rủi ro tương thích**, sau đó xác định thứ tự chuyển đổi phù hợp. Chỉ nên viết module-info.java khi đã hiểu ứng dụng đang phụ thuộc vào những thành phần nào và cách chúng được nạp.

## 2. Xác định trạng thái hiện tại của ứng dụng

Trước khi dùng công cụ JPMS, ghi nhận cách hệ thống chạy ở hiện tại:

| Nội dung cần kiểm kê | Ví dụ câu hỏi |
|---|---|
| Phiên bản Java | Build bằng JDK nào, production chạy trên JRE/JDK nào? |
| Artifact chính | Chạy bằng -cp, -jar, executable JAR, WAR hay container? |
| Dependency | Có bao nhiêu JAR trực tiếp, transitively, optional và test-only? |
| Framework | Có Spring, Hibernate, Jackson, CDI, logging hay bytecode agent không? |
| Nạp lớp động | Có Class.forName, ServiceLoader, URLClassLoader hay plugin manager không? |
| Native integration | Có JNI, JNA, native image, native library hoặc agent không? |
| Đóng gói | Dùng Maven Shade, Gradle Shadow, distribution ZIP hay Docker image? |
| Yêu cầu triển khai | Có cần custom runtime image, giảm kích thước hoặc tách plugin layer không? |
| Hợp đồng tương thích | Có API nhị phân, serialization, cấu hình và dữ liệu cũ cần giữ không? |

Đầu ra nên là bảng inventory gồm tên artifact, phiên bản, nguồn, chức năng, tình trạng modular, package quan trọng và người chịu trách nhiệm nâng cấp.

Đừng chỉ kiểm kê dependency khai báo trong pom.xml hoặc build.gradle. Một thư viện có thể được copy thủ công vào thư mục lib, được tải theo tên class từ file cấu hình, hoặc do plugin tự tải ở runtime. Những dependency đó cũng phải xuất hiện trong danh mục.

## 3. Chốt một baseline có thể tái hiện

Trước khi modular hóa, chạy ứng dụng classpath nguyên trạng và ghi lại các bằng chứng:

1. JDK version và vendor.
2. Lệnh build và lệnh chạy thực tế.
3. Danh sách JAR cùng checksum hoặc phiên bản.
4. Test suite và các use case quan trọng.
5. Dữ liệu đầu vào/đầu ra đại diện.
6. Log khởi động, plugin discovery, service discovery và cảnh báo truy cập.
7. Thời gian khởi động, bộ nhớ và throughput ở mức cần theo dõi.

Ví dụ chạy ứng dụng classpath:

~~~bash
java -cp "app.jar:lib/*" com.acme.legacy.Main
~~~

Trên Windows, classpath separator là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;lib/*" com.acme.legacy.Main
~~~

Nếu dùng executable JAR với java -jar, đừng mặc định các tham số classpath bên ngoài có hiệu lực giống khi chạy -cp. Cần xác định manifest Main-Class, Class-Path, cấu trúc fat JAR và launcher thực tế của sản phẩm.

Baseline là thước đo để biết liệu lỗi phát sinh từ thay đổi module hay đã tồn tại trước đó. Không nên vừa nâng Java version, thay framework lớn và modular hóa toàn bộ trong cùng một thay đổi nếu không có đủ kiểm thử để tách nguyên nhân.

## 4. Vẽ sơ đồ dependency tĩnh bằng jdeps

jdeps là công cụ phân tích dependency ở mức class/package/module từ bytecode Java.

Phân tích một JAR:

~~~bash
jdeps --summary app.jar
~~~

Phân tích sâu với các dependency có trong thư mục lib:

~~~bash
jdeps --recursive \
      --class-path "lib/*" \
      app.jar
~~~

Xem dependency chi tiết đến class:

~~~bash
jdeps --verbose:class \
      --class-path "lib/*" \
      app.jar
~~~

Lấy danh sách dependency module được công cụ suy ra:

~~~bash
jdeps --print-module-deps \
      --class-path "lib/*" \
      app.jar
~~~

Trong giai đoạn này, cần chú ý:

- Dependency nào là Java SE/JDK module.
- Dependency nào đến từ thư viện ngoài.
- Package nào được dùng trong public signature.
- Class nào tham chiếu tới implementation type của thư viện khác.
- Dependency nào có vẻ chỉ xuất hiện gián tiếp.

jdeps không tự trở thành nguồn sự thật tuyệt đối: nó phân tích tham chiếu có thể quan sát từ bytecode, nhưng không suy ra đầy đủ tên class tạo từ string, dependency được tải bằng reflection, service file, JNI hoặc runtime plugin. Hãy kết hợp kết quả với inventory và kiểm thử.

## 5. Kiểm tra internal JDK API trước khi di chuyển

Một trong những rào cản khi nâng JDK hoặc dùng named module là dependency tới internal JDK API.

Chạy:

~~~bash
jdeps --jdk-internals --recursive \
      --class-path "lib/*" \
      app.jar
~~~

Nếu công cụ chỉ ra class thuộc sun.*, jdk.internal.* hoặc package implementation không được hỗ trợ, ghi lại call site và module/JAR sở hữu code đó.

Hướng xử lý:

- Ưu tiên public Java API tương ứng.
- Nâng cấp thư viện đã bỏ dependency tới JDK internal API.
- Cô lập phần tích hợp nếu chưa thể thay ngay.
- Chỉ dùng --add-exports hoặc --add-opens có phạm vi nhỏ như bước chuyển tiếp.

Ví dụ thay API Base64 cũ bằng java.util.Base64, thao tác atomic bằng java.util.concurrent.atomic hoặc VarHandle, file/buffer bằng java.nio, và các tác vụ mật mã bằng java.security hoặc javax.crypto.

Không phải mọi API nội bộ đều có thay thế một-một. Khi đổi từ internal API sang public API, cần đối chiếu cả hiệu năng, memory ordering, resource lifetime và hành vi tương thích, không chỉ sửa tên class cho biên dịch được.

## 6. Phân loại từng JAR theo khả năng modular hóa

Mỗi dependency nên được gắn một trong các trạng thái sau:

**Explicit named module:** JAR có module-info.class với descriptor rõ ràng. Module name, requires, exports, opens, uses và provides được khai báo trong descriptor.

**Automatic module:** JAR không có explicit descriptor nhưng được đặt trên module path và được Java nhận diện là automatic module. Tên module có thể lấy từ Automatic-Module-Name trong manifest hoặc được suy ra từ tên JAR. Automatic module export các package của nó và có quy tắc readability mang tính chuyển tiếp rộng hơn explicit module.

**Classpath library / unnamed module:** JAR vẫn được dùng trên classpath. Những class trên classpath thuộc unnamed module của class loader tương ứng, không thể được tham chiếu bằng một tên module trong requires.

Kiểm tra artifact:

~~~bash
jar --describe-module --file lib/example.jar
~~~

Nếu JAR không chứa descriptor, lệnh có thể cho biết tên automatic module được suy ra. Một JAR có Automatic-Module-Name chưa phải explicit module: manifest entry cung cấp tên module ổn định khi dùng trên module path, nhưng không thay thế module-info.class.

Khi chuyển đổi, đừng giả định mọi thư viện có thể đặt trên module path mà không thay đổi. Đặc biệt lưu ý split packages, default package, dependency chưa tương thích và mã dựa trên classpath discovery.

## 7. Kiểm tra tính ổn định của module name

Automatic module có thể có tên được suy ra từ tên file JAR. Ví dụ tên artifact thay đổi theo version hoặc quy tắc chuẩn hóa có thể dẫn đến tên module khác mong đợi.

Với thư viện chưa explicit modular nhưng cần dùng trong module path, ưu tiên version có Automatic-Module-Name cố định và được nhà cung cấp duy trì.

Một named module consumer cần requires với tên module chính xác:

~~~java
module com.acme.app {
    requires com.acme.reporting;
}
~~~

Nếu artifact thư viện thực tế được nhận diện là tên khác, resolution sẽ thất bại.

Đối với dependency bên ngoài, tránh cam kết module descriptor vào source trước khi xác nhận module name ổn định ở phiên bản dự kiến phát hành.

Khi có thể, nâng cấp lên bản thư viện explicit module do chính maintainers phát hành thay vì tự sửa tên JAR bằng các quy tắc không được kiểm soát.

## 8. Phát hiện split package

Classpath cho phép nhiều JAR chứa các class cùng package. Named module graph thường không cho phép việc một module đọc các package có cùng tên từ nhiều module khác nhau theo cách gây xung đột.

Ví dụ:

~~~text
lib/
  order-api.jar
    com/acme/order/Order.class
  order-impl.jar
    com/acme/order/DefaultOrderService.class
~~~

Hai artifact dùng chung package com.acme.order. Nếu cố chuyển chúng thành hai named module riêng, có thể gặp lỗi split package hoặc module resolution/layer instantiation thất bại.

Hướng xử lý:

1. Xác định tất cả JAR chứa cùng package.
2. Kiểm tra chúng có chủ ý là một thư viện được tách build artifact hay không.
3. Nếu thực chất là cùng một module logic, cân nhắc gộp code/artifact thành một named module.
4. Nếu là những thành phần độc lập, đổi cấu trúc package ở một phía và cập nhật import.
5. Với thư viện bên thứ ba, ưu tiên bản mới đã khắc phục vấn đề.
6. Kiểm tra đặc biệt các package sinh ra bởi code generation, annotation processor và shading.

Đừng sửa split package bằng cách thêm --add-exports. Export không thay đổi quyền sở hữu package giữa các module.

## 9. Phát hiện dependency cycle

Một hệ thống classpath có thể tồn tại quan hệ tham chiếu hai chiều:

~~~text
billing -> customer
customer -> billing
~~~

Khi chuyển thành hai explicit named module riêng:

~~~java
module com.acme.billing {
    requires com.acme.customer;
}
~~~

~~~java
module com.acme.customer {
    requires com.acme.billing;
}
~~~

chu trình requires không tạo được một cấu hình module hợp lệ.

Hãy phân tích cycle ở cấp package/class trước khi chọn module boundary. Một số cách phá cycle:

- Tách interface hoặc kiểu dữ liệu chung thành module API nhỏ.
- Đảo hướng dependency qua interface và dependency injection.
- Dùng event, callback hoặc service contract để tránh import implementation hai chiều.
- Gộp hai nhóm class thành một module nếu chúng thực sự có vòng đời và khả năng phát hành giống nhau.

Không nên tạo module theo mỗi JAR hiện tại một cách máy móc. Ranh giới module nên phản ánh dependency direction và hợp đồng API có chủ đích.

## 10. Đánh giá public API và package visibility

Trên classpath, code có thể import một public class từ bất kỳ package nào nếu class đó có thể tìm thấy và các access modifier cho phép. Với JPMS, named module chỉ công bố package cho consumer nếu có exports phù hợp.

Ví dụ:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Nếu ứng dụng import com.acme.customer.internal.DefaultCustomerRepository thì sau khi modular hóa, việc import có thể bị chặn vì package internal chưa được export.

Trước khi viết descriptor, phân loại package:

- **Public API:** kiểu được consumer khác sử dụng chính thức.
- **SPI:** service type hoặc extension point.
- **Internal implementation:** không dự kiến cho consumer phụ thuộc trực tiếp.
- **Generated/integration package:** cần xem thực tế framework và build.

Đầu ra nên gồm danh sách package được export và danh sách consumer phải sửa để ngừng phụ thuộc implementation detail.

Mỗi module không nhất thiết export tất cả package. Chỉ định exports dựa trên API muốn hỗ trợ lâu dài; qualified export có thể phù hợp nếu package chỉ dành cho một nhóm named module được biết trước.

## 11. Reflection và framework là rủi ro riêng

Framework serializer, ORM, dependency injection hoặc test runner có thể tạo object và đọc field/constructor bằng reflection. JPMS phân biệt:

- exports: cho phép truy cập thông thường tới public types trong package.
- opens: cho phép deep reflection theo phạm vi được khai báo.
- open module: mở các package của module cho deep reflection.
- --add-opens: mở một package ở runtime cho module đích được chỉ định.

Ví dụ model được framework serialization xử lý:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.fasterxml.jackson.databind;
}
~~~

Ví dụ trên chỉ hợp lệ khi tên module thực tế của framework là com.fasterxml.jackson.databind trong cấu hình mà ứng dụng dùng; phải xác nhận module name của JAR.

Các câu hỏi cần kiểm tra:

- Framework có tìm constructor/field private bằng setAccessible không?
- Nó dùng proxy, subclass generation, method handle hoặc bytecode enhancer không?
- Test framework có cần mở package test khi chạy trên module path không?
- Có thư viện tự chọn ClassLoader hoặc context class loader không?
- Có package nào bị mở toàn bộ chỉ vì thiếu một access cụ thể không?

Không chuyển mọi package thành opens hoặc mở toàn module để tránh sửa framework. Hãy nâng cấp framework hỗ trợ JPMS và mở đúng package cho đúng consumer khi cần thiết.

## 12. ServiceLoader và cấu hình provider

Classpath thường đăng ký service provider bằng file:

~~~text
META-INF/services/com.acme.payment.api.PaymentProcessor
~~~

Nội dung chứa tên class provider:

~~~text
com.acme.payment.card.CardPaymentProcessor
~~~

Khi chuyển sang explicit module, provider được đăng ký qua module-info.java:

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

Consumer named module cần uses:

~~~java
module com.acme.checkout {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

Cần kiểm kê mọi META-INF/services, ServiceLoader.load, factory/plugin registry và file cấu hình chọn implementation. Một provider có thể biến mất sau khi modular hóa nếu:

- Không chuyển service registration đúng cách.
- Provider module không nằm trong resolved module graph.
- Consumer thiếu uses.
- Service API được nạp thành những class khác nhau trong các layer/class loader khác nhau.
- Fat JAR hoặc shading đã làm mất/ghi đè service resource.

Đối với plugin dùng custom ModuleLayer, xem xét Configuration.resolveAndBind để đưa provider phù hợp vào graph, và dùng ServiceLoader.load(layer, ServiceType.class) để tìm trong layer thích hợp.

## 13. Resource, manifest và class loader assumptions

Migration không chỉ liên quan đến file .class. Ứng dụng có thể tìm resource bằng:

~~~java
SomeClass.class.getResource("/config/defaults.properties");
~~~

hoặc:

~~~java
Thread.currentThread()
    .getContextClassLoader()
    .getResource("config/defaults.properties");
~~~

Cách tìm resource trong named module phụ thuộc vào module ownership, quy tắc đóng gói resource và một số ràng buộc về encapsulation khi truy cập resource từ bên ngoài module. Đường dẫn hoạt động trên classpath chưa chắc cho kết quả tương tự sau khi chuyển resource vào một named module.

Cần kiểm kê:

- File cấu hình trong JAR và thư mục ngoài.
- Resource path dùng đường dẫn tuyệt đối hay tương đối.
- Cách dùng Class.getResource, ClassLoader.getResource và context class loader.
- Service descriptors trong META-INF/services.
- Manifest Main-Class, Class-Path, Automatic-Module-Name và các mục liên quan.
- Plugin JAR được scan từ filesystem và trình tự discovery.
- Các class/resource được tạo động bởi annotation processing hoặc code generation.

Đặc biệt, không nên dựa trên việc liệt kê mọi JAR từ một class loader của module layer: JPMS có thể dùng nhiều class loader và cơ chế nạp riêng cho module. Hãy thiết kế resource lookup theo contract của module hoặc framework, rồi kiểm thử trên artifact đóng gói cuối cùng.

## 14. JNI, agent và các tích hợp ngoài JVM

Một dự án classpath có thể có JNI, Java agent, native code, instrumentation hoặc thư viện tạo bytecode runtime. Các thành phần này cần được đánh giá độc lập với dependency Java thuần túy.

Ví dụ:

- Native library được nạp qua System.loadLibrary.
- Agent chạy với -javaagent hoặc dùng Instrumentation.
- Framework tự tạo subclass/proxy hoặc redefine class.
- Tool runtime cần truy cập module/package không được export/open.
- Ứng dụng dùng custom class loader tạo namespace độc lập.

Khi modular hóa, cần xác nhận module của class được instrument, class loader của agent và quyền truy cập package cần thiết. Nếu phải mở quyền tạm thời, ghi rõ --add-opens hoặc --add-exports trong test/runtime configuration và có kế hoạch bỏ khi thư viện đã hỗ trợ API phù hợp.

Không mặc định rằng đổi JVM flag là đủ để xử lý toàn bộ vấn đề JNI. Native dependency còn có yêu cầu về OS, kiến trúc, ABI, loading path và vòng đời tài nguyên.

## 15. Xem lại cấu hình build và test

Maven/Gradle có thể tự phân biệt module path và classpath tùy plugin, version và cấu trúc dự án. Cần kiểm tra lệnh javac/test JVM thực tế, không chỉ đoạn cấu hình source trông có vẻ modular.

Các điểm quan trọng:

- JDK toolchain có phù hợp mục tiêu hay không?
- module-info.java có được compile và đưa vào JAR cuối cùng không?
- Dependency được đặt trên module path hay classpath trong từng phase?
- Test dùng module path, patch-module, opens hay classpath?
- Annotation processor được đặt ở processor path/module path phù hợp không?
- Shaded JAR có phá module-info.class hoặc META-INF/services không?
- Runtime launcher có sử dụng đúng module name/main class không?

Ví dụ cấu trúc đề xuất cho một modular component:

~~~text
customer-api/
  src/main/java/
    module-info.java
    com/acme/customer/api/Customer.java
  src/test/java/
    com/acme/customer/api/CustomerTest.java
~~~

Trước khi áp dụng cấu trúc này cho tất cả project, hãy thử nghiệm trên một module ít dependency để xác nhận build, test, packaging và IDE hoạt động đồng bộ.

## 16. Chiến lược chuyển đổi theo giai đoạn

Không bắt buộc modular hóa toàn bộ ứng dụng trong một lần phát hành. Một lộ trình điển hình:

### Giai đoạn 1: vẫn chạy classpath, loại bỏ rủi ro

- Nâng JDK lên version mục tiêu trong một môi trường kiểm thử.
- Dùng jdeps để tìm dependency và internal JDK API.
- Nâng thư viện đã hỗ trợ JDK mục tiêu.
- Loại hoặc khoanh vùng split package và dependency cycle.
- Giảm reflection sâu không cần thiết.
- Tạo regression tests cho service/resource/class loading.

Chưa cần thay đổi module-info.java của toàn ứng dụng.

### Giai đoạn 2: chuẩn hóa API boundary

- Xác định package API thật sự.
- Tách implementation và API interface nếu cần.
- Loại direct dependency vào internal class của component khác.
- Thống nhất module name ổn định của thư viện.
- Chuyển plugin registry có thể sang SPI công khai.

### Giai đoạn 3: thử một module nhỏ

- Chọn thư viện có dependency ít, không chứa split package.
- Bổ sung module-info.java với requires/exports đúng.
- Build modular JAR và thử từ một consumer đại diện.
- Kiểm tra resource, reflection, service discovery và unit tests.
- Duy trì compatibility cho consumer classpath nếu sản phẩm yêu cầu.

### Giai đoạn 4: mở rộng graph

- Chuyển dần component theo dependency direction.
- Dùng automatic module có kiểm soát làm cầu nối cho thư viện chưa explicit modular.
- Kiểm tra từng tầng dependency, tránh cycle.
- Chuyển ứng dụng chính thành named module khi dependency đã sẵn sàng.

### Giai đoạn 5: xác nhận runtime và đóng gói

- Chạy ứng dụng từ module path.
- Quan sát graph bằng --show-module-resolution.
- Thử đúng sản phẩm đóng gói, Docker/runtime image và plugin.
- Nếu dùng jlink, bảo đảm module được link là explicit module và service provider được đưa vào image theo yêu cầu.
- Xóa các --add-exports/--add-opens chỉ còn dùng để che lỗi chưa xử lý.

Chiến lược này giúp mỗi lần thay đổi có phạm vi nhỏ, dễ rollback và dễ xác định nguyên nhân khi gặp lỗi.

## 17. Automatic module là cầu nối, không phải đích cuối cùng

Khi một thư viện chưa có module-info.class nhưng có thể đặt trên module path, JPMS có thể nhận nó là automatic module.

Điểm thuận lợi:

- Named module khác có thể requires theo automatic module name.
- Thư viện không cần được viết lại ngay.
- Các package của automatic module được export, giảm một số rào cản migration ban đầu.

Tuy nhiên, automatic module chưa có descriptor dependency chính xác, trạng thái export rộng và có thể dựa vào các giả định classpath cũ. Nó còn có giới hạn khi xây dựng runtime image bằng jlink.

Không nên xem automatic module như giải pháp vĩnh viễn nếu ứng dụng có kế hoạch mạnh về encapsulation và custom runtime image. Khi thư viện có explicit module chính thức, hãy thay thế cầu nối bằng artifact được hỗ trợ.

Với ứng dụng chính vẫn nằm trên classpath, có thể chuyển một số thư viện độc lập sang module path trước rồi dùng --add-modules khi cần. Nhưng đừng mặc định mọi thư viện trên module path đều tự trở thành resolved module, cũng đừng vội chuyển ứng dụng chính sang named module khi còn phụ thuộc vào những class chỉ có trong unnamed module.

## 18. Ranh giới giữa named module và unnamed module

Mã trên classpath thuộc unnamed module. Một named module có descriptor không thể viết:

~~~java
module com.acme.app {
    requires unnamed;
}
~~~

Không có module name chuẩn nào đại diện cho toàn bộ classpath để sử dụng trong requires.

Khi chuyển consumer thành named module, cần giải quyết cách nó phụ thuộc các thư viện classpath còn lại. Tùy chiến lược, có thể:

- Đưa thư viện thích hợp lên module path dưới dạng automatic module.
- Nâng thư viện lên bản explicit module.
- Tách các thành phần chưa sẵn sàng sang một launcher/adapter vẫn chạy classpath.
- Thiết kế public SPI hoặc một ranh giới process/service để giảm phụ thuộc trực tiếp.

Các runtime flags như --add-reads có thể hỗ trợ chẩn đoán vài tình huống nhưng không thay thế kiến trúc dependency rõ ràng và không tự biến JAR trên classpath thành named module.

## 19. Dùng thử module path trước khi sửa toàn bộ source

Một cách thực hành là tạo một proof of concept với vài JAR đại diện:

~~~text
prototype/
  app.jar
  lib/
    customer-api.jar
    customer-impl.jar
    logging.jar
~~~

Xác định module name:

~~~bash
jar --describe-module --file lib/customer-api.jar
jar --describe-module --file lib/customer-impl.jar
~~~

Nếu dependency có thể dùng trên module path, kiểm tra graph trong một launcher thử nghiệm:

~~~bash
java --module-path "lib:app.jar" \
     --show-module-resolution \
     --module com.acme.app/com.acme.app.Main
~~~

Lệnh chỉ áp dụng khi com.acme.app thực sự được nhận diện là named hoặc automatic module có main class phù hợp; nếu ứng dụng còn là classpath artifact, hãy giữ cách chạy classpath và thử module hóa các thư viện từng phần trước.

Đối chiếu với baseline classpath: chương trình khởi động, service discovery, reflection, resource loading và các đường plugin quan trọng phải hoạt động.

Nếu lỗi xảy ra ngay ở bước resolution, tập trung vào tên module/dependency/split package. Nếu resolution qua nhưng ứng dụng lỗi khi chạy, kiểm tra quyền truy cập, dynamic class loading và cấu hình framework.

## 20. Tiêu chí sẵn sàng modular hóa

Có thể dùng các tiêu chí sau để quyết định liệu một component đã sẵn sàng được chuyển thành explicit named module hay chưa:

| Tiêu chí | Dấu hiệu đạt |
|---|---|
| Module boundary | Có tên và phạm vi trách nhiệm rõ ràng |
| Dependency direction | Không có cycle khó xử lý; dependency đủ rõ |
| Package ownership | Không còn split package gây xung đột |
| API contract | Có tập package export được xác định rõ |
| Third-party libraries | Module name và khả năng dùng trên module path đã được kiểm chứng |
| Reflection | Opens cần thiết đã được giới hạn và giải thích |
| Service registration | Uses/provides và provider discovery hoạt động |
| Resource/class loader | Đã thử trên cấu trúc modular JAR và launcher thật |
| Build/test | Compiler, test runner, IDE và CI có cùng cấu hình |
| Runtime compatibility | Chạy đúng trên JDK mục tiêu với các use case đại diện |
| Observability | Có log module resolution và cơ chế phân tích lỗi |
| Rollback | Có đường quay lại cấu hình hoạt động nếu migration gặp lỗi |

Không nên cố đạt trạng thái “mọi JAR đều là module” bằng cách đặt tất cả lên module path. Mục tiêu là có module graph được thiết kế và kiểm chứng, không chỉ thay đổi cách tìm JAR.

## 21. Danh sách kiểm tra trước khi bắt đầu

- [ ] Đã khóa phiên bản JDK, ứng dụng và dependency làm baseline.
- [ ] Có inventory cho direct, transitive, optional và runtime-only dependency.
- [ ] Đã chạy jdeps, gồm phân tích JDK internal API.
- [ ] Đã kiểm tra automatic module name và trạng thái descriptor của các JAR.
- [ ] Đã tìm split package và dependency cycle.
- [ ] Đã tách API công khai khỏi implementation package.
- [ ] Đã xác định các điểm reflection sâu, bytecode generation và agent.
- [ ] Đã kiểm kê META-INF/services, ServiceLoader và provider được tải động.
- [ ] Đã rà soát resource, manifest và context class loader.
- [ ] Đã kiểm tra native dependency nếu có.
- [ ] Có integration tests trên JDK mục tiêu và artifact phát hành thật.
- [ ] Có kế hoạch chuyển đổi theo tầng và phương án rollback.
- [ ] Cờ --add-exports/--add-opens được theo dõi như khoản nợ migration, không mặc định là API lâu dài.

## Kết luận

Đánh giá ứng dụng classpath trước khi modular hóa là bước xác định **dependency graph thực tế**, những giả định ngầm của classpath và rủi ro khi JPMS áp dụng readability, exports, opens và module resolution.

Hãy bắt đầu từ baseline có thể tái hiện, dùng jdeps để phân tích bytecode, kiểm kê dependency động, xác định split package/cycle, phân loại automatic và explicit module, rồi thử chuyển một component có ranh giới rõ. Chỉ mở rộng sang ứng dụng chính khi build, runtime, ServiceLoader, reflection và resource loading đã được kiểm chứng.

Một migration thành công không nhất thiết chuyển tất cả code trong một lần. Nó tạo ra module graph có chủ đích, giữ tương thích cần thiết và giảm dần các phụ thuộc nội bộ không được hỗ trợ.
