# Vai trò của pom.xml, settings.gradle và build.gradle trong dự án Spring Boot

## 1. Bức tranh tổng quan

Khi khởi tạo một dự án Spring Boot, ta thường chọn **Maven** hoặc **Gradle** làm công cụ build. Công cụ build chịu trách nhiệm tìm và tải thư viện, biên dịch Java, chạy kiểm thử, đóng gói ứng dụng và cung cấp lệnh chạy trong lúc phát triển. Ba tên tệp thường gặp có vai trò khác nhau:

| Tệp | Thuộc công cụ | Vai trò chính |
| --- | --- | --- |
| **pom.xml** | Maven | Mô tả dự án (Project Object Model): tọa độ artifact, Java, thư viện, plugin, cấu hình build và đóng gói. |
| **settings.gradle** | Gradle (Groovy DSL) | Khởi tạo cấu trúc build: tên dự án gốc, danh sách subproject; có thể cấu hình nơi tìm plugin và chính sách kho thư viện. |
| **build.gradle** | Gradle (Groovy DSL) | Cấu hình cách từng project được build: plugin, dependency, Java toolchain, repository, task, test và packaging. |

**Phân biệt quan trọng:** Một dự án dùng Maven thường có **pom.xml**. Một dự án dùng Gradle thường có **settings.gradle** và **build.gradle**. Đây là **hai hệ thống build thay thế nhau**; không cần tạo đủ ba tệp cho một ứng dụng. Nếu một repository cố ý hỗ trợ cả Maven lẫn Gradle thì mỗi hệ thống có cấu hình độc lập, không tự đồng bộ dependency hay task.

Trong bài này, ví dụ Spring Boot **3.3.5** và **Java 17** chỉ là một bộ phiên bản minh họa nhất quán. Khi tạo dự án thực tế, chọn các phiên bản tương thích từ Spring Initializr và kiểm tra phiên bản wrapper của Maven/Gradle.

## 2. Vị trí tệp khi khởi tạo dự án

Hai dự án ví dụ có cùng mã Java nhưng khác bộ tệp build:

~~~text
demo-maven/
├── pom.xml
├── mvnw / mvnw.cmd
├── .mvn/wrapper/...
└── src/
    └── main/java/com/example/demo/DemoApplication.java

demo-gradle/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
├── gradle/wrapper/...
└── src/
    └── main/java/com/example/demo/DemoApplication.java
~~~

