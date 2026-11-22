# Spring Boot build plugin và vai trò đóng gói lại

Một dự án Spring Boot có thể biên dịch thành công nhưng file JAR tạo ra vẫn không chạy được bằng lệnh `java -jar`. Nguyên nhân thường nằm ở sự khác nhau giữa **JAR Java thông thường** và **executable archive** mà Spring Boot tạo bằng build plugin.

Spring Boot cung cấp plugin cho Maven và Gradle để hỗ trợ chạy, kiểm thử hoặc đóng gói ứng dụng. Trong đó, vai trò nổi bật nhất ở bước phát hành là **đóng gói lại (repackage)**: tổ chức class của ứng dụng, resource, thư viện phụ thuộc và Spring Boot loader thành một archive có thể tự chạy.

Hiểu ranh giới giữa compile, package và repackage giúp tránh nhầm lẫn về file artifact, classpath, manifest, dependency scope cũng như cách chạy ứng dụng trong server hoặc container.

## 1. Build plugin giải quyết vấn đề gì?

Một ứng dụng Spring Boot không chỉ có class của dự án. Nó thường cần nhiều thư viện: Spring Framework, embedded server, JSON mapper, database driver, logging và những dependency khác.

Khi dùng Java JAR thông thường, thao tác đóng gói chỉ đưa các class và resource của project vào archive. Những JAR phụ thuộc vẫn nằm bên ngoài và cần được cung cấp đúng classpath khi chạy.

Spring Boot build plugin hỗ trợ tạo một archive thuận tiện hơn:

- Đóng gói class và resource của ứng dụng.
- Đưa các runtime dependencies phù hợp vào archive.
- Thêm thành phần **Spring Boot loader** để nạp những JAR lồng bên trong.
- Tạo manifest mô tả launcher và main class của ứng dụng.
- Hỗ trợ executable JAR hoặc executable WAR tùy loại ứng dụng.
- Có thể bổ sung metadata về các layer để xây dựng container image hiệu quả hơn.

Quá trình build vẫn do Maven hoặc Gradle điều phối. Plugin không thay thế compiler, test runner hay dependency resolution; nó sử dụng kết quả của các bước đó để tạo một artifact Spring Boot có thể khởi động.

## 2. Phân biệt JAR thông thường và executable Spring Boot JAR

Một JAR Java thông thường có thể trông như sau:

~~~text
catalog-service.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        ├── CatalogApplication.class
        └── service/
            └── CatalogService.class
~~~

Nếu các thư viện Spring nằm ngoài JAR, lệnh `java -jar catalog-service.jar` sẽ không tự tìm thấy chúng. Tùy cách build manifest và classpath, ứng dụng có thể báo thiếu main class, thiếu dependency hoặc không có entry point.

Executable JAR được Spring Boot đóng gói lại thường có cấu trúc:

~~~text
catalog-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/CatalogApplication.class
    │   └── application.yml
    ├── lib/
    │   ├── spring-boot-....jar
    │   ├── spring-context-....jar
    │   └── các-runtime-dependency-khác.jar
    ├── classpath.idx                (nếu được tạo)
    └── layers.idx                   (nếu được tạo)
~~~

Từ cấu trúc này:

- `BOOT-INF/classes/` chứa code và resource của ứng dụng.
- `BOOT-INF/lib/` chứa các dependency JAR cần thiết.
- `org/springframework/boot/loader/` chứa các lớp khởi chạy và hỗ trợ nạp nested JAR.
- `META-INF/MANIFEST.MF` cho Java biết entry point của archive.

Tên file phụ thuộc vào version và danh sách dependency thực tế; cấu trúc trên chỉ minh họa các nhóm thành phần.

Một executable JAR không đơn giản là “gộp nội dung tất cả dependency vào cùng thư mục package”. Spring Boot thường giữ các dependency dưới dạng **nested JAR** và dùng loader để nạp chúng.

## 3. Spring Boot loader và manifest hoạt động ra sao?

Java launcher thông thường đọc `Main-Class` trong manifest để tìm điểm bắt đầu chương trình. Với executable Spring Boot JAR, `Main-Class` thường trỏ tới **Spring Boot launcher**, trong khi main class ứng dụng được ghi ở `Start-Class`.

