# Giữ artifact thư viện riêng khi dự án đồng thời tạo sản phẩm thực thi

## 1. Vấn đề và mục tiêu

Một dự án Spring Boot có thể cần **hai loại sản phẩm từ cùng mã nguồn**: JAR thư viện cho ứng dụng khác sử dụng như dependency, và executable JAR có Spring Boot launcher để chạy bằng `java -jar`. Tuy cùng phần mở rộng `.jar`, cấu trúc và hợp đồng sử dụng khác nhau. Nếu Maven mặc định thay JAR chính bằng Boot executable JAR, downstream module dùng dependency bình thường có thể không import được class. Nếu Gradle dùng cùng tên output cho `jar` và `bootJar`, một task có thể ghi đè sản phẩm của task khác.

Bài này hướng dẫn **giữ một artifact thư viện không classifier** và tạo riêng một **artifact thực thi có classifier `exec`**, đồng thời kiểm tra cả cách tiêu thụ lẫn cách publish. Đối với dự án quy mô lớn, bài cũng chỉ rõ khi nào nên tách module `core` và `app` thay vì duy trì hai vai trò trong một module.

Sau bài học, bạn có thể:

1. So sánh plain Java JAR với Spring Boot executable JAR theo layout/classpath.
2. Cấu hình Maven `spring-boot:repackage` với `classifier=exec` và hiểu `attach`.
3. Cấu hình Gradle `jar` và `bootJar` với classifier khác nhau; tạo Maven publication gồm library chính và exec bổ sung.
4. Viết ví dụ chạy được với Java 17, Spring Boot 4.1.2, Maven và Gradle.
5. Biên dịch một consumer Java độc lập **chỉ dùng ordinary JAR**, rồi chạy HTTP service từ exec JAR để kiểm tra hai hợp đồng riêng.
6. Nhận diện lỗi metadata, classifier, plugin inheritance, dependency coupling và multi-module.
7. Định nghĩa QA gates cho cả build artifact, consumer và release repository.

**Bối cảnh:** *Tùy biến đóng gói* trong Spring Boot Build Tooling Packaging. Ví dụ dùng Java 17, Spring Boot 4.1.2, Maven tương thích hoặc Gradle phiên bản được Boot plugin hỗ trợ. Tên artifact trong ví dụ là `dual-artifact-demo:1.0.0`.

## 2. Tại sao không dùng một Boot JAR làm cả thư viện?

### Plain JAR dùng làm library

Trong một ordinary JAR, class nằm ở đường dẫn tương ứng tên package:

~~~text
dual-artifact-demo-1.0.0.jar
├── META-INF/MANIFEST.MF
└── dev/example/dual/
    ├── DualArtifactApplication.class
    └── api/PublicGreeting.class
~~~

Chương trình khác có thể import `dev.example.dual.api.PublicGreeting` nếu JAR này được đặt trên compile classpath. JAR thư viện **không bắt buộc** có executable `Main-Class` hay tự chứa runtime dependencies. Thông tin các dependency của nó đến từ POM hoặc Gradle module metadata khi được publish.

### Executable Spring Boot JAR

Khi dùng Maven `spring-boot:repackage` hoặc Gradle `bootJar`, cấu trúc mặc định của executable JAR là:

~~~text
dual-artifact-demo-1.0.0-exec.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── dev/example/dual/
    │       ├── DualArtifactApplication.class
    │       └── api/PublicGreeting.class
    └── lib/
        ├── spring-boot-...jar
        └── ...
~~~

Spring Boot launcher cung cấp classpath đặc biệt từ `BOOT-INF/classes` và nested JARs trong `BOOT-INF/lib` để chạy `java -jar`. Nhưng compiler/classloader Java tiêu chuẩn **không tự xem `BOOT-INF/classes` là root package path** khi executable JAR được thêm vào classpath thư viện. Vì vậy một downstream project có thể báo `package ... does not exist` dù class thực sự tồn tại bên trong executable JAR.

| Khía cạnh | Plain library JAR | Boot executable JAR |
| --- | --- | --- |
| Đường dẫn class | `dev/example/.../*.class` | `BOOT-INF/classes/dev/example/.../*.class` |
| Runtime dependencies | Được resolve qua POM/module metadata | Thường nằm dưới `BOOT-INF/lib` |
| Entry point | Không bắt buộc | Boot launcher và `Start-Class` |
| Người sử dụng | `javac`, compiler, Maven/Gradle dependency graph | JVM `java -jar`, nền tảng triển khai |
| Kiểm thử đúng | Biên dịch/chạy consumer từ classpath | Launch app và smoke test |
| Có thể thay thế nhau? | Không | Không |

