# Configuration khai báo, phân giải và công bố trong mô hình dependency của Gradle

## 1. Hiểu đúng từ “configuration”: đây là một đối tượng dependency, không phải chỉ là pha build

Trong Gradle, từ **configuration** xuất hiện với hai nghĩa dễ nhầm:

- **Configuration phase** là một giai đoạn của vòng đời build, lúc Gradle đánh giá build scripts, đăng ký/cấu hình task và dựng mô hình cần thiết.
- **Dependency configuration** là một **đối tượng có tên** thuộc `ConfigurationContainer` của project, dùng để khai báo dependency, chọn/đọc kết quả phân giải dependency, hoặc đưa một tập artifact và metadata ra cho bên khác sử dụng.

Bài này nói về **dependency configuration**, không phải chỉ giải thích configuration phase.

Ví dụ khi đọc `build.gradle.kts`:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api("org.example:public-api:1.0")
    implementation("org.example:internal-impl:1.0")
}
~~~

Hai lời gọi `api(...)` và `implementation(...)` thêm dependency vào các **configuration khai báo** do plugin `java-library` cung cấp. Đoạn trên là **snippet minh họa**: tọa độ `org.example:...` không được khẳng định là artifact công khai có thể tải được.

Gradle **không nhất thiết tải JAR** khi gặp dòng `implementation("...")`. Việc lựa chọn phiên bản, áp dụng rules và tải dependency xảy ra khi một **configuration phân giải được** thật sự được yêu cầu giải quyết. Còn việc một project khác “nhìn thấy” JAR/dependencies của thư viện thông qua project dependency thuộc về **configuration công bố được** và mô hình variants.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt ba vai trò **declarable / resolvable / consumable** và ba cờ điều khiển tương ứng.
2. Nhận diện `implementation`, `api`, `compileClasspath`, `runtimeClasspath`, `apiElements` và `runtimeElements`.
3. Giải thích quan hệ giữa khai báo dependency, giải quyết dependency graph và chọn outgoing variant của project thư viện.
4. Biết khi nào dùng `extendsFrom`, khi nào tạo configuration riêng, và vì sao không phân giải `implementation` trực tiếp.
5. Đọc báo cáo `dependencies`, `dependencyInsight`, `resolvableConfigurations` và `outgoingVariants`.
6. Hiểu “công bố” variant cho consumer khác với “publish” artifact lên Maven repository.

## 2. Vì sao Gradle cần ba vai trò riêng?

Một build dùng dependency ở hai chiều:

- **Chiều vào (incoming)**: project đang làm việc cần biết thư viện nào tham gia compile/runtime/test/tooling, rồi giải quyết thành các file cụ thể.
- **Chiều ra (outgoing)**: project thư viện cung cấp những artifact, thuộc tính và thông tin dependency nào cho project khác tiêu thụ.

Không nên dùng một cấu hình “vừa để khai báo vừa để giải quyết vừa để công bố” cho mọi việc. Điều này gây khó kiểm soát, đặc biệt khi một thư viện có nhiều variants (API, runtime, test fixtures, platform, native target...).

Gradle hiện đại khuyến khích **mỗi configuration giữ một vai trò chính**:

| Vai trò | Tiếng Anh | Dùng để | Ví dụ quen thuộc |
| --- | --- | --- | --- |
| **Khai báo** | Declarable / dependency-scope | Nơi thêm dependencies và constraints; mô tả yêu cầu | `implementation`, `api`, `compileOnly`, `runtimeOnly` |
| **Phân giải** | Resolvable | Từ yêu cầu và attributes chọn thành phần/variants, tạo graph và file collection | `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` |
| **Công bố** | Consumable | Đưa outgoing variant, artifacts, attributes và dependency metadata ra cho consumer | `apiElements`, `runtimeElements` |

Ba cờ của `Configuration` mô tả khả năng:

- `isCanBeDeclared`: configuration được dùng làm **dependency scope** để khai báo.
- `isCanBeResolved`: configuration có thể được **resolve** ở phía consumer.
- `isCanBeConsumed`: configuration có thể được **consumer khác lựa chọn** như một outgoing variant.

Tên property và helper APIs về **declarable** có ở các phiên bản Gradle hiện đại; nếu đang dùng Gradle rất cũ, xem tài liệu đúng phiên bản Wrapper vì mô hình role/DSL và cờ có thể khác. Với build mới, ưu tiên một role chính, không dựa vào các cấu hình kiểu cũ cho phép nhiều vai trò cùng lúc.

### 2.1. Ma trận điển hình

| Role | `canBeDeclared` | `canBeResolved` | `canBeConsumed` |
| --- | :---: | :---: | :---: |
| Dependency-scope / declarable | true | false | false |
| Resolvable | false | true | false |
| Consumable | false | false | true |

**Không phải mọi configuration tồn tại trong thế giới thực đều đúng chính xác một hàng**: plugin cũ hoặc configuration tạo theo API legacy có thể còn mang nhiều vai trò. Điều đó giải thích được một số project cũ, nhưng **không phải mẫu thiết kế nên bắt chước**.

Ba cờ này không biểu thị “đang có bao nhiêu thư viện”, “đã download hay chưa”, hoặc “đã publish thành công”. Chúng xác định **configuration được phép sử dụng theo cách nào**.

