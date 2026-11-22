# Thêm Automatic-Module-Name như bước chuyển tiếp

Khi một thư viện Java được phát hành từ thời classpath chưa có **module-info.java**, ứng dụng dùng Java Platform Module System (JPMS) vẫn có thể đưa JAR của thư viện đó lên module path. JAR không có descriptor tường minh sẽ được module system coi là **automatic module**. Vấn đề là tên automatic module có thể được suy ra từ tên file JAR, nên dễ thay đổi khi artifact được đổi tên, thay đổi quy ước đóng gói hoặc nâng cấp phiên bản.

Thuộc tính manifest **Automatic-Module-Name** cho phép tác giả thư viện ấn định một tên module ổn định trước khi chuyển thư viện sang dạng explicit named module. Đây là một bước chuyển tiếp hữu ích: consumer bắt đầu viết **requires** theo một tên có chủ đích, trong khi artifact vẫn có thể phục vụ ứng dụng classpath và chưa bắt buộc phải có **module-info.class**.

Điểm cốt lõi: **Automatic-Module-Name chỉ ổn định tên, không biến JAR thành explicit modular JAR và không tự tạo ranh giới encapsulation.** Dùng thuộc tính này để giảm rủi ro khi migration, đồng thời chuẩn bị kế hoạch bổ sung module descriptor đúng nghĩa.

## 1. Vấn đề trước khi có Automatic-Module-Name

Giả sử một thư viện được phát hành dưới tên:

~~~text
acme-codec-1.8.0.jar
~~~

JAR này không chứa file **module-info.class**. Khi đưa nó lên module path, Java có thể tạo automatic module với tên được suy ra từ tên JAR theo quy tắc của module system. Tên được suy ra thường loại bỏ phần suffix phiên bản và chuẩn hóa ký tự phân cách, nhưng đây không phải một hợp đồng module name mà tác giả thư viện đã công bố trực tiếp.

Nếu JAR được đổi tên vì chính sách artifact, ví dụ:

~~~text
acme-codec-1.8.0.jar
acme-serialization-codec-2.0.0.jar
~~~

tên automatic module được suy ra có thể thay đổi. Một ứng dụng có module descriptor:

~~~java
module com.acme.application {
    requires acme.codec;
}
~~~

có thể không còn resolve được dependency ở lần nâng cấp khi tên module mới khác với tên trước đó. Vấn đề không nhất thiết nằm ở API class của thư viện: cùng một package và class vẫn có thể tồn tại, nhưng tên module dùng trong **requires** không còn khớp.

Thuộc tính **Automatic-Module-Name** giải quyết một phần rủi ro này bằng cách tách tên module khỏi tên file JAR.

## 2. Automatic-Module-Name là gì?

Đây là một thuộc tính trong file **META-INF/MANIFEST.MF** của JAR. Ví dụ:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.codec
~~~

Khi JAR không có explicit module descriptor và được đặt trên module path của Java 9 trở lên, module system ưu tiên dùng giá trị **com.acme.codec** làm tên automatic module thay vì suy ra tên từ filename.

Ví dụ:

~~~text
mlib/
└── acme-codec-1.8.0.jar
    └── META-INF/
        └── MANIFEST.MF
~~~

Nếu manifest chứa:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

thì một named module khác có thể khai báo:

~~~java
module com.acme.application {
    requires com.acme.codec;
}
~~~

Tên **com.acme.codec** có thể được giữ nguyên ở nhiều phiên bản artifact dù tên JAR thay đổi.

Giá trị này cần là một module name hợp lệ theo quy tắc JPMS. Nên dùng tên có cấu trúc giống package và theo quy ước đảo ngược tên miền, ví dụ **com.acme.codec**, **org.example.csv** hoặc **io.example.transport**. Tránh tên chung chung như **util**, **common** hoặc **core** vì dễ va chạm với dependency khác.

## 3. Automatic-Module-Name thay đổi điều gì, không thay đổi điều gì?