**Nguyên tắc:** ordinary JAR là **hợp đồng classpath cho consumer**; executable JAR là **hợp đồng runtime cho deployment**. Classifier phân biệt artifact, nhưng chính cách đóng gói tạo ra hai cấu trúc.

## 3. Ba phương án kiến trúc

**Phương án A — Một module, hai archive.** Cùng `groupId:artifactId:version`, ordinary JAR giữ tọa độ **không classifier**, executable JAR dùng classifier `exec`. Ít thay đổi project, version đồng bộ, phù hợp khi đang duy trì một ứng dụng mà chỉ một API nhỏ cần tái sử dụng.

**Phương án B — Hai module `core` và `app`.** `core` chứa API/logic và chỉ tạo JAR thư viện; `app` phụ thuộc `core` và tạo Boot executable. Rõ boundary hơn, consumer không vô tình kéo toàn bộ phụ thuộc web/database của ứng dụng. Đây thường là lựa chọn tốt cho nhiều downstream consumers.

**Phương án C — Hai repository hoặc release streams.** Dùng khi public library và service có ownership, compatibility, bảo mật hoặc release cadence khác nhau. Đổi lại, version/dependency management phức tạp hơn. Không cần dùng phương án C chỉ vì mong muốn một file `-exec.jar`.

~~~text
A — Single-module dual artifact
src/main/java --> compile --> plain.jar        (library)
                        \--> Boot repackage   (exec.jar)

B — Multi-module
core/src --> core.jar (library)
             |
             v
app/src + core.jar --> bootJar/repackage --> app.jar (executable)
~~~

**Lưu ý quan trọng:** tách hai file trong cùng một module **không tự tách dependency graph**. Một consumer chỉ cần class API thuần Java vẫn có thể nhận dependency metadata của toàn bộ module Spring Boot. Cân nhắc tách module khi vấn đề đó trở nên đáng kể.

## 4. Maven: mặc định repackage thay artifact chính

Khi Maven module có packaging `jar`, phase `package` chạy `maven-jar-plugin:jar` trước, tạo ordinary JAR. Goal `spring-boot:repackage` sau đó biến source archive thành executable archive. Nếu **không cấu hình classifier**, plugin mặc định thay **main artifact** bằng executable JAR; bản gốc thường được lưu ở local với tên `*.jar.original`.

~~~text
Mặc định:
target/dual-artifact-demo-1.0.0.jar          -> executable
target/dual-artifact-demo-1.0.0.jar.original -> JAR trước repackage
~~~

Khi `mvn install` hoặc `mvn deploy` chạy với `attach=true` mặc định, **main artifact** có thể là executable JAR. Điều này không phù hợp nếu các project khác cần ordinary JAR ở tọa độ không classifier. File `.jar.original` chỉ nằm trong thư mục build và **không phải** một supplementary artifact tự động được publish làm thư viện.

### Cấu hình classifier `exec`

Giữ ordinary JAR ở tọa độ chính và tạo thêm executable JAR:

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

**Đây là cấu hình dùng với `spring-boot-starter-parent`.** Parent đã định nghĩa execution có ID `repackage`; child tùy biến **cùng ID** để merge configuration, không thêm một execution khác khiến repackage chạy trùng.

Output:

~~~text
target/dual-artifact-demo-1.0.0.jar       -> plain library JAR
target/dual-artifact-demo-1.0.0-exec.jar  -> executable Boot JAR
~~~

Hai tọa độ Maven tương ứng:

~~~text
dev.example:dual-artifact-demo:jar:1.0.0
dev.example:dual-artifact-demo:jar:exec:1.0.0
~~~

Tọa độ thứ nhất không có classifier; tọa độ thứ hai dùng `exec`. **Classifier là thành phần định danh artifact, không phải một `artifactId` mới.**

### Vai trò của `attach`

- `attach=true` (mặc định): nếu `classifier=exec`, bản executable được attach **bên cạnh** ordinary JAR để tham gia `install`/`deploy`.
- `attach=false`: executable vẫn có thể được tạo ở local, nhưng không được attach để install/deploy. Chỉ nên dùng khi pipeline chủ đích publish thư viện mà phát hành executable bằng kênh khác.
- `skip=true`: bỏ qua repackage, nên không có executable JAR từ goal đó.
- `layout=NONE`: không tạo Boot bootstrap launcher; không phù hợp nếu phải chạy bằng `java -jar` thông thường.

Cần phân biệt **file được tạo trong `target`** và **artifact thực sự được attach/publish**. Build thành công không bảo đảm remote repository đã có cả hai.

## 5. Ví dụ Maven hoàn chỉnh, Java 17 và Spring Boot 4.1.2

### Cấu trúc dự án

