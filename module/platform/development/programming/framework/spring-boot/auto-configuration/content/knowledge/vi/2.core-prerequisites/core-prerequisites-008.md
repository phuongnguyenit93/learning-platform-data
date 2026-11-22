# Dependency trực tiếp, dependency bắc cầu và phiên bản Spring Boot đang sử dụng

## 1. Vì sao phải hiểu dependency trước khi học auto-configuration?

Spring Boot đưa ra rất nhiều cấu hình mặc định dựa trên **những class thực sự có trên classpath**. Nhưng classpath của một ứng dụng được tạo bởi cả dependency mà lập trình viên trực tiếp khai báo lẫn dependency do các thư viện khác kéo theo. Vì vậy, trước khi giải thích tại sao một auto-configuration được kích hoạt, phải biết **ứng dụng đang chạy với những thư viện nào và phiên bản thực tế của chúng**.

Một trường hợp thường gặp: trong Gradle, ứng dụng chỉ khai báo **spring-boot-starter-web** nhưng vẫn dùng được **DispatcherServlet** của Spring MVC và **ObjectMapper** của Jackson. Hai loại class này đến từ các dependency được mang vào qua starter, không nhất thiết được ứng dụng ghi trực tiếp trong build.gradle. Nếu một thư viện bắc cầu bị thay, bị exclude hoặc được chọn ở phiên bản khác, các điều kiện **@ConditionalOnClass**, **@ConditionalOnMissingBean** và hành vi tự cấu hình có thể khác.

Có ba câu hỏi phải tách bạch:

1. **Tôi khai báo dependency nào?** Xem phần **dependencies** của build.gradle hoặc các khai báo tương đương.
2. **Gradle chọn dependency nào để biên dịch và chạy?** Xem đồ thị dependency của đúng configuration, đặc biệt **runtimeClasspath** và **dependencyInsight**.
3. **Phiên bản Spring Boot đang sử dụng là phiên bản nào?** Phân biệt phiên bản plugin, BOM quản lý dependency, các artifact Boot được resolve và version thư viện Boot thực sự có ở runtime.

Bài này giải thích cách trả lời cả ba bằng lệnh và bằng chứng, giúp đọc auto-configuration chính xác hơn.

## 2. Dependency trực tiếp (direct dependency)

**Dependency trực tiếp** là dependency được project **khai báo rõ ràng** trong cấu hình build. Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở đây project khai báo trực tiếp hai dependency:

- **spring-boot-starter-web** là dependency của mã ứng dụng ở configuration **implementation**; nó tham gia compile classpath và runtime classpath theo cách Gradle Java plugin xác định.
- **spring-boot-starter-test** là dependency dùng khi biên dịch/chạy test; thông thường nó không được đóng gói làm dependency runtime của ứng dụng production.

Điểm cần chú ý: dependency trực tiếp **không đồng nghĩa** với dependency có code nằm trong module của mình. Starter web phần lớn là một cách **tập hợp dependency và cung cấp một quy ước sử dụng thư viện**. Bản thân starter không tự làm nhiệm vụ component scanning hay đăng ký các bean Spring MVC.

Dependency trực tiếp cũng không nhất thiết phải có phiên bản ghi ngay cạnh tọa độ **group:artifact**. Nếu project import BOM hoặc dùng dependency constraints, phần phiên bản có thể do cơ chế quản lý dependency quyết định.

### 2.1. Một số configuration quan trọng trong Gradle

| Khai báo | Dùng cho mục đích nào? | Có mặc định tham gia runtime của ứng dụng chính? |
| --- | --- | --- |
| **implementation** | Thư viện cần cho implementation của mã chính | Có, theo dependency resolution của project. |
| **api** (java-library) | Thư viện lộ ra ở API công khai của một Java library | Có; đồng thời có thể truyền vào compile classpath của consumer. |
| **compileOnly** | Chỉ cần khi biên dịch; môi trường khác phải cung cấp lúc chạy nếu cần | Không. |
| **runtimeOnly** | Chỉ cần khi chạy, ví dụ một JDBC driver | Có, nhưng không ở compile classpath thông thường. |
| **testImplementation** | Mã test, test framework, assertion libraries | Không đưa vào runtime classpath chính; dùng cho test. |
| **testRuntimeOnly** | Thành phần chỉ cần khi chạy test | Không đưa vào runtime classpath chính. |

Các dòng trên là **vai trò configuration**. Chúng không cho biết artifact nào thực sự được chọn nếu tồn tại conflict, constraints hoặc rule khác. Hãy luôn kiểm tra kết quả resolution.

### 2.2. Tại sao phân loại direct lại hữu ích?

Khi thấy một package import trong mã ứng dụng, hãy biết dependency cung cấp API ấy có được khai báo trực tiếp hay chỉ tình cờ có mặt qua thư viện khác. Dựa vào dependency bắc cầu mà ứng dụng trực tiếp gọi API có thể khiến mã bị vỡ khi thư viện trung gian thay dependency.

