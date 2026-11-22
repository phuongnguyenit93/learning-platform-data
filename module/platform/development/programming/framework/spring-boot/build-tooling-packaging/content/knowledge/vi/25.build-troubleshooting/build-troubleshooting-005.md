# Xử lý không tìm thấy main class hoặc có nhiều main class trong Spring Boot

## 1. Mục tiêu và cách tiếp cận

Trong nhóm chủ đề cha **Chẩn đoán sự cố**, bài học này giải quyết hai lỗi thường gặp khi đóng gói Spring Boot:

1. Build không tìm thấy main class, không xác định được entry point hoặc tạo archive không chạy được bằng java -jar.
2. Project có nhiều class cùng chứa public static void main(String[] args), khiến build tool chọn sai lớp khởi động hoặc không thể xác định lựa chọn mà nhóm mong muốn.

Với Java 17, entry point chuẩn là phương thức **public static void main(String[] args)**. Spring Boot executable JAR có thêm một lớp launcher riêng, vì vậy phải phân biệt:

- **Main class ứng dụng:** class do nhóm phát triển viết, chứa phương thức main.
- **Main-Class trong manifest của Boot JAR:** class launcher của Spring Boot, chịu trách nhiệm thiết lập classloader và nạp các nested JAR.
- **Start-Class trong manifest:** FQCN của main class ứng dụng mà launcher sẽ gọi.

Nếu có nhiều ứng viên, cách ổn định là cấu hình rõ **fully qualified class name (FQCN)** ở Spring Boot Maven Plugin hoặc Gradle Plugin. Nếu không có ứng viên, hãy kiểm tra source set, chữ ký method, package, module và compiled output trước khi sửa manifest.

Bài dùng **Java 17, Spring Boot 3.3.5, Maven 3.9.x hoặc Gradle 8.5**. Các ví dụ là bộ phiên bản cố định để thực hành; khi áp dụng vào dự án, dùng phiên bản đã được tổ chức kiểm thử.

## 2. Main class trong Java 17

### 2.1. Chữ ký entry point chuẩn

Java launcher tìm một phương thức main phù hợp trong class được yêu cầu chạy. Với Java 17, dạng rõ ràng và phổ biến là:

~~~java
public static void main(String[] args)
~~~

Ý nghĩa:

- **public:** launcher có thể gọi method từ bên ngoài class.
- **static:** không cần tạo object trước khi gọi.
- **void:** không trả về giá trị cho launcher.
- **main:** tên method được nhận diện.
- **String[] args:** mảng tham số dòng lệnh.

Dạng varargs cũng tương đương về chữ ký:

~~~java
public static void main(String... args)
~~~

Các dạng dưới đây không phải entry point chuẩn của Java 17:

~~~java
private static void main(String[] args) { }
public void main(String[] args) { }
public static int main(String[] args) { return 0; }
public static void main() { }
public static void Main(String[] args) { }
~~~

Tên method phân biệt chữ hoa/chữ thường. Java 17 cần dạng static main truyền thống; không áp dụng các tính năng preview hoặc cách khai báo entry point của những JDK mới hơn vào project target 17.

### 2.2. Annotation không thay thế main method

Annotation **@SpringBootApplication** đánh dấu cấu hình ứng dụng, hỗ trợ auto-configuration và component scanning. Annotation này không tự sinh phương thức main.

Ví dụ class sau hợp lệ về cú pháp Java nhưng chưa có entry point để đóng gói thành executable Boot JAR:

~~~java
package com.example.catalog;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
}
~~~

Nếu muốn archive chạy bằng java -jar, hãy thêm main method và gọi SpringApplication.run.

### 2.3. Main class phải nằm trong main source set

Cấu trúc chuẩn:

~~~text
src/
├── main/
│   └── java/
│       └── com/example/catalog/CatalogApplication.java
└── test/
    └── java/
        └── com/example/catalog/CatalogApplicationTests.java
~~~

Maven compile application code từ **src/main/java**. Gradle Java plugin dùng **main source set**. Class chỉ nằm dưới src/test/java không phải main class của executable application archive.

