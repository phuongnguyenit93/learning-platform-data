# Cấu hình mainClass, finalName và thư mục đầu ra trong Maven với Spring Boot

## 1. Vì sao cần hiểu ba thiết lập này?

Khi xây dựng ứng dụng Spring Boot với Maven, câu lệnh `mvn package` có thể tạo nhiều file: class đã biên dịch, test report, một JAR thông thường và một executable JAR do Spring Boot Maven Plugin tái đóng gói. Để tự động chạy hoặc triển khai đúng file, cần trả lời được ba câu hỏi riêng:

- **`mainClass`:** class Java nào là điểm vào của ứng dụng?
- **`finalName`:** tên cơ sở của artifact được tạo tại máy là gì?
- **Thư mục đầu ra:** classes, file trung gian và JAR cuối nằm ở đâu?

Ba yếu tố liên hệ với nhau nhưng không thay thế nhau. Đổi tên archive **không** tự thay main class. Chỉnh nơi lưu compiled classes **không** mặc nhiên đổi nơi lưu JAR. Cấu hình đúng class nhưng không bind goal `repackage` vẫn có thể tạo plain JAR không chạy được bằng `java -jar`.

Bài thuộc mục **Maven với Spring Boot** trong chủ đề **Spring Boot Build Tooling Packaging**. Trọng tâm là cách Maven và Spring Boot Maven Plugin tạo, đặt tên, bố trí và kiểm chứng executable archive. Các chủ đề cấu hình runtime và CI/CD sẽ được đưa vào khi chúng trực tiếp ảnh hưởng đến kết quả đóng gói.

Sau bài học, bạn sẽ biết viết `pom.xml` để chọn main class, đặt tên JAR và đổi thư mục build; chạy một ví dụ Java 17+; kiểm tra manifest và cấu trúc JAR; phát hiện các lỗi xuất hiện khi đổi tên hoặc đường dẫn artifact.

## 2. Phân biệt các khái niệm trước khi cấu hình

| Khái niệm | Nơi thường cấu hình | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| Maven coordinates | `<groupId>`, `<artifactId>`, `<version>` | Định danh module để install/deploy và khai báo dependency | `example.learning:packaging-demo:1.0.0` |
| Application main class | `<mainClass>` của Spring Boot Maven Plugin | Lớp có phương thức `main` được launcher chuyển quyền điều khiển | `demo.Application` |
| Local artifact base name | `<build><finalName>` | Tên file package ở local trước extension/classifier | `demo-service` |
| General build directory | `<build><directory>` | Gốc của file build và output trung gian | `target` |
| Compiled main classes | `<build><outputDirectory>` | Nơi chứa class và resources production sau compile/process-resources | `target/classes` |
| Compiled test classes | `<build><testOutputDirectory>` | Nơi chứa class/resources của test | `target/test-classes` |
| Repackage output directory | `<outputDirectory>` **trong** `spring-boot-maven-plugin` | Nơi goal `repackage` xuất archive của nó | Mặc định là `project.build.directory` |

Các giá trị mặc định Maven theo mô hình thông thường là:

~~~text
project.build.directory       = target
project.build.outputDirectory = target/classes
project.build.testOutputDirectory = target/test-classes
project.build.finalName       = artifactId-version
~~~

Trong một POM thực tế, các giá trị có thể bị thay bởi parent, plugin hoặc thuộc tính dự án. Để biết giá trị thực, cần xem **effective POM** thay vì suy đoán từ tên thư mục.

### 2.1. Nhiều chỗ tên là outputDirectory

Đây là sai lầm dễ gặp nhất. Đặt:

~~~xml
<build>
    <outputDirectory>build/classes</outputDirectory>
</build>
~~~

có nghĩa **đổi thư mục compiled classes**, không có nghĩa file JAR tự xuất hiện tại `build/classes/app.jar`.

Ngược lại, đặt:

~~~xml
<build>
    <directory>build-output</directory>
</build>
~~~

