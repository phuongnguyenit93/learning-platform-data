# Quan sát tác động khi plugin Boot kết hợp với java-library, application và maven-publish

## 1. Mục tiêu: hiểu Gradle thay đổi những gì khi ghép plugin

Trong một build Gradle dùng Spring Boot, các plugin có vai trò khác nhau:

- `org.springframework.boot` bổ sung khả năng **chạy, đóng gói ứng dụng Spring Boot** và tích hợp với một số plugin khác.
- `java-library` mô tả **module Java được dùng như thư viện**: có API cho module khác, dependency tách thành `api`/`implementation`, các biến thể để module khác tiêu thụ.
- `application` mô tả **chương trình JVM có điểm vào `main`**: cung cấp lệnh chạy và bộ phân phối có start script.
- `maven-publish` mô tả **cái gì được xuất bản lên Maven repository**: tạo `MavenPublication`, POM và các tác vụ publish.

Bài này tập trung vào **tác động khi các plugin cùng xuất hiện**: task nào được tạo, artifact nào được đóng gói, artifact nào được publish và module khác có dùng nó như JAR thư viện được không.

Điểm nền tảng: Spring Boot Gradle Plugin **phản ứng khi phát hiện plugin khác được áp dụng**. Chỉ áp dụng `org.springframework.boot` mà không có plugin Java/Groovy/Kotlin thích hợp thì chưa tạo đầy đủ đường đi build ứng dụng. `java-library` và `application` đều áp dụng Java plugin theo cơ chế Gradle, nên có thể kích hoạt đường đi `bootJar` dù không khai báo `id 'java'` trực tiếp.

### Bức tranh về artifact

```text
                       Gradle project
                            |
            +---------------+----------------+
            |               |                |
       java-library     application      maven-publish
            |               |                |
      Java variants    mainClass/run      publications
      apiElements      startScripts        repositories
      runtimeElements  distZip/distTar     publish tasks
            |               |
            +------- Java plugin -----------+
                            |
                     Spring Boot reacts
                      /            \
                    bootJar       bootRun
                executable JAR   run from classes
                    |
           +--------+--------+
           |                 |
     boot distribution   explicit bootJar artifact
     (with application)  (with maven-publish)
```

Bảng quan sát nhanh (với Spring Boot Gradle Plugin **3.5.x**, Gradle 8.x):

| Kết hợp plugin | Tác động chính | Artifact/đầu ra cần kiểm tra |
|---|---|---|
| `java-library` | Kế thừa Java plugin; thêm `api` và biến thể tiêu thụ | `jar` bình thường, `apiElements`/`runtimeElements` |
| `org.springframework.boot` + `java-library` | Vì đã có Java plugin, Boot cũng tạo `bootJar`/`bootRun`; `assemble` có phụ thuộc `bootJar` | `*-plain.jar` và executable JAR; có thể lỗi nếu module thư viện không có main |
| `application` | Kế thừa Java, có `run`, `startScripts` và distribution `main` | Distribution JVM thường chứa JAR/thư viện và start scripts |
| `org.springframework.boot` + `application` | Thêm `bootStartScripts` và distribution `boot`; dùng cấu hình `application.mainClass` | `bootDistZip`/`bootDistTar` chứa executable JAR và scripts chạy bằng `java -jar` |
| `maven-publish` | Thêm cơ chế publications và publish tasks | Chỉ publish artifact/component được cấu hình, không tự suy ra cần publish `bootJar` |
| `java-library` + `maven-publish` | `from components.java` publish Java component và metadata dependency | JAR thư viện cùng POM/Gradle Module Metadata |
| `org.springframework.boot` + `maven-publish` | Có thể publish executable JAR khi khai báo `artifact(tasks.named('bootJar'))` | Artifact `bootJar`, loại metadata tùy cấu hình publication |

**Không nên đánh đồng “build tạo ra JAR” với “publication đưa JAR đó lên repository”.** `build/libs`, các biến thể `components.java` và cấu hình `publishing` là ba nơi có ý nghĩa khác nhau.

## 2. Khi Boot gặp java-library

### 2.1. java-library không đơn giản là một tên khác của Boot

Plugin `java-library` mở rộng Java plugin, cung cấp:

- `compileJava`, `test`, `jar` và các task Java thông thường.
- `api`: dependency có kiểu xuất hiện trong chữ ký API công khai của thư viện; người tiêu thụ cần thấy khi compile.
- `implementation`: dependency là chi tiết triển khai; người tiêu thụ thường không thấy ở **compile classpath** của mình nhưng vẫn cần khi runtime.
- `apiElements` và `runtimeElements`: các **consumable variants** (biến thể người khác sử dụng khi phụ thuộc vào module), gắn artifact và thông tin dependency thích hợp.

Ví dụ trong `build.gradle` của một module **thư viện thực sự**:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.17'
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Đây là **đoạn khai báo minh họa**; cần có `repositories { mavenCentral() }` và build phù hợp mới resolve dependency. Dùng `api` nếu kiểu từ dependency xuất hiện trong chữ ký public; các thư viện chỉ dùng bên trong method thường đặt ở `implementation`. `implementation` không phải đồng nghĩa “không xuất hiện khi runtime của consumer”.

### 2.2. Điều gì xảy ra nếu còn áp dụng Spring Boot?

```groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot' version '3.5.16'
}
```

Vì `java-library` đã kéo Java plugin vào, Spring Boot tạo `bootJar`, `bootRun`, `bootBuildImage`, cấu hình `bootArchives`, cập nhật `assemble` để dựng executable archive và đặt classifier `plain` làm quy ước cho `jar`. Do đó Gradle có thể tạo:

- `build/libs/<module>-<version>.jar`: **executable Boot JAR**, lớp ứng dụng dưới `BOOT-INF/classes`, thư viện runtime dưới `BOOT-INF/lib`.
- `build/libs/<module>-<version>-plain.jar`: **JAR Java bình thường** do task `jar` tạo, dùng làm thư viện/classpath thông thường.

Tên file là quy ước mặc định nếu không đổi `archiveBaseName`, `archiveVersion` hay `archiveClassifier`. Không suy từ đuôi `.jar` rằng hai file có thể thay thế nhau.

**Cạm bẫy:** module thư viện có thể không có method `main`. Khi `assemble` kích hoạt `bootJar`, task có thể lỗi vì không tìm thấy hoặc chưa cấu hình main class. Hơn nữa, executable Boot JAR **không phải** thư viện Java thông thường để đưa lên compile classpath: lớp nằm trong `BOOT-INF/classes`, không ở root của JAR như JAR thư viện.

Khuyến nghị khi làm dự án nhiều module: **chỉ áp dụng Spring Boot plugin cho module ứng dụng có điểm vào**. Các module `core`, `domain`, `shared-lib` chỉ cần `java-library` (và `maven-publish` nếu muốn publish); điều này tránh tạo executable JAR vô nghĩa và giữ cách tiêu thụ thư viện chuẩn.

Nếu chính một module vừa là application vừa chủ định phát hành API, phải xác định **hai nhu cầu artifact** riêng, chứ không đổi ngẫu nhiên tên `bootJar` thành `jar`.

## 3. Khi Boot gặp application

Gradle `application` áp dụng Java plugin và Distribution plugin, tạo:

- `run`: chạy class main của ứng dụng với runtime classpath của source set chính.
- `startScripts`: tạo script cho Windows và Unix.
- `distZip`/`distTar`: gói distribution Java thông thường.
- `installDist`: cài distribution vào thư mục build để chạy thử.
- Extension `application` để khai báo `mainClass` và, nếu muốn, `applicationDefaultJvmArgs`.

Khi có **Spring Boot Gradle Plugin**, Gradle còn có:

1. `bootRun`: chạy ứng dụng Spring Boot từ class/resource đã build và classpath runtime, không cần đóng gói JAR trước.
2. `bootStartScripts`: tạo script chạy executable JAR trong `bootArchives` qua `java -jar`.
3. Distribution `boot`, thường đóng bằng `bootDistZip`/`bootDistTar`; có executable JAR ở `lib` và script ở `bin`.
4. `application.mainClass` được dùng làm quy ước cho main class của `bootRun` và mục `Start-Class` trong manifest `bootJar`.
5. `applicationDefaultJvmArgs` có thể được áp dụng cho các task chạy và script của distribution Boot.

Ví dụ cấu hình:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'application'
}

