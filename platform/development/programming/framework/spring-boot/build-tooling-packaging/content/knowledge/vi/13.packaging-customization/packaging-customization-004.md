# Cấu hình manifest bổ sung mà vẫn giữ đúng điểm khởi động Spring Boot

## 1. Vấn đề: thêm metadata nhưng không làm hỏng executable JAR

Một ứng dụng Spring Boot sau khi đóng gói bằng Maven hoặc Gradle thường được chạy bằng **java -jar**. File JAR chứa **META-INF/MANIFEST.MF**, một tệp metadata mô tả archive và thông tin khởi động. Nhóm phát triển có thể muốn bổ sung:

- **Implementation-Title**: tên dịch vụ hoặc sản phẩm.
- **Implementation-Version**: phiên bản ứng dụng đang phát hành.
- **Build-Revision**: mã commit/build revision để truy vết.
- **Build-Channel**: ví dụ **training**, **staging** hoặc **release**.
- **Built-By-Team**: tên nhóm chịu trách nhiệm tạo artifact.

Nhu cầu đó hợp lý, nhưng Spring Boot executable JAR **khác JAR Java thông thường**. Nếu chỉnh sai **Main-Class** hoặc **Start-Class**, file vẫn có đuôi **.jar**, vẫn có manifest, thậm chí vẫn chứa đủ class, nhưng **java -jar có thể không khởi động được**.

Quy tắc an toàn của bài:

1. Để **Spring Boot packaging plugin quản lý phần launcher** của executable archive.
2. Chỉ thêm các manifest attributes **không xung đột** với thuộc tính mà Spring Boot loader cần.
3. Nếu phải chỉ định entry point, dùng **Spring Boot Maven Plugin mainClass** hoặc **Gradle springBoot.mainClass / bootJar.mainClass**.
4. **Build, đọc manifest cuối cùng và chạy JAR thật** sau khi thêm metadata; không kết luận đúng chỉ vì POM/build.gradle có cấu hình mong muốn.

Bài dùng **Spring Boot 3.3.5**, Java **17**, Maven và Gradle Groovy DSL (**Gradle 8.5**) để minh họa. Các phiên bản là ví dụ thực hành có chủ đích, không khẳng định là mới nhất. Với Spring Boot 4 hoặc phiên bản loader khác, phải kiểm tra tên launcher của chính phiên bản đang dùng.

## 2. META-INF/MANIFEST.MF là gì?

JAR là tệp ZIP có cấu trúc chuẩn. Manifest thường nằm tại:

~~~text
META-INF/MANIFEST.MF
~~~

Một đoạn manifest đơn giản:

~~~text
Manifest-Version: 1.0
Implementation-Title: manifest-demo
Implementation-Version: 1.0.0
Build-Channel: training
Build-Revision: lesson-149
~~~

Nội dung trên chỉ thể hiện một số thuộc tính metadata. Nó **chưa đủ** để làm executable Spring Boot archive. Các header khởi động sẽ được trình bày ở phần sau.

Manifest là định dạng có quy tắc riêng: mỗi attribute có **tên**, dấu hai chấm, khoảng trắng và **giá trị**, các section phân cách bằng dòng trống. Dòng quá dài có thể được **gấp thành nhiều dòng vật lý** với một dấu cách ở đầu dòng tiếp theo. Vì vậy, khi kiểm tra giá trị dài, cách đáng tin cậy hơn là dùng **java.util.jar.Manifest** thay vì cố tìm toàn bộ giá trị trên một dòng bằng grep.

Một số lưu ý:

- **Manifest-Version** thường được công cụ JAR sinh tự động.
- **Manifest attributes không phải các property của application.properties**. Viết Build-Channel trong manifest không đồng nghĩa Spring Boot tự đặt spring.profiles.active hoặc cung cấp property app.build-channel.
- **Manifest không phải nơi lưu secret**: ai có file JAR thường đọc được các attribute.
- Thay đổi nội dung manifest làm thay đổi byte của archive và checksum; artifact đã được ký có thể cần build/ký lại đúng quy trình.
- Nếu chỉ cần ứng dụng xem version/build metadata qua Actuator, còn có cơ chế **build-info.properties** riêng; manifest và build-info là hai nguồn metadata khác nhau.

## 3. Main-Class và Start-Class: điểm cốt lõi của Spring Boot

### 3.1. Đối với JAR Java thông thường

Trong một JAR đơn giản có tất cả dependency phù hợp trên classpath, manifest có thể trỏ trực tiếp đến class chứa phương thức:

~~~java
public static void main(String[] args)
~~~

Ví dụ:

~~~text
Main-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

Với JAR Java thường, JVM có thể gọi class này trực tiếp khi chạy **java -jar**, miễn là nó được đóng gói đúng vị trí và mọi dependency cần thiết có thể được nạp.

### 3.2. Đối với Spring Boot executable JAR 3.3

Spring Boot đặt application classes và runtime dependencies trong archive theo bố cục riêng:

~~~text
manifest-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/launch/
│   └── JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── com/example/manifestdemo/ManifestDemoApplication.class
    └── lib/
        ├── spring-boot-*.jar
        └── ...
~~~

Trong Spring Boot **3.3.x**, manifest của executable JAR với layout thông thường phải có ý nghĩa tương đương:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

- **Main-Class** là **Spring Boot launcher**, được JVM gọi đầu tiên bởi **java -jar**. Launcher xây classloader hiểu dependency JAR lồng trong **BOOT-INF/lib** và class của ứng dụng trong **BOOT-INF/classes**.
- **Start-Class** là **class entry point thực tế của ứng dụng**, chứa **public static void main(String[] args)**. Launcher đọc thông tin này rồi gọi entry point tương ứng.
- Spring Boot Maven/Gradle Plugin có thể bổ sung các header khác, ví dụ **Spring-Boot-Version**, **Spring-Boot-Classes**, **Spring-Boot-Lib**, **Spring-Boot-Classpath-Index**, **Spring-Boot-Layers-Index**. Các giá trị cụ thể phụ thuộc plugin/version/layout; **không nên chỉnh thủ công chỉ để thêm metadata nghiệp vụ**.

