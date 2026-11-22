# Tùy chỉnh thuộc tính build và quản lý thời gian dựng trong Spring Boot

## 1. Mục tiêu

Một bản phát hành Spring Boot nên trả lời được ít nhất ba câu hỏi: **đây là phiên bản nào**, **được dựng từ nguồn nào**, và **thời gian được ghi nhận có ý nghĩa gì**. Spring Boot hỗ trợ metadata chuẩn trong file `META-INF/build-info.properties`. Gradle Spring Boot Plugin cung cấp task `bootBuildInfo`; Maven Spring Boot Plugin cung cấp goal `build-info`. Khi file này nằm trong classpath, ứng dụng có thể đọc nó qua `BuildProperties` và Spring Boot Actuator có thể xuất nó ở endpoint `/actuator/info` nếu được cấu hình/expose phù hợp.

Tuy nhiên, giá trị `build.time` thường được sinh từ **thời điểm thực thi bản dựng**. Nếu giữ giá trị thay đổi liên tục, cùng một revision nguồn có thể tạo ra những artifact có nội dung khác nhau và khiến Gradle chạy lại nhiều task không cần thiết. Vì vậy cần phân biệt **metadata nhận diện phiên bản** với **thời gian vận hành/triển khai**, đồng thời lựa chọn chính sách timestamp rõ ràng.

Sau bài học, bạn sẽ:

1. Hiểu các khóa chuẩn `build.group`, `build.artifact`, `build.name`, `build.version`, `build.time` và các khóa bổ sung.
2. Cấu hình Groovy DSL/Kotlin DSL để tạo metadata, đổi thuộc tính và **loại `build.time`** khi tối ưu tính tái lập.
3. Cấu hình `spring-boot:build-info` trong Maven, thêm properties và điều khiển timestamp bằng `<time>off</time>` hoặc giá trị ISO-8601.
4. Xây một chương trình Java 17/Spring Boot có thể đọc `BuildProperties` thật và in output xác định.
5. Kiểm tra task `bootBuildInfo`, file `META-INF/build-info.properties`, Boot executable JAR và sự khác biệt giữa build time, JVM start time, Git commit time, release time và deployment time.
6. Hiểu quan hệ giữa timestamp biến đổi, Gradle `UP-TO-DATE`, build cache, reproducible archives và CI/CD.
7. Tránh ghi secret, host path, access token hoặc metadata không được phép công khai vào một tài nguyên nằm trong artifact.

**Phạm vi:** ví dụ dùng Spring Boot 3.3.13, Java 17, Gradle Spring Boot Plugin tương ứng hoặc Spring Boot Maven Plugin. Đây là mốc phiên bản để các ví dụ nhất quán, không ngụ ý bản mới nhất. Hãy sử dụng wrapper/phiên bản đang được dự án thật chấp nhận.

## 2. Thế nào là build metadata?

Build metadata mô tả **artifact được sản xuất** thay vì cấu hình vận hành hiện tại của ứng dụng. Nó thường được tạo lúc build và lưu vào artifact để có thể tra cứu sau khi phát hành.

Ví dụ file ở classpath `META-INF/build-info.properties`:

~~~properties
build.artifact=metadata-demo
build.group=com.example
build.name=metadata-demo
build.version=1.0.0
build.channel=training
build.revision=manual-local
~~~

Đây là **ví dụ với build time bị loại**, nên không có `build.time`. Thứ tự dòng do plugin ghi ra có thể khác; một file Java Properties không yêu cầu thứ tự như bảng trên.

| Khóa trong file | Ý nghĩa | Nguồn mặc định thường gặp |
| --- | --- | --- |
| `build.artifact` | Tên artifact được nhận diện | Gradle: archive base name của `bootJar`/`bootWar`; Maven: artifactId |
| `build.group` | Nhóm/tọa độ sở hữu | Gradle `project.group`; Maven `groupId` |
| `build.name` | Tên hiển thị | Gradle project name; Maven `name` hoặc giá trị suy ra |
| `build.version` | Phiên bản artifact | Gradle `project.version`; Maven `version` |
| `build.time` | Instant ghi trong metadata lúc build | Plugin-defined timestamp, có thể loại hoặc cố định |
| `build.channel`, `build.revision` | Thuộc tính mở rộng | Do nhóm xây dựng khai báo |

Các thuộc tính mở rộng sẽ được thêm **tiền tố `build.`** khi plugin tạo file. Ví dụ viết key `channel` trong Gradle `additional` thì file có `build.channel`, còn `BuildProperties.get("channel")` đọc giá trị theo tên logic `channel`.

**Metadata không phải database audit:** nếu bạn cần bằng chứng có thể kiểm chứng về người phê duyệt, provenance, chữ ký artifact hoặc SBOM, hãy dùng hệ thống release/CI và cơ chế signing/attestation phù hợp; không chỉ thêm một chuỗi tự khai báo vào build-info.

## 3. Phân biệt bốn lớp “properties” dễ nhầm

Tên gọi “build properties” có thể chỉ những đối tượng hoàn toàn khác nhau.

| Khái niệm | Nơi cấu hình/đọc | Ảnh hưởng |
| --- | --- | --- |
| Gradle project properties | `gradle.properties`, `-P...`, Providers API | Đầu vào cho build scripts/tasks |
| Spring Boot build-info properties | `META-INF/build-info.properties`, `BuildProperties` | Metadata đã được đóng vào classpath/artifact |
| Spring runtime configuration | `application.properties`, environment, system properties, Config Server | Hành vi ứng dụng khi khởi động/chạy |
| CI/release metadata | Git revision, CI run ID, signed provenance, deployment records | Nhận diện nguồn/phê duyệt/đợt triển khai |

Ví dụ:

~~~properties
# gradle.properties
org.gradle.caching=true
~~~

`org.gradle.caching` điều khiển build cache của Gradle; nó **không trở thành** `build.org.gradle.caching` trong Boot JAR. Ngược lại:

~~~properties
# src/main/resources/application.properties
app.feature.enabled=true
~~~

là cấu hình ứng dụng; nó **không tự tạo** `BuildProperties`. Muốn có metadata Boot build cần `springBoot { buildInfo(...) }` hoặc Maven goal tương ứng.

Cũng không được coi `-Pversion=...`, `-Dspring.profiles.active=...` và `build.version` là cùng một công cụ. Project build version phải được định nghĩa ở nguồn cấu hình có quyền kiểm soát, sau đó metadata mới phản ánh/ghi đè theo thiết kế.

## 4. Cách Spring Boot Gradle Plugin tạo metadata

Khi áp dụng Spring Boot Gradle Plugin với Java plugin, bạn có thể bật:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Lệnh trên đăng ký task `bootBuildInfo`. Trong Spring Boot 3.3, task được nối với vòng đời `classes` khi Java plugin có mặt; output mặc định là file `META-INF/build-info.properties` trong output resources của main source set, thường:

~~~text
build/resources/main/META-INF/build-info.properties
~~~

Sau `bootJar`, file thường nằm trong executable archive dưới:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

