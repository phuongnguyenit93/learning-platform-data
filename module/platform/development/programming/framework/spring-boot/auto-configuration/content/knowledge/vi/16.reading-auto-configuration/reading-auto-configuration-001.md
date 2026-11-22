# Tìm lớp tự cấu hình tương ứng với một tính năng và đúng phiên bản đang chạy

## 1. Vì sao phải tìm đúng lớp và đúng phiên bản?

Một tính năng Spring Boot có thể được cung cấp bởi auto-configuration nằm trong chính Spring Boot, một starter bên thứ ba hoặc thư viện nội bộ. Khi cần hiểu tính năng được bật ở đâu, điều kiện nào tạo bean và vì sao hành vi khác tài liệu, cần xác định:

1. **Artifact nào** cung cấp tính năng: starter, module auto-config hay thư viện lõi?
2. **Auto-configuration class nào** chịu trách nhiệm đăng ký bean hoặc cấu hình liên quan?
3. **Class đó thuộc JAR nào** trên runtime classpath?
4. **Phiên bản nào thực sự được resolve và chạy**, thay vì chỉ nhìn version khai báo trong build file?
5. Trong phiên bản đang chạy, class và condition còn giữ nguyên tên/vị trí hay đã được di chuyển, tách hoặc thay thế?

Không nên bắt đầu bằng cách đoán tên class từ tên tính năng. Một tính năng có chữ "web", "cache" hoặc "security" trong tài liệu có thể được chia thành nhiều auto-configuration; starter chỉ kéo dependency vào classpath chứ không nhất thiết chứa class thực hiện cấu hình.

**Nguyên tắc:** xác định runtime dependency/version trước, tìm entry point auto-configuration trong đúng JAR, sau đó đọc source/bytecode và xác minh bằng Condition Evaluation Report hoặc context test.

## 2. Phân biệt starter, auto-configuration và thư viện triển khai

Một tính năng thường được phân thành các vai trò:

| Thành phần | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| Starter artifact | Dependency tiện dụng, tập hợp dependency cần thiết | Ứng dụng đã kéo module nào vào runtime classpath? |
| Auto-configuration artifact | Chứa lớp cấu hình tự động và metadata discovery | Class nào đăng ký bean, condition nào được kiểm tra? |
| Core/runtime library | Chứa API và implementation mà bean sử dụng | Bean tạo ra dùng class nào và hành vi nằm ở đâu? |
| Configuration metadata | Mô tả property để IDE/documentation gợi ý | Có key cấu hình nào, kiểu/default/deprecation ra sao? |
| Spring Boot loader/build plugin | Đóng gói và khởi chạy ứng dụng | Artifact nào thực sự được nạp khi chạy JAR? |

Một starter có thể chỉ có POM gần như rỗng, khai báo dependency sang module khác. Vì vậy, dùng lệnh liệt kê nội dung starter JAR mà không thấy auto-configuration class **không chứng minh tính năng không có auto-configuration**. Phải lần theo dependency đến JAR chứa class.

Tương tự, spring-boot-autoconfigure chứa nhiều auto-configuration của Spring Boot, nhưng một số tính năng được tách thành module riêng hoặc do dự án khác cung cấp. Tên artifact, tên class và tên property không nhất thiết giống nhau.

## 3. Bước 1 — xác định phiên bản Spring Boot thực tế

### 3.1. Maven: xem dependency tree

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Để kiểm tra một module cụ thể và thấy cả các dependency bị loại vì conflict:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot:spring-boot-autoconfigure
~~~

Tìm các dấu hiệu:

- Version được resolve trong dependency graph.
- Dependency bị đổi version bởi dependency management hoặc BOM.
- Một version bị bỏ qua vì conflict (Maven có thể ghi omitted for conflict).
- Starter kéo theo spring-boot-autoconfigure hoặc artifact chuyên biệt nào.

Có thể xem POM hiệu lực:

~~~bash
mvn help:effective-pom
~~~

POM hiệu lực cho biết dependency management, parent và property đã được áp dụng. Tuy nhiên, **effective POM không thay thế dependency tree**: tree cho thấy phiên bản dependency được resolve trong đồ thị thực tế.

Nếu dự án dùng Spring Boot parent hoặc BOM, các module Spring Boot thường được quản lý cùng một release line. Không nên tự override riêng spring-boot-autoconfigure sang version khác spring-boot nếu không có lý do và kiểm thử tương thích.

