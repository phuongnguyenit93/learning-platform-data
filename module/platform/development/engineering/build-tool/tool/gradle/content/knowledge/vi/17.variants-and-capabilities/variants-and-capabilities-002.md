# Consumable configuration và resolvable configuration trong Gradle

## 1. Đặt đúng câu hỏi: project đang cần “nhận” hay “cung cấp” artifact?

Một `Configuration` của Gradle không đơn giản là một danh sách JAR. Nó là một phần của **mô hình quản lý dependency và variant**, giúp Gradle biết:

- **Khai báo dependency nào** mà project muốn sử dụng?
- **Giải quyết dependency thành file/artifact cụ thể** cho compile, runtime hoặc một task?
- **Công bố artifact/variant nào** để project khác lựa chọn khi phụ thuộc vào project này?

Hai vai trò của đề bài là:

- **Resolvable configuration**: phía *consumer*; Gradle có quyền **resolve** dependency graph thành một tập file/artifact phù hợp với nhu cầu của consumer.
- **Consumable configuration**: phía *producer*; project **công bố một variant**, thường kèm artifact, metadata, dependencies, attributes và capability, cho project khác lựa chọn.

Trong Gradle hiện đại còn có một vai trò thiết yếu thứ ba:

- **Declarable configuration** (*dependency scope*): là **bucket để khai báo dependency** nhưng bản thân không trực tiếp resolve hay công bố variant. Ví dụ `implementation`, `api` (với `java-library`), `testImplementation`.

**Tư duy đúng:** **declarable → resolvable → consumable variant của project/module phụ thuộc**. Bên consumer chọn variant mà bên producer chào bán theo attributes/capabilities, chứ không nhất thiết chọn theo *tên configuration* giống nhau.

Ví dụ `:app` khai báo `implementation(project(":lib"))`: Gradle dùng `compileClasspath` hoặc `runtimeClasspath` của `:app` để resolve. Bên `:lib`, plugin `java-library` có thể công bố `apiElements` và `runtimeElements`. Gradle sẽ chọn variant thích hợp qua thuộc tính, không yêu cầu `:app` gọi `configurations.getByName("runtimeElements").resolve()` trên project khác.

## 2. Ba vai trò configuration và các flags tương ứng

Các thuộc tính cốt lõi của `Configuration`:

- `canBeDeclared`: có được dùng làm nơi **khai báo dependency** hay không?
- `canBeResolved`: có được **resolve dependency graph** thành files/artifacts không?
- `canBeConsumed`: có được **công bố/tiêu thụ bởi project khác** như một outgoing variant không?

| Vai trò | `canBeDeclared` | `canBeResolved` | `canBeConsumed` | Ví dụ |
| --- | --- | --- | --- | --- |
| Declarable / dependency scope | `true` | `false` | `false` | `implementation`, `testImplementation` |
| Resolvable / consumer | `false` | `true` | `false` | `compileClasspath`, `runtimeClasspath` |
| Consumable / producer | `false` | `false` | `true` | `apiElements`, `runtimeElements` |
| Mixed roles kiểu cũ | Có thể nhiều cờ `true` | Có thể nhiều cờ `true` | Có thể nhiều cờ `true` | Tránh thiết kế mới dạng này |

Cơ chế cũ của Gradle từng cho phép configuration đa vai trò, nhưng **best practice hiện nay là một configuration giữ một vai trò rõ ràng**. Điều này giúp tránh resolve nhầm nơi, công bố nhầm classpath nội bộ hoặc tạo ambiguous variant.

### Đọc cú pháp trong Groovy và Kotlin

**Kotlin DSL — các thuộc tính trên Configuration đã có:**

```kotlin
configurations.named("runtimeClasspath") {
    // Kotlin DSL property từ các Java boolean getters:
    isCanBeResolved = true
    isCanBeConsumed = false
    isCanBeDeclared = false
}
```

**Groovy DSL — cùng ý nghĩa:**

```groovy
configurations.named('runtimeClasspath') {
    canBeResolved = true
    canBeConsumed = false
    canBeDeclared = false
}
```

Các đoạn này **chỉ minh họa tên property** của một configuration có vai trò đã xác lập. **Không cần và không nên sửa cờ của configuration do Java plugin tạo** trong build bình thường. Hãy dùng API factory tương ứng khi bạn tự tạo configuration mới.

Một số API/cờ đã thay đổi theo đời Gradle; hãy đối chiếu phiên bản **Gradle Wrapper** của dự án khi dùng cú pháp mới.

## 3. Configuration không phải repository, task hay bản thân artifact

| Đối tượng | Vai trò |
| --- | --- |
| `Configuration` | Gom dependency/attributes/variants và quy định vai trò khai báo, resolve hoặc công bố. |
| `Dependency` | Một quan hệ “tôi cần module/project/file này”, ví dụ `project(":lib")` hoặc `org.example:tool:1.0`. |
| `Repository` | Nguồn Gradle tìm metadata và file của external modules, ví dụ Maven Central. |
| `Task` | Thực hiện công việc như compile, đóng JAR hoặc sinh ZIP. |
| `Outgoing artifact` | File do producer cung cấp cùng một consumable variant. |
| `Attribute` | Thuộc tính mô tả nhu cầu/khả năng của variant, như `org.gradle.usage=java-runtime`. |
| `Capability` | Danh tính chức năng/thành phần mà variant cung cấp, dùng để chọn hoặc giải quyết các nhà cung cấp cạnh tranh. |