application {
    mainClass = 'com.example.app.DemoApplication'
    applicationDefaultJvmArgs = ['-Dfile.encoding=UTF-8']
}
```

Đây là đoạn build dành cho một ứng dụng có class `com.example.app.DemoApplication`, không phải build đầy đủ. Main class có thể được Spring Boot suy luận khi thích hợp, nhưng **khai báo tường minh** hữu ích khi có nhiều entrypoint hoặc muốn distribution ổn định.

| Task | Cách thực thi | Phù hợp |
|---|---|---|
| `run` | Application plugin chạy main class trên runtime classpath | Chạy chương trình Java với cơ chế của Application plugin |
| `bootRun` | BootRun (dựa trên JavaExec) chạy Spring Boot từ main source set | Phát triển/chạy ứng dụng mà chưa cần `bootJar` |
| `jar` | Tạo JAR Java bình thường | Thư viện hoặc đầu vào cho Java distribution |
| `bootJar` | Đóng ứng dụng và dependency runtime vào executable JAR | `java -jar` hoặc phân phối Boot |
| `distZip` | Gói Java distribution mặc định (`main`) | Script + JAR/libraries của Application plugin |
| `bootDistZip` | Gói Boot distribution | Script gọi executable JAR |
| `bootBuildImage` | Dựng OCI image qua buildpacks nếu môi trường đủ điều kiện | Image runtime; **không phải** một cách publish Maven |

Bộ file của `distZip` và `bootDistZip` khác nhau về cách tổ chức runtime. Không coi hai ZIP là bản sao hay chạy cả hai theo cùng một cơ chế. Các task tạo image thường còn phụ thuộc container engine/daemon hoặc môi trường buildpacks, nên không dùng việc xuất hiện `bootBuildImage` trong `tasks` để kết luận một image đã được dựng.

## 4. Khi Boot gặp maven-publish: chọn đúng artifact

`maven-publish` cung cấp `publishing { publications { ... } repositories { ... } }`, các task như:

- `generatePomFileFor<Publication>Publication` (metadata POM).
- `publish<Publication>PublicationTo<Repository>Repository` (đưa publication lên repository).
- `publish<Publication>PublicationToMavenLocal` và `publishToMavenLocal` (local Maven repository).
- `publish` (aggregate các publication đến repository khai báo).

**Không mặc định** rằng áp dụng `maven-publish` sẽ tự publish file `bootJar`. Cần tạo một `MavenPublication` và chỉ rõ component/artifact.

### 4.1. Publish thư viện bình thường

Trong module có `java-library`:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` lấy **Java component**: JAR bình thường, thông tin API/runtime variants và dependency metadata được cấu hình. Đây là cách thường dùng khi người nhận sẽ đặt artifact lên classpath để compile hoặc chạy.

### 4.2. Publish ứng dụng Spring Boot executable JAR

Trong module ứng dụng:

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16'
    id 'java'
    id 'maven-publish'
}