**Những điểm cần nhớ:**

- Chỉ apply Spring Boot plugin chưa đồng nghĩa `build-info.properties` tự được tạo: phải **bật `buildInfo`**.
- File đó thuộc main runtime classpath, khác với `src/test/resources`.
- Gradle `bootJar` sử dụng main classes/resources; metadata được đóng cùng ứng dụng, không cần copy bằng shell thủ công.
- `bootBuildInfo` không phải `bootJar`; task đầu tạo file metadata, task sau tạo executable archive.
- Không sửa file đã sinh trong `build/resources/main` bằng tay: `clean` hoặc lần build sau có thể ghi lại từ DSL.

### 4.1. Những thuộc tính nào có thể tùy chỉnh?

Spring Boot Gradle plugin cho phép chỉnh các khóa chuẩn `artifact`, `group`, `name`, `version`, cùng với `additional`. Ví dụ **fragment Groovy**:

~~~groovy
springBoot {
    buildInfo {
        properties {
            artifact = 'public-service'
            group = 'com.example.services'
            name = 'Public Service'
            version = '2.3.4'
            additional = [
                'channel': 'release',
                'schema': 'v1'
            ]
        }
    }
}
~~~

Đây là **fragment build-info metadata**. Nó thay giá trị được ghi trong file và được Spring Boot đọc; **không tự đổi** `project.group`, `project.version`, tên file của task `bootJar` hoặc publishing coordinates. Nếu metadata version là `2.3.4` nhưng Gradle project version vẫn `1.0.0`, release pipeline có thể công bố thông tin mâu thuẫn.

Vì vậy, trong đa số dự án nên **giữ group/artifact/version mặc định lấy từ project**; chỉ ghi đè khi thực sự có contract rõ ràng. Thuộc tính mở rộng phù hợp hơn cho những thông tin phụ như revision, release channel, schema version.

## 5. Gradle Groovy DSL — project hoàn chỉnh, metadata không có build.time

Chúng ta dựng ứng dụng console `metadata-demo` dùng Java 17. Bản chính loại `build.time` để bản dựng có đầu ra ổn định hơn; sau đó sẽ thử bật lại time để thấy trade-off.

Cấu trúc:

~~~text
metadata-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/com/example/metadata/MetadataApplication.java
│   └── test/java/com/example/metadata/MetadataApplicationTest.java
└── build/                            # Gradle tạo khi build
~~~

Nếu dùng Groovy DSL, tệp `settings.gradle`:

~~~groovy
rootProject.name = 'metadata-demo'
~~~

Tệp `build.gradle` đầy đủ:

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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'channel': 'training',
                'revision': 'manual-local'
            ]
        }
    }
}
~~~

**Phần then chốt:** `excludes = ['time']` là DSL chính thức của Spring Boot 3.3 để **không ghi `build.time`**. Nó không phải lệnh xóa property từ một file đang tồn tại; plugin sinh file mới theo cấu hình. `additional` chỉ thêm hai giá trị ổn định; chúng trở thành `build.channel` và `build.revision`.

Không cố định thủ công `artifact`/`group`/`version` ở ví dụ này, nên metadata mặc định đi theo `rootProject.name`, `group` và `version`. Nếu bạn đổi `rootProject.name` hoặc `version`, output mong đợi và archive name thay đổi tương ứng.

**Yêu cầu môi trường:** cần Gradle wrapper hoặc Gradle CLI tương thích và JDK 17 toolchain có sẵn/có cơ chế provision phù hợp. Những file `settings.gradle` và `build.gradle` không tự tạo `gradlew`. Khi dùng Spring Initializr, wrapper thường được cung cấp; trên Windows dùng `.\gradlew.bat`.

## 6. Gradle Kotlin DSL — cấu hình tương đương

Nếu repository dùng Kotlin DSL, **chọn cặp file này thay cho cặp Groovy**, không để cả `build.gradle` và `build.gradle.kts` cùng được coi là hai scripts nối tiếp.

Tệp `settings.gradle.kts`:

~~~kotlin
rootProject.name = "metadata-demo"
~~~

Tệp `build.gradle.kts` đầy đủ:

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

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(
                mapOf(
                    "channel" to "training",
                    "revision" to "manual-local"
                )
            )
        }
    }
}
~~~

Khác biệt quan trọng so với Groovy:

- `excludes` là Gradle `SetProperty`, nên Kotlin dùng `excludes.set(setOf("time"))`.
- `additional` là `MapProperty`, nên Kotlin dùng `additional.set(mapOf(...))`.
- Không cần tự đăng ký task mới có tên `bootBuildInfo`; DSL `springBoot.buildInfo` làm điều đó.

**Điểm kiểm chứng:** hai phiên bản DSL tạo cùng những khóa logic trong `build-info.properties`, với `build.time` vắng mặt. Không so sánh bytes giữa hai môi trường khác Gradle/JDK rồi kết luận DSL khác hành vi; phải giữ toolchain/dependencies tương ứng để so sánh công bằng.

## 7. Java 17: đọc metadata thật bằng BuildProperties

Tạo `src/main/java/com/example/metadata/MetadataApplication.java`:

~~~java
package com.example.metadata;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    CommandLineRunner reportMetadata(BuildProperties build) {
        return args -> {
            System.out.println("ARTIFACT=" + build.getArtifact());
            System.out.println("GROUP=" + build.getGroup());
            System.out.println("VERSION=" + build.getVersion());
            System.out.println("CHANNEL=" + build.get("channel"));
            System.out.println("REVISION=" + build.get("revision"));

            if (build.getTime() == null) {
                System.out.println("TIME=<absent>");
            } else {
                System.out.println("TIME=" + build.getTime());
            }
        };
    }
}
~~~

`BuildProperties` thuộc `org.springframework.boot.info.BuildProperties`. Spring Boot tạo bean từ file `META-INF/build-info.properties` khi file đó tồn tại trong classpath. Class có các method `getArtifact()`, `getGroup()`, `getName()`, `getVersion()` và `getTime()`; khóa tùy chỉnh đọc bằng `get("channel")`/`get("revision")`, **không kèm tiền tố `build.`**.

`getTime()` trả kiểu `java.time.Instant` hoặc `null` nếu không có property time phù hợp. Không được gọi `build.getTime().toString()` vô điều kiện khi metadata đã loại time.

Trong bài dùng dependency `spring-boot-starter`, không bắt buộc thêm Actuator hay Web starter chỉ để inject `BuildProperties` từ auto-configuration của Spring Boot. Nếu project bỏ task `buildInfo` mà vẫn inject bean không có fallback, application context có thể không khởi động được vì thiếu `BuildProperties`; đây là dấu hiệu build metadata resource chưa được sinh/đóng gói.

### 7.1. JUnit test để bảo đảm metadata đúng contract

Tạo `src/test/java/com/example/metadata/MetadataApplicationTest.java`:

~~~java
package com.example.metadata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest
class MetadataApplicationTest {

    @Autowired
    private BuildProperties build;