Một **resolvable configuration** tự nó không tải file cho đến khi một thao tác cần resolution xảy ra. Một **consumable configuration** không có nghĩa Gradle lập tức upload JAR lên Maven: nó chỉ công bố outgoing variant cho hệ thống dependency resolution; việc **publish ra repository ngoài** cần plugin/cấu hình phát hành phù hợp.

## 4. Dùng Java plugin để thấy ba vai trò trong thực tế

Plugin `java-library` tạo sẵn mô hình tương đối đầy đủ, nên hầu hết dự án Java **không cần tự tạo** `apiElements`, `runtimeElements` hay `compileClasspath`.

| Configuration của Java/Java Library | Vai trò | Ý nghĩa chính |
| --- | --- | --- |
| `api` (java-library) | Declarable | Thư viện cần cho public API được công bố tới consumer khi thích hợp. |
| `implementation` | Declarable | Thư viện dùng trong implementation nội bộ. |
| `runtimeOnly` | Declarable | Phần phụ thuộc chỉ cần lúc chạy. |
| `testImplementation` | Declarable | Phần phụ thuộc cho test code. |
| `compileClasspath` | Resolvable | Tập artifact Gradle cần cho biên dịch Java. |
| `runtimeClasspath` | Resolvable | Tập artifact cần tại runtime. |
| `testCompileClasspath` | Resolvable | Classpath biên dịch test. |
| `testRuntimeClasspath` | Resolvable | Classpath chạy test. |
| `apiElements` (java-library) | Consumable | Variant API mà consumer có thể dùng để compile. |
| `runtimeElements` | Consumable | Variant runtime mà consumer có thể dùng khi chạy. |

Đừng hiểu “`runtimeElements` chứa mọi file mà project tự dùng ở runtime”. Nó là **outgoing variant** thuộc project producer. Phía project cần chạy mã dùng `runtimeClasspath` của **chính mình** để giải quyết dependencies và nhận variant tương thích từ producer.

### 4.1. Hình dung hai phía

```text
Project :app (consumer)                     Project :lib (producer)
┌─────────────────────────┐                ┌──────────────────────────┐
│ dependencies            │                │ dependencies             │
│ implementation(:lib)    │                │ api, implementation      │
│     [declarable]        │                │      [declarable]        │
│           │             │                │            │             │
│  compileClasspath      │  --select----> │ apiElements              │
│     [resolvable]        │   attributes   │      [consumable]        │
│           │             │                │                          │
│   Java compiler        │                │ runtimeElements          │
│                        │  --select----> │      [consumable]        │
│  runtimeClasspath      │   attributes   │                          │
│     [resolvable]        │                │ outputs của :lib         │
└─────────────────────────┘                └──────────────────────────┘
```

Đây là mô hình giải thích. Trong Gradle thực tế có thể có **secondary variants** như thư mục class thay vì JAR, variant bổ sung do plugin tạo, và nhiều bước metadata/attribute matching. Không nên khẳng định mỗi lần compile đều bắt buộc tạo file `lib.jar`.

## 5. Làm thế nào resolvable configuration chọn consumable variant?

Gradle áp dụng **variant-aware dependency resolution**. Một *consumer* có những attributes yêu cầu, còn mỗi *producer variant* công bố một tập attributes/capabilities. Gradle tìm những variant **tương thích**, sau đó dùng các quy tắc lựa chọn/disambiguation khi có nhiều ứng viên.

Các attributes của hệ sinh thái JVM thường gặp:

| Attribute | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Consumer cần API cho compile hay runtime. |
| `org.gradle.category` | `library`, `documentation`, `platform` | Loại thành phần. |
| `org.gradle.libraryelements` | `jar`, `classes` | Hình thức artifact thư viện. |
| `org.gradle.dependency.bundling` | `external`, `embedded` | Cách các dependency được đóng gói/sử dụng. |
| `org.gradle.jvm.version` | `17` | Mức Java compatibility của variant. |
| Custom attribute | `com.example.artifact.kind=report` | Phân biệt artifact chuyên biệt do team quy định. |

**Hai điểm cần tránh nhầm:**

1. **Tên configuration không phải quy tắc matching chính.** `runtimeClasspath` ở consumer không nhất thiết khớp “theo tên” với `runtimeElements`. Gradle chọn theo attributes/capability và quy tắc của ecosystem.
2. **Thuộc tính không chỉ so sánh chuỗi tuyệt đối.** Một số thuộc tính có quy tắc tương thích và ưu tiên, chẳng hạn các semantics của `Usage` trong hệ sinh thái Java. Đối với custom attribute kiểu String chưa định nghĩa rules, có thể coi một giá trị khác là không tương thích; muốn fallback phải khai báo rule phù hợp.

Với một module có hai variant `apiElements` và `runtimeElements`, compile thường yêu cầu `java-api` còn runtime yêu cầu `java-runtime`. Gradle dùng metadata của producer và yêu cầu của consumer để chọn.