Kiểm tra những trường hợp:

- Main class đặt nhầm trong test source set.
- Generated source chưa được gắn vào compile task hoặc main source set.
- Plugin Spring Boot được áp dụng nhầm ở module core thay vì app.
- Source file khai báo package khác với FQCN trong cấu hình.
- Tên class, package hoặc chữ hoa/thường không khớp.
- Build đang chạy ở subproject không chứa class cần đóng gói.

### 2.4. Cấu hình bằng FQCN

Ví dụ:

~~~java
package com.example.catalog;

public class CatalogApplication {
    public static void main(String[] args) {
        System.out.println("CATALOG_APP_STARTED");
    }
}
~~~

FQCN chính xác:

~~~text
com.example.catalog.CatalogApplication
~~~

Không dùng tên file, đường dẫn filesystem, đuôi .java hoặc .class. Cấu hình main class nhận tên Java đầy đủ, không phải đường dẫn source.

## 3. Phân biệt hai tình huống lỗi

| Tình huống | Dấu hiệu thường gặp | Nơi kiểm tra đầu tiên |
| --- | --- | --- |
| Không có main class | Plugin không tìm thấy main class; Gradle không resolve được entry point; repackage/bootJar thất bại | Source set, method signature, module, compile output |
| Có nhiều main class | Build chọn nhầm ứng dụng hoặc tự dò không cho kết quả mong muốn | FQCN và cấu hình mainClass |
| Cấu hình đúng tên nhưng class không tồn tại | Archive có thể được tạo nhưng java -jar không nạp được Start-Class | Package name, class output, module, artifact |
| Manifest sai | no main manifest attribute hoặc launcher không đúng | META-INF/MANIFEST.MF và plugin configuration |
| Chạy nhầm file | Plain JAR thiếu Boot layout | Đường dẫn target/build/libs và classifier |

Thông báo lỗi có thể khác theo phiên bản plugin, lifecycle và task. Hãy xem goal/task đang thất bại, module và đường dẫn archive thay vì chỉ dựa vào một dòng lỗi lấy từ dự án khác.

## 4. Main-Class và Start-Class trong Spring Boot JAR

Một JAR Java thông thường có thể đặt class ứng dụng trong thuộc tính Main-Class của manifest. Spring Boot executable JAR cần một launcher để nạp dependencies nằm lồng trong archive.

Manifest điển hình của Spring Boot 3.3:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
~~~

Hai thuộc tính có nhiệm vụ khác nhau:

- **Main-Class** trỏ tới Boot Launcher. Launcher dựng classloader và tìm class/resources trong nested JAR.
- **Start-Class** trỏ tới main class của ứng dụng có public static void main(String[]).

Vì vậy, khi dùng Spring Boot Maven/Gradle Plugin, không đặt Main-Class thành class ứng dụng một cách tùy tiện. Hãy cấu hình main class trong Spring Boot plugin; plugin sẽ quản lý manifest theo archive layout.

Với executable WAR, launcher thường là WarLauncher; với executable JAR, launcher là JarLauncher. Tên package/class launcher có thể phụ thuộc phiên bản Spring Boot, vì vậy hãy kiểm tra manifest của chính artifact được build.

## 5. Ví dụ Java 17 có hai main classes

### 5.1. Main class của ứng dụng

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner startupProof() {
        return args -> System.out.println("CATALOG_APP_STARTED");
    }
}
~~~

Đây là Spring Boot application entry point. Ví dụ dùng starter cơ bản, không mở HTTP server. Khi context khởi động và CommandLineRunner chạy, code in ra dòng CATALOG_APP_STARTED.

### 5.2. Main class thứ hai

File **src/main/java/com/example/catalog/tools/MigrationTool.java**:

~~~java
package com.example.catalog.tools;

public class MigrationTool {

    public static void main(String[] args) {
        System.out.println("MIGRATION_TOOL_STARTED");
    }
}
~~~

Cả hai class đều có main method hợp lệ. Đây không nhất thiết là lỗi: chúng có thể đại diện hai entry point có mục đích khác nhau.

