# Hướng dẫn chạy với module path

## 1. Mục đích của hướng dẫn

Khi một ứng dụng Java đã sử dụng Java Platform Module System (JPMS), cách chạy chương trình khác với cách quen thuộc chỉ dựa vào classpath. Thay vì đưa mọi JAR vào tham số -cp và cung cấp tên main class, ứng dụng có thể khai báo các module có tên, xác định dependency bằng module-info.java, đưa artifact lên module path và chọn main module khi khởi động JVM.

Hướng dẫn này trình bày một quy trình có thể lặp lại từ source code đến bản phân phối:

1. Xác định tên module và main class.
2. Biên dịch các named module.
3. Chạy trực tiếp từ exploded modules.
4. Đóng gói modular JAR.
5. Chạy từ thư mục phân phối với --module-path và -m.
6. Kiểm tra module graph và xử lý các lỗi thường gặp.
7. Ghi lại câu lệnh chạy cho môi trường development, CI và production.

Mục tiêu là giúp người đọc hiểu chính xác **module path chứa gì, JVM phân giải những module nào và lệnh chạy cần viết ra sao**.

## 2. Điều kiện trước khi chạy

Trước tiên, xác nhận môi trường đáp ứng các yêu cầu:

- Có JDK hoặc runtime Java hỗ trợ JPMS (Java 9 trở lên).
- Biết chính xác phiên bản Java mục tiêu của ứng dụng.
- Có các modular JAR hoặc thư mục chứa exploded modules tương ứng.
- Có tên module chính và main class hợp lệ.
- Có các dependency cần thiết trong module path hoặc trong runtime image.
- Có module-info.class trong explicit named module.
- Biết ứng dụng còn dùng thư viện classpath, plugin, ServiceLoader hay reflection hay không.

Kiểm tra công cụ Java:

~~~bash
java -version
javac -version
~~~

Xem những system module mà runtime hiện có:

~~~bash
java --list-modules
~~~

Nếu dùng custom runtime image từ jlink, hãy chạy lệnh kiểm tra bằng executable java nằm trong image đó, không chỉ bằng JDK cài trên máy phát triển.

## 3. Phân biệt module path và classpath

Classpath truyền thống là tập thư mục hoặc JAR chứa class/resource, thường được chỉ định bằng -cp hoặc --class-path:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Mã trên classpath thuộc unnamed module của class loader liên quan. Chương trình khởi chạy bằng tên main class và không phải khai báo main module.

Module path chứa các artifact mà Java có thể nhận diện là named module:

~~~bash
java --module-path dist/mods \
     --module com.example.app/com.example.app.Main
~~~

Dạng ngắn tương đương:

~~~bash
java -p dist/mods -m com.example.app/com.example.app.Main
~~~

Trong lệnh trên:

- -p hoặc --module-path: đường dẫn để tìm named module.
- -m hoặc --module: chỉ định main module, có thể kèm main class sau dấu /.
- com.example.app: tên module, không nhất thiết trùng tên file JAR.
- com.example.app.Main: tên đầy đủ của main class trong module app.

JVM bắt đầu resolution từ root module rồi phân giải dependency theo requires trong descriptor. Không phải cứ JAR nằm trong thư mục module path là JAR đó chắc chắn được chọn vào runtime module graph.

## 4. Cấu trúc ví dụ với hai module

Ta tạo ứng dụng rất nhỏ gồm:

- com.example.greeting: module thư viện công bố API chào hỏi.
- com.example.app: module chứa main class và đọc module greeting.

Cấu trúc source:

~~~text
demo/
  src/
    com.example.greeting/
      module-info.java
      com/example/greeting/api/Greeter.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  out/
  dist/
~~~

Descriptor thư viện, file src/com.example.greeting/module-info.java:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

API thư viện, file Greeter.java:

~~~java
package com.example.greeting.api;

public final class Greeter {
    private Greeter() {
    }

    public static String sayHello(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Descriptor ứng dụng, file src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Main class, file src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "JPMS";
        System.out.println(Greeter.sayHello(name));
    }
}
~~~

