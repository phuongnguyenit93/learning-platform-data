# Gộp service descriptor, tài nguyên trùng và giới hạn của fat JAR trong Gradle

## 1. Fat JAR là gì và vì sao việc “gộp mọi JAR” có thể làm ứng dụng hỏng?

**Fat JAR**, còn gọi là **uber JAR** hoặc **shaded JAR**, là một archive JAR chứa class và resource của ứng dụng cùng với class/resource từ các dependency được chọn. Mục tiêu thường là mang một artifact duy nhất đến máy chạy:

```bash
java -jar app-1.0.0-all.jar
```

Tuy nhiên JAR là file ZIP có cấu trúc tên đường dẫn, không phải “thư mục cộng dồn” với quy tắc hợp nhất tự nhiên. Nếu hai dependency đều có resource tên `META-INF/services/demo.spi.Greeting`, `config.properties`, `META-INF/spring.factories` hoặc `META-INF/LICENSE`, chúng **đụng nhau ở cùng đường dẫn trong output JAR**.

Một thao tác giải nén rồi sao chép thiếu chính sách có thể:

- **Giữ file đầu tiên** và bỏ phần đóng góp của dependency còn lại.
- **Cho phép hai ZIP entries cùng tên**, nhưng nhiều Java API chỉ đọc một entry hoặc xử lý không thống nhất.
- **Báo lỗi duplicate** và dừng build.
- **Ghép byte theo cách không đúng định dạng**, làm mất metadata hoặc tạo resource không hợp lệ.
- **Làm chữ ký JAR mất hiệu lực** hoặc phá multi-release JAR / Java module metadata.
- **Khiến ServiceLoader chỉ thấy một provider**, dù trên runtime classpath thông thường có hai providers.

Chủ đề này tập trung vào cách **gộp Java service descriptors**, quyết định chính sách cho **các loại tài nguyên trùng khác nhau** và nhận diện **giới hạn kỹ thuật của fat JAR** trong Gradle. Không nên mặc định rằng cứ đặt `duplicatesStrategy = EXCLUDE` hoặc `mergeServiceFiles()` là giải quyết được mọi vấn đề.

### Kết quả học tập

Sau bài này bạn có thể: giải thích `META-INF/services` và `ServiceLoader`; phân biệt thin JAR/fat JAR; dựng multi-project Java 17 với hai provider cùng đóng góp một descriptor; so sánh JAR naïve và Shadow JAR; sử dụng `mergeServiceFiles()` cùng duplicate handling đúng thứ tự; kiểm tra nội dung archive và runtime; nhận biết các metadata khác cần transformer riêng; đánh giá module-info, signature, ZIP64, minimization, relocation và reproducibility.

## 2. Thin JAR, distribution và fat JAR khác nhau thế nào?

| Hình thức | Cấu trúc | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Thin JAR** | JAR ứng dụng chỉ chứa class/resource của app; dependency ở các JAR riêng trên classpath. | Giữ nguyên metadata, chữ ký và cấu trúc dependency; dễ update thư viện riêng. | Cần quản lý cả thư mục lib/classpath khi triển khai. |
| **Application distribution** | Script chạy + app JAR + nhiều dependency JAR trong `lib/`. | Gradle `application` plugin có `installDist`/`distZip`; giữ các JAR riêng. | Không phải một file JAR độc lập để chạy `java -jar` theo mọi cấu trúc. |
| **Fat/uber JAR** | Gộp class và resource từ app/dependencies vào một JAR. | Phân phối một artifact, thuận tiện với JVM ứng dụng đơn giản. | Đụng tài nguyên, chữ ký, JPMS, SPI, licensing, kích thước, classpath isolation. |
| **Executable framework archive** | Ví dụ Spring Boot `bootJar` dùng launcher/layout riêng. | Tích hợp framework và dependency management. | Không tương đương “unzip mọi lib vào root”; dùng công cụ theo framework. |

Gradle core `jar` task bình thường tạo **thin JAR**; core `application` plugin tạo distribution. Để tạo fat JAR có merge/relocation nâng cao, một lựa chọn phổ biến là **Shadow** của GradleUp (`com.gradleup.shadow`). Fat JAR không phải yêu cầu bắt buộc của Java: khi cần giữ JARs riêng, dùng distribution/classpath có thể **an toàn và đơn giản hơn**.

## 3. Cơ chế Java SPI: service descriptor là dữ liệu có cấu trúc

Java `ServiceLoader` triển khai cơ chế Service Provider Interface (SPI). Consumer khai báo một **service type** (interface/abstract class), còn provider JAR chứa implementation và một resource descriptor trong:

```text
META-INF/services/<fully-qualified-binary-name-of-service>
```

Giả sử service interface là `demo.spi.Greeting`, đường dẫn resource **phải đúng**:

```text
META-INF/services/demo.spi.Greeting
```

File descriptor chứa **tên lớp provider đủ package**, mỗi dòng một tên, mã hóa UTF-8 theo cơ chế service provider configuration files. Ví dụ một provider:

```text
demo.providers.en.EnglishGreeting
```

Provider khác có descriptor **cùng tên đường dẫn**:

```text
demo.providers.vi.VietnameseGreeting
```

Trên **classpath thông thường** với hai JAR riêng, `ServiceLoader` có thể đọc cả hai resources qua class loader, từ đó nhìn thấy hai providers. Nhưng khi dựng fat JAR naïve mà **chỉ giữ một descriptor**, provider còn lại vẫn có thể tồn tại dưới dạng `.class` song **không được khám phá qua ServiceLoader**.

### 3.1. Quy tắc nội dung descriptor

- Mỗi tên provider nằm trên một dòng, ví dụ `com.example.impl.ProviderA`.
- Dòng trống và comment mở đầu bằng `#` được xử lý theo quy tắc `ServiceLoader`.
- Tên service type trong đường dẫn phải khớp **binary name** mà code dùng khi gọi `ServiceLoader.load(ServiceType.class)`.
- Lớp provider phải thực sự được đóng gói, load được và đáp ứng hợp đồng provider. Với classpath providers phổ biến, dùng class public implement service và constructor không tham số public.
- Các dependency của provider cũng phải có sẵn trên runtime classpath/fat JAR; merge descriptor **không tự giải quyết missing class**.
- Nếu thực hiện relocation package, phải xem xét đổi **cả tên service descriptor lẫn tên class trong nội dung**, không chỉ đổi bytecode.
- Với **Java modules đặt trên module path**, service declaration có thể dựa vào `module-info.java` và các câu lệnh `uses`/`provides ... with ...`; chỉ gộp file `META-INF/services` không giải quyết mọi vấn đề JPMS.

### 3.2. ServiceLoader không bảo đảm thứ tự business logic

Nếu app cần output ổn định, đừng phụ thuộc thứ tự khám phá providers. Sau khi lấy các implementations, hãy sắp xếp theo khóa business rõ ràng. Ví dụ dưới đây dùng `TreeMap` để luôn in ngôn ngữ `en` trước `vi`. Provider discovery order có thể thay đổi theo class loader/archive và cách merge; không nên dựa vào “JAR A xuất hiện trước JAR B” để điều khiển nghiệp vụ.

## 4. DuplicatesStrategy: những lựa chọn khác nhau có hậu quả khác nhau

Gradle `Jar`/`Copy` tasks sử dụng `DuplicatesStrategy` để xử lý hai input files có **cùng path đầu ra**.