    @Test
    void buildMetadataHasExpectedValues() {
        assertEquals("metadata-demo", build.getArtifact());
        assertEquals("com.example", build.getGroup());
        assertEquals("1.0.0", build.getVersion());
        assertEquals("training", build.get("channel"));
        assertEquals("manual-local", build.get("revision"));
        assertNull(build.getTime());
    }
}
~~~

Test này kiểm tra rằng file đã được tạo và bean có đúng giá trị với **cấu hình exclude time**. Nếu sau này có chủ đích đổi version/channel hoặc giữ build.time, phải cập nhật assertions tương ứng; không nên hardcode một số version trong test release thật mà quên sửa khi bump version.

## 8. Chạy và kiểm chứng từ task tới executable JAR

Trong thư mục `metadata-demo` với Gradle wrapper hợp lệ:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew clean bootBuildInfo
./gradlew clean build
java -jar build/libs/metadata-demo-1.0.0.jar
~~~

Lệnh `./gradlew clean bootBuildInfo` minh họa task trực tiếp; lệnh `./gradlew clean build` dựng lại đầy đủ và thực hiện test theo Java lifecycle. Khi build chỉ có Gradle Java plugin và chưa khai báo Java source, output có thể `NO-SOURCE`; nhưng project này đã có Java main/test source nên compiler và test tasks có việc thực.

Trên Windows PowerShell, dùng `.\gradlew.bat` thay `./gradlew`. Khi không có wrapper, dùng Gradle cài tương thích hoặc tạo wrapper theo quy trình repository.

**Các dòng riêng do chương trình in** khi chạy executable JAR với cấu hình ở mục 5/6:

~~~text
ARTIFACT=metadata-demo
GROUP=com.example
VERSION=1.0.0
CHANNEL=training
REVISION=manual-local
TIME=<absent>
~~~

Spring Boot có thể in thêm startup logs; đoạn trên là stdout từ `CommandLineRunner`, không phải toàn bộ output terminal. Nếu dùng main class khác, đổi group/version hoặc khai báo metadata khác, kết quả sẽ thay đổi theo cấu hình thật.

### 8.1. Xác định vị trí file metadata

Trong Gradle, kiểm tra:

~~~text
build/resources/main/META-INF/build-info.properties
~~~

Đây là output thông thường của task trong Spring Boot 3.3. Nếu task destination directory đã được tùy chỉnh, đường dẫn có thể khác. Sau `bootJar`:

~~~bash
jar tf build/libs/metadata-demo-1.0.0.jar
~~~

Tìm entry:

~~~text
BOOT-INF/classes/META-INF/build-info.properties
~~~

Có file trong JAR chứng minh nó đã được đóng gói; **chưa đủ** chứng minh mọi giá trị đều đúng. Để xem nội dung, dùng công cụ ZIP hỗ trợ, chẳng hạn trên Linux/macOS nếu có `unzip`:

~~~bash
unzip -p build/libs/metadata-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
~~~

Nếu không có `unzip`, có thể giải nén archive vào một thư mục kiểm tra riêng bằng JDK `jar` rồi đọc entry. Không dùng `jar -xf` bừa vào project root vì có thể tạo/ghi đè nhiều file.

### 8.2. Khi kiểm tra bản build mới

Không chỉ nhìn thấy file tồn tại rồi kết luận đó là file từ lượt build hiện tại. Để tránh nhầm artifact cũ:

- Chạy `clean` khi thật sự muốn tạo lại local outputs.
- Xem log `bootBuildInfo`, `processResources`, `bootJar`.
- Kiểm tra path đúng với module/version/classifier hiện tại.
- Kiểm tra nội dung property, không chỉ tên file.
- Chạy chính JAR dự định publish bằng `java -jar`.
- Nếu CI sử dụng nhiều modules, gọi đúng task path, ví dụ `:api-service:bootJar` nếu module `api-service` có thật.

## 9. Vấn đề của build.time mặc định

### 9.1. Một instant thay đổi làm output khác

Với cấu hình đơn giản:

~~~groovy
springBoot {
    buildInfo()
}
~~~

task tạo metadata mặc định gồm `build.time` là instant tại thời điểm build. File có thể chứa dòng kiểu:

~~~properties
build.time=2026-11-09T02:00:00Z
~~~

**Đây chỉ là chuỗi timestamp minh họa**, không phải giờ dự kiến của lần chạy trên máy người học. Ở lần build khác, instant có thể đổi dù Java source, dependency versions và group/version không đổi.

Hậu quả:

1. File `build-info.properties` thay đổi bytes.
2. Các task downstream phụ thuộc output resources có thể phải xử lý lại.
3. Archive JAR cuối có thể khác checksum chỉ vì timestamp.
4. Build cache và Gradle up-to-date checks khó phát huy hiệu quả đối với phần việc liên quan.
5. Hai người build cùng commit có thể tạo binary khác nhau mà không có thay đổi nghiệp vụ.

Tài liệu Spring Boot 3.3 nêu rằng với default time, task `bootBuildInfo` **không up-to-date** và đầu ra thay đổi liên tục. Do đó việc xóa time có ý nghĩa trực tiếp đối với hiệu năng và tính repeatable của build, chứ không chỉ là thay đổi cách trình bày endpoint info.

### 9.2. Hai chính sách cần chọn tường minh

| Chính sách | Build metadata | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Ghi thời gian build thực | Có `build.time` động | Biết instant thực thi plugin | Đầu ra thay đổi, mất ổn định/cache; cùng source có thể khác bytes |
| Bỏ build time | Không có `build.time` | Ổn định hơn, thuận lợi repeatability | Không thể hỏi `BuildProperties.getTime()` để biết thời điểm build |
| Ghi một instant cố định có ý nghĩa | `build.time` cố định | Có metadata thời gian ổn định | Phải quản lý nguồn timestamp, giải thích nó đại diện cho sự kiện gì |

**Không có lựa chọn tuyệt đối đúng cho mọi hệ thống.** Với dịch vụ có yêu cầu reproducible builds/supply chain, loại timestamp ngẫu nhiên thường hợp lý. Với pipeline cần audit **thời điểm job chạy thật**, nên lưu timestamp trong CI deployment record, build run metadata hoặc provenance có chữ ký, thay vì biến binary theo từng giây.

### 9.3. Khuyến nghị Gradle 3.3: excludes thay vì “time = null” từ bản cũ

Theo DSL Spring Boot 3.3:

**Groovy fragment:**

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
springBoot {
    buildInfo {
        excludes.set(setOf("time"))
    }
}
~~~

Đây là cách được tài liệu hóa cho dòng 3.3. Một số bài viết Spring Boot 2.x cũ dùng `properties.time = null` để bỏ time; **không sao chép cú pháp đời cũ** vào dự án 3.3 khi đã có API `excludes`. Không đặt cả hai fragment mâu thuẫn trong cùng module.

### 9.4. “Bỏ time” không tự bảo đảm binary reproducible hoàn toàn

Ngay khi `build.time` biến mất, binary JAR vẫn có thể đổi nếu:

- Đầu vào source hoặc dependencies thay đổi.
- Java compiler/toolchain hoặc annotation processor sinh dữ liệu không ổn định.
- Archive entries chứa timestamps, filesystem ordering hoặc absolute paths không ổn định.
- Manifest, Git metadata hoặc custom resource processing ghi timestamp khác.
- Code generator dùng `new Date()`, `Instant.now()`, random UUID hoặc network data mà không ghi input tương ứng.
- Packaging/plugin/JVM/OS khác nhau làm output khác.

**Reproducibility là thuộc tính của toàn bộ build**, không chỉ của một property. Loại `build.time` là một bước quan trọng, nhưng phải kiểm tra deterministic inputs, archive file ordering/timestamps, dependency locks và toolchain nếu cần bit-for-bit identical output.

## 10. Tùy chọn: kiểm tra hiệu quả incremental build

Để quan sát tác động của build time:

**Trường hợp A — để mặc định có time:**

~~~groovy
springBoot {
    buildInfo()
}
~~~

Chạy hai lần không đổi mã nguồn:

~~~bash
./gradlew build --info
./gradlew build --info
~~~

Theo mô tả chính thức, `bootBuildInfo` thường không ở trạng thái `UP-TO-DATE` khi time động được tạo; downstream tasks như `classes`, một số tests hoặc packaging có thể bị ảnh hưởng. **Không khẳng định mọi task luôn chạy** vì Gradle version, task graph và cache policy có thể khác.

**Trường hợp B — exclude time:**

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Chạy cùng cặp lệnh:

~~~bash
./gradlew build --info
./gradlew build --info
~~~

Nếu inputs không đổi, `bootBuildInfo` có cơ hội trở thành `UP-TO-DATE` và downstream outputs ổn định hơn. Đây là ví dụ đúng theo lý do của tính năng.

### 10.1. Đừng nhầm UP-TO-DATE với FROM-CACHE

- `UP-TO-DATE`: outputs trong workspace hiện tại vẫn phù hợp inputs và local execution history.
- `FROM-CACHE`: task output được restore từ Gradle build cache nếu task cacheable và có entry hợp lệ.
- `EXECUTED`: task actions đã chạy trong lượt này.
- `NO-SOURCE` hoặc `SKIPPED`: task không có input hoặc được bỏ qua theo điều kiện.

Bỏ `build.time` giúp giảm input/output biến động; nó **không bảo đảm** task `bootBuildInfo` hoặc `bootJar` luôn `FROM-CACHE`. Để biết task nào cacheable, phải xem implementation/plugin version và log thật.

### 10.2. Configuration cache không phải build-info time

`--configuration-cache` lưu kết quả configuration/task graph; `bootBuildInfo` tạo file metadata trong execution/build process. Việc dùng configuration cache không thay thế cơ chế điều khiển `build.time`. Có thể cấu hình đồng thời, nhưng phải đảm bảo các plugins/custom tasks tuân thủ configuration-cache requirements.

Nếu Gradle báo problem về task `bootBuildInfo`/serialization, xem report và plugin version; không “sửa” bằng cách xóa metadata hoặc tắt mọi cache một cách vô điều kiện.

## 11. Maven: tạo build-info và tùy chỉnh thời gian

Maven Spring Boot Plugin có goal `spring-boot:build-info`. Khác với Gradle, Maven sử dụng configuration XML và lifecycle executions. Dưới đây là **project Maven thay thế Gradle** với cùng Java source ở mục 7.

Tệp `pom.xml` hoàn chỉnh:

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
    <artifactId>metadata-demo</artifactId>
    <name>metadata-demo</name>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                        <configuration>
                            <time>off</time>
                            <additionalProperties>
                                <channel>training</channel>
                                <revision>manual-local</revision>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là POM Maven đầy đủ cho ví dụ. Nó dùng Spring Boot starter parent để quản lý dependency/plugin defaults và execution `repackage` khi plugin khai báo. Execution bổ sung `build-info` được định nghĩa trong `build/plugins`; không cần tạo task Gradle `bootBuildInfo` trong POM.

**Chi tiết `<time>off</time>`:** đây là cách Spring Boot Maven Plugin tài liệu hóa để **loại `build.time`** khỏi file. Các khóa mở rộng trong `<additionalProperties>` trở thành `build.channel` và `build.revision`.

**Chi tiết `project.build.outputTimestamp`:** giá trị ISO-8601 cố định trong ví dụ dành cho chính sách timestamp của archive/plugin hỗ trợ reproducible outputs. Nó **không phải thời gian máy thực tế ở lượt chạy**. Trong POM này, `<time>off</time>` vẫn khiến `build.time` vắng mặt dù `project.build.outputTimestamp` được khai báo. Không coi một timestamp cố định tùy ý là thông tin audit production.

### 11.1. Lệnh Maven và file output

~~~bash
mvn -version
mvn clean test
mvn package
java -jar target/metadata-demo-1.0.0.jar
~~~

Nếu repository có Maven wrapper, dùng `./mvnw` trên Unix hoặc `.\mvnw.cmd` trên Windows. Khi `mvn package`, Maven sẽ tạo file `target/classes/META-INF/build-info.properties` thông qua goal `build-info`. Spring Boot `repackage` đưa file metadata vào executable archive, thường dưới `BOOT-INF/classes/META-INF/build-info.properties`.

Trong project Maven ở ví dụ, code Java ở mục 7 và test ở mục 7.1 cho kết quả giống bản Gradle: thông tin artifact/group/version/channel/revision và `TIME=<absent>`. Nếu Maven goal không chạy, ứng dụng có thể không có `BuildProperties` bean. Khi đó kiểm tra `mvn help:effective-pom` và log goal, không tự viết file build-info bằng tay.

### 11.2. Nếu không kế thừa spring-boot-starter-parent

Một POM dùng parent khác hoặc chỉ import Boot BOM có thể **không** kế thừa plugin management/execution giống Spring Boot parent. Khi đó phải cấu hình plugin version và executions `build-info`, `repackage` phù hợp. Đừng copy nguyên fragment có goal `repackage` nếu project đã định nghĩa goal này ở parent khác, vì có thể tạo duplicate executions.

Kiểm chứng:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn spring-boot:help -Ddetail=true -Dgoal=build-info
~~~

Lệnh `spring-boot:help` yêu cầu plugin prefix/resolution hợp lệ. Đọc version/goal/config đang có hiệu lực; không đoán rằng mọi Maven project Spring Boot tự sinh file build-info.

## 12. Quản lý build time trong Maven: ba lựa chọn

### 12.1. Giữ thời gian động mặc định

Nếu bỏ `<time>off</time>` và không thiết lập `project.build.outputTimestamp`, goal `build-info` thường dùng thời điểm bắt đầu phiên Maven session làm `build.time` (theo Spring Boot Maven Plugin 3.3). Giá trị này biến thiên theo lần chạy; hai artifact từ cùng source có thể khác nhau.

Điều này phù hợp khi bạn chủ đích muốn ghi thời gian thực thi phiên build, nhưng không nên coi đó là Git commit time hay deployment time.

### 12.2. Bỏ time để ưu tiên ổn định