Tuy nhiên, một executable Boot JAR cụ thể có một Start-Class được chọn. Maven và Gradle có cách tự dò khác nhau; không nên dựa vào thứ tự quét file để quyết định ứng dụng nào được chạy.

### 5.3. Kết quả mong đợi

Nếu archive được cấu hình cho CatalogApplication, chạy:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

ứng dụng phải khởi động CatalogApplication và log có dòng:

~~~text
CATALOG_APP_STARTED
~~~

Nó không được khởi động MigrationTool chỉ vì class đó cũng chứa main.

Nếu cần phát hành cả ứng dụng và migration tool như hai chương trình độc lập, cân nhắc tách thành hai module/artifact. Mỗi artifact có manifest, dependency graph, runtime configuration và release contract riêng.

## 6. Maven: cấu hình main class rõ ràng

### 6.1. Cấu hình Spring Boot Maven Plugin

Trong POM của module ứng dụng:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.catalog.CatalogApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

FQCN phải trỏ tới class nằm trong compiled output của module app.

Nếu POM kế thừa **spring-boot-starter-parent**, goal repackage đã được cấu hình trong lifecycle với execution ID repackage. Trường hợp chuẩn chỉ cần khai báo plugin và cấu hình mainClass như trên.

Nếu **không** dùng Spring Boot starter parent, cần tự gắn goal repackage:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.catalog.CatalogApplication</mainClass>
            </configuration>
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

Không thêm execution trùng khi parent đã có execution repackage. Nếu cần ghi đè cấu hình inherited, dùng đúng execution ID của parent.

### 6.2. POM đầy đủ cho ứng dụng Maven

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
    <artifactId>catalog-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <configuration>
                    <mainClass>com.example.catalog.CatalogApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM này cấu hình Java 17, Spring Boot 3.3.5, starter cơ bản, starter-test và main class rõ ràng cho repackage.

### 6.3. Build và chạy Maven

~~~bash
./mvnw -B -ntp clean package
~~~

Artifact mặc định:

~~~text
target/catalog-app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

Nếu project có classifier hoặc finalName tùy chỉnh, dùng đúng đường dẫn artifact thực tế.

### 6.4. Maven multi-module: đặt plugin ở đúng module

Ví dụ:

~~~text
catalog-platform/
├── pom.xml
├── catalog-core/
│   └── pom.xml
└── catalog-app/
    └── pom.xml
~~~

Root POM thường có packaging pom và khai báo modules. catalog-core là thư viện Java; catalog-app là ứng dụng executable.

**Spring Boot Maven Plugin và cấu hình mainClass nên nằm trong catalog-app/pom.xml**, nơi chứa CatalogApplication. Không áp dụng repackage cho root aggregator hoặc core library chỉ vì muốn build toàn reactor.

Build app cùng module phụ thuộc:

~~~bash
./mvnw -pl catalog-app -am clean package
~~~

Nếu app có nhiều main classes, mainClass vẫn trỏ tới entry point mong muốn. Nếu core cũng có class main, không đưa core vào cấu hình Boot plugin của app một cách vô ý.

### 6.5. Chỉ định main class cho spring-boot:run

Khi cần chạy app trong Maven trước khi đóng gói:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.main-class=com.example.catalog.CatalogApplication
~~~

Thuộc tính trên dành cho goal spring-boot:run. Để kiểm soát repackage, cấu hình mainClass trong Spring Boot Maven Plugin. Không mặc định một thuộc tính dành cho run goal sẽ tự thay đổi mọi execution khác.

## 7. Gradle: cấu hình mainClass cho bootJar

### 7.1. Cấu hình Spring Boot DSL

File **build.gradle** (Groovy DSL):

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

springBoot.mainClass là cấu hình cấp project cho main class ứng dụng. Spring Boot Gradle Plugin dùng nó để cấu hình executable archive và bootRun theo cơ chế của plugin.

Đây là lựa chọn phù hợp khi project có nhiều main classes nhưng muốn một entry point mặc định duy nhất.

### 7.2. Cấu hình trực tiếp trên bootJar