Ví dụ, nếu ứng dụng **tự viết code dùng ObjectMapper**, nên cân nhắc khai báo dependency trực tiếp cho API Jackson liên quan hoặc starter phù hợp thay vì phụ thuộc ngầm rằng một thư viện không liên quan sẽ kéo Jackson vào mãi mãi. Trái lại, không cần khai báo mọi dependency bắc cầu thành direct chỉ để làm đẹp danh sách; điều đó làm giảm khả năng quản lý phiên bản tập trung.

## 3. Dependency bắc cầu (transitive dependency)

**Dependency bắc cầu** là dependency xuất hiện vì **một dependency khác cần nó**. Trong Gradle, khi mô-đun A phụ thuộc B và B phụ thuộc C (và metadata chỉ ra C cần cho configuration tương ứng), C có thể trở thành một phần của dependency graph của A dù A không khai báo C.

Sơ đồ minh họa đơn giản cho ứng dụng web:

~~~text
Project demo
  └─ direct: spring-boot-starter-web
       ├─ transitive: spring-boot-starter
       ├─ transitive: spring-boot-starter-json
       │    └─ transitive: jackson-databind (qua dependency graph)
       ├─ transitive: spring-boot-starter-tomcat
       │    └─ transitive: tomcat-embed-core
       ├─ transitive: spring-web
       └─ transitive: spring-webmvc
            └─ transitive: spring-core / Spring Framework components
~~~

Đây là **sơ đồ khái niệm đã lược bớt nhánh**. Các cạnh và phiên bản chính xác phải lấy từ metadata và báo cáo Gradle của đúng phiên bản starter. Không dùng sơ đồ này như bản chụp dependency tree của mọi ứng dụng.

Một artifact có thể vừa là dependency trực tiếp vừa xuất hiện qua nhiều nhánh bắc cầu. Gradle sẽ **resolve một tập component cho từng configuration**, nên không mặc định tải một bản JAR riêng cho mỗi đường đi trên cây.

### 3.1. Dependency bắc cầu giải thích vì sao auto-configuration chạy

Trong ứng dụng Spring Boot, một auto-configuration có thể kiểm tra sự hiện diện của class bằng điều kiện như **@ConditionalOnClass**. Class ấy có thể xuất hiện do dependency bắc cầu, ví dụ Spring MVC hoặc Jackson được mang vào bởi starter web.

Khi class xuất hiện, một điều kiện classpath có thể match. Nhưng **chỉ có class trên classpath chưa đủ kết luận bean sẽ được tạo**: auto-configuration còn xét property, bean hiện có, loại ứng dụng và các điều kiện khác.

Ngược lại, nếu một dependency bắc cầu bị exclude, một điều kiện classpath có thể không còn match. Các thư viện khác có thể vẫn tham chiếu class bị thiếu và dẫn tới lỗi biên dịch hoặc runtime. Vì vậy **exclude có tác động vượt ra ngoài việc làm nhỏ file JAR**.

### 3.2. Dependency graph không phải class loading sequence

Gradle dependency resolution xác định những component/artifact cần dùng cho một configuration. Classpath là danh sách artifact sau resolution. JVM và Spring mới dùng những class ấy trong quá trình khởi động.

Không nên suy luận rằng “dependency xuất hiện trước trên cây” thì Spring tạo bean trước. Thứ tự bean phụ thuộc vào cấu hình và vòng đời của Spring, còn thứ tự auto-configuration có cơ chế riêng. Dependency graph trả lời **có gì và phiên bản nào**; condition report trả lời **vì sao một cấu hình được áp dụng**.

## 4. Version khai báo, version được quản lý và version được chọn

Bài toán phiên bản phức tạp hơn việc đọc một số trong build.gradle. Cần phân biệt ba mức:

| Mức | Ví dụ | Điều nó cho biết |
| --- | --- | --- |
| **Requested/declared version** | Khai báo trực tiếp một tọa độ version, hoặc plugin version | Phiên bản được yêu cầu ở một vị trí cấu hình. |
| **Managed/constraint version** | Version do Spring Boot BOM/platform hoặc constraint quản lý | Quy tắc/đề xuất/ràng buộc tham gia vào giải thuật chọn version. |
| **Resolved/selected version** | Artifact cụ thể xuất hiện trên runtimeClasspath | Phiên bản Gradle thực sự chọn cho configuration ấy. |

Nếu project dùng BOM, có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

mà không ghi version trên dòng **implementation**. Gradle vẫn có thể resolve starter và các dependency của nó nhờ BOM/management đã được thiết lập ở project.

Nếu một artifact được yêu cầu ở nhiều phiên bản, Gradle sẽ tiến hành conflict resolution theo metadata, constraints và các rule của build. Kết quả **có thể khác version người đọc đoán từ một dòng khai báo**. Các lý do thường gặp gồm: một nhánh bắc cầu yêu cầu version mới hơn, constraint bắt buộc một version, platform, dependency substitution, hoặc resolution strategy. Không nên giả định “direct luôn thắng transitive” hay “BOM tuyệt đối không thể bị ghi đè”.