### 3.2. Gradle: xem runtimeClasspath

Chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để biết dependency nào kéo module vào và vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Trên Windows:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

dependencyInsight hữu ích khi nhiều starter yêu cầu version khác nhau hoặc có rule/platform ép version. Với ứng dụng nhiều project, chạy task trong đúng subproject đang tạo executable; dependency graph của module khác không chứng minh classpath của ứng dụng hiện tại.

### 3.3. Không nhầm version khai báo với version runtime

Ví dụ pom.xml có parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
</parent>
~~~

Đây là version parent được khai báo. Nếu dự án override dependency, dùng BOM khác hoặc đóng gói artifact khác, version runtime cần được xác nhận riêng.

Có thể in version Spring Boot trong lúc ứng dụng chạy:

~~~java
import org.springframework.boot.SpringBootVersion;

System.out.println("Spring Boot version: "
        + SpringBootVersion.getVersion());
~~~

Đặt đoạn này trong main hoặc runner. Với ứng dụng Spring Boot thông thường, SpringBootVersion.getVersion() trả về version của lớp Spring Boot được nạp. Nếu kết quả null trong môi trường đóng gói tùy biến, kiểm tra manifest/JAR và class origin.

Có thể xem version từ command line hoặc build info, nhưng **runtime classpath mới là căn cứ chính** cho class mà JVM thực sự nạp.

## 4. Bước 2 — tìm artifact cung cấp tính năng

Bắt đầu từ tên tính năng trong tài liệu, property hoặc bean đang quan sát. Tìm các dependency liên quan:

~~~bash
mvn dependency:tree -Dverbose
~~~

Hoặc với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm theo các dấu hiệu:

- Starter có tên tính năng.
- Module có hậu tố autoconfigure.
- Module có hậu tố starter.
- Thư viện runtime/API mà bean phụ thuộc.
- Module Spring Boot tích hợp chính thức.

Ví dụ giả định:

~~~text
com.acme:acme-report-starter
  \- com.acme:acme-report-autoconfigure
      \- com.acme:acme-report-core
~~~

Trong ví dụ này, class auto-configuration nhiều khả năng nằm trong acme-report-autoconfigure, còn API/implementation ở acme-report-core. Đây là **cấu trúc minh họa**, không phải tên artifact của một thư viện cụ thể.

Đừng suy ra JAR chỉ từ package name. Hãy kiểm tra artifact thực sự trên runtime classpath và nội dung JAR.

## 5. Bước 3 — tìm entry point auto-configuration trong JAR

### 5.1. Spring Boot 3.x: AutoConfiguration.imports

Với Spring Boot 3.x, cơ chế discovery chuẩn cho auto-configuration là resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Resource chứa tên đầy đủ của các auto-configuration class, mỗi dòng một class. Khi đã biết JAR nghi vấn, kiểm tra nội dung:

~~~bash
jar tf path/to/library-autoconfigure.jar
~~~

Tìm file imports:

~~~bash
jar tf path/to/library-autoconfigure.jar | grep AutoConfiguration.imports
~~~

Đọc nội dung resource trong JAR:

~~~bash
unzip -p path/to/library-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trên Windows PowerShell, nếu không có unzip, có thể dùng jar để liệt kê rồi giải nén JAR ra thư mục tạm:

~~~powershell
jar tf path\to\library-autoconfigure.jar
jar xf path\to\library-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Khi tìm thấy tên class, ghi lại **fully qualified class name**, ví dụ:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Sau đó tìm class tương ứng trong JAR:

~~~bash
jar tf path/to/library-autoconfigure.jar | grep ReportsAutoConfiguration
~~~

Không mặc định rằng mọi dòng trong imports đều tạo bean. File này liệt kê candidate; class có thể tiếp tục dùng ConditionalOnClass, ConditionalOnProperty, ConditionalOnBean hoặc condition khác.

### 5.2. Spring Boot 2.x: spring.factories

Với các phiên bản Spring Boot 2.x, auto-configuration thường được đăng ký qua:

~~~text
META-INF/spring.factories
~~~

Trong resource này, tìm key EnableAutoConfiguration:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Có thể đọc:

~~~bash
unzip -p path/to/library-autoconfigure.jar META-INF/spring.factories
~~~

**Không áp dụng máy móc cách tìm của Boot 3 cho Boot 2 hoặc ngược lại.** Spring Boot 3 chuyển discovery auto-configuration sang AutoConfiguration.imports; một thư viện tương thích nhiều major version có thể phải đóng gói metadata phù hợp cho từng release line theo hướng dẫn của thư viện.