Trong Spring Boot 3.3, **đổi Main-Class thành ManifestDemoApplication là sai với Boot JAR mặc định**, vì class ứng dụng nằm dưới BOOT-INF/classes và phụ thuộc có thể nằm bên trong nested JAR. JVM chuẩn không tự tổ chức classpath như Spring Boot launcher.

**Tương tự, đổi Start-Class sang class không tồn tại hoặc không có phương thức main phù hợp sẽ khiến launcher không tìm được điểm chạy.** Class name phải là **fully qualified name** gồm package và tên class, phân biệt chữ hoa/chữ thường.

### 3.3. Trình tự khi chạy java -jar

~~~text
java -jar manifest-demo-1.0.0.jar
                 |
                 v
JVM đọc META-INF/MANIFEST.MF
                 |
                 v
Main-Class = org.springframework.boot.loader.launch.JarLauncher
                 |
                 v
Boot loader nạp BOOT-INF/classes + BOOT-INF/lib
                 |
                 v
Start-Class = com.example.manifestdemo.ManifestDemoApplication
                 |
                 v
ManifestDemoApplication.main(String[])
                 |
                 v
SpringApplication.run(...)
~~~

Nếu startup lỗi, xem stack trace để xác định **lỗi launcher/entry point**, **thiếu class/dependency** hay **lỗi cấu hình ứng dụng**; không phải mọi lỗi khởi động đều do manifest.

## 4. Những thuộc tính nào được thêm, những thuộc tính nào cần tránh?

| Loại thuộc tính | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Metadata nhận diện** | Implementation-Title, Implementation-Version | Thường an toàn để bổ sung. |
| **Metadata quy trình build** | Build-Revision, Build-Channel, Built-By-Team | Có thể bổ sung nếu giá trị không nhạy cảm và được quản lý đúng. |
| **Điểm vào launcher** | Main-Class | Để Boot plugin quản lý với executable JAR mặc định. |
| **Class ứng dụng** | Start-Class | Dùng Spring Boot mainClass configuration; tránh hai nguồn cấu hình trái nhau. |
| **Bố cục Spring Boot** | Spring-Boot-Classes, Spring-Boot-Lib | Không tùy tiện sửa; gắn với cách loader tìm class/dependency. |
| **Classpath chuẩn của JAR** | Class-Path | Thường không cần cho Boot JAR có nested dependencies; không dùng thay BOOT-INF/lib. |
| **Java module metadata** | Automatic-Module-Name | Chỉ thêm khi hiểu tác động với JPMS/consumer; không cần cho ví dụ. |
| **Package sealing / Multi-release** | Sealed, Multi-Release | Chỉ cấu hình khi archive thực sự có cấu trúc/hành vi tương ứng. |

**Nhận diện phiên bản:** Implementation-Version nên lấy từ version dự án chứ không tự nhập số cố định khác với POM hoặc Gradle project version. **Build-Revision** nên đại diện cho đúng commit đã build; bản demo dùng **lesson-149** để kết quả kiểm tra có thể tái lập. Đừng gán ngẫu nhiên giá trị rồi gọi là Git SHA thật.

## 5. Một chương trình Java 17 dùng chung cho Maven và Gradle

Để bài thực hành so sánh công bằng, cả hai công cụ đều build cùng một ứng dụng Spring Boot. Tạo source:

**src/main/java/com/example/manifestdemo/ManifestDemoApplication.java**

~~~java
package com.example.manifestdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManifestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ManifestDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner startupProof() {
        return args -> System.out.println("MANIFEST_BOOT_OK");
    }
}
~~~

Đây là **một file Java hoàn chỉnh**, package trùng với đường dẫn folder. Dự án dùng **spring-boot-starter** nên không bật HTTP server, không cần database và không phải cung cấp application.properties. Khi executable JAR chạy thành công, **CommandLineRunner** ghi đúng một dòng từ mã của chúng ta:

~~~text
MANIFEST_BOOT_OK
~~~

Spring Boot có thể in log khởi động ngoài dòng đó; đây là **stdout xác định do chương trình sinh ra**, không phải toàn bộ terminal output.

Cấu trúc tối thiểu khi chọn Maven:

~~~text
manifest-demo/
├── pom.xml
└── src/main/java/com/example/manifestdemo/ManifestDemoApplication.java
~~~

Khi chọn Gradle:

~~~text
manifest-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/com/example/manifestdemo/ManifestDemoApplication.java
~~~

**Chỉ chọn một cách build cho một bản thực hành.** Maven Wrapper/Gradle Wrapper cần được tạo hoặc cung cấp sẵn trong repository; việc liệt kê tên wrapper trong cây thư mục không tự tạo ra wrapper hoạt động.

## 6. Maven: thêm manifestEntries rồi để Spring Boot repackage quản lý entry point

### 6.1. Vai trò của hai Maven plugin

Maven có hai bước đóng gói liên quan:

1. **maven-jar-plugin** tạo JAR thông thường từ classes/resources, đồng thời có thể ghi **manifestEntries** bổ sung vào manifest của JAR đầu vào.
2. **spring-boot-maven-plugin** với goal **repackage** biến JAR đã tạo thành **Spring Boot executable JAR**, viết lại những phần manifest do loader quản lý, nhất là **Main-Class** và **Start-Class**, rồi giữ các metadata bổ sung thích hợp.

