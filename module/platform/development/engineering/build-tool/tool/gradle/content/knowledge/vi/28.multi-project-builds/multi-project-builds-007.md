# Trao đổi artifact qua configuration và variant trong Gradle multi-project build

Trong một Gradle **multi-project build**, project `:producer` có thể tạo một JAR, ZIP, báo cáo, dữ liệu sinh từ schema hoặc một tệp cấu hình mà `:consumer` cần sử dụng. Cách dễ nghĩ nhất là cho consumer đọc thẳng đường dẫn `../producer/build/...` hoặc gọi `dependsOn(":producer:someTask")`. Nhưng cách đó khiến hai project **phụ thuộc vào tên task, bố cục output nội bộ và thứ tự build**. Khi producer đổi task/output, consumer dễ hỏng; khi bật Configuration Cache hoặc song song hóa build, thao tác truy cập Project/task của project khác còn làm tăng rủi ro unsafe cross-project access.

Gradle có cơ chế tốt hơn: **producer công bố artifact qua một consumable configuration (outgoing variant); consumer khai báo project dependency rồi resolve qua một resolvable configuration (incoming variant request)**. Gradle chọn artifact tương thích dựa vào **attributes**, đồng thời có thể tự nối task tạo output.

Bài Knowledge thuộc phần **Build nhiều dự án** của *Build Tool Gradle*. Bạn sẽ phân biệt ba vai trò của configuration, artifact và variant; hiểu attribute matching, compatibility/disambiguation, capabilities và Java API/runtime variants; thực hành **producer có hai ZIP variants debug/release và Java 17 consumer đọc variant đã chọn**; tìm hiểu task dependencies tự động, lazy resolution, Gradle CLI diagnostics, cách dùng Gradle Module Metadata khi xuất bản ra ngoài build và các anti-pattern cần tránh.

## 1. Vấn đề: cần output của project khác nhưng không muốn “chọc vào build/”

Giả sử:

~~~text
multi-project/
├── settings.gradle.kts
├── producer/
│   └── build.gradle.kts
└── consumer/
    └── build.gradle.kts
~~~

Producer có task tạo ZIP:

~~~text
producer/build/bundles/shared-bundle-debug.zip
~~~

Consumer cần ZIP để chạy một bước kiểm tra. Cách **không nên dùng**:

~~~kotlin
// Ví dụ sai về kiến trúc, không copy vào build.
tasks.register<Copy>("receiveBundle") {
    from("../producer/build/bundles/shared-bundle-debug.zip")
    into(layout.buildDirectory.dir("received"))
}
~~~

Lý do:

1. Đường dẫn tới output của project khác được hard-code.
2. Gradle không tự biết **task nào sản xuất file đó** chỉ từ một chuỗi đường dẫn.
3. Nếu chạy `./gradlew :consumer:receiveBundle` trong clean checkout, file producer có thể chưa tồn tại.
4. Consumer phải biết producer chọn tên archive, version/classifier, layout và task internals thế nào.
5. Khi producer thay artifact từ ZIP thành JAR hoặc có debug/release variants, consumer buộc phải sửa code riêng.
6. Với những output phức tạp, người viết dễ thêm `dependsOn(":producer:makeDebugBundle")` thủ công và tạo tight coupling giữa subprojects.

**Thiết kế nên dùng:** producer xuất một **hợp đồng artifact** gồm attribute và file do task tạo; consumer yêu cầu hợp đồng đó bằng dependency. Tên task/output path được giấu bên trong producer.

## 2. Đọc sơ đồ trước khi xem DSL

~~~text
                  :producer
      tasks.register<Zip>("makeDebugBundle")
                       |
                       v
            outgoing artifact: ZIP
                       |
       consumable config: debugBundleElements
       attributes: demo.bundle.mode = debug
                       |
                       | project(":producer")
                       |
                  :consumer
       dependencyScope: bundleDependencies
                       |
                       v
       resolvable config: selectedBundle
       attributes: demo.bundle.mode = debug
                       |
                       v
        variant-aware dependency resolution
                       |
                       v
                selected ZIP files
                       |
                       v
         Sync task: copy into build/received
                       |
                       v
            Java 17 program reads ZIP
~~~

Đổi consumer request thành `demo.bundle.mode = release` sẽ chọn **release variant**, không cần thay tên task của producer trong consumer code.

**Hai chiều của configuration không giống nhau:** producer nói “tôi *cung cấp* những variants nào”; consumer nói “tôi *cần* loại variant nào”. Gradle là bên đối chiếu.

## 3. Configuration có ba vai trò, không còn là một “túi” dùng cho mọi việc

Gradle hiện đại phân biệt:

| Vai trò | Gradle API | Flags về mặt ý nghĩa | Ví dụ tiêu chuẩn |
| --- | --- | --- | --- |
| **Declarable / dependency scope** | `configurations.dependencyScope("...")` | `canBeDeclared=true`; không resolve/consume | `implementation`, `api`, `testImplementation` |
| **Resolvable / incoming** | `configurations.resolvable("...")` | `canBeResolved=true`; không declare/consume | `compileClasspath`, `runtimeClasspath` |
| **Consumable / outgoing** | `configurations.consumable("...")` | `canBeConsumed=true`; không declare/resolve | `apiElements`, `runtimeElements` |

Ba factory `dependencyScope`, `resolvable` và `consumable` được tài liệu Gradle hiện tại trình bày là **incubating APIs**. Với Gradle 9.x hiện hành chúng là cách biểu đạt rõ ý định; khi làm việc trên Wrapper cũ phải đối chiếu Gradle API version thực tế.

Một configuration **nên có duy nhất một vai trò**. Đối với configuration tạo thủ công bằng API cũ, xác định rõ:

~~~kotlin
// Mảnh tương đương cách cũ, không cần khi dùng factory ở trên.
val outgoing = configurations.create("outgoingExample") {
    isCanBeResolved = false
    isCanBeConsumed = true
    isCanBeDeclared = false
}
~~~

Không tạo configuration với cả ba flags true rồi vừa `dependencies.add(...)`, vừa `resolve()`, vừa `artifacts.add(...)` như các tutorial cũ: Gradle đang tiến tới loại bỏ các cách sử dụng role mơ hồ.

### So sánh cách Java plugin phân tầng

~~~text
implementation    (declarable)
      |
      +--> compileClasspath   (resolvable)
      |
      +--> runtimeClasspath   (resolvable)
                    |
                    v
apiElements / runtimeElements  (consumable variants)
~~~

Sơ đồ khái niệm: plugin Java/Java Library có cấu trúc inheritance/variant metadata chi tiết hơn, nhưng điểm cốt lõi là **`implementation` để khai báo dependency; `compileClasspath` để resolve; `runtimeElements` để cung cấp**.

Bạn **không nên tự viết lại `implementation`, `compileClasspath`, `apiElements`** nếu Java plugin đã tạo chúng. Chỉ xây custom configurations khi có artifact/usage thực sự khác với những gì plugin cung cấp.

## 4. Artifact khác configuration và variant