publishing {
    publications {
        bootJava(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
}
```

Đây là mẫu do tài liệu Spring Boot khuyến nghị: `artifact tasks.named('bootJar')` chọn đúng executable archive. Chỉ dùng block trên sau khi đã cấu hình main class và dependency cho một ứng dụng thật.

**Hệ quả về metadata:** publication chỉ dùng `artifact tasks.named('bootJar')` không tự mang toàn bộ thông tin dependency/variants từ `components.java`. Điều này thường chấp nhận được khi phát hành **ứng dụng đóng gói tự chạy**, vì Boot JAR đã chứa thư viện runtime thích hợp. Nhưng nếu consumer cần API/thư viện transitively resolved, hãy publish Java component của **module thư viện** thay vì trông đợi một fat JAR có POM tương đương thư viện.

### 4.3. Chuyện gì xảy ra với `from components.java` trên module Boot?

Boot plugin đặt classifier `plain` cho task `jar` theo quy ước. Vì `components.java` thường tham chiếu JAR **thường**, publication `from components.java` có thể đưa artifact `-plain.jar` thay vì executable JAR. Khi publish ra Maven repository, nếu JAR thư viện bị gắn classifier `plain` mà bạn mong muốn có **primary JAR không classifier**, người tiêu thụ theo tọa độ thông thường có thể không lấy được đúng artifact. Đừng giả định “from components.java” sẽ thay bằng “bootJar”.

Nếu thực sự muốn publish **hai loại JAR cùng một publication**, hãy chọn classifier rõ ràng. Ví dụ **đoạn thay thế** cho dự án ứng dụng đã có `java`, `org.springframework.boot` và `maven-publish`:

```groovy
tasks.named('jar') {
    archiveClassifier = ''
}
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java      // JAR Java thường: artifact chính
            artifact tasks.named('bootJar') // JAR executable: classifier "boot"
        }
    }
}
```

Cấu hình này để consumer mặc định lấy **plain JAR**; artifact có classifier `boot` dành cho người biết cần executable archive. Đây là **phương án thay thế** cho publication `bootJava` ở mục 4.2, không thêm hai cấu hình trái mục đích vào cùng build nếu chưa thiết kế tọa độ phát hành. Nếu muốn deploy executable JAR làm artifact chính, ưu tiên publication chỉ có `bootJar` hoặc publication riêng với `artifactId` khác; kiểm tra artifact/POM sau publish.

**Không publish một fat JAR Spring Boot làm Java library chỉ vì “file cũng là JAR”.** Lớp nằm trong `BOOT-INF/classes` và các dependency lồng bên trong không được Java classpath thông thường giải nén/nạp theo cách Java library được thiết kế.

## 5. Bài thực hành quan sát: dự án Gradle hai module

Ta xây dựng dự án có một thư viện Java và một ứng dụng Boot dùng thư viện đó. Cách chia module giúp thấy rõ **plugin nào áp dụng ở đâu**, đồng thời minh họa cả `java-library`, `application` và `maven-publish`.

**Yêu cầu:** JDK 17+, Gradle 8.14.3 (hoặc Gradle 8.x tương thích với Spring Boot 3.5), mạng hoặc cache đủ dependency/plugin. Ví dụ dùng Spring Boot **3.5.16** được pin cố định để minh họa; không tự suy rằng đây luôn là bản mới nhất. Các ví dụ dưới đây dùng **Groovy DSL** (`.gradle`), không trộn cú pháp Kotlin DSL `.gradle.kts`.

### 5.1. Cây thư mục

```text
boot-plugin-lab/
├── settings.gradle
├── build.gradle
├── gradlew                  # nếu dự án đã tạo Gradle Wrapper
├── gradlew.bat              # trên Windows
├── gradle/wrapper/...       # nếu đã tạo Gradle Wrapper
├── shared-lib/
│   ├── build.gradle
│   └── src/main/java/com/example/domain/Greeter.java
└── service-app/
    ├── build.gradle
    └── src/main/java/com/example/app/DemoApplication.java
```

Các file Wrapper trong sơ đồ là **có sau khi bạn tạo Gradle Wrapper**, không xuất hiện chỉ vì viết `settings.gradle`. Nếu chưa có wrapper, máy cần Gradle cài sẵn để chạy `gradle wrapper --gradle-version 8.14.3`. Sau khi tạo hãy commit `gradlew`, `gradlew.bat` và `gradle/wrapper` để người khác có thể chạy lại.

### 5.2. `settings.gradle` ở root

```groovy
rootProject.name = 'boot-plugin-lab'
include 'shared-lib', 'service-app'
```

### 5.3. `build.gradle` ở root

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
}

allprojects {
    group = 'com.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
```

`apply false` đưa version plugin vào phần quản lý resolution của build root nhưng **không áp dụng plugin Boot cho root**. Module con nào cần Spring Boot sẽ tự áp dụng `id 'org.springframework.boot'`. Đây là cách tránh tạo task Boot cho thư viện.

### 5.4. `shared-lib/build.gradle`

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            name = 'lab'
            url = uri(rootProject.layout.buildDirectory.dir('maven-repo').get().asFile)
        }
    }
}
```

Ở đây `from components.java` publish thư viện bình thường. Repository `lab` được đặt tại **`build/maven-repo` của root** để quan sát an toàn trong máy đang làm bài, không tự đẩy lên server bên ngoài. Trong hệ thống thật, có thể dùng Maven repository nội bộ và credential theo chính sách.

Tạo `shared-lib/src/main/java/com/example/domain/Greeter.java`:

```java
package com.example.domain;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Đây là thư viện Java 17 thuần, không có Spring Boot main class và không cần plugin Spring Boot. `Greeter.greet("Gradle")` trả về chuỗi `Hello, Gradle!`.

