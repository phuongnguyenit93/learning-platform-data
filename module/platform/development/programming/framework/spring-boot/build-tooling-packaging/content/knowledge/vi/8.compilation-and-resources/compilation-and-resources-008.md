# Xử lý tài nguyên trùng tên và quy tắc đưa tệp vào archive

Khi Maven hoặc Gradle biên dịch một ứng dụng Spring Boot, các tệp trong `src/main/resources` được đưa vào **classpath của ứng dụng** rồi có thể xuất hiện bên trong executable JAR/WAR. Nếu nhiều nguồn cùng tạo một đường dẫn đích — chẳng hạn hai tệp đều trở thành `config/messages.properties` — kết quả có thể là **build thất bại, một tệp bị bỏ qua, bị ghi đè, hoặc archive chứa entry trùng nhau**. Cần hiểu xung đột phát sinh ở bước nào trước khi chọn cách xử lý.

Bài học tập trung vào **quy tắc đưa resource vào archive**, xử lý **tên/đường dẫn trùng**, cấu hình **include/exclude**, khác biệt **Gradle và Maven**, phân biệt **trùng entry trong một archive với trùng resource ở các dependency JAR khác nhau**, và cách xác minh file thực tế đã đóng gói. Các ví dụ dùng Java 17, Gradle 8.x và Maven 3.x; khi có plugin Spring Boot, ví dụ minh họa dòng 3.3.x. Những cú pháp liên quan hệ build phải đặt vào đúng DSL/POM của project.

## 1. Resource là gì, và “trùng tên” được xác định như thế nào?

Trong Java, **resource** là dữ liệu phục vụ lúc chạy như YAML, properties, JSON, template, HTML, CSS, hình ảnh, file mẫu và metadata. Build tool không biên dịch các tệp này thành `.class` như Java source; thông thường chúng được **sao chép hoặc xử lý** sang thư mục output.

Cấu trúc phổ biến:

```text
resource-demo/
├── build.gradle hoặc pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   └── ResourceDemoApplication.java
    │   └── resources/
    │       ├── application.yml
    │       ├── demo/message.txt
    │       ├── static/logo.svg
    │       └── templates/page.html
    └── test/
        ├── java/com/example/demo/
        │   └── ResourceDemoApplicationTest.java
        └── resources/
            └── demo/message.txt
```

**Đường dẫn tương đối trong classpath** mới là tiêu chí chính để nhận diện xung đột, không chỉ tên basename. Hai file `images/header.svg` và `icons/header.svg` có cùng tên cuối nhưng **không** trùng classpath path. Ngược lại, file ở hai root khác nhau nhưng cùng đường dẫn `demo/message.txt` sẽ va chạm **nếu được đưa về cùng một output root**.

Ví dụ:

```text
src/main/resources/demo/message.txt       -> demo/message.txt
src/shared/resources/demo/message.txt     -> demo/message.txt  (TRÙNG đường dẫn đích)

src/main/resources/icons/header.svg       -> icons/header.svg
src/shared/resources/images/header.svg    -> images/header.svg (KHÔNG trùng)
```

Các đường dẫn trên được chuẩn hóa theo cấu trúc archive, thường dùng dấu `/`. Không phụ thuộc vào khác biệt chữ hoa/chữ thường giữa hệ điều hành: `Logo.svg` và `logo.svg` có thể gây hành vi khác trên filesystem không phân biệt chữ hoa/chữ thường hoặc khi được giải nén ở hệ khác. Dùng cách đặt tên nhất quán và không tạo collision sau khi chuẩn hóa.

Phân loại xung đột:

| Tình huống | Ví dụ | Giai đoạn cần xử lý |
| --- | --- | --- |
| Hai source resource root sinh cùng path | `main/resources/demo/x.txt` và `shared/resources/demo/x.txt` | `processResources` của Gradle / `process-resources` của Maven |
| Thêm file vào JAR bằng một archive copy rule trùng file đã có | `bootJar.from(...)` tạo lại `BOOT-INF/classes/demo/x.txt` | Task đóng gói archive |
| Hai dependency JAR cùng chứa `META-INF/services/...` | `library-a.jar` và `library-b.jar` | Classpath/runtime hoặc bước tạo *shaded* JAR, nếu có |
| Main resource và test resource trùng path | `src/main/resources/demo/x.txt` và `src/test/resources/demo/x.txt` | Test classpath, không nhất thiết là xung đột archive production |
| Một file cấu hình trong JAR và một file ngoài ứng dụng | `application.yml` nội bộ và ngoài thư mục config | Cơ chế ưu tiên cấu hình Spring Boot, không phải trùng archive entry |

**Điểm quan trọng:** “cùng tên” giữa hai dependency JAR **khác nhau** không tự tạo một duplicate entry trong JAR ngoài nếu ứng dụng dùng Spring Boot nested JAR. Cũng không đồng nghĩa các file tự được merge.

## 2. Tài nguyên đi qua những bước nào trước khi vào JAR/WAR?

Sơ đồ tổng quát của project Java/Spring Boot:

```text
src/main/java  ------ compileJava / compile -------> .class
                                                    \
src/main/resources -- processResources -------------> output main
                                                      \
                                                       +--> jar/bootJar/bootWar
                                                      /     \
runtime dependencies --------------------------------+       +--> artifact deploy

src/test/java + src/test/resources
            ---- compileTest / processTestResources --> output test
                                                         |
                                                         +--> test (không mặc định vào JAR production)
```

| Thành phần | Gradle thông dụng | Maven thông dụng | Trong executable Spring Boot JAR |
| --- | --- | --- | --- |
| Class ứng dụng | `build/classes/java/main` | `target/classes` | `BOOT-INF/classes/.../*.class` |
| Resource chính | `build/resources/main` | `target/classes` | `BOOT-INF/classes/...` |
| Runtime dependency | Configuration `runtimeClasspath` | Dependency runtime/compile phù hợp | `BOOT-INF/lib/*.jar` |
| Class/resource kiểm thử | `build/classes/java/test` và `build/resources/test` | `target/test-classes` | **Không** mặc định đóng gói |

Trong executable WAR, class ứng dụng thường ở `WEB-INF/classes` và dependency ở `WEB-INF/lib` / `WEB-INF/lib-provided` tùy mô hình triển khai. Còn plain JAR do `jar` hoặc `maven-jar-plugin` tạo thường đặt class/resource ở **gốc JAR**, không phải `BOOT-INF/classes`.

**Các quy tắc đưa file vào artifact được áp dụng theo tầng:**

1. Build tool xác định **source roots** (root nào là main resource/test resource).
2. `include`/`exclude` và các bước copy/filter quyết định tài nguyên nào đi vào output.
3. Rules cho **đường dẫn đích**, rename, duplicate strategy quyết định cách xử lý cùng path.
4. Archive task chọn class/resource output cùng runtime dependencies để đóng gói.
5. Spring Boot launcher tìm tài nguyên theo **classpath lúc chạy**; các thư viện nằm trong nested JAR có path riêng bên trong.

Vì có nhiều tầng, bạn phải xác định file xuất hiện ở đâu: **source**, **output resources/classes**, **archive chính**, **dependency JAR**, hay **config bên ngoài**.

## 3. Gradle: quản lý resource ở `processResources`

Gradle Java plugin tạo source set `main` với `src/main/resources` theo quy ước. Task `processResources` (kiểu `ProcessResources`) dùng các quy tắc `CopySpec` để sao chép và có thể biến đổi resource vào `build/resources/main`.

### 3.1. Thêm resource root có chủ đích

Ví dụ `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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

sourceSets {
    main {
        resources {
            srcDir 'src/shared/resources'
        }
    }
}

tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    exclude '**/*.bak', 'draft/**'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **cấu hình hoàn chỉnh cho build file**, với Java main class cần được tạo như mục 6. `srcDir` bổ sung `src/shared/resources` vào main source set, trong khi `src/main/resources` tiếp tục là root mặc định. `exclude` trong `processResources` bỏ file backup và thư mục `draft` **ở bước xử lý resource**. Hai file thuộc các root khác nhau mà sau copy có **cùng đường dẫn đích** sẽ bị phát hiện vì `duplicatesStrategy = DuplicatesStrategy.FAIL`.

**Đừng sửa nhầm `sourceSets.main.resources.srcDirs` theo cách thay thế hết root mặc định** nếu bạn chỉ cần thêm một thư mục. `srcDir` bổ sung nguồn; cách gán lại toàn bộ danh sách có thể bỏ `src/main/resources` nếu không liệt kê nó.

### 3.2. Các giá trị `DuplicatesStrategy`

Gradle hỗ trợ các chiến lược sau cho một thao tác copy/archive:

| Giá trị | Khi phát hiện cùng path đích | Khi nào nên dùng |
| --- | --- | --- |
| `FAIL` | Ném `DuplicateFileCopyingException`, làm task thất bại | Khi duplicate là lỗi dữ liệu/build, phù hợp nguyên tắc phát hiện sớm |
| `EXCLUDE` | Giữ bản đã sao chép đầu tiên, bỏ các bản đến sau | Khi có thứ tự nguồn được kiểm soát và chấp nhận chính sách “first wins” |
| `INCLUDE` | Không ngăn duplicate; ZIP/JAR có thể có nhiều entry cùng path | Chỉ dùng nếu định dạng và consumer xử lý duplicate theo cách đã kiểm chứng |
| `WARN` | Như `INCLUDE` nhưng ghi cảnh báo | Khi cần quan sát, không phải giải pháp lâu dài cho bản deploy |
| `INHERIT` | Kế thừa từ copy spec cha | Giá trị mặc định của nhiều task/spec, không phải cách đặt ý nghĩa nghiệp vụ |

Ví dụ cấu hình:

```groovy
tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

Nếu lựa chọn `EXCLUDE`:

```groovy
tasks.named('processResources') {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
```

Hãy hiểu rõ: **`EXCLUDE` không “gộp hai file thành một”**. Nó bỏ file sau và giữ file được xử lý đầu tiên; thứ tự có thể thay đổi khi cấu hình source/copy spec đổi. Tránh dùng `EXCLUDE` để che xung đột quan trọng như hai file `application.yml` khác nội dung. `FAIL` thường giúp bạn sửa nguyên nhân ngay từ source root. Với `INCLUDE`/`WARN`, archive ZIP có thể chứa nhiều entry trùng tên và các công cụ đọc có thể chọn bản khác nhau; tính đúng đắn khi runtime **không được bảo đảm**.

