# Dependency trực tiếp, bắc cầu, constraint và artifact trong Gradle

## 1. Mục tiêu và mô hình tổng quan

Khi khai báo `implementation("org.apache.httpcomponents:httpclient:4.5.13")`, Gradle không chỉ tải một tệp JAR. Nó cần đọc thông tin của module, theo các quan hệ dependency, chọn version phù hợp, áp dụng constraints, chọn variant theo classpath và cuối cùng cung cấp **artifacts** cho công việc biên dịch/chạy ứng dụng.

Bốn khái niệm quan trọng:

- **Dependency trực tiếp (direct)**: quan hệ được project của bạn khai báo trong `dependencies { }`, ví dụ `implementation("g:n:v")` hoặc `implementation(project(":lib"))`.
- **Dependency bắc cầu (transitive)**: dependency mà **một dependency khác** khai báo trong metadata, được đi theo khi Gradle resolve graph phù hợp.
- **Dependency constraint**: một **yêu cầu về version** của module; chỉ ảnh hưởng khi module đó đã có mặt trong graph. Constraint **không tự thêm** module hoặc JAR.
- **Artifact**: file/thư mục thực tế được cung cấp bởi một component/variant sau resolution, chẳng hạn `.jar`, `.zip` hoặc classes directory.

Bài tập trung vào sự khác biệt của bốn khái niệm này, cách chúng kết nối qua configuration/variant/metadata và cách tìm lý do Gradle chọn một version. Ví dụ sử dụng **Gradle Kotlin DSL**, Java 17+ và Gradle Wrapper.

## 2. Từ khai báo đến file classpath

Sơ đồ giả định: ứng dụng trực tiếp dùng A; A cần B, B cần C; ứng dụng bổ sung constraint cho C.

~~~text
Ứng dụng app
  |
  +-- A:1.0                  direct dependency
       |
       +-- B:2.0             transitive dependency
            |
            +-- C:1.0        transitive dependency

Constraint: C >= 1.5         không tự tạo cạnh gọi C
                              nhưng điều chỉnh C vì C đã có mặt

Sau conflict resolution:
  selected version của C có thể là 1.5 hoặc cao hơn
  (phụ thuộc các yêu cầu khác)

Sau variant/artifact resolution:
  A.jar, B.jar, C.jar ... là các file được chọn
~~~

Sơ đồ chỉ minh họa; không phải output từ một lần chạy thật. Mỗi **configuration** có một graph riêng. `compileClasspath` có thể khác `runtimeClasspath`; Gradle có thể chọn variant của project dependency cung cấp **classes directory** thay vì JAR. Do đó, danh sách file trong cache không phải mô hình dependency đầy đủ.

| Đối tượng | Ví dụ | Vai trò |
| --- | --- | --- |
| Dependency declaration | `implementation("g:n:1.0")` | Yêu cầu một component từ configuration. |
| Module coordinate | `commons-codec:commons-codec:1.15` | Danh tính group/name/version. |
| Metadata | `.module`, `pom.xml`, `ivy.xml` | Mô tả dependencies, versions, variants/artifacts. |
| Constraint | `constraints { implementation("g:n:1.5") }` | Điều kiện version, không tự thêm dependency. |
| Variant | `apiElements`, `runtimeElements` | Cách một component được tiêu thụ theo attributes. |
| Artifact | `library-1.0.jar` | File thực tế được giải quyết. |
| Resolvable configuration | `runtimeClasspath` | Graph và artifacts dành cho một nhu cầu tiêu thụ. |

Một module có thể xuất ra nhiều artifact/variant; một artifact không nhất thiết chứa thông tin về module bắc cầu. **Direct/transitive là quan hệ trong graph; artifact là kết quả vật lý.**

## 3. Dependency trực tiếp và các loại tọa độ

Với external module, ký hiệu thường dùng:

~~~text
group:name:version

org.apache.httpcomponents:httpclient:4.5.13
commons-codec:commons-codec:1.15
org.apache.commons:commons-lang3:3.14.0
~~~

Tạo dependency trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    compileOnly("org.jetbrains:annotations:24.1.0")
    runtimeOnly("ch.qos.logback:logback-classic:1.4.14")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}
~~~

Đây là mẫu minh họa **scope**; không chứa test/source nên không phải ứng dụng hoàn chỉnh. Version là mốc ví dụ, không mặc định là version mới nhất.

