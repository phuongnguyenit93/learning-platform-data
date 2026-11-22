# Loại bỏ --add-exports và --add-opens tạm thời khi migration sang JPMS

Trong quá trình chuyển một ứng dụng Java từ classpath truyền thống sang Java Platform Module System (JPMS), nhiều nhóm phát triển tạm thêm các tùy chọn **--add-exports** và **--add-opens**. Những tùy chọn đó giúp mã cũ tiếp tục hoạt động khi một thư viện cần truy cập package nội bộ hoặc framework cần reflection sâu vào các field, constructor và method không public.

Tuy nhiên, khi các ngoại lệ nằm vĩnh viễn trong script chạy, IDE, build tool hay container, quyền truy cập thực tế không còn được mô tả đầy đủ bằng **module-info.java**. Người bảo trì khó biết library nào thực sự cần ngoại lệ, có thể gặp lỗi khi nâng cấp JDK, và đôi khi mở rộng quyền vượt quá nhu cầu.

Mục tiêu của migration là **thay cách truy cập tạm bằng API, module descriptor hoặc phiên bản thư viện phù hợp, sau đó loại bỏ từng cờ đã không còn cần thiết**. Không nên xóa hàng loạt tất cả cờ mà chưa biết nguyên nhân ban đầu và chưa kiểm chứng được các chức năng phụ thuộc.

## 1. Vì sao các cờ tạm xuất hiện?

JPMS áp dụng những ranh giới mà classpath trước đây không kiểm soát ở cấp module:

- Module tiêu thụ phải có quan hệ đọc module cung cấp kiểu dữ liệu, thường thông qua **requires**.
- Package cung cấp API phải được **exports** cho module tiêu thụ.
- Framework cần deep reflection vào một package thường cần package được **opens** cho module framework.

Ví dụ descriptor của domain:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module **com.example.app** không thể tự ý import một class public nằm trong **com.example.domain.internal** chỉ vì domain đã có trên module path. Tương tự, module JSON không mặc nhiên được gọi **setAccessible(true)** trên field private trong package **com.example.domain.model**.

Các ngoại lệ runtime thường có dạng:

~~~bash
--add-exports com.example.domain/com.example.domain.internal=com.example.app
--add-opens com.example.domain/com.example.domain.model=com.example.json
~~~

Cờ thứ nhất bổ sung quyền export package cho module app. Cờ thứ hai bổ sung quyền mở package cho deep reflection từ module json.

Những cờ này không sửa descriptor được đóng gói vào JAR. Khi muốn thiết kế lại ranh giới module cho rõ ràng, cần xác định lý do từng cờ tồn tại rồi thay bằng giải pháp đúng về kiến trúc.

## 2. So sánh các cơ chế truy cập

| Cơ chế | Công dụng | Vấn đề được giải quyết |
| --- | --- | --- |
| requires M | Module hiện tại đọc module M | Dependency giữa các named module |
| exports p | Export package p tới mọi module có quyền đọc | Public API |
| exports p to M | Export package p cho một số module được nêu tên | API nội bộ có giới hạn |
| opens p | Open package p cho deep reflection | Framework reflection rộng |
| opens p to M | Open package p cho module M | Reflection có giới hạn |
| --add-exports S/p=T | Bổ sung quyền export tại compile/runtime theo công cụ tương ứng | Tương thích với consumer chưa được phép |
| --add-opens S/p=T | Bổ sung quyền open tại runtime | Tương thích với framework reflection |
| --add-reads S=T | Bổ sung quan hệ đọc | Tương thích khi thiếu module readability |

Trong cú pháp **S/p=T**, S là module sở hữu package p; T là module nhận quyền. T có thể là tên module hoặc giá trị đặc biệt **ALL-UNNAMED** trong tùy chọn dòng lệnh.

**--add-exports** không biến private member thành public. **--add-opens** không thay thế exports khi source code của module khác cần import API public. **--add-reads** không cấp quyền truy cập vào package chưa được export.