Các file spring.factories vẫn có thể được sử dụng cho những SPI/extension khác trong các phiên bản Boot mới; điều cần phân biệt là key EnableAutoConfiguration cũ không còn là cơ chế đăng ký auto-configuration chuẩn của Boot 3.

### 5.3. Kiểm tra metadata bổ trợ

Một số JAR có thêm:

- META-INF/spring-autoconfigure-metadata.properties: metadata hỗ trợ lọc auto-configuration sớm trong một số phiên bản/cơ chế của Boot.
- META-INF/spring-configuration-metadata.json: metadata về property, kiểu, mô tả, default và deprecation.
- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports: danh sách candidate của Boot 3.x.

Không nhầm configuration metadata với danh sách auto-configuration. spring-configuration-metadata.json giúp tìm **tên property**; nó không phải nguồn chuẩn để biết class nào đăng ký bean.

## 6. Bước 4 — đọc class và condition của đúng version

Sau khi tìm được tên class từ JAR, kiểm tra đúng artifact/version trước khi tra source. Một class có thể đã được đổi package, đổi tên, tách thành nhiều class hoặc xóa ở release mới.

### 6.1. Mở source trong IDE

Trong IntelliJ IDEA:

1. Mở External Libraries hoặc Maven/Gradle dependencies.
2. Chọn đúng artifact và version đã resolve.
3. Tìm class theo fully qualified name từ AutoConfiguration.imports hoặc spring.factories.
4. Mở source attachment nếu IDE đã tải source JAR.
5. Nếu không có source, xem decompiled bytecode và xác minh với artifact thực tế.

Trong Eclipse, mở Maven Dependencies/Gradle Dependencies, tìm JAR đúng version rồi mở class. Có thể attach source JAR để đọc code gốc.

**Không đọc source từ nhánh GitHub main rồi kết luận đó là code đang chạy.** main có thể đã thay đổi sau release, hoặc class đã di chuyển ở version mới. Hãy mở tag/commit tương ứng hoặc source JAR đúng version.

### 6.2. Dùng source JAR hoặc decompiler

Maven có thể tải source artifact:

~~~bash
mvn dependency:sources
~~~

Nếu không có source JAR, có thể dùng decompiler trong IDE hoặc javap để xem signature/annotation cơ bản:

~~~bash
javap -classpath path/to/library-autoconfigure.jar -p com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

javap giúp xác nhận class có tồn tại, method và signature. Nó không trình bày source ở mức dễ đọc như source JAR và không tự giải thích toàn bộ semantics của condition.

Khi đọc class, tập trung vào:

- AutoConfiguration hoặc Configuration.
- ConditionalOnClass và ConditionalOnMissingClass.
- ConditionalOnProperty.
- ConditionalOnBean và ConditionalOnMissingBean.
- ConditionalOnWebApplication.
- Import, ImportAutoConfiguration và nested configuration.
- Các method Bean và kiểu trả về.
- before, after, beforeName, afterName hoặc ordering metadata.
- Các configuration properties được đăng ký qua EnableConfigurationProperties.

Một auto-configuration class có thể chỉ import class khác hoặc đăng ký properties. Bean thực sự có thể nằm trong nested configuration hay method ở class được import. Hãy theo chuỗi tham chiếu cho đến nơi bean được đăng ký.

## 7. Bước 5 — xác minh class thuộc đúng JAR và runtime classpath

Khi nhiều version của cùng một thư viện cùng xuất hiện trong dependency graph, tên class giống nhau chưa đủ. Cần xác định JVM đang nạp class từ đâu.

### 7.1. In nguồn class bằng Java

Đoạn mã sau giúp xem CodeSource của một class:

~~~java
Class<?> type = com.acme.reports.autoconfigure.ReportsAutoConfiguration.class;

System.out.println("Class: " + type.getName());
System.out.println("Origin: "
        + (type.getProtectionDomain().getCodeSource() == null
                ? "unknown"
                : type.getProtectionDomain().getCodeSource().getLocation()));
~~~

Đặt đoạn này trong code chẩn đoán tạm thời của ứng dụng, với class thực tế đã tồn tại trong dependency. Trong executable Spring Boot JAR, nested JAR và classloader có thể làm URL hiển thị khác JAR độc lập; một số môi trường tùy biến có thể không cung cấp CodeSource. Vì vậy hãy kết hợp với dependency tree và runtime classpath, không coi một URL đơn lẻ là bằng chứng duy nhất.