- `implementation`: dependency cần để triển khai ứng dụng, thường có trên compile và runtime classpath của project.
- `compileOnly`: có lúc biên dịch nhưng không tự có trong runtime graph.
- `runtimeOnly`: dùng khi chạy, không để source chính import API khi compile.
- `testImplementation`: dùng cho source set test, không mặc định vào artifact runtime sản phẩm.
- `api`: có khi áp dụng `java-library` plugin; dependency là một phần API công khai của thư viện và ảnh hưởng compile classpath của consumer.

**Một dòng khai báo không phải một version pin cứng.** Nếu `implementation("commons-codec:commons-codec:1.11")` nhưng graph có yêu cầu khác cần 1.15, Gradle có thể chọn 1.15. `1.11` là **requested version**, còn `1.15` có thể là **selected version**. Cách chọn cụ thể còn phụ thuộc constraints, version ranges, selection rules và metadata.

### Module, project và file dependency

Ba loại thường gặp:

~~~kotlin
dependencies {
    // External module dependency: có metadata từ repository.
    implementation("org.apache.commons:commons-lang3:3.14.0")

    // Project dependency: chỉ dùng khi :lib được include trong settings.
    // implementation(project(":lib"))

    // File dependency: chỉ hợp lệ nếu file thực sự tồn tại.
    // implementation(files("libs/local-helper.jar"))
}
~~~

Hai dòng comment cần điều kiện ngoài file này, nên **không bỏ dấu comment** nếu project chưa có `:lib` hoặc JAR. File dependency **không có transitive module metadata**; Gradle không tự suy ra những JAR khác mà local-helper cần. Project dependency lại có thể mang variant/task dependency và các transitive dependencies do project kia công bố.

## 4. Dependency bắc cầu đến từ metadata

Ví dụ ứng dụng chỉ khai báo:

~~~kotlin
dependencies {
    implementation("org.apache.httpcomponents:httpclient:4.5.13")
}
~~~

Module này được publish cùng metadata mô tả các thư viện cần thiết như `httpcore`, `commons-logging`, `commons-codec`. Khi resolve `runtimeClasspath`, Gradle có thể tạo cây rút gọn:

~~~text
runtimeClasspath
\--- org.apache.httpcomponents:httpclient:4.5.13
     +--- org.apache.httpcomponents:httpcore:4.4.x
     +--- commons-logging:commons-logging:1.2
     \--- commons-codec:commons-codec:1.11
~~~

Đây là sơ đồ **rút gọn**; version chính xác của các dependency phải xem bằng lệnh Gradle thật. Dòng `commons-codec` là transitive: app không viết nó nhưng metadata của `httpclient` yêu cầu nó. Một module có thể xuất hiện qua nhiều đường (A → C và B → C), không đồng nghĩa Gradle mặc nhiên đặt hai phiên bản C khác nhau trên classpath.

**Không dựa vào dependency bắc cầu làm API của mã nguồn ứng dụng.** Nếu Java của bạn trực tiếp import `org.apache.commons.codec.*`, hãy khai báo chính `commons-codec` là direct dependency. Nếu chỉ muốn quản lý version codec mà ứng dụng không dùng API của nó trực tiếp, constraint phù hợp hơn:

~~~kotlin
dependencies {
    // App trực tiếp gọi API HttpClient.
    implementation("org.apache.httpcomponents:httpclient:4.5.13")

    constraints {
        // Chỉ ảnh hưởng nếu commons-codec có mặt trong graph.
        implementation("commons-codec:commons-codec:1.15") {
            because("Tránh version codec bắc cầu cũ")
        }
    }
}
~~~

**Transitivity không có nghĩa bất kỳ dependency nào của thư viện đều đi vào mọi classpath**. Metadata, variant/attributes, scope, exclusions và yêu cầu consumer quyết định những quan hệ nào được tính khi resolve.

## 5. Ví dụ Java 17 chạy được: direct, transitive và constraint

Tạo một project đã có Gradle Wrapper, cấu trúc:

~~~text
dependency-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/example/App.java
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "dependency-lab"
~~~

`build.gradle.kts` (một file độc lập hoàn chỉnh):

~~~kotlin
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
    mainClass.set("example.App")
}

dependencies {
    // Direct dependency: code Java sử dụng HttpClient.
    implementation("org.apache.httpcomponents:httpclient:4.5.13")

    // Constraint cho module xuất hiện transitively.
    constraints {
        implementation("commons-codec:commons-codec:1.15") {
            because("Yêu cầu version bắc cầu đã được đánh giá")
        }
    }
}
~~~

