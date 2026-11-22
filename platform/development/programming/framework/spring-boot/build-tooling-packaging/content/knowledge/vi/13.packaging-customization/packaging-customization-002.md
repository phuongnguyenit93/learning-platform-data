# Bổ sung hoặc loại trừ thư viện trong cấu hình repackage và bootJar

## 1. Mục tiêu và ngữ cảnh

Một ứng dụng Spring Boot được build bằng Maven hoặc Gradle có thể đóng gói thành **executable JAR** chứa mã ứng dụng và các thư viện cần thiết để chạy bằng `java -jar`. Khi có thêm JDBC driver, JSON module hoặc thư viện phục vụ riêng môi trường phát triển, bạn phải quyết định **artifact nào thực sự cần nằm trong JAR phát hành**, chứ không chỉ làm cho source code biên dịch được.

Hai tác vụ trung tâm:

- **Maven**: goal `spring-boot:repackage` của `spring-boot-maven-plugin` lấy JAR/WAR do lifecycle tạo ra và đóng gói lại với launcher cùng các dependencies thích hợp.
- **Gradle**: task `bootJar` của `org.springframework.boot` Gradle plugin tạo executable JAR; tập thư viện được đóng gói phụ thuộc vào **classpath của task**.

Sau bài học, bạn có thể:

1. Phân biệt dependency **khai báo**, dependency **được resolve trong classpath**, và dependency **thực tế nằm trong executable JAR**.
2. Bổ sung thư viện đúng scope trong Maven/Gradle, tránh nhầm `test` hoặc `compileOnly` với thư viện chạy thật.
3. Loại một artifact khỏi Maven `repackage` bằng `<excludes>`, hiểu `<excludeGroupIds>` và sự khác nhau với exclusions ở cấp dependency.
4. Điều chỉnh tập thư viện đóng gói của Gradle `bootJar`, biết khi nào dùng `runtimeOnly`, `developmentOnly`, dependency exclusion hay task-specific classpath.
5. Kiểm tra `BOOT-INF/lib/` trong artifact, chạy smoke test, đọc dependency tree và nhận ra lỗi runtime sau khi loại bỏ thư viện.
6. Giữ đồng nhất local/CI, tránh sản sinh artifact thiếu dependency hoặc đưa thư viện phát triển/secret vào bản production.

**Ví dụ xuyên suốt:** Spring Boot `3.3.5`, Java `17`, một ứng dụng chỉ dùng `spring-boot-starter` và thư viện `com.h2database:h2` để **minh họa việc có/không có một runtime JAR**. H2 ở đây *không được dùng làm database thực*, không mở kết nối và không cần JDBC starter. Phiên bản Spring Boot chỉ phục vụ minh họa; hãy sử dụng phiên bản dự án thật và ma trận hỗ trợ Maven/Gradle/JDK của nó.

## 2. Cấu trúc executable JAR và ba lớp quyết định

Spring Boot executable JAR thông dụng có dạng:

~~~text
packaging-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...  (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/                          (class và resource của ứng dụng)
    │   └── com/example/packaging/PackagingDemoApplication.class
    └── lib/                              (các dependency JAR được đóng gói)
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        ├── ...
        └── h2-*.jar                      (chỉ khi đã được bao gồm)
~~~

Trong layout JAR thông thường, `Main-Class` trong manifest trỏ tới **Spring Boot launcher**, còn `Start-Class` trỏ tới application main class. Launcher nạp nested JARs dưới `BOOT-INF/lib`; việc copy một thư viện tùy tiện vào `BOOT-INF/classes` hoặc sửa `Main-Class` thường không phải cách quản lý classpath đúng.

**Ba bước hoàn toàn khác nhau:**

| Tầng | Maven | Gradle | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| **Khai báo** | `<dependencies>`, `<scope>` | `dependencies { implementation / runtimeOnly / ... }` | Dự án yêu cầu artifact nào? |
| **Resolve** | Maven dependency mediation, scopes, BOM/dependencyManagement | Configurations, constraints, BOM, dependency resolution | Phiên bản nào thực tế nằm trên classpath nào? |
| **Đóng gói** | Spring Boot `repackage` với `includes/excludes` | `bootJar` với task `classpath` và quy tắc developmentOnly | Tệp JAR nào thực sự nằm trong executable archive? |

Đừng suy luận “dependency tree có module X” tức là “JAR phát hành nhất định có X”. Cấu hình đóng gói có thể loại module ấy. Ngược lại, không nhìn thấy module trong source code **không có nghĩa** nó vô dụng: runtime có thể dùng SPI, reflection, logging provider, driver hoặc autoconfiguration.

### Phân biệt executable JAR, plain JAR và WAR

- **Maven**: `package` tạo JAR nguồn; `repackage` tạo executable archive, bản JAR gốc thường được giữ ở tệp `.original`. Đừng dùng `.original` để kiểm tra `BOOT-INF/lib`.
- **Gradle**: `bootJar` tạo executable archive; task `jar` có thể tạo tệp `-plain.jar`. Plain JAR thường không chứa Spring Boot loader và nested dependencies đầy đủ.
- **WAR**: executable WAR có layout `WEB-INF/classes`, `WEB-INF/lib`, và có thể có `WEB-INF/lib-provided`. Quy tắc cho servlet container bên ngoài khác executable JAR; bài này tập trung vào **JAR**.

Bên cạnh đó, `layers.idx` và `classpath.idx` (nếu có) cung cấp metadata hỗ trợ đóng gói/launch, **không thay thế** việc chọn thư viện thực tế.

## 3. Chọn scope/configuration trước khi nghĩ đến exclude

### Maven

| Scope | Trong quá trình build | Đối với `repackage` Spring Boot JAR |
| --- | --- | --- |
| `compile` (mặc định) | Cần khi compile và runtime | Thường được bao gồm nếu không có filter loại |
| `runtime` | Không cần khi compile; cần lúc chạy | Thường được bao gồm |
| `test` | Phục vụ biên dịch/chạy test | Không thuộc runtime archive thông thường |
| `provided` | Có khi compile, được kỳ vọng có ở môi trường chạy bên ngoài | **Spring Boot repackage có thể bao gồm cả `provided`**, khác suy luận đơn giản từ Maven standard scopes; phải đọc tài liệu đúng version |
| `system` | Phụ thuộc tệp cục bộ do người dùng chỉ định | Mặc định `includeSystemScope=false` trong Spring Boot Maven plugin; tránh cho build tái lập |
| `optional` | Điều chỉnh mức độ lan truyền dependency tới consumers | Không nên xem optional là nút “loại khỏi Boot JAR”; hành vi đóng gói phụ thuộc plugin/version, cần kiểm tra artifact |

**Cẩn thận với `provided`:** Spring Boot Maven plugin `repackage` và `run` ở nhánh 3.3 có quy tắc bao gồm cả một số `provided` dependencies. Đừng ghi “provided = chắc chắn vắng mặt khỏi executable JAR”. Quy tắc cho **WAR và container ngoài** khác và phải được thiết kế theo mô hình triển khai thực tế.

### Gradle

| Configuration | Vai trò | Thông thường trong `bootJar`? |
| --- | --- | --- |
| `implementation` | Dùng compile và runtime | Có, qua runtime classpath |
| `runtimeOnly` | Dùng khi chạy nhưng không compile | Có, phù hợp JDBC driver dùng reflection/SPI |
| `compileOnly` | Chỉ cần khi compile | Không thuộc runtime classpath thông thường |
| `testImplementation` / `testRuntimeOnly` | Chỉ phục vụ test | Không thuộc runtime JAR ứng dụng |
| `developmentOnly` (Spring Boot plugin) | Công cụ chỉ phục vụ quá trình phát triển, ví dụ Devtools | **Mặc định bị loại khỏi executable JAR/WAR** |

Bảng mô tả hành vi mặc định trong Spring Boot Gradle plugin với Java/JVM project. Cấu hình tùy biến `bootJar.classpath`, `runtimeClasspath` hoặc source sets có thể thay đổi kết quả.

**Nguyên tắc chọn giải pháp:**

- Thư viện cần để ứng dụng chạy: thêm bằng `runtime` (Maven) hoặc `runtimeOnly` (Gradle), hay `compile/implementation` nếu mã Java gọi trực tiếp API.
- Thư viện chỉ dùng trong test: `test` / `testImplementation`, không cố dùng exclude ở bước packaging.
- Thư viện chỉ dùng lúc phát triển: cân nhắc `spring-boot-devtools` theo cấu hình phát triển và `developmentOnly` của Gradle.
- Thư viện chỉ cần trên một cấu hình deploy đặc biệt: chọn artifact/build variant riêng với kiểm thử, không tạo sự khác biệt ngầm giữa local và production.

## 4. Ví dụ Java có thể kiểm tra thư viện được đóng gói

Ta dùng **một class Spring Boot hoàn chỉnh** để kiểm tra sự có mặt của `org.h2.Driver` bằng reflection. Vì mã không import trực tiếp class H2, nó có thể compile khi H2 được khai báo ở runtime scope và cũng chạy được khi H2 bị loại khỏi archive. Đây là phép thử **quan sát classpath**, không phải kiểm thử JDBC.

Tạo file **`src/main/java/com/example/packaging/PackagingDemoApplication.java`**:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingDemoApplication {

    public static void main(String[] args) {
        System.out.println("PACKAGED_H2=" + h2Present());
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    private static boolean h2Present() {
        try {
            Class.forName("org.h2.Driver");
            return true;
        }
        catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
~~~

**Giải thích:**

1. `@SpringBootApplication` là cấu hình Boot, và `main` là điểm khởi động Java hợp lệ.
2. `Class.forName("org.h2.Driver")` tìm class theo tên tại **runtime**, nên không cần import JAR H2 khi compile.
3. Nếu class có mặt và có thể nạp được, chương trình in `PACKAGED_H2=true`; khi class không nằm trong runtime classpath, nó in `PACKAGED_H2=false`.
4. Cả hai trường hợp sau đó đều gọi `SpringApplication.run`; vì không có JDBC starter nên ví dụ không tạo kết nối H2.
5. Trong môi trường thật, lỗi `ClassNotFoundException` cũng có thể bắt nguồn từ vấn đề classloader; kiểm tra archive + runtime như mục 10 mới đủ bằng chứng.

**Dòng marker kỳ vọng khi H2 có trong executable archive:**

~~~text
PACKAGED_H2=true
~~~

**Dòng marker kỳ vọng sau khi loại H2 và chạy JAR được build lại:**

~~~text
PACKAGED_H2=false
~~~

Spring Boot có thể in thêm banner và log với thời gian/PID thay đổi. Chỉ hai dòng marker được chỉ định là output ổn định của phần mã kiểm tra.

## 5. Maven: baseline có một runtime dependency được đưa vào JAR

### 5.1. POM đầy đủ dùng cho bài thực hành

File **`pom.xml`** cho dự án Maven độc lập, với Maven Wrapper phù hợp đã được thiết lập trong repository:

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
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

Spring Boot Starter Parent quản lý các dependency versions, trong đó có H2 version tương thích với BOM của bản Boot đã chọn. **Không cần tự gắn version H2** vào POM ví dụ. Nếu project thật chỉ import Spring Boot BOM mà không kế thừa Parent, cần cấu hình compiler/plugin executions phù hợp: BOM import không tự mang toàn bộ plugin management và repackage execution của Parent.

Khi kế thừa `spring-boot-starter-parent`, chỉ cần khai báo Spring Boot Maven plugin trong `<plugins>` vì Parent đã cấu hình execution `repackage` thích hợp. Đừng vô tình khai báo hai execution `repackage` làm goal chạy lặp.

### 5.2. Build và kiểm tra baseline

Linux/macOS (ở project root):

~~~bash
./mvnw --version
./mvnw clean package
./mvnw dependency:tree -Dincludes=com.h2database:h2
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-'
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean package
.\mvnw.cmd dependency:tree -Dincludes=com.h2database:h2
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\target\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Sau `package`, Maven tạo executable JAR `target/packaging-demo-0.0.1-SNAPSHOT.jar`; file gốc `.original` (nếu có) **không phải** file để chạy. Lệnh `jar tf` phải hiển thị entry dạng `BOOT-INF/lib/h2-<phiên-bản>.jar`; chính tên version do BOM quản lý nên không ghi cố định trong output kỳ vọng.

Trong output của `java -jar`, marker mong đợi là `PACKAGED_H2=true`. Dòng `dependency:tree` chứng minh H2 được resolve cho Maven project, còn `jar tf` chứng minh H2 **thực sự đã được đóng gói**. Đây là hai phép đo khác nhau, cần giữ cả hai khi đánh giá tùy biến.

## 6. Maven: loại đúng một thư viện khỏi `repackage`

Để loại **chính H2 JAR** khỏi executable archive, vẫn giữ dependency `com.h2database:h2` trong `<dependencies>` rồi thay khai báo plugin trong `pom.xml` bằng:

~~~xml
<!-- Trích đoạn thuộc <build><plugins> của pom.xml hiện có -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

**Đây là fragment để thay phần plugin trước đó, không phải POM mới.** Trong `spring-boot-maven-plugin`, `<excludes>` chứa các `<exclude>` xác định **module bằng groupId + artifactId**, có thể chỉ định thêm classifier nếu cần. Cách này cho phép H2 vẫn xuất hiện trong dependency graph nhưng bị loại khỏi tập JAR của Boot archive.

Chạy lại `clean package`:

~~~bash
./mvnw clean package
./mvnw dependency:tree -Dincludes=com.h2database:h2
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-' || echo 'H2 NOT PACKAGED'
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Trong PowerShell:

~~~powershell
.\mvnw.cmd clean package
.\mvnw.cmd dependency:tree -Dincludes=com.h2database:h2
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\target\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Kết quả kỳ vọng là `dependency:tree` **vẫn hiển thị H2**, trong khi `jar tf` **không có entry H2** và `java -jar` in `PACKAGED_H2=false`. Với PowerShell, `Select-String` không tìm thấy kết quả sẽ không in dòng tương ứng; không xem sự im lặng đó như bằng chứng nếu lệnh `jar` trước đó bị lỗi. Luôn kiểm tra mã thoát hoặc chạy lại riêng lệnh `jar tf` khi cần.

**Ý nghĩa chính:** cấu hình `repackage.excludes` không biến mất khai báo H2 trong POM, không làm compiler ngừng nhận dependency phù hợp, và không thay đổi toàn bộ Maven resolution graph; nó điều chỉnh thành phần đóng gói/goal Boot có liên quan. Trong Spring Boot Maven Plugin, các exclude settings cũng có thể ảnh hưởng goal `spring-boot:run` theo hướng dẫn plugin; đừng coi `spring-boot:run` và `java -jar` luôn giống nhau nếu cấu hình build khác nhau.

### `excludeGroupIds`: loại cả nhóm artifact

Spring Boot Maven plugin còn hỗ trợ:

~~~xml
<configuration>
    <excludeGroupIds>com.example.legacy,com.example.diagnostics</excludeGroupIds>
</configuration>
~~~

Đây là **danh sách groupId**, không phải artifactId; sẽ loại mọi artifact có groupId khớp trong phạm vi repackage. **Chỉ dùng khi bạn đã kiểm tra đầy đủ nhóm**. Một groupId như `org.springframework` hoặc `com.fasterxml.jackson.core` có thể bao gồm thư viện cốt lõi; loại cả nhóm tùy tiện rất dễ làm ứng dụng không khởi động.

Khi cần loại đúng một artifact, `<excludes>` thường an toàn và dễ rà soát hơn `<excludeGroupIds>`. Nếu đã có cả hai, phải đọc effective plugin config để biết chính xác tập bị loại.

### `<includes>` không có nghĩa tự tải một thư viện mới

Plugin có cấu hình `<includes>` để giới hạn/cấp phép các dependency khi đóng gói. **Nó là bộ lọc đối với dependencies đang được project resolve**, không thay thế `<dependency>` trong POM và không thể tự thêm một tọa độ chưa có trong dependency graph.

Ví dụ fragment cú pháp:

~~~xml
<configuration>
    <includes>
        <include>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </include>
    </includes>
</configuration>
~~~

**Không áp dụng fragment trên cho ứng dụng mẫu bình thường**: dùng allowlist mà chỉ có H2 có thể loại các Boot starter dependencies khác cần để chạy. Chỉ sử dụng `includes` khi bạn thực sự muốn kiểm soát tất cả dependencies eligible, đã lập danh sách đầy đủ và chạy smoke tests trên JAR cuối. Nếu mục tiêu là **thêm** một thư viện, cách chuẩn là thêm `<dependency>` với scope đúng.

## 7. Maven: không nhầm exclude trong dependency với exclude trong repackage

Có hai loại exclude khác nhau về tác dụng:

**Cấp dependency — ngăn kéo một transitive module:**

~~~xml
<!-- Trích đoạn ví dụ: loại transitive artifact từ nhánh dependency này -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>customer-client</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>legacy-transport</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Các tọa độ `com.example:customer-client:1.2.0` và `legacy-transport` chỉ **minh họa cú pháp**, không phải thư viện public được bảo đảm tồn tại. `<exclusions>` ở cấp dependency điều chỉnh **dependency graph của nhánh đó**. Nếu dependency khác vẫn kéo cùng module, nó có thể xuất hiện qua đường khác.

**Cấp Spring Boot plugin — lọc file đóng gói:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

Cơ chế plugin chỉ kiểm soát tập artifact mà `repackage` sẽ đặt vào executable JAR, không sửa dependency declarations của project. Nếu bạn **không còn dùng thư viện ở bất kỳ cấu hình nào**, giải pháp sạch là xóa dependency khai báo hoặc loại transitive ở đúng nhánh, thay vì giữ nó trong dependency tree rồi âm thầm ẩn khỏi archive.

### Các tùy chọn Maven cần biết

- `excludeDevtools`: Spring Boot Maven plugin mặc định loại `spring-boot-devtools` khỏi executable archive.
- `excludeDockerCompose`: với phiên bản hỗ trợ, loại `spring-boot-docker-compose` theo mặc định.
- `includeSystemScope`: mặc định `false`; tránh bật chỉ để gói một file JAR nằm trên máy cá nhân, vì sẽ làm build khó tái lập.
- `requiresUnpack`: dùng với thư viện cần được bung ra thành file khi chạy; **không phải** cách thêm/loại dependency.
- `includeTools`: điều khiển jar tools dùng cho layer operations ở các version hỗ trợ; **không phải** công tắc loại những thư viện ứng dụng tùy ý.
- `classifier`/ `attach`: điều khiển artifact được tạo và đính kèm để install/deploy; **không quyết định** module nào bị loại khỏi classpath.

Tránh bật `includeSystemScope` để “sửa” lỗi `ClassNotFoundException` do thiếu thư viện trong production. Một JAR hệ thống nằm ngoài repository chính thức cần được quản lý nguồn gốc/version/checksum hoặc publish nội bộ theo chính sách.

## 8. Gradle: thêm thư viện qua `runtimeOnly` và xác minh `bootJar`

File **`settings.gradle`** (Groovy DSL):

~~~groovy
rootProject.name = 'packaging-demo'
~~~

File **`build.gradle`** đầy đủ, dùng cùng class Java mục 4:

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
    implementation 'org.springframework.boot:spring-boot-starter'
    runtimeOnly 'com.h2database:h2'
}

springBoot {
    mainClass = 'com.example.packaging.PackagingDemoApplication'
}
~~~

`runtimeOnly 'com.h2database:h2'` đưa H2 vào **runtimeClasspath**, không vào compileClasspath của source main. Vì code dùng reflection, project vẫn compile được. `bootJar` mặc định đóng gói main output cùng runtime libraries phù hợp, nên H2 phải xuất hiện ở `BOOT-INF/lib/`.

**Nếu dự án dùng `dependencyResolutionManagement` với `RepositoriesMode.FAIL_ON_PROJECT_REPOS` ở settings, phải bỏ block `repositories` trong `build.gradle` và đặt Maven Central/mirror tại settings.** Cấu hình repo khác phạm vi cấu hình thư viện trong bài.

### Chạy Gradle trên Linux/macOS

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew clean bootJar
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-'
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

### Chạy Gradle trên Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency h2 --configuration runtimeClasspath
.\gradlew.bat clean bootJar
jar tf .\build\libs\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\build\libs\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

**Kết quả mong đợi:** `runtimeClasspath` chứa H2, `jar tf` tìm thấy `BOOT-INF/lib/h2-...`, và `java -jar` in `PACKAGED_H2=true`.

Nếu không có H2 trong dependency graph, xem xem `runtimeOnly` có nằm đúng module hay bị excludes/constraints ảnh hưởng. Nếu có trong graph nhưng vắng khỏi archive, xem `bootJar.classpath`, `developmentOnly` hoặc những filter packaging đã được áp dụng. Một module có thể nằm trong **testRuntimeClasspath** mà không có trong **runtimeClasspath** của main.

## 9. Gradle: loại một JAR khỏi đúng task `bootJar`

Khác Maven `repackage.excludes`, Spring Boot Gradle plugin chủ yếu dựa vào **classpath của task `bootJar`**. Nếu muốn loại H2 **chỉ khỏi executable archive**, nhưng vẫn giữ `runtimeOnly` để thử nghiệm/kiểm chứng khác biệt giữa build classpath và packaged classpath, có thể lọc file trong classpath của `BootJar`.

### Groovy DSL

**Thêm** block sau vào `build.gradle` ở mục 8, không xóa `runtimeOnly 'com.h2database:h2'`:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    classpath = classpath.filter { file ->
        !(file.name ==~ /h2-[0-9].*\.jar/)
    }
}
~~~

Đây là ví dụ filter theo **tên file JAR** dành riêng cho bài thực hành. Gradle `FileCollection.filter` tạo tập file đã lọc, còn `BootJar.classpath` quyết định tập nested libraries đưa vào archive. Khi set lại classpath, phải giữ các file/class directories khác; đoạn trên chỉ bỏ file có tên khớp `h2-<version>.jar`.

**Quan trọng về độ bền:** lọc theo filename là kỹ thuật task-level, không phải cách ổn định nhất để quản lý dependency theo group/module. Nếu file H2 được đổi tên hoặc có custom classifier, biểu thức có thể không còn khớp. Với dự án thật, ưu tiên xóa dependency không cần, dùng Gradle dependency exclusions theo tọa độ khi thực sự muốn bỏ khỏi **runtime resolution graph**, hoặc dùng mô hình packaging có kiểm thử rõ. Nếu bắt buộc lọc đúng archive, hãy thêm kiểm tra `BOOT-INF/lib` trong CI.

### Kotlin DSL tương đương

**Thêm** vào `build.gradle.kts` trong dự án dùng Kotlin DSL (và nhớ import `BootJar` đầu file):

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    classpath = classpath.filter { file ->
        !Regex("""h2-[0-9].*\.jar""").matches(file.name)
    }
}
~~~

Ở Kotlin DSL, phần `import` cần đặt ở đầu file. `classpath.filter` vẫn giữ directories của main output cùng các JAR khác. **Chọn Groovy hoặc Kotlin, không chèn cả hai vào cùng file**.

**Không dùng** `tasks.named("bootJar") { exclude("BOOT-INF/lib/h2-*.jar") }` như một công thức thay thế mặc định: `exclude` ở cấp archive copy specification có ngữ nghĩa khác với loại module khỏi dependency graph/classpath. Có thể sinh kết quả khác dự kiến do Spring Boot tasks thêm nested libraries theo quy trình riêng; nên kiểm soát `BootJar.classpath` và xác minh archive.

### Verify sau khi lọc

~~~bash
./gradlew clean bootJar
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-' || echo 'H2 NOT PACKAGED'
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Kết quả: `dependencyInsight` có thể **vẫn thấy H2 trong runtimeClasspath** nhưng `BOOT-INF/lib` không còn H2 và app in:

~~~text
PACKAGED_H2=false
~~~

Đây là trạng thái **cố ý khác biệt** để minh họa. Trong production, nếu ứng dụng thực sự gọi driver H2 thì việc loại H2 khỏi `bootJar` sẽ làm ứng dụng fail khi truy cập database, dù `bootRun` có thể vẫn chạy được. **Không đánh đồng một test build xanh với executable JAR chạy đúng chức năng.**

### Gradle: loại ở tầng dependency graph khi phù hợp hơn

Nếu ứng dụng không còn cần H2 trong bất kỳ runtime nào, cách sạch nhất là **xóa** khai báo `runtimeOnly 'com.h2database:h2'`. Nếu chỉ muốn loại *transitive dependency* của một thư viện khác, Gradle cho phép exclusion trên dependency declaration:

~~~groovy
dependencies {
    implementation('com.example:client-sdk:1.2.0') {
        exclude group: 'com.example', module: 'legacy-transport'
    }
}
~~~

Đây là **cú pháp minh họa**, không phải tọa độ artifact public được bảo đảm tồn tại. Exclusion chỉ tác động lên nhánh dependency tương ứng; nếu một đường phụ thuộc khác vẫn cần artifact đó, artifact có thể vẫn được chọn. Kiểm tra bằng `dependencyInsight` thay vì giả định `exclude` luôn xóa được module khỏi toàn bộ graph.

**Khác biệt cần nhớ:** Gradle dependency exclusion thay đổi resolution graph của classpath liên quan, có thể ảnh hưởng `bootRun`/test/runtime khác. `bootJar.classpath` filter chỉ tác động task đóng gói nếu không có custom wiring khác. Hai cơ chế **không thay thế nhau**.

## 10. Gradle: `developmentOnly` và tùy chọn thêm thư viện ở mức đóng gói

Spring Boot Gradle plugin tạo `developmentOnly` dành cho những dependency phát triển, điển hình là Devtools:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Theo mặc định, các dependencies khai báo ở `developmentOnly` **không nằm trong executable JAR/WAR**. Đây là giải pháp phù hợp để loại công cụ development mà **không phải tự viết filter thủ công** trong `bootJar`.

Nếu chủ ý muốn đưa `developmentOnly` vào một **archive dành cho mục đích đặc biệt**, plugin cho phép thêm classpath configuration ấy vào task. Ví dụ Groovy DSL:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    classpath configurations.developmentOnly
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    classpath(configurations["developmentOnly"])
}
~~~