### 5.1. Capability khác attribute

Attribute mô tả *đặc tính variant*, còn capability giúp biểu diễn *chức năng được cung cấp*. Một module thường có default capability dựa trên group/name/version. Variant cũng có thể khai báo capability thêm để biểu diễn tính năng, hoặc tránh chọn đồng thời hai implementation cạnh tranh.

**Không phải mỗi consumable configuration có một capability độc lập tự động.** Các variant cùng component thường chia sẻ default capability. Nếu có nhiều outgoing variant cùng attributes và capabilities, Gradle có thể không phân biệt được. Hãy thiết kế variant riêng có attributes có ý nghĩa, hoặc capability riêng khi chức năng thực sự khác.

## 6. Tạo configuration theo vai trò bằng factory API

Trong những phiên bản Gradle mới, `ConfigurationContainer` có các factory theo vai trò:

- `configurations.dependencyScope("...")` tạo **declarable** configuration.
- `configurations.resolvable("...")` tạo **resolvable** configuration.
- `configurations.consumable("...")` tạo **consumable** configuration.

Các factory này được tài liệu Gradle ghi là **incubating APIs** tại thời điểm viết, nên phải kiểm tra version Wrapper trước khi sử dụng trong build/plugin cần hỗ trợ nhiều phiên bản.

**Kotlin DSL — minh họa một bộ configuration tùy biến:**

```kotlin
val reportDependencies =
    configurations.dependencyScope("reportDependencies")

val reportFiles = configurations.resolvable("reportFiles") {
    extendsFrom(reportDependencies.get())
}

configurations.consumable("reportElements")
```

**Groovy DSL:**

```groovy
def reportDependencies =
    configurations.dependencyScope('reportDependencies')

def reportFiles = configurations.resolvable('reportFiles') {
    extendsFrom(reportDependencies.get())
}

configurations.consumable('reportElements')
```

Ở đây cả ba tên thuộc project hiện tại và **chỉ biểu diễn role**, chưa đủ để một quy trình share file hoạt động. Một resolvable configuration cần dependencies/attributes phù hợp; một consumable configuration cần **attributes và outgoing artifact** phù hợp. Phần thực hành bên dưới sẽ bổ sung đủ các thành phần.

### 6.1. Vì sao dùng extendsFrom?

`extendsFrom` làm một configuration **thừa hưởng dependency declarations** và một số thông tin của configuration được kế thừa. Trong ví dụ:

```text
reportDependencies (declarable)
       |
       | extendsFrom — đọc từ góc nhìn reportFiles
       v
reportFiles (resolvable)
       |
       +-- resolve thành các artifacts/files
```

`extendsFrom` không làm hai configuration thành **cùng một** và **không tự sao chép attribute yêu cầu** của consumer. Nó cũng không thay thế việc công bố artifact ở producer. Bạn phải định nghĩa nhiệm vụ/ràng buộc rõ ràng cho từng phía.

Một sai lầm thường gặp là gọi `reportDependencies.resolve()`: đây là declarable configuration, không có vai trò resolve. Hãy dùng resolvable configuration `reportFiles` sau khi nó đã kế thừa dependency declarations.

### 6.2. Dùng API cũ khi cần tương thích

Với Gradle version không có factory theo vai trò, có thể đăng ký configuration rồi **chỉ rõ các cờ**, ví dụ:

**Kotlin:**

```kotlin
val reportFiles = configurations.register("reportFiles") {
    isCanBeResolved = true
    isCanBeConsumed = false
    isCanBeDeclared = false
}
```

**Groovy:**

```groovy
def reportFiles = configurations.register('reportFiles') {
    canBeResolved = true
    canBeConsumed = false
    canBeDeclared = false
}
```

Các đoạn trên là ví dụ **định nghĩa role**, chưa đủ để resolve một project dependency. Phải cấu hình dependencies, attributes, và producer variants như những phần kế tiếp.

**Không dùng `configurations.create("runtimeElements")` khi plugin `java-library` đã tạo configuration cùng tên.** Đừng tự đăng ký trùng; dùng `configurations.named("runtimeElements")` để cấu hình thêm nếu thật sự cần.

## 7. Ví dụ đầy đủ thứ nhất: Java 17 library và application

Ví dụ này minh họa Gradle tự tạo các configuration tiêu chuẩn. Nó chạy bằng core plugins, không cần Maven Central hay dependency ngoài.

### 7.1. Cấu trúc

```text
java-variants-lab/
├── settings.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/Greeter.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/Main.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "java-variants-lab"
include(":lib", ":app")
```

**`lib/build.gradle.kts`:**

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

**`lib/src/main/java/demo/Greeter.java`:**

```java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting() {
        return "Hello from lib";
    }
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation(project(":lib"))
}
```

**`app/src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greeting());
    }
}
```

### 7.2. Chạy và đối chiếu

Dùng Gradle Wrapper của project và JDK/toolchain tương thích Java 17. Nếu project mới chưa có Wrapper nhưng đã cài Gradle, chạy `gradle wrapper` ở root một lần để tạo Wrapper.