là đổi **build directory tổng**, nên thông thường Maven cùng các plugin sử dụng `project.build.directory` sẽ chuyển sang vùng đó.

Nếu `<outputDirectory>` nằm **bên trong cấu hình Spring Boot Maven Plugin** và goal tương ứng hỗ trợ parameter này, nó là đường dẫn output của goal plugin. Hai cú pháp trông giống nhau nhưng thuộc hai lớp cấu hình khác nhau, nên không được tráo vị trí.

## 3. Maven package và Spring Boot repackage

Với project `<packaging>jar</packaging>`, quá trình điển hình là:

~~~text
src/main/java + src/main/resources
                  |
                  v
      Maven resource/compile phases
                  |
                  v
             target/classes
                  |
                  v
         Maven jar:jar (package)
                  |
                  v
      Plain JAR từ mã project
                  |
                  v
    Spring Boot repackage goal
                  |
                  v
 Executable JAR + Boot launcher
                  |
                  v
              java -jar
~~~

Maven lifecycle có thêm nhiều phase/goal khác; sơ đồ chỉ chọn các bước phục vụ bài học. `spring-boot:repackage` sử dụng archive đã được tạo ở package phase, bố trí class và runtime dependencies theo executable layout Spring Boot, đồng thời cấu hình manifest cho launcher.

Một JAR chỉ chứa class của ứng dụng không tự động chứa mọi runtime dependency. Với ứng dụng Spring Boot, một executable JAR thường có:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/...
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Danh sách trên là **minh họa đã rút gọn**, không phải stdout đầy đủ của `jar tf`. Trong Spring Boot 3.3, các launcher như `org.springframework.boot.loader.launch.JarLauncher` thuộc Boot loader. Tên cụ thể tùy phiên bản Boot và loại archive.

### 3.1. Khi nào goal repackage chạy?

- Nếu dự án sử dụng `spring-boot-starter-parent` và khai báo `spring-boot-maven-plugin` trong `<build><plugins>`, execution `repackage` đã được parent cấu hình cho lifecycle.
- Nếu dự án **không dùng parent Boot**, bạn thường cần tự bind `repackage` vào lifecycle `package` bằng `<executions>`, đồng thời quản lý version plugin.
- Nếu chỉ gọi goal `spring-boot:repackage` trên thư mục vừa clean, chưa có source JAR để tái đóng gói, goal có thể thất bại. Khi cần gọi tường minh, sử dụng `mvn package spring-boot:repackage` để chạy package phase trước, hoặc cấu hình execution và gọi `mvn package` một lần theo quy trình chuẩn.

Không gọi thêm `spring-boot:repackage` sau một `mvn package` vốn đã bind goal ấy nếu không có mục đích rõ ràng. Chạy lặp có thể khiến kết quả và log khó chẩn đoán.

## 4. mainClass: chọn điểm khởi động Java

### 4.1. FQCN là gì?

Ví dụ file Java:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Class được khai báo trong package `demo`, vì vậy **fully qualified class name (FQCN)** là `demo.Application`. Trong cấu hình `mainClass`, dùng FQCN, **không** dùng `Application.java`, `src/main/java/demo/Application.java` hay `Application` khi class nằm trong package.

Spring Boot Maven Plugin có thể tự dò class chứa phương thức `main` nếu `mainClass` chưa được chỉ định. Khi project có nhiều main class, việc dò tự động có thể cho kết quả không mong muốn; hãy cấu hình tường minh.

### 4.2. mainClass nằm ở đâu?