**Artifact:** một file hoặc directory được một task tạo và Gradle có thể theo dõi, chẳng hạn:

~~~text
build/bundles/shared-bundle-debug.zip
build/libs/producer.jar
build/reports/schema-report.json
~~~

**Configuration:** một container có vai trò, dependencies, artifacts, attributes và các thông tin liên quan. Một **consumable configuration** có thể công bố **outgoing variant** của một project.

**Variant:** một lựa chọn cụ thể của component với **attributes, artifacts, dependencies và capabilities**. Ví dụ producer có:

~~~text
Variant A: bundle mode debug
    attributes: demo.bundle.mode = debug
    artifact: shared-bundle-debug.zip

Variant B: bundle mode release
    attributes: demo.bundle.mode = release
    artifact: shared-bundle-release.zip
~~~

Consumer yêu cầu `demo.bundle.mode=release` và Gradle sẽ chọn B khi matching rules cho phép. **Tên của variant/configuration** như `debugBundleElements` là chi tiết của producer; **attribute** mới là contract để consumer yêu cầu điều mình cần.

Với Java libraries, `apiElements` và `runtimeElements` là variants có sẵn do plugin cung cấp. Với một ZIP custom, bạn có thể công bố custom variant riêng.

## 5. Attribute matching diễn ra ở bước nào?

Khi consumer resolve `selectedBundle`:

1. Gradle đọc dependencies được khai báo, ví dụ `project(":producer")`.
2. Xác định các **consumable variants** producer đưa ra.
3. Đối chiếu **attributes của consumer** với attributes của từng producer variant.
4. Loại các variants không tương thích; nếu có nhiều variant hợp lệ, dùng disambiguation rules/chọn phương án phù hợp.
5. Chọn artifacts và dependency graph của variant.
6. Khi task yêu cầu file collection đó, Gradle có thể thực thi task producer để tạo artifacts trước.

Ví dụ:

| Consumer request | Producer debug variant | Producer release variant | Kết quả |
| --- | --- | --- | --- |
| `mode=debug` | `mode=debug` | `mode=release` | Chọn debug |
| `mode=release` | `mode=debug` | `mode=release` | Chọn release |
| `mode=staging` | `mode=debug` | `mode=release` | Không có variant tương thích, trừ khi định nghĩa compatibility rule |
| Không đặt mode attribute | Hai variants mang mode khác nhau | Cả hai có thể là candidates | Có thể mơ hồ; cần khai báo nhu cầu/chiến lược disambiguation |

**Attributes không chỉ là nhãn hiển thị.** Chúng có tên và kiểu dữ liệu. Cùng tên nhưng khai báo kiểu không tương thích (`String` so với `Named` chẳng hạn) có thể làm matching fail hoặc phát sinh lỗi metadata. Với custom attribute, producer/consumer phải thống nhất **tên, kiểu và ý nghĩa**.

## 6. Các attributes tiêu chuẩn và custom

Gradle cung cấp những attributes dùng rộng rãi:

| Attribute | Ví dụ giá trị | Vai trò |
| --- | --- | --- |
| `Usage.USAGE_ATTRIBUTE` | `java-api`, `java-runtime` | Artifact dùng để compile API hay chạy runtime |
| `Category.CATEGORY_ATTRIBUTE` | `library`, `documentation`, `platform` | Loại component |
| `LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE` | `jar`, `classes`, `resources` | Hình thức đóng gói của Java library |
| `Bundling.BUNDLING_ATTRIBUTE` | `external`, `embedded`, `shadowed` | Dependencies được đóng gói kiểu nào |
| `TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE` | `17` | JVM compatibility được Gradle Java ecosystem sử dụng |
| Custom `demo.bundle.mode` | `debug`, `release` | Ý nghĩa riêng của ZIP contract trong ví dụ |

Nên dùng attributes tiêu chuẩn khi nghĩa của chúng phù hợp. Ví dụ library runtime JAR có thể biểu diễn bằng `Usage.JAVA_RUNTIME` và `LibraryElements.JAR`. Với ZIP chứa một file data mode, không nên tự gắn `java-runtime` chỉ vì dự án dùng Java 17: đó **không phải Java runtime library**.

Trong ví dụ, ta dùng một custom attribute:

~~~kotlin
import org.gradle.api.attributes.Attribute

val bundleModeAttribute =
    Attribute.of("demo.bundle.mode", String::class.java)
~~~

Đoạn này là **mảnh khai báo**, phải được dùng nhất quán ở cả producer và consumer. Tên thuộc namespace của tổ chức trong dự án thật để tránh collision với các plugins khác.

## 7. Ví dụ hoàn chỉnh: debug/release ZIP variants, consumer chọn bằng property

### 7.1. Yêu cầu

- Gradle Wrapper dùng phiên bản **Gradle 9.x hỗ trợ `consumable` / `resolvable` / `dependencyScope`**.
- JDK 17 có sẵn làm Java toolchain; phiên bản JDK chạy Gradle phải tương thích với Wrapper.
- Không cần Maven Central, external Gradle plugins hoặc thư viện ngoài cho demo.
- Một shell hỗ trợ chạy `./gradlew` hoặc `gradlew.bat`.

Bài này cố ý tạo ZIP từ **các file dữ liệu** thay vì JAR từ Java bytecode, để tập trung vào **cross-project artifact sharing**. Consumer có một chương trình Java 17 dùng `java.util.zip.ZipFile` để đọc đúng ZIP đã được Gradle chọn.

### 7.2. Cây thư mục

~~~text
variant-sharing-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── producer/
│   ├── build.gradle.kts
│   └── src/bundles/
│       ├── debug/channel.txt
│       └── release/channel.txt
└── consumer/
    ├── build.gradle.kts
    └── src/main/java/demo/consumer/InspectBundle.java
~~~

Không có `build.gradle.kts` ở root vẫn hợp lệ: settings khai báo hai subprojects; mỗi project có script riêng. **Không tạo file output trong `producer/build/` bằng tay**; task `Zip` sẽ làm việc đó.

### 7.3. Root `settings.gradle.kts`

~~~kotlin
rootProject.name = "variant-sharing-demo"

include("producer", "consumer")
~~~

Sau đó Gradle nhận các project paths `:producer` và `:consumer`.

### 7.4. Data source của producer

Tạo file:

~~~text
producer/src/bundles/debug/channel.txt
~~~

với nội dung (một dòng, có thể có newline cuối file):

~~~text
debug
~~~

Tạo file:

~~~text
producer/src/bundles/release/channel.txt
~~~

với nội dung:

~~~text
release
~~~

Tập tin `channel.txt` được đóng vào ZIP dưới đường dẫn `payload/channel.txt`. Cả hai variants có cùng **file layout**, nhưng chứa **giá trị khác nhau**; vì vậy consumer có thể kiểm tra variant đúng bằng việc đọc nội dung file đã giải nén trên luồng ZIP.

### 7.5. Producer `build.gradle.kts` — toàn bộ file

~~~kotlin
import org.gradle.api.attributes.Attribute

