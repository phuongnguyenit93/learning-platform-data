# Đối chiếu dependency thực tế bằng công cụ của Maven hoặc Gradle

Trong một dự án Java, danh sách dependency được khai báo trong file build chưa phản ánh đầy đủ những thư viện thực sự có mặt trên classpath khi biên dịch, kiểm thử hoặc chạy ứng dụng. Một dependency có thể được kéo vào gián tiếp qua framework; nhiều thư viện có thể yêu cầu cùng một module nhưng chỉ một phiên bản được chọn; profile, variant, constraint và cấu hình build có thể làm kết quả khác nhau giữa các môi trường.

Khi migration Java, cần biết **dependency nào thực sự được resolve, phiên bản nào được chọn, vì sao phiên bản đó được chọn và cấu hình nào sử dụng nó**. Maven và Gradle đều cung cấp các báo cáo để trả lời những câu hỏi này. Bài học hướng dẫn cách dùng các công cụ đó để kiểm kê dependency thực tế, truy nguyên dependency bắc cầu, phân tích xung đột phiên bản và xác minh mức tương thích với phiên bản Java mục tiêu.

Nội dung thuộc chủ đề **Java Advance Compatibility Migration**, chương **Công cụ phân tích**. Trọng tâm là phân tích graph đã resolve bằng Maven hoặc Gradle; việc sửa mã nguồn hay thay dependency cần được thực hiện sau khi đã hiểu rõ kết quả.

## 1. Vì sao phải đối chiếu dependency đã resolve?

Giả sử file build khai báo trực tiếp:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.x")
}
~~~

Khai báo này chỉ cho biết ứng dụng yêu cầu một starter. Starter lại phụ thuộc vào Spring MVC, Spring Core, Jackson, logging và nhiều thư viện khác. Các dependency đó tiếp tục có dependency riêng.

Graph thực tế có thể được hình dung như sau:

~~~text
Ứng dụng
  |
  +-- spring-boot-starter-web
        |
        +-- spring-webmvc
        |     |
        |     +-- spring-web
        |     +-- spring-core
        |
        +-- spring-boot-starter-json
        |     |
        |     +-- jackson-databind
        |     |     +-- jackson-core
        |     |     +-- jackson-annotations
        |     +-- jackson-datatype-*
        |
        +-- spring-boot-starter-tomcat
              |
              +-- tomcat-embed-core
              +-- tomcat-embed-websocket
~~~

Đây là sơ đồ minh họa quan hệ dependency, không phải graph cố định của mọi phiên bản Spring Boot. Phiên bản thực tế phụ thuộc vào BOM, plugin, cấu hình và những dependency khác của dự án.

Một thư viện có thể được đưa vào graph từ nhiều nhánh. Ví dụ:

~~~text
Ứng dụng
  |
  +-- thư viện A
  |     +-- commons-io:2.11
  |
  +-- thư viện B
        +-- commons-io:2.15
~~~

Dự án không nhất thiết đóng gói cả hai phiên bản. Công cụ build áp dụng quy tắc giải quyết xung đột để chọn một phiên bản cho module tương ứng trong một cấu hình cụ thể.

Điều này tạo ra khác biệt giữa các khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Declared dependency | Dependency được khai báo trực tiếp trong file build hoặc được kế thừa từ cấu hình cha |
| Transitive dependency | Dependency được một dependency khác yêu cầu |
| Resolved dependency | Dependency đã được hệ thống build chọn sau khi áp dụng quy tắc và constraint |
| Selected version | Phiên bản cuối cùng được chọn cho một module trong graph |
| Configuration / scope | Tập dependency phục vụ một mục đích như compile, runtime hoặc test |
| Artifact | Tệp JAR, POM hoặc thành phần được tải về và sử dụng |
| Dependency constraint | Quy tắc giới hạn, ưu tiên hoặc yêu cầu phiên bản |
| Exclusion | Quy tắc loại một dependency bắc cầu khỏi nhánh hoặc graph theo cấu hình |

Khi kiểm tra migration, câu hỏi quan trọng không chỉ là “POM/build.gradle khai báo thư viện nào?” mà là “runtime của ứng dụng thực sự nhận được những artifact nào?”.

## 2. Phân biệt dependency graph theo từng classpath

Một dự án Java thường có nhiều classpath. Không nên xem một báo cáo dependency duy nhất là toàn bộ dependency của dự án.

### 2.1. Các classpath thường cần kiểm tra

| Classpath | Mục đích | Rủi ro khi migration |
|---|---|---|
| Compile classpath | Dependency cần để biên dịch mã nguồn chính | API hoặc annotation không tương thích với compiler/release |
| Runtime classpath | Dependency cần khi chạy ứng dụng | Lỗi class loading, API hoặc bytecode không tương thích |
| Test compile classpath | Dependency để biên dịch test | Framework test hoặc mock library chưa hỗ trợ JDK mới |
| Test runtime classpath | Dependency khi chạy test | Engine, agent hoặc test runtime gặp lỗi |
| Annotation processor | Công cụ xử lý annotation và sinh mã | Processor cũ có thể không chạy với compiler mới |
| Buildscript/plugin classpath | Thư viện và plugin phục vụ build | Build tool hoặc plugin không tương thích với JDK chạy build |
| Custom configuration | Dependency của task hoặc capability riêng | Có thể bị bỏ sót nếu chỉ xem compile/runtime mặc định |

Ví dụ, một dependency có thể chỉ xuất hiện trong test classpath và không được đóng gói vào ứng dụng. Ngược lại, một thư viện có thể chỉ có ở runtime do được khai báo bằng scope/configuration runtime.

Với ứng dụng Spring, việc chỉ xem compile classpath có thể bỏ qua driver, logging provider hoặc thư viện được nạp khi chạy. Với một thư viện dùng chung, test runtime có thể chứa các dependency không thuộc public runtime của artifact phát hành.