Sự phân biệt này quan trọng khi chọn cách thay cờ: lỗi compile liên quan API public thường không được giải quyết bằng opens, còn lỗi deep reflection không được sửa bằng exports đơn thuần.

## 3. Xác định lỗi thực tế trước khi bỏ cờ

Một số thông báo phổ biến:

**Package is not visible**

~~~text
package com.example.domain.internal is not visible
(package ... is declared in module com.example.domain,
 which does not export it to module com.example.app)
~~~

Điều này thường cho thấy consumer đang import package chưa export. Kiểm tra cả requires và exports. Nếu package là internal, hướng xử lý tốt nhất thường là chuyển sang API public ổn định.

**IllegalAccessError**

~~~text
java.lang.IllegalAccessError:
class ... cannot access class ... in module ...
~~~

Lỗi truy cập có thể chỉ xuất hiện lúc chạy khi bytecode tham chiếu kiểu hoặc member không được phép. Phải xem chính xác hai module liên quan, package và phiên bản bytecode.

**InaccessibleObjectException**

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module com.example.domain does not "opens
com.example.domain.model" to module com.example.json
~~~

Đây là dấu hiệu framework cố truy cập sâu bằng reflection. Cần xác định framework gọi reflection, loại member bị truy cập và khả năng chuyển sang public accessor hoặc khai báo opens có giới hạn.

**ClassNotFoundException** và **NoClassDefFoundError** thường liên quan tới classpath/module path, class loader hay dependency runtime. Không nên mặc định mọi lỗi này đều cần thêm --add-opens hoặc --add-exports.

## 4. Kiểm kê tất cả nguồn JVM và compiler arguments

Trước khi thay đổi, liệt kê từng cờ và nơi nó được truyền. Một ứng dụng có thể có cờ ở:

- Maven Compiler Plugin, Surefire, Failsafe hoặc các plugin khởi chạy.
- Gradle JavaCompile, Test, JavaExec và application distribution.
- Run/Debug Configuration của IDE.
- Script shell, PowerShell, Dockerfile và entrypoint container.
- CI/CD pipeline, Kubernetes manifest, Helm values hoặc deployment script.
- Biến môi trường **JDK_JAVA_OPTIONS**, **JAVA_TOOL_OPTIONS**, tùy chọn của Java agent.
- Test framework, annotation processor, công cụ code generation hoặc công cụ đo coverage.

Mẫu bảng kiểm kê:

| Cờ đang dùng | Môi trường | Consumer | Lý do | Phương án gỡ |
| --- | --- | --- | --- | --- |
| --add-exports ...internal=app | Build, run | com.example.app | Import API nội bộ | Đổi sang public API |
| --add-opens ...model=json | Test, run | com.example.json | Private-field reflection | Qualified opens hoặc serializer mới |
| --add-opens java.base/...=ALL-UNNAMED | Run | Legacy framework | Reflection vào JDK internals | Nâng cấp framework |

Có thể tìm cấu hình trong repository bằng lệnh trên Linux/macOS:

~~~bash
grep -RInE -- '--add-(exports|opens|reads)' \
  pom.xml build.gradle build.gradle.kts scripts .github
~~~

Điều chỉnh các đường dẫn theo repository; không phải dự án nào cũng có tất cả các file này. Trên Windows, có thể dùng tìm kiếm toàn dự án của IDE hoặc PowerShell.

Đừng dừng ở source configuration. Hãy kiểm tra lệnh java thực sự được tạo trong môi trường chạy và các cờ được thêm bởi biến môi trường hoặc launcher để tránh bỏ sót ngoại lệ ẩn.

## 5. Loại bỏ --add-exports bằng cách chuyển sang public API

Giả sử module domain có class nội bộ:

~~~java
package com.example.domain.internal;