**Điều rất quan trọng:** Muốn thay đổi entry point, hãy dùng **mainClass trong spring-boot-maven-plugin**. **Không** cố đặt Main-Class hoặc Start-Class ở maven-jar-plugin để ép Spring Boot khởi động theo một kiểu khác; Spring Boot repackage có quyền ghi lại chúng.

Khi dùng **spring-boot-starter-parent**, execution **repackage** đã được cấu hình sẵn. Cần khai báo Spring Boot plugin trong build/plugins; không bắt buộc tự tạo thêm một execution repackage trùng lặp.

### 6.2. pom.xml đầy đủ

Lưu **pom.xml** sau ở gốc ứng dụng:

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
    <artifactId>manifest-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <build.revision>lesson-149</build.revision>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Tạo JAR gốc và thêm metadata không xung đột. -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifestEntries>
                            <Implementation-Title>manifest-demo</Implementation-Title>
                            <Implementation-Version>${project.version}</Implementation-Version>
                            <Build-Channel>training</Build-Channel>
                            <Build-Revision>${build.revision}</Build-Revision>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>

            <!-- Repackage và quản lý Main-Class/Start-Class đúng chuẩn Boot. -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.manifestdemo.ManifestDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đây là POM đầy đủ** cho ứng dụng demo. Phân tích những dòng quan trọng:

- **project.version = 1.0.0**: version phát hành của ứng dụng. **Implementation-Version** được lấy từ thuộc tính này, tránh phải sửa hai nơi.
- **build.revision = lesson-149**: giá trị demo không nhạy cảm. Sau này có thể truyền một revision thật từ CI.
- **maven-jar-plugin > archive > manifestEntries**: thêm **Implementation-Title**, **Implementation-Version**, **Build-Channel**, **Build-Revision**. Bốn thuộc tính này không thay thế Main-Class hoặc Start-Class.
- **spring-boot-maven-plugin > mainClass**: chỉ định rõ class **com.example.manifestdemo.ManifestDemoApplication** làm entry point ứng dụng; Boot plugin ghi thông tin cần thiết vào manifest của executable JAR.
- **Thứ tự plugin trong build/plugins**: Maven JAR Plugin được khai báo trước Spring Boot Plugin. Với cùng pha package, nguyên tắc là tạo JAR đầu vào trước rồi repackage. Cấu hình của Spring Boot starter parent đã xử lý execution repackage cho trường hợp tiêu chuẩn.
- **packaging = jar**: không cấu hình thêm layout khác, vì ta cần executable JAR tiêu chuẩn của Spring Boot 3.3.

**Không cần** thêm dòng **Main-Class: org.springframework.boot.loader.launch.JarLauncher** bằng tay trong manifestEntries. Launcher được Boot plugin chọn dựa trên layout/version đang build.

### 6.3. Build Maven và đường dẫn artifact

Nếu repository có Maven Wrapper:

~~~bash
./mvnw clean package
~~~

Nếu không có wrapper nhưng máy đã cài Maven:

~~~bash
mvn clean package
~~~

Trên Windows, dùng **mvnw.cmd** thay cho **./mvnw**. Sau khi package thành công với POM mẫu, executable archive dự kiến nằm ở:

~~~text
target/manifest-demo-1.0.0.jar
~~~

Khi không cấu hình classifier cho repackage, executable Boot JAR **thay thế main artifact**; bản JAR gốc có thể tồn tại dưới tên đuôi **.original** trong target, nhưng không phải file triển khai chính. Mọi thao tác kiểm tra phải hướng đến **manifest-demo-1.0.0.jar** sau repackage, không đọc manifest của file .original rồi cho rằng đó là manifest cuối cùng.

### 6.4. Chạy Maven artifact

~~~bash
java -jar target/manifest-demo-1.0.0.jar
~~~

Dòng stdout do code của chúng ta in ra:

~~~text
MANIFEST_BOOT_OK
~~~

Nếu thiếu launcher hoặc Start-Class sai, ứng dụng có thể không tới được CommandLineRunner. Vì vậy **java -jar** là phép kiểm tra hành vi bổ sung cho việc đọc các attribute.

## 7. Gradle: manifest của bootJar và cấu hình springBoot.mainClass

### 7.1. Phân biệt jar với bootJar

Khi ứng dụng áp dụng Java plugin và Spring Boot Gradle Plugin:

- Task **jar** tạo **plain JAR** có các class/resource thông thường; với Spring Boot Gradle plugin, task jar thường mang classifier **plain** để tránh trùng filename.
- Task **bootJar** tạo **executable Spring Boot JAR** với Boot loader và dependency nested trong BOOT-INF/lib.
- **mainClass** của Spring Boot Gradle Plugin có thể được tự tìm theo source code, nhưng nếu có nhiều phương thức main, nên chỉ định tường minh.
- **Manifest attributes bổ sung phải cấu hình trên task tạo artifact cần phân phối**, trong trường hợp này là **bootJar**.

Đừng chỉ viết:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes 'Build-Channel': 'training'
    }
}
~~~

... rồi mặc định rằng cùng metadata đó chắc chắn nằm trong Boot JAR. **jar và bootJar là hai task khác nhau**, với manifest và output riêng. Nếu muốn metadata ở executable archive, hãy đặt vào **tasks.named('bootJar')**.

### 7.2. settings.gradle đầy đủ

~~~groovy
rootProject.name = 'manifest-demo'
~~~

### 7.3. build.gradle đầy đủ (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}

tasks.named('bootJar') {
    manifest {
        attributes(
            'Implementation-Title': 'manifest-demo',
            'Implementation-Version': project.version.toString(),
            'Build-Channel': 'training',
            'Build-Revision': 'lesson-149'
        )
    }
}
~~~