Trong `pom.xml`, đoạn sau đặt trong `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
    </configuration>
</plugin>
~~~

Spring Boot Maven Plugin quản lý thông tin entry point khi `repackage`. Với executable JAR Spring Boot 3.3 có layout chuẩn, manifest thường có hai dòng quan trọng:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.Application
~~~

- **`Main-Class`** là lớp launcher mà JVM gọi trực tiếp khi chạy `java -jar`. Spring Boot launcher biết cách nạp class và các JAR lồng bên trong executable archive.
- **`Start-Class`** là application main class được launcher gọi sau khi đã chuẩn bị classpath.

Vì thế, nếu muốn thay **lớp ứng dụng**, hãy cấu hình `mainClass` của Spring Boot Maven Plugin. **Không** cố đặt `Main-Class: demo.Application` bằng `maven-jar-plugin` để thay chức năng của Boot loader. Khi `repackage` chạy, plugin Boot có thể ghi lại cả `Main-Class` và `Start-Class` theo layout của nó.

### 4.3. Một module có nhiều main class

Giả sử project có `demo.Application` để chạy dịch vụ và `demo.ImportTool` để chạy CLI. Nếu artifact phát hành là server, hãy chọn `demo.Application`. Nếu cần hai ứng dụng độc lập, thường dễ quản lý hơn khi tạo hai module/artifact hoặc cấu hình nhiều executions/classifiers có kiểm soát. Không coi thứ tự class được compiler tạo ra là một hợp đồng chọn main ổn định.

### 4.4. mainClass không phải cấu hình runtime

`mainClass` không quyết định cổng HTTP, profile, URL database hay `application.yml`. Ví dụ:

~~~bash
java -jar target/demo-service.jar --spring.profiles.active=dev
~~~

Với manifest đã đóng gói từ trước, điểm vào vẫn là `demo.Application`. Spring Boot nhận tùy chọn `spring.profiles.active` trong lúc application chạy. Đổi profile và đổi main class là hai trách nhiệm khác nhau.

## 5. finalName: tên file local khác Maven coordinates

Maven mặc định đặt tên JAR thông thường theo `artifactId-version.jar`. Giả sử POM khai báo:

~~~xml
<groupId>example.learning</groupId>
<artifactId>packaging-demo</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Nếu không sửa `finalName`, file package local thường là:

~~~text
target/packaging-demo-1.0.0.jar
~~~

Để đặt tên ngắn:

~~~xml
<build>
    <finalName>demo-service</finalName>
</build>
~~~

File package local thông thường sẽ là:

~~~text
target/demo-service.jar
~~~

**Không viết sẵn đuôi `.jar` trong `finalName` chỉ để đổi extension**: với packaging JAR, Maven plugin chịu trách nhiệm thêm extension theo loại artifact. Đặt `finalName` thành `demo-service.jar` có nguy cơ gây tên `demo-service.jar.jar` hoặc kết quả phụ thuộc plugin.

### 5.1. finalName không đổi GAV

Dù local archive tên `target/demo-service.jar`, tọa độ Maven vẫn là:

~~~text
example.learning:packaging-demo:1.0.0
~~~

`mvn install` sẽ cài artifact theo mô hình repository dựa trên `groupId/artifactId/version`, thông thường có dạng:

~~~text
~/.m2/repository/example/learning/packaging-demo/1.0.0/packaging-demo-1.0.0.jar
~~~

Đường dẫn local Maven repository thực tế có thể tùy cấu hình, và artifact có thể có classifier. Không dùng `finalName` để đổi tên module mà downstream project phải khai báo. Để thay Maven identity cần sửa tọa độ, kèm đánh giá ảnh hưởng lên dependencies.

### 5.2. Classifier có thể sinh nhiều JAR

Nếu cấu hình `spring-boot-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

với `finalName=demo-service`, build có thể tạo:

~~~text
target/demo-service.jar
target/demo-service-exec.jar
~~~

Trong kiểu cấu hình giữ plain artifact cạnh executable artifact, `-exec.jar` là bản được repackage; `demo-service.jar` là plain JAR. Điều này có nghĩa script dùng `target/*.jar` có nguy cơ chọn sai file. Đừng suy đoán archive nào runnable chỉ từ phần mở rộng: đọc manifest hoặc chạy thử chính file cần triển khai.