- **src/main/java** chứa mã ứng dụng; **src/main/resources** chứa cấu hình như application.properties hoặc application.yml; **src/test/java** chứa test. Hai hệ build đều nhận diện cấu trúc này theo quy ước.
- **Maven Wrapper (mvnw)** và **Gradle Wrapper (gradlew)** giúp chạy bản công cụ do dự án quy định, hạn chế khác biệt giữa máy cá nhân và CI. Trên Windows dùng **mvnw.cmd** hoặc **gradlew.bat**; trên macOS/Linux dùng **./mvnw** hoặc **./gradlew**.
- Thư mục **target/** (Maven) và **build/** (Gradle) là sản phẩm sinh ra khi build, không phải nơi viết mã nguồn.

Spring Initializr cho phép chọn Maven hay Gradle rồi sinh sẵn cấu trúc tương ứng. Kiểm tra các tệp build ngay sau khi giải nén giúp biết chính xác lệnh nào phải dùng.

## 3. pom.xml: bản mô tả dự án đối với Maven

Maven đọc **pom.xml** để tạo mô hình dự án và biết cần thực hiện gì trong từng pha của build lifecycle. Ba thành phần **groupId**, **artifactId** và **version** định danh artifact, ví dụ com.example:demo-maven:0.0.1-SNAPSHOT.

Một **pom.xml hoàn chỉnh, tối thiểu** cho ứng dụng web Spring Boot:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-maven</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Các phần cần hiểu:

1. **parent**: Spring Boot starter parent thừa kế cấu hình Maven hữu ích, trong đó có dependency management và plugin management. Vì vậy hai starter trong ví dụ không cần khai báo version riêng.
2. **properties/java.version**: khai báo phiên bản Java mục tiêu theo quy ước của Spring Boot parent; máy build vẫn cần một JDK tương thích.
3. **dependencies**: mô tả thư viện ứng dụng cần. spring-boot-starter-web cung cấp các thành phần để viết web/API; spring-boot-starter-test dành cho test nhờ scope test. Maven sẽ giải quyết cả dependency bắc cầu.
4. **build/plugins**: spring-boot-maven-plugin thêm mục tiêu hỗ trợ chạy và đóng gói Spring Boot; với starter parent, goal **repackage** được gắn vào chu trình package để tạo JAR chạy bằng java -jar.
5. **packaging**: nếu không khai báo, Maven mặc định là jar. Có thể đặt **war** nếu dự án thực sự cần WAR và cấu hình tương ứng.

Maven có các pha lifecycle liên tiếp, chẳng hạn **compile → test → package → verify**. Lệnh gọi pha phía sau sẽ thực hiện các pha cần thiết ở trước. Một số thao tác thực tế (chạy tại thư mục demo-maven):

~~~bash
./mvnw clean verify
./mvnw spring-boot:run
java -jar target/demo-maven-0.0.1-SNAPSHOT.jar
~~~

Lệnh đầu xóa sản phẩm build cũ, biên dịch, chạy test, đóng gói và đi qua pha verify. Lệnh thứ hai chạy trực tiếp trong môi trường phát triển; lệnh thứ ba chạy artifact đã được đóng gói bằng plugin Spring Boot. Trên Windows thay **./mvnw** bằng **mvnw.cmd**. Nếu không có wrapper, dùng **mvn** đã cài phù hợp trên máy.

**Maven BOM và quản lý phiên bản:** Dependency management do Spring Boot parent cung cấp giúp các thư viện trong hệ sinh thái Boot dùng bộ phiên bản đồng bộ. Không nên tự gắn version khác cho từng starter khi chưa có lý do rõ ràng. Dự án không dùng starter parent vẫn có thể import BOM **spring-boot-dependencies** trong phần dependencyManagement và tự cấu hình plugin; đó là một cách tổ chức khác.

## 4. settings.gradle: khai báo *những project nào* thuộc build Gradle

Gradle có các giai đoạn chính là **initialization → configuration → execution**. Trong initialization, Gradle đọc **settings.gradle** trước các build script để xác định project gốc và các project thành viên.

Đối với ứng dụng Spring Boot một module, nội dung có thể chỉ cần:

~~~groovy
rootProject.name = 'demo-gradle'
~~~

Dòng này đặt tên dự án gốc, góp phần xác định tên artifact mặc định. **settings.gradle không phải nơi chính để khai báo các dependency ứng dụng hay các task compile/test.** Với bản Gradle mới, settings còn có thể chứa **pluginManagement { ... }** (nguồn và cách phân giải plugin) và **dependencyResolutionManagement { ... }** (chính sách repository, version catalog), nhưng các cấu hình đó chỉ thêm khi cần.

Với build nhiều module, nội dung settings.gradle có thể là:

~~~groovy
rootProject.name = 'learning-app'
include 'api', 'core'
~~~

Điều này thông báo rằng Gradle có ba project: gốc **learning-app**, **:api** và **:core**. Mỗi subproject thường có build.gradle riêng, ví dụ:

~~~text
learning-app/
├── settings.gradle
├── build.gradle
├── api/build.gradle
└── core/build.gradle
~~~

**include không tự tạo quan hệ phụ thuộc.** Nếu module api sử dụng code của core, build.gradle trong api phải khai báo dependency thích hợp, chẳng hạn đoạn minh họa sau:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Đoạn trên là **một phần** của build.gradle trong module api, không phải toàn bộ build script có thể chạy độc lập. Nếu module core là thư viện Java thông thường, nó thường dùng plugin **java-library**, không cần áp dụng Spring Boot plugin cho mọi module.

## 5. build.gradle: mô tả *mỗi project được build thế nào*

**build.gradle** dùng Groovy DSL để cấu hình plugin, task, repositories, dependency, Java version và quy tắc build của project tương ứng. Đây là **build.gradle hoàn chỉnh, tối thiểu** cho ví dụ demo-gradle (đi cùng settings.gradle một module bên trên):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
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

Ý nghĩa của từng khối:

- **plugins**: plugin java cung cấp việc compile, test, tạo JAR; Spring Boot plugin cung cấp **bootRun**, **bootJar** và hành vi packaging của Boot; plugin io.spring.dependency-management cho phép import BOM tương thích khi đi cùng Spring Boot plugin.
- **group/version**: xác định metadata và phiên bản artifact. Tên project mặc định lấy từ settings.gradle.
- **java.toolchain**: yêu cầu toolchain Java 17 cho các task Java. Cần có JDK phù hợp hoặc cấu hình Gradle để tự tải toolchain khi môi trường hỗ trợ.
- **repositories**: mavenCentral() là nơi Gradle tìm dependency ứng dụng. Kho tìm **plugin** có thể được cấu hình riêng trong settings.gradle.
- **dependencies**: implementation là dependency dùng cho mã ứng dụng; testImplementation dùng cho mã kiểm thử. Bộ phiên bản của Spring Boot được quản lý bởi BOM thông qua cấu hình plugin đã nêu.
- **tasks.named('test')**: bật JUnit Platform để chạy JUnit 5 với cấu hình test trong ví dụ.

Khi thực thi một task, Gradle xây dựng task graph và chạy các task phụ thuộc cần thiết. Các lệnh thông dụng (trong thư mục demo-gradle):

~~~bash
./gradlew clean build
./gradlew bootRun
java -jar build/libs/demo-gradle-0.0.1-SNAPSHOT.jar
~~~

**build** sẽ gọi các phần cần thiết như biên dịch, test và assemble. Với cấu hình Spring Boot ở trên, **bootJar** tạo executable JAR có thể chạy bằng java -jar. Gradle có thể tạo thêm **demo-gradle-0.0.1-SNAPSHOT-plain.jar** từ task jar thông thường; file **-plain.jar** không chứa bộ launcher/dependency dạng executable Boot JAR nên không dùng thay cho bootJar. Trên Windows dùng **gradlew.bat**.

Tương đương Kotlin DSL là **settings.gradle.kts** và **build.gradle.kts**; chúng dùng cú pháp Kotlin, không thể sao chép nguyên đoạn Groovy trên sang .kts.

## 6. Ví dụ chung: cùng một ứng dụng chạy bằng Maven hoặc Gradle

Để kiểm chứng hai cấu hình ở mục 3 và 5, tạo file:

**src/main/java/com/example/demo/DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class GreetingController {
        @GetMapping("/hello")
        public String hello() {
            return "Hello Spring Boot";
        }
    }
}
~~~

Đây là **file Java hoàn chỉnh**, dùng được trong **một trong hai** dự án ví dụ. Annotation **@SpringBootApplication** bật auto-configuration và component scan trong package của ứng dụng; controller lồng bên trong được phát hiện, cung cấp endpoint HTTP GET /hello. Sau khi chạy bằng **spring-boot:run** hoặc **bootRun**, truy cập:

~~~bash
curl http://localhost:8080/hello
~~~

Body của HTTP response:

~~~text
Hello Spring Boot
~~~

Muốn chạy JAR thì thực hiện lệnh build trước, rồi dùng đúng đường dẫn JAR executable đã nêu cho Maven hoặc Gradle. Ví dụ này yêu cầu JDK phù hợp, tải được dependency từ repository và cổng 8080 đang rảnh; không khẳng định toàn bộ log khởi động sẽ giống nhau trên mọi môi trường.

## 7. Maven và Gradle xử lý multi-module khác nhau

| Câu hỏi | Maven | Gradle |
| --- | --- | --- |
| Danh sách module? | Trong **pom.xml** của aggregator, khai báo **modules/module**; aggregator thường có packaging pom. | Trong **settings.gradle**, khai báo **include**. |
| Mỗi module cấu hình ở đâu? | **pom.xml** riêng của từng module. | **build.gradle** riêng của từng subproject; cấu hình chung có thể đặt tại build gốc hay convention plugin. |
| Quan hệ phụ thuộc module? | Module sử dụng phải khai báo dependency theo tọa độ Maven của module kia. | Module sử dụng khai báo project dependency, ví dụ **implementation project(':core')**. |
| Thực thi build? | Maven reactor xác định thứ tự xây dựa trên quan hệ dependency. | Gradle tạo task graph theo dependency và task được yêu cầu. |

Ví dụ **đoạn XML minh họa** trong POM aggregator Maven (không phải một file pom.xml đầy đủ):

~~~xml
<packaging>pom</packaging>
<modules>
    <module>api</module>
    <module>core</module>
</modules>
~~~

Như với Gradle include, việc liệt kê module Maven không tự có nghĩa là module api phụ thuộc core. Việc dự án có nhiều module cũng không bắt buộc mọi module đều phải là ứng dụng Spring Boot: module thư viện có thể xuất JAR thường, còn module khởi chạy Boot xuất executable JAR.

## 8. Build và packaging: phân biệt JAR thường với Spring Boot executable JAR

1. **Biên dịch** chuyển .java thành .class, nhưng chỉ biên dịch chưa tạo ứng dụng độc lập chạy bằng java -jar.
2. **Thử nghiệm** chạy test theo cấu hình. Maven pha package và Gradle task build thường bao gồm bước test; cố ý bỏ qua test có thể che lỗi nên không lấy đó làm mặc định.
3. **Đóng gói** gom class/resources thành artifact. Spring Boot packaging thường bổ sung loader và thư viện phụ thuộc để executable JAR chạy được trên máy có Java phù hợp.
4. **Chạy** dùng java -jar đối với executable JAR. Trong lúc phát triển, Maven **spring-boot:run** và Gradle **bootRun** tiện hơn khi cần chạy từ source.

| Nhu cầu | Maven Wrapper | Gradle Wrapper |
| --- | --- | --- |
| Xóa kết quả build cũ | **./mvnw clean** | **./gradlew clean** |
| Chạy test | **./mvnw test** | **./gradlew test** |
| Build có test | **./mvnw clean verify** | **./gradlew clean build** |
| Chạy ứng dụng từ source | **./mvnw spring-boot:run** | **./gradlew bootRun** |
| Kiểm tra dependency | **./mvnw dependency:tree** | **./gradlew dependencies --configuration runtimeClasspath** |
| Xem cấu trúc build | **./mvnw help:effective-pom** (POM hiệu lực) | **./gradlew projects** (project được include) |

Tên artifact phụ thuộc vào cấu hình tên/version/classifier. Mặc định ví dụ Maven ở trên tạo **target/demo-maven-0.0.1-SNAPSHOT.jar**; ví dụ Gradle dùng **build/libs/demo-gradle-0.0.1-SNAPSHOT.jar** cho Boot JAR. Khi đổi artifactId, rootProject.name hay version, tên tệp có thể đổi.

Nếu cần **WAR**, Maven dùng packaging war kèm cấu hình dependency/container phù hợp; Gradle áp dụng plugin war và xét task **bootWar**. Không nên chuyển sang WAR chỉ vì dùng Spring Boot: executable JAR thường là lựa chọn đơn giản cho dịch vụ độc lập.

## 9. Những lỗi thường gặp và cách tìm nguyên nhân

**Lỗi 1 — Đặt dependency trong settings.gradle rồi mong build.gradle tự nhận.** settings.gradle chủ yếu xác định cấu trúc và chính sách phân giải. Dependency trực tiếp của ứng dụng phải đặt trong cấu hình dependency của project thích hợp (hoặc cơ chế chia sẻ cấu hình đã chủ động thiết kế).

**Lỗi 2 — Có include ':core' nhưng api vẫn không import được class của core.** include chỉ đưa core vào build. Phải khai báo dependency **project(':core')** trong api và đảm bảo core áp dụng plugin Java phù hợp để xuất artifact.

**Lỗi 3 — Viết cả pom.xml và build.gradle rồi sửa một bên, mong bên kia tự cập nhật.** Maven và Gradle có quy tắc quản lý dependency/plugin riêng. Xác định công cụ build chính từ wrapper và lệnh CI của dự án.

**Lỗi 4 — Thiếu kho dependency hoặc dùng phiên bản plugin/JDK không tương thích.** Kiểm tra **repositories**, nơi phân giải plugin, **java -version**, phiên bản Gradle wrapper và phiên bản Spring Boot. Đừng suy luận lỗi mạng thành lỗi cú pháp build.

**Lỗi 5 — Chạy nhầm plain JAR hoặc không chạy bước đóng gói.** Với Gradle, ưu tiên output của **bootJar** cho java -jar; với Maven, kiểm tra **spring-boot-maven-plugin** và executable JAR sau package. Nếu dùng JAR thư viện thường, nó có thể thiếu launcher hoặc dependency cần cho một ứng dụng Spring Boot độc lập.

**Lỗi 6 — Thư mục source hoặc package/class chính sai.** Class có main phải biên dịch được; khai báo package cần khớp đường dẫn thông dụng. Trong ví dụ, class **com.example.demo.DemoApplication** nằm dưới **com/example/demo/**, có annotation @SpringBootApplication và main hợp lệ.

**Lỗi 7 — Dùng cú pháp Groovy trong build.gradle.kts.** File .gradle.kts là Kotlin DSL: khai báo string, plugin và cấu hình khác cú pháp. Trước khi sao chép snippet, kiểm tra đuôi file.

**Lỗi 8 — Nhầm build thành deployment.** pom.xml/build.gradle mô tả sản phẩm và cách build; chúng không tự quyết định ứng dụng sẽ chạy ở server, Docker hay Kubernetes. Dockerfile, cấu hình runtime và pipeline triển khai là những bước kế tiếp, ngoài trách nhiệm cốt lõi của ba tệp.

## 10. Cách tự kiểm tra sau khi khởi tạo

1. Chọn **Maven** hoặc **Gradle** trên Spring Initializr; xem có đúng pom.xml hoặc cặp settings.gradle/build.gradle.
2. Mở tệp để xác định **tên project/artifact, Java version, Spring Boot version, dependency và plugin**.
3. Tạo DemoApplication.java như ví dụ, dùng wrapper chạy test/build và quan sát thư mục **target/** hoặc **build/libs/**.
4. Chạy bằng lệnh dành cho công cụ đã chọn; gọi **GET /hello** và đối chiếu body trả về.
5. Nếu chuyển sang nhiều module, xác định **nơi khai báo module** và **nơi khai báo dependency giữa module**; đây là hai trách nhiệm khác nhau.

**Ghi nhớ:** **pom.xml** mô tả cách Maven xây dự án; **settings.gradle** cho Gradle biết những project nào tham gia một build; **build.gradle** mô tả plugin, dependency và task của các project ấy. Hiểu đúng ranh giới này giúp đọc được cấu trúc dự án Spring Boot, sửa lỗi khởi tạo và chọn đúng lệnh build/package.