Đây là **build.gradle Groovy DSL hoàn chỉnh** khi kết hợp với settings.gradle và file Java ở mục 5. Giải thích:

1. **springBoot.mainClass** cung cấp tên class thực sự chạy ứng dụng, khớp package/class của source Java. Spring Boot Gradle Plugin dùng thông tin này khi đóng executable JAR.
2. **tasks.named('bootJar')** chọn đúng task tạo executable archive; thuộc tính **manifest** đến từ Gradle Jar task API.
3. **attributes(...)** thêm bốn header nghiệp vụ, **không đặt Main-Class** hoặc **Start-Class**.
4. **project.version.toString()** liên kết Implementation-Version với version project.
5. **gradlePlugin version 3.3.5** là version Spring Boot build plugin; **project.version 1.0.0** là version ứng dụng; chúng là hai thứ khác nhau.
6. Java toolchain 17 phục vụ các task Java phù hợp; JVM chạy Gradle vẫn phải tương thích với phiên bản Gradle và plugin.

Với Boot 3.3 và layout JAR tiêu chuẩn, plugin tự tạo **Main-Class** trỏ Boot JarLauncher và **Start-Class** trỏ tới mainClass đã chọn.

### 7.4. Lựa chọn khác: đặt mainClass ngay trên bootJar

Trong một số build bạn chỉ muốn đổi entry point của task bootJar mà không thiết lập toàn project, có thể dùng đoạn **thay thế cho block springBoot ở trên**:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}
~~~

Nếu cũng cần metadata, hãy đặt **mainClass** cùng **manifest attributes** trong **một** block bootJar:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
    manifest {
        attributes(
            'Implementation-Title': 'manifest-demo',
            'Implementation-Version': project.version.toString(),
            'Build-Channel': 'training',
            'Build-Revision': 'lesson-149'
        )
    }
}
~~~

Đây là **cấu hình thay thế**, không phải file hoàn chỉnh. Không cần đồng thời đặt **springBoot.mainClass** khác với **bootJar.mainClass**, vì điều đó tạo hai nguồn thông tin mâu thuẫn. Trong Gradle 8.5/Spring Boot 3.3, Gradle DSL còn hỗ trợ đặt **Start-Class** trong manifest của bootJar, nhưng **dùng mainClass property dễ hiểu và ít rủi ro hơn**.

### 7.5. Build và chạy Gradle artifact

Từ root có Gradle Wrapper:

~~~bash
./gradlew clean bootJar
~~~

Hoặc muốn chạy cả các task verification thông thường:

~~~bash
./gradlew clean build
~~~

Trên Windows dùng **gradlew.bat**. Với settings.gradle và version ở mục 7, file executable mặc định dự kiến:

~~~text
build/libs/manifest-demo-1.0.0.jar
~~~

Khi chạy **build**, có thể có thêm plain JAR:

~~~text
build/libs/manifest-demo-1.0.0-plain.jar
~~~

**Đừng kiểm tra file -plain.jar để đánh giá manifest Boot JAR**. File -plain có mục đích khác và không có đầy đủ Boot loader layout. Chạy executable:

~~~bash
java -jar build/libs/manifest-demo-1.0.0.jar
~~~

Dòng stdout do mã Java in ra:

~~~text
MANIFEST_BOOT_OK
~~~

## 8. Kết quả manifest cuối cùng cần thấy

Dù chọn Maven hay Gradle, trong **executable Spring Boot 3.3 JAR tiêu chuẩn**, các attribute quan trọng dự kiến như sau (thứ tự dòng thực tế có thể khác):

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.manifestdemo.ManifestDemoApplication
Implementation-Title: manifest-demo
Implementation-Version: 1.0.0
Build-Channel: training
Build-Revision: lesson-149
~~~

Đây là **trích đoạn minh họa các mục cần kiểm tra**, không phải toàn văn manifest thực tế. Spring Boot Plugin có thể thêm Spring-Boot-Version, Spring-Boot-Classes, Spring-Boot-Lib và nhiều thuộc tính khác; trình tạo JAR có thể gấp dòng dài theo đặc tả manifest.

**Điều kiện PASS không chỉ là “có thêm Build-Channel”.** Ít nhất phải kiểm tra:

- Main-Class là Boot launcher đúng với phiên bản/layout.
- Start-Class đúng fully qualified application main class.
- Implementation-Title/Version và Build-Channel/Revision có giá trị dự kiến.
- **BOOT-INF/classes/** thực sự chứa class ứng dụng và **BOOT-INF/lib/** có runtime dependency.
- Lệnh **java -jar** khởi động ứng dụng đúng, không chỉ in metadata.

## 9. Bài thực hành kiểm tra manifest bằng Java 17

Vì manifest có thể bị **line wrapping**, ta dùng API chuẩn Java **java.util.jar.JarFile**, **Manifest**, **Attributes**. Bài test này đọc **file archive cuối cùng**, không dựa vào thứ tự dòng hoặc một công cụ Unix riêng biệt.

Đặt tệp **ManifestVerifier.java** ở **root** của dự án (cạnh pom.xml hoặc build.gradle); **không** đặt nó trong src/main/java để tránh biến công cụ kiểm tra thành phần của ứng dụng.

~~~java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ManifestVerifier {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ManifestVerifier.java <executable.jar>");
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing manifest");
            }

            Attributes attrs = manifest.getMainAttributes();
            expect(attrs, "Main-Class",
                    "org.springframework.boot.loader.launch.JarLauncher");
            expect(attrs, "Start-Class",
                    "com.example.manifestdemo.ManifestDemoApplication");
            expect(attrs, "Implementation-Title", "manifest-demo");
            expect(attrs, "Implementation-Version", "1.0.0");
            expect(attrs, "Build-Channel", "training");
            expect(attrs, "Build-Revision", "lesson-149");

            String appClass =
                    "BOOT-INF/classes/com/example/manifestdemo/"
                    + "ManifestDemoApplication.class";
            if (jar.getEntry(appClass) == null) {
                throw new IllegalStateException(
                        "App class missing: " + appClass);
            }
        }

        System.out.println("MANIFEST_OK");
    }

    private static void expect(
            Attributes attrs, String key, String expected) {
        String actual = attrs.getValue(key);
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    key + ": expected " + expected + " but was " + actual);
        }
    }
}
~~~

**Đây là file Java hoàn chỉnh** tương thích Java 17. Nó kiểm tra manifest metadata và class ứng dụng nằm đúng trong Boot layout. Khi một attribute sai hoặc archive thiếu class, chương trình ném exception và tiến trình kết thúc với exit code khác 0; điều này hữu ích để làm gate trong CI.

### 9.1. Chạy kiểm chứng trên Maven executable JAR

~~~bash
./mvnw clean package
java ManifestVerifier.java target/manifest-demo-1.0.0.jar
java -jar target/manifest-demo-1.0.0.jar
~~~

Lệnh **java ManifestVerifier.java** sử dụng khả năng **Java source-file launcher** có từ Java 11, không cần chạy javac trước. Cần dùng JDK/JVM đủ mới.

Nếu manifest và layout đúng, **stdout riêng của chương trình verifier** là:

~~~text
MANIFEST_OK
~~~

**Lệnh java -jar ở dòng tiếp theo** là kiểm tra riêng; khi khởi động thành công, ứng dụng in:

~~~text
MANIFEST_BOOT_OK
~~~

Không khẳng định toàn bộ terminal chỉ có đúng hai dòng, vì Maven/Spring Boot có thể ghi thêm log.

### 9.2. Chạy kiểm chứng trên Gradle executable JAR

~~~bash
./gradlew clean bootJar
java ManifestVerifier.java build/libs/manifest-demo-1.0.0.jar
java -jar build/libs/manifest-demo-1.0.0.jar
~~~

Kết quả verifier cũng phải là **MANIFEST_OK**, và ứng dụng in **MANIFEST_BOOT_OK**. Chỉ khác công cụ và đường dẫn build artifact; các expected attributes đều được thiết kế giống nhau.

### 9.3. Cách đọc thủ công manifest bằng công cụ JDK

Lệnh:

~~~bash
jar tf target/manifest-demo-1.0.0.jar
~~~

liệt kê các entry của Maven archive. Với Gradle, đổi đường dẫn sang **build/libs/manifest-demo-1.0.0.jar**. Trong danh sách phải có **META-INF/MANIFEST.MF** và **BOOT-INF/classes/com/example/manifestdemo/ManifestDemoApplication.class**.

Nếu cần mở manifest theo cách thủ công, có thể vào một **thư mục tạm trống** và dùng **jar xf đường-dẫn-tuyệt-đối-đến-JAR META-INF/MANIFEST.MF**, rồi đọc tệp vừa được giải nén. **Đừng chạy jar xf trực tiếp trong project root nếu không muốn tạo META-INF ở đó.** Với môi trường Unix có unzip, có thể xem nội dung mà không giải nén ra đĩa bằng lệnh unzip -p với tên entry thích hợp.

**Vì sao vẫn nên dùng ManifestVerifier?** Một giá trị dài có thể trải nhiều dòng vật lý trong MANIFEST.MF, trong khi **Attributes.getValue** trả về giá trị logic đã được ghép đúng theo đặc tả.

## 10. Gắn build revision thực tế khi CI chạy

Trong ví dụ, Build-Revision là **lesson-149** cố định để bài có output xác định. Với dự án production, revision nên lấy từ commit đã checkout trong CI, thay vì gõ tay một SHA.

### 10.1. Maven: dùng project property

POM ở mục 6 đã chứa:

~~~xml
<properties>
    <build.revision>lesson-149</build.revision>
</properties>
~~~

và manifestEntries:

~~~xml
<Build-Revision>${build.revision}</Build-Revision>
~~~

Đây là **hai fragments bên trong POM**, không phải hai POM mới. Trong CI, có thể truyền property lúc build:

~~~bash
./mvnw -Dbuild.revision=abc123 clean package
~~~

Trong đó **abc123 chỉ là giá trị minh họa**. Khi thay build.revision, trường **Build-Revision** của manifest sẽ đổi theo. Chương trình **ManifestVerifier.java** ở mục 9 đang kỳ vọng **lesson-149**, vì vậy nếu cố tình build với abc123, phải **đổi expected revision trong verifier hoặc truyền expected revision vào công cụ kiểm thử**. Không kết luận build lỗi chỉ vì dữ liệu kiểm thử cố định chưa được cập nhật theo input mới.

Cần giữ chính sách version/revision thống nhất giữa artifact, CI logs và metadata triển khai. Không đưa credential, secret hoặc token vào manifest thông qua property.

### 10.2. Gradle: dùng gradle.properties hoặc -P

Ở phương án Gradle, thay dòng:

~~~groovy
'Build-Revision': 'lesson-149'
~~~

bằng:

~~~groovy
'Build-Revision': providers.gradleProperty('buildRevision')
        .orElse('lesson-149').get()
~~~

Đây là **fragment nằm trong attributes(...)** của block bootJar. Dùng **providers.gradleProperty** cho phép Gradle nhận property từ **gradle.properties** hoặc **-P** trên command line. Ví dụ:

~~~bash
./gradlew -PbuildRevision=abc123 clean bootJar
~~~

Khi không truyền property, revision mặc định là **lesson-149**, phù hợp verifier ở mục 9. Khi truyền abc123, verifier phải so sánh với abc123 mới đúng.

**Không cần chạy lệnh git trực tiếp trong quá trình configuration của Gradle** chỉ để có revision nếu CI đã cung cấp SHA. Tránh phụ thuộc thời gian/người dùng hiện tại làm build không tái lập được khi không có nhu cầu.

## 11. Khác biệt khi ứng dụng có nhiều main class

Một dự án Java có thể chứa nhiều phương thức **main**, ví dụ **ManifestDemoApplication** và **DataMigrationCli**. Công cụ build có thể không biết nên lấy class nào, hoặc chọn class không đúng ý định khi dựa vào auto-detection.

Đối với **Maven Spring Boot**, chỉ rõ:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.manifestdemo.ManifestDemoApplication</mainClass>
    </configuration>
</plugin>
~~~

Đối với **Gradle Spring Boot**:

~~~groovy
springBoot {
    mainClass = 'com.example.manifestdemo.ManifestDemoApplication'
}
~~~

Cả hai ví dụ trên là **fragments**, không phải toàn bộ POM/build.gradle. Chúng đảm bảo entry point của archive được xác định theo cách mà Boot plugin hiểu, thay vì nhập tùy ý:

~~~text
Main-Class: com.example.manifestdemo.ManifestDemoApplication
~~~

để JVM gọi class app trực tiếp từ Boot archive. Nếu build muốn tạo **nhiều executable JAR với entry point khác nhau**, cần cấu hình **nhiều archive task/execution**, classifier và mainClass riêng, tránh hai task ghi đè cùng file; không chỉ sửa một header trên artifact đã được repackage.

### 11.1. Spring Boot Kotlin application

Nếu class có hàm top-level **main** trong Kotlin file ExampleApplication.kt, JVM thường sinh class **ExampleApplicationKt**. Để đặt mainClass chính xác, phải dùng **tên JVM class thực** chứ không chỉ tên Kotlin source. Ví dụ này chỉ là lưu ý cross-language; bài chính dùng Java 17 nên tên **ManifestDemoApplication** khớp trực tiếp.

### 11.2. PropertiesLauncher và layout khác JAR

Spring Boot còn có cách launch dùng **PropertiesLauncher** và những layout khác (ví dụ Maven layout ZIP/DIR). Khi đổi layout theo hướng này, **Main-Class có thể khác JarLauncher**. Nhưng bài đang nói về **JAR layout mặc định** của Boot 3.3, nên không đổi layout hoặc launcher.

**Nếu có yêu cầu đặc biệt về external loader path**, hãy dùng tính năng launcher/layout được Boot plugin hỗ trợ và kiểm thử riêng. Không “sửa bừa” Main-Class trong manifest cho đến khi JAR bắt đầu chạy, vì có thể làm mất khả năng load nested libraries hoặc bỏ qua những quy tắc cần thiết.

## 12. Khác nhau giữa manifest của plain JAR và Boot JAR

Một build Spring Boot có thể có hai loại output cùng chứa META-INF/MANIFEST.MF:

| Thuộc tính | Plain JAR | Executable Boot JAR |
| --- | --- | --- |
| Vị trí class ứng dụng | Thường ngay dưới package path | BOOT-INF/classes |
| Dependency runtime | Thường không chứa nested runtime libraries | BOOT-INF/lib |
| Main-Class | Có thể vắng hoặc trỏ app nếu tự cấu hình | Boot JarLauncher cho layout mặc định |
| Start-Class | Không bắt buộc | Trỏ main class thực tế của ứng dụng |
| Implementation-Title/Version | Có thể có khi cấu hình | Có thể có khi cấu hình |
| Dùng java -jar như app Boot độc lập | Không được bảo đảm | Có, khi đóng gói/entry point đúng |

**Maven:** Spring Boot repackage không classifier thường thay JAR chính bằng executable archive và giữ file **.original** cục bộ. Đừng kiểm chứng **.original** rồi tưởng nó là artifact Boot.

**Gradle:** Spring Boot plugin có thể tạo **manifest-demo-1.0.0-plain.jar** từ task jar và **manifest-demo-1.0.0.jar** từ bootJar. Bài thực hành chỉ thêm các attribute nghiệp vụ vào **bootJar manifest**; không suy ra plain JAR sẽ có đủ chúng.

Nếu muốn cả hai artifact đều có metadata như nhau, cần cấu hình tương ứng trên **jar và bootJar**, rồi kiểm tra cả hai file. Nhưng **không ép plain JAR dùng Main-Class JarLauncher** khi nó không có Boot loader layout.

**Cách chọn file đưa vào CI/CD:** Không dùng glob **build/libs/*.jar** nếu có cả plain và Boot JAR, vì có thể lấy nhầm. Dùng đường dẫn đã biết hoặc Provider **bootJar.archiveFile** trong Gradle. Khi đổi tên/version, cập nhật pipeline và kiểm tra artifact thực tế.

## 13. Manifest so với build-info.properties và các nguồn metadata khác

Khi cần version/revision để chẩn đoán sản phẩm, có nhiều lựa chọn:

1. **JAR manifest**: metadata ở META-INF/MANIFEST.MF, đọc bằng **JarFile**. Phù hợp kiểm tra archive khi chưa chạy hoặc cần điều tra gói phát hành.
2. **Spring Boot build-info**: thông tin build trong **META-INF/build-info.properties** khi bật Maven goal **spring-boot:build-info** hoặc Gradle task **bootBuildInfo** tương ứng. Đây là tệp riêng, không phải manifest.
3. **Environment variables / Spring properties**: cấu hình runtime thay đổi theo môi trường triển khai, ví dụ profile hoặc endpoint external.
4. **Container image labels / CI metadata**: thông tin commit/build ở cấp image hoặc pipeline, giúp truy vết artifact nguồn.

**Không nhầm:** Tự thêm **Implementation-Version** vào manifest **không tự bảo đảm** endpoint **/actuator/info** hiển thị build version. Actuator có cơ chế InfoContributor và build-info riêng; muốn expose metadata phải cấu hình/cho phép endpoint phù hợp, đồng thời tránh đưa dữ liệu nội bộ nhạy cảm ra HTTP công khai.