### 5.5. `service-app/build.gradle`

```groovy
plugins {
    id 'org.springframework.boot'
    id 'application'
    id 'maven-publish'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.app.DemoApplication'
}

dependencies {
    implementation project(':shared-lib')

    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.16'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

publishing {
    publications {
        bootJava(MavenPublication) {
            artifact tasks.named('bootJar')
        }
    }
    repositories {
        maven {
            name = 'lab'
            url = uri(rootProject.layout.buildDirectory.dir('maven-repo').get().asFile)
        }
    }
}
```

Giải thích những lựa chọn:

1. `application` **đã áp dụng Java plugin**, nên `org.springframework.boot` tạo `bootJar`, `bootRun` và các task liên quan; không cần ghi thêm `id 'java'`.
2. `application.mainClass` là điểm vào để `run`, `bootRun`, `bootJar` và start scripts có cơ sở xác định main class.
3. `implementation project(':shared-lib')` là dependency từ ứng dụng sang thư viện trong cùng build. `shared-lib` sẽ được compile trước khi ứng dụng cần dùng lớp của nó.
4. `platform('org.springframework.boot:spring-boot-dependencies:3.5.16')` nhập các ràng buộc phiên bản từ BOM qua **Gradle native platform support**; `implementation 'org.springframework.boot:spring-boot-starter'` mới thật sự thêm starter. Việc áp dụng riêng Spring Boot plugin **không tự thêm** dependency starter.
5. `bootJava` chọn `bootJar` làm artifact publish, trong khi thư viện chọn `components.java`.
6. Có thể dùng `io.spring.dependency-management` thay cho native BOM, nhưng khi áp dụng plugin đó, Spring Boot tự import BOM phù hợp; tránh trộn nhiều nguồn quản lý version mà không hiểu thứ tự áp dụng.

### 5.6. `service-app/src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.domain.Greeter;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> System.out.println(Greeter.greet("Gradle"));
    }
}
```

Ứng dụng dùng `spring-boot-starter` chứ không phải web starter, nên không cần khởi động HTTP server. Khi chạy thành công, stdout **có chứa dòng** sau:

```text
Hello, Gradle!
```

Spring Boot/Gradle còn có thể in thông tin startup và log khác tùy môi trường; không coi toàn bộ stdout chỉ có một dòng.

## 6. Quan sát tasks và artifact của từng module

Tại root dự án có Gradle Wrapper, chạy trên Linux/macOS:

```bash
./gradlew :shared-lib:tasks --all
./gradlew :service-app:tasks --all

./gradlew :shared-lib:jar
./gradlew :service-app:jar :service-app:bootJar

./gradlew :service-app:run
./gradlew :service-app:bootRun
```

Windows PowerShell/cmd dùng `gradlew.bat` thay `./gradlew`. Các lệnh `run` và `bootRun` là **hai lần chạy độc lập** để so sánh, không nhất thiết gọi cả hai mỗi lần build. Với bài này, cả hai đều chạy `DemoApplication` và in dòng chào; `bootRun` dùng tích hợp Spring Boot và có thêm các quy ước phù hợp cho quá trình phát triển.

Để không phải kéo theo log dài của `tasks --all`, có thể hỏi trực tiếp từng task:

```bash
./gradlew :shared-lib:help --task jar
./gradlew :service-app:help --task bootJar
./gradlew :service-app:help --task bootDistZip
./gradlew :service-app:help --task publishBootJavaPublicationToLabRepository
```

**Quan sát kỳ vọng** với cấu hình và tên/version mặc định của ví dụ:

| Nơi | File/task | Ý nghĩa |
|---|---|---|
| `shared-lib/build/libs/` | `shared-lib-1.0.0.jar` | JAR Java bình thường, dùng được làm thư viện |
| `service-app/build/libs/` | `service-app-1.0.0-plain.jar` | JAR thường do task `jar` tạo |
| `service-app/build/libs/` | `service-app-1.0.0.jar` | Executable Boot JAR do `bootJar` tạo |
| `:shared-lib:jar` | Task Java library | Không có main class vẫn tạo được JAR thư viện |
| `:service-app:bootJar` | Task Boot | Đóng lớp ứng dụng + runtime dependency |
| `:service-app:run` | Task Application | Chạy trực tiếp từ classpath |
| `:service-app:bootRun` | Task Spring Boot | Chạy ứng dụng từ main source set |
| `:service-app:bootDistZip` | Task phân phối Boot | ZIP gồm executable JAR và script khởi chạy |

Đừng chỉ dựa vào bảng kỳ vọng nếu bạn đã thay version, `archiveClassifier` hoặc tên module: **task output thực tế** mới là nguồn xác nhận.

Kiểm tra archive bằng công cụ `jar` của JDK:

```bash
./gradlew :service-app:bootJar :service-app:jar

