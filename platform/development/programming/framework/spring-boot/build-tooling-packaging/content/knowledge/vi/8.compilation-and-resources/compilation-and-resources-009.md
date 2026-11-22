# Tách tài nguyên kiểm thử khỏi tài nguyên đóng gói trong Spring Boot (Maven và Gradle)

## 1. Vì sao phải tách tài nguyên?

Một dự án Spring Boot có nhiều tệp không phải mã Java: **application.properties**, YAML, template, ảnh, SQL migration, chứng chỉ, file JSON/CSV mẫu, dữ liệu giả và các fixture kiểm thử. Không phải tệp nào cũng cần nằm trong JAR chạy production.

Ví dụ:
- **Cấu hình và dữ liệu ứng dụng thực sự cần khi chạy** thuộc phần *main*.
- **Dữ liệu mẫu, mock response, test properties, JSON/CSV fixture** chỉ phục vụ unit test, integration test hoặc Spring Boot test context thuộc phần *test*.
- **Executable Spring Boot JAR** phải mang tài nguyên production cần thiết, nhưng không nên kéo theo test fixtures, test configuration hoặc lớp kiểm thử.

Sự phân chia đúng bắt đầu từ **source layout** của Maven/Gradle. Cả hai công cụ mặc định coi **src/main/resources** và **src/test/resources** là **hai nguồn tài nguyên khác nhau**. Không cần thêm một bước xóa thủ công sau khi đóng gói nếu tuân thủ đúng quy ước và không tự làm lẫn nguồn.

**Mục tiêu bài này:** hiểu đường đi từ resource source → resource output → classpath test/runtime → JAR; thiết lập dự án Spring Boot; dùng profile test đúng cách; xác nhận JAR sạch; xử lý layout tùy chỉnh và các lỗi phổ biến.

## 2. Hai thư mục resource có vai trò khác nhau

Cấu trúc quy ước của một ứng dụng Java/Spring Boot:

~~~text
resource-split/
├── pom.xml                  # dùng khi chọn Maven
├── settings.gradle           # dùng khi chọn Gradle
├── build.gradle              # dùng khi chọn Gradle
└── src/
    ├── main/
    │   ├── java/com/example/resourcesplit/ResourceSplitApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── messages/public.txt
    └── test/
        ├── java/com/example/resourcesplit/ResourceSplitApplicationTest.java
        └── resources/
            ├── application-test.properties
            └── fixtures/test-only.txt
~~~

Đây là cây thư mục mô tả **hai lựa chọn build thay thế**. Một dự án thực tế nên chọn Maven hoặc Gradle và giữ bộ tệp build tương ứng; không nhất thiết cần cả ba tệp pom.xml, settings.gradle và build.gradle.

| Vị trí | Chức năng | Được test đọc? | Được JAR main/Boot JAR đóng gói mặc định? |
| --- | --- | --- | --- |
| **src/main/java** | Java source sản phẩm | Có, qua main classes của project | Có, sau biên dịch |
| **src/main/resources** | Cấu hình, template và dữ liệu runtime | Có | **Có** |
| **src/test/java** | JUnit/Spring test code | Có | **Không** |
| **src/test/resources** | Dữ liệu mẫu và cấu hình cho test | **Có** | **Không** |

**“Test đọc được main resources” không có nghĩa “test resources sẽ đi vào main JAR”.** Trong quá trình kiểm thử, test classpath thường bao gồm output của cả main và test. Khi đóng gói JAR thường hoặc executable Boot JAR mặc định, công cụ lấy main output/runtime dependencies thích hợp; không lấy test output.

Nếu đặt **test-only.txt** trong **src/main/resources** dù chỉ test gọi đến, nó vẫn trở thành tài nguyên production. Việc đặt sai thư mục là nguyên nhân rò rỉ test fixture thường gặp nhất.

## 3. Đường đi tài nguyên trong Maven

Maven quy định các thư mục chuẩn và các pha lifecycle. Với layout mặc định:

~~~text
src/main/resources/**        --process-resources-->       target/classes/**
src/main/java/**             --compile----------->       target/classes/**/*.class