val bundleModeAttribute =
    Attribute.of("demo.bundle.mode", String::class.java)

// Tạo hai ZIP artifacts từ hai bộ dữ liệu.
val debugZip = tasks.register<Zip>("makeDebugBundle") {
    archiveBaseName.set("shared-bundle")
    archiveVersion.set("")
    archiveClassifier.set("debug")
    destinationDirectory.set(layout.buildDirectory.dir("bundles"))

    from("src/bundles/debug") {
        into("payload")
    }
}

val releaseZip = tasks.register<Zip>("makeReleaseBundle") {
    archiveBaseName.set("shared-bundle")
    archiveVersion.set("")
    archiveClassifier.set("release")
    destinationDirectory.set(layout.buildDirectory.dir("bundles"))

    from("src/bundles/release") {
        into("payload")
    }
}

// Dùng cùng attribute schema cho cả hai outgoing variants.
dependencies {
    attributesSchema {
        attribute(bundleModeAttribute)
    }
}

// Chỉ có vai trò consumable, không resolve trong producer.
configurations.consumable("debugBundleElements") {
    attributes {
        attribute(bundleModeAttribute, "debug")
    }
}

configurations.consumable("releaseBundleElements") {
    attributes {
        attribute(bundleModeAttribute, "release")
    }
}

// TaskProvider<Zip> được gắn làm artifact:
// Gradle giữ mối liên kết builtBy tới nhiệm vụ tạo ZIP.
artifacts {
    add("debugBundleElements", debugZip)
    add("releaseBundleElements", releaseZip)
}
~~~

Đây là một **producer Gradle Kotlin DSL build file hoàn chỉnh** với Gradle 9.x. Không cần `java` plugin ở producer vì không có Java source trong producer: `Zip` là Gradle task type có sẵn. Nếu sau này producer tạo JAR từ source Java, áp dụng Java plugin và dùng `tasks.register<Jar>`/`from(sourceSets.main.get().output)` theo bài toán.

**Từng đoạn thực hiện gì?**

1. `Attribute.of("demo.bundle.mode", String::class.java)` xác định tên+kiểu của variant key.
2. `makeDebugBundle` tạo `build/bundles/shared-bundle-debug.zip`.
3. `makeReleaseBundle` tạo `build/bundles/shared-bundle-release.zip`.
4. `archiveVersion.set("")` bỏ version suffix, để archive names ổn định và dễ đọc trong demo.
5. `dependencies.attributesSchema.attribute(...)` đăng ký custom attribute tại project.
6. `configurations.consumable(...)` tạo hai outgoing configurations, mỗi configuration có một giá trị attribute riêng.
7. `artifacts.add(..., debugZip/releaseZip)` gắn **TaskProvider** làm artifact: Gradle biết file tạo từ task nào, không chỉ một string path.

**Không tự thêm `dependsOn(":producer:makeDebugBundle")` ở consumer.** Hợp đồng artifact đã cho Gradle dữ liệu để nối producer task khi resolving artifact.

### 7.6. Consumer `build.gradle.kts` — toàn bộ file

~~~kotlin
import org.gradle.api.attributes.Attribute

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.consumer.InspectBundle")
}

val bundleModeAttribute =
    Attribute.of("demo.bundle.mode", String::class.java)

// -PbundleMode=release chọn release; mặc định chọn debug.
val requestedMode = providers.gradleProperty("bundleMode").orElse("debug")

dependencies {
    attributesSchema {
        attribute(bundleModeAttribute)
    }
}

// 1) Chỗ chỉ để khai báo project dependency.
val bundleDependencies =
    configurations.dependencyScope("bundleDependencies")

// 2) Chỗ dùng để resolve artifact đã chọn.
val selectedBundle = configurations.resolvable("selectedBundle") {
    extendsFrom(bundleDependencies.get())

    attributes {
        attribute(bundleModeAttribute, requestedMode.get())
    }
}

dependencies {
    add("bundleDependencies", project(":producer"))
}

// Sync luôn giữ destination khớp đúng artifact set hiện tại.
// Khi đổi debug -> release, ZIP cũ trong received được dọn.
val receiveBundle = tasks.register<Sync>("receiveBundle") {
    from(selectedBundle)
    into(layout.buildDirectory.dir("received"))
}

// Java application đọc ZIP ở consumer/build/received.
tasks.named<JavaExec>("run") {
    dependsOn(receiveBundle)
}
~~~

Đây là **consumer Gradle Kotlin DSL build file đầy đủ**. `application` plugin cung cấp Java source compilation, `run` task và `mainClass` extension. Không cần repo bên ngoài vì consumer chỉ khai báo một **project dependency** tới `:producer`.

**Tách hai consumer configurations là cố ý:**

- `bundleDependencies` (`dependencyScope`): chỉ chứa declaration `project(":producer")`.
- `selectedBundle` (`resolvable`): kế thừa dependencies từ bucket, có attributes `demo.bundle.mode`.
- `from(selectedBundle)` trong `Sync`: Gradle resolve variant và lấy file(s) khi task cần.

Việc `selectedBundle` được khai báo **resolvable** không có nghĩa bạn nên đưa thêm dependencies trực tiếp vào đó: giữ **declaration riêng**, resolution riêng giúp config roles rõ ràng và thuận với Gradle hiện đại.

**Tại sao dùng `Sync` thay `Copy`?** Nếu chạy debug rồi release, `Copy` vào cùng thư mục có thể để lại hai ZIP; chương trình minh họa muốn thư mục `received` chứa đúng **một** artifact đã chọn. `Sync` cập nhật destination cho khớp input files, loại các file không còn thuộc tập đầu vào.

### 7.7. Java 17 program trong consumer

Tạo `consumer/src/main/java/demo/consumer/InspectBundle.java`:

~~~java
package demo.consumer;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.stream.Stream;

public final class InspectBundle {
    private InspectBundle() {
    }

    public static void main(String[] args) throws Exception {
        Path received = Path.of("build", "received");

        List<Path> zipFiles;
        try (Stream<Path> files = Files.list(received)) {
            zipFiles = files
                .filter(file -> file.getFileName().toString().endsWith(".zip"))
                .sorted()
                .toList();
        }

        if (zipFiles.size() != 1) {
            throw new IllegalStateException(
                "Expected exactly one ZIP, got " + zipFiles.size()
            );
        }

        try (ZipFile zip = new ZipFile(zipFiles.get(0).toFile())) {
            ZipEntry entry = zip.getEntry("payload/channel.txt");
            if (entry == null) {
                throw new IllegalStateException(
                    "Missing payload/channel.txt"
                );
            }

            try (InputStream input = zip.getInputStream(entry)) {
                String channel = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
                ).strip();

                System.out.println("Selected variant: " + channel);
            }
        }
    }
}
~~~

**Mã Java chạy độc lập** nếu đã có ZIP với entry `payload/channel.txt` trong đường dẫn `build/received` và Java 17. `Files.list` + `Stream.toList()` được Java 17 hỗ trợ. `ZipFile` đọc ZIP theo chuẩn JDK, không cần thư viện thứ ba.