Khi thư viện chưa có module-info.class, tên module có thể đến từ manifest. Các quy tắc khác của automatic module vẫn được áp dụng.

| Khía cạnh | Sau khi thêm Automatic-Module-Name |
|---|---|
| Tên automatic module | Dùng tên được khai báo trong manifest |
| Phụ thuộc của named consumer | Có thể viết **requires** theo tên module ổn định |
| Có **module-info.class** tường minh | Chưa có |
| Các package được export | Automatic module vẫn export các package của nó |
| Deep reflection | Automatic module vẫn có hành vi mở các package theo quy tắc automatic module |
| Đồ thị dependency tường minh của thư viện | Chưa được mô tả bằng bộ **requires** do tác giả viết |
| Khả năng dùng trên classpath | Vẫn có thể dùng JAR theo cơ chế classpath |
| Maven/Gradle dependency version | Không được quản lý bởi thuộc tính manifest |
| Khả năng trở thành explicit module ở bản sau | Có, nếu phát hành descriptor có cùng tên và hợp đồng API phù hợp |

Điều này có nghĩa **Automatic-Module-Name** không phải biện pháp thay thế **exports**, **opens**, **uses** hay **provides**. Nó chỉ giải quyết chuyện đặt tên trong giai đoạn automatic module.

Trong một automatic module, quy tắc readability và encapsulation mang tính tương thích rộng hơn explicit module. Thư viện legacy nhờ đó dễ tham gia module path, nhưng consumer vẫn có thể phụ thuộc vào những package implementation mà tác giả chưa từng xác nhận là API ổn định.

## 4. Khi nào nên thêm thuộc tính này?

Đây là bước phù hợp khi có một hoặc nhiều điều kiện sau:

1. Thư viện chưa sẵn sàng phát hành **module-info.java** vì còn hỗ trợ môi trường Java cũ hoặc có dependency chưa modular hóa.
2. Có ứng dụng đang chuyển dần sang JPMS và cần khai báo **requires** tới thư viện.
3. Tên JAR chứa classifier, thông tin phiên bản hoặc hậu tố có thể thay đổi giữa các bản phát hành.
4. Nhóm duy trì muốn giữ tên module ổn định để sau này thêm explicit descriptor mà không buộc consumer đổi **requires**.
5. Thư viện đã xuất hiện như automatic module trong runtime graph và cần giảm bất ổn về identity trong quá trình migration.

Nếu thư viện đã có **module-info.class** tường minh, việc thêm **Automatic-Module-Name** không thay thế tên module trong descriptor. Khi explicit descriptor có mặt, tên module trong descriptor là tên authoritative.

Nếu thư viện chưa có consumer dùng module path, thuộc tính này vẫn có thể được thêm sớm như một cách công bố định hướng tên module. Nhưng nó không tự đem lại lợi ích encapsulation cho ứng dụng classpath.

## 5. Đặt tên module ổn định ngay từ đầu

Tên được công bố trong manifest sẽ trở thành một phần của hợp đồng sử dụng thư viện trên module path. Do đó, không nên xem nó như một chi tiết build dễ thay đổi.

Một số nguyên tắc:

- Dùng tên có namespace rõ, thường theo reverse-domain naming.
- Chọn một tên duy nhất cho một module logic; tránh cùng tên cho các thư viện khác nhau.
- Không đưa phiên bản vào module name, ví dụ tránh **com.acme.codec.v2** chỉ vì artifact lên bản 2.0.
- Không đặt tên theo tên file JAR đang dùng nếu filename là chi tiết đóng gói tạm thời.
- Xác định module name dự kiến của explicit descriptor ngay khi chọn tên manifest.
- Kiểm tra tên không trùng system module hoặc module khác trong runtime dependency graph.
- Lưu tên module trong tài liệu phát hành để consumer không phải tự suy đoán.
- Hạn chế đổi tên module; nếu bắt buộc đổi thì coi đó là migration có tác động tới source descriptor của consumer.