Có thể kiểm tra class resource:

~~~java
String resource =
        "com/acme/reports/autoconfigure/ReportsAutoConfiguration.class";

System.out.println(type.getClassLoader().getResource(resource));
~~~

Kết quả thường cho biết URL resource mà classloader tìm thấy. Nếu có nhiều classloader, cần kiểm tra đúng classloader của class đang được dùng.

### 7.2. Kiểm tra JAR đóng gói

Với Spring Boot executable JAR, dependency thường nằm trong:

~~~text
BOOT-INF/lib/
~~~

Liệt kê:

~~~bash
jar tf target/my-app.jar
~~~

Tìm artifact và version, ví dụ:

~~~text
BOOT-INF/lib/spring-boot-autoconfigure-3.3.5.jar
BOOT-INF/lib/acme-report-autoconfigure-1.4.2.jar
~~~

Các tên trên chỉ là **ví dụ minh họa**. Đối chiếu với JAR thật được đóng gói, vì version runtime có thể khác version bạn tưởng từ build file.

Nếu cần kiểm tra resource bên trong nested JAR, trước tiên giải nén executable JAR ra thư mục tạm, sau đó mở JAR con tương ứng bằng jar tf hoặc unzip -p. Không nhầm resource của ứng dụng với resource trong dependency.

## 8. Bước 6 — xác minh bằng Condition Evaluation Report

Sau khi xác định class và version, bật báo cáo:

~~~bash
java -jar target/my-app.jar --debug
~~~

Tìm tên class trong các nhóm:

- **Positive matches:** các điều kiện đã khớp.
- **Negative matches:** các điều kiện không khớp và lý do.
- **Exclusions:** các auto-configuration bị loại trừ.
- **Unconditional classes:** các cấu hình không cần condition tương ứng.

Nếu class tìm được trong JAR nhưng không xuất hiện trong báo cáo, kiểm tra:

1. Resource discovery có thực sự chứa class đó không?
2. Dependency có nằm trên runtime classpath của đúng ứng dụng không?
3. Auto-configuration có bị exclude không?
4. Class có bị lọc trước khi đánh giá bởi điều kiện hoặc metadata không?
5. Có đang chạy đúng artifact/JAR/version vừa kiểm tra không?

Nếu class xuất hiện nhưng bean method không khớp, đọc condition cụ thể ở method đó. Nếu condition match nhưng bean vẫn không tạo được, đọc stack trace và lỗi khởi tạo.

Với ứng dụng có Actuator, endpoint /actuator/conditions có thể cung cấp thông tin condition qua HTTP khi dependency, exposure và quyền truy cập được cấu hình. Endpoint này là công cụ riêng; --debug không tự cài Actuator hay mở endpoint.

## 9. Ví dụ quy trình tìm auto-configuration theo một tính năng

Giả sử ứng dụng dùng tính năng cache và cần biết class nào thực sự cấu hình cache.

### Bước 1: xác định dependency đã resolve

Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.boot,com.example
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Xác định version Spring Boot và artifact cache liên quan. Đừng giả định chỉ có một JAR: starter có thể kéo module auto-config, API và implementation riêng.

### Bước 2: tìm discovery resource

Với Boot 3.x, mở META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports trong các JAR liên quan. Tìm candidate có tên liên quan đến cache.

Với Boot 2.x, kiểm tra key EnableAutoConfiguration trong META-INF/spring.factories của artifact đúng version.

### Bước 3: mở class đúng version

Dùng source JAR/tag tương ứng để đọc class được khai báo trong resource. Tìm các annotation condition và method Bean. Nếu class chỉ import cấu hình con, đi tiếp đến class con.

### Bước 4: bật báo cáo khi chạy

~~~bash
java -jar target/my-app.jar --debug
~~~

Tìm tên auto-configuration trong Positive/Negative matches. Đối chiếu điều kiện với property, classpath và bean hiện tại.

### Bước 5: xác nhận hành vi

Dùng test cô lập hoặc integration test để kiểm tra bean có/không có khi thay đổi property và prerequisite. Đừng dừng ở việc tìm thấy tên class: cần chứng minh class đó thuộc đúng version và condition thực sự khớp trong runtime.