~~~text
dual-artifact-demo/
├── pom.xml
├── src/main/java/dev/example/dual/
│   ├── DualArtifactApplication.java
│   └── api/PublicGreeting.java
├── src/test/java/dev/example/dual/PublicGreetingTest.java
└── consumer/
    └── ConsumerMain.java
~~~

Thư mục `consumer` là ví dụ một chương trình riêng, **không** nằm dưới Maven main source set. Nhờ vậy khi biên dịch consumer, ta thực sự kiểm tra output ordinary JAR thay vì vô tình tìm class từ project sources.

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <classifier>exec</classifier>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM này không cần lặp lại `<goal>repackage</goal>` vì starter parent đã cung cấp execution. Classifier được khai báo **bên trong đúng execution** để giữ bản JAR gốc làm main artifact.

### API thư viện — `src/main/java/dev/example/dual/api/PublicGreeting.java`

~~~java
package dev.example.dual.api;

public final class PublicGreeting {
    private PublicGreeting() {
    }

    public static String text() {
        return "LIBRARY_OK";
    }
}
~~~

Đây là API Java thuần, không cần Spring để sử dụng. Mục tiêu là tạo một hợp đồng classpath kiểm chứng được bằng `javac` và `java` mà không phải resolve web server framework ở consumer demo.

### Ứng dụng — `src/main/java/dev/example/dual/DualArtifactApplication.java`

~~~java
package dev.example.dual;