Ví dụ tên được lựa chọn:

~~~text
Artifact: com.acme:codec-core:1.8.0
JAR: codec-core-1.8.0.jar
Automatic-Module-Name: com.acme.codec
Future module-info.java: module com.acme.codec { ... }
~~~

Maven coordinates và module name là hai hệ thống định danh khác nhau. GroupId, artifactId và version dùng để build tool chọn artifact; JPMS dùng module name để resolve module.

## 6. Thêm manifest attribute với Maven

Nếu dự án đóng gói JAR bằng Maven, có thể cấu hình **maven-jar-plugin** để ghi thuộc tính manifest.

Ví dụ trong **pom.xml**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <configuration>
        <archive>
          <manifestEntries>
            <Automatic-Module-Name>com.acme.codec</Automatic-Module-Name>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Trong dự án thực tế, nên pin version plugin theo chính sách build hoặc quản lý phiên bản plugin tại parent POM. Phần minh họa tập trung vào vị trí thuộc tính manifest.

Đóng gói thư viện:

~~~bash
mvn clean package
~~~

Đọc lại manifest của artifact đã tạo bằng JDK hoặc công cụ ZIP/JAR để xác nhận tên module thực sự có mặt, thay vì chỉ xem cấu hình trong POM.

Nếu build pipeline tạo thêm **sources JAR**, **javadoc JAR** hoặc shaded JAR, cần xác định artifact nào thực sự được consumer dùng trên module path. Thuộc tính cần nằm trong JAR runtime được phát hành, không chỉ trong artifact phụ.

Nếu dự án dùng plugin khác để tạo uber-JAR hoặc repackage artifact, hãy kiểm tra bước đóng gói cuối có giữ nguyên **META-INF/MANIFEST.MF** và thuộc tính **Automatic-Module-Name** hay không.

## 7. Thêm manifest attribute với Gradle

Với Gradle Groovy DSL, có thể cấu hình task **jar**:

~~~groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.acme.codec'
        )
    }
}
~~~

Sau đó chạy:

~~~bash
./gradlew clean jar
~~~

Với Gradle Kotlin DSL, cấu hình tương đương:

~~~kotlin
tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Automatic-Module-Name" to "com.acme.codec"
        )
    }
}
~~~

Trong dự án multi-project, cần cấu hình đúng subproject tạo thư viện. Không nên gán cùng một module name cho mọi subproject bằng cấu hình dùng chung nếu các subproject tạo ra các module khác nhau.

Nếu pipeline phát hành biến JAR thường thành fat JAR, shadow JAR hoặc sản phẩm đóng gói khác, hãy kiểm tra manifest của artifact cuối. Một tên module ổn định chỉ giúp consumer nếu đúng artifact dùng ở runtime mang thuộc tính đó.

## 8. Xác nhận artifact đã có Automatic-Module-Name

Cấu hình build chưa phải bằng chứng rằng JAR phát hành chứa thuộc tính manifest. Cần xác minh trên file đầu ra.

Đầu tiên, kiểm tra JAR không vô tình có descriptor tường minh:

~~~bash
jar --list --file build/libs/codec-core.jar
~~~

Nếu danh sách có **module-info.class** ở root, đây có thể đã là explicit modular JAR, không còn chỉ là automatic module. Nếu không có descriptor, tiếp tục kiểm tra manifest và cách JDK nhận diện module.

Dùng:

~~~bash
jar --describe-module --file build/libs/codec-core.jar
~~~

Kết quả sẽ mô tả module mà JDK nhận diện từ JAR. Với JAR không có descriptor, công cụ có thể mô tả automatic module và tên được suy ra hoặc tên từ manifest. Cách trình bày chi tiết của output phụ thuộc JDK; điều quan trọng là tên module và trạng thái automatic có đúng hay không.