# Xem danh sách thành phần Boot executable archive
jar tf service-app/build/libs/service-app-1.0.0.jar

# Chạy đúng executable archive
java -jar service-app/build/libs/service-app-1.0.0.jar
```

Trong danh sách archive Boot thường có `BOOT-INF/classes/com/example/app/DemoApplication.class` và `BOOT-INF/lib/` chứa JAR dependency runtime (gồm artifact phù hợp từ `shared-lib`). JAR `-plain.jar` lại đặt lớp ở đường dẫn package thông thường như `com/example/app/DemoApplication.class` và không tự nhúng tất cả runtime dependencies. Đừng mong `java -jar ...-plain.jar` hoạt động giống Boot JAR.

Để xem Gradle lựa chọn dependency và biến thể:

```bash
./gradlew :shared-lib:outgoingVariants
./gradlew :service-app:dependencies --configuration runtimeClasspath
./gradlew :service-app:dependencyInsight --configuration runtimeClasspath --dependency shared-lib
```

`outgoingVariants` cho biết biến thể của Java library như `apiElements` và `runtimeElements`. Với dependency là **project dependency**, `dependencyInsight` có thể hiển thị quan hệ và lý do chọn variant tùy version/cấu hình Gradle; đừng đọc nhãn như cam kết về cấu trúc một fat JAR. Xem thêm `:shared-lib:dependencies` nếu muốn so sánh API và implementation của thư viện.

## 7. Quan sát distribution do application và Boot tạo

Trong `service-app`, chạy:

```bash
./gradlew :service-app:distZip :service-app:bootDistZip
```

File ZIP được tạo dưới `service-app/build/distributions/`; tên chính xác có thể gồm tên distribution, tên project và version. Mở hai ZIP để so sánh:

- Distribution **`main`** từ Application plugin: scripts chuẩn chạy main class với classpath gồm JAR và dependency trong thư mục phân phối.
- Distribution **`boot`** từ Spring Boot integration: scripts do `bootStartScripts` tạo để chạy executable JAR theo kiểu `java -jar`, JAR thường nằm trong thư mục `lib` của distribution.

Để dùng script từ distribution, giải nén ZIP tương ứng và chạy file dưới `bin` với tên phân phối thực tế. Trên Unix script cần quyền thực thi; trên Windows dùng script `.bat` được cung cấp. `bootDistZip` không có nghĩa upload artifact lên Maven repository: đó là thao tác đóng gói distribution cho người chạy ứng dụng.

Nếu lệnh `bootDistZip` không tồn tại, kiểm tra `application` đã được áp dụng trong **module app** hay chưa. Nếu `bootJar` không tồn tại, kiểm tra Java/Application plugin đã thực sự được áp dụng hay chưa. Nếu `bootJar` không tìm thấy main class, kiểm tra `application.mainClass` và class đã được compile.

## 8. Quan sát maven-publish mà không đẩy lên server bên ngoài

Ví dụ đã cấu hình repository dạng file trong root `build/maven-repo`. Có thể publish đúng hai publication bằng các task:

```bash
./gradlew :shared-lib:publishLibraryPublicationToLabRepository
./gradlew :service-app:publishBootJavaPublicationToLabRepository
```

Gradle tạo các thư mục theo Maven coordinates, chẳng hạn:

```text
build/maven-repo/
└── com/
    └── example/
        ├── shared-lib/
        │   └── 1.0.0/
        │       ├── shared-lib-1.0.0.jar
        │       └── shared-lib-1.0.0.pom
        └── service-app/
            └── 1.0.0/
                ├── service-app-1.0.0.jar
                └── service-app-1.0.0.pom