### 3.3. Sửa tận nguồn xung đột

Giả sử:

```text
src/main/resources/demo/message.txt       chứa: from-main
src/shared/resources/demo/message.txt     chứa: from-shared
```

Sau khi thêm cả hai root và dùng `FAIL`, `./gradlew processResources` phải phát hiện đường dẫn `demo/message.txt` trùng (miễn là hai file thật sự có trong input của task). Cách sửa có thể là:

- Chọn **một file nguồn chính thức** rồi loại file còn lại khỏi source set.
- Đổi đường dẫn shared thành `demo/shared-message.txt` để cả hai có mục đích riêng.
- Chỉ khi có quyết định rõ ràng về quyền ưu tiên, định nghĩa copy/rename/filter path tường minh và kiểm tra kết quả.

Không sửa bằng cách “thử build nhiều lần xem file nào thắng”. Một bản build lặp lại khác thứ tự nguồn hoặc khác hệ điều hành có thể che giấu vấn đề.

### 3.4. Quy tắc `include` và `exclude`

Ví dụ chỉ giữ tài nguyên từ thư mục `reports`:

```groovy
tasks.named('processResources') {
    include 'reports/**'
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

**Chú ý:** khi dùng `include`, những file ngoài `reports/**` (kể cả `application.yml`, templates, static assets) có thể bị loại. Đó là **whitelist có phạm vi lớn**, không phù hợp nếu ứng dụng còn cần resource khác.

Phương án thường an toàn hơn là giữ mặc định và **exclude một số đường dẫn cụ thể**:

```groovy
tasks.named('processResources') {
    exclude 'draft/**', '**/*.bak', '**/*.tmp'
}
```

Pattern của copy spec khớp đường dẫn **tương đối từ resource root**; không viết `src/main/resources/draft/**` nếu mục tiêu cần loại `draft/**`. Thử với output thực tế vì một pattern quá rộng có thể loại cả tài nguyên dùng ở runtime.

**Đừng nhầm `.gitignore` với rule build.** `.gitignore` điều khiển Git theo dõi file, không phải bộ lọc đảm bảo file không bị đóng gói. Một tài nguyên đang tồn tại trong source root có thể được copy/đóng gói cho dù tên file xuất hiện trong `.gitignore`.

## 4. Gradle: phân biệt `processResources` với `bootJar`

Khi kết hợp Gradle Java và Spring Boot plugin:
- `processResources` tạo **output resource của source set main**.
- `bootJar` tập hợp class/resource main cùng runtime libraries để tạo executable Spring Boot JAR.
- `jar` tạo **plain JAR**, dùng rule và artifact riêng.
- `bootWar` tương tự cho WAR nếu có `war` plugin.

Ví dụ điều chỉnh **archive task** chỉ để không đưa các tệp backup vào executable JAR:

```groovy
tasks.named('bootJar') {
    duplicatesStrategy = DuplicatesStrategy.FAIL
    exclude '**/*.bak'
}
```

`duplicatesStrategy` ở đây chỉ kiểm soát **các path trùng khi task `bootJar` thêm entry**; nó **không xử lý** việc trùng resource đã bị mất hoặc bị ghi đè ở bước `processResources`. Ngược lại, nếu file bị loại ngay ở `processResources`, `bootJar` bình thường không thể lấy lại file ấy từ main resource output.

**Ưu tiên lọc tại source/processResources** đối với tài nguyên ứng dụng: nó giữ classpath chạy bằng `bootRun` và nội dung `bootJar` nhất quán. Chỉ dùng archive-level exclusion cho yêu cầu đóng gói thật sự đặc biệt, rồi xác minh archive đầu ra. Chỉ viết rule ở `tasks.named('jar')` không bảo đảm cùng rule được áp dụng cho `bootJar`; chúng là các task riêng.

Nếu bạn thêm file trực tiếp bằng `from(...)` trong `bootJar`, tài nguyên ấy có thể **bỏ qua `processResources`**. Khi đó cần xem path đã đặt trong archive và duplicate strategy ngay tại task archive. Tránh chép một file vào hai đường vào (vừa source resource, vừa `bootJar.from`), vì như vậy dễ tạo duplicate.

## 5. Maven: kiểm soát resource trước khi tạo JAR

Maven đưa resource chính vào `target/classes` thông qua Maven Resources Plugin, thông thường tại phase `process-resources`. File test đi qua `process-test-resources` vào `target/test-classes`. Các resource directory cấu hình trong `<build><resources>`, còn bộ lọc tên/đường dẫn dùng `<includes>` và `<excludes>`.

### 5.1. Ví dụ chỉ loại một số file trong Maven

Đoạn sau đặt **bên trong `<project>` của `pom.xml`**:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
            <excludes>
                <exclude>draft/**</exclude>
                <exclude>**/*.bak</exclude>
                <exclude>**/*.tmp</exclude>
            </excludes>
        </resource>
    </resources>
</build>
```