`src/main/java/example/App.java`:

~~~java
package example;

import org.apache.http.client.HttpClient;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(HttpClient.class.getSimpleName());
    }
}
~~~

Chạy từ root:

~~~bash
./gradlew --version
./gradlew -q run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath
~~~

Khi project build và chạy thành công, stdout **của `main`** là:

~~~text
HttpClient
~~~

Đây là chương trình Java 17 biên dịch được thông qua Gradle Application plugin; không cần tạo kết nối HTTP để chạy ví dụ. Máy cần Gradle Wrapper, JDK/toolchain phù hợp và quyền truy cập `mavenCentral()`/cache dependency. `-q` giảm logging của Gradle; log environment hoặc tải toolchain có thể khác, nhưng câu lệnh `System.out.println` trên in một dòng như trên.

### Hiểu dependency report dự kiến

Vì metadata của `httpclient:4.5.13` yêu cầu codec cũ hơn, trong một graph không có ràng buộc khác, Gradle sẽ có xu hướng chọn version thỏa constraint `commons-codec:1.15`:

~~~text
runtimeClasspath
+--- org.apache.httpcomponents:httpclient:4.5.13
|    ...
|    \--- commons-codec:commons-codec:1.11 -> 1.15
\--- commons-codec:commons-codec:1.15 (c)
~~~

Đây là **minh họa đã lược bỏ nhánh**, không phải output đầy đủ được thu thực tế. Ý nghĩa ký hiệu:

- `1.11 -> 1.15`: một cạnh yêu cầu 1.11 nhưng selected version là 1.15.
- `(c)`: version constraint, **không phải một file JAR thứ hai**.
- `(*)` nếu xuất hiện: nhánh đã được trình bày ở nơi khác trong tree.
- Các đường dẫn chính xác và selection reasons phải kiểm tra `dependencyInsight`.

**Thí nghiệm quan trọng:** nếu loại bỏ direct dependency `httpclient` và không có thư viện nào khác đem codec vào graph, **giữ constraint codec cũng không thêm codec vào graph**. Đó là sự khác biệt cơ bản với một direct dependency.

## 6. Dependency constraint: giới hạn việc chọn version, không thêm module

Constraint dùng để yêu cầu một version/range của module đã hiện diện:

~~~kotlin
dependencies {
    implementation("org.apache.httpcomponents:httpclient:4.5.13")

    constraints {
        implementation("commons-codec:commons-codec:1.15") {
            because("Đã kiểm thử với codec 1.15 trở lên")
        }
    }
}
~~~

Cơ chế:

1. App yêu cầu `httpclient` trực tiếp.
2. Metadata của httpclient đưa `commons-codec` vào graph.
3. Constraint được đánh giá cùng những yêu cầu version khác về codec.
4. Gradle chọn version tương thích theo conflict resolution. **Version 1.15 ở đây thường diễn đạt yêu cầu tối thiểu tương thích, không mặc định pin đúng 1.15**.
5. `because` lưu giải thích con người để audit/debug, không làm constraint nghiêm ngặt hơn.

Nếu chỉ có:

~~~kotlin
dependencies {
    constraints {
        implementation("commons-codec:commons-codec:1.15")
    }
}
~~~

thì **không có artifact commons-codec chỉ do block này**. Để code tự sử dụng thư viện, hãy thêm `implementation("commons-codec:commons-codec:1.15")`.

### Version string, `require`, `strictly`, `prefer` và `reject`

| Cú pháp | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `require("1.15")` | Yêu cầu version tương thích, thường vẫn cho nâng cao hơn. | Không pin tuyệt đối. |
| `strictly("1.15")` | Ràng buộc chính xác 1.15 hoặc một range nghiêm ngặt nếu dùng range. | Xung đột không tương thích có thể làm resolution fail. |
| `prefer("1.15")` | Thể hiện version ưu tiên. | Yếu hơn một yêu cầu bắt buộc; không bảo đảm selected 1.15. |
| `reject("1.12")` | Loại version không được phép. | Phải còn version hợp lệ khác để chọn. |

Ví dụ thay thế constraint ở trên (không dùng đồng thời hai constraint mâu thuẫn):