```

Các file checksum hoặc metadata phụ trợ có thể được tạo thêm, tùy Gradle/repository; sơ đồ chỉ nêu những artifact chính để nhận diện.

**Điều cần tự kiểm tra:**

1. `shared-lib-1.0.0.jar` trong repository là JAR thư viện có lớp ở root package, được xuất bản từ `components.java`.
2. `service-app-1.0.0.jar` là Boot executable JAR được publish bằng `artifact tasks.named('bootJar')`; có thể chạy `java -jar` khi đủ điều kiện.
3. Mở hai file `.pom` để xem metadata. Library publication gắn Java component có thể biểu diễn dependency API/runtime; Boot application publication chỉ gắn artifact không nhất thiết liệt kê đầy đủ các dependency bên trong.
4. Không suy từ việc `publish...` thành công rằng JAR ứng dụng hợp lệ: chạy thử artifact được publish và kiểm tra `BOOT-INF/`.
5. Nếu đổi classifier hoặc publication name, kiểm tra lại đường dẫn và tọa độ; không mặc định tên file ở trên còn đúng.

Khi chỉ muốn xem POM của publication trước khi publish, dùng:

```bash
./gradlew :shared-lib:generatePomFileForLibraryPublication
./gradlew :service-app:generatePomFileForBootJavaPublication
```

Các file POM thường nằm ở `<module>/build/publications/<publication>/pom-default.xml`. Đừng coi file Gradle Module Metadata (`.module`) và Maven POM (`.pom`) là cùng một định dạng hay bảo đảm diễn tả dependency variants giống hệt nhau.

### Nếu xuất bản nhiều publication

Đừng vừa tạo publication Boot app không classifier vừa tạo Java component không classifier **cùng GAV** mà không kiểm tra đường dẫn và artifact trùng. Nếu cần cả thư viện và executable app, ưu tiên **hai module hoặc hai artifactId**. Với cùng một module, có thể sử dụng classifier khác nhau như ở mục 4.3, nhưng người dùng thư viện phải biết nên lấy bản nào. Phân biệt rõ ý định:

- **Thư viện tái sử dụng**: `from components.java`, chú trọng API/runtime metadata, JAR thường.
- **Ứng dụng deploy/chạy**: `artifact tasks.named('bootJar')`, chú trọng executable archive và quy trình phát hành.

## 9. Một thí nghiệm nhỏ: áp dụng Boot nhầm vào thư viện

Giả sử sửa thử `shared-lib/build.gradle` để thêm plugin Boot **như một thí nghiệm**, không phải cấu hình khuyến nghị:

```groovy
plugins {
    id 'java-library'
    id 'org.springframework.boot'
    id 'maven-publish'
}
```

Với root đã định nghĩa version Boot qua `apply false`, cấu hình trên sẽ khiến `shared-lib` có task `bootJar`. Quan sát bằng:

```bash
./gradlew :shared-lib:tasks --all
./gradlew :shared-lib:help --task bootJar
./gradlew :shared-lib:assemble
```

Module `shared-lib` trong ví dụ **không có main class**. Vì `assemble` phụ thuộc `bootJar`, build có thể dừng ở lỗi không xác định được main class cho executable JAR. Đó là **bằng chứng về tính reactive của plugin Boot**, không chứng minh `java-library` không tương thích về mặt cú pháp.

Để trở về thiết kế đúng, chỉ cần dùng cấu hình `shared-lib` ban đầu **không áp dụng Boot plugin**. Tránh workaround `springBoot.mainClass` giả tạo hoặc ép `bootJar` cho một thư viện chỉ để cho task chạy được. Nếu bắt buộc áp dụng Boot plugin vào module khác mục đích, hãy kiểm tra và cấu hình rõ các task liên quan, không đưa thay đổi đó lên mọi subproject một cách máy móc.

## 10. Lỗi thường gặp và hướng kiểm tra

| Triệu chứng | Nguồn gốc thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| `bootJar` không tồn tại | Chưa áp dụng Java/Groovy/Kotlin thích hợp cho module | Xem `plugins` và `tasks --all` ở **đúng module** |
| `bootJar` không tìm thấy main class | Module là library không có entrypoint hoặc mainClass không rõ | Chỉ dùng Boot ở app, hoặc cấu hình `application.mainClass` đúng |
| `jar` tạo file `-plain.jar` | Boot đặt quy ước classifier `plain` để tránh đụng Boot JAR | Đây là hành vi bình thường; chọn artifact theo mục đích |
| JAR Boot dùng như dependency nhưng compile báo thiếu class | Class ứng dụng nằm dưới `BOOT-INF/classes` | Publish/use JAR thường của Java library |
| `application` có `run` nhưng thiếu `bootDistZip` | Không áp dụng Boot hoặc xem nhầm module | Kiểm tra plugin và task tại module app |
| ZIP Boot có tên khác dự tính | Distribution name/version/classifier có thể thay | Liệt kê `build/distributions` sau khi chạy task |
| `publish` không upload Boot JAR | Chưa khai báo publication gắn `bootJar` | Dùng `artifact tasks.named('bootJar')` |
| Publication xuất `-plain.jar` ngoài ý muốn | `from components.java` lấy Java component | Chọn Boot artifact riêng, hoặc đổi classifier minh bạch |
| Publish app chỉ có POM rất ít dependency | Publication chỉ gắn bootJar artifact | Đúng kỳ vọng nếu coi đó là executable app; library dùng `components.java` |
| `api` không được nhận diện | Module chỉ dùng `java`/`application`, chưa dùng `java-library` | Áp dụng `java-library` khi thiết kế thư viện có API |
| Không resolve được Spring Boot starter do thiếu version | Chưa quản lý phiên bản qua BOM/Gradle platform | Dùng `platform('org.springframework.boot:spring-boot-dependencies:...')` hoặc dependency-management plugin |
| `bootBuildImage` lỗi kết nối môi trường build | Chưa có container engine/buildpack phù hợp | Xem yêu cầu build image riêng, không coi là lỗi Maven publishing |
| Module khác nhận dependency nhưng lúc chạy thiếu lớp | Sai runtime variant/implementation hoặc publish nhầm JAR | Xem `outgoingVariants`, `runtimeClasspath`, POM và archive |
| `publishToMavenLocal` không thấy file ở repo `lab` | Hai destination khác nhau | Dùng `publish...ToLabRepository` khi muốn ghi root `build/maven-repo` |

## 11. Checklist quan sát và quyết định kiến trúc

- [ ] Biết module nào là **library** (có API tái sử dụng), module nào là **application** (có `main`).
- [ ] Chỉ áp dụng `org.springframework.boot` ở module cần chạy/đóng gói Spring Boot app.
- [ ] Dùng `java-library` nếu cần tách dependency API/implementation và xuất Java component cho consumer.
- [ ] Khi áp dụng `application`, khai báo `mainClass` để `run`/`bootRun`/distribution xác định đúng entrypoint.
- [ ] Dùng `tasks --all` hoặc `help --task ...` để nhìn task thực tế; không đoán dựa trên tên plugin.
- [ ] Phân biệt `jar` (plain) và `bootJar` (executable), kiểm tra archive bằng `jar tf`.
- [ ] Phân biệt `distZip` (Java distribution) và `bootDistZip` (Boot distribution).
- [ ] Publish thư viện bằng `from components.java`, publish Boot app bằng `artifact tasks.named('bootJar')` khi phù hợp.
- [ ] Kiểm tra classifier, group/artifact/version và generated `.pom` sau publish.
- [ ] Thử chạy **đúng executable archive được phát hành**, không chỉ thành công của task publish.
- [ ] Kiểm tra Gradle wrapper/JDK và dependency management trước khi truy lỗi plugin.

**Ghi nhớ:** `java-library` quyết định module được **tiêu thụ như thư viện** ra sao; `application` quyết định **chạy và phân phối chương trình** ra sao; Spring Boot plugin bổ sung **executable JAR, BootRun và Boot distribution** khi phát hiện Java/Application plugin; `maven-publish` quyết định **artifact nào thực sự đi lên repository**. Đọc task graph, variant, archive và publication cùng nhau mới biết kết quả ghép plugin có đúng mục đích.

### Tài liệu chính thức

- [Spring Boot 3.5 — Reacting to Other Plugins](https://docs.spring.io/spring-boot/3.5/gradle-plugin/reacting.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Publishing Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/publishing.html)
- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/gradle-plugin/running.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)