Có thể cấu hình task cụ thể:

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Cách này làm rõ archive nào dùng main class nào. Nếu project có nhiều executable archive/tasks, cấu hình task-level giúp từng archive có thể dùng một entry point riêng.

Không cấu hình nhầm task jar. Task jar tạo plain JAR; executable Spring Boot JAR được tạo bởi bootJar.

### 7.3. Kotlin DSL

Với build.gradle.kts, cấu hình project-level:

~~~kotlin
springBoot {
    mainClass.set("com.example.catalog.CatalogApplication")
}
~~~

Hoặc task-level:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    mainClass.set("com.example.catalog.CatalogApplication")
}
~~~

Kotlin DSL dùng Property<String> nên thường gọi set(). Không sao chép Groovy DSL nguyên xi vào Kotlin DSL.

### 7.4. Build và chạy Gradle

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Artifact mặc định:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar build/libs/catalog-app-1.0.0.jar
~~~

Nếu có nhiều main classes, kiểm tra manifest Start-Class có đúng FQCN đã chọn hay không.

### 7.5. Cấu hình main class cho bootRun

Có thể chạy app trực tiếp qua Gradle:

~~~bash
./gradlew bootRun
~~~

Nếu cần cấu hình riêng cho task:

~~~groovy
tasks.named('bootRun') {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Hoặc dùng springBoot.mainClass ở cấp project. bootRun chạy từ main source set. Spring Boot Gradle Plugin cũng có task bootTestRun dành cho test source set; không dùng test main class làm entry point của production bootJar.

## 8. Xử lý project có nhiều main classes

### 8.1. Không phụ thuộc thứ tự dò tự động

Spring Boot Maven Plugin có thể sử dụng **class đầu tiên được compile tìm thấy có method main** nếu không cấu hình mainClass. Vì vậy, khi thêm class migration hoặc CLI mới, kết quả tự dò có thể không còn là class mà nhóm dự định phát hành.

Gradle BootJar tự dò class có public static void main(String[]) trong output của main source set. Khi có nhiều ứng viên, không nên dựa vào cơ chế tự dò hoặc thứ tự quét file; hãy đặt mainClass tường minh.

Điều cần nhớ:

- Maven và Gradle có cơ chế tự dò khác nhau.
- Build thành công không chứng minh entry point đã chọn đúng.
- Một executable archive cụ thể có một Start-Class.
- Nếu cần nhiều ứng dụng độc lập, tạo nhiều artifact/module hoặc task đóng gói được cấu hình riêng.

### 8.2. Chọn một main class canonical

Giả sử project có:

~~~text
com.example.catalog.CatalogApplication
com.example.catalog.tools.MigrationTool
com.example.catalog.tools.ReindexTool
~~~

Nhưng artifact chính là Catalog API. Maven:

~~~xml
<configuration>
    <mainClass>com.example.catalog.CatalogApplication</mainClass>
</configuration>
~~~

Gradle:

~~~groovy
springBoot {
    mainClass = 'com.example.catalog.CatalogApplication'
}
~~~

Các class MigrationTool/ReindexTool vẫn có thể được gọi qua task riêng, test hoặc artifact khác; chúng không trở thành entry point của Boot JAR chính.

### 8.3. Khi cần nhiều executable độc lập

Nếu migration tool và web application có lifecycle, dependency hoặc cấu hình runtime khác nhau, tách module:

~~~text
catalog-platform/
├── catalog-core/
├── catalog-api/
│   └── CatalogApplication.java
└── catalog-migration/
    └── MigrationApplication.java
~~~

Mỗi app module có main class, plugin configuration, artifact name, runtime dependency graph và deployment configuration riêng. Cách này thường dễ vận hành hơn một Boot JAR duy nhất có nhiều entry point.

### 8.4. Nhiều task BootJar trong Gradle

Có thể tạo nhiều executable archive task khi có nhu cầu rõ ràng. Mỗi task cần mainClass, classpath, archive classifier, output destination và task dependencies đúng. Không chỉ đăng ký một BootJar task rồi giả định plugin tự cấu hình mọi property giống task bootJar mặc định.

Trước khi tạo nhiều task tùy chỉnh, cân nhắc tách module. Nếu vẫn dùng một module, kiểm tra manifest và chạy thử từng archive để bảo đảm mỗi file khởi động đúng ứng dụng.

## 9. Chẩn đoán khi không tìm thấy main class

### Bước 1: xác định đúng module và task

Maven:

~~~bash
./mvnw -pl catalog-app -am clean package
~~~

Gradle:

~~~bash
./gradlew :catalog-app:clean :catalog-app:bootJar
~~~

Xác nhận plugin được áp dụng ở module chứa application class, không phải root aggregator hoặc library module.

### Bước 2: xác nhận source file nằm trong main source set

Maven:

~~~text
catalog-app/src/main/java/com/example/catalog/CatalogApplication.java
~~~

Gradle Java plugin mặc định dùng src/main/java. Nếu class chỉ ở src/test/java, plugin không tìm thấy nó trong main output.

### Bước 3: kiểm tra method signature

Tìm đúng:

~~~java
public static void main(String[] args)
~~~

Kiểm tra public, static, void, tên main viết thường và parameter String[]. Method phải nằm trong class đúng package và compile thành công.

### Bước 4: kiểm tra class đã compile

Maven:

~~~text
target/classes/com/example/catalog/CatalogApplication.class
~~~

Gradle:

~~~text
build/classes/java/main/com/example/catalog/CatalogApplication.class
~~~

Nếu file không tồn tại, xử lý lỗi compile, source set hoặc code generation trước khi sửa plugin.

### Bước 5: kiểm tra FQCN

Nếu source khai báo package com.example.catalog thì cấu hình com.example.catalog.CatalogApplication. Không dùng package cũ sau refactor.

### Bước 6: cấu hình mainClass tường minh

Maven đặt mainClass trong spring-boot-maven-plugin. Gradle đặt springBoot.mainClass hoặc bootJar.mainClass. Đây là bước sửa chính khi có nhiều ứng viên hoặc tự dò chọn sai.

### Bước 7: clean và build lại

Maven:

~~~bash
./mvnw -B -ntp clean package
~~~

Gradle:

~~~bash
./gradlew --no-daemon clean bootJar
~~~

Clean loại output cũ còn sót lại sau khi class được đổi tên hoặc xóa.

## 10. Chẩn đoán khi có nhiều main classes

### 10.1. Tìm method main trong source

Linux/macOS:

~~~bash
grep -R -n "static void main" src/main/java
~~~

PowerShell:

~~~powershell
Get-ChildItem src/main/java -Recurse -Filter *.java |
    Select-String -Pattern 'static void main'
~~~

Đây là tìm kiếm nhanh, không phải Java parser. Nó có thể bỏ sót method được format nhiều dòng hoặc tìm thấy comment/string. Dùng kết quả để xác định class cần đọc và xác minh.

### 10.2. Kiểm tra compiled class bằng javap

~~~bash
javap -classpath target/classes -public com.example.catalog.CatalogApplication
~~~

Output cần có:

~~~text
public static void main(java.lang.String[]);
~~~

Nếu javap báo class not found, kiểm tra classpath, output directory và package name.

### 10.3. Không nhầm test main với app main

Test utility có thể chứa main method nhưng không nên là entry point production.

- Maven Boot repackage dùng compiled application classes của module.
- Gradle BootJar tìm trong main source set.
- Gradle bootTestRun dành cho test source set, không thay thế bootJar.

Nếu test helper nằm nhầm trong src/main/java, chuyển về src/test/java nếu nó chỉ phục vụ test.

## 11. Kiểm tra manifest và nội dung archive

### 11.1. Liệt kê JAR

Maven:

~~~bash
jar tf target/catalog-app-1.0.0.jar
~~~

Gradle:

~~~bash
jar tf build/libs/catalog-app-1.0.0.jar
~~~

Executable Boot JAR thông thường có:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/...
~~~

Nếu chỉ thấy class ở package root và không có BOOT-INF, có thể bạn đang xem plain JAR.

### 11.2. Đọc manifest trên Linux/macOS

~~~bash
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
~~~

Với Spring Boot 3.3, manifest điển hình:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.CatalogApplication
~~~

Nếu Start-Class là class cũ hoặc class khác, cấu hình mainClass chưa áp dụng hoặc artifact được kiểm tra không phải output mới nhất.

### 11.3. Đọc manifest trên Windows PowerShell

~~~powershell
jar xf target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
~~~

jar xf giải nén manifest vào working directory hiện tại. Dùng thư mục tạm hoặc kiểm tra trước để tránh ghi đè file có sẵn.

### 11.4. Chạy đúng artifact

Maven:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

Gradle:

~~~bash
java -jar build/libs/catalog-app-1.0.0.jar
~~~

Nếu dùng classifier hoặc finalName tùy chỉnh, thay bằng đường dẫn thực tế. Không chọn file đầu tiên theo wildcard khi thư mục có plain JAR và Boot JAR.

## 12. Tình huống đặc biệt

### 12.1. Kotlin top-level main

Với Kotlin:

~~~kotlin
fun main(args: Array<String>) {
    println("KOTLIN_APP_STARTED")
}
~~~

Compiler thường tạo Java class có hậu tố Kt, ví dụ:

~~~text
CatalogApplicationKt
~~~

FQCN có thể là:

~~~text
com.example.catalog.CatalogApplicationKt
~~~

Nếu dùng @file:JvmName, tên generated class thay đổi. Cấu hình tên JVM class được compiler sinh, không đoán theo tên file .kt.

### 12.2. Main class từ generated sources

Annotation processor hoặc code generator có thể tạo class main. Xác nhận generated directory đã được gắn vào main compile source set và class xuất hiện trong compiled output trước repackage.

Nếu generated file chỉ được tạo sau một task không liên kết với compileJava, package có thể chạy mà không có class dự kiến.

### 12.3. Module core cũng có main method

Một library module có thể chứa demo/test main. Không áp Spring Boot plugin lên core chỉ vì nó có method main. Core thường tạo plain JAR; app module cấu hình entry point của riêng nó.

### 12.4. Project không cần executable archive

Nếu sản phẩm chỉ là thư viện, dùng Maven jar packaging hoặc Gradle Java/Java Library plugin. Spring Boot Maven Plugin có layout NONE để bundle dependencies mà không có bootstrap loader, nhưng archive đó **không phải executable JAR để chạy bằng java -jar**.

### 12.5. Class có main nhưng không khởi động Spring

Một class có main method có thể là entry point Java hợp lệ nhưng không nhất thiết khởi động Spring context. Nếu cần Spring Boot, main method phải khởi tạo ứng dụng, ví dụ SpringApplication.run. Main method tồn tại không chứng minh cấu hình Spring đúng.

## 13. Java 17 utility kiểm tra main method

Tạo file **MainMethodInspector.java** trong thư mục công cụ độc lập:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class MainMethodInspector {

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java MainMethodInspector.java <fully-qualified-class>");
            System.exit(2);
        }

        Class<?> type = Class.forName(args[0]);
        Method main = type.getMethod("main", String[].class);

        int modifiers = main.getModifiers();
        boolean valid = Modifier.isPublic(modifiers)
                && Modifier.isStatic(modifiers)
                && main.getReturnType() == void.class;

        if (!valid) {
            System.err.println("INVALID_MAIN_METHOD");
            System.exit(1);
        }

        System.out.println("MAIN_METHOD_OK:" + type.getName());
    }
}
~~~