| Strategy | Tác dụng | Khi nào hợp lý? | Rủi ro với service descriptors |
| --- | --- | --- | --- |
| `EXCLUDE` | Giữ resource xuất hiện trước, bỏ resource trùng phía sau. | Có thể hợp lý cho một số file thực sự tương đương hoặc được ưu tiên rõ. | Bỏ provider declarations trong resource trùng. |
| `FAIL` | Dừng khi phát hiện duplicate path. | Tốt cho audit hoặc resource không được phép xung đột. | Dừng cả khi hai descriptor cần được **merge**, nếu chưa cho phép transformer xử lý. |
| `INCLUDE` | Cho các duplicate entries đi tiếp trong pipeline. | Khi có transformer nhận đủ inputs và tạo output hợp lệ. | Nếu không có transformer, có thể giữ nhiều entries cùng path; không phải “merge text”. |
| `WARN` | Cho đi tiếp và ghi cảnh báo theo semantics của task/plugin. | Cần quan sát duplicates trong quá trình migration. | Vẫn cần xác định transformer/policy và kiểm tra output. |
| `INHERIT` | Nhận policy từ copy spec cha. | Khi tổ chức hóa copy specs có chủ đích. | Có thể gây lỗi nếu không có policy cha phù hợp. |

**Với Shadow 9.x**, tài liệu nêu `ShadowJar` có default `duplicatesStrategy = EXCLUDE`. Quy tắc duplicate được áp dụng **trước** một số resource transformers; vì vậy cấu hình:

```kotlin
// Sai nếu có nhiều descriptor cùng path và kỳ vọng gộp đầy đủ.
tasks.named<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("shadowJar") {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    mergeServiceFiles()
}
```

có thể **chỉ đưa descriptor đầu tiên** tới `ServiceFileTransformer`. Việc có dòng `mergeServiceFiles()` **không đủ** nếu bạn đã bỏ duplicate inputs trước đó.

Có hai chiến lược đúng để phối hợp:

1. `INCLUDE` tổng thể, `mergeServiceFiles()`, rồi xử lý **những resource không phải service descriptors** bằng policy riêng.
2. `EXCLUDE` tổng thể, `mergeServiceFiles()` và **override riêng `META-INF/services/**` thành `INCLUDE` để transformer nhìn đủ đầu vào.

Trong bài lab, chúng ta chọn **cách 2**: bảo thủ với những resource chưa rõ ý nghĩa, nhưng **cho phép service descriptors trùng đi qua transformer**.

## 5. Shadow plugin: phiên bản, compatibility và các task liên quan

Dùng GradleUp Shadow plugin ID:

```kotlin
plugins {
    id("com.gradleup.shadow") version "9.6.1"
}
```

Phiên bản **9.6.1** là bản phát hành đã được đăng trên Gradle Plugin Portal trong năm 2026; theo compatibility matrix của Shadow, nhánh **9.5+ yêu cầu Gradle 9.2+ và Java 17+ để chạy plugin**. Để thực hành đúng cấu hình ở đây, nên dùng **Gradle Wrapper 9.2+ tương thích** và JDK 17+ để chạy Gradle. Project Java trong lab dùng Java toolchain 17. Không dùng plugin version tương lai/không tồn tại; không đổi plugin ID về `com.github.johnrengelman.shadow` vì đó là ID lịch sử của plugin trước khi chuyển sang GradleUp.

Shadow thường cung cấp task `shadowJar`, với archive classifier mặc định `all`: khi project `:app` có `version = "1.0.0"`, đầu ra thông thường là:

```text
app/build/libs/app-1.0.0-all.jar
```

Lệnh build:

```bash
./gradlew :app:shadowJar
```

**Đừng giả định `jar` và `shadowJar` là cùng task.** `:app:jar` tạo artifact chuẩn; `:app:shadowJar` đóng gói dependencies theo policy Shadow. Phụ thuộc Gradle/plugin wiring, `build` có thể kéo thêm tasks nhưng pipeline quan trọng nên gọi task artifact mong muốn rõ ràng.

## 6. Bài lab Java 17 đầy đủ: hai provider cùng một service descriptor

Lab gồm **bốn Gradle subprojects**:

1. `:spi` định nghĩa interface `Greeting`.
2. `:english-provider` implement `Greeting`, cung cấp descriptor cùng đường dẫn.
3. `:vietnamese-provider` implement `Greeting`, cung cấp descriptor cùng đường dẫn.
4. `:app` gọi `ServiceLoader` để tìm providers và sử dụng Shadow đóng gói.

Đây là ví dụ có thể chạy thực tế với Gradle Wrapper đúng compatibility và Plugin Portal truy cập được. Không cần external Java libraries ngoài Shadow **build plugin**.

### 6.1. Cây thư mục chính xác

```text
fat-jar-services-lab/
├── settings.gradle.kts
├── spi/
│   ├── build.gradle.kts
│   └── src/main/java/demo/spi/Greeting.java
├── english-provider/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/providers/en/EnglishGreeting.java
│   └── src/main/resources/META-INF/services/demo.spi.Greeting
├── vietnamese-provider/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/providers/vi/VietnameseGreeting.java
│   └── src/main/resources/META-INF/services/demo.spi.Greeting
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
```

**Lưu ý:** hai descriptor files nằm trong **hai module khác nhau** nhưng tên **đường dẫn bên trong JAR trùng nhau**. Đây là điều kiện để minh họa mất provider khi naïve merge.

### 6.2. Root settings.gradle.kts

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "fat-jar-services-lab"
include(":spi", ":english-provider", ":vietnamese-provider", ":app")
```

Chúng ta dùng `pluginManagement.repositories` để tải **Shadow plugin**, khác với project dependency repositories. Toàn bộ Java code ở ví dụ dùng Gradle project dependencies nội bộ nên không cần `mavenCentral()`. Nếu tổ chức dùng plugin mirror, đặt đúng repository chứa plugin marker/implementation thay cho hoặc trước Plugin Portal.

### 6.3. SPI interface

**`spi/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

**`spi/src/main/java/demo/spi/Greeting.java`:**

```java
package demo.spi;

public interface Greeting {
    String language();

    String message();
}
```

Module này chỉ chứa contract. Nó **không tự triển khai** một provider và không có service descriptor. Hai provider modules đều compile dependency vào `:spi`.

### 6.4. English provider

**`english-provider/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":spi"))
}
```

**`english-provider/src/main/java/demo/providers/en/EnglishGreeting.java`:**

```java
package demo.providers.en;

import demo.spi.Greeting;

public final class EnglishGreeting implements Greeting {
    public EnglishGreeting() {
    }

    @Override
    public String language() {
        return "en";
    }

    @Override
    public String message() {
        return "Hello";
    }
}
```

**`english-provider/src/main/resources/META-INF/services/demo.spi.Greeting`:**

```text
demo.providers.en.EnglishGreeting
```

Service descriptor phải được lưu như resource, không phải file Java và không thêm đuôi `.txt`. Java plugin sẽ chép nó từ `src/main/resources` vào JAR của provider khi đóng gói.

### 6.5. Vietnamese provider

**`vietnamese-provider/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":spi"))
}
```

**`vietnamese-provider/src/main/java/demo/providers/vi/VietnameseGreeting.java`:**

```java
package demo.providers.vi;

import demo.spi.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String language() {
        return "vi";
    }

    @Override
    public String message() {
        return "Xin chào";
    }
}
```

**`vietnamese-provider/src/main/resources/META-INF/services/demo.spi.Greeting`:**

```text
demo.providers.vi.VietnameseGreeting
```

Hai modules provider dùng **cùng resource path** nhưng **nội dung khác nhau**. Nếu cả hai JAR nằm riêng trên classpath, `ServiceLoader` có thể khám phá cả hai. Nếu fat JAR chỉ giữ resource từ English provider, service Vietnamese sẽ bị “ẩn” khỏi discovery dù class `VietnameseGreeting.class` vẫn được đóng gói.