```bash
./gradlew :lib:outgoingVariants --variant apiElements
./gradlew :lib:outgoingVariants --variant runtimeElements
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew -q :app:run
```

Windows dùng `gradlew.bat`. Với `:app:run`, **stdout của chương trình Java**:

```text
Hello from lib
```

### 7.3. Từng lệnh chứng minh điều gì?

- `:lib:outgoingVariants --variant apiElements` cho thấy **variant API** mà `:lib` cung cấp, gồm các attributes như `org.gradle.usage=java-api`, capabilities và artifacts.
- `:lib:outgoingVariants --variant runtimeElements` cho thấy **variant runtime** của producer. Attributes thường bao gồm `java-runtime` và mức JVM compatibility.
- `:app:resolvableConfigurations --configuration compileClasspath` cho thấy **resolvable configuration** của app và attributes yêu cầu.
- `:app:resolvableConfigurations --configuration runtimeClasspath` làm tương tự cho runtime.
- `:app:dependencies --configuration runtimeClasspath` cho biết dependency graph, trong đó `:lib` là project dependency.
- `:app:run` thực thi ứng dụng; Gradle chọn artifact/variant phù hợp và đảm bảo task producer cần thiết được chạy.

**Không cần tự gọi `:lib:jar` trong build script của app**: project dependency và variant model giúp Gradle nối các producer tasks phù hợp. Ở một số trường hợp compile có thể tiêu thụ **classes directory secondary variant** thay vì JAR; điều này không làm thay đổi vai trò `apiElements` như một outgoing variant.

### 7.4. Phiên bản Groovy DSL tương đương

Thay file settings bằng `settings.gradle`:

```groovy
rootProject.name = 'java-variants-lab'
include 'lib', 'app'
```

Thay `lib/build.gradle.kts` bằng `lib/build.gradle`:

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

Thay `app/build.gradle.kts` bằng `app/build.gradle`:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    implementation project(':lib')
}
```

Hai file Java **giữ nguyên**. Chỉ dùng một phiên bản Gradle DSL cho từng build script trong bài tập, không ghép hai khối `plugins` của Groovy và Kotlin vào cùng file.

## 8. Ví dụ đầy đủ thứ hai: custom consumable ZIP → resolvable configuration

Phần này cho thấy **tự tạo** một artifact variant, thay vì dùng mô hình Java plugin có sẵn.

Bài tập có hai project:

- `:producer` cung cấp một file ZIP chứa `report.txt` trên **consumable configuration** `reportElements`.
- `:consumer` khai báo project dependency vào **declarable** `reportDependencies`, rồi resolve bằng **resolvable** `reportFiles` và đọc ZIP.

Để chọn đúng variant, cả producer và consumer dùng một custom attribute `com.example.artifact.kind` có giá trị `report`. Vì chỉ có một consumable configuration trong producer demo, quy tắc matching khá đơn giản. Đây là ví dụ thực hành trên Gradle hiện đại có hỗ trợ factory `dependencyScope`, `resolvable`, `consumable`.

### 8.1. Cấu trúc và file nguồn

```text
roles-lab/
├── settings.gradle.kts
├── producer/
│   ├── build.gradle.kts
│   └── report.txt
└── consumer/
    └── build.gradle.kts
```

`producer/report.txt` chứa đúng một dòng:

```text
REPORT_OK
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "roles-lab"
include(":producer", ":consumer")
```

### 8.2. Producer Kotlin DSL — đăng ký task và công bố variant

`producer/build.gradle.kts`:

```kotlin
import org.gradle.api.attributes.Attribute
import org.gradle.api.tasks.bundling.Zip

val reportKind =
    Attribute.of("com.example.artifact.kind", String::class.java)

// Task tạo ZIP từ report.txt thuộc chính project producer.
val reportBundle = tasks.register<Zip>("reportBundle") {
    archiveFileName.set("report.zip")
    destinationDirectory.set(layout.buildDirectory.dir("bundles"))
    from(layout.projectDirectory.file("report.txt"))
}

// Outgoing variant cho project khác sử dụng.
configurations.consumable("reportElements") {
    attributes {
        attribute(reportKind, "report")
    }
}

// Gắn artifact của task Zip vào consumable configuration.
artifacts {
    add("reportElements", reportBundle)
}
```

**Giải thích:**

1. `reportBundle` là `TaskProvider<Zip>`. Nó tạo `build/bundles/report.zip` khi được yêu cầu.
2. `configurations.consumable("reportElements")` công bố một variant, không dùng để resolve file ở chính producer.
3. `attribute(reportKind, "report")` cho biết variant đại diện cho loại artifact `report`.
4. `artifacts.add("reportElements", reportBundle)` gắn output của task Zip vào outgoing variant, để Gradle biết task sản xuất artifact khi consumer cần nó. Đây không phải lệnh publish lên Maven Central.
5. Vì không áp dụng `java-library` trong project producer của demo, nó không phát sinh thêm các variant Java như `apiElements` và `runtimeElements` gây khó phân biệt cho bài tập.

### 8.3. Consumer Kotlin DSL — khai báo và resolve

`consumer/build.gradle.kts`:

```kotlin
import org.gradle.api.attributes.Attribute
import java.util.zip.ZipFile