**Không sử dụng cấu hình này cho production chỉ vì “thiếu devtools”**: Devtools là công cụ phát triển, thường không nên được đóng gói. Cú pháp `classpath(...)` ở đây **thêm** file vào classpath task; khác với phép gán `classpath = ...` dùng để **thay** tập classpath. Nếu project có nội dung `bootJar.classpath` tùy biến từ trước, hãy bảo toàn các library cốt lõi.

Khi thật sự cần thêm **một thư viện chỉ có ở archive**, task cũng có thể bổ sung tệp JAR từ một configuration tùy chọn. Tuy nhiên, nó sẽ không tự cập nhật compile/test classpath hay nguồn gốc dependency; nếu package mới gọi library trong application code, phải đảm bảo compile/runtime design nhất quán. **Ưu tiên khai báo `implementation` hoặc `runtimeOnly` trong project** để cả IDE, test, dependency graph và CI có thể quan sát được phụ thuộc đó.

### `requiresUnpack` giải quyết trường hợp khác

Một số thư viện không chạy được khi chỉ tồn tại dưới dạng nested JAR. Spring Boot Gradle hỗ trợ:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

Cấu hình này chỉ đánh dấu thư viện cần **unpack sang tệp tạm khi ứng dụng chạy**, **không phải** lệnh thêm module mới và không phải loại dependency. Nếu thư viện chưa nằm trên classpath task, `requiresUnpack` không khiến nó xuất hiện.