~~~kotlin
dependencies {
    implementation("org.apache.httpcomponents:httpclient:4.5.13")

    constraints {
        implementation("commons-codec:commons-codec") {
            version {
                strictly("1.15")
            }
            because("Ví dụ pin chính xác để kiểm thử tương thích")
        }
    }
}
~~~

Ràng buộc `strictly` vẫn **không tự thêm** codec vào graph. Nếu dependency khác có strict requirement không tương thích, Gradle có thể từ chối resolve, thay vì lặng lẽ chọn version mà không thỏa cả hai.

Ví dụ thêm về rich version, là **mảnh code đặt bên trong `dependencies { }`**:

~~~kotlin
constraints {
    implementation("commons-codec:commons-codec") {
        version {
            prefer("1.15")
            reject("1.12")
        }
    }
}
~~~

Đừng dùng `strictly` hoặc `reject` tùy tiện để “sửa bảo mật” mà không kiểm thử tương thích API; một version cao hơn có thể không binary-compatible trong một số trường hợp.

## 7. Dependency conflict: requested khác selected

Giả sử app có nhiều đường dẫn đến một module:

~~~text
app
├── A:1.0
│    └── shared:2.0
├── B:1.0
│    └── shared:3.0
└── constraint: shared >= 2.5
~~~

Trên cùng resolved configuration, Gradle cần chọn một version hợp lệ của `shared` (trong tình huống đơn giản này có thể là `3.0`). Những yếu tố tác động gồm yêu cầu trực tiếp/bắc cầu, version ranges, constraints, platform, strictness, metadata, dependency substitution và selection rules.

**Sai lầm phổ biến:**
- “Dependency trực tiếp luôn thắng transitive”: **sai**, vì version được chọn thông qua resolution.
- “Khai báo ở dòng cuối sẽ thắng”: **sai**, không phải thuật toán ghi đè theo thứ tự dòng.
- “Constraint có version là đã tải JAR”: **sai**.
- “Có hai đường đến module nên có hai bản JAR”: **không mặc định**, Gradle thường giải quyết thành một selected module version trên graph đó.

Với xung đột version, hãy dùng `dependencyInsight` để biết **đường nào đã yêu cầu version nào**, và **vì sao Gradle chọn phiên bản cuối**.

## 8. Configuration và variant: vì sao compile khác runtime?

Một project Java có các **bucket configuration** để khai báo dependency và các **resolvable configurations** để tiêu thụ graph.

| Configuration | Vai trò | Đặc điểm |
| --- | --- | --- |
| `implementation` | Khai báo dependency dùng trong triển khai. | Bucket, không phải resolved classpath riêng. |
| `compileOnly` | Dependency có khi compile, không mặc định runtime. | Dùng đúng khi runtime được cung cấp từ nơi khác. |
| `runtimeOnly` | Dependency runtime, không cần cho source compile. | Không nên import API module này vào Java source chính. |
| `testImplementation` | Dependency cho test source set. | Không phải runtime dependency của app sản phẩm. |
| `api` | Dependency là phần API công khai của Java library. | Có trong `java-library` plugin. |
| `compileClasspath` | Graph/classpath được chọn cho Java compiler. | Có thể khác runtime. |
| `runtimeClasspath` | Graph/classpath được chọn khi chạy app. | Thường gồm implementation và runtimeOnly. |
| `testRuntimeClasspath` | Graph khi chạy test. | Có test dependencies và runtime dependencies liên quan. |

Đừng coi `implementation` là danh sách artifact hoàn chỉnh. Khi chạy:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Gradle resolve **hai graph có mục đích khác nhau**, có thể chọn các **variants** khác nhau của cùng producer, với artifacts và các cạnh bắc cầu khác nhau. Một constraint khai báo ở `testImplementation` không tự trở thành quy tắc áp cho mọi configuration của cả build.

### Variant-aware dependency management

Producer có thể công bố các variants theo attributes như `org.gradle.usage=java-api`, `org.gradle.usage=java-runtime`, `org.gradle.libraryelements` và phiên bản JVM. Consumer yêu cầu variant phù hợp với compile/runtime và Gradle chọn phần thỏa attributes.

Ví dụ thư viện Java áp dụng `java-library`, dependency `api("g:public:x")` thường hiện trên compile classpath của consumer, còn `implementation("g:private:y")` là chi tiết triển khai, thường không lộ ra compile classpath consumer nhưng cần tại runtime. Đó là lý do không thể suy ra classpath từ danh sách dependency trực tiếp mà bỏ qua variant/metadata.