Với mục tiêu bài này, ta dùng **manifestEntries/bootJar.manifest** và kiểm tra trực tiếp bằng JarFile; không cần thêm Actuator chỉ để đọc JAR.

## 14. Lưu ý về định dạng manifest và tính tái lập bản build

### 14.1. Header và độ dài dòng

Manifest attribute name tuân theo ràng buộc tên/độ dài của đặc tả JAR. Chọn các header ngắn, dễ đọc như **Build-Revision**, **Build-Channel**, **Implementation-Title**. Giá trị dài có thể được gấp thành các dòng tiếp theo bắt đầu bằng khoảng trắng. Đừng chỉnh tệp MANIFEST.MF bằng thao tác nối chuỗi thuần rồi quên ranh giới section, xuống dòng hoặc encoding.

**Phép kiểm tra đúng** là lấy giá trị logic qua **Manifest.getMainAttributes().getValue(...)** như Java verifier trong bài. Đặc biệt, manifest có thể chứa **named sections** cho entry khác: metadata build của toàn archive nên nằm trong **main attributes**, không đặt nhầm dưới section của một file cụ thể.

### 14.2. Đường dẫn archive và bản build đã ký

Khi JAR được ký, manifest và chữ ký liên quan với nội dung archive. Thay đổi manifest **sau khi ký** có thể làm xác thực chữ ký thất bại. Cách an toàn là **cấu hình metadata từ build script → tạo JAR → kiểm tra → ký/publish theo pipeline**. Không nên mở JAR production bằng công cụ ZIP rồi sửa manifest trực tiếp để “fix nhanh”.

