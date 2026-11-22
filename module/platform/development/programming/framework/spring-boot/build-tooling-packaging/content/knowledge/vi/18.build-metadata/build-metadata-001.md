# Vai trò của group, artifact, version và danh tính sản phẩm

Khi phát hành một ứng dụng Spring Boot, có thể xuất hiện các tên khác nhau: tên Gradle project, group, artifactId, version, tên executable JAR, tên ứng dụng Spring và tên container image. **Những tên đó không mặc nhiên đồng nghĩa**. Chẳng hạn, build có thể đặt `project.name=metadata-demo`, `group=com.example.catalog`, `version=1.2.3` nhưng tạo file `catalog-service-1.2.3.jar` và chạy service có `spring.application.name=orders-api`.

Để quản lý đúng một bản phát hành, cần phân biệt:

1. **Group:** namespace/nhóm đứng sau artifact.
2. **Artifact:** đơn vị phân phối và tên logic dùng khi publish/resolve.
3. **Version:** dấu mốc phát hành của artifact.
4. **Product/application identity:** tên sản phẩm và tên logical service trong hệ thống.
5. **Binary identity:** checksum/digest của chính file đã build hoặc image đã triển khai.

**Ý chính:** `groupId:artifactId:version` (GAV) định vị module/version trong repository; Gradle archive task quyết định tên file output; Spring Boot build-info cho biết metadata được nhúng vào binary; `spring.application.name` phục vụ danh tính runtime. Khi điều tra sự cố production, phải đối chiếu chúng thay vì suy đoán.

Các ví dụ dùng Java 17, Spring Boot 3.3.5 và Gradle 8.7 để có cấu hình cụ thể. Đây là phiên bản minh họa, không phải tuyên bố phiên bản mới nhất.

## 1. GAV là gì?

Ví dụ tọa độ Maven:

~~~text
com.example.catalog:catalog-api:1.2.3
~~~

| Phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `groupId` | Namespace/nhóm của artifact | `com.example.catalog` |
| `artifactId` | Tên logic của artifact | `catalog-api` |
| `version` | Phiên bản của module | `1.2.3` |

Trong repository Maven có layout tiêu chuẩn, JAR và POM cho tọa độ này có thể được lưu dưới:

~~~text
com/example/catalog/catalog-api/1.2.3/catalog-api-1.2.3.jar
com/example/catalog/catalog-api/1.2.3/catalog-api-1.2.3.pom
~~~

Dấu chấm ở groupId được chuyển thành separator trong đường dẫn repository. Đây không phải đường dẫn source Java và cũng không phải cấu trúc nội bộ của Spring Boot executable JAR.

**Lưu ý:** GAV là tọa độ **module/version**, nhưng một module có thể có thêm file sources, Javadoc, artifact classifier `tests`, POM hoặc WAR. Các trường `classifier` và `extension/type` có thể cần thiết để chỉ đúng file artifact.

~~~text
GAV:        com.example.catalog:catalog-api:1.2.3
classifier: tests      (tùy chọn)
extension:  jar        (ví dụ)
~~~

Một tọa độ GAV có thể xuất hiện trong nhiều repositories; không nên coi cùng GAV ở hai nơi là bằng chứng tuyệt đối của cùng bytes. Đặc biệt với snapshots hoặc repository cho phép overwrite, phải dùng checksum và release provenance để khẳng định nội dung.

### `groupId` không bắt buộc bằng Java package

Một library có groupId `com.example.catalog` nhưng chứa classes ở `com.example.catalog.domain`, `com.example.shared` hoặc package khác. Chọn group có quy ước ổn định, thường là reverse domain được tổ chức kiểm soát, để giảm xung đột tên. Tuy vậy khai báo group không tự cấp quyền publish: repository vẫn kiểm tra authentication, authorization và namespace policy.

### ArtifactId không phải tên sản phẩm marketing

Một sản phẩm **Catalog Platform** có thể chứa ba artifacts:

~~~text
com.example.catalog:catalog-core:1.2.3
com.example.catalog:catalog-api:1.2.3
com.example.catalog:catalog-batch:1.2.3
~~~

Ba artifactIds nên phân biệt những đơn vị được publish/deploy. Dùng chung một artifactId và version cho nhiều binaries khác nhau có thể gây collision trong repository.

