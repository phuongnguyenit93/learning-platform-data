# SourceSet, source directory, resources và classpath trong dự án Java với Gradle

## 1. Bài toán và mục tiêu

Một project Java không chỉ có các file `.java`. Nó còn có JSON, `.properties`, XML, template, dữ liệu test, các nguồn được tạo tự động và thư viện bên ngoài. Nếu Gradle không biết **nhóm file nào thuộc phần nào của project**, nó không thể cấu hình chính xác compiler, đóng gói JAR hoặc chạy tests.

Trong Gradle, **SourceSet** mô hình hóa một **nhóm nguồn và tài nguyên có cùng mục đích biên dịch/thực thi**. Với plugin `java` hoặc `application`, hai SourceSet mặc định là:

- **`main`:** mã và tài nguyên sản phẩm, thường được biên dịch thành classes và đóng gói vào JAR.
- **`test`:** mã và tài nguyên phục vụ kiểm thử, được biên dịch/chạy riêng; thông thường không được đóng gói vào JAR sản phẩm.

Từ một SourceSet, Gradle biết **tìm source ở đâu**, **tài nguyên cần copy từ đâu**, **output biên dịch ở đâu**, **compile classpath khác runtime classpath thế nào** và **cần tạo những tasks/configurations nào**.

**Sau bài học bạn có thể:**

1. Giải thích SourceSet, SourceDirectorySet, SourceSetOutput và FileCollection.
2. Nhận diện cây thư mục chuẩn `src/main/java`, `src/main/resources`, `src/test/java`, `src/test/resources`.
3. Phân biệt `java.srcDir(...)` (thêm) với `java.srcDirs = [...]` (thay thế), cũng như cơ chế tương tự cho resources.
4. Phân biệt `sourceSets.main.compileClasspath`, `sourceSets.main.runtimeClasspath`, `configurations.compileClasspath` và `sourceSets.main.output`.
5. Hiểu `compileJava`, `processResources`, `classes`, `compileTestJava`, `processTestResources`, `test`, `jar`.
6. Chạy một ứng dụng Java 17+ đọc resource qua ClassLoader, dùng source directory tùy biến và có JUnit tests.
7. Thiết kế SourceSet `integrationTest` tách riêng, cấu hình custom Test task đúng classpath.
8. Phân biệt source thường, generated source, generated resource; tránh hardcode `build/` và thiếu task dependency.

> Ví dụ chính dùng **Gradle Groovy DSL** (`build.gradle`), Java 17+ và Gradle Wrapper. Kotlin DSL (`build.gradle.kts`) có cú pháp khác. Các ví dụ mở rộng được ghi rõ là **thay thế** hoặc **bổ sung**, không dán tất cả tùy tiện vào một file.

## 2. SourceSet là gì — và không phải là gì?

Một `SourceSet` là một mô hình logic thuộc Java plugin. Nó không phải một folder đơn lẻ, một Maven dependency, cũng không phải một Gradle task. Một SourceSet có thể gồm **nhiều thư mục source**, **nhiều thư mục resources**, classpath và output:

```text
SourceSet main
├── java source roots
│   ├── src/main/java
│   └── src/extra/java             (thêm bằng srcDir)
├── resource roots
│   ├── src/main/resources
│   └── src/extra/resources        (thêm bằng srcDir)
├── compileClasspath              -> libraries dùng khi javac compile main
├── runtimeClasspath              -> main output + runtime dependencies
└── output
    ├── classesDirs                -> .class
    ├── resourcesDir               -> resources đã copy/xử lý
    └── additional registered dirs -> nếu có task tạo output riêng
```

Với SourceSet `test`, Gradle lặp lại ý tưởng đó cho file test, tài nguyên test, lớp test và test classpath. SourceSet có tính **mô hình hóa nguồn và đầu ra**; các task của Java plugin sử dụng mô hình này để compile, xử lý tài nguyên, tạo JAR và chạy tests.

**Khác biệt dễ nhầm:**

| Khái niệm | Đúng nghĩa |
| --- | --- |
| `sourceSets.main` | Một `SourceSet` logic, đại diện code/resources production. |
| `sourceSets.main.java` | `SourceDirectorySet` chọn các file Java nguồn của `main`. |
| `sourceSets.main.resources` | `SourceDirectorySet` chọn các file tài nguyên, thường không phải Java. |
| `sourceSets.main.output` | `SourceSetOutput` gồm classes, resources và các output dirs đăng ký thêm. |
| `tasks.named('compileJava')` | `TaskProvider` của tác vụ biên dịch Java; không phải SourceSet. |
| `configurations.compileClasspath` | Resolvable dependency configuration cung cấp thư viện cho compiler. |
| `sourceSets.main.compileClasspath` | `FileCollection` được compile task sử dụng; có thể được cấu hình bổ sung. |
| `src/main/java` | Folder convention, không tự mang định nghĩa classpath khi chưa có plugin liên quan. |

Đừng viết toàn bộ logic phụ thuộc đường dẫn bằng tay chỉ vì project hiện đang nhỏ. Khi dùng SourceSet, Gradle có thể quản lý thay đổi thư mục, task dependency và IDE model một cách nhất quán hơn.

## 3. Layout mặc định của Java plugin

Java plugin tạo convention như sau:

```text
project/
├── settings.gradle
├── build.gradle
├── gradlew, gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/         Java production
    │   └── resources/    dữ liệu production
    └── test/
        ├── java/         Java tests
        └── resources/    dữ liệu chỉ test cần
```

| SourceSet | Java source root | Resources source root | Dùng ở đâu |
| --- | --- | --- | --- |
| `main` | `src/main/java` | `src/main/resources` | `compileJava`, `processResources`, `jar`, ứng dụng runtime. |
| `test` | `src/test/java` | `src/test/resources` | `compileTestJava`, `processTestResources`, `test`. |

Các thư mục chưa tồn tại **không phải lỗi**. Gradle biên dịch/copy những gì nó tìm thấy; task có thể `NO-SOURCE` nếu không có file nguồn phù hợp. Tuy nhiên một test nằm nhầm `src/tests/java` (thừa `s`) sẽ không tự được phát hiện theo convention.

Đường dẫn package Java thường phản ánh tên package: class `example.App` ở `src/main/java/example/App.java`. Quy tắc package là của Java, không phải vì Gradle yêu cầu mọi thư mục phải tuyệt đối trùng package; tuân convention giúp tránh nhầm lẫn với IDE, annotation processors và các plugin.

### 3.1. Task nào được tạo?