Đây là Java 17 source-file launcher program đầy đủ. Nó dùng reflection để tải class theo tên và tìm method có parameter String[].

Chạy sau khi application classes đã compile:

~~~bash
java -cp target/classes MainMethodInspector.java com.example.catalog.CatalogApplication
~~~

Khi thành công, stdout:

~~~text
MAIN_METHOD_OK:com.example.catalog.CatalogApplication
~~~

Nếu không tìm thấy class hoặc method, chương trình ném exception. Nếu method tồn tại nhưng không đúng modifiers/return type, stderr là INVALID_MAIN_METHOD và exit code 1.

**Giới hạn:** chương trình này chỉ kiểm tra method reflection ở compiled class. Nó không xác minh @SpringBootApplication, dependency graph, manifest hoặc khả năng khởi động của toàn ứng dụng. Đây là công cụ chẩn đoán nhỏ, không thay thế Maven/Gradle packaging.

## 14. Quy trình chẩn đoán từ đầu đến cuối

1. Xác định artifact cần tạo là executable Boot JAR hay plain library JAR.
2. Xác định module chứa application class.
3. Kiểm tra class nằm trong main source set.
4. Kiểm tra method có đúng public static void main(String[]).
5. Kiểm tra package và FQCN.
6. Nếu có nhiều main classes, chọn một entry point cho artifact.
7. Cấu hình mainClass trong Spring Boot Maven/Gradle Plugin.
8. Chạy clean build bằng Wrapper.
9. Xác nhận class đã compile.
10. Xác nhận archive có Boot layout.
11. Đọc manifest và kiểm tra Start-Class.
12. Chạy java -jar trên đúng file.
13. Nếu chạy sai app, kiểm tra classifier, output directory và artifact cũ.
14. Nếu runtime không nạp được class, kiểm tra dependency/module/classloader sau khi entry point đã đúng.