### 6.6. Ứng dụng sử dụng ServiceLoader

**`app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.spi.Greeting;

import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        var greetings = new TreeMap<String, String>();

        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            String old = greetings.putIfAbsent(
                provider.language(), provider.message()
            );
            if (old != null) {
                throw new IllegalStateException(
                    "Duplicate language: " + provider.language()
                );
            }
        }

        greetings.forEach((language, message) ->
            System.out.println(language + "=" + message)
        );
        System.out.println("providers=" + greetings.size());
    }
}
```

- App chỉ biết interface `demo.spi.Greeting`, không trực tiếp `new EnglishGreeting()` hoặc `new VietnameseGreeting()`.
- Provider implementation modules sẽ nằm trên **runtime classpath** và cung cấp service descriptors.
- `TreeMap` sắp xếp kết quả theo `language()` nên output **ổn định**, không phụ thuộc thứ tự ServiceLoader tìm thấy các JAR.
- Nếu descriptor Vietnamese mất, app thường vẫn chạy nhưng chỉ in provider còn lại. Đây là **lỗi chức năng âm thầm**, không nhất thiết là `ClassNotFoundException`.
- Hai providers ở demo có key khác nhau, nên không rơi vào nhánh báo duplicate language.

### 6.7. app/build.gradle.kts: cả JAR naïve và Shadow JAR đúng

**`app/build.gradle.kts`:**

```kotlin
import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.jvm.tasks.Jar

plugins {
    id("application")
    id("com.gradleup.shadow") version "9.6.1"
}

version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

dependencies {
    implementation(project(":spi"))
    runtimeOnly(project(":english-provider"))
    runtimeOnly(project(":vietnamese-provider"))
}

// Fat JAR chuẩn: để mọi descriptor đi tới ServiceFileTransformer.
tasks.named<ShadowJar>("shadowJar") {
    // Giữ first-found cho resource khác nếu không có transformer riêng.
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    // Chỉ cho phép duplicate service descriptors vào merge pipeline.
    filesMatching("META-INF/services/**") {
        duplicatesStrategy = DuplicatesStrategy.INCLUDE
    }

    // Gộp tất cả provider lines cùng service type thành một descriptor.
    mergeServiceFiles()

    manifest {
        attributes["Main-Class"] = "demo.app.Main"
    }
}

// Đối chứng có chủ đích: giải nén mọi runtime JAR một cách naïve,
// giữ descriptor đầu tiên và làm mất provider còn lại.
val runtimeJars = configurations.named("runtimeClasspath")

tasks.register<Jar>("naiveFatJar") {
    group = "build"
    description = "Counterexample: naive fat JAR drops duplicate resources"
    archiveClassifier.set("naive")

    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    manifest {
        attributes["Main-Class"] = "demo.app.Main"
    }

    from(sourceSets.main.get().output)
    // Lấy cả task dependencies xây JAR từ project dependencies.
    dependsOn(runtimeJars)
    from({
        runtimeJars.get().files.map { file ->
            if (file.isDirectory) file else zipTree(file)
        }
    })
}
```

**Những quyết định đáng chú ý:**

1. `implementation(project(":spi"))` đưa SPI interface vào **compile** và runtime classpath của app.
2. `runtimeOnly(project(":english-provider"))` và `runtimeOnly(project(":vietnamese-provider"))` đưa provider JAR vào runtime (và vào Shadow input), không lộ implementation vào compile source của app.
3. `tasks.named<ShadowJar>("shadowJar")` cấu hình task của Shadow đã được plugin tạo.
4. `mergeServiceFiles()` khai báo ResourceTransformer cho `META-INF/services`.
5. `filesMatching("META-INF/services/**") { duplicatesStrategy = INCLUDE }` đảm bảo **hai resources trùng tên không bị loại trước khi transformer đọc**.
6. `duplicatesStrategy = EXCLUDE` tổng thể vẫn chỉ giữ file đầu tiên đối với **những resource chưa có transformer**. Điều này là policy ví dụ, **không đủ an toàn chung cho production** nếu những resource khác cũng cần hợp nhất.
7. `manifest` cung cấp `Main-Class` để có thể chạy `java -jar`.
8. `naiveFatJar` dùng core `Jar`, giải nén dependencies bằng `zipTree` và `EXCLUDE`. Nó chỉ để **chứng minh lỗi phổ biến**, không phải một mẫu fat-JAR production.
9. `dependsOn(runtimeJars)` ở task naïve là nỗ lực giữ task dependencies của artifacts từ project runtimeClasspath; trong build lớn nên dùng mô hình artifact/provenance của plugin chuyên dụng thay vì tự xử lý `zipTree`.
10. `filesMatching` là API CopySpec; tài liệu Shadow cảnh báo việc dùng một số CopySpec hooks có thể ảnh hưởng output caching. Đánh đổi này phù hợp cho lab; với pipeline lớn nên review policy/transformers và cache behavior.

**Không copy đoạn naïve vào dự án thật** để thay thế Shadow. Giải nén JAR bằng `zipTree` ở mức Gradle core làm bạn phải tự chịu trách nhiệm về service descriptors, signed metadata, multi-release paths và resource transformations.

## 7. Chạy lab và kiểm tra sự khác biệt

### 7.1. Thin classpath: cả hai providers có mặt

Từ root project có Gradle Wrapper tương thích:

```bash
./gradlew --version
./gradlew -q :app:run
```

Stdout từ ứng dụng:

```text
en=Hello
vi=Xin chào
providers=2
```

`application` plugin chạy app với runtime classpath gồm `:spi` và hai provider dependencies ở các JAR riêng. `ServiceLoader` thấy cả hai service descriptors.

### 7.2. Naïve fat JAR: duplicate descriptor bị mất

```bash
./gradlew :app:naiveFatJar
java -jar app/build/libs/app-1.0.0-naive.jar
```

Từ cấu trúc lab chỉ có hai providers cùng đóng góp một descriptor, `EXCLUDE` sẽ khiến fat JAR naïve **chỉ giữ một trong hai descriptors**. Output minh họa **có thể** là:

```text
en=Hello
providers=1
```

Hoặc:

```text
vi=Xin chào
providers=1
```

**Không khẳng định provider nào “luôn thắng”** trên mọi Gradle version, task order hoặc source ordering. Điều quan trọng, với đúng cấu trúc demo, là chỉ còn **một provider** được khám phá qua ServiceLoader. Hai classes provider có thể vẫn tồn tại trong JAR, nhưng một provider thiếu tên trong descriptor và không được discover.

### 7.3. Shadow JAR: descriptor được hợp nhất

```bash
./gradlew :app:shadowJar
java -jar app/build/libs/app-1.0.0-all.jar
```

Stdout từ ứng dụng:

```text
en=Hello
vi=Xin chào
providers=2
```

Đó là kỳ vọng quan trọng: **số provider và behavior khi chạy fat JAR khớp với application chạy trên thin runtime classpath**.

### 7.4. Lưu ý về môi trường chạy

- Dùng **Gradle Wrapper 9.2+** và Java 17+ để chạy phiên bản Shadow 9.6.1 đã pin; Java toolchain của modules chọn JDK 17 cho compile/run.
- Nếu chưa có Wrapper, dùng Gradle đã cài tương thích để chạy `gradle wrapper` một lần, sau đó lưu Wrapper scripts và `gradle/wrapper` trong Git.
- Lần đầu Gradle phải resolve Shadow plugin và dependencies của plugin từ Gradle Plugin Portal (hoặc mirror).
- Trên Windows dùng `gradlew.bat`/`.\gradlew.bat`.
- Lệnh `java -jar` dùng runtime Java trên PATH: với mã Java 17, cần Java 17 hoặc mới hơn. Kiểm tra `java -version` khi gặp `UnsupportedClassVersionError`.