## 3. Declarable: nơi ghi yêu cầu dependency

Một **configuration khai báo** là nơi bạn đưa vào những yêu cầu như:

- tọa độ module `group:module:version`;
- project dependency như `project(":library")`;
- version constraints, platforms/BOM và các dependency attributes liên quan;
- dependencies được kế thừa bởi các configuration khác theo quan hệ cấu hình.

Ví dụ **`build.gradle.kts`** của một project dùng Java Library plugin:

~~~kotlin
plugins {
    id("java-library")
}

repositories {
    mavenCentral()
}

dependencies {
    api("org.apache.commons:commons-lang3:3.17.0")
    implementation("com.google.guava:guava:33.3.1-jre")
    compileOnly("org.jetbrains:annotations:26.0.1")
    runtimeOnly("org.slf4j:slf4j-simple:2.0.16")
}
~~~

Ví dụ này minh họa bốn phạm vi có ý nghĩa khác nhau, sử dụng một số tọa độ dependency thực tế để dễ hình dung. Để build chạy thành công cần kết nối repository, tọa độ phiên bản còn khả dụng và tương thích với môi trường; **không dùng ví dụ này làm bản khóa phiên bản cho production**.

- `api`: dependency là một phần của API mà consumer cần biết khi compile với thư viện. Nó thường tham gia cả compile/runtime của chính thư viện và compile view của consumer.
- `implementation`: dependency cần cho implementation của thư viện; không tự động được đưa vào **compile API** của consumer, nhưng có thể là dependency runtime chuyển tiếp.
- `compileOnly`: cần để compile project hiện tại nhưng không tự mang vào runtime của component được công bố theo cách thông thường.
- `runtimeOnly`: cần ở runtime nhưng không cần trên compile classpath.

Khai báo một dòng `implementation(...)` **không bảo đảm** JAR được tải ngay. Gradle sẽ đưa dependency khai báo vào những configuration resolvable phù hợp và thực hiện resolution khi cần (ví dụ task `compileJava` hoặc `test` yêu cầu classpath).

### 3.1. Vì sao không gọi resolve() trên implementation?

Mô hình đúng là:

~~~text
dependencies { implementation("g:m:v") }
                  |
                  | Khai bao yeu cau
                  v
         implementation (declarable)
                  |
                  | extendsFrom / ket noi do plugin tao
                  v
     compileClasspath / runtimeClasspath
               (resolvable)
                  |
                  | Resolution
                  v
        Dependency graph + files
~~~

`implementation` là **configuration khai báo**, không phải classpath được thiết kế để resolve trực tiếp. Nếu cố gọi `configurations["implementation"].resolve()` trong một project Java hiện đại, Gradle sẽ báo configuration không được phép resolve.

Thay vào đó, khi cần một classpath đã giải quyết, dùng configuration đúng vai trò: `compileClasspath`, `runtimeClasspath` hoặc một configuration resolvable do bạn tự tạo. Với các task có sẵn, **để plugin gắn classpath qua provider** thường là lựa chọn tốt hơn tự gọi `resolve()` trong build script.

## 4. Resolvable: biến yêu cầu thành component, variant và files

**Configuration phân giải** là điểm xuất phát khi Gradle cần kết quả dependency resolution. Một configuration loại này bao gồm:

- yêu cầu dependency được kế thừa hoặc khai báo theo cơ chế phù hợp;
- attributes của **consumer** (ví dụ yêu cầu Java API hay Java runtime);
- constraints, exclusions, resolution rules và repositories liên quan;
- kết quả là một graph các components/variants, có thể dẫn tới file artifacts được tải.

Với Java plugin, hai configuration quan trọng là:

| Configuration | Dùng chủ yếu cho | Đặc trưng |
| --- | --- | --- |
| `compileClasspath` | Compile mã nguồn Java chính | Chọn các variants phù hợp với Java API / compile usage |
| `runtimeClasspath` | Chạy chương trình hoặc test/runtime phụ thuộc vào classpath chính | Chọn các variants phù hợp với Java runtime |
| `testCompileClasspath` | Compile test | Có các dependencies dành cho test |
| `testRuntimeClasspath` | Chạy test | Kết hợp code/test và runtime dependencies phù hợp |

Một build có thể có nhiều resolvable configurations khác: cho code generator, annotation processor, integration test runtime, công cụ kiểm tra hoặc một source set riêng.

### 4.1. Phân giải không đồng nghĩa “tải mọi thứ ngay”

Khi cần giải quyết, Gradle tiến hành từ yêu cầu dependency, chọn phiên bản tương thích, áp dụng constraints và rules, ghép graph và chọn variants dựa trên attributes. Việc tìm artifact có thể dùng cache; nếu file chưa có hoặc cần metadata mới thì Gradle mới truy cập repository tương ứng. Vì vậy:

- **Khai báo** ≠ **resolve**.
- **Resolve** ≠ **download lại mọi file ở mỗi build**.
- **Resolve graph** ≠ **thực thi một task**.
- Một task có thể sử dụng classpath từ configuration resolvable và vẫn bị `UP-TO-DATE`; hai cơ chế khác nhau.

**Không nên eager-resolve** classpath lúc Gradle đang cấu hình build chỉ để “xem file nào”. Việc đó có thể làm configuration chậm, truy cập mạng sớm, gây lỗi khi build chỉ muốn chạy `help`, và ảnh hưởng khả năng sử dụng Configuration Cache. Dùng báo cáo dependency, provider-aware task APIs và công cụ chẩn đoán đúng mục đích.