## 2. Gradle `project.group`, `project.name` và `project.version`

Trong `build.gradle` (Groovy DSL):

~~~groovy
group = 'com.example.catalog'
version = '1.2.3'
~~~

Gradle `project.name` thường được khai báo trong `settings.gradle`:

~~~groovy
rootProject.name = 'metadata-demo'
~~~

Khi dùng **Maven Publish plugin**, các giá trị mặc định của `MavenPublication` là:

| Trường của publication | Giá trị mặc định |
| --- | --- |
| `groupId` | `project.group` |
| `artifactId` | `project.name` |
| `version` | `project.version` |

Với các giá trị trên, một Maven publication không override sẽ mặc định có GAV:

~~~text
com.example.catalog:metadata-demo:1.2.3
~~~

**Không nhầm `project.name` với file output:** tên JAR còn phụ thuộc `archiveBaseName`, `archiveVersion`, `archiveClassifier` và `archiveFileName`.

### Maven POM đối chiếu

Maven ghi trực tiếp:

~~~xml
<groupId>com.example.catalog</groupId>
<artifactId>metadata-demo</artifactId>
<version>1.2.3</version>
~~~

Maven còn có `<name>Catalog Service</name>` để hiển thị tên project dễ hiểu. `<name>` không thay `<artifactId>`. Trong Maven, groupId và version có thể được kế thừa từ parent; hãy đọc effective POM nếu file con không khai báo tường minh.

### Thay group theo environment?

Thông thường **không cần** tạo các GAV khác nhau như `com.example.catalog.dev:catalog-api:1.2.3` và `com.example.catalog.prod:catalog-api:1.2.3` chỉ vì triển khai qua dev/staging/prod. Cùng một release artifact nên được promote với cùng bytes, còn URL, profile, credentials và server settings được cung cấp ở runtime/deployment. Nếu tổ chức có policy artifact theo môi trường riêng, phải quản lý nhất quán chứ không áp dụng tùy hứng.

## 3. `version` là phiên bản artifact, không phải phiên bản tool

Một project có thể đồng thời sử dụng:

~~~text
Application artifact version: 1.2.3
Spring Boot Gradle plugin:    3.3.5
Gradle Wrapper:              8.7
Java toolchain:              17
Git revision:                <commit-id>
~~~

`project.version=1.2.3` không có nghĩa đang chạy Spring Boot 1.2.3 hay Java 1.2.3. Các version này theo những trục riêng.

### Semantic Versioning

Quy ước phổ biến:

~~~text
MAJOR.MINOR.PATCH
1.2.3
~~~

- **MAJOR:** thay đổi không tương thích theo hợp đồng công bố.
- **MINOR:** thêm chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích ngược.

Đây là chính sách mà nhóm phát triển thực hiện. Maven/Gradle **không tự bảo đảm** một phiên bản là backward compatible chỉ vì nó có ba con số.

### Snapshot và release

~~~text
1.3.0-SNAPSHOT
1.3.0-RC1
1.3.0
~~~

`SNAPSHOT` thường dùng cho bản phát triển, có thể được publish nhiều lần với metadata/timestamp tương ứng; release chính thức nên tuân theo policy bất biến. Không nên ghi đè file mới dưới cùng tọa độ release `1.2.3`, vì consumers, caches và rollback có thể chọn bytes khác nhau mà vẫn thấy cùng version.

Version **không thay thế Git commit hoặc SHA-256**. Hai bản rebuild có cùng version nhưng bytes khác vì dependency/timestamp/build environment cũng là trường hợp cần quản trị.

### Một repo, nhiều version modules

Multi-project có thể dùng **release train**:

~~~text
catalog-core:1.2.3
catalog-api:1.2.3
catalog-batch:1.2.3
~~~

hoặc **independent versioning**:

~~~text
catalog-core:2.0.1
catalog-api:1.2.3
catalog-batch:0.8.4
~~~

Chính sách nào cũng cần có release records, compatibility tests và tọa độ không va chạm. Không bắt buộc mọi module chung repository phải có cùng version.

## 4. Tên file JAR/WAR khác Maven artifactId

Gradle archive tasks như `jar`, `bootJar`, `war`, `bootWar` có các properties:

| Property | Vai trò | Ví dụ |
| --- | --- | --- |
| `archiveBaseName` | Tên cơ sở của archive | `catalog-service` |
| `archiveVersion` | Version gắn vào filename theo convention | `1.2.3` |
| `archiveClassifier` | Phân biệt loại archive | `plain` |
| `archiveExtension` | Extension | `jar` |
| `archiveFileName` | Tên file hoàn chỉnh khi override | `release.jar` |
| `destinationDirectory` | Thư mục output | `build/libs` |

Với baseName `catalog-service`, archiveVersion `1.2.3`, classifier rỗng, extension `jar`, filename thường là:

~~~text
catalog-service-1.2.3.jar
~~~

Nếu `archiveFileName.set('release.jar')`, tên file bị cố định là `release.jar`, không tự đổi theo `project.version` nữa.

~~~groovy
tasks.named('bootJar') {
    archiveBaseName.set('catalog-service')
    archiveVersion.set(project.version.toString())
}
~~~

Đây là snippet đặt trong project có Spring Boot plugin và Java plugin. `bootJar` là executable Boot archive; `jar` của Java plugin có thể tạo plain JAR với classifier `plain` theo cấu hình plugin. Đừng coi hai JAR cùng đuôi `.jar` là cùng công dụng.

**Ví dụ quan trọng:**

~~~text
Gradle project.name           = metadata-demo
Gradle bootJar baseName      = catalog-service
Maven publication artifactId = metadata-demo (nếu mặc định)
~~~

Ba giá trị có thể khác nhau mà không mâu thuẫn. Tên local file và tên artifact khi publish vào repository cũng có thể khác nhau.

## 5. Spring Boot build metadata: `build-info.properties`

Spring Boot Gradle plugin có task `bootBuildInfo` tạo file `META-INF/build-info.properties`. Trong executable Boot JAR, file này thường nằm ở:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

Khi cấu hình `springBoot { buildInfo() }` hoặc block `springBoot { buildInfo { ... } }`, Gradle tích hợp task này vào resources/classes build. Spring Boot có thể auto-configure `BuildProperties` nếu resource có mặt trong runtime classpath.

Theo Spring Boot 3.3, giá trị mặc định:

| Build info key | Nguồn mặc định |
| --- | --- |
| `build.artifact` | Base name của `bootJar` hoặc `bootWar` |
| `build.group` | Gradle `project.group` |
| `build.name` | Gradle `project.name` |
| `build.version` | Gradle `project.version` |
| `build.time` | Thời gian build, trừ khi exclude |

Điểm dễ nhầm nhất: **`build.artifact` không mặc định là `MavenPublication.artifactId`**. Một giá trị lấy từ Boot archive base name, còn một giá trị lấy từ Gradle project name/publication override.

### `spring.application.name` là danh tính runtime

Trong Spring configuration:

~~~properties
spring.application.name=orders-api
~~~

Tên này có thể được logging, tracing hoặc service discovery dùng tùy tích hợp. Nó không tự thay đổi group, artifactId, version hay file archive.

Một service có thể có:

~~~text
Build group:             com.example.catalog
Build artifact:          catalog-service
Build name:              metadata-demo
Build version:           1.2.3
Spring application name: orders-api
~~~

Nếu monitoring dùng tên `orders-api` nhưng artifact được phát hành tên `catalog-service`, điều đó hợp lệ khi có mapping release rõ ràng.

## 6. Bài thực hành đầy đủ: build info và tên ứng dụng khác nhau

Ví dụ Java 17, Spring Boot 3.3.5, Gradle Groovy DSL. Mục tiêu tạo executable JAR với `project.name=metadata-demo`, `group=com.example.catalog`, `version=1.2.3`, `archiveBaseName=catalog-service` và Spring app name `orders-api`.

### Cấu trúc thư mục

~~~text
metadata-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/catalog/MetadataDemoApplication.java
    └── resources/application.properties
~~~

### File `settings.gradle`

~~~groovy
rootProject.name = 'metadata-demo'
~~~

### File `build.gradle`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example.catalog'
version = '1.2.3'

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
    mainClass = 'com.example.catalog.MetadataDemoApplication'

    buildInfo {
        // Bo build.time de metadata khong doi theo moi lan build.
        excludes = ['time']
    }
}