src/test/resources/**        --process-test-resources-->  target/test-classes/**
src/test/java/**             --test-compile------->       target/test-classes/**/*.class

Maven test classpath = test output + main output + test-scope dependencies cần thiết

Maven package (JAR thường) = main classes/resources trong target/classes
Spring Boot repackage      = main classes/resources + dependency runtime cần thiết
~~~

Các mốc cần nắm:

1. Pha **process-resources** sử dụng Maven Resources Plugin để copy/filter resource dành cho main vào **target/classes**.
2. Pha **process-test-resources** đưa resource test vào **target/test-classes**.
3. **test-compile** tạo các class test cũng trong **target/test-classes**.
4. **test** dùng cả main output và test output trên test classpath để chạy unit/integration test tương ứng.
5. **package** tạo artifact phân phối. Với dự án Spring Boot có spring-boot-maven-plugin được cấu hình theo Spring Boot parent, bước **repackage** xây executable JAR từ artifact chính và dependency runtime phù hợp.

**Mặc định Maven không nhặt toàn bộ thư mục target rồi đưa vào JAR.** **target/test-classes** có thể còn trên đĩa sau khi chạy test/package nhưng không tự xuất hiện trong executable JAR. Không được kết luận “test resources bị đóng gói” chỉ vì chúng còn trong target/test-classes.

### Lệnh Maven hữu ích

~~~bash
./mvnw clean test
./mvnw package
~~~

- **clean test** xóa output cũ rồi chạy qua các pha resource processing, compile và test.
- **package** tạo artifact để kiểm tra.
- Trên Windows dùng **mvnw.cmd**; khi dự án không có wrapper và đã cài Maven phù hợp, dùng **mvn**.

Maven **-DskipTests** có thể bỏ qua việc *chạy* test nhưng không phải cơ chế phân chia tài nguyên. Dùng flag skip test để đóng gói mà không hiểu cấu trúc source sẽ không giải quyết việc một fixture được đặt nhầm trong **src/main/resources**.

## 4. Đường đi tài nguyên trong Gradle

Gradle Java plugin có khái niệm **source set**. Mặc định tồn tại:

- **main**: src/main/java + src/main/resources.
- **test**: src/test/java + src/test/resources.

Gradle tạo các task và đầu ra tương ứng:

~~~text
src/main/resources/**   --processResources-->       build/resources/main/**
src/main/java/**        --compileJava-------->       build/classes/java/main/**

src/test/resources/**   --processTestResources-->   build/resources/test/**
src/test/java/**        --compileTestJava----->      build/classes/java/test/**

sourceSets.main.output = main classes + main processed resources
sourceSets.test.output = test classes + test processed resources

test task               -> test runtime classpath (main + test + test deps)
jar task                -> main output
bootJar task            -> main output + main runtime dependencies
~~~

Lệnh kiểm tra bằng Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew processResources processTestResources
./gradlew bootJar
~~~

Trên Windows dùng **gradlew.bat**. Khi chạy **test**, Gradle thường sẽ chạy các task cần thiết để có main/test classes và resources. **processTestResources** có thể xuất hiện dưới dạng **UP-TO-DATE** nếu resource không thay đổi; điều đó không có nghĩa task không áp dụng.

Trong ứng dụng Boot, **bootJar** tạo executable JAR. Spring Boot Gradle Plugin cấu hình Boot JAR từ **main source set** và **runtimeClasspath** của main; đây là lý do test fixtures và **testImplementation** dependencies không tự đi vào artifact sản phẩm.

**Phân biệt task:** **jar** thông thường tạo JAR từ main output; **bootJar** tạo Spring Boot executable JAR với bố cục Boot, gồm **BOOT-INF/classes/** và **BOOT-INF/lib/**. Cả hai không phải bản sao vô điều kiện của toàn bộ thư mục build/.

## 5. Tài nguyên chính (main) và tài nguyên test ở Spring Boot

Spring Boot có cơ chế nạp cấu hình theo profile. Đặt profile **test** là cách thường dùng để điều chỉnh property khi chạy kiểm thử.

Trong bài thực hành, dùng:

**src/main/resources/application.properties**

~~~properties
app.label=PRODUCTION
spring.main.banner-mode=off
~~~

**src/main/resources/messages/public.txt**

~~~text
PUBLIC_RESOURCE
~~~

**src/test/resources/application-test.properties**

~~~properties
app.label=TEST_ONLY
~~~

**src/test/resources/fixtures/test-only.txt**

~~~text
TEST_FIXTURE_ONLY
~~~

Những tệp này minh họa ranh giới rõ ràng:

- **application.properties** và **messages/public.txt** thuộc main nên vừa đọc được khi test vừa có trong JAR.
- **application-test.properties** và **fixtures/test-only.txt** thuộc test nên xuất hiện ở **test runtime classpath**, còn JAR chính không mang theo.
- Giá trị **app.label** trong test có thể được thay bằng **TEST_ONLY** khi bật profile test; khi chạy JAR production không bật profile đó và không có nguồn override ngoài, giá trị là **PRODUCTION**.

**Không nhầm quy tắc:** Tên **application-test.properties** tự nó **không** khiến tệp bị loại khỏi đóng gói. Một **application-test.properties đặt trong src/main/resources** vẫn là *main resource* và có thể bị đóng gói. Chính **vị trí source set** và cấu hình build quyết định tài nguyên thuộc artifact nào.

Tương tự, file **application-prod.yml** trong main là cấu hình runtime có thể được đóng gói và kích hoạt khi profile prod được chọn. Không nên xóa mọi tệp có tên chứa **test** bằng pattern tên mà không biết chúng dùng ở đâu.

### Kích hoạt profile test

Trong test class, dùng **@ActiveProfiles("test")** cùng Spring Test context để kích hoạt cấu hình theo profile. **src/test/resources** chỉ làm resource có mặt trên test classpath; bản thân đường dẫn này **không tự kích hoạt** profile test.

Khi không khởi tạo Spring ApplicationContext, một unit test Java thuần vẫn có thể đọc fixture bằng classloader, nhưng **@ActiveProfiles** không tự có tác dụng nếu không sử dụng Spring Test context. Chọn công cụ test phù hợp điều muốn kiểm tra.

## 6. Bài thực hành Spring Boot hoàn chỉnh (Java 17)

Ta xây cùng một chương trình và cùng các resource, rồi chọn cấu hình Maven **hoặc** Gradle. Ví dụ này cố tình không mở HTTP server và không cần database để tập trung vào resource handling.

### 6.1. Java application: đọc resource main

Tạo file **src/main/java/com/example/resourcesplit/ResourceSplitApplication.java**:

~~~java
package com.example.resourcesplit;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;

@SpringBootApplication
public class ResourceSplitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceSplitApplication.class, args);
    }

    @Bean
    CommandLineRunner showMainResources(Environment environment) {
        return args -> {
            String label = environment.getProperty("app.label", "MISSING");
            String message;
            try (InputStream input = new ClassPathResource(
                    "messages/public.txt").getInputStream()) {
                message = new String(
                        input.readAllBytes(), StandardCharsets.UTF_8).trim();
            }
            System.out.println("app.label=" + label);
            System.out.println("main.resource=" + message);
        };
    }
}
~~~

Đây là **file Java hoàn chỉnh**. **ClassPathResource** đọc qua classpath nên hoạt động cả khi chạy từ thư mục build lẫn khi file resource được đặt bên trong executable Boot JAR. Trong JAR, không thể dùng giả định đường dẫn filesystem trực tiếp **src/main/resources/messages/public.txt** còn tồn tại.

**CommandLineRunner** chạy sau khi context Boot khởi tạo; nó in hai dòng đã biết. Bài thực hành không khai báo Spring Web starter nên không tạo HTTP endpoint hay phụ thuộc cổng 8080.

### 6.2. JUnit test: đọc cả main resource và test-only fixture

Tạo file **src/test/java/com/example/resourcesplit/ResourceSplitApplicationTest.java**:

~~~java
package com.example.resourcesplit;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ResourceSplitApplicationTest {

    @Autowired
    private Environment environment;

    @Test
    void testResourcesAreAvailableWithoutChangingMainResources()
            throws IOException {
        assertEquals("TEST_ONLY", environment.getProperty("app.label"));
        assertEquals("PUBLIC_RESOURCE", load("messages/public.txt"));
        assertEquals("TEST_FIXTURE_ONLY", load("fixtures/test-only.txt"));
    }

    private static String load(String path) throws IOException {
        try (InputStream input = new ClassPathResource(path).getInputStream()) {
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }
}
~~~

Đây cũng là **file Java hoàn chỉnh**, chạy với Spring Boot Starter Test. Test xác nhận ba điều độc lập:

1. Spring Test context đã kích hoạt **profile test** và thấy giá trị **TEST_ONLY**.
2. File **messages/public.txt** từ main xuất hiện trên test classpath.
3. File **fixtures/test-only.txt** từ test cũng xuất hiện trên test classpath.

Khi **@SpringBootTest** khởi tạo Spring context, CommandLineRunner trong ứng dụng cũng có thể in **app.label=TEST_ONLY** và **main.resource=PUBLIC_RESOURCE** vào log test. Output của test runner/Maven/Gradle còn chứa log khác và số lượng dòng tùy môi trường; vì vậy ta xác nhận tính đúng bằng **assertEquals**, không bằng so sánh toàn bộ stdout của test.

Nếu test thiếu file fixture hoặc profile không kích hoạt, nó sẽ thất bại bằng assertion hoặc lỗi resource, giúp tìm lỗi trước khi đóng gói.

## 7. Lựa chọn A: Maven pom.xml đầy đủ

Dùng **pom.xml** sau cùng với mã Java và các resource ở mục 5–6:

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
    <artifactId>resource-split</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lý do cấu hình này đủ:** Spring Boot parent cấu hình dependency/plugin management phù hợp; thư mục resource main/test được Maven tự nhận theo quy ước. **spring-boot-starter-test** có scope **test**, nên các thư viện test chỉ phục vụ kiểm thử. Spring Boot Maven Plugin phục vụ đóng gói executable JAR. **Không cần tự viết plugin copy/exclude** để bỏ src/test/resources khỏi JAR.

Từ thư mục gốc, dùng một trong hai cách:

~~~bash
./mvnw clean verify
java -jar target/resource-split-0.0.1-SNAPSHOT.jar
~~~

Hoặc nếu không có Maven Wrapper:

~~~bash
mvn clean verify
java -jar target/resource-split-0.0.1-SNAPSHOT.jar
~~~

Trên Windows sử dụng **mvnw.cmd** thay **./mvnw**. Lệnh **verify** chạy qua compile/test/package trước khi kết thúc; nếu mọi bước thành công, executable JAR có tên dự kiến như trên với POM mẫu.

**Khi chạy JAR production** mà không có override property hay active profile ngoài, hai dòng do code in ra chính xác là:

~~~text
app.label=PRODUCTION
main.resource=PUBLIC_RESOURCE
~~~

Spring Boot có thể in log khởi động ngoài hai dòng này. Đừng nhầm log framework với output xác định của CommandLineRunner.

## 8. Lựa chọn B: Gradle build.gradle đầy đủ

Chọn Gradle thì dùng **settings.gradle**:

~~~groovy
rootProject.name = 'resource-split'
~~~

Và **build.gradle** (Groovy DSL):

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là cấu hình Gradle Groovy DSL **hoàn chỉnh** cho ví dụ một module. Nó giữ nguyên **sourceSets mặc định** từ Java plugin, nên không cần khai báo lại main/test resource directories.

**Gradle Wrapper** nên đi kèm repository; Gradle 8.5 hỗ trợ chạy trên JDK 17 và phù hợp để minh họa Spring Boot 3.3.5. Đối với dự án dùng **build.gradle.kts**, cần chuyển cú pháp sang Kotlin DSL, không đơn giản đổi đuôi file.

Từ root project:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/resource-split-0.0.1-SNAPSHOT.jar
~~~

Trên Windows dùng **gradlew.bat**. Task **test** kiểm tra fixture và test profile; **bootJar** lấy output/resources của source set main và dependency runtime để tạo executable Boot JAR.

Khi chạy executable JAR với môi trường mặc định, hai dòng do mã Java in ra vẫn là:

~~~text
app.label=PRODUCTION
main.resource=PUBLIC_RESOURCE
~~~

Tính nhất quán này cho thấy **bộ mã nguồn và resource giống nhau** có thể được build bằng hai công cụ mà vẫn tách test fixture khỏi artifact chính.

## 9. Kiểm chứng chắc chắn rằng JAR không chứa tài nguyên test

**Không chỉ tin rằng test chạy xanh.** Sau build, trực tiếp liệt kê danh sách file trong JAR và so sánh với checklist.

### 9.1. Maven

Sau **./mvnw clean verify**:

~~~bash
jar tf target/resource-split-0.0.1-SNAPSHOT.jar
~~~

### 9.2. Gradle

Sau **./gradlew clean test bootJar**:

~~~bash
jar tf build/libs/resource-split-0.0.1-SNAPSHOT.jar
~~~

**Trong danh sách tệp của Spring Boot executable JAR**, phải có các entry:

~~~text
BOOT-INF/classes/application.properties
BOOT-INF/classes/messages/public.txt
BOOT-INF/classes/com/example/resourcesplit/ResourceSplitApplication.class
~~~

**Không được có** các entry sau:

~~~text
BOOT-INF/classes/application-test.properties
BOOT-INF/classes/fixtures/test-only.txt
BOOT-INF/classes/com/example/resourcesplit/ResourceSplitApplicationTest.class
~~~

JAR thực tế còn có nhiều entry như launcher, metadata và các JAR trong **BOOT-INF/lib/**; đây chỉ là những đường dẫn cần đối chiếu. Nếu dùng **jar** thường không repackaged, layout có thể không chứa tiền tố BOOT-INF/classes, nhưng nguyên tắc **main vs test** vẫn đúng.

Có thể dùng **jar tf** cùng công cụ lọc văn bản phù hợp hệ điều hành; lệnh đơn giản ở trên chạy được khi JDK có **jar** tool. Cần chắc chắn đang xem **executable Boot JAR**, không nhầm Gradle **-plain.jar** hoặc một test JAR tạo thêm.

### 9.3. Kiểm chứng thư mục output build

Maven:

~~~text
target/classes/application.properties
target/classes/messages/public.txt
target/test-classes/application-test.properties
target/test-classes/fixtures/test-only.txt
~~~

Gradle:

~~~text
build/resources/main/application.properties
build/resources/main/messages/public.txt
build/resources/test/application-test.properties
build/resources/test/fixtures/test-only.txt
~~~

Nếu thấy **fixtures/test-only.txt** trong **target/classes** hoặc **build/resources/main**, hãy xem lại source root và cấu hình copy/filter. Chỉ thấy nó trong **target/test-classes** hoặc **build/resources/test** là đúng.

**Giới hạn của phép kiểm tra:** Việc tệp không xuất hiện dưới một tên cụ thể chưa đủ chứng minh mọi dữ liệu nhạy cảm đã được loại. Có thể file bị đổi tên, tạo lại trong processResources hoặc copy vào archive bằng một custom task. Khi yêu cầu kiểm soát nghiêm ngặt, hãy kiểm tra toàn bộ entries, đường đi của task và dùng một kiểm thử artifact tự động.

## 10. Phân biệt test resource, test dependency, profile và package

Bốn khái niệm thường bị trộn lẫn:

| Thành phần | Điều khiển cái gì? | Ví dụ |
| --- | --- | --- |
| **src/test/resources** | Tệp nào xuất hiện trên **test resources output/classpath**. | fixtures/test-only.txt |
| **testImplementation** (Gradle) hoặc **scope test** (Maven) | Dependency thư viện nào chỉ phục vụ test compile/runtime. | spring-boot-starter-test |
| **@ActiveProfiles("test")** | Profile nào được Spring Test context kích hoạt. | Chọn application-test.properties |
| **bootJar/repackage** | Tệp main và dependency runtime nào được đưa vào executable Boot archive. | BOOT-INF/classes, BOOT-INF/lib |

**Vị trí tệp**, **scope của dependency**, **Spring profile** và **packaging task** là bốn lớp cấu hình khác nhau. Chỉ đặt một dependency test đúng scope không làm file ở src/main/resources biến thành file test.

Ví dụ một file **application-test.yml** nằm trong **src/main/resources** có thể là cố ý nếu ứng dụng production cũng cần chạy với profile **test** ở môi trường kiểm định. Nếu file đó chứa credential, secret hoặc dữ liệu fixture chỉ dành cho test, phải đánh giá lại vị trí/nguồn cấu hình. Không dùng tên file làm ranh giới bảo vệ.

## 11. Khi dùng cấu trúc source khác chuẩn

**Ưu tiên giữ layout mặc định.** Chỉ cấu hình thêm khi dự án cũ hoặc quy trình sinh dữ liệu thực sự yêu cầu.

### 11.1. Gradle: thêm directory vào test source set

Giả sử có file fixture dưới **src/test-extra/resources**, và muốn test cũng đọc được. Trong **build.gradle** Groovy DSL, thêm fragment:

~~~groovy
sourceSets {
    test {
        resources {
            srcDir 'src/test-extra/resources'
        }
    }
}
~~~

**srcDir** thêm một thư mục resource vào source set test, giữ src/test/resources mặc định. Khi chạy **processTestResources**, tài nguyên mới sẽ được copy vào **build/resources/test**. **Không đưa folder test-extra vào sourceSets.main.resources** nếu muốn giữ nó ngoài JAR.

Nếu dùng **srcDirs = [...]** thay vì **srcDir**, bạn đang đặt lại danh sách nguồn resource tương ứng. Hãy đưa toàn bộ đường dẫn cần giữ vào danh sách để không vô tình làm mất thư mục mặc định.

### 11.2. Maven: thêm thư mục test resource không chuẩn

Trong **pom.xml**, có thể dùng **build/testResources**. Ví dụ fragment cho một dự án cần cả thư mục chuẩn và thư mục fixture bổ sung:

~~~xml
<build>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
            <filtering>false</filtering>
        </testResource>
        <testResource>
            <directory>src/test-extra/resources</directory>
            <filtering>false</filtering>
        </testResource>
    </testResources>
</build>
~~~

Đây là **fragment minh họa**, không phải toàn bộ pom.xml. Khi ghép vào POM ở mục 7, đặt **testResources** trong cùng block **build** đã chứa plugins; không tạo hai block build song song trong một POM. Khai báo danh sách testResources tường minh có thể **thay thế** danh sách default, nên cần giữ thư mục src/test/resources nếu vẫn muốn dùng nó.

Trong Maven, **build/resources** (cho main) và **build/testResources** (cho test) là hai phần riêng. Đưa thư mục fixture vào **build/resources** sẽ khiến nó có mặt trong target/classes và có nguy cơ lọt vào artifact.

### 11.3. Custom copy task và generated resources

Một số dự án tạo tài nguyên từ template hoặc file sinh tự động. Cần xác định **đích output** của task sinh tài nguyên:

- File dùng production: tạo vào nơi thuộc main resources output, đăng ký task dependency đúng, đảm bảo deterministic.
- File chỉ dùng test: tạo vào nơi thuộc test resources output và để test task phụ thuộc task sinh file.
- Không tạo chung một thư mục output rồi đưa cả thư mục đó vào **bootJar** nếu chứa đồng thời cấu hình production và fixture test.

Ví dụ Gradle có thể thêm generated test resources qua sourceSet test và task Copy được quản lý. Với quy trình phức tạp, cần tránh nhiều task cùng ghi chung một output directory vì làm Gradle incremental build/up-to-date checking khó chính xác.

## 12. Resource filtering và việc dùng dữ liệu mẫu

### Maven resources filtering

Maven Resources Plugin có tính năng **filtering** để thay token bằng property khi copy resource. Tùy cấu hình, filtering của **resources** và **testResources** có thể khác nhau. Nếu một tệp test cần giá trị riêng, đặt nó trong testResources với filtering phù hợp; đừng copy bản đã filter dùng test sang target/classes.

Nếu file là binary, JSON chứa placeholder không intended hoặc file cần giữ byte nguyên vẹn, nên cân nhắc **filtering=false** cho resource đó. Tránh dùng filtering với dữ liệu nhạy cảm thật trong repository.

### Gradle expand/filter

Gradle **processResources** và **processTestResources** là các copy task riêng. Ví dụ một fragment dùng khi thật sự cần thay giá trị test-only:

~~~groovy
tasks.named('processTestResources') {
    filesMatching('test-settings.properties') {
        expand(testLabel: 'TEST_ONLY')
    }
}
~~~

Đoạn này chỉ tác động lên file **test-settings.properties** nằm trong nguồn test resource. Không tác động đến **processResources** của main. Nếu resource không chứa template cần expand, không cần thêm block đó. Những tệp có cú pháp **$** hoặc dấu ngoặc trùng với Gradle template có thể cần escape khi dùng expand; giữ resource nguyên dạng là lựa chọn đơn giản hơn nếu không cần filtering.

### Tránh lộ dữ liệu nhạy cảm

Bản thân việc tách thư mục không bảo vệ thông tin đã lỡ đưa vào main JAR hoặc dependency JAR. Đừng commit mật khẩu, token hay dữ liệu người dùng thật vào resource, kể cả test fixture. Dùng secret store/env vars và fixture giả trong kiểm thử. Kiểm tra artifact cuối cùng trước khi phát hành.

## 13. Những sai lầm thường gặp

**Lỗi 1 — Để fixtures dưới src/main/resources vì test đọc được.** Test chạy xanh nhưng file bị đóng vào production JAR. Chuyển fixture thật sự test-only sang **src/test/resources**.

**Lỗi 2 — Tin application-test.properties tự động bị loại.** Tên profile không quyết định scope. Tệp đặt trong **src/main/resources** vẫn thuộc main; tệp đặt trong **src/test/resources** thuộc test.

**Lỗi 3 — SpringBootTest không áp dụng cấu hình test.** Kiểm tra **@ActiveProfiles("test")**, đường dẫn và chính tả **application-test.properties**, test classpath và các nguồn override property khác. Chỉ có src/test/resources không tự kích hoạt profile.

**Lỗi 4 — Dùng test dependency scope để loại resource khỏi package.** Maven scope test hoặc Gradle testImplementation kiểm soát dependency, không làm thay đổi vị trí resource source set. Cần sửa đúng thư mục.

**Lỗi 5 — Gradle sourceSets.main.resources trỏ tới src/test/resources.** Cấu hình này biến fixture thành main resource; **bootJar** có thể đóng gói nó. Chuyển đường dẫn đó sang sourceSets.test.resources.

**Lỗi 6 — Maven build/resources trỏ tới thư mục test.** process-resources copy fixture vào target/classes, sau đó JAR chứa fixture. Sửa block resources/testResources đúng mục đích.

**Lỗi 7 — Tự viết bootJar.from(sourceSets.test.output).** Điều này có thể ép các class/test fixtures vào executable JAR, vượt qua phân chia mặc định. Bỏ custom copy không cần thiết; xác minh archive sau khi sửa.

**Lỗi 8 — Dùng cùng tên/đường dẫn resource ở main và test rồi phụ thuộc vào thứ tự ưu tiên.** Trùng đường dẫn làm việc resolve theo classloader/classpath dễ khó hiểu, nhất là khi plugin hoặc IDE có cách tạo classpath khác. Dùng **application-test.properties** với profile rõ ràng và đặt fixture dưới **fixtures/**.

**Lỗi 9 — Coi target/test-classes hoặc build/resources/test trên đĩa là bằng chứng JAR bị bẩn.** Đây là output hợp lệ để chạy test. Cần kiểm tra thực tế entry bên trong executable JAR.

**Lỗi 10 — Chạy java -jar rồi truy cập đường dẫn src/main/resources dưới filesystem.** File đã nằm trong archive, không bảo đảm thư mục source còn tồn tại. Đọc qua **ClassPathResource** hoặc **ClassLoader.getResourceAsStream**.

**Lỗi 11 — Chạy jar tf trên nhầm JAR.** Gradle có thể tạo file **-plain.jar** bên cạnh Boot JAR. Chọn đúng executable Boot JAR cần triển khai và kiểm tra đường dẫn **BOOT-INF/classes/**.

**Lỗi 12 — Test pass nhưng production vẫn đọc TEST_ONLY.** Kiểm tra app.label bị override từ env, command-line arguments, cấu hình ngoài JAR hoặc profile được bật lúc chạy. Trong ví dụ, hai dòng stdout mặc định chỉ cố định khi không có override.

**Lỗi 13 — Copy cả build/ hoặc target/ vào Docker image rồi tưởng JAR chứa test.** Docker build context/image có thể chứa các file output test độc lập với JAR. Nên sao chép đúng artifact cần chạy vào image và kiểm tra Dockerfile; một JAR sạch không có nghĩa toàn bộ image không có file test.

**Lỗi 14 — Khai báo testResources tùy chỉnh làm mất folder chuẩn.** Cấu hình thay thế danh sách đường dẫn có thể bỏ qua src/test/resources nếu không liệt kê. Kiểm tra output sau process-test-resources/processTestResources.

**Lỗi 15 — Dùng exclude '**/test/**' ở bước package rồi cho rằng đã tách đúng.** Pattern tên có thể loại nhầm resource runtime hoặc bỏ sót fixtures có tên khác. Sửa phân loại từ source set là giải pháp đáng tin hơn, sau đó dùng artifact inspection để phát hiện sai sót.

## 14. Checklist kiểm tra trước khi phát hành

1. **Phân loại** từng loại resource: ứng dụng thực sự cần hay chỉ phục vụ test?
2. **Đặt đúng nơi**: production resources ở src/main/resources; test fixtures và cấu hình test-only ở src/test/resources.
3. **Không cấu hình chéo** Maven build/resources với testResources, hoặc Gradle sourceSets.main với sourceSets.test.
4. **Tách dependency test**: Maven scope test và Gradle testImplementation cho JUnit/Spring Boot test tools.
5. **Kích hoạt profile test rõ ràng** bằng @ActiveProfiles hoặc test property mechanism phù hợp; không trông chờ tên thư mục tự bật profile.
6. **Chạy test** và xác nhận main + test resource đều đọc được trên test classpath.
7. **Đóng gói sạch** với Maven clean verify hoặc Gradle clean test bootJar.
8. **Liệt kê archive** bằng jar tf và xác nhận resource/test class không nằm trong executable Boot JAR.
9. **Chạy artifact** bằng java -jar với runtime configuration dự kiến; xác nhận các file main được đọc từ classpath và hành vi production đúng.
10. **Kiểm tra custom task/Dockerfile** nếu chúng có thể copy fixture ra ngoài cấu trúc build mặc định.

## 15. Tài liệu tham khảo chính thức

- Maven — Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout
- Maven — Build Lifecycle (process-resources, process-test-resources, test, package): https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Getting Started (classpath resources for tests): https://maven.apache.org/guides/getting-started/
- Gradle — Building Java & JVM Projects (source sets, managing resources): https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Spring Boot — Gradle Plugin: Reacting to the Java Plugin / BootJar: https://docs.spring.io/spring-boot/gradle-plugin/reacting.html

**Ghi nhớ:** **Test có thể đọc được cả main resources và test resources; executable Spring Boot JAR mặc định chỉ đóng gói main resources cùng dependency runtime cần thiết.** Việc phân biệt **src/main/resources** với **src/test/resources** từ đầu và kiểm tra JAR thực tế giúp bài test đủ dữ liệu nhưng bản phát hành không mang theo fixture, test configuration hay mã JUnit.