## 5. Consumable: công bố outgoing variants cho các project khác

Một **configuration công bố được** diễn đạt “project này có thứ gì để người khác sử dụng”:

- artifacts đi ra (ví dụ file JAR);
- attributes cho biết tính chất variant (API/runtime, library/category, JVM version và các thuộc tính khác khi có);
- dependencies/constraints được gắn với variant theo mô hình plugin;
- capabilities và metadata khác nếu được cấu hình.

Với plugin `java-library`, hai outgoing configurations quen thuộc là:

| Configuration | Vai trò | Ý nghĩa với consumer |
| --- | --- | --- |
| `apiElements` | Consumable | Biểu diễn **API variant** của library, dùng cho consumer cần compile against library |
| `runtimeElements` | Consumable | Biểu diễn **runtime variant** của library, có phần phụ thuộc runtime cần thiết |

Khi project `:app` khai báo `implementation(project(":library"))` và cần compile:

1. Consumer resolve `:app:compileClasspath` với tập attributes phù hợp Java API.
2. Gradle tìm các variants mà `:library` công bố.
3. Với nhu cầu compile API, Gradle thường chọn `apiElements`.
4. Khi `:app:runtimeClasspath` được resolve, consumer yêu cầu runtime usage và thường chọn `runtimeElements`.
5. Artifacts và dependencies của variant được chọn tham gia classpath theo quy tắc của plugin.

Sơ đồ:

~~~text
Producer :library                           Consumer :app
------------------                          ----------------------
apiElements   (consumable) <----- matches -- compileClasspath (resolvable)
runtimeElements(consumable) <----- matches -- runtimeClasspath (resolvable)
             |                                     ^
             +-- JAR + variant metadata             |
                                                   |
                              implementation(project(":library"))
                               (declarable dependency request)
~~~

**Quan trọng:** consumer không “resolve `apiElements` của chính mình” để lấy thư viện. Nó resolve configuration **incoming** của mình, Gradle tìm outgoing variant phù hợp của **producer**. `apiElements` và `runtimeElements` không phải nơi người dùng thêm dependency một cách tùy tiện.

### 5.1. Consumable khác với publish lên Maven

“Công bố” ở đây có nghĩa **expose một variant để consumer lựa chọn**. Nó **không tự đồng nghĩa** đã upload JAR lên Maven Central, Nexus hay Artifactory.

- Project dependency `project(":library")` có thể tiêu thụ variants ngay trong cùng build mà không cần publish từ trước.
- Muốn phát hành ra Maven repository thường dùng plugin `maven-publish`, tạo publication từ software component phù hợp và cấu hình nơi publish.
- Khi publishing, Gradle có thể biểu diễn variants trong **Gradle Module Metadata**, trong khi Maven POM có mô hình scope ít chi tiết hơn. Không nên coi mỗi consumable configuration là một Maven publication riêng mặc định.

### 5.2. Ví dụ snippet công bố bằng maven-publish

Trong project thư viện đã áp dụng plugin `java-library`, có thể áp dụng thêm `maven-publish` và khai báo publication:

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.training"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Đây là **build script minh họa** hợp lệ về mô hình publish. Muốn publish lên server thật cần thêm repository, authentication, group/artifact/version chính sách phù hợp; không ghi secret trong script. Có thể dùng task `publishToMavenLocal` để thử publish vào local Maven repository khi môi trường phù hợp. Không nhầm `from(components["java"])` với `from` của `CopySpec`: hai API khác nhau hoàn toàn.

## 6. Một dự án Java 17+ chạy được để thấy ba vai trò phối hợp

Đây là ví dụ **không cần tải dependency ngoài**: một project Java Library cung cấp class, một Java Application tiêu thụ class đó qua project dependency. Cần một bản Gradle Wrapper hợp lệ và JDK 17+ tương thích với phiên bản Gradle của bạn.

### 6.1. Cấu trúc thư mục

~~~text
gradle-configuration-roles/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── library/
│   ├── build.gradle.kts
│   └── src/main/java/demo/Greeter.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/Main.java
~~~

**`settings.gradle.kts`:**

~~~kotlin
rootProject.name = "gradle-configuration-roles"
include(":library", ":app")
~~~

**Root `build.gradle.kts`:** có thể để rỗng cho ví dụ này; không cần tự thêm `allprojects` hoặc `subprojects`.

**`library/build.gradle.kts`:**

~~~kotlin
plugins {
    id("java-library")
}
~~~

**`app/build.gradle.kts`:**

~~~kotlin
plugins {
    application
}

dependencies {
    implementation(project(":library"))
}

application {
    mainClass.set("demo.Main")
}
~~~

**`library/src/main/java/demo/Greeter.java`:**

~~~java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

**`app/src/main/java/demo/Main.java`:**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Gradle"));
    }
}
~~~

Hai class này tương thích Java 17+ (và không dùng API ngoài JDK). Người học tạo toàn bộ file theo cấu trúc trên, dùng Gradle Wrapper của một project mới hoặc của môi trường đang có.

### 6.2. Chạy

Linux/macOS:

~~~bash
./gradlew -q :app:run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q :app:run
~~~