## 9. Artifact: file được resolve khác component metadata

Một **component/module** có danh tính và metadata; **artifact** là sản phẩm file/thư mục được công bố/chọn:

~~~text
Module:
  org.apache.httpcomponents:httpclient:4.5.13

Metadata điển hình:
  httpclient-4.5.13.pom
  (và có thể Gradle Module Metadata nếu publisher công bố)

Artifact điển hình:
  httpclient-4.5.13.jar

Module bắc cầu:
  commons-codec:commons-codec:1.15

Artifact tương ứng:
  commons-codec-1.15.jar
~~~

Các tên file minh họa quy ước Maven; không phải mọi module đều có một JAR mặc định. Một project dependency có thể cung cấp **classes directories**; một component có thể publish nhiều artifacts và variants cho những mục đích khác nhau.

### Metadata là nguồn gốc transitivity

- **Gradle Module Metadata** (`.module`): có thể mô tả variants, attributes, capabilities, dependency constraints và rich version semantics.
- **Maven POM** (`pom.xml`): công bố dependencies/scopes theo Maven; Gradle suy diễn model tương ứng.
- **Ivy metadata** (`ivy.xml`): có configurations/relations riêng.
- **Artifact-only**: khi không sử dụng metadata, khả năng biết dependency bắc cầu và variant bị hạn chế mạnh.

Constraint do Gradle khai báo được publish đầy đủ qua **Gradle Module Metadata**; các format POM/Ivy không bảo toàn toàn bộ semantics constraint tương đương. Khi làm thư viện dùng chung, cần kiểm thử cả Gradle consumer và, nếu hỗ trợ, Maven consumer.

## 10. `@jar` và classifier: chỉ lấy artifact có thể bỏ qua metadata

Gradle hỗ trợ **artifact-only notation**, ví dụ:

~~~kotlin
dependencies {
    // Ví dụ cú pháp: không chạy nếu artifact không tồn tại ở repository.
    implementation("com.example:legacy-lib:1.0@jar")
}
~~~

Phần `@jar` làm Gradle yêu cầu file JAR theo extension, **bỏ qua metadata-based resolution** cho dependency đó. Hệ quả: **transitive dependencies, variant-aware resolution và capabilities lấy từ metadata không được xử lý theo cách của một module dependency thông thường**.

Không dùng `@jar` như một “mẹo tăng tốc” trên tất cả dependency. Nếu JAR cần các module khác mà metadata thông thường khai báo, build có thể thiếu dependency và gặp `NoClassDefFoundError` khi chạy.

Một artifact cũng có thể mang **classifier** như `sources`, `javadoc` hoặc một flavor đặc biệt. Notation có thể có dạng:

~~~text
group:name:version:classifier@extension
~~~

Nhưng **classifier khác variant Gradle**: variant có attributes và dependency edges, classifier chỉ nói về tên/loại artifact. Khi publisher có Gradle Module Metadata, nên ưu tiên variant-aware resolution thay vì hard-code classifier nếu mục đích là chọn tính năng hoặc phần Java API/runtime.

### Local file dependency

~~~kotlin
dependencies {
    // Chỉ hoạt động nếu libs/local-helper.jar có thật trong project.
    implementation(files("libs/local-helper.jar"))
}
~~~

Gradle đưa một file vào classpath, nhưng file đó **không tự mang theo metadata module dependency**. Nếu nó cần thư viện khác để chạy, hãy khai báo các dependencies bổ sung hoặc publish module có metadata. Không nên thay dependency có metadata tốt bằng file JAR thủ công chỉ để làm dependency tree ngắn đi.

## 11. Multi-project: project dependency mang variant và artifacts

Giả sử settings khai báo:

~~~kotlin
rootProject.name = "platform"
include("app", "lib")
~~~

`lib/build.gradle.kts`:

~~~kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

dependencies {
    api("org.apache.commons:commons-lang3:3.14.0")
    implementation("com.google.guava:guava:33.0.0-jre")
}
~~~

Trong block `plugins` trên, `` đại diện **Kotlin backticks** quanh built-in plugin identifier `java-library` (không phải dấu nháy kép). Khi chép sang file Kotlin DSL, hãy giữ đúng cặp backticks.

`app/build.gradle.kts`:

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass.set("example.App")
}
~~~

Hai file Gradle trên chỉ minh họa cấu hình, chưa thể chạy `app:run` nếu chưa cung cấp `src/main/java/example/App.java` thực tế. Quan hệ `implementation(project(":lib"))`:

- Là **direct project dependency**, không phải đường dẫn tới JAR.
- Cho Gradle biết component của lib và cách lấy variants/artifacts phù hợp cho compile/runtime.
- Thường mang dependency transitively cần thiết của lib tới consumer, theo variant.
- Có thể làm Gradle sắp xếp task tạo output của lib trước task tiêu thụ của app.

Dòng `api` của `lib` công bố dependency dùng trong API công khai tới compile classpath của consumer; `implementation` là chi tiết triển khai và thường không cần lộ ở consumer compile classpath, nhưng vẫn có thể cần lúc runtime.

Đừng thay `project(":lib")` bằng `files("../lib/build/libs/lib.jar")` nếu không có lý do đặc biệt: cách file path bỏ mất metadata, variant information và dependency scheduling tự nhiên. Nếu chỉ muốn một artifact được sinh từ task cụ thể, cân nhắc outgoing variant/artifact riêng.

## 12. Exclude, `isTransitive = false` và constraint là ba việc khác nhau

**Constraint** làm thay đổi yêu cầu version nhưng **không xóa module khỏi graph**.

**Exclude** cố ý loại một dependency khỏi một đường đi, ví dụ:

~~~kotlin
dependencies {
    implementation("org.apache.httpcomponents:httpclient:4.5.13") {
        exclude(group = "commons-logging", module = "commons-logging")
    }
}
~~~

Đây là cú pháp minh họa, **không phải** khuyến nghị bỏ commons-logging khỏi ứng dụng. Nếu library vẫn cần class từ module bị exclude, runtime có thể fail. Một đường dependency khác vẫn có thể đem module bị exclude vào graph.

**Tắt transitive cho declaration cụ thể**:

~~~kotlin
dependencies {
    implementation("org.apache.httpcomponents:httpclient:4.5.13") {
        isTransitive = false
    }
}
~~~

Nó ngăn Gradle theo những transitive dependencies qua declaration này, không bảo đảm artifact tự chạy đúng. Những module khác vẫn có thể được yêu cầu bởi các đường khác. Không áp dụng `isTransitive = false` đại trà để giảm kích thước build hoặc che vấn đề security.

**Artifact-only `@jar`** bỏ qua metadata của yêu cầu artifact cụ thể, nên cũng có thể mất cả variants và transitive edges. Vì vậy hãy chọn công cụ theo mục tiêu: **nâng version transitive → constraint**; **loại dependency không cần thật → exclude có kiểm thử**; **chỉ lấy một artifact không có metadata → artifact-only notation** khi đã hiểu hậu quả.

## 13. BOM/platform, version catalog và dependency locking

Các công cụ liên quan:

| Cơ chế | Mục đích | Có tự thêm mọi thư viện vào classpath? |
| --- | --- | --- |
| Dependency constraint | Quản lý version của module hiện diện. | Không. |
| `platform("g:bom:v")` | Nhập version constraints từ platform/BOM. | Không. |
| `enforcedPlatform(...)` | Áp version constraints theo cách forced mạnh hơn. | Không; dùng thận trọng vì có thể ảnh hưởng consumer. |
| Version catalog | Đặt alias + version cho cách khai báo dependency. | Không; phải thật sự dùng alias. |
| Dependency locking | Ghi/kiểm tra resolved versions để tái lập graph. | Không phải dependency declaration. |
| Dependency verification | Kiểm tra checksum/chữ ký artifact tải về. | Không ảnh hưởng khái niệm direct/transitive. |

Ví dụ platform (mảnh cấu hình trong project có plugin tạo `implementation`):

~~~kotlin
dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.3.0")
    )
    implementation("org.springframework:spring-core")
}
~~~

BOM cung cấp version constraints cho các module tương ứng nhưng **không tự kéo toàn bộ những thư viện được liệt kê trong BOM**. Đây là mốc version minh họa, cần chọn phiên bản platform/JDK/framework phù hợp với dự án.

Một alias trong `gradle/libs.versions.toml` cũng **không tự thêm dependency hoặc constraint**. Nó tạo cách tham chiếu thuận tiện; việc sử dụng alias trong `dependencies` mới tạo yêu cầu. Khi muốn một bộ rules có thể publish qua multi-project, `java-platform` cùng `dependencies { constraints { api(...) } }` là một phương án chính thống.

