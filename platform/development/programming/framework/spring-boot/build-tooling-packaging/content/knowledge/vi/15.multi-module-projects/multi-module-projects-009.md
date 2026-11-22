# Xuất bản POM hoặc Gradle Module Metadata phản ánh đúng phụ thuộc

## 1. Bài toán của một dự án Spring Boot đa mô-đun

Trong một repository Spring Boot có nhiều module, nhóm phát triển thường dùng **project dependency** để cho ứng dụng phụ thuộc vào thư viện nội bộ. Nhưng khi phát hành thư viện ra Maven repository, người sử dụng bên ngoài **không còn đọc được build.gradle hay pom.xml nguồn trong repository gốc**. Họ chỉ nhận các file artifact, ví dụ:

~~~text
com.example:core:1.0.0
├── core-1.0.0.jar
├── core-1.0.0.pom
└── core-1.0.0.module    # khi Gradle xuất Gradle Module Metadata
~~~

**JAR** chứa mã bytecode/resources. **POM** và **Gradle Module Metadata (GMM)** cho Maven/Gradle biết module đó cần những dependency nào, version nào, vào compile hay runtime classpath, và trong trường hợp Gradle còn có nhiều biến thể/attributes.

Một thư viện có thể chạy đúng trong multi-project build nhưng **sai metadata sau khi publish**. Hậu quả:

- Consumer biên dịch lỗi do thiếu class nằm trong **public API** của thư viện.
- Consumer biên dịch được nhưng runtime lỗi do thiếu **implementation dependency** hoặc JDBC driver.
- Thư viện test bị xuất nhầm vào ứng dụng production.
- Maven consumer và Gradle consumer resolve dependency graph khác nhau.
- File POM khai báo một **parent POM/BOM không có trong repository**.
- Pipeline publish một **Spring Boot executable JAR** thay cho library JAR chuẩn nên consumer không tìm thấy class.

**Mục tiêu:** xuất bản **plain Java library JAR** cùng metadata mô tả đúng API, implementation, runtime và version; phân biệt việc này với đóng gói **Spring Boot executable app**. Bài minh họa cả Gradle Java Library + maven-publish lẫn Maven multi-module, đồng thời kiểm chứng bằng một consumer độc lập.

**Phiên bản mẫu:** Java 17, Spring Boot 3.3.5, Gradle 8.5, Maven 3.9.x, thư viện phiên bản 1.0.0. Các version này được cố định để ví dụ có thể tái lập; không đại diện cho bản mới nhất.

## 2. Phân biệt JAR, Maven POM và Gradle Module Metadata

### 2.1. Library JAR so với Spring Boot executable JAR

Library JAR thông thường có các class ở đường dẫn Java classpath:

~~~text
core-1.0.0.jar
└── com/example/core/CatalogFormatter.class
~~~

Nó không tự đóng toàn bộ Guava, Commons Lang và JDBC driver ở bên trong. **Consumer phải nhận dependency graph transitive từ metadata**.

Spring Boot executable JAR thường có cấu trúc:

~~~text
app-1.0.0.jar
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/app/CatalogApplication.class
    └── lib/...
~~~

JAR thứ hai phù hợp để chạy bằng **java -jar**. Nhưng class app đặt dưới **BOOT-INF/classes**, không ở classpath root của library JAR. **Không lấy Boot JAR làm dependency compile của module khác.** Trong kiến trúc bài này, **core xuất bản thư viện**, còn **app chỉ đóng gói để triển khai**.

### 2.2. Maven POM và dependency scopes

Maven POM là file XML mô tả module theo **groupId:artifactId:version** cùng dependencies, parent, dependencyManagement và các thông tin liên quan. Một POM có thể khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
        <version>33.3.1-jre</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đây là **một fragment**, không phải POM đầy đủ. Maven có những scope quan trọng:

| Scope Maven | Khi dùng module làm dependency |
| --- | --- |
| **compile** | Dùng lúc compile và runtime; có tính transitive. |
| **runtime** | Không bắt buộc lúc compile nhưng dùng runtime; có tính transitive tương ứng. |
| **provided** | Cần lúc compile/test, được JDK hoặc runtime container cung cấp; không kéo vào runtime dependency thông thường của consumer. |
| **test** | Dành cho test của module; không truyền thành dependency sản phẩm của consumer. |
| **import** | Chỉ trong dependencyManagement với type pom để nhập BOM; không phải một runtime JAR. |

POM thuần không có khái niệm **apiElements** và **runtimeElements** đầy đủ như Gradle. Cùng một dependency compile trong Maven có thể là chi tiết triển khai nội bộ, nhưng Maven không có cấu hình **implementation** tách public API giống Gradle Java Library.

### 2.3. Gradle Module Metadata và variants

**Gradle Module Metadata** là file **.module** dạng JSON. Nó chứa mô tả variants với **attributes, capabilities, dependencies, dependency constraints, artifacts** cùng phiên bản module.

Hình dung một Java library:

~~~text
core-1.0.0.module
├── apiElements
│   ├── usage = java-api
│   ├── artifact = core-1.0.0.jar
│   └── dependencies cần cho compiler của consumer
└── runtimeElements
    ├── usage = java-runtime
    ├── artifact = core-1.0.0.jar
    └── dependencies cần để chạy thư viện
~~~

Đây là sơ đồ **logic**, không phải toàn bộ JSON literal. Consumer Gradle dùng các attributes để chọn biến thể thích hợp. Cách này diễn đạt ranh giới compile/runtime chính xác hơn một POM tổng quát.