## 8. Kiểm tra thật nội dung service descriptor trong JAR

Chỉ nhìn `providers=2` đã hữu ích, nhưng khi audit production artifact hãy kiểm tra **resource entries** và nội dung descriptor.

### 8.1. Dùng JDK jar tool

```bash
jar tf app/build/libs/app-1.0.0-naive.jar
jar tf app/build/libs/app-1.0.0-all.jar
```

Tìm những dòng:

```text
META-INF/services/demo.spi.Greeting
demo/providers/en/EnglishGreeting.class
demo/providers/vi/VietnameseGreeting.class
```

Các class files cần tồn tại, nhưng **sự tồn tại của class không chứng minh service descriptor chứa tên class**. `jar tf` liệt kê entries chứ không hiển thị contents. Không cần trông chờ output đầy đủ của `jar tf` giống nhau giữa phiên bản Gradle, vì archive còn manifest/Gradle resources khác.

### 8.2. Viết tool Java 17 độc lập để audit descriptor

Tạo một file tại root **`JarServiceAudit.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarFile;

public final class JarServiceAudit {
    private JarServiceAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Provide one JAR path");
        }

        String service = "META-INF/services/demo.spi.Greeting";

        try (JarFile jar = new JarFile(args[0])) {
            long count = jar.stream()
                .filter(entry -> entry.getName().equals(service))
                .count();

            var descriptor = jar.getJarEntry(service);
            if (descriptor == null) {
                throw new IllegalStateException("Descriptor missing");
            }

            try (var reader = new BufferedReader(
                    new InputStreamReader(
                        jar.getInputStream(descriptor),
                        StandardCharsets.UTF_8
                    ))) {

                var providers = reader.lines()
                    .map(String::strip)
                    .filter(line -> !line.isEmpty())
                    .filter(line -> !line.startsWith("#"))
                    .sorted()
                    .toList();

                System.out.println("descriptor.entries=" + count);
                System.out.println("declared.providers=" + providers.size());
                providers.forEach(System.out::println);
            }
        }
    }
}
```

Với Java 17 JDK cài sẵn, biên dịch **không cần Gradle**:

```bash
mkdir -p audit-out
javac -encoding UTF-8 -d audit-out JarServiceAudit.java
java -cp audit-out JarServiceAudit app/build/libs/app-1.0.0-all.jar
```

Kết quả đối với Shadow JAR được merge đúng:

```text
descriptor.entries=1
declared.providers=2
demo.providers.en.EnglishGreeting
demo.providers.vi.VietnameseGreeting
```

Với JAR naïve, kết quả sẽ có `descriptor.entries=1`, `declared.providers=1` và **một trong hai class names**. Việc dùng `JarFile.getJarEntry()` với archive có nhiều entries trùng tên có thể chọn một entry cụ thể; vì thế **đếm ZIP entries** là phép đo riêng với **đếm provider lines**. Trong final Shadow JAR đúng, ta kỳ vọng **một descriptor hợp nhất** chứa **hai lines**.

Đoạn tool audit là chương trình Java độc lập; nó không cần dependency Gradle, JUnit hay Shadow khi chạy. Chạy `javac` và `java` từ JDK 17+; dùng `java` trên PATH khác phiên bản nếu cần sẽ không thay logic đọc ZIP/UTF-8 ở đây.

## 9. Cấu hình Groovy DSL tương đương cho lab

Giữ nguyên các **Java files** và resource files từ mục 6. Thay `settings.gradle.kts` bằng **`settings.gradle`**:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'fat-jar-services-lab'
include 'spi', 'english-provider', 'vietnamese-provider', 'app'
```

Ở `spi/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Ở **`english-provider/build.gradle`** và **`vietnamese-provider/build.gradle`**, dùng cùng nội dung:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':spi')
}
```

**`app/build.gradle`:**

```groovy
import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import org.gradle.api.file.DuplicatesStrategy

plugins {
    id 'application'
    id 'com.gradleup.shadow' version '9.6.1'
}

version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':spi')
    runtimeOnly project(':english-provider')
    runtimeOnly project(':vietnamese-provider')
}

tasks.named('shadowJar', ShadowJar) {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    filesMatching('META-INF/services/**') {
        duplicatesStrategy = DuplicatesStrategy.INCLUDE
    }

    mergeServiceFiles()

    manifest {
        attributes 'Main-Class': 'demo.app.Main'
    }
}

def runtimeJars = configurations.runtimeClasspath

tasks.register('naiveFatJar', Jar) {
    group = 'build'
    description = 'Counterexample: naive fat JAR drops duplicate resources'
    archiveClassifier.set('naive')

    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    manifest {
        attributes 'Main-Class': 'demo.app.Main'
    }

    from(sourceSets.main.output)
    dependsOn(runtimeJars)
    from({
        runtimeJars.files.collect { file ->
            file.isDirectory() ? file : zipTree(file)
        }
    })
}
```

Lưu ý:
- Đây là **một bộ build scripts thay thế Kotlin DSL**, không dán đồng thời cả hai phiên bản vào cùng project.
- Plugin ID/Shadow version và resource paths **giống nhau**, chỉ thay cú pháp.
- Các lệnh `./gradlew -q :app:run`, `:app:naiveFatJar` và `:app:shadowJar` vẫn có cùng kết quả chính theo cấu trúc demo.
- Groovy `Jar` class là task type do Gradle cung cấp; Kotlin dùng import `org.gradle.jvm.tasks.Jar`. Cả hai cấu hình `duplicatesStrategy` tại task.
- Nếu chỉ muốn dùng Shadow trong production, **bỏ task `naiveFatJar`** vì nó chỉ để chứng minh lỗi.

## 10. Một cấu hình Shadow thay thế: INCLUDE toàn bộ rồi chọn policy riêng

Ở mục 6.7 chúng ta đặt `EXCLUDE` tổng thể nhưng cho service descriptors `INCLUDE`. Shadow documentation còn có mẫu:

**Kotlin (thay cấu hình `shadowJar` trong lab):**

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    // Cho tất cả duplicates đi tới transformers ban đầu.
    duplicatesStrategy = DuplicatesStrategy.INCLUDE

    // Gộp service descriptors thành một resource theo service type.
    mergeServiceFiles()

    // Các resources không thuộc META-INF/services: chọn chính sách riêng.
    filesNotMatching("META-INF/services/**") {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}
```

**Groovy:**

```groovy
tasks.named('shadowJar', ShadowJar) {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()

    filesNotMatching('META-INF/services/**') {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}
```

Hai cách nhìn tương đương về mục tiêu **cho service descriptors được merge, những tài nguyên còn lại có policy rõ**. Khi dùng transformer khác (Spring metadata, Log4j plugin cache...), phải thay policy cho từng resource đó tương ứng; một global `EXCLUDE` cho mọi thứ khác có thể vẫn phá chức năng.

**Quan trọng:** các lời gọi `filesMatching`/`filesNotMatching` từ `CopySpec` có thể làm vô hiệu hóa output caching của Shadow task theo cảnh báo tài liệu. Hãy đo lường hoặc dùng resource transformer chuyên dụng như `PreserveFirstFoundResourceTransformer` khi cần, thay vì tùy tiện thêm nhiều copy actions vào production. Không phải mọi build cần tối đa cacheability bằng mọi giá; tính đúng đắn của artifact ưu tiên trước.

## 11. Vì sao chỉ để INCLUDE mà không merge cũng sai?