`application` plugin chạy `JavaExec` với working directory mặc định là **consumer project directory**, phù hợp với `Path.of("build", "received")`. Nếu code được gọi trực tiếp từ IDE/Java CLI với working directory khác, phải đặt đúng current directory hoặc truyền đường dẫn file qua argument.

### 7.8. Chạy debug variant — không build producer thủ công

Từ root, Linux/macOS:

~~~bash
./gradlew :consumer:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :consumer:run --quiet
~~~

**Stdout chính xác do Java Main in ra**:

~~~text
Selected variant: debug
~~~

Gradle có thể in thêm logs/warnings tùy phiên bản, nhưng chuỗi trên là nội dung `System.out.println`. Gradle sẽ:

1. Cấu hình hai subprojects.
2. Consumer yêu cầu `demo.bundle.mode=debug`.
3. Resolver chọn `debugBundleElements` của producer.
4. Từ artifact `debugZip`, Gradle biết cần `:producer:makeDebugBundle`.
5. `:consumer:receiveBundle` lấy ZIP qua `selectedBundle`, đồng bộ tới `consumer/build/received`.
6. `:consumer:run` chạy Java 17 program và đọc `payload/channel.txt`.

Không có dòng nào trong consumer trực tiếp đọc `producer/build/bundles/...` hay gọi task producer theo tên.

### 7.9. Chạy release variant từ cùng consumer

~~~bash
./gradlew :consumer:run -PbundleMode=release --quiet
~~~

Windows:

~~~powershell
.\gradlew.bat :consumer:run -PbundleMode=release --quiet
~~~

**Stdout Java**:

~~~text
Selected variant: release
~~~

`-PbundleMode=release` là Gradle **project property**; consumer đọc bằng `providers.gradleProperty("bundleMode")`. Gradle request từ `debug` đổi sang `release`, match outgoing variant mới, và `Sync` loại ZIP debug còn dư.

Bạn có thể so sánh:

~~~text
Debug selected:
consumer/build/received/shared-bundle-debug.zip

Release selected:
consumer/build/received/shared-bundle-release.zip
~~~

Hai dòng tên file trên là **cấu trúc kỳ vọng sau mỗi lần Sync**, không phải các tệp cùng tồn tại sau lần release. Gradle không cần copy toàn bộ cả hai artifacts vào consumer trong một invocation.

### 7.10. Thử lỗi có chủ đích: không có variant

~~~bash
./gradlew :consumer:receiveBundle -PbundleMode=staging
~~~

Producer chỉ cung cấp `debug` và `release`. Vì vậy khi consumer yêu cầu `staging`, Gradle phải báo **không tìm được variant phù hợp** (dạng diagnostic có thể khác theo Gradle version). Không nên tạo ZIP mặc định im lặng trong trường hợp này: yêu cầu một contract không được producer cung cấp là lỗi kiến trúc/khai báo.

Nếu muốn `staging` fallback sang `debug`, bạn phải thiết kế **compatibility rule** hoặc normalize request trước khi resolve và tài liệu hóa rõ semantics; **không tự fallback bằng string path** tới một file tình cờ tồn tại.

## 8. Kiểm chứng variant model bằng Gradle CLI

Từ root:

~~~bash
./gradlew :producer:outgoingVariants --all
./gradlew :consumer:resolvableConfigurations --configuration selectedBundle
./gradlew :consumer:dependencies --configuration selectedBundle
./gradlew :consumer:receiveBundle --dry-run
~~~

Kết quả mong đợi về **nội dung**, không hứa một định dạng log byte-for-byte:

| Lệnh | Bạn kiểm tra được gì? |
| --- | --- |
| `:producer:outgoingVariants --all` | Hai variants `debugBundleElements` / `releaseBundleElements`, attribute và ZIP artifacts |
| `:consumer:resolvableConfigurations --configuration selectedBundle` | Consumer configuration có vai trò resolvable và requested attribute |
| `:consumer:dependencies --configuration selectedBundle` | Project dependency `:producer` trong graph |
| `:consumer:receiveBundle --dry-run` | Task graph có task producer tạo ZIP và consumer Sync tương ứng |
| `:consumer:dependencyInsight --configuration selectedBundle --dependency producer` | Đường selection/resolution trong trường hợp tool có thể chọn dependency để phân tích |

**`--dry-run` không tạo ZIP hoặc copy tệp**: chỉ quan sát scheduling. Khi output files chưa tồn tại, phải chạy task thật để xác minh artifact content và stdout Java.

### Đọc outgoing variant khác đọc incoming configuration

Producer:

~~~text
outgoingVariants -> tôi cung cấp gì?
  debugBundleElements: demo.bundle.mode=debug -> ZIP
  releaseBundleElements: demo.bundle.mode=release -> ZIP
~~~

Consumer:

~~~text
resolvableConfigurations -> tôi yêu cầu gì?
  selectedBundle: demo.bundle.mode=release
~~~

Nếu user gặp `No matching variant`, **so sánh hai báo cáo**, đừng chỉ xem tên task hoặc `implementation` dependencies.

## 9. Dependency từ artifact tự động làm nhiệm vụ ordering

Trong demo producer:

~~~kotlin
val debugZip = tasks.register<Zip>("makeDebugBundle") {
    // output ZIP...
}

artifacts {
    add("debugBundleElements", debugZip)
}
~~~

Điểm quan trọng là `debugZip` là một **TaskProvider<Zip>**, không phải chuỗi `"/producer/build/bundles/file.zip"`. Khi task output được publish như artifact, Gradle có metadata để biết **artifact được build bởi task nào**.

Consumer:

~~~kotlin
val receiveBundle = tasks.register<Sync>("receiveBundle") {
    from(selectedBundle)
    into(layout.buildDirectory.dir("received"))
}
~~~

`selectedBundle` là một Gradle configuration có dependency tới producer. Khi dùng làm file collection input của `Sync`, Gradle có thể kéo task sản xuất artifact vào graph. Vì vậy không cần:

~~~kotlin
// Tránh ở consumer:
dependsOn(":producer:makeDebugBundle")
~~~

Điều này khác với `tasks.named<JavaExec>("run") { dependsOn(receiveBundle) }` trong demo: đó là **dependency cùng project** giữa Java runtime task và bước nhận ZIP, được dùng vì Java application tự đọc một path trên disk khi chạy; nếu không nối `run` với `receiveBundle`, Gradle không thể tự biết từ Java source rằng trước khi run cần đồng bộ ZIP.

**Phân biệt:** cross-project task wiring nên xuất phát từ artifact dependency; within-project task wiring vẫn có thể cần khi một task không lấy Provider/FileCollection của output trực tiếp.

## 10. Lazy configuration và khi nào artifact thực sự được resolve

Các APIs:

~~~kotlin
tasks.register<Zip>("makeDebugBundle") { ... }
configurations.consumable("debugBundleElements") { ... }
configurations.dependencyScope("bundleDependencies")
configurations.resolvable("selectedBundle") { ... }
~~~

