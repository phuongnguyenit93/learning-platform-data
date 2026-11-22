# Tổ chức source set và thư mục nguồn tùy chỉnh trong bản dựng Spring Boot

## 1. Mục tiêu học tập

Dự án Java/Spring Boot thường dùng cấu trúc `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources`. Khi phát triển hệ thống cũ, dùng mã nguồn sinh tự động, tách tài nguyên theo nhóm hoặc bổ sung test độc lập, ta có thể cần các thư mục khác. Điều quan trọng là **khai báo chúng đúng với build tool**, hiểu chúng thuộc classpath nào, và xác nhận Java compiler, test runner, `bootRun`/`spring-boot:run` và executable JAR đều nhìn thấy dữ liệu cần thiết.

Bài này hướng dẫn:

- Ý nghĩa của **source set** trong Gradle và cấu trúc nguồn tương ứng trong Maven.
- Phân biệt nguồn Java, resource, test source và test resource.
- Thêm hoặc thay thế thư mục nguồn bằng Gradle Groovy DSL/Kotlin DSL.
- Bổ sung Java source roots và resource roots của Maven mà vẫn giữ cấu trúc chuẩn.
- Kiểm tra luồng `compileJava`/`processResources`, `test` và Spring Boot packaging.
- Quản lý generated sources, test suite riêng, IDE sync và các lỗi thường gặp.

**Giới hạn:** một ứng dụng Spring Boot Java, có thể mở rộng cho multi-module. Ví dụ dùng Java 17 và Spring Boot 3.3.13 làm mốc minh họa; dự án thực tế phải dùng version/JDK/Gradle wrapper hoặc Maven version được xác nhận trong repository. Không nhất thiết cấu hình tùy chỉnh khi Maven/Gradle convention đã đáp ứng yêu cầu.

## 2. Quy ước mặc định trước khi tùy chỉnh

### 2.1. Cây thư mục tiêu chuẩn

~~~text
source-layout-demo/
├── build.gradle                   # Gradle Groovy DSL
│   hoặc build.gradle.kts          # Gradle Kotlin DSL
│   hoặc pom.xml                   # Maven
├── settings.gradle                # Chỉ Gradle, nếu dùng Groovy DSL
│   hoặc settings.gradle.kts       # Gradle Kotlin DSL
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/demo/LayoutApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        ├── java/
        │   └── com/example/demo/LayoutApplicationTest.java
        └── resources/
            └── test-data.txt
~~~

Đây là **sơ đồ lựa chọn**, không yêu cầu cùng lúc có `pom.xml` và cả hai dạng build Gradle. Khi dùng Gradle, chọn `build.gradle` + `settings.gradle` **hoặc** `build.gradle.kts` + `settings.gradle.kts`; khi dùng Maven, chọn `pom.xml`.

Bảng ý nghĩa:

| Thư mục | Vai trò | Thường đi vào đâu? |
| --- | --- | --- |
| `src/main/java` | Source Java của sản phẩm | Main classes; JAR/WAR ứng dụng sau khi biên dịch |
| `src/main/resources` | Cấu hình, template, dữ liệu classpath | Main resources; thường đi vào executable archive |
| `src/test/java` | Mã Java kiểm thử | Test classes và test runtime, không đóng vào Boot JAR thông thường |
| `src/test/resources` | Dữ liệu phục vụ kiểm thử | Test runtime classpath; không đóng vào Boot JAR thông thường |

Cả Maven lẫn Gradle đều dựa trên quy ước này. **Source file không phải class file**: build tool biên dịch Java từ source directory, rồi đưa kết quả vào output directory. Resource thường được sao chép/xử lý theo cấu hình, không biên dịch như Java.

### 2.2. Gradle gọi đó là `SourceSet`

Với Gradle Java plugin, có hai source set mặc định:

- `main`: code/resource của ứng dụng, các configuration như `implementation`/`runtimeOnly`, output được `jar`/`bootJar` sử dụng.
- `test`: code/resource kiểm thử, configuration như `testImplementation`/`testRuntimeOnly`, output được task `test` sử dụng.

Mỗi `SourceSet` có những phần khác nhau:

| Phần | Ví dụ truy cập trong Gradle | Nội dung |
| --- | --- | --- |
| Java source roots | `sourceSets.main.java.srcDirs` | Những thư mục Gradle quét file `.java` |
| Resource roots | `sourceSets.main.resources.srcDirs` | Những thư mục Gradle lấy resource |
| Classes output | `sourceSets.main.output.classesDirs` | Thư mục class đã biên dịch (thường `build/classes/java/main`) |
| Resource output | `sourceSets.main.output.resourcesDir` | Thư mục resource sau xử lý (thường `build/resources/main`) |
| Compile classpath | `sourceSets.main.compileClasspath` | Dependencies và outputs cần khi compile |
| Runtime classpath | `sourceSets.main.runtimeClasspath` | Classes, resources, runtime dependencies khi chạy |

Trong Gradle, tạo source set mới thường sinh thêm các configuration và task compile/resource tương ứng; tuy nhiên **không tự tạo task `Test` thực thi suite tùy chỉnh** nếu bạn chỉ khai báo một source set tên mới. Xem mục 9.

### 2.3. Maven không dùng container `SourceSet` như Gradle

Maven convention cũng phân biệt main/test, nhưng quản lý qua **source roots**, `resources` và plugin/lifecycle. Ví dụ:

- Main Java từ `src/main/java`, biên dịch qua compiler plugin.
- Main resources từ `src/main/resources`, xử lý qua resources plugin.
- Test Java từ `src/test/java`, test resources từ `src/test/resources`.
- Thêm Java directories bằng `build-helper-maven-plugin` hoặc cấu hình phù hợp; có thể khai báo nhiều resource directories dưới `build/resources`.