val reportKind =
    Attribute.of("com.example.artifact.kind", String::class.java)

// Nơi chỉ khai báo dependency.
val reportDependencies =
    configurations.dependencyScope("reportDependencies")

// Nơi thật sự resolve dependency thành file.
val reportFiles = configurations.resolvable("reportFiles") {
    extendsFrom(reportDependencies.get())

    attributes {
        attribute(reportKind, "report")
    }
}

// Project dependency nằm ở dependency scope; không add trực tiếp vào
// outgoing configuration của producer.
dependencies {
    add("reportDependencies", project(":producer"))
}

// Chỉ đọc ZIP ở execution time sau khi Gradle resolve artifacts.
tasks.register("showReport") {
    val incoming = reportFiles.get()
    inputs.files(incoming)

    doLast {
        val archive = incoming.singleFile
        ZipFile(archive).use { zip ->
            val entry = zip.getEntry("report.txt")
                ?: error("Missing report.txt")
            val content = zip.getInputStream(entry)
                .bufferedReader(Charsets.UTF_8)
                .use { it.readText().trim() }

            println("Report: $content")
        }
    }
}
```

**Giải thích:**

1. `reportDependencies` đóng vai trò **declarable**: tập hợp project dependency `:producer`.
2. `reportFiles` đóng vai trò **resolvable**; `extendsFrom(reportDependencies.get())` khiến nó nhận dependency declarations từ bucket.
3. `reportFiles` yêu cầu attribute `com.example.artifact.kind=report`. Gradle chọn outgoing variant của `:producer` có attribute tương thích.
4. `inputs.files(incoming)` khai báo file đầu vào cho task và giữ thông tin dependency gắn với outgoing artifact. Gradle nhận biết task `:producer:reportBundle` cần chạy trước khi consumer dùng ZIP.
5. `ZipFile` là API JDK. Đoạn thực thi đọc mục `report.txt` từ ZIP và in nội dung; không phụ thuộc thư viện Java tải từ mạng.

**Lưu ý về configuration cache:** ví dụ dùng `doLast` đơn giản để minh họa quy trình, chưa phải custom task type chuẩn hóa cho dự án production. Với build lớn cần configuration cache và build cache nghiêm ngặt, nên tạo task class có `@InputFile`, `RegularFileProperty`, `@TaskAction` rồi nối input từ output/provider của producer.

### 8.4. Chạy và kết quả

Từ `roles-lab` có Wrapper:

```bash
./gradlew :producer:outgoingVariants --variant reportElements
./gradlew :consumer:resolvableConfigurations --configuration reportFiles
./gradlew :consumer:dependencies --configuration reportFiles
./gradlew -q :consumer:showReport
```

Stdout từ action `showReport`:

```text
Report: REPORT_OK
```

Artifact được ghi ở `producer/build/bundles/report.zip` theo mặc định. Một consumer **không cần tự biết đường dẫn** đó trong build script: nó yêu cầu project `:producer` và variant `report`; Gradle dùng artifact metadata của producer.

Có thể xác nhận nội dung ZIP bằng một chương trình unzip ngoài nếu muốn, nhưng bài học không phụ thuộc hệ điều hành có sẵn lệnh `unzip`.

### 8.5. Tương đương Groovy DSL

Dùng **`settings.gradle`** (thay thế settings Kotlin):

```groovy
rootProject.name = 'roles-lab'
include 'producer', 'consumer'
```

**`producer/build.gradle`:**

```groovy
import org.gradle.api.attributes.Attribute
import org.gradle.api.tasks.bundling.Zip

def reportKind = Attribute.of('com.example.artifact.kind', String)

def reportBundle = tasks.register('reportBundle', Zip) {
    archiveFileName.set('report.zip')
    destinationDirectory.set(layout.buildDirectory.dir('bundles'))
    from(layout.projectDirectory.file('report.txt'))
}

configurations.consumable('reportElements') {
    attributes {
        attribute(reportKind, 'report')
    }
}

artifacts {
    add('reportElements', reportBundle)
}
```

**`consumer/build.gradle`:**

```groovy
import org.gradle.api.attributes.Attribute
import java.util.zip.ZipFile

def reportKind = Attribute.of('com.example.artifact.kind', String)

def reportDependencies =
    configurations.dependencyScope('reportDependencies')

def reportFiles = configurations.resolvable('reportFiles') {
    extendsFrom(reportDependencies.get())
    attributes {
        attribute(reportKind, 'report')
    }
}

dependencies {
    add('reportDependencies', project(':producer'))
}