đều hỗ trợ mô hình khai báo/lazy tốt hơn cách truy cập `tasks.getByName` hoặc gọi `configurations["..."].files` ngay trong configuration phase.

**Không chủ động resolve configuration trong build script để in đường dẫn file:**

~~~kotlin
// Phản ví dụ:
val filesNow = configurations["selectedBundle"].files
println(filesNow)
~~~

Dạng này có thể khởi động resolution sớm trong configuration phase, làm giảm khả năng Configuration Cache/parallel configuration, và có thể gây unsafe access khi tác động tới project khác.

Hãy cung cấp configuration/FileCollection cho task input:

~~~kotlin
tasks.register<Sync>("receiveBundle") {
    from(selectedBundle)
    into(layout.buildDirectory.dir("received"))
}
~~~

Hoặc trong custom task type, mô hình hóa một `@InputFiles` / `ConfigurableFileCollection` property rồi lấy file lúc task action chạy; không đọc metadata/file outputs của producer trong configuration script của consumer.

### Vấn đề “safe across projects”

Gradle cảnh báo unsafe cross-project configuration resolution nếu consumer truy cập `project(":producer").configurations...` rồi resolve nó trực tiếp từ build script hoặc task của consumer. **Project dependency** là API an toàn hơn vì Gradle tự quản lý graph và access boundaries.

Không cần viết:

~~~kotlin
// Phản ví dụ, tránh trong consumer:
val producerFiles =
    project(":producer").configurations["debugBundleElements"].files
~~~

Trong multi-project build hiện đại, hướng này có thể gây lỗi/deprecation và làm phá encapsulation: consumer đang chạm **nội bộ project model của producer** thay vì tuyên bố dependency.

## 11. Vì sao cấu hình “chỉ tên” không đủ?

Legacy code đôi khi viết:

~~~kotlin
// Cách cũ, KHÔNG nên dùng cho build mới.
dependencies {
    add(
        "bundleDependencies",
        project(
            mapOf(
                "path" to ":producer",
                "configuration" to "debugBundleElements"
            )
        )
    )
}
~~~

Ý tưởng là consumer chỉ thẳng tên configuration của producer. Cách này **làm lộ tên configuration nội bộ**, hạn chế khả năng producer đổi cấu trúc và bỏ qua lợi ích variant-aware selection. Gradle hướng dẫn **ưu tiên attributes** cho các consumable/resolvable configurations; cách chọn trực tiếp configuration theo tên đã bị loại bỏ ở một số đường resolution của Maven/Ivy và không phải hướng phát triển cho project dependencies mới.

Cũng **không tạo consumable configuration không có attribute** rồi hy vọng Gradle chắc chắn chọn nó chỉ vì “producer chỉ có một variant”. Theo tài liệu Gradle Best Practices, thiếu attributes làm dependency resolution mong manh, có thể báo không tìm được variant.

Trong demo, chính `demo.bundle.mode` giúp Gradle match **ý định** thay vì tên implementation.

## 12. Compatibility và disambiguation: khi nào cần rules?

Một attribute matching engine có hai loại rules quan trọng:

- **Compatibility:** consumer yêu cầu giá trị A, producer cung cấp B, vậy B có được chấp nhận không?
- **Disambiguation:** nếu nhiều producer variants **đều tương thích**, nên chọn variant nào?

Ví dụ với Java target version, Gradle có built-in rules để consumer Java 17 không tự chọn variant build cho Java cao hơn không tương thích. Với custom `demo.bundle.mode`, demo giữ matching **chính xác**: debug ≠ release. Đây là cách dễ hiểu và an toàn nhất cho artifact có nội dung khác nhau.

Nếu phát sinh yêu cầu:

~~~text
consumer asks: staging
producer offers: debug, release
policy: staging may use debug but must never silently use release
~~~

thì đó là **một quy tắc nghiệp vụ** cần được thiết kế rõ. Có hai lựa chọn:

1. Normalize project property `bundleMode=staging` thành `debug` **trước khi tạo requested attribute**, ghi rõ behavior.
2. Viết custom `AttributeCompatibilityRule<T>` và nếu nhiều candidates, `AttributeDisambiguationRule<T>` để thực thi policy.

Không nên thêm compatibility rule chỉ để che lỗi gõ sai `-PbundleMode=relase`. Default fail rõ ràng giúp phát hiện cấu hình sai nhanh hơn.

### Lưu ý kiểu của custom attribute

~~~kotlin
Attribute.of("demo.bundle.mode", String::class.java)
~~~

và:

~~~kotlin
Attribute.of("demo.bundle.mode", SomeNamedType::class.java)
~~~

**không phải cùng schema** dù tên giống. Khi publish artifacts ra repository kèm Gradle Module Metadata, custom attribute values/types cần tương thích với consumer build tool ecosystem. Với use case đơn giản trong một multi-project build, String đủ để minh họa.

## 13. Java Library: variant sharing diễn ra sẵn mà không cần custom ZIP

Với project `:library`:

~~~kotlin
plugins {
    id("java-library")
}
~~~

Gradle tự có outgoing variants:

~~~text
apiElements
    org.gradle.usage = java-api
    ...
runtimeElements
    org.gradle.usage = java-runtime
    ...
~~~

Consumer:

~~~kotlin
plugins {
    id("application")
}

dependencies {
    implementation(project(":library"))
}
~~~

Đây là mô hình **project dependency tiêu chuẩn**. Gradle Java plugins tự thiết lập compile/runtime configurations, usages, attributes và task graph:

- `compileJava` của consumer cần Java API-compatible variant của library.
- `run` / runtimeClasspath cần runtime-compatible variant của library.
- Nếu library thêm external runtime dependencies, runtime variant công bố chúng phù hợp.

**Không phải mọi project dependency đều phải tự tạo `consumable`/`resolvable`.** Khi cần JAR/classes của Java library, dùng conventions chuẩn. Chỉ xây custom variant khi artifact có ý nghĩa riêng (ZIP dữ liệu, instrumented JAR, generated schema, test fixtures, docs, platform-specific resource).

## 14. Feature variants và capabilities khác custom ZIP variant như thế nào?

Java Library plugin hỗ trợ **feature variants** để một thư viện có các phần chức năng tùy chọn. Ví dụ:

~~~kotlin
plugins {
    id("java-library")
}

java {
    registerFeature("jsonSupport") {
        usingSourceSet(sourceSets.create("jsonSupport"))
    }
}
~~~

Đây là **mảnh build script**: source set và feature được khai báo, nhưng muốn có code thật phải thêm `src/jsonSupport/java` và dependencies phù hợp. Gradle có thể tạo variants như `jsonSupportApiElements` và `jsonSupportRuntimeElements`, với **capability riêng**.

Consumer có thể yêu cầu capability:

~~~kotlin
dependencies {
    runtimeOnly(project(":library")) {
        capabilities {
            requireCapability("org.example:library-json-support")
        }
    }
}
~~~

