# Module path trong Gradle Java Plugin

## 1. Gradle và JPMS giải quyết hai lớp dependency khác nhau

Gradle Java Plugin điều phối quá trình biên dịch, kiểm thử và đóng gói các ứng dụng Java. Java Platform Module System (JPMS) lại xác định cách các **named module** đọc nhau, package nào được export, package nào được mở cho reflection và module nào được phân giải khi chương trình chạy.

Vì vậy, trong dự án Gradle có JPMS, tồn tại hai cách mô tả dependency bổ sung cho nhau:

1. **Gradle dependency**: khai báo bằng implementation, api, compileOnly, runtimeOnly hoặc project(...), giúp Gradle lấy artifact và đưa chúng vào đúng configuration.
2. **JPMS dependency**: khai báo trong module-info.java bằng requires, requires transitive, exports, opens, uses và provides, giúp javac/JVM xây dựng module graph và kiểm tra quyền truy cập.

Gradle không tự sinh requires chỉ vì bạn viết implementation. Ngược lại, viết requires trong module-info.java không khiến Gradle tự tải dependency từ Maven repository nếu chưa khai báo dependency cần thiết.

Mục tiêu của bài này là hiểu cách Gradle Java Plugin xác định **module path**, cách tổ chức dự án modular, và cách kiểm tra lỗi phát sinh khi dependency bị đặt nhầm trên classpath.

## 2. Module path khác classpath như thế nào?

Trên classpath truyền thống, compiler và JVM tìm các class từ thư mục hoặc JAR. Mã trên classpath thuộc **unnamed module** của class loader tương ứng, không có module-info.java và không dùng requires để mô tả dependency.

Với module path, compiler và JVM có thể tìm các named module:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Một named module có tên rõ ràng và descriptor mô tả mối quan hệ với các module khác:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Muốn app import kiểu public từ catalog, không chỉ cần đọc catalog qua requires mà catalog còn phải export package chứa kiểu đó.

Trong Gradle, cả classpath và module path đều có thể được tạo từ các dependency configuration. **Điều quyết định là Gradle tổ chức các artifact thành đối số nào của javac hoặc JVM**, chứ không phải việc người phát triển chỉ đặt tên configuration là compileClasspath hay runtimeClasspath.

## 3. Cấu trúc source một named module trong dự án Gradle

Gradle Java Plugin mặc định nhận mã nguồn chính trong src/main/java và mã kiểm thử trong src/test/java. Đối với một named module, đặt module-info.java ở gốc source chính:

~~~text
catalog/
  build.gradle
  src/
    main/
      java/
        module-info.java
        com/acme/catalog/api/Catalog.java
    test/
      java/
        com/acme/catalog/api/CatalogTest.java
~~~

Ví dụ descriptor:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

Và public API:

~~~java
package com.acme.catalog.api;

public final class Catalog {
    private Catalog() {
    }

    public static String title() {
        return "Java Modules";
    }
}
~~~

Một ứng dụng khác muốn dùng Catalog phải đọc com.acme.catalog và phải có quyền truy cập package com.acme.catalog.api. Tên project Gradle, tên file JAR và tên JPMS module có thể khác nhau; **module name là tên khai báo sau từ khóa module** trong module-info.java.

## 4. Bật module-path inference trong Gradle

Gradle hỗ trợ suy luận dependency nào cần nằm trên module path thông qua Java plugin extension:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}
~~~

Trong các phiên bản Gradle hiện đại, chế độ suy luận module path thường đã được bật theo mặc định cho Java Plugin; khai báo tường minh giúp ý định build rõ ràng.

Khi source set chứa module-info.java và bật inference, Gradle có thể cấu hình javac để biên dịch nó như một named module. Với các dependency là JAR, Gradle dựa vào bằng chứng module metadata để lựa chọn module path, đặc biệt:

- JAR có module-info.class: **explicit named module**.
- JAR có Automatic-Module-Name trong MANIFEST.MF: có tên automatic module ổn định và có thể được Gradle nhận diện cho module path.
- JAR không có hai dấu hiệu trên: Gradle có thể giữ nó trên classpath, dù JVM có khả năng suy ra một automatic module name khi JAR được chủ động đặt trên module path.