**Gradle maven-publish** thường công bố **POM và .module song song** cùng library JAR. Maven dùng POM, còn Gradle có thể ưu tiên .module khi repository và metadata sources cho phép. Việc có .module không làm mất khả năng dùng POM của Maven.

## 3. Mẫu phụ thuộc đúng cần được xuất bản

Ta xây **core** có ba nhu cầu khác nhau:

1. **Commons Lang** chứa kiểu **Pair<String,String>** xuất hiện trong method public. Consumer phải thấy Commons Lang khi biên dịch. Gradle khai báo **api**.
2. **Guava** chứa **CharMatcher**, chỉ dùng bên trong thân method; consumer không cần import Guava khi compile. Gradle khai báo **implementation**. Nhưng runtime vẫn phải có Guava.
3. **H2 JDBC driver** chỉ cần lúc chạy phương thức gọi **java.sql.DriverManager**, không cần import trực tiếp class H2 trong source. Gradle khai báo **runtimeOnly**.
4. **JUnit Jupiter** chỉ để kiểm thử thư viện. Gradle khai báo **testImplementation**; Maven khai báo **scope test**.

Bảng hợp đồng của **Gradle java-library**:

| Dependency trực tiếp | Cấu hình core | API/compile của consumer | Runtime của consumer |
| --- | --- | --- | --- |
| commons-lang3 3.14.0 | **api** | Có | Có |
| guava 33.3.1-jre | **implementation** | Không được core xuất như API | Có |
| h2 2.3.232 | **runtimeOnly** | Không | Có |
| junit-jupiter 5.11.3 | **testImplementation** | Không | Không |
| junit-platform-launcher 1.11.3 | **testRuntimeOnly** | Không | Không |

**Chú ý:** Chữ “Không” nghĩa là configuration này **không cấp** dependency cho classpath đó; không phủ nhận khả năng thư viện tình cờ xuất hiện qua một dependency khác. Đừng suy luận từ graph đã bị ảnh hưởng bởi nhiều đường transitive rằng core công bố sai.

### 3.1. Vì sao public ABI quyết định api?

**ABI (Application Binary Interface)** bao gồm những kiểu mà compiler của consumer cần hiểu khi gọi phương thức public/protected, dùng superclass/interface, public field hoặc annotation public. Nếu public method trả về **Pair**, mà Commons Lang chỉ khai báo implementation, core tự compile được nhưng consumer không có type Pair trên compile classpath theo hợp đồng.

Ngược lại, Guava CharMatcher chỉ trong thân phương thức. Khai báo nó bằng **api** làm lộ chi tiết triển khai, tăng coupling và có thể khiến consumer dựa vào thư viện transitive một cách vô tình.

### 3.2. Vì sao runtime dependency vẫn phải publish?

**Ẩn Guava khỏi API compile** không có nghĩa **loại Guava khỏi runtime**. Khi core thực thi CharMatcher, class vẫn phải có mặt. Tương tự, JDBC URL **jdbc:h2:mem:** cần H2 driver được nạp khi chạy. POM/GMM phải công bố runtime dependencies dù compiler của consumer không import các class đó.

## 4. Cấu trúc hai module mẫu

~~~text
publisher/
├── settings.gradle           # phương án Gradle
├── pom.xml                   # phương án Maven
├── core/
│   ├── build.gradle          # Gradle hoặc pom.xml Maven
│   └── src/
│       ├── main/java/com/example/core/CatalogFormatter.java
│       └── test/java/com/example/core/CatalogFormatterTest.java
└── app/
    ├── build.gradle          # Gradle hoặc pom.xml Maven
    └── src/main/java/com/example/app/CatalogApplication.java
~~~

**core** là module thư viện được publish tại **com.example:core:1.0.0**. **app** là Spring Boot executable app, phụ thuộc core. Khi thực hành, chọn **Gradle hoặc Maven** và tạo bộ file build tương ứng; không cần duy trì đồng thời hai hệ thống build.

## 5. Ba file Java 17 hoàn chỉnh cho cả Maven và Gradle

### 5.1. core/CatalogFormatter.java

Tệp **core/src/main/java/com/example/core/CatalogFormatter.java**:

~~~java
package com.example.core;

import com.google.common.base.CharMatcher;
import org.apache.commons.lang3.tuple.Pair;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Locale;

public final class CatalogFormatter {
    private CatalogFormatter() {
    }

    public static Pair<String, String> describe(String raw) {
        String normalized = CharMatcher.whitespace()
                .trimFrom(raw)
                .toUpperCase(Locale.ROOT);
        return Pair.of("normalized", normalized);
    }

    public static boolean canOpenEmbeddedDb() throws SQLException {
        try (Connection connection =
                DriverManager.getConnection("jdbc:h2:mem:catalog")) {
            return !connection.isClosed();
        }
    }
}
~~~

**Đây là file Java 17 hoàn chỉnh.** Pair thuộc public method signature; CharMatcher nằm trong thân method; java.sql.* thuộc JDK, còn implementation JDBC driver H2 được tìm khi chạy qua service provider.

Database **H2 in-memory** không cần DB server, phù hợp cho bài tập metadata. Mục đích không phải cung cấp mẫu truy cập database production hay định nghĩa thư viện database công cộng nên luôn ép mọi consumer dùng H2; trong thực tế ranh giới driver có thể do ứng dụng quyết định.

### 5.2. core/CatalogFormatterTest.java

Tệp **core/src/test/java/com/example/core/CatalogFormatterTest.java**:

~~~java
package com.example.core;