### 2.2. Dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là dependency mà module chủ động khai báo. Dependency bắc cầu được kéo vào bởi một dependency khác.

Ví dụ:

~~~text
app
  +-- library-a:1.0
  |     +-- common-utils:2.0
  |
  +-- library-b:3.0
        +-- common-utils:2.5
~~~

Ứng dụng có thể chỉ khai báo library-a và library-b, nhưng common-utils vẫn có mặt trong graph. Khi nâng library-b, phiên bản common-utils được chọn có thể thay đổi dù file build không sửa dòng khai báo common-utils.

Điều này đặc biệt quan trọng trong migration Java: một dependency bắc cầu có thể yêu cầu runtime mới hơn, thay đổi API hoặc kéo theo một thư viện khác không tương thích với nền tảng hiện tại.

### 2.3. Cùng một module có thể có graph khác nhau

Graph có thể khác theo:

- Module được build.
- Maven profile đang bật.
- Gradle configuration được resolve.
- Platform hoặc BOM được áp dụng.
- Hệ điều hành và kiến trúc CPU.
- Attribute của variant.
- Phiên bản JDK hoặc toolchain.
- Property, environment variable hoặc init script.
- Dependency lock và quy tắc resolution.

Vì vậy, khi chia sẻ báo cáo, cần ghi rõ module, configuration/scope, profile và lệnh đã chạy. Báo cáo từ local không nhất thiết giống CI hoặc production nếu đầu vào resolution khác nhau.

## 3. Đối chiếu dependency bằng Maven

Maven có plugin Dependency để xem cây dependency, phân tích dependency được sử dụng và kiểm tra các artifact đã resolve. Plugin Help giúp xem POM hiệu lực sau khi kế thừa và áp dụng profile.

### 3.1. Xem cây dependency bằng dependency:tree

Chạy từ thư mục module có file pom.xml:

~~~bash
./mvnw dependency:tree
~~~

Nếu dự án không có Maven Wrapper, có thể dùng lệnh mvn theo phiên bản Maven đã cài.

Trên Windows, lệnh tương ứng thường là:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Kết quả minh họa:

~~~text
com.example:orders-service:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:3.x:compile
|  +- org.springframework:spring-webmvc:jar:6.x:compile
|  |  +- org.springframework:spring-web:jar:6.x:compile
|  |  \- org.springframework:spring-context:jar:6.x:compile
|  \- com.fasterxml.jackson.core:jackson-databind:jar:2.x:compile
|     +- com.fasterxml.jackson.core:jackson-annotations:jar:2.x:compile
|     \- com.fasterxml.jackson.core:jackson-core:jar:2.x:compile
\- org.postgresql:postgresql:jar:42.x:runtime
~~~

Các con số x chỉ là placeholder để minh họa. Hãy đọc version cụ thể từ báo cáo của dự án đang phân tích.

Một dòng thường thể hiện:

~~~text
groupId:artifactId:type:version:scope
~~~

Ví dụ:

~~~text
org.postgresql:postgresql:jar:42.x:runtime
~~~

Có nghĩa artifact thuộc group org.postgresql, artifact postgresql, đóng gói dạng JAR, có phiên bản được resolve và scope runtime trong graph Maven.

Các ký hiệu cây:

- +- biểu thị một nhánh còn dependency tiếp theo.
- \- biểu thị nhánh cuối ở cấp hiện tại.
- | giúp thể hiện nhánh cha đang tiếp tục.
- Dòng thụt vào sâu hơn là dependency bắc cầu của dòng phía trên.

### 3.2. Hiển thị các nhánh bị loại do xung đột

Mặc định, cây có thể tập trung vào các dependency được chọn. Dùng -Dverbose để hiển thị thêm thông tin về các node bị loại hoặc bị conflict:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Một kết quả minh họa:

~~~text
com.example:orders-service:jar:1.0.0
+- com.example:client-a:jar:1.0:compile
|  \- com.example:common-utils:jar:2.0:compile
\- com.example:client-b:jar:1.0:compile
   \- (com.example:common-utils:jar:2.5:compile
       - omitted for conflict with 2.0)
~~~

Trong ví dụ giả định này, Maven chọn common-utils:2.0 vì quy tắc mediation của Maven. Dependency 2.5 được hiển thị là bị loại do conflict.

Đừng đọc omitted for conflict như bằng chứng phiên bản bị loại không tồn tại trong repository. Nó chỉ cho biết node đó không phải phiên bản được chọn trong graph hiện tại.

### 3.3. Lọc dependency cần điều tra

Khi graph lớn, có thể lọc theo groupId hoặc artifactId:

~~~bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Có thể lọc thêm theo scope:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Hoặc kết hợp để tập trung vào một nhóm thư viện trong runtime graph:

~~~bash
./mvnw dependency:tree -Dverbose -Dscope=runtime -Dincludes=com.fasterxml.jackson.core:*
~~~

Các filter giúp giảm nhiễu khi điều tra một dependency cụ thể. Nếu cần hiểu đường đi từ dependency gốc đến thư viện đang được chọn, hãy chạy lại cây đầy đủ hoặc xem cả những nhánh liên quan; một kết quả lọc có thể làm mất ngữ cảnh của các nhánh khác.

### 3.4. Xem POM hiệu lực và dependencyManagement

POM trong repository chưa chắc là POM cuối cùng Maven dùng. POM có thể kế thừa từ parent, import BOM, nhận property và bật profile.

Tạo POM hiệu lực:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Có thể dùng verbose để bổ sung thông tin nguồn gốc cấu hình nếu phiên bản Maven Help Plugin hỗ trợ:

~~~bash
./mvnw help:effective-pom -Dverbose
~~~

POM hiệu lực giúp trả lời:

- Dependency nào được kế thừa từ parent?
- Version property nào đang được thay thế?
- BOM nào được import?
- DependencyManagement đang quản lý phiên bản nào?
- Profile nào bổ sung hoặc thay đổi dependency?
- Plugin nào được cấu hình ở cấp parent?

Cần phân biệt dependencyManagement với dependencies:

- dependencies đưa dependency vào graph của project.
- dependencyManagement quản lý version, scope hoặc cấu hình mặc định khi dependency được khai báo; tự nó không nhất thiết thêm dependency vào classpath.
- BOM được import trong dependencyManagement cung cấp tập version được quản lý cho các dependency liên quan.

Nếu dependency:tree cho thấy phiên bản khác với version nhìn thấy trong một file POM, hãy xem POM hiệu lực và graph đã resolve để tìm nguyên nhân.

### 3.5. Kiểm tra profile đang hoạt động

Maven profile có thể được kích hoạt theo property, JDK, hệ điều hành, file tồn tại hoặc cấu hình settings.

Xem profile đang hoạt động:

~~~bash
./mvnw help:active-profiles
~~~

Nếu dự án cần profile cụ thể, chạy báo cáo với cùng điều kiện profile:

~~~bash
./mvnw -Pproduction dependency:tree
~~~

Một báo cáo dependency từ profile mặc định không chứng minh graph production giống hệt. Khi đối chiếu CI, cần dùng cùng tham số -P, -D và settings phù hợp.

### 3.6. Phân tích dependency được khai báo nhưng có vẻ không dùng

Maven Dependency Plugin cung cấp goal dependency:analyze:

~~~bash
./mvnw dependency:analyze
~~~

Goal này phân tích bytecode đã biên dịch để tìm một số trường hợp như:

- Dependency được khai báo nhưng không thấy sử dụng.
- Class được sử dụng nhưng dependency không được khai báo trực tiếp.
- Dependency được sử dụng gián tiếp thông qua class khác.

Kết quả có thể chỉ ra:

~~~text
Used undeclared dependencies found
Unused declared dependencies found
~~~

Đây là tín hiệu để điều tra, không phải lệnh tự động xóa dependency. Phân tích tĩnh có thể bỏ sót các trường hợp:

- Reflection và class name được tạo động.
- ServiceLoader và SPI.
- Annotation được xử lý ở runtime hoặc compile time.
- Framework tự động scan classpath.
- Resource được tải theo tên.
- Dependency chỉ được dùng trong một profile hoặc đường chạy đặc biệt.
- Public API của thư viện cần dependency để consumer biên dịch.

Trước khi xóa một dependency, cần kiểm tra cách ứng dụng sử dụng nó trong runtime, test và môi trường triển khai.

### 3.7. Kiểm tra scope Maven

Maven scope quyết định dependency có mặt trong những classpath nào và cách truyền dependency cho consumer.

| Scope | Compile | Test | Runtime ứng dụng | Truyền bắc cầu cho consumer |
|---|---:|---:|---:|---:|
| compile | Có | Có | Có | Có |
| provided | Có | Có | Không theo runtime classpath thông thường | Không |
| runtime | Không dùng để compile mã chính | Có | Có | Có |
| test | Không | Có | Không | Không |
| system | Có | Có | Không nên dựa vào như dependency thông thường | Không |
| import | Dùng trong dependencyManagement cho BOM | — | — | Quản lý version, không phải artifact runtime |

Scope provided thường dùng khi môi trường triển khai cung cấp API hoặc implementation tương ứng. Nếu đổi runtime hoặc application server, cần xác nhận nền tảng mới thực sự cung cấp dependency đó.

Scope runtime có thể không xuất hiện trên compile classpath nhưng vẫn cần thiết khi chạy. Nếu chỉ kiểm tra compile graph, nhóm có thể bỏ sót lỗi runtime.

### 3.8. Quy tắc chọn phiên bản trong Maven

Maven áp dụng dependency mediation để chọn một phiên bản khi cùng tọa độ dependency xuất hiện nhiều lần. Quy tắc phổ biến là **nearest definition**: dependency được tìm thấy ở độ sâu gần project nhất thường được ưu tiên; nếu ở cùng độ sâu, thứ tự khai báo có thể ảnh hưởng kết quả.

Ví dụ:

~~~text
app
  +-- library-a
  |     +-- shared-api:1.4
  |
  +-- library-b
        +-- shared-api:2.0
~~~

Nếu hai phiên bản nằm ở cùng độ sâu, thứ tự nhánh trong POM có thể ảnh hưởng phiên bản được chọn. Nếu một phiên bản được khai báo trực tiếp trong project, nó có thể được ưu tiên hơn phiên bản bắc cầu ở sâu hơn.

Đừng cho rằng Maven luôn chọn version lớn nhất. Khi cần kiểm soát phiên bản, có thể dùng dependencyManagement hoặc khai báo dependency trực tiếp, nhưng phải kiểm tra binary/API compatibility của phiên bản được ép chọn.

## 4. Đối chiếu dependency bằng Gradle

Gradle cung cấp task dependencies để xem cây dependency và dependencyInsight để truy nguyên lý do một phiên bản được chọn. Các task này làm việc theo configuration, vì vậy phải chỉ định đúng module và classpath cần kiểm tra.

### 4.1. Xem cây dependency

Từ thư mục gốc của dự án:

~~~bash
./gradlew dependencies
~~~

Nếu dự án có nhiều module, chỉ định module:

~~~bash
./gradlew :orders-service:dependencies
~~~

Để xem runtime classpath:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

Để xem compile classpath:

~~~bash
./gradlew :orders-service:dependencies --configuration compileClasspath
~~~

Trên Windows, sử dụng wrapper tương ứng:

~~~powershell
.\gradlew.bat :orders-service:dependencies --configuration runtimeClasspath
~~~