public final class InternalCustomer {
    public String displayName() {
        return "Customer A";
    }
}
~~~

Domain chỉ export API:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Nhưng module app import trực tiếp class nội bộ:

~~~java
import com.example.domain.internal.InternalCustomer;
~~~

Nhóm trước đây thêm:

~~~bash
--add-exports com.example.domain/com.example.domain.internal=com.example.app
~~~

Giải pháp dài hạn là thiết kế một kiểu API ổn định thuộc package đã export:

~~~java
// com.example.domain.api.CustomerView
package com.example.domain.api;

public record CustomerView(String displayName) {
}
~~~

Một service công khai trả về kiểu API:

~~~java
// com.example.domain.api.CustomerService
package com.example.domain.api;

public final class CustomerService {
    public CustomerView findCustomer() {
        return new CustomerView("Customer A");
    }
}
~~~

Module app chuyển sang:

~~~java
import com.example.domain.api.CustomerService;
import com.example.domain.api.CustomerView;

CustomerView customer =
    new CustomerService().findCustomer();

System.out.println(customer.displayName());
~~~

Descriptor app chỉ cần đọc domain:

~~~java
module com.example.app {
    requires com.example.domain;
}
~~~

Và domain tiếp tục export package API:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Khi không còn mã nào import package internal, cờ add-exports cho app có thể được loại bỏ. Đây là sửa nguyên nhân gốc: app không phụ thuộc vào chi tiết triển khai của domain nữa.

Nếu library domain là thư viện bên ngoài không thể sửa source, hãy tìm phiên bản có public API phù hợp hoặc dùng API chính thức thay vì thiết lập dependency lâu dài tới package được ghi là internal.

## 6. Qualified exports thay cho quyền cấp bằng launcher

Một số package không phải API công khai cho tất cả consumer, nhưng là SPI hoặc API nội bộ dành cho nhóm module đã được xác định.

Nếu kiểm soát module descriptor, có thể khai báo:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    exports com.example.domain.spi
        to com.example.persistence,
           com.example.reporting;
}
~~~

Lúc này, hai module persistence và reporting có thể truy cập các kiểu public trong package SPI, với điều kiện có quan hệ đọc domain.

So với:

~~~bash
--add-exports com.example.domain/com.example.domain.spi=com.example.persistence
~~~

descriptor thể hiện rõ ý định của chủ sở hữu module. Quyền đó được lưu trong module-info.class và được review cùng source.

Cần cân nhắc giới hạn của phương án này:

- Mỗi consumer mới có thể khiến descriptor cần sửa.
- Qualified exports vẫn export cả package, không thể chỉ export riêng một class.
- Nó không tự tạo quan hệ reads từ consumer tới domain.
- Nếu một SPI trở thành API được dùng rộng rãi, nên xem lại ranh giới package thay vì kéo dài danh sách module đích.

Mục tiêu không phải thay một tập cờ bằng descriptor phức tạp không có nguyên tắc, mà diễn đạt quyền thật sự cần thiết tại nơi sở hữu module.

## 7. Loại bỏ --add-opens khi framework dùng reflection

Giả sử framework JSON cần truy cập field private của model:

~~~java
package com.example.domain.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Framework có thể thử:

~~~java
Field field = Customer.class.getDeclaredField("name");
field.setAccessible(true);
Object value = field.get(customer);
~~~

Nếu model package chưa được open cho framework, deep reflection sẽ bị chặn. Nhóm đã thêm tạm:

~~~bash
--add-opens com.example.domain/com.example.domain.model=com.example.json
~~~

Có hai hướng thay thế.

**Hướng A — bỏ nhu cầu truy cập private.** Nếu serializer hỗ trợ public constructor, public accessor, record hoặc adapter riêng, hãy chuyển sang cơ chế đó. Ví dụ tạo DTO công khai:

~~~java
package com.example.domain.api;

public record CustomerDto(String name) {
}
~~~