| Task | Chức năng | Output mặc định thường thấy |
| --- | --- | --- |
| `compileJava` | Compile `main.java`. | `build/classes/java/main` |
| `processResources` | Copy/lọc `main.resources`. | `build/resources/main` |
| `classes` | Lifecycle task chuẩn bị classes + resources của main. | Không tự sinh dữ liệu riêng. |
| `compileTestJava` | Compile `test.java` dựa trên main output và test compile classpath. | `build/classes/java/test` |
| `processTestResources` | Copy/lọc `test.resources`. | `build/resources/test` |
| `testClasses` | Lifecycle task chuẩn bị classes + resources của test. | Không tự sinh dữ liệu riêng. |
| `test` | Chạy test bằng test output và runtime classpath. | `build/test-results/test`, `build/reports/tests/test`. |
| `jar` | Đóng gói output của main, **không** tự lấy test source/output. | `build/libs/<project-name>.jar` nếu chưa đổi archive naming. |

Các đường `build/...` ở bảng là **convention** của Java plugin trong Gradle hiện đại; có thể khác nếu build thay `layout.buildDirectory`, `java.destinationDirectory`, `resourcesDir` hoặc plugins khác tham gia. Lấy đường thực từ các properties/task thay vì đoán khi viết build logic.

Sơ đồ:

```text
src/main/java ------- compileJava -------- build/classes/java/main
src/main/resources -- processResources --- build/resources/main
                                  \       /
                                   classes ---- jar (main output)
src/test/java ------- compileTestJava ---- build/classes/java/test
src/test/resources -- processTestResources - build/resources/test
                                  \       /
                                   testClasses ---- test
```

Khi chạy `./gradlew build`, Java plugin thường kết hợp lifecycle `assemble` (trong đó có `jar`) và `check` (trong đó có `test`). Đừng coi `compileJava` là tác vụ copy resource: `processResources` phụ trách phần đó.

## 4. API của SourceSet và SourceDirectorySet

Một SourceSet cung cấp:

- `java`, `resources`: `SourceDirectorySet` quản lý thư mục và bộ lọc file.
- `allJava`: toàn bộ Java sources liên quan, có thể gồm nguồn do plugin ngôn ngữ khác thêm.
- `allSource`: mọi sources/resources liên quan của SourceSet.
- `compileClasspath`, `runtimeClasspath`: `FileCollection` cho các giai đoạn khác nhau.
- `output`: `SourceSetOutput` chứa các đầu ra.

`java` và `resources` là read-only *references* tới `SourceDirectorySet`, nhưng bạn có thể cấu hình **nội dung** của chúng qua `srcDir`, `srcDirs`, `include`, `exclude`. Không cố gán một Java String trực tiếp cho `sourceSets.main.java`.

### 4.1. Thêm một source directory bằng srcDir

```groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            srcDir 'src/extra/java'
        }
        resources {
            srcDir 'src/extra/resources'
        }
    }
}
```

Sau cấu hình trên:

- Java của main có thể lấy từ `src/main/java` **và** `src/extra/java`.
- Resources của main lấy từ `src/main/resources` **và** `src/extra/resources`.
- SourceSet vẫn là **main**, không có `extra` SourceSet mới, cũng không có `compileExtraJava` tự phát sinh.
- Những file `.java` ở cả hai Java roots được `compileJava` xử lý cùng một compilation context.

Đây là phương án tốt nếu thư mục thứ hai chỉ bổ sung cùng nhóm code production và **dùng cùng classpath/output**.

### 4.2. Thay thế toàn bộ bằng srcDirs = [...]

```groovy
sourceSets {
    main {
        java {
            srcDirs = ['legacy-src']
        }
        resources {
            srcDirs = ['legacy-resources']
        }
    }
}
```

Đây là **cấu hình thay thế**, không áp dụng cùng lúc với ví dụ thêm thư mục nếu không cố ý. Sau phép gán:

- `src/main/java` không còn nằm trong danh sách Java roots theo convention.
- `src/main/resources` không còn nằm trong resources roots.
- Gradle chỉ đọc những roots trong danh sách mới (và các roots được plugin hoặc cấu hình bổ sung tiếp theo).

**Quy tắc nhớ:** `srcDir('x')` **thêm**; `srcDirs = ['x']` **thay thế**. Đó là một trong những nguyên nhân phổ biến của lỗi `NO-SOURCE` hoặc class bỗng không được compile sau khi sửa `build.gradle`.

Nếu muốn chỉ định nhiều roots nhưng vẫn giữ convention, dùng nhiều `srcDir` hoặc đưa cả thư mục mặc định vào danh sách thay thế rõ ràng:

```groovy
sourceSets {
    main {
        java {
            srcDirs = ['src/main/java', 'legacy-src']
        }
    }
}
```

### 4.3. include/exclude đúng file tree

```groovy
sourceSets {
    main {
        java {
            exclude '**/experimental/**'
        }
        resources {
            include '**/*.properties', '**/*.txt'
            exclude '**/secrets/**'
        }
    }
}
```

Đoạn này **chỉ minh họa bộ lọc**, không dùng cho lab mục 7 vì nó có thể bỏ sót một số resource khác. Patterns tuân kiểu Ant, tương đối so với source roots; `include`/`exclude` làm thay đổi **file được xử lý**, không chỉ làm IDE ẩn thư mục.

**Không xem exclude khỏi resource processing là biện pháp bảo vệ secret đủ mạnh.** Bí mật không nên được commit dưới `src/main/resources` ngay từ đầu. Nếu file secret đã nằm trong repository, việc bỏ qua lúc đóng gói không xóa lịch sử hoặc những nơi khác có thể đọc nó.

## 5. Resources: source root khác runtime classpath

Resource là dữ liệu dùng khi runtime: file cấu hình, localization, template, JSON, XML, icon, chứng chỉ public hoặc fixture của test. Với Java plugin, `processResources` là một task kiểu `ProcessResources` (Copy task chuyên biệt) để copy/lọc resources vào thư mục output.

Ví dụ:

```text
src/main/resources/app.properties
src/main/resources/templates/email.txt
src/main/resources/i18n/messages_vi.properties
```

Sau `processResources`:

```text
build/resources/main/app.properties
build/resources/main/templates/email.txt
build/resources/main/i18n/messages_vi.properties
```

**Đường dẫn tương đối bên trong resource root được bảo toàn.** Nếu root là `src/main/resources`, tên classpath resource của file `app.properties` là `app.properties`, không phải `src/main/resources/app.properties`. Nếu file nằm `src/main/resources/templates/email.txt`, đường classpath là `templates/email.txt`.

### 5.1. Đọc resource từ Java