tasks.register('showReport') {
    def incoming = reportFiles.get()
    inputs.files(incoming)

    doLast {
        def zip = new ZipFile(incoming.singleFile)
        try {
            def entry = zip.getEntry('report.txt')
            if (entry == null) {
                throw new GradleException('Missing report.txt')
            }
            def content = zip.getInputStream(entry)
                .getText('UTF-8').trim()
            println "Report: $content"
        } finally {
            zip.close()
        }
    }
}
```

File `report.txt` không đổi. Kết quả tác vụ Groovy cũng là `Report: REPORT_OK`. Hãy dùng **một** cặp settings/build script theo DSL đã chọn để tránh xung đột khi thực hành.

## 9. Producer có thể công bố nhiều variants

Trong thư viện Java, `apiElements` và `runtimeElements` là ví dụ có sẵn về nhiều variants của cùng một component. Một project tùy biến cũng có thể cung cấp:

- ZIP chứa báo cáo dạng thô.
- ZIP báo cáo đã chuẩn hóa.
- JAR dành cho runtime Java 17.
- Một variant có tính năng bổ sung và capability riêng.

Mỗi consumable configuration cần được thiết kế với **attributes khác biệt có ý nghĩa**, và khi thích hợp **capabilities** để consumer có thể chọn đúng sản phẩm. Không đăng ký hai consumable variants cùng attribute set và capability mà không có cách phân biệt; Gradle có thể báo lỗi/ambiguous matching.

**Không lạm dụng “thêm một configuration = thêm một variant có thể tìm thấy”.** Nếu chưa gắn artifact hoặc metadata/attributes phù hợp, consumer có thể không có artifact hữu ích để lấy, hoặc không tìm được matching variant.

### 9.1. Thay đổi thử attribute để quan sát lỗi

Trong ví dụ `roles-lab`, nếu bạn chỉ đổi consumer:

```kotlin
// Trong consumer/reportFiles attributes (thay cho "report"):
attribute(reportKind, "something-else")
```

nhưng producer vẫn công bố `"report"`, việc resolve `reportFiles` sẽ không tìm được outgoing variant khớp theo custom attribute như dự kiến. Bạn có thể thấy thông báo kiểu **No matching variant of project :producer** hoặc mô tả attributes không tương thích. Đây là bài thử lỗi, **không phải cấu hình đúng**. Hãy đổi về `"report"` sau khi quan sát.

### 9.2. Không dùng targetConfiguration như thiết kế mặc định

Trong build cũ có thể thấy ý định ép consumer chọn configuration theo tên, ví dụ target configuration của dependency. Cách đó đi ngược tinh thần variant-aware matching và dễ làm mất compatibility rules/metadata. Với custom artifacts, ưu tiên khai báo attributes/capability có ý nghĩa hai phía thay vì buộc consumer biết tên một configuration nội bộ.

## 10. Consumable không đồng nghĩa “tải được như FileCollection”

Sai lầm thường gặp là muốn lấy artifact của chính project bằng cách gọi `files`/`resolve` trên consumable configuration:

```kotlin
// Mã minh họa lỗi về vai trò; không chạy:
val outgoing = configurations.named("reportElements").get()
val files = outgoing.resolve() // reportElements không resolvable
```

`reportElements` dùng để công bố artifact; muốn kiểm tra nó, xem `outgoingVariants` hoặc `outgoing.artifacts`. Nếu muốn task cùng project dùng file đã tạo, thông thường hãy truyền **output property/TaskProvider của task producer** thay vì bắt một consumable configuration tự resolve.

Ngược lại:

```kotlin
// Mã minh họa lỗi về vai trò; không chạy:
val incoming = configurations.named("reportFiles").get()
incoming.outgoing.artifact("output.zip") // Không nên dùng resolvable làm outgoing variant.
```

`reportFiles` tồn tại để nhận dependency graph và resolution. Nếu muốn cung cấp output cho project khác, hãy tạo **một consumable configuration riêng**.

## 11. Declarable cũng không nên resolve trực tiếp

Ví dụ Java:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Ở đây `implementation` chỉ là bucket khai báo. Nếu bạn cố gọi:

```kotlin
// Không phải cách đúng; chỉ minh họa lỗi:
val files = configurations.getByName("implementation").resolve()
```

Gradle sẽ phản đối vì `implementation` được thiết kế **không resolvable**. Để lấy classpath, xem `compileClasspath` hoặc `runtimeClasspath` của project. Việc `implementation` không resolvable **không có nghĩa** Java plugin “không dùng dependency”: các resolvable configurations đã được nối `extendsFrom` để tập hợp dependency.

`dependencies { implementation(...) }` và `configurations { implementation { ... } }` cũng có ý nghĩa khác nhau: một bên **khai báo dependency** vào configuration, bên kia **cấu hình chính đối tượng Configuration**.

## 12. Thời điểm resolution và ảnh hưởng đến hiệu năng

Khi build script chạy giai đoạn configuration, nên tránh **resolve toàn bộ classpath ngay lập tức** chỉ để kiểm tra một filename:

```kotlin
// Không khuyến nghị ở cấp build script:
val jars = configurations.getByName("runtimeClasspath").files
```

Truy cập `files` có thể kích hoạt dependency resolution ngay trong giai đoạn cấu hình. Điều này khiến Gradle phải tải metadata/artifact quá sớm, tăng thời gian cấu hình và có thể ảnh hưởng configuration cache.

Thực hành tốt hơn:

- Giữ `TaskProvider` và `Configuration`/`FileCollection` như giá trị cấu hình cho task.
- Khai báo input/output chính xác; Gradle resolve khi task cần.
- Với custom task production, dùng `ConfigurableFileCollection`, `@Classpath` hoặc `@InputFiles`, và provider/task wiring thay vì `.files` ở cấp script.
- Không làm `configurations.all { ... }` chỉ để áp cùng thay đổi; dùng `configurations.configureEach { ... }` hoặc `configurations.named("...")`.
- Không lạm dụng `getByName` để ép hiện thực hóa mọi configuration khi chỉ cần đăng ký configuration action.

**Phân biệt hai mức lazy:** *configuration realization* là tạo/cấu hình đối tượng Configuration; *dependency resolution* là tính graph/đọc metadata, thường tốn mạng và có thể tải artifacts. Một `Configuration` đã được realized chưa chắc đã resolve dependency.

## 13. Repository và dependency graph: cái gì có và cái gì không?

Một resolvable configuration có thể chứa:

- External module dependencies như `"org.apache.commons:commons-lang3:3.17.0"`, cần repository thích hợp.
- Project dependency như `project(":producer")`, dùng outgoing variants của project đó.
- Local file dependency, dùng FileCollection, không đi qua Maven repository theo nghĩa module resolution.

**Consumable configuration của project không tự cần Maven repository để một project khác trong cùng build chọn variant.** Với bài `roles-lab`, project dependency và ZIP đều ở local build; không cần `mavenCentral()`.

Ngược lại, nếu khai báo external module trong declarable scope, một resolvable configuration kế thừa scope đó sẽ cần kho chứa module khi Gradle thực hiện resolution. **Plugin repositories** phục vụ một nhu cầu khác, không tự bổ sung kho cho external module dependencies.

## 14. Công cụ chẩn đoán configuration và variant

Các task báo cáo hữu ích trong Gradle:

```bash
# Danh sách variant mà project producer công bố:
./gradlew :producer:outgoingVariants
./gradlew :producer:outgoingVariants --variant reportElements