Một phản xạ phổ biến khi thấy duplicates là:

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    // Không gọi mergeServiceFiles().
}
```

Với service descriptor trùng path, thao tác này **có thể tạo nhiều ZIP entries có tên giống nhau**. Nó không tạo một danh sách providers đã ghép. Một số Zip APIs chọn entry đầu/entry cuối, một số tool xử lý khác nhau; không nên dựa vào hành vi không thống nhất.

Đặc biệt, `ServiceLoader` khi chạy từ **fat JAR chứa duplicate entries** có thể chỉ thấy một resource theo tên, chứ không bảo đảm nhìn thấy mọi bản descriptor giống như khi hai JAR **riêng** cùng nằm trên classpath.

Cơ chế đúng là:
1. Cho đủ duplicate inputs tới transformer.
2. Transformer hiểu định dạng và tạo **một resource hợp lệ**.
3. Kiểm tra bằng `JarFile`, `jar tf` và **behavior runtime**.

## 12. Phân loại tài nguyên trùng: không có một policy cho mọi file

Bảng sau là cơ sở xây một duplicate-resource policy trong team.

| Loại entry | Rủi ro khi trùng | Policy cần cân nhắc |
| --- | --- | --- |
| `META-INF/services/*` (Java SPI) | Mất một hoặc nhiều providers. | **Merge theo dòng** bằng `mergeServiceFiles()`; kiểm thử `ServiceLoader`. |
| `META-INF/spring.factories` | Nhiều properties keys và danh sách class implementations. | Dùng transformer/logic chuyên cho định dạng và version Spring; không ghép byte tùy tiện. |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Mất auto-configuration registrations. | Hợp nhất danh sách class names theo semantic của Spring Boot version; test startup. |
| `META-INF/spring.handlers`, `META-INF/spring.schemas` | Trùng keys ánh xạ Spring namespaces/schema. | Merge properties có kiểm tra xung đột key. |
| `Log4j2Plugins.dat` | Cache nhị phân cho Log4j 2 plugins. | Dùng transformer tương thích như Log4j2 plugin-cache transformer; không concat text. |
| `META-INF/services/org.codehaus.groovy.runtime.ExtensionModule` | Format riêng của Groovy extension modules. | Dùng Groovy extension module transformer; generic ServiceFileTransformer có ngoại lệ. |
| `reference.conf`/`application.conf` | Dữ liệu config phân cấp/priority; kết hợp có thể thay hành vi. | Dựa vào thư viện/framework config API hoặc transformer hiểu định dạng. |
| `META-INF/native-image/**` | Reflection/resource configs của GraalVM Native Image. | Merge JSON/config có kiểm tra để không mất metadata. |
| `module-info.class` | Các module descriptors khác nhau cùng path; JPMS graph. | Không “giữ ngẫu nhiên một module-info”; ưu tiên modular jars riêng hoặc xử lý module strategy có chủ đích. |
| `META-INF/versions/**` | Multi-release classes cùng đường dẫn versioned. | Bảo toàn `Multi-Release: true`, version paths và bytecode compatibility; kiểm thử runtime. |
| `META-INF/MANIFEST.MF` | Main-Class, Class-Path, sealing, Multi-Release, package metadata. | Tạo manifest đích rõ ràng, không gộp bằng copy raw. |
| `META-INF/*.SF`, `*.DSA`, `*.RSA`, `*.EC` | Metadata chữ ký của JAR nguồn. | Không giữ chữ ký đã mất hiệu lực; xác định policy xác minh/re-sign final artifact. |
| `META-INF/INDEX.LIST` | Chỉ mục classpath của JAR nguồn có thể không phù hợp với archive mới. | Xem xét loại bỏ/cập nhật theo chính sách. |
| `LICENSE`, `NOTICE`, `META-INF/LICENSE*` | Nghĩa vụ pháp lý của nhiều dependencies. | Bảo toàn, tổng hợp và kiểm tra thông báo bản quyền; **không xóa âm thầm**. |
| `log4j2.xml`, `application.properties` | Config chạy app có thể bị override ngoài ý muốn. | Quyết định file canonical; tránh “first wins” nếu chưa biết semantics. |
| `META-INF/gradle-plugins/*.properties` | Gradle plugin marker metadata. | Hạn chế gộp vào runtime ứng dụng nếu không cần; kiểm tra classloader/resource requirements. |
| Identical PNG/font/static resource paths | Một resource có thể bị mất. | So sánh bytes/hash; giữ một bản nếu đồng nhất và được chấp thuận, báo FAIL nếu khác. |

**Không phải tất cả entries trong bảng đều hiện diện ở mọi ứng dụng.** Hãy scan các dependency JAR thật để chọn policies có ý nghĩa, thay vì loại toàn bộ `META-INF/**` theo kiểu “cho sạch”.

## 13. Gộp resource text, binary và properties là ba chuyện khác nhau

### 13.1. Java service descriptor: danh sách provider class names

Có thể hợp nhất các dòng non-empty/comment đã làm sạch, với lưu ý semantics của ServiceLoader và relocation. Shadow `mergeServiceFiles()` được thiết kế cho trường hợp này.

### 13.2. Plain-text resource: chỉ append khi format cho phép

Một file `config.txt` do hai dependencies cung cấp có thể **không** cho phép nối nội dung. Nếu bạn cần append thật, phải biết ngữ pháp: newline boundary, comment format và ý nghĩa khi trùng key.

Shadow có các resource transformers hỗ trợ append text files và XML trong một số trường hợp. Ví dụ `append("...")` chỉ nên dùng khi **định dạng và thứ tự** cho phép. Không append JSON hoặc YAML bừa bãi, vì hai documents liền nhau có thể không phải một document hợp lệ.

### 13.3. Binary metadata: không nối bytes

`Log4j2Plugins.dat` là cache nhị phân; ghép raw bytes của hai file gần như không có ý nghĩa. Tương tự metadata JSON của native image cần merge theo keys/arrays, không nối hai JSON objects thành một file. Dùng transformer mà plugin/framework khuyến nghị và kiểm tra behavior thực tế.

### 13.4. Properties-like resources: quyết định xung đột keys

Với `spring.factories`, `spring.handlers` hay một file `config.properties` tự viết, các key trùng có thể có semantics khác nhau:

- Có key là danh sách cần append/union.
- Có key là mapping một-một và trùng giá trị là lỗi cấu hình.
- Có key được ưu tiên theo application override.

Một transformer chỉ “lấy file cuối” hoặc “lấy file đầu” không biết ý nghĩa nghiệp vụ. Chính sách phải được chốt theo framework version và kiểm chứng bằng test.

## 14. Gộp service descriptors và relocation package

Shadow hỗ trợ **relocation** để đổi namespace package trong output, chẳng hạn đổi một package thư viện nhằm tránh xung đột class names. Relocation cũng đặt ra yêu cầu sửa metadata.

Ví dụ minh họa Kotlin (chỉ dùng khi bạn thật sự cần relocate một library):

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()
    relocate("com.vendor.alpha", "com.example.shaded.alpha")
}
```

Với service descriptor:
- Nếu service type `com.vendor.alpha.Service` được relocate, **tên file descriptor** có thể cần đổi theo.
- Nếu provider class `com.vendor.alpha.Provider` được relocate, **dòng bên trong descriptor** phải chỉ tới class name mới.
- Transformer/relocator của plugin có thể hỗ trợ remapping một số metadata, nhưng không nên suy luận tất cả file text/XML/binary được sửa tự động.
- Khi có reflection qua `Class.forName("...")`, resource URLs, JNI/native libraries, serialization, protobuf hoặc class-name strings trong metadata, cần audit thêm.

Đây là ví dụ policy, **không chạy trong lab chính** vì lab không có package `com.vendor.alpha`. Với sản phẩm thật, luôn kiểm tra `ServiceLoader`/runtime behavior sau relocation, không chỉ kiểm tra JAR build thành công.

## 15. Minimization: nhỏ JAR nhưng có thể xóa mất provider

Một số shading tools hỗ trợ loại lớp dependency “không được dùng” nhằm giảm kích thước archive. Shadow có cơ chế **minimize**, và các phiên bản mới có lựa chọn liên quan R8/ProGuard khi được cấu hình.

Rủi ro lớn của SPI:
- App chỉ gọi `ServiceLoader.load(Greeting.class)`.
- Implementation `EnglishGreeting` được tham chiếu **bằng tên trong resource** `META-INF/services/...`, không phải bằng `new EnglishGreeting()` trong code.
- Một phân tích static reachability không hiểu service metadata hoặc reflection có thể kết luận provider class “không được dùng”, loại `.class` khỏi JAR.
- Descriptor vẫn còn, nhưng runtime ném `ServiceConfigurationError` vì provider được liệt kê không load được.

**Không bật minimize chỉ để giảm vài MB khi chưa có integration test chạy thực tế từ final JAR.** Nếu cần tối ưu, bảo toàn những packages/provider classes sử dụng qua SPI/reflection, framework component scanning, annotation processing output, JNI và dynamic classloading. So sánh content JAR và chạy suite smoke/integration test sau minimize.

## 16. Signed JAR, manifest và rủi ro security khi shading

### 16.1. Chữ ký của dependency JAR thường không còn hợp lệ sau khi gộp

JAR ký số có thể có `META-INF/*.SF`, `*.RSA`, `*.DSA` hoặc các entry liên quan. Khi thay đổi bytes/manifest/nội dung archive, chữ ký nguồn **không còn đại diện cho JAR mới**.

Dùng nguyên metadata chữ ký của các thư viện đã bị repack có thể làm Java báo `SecurityException: Invalid signature file digest for Manifest main attributes` hoặc lỗi xác minh khác.

Một phương án tùy use case là loại signature metadata nguồn **không còn hợp lệ**, sau đó **ký artifact cuối cùng** theo quy trình release/signing của tổ chức. Nhưng:
- Loại signature không thay thế việc kiểm chứng **nguồn dependency** trước build.
- Không loại toàn bộ `META-INF/**` vì có thể làm mất services, licenses và framework metadata.
- Nếu tổ chức bắt buộc giữ chữ ký gốc của từng JAR, **thin distribution** thường là kiến trúc phù hợp hơn.

Ví dụ policy chọn lọc (minh họa, không thêm vào lab chính khi chưa audit):

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    exclude("META-INF/*.SF", "META-INF/*.DSA", "META-INF/*.RSA")
}
```

Không dùng mẫu exclude như lời khuyên bao quát: cách nhận dạng chữ ký và luật bảo toàn cần phù hợp với dependencies, compliance và release pipeline cụ thể.

### 16.2. Manifest của fat JAR cần chính xác

`META-INF/MANIFEST.MF` có thể chứa `Main-Class`, `Class-Path`, `Multi-Release`, package sealing, build info hoặc metadata khác. Khi bạn hợp nhất nhiều JAR, không thể lấy manifest từ mọi dependency rồi “ghép” các thuộc tính theo thứ tự tùy ý.

Trong lab, `manifest { attributes["Main-Class"] = "demo.app.Main" }` quyết định entry point. Nếu Java runtime nói `no main manifest attribute`, vấn đề nằm ở manifest của **archive đang chạy**, không phải chỉ ở source Main.java.

Kiểm tra:

```bash
jar tf app/build/libs/app-1.0.0-all.jar
java -jar app/build/libs/app-1.0.0-all.jar
```

Chạy `jar tf` cho biết manifest có mặt nhưng không in nội dung thuộc tính; dùng `jar xf` vào thư mục riêng hoặc `JarFile.getManifest()` bằng Java nếu cần audit sâu.

### 16.3. SBOM, provenance và licensing

Gộp code vào một file **không làm mất trách nhiệm**:
- Ghi lại versions của tất cả dependencies đã đóng gói.
- Tạo SBOM (theo chính sách CycloneDX/SPDX hoặc tương đương).
- Quét license và NOTICE; tránh bỏ mất text quan trọng khi hai JAR cùng có `LICENSE`.
- Kiểm tra CVE trên **thành phần nguồn** ngay cả khi class names đã relocate.
- Ký và lưu provenance của final build artifact nếu chuỗi cung ứng yêu cầu.

Fat JAR là một hình thức distribution, **không phải cơ chế ẩn danh dependency**.

## 17. module-info.class, JPMS và multi-release JAR

### 17.1. JPMS module descriptors không cộng cơ học

Nếu nhiều dependency là named modules với `module-info.class`, fat JAR root không thể giữ nhiều module descriptors cùng path rồi hy vọng JVM vẫn hiểu như ban đầu. Bỏ hoặc giữ một descriptor có thể làm sai module graph, `requires`, `exports`, `uses` và `provides`.

Khi cần đúng Java Module System behavior:
- Ưu tiên giữ modular JARs riêng trên module path.
- Cân nhắc `jlink`/runtime image hoặc bản phân phối hỗ trợ JPMS.
- Nếu bắt buộc shade, cần chiến lược module metadata rõ và test với **module-path**, không chỉ classpath.
- Dùng `META-INF/services` trong unnamed module/classpath context **không tự thay thế** đầy đủ `module-info.java` trong named modules.

### 17.2. Multi-release JAR có versioned entries

Multi-release JAR có thể chứa:

```text
META-INF/MANIFEST.MF        (Multi-Release: true)
META-INF/versions/9/...
META-INF/versions/17/...
```

Khi shading, phải bảo toàn relation giữa versioned class paths và manifest attribute `Multi-Release: true`. Nếu mất attribute/đường dẫn hoặc ghép sai các versioned classes, runtime Java có thể dùng implementation không mong muốn.

Không gộp `module-info.class` hoặc versioned resources bằng một global first-wins policy thiếu kiểm chứng. Chạy tests ít nhất trên Java runtimes mà artifact cam kết hỗ trợ.

## 18. Giới hạn kích thước ZIP/JAR: ZIP64, số entries và bộ nhớ

JAR sử dụng container ZIP. ZIP truyền thống có giới hạn về số entries và kích thước; extension **ZIP64** hỗ trợ archives rất lớn.

Trong Gradle, `Jar`/`ShadowJar` có property `zip64`. Ví dụ minh họa:

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    isZip64 = true
}
```

Chỉ bật khi có nhu cầu và đã kiểm tra toolchain/consumer hỗ trợ. Tài liệu Gradle nhắc tới giới hạn ZIP thông thường khi vượt **65.535 entries** hoặc cần xử lý file/archive lớn hơn mức khoảng **4 GiB**. Dù ZIP64 giải quyết giới hạn container, một fat JAR khổng lồ vẫn có các vấn đề khác:

- Khởi động classpath scan chậm, thời gian deploy/upload/download lớn.
- CI cache và registry lưu artifact nặng.
- JVM classloading/reflection/resource scanning tăng chi phí.
- Công cụ bên thứ ba có thể không hỗ trợ ZIP64 hay một số ZIP features.
- Lỗi duplicate resource vẫn tồn tại; ZIP64 **không phải** transformer.

Nếu kích thước tăng bất thường, kiểm tra runtime dependencies được gộp, loại test-only dependencies khỏi runtimeClasspath và cân nhắc thin distribution/container layers thay vì chỉ bật ZIP64.

## 19. Reproducible fat JAR: thứ tự file và timestamps

Một artifact có nội dung logic tương tự vẫn có thể khác **byte-for-byte** giữa hai build do:
- Thứ tự entries trong ZIP.
- Timestamps từ source files/dependency JARs.
- Manifest/build info gắn thời gian, hostname hoặc đường dẫn máy.
- Phiên bản/metadata dependencies và Gradle/plugin versions khác nhau.
- Chiến lược first-wins khi duplicate input order không ổn định.

Gradle `Jar` có những properties thường dùng:

```kotlin
tasks.named<ShadowJar>("shadowJar") {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
```

Gradle mới có defaults hỗ trợ reproducibility cho archive tasks, nhưng **khai báo explicit vẫn nên được xem trong ngữ cảnh plugin/task/version**. Không hứa 100% deterministic archive chỉ vì hai flags này: transformers, ZIP metadata, build scripts, resolved dependency graph và environment cũng cần được kiểm soát.

Với duplicate policy kiểu `EXCLUDE`, “first-found” chỉ là một **lựa chọn**, không phải semantics business đã được xác định. Sử dụng transformers/validation rõ ràng và kiểm tra số providers/resource nội dung để tránh thứ tự đầu vào làm thay đổi chức năng ứng dụng.

## 20. Shadow và Gradle configurations: gộp dependency nào?

Shadow thường lấy dependency từ **`runtimeClasspath`** của project có ShadowJar. Vì vậy:

- `implementation` đưa dependency vào compile + runtime.
- `runtimeOnly` đưa provider implementation vào runtime mà app compile không cần trực tiếp biết provider class.
- `testImplementation` không tự thuộc `runtimeClasspath` của app. Không nên cố nhét JUnit/test dependencies vào fat JAR production.
- `compileOnly` không nằm trên runtime theo mặc định; nếu ứng dụng thật sự cần dependency lúc chạy, phải bảo đảm nó được cung cấp bởi deployment hoặc runtime scope.
- `api` của java-library có semantics của outgoing variants; app vẫn cần resolve runtime dependencies tương ứng qua variant-aware resolution.
- Gradle `runtimeClasspath` có thể chứa JARs, directories hoặc project outputs; tự `zipTree` mọi file mà không phân loại sẽ lỗi nếu gặp directories. Demo naïve đã phân biệt `file.isDirectory` nhưng vẫn không đầy đủ về resource semantics.

Để xem graph thật:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency spi --configuration runtimeClasspath
```

`dependencyInsight --dependency spi` chỉ là minh họa cách điều tra project/module có tên phù hợp; với lab này `:spi` là project dependency. Output reports phụ thuộc Gradle version, không có stdout cố định.

**Cảnh giác với optional dependencies.** Một JAR đã được shade không tự cung cấp những module optional không có trong resolved runtimeClasspath; các framework tạo class bằng reflection vẫn có thể thiếu implementation lúc chạy.

## 21. Kiểm tra đầu ra bằng automation thay vì nhìn log thủ công

### 21.1. Smoke test luôn chạy từ FINAL artifact

Một pipeline tốt có thể:

1. `./gradlew :app:shadowJar`.
2. Chạy `java -jar app/build/libs/app-1.0.0-all.jar` từ môi trường sạch.
3. Khẳng định stdout chứa đúng:
   - `en=Hello`
   - `vi=Xin chào`
   - `providers=2`
4. Chạy `JarServiceAudit`, khẳng định `descriptor.entries=1` và `declared.providers=2`.
5. Kiểm tra tập dependencies/license/signature policy và SBOM.

Kiểm tra `./gradlew :app:run` **chưa đủ**: nó chạy trên nhiều JARs riêng, có thể pass ngay cả khi fat JAR đã làm mất service descriptor. Cần kiểm tra **archive sau khi package**.

### 21.2. Gắn QA task vào lifecycle khi có chủ đích

Bạn có thể tạo task `verifyShadedJar` chạy sau `shadowJar` và kiểm tra archive như một phần release gate. Cách đơn giản là dùng một JavaExec task hoặc test process nhận đường dẫn `shadowJar.archiveFile` qua Provider, rồi dùng JDK APIs để đếm descriptors/providers.

Trong production, không nên truy cập `shadowJar.archiveFile.get().asFile` ở configuration phase khi không cần. Hãy dùng Provider để nối output của task producer vào input của consumer task, vừa giữ lazy configuration vừa bảo toàn task dependency.

**Không tự nối mọi smoke test tốn kém vào `build` nếu team cần vòng phát triển nhanh**; có thể nối vào `check`/`releaseCheck` theo policy hoặc một CI stage riêng. Điều quan trọng là build phát hành final artifact **bắt buộc** đi qua artifact-level tests trước deploy.

### 21.3. Không dựa vào unzip tool cụ thể của hệ điều hành

Một số tài liệu dùng:

```bash
unzip -p app/build/libs/app-1.0.0-all.jar META-INF/services/demo.spi.Greeting
```

Lệnh này hữu ích trên Unix khi có `unzip`, nhưng trên Windows tối giản có thể không có. Bài lab cung cấp `JarServiceAudit.java` dùng **JDK chuẩn**, chạy cross-platform khi có JDK 17+, tránh phụ thuộc `unzip` trong QA bắt buộc.

## 22. Các lỗi phổ biến và cách đọc đúng nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| `ServiceLoader` chỉ thấy 1 provider sau shading | Một descriptor bị `EXCLUDE` hoặc merge transformer không nhận đủ inputs. | Cho `META-INF/services/**` đi qua transformer bằng `INCLUDE`, gọi `mergeServiceFiles()`, audit output. |
| Build pass nhưng `ServiceConfigurationError: Provider ... not found` | Descriptor còn tên nhưng class provider đã bị loại/minimize/relocate sai. | So sánh class entries, disable minimize để thử, kiểm tra relocation mapping. |
| JAR có hai entries cùng tên descriptor | Global `INCLUDE` nhưng thiếu merge transformer. | Dùng `mergeServiceFiles()` và audit `descriptor.entries=1`. |
| `DuplicateFileCopyingException` | `FAIL` không cho phép duplicate path. | Chỉ cho phép/merge các loại resource hợp lệ; giữ FAIL cho collisions không mong muốn. |
| `META-INF/services` đã gộp nhưng Spring config mất | `mergeServiceFiles` không xử lý mọi metadata frameworks. | Dùng transformer/chính sách riêng cho Spring resources theo version. |
| Log4j 2 không tìm plugin sau shading | `Log4j2Plugins.dat` bị mất/ghi đè. | Dùng Log4j plugin-cache transformer tương thích. |
| Groovy extension module không chạy | Descriptor `ExtensionModule` dùng format khác SPI thông thường. | Dùng Groovy extension module transformer. |
| `SecurityException` khi mở JAR | Signed metadata nguồn không còn khớp sau repack. | Audit signatures, loại metadata không hợp lệ theo policy và re-sign final archive nếu cần. |
| `no main manifest attribute` | Fat JAR thiếu `Main-Class`. | Cấu hình manifest của task JAR thực sự được chạy. |
| `ClassNotFoundException` sau shading | Dependency không có trong runtimeClasspath, relocate/duplicate policy loại class, hoặc classloader khác. | Kiểm tra graph và `jar tf`, test final artifact. |
| `NoClassDefFoundError` chỉ khi chạy fat JAR | Optional/runtime dependency thiếu hoặc metadata bị mất. | Xem runtime dependencies và stacktrace, không dựa vào compile success. |
| `UnsupportedClassVersionError` | Build/run với JVM quá cũ so với classfile. | Chọn JDK/toolchain target phù hợp, chạy Java 17+ cho demo. |
| Một file `reference.conf` bị mất | Global EXCLUDE chọn bản đầu tiên. | Chọn config merge strategy hiểu định dạng. |
| `ZipException: duplicate entry` ở tool ngoài | Archive chứa duplicate entries do `INCLUDE` không transform. | Loại duplicates ngoài ý muốn, merge resource tương ứng. |
| Fat JAR quá lớn | RuntimeClasspath kéo theo nhiều artifacts, resources, transitive dependencies. | Audit dependency graph/size, loại không cần thiết một cách có căn cứ; cân nhắc thin distribution. |
| Không bật được ZIP64 hoặc tool khác không đọc | Giới hạn ZIP/ZIP64 compatibility. | Bật `isZip64` khi thực sự cần và test readers/deployment tools. |
| `java -jar` chạy nhưng ServiceLoader có 0 providers | Descriptor không đóng gói, tên file/service type sai hoặc provider load error. | Kiểm tra `src/main/resources`, descriptor paths, JAR entries và stderr. |
| `:app:run` đúng nhưng `java -jar all.jar` sai | Thin runtime classpath giữ hai descriptors riêng; shading mất metadata. | Đưa artifact-level smoke test vào release pipeline. |
| Shadow plugin không tải được | Thiếu Plugin Portal/mirror, Gradle/JDK không đủ version. | Kiểm tra `pluginManagement.repositories`, Wrapper và Shadow compatibility. |
| Spring Boot bootJar bị xung đột với shadowJar | Hai cơ chế packaging/launcher khác nhau. | Chọn workflow được framework hỗ trợ; không gộp plugins bừa bãi. |

## 23. Checklist trước khi phát hành fat JAR

1. **Phạm vi đầu vào:** `runtimeClasspath` chứa chính xác dependencies nào, có lẫn test/optional/untrusted không?
2. **SPI:** các service descriptors trùng đã gộp thành **một resource trên mỗi service type** chưa? Có còn đủ provider lines không?
3. **Classes:** các lớp provider còn trong final archive không, package names và constructor đúng không?
4. **Resources khác:** Spring, Log4j, Groovy, native-image, XML/properties/JSON có transformer/duplicate policy đúng semantics không?
5. **Manifest:** `Main-Class` và các attributes bắt buộc có đúng trong final JAR không?
6. **Chữ ký:** các signed dependency entries có bị repack mà giữ signature invalid không? Có release signing/provenance phù hợp không?
7. **License:** các license/NOTICE của dependencies có được bảo toàn và tổng hợp đúng policy pháp lý không?
8. **JPMS/multi-release:** module descriptors, versioned paths và `Multi-Release` metadata được xử lý có chủ đích chưa?
9. **Relocation/minimize:** các names trong descriptors và classes có tương ứng không? Có classes chỉ được gọi qua reflection bị loại không?
10. **Reproducibility:** dependency versions, Wrapper/Shadow plugin version, manifest dynamic fields, timestamps và file order có được kiểm soát không?
11. **Kích thước/ZIP64:** JAR có cần Zip64 không, runtime/tools có hỗ trợ và có chấp nhận kích thước deploy không?
12. **Smoke/integration test:** đã chạy **java -jar final artifact** trên Java runtime mục tiêu, không chỉ chạy `:app:run`?
13. **CI gate:** failure của artifact-level test có ngăn publish/deploy không?
14. **SBOM/vulnerability scanning:** nguồn dependencies đã được ghi nhận dù chúng bị shade/relocate?
15. **Plan B:** khi fat JAR phá behavior hoặc vượt yêu cầu compliance, đã cân nhắc `installDist`/`distZip` hoặc image/container giữ dependencies riêng chưa?

## 24. Bảng quyết định: chọn chiến lược nào?

| Câu hỏi | Cách làm |
| --- | --- |
| Hai thư viện có `META-INF/services/demo.spi.Greeting` cùng tên? | Cho cả hai inputs tới `ServiceFileTransformer` bằng `mergeServiceFiles` và duplicate policy phù hợp. |
| `mergeServiceFiles` nhưng vẫn mất provider? | Kiểm tra `duplicatesStrategy=EXCLUDE` có loại file trước transformer không. |
| Muốn chỉ service descriptors được phép trùng? | Global `EXCLUDE`, riêng `filesMatching("META-INF/services/**")` dùng `INCLUDE`; xem ảnh hưởng cache. |
| Muốn xử lý nhiều resource transformers? | Global `INCLUDE`/`WARN`, transformer phù hợp từng format, duplicate policy riêng cho phần còn lại. |
| Hai file `config.properties` khác giá trị? | Không tự merge theo tên file; quyết định precedence/key policy hoặc FAIL. |
| Metadata Log4j2 là binary cache? | Dùng transformer dành riêng; không concat. |
| JAR đã ký hoặc có `module-info.class`? | Audit signature/JPMS và cân nhắc giữ dependencies riêng. |
| Chỉ cần app chạy với dependencies, không bắt buộc một JAR? | Dùng Java Application distribution (thin JAR + lib/ + start scripts). |
| Muốn biết SPI còn đủ providers? | `java -jar` và `JarServiceAudit` trên **final JAR**. |
| Muốn so sánh trước/sau khi gộp? | Chạy `:app:run`, `:app:naiveFatJar`, `:app:shadowJar` rồi đối chiếu `providers`. |
| Muốn giảm kích thước bằng minimize? | Test reflection/ServiceLoader và dependencies trước khi loại classes. |
| Build reproducible? | Pin dependencies/versions, ổn định resource ordering và ZIP timestamps, kiểm tra bytewise artifact. |
| Vượt giới hạn ZIP thường? | Cân nhắc `isZip64=true` và compatibility; không coi đây là cách chữa mất resource. |

**Kết luận:** Một fat JAR không đơn giản là phép hợp ZIP. **Service descriptors có semantics danh sách provider registrations**, nên những resource cùng `META-INF/services/<service>` phải được **merge hợp lệ** để `ServiceLoader` tìm đủ implementations. Với Shadow, việc đặt `mergeServiceFiles()` phải đi kèm `DuplicatesStrategy` phù hợp vì **EXCLUDE có thể chặn duplicate resources trước transformer**. Những resource khác — signatures, Spring/Log4j metadata, manifest, multi-release và module descriptors — cần chính sách riêng; không có một “global duplicate switch” chữa tất cả. Hãy luôn kiểm tra **JAR đã đóng gói cuối cùng** bằng cả archive inspection lẫn runtime smoke test, và chọn thin distribution nếu yêu cầu kỹ thuật/pháp lý khiến shading quá rủi ro.

### Tài liệu chính thức và tham khảo

- [GradleUp Shadow — Controlling JAR Content Merging](https://gradleup.com/shadow/configuration/merging/): `mergeServiceFiles`, default duplicates strategy, transformer ordering, `filesMatching`/`filesNotMatching` và các transformer đặc biệt.
- [GradleUp Shadow — Getting Started](https://gradleup.com/shadow/): fat JAR, plugin ID và overview.
- [GradleUp Shadow — Change Log](https://gradleup.com/shadow/changes/): hành vi duplicate handling và compatibility theo release.
- [Gradle Plugin Portal — com.gradleup.shadow](https://plugins.gradle.org/plugin/com.gradleup.shadow): plugin ID và version phát hành.
- [Gradle — Jar Task DSL](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html): `duplicatesStrategy`, `zip64`, timestamps, reproducible file order, manifest.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `installDist`, `distZip`, thin distribution.
- [Gradle — Working With Files / Copying](https://docs.gradle.org/current/userguide/working_with_files.html): CopySpec, `DuplicatesStrategy` và JAR content.
- [Java SE 17 — ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider configuration files, discovery và module behavior.
- [Java SE 17 — JarFile API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): inspect JAR entries, manifest, ZIP resources.