## 11. Maven và Gradle: bảng đối chiếu “bổ sung/loại trừ” theo mục tiêu

| Mục tiêu | Maven | Gradle | Hệ quả cần kiểm tra |
| --- | --- | --- | --- |
| Thêm thư viện cần ở runtime | `<dependency><scope>runtime</scope></dependency>` | `runtimeOnly("group:module")` | Runtime classpath và nested JAR |
| Thêm thư viện cần compile + runtime | `compile` hoặc scope mặc định | `implementation("group:module")` | Compile, runtime và test |
| Test library không đưa vào executable JAR | `test` | `testImplementation` | Có trong testClasspath nhưng vắng archive |
| Thư viện chỉ dùng development | Spring Boot plugin có cơ chế loại Devtools; cân nhắc Maven scopes/optional phù hợp | `developmentOnly` | Không leak vào artifact phát hành |
| Loại 1 module **chỉ ở bước đóng gói** | `spring-boot-maven-plugin` `<excludes>` | Điều chỉnh `BootJar.classpath` có kiểm chứng | Dependency graph có thể vẫn thấy module |
| Loại 1 transitive module khỏi graph | `<exclusions>` trên dependency | `exclude(group, module)` trên dependency hoặc policy được kiểm soát | Ảnh hưởng tới resolution classpath |
| Loại cả group khi repackage | `<excludeGroupIds>` | Không có tùy chọn cùng nghĩa trực tiếp trong `bootJar`; phải thiết kế theo Gradle configuration/classpath | Nguy cơ loại cả nhóm thư viện cần thiết |
| Thêm dev-only vào archive đặc biệt | Cần explicit plugin config và phân tích bảo mật | `bootJar { classpath(configurations.developmentOnly) }` | Thường không nên cho production |
| Thư viện nested cần unpack | `<requiresUnpack>` | `requiresUnpack(...)` | Artifact vẫn được đóng gói nhưng được bung khi chạy |