tasks.named('bootJar', BootJar) {
    archiveBaseName.set('catalog-service')
    archiveVersion.set(project.version.toString())
}
~~~

**Giải thích:**

1. Gradle project.name lấy từ settings; `group` và `version` được đặt trong build script.
2. `bootJar.archiveBaseName` đổi tên binary, không đổi `project.name`.
3. `springBoot.buildInfo` bật task `bootBuildInfo` và tạo metadata resource. `excludes=['time']` tránh build-info thay đổi timestamp mỗi lần, cải thiện up-to-date/reproducibility cho phần metadata.
4. `spring-boot-starter` cung cấp runtime tối thiểu cho Spring Boot command-line app, không tự khởi tạo HTTP server.
5. Không bật `maven-publish` trong mẫu này, nên khai báo `group`/`version` chưa đồng nghĩa ứng dụng đã được publish.

### File `src/main/resources/application.properties`

~~~properties
spring.application.name=orders-api
~~~

### File `src/main/java/com/example/catalog/MetadataDemoApplication.java`

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class MetadataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showIdentity(
            BuildProperties info, Environment environment) {
        return args -> {
            System.out.println("APP_NAME=" +
                    environment.getProperty(
                            "spring.application.name", "unnamed"));
            System.out.println("BUILD_GROUP=" + info.getGroup());
            System.out.println("BUILD_ARTIFACT=" + info.getArtifact());
            System.out.println("BUILD_NAME=" + info.getName());
            System.out.println("BUILD_VERSION=" + info.getVersion());
        };
    }
}
~~~

`BuildProperties` được Spring Boot auto-configure từ `META-INF/build-info.properties` nếu resource có mặt. Nếu bỏ `buildInfo` rồi vẫn inject bắt buộc, startup có thể lỗi thiếu bean. Class Java có package và tên file khớp, hợp lệ trên Java 17.

### Build và chạy

Nếu đã có Gradle Wrapper 8.7 tương thích, từ root:

~~~bash
./gradlew clean bootJar
~~~

Output:

~~~text
build/libs/catalog-service-1.2.3.jar
~~~

Chạy:

~~~bash
java -jar build/libs/catalog-service-1.2.3.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Năm dòng **do ứng dụng in**:

~~~text
APP_NAME=orders-api
BUILD_GROUP=com.example.catalog
BUILD_ARTIFACT=catalog-service
BUILD_NAME=metadata-demo
BUILD_VERSION=1.2.3
~~~

Các log Spring Boot/JVM khác có thể tùy môi trường. Vì không có web server, ứng dụng command-line kết thúc sau khi runner hoàn tất nếu không có công việc nền khác.

### Kiểm tra archive

~~~bash
jar tf build/libs/catalog-service-1.2.3.jar
~~~

Tìm:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/catalog/MetadataDemoApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/classes/META-INF/build-info.properties
~~~

`jar tf` chỉ liệt kê entries. Nếu có `unzip` trên Linux/macOS:

~~~bash
unzip -p build/libs/catalog-service-1.2.3.jar BOOT-INF/classes/META-INF/build-info.properties
~~~

Những thuộc tính quan trọng:

~~~properties
build.artifact=catalog-service
build.group=com.example.catalog
build.name=metadata-demo
build.version=1.2.3
~~~

Không yêu cầu thứ tự dòng cố định hoặc file chỉ có bốn key. Ví dụ đã loại mặc định `build.time`.