Cách dùng ClassLoader phù hợp khi chạy trong IDE, Gradle `run`, test, hoặc file JAR:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class ResourceReader {
    public static String read(String path) {
        try (InputStream in = ResourceReader.class
                .getClassLoader().getResourceAsStream(path)) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: " + path);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
```

Đây là **lớp utility minh họa**: nó cần được lưu ở `ResourceReader.java` và gọi từ chương trình khác, không có phương thức `main` để chạy độc lập. Lab đầy đủ ở mục 7 sẽ có `main()` và stdout cụ thể.

Điểm cần chú ý:

- `ClassLoader.getResourceAsStream("app.properties")` tra **classpath**, không tra current working directory.
- `Class.getResourceAsStream("/app.properties")` sử dụng đường **tuyệt đối tính từ classpath root** vì có `/` đầu; nếu bỏ `/` thì đường tương đối theo package của class.
- `ClassLoader.getResourceAsStream` không dùng dấu `/` đầu. Đặt path `templates/email.txt` thay vì một absolute OS path.
- Trả về `null` khi không tìm thấy, nên **kiểm tra trước khi đọc**.
- Không dùng `new File("src/main/resources/app.properties")` cho code production; đường đó thường không tồn tại khi ứng dụng được đóng gói JAR hoặc chạy từ directory khác.
- `InputStream.readAllBytes()` có từ Java 9+, phù hợp Java 17. Với file lớn, nên đọc stream theo chunk thay vì giữ toàn bộ trong bộ nhớ.

### 5.2. Resources test không tự đưa vào JAR sản phẩm

`src/test/resources` được xử lý bởi `processTestResources` thành `build/resources/test` và góp vào **test runtime classpath**. Nó giúp test đọc fixture nhưng không tự xuất hiện trong `jar` của main.

Nếu code sản phẩm cần một file khi phát hành, file đó phải thuộc main resources hoặc một output được đăng ký thích hợp vào main. Nếu file chỉ phục vụ test, hãy đặt nó dưới test resources để tránh tăng kích thước hoặc vô tình công bố dữ liệu test trong sản phẩm.

### 5.3. Copy resources không phải Java compile

Để xem riêng hai bước:

```bash
./gradlew clean compileJava processResources --console=plain
```

`compileJava` biên dịch source thành `.class`. `processResources` copy/lọc resource; `classes` là lifecycle task phụ thuộc hai phần và có thể được gọi gọn:

```bash
./gradlew classes --console=plain
```

Thay resource thường khiến `processResources` cần làm lại; không suy luận `compileJava` chắc chắn phải biên dịch lại mọi class. Cách Gradle đánh giá up-to-date/incremental còn phụ thuộc các inputs, annotation processors và cấu hình task.

### 5.4. Resource processing có thể biến đổi nội dung

Ngoài copy nguyên file, `ProcessResources` hỗ trợ `filesMatching`, `expand`, `filteringCharset` để biến đổi các file text.

**Ví dụ mở rộng**: tạo `src/main/resources/version.properties` với nội dung:

```properties
version=${appVersion}
```

Sau đó bổ sung vào `build.gradle`:

```groovy
tasks.named('processResources', ProcessResources) {
    def versionText = '1.0.0'
    inputs.property('appVersion', versionText)
    filteringCharset = 'UTF-8'

    filesMatching('version.properties') {
        expand(appVersion: versionText)
    }
}
```

Khi task chạy, file `build/resources/main/version.properties` có dòng `version=1.0.0`. `expand` dùng cú pháp Groovy template `${name}`, nên cần escape hoặc chọn cách copy khác nếu dữ liệu chứa ký hiệu `${...}` mà bạn không muốn thay. **Chỉ dùng với text phù hợp**; không áp dụng template expansion bừa bãi cho ảnh, file nhị phân hoặc tài liệu có dữ liệu `${...}` riêng.

`inputs.property` mô hình hóa giá trị version đầu vào để Gradle biết thay đổi có thể yêu cầu xử lý lại resources. Trong project thực, hãy lấy version từ Provider/Property được quản lý, không lưu secret hoặc thông tin máy developer vào resource được phát hành.

## 6. Classpath: ba lớp cần tách biệt

**Classpath** là tập entry (directories/JAR) mà compiler hoặc JVM nhìn thấy. Một dependency khai báo bằng tọa độ không đồng nghĩa classpath chứa đúng phiên bản đó ngay lập tức; Gradle cần resolve version/variant theo configuration.

### 6.1. Main compileClasspath

```text
src/main/java + src/extra/java
        |
        | javac sử dụng main compileClasspath
        v
   compileJava
        |
        v
build/classes/java/main
```

Các bucket như `implementation`, `compileOnly` đóng góp libraries khi compile main. Nhưng `runtimeOnly` không được đưa vào compile classpath **chỉ vì nó ở runtime**. Điều này tránh để mã nguồn vô tình import API chỉ có ở runtime.

### 6.2. Main runtimeClasspath

```text
SourceSet main runtimeClasspath
        |
        +-- sourceSets.main.output
        |     +-- compiled classes
        |     +-- processed resources
        |     \-- registered generated outputs
        |
        +-- resolved runtime dependencies
              +-- implementation
              \-- runtimeOnly
```

`sourceSets.main.runtimeClasspath` là `FileCollection` chứa output của chính SourceSet **và** runtime dependencies. `configurations.runtimeClasspath` là resolvable dependency configuration: khi xem nó qua report `dependencies`, bạn chủ yếu thấy các external/project dependency components, không phải danh sách mọi file `.class` và resource của main.

**Đừng thay `sourceSets.main.runtimeClasspath` bằng `configurations.runtimeClasspath`** trong một JavaExec nếu bạn cần chạy class đã biên dịch: danh sách từ configuration không tự có local compiled classes. Bài lab dùng plugin `application`, task `run` đã được cấu hình classpath tương ứng.

### 6.3. Test compile và test runtime

```text
testCompileClasspath:
  - main compiled output
  - testImplementation / testCompileOnly và các nguồn được kế thừa
  - dependencies phù hợp

testRuntimeClasspath:
  - main output
  - test output
  - testImplementation / testRuntimeOnly và runtime dependencies
```

Đó là mô tả **classpath hiệu lực của compilation và test JVM**; class/source-set outputs không nhất thiết xuất hiện thành “module” trong report `testCompileClasspath` của dependency resolver.

Test có thể compile thành công với JUnit annotation API ở `testImplementation` nhưng không chạy nếu thiếu JUnit engine hoặc Platform launcher tại `testRuntimeOnly`. Ngược lại, đặt Jupiter API chỉ ở `testRuntimeOnly` khiến compiler không nhận ra `org.junit.jupiter.api.Test`.

### 6.4. Configuration khác SourceSet classpath

| Đối tượng | Vai trò |
| --- | --- |
| `implementation`, `compileOnly`, `runtimeOnly` | Buckets để **khai báo** dependency. |
| `compileClasspath`, `runtimeClasspath` | Configurations để **resolve** dependency của main. |
| `testImplementation`, `testRuntimeOnly` | Buckets dành riêng test. |
| `testCompileClasspath`, `testRuntimeClasspath` | Resolvable configurations cho test dependencies. |
| `sourceSets.main.compileClasspath` | FileCollection của classpath cho `compileJava`. |
| `sourceSets.main.runtimeClasspath` | FileCollection đầy đủ dùng để chạy main, có output + dependencies. |
| `sourceSets.main.output` | FileCollection riêng cho **output local**: classes và resources. |

**Không lấy `sourceSets.main.compileClasspath.files` quá sớm tại pha cấu hình** chỉ để in report hoặc tự chọn JAR: nó có thể buộc resolution sớm, làm chậm build, gây lỗi khi repo tạm thời không sẵn và cản cơ chế configuration cache. Hãy giữ Provider/FileCollection lazy và dùng công cụ báo cáo dependency được Gradle hỗ trợ.

## 7. Lab chạy được: Java 17+, hai Java roots và hai resource roots

Lab này chứng minh trong **một SourceSet main** có thể thêm cả Java sources lẫn resources mà không tạo task compile riêng. Nó dùng external dependency Commons Lang để classpath có một thư viện thực, đồng thời có JUnit Jupiter tests kiểm tra output và test resource.

### 7.1. Cây thư mục

```text
source-set-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/App.java
    │   └── resources/app.properties
    ├── extra/
    │   ├── java/example/TextFormatter.java
    │   └── resources/extra/info.txt
    └── test/
        ├── java/example/AppTest.java
        └── resources/test-only.txt
```

`gradlew` và `gradle/wrapper/ ...` biểu thị **Wrapper đã được tạo**, không phải lệnh tự sinh. Nếu project mới chưa có Wrapper, dùng Gradle đã cài đặt để khởi tạo/thiết lập Wrapper phù hợp hoặc tạo project bằng `gradle init`. Máy cần JDK 17+ và mạng để lấy dependencies chưa cache.

### 7.2. File settings.gradle

```groovy
rootProject.name = 'source-set-lab'
```

### 7.3. File build.gradle — toàn bộ nội dung baseline

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

sourceSets {
    main {
        java {
            srcDir 'src/extra/java'
        }
        resources {
            srcDir 'src/extra/resources'
        }
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'

    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter-api'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'example.App'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

- `application` áp dụng hỗ trợ Java và tạo task `run`, ngoài các tasks của Java plugin.
- `java.srcDir` và `resources.srcDir` thêm roots vào **main**, giữ convention mặc định. Không định nghĩa thêm SourceSet `extra`.
- `implementation` đưa Commons Lang vào main compile/runtime dependencies.
- `testImplementation` của JUnit BOM và Jupiter API giúp test compile; `testRuntimeOnly` cung cấp Jupiter Engine và Platform Launcher.
- JUnit BOM `5.11.4` quản lý phiên bản Jupiter `5.11.4` và Platform `1.11.4`; các tọa độ không version trong ví dụ chỉ có ý nghĩa vì BOM đang tham gia graph.
- `useJUnitPlatform()` cấu hình cơ chế test runner, không tự tải test dependencies.

**Không cần khai báo `sourceSets.test` trong lab**, bởi Java plugin đã tạo source set này. Dự án dùng hai test directories theo convention.

### 7.4. File src/main/resources/app.properties

```properties
name=gradle
```

Ở đây file chứa ASCII nên có thể đọc ổn định trong nhiều môi trường. Code Java bên dưới chủ động dùng UTF-8 khi nạp properties để nhất quán khi nội dung có tiếng Việt ở dự án thật.

### 7.5. File src/extra/resources/extra/info.txt

```text
resources-ok
```

Tên classpath resource là `extra/info.txt`. Dù file gốc nằm trong một directory không mặc định `src/extra/resources`, sau khi thêm `resources.srcDir`, nó vẫn là resource của SourceSet main. Nó sẽ được `processResources` copy về `build/resources/main/extra/info.txt`.

### 7.6. File src/extra/java/example/TextFormatter.java

```java
package example;

import java.util.Locale;

public final class TextFormatter {
    private TextFormatter() {
    }

    public static String wrap(String text) {
        return "[" + text.toUpperCase(Locale.ROOT) + "]";
    }
}
```

`TextFormatter` là class **production** mặc dù nằm ở `src/extra/java`. Do `srcDir` đã thêm root, `compileJava` biên dịch class này cùng các file ở `src/main/java`. Không có `compileExtraJava` trong lab.

### 7.7. File src/main/java/example/App.java

```java
package example;

import org.apache.commons.lang3.StringUtils;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String message() {
        Properties props = new Properties();

        try (InputStream in = App.class.getClassLoader()
                .getResourceAsStream("app.properties")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing app.properties");
            }
            props.load(new InputStreamReader(
                    in, StandardCharsets.UTF_8));
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }

        String name = StringUtils.capitalize(
                props.getProperty("name"));

        String extra;
        try (InputStream in = App.class.getClassLoader()
                .getResourceAsStream("extra/info.txt")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing extra/info.txt");
            }
            extra = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }

        return TextFormatter.wrap(name) + " " + extra;
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**Giải thích từng nguồn dữ liệu:**

1. `StringUtils.capitalize` do Commons Lang cung cấp, chứng minh main compile classpath đã resolve dependency `implementation`.
2. `App.java` thuộc Java source root mặc định.
3. `TextFormatter.java` thuộc Java source root bổ sung; vì cả hai class chung package `example`, compiler sử dụng chúng bình thường.
4. `app.properties` từ resources root mặc định được tìm qua `ClassLoader`.
5. `extra/info.txt` từ resources root bổ sung được tìm qua chính ClassLoader.
6. `StringUtils.capitalize("gradle")` trả `Gradle`. `TextFormatter.wrap("Gradle")` trả `[GRADLE]`, nên kết hợp với text resource sẽ cho output dự kiến.
7. Code kiểm tra `null` rõ ràng; không phụ thuộc `System.getProperty("user.dir")` hoặc path nguồn tồn tại sau packaging.

### 7.8. File src/test/resources/test-only.txt

```text
test-data
```

File này dành riêng cho test source set. Nó được copy bởi `processTestResources` và có trên test runtime classpath; nó **không nằm trong JAR của main** theo cấu hình chuẩn.

### 7.9. File src/test/java/example/AppTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class AppTest {
    @Test
    void combinesJavaAndResources() {
        assertEquals("[GRADLE] resources-ok", App.message());
    }

    @Test
    void readsTestOnlyResource() throws IOException {
        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream("test-only.txt")) {
            assertNotNull(in);
            String text = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            assertEquals("test-data", text);
        }
    }
}
```

Có **hai** phương thức `@Test`. Test đầu truy cập `main output` và class của production, test thứ hai đọc fixture của **test resources**. Vì test source import Jupiter API, JUnit được khai báo ở test scope, không làm JAR sản phẩm phụ thuộc test libraries.

### 7.10. Chạy thực tế và stdout đáng tin

Linux/macOS:

```bash
./gradlew clean run --console=plain
./gradlew test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean run --console=plain
.\gradlew.bat test --console=plain
```

**Stdout do chính `App.main` in** là một dòng:

```text
[GRADLE] resources-ok
```

Đó là kết quả trực tiếp của mã Java và resource files đã nêu. Console Gradle còn có thể in daemon, task execution, thời gian và `BUILD SUCCESSFUL`; không so sánh toàn bộ log byte-for-byte.

Với Maven Central truy cập được và các file đúng như lab, `AppTest` có **2 tests PASS**. Vì `testLogging` bật events, phần log có thể tương tự:

```text
AppTest > combinesJavaAndResources() PASSED
AppTest > readsTestOnlyResource() PASSED
BUILD SUCCESSFUL
```

Đây là **trích đoạn minh họa**, thứ tự test không được đảm bảo. Nếu app chạy được nhưng test không compile do thiếu JUnit, xem `testCompileClasspath`. Nếu test compile được nhưng runtime fail do thiếu JUnit Platform Engine/Launcher, xem `testRuntimeClasspath`.

### 7.11. Kiểm tra class/resource output sau khi build

```text
build/
├── classes/
│   └── java/
│       ├── main/
│       │   └── example/
│       │       ├── App.class
│       │       └── TextFormatter.class
│       └── test/
│           └── example/AppTest.class
└── resources/
    ├── main/
    │   ├── app.properties
    │   └── extra/info.txt
    └── test/
        └── test-only.txt