Không lấy cú pháp Maven `<excludes>` chuyển thành `bootJar { excludes ... }` mà không kiểm chứng Gradle API: mỗi plugin có **mô hình cấu hình khác**.

## 12. Đọc dependency graph để phân biệt thiếu dependency với thiếu file trong JAR

### Maven: xác định tọa độ và nhánh phụ thuộc

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=com.h2database:h2
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

`dependency:tree` phản ánh các dependencies do Maven resolve và chọn theo mediation rules. `effective-pom` cho thấy POM sau khi merge parent/profile/plugin management; rất hữu ích khi nghi một profile hoặc parent đang áp dụng `repackage.excludes` ngoài ý muốn.

**Không sửa file `effective-pom.xml`** để sửa cấu hình: phải sửa `pom.xml` nguồn. Nếu project multi-module, chạy lệnh trong đúng module đóng gói; một module library có dependency graph khác module app.

### Gradle: xem configuration đúng với runtime

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

`runtimeClasspath` là classpath của main source set, còn `testRuntimeClasspath` dùng cho test. `dependencyInsight` giải thích lý do chọn version/nhánh kéo dependency vào. Nếu H2 vẫn nằm trong `runtimeClasspath` nhưng bị lọc khỏi `BootJar.classpath`, lệnh này **không thể tự chứng minh H2 nằm trong JAR**. Bắt buộc kết hợp với kiểm tra archive.

