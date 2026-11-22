# Sử dụng layout trích xuất phù hợp cho Java CDS và xác định giới hạn phiên bản

Khi triển khai Spring Boot bằng Dockerfile, bạn có thể chạy trực tiếp `java -jar app.jar`, trích xuất JAR để tối ưu cách nạp class, hoặc tạo **CDS archive** giúp JVM chia sẻ metadata class và có thể giảm thời gian khởi động/dung lượng bộ nhớ. Nhưng không phải mọi kiểu trích xuất JAR, mọi lệnh `jarmode` và mọi phiên bản Java đều hỗ trợ CDS giống nhau. Một Dockerfile trông hợp lý vẫn có thể tạo `application.jsa` không dùng được vì thiếu thư viện, classpath khác lúc chạy thật, đã thay image/JDK, hoặc sử dụng lệnh dành cho một thế hệ Spring Boot khác.

Bài học tập trung vào **Spring Boot 3.3.13 + Java 17**, giải thích cách dùng `java -Djarmode=tools -jar ... extract` để tạo layout CDS-friendly, phân biệt **extraction mặc định** với `extract --layers` để giữ Docker cache, huấn luyện CDS qua `-XX:ArchiveClassesAtExit`, chạy bằng `-XX:SharedArchiveFile`, xác minh archive thực sự được sử dụng, và nhận biết **giới hạn phiên bản JDK/Spring Boot, classpath và quy trình deploy**. Có project Java 17 hoàn chỉnh, cấu hình Maven/Gradle, hai Dockerfile mẫu, các lệnh kiểm chứng và checklist CI/CD.

**Phạm vi phiên bản:** Spring Boot 3.3.13 được chọn làm mốc để cú pháp nhất quán, không khẳng định đó là phiên bản mới nhất hoặc còn trong thời hạn hỗ trợ. Với ứng dụng thực, hãy dùng version đã được tổ chức phê duyệt và đọc tài liệu ứng với **đúng nhánh**. Trường hợp Java 24 trở lên và **AOT Cache** là một luồng khác, được nêu ở phần giới hạn, **không trộn với cú pháp CDS trên Java 17**.

## 1. CDS là gì và giúp gì cho Spring Boot?

**Class Data Sharing (CDS)** là khả năng của HotSpot JVM lưu thông tin đã được xử lý của các class vào một archive dạng `.jsa`. Lần chạy sau, JVM có thể dùng lại những metadata/class phù hợp thay vì luôn thực hiện toàn bộ công việc nạp/xử lý theo cách thông thường.

Hai khả năng cần phân biệt:

- **Default CDS của JDK**: nhiều bản JVM đã có archive mặc định cho các class nền tảng. Bạn có thể nhận lợi ích nhất định dù chưa tạo archive riêng cho ứng dụng.
- **Application CDS (AppCDS) / dynamic CDS archive**: lưu thêm class ứng dụng/thư viện được JVM nạp trong một lần chạy “huấn luyện”. Trên **Java 17**, tùy chọn `-XX:ArchiveClassesAtExit=application.jsa` tạo dynamic archive khi JVM thoát, rồi `-XX:SharedArchiveFile=application.jsa` yêu cầu JVM sử dụng archive này ở lần chạy khác.

CDS có thể cải thiện **startup và footprint**; nó **không** làm thuật toán nghiệp vụ chạy nhanh hơn một cách mặc định, không phải database cache, không lưu object graph của cả ứng dụng và không bảo đảm một mức cải thiện cố định. Lợi ích thay đổi theo số class đã load, classloader, JVM, image, cold/warm startup, filesystem và tài nguyên container.

Một quy trình hợp lệ:

```text
Spring Boot executable JAR
          |
          | jarmode=tools extract
          v
CDS-friendly layout: small application JAR + lib/*.jar
          |
          | Java 17 training JVM, exits cleanly
          | -XX:ArchiveClassesAtExit=application.jsa
          v
application.jsa
          |
          | Same compatible runtime layout/JDK
          | -XX:SharedArchiveFile=application.jsa
          v
Application starts with CDS archive available
```

**Không phải chỉ bật một JVM flag là đủ.** Archive phải được tạo thành công, có đường dẫn và classpath đúng, và JVM phải chấp nhận sử dụng nó ở lần chạy production.

## 2. Vì sao layout của Spring Boot executable JAR quan trọng?

Một executable JAR Spring Boot tiêu chuẩn thường có:

```text
app.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...       # Boot launcher classes
└── BOOT-INF/
    ├── classes/...                           # Application classes/resources
    ├── lib/*.jar                             # Nested runtime dependency JARs
    └── layers.idx                            # Optional archive layer index
```

Chạy:

```bash
java -jar app.jar
```

thường đúng về chức năng. Tuy nhiên, bên trong JAR vẫn có **nested JARs**, khiến classpath không giống một danh sách các JAR bình thường nằm trên filesystem. Cơ chế CDS/JVM có những ràng buộc về classpath và file JAR; layout chứa nested archives không phải cách tiện nhất để chuẩn bị archive CDS dùng lại.

Từ **Spring Boot 3.3**, `jarmode=tools extract` tạo layout trong đó:
- Runtime dependencies được trích ra thư mục **`lib/`**.
- Một **application JAR nhỏ hơn** chứa classes/resource/manifest và tham chiếu tới các file thư viện được tách.
- Bạn chạy được ứng dụng bằng `java -jar` trên **application JAR đã trích xuất**, không cần tự xây classpath thủ công.

Tài liệu Spring Boot 3.3 gọi **default extraction layout** là cách triển khai hiệu quả và **CDS-friendly**. Đây không đơn giản là `jar xf` trích nguyên sơ mọi entry về chỗ cũ; công cụ Boot tạo layout thuận tiện để chạy thực và xây cache.

**Không đánh đồng:**
- `java -jar original-fat.jar`: chạy outer executable JAR, classpath nested archives.
- `java -jar extracted/app.jar`: chạy JAR nhỏ sau extraction với thư viện `lib/` ở vị trí phù hợp.
- `java -cp lib/*:...`: classpath tự ghép. Nếu thứ tự/path khác lúc training, CDS có thể không tái sử dụng như mong muốn.

## 3. Hai chế độ extraction trong Spring Boot 3.3

Spring Boot 3.3 cung cấp công cụ `spring-boot-jarmode-tools` thông qua special mode:

```bash
java -Djarmode=tools -jar app.jar
```

Lệnh trên hiển thị help về các command được hỗ trợ, trong đó có `extract`, `list-layers` và `help`.

### 3.1. Layout mặc định: `extract --destination`

```bash
java -Djarmode=tools -jar app.jar extract --destination unpacked
```

Đây là lựa chọn **đơn giản nhất cho AppCDS**. Nếu source tên `app.jar`, cấu trúc mô tả ở mức ý tưởng:

```text
unpacked/
├── app.jar                        # Application JAR được Boot tạo để chạy
└── lib/
    ├── spring-boot-*.jar
    ├── spring-context-*.jar
    └── ...                        # Các runtime dependencies khác
```

File JAR nhỏ mang **tên ứng dụng đầu vào**, không mặc định luôn là `application.jar`. Theo tài liệu Boot 3.3, extraction mặc định tạo `<tên-app>/<tên-app>.jar` và các JAR phụ thuộc dưới `lib/`. Đường dẫn chính xác có thể thêm metadata/các file theo build; cần kiểm tra output thực tế.

