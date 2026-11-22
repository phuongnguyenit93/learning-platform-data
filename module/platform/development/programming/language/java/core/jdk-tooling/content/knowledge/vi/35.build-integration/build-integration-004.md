# Source set trong Gradle

**Source set** là một nhóm logic gồm source files và resources được Gradle xử lý như một đơn vị build. Với Java, một source set xác định thư mục chứa mã nguồn và tài nguyên, classpath dùng để biên dịch, classpath dùng khi chạy, cùng các thư mục output chứa class đã biên dịch và resources đã xử lý.

Source set giúp tách những phần mã có mục đích hoặc dependency khác nhau. Một dự án Java thường có source set `main` cho code production và `test` cho unit test. Khi cần integration test, generated code, benchmark hoặc một nhóm source độc lập có classpath riêng, có thể tạo thêm source set như `integrationTest`, `benchmark` hoặc `codegen`.

Trong Gradle, source set không chỉ là tên thư mục. Khi Java Plugin tạo một source set, Gradle còn tạo các configuration dependency và task biên dịch/xử lý resources tương ứng. Nhờ đó, cùng một project có thể biên dịch nhiều nhóm source với classpath và output tách biệt.

## 1. Source set giải quyết vấn đề gì?

Một dự án Java thường chứa nhiều loại mã nguồn:

- Mã ứng dụng hoặc thư viện được đóng gói để phát hành.
- Unit test chạy nhanh, thường kiểm tra một class hoặc một nhóm nhỏ class.
- Integration test cần kết nối database, HTTP service, message broker hoặc nhiều thành phần cùng lúc.
- Functional test hoặc acceptance test chạy theo kịch bản ở mức hệ thống.
- Benchmark cần dependency và cách chạy riêng.
- Source được sinh ra từ schema, protocol definition hoặc annotation processor.
- Mã hỗ trợ build hoặc công cụ nội bộ không nên đi vào artifact production.

Nếu gom tất cả vào `src/main/java`, dependency test có thể lọt vào classpath production, code test có thể bị đóng gói vào JAR và build khó kiểm soát. Nếu chỉ tạo nhiều thư mục tùy ý mà không khai báo với Gradle, compiler có thể không nhìn thấy các file đó.

Source set tạo ranh giới rõ ràng giữa các nhóm source. Mỗi nhóm có thể có source roots, resource roots, dependency configurations, compile task và output riêng.

## 2. Source set gồm những thành phần nào?

Một Java source set có các thành phần chính:

| Thành phần | Ý nghĩa |
|---|---|
| `java` | Các Java source file được biên dịch |
| `resources` | Resource file được copy/xử lý vào output |
| `allJava` | Tập hợp Java source của source set |
| `allSource` | Tập hợp source và resources |
| `compileClasspath` | Classpath dùng khi biên dịch |
| `runtimeClasspath` | Classpath dùng khi chạy |
| `output` | Các output directory, gồm class đã biên dịch và resources đã xử lý |
| `name` | Tên source set |

Ví dụ một source set tên `integrationTest` có thể có:

- Source root: `src/integrationTest/java`.
- Resource root: `src/integrationTest/resources`.
- Compile classpath: output của `main` và dependency dành cho integration test.
- Runtime classpath: class đã biên dịch, resources và dependency cần khi chạy integration test.
- Output: class và resources riêng trong thư mục `build`.

Source và resource của một source set có thể nằm ở nhiều thư mục khác nhau. Không bắt buộc tất cả file phải cùng một root.

## 3. Source set mặc định của Java Plugin

Khi áp dụng Java Plugin hoặc Application Plugin, Gradle tạo sẵn hai source set:

| Source set | Vai trò | Source mặc định | Resource mặc định |
|---|---|---|---|
| `main` | Mã production | `src/main/java` | `src/main/resources` |
| `test` | Mã test | `src/test/java` | `src/test/resources` |

Cấu trúc dự án thường dùng:

```text
source-set-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   ├── java/
    │   └── resources/
    └── test/
        ├── java/
        └── resources/
```

`main` là source set đặc biệt: Gradle rút gọn tên task và configuration, nên dùng `compileJava`, `processResources`, `classes`, `implementation` và `runtimeOnly` thay vì `compileMainJava`, `processMainResources` hoặc `mainImplementation`.

`test` có các task và configuration riêng như `compileTestJava`, `processTestResources`, `testClasses`, `testImplementation` và `testRuntimeOnly`.

Java Plugin tự nối task `test` vào lifecycle task `check`. Task `jar` đóng gói output của `main`, không tự động đưa source hoặc class của mọi source set khác vào JAR production.

## 4. Task được tạo cho mỗi source set

Khi tạo source set tùy chỉnh tên `integrationTest`, Java Plugin tạo các task theo tên source set:

| Task | Mục đích |
|---|---|
| `compileIntegrationTestJava` | Biên dịch Java source của source set |
| `processIntegrationTestResources` | Copy/xử lý resources |
| `integrationTestClasses` | Chuẩn bị class và resource output |
| `integrationTestImplementation` | Configuration khai báo dependency compile/runtime |
| `integrationTestCompileOnly` | Dependency chỉ cần lúc biên dịch |
| `integrationTestRuntimeOnly` | Dependency chỉ cần lúc chạy |
| `integrationTestAnnotationProcessor` | Annotation processor cho source set |

Tên task biên dịch tuân theo mẫu `compileSourceSetJava`; tên task xử lý resource là `processSourceSetResources`; task gom class và resource là `sourceSetClasses`.

Source set tự tạo task biên dịch và các dependency configuration, nhưng **không tự tạo một task kiểu Test để thực thi test case**. Nếu source set chứa integration test, cần đăng ký một `Test` task và gán đúng test class directories cùng runtime classpath.

## 5. Compile classpath và runtime classpath

Hai classpath có mục đích khác nhau:

**Compile classpath**

Chứa những class và dependency mà compiler cần để kiểm tra type, method và symbol khi biên dịch source. Ví dụ, integration test cần nhìn thấy class production để gọi API của ứng dụng.

**Runtime classpath**

Chứa class và dependency cần có khi JVM thực thi chương trình hoặc test. Nó thường gồm output của source set cùng các dependency runtime.

Source set `main` có compile classpath dựa trên các configuration production. Source set `test` có compile/runtime classpath riêng, được cấu hình để test có thể dùng output production và dependency test.

Với source set tùy chỉnh, nếu test cần gọi class từ `main`, cần thêm `sourceSets.main.output` vào compile classpath và runtime classpath của source set đó. Nếu thiếu phần này, integration test có thể báo lỗi không tìm thấy class production khi biên dịch hoặc chạy.

Không ghi đè toàn bộ classpath mặc định nếu chỉ cần bổ sung một phần. Dùng `+=` để thêm output hoặc file collection vào classpath có sẵn.

## 6. Dependency configurations theo source set

Java Plugin tạo các configuration theo tên source set. Với `integrationTest`, một số configuration quan trọng là:

| Configuration | Dùng khi |
|---|---|
| `integrationTestImplementation` | Dependency cần cho compile và runtime của integration test |
| `integrationTestCompileOnly` | Dependency chỉ cần để compile |
| `integrationTestRuntimeOnly` | Dependency chỉ cần khi chạy test |
| `integrationTestAnnotationProcessor` | Annotation processor chạy khi compile source set |
| `integrationTestCompileClasspath` | Classpath đã resolve cho compiler |
| `integrationTestRuntimeClasspath` | Classpath đã resolve để thực thi |

Với source set `main`, các configuration thường gặp là `implementation`, `compileOnly`, `runtimeOnly` và `annotationProcessor`. Với `test`, các configuration thường gặp là `testImplementation`, `testCompileOnly`, `testRuntimeOnly` và `testAnnotationProcessor`.