import org.apache.commons.lang3.tuple.Pair;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogFormatterTest {
    @Test
    void normalizesText() {
        assertEquals(Pair.of("normalized", "JAVA"),
                CatalogFormatter.describe("  java  "));
    }

    @Test
    void loadsRuntimeDriver() throws Exception {
        assertTrue(CatalogFormatter.canOpenEmbeddedDb());
    }
}
~~~

Hai test xác minh thuật toán và việc H2 driver xuất hiện trên **test runtime classpath**, qua runtimeOnly/runtime scope. **JUnit không phải** dependency production của library.

### 5.3. app/CatalogApplication.java

Tệp **app/src/main/java/com/example/app/CatalogApplication.java**:

~~~java
package com.example.app;

import com.example.core.CatalogFormatter;
import org.apache.commons.lang3.tuple.Pair;
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
    CommandLineRunner runCatalog() {
        return args -> {
            Pair<String, String> result =
                    CatalogFormatter.describe("  gradle  ");
            System.out.println(result.getLeft() + "=" + result.getRight());
            System.out.println("H2=" +
                    CatalogFormatter.canOpenEmbeddedDb());
        };
    }
}
~~~

App cố ý **import Pair trực tiếp** để chứng minh Commons Lang cần nằm trên compile API của core. App **không import Guava hoặc org.h2.Driver**, nhưng chúng cần khi thực thi core.

Với graph đúng, chương trình in **hai dòng xác định từ mã của chúng ta**:

~~~text
normalized=GRADLE
H2=true
~~~

Log Spring Boot/Maven/Gradle có thể xuất hiện thêm; không được coi đoạn trên là toàn bộ terminal output.

## 6. Gradle: java-library + maven-publish

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'publisher'
include 'core', 'app'
~~~

Include giúp Gradle quản lý subproject. Nó **không tự publish các subproject**. Muốn upload artifact cần cấu hình publication và đích repository.

### 6.2. core/build.gradle hoàn chỉnh

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
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
    api 'org.apache.commons:commons-lang3:3.14.0'
    implementation 'com.google.guava:guava:33.3.1-jre'
    runtimeOnly 'com.h2database:h2:2.3.232'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test') {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Catalog Core'
                description = 'Library with explicit API and runtime metadata'
            }
        }
    }
    repositories {
        maven {
            name = 'demo'
            url = rootProject.file('build/repo').toURI()
        }
    }
}
~~~

Đây là **toàn bộ core/build.gradle**, dùng Groovy DSL. Mỗi phần quan trọng:

- **java-library** tạo configurations **api, implementation, runtimeOnly** và consumable variants **apiElements/runtimeElements**.
- **maven-publish** tạo các task generate POM/GMM và publish, không làm core trở thành executable Spring Boot application.
- **from components.java** là **dòng then chốt**: publication lấy **Java component cùng dependency metadata**, chứ không chỉ gắn JAR file.
- **group/version + project name core** dẫn đến tọa độ mặc định **com.example:core:1.0.0**.
- **api Commons Lang** được công bố trên compile API; **implementation Guava** ở runtime; **runtimeOnly H2** ở runtime; dependencies test không xuất thành runtime libraries.
- **repositories.mavenCentral()** dùng để tải dependency build. **publishing.repositories** là nơi gửi publication. Đây là hai loại repository cấu hình khác nhau.
- Repository **demo** là một **Maven repository dạng file** ở thư mục **publisher/build/repo**, để demo không cần token hoặc server xuất bản. Vẫn cần internet/cache để tải libraries.

Không áp Spring Boot plugin cho core; core là thư viện Java thuần và phải xuất plain JAR với class ở đường dẫn package chuẩn.

### 6.3. app/build.gradle hoàn chỉnh

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
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

App dùng project dependency khi phát triển trong cùng repository. **spring-boot-starter** có thể bỏ version nhờ Spring Boot plugin kết hợp dependency-management plugin; BOM này **không tự quyết định mọi dependency** của core, vì core không áp plugin Boot.

Tại app, **bootJar** đóng gói executable Boot JAR. Khi phát hành **core như library**, chúng ta **không publish bootJar của app thay core JAR**.

### 6.4. Các lệnh Gradle