import dev.example.dual.api.PublicGreeting;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DualArtifactApplication {
    public static void main(String[] args) {
        SpringApplication.run(DualArtifactApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting() {
        return PublicGreeting.text();
    }
}
~~~

Ứng dụng Spring Boot sử dụng cùng class API và trả nội dung đó qua HTTP. Với Spring Boot 4.1.2, `spring-boot-starter-webmvc` cấp dependency cần cho MVC và servlet web server được autoconfigure.

### Unit test — `src/test/java/dev/example/dual/PublicGreetingTest.java`

~~~java
package dev.example.dual;

import dev.example.dual.api.PublicGreeting;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublicGreetingTest {
    @Test
    void returnsExpectedLibraryValue() {
        assertEquals("LIBRARY_OK", PublicGreeting.text());
    }
}
~~~

Test xác minh Java logic nhưng **chưa** xác minh library archive đã được đóng gói ở package root. Vì vậy vẫn cần consumer test và kiểm tra JAR thực tế ở các phần sau.

### Build

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Kết quả mong muốn:

~~~text
target/
├── classes/...
├── surefire-reports/...
├── dual-artifact-demo-1.0.0.jar
└── dual-artifact-demo-1.0.0-exec.jar
~~~

Với `repackage` có classifier, **không cần** kỳ vọng có file `.jar.original`. Ordinary JAR và executable JAR là hai artifact riêng, không phải bản backup cũ của nhau. Kiểm tra log Maven để thấy `jar:jar` chạy trước `spring-boot:repackage`.

## 6. Kiểm tra hai sản phẩm độc lập

### 6.1. Kiểm tra archive layout

~~~bash
jar tf target/dual-artifact-demo-1.0.0.jar
jar tf target/dual-artifact-demo-1.0.0-exec.jar
~~~

Trong ordinary JAR phải có entry:

~~~text
dev/example/dual/api/PublicGreeting.class
dev/example/dual/DualArtifactApplication.class
~~~

Trong executable JAR phải có entry:

~~~text
BOOT-INF/classes/dev/example/dual/api/PublicGreeting.class
BOOT-INF/classes/dev/example/dual/DualArtifactApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Plain JAR không cần `Main-Class`. Executable JAR mặc định có manifest với Boot launcher trong `Main-Class` và class ứng dụng trong `Start-Class`. `jar tf` chứng minh sự tồn tại entries, nhưng chưa chứng minh consumer compile hoặc ứng dụng chạy được.

### 6.2. Consumer Java — `consumer/ConsumerMain.java`

~~~java
package dev.consumer;

import dev.example.dual.api.PublicGreeting;

public class ConsumerMain {
    public static void main(String[] args) {
        System.out.println("CONSUMER=" + PublicGreeting.text());
    }
}
~~~

**Linux/macOS** từ project root, sau `mvn clean verify`:

~~~bash
mkdir -p target/consumer-classes
javac -cp target/dual-artifact-demo-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:target/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Stdout chính xác:**

~~~text
CONSUMER=LIBRARY_OK
~~~

Trên Windows PowerShell, classpath separator là dấu chấm phẩy:

~~~powershell
New-Item -ItemType Directory -Force target\consumer-classes | Out-Null
javac -cp target\dual-artifact-demo-1.0.0.jar -d target\consumer-classes consumer\ConsumerMain.java
java -cp "target\consumer-classes;target\dual-artifact-demo-1.0.0.jar" dev.consumer.ConsumerMain
~~~

Nếu `javac` không thể import `PublicGreeting` từ ordinary JAR, kiểm tra package name, version/classifier và nội dung `jar tf`. Không dùng output `target/classes` làm `-cp` trong consumer test vì điều đó sẽ che lỗi đóng gói ordinary JAR.

**Phép phản chứng:** thay `-cp` bằng đường dẫn `-exec.jar` trong lệnh `javac` sẽ không cho compiler chuẩn thấy class ở classpath root như mong đợi. Đây là điểm khác biệt cấu trúc của Boot executable JAR, không phải class đã biến mất khỏi archive.

### 6.3. Thử executable bằng HTTP

Trong terminal thứ nhất:

~~~bash
java -jar target/dual-artifact-demo-1.0.0-exec.jar --server.port=18080
~~~

Trong terminal thứ hai, khi server đã khởi động:

~~~bash
curl -fsS http://127.0.0.1:18080/greeting
~~~

**HTTP response body chính xác:**

~~~text
LIBRARY_OK
~~~

Ứng dụng không tự in chuỗi này ra stdout; đây là **HTTP response body**. Không khẳng định toàn bộ console output là `LIBRARY_OK` vì Spring Boot còn có log. Dừng server bằng `Ctrl+C` sau thử nghiệm.

Hai kiểm chứng có mục đích khác nhau: **consumer test** chứng minh ordinary JAR phù hợp làm library; **HTTP smoke test** chứng minh executable JAR chạy được cùng runtime dependencies.

## 7. Maven không có starter parent: phải bind goal

Nếu module dùng corporate parent hoặc chỉ import `spring-boot-dependencies` BOM, hãy nhớ rằng import BOM chỉ quản lý **dependency versions**, không nhập execution của Boot starter parent. Khi đó cần khai báo version Boot Maven Plugin và goal `repackage` trong phase `package`.

Đây là **fragment cho `<build><plugins>`**, không phải một POM hoàn chỉnh:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

BOM được import riêng dưới `<dependencyManagement>` với `<type>pom</type>` và `<scope>import</scope>`. Compiler, Surefire, Jar Plugin và Java release target cũng cần phiên bản/cấu hình phù hợp vì những defaults của starter parent không còn được kế thừa.

Chạy `mvn help:effective-pom` để kiểm tra execution. Nếu corporate parent đã có goal `repackage`, cấu hình child phải merge/tùy biến execution đúng ID, tránh chạy trùng.

**Bẫy classifier chọn source:** Khi source JAR mang **cùng classifier `exec`** đã tồn tại, Boot `repackage` có thể chọn nó làm source archive thay vì ordinary main JAR. Vì thế đừng để `maven-jar-plugin` đồng thời tạo một `-exec.jar` khác ngoài ý muốn. Nếu nhiều goals ở cùng phase `package`, khai báo Jar Plugin trước Boot Plugin khi cần đảm bảo source archive được tạo trước.

## 8. Maven install/deploy và tọa độ của hai artifact

Sau khi cấu hình `classifier=exec`, `attach=true` mặc định:

~~~bash
mvn clean install
~~~

Local Maven repository thường có:

~~~text
~/.m2/repository/dev/example/dual-artifact-demo/1.0.0/
├── dual-artifact-demo-1.0.0.pom
├── dual-artifact-demo-1.0.0.jar
└── dual-artifact-demo-1.0.0-exec.jar
~~~

**Downstream Maven consumer** dùng ordinary artifact không classifier:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Nếu thêm `<classifier>exec</classifier>`, Maven sẽ lấy executable artifact, **không nên dùng** làm compile dependency thông thường. Một consumer chỉ cần public library API thì không được cố import `BOOT-INF/classes` bằng custom code.

`mvn install` chỉ cài trong local repository; `mvn deploy` mới phát hành tới remote repository với `distributionManagement` và credential phù hợp. `mvn package` hay `mvn verify` không có nghĩa đã publish hai artifact. Sau khi publish, hãy kiểm tra **file, classifier và metadata** tại repository thật.

Với dự án mà executable chỉ dùng để tạo container image, có thể đặt `attach=false` và publish ordinary JAR, nhưng **không** làm vậy nếu deployment pipeline cần tải classifier `exec` từ repository. Cần chốt rõ policy phân phối.

## 9. Gradle: `jar` và `bootJar` có output và classifier riêng

Khi áp dụng Spring Boot Gradle Plugin cùng Java plugin:

- `jar` tạo ordinary JAR với class ở root package path.
- `bootJar` tạo executable Spring Boot archive có `BOOT-INF/classes` và `BOOT-INF/lib`.
- Theo mặc định của Boot Gradle Plugin, khi `bootJar` được cấu hình, `jar` thường nhận classifier `plain` để không ghi đè output:

~~~text
build/libs/
├── dual-artifact-demo-1.0.0.jar        # bootJar executable
└── dual-artifact-demo-1.0.0-plain.jar  # ordinary JAR
~~~

Nếu muốn **artifact thư viện không classifier** và executable là variant `exec` như trong Maven, đổi rõ:

~~~groovy
tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
}
~~~

Output mong muốn:

~~~text
build/libs/
├── dual-artifact-demo-1.0.0.jar       # ordinary library
└── dual-artifact-demo-1.0.0-exec.jar  # Boot executable
~~~

Chú ý `jar` và `bootJar` là hai task khác nhau. **Đừng disable `jar`** nếu ordinary JAR là deliverable. Ngược lại, chỉ thấy hai file `.jar` trong `build/libs` chưa chứng minh publication đã mang cả hai; xuất bản là bước riêng.

## 10. Ví dụ Gradle Groovy DSL đầy đủ

Dùng lại Java `PublicGreeting`, `DualArtifactApplication`, `PublicGreetingTest` và `consumer/ConsumerMain.java` của mục 5–6. Với lựa chọn Gradle, tạo:

**`settings.gradle`**

~~~groovy
rootProject.name = 'dual-artifact-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot' version '4.1.2'
    id 'maven-publish'
}