Có thể kiểm tra bằng **ModuleFinder** ngay trong Java:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
            Path.of("build/libs/codec-core.jar")
        );

        ModuleReference reference = finder
            .find("com.acme.codec")
            .orElseThrow();

        System.out.println(reference.descriptor().name());
        System.out.println(reference.descriptor().isAutomatic());
    }
}
~~~

Với JAR legacy chỉ có manifest attribute, kỳ vọng tên là **com.acme.codec** và **isAutomatic()** là **true**. Nếu sau này artifact có explicit descriptor, tên có thể giữ nguyên nhưng **isAutomatic()** phải là **false**.

Đây là cách kiểm tra khác biệt quan trọng giữa **ổn định tên** và **modular hóa tường minh**.

## 9. Dùng thư viện từ một named module consumer

Giả sử thư viện JAR được đặt tại:

~~~text
mlib/
└── codec-core-1.8.0.jar
~~~

JAR chứa:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

Ứng dụng consumer có descriptor:

~~~java
module com.acme.application {
    requires com.acme.codec;
}
~~~

Ứng dụng có thể import các class public của thư viện theo package thực tế:

~~~java
package com.acme.application;

import com.acme.codec.api.Codec;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Codec().encode("hello"));
    }
}
~~~

Để biên dịch và chạy, cần có module ứng dụng và automatic module trên module path, ví dụ khi đã có các artifact phù hợp:

~~~bash
javac --module-path mlib -d out \
  src/com.acme.application/module-info.java \
  src/com.acme.application/com/acme/application/Main.java
~~~

~~~bash
java --module-path "mlib:out" \
  -m com.acme.application/com.acme.application.Main
~~~

Hai câu lệnh minh họa cú pháp POSIX, nơi các mục module path phân cách bằng dấu hai chấm. Trên Windows, dùng dấu chấm phẩy giữa các mục, ví dụ **"mlib;out"**. Cấu trúc source/output có thể khác khi build hệ thống nhiều module; cần điều chỉnh đúng thư mục exploded module hoặc modular JAR thực tế.

Nếu application không tìm thấy **com.acme.codec**, hãy xác nhận tên manifest và module path trước khi sửa **requires**. Thêm một JAR vào classpath không khiến named consumer đọc nó thông qua **requires com.acme.codec**.

## 10. Tính tương thích với ứng dụng Java 8 và classpath

Một lợi ích của **Automatic-Module-Name** là nó chỉ là metadata manifest. Với ứng dụng chạy Java 8 và sử dụng JAR trên classpath, thuộc tính này không biến thư viện thành named module và không khiến Java 8 phải đọc JPMS descriptor.

Do đó, một JAR không chứa module-info.class có thể:

- Tiếp tục chạy trên Java 8 khi bytecode và API vẫn tương thích với Java 8.
- Có tên automatic module ổn định khi được đặt trên module path của Java 9 trở lên.
- Phục vụ các consumer classpath và module path trong thời gian chuyển đổi.

Tuy nhiên, chỉ thêm thuộc tính manifest **không bảo đảm** Java 8 compatibility. Nếu thư viện đã được biên dịch thành bytecode phiên bản mới hoặc sử dụng API chỉ có trên Java mới, Java 8 vẫn không chạy được. Build vẫn phải thiết lập compiler release/target và kiểm thử runtime theo phiên bản được hỗ trợ.

Thuộc tính manifest giúp giảm trở ngại migration, nhưng không thay thế chính sách hỗ trợ JDK của thư viện.

## 11. Những giới hạn của automatic module vẫn còn

### 11.1. Không có exports được thiết kế tường minh

Automatic module export các package theo quy tắc tương thích. Consumer có thể import class public ở package implementation dù tác giả không xem đó là API ổn định.

Điều này có thể khiến consumer hình thành dependency vào chi tiết nội bộ. Khi chuyển sang explicit module và chỉ export package API thực sự, consumer đó sẽ không compile hoặc chạy được nếu vẫn dùng class nội bộ.