Module domain tự chuyển model nội bộ sang CustomerDto trước khi trao dữ liệu cho framework. Khi framework chỉ thao tác trên API công khai và không cần deep reflection, có thể giữ model package đóng.

**Hướng B — khai báo qualified opens.** Nếu reflection là một phần hợp lệ của thiết kế và framework là named module:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Quyền reflection giờ được ghi trong module-info.java. Cờ launcher tương ứng có thể được gỡ sau khi đã kiểm tra runtime.

Nếu framework vẫn nằm trên classpath, nó thuộc unnamed module. Không thể viết **opens package to ALL-UNNAMED** trong module-info.java vì ALL-UNNAMED không phải tên module hợp lệ để khai báo trong descriptor. Khi đó có thể cân nhắc chuyển framework thành named module có tên ổn định, thay đổi cách serializer sử dụng model hoặc tạm giữ cờ runtime ở phạm vi tối thiểu.

## 8. Tránh nhầm exports, opens và open module

Một package export không có nghĩa mọi field private được mở cho reflection:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Một package open không có nghĩa mọi class public trong package đó trở thành API có thể import theo cách thông thường từ module khác:

~~~java
module com.example.domain {
    opens com.example.domain.model
        to com.example.json;
}
~~~

Java còn cho phép:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

Open module mở tất cả package cho deep reflection. Nó có phạm vi rộng hơn nhiều so với opens có giới hạn.

Khi migration, nên ưu tiên mở đúng package cho đúng module. Chỉ dùng open module nếu kiến trúc thật sự cần mở toàn bộ module và đã hiểu tác động encapsulation.

Việc một framework không thể chạy vì thiếu quyền không phải lý do đủ để ngay lập tức thêm open module mà không kiểm tra package và caller.

## 9. ALL-UNNAMED không phải một module cụ thể

Hai cấu hình thường gặp là:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
--add-exports com.example.domain/com.example.domain.internal=ALL-UNNAMED
~~~

**ALL-UNNAMED** chỉ mọi unnamed module. Nó được dùng trong launcher/compile options, không phải tên module có thể khai báo bằng requires hay opens ... to trong module-info.java.

Phạm vi ALL-UNNAMED rộng: nhiều thư viện trên classpath có thể nhận quyền truy cập cùng package.

Lộ trình thu hẹp:

1. Xác định class và thư viện thực sự cần quyền.
2. Kiểm tra bản library hiện tại có hỗ trợ Java module system không.
3. Chuyển consumer sang named module có tên ổn định nếu khả thi.
4. Dùng exports ... to hoặc opens ... to khi sở hữu module nguồn.
5. Nếu chưa thể thay, giữ cờ có lý do, người chịu trách nhiệm và điều kiện gỡ bỏ.

Không nên thay ALL-UNNAMED bằng một tên module đoán từ tên file JAR. Đầu tiên phải xác nhận consumer thực sự là named module với tên đó trên module path.

## 10. Cờ mở API nội bộ của JDK

Một số thư viện cũ truy cập class trong package nội bộ của JDK hoặc dùng reflection vào class thuộc java.base. Có thể bắt gặp:

~~~bash
--add-exports java.base/jdk.internal.misc=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Ứng dụng không sở hữu descriptor của java.base. Vì vậy, không thể sửa module-info.java của module nền tảng để tạo giải pháp tùy ý.

Hướng xử lý ưu tiên:

- Nâng cấp framework hoặc library lên phiên bản chính thức hỗ trợ JDK mục tiêu.
- Thay internal API bằng API Java được hỗ trợ.
- Đánh giá API chuẩn cho reflection, method handles, serialization và concurrency nếu phù hợp.
- Gỡ dependency cũ cung cấp các API không còn cần thiết.
- Kiểm thử trên phiên bản JDK được dùng trong production.

Có thể dùng **jdeps** để tìm tham chiếu bytecode tới API nội bộ JDK:

~~~bash
jdeps --jdk-internals path/to/legacy-library.jar
~~~

Kết quả không bao phủ mọi truy cập reflection được xây dựng từ string ở runtime. Kết hợp với integration test, log và stack trace để xác định library thật sự gây lỗi.

Từ JDK 17, cơ chế strong encapsulation được áp dụng nghiêm ngặt hơn đối với nhiều package nội bộ, và **--illegal-access** không còn là giải pháp nới quyền hữu hiệu. Không nên chuyển từ các cờ --add-opens cụ thể sang --illegal-access với kỳ vọng giữ mọi thư viện cũ chạy được.

## 11. Thực hiện migration theo từng giai đoạn

**Giai đoạn 1 — baseline.** Ghi lại JDK version, phiên bản library, lệnh javac/java, test suite và tất cả cờ add-exports/add-opens. Chạy hệ thống hiện tại để có mốc so sánh trước khi thay đổi.

**Giai đoạn 2 — phân loại.** Với mỗi cờ, xác định package nguồn, consumer, loại truy cập (public API hay deep reflection), môi trường cần cờ và stack trace gốc. Những cờ không có bằng chứng sử dụng phải được thử bỏ riêng, không xóa mù.

**Giai đoạn 3 — thay nguyên nhân.** Đổi code sang public API, sửa descriptor, nâng cấp framework hoặc thay serializer/adapter. Không tạo ngoại lệ quyền mới rộng hơn để thay cho ngoại lệ cũ.

**Giai đoạn 4 — bỏ từng cờ.** Sau mỗi thay đổi, biên dịch, chạy unit test, test reflection/service và integration test. Nếu lỗi, ghi rõ bằng chứng rồi sửa nguyên nhân thay vì lập tức khôi phục mọi cờ.

**Giai đoạn 5 — xác minh trên runtime tương đương production.** Dùng cùng JDK, classpath/module path, artifact và JVM args dự kiến khi triển khai. Test xanh trên classpath không chứng minh named-module runtime đã hoạt động.

**Giai đoạn 6 — cập nhật vận hành.** Gỡ cờ khỏi IDE, CI/CD, container, distribution và tài liệu. Đối chiếu command line thực sự được truyền vào JVM.

Migration hoàn tất với một cờ khi không còn code, framework hoặc môi trường được hỗ trợ nào phụ thuộc vào ngoại lệ đó.

## 12. Những nơi cần sửa trong Maven

Compiler có thể được cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-exports</arg>
            <arg>com.example.domain/com.example.domain.internal=com.example.app</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Test fork thường có JVM arguments riêng trong Maven Surefire hoặc Failsafe:

~~~xml
<argLine>
    --add-opens com.example.domain/com.example.domain.model=com.example.json
</argLine>
~~~

Sau khi chuyển sang public API hoặc qualified opens, cần gỡ cờ tương ứng ở cả những nơi không còn nhu cầu.

Lưu ý POM module có thể kế thừa cấu hình từ parent POM hoặc profile CI. Nếu chỉ sửa POM con mà không xem effective configuration, cờ có thể vẫn tiếp tục được truyền.

Cấu hình đóng gói hoặc launcher tạo ra bởi plugin khác cũng phải được cập nhật nếu bản production sử dụng.

## 13. Những nơi cần sửa trong Gradle

Trong Gradle Groovy DSL, có thể tồn tại compiler arguments:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.domain/com.example.domain.internal=com.example.app'
    ]
}
~~~

Cấu hình chạy ứng dụng:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=com.example.json'
    )
}
~~~

Test cũng có thể truyền một bộ arguments khác:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=com.example.json'
    )
}
~~~

Khi dọn cờ, hãy kiểm tra build.gradle, build.gradle.kts, convention plugin, buildSrc và cấu hình dự án cha. Nếu dùng application distribution, kiểm tra cả startup scripts được sinh ra sau build.