Với file `target/cds-layout-demo-1.0.0.jar` và đích `unpacked`, cách chạy là:

```bash
java -jar unpacked/cds-layout-demo-1.0.0.jar
```

Cũng có thể vào thư mục `unpacked` rồi chạy `java -jar cds-layout-demo-1.0.0.jar`. Giữ nguyên cây thư mục vì manifest/classpath của JAR trích xuất liên hệ tới các thư viện `lib/`.

### 3.2. Layout giữ Docker layers: `extract --layers --destination`

```bash
java -Djarmode=tools -jar app.jar extract --layers --destination extracted
```

Kết quả được nhóm theo layer index:

```text
extracted/
├── dependencies/
├── spring-boot-loader/
├── snapshot-dependencies/
└── application/
```

Khi **COPY nội dung** của bốn thư mục vào **cùng một thư mục đích runtime** theo đúng thứ tự, bạn tái tạo layout để có thể chạy bằng:

```bash
java -jar application.jar
```

Đây là layout được tài liệu Dockerfile Spring Boot 3.3 dùng để kết hợp **OCI cache** với **CDS**. File `application.jar` trong image cuối là launcher/application artifact được công cụ tạo, **không nhất thiết là bản uber JAR gốc**.

### 3.3. Chọn chế độ nào?

| Nhu cầu | Cách extract | Đầu ra nên dùng |
| --- | --- | --- |
| Chạy CDS trong máy local/VM bằng ít bước | `extract --destination unpacked` | `unpacked/<app>.jar` và `unpacked/lib/` |
| Dockerfile cần tái sử dụng cache theo dependencies/loader/app | `extract --layers --destination extracted` | Bốn thư mục và `COPY` riêng vào `/application` |
| Chỉ xem nội dung entry | `jar tf` hoặc `unzip -l` | Danh sách entry, **không** thay thế Boot extraction |
| Muốn chạy outer JAR không extract | `java -jar original.jar` | Hợp lệ runtime nhưng không tận dụng layout CDS-friendly của Boot 3.3 |
| Dùng Buildpacks | `bootBuildImage` hoặc Maven `build-image` | Buildpack quản lý image layout/huấn luyện theo capabilities riêng |

**Điểm mấu chốt:** `--layers` không đồng nghĩa “mới hỗ trợ CDS”; **cả layout mặc định lẫn layout được ghép lại từ layers đều CDS-friendly** khi classpath và cấu trúc cuối tương ứng. Còn tùy chọn `--layers` đặc biệt hữu ích để tạo Docker/OCI layers ổn định.

## 4. Giới hạn phiên bản Spring Boot: `tools` khác `layertools`

Các tài liệu của nhiều năm có các lệnh giống nhưng **không tương đương**:

| Nhánh/cơ chế | Lệnh thường gặp | Ghi chú |
| --- | --- | --- |
| Spring Boot 2.x và các phiên bản trước 3.3 có layered JAR support | `-Djarmode=layertools` | Command và layout cũ; đọc tài liệu nhánh đang chạy |
| **Spring Boot 3.3** | `-Djarmode=tools`, command `extract`, `list-layers`, `help` | Có extraction CDS-friendly `lib/`; dùng cú pháp 3.3 trong bài |
| Spring Boot 3.3 khi cần Docker layers | `extract --layers --destination ...` | Dựng lại runtime layout bằng `COPY` bốn nhóm |
| Các nhánh Spring Boot/JDK mới | Kiểm tra tính năng tương ứng, có thể có **JVM AOT Cache** | Không giả định mọi lệnh/flag mới chạy trên Boot 3.3 + Java 17 |

Trong Spring Boot 3.3, `-Djarmode=tools extract` **thay thế hướng dẫn cũ** `-Djarmode=layertools extract`; tương tự `list-layers` thay lệnh liệt kê cũ. Không copy nguyên một Dockerfile bài viết cũ rồi đổi mỗi số version Maven/Gradle.

Một hạn chế được tài liệu Boot 3.3 nêu rõ: **tools mode không sử dụng được với fully executable JAR có nhúng shell launch script**. Nếu project đã bật launch script để chạy file trực tiếp như chương trình Unix, hãy **tắt launch script** trên artifact sẽ dùng `jarmode=tools extract`.

### 4.1. Boot tools là thành phần có thể bị loại khỏi archive

Gradle task `bootJar` và Maven `spring-boot-maven-plugin` của Boot 3.3 có thuộc tính **`includeTools`**. Nếu đã đặt `includeTools=false`, artifact có thể chạy `java -jar` bình thường nhưng **không còn công cụ cần cho `jarmode=tools`** trong archive.

Đừng nhầm giữa việc có/không có `BOOT-INF/layers.idx` với việc có/không có `spring-boot-jarmode-tools`. Spring Boot 3.3 đã tách cơ chế điều khiển include tools khỏi một số thiết lập layer cũ. Khi debug, kiểm tra đồng thời:
1. Version Spring Boot plugin thực dùng.
2. Có tools trong packaged JAR không.
3. Có embedded launch script không.
4. Command `tools extract` đúng nhánh/version không.
5. Khi dùng `--layers`, layer index được tạo và đọc thành công hay không.

## 5. Giới hạn JVM: Java 17 CDS, Java 24+ và AOT Cache

Bài dùng **Java 17** vì Spring Boot 3.3 hỗ trợ mức Java này và HotSpot Java 17 có **dynamic CDS archive** qua `ArchiveClassesAtExit`. Chạy:

```bash
java -version
java -XX:+PrintFlagsFinal -version
```

Lệnh thứ hai liệt kê nhiều flags và thường khá dài; dùng `java -version` và docs JVM để kiểm tra tên/tác dụng flag, không cần in toàn bộ flag list trong CI. Nếu image dùng runtime khác HotSpot hoặc bản JDK không hỗ trợ option, JVM sẽ báo không nhận `-XX:...`; **đừng im lặng giả định CDS đã bật**.

Các phân biệt phiên bản:

- **Java 17 (HotSpot):** có `-XX:ArchiveClassesAtExit=...`, `-XX:SharedArchiveFile=...`, `-Xshare:off/on/auto`. AppCDS tạo archive động dựa trên class được load.
- **Java 21 (HotSpot):** cũng có CDS, nhưng **không dùng bừa file `.jsa` đã train trên Java 17**. Tạo archive với runtime/JVM phù hợp bản triển khai.
- **Java 24 trở lên:** JVM đã bổ sung **AOT Cache** theo các JEP mới. Tài liệu Spring Boot các nhánh mới khuyến nghị AOT Cache thay CDS khi JVM hỗ trợ; syntax có thể khác giữa các bản Java/Boot. **Không dùng `-XX:AOTCache` hay `-XX:AOTMode` trên Java 17 theo mẫu bài này**.
- **GraalVM native executable:** là mô hình triển khai khác; không tự mang HotSpot CDS archive `application.jsa` vào native binary.
- **Spring AOT (`processAot`) / native-image:** khác mục tiêu với CDS. Spring AOT có thể tạo mã/hints cho reflection/bean initialization, còn CDS chia sẻ class metadata ở JVM.

**Không kết luận Spring Boot 3.3 hỗ trợ mọi Java tương lai** chỉ vì JVM mới có AOT Cache; phải kiểm tra **bảng tương thích Boot/JDK của phiên bản thực tế**. Khi nâng JDK major hoặc Spring Boot plugin, nên huấn luyện lại archive và kiểm tra runtime flags.