Trên Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew`; Java/JDK commands vẫn có thể dùng tương tự.

## 7. Thay từng giá trị sẽ ảnh hưởng ở đâu?

| Thay đổi | Kết quả chính | Không tự thay |
| --- | --- | --- |
| `group='com.example.new'` | `build.group`, default Maven publication groupId nếu có | `spring.application.name` |
| `version='1.2.4'` | `build.version` và filename nếu archiveVersion lấy project.version | Java package |
| `rootProject.name='catalog-project'` | project.name, default `build.name`, default publication artifactId | archiveBaseName đặt tường minh |
| `archiveBaseName='catalog-v2'` | Filename và default `build.artifact` | Maven publication artifactId |
| `spring.application.name=inventory-api` | Spring Environment app name | GAV |
| `archiveFileName='fixed.jar'` | Filename cố định | Version metadata của project |

**Không thay tên bằng mọi giá để tất cả trường giống nhau.** Có lúc bạn muốn app name mô tả logical service, artifactId mô tả thư viện phát hành và archive name mô tả binary dùng deploy. Cách đúng là thống nhất **quy tắc mapping**, không phải đồng nhất sai ngữ nghĩa.

## 8. Publish một Java library: Maven artifactId có thể khác file JAR

Để học đúng Maven coordinates, dùng **Java library độc lập**, không sử dụng Spring Boot executable archive làm dependency library.

Cấu trúc:

~~~text
formatter-library/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/format/TextFormatter.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'formatter-library'
~~~

### `build.gradle`

~~~groovy
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.catalog'
version = '1.2.3'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
            artifactId = 'format-kit'
        }
    }
}
~~~

### `src/main/java/com/example/format/TextFormatter.java`

~~~java
package com.example.format;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String normalize(String value) {
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Chạy từ root với Gradle Wrapper tương thích:

~~~bash
./gradlew clean jar
./gradlew publishToMavenLocal
~~~

JAR local do `jar` task tạo thường là:

~~~text
build/libs/formatter-library-1.2.3.jar
~~~

Nhưng Maven publication là:

~~~text
com.example.catalog:format-kit:1.2.3
~~~

Trong Maven local repository thông dụng:

~~~text
~/.m2/repository/com/example/catalog/format-kit/1.2.3/
    format-kit-1.2.3.jar
    format-kit-1.2.3.pom
~~~

Repository directory có thể thay đổi theo cấu hình/OS. ArtifactId được override thành `format-kit` cho publication, **không bắt buộc local output filename đổi**. Consumer có thể sử dụng:

~~~groovy
repositories {
    mavenLocal()
}

dependencies {
    implementation 'com.example.catalog:format-kit:1.2.3'
}
~~~

Đây là snippet của một **project khác** có Java plugin; trong CI thật nên dùng repository quản trị thay vì phụ thuộc Maven local trên developer machine.

### Vì sao không publish Boot JAR như một Java library tùy tiện?

Spring Boot executable JAR chứa launcher, `BOOT-INF/classes` và nested runtime dependencies. Một ordinary Java library JAR có classes ở root và metadata phục vụ consumer compile/runtime variants. Copy `from components.java` của library sang application publish pipeline mà không xem artifact type có thể phân phối plain JAR thay vì Boot executable hoặc tạo dependency không phù hợp. Nếu cần publish executable service, hãy cấu hình publication/distribution rõ mục đích.

## 9. Maven POM: GAV và tên file output

Một Spring Boot Maven project có thể khai báo:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example.catalog</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>1.2.3</version>
    <name>Catalog Service</name>

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
        <finalName>catalog-service</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.catalog.MetadataDemoApplication</mainClass>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **phương án Maven thay thế**, không cần giữ Gradle và Maven cùng lúc. Parent Boot quản lý nhiều dependency/plugin versions và hỗ trợ `repackage` khi `spring-boot-maven-plugin` được áp dụng. Goal `build-info` ở đây tạo metadata cho `BuildProperties`.

POM này có:

~~~text
GAV:      com.example.catalog:metadata-demo:1.2.3
<name>:   Catalog Service
<finalName>: catalog-service
~~~

Sau `mvn clean package`, JAR chính dự kiến là `target/catalog-service.jar`. **`finalName` đổi tên file, không đổi Maven artifactId/version**. Nếu không override, Maven thường tạo filename theo `artifactId-version`.

Cũng cần lưu ý Spring Boot Maven build-info lấy giá trị từ **Maven project**, có thể khác cách Gradle build-info lấy `build.artifact` từ Boot archive base name. Không copy expected stdout của ví dụ Gradle rồi coi đó là bắt buộc cho mọi Maven build.

## 10. Inspect build-info bằng Java 17 không cần chạy Spring

Nếu không có `unzip`, tạo file độc lập `BuildInfoInspector.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class BuildInfoInspector {
    private BuildInfoInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java BuildInfoInspector <boot-jar>");
            System.exit(2);
        }

        try (JarFile jar = new JarFile(args[0])) {
            JarEntry entry = jar.getJarEntry(
                    "BOOT-INF/classes/META-INF/build-info.properties");
            if (entry == null) {
                System.err.println("BUILD_INFO_MISSING");
                System.exit(3);
            }

            Properties props = new Properties();
            try (InputStream input = jar.getInputStream(entry)) {
                props.load(input);
            }

            System.out.println("GROUP=" +
                    props.getProperty("build.group", "(absent)"));
            System.out.println("ARTIFACT=" +
                    props.getProperty("build.artifact", "(absent)"));
            System.out.println("NAME=" +
                    props.getProperty("build.name", "(absent)"));
            System.out.println("VERSION=" +
                    props.getProperty("build.version", "(absent)"));
        }
    }
}
~~~