### 4.1. Spring Boot BOM quản lý những gì?

Spring Boot phát hành **spring-boot-dependencies** BOM với tập version được kiểm thử/khuyến nghị cho nhiều thư viện mà Boot tích hợp: Spring Framework, Jackson, logging, các embedded server và nhiều công nghệ khác. Dùng một BOM nhất quán giúp giảm việc tự ghép version giữa các module.

Trong Gradle có hai cách phổ biến:

- Plugin **io.spring.dependency-management** tích hợp với Spring Boot Gradle plugin, có thể import BOM phù hợp với phiên bản plugin Boot.
- Cơ chế **platform** gốc của Gradle có thể import Maven BOM: **implementation platform('org.springframework.boot:spring-boot-dependencies:...')** hoặc cấu hình phù hợp khác. **enforcedPlatform** mang semantics mạnh hơn và cần dùng thận trọng khi phát hành thư viện.

Đừng trộn các cơ chế quản lý version mà không hiểu độ ưu tiên hoặc hiệu ứng conflict. Nếu dùng plugin dependency management, cách nó áp dụng version và cách Gradle native constraints tham gia resolution có thể không giống nhau trong mọi tình huống. Quyết định cuối cùng phải dựa trên **dependencyInsight của configuration thật**.

### 4.2. Một chữ “Spring Boot version” có thể chỉ nhiều thứ

Có ít nhất bốn phiên bản liên quan nhưng khác vai trò:

1. **Spring Boot Gradle plugin version**, ví dụ ở dòng **id 'org.springframework.boot' version '3.3.13'**. Nó điều khiển các Gradle task, bootJar, bootRun và integration của build.
2. **Spring Boot BOM version**, ví dụ **org.springframework.boot:spring-boot-dependencies:3.3.13**, quản lý version của các dependency theo bảng tương thích.
3. **Resolved Spring Boot library version**, ví dụ artifact **spring-boot**, **spring-boot-autoconfigure**, **spring-boot-starter-web** trong runtimeClasspath.
4. **Spring Boot runtime version** được lớp **org.springframework.boot.SpringBootVersion** báo cáo từ thư viện Spring Boot đang nạp ở runtime.

Trong một project cấu hình chuẩn, những version Boot cốt lõi thường **được căn chỉnh**. Tuy nhiên, chúng không phải cùng một định nghĩa, và một build đã tùy biến hoặc có xung đột vẫn có thể chọn bộ artifact không đồng nhất.

**Spring Framework version** (ví dụ artifact **spring-context**, **spring-core**) cũng **không phải** Spring Boot version. Version Java/JDK và Gradle lại là hai loại version khác. Đừng dùng “Java 21”, “Gradle 8” hoặc số ở artifact Spring Framework làm câu trả lời cho câu hỏi “ứng dụng đang dùng Spring Boot version nào?”.

## 5. Ví dụ Gradle chạy được: khám phá dependency graph của Spring Boot

Tạo một project Java 21 nhỏ để kiểm chứng các ý tưởng trên. Phiên bản **3.3.13** dưới đây là **một mốc được cố định cho ví dụ**, không phải lời khẳng định về phiên bản mới nhất hoặc phiên bản của project khác. Khi áp dụng vào project thật, hãy đọc version thực tế thay vì sao chép mốc này.

### 5.1. Cấu trúc

~~~text
dependency-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/dependencylab/
    └── DependencyLabApplication.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'dependency-lab'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Những điểm cần quan sát:

- Direct runtime dependency: **spring-boot-starter-web**.
- Direct test dependency: **spring-boot-starter-test**.
- Phiên bản Boot Gradle plugin: **3.3.13**.
- Plugin dependency-management cùng Boot plugin giúp dùng bảng dependency management từ BOM tương ứng trong thiết lập thông thường.
- **Không ghi version** trực tiếp trên dòng starter-web. Version của starter được giải quyết bởi cơ chế management.
- Java toolchain 21 là lựa chọn JDK của ví dụ, không phải version Spring Boot.

Mã trong **src/main/java/com/example/dependencylab/DependencyLabApplication.java**:

~~~java
package com.example.dependencylab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootVersion;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DependencyLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyLabApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectClasspath() {
        return args -> {
            ClassLoader loader =
                DependencyLabApplication.class.getClassLoader();

            System.out.println(
                "Spring Boot runtime version: "
                    + SpringBootVersion.getVersion()
            );
            System.out.println(
                "Spring MVC DispatcherServlet available: "
                    + ClassUtils.isPresent(
                        "org.springframework.web.servlet.DispatcherServlet",
                        loader
                    )
            );
            System.out.println(
                "Jackson ObjectMapper available: "
                    + ClassUtils.isPresent(
                        "com.fasterxml.jackson.databind.ObjectMapper",
                        loader
                    )
            );
        };
    }
}
~~~