Ví dụ manifest minh họa cho một phiên bản Spring Boot hiện đại:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.CatalogApplication
Spring-Boot-Version: <spring-boot-version>
~~~

`Start-Class` là lớp có phương thức `public static void main(String[] args)` của ứng dụng:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Khi chạy:

~~~bash
java -jar catalog-service.jar
~~~

trình tự khái quát là:

~~~text
java -jar catalog-service.jar
            |
            v
JVM đọc META-INF/MANIFEST.MF
            |
            v
Chạy Spring Boot JarLauncher
            |
            v
Thiết lập classpath từ BOOT-INF/classes và BOOT-INF/lib
            |
            v
Nạp Start-Class
            |
            v
CatalogApplication.main(args)
            |
            v
SpringApplication.run(...)
~~~

Tên đầy đủ của launcher có thể khác giữa các thế hệ Spring Boot. Ví dụ, một số phiên bản cũ dùng `org.springframework.boot.loader.JarLauncher`, còn các phiên bản mới đặt launcher trong package `org.springframework.boot.loader.launch`. Không nên tự sửa manifest theo ví dụ này; build plugin sẽ chọn launcher tương thích với phiên bản Spring Boot đang dùng.

### Vì sao cần Spring Boot launcher?

Java classpath thông thường không tự coi mọi file `.jar` nằm **bên trong** một JAR khác là classpath entry. Boot loader hỗ trợ đọc các dependency lồng nhau theo layout được Spring Boot định nghĩa.

Nếu bỏ loader nhưng vẫn giữ các dependency trong `BOOT-INF/lib`, JVM thông thường có thể không tìm được các lớp của Spring. Ngược lại, nếu chạy một JAR không được đóng gói lại bằng launcher của Boot, không thể mặc định nó có cùng layout.

Vì vậy, **Spring Boot loader là một phần chức năng của executable archive**, không chỉ là metadata trang trí.

## 4. Maven: spring-boot-maven-plugin và repackage

Với Maven, Spring Boot cung cấp:

~~~text
org.springframework.boot:spring-boot-maven-plugin
~~~

Goal chính cho quá trình tạo executable archive là:

~~~text
spring-boot:repackage
~~~

Maven thực hiện những phase như `compile`, `test`, `package`. Goal `repackage` của plugin được dùng **sau khi** Maven đã tạo JAR/WAR thông thường, rồi đóng gói lại artifact đó theo layout của Spring Boot.

Ví dụ POM sử dụng Spring Boot parent:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version><!-- Phiên bản Spring Boot của dự án --></version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-service</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong ví dụ này, trường `version` của parent phải được thay bằng phiên bản có thật, nhất quán với dự án. Phần lớn project Maven dùng starter parent được quản lý cấu hình plugin và execution `repackage` phù hợp.

Build:

~~~bash
mvn clean package
~~~

Khi execution của `repackage` đã được gắn với lifecycle, Maven tạo JAR và plugin biến nó thành executable Spring Boot JAR. Kết quả thường nằm trong `target/`:

~~~text
target/
├── catalog-service-1.0.0.jar
└── catalog-service-1.0.0.jar.original
~~~

File `.jar` là executable archive đã được đóng gói lại. File `.jar.original` là JAR ban đầu do Maven tạo trước khi repackage, khi plugin thay thế artifact chính theo cấu hình mặc định.

Tên file và việc giữ artifact gốc có thể khác nếu dự án cấu hình `classifier`, `attach` hoặc cách đóng gói riêng. Không nên dùng hậu tố `.original` như một yêu cầu tuyệt đối cho mọi project.

### Maven không dùng Spring Boot parent

Nếu dự án dùng parent POM riêng, việc chỉ khai báo plugin **không đảm bảo** goal `repackage` tự được gắn vào `package`. Có thể cần khai báo execution tường minh:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version><!-- Phiên bản phù hợp với Spring Boot --></version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Ở ví dụ này, các chỗ chứa comment phiên bản là placeholder cần thay trong một POM thực tế. Execution của goal `repackage` có thể được gắn với phase `package` theo default của goal; nếu cấu hình tùy biến, cần xác định phase/execution thật sự.