Trong cấu hình goal `build-info`:

~~~xml
<configuration>
    <time>off</time>
</configuration>
~~~

Đây là **fragment thay cho** phần configuration dài trong POM ở mục 11, không tạo một execution thứ hai. Khi sinh metadata, file không có `build.time` và `BuildProperties.getTime()` trả `null`. Bất kỳ controller/test nào hiển thị time phải xử lý null.

Spring Boot Maven Plugin cũng hỗ trợ danh sách `excludeInfoProperties`; nhưng `time>off</time>` là cách trực tiếp, dễ đọc và được tài liệu hóa cho nhu cầu chỉ bỏ time.

### 12.3. Ghi một instant cố định có ý nghĩa

Nếu project cần timestamp đại diện cho **release event** đã được kiểm soát, có thể đặt giá trị ISO-8601 parseable bởi `Instant.parse`:

~~~xml
<configuration>
    <time>2025-01-01T00:00:00Z</time>
</configuration>
~~~

Ví dụ timestamp này **chỉ minh họa cú pháp**, không phải thời gian phát hành thật. Trong pipeline production, lấy timestamp từ một nguồn đã định nghĩa (chẳng hạn release manifest hoặc commit/release epoch theo chính sách), rồi kiểm soát giá trị đó qua CI/POM property.

Nếu muốn dùng giá trị Maven property, cấu hình goal có thể tham chiếu:

~~~xml
<configuration>
    <time>${project.build.outputTimestamp}</time>
</configuration>
~~~

Ở đây `project.build.outputTimestamp` phải được định nghĩa/được build system resolve thành một timestamp hợp lệ. Nếu không khai báo, behavior mặc định của Spring Boot Maven Plugin có thể lấy session start time; muốn build thực sự tái lập, đừng dựa vào một giá trị không xác định.

**Lưu ý:** timestamp trong `build.time` và timestamp của ZIP archive entries là **hai khái niệm khác nhau**. Cấu hình `project.build.outputTimestamp` ảnh hưởng reproducible archive timestamp theo các Maven plugins hỗ trợ; `build-info time` quyết định nội dung của file metadata. Muốn binary bit-for-bit giống nhau, phải quản lý cả hai và những inputs khác.

## 13. “Thời gian dựng” còn có nhiều ý nghĩa

| Mốc thời gian | Sự kiện | Phần mềm/cơ chế thường ghi |
| --- | --- | --- |
| Git commit time | Commit được tạo/ghi trong VCS | Git metadata |
| CI job start time | Runner bắt đầu job | CI server |
| Build-info time | Timestamp plugin ghi vào `build.time` | Spring Boot Gradle/Maven Plugin |
| Artifact publication time | Artifact được đưa lên repository | Artifact repository |
| Release approved time | Release được phê duyệt | Release management |
| Deployment time | Bản được đưa lên môi trường | CD system/platform |
| Application startup time | JVM/Spring context bắt đầu | Runtime metrics/logging |

Không nên gọi chúng bằng cùng một tên “build date”. Ví dụ một artifact được dựng từ 10 giờ sáng, publish buổi trưa và triển khai tối hôm sau. `BuildProperties.getTime()` **không trả về deployment time**. Khi restart container, ứng dụng **không thay đổi** build-info time đã đóng gói.

Nếu cần hỏi “ứng dụng đã chạy bao lâu?”, dùng runtime uptime/startup telemetry, không dùng metadata bản dựng. Nếu cần hỏi “release nào đang chạy ở staging?”, sử dụng version/revision cùng deployment record.

### 13.1. Giờ địa phương và UTC

`build.time` nên dùng một **Instant** parseable, ví dụ:

~~~text
2025-01-01T00:00:00Z
~~~

`Z` biểu thị UTC. Bất kể máy build đặt timezone Asia/Ho_Chi_Minh, UTC hay một múi khác, một Instant là thời điểm toàn cục. Cách trình bày theo timezone người xem nên thực hiện ở UI hoặc logging/reporting layer.

Java 17 chuyển Instant sang local datetime khi cần:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeExample {

    public static void main(String[] args) {
        Instant buildTime = Instant.parse("2025-01-01T00:00:00Z");
        ZonedDateTime local =
                buildTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(buildTime);
        System.out.println(local);
    }
}
~~~

Lưu file riêng `TimeExample.java`, biên dịch/chạy bằng JDK 17:

~~~bash
javac TimeExample.java
java TimeExample
~~~

Stdout chính xác:

~~~text
2025-01-01T00:00:00Z
2025-01-01T07:00+07:00[Asia/Ho_Chi_Minh]
~~~

Đây là một **Java SE example độc lập** để học cách biểu diễn thời gian, không cần Spring Boot. Giá trị ví dụ là một mốc cố định, không đọc thời gian hệ thống hiện tại nên output không thay đổi qua các lần chạy.

### 13.2. Đừng dùng formatted local time làm dữ liệu chuẩn

Các chuỗi kiểu `09/11/2026 09:00` không chứa timezone/offset, có thể bị hiểu khác nhau giữa máy build/CI và máy vận hành. Dùng ISO-8601 với `Z` hoặc offset hợp lệ cho metadata machine-readable. Nếu giữ `build.time`, không ghi chuỗi tùy ý như `Mon Nov 9` rồi giả định `BuildProperties.getTime()` parse thành công.

## 14. Build metadata và Actuator /actuator/info

### 14.1. BuildProperties không bắt buộc endpoint HTTP

Bean `BuildProperties` được ứng dụng dùng trực tiếp từ build-info resource. Vì vậy ví dụ console ở mục 7 chỉ cần Spring Boot starter, không có HTTP endpoint. Để xuất build info ra HTTP cần thêm **Actuator và web application**, cùng exposure policy.

Với Gradle Groovy, dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Kotlin tương đương:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Với Maven, thêm hai `dependency` tương ứng vào `<dependencies>`. Đây là **tùy chọn mở rộng**, không cần nếu chỉ dùng BuildProperties qua Java code.