Dòng do ứng dụng Java in ra:

~~~text
Xin chao, Gradle!
~~~

Lệnh `-q` giảm log Gradle; các warning từ môi trường hoặc JVM vẫn có thể xuất hiện. Kết quả trên là **stdout của ứng dụng** trong ví dụ.

### 6.3. Điều gì xảy ra với ba role?

1. `:app` **khai báo** `implementation(project(":library"))`; đây là dependency request.
2. Khi `:app:compileJava` cần classpath, Gradle **resolve** `:app:compileClasspath`.
3. Vì compilation cần Java API, Gradle chọn outgoing **`apiElements`** thích hợp do `:library` công bố.
4. Khi `:app:run` cần chạy chương trình, plugin ứng dụng dùng classpath runtime; Gradle **resolve** `:app:runtimeClasspath` và chọn outgoing **`runtimeElements`** phù hợp từ `:library`.
5. Gradle bảo đảm các artifact đầu ra cần thiết của `:library` được tạo theo task dependency graph trước khi bên tiêu thụ sử dụng. Vì vậy lệnh gọi `:app:run` không đòi hỏi bạn chạy `:library:jar` thủ công.

**Không cần repository Maven** trong ví dụ: dependency trỏ tới một project trong chính multi-project build. Đây là lý do ví dụ phù hợp để nghiên cứu variant selection mà không phụ thuộc internet.

## 7. Quan sát vai trò bằng các task báo cáo của Gradle

Từ ví dụ mục 6, chạy:

~~~bash
# Cac configuration phan giai duoc cua project app
./gradlew :app:resolvableConfigurations --console=plain

# Cac outgoing variants cua project library
./gradlew :library:outgoingVariants --console=plain

# Cay dependency khi app can compile
./gradlew :app:dependencies --configuration compileClasspath --console=plain

# Cay dependency khi app can run
./gradlew :app:dependencies --configuration runtimeClasspath --console=plain

# Tim dependency project library trong runtimeClasspath
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency library --console=plain
~~~

Lệnh báo cáo và định dạng output có thể khác giữa các phiên bản Gradle/plug-ins. Nếu một task report chưa được hỗ trợ trên Gradle Wrapper đang dùng, tra tài liệu đúng phiên bản hoặc dùng `dependencies` / `dependencyInsight` để chẩn đoán thay vì thay đổi nội dung build.

Bạn nên quan sát:

- `:app:dependencies --configuration compileClasspath` có project dependency `project :library`.
- `:app:dependencies --configuration runtimeClasspath` cũng có project dependency `project :library`.
- `:library:outgoingVariants` cho biết các variants như `apiElements` và `runtimeElements` cùng attributes/artifacts liên quan. Đây là **phía producer**.
- `:app:resolvableConfigurations` cho thấy những configuration mà consumer có thể giải quyết và attributes chúng mang theo.
- `dependencyInsight` giúp xem đường đi, phiên bản/variant lựa chọn và lý do trong những trường hợp report hỗ trợ.

**Không đọc output rồi kết luận** mọi configuration `apiElements` và `runtimeElements` đều chứa cùng dependencies. Tùy plugin và các `api`/`implementation`/`runtimeOnly` declarations, metadata đi với API variant và runtime variant có thể khác nhau.

### 7.1. In flags trong script: chỉ để học, không dùng làm build logic thường trực

Nếu dùng Gradle hiện đại hỗ trợ property `isCanBeDeclared`, có thể **tạm thời thêm** đoạn sau vào cuối `library/build.gradle.kts` để tự xem flags:

~~~kotlin
listOf(
    "api",
    "implementation",
    "compileClasspath",
    "runtimeClasspath",
    "apiElements",
    "runtimeElements"
).forEach { configName ->
    val c = configurations.named(configName).get()
    println(
        c.name +
            ": declared=" + c.isCanBeDeclared +
            ", resolved=" + c.isCanBeResolved +
            ", consumed=" + c.isCanBeConsumed
    )
}
~~~

Sau đó chạy `./gradlew -q :library:help --no-configuration-cache`. Các configuration tương ứng của Java Library plugin trong mô hình role hiện đại thường cho các nhóm kết quả:

~~~text
api: declared=true, resolved=false, consumed=false
implementation: declared=true, resolved=false, consumed=false
compileClasspath: declared=false, resolved=true, consumed=false
runtimeClasspath: declared=false, resolved=true, consumed=false
apiElements: declared=false, resolved=false, consumed=true
runtimeElements: declared=false, resolved=false, consumed=true
~~~

**Hai điểm cần chú ý:** các dòng trên chỉ là phần được `println` trong script in, không gồm output của Gradle; thứ tự theo list đã khai báo. Khối này được chạy trong **configuration phase** để quan sát flags, và lời gọi `named(...).get()` có thể realize các configuration. Vì thế, **loại bỏ sau thí nghiệm**; không thêm logging và eager lookup như vậy vào mọi build production. Với Gradle cũ không hỗ trợ `isCanBeDeclared`, cần dùng APIs/report phù hợp phiên bản thay vì sao chép snippet nguyên xi.

## 8. api và implementation: khác nhau ở phía consumer như thế nào?

Trong `java-library`, hai declaration scopes thường bị dùng nhầm:

- `api`: dependency là một phần của API công khai được consumer cần ở compile time.
- `implementation`: dependency phục vụ nội bộ library, không nhằm xuất hiện trên compile classpath của consumer chỉ vì library phụ thuộc vào nó.

Giả sử project `:library` có public method trả về một type thuộc thư viện thứ ba. Nếu code của `:app` cần import hoặc gọi method đó, dependency chứa type này nên được cân nhắc là `api`. Nếu thư viện thứ ba chỉ dùng trong thân method riêng của `:library`, thường phù hợp với `implementation`.

Ví dụ tình huống minh họa:

~~~text
:library
  public API signature -> uses ExternalType
  implementation detail -> uses InternalHelper

:app compileClasspath
  needs library API + API-visible dependencies
  should not require implementation-only libraries

:app runtimeClasspath
  may need runtime dependencies of library
  (including runtime dependencies arising from implementation)
~~~

Đây là nguyên tắc mô hình dependency, không phải khẳng định `implementation` luôn bị loại hoàn toàn khỏi mọi graph. Việc một dependency hiện diện ở **runtime** khác việc nó được phơi bày trên **compile API**.

Khi gặp `NoClassDefFoundError` lúc runtime hoặc `cannot find symbol` lúc compile, hãy kiểm tra **đúng resolvable configuration** tại thời điểm tương ứng, thay vì thêm ngẫu nhiên dependency vào mọi scope.

## 9. Tự tạo declarable và resolvable configurations khi có công cụ riêng

Mặc dù plugin Java cung cấp phần lớn những configuration thông thường, đôi lúc bạn cần classpath riêng cho code generator, plugin tool, script phụ trợ hoặc một nhóm source. Không nên dùng `implementation` của ứng dụng như một “sọt chung” cho mọi công cụ build.

Với Gradle hiện đại có các role-specific APIs, ý tưởng thường là:

1. Tạo configuration **dependency scope** chứa yêu cầu của công cụ.
2. Tạo configuration **resolvable** thể hiện classpath cần giải quyết.
3. Nối resolvable configuration với declaration scope bằng `extendsFrom`.
4. Đưa file collection/provider vào task cần nó; không resolve ngay khi script đang cấu hình.

### 9.1. Ví dụ Kotlin DSL minh họa cấu hình có vai trò rõ

Đây là **snippet cho Gradle có hỗ trợ `dependencyScope` và `resolvable`**. Nó khai báo một công cụ ở một scope riêng; muốn resolve thật phải dùng module có thật và repository phù hợp.

~~~kotlin
val generatorDependencies = configurations.dependencyScope("generatorDependencies")

val generatorClasspath = configurations.resolvable("generatorClasspath") {
    extendsFrom(generatorDependencies.get())
}

repositories {
    mavenCentral()
}

dependencies {
    add("generatorDependencies", "org.example:code-generator:1.0")
}
~~~

Tọa độ `org.example:code-generator:1.0` là **placeholder minh họa**, không phải artifact được bảo đảm tồn tại. Chỉ nên thử resolution khi thay bằng dependency thực tế.

**Diễn giải:**

- `generatorDependencies`: nơi thêm dependency yêu cầu, không dùng trực tiếp để gọi `resolve()`.
- `generatorClasspath`: nơi Gradle sẽ resolve những yêu cầu kế thừa, có thể gắn vào `JavaExec` hoặc custom task phù hợp.
- `extendsFrom(generatorDependencies.get())` thiết lập quan hệ kế thừa dependencies; `get()` ở đây lấy đối tượng configuration khi đang cấu hình, **không resolve artifacts** của scope.
- `generatorClasspath` **không tự trở thành consumable variant** chỉ vì nhận dependencies từ scope kia.

Trong một task thật, hãy cấu hình `classpath` bằng provider/configuration phù hợp, tránh đọc `generatorClasspath.get().files` sớm. Nếu phải dùng `JavaExec` để chạy main class của công cụ, cần API classpath, main class và dependencies phù hợp; snippet trên chỉ làm rõ **mô hình configuration**, chưa phải task chạy độc lập.

### 9.2. Khi cần consumable custom variant

Ví dụ một project muốn project khác dùng bộ tài liệu đã đóng gói, không phải JAR Java thông thường. Khi đó có thể tạo configuration **consumable** chứa outgoing artifact của một task archive, kèm attributes và capability phù hợp để consumer lựa chọn. Tuy nhiên, thiết kế custom variant đúng còn liên quan tới `Category`, `Usage`, `DocsType` hoặc attributes riêng, artifact dependencies, compatibility/disambiguation và publication metadata.

**Không dùng** `configurations.create("docs")` rồi bật cả `canBeResolved`, `canBeConsumed` và `canBeDeclared` để “cho chắc”. Vai trò nên tách biệt. Với nhu cầu chỉ phát hành một JAR tiêu chuẩn, **dùng `java-library` và `maven-publish`** thay vì tự tái tạo `apiElements`/`runtimeElements`.

### 9.3. API cũ: configuration tạo bằng creating

Một số script cũ dùng:

~~~kotlin
val legacyToolClasspath by configurations.creating {
    isCanBeResolved = true
    isCanBeConsumed = false
}
~~~

Mẫu này có thể xuất hiện trong tài liệu hoặc project cũ. Với Gradle có cơ chế **declarable role** riêng, phải kiểm tra thêm `canBeDeclared` và ý nghĩa legacy defaults; chỉ hai cờ ở trên không đủ để chứng minh configuration là một resolvable-only scope đúng mẫu hiện đại.

