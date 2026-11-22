# Đóng gói và chạy artifact độc lập với IDE

Một ứng dụng Java chạy được trong IntelliJ IDEA, Eclipse hoặc VS Code chưa chắc đã chạy được khi đưa sang máy khác. IDE có thể tự chọn main class, bổ sung thư viện vào classpath, đặt working directory, truyền VM options, nạp biến môi trường và dùng JDK đã cấu hình riêng. Khi đóng gói để phân phối, các thông tin đó phải được thể hiện trong artifact, distribution hoặc lệnh khởi chạy.

Mục tiêu của bài thực hành này là tạo artifact từ Maven hoặc Gradle, xác định cách artifact mang theo dependency, rồi chạy bằng lệnh Java trên terminal mà không phụ thuộc IDE. Các lựa chọn phổ biến gồm JAR thông thường, executable JAR có manifest, fat/uber JAR gộp dependency và distribution chứa JAR cùng thư viện, script khởi chạy. Mỗi kiểu có ưu điểm và giới hạn riêng.

## 1. Artifact là gì và vì sao cần kiểm tra ngoài IDE?

Artifact là đầu ra được build tạo ra để sử dụng hoặc phân phối. Với ứng dụng Java, artifact thường là:

- File JAR chứa class và resource của ứng dụng.
- Fat JAR hoặc uber JAR chứa cả class của dependency.
- ZIP/TAR distribution chứa JAR, thư viện, script và file cấu hình mẫu.
- WAR hoặc EAR dành cho môi trường application server.
- Native package hoặc installer được tạo bằng công cụ đóng gói phù hợp.
- Container image chứa runtime và ứng dụng.

Trong bài này, trọng tâm là ứng dụng Java có điểm vào main và có thể chạy từ terminal.

Khi chạy từ IDE, IDE thường làm nhiều việc thay người phát triển:

1. Biên dịch source thành class.
2. Tìm main class đã chọn trong Run Configuration.
3. Tạo classpath từ module và dependency.
4. Truyền VM options và application arguments.
5. Đặt working directory.
6. Cung cấp environment variables.
7. Chọn JDK để chạy.

Khi chạy artifact độc lập, các thông tin cần thiết phải được đóng gói hoặc truyền vào một cách tường minh. Nếu chỉ kiểm tra bằng nút Run của IDE, ta chưa chứng minh artifact đã được đóng gói đúng.

## 2. Chương trình Java tối thiểu có thể chạy

Một ứng dụng Java cần một phương thức main phù hợp để JVM bắt đầu thực thi:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
~~~

Tên lớp đầy đủ là com.example.app.Main. Tên này sẽ được ghi vào manifest hoặc dùng trong lệnh java với classpath.

Với Maven theo cấu trúc mặc định:

~~~text
my-app/
  pom.xml
  src/
    main/
      java/
        com/example/app/Main.java
      resources/
    test/
      java/
~~~

Với Gradle:

~~~text
my-app/
  settings.gradle.kts
  build.gradle.kts
  src/
    main/
      java/
        com/example/app/Main.java
      resources/
    test/
      java/
~~~

Source trong src/main/java được compile; resource trong src/main/resources được đưa vào output theo cấu hình mặc định. Khi đóng gói JAR, class và resource thường nằm ở root của archive theo package path.

## 3. JAR thông thường chứa những gì?

JAR là một file ZIP có quy ước dành cho Java. Một JAR ứng dụng thông thường thường chứa:

~~~text
my-app.jar
  META-INF/
    MANIFEST.MF
  com/
    example/
      app/
        Main.class
  application.properties
  templates/
    welcome.html
~~~

JAR thường chứa class/resource của chính project. Nó không mặc nhiên chứa các dependency bên ngoài. Nếu ứng dụng dùng thư viện như Jackson hoặc PostgreSQL JDBC driver, các JAR đó có thể nằm riêng trong dependency cache hoặc thư mục lib.

Vì thế, cần phân biệt:

- JAR thông thường: chứa output của project.
- Executable JAR: có thông tin điểm vào để JVM biết main class.
- Fat/uber JAR: gộp dependency vào cùng một JAR.
- Distribution: chứa JAR ứng dụng, dependency riêng và script khởi chạy.

Executable JAR không đồng nghĩa với fat JAR. Một JAR có Main-Class vẫn có thể thiếu dependency runtime.

## 4. Manifest và thuộc tính Main-Class