Trong `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info
management.info.build.enabled=true
~~~

Theo Spring Boot 3.3, chỉ endpoint `health` thường được expose qua HTTP mặc định; vì vậy cần chủ động thêm `info`. `BuildInfoContributor` tự có khi build-info resource hiện diện và tính năng được bật. `management.info.build.enabled=true` làm rõ ý định, còn chính sách của hệ thống có thể thay đổi mặc định.

Khởi chạy ứng dụng web sau khi bổ sung starter:

~~~bash
./gradlew bootRun --args='--server.port=18080'
~~~

Trong terminal khác:

~~~bash
curl -fsS http://localhost:18080/actuator/info
~~~

JSON có thể chứa một object `build` với các khóa artifact, group, name, version, channel, revision; các trường khác phụ thuộc contributors và runtime configuration. Khi time bị exclude, đừng kỳ vọng trường `time` luôn xuất hiện. Không hardcode toàn bộ JSON byte-for-byte vì serialization/ordering và contributors có thể khác.

### 14.2. Security: metadata cũng có thể nhạy cảm

Không đặt vào `build-info.properties`:

- Access token, repository password, signing key, secret API key.
- Internal filesystem path, full CI environment dump, host username hoặc IP nhạy cảm.
- Thông tin môi trường production không cần trong artifact.
- Full Git remote URL có credentials.

Ngay cả khi không expose `/actuator/info`, bất kỳ ai có executable JAR có thể giải nén `META-INF/build-info.properties`. **Không xem việc tắt HTTP endpoint là biện pháp bảo vệ secrets trong artifact**.

Nếu bạn muốn hiển thị revision, dùng một identifier được phép công khai (ví dụ short commit hash) theo policy. Không tự thêm full branch names/private ticket IDs khi endpoint có thể được public.

## 15. Tùy chỉnh thuộc tính khác: group, name, artifact, version và additional

### 15.1. Chỉnh thuộc tính chuẩn theo DSL

**Gradle Groovy fragment:**

~~~groovy
springBoot {
    buildInfo {
        properties {
            artifact = 'course-service'
            group = 'com.example.training'
            name = 'Course Service'
            version = '2.1.0'
        }
    }
}
~~~

**Gradle Kotlin fragment:**

~~~kotlin
springBoot {
    buildInfo {
        properties {
            artifact.set("course-service")
            group.set("com.example.training")
            name.set("Course Service")
            version.set("2.1.0")
        }
    }
}
~~~

**Các đoạn này chỉ là ví dụ ghi đè metadata**. Nếu áp dụng lên project `metadata-demo` của bài, output Java ở mục 8 sẽ không còn artifact/group/version như trước; phải cập nhật assertions/test theo contract mới. Đừng kết hợp cùng lúc hai khối buildInfo khai báo giá trị mâu thuẫn.

Với Maven, mặc định group/artifact/version/name lấy từ POM. Muốn chỉnh “phần nhận diện release”, thường sửa **`groupId`, `artifactId`, `version` và `name` của POM** từ một nguồn thật, không tự đặt metadata khác hẳn tọa độ artifact đã publish. Maven plugin `build-info` còn có option `excludeInfoProperties`, outputFile và additionalProperties; cần đọc effective POM/plugin version nếu tùy biến sâu.

### 15.2. Thuộc tính bổ sung có ý nghĩa gì?

Những metadata bổ sung hữu ích:

| Key logic | Ví dụ | Lưu ý |
| --- | --- | --- |
| `channel` | `training`, `snapshot`, `release` | Chỉ dùng label theo policy tổ chức |
| `revision` | Short Git SHA được phê duyệt | Phải là revision thực, không placeholder trong release |
| `schema` | `v1` | Version cho hợp đồng metadata, không phải app version |
| `builder` | `ci` | Không ghi username/host machine nhạy cảm |
| `toolchain` | `java-17` | Mô tả compiler target; không nhất thiết là runtime JVM |
| `pipeline` | ID được công khai | Có thể dẫn tới CI run records, cân nhắc exposure |

Khi đặt `additional`, plugin thêm tiền tố `build.`. Đừng tự ghi key `build.channel` trong map nếu mục tiêu là `build.channel`, vì có thể tạo key thừa `build.build.channel`. Tên key nên đơn giản, ổn định và không chứa giá trị không chuẩn hóa.

### 15.3. Thuộc tính lấy từ CI: đừng gọi API hệ thống tại configuration time vô cớ

Một anti-pattern là:

~~~groovy
springBoot {
    buildInfo {
        properties {
            additional = [
                'revision': System.getenv('GIT_COMMIT'),
                'hostname': java.net.InetAddress.localHost.hostName
            ]
        }
    }
}
~~~

Đoạn này **không khuyến nghị dùng**: nó đọc environment khi Gradle configuration, ghi hostname potentially sensitive và tạo dependency on machine state. Nó có thể ảnh hưởng configuration cache và khả năng tái lập build.

**Chiến lược tốt:** cung cấp một CI variable được kiểm soát, dùng Gradle Providers API/lazy values cho task inputs, chọn fallback rõ ràng trong development và tránh ghi dữ liệu không cần thiết. Spring Boot Gradle docs xác nhận additional property có thể được tính lazy qua `Provider`. Ví dụ Kotlin fragment minh họa khi project thật có `CI_COMMIT_SHA`:

~~~kotlin
springBoot {
    buildInfo {
        properties {
            additional.put(
                "revision",
                providers.environmentVariable("CI_COMMIT_SHA").orElse("local")
            )
        }
    }
}
~~~

Đây là **fragment bổ sung**, thay cho setting `additional.set(mapOf(...))` ở bản đầy đủ nếu muốn một nguồn revision khác. Với production, policy phải yêu cầu biến có thật chứ không âm thầm publish `local` như release metadata. Không giữ cả static `revision` và dynamic `revision` mà không xác định giá trị nào được dùng.

Lưu ý: nếu bạn chủ đích đưa Git SHA vào file, output **sẽ khác khi source revision khác**, và đó là thay đổi hợp lệ của build inputs. Reproducibility nghĩa là cùng source và môi trường **được định nghĩa** tạo cùng output; không phải ép mọi revision khác nhau dùng cùng một file metadata.

## 16. Tương quan với Git metadata

Spring Boot còn hỗ trợ `git.properties` (qua plugin phù hợp) để Actuator hiển thị Git branch, commit id/time. Nó **không phải** cùng file với `build-info.properties`:

~~~text
classpath:/META-INF/build-info.properties  → BuildProperties
classpath:/git.properties                  → GitProperties
~~~

Thông tin khác nhau:

- `build.version`: version do build tool/POM cung cấp.
- `build.revision`: thuộc tính tùy chỉnh nếu team chủ động ghi, nên khớp nguồn CI.
- `git.commit.id`: giá trị từ Git metadata.
- `git.commit.time`: thời điểm commit, không phải thời điểm build.
- `build.time`: instant do build-info plugin quyết định.

Nếu team có Git plugin tạo `git.properties` và đồng thời ghi `build.revision`, nên có test/assertion kiểm tra chúng cùng một nguồn. Không tự sửa Git commit time để “làm đẹp” build.time. Với một release artifact, commit id thường là khóa truy vết ổn định hơn build timestamp đơn lẻ.

## 17. Build metadata và ZIP timestamps: hai tầng độc lập

### 17.1. Metadata file

Khi trong `build-info.properties` có:

~~~properties
build.time=2025-01-01T00:00:00Z
~~~

đây là **nội dung text** của một resource. Giữ nó cố định hoặc loại hẳn giúp file ổn định.

### 17.2. Archive entry timestamps

Một JAR là ZIP archive; mỗi entry trong đó có metadata như timestamp. Một plugin/archiver có thể ghi thời gian file của từng entry, dẫn đến JAR bytes khác nhau dù `build-info.properties` giống nhau. Do đó cần cấu hình reproducible archive ở tầng Gradle/Maven nếu chính sách yêu cầu byte-for-byte equivalence.

Với Gradle `AbstractArchiveTask`, một số cấu hình hữu ích (fragment tùy chọn) là:

**Groovy:**

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

**Kotlin:**

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Đây là một phần của chính sách reproducible archives, **không phải thay thế** cấu hình `buildInfo.excludes`. Những Gradle versions mới có defaults riêng; đọc chính xác wrapper version để tránh tự khẳng định một default.

Với Maven, các archiver/plugins tương thích có thể dùng:

~~~xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Một giá trị ổn định có thể được dùng để chuẩn hóa timestamp archive entries; ví dụ là ISO-8601. Nếu CI muốn thời gian phát hành là một metadata riêng, hãy định nghĩa nguồn thống nhất và không ngẫu nhiên đổi `project.build.outputTimestamp` mỗi lần retry job khi đang theo đuổi reproducibility.

### 17.3. Vì sao kiểm checksum JAR có thể là kiểm tra bổ sung?

Nếu hai build từ cùng commit/dependencies/toolchain/policy tạo file `metadata-demo-1.0.0.jar` khác checksum, xem:

1. `build-info.properties` có timestamp động không?
2. Generated Git metadata có thời gian lấy từ system clock không?
3. ZIP entry timestamps/order có ổn định không?
4. Java compiler/annotation processor/codegen có dữ liệu không xác định không?
5. Build tools và environment có thật sự tương đồng không?
6. Có build step thêm signature, launch script hay dữ liệu CI không ổn định không?

Dùng checksum như tín hiệu chẩn đoán; **không kết luận hai JAR khác bytes là bị tấn công** trước khi kiểm tra những nguồn biến động hợp lệ.

## 18. Kiểm thử và CI/CD cho chính sách build metadata

Một pipeline có thể dùng checklist:

1. **Khóa inputs:** Gradle wrapper/Maven version, Spring Boot plugin, Java toolchain, dependency versions.
2. **Định nghĩa contract:** metadata nào được xem là bắt buộc và được phép công khai?
3. **Chọn chính sách thời gian:** giữ time, loại time hoặc cố định một instant từ nguồn release có kiểm soát.
4. **Gắn revision đúng nguồn:** CI job bắt buộc đưa Git commit SHA, tránh fallback giả trong release.
5. **Sinh metadata:** Gradle `bootBuildInfo` hoặc Maven `build-info`.
6. **Chạy tests:** kiểm tra `BuildProperties` với version/group/channel/revision tương ứng.
7. **Đóng gói:** `bootJar`/Maven `package` + `repackage`.
8. **Kiểm file thực:** đọc `META-INF/build-info.properties` bên trong archive đã publish.
9. **Smoke test:** chạy `java -jar`, xác minh output/endpoint nếu phù hợp.
10. **Đối chiếu record:** commit SHA, CI run, artifact checksum, release/deployment records; không coi `build.time` là nguồn sự thật duy nhất.
11. **Bảo vệ bí mật:** kiểm tra các thuộc tính không lộ token/private data qua artifact hoặc Actuator.
12. **Rebuild test:** nếu yêu cầu reproducibility, dựng lại với inputs tương đồng và so sánh hashes, xử lý sai lệch.

### 18.1. Tính chính xác của metadata trước hiệu năng

Nếu yêu cầu của hệ thống là phải biết **chính xác instant build thực**, đừng chỉ exclude time rồi mặc định ghi một giá trị vô nghĩa thay thế. Hãy thiết kế provenance ngoài artifact hoặc một metadata thời gian hợp lệ có nguồn kiểm chứng. Ngược lại, đừng giữ dynamic time trong file chỉ vì nó có sẵn khi hệ thống chủ yếu cần rebuild giống nhau theo source.

Một lựa chọn thực tế là:

- Artifact chứa các giá trị ổn định như version/revision/channel.
- CI giữ job start/end timestamps.
- Artifact repository giữ publish timestamp/checksum.
- Deployment platform giữ deploy time/environment.
- Monitoring giữ application startup time.

Phân tầng này vừa thuận lợi truy vết vừa không biến mọi lần build cùng commit thành binary khác nhau chỉ vì đồng hồ.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Spring không có bean `BuildProperties` | Chưa bật build-info hoặc file không trên classpath | Kiểm tra `bootBuildInfo`/Maven goal, file và archive |
| `build-info.properties` không xuất hiện | Task/goal chưa chạy, cấu hình module sai | `./gradlew tasks --all`, `mvn help:effective-pom` và output |
| `build.time` vẫn có dù tưởng đã exclude | Đặt config sai vị trí, Gradle DSL version khác, generated artifact cũ | Xem đúng `buildInfo.excludes`, `clean` và file mới |
| `BuildProperties.getTime()` trả null | Time bị loại hoặc giá trị không parseable | Kiểm tra file; xử lý null, xem `get("time")` khi cần chẩn đoán |
| `build.version` khác archive filename | Metadata bị override nhưng project version chưa đổi | Xem Gradle `version`/POM `version`, `bootJar` output và metadata |
| `build.artifact` không giống artifactId Maven | `<artifactId>` và `name`/customization khác | Xem POM, goal build-info và output file |
| `bootBuildInfo` không UP-TO-DATE | Default `build.time` động | Exclude time nếu reproducibility ưu tiên |
| Build thường chạy lại tests dù không sửa Java | Metadata resource thay đổi từ build time | So sánh task graph/`--info`, kiểm output của bootBuildInfo |
| `/actuator/info` trả 404 | Chưa thêm Actuator/web starter hoặc chưa expose endpoint | Kiểm tra dependencies và `management.endpoints.web.exposure.include` |
| `/actuator/info` không có build | Không có build-info resource hoặc BuildInfoContributor bị disable | Xem `management.info.build.enabled`, file và logs |
| CI lộ Git branch/secret | Additional properties lấy env bừa | Audit metadata, remove sensitive keys, kiểm tra endpoint exposure |
| `java -jar` hiển thị version cũ | Đang chạy nhầm JAR, file build cũ hoặc copy sai classifier | Xác định output của bootJar/repackage, xem manifest/contents |
| Maven `<time>off</time>` nhưng JAR checksum vẫn khác | ZIP timestamps, codegen, Git metadata, tools/environment còn đổi | Xem `project.build.outputTimestamp` và các nguồn nondeterminism |
| Gradle `FROM-CACHE` không xuất hiện | Task không cacheable/miss hoặc chỉ UP-TO-DATE | Xem `--info`, task inputs, build cache settings |
| Gradle configuration cache báo lỗi quanh build-info | Plugin/task compatibility theo version | Xem configuration cache report, nâng plugin hoặc tắt tạm cấu hình đó |
| Runtime instant và build instant không giống | Hai sự kiện khác nhau | Dùng log/metrics cho startup, CI record cho build |
| Timezone gây hiểu nhầm | Timestamp string không có offset hoặc format không đúng | Dùng `Instant`/ISO-8601 UTC, format ở tầng trình bày |

**Thứ tự xử lý:** xác nhận build plugin/task → kiểm file nguồn metadata sau build → kiểm entry trong archive → kiểm giá trị qua BuildProperties → mới điều tra Actuator/CI runtime. Đừng sửa controller khi file `build-info.properties` chưa từng được tạo.

## 20. Bài tập thực hành có đáp án

### Bài 1 — Đổi channel

**Yêu cầu:** sửa thuộc tính `channel` trong Gradle example từ `training` thành `release`, build lại rồi in metadata.

**Kết quả:** file có `build.channel=release` và `BuildProperties.get("channel")` trả `release`. Phải sửa assertion JUnit nếu vẫn hardcode `training`. `project.version` không tự thay chỉ vì channel đổi.

### Bài 2 — Điều gì xảy ra với time?

**Câu hỏi:** bản Groovy có `excludes = ['time']`; code gọi `build.getTime()`. Giá trị là gì?

**Đáp án:** `null`. Không có `build.time` trong generated resource. Vì thế cần null-handling hoặc chính sách thay thế khi hiển thị.

### Bài 3 — Bản dựng chạy lại không đổi source

**Tình huống:** task `bootBuildInfo` chạy mỗi lượt dù Java source không đổi. Build dùng `springBoot { buildInfo() }` mà không exclude time.

**Đáp án:** default `build.time` là instant thay đổi; nó làm output biến động và task không up-to-date theo tài liệu. Nếu team ưu tiên repeatability/performance, thêm `excludes` cho `time` và đo lại.

### Bài 4 — Group và artifact

**Câu hỏi:** vì sao `build.artifact` có thể khác `build.name`? Có nên coi chúng bắt buộc giống nhau không?

**Đáp án:** artifact thường là tên kỹ thuật/base name của archive, name là tên hiển thị. Chúng có thể khác có chủ đích. Quan trọng là chúng phản ánh đúng artifact/release contract chứ không phải luôn giống nhau.

### Bài 5 — Maven time off

**Yêu cầu:** đặt cấu hình Maven goal không sinh `build.time`.

**Đáp án:**

~~~xml
<configuration>
    <time>off</time>
</configuration>
~~~

Đây là fragment trong execution `spring-boot:build-info`, không phải property của `maven-jar-plugin`. Sau `mvn package` kiểm file `target/classes/META-INF/build-info.properties`.

### Bài 6 — Hai nghĩa outputTimestamp

**Câu hỏi:** POM có `project.build.outputTimestamp=2025-01-01T00:00:00Z` và goal `build-info` có `<time>off</time>`. File metadata có time không?

**Đáp án:** không. `<time>off</time>` loại `build.time`. `project.build.outputTimestamp` vẫn có thể được các archive plugins dùng để chuẩn hóa ZIP/JAR entry timestamps. Hai tầng cấu hình độc lập.

### Bài 7 — Actuator info 404

**Tình huống:** `BuildProperties` trong ứng dụng hoạt động nhưng HTTP `/actuator/info` trả 404.

**Đáp án:** bean metadata tồn tại chưa có nghĩa endpoint HTTP đã được cài/expose. Cần kiểm tra Actuator dependency, web server, endpoint exposure và security. Không tự copy file metadata vào một REST controller thủ công.

### Bài 8 — Thời gian triển khai

**Câu hỏi:** sau khi restart một JAR phát hành từ hôm trước, `build.time` có biến thành thời gian restart không?

**Đáp án:** không. Đây là metadata được ghi khi build và đóng vào archive. Thời gian restart phải lấy từ runtime/monitoring/operations records.

### Bài 9 — Cùng code, khác SHA-256

**Tình huống:** loại `build.time` mà hai JAR cùng commit vẫn khác checksum.

**Đáp án:** cần kiểm tra ZIP timestamps/order, generated source/resources, toolchain, dependency graph, Git properties và CI environment. Exclude time chỉ loại một nguồn nondeterminism.

### Bài 10 — Rò rỉ dữ liệu

**Tình huống:** một người đưa access token vào `additional` rồi chỉ disable `/actuator/info`.

**Đáp án:** chưa an toàn. Token vẫn nằm trong JAR và có thể được extract từ `META-INF/build-info.properties`. Phải loại token khỏi metadata, thu hồi/rotate nếu đã publish và sửa CI policy.

## 21. Checklist trước khi phát hành

- [ ] Có task `bootBuildInfo` hoặc Maven execution `build-info` chạy thật ở đúng module ứng dụng.
- [ ] File được sinh ở `META-INF/build-info.properties` và nằm trong artifact cuối.
- [ ] Metadata có group/artifact/name/version đúng với coordinates và file publish.
- [ ] Các khóa additional ổn định, có ý nghĩa, không chứa secret hoặc dữ liệu nhạy cảm.
- [ ] Có chính sách rõ ràng cho `build.time`: động, loại bỏ, hoặc fixed provenance timestamp.
- [ ] Nếu ưu tiên reproducibility, đã exclude time ở Gradle và chọn `time=off`/fixed trong Maven.
- [ ] Đã kiểm tra archive timestamps/order và nguồn nondeterminism khác khi so sánh checksums.
- [ ] `BuildProperties.getTime()` được xử lý nullable.
- [ ] Test/smoke test kiểm đúng metadata và JAR thực tế.
- [ ] Actuator `info` (nếu có) chỉ được expose theo policy và không làm lộ thông tin không cần thiết.
- [ ] Git revision, CI run ID, release time và deployment time không bị nhầm với build instant.
- [ ] Version của Gradle wrapper/Maven/Spring Boot plugin được ghi rõ và các DSL snippets khớp phiên bản.
- [ ] CI publish đúng JAR/Build Info, không lấy nhầm artifact cũ hoặc plain JAR.

**Kết luận:** quản lý metadata hiệu quả không chỉ là thêm một timestamp. Trước hết giữ đúng group/artifact/version để truy vết, thêm thuộc tính mở rộng được kiểm soát, sau đó quyết định rõ build time thuộc **binary** hay **CI/release record**. Với Spring Boot 3.3, Gradle `buildInfo.excludes = ['time']` và Maven `<time>off</time>` là hai cách chuẩn để loại thời gian động, giúp output ổn định hơn; tính reproducible toàn bộ vẫn cần được kiểm chứng trên artifacts thật.

## 22. Tài liệu chính thức

- Spring Boot 3.3 — Gradle Plugin, *Integrating with Actuator / Generating Build Information*: https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html
- Spring Boot 3.3 — Maven Plugin, *Integrating with Actuator / build-info*: https://docs.spring.io/spring-boot/docs/3.3.13/maven-plugin/reference/htmlsingle/
- Spring Boot 3.3.13 API — `BuildProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html
- Spring Boot 3.3 — Actuator *Endpoints / Application Information*: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Gradle — Incremental Build & Task Outcomes: https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Apache Maven — Reproducible Builds Guide: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Java SE 17 — `Instant` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html

Khi thay đổi build tool/plugin hoặc nâng Java/Spring Boot, kiểm tra lại API cấu hình tương ứng: bài học nhằm tạo một **hợp đồng metadata ổn định, có thể kiểm thử và truy vết**, chứ không buộc mọi dự án phải loại bỏ thời gian trong mọi trường hợp.