Kết quả minh họa:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- org.springframework.boot:spring-boot-starter-web:3.x
|    +--- org.springframework:spring-webmvc:6.x
|    |    +--- org.springframework:spring-web:6.x
|    |    \--- org.springframework:spring-context:6.x
|    \--- org.springframework.boot:spring-boot-starter-json:3.x
|         \--- com.fasterxml.jackson.core:jackson-databind:2.x
|              +--- com.fasterxml.jackson.core:jackson-annotations:2.x
|              \--- com.fasterxml.jackson.core:jackson-core:2.x
\--- org.postgresql:postgresql:42.x
~~~

Tên configuration có thể khác giữa dự án Java application, Android, Kotlin, plugin framework hoặc cấu hình tự định nghĩa. Nếu runtimeClasspath không tồn tại, hãy xem các configuration có sẵn trong project và chọn đúng configuration có thể resolve.

### 4.2. Xem các configuration quan trọng

Một số configuration thường gặp trong plugin Java:

~~~bash
./gradlew :orders-service:dependencies --configuration compileClasspath
./gradlew :orders-service:dependencies --configuration runtimeClasspath
./gradlew :orders-service:dependencies --configuration testCompileClasspath
./gradlew :orders-service:dependencies --configuration testRuntimeClasspath
./gradlew :orders-service:dependencies --configuration annotationProcessor
~~~

Mục đích:

- compileClasspath: thư viện cần cho compile mã chính.
- runtimeClasspath: thư viện cần khi chạy ứng dụng.
- testCompileClasspath: thư viện cần để biên dịch test.
- testRuntimeClasspath: thư viện cần để chạy test.
- annotationProcessor: processor dùng trong compile.

Không phải project nào cũng có đủ những configuration này. Các plugin khác có thể tạo configuration riêng như integration test, code generation, migration hoặc native image.

### 4.3. Truy nguyên một dependency bằng dependencyInsight

Khi thấy dependency có phiên bản bất ngờ, dùng:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Có thể tìm theo tọa độ cụ thể:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency com.fasterxml.jackson.core:jackson-databind --configuration runtimeClasspath
~~~

Báo cáo giúp trả lời:

- Dependency được yêu cầu từ những nhánh nào?
- Phiên bản nào được yêu cầu trực tiếp hoặc gián tiếp?
- Phiên bản nào cuối cùng được chọn?
- Vì sao Gradle chọn phiên bản đó?
- Có constraint, platform hoặc resolution rule nào tác động không?

Một kết quả minh họa có thể chứa:

~~~text
com.fasterxml.jackson.core:jackson-databind:2.x
  Selection reasons:
    - By conflict resolution: between versions 2.a and 2.b
    - By constraint
~~~

Các dòng Selection reasons rất quan trọng. Chúng giúp phân biệt phiên bản được chọn do conflict resolution, constraint, rule hoặc một dependency khác trong graph.

### 4.4. Đọc các ký hiệu trong Gradle report

Trong cây dependency, Gradle có thể hiển thị:

| Ký hiệu hoặc thông tin | Ý nghĩa thường gặp |
|---|---|
| +--- | Một nhánh dependency |
| \--- | Nhánh cuối tại cấp hiện tại |
| (*) | Nhánh đã được hiển thị ở nơi khác, không mở rộng lặp lại |
| -> | Phiên bản được yêu cầu đã được thay bằng phiên bản được chọn |
| FAILED | Dependency hoặc configuration không resolve thành công |
| Selection reasons | Các lý do Gradle chọn component/version |

Ví dụ:

~~~text
+--- com.example:client-a:1.0
|    \--- com.example:shared-api:1.4
\--- com.example:client-b:1.0
     \--- com.example:shared-api:2.0 -> 2.3
~~~

Điều này cho biết một nhánh yêu cầu shared-api:2.0, nhưng phiên bản được chọn trong graph là 2.3. Hãy dùng dependencyInsight để tìm các nhánh, constraint hoặc rule khiến kết quả thay đổi.

### 4.5. Xem dependency của buildscript

Gradle build có dependency phục vụ chính quá trình build, ví dụ plugin hoặc thư viện được khai báo trong buildscript.

Có thể xem classpath buildscript bằng:

~~~bash
./gradlew :orders-service:buildEnvironment
~~~

Báo cáo này hữu ích khi plugin hoặc thư viện buildscript xung đột. Tuy nhiên, không nên coi nó là danh sách duy nhất của mọi plugin được resolve qua Plugins DSL. Plugin DSL còn liên quan đến pluginManagement trong settings, plugin marker và cấu hình resolution khác. Khi điều tra plugin, cần đọc thêm settings.gradle/settings.gradle.kts, khai báo plugins, version catalog và cấu hình init script nếu có.

Đây là một ranh giới quan trọng trong migration: ứng dụng có thể chạy trên JDK mới nhưng Gradle hoặc plugin không thể khởi động trên JDK đó.

## 5. Hiểu quy tắc resolution của Gradle

Gradle giải quyết dependency theo component, version, constraint, variant và attribute. Không phải lúc nào kết quả cũng chỉ là chọn version lớn nhất.

### 5.1. Conflict resolution

Với các module cùng tọa độ, Gradle mặc định thường chọn phiên bản cao hơn khi có conflict version thông thường. Tuy nhiên, constraints, platform, strict version, resolution rule và các cơ chế khác có thể thay đổi kết quả.

Ví dụ:

~~~text
app
  +-- library-a
  |     +-- shared-api:1.4
  |
  +-- library-b
        +-- shared-api:2.0

Resolved:
  shared-api:2.0
~~~

Kết quả thực tế cần được xác nhận bằng dependencyInsight thay vì suy luận từ sơ đồ.

### 5.2. Constraints và version catalog

Version catalog cung cấp alias và version để quản lý khai báo tập trung. Ví dụ:

~~~toml
[versions]
jackson = "2.x"

[libraries]
jackson-databind = {
    module = "com.fasterxml.jackson.core:jackson-databind",
    version.ref = "jackson"
}
~~~

Catalog giúp giảm khai báo lặp nhưng không phải lúc nào cũng là nơi quyết định phiên bản cuối cùng. Dependency có thể bị ảnh hưởng bởi platform, constraint hoặc rule ở nơi khác.

Gradle có các loại constraint và chỉ thị version như:

- strictly: giới hạn chặt phạm vi version được phép.
- prefer: ưu tiên một version nếu không có ràng buộc mạnh hơn.
- require: yêu cầu version hoặc khoảng version.
- reject: loại một số version.
- because: ghi lý do cho constraint.

Khi dependencyInsight hiển thị By constraint, hãy tìm constraint trong build script, platform, version catalog hoặc plugin quản lý dependency.

### 5.3. Platform và BOM

Một platform có thể quản lý phiên bản cho nhóm thư viện liên quan. Ví dụ:

~~~groovy
dependencies {
    implementation(platform("com.example:example-bom:1.0"))
    implementation("com.example:library-a")
    implementation("com.example:library-b")
}
~~~

BOM/Platform giúp các module trong cùng hệ sinh thái sử dụng bộ version đã được kiểm thử cùng nhau. Khi nâng framework, thường nên nâng platform hoặc BOM theo hướng dẫn của nhà cung cấp thay vì ép từng dependency con lên phiên bản mới nhất một cách độc lập.

Gradle phân biệt platform() và enforcedPlatform():

- platform() nhập các dependency constraints từ platform.
- enforcedPlatform() áp dụng các version trong platform theo cách cưỡng chế mạnh hơn đối với dependency liên quan.

Dùng enforced platform có thể ảnh hưởng đến consumer của thư viện nếu ràng buộc bị truyền tiếp. Chỉ sử dụng khi có chủ đích và hiểu tác động đến graph.

### 5.4. Variant selection và attributes

Gradle không chỉ chọn version mà còn chọn variant của component dựa trên attributes. Ví dụ:

- Usage: compile hay runtime.
- Category: library, platform hoặc documentation.
- Target JVM version.
- Operating system hoặc architecture trong các plugin hỗ trợ native.
- Các attribute do plugin tự định nghĩa.

Một module có thể cung cấp nhiều variant. Gradle chọn variant phù hợp với nhu cầu của consumer.

Khi migration Java, attribute org.gradle.jvm.version có thể tham gia chọn variant theo mức JVM. Nếu producer chỉ cung cấp variant yêu cầu JVM mới hơn consumer, resolution có thể thất bại với thông báo không tìm được variant phù hợp.

Khi gặp lỗi variant, đừng chỉ kiểm tra version string. Hãy xem toàn bộ thông báo attribute và yêu cầu của consumer/producer.

### 5.5. Exclusions và force

Gradle cho phép loại dependency bắc cầu hoặc ép version. Ví dụ:

~~~groovy
dependencies {
    implementation("com.example:library-a:1.0") {
        exclude group: "com.example", module: "legacy-api"
    }
}
~~~

Hoặc:

~~~groovy
configurations.configureEach {
    resolutionStrategy.force("com.example:shared-api:2.3")
}
~~~

Các cách này có thể giải quyết conflict trước mắt, nhưng cũng có thể tạo graph không tương thích với dependency yêu cầu phiên bản khác. Nếu ép version, phải xác minh binary/API compatibility và chạy test trên các luồng sử dụng dependency đó.

Exclusion có thể làm mất một thư viện mà framework tải động hoặc service loader cần. Chỉ loại dependency sau khi hiểu vì sao nó được đưa vào graph và cách ứng dụng sử dụng.

## 6. Đối chiếu kết quả Maven và Gradle

Không nên kỳ vọng hai công cụ luôn in ra graph có hình thức giống nhau. Maven và Gradle có mô hình resolution, scope/configuration và variant khác nhau.

| Nội dung cần đối chiếu | Maven | Gradle |
|---|---|---|
| Xem graph | dependency:tree | dependencies |
| Truy nguyên một dependency | Lọc dependency:tree, xem nhánh verbose | dependencyInsight |
| Xem cấu hình hiệu lực | help:effective-pom | Xem build script, convention plugin, catalog, platform và attributes |
| Xem profile/cấu hình đang bật | help:active-profiles | Kiểm tra task/configuration, property và plugin logic |
| Dependency build | Plugin/dependency trong POM và build extensions | buildEnvironment, plugin DSL và settings |
| Phân tích khai báo so với sử dụng | dependency:analyze | Plugin phân tích riêng hoặc kiểm tra bytecode/tooling |
| Khóa phiên bản | dependencyManagement, phiên bản cụ thể và quy trình kiểm soát artifact | Dependency locking |
| Xác minh artifact | Repository, checksum/signature và plugin hỗ trợ | Dependency verification |

Khi một module được build bằng cả Maven và Gradle, hai graph có thể khác do:

- Một bên khai báo thiếu dependency.
- Scope Maven và configuration Gradle được ánh xạ khác nhau.
- BOM/platform hoặc version catalog không đồng bộ.
- Một bên có exclusion hoặc force.
- Profile Maven và property Gradle khác nhau.
- Variant metadata được Gradle sử dụng nhưng Maven không có cùng cơ chế lựa chọn.
- Repository hoặc thời điểm resolve khác nhau.
- Một bên dùng dependency lock trong khi bên kia resolve theo phiên bản động.

Cần so sánh theo cùng mục tiêu: compile với compile, runtime với runtime, test với test. So sánh Maven runtime graph với Gradle compileClasspath sẽ dẫn đến kết luận sai.

## 7. Từ dependency graph đến khả năng tương thích Java