Nếu **không** cấu hình classifier, Spring Boot `repackage` mặc định thay main artifact bằng executable archive; bản thường có thể được lưu tạm với đuôi `.original`. Plugin cũng có parameter `attach` ảnh hưởng việc artifact repackaged có được gắn với quá trình install/deploy hay không. Dùng classifier/attach khi cần khác biệt về artifact semantics, không chỉ để thay tên local file.

## 6. Thực hành: một Spring Boot executable JAR chạy được

Ví dụ độc lập sau sử dụng **Java 17**, **Spring Boot 3.3.5** và Maven tương thích. Nó không cần web server hoặc database. Mục tiêu là đóng gói JAR `demo-service.jar`, xác nhận `mainClass=demo.Application` rồi chạy được từ command line.

Tạo cấu trúc:

~~~text
packaging-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          Application.java
~~~

### 6.1. POM hoàn chỉnh

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

    <groupId>example.learning</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <finalName>demo-service</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chú ý:

- `spring-boot-starter-parent` cung cấp dependency management và quản lý cấu hình Maven plugin; ví dụ có khai báo Spring Boot plugin nên `repackage` tham gia package lifecycle theo parent.
- `spring-boot-starter` cung cấp runtime Spring Boot cơ bản, **không** tự thêm servlet HTTP server.
- `java.version` là baseline Java phù hợp với Boot 3.3; vẫn phải cài JDK tương thích.
- `finalName` cho file local tên `demo-service.jar`.
- `mainClass` chọn `demo.Application`.
- `<build><directory>` không khai báo nên dùng `target` theo Maven mặc định.

### 6.2. File Java hoàn chỉnh