```

Sau `./gradlew jar`, JAR main thường chứa:

```text
META-INF/MANIFEST.MF
example/App.class
example/TextFormatter.class
app.properties
extra/info.txt
```

**Không** có `AppTest.class` hay `test-only.txt` trong JAR main theo mặc định. Xem thực tế bằng JDK tool:

```bash
./gradlew jar --console=plain
jar tf build/libs/source-set-lab.jar
```

Lệnh `jar tf` dùng JDK `jar` và tên archive mặc định của lab (`rootProject.name = 'source-set-lab'`, không đặt project version khác). Nếu build thay archiveBaseName/version/classifier, dùng tên JAR thực tế trong `build/libs`.

## 8. Khác nhau giữa SourceSetOutput và classesDirs

Trong Gradle, `sourceSets.main.output` thuộc kiểu `SourceSetOutput` (một `FileCollection`). Nó không chỉ là thư mục `.class`.

| Truy cập | Bao gồm |
| --- | --- |
| `sourceSets.main.output.classesDirs` | Thư mục chứa `.class`, có thể nhiều thư mục từ Java/Kotlin/Groovy. |
| `sourceSets.main.output.resourcesDir` | Thư mục resource output của SourceSet (`File`, có thể `null` trong một số cấu hình). |
| `sourceSets.main.output` | Toàn bộ classes dirs, processed resources dir và các extra output dirs đã đăng ký. |
| `sourceSets.main.java.destinationDirectory` | `DirectoryProperty` đích Java compilation; trong plugin Java chuẩn thường góp vào `classesDirs`. |

**Gradle 8+ lưu ý:** việc lấy riêng `sourceSets.main.output.classesDirs` không mặc nhiên làm task phụ thuộc `processResources`. Nó chủ yếu mang task dependencies tạo class files. Nếu một task cần **cả class và resources**, dùng **`sourceSets.main.output`** làm input; đừng chỉ lấy `classesDirs` rồi trông chờ resources đã được xử lý.

Ví dụ task copy artifact:

```groovy
tasks.register('copyMainOutput', Copy) {
    from sourceSets.main.output
    into layout.buildDirectory.dir('copied-main-output')
}
```

Khi chạy `./gradlew copyMainOutput`, task sẽ lấy cả `example/App.class` và `app.properties`, `extra/info.txt` theo quan hệ task output. `Copy.from(sourceSets.main.output)` là dataflow rõ ràng, tốt hơn hardcode đường dẫn `build/classes/java/main` và `build/resources/main` riêng lẻ.

### 8.1. Không gộp output của nhiều task vào cùng thư mục một cách tùy tiện

Đổi `java.destinationDirectory` thành `build/resources/main` để “tất cả nằm chung” dễ tạo output overlap. Điều đó ảnh hưởng up-to-date checking, caching, stale files và ownership. Giữ classes và resources output tách biệt theo convention hoặc thiết kế owner rõ, sau đó dùng `SourceSetOutput` để gom cho JAR/runtime.

## 9. Thêm SourceSet mới cho integrationTest

`srcDir` chỉ bổ sung cùng nhóm nguồn. Nếu bạn muốn **một bộ test độc lập** có classpath khác, tasks khác và lifecycle riêng, nên định nghĩa **SourceSet mới** hoặc dùng **JVM Test Suite plugin**.

### 9.1. Khi nào cần SourceSet mới?

- Integration tests cần database driver, API server, container tools mà unit tests không dùng.
- Code generation cần một bước compile/packaging riêng.
- Một module có test nhanh và test chậm với task/report riêng.
- Một nhóm nguồn cần compiled classes không được đóng gói vào JAR chính.

Không cần tạo SourceSet mới chỉ để thêm thư mục `src/legacy/java` nếu nội dung vẫn là **main code** cùng compile/runtime classpath.

### 9.2. Một ví dụ bổ sung vào lab: integrationTest

**Đoạn dưới là phần mở rộng**, hãy đặt vào cuối `build.gradle` của lab mục 7 (không thêm nhiều block trùng tên):

```groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}