Khi viết hẳn `<resources>`, hãy giữ lại `src/main/resources` nếu dự án cần root mặc định. Nếu còn resource root thứ hai, khai báo thêm `<resource>` tương ứng.

Ví dụ dùng `include` có chủ đích:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <includes>
            <include>config/*.yml</include>
            <include>reports/**</include>
        </includes>
        <excludes>
            <exclude>reports/internal/**</exclude>
        </excludes>
    </resource>
</resources>
```

Đoạn này là **thay thế cho phần `<resources>`**, không chèn cạnh một khối resource trùng lặp nếu dự án không cần. Chỉ các path được `include` cho phép rồi không bị `exclude` mới được copy theo resource entry này. File như `static/index.html` không khớp có thể bị loại; phải rà soát đủ các asset runtime trước khi áp dụng whitelist.

### 5.2. Khi khai báo hai resource roots trùng đích

Ví dụ **cấu hình có nguy cơ xung đột**:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
    </resource>
    <resource>
        <directory>src/shared/resources</directory>
    </resource>
</resources>
```

Nếu cả hai root chứa `demo/message.txt`, chúng đều nhắm tới `target/classes/demo/message.txt`. Maven Resources Plugin có tham số `overwrite` liên quan việc ghi đè file output, nhưng **`overwrite=true/false` không phải bộ quy tắc tương đương `Gradle DuplicatesStrategy.FAIL/EXCLUDE/INCLUDE`**. Việc bản nào còn lại có thể phụ thuộc plugin version, thứ tự xử lý, timestamp và file đích còn tồn tại; tránh dựa vào hiệu ứng ghi đè ngầm.

Giải pháp đáng tin hơn:
1. Chỉ duy trì **một source chính thức** cho từng classpath path.
2. Sửa đường dẫn nguồn hoặc dùng `<targetPath>` có chủ đích để mỗi nhóm resource có prefix riêng.
3. Nếu cần hợp nhất dữ liệu, dùng một bước sinh resource **có quy tắc rõ ràng** trước khi `process-resources`, và kiểm tra file sinh.

Ví dụ giữ hai tệp tên `demo/message.txt` bằng cách chuyển resource shared vào prefix `shared`:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
    </resource>
    <resource>
        <directory>src/shared/resources</directory>
        <targetPath>shared</targetPath>
    </resource>
</resources>
```

Kết quả mong đợi ở output:

```text
target/classes/demo/message.txt
target/classes/shared/demo/message.txt
```

`targetPath` thay đổi **đường dẫn resource ở classpath và trong archive**, do đó đoạn code đọc file phải dùng path mới (`shared/demo/message.txt`). Khi dùng với cấu hình đa module, tránh một đường dẫn `targetPath` vô tình trùng với thư mục đã có ở main.

### 5.3. Include/exclude ở archive Maven

Maven thông thường tạo plain JAR bằng `maven-jar-plugin` từ `target/classes`. Có thể loại file **chỉ ở bước đóng gói JAR** bằng plugin này:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <configuration>
                <excludes>
                    <exclude>demo/local-only.txt</exclude>
                </excludes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn cấu hình plugin** để ghép vào `<build><plugins>` có sẵn; không tạo thêm `<build>` thứ hai. `maven-jar-plugin` nhìn đường dẫn **tương đối từ `target/classes`**, không phải `src/main/resources/demo/local-only.txt`. Nếu `spring-boot-maven-plugin` sau đó thực hiện `repackage` từ JAR này, file đã bị loại khỏi JAR đầu vào nên thông thường cũng không nằm trong `BOOT-INF/classes` của executable JAR.

Phân biệt `spring-boot-maven-plugin` có cấu hình `<excludes>` cho **dependency artifact** (theo group/artifact), không phải một cách tương đương để lọc tùy ý mọi resource path. Để bỏ resource đơn lẻ, ưu tiên `<resources>` hoặc cấu hình archive plugin phù hợp.

## 6. Ví dụ Java 17 chạy được: xác minh resource mà ứng dụng thực sự đọc

Ví dụ Gradle `build.gradle` ở mục 3.1 có dependency starter. Tạo hai file Java trong package `com.example.demo`.

**File `src/main/java/com/example/demo/ResourceDemoApplication.java`:**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}
```

**File `src/main/java/com/example/demo/ResourceProbe.java`:**

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceProbe {

    private ResourceProbe() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream in = ResourceProbe.class
                .getClassLoader()
                .getResourceAsStream("demo/message.txt")) {
            if (in == null) {
                throw new IOException("Missing demo/message.txt");
            }
            String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("resource=" + value.strip());
        }
    }
}
```

File `src/main/resources/demo/message.txt` chứa **đúng một dòng**:

```text
from-main
```

Khi `src/shared/resources/demo/message.txt` cũng chứa **đúng một dòng `from-shared`**, lệnh:

```bash
./gradlew clean processResources
```

sẽ phát hiện duplicate vì `duplicatesStrategy = DuplicatesStrategy.FAIL` đã được cấu hình ở mục 3.1. Bạn có thể **sửa file shared thành** `src/shared/resources/demo/shared-message.txt` để hai file có path khác nhau.

Sau khi đã sửa xung đột, chạy:

```bash
./gradlew clean classes
java -cp "build/classes/java/main:build/resources/main" com.example.demo.ResourceProbe
```

Kết quả stdout **do `ResourceProbe` in ra** (không tính log Gradle/JVM) là:

```text
resource=from-main
```

Trên Windows PowerShell, dùng:

```powershell
.\gradlew.bat clean classes
java -cp "build/classes/java/main;build/resources/main" com.example.demo.ResourceProbe
```

Dấu phân cách classpath là `:` trên Linux/macOS và `;` trên Windows. Lệnh `java -cp` dùng class và resource output có sẵn trong project; **không** cần đóng gói Boot JAR trước. `ResourceProbe` là chương trình Java thuần dùng API classpath. Chọn `getResourceAsStream` thay vì `new File("src/main/resources/demo/message.txt")` vì resource sau đóng gói có thể nằm bên trong JAR.

Nếu ứng dụng có nhiều `main` như ở ví dụ này, hãy chọn entry point deploy cho Boot archive trong `build.gradle`:

```groovy
springBoot {
    mainClass = 'com.example.demo.ResourceDemoApplication'
}
```

Sau đó:

```bash
./gradlew clean bootJar
```

Với `group/version` và root project name nhất quán (ví dụ `rootProject.name = 'resource-demo'`), artifact phổ biến là `build/libs/resource-demo-1.0.0.jar`. Đường dẫn thực tế có thể khác tùy cấu hình archive; hãy kiểm tra thư mục `build/libs`.

**Tại sao chạy `clean` trong bài thực hành?** Để tránh một file output cũ che lấp kết quả sau khi bạn đổi tên hoặc xóa source resource. Quy trình build bình thường không nhất thiết cần `clean` mỗi lần; trong bài kiểm tra trùng tên, nó hữu ích để có kết quả dễ tái lập.

## 7. Quy tắc kiểm tra file trong Spring Boot archive

### 7.1. Cấu trúc archive phổ biến

Với Spring Boot executable JAR:

```text
resource-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/ResourceDemoApplication.class
│   │   ├── demo/message.txt
│   │   ├── application.yml
│   │   ├── static/
│   │   └── templates/
│   └── lib/
│       ├── spring-boot-*.jar
│       └── ...
└── org/springframework/boot/loader/...
```

Đây là **sơ đồ minh họa**, không phải danh sách bắt buộc của mọi project. Spring Boot 3.x executable JAR đặt ứng dụng dưới `BOOT-INF/classes` và dependency JAR dưới `BOOT-INF/lib`. Plain JAR có bố cục khác; executable WAR thường là `WEB-INF/classes` và `WEB-INF/lib`.

Dùng JDK để liệt kê:

```bash
jar tf build/libs/resource-demo-1.0.0.jar
```

Tìm các entry có path:

```text
BOOT-INF/classes/demo/message.txt
BOOT-INF/classes/demo/shared-message.txt
BOOT-INF/classes/com/example/demo/ResourceDemoApplication.class
```

`jar tf` **chỉ liệt kê tên entry**, không hiển thị nội dung file. Nếu có công cụ `unzip`, có thể đọc trực tiếp nội dung:

```bash
unzip -p build/libs/resource-demo-1.0.0.jar BOOT-INF/classes/demo/message.txt
```

Nội dung dự kiến:

```text
from-main
```

Trên Windows, có thể dùng 7-Zip/ZIP viewer hoặc trích xuất file bằng `jar xf` vào một **thư mục tạm riêng** rồi xem `BOOT-INF/classes/demo/message.txt`. Đừng tự chỉnh nội dung trực tiếp bên trong archive build xong; hãy sửa source và chạy build lại.

### 7.2. Kiểm tra trùng tên entry trong cùng JAR

`jar tf` có thể hiện cùng một path nhiều lần nếu archive chứa duplicate entries. Bạn có thể nhận biết bằng cách xuất danh sách entry và đếm số lần path xuất hiện (một số công cụ ZIP có tùy chọn hiển thị duplicate rõ hơn). Nếu không có duplicate trong danh sách **JAR ngoài**, điều đó **không** đảm bảo không có cùng resource path trong nhiều dependency JAR **lồng nhau**.

Ví dụ:

```text
BOOT-INF/lib/library-a.jar -> META-INF/services/com.example.Plugin
BOOT-INF/lib/library-b.jar -> META-INF/services/com.example.Plugin
```

Hai file có cùng đường dẫn **bên trong hai nested JAR khác nhau**, nên không tự tạo hai entry `BOOT-INF/classes/META-INF/services/...` trong outer JAR. Chúng có thể được dùng cùng nhau bởi `ServiceLoader` khi classpath/runtime classloader hỗ trợ. Không tùy ý loại một bản chỉ vì thấy “trùng tên”.

### 7.3. Vì sao không nên giải quyết mọi xung đột bằng `EXCLUDE`?

Một quy tắc loại file ở `processResources` hoặc archive task có thể:
- loại nhầm `application.yml`, `META-INF/spring/...AutoConfiguration.imports` hoặc metadata quan trọng;
- làm mất template, CSS, hình ảnh ứng dụng cần lúc chạy;
- che một thay đổi từ dependency cập nhật;
- khiến `bootRun` (đọc output resource) và `java -jar` (đọc artifact) có dữ liệu khác nhau;
- để lại bản resource không mong muốn nếu thứ tự copy thay đổi.

Đặc biệt, `META-INF/services/*` là dạng metadata có thể **chủ đích xuất hiện trong nhiều dependency JAR**. Việc gộp service descriptors chỉ đặt ra khi bạn **flatten/shade** các JAR thành một archive; khi đó phải có chiến lược merge chuyên dụng và kiểm thử. Spring Boot nested executable JAR thông thường **không đồng nghĩa với shaded JAR**.

## 8. Test resources trùng với main resources

Ví dụ:

```text
src/main/resources/demo/message.txt  -> "from-main"
src/test/resources/demo/message.txt  -> "from-test"
```

Điều này có thể **có chủ ý**: test muốn đọc fixture thay cho resource mặc định. Maven/Gradle thường xây **main output** và **test output** ở các vị trí khác nhau; không vì trùng classpath-relative path giữa main/test mà `bootJar` buộc phải lỗi duplicate.

Tuy nhiên, khi test runtime classpath chứa cả test và main output, việc API `getResourceAsStream("demo/message.txt")` trả về **bản nào** có thể phụ thuộc thứ tự classpath. Đừng suy đoán “test luôn thắng” trong mọi build tool/IDE/custom configuration.

Nếu phải bảo đảm tính xác định của test:
- Dùng tên fixture rõ ràng `fixtures/message-test.txt` thay vì trùng đường dẫn main.
- Hoặc đưa path cụ thể vào code/test cấu hình và kiểm thử giá trị đã nạp.
- Với cấu hình Spring Boot profile, dùng file `application-test.yml` và kích hoạt profile `test` có chủ đích; **profile selection** khác với **thứ tự resource trên classpath**.

`src/test/resources` không vào executable production JAR **theo mặc định**, trừ khi bạn cấu hình copy/archive bổ sung hoặc vô tình cho test source set vào main.

## 9. Phân biệt trùng resource và ưu tiên cấu hình Spring Boot

Một tình huống dễ ngộ nhận:

```text
BOOT-INF/classes/application.yml        (cấu hình đóng gói)
./config/application.yml                 (cấu hình ngoài JAR)
```

Đây **không phải hai entry trùng trong archive**. Spring Boot có **cơ chế tìm kiếm và ưu tiên property sources/config data** riêng, bao gồm profile, vị trí cấu hình ngoài, biến môi trường, system properties và command-line arguments. Một giá trị bên ngoài có thể ghi đè giá trị đóng gói theo quy tắc Spring Boot, khác hoàn toàn `DuplicatesStrategy` của Gradle.

Ngược lại, nếu hai root main resource cùng tạo **`application.yml`** và copy stage xử lý không rõ ràng, đó là **duplicate path tại build time**. Phải sửa ở nguồn/build config trước khi tranh luận về property precedence lúc chạy.

Một chiến lược hợp lý:
- Đặt **cấu hình mặc định, không chứa bí mật** ở `src/main/resources/application.yml`.
- Đặt secret và thông số môi trường vào secret manager, environment variables hoặc config ngoài artifact.
- Không tạo nhiều bản `application.yml` ở các resource roots khác nhau chỉ để chọn bản “thắng” theo thứ tự copy.
- Kiểm thử giá trị hiệu lực trong môi trường dự kiến, vì build-time filtering và runtime property resolution là hai bước riêng.

## 10. Filtering và generated resources: cách tránh collision không rõ nguồn

### 10.1. Gradle `expand` và giữ nguyên file chưa lọc

Gradle có thể thay placeholder của resource text trong `processResources`:

```groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(buildVersion: project.version)
    }
}
```

File `src/main/resources/build-info.properties`:

```properties
build.version=${buildVersion}
```

Sau processing, với `project.version = '1.0.0'`, output dự kiến:

```properties
build.version=1.0.0
```

Đây là **biến đổi nội dung file**, không phải cách tự xử lý path trùng. Nếu còn một task khác sinh `build-info.properties` vào cùng output root, cần phân định một nguồn chính thức. Không đặt rule `expand` lên mọi file nhị phân vì file PNG/PDF/JAR có thể bị hỏng hoặc bị diễn giải sai.

### 10.2. Maven filtering

Maven Resources Plugin hỗ trợ `<filtering>true</filtering>` và các biến từ POM/properties/filter files. Nên áp dụng chỉ cho **tệp text cần lọc**, tránh áp dụng lên toàn bộ ảnh/binary.

Ví dụ chia hai nhóm trong `<build><resources>`:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>build-info.properties</exclude>
        </excludes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>build-info.properties</include>
        </includes>
    </resource>
</resources>
```

Cùng một source directory xuất hiện **hai lần** nhưng pattern được cấu hình **không giao nhau**, nên `build-info.properties` chỉ được copy trong nhóm filtering. Đây là cách tổ chức rõ khi cần lọc đúng một file text. Nếu để hai entry đều bao gồm `build-info.properties`, bạn lại tạo cùng một output path và kết quả có thể phụ thuộc quy tắc ghi đè.

Maven còn có `<nonFilteredFileExtensions>` để bảo vệ các extension nhị phân; việc lọc nhầm ảnh/PDF/JAR có thể phá dữ liệu. Xem file output sau process-resources để chắc giá trị được thay đúng.

### 10.3. Generated resources cần owner và thứ tự task rõ ràng

Một plugin/task sinh file `META-INF/build-info.properties`, còn file source cũng tạo đúng path đó, là một xung đột tương tự hai root. Cần chọn **ai sở hữu file cuối**, tránh vừa commit source vừa sinh đè lên cùng path.

Với Gradle, nếu một task sinh resource để `processResources` tiêu thụ, nối task thông qua provider/task dependency phù hợp và chỉ định một output directory riêng; tránh viết trực tiếp vào `src/main/resources` trong lúc build. Với Maven, cần gắn plugin generation vào phase trước `process-resources` hoặc đưa output vào resource root phù hợp, kiểm tra thứ tự plugin. Không chữa bằng xóa output thủ công trong từng lần build.

Ví dụ quy trình an toàn ở mức khái niệm:

```text
generateMetadata -> generated/resources/META-INF/build-info.properties
                                     |
                                     v
                      processResources (một nguồn duy nhất)
                                     |
                                     v
                         build/resources/main
                                     |
                                     v
                               bootJar/bootWar
```

Generated resource và file do con người quản lý nên có **đường dẫn và ownership rõ ràng** để tránh build tái lập ra kết quả khác nhau.

## 11. Quy tắc đưa file vào archive: những gì nên và không nên có

Một artifact ứng dụng triển khai thường cần:

| Tệp/loại dữ liệu | Đưa vào artifact? | Lý do |
| --- | --- | --- |
| `.class` từ `src/main/java` | Có | Chương trình chạy |
| `application.yml` mặc định | Có nếu cần và không chứa secret | Cấu hình baseline |
| `static/**`, `templates/**` | Có khi ứng dụng cần | Web asset và template |
| `META-INF/**` hợp lệ | Có khi tính năng/thư viện cần | Metadata, SPI, auto-configuration |
| Runtime dependencies | Có theo layout Spring Boot | Thư viện cần chạy |
| `src/test/java`, `src/test/resources` | Không, theo mặc định | Chỉ phục vụ test |
| Backup `*.bak`, file nháp, tài liệu nội bộ không cần chạy | Thường không | Rác trong artifact, tăng kích thước/rủi ro |
| Mật khẩu thật, private key và token trong resource source | Không | Không nhúng bí mật trong archive |
| Driver phụ thuộc runtime đúng scope | Có khi cần | Nếu thiếu có thể lỗi `ClassNotFoundException` |
| File config riêng cho môi trường deploy | Thường quản lý ngoài artifact | Dễ thay đổi mà không rebuild |

Đừng loại nguyên `META-INF/**` vì nghĩ đó là “metadata phụ”. Một số file trong đó cần cho Java `ServiceLoader`, logging, Spring Boot auto-configuration hoặc công cụ runtime. Tương tự, không xóa `BOOT-INF/lib` để giảm kích thước executable JAR rồi chờ `java -jar` tự tải dependency.

**Classpath của Boot executable JAR không phải chỉ là `BOOT-INF/classes`**; các dependency ở nested `BOOT-INF/lib/*.jar` vẫn được Boot loader sử dụng. Vì vậy, kiểm tra resource ở cả **ứng dụng** và **thư viện phụ thuộc** khi phát hiện hành vi runtime khó hiểu.

## 12. Quy trình điều tra lỗi duplicate hoặc thiếu resource

Một quy trình kiểm tra cho cả Gradle và Maven:

1. **Xác định path resource mà code tra cứu**, ví dụ `demo/message.txt` (không phải path filesystem nguồn).
2. **Liệt kê các source roots chính/test/generated** liên quan đến task; xem có bao nhiêu file tạo ra path này.
3. **Xem quy tắc include/exclude/rename/targetPath/filtering/duplicatesStrategy** trên đúng task hoặc resource entry.
4. **Chạy clean build một lần để chẩn đoán**, tránh nhìn nhầm output cũ.
5. **Xem output trước khi đóng gói**: `build/resources/main` hoặc `target/classes`.
6. **Xem đúng artifact được deploy**: `jar tf`, file trong `BOOT-INF/classes` hay `WEB-INF/classes`; phân biệt plain JAR và Boot JAR.
7. **Nếu resource nằm trong dependency**, kiểm tra dependency tree và nội dung nested JAR tương ứng; đừng chỉ tìm trong `BOOT-INF/classes`.
8. **Chạy artifact thật** trong môi trường đại diện và kiểm tra nội dung resource được nạp hoặc chức năng sử dụng resource.
9. **Bổ sung kiểm thử hồi quy** cho đường dẫn/giá trị quan trọng để thay đổi build về sau không đưa collision trở lại.

Lệnh tham khảo Gradle:

```bash
./gradlew clean processResources
./gradlew bootJar
./gradlew dependencies --configuration runtimeClasspath
jar tf build/libs/resource-demo-1.0.0.jar
```

Lệnh tương ứng Maven:

```bash
./mvnw clean process-resources
./mvnw package
./mvnw dependency:tree
jar tf target/resource-demo-1.0.0.jar
```

Nếu chưa có wrapper, dùng `gradle` hoặc `mvn` khi build tool được cài phù hợp. Với Gradle, tên output JAR phụ thuộc `project.name`, `version` và archive settings; với Maven, phụ thuộc `artifactId`, `version` và packaging. **Đừng sao chép nguyên tên ví dụ nếu project thực tế khác.**

Các nhóm lỗi thường gặp:

| Lỗi hoặc biểu hiện | Nguyên nhân thường gặp | Sửa tại đâu? |
| --- | --- | --- |
| Gradle báo `Entry ... is a duplicate` | Hai source/copy spec cùng path nhưng chưa có chiến lược hợp lệ | Kiểm tra `processResources` hoặc `bootJar`; đặt `FAIL` và sửa nguồn |
| `getResourceAsStream` trả `null` | File bị exclude, sai classpath path, hoặc chưa được copy | Kiểm tra output main/test và archive |
| Test đọc file khác production | Main/test trùng resource path và thứ tự classpath khác | Đặt fixture path riêng, xác minh classloader |
| File đã xóa khỏi source nhưng vẫn có trong JAR | Output cũ hoặc task/custom copy vẫn sinh file | Chạy `clean` để điều tra; tìm task/source thực |
| Tài nguyên ứng dụng bị “ghi đè” | Hai Maven resource roots cùng target path | Định nghĩa một nguồn hoặc `targetPath` riêng |
| JAR chứa hai entry cùng tên | CopySpec/`INCLUDE` hoặc archive injection trùng path | Loại hoặc đổi đường dẫn, dùng `FAIL` và kiểm tra lại |
| Không tìm thấy resource trong `BOOT-INF/classes` | Resource thuộc dependency JAR chứ không thuộc ứng dụng | Kiểm tra `BOOT-INF/lib` và classpath |
| `application.yml` có giá trị khác kỳ vọng | Có thể do runtime property precedence hoặc build-time filtering | Phân biệt cấu hình Spring và copy stage |
| Static resource bị 404 sau build | `include` quá hẹp hoặc `exclude` quá rộng | Mở archive và sửa resource patterns |
| Image/PDF bị lỗi sau packaging | Lọc text nhầm file binary | Tách filtering, bỏ lọc file nhị phân |
| Spring Boot mất auto-configuration hoặc SPI | Loại nhầm `META-INF/**` | Khôi phục metadata, kiểm tra các thư viện |
| Bản JAR dùng để deploy không trùng JAR vừa kiểm tra | Có plain JAR và executable JAR hoặc classifier khác | Xác định artifact cụ thể trong CI/CD |

## 13. Checklist trước khi hoàn tất cấu hình resource/packaging

- [ ] Mỗi resource **quan trọng** có một **đường dẫn classpath duy nhất** và một nguồn chịu trách nhiệm rõ ràng.
- [ ] Đã phân biệt main/test/generated resource và tránh dùng test fixture trong production archive.
- [ ] Với Gradle, biết `duplicatesStrategy` áp dụng cho **task nào**; ưu tiên `FAIL` để phát hiện va chạm, chỉ dùng `EXCLUDE` khi chọn first-wins có chủ đích.
- [ ] Với Maven, có `<resources>` đầy đủ, pattern `include/exclude` phù hợp, không dựa vào `overwrite` để thay thế chiến lược xử lý duplicate.
- [ ] Rule ở `processResources` và `bootJar` không vô tình mâu thuẫn; file runtime cần thiết nằm trong archive.
- [ ] Không gộp bừa `META-INF/services/**` hoặc xóa `META-INF/**`; nếu làm shaded JAR phải có quy tắc merge riêng.
- [ ] Filtering chỉ tác động file text thích hợp, không làm hỏng binary và không sinh hai file vào cùng output path.
- [ ] Đã kiểm tra **output resource trước archive** và **archive sau package**; biết `jar tf` chỉ liệt kê entry.
- [ ] Artifact chạy thật dùng được tài nguyên bằng đường dẫn **classpath**, không phụ thuộc vào `src/main/resources` còn tồn tại.
- [ ] Không đưa secret, file nháp, backup và dữ liệu kiểm thử vào production JAR; kết quả build có thể kiểm chứng lại.

**Nguyên tắc chốt:** xác định **đường dẫn đích** rồi giải quyết trùng lặp **ở giai đoạn sớm nhất có thể**. `include/exclude` quyết định **file nào được mang đi**; `duplicatesStrategy` của Gradle quyết định **phản ứng khi cùng path**; Maven cần nguồn và mapping output được thiết kế tường minh; archive task quyết định **cấu trúc JAR/WAR**; classpath runtime quyết định **resource nào được đọc**. Đọc output thật và chạy artifact thật là bước xác nhận cuối cùng.

## Tài liệu kỹ thuật

- [Gradle ProcessResources task](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html)
- [Gradle DuplicatesStrategy API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html)
- [Apache Maven Resources Plugin — Including and Excluding](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Apache Maven Resources Plugin — Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Spring Boot — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)