Phần quan trọng là mối quan hệ giữa ba yếu tố:

- App phải có requires com.example.greeting để đọc module thư viện.
- Greeting phải exports com.example.greeting.api để app dùng được kiểu public.
- Main class phải có phương thức public static void main(String[] args) hợp lệ để launcher khởi chạy.

## 5. Biên dịch hai module từ source

Đứng tại thư mục demo, dùng javac:

~~~bash
javac --module-source-path src \
      --module com.example.greeting,com.example.app \
      -d out/mods
~~~

Dạng một dòng, phù hợp để dùng trên PowerShell hoặc Command Prompt:

~~~text
javac --module-source-path src --module com.example.greeting,com.example.app -d out/mods
~~~

Ý nghĩa:

- --module-source-path src cho compiler biết vị trí source nhiều module.
- --module / -m chọn module cần biên dịch.
- -d out/mods ghi kết quả biên dịch thành từng thư mục module riêng.

Sau khi biên dịch thành công:

~~~text
out/
  mods/
    com.example.greeting/
      module-info.class
      com/example/greeting/api/Greeter.class
    com.example.app/
      module-info.class
      com/example/app/Main.class
~~~

Nếu module phụ thuộc một modular JAR đã biên dịch ở bên ngoài cây source, hãy bổ sung --module-path cho javac. Tham số module source path không được dùng để thay thế module path của dependency đã biên dịch.

## 6. Chạy trực tiếp từ exploded modules

Một **exploded module** là thư mục chứa module-info.class cùng các class/resource thuộc module đó, chưa được đóng gói thành JAR.

Với output ở trên, chạy:

~~~bash
java --module-path out/mods \
     -m com.example.app/com.example.app.Main
~~~

Kết quả mong đợi:

~~~text
Xin chào, JPMS!
~~~

Truyền tham số cho main:

~~~bash
java --module-path out/mods \
     -m com.example.app/com.example.app.Main Lan
~~~

Kết quả:

~~~text
Xin chào, Lan!
~~~

Tất cả đối số sau main module/main class trong lệnh này được truyền vào String[] args của main class.

Trong module path, out/mods là thư mục cha chứa **các thư mục module con**. Không cần liệt kê từng file .class hoặc từng package.

Đây là cách thuận tiện khi debug hoặc chạy local mà chưa cần tạo JAR.

## 7. Đóng gói thành modular JAR

Khi phân phối ứng dụng, thông thường nên đóng gói mỗi module thành một modular JAR riêng. Một JAR được coi là explicit named module khi có descriptor module-info.class hợp lệ.

Tạo thư mục đích:

~~~bash
mkdir -p dist/mods
~~~

Lệnh trên dành cho shell POSIX. Trên PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force dist/mods
~~~

Đóng gói module thư viện:

~~~bash
jar --create \
    --file dist/mods/com.example.greeting.jar \
    -C out/mods/com.example.greeting .
~~~

Đóng gói ứng dụng:

~~~bash
jar --create \
    --file dist/mods/com.example.app.jar \
    --main-class com.example.app.Main \
    -C out/mods/com.example.app .
~~~

Tùy chọn --main-class của jar cho phép ghi thông tin main class cho modular JAR nếu công cụ và descriptor hỗ trợ. Tuy nhiên, cách chạy ghi rõ cả main module/main class vẫn rất dễ hiểu và độc lập với việc thông tin main class đã được đóng gói như thế nào.

Kiểm tra descriptor trong artifact cuối cùng:

~~~bash
jar --describe-module --file dist/mods/com.example.app.jar
jar --describe-module --file dist/mods/com.example.greeting.jar
~~~

Khi kiểm tra, bảo đảm JAR chứa đúng module name và directive requires/exports như source. Không suy đoán module name chỉ từ tên file JAR.

## 8. Chạy từ các modular JAR đã phát hành

Cấu trúc phân phối:

~~~text
dist/
  mods/
    com.example.app.jar
    com.example.greeting.jar
~~~

Lệnh chạy chính:

~~~bash
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

Đầu ra:

~~~text
Xin chào, JPMS!
~~~

JVM tìm app và greeting từ cùng module path. App được chọn làm root vì tham số -m; greeting được phân giải nhờ requires trong descriptor của app.

Nếu modular JAR đã ghi main class trong descriptor, có thể dùng dạng ngắn hơn:

~~~bash
java --module-path dist/mods -m com.example.app
~~~

Dạng chỉ tên module sẽ không hoạt động nếu runtime không tìm được thông tin main class hợp lệ trong module. Vì vậy tài liệu triển khai nên dùng dạng module/mainclass khi cần tránh phụ thuộc vào metadata main class.

Nếu JAR của bạn chỉ là executable JAR truyền thống có Main-Class trong manifest, không tự động suy ra rằng cách chạy -m với tên module bất kỳ sẽ hợp lệ. Hãy kiểm tra nó có module-info.class, Automatic-Module-Name hay chỉ có manifest dành cho classpath.

## 9. Đường dẫn module trên Linux, macOS và Windows

Một module path có thể chứa nhiều phần tử: các thư mục chứa modular JAR, các exploded modules hoặc file JAR cụ thể. Khi có nhiều phần tử, ký tự phân cách phụ thuộc hệ điều hành.

| Hệ điều hành | Dấu phân cách path |
|---|---|
| Linux / macOS | Dấu hai chấm : |
| Windows | Dấu chấm phẩy ; |

Ví dụ trên Linux/macOS:

~~~bash
java --module-path "dist/mods:third-party" \
     -m com.example.app/com.example.app.Main
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
java --module-path "dist/mods;third-party" -m com.example.app/com.example.app.Main
~~~

Nếu thư mục chứa dấu cách, luôn quote toàn bộ giá trị path:

~~~bash
java --module-path "/opt/My Application/modules" \
     -m com.example.app/com.example.app.Main
~~~

Trên Windows:

~~~powershell
java --module-path "C:\Program Files\Example\modules" -m com.example.app/com.example.app.Main
~~~

Không dùng dấu : của POSIX làm path separator trên Windows vì nó xuất hiện trong ký hiệu ổ đĩa, chẳng hạn C:.

Đường dẫn tương đối được tính từ **thư mục làm việc hiện tại**, không tự động tính từ vị trí JAR hoặc executable java. Đây là nguyên nhân thường gặp khi chạy được trong IDE nhưng lỗi trên CI hoặc production.

## 10. Main module, main class và root modules

Với:

~~~bash
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

com.example.app là **main module**, còn com.example.app.Main là **main class**. Tên module có thể dùng dấu chấm nhưng không nhất thiết trùng package chứa main class.

Main module được đưa vào tập root modules. Từ đó module resolution sẽ theo các dependency requires.

Ví dụ:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.logging;
}
~~~

Khi chạy app, các module cần thiết như greeting và java.logging được phân giải nếu có thể tìm thấy.

Nếu một provider hoặc module bổ sung không được kéo vào graph qua requires hoặc cơ chế service binding tương ứng, có thể cần thêm root khi chạy:

~~~bash
java --module-path dist/mods \
     --add-modules com.example.plugin \
     -m com.example.app/com.example.app.Main
~~~

--add-modules chỉ định thêm những module làm root. Nó không sửa module-info.class và không tự cấp quyền truy cập package nội bộ của module mới cho mọi consumer.

Có thể truyền nhiều tên module cho --add-modules, phân cách bằng dấu phẩy. Chỉ thêm những module thực sự cần thiết để ứng dụng hoạt động, không mặc định thêm toàn bộ module path cho mọi ứng dụng.

## 11. Khi module path chứa thư viện bên thứ ba

Một ứng dụng thực tế thường phụ thuộc vào các thư viện ngoài, ví dụ HTTP client, JSON, logging hoặc database driver.

Trước khi thêm chúng lên module path, kiểm tra JAR thực tế:

~~~bash
jar --describe-module --file lib/library.jar
~~~

Có ba tình huống thường gặp:

1. **Explicit named module:** JAR chứa module-info.class. Đây là trường hợp rõ ràng nhất; descriptor quy định requires/exports/opens/uses/provides.
2. **Automatic module:** JAR không có module-info.class nhưng được JVM coi là automatic module khi đặt trên module path. Tên có thể lấy từ Automatic-Module-Name hoặc được suy ra từ tên artifact.
3. **Classpath library:** JAR vẫn nằm trên classpath, thuộc unnamed module; named module không thể viết requires tới unnamed module như một named dependency thông thường.

Một automatic module hữu ích như cầu nối migration nhưng có thể có module name không ổn định nếu suy ra từ tên file. Hãy ưu tiên artifact có module name ổn định và kiểm tra split packages.

Nếu module-info.java của app viết:

~~~java
module com.example.app {
    requires com.example.json;
}
~~~

thì trên module path phải có module được nhận diện bằng **đúng tên com.example.json**. Đưa file json-lib.jar lên classpath chưa đủ để javac hoặc JVM phân giải requires đó.

## 12. Khác biệt giữa -jar, -cp và -m

Ba cách chạy Java phục vụ những mục đích khác nhau:

~~~bash
# Chạy main class trên classpath.
java -cp "app.jar:lib/*" com.example.app.Main
~~~

~~~bash
# Chạy executable JAR theo metadata trong manifest.
java -jar app.jar
~~~

~~~bash
# Chạy một named module từ module path.
java --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

Điểm quan trọng:

- -jar chọn JAR executable và dùng cơ chế launch theo manifest; không đồng nghĩa tự khởi chạy một named module từ module path.
- -cp chọn classpath truyền thống và yêu cầu main class.
- -m chọn main module và main class theo JPMS.
- Khi chạy -jar, đừng giả định mọi -cp truyền kèm sẽ được sử dụng như lệnh classpath thông thường.
- Thay lệnh -jar bằng -m có thể làm thay đổi cách classloader/resource/service được tìm, vì thế phải thử với artifact thực tế.

Một module có thể được đóng gói bằng JAR nhưng điều đó không có nghĩa mọi cách chạy JAR đều tương đương nhau.

## 13. Đọc đúng quan hệ requires và exports

Module path chỉ giúp tìm module. Nó không thay các quy tắc module access.

Thư viện:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

Ứng dụng:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Consumer cần đọc module cung cấp. Nếu class nằm trong package chưa export, consumer không thể import/call nó theo cách thông thường dù class được khai báo public.

Một lỗi compile điển hình:

~~~text
package com.example.greeting.internal is not visible
~~~

Hướng xử lý đúng là xem app có đang phụ thuộc nhầm implementation package không. Nếu bạn sở hữu module thư viện, cân nhắc công bố API ổn định qua exports. Nếu đó là package nội bộ của bên thứ ba, ưu tiên public API thay vì mở rộng quyền truy cập bằng cờ tạm thời.

Không nên áp dụng --add-exports cho mọi package chỉ để làm ứng dụng chạy qua lỗi đầu tiên. Cần xác định rõ ranh giới module và dependency hợp lệ.

## 14. Kiểm tra module graph lúc khởi động

Khi ứng dụng không tìm thấy module hoặc chạy khác mong đợi, dùng:

~~~bash
java --show-module-resolution \
     --module-path dist/mods \
     -m com.example.app/com.example.app.Main
~~~

Option này hiển thị thông tin về module resolution trong lần chạy, giúp xác định:

- Module chính và các module phụ thuộc đã được phân giải.
- Dependency đến module nào khiến root graph mở rộng.
- Module provider hoặc module bổ sung có được đưa vào runtime graph không.
- Có xuất hiện module version hoặc module nguồn khác mong đợi không.

Kiểm tra module descriptor của JAR:

~~~bash
jar --describe-module \
    --file dist/mods/com.example.app.jar
~~~

Kiểm tra các module mà Java runtime có thể quan sát với module path được truyền:

~~~bash
java --module-path dist/mods \
     --list-modules
~~~

Đối với một module cụ thể:

~~~bash
java --module-path dist/mods \
     --describe-module com.example.app