Từ thư mục root **publisher/** có Gradle Wrapper 8.5 hợp lệ:

~~~bash
./gradlew :core:test :app:bootJar
./gradlew :core:publishMavenJavaPublicationToDemoRepository
~~~

Trên Windows dùng **gradlew.bat**. Nếu repository chưa có wrapper, cần tạo wrapper qua Gradle đã cài hoặc scaffold dự án; không thể chạy ./gradlew chỉ vì file build.gradle tồn tại.

Sau publish thành công, repository local dự kiến có:

~~~text
publisher/build/repo/com/example/core/1.0.0/
├── core-1.0.0.jar
├── core-1.0.0.pom
├── core-1.0.0.module
└── checksum artifacts (tùy môi trường)
~~~

App executable artifact dự kiến ở:

~~~text
publisher/app/build/libs/app-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar app/build/libs/app-1.0.0.jar
~~~

Output nghiệp vụ của app:

~~~text
normalized=GRADLE
H2=true
~~~

**Chỉ app chạy đúng chưa chứng minh core đã publish tốt.** Cần xem metadata và chạy consumer **không dùng project(':core')** ở các mục tiếp theo.

## 7. Metadata Gradle phát hành gồm những gì?

### 7.1. apiElements và runtimeElements

Gradle Java Library plugin cung cấp **apiElements** cho consumer compile và **runtimeElements** cho consumer runtime. Với dependencies mẫu:

~~~text
apiElements:
  - commons-lang3:3.14.0

runtimeElements:
  - commons-lang3:3.14.0
  - guava:33.3.1-jre
  - h2:2.3.232

không xuất như dependency consumer:
  - junit-jupiter:5.11.3
  - junit-platform-launcher:1.11.3
~~~

Sơ đồ là **biểu diễn logic**. Trong JSON thật, attributes, metadata về variants, checksum và version declaration có cấu trúc riêng. Dependency transitive của Guava hoặc H2 cũng được resolve theo metadata của chính chúng.

### 7.2. Maven POM sinh từ Java component

Khi dùng **from components.java** trên java-library, Gradle sinh POM có scope phù hợp. Phần dependency gần tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
        <scope>compile</scope>
    </dependency>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
        <version>33.3.1-jre</version>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <version>2.3.232</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đây là **fragment kỳ vọng**, không phải POM toàn văn. Gradle có thể thêm các XML elements hợp lệ khác và marker comment báo có .module tương ứng.

Ánh xạ chính:

| Khai báo Gradle java-library | POM Maven sinh từ Java component |
| --- | --- |
| **api** | **compile** |
| **implementation** | **runtime** |
| **runtimeOnly** | **runtime** |
| **testImplementation / testRuntimeOnly** | Không xuất thành dependency compile/runtime của consumer |
| **compileOnly** | Không được coi là runtime dependency công bố; Maven POM không biểu diễn đầy đủ ngữ nghĩa compile-only |

**Mấu chốt:** Guava không nằm trên consumer compileClasspath do core export như api, nhưng vẫn nằm trên consumer runtimeClasspath. Đây là behavior đúng.

### 7.3. GMM đầy đủ hơn POM

Gradle Module Metadata có **variants và attributes** chọn theo usage như java-api/java-runtime. Ngoài ra có thể mô tả **rich version constraints, dependency constraints, capabilities và feature variants**. Maven POM không có cấu trúc tương đương cho mọi tính năng nên mapping có thể mất thông tin.

Gradle thường xuất **cả POM và .module**, cùng một marker comment trong POM chỉ dẫn Gradle rằng module metadata chi tiết hơn tồn tại. Maven client tiếp tục đọc POM; Gradle consumer có thể ưu tiên .module. Nếu proxy/repository làm mất .module, Gradle có thể fallback sang POM và hành vi variant selection có thể kém chính xác hơn.

### 7.4. Kiểm tra file được sinh trước khi publish

~~~bash
./gradlew :core:generatePomFileForMavenJavaPublication
./gradlew :core:generateMetadataFileForMavenJavaPublication
~~~

Các file build-local thông thường:

~~~text
core/build/publications/mavenJava/pom-default.xml
core/build/publications/mavenJava/module.json
~~~

Sau publish, chúng được đặt theo Maven layout **core-1.0.0.pom** và **core-1.0.0.module**. Hãy kiểm tra **đúng dependency/variant/scope**, không chỉ kiểm tra rằng file tồn tại.

Nếu công cụ build có thêm plugin thay đổi publication, nội dung có thể khác. Khi cần kiểm thử CI, dùng XML/JSON parser và so sánh dependency theo **group/name/version/scope/variant**, không so sánh thứ tự dòng.

## 8. Xem classpath và outgoing variants khi vẫn ở workspace

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :core:dependencies --configuration runtimeClasspath
./gradlew :core:outgoingVariants
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

**Dự kiến:**

- **core compileClasspath:** Commons Lang + Guava; không yêu cầu H2.
- **core runtimeClasspath:** Commons Lang + Guava + H2.
- **core outgoingVariants:** apiElements và runtimeElements cùng attributes/artifacts.
- **app compileClasspath:** có Commons Lang qua API của core; core không xuất Guava/H2 trên API compile.
- **app runtimeClasspath:** có Commons Lang + Guava + H2 phục vụ chạy thư viện.

**Quan trọng:** core compileClasspath của **module khai báo** và app compileClasspath của **consumer** không phải cùng thứ. Guava phải có trong compiler của core vì code core import CharMatcher, nhưng consumer không phải nhìn thấy Guava khi chỉ gọi public API chứa Pair.

Các lệnh này giúp giải thích build nội bộ, **chưa thay thế kiểm thử consumption sau publish**.

## 9. Consumer Gradle độc lập: thử metadata thật, không dùng project dependency

Tạo **một dự án thứ hai** bên cạnh publisher:

~~~text
workspace/
├── publisher/
│   └── build/repo/com/example/core/1.0.0/...
└── consumer/
    ├── settings.gradle
    ├── build.gradle
    └── src/main/java/com/example/consumer/ConsumerMain.java
~~~

Tệp **consumer/settings.gradle**:

~~~groovy
rootProject.name = 'consumer'
~~~

Tệp **consumer/build.gradle**:

~~~groovy
plugins {
    id 'application'
}

group = 'com.example.consumer'
version = '1.0.0'

repositories {
    maven {
        url = uri('../publisher/build/repo')
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example:core:1.0.0'
}

application {
    mainClass = 'com.example.consumer.ConsumerMain'
}
~~~

Đây là **file build.gradle hoàn chỉnh**. Nó dùng tọa độ của artifact đã publish, **không biết gì về project(':core')**, nên buộc Gradle đọc metadata của repository. Plugin application tạo task **run** và bao gồm khả năng Java plugin.

Tệp **consumer/src/main/java/com/example/consumer/ConsumerMain.java**:

~~~java
package com.example.consumer;

import com.example.core.CatalogFormatter;
import org.apache.commons.lang3.tuple.Pair;

public class ConsumerMain {
    public static void main(String[] args) throws Exception {
        Pair<String, String> result =
                CatalogFormatter.describe("  gradle  ");
        System.out.println(result.getLeft() + "=" + result.getRight());
        System.out.println("H2=" +
                CatalogFormatter.canOpenEmbeddedDb());
    }
}
~~~

Đây là class Java 17 hoàn chỉnh. **Không** khai báo Commons Lang, Guava hoặc H2 trực tiếp trong consumer/build.gradle. Chúng phải tới từ metadata của core.

Đứng tại **workspace/consumer**, với Gradle phù hợp đã cài:

~~~bash
gradle run
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
~~~

Nếu consumer có wrapper, dùng **./gradlew** thay cho **gradle**. Để runnable, JDK 17 phải có và dependencies cần được tải từ Maven Central/cache.

**Hai dòng ứng dụng in ra khi metadata đúng:**

~~~text
normalized=GRADLE
H2=true
~~~

Trong graph, **compileClasspath** nên có core + Commons Lang; **runtimeClasspath** có thêm Guava/H2. JUnit của core không được đưa vào runtime graph của consumer. Nếu runtime JDBC lỗi, kiểm tra H2 dependency trong runtime variant/POM, repository và thông báo exception.

**Một consumer độc lập là phép thử mạnh hơn reactor:** nó buộc công cụ đọc published identity/metadata thay vì đọc project graph từ workspace gốc.

## 10. Maven: quan hệ aggregator, parent và dependency

Trong Maven multi-module, cần phân biệt:

- **Aggregation**: root POM khai báo **modules**, cho Maven Reactor xây nhiều module theo dependency graph.
- **Inheritance**: child POM khai báo **parent**, nhận cấu hình, group/version, dependencyManagement, pluginManagement và properties thích hợp.
- **Dependency**: app POM khai báo core theo Maven coordinates; Maven resolve từ reactor hoặc repository.
- **Publication**: install/deploy **artifact + POM** của từng module; parent POM có thể cần publish riêng.

**Aggregation không tự kéo theo inheritance**. Một child nằm trong <modules> không tự kế thừa parent config nếu không ghi <parent>. Ngược lại, **published core POM tham chiếu parent nội bộ** thì consumer ngoài reactor phải resolve được parent POM đó.

### 10.1. Root pom.xml hoàn chỉnh

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
    <artifactId>publisher-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

Root vừa là **aggregator** vừa là **parent** của core/app. Nó không đóng JAR vì **packaging pom**. Spring Boot parent cung cấp dependency management cho các starter thuộc app; không tự biến core thành Boot application.

### 10.2. core/pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>publisher-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>com.google.guava</groupId>
            <artifactId>guava</artifactId>
            <version>33.3.1-jre</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Đây là core POM độc lập trong Maven Reactor. Parent cung cấp group/version và dependencyManagement để starter-test không cần version tường minh.

**Khác với Gradle Java Library:** Maven compile scope mặc định dành cho cả **Commons Lang** và **Guava**, vì code core cần cả hai khi compile. Maven **không có configuration implementation tách khỏi public API**. Không đổi Guava thành scope runtime trong core POM chỉ để “ẩn” khỏi compile classpath consumer, vì compiler của chính core đang import Guava CharMatcher.

Với POM viết theo Maven ở đây:

~~~text
Commons Lang : Maven compile
Guava        : Maven compile
H2           : Maven runtime
Starter Test : Maven test
~~~

Với POM **do Gradle java-library sinh ra**:

~~~text
Commons Lang : Maven compile
Guava        : Maven runtime
H2           : Maven runtime
JUnit        : không là dependency runtime/compile của consumer
~~~

Hai cách đều có thể tạo core chạy được, nhưng Gradle thể hiện **rõ public API vs implementation hơn**. Đây là giới hạn mô hình dependency Maven cần hiểu khi so sánh published POM.

### 10.3. app/pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>publisher-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

**App** phụ thuộc core bằng GAV **com.example:core:1.0.0**. Trong cùng reactor, Maven có thể build module core trước app. Boot Maven Plugin chỉ xuất hiện tại app và thực hiện **repackage** để tạo executable artifact; **core vẫn là library JAR thường**.

Nếu muốn đóng gói app theo Maven:

~~~bash
./mvnw clean verify
java -jar app/target/app-1.0.0.jar
~~~

Hoặc dùng **mvn clean verify** khi không có wrapper nhưng đã cài Maven phù hợp. Trên Windows dùng **mvnw.cmd**. Với main class ở mục 5 và đúng dependencies, hai dòng output của ứng dụng vẫn là **normalized=GRADLE** và **H2=true**.

## 11. Maven: install/deploy POM cùng parent

Một lỗi publication nguy hiểm là **chỉ upload core-1.0.0.jar** mà bỏ POM, hoặc publish core POM có **parent không thể resolve**.

Từ root publisher:

~~~bash
./mvnw -pl core -am clean install
~~~

Lệnh này chọn module **core** và những reactor projects cần thiết, sau đó install JAR/POM vào local Maven repository. Nếu cấu hình dự án phức tạp, cần xác minh cả root parent được cài; có thể chạy **mvn install** ở root nếu muốn cài toàn bộ reactor.

Trong local Maven repository, dự kiến cần:

~~~text
~/.m2/repository/com/example/publisher-parent/1.0.0/publisher-parent-1.0.0.pom
~/.m2/repository/com/example/core/1.0.0/core-1.0.0.pom
~/.m2/repository/com/example/core/1.0.0/core-1.0.0.jar
~~~

Khi deploy ra remote repository của tổ chức, parent **publisher-parent:1.0.0** cũng phải có mặt; Spring Boot parent là public artifact có thể resolve từ repository thích hợp. Nếu core POM trỏ tới một **internal BOM/parent** khác, những metadata đó cũng phải publish và cấp quyền phù hợp.

**Phân biệt package, install và deploy:**

- **package**: tạo artifact tại **target/**.
- **install**: cài artifact/POM vào **local Maven repository**.
- **deploy**: gửi artifact/POM đến **remote Maven repository** đã cấu hình (kèm credential/permission phù hợp).

Chỉ chạy **mvn package** không làm consumer ở máy khác tìm thấy core. Chỉ có core JAR trong repo mà thiếu POM cũng khiến transitive dependencies không được truyền đúng.

### 11.1. Kiểm tra effective POM và dependency tree

~~~bash
./mvnw -pl core help:effective-pom
./mvnw -pl app dependency:tree
~~~

**effective-pom** áp dụng parent và dependencyManagement để thấy model được Maven dùng khi build. **dependency:tree** giải thích core, Commons Lang, Guava và H2 đi vào app theo đường transitive.

**Nhưng effective POM không thay thế việc đọc published POM**. Published core POM có thể vẫn giữ thẻ parent, nên consumer phải resolve được parent. Cần test một consumer riêng **ngoài reactor**, chỉ khai báo GAV core và repository đích.

### 11.2. Một dependency trong consumer Maven

Consumer Maven có thể khai báo:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Đây là **fragment nằm trong dependencies của pom.xml consumer**, không phải toàn bộ POM chạy độc lập. Consumer sẽ đọc POM core đã install/deploy và parent tương ứng. Nếu thiếu parent/BOM/version, Maven sẽ fail trước khi tải được dependency graph đúng.

## 12. BOM, constraints và chính sách version khi publish

### 12.1. BOM là version management, không tự thêm library runtime

Trong Maven, một BOM được import trong **dependencyManagement**, ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **fragment cấu hình** của một POM khác, không chèn thêm vào root POM bài tập vì root đã dùng Spring Boot parent. BOM quản lý version của các dependency được khai báo, **không tự khiến tất cả dependency nằm trong BOM xuất hiện trên classpath**.

Trong Gradle, có thể dùng native **platform** cho dependency constraints:

~~~groovy
dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    api 'org.springframework.boot:spring-core'
}
~~~

Đây là **fragment minh họa cho một java-library muốn đưa constraints của BOM vào public API**, không phải đoạn cần thêm vào core demo. Gradle GMM mô tả platform/constraints chi tiết hơn POM; nếu publish tới Maven consumers, cần kiểm tra generated dependencyManagement/versions và khả năng resolve của consumer.

### 12.2. Declared versions khác resolved versions

Maven Publish Plugin của Gradle có thể xuất bản **declared version** từ dependency declarations. Nhưng dependency locking, conflict resolution, rich constraints hoặc dynamic selectors có thể khiến **resolved version** mà project test khác với text khai báo.

Gradle hỗ trợ **versionMapping**. Ví dụ thay block publication của core bằng:

~~~groovy
mavenJava(MavenPublication) {
    from components.java

    versionMapping {
        usage('java-api') {
            fromResolutionOf('runtimeClasspath')
        }
        usage('java-runtime') {
            fromResolutionResult()
        }
    }
}
~~~

Đoạn này là **fragment thay thế**, không phải toàn bộ build.gradle. Nó cho phép mapping versions từ kết quả resolve, giúp published POM gần với dependencies đã được build/test. Không tự suy ra rằng versionMapping giải quyết mọi rich constraints hoặc làm mọi consumer luôn dùng cùng version: consumer vẫn có dependency resolution rules của mình.

Với core demo, ba dependency chính đều đã khai báo version cố định, nên phiên bản trong POM dễ kiểm tra mà không cần versionMapping.

### 12.3. Không publish versionless dependencies không thể resolve

Một dependency không có version trong published POM **chỉ hợp lệ** khi parent/dependencyManagement hoặc cơ chế chuẩn khác thực sự cung cấp version và có thể truy cập từ consumer. Không xóa version để làm gọn POM rồi bỏ quên parent/BOM.

Tương tự, Gradle module metadata có constraints nhưng không có khả năng chọn phiên bản hợp lệ sẽ khiến consumer fail. Luôn kiểm tra **metadata đã publish**, không chỉ suy ra từ cấu hình nguồn.

## 13. Boot executable artifact không giống Java component publication

Spring Boot Gradle Plugin có hướng dẫn publish **bootJar** bằng một MavenPublication gắn artifact trực tiếp. Một fragment minh họa:

~~~groovy
publishing {
    publications {
        bootApp(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
~~~

Muốn dùng fragment này, module app phải đã áp dụng **maven-publish** và cấu hình publishing repository. Nhưng **artifact tasks.named('bootJar') chỉ chỉ ra file upload**; nó **không tự tạo đầy đủ Java library dependency metadata** như publication **from components.java**.

Không trộn một Boot executable JAR vào publication Java component rồi mong consumer compile như library thường: **BOOT-INF/classes** không phải classpath root của library JAR. Nếu một tổ chức cần publish cả plain JAR và executable app, phải thiết kế publication/classifier/coordinates riêng, tránh đè artifact và cho consumer biết rõ loại nào nên dùng.

**Quy tắc thực hành:** core được phát hành dưới dạng **Java library + POM/GMM**; app được phát hành dưới dạng **executable Boot JAR/container image**. Đây là cách giữ contract dependency rõ ràng cho multi-module Spring Boot.

## 14. Khi Maven và Gradle đọc metadata khác nhau

### 14.1. Tính biểu đạt khác nhau

GMM biểu diễn variants/capabilities/rich versions, còn Maven POM chủ yếu có scopes, optional, exclusions và dependencyManagement. Các tính năng như **feature variants**, **compileOnlyApi** hoặc capability conflict rules có thể **không ánh xạ hoàn toàn** sang POM.

Khi Gradle publish một component có features không thể diễn đạt đầy đủ trong POM, Gradle có thể cảnh báo. Không chỉ dùng **suppressPomMetadataWarningsFor** để tắt thông báo: hành động đó không sửa contract của Maven consumer. Phải xác minh tính tương thích hoặc cung cấp artifact/publication khác nếu cần.

### 14.2. Có POM nhưng thiếu .module

Maven consumer vẫn đọc được POM. Gradle có thể suy ra variants từ POM scopes nhưng mất một phần thông tin Gradle-native. Nếu repository/proxy lọc bỏ .module hoặc chỉ phục vụ metadataSources.mavenPom(), consumer Gradle có thể resolve khác lúc đọc GMM.

### 14.3. Có .module nhưng thiếu POM

Consumer Maven không hiểu GMM như POM thay thế. Nếu mục tiêu hỗ trợ Maven, phải publish POM hợp lệ cùng artifact. Cấu hình **maven-publish** từ Java component thường đáp ứng điều này.

### 14.4. Metadata cache không nhất quán

Nếu cùng một GAV **com.example:core:1.0.0** bị ghi đè nhiều lần, một consumer có thể giữ POM/JAR cũ còn consumer khác tải module metadata mới. Vì vậy bản release nên **immutable**, tăng version khi dependency graph hoặc bytes thay đổi và publish đồng bộ JAR/POM/.module/checksums. Không chữa lỗi metadata bằng cách liên tục ghi đè release version cố định.

## 15. CI: kiểm chứng bản publish bằng consumer contract

### 15.1. Quy trình Gradle

Một pipeline kiểm tra thư viện có thể chạy:

~~~bash
./gradlew clean :core:test :app:bootJar
./gradlew :core:generatePomFileForMavenJavaPublication
./gradlew :core:generateMetadataFileForMavenJavaPublication
./gradlew :core:publishMavenJavaPublicationToDemoRepository
~~~

Sau đó kiểm tra:

1. Repository có **core-1.0.0.jar, core-1.0.0.pom, core-1.0.0.module**.
2. POM có **Commons Lang compile**, **Guava/H2 runtime**, không công bố JUnit dưới compile/runtime.
3. GMM có **Commons Lang ở API và runtime**, **Guava/H2 ở runtime**, không có JUnit trong variants dùng cho consumer.
4. Group/artifact/version đúng, không còn dynamic version trái chính sách.
5. Consumer độc lập compile và chạy, cho ra **normalized=GRADLE** và **H2=true**.
6. App Boot JAR cũng chạy thành công nhưng **không bị chọn nhầm làm core artifact**.

**Gợi ý kiểm thử tự động:** dùng XML parser đọc POM và JSON parser đọc .module, so sánh theo group/name/version/scope/variant. Đừng dùng so sánh toàn văn theo thứ tự dòng, vì Gradle versions có thể thêm attributes hoặc thay thứ tự entries.

### 15.2. Quy trình Maven

~~~bash
./mvnw clean verify
./mvnw -pl core -am install
./mvnw -pl core help:effective-pom
./mvnw -pl app dependency:tree
~~~

Sau đó xem parent/core POM thực sự được cài trong local Maven repository và chạy consumer ngoài reactor. Nếu xuất bản lên remote server, kiểm tra cả **parent POM, BOM nội bộ và quyền truy cập**, không chỉ core JAR.

### 15.3. Nhận diện lỗi từ phía consumer

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| Compile lỗi thiếu Pair | Commons Lang có ở API variant / POM compile không? |
| Runtime lỗi NoClassDefFoundError của Guava | Guava có trong runtimeElements / POM runtime không? |
| Runtime báo No suitable driver cho jdbc:h2 | H2 có trong runtime graph không? |
| JUnit xuất hiện trong runtime production | Scope/test configurations có bị publish sai không? |
| Non-resolvable parent POM | Parent/BOM nội bộ đã publish và consumer có repository/permission chưa? |
| Gradle và Maven chọn dependencies khác nhau | So sánh .module vs POM, versions, constraints, metadataSources |
| App Boot JAR không dùng được như library | Có nhầm bootJar làm plain Java component publication không? |

## 16. Các lỗi phổ biến và hướng xử lý

**1. Publish mỗi JAR mà không có POM hoặc GMM.** Consumer không biết transitive dependencies. Dùng **maven-publish from components.java** cho Gradle library hoặc Maven install/deploy đầy đủ JAR và POM.

**2. Dùng Gradle java plugin nhưng khai báo api.** **api** thuộc java-library. Chuyển module cung cấp public API sang **java-library**.

**3. Đặt Commons Lang ở implementation dù public API dùng Pair.** Consumer cần type Pair khi compile. Chuyển Commons Lang sang **api** hoặc thiết kế public API không lộ type này.

**4. Đặt Guava ở api dù chỉ dùng nội bộ.** Không gây lỗi ngay nhưng rò rỉ chi tiết triển khai. Dùng **implementation**.

**5. Loại Guava khỏi runtime vì muốn giấu implementation.** Class CharMatcher vẫn được gọi khi chạy. Implementation của core **phải có** ở consumer runtime.

**6. Đặt H2 ở testImplementation trong khi feature sản phẩm dùng JDBC URL H2.** Test có thể chạy nhưng app không có driver. Chọn runtimeOnly nếu thư viện thật sự cam kết runtime driver đó.

**7. Publish JUnit như runtime dependency.** Consumer nhận test tool thừa. Giữ JUnit trong testImplementation hoặc Maven test scope.

**8. Dùng Gradle artifact file upload mà quên component.** File có thể được upload nhưng metadata dependency thiếu. Với library, dùng **from components.java**.

**9. Dùng Boot executable JAR như thư viện.** Class nằm dưới BOOT-INF/classes; không phù hợp compile consumer thường. Xuất plain JAR từ core.

**10. Tưởng Gradle build.success đồng nghĩa publish.success.** Build nội bộ có project dependency và classpath khác consumer ngoài. Hãy publish và test consumer độc lập.

**11. Maven core POM có parent private chưa được deploy.** Consumer không thể dựng effective model. Publish parent POM và BOM nội bộ hoặc thiết kế POM tự đủ.

**12. Đổi Maven Guava compile thành runtime để giả lập Gradle implementation.** Maven core cần Guava lúc compile; scope runtime sẽ làm core compile fail. Hiểu giới hạn Maven scopes thay vì sửa sai.

**13. Chỉ gọi Maven package.** Package không install/deploy artifact tới repository của consumer. Dùng install/deploy theo môi trường.

**14. Chỉ kiểm tra Gradle .module mà có Maven consumer.** Maven dùng POM. Phải QA POM và test Maven consumer.

**15. Chỉ kiểm tra POM mà có Gradle consumer.** Gradle có thể ưu tiên GMM chứa variants khác. Phải QA cả hai.

**16. Suppress POM metadata warnings không đọc nội dung.** Ẩn warning không biến rich constraints/capabilities thành POM tương đương. Cần đánh giá consumer compatibility.

**17. Version thiếu trong published POM.** Kiểm tra BOM/parent/dependencyManagement và versionMapping. Không publish versionless dependency thiếu nguồn quản lý.

**18. Repository publish và repository resolve bị nhầm.** **repositories** tải build dependency; **publishing.repositories** xác định nơi ghi artifact. Cấu hình cả hai đúng nhu cầu.

**19. ArtifactId trong publication khác tọa độ consumer.** Kiểm tra **groupId/artifactId/version** của generated POM và URI repository. Đừng chỉ dựa vào tên project hoặc folder.

**20. Publish đè cùng release GAV với nội dung khác.** Cache dẫn đến các consumer thấy metadata khác nhau. Dùng release version immutable, không sửa lại một phiên bản đã công bố.

**21. Maven parent và aggregator bị nhầm.** Có <modules> không tự làm POM con kế thừa cấu hình. Child phải khai báo <parent> đúng nếu muốn inheritance.

**22. Consumer chỉ chạy bằng project(':core').** Đây không phải test publication. Tạo consumer ở project riêng dùng **com.example:core:1.0.0**.

**23. Có BOM nhưng tưởng BOM tự mang vào mọi library.** BOM chỉ quản lý version/constraints; vẫn phải khai báo dependency cần dùng ở configuration đúng.

**24. Chỉ kiểm tra API compile mà quên runtime.** Consumer có thể compile đẹp nhưng lỗi CharMatcher hoặc JDBC driver khi chạy. Bắt buộc có runtime smoke test.

## 17. Checklist xuất bản thư viện cho nhóm khác dùng

- [ ] Tách **library core** khỏi **Spring Boot app**.
- [ ] Module thư viện Gradle dùng **java-library + maven-publish**.
- [ ] Gradle publication dùng **from components.java**.
- [ ] API dependency chứa type public được khai báo **api**.
- [ ] Implementation dependency cần lúc chạy có mặt ở runtimeElements/POM runtime.
- [ ] Runtime-only provider/driver có mặt ở consumer runtime.
- [ ] JUnit và test support không bị xuất thành dependency sản phẩm.
- [ ] Maven POM có đủ scopes và parent/BOM được publish, có thể resolve.
- [ ] Generated POM có đúng groupId/artifactId/version và dependency versions.
- [ ] Gradle .module có đúng apiElements/runtimeElements và attributes.
- [ ] Có checksum/release identity và không ghi đè release artifact.
- [ ] Consumer Maven và consumer Gradle được kiểm thử độc lập nếu phải hỗ trợ cả hai.
- [ ] App executable JAR không bị phát hành nhầm làm library.
- [ ] CI phát hiện lỗi publish, parse metadata và chạy consumer smoke test.
- [ ] Version/BOM/constraints thay đổi thì phải kiểm tra lại contract.

## 18. Tài liệu chính thức

- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Spring Boot — Publishing with the Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/publishing.html)
- [Spring Boot — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Kết luận:** Trong multi-module Spring Boot, build thành công **không chứng minh metadata xuất bản đúng**. Hãy publish plain JAR của thư viện cùng **Maven POM và Gradle Module Metadata**, ánh xạ đúng **api/implementation/runtimeOnly**, giữ test dependencies ngoài production, xử lý parent/BOM/version rõ ràng và kiểm tra **consumer độc lập**. Spring Boot executable JAR thuộc đường triển khai ứng dụng, không thay thế publication của một Java library.