Ở đây capability coordinate **chỉ minh họa**; phải khớp group/module name/version và cấu hình feature thực của project. Với feature mặc định, Gradle thường dùng tên main module + hậu tố theo kebab-case feature name.

**Phân biệt:**

| Cơ chế | Mục tiêu |
| --- | --- |
| Custom ZIP debug/release variants | Chọn **một loại artifact** theo attribute `demo.bundle.mode` |
| Java `apiElements`/`runtimeElements` | Chọn variant của cùng Java library theo usage compile/runtime |
| Java feature variant | Yêu cầu **tính năng bổ sung** cùng library, thường qua capability |
| Artifact transform | Biến artifact từ loại này sang loại khác theo attribute (ví dụ JAR → processed JAR) |
| Classifier dependency | Yêu cầu file gắn classifier cố định, ít semantics hơn variant-aware matching |

**Capability** không đồng nghĩa attribute. Capability biểu diễn “module/feature này cung cấp chức năng gì” và có thể phát hiện conflicts giữa các implementations; attribute biểu diễn **đặc tính** của variant mà consumer mong muốn. Một dependency có thể cần cả hai.

### Publish feature variants

Nếu dùng `maven-publish` và `from(components["java"])`, Gradle Module Metadata giữ feature variants/capabilities rõ hơn Maven POM. Maven-only consumers thường nhận metadata “lossy” hơn, nên cần kiểm tra khả năng tương thích khi dùng library bên ngoài multi-project build.

## 15. Artifact transform và `ArtifactView`: khi nào cần?

Một use case khác: producer chỉ cung cấp JAR thông thường, consumer cần **instrumented JAR** hoặc giải nén ZIP theo quy tắc. Có thể chọn:

- Producer thực sự tạo một outgoing variant mới và đăng ký artifact của task, như trong demo.
- Hoặc dùng **artifact transform** để Gradle biến đầu vào có attribute A thành output có attribute B, với cache/incremental semantics của transform phù hợp.
- Consumer có thể dùng **ArtifactView** để yêu cầu artifacts theo attributes bổ sung mà không phải ép mọi file dependencies có cùng hình thức.

**Khi nào nên dùng variant producer?** Khi producer là bên có hiểu biết và chịu trách nhiệm về artifact đặc thù, ví dụ debug/release ZIP do chính producer tạo.

**Khi nào dùng transform?** Khi quá trình chuyển đổi mang tính general-purpose cho nhiều dependencies, ví dụ một transform chuẩn hóa JARs hoặc xử lý artifact thành dạng khác dựa trên input type. Artifact transform cần được đăng ký với from/to attributes và action implementation đúng Gradle API; nó **không phải** thay thế cho mọi custom task.

Một `ArtifactView` giúp chọn/lọc artifact files theo attributes hoặc component filters, nhưng vẫn phải hiểu parent resolvable configuration và Gradle variant matching. Đừng giải quyết một lỗi thiếu artifact bằng cách gọi `zipTree` trực tiếp lên một path trong producer.

## 16. Task outputs, Gradle dependency graph và caching

Một artifact được tiêu thụ có hai lớp quan trọng:

1. **Danh tính/variant contract**: Gradle biết consumer muốn loại artifact nào.
2. **Task provenance**: Gradle biết file đó được tạo bởi task nào.

Trong demo, `Zip` task có inputs `src/bundles/debug` hoặc `src/bundles/release` và archive output do task quản lý. `artifacts.add("...", taskProvider)` gắn output với consumable variant. `Sync.from(selectedBundle)` sử dụng file collection chứa dependency provenance.

Lợi ích:

- Không cần hard-code cross-project task names.
- Chạy consumer task có thể build producer artifact đúng lúc.
- Gradle xác định task order dựa trên dependency graph.
- Up-to-date checks theo task inputs/outputs giúp tránh chạy lại khi không cần.
- Khi attribute đổi debug → release, dependency graph trỏ đúng producer task mới.
- Có thể cải thiện Configuration Cache/parallelism so với truy cập model project khác trong task actions.

**Không suy rằng mọi custom task tự cacheable chỉ vì nó có outputs.** Task type, inputs/outputs, determinism và Gradle Build Cache config quyết định cacheability. `Zip`/`Sync` có tracking semantics tiêu chuẩn; custom task dùng `doLast` với file paths ngầm có thể cần khai báo `@InputFiles`/`@OutputFile` để Gradle quản lý đúng.

### Nguy cơ truy cập artifact quá sớm

Nếu tại configuration time bạn gọi `selectedBundle.get().files` và xử lý file đó bằng Java File API trước khi task producer chạy, file có thể không tồn tại hoặc Gradle resolve dependency graph quá sớm. Hãy truyền Provider/FileCollection tới task và xử lý khi task được thực thi.

## 17. Khi cần chia sẻ directory thay vì ZIP

Một task codegen có thể tạo:

~~~text
producer/build/generated/schema/
    schema.json
    manifest.txt
~~~

Có thể xuất bản directory dưới một consumable configuration thông qua artifact có `builtBy` hoặc Gradle task output provider hợp lệ. Consumer nên yêu cầu artifact theo attributes mô tả **directory type** và gắn vào `Copy`/`Sync`/custom task input.

Những điều cần quyết định:

- Artifact contract là **directory** hay archive file?
- Có nhiều files trong directory và có cần preserve relative paths?
- Generated files có deterministic và không ghi ngoài output root không?
- Task producing directory đã khai báo outputs rõ chưa?
- Gradle consumer có cần build artifact **khi không có source code** như một task báo cáo?

Đối với bài học chạy được, ZIP là một dạng artifact rõ ràng và ổn định hơn cho việc minh họa tệp được trao đổi. Không tự copy directory từ project khác bằng `file("../producer/build/generated")` rồi gọi `dependsOn` thủ công.

## 18. Configuration inheritance bằng `extendsFrom`

Ở consumer, demo dùng:

~~~kotlin
val bundleDependencies =
    configurations.dependencyScope("bundleDependencies")

val selectedBundle = configurations.resolvable("selectedBundle") {
    extendsFrom(bundleDependencies.get())
}
~~~

`extendsFrom` nghĩa selectedBundle có thể kế thừa dependency declarations, constraints, exclude rules/artifacts/capabilities phù hợp từ bucket. Nó **không** làm thay đổi flags vai trò của configuration và **không kế thừa attributes**.

Nếu dùng:

~~~kotlin
dependencies {
    add("bundleDependencies", project(":producer"))
}
~~~

thì dependency nằm ở declarable bucket, consumer resolution thông qua `selectedBundle`. Không cần khai báo cùng dependency một lần nữa ở selectedBundle.

**Chỉ extendsFrom các configurations thuộc cùng project.** Đừng tìm cách `extendsFrom(project(":producer").configurations["..."])`. Khi cần trao đổi giữa projects, dùng **project dependency**, không dùng configuration inheritance xuyên project.

## 19. Attribute contract là public interface của build logic

Một custom attribute như:

~~~text
demo.bundle.mode
  type: java.lang.String
  allowed: debug | release
~~~