group = 'dev.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('jar') {
    archiveClassifier = ''
}

tasks.named('bootJar') {
    archiveClassifier = 'exec'
    mainClass = 'dev.example.dual.DualArtifactApplication'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact tasks.named('bootJar')
        }
    }
}
~~~

**Giải thích:**

- `java-library` tạo Java component và ordinary `jar`. Đây là lựa chọn rõ khi module có API được publish.
- Spring Boot Gradle Plugin tạo `bootJar`, được liên kết vào assemble khi dùng Java plugin.
- BOM được đưa vào Gradle native platform để các starter dependencies được quản lý version; ví dụ dùng `api platform` giúp truyền constraints phù hợp qua Java component metadata. Trong dự án thật cần đánh giá mức độ expose dependency/BOM tới consumer.
- `jar.archiveClassifier=''` làm ordinary JAR trở thành artifact không classifier.
- `bootJar.archiveClassifier='exec'` làm executable JAR thành artifact classified.
- `maven-publish` tạo publication `mavenJava`. `from components.java` dùng ordinary Java library component làm publication chính; `artifact tasks.named('bootJar')` thêm executable JAR như supplemental artifact.
- Tránh thêm một publication thứ hai có cùng extension và classifier không phân biệt được, vì sẽ tạo duplicate/collision hoặc publish không rõ sản phẩm nào là main.
- `maven-publish` có thể sinh Gradle Module Metadata bên cạnh Maven POM. Để bảo đảm downstream dùng đúng artifact, phải kiểm tra resolved metadata/variant thực tế ở cả Maven và Gradle consumer khi phát hành.

### Chạy build Gradle

Nếu dự án đã có Gradle Wrapper tương thích:

~~~bash
./gradlew clean build
jar tf build/libs/dual-artifact-demo-1.0.0.jar
jar tf build/libs/dual-artifact-demo-1.0.0-exec.jar
~~~

Bản ordinary JAR phải có `dev/example/dual/api/PublicGreeting.class` tại root; executable JAR phải có cùng class dưới `BOOT-INF/classes`. Task `build` chạy Java verification theo graph và task `assemble` của Boot plugin kết nối với `bootJar`. `./gradlew bootJar` đơn lẻ **không tự đảm bảo đã chạy unit test**.

### Consumer test với Gradle output

~~~bash
mkdir -p build/consumer-classes
javac -cp build/libs/dual-artifact-demo-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:build/libs/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Stdout chính xác:** `CONSUMER=LIBRARY_OK`.

### Chạy executable và kiểm tra HTTP

~~~bash
java -jar build/libs/dual-artifact-demo-1.0.0-exec.jar --server.port=18080
~~~

Ở terminal khác:

~~~bash
curl -fsS http://127.0.0.1:18080/greeting
~~~

HTTP body chính xác là `LIBRARY_OK`.

### Publish local

~~~bash
./gradlew publishToMavenLocal
~~~