Khi xây build mới, ưu tiên helpers phân vai rõ như `dependencyScope`, `resolvable` và `consumable` nếu phiên bản Gradle hỗ trợ, tránh sao chép cấu hình đa vai trò từ bài viết cũ.

## 10. extendsFrom truyền gì và không truyền gì?

`extendsFrom` tạo quan hệ kế thừa dependency declarations từ configuration cha sang con. Trong plugin Java, các cấu hình classpath nối với declaration scopes theo cách Gradle đã định nghĩa.

Ví dụ khái niệm:

~~~text
generatorDependencies (declarable)
          |
          | extendsFrom
          v
generatorClasspath (resolvable)
          |
          v
Dependency resolution
~~~

Những điều **đúng**:

- Resolvable configuration có thể dùng dependencies và constraints kế thừa để xây graph.
- Có thể tổ chức nhiều dependency scopes để chia sẻ tập yêu cầu với các classpaths khác nhau khi hợp lý.
- Quan hệ kế thừa **không tự gọi resolution**; cần một consumer/task/report yêu cầu kết quả.

Những điều **không nên suy ra**:

- `extendsFrom` không biến configuration khai báo thành configuration resolve được.
- `extendsFrom` không tự biến configuration con thành consumable variant.
- `extendsFrom` không có nghĩa là mọi thuộc tính resolution/attributes, artifact và vai trò được sao chép y hệt theo một quy tắc chung.
- `extendsFrom` không thay cho variant-aware matching giữa **consumer** và **producer**.
- Không nên thiết kế vòng kế thừa hoặc dùng quan hệ này để trộn mọi scopes vào mọi classpath.

Nếu cần hiểu vì sao một module xuất hiện trong runtime nhưng không có trong compile, hãy đọc các scope declaration và quan hệ extendsFrom của plugin/source set liên quan, rồi dùng report dependency đúng configuration.

## 11. Variant-aware dependency resolution: attributes quyết định lựa chọn

Điều rất quan trọng: Gradle hiện đại không chỉ “tìm file JAR có cùng tên”. Nó xem **consumer đang cần gì** và **producer đang cung cấp những variants nào**.

Một số attributes thường gặp trong Java ecosystem:

| Thuộc tính/khái niệm | Vai trò |
| --- | --- |
| `org.gradle.usage` | Phân biệt nhu cầu Java API hoặc Java runtime |
| `org.gradle.category` | Phân loại library, platform, documentation... |
| `org.gradle.libraryelements` | Dạng library như JAR/classes tùy plugin và môi trường |
| `org.gradle.jvm.version` | Khả năng tương thích JVM/bytecode theo thông tin variant |
| `capability` | Nhận diện khả năng mà component/variant cung cấp |
| `artifact type` / transform | Có thể liên quan lựa chọn hoặc biến đổi artifact để dùng được |

**Sơ đồ lựa chọn:**

~~~text
Consumer resolves runtimeClasspath
        |
        +-- Requested attributes (Java runtime, JVM constraints, ...)
        |
        v
Look at producer variants
   - apiElements:    API usage / metadata
   - runtimeElements: runtime usage / metadata
   - other variants:  plugin-defined
        |
        v
Compatibility + disambiguation rules
        |
        v
Selected variant(s) + graph + artifacts
~~~

Nếu producer công bố các variants không tương thích với consumer, Gradle có thể báo **No matching variant**. Nếu nhiều variants đều đáp ứng nhưng Gradle không thể chọn duy nhất, có thể báo **ambiguous variant selection**.

Không khắc phục bằng cách bật `canBeConsumed = true` cho một configuration tùy ý rồi hy vọng Gradle tự hiểu. Phải đọc **attributes yêu cầu** và **attributes được cung cấp**, cùng quy tắc tương thích/disambiguation; sau đó sửa đúng producer hoặc consumer, hay dùng plugin cung cấp model phù hợp.

## 12. Báo cáo dependency giúp trả lời câu hỏi gì?

### 12.1. dependencies: một configuration đang chứa graph nào?

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Dùng khi muốn biết:

- dependency trực tiếp và dependency chuyển tiếp nào đang có;
- vì sao runtime classpath khác compile classpath;
- các version conflict thường thể hiện ra sao trong graph;
- project dependencies có tham gia không.

Một báo cáo không luôn kể đầy đủ **lý do variant được chọn**; khi cần xem chi tiết, dùng `dependencyInsight` hoặc các báo cáo variant.

### 12.2. dependencyInsight: tại sao component/version được chọn?

~~~bash
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency library
~~~

Trong build dùng external dependencies, `--dependency` có thể là một tên module phù hợp; report hỗ trợ chỉ ra đường dependency, constraints/conflicts và lý do version selection. Có thể cần tùy chọn bổ sung như `--all-variants` tùy phiên bản và trạng thái resolution.

### 12.3. outgoingVariants: producer cung cấp cái gì?

~~~bash
./gradlew :library:outgoingVariants
~~~

Dùng để xem các variants/artifacts và attributes phía outgoing. Đây là điểm tốt để điều tra “consumer muốn runtime nhưng producer chỉ có API” hay custom variant không mang attributes mong đợi.