Không được kết luận rằng production không còn cờ chỉ vì một JavaExec task local đã được sửa.

## 14. Ví dụ chạy mà không cần ngoại lệ

Giả sử domain đã có API công khai và opens có giới hạn:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Consumer app:

~~~java
module com.example.app {
    requires com.example.domain;
    requires com.example.json;
}
~~~

Biên dịch modular source tree:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.json,com.example.app
~~~

Khởi chạy:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Hai cờ tạm của ví dụ ban đầu đã biến mất vì quyền API và reflection được mô tả đúng trong source descriptor.

Nếu framework nằm trong một JAR bên ngoài, bản JAR đó phải được đặt ở vị trí phù hợp và nhận diện đúng module name. Không suy ra module name từ tên file nếu đó là explicit module; hãy dùng **jar --describe-module**.

## 15. Xác minh quyền thực tế bằng Module API

Có thể kiểm tra export của module domain tới consumer:

~~~java
Module domain = CustomerService.class.getModule();
Module app = Main.class.getModule();

boolean exported =
    domain.isExported("com.example.domain.api", app);

System.out.println("API exported to app: " + exported);
~~~

Kiểm tra quyền open:

~~~java
Module json = ModuleLayer.boot()
    .findModule("com.example.json")
    .orElseThrow();

boolean opened =
    domain.isOpen("com.example.domain.model", json);

System.out.println("Model open to JSON: " + opened);
~~~

Nếu kết quả true nhưng launcher vẫn đang truyền --add-opens hoặc --add-exports, bạn mới xác nhận quyền runtime **đang tồn tại**, chưa chứng minh descriptor đã thay thế được cờ tạm.

Phải đối chiếu module-info.java, descriptor trong artifact và launcher đã loại cờ. Có thể xem modular JAR:

~~~bash
jar --describe-module --file mods/com.example.domain.jar
~~~

Khi test đúng cấu hình không còn ngoại lệ, kết quả Module API giúp xác nhận ranh giới runtime theo module graph mới.

## 16. Test hồi quy khi bỏ cờ

| Nhóm kiểm tra | Mục tiêu |
| --- | --- |
| Compile-time | Consumer chỉ import package API được export |
| Unit test domain | Logic không đổi sau khi tách API |
| Reflection test | Framework thực sự đọc/ghi model ở nơi cần opens |
| Serialization test | Serialize và deserialize private state qua cơ chế được hỗ trợ |
| ServiceLoader test | Provider vẫn được phát hiện ở đúng module/layer |
| Integration test | Các luồng nghiệp vụ chính chạy bằng module path |
| Packaging test | JAR cuối chứa module-info.class và resource cần thiết |
| Negative test | Module không được cấp quyền vẫn bị chặn khỏi package nội bộ |
| Production-like smoke test | JDK và JVM args thật không cần cờ đã loại bỏ |

Test reflection phải kích hoạt đường deep reflection thật, chẳng hạn deserialize object có field private. Nếu chỉ kiểm tra public getter, test có thể xanh dù thao tác private-field reflection vẫn bị lỗi.

Một test module path nên chạy bằng launcher có module chính:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Khi phải hỗ trợ nhiều JDK version, cần kiểm thử các phiên bản đó vì dependency tới internal API thường nhạy cảm với nâng cấp runtime.

## 17. Khi chưa thể loại bỏ ngay

Có trường hợp cần giữ ngoại lệ trong một giai đoạn:

- Upstream library chưa có phiên bản hỗ trợ JPMS/JDK hiện tại.
- Module nguồn thuộc sản phẩm bên ngoài, không thể sửa descriptor.
- Framework chưa có cơ chế public accessor hoặc adapter phù hợp.
- Agent/instrumentation đặc thù yêu cầu truy cập không có giải pháp thay thế ngay.
- Chưa có regression test để chứng minh đường thực thi quan trọng.
- Bỏ cờ gây regression thực tế và nguyên nhân chưa được khắc phục.

