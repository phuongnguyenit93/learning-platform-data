# Tải sản phẩm từ kho và kiểm tra khả năng chạy hoặc sử dụng từ dự án khác

## 1. Mục tiêu và phạm vi

Sau khi sản phẩm Java/Spring Boot được publish lên artifact repository, cần kiểm tra rằng người dùng có thể **tải đúng phiên bản từ kho và sử dụng được trong một môi trường độc lập**. Có hai loại sản phẩm cần phân biệt:

1. **Ứng dụng executable**: Spring Boot JAR/WAR có thể chạy bằng `java -jar` hoặc deploy vào Servlet container. Cần tải artifact, kiểm tra manifest/runtime và chạy smoke test.
2. **Thư viện Java**: JAR cung cấp public API để dự án khác khai báo dependency, compile, test và gọi class/method. Cần resolve POM/metadata cùng transitive dependencies, rồi kiểm tra trong consumer project.

**Không thể kiểm chứng hai loại bằng cùng một cách.** Spring Boot executable JAR thường đặt application classes dưới `BOOT-INF/classes` và dependencies lồng trong `BOOT-INF/lib`; đây không phải cấu trúc của JAR thư viện thông thường trên Java compile classpath.

Ví dụ dùng **Spring Boot 3.3.5**, Java 17, Maven Wrapper, Gradle Wrapper và Maven Dependency Plugin 3.7.1. Đây là bộ version minh họa, không phải khuyến nghị bản mới nhất. Hãy dùng version được dự án phê duyệt.

Sau bài này, bạn có thể:

- Đọc Maven coordinates `groupId:artifactId:version[:type[:classifier]]` và hiểu đường dẫn artifact trong Maven-compatible repository.
- Phân biệt release, SNAPSHOT, POM metadata, classifier, executable JAR và plain library JAR.
- Cấu hình private repository credentials an toàn qua Maven `settings.xml` hoặc Gradle user properties.
- Tải một artifact cụ thể bằng Maven Dependency Plugin và chạy Spring Boot executable JAR đã tải.
- Tạo consumer project Maven/Gradle để resolve library, kiểm tra dependency graph, compile, test và gọi public API.
- Xác minh archive contents, manifest, Java compatibility, checksum và signature/provenance khi có.
- Chẩn đoán lỗi repository, coordinates, thiếu POM/transitive dependencies, nhầm Boot JAR với library, version conflict và cache cũ.

## 2. Artifact repository và Maven coordinates

Artifact repository lưu binary cùng metadata đã build. Một Maven module thường được nhận diện bằng GAV:

- `groupId`: namespace, ví dụ `com.example.catalog`.
- `artifactId`: tên module, ví dụ `catalog-client`.
- `version`: version, ví dụ `1.4.2`.

Artifact có thể có packaging/type như `jar`, `war`, `pom` và classifier như `sources`, `javadoc`, `exec`, `tests`.

Ví dụ:

~~~text
com.example.catalog:catalog-client:1.4.2
com.example.catalog:catalog-service:1.0.0:jar:exec
~~~

Maven repository chuẩn lưu theo đường dẫn:

~~~text
<repository-root>/
└── com/
    └── example/
        └── catalog/
            └── catalog-client/
                └── 1.4.2/
                    ├── catalog-client-1.4.2.pom
                    ├── catalog-client-1.4.2.jar
                    └── ...
~~~

Với classifier `exec`, file có tên `catalog-service-1.0.0-exec.jar`.

**POM không phải file phụ trang trí.** Nó mô tả coordinates, packaging và dependencies/scopes để consumer resolve đúng graph. Một JAR có thể tải được nhưng nếu POM thiếu hoặc sai, consumer vẫn compile fail hoặc runtime thiếu class.

| File | Ý nghĩa |
| --- | --- |
| `artifact-version.jar` | Binary JAR chính |
| `artifact-version.pom` | Maven metadata và transitive dependencies |
| `artifact-version-sources.jar` | Source code đính kèm |
| `artifact-version-javadoc.jar` | API documentation |
| `artifact-version-exec.jar` | Executable variant gắn classifier `exec` |
| `.module` | Gradle Module Metadata nếu publisher Gradle tạo |
| `.sha256`, `.sha512`, `.asc` | Checksum/signature sidecar nếu repository cung cấp |
| `maven-metadata.xml` | Metadata cho version/SNAPSHOT resolution |