Đây là chương trình Spring Boot hoàn chỉnh trong cấu trúc project phía trên. **ClassUtils.isPresent** kiểm tra khả năng nạp class theo classloader của ứng dụng; không cần import DispatcherServlet hoặc ObjectMapper trong mã nguồn. Vì vậy ví dụ vẫn có thể biên dịch khi ta đổi starter ở thí nghiệm sau.

### 5.2. Chạy ứng dụng và đọc kết quả

Với Gradle được cài và JDK 21 sẵn có, tại thư mục root:

~~~bash
gradle bootRun
~~~

Nếu project có Gradle Wrapper, có thể dùng:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng **.\gradlew.bat bootRun**. Khi ứng dụng khởi động thành công với dependency đã khai báo, các dòng do ApplicationRunner in ra dự kiến là:

~~~text
Spring Boot runtime version: 3.3.13
Spring MVC DispatcherServlet available: true
Jackson ObjectMapper available: true
~~~

Chúng có thể xuất hiện giữa log khởi động; đây **không phải toàn bộ stdout** của Gradle. Trong ví dụ ghép version đồng bộ, runtime version trả về **3.3.13**. Nếu project tự override dependency, kết quả có thể khác; nếu metadata package của library bị mất trong môi trường đóng gói đặc biệt, **SpringBootVersion.getVersion()** có thể không trả về chuỗi version mong đợi. Do đó vẫn cần kiểm tra dependency graph.

### 5.3. Đọc toàn bộ dependency runtime

Ở root:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Khi dùng Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Lệnh trả về cây dependency của **runtimeClasspath**. Với starter web, hãy lần theo các nhánh đến **spring-webmvc**, **spring-boot-autoconfigure**, **jackson-databind** và embedded server tương ứng. Không cố ghi nhớ toàn bộ cây từ một ví dụ vì phiên bản và metadata có thể thay đổi.

Đọc báo cáo theo hướng:

~~~text
dependency-lab
 └─ spring-boot-starter-web      (direct)
      ├─ ... Spring MVC          (transitive)
      ├─ ... JSON/Jackson        (transitive)
      └─ ... embedded server     (transitive)
~~~

Trong kết quả thật của Gradle, bạn có thể thấy ký hiệu **->** (requested version được chọn thành version khác), **(*)** (một nhánh đã được thể hiện trước đó) và **(c)** (dependency constraint, tùy phiên bản/cách xuất report). Đây là tín hiệu cần đọc tiếp, không phải thông báo lỗi mặc định.

### 5.4. Truy vết một artifact bằng dependencyInsight

Cây đầy đủ có thể dài. Khi chỉ muốn biết “Jackson đến từ đâu và Gradle chọn bản nào?”, dùng:

~~~bash
gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

Trong PowerShell, có thể viết một dòng:

~~~powershell
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Lệnh này giúp trả lời các câu hỏi:

- **Phiên bản nào được chọn?**
- **Những đường dependency nào dẫn tới module đó?**
- **Có requested version khác selected version không?**
- **Lý do selection có liên quan conflict, constraints hay rule không?**

Tiếp tục điều tra các thư viện Spring Boot cốt lõi:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-autoconfigure
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-starter-web
~~~

Nếu project có nhiều Gradle subproject, phải gọi task của **đúng module ứng dụng**. Ví dụ: **gradle :api-service:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind**. Kết quả ở root hoặc module thư viện chưa chắc là runtime graph của dịch vụ đang chạy.

### 5.5. So sánh compileClasspath và runtimeClasspath

Chạy:

~~~bash
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Mục tiêu là nhận ra ba đồ thị có phạm vi khác nhau. **testRuntimeClasspath** có thể có JUnit/AssertJ hoặc thư viện test khác mà ứng dụng production không sử dụng. Ngược lại, **runtimeOnly** có thể chỉ xuất hiện ở runtime. Đừng lấy một dependency trong testRuntimeClasspath làm bằng chứng rằng auto-configuration production sẽ thấy class đó.

Trong trường hợp dùng executable JAR, cần kiểm tra **artifact đóng gói cuối cùng** vì việc package/deploy có thể tạo khác biệt so với việc chỉ xem build.gradle. Lệnh build.gradle và source code không phải nguồn thông tin duy nhất về runtime classpath.

## 6. Thử nghiệm thay một direct dependency để hiểu transitive dependency

Trong **build.gradle**, đổi:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

thành:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter'
~~~

Giữ nguyên class **DependencyLabApplication**. Chạy lại:

~~~bash
gradle bootRun
~~~

Theo đồ thị dependency mặc định của mốc ví dụ, ứng dụng lúc này không còn được starter web kéo Spring MVC và Jackson vào. Các dòng kiểm tra classpath dự kiến:

~~~text
Spring Boot runtime version: 3.3.13
Spring MVC DispatcherServlet available: false
Jackson ObjectMapper available: false
~~~