Cần phân biệt configuration dùng để khai báo dependency với classpath đã resolve để task sử dụng. Ví dụ `integrationTestImplementation` là nơi khai báo dependency; `integrationTestCompileClasspath` là tập file được dùng khi compiler chạy.

Nếu integration test cần cùng dependency của production và test framework, có thể cấu hình `integrationTestImplementation` kế thừa từ `implementation` và `testImplementation`; `integrationTestRuntimeOnly` có thể kế thừa từ `runtimeOnly` và `testRuntimeOnly`.

Hãy tạo source set trước khi truy cập các configuration do source set sinh ra. Gradle tự tạo các configuration này; không tự tạo một configuration cùng tên với vai trò khác.

## 7. Tạo source set tùy chỉnh bằng Kotlin DSL

Ví dụ tạo source set `integrationTest`:

```kotlin
plugins {
    java
}

sourceSets {
    create("integrationTest") {
        compileClasspath += sourceSets.main.get().output
        runtimeClasspath += sourceSets.main.get().output
    }
}
```

Đoạn cấu hình này:

1. Tạo source set có tên `integrationTest`.
2. Gradle mặc định tìm Java source trong `src/integrationTest/java`.
3. Gradle mặc định tìm resources trong `src/integrationTest/resources`.
4. Thêm output của `main` vào compile classpath và runtime classpath.
5. Tạo các task compile/resource/classes và dependency configuration tương ứng.

Có thể truy cập source set sau khi tạo:

```kotlin
val integrationSources = sourceSets["integrationTest"]

println(integrationSources.name)
println(integrationSources.java.srcDirs)
println(integrationSources.resources.srcDirs)
```

Không cần khai báo thủ công `compileIntegrationTestJava` hoặc `processIntegrationTestResources`; Java Plugin tạo các task đó dựa trên source set.

## 8. Tạo source set tùy chỉnh bằng Groovy DSL

Nếu dự án dùng `build.gradle`, cấu hình tương đương là:

```groovy
plugins {
    id 'java'
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}
```

Gradle tạo các task và configuration theo cùng quy ước. Điểm khác biệt chính là cú pháp DSL; mô hình SourceSet và task graph không thay đổi.

Không trộn cú pháp Kotlin DSL và Groovy DSL trong cùng một build script. Tên file quyết định DSL: `build.gradle.kts` dùng Kotlin DSL, còn `build.gradle` dùng Groovy DSL.

## 9. Thêm dependency cho source set tùy chỉnh

Sau khi tạo source set, có thể khai báo dependency cho nó:

```kotlin
configurations["integrationTestImplementation"].extendsFrom(
    configurations["implementation"],
    configurations["testImplementation"]
)

configurations["integrationTestRuntimeOnly"].extendsFrom(
    configurations["runtimeOnly"],
    configurations["testRuntimeOnly"]
)

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.12.2")
}
```

Trong ví dụ:

- `integrationTestImplementation` kế thừa dependency production và test framework.
- `integrationTestRuntimeOnly` kế thừa dependency runtime của production và test.
- JUnit Jupiter API/engine được dùng cho test source.
- JUnit Platform launcher được thêm vào runtime của test.

Khai báo dependency sau khi source set đã được tạo để các configuration `integrationTestImplementation` và `integrationTestRuntimeOnly` tồn tại.

Không nhất thiết phải cho integration test kế thừa toàn bộ dependency của unit test. Nếu integration test dùng framework hoặc client riêng, hãy khai báo đúng dependency cần thiết cho source set đó.

## 10. Tạo task chạy integration test

Source set chỉ mô tả source, classpath và output. Để chạy các class test, tạo một task kiểu `Test`:

```kotlin
val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = sourceSets["integrationTest"].output.classesDirs
    classpath = sourceSets["integrationTest"].runtimeClasspath

    shouldRunAfter("test")
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(integrationTest)
}
```