## 6. Những điều kiện khiến `application.jsa` không sử dụng được

Java CDS có ràng buộc về **classpath, module path, JAR bytes, JDK build và tùy chọn VM**:

1. **JDK runtime tương thích**: khuyến nghị dùng cùng nhà cung cấp, phiên bản/build, CPU architecture và base image cho training và production. Archive có thể không hoạt động nếu JDK khác.
2. **Classpath cuối**: những đường dẫn JAR và tập entries được JVM nhìn thấy phải phù hợp với lúc tạo archive; đừng train ở `/tmp` rồi tùy tiện chuyển `lib/` sang một vị trí khác hoặc đổi command `-cp`.
3. **JAR không bị chỉnh sau khi train**: cập nhật dependency, class/resources, plugin-generated manifest hoặc thư viện trong `lib/` có thể làm archive không hợp lệ hay kém hiệu quả.
4. **VM flags có thể ảnh hưởng CDS**: một số flags liên quan module path, patch modules, class loading hoặc advanced options vô hiệu hóa hoặc giảm khả năng dùng archive.
5. **Những class đã load trong training** được đưa vào archive trong phạm vi JVM hỗ trợ. Những class chỉ load khi truy cập một endpoint hiếm có thể không được hưởng lợi nếu không tham gia training.
6. **Classloader/application topology** có thể tác động classes được lưu; việc dùng layout do Boot tạo là cách hạn chế rủi ro.
7. **Filesystem và permissions**: container cần đọc được `application.jsa`, JAR nhỏ và các files trong `lib/`; không được lạm dụng root permissions để che quyền sai.

Với Java 17, tài liệu JVM về Application CDS cũng nhấn mạnh rằng classpath không thể tùy tiện chứa **non-empty directories** trong một số phương thức tạo archive. Layout nhỏ **JAR + lib JARs** phù hợp hơn một cách bung class thành các thư mục chứa `.class` rồi thêm nguyên các thư mục đó vào `-cp`.

**Chốt:** *CDS archive là dữ liệu gắn với một bản build và một môi trường JVM*, không phải asset dùng chung vĩnh viễn giữa mọi release. Mỗi lần đổi **ứng dụng/JAR/JDK/runtime layout**, nên coi archive cũ là **không hợp lệ cho release mới** và tạo lại.

## 7. Project Java 17 + Spring Boot 3.3 thực hành

Để người học kiểm tra lệnh thật, xây một ứng dụng REST đơn giản. Có thể dùng Maven hoặc Gradle với **cùng mã Java**.

```text
cds-layout-demo/
├── pom.xml                              # Chọn Maven
├── settings.gradle                       # Chọn Gradle
├── build.gradle                          # Chọn Gradle
├── Dockerfile.cds                       # Docker multi-stage layered CDS
├── Dockerfile.extracted                 # Docker non-layered extracted CDS
└── src/
    ├── main/java/com/example/cds/
    │   ├── CdsLayoutApplication.java
    │   └── PingController.java
    └── test/java/com/example/cds/
        └── PingControllerTest.java
```

Đây là cây file **theo lựa chọn**, không có yêu cầu một dự án thực tế phải đồng thời duy trì cả Maven và Gradle. Khi thử Maven, dùng `pom.xml`; khi thử Gradle, dùng `settings.gradle` + `build.gradle`. Các Dockerfile chỉ copy từ output tương ứng.

### 7.1. Main class

Tạo `src/main/java/com/example/cds/CdsLayoutApplication.java`:

```java
package com.example.cds;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CdsLayoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CdsLayoutApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt auto-configuration và component scan dưới `com.example.cds`. Với web starter, ứng dụng có embedded server và **không tự kết thúc**, khác với các console demo chỉ chạy một lần.

### 7.2. REST endpoint

Tạo `src/main/java/com/example/cds/PingController.java`:

```java
package com.example.cds;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "cds-ready";
    }
}
```

Khi app đang chạy trên cổng mặc định 8080, lệnh:

```bash
curl -fsS http://localhost:8080/ping
```

cho body:

```text
cds-ready
```

Đây là output **HTTP body**, không phải log khởi động Java. Dùng `Ctrl+C` để dừng app khi thử local.

### 7.3. JUnit test thuần Java

Tạo `src/test/java/com/example/cds/PingControllerTest.java`:

```java
package com.example.cds;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PingControllerTest {

    @Test
    void pingReturnsExpectedText() {
        assertEquals("cds-ready", new PingController().ping());
    }
}
```

Test này kiểm tra hành vi controller và không cần khởi động Spring context, nên cũng chạy được trong CI đơn giản. Nó **không** kiểm tra archive CDS hoặc Docker image; phần đó sẽ được kiểm tra riêng sau khi build artifact.

## 8. Maven POM đầy đủ để tạo executable Boot JAR

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cds-layout-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

Spring Boot parent quản lý version và execution `repackage` của plugin theo conventions. Maven sẽ tạo executable JAR trong `target/cds-layout-demo-1.0.0.jar` và, trong cấu hình thông thường, kèm công cụ `spring-boot-jarmode-tools`.

Build và test từ root project:

```bash
./mvnw clean verify
```

Nếu project không có Maven Wrapper, dùng `mvn clean verify` với Maven/JDK phù hợp. Trên Windows PowerShell dùng `.\mvnw.cmd clean verify`.

Sau đó:

```bash
jar tf target/cds-layout-demo-1.0.0.jar
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar
```

Nếu `java -Djarmode=tools` không nhận lệnh, kiểm tra version/plugin execution và `includeTools` thay vì coi file tên `.jar` nào cũng có tools.

**Không dùng `target/*.jar.original`** làm input extraction. Đó có thể là JAR trước `repackage`, không có đầy đủ Boot launcher và các nested libraries.

## 9. Gradle Groovy DSL tương đương

Tạo `settings.gradle`:

```groovy
rootProject.name = 'cds-layout-demo'
```

Tạo `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.cds.CdsLayoutApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`bootJar` tạo **executable JAR**, còn task `jar` có thể tạo `*-plain.jar` theo conventions. Khi dùng `extract`, phải chọn **đúng `bootJar` output**, không chọn file plain bằng wildcard. `springBoot.mainClass` được chỉ định rõ để tránh ambiguity khi module có nhiều `main`.

Build:

```bash
./gradlew clean test bootJar
java -Djarmode=tools -jar build/libs/cds-layout-demo-1.0.0.jar
```

Trên Windows PowerShell dùng `.\gradlew.bat`; nếu không có Gradle Wrapper thì dùng bản Gradle cài sẵn tương thích.

Nếu dùng `build.gradle.kts`, cấu hình Gradle Kotlin DSL tương đương về main class và test:

```kotlin
springBoot {
    mainClass.set("com.example.cds.CdsLayoutApplication")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Đây là **đoạn áp dụng vào build.gradle.kts đã có plugin Java và Spring Boot**, không phải một file Kotlin DSL độc lập. Giữ cú pháp `mainClass.set(...)` và typed task cho Kotlin DSL; không sao chép nguyên Groovy DSL vào `build.gradle.kts`.

## 10. Kiểm tra trước extraction: phải là đúng Boot JAR

Với Maven:

```bash
JAR=target/cds-layout-demo-1.0.0.jar
jar tf "$JAR" | grep '^BOOT-INF/'
jar tf "$JAR" | grep 'META-INF/MANIFEST.MF'
```

Với Gradle thay `JAR=build/libs/cds-layout-demo-1.0.0.jar`. Trong danh sách, bạn mong đợi:
- `BOOT-INF/classes/com/example/cds/CdsLayoutApplication.class`.
- `BOOT-INF/classes/com/example/cds/PingController.class`.
- `BOOT-INF/lib/spring-boot-3.3.13.jar` và nhiều runtime dependencies.
- `META-INF/MANIFEST.MF` với các thuộc tính Boot launcher/Start-Class.
- `BOOT-INF/layers.idx` nếu layered index được bật.

**`jar tf` chỉ liệt kê entry**, không chứng minh CDS đang hoạt động. Nó giúp phân biệt executable JAR với plain JAR. Khi có `unzip`, xem manifest:

```bash
unzip -p "$JAR" META-INF/MANIFEST.MF
```

Với Spring Boot 3.3, những field tiêu biểu:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.cds.CdsLayoutApplication
```

Đây là trích đoạn, manifest có thể chứa thêm metadata. Nếu dùng fully executable JAR nhúng launch script, `tools` mode không hỗ trợ: cần build artifact khác **không có script**.

## 11. Thực hành CDS với layout mặc định trên máy local

Dùng Maven artifact để lệnh dễ đọc; Gradle chỉ cần thay đường dẫn. Từ thư mục gốc project:

```bash
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar \
  extract --destination unpacked
```

Sau khi tools chạy thành công, kiểm tra:

```bash
ls -l unpacked
ls -l unpacked/lib
```

Bạn mong đợi **`unpacked/cds-layout-demo-1.0.0.jar`** và các runtime JAR bên dưới **`unpacked/lib/`**; một số metadata khác có thể hiện diện tùy archive. Bây giờ vào thư mục output:

```bash
cd unpacked
java -jar cds-layout-demo-1.0.0.jar
```

Terminal khác kiểm tra:

```bash
curl -fsS http://localhost:8080/ping
```

Kết quả:

```text
cds-ready
```

Dừng app bằng Ctrl+C. Việc chạy được JAR nhỏ **xác minh layout có đủ classpath để khởi động**, nhưng chưa chứng minh có AppCDS archive. Bước huấn luyện ở mục sau sẽ sinh file `.jsa`.

**Đừng tự đổi tên JAR hoặc di chuyển `lib/` sau extraction** nếu chưa hiểu manifest/classpath. Nếu cần đặt image root ở `/application`, hãy trích xuất trực tiếp hoặc copy nguyên cây layout **trước khi huấn luyện**, rồi dùng đúng vị trí đó ở production.

## 12. Huấn luyện CDS trên Java 17 bằng `ArchiveClassesAtExit`

Trong `unpacked/` có executable application JAR nhỏ và `lib/`. Chạy:

```bash
java -XX:ArchiveClassesAtExit=application.jsa \
  -Dspring.context.exit=onRefresh \
  -jar cds-layout-demo-1.0.0.jar
```

Ý nghĩa:
- `-XX:ArchiveClassesAtExit=application.jsa`: yêu cầu JVM ghi **dynamic CDS archive** khi process kết thúc.
- `-Dspring.context.exit=onRefresh`: trong tích hợp Spring Framework, yêu cầu **thoát sau khi refresh application context**, phục vụ training mà không giữ web server phục vụ request vô thời hạn.
- `-jar cds-layout-demo-1.0.0.jar`: chạy **JAR đã extract**, không phải outer JAR tại `target/`.

Ở Docker/CI, training phải **kết thúc với exit code thành công** và tạo được file archive trước khi image tiếp tục build. Nếu chương trình có startup listener kết nối DB, Kafka, service nội bộ hoặc đòi secrets trong `@PostConstruct`, `onRefresh` không có nghĩa mọi side effect biến mất. Cần thiết kế training profile/config phù hợp hoặc bỏ CDS nếu không thể huấn luyện an toàn trong build.

Kiểm tra:

```bash
test -s application.jsa
ls -lh application.jsa
```

Lệnh `test -s` có nghĩa “file tồn tại và không rỗng” trên Unix shell; đây **chưa phải xác minh JVM sẽ sử dụng được** archive. Không có stdout chuẩn cố định khi training: Spring Boot và HotSpot log khác nhau theo version/log settings.

### 12.1. Nếu training không thoát

Một ứng dụng thực có thể có thread/background services. Bạn cần điều chỉnh cấu hình training, không chạy `ArchiveClassesAtExit` rồi chờ vô thời hạn. Có thể kiểm soát điều kiện init, tránh scheduler/consumer vô tình hoạt động trong build, và đặt timeout ở CI.

**Không truyền `-Dspring.context.exit=onRefresh` khi chạy production**: property đó nhằm kết thúc training sớm; khi có mặt trong production, web server sẽ không hoạt động như dịch vụ lâu dài.

## 13. Chạy ứng dụng với CDS archive

Khi archive đã được tạo, đứng **trong chính thư mục `unpacked`** và chạy:

```bash
java -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

Một terminal khác:

```bash
curl -fsS http://localhost:8080/ping
```

Body vẫn là:

```text
cds-ready
```

Sự đúng đắn của endpoint là phép thử **ứng dụng không bị hỏng** sau khi bật CDS. Muốn kiểm tra JVM đã nhận `.jsa`, dùng logs như phần sau; đừng đoán từ HTTP body.

Nếu JDK/cache không tương thích, JVM có thể cảnh báo và không tận dụng đầy đủ archive, hoặc fail nếu bạn buộc `-Xshare:on`. Theo khuyến nghị Java 17, **`-Xshare:auto`** phù hợp production vì cho phép JVM quyết định có thể dùng CDS hay không; còn `-Xshare:on` nên dành cho chẩn đoán cần fail-fast.

## 14. Cách xác minh CDS đang được JVM sử dụng

Trong Java 17 HotSpot, bật unified logging:

```bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

Những log liên quan CDS giúp phát hiện:
- Archive nào được map/mở thành công.
- Có vấn đề tương thích với classpath/JDK hay không.
- Lớp shared archive có được JVM chấp nhận hay bị bỏ qua.
- Sự khác biệt giữa default JDK CDS archive và **application.jsa**.

Đừng so sánh một dòng output log cứng cho mọi JVM minor version/vendor; cách viết log có thể khác. Nếu cần log nhiều hơn có thể dùng:

```bash
java -Xlog:cds=debug \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

`-Xlog:cds=debug` có thể tạo rất nhiều dòng; chỉ bật trong chẩn đoán, không mặc định trong production.

Để **fail-fast trong môi trường kiểm tra** khi archive không thể được dùng:

```bash
java -Xshare:on \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

**Không bật `-Xshare:on` một cách không kiểm soát trên tất cả production workloads**: Java 17 docs cảnh báo mode bắt buộc có thể làm JVM exit khi shared archive không hợp lệ. Trong production dùng chế độ thông thường và giám sát logs/metrics phù hợp.

### 14.1. So sánh startup có và không dùng AppCDS

Khi benchmark, dùng **cùng JDK, CPU/memory limits, filesystem, config và app JAR**, chỉ đổi flags. Ví dụ không dùng CDS:

```bash
java -Xshare:off -jar cds-layout-demo-1.0.0.jar
```

So với:

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

`-Xshare:off` tắt cả CDS mặc định của JDK, nên đây là **so sánh cực trị**. Nếu muốn đo thêm giá trị của *application CDS so với default JDK CDS*, cần một baseline JVM bật CDS mặc định nhưng **không chỉ định `application.jsa`**. Chạy nhiều vòng, warm/cold cache có kiểm soát, đo startup, RSS, throughput và quan sát hành vi thật. Không hứa “giảm 50% thời gian khởi động” nếu không có phép đo của chính app.

## 15. Dockerfile baseline: một uber JAR, không CDS

Để thấy khác biệt layout, tạo `Dockerfile.basic`:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/cds-layout-demo-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

Build sau khi `./mvnw clean package`:

```bash
docker build -f Dockerfile.basic -t cds-demo:basic .
docker run --rm -p 8080:8080 cds-demo:basic
```

Trong terminal khác gọi `curl -fsS http://localhost:8080/ping`. Body `cds-ready`. Dockerfile này **đơn giản và chạy được**, nhưng:
- Không dùng Boot tools extraction.
- Không sinh `application.jsa`.
- Copy nguyên outer JAR, nên khi code app thay đổi toàn bộ file JAR được copy lại.
- Không tách phần dependencies thành OCI layers theo `layers.idx`.

Vì thế `Dockerfile.basic` là baseline hợp lý khi cân nhắc chi phí phức tạp của CDS và multi-stage extraction. **Không phải mọi project đều cần CDS.**

## 16. Dockerfile CDS dùng extraction mặc định, không yêu cầu bốn lớp OCI

Khi chỉ quan tâm layout CDS-friendly và muốn ví dụ dễ hiểu, tạo `Dockerfile.extracted` (Maven demo):

```dockerfile
# Dùng cùng họ runtime và Java 17 cho training / serving.
FROM bellsoft/liberica-openjre-debian:17-cds AS extractor
WORKDIR /workspace
COPY target/cds-layout-demo-1.0.0.jar input.jar
RUN java -Djarmode=tools -jar input.jar extract --destination /unpacked

FROM bellsoft/liberica-openjre-debian:17-cds
WORKDIR /application
COPY --from=extractor /unpacked/ ./

# Training chạy trong chính layout cuối.
RUN java -XX:ArchiveClassesAtExit=application.jsa \
    -Dspring.context.exit=onRefresh \
    -jar cds-layout-demo-1.0.0.jar

EXPOSE 8080
ENTRYPOINT ["java", "-XX:SharedArchiveFile=application.jsa", \
            "-jar", "cds-layout-demo-1.0.0.jar"]
```

Trình tự:
1. Builder copy **đúng Boot JAR** đã package.
2. Boot tools tạo `/unpacked/<tên-jar>` và `/unpacked/lib/`.
3. Runtime stage copy nguyên layout vào `/application`.
4. Lệnh `RUN` huấn luyện CDS ở **`/application`**, cùng nơi và cùng JVM image family dùng khi container thực chạy.
5. `ENTRYPOINT` đọc `application.jsa`, chạy chính JAR nhỏ.
6. Docker image cuối **không cần giữ input uber JAR gốc** ở `/workspace/input.jar`.

Build:

```bash
./mvnw clean package
docker build -f Dockerfile.extracted -t cds-demo:extracted .
```

Chạy:

```bash
docker run --rm -p 8080:8080 cds-demo:extracted
```

Kết quả `GET /ping` vẫn là `cds-ready`. Nếu dùng Gradle, sửa dòng `COPY target/...` thành `COPY build/libs/cds-layout-demo-1.0.0.jar input.jar` sau khi chạy `./gradlew clean test bootJar`.

**Giới hạn của Dockerfile này:** `COPY` nguyên layout extracted trong một bước không cố tối đa hóa layer cache khi chỉ app code đổi. Nó là ví dụ **CDS trước, Docker cache sau**. Để có cả hai, dùng Dockerfile ở mục 17.

## 17. Dockerfile kết hợp bốn Spring Boot layers với CDS

Tạo `Dockerfile.cds` cho Maven demo:

```dockerfile
# Spring Boot 3.3 + Java 17 CDS: extract tại builder.
FROM bellsoft/liberica-openjre-debian:17-cds AS extractor
WORKDIR /workspace

# Không dùng wildcard nếu target có nhiều artifact.
COPY target/cds-layout-demo-1.0.0.jar input.jar
RUN java -Djarmode=tools -jar input.jar extract --layers --destination extracted

# Dùng cùng runtime image cho training và serving.
FROM bellsoft/liberica-openjre-debian:17-cds
WORKDIR /application

# Mỗi COPY là một lớp OCI riêng, theo thứ tự cache-friendly.
COPY --from=extractor /workspace/extracted/dependencies/ ./
COPY --from=extractor /workspace/extracted/spring-boot-loader/ ./
COPY --from=extractor /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extractor /workspace/extracted/application/ ./

# Sinh application CDS sau khi đã ghép toàn bộ classpath.
RUN java -XX:ArchiveClassesAtExit=application.jsa \
    -Dspring.context.exit=onRefresh \
    -jar application.jar

EXPOSE 8080
ENTRYPOINT ["java", "-XX:SharedArchiveFile=application.jsa", \
            "-jar", "application.jar"]
```

**Đây là ví dụ Dockerfile đúng bố cục Spring Boot 3.3**, trong đó lệnh `extract --layers` tạo các thư mục tương ứng với bốn layer:
- `dependencies`: thư viện release ngoài project.
- `spring-boot-loader`: mã launcher của Boot.
- `snapshot-dependencies`: dependency SNAPSHOT ngoài project.
- `application`: class/resource và local project module dependencies.

Những thư mục được **ghép tại cùng root `/application`**. Cấu trúc chứa **`application.jar`** và `lib/` phù hợp để chạy Boot ở chế độ đã trích xuất. `RUN` huấn luyện phải đứng **sau cả bốn COPY**; nếu train trước rồi tiếp tục thay classpath files, archive có thể lỗi hoặc không phát huy hiệu quả.

### 17.1. Lệnh build và chạy image

```bash
./mvnw clean package
docker build -f Dockerfile.cds -t cds-demo:layered .
docker run --rm -p 8080:8080 cds-demo:layered
```

Trong terminal khác:

```bash
curl -fsS http://localhost:8080/ping
```

HTTP body:

```text
cds-ready
```

Với Gradle: chạy `./gradlew clean test bootJar` và đổi đúng một dòng Dockerfile thành `COPY build/libs/cds-layout-demo-1.0.0.jar input.jar`.

### 17.2. Vì sao bốn `COPY` giúp cache?

Khi chỉ sửa `PingController.java`, layer `application` thường thay đổi, còn `dependencies` và `spring-boot-loader` có cơ hội tái sử dụng. Nếu có SNAPSHOT dependency đổi, layer `snapshot-dependencies` có thể khác. Nhưng **layer chứa `application.jsa` cũng phải được tạo lại** khi phần code/classpath liên quan thay đổi.

**Không hứa Docker luôn chỉ rebuild đúng một layer**: BuildKit cache chịu ảnh hưởng của base image digest, entry timestamps, file bytes, metadata và thứ tự các Dockerfile instructions. Nếu base image/JDK đổi, phải huấn luyện lại `application.jsa`; nếu task build làm JAR không deterministic, Docker cache có thể miss dù source gần như không thay.

### 17.3. Docker image trong sản xuất

Ngoài bài thực hành:
- **Pin base image theo digest** trong pipeline release nếu có yêu cầu reproducibility.
- Dùng non-root user khi policy cho phép, đảm bảo `application.jsa`/JAR/`lib` có quyền đọc.
- Không truyền DB passwords hoặc production secrets trong `docker build` chỉ để training.
- Giữ `WORKDIR /application` và layout/entrypoint cuối phù hợp.
- Nếu có nhiều artifacts ở `target` hoặc `build/libs`, chọn **đúng Boot JAR bằng path cụ thể**, không dùng `*.jar` mơ hồ.
- Docker ENTRYPOINT phải **bỏ `-Dspring.context.exit=onRefresh`**, nếu không app sẽ kết thúc thay vì phục vụ HTTP.

## 18. Xác minh `application.jsa` trong image, không chỉ thấy build thành công

Build Dockerfile có bước `RUN ... ArchiveClassesAtExit` thường fail khi training fail, nhưng khi image thành công vẫn nên kiểm tra file và JVM acceptance.

Kiểm tra kích thước file trong image đã build:

```bash
docker run --rm --entrypoint /bin/sh cds-demo:layered \
  -c 'test -s /application/application.jsa && ls -lh /application/application.jsa'
```

Kiểm tra HotSpot logging:

```bash
docker run --rm -p 8080:8080 \
  --entrypoint java cds-demo:layered \
  -Xlog:cds=info -XX:SharedArchiveFile=application.jsa \
  -jar application.jar
```

Dòng log có thể khác nhau giữa vendor/JDK patch versions. Hãy tìm thông tin cho thấy JVM đã load **application CDS archive** và không có cảnh báo mismatch; không lấy dòng `cds-ready` làm bằng chứng, vì endpoint sẽ trả lời giống nhau **cả khi không có CDS**.

Khi muốn fail-fast trong **CI test**, có thể dùng `-Xshare:on` trong một lệnh kiểm chứng riêng nhưng **không** thay ENTRYPOINT production thành forced mode một cách không được kiểm thử. JVM flag `-Xshare:on` có thể khiến app không khởi động nếu archive không hợp lệ.

## 19. Tình huống làm archive không tái sử dụng được

| Thay đổi | Rủi ro đối với `application.jsa` | Cách xử lý |
| --- | --- | --- |
| Sửa class hoặc resource ứng dụng, rebuild JAR | Application classes/JAR bytes khác | **Train lại** archive với artifact mới |
| Nâng Spring Boot/Framework/dependency version | Classpath và class metadata đổi | Train lại sau upgrade, chạy smoke tests |
| Thay đổi thư viện release trong `lib/` | File JAR mới/different bytes | Train lại, không giữ `.jsa` cũ |
| Update SNAPSHOT library cùng version | Bytes thay dù coordinate không đổi | Không dùng archive cũ; dùng immutable dependency cho release |
| Đổi image từ JDK 17 vendor A sang vendor B | JVM/archive compatibility có thể khác | Huấn luyện và chạy cùng runtime distribution/build |
| Thay CPU architecture AMD64 ↔ ARM64 | CDS binary layout có thể không tương thích | Build/train riêng mỗi platform |
| Đổi Java 17 patch version hoặc flags | JVM có thể không chấp nhận archive | Train lại với runtime production |
| Đổi `WORKDIR` hoặc di chuyển `lib/` sau train | Classpath/JAR paths khác | Hoàn thiện layout trước training, không di chuyển |
| Thay JAR launcher/shell script | Tool mode có thể bị ảnh hưởng | Dùng Boot JAR không nhúng launch script |
| Lưu archive ngoài final image | Runtime không tìm thấy `application.jsa` | Đảm bảo `RUN` tạo trong final stage hoặc `COPY` đúng |
| Chạy JAR từ thư mục khác với nơi training | Relative paths có thể không còn hợp lệ | Giữ `WORKDIR` nhất quán, kiểm tra classpath |
| Thêm Java agent hoặc module patch flags | Classloader/flags thay, một số tối ưu CDS có thể bị tắt | Kiểm thử đúng startup JVM options sẽ deploy |
| Đổi profile Spring và bean load set | Class load được trong training khác runtime | Đánh giá phạm vi training và đo hiệu quả thực |
| Dùng native image thay HotSpot JVM | Không có cơ chế Java `.jsa` tương ứng | Dùng quy trình native image riêng |

**Ghi nhớ:** Docker layer cache và CDS archive có vòng đời **khác nhau**. Docker có thể reuse dependency image layers trong khi phải sinh lại `application.jsa` vì code app đổi. Hoặc image layer còn đó nhưng JDK runtime khác làm CDS không hợp lệ. Cache hit của Docker **không chứng minh CDS hit**.

## 20. Lưu ý riêng về training `spring.context.exit=onRefresh`

Spring Framework hỗ trợ property `spring.context.exit=onRefresh` để dùng trong training scenario được Spring Boot 3.3 hướng dẫn. Tư duy của nó là:

1. JVM nạp những class cần để khởi tạo context.
2. Application context refresh.
3. Quy trình training được kết thúc để JVM ghi `.jsa`.
4. Runtime lần sau **không** truyền property này nên ứng dụng vận hành bình thường.

Nhưng không phải mọi ứng dụng đều “không có side effect” khi refresh. Những thứ như:
- `@PostConstruct`, bean init/custom `BeanFactoryPostProcessor`;
- kiểm tra kết nối datasource, DB migrations;
- custom bean kết nối Kafka/RabbitMQ/Redis trong quá trình init;
- đọc secret/config từ Vault, DNS/service discovery;
- scheduler/listener khởi động rất sớm

có thể vẫn gây lỗi nếu chạy trong Docker build environment không có infrastructure.

**Giải pháp an toàn:**
- Dùng một **training profile** tối giản, không truy cập hệ production; nhưng nhớ class set/profile khác có thể giảm lợi ích CDS.
- Hoãn/disable side effects không cần thiết khi training, không chỉnh classpath tùy tiện.
- Không inject secret thật vào layer image build vì secret có thể lưu vết trong logs/history.
- Đặt timeout và giới hạn tài nguyên cho CI training run.
- Nếu không huấn luyện an toàn được, **chạy extracted layout không CDS vẫn là lựa chọn tốt hơn việc ép training phá pipeline**.

Một số app cần cho bean init đọc runtime config; tốt nhất tách rõ wiring/initialization với việc truy cập hệ ngoài ngay khi context refresh, nếu kiến trúc cho phép.

## 21. Phân biệt hỗ trợ Boot tools và CDS ở Maven/Gradle

### 21.1. Maven

Với Spring Boot 3.3 parent, `spring-boot-maven-plugin` ở POM mục 8 đủ để repackage. Nếu công ty **không kế thừa** Spring Boot parent mà chỉ import BOM, phải khai báo plugin version/execution `repackage` tường minh.

Nếu đã tùy chỉnh plugin làm mất tools, kiểm tra:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <includeTools>true</includeTools>
    </configuration>
</plugin>
```

Đây là **đoạn plugin thay thế/bổ sung bên trong POM**; nếu POM đã có `spring-boot-maven-plugin`, chỉ thêm `<includeTools>true</includeTools>` vào cùng declaration. Trong Boot 3.3 thông thường tools đã được include; **không bắt buộc thêm đoạn này** nếu bạn không override.

Để dùng `--layers`, đừng tắt layered index bằng `<layers><enabled>false</enabled></layers>`. Nếu không cần phân lớp, `extract` mặc định vẫn có thể dùng với tools nếu artifact hỗ trợ. Tên parameter và quan hệ giữa layer/tools đã thay qua các version; luôn đọc Maven Plugin reference đúng nhánh.

### 21.2. Gradle

Task `bootJar` được Spring Boot Gradle plugin tạo; nếu cần đảm bảo tools:

```groovy
tasks.named('bootJar') {
    includeTools = true
}
```

Đây là **đoạn thêm vào `build.gradle` Groovy**, không phải file độc lập. Chỉ dùng khi dự án đã override hoặc muốn làm rõ cấu hình; default trong Boot 3.3 thường đã include tools. Nếu project bật launch script cho `bootJar`, hãy tắt cấu hình script nếu muốn dùng tools mode.

**Không sửa task `jar` plain để thêm `includeTools`**; tools mode là một khả năng của **Spring Boot executable archive**, không phải JAR library thông thường.

### 21.3. Nếu JAR không có `layers.idx`

`jar tf app.jar` không thấy `BOOT-INF/layers.idx` có thể vì:
- Bạn đang kiểm tra plain JAR, không phải `bootJar` / `repackage` output.
- Layering đã bị disable.
- Version/plugin không hỗ trợ hoặc chưa được cấu hình đúng.
- Bạn kiểm tra nhầm một artifact cũ.

Nếu chỉ muốn `extract --destination` mặc định và có tools hợp lệ, không cần tự áp đặt chính sách bốn Docker layers. Nhưng khi Dockerfile dùng `extract --layers`, **phải có layer metadata phù hợp** để mapping thành các thư mục mà `COPY` mong đợi.

## 22. Docker CDS so với Buildpacks và AOT: chọn đúng công cụ

| Phương án | Nhiệm vụ | Ai quyết định cách tạo image/runtime? |
| --- | --- | --- |
| Dockerfile copy nguyên JAR | Đơn giản, ít bước | Người viết Dockerfile |
| Dockerfile Boot `tools extract` + JAR nhỏ/lib | Layout hiệu quả, CDS-friendly | Người viết Dockerfile |
| Dockerfile Boot `tools extract --layers` + CDS | OCI layers riêng + CDS archive | Người viết Dockerfile, JVM và Boot tools |
| Spring Boot `bootBuildImage` / Maven `build-image` | Buildpacks tạo OCI image, có cơ chế caching/layering riêng | Builder/buildpacks |
| Spring AOT processing | Tối ưu công việc của framework và generated code/hints | Spring AOT tooling |
| JVM AOT Cache (Java 24+ và runtime/Boot phù hợp) | Kỹ thuật JVM mới khác quy trình CDS Java 17 | JVM/runtime/tooling mới |
| GraalVM native image | Biên dịch thành native executable, không chạy qua HotSpot `-jar` | Native-image toolchain |

**Đừng áp dụng cú pháp Buildpacks CDS của một builder tùy ý vào Dockerfile**, hoặc trộn JVM AOT Cache của Java mới vào lệnh AppCDS Java 17. Một `bootBuildImage` có thể tự xử lý layer/caching theo builder phiên bản khác mà không xuất đúng bốn dòng `COPY` như Dockerfile custom.

Nếu mục tiêu chỉ là **rút ngắn thời gian tải image** nhờ Docker cache, layout `--layers` có thể đủ mà không cần CDS. Nếu mục tiêu là giảm startup/memory, mới cần thử training và đánh giá CDS. Nếu app không có latency requirement, baseline image đơn giản có thể dễ vận hành hơn.

## 23. Kiểm thử theo từng tầng: build, layout, archive và endpoint

Một pipeline tốt nên có những điều kiện độc lập:

### 23.1. Artifact đúng

```bash
./mvnw -B clean verify
test -s target/cds-layout-demo-1.0.0.jar
jar tf target/cds-layout-demo-1.0.0.jar |
  grep -Fx 'BOOT-INF/classes/com/example/cds/CdsLayoutApplication.class'
```

### 23.2. Tools mode và extraction thành công

```bash
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar help extract
java -Djarmode=tools -jar target/cds-layout-demo-1.0.0.jar \
  extract --destination unpacked
test -s unpacked/cds-layout-demo-1.0.0.jar
test -d unpacked/lib
```

### 23.3. CDS training tạo archive không rỗng

```bash
cd unpacked
java -XX:ArchiveClassesAtExit=application.jsa \
  -Dspring.context.exit=onRefresh \
  -jar cds-layout-demo-1.0.0.jar
test -s application.jsa
```

### 23.4. Runtime kiểm tra cả CDS và nghiệp vụ

```bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=application.jsa \
  -jar cds-layout-demo-1.0.0.jar
```

Một terminal khác dùng `curl -fsS http://localhost:8080/ping` và kiểm tra body `cds-ready`. **CI tự động** cần khởi động process có quản lý vòng đời, chờ readiness, timeout, xem exit code và dừng process; không gọi một web server chạy mãi đồng bộ rồi cho rằng pipeline sẽ tự hoàn tất.

Nếu kiểm tra Dockerfile `--layers`, cần thêm:
- Danh sách layer từ `java -Djarmode=tools -jar ... list-layers`.
- Kiểm tra ``dependencies`, `spring-boot-loader`, `snapshot-dependencies`, `application` được extracted.
- Kiểm tra file `application.jar` và `lib` sau khi copy vào runtime image.
- Kiểm tra `application.jsa` tồn tại **trong final image**.
- Smoke test image với `docker run`, startup logs và endpoint.

**Nhớ:** lệnh `test -s` chỉ chạy trên Bash/POSIX shell. Trên PowerShell dùng `Test-Path`/`Get-Item`, hoặc chạy validation trong CI Linux.

## 24. So sánh hiệu quả có kiểm soát

Đừng chỉ nhìn log “archive generated” rồi tuyên bố startup tốt hơn. Một cách đánh giá thực tế:

1. Xác định **metric cần cải thiện**: time-to-first-request, application ready time, RSS/PSS memory, image pull/build time.
2. Giữ **cùng source commit, dependency graph, Java image, CPU/memory/cgroup settings và config**.
3. Tạo **baseline 1**: outer uber JAR, không AppCDS.
4. Tạo **baseline 2**: extracted layout không AppCDS, để biết phần lợi ích riêng của extraction.
5. Tạo **variant 3**: extracted layout có AppCDS. Bật `-Xlog:cds` trong lượt xác minh đầu để biết archive thực được load.
6. Chạy nhiều lần, phân biệt cold/warm filesystem cache và container/image cache.
7. Đo cả **chi phí tạo `application.jsa`** trong build và kích thước archive/image tăng thêm.
8. Xem hoạt động khi **classpath đổi**, JDK patch release hoặc image base digest thay.
9. Lưu kết quả/giới hạn trong pipeline, không viết một con số “nhanh hơn X%” cho mọi ứng dụng.

Nếu app khởi động lâu vì database migrations, remote secrets, network warm-up hoặc scheduler, CDS có thể chỉ ảnh hưởng một phần nhỏ total startup. Nếu nhiều JVM chạy cùng host/memory context, lợi ích memory sharing cũng phụ thuộc cách hệ điều hành/container chia sẻ các memory pages.

**CDS không thay thế performance profiling.** Nó là một khả năng tối ưu được đo và kiểm soát, không phải yêu cầu bắt buộc của một Spring Boot Dockerfile.

## 25. Lỗi thường gặp khi extract và dùng CDS

| Hiện tượng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| `-Djarmode=layertools` hoạt động trong ví dụ cũ nhưng không đúng với Boot 3.3 | Nhầm phiên bản jarmode | Dùng `-Djarmode=tools` và đúng commands |
| `tools extract` bị lỗi trên archive có shell launch script | Fully executable JAR không hỗ trợ tools mode | Tạo Boot JAR không nhúng script |
| `java -Djarmode=tools` không hiện help | Tools bị exclude hoặc đang dùng plain JAR | Kiểm tra `includeTools`, `bootJar`/`repackage` |
| `--layers` không trích ra bốn thư mục | Layer index thiếu, sai version/tool config | Kiểm tra `BOOT-INF/layers.idx` và `help extract` |
| `unpacked/lib` rỗng/mất | Chọn nhầm artifact hoặc extract sai layout | Trích đúng executable JAR, đối chiếu `BOOT-INF/lib` |
| `java -jar` trên extracted JAR báo thiếu class | Di chuyển JAR hoặc `lib`, manifest/classpath không còn khớp | Copy nguyên cây extraction, chạy ở đúng vị trí |
| `application.jsa` không xuất hiện | Training không kết thúc thành công, path/permissions sai, flag không được JVM nhận | Xem exit code/logs, `test -s` và JDK version |
| Training Docker `RUN` treo | Web server/worker/service init không thoát đúng | Dùng `spring.context.exit=onRefresh`, thiết kế training phù hợp |
| Training cần DB/secrets thật | Bean init có side effects từ môi trường production | Tách training configuration an toàn hoặc bỏ CDS |
| `.jsa` có file nhưng JVM cảnh báo không dùng | Classpath/JDK/flags khác hoặc archive không tương thích | `-Xlog:cds=info`, train lại từ final layout |
| Đổi JDK patch, runtime vendor hoặc CPU architecture | Binary archive gắn với VM/platform | Build/train lại cho từng runtime target |
| App JAR thay sau training | Archived classes/path/bytes không phù hợp | Huấn luyện lại trên đúng artifact release |
| CDN/Docker cache hit mà CDS không hit | OCI layer cache khác CDS JVM class archive | Kiểm tra logs CDS riêng |
| Tạo archive lúc source vẫn thay đổi liên tục | Artifact bị thay khiến archive cũ lỗi | Sinh `.jsa` trong image build của mỗi release |
| Đưa `-Dspring.context.exit=onRefresh` vào ENTRYPOINT production | App thoát ngay sau refresh, không phục vụ HTTP | Chỉ dùng property trong `RUN` training |
| Dùng `-Xshare:on` trong production không kiểm soát | JVM fail khởi động khi archive mismatch | Dùng chế độ thông thường, guard ở CI |
| Class chỉ load khi có request không vào archive | Training dừng sớm trước khi code path đó chạy | Thiết kế workload training phù hợp, đo lại startup |
| Gradle Docker COPY nhầm `*-plain.jar` | Wildcard lấy sai artifact | Chọn explicit `build/libs/cds-layout-demo-1.0.0.jar` |
| Docker image có `application.jsa` nhưng runtime path khác | `WORKDIR`, `lib` hoặc ENTRYPOINT sai | Cố định layout trước training và khi chạy |
| Java 17 báo `Unrecognized VM option 'AOTCache'` | Flag thuộc JVM mới hơn | Dùng `ArchiveClassesAtExit`/`SharedArchiveFile` trên Java 17 |
| CDS có vẻ không mang lợi ích | Startup chủ yếu do network/DB hoặc archive chỉ chứa ít class | So sánh baseline và logs, tối ưu đúng bottleneck |
| Container chạy với user khác không đọc được `.jsa` | File permissions và ownership trong image | Cho phép runtime user đọc file, không chạy root chỉ để vượt lỗi |
| JVM dùng archive mặc định nhưng không dùng app archive | Application CDS file thiếu/sai, log bị hiểu nhầm | Xem `-Xlog:cds` và đường dẫn `SharedArchiveFile` |

## 26. Checklist hoàn tất bài thực hành

- [ ] Biết **CDS/AppCDS** khác Docker layer cache, Spring AOT và GraalVM native image.
- [ ] Chọn đúng **Spring Boot 3.3.13 / Java 17** cho ví dụ; không sử dụng lệnh của các nhánh khác.
- [ ] Tạo được **Spring Boot executable JAR**, không chọn nhầm Maven `*.jar.original` hoặc Gradle `*-plain.jar`.
- [ ] Không nhúng **fully executable launch script** khi cần dùng `jarmode=tools`.
- [ ] JAR có `spring-boot-jarmode-tools`/cấu hình `includeTools` phù hợp.
- [ ] Hiểu `extract --destination` tạo **application JAR nhỏ + lib/** cho CDS.
- [ ] Hiểu `extract --layers --destination` cho Dockerfile có bốn thư mục và cần ghép chúng vào một runtime root.
- [ ] Nếu dùng `--layers`, đã kiểm tra `BOOT-INF/layers.idx` và có đủ những layer mà Dockerfile `COPY`.
- [ ] Mã Java 17 REST app build/test thành công và endpoint `/ping` trả body `cds-ready`.
- [ ] Training chạy trên layout **đã hoàn thiện**, dùng `-XX:ArchiveClassesAtExit=application.jsa` và `-Dspring.context.exit=onRefresh`.
- [ ] File `application.jsa` được sinh **sau khi training exit thành công** và không rỗng.
- [ ] Production chạy `-XX:SharedArchiveFile=application.jsa` nhưng **không** dùng `spring.context.exit=onRefresh`.
- [ ] `-Xlog:cds` xác nhận JVM chấp nhận archive, không chỉ thấy file có tên `.jsa`.
- [ ] Training và production dùng **JVM compatible**, classpath/JAR và paths không bị thay.
- [ ] Khi đổi code/dependency/JDK/image, **train lại** archive cho version mới.
- [ ] Đã dùng Docker image runtime phù hợp và xem xét non-root user/permission/secret safety.
- [ ] CI kiểm tra build, layout, archive, endpoint, logs và image digests.
- [ ] Đánh giá startup/memory bằng nhiều lượt chạy với baseline rõ ràng, không tuyên bố cải thiện không có đo.
- [ ] Với Java 24+ hoặc Spring Boot nhánh mới, đọc lại tài liệu **AOT Cache** thay vì copy flags Java 17.

**Kết luận:** Để dùng Java CDS với Spring Boot 3.3, hãy **trích xuất đúng layout** bằng `-Djarmode=tools extract`, **huấn luyện trên application JAR đã trích xuất** với `-XX:ArchiveClassesAtExit`, rồi **dùng lại đúng runtime tree/JDK** cùng `-XX:SharedArchiveFile`. Nếu viết Dockerfile tối ưu cache, dùng `extract --layers`, `COPY` các layer theo thứ tự và chỉ **huấn luyện sau khi hoàn thiện toàn bộ classpath**. Kiểm tra **JVM logs, endpoint và ràng buộc version** trước khi coi CDS đã hoạt động trong production.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Class Data Sharing](https://docs.spring.io/spring-boot/3.3/reference/packaging/class-data-sharing.html)
- [Spring Boot 3.3 — Efficient Deployments / Extracted Layout](https://docs.spring.io/spring-boot/3.3/reference/packaging/efficient.html)
- [Spring Boot 3.3 — Dockerfiles and CDS](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Release Notes — CDS and `jarmode=tools`](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes)
- [Oracle Java 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html)
- [Oracle Java 17 — The `java` Command, CDS Restrictions](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading and Linking](https://openjdk.org/jeps/483)