Sự khác nhau giữa **JVM có thể coi JAR là automatic module** và **Gradle tự quyết định đưa JAR lên module path** là điểm dễ nhầm nhất. Đừng giả định mọi thư viện implementation đều tự động xuất hiện trong module graph.

Nếu ứng dụng gặp module not found, trước hết kiểm tra metadata JAR và cách Gradle phân loại artifact. Không giải quyết bằng việc sao chép JAR ngẫu nhiên vào source folder.

## 5. Ví dụ thực tế: Gradle multi-project với hai JPMS module

Ta tạo một build gồm:

- Project Gradle :catalog, sinh named module com.acme.catalog.
- Project Gradle :app, sinh named module com.acme.app.
- Module app đọc catalog và gọi public API của catalog.

Cấu trúc:

~~~text
demo/
  settings.gradle
  catalog/
    build.gradle
    src/main/java/
      module-info.java
      com/acme/catalog/api/Catalog.java
  app/
    build.gradle
    src/main/java/
      module-info.java
      com/acme/app/Main.java
  gradlew
  gradlew.bat
~~~

Trong settings.gradle:

~~~groovy
rootProject.name = 'jpms-gradle-demo'
include 'catalog', 'app'
~~~

Gradle project path :catalog và :app là định danh trong build. JPMS không bắt buộc dùng đúng hai tên này làm module name.

## 6. Cấu hình module thư viện bằng java-library

File catalog/build.gradle:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}
~~~

Plugin java-library mở rộng Java Plugin và thêm configuration api, dùng khi thư viện có dependency xuất hiện trong public API của chính thư viện.

File catalog/src/main/java/module-info.java:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
~~~

File Catalog.java:

~~~java
package com.acme.catalog.api;

public final class Catalog {
    private Catalog() {
    }

    public static String title() {
        return "Java Modules";
    }
}
~~~

Gradle biên dịch Java source và module descriptor, tạo module-info.class trong output. Khi đóng gói bằng task jar, descriptor sẽ nằm trong modular JAR cùng các class khác.

Module không cần viết requires java.base: mọi named module đều có readability ngầm tới java.base.

## 7. Cấu hình ứng dụng với Application Plugin

File app/build.gradle:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

dependencies {
    implementation project(':catalog')
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

Application Plugin áp dụng Java Plugin và cung cấp task run cùng cấu hình launcher. Khi định nghĩa mainModule và mainClass, Gradle có thông tin để chạy ứng dụng modular theo cách phù hợp.

File app/src/main/java/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

File app/src/main/java/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.catalog.api.Catalog;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Catalog.title());
    }
}
~~~

Đây là điểm cần nhớ:

- implementation project(':catalog') nói với **Gradle** rằng app cần artifact từ project catalog.
- requires com.acme.catalog nói với **JPMS** rằng module app đọc named module catalog.
- exports com.acme.catalog.api cho phép app sử dụng các public types trong package API của catalog.

Thiếu một trong các điều kiện quan trọng này có thể khiến compile thất bại. Các dependency configuration của Gradle không thay thế module descriptor.

## 8. Biên dịch và chạy ứng dụng modular

Trong thư mục demo, chạy:

~~~bash
./gradlew clean :app:compileJava
./gradlew :app:run
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean :app:compileJava
.\gradlew.bat :app:run
~~~

Kết quả ứng dụng mong đợi:

~~~text
Java Modules
~~~

Có thể build toàn bộ:

~~~bash
./gradlew build
~~~

Hoặc đóng gói từng module:

~~~bash
./gradlew :catalog:jar :app:jar
~~~

Output thường gồm:

~~~text
catalog/build/classes/java/main/module-info.class
catalog/build/classes/java/main/com/acme/catalog/api/Catalog.class
catalog/build/libs/...

app/build/classes/java/main/module-info.class
app/build/classes/java/main/com/acme/app/Main.class
app/build/libs/...
~~~

Tên JAR cuối cùng có thể bao gồm project name, version hoặc cấu hình archive. Kiểm tra đúng artifact thực tế; không đoán tên JAR chỉ dựa vào module name.

Application Plugin cũng có thể cung cấp task installDist và distZip để tạo bản phân phối. Hãy chạy và kiểm tra startup script thực tế của bản phân phối vì đây mới là cách chương trình sẽ khởi động bên ngoài Gradle.

## 9. Gradle tự suy luận module path, nhưng không tự sửa descriptor