### 14.3. Tránh timestamp ngẫu nhiên khi không cần

Mỗi lần ghi Build-Time theo thời gian thực có thể làm JAR khác checksum dù code không đổi. Nếu cần reproducible build, dùng các thiết lập archive timestamp/order được Maven/Gradle/Spring Boot hỗ trợ và lưu thời điểm build ở CI metadata riêng. Với **Build-Revision** và version cố định, bài thực hành cho kết quả metadata ổn định giữa các lần chạy cùng input.

### 14.4. Phạm vi bảo mật

**Không lưu password, access token, private URL chứa credential hoặc dữ liệu khách hàng** trong manifest. Bất kỳ ai có artifact đều có thể trích xuất META-INF/MANIFEST.MF mà không cần chạy ứng dụng. Build agent hostname/user path cũng có thể là metadata không cần chia sẻ; chọn những trường thật sự phục vụ truy vết.

## 15. Lỗi thường gặp và hướng xử lý

**Lỗi 1 — Main-Class trỏ thẳng application class trong Boot JAR.** Với Boot 3.3 JAR layout mặc định, JVM cần gọi Boot JarLauncher để hiểu BOOT-INF/lib. Hãy bỏ cấu hình Main-Class thủ công trong maven-jar-plugin hoặc bootJar.manifest, sử dụng Boot plugin để tạo launcher.

**Lỗi 2 — Start-Class sai tên package/class.** Kiểm tra package ở file Java và fully qualified name trong **spring-boot-maven-plugin.mainClass** hoặc **springBoot.mainClass**; thử **jar tf** để xác nhận BOOT-INF/classes có file .class tương ứng.

**Lỗi 3 — Maven manifestEntries có Build-Revision nhưng artifact cuối không thấy.** Xem đã chạy goal **repackage** chưa, xem đúng target JAR (không phải .original) và kiểm tra plugin cấu hình đúng trong **build/plugins**. Nếu có nhiều execution custom, kiểm tra thứ tự tạo JAR rồi repackage và xem build log.

**Lỗi 4 — Gradle thêm metadata vào jar nhưng kiểm tra bootJar.** Hai task khác nhau. Chuyển cấu hình metadata sang **tasks.named('bootJar')** nếu metadata phải có trong executable archive; xây và đọc lại file đúng.

**Lỗi 5 — Đặt Main-Class thông qua Maven JAR Plugin rồi thấy bị Spring Boot thay thế.** Đây là hành vi có chủ đích của Boot repackage. Muốn đổi application main, dùng **spring-boot-maven-plugin.mainClass**, không cố ngăn plugin sửa Main-Class.

**Lỗi 6 — Có nhiều main method và plugin chọn nhầm.** Chỉ định mainClass rõ ràng trong build, không dựa hoàn toàn vào cơ chế tự tìm.

**Lỗi 7 — Java chạy báo ClassNotFoundException hoặc NoClassDefFoundError.** Không phải lúc nào cũng do manifest: phân biệt class loader, Start-Class, nested dependency, scope dependency và JDK runtime. Kiểm tra BOOT-INF/classes, BOOT-INF/lib, Java version và stack trace.

**Lỗi 8 — Đọc META-INF/MANIFEST.MF rồi tìm không ra giá trị dài bằng grep.** Manifest có thể gấp dòng; dùng **java.util.jar.Manifest** để đọc giá trị logic.

**Lỗi 9 — Thêm Class-Path liệt kê nested JAR.** Boot JarLauncher tự xử lý nested libraries. Class-Path theo manifest chuẩn thường không thay thế BOOT-INF/lib. Để Spring Boot quản lý loader classpath.