### 14.1. Chuỗi lệnh Maven

~~~bash
./mvnw -B -ntp clean package
javap -classpath target/classes -public com.example.catalog.CatalogApplication
jar tf target/catalog-app-1.0.0.jar
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
java -jar target/catalog-app-1.0.0.jar
~~~

### 14.2. Chuỗi lệnh Gradle

~~~bash
./gradlew --no-daemon clean classes bootJar
javap -classpath build/classes/java/main -public com.example.catalog.CatalogApplication
jar tf build/libs/catalog-app-1.0.0.jar
unzip -p build/libs/catalog-app-1.0.0.jar META-INF/MANIFEST.MF
java -jar build/libs/catalog-app-1.0.0.jar
~~~

Trên Windows không có unzip mặc định, dùng jar xf để trích manifest rồi Get-Content. javap và jar thuộc JDK.

## 15. Các lỗi thường gặp và cách sửa

**1. Không có method main.** Class chỉ có @SpringBootApplication. Thêm public static void main(String[] args) và gọi SpringApplication.run.

**2. Method main không public.** Đặt public để Java launcher gọi được.

**3. Method main không static.** Java 17 cần static main.

**4. Return type sai.** Dùng void, không dùng int hoặc kiểu khác.

**5. Tên method viết hoa.** Main khác main; sửa chính tả.