Suy luận module path giúp Gradle quyết định vị trí dependency khi truyền cho compiler/runtime. Nó không tự động:

- Viết requires vào module-info.java.
- Export package mà bạn chưa khai báo.
- Mở package cho deep reflection.
- Chuyển dependency JAR cũ thành explicit module.
- Đăng ký service provider thay cho uses và provides.
- Giải quyết dependency cycle hoặc split package.
- Biến JAR đang trên classpath thành named module nếu Gradle không nhận diện metadata module.

Nếu app chứa:

~~~java
module com.acme.app {
    requires com.acme.catalog;
}
~~~

nhưng app/build.gradle không khai báo dependency tới catalog, Gradle không nhất thiết đưa catalog vào compile task.

Ngược lại, nếu build.gradle có implementation project(':catalog') nhưng module-info.java thiếu requires com.acme.catalog, compiler vẫn có thể báo module app không đọc module catalog.

**Hãy coi dependency khai báo trong Gradle và dependency khai báo trong JPMS là hai bản đồ phải nhất quán.**

## 10. api, implementation và requires transitive

Trong một module thư viện, cần phân biệt loại dependency theo vai trò API.

Ví dụ module com.acme.reports có public method trả về kiểu thuộc module com.acme.models:

~~~java
package com.acme.reports.api;

import com.acme.models.api.ReportModel;

public interface ReportService {
    ReportModel generate();
}
~~~

Nếu consumer đọc reports và sử dụng ReportModel trong public signature, descriptor có thể dùng:

~~~java
module com.acme.reports {
    requires transitive com.acme.models;
    exports com.acme.reports.api;
}
~~~

Trong build Gradle của reports, dùng java-library:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':models')
}
~~~

Hai khai báo có vai trò liên quan nhưng không trùng nhau:

- api cho Gradle biết dependency là phần bề mặt API của thư viện và phải được công bố cho consumer Gradle.
- requires transitive cho JPMS biết module đọc reports cũng được cấp readability tới models.

Nếu dependency chỉ dùng bên trong implementation, thường chọn implementation trong Gradle và requires thông thường trong module-info.java:

~~~groovy
dependencies {
    implementation project(':internal-helpers')
}
~~~

~~~java
module com.acme.reports {
    requires com.acme.internal.helpers;
    exports com.acme.reports.api;
}
~~~

Không tự động thay mọi implementation thành api hay mọi requires thành requires transitive. Hãy xem kiểu nào thực sự xuất hiện trong hợp đồng public.

## 11. Phân biệt compileClasspath và runtimeClasspath với module path

Gradle có các configuration quen thuộc:

| Configuration | Vai trò thường gặp |
|---|---|
| implementation | Dependency cần biên dịch module và thường có ở runtime |
| api | Dependency được công bố qua API của thư viện khi dùng java-library |
| compileOnly | Chỉ cần khi compile, không tự được mang tới runtime |
| runtimeOnly | Không cần compile trực tiếp, nhưng cần ở runtime |
| testImplementation | Dependency cho test compile/run |
| testRuntimeOnly | Dependency chỉ cần khi chạy test |

Tên compileClasspath hoặc runtimeClasspath trong Gradle vẫn là khái niệm **dependency configuration**. Nó không đồng nghĩa tất cả artifact trong đó sẽ được truyền nguyên vẹn cho cờ --class-path của javac/java.

Khi module-path inference hoạt động, Gradle tách dependency được nhận diện là module khỏi những thư viện vẫn dùng classpath. Vì vậy, lệnh Gradle in ra một compileClasspath chứa cả những dependency mà lúc gọi javac chúng được tổ chức vào module path.

Để xem dependency resolution từ góc nhìn Gradle:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Để tìm lý do chọn phiên bản một dependency cụ thể:

~~~bash
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency some-library
~~~

Các lệnh này giúp tìm artifact và phiên bản. Nhưng để biết compiler đã nhận classpath/module path nào, còn cần quan sát task compile và module metadata.

## 12. Automatic module và thư viện JAR chưa modular hóa

Một JAR chưa có module-info.class vẫn có thể trở thành automatic module nếu được đặt trên module path. JVM có thể suy ra module name từ tên JAR, còn Gradle không nhất thiết chọn đưa nó vào module path nếu JAR không có metadata nhận diện ổn định.