## 14. Cách xem graph và giải thích version thực sự được chọn

Trong dự án có Wrapper:

~~~bash
# Xem các configuration cùng dependencies của root project.
./gradlew dependencies

# Xem resolved compile graph.
./gradlew dependencies --configuration compileClasspath

# Xem resolved runtime graph.
./gradlew dependencies --configuration runtimeClasspath

# Tìm mọi đường đến commons-codec và lý do chọn version.
./gradlew dependencyInsight --dependency commons-codec --configuration runtimeClasspath

# Với module :app của multi-project build.
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-codec --configuration runtimeClasspath
~~~

Cách đọc `dependencies`:

1. Các nhánh con thể hiện quan hệ trực tiếp/bắc cầu trong configuration đang được resolve.
2. `requested -> selected` biểu thị version được yêu cầu khác version thực tế.
3. `(c)` biểu thị constraint; **không phải artifact**.
4. `(*)` thường biểu thị subtree đã được mở rộng ở một chỗ khác, không phải “trùng JAR”.
5. `FAILED` hoặc lỗi resolve cần điều tra repository/metadata/version/variant thay vì tự sửa bằng một JAR thủ công.

`dependencyInsight` bổ sung thông tin về **selection reason** như “By constraint”, “By conflict resolution”, “Was requested”, “Forced” và đường nào đã đưa module vào graph. Nếu tên module quá phổ biến, dùng `--dependency group:name` để tránh nhiều kết quả trùng; `--single-path` có thể rút ngắn khi graph lớn, `--all-variants` giúp xem variant khi cần (theo Gradle version).

**Lưu ý:** `dependencies --configuration implementation` không phải cách lý tưởng để xem artifact graph; `implementation` là bucket khai báo, thường không resolvable. Hãy xem `compileClasspath`/`runtimeClasspath` thực sự được tiêu thụ.

## 15. Các tình huống lỗi và quyết định sửa

| Triệu chứng | Nguyên nhân có thể | Cách xác minh/sửa |
| --- | --- | --- |
| `ClassNotFoundException`/`NoClassDefFoundError` khi chạy | Thiếu artifact ở runtime, scope `compileOnly` sai, exclude/tắt transitive. | Xem `runtimeClasspath`, metadata và đường đưa class vào. |
| `NoSuchMethodError` | Version trên runtime khác version API được dùng khi compile, hoặc thư viện không còn binary-compatible. | So sánh `compileClasspath` và `runtimeClasspath`, `dependencyInsight`. |
| Có `commons-codec` dù app không khai báo | Module transitive từ `httpclient` hoặc thư viện khác. | `dependencyInsight --dependency commons-codec`. |
| Có constraint nhưng không tải codec | Không module nào đưa codec vào graph. | Kiểm tra direct/transitive; thêm direct dependency nếu app dùng API codec. |
| Khai báo 1.11 nhưng chọn 1.15 | Constraint hoặc conflict resolution chọn version khác. | `dependencyInsight` và `(c)`. |
| Compile fail nhưng runtimeClasspath có module | Dependency `runtimeOnly` hoặc khác variant. | Xem compile graph và `api`/`implementation`. |
| Local JAR thiếu thư viện | File dependency không có transitive metadata. | Publish module với metadata, hoặc khai báo đầy đủ dependencies. |
| Dùng `@jar` xong mất dependency bắc cầu | Artifact-only bỏ qua metadata. | Trở lại module notation chuẩn nếu cần transitive. |
| Strict constraint gây resolution failure | Không có version nào thỏa tất cả yêu cầu. | Xem rich versions, BOM, platform, selection reasons. |
| Đã có `dependsOn` nhưng task vẫn thiếu file JAR | Task dependency khác dependency graph/artifact selection. | Kiểm tra project dependency/variant, input/output và cấu hình consumer. |
| Xung đột capabilities/variants | Hai components cùng cung cấp feature hoặc attributes không tương thích. | Xem thông báo Gradle và variant/capability metadata. |
| Module không có trong repository | Sai tọa độ/version, thiếu repo hoặc metadata. | Kiểm tra `repositories`, proxy/cache và lỗi gốc. |

### Quy trình điều tra