### 12.4. resolvableConfigurations: consumer đang yêu cầu gì?

~~~bash
./gradlew :app:resolvableConfigurations
~~~

Dùng để xem cấu hình incoming có thể resolve và các attributes (nếu được Gradle/plugin báo cáo). Từ đó đối chiếu với `outgoingVariants` để hiểu variant matching.

Nếu project quá lớn, thu hẹp theo module và configuration cần thiết; không chạy `dependencies` trên mọi cấu hình rồi giả định mọi phần đều đáng tin để chia sẻ công khai. Dependency report có thể lộ tên repository/module nội bộ.

## 13. Lỗi hay gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `Resolving dependency configuration 'implementation' is not allowed` | `implementation` chỉ khai báo, không resolve | Dùng `compileClasspath`/`runtimeClasspath` hoặc resolvable configuration riêng |
| `Dependencies can not be declared against ...` | Đã thêm dependency vào configuration không có role declarable | Thêm vào dependency scope phù hợp, nối qua `extendsFrom` nếu cần |
| `No matching variant of project :library was found` | Attributes/usage/JVM constraints không tương thích outgoing variants | So sánh `resolvableConfigurations` và `outgoingVariants` |
| `Cannot choose between variants` | Nhiều outgoing variants cùng khớp mà không phân giải được | Bổ sung attributes/compatibility rules đúng hoặc điều chỉnh plugin/model |
| Compile thành công nhưng runtime thiếu class | Scope runtime hoặc dependency chuyển tiếp không đúng | Xem `runtimeClasspath`, `runtimeOnly` và `runtimeElements` |
| App không compile được type từ library API | Dependency dùng `implementation` trong library nhưng type lộ qua public signature | Cân nhắc `api` đối với dependency thật sự thuộc public API |
| Tự tạo configuration rồi vẫn không lấy được file | Configuration chỉ khai báo/consumable, chưa resolvable | Tách role, tạo resolvable scope |
| Artifact đã build nhưng consumer không thấy | Chưa công bố outgoing variant hoặc task/artifact metadata chưa nối | Dùng plugin phù hợp hoặc cấu hình consumable variant đúng |
| Lệnh `publish` không tồn tại hoặc không đẩy JAR | Consumable configuration không tự tạo publication | Áp dụng `maven-publish` và tạo publication/repository |
| `dependencyInsight` trả báo cáo không mong đợi | Chọn sai project/configuration hoặc module pattern | Kiểm tra đúng `:app` và `compileClasspath`/`runtimeClasspath` |
| Configuration cache không tái sử dụng được | Script eager-resolve hoặc dùng API không tương thích | Tránh resolution trong configuration phase, dùng provider và report |
| Dep xuất hiện “hai lần” ở graph | Các declarations/extendsFrom/transitivity hoặc report nhiều paths | Đọc graph và selected versions trước khi kết luận xung đột |
| Copy code Gradle cũ sai role flags | API và default legacy khác model hiện đại | Xem phiên bản Wrapper; dùng role-specific APIs khi có |

### 13.1. Trình tự debug một lỗi variant

1. Xác định **consumer** đang resolve cấu hình nào: `compileClasspath` hay `runtimeClasspath`?
2. Chạy `resolvableConfigurations` hoặc xem attributes được hiển thị trong lỗi.
3. Xác định **producer** là project nào hoặc external module nào.
4. Chạy `outgoingVariants` nếu producer là một project trong build; với external module, xem metadata của module.
5. So sánh usage, category, JVM version/capability và các attributes liên quan.
6. Kiểm tra plugin và source set có đang cung cấp variant mà consumer cần hay không.
7. Chỉ sửa scopes/attributes thực sự sai; không bật mọi cờ để ép resolution.
8. Chạy lại `dependencies` / `dependencyInsight` của đúng configuration để xác nhận graph được chọn đúng.

## 14. Các ngộ nhận cần tránh

**Ngộ nhận 1 — “Configuration là một thư mục chứa JAR”.** Không đúng. Nó là một phần của mô hình dependency; resolvable configuration có thể dẫn đến graph và files, nhưng bản thân configuration không chỉ là directory.

**Ngộ nhận 2 — “Mọi configuration đều resolve được”.** Không đúng. `implementation` và `api` thường là nơi khai báo; `runtimeElements` dùng để công bố, không phải nơi hỏi `files` của chính producer.

**Ngộ nhận 3 — “canBeConsumed nghĩa là đã upload”.** Không đúng. Nó cho phép producer công bố variant; publishing ngoài repository là bước khác.

**Ngộ nhận 4 — “api và implementation không ảnh hưởng consumer”.** Sai. `api` thường được đưa ra compile API của consumer; `implementation` không nhằm phơi bày compile detail, nhưng vẫn có vai trò runtime.

**Ngộ nhận 5 — “Khai báo xong là Gradle tải ngay tất cả JAR”.** Không đúng. Dependency resolution và file download được tiến hành khi cần, có cache và metadata liên quan.

**Ngộ nhận 6 — “extendsFrom làm hai configurations giống nhau hoàn toàn”.** Không. Nó kế thừa các dependency declarations và constraints có liên quan theo cơ chế Gradle, không biến đổi vai trò hoặc bảo đảm attributes giống nhau.