Vì vậy, câu “thêm source set” cần hiểu theo build tool: **Gradle tạo/cấu hình SourceSet; Maven chỉnh source roots/resource roots và plugin**. Đừng cố viết `sourceSets { ... }` vào `pom.xml`.

## 3. Ví dụ ứng dụng dùng thêm thư mục ngoài quy ước

Ta muốn giữ nguyên các thư mục chuẩn và thêm:

~~~text
source-layout-demo/
├── src/
│   ├── main/
│   │   └── java/com/example/demo/LayoutApplication.java
│   ├── custom/
│   │   ├── java/com/example/demo/ExtraGreeting.java
│   │   └── resources/greeting.txt
│   └── test-support/
│       ├── java/com/example/demo/ExtraGreetingTest.java
│       └── resources/test-marker.txt
├── build.gradle          # hoặc build.gradle.kts
└── settings.gradle       # hoặc settings.gradle.kts
~~~

Ở đây:

- `LayoutApplication.java` vẫn nằm trong root chuẩn của source set `main`.
- `ExtraGreeting.java` nằm trong **main Java root bổ sung** `src/custom/java`.
- `greeting.txt` nằm trong **main resource root bổ sung** `src/custom/resources`.
- `ExtraGreetingTest.java` và `test-marker.txt` là **test-only**; không được vô tình đóng vào production archive.
- Không có file Java hay resource nào cần chuyển sang output directory bằng thao tác copy thủ công trước mỗi lần build.

Mục tiêu kiểm tra: khi chạy ứng dụng, Spring Boot có thể tạo bean `ExtraGreeting` và đọc `greeting.txt`; khi chạy test, JUnit thấy lớp test từ thư mục bổ sung và đọc được `test-marker.txt`.

## 4. Gradle: thêm source roots mà không mất đường dẫn mặc định

### 4.1. Groovy DSL — `build.gradle` hoàn chỉnh

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'source-layout-demo'
~~~

Tệp `build.gradle`:

~~~groovy
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

