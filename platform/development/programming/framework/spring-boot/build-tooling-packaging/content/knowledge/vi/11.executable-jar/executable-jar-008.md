# Cấu hình tên, phiên bản, classifier và vị trí lưu JAR trong Spring Boot (Maven và Gradle)

## 1. Mục tiêu bài học

Khi đóng gói ứng dụng Spring Boot, một bản build có thể tạo **executable JAR** để chạy bằng `java -jar`, đồng thời có thể tạo **plain JAR** chứa class và resource thông thường. Trong thực tế cần quyết định rõ:

- **Tên cơ sở (base name):** JAR được gọi theo tên module, tên dịch vụ hay tên khác?
- **Phiên bản (version):** có xuất hiện trong tên JAR không, lấy từ đâu?
- **Classifier:** dùng hậu tố `exec`, `boot`, `plain` hay không dùng hậu tố để phân biệt các biến thể?
- **Thư mục xuất JAR:** mặc định là `target/` trong Maven hoặc `build/libs/` trong Gradle; khi cần chuyển sang `release-build/`, `build/releases/` thì cấu hình ở đâu?
- **Artifact được phân phối:** pipeline nên chọn executable JAR nào thay vì chọn nhầm plain JAR?

Ví dụ mong muốn cùng một chương trình tạo hai file:

~~~text
demo-service-2.3.0.jar         # plain JAR: class/resource thông thường
demo-service-2.3.0-exec.jar    # Spring Boot executable JAR
~~~