là **hợp đồng sử dụng artifact**. Nếu team thay `debug` thành `development` một cách im lặng, consumer build đã biết attribute cũ có thể fail. Cách quản lý tốt:

- Đặt tên thuộc namespace ổn định, tránh conflict với Gradle/third-party plugin attributes.
- Văn bản hóa value set, kiểu dữ liệu, ý nghĩa artifact và compatibilities.
- Giữ các variants có semantics độc lập; không dùng `release` để chỉ bất kỳ ZIP nào tiện nhất.
- Nếu cần deprecate variant, có migration path hoặc compatibility rule có kiểm soát.
- Tách cấu hình người dùng (`-PbundleMode`) khỏi attribute contract bằng normalization/validation khi phù hợp.
- Với nhiều projects dùng chung contract, đưa attribute definition vào **convention plugin** hoặc build logic library thay vì copy tên string lung tung.

**Lưu ý:** ví dụ viết Attribute.of hai lần ở producer và consumer để bài học tự chạy với hai scripts riêng. Trong monorepo lớn, nên dùng một plugin/build-logic shared API để giảm typo/kiểu sai.

## 20. Chẩn đoán: `No matching variant`

Một lỗi quen thuộc:

~~~text
No matching variant of project :producer was found.
The consumer was configured to find ...
~~~

Đó là **dạng thông báo minh họa**, không hứa từng dòng của Gradle logs. Khi gặp lỗi, kiểm tra:

1. Producer có consumable configuration không?
2. Configuration đã gắn artifact chưa?
3. Producer có attributes nào? Dùng `:producer:outgoingVariants --all`.
4. Consumer yêu cầu attributes nào? Dùng `:consumer:resolvableConfigurations --configuration selectedBundle`.
5. Attribute key có **cùng tên và kiểu** ở producer/consumer không?
6. Giá trị `debug`, `release` có viết đúng, kể cả chữ hoa/thường không?
7. Consumer có đang yêu cầu Java runtime usage trong khi producer chỉ cung cấp ZIP data variant không?
8. Có multiple compatible variants khiến resolver không phân biệt được không?
9. Có capability yêu cầu sai hoặc conflict capability với dependency khác không?
10. Với external modules, Gradle Module Metadata/POM của artifact có thực sự công bố variant đó không?

Không sửa bằng cách chọn bừa `targetConfiguration` hoặc hard-code output path mà chưa hiểu attribute mismatch.

## 21. Chẩn đoán: artifact không được tạo trước consumer task

Nếu consumer báo không tìm được file mà đáng ra producer tạo:

- Đã gắn **task provider** hoặc output provider có `builtBy` vào outgoing artifact chưa?
- Có lỡ viết `artifacts.add("debugBundleElements", file("build/bundles/..."))` thay vì publish task output khiến Gradle không biết task producing file?
- `Sync.from(selectedBundle)` có dùng configuration đúng, hay chỉ đọc string path?
- Producer ZIP task có đúng inputs và output directory không?
- Task bị `SKIPPED`/`NO-SOURCE` vì source directory rỗng hoặc sai path không?
- `receiveBundle` được chạy trực tiếp hay `run` không có dependency đến receiveBundle?
- Có thay đổi filename classifier/version nhưng consumer vẫn tìm fixed name không?

Trong demo, producer Zip task dùng `archiveBaseName`, `archiveVersion=""`, `archiveClassifier` và `destinationDirectory` rõ ràng; consumer không quan tâm đến tên này vì Gradle resolve artifact. Java demo có thể xác định ZIP bằng liệt kê folder after Sync và yêu cầu đúng một file.

## 22. Chẩn đoán: chỉ “có configuration” nhưng không resolve được

Một configuration có tên `bundleDependencies` là **declarable bucket**, không được dùng như file collection task input để resolve. Một configuration `debugBundleElements` là **consumable outgoing**, không được consumer đọc trực tiếp bằng cách resolve nó trong producer.

Khi muốn lấy artifacts, phải có **resolvable configuration** ở consumer:

~~~kotlin
val selectedBundle = configurations.resolvable("selectedBundle") {
    extendsFrom(bundleDependencies.get())
    attributes {
        attribute(bundleModeAttribute, requestedMode.get())
    }
}
~~~

Dùng rõ ba vai trò tránh lỗi Gradle kiểu:

~~~text
Resolving dependency configuration 'implementation' is not allowed.
~~~

hoặc những cảnh báo về resolution trên configuration không được dùng cho mục đích đó. Dòng trên là **dạng lỗi minh họa**, không phải output được chạy trong demo.

## 23. Không nhầm variant với Gradle project selection

Một multi-project build có thể có:

~~~text
:library
:service
:ui
~~~

Đó là **project paths**. Mỗi project có thể có nhiều **variants**:

~~~text
:library
    apiElements
    runtimeElements
    debugInstrumentedElements (nếu tự tạo)
~~~

Consumer dependency:

~~~kotlin
implementation(project(":library"))
~~~

chọn **project component**; Gradle vẫn phải chọn **variant phù hợp** từ project đó theo consumer attributes. Lệnh:

~~~bash
./gradlew :library:outgoingVariants
~~~

giúp thấy lựa chọn. `project(":library")` không đồng nghĩa “lấy tệp JAR ở build/libs/ tùy ý” và cũng không tự buộc Gradle chọn `runtimeElements` trong mọi context.

## 24. Artifact exchange so với Maven Publish

Demo trao đổi ZIP **trong cùng một multi-project build**:

~~~text
project dependency -> consumer resolves producer outgoing variant
~~~

Không cần Maven repository, GAV hay `maven-publish`. Gradle thấy producer và consumer trong cùng settings build và chọn variant trực tiếp.

Nếu muốn dự án **khác repository/build** tiêu thụ artifact, cần xuất bản module qua một repository/metadata format phù hợp:

- `maven-publish` có thể publish SoftwareComponent/JAR variants nếu được mô hình hóa vào publication.
- Gradle Module Metadata lưu variants/capabilities tốt hơn Maven POM.
- Một **ad-hoc consumable configuration** không tự biến thành Maven published variant chỉ vì nó tồn tại trong project. Phải tích hợp đúng vào publishable SoftwareComponent hoặc tạo publication/artifact logic phù hợp.
- Với Java feature variants, Gradle Java plugin hỗ trợ đăng ký feature và công bố chúng qua `components["java"]` khi dùng publishing plugin.

Không nói “đã tạo `configurations.consumable` là Maven Central tự thấy ZIP”. **Trong cùng build** và **giữa builds qua repository** là hai cơ chế phân phối khác nhau.

## 25. Bảng lựa chọn API theo mục tiêu