Đặt trong `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner printResult() {
        return args -> System.out.println("Demo packaged OK");
    }
}
~~~

`CommandLineRunner` chạy khi application context đã khởi tạo. Ứng dụng không chứa web server hay công việc nền dài hạn trong ví dụ, nên tiến trình thường kết thúc sau khi in dòng kiểm chứng.

### 6.3. Build và chạy

Tại thư mục có `pom.xml`:

~~~bash
mvn clean package
java -jar target/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu project có Maven Wrapper, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trong Windows PowerShell.

Với banner và root logging được tắt bằng command-line arguments như trên, chương trình tự in đúng dòng:

~~~text
Demo packaged OK
~~~

Log Maven trong bước `mvn clean package` không phải stdout riêng của chương trình. Nếu không thấy dòng trên, hãy đọc cả thông báo khởi động, manifest và đường dẫn executable JAR thực tế. **Không cần gọi `javac` thủ công**: Maven compile quản lý classpath có dependencies và plugin.

### 6.4. Kiểm tra archive đã đóng gói

~~~bash
jar tf target/demo-service.jar
~~~

Với executable JAR Spring Boot 3.3 thông thường, trong danh sách sẽ có các đường dẫn như:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/demo/Application.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Các dấu `...` chỉ phần đã rút gọn, **không phải stdout chính xác** của `jar tf`. Lệnh `jar tf` dùng công cụ `jar` trong JDK để liệt kê archive.

Nếu trên máy có `unzip`, có thể xem manifest:

~~~bash
unzip -p target/demo-service.jar META-INF/MANIFEST.MF
~~~

Tìm `Start-Class: demo.Application` và `Main-Class` của Boot launcher. Nếu Windows không có `unzip`, dùng công cụ xem ZIP hoặc giải nén manifest sang thư mục tạm. Lệnh chạy `java -jar` là kiểm tra cuối về tính executable.

## 7. Đổi thư mục đầu ra tổng thể

Nếu muốn toàn bộ output của module nằm dưới thư mục `build-output` thay vì `target`, sửa POM:

~~~xml
<build>
    <directory>${project.basedir}/build-output</directory>
    <finalName>demo-service</finalName>
    <!-- Các cấu hình plugin khác của dự án được giữ nguyên -->
</build>
~~~

Đây là **fragment minh họa**, không thay thế toàn bộ nội dung `<build>` đã có trong POM hoàn chỉnh. Sau khi tích hợp vào đúng POM, layout thường là:

~~~text
packaging-demo/
  pom.xml
  src/...
  build-output/
    classes/
    test-classes/
    demo-service.jar
    ...
~~~

Bởi `project.build.outputDirectory` theo mặc định có quan hệ với `project.build.directory`, nơi biên dịch class cũng thường chuyển theo. Parameter `outputDirectory` của `spring-boot:repackage` mặc định là `project.build.directory`, nên archive repackaged có thể đi vào thư mục mới.

Build và chạy lại bằng đường dẫn mới:

~~~bash
mvn clean package
java -jar build-output/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Kết quả chương trình trong ví dụ vẫn là:

~~~text
Demo packaged OK
~~~

**Điều cần cập nhật khi đổi `directory`:** đường dẫn artifact trong script deploy, Dockerfile, pipeline upload/download, lệnh test, tooling tự viết và các bước đọc test reports. `mvn clean` cũng sẽ tác động thư mục build theo cấu hình Maven. Không đổi thư mục build chỉ vì muốn đặt tên file: dùng `finalName` cho nhu cầu đó.

### 7.1. Nếu chỉ muốn đổi thư mục compiled classes

Đây là **một ý định khác**:

~~~xml
<build>
    <outputDirectory>${project.build.directory}/custom-classes</outputDirectory>
</build>
~~~

Thông thường `project.build.outputDirectory` sẽ chỉ đến `target/custom-classes` nếu build directory chưa đổi. Các plugin chuẩn Maven có thể dùng giá trị này để lấy output class, nhưng script hay plugin custom hardcode `target/classes` có thể sai.

Không dùng cú pháp trên nếu yêu cầu là **“đặt JAR tại build-output/”**. Nó không trực tiếp định vị file JAR cuối.

### 7.2. Nếu chỉ muốn đổi output của Spring Boot repackage

Spring Boot Maven Plugin có parameter `outputDirectory` **thuộc goal `repackage`**. Ví dụ cú pháp:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>demo.Application</mainClass>
        <outputDirectory>${project.build.directory}/repackaged</outputDirectory>
    </configuration>
</plugin>
~~~

Ý định ở đây là chỉ đạo nơi **goal repackage** ghi archive, không thay thế giá trị `project.build.outputDirectory` của compiler. Vì packaging thường liên kết việc tạo source JAR, repackage, attach và install/deploy, nếu cấu hình plugin-specific output hãy **kiểm tra behavior thực tế của phiên bản plugin đang dùng**: source archive có đúng không, file repackaged nằm ở đâu, file nào sẽ được install/deploy, và script CI chọn đúng archive không.

Với dự án thông thường, nên để parameter `outputDirectory` của repackage theo mặc định `project.build.directory`. Nếu pipeline muốn một thư mục chuyên để publish artifact, có thể copy file đã build thành công sang staging directory trong pipeline mà không làm thay đổi cơ chế Maven compile/repackage.

## 8. Dự án không dùng spring-boot-starter-parent

Một số module dùng parent POM nội bộ của công ty hoặc parent khác Spring Boot. Khi đó **không mặc định** có execution `repackage` được bind vào `package` như ví dụ starter parent.

Cấu hình plugin thường cần version tường minh và execution:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <configuration>
        <mainClass>demo.Application</mainClass>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **fragment đặt trong `<build><plugins>`**, chưa phải POM hoàn chỉnh. Project còn cần dependencies Spring Boot, quản lý version (chẳng hạn import `spring-boot-dependencies` BOM), JDK/compiler phù hợp và một class main đúng. Nếu có nhiều plugin executions cùng phase `package`, xem effective POM và logs để hiểu thứ tự.

Goal `repackage` không tự tạo source JAR từ mã nguồn. Khi cần chạy bằng lệnh tường minh cho project chưa bind execution, ví dụ:

~~~bash
mvn package spring-boot:repackage
~~~

Câu lệnh chạy phase package trước rồi gọi goal. Nếu plugin execution đã bind, thông thường chỉ cần `mvn clean package`. Không sử dụng `mvn spring-boot:repackage` đơn lẻ ngay sau clean và mong nó tự compile/package toàn bộ app.

## 9. Xác minh effective POM và đường dẫn thật

Để biết cấu hình Maven đã được tổng hợp sau parent/inheritance/properties, chạy từ đúng module:

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=project.build.finalName -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.outputDirectory -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.testOutputDirectory -q -DforceStdout
~~~

Giá trị in ra từ Maven Help Plugin giúp xác nhận các thuộc tính build. Tuy nhiên `effective-pom` **không chứng minh** JAR đã tồn tại, đã được repackage hoặc chạy đúng: cần kiểm tra artifact thực tế.

| Câu hỏi | Bằng chứng cần xem |
| --- | --- |
| Maven đang dùng `finalName` nào? | `help:evaluate` cho `project.build.finalName` |
| Thư mục build thực sự ở đâu? | `help:evaluate` cho `project.build.directory` |
| Mã Java đã compile ở đâu? | `project.build.outputDirectory` và class file trên đĩa |
| Plugin repackage đã được bind vào phase nào? | `help:effective-pom` và log `mvn package` |
| JAR executable nằm ở đâu? | File thực tế sau clean/package và cấu hình classifier/output |
| Main class nào nằm trong archive? | `META-INF/MANIFEST.MF`, nhất là `Start-Class` |
| Dependency runtime đã được đóng gói? | Nội dung `BOOT-INF/lib` trong `jar tf` |
| File phát hành có chạy được? | `java -jar` với JDK phù hợp tại môi trường chạy |

Đối với Linux/macOS:

~~~bash
ls -l target/demo-service.jar
jar tf target/demo-service.jar
java -jar target/demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Đối với Windows PowerShell:

~~~powershell
Get-Item .\target\demo-service.jar
jar tf .\target\demo-service.jar
java -jar .\target\demo-service.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Nếu đã chỉnh build directory, đổi `target` trong lệnh thành đường dẫn thật. Nếu có classifier, dùng **đúng tên file executable**. Không dùng wildcard `target/*.jar` mà chưa kiểm tra danh sách: build có thể chứa plain JAR, executable JAR và archives từ các executions khác.

## 10. Quan hệ giữa mainClass và manifest trong các layout khác nhau

Một file `.jar` là ZIP archive có manifest. Nhưng không phải mọi JAR có `Main-Class` đều là Spring Boot executable archive. Spring Boot loader giải quyết nested dependencies trong cấu trúc `BOOT-INF/lib` theo layout mà Maven plugin tạo.

- Với executable **JAR**, code production thường ở `BOOT-INF/classes`, dependencies ở `BOOT-INF/lib`, launcher thường là `JarLauncher`.
- Với executable **WAR**, code và libraries theo layout `WEB-INF`, launcher khác (ví dụ `WarLauncher`) và quy tắc provided dependencies khác.
- Với layout tùy biến như `ZIP` hoặc `NONE`, cách đóng gói/khởi chạy có thể khác. Đặc biệt `NONE` không cung cấp bootstrap loader để tự chạy theo cách executable JAR thông thường.

Nếu application cần deploy như WAR lên servlet container bên ngoài, không đủ chỉ sửa `finalName` từ `.jar` sang `.war`. Phải dùng `<packaging>war</packaging>` và cấu hình ứng dụng/container phù hợp.

Cấu hình `mainClass` của Spring Boot Maven Plugin là nơi lựa chọn application class; lựa chọn layout có thể làm thay đổi launcher `Main-Class`, không đồng nghĩa application code bị đổi.

## 11. CI/CD, Maven multi-module và Dockerfile

### 11.1. Script phụ thuộc tên file

Trước khi sửa `finalName`, pipeline có thể dùng:

~~~text
target/packaging-demo-1.0.0.jar
~~~

Sau khi sửa thành `demo-service`, phải dùng:

~~~text
target/demo-service.jar
~~~

Nếu không clean, file cũ có thể còn trên máy local khiến script chạy nhầm phiên bản. Do đó quy trình kiểm thử tốt thường bắt đầu từ clean workspace hoặc `mvn clean package` rồi **xác minh file cụ thể** trước upload và deploy.

### 11.2. Maven reactor nhiều module

Một project Maven parent/aggregator có thể chứa:

~~~text
project/
  pom.xml
  api/
    pom.xml
    target/
  service/
    pom.xml
    target/
  shared/
    pom.xml
    target/
~~~

Mỗi module mặc định có `target/` của riêng mình. Nếu module `service` đặt `<finalName>demo-service</finalName>`, file có thể nằm ở `service/target/demo-service.jar`, không phải `target/demo-service.jar` tại root aggregator. Đường dẫn CI phải chỉ đúng module chứa Boot executable archive. Các module library thường không cần repackage thành executable JAR.

### 11.3. Artifact JAR khác container image

`spring-boot:build-image` có thể tạo OCI image bằng buildpacks. Tên/tag container image cần cấu hình phù hợp với goal build-image và registry; `finalName` không phải cách chung để đặt tên/tag image. Tương tự, đổi outputDirectory của compiler không làm container image xuất hiện như một JAR trong `target`.

## 12. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `mvn package` xanh nhưng không có file tại `target/` | Build directory đã đổi hoặc module không tạo JAR | Kiểm tra `project.build.directory`, packaging và output thực tế |
| Tên artifact không đúng | `finalName` chưa có hiệu lực hoặc plugin có classifier | In `project.build.finalName`, đọc tên file kết quả |
| `no main manifest attribute` khi `java -jar` | Chạy plain JAR hoặc `repackage` chưa chạy | Xem effective POM, log goal, manifest của chính file đang chạy |
| `ClassNotFoundException` cho application main | `mainClass` sai package, class không được đóng gói, artifact sai | Kiểm tra FQCN, `BOOT-INF/classes` và `Start-Class` |
| Có hai file `demo-service.jar` và `demo-service-exec.jar` | Cấu hình classifier tạo plain và repackaged artifacts riêng | Kiểm tra manifest/contents; chọn đúng archive runnable |
| App chạy bằng `spring-boot:run` nhưng `java -jar` lỗi | Development classpath khác archive, thiếu repackage hoặc dependency runtime | Kiểm tra package lifecycle, `BOOT-INF/lib`, startup log |
| Đặt `<outputDirectory>dist</outputDirectory>` nhưng JAR vẫn trong `target` | Đang đổi nơi compile classes, không đổi archive directory | Dùng đúng `<build><directory>` hoặc bước copy artifact |
| JAR không được install/deploy như mong đợi | Classifier, `attach=false`, output plugin-specific hoặc plugin execution | Kiểm tra hiệu lực của repackage, artifact attachment, repository |
| Đổi `directory` khiến CI upload không thấy JAR | CI hardcode đường dẫn `target` cũ | Cập nhật đường dẫn artifact trong pipeline |
| Build plugin báo không tìm thấy source archive | Chạy repackage trước package hoặc execution sai | Chạy đúng lifecycle; xác minh jar plugin tạo file trước |
| Maven install tên file khác local finalName | Coordinates vẫn dựa trên GAV | Hiểu repo layout theo `groupId/artifactId/version` |
| Chạy nhầm artifact cũ sau khi đổi tên | Thư mục còn file của build trước | Build sạch, kiểm tra file hash/version và tên tuyệt đối |

**Lưu ý về lỗi:** một `ClassNotFoundException` hoặc `NoClassDefFoundError` cũng có thể xuất phát từ runtime classpath, binary incompatibility hoặc cấu hình ứng dụng. Không kết luận lỗi `mainClass` chỉ từ tên exception; cần kết hợp manifest, archive và full stack trace.

## 13. Quy trình kiểm chứng sau khi thay đổi

Khi cần sửa cả main class, file name và đường dẫn build, đi theo thứ tự:

1. **Xác định dự án và module:** đang build JAR, WAR hay multi-module? Có parent `spring-boot-starter-parent` không?
2. **Xác định main class:** kiểm tra package, chữ ký [[public static void main(String[] args)]] và mục tiêu sản phẩm; đặt `<mainClass>` khi cần cố định.
3. **Đặt local filename:** dùng `<build><finalName>`, không đổi `artifactId` nếu chỉ muốn đổi tên file.
4. **Đặt output đúng loại:** dùng `<build><directory>` khi cần đổi build root, giữ `<build><outputDirectory>` cho compiled classes; chỉ chỉnh plugin `outputDirectory` nếu hiểu rõ tác động.
5. **Xem lifecycle:** xác minh `spring-boot:repackage` đã được bind vào `package` hoặc chạy explicit đúng thứ tự.
6. **Build sạch:** `mvn clean package`, không dựa vào file cũ.
7. **Inspect:** xác nhận file cuối đúng path/name, manifest, `BOOT-INF/classes`, `BOOT-INF/lib`.
8. **Run:** `java -jar` với đúng JDK và môi trường, xem exit code/stdout.
9. **Cập nhật consumer:** Dockerfile, CI artifact path, deploy script và lệnh khởi động phải trỏ đúng file.
10. **Kiểm tra artifact repository khi cần:** nếu dùng `mvn install`/`mvn deploy`, xác nhận GAV/classifier/attach theo hợp đồng với downstream consumer.

### Tự kiểm tra kiến thức

**Câu A.** POM khai báo `artifactId=orders`, `version=2.1.0` và `finalName=order-service`. Build directory mặc định, packaging JAR. Tên local archive thường là gì?

**Trả lời:** `target/order-service.jar`, trong khi coordinates vẫn chứa `orders:2.1.0`.

**Câu B.** Đổi `<build><outputDirectory>` thành `target/classes-v2` có khiến JAR được ghi vào `target/classes-v2` không?

**Trả lời:** Không. Thiết lập này chủ yếu thay nơi compiled production classes/resources. Vị trí JAR phụ thuộc build directory và packaging plugin.

**Câu C.** Trong executable JAR, tại sao `Main-Class` thường không phải `demo.Application`?

**Trả lời:** JVM cần Spring Boot launcher để tải thư viện lồng bên trong archive; application main thường được ghi trong `Start-Class`.

**Câu D.** Vì sao có thể chạy `java -jar target/demo-service-exec.jar` nhưng không chạy được `java -jar target/demo-service.jar`?

**Trả lời:** Một cấu hình `classifier=exec` có thể tạo executable archive riêng với plain artifact; phải xem manifest và nội dung file.

**Câu E.** Đổi `finalName` có đổi file trong Maven repository theo artifactId mới không?

**Trả lời:** Không. Tên local package không đồng nghĩa Maven coordinates; Maven install/deploy xác định artifact theo GAV, extension và classifier.

## 14. Tài liệu chính thức

- Maven POM Reference — `directory`, `outputDirectory`, `finalName`: https://maven.apache.org/pom.html
- Maven Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — evaluate: https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html

Khi ứng dụng đang dùng một phiên bản Spring Boot/Maven cũ hơn hoặc mới hơn ví dụ, cần kiểm tra tài liệu **đúng phiên bản plugin**, đặc biệt tên launcher, tham số goal và mặc định của repackage.

**Ghi nhớ:** `mainClass` quyết định lớp ứng dụng được launcher gọi; `finalName` quyết định tên cơ sở của local archive; `project.build.directory` quyết định thư mục build tổng; `project.build.outputDirectory` quyết định nơi compiler đặt classes. Chỉ khi xác nhận được **effective POM → artifact → manifest → java -jar** mới có đủ bằng chứng rằng packaging thực hiện đúng ý định.