dependencies {
    integrationTestImplementation platform('org.junit:junit-bom:5.11.4')
    integrationTestImplementation 'org.junit.jupiter:junit-jupiter-api'
    integrationTestRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Giải thích theo thứ tự:

1. `sourceSets.integrationTest` tạo nhóm nguồn **riêng**. Java plugin tự tạo các tasks như `compileIntegrationTestJava`, `processIntegrationTestResources`, `integrationTestClasses` và configurations như `integrationTestImplementation`, `integrationTestRuntimeOnly`.
2. `compileClasspath += sourceSets.main.output` cho compiler của integration tests nhìn thấy production compiled classes.
3. `runtimeClasspath += sourceSets.main.output` cho test JVM nhìn thấy production classes **và resources**.
4. `integrationTestImplementation.extendsFrom implementation` thêm main implementation dependencies vào compile scope của suite; `integrationTestRuntimeOnly.extendsFrom runtimeOnly` thêm các main runtime-only libraries cần thiết.
5. JUnit API nằm trong `integrationTestImplementation`, Engine/Launcher nằm trong `integrationTestRuntimeOnly`.
6. `tasks.register('integrationTest', Test)` là **bước bắt buộc riêng** để chạy test; tạo SourceSet **không tự tạo** một `Test` task chạy tất cả tests của SourceSet đó.
7. `testClassesDirs` chỉ rõ thư mục test classes, `classpath` chỉ rõ runtime dependencies. Đặc biệt với Gradle 9+, không dựa vào convention cũ rằng mọi custom Test task tự lấy classpath của SourceSet `test`.
8. `shouldRunAfter` chỉ ưu tiên chạy integrationTest sau unit test **nếu cả hai có trong graph**; nó không tự đưa `test` vào graph. `check.dependsOn` mới gắn integrationTest vào lifecycle check.

### 9.3. Mã integration test minh họa chạy được

Tạo **`src/integrationTest/java/example/AppIntegrationTest.java`**:

```java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIntegrationTest {
    @Test
    void mainResourcesReachIntegrationClasspath() {
        assertEquals("[GRADLE] resources-ok", App.message());
    }
}
```

Chạy:

```bash
./gradlew integrationTest --console=plain
./gradlew check --console=plain
```

`integrationTest` chạy một test trong source set riêng, dự kiến PASS khi lab chính vẫn nguyên vẹn. `check` chạy cả các verification tasks được gắn, gồm unit `test` và `integrationTest`. File test của SourceSet mới không tự được đóng gói vào JAR main.

**Tùy chọn thiết kế hiện đại:** JVM Test Suite plugin của Gradle có DSL `testing { suites { ... } }` để mô hình hóa các test suites, dependencies và targets; phù hợp khi tổ chức có nhiều suite theo chuẩn chung. Đoạn thủ công ở trên giúp học rõ từng cơ chế SourceSet/classpath/task, không phải cách duy nhất.

## 10. Generated Java source: đừng chỉ thêm đường dẫn build/generated

Một lỗi phổ biến là có task tạo `.java` dưới `build/generated`, rồi viết:

```groovy
// PHẢN VÍ DỤ: chỉ thêm đường dẫn; không mô tả ai tạo file.
sourceSets.main.java.srcDir 'build/generated/sources/marker/java'
```

Nếu compiler chạy trước task sinh source, `compileJava` không tìm thấy file hoặc dùng source cũ. Đường dẫn trùng output không giúp Gradle suy ra dependency **chỉ bằng tên file**. Đừng chạy `generate...` tay trước mỗi lần compile như workaround lâu dài.

### 10.1. Gắn nguồn được tạo với task producer

Phần code sau là **một mở rộng độc lập có thể thêm vào lab** (không cần áp dụng cùng với mọi mở rộng khác):

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

abstract class GenerateMarker extends DefaultTask {
    @OutputDirectory
    abstract DirectoryProperty getTargetDir()

    @TaskAction
    void generate() {
        File target = targetDir.file('example/GeneratedMarker.java')
                .get().asFile
        target.parentFile.mkdirs()
        target.setText(
            'package example; ' +
            'public final class GeneratedMarker { ' +
            'public static String value() { return "generated"; } }',
            'UTF-8'
        )
    }
}

def generator = tasks.register('generateMarker', GenerateMarker) {
    targetDir.set(layout.buildDirectory.dir(
            'generated/sources/marker/java'))
}

sourceSets {
    main {
        java.srcDir(generator)
    }
}
```

- `@OutputDirectory` cho Gradle biết producer tạo một source tree.
- `tasks.register` trả `TaskProvider`, không phải một string path.
- `java.srcDir(generator)` sử dụng task output làm source input, giúp mang theo dependency tới generator.
- `generateMarker` tạo class `example.GeneratedMarker` trước khi compile cần đọc file.
- Tách thư mục generated sources ra khỏi regular `src/main/java`; không check in generated source nếu project muốn tái tạo chúng trong build.

Sau `./gradlew compileJava`, hãy tìm `build/classes/java/main/example/GeneratedMarker.class`; task compile có thể nhận source mới thông qua input mang build dependency.

**Không ghi output tạo source trực tiếp vào `src/main/java` khi đó là generated data**, tránh làm thay đổi working tree và làm khó incremental build. Với annotation processors, hãy dùng cơ chế generated source và annotationProcessor path của JavaCompile thay vì tạo một nhiệm vụ tự động riêng không cần thiết.

## 11. Generated resources: đăng ký output khác với resource source root

Nếu một task tạo file **resource đã hoàn chỉnh**, không nhất thiết bắt `processResources` copy lại nó. Gradle cho phép đăng ký thư mục output bổ sung vào `SourceSetOutput`.

Ví dụ mở rộng từ tài liệu `SourceSetOutput`:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

abstract class GenerateCatalog extends DefaultTask {
    @OutputDirectory
    abstract DirectoryProperty getTargetDir()

    @TaskAction
    void generate() {
        File target = targetDir.file('generated/catalog.txt')
                .get().asFile
        target.parentFile.mkdirs()
        target.setText('generated resource\n', 'UTF-8')
    }
}

def generatedCatalog = tasks.register('generateCatalog',
        GenerateCatalog) {
    targetDir.set(layout.buildDirectory.dir(
            'generated/resources/catalog'))
}

sourceSets {
    main {
        output.dir(generatedCatalog)
    }
}
```

`output.dir(generatedCatalog)` đăng ký output directory và thông tin task cần thực hiện. Khi `jar` hoặc task tiêu thụ toàn bộ `sourceSets.main.output`, directory đó có thể tham gia classpath/đóng gói, và Gradle biết task producer.

Phân biệt hai mô hình:

- `resources.srcDir('src/extra/resources')`: chỉ **input resource root**, thường đi qua `processResources` rồi tới `build/resources/main`.
- `output.dir(generatedCatalog)`: một **output directory đã được generator tạo**, được đăng ký trực tiếp vào SourceSet output; không cần giả định nó xuất hiện ở `build/resources/main`.

Đừng để hai generators cùng ghi một directory hoặc hai tasks cùng claim một file output. Khi một task đọc file generated, ưu tiên Provider/task output gốc, không raw `new File("build/generated/...")`.

## 12. Tùy chỉnh output, packaging và runtime

### 12.1. Đổi Java destinationDirectory

Khi thật sự cần thay nơi Gradle ghi `.class`:

```groovy
sourceSets {
    main {
        java {
            destinationDirectory.set(
                layout.buildDirectory.dir('custom-classes/main'))
        }
    }
}
```

Đây là một **override có chủ đích**; không thêm vào lab nếu không có yêu cầu thực tế. Thường nên giữ convention để IDE, plugins và tooling ít bị bất ngờ. Đổi `java.destinationDirectory` không có nghĩa đổi luôn nơi `processResources` xuất file.

### 12.2. Packaging main output

Task `jar` của Java plugin mặc định đóng gói output thuộc `sourceSets.main`. Nếu cần tạo một artifact riêng từ SourceSet custom, có thể đăng ký `Jar` với sourceSet tương ứng:

```groovy
tasks.register('integrationTestJar', Jar) {
    archiveClassifier = 'integration-tests'
    from sourceSets.integrationTest.output
}
```

Đoạn này chỉ chạy nếu bạn đã tạo SourceSet `integrationTest` ở mục 9, không áp dụng cho lab cơ bản. Nó tạo JAR **của integration test output**, khác JAR chính; không tự publish artifact hay làm integration tests được thực thi.

### 12.3. Đừng sửa classpath thành raw File list nếu không cần

Ví dụ phản pattern:

```groovy
tasks.register('runManually', JavaExec) {
    mainClass = 'example.App'
    // SAI: chỉ có external dependencies, thiếu local classes/resources:
    classpath = configurations.runtimeClasspath
}
```

Cách đúng cho một JavaExec chạy code main:

```groovy
tasks.register('runMainAgain', JavaExec) {
    mainClass = 'example.App'
    classpath = sourceSets.main.runtimeClasspath
}
```

Đoạn thứ hai có cả **compiled class dirs, resource dirs và dependencies**. Với project `application`, bạn thường không cần tự định nghĩa `JavaExec` vì task `run` đã làm đúng việc đó.

## 13. Chẩn đoán SourceSet và classpath theo bước

### Bước 1 — Xác định loại lỗi

| Lỗi | Đầu mối cần xem |
| --- | --- |
| `compileJava NO-SOURCE` | `sourceSets.main.java.srcDirs`, include/exclude, vị trí .java. |
| `cannot find symbol TextFormatter` | Thư mục `src/extra/java` có được thêm vào main không? Package/class name chính xác? |
| `package org.apache.commons.lang3 does not exist` | `implementation`/`compileClasspath`, repository và version. |
| `Missing app.properties` | File nằm dưới resources root? `processResources` có chạy? Path ClassLoader đúng? |
| `Missing extra/info.txt` | `resources.srcDir('src/extra/resources')`, đường tương đối `extra/info.txt`. |
| Test không tìm thấy `test-only.txt` | `src/test/resources`, `processTestResources`, test runtime classpath. |
| Test compile fail vì JUnit | `testImplementation`, `testCompileClasspath`. |
| Test compile pass nhưng test không chạy | Engine, Launcher, `useJUnitPlatform`, `testRuntimeClasspath`. |
| `NoClassDefFoundError` lúc chạy | `runtimeClasspath` hoặc output không tham gia runtime. |
| JAR thiếu file resource | `processResources`, `sourceSets.main.output`, `jar` contents. |
| `srcDirs = [...]` làm class biến mất | Danh sách cũ đã bị thay thế, không phải append. |
| Custom `integrationTest` không chạy | Có `Test` task? `testClassesDirs`, `classpath` và `check.dependsOn` đúng chưa? |

### Bước 2 — Kiểm tra graph của tasks

```bash
./gradlew classes --dry-run --console=plain
./gradlew test --dry-run --console=plain
```

Trong lab chuẩn, bạn sẽ thấy `compileJava`, `processResources`, `classes` và các tasks của test theo graph tương ứng. Với `--dry-run`, Gradle **không chạy action**, vì vậy không xác nhận file được tạo; các task có thể hiện trạng thái `SKIPPED` do dry-run.

Nếu generated sources/resources được nối đúng output Provider, task tạo dữ liệu cần có trong graph trước consumer. Nếu chỉ thêm path raw, generator có thể vắng mặt.

### Bước 3 — Kiểm tra dependency classpaths

```bash
./gradlew -q dependencies --configuration compileClasspath
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencies --configuration testCompileClasspath
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Với lab cơ bản, `commons-lang3` cần hiện diện trên main compile/runtime graph. JUnit thuộc test compile/runtime theo scope được khai báo. Đừng dùng `dependencies --configuration implementation` làm bằng chứng cuối cùng cho classpath **đã resolve**, vì `implementation` là declarable bucket.

Với lỗi chọn version khác mong đợi, dùng:

```bash
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency org.apache.commons:commons-lang3
```

### Bước 4 — Kiểm tra actual output và packaging

```bash
./gradlew clean classes test jar --console=plain
jar tf build/libs/source-set-lab.jar
```

Kiểm tra cả `build/classes/java/main` và `build/resources/main`, tránh suy đoán từ một directory. Nếu resources đã copy nhưng app không tìm thấy, đọc lại string path của `getResourceAsStream`, xác định class loader có đúng `SourceSet main runtimeClasspath` không.

### Bước 5 — Xem input và up-to-date

```bash
./gradlew classes --info --console=plain
./gradlew classes --info --console=plain
```

Lần thứ hai task có thể `UP-TO-DATE` khi inputs/outputs không đổi; đó là bình thường. Nếu file mới trong source root không được nhận diện, xem pattern excludes, directory path và tasks đang chạy. Nếu một producer đã ghi file ngoài directory output được khai báo, Gradle không thể theo dõi chính xác input/output và có thể vô hiệu hóa các tối ưu.

## 14. Những bẫy phổ biến cần tránh

1. **Nhầm SourceSet với directory**: SourceSet có thể dùng nhiều source/resource roots, không cần tạo một SourceSet mới cho từng folder.
2. **Gán `srcDirs = [...]` khi muốn thêm**: làm mất convention roots. Khi muốn bổ sung, dùng `srcDir(...)`.
3. **Đưa resources vào `java.srcDir`**: Java SourceDirectorySet chủ yếu chọn file `.java`, không tự thay `processResources`.
4. **Đọc `src/main/resources` bằng path hệ điều hành**: build JAR/IDE có working directory khác; dùng classpath resource API.
5. **Quên Java package path**: sai vị trí file có thể không lỗi tức thì nhưng gây nhầm lẫn với tools và generated code.
6. **Đóng gói test resources vào production JAR**: rò dữ liệu test/fixture; giữ `test` riêng.
7. **Nhầm `SourceSet.output.classesDirs` với toàn bộ output**: bỏ sót resources và task dependencies của `processResources`.
8. **Dùng `configurations.runtimeClasspath` để chạy local classes**: thiếu source set output.
9. **Chạy chỉ `compileJava` rồi đòi thấy processed resources**: cần `processResources` hoặc `classes`.
10. **Thêm generated dir bằng chuỗi raw path mà không nối generator task**: dễ build race và file stale.
11. **Hai tasks ghi cùng output dir**: gây overlap, khó cache và up-to-date.
12. **Dùng `classpath.files` ở configuration phase**: resolve sớm, ảnh hưởng cấu hình lazy.
13. **Tạo custom SourceSet rồi nghĩ nó tự có Test task**: compilation tasks được tạo, execution Test task cần cấu hình.
14. **Custom Test task không có `testClassesDirs` hoặc `classpath`**: Gradle 9 không tự thừa hưởng mặc định của test source set.
15. **Dùng `mustRunAfter` thay cho dependency dữ liệu**: ordering không thêm task vào graph.
16. **Cho rằng `testImplementation` làm thư viện có mặt trên main runtime**: source set/scopes có quan hệ một chiều.
17. **Đổi classes/resource output locations không cần thiết**: làm IDE/build logic phụ thuộc convention bị bất ngờ.
18. **Tự copy binary resource bằng `expand`**: làm hỏng bytes; chỉ filter text phù hợp.
19. **Bỏ qua encoding**: file `.properties` có Unicode nên code chủ động chọn UTF-8 (hoặc escape theo chuẩn dùng).
20. **Nhầm SourceSet với Java module (JPMS)**: `module-info.java` là hệ module Java; SourceSet là mô hình build khác.

## 15. Bài tập thực hành và đáp án

**Bài 1 — Đọc cấu trúc:** Trong lab, file `src/extra/java/example/TextFormatter.java` thuộc SourceSet nào? Gradle dùng task nào để compile? **Đáp án:** `main`, `compileJava`. Lý do: `main.java.srcDir` thêm root nhưng không tạo SourceSet mới.

**Bài 2 — Append và replace:** Nếu bạn thay `java.srcDir 'src/extra/java'` thành `java.srcDirs = ['src/extra/java']`, file `src/main/java/example/App.java` có còn được compile không? **Đáp án:** không theo roots còn lại, trừ khi root mặc định được thêm lại nơi khác.

**Bài 3 — Resources:** Tại sao `extra/info.txt` dùng trong `getResourceAsStream`, không phải `src/extra/resources/extra/info.txt`? **Đáp án:** ClassLoader tra path tương đối với **classpath root đã xử lý**, không tra source folder path.

**Bài 4 — Output:** Khi `sourceSets.main.output.classesDirs` đã sẵn sàng, bạn có chắc `processResources` chạy xong không? **Đáp án:** không; muốn cả classes và resources nên dùng `sourceSets.main.output`.

**Bài 5 — Test fixture:** Vì sao `test-only.txt` không có trong main JAR? SourceSet nào quản lý nó và task nào copy? **Đáp án:** `test.resources`, `processTestResources`, không được `jar` của main lấy mặc định.

**Bài 6 — Compile vs runtime:** Main có `implementation 'org.apache.commons:commons-lang3:3.17.0'`. Lệnh nào xem graph compile và runtime? Tại sao cùng dependency có thể xuất hiện ở cả hai? **Đáp án:** `dependencies --configuration compileClasspath` và `runtimeClasspath`, vì implementation tham gia cả compile và runtime.

**Bài 7 — Extend lab:** Thêm `src/extra/resources/extra/second.txt`, đọc bằng ClassLoader và chạy `./gradlew run`. Dự đoán nơi Gradle copy file và đường path resource. **Đáp án:** `build/resources/main/extra/second.txt` và `extra/second.txt`.

**Bài 8 — Custom suite:** Tại sao `sourceSets.integrationTest` tạo `compileIntegrationTestJava` nhưng chưa tự chạy tests? Cần cấu hình những property nào trên custom `Test` task? **Đáp án:** `testClassesDirs` và `classpath`, gắn vào `check` nếu muốn tham gia lifecycle.

**Bài 9 — Generated sources:** Tại sao `java.srcDir(generator)` tốt hơn `java.srcDir('build/generated/...')`? **Đáp án:** nó mang producer task output và dependency, compiler không phải dựa vào file có sẵn từ lần build cũ.

**Bài 10 — Generated resources:** So sánh `resources.srcDir('src/extra/resources')` và `output.dir(generateCatalog)`. Cách nào đi qua `processResources`, cách nào đăng ký output bổ sung đã được task tạo?

**Bài 11 — Resource filtering:** Thử bổ sung `version.properties` có `version=${appVersion}`. Tại sao cần `inputs.property` khi thay giá trị version và vì sao không dùng template expansion cho binary resources?

**Bài 12 — Java classpath:** Tạo `JavaExec` có `classpath = configurations.runtimeClasspath` rồi chạy. Khi nào nó báo `ClassNotFoundException`? Sửa bằng cách dùng `sourceSets.main.runtimeClasspath`.

### Tự kiểm tra nhanh

1. **SourceSet có bắt buộc tương ứng đúng một source directory?** Không.
2. **`main` và `test` do plugin nào tạo?** `java` và các plugin xây trên Java plugin.
3. **`srcDir` khác `srcDirs =` thế nào?** Append so với replace.
4. **Resource mặc định của main?** `src/main/resources`.
5. **Resource mặc định của test?** `src/test/resources`.
6. **Ai copy main resources?** `processResources`.
7. **Ai copy test resources?** `processTestResources`.
8. **`sourceSets.main.output` chỉ có class files?** Không, cả resources/output dirs bổ sung.
9. **`runtimeClasspath` có thể chứa resources không?** Có, qua SourceSet output.
10. **`implementation` là file collection đã resolve?** Không, đó là declarable dependency bucket.
11. **`classpath = configurations.runtimeClasspath` có đủ để JavaExec chạy local main class?** Không nếu thiếu local output.
12. **Thêm SourceSet mới có tự tạo custom Test task?** Không.
13. **`testClassesDirs` của custom Test task nên lấy ở đâu?** `sourceSets.<name>.output.classesDirs`.
14. **SourceSet có tự đóng gói tất cả vào JAR?** Chỉ các task packaging đã được cấu hình dùng output đó; `jar` mặc định dùng main.
15. **Khi nào chọn JVM Test Suite?** Khi muốn mô hình hóa nhiều bộ test có dependencies/targets riêng thay vì cấu hình tay từng task.

## 16. Tài liệu chính thức

- **Gradle — Building Java & JVM Projects:** SourceSet, source directories, classpaths, resources và custom integration test setup: https://docs.gradle.org/current/userguide/building_java_projects.html
- **Gradle — Java Plugin:** danh sách task, layout mặc định và các properties của source set: https://docs.gradle.org/current/userguide/java_plugin.html
- **Gradle — SourceSet DSL:** `java`, `resources`, `allJava`, `allSource`, `compileClasspath`, `runtimeClasspath`: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html
- **Gradle — SourceDirectorySet DSL:** `srcDir`, `srcDirs`, `include`, `exclude`: https://docs.gradle.org/current/dsl/org.gradle.api.file.SourceDirectorySet.html
- **Gradle — SourceSetOutput API:** `classesDirs`, `resourcesDir`, `output.dir` và generated resources: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/SourceSetOutput.html
- **Gradle — Java Testing:** cấu hình SourceSet `integrationTest`, custom `Test`, `testClassesDirs`/`classpath`: https://docs.gradle.org/current/userguide/java_testing.html
- **Gradle — Working With Files:** resource copying, filters, reproducibility và lazy file wiring: https://docs.gradle.org/current/userguide/working_with_files.html
- **Gradle — ProcessResources DSL:** `filesMatching`, `expand`, `filteringCharset`: https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html
- **Gradle — Creating Dependency Configurations:** scopes `implementation`/`runtimeOnly`, resolvable classpaths: https://docs.gradle.org/current/userguide/declaring_configurations.html
- **Gradle — JVM Test Suite Plugin:** giải pháp khác cho nhiều test suites: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- **Gradle — Gradle 8 migration:** `classesDirs` không tự kéo `processResources` như trước: https://docs.gradle.org/current/userguide/upgrading_version_7.html

**Kết luận:** SourceSet mô hình hóa **một nhóm code và resources cùng compile/runtime context**, không phải chỉ một folder. Khi muốn bổ sung nguồn, dùng `srcDir()`; khi muốn thay toàn bộ roots, dùng `srcDirs = [...]`. Resources phải được xử lý và đọc từ classpath, không từ source path. Phân biệt rõ **compileClasspath**, **runtimeClasspath**, **SourceSet.output** và **output.classesDirs**; tạo SourceSet mới chỉ khi bạn thực sự cần classpath/tasks/vòng đời riêng. Với file được tạo tự động, nối producer task output để Gradle đảm bảo build đúng thứ tự và tái lập được.