| Nhu cầu | Cơ chế nên ưu tiên |
| --- | --- |
| Java project `:app` dùng code của `:library` | `implementation(project(":library"))`, Java plugin variants |
| Consumer cần ZIP/report/codegen artifact đặc thù từ producer | Custom consumable variant + resolvable configuration + attributes |
| Có nhiều ZIP debug/release | Hai variants với `demo.bundle.mode` attributes |
| Nhiều projects chia sẻ attribute definitions | Convention plugin / build logic chung |
| Java library có feature tùy chọn | `java.registerFeature` + capabilities/feature variants |
| File có thể tự sinh từ artifact chung bằng một phép biến đổi | Artifact transform |
| Consumer chỉ cần copy artifact đầu vào | `Copy`/`Sync` từ resolved configuration, không hard-code file |
| Consumer chạy app dựa vào file đã copy | Task dependency cùng project giữa `run` và `receiveBundle` |
| Cần đóng gói public release cho người ngoài build | Publishing plugin + publishable component + metadata |
| Cần xem producer mang những gì | `outgoingVariants` |
| Cần xem consumer đòi hỏi những gì | `resolvableConfigurations` |
| Cần xem dependency graph | `dependencies` và `dependencyInsight` |

## 26. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** `implementation`, `runtimeClasspath` và `runtimeElements` tương ứng ba vai trò nào?

**Đáp:** Declarable, resolvable và consumable. Java plugin quản lý chúng; không nên resolve `implementation` trực tiếp.

**Câu 2.** Tại sao `from("../producer/build/output.zip")` ở consumer là anti-pattern?

**Đáp:** Nó hard-code producer layout, không tự giữ task dependency provenance và tạo coupling; clean build có thể thiếu file.

**Câu 3.** Producer có variants `mode=debug` và `mode=release`. Consumer yêu cầu `mode=debug` thì Gradle chọn thế nào?

**Đáp:** Resolver đối chiếu attributes và chọn outgoing variant debug tương thích; không dựa vào tên task producer.

**Câu 4.** Vì sao `artifacts.add("debugBundleElements", debugZip)` tốt hơn thêm một string filename?

**Đáp:** `debugZip` là TaskProvider, Gradle có thể liên kết file output với task producing nó và xây dependency graph chính xác.

**Câu 5.** `selectedBundle` có thể được cấu hình vừa `canBeResolved=true` vừa `canBeConsumed=true` cho tiện không?

**Đáp:** Không nên. Configuration hiện đại nên có một vai trò rõ ràng. Producer consumable, consumer resolvable; dependency declarations ở bucket riêng.

**Câu 6.** Nếu chạy release sau debug và dùng `Copy`, chuyện gì có thể xảy ra?

**Đáp:** ZIP debug cũ có thể còn trong destination. `Sync` giúp giữ destination khớp chính xác selected artifacts.

**Câu 7.** `extendsFrom` có tự kế thừa attributes từ parent configuration không?

**Đáp:** Không. Nó truyền dependency declarations/constraints và một số thông tin liên quan, nhưng không truyền attributes hay role flags.

**Câu 8.** Consumer có thể lấy cấu hình của producer bằng `project(":producer").configurations[...]` rồi resolve trong task action không?

**Đáp:** Không nên. Đây là unsafe cross-project access theo Gradle; dùng project dependency + resolver của chính consumer.

**Câu 9.** Debug và release ZIP có cần xuất bản lên Maven repo trong demo không?

**Đáp:** Không. Đây là cross-project artifact exchange trong cùng build; consumer dùng `project(":producer")` trực tiếp.

**Câu 10.** Nếu muốn external consumer biết feature variants, chỉ tạo `consumable` config là đủ chưa?

**Đáp:** Chưa. Phải tích hợp variant vào publishable component và xuất bản metadata phù hợp; Gradle Module Metadata biểu đạt giàu hơn Maven POM.

**Câu 11.** Khi `mode=staging` không có producer variant, có nên tự dùng release ZIP path để khỏi lỗi không?

**Đáp:** Không. Cần fail rõ hoặc định nghĩa compatibility/normalization policy có tài liệu và tests.

**Câu 12.** `maxParallelForks` hay `--parallel` có thay cho variant matching không?

**Đáp:** Không. Chúng liên quan scheduling/parallel test or tasks, còn variant matching chọn **artifact đúng contract**.

**Câu 13.** Feature variant dùng capability khác attribute thế nào?

**Đáp:** Capability biểu diễn chức năng của component và giúp detect conflicts/optional features; attribute biểu diễn đặc tính một variant để match consumer request.

**Câu 14.** Nếu consumer cần `runtimeElements` của `:library`, có nên chỉ tên đó trực tiếp không?

**Đáp:** Thông thường không. Java plugin đã cấu hình `runtimeClasspath` attributes; dùng project dependency và để Gradle chọn variant tự động.

## 27. Checklist review một cross-project artifact contract

- [ ] Producer và consumer thuộc đúng settings build; `include("producer", "consumer")` hợp lệ.
- [ ] Producer có task tạo artifact với inputs/outputs được mô hình rõ.
- [ ] Outgoing artifact gắn vào consumable configuration bằng task/output provider có provenance.
- [ ] Consumable configuration không được dùng làm nơi resolve dependencies.
- [ ] Dependency declarations ở declarable bucket, resolution ở resolvable config.
- [ ] Attributes được định nghĩa cùng name/type và giá trị hợp lệ tại producer/consumer.
- [ ] Không dùng hard-coded path `../producer/build/...` ở consumer.
- [ ] Không lấy `Project.configurations` của project khác rồi resolve bằng tay.
- [ ] Không gọi `dependsOn` task của producer nếu artifact dependency đã đủ.
- [ ] Consumer task nhận FileCollection/Provider để Gradle bảo toàn task graph.
- [ ] Nếu chuyển variant trong cùng output directory, dùng `Sync` hoặc cleanup rõ ràng.
- [ ] Có diagnostics `outgoingVariants`, `resolvableConfigurations`, dependency graph.
- [ ] Có negative test cho variant thiếu hoặc không tương thích.
- [ ] Không tự gắn Java usage/category attributes cho ZIP không phải Java library.
- [ ] Biết khi nào dùng Java component chuẩn thay custom variant.
- [ ] Biết phân biệt project dependency và xuất bản ra Maven/Gradle metadata.
- [ ] Chạy clean build và consumer test với ít nhất hai attribute values.

## 28. Tài liệu chính thức

- [Gradle — How to Share Artifacts Between Projects](https://docs.gradle.org/current/userguide/how_to_share_outputs_between_projects.html): producer consumable variants, consumer declarable/resolvable configurations, attributes, task output artifacts.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): ba roles declarable/resolvable/consumable, factory APIs, `extendsFrom` và unsafe resolution.
- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): variant-aware resolution, compatibility/disambiguation và diagnostics.
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html): standard/custom attributes, compatibility rules, matching.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): luôn công bố attributes, tránh chỉ configuration names và unsafe patterns.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): `project(":...")` dependencies và task order.
- [Gradle — Creating Feature Variants](https://docs.gradle.org/current/userguide/how_to_create_feature_variants_of_a_library.html): Java feature variants, capabilities và metadata publishing.
- [Gradle — Artifact Resolution](https://docs.gradle.org/current/userguide/artifact_resolution.html): resolvable configurations, artifacts và Gradle API.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): metadata cho variants/capabilities khi xuất bản artifacts ngoài build.