~~~

--list-modules cho thấy các module có thể quan sát theo cấu hình launcher, trong khi --show-module-resolution cho thấy graph được phân giải trong lần chạy cụ thể. Hai thông tin này phục vụ mục đích khác nhau.

## 15. Xác minh tính hợp lệ của module trên module path

Trước khi chạy ứng dụng production, có thể yêu cầu launcher kiểm tra các module:

~~~bash
java --module-path dist/mods \
     --validate-modules
~~~

Lệnh này hữu ích để phát hiện một số vấn đề trong module path như module descriptor hoặc những xung đột module/package có thể được công cụ nhận diện.

Với artifact đã biên dịch, dùng jdeps để xem dependency module:

~~~bash
jdeps --check com.example.app \
      --module-path dist/mods
~~~

Nếu thư viện dùng JDK internal API, có thể thử phân tích:

~~~bash
jdeps --jdk-internals \
      --module-path dist/mods \
      dist/mods/com.example.app.jar
~~~

Cần nhớ jdeps là công cụ phân tích tĩnh. Nó không nhận diện đầy đủ các module nạp bằng reflection, tên class trong cấu hình, plugin runtime hoặc ServiceLoader. Vì vậy vẫn cần test các đường chạy thật.

## 16. ServiceLoader và module provider

Nếu ứng dụng dùng SPI, việc provider JAR nằm trong module path không phải lúc nào cũng đủ để bảo đảm provider được chọn và sử dụng.

Module consumer khai báo uses:

~~~java
module com.example.app {
    requires com.example.greeting;
    uses com.example.greeting.api.GreetingProvider;
}
~~~

Module provider khai báo provides:

~~~java
module com.example.provider {
    requires com.example.greeting;

    provides com.example.greeting.api.GreetingProvider
        with com.example.provider.DefaultGreetingProvider;
}
~~~

Để ServiceLoader tìm được implementation, provider module phải tồn tại trong phạm vi module graph/layer được sử dụng và đăng ký provider hợp lệ.

Khi cần đưa một provider module vào graph rõ ràng để chẩn đoán hoặc cấu hình:

~~~bash
java --module-path dist/mods \
     --add-modules com.example.provider \
     -m com.example.app/com.example.app.Main
~~~

Không cần app import trực tiếp DefaultGreetingProvider. App nên phụ thuộc vào service interface, và provider triển khai service contract.

Nếu dùng custom ModuleLayer, ServiceLoader.load(layer, ServiceType.class) giúp tìm provider theo layer thích hợp. Đừng giả định thread context class loader có thể nhìn thấy mọi plugin nằm trong một layer riêng.

## 17. Reflection và opens khi chạy trên module path

Framework ORM, JSON serialization, dependency injection hoặc test runner có thể cần reflection sâu để gọi constructor không public hoặc truy cập private fields.

JPMS phân biệt:

- exports: cho phép mã khác sử dụng public type/member trong package, với readability phù hợp.
- opens: cho phép deep reflection theo phạm vi được mở.
- --add-exports: bổ sung export tạm thời có đích.
- --add-opens: mở package tạm thời cho reflection sâu.

Ví dụ khi bạn sở hữu module:

~~~java
module com.example.app {
    requires com.example.greeting;
    opens com.example.app.model to com.example.serializer;
}
~~~

Ở đây com.example.serializer phải là tên module thực tế của framework đã được phân giải. Không nên đoán tên module chỉ từ artifact file name.

Trong tình huống migration, một lệnh tạm thời có thể là:

~~~bash
java --module-path dist/mods \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

Lệnh này có ý nghĩa khi caller đang cần deep reflection thuộc unnamed module. ALL-UNNAMED không phù hợp nếu bạn cần giới hạn một named module cụ thể.

Nếu lỗi là InaccessibleObjectException, hãy kiểm tra reflection/opens. Nếu lỗi là package not exported hoặc IllegalAccessError từ regular bytecode access, hãy xem requires/exports. Không dùng một cờ duy nhất để giải quyết mọi lỗi liên quan module.