Gradle đọc Maven POM và Gradle Module Metadata; Maven chủ yếu dùng POM. Không xóa metadata nếu consumer cần nó để biết dependency graph hoặc variants.

## 3. Phân biệt executable JAR và library JAR

Ví dụ Spring Boot executable JAR:

~~~text
catalog-service.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/catalog/...
    └── lib/spring-*.jar
~~~

Application class nằm dưới `BOOT-INF/classes`, còn dependency JAR nằm lồng trong `BOOT-INF/lib`. Java compiler của consumer project **không tự coi các đường dẫn lồng này là classpath bình thường**. Vì vậy, không dùng fat JAR làm dependency Java thông thường.

Plain library JAR thường có class ở root:

~~~text
com/example/catalog/CatalogClient.class
META-INF/MANIFEST.MF
~~~

| Loại | Kiểm tra | Cách dùng |
| --- | --- | --- |
| Spring Boot executable JAR | `BOOT-INF/classes`, `BOOT-INF/lib`, manifest/launcher | `java -jar app.jar` |
| Plain Java library | Package/class ở root, POM metadata | Maven/Gradle dependency |
| Executable WAR | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | `java -jar app.war` hoặc external Servlet container |
| POM-only artifact | Metadata, parent/BOM/dependency management | Import làm parent/BOM, không chạy như JAR |
| Sources/Javadoc | Nội dung source/docs, classifier | IDE/documentation tooling |

**Quy tắc:** dùng executable archive để chạy ứng dụng; dùng plain library JAR để làm dependency. Nếu cùng một module cần phát hành cả hai dạng, publish thành hai artifacts phân biệt bằng classifier hoặc tách module.

## 4. Repository URL, credentials và version policy

URL minh họa:

~~~text
Release:
https://repo.example.com/repository/maven-releases/

Snapshot:
https://repo.example.com/repository/maven-snapshots/
~~~

Thay bằng URL do tổ chức cung cấp. Không suy đoán URL repository manager từ tên server.

### 4.1. Maven settings.xml

Maven tra credentials trong user settings:

- Linux/macOS: `~/.m2/settings.xml`.
- Windows: `%USERPROFILE%\.m2\settings.xml`.

Ví dụ:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

`REPO_USER` và `REPO_TOKEN` được cấp từ môi trường developer/CI secret store. Maven settings hỗ trợ interpolation từ environment variables. **Không commit settings.xml chứa token, không hard-code password trong POM và không in credentials ra logs.**

`id` trong `<server>` phải khớp repository ID Maven dùng để tải/deploy. Sai ID có thể gây 401/403 dù token đúng.

### 4.2. Gradle credentials

Đặt credentials ngoài repository. Với repository tên `companyReleases`, Gradle tìm hai property `companyReleasesUsername` và `companyReleasesPassword` khi dùng `credentials(PasswordCredentials)`. Trên máy developer, lưu giá trị thật trong `GRADLE_USER_HOME/gradle.properties` với quyền đọc giới hạn; trong CI, cấp chúng từ secret store qua `ORG_GRADLE_PROJECT_companyReleasesUsername` và `ORG_GRADLE_PROJECT_companyReleasesPassword`. Không commit file chứa credentials và không in giá trị ra log.

### 4.3. Release và SNAPSHOT

| Version | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| `1.4.2` | Release cụ thể, bất biến sau publish | Dùng cho production |
| `1.5.0-RC1` | Pre-release | Chỉ dùng khi chấp nhận thử nghiệm |
| `1.5.0-SNAPSHOT` | Bản phát triển có thể publish lại | Dùng dev/integration |

**Không ghi đè release version đã publish.** Nếu cần sửa, phát hành version mới. SNAPSHOT dùng metadata và timestamped artifacts; cache có thể khiến hai máy resolve khác thời điểm. Maven hỗ trợ `-U` và Gradle hỗ trợ `--refresh-dependencies` để refresh có chủ đích.

## 5. Producer mẫu: publish Java library bằng Maven

Tạo library `catalog-client` chỉ cung cấp public API, không có Spring Boot launcher.

Cấu trúc:

~~~text
catalog-client/
├── pom.xml
└── src/main/java/com/example/catalog/
    └── CatalogClient.java
~~~

File `src/main/java/com/example/catalog/CatalogClient.java`:

~~~java
package com.example.catalog;

public final class CatalogClient {

    private CatalogClient() {
    }

    public static String greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name + " from catalog-client";
    }
}
~~~