Trong trường hợp đó, ghi hồ sơ cho từng cờ:

~~~text
Flag: --add-opens java.base/java.lang=ALL-UNNAMED
Owner: Platform team
Consumer: legacy framework
Reason: runtime deep reflection
Replacement: upgrade to supported framework version
Validation: integration + production-like smoke test
Removal condition: tests pass without the flag
~~~

Giữ phạm vi hẹp nhất có thể; không tự động thay nhiều cờ cụ thể bằng một cấu hình open rộng hơn.

Đây là trạng thái migration còn việc phải xử lý, không phải bằng chứng rằng có thể bỏ qua JPMS encapsulation vĩnh viễn.

## 18. Lỗi thường gặp khi dọn cờ

**Xóa khỏi IDE nhưng quên CI:** cấu hình chạy có thể khác nhau. Kiểm tra tất cả nơi cung cấp JVM arguments.

**Sửa descriptor nhưng dùng JAR cũ:** source đã đúng nhưng runtime vẫn dùng artifact cũ; xem module-info.class trong JAR đang triển khai.

**Dùng exports thay cho opens:** code compile được nhưng framework vẫn báo InaccessibleObjectException khi truy cập member private.

**Dùng opens thay cho exports:** deep reflection có quyền nhưng mã nguồn consumer vẫn không thể import package chưa được export.

**Bỏ cờ runtime mà quên compile-time:** compiler vẫn có thể cần truy cập package; tốt nhất sửa API/descriptor thay vì giữ compiler workaround.

**Chỉ chạy test trên classpath:** các class thuộc unnamed module không phản ánh đầy đủ quy tắc truy cập của named module.

**Thay nhiều cờ bằng open module:** có thể xóa lỗi nhưng làm ranh giới reflection quá rộng.

**Không nhận diện JDK internals:** một library khác vẫn dùng API nội bộ dù source ứng dụng đã được sửa; kiểm tra artifact và dependency tree.

**Thử một lúc quá nhiều thay đổi:** khi lỗi phát sinh không biết do cờ, dependency hay module path; chia thay đổi theo từng nguyên nhân.

## 19. Checklist kết thúc một đợt migration

1. Đã có danh sách đầy đủ mọi cờ add-exports/add-opens trong build và runtime.
2. Mỗi cờ có package nguồn, module nhận quyền và lý do rõ ràng.
3. Mã nguồn không còn import package nội bộ chỉ vì cờ tạm.
4. API cần chia sẻ đã được export hoặc qualified export đúng phạm vi.
5. Framework cần deep reflection đã có qualified opens hợp lệ, hoặc không cần reflection sâu nữa.
6. Thư viện dùng JDK internal API đã được nâng cấp, thay thế hoặc có kế hoạch xử lý riêng.
7. Compiler, test runner, IDE và production launcher đã bỏ cờ không cần thiết.
8. JAR cuối có descriptor đúng và không phải bản artifact cũ.
9. Unit, reflection, integration và service tests đã chạy trên module path.
10. Các luồng nghiệp vụ quan trọng không còn báo lỗi package visibility, IllegalAccessError hoặc InaccessibleObjectException.
11. Những cờ còn lại có owner, mục tiêu loại bỏ và phạm vi quyền tối thiểu.
12. Kết quả được xác minh trên JDK và môi trường mà hệ thống thực sự hỗ trợ.

**Loại bỏ --add-exports và --add-opens tạm thời không chỉ là xóa hai tham số dòng lệnh.** Đây là quá trình chuyển quyền truy cập từ các ngoại lệ khó theo dõi sang public API, package được export/open có chủ đích và dependency được quản lý rõ ràng. Khi làm theo từng bước và xác minh đúng runtime, ứng dụng modular dễ bảo trì hơn và ít phụ thuộc hơn vào các cơ chế tương thích tạm thời.