**Về Gradle dependency locking:** lockfile có thể cố định các resolved versions để tăng tính tái lập, nhưng **không tự bảo đảm tập file trong `bootJar`** nếu bạn có task-specific filters/custom classpath. Version catalog/BOM cũng chỉ mô tả phiên bản/constraints, không thay thế kiểm tra file đầu ra.

## 13. Kiểm tra executable JAR bằng công cụ JDK, không phụ thuộc IDE

### 13.1. Liệt kê các nested JAR

Maven:

~~~bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/lib/'
~~~

Gradle:

~~~bash
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/lib/'
~~~

Trong PowerShell:

~~~powershell
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^BOOT-INF/lib/'
~~~

Với Gradle, thay path bằng `.\build\libs\...`. Nếu có yêu cầu phiên bản cụ thể, chỉ liệt kê tên JAR chưa chứng minh đúng BOM: cần đối chiếu tên/version thực tế được resolve.

### 13.2. Kiểm tra manifest

Spring Boot executable JAR 3.3 thông thường có entry như:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingDemoApplication
~~~

`Main-Class` là Spring Boot launcher, không phải lớp main của project. `Start-Class` cho biết application main class. Một archive có đủ thư viện nhưng `Start-Class` sai vẫn có thể không chạy được; vì thế **kiểm tra launcher và dependency** là hai bước khác nhau.

### 13.3. So sánh trước/sau mà không lẫn artifact cũ