## 18. Chạy ứng dụng có thư viện legacy trên classpath

Trong giai đoạn migration, có thể có code vẫn phụ thuộc một số thư viện cũ đặt trên classpath. Khi đó câu lệnh có thể kết hợp module path và classpath cho **những thành phần độc lập phù hợp**:

~~~bash
java --module-path dist/mods \
     --class-path "legacy/*" \
     -m com.example.app/com.example.app.Main
~~~

Tuy nhiên, không phải một named module có thể tự động import class từ unnamed module chỉ vì thêm --class-path. Cần xem lại thiết kế dependency của named module, hoặc đưa thư viện thích hợp lên module path với tên module hợp lệ.

Một số trường hợp bridge từ code classpath tới named module có thể cần --add-modules để đưa named module vào graph. Cần xác định chính xác bên gọi và bên cung cấp trước khi chọn option.

Nếu dự án còn nhiều thư viện không thể modular hóa, hãy cân nhắc giữ launcher hoặc phần ứng dụng chính trên classpath trong thời gian chuyển đổi, đồng thời modular hóa thư viện độc lập từng phần thay vì ép toàn hệ thống chuyển ngay sang -m.

## 19. Package split, module name trùng và dependency cycle

Các lỗi cấu trúc có thể xuất hiện khi chuyển từ classpath sang module path:

**Split package:** hai module khác nhau chứa các class cùng một package và tạo xung đột trong graph. Sửa bằng cách gộp artifact thuộc cùng module logic hoặc tổ chức lại package, không phải bằng --add-exports.

**Tên module trùng:** nhiều JAR khác nhau cùng khai báo/suy ra một module name. Tùy module path và cách finder tìm module, một artifact có thể che artifact khác hoặc gây lỗi. Kiểm tra module name của từng JAR và chỉ phân phối một version phù hợp.

**Dependency cycle:** hai explicit modules requires lẫn nhau. JPMS không thiết kế để giải quyết chu trình requires này như một module graph bình thường. Cần phá cycle bằng cách tách API hoặc thay đổi chiều dependency.

**Không tìm thấy module:** tên trong requires hoặc -m không trùng module name thật; thư mục module path không chứa artifact đúng; hoặc JAR bị đóng gói sai.

Khi gặp lỗi, không sửa hàng loạt module descriptor ngay. Hãy xác định tên module, nguồn artifact, package ownership và requires graph trước.

## 20. Runtime image từ jlink là một dạng phân phối khác

Nếu muốn phân phối runtime Java đi kèm ứng dụng thay vì phụ thuộc JDK cài sẵn, có thể dùng jlink để tạo custom runtime image từ các explicit named modules hợp lệ.

Ví dụ trên Linux/macOS với JDK phù hợp:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:dist/mods" \
  --add-modules com.example.app \
  --launcher demo=com.example.app/com.example.app.Main \
  --output dist/runtime
~~~

Khi image được tạo thành công:

~~~bash
dist/runtime/bin/demo
~~~

Nếu ứng dụng dùng service provider, xem xét --bind-services khi tạo image, và kiểm tra provider đã có mặt trong graph/image.

Lưu ý:

- jlink là bước đóng gói runtime, không thay thế javac.
- Automatic module không phải đầu vào explicit-module phù hợp để link trực tiếp.
- Runtime image thường gắn với hệ điều hành/CPU và JDK dùng để tạo image.
- Image đã link không tự chứa mọi plugin hoặc JAR chỉ tải động nếu chúng không được đưa vào thiết kế đóng gói.
- Phải kiểm thử trên chính image production bằng image/bin/java, không chỉ bằng JDK phát triển.

## 21. Ghi lệnh chạy ổn định trong script triển khai

Lệnh chứa đường dẫn tương đối sẽ phụ thuộc thư mục làm việc hiện tại. Nếu người dùng có thể chạy script từ bất kỳ thư mục nào, nên tính path theo vị trí script.

Ví dụ thư mục phân phối:

~~~text
distribution/
  bin/
    run.sh
  mods/
    com.example.app.jar
    com.example.greeting.jar