Lệnh này xuất bản **tại local Maven repository** những artifact được cấu hình trong publication. Kiểm tra hai file `.jar` và `-exec.jar` cùng metadata ở repository; đừng suy ra remote registry được cập nhật. Nếu muốn publish remote, phải cấu hình repository và credential riêng trong block `publishing.repositories` theo hệ thống của tổ chức.

## 11. Cân nhắc dependency/API coupling

Giữ library và executable trong cùng module không có nghĩa metadata dependency tự được tách. Khi `dual-artifact-demo` có `spring-boot-starter-webmvc` làm runtime dependency, ordinary JAR được publish theo cùng module có thể khiến consumer resolve web/framework dependencies dù API `PublicGreeting` không dùng Spring.

Điều này **không phải lỗi classifier**. Classifier tách artifact file, không tách POM/module dependency graph. Giải pháp:

- Giữ **public API** nhỏ và tránh expose các kiểu Spring/Web/DB nếu thư viện không có chủ đích phụ thuộc chúng.
- Dùng Maven scopes và dependencyManagement có kiểm soát; không tùy tiện đặt dependency `provided` chỉ để giảm dependency graph nếu executable cần dependency đó khi chạy.
- Với Gradle `java-library`, phân biệt `api` và `implementation`. Chỉ đưa dependency vào `api` khi type đó nằm trong public API; kiểm tra publication metadata.
- Khi nhiều consumer hoặc thư viện cần release độc lập, tách module `core` và `app`.
- Công bố rõ lịch tương thích API (binary/source), version, deprecations và artifact coordinates để consumer không bị ép nâng theo service release ngoài ý muốn.

## 12. Multi-module: phương án sạch hơn cho dự án lớn

~~~text
root/
├── greeting-core/           -> plain JAR, library API
│   └── dev.example.core.GreetingService
└── greeting-app/            -> executable Boot JAR
    └── depends on greeting-core
~~~

**Maven:** Root có packaging `pom` và modules `greeting-core`, `greeting-app`. Module core chỉ cần `jar:jar` và không bật `repackage`; module app chứa `spring-boot-maven-plugin` và `@SpringBootApplication`.

Root `pom.xml` fragment:

~~~xml
<packaging>pom</packaging>
<modules>
    <module>greeting-core</module>
    <module>greeting-app</module>
</modules>
~~~

Dependency trong app `pom.xml` fragment:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

**Gradle:** `settings.gradle`:

~~~groovy
rootProject.name = 'dual-artifact-platform'
include 'greeting-core', 'greeting-app'
~~~

App `build.gradle` fragment:

~~~groovy
dependencies {
    implementation project(':greeting-core')
}
~~~

Các fragment này chỉ cho thấy **liên kết module**, không phải build configuration đầy đủ; repository, BOM, plugin versions và Java toolchain vẫn phải cấu hình đúng. `greeting-core` áp dụng `java-library`; `greeting-app` áp dụng Boot Gradle Plugin. Consumer của library phụ thuộc **greeting-core**, không phụ thuộc `greeting-app`.

**Điểm cần tránh:** không bind Boot `repackage` ở root packaging `pom` hoặc inherited đại trà cho mọi child library; điều đó có thể khiến library bị biến thành executable archive, hoặc module root không có source JAR để repackage.

## 13. Phân biệt cách xuất bản và cách tiêu thụ

| Hành động | Maven | Gradle | Ý nghĩa |
| --- | --- | --- | --- |
| Build ordinary JAR | `jar:jar` mặc định ở `package` | `jar` | Artifact thư viện |
| Build exec JAR | `spring-boot:repackage` classifier `exec` | `bootJar` classifier `exec` | Artifact để chạy |
| Chạy test | `mvn verify` | `./gradlew build` | Theo goals/tasks đã cấu hình |
| Cài local repository | `mvn install` | `publishToMavenLocal` | Test consumers trên máy build |
| Publish remote | `mvn deploy` | `publish` với repository config | Phát hành artifact ra nơi khác |
| Consumer library | Không dùng classifier | Tọa độ/variant Java library | Dùng classpath bình thường |
| Deploy executable | Classifier `exec` hoặc file ứng dụng rõ ràng | Output `bootJar` | `java -jar` / container |

**Không dùng `mvn package` hay `./gradlew build` làm bằng chứng đã publish artifact**. Build artifact nằm trong `target`/`build/libs`; publication là bước tường minh tiếp theo.

Maven consumer bình thường:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>dual-artifact-demo</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Thêm `<classifier>exec</classifier>` sẽ chọn executable artifact, không nên dùng để compile Java consumer thông thường. Với Gradle, một consumer có thể khai báo `implementation 'dev.example:dual-artifact-demo:1.0.0'` nhưng cần kiểm tra Gradle Module Metadata/variants nếu repository tạo ra nhiều artifacts và custom variants. Nếu chỉ có một API ổn định, module library độc lập là cách tránh nhập nhằng lâu dài.