**6. Parameter không phải String array.** Dùng String[] hoặc String....

**7. Main class nằm trong src/test/java.** Chuyển vào src/main/java nếu đó là app entry point.

**8. Cấu hình sai FQCN.** Kiểm tra package declaration, tên class và chữ hoa/thường.

**9. Class chưa compile.** Chạy compile/classes và xử lý lỗi compiler trước repackage/bootJar.

**10. Plugin nằm sai module.** Áp Boot plugin vào app; core library dùng plain JAR.

**11. Maven không chạy repackage.** Kiểm tra starter parent, plugin execution và package lifecycle.

**12. Maven tự chọn main class không mong muốn.** Đặt mainClass trong spring-boot-maven-plugin.

**13. Gradle bootJar chọn nhầm entry point.** Đặt springBoot.mainClass hoặc bootJar.mainClass.

**14. Có nhiều main classes.** Chọn FQCN cho artifact; không phụ thuộc thứ tự tự dò.

**15. Cấu hình main class trong maven-jar-plugin.** Spring Boot repackage quản lý manifest. Chuyển cấu hình sang Spring Boot Maven Plugin.

**16. Đặt app class vào Main-Class của Boot manifest.** Main-Class phải là Boot Launcher; app class nằm ở Start-Class.

**17. Start-Class cũ sau refactor.** Cập nhật mainClass, clean và build lại.