~~~

Nội dung bin/run.sh trên shell POSIX:

~~~sh
#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_HOME="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

exec java \
  --module-path "$APP_HOME/mods" \
  -m com.example.app/com.example.app.Main "$@"
~~~

Script xác định APP_HOME từ vị trí script, thay vì phụ thuộc vào thư mục mà người dùng đang đứng. Phần "$@" chuyển toàn bộ đối số CLI cho main class.

Trên Windows PowerShell, ý tưởng tương đương:

~~~powershell
$ErrorActionPreference = "Stop"
$AppHome = Split-Path -Parent $PSScriptRoot
$Modules = Join-Path $AppHome "mods"

& java --module-path $Modules -m com.example.app/com.example.app.Main @args
exit $LASTEXITCODE
~~~

Script Windows nên được lưu ở distribution/bin/run.ps1 để $PSScriptRoot trỏ đúng thư mục bin. Nếu Java runtime được đóng gói cùng sản phẩm, thay lời gọi java của hệ thống bằng đường dẫn đến executable java bên trong runtime đó.

Trong CI và production, ghi rõ những biến môi trường có ảnh hưởng đến JVM, chẳng hạn JAVA_HOME, thay vì dựa vào máy đang có JDK bất kỳ trên PATH.

## 22. Những thông tin bắt buộc nên có trong README phát hành

Một hướng dẫn chạy module path dành cho người sử dụng nên mô tả tối thiểu:

1. Phiên bản Java/JDK được hỗ trợ.
2. Cách giải nén hoặc cài đặt artifact.
3. Thư mục chứa modular JAR và cách giữ cấu trúc phân phối.
4. Main module và main class.
5. Lệnh chạy trên Linux/macOS và Windows.
6. Cách truyền tham số ứng dụng.
7. Các biến môi trường, file cấu hình và quyền truy cập filesystem cần thiết.
8. Những module/provider cần được phân phối kèm.
9. Cách bật chẩn đoán module resolution.
10. Lỗi thường gặp cùng hướng xử lý.
11. Cách chạy bằng custom runtime image nếu có.
12. Lệnh test nhanh để xác nhận chương trình hoạt động.

Ví dụ đoạn lệnh ngắn dành cho người dùng:

~~~text
Yêu cầu: Java 17+ và thư mục dist/mods đầy đủ.

Linux/macOS:
  java --module-path dist/mods -m com.example.app/com.example.app.Main

Windows PowerShell:
  java --module-path dist/mods -m com.example.app/com.example.app.Main

Debug:
  java --show-module-resolution --module-path dist/mods -m com.example.app/com.example.app.Main
~~~

Đây là ví dụ cấu trúc tài liệu. Dự án thật cần thay tên module, JDK version, đường dẫn và thông tin cấu hình tương ứng, không sao chép nguyên các tên com.example.* vào sản phẩm thực.

## 23. Bảng lỗi thường gặp khi khởi chạy

| Thông báo/biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Module com.example.app not found | Main module không có trên module path hoặc tên sai | Kiểm tra folder, jar --describe-module, -m |
| Module X not found, required by Y | Dependency trong requires thiếu hoặc được nhận diện tên khác | Bổ sung modular JAR đúng tên/phiên bản |
| Main class not found | Phần sau dấu / sai hoặc class không nằm trong JAR/module | Kiểm tra package/class và nội dung artifact |
| Module ... does not export package | Public type ở package chưa được export cho caller | Kiểm tra API, requires/exports |
| IllegalAccessError | Runtime từ chối tham chiếu bytecode theo quy tắc module/member access | Đối chiếu module graph và descriptor |
| InaccessibleObjectException | Deep reflection vào package chưa opens | Sửa framework/opens có chọn lọc |
| ClassNotFoundException | Class không tồn tại hoặc bị nạp trong loader/path khác | Kiểm tra artifact, plugin, module layer |
| NoClassDefFoundError | Class cần khi chạy không tìm được hoặc khởi tạo phụ thuộc thất bại | Kiểm tra nguyên nhân gốc và runtime dependency |
| ServiceConfigurationError | Provider registration, metadata hoặc khởi tạo service lỗi | Kiểm tra uses/provides và provider module |
| Mã chạy bằng IDE nhưng lỗi qua script | Module path, JDK, cwd hoặc JVM args khác nhau | Ghi lại lệnh thực tế và chuẩn hóa launcher |
| Split package/resolution conflict | Hai module/package không thể cùng tồn tại trong graph | Sửa package ownership hoặc artifact |
| Bản jlink thiếu module | Runtime image không chứa dependency/provider cần thiết | Kiểm tra --add-modules, --bind-services và image |