## 14. Bẫy thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hành động kiểm tra |
| --- | --- | --- |
| Consumer import class không được | Dùng Boot executable thay ordinary JAR | `jar tf`: class phải nằm ở root package path |
| `java -jar` plain JAR lỗi | Không có Boot launcher hoặc thiếu runtime deps | Chạy đúng `-exec.jar` |
| Maven tạo `.jar.original` nhưng không có ordinary artifact publish | Không classifier, repackage đã thay main artifact | Đặt classifier `exec`, kiểm tra `attach` |
| Maven Boot plugin chạy hai lần | Starter parent đã có execution ID `repackage`, child thêm execution khác ID | Dùng đúng ID inherited và đọc effective POM |
| Maven exec không publish | `attach=false` hoặc execution bị skip | Kiểm tra config, install/deploy output |
| Maven chọn sai archive làm source | Có sẵn artifact mang classifier `exec` | Kiểm tra Jar Plugin executions và thứ tự phase `package` |
| Gradle hai outputs trùng path | `jar` và `bootJar` có cùng archive name/classifier | Đặt `jar=''`, `bootJar='exec'` |
| Gradle chỉ build exec JAR | Task `jar` bị disable hoặc không nằm trong graph | Bật `jar`, kiểm tra `assemble` và outputs |
| Gradle build 2 JAR nhưng publish 1 | Publication thiếu `artifact tasks.named('bootJar')` | Cấu hình `maven-publish` và kiểm tra local repo |
| Publication báo duplicate artifact | Cả hai jar có cùng extension/classifier trong publication | Đặt classifiers phân biệt |
| App/consumer khác version | Pipeline build hai artifact khác commit/version | Build cùng một job/commit, kiểm tra checksums |
| Consumer kéo nhiều dependency không cần | Một module kiêm service và library | Tách `core`, xem Maven scopes/Gradle api/implementation |
| CI chỉ đếm 2 file nhưng vẫn sai | Một file có thể là `.original`, source JAR hoặc plain với tên exec | Kiểm tra class layout và chạy consumer/app thực |
| Module core bị repackage | Plugin Boot inherited sai phạm vi | Chỉ activate Boot plugin trong module ứng dụng |

**Phương pháp debug:** lần lượt kiểm tra **GAV/classifier → file thực tế → archive layout → consumer compilation → executable startup → repository metadata**. Không sửa JDK chỉ vì sai classifier.

## 15. Quality gates cho cả hai artifact

**Gate A — Library:** plain JAR tồn tại; `PublicGreeting.class` ở Java package root; consumer `javac -cp` biên dịch được; `ConsumerMain` in chính xác `CONSUMER=LIBRARY_OK`.

**Gate B — Executable:** exec JAR tồn tại; có `BOOT-INF/classes`, `BOOT-INF/lib` và Boot launcher; `java -jar` khởi động; HTTP `GET /greeting` trả 200 và body `LIBRARY_OK`.

**Gate C — Build lineage:** unit tests bắt buộc thực sự được phát hiện; cả hai được tạo từ cùng source commit/version; không task/goal nào ghi đè output; archive checksum và manifest được lưu nếu policy yêu cầu.

**Gate D — Publication:** ordinary JAR không classifier và exec JAR classified đã được publish theo policy; downstream consumer resolve lại từ repository và compile thành công; deployment chọn đúng exec artifact.

**Lệnh QA Maven cơ bản trên Linux/macOS:**

~~~bash
mvn clean verify
jar tf target/dual-artifact-demo-1.0.0.jar
jar tf target/dual-artifact-demo-1.0.0-exec.jar
mkdir -p target/consumer-classes
javac -cp target/dual-artifact-demo-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:target/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Lệnh QA Gradle cơ bản:**

~~~bash
./gradlew clean build
jar tf build/libs/dual-artifact-demo-1.0.0.jar
jar tf build/libs/dual-artifact-demo-1.0.0-exec.jar
mkdir -p build/consumer-classes
javac -cp build/libs/dual-artifact-demo-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:build/libs/dual-artifact-demo-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Ghi chú:** lệnh `jar tf` chỉ in danh sách, chưa tự assert các entries; trong CI phải viết kiểm tra exact names và dừng khi thiếu. Phép thử HTTP executable cần một process server riêng, timeout, cleanup và cổng không bị chiếm; ở phần demo bạn chạy trong terminal thứ nhất rồi `curl` ở terminal thứ hai.

Đừng coi `BUILD SUCCESS` đồng nghĩa hợp đồng library/executable đã đạt. Maven/Gradle chỉ bảo đảm goals/tasks được thực thi theo cấu hình hiện tại, không tự biết sản phẩm nào đáng lẽ là default library artifact.