**18. Build nhầm root aggregator.** Chạy từ đúng module hoặc dùng -pl/-am và task path.

**19. Generated main class chưa vào source set.** Đăng ký generated source directory và task dependency trước compile.

**20. Kotlin dùng sai tên generated class.** Kiểm tra hậu tố Kt hoặc @JvmName rồi cấu hình FQCN.

**21. Chạy nhầm plain JAR.** Kiểm tra BOOT-INF và manifest; chọn output repackage/bootJar.

**22. Artifact cũ còn trong target/build.** Chạy clean trước khi kiểm tra output.

**23. Nhiều artifact có classifier.** Xem output directory, classifier và task; chọn đúng file.

**24. Build success nhưng java -jar báo no main manifest attribute.** Có thể đang chạy plain JAR hoặc repackage chưa chạy. Kiểm tra archive/manifest.

**25. Main class có trong source nhưng không có trong JAR.** Kiểm tra module, source set, compile output và archive configuration.

**26. Manifest có Start-Class đúng nhưng ClassNotFoundException.** Xác minh class thực có trong BOOT-INF/classes, đúng package và đúng artifact.

**27. NoClassDefFoundError sau khi entry point đúng.** Đây là vấn đề dependency/runtime classpath. Kiểm tra BOOT-INF/lib, dependency scope và resolution.

**28. Nhiều ứng dụng nhưng muốn một JAR chọn theo profile.** Start-Class của archive đã cố định. Tách artifact/module hoặc dùng một main class điều phối profile/command có chủ đích.

**29. Áp Boot plugin lên library chỉ vì có demo main.** Library không cần executable archive. Dùng Java Library plugin và tách demo app nếu cần.

**30. Không kiểm tra artifact sau build.** Build success chưa chứng minh Start-Class đúng. Đọc manifest và chạy đúng file JAR.

## 16. Checklist trước khi phát hành executable JAR

- [ ] Xác định đúng module ứng dụng.
- [ ] Main class nằm trong main source set.
- [ ] Class có public static void main(String[] args).
- [ ] Package và FQCN đúng, phân biệt chữ hoa/chữ thường.
- [ ] Nếu có nhiều main classes, đã chọn entry point cụ thể.
- [ ] Maven: spring-boot-maven-plugin có mainClass đúng.
- [ ] Gradle: springBoot.mainClass hoặc bootJar.mainClass đúng.
- [ ] Không cấu hình nhầm maven-jar-plugin hoặc task jar.
- [ ] Plugin được áp dụng trong module app, không phải core/root aggregator.
- [ ] Clean build hoàn tất.
- [ ] Class đã xuất hiện trong target/classes hoặc build/classes/java/main.
- [ ] Executable archive có Boot layout.
- [ ] Manifest có Boot Launcher ở Main-Class.
- [ ] Manifest có FQCN ứng dụng ở Start-Class.
- [ ] Đã chạy java -jar trên đúng artifact.
- [ ] Nếu multi-module, artifact và classpath đến từ đúng module.
- [ ] Nếu Kotlin, đã dùng tên generated JVM class.
- [ ] Nếu không cần executable, dùng plain JAR thay vì ép repackage.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Configuring Executable Archive Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Executable JAR Launcher and Manifest: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html
- Oracle Java 17 — JAR File Specification and Main-Class: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Oracle Java 17 — java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java 17 — javap tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle 8.5 — Java Plugin and Source Sets: https://docs.gradle.org/8.5/userguide/java_plugin.html

**Kết luận:** Khi Spring Boot báo không tìm thấy main class hoặc có nhiều main class, hãy xác minh class entry point có đúng chữ ký Java 17 và nằm trong main source set hay không. Sau đó cấu hình **FQCN** trực tiếp ở Spring Boot Maven/Gradle Plugin. Kiểm tra **Main-Class** của Boot Launcher, **Start-Class** của ứng dụng, nội dung archive và kết quả java -jar. Một executable Boot JAR cần một entry point được chọn rõ ràng; nếu có nhiều ứng dụng độc lập, hãy phát hành artifact/module riêng thay vì phụ thuộc vào cơ chế tự dò.