Có thể gọi goal thủ công:

~~~bash
mvn package spring-boot:repackage
~~~

Tuy nhiên, với pipeline thường xuyên build, cấu hình execution nhất quán trong POM sẽ dễ duy trì hơn so với phụ thuộc vào việc người chạy lệnh nhớ bổ sung goal mỗi lần.

## 5. Vai trò của repackage trong Maven lifecycle

Cần phân biệt hai bước:

~~~text
mvn package
      |
      v
Maven compiler/test/resource processing
      |
      v
maven-jar-plugin hoặc maven-war-plugin
      |
      v
Artifact JAR/WAR thông thường
      |
      v
spring-boot:repackage (nếu được bind)
      |
      v
Executable Spring Boot JAR/WAR
~~~

`repackage` **không thay thế compilation**. Nó nhận kết quả package và tổ chức lại archive, thêm loader, nested dependencies và manifest.

Nếu build báo lỗi không tìm thấy main class, phải xác định lớp chứa `main()` và cấu hình main class cho plugin. Nếu build chưa tạo được artifact gốc, repackage không thể tự tạo lại các class chưa được biên dịch.

### Chỉ định main class khi cần

Trong project có nhiều main class, có thể khai báo:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.CatalogApplication</mainClass>
    </configuration>
</plugin>
~~~

Nếu chỉ có một main class rõ ràng, plugin thường có thể suy ra. Với nhiều entry point hoặc cấu trúc multi-module phức tạp, việc khai báo tường minh giúp tránh chọn nhầm class.

### Có thể bỏ qua repackage không?

Maven plugin có tùy chọn `skip` dành cho những tình huống không muốn chạy goal `repackage`. Khi đó artifact có thể chỉ là archive thông thường do Maven tạo.

Không nên tắt repackage rồi vẫn phát hành file như một executable Spring Boot JAR, trừ khi build sử dụng cách đóng gói và classpath khác được thiết kế riêng.

## 6. Gradle: spring-boot-gradle-plugin và bootJar

Với Gradle, Spring Boot plugin được khai báo bằng plugin ID:

~~~text
org.springframework.boot
~~~

Ví dụ Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Thay `<spring-boot-version>` bằng phiên bản của project. Nếu không dùng dependency management của plugin hoặc BOM, cần cấu hình quản lý version dependency tương ứng.

Khi dự án dùng Java plugin và Spring Boot plugin, task `bootJar` thường được tạo để đóng gói **executable JAR**.

~~~bash
./gradlew bootJar
~~~

Khác Maven `repackage` vốn xử lý một JAR/WAR đã được Maven tạo, Gradle `bootJar` là một archive task được cấu hình để tạo executable Spring Boot archive.

Luồng tư duy:

~~~text
Gradle compileJava + processResources
           |
           v
      class/resource output
           |
           v
         bootJar
           |
           v
   Executable Spring Boot JAR
~~~

### bootJar và jar khác nhau như thế nào?

Trong project Gradle sử dụng Spring Boot plugin, có thể có cả hai task:

- `jar`: tạo JAR Java thông thường từ output của project.
- `bootJar`: tạo executable Spring Boot JAR gồm loader và runtime dependencies.

Với cách cấu hình của nhiều phiên bản plugin Spring Boot, task `jar` được gắn classifier `plain` để tránh trùng tên với executable JAR:

~~~text
build/libs/
├── catalog-service-1.0.0.jar
└── catalog-service-1.0.0-plain.jar
~~~

Thông thường file không có classifier là executable artifact của `bootJar`, còn file `-plain.jar` là JAR thông thường.

Tuy vậy, **tên và classifier có thể được tùy chỉnh**; nên xác định file theo task tạo ra nó và manifest thực tế, không chỉ nhìn kích thước hay hậu tố.

Một ví dụ đặt tên rõ ràng:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'catalog-service-exec.jar'
}
~~~

Với Kotlin DSL:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("catalog-service-exec.jar")
}
~~~