Khi chẩn đoán, ưu tiên xác định lỗi nằm ở **khám phá module**, **resolution graph**, **quyền truy cập package** hay **nạp class/resource/service**. Những lớp vấn đề này cần những hướng sửa khác nhau.

## 24. Quy trình kiểm tra trước khi phát hành

Một quy trình kiểm tra thực tế:

1. Build từ JDK/toolchain được chỉ định trong tài liệu.
2. Tạo đúng các modular JAR, không dùng nhầm file cũ.
3. Kiểm tra module descriptor bằng jar --describe-module.
4. Xác nhận thư mục module path chứa đúng tất cả artifact cần thiết.
5. Dùng java --module-path ... --validate-modules để kiểm tra cơ bản.
6. Chạy java --show-module-resolution ... -m ... để xác nhận graph.
7. Gọi main class qua đúng lệnh sẽ dùng trong production.
8. Kiểm thử tham số CLI và file cấu hình.
9. Chạy các tính năng sử dụng reflection, ServiceLoader, resource và plugin.
10. Kiểm thử trên Windows/Linux/macOS tương ứng với hệ thống hỗ trợ.
11. Nếu có script, chạy từ một thư mục khác nơi script được đặt để kiểm tra đường dẫn.
12. Nếu có custom runtime image, chạy toàn bộ test bằng executable của image.
13. Ghi lại lệnh startup được phê duyệt và môi trường Java tương ứng.

Không chỉ dựa vào kết quả compile thành công. Một modular JAR có thể biên dịch hợp lệ nhưng lỗi khi khởi động vì dependency runtime, quyền mở package hoặc service provider chưa được bố trí đúng.

## 25. Checklist nhanh cho người vận hành

- [ ] Có Java runtime phiên bản phù hợp.
- [ ] Biết main module và main class chính xác.
- [ ] Module path trỏ đúng thư mục JAR/exploded modules.
- [ ] Các dependency khai báo bằng requires đều có thể được tìm thấy.
- [ ] Không có module name hoặc package xung đột.
- [ ] JAR ứng dụng chứa module-info.class nếu cần explicit module.
- [ ] Đã chọn đúng -m, không nhầm với -jar hoặc -cp.
- [ ] Đường dẫn được quote và dùng đúng path separator của hệ điều hành.
- [ ] Nếu dùng provider, module provider đã được phân giải và đăng ký hợp lệ.
- [ ] Nếu dùng reflection, package cần thiết được opens có chọn lọc.
- [ ] Đã kiểm tra module graph bằng --show-module-resolution.
- [ ] Script production không phụ thuộc bất ngờ vào current working directory.
- [ ] Đã chạy smoke test bằng chính artifact và runtime dùng để phát hành.

## Kết luận

Chạy ứng dụng với module path là cách để JVM nhận diện các named module, bắt đầu từ main module và phân giải dependency theo module-info.java. Câu lệnh cốt lõi là:

~~~bash
java --module-path <thu-muc-modules> \
     -m <ten-module>/<ten-main-class>
~~~

Tài liệu triển khai tốt cần nêu rõ module name, main class, cấu trúc phân phối, phiên bản Java, đường dẫn dành cho từng hệ điều hành và cách kiểm tra module resolution. Khi gặp lỗi, hãy phân biệt thiếu module, sai readability/export, reflection không được mở và dependency tải động. Cách làm này giúp lệnh chạy từ IDE, CI đến production đồng nhất và có thể chẩn đoán.