**Lỗi 10 — Implementation-Version khác project.version.** Tránh giá trị hard-coded sai; Maven dùng **project.version**, Gradle dùng **project.version.toString()** hoặc một Provider có quy tắc rõ ràng.

**Lỗi 11 — CI đổi Build-Revision nhưng verifier vẫn kỳ vọng lesson-149.** Giữ expected values cùng input build; truyền revision mong đợi vào gate nếu giá trị thay đổi từng commit.

**Lỗi 12 — Bản Gradle tạo hai JAR và CI lấy -plain.jar.** Không mặc định mọi file .jar đều là executable. Chọn bootJar output, kiểm tra Main-Class/Start-Class và thử java -jar.

**Lỗi 13 — Đặt Start-Class trong manifest và mainClass property thành hai class khác nhau.** Một plugin/task có thể ưu tiên một nguồn hoặc ghi lại thông tin; hãy giữ **một nguồn cấu hình entry point duy nhất** và kiểm tra manifest cuối.

**Lỗi 14 — Repackage với layout ZIP/PropertiesLauncher nhưng verifier kỳ vọng JarLauncher.** Ví dụ của bài chỉ dành cho JAR layout tiêu chuẩn. Khi đổi layout, dùng expected Main-Class tương ứng, không gắn cứng quy tắc JarLauncher cho mọi Boot archive.

**Lỗi 15 — Sửa manifest bằng unzip/zip sau build rồi không chạy lại test.** Archive có thể bị thay đổi chữ ký, checksum, cấu trúc Boot hoặc metadata version. Sửa từ cấu hình Maven/Gradle và build lại.

**Lỗi 16 — Nghĩ Implementation-Title trong manifest tự trở thành Spring property.** Spring Environment không tự nhập mọi JAR manifest entry thành application.properties. Nếu code cần đọc, dùng API thích hợp hoặc cấu hình build-info.

**Lỗi 17 — JAR chạy trên laptop nhưng lỗi trong container.** Kiểm tra image Java runtime, source compatibility, paths, các biến môi trường, dependency runtime và Dockerfile copy đúng Boot JAR. Manifest đúng chỉ là một trong các điều kiện startup.

**Lỗi 18 — Plugin Spring Boot không chạy repackage.** Nếu Maven không dùng starter parent, phải gắn execution **repackage** vào lifecycle; nếu Gradle chưa áp plugin Boot, không có bootJar. Kiểm tra task/goal thực sự chạy.

**Lỗi 19 — Header tùy chỉnh chứa thông tin bí mật.** Manifest là metadata đọc được. Loại bỏ secret và dùng secret manager/runtime configuration.

**Lỗi 20 — Thay Spring Boot version nhưng giữ nguyên tên launcher trong custom script.** Loader implementation và package có thể thay đổi giữa version. Với bài này, **org.springframework.boot.loader.launch.JarLauncher** là đặc trưng tương ứng Boot 3.3; không viết giả định đó cho mọi phiên bản Spring Boot cũ/mới.

## 16. Checklist trước khi phát hành

- [ ] Xác định rõ artifact đang phân phối là **Spring Boot executable JAR**, không phải plain JAR.
- [ ] Chọn các manifest attributes bổ sung không xung đột với metadata loader.
- [ ] Maven: đưa metadata vào **maven-jar-plugin.archive.manifestEntries**.
- [ ] Maven: đặt entry point tại **spring-boot-maven-plugin.mainClass**; bảo đảm repackage được chạy sau khi tạo JAR gốc.
- [ ] Gradle: thêm metadata vào **bootJar.manifest**, không chỉ jar.manifest.
- [ ] Gradle: đặt entry point tại **springBoot.mainClass** hoặc **bootJar.mainClass**.
- [ ] Đảm bảo Main-Class, Start-Class cuối cùng phù hợp **phiên bản và layout** của Boot.
- [ ] Build bằng clean package/bootJar; đọc đúng artifact cuối cùng.
- [ ] Dùng **ManifestVerifier.java** (hoặc công cụ tương đương) để xác minh chính xác metadata và Boot layout.
- [ ] Dùng **java -jar** và xác nhận ứng dụng thực sự chạy.
- [ ] Không đưa secret vào manifest; liên kết version/revision với metadata CI.
- [ ] Nếu thay đổi manifest sau khi ký JAR, phải build/ký lại theo quy trình phù hợp.
- [ ] Trong CI/CD, fail pipeline nếu verifier hoặc java -jar smoke test thất bại.
- [ ] Không suy ra bản build đúng chỉ từ việc nhìn thấy trường Main-Class trong raw manifest.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Specification, Launching: https://docs.spring.io/spring-boot/3.3/reference/executable-jar/launching.html
- Apache Maven JAR Plugin — Manifest Customization: https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html
- Apache Maven Archiver — Manifest Configuration: https://maven.apache.org/shared/maven-archiver/examples/manifest.html
- Gradle — Jar Task API: https://docs.gradle.org/8.5/dsl/org.gradle.jvm.tasks.Jar.html
- Java SE — java.util.jar.Manifest / Attributes / JarFile: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html

**Kết luận:** Trong Spring Boot 3.3 executable JAR, **Main-Class là Boot launcher** và **Start-Class là entry point của ứng dụng**. Maven cho phép thêm metadata qua **maven-jar-plugin.manifestEntries** rồi để **spring-boot:repackage** quản lý phần khởi động; Gradle thêm metadata vào **bootJar.manifest** và đặt application main qua **springBoot.mainClass/bootJar.mainClass**. Luôn đối chiếu **manifest của JAR cuối cùng + cấu trúc BOOT-INF + java -jar** trước khi công bố artifact.