Cấu hình này thay tên output của task `bootJar`, không thay tên class chính bên trong archive.

### bootRun khác bootJar

`bootRun` dùng để chạy ứng dụng qua Gradle từ project classpath, thường hữu ích trong phát triển:

~~~bash
./gradlew bootRun
~~~

`bootJar` tạo archive để triển khai:

~~~bash
./gradlew bootJar
java -jar build/libs/catalog-service-exec.jar
~~~

`bootRun` không phải thao tác repackage. Nó có thể dùng Spring Boot Devtools và classpath phù hợp với phát triển, trong khi executable JAR được tạo để vận hành độc lập bằng `java -jar`.

## 7. Spring Boot Gradle plugin và dependency classpath

Task `bootJar` cần các dependency runtime phù hợp để ứng dụng khởi chạy. Với Gradle, cách đặt dependency ảnh hưởng tới những gì có thể xuất hiện trong archive:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ý nghĩa:

| Gradle configuration | Vai trò tiêu biểu | Trong executable JAR |
|---|---|---|
| `implementation` | Thư viện code và runtime của ứng dụng | Thường được đưa vào |
| `runtimeOnly` | Thư viện chỉ cần khi chạy | Thường được đưa vào |
| `compileOnly` | Chỉ cần để biên dịch | Thường không đưa vào |
| `annotationProcessor` | Chạy lúc annotation processing | Không phải runtime dependency mặc định |
| `developmentOnly` | Dependency cho workflow phát triển khi plugin hỗ trợ | Không đóng gói theo `bootJar` tiêu chuẩn |
| `testImplementation` | Dependency cho test | Không phải runtime dependency của ứng dụng |

Ví dụ trên mang tính minh họa; mỗi dự án cần quản lý version cụ thể của dependency theo BOM hoặc dependency-management strategy.

Nếu driver database được khai báo `compileOnly` nhưng ứng dụng thực sự cần nó khi chạy, executable JAR có thể thiếu driver và báo `ClassNotFoundException` hoặc lỗi datasource. Đó là vấn đề **dependency scope**, không phải lỗi của Spring Boot loader.

Ngược lại, không nên đặt thư viện chỉ dùng cho test hoặc annotation processing vào runtime classpath chỉ để tránh lỗi build; việc ấy có thể làm tăng kích thước artifact và thay đổi hành vi khi khởi chạy.

## 8. Maven dependency scope ảnh hưởng tới artifact ra sao?

Maven phân biệt các scope như `compile`, `runtime`, `provided` và `test`.

Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong executable archive, plugin chọn các dependency theo quy tắc packaging của Spring Boot và cấu hình plugin. Không nên đánh đồng quy tắc đó với nội dung của một JAR Maven thuần.

Đặc biệt, `provided` có vai trò khác khi build executable WAR cho external servlet container. Cách Spring Boot đóng gói provided dependencies có thể phục vụ việc chạy archive executable nhưng tránh xung đột với container bên ngoài.

Đối với Devtools, Spring Boot Maven Plugin mặc định loại Devtools khỏi executable archive trong mô hình thông thường. Có thể cấu hình lại, nhưng production thường không nên mang theo hạ tầng restart dành cho phát triển.

## 9. Executable WAR và bootWar

Ngoài executable JAR, Spring Boot hỗ trợ executable WAR. WAR thường dùng khi ứng dụng cần có khả năng triển khai vào **external servlet container**, đồng thời có thể hỗ trợ chạy bằng `java -jar` khi được đóng gói theo layout Boot.