Một số thư viện hỗ trợ manifest entry:

~~~text
Automatic-Module-Name: com.acme.legacy
~~~

Entry này cung cấp một module name ổn định khi JAR dùng trên module path, nhưng **không biến JAR thành explicit module**.

Để kiểm tra metadata artifact:

~~~bash
jar --describe-module --file libs/legacy.jar
~~~

Với thư viện bên ngoài, nên ưu tiên:

1. Bản mới có module-info.class phù hợp.
2. Bản có Automatic-Module-Name ổn định nếu cần giai đoạn chuyển tiếp.
3. Thay thư viện hoặc điều chỉnh kiến trúc nếu nó không thể dùng an toàn trên module path.

Không nên đổi tên JAR ngẫu nhiên chỉ để module name tạm thời khớp requires, vì việc nâng cấp artifact có thể phá cấu hình. Không nên mặc định Gradle sẽ chuyển JAR classpath sang module path chỉ vì bạn thêm requires tên dự đoán vào descriptor.

## 13. Vì sao named module không tự đọc được thư viện trên classpath?

Một vấn đề migration phổ biến:

- app là explicit named module với module-info.java.
- lib-old.jar không có module metadata nên Gradle vẫn đặt nó trên classpath.
- app cố requires một tên module được đoán từ tên lib-old.jar.

Lúc compile, javac có thể báo module not found vì dependency không có trên module path dưới tên đó. Nếu app tham chiếu trực tiếp class thuộc unnamed module, module readability thông thường của JPMS cũng không cho phép named module phụ thuộc vào unnamed module như một named dependency hợp lệ.

Giải pháp không phải thêm đường dẫn classpath vào module-info.java. Có thể:

- Nâng dependency lên bản modular hoặc bản có module metadata ổn định.
- Giữ phần ứng dụng chưa sẵn sàng trên classpath cho tới khi dependency được chuẩn hóa.
- Tách adapter hoặc process boundary để giảm direct dependency.
- Dùng cấu hình module path thủ công có kiểm soát trong một bước migration ngắn hạn, kèm bài test thật.

Việc chuyển thư viện cũ thành automatic module không tự giải quyết mọi vấn đề của nó: split package, reflection, resource và service discovery vẫn phải được kiểm chứng.

## 14. Đánh giá split packages và dependency cycles

Classpath cho phép nhiều JAR cùng sở hữu class trong một package. Với JPMS, khi module graph tạo ra xung đột package giữa các module có quan hệ đọc, compilation hoặc resolution có thể thất bại.

Ví dụ:

~~~text
library-a.jar: com/acme/shared/Alpha.class
library-b.jar: com/acme/shared/Beta.class
~~~

Nếu đây là hai module độc lập nhưng cùng package com.acme.shared, hãy cân nhắc:

- Gộp các class thực sự thuộc một module logic.
- Tách package theo trách nhiệm của từng module.
- Nâng cấp thư viện đã được nhà cung cấp sửa split package.
- Kiểm tra JAR sau shading vì công cụ build có thể vô tình tạo ra split package mới.

Nếu hai module requires nhau theo chu trình, module graph cũng không hợp lệ theo thiết kế JPMS. Cần phá cycle bằng cách tách API interface, đảo hướng dependency hoặc gộp module đúng ranh giới.

Gradle có thể sắp xếp task biên dịch theo project dependency, nhưng **task graph của Gradle không làm một JPMS requires cycle trở nên hợp lệ**.

## 15. Kiểm tra task JavaCompile và compiler arguments

Khi gặp lỗi module not found hoặc package not visible, cần xem cách Gradle gọi javac.

Một bước đầu:

~~~bash
./gradlew :app:compileJava --info
~~~

Để có log chi tiết hơn, có thể dùng:

~~~bash
./gradlew :app:compileJava --debug
~~~

Đầu ra của từng phiên bản Gradle/toolchain có thể khác nhau, và không nhất thiết in đầy đủ mọi compiler argument dưới một dòng dễ đọc. Nếu cần kiểm tra cụ thể, dùng build diagnostics hoặc logging trong phạm vi dự án để xem compiler options và các file được phân loại vào module path.

Các điểm cần xác nhận:

- Có module-info.java trong source set thực sự được compile.
- modularity.inferModulePath đang được bật.
- Đúng JDK/toolchain được dùng cho JavaCompile.
- Dependency có module-info.class hoặc Automatic-Module-Name khi cần được Gradle nhận diện.
- Source module name trong requires khớp module name của dependency.
- Package cần dùng được exports bởi dependency.

Nếu compiler không tìm thấy module, đừng thêm --add-exports trước khi xác nhận artifact có mặt ở module path. Export chỉ giải quyết package access, không tạo module bị thiếu.

## 16. Java Toolchains và --release

Dùng toolchain để cố định JDK compile:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}
~~~

Nếu cần tạo bytecode tương thích Java 17 khi biên dịch trên JDK hỗ trợ target đó:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Toolchain chọn JDK dùng để chạy compiler; --release chỉ định language level, class-file format và API nền tảng phù hợp với target release. Đây không phải cùng một cấu hình.

Nếu chạy CI hoặc application runtime trên Java 17, cần kiểm tra dependency có được biên dịch phù hợp và module descriptor không yêu cầu API chỉ xuất hiện trên Java mới hơn.

Sử dụng module-info.java yêu cầu Java 9 trở lên. Không thể dùng --release 8 với source module descriptor theo cách biên dịch JPMS thông thường.

## 17. Cấu hình chạy ứng dụng theo module identity

Với Application Plugin:

~~~groovy
application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'
}
~~~

Có thể chạy:

~~~bash
./gradlew :app:run
~~~

Và tạo bản phân phối:

~~~bash
./gradlew :app:installDist
~~~

Sau khi build, nếu muốn kiểm tra thủ công bằng Java launcher, chỉ dùng các JAR thực sự đã tạo và kiểm tra module name:

~~~bash
jar --describe-module --file catalog/build/libs/catalog.jar
jar --describe-module --file app/build/libs/app.jar
~~~

Nếu file JAR thực tế có hậu tố version, thay path trên bằng tên đúng trong build/libs. Sau đó dùng module path với các JAR tương ứng:

~~~bash
java --module-path "catalog/build/libs:app/build/libs" \
     --show-module-resolution \
     -m com.acme.app/com.acme.app.Main
~~~

Trên Windows, thay dấu phân cách path bằng dấu chấm phẩy và dùng dạng lệnh phù hợp shell.

Thông tin --show-module-resolution giúp kiểm tra những module đã được phân giải; tuy nhiên bản thân nó không chứng minh mọi provider hoặc class được tải động đều đã được khám phá.

## 18. Testing trên module path cần xem riêng

Một ứng dụng modular có thể compile main source thành công nhưng test thất bại do cấu trúc test khác:

- Test class nằm trên classpath, không ở cùng named module với production class.
- Framework dùng reflection sâu để tạo test object hoặc truy cập private member.
- Test cần truy cập implementation package chưa export.
- Một số test framework có automatic module name hoặc module metadata khác với dự đoán.

Cấu hình Gradle test không thể suy ra một cách máy móc chỉ từ main source set. Với integration test, cần xác nhận JVM test thực tế sử dụng module path hay classpath và test code được nạp vào module nào.

Ví dụ khi test framework cần reflection sâu, có thể phải cấu hình JVM args có chủ đích:

~~~groovy
tasks.named('test', Test) {
    jvmArgs '--add-opens=com.acme.catalog/com.acme.catalog.internal=ALL-UNNAMED'
}
~~~

Đây chỉ là ví dụ về một tình huống có thể dùng trong migration; nó chỉ có tác dụng nếu package và module thực sự tồn tại, có mặt trong graph, và test code ở unnamed module. Không nên thêm opens rộng khi chưa biết caller nào cần. Với test nằm trong named module, target của opens có thể là tên module test framework hoặc module khác thích hợp.

## 19. Reflection, resources và ServiceLoader

Khi chuyển dependency lên module path, runtime access có thể khác so với classpath cũ.

**Reflection:** Package được exports cho regular code access không đồng nghĩa đã opens cho deep reflection. Framework serialization/ORM có thể cần qualified opens:

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.fasterxml.jackson.databind;
}
~~~

Tên com.fasterxml.jackson.databind phải khớp module identity thực tế của library. Nếu dùng phiên bản thư viện khác hoặc JAR chưa modular, cần xác nhận lại trước khi viết descriptor.