**Ngộ nhận 7 — “Bật cả ba flags giúp tương thích ngược tốt hơn”.** Các legacy configurations có thể làm vậy, nhưng thiết kế mới nên phân vai rõ để giảm ambiguity và tương tác không mong muốn.

**Ngộ nhận 8 — “Phải custom configuration cho mọi thư viện”.** Không. Plugin Java/Java Library đã cung cấp scopes/classpaths/variants phổ biến; hãy tái sử dụng trước.

## 15. Bài tập tự kiểm tra

**Bài 1.** `dependencies { implementation("g:m:1") }` là khai báo hay phân giải?  
**Đáp án:** khai báo một dependency request trên declarable scope, chưa có nghĩa đã tải artifact.

**Bài 2.** `runtimeClasspath` có role chính nào?  
**Đáp án:** resolvable; dùng để xác định dependencies/files cho runtime.

**Bài 3.** `runtimeElements` có phải nơi thêm dependency của ứng dụng không?  
**Đáp án:** không; đây thường là consumable outgoing variant của producer.

**Bài 4.** Project `:app` compile phụ thuộc `project(":library")` thường chọn variant nào?  
**Đáp án:** Java API variant như `apiElements` từ `:library`, khi attributes phù hợp.

**Bài 5.** Project `:app` chạy ứng dụng sẽ chọn variant nào của `:library`?  
**Đáp án:** runtime variant như `runtimeElements`, khi consumer resolve runtimeClasspath.

**Bài 6.** Tại sao không gọi `configurations["implementation"].resolve()`?  
**Đáp án:** implementation là declaration scope không được thiết kế để resolve; phải dùng classpath resolvable phù hợp.

**Bài 7.** Bạn có tool dependency chỉ phục vụ code generation. Có nên thêm nó vào `implementation` của app?  
**Đáp án:** thường không; tạo dedicated declarable scope và resolvable tooling classpath, tránh làm dependency của công cụ lọt vào classpath app.

**Bài 8.** Muốn xem library xuất ra những variants nào, dùng lệnh nào?  
**Đáp án:** `./gradlew :library:outgoingVariants`.

**Bài 9.** Đã tạo `runtimeElements` nhưng chưa áp dụng `maven-publish`. JAR đã được upload lên Maven chưa?  
**Đáp án:** chưa. Outgoing variant và publication là các khái niệm khác nhau.

**Bài 10.** `extendsFrom` có tự bật `canBeConsumed` không?  
**Đáp án:** không; role flags và quan hệ kế thừa dependency declarations là những cấu hình riêng.

**Bài 11.** External library xuất hiện khi chạy nhưng không có trên compile classpath của consumer. Đây chắc chắn là lỗi?  
**Đáp án:** không nhất thiết. Dependency implementation/runtime-only có thể cần lúc chạy nhưng không là một phần của public compile API. Xem việc API của thư viện thực sự dùng type nào.

**Bài 12.** `dependencyInsight` nên chạy trên `implementation` hay `runtimeClasspath` khi debug runtime?  
**Đáp án:** chọn resolvable `runtimeClasspath` của đúng project.

## 16. Checklist khi thiết kế configuration

- [ ] Phân biệt đang nói về dependency configuration hay Gradle configuration phase.
- [ ] Xác định role chính của configuration: declarable, resolvable hay consumable.
- [ ] Không gọi resolve trên declaration-only configuration.
- [ ] Dùng `api`/`implementation`/`runtimeOnly` đúng ý nghĩa với consumer.
- [ ] Không bật cả ba role flags để giải quyết triệu chứng.
- [ ] Nếu tạo classpath riêng, tạo declarable dependency scope và resolvable classpath đúng cách.
- [ ] Chỉ dùng `extendsFrom` để kế thừa declarations cần thiết, không coi là sao chép toàn bộ thuộc tính.
- [ ] Với producer custom variant, khai báo attributes/artifacts/capabilities phù hợp consumer.
- [ ] Dùng `dependencies`/`dependencyInsight` để chẩn đoán graph và version selection.
- [ ] Dùng `outgoingVariants` và `resolvableConfigurations` để so sánh hai đầu variant matching.
- [ ] Không eager-resolve classpath trong configuration phase chỉ để log/debug.
- [ ] Phân biệt outgoing variant với Maven publication; giữ credentials ngoài source.
- [ ] Kiểm tra phiên bản Gradle Wrapper trước khi dùng APIs role-specific mới.

## 17. Tài liệu chính thức

- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): các vai trò configuration, declarable/resolvable/consumable và cách khai báo.
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html): dependency requests và các declaration scopes.
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): cách Gradle tạo graph và chọn các thành phần.
- [Gradle — Variant-aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): attributes, producer variants và matching.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation` và outgoing variants cho Java libraries.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight` và báo cáo phù hợp.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): cách phát hành software component/artifact tới Maven repository.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tác động của build model, configuration và việc tránh resolution sớm.

**Tóm tắt:** ba câu hỏi xác định role là **“Tôi khai báo cần gì?” → declarable; “Tôi cần giải quyết ra thành phần/files nào?” → resolvable; “Tôi cung cấp variant/artifact gì cho project khác?” → consumable.** Hiểu ba chiều này sẽ giúp đọc dependency graph, chọn đúng `api`/`implementation` và sửa lỗi variant thay vì thử bật/tắt cờ tùy tiện.