Với Gradle, khi áp dụng thêm `war` plugin, Spring Boot có task `bootWar`:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Trong một ứng dụng WAR thật, lớp main thường kế thừa `SpringBootServletInitializer` để external servlet container có thể khởi tạo ApplicationContext:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class CatalogApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(CatalogApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Build WAR bằng Gradle:

~~~bash
./gradlew bootWar
~~~

WAR của Spring Boot có thể gồm:

~~~text
catalog-service.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   └── lib-provided/
└── org/springframework/boot/loader/...
~~~

Ý nghĩa chính:

- `WEB-INF/classes/`: class và resource của ứng dụng.
- `WEB-INF/lib/`: các thư viện cần cho deployment vào servlet container.
- `WEB-INF/lib-provided/`: những dependency chỉ dùng để hỗ trợ chạy WAR theo cách executable mà không đưa vào classpath thông thường của external container.

Khi chạy WAR bằng `java -jar`, Boot launcher có thể sử dụng các thành phần cần thiết. Khi triển khai WAR vào một servlet container bên ngoài, container cung cấp servlet runtime của chính nó.

Nếu ứng dụng chỉ chạy bằng container image và embedded server của Spring Boot, executable JAR thường đơn giản hơn executable WAR. WAR phù hợp khi có yêu cầu triển khai vào external servlet container.

### Maven đóng gói WAR

Maven project có thể đặt:

~~~xml
<packaging>war</packaging>
~~~

Với servlet container được cung cấp từ bên ngoài, dependency container thường được đặt scope `provided` theo yêu cầu. `spring-boot:repackage` có thể xử lý WAR đã được Maven đóng gói và thêm loader để hỗ trợ cách chạy executable.

Điều quan trọng là lựa chọn JAR hay WAR xuất phát từ **mô hình deployment**, không phải vì WAR luôn tốt hơn JAR hoặc ngược lại.

## 10. Repackage không giống shading hay uber-JAR truyền thống

Có nhiều cách tạo một Java artifact chứa dependency:

| Cách | Cơ chế | Đặc điểm |
|---|---|---|
| JAR thường | Chứa class/resource của project | Dependency cần được cung cấp từ bên ngoài |
| Maven Shade/Gradle Shadow | Thường giải nén và gộp dependency classes vào archive | Có thể cần xử lý trùng resource, package relocation |
| Spring Boot executable JAR | Giữ dependency thành nested JAR dưới `BOOT-INF/lib` | Boot loader thiết lập classpath và khởi chạy ứng dụng |

Hai cách shade và repackage có thể phục vụ mục tiêu khác nhau. Nếu cùng áp dụng lên một artifact mà không hiểu layout, có thể tạo trùng class, hỏng resource hoặc làm manifest/launcher không còn đúng.

Với một ứng dụng Spring Boot thông thường, nên ưu tiên `bootJar` hoặc `spring-boot:repackage` thay vì tự dựng uber-JAR bằng cách giải nén mọi dependency.

Khi phát hành **thư viện** để project khác import, một JAR thường lại phù hợp hơn executable Boot JAR. Lý do là các class ứng dụng trong executable Boot archive nằm dưới `BOOT-INF/classes`, không ở vị trí classpath mà một thư viện JAR thông thường mong đợi.

## 11. Module thư viện và module ứng dụng nên đóng gói khác nhau

Một project multi-module có thể gồm:

~~~text
workspace/
├── common-domain/
├── catalog-data/
└── catalog-app/
~~~

Trong đó:

- `common-domain` cung cấp API và domain objects cho module khác.
- `catalog-data` chứa logic truy cập dữ liệu dùng chung.
- `catalog-app` có `@SpringBootApplication` và `main()` để chạy server.

Với mô hình này, module thư viện thường tạo **plain JAR**. Chỉ module ứng dụng cần **executable Spring Boot JAR**.

Ví dụ trong Gradle, plugin Boot có thể chỉ được áp dụng cho module ứng dụng. Nếu vì quy ước build buộc áp dụng plugin vào mọi module, có thể cần cấu hình tắt `bootJar` ở module thư viện và giữ `jar`, nhưng không nên thay đổi task graph khi chưa xác định mục đích đóng gói.

Một executable Boot JAR không phải lựa chọn tốt để làm dependency trực tiếp cho module khác: layout `BOOT-INF` được thiết kế cho loader khởi chạy, không phải để compiler Java tra class như library JAR bình thường.

### Maven classifier cho artifact khác nhau

Trong Maven, `repackage` có khả năng cấu hình `classifier` để tạo executable artifact bổ sung thay vì thay thế JAR chính.

Ví dụ minh họa:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

Với cấu hình phù hợp, output có thể gồm:

~~~text
catalog-service-1.0.0.jar
catalog-service-1.0.0-exec.jar
~~~

Nhờ vậy, một artifact có thể phục vụ vai trò thư viện, một artifact khác phục vụ chạy ứng dụng. Đây là tình huống đặc biệt; khi không có nhu cầu xuất bản cả hai loại artifact, không cần tăng độ phức tạp build.

## 12. Layered JAR: hỗ trợ cache khi build container image

Spring Boot có thể bổ sung thông tin phân lớp (*layers*) vào executable archive. Mục tiêu là chia nội dung theo tần suất thay đổi, để quá trình build image tận dụng cache hiệu quả hơn.

Các nhóm layer thường gặp:

~~~text
dependencies
spring-boot-loader
snapshot-dependencies
application
~~~

Ý nghĩa khái quát:

- `dependencies`: các dependency ít thay đổi.
- `spring-boot-loader`: thành phần loader của Spring Boot.
- `snapshot-dependencies`: dependency dạng snapshot, có thể thay đổi thường xuyên.
- `application`: class và resource của project.

Metadata có thể nằm trong:

~~~text
BOOT-INF/layers.idx
~~~

File này ghi nhận cách phân lớp, nhưng **JAR không tự biến thành container image** chỉ vì có `layers.idx`.

Các phiên bản Spring Boot có công cụ để xem hoặc trích xuất layer; cơ chế và cú pháp launch mode có thể thay đổi theo phiên bản. Nếu pipeline cần sử dụng layer metadata, hãy dùng công cụ và hướng dẫn tương ứng với version plugin đang chạy.

Layering hữu ích trong Docker image hoặc buildpacks vì phần dependency ổn định có thể dùng cache giữa các lần build, còn lớp application thay đổi khi sửa code. Nó không thay đổi bản chất Spring ApplicationContext hoặc Spring profile.

## 13. bootBuildImage khác với bootJar

Bên cạnh executable archive, Spring Boot Gradle plugin còn cung cấp task kiểu `bootBuildImage` để tạo OCI container image qua Cloud Native Buildpacks khi môi trường build đáp ứng yêu cầu.

~~~bash
./gradlew bootBuildImage
~~~

Tương ứng, Spring Boot Maven Plugin có goal build image, ví dụ:

~~~bash
mvn spring-boot:build-image
~~~

Hai bước cần phân biệt:

~~~text
bootJar / repackage
        |
        v
Executable Spring Boot archive
        |
        v
bootBuildImage / build-image (nếu được chọn)
        |
        v
OCI container image
~~~

Bước tạo image còn phụ thuộc môi trường container, builder, registry và các quyền cần thiết. Build image **không phải** nhiệm vụ bắt buộc của `repackage`, và một JAR chạy được bằng `java -jar` không tự động tạo ra Docker image.

Nếu sử dụng Dockerfile riêng, executable JAR có thể được copy vào image mà không cần task `bootBuildImage`; cách chọn tùy theo quy trình triển khai.

## 14. Cấu hình bên ngoài vẫn hoạt động với executable archive

Đóng gói lại không có nghĩa mọi cấu hình môi trường phải nhúng vào JAR. Spring Boot vẫn hỗ trợ externalized configuration.

Ví dụ build một lần:

~~~bash
./gradlew bootJar
~~~

Sau đó cùng executable JAR có thể được chạy ở hai môi trường:

~~~bash
java -jar build/libs/catalog-service.jar --spring.profiles.active=staging
~~~

~~~bash
java -jar build/libs/catalog-service.jar --spring.profiles.active=prod
~~~

Tên JAR thực tế phụ thuộc build configuration. Hai lệnh trên minh họa rằng **Spring profile quyết định cấu hình runtime**, không quyết định cách build plugin tổ chức archive.

Có thể cung cấp file cấu hình bên ngoài thông qua `./config/application.yml`, biến môi trường, command-line properties hoặc Config Data location/import phù hợp. Không nên tạo executable JAR khác nhau chỉ để đổi database URL, token hoặc logging level nếu cùng code và dependency.

Cần tránh đưa secret thật vào classpath resource đóng gói cùng ứng dụng. Archive có thể được sao chép hoặc tải xuống; dùng secret manager hay cơ chế cấu hình của nền tảng triển khai sẽ an toàn và dễ quản lý hơn.

## 15. Những lỗi thường gặp khi đóng gói

### no main manifest attribute

Nếu chạy:

~~~bash
java -jar catalog-service.jar
~~~

mà nhận lỗi dạng:

~~~text
no main manifest attribute, in catalog-service.jar
~~~

file JAR có thể là JAR thường chưa có `Main-Class` phù hợp. Hãy xác nhận có chạy `bootJar` hoặc Maven execution `repackage` hay không, và có đang chọn nhầm file `-plain.jar` hoặc `.jar.original` không.

### Could not find or load main class

Có thể do manifest chọn sai main class, entry point bị đổi package hoặc archive không chứa class ở vị trí mà launcher mong đợi.

Với project có nhiều `main()`, nên cấu hình main class tường minh cho build plugin.

Ví dụ Gradle:

~~~groovy
springBoot {
    mainClass = 'com.example.CatalogApplication'
}
~~~

Với Maven, dùng `<mainClass>com.example.CatalogApplication</mainClass>` trong cấu hình plugin.

### ClassNotFoundException hoặc NoClassDefFoundError khi chạy

Không nên chỉ nhìn thấy nested JAR là kết luận dependency đầy đủ. Một thư viện có thể đang được khai báo sai scope, bị exclude hoặc xung đột version.

Kiểm tra dependency runtime thực tế và nội dung `BOOT-INF/lib`. Ví dụ JDBC driver đặt `compileOnly` trong Gradle sẽ không được đưa vào runtime classpath theo cách mong muốn.

### Maven package tạo JAR nhưng không phải Spring Boot archive

Nếu không dùng `spring-boot-starter-parent` hoặc execution bị thay đổi, `repackage` có thể chưa được gắn với lifecycle. Xác nhận cấu hình Spring Boot Maven Plugin và goal `repackage`.

Chỉ có khai báo dependency `spring-boot-starter-web` **không tự biến** Maven JAR thường thành executable Boot JAR.

### Plugin báo không tìm thấy main class

Một project thư viện không có entry point có thể không phù hợp để chạy `bootJar` hoặc `repackage`. Hãy quyết định module đó cần plain JAR hay executable archive. Nếu là ứng dụng thực sự, xác nhận `@SpringBootApplication` class có `main()` và khai báo main class khi cần.

### JAR đóng gói được nhưng web server không khởi động

Packaging thành công không bảo đảm hạ tầng runtime đúng. Ứng dụng có thể thiếu server starter, sai datasource, cấu hình profile không đúng hoặc có bean startup failure.

Phân biệt lỗi archive/launcher với lỗi xảy ra sau khi `SpringApplication.run()` bắt đầu tạo ApplicationContext.

### Đóng gói quá nhiều dependency

Một executable JAR có thể lớn vì chứa toàn bộ runtime libraries. Không nên loại dependency mù quáng chỉ để giảm size: loại sai sẽ gây lỗi classpath. Hãy xem runtime dependency graph, scope và các thư viện thực sự cần.

Đối với container, layering và image cache thường giúp giảm thời gian triển khai hơn là cố giải nén rồi tối ưu JAR thủ công.

### Chạy JAR bằng -cp không giống java -jar

Lệnh `java -jar app.jar` cho launcher của Spring Boot cơ hội thiết lập classpath nested JAR theo manifest.

Không nên giả định `java -cp app.jar com.example.CatalogApplication` sẽ chạy giống hệt, vì class của ứng dụng nằm dưới `BOOT-INF/classes` và dependency ở `BOOT-INF/lib`. Nếu cần custom launcher hoặc custom classpath, phải hiểu layout của Spring Boot archive.

## 16. Kiểm tra artifact trước khi phát hành

Một nhóm bước xác nhận kỹ thuật hữu ích trong pipeline phát hành:

1. Xác định task/goal tạo artifact: `bootJar`, `bootWar` hay `spring-boot:repackage`.
2. Xác nhận đúng module có main class và đúng kiểu archive.
3. Kiểm tra file đầu ra và không nhầm executable archive với plain JAR.
4. Kiểm tra manifest, đặc biệt entry point của loader và `Start-Class`.
5. Kiểm tra dependency runtime quan trọng có mặt trong archive.
6. Chạy artifact bằng `java -jar` trong môi trường kiểm thử phù hợp.
7. Kiểm tra active profile và cấu hình bên ngoài được nạp đúng.
8. Quan sát startup logs, health endpoint và shutdown behavior.
9. Nếu dùng container, xác nhận image sử dụng đúng artifact và các layer phù hợp.
10. Chỉ phát hành artifact đã được kiểm thử, thay vì đóng gói khác đi cho từng môi trường mà không có lý do.

Ví dụ xem nội dung JAR bằng JDK `jar` tool:

~~~bash
jar tf build/libs/catalog-service.jar
~~~

Lệnh có thể liệt kê các đường dẫn như `BOOT-INF/classes/`, `BOOT-INF/lib/` và Spring Boot loader classes. Nó chỉ xác nhận cấu trúc archive, không tự chứng minh ứng dụng sẽ kết nối database hay nhận request thành công.

Trong môi trường thực tế, kết hợp kiểm tra archive với một smoke test khởi động sẽ có giá trị hơn việc chỉ so sánh kích thước file.

## 17. Quy trình chọn Maven hay Gradle plugin

Cả hai plugin đều giải quyết mục tiêu tạo executable Spring Boot artifact, nhưng gắn vào build tool theo cách khác nhau:

| Tiêu chí | Maven | Gradle |
|---|---|---|
| Plugin | `spring-boot-maven-plugin` | `org.springframework.boot` |
| Build lifecycle | Maven phases/goals | Gradle task graph |
| Đóng gói executable JAR | `spring-boot:repackage` sau bước package | Task `bootJar` |
| Đóng gói executable WAR | Repackage WAR | Task `bootWar` |
| Chạy từ project | `spring-boot:run` | `bootRun` |
| Artifact thường | JAR/WAR gốc | Task `jar` / `war` |
| Container image | Goal build-image | Task `bootBuildImage` |

Không cần dùng cả Maven lẫn Gradle trong cùng một module. Chọn build tool dựa trên tiêu chuẩn dự án, hệ thống CI, cấu trúc multi-module và công cụ team đang sử dụng.

Dù dùng build tool nào, Spring Boot version của plugin, framework và dependency cần được quản lý nhất quán; tránh trộn các phiên bản không tương thích khi khai báo thủ công.

## 18. Kết luận: repackage tạo ranh giới giữa code và artifact chạy được

Spring Boot build plugin không chỉ “nén project thành một file JAR”. Nó biến kết quả compilation và dependency resolution thành **executable archive** với layout, loader và manifest phù hợp.

Điểm cần nhớ:

- **JAR thường** chứa class/resource của module, không mặc định gom mọi runtime dependency.
- **Spring Boot executable JAR** có `BOOT-INF/classes`, `BOOT-INF/lib`, loader và manifest để chạy bằng `java -jar`.
- Với **Maven**, `spring-boot:repackage` xử lý JAR/WAR đã được package.
- Với **Gradle**, `bootJar`/`bootWar` trực tiếp tạo executable archive theo task model.
- **Dependency scope** quyết định những thư viện nào phục vụ runtime; task packaging không tự sửa dependency thiếu hoặc sai.
- **Spring profile** và externalized configuration vẫn là quyết định runtime, không phải công việc của repackage.
- **Layered JAR** có thể hỗ trợ tối ưu container image nhưng không đồng nghĩa đã tạo image.
- Module ứng dụng cần executable archive; module thư viện thường cần plain JAR.

Khi phân biệt rõ **biên dịch → đóng gói thường → đóng gói Spring Boot → chạy/triển khai**, bạn có thể chẩn đoán lỗi artifact chính xác hơn và xây dựng pipeline phát hành Spring Boot nhất quán, dễ vận hành.