Với cấu hình ví dụ của bài, Maven đặt chúng ở **release-build/**; Gradle đặt chúng ở **build/releases/**. Việc đặt hai file cùng một tên cơ sở không làm chúng có nội dung giống nhau.

**Phiên bản sử dụng để minh họa:** Java 17, Spring Boot 3.3.5, Gradle 8.5, Maven 3.9.x. Đây là bộ phiên bản ví dụ và không được xem là khẳng định phiên bản mới nhất. Mỗi dự án cần kiểm tra tương thích công cụ build, plugin và JDK khi nâng cấp.

## 2. Hiểu đúng khái niệm trước khi đổi tên

### 2.1. Artifact, JAR và executable JAR

**JAR** là một archive định dạng ZIP chứa class Java và resource. **Plain JAR** của Java plugin hoặc Maven JAR Plugin thường chứa cấu trúc như:

~~~text
META-INF/MANIFEST.MF
com/example/demo/ArtifactNamingApplication.class
application.properties
~~~

Một **Spring Boot executable JAR** được đóng gói bằng **spring-boot:repackage** (Maven) hoặc **bootJar** (Gradle), thường có cấu trúc:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/demo/ArtifactNamingApplication.class
BOOT-INF/lib/...
~~~

Executable JAR chứa launcher và dependency runtime cần thiết, nên có thể chạy qua **java -jar** nếu được cấu hình đúng main class. Plain JAR từ ví dụ đơn giản **không phải** executable Boot JAR; nó không tự mang tất cả dependency của ứng dụng và không nên chọn làm file triển khai chỉ vì đuôi cũng là `.jar`.

**Classifier không phải cơ chế khiến JAR chạy được.** Classifier chỉ là phần tên/thuộc tính để phân biệt artifact. Việc executable xuất phát từ cách plugin **đóng gói nội dung và manifest**, không phải từ chuỗi `-exec`.

### 2.2. Tên file khác tọa độ artifact

Trong Maven, tọa độ thường gồm:

~~~text
groupId : artifactId : version [: classifier] : type
~~~

Ví dụ:

~~~text
com.example : jar-naming-demo : 2.3.0 : exec : jar
~~~

- **groupId** nhận diện nhóm hoặc namespace xuất bản.
- **artifactId** nhận diện module.
- **version** là phiên bản artifact trong Maven repository.
- **classifier** là nhãn tùy chọn cho một biến thể được đính kèm.
- **type** thường là `jar`, nhưng còn có các loại artifact khác.

Trong Gradle, `group` và `version` cũng là thông tin metadata của project. **Tên file tại máy** và **tọa độ khi publish** có liên hệ nhưng không đồng nhất. Đặc biệt, đổi **Maven build.finalName** **không đổi** `artifactId` hoặc `version` trong POM.

### 2.3. Bốn thành phần của tên file

Một quy ước phổ biến là:

~~~text
<baseName>-<version>-<classifier>.jar
~~~

Khi không có classifier, bỏ cả dấu nối và giá trị classifier:

~~~text
demo-service-2.3.0.jar
~~~

Khi có classifier `exec`:

~~~text
demo-service-2.3.0-exec.jar
~~~

Gradle còn hỗ trợ thành phần **appendix** và tên extension qua API archive task; thứ tự thông thường là **baseName, appendix, version, classifier, extension**. Maven chủ yếu tạo tên từ **finalName + classifier + extension** cho plugin JAR tương ứng. Đây là những quy tắc tạo **tên file**; không nên suy luận mọi khía cạnh Maven/Gradle publication chỉ từ tên file.

## 3. Mặc định của Maven và Gradle khác nhau như thế nào?

| Vấn đề | Maven với Spring Boot parent | Gradle với Spring Boot plugin |
| --- | --- | --- |
| Version ứng dụng | `<project><version>...` | `version = '...'` |
| Tên cơ sở artifact | `artifactId` | Thường từ `project.name` / base archives name |
| Tên file thông thường | `artifactId-version.jar` | `name-version.jar` |
| Thư mục output | `target/` | `build/libs/` |
| Tạo JAR thường | `maven-jar-plugin` trong package lifecycle | Task `jar` |
| Tạo Boot JAR | Goal `spring-boot:repackage` | Task `bootJar` |
| Classifier Boot JAR mặc định | Không có; Boot thay main JAR | Thường **không có** |
| Classifier plain JAR mặc định | Không cần classifier nếu dùng riêng main JAR; khi repackage không classifier, bản gốc được sao lưu `.original` | **plain** theo convention Spring Boot |
| Thay tên file | `<build><finalName>` | `archiveBaseName`, `archiveVersion`, `archiveClassifier`, `archiveFileName` |
| Đổi thư mục build/artifact | `<build><directory>` hoặc outputDirectory của plugin thích hợp | `destinationDirectory` của task archive |

**Quan trọng:** Spring Boot Gradle Plugin thường cấu hình **jar** với classifier `plain` để có thể build song song cùng **bootJar**. Maven Spring Boot Plugin **không làm tương tự một cách mặc định**: nếu repackage không có classifier, executable Boot JAR thay thế main artifact và bản JAR gốc có thể được giữ trên đĩa với phần đuôi `.original`. Vì thế không nên áp một quy tắc đặt tên duy nhất cho cả hai công cụ khi chưa cấu hình.

## 4. Maven: finalName, project.version, classifier và build.directory

### 4.1. Mặc định Maven không cần cấu hình đặc biệt

Với POM:

~~~xml
<groupId>com.example</groupId>
<artifactId>jar-naming-demo</artifactId>
<version>2.3.0</version>
~~~

Đây là **đoạn trong POM**, không phải file `pom.xml` hoàn chỉnh. Theo quy ước, tên JAR cơ bản là:

~~~text
target/jar-naming-demo-2.3.0.jar
~~~

Giá trị `project.version` là **2.3.0**. Số version **Spring Boot Plugin** (ví dụ **3.3.5**) không tự trở thành version ứng dụng: `3.3.5` là phiên bản công cụ/framework, còn `2.3.0` là version sản phẩm của dự án.

### 4.2. Đổi local filename bằng build.finalName

Trong `pom.xml`:

~~~xml
<build>
    <finalName>demo-service-2.3.0</finalName>
</build>
~~~

Từ đó JAR được đặt tên **demo-service-2.3.0.jar** trong thư mục build đang cấu hình. Tuy nhiên, viết cứng `2.3.0` khiến khi nâng project version lên `2.4.0`, tên file **vẫn có thể giữ 2.3.0** nếu quên sửa.

Nên tham chiếu version project:

~~~xml
<build>
    <finalName>demo-service-${project.version}</finalName>
</build>
~~~

Tương ứng, nếu POM có version 2.3.0 thì finalName được nội suy thành **demo-service-2.3.0**.

**Lưu ý:** `finalName` chỉ là phần tên **không gồm đuôi .jar**. Không ghi `demo-service.jar` vào finalName rồi mong Maven không thêm `.jar`. Ngoài ra, `finalName` là cấu hình output của build, **không phải lời khai đổi Maven coordinates**; khi `mvn install/deploy`, tên trên repository thông thường vẫn theo artifactId/version/classifier.

### 4.3. Đổi thư mục output bằng build.directory

Maven dùng `project.build.directory` làm thư mục output chính. Để chuyển từ `target/` sang **release-build/** dưới project root:

~~~xml
<build>
    <directory>${project.basedir}/release-build</directory>
    <finalName>demo-service-${project.version}</finalName>
</build>
~~~

Khi đó, với version 2.3.0, file JAR được tạo trong:

~~~text
release-build/demo-service-2.3.0.jar
~~~

Nhưng `<directory>` **không phải chỉ đổi nơi chứa JAR**. Nó đổi **thư mục build của Maven**, nên các output khác như `classes`, `test-classes`, báo cáo plugin và file trung gian cũng có thể chuyển từ `target/` sang `release-build/`. Nếu CI đang cố đọc `target/surefire-reports`, `target/classes` hoặc `target/*.jar`, cần cập nhật đường dẫn sau khi đổi directory.

**Không phải lúc nào nên chuyển build.directory.** Nếu chỉ muốn gom artifact phát hành vào một thư mục riêng mà vẫn giữ Maven lifecycle theo convention, có thể dùng bước **copy/publish artifact trong CI** hoặc cấu hình outputDirectory của plugin cụ thể, rồi xác minh chặt chẽ artifact được install/deploy. Bài thực hành dưới đây chọn `build.directory` vì dễ hiểu và làm cả plain/exec JAR ở cùng vị trí.

### 4.4. Spring Boot Maven Plugin: classifier phân biệt executable JAR

Plugin Spring Boot có goal `repackage` để sửa JAR tạo bởi pha `package` thành executable archive. Nếu **không cấu hình classifier**, executable có thể thay bản JAR chính:

~~~text
target/jar-naming-demo-2.3.0.jar          # executable Boot JAR
target/jar-naming-demo-2.3.0.jar.original # bản gốc được lưu tại local build
~~~

`.original` không phải một biến thể Maven classifier được publish tự động và không nên dùng làm artifact triển khai.

Khi cấu hình **classifier exec**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
~~~

... Maven có thể giữ **hai artifact**:

~~~text
demo-service-2.3.0.jar        # JAR thường/main artifact
demo-service-2.3.0-exec.jar   # executable Spring Boot JAR
~~~

Với `spring-boot-starter-parent`, goal **repackage** đã được cấu hình trong execution kế thừa; thêm plugin và cấu hình classifier như trên là đủ cho ví dụ. Nếu không sử dụng Boot parent, cần **gắn goal repackage vào package lifecycle** đúng cách, vì chỉ thêm thông tin phiên bản/dependency trong POM chưa chắc gọi repackage.

**Chi tiết quan trọng:** Classifier của Spring Boot Maven Plugin còn tham gia **chọn nguồn để repackage**. Nếu Maven project đã có một JAR đầu vào mang classifier `exec`, plugin có thể chọn chính artifact ấy để repackage; khi không có, nó sử dụng JAR chính và đính kèm Boot archive dưới classifier `exec`. Do đó, với build phức tạp, cần tránh classifier trùng vô ý giữa nhiều execution của các plugin đóng gói.

### 4.5. attach và classifier liên hệ với install/deploy như thế nào?

Spring Boot Maven Plugin có thuộc tính `attach` (mặc định **true**). Khi executable Boot JAR có **classifier exec**, plugin có thể đính kèm nó như **supplemental artifact** để `mvn install` hoặc `mvn deploy` xuất bản bên cạnh JAR chính.

Ví dụ ở mức khái niệm:

~~~text
com.example:jar-naming-demo:2.3.0       → main/plain JAR
com.example:jar-naming-demo:2.3.0:exec  → executable Boot JAR
~~~

Nếu `<attach>false</attach>`, repackaged JAR vẫn có thể được tạo để sử dụng tại local build, nhưng **không được đính kèm để install/deploy** theo hành vi mặc định của plugin.

Điều này hữu ích khi một module vừa được dùng như thư viện Java, vừa có executable demo. **Plain JAR** có class ở vị trí thường, phù hợp làm dependency; **Boot JAR** có class dưới `BOOT-INF/classes` nên **không nên** dùng như JAR thư viện truyền thống cho module khác.

## 5. Maven: pom.xml đầy đủ, tạo hai JAR tên rõ ràng

Tạo thư mục dự án **jar-naming-demo** và lưu `pom.xml` sau ở root:

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
    <artifactId>jar-naming-demo</artifactId>
    <version>2.3.0</version>
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
        <directory>${project.basedir}/release-build</directory>
        <finalName>demo-service-${project.version}</finalName>

        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <classifier>exec</classifier>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lý giải từng dòng liên quan đến tên/version/path:**

1. `artifactId = jar-naming-demo` là định danh Maven module. **Không bị đổi** khi dùng finalName.
2. `version = 2.3.0` là phiên bản project/artifact.
3. `packaging = jar` yêu cầu xây dựng JAR; đây là giá trị mặc định của nhiều project Maven Java, nhưng ghi tường minh để dễ học.
4. `java.version = 17` là baseline Java của ví dụ Spring Boot 3.x, **không phải** phiên bản của artifact.
5. `directory = .../release-build` đặt thư mục output Maven chung.
6. `finalName = demo-service-\${project.version}` làm tên file chứa version động theo POM. Trong ví dụ, giá trị hiệu lực là `demo-service-2.3.0`.
7. `classifier = exec` tạo **repackaged executable JAR** với hậu tố `-exec`, trong khi JAR chính giữ dạng plain.

Vì Boot parent đã cấu hình execution `repackage`, POM trên không cần khai báo lại execution đó. Nếu dùng parent khác, phải bổ sung execution đúng pha package theo tài liệu Spring Boot.

### 5.1. Mã ứng dụng Java 17 hoàn chỉnh

Tạo file **src/main/java/com/example/demo/ArtifactNamingApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArtifactNamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArtifactNamingApplication.class, args);
    }

    @Bean
    CommandLineRunner printArtifactName() {
        return args -> System.out.println("JAR_NAMING_OK");
    }
}
~~~

Đây là ứng dụng Spring Boot chạy được với Java 17 và starter cơ bản; không mở HTTP server, không cần database và không cần cấu hình `application.properties`. Nó in một dòng để kiểm chứng executable JAR thực sự khởi chạy.

### 5.2. Build Maven và kết quả dự kiến

Từ project root:

~~~bash
./mvnw clean package
~~~

Nếu chưa có Maven Wrapper nhưng có Maven phù hợp:

~~~bash
mvn clean package
~~~

Trên Windows dùng **mvnw.cmd** thay **./mvnw**. Sau build thành công, thư mục **release-build/** sẽ có:

~~~text
release-build/
├── classes/
├── generated-sources/                 # tùy plugin
├── demo-service-2.3.0.jar             # plain JAR
└── demo-service-2.3.0-exec.jar        # executable Boot JAR
~~~

Các thư mục trung gian có thể khác tùy Maven/plugin, nhưng **hai tên JAR trên** là kết quả cần đối chiếu theo cấu hình bài học. Nếu project có thêm plugin đóng gói thì có thể sinh thêm artifact, cần nhìn đúng classifier.

Chạy **đúng** executable JAR:

~~~bash
java -jar release-build/demo-service-2.3.0-exec.jar
~~~

Ngoài log khởi động Spring Boot, dòng stdout do **chính chương trình** in ra là:

~~~text
JAR_NAMING_OK
~~~

Lệnh dưới đây **không phải cách chạy** được bảo đảm cho plain JAR:

~~~bash
java -jar release-build/demo-service-2.3.0.jar
~~~

Plain JAR không được Boot repackaged, nên không có cùng bootstrap/dependency layout. Tùy manifest, có thể xuất hiện thông báo thiếu Main-Class hoặc thiếu class/dependency. Không sửa bằng cách chỉ đổi tên file thành `-exec.jar`.

### 5.3. Vì sao không đặt version cố định trong finalName?

Giả sử nâng phiên bản POM từ **2.3.0** lên **2.4.0**:

- Với `<finalName>demo-service-\${project.version}</finalName>`: tên JAR đổi theo thành **demo-service-2.4.0-exec.jar**.
- Với `<finalName>demo-service-2.3.0</finalName>`: tên JAR vẫn chứa **2.3.0**, dù artifact Maven đã là **2.4.0**.

Trong CI/CD, khác biệt này dễ khiến pipeline chọn nhầm artifact cũ. Tên file có version động hỗ trợ truy vết, nhưng còn phải quản lý clean build và loại bỏ artifact cũ khi phân phối.

## 6. Maven: chọn outputDirectory riêng cho repackage khi thật sự cần

Spring Boot Maven Plugin cung cấp tham số **outputDirectory** cho goal `repackage`. Ví dụ **fragment plugin configuration**, không phải POM đầy đủ:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
        <outputDirectory>${project.build.directory}/delivery</outputDirectory>
    </configuration>
</plugin>
~~~

Ý nghĩa:

- `project.build.directory` là thư mục build chung, mặc định `target` hoặc đã bị đổi bằng `<build><directory>`.
- `outputDirectory` chỉ định nơi plugin **ghi repackaged archive**.
- Cấu hình này **không tự đổi** nơi Maven JAR Plugin tạo plain JAR hoặc nơi mọi task Maven lưu output.

Đoạn này là **một lựa chọn thay thế** cho plugin configuration ở mục 5, không phải thứ cần chèn thêm song song. Khi tách đường dẫn của Boot archive khỏi main JAR, hãy chạy **package/verify**, kiểm tra file thực tế và thử cả **install/deploy** nếu project publish artifact; hệ thống artifact attachment, copy step và CI path phải nhất quán.

**Khuyến nghị:** Nếu chỉ muốn phân phát artifact ở một thư mục release do CI quản lý, thường dễ bảo trì hơn khi giữ `target/` và dùng CI copy/upload **đúng executable JAR**. Đổi outputDirectory không tự thay đổi Maven GAV, không tự sửa đường dẫn đã hard-code trong Dockerfile/pipeline.

## 7. Gradle: phân biệt archive properties của bootJar và jar

Gradle Java Plugin có task **jar**; Spring Boot Gradle Plugin tạo task **bootJar** khi Java plugin được áp dụng. `BootJar` mở rộng `Jar`, nên dùng chung các thuộc tính đặt tên/vị trí archive.

| Thuộc tính Gradle | Công dụng |
| --- | --- |
| **archiveBaseName** | Tên cơ sở, ví dụ `demo-service`. |
| **archiveAppendix** | Phần bổ sung tùy chọn sau baseName. |
| **archiveVersion** | Phần version trong tên file. |
| **archiveClassifier** | Nhãn biến thể, ví dụ `exec` hoặc `plain`. |
| **archiveExtension** | Đuôi archive, với Jar thường là `jar`. |
| **archiveFileName** | Tên file đầy đủ, có thể ghi đè quy tắc ghép các phần trên. |
| **destinationDirectory** | Thư mục chứa file archive. |
| **archiveFile** | Provider của file kết quả, suy ra từ destinationDirectory và archiveFileName. |

Ví dụ ghép tên khi không có appendix:

~~~text
archiveBaseName  = demo-service
archiveVersion   = 2.3.0
archiveClassifier= exec
archiveExtension = jar

=> demo-service-2.3.0-exec.jar
~~~

Nếu classifier rỗng, JAR thành `demo-service-2.3.0.jar`. Nếu muốn bỏ phần version khỏi filename, có thể đặt **archiveVersion** rỗng theo task, nhưng điều đó **không** đồng nghĩa thay đổi `project.version` dùng cho publication metadata.

### 7.1. Classifier mặc định của Spring Boot Gradle

Theo convention Spring Boot Gradle Plugin:

~~~text
bootJar → <name>-<version>.jar
jar     → <name>-<version>-plain.jar
~~~

Khi có cả hai task, `jar` được cấu hình classifier **plain** để tránh trùng tên với `bootJar`. Nếu muốn **exec JAR mang classifier** và **plain JAR là file không có classifier**, có thể đổi:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier.set('exec')
}

tasks.named('jar') {
    archiveClassifier.set('')
}
~~~

Đây là **đoạn build.gradle**, không phải cấu hình đủ cho một project độc lập. Hai task có tên file khác nhau nên có thể cùng xuất ra một directory.

**Cảnh báo va chạm:** Không đặt **bootJar** và **jar** chung `archiveFileName` + `destinationDirectory`, vì hai task có thể ghi vào cùng đường dẫn. Kết quả phụ thuộc task nào chạy sau và có thể gây lỗi build, output cache hoặc artifact publication. Giữ ít nhất một thành phần tên khác nhau.

## 8. Gradle: build.gradle đầy đủ với tên và nơi lưu tùy chỉnh

File **settings.gradle**:

~~~groovy
rootProject.name = 'jar-naming-demo'
~~~

File **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '2.3.0'

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

tasks.named('bootJar') {
    archiveBaseName.set('demo-service')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('exec')
    destinationDirectory.set(layout.buildDirectory.dir('releases'))
}

tasks.named('jar') {
    archiveBaseName.set('demo-service')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('plain')
    destinationDirectory.set(layout.buildDirectory.dir('releases'))
}
~~~

Đây là **build.gradle hoàn chỉnh** của ví dụ và dùng Java 17. Cần có Gradle Wrapper tương thích hoặc Gradle 8.5 cài sẵn; nếu không có JDK 17 phù hợp được Gradle nhận diện, phải cài Java tương ứng hoặc cấu hình toolchain resolver riêng.

**Giải thích:**

1. `group` và `version` là metadata của project; version **2.3.0** phục vụ quản lý artifact/dependency.
2. `bootJar` tạo executable JAR với classifier **exec**, tên **demo-service-2.3.0-exec.jar**.
3. `jar` tạo plain JAR với classifier **plain**, tên **demo-service-2.3.0-plain.jar**.
4. Cả hai dùng `layout.buildDirectory.dir('releases')` nên kết quả nằm dưới **build/releases/**, không còn mặc định **build/libs/**.
5. `archiveVersion.set(project.version.toString())` giữ version trong filename đi theo `project.version`. Vì vậy đổi `version='2.4.0'` sẽ đổi phần version của cả hai file ở build kế tiếp.
6. `archiveBaseName` là phần tên file, không làm thay `rootProject.name` trong settings.gradle hoặc module coordinate mặc định của publication.
7. `archiveClassifier` chỉ là tên biến thể, **không trực tiếp đổi lớp Java nào được compile hoặc packaging layout của task**.

**Khác Maven ở ví dụ này:** Với Gradle, plain JAR giữ hậu tố **-plain**; Maven dùng plain JAR không classifier. Nếu muốn hai công cụ tạo cùng hai filename như mục 1, đổi **jar.archiveClassifier** từ `plain` thành chuỗi rỗng `''`. Khi đó Gradle xuất ra:

~~~text
build/releases/demo-service-2.3.0.jar
build/releases/demo-service-2.3.0-exec.jar
~~~

Việc chọn để `plain` hay rỗng phụ thuộc quy ước phân phối của dự án. Không có quy tắc bắt buộc rằng plain JAR phải luôn có hậu tố `plain`.

### 8.1. Dùng chung chương trình Java

Tạo file **src/main/java/com/example/demo/ArtifactNamingApplication.java** với toàn bộ nội dung:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArtifactNamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ArtifactNamingApplication.class, args);
    }

    @Bean
    CommandLineRunner printArtifactName() {
        return args -> System.out.println("JAR_NAMING_OK");
    }
}
~~~

Class Java này **giống chính xác** file dùng trong phương án Maven; chỉ file cấu hình build và đường dẫn output thay đổi.

### 8.2. Build Gradle và file output dự kiến

~~~bash
./gradlew clean build
~~~

Hoặc khi chỉ muốn tạo Boot JAR:

~~~bash
./gradlew clean bootJar
~~~

**Phân biệt:** `build` chạy lifecycle assemble/check nên thường tạo cả `jar` và `bootJar` theo task graph chuẩn; `bootJar` chỉ yêu cầu executable archive và các dependency cần thiết. Không suy ra `bootJar` luôn chạy cả plain `jar` nếu không có quan hệ task.

Sau **clean build**, các file cần quan sát là:

~~~text
build/
└── releases/
    ├── demo-service-2.3.0-exec.jar     # bootJar
    └── demo-service-2.3.0-plain.jar    # jar
~~~

Chạy ứng dụng:

~~~bash
java -jar build/releases/demo-service-2.3.0-exec.jar
~~~

Ngoài log Boot, stdout do chương trình tự in:

~~~text
JAR_NAMING_OK
~~~

Nếu không có wrapper trên máy, có thể dùng `gradle clean build` sau khi cài Gradle phù hợp. Trên Windows dùng **gradlew.bat**; đường dẫn tương đối đến file JAR có thể dùng dấu gạch chéo hoặc dấu gạch ngược tùy shell.

## 9. archiveFileName: khi cần tên file cố định chính xác

Đôi khi hệ thống triển khai yêu cầu **app.jar** thay vì tên chứa version. Gradle cho phép đặt trực tiếp:

~~~groovy
tasks.named('bootJar') {
    archiveFileName.set('app.jar')
    destinationDirectory.set(layout.buildDirectory.dir('delivery'))
}
~~~

Đây là **fragment của build.gradle**; nó thay cách xác định tên của `bootJar` mà không tự thay project.version. File Boot JAR được ghi dưới **build/delivery/app.jar**.

**Điểm phải nhớ:** Khi đã đặt `archiveFileName` cố định, sửa `archiveBaseName`, `archiveVersion` hoặc `archiveClassifier` **không tự cập nhật filename đã override**. Nếu bạn cần tên file chứa version động, nên dùng từng thành phần (`archiveBaseName`, `archiveVersion`, `archiveClassifier`) hoặc một Provider/giá trị được xây dựng có chủ đích.

Nếu `jar` cũng được cấu hình tạo **app.jar** trong **build/delivery/**, hai task đụng đường dẫn. Hãy cho plain JAR tên khác hoặc chỉ publish executable Boot JAR theo yêu cầu pipeline.

**Có nên bỏ version khỏi filename?** Có thể nếu deploy system đòi filename ổn định và version được lưu trong registry tag/manifest/metadata, nhưng quá trình upload nên kèm **checksum và metadata version** để không ghi đè artifact cũ mà mất khả năng truy vết.

## 10. base.archivesName và cấu hình nhiều task Gradle

Trong Gradle, có thể đặt tên cơ sở cho archive tasks thông qua base plugin extension, ví dụ:

~~~groovy
base {
    archivesName = 'demo-service'
}
~~~

Đây là **fragment Groovy DSL trong build.gradle**. Nó đặt **convention** cho tên cơ sở của các archive task sử dụng convention này. Tuy nhiên, nếu task cụ thể đã có `archiveBaseName.set('...')`, giá trị tường minh trên task được ưu tiên.

Đối với một ứng dụng có cả `jar` và `bootJar`:

- Dùng **base.archivesName** khi muốn tên cơ sở chung.
- Dùng **tasks.named('bootJar')** khi muốn đổi riêng executable archive.
- Dùng **tasks.named('jar')** khi muốn đổi riêng plain archive.
- Dùng **destinationDirectory** ở từng task khi output directories khác nhau.

Ví dụ fragment chỉ cấu hình base chung nhưng giữ classifier riêng:

~~~groovy
base {
    archivesName = 'billing-service'
}

tasks.named('bootJar') {
    archiveClassifier.set('exec')
}

tasks.named('jar') {
    archiveClassifier.set('plain')
}
~~~

Với `version='2.3.0'` và destinationDirectory mặc định, kết quả dự kiến:

~~~text
build/libs/billing-service-2.3.0-exec.jar
build/libs/billing-service-2.3.0-plain.jar
~~~

Đừng cùng lúc cấu hình base và từng task khác nhau nếu không có lý do: nó làm người đọc khó xác định tên file cuối cùng.

## 11. Cách kiểm tra artifact thay vì đoán tên

### 11.1. Liệt kê file JAR sau build

Maven:

~~~bash
./mvnw clean package
~~~

Sau đó xem **release-build/** bằng file explorer, `ls` (Linux/macOS) hoặc `dir` (Windows). Nếu dùng POM ở mục 5, hai file cần quan sát là:

~~~text
release-build/demo-service-2.3.0.jar
release-build/demo-service-2.3.0-exec.jar
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

Với build.gradle ở mục 8, hai file cần quan sát:

~~~text
build/releases/demo-service-2.3.0-plain.jar
build/releases/demo-service-2.3.0-exec.jar
~~~

### 11.2. Kiểm tra nội dung JAR bằng công cụ JDK

Dùng `jar tf` có sẵn trong JDK.

Maven Boot JAR:

~~~bash
jar tf release-build/demo-service-2.3.0-exec.jar
~~~

Maven plain JAR:

~~~bash
jar tf release-build/demo-service-2.3.0.jar
~~~

Gradle Boot JAR:

~~~bash
jar tf build/releases/demo-service-2.3.0-exec.jar
~~~

Gradle plain JAR:

~~~bash
jar tf build/releases/demo-service-2.3.0-plain.jar
~~~

**Dấu hiệu thường gặp:**

- Executable Spring Boot JAR có các entry `BOOT-INF/classes/`, `BOOT-INF/lib/` và Boot launcher tương ứng phiên bản.
- Plain JAR chứa `com/example/demo/ArtifactNamingApplication.class` ở vị trí classpath thông thường và không có đầy đủ nested dependency/runtime layout của Boot archive.

Với JAR không dùng layout mặc định hoặc project có cấu hình packaging đặc biệt, phải đối chiếu theo plugin config. Không chỉ dựa vào chuỗi classifier `exec` để xác nhận artifact chạy được.

### 11.3. Chạy đúng executable archive

~~~bash
java -jar release-build/demo-service-2.3.0-exec.jar
~~~

Hoặc:

~~~bash
java -jar build/releases/demo-service-2.3.0-exec.jar
~~~

**Chỉ chạy một lệnh tương ứng với công cụ build được chọn.** Lệnh thứ nhất dành cho Maven, lệnh thứ hai cho Gradle. Nếu app in `JAR_NAMING_OK`, ta biết artifact thật có thể khởi chạy bằng Java đang dùng; cần thêm kiểm thử nghiệp vụ nếu muốn xác nhận app hoàn chỉnh.

### 11.4. Gradle: xem đường dẫn archive file qua Provider

Trong build.gradle có thể bổ sung task chẩn đoán riêng:

~~~groovy
tasks.register('showBootJarPath') {
    doLast {
        println(tasks.named('bootJar').get().archiveFile.get().asFile)
    }
}
~~~

Sau đó:

~~~bash
./gradlew -q showBootJarPath
~~~

Task in **đường dẫn file dự kiến** dựa trên `destinationDirectory` và `archiveFileName`. Nó **không tự build JAR** vì task này không có `dependsOn('bootJar')`. Nếu file chưa tồn tại, đường dẫn vẫn có thể được hiển thị; muốn xác nhận artifact thật, cần chạy `bootJar` và kiểm tra file.

## 12. Tên file, phiên bản và CI/CD

### 12.1. Không dùng wildcard dễ nhầm plain với Boot

Ví dụ lệnh Docker/CI chọn file theo wildcard:

~~~text
build/releases/*.jar
~~~

... có thể match **cả executable JAR và plain JAR**. Thứ tự của glob không phải quy tắc xác định artifact đúng. Một pipeline có thể vô tình copy/publish plain JAR.

**Nên chọn chính xác:**

~~~text
build/releases/demo-service-2.3.0-exec.jar
~~~

Hoặc trong hệ thống CI có khả năng nhận artifact output từ Gradle task, đọc trực tiếp **bootJar.archiveFile** hoặc đường dẫn đã khai báo trong task.

**Maven** cũng tương tự: chọn `release-build/demo-service-2.3.0-exec.jar`, không lấy file đầu tiên trong `release-build/*.jar`.

### 12.2. Tên file cố định hay có version?

| Mục đích | Gợi ý |
| --- | --- |
| Artifact lưu trữ trong repository/CI | Chứa version hoặc build ID; tránh ghi đè ngẫu nhiên |
| Docker build stage | Có thể copy file có classifier rõ ràng tới tên ổn định trong image, ví dụ `app.jar` |
| Maven library publication | Giữ Maven coordinates đúng, chọn main/plain JAR cho consumer |
| Spring Boot executable deployment | Dùng Boot JAR chính xác, có classifier hoặc convention tách rõ |
| Artifact rolling deployment | Theo dõi version, checksum, provenance và tên file được build từ commit nào |

Một quy trình thường dùng: build tạo **demo-service-2.3.0-exec.jar**, CI upload nó kèm metadata `version=2.3.0`, rồi Dockerfile copy **đúng file đó** vào image với đường dẫn ổn định `/app/app.jar`. Việc **đổi tên file ở bước copy** trong container không làm thay đổi nội dung và Maven coordinates gốc.

### 12.3. Phân biệt project version với phiên bản plugin

Trong ví dụ:

~~~text
Project/application version : 2.3.0
Spring Boot plugin version  : 3.3.5
Java toolchain version      : 17
Archive classifier         : exec
~~~

Đây là **bốn thông tin khác nhau**. Tên `demo-service-2.3.0-exec.jar` có version **2.3.0** vì dự án chọn nó, không phải vì Spring Boot plugin mặc định lấy `3.3.5`. JDK 17 không xuất hiện trong filename trừ khi bạn chủ động cho nó vào appendix/classifier.

### 12.4. Tái lập bản build

Tên file giống nhau **không chứng minh byte-for-byte giống nhau**. Nội dung JAR có thể khác vì code, dependency, timestamp, thứ tự entry hoặc resource được sinh từ môi trường. Spring Boot Maven Plugin hỗ trợ **outputTimestamp**; Gradle archive tasks có những thiết lập về reproducible file order/preserve timestamps. Khi cần checksum reproducibility, pin dependency/plugin versions, dùng clean build và kiểm tra tính deterministic của resource/code generation.

Không nên tạo version tên file dựa đơn thuần vào thời gian hiện tại trong môi trường CI mà không lưu metadata đi kèm. Version, commit SHA và checksum giúp truy vết rõ ràng hơn.

### 12.5. Upload, install và publish không chỉ dựa vào đường dẫn local

- **Maven:** `mvn install`/`mvn deploy` xuất bản theo artifact coordinates và danh sách attached artifacts. `finalName` đổi file local nhưng không đổi artifactId/version trên repository. Classifier `exec` có thể xuất hiện như attached artifact nếu `attach=true`.
- **Gradle:** `bootJar` và `jar` tạo file local; việc xuất bản bằng `maven-publish` phải cấu hình publication/artifact tương ứng. **Đừng mặc định** Gradle sẽ publish đúng executable Boot JAR chỉ vì task bootJar đã tạo file.
- **CI/CD artifact upload:** phải trỏ đến output đã kiểm chứng. Đổi destinationDirectory nhưng không sửa pipeline sẽ gây lỗi “file not found” hoặc upload nhầm artifact cũ.

## 13. Một số tình huống cấu hình cần cân nhắc

### 13.1. Chỉ cần executable Spring Boot JAR

Nếu ứng dụng hoàn toàn không cần plain JAR, trong Gradle có thể tắt task plain:

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

**Cẩn trọng:** Không tắt `jar` một cách máy móc khi dự án còn dùng native image plugin hoặc các integration khác phụ thuộc plain JAR. Spring Boot documentation đặc biệt lưu ý việc này trong một số cấu hình native image. Với Maven, khi không đặt classifier cho `repackage`, executable thay main artifact; không cần một bước disable jar task tương đương.

### 13.2. Cần cả library JAR và executable JAR

Maven: dùng **classifier exec** cho Boot archive, giữ main JAR để module khác phụ thuộc. Đây là lựa chọn tốt khi module vừa phải phát hành class theo bố cục Java thông thường vừa có entry point demo, mặc dù về kiến trúc thường nên cân nhắc tách thư viện và ứng dụng thành hai module.

Gradle: `jar` làm plain archive; `bootJar` làm executable archive. Nếu cần publish cả hai, phải thiết kế publication và classifier theo yêu cầu consumer; không chỉ thay file names.

### 13.3. Multi-module build

Giả sử Gradle có **:app** và **:core**. Thường chỉ :app áp dụng `org.springframework.boot` và tạo bootJar. :core dùng `java-library` và tạo plain JAR, không cần bootJar. Nếu mọi subproject cùng đặt `archiveBaseName='demo-service'` và version giống nhau vào chung thư mục output, chúng có nguy cơ **trùng filename**.

Trong multi-project:

- Giữ tên cơ sở khác nhau theo module, hoặc đặt `destinationDirectory` riêng theo project.
- Khi gom artifact của các module vào một thư mục distribution, thêm module name/classifier nếu cần.
- Đừng viết cấu hình áp dụng Boot plugin đồng loạt cho thư viện chỉ để “có JAR”.
- Với Maven multi-module, `finalName` ở POM cha có thể được kế thừa; nếu nó cố định một tên cho mọi module và các module có cùng build.directory, có thể sinh xung đột. Kiểm tra effective POM/build output của từng module.

### 13.4. Đổi toàn bộ thư mục Gradle build so với đổi riêng destinationDirectory

Gradle cho phép cấu hình chung **layout.buildDirectory**, nhưng hành động đó chuyển **nhiều loại output**: classes, resources, test results, reports và artifacts. Nếu mục tiêu chỉ là JAR, thường đủ dùng **destinationDirectory** của `bootJar`/`jar`. Đây là khác biệt tương tự Maven `build.directory` so với plugin-specific outputDirectory.

### 13.5. Nâng version dự án

Khi đổi project version từ 2.3.0 sang 2.4.0:

~~~text
Maven project.version 2.4.0      → demo-service-2.4.0-exec.jar
Gradle project.version 2.4.0     → demo-service-2.4.0-exec.jar
~~~

Trong cả hai cách, tên có version tự cập nhật vì cấu hình tham chiếu giá trị project. Đừng quên rằng repository coordinate của artifact cũng đổi phiên bản; việc tăng version không chỉ làm đẹp tên file.

## 14. Lỗi thường gặp và cách giải quyết

**1. File JAR có tên sai version.** Kiểm tra `pom.xml <version>` hoặc `Gradle version = '...'`, sau đó xem `finalName`/`archiveVersion` có hard-code phiên bản cũ không. Với Gradle, nếu đã set `archiveFileName` cố định thì cấu hình archiveVersion không còn điều khiển tên file.

**2. Không thấy JAR trong target/ hoặc build/libs/.** Bạn có thể đã đổi `build.directory`, plugin `outputDirectory` hoặc `destinationDirectory`. Đối chiếu POM/build script và output task. Không mặc định đây là lỗi compile.

**3. Có hai JAR nhưng chọn nhầm plain JAR để chạy.** Xem classifier/task, kiểm tra `jar tf` cho `BOOT-INF/classes` và thử `java -jar` trên executable. Đừng xem `.jar` là bằng chứng executable.

**4. Maven tạo file .jar.original.** Đây thường là bản JAR gốc được Spring Boot `repackage` giữ lại khi không đặt classifier. Không tự tuyên bố nó là published artifact. Nếu cần cả hai biến thể rõ ràng, dùng `classifier exec`.

**5. Maven chỉ tạo plain JAR, không có executable.** Kiểm tra spring-boot-maven-plugin đã khai báo đúng, execution repackage có chạy trong package lifecycle chưa; khi dùng parent không phải `spring-boot-starter-parent`, có thể phải khai báo goal repackage tường minh.

**6. Đặt classifier trong maven-jar-plugin mà không đồng bộ Spring Boot repackage.** Maven Boot Plugin có logic chọn artifact nguồn theo classifier. Nếu các plugin cùng đặt classifier mà không hiểu thứ tự execution, kết quả có thể khác mong đợi. Giữ một thiết kế attachment rõ ràng và kiểm tra archive thực tế.

**7. Sửa finalName rồi nghĩ artifact Maven trên repository cũng đổi tên.** Tọa độ publish vẫn dựa vào groupId/artifactId/version/classifier. Nếu muốn đổi artifactId thật, chỉnh POM và phụ thuộc tiêu thụ; finalName chỉ thay tên file tại build.

**8. Gradle bootJar và jar ghi đè nhau.** Hai task đang có cùng `archiveFileName` và `destinationDirectory`. Đặt classifier khác nhau (`exec`/`plain`) hoặc thư mục khác nhau; chạy clean build để loại file cũ.

**9. Gradle có hậu tố -plain dù không cấu hình.** Spring Boot Gradle Plugin thiết lập convention classifier `plain` cho task jar để tránh trùng với bootJar. Đây là hành vi bình thường, không phải tên file hỏng.

**10. Bỏ classifier khỏi bootJar mà quên sửa jar.** Nếu jar còn classifier `plain`, không trùng tên; nếu jar cũng rỗng và cùng destinationDirectory, sẽ trùng. Kiểm tra mọi archive task thay vì chỉ bootJar.

**11. Chỉ chạy bootJar mà ngạc nhiên chưa có plain JAR.** `bootJar` không nhất thiết phụ thuộc task `jar`. Muốn cả hai, gọi `build`/`assemble` theo task graph hoặc explicit `jar bootJar`.

**12. CI dùng glob build/libs/*.jar và chạy sai file.** Đổi pipeline thành path rõ ràng hoặc lấy artifact path từ task; update sau khi thay destinationDirectory.

**13. Chuyển Maven build.directory làm mất báo cáo ở target/.** Output classes/test reports cũng chuyển; sửa CI tool path hoặc cân nhắc chỉ copy artifact thay vì đổi toàn bộ build directory.

**14. Dùng archiveFileName='app.jar' nhưng kỳ vọng version hiện trong filename.** archiveFileName cố định đã override cấu trúc tên. Muốn version, đặt archiveVersion hoặc tự tạo filename động có kiểm soát.

**15. Java runtime không phù hợp.** Class được compile bằng Java 17 cần runtime Java đủ mới; classifier tên `java17` không tự kiểm soát classfile version. Kiểm tra Gradle toolchain/Maven compiler release và JVM chạy ở production.

**16. Jar có BOOT-INF nhưng vẫn không khởi động.** Kiểm tra main class, manifest/launcher, dependency runtime, cấu hình ứng dụng và log lỗi. Một archive có vẻ đúng cấu trúc chưa chứng minh mọi dependency đã được đóng.

**17. Publisher chỉ upload plain JAR dù bootJar đã có.** Maven cần attachment/classifier đúng; Gradle publishing cần cấu hình artifact/publication đúng. Không lấy tên file local làm bằng chứng publish thành công.

**18. Version chứa SNAPSHOT.** Với Maven, `version=2.3.0-SNAPSHOT` sinh tên `demo-service-2.3.0-SNAPSHOT-exec.jar` tại local theo finalName, nhưng repository snapshot có thể dùng timestamped filenames theo chính sách lưu trữ. CI không nên đoán file remote hoàn toàn từ local filename.

**19. Cùng một filename qua các lần deploy gây khó rollback.** Dùng version/commit ID, immutable registry path, checksum và metadata thay vì chỉ một file `app.jar` bị ghi đè liên tục.

**20. Đặt outputDirectory của Boot riêng nhưng không đổi đường dẫn Dockerfile.** Kiểm tra file nào thật sự được tạo, sửa build context/upload path; không lấy sự tồn tại của JAR cũ làm dấu hiệu build hiện tại thành công.

## 15. Checklist thực hành và phát hành

- [ ] Xác định rõ JAR nào là **executable Boot JAR**, JAR nào là **plain JAR**.
- [ ] Phân biệt **project version**, **Spring Boot plugin version**, **Java version**.
- [ ] Với Maven: quyết định `artifactId`, `version`, `build.finalName`, `build.directory` và `spring-boot-maven-plugin.classifier`.
- [ ] Với Maven: nếu dùng Boot parent, xác nhận repackage execution; nếu không dùng Boot parent, cấu hình repackage vào lifecycle.
- [ ] Với Gradle: đặt `archiveBaseName`, `archiveVersion`, `archiveClassifier` và `destinationDirectory` ở `bootJar`/ `jar` khi cần.
- [ ] Tránh hai archive tasks cùng ghi một filepath.
- [ ] Dùng version động trong filename khi muốn truy vết artifact qua nhiều release.
- [ ] Chạy clean build, liệt kê đường dẫn file đã tạo.
- [ ] Dùng `jar tf` để phân biệt Boot layout với plain layout.
- [ ] Chạy **đúng executable JAR** bằng `java -jar`, xác nhận stdout/khởi động.
- [ ] Đồng bộ Dockerfile/CI artifact glob sau khi đổi filename hoặc thư mục.
- [ ] Khi publish, xác nhận **Maven attached artifacts** hoặc **Gradle publications** tương ứng.
- [ ] Ghi metadata version/commit/checksum để truy vết và rollback.

## 16. Tài liệu chính thức

- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven — POM Reference (build.directory, finalName): https://maven.apache.org/pom.html
- Gradle — Jar Task API (archiveBaseName, archiveVersion, archiveClassifier, archiveFileName, destinationDirectory): https://docs.gradle.org/8.5/dsl/org.gradle.jvm.tasks.Jar.html
- Gradle — Working with Files and Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Spring Boot 3.3 — Gradle Plugin Publishing: https://docs.spring.io/spring-boot/3.3/gradle-plugin/publishing.html

**Kết luận:** Muốn kiểm soát tên, version, classifier và nơi lưu Spring Boot JAR, trước hết xác định **artifact executable hay plain**. Maven dùng **version + build.finalName + build.directory + spring-boot-maven-plugin.classifier**; Gradle dùng các **archive properties của bootJar và jar**, đặc biệt **archiveBaseName, archiveVersion, archiveClassifier và destinationDirectory**. Sau mỗi thay đổi, xác minh **file thực tế, nội dung JAR và lệnh chạy**, rồi cập nhật CI/CD theo đúng đường dẫn thay vì chỉ dựa vào wildcard.