**Resources:** ClassLoader.getResource và Class.getResource có thể cho kết quả khác khi resource nằm trong package bị encapsulate. Thử đúng cách đóng gói và class loader dùng trong production.

**ServiceLoader:** Consumer khai báo uses; provider khai báo provides ... with ...:

~~~java
module com.acme.app {
    requires com.acme.catalog;
    uses com.acme.catalog.api.CatalogProvider;
}
~~~

Provider module:

~~~java
module com.acme.catalog.provider {
    requires com.acme.catalog;
    provides com.acme.catalog.api.CatalogProvider
        with com.acme.catalog.provider.DefaultCatalogProvider;
}
~~~

Không phải cứ thêm runtimeOnly dependency là service provider chắc chắn được phân giải và tải trong mọi cấu hình. Hãy xác nhận module provider được đưa vào runtime graph hoặc cấu hình service binding thích hợp, và test ServiceLoader với artifact phát hành thật.

## 20. Annotation processing và code generation

Gradle Java Plugin có configuration annotationProcessor cho các thư viện processor:

~~~groovy
dependencies {
    annotationProcessor 'com.example:some-processor:1.0'
}
~~~

Đây là configuration phục vụ compiler chạy annotation processor; không mặc định là module dependency của mã ứng dụng.

Nếu processor là một named module, Java compiler cũng có các cơ chế module path dành riêng cho processor. Tuy nhiên, cách Gradle cung cấp processor path và module path phụ thuộc cấu hình toolchain/plugin. Không nên đơn giản thêm requires tới module processor chỉ để kích hoạt annotation processing.

Khi code generation sinh class trong package của một named module, hãy xác nhận generated source được compile trong đúng module, không vô tình tạo split package hoặc source path bị ánh xạ sai.

Các dự án dùng Lombok, MapStruct hoặc processor riêng cần kiểm thử compiler task trên module path thật thay vì chỉ dựa vào kết quả IDE.

## 21. jlink và module path của Gradle không giống nhau

Module-path inference giúp Gradle compile và run named module. Nó **không tự có nghĩa** Java Plugin đã tạo custom runtime image.

Nếu muốn dùng jlink, thông thường cần:

1. Build explicit modular JAR cho ứng dụng và các dependency có thể link.
2. Cung cấp JDK jmods và các module application trên module path của jlink.
3. Chọn root bằng --add-modules.
4. Xem xét --bind-services nếu cần service provider.
5. Kiểm tra image cuối cùng bằng image/bin/java --list-modules và chạy integration tests.

Một automatic module có thể được sử dụng như cầu nối trên module path trong giai đoạn migration, nhưng không phải đầu vào explicit-module phù hợp để link trực tiếp như một module ứng dụng bằng jlink.

Nếu build cần tự động hóa jlink, hãy dùng workflow/task/plugin chuyên biệt và kiểm thử trên môi trường mục tiêu. Đừng kỳ vọng task jar hoặc build của Java Plugin tự tạo runtime image.

## 22. Bảng triệu chứng và hướng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| module not found: X | Dependency không nằm trong module path hoặc tên module không khớp | Kiểm tra jar --describe-module, Gradle dependency và compiler args |
| package ... is not visible | Thiếu requires/readability hoặc package chưa export | Kiểm tra module-info.java của consumer và provider |
| Cannot read unnamed module | Named module phụ thuộc vào code còn trên classpath | Xem lại tính modular của thư viện và Gradle inference |
| Split package conflict | Nhiều module dùng cùng package | Kiểm kê JAR, đổi/gộp package hoặc nâng dependency |
| Test báo InaccessibleObjectException | Reflection sâu vào package chưa mở | Kiểm tra opens và target module thực tế |
| Code chạy trong IDE nhưng Gradle lỗi | IDE và Gradle chọn classpath/module path hoặc JDK khác nhau | Chạy Gradle wrapper, kiểm tra toolchain và compile task |
| Compile qua nhưng runtime NoClassDefFoundError | Thiếu dependency/runtime module, hoặc khác class loader | Kiểm tra runtimeClasspath, module resolution, artifact |
| ServiceLoader không thấy provider | Provider module không resolved hoặc registration thiếu | Kiểm tra uses/provides, runtime graph, module metadata |
| Resource trả null sau migration | Resource lookup khác theo module/class loader | Kiểm tra đóng gói resource và module encapsulation |
| Build thành công nhưng jlink lỗi | Dependency chưa là explicit module hoặc thiếu JMOD/module | Kiểm tra module graph riêng của jlink |