Biên dịch:

~~~bash
javac BuildInfoInspector.java
~~~

Chạy sau khi đã build Gradle demo:

~~~bash
java BuildInfoInspector build/libs/catalog-service-1.2.3.jar
~~~

Stdout:

~~~text
GROUP=com.example.catalog
ARTIFACT=catalog-service
NAME=metadata-demo
VERSION=1.2.3
~~~

`JarFile` mở outer executable Boot JAR, đọc entry build-info mà không giải nén nested dependencies hoặc chạy ứng dụng. Nếu đưa plain JAR hoặc Boot JAR chưa bật build-info, chương trình in `BUILD_INFO_MISSING` và thoát khác 0, thay vì đoán version từ filename.

## 11. Runtime identity, image tag và binary checksum

Một sản phẩm có thể được mô tả:

~~~text
Product:                Catalog Platform
Spring application name: orders-api
Gradle project name:    metadata-demo
Maven GAV:              com.example.catalog:metadata-demo:1.2.3
Executable file:        catalog-service-1.2.3.jar
Container image tag:    registry.example.test/catalog/orders-api:1.2.3
Git revision:           <commit-id-from-CI>
Image digest:           sha256:<digest-from-registry>
~~~

Các giá trị trong dấu ngoặc góc là **ký hiệu**, không phải dữ liệu đã được kiểm chứng. `registry.example.test` là hostname minh họa. Docker/OCI tag có thể bị gắn lại nếu registry policy cho phép; digest cụ thể phản ánh nội dung image đáng tin hơn chỉ một tag.

`spring.application.name` là danh tính logic của service, còn environment (`dev`/`staging`/`prod`), region, Kubernetes Deployment/Pod và container ID là thông tin triển khai. Không nhét environment vào GAV chỉ để phân biệt nơi chạy nếu release process promote **cùng binary** qua nhiều môi trường.

### Hash của artifact

Linux/macOS:

~~~bash
sha256sum build/libs/catalog-service-1.2.3.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 build/libs/catalog-service-1.2.3.jar
~~~

Checksum là giá trị tính từ **bytes thật** nên không có output cố định trong bài. Dùng GAV, artifact hash, Git commit và CI run/image digest khi cần xác thực chính xác phiên bản đã triển khai.

### Build time và reproducibility

Spring Boot `build-info.properties` mặc định có thể chứa `build.time` thay đổi theo thời điểm build. Theo tài liệu Spring Boot 3.3, điều đó khiến task build-info có thể luôn thay đổi output và ảnh hưởng up-to-date checks. Trong ví dụ:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

đã loại một nguồn thay đổi thời gian. Nhưng chỉ bỏ timestamp **không tự bảo đảm toàn bộ JAR có cùng SHA-256** sau rebuild: dependency resolution, archive metadata, generated sources, toolchains và các input khác vẫn cần quản lý.

### Bảo mật metadata

File build-info, manifest, logs và Actuator `info` có thể được người có quyền đọc artifact hoặc endpoint nhìn thấy. Không đưa password, token, private key, secret endpoint credentials hoặc thông tin nhạy cảm vào metadata. Nếu dùng Actuator info endpoint, cấu hình quyền truy cập và exposure phù hợp, không mặc định công khai.

## 12. Lệnh kiểm tra GAV và sản phẩm

### Gradle

~~~bash
./gradlew properties
./gradlew tasks --all
./gradlew clean bootJar
jar tf build/libs/catalog-service-1.2.3.jar
~~~

Với multi-project build, nếu app ở subproject `:app`:

~~~bash
./gradlew :app:properties
./gradlew :app:bootJar
~~~

Chỉ dùng đúng project path có trong settings. `properties` hiển thị nhiều giá trị, còn `jar tf` cho nội dung artifact cuối. Không coi tên file trong output là bằng chứng duy nhất về publication.

### Maven

~~~bash
mvn help:effective-pom
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
~~~

`effective-pom` giúp thấy các trường sau inheritance, plugin/dependency management. Lệnh `help:evaluate` cần Maven Help Plugin được resolve. Nếu project chỉ import Spring Boot BOM mà không cấu hình packaging plugin, BOM **không tự sinh executable JAR** hay gắn goal `repackage`.

### Manifest không phải Maven POM

Spring Boot executable JAR thường có:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.catalog.MetadataDemoApplication
~~~

Hai giá trị này dùng để khởi động Java/Spring Boot, **không phải GAV**. `Implementation-Version` trong manifest không luôn tự xuất hiện chỉ vì `project.version` có giá trị; dùng build-info hoặc cấu hình manifest riêng nếu cần.

## 13. Bảng lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Đổi tên `bootJar` mà Maven artifactId không đổi | Archive name và publication metadata độc lập | Xem `MavenPublication` và generated POM |
| `build.artifact` khác artifactId Maven | Boot build-info lấy archive base name | Xác định policy mapping, cấu hình đúng nơi |
| Đổi version nhưng filename vẫn `app.jar` | `archiveFileName` cố định | Dùng `archiveVersion` theo project.version |
| `spring.application.name` không giống project.name | Hai vai trò khác nhau | Giữ đúng runtime identity, ghi mapping |
| Thiếu bean `BuildProperties` | Chưa tạo/đóng gói `build-info.properties` | Bật `buildInfo` và kiểm tra archive |
| Manifest không có `Implementation-Version` | Chưa cấu hình trường đó | Dùng build-info hoặc manifest attribute riêng |
| CI publish sai artifactId | Maven Publish mặc định dùng project.name | Override `artifactId` ở publication |
| Local Maven cache có bản cũ | Version bị dùng lại hoặc publish cũ | Đọc POM/hash, tăng release version đúng policy |
| App chạy artifact cũ mặc dù tag giống | Registry/deployment/cache dùng file khác | So checksum và image digest |
| Boot JAR dùng làm Java library gây lỗi load | Executable layout khác ordinary JAR | Publish library component/variant |
| Nhiều modules publish cùng GAV | Tọa độ collision | Đặt artifactId hoặc version phù hợp |
| `ClassNotFoundException` lúc chạy | Dependency/packaging/classpath, không chỉ metadata | Kiểm tra `BOOT-INF/lib` và launcher |
| Actuator info lộ secrets | Metadata/exposure không an toàn | Không nhúng secrets, giới hạn quyền |
| Parent Maven làm version khó hiểu | Group/version có thể kế thừa | Xem `effective-pom` |

## 14. Checklist cho một release

1. **Xác định product, owner và namespace group**.
2. **Chọn artifactId rõ cho từng module**, không dùng trùng GAV cho bytes khác nhau.
3. **Đặt version theo chính sách**, phân biệt snapshots và releases.
4. **Phân biệt version project** với Spring Boot, Gradle, Java và dependency versions.
5. **Xác định file output** của `bootJar`/`bootWar` hay plain `jar`/`war`.
6. **Build đúng artifact** bằng Wrapper/toolchain/versions đã được kiểm soát.
7. **Đọc `build-info.properties` từ artifact thật**: group, artifact, name, version.
8. **Đối chiếu Maven publication/POM**, không đoán artifactId từ filename.
9. **Kiểm tra runtime `spring.application.name`** có phù hợp hệ thống logging/observability.
10. **Gắn provenance**: Git SHA, CI run, checksum và image digest khi có.
11. **Không ghi đè release artifact** dưới cùng tọa độ mà thay nội dung.
12. **Không đưa secrets vào metadata**.
13. **Smoke test bằng đúng executable JAR/container image** sẽ được triển khai.
14. **Ghi release record** để các nhóm có thể rollback và xác minh.

Mẫu release record:

~~~text
Product: Catalog Platform
Application name: orders-api
Group: com.example.catalog
Publication artifactId: metadata-demo
Version: 1.2.3
Executable JAR: catalog-service-1.2.3.jar
Git commit: <actual-commit>
SHA-256: <actual-hash>
OCI digest (if used): <actual-digest>
~~~

Đây chỉ là **mẫu điền thông tin**, phải thay các giá trị nằm trong ngoặc góc bằng kết quả thật từ CI/repository; không ghi commit hoặc hash tự bịa vào biên bản release.

## 15. Câu hỏi ôn tập

**Câu 1.** Gradle project group `com.example.catalog`, name `metadata-demo`, version `1.2.3`. MavenPublication mặc định có GAV nào?

**Đáp án:** `com.example.catalog:metadata-demo:1.2.3`.

**Câu 2.** Nếu `bootJar.archiveBaseName='catalog-service'` thì artifactId Maven có tự đổi thành `catalog-service` không?

**Đáp án:** Không. Archive base name và Maven publication artifactId là hai thuộc tính; Gradle Maven Publish mặc định artifactId từ project.name.

**Câu 3.** Vì sao `build.artifact=catalog-service` nhưng `build.name=metadata-demo`?

**Đáp án:** Spring Boot Gradle build-info mặc định lấy artifact từ Boot archive base name, name từ Gradle project.name.

**Câu 4.** `spring.application.name=orders-api` có thay GAV không?

**Đáp án:** Không. Đây là runtime Spring property, không phải Maven/Gradle publication metadata.

**Câu 5.** `project.version=1.2.3` có phải version của Spring Boot framework không?

**Đáp án:** Không. Đây là version sản phẩm/library; Boot plugin version khai báo riêng.

**Câu 6.** Maven `<finalName>catalog-service</finalName>` có làm artifactId thành `catalog-service` không?

**Đáp án:** Không. Nó đổi tên output file, không thay tọa độ `groupId:artifactId:version`.

**Câu 7.** Vì sao cùng GAV có thể chưa chứng minh hai file cùng bytes?

**Đáp án:** Repository/snapshot/overwrite hoặc non-reproducible rebuild có thể tạo bytes khác; cần hash, immutability và provenance.

**Câu 8.** Dùng thông tin nào để ứng dụng in version đã build?

**Đáp án:** Bật Spring Boot build-info, bảo đảm file `META-INF/build-info.properties` trên classpath, rồi đọc bằng `BuildProperties`.

**Câu 9.** Library `formatter-library` publish artifactId `format-kit`, consumer phải dùng tên nào?

**Đáp án:** Dùng tọa độ `com.example.catalog:format-kit:1.2.3` đã publish; tên local JAR có thể vẫn là `formatter-library-1.2.3.jar`.

**Câu 10.** Tại sao không nên chỉ dùng Docker tag `1.2.3` cho audit production?

**Đáp án:** Tag có thể bị retag nếu policy cho phép; digest/checksum giúp đối chiếu đúng nội dung đã triển khai.

## 16. Tài liệu chính thức

- Maven — [Maven Artifacts](https://maven.apache.org/repositories/artifacts.html): GAV, classifier, extension và tọa độ repository.
- Maven — [Naming Conventions](https://maven.apache.org/guides/mini/guide-naming-conventions.html): groupId, artifactId, version và SNAPSHOT.
- Maven — [Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): GAV ở POM, packaging và defaults.
- Gradle — [Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): default `MavenPublication` fields và artifactId override.
- Gradle — [MavenPublication API](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html): mapping project group/name/version.
- Gradle — [The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): archive tasks và library outputs.
- Spring Boot 3.3 — [Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html): `bootBuildInfo`, `build.artifact/group/name/version/time`.
- Spring Boot 3.3 — [Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): `bootJar` và output archive.
- Spring Boot — [Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): thông tin runtime và bảo mật endpoint.

**Ghi nhớ:** GAV xác định **artifact trong repository**, archive properties xác định **tên file build**, Spring Boot build-info xác định **metadata trong binary**, còn `spring.application.name` xác định **tên logic của ứng dụng runtime**. Khi phát hành hoặc rollback, hãy kiểm chứng **GAV → publication → file/checksum → build-info → deployment identity** thay vì mặc định mọi tên tự giống nhau.