### 5.1. POM producer

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-client</artifactId>
    <version>1.4.2</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/repository/maven-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>
</project>
~~~

- GAV xác định artifact.
- Compiler release 17 tạo bytecode tương thích Java 17.
- `distributionManagement` chỉ định nơi **deploy**; đây không phải cấu hình repository cho consumer.
- Repository IDs phải khớp `settings.xml`.
- Maven deploy lifecycle upload JAR, POM và metadata cần thiết.

Publish:

~~~bash
./mvnw --version
./mvnw clean deploy
~~~

PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean deploy
~~~

Repository có thể chứa:

~~~text
com/example/catalog/catalog-client/1.4.2/
├── catalog-client-1.4.2.pom
└── catalog-client-1.4.2.jar
~~~

**Không kết luận publish thành công chỉ vì JAR tồn tại trong `target`.** Cần xác minh artifact đã upload lên remote repository và consumer độc lập resolve được từ xa.

## 6. Consumer Maven: tải library và gọi API

Tạo project độc lập `catalog-consumer`. Không dùng source producer, `systemPath` hoặc JAR tự copy; consumer phải resolve GAV từ remote repository.

### 6.1. POM consumer

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.consumer</groupId>
    <artifactId>catalog-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.10.2</junit.version>
    </properties>

    <repositories>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/repository/maven-releases/</url>
            <releases>
                <enabled>true</enabled>
                <checksumPolicy>fail</checksumPolicy>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>catalog-client</artifactId>
            <version>1.4.2</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Repository ID `company-releases` khớp server ID trong Maven settings. `checksumPolicy=fail` khiến Maven dừng nếu checksum repository cung cấp không khớp; nó **không thay thế** chữ ký số/provenance độc lập.

### 6.2. Consumer gọi public API