sourceSets {
    main {
        java {
            srcDir 'src/custom/java'
        }
        resources {
            srcDir 'src/custom/resources'
        }
    }

    test {
        java {
            srcDir 'src/test-support/java'
        }
        resources {
            srcDir 'src/test-support/resources'
        }
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Script này **giữ** `src/main/java`/`src/main/resources` và `src/test/java`/`src/test/resources` vì `srcDir` **thêm một root** vào tập hợp mặc định. Spring Boot starter được dùng để có một ứng dụng console, không cần web server; test starter cung cấp JUnit/Spring Test.

### 4.2. Kotlin DSL — `build.gradle.kts` tương đương

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "source-layout-demo"
~~~

Tệp `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

sourceSets {
    named("main") {
        java.srcDir("src/custom/java")
        resources.srcDir("src/custom/resources")
    }

    named("test") {
        java.srcDir("src/test-support/java")
        resources.srcDir("src/test-support/resources")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Hai cấu hình Gradle chỉ khác cú pháp DSL, cùng có Java toolchain 17, cùng dependency management và cùng source roots. Trong Kotlin DSL, `named("main")`/`named("test")` chỉ rõ source set hiện hữu; dùng typed `Test` cho task có `useJUnitPlatform()`.

**Đối chiếu đúng hành vi:** nên dùng cùng phiên bản Gradle wrapper, JDK, dependency repository và Spring Boot plugin khi so sánh hai script. Không đặt cả `build.gradle` và `build.gradle.kts` cạnh nhau trong cùng một module rồi coi đó là hai nguồn cấu hình build được chạy nối tiếp.

## 5. Mã Java/resource để xác nhận cấu hình thực sự hoạt động

### 5.1. Main class ở thư mục chuẩn

Tạo `src/main/java/com/example/demo/LayoutApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayoutApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyExtraSource(ExtraGreeting greeting) {
        return args -> System.out.println("CUSTOM_SOURCE=" + greeting.getMessage());
    }
}
~~~

`ExtraGreeting` chưa nằm trong `src/main/java`, nên nếu quên đăng ký `src/custom/java`, compiler sẽ không tìm được class khi biên dịch `LayoutApplication`. Đây là **bằng chứng thực tế** để kiểm tra cấu hình source root.

### 5.2. Class ở main Java root tùy chỉnh

Tạo `src/custom/java/com/example/demo/ExtraGreeting.java`:

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

import org.springframework.stereotype.Component;

@Component
public class ExtraGreeting {

    public String getMessage() {
        try (InputStream stream =
                 ExtraGreeting.class.getResourceAsStream("/greeting.txt")) {
            if (stream == null) {
                throw new IllegalStateException("greeting.txt is not on the classpath");
            }
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8).strip();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

Java 17 hỗ trợ `InputStream.readAllBytes()` và `String.strip()`. `@Component` khiến Spring Boot component scan nhận class nếu nó đã được compile và nằm trong package con của `com.example.demo`. Trường hợp file nguồn nằm trong root tùy chỉnh nhưng package khai báo không thuộc vùng component scan, compile có thể thành công nhưng Spring vẫn không tạo bean; hai vấn đề cần phân biệt.

### 5.3. Resource chính từ thư mục tùy chỉnh

Tạo file văn bản UTF-8 `src/custom/resources/greeting.txt` chỉ có một dòng:

~~~text
xin-chao-tu-custom
~~~

Trong code, `getResourceAsStream("/greeting.txt")` tìm resource **theo tên trên classpath**, không theo đường dẫn vật lý `src/custom/resources/greeting.txt`. `processResources` sẽ đưa file này về một root resource output; khi đóng gói Boot JAR, nó được đặt ở classpath của ứng dụng.

Do dùng `.strip()`, một dấu xuống dòng cuối file vẫn cho cùng thông điệp.

### 5.4. Test Java và resource kiểm thử bổ sung

Tạo `src/test-support/java/com/example/demo/ExtraGreetingTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class ExtraGreetingTest {

    @Autowired
    private ExtraGreeting greeting;

    @Test
    void loadsExtraJavaAndMainResource() {
        assertEquals("xin-chao-tu-custom", greeting.getMessage());
    }

    @Test
    void loadsAdditionalTestResource() {
        assertNotNull(getClass().getResourceAsStream("/test-marker.txt"));
    }
}
~~~

Ở test thứ hai, lấy resource stream chỉ để kiểm tra tồn tại; với code production, nên đóng stream sau khi sử dụng để tránh rò rỉ. Để mẫu kiểm thử cũng quản lý resource tốt, thay phương thức thứ hai bằng:

~~~java
@Test
void loadsAdditionalTestResource() throws Exception {
    try (var stream = getClass().getResourceAsStream("/test-marker.txt")) {
        assertNotNull(stream);
        assertEquals(
                "TEST_ONLY",
                new String(stream.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).strip()
        );
    }
}
~~~

**Chỉ sử dụng một phiên bản của `loadsAdditionalTestResource` trong class test**: bản đầu minh họa ý tưởng nhanh; bản thứ hai là phiên bản nên giữ trong file thực tế. Tệp `src/test-support/resources/test-marker.txt`:

~~~text
TEST_ONLY
~~~

Nếu chỉ muốn một file test hoàn chỉnh, dùng class ở trên nhưng thay đúng phương thức kiểm tra resource bằng phiên bản `try-with-resources`. Không ghép hai phương thức trùng tên cùng tham số.

### 5.5. Chạy và kết quả cần thấy

Dùng Gradle wrapper của dự án nếu có (Linux/macOS):

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

Lệnh thứ hai khởi động ứng dụng không có web server; log khởi động còn nhiều dòng nhưng bạn phải thấy **một dòng do ứng dụng tự in**:

~~~text
CUSTOM_SOURCE=xin-chao-tu-custom
~~~

Nếu cần kiểm tra artifact production:

~~~bash
./gradlew bootJar
java -jar build/libs/source-layout-demo-1.0.0.jar
~~~

Tên file dựa trên project name/version và convention Boot JAR trong cấu hình ví dụ. Với Windows PowerShell, dùng `.\gradlew.bat`. Nếu dự án chưa có wrapper, cần chuẩn bị wrapper hợp lệ hoặc Gradle đã được cài tương thích. Không tự giả định `gradlew` xuất hiện chỉ vì có build.gradle.

Khi chạy `./gradlew test`, JUnit cần phát hiện **2 test methods** của `ExtraGreetingTest`. Khi chạy `bootRun`/executable JAR, output ứng dụng vẫn có `CUSTOM_SOURCE=...`. File `test-marker.txt` chỉ dành cho test runtime, không được đóng trong Boot JAR theo cấu hình chuẩn.

## 6. `srcDir` khác `setSrcDirs`: thêm hay thay thế toàn bộ?

Đây là lỗi thay đổi hành vi phổ biến nhất.

### 6.1. Thêm một đường dẫn

**Groovy:**

~~~groovy
sourceSets {
    main {
        java.srcDir 'src/custom/java'
        resources.srcDir 'src/custom/resources'
    }
}
~~~

**Kotlin:**

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir("src/custom/java")
        resources.srcDir("src/custom/resources")
    }
}
~~~

`srcDir` là thao tác **append**, nên Gradle vẫn giữ các đường dẫn convention đã có trong `main`. Nếu cần nhiều root:

~~~groovy
sourceSets {
    main {
        java {
            srcDir 'src/custom/java'
            srcDir 'src/legacy/java'
        }
    }
}
~~~

Hai đường dẫn bổ sung được đưa vào Java source roots; file Java ở các root đó được biên dịch như một phần của cùng `main` source set.

### 6.2. Thay thế các root mặc định

**Groovy:**

~~~groovy
sourceSets {
    main {
        java.srcDirs = ['code/java', 'generated/java']
        resources.srcDirs = ['config/resources']
    }
}
~~~

**Kotlin:**

~~~kotlin
sourceSets {
    named("main") {
        java.setSrcDirs(listOf("code/java", "generated/java"))
        resources.setSrcDirs(listOf("config/resources"))
    }
}
~~~

`srcDirs = ...` (Groovy) hoặc `setSrcDirs(...)` (Kotlin) là thao tác **replace** danh sách. Nếu không liệt kê `src/main/java`/`src/main/resources`, Gradle sẽ **không còn quét những root đó** bằng `main` mặc định.

Thay thế có ích khi chuyển hẳn sang layout khác; nếu chỉ muốn bổ sung, dùng `srcDir`. Không dùng `setSrcDirs` rồi ngạc nhiên vì `LayoutApplication.java` biến mất khỏi compilation.

### 6.3. Không đổi tên source set khi chỉ đổi thư mục

Một source set mới tên `custom` không có cùng ý nghĩa với việc thêm `src/custom/java` vào `main`:

~~~groovy
sourceSets {
    custom {
        java.srcDir 'src/custom/java'
    }
}
~~~

Đoạn trên **tạo source set độc lập** `custom` thay vì thêm class vào `main`. Nó có output/classpaths/configurations riêng và không tự động trở thành một phần của `main` hay `bootJar`. Nếu `LayoutApplication` dùng `ExtraGreeting` từ `custom` mà bạn chưa cấu hình dependency giữa các source sets, main compilation có thể không tìm thấy class.

**Quy tắc:** code thuộc cùng ứng dụng/production classpath thì thêm root vào `main`; chỉ tạo source set độc lập khi thật sự cần mô hình classpath/lifecycle tách biệt.

## 7. Từ source roots đến output: task nào làm việc gì?

Trong Gradle Java plugin:

~~~text
main.java.srcDirs
    ↓ compileJava
build/classes/java/main/
    ↓
    ├───────────────┐
main.resources      │
    ↓ processResources
build/resources/main/
    ↓               │
    └─ classes ◄────┘       (lifecycle task phụ thuộc kết quả cần thiết)
         ↓
main.output + runtimeClasspath
         ↓
bootRun / bootJar
~~~

Quan hệ trên minh họa luồng đầu ra; task graph thực tế còn các dependency/optimization khác. `classes` tổng hợp compilation và resource processing, không phải task “đọc trực tiếp tất cả file Java/resource”.

Với source set `test`:

~~~text
test.java.srcDirs       → compileTestJava → build/classes/java/test/
test.resources.srcDirs  → processTestResources → build/resources/test/
                      ↓
              test.output + test.runtimeClasspath
                      ↓
                    test
~~~

Test classpath thường bao gồm main output và các test dependencies. Vì thế test có thể truy cập `ExtraGreeting` và `greeting.txt` trong main classpath, cộng thêm `test-marker.txt` trong test resources.

Khi Spring Boot Gradle Plugin tạo `bootJar`, nó lấy classes/resources cùng runtime dependencies của **main source set** theo cấu hình chuẩn. `test` output không tự đóng vào executable archive. `bootRun` cũng mặc định dùng main runtime classpath. Đặt source roots nhầm dưới `test` có thể tạo tình huống test pass nhưng production `bootJar` thiếu class/resource.

### 7.1. Nơi output thường nằm

| Loại | Gradle | Maven |
| --- | --- | --- |
| Main compiled Java | `build/classes/java/main` | `target/classes` |
| Main processed resources | `build/resources/main` | `target/classes` |
| Test compiled Java | `build/classes/java/test` | `target/test-classes` |
| Test processed resources | `build/resources/test` | `target/test-classes` |
| Spring Boot executable JAR | `build/libs/*.jar` từ `bootJar` | `target/*.jar` sau `repackage` |

Đây là convention với plugin phổ biến; outputDirectory/destinationDirectory, classifier và custom plugin có thể thay đổi. **Không đặt output build vào source root**, vì làm thế dễ khiến class hoặc resource sinh ra bị compiler/resource task đọc lại ở các lần build sau.

### 7.2. Kiểm tra ở command line

~~~bash
./gradlew clean compileJava processResources
./gradlew compileTestJava processTestResources
./gradlew test
./gradlew bootJar
~~~

Sau đó quan sát:

~~~text
build/classes/java/main/com/example/demo/ExtraGreeting.class
build/resources/main/greeting.txt
build/classes/java/test/com/example/demo/ExtraGreetingTest.class
build/resources/test/test-marker.txt
~~~

Với ví dụ có tên `source-layout-demo`, executable JAR thường là `build/libs/source-layout-demo-1.0.0.jar`. Kiểm tra nội dung JAR:

~~~bash
jar tf build/libs/source-layout-demo-1.0.0.jar
~~~

Tìm các entry `BOOT-INF/classes/com/example/demo/ExtraGreeting.class` và `BOOT-INF/classes/greeting.txt`. Không nên có `ExtraGreetingTest.class` hay `test-marker.txt` trong production Boot JAR. Nếu có, kiểm tra việc nguồn test đã bị thêm nhầm vào `main` hay copy thủ công vào archive.

Lệnh `jar tf` yêu cầu JDK có công cụ `jar`, và đường dẫn file phải đúng với output thực tế. Nếu file bị đổi tên, liệt kê `build/libs` trước.

## 8. Maven: thêm thư mục nguồn và resource tương đương

### 8.1. Khác biệt cốt lõi với Gradle

Maven mặc định lấy Java code từ `src/main/java` và `src/test/java`. Trong POM, `build/sourceDirectory` và `build/testSourceDirectory` cho phép đặt **một main source root và một test source root**, nhưng việc gán chúng thường **thay** đường dẫn chuẩn. Muốn giữ `src/main/java` mà **thêm** `src/custom/java`, nên dùng plugin để đăng ký source root bổ sung đúng lifecycle, ví dụ `build-helper-maven-plugin`.

Resources thì Maven cho phép liệt kê nhiều `<resource>` trong `build/resources` và nhiều `<testResource>` trong `build/testResources`. Khi tự khai báo collection resources, phải nhớ **giữ lại root chuẩn nếu vẫn cần**.

### 8.2. Cấu hình Maven `pom.xml` hoàn chỉnh

Ví dụ này dùng Spring Boot starter parent 3.3.13, JDK 17 và Build Helper Maven Plugin 3.6.2. Nó áp dụng **cùng cây source/data ở mục 3–5**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>source-layout-demo</artifactId>
    <version>1.0.0</version>

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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
            </resource>
            <resource>
                <directory>src/custom/resources</directory>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>src/test/resources</directory>
            </testResource>
            <testResource>
                <directory>src/test-support/resources</directory>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>extra-main-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>src/custom/java</source>
                            </sources>
                        </configuration>
                    </execution>

                    <execution>
                        <id>extra-test-java</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>add-test-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>src/test-support/java</source>
                            </sources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **POM hoàn chỉnh**, có thể dùng với source Java và resource của ví dụ. Nó khác Gradle ở cách thêm root, nhưng cùng đưa source Java tùy chỉnh vào main/test compilation và đưa resource vào classpath tương ứng.

**Vì sao chọn phase `generate-sources` và `generate-test-sources`?** Build Helper đăng ký root trước các phase `compile`/`test-compile`, nên compiler thấy source khi chạy lifecycle. Tương tự, resource được Maven Resources Plugin xử lý trong các phase resource tương ứng.

**Vì sao khai báo `spring-boot-maven-plugin`?** Parent Spring Boot cung cấp plugin configuration/execution repackage; module ứng dụng khai báo plugin để Maven tạo executable archive khi `package`. Không cần dùng Goal Gradle `bootJar` trong Maven project.

**Cần nhớ về resource filtering:** khi tự viết `<build><resources>...` bạn thay tập cấu hình resources được kế thừa/mặc định theo POM. Ứng dụng nào có filtering cho `application.properties`/`application.yml` hoặc exclusions đặc biệt phải tái hiện đúng rules đó. Ví dụ này dùng text resource thuần không yêu cầu filtering.

### 8.3. Khi nào `sourceDirectory` đủ, khi nào phải thêm plugin?

Nếu muốn **chuyển hẳn** main Java từ `src/main/java` sang `code/java`, Maven có thể dùng:

~~~xml
<build>
    <sourceDirectory>code/java</sourceDirectory>
</build>
~~~

Đây chỉ là đoạn POM bổ sung vào build hiện hữu. Hậu quả: compiler chủ yếu đọc `code/java` như main source root; đừng mong `src/main/java` còn được compile chỉ vì nó vẫn tồn tại trên đĩa.

Nếu muốn **thêm** `code/java` nhưng vẫn giữ `src/main/java`, `sourceDirectory` không diễn đạt đúng tập nhiều root; sử dụng `build-helper:add-source` hoặc plugin có hợp đồng tương đương.

Tương tự `testSourceDirectory` thay test source root chuẩn, còn `build-helper:add-test-source` thêm root. Cần cân nhắc test naming và Maven Surefire/Failsafe khi thêm một bộ test riêng: thêm test source root **không tự tạo lifecycle test suite tách biệt**.

### 8.4. Chạy Maven và kiểm tra output

Trong thư mục có `pom.xml`:

~~~bash
mvn -version
mvn clean test
mvn package
java -jar target/source-layout-demo-1.0.0.jar
~~~

Nếu repository đã có Maven wrapper, thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (PowerShell). File `pom.xml` tự nó không sinh Maven wrapper.

Khi class được thêm đúng, Maven compile `ExtraGreeting.java` và test compile `ExtraGreetingTest.java`. Đầu ra thường thấy:

~~~text
target/classes/com/example/demo/ExtraGreeting.class
target/classes/greeting.txt
target/test-classes/com/example/demo/ExtraGreetingTest.class
target/test-classes/test-marker.txt
target/source-layout-demo-1.0.0.jar
~~~

Sau khi ứng dụng chạy, dòng do `CommandLineRunner` in là:

~~~text
CUSTOM_SOURCE=xin-chao-tu-custom
~~~

Dùng `jar tf target/source-layout-demo-1.0.0.jar` và tìm `BOOT-INF/classes/com/example/demo/ExtraGreeting.class` và `BOOT-INF/classes/greeting.txt`. `ExtraGreetingTest.class`/`test-marker.txt` thường không nằm trong JAR ứng dụng.

Muốn xem mô hình POM sau kế thừa:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM giúp kiểm tra plugin executions và resource definitions. Tuy vậy, source root được Build Helper đăng ký **khi goal chạy trong lifecycle**, nên chỉ nhìn POM không phải bằng chứng đủ; kiểm tra log `build-helper:add-source`/`add-test-source` và output classes sau `mvn clean test`.

## 9. Source set độc lập cho integration tests

Đến đây, `src/test-support/java` trong ví dụ là **thư mục bổ sung của source set `test`**. Nó được chạy chung với unit test theo task `test`. Khi một nhóm kiểm thử cần dependency hoặc vòng đời riêng (ví dụ integration tests phải có database/testcontainers), hãy cân nhắc **source set riêng**.

### 9.1. Chỉ thêm test root khác với tạo suite mới

| Nhu cầu | Cách Gradle phù hợp | Cần cấu hình thêm? |
| --- | --- | --- |
| Test helpers cùng classpath với unit tests | Thêm `src/test-support/java` vào `sourceSets.test` | Không cần task Test mới |
| Integration tests dùng classpath/lifecycle riêng | Tạo source set `integrationTest` và task `Test` tương ứng, hoặc JVM Test Suite plugin | Có; dependency classpath và task |
| Test Java được biên dịch nhưng không chạy | Chỉ tạo source set mới | Chưa có task runner; phải cấu hình |
| Test Gradle cần chạy trong `build` | Nối task integrationTest vào `check` | Có; tránh tự giả định |

Một ví dụ **fragment Kotlin DSL** bổ sung sau các plugin Java/Spring Boot trong `build.gradle.kts`:

~~~kotlin
val integrationTest by sourceSets.creating {
    java.setSrcDirs(listOf("src/it/java"))
    resources.setSrcDirs(listOf("src/it/resources"))
    compileClasspath += sourceSets["main"].output
    runtimeClasspath += output + compileClasspath
}

configurations[integrationTest.implementationConfigurationName]
    .extendsFrom(configurations["testImplementation"])

configurations[integrationTest.runtimeOnlyConfigurationName]
    .extendsFrom(configurations["testRuntimeOnly"])

tasks.register<Test>("integrationTest") {
    description = "Runs integration tests"
    group = "verification"

    testClassesDirs = integrationTest.output.classesDirs
    classpath = integrationTest.runtimeClasspath
    shouldRunAfter(tasks.named("test"))
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(tasks.named("integrationTest"))
}
~~~

Điều kiện: build đã áp dụng Java plugin, có source set `main`/`test` và có test engine/dependencies thích hợp. Nếu tạo suite mới bằng `integrationTest`, sẽ có configuration dạng `integrationTestImplementation` và `integrationTestRuntimeOnly`. Mẫu trên cho chúng kế thừa dependencies kiểm thử đang có; dự án thật có thể muốn tách dependency và cơ sở dữ liệu riêng.

`shouldRunAfter` là **ràng buộc thứ tự mềm**, không tạo dependency: task integration vẫn chỉ chạy khi được yêu cầu hoặc `check` phụ thuộc nó. `dependsOn` mới khiến integration test tham gia lifecycle `check`. Nếu không muốn integration tests chạy ở mọi `build`, bỏ kết nối với `check` và gọi `./gradlew integrationTest` riêng.

Đây là **cấu hình mở rộng tùy chọn**, không cần cho ví dụ nguồn tùy chỉnh ở mục 4–5. Nó cũng có thể được thực hiện bằng Gradle JVM Test Suite Plugin; chọn một mô hình phù hợp với chính sách kiểm thử, không chồng nhiều cách tạo cùng tên source set/task.

### 9.2. Maven integration test khác Gradle source set

Maven dùng Surefire/Failsafe và lifecycle để phân biệt unit/integration tests. `build-helper:add-test-source` chỉ bổ sung source root vào **test compilation**, không tự tạo task/phases kiểu Gradle source set mới và không tự cấu hình Failsafe để phân loại `*IT.java`. Nếu dự án muốn test suite riêng, cần thiết kế Failsafe executions, naming patterns, profiles và môi trường chạy theo yêu cầu.

Không nên bỏ integration tests vào main source root chỉ để compiler tìm được import. Làm như vậy có thể mang test code/dependencies vào executable JAR và làm sai ranh giới giữa source production với test.

## 10. Generated sources và generated resources

Code/resource tạo bởi annotation processors, OpenAPI generator, protobuf, template engine hoặc task tùy chỉnh thường **không nên commit trực tiếp vào `src/main/java` hoặc sinh ra ngay trong source root do con người quản lý**. Đặt output dưới `build/generated/...` (Gradle) hoặc `target/generated-sources/...` (Maven), rồi để task/plugin đăng ký source root trước compilation.

### 10.1. Gradle: đường dẫn output phải có task dependency

Ví dụ về **generated resource** có thể bổ sung vào `build.gradle.kts`:

~~~kotlin
val prepareGeneratedResources by tasks.registering(Copy::class) {
    from("src/templates")
    into(layout.buildDirectory.dir("generated/resources/main"))
}

sourceSets.named("main") {
    resources.srcDir(prepareGeneratedResources)
}
~~~

Đây là fragment cho project có Java plugin; cần tạo thư mục input `src/templates` với những file được phép copy. Khi `resources.srcDir` nhận `TaskProvider`, Gradle có thông tin producer và output của task để xử lý dependency. Đích `build/generated/resources/main` thuộc build output; không đưa output trở lại `src/main/resources`.

Bản Groovy tương đương:

~~~groovy
def prepareGeneratedResources = tasks.register('prepareGeneratedResources', Copy) {
    from 'src/templates'
    into layout.buildDirectory.dir('generated/resources/main')
}

sourceSets {
    main {
        resources.srcDir prepareGeneratedResources
    }
}
~~~

Nếu output của generator là **file Java**, đăng ký directory producer vào `sourceSets.main.java` và đảm bảo `compileJava` có dependency đúng với task tạo sources. Dùng `TaskProvider`/task outputs thay vì chỉ gắn đường dẫn đến thư mục chưa sinh ra; cách chỉ dùng string path có thể khiến build chạy thiếu thứ tự và báo class không tồn tại.

### 10.2. Maven: plugin tạo mã trước compile

Maven có các phase `generate-sources` và `generate-test-sources` trước `compile`/`test-compile`. Nhiều generator plugin đã tự đăng ký source root; nếu không, có thể dùng `build-helper:add-source` trỏ tới output ở `target/generated-sources/...`. Nhưng chỉ thêm root **không tự chạy generator**; vẫn phải cấu hình goal sinh mã và thứ tự thực thi.

Không nên chạy code generator bằng script thủ công trước `mvn compile` rồi coi đó là quy trình build đủ tin cậy: trên CI máy sạch output sẽ không tồn tại. Mục tiêu là **clean build từ source đầu vào** vẫn tự tạo đủ generated source/resource.

## 11. Spring Boot configuration và resource overrides

### 11.1. Resource classpath không phải đường dẫn nguồn

Với `src/custom/resources/greeting.txt`, code runtime gọi `getResourceAsStream("/greeting.txt")`. Với Spring Boot, các file `application.properties` hoặc `application.yml` cũng thường nằm trong classpath (hoặc một vị trí external config được Spring Boot hỗ trợ), nhưng **đường dẫn thư mục nguồn không trực tiếp là tên resource**.

Ví dụ thêm `src/custom/resources` vào main có thể khiến `src/custom/resources/application.yml` được đưa vào cùng classpath với `src/main/resources/application.yml`. Nếu hai root chứa **cùng relative path**, copy task có thể xử lý duplicate bằng quy tắc hoặc báo lỗi tùy Gradle/Maven/plugin; đừng dựa vào thứ tự root mơ hồ để chọn “file thắng”.

Với cấu hình Spring Boot, hãy giữ **một nguồn rõ ràng** cho một tài nguyên logical khi có thể, hoặc thiết kế profile/config import đúng cách. Không vô tình tạo hai `application.properties` ở hai root rồi đoán precedence trong archive.

### 11.2. Resource filtering và secrets

- Gradle `processResources` mặc định chủ yếu copy resources; nếu muốn template substitution, phải cấu hình cụ thể `processResources` và các inputs cần theo dõi.
- Maven Resources Plugin hỗ trợ filtering qua `<filtering>true</filtering>`; starter parent có thể có cấu hình mặc định riêng. Nếu thay `build/resources`, cần kiểm tra lại các rule filtering/excludes của dự án.
- Không đưa token, mật khẩu, private key hoặc config môi trường nhạy cảm vào `src/main/resources` hoặc custom main resource root rồi phát hành cùng Boot JAR.
- Test fixtures và mock credentials chỉ được đặt ở `test resources` và không được vô tình copy sang main output.

Đóng gói executable JAR/WAR có thể đưa tài nguyên trực tiếp vào artifact; bất kỳ ai có file JAR cũng có thể giải nén xem nhiều nội dung. Việc “không lộ trong source” không bảo đảm nội dung được bảo mật sau packaging.

## 12. IDE, build cache và đường dẫn phụ thuộc máy

Gradle/Maven IDE integration thường đọc source roots từ **build model đã sync**, không chỉ từ việc bạn đánh dấu thư mục bằng giao diện.

- **IntelliJ IDEA:** Reload All Gradle Projects hoặc Reload Maven Projects sau khi sửa DSL/POM; kiểm tra module sources/resources và test roots được IDE nhận diện.
- **Eclipse/STS:** Refresh Gradle Project (Buildship) hoặc Maven Update Project (m2e); kiểm tra Java Build Path sau khi build tool đã cập nhật.
- **VS Code:** Java/Maven/Gradle extensions cần hoàn tất import; kiểm tra Java Projects và log của extension nếu thư mục custom báo đỏ.

Không sửa classpath IDE bằng tay rồi quên cập nhật build script. Cấu hình IDE thủ công có thể giúp editor hết đỏ trong chốc lát nhưng `./gradlew clean build` hoặc `mvn clean verify` trên CI vẫn thất bại.

Khi di chuyển thư mục, tránh absolute path như `C:\Users\me\project\src\custom` hoặc `/home/me/work` trong build.gradle/pom.xml. Chọn path tương đối từ module root hoặc Gradle layout/Maven project directory để đồng nghiệp và CI dựng lại được. Đường dẫn `../shared/src` trỏ sang một module khác là một dấu hiệu nên cân nhắc **project/module dependency** thay vì biên dịch chéo nguồn.

## 13. Vấn đề thường gặp và cách tìm đúng nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và xử lý |
| --- | --- | --- |
| Java class trong `src/custom/java` không được compile | Quên `main.java.srcDir` hoặc Build Helper add-source | Xem script/POM, kiểm tra `compileJava`/`mvn compile` và output class |
| Class ở `src/main/java` biến mất sau thêm custom root | Dùng `srcDirs = ...`/`setSrcDirs(...)` thay vì `srcDir` | Thêm lại default root hoặc đổi sang append |
| File `greeting.txt` không được tìm thấy | Đưa vào Java root thay vì resource root; sai relative path | Xem `processResources`/`target/classes` và đường dẫn `/greeting.txt` |
| Gradle test không thấy class test trong thư mục lạ | Chưa thêm `sourceSets.test.java.srcDir` | Cấu hình đúng test roots, kiểm tra `compileTestJava` |
| Test chạy nhưng file test-only xuất hiện trong Boot JAR | Đã thêm test resources vào `main` | Di chuyển resource về test root, rebuild sạch và kiểm tra JAR |
| Task integration test không chạy | Chỉ tạo source set mới, chưa có task `Test` hoặc lifecycle dependency | Đăng ký task, set `testClassesDirs`/`classpath` và nối `check` nếu cần |
| Maven sourceDirectory trỏ custom, source mặc định không còn | `sourceDirectory` là một root thay thế | Dùng Build Helper để thêm Java root mới nếu cần giữ cả hai |
| Maven resource custom khiến config cũ biến mất | Khai báo `<resources>` nhưng bỏ `src/main/resources` | Liệt kê đủ các resource roots và xem filtering |
| IDE thấy code nhưng CLI build không thấy | IDE đánh dấu folder thủ công nhưng build model chưa cấu hình | Đặt source roots trong script/POM và sync lại |
| CLI build được nhưng IDE chưa tìm được class | IDE import/sync chưa cập nhật | Reload Gradle/Maven project, kiểm tra JDK |
| Generated source chỉ build được sau chạy script riêng | Generator chưa được nối vào task/phase | Khai báo producer output và dependency/phase đúng |
| `bootJar` không có class dù compileTestJava có | Code đặt trong test source set thay vì main | Đưa production source vào main và rebuild |
| Resource trùng tên xuất hiện bất thường | Nhiều roots có cùng relative path | Kiểm tra duplicate handling và cấu trúc tài nguyên |
| Một máy compile được, CI máy khác không | Dùng absolute path hoặc generated file không được tạo | Dùng path relative/layout và clean build từ checkout mới |

Đừng xóa cache IDE/Gradle/Maven ngay khi có lỗi. Dùng **lệnh build và output thực tế** để xác định thư mục nguồn nào được nhìn thấy trước, rồi mới sửa đúng root/task. Xóa cache chỉ hợp lý khi đã có chứng cứ trạng thái cache làm sai kết quả.

## 14. Quy trình kiểm chứng sau khi thêm source roots

Thực hiện trong một repository sạch hoặc một bản sao dùng để học.

**Với Gradle:**

1. Đọc `build.gradle`/`build.gradle.kts` và xác định code thuộc `main` hay `test`.
2. Thêm `src/custom/java`, `src/custom/resources` vào `main` bằng `srcDir`; thêm test-only roots vào `test`.
3. Chạy `./gradlew clean compileJava processResources` và xem output dưới `build/classes/java/main` + `build/resources/main`.
4. Chạy `./gradlew clean test`, xác nhận `ExtraGreetingTest` được phát hiện và hai test methods pass.
5. Chạy `./gradlew bootJar` rồi `jar tf`, xác nhận production class/resource có trong Boot JAR và test-only resource không bị lẫn vào.
6. Chạy `java -jar`, kiểm tra dòng `CUSTOM_SOURCE=xin-chao-tu-custom`.
7. Đồng bộ lại IDE; đảm bảo IDE dùng cùng build model với wrapper/CLI.

**Với Maven:**

1. Giữ `src/main/java` và `src/test/java`; dùng Build Helper cho source roots bổ sung.
2. Khai báo cả default lẫn custom resource directories dưới `build/resources`/`build/testResources`.
3. Chạy `mvn clean test`, xem log Build Helper và output `target/classes`/`target/test-classes`.
4. Chạy `mvn package`, xác định executable archive và kiểm tra các file trong JAR.
5. Chạy `java -jar`, kiểm tra đúng dòng output ứng dụng, rồi reload Maven project trong IDE.

**Đạt yêu cầu** khi bạn giải thích được vì sao một root thuộc `main`/`test`, kết quả nào được compile/copy vào classpath, vì sao Boot archive chỉ cần main output, và có bằng chứng từ clean build, test cùng archive để xác nhận.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Trong Gradle, khác biệt giữa `java.srcDir("src/custom/java")` và `java.setSrcDirs(listOf("src/custom/java"))`?

**Đáp án:** `srcDir` bổ sung root, vẫn giữ các roots đang có. `setSrcDirs` thay toàn bộ roots bằng tập mới, có thể loại `src/main/java`.

**Câu 2.** Một Gradle source set mới tên `experimental` có tự động trở thành một phần của executable Spring Boot JAR không?

**Đáp án:** Không. Theo cấu hình chuẩn Boot JAR dùng main output/runtimeClasspath. Source set `experimental` có output/classpath riêng và chỉ trở thành đầu vào của JAR nếu build chủ động nối chúng theo mô hình cần thiết.

**Câu 3.** Đặt `application.yml` dưới `src/custom/java`, thêm Java root và chạy `bootJar`. Có chắc ứng dụng đọc được file config đó không?

**Đáp án:** Không. Java source directory chủ yếu cho file `.java`; YAML cần nằm trong resource root để được copy theo resource processing, hoặc phải có cấu hình external config được hỗ trợ.

**Câu 4.** Maven muốn giữ `src/main/java` và thêm `src/legacy/java`, có nên đặt `<sourceDirectory>src/legacy/java</sourceDirectory>` không?

**Đáp án:** Không nếu muốn giữ cả hai. `sourceDirectory` đặt một main root; dùng Build Helper `add-source` tại `generate-sources` hoặc giải pháp tương đương để thêm Java root.

**Câu 5.** Vì sao một test trong `src/test-support/java` pass nhưng class test không thấy trong Boot JAR?

**Đáp án:** Test source được compile vào test output/classpath, còn Boot JAR đóng gói main classes/resources và runtime dependencies. Đây là phân tách đúng.

**Câu 6.** Nếu generated Java files được viết dưới `build/generated/sources` nhưng `compileJava` không nhận, nên sửa gì?

**Đáp án:** Kết nối output directory của task sinh mã với main Java source set và bảo đảm compiler phụ thuộc vào producer task; không dựa vào việc generator đã chạy thủ công trước đó.

**Câu 7.** Tại sao `<resources>` trong POM không nên chỉ liệt kê `src/custom/resources` khi dự án còn dùng `src/main/resources`?

**Đáp án:** Nó có thể thay collection resource roots mặc định/được kế thừa. Muốn giữ tài nguyên cũ phải khai báo cả `src/main/resources` và đường dẫn tùy chỉnh, đồng thời kiểm tra filtering/excludes.

## 16. Tài liệu chính thức

- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Building Java & JVM Projects — Source Sets: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle Testing in Java & JVM Projects — Configuring Integration Tests: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Spring Boot Gradle Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
- Maven Resources Plugin — Specifying Resource Directories: https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html
- MojoHaus Build Helper Maven Plugin — Add Source/Test Source: https://www.mojohaus.org/build-helper-maven-plugin/usage.html

Tài liệu Gradle “current” có thể thay đổi qua các phiên bản. Trong dự án thật, nên đối chiếu theo **Gradle wrapper, Java plugin, Spring Boot plugin và Maven plugin version** mà dự án dùng. Cách tổ chức bền vững là giữ ranh giới production/test rõ ràng, để source/resource roots được định nghĩa trong build, và chứng minh bằng clean build cùng archive thực tế.