1. Chạy **`clean package`** hoặc **`clean bootJar`** trong đúng module.
2. Ghi tên và kích thước JAR cần kiểm tra; nếu thư mục chứa nhiều JAR, xác định đúng file executable, không chọn bừa file `-plain.jar` hoặc `.original`.
3. Liệt kê `BOOT-INF/lib/`, lưu danh sách trước và sau; khi chỉ loại H2, **những thư viện Spring Boot cần thiết không nên biến mất**.
4. Chạy `java -jar` với đúng JAR mới tạo. Trong ví dụ H2, kiểm tra marker `PACKAGED_H2=true/false`.
5. Chạy smoke/integration tests sử dụng các tính năng phụ thuộc vào những library còn lại. Một JAR có thể khởi động nhưng lỗi khi đến nhánh dùng thư viện bị loại.
6. Đối chiếu kết quả trên CI và môi trường runtime được hỗ trợ. Đừng lấy việc “`bootRun` local vẫn chạy” làm bằng chứng JAR phát hành đã có đúng thư viện.

Khi cần kiểm tra checksum để bảo đảm artifact đúng file đã chạy/deploy, dùng `sha256sum` trên Linux hoặc `Get-FileHash` ở Windows. Checksum khác nhau có thể do nhiều nguyên nhân (thời gian build, metadata, tập dependency); để chứng minh **đã loại thư viện nào**, danh sách nested JAR và dependency graph vẫn là bằng chứng trực tiếp hơn.

## 14. Rủi ro và tiêu chí quyết định có nên loại thư viện

### 14.1. Classpath trong unit tests có thể rộng hơn artifact runtime

Một test có thể pass vì dependency có trong `testRuntimeClasspath`, trong Maven test classpath, hoặc khi chạy `bootRun` trên máy cá nhân. Nhưng executable JAR sau đóng gói lại thiếu một nested library, dẫn tới:

- `ClassNotFoundException` / `NoClassDefFoundError` khi nạp class.
- `ServiceConfigurationError` khi SPI/provider không tìm thấy.
- `NoSuchMethodError` hoặc lỗi liên kết nếu vô tình đóng gói một bộ phiên bản không tương thích.
- Lỗi kết nối JDBC hoặc parser/driver ở một chức năng ít chạy, dù app khởi động vẫn thành công.
- Lỗi autoconfiguration vì một thư viện biến mất hoặc dependency mới làm một condition được kích hoạt khác trước.

**Smoke test phải chạy từ `java -jar` của artifact cuối**, không chỉ test JVM có classpath IDE/Gradle/Maven đầy đủ.

### 14.2. Chọn cách loại trừ đúng nguyên nhân

Nếu dependency **không còn dùng**: xóa khỏi `dependencies`/POM trước. Nếu dependency bị kéo vào **transitively** nhưng không cần: dùng exclusion ở nhánh được xác nhận, rồi kiểm tra đường phụ thuộc khác. Nếu dependency chỉ không phù hợp với **artifact** nhưng vẫn cần ở công cụ/test runtime khác: dùng plugin/task packaging-specific có test đi kèm.

Không loại `spring-boot-loader`, SLF4J provider, Spring Framework core, Jackson modules, JDBC driver hoặc security library chỉ để giảm kích thước JAR nếu application vẫn cần chúng. Lợi ích vài MB không bù được nguy cơ mất chức năng và khó chẩn đoán lỗi production.

### 14.3. Bảo mật và provenance

Loại một JAR khỏi executable archive có thể làm thay đổi SBOM và phạm vi phát hiện CVE **trong artifact ấy**, nhưng không tự xóa lỗ hổng khỏi source tree, dependency graph, test tools, container base image hoặc các artifact khác. Nếu dependency vẫn được tải trong build, tổ chức có thể vẫn cần quản trị nó theo chính sách.

Đọc advisory, đánh giá package thực sự trong runtime, cập nhật phiên bản theo Spring Boot BOM/phạm vi tương thích khi có bản vá. Đừng dùng exclude để che cảnh báo scanner mà không đánh giá đường gọi của ứng dụng và tác động đến chức năng.

## 15. CI: biến điều kiện đóng gói thành một kiểm tra tự động

Nếu quyết định **có chủ đích loại H2** khỏi archive ví dụ, CI có thể xác minh rằng H2 **không có trong executable JAR**, và các thư viện Spring Boot bắt buộc **vẫn có**.

Ví dụ đoạn script **Linux/bash** chạy sau Maven `package`:

~~~bash
set -eu
jar_path="target/packaging-demo-0.0.1-SNAPSHOT.jar"

jar tf "$jar_path" > jar-entries.txt

if grep -q '^BOOT-INF/lib/h2-' jar-entries.txt; then
    echo "Unexpected H2 JAR in executable archive" >&2
    exit 1
fi

grep -q '^BOOT-INF/lib/spring-boot-' jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class$' jar-entries.txt

echo "Packaging contents verified"
~~~

Với Gradle, đổi path thành `build/libs/packaging-demo-0.0.1-SNAPSHOT.jar`. Script giả định đang ở đúng working directory và `jar` từ JDK đã cài. Các lệnh `grep -q` trả exit code khác 0 nếu thiếu nội dung mong đợi, nhờ `set -e` khiến job fail. **Dòng in chính xác của script khi pass**:

~~~text
Packaging contents verified
~~~

Nếu mục tiêu là **bắt buộc bao gồm H2**, đảo phép kiểm tra:

~~~bash
jar tf "$jar_path" | grep -q '^BOOT-INF/lib/h2-'
~~~

**Lưu ý pipeline:** với `set -o pipefail`, `jar tf | grep -q` đôi khi sinh trạng thái không mong muốn nếu phía `jar` gặp broken pipe sau khi grep đã tìm thấy dữ liệu; mẫu lưu file `jar-entries.txt` trước rồi grep sẽ đơn giản và ổn định hơn. Có thể thay bằng script Python/Java đọc archive nếu tổ chức có yêu cầu phức tạp hơn.