JAR có thể chứa file META-INF/MANIFEST.MF. Manifest là metadata cho archive. Để chạy bằng lệnh java -jar, manifest thường cần thuộc tính Main-Class:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
~~~

Tên main class phải là fully qualified class name, không có phần mở rộng .class và không dùng dấu slash thay dấu chấm.

Chạy:

~~~bash
java -jar my-app.jar
~~~

JVM đọc Main-Class và gọi phương thức main. Nếu truyền đối số:

~~~bash
java -jar my-app.jar --mode report input.csv
~~~

Các đối số sau tên JAR được chuyển vào mảng args của main.

### 4.1. Lệnh java -jar và classpath

Lệnh java -jar dùng manifest của JAR làm điểm vào. Không nên kỳ vọng thêm -cp hoặc -classpath vào cùng lệnh sẽ bổ sung classpath như cách chạy main class trực tiếp; khi dùng -jar, classpath người dùng bị bỏ qua theo quy tắc launcher.

Nếu cần chỉ định classpath ở command line, chạy main class trực tiếp:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Trên Windows, dấu phân cách các mục classpath là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;lib/*" com.example.app.Main
~~~

Trên Linux/macOS, dấu phân cách classpath là dấu hai chấm. Wildcard lib/* có thể giúp nạp các JAR trực tiếp trong thư mục lib; không nên giả định nó quét đệ quy các thư mục con.

### 4.2. Manifest Class-Path cho thin JAR

Manifest có thuộc tính Class-Path để chỉ các JAR phụ trợ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/jackson-databind.jar lib/jackson-core.jar
~~~

Các đường dẫn trong Class-Path được phân giải tương đối với vị trí JAR chứa manifest. Chúng phải trỏ đến file thực sự tồn tại và có thể truy cập. Với ứng dụng phân phối, cần giữ nguyên cấu trúc thư mục dự kiến.

Class-Path trong manifest hữu ích cho thin JAR nhưng cần cập nhật khi dependency thay đổi. Công cụ build có thể tạo danh sách này từ runtime dependencies.

## 5. Chọn kiểu đóng gói phù hợp

| Kiểu | Nội dung | Cách chạy | Điểm cần chú ý |
|---|---|---|---|
| JAR thường | Class/resource của project | Cần classpath và main class | Không tự có dependency |
| Executable thin JAR | JAR project và Main-Class; dependency nằm riêng | java -jar nếu manifest Class-Path đúng | Cần giữ cấu trúc lib |
| Fat/uber JAR | Class/resource project và dependency được gộp | java -jar | Có thể xung đột resource, service và chữ ký |
| Application distribution | JAR, lib, script và cấu trúc thư mục | Chạy script trong bin | Có nhiều file nhưng dễ vận hành |
| Container image | Ứng dụng cùng runtime và cấu hình image | Chạy container | Cần quản lý image, runtime và môi trường |

Không có một lựa chọn tối ưu cho mọi ứng dụng. Fat JAR thuận tiện khi cần một file để chuyển giao. Distribution phù hợp hơn khi cần script khởi chạy, nhiều dependency, cấu hình JVM hoặc thư mục làm việc rõ ràng.

## 6. Chuẩn bị môi trường Java để chạy artifact

Máy chạy artifact cần có Java runtime tương thích với bytecode và thư viện mà ứng dụng sử dụng.

Kiểm tra:

~~~bash
java -version
~~~

Kiểm tra compiler nếu cần build tại máy:

~~~bash
javac -version
~~~

Ứng dụng được compile với JDK mới hơn có thể không chạy trên runtime cũ hơn. Ví dụ class file được tạo cho Java 21 không thể chạy trên Java 17. Có thể xuất hiện lỗi UnsupportedClassVersionError.

Với Maven Compiler Plugin, dùng release để xác định API/bytecode mục tiêu:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Giá trị 17 chỉ là ví dụ. Hãy chọn version phù hợp với runtime mà người dùng cuối có thể cài. Compile với --release giúp giới hạn API Java theo phiên bản mục tiêu; nó không bảo đảm dependency bên ngoài cũng tương thích.

JAR không chứa JVM. Nếu máy đích không có runtime phù hợp, cần yêu cầu cài Java, đóng gói runtime riêng hoặc tạo ứng dụng native/package bằng công cụ phù hợp.

## 7. Đóng gói executable JAR bằng Maven

Maven mặc định tạo JAR trong thư mục target khi project có packaging jar. Có thể cấu hình Maven JAR Plugin để ghi Main-Class vào manifest.

Ví dụ POM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.app.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build:

~~~bash
./mvnw clean package
~~~

Trên Windows nếu project không có Maven Wrapper dạng shell, dùng mvnw.cmd:

~~~powershell
.\mvnw.cmd clean package
~~~

Artifact thường nằm tại:

~~~text
target/my-app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar target/my-app-1.0.0.jar
~~~

Ví dụ này tạo executable JAR có Main-Class. Nếu ứng dụng có dependency bên ngoài, JAR vẫn có thể không chạy được cho đến khi dependency được đưa vào classpath hoặc được đóng gói cùng.

### 7.1. Thin JAR với dependency riêng

Một cấu trúc phân phối có thể là:

~~~text
app/
  my-app.jar
  lib/
    jackson-databind.jar
    jackson-core.jar
    jackson-annotations.jar
~~~

JAR ứng dụng có thể ghi Class-Path trỏ đến các file trong lib. Maven JAR Plugin hỗ trợ tạo manifest classpath dựa trên dependency:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>com.example.app.Main</mainClass>
                <addClasspath>true</addClasspath>
                <classpathPrefix>lib/</classpathPrefix>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

Cấu hình trên tạo manifest Class-Path với prefix lib/. Nó không tự đảm bảo thư viện đã được copy vào thư mục lib; cần thêm bước copy runtime dependencies hoặc tạo distribution archive. Nếu manifest trỏ đến lib nhưng thư mục đó thiếu file, ứng dụng sẽ lỗi khi nạp class.

Một cách khác là chạy main class với classpath rõ ràng:

~~~bash
java -cp "my-app.jar:lib/*" com.example.app.Main
~~~

Trên Windows:

~~~powershell
java -cp "my-app.jar;lib/*" com.example.app.Main
~~~

Với ứng dụng phân phối cho người dùng, script khởi chạy thường dễ quản lý hơn việc yêu cầu người dùng tự viết classpath.

## 8. Tạo fat JAR bằng Maven Shade Plugin

Fat JAR hoặc uber JAR gộp class và resource của ứng dụng cùng dependency vào một archive. Khi cấu hình đúng, người dùng chỉ cần một file:

~~~bash
java -jar target/my-app-1.0.0-all.jar
~~~

Maven Shade Plugin là một lựa chọn phổ biến:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.app.Main</mainClass>
                    </transformer>
                    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
                <shadedArtifactAttached>true</shadedArtifactAttached>
                <shadedClassifierName>all</shadedClassifierName>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Sau đó:

~~~bash
./mvnw clean package
~~~

Plugin tạo artifact được gắn classifier all theo cấu hình trên. Tên file cụ thể phụ thuộc finalName và project coordinates; kiểm tra thư mục target thay vì đoán tên.

### 8.1. Vì sao cần xử lý resource khi gộp JAR?

Gộp file JAR không đơn giản là giải nén tất cả vào một thư mục. Hai dependency có thể chứa cùng đường dẫn resource. Một số resource cần được hợp nhất theo định dạng, ví dụ:

- META-INF/services: khai báo provider cho Java ServiceLoader.
- File cấu hình framework.
- License/NOTICE.
- Metadata module.
- Manifest.

Nếu chỉ giữ một file khi có nhiều file trùng tên, provider hoặc cấu hình của dependency khác có thể bị mất. ServicesResourceTransformer của Shade Plugin giúp hợp nhất nội dung service descriptor thay vì chỉ giữ một bản.

Các framework hoặc thư viện đặc thù có thể cần transformer/filter bổ sung. Hãy đọc tài liệu của dependency và plugin khi fat JAR chạy khác với ứng dụng trong IDE.

### 8.2. Chữ ký của dependency khi shading

Khi gộp và thay đổi nội dung JAR, chữ ký số của dependency gốc không còn đại diện chính xác cho nội dung sau khi gộp. Không sao chép nguyên các file chữ ký cũ rồi cho rằng fat JAR vẫn được ký hợp lệ.

Nếu phát hành artifact đã shading, hãy dùng quy trình ký cho artifact cuối cùng sau khi hoàn tất việc đóng gói. Giữ lại metadata license/NOTICE theo nghĩa vụ của dependency và kiểm tra policy phân phối.

### 8.3. Xung đột class và resource

Hai dependency có thể chứa cùng một class hoặc resource. Khi đó, thứ tự và cách gộp có thể làm thay đổi class được nạp hoặc file cấu hình được sử dụng.

Các cách xử lý:

- Loại bỏ dependency không cần thiết.
- Exclude module bắc cầu không mong muốn.
- Relocate package khi thật sự cần tránh xung đột và đã kiểm tra tác động.
- Cấu hình transformer cho resource cần hợp nhất.
- Kiểm tra nội dung archive sau khi shading.

Không nên dùng fat JAR như cách che giấu dependency graph. Vẫn cần biết thư viện nào được đưa vào artifact.

## 9. Đóng gói bằng Gradle Application Plugin

Gradle Application Plugin phù hợp khi muốn phân phối ứng dụng cùng dependency và script chạy. Nó tạo distribution với thư mục bin và lib, đồng thời cung cấp task run để chạy ứng dụng trong quá trình phát triển.

Ví dụ build.gradle.kts:

~~~kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}

application {
    mainClass = "com.example.app.Main"
    applicationDefaultJvmArgs = listOf("-Dfile.encoding=UTF-8")
}
~~~

Build distribution:

~~~bash
./gradlew clean installDist
~~~

Gradle tạo cấu trúc tương tự:

~~~text
build/install/my-app/
  bin/
    my-app
    my-app.bat
  lib/
    my-app-1.0.0.jar
    jackson-databind-2.17.2.jar
    jackson-core-2.x.jar
    ...
~~~

Chạy trên Linux/macOS:

~~~bash
./build/install/my-app/bin/my-app
~~~

Chạy trên Windows:

~~~powershell
.\build\install\my-app\bin\my-app.bat
~~~

Application Plugin tạo script với classpath cần thiết và sử dụng main class đã cấu hình. Distribution ZIP có thể được tạo bằng:

~~~bash
./gradlew distZip
~~~

Artifact ZIP thường nằm trong build/distributions. Có thể chuyển ZIP sang máy khác, giải nén và chạy script trong bin.

### 9.1. Task run khác với chạy JAR đã đóng gói

~~~bash
./gradlew run
~~~

Task run chạy ứng dụng từ runtime classpath do Gradle quản lý. Nó hữu ích khi phát triển, nhưng không thay thế kiểm tra distribution. Muốn xác minh artifact độc lập, hãy chạy script từ installDist hoặc giải nén ZIP được tạo.

### 9.2. Cấu hình JVM mặc định

Application Plugin hỗ trợ applicationDefaultJvmArgs để truyền JVM arguments cho script khởi chạy. Có thể dùng cho system property hoặc thiết lập runtime không nhạy cảm.

Không đặt secret trực tiếp vào build script hoặc script distribution. Credential nên được cấp qua môi trường triển khai hoặc secret manager.

## 10. Tạo fat JAR với Gradle

Gradle core không tự biến mọi JAR thành fat JAR chỉ bằng cách thêm Main-Class. Một plugin chuyên dụng như Shadow Plugin thường được dùng để đóng gói dependency.

Ví dụ Kotlin DSL với Shadow Plugin:

~~~kotlin
plugins {
    java
    id("com.gradleup.shadow") version "8.3.9"
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}

tasks.jar {
    manifest {
        attributes["Main-Class"] = "com.example.app.Main"
    }
}

tasks.shadowJar {
    manifest {
        attributes["Main-Class"] = "com.example.app.Main"
    }
}
~~~

Build:

~~~bash
./gradlew clean shadowJar
~~~

Shadow Plugin tạo archive có dependency được gộp theo cấu hình của plugin. Tên task và tên file có thể thay đổi theo plugin version/configuration; xem task output để xác nhận artifact.

Nếu ứng dụng sử dụng ServiceLoader, resource trùng nhau hoặc framework có metadata riêng, cần cấu hình merge/transform tương ứng. Đọc tài liệu version plugin đang dùng và test artifact thực tế.

Đối với nhiều ứng dụng, Application Plugin tạo distribution rõ ràng và dễ debug hơn. Fat JAR thuận tiện khi cần một file, nhưng phải xử lý xung đột class/resource và kiểm tra archive kỹ hơn.

## 11. Chạy JAR bằng classpath khi không dùng fat JAR

Một JAR thường có thể chạy nếu tất cả dependency runtime được cung cấp qua classpath.

Ví dụ thư mục:

~~~text
release/
  app.jar
  lib/
    library-a.jar
    library-b.jar
~~~

Linux/macOS:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "app.jar;lib/*" com.example.app.Main
~~~

Nếu dùng module path thay vì classpath, cách khởi chạy và quy tắc module resolution sẽ khác. Không trộn lẫn classpath và module path khi chưa hiểu module descriptor và dependency module.

### 11.1. Thứ tự classpath

Khi có nhiều phiên bản cùng một class trên classpath, thứ tự tìm kiếm có thể ảnh hưởng class được nạp. Đây là nguyên nhân khó debug khi ứng dụng chạy trong IDE nhưng chạy khác ở máy khác.

Hãy kiểm soát dependency graph và tránh đặt nhiều version trùng lặp trong lib. Maven dependency tree hoặc Gradle dependencyInsight giúp xem version nào được chọn.

### 11.2. Không dựa vào wildcard ngoài ý muốn

Wildcard trong classpath như lib/* giúp nạp các JAR trực tiếp trong thư mục lib. Tuy nhiên, không nên dùng thư mục lib chứa nhiều file không liên quan hoặc nhiều version khác nhau. Distribution cần có danh sách dependency được build tạo ra, không phải thư mục tùy tiện do người dùng tự thêm file.

## 12. Resource và đường dẫn khi chạy ngoài IDE

Một lỗi thường gặp là code đọc file bằng đường dẫn tương đối:

~~~java
Path config = Path.of("config/application.properties");
~~~

Đường dẫn này được tính từ working directory của process. IDE có thể đặt working directory về project root, còn khi chạy JAR từ thư mục khác, đường dẫn sẽ trỏ sang nơi khác.

### 12.1. Resource đóng gói trong JAR

Nếu file là resource bất biến được đóng gói cùng ứng dụng, hãy đọc qua classpath:

~~~java
try (InputStream input = Main.class.getResourceAsStream("/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing defaults.properties");
    }
    Properties properties = new Properties();
    properties.load(input);
}
~~~

ClassLoader resource có thể đọc file nằm trong JAR mà không cần biến nó thành filesystem path. Không giả định URL resource luôn có thể chuyển thành File; khi chạy trong JAR, resource không nhất thiết là file độc lập.

### 12.2. File cấu hình bên ngoài

File cần được người vận hành chỉnh sửa nên đặt ngoài JAR, ví dụ trong thư mục config của distribution hoặc đường dẫn được truyền qua tham số. Có thể dùng system property:

~~~bash
java -Dapp.config=/etc/my-app/application.properties -jar my-app.jar
~~~

Hoặc truyền application argument:

~~~bash
java -jar my-app.jar --config ./config/application.properties
~~~

Ứng dụng cần đọc và xử lý tham số tương ứng. Không ghi file cấu hình vận hành vào trong JAR rồi kỳ vọng người dùng có thể chỉnh trực tiếp mà không rebuild.

## 13. JVM arguments và application arguments

Hai loại đối số thường bị nhầm:

- JVM arguments cấu hình máy ảo, ví dụ heap, system property, garbage collector.
- Application arguments được chuyển vào phương thức main.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -Dapp.env=production -jar my-app.jar --port 8080
~~~

Trong lệnh trên:

- -Xms256m và -Xmx1g là JVM options.
- -Dapp.env=production là system property.
- --port 8080 là application arguments.

Với java -jar, JVM options phải đặt trước -jar và tên file JAR. Các đối số sau tên JAR được chuyển vào ứng dụng.

Có thể đọc system property:

~~~java
String environment = System.getProperty("app.env", "local");
~~~

Và đọc application arguments qua mảng args. Cần định nghĩa rõ thứ tự và cách parse để script khởi chạy có thể truyền giá trị.

## 14. Working directory, environment và file ghi ra

Ứng dụng độc lập cần xác định nơi đọc/ghi file. Không nên dựa vào working directory tình cờ do IDE hoặc shell đặt.

Các lựa chọn:

- Yêu cầu người vận hành chạy từ thư mục distribution root.
- Nhận đường dẫn cấu hình qua tham số.
- Nhận output directory qua system property/environment.
- Dùng user home hoặc thư mục dữ liệu ứng dụng theo OS khi phù hợp.
- Tạo thư mục output nếu được phép và báo lỗi rõ nếu không có quyền.

Ví dụ lấy thư mục từ system property:

~~~java
Path outputDirectory = Path.of(
    System.getProperty("app.outputDir", "output")
).toAbsolutePath().normalize();

Files.createDirectories(outputDirectory);
~~~

Với môi trường production, nên cấu hình đường dẫn rõ và kiểm soát quyền truy cập. Không ghi log, database hoặc dữ liệu người dùng vào thư mục cài đặt nếu thư mục đó có thể read-only.

## 15. Native library và phụ thuộc theo hệ điều hành

Một JAR có thể chứa Java bytecode chạy trên nhiều hệ điều hành, nhưng dependency có native library thì không nhất thiết portable.

Ví dụ:

- JNI/JNA library.
- Native image hoặc executable được gọi từ Java.
- Driver cần binary riêng theo OS/architecture.
- Script launch phụ thuộc shell.

Nếu artifact chứa native library, cần kiểm tra:

- OS và CPU architecture.
- Native binary tương thích runtime/ABI.
- Cách thư viện tìm và extract native resource.
- Quyền thực thi file nếu chạy executable.
- Đường dẫn và thư viện hệ thống cần thiết.

Không giả định một fat JAR luôn portable giữa Windows, Linux và macOS nếu dependency có native component.

## 16. Kiểm tra nội dung artifact

Trước khi gửi artifact, hãy xem archive có chứa file dự kiến.

Liệt kê nội dung JAR:

~~~bash
jar --list --file target/my-app.jar
~~~

Xem manifest:

~~~bash
unzip -p target/my-app.jar META-INF/MANIFEST.MF
~~~

Trên Windows, có thể dùng công cụ jar để liệt kê nội dung. Có thể mở JAR bằng công cụ ZIP hoặc dùng lệnh tương đương của môi trường.

Kiểm tra:

- Main class có tồn tại đúng package/path không?
- Manifest có Main-Class đúng không?
- Resource cần thiết đã được đóng gói chưa?
- Dependency có được kèm theo hoặc trỏ đúng thư mục lib không?
- Không có file secret, local config hoặc debug output ngoài ý muốn?
- Fat JAR có service descriptor/metadata cần thiết không?

Không chỉ nhìn tên file JAR để kết luận nội dung đã đúng.

## 17. Chạy artifact trong môi trường sạch

Một quy trình xác minh tốt là chạy artifact sau khi build từ một thư mục hoặc runner không phụ thuộc IDE.

Ví dụ:

~~~bash
./mvnw clean package
java -jar target/my-app-1.0.0.jar
~~~

Hoặc:

~~~bash
./gradlew clean installDist
./build/install/my-app/bin/my-app
~~~

Để kiểm tra distribution ZIP:

1. Tạo distZip.
2. Copy ZIP sang thư mục tạm hoặc runner sạch.
3. Giải nén.
4. Kiểm tra Java runtime.
5. Chạy script trong bin.
6. Thử tham số, config và resource cần thiết.

Khi có thể, test bằng JRE/runtime đúng với môi trường triển khai. Không nên dựa vào IDE đã cấu hình JDK mới nhất nếu production dùng runtime cũ hơn.

### 17.1. Vì sao không chỉ dùng Maven exec hoặc Gradle run?

Các lệnh như Maven Exec Plugin hoặc Gradle run thường chạy main class với classpath do build tool quản lý. Chúng hữu ích để phát triển và debug, nhưng không chứng minh JAR/distribution đã chứa đủ file và metadata.

Kiểm tra artifact cần chạy chính file đã tạo ra, bằng lệnh java -jar, classpath distribution hoặc script được đóng gói.

## 18. Những lỗi thường gặp khi chạy artifact

| Thông báo/dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| no main manifest attribute | Manifest thiếu Main-Class | Cấu hình main class trong JAR plugin/shading |
| Could not find or load main class | Sai tên lớp hoặc classpath | Kiểm tra fully qualified name và vị trí class |
| NoClassDefFoundError | Thiếu dependency runtime | Tạo fat JAR hoặc cung cấp lib/classpath |
| ClassNotFoundException | Classpath thiếu JAR/class | Kiểm tra đường dẫn và classpath separator |
| UnsupportedClassVersionError | Runtime cũ hơn bytecode | Dùng JDK tương thích hoặc compile với release thấp hơn |
| FileNotFoundException | Working directory hoặc config path sai | Truyền đường dẫn rõ hoặc đọc resource qua classpath |
| Resource không tìm thấy | Resource chưa đóng gói hoặc dùng sai path | Kiểm tra JAR và ClassLoader resource path |
| Service provider không hoạt động | META-INF/services bị mất khi gộp JAR | Cấu hình service resource transformer |
| Chạy khác giữa Windows và Linux | Path, line ending, native library hoặc script | Kiểm tra OS-specific assumptions |
| Permission denied | Script/file không có quyền thực thi hoặc output không có quyền ghi | Sửa permission phù hợp và output path |
| Could not find or load main class khi dùng wildcard | Classpath separator hoặc thư mục sai | Dùng ; trên Windows, : trên Unix-like |
| Heap space | Heap runtime không đủ | Điều chỉnh JVM memory theo workload |

## 19. Chẩn đoán theo thứ tự

Khi artifact chạy trong IDE nhưng thất bại ở terminal:

**Bước 1 — Xác nhận runtime.** Chạy java -version và xác định JDK/JRE mà terminal thực sự sử dụng.

**Bước 2 — Xác nhận artifact.** Kiểm tra đúng file được tạo từ build mới nhất, không chạy nhầm JAR cũ.

**Bước 3 — Xem manifest.** Kiểm tra Main-Class và Class-Path nếu dùng executable thin JAR.

**Bước 4 — Xem nội dung archive.** Xác nhận class, resource và thư viện đã được đóng gói hoặc có mặt trong lib.

**Bước 5 — Kiểm tra classpath.** Xác nhận đường dẫn, wildcard và separator theo OS.

**Bước 6 — Kiểm tra working directory/config.** Xác định file được đọc tương đối hay qua classpath, tham số và system property nào được yêu cầu.

**Bước 7 — Kiểm tra runtime compatibility.** Xem bytecode target, API Java và native dependencies.

**Bước 8 — Chạy từ thư mục sạch.** Giải nén distribution hoặc copy artifact sang vị trí khác để loại bỏ phụ thuộc IDE/workspace.

## 20. Đóng gói ứng dụng cùng script khởi chạy

Script khởi chạy giúp người dùng không phải nhớ classpath, main class và JVM options.

Ví dụ shell đơn giản cho thin JAR:

~~~bash
#!/usr/bin/env sh
APP_HOME=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec java -cp "$APP_HOME/app.jar:$APP_HOME/lib/*" com.example.app.Main "$@"
~~~

Script này minh họa cách tìm distribution root tương đối với vị trí script, rồi chuyển tiếp mọi argument. Cần điều chỉnh separator và cách xử lý path cho Windows nếu hỗ trợ đa nền tảng. Với dự án thực tế, Gradle Application Plugin hoặc công cụ distribution tương ứng có thể sinh script chuẩn hơn.

Trên Windows, script .bat có thể đặt classpath bằng dấu chấm phẩy và gọi main class. Nên test cả hai script nếu distribution hỗ trợ Windows và Unix-like.

Không nhúng secret vào script. Script chỉ nên thiết lập đường dẫn, JVM options không nhạy cảm và gọi ứng dụng; secret phải đến từ môi trường triển khai an toàn.

## 21. Java modules và module path

Ứng dụng có module-info.java có thể được chạy trên module path. Khi đó, module resolution, readability và exports tuân theo Java Platform Module System.

Classpath truyền thống:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Module path:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Đây là hai mô hình khởi chạy khác nhau. Nếu ứng dụng/module có descriptor, hãy đóng gói module dependency đúng cách và xác định module name. Không chuyển tùy tiện một lệnh classpath thành module path mà không kiểm tra module metadata.

Với ứng dụng modular, có thể xem module descriptor trong JAR:

~~~bash
jar --describe-module --file app.jar
~~~

## 22. Runtime riêng, jlink và jpackage

JAR không chứa Java runtime. Nếu muốn phân phối một ứng dụng mà người dùng không phải cài JDK đầy đủ, có thể cân nhắc:

- Yêu cầu cài một JRE tương thích và ghi rõ version.
- Dùng jlink để tạo runtime image tối giản cho các module cần thiết.
- Dùng jpackage để tạo application image hoặc installer theo nền tảng.
- Đóng gói ứng dụng vào container image nếu môi trường triển khai phù hợp.

### 22.1. jlink

jlink tạo runtime image từ các Java modules cần thiết. Nó phù hợp khi ứng dụng modular và xác định được module dependency. Runtime image gắn với nền tảng/architecture mục tiêu; cần tạo riêng cho từng nền tảng cần hỗ trợ.

### 22.2. jpackage

jpackage có thể tạo application image hoặc installer phù hợp nền tảng. Nó có thể đóng gói runtime và application content theo cấu hình. Quá trình tạo package cần thực hiện trên nền tảng tương ứng hoặc theo giới hạn hỗ trợ của toolchain.

Các công cụ này nâng cấp mức độ phân phối so với JAR thuần, nhưng cần kiểm tra license, kích thước runtime, update strategy, code signing và cách cài đặt trên OS đích.

## 23. Artifact trong CI và quy trình phát hành

CI nên tạo artifact từ source commit xác định, sau đó lưu file cùng metadata:

- Commit hash/tag.
- Version ứng dụng.
- JDK/build tool version.
- Tên artifact và loại package.
- Checksum SHA-256.
- SBOM hoặc dependency report nếu quy trình yêu cầu.
- Test/build result.

Không publish artifact chỉ dựa trên tên file. Hãy xác nhận file được tạo từ job đúng, digest được ghi nhận và artifact đã được test theo cách chạy độc lập.

Một pipeline đơn giản:

~~~text
Checkout commit
      |
      v
Build và test
      |
      v
Package JAR/distribution
      |
      v
Chạy smoke test ngoài IDE
      |
      v
Tạo checksum và metadata
      |
      v
Lưu artifact / publish release
~~~

Nếu artifact được ký, hãy ký bản cuối cùng sau khi hoàn tất shading hoặc packaging. Thay đổi archive sau khi ký sẽ làm chữ ký không còn hợp lệ.

## 24. Bài thực hành tổng hợp

Thực hiện theo các bước sau với một ứng dụng Java có main class và ít nhất một dependency runtime.

### Phần A — Build executable JAR bằng Maven

1. Khai báo Main-Class trong Maven JAR Plugin.
2. Chạy clean package.
3. Liệt kê nội dung JAR.
4. Đọc manifest và xác nhận Main-Class.
5. Chạy bằng java -jar.
6. Nếu có dependency, xác định JAR thường đã chứa dependency hay chưa.

### Phần B — Build fat JAR hoặc distribution

Chọn một trong hai:

- Maven Shade Plugin để tạo fat JAR.
- Gradle Application Plugin để tạo distribution chứa lib và script.

Sau khi build, kiểm tra cấu trúc archive/thư mục và xác định tất cả runtime dependencies.

### Phần C — Chạy ngoài IDE

1. Copy artifact hoặc ZIP sang thư mục tạm.
2. Không chạy từ nút Run của IDE.
3. Mở terminal tại vị trí distribution.
4. Kiểm tra java -version.
5. Chạy artifact hoặc script.
6. Truyền một application argument và một JVM system property.
7. Kiểm tra resource, config và output directory.

### Phần D — Kiểm tra tính độc lập

Thử chạy với:

- Working directory khác project root.
- User không có quyền ghi vào thư mục cài đặt.
- Runtime Java đúng version mục tiêu.
- Thư mục config bên ngoài.
- Một máy/runner không có IDE.

Ghi lại các file và thiết lập runtime mà ứng dụng cần. Nếu artifact chỉ chạy khi có một file nằm trong project workspace, hãy xác định file đó là resource cần đóng gói hay config cần cung cấp bên ngoài.

## 25. Những điều cần ghi nhớ

- IDE có thể tự tạo classpath, chọn main class, đặt working directory và truyền JVM options; artifact độc lập phải thể hiện các yêu cầu này rõ ràng.
- JAR thường không tự chứa dependency runtime.
- Main-Class trong manifest cho phép chạy bằng java -jar, nhưng không biến JAR thành fat JAR.
- Thin JAR cần dependency riêng và classpath/manifest Class-Path đúng.
- Fat JAR thuận tiện nhưng cần xử lý resource trùng, ServiceLoader, chữ ký và license metadata.
- Gradle Application Plugin tạo distribution với lib và script khởi chạy.
- Maven JAR Plugin cấu hình manifest; Maven Shade Plugin có thể gộp dependency.
- java -jar và java -cp là hai cách khởi chạy khác nhau; separator classpath là dấu hai chấm trên Unix-like và dấu chấm phẩy trên Windows.
- Resource trong JAR nên được đọc qua classpath; file cấu hình vận hành thường nên đặt bên ngoài artifact.
- JVM arguments đặt trước -jar; application arguments đặt sau tên JAR.
- JAR không mang theo JVM; runtime phải tương thích với bytecode, API và native dependency.
- Hãy kiểm tra manifest, archive contents và chạy artifact trong thư mục sạch ngoài IDE trước khi phát hành.

Đóng gói hoàn tất khi người dùng có thể lấy artifact hoặc distribution, cài runtime phù hợp, cung cấp cấu hình cần thiết và khởi chạy bằng lệnh hoặc script đã xác định. Chạy được trong IDE chỉ chứng minh source có thể chạy trong môi trường phát triển; chạy được artifact từ terminal trong môi trường sạch mới xác nhận quy trình packaging đã mang theo đúng class, resource, dependency và thông tin khởi chạy.