Hai thuộc tính quan trọng:

- `testClassesDirs`: thư mục chứa class test đã biên dịch.
- `classpath`: classpath dùng khi chạy test, bao gồm class test, output production và các dependency runtime.

`shouldRunAfter("test")` yêu cầu integration test chạy sau unit test khi cả hai task được chọn. Đây là ràng buộc thứ tự mềm; Gradle vẫn có quyền tối ưu task graph và thực thi song song khi phù hợp.

`dependsOn(integrationTest)` gắn integration test vào lifecycle `check`. Nhờ đó, lệnh `./gradlew check` sẽ chạy cả unit test và integration test.

Nếu không gắn task vào `check`, lệnh `check` mặc định không biết cần chạy task integration test mới tạo.

## 11. Ví dụ hoàn chỉnh Java 17+ với main, test và integrationTest

Ví dụ này dùng Gradle Kotlin DSL, Java 17 toolchain và JUnit 5. Dự án có source set `main`, `test` mặc định và `integrationTest` tùy chỉnh.

Cấu trúc thư mục:

```text
source-set-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/App.java
    ├── test/
    │   └── java/
    │       └── com/example/AppTest.java
    └── integrationTest/
        └── java/
            └── com/example/AppIntegrationTest.java
```

File `settings.gradle.kts`:

```kotlin
rootProject.name = "source-set-demo"
```

File `build.gradle.kts`:

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("com.example.App")
}

sourceSets {
    create("integrationTest") {
        compileClasspath += sourceSets.main.get().output
        runtimeClasspath += sourceSets.main.get().output
    }
}

configurations["integrationTestImplementation"].extendsFrom(
    configurations["implementation"],
    configurations["testImplementation"]
)

configurations["integrationTestRuntimeOnly"].extendsFrom(
    configurations["runtimeOnly"],
    configurations["testRuntimeOnly"]
)

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.12.2")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = sourceSets["integrationTest"].output.classesDirs
    classpath = sourceSets["integrationTest"].runtimeClasspath

    shouldRunAfter("test")
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(integrationTest)
}
```

File `src/main/java/com/example/App.java`:

```java
package com.example;

public final class App {
    private App() {
    }