Vì vậy, ngay khi dùng Automatic-Module-Name, hãy công bố rõ package nào được xem là API ổn định trong tài liệu và kiểm thử consumer chỉ dùng những package đó.

### 11.2. Dependency chưa được khai báo bằng requires tường minh

Automatic module dùng quy tắc readability đặc biệt để hỗ trợ JAR legacy. Nó không chứa bộ **requires** do tác giả thư viện review giống explicit module descriptor.

Khi chuyển sang explicit module, tác giả phải xác định dependency thực sự cần thiết, phân biệt **requires**, **requires transitive** và **requires static**, rồi kiểm tra module graph.

Một runtime chạy được với automatic module chưa đủ để kết luận descriptor mới sẽ hợp lệ.

### 11.3. Reflection và framework có thể thay đổi khi modular hóa

Automatic module có hành vi mở package rộng để tương thích với code và reflection cũ. Khi thêm explicit descriptor, package không được mở sẽ chịu strong encapsulation của named module.

Các framework ORM, JSON serialization hoặc dependency injection có thể cần **opens** hoặc API công khai thích hợp. Không nên đổi trạng thái module mà thiếu integration test cho các code path dùng reflection.

### 11.4. Service metadata có thể cần được chuyển đổi

JAR legacy có thể khai báo service provider qua file **META-INF/services/**. Module system có cơ chế diễn giải service metadata của automatic module, nhưng explicit module cần khai báo **provides ... with ...** đúng contract, và consumer named module cần **uses** khi dùng ServiceLoader.

Khi chuyển sang explicit descriptor, kiểm tra service discovery bằng test chạy thực tế. Đừng giả định việc giữ nguyên file META-INF/services bảo đảm hành vi mọi layer giống trước.

### 11.5. Không giải quyết split package

Nếu hai JAR cùng chứa class thuộc một package, việc thêm Automatic-Module-Name không chuyển chúng thành một module hợp lệ. Khi đặt cả hai trên module path, split package vẫn có thể gây xung đột về readability, exports hoặc class-loader mapping.

Hãy tách namespace, hợp nhất artifact khi phù hợp hoặc thay dependency; không dùng thuộc tính manifest như một biện pháp sửa split package.

## 12. Chọn thời điểm chuyển sang module-info.java

Khi thư viện và dependency đã sẵn sàng để thiết kế module boundary thực sự, nên chuyển từ automatic sang explicit module.

Một descriptor tương lai có thể là:

~~~java
module com.acme.codec {
    requires java.logging;

    exports com.acme.codec.api;
    opens com.acme.codec.model to com.acme.serializer;

    uses com.acme.codec.spi.CodecExtension;
    provides com.acme.codec.spi.CodecExtension
        with com.acme.codec.internal.DefaultCodecExtension;
}
~~~

Đây chỉ là ví dụ minh họa. Descriptor thực tế cần khớp với những package, dependency và service type có thật trong thư viện. Không copy các directive mẫu vào project nếu module tương ứng chưa tồn tại hoặc package không cần reflection.

Nguyên tắc chuyển đổi:

1. **Giữ tên module ổn định:** tên trong **module-info.java** nên là tên đã công bố qua **Automatic-Module-Name** nếu không có lý do buộc đổi.
2. **Xác định public API:** export những package mà consumer thực sự được hỗ trợ sử dụng.
3. **Khai báo dependency:** viết requires theo dependency thực tế và review tính transitive khi API công khai chứa kiểu từ module khác.
4. **Xử lý reflection:** mở đúng package cho framework cần thiết, tránh mở toàn module.
5. **Xử lý service:** khai báo uses/provides theo contract và kiểm tra provider discovery.
6. **Xử lý vấn đề cấu trúc:** giải quyết split package, cycle hoặc dependency vào classpath trước khi công bố descriptor.
7. **Kiểm thử consumer:** chạy compile, unit test, integration test và khởi động trên đúng JDK/module path.
8. **Phát hành có kiểm soát:** cập nhật release notes để consumer biết module đã chuyển từ automatic sang explicit.

Chuyển sang explicit module có thể làm lộ các phụ thuộc vào package nội bộ vốn được automatic module export. Đây là thay đổi có tác động tới consumer; cần cung cấp hướng migration thay vì xem đó là lỗi của người sử dụng.

## 13. Nếu vẫn cần hỗ trợ Java 8 khi đã có module-info.class

File **module-info.class** là thành phần của JPMS bắt đầu từ Java 9. Một thư viện muốn có explicit descriptor trên Java 9+ nhưng vẫn hỗ trợ chạy trên Java 8 có thể cân nhắc **multi-release JAR**.

Một chiến lược đóng gói là giữ class tương thích Java 8 ở root và đặt module descriptor trong vùng dành cho Java 9:

~~~text
codec-core.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 9/
│           └── module-info.class
└── com/acme/codec/...
~~~

Manifest cần khai báo thuộc tính multi-release phù hợp:

~~~text
Multi-Release: true
~~~

Khi dùng multi-release JAR, JDK 9+ có thể nhìn thấy descriptor phiên bản phù hợp theo quy tắc đóng gói, trong khi runtime Java 8 sử dụng nội dung tương thích tại root. Quy trình này phức tạp hơn chỉ thêm Automatic-Module-Name: cần build nhiều target bytecode, đóng gói đúng entry và kiểm thử trên cả Java 8 lẫn các JDK mới.

Nếu đội ngũ chưa cần explicit module ngay, dùng Automatic-Module-Name trước là lựa chọn chuyển tiếp đơn giản hơn. Nhưng không nên kéo dài vô hạn nếu mục tiêu cuối là strong encapsulation và module descriptor đầy đủ.

## 14. Rủi ro khi đổi tên module giữa các phiên bản

Thêm Automatic-Module-Name lần đầu cũng có thể là một thay đổi gây tác động.

Ví dụ, phiên bản cũ chưa có manifest attribute và Java tự suy ra tên **acme.codec.core**. Một ứng dụng đã khai báo:

~~~java
module com.acme.application {
    requires acme.codec.core;
}
~~~

Phiên bản mới thêm:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

Khi đó tên module thay đổi từ **acme.codec.core** sang **com.acme.codec**. Consumer phải cập nhật **requires**. Dù mã Java của thư viện không đổi, việc thay đổi module name là thay đổi hợp đồng JPMS.

Để giảm tác động:

- Kiểm kê consumer dùng module path và tên automatic module cũ.
- Chọn tên mới theo chiến lược dài hạn, không đổi tiếp giữa các release.
- Ghi rõ tên cũ và tên mới trong release notes.
- Cho consumer thời gian chuyển **module-info.java** và cấu hình launcher.
- Kiểm tra module path không còn đồng thời chứa hai JAR có cùng module name hoặc hai bản thư viện gây xung đột.
- Nếu phù hợp, giữ tên đã được consumer sử dụng ổn định thay vì chọn tên đẹp hơn nhưng gây nhiều thay đổi.

Không có cơ chế alias module name tổng quát trong JPMS tương đương symlink giữa hai tên module. Nếu cần đổi tên, phải điều phối consumer và artifact thực tế.

## 15. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| JAR trên classpath nhưng named consumer báo module không tìm thấy | Classpath không cung cấp named module cho requires | Đưa JAR lên module path đúng runtime |
| Tên module khác mong đợi | Manifest attribute không được đóng gói, hoặc tên suy ra từ filename | Kiểm tra artifact cuối bằng jar --describe-module |
| isAutomatic() vẫn trả về true | Thuộc tính manifest không tạo explicit descriptor | Đây là trạng thái dự kiến trong giai đoạn chuyển tiếp |
| Thêm manifest nhưng chương trình không chạy trên Java 8 | Bytecode/API không tương thích với Java 8 | Điều chỉnh compiler target/release và kiểm thử trên Java 8 |
| Consumer lỗi sau khi đổi tên module | requires còn dùng tên automatic module cũ | Cập nhật descriptor của consumer và launcher flags |
| Build tạo JAR đúng nhưng shadow/fat JAR sai manifest | Bước đóng gói cuối ghi đè hoặc bỏ metadata | Cấu hình manifest cho artifact cuối |
| Runtime báo hai module trùng tên | Hai artifact cùng được nhận diện với một module name | Loại bỏ artifact trùng và thống nhất dependency resolution |
| Runtime báo package xung đột | Split package giữa dependency | Sửa cấu trúc package/artifact, không trông chờ vào module name |
| Consumer đang dùng class implementation mà explicit module sắp ẩn | Automatic module trước đó export rộng | Thay bằng API được hỗ trợ hoặc thiết kế migration |
| ServiceLoader mất provider sau khi đổi sang explicit module | Descriptor thiếu provides/uses hoặc provider chưa được resolve | Kiểm tra service metadata, configuration và layer |

Một nguyên tắc hữu ích là giữ được ba loại bằng chứng riêng: **manifest có đúng thuộc tính**, **JDK đọc ra đúng module name**, và **ứng dụng thực tế resolve được module đó**. Chỉ một trong ba điều kiện chưa đủ để khẳng định quá trình chuyển đổi hoạt động.

## 16. Kiểm soát bằng CI và tài liệu phát hành

Đối với thư viện được dùng bởi nhiều dự án, có thể bổ sung bước kiểm tra tự động sau khi tạo JAR:

1. Build artifact runtime đúng như artifact sẽ publish.
2. Kiểm tra manifest chứa **Automatic-Module-Name** đúng tên đã cam kết.
3. Kiểm tra JAR chưa vô tình có descriptor tường minh nếu release hiện tại vẫn ở trạng thái automatic.
4. Dùng **ModuleFinder** hoặc **jar --describe-module** để xác nhận tên module JDK nhận diện.
5. Biên dịch một named consumer đơn giản có **requires** đúng tên để kiểm chứng integration.
6. Chạy smoke test với artifact trên module path.
7. Với thư viện vẫn hỗ trợ Java 8, chạy compatibility test bằng Java 8.
8. Đưa tên module vào release notes và thông tin API của thư viện.

Ví dụ một tiêu chí CI nhỏ bằng Java:

~~~java
ModuleReference ref = ModuleFinder
    .of(Path.of("dist/codec-core.jar"))
    .find("com.acme.codec")
    .orElseThrow(() -> new AssertionError("Wrong module name"));

if (!ref.descriptor().isAutomatic()) {
    throw new AssertionError("Unexpected explicit descriptor");
}
~~~

Đoạn code này chỉ phù hợp ở giai đoạn mà JAR dự kiến vẫn là automatic module. Khi phát hành explicit modular JAR, điều kiện kiểm tra cần đổi: tên module giữ nguyên nhưng **isAutomatic()** phải là **false**.

Với dự án lớn, nên lưu một bảng migration gồm artifact, module name hiện tại, tên dự kiến của explicit module, owner, thời hạn và trạng thái chuyển đổi. Việc có CI và owner giúp thuộc tính Automatic-Module-Name không trở thành điểm dừng vô thời hạn.

## 17. Lộ trình migration thực tế

Có thể triển khai theo các bước sau:

| Giai đoạn | Công việc chính | Tiêu chí hoàn thành |
|---|---|---|
| 1. Kiểm kê | Xác định JAR legacy, module name tự suy ra và consumer trên module path | Biết dependency nào đang dựa vào tên tự suy ra |
| 2. Chọn tên | Thiết kế tên module ổn định, tránh xung đột | Tên có owner và được ghi nhận trong tài liệu |
| 3. Manifest | Thêm Automatic-Module-Name vào JAR runtime | Artifact cuối chứa đúng manifest attribute |
| 4. Xác minh | Dùng ModuleFinder, jar --describe-module và named consumer test | JDK nhận diện tên đúng, vẫn là automatic module |
| 5. Migration consumer | Đổi requires và launcher config khi cần | Consumer compile và chạy trên module path |
| 6. Chuẩn bị explicit descriptor | Phân tích dependency, exports, opens, service và split package | Có bản thiết kế module-info.java có thể kiểm thử |
| 7. Phát hành explicit module | Đóng gói module-info.class và giữ module name ổn định | ModuleFinder báo isAutomatic() = false |
| 8. Thu hồi nợ kỹ thuật | Xóa các flag/adapter tạm không còn cần | Test pass, module boundary rõ ràng |

Không cần buộc tất cả dependency chuyển sang explicit module cùng một lần. Tuy nhiên, nên xác định rõ những thành phần nào còn automatic và những thành phần nào đã có descriptor, thay vì coi cả hai là tương đương vì cùng có tên module.

## 18. Bài tập thực hành

1. Tạo một thư viện Java không có **module-info.java**, build thành JAR với class **com.acme.codec.api.Codec**.
2. Đặt JAR trên module path và chạy **jar --describe-module** để quan sát automatic module name được suy ra.
3. Thêm **Automatic-Module-Name: com.acme.codec** vào manifest bằng Maven hoặc Gradle.
4. Build lại rồi kiểm tra tên module bằng **ModuleFinder**; xác nhận **isAutomatic()** là **true**.
5. Tạo module **com.acme.application** có **requires com.acme.codec**, biên dịch và chạy trên module path.
6. Đổi tên file JAR nhưng giữ manifest attribute, xác nhận tên module vẫn là **com.acme.codec**.
7. Bỏ manifest attribute và đổi tên file JAR để quan sát rủi ro tên automatic module tự suy ra.
8. Thử đưa cùng JAR lên classpath, rồi kiểm tra class thuộc unnamed module thay vì named module.
9. Tạo bản explicit **module-info.java** dùng tên **com.acme.codec**, chỉ export package API và so sánh quyền truy cập với automatic module.
10. Nếu thư viện có reflection hoặc service provider, kiểm tra lại opens và provides sau khi chuyển sang explicit.
11. Viết test CI xác nhận module name không đổi qua hai lần build.
12. Thảo luận điều kiện để bỏ trạng thái automatic module hoàn toàn khỏi runtime graph.

## 19. Những điểm cần ghi nhớ

- **Automatic-Module-Name** là manifest attribute nằm trong **META-INF/MANIFEST.MF** của JAR.
- Nó ấn định tên automatic module khi JAR không có module-info.class được đặt trên module path.
- Nó không tạo **module-info.class**, không khai báo **requires**, không giới hạn **exports** và không thay thế module descriptor.
- Automatic module vẫn là named module, nhưng có cơ chế tương thích rộng hơn explicit named module.
- Trên classpath, thuộc tính này không biến JAR thành named module.
- Thuộc tính manifest không tự bảo đảm bytecode Java 8 compatibility; cần build và test riêng.
- Nên giữ tên từ Automatic-Module-Name khi phát hành explicit module-info.java sau này.
- Một lần đổi tên automatic module có thể làm hỏng **requires** của consumer.
- Maven/Gradle cần ghi thuộc tính vào đúng runtime artifact cuối cùng; luôn kiểm tra JAR sau đóng gói.
- Để đạt strong encapsulation, cần explicit descriptor với exports/opens và dependency được thiết kế chủ động.
- Lộ trình tốt có bước chuyển tiếp, tiêu chí hoàn thành, người phụ trách và kiểm tra tự động.

**Automatic-Module-Name là lời hứa về tên, không phải lời hứa rằng thư viện đã modular hóa xong.** Dùng nó để ổn định quan hệ **requires** trong quá trình migration; sau đó chuyển dần sang module-info.class, kiểm soát package API, reflection và service để xây dựng module boundary đúng nghĩa.