# Danh sách resolvable configurations ở consumer:
./gradlew :consumer:resolvableConfigurations
./gradlew :consumer:resolvableConfigurations --configuration reportFiles

# Dependency graph trên resolvable configuration:
./gradlew :consumer:dependencies --configuration reportFiles

# Với Java app/lib:
./gradlew :lib:outgoingVariants --variant apiElements
./gradlew :lib:outgoingVariants --variant runtimeElements
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
```

Chạy nhóm lệnh phù hợp với **bài tập tương ứng**: project `producer/consumer` thuộc `roles-lab`; project `lib/app` thuộc `java-variants-lab`. Không yêu cầu cả bốn project cùng tồn tại trong một build.

### 14.1. Đọc output outgoingVariants

Báo cáo có thể hiện các mục:

- **Variant name**: ví dụ `runtimeElements` hoặc `reportElements`.
- **Capabilities**: default capability và capability thêm nếu có.
- **Attributes**: nhu cầu mà variant đáp ứng, như `org.gradle.usage`.
- **Artifacts**: JAR/ZIP hoặc đường dẫn output được công bố.
- **Secondary variants**: các hình thức artifact phụ mà Gradle cũng có thể chọn.

Nếu custom configuration không có attributes, Gradle có thể đánh dấu nó không phù hợp với variant-aware selection. Hãy khai báo ít nhất một attribute có ý nghĩa thay vì dựa vào lựa chọn “theo tên” kiểu cũ.

### 14.2. Đọc output resolvableConfigurations

Báo cáo có thể cho biết:

- Tên configuration được resolve (`compileClasspath`, `reportFiles`...).
- Attributes mà consumer yêu cầu.
- Parent/inherited configurations (`extendsFrom`).
- Description hoặc thông tin variant selection liên quan.

Không cần kỳ vọng một đoạn stdout cố định cho các lệnh báo cáo: cách trình bày phụ thuộc Gradle version và plugin. **Output chạy thực của hai ví dụ Java/ZIP** mới được đưa ra chính xác ở mục tương ứng.

### 14.3. Dùng dependencyInsight khi có xung đột

Với Java build có external module:

```bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Lệnh này chỉ hữu ích khi project `:app` thật sự có module `commons-lang3` trong configuration đang xét; với bài Java nhỏ ở mục 7 (chỉ có project dependency `:lib`), lệnh có thể không tìm thấy dependency đó. Trong dự án thực, thay bằng tên module cần điều tra.