Đừng cố giải quyết tất cả triệu chứng bằng --add-exports hoặc --add-opens. Các cờ đó chỉ thay đổi một phần quyền truy cập, không sửa dependency thiếu, module name sai hoặc package ownership.

## 23. Quy trình chuyển một Gradle project sang module path

Một trình tự thực hành hiệu quả:

1. **Chốt baseline:** build và test dự án classpath đang hoạt động, xác định JDK và Gradle Wrapper.
2. **Kiểm kê dependency:** chạy dependencies, dependencyInsight và dùng jdeps để xác định JDK modules cùng internal APIs.
3. **Đánh giá JAR:** kiểm tra explicit module-info.class, Automatic-Module-Name và tên module thực tế.
4. **Thiết kế module boundary:** tách package API khỏi implementation, loại split packages và dependency cycles.
5. **Thử module nhỏ:** thêm module-info.java vào một library có dependency ít.
6. **Bật inference rõ ràng:** cấu hình modularity.inferModulePath cho project hoặc source set cần chuyển.
7. **Đồng bộ khai báo:** Gradle dependencies cho artifact và requires/exports trong descriptor.
8. **Build bằng wrapper:** chạy compileJava, test, jar và kiểm tra output module-info.class.
9. **Chuyển ứng dụng chính:** thiết lập mainModule và mainClass trong Application Plugin.
10. **Kiểm tra runtime:** chạy Gradle run, distribution startup script và Java launcher với --show-module-resolution.
11. **Xử lý dynamic access:** kiểm thử reflection, resources, ServiceLoader, annotation processor và class loader.
12. **Phát hành từng phần:** ghi lại cờ migration tạm thời, kiểm tra JDK mục tiêu và có kế hoạch rollback.

Không cần chuyển toàn bộ dependency sang module path ngay lập tức nếu chúng chưa sẵn sàng. Một module boundary rõ ràng, ít cờ tạm thời và build ổn định thường hữu ích hơn việc chỉ di chuyển nhiều JAR cùng lúc.

## 24. Checklist trước khi đóng gói và phát hành

- [ ] JDK toolchain và Gradle Wrapper được cố định.
- [ ] Source chính có module-info.java ở vị trí đúng.
- [ ] modularity.inferModulePath được cấu hình theo chủ đích.
- [ ] Gradle dependency tương ứng với requires trong module descriptor.
- [ ] Đã xác minh module name thực tế của từng JAR quan trọng.
- [ ] Public API nằm trong package được exports phù hợp.
- [ ] Không có split packages hoặc requires cycles chưa xử lý.
- [ ] Dependency chưa modular được phân loại và có hướng chuyển đổi.
- [ ] Application Plugin dùng mainModule và mainClass đúng.
- [ ] Task test chạy trên cấu hình tương thích JPMS.
- [ ] Reflection và resource access đã được thử trong môi trường runtime thật.
- [ ] ServiceLoader phát hiện provider đúng như mong đợi.
- [ ] Artifact JAR cuối cùng có module-info.class và dependency cần thiết.
- [ ] Startup script/distribution dùng đúng module graph.
- [ ] Nếu tạo runtime image, đã kiểm tra riêng graph cho jlink.
- [ ] Có test trên JDK và OS mục tiêu, không chỉ thành công trong IDE.

## Kết luận

**Module path trong Gradle Java Plugin** là kết quả của việc Gradle suy luận hoặc cấu hình nơi đặt các dependency khi compiler và JVM xử lý một ứng dụng dùng JPMS. Việc có module-info.java và bật modularity.inferModulePath giúp Gradle xử lý named modules tốt hơn, nhưng Gradle không thể tự tạo một module graph đúng nếu dependency descriptor, package visibility hoặc module metadata chưa phù hợp.

Trong một build modular ổn định, Gradle cung cấp đúng artifact, JPMS descriptor khai báo đúng readability và package access, còn Application Plugin khởi chạy bằng đúng module name. Hãy kiểm tra ba lớp đó cùng nhau, đặc biệt với automatic modules, test framework, ServiceLoader và thư viện legacy, để chuyển từ classpath sang module path có kiểm soát.