## 10. Các lỗi thường gặp khi truy tìm class

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tìm starter JAR nhưng không thấy auto-configuration class | Starter chỉ khai báo dependency | Theo dependency tree sang artifact auto-config |
| Tài liệu nói có class nhưng JAR hiện tại không có | Tài liệu thuộc version khác hoặc class đã đổi tên/package | Kiểm tra version runtime và source JAR/tag tương ứng |
| AutoConfiguration.imports không có class mong đợi | Đang xem sai JAR hoặc sai major version | Tìm đúng artifact; với Boot 2 kiểm tra spring.factories |
| Class có trong JAR nhưng không xuất hiện trong report | Không được discovery, bị exclude hoặc bị lọc | Kiểm tra resource, classpath, exclusion và điều kiện |
| Class xuất hiện trong report nhưng bean không có | Condition ở bean method không khớp | Đọc Negative match tại đúng method |
| Dependency tree cho thấy hai version | Conflict hoặc override qua BOM/platform | Dùng dependencyInsight/tree verbose, căn chỉnh version |
| Source trên GitHub khác decompiler trong JAR | Đang xem nhánh/tag không khớp release | Dùng source JAR hoặc tag đúng version |
| Condition match nhưng startup thất bại | Lỗi khởi tạo bean sau khi condition đã chạy | Đọc stack trace, constructor và factory method |
| Đổi version dependency mà class vẫn như cũ | JAR runtime chưa được cập nhật hoặc đang chạy artifact cũ | Clean/rebuild/redeploy đúng ứng dụng, xác nhận executable JAR |
| Chỉ đọc spring-configuration-metadata.json để tìm class | Metadata đó mô tả properties, không phải danh sách auto-config | Tìm AutoConfiguration.imports hoặc spring.factories theo version |

## 11. Checklist trước khi kết luận

Khi ghi lại kết quả điều tra một tính năng, lưu đủ các bằng chứng:

- Tên ứng dụng/module đang chạy.
- Phiên bản Spring Boot thực tế (runtime).
- Artifact và version chứa auto-configuration class.
- Discovery resource và dòng khai báo class.
- Fully qualified class name và các class cấu hình con được import.
- Các condition ở class và bean method.
- Kết quả Positive/Negative match khi chạy với cấu hình thực tế.
- Bean cuối cùng có/không có và test xác nhận.

Có thể ghi kết quả theo mẫu:

~~~text
Feature: <tên tính năng>
Spring Boot runtime: <version>
Provider artifact: <group:artifact:version>
Discovery: <AutoConfiguration.imports hoặc spring.factories>
Auto-configuration class: <fully-qualified-class-name>
Bean method: <ConfigurationClass#beanMethod>
Conditions: <các condition liên quan>
Runtime report: <Positive/Negative match và lý do>
Verification: <test hoặc quan sát bean trong context>
~~~

Không ghi một class chỉ vì tên có vẻ phù hợp. Phải xác minh class thuộc artifact đúng version và được discovery/condition xử lý trong runtime thực tế.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể chỉ mở starter JAR để tìm class auto-configuration?  
**Đáp án:** Starter thường chỉ kéo các artifact khác vào dependency graph; class có thể nằm trong module autoconfigure riêng.

**Câu 2.** Boot 3.x thường công bố auto-configuration qua resource nào?  
**Đáp án:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports. Boot 2.x thường dùng key EnableAutoConfiguration trong META-INF/spring.factories.

**Câu 3.** Vì sao phải xác nhận version runtime thay vì chỉ nhìn version trong pom.xml?  
**Đáp án:** Dependency management, BOM, conflict resolution và override có thể khiến version được resolve khác giả định ban đầu.

**Câu 4.** Class có trong JAR nhưng không có bean thì bước tiếp theo là gì?  
**Đáp án:** Xác nhận class được discovery, kiểm tra exclusion và đọc Condition Evaluation Report ở cấp bean method; nếu condition match, đọc lỗi khởi tạo.

**Câu 5.** Có thể dùng CodeSource để làm gì?  
**Đáp án:** Xem vị trí class được nạp từ đâu trong runtime, rồi đối chiếu với dependency tree và JAR thực tế. Trong executable JAR tùy biến, URL có thể không đơn giản hoặc không có.

**Ghi nhớ:** Muốn tìm đúng auto-configuration của một tính năng, hãy đi theo chuỗi **runtime version → dependency/artifact → discovery resource → class và condition → Condition Evaluation Report → kiểm chứng bean**. Không dựa vào tên class đoán mò, source của nhánh main hoặc version khai báo đơn lẻ.