## 15. Các lỗi phổ biến khi thiết kế cấu hình

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| `Resolving dependency configuration 'implementation' is not allowed` | Cố resolve configuration declarable. | Dùng `compileClasspath`/`runtimeClasspath` hoặc tự tạo resolvable configuration nối `extendsFrom`. |
| `Resolving dependency configuration 'reportElements' is not allowed` | Cố resolve consumable configuration. | Đây là outgoing variant; dùng `outgoingVariants` để xem, consumer dùng resolvable config. |
| Consumer báo **No matching variant** | Attributes/capabilities không tương thích, không có consumable variant hoặc artifact phù hợp. | So sánh `outgoingVariants` của producer với `resolvableConfigurations` của consumer. |
| **Cannot choose between variants** | Có nhiều variants cùng đáp ứng mà thiếu tiêu chí phân biệt. | Bổ sung thuộc tính/capabilities mang ý nghĩa thật; tránh duplicate variants. |
| Consumer thấy variant nhưng không có file | Quên `artifacts.add(...)` hoặc artifact provider cấu hình sai. | Kiểm tra phần Artifacts trong `outgoingVariants` và output producer task. |
| Task consumer đọc ZIP trước khi nó được tạo | Chỉ ghép đường dẫn file thủ công, không có task dependency. | Công bố artifact từ TaskProvider hoặc nối output Provider, khai báo input của task. |
| `Could not find ...` external module | Thiếu repository/module/version hoặc lỗi mạng. | Kiểm tra `repositories`, tọa độ, `dependencies` và credential. |
| `No matching variant ... JVM version` | Producer xây Java target không tương thích với JVM consumer. | Chỉnh Java toolchain/target đúng policy hoặc chọn variant phù hợp. |
| Gọi `dependencyScope(...)` bị lỗi cú pháp | Gradle Wrapper quá cũ không có factory tương ứng. | Xem version và dùng `configurations.register` + flags hợp lệ nếu cần. |
| `Cannot add a configuration with name ...` | Trùng tên configuration do plugin tự tạo. | Dùng `configurations.named(...)` cho configuration đã có; không tạo lần hai. |
| `implementation(project(":lib"))` nhưng compile không tìm class | Project path/Java source sai, variant không tương thích hoặc dependency khai sai scope. | Kiểm tra settings, `:lib:outgoingVariants`, compileClasspath và source path. |
| Mã build chậm do tải artifacts ở configuration | Truy cập `.files`/`resolve()` quá sớm. | Chuyển sang lazy task input/Provider và hạn chế eager resolution. |

## 16. Quy trình thiết kế một custom variant đúng

1. **Xác định artifact producer tạo ra:** JAR, ZIP, report JSON, schema hoặc tài nguyên nào?
2. **Đăng ký task producer** bằng `tasks.register` với output được quản lý rõ ràng.
3. **Tạo consumable configuration** bằng `configurations.consumable("...")`, chọn attributes/capabilities đại diện đúng artifact.
4. **Gắn outgoing artifact** thông qua task provider hoặc output được model hóa đúng, để giữ thông tin task dependency.
5. **Ở consumer, tạo declarable scope** qua `configurations.dependencyScope("...")`; khai báo dependency bằng `add("scopeName", project(":producer"))` hoặc API tương ứng.
6. **Tạo resolvable configuration** qua `configurations.resolvable("...")`, `extendsFrom` declarable scope và cấu hình attributes tương thích.
7. **Dùng configuration trong task input**; không resolve file ở configuration time nếu không thật cần.
8. **Chạy các báo cáo** `outgoingVariants`, `resolvableConfigurations` và `dependencies`; rồi chạy task thực tế.
9. **Thử âm bản** bằng cách đổi một attribute để quan sát lỗi matching, sau đó hoàn nguyên.
10. **Kiểm tra yêu cầu của build production:** cache/configuration cache, metadata publish, credentials, test variant compatibility, Java version và policy của tổ chức.

## 17. Tổng kết nhanh

| Câu hỏi | Trả lời |
| --- | --- |
| Muốn **khai báo** thư viện? | Declarable/dependency scope, ví dụ `implementation`. |
| Muốn **lấy classpath/tập artifacts**? | Resolvable configuration, ví dụ `runtimeClasspath`. |
| Muốn **cho project khác tiêu thụ artifact**? | Consumable configuration, ví dụ `runtimeElements` hoặc custom `reportElements`. |
| “Tên trùng nhau” có khiến Gradle chọn đúng artifact? | Không. Variant-aware selection chủ yếu dựa vào attributes/capabilities/rules, không chỉ tên. |
| `extendsFrom` có tạo artifact không? | Không. Nó truyền dependency declarations; artifact do producer cung cấp. |
| `consumable` có tự upload artifact lên Maven không? | Không. Publish ra repository ngoài là quy trình khác. |
| Có nên dùng cùng một configuration vừa resolve vừa consume? | Không cho thiết kế mới; tách vai trò rõ ràng. |
| Cách quan sát? | `outgoingVariants`, `resolvableConfigurations`, `dependencies`, và chạy task thực tế. |

**Cốt lõi:** `consumable` thuộc phía **cung cấp variant**, `resolvable` thuộc phía **lựa chọn và lấy artifact**, còn `declarable` thuộc phía **tập hợp dependency requests**. Khi ba vai trò tách bạch và attributes được thiết kế rõ ràng, Gradle có thể chọn đúng sản phẩm giữa các project, nối task producer/consumer và giải thích lỗi variant bằng các báo cáo có sẵn.

### Tài liệu chính thức của Gradle

- [Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html) — ba vai trò, flags và API `dependencyScope`/`resolvable`/`consumable`.
- [Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html) — matching, khả năng tương thích và xem variants.
- [Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html) — những attributes tiêu chuẩn và custom schema.
- [How to Share Artifacts Between Projects](https://docs.gradle.org/current/userguide/how_to_share_outputs_between_projects.html) — producer/consumer, outgoing artifact, attributes và project dependency.
- [Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html) — thiết kế configuration có attributes, tránh trộn vai trò.
- [Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — `api`/`implementation`, `apiElements`/`runtimeElements` trong JVM.