1. Xác định lỗi lúc **compile, test hay runtime** rồi chọn configuration tương ứng.
2. Chạy `dependencies --configuration ...` để nắm graph.
3. Chạy `dependencyInsight` cho module liên quan, đọc requested/selected, lý do và các đường bắc cầu.
4. Kiểm tra version requirements từ constraint, BOM, strict rules và những exclusions.
5. Nếu source code dùng API của module trực tiếp, khai báo dependency trực tiếp.
6. Nếu chỉ cần thay version transitive, thêm constraint thích hợp với `because(...)` và test lại.
7. Nếu muốn loại một module, xác minh nó không cần ở runtime trước khi exclude.
8. Không dùng file dependency hoặc `@jar` chỉ để “giải quyết cho nhanh” mà bỏ metadata cần thiết.
9. Kiểm thử compile, tests và chạy thật, so sánh artifact của resolved graph.
10. Với build quan trọng, dùng Gradle Wrapper, dependency locking/verification phù hợp và theo dõi version updates có kiểm soát.

## 16. Bài tập tự kiểm tra

Cho mô hình:

~~~text
app
+-- direct X:1.0
|   \-- transitive Z:1.0
+-- direct Y:2.0
|   \-- transitive Z:2.0
\-- constraint Z >= 1.5
~~~

Giả sử không có strict rule hay metadata đặc biệt:

1. **Z có được thêm chỉ vì constraint?** Không. Z có mặt nhờ X và Y.
2. **Z có chắc được chọn 1.5?** Không. Có yêu cầu Z:2.0, version cuối có thể là 2.0.
3. **Hai cạnh đến Z có mặc nhiên tải hai version?** Không. Gradle resolution hợp nhất yêu cầu trên cùng graph.
4. **Bỏ X và Y, chỉ giữ constraint, có JAR Z không?** Không.
5. **Code app tự import API của Z thì sao?** Khai báo direct dependency tới Z.
6. **Muốn buộc đúng version mà không cho nâng cao hơn?** Dùng `strictly` có chủ đích và kiểm tra conflict.
7. **Cần biết vì sao Z:2.0 được chọn?** Dùng `dependencyInsight` trên configuration phù hợp.
8. **Constraint khác artifact ở điểm nào?** Một cái là version requirement; một cái là file thực.
9. **`files("libs/z.jar")` có tự đọc transitive metadata không?** Không.
10. **`@jar` có giữ nguyên transitive như module dependency thường không?** Không, nó bypass metadata.
11. **`api` và `implementation` của Java library có như nhau không?** Không, chúng khác về API visibility tới consumer.
12. **Tại sao phải chỉ rõ `runtimeClasspath`?** Mỗi resolvable configuration có graph/variant riêng, không thể kết luận từ sai scope.

## 17. Checklist cuối

- [ ] Phân biệt direct, transitive, constraint và artifact trong một graph cụ thể.
- [ ] Biết requested version có thể khác selected version.
- [ ] Khai báo direct dependency cho library mà code thực sự dùng API.
- [ ] Dùng constraint để điều chỉnh version transitive khi không cần thêm direct dependency giả.
- [ ] Không coi constraint là dependency tạo artifact.
- [ ] Đặt dependency/constraint đúng configuration và hiểu variant compile/runtime.
- [ ] Dùng `dependencies` và `dependencyInsight` để kiểm chứng, không đoán dựa vào build script.
- [ ] Không tùy tiện dùng `isTransitive = false`, exclude hoặc `@jar`.
- [ ] Biết metadata Maven/Gradle Module Metadata ảnh hưởng graph/variant/artifact.
- [ ] Với multi-project, ưu tiên `project(":lib")`/outgoing variants thay vì đường dẫn JAR thủ công.
- [ ] Kiểm tra runtime behavior và tests sau khi nâng version, pin strict hoặc thay đổi graph.
- [ ] Cân nhắc version locking và artifact verification để build có thể tái lập, an toàn.

## Tài liệu chính thức

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): module/project/file dependencies và cách khai báo.
- [Gradle — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): constraint không thêm module, rich versions, transitivity và publication.
- [Gradle — Graph Resolution](https://docs.gradle.org/current/userguide/graph_resolution.html): graph, requested/selected components, resolution và variants.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight` và selection reasons.
- [Gradle — Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): Gradle Module Metadata, POM, Ivy, variants/artifacts.
- [Gradle — Resolving Specific Artifacts](https://docs.gradle.org/current/userguide/resolving_specific_artifacts.html): artifact-only `@extension` và classifier.
- [Gradle — Publishing Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): khả năng publish dependency constraints.
- [Gradle — Multi-project Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project dependencies, outgoing artifacts và variants.