Dependency report cho biết module và version đã resolve, nhưng thường không tự trả lời đầy đủ dependency đó hỗ trợ Java tối thiểu từ phiên bản nào. Để đánh giá migration, cần kết hợp nhiều nguồn bằng chứng.

### 7.1. Xác định dependency nào ảnh hưởng đến runtime

Bắt đầu với runtime classpath của ứng dụng hoặc module có thể triển khai. Phân loại:

- Dependency trực tiếp.
- Dependency bắc cầu.
- Dependency chỉ dùng khi test.
- Dependency chỉ phục vụ build.
- Dependency được cung cấp bởi container/application server.
- Dependency tải động hoặc được nạp theo cấu hình.

Không phải mọi dependency trong build đều được đóng gói vào artifact. Cần hiểu cách đóng gói và classloader của ứng dụng.

Ví dụ, một ứng dụng WAR có thể đánh dấu thư viện là provided vì application server cung cấp. Một ứng dụng fat JAR có thể đóng gói phần lớn runtime dependencies. Hai kiểu triển khai cần kiểm tra khác nhau.

### 7.2. Kiểm tra metadata và tài liệu của artifact

Với dependency quan trọng, kiểm tra:

- Tài liệu yêu cầu JDK tối thiểu.
- Release notes và compatibility matrix.
- Metadata Maven POM hoặc Gradle Module Metadata.
- Phiên bản framework mà thư viện hỗ trợ.
- Yêu cầu hệ điều hành, native library hoặc agent.
- Các issue đã biết liên quan đến JDK mục tiêu.

Trong Gradle, metadata có thể chứa variant và thuộc tính JVM target. Trong Maven, POM có thể cung cấp dependency metadata và thông tin dự án, nhưng không phải mọi thư viện đều khai báo rõ Java baseline.

Nếu tài liệu không nêu rõ, cần kiểm tra artifact thực tế và chạy thử trong môi trường mục tiêu.

### 7.3. Kiểm tra bytecode của JAR

Có thể dùng javap để xem class file:

~~~bash
javap -verbose -classpath library.jar com.example.SomeClass
~~~

Tìm major version để xác định class file version của class đó. Một số mốc:

| Java | Major class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu một class có major version cao hơn khả năng của runtime đích, runtime cũ không thể nạp class đó bình thường.

Tuy nhiên, kiểm tra một class không đủ chứng minh toàn bộ JAR tương thích. JAR có thể chứa class được biên dịch ở các release khác nhau, đặc biệt là Multi-Release JAR. Cần kiểm tra nhiều class đại diện hoặc quét toàn bộ artifact.

### 7.4. Dùng jdeps để phân tích phụ thuộc và API nội bộ

JDK cung cấp jdeps để phân tích dependency ở mức class/package và phát hiện việc sử dụng một số API nội bộ:

~~~bash
jdeps --jdk-internals library.jar
~~~

Có thể chỉ định release mục tiêu khi phân tích Multi-Release JAR:

~~~bash
jdeps --multi-release 21 --jdk-internals library.jar
~~~

jdeps giúp phát hiện tham chiếu tới API nội bộ của JDK hoặc dependency giữa package. Nó không thay thế compatibility matrix của nhà cung cấp và cũng không chứng minh hành vi runtime đúng. Những đường gọi động qua reflection hoặc cấu hình có thể không được phân tích tĩnh đầy đủ.

### 7.5. Phân biệt bytecode version và Java API baseline

Một JAR có class file Java 17 có thể vẫn gọi API chỉ tồn tại từ Java 21 nếu quá trình build không giới hạn API đúng cách. Ngược lại, một thư viện có thể được biên dịch bằng JDK mới nhưng target release thấp hơn.

Vì vậy, cần kết hợp:

1. Metadata và tài liệu của nhà cung cấp.
2. Release đích/variant metadata.
3. Bytecode thực tế.
4. API Java mà thư viện tham chiếu.
5. Kiểm thử trên runtime mục tiêu.

Không nên chỉ dựa vào major version để kết luận toàn bộ dependency có thể chạy trên một JDK.

## 8. Điều tra một dependency có vấn đề: ví dụ thực hành

Giả sử sau khi nâng framework, ứng dụng gặp lỗi liên quan tới một thư viện JSON. Báo cáo build cho thấy nhiều nhánh yêu cầu các phiên bản Jackson khác nhau.

### 8.1. Với Maven

Xem cây đầy đủ và các node conflict:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Lọc nhóm Jackson:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:*
~~~

Xem POM hiệu lực:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Kiểm tra profile:

~~~bash
./mvnw help:active-profiles
~~~

Sau đó lần theo:

- Framework/BOM nào quản lý Jackson?
- Dependency trực tiếp nào khai báo version riêng?
- Có thư viện bắc cầu nào kéo version khác không?
- Có profile production thay đổi version hoặc scope không?
- Các module Jackson có đang được căn chỉnh cùng release không?

Không nên sửa riêng jackson-databind mà bỏ qua jackson-core và jackson-annotations nếu hệ sinh thái yêu cầu chúng đồng bộ.

### 8.2. Với Gradle

Xem runtime graph:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

Truy nguyên module đang có vấn đề:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Lặp lại với module liên quan nếu cần:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-core --configuration runtimeClasspath
~~~

Kiểm tra:

- Phiên bản được yêu cầu từ từng nhánh.
- Phiên bản được chọn cuối cùng.
- Selection reason.
- Platform hoặc constraint có tác động.
- Có force hoặc resolution rule không.
- Variant được chọn có đáp ứng JVM target không.

### 8.3. Đưa ra cách sửa có căn cứ

Các hướng xử lý thường gặp:

- Nâng BOM/platform của framework để nhận bộ dependency đã được kiểm thử cùng nhau.
- Loại bỏ khai báo version trùng lặp nếu version đã được quản lý tập trung.
- Thay dependency trực tiếp nếu nó kéo theo một nhánh cũ không còn được hỗ trợ.
- Thay thư viện đã ngừng duy trì.
- Dùng constraint có lý do rõ ràng khi cần giữ một version tương thích.
- Exclude một dependency chỉ khi đã xác nhận nhánh đó không cần thiết và implementation thay thế đã có.
- Nâng framework hoặc application server nếu dependency bị ràng buộc bởi nền tảng.

Sau khi sửa, chạy lại đúng lệnh dependency report để xác nhận graph mới. Tiếp theo build và test trên JDK mục tiêu. Một báo cáo graph đẹp hơn chưa đủ chứng minh ứng dụng đã hoạt động đúng.

## 9. Quản lý tính tái lập của dependency resolution

Dependency graph có thể thay đổi theo thời gian nếu dự án dùng version động, SNAPSHOT, repository mutable hoặc không khóa dependency.

### 9.1. Phiên bản động

Các khai báo dạng:

~~~groovy
implementation("com.example:library:+")
~~~

hoặc:

~~~xml
<version>[2.0,)</version>
~~~

có thể resolve ra phiên bản khác ở lần build sau tùy metadata repository và thời điểm kiểm tra. Điều này làm cho kết quả migration khó tái lập.

Trong production build, nên ưu tiên version rõ ràng, BOM/platform có kiểm soát hoặc cơ chế lock phù hợp.

### 9.2. Dependency locking của Gradle

Gradle hỗ trợ dependency locking để ghi nhận phiên bản đã resolve. Project cần bật locking, ví dụ:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó có thể ghi lock state khi chạy task resolve phù hợp:

~~~bash
./gradlew dependencies --write-locks
~~~

Lock file giúp các lần build sau dùng lại phiên bản đã khóa trong phạm vi cấu hình được quản lý. Khi chủ động nâng dependency, cần cập nhật lock file và review thay đổi như một phần của migration.

Locking không bảo đảm artifact trong repository không bị thay thế. Có thể kết hợp dependency verification để xác minh checksum hoặc chữ ký của artifact đã tải.

### 9.3. Quản lý phiên bản với Maven

Maven thường dùng:

- Version cụ thể cho dependency.
- Parent POM và BOM trong dependencyManagement.
- Maven Enforcer Plugin để kiểm tra quy tắc dependency.
- Repository được kiểm soát.
- Phiên bản plugin build được pin.
- Quy trình lưu lại effective POM và dependency tree trong CI khi cần audit.

Ví dụ, Maven Enforcer có thể áp dụng rule dependency convergence để phát hiện các nhánh yêu cầu version không đồng nhất. Rule này giúp phát hiện vấn đề, nhưng không tự chứng minh version nào là phù hợp với ứng dụng.

### 9.4. Repository và checksum

Cùng một tọa độ dependency nhưng nguồn repository, metadata hoặc artifact có thể khác nhau nếu hệ thống cho phép repository không đáng tin cậy hoặc artifact mutable.

Đối với build quan trọng:

- Dùng repository được quản trị.
- Hạn chế SNAPSHOT và version động trong release build.
- Xác minh checksum hoặc chữ ký khi có thể.
- Ghi nhận repository và dependency metadata.
- Giữ cache/build environment nhất quán khi cần tái lập kết quả.
- Không xem cache local là nguồn xác nhận duy nhất.

## 10. Tích hợp dependency analysis vào CI

Không nên chỉ chạy dependency report khi migration gặp lỗi. Có thể đưa một số kiểm tra vào pipeline để phát hiện thay đổi graph sớm.

Một pipeline có thể thực hiện:

~~~text
Checkout source
     |
     v
Resolve dependencies
     |
     v
Generate dependency reports
     |
     +--> Compile classpath
     |
     +--> Runtime classpath
     |
     +--> Test classpath
     |
     v
Check dependency policy
     |
     +--> Version conflict
     +--> Unsupported/blocked dependency
     +--> Dynamic version policy
     +--> Vulnerability scan
     |
     v
Build and tests on target JDK
     |
     v
Publish reports and artifact metadata
~~~

Các báo cáo nên lưu theo commit hoặc build number để có thể so sánh giữa trước và sau migration.

Có thể theo dõi:

- Dependency trực tiếp được thêm hoặc xóa.
- Dependency bắc cầu mới xuất hiện.
- Phiên bản được chọn thay đổi.
- Dependency chuyển từ compile sang runtime hoặc ngược lại.
- Thay đổi BOM/platform.
- Dependency có yêu cầu Java tối thiểu cao hơn.
- Artifact có bytecode release vượt quá baseline.
- Dependency có lỗ hổng hoặc đã hết hỗ trợ.

### 10.1. So sánh trước và sau migration

Nên tạo hai bộ báo cáo:

~~~text
baseline/
  compile-dependencies.txt
  runtime-dependencies.txt
  test-dependencies.txt
  effective-pom.xml        # Maven
  dependency-locks/        # Gradle, nếu dùng locking

target/
  compile-dependencies.txt
  runtime-dependencies.txt
  test-dependencies.txt
  effective-pom.xml
  dependency-locks/
~~~

So sánh để tìm thay đổi có ý nghĩa, sau đó truy nguyên từng dependency quan trọng bằng công cụ phù hợp.

Không phải mọi thay đổi graph đều là lỗi. Một dependency mới có thể là yêu cầu hợp lệ của framework mới. Điều cần làm là xác định thay đổi có chủ đích, đánh giá tác động và lưu bằng chứng.

### 10.2. Kiểm tra policy thay vì chỉ lưu báo cáo

Nếu tổ chức có quy định về Java baseline, có thể thêm policy:

- Không cho phép dependency runtime có bytecode vượt quá release được hỗ trợ.
- Không cho phép version động trong release build.
- Không cho phép một số dependency đã bị chặn.
- Không cho phép dependency có lỗ hổng vượt ngưỡng chính sách.
- Yêu cầu version framework nằm trong ma trận được hỗ trợ.
- Yêu cầu các module dùng chung tuân theo baseline runtime đã thống nhất.

Policy cần được định nghĩa theo nhu cầu thực tế. Một rule cứng có thể gây false positive nếu không phân biệt test-only, build-only, provided và runtime dependency.

## 11. Các giới hạn cần hiểu khi đọc dependency report

### Báo cáo không thể hiện mọi dependency được tải động

Một ứng dụng có thể tải plugin, driver hoặc module theo tên class ở runtime. Các thành phần này không nhất thiết xuất hiện trong dependency graph tĩnh.

### Dependency graph không chứng minh tính tương thích API

Một thư viện có thể resolve thành công nhưng vẫn gọi API bị loại bỏ hoặc không có trên runtime mục tiêu. Cần kiểm tra bytecode, API và test.

### Dependency được resolve không đồng nghĩa luôn được đóng gói

Provided dependency, container library, compile-only dependency và custom packaging có thể không nằm trong artifact cuối. Phải kiểm tra cách đóng gói thực tế.

### Dependency bắc cầu có thể thay đổi theo platform

BOM, constraints, version catalog và profile có thể đổi phiên bản được chọn mà không sửa khai báo trực tiếp của module.

### Báo cáo một configuration không đại diện cho tất cả

Runtime graph khác test graph; compile graph khác annotation processor graph. Cần kiểm tra những configuration phù hợp với mục tiêu.

### Dependency analysis tĩnh có thể báo sai mức sử dụng

Reflection, service loader, framework scanning và resource-based loading có thể khiến công cụ không nhận ra dependency đang được dùng.

### Kết quả local có thể khác CI

JDK, property, profile, repository, init script, lock state và cache có thể khác nhau. Khi điều tra migration, hãy lưu lại lệnh, môi trường và commit tạo ra báo cáo.

## 12. Checklist đối chiếu dependency trong một đợt Java migration

Trước khi chốt migration, hãy xác nhận:

- [ ] Đã xác định đúng module cần phân tích.
- [ ] Đã ghi lại commit, JDK, build tool và tham số build.
- [ ] Đã xem compile classpath và runtime classpath.
- [ ] Đã xem test classpath và annotation processor khi có liên quan.
- [ ] Đã kiểm tra dependency trực tiếp và bắc cầu.
- [ ] Đã truy nguyên các dependency có version bị đổi hoặc conflict.
- [ ] Đã xem Maven effective POM/profile hoặc Gradle constraints/platform/variant.
- [ ] Đã kiểm tra dependency build và plugin.
- [ ] Đã xác minh Java baseline của các thư viện quan trọng.
- [ ] Đã kiểm tra bytecode/API của artifact có rủi ro.
- [ ] Đã xem xét native library, agent và dependency tải động.
- [ ] Đã kiểm tra version động, SNAPSHOT, lock và repository policy.
- [ ] Đã chạy lại báo cáo sau khi thay đổi.
- [ ] Đã build và test trên runtime mục tiêu.
- [ ] Đã lưu báo cáo trước/sau để có thể review.

## 13. Mẫu báo cáo dependency cho migration

Có thể lưu một bản ghi ngắn theo mẫu:

~~~text
PROJECT
  Module:
  Commit:
  Build tool and version:
  Build JVM:
  Target JDK:
  Compiler release:

RESOLUTION CONTEXT
  Maven profiles / Gradle properties:
  Module:
  Configuration or scope:
  Repository:
  Lock state:

DEPENDENCY FINDINGS
  Direct dependencies:
  Important transitive dependencies:
  Version conflicts:
  Selected versions and reasons:
  BOM / platform / constraints:
  Exclusions / force rules:
  Build plugins and processors:

JAVA COMPATIBILITY
  Required Java baseline:
  Bytecode major versions:
  Internal JDK API usage:
  Native libraries and agents:
  Vendor support evidence:

MIGRATION IMPACT
  Dependencies to upgrade:
  Dependencies to replace/remove:
  Compatibility blockers:
  Unverified components:
  Required tests:

VALIDATION
  Dependency report before:
  Dependency report after:
  Build result:
  Runtime test result:
  Security scan:
  Rollback plan:
~~~

Báo cáo tốt phải giúp người review lần theo được từ dependency gây vấn đề đến nhánh đưa nó vào graph, quy tắc chọn version, bằng chứng Java compatibility và quyết định xử lý.

## 14. Ghi nhớ

Khi đối chiếu dependency bằng Maven hoặc Gradle, hãy trả lời bốn câu hỏi:

1. **Có gì trong graph?** Xem đúng module và configuration/scope, bao gồm dependency bắc cầu.
2. **Vì sao nó có mặt?** Truy nguyên nhánh phụ thuộc, BOM/platform, constraint, profile, variant và rule.
3. **Phiên bản nào được dùng?** Xác định selected version và lý do resolution, thay vì chỉ đọc version trong file khai báo.
4. **Nó có chạy được trên target không?** Kết hợp tài liệu hỗ trợ, metadata, bytecode, API analysis và kiểm thử trên runtime mục tiêu.

Maven và Gradle cung cấp bằng chứng về graph đã resolve. Người thực hiện migration cần diễn giải bằng chứng đó trong ngữ cảnh ứng dụng: dependency nào thuộc runtime, dependency nào chỉ phục vụ build/test, phiên bản nào bị thay thế, và thư viện nào có thể cản trở Java target.

Khi đã biết dependency thực tế và lý do mỗi phiên bản được chọn, nhóm có thể xử lý migration có căn cứ, tránh nâng hoặc ép version tùy tiện, đồng thời tạo được báo cáo trước/sau đủ rõ để review và tái lập.