File `src/main/java/com/example/consumer/ConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.example.catalog.CatalogClient;

public class ConsumerApplication {

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Ada";
        System.out.println(CatalogClient.greeting(name));
    }
}
~~~

File `src/test/java/com/example/consumer/CatalogClientIntegrationTest.java`:

~~~java
package com.example.consumer;

import com.example.catalog.CatalogClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogClientIntegrationTest {

    @Test
    void callsPublishedLibrary() {
        assertEquals(
                "Hello, Ada from catalog-client",
                CatalogClient.greeting("Ada")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> CatalogClient.greeting(" ")
        );
    }
}
~~~

Đây là **consumer-side test**: class public phải được resolve từ repository và method hoạt động như kỳ vọng. Producer test pass chưa đủ vì producer có thể chạy với source output/classpath khác artifact đã publish.

### 6.3. Chạy consumer

Linux/macOS:

~~~bash
./mvnw clean test
./mvnw dependency:tree -Dincludes=com.example:catalog-client
./mvnw -q compile exec:java \
    -Dexec.mainClass=com.example.consumer.ConsumerApplication \
    -Dexec.args=Ada
~~~

PowerShell:

~~~powershell
.\mvnw.cmd clean test
.\mvnw.cmd dependency:tree "-Dincludes=com.example:catalog-client"
.\mvnw.cmd -q compile exec:java "-Dexec.mainClass=com.example.consumer.ConsumerApplication" "-Dexec.args=Ada"
~~~

Output do consumer main in ra:

~~~text
Hello, Ada from catalog-client
~~~

`dependency:tree` cho biết version và transitive graph. `exec:java` chạy consumer với dependency classpath Maven đã resolve.

## 7. Consumer Gradle: dùng cùng Maven repository

Gradle cũng đọc Maven-compatible repository.

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example.consumer'
version = '1.0.0'

repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/repository/maven-releases/')
        credentials(PasswordCredentials)
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example:catalog-client:1.4.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.test {
    useJUnitPlatform()
}
~~~

`credentials(PasswordCredentials)` lấy properties theo repository name `companyReleases`, thường là `companyReleasesUsername` và `companyReleasesPassword` trong Gradle user properties. Không đặt token trong build script.

File `settings.gradle`:

~~~groovy
rootProject.name = 'catalog-consumer-gradle'
~~~

Dùng lại consumer main/test source ở mục 6 trong source layout Gradle.

Chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency catalog-client --configuration runtimeClasspath
./gradlew clean test
~~~

- `dependencies` liệt kê dependency graph.
- `dependencyInsight` giải thích version được chọn và selection reasons.
- `clean test` compile/test consumer với artifact từ Maven repository.

Nếu project có `gradle/verification-metadata.xml`, Gradle kiểm tra artifacts theo checksum/signature metadata trước khi dùng.

## 8. Tải executable Spring Boot JAR từ repository

Một ứng dụng runnable cần kiểm tra đúng **executable artifact**, manifest/Boot layout và khả năng khởi chạy.

### 8.1. Publish executable JAR với classifier exec

Ví dụ tọa độ:

~~~text
groupId:    com.example.catalog
artifactId: catalog-service
version:    1.0.0
classifier: exec
type:       jar
~~~

Spring Boot Maven Plugin `repackage` tạo executable JAR. Nếu muốn publish cả plain artifact lẫn executable artifact, cấu hình classifier `exec` để executable JAR được attach bên cạnh artifact chính.

**Fragment khi kế thừa `spring-boot-starter-parent`:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Starter Parent đã có execution ID `repackage`; ở trường hợp đó chỉ cần cấu hình classifier. Nếu không dùng parent và chưa có execution, phải khai báo goal `repackage` trong execution phù hợp.

Với classifier `exec`, Spring Boot Maven Plugin giữ plain JAR làm artifact chính và attach executable archive như artifact bổ sung:

~~~text
catalog-service-1.0.0.jar
catalog-service-1.0.0-exec.jar
catalog-service-1.0.0.pom
~~~

Consumer dùng plain JAR nếu đó thực sự là API library; operator tải classifier `exec` để chạy ứng dụng. Nếu module chỉ là application và không có API tái sử dụng, đừng coi plain JAR tự nhiên là library tốt.

### 8.2. Tải classifier bằng Maven Dependency Plugin

`dependency:get` nhận tọa độ:

~~~text
groupId:artifactId:version[:packaging[:classifier]]
~~~

Linux/macOS:

~~~bash
./mvnw org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get \
    -Dartifact=com.example.catalog:catalog-service:1.0.0:jar:exec \
    -Dtransitive=false \
    -DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/
~~~

PowerShell:

~~~powershell
.\mvnw.cmd org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get "-Dartifact=com.example.catalog:catalog-service:1.0.0:jar:exec" "-Dtransitive=false" "-DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/"
~~~

`company-releases` là repository ID; credentials lấy từ `settings.xml` cùng ID. `-Dtransitive=false` phù hợp với executable JAR vì Boot JAR đã đóng gói runtime dependencies. Với plain library JAR, consumer cần resolve POM/transitive dependencies.

Maven Dependency Plugin `dependency:get` luôn xét Maven Central theo quy tắc goal; mirror trong settings có thể điều hướng repository. Với repository nội bộ, cấu hình URL/ID và mirror theo chuẩn công ty.

### 8.3. Local repository path

Artifact tải về thường nằm tại:

~~~text
Linux/macOS:
~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar

Windows:
%USERPROFILE%\.m2\repository\com\example\catalog\catalog-service\1.0.0\catalog-service-1.0.0-exec.jar
~~~

Nếu Maven dùng `localRepository` tùy chỉnh trong settings, dùng đường dẫn đó. Đây là cache/download local, không phải file gốc trên remote repository.

### 8.4. Kiểm tra archive và chạy

~~~bash
jar tf ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar
~~~

Với Spring Boot executable JAR, cần thấy những phần phù hợp:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/...
BOOT-INF/lib/...
~~~

Kiểm tra manifest:

~~~bash
unzip -p ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar META-INF/MANIFEST.MF
~~~

Manifest executable thường có `Main-Class` là Spring Boot launcher và `Start-Class` là application main class. Không hard-code launcher name cho mọi Boot version; đọc manifest thực tế.

Chạy:

~~~bash
java -jar ~/.m2/repository/com/example/catalog/catalog-service/1.0.0/catalog-service-1.0.0-exec.jar --server.port=8081
~~~

Terminal khác:

~~~bash
curl -fsS http://localhost:8081/health
~~~

Nếu endpoint health demo trả `catalog-service-ok`, response body mong đợi là:

~~~text
catalog-service-ok
~~~

Đây là kiểm chứng **artifact tải từ kho có thể khởi chạy**. Nếu app cần database, credentials hoặc service ngoài, phải cấp runtime configuration hợp lệ; không nhúng secret vào JAR chỉ để smoke test.

## 9. Gradle producer: publish Java library

Nếu producer dùng Gradle, plugin `maven-publish` tạo Maven-compatible publication. Với thư viện Java thuần, dùng `java-library`:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.4.2'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/repository/maven-releases/')
            credentials(PasswordCredentials)
        }
    }
}
~~~

Gradle user properties nằm trong `GRADLE_USER_HOME/gradle.properties`, ngoài repository. Hai key `companyReleasesUsername` và `companyReleasesPassword` nhận giá trị thật từ secret store; khi dùng `credentials(PasswordCredentials)`, Gradle tự tra cứu chúng theo tên repository. CI có thể cấp cùng property qua `ORG_GRADLE_PROJECT_companyReleasesUsername` và `ORG_GRADLE_PROJECT_companyReleasesPassword`. Không commit file chứa credentials.

Publish:

~~~bash
./gradlew clean test publish
~~~

`from components.java` publish Java component cùng metadata Maven; `withSourcesJar()`/`withJavadocJar()` tạo source/Javadoc artifacts nếu cần.

**Nếu producer là Spring Boot application:** đừng mặc định publish `bootJar` làm library dependency. Spring Boot Gradle Plugin có thể tạo executable archive (`bootJar`) và plain archive (`jar`, thường classifier `plain`). Hãy xác định rõ artifact nào là library và artifact nào là executable distribution; tốt nhất tách library thành module `java-library` hoặc attach executable archive với classifier riêng. Kiểm tra publication tasks và repository contents trước khi giao cho consumer.

## 10. Xác minh checksum, chữ ký và provenance

Tải được file đúng tên chưa chứng minh bytes là đúng artifact đã được phê duyệt.

### 10.1. SHA-256

Linux/macOS:

~~~bash
sha256sum catalog-client-1.4.2.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\catalog-client-1.4.2.jar -Algorithm SHA256
~~~

So sánh với **checksum đáng tin cậy** từ CI, release manifest hoặc provenance đã xác thực. Nếu repository có `.sha256`, checksum giúp phát hiện lỗi truyền tải/biến đổi bytes; nếu checksum và JAR cùng đến từ nguồn bị xâm nhập, riêng checksum không chứng minh publisher là ai.

### 10.2. Chữ ký và Gradle dependency verification

Nếu tổ chức ký artifacts, xác minh chữ ký bằng public key/fingerprint đã phê duyệt và kiểm tra attestation/provenance theo release policy.

Gradle có dependency verification qua `gradle/verification-metadata.xml`, hỗ trợ SHA-256/SHA-512 và PGP signatures:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Lệnh bootstrap checksum metadata cho dependencies Gradle resolve. **Không commit kết quả mù quáng**: kiểm tra nguồn tin cậy, review diff và xác nhận checksum mới. Gradle không xác minh changing/SNAPSHOT dependencies theo cùng cách với release artifacts trong metadata verification.

### 10.3. Maven checksum policy

Maven repository declaration có thể cấu hình `checksumPolicy` cho release/snapshot metadata khi repository cung cấp checksum. `fail` khiến build dừng nếu checksum nhận được không khớp. Đây là kiểm tra integrity theo checksum repository; để xác minh publisher cần chữ ký/provenance và trust policy phù hợp.

### 10.4. Ghi nhận kết quả

Báo cáo kiểm chứng nên lưu:

- GAV và classifier/type chính xác.
- Repository URL/ID và version.
- SHA-256 của file đã tải.
- Maven/Gradle và Java version.
- Kết quả `jar tf`, manifest hoặc dependency graph.
- Test/consumer build result.
- Nếu là executable app: runtime settings, startup logs và HTTP smoke result.
- Release commit, CI run và signature/attestation reference nếu có.

## 11. POM và transitive dependencies

Khi consumer khai báo:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-client</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

Maven đọc POM để biết dependency graph. Ví dụ minh họa:

~~~text
catalog-consumer
└── com.example:catalog-client:1.4.2
    ├── org.slf4j:slf4j-api:...
    └── com.example:catalog-model:...
~~~

Nếu producer quên khai báo dependency cần thiết trong POM, consumer có thể compile fail hoặc runtime fail với `NoClassDefFoundError`.

Maven:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=com.example
./mvnw dependency:resolve
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency catalog-client --configuration runtimeClasspath
~~~

`dependency:tree` xem direct/transitive dependencies; `dependencyInsight` giải thích version được chọn và selection reasons.

**Không tự thêm mọi JAR transitive bằng tay vào `libs/`.** Dùng POM/Gradle Module Metadata để build tool quản lý dependency graph, version và scope.

## 12. Tương thích Java và API

Artifact tồn tại và checksum đúng nhưng vẫn có thể không tương thích consumer runtime.

1. **Java bytecode target:** thư viện compile với Java 21 không chạy trên Java 17; lỗi thường gặp là `UnsupportedClassVersionError`.
2. **Public API:** consumer gọi method/class có thật trong version được resolve không?
3. **Transitive dependencies:** POM mô tả đúng dependencies/scopes không?
4. **Binary compatibility:** đổi method signature hoặc xóa class có thể gây `NoSuchMethodError`/`NoClassDefFoundError`.
5. **Runtime assumptions:** thư viện có yêu cầu Spring context, servlet container, native library, file config hoặc environment variables không?
6. **Dependency conflicts:** consumer có thể dùng version khác của Spring/Jackson/logging; xem dependency graph.
7. **Artifact classifier/type:** tải nhầm `sources`, `tests`, `plain` hoặc `exec` sẽ cho cấu trúc khác mong đợi.

Kiểm tra public API của plain library JAR:

~~~bash
javap -classpath catalog-client-1.4.2.jar com.example.catalog.CatalogClient
~~~

`javap` in API mà compiler nhìn thấy; nó hữu ích để xác nhận class/method có trong artifact nhưng không thay consumer compilation/test.

## 13. Release và SNAPSHOT

Release `1.4.2` nên đại diện cho **một bộ bytes bất biến**. Nếu cần sửa, phát hành `1.4.3`. Không sửa nội dung `1.4.2` tại repository rồi giữ nguyên tọa độ; consumer có thể cache bản cũ, CI khác tải bản mới và hành vi không còn tái lập.

`1.5.0-SNAPSHOT` là version phát triển có thể thay đổi. Repository quản lý snapshot metadata/timestamped builds; Maven/Gradle cache policy có thể khiến hai máy resolve khác thời điểm.

Maven refresh:

~~~bash
./mvnw -U clean test
~~~

Gradle refresh:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

Không dùng SNAPSHOT làm dependency release production trừ khi có chính sách chấp nhận rõ ràng. Để tái lập, ưu tiên release bất biến hoặc dependency locking/verification/provenance.

## 14. Kiểm chứng từ xa, tránh local cache

Một lỗi kiểm thử phổ biến là producer chạy `install`/`publishToMavenLocal` rồi consumer dùng `mavenLocal()`. Cách này chứng minh artifact dùng được từ local Maven cache, nhưng **không chứng minh remote repository đã publish đúng**.

### Maven: local repository cô lập

~~~bash
./mvnw -Dmaven.repo.local=target/remote-verification-repo \
    org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get \
    -Dartifact=com.example:catalog-client:1.4.2 \
    -Dtransitive=false \
    -DremoteRepositories=company-releases::default::https://repo.example.com/repository/maven-releases/
~~~

Sau đó chạy consumer project với cùng local repository riêng:

~~~bash
./mvnw -Dmaven.repo.local=target/remote-verification-repo clean test
~~~

Maven phải tải plugin/dependencies vào cache tạm, nên lượt đầu có thể chậm. Cách này chứng minh consumer resolve từ remote repository nếu không có local artifact giả mạo sẵn trong cache riêng.

### Gradle: không dùng mavenLocal để che lỗi

Consumer Gradle khai báo repository đúng URL. Khi muốn refresh:

~~~bash
./gradlew --refresh-dependencies clean test
~~~

`--refresh-dependencies` yêu cầu Gradle kiểm tra metadata/artifact lại theo cache rules; nó không xóa toàn bộ `GRADLE_USER_HOME`.

**Không xóa bừa toàn bộ `~/.m2` hoặc `~/.gradle`** chỉ để xác minh một dependency. Dùng local repository/cache tạm hoặc refresh có kiểm soát.

## 15. Repository security và dependency confusion

Repository order và repository IDs ảnh hưởng artifact được resolve:

- Gradle tìm module từ repositories đã khai báo; thứ tự, metadata và content rules có ý nghĩa.
- Maven có thể dùng repositories trong POM, settings profiles và mirrors; mirror có thể chuyển requests qua internal proxy.
- Tọa độ nội bộ như `com.company:common-utils:1.0.0` không nên vô tình resolve từ public repository không được tổ chức kiểm soát.
- Repository manager nội bộ thường nên proxy/cache public dependencies và host private releases/snapshots theo policy thống nhất.
- Dùng HTTPS và credential permissions tối thiểu.
- Không dùng `flatDir` hoặc file JAR rời cho artifacts cần transitive dependency metadata.
- Không cho untrusted build publish/overwrite release coordinates mà production consumers tin cậy.
- Kiểm tra checksum, signature và provenance trước khi phát hành critical dependencies.

**Tránh repository shadowing/dependency confusion:** cùng GAV có thể xuất hiện ở nhiều nguồn. Nếu nguồn không được kiểm soát đứng trước hoặc được ưu tiên ngoài ý muốn, consumer có thể tải artifact khác bytes dù coordinates nhìn giống nhau. Dùng repository allowlist/content filters, centralized repository policy và verification metadata.

## 16. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| HTTP 401 | Credentials thiếu/sai hoặc server ID không khớp repository ID | Kiểm tra Maven settings, Gradle user properties và ID |
| HTTP 403 | Tài khoản xác thực được nhưng thiếu quyền read/deploy | Xin đúng repository permission |
| HTTP 404 | Sai GAV/version/classifier/repository URL hoặc chưa publish | So coordinates, path và repository contents |
| Could not find artifact | Repository chưa khai báo, mirror sai, version không tồn tại | Kiểm tra POM repositories, settings mirrors và logs |
| Có POM nhưng không có JAR | Publisher deploy thiếu binary hoặc packaging sai | Kiểm tra publish task, POM packaging và remote contents |
| Consumer compile fail vì thiếu class | Tải plain library sai version hoặc artifact không chứa public class | `jar tf`, `javap`, dependency tree và GAV |
| NoClassDefFoundError | POM thiếu dependency hoặc scope/optional sai | Kiểm tra POM/dependency tree; publish version mới |
| NoSuchMethodError | Binary/API version conflict lúc runtime | Xem dependency graph và API compatibility |
| UnsupportedClassVersionError | Artifact target Java cao hơn runtime | Kiểm tra JDK compiler release và consumer/runtime |
| no main manifest attribute | Đã tải plain JAR/library nhưng chạy bằng java -jar | Dùng executable classifier hoặc đúng application artifact |
| ClassNotFoundException với Boot JAR dependency | Application classes nằm trong BOOT-INF/classes | Dùng plain library JAR |
| App chạy local nhưng fail CI | Khác env/profile/secret/port/database/runtime | Chạy với cùng runtime config và CI smoke test |
| Snapshot cũ | Metadata/artifact cache chưa refresh | Maven -U, Gradle --refresh-dependencies |
| SHA-256 mismatch | File bị đổi, mirror khác bytes hoặc artifact bị can thiệp | Dừng build, xác minh trusted checksum/signature |
| Gradle không resolve private repo | Credential property name không trùng repository name | Kiểm tra companyReleasesUsername/Password |
| Maven deploy 401 | distributionManagement ID khác server ID | Đồng bộ ID và deploy permission |
| Consumer dùng nhầm local artifact | Có mavenLocal hoặc local cache từ publish trước | Dùng local repo tạm và remote repository explicit |
| POM thiếu transitive dependency | Producer chỉ publish JAR hoặc scope sai | Publish POM đúng, kiểm tra dependency tree |
| Classifier không tải được | Publisher chưa attach classifier | Kiểm tra repackage classifier và remote files |
| Download đúng JAR nhưng runtime thiếu config | App phụ thuộc environment/secret/service ngoài | Cấp config runtime hợp lệ, không nhúng secrets |
| Cùng GAV nhưng bytes khác | Repository shadowing hoặc release bị ghi đè | Kiểm tra repository order, immutable releases và checksums |

### Trình tự chẩn đoán

1. Xác nhận `groupId`, `artifactId`, `version`, `type` và `classifier`.
2. Kiểm tra repository URL/ID, credentials và release/snapshot policy.
3. Kiểm tra POM và binary có tồn tại trên remote.
4. Dùng Maven `dependency:get` hoặc Gradle resolution để lấy artifact.
5. Kiểm tra archive bằng `jar tf`, manifest và checksum.
6. Nếu là library, compile/test trong consumer độc lập.
7. Nếu là executable app, chạy `java -jar` và HTTP/CLI smoke test.
8. Kiểm tra Java version, transitive dependencies, runtime config và version conflicts.
9. Nếu checksum/signature không khớp, dừng sử dụng và điều tra nguồn publish; không bỏ qua verification.

## 17. Quy trình CI: publish xong phải có consumer verification

~~~text
Producer source
      |
      v
Build + producer tests
      |
      v
Publish release artifact + POM + metadata
      |
      v
Resolve from remote repository
      |
      +--> Executable JAR: inspect + java -jar + smoke test
      |
      +--> Library JAR: consumer compile + tests + runtime test
      |
      v
Checksum / signature / provenance checks
      |
      v
Mark release ready for downstream consumers
~~~

Checklist pipeline:

1. Build đúng commit, JDK và toolchain đã pin.
2. Chạy producer tests và quality checks.
3. Publish release version bất biến, không overwrite.
4. Tạo consumer workspace riêng, không share `target/classes` hoặc source producer.
5. Resolve bằng đúng remote repository, credentials read-only và coordinates đã publish.
6. Dùng local repository/cache mới hoặc refresh có kiểm soát để tránh local artifact cũ.
7. Kiểm tra POM/module metadata và transitive dependency graph.
8. Với library, compile/test consumer và gọi API thực tế.
9. Với executable app, tải đúng classifier/artifact, kiểm tra manifest, chạy app và smoke test endpoint.
10. Xác minh SHA-256/signature/provenance theo release policy.
11. Lưu build logs, test reports, GAV/classifier, repository, checksum và CI run ID.
12. Chỉ đánh dấu release-ready khi publisher và consumer verification đều pass.

**Một build producer xanh chưa đủ.** Consumer verification phát hiện lỗi chỉ lộ ra khi artifact rời source workspace: thiếu POM, classifier sai, dependency scope sai, classpath khác, version conflict hoặc runtime assumptions chưa được tài liệu hóa.

## 18. Bài thực hành và tiêu chí hoàn thành

1. Tạo library `catalog-client:1.4.2` với `CatalogClient.greeting()` và POM Java 17.
2. Cấu hình `distributionManagement` và credentials trong Maven user `settings.xml`.
3. Chạy `./mvnw clean deploy`; xác nhận JAR/POM xuất hiện ở release repository.
4. Tạo consumer Maven project mới, khai báo `company-releases` và dependency `com.example:catalog-client:1.4.2`.
5. Chạy `./mvnw clean test`; xác nhận consumer compile/test mà không include source producer.
6. Chạy `dependency:tree` và `exec:java`; kiểm tra output `Hello, Ada from catalog-client`.
7. Tạo consumer Gradle project, dùng cùng Maven repository và dependency GAV, chạy `dependencyInsight` cùng `clean test`.
8. Bật Gradle dependency verification nếu tổ chức yêu cầu, review checksum/signature metadata trước khi commit.
9. Tạo Spring Boot executable app artifact với classifier `exec`, giữ plain JAR riêng.
10. Dùng Maven `dependency:get` tải classifier `exec` từ remote repository; không lấy file từ `target/` producer.
11. Dùng `jar tf` và manifest xác nhận Boot launcher/nested libraries; chạy `java -jar` và HTTP smoke test.
12. Thử nhầm plain JAR với executable JAR, giải thích vì sao `java -jar` hoặc consumer classpath không đáp ứng mục đích.
13. Thử version không tồn tại hoặc classifier sai; đọc lỗi resolver và xác định đúng tọa độ.
14. Kiểm tra checksum với trusted release manifest; không chỉ so checksum sidecar không xác thực.
15. Ghi GAV, classifier, repo URL/ID, Java/Maven/Gradle versions, SHA-256, dependency graph, consumer tests và smoke result.
16. Khôi phục source thử nghiệm hoặc giữ version mới theo release policy; không overwrite release đã publish.

**Đạt yêu cầu khi:** bạn tải artifact từ remote repository, xác minh đúng version/bytes, chạy được executable Spring Boot archive, và chứng minh plain Java library được compile/test/call từ project Maven hoặc Gradle độc lập.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Apache Maven Dependency Plugin 3.7.1 – Usage and dependency:get](https://maven.apache.org/components/plugins-archives/maven-dependency-plugin-3.7.1/usage.html)
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven – Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Apache Maven – Deploying over HTTP(S)](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Gradle – Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html)
- [Gradle – Managing Dependencies of JVM Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)
- [Gradle – Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle – Securing Dependencies with Checksums and Signatures](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle – Securing Repositories and Credentials](https://docs.gradle.org/current/userguide/securing_repositories.html)