    public static String message() {
        return "source-set-demo";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

File `src/test/java/com/example/AppTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsApplicationMessage() {
        assertEquals("source-set-demo", App.message());
    }
}
```

File `src/integrationTest/java/com/example/AppIntegrationTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIntegrationTest {
    @Test
    void integrationTestCanUseProductionClasses() {
        assertEquals("source-set-demo", App.message());
    }
}
```

### Tạo Gradle Wrapper và chạy project

Nếu project chưa có wrapper, dùng Gradle đã cài để tạo wrapper:

```sh
gradle wrapper --gradle-version 9.9.0
```

Sau đó chạy ứng dụng:

Linux/macOS:

```sh
./gradlew run
```

Windows:

```powershell
.\gradlew.bat run
```

Stdout của ứng dụng:

```text
source-set-demo
```

Chạy unit test và integration test:

```sh
./gradlew clean test integrationTest
```

Chạy toàn bộ verification lifecycle:

```sh
./gradlew check
```

`check` bao gồm `test` mặc định và `integrationTest` đã được gắn vào lifecycle. Bài test integration chứng minh source set riêng có thể biên dịch và chạy test với output production trên classpath.

Ví dụ test chỉ xác nhận wiring của source set và quyền truy cập class production. Một integration test thực tế thường kết nối database, HTTP service hoặc thành phần ngoài process và cần cấu hình môi trường riêng.

## 12. Thay đổi source directory và resource directory

Nếu dự án có layout khác quy ước, có thể thêm hoặc thay thế source roots.

Thêm một thư mục Java vào `main`:

```kotlin
sourceSets {
    main {
        java.srcDir("legacy-src")
        resources.srcDir("legacy-resources")
    }
}
```

`srcDir()` thêm một thư mục vào danh sách hiện tại. Cách này phù hợp khi cần giữ cả thư mục mặc định và thư mục legacy.

Thay thế toàn bộ danh sách source roots:

```kotlin
sourceSets {
    main {
        java.setSrcDirs(listOf("app/java", "shared/java"))
        resources.setSrcDirs(listOf("app/resources"))
    }
}
```

`setSrcDirs()` thay danh sách hiện có. Khi dùng nó, hãy thêm lại mọi thư mục mặc định mà dự án vẫn cần; nếu không, Gradle sẽ không còn quét các root đã bị thay thế.

Có thể cấu hình tương tự cho source set tùy chỉnh:

```kotlin
sourceSets {
    integrationTest {
        java.srcDir("src/it/java")
        resources.srcDir("src/it/resources")
    }
}
```

Không nên di chuyển source chỉ để làm build script ngắn hơn nếu layout chuẩn đã phù hợp. Quy ước `src/<sourceSet>/java` và `src/<sourceSet>/resources` giúp IDE, plugin và thành viên nhóm dễ hiểu dự án.

## 13. Lọc source bằng include và exclude

Source set hỗ trợ include/exclude pattern để điều chỉnh file nào được đưa vào compilation:

```kotlin
sourceSets {
    main {
        java {
            include("com/example/api/**")
            exclude("com/example/api/internal/**")
        }
    }
}
```

Pattern áp dụng lên đường dẫn tương đối của source root. Dùng include/exclude khi cần giữ layout hiện tại nhưng chỉ biên dịch một phần source.

Không dùng exclude để che lỗi package hoặc tổ chức source không rõ ràng. Nếu hai nhóm source có dependency hoặc lifecycle khác nhau, tạo source set riêng thường dễ bảo trì hơn.

## 14. Resources trong source set

Mỗi source set có resource roots riêng. Gradle copy/process resources vào output directory tương ứng và đưa output vào runtime classpath của source set.

Ví dụ:

```text
src/main/resources/app.properties
src/test/resources/test-data.json
src/integrationTest/resources/it-config.properties
```

Các file này được xử lý bởi:

- `processResources` cho `main`.
- `processTestResources` cho `test`.
- `processIntegrationTestResources` cho `integrationTest`.

Code chạy trong `main` có thể đọc resource bằng class loader:

```java
try (var input = App.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing app.properties");
    }
}
```

Resource của `integrationTest` chỉ nằm trên runtime classpath của source set/task tương ứng nếu đã cấu hình như ví dụ. Không mặc định coi resource test là resource production; `jar` chỉ đóng gói output `main` trừ khi build script được tùy chỉnh.

## 15. Generated sources và annotation processor

Generated source là mã Java được sinh trong quá trình build, ví dụ từ schema, OpenAPI, Protocol Buffers hoặc code generator nội bộ.

Nếu source được sinh ra là một phần của production code, hãy thêm output directory vào source set `main` và nối task sinh mã với compile task:

```kotlin
sourceSets {
    main {
        java.srcDir(layout.buildDirectory.dir(
            "generated/sources/schema/main/java"
        ))
    }
}

tasks.named("compileJava") {
    dependsOn("generateSchema")
}
```

Ví dụ giả định plugin hoặc build logic đã đăng ký task `generateSchema`. Nếu task chưa tồn tại, cần tạo hoặc áp dụng plugin cung cấp task đó.

Thư mục generated nên nằm dưới `build/` thay vì ghi đè source do developer quản lý. Gradle có thể xóa `build/` khi chạy `clean`; vì vậy không lưu mã nguồn viết tay ở đó.

Với annotation processor, khai báo processor ở configuration riêng:

```kotlin
dependencies {
    annotationProcessor("com.example:my-processor:1.0.0")
    testAnnotationProcessor("com.example:test-processor:1.0.0")
}
```

Source set tùy chỉnh có configuration annotation processor riêng, ví dụ `integrationTestAnnotationProcessor`. Chọn đúng configuration để processor chỉ chạy trong source set cần nó.

## 16. Source set và Java module system

Gradle SourceSet không đồng nghĩa với Java Platform Module System (JPMS).

- **Gradle source set** là nhóm source/resource và classpath/output phục vụ build.
- **Java module** là đơn vị module ở cấp ngôn ngữ/runtime, thường khai báo bằng `module-info.java`.
- **Gradle project/subproject** là một đơn vị trong project graph, có build script, dependency và artifact riêng.

Một source set có thể chứa `module-info.java`, nhưng việc tạo source set không tự tạo Java module mới. Nếu cần module boundary, `requires`, `exports` hoặc module path, phải cấu hình JPMS riêng.

Unit test trong source set `test` có thể chạy trên classpath truyền thống nếu không có `module-info.java` trong test source. Nếu cần kiểm tra module boundary hoặc white-box test, cần cấu hình module path/patch module phù hợp; đây là vấn đề khác với việc đặt source vào thư mục riêng.

## 17. Khi nào nên tạo custom source set?

Custom source set phù hợp khi nhóm source:

- Có lifecycle biên dịch hoặc thực thi riêng.
- Cần compile/runtime classpath khác với `main` hoặc `test`.
- Tạo class output được xử lý hoặc đóng gói khác.
- Là một phần tự nhiên của cùng project, ví dụ integration test cho production code.

Ví dụ phù hợp:

| Nhu cầu | Source set gợi ý |
|---|---|
| Production code | `main` |
| Unit test | `test` |
| Integration test có dependency riêng | `integrationTest` |
| Benchmark JMH | `benchmark` |
| Smoke test chạy sau deploy | `smokeTest` |
| Code generator tool có classpath riêng | `codegen` |

Không phải mọi thư mục đều cần một source set. Nếu chỉ cần thêm vài file Java vào cùng compilation, có thể thêm source directory vào source set hiện có. Nếu API và implementation cần phát hành thành artifact riêng hoặc có dependency graph riêng, cân nhắc tách thành Gradle subproject thay vì thêm source set.

## 18. Source set trong multi-project build

Gradle multi-project build gồm nhiều project/subproject, mỗi project có thể có các source set riêng.

Ví dụ:

```text
root/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/
└── core/
    ├── build.gradle.kts
    └── src/main/java/
```

`core` và `app` là hai Gradle project khác nhau. Mỗi project có `main` và `test` riêng nếu áp dụng Java Plugin.

Khai báo dependency project:

```kotlin
dependencies {
    implementation(project(":core"))
}
```

Dùng subproject khi cần ranh giới module, artifact, versioning, publication hoặc ownership riêng. Dùng source set khi các nhóm source thuộc cùng một project nhưng cần compile/runtime classpath hoặc task khác nhau.

Không tạo source set để thay thế dependency giữa các project. Source set không tự tạo project dependency và không xuất bản artifact độc lập.

## 19. Source set và Maven source directory

Gradle và Maven đều có quy ước source directory phổ biến:

| Mục đích | Gradle Java Plugin | Maven mặc định |
|---|---|---|
| Production Java | `src/main/java` | `src/main/java` |
| Production resources | `src/main/resources` | `src/main/resources` |
| Test Java | `src/test/java` | `src/test/java` |
| Test resources | `src/test/resources` | `src/test/resources` |
| Integration test riêng | Custom source set + `Test` task | Plugin/configuration bổ sung hoặc module riêng |

Trong Gradle, source set là một mô hình build có API: source roots, resource roots, compile/runtime classpath, output, dependency configurations và task được kết nối với nhau.

Trong Maven, các thư mục mặc định được quản lý bởi lifecycle/plugin. Khi cần thêm test source hoặc compilation khác, thường cần cấu hình plugin như build-helper-maven-plugin, maven-compiler-plugin, maven-surefire-plugin hoặc maven-failsafe-plugin. Maven profile không tự động tương đương với Gradle source set; profile chủ yếu điều chỉnh cấu hình build theo môi trường hoặc lựa chọn chạy.

Khi chuyển build từ Maven sang Gradle, hãy ánh xạ mục đích của từng nhóm source và dependency trước, rồi tạo source set/task tương ứng. Không chỉ sao chép tên thư mục mà bỏ qua classpath và lifecycle.

## 20. Kiểm tra source set và task graph

Các lệnh sau giúp xem Gradle đã nhận source set và task hay chưa:

Liệt kê task:

```sh
./gradlew tasks --all
```

Chạy riêng task compile:

```sh
./gradlew compileJava
./gradlew compileTestJava
./gradlew compileIntegrationTestJava
```

Xem dependency configuration:

```sh
./gradlew dependencies --configuration integrationTestRuntimeClasspath
```

Xem dependency cụ thể:

```sh
./gradlew dependencyInsight --dependency junit-jupiter --configuration integrationTestRuntimeClasspath
```

Xem task graph trước khi chạy:

```sh
./gradlew integrationTest --dry-run
```

Nếu task không xuất hiện, kiểm tra Java Plugin đã được áp dụng và source set được tạo trong build script. Nếu task có nhưng không tìm thấy class, kiểm tra source root và compile classpath. Nếu test không chạy, kiểm tra `testClassesDirs`, `classpath`, test framework và test naming/filter.

## 21. IDE và source set tùy chỉnh

IntelliJ IDEA và Eclipse đọc mô hình project từ Gradle. Sau khi thêm source set:

1. Reload/Refresh Gradle project.
2. Kiểm tra IDE đã nhận đúng source roots và dependencies.
3. Kiểm tra thư mục test tùy chỉnh được đánh dấu là test source nếu IDE chưa nhận diện tự động.
4. Chạy test bằng Gradle nếu IDE runner không dùng đúng classpath của custom source set.
5. Khi build script thay đổi, đồng bộ lại Gradle model trước khi kết luận IDE bị lỗi.

IDE có thể lưu metadata riêng trong workspace. Không sửa `.classpath` hoặc cấu hình module thủ công nếu Gradle là nguồn cấu hình chính và có thể sinh lại metadata.

## 22. Lỗi thường gặp khi cấu hình source set

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `compileIntegrationTestJava` không tìm thấy source | Source nằm sai root hoặc tên source set khác dự kiến | Kiểm tra `src/integrationTest/java` và `sourceSets` |
| Không resolve được class production trong integration test | Thiếu `sourceSets.main.output` trong classpath | Bổ sung main output vào compile và runtime classpath |
| Compile được nhưng chạy test thiếu dependency | Dependency chỉ có trên compile classpath | Khai báo dependency trong `integrationTestRuntimeOnly` hoặc `integrationTestImplementation` |
| Task `integrationTest` không xuất hiện | Chưa đăng ký `Test` task | Tạo `tasks.register<Test>("integrationTest")` |
| Task chạy nhưng không phát hiện test | `testClassesDirs` hoặc classpath chưa đúng, test không khớp framework | Gán output classes và runtime classpath của source set; kiểm tra JUnit/TestNG |
| `check` không chạy integration test | Custom test task chưa gắn vào lifecycle | Thêm `dependsOn(integrationTest)` cho `check` |
| JUnit class không tìm thấy khi compile | Dependency đặt ở configuration khác hoặc source set chưa tạo | Khai báo vào `integrationTestImplementation` sau khi tạo source set |
| Resource không có khi chạy | Resource nằm sai root hoặc không có trong runtime classpath | Kiểm tra `src/<sourceSet>/resources` và source set output |
| Generated class không tìm thấy | Compile chạy trước task sinh source | Thêm generated source directory và `dependsOn` generator |
| JAR chứa code test | Đã tùy chỉnh `jar` đưa nhầm output test vào archive | Chỉ đóng gói output production nếu artifact là production JAR |
| IDE không nhận thư mục test mới | Gradle model chưa refresh hoặc IDE chưa đánh dấu test root | Reload project và kiểm tra source root classification |
| Configuration không tồn tại | Truy cập trước khi tạo source set hoặc sai tên | Tạo source set trước rồi dùng configuration name theo convention |
| Dependency bị lặp hoặc thừa | Cho custom source set kế thừa quá nhiều configuration | Chỉ kế thừa dependency thực sự cần thiết |

## 23. Hiệu năng và tính bảo trì

Source set riêng có thể làm build rõ ràng hơn, nhưng mỗi source set mới cũng tạo thêm task và configuration. Quá nhiều source set nhỏ, trùng lặp có thể làm build script khó hiểu và tăng chi phí configuration.

Một số nguyên tắc:

- Giữ `main` và `test` theo convention mặc định.
- Chỉ tạo source set khi cần classpath, task hoặc lifecycle riêng.
- Dùng dependency configuration riêng để tránh dependency test lọt vào production.
- Không thêm generated source vào thư mục source viết tay.
- Để task generator khai báo input/output rõ ràng và nối đúng với compile task.
- Tránh ghi đè compile/runtime classpath khi chỉ cần bổ sung output.
- Gắn verification task vào `check` nếu build CI phải thực thi chúng.
- Dùng project dependency khi cần artifact/module boundary riêng.
- Giữ DSL thống nhất và đặt tên source set mô tả đúng mục đích.

Source set giúp Gradle hiểu phần nào cần compile, resource nào cần xử lý, dependency nào cần resolve và output nào được dùng khi chạy. Build script tốt làm rõ các quan hệ này thay vì chỉ liệt kê nhiều đường dẫn.

## 24. Checklist

- [ ] Đã phân biệt source set với source directory, Gradle project và Java module.
- [ ] Đã hiểu `main` và `test` mặc định của Java Plugin.
- [ ] Đã biết source set gồm Java source, resources, classpath và output.
- [ ] Đã hiểu compile classpath khác runtime classpath.
- [ ] Đã biết task `compileSourceSetJava`, `processSourceSetResources` và `sourceSetClasses`.
- [ ] Đã tạo custom source set trước khi khai báo dependency configuration của nó.
- [ ] Đã thêm `main.output` vào classpath khi custom test cần production classes.
- [ ] Đã khai báo dependency đúng `Implementation`, `CompileOnly`, `RuntimeOnly` và `AnnotationProcessor`.
- [ ] Đã tạo `Test` task riêng cho custom test source set.
- [ ] Đã gắn custom verification task vào `check` nếu cần chạy trong CI.
- [ ] Đã cấu hình generated source directory và dependency task sinh mã.
- [ ] Đã kiểm tra resources nằm trên đúng runtime classpath.
- [ ] Đã reload Gradle model trong IDE.
- [ ] Đã kiểm tra task graph và dependency configuration.
- [ ] Đã xác nhận JAR production chỉ chứa output dự kiến.

## 25. Tài liệu tham khảo

- Gradle User Manual — Building Java & JVM Projects, Source Sets: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle User Manual — Testing in Java & JVM Projects, Integration Tests: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle Java Plugin — Tasks and Dependency Configurations: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle DSL Reference — SourceSet: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html
- Gradle User Manual — Managing Dependencies of JVM Projects: https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html

Source set là mô hình Gradle dùng để nhóm source và resources cùng classpath, dependency và output tương ứng. Bắt đầu với `main` và `test`; chỉ tạo `integrationTest` hoặc source set khác khi cần compilation/runtime setup hay task lifecycle riêng. Khi cấu hình đúng classpath và nối task vào lifecycle, Gradle có thể build và kiểm thử từng nhóm source một cách độc lập, có thể lặp lại và dễ kiểm soát.