**Giải thích:** Starter nền tảng vẫn cung cấp các thành phần cần cho một ứng dụng Boot cơ bản, nhưng không tự kéo mọi thư viện web/JSON. Ứng dụng có thể chạy như non-web application và thoát sau khi ApplicationRunner kết thúc. Trước khi kết luận về Jackson hay MVC trong một project khác, hãy kiểm tra xem có dependency nào **khác** vẫn đưa chúng trở lại classpath không.

Khi thay starter, chạy lại:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Nếu không còn artifact trong configuration, dependencyInsight sẽ không cho ra đường dependency được chọn cho artifact đó. So sánh trước/sau là bằng chứng trực tiếp về ảnh hưởng của dependency bắc cầu.

### 6.1. Thêm dependency trực tiếp để thử một điều kiện riêng

Trong trạng thái chỉ có **spring-boot-starter**, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **đoạn thay thế toàn bộ dependencies block** của ví dụ. Chạy lại, ta kỳ vọng **Jackson ObjectMapper available: true**, còn **Spring MVC DispatcherServlet available: false**, nếu không có dependency nào khác đưa MVC vào. Lúc này Jackson là dependency **trực tiếp** của project thay vì chỉ xuất hiện qua starter web.

Một class hiện diện có thể thỏa mãn điều kiện **@ConditionalOnClass** nào đó. Tuy nhiên, việc class Jackson có mặt **không tự bảo đảm ứng dụng sẽ cần hoặc tự tạo bean MVC/HTTP**. Các điều kiện khác và loại ứng dụng tiếp tục quyết định những gì được cấu hình.

Sau thí nghiệm, khôi phục dependency block ban đầu để tiếp tục các lệnh xác minh ở trạng thái web chuẩn.

## 7. Làm thế nào xác định đúng phiên bản Spring Boot đang dùng?

Không có một dòng lệnh duy nhất luôn trả lời trọn vẹn mọi trường hợp. Hãy kết hợp **khai báo build**, **resolved runtime dependencies** và **thực tế runtime**.

### Bước 1 — Đọc các vị trí quản lý phiên bản

Trong Gradle, tìm:

- Plugin **org.springframework.boot** và version áp dụng cho module.
- Plugin **io.spring.dependency-management**, BOM import hoặc **platform**/**enforcedPlatform**.
- Các version, constraints, **resolutionStrategy**, catalog version, convention plugin và dependency substitution nếu project sử dụng.
- Trong multi-module, nơi khai báo plugin ở root **apply false** chưa chắc là nơi phiên bản BOM/runtime được áp dụng cho từng subproject.

Với Maven, các nguồn tương đương là **spring-boot-starter-parent**, **dependencyManagement** import BOM, dependencies trực tiếp và các override. Parent hoặc BOM mô tả cơ chế quản lý version, nhưng không thay thế việc kiểm tra dependency tree khi nghi ngờ conflict.

### Bước 2 — Đọc version của artifact Boot được resolve

Chạy trong đúng module:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot
gradle dependencyInsight --configuration runtimeClasspath --dependency org.springframework.boot:spring-boot-autoconfigure
~~~

Để trả lời “runtime thật có version nào”, version được chọn ở **runtimeClasspath** có ý nghĩa hơn việc chỉ đọc version trong plugin block. Nếu các artifact Spring Boot lõi bị chọn khác phiên bản, hãy coi đó là dấu hiệu cần điều tra thay vì giả định rằng tất cả tương thích.

### Bước 3 — Kiểm tra ứng dụng lúc chạy

Trong mã Java có thể dùng:

~~~java
String runtimeVersion = org.springframework.boot.SpringBootVersion.getVersion();
System.out.println("Spring Boot runtime version: " + runtimeVersion);
~~~

Đây là **đoạn code Java minh họa**, được chạy bên trong ứng dụng đã có dependency Spring Boot. Phương thức đọc thông tin version của thư viện Boot mà JVM đang sử dụng; khác với việc đọc khai báo ở build file. Nó hữu ích để kiểm tra runtime, nhưng trong trường hợp manifest/package metadata bất thường có thể không cho một giá trị tin cậy. Hãy đối chiếu với artifact resolved và artifact thực sự được deploy.

Một ứng dụng cũng thường có log khởi động/banner hiển thị version Boot, nhưng log có thể bị tắt, thay banner hoặc được tùy biến. **Không dựa duy nhất vào chuỗi banner** khi điều tra conflict.

### Bước 4 — Kiểm tra file được triển khai

Đối với project ví dụ:

~~~bash
gradle bootJar
jar tf build/libs/dependency-lab-0.0.1-SNAPSHOT.jar
~~~

Trong executable Spring Boot JAR chuẩn, các thư viện runtime thường xuất hiện ở **BOOT-INF/lib/**, ví dụ entry **spring-boot-...jar**, **spring-boot-autoconfigure-...jar** và các dependency khác. Kiểm tra tên file để biết các artifact thực tế đã được package vào bản phát hành. Cấu trúc output cụ thể phụ thuộc chế độ packaging và customizations; layered JAR vẫn thường có các entry thư viện. Nếu deploy bằng Docker image, WAR hoặc external container, cần kiểm tra classpath/artifact của **môi trường thực sự được deploy** thay vì suy luận từ JAR một phiên bản build cũ.

**Không mặc định rằng JAR vừa build là JAR production đã chạy.** Build hiện tại, file phát hành và container đang chạy có thể được tạo ở thời điểm khác nhau.

### Bước 5 — So sánh và ghi lại bằng chứng

Bảng kiểm tra khuyến nghị:

| Dữ kiện | Nguồn kiểm chứng | Ví dụ cho project minh họa |
| --- | --- | --- |
| Boot Gradle plugin | plugins block / plugin resolution | 3.3.13 |
| BOM quản lý | dependency management/BOM/platform | spring-boot-dependencies:3.3.13 |
| Spring Boot thư viện được chọn | runtimeClasspath dependencyInsight | Mục tiêu đồng bộ 3.3.13 |
| Spring Boot runtime library | SpringBootVersion.getVersion() | 3.3.13 khi library metadata chuẩn |
| Spring Framework / Jackson / Tomcat | dependencyInsight cho artifact đó | Phụ thuộc BOM, graph và override |
| JDK thực thi | java -version và runtime environment | Không suy ra chỉ từ Spring Boot version |

“Ứng dụng dùng Spring Boot 3.3.13” là kết luận hợp lý **sau khi** xác nhận Boot plugin/BOM và các thư viện cốt lõi thực sự ở phiên bản đó, chứ không chỉ vì nhìn thấy một version ở root project.

## 8. Dependency conflict: vì sao selected version khác requested version?

Giả sử một thư viện yêu cầu một phiên bản Jackson, còn thư viện khác yêu cầu phiên bản khác. Gradle resolve chúng theo quy tắc và metadata áp dụng ở configuration. Với đường phụ thuộc có conflict, báo cáo dependencies có thể hiển thị chuyển đổi version bằng **->**; **dependencyInsight** cho biết component được chọn và lý do liên quan.

Các yếu tố cần phân biệt:

- **Version constraint / platform:** đưa thông tin về phiên bản được phép, ưu tiên hoặc bắt buộc tùy cách khai báo.
- **Transitive request:** thêm những yêu cầu phiên bản từ các dependency cấp dưới.
- **Dependency substitution:** thay một module bằng module khác hoặc project khác khi build có rule tương ứng.
- **Resolution strategy:** có thể ép/chọn phiên bản đặc thù nhưng cần lý do rõ ràng.
- **Dependency lock:** nếu project bật locking, file lock có thể giúp giữ đồ thị resolved ổn định trong phạm vi được khóa.

Không có quy tắc tổng quát “version cao nhất luôn tốt nhất”. Gradle có cơ chế conflict resolution mặc định, nhưng constraints, strict versions và rules có thể thay đổi kết quả; version mới hơn chưa chắc tương thích với Spring Boot/BOM hiện có. Mọi override cần được kiểm thử về binary compatibility và hành vi runtime.

### 8.1. Một ví dụ override cần đọc kỹ

Giả sử build đang import Boot BOM nhưng một người thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
~~~

Mục đích của ví dụ là minh họa **requested version trực tiếp** cho Jackson, không đề xuất override này trong mọi bản Boot. Version được chọn sau resolution **có thể** phụ thuộc BOM/constraint, dependency khác và rule cụ thể. Không kết luận chỉ từ dòng khai báo rằng version 2.17.2 chắc chắn hiện diện tại runtime.

Sau khi sửa, phải chạy:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
gradle dependencies --configuration runtimeClasspath
~~~

Xác nhận **selected version** và so với tập version được Boot quản lý. Nếu override là vì bản vá bảo mật, hãy đánh giá cả khả năng tương thích với các thư viện Jackson liên quan chứ không chỉ một artifact.

### 8.2. Khi nào nên exclude một dependency bắc cầu?

**Exclude** phù hợp khi có chứng cứ một thư viện kéo dependency không cần, xung đột hoặc cần một implementation thay thế có chủ đích. Ví dụ cú pháp:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

Đoạn này chỉ minh họa cách exclude Tomcat starter. Một ứng dụng **Servlet** cần một web server/container thích hợp để chạy; nếu loại Tomcat mà không cung cấp phương án thay thế hoặc chạy trong container phù hợp, ứng dụng có thể không hoạt động như mong đợi. Đừng sao chép exclude trên để “tối ưu dependency” mà chưa có mục tiêu và test.

Cần nhớ: một dependency có thể đi vào qua **nhiều đường**. Exclude ở một nhánh không bảo đảm artifact biến mất khỏi graph nếu nhánh khác vẫn kéo nó vào. Hãy xác minh bằng dependencyInsight và kiểm tra runtime.

## 9. Mối liên hệ trực tiếp với Spring Boot auto-configuration

Spring Boot auto-configuration đánh giá classpath **sau khi cơ chế build/dependency resolution đã tạo môi trường runtime**. Hai tầng hoạt động khác nhau nhưng liên quan chặt chẽ:

~~~text
build.gradle / BOM / constraints
             |
             v
Gradle giải quyết dependency graph
             |
             v
runtimeClasspath thực tế
             |
             v
Spring Boot quét/import auto-configuration ứng viên
             |
             v
@ConditionalOnClass, @ConditionalOnBean,
@ConditionalOnProperty, loại web app, ...
             |
             v
Bean được tạo hoặc cấu hình bị bỏ qua
~~~

Một lỗi tưởng như “Spring Boot không tự cấu hình” có thể bắt nguồn ở tầng dependency:

**Ví dụ A — thiếu class:** Một auto-configuration yêu cầu class X nhưng dependency chứa X không có trong runtimeClasspath. Điều kiện classpath không match, nên cấu hình liên quan không được áp dụng.

**Ví dụ B — có class nhưng sai version:** Cùng tên class tồn tại nhưng thư viện khác version có API không tương thích. Condition chỉ kiểm tra sự hiện diện class **không bảo đảm tương thích nhị phân mọi API**. Ứng dụng có thể lỗi khi nạp class, khởi tạo bean hoặc gọi phương thức.

**Ví dụ C — class từ test:** Class xuất hiện trong testRuntimeClasspath nhưng không có trong runtimeClasspath của ứng dụng chính. Test có thể chạy với classpath khác production. Phải kiểm tra đúng configuration.

**Ví dụ D — có dependency nhưng vẫn không có bean:** Điều kiện khác không match, chẳng hạn property disabled, bean do người dùng định nghĩa khiến **@ConditionalOnMissingBean** back off, hoặc không phải loại web application phù hợp. DependencyInsight không thể thay thế condition report.

**Ví dụ E — starter khác runtime stack:** Một ứng dụng đưa Spring MVC vào cùng những thành phần Reactive có thể thay đổi cách Boot xác định loại ứng dụng. Đừng nhìn riêng một starter rồi tự suy ra toàn bộ runtime; cần biết classpath, cấu hình web application type và các điều kiện thực tế.

### 9.1. Phương pháp chẩn đoán theo thứ tự

Khi một bean đáng lẽ được tự cấu hình nhưng không có:

1. **Xác nhận đúng module ứng dụng và configuration:** đọc **runtimeClasspath**, không đọc nhầm testClasspath hoặc dependency tree của root build.
2. **Truy dependency:** xác định class cần thiết nằm trong artifact nào; dùng **dependencyInsight** để thấy version và đường đi.
3. **Kiểm tra version Boot đã chọn:** đối chiếu **spring-boot** và **spring-boot-autoconfigure**, sau đó kiểm tra version của thư viện liên quan.
4. **Đọc Condition Evaluation Report:** bật **--debug** cho ứng dụng, hoặc dùng Actuator conditions endpoint khi đã cấu hình an toàn để truy cập.
5. **Kiểm tra bean và property:** xác định người dùng đã khai báo bean nào, property nào ghi đè, profile nào đang active.
6. **Sửa nguyên nhân tối thiểu và kiểm chứng lại:** sau mỗi thay đổi dependency, chạy build/test, đối chiếu graph và condition report.

Không nên giải quyết tất cả bằng cách thêm dependency thủ công, bật bean overriding hoặc exclude hàng loạt. Những thay đổi ấy có thể che lỗi thật.

## 10. Các hiểu lầm thường gặp

**“Trong build.gradle chỉ thấy một dependency thì runtime chỉ có một JAR.”** Sai. Dependency trực tiếp có thể kéo nhiều dependency bắc cầu. Đếm JAR từ runtimeClasspath, không đếm dòng implementation.

**“Starter là auto-configuration.”** Sai. Starter thường tập hợp dependency. Auto-configuration là các lớp cấu hình có điều kiện mà Spring Boot phát hiện/import từ các tài nguyên phù hợp.

**“Không ghi version ở implementation nghĩa là Gradle luôn tự lấy bản mới nhất.”** Sai. Version có thể do BOM, constraint hoặc resolution rule quyết định; không phải mặc định nâng lên newest trên Internet.

**“Dòng plugin Boot version cho biết chắc tất cả dependency Boot ở runtime cùng version.”** Không đủ. Plugin, BOM và thư viện Boot resolved có thể bị quản lý khác nhau. Cần đọc runtimeClasspath và runtime evidence.

**“Dependency trực tiếp luôn thắng dependency bắc cầu.”** Không phải quy tắc tổng quát. Selection phụ thuộc cơ chế resolution và constraints cụ thể.

**“Thư viện chỉ có trong test cũng được Boot auto-config ở production.”** Sai. Test classpath và runtime classpath chính khác nhau.

**“Giữ mọi transitive dependency mới an toàn.”** Không hẳn. Một dependency có thể không cần thiết hoặc gây xung đột; nhưng loại bỏ phải dựa trên bằng chứng về classpath/compatibility.

**“Thêm @ConditionalOnClass là đảm bảo một integration tương thích.”** Sai. Sự tồn tại của class chưa chứng minh tương thích về API hoặc hành vi ở mọi version.

**“Một dependencyInsight rỗng nghĩa là class không thể tồn tại.”** Chưa chắc. Có thể đang kiểm tra sai configuration, sai tên artifact, hoặc class đến từ artifact khác/shading. Cần xác minh classpath thực tế.

**“Log khởi động là bằng chứng duy nhất của Spring Boot version.”** Không nên. Banner có thể thay hoặc bị tắt; kiểm chứng bằng cả resolved dependencies và runtime library.

## 11. Bài thực hành tự kiểm tra

### Bài 1 — Vẽ lại đường đi của Jackson

Với project dùng starter web, chạy:

~~~bash
gradle dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Ghi lại **direct dependency** nào tạo đường đi tới Jackson, version được chọn và lý do selection. Sau đó kiểm tra liệu Jackson có được khai báo trực tiếp trong build.gradle hay không. Câu trả lời phải dựa trên graph thực tế, không dựa trên giả định rằng starter nào cũng có cùng dependency tree ở mọi phiên bản.

### Bài 2 — So sánh hai classpath

Chạy:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Tìm ít nhất hai thư viện test chỉ nằm ở testRuntimeClasspath. Giải thích tại sao kết quả classpath trong test không chứng minh production có cùng những class đó.

### Bài 3 — Kiểm chứng runtime version

Dùng **SpringBootVersion.getVersion()** trong ví dụ. So sánh với version plugin và artifact **org.springframework.boot:spring-boot** được chọn qua dependencyInsight. Nếu ba giá trị không đồng nhất, cần tìm nguyên nhân từ BOM, override, dependency conflict hoặc artifact thực tế đang chạy.

### Bài 4 — Dự đoán trước khi đổi starter

Dự đoán giá trị boolean của hai class **DispatcherServlet** và **ObjectMapper** sau khi thay starter-web bằng starter. Chạy lại và đối chiếu với runtimeClasspath. Nếu kết quả khác dự đoán, tìm dependency nào đã cung cấp class.

### Bài 5 — Tìm nguyên nhân bean vắng mặt

Giả sử một service không có một bean Jackson được kỳ vọng. Hãy chia quá trình kiểm tra thành hai nửa: **dependency graph có ObjectMapper không?** và **condition report cho biết Jackson auto-configuration có match không?** Trả lời được hai câu này trước khi quyết định viết bean tùy chỉnh.

## 12. Checklist hoàn thành

- [ ] Phân biệt được dependency trực tiếp và dependency bắc cầu bằng ví dụ từ runtimeClasspath.
- [ ] Biết các vai trò chính của implementation, api, runtimeOnly, compileOnly và testImplementation.
- [ ] Giải thích được vì sao starter web mang Spring MVC/Jackson vào project dù build.gradle không khai báo trực tiếp từng artifact.
- [ ] Dùng được **dependencies** và **dependencyInsight** để xác nhận đường đi và version đã chọn.
- [ ] Phân biệt được version Boot Gradle plugin, BOM, resolved Boot artifact và SpringBootVersion runtime.
- [ ] Không nhầm Spring Framework version, JDK version hoặc Gradle version với Spring Boot version.
- [ ] Kiểm tra được BOOT-INF/lib của executable JAR khi cần xác nhận artifact đóng gói.
- [ ] Dự đoán và kiểm tra được sự thay đổi classpath khi đổi direct dependency.
- [ ] Giải thích được vì sao classpath có thể khiến một điều kiện auto-configuration match hoặc không match.
- [ ] Biết kết hợp dependencyInsight với Condition Evaluation Report khi chẩn đoán một bean bị thiếu.

## Kết luận

**Dependency trực tiếp** là những thứ ứng dụng khai báo. **Dependency bắc cầu** là những thứ các dependency khác kéo vào. **Phiên bản thực sự đang dùng** được xác định bởi dependency resolution của đúng runtimeClasspath và những artifact ứng dụng thật sự nạp hoặc đóng gói, chứ không chỉ bởi một số version được viết trong build.gradle.

Đối với Spring Boot auto-configuration, hiểu dependency graph là bước nền tảng: classpath quyết định một phần điều kiện có thể thỏa mãn; condition report giải thích vì sao bean được hoặc không được tạo. Làm chủ hai nguồn bằng chứng này giúp chẩn đoán cấu hình nhanh, tránh chỉnh dependency theo cảm tính và giữ các ứng dụng Boot nhất quán khi nâng cấp thư viện.