Trong CI Windows PowerShell, dùng `jar tf` để lấy danh sách và `Select-String` để đối chiếu, kết hợp kiểm tra kết quả/exit code; không sao chép nguyên script `set -eu` của bash sang PowerShell.

CI cần thêm **test thật của ứng dụng** và smoke test chạy đúng artifact. Một kiểm tra `BOOT-INF/lib` pass chỉ xác nhận danh sách file, không tự bảo đảm application context và chức năng hoạt động đầy đủ.

## 16. Những hiểu lầm và lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| Đã thêm H2 trong POM nhưng `java -jar` báo thiếu driver | Scope không phù hợp, plugin `repackage.excludes`, chạy nhầm file gốc hoặc version/module sai | Xem `dependency:tree`, `BOOT-INF/lib/`, effective POM và path JAR |
| Đã thêm `runtimeOnly` trong Gradle nhưng `bootJar` không có file | Runtime graph bị exclude, task classpath filter, `developmentOnly` hoặc build sai module | `dependencies --configuration runtimeClasspath`, `dependencyInsight`, `jar tf` |
| Maven `dependency:tree` vẫn thấy module vừa exclude | `repackage.excludes` lọc đóng gói, không loại khỏi graph | Đây là hành vi đúng; đối chiếu trực tiếp nested JAR |
| Gradle `bootRun` hoạt động còn `java -jar` lỗi | Task `bootJar` có classpath filter mà `bootRun` vẫn dùng runtimeClasspath đầy đủ | So sánh `bootJar.classpath`, `runtimeClasspath` và file JAR |
| Loại group rộng, Boot JAR không khởi động | `excludeGroupIds` loại cả module cần thiết | Quay về exclude theo groupId/artifactId hẹp, kiểm tra lại toàn bộ nested JAR |
| Bật `<includes>` chỉ cho một module rồi app lỗi | Allowlist vô tình loại nhiều thư viện cốt lõi | Bỏ allowlist hoặc bổ sung đầy đủ sau khi kiểm thử |
| `testImplementation` có H2 nhưng JAR không có | Dependency chỉ được dùng trong test configuration | Chuyển sang `runtimeOnly` nếu runtime app thật sự cần |
| Đóng gói `spring-boot-devtools` vào production | Đưa Devtools vào classpath đóng gói không có chủ đích | Dùng `developmentOnly` (Gradle), giữ exclude mặc định/kiểm tra repackage (Maven) |
| `NoClassDefFoundError` chỉ khi chạm API ít dùng | Dependency cần thiết đã bị loại, nhưng smoke test chưa phủ được nhánh đó | Bổ sung integration test nghiệp vụ, kiểm tra runtime graph |
| JAR nhỏ hơn nhưng scanner vẫn cảnh báo | Dependency còn trong image khác, test/build graph hoặc scanner quét nguồn khác | Xác định chính xác artifact được scan và phạm vi CVE |
| Chạy nhầm `-plain.jar` hoặc `.original` | Archive này không phải executable archive cuối | Tìm JAR Boot đúng classifier và xem manifest/BOOT-INF |
| Lệnh `spring-boot:repackage` riêng thất bại | Goal cần JAR nguồn của phase `package` trước | Dùng `clean package` khi execution gắn lifecycle hoặc `package spring-boot:repackage` nếu cấu hình cần |
| Build local xanh, CI không resolve được library | Khác repository, mirror, credential, proxy hoặc Gradle/Maven cache | Cố định Wrapper/JDK/BOM, kiểm tra dependency graph trên CI sạch |

## 17. Quy trình quyết định và checklist sau thay đổi

1. **Nêu mục tiêu:** bạn thêm thư viện vì ứng dụng cần lúc chạy, hay loại library khỏi artifact vì không cần production?
2. **Ghi baseline:** Spring Boot version, JDK, Maven/Gradle Wrapper, dependency tree/runtimeClasspath, danh sách nested JAR và kết quả smoke test.
3. **Chọn tầng thay đổi nhỏ nhất:** dependency declaration/scope cho việc thêm; exclusion trong graph nếu thực sự không cần; plugin/task packaging-specific khi chỉ muốn thay archive.
4. **Đặt version theo BOM** khi có thể, tránh tạo sự không tương thích trong cả họ thư viện; ghi rõ lý do nếu phải override.
5. **Build sạch:** Maven `clean package` hoặc Gradle `clean bootJar` bằng Wrapper tại đúng module.
6. **Read artifact:** mở manifest, liệt kê `BOOT-INF/lib`, kiểm tra đúng artifact/classifier.
7. **Run artifact:** `java -jar`, quan sát marker/health/nhánh nghiệp vụ phụ thuộc thư viện.
8. **Run tests:** unit tests, integration tests, runtime smoke test trên JDK/môi trường đã cam kết.
9. **Automate assertion:** CI kiểm tra module cần có/không được có và báo FAIL nếu không đúng.
10. **Review security:** SBOM, dependency graph, nguồn tải, CVE, license và rủi ro bỏ thư viện.
11. **Document và rollback:** ghi thay đổi trong PR, có thể quay về dependency/packaging trước đó nếu tính năng hoặc compatibility fail.

Bạn hoàn thành bài khi có thể chỉ ra **vì sao `mvn dependency:tree` hoặc `gradle dependencies` chưa đủ để kết luận một thư viện có trong executable JAR**, tự bổ sung hoặc loại H2 trong ví dụ, sau đó chứng minh kết quả bằng **`BOOT-INF/lib` và `java -jar`**.

## Tài liệu chính thức

- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot – Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/index.html)
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven – Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Gradle – Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Excluding Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html)