## 16. Bài tập có đáp án

**Bài 1.** Tại sao một JAR trong `target` chứa `PublicGreeting.class` nhưng Maven consumer vẫn không compile được?

*Đáp án:* class có thể nằm trong `BOOT-INF/classes` của Boot executable; compiler tiêu chuẩn cần nó ở root package path của ordinary JAR.

**Bài 2.** Khi Maven starter parent đã cấu hình `repackage`, cần tạo một execution khác ID để thêm classifier `exec` không?

*Đáp án:* Không. Tùy biến execution cùng ID `repackage` để tránh chạy trùng.

**Bài 3.** Với `classifier=exec`, executable được publish từ Maven khi nào?

*Đáp án:* Nếu goal chạy và `attach=true` (mặc định), nó được attach và tham gia `install`/`deploy` khi các phase đó được gọi.

**Bài 4.** Tại sao file `.jar.original` không phải phương án thay thế cho main library artifact?

*Đáp án:* Nó chủ yếu là bản local trước repackage, không tự mang identity/classifier/publication của ordinary main library JAR.

**Bài 5.** Gradle Boot plugin mặc định có thể cho `jar` classifier `plain`. Muốn library không classifier và exec có classifier, cấu hình gì?

*Đáp án:* `jar.archiveClassifier=''` và `bootJar.archiveClassifier='exec'`.

**Bài 6.** Chạy `./gradlew build` tạo hai JAR có chứng minh Maven repository đã nhận cả hai không?

*Đáp án:* Không. Cần `maven-publish`, publication components.java và artifact bootJar, rồi kiểm tra `publishToMavenLocal` hoặc remote repository thực tế.

**Bài 7.** Class API đã compile từ ordinary JAR nhưng JVM chạy exec báo lỗi classpath. Có liên quan classifier không?

*Đáp án:* Có thể, nhưng phải kiểm tra executable packaging, manifest, nested dependencies, runtime JDK và config; consumer test chỉ chứng minh ordinary JAR.

**Bài 8.** Một project giữ hai JAR trong cùng module có tự giảm dependency Spring Web cho consumers không?

*Đáp án:* Không. Metadata dependency vẫn thuộc module. Tách core/app giúp tách dependency/API contract rõ hơn.

## 17. Checklist cuối

- [ ] Tên và hợp đồng **library artifact** đã được thống nhất.
- [ ] Tên và hợp đồng **executable artifact** đã được thống nhất.
- [ ] Ordinary JAR chứa class ở root package path.
- [ ] Executable JAR chứa Boot loader, `BOOT-INF/classes`, `BOOT-INF/lib`.
- [ ] Maven starter parent: chỉnh execution ID `repackage` dùng classifier `exec`.
- [ ] Maven không dùng starter parent: pin plugin version, bind goal vào `package`, classifier `exec`.
- [ ] Không có secondary source artifact cùng classifier làm repackage chọn nhầm.
- [ ] `attach` đúng policy publish.
- [ ] Gradle `jar` được giữ và output không classifier; `bootJar` có classifier `exec`.
- [ ] Gradle `maven-publish` công bố Java component và exec artifact nếu cần cả hai.
- [ ] Consumer thực sự compile/chạy bằng ordinary JAR.
- [ ] App thực sự chạy `java -jar` và HTTP smoke test thành công.
- [ ] Hai output đến từ cùng commit/version, không ghi đè.
- [ ] Xem xét tách `core`/`app` nếu có nhiều consumers hoặc dependency coupling lớn.
- [ ] Kiểm tra local/remote repository sau publish, không chỉ `target`/`build/libs`.

**Kết luận:** **đừng dùng Spring Boot executable JAR như một library JAR**. Khi dự án phải cho ra cả hai, Maven dùng `repackage` với classifier `exec` và Gradle dùng `jar`/`bootJar` với classifiers khác nhau; cả hai cần publication rõ ràng và hai loại test riêng biệt.

## 18. Tài liệu chính thức

1. [Spring Boot Maven Plugin — Packaging Executable Archives; Custom Classifier](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
2. [Spring Boot Maven Plugin — Repackage Parameters: classifier, attach, layout](https://docs.spring.io/spring-boot/maven-plugin/packaging.html#spring-boot:repackage)
3. [Spring Boot Gradle Plugin — Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
4. [Spring Boot Gradle Plugin — Publishing Your Application](https://docs.spring.io/spring-boot/gradle-plugin/publishing.html)
5. [Spring Boot Executable JAR Format — Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
6. [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
7. [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
8. [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
9. [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
10. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
