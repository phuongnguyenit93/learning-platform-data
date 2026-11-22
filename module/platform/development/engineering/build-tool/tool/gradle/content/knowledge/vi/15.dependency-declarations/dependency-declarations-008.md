# Exclude dependency bắc cầu và tránh loại nhầm thư viện cần thiết trong Gradle

## 1. Vì sao cần hiểu dependency exclusion?

Trong Gradle, khi khai báo một thư viện bên ngoài, project thường nhận cả những **dependency bắc cầu** (*transitive dependencies*) mà thư viện khai báo trong metadata. Đó là cơ chế hữu ích: người dùng không phải tự liệt kê toàn bộ JAR bên dưới mỗi dependency. Nhưng đôi khi một thư viện kéo theo module cũ, không còn cần cho code path đang dùng, trùng chức năng với module khác, hoặc xung đột với hệ thống hiện tại.

Gradle cho phép dùng `exclude(...)` để **loại module được chỉ định khỏi một nhánh hoặc một configuration đang resolve**. Điều cần nhớ: loại nhầm một thư viện mà code bên thứ ba vẫn sử dụng có thể làm ứng dụng lỗi khi chạy, kể cả khi `compileJava` thành công.

Ví dụ hình dung:

~~~text
Ứng dụng
  └── library-A
        ├── library-B   (A thực sự cần khi chạy)
        └── library-C   (A không dùng trong use case hiện tại)
~~~

Bạn có thể muốn bỏ C nhưng phải **kiểm tra** rằng A không cần C trong những code path quan trọng. Không nên loại B chỉ vì Java source ứng dụng không import B trực tiếp: A có thể gọi B bên trong.

Bài học giúp bạn:

- Đọc graph và phân biệt **direct dependency** với **transitive dependency**.
- Dùng `exclude(group = "...", module = "...")` trong **Kotlin DSL** và **Groovy DSL**.
- Phân biệt **per-dependency exclude**, **per-configuration exclude** và `isTransitive = false`.
- Hiểu vì sao một module vẫn có mặt khi chỉ một đường tới nó bị exclude.
- Dùng `dependencies`, `dependencyInsight` và các classpaths để xác minh.
- Tránh loại sai thư viện ở production runtime, test, annotation processor hoặc distribution.
- Chọn phương án thay thế: constraints, BOM/platform, metadata rules, capabilities khi vấn đề không phải “module dư”.
- Làm một thí nghiệm Gradle + Java 17 từ đầu, đối chiếu stdout trước và sau exclusion.

**Phạm vi:** Exclude trong bài là **dependency resolution**, không phải `Copy.exclude("**/*.java")` để lọc file, `-x test` để bỏ task hoặc `.gitignore` để ẩn file khỏi Git.

## 2. Direct dependency và transitive dependency

Project Java có:

~~~kotlin
plugins {
    id("application")
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4")
}
~~~

Ý nghĩa:

1. `commons-beanutils:commons-beanutils:1.9.4` là dependency project khai báo trực tiếp.
2. Theo dependency metadata trong ví dụ hướng dẫn chính thức của Gradle, module này yêu cầu thêm `commons-logging:commons-logging:1.2` và `commons-collections:commons-collections:3.2.2`.
3. Gradle sẽ resolve graph qua một configuration thích hợp như `runtimeClasspath`, lấy các artifact hợp lệ từ repository.
4. Module có mặt trên **resolved classpath** không nhất thiết phải được khai báo trực tiếp trong `dependencies { }`.

Sơ đồ minh họa:

~~~text
app
└── commons-beanutils:commons-beanutils:1.9.4 [direct]
    ├── commons-logging:commons-logging:1.2 [transitive]
    └── commons-collections:commons-collections:3.2.2 [transitive]
~~~

Tên `group:name:version` chỉ định module/version muốn sử dụng. Trong resolution thực tế, Gradle còn xét graph nhiều nhánh, constraints, variants, conflicts và rules. Bạn không thể suy ra chính xác toàn bộ runtime classpath chỉ bằng cách đếm số dòng dependency trực tiếp.

### 2.1. Bốn tầng khác nhau

| Tầng | Vai trò |
| --- | --- |
| **Dependency declaration** | Lời gọi `implementation("group:name:version")` trong build script |
| **Configuration scope** | `implementation`, `runtimeOnly`, `testImplementation`... nhóm declaration theo mục đích |
| **Resolvable configuration** | `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`... cho Gradle giải quyết graph |
| **Task và runtime** | `compileJava`, `test`, `run`, distribution hoặc ứng dụng thực sự tiêu thụ các file đã resolve |

Một module có thể là direct ở `:library` nhưng transitive ở `:app` nếu app phụ thuộc library. “Transitive” mô tả **quan hệ trong graph**, không phải tên loại artifact.

### 2.2. Vì sao một thư viện transitive lại quan trọng?

Một dependency cha có thể cần thư viện con để logging, JSON parsing, HTTP client, database driver, serialization, reflection, ServiceLoader, annotation processing hoặc một tính năng tùy chọn. Dependency con có thể **không xuất hiện trong Java source của ứng dụng** mà vẫn được thư viện cha gọi khi chạy.

Các lỗi có thể xuất hiện:

~~~text
java.lang.NoClassDefFoundError: some/package/RequiredType
java.lang.ClassNotFoundException: some.package.RequiredType
java.lang.NoSuchMethodError: some.package.Library.method(...)
~~~

Đây là các **dạng lỗi minh họa**, không phải stdout chắc chắn của thí nghiệm bên dưới. `NoClassDefFoundError`/`ClassNotFoundException` có thể liên quan classpath bị thiếu; `NoSuchMethodError` thường còn liên quan phiên bản API/ABI không tương thích. Hãy đọc `Caused by`, graph và stacktrace trước khi đoán.

## 3. Per-dependency exclude: loại một module trong một nhánh

### 3.1. Kotlin DSL (`build.gradle.kts`)

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(
            group = "commons-collections",
            module = "commons-collections"
        )
    }
}
~~~

Đoạn này giả định đã áp dụng Java/Application plugin và có `repositories { mavenCentral() }`. Tác dụng:

- Giữ direct dependency `commons-beanutils`.
- Loại module `commons-collections:commons-collections` từ những transitive dependencies đi qua declaration này.
- Không loại `commons-logging` nếu nó chỉ là một dependency khác của BeanUtils.
- Không xóa `commons-collections` khỏi Gradle cache hoặc từ Maven Central.
- Không tự thay đổi dependency declarations của project khác.

Ở Kotlin DSL, `exclude(group = "...", module = "...")` là API để bổ sung rule; không cần viết một câu lệnh điều kiện chạy lúc task execution.

### 3.2. Groovy DSL (`build.gradle`)

~~~groovy
dependencies {
    implementation('commons-beanutils:commons-beanutils:1.9.4') {
        exclude group: 'commons-collections', module: 'commons-collections'
    }
}
~~~

Hai ví dụ có **cùng ngữ nghĩa**. Kotlin dùng dấu ngoặc, dấu nháy đôi và named arguments; Groovy có thể dùng dấu nháy đơn và map-style notation. Không chép nguyên `exclude group: ...` vào `.gradle.kts` vì đây không phải cú pháp Kotlin.

### 3.3. Group, module, version khác nhau

Tọa độ module:

~~~text
group : module : version
commons-collections : commons-collections : 3.2.2
~~~

Rule exclusion thường định danh bằng `group` và/hoặc `module`. Khi biết chính xác cả hai, hãy dùng cả hai. **Exclude không phải thao tác chọn một phiên bản duy nhất**: nếu chỉ muốn tránh version lỗi, kiểm soát phiên bản bằng constraint, platform/BOM hoặc cơ chế resolution tương ứng thay vì loại toàn bộ module.

Ví dụ quá rộng:

~~~kotlin
// Có thể loại nhiều module hơn mong muốn.
exclude(group = "org.apache.commons")
~~~

Một group có thể chứa rất nhiều thư viện quan trọng. Với module `commons-collections4`, hãy chỉ ra cả `group = "org.apache.commons"` lẫn `module = "commons-collections4"` nếu thật sự cần loại. Đừng nhầm với `commons-collections:commons-collections` (nhánh 3.x) vì **đó là module khác**.

### 3.4. “Exclude một nhánh” không phải “xóa declaration trực tiếp”

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("commons-collections:commons-collections:3.2.2")
}
~~~

`commons-collections` vẫn có trên classpath vì project **đã khai báo trực tiếp** nó ở dòng thứ hai. Rule gắn vào BeanUtils không xóa declaration này.

## 4. Tại sao exclude rồi module vẫn xuất hiện?

Gradle xem **toàn bộ dependency graph** và các đường đi có liên quan. Một rule chỉ gắn trên dependency A không buộc dependency B cũng loại cùng module.

### 4.1. Một đường đi

~~~text
app
  └── A ──> X
~~~

Nếu `implementation(A) { exclude(X) }` và không có đường khác/direct dependency tới X, thì X không còn được kéo vào graph qua A.

### 4.2. Hai đường đi

~~~text
app
  ├── A ──exclude(X)──> X  [đường này bị loại]
  └── B ──────────────> X  [đường này vẫn yêu cầu X]
~~~

Module X **vẫn có thể xuất hiện** vì nhánh B không yêu cầu exclusion tương ứng. Trong hướng dẫn của Gradle, per-dependency exclusion chỉ thật sự loại module khỏi toàn graph khi không có những đường cần module đó còn lại.

Ví dụ Gradle dùng trong tài liệu:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("com.opencsv:opencsv:4.6")
}
~~~

Trong graph minh họa này, `opencsv` kéo `commons-beanutils` theo một đường khác không mang rule exclude, khiến `commons-collections` xuất hiện. Không nên kết luận Gradle đã “bỏ qua exclude”; graph vẫn có đường phụ thuộc hợp lệ.

### 4.3. Loại từ mọi đường liên quan — chỉ khi đã kiểm tra an toàn

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("com.opencsv:opencsv:4.6") {
        exclude(group = "commons-collections", module = "commons-collections")
    }
}
~~~

Đây là **mẫu cấu hình**, không phải khuyến nghị mù quáng phải loại collections khỏi hai thư viện. Chỉ làm khi đã chứng minh các code path mình dùng không yêu cầu module đó và đã kiểm thử cả chức năng BeanUtils/OpenCSV có liên quan.

**Cẩn thận tên trùng:** `org.apache.commons:commons-collections4` có group/module khác `commons-collections:commons-collections`. Nó có thể vẫn xuất hiện ngay cả khi đã loại collections3, nhưng không nên tự động loại collections4.

## 5. Configuration-level exclude: phạm vi lớn hơn

Gradle cũng có `Configuration.exclude(...)`. Thay vì đặt rule lên một dependency declaration, rule áp dụng ở **một configuration cụ thể** và quá trình resolve liên quan.

### 5.1. Kotlin DSL

~~~kotlin
configurations.named("runtimeClasspath") {
    exclude(
        group = "commons-collections",
        module = "commons-collections"
    )
}
~~~

Ví dụ giả định Java/Application plugin đã tạo `runtimeClasspath`. Đây là configuration **resolvable** cho runtime mã chính, không phải tên một task.

Khác biệt so với per-dependency rule:

- Không chỉ nhắm vào nhánh BeanUtils, mà dùng rule cấp configuration.
- Có thể loại module dù nó được mang tới bởi nhiều dependency paths của configuration đó.
- Không tự bảo đảm module bị loại khỏi **mọi** configuration khác như `compileClasspath`, `testCompileClasspath`, custom tooling hoặc annotation processing.
- Có thể làm hỏng runtime nếu một nhánh khác thực sự cần module.

### 5.2. Groovy DSL

~~~groovy
configurations.named('runtimeClasspath') {
    exclude group: 'commons-collections', module: 'commons-collections'
}
~~~

Vẫn cùng ý nghĩa. Đây không phải một lệnh xóa file trong build directory.

### 5.3. Đặt rule ở implementation có thể lan rộng hơn

~~~kotlin
configurations.named("implementation") {
    exclude(group = "commons-collections", module = "commons-collections")
}
~~~

Java plugin tạo các classpaths kế thừa dependency declarations và exclude rules từ `implementation`. Vì vậy exclusion ở scope này có thể ảnh hưởng cả compile và runtime (và các scopes test kế thừa). Đừng đặt rule lên `implementation` chỉ vì muốn loại module **trong một nhánh runtime duy nhất**.

### 5.4. Exclude toàn bộ configurations là lựa chọn rủi ro

~~~kotlin
// Anti-pattern nếu không có chính sách dự án được kiểm chứng.
configurations.configureEach {
    exclude(group = "commons-collections", module = "commons-collections")
}
~~~

Dù có thể hợp lệ về cú pháp, nó có thể ảnh hưởng rất nhiều classpaths, tools và variants. Tài liệu best practices của Gradle khuyên **đặt exclusion càng hẹp càng tốt**, lý tưởng trên từng dependency declaration, và tránh rule toàn cục khi không cần.

### 5.5. Bảng so sánh phạm vi

| Cách làm | Bắt đầu ảnh hưởng từ đâu | Rủi ro chính |
| --- | --- | --- |
| `implementation("A") { exclude(X) }` | Đường bắc cầu của A | X có thể vẫn xuất hiện qua B |
| `configurations.named("runtimeClasspath") { exclude(X) }` | Runtime graph của configuration đó | Có thể làm B thiếu X tại runtime |
| `configurations.named("implementation") { exclude(X) }` | Scope implementation và các configuration kế thừa | Có thể ảnh hưởng compile/test/runtime ngoài ý muốn |
| `configurations.configureEach { exclude(X) }` | Rất nhiều configurations của project | Rủi ro loại sai trên diện rộng |

## 6. `isTransitive = false` không phải loại một module

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        isTransitive = false
    }
}
~~~

Dòng `isTransitive = false` ngăn các dependencies bắc cầu qua **declaration đó**, không chỉ loại `commons-collections`. `commons-logging` và những dependency khác cũng có thể mất nếu không được kéo vào từ đường khác.

| Cấu hình | Tác động |
| --- | --- |
| `exclude(group, module)` trên A | Loại module cụ thể khỏi đường qua A |
| `isTransitive = false` trên A | Không lấy **mọi transitive dependency** qua A |
| `isTransitive = false` trên configuration | Chặn transitivity trong phạm vi configuration, có thể ảnh hưởng rất rộng |

**Không nghĩ rằng tắt transitive của A sẽ loại vĩnh viễn mọi module con:** Một dependency khác vẫn có thể kéo module ấy vào graph. Nếu code path của A cần thư viện con, tắt toàn bộ transitivity sẽ làm thiếu class runtime; bạn buộc phải khai báo các thư viện cần thiết theo cách khác.

Đừng nhầm `isTransitive` với `extendsFrom`: `extendsFrom` là kế thừa các declarations/rules giữa configurations; transitivity là giải quyết dependency bắc cầu từ metadata module.

## 7. Bài thực hành Gradle Kotlin DSL + Java 17 có thể chạy

Thí nghiệm này dùng **JDK 17**, Gradle hỗ trợ JDK đó, Maven Central (có mạng hoặc cache artifact) và Application plugin tích hợp. Mục tiêu là kiểm tra **sự tồn tại của .class file trên runtime classpath** chứ không gọi method có thể cần module bị loại. Sự hiện diện/thiếu vắng class file **không tự chứng minh** exclude an toàn cho mọi API của BeanUtils.

### 7.1. Cây thư mục

~~~text
exclusion-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "exclusion-lab"
~~~

### 7.3. build.gradle.kts phiên bản đầu tiên

~~~kotlin
plugins {
    id("application")
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
    mainClass.set("demo.Main")
}

dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4")
}
~~~

Giải thích:

- `application` cung cấp các task compile Java và `run`.
- `mavenCentral()` dùng để resolve artifacts bên ngoài.
- `java.toolchain` yêu cầu JDK 17 để biên dịch/chạy Java; máy phải cung cấp toolchain phù hợp.
- `mainClass` là tên class đầy đủ, khớp với package trong file `Main.java`.
- Chưa có exclusion nên runtimeClasspath có các transitive libraries từ BeanUtils trong ví dụ.

### 7.4. File Java 17 hoàn chỉnh

`src/main/java/demo/Main.java`:

~~~java
package demo;

public final class Main {
    private Main() {
    }

    private static boolean present(String classFile) {
        return Main.class.getClassLoader().getResource(classFile) != null;
    }

    public static void main(String[] args) {
        System.out.println("beanutils=" +
                present("org/apache/commons/beanutils/BeanUtils.class"));
        System.out.println("logging=" +
                present("org/apache/commons/logging/LogFactory.class"));
        System.out.println("collections3=" +
                present("org/apache/commons/collections/FastHashMap.class"));
    }
}
~~~

**Đây là một chương trình Java 17 biên dịch/chạy được**. Nó dùng `ClassLoader.getResource(...)` để xem class file có trong runtime classpath không; không buộc JVM tải và thực thi các method của thư viện được kiểm tra.

### 7.5. Chạy phiên bản chưa exclude

Đứng ở root `exclusion-lab`:

~~~bash
gradle --quiet run
~~~

Với graph như ví dụ chuẩn và không có cấu hình khác, **stdout do Java in**:

~~~text
beanutils=true
logging=true
collections3=true
~~~

Ba dòng chứng minh class files hiện diện, **không** chứng minh tất cả thư viện tương thích với ứng dụng. Gradle `run` chỉ có thể hoạt động sau khi resolve được dependencies và tìm thấy toolchain cần thiết.

### 7.6. Xem tree trước exclusion

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Trong report, nhánh module liên quan sẽ có dạng (rút gọn, không phải stdout đầy đủ):

~~~text
commons-beanutils:commons-beanutils:1.9.4
+--- commons-logging:commons-logging:1.2
\--- commons-collections:commons-collections:3.2.2
~~~

Hãy ghi lại graph này để so sánh. Tập các dependency thực tế có thể có thông tin version conflict, attributes và marker báo cáo phụ thuộc Gradle/version.

### 7.7. Thay đúng một block để exclude collections3

Giữ nguyên file `build.gradle.kts`, chỉ thay `dependencies { ... }` thành:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }
}
~~~

Chạy:

~~~bash
gradle --quiet run
~~~

Trong project thí nghiệm này không có đường khác kéo collections3 trở lại, nên stdout Java là:

~~~text
beanutils=true
logging=true
collections3=false
~~~

Giải thích: `commons-beanutils` vẫn được khai báo trực tiếp; `commons-logging` vẫn được kéo theo; class resource `FastHashMap.class` từ collections3 không còn. Đó là một kiểm tra **module presence**, không phải chứng minh tất cả chức năng BeanUtils chạy an toàn nếu thiếu collections3.

### 7.8. Xem tree sau exclusion

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Nhánh rút gọn sẽ còn:

~~~text
commons-beanutils:commons-beanutils:1.9.4
\--- commons-logging:commons-logging:1.2
~~~

Đây là graph dự kiến của đúng ví dụ, không mô tả mọi biến thể trong một project thực tế.

### 7.9. Thêm direct dependency để kiểm tra một đường khác

Tiếp tục thay block dependencies bằng:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("commons-collections:commons-collections:3.2.2")
}
~~~

Chạy `gradle --quiet run` trong project mới, stdout lại là:

~~~text
beanutils=true
logging=true
collections3=true
~~~

Vì module collections3 đã **được khai báo trực tiếp**. Rule exclude trong BeanUtils không thể xóa direct declaration thứ hai.

### 7.10. Kiểm tra mã Java riêng bằng javac/java

Nếu chỉ có JDK 17 và chưa dùng Gradle, bạn vẫn có thể xác nhận file Java hợp lệ:

~~~bash
javac -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Vì classpath của lệnh `java` này chỉ chứa `out`, không có JAR bên ngoài, stdout **chính xác**:

~~~text
beanutils=false
logging=false
collections3=false
~~~

Thí nghiệm javac/java này **không kiểm chứng Gradle exclusions**; nó chỉ cho thấy mã Java tự biên dịch được và phương thức tìm resource phản ánh classpath được cấp. Để kiểm tra thực tế Gradle, dùng `gradle run` và `gradle dependencies`.

### 7.11. Gradle Wrapper và Windows

Nếu project có Wrapper, nên dùng bản Gradle cố định của dự án:

~~~bash
# macOS/Linux
./gradlew --quiet run
./gradlew dependencies --configuration runtimeClasspath
~~~

~~~bat
rem Windows Command Prompt
gradlew.bat --quiet run
gradlew.bat dependencies --configuration runtimeClasspath
~~~

Nếu chưa có Wrapper thì `gradlew`/`gradlew.bat` chưa tồn tại; dùng bản Gradle tương thích đã cài để tạo Wrapper khi cần. Bạn phải có JDK 17 hoặc toolchain provisioning được cấu hình. Với Maven Central không sẵn mạng và artifact chưa nằm trong cache, lỗi resolution không đồng nghĩa `exclude` sai.

## 8. Ví dụ nhiều nhánh: opencsv và commons-collections

Để quan sát trường hợp một đường khác đưa module trở lại, thay block dependencies trong project thí nghiệm bằng:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("com.opencsv:opencsv:4.6")
}
~~~

Chạy:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --dependency commons-collections --configuration runtimeClasspath
~~~

Trong graph theo hướng dẫn Gradle, `opencsv` có đường tới `commons-beanutils` không mang exclusion, do đó `commons-collections` vẫn hiện diện. Nếu kết quả của một phiên bản thư viện mới khác đi, tin vào report của **graph đang chạy**, không ép theo một sơ đồ cũ.

Muốn loại ở cả hai nhánh (chỉ khi đã xác nhận các code paths thực sự không cần):

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("com.opencsv:opencsv:4.6") {
        exclude(group = "commons-collections", module = "commons-collections")
    }
}
~~~

Đừng tự thêm exclusion cho `org.apache.commons:commons-collections4` chỉ vì nó có tên gần giống collections3; đây là module khác và có thể phục vụ một API khác.

## 9. Hai lệnh phải biết: dependencies và dependencyInsight

### 9.1. Kiểm tra từng resolved classpath

~~~bash
gradle dependencies --configuration compileClasspath
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
~~~

Bảng:

| Configuration | Ý nghĩa cần kiểm tra |
| --- | --- |
| `compileClasspath` | Những module cần cho compile mã chính |
| `runtimeClasspath` | Những module cần khi chạy ứng dụng |
| `testCompileClasspath` | Những module cần compile test |
| `testRuntimeClasspath` | Những module có khi thực thi test |

**Đừng nhầm scope:** Exclusion chỉ ở runtimeClasspath có thể không ảnh hưởng compileClasspath. Và testRuntimeClasspath có thể có module thông qua testImplementation mà runtimeClasspath mã chính không có.

Các marker Gradle report hữu ích:

- `(*)`: subtree bị lặp nên được rút gọn khi in báo cáo, **không phải** thông báo exclusion.
- `(c)`: dependency constraint.
- `(n)`: dependency hoặc configuration không thể resolve trong report.

### 9.2. Tìm tất cả đường đến module

~~~bash
gradle dependencyInsight --dependency commons-collections --configuration runtimeClasspath
~~~

`dependencyInsight` tập trung vào một module, hiển thị những đường đi liên quan và lý do chọn version. Dùng **đúng resolved configuration của task đang gặp vấn đề**.

Không dùng `--single-path` trong bước khảo sát đầu tiên nếu mục tiêu là tìm nhiều đường đi, vì flag đó chỉ cho một đường, dễ bỏ sót nhánh khác kéo module vào graph.

### 9.3. Nhận diện version conflict

Nếu report ghi:

~~~text
org.example:utility:1.2 -> 1.7
~~~

điều đó thường có nghĩa một version khác đã được chọn trong resolution. Nó không tự nói module phải bị exclude. Khi vấn đề là chọn version tương thích, dùng constraints/BOM/platform hoặc mechanisms tương ứng, rồi kiểm chứng bằng `dependencyInsight` và tests.

### 9.4. Quy trình điều tra có thể lặp lại

1. Ghi nhận triệu chứng: compile fail, runtime fail, test fail, duplicate class, security alert, size bất thường.
2. Xác định **configuration đang được resolve**: compile, runtime, test, annotation processor, custom tool...
3. Chạy `dependencies --configuration ...`, chụp snapshot graph hiện tại.
4. Chạy `dependencyInsight --dependency group:name --configuration ...`, xem tất cả đường tới module.
5. Đọc tài liệu/metadata của dependency cha và xác minh module có thực sự thừa trong code path bạn dùng không.
6. Đặt exclusion **hẹp nhất** có thể; chỉ rõ cả group và module.
7. Chạy lại **cùng hai lệnh**; so sánh module/version thực sự.
8. Chạy compile/test/integration/smoke trên classpath gần production.
9. Kiểm tra distribution/fat JAR/container nếu việc đóng gói phức tạp.
10. Ghi chú lý do và điều kiện gỡ bỏ rule khi nâng phiên bản thư viện cha.

## 10. Tránh loại nhầm thư viện cần thiết ở runtime

### 10.1. “Ứng dụng không import B” không đủ

Nếu BeanUtils hoặc bất kỳ library A nào gọi API của B khi triển khai một tính năng, việc app không import B chỉ chứng tỏ Java source của app không dùng B **trực tiếp**. Khi gọi tính năng của A, JVM vẫn cần B.

Vì thế một bài test chỉ kiểm tra `BeanUtils.class` có trên classpath hoặc một phương thức đơn giản chạy được **không** chứng minh rằng toàn bộ BeanUtils an toàn khi thiếu Commons Collections.

### 10.2. Vì sao test pass nhưng production crash?

- Unit test mock dependency cha và không gọi implementation thật.
- Test chỉ dùng một subset API.
- `testRuntimeClasspath` có B từ test-only dependency, che việc `runtimeClasspath` thiếu B.
- B chỉ được yêu cầu khi xử lý dữ liệu hiếm, driver đặc thù hoặc reflective loader.
- `run` trong IDE có classpath khác distribution/container.
- Module bị exclude ở một project nhưng được kéo trở lại trong môi trường test.

Cần chạy **smoke test/integration test** bao phủ chức năng thực tế sau khi exclude và xác minh artifact sản xuất.

### 10.3. Lỗi thường xuất hiện khi thiếu module

~~~text
java.lang.NoClassDefFoundError: some/package/RequiredType
~~~

Có thể do class không còn trên runtime classpath hoặc lỗi liên kết/khởi tạo class. Xem stacktrace, `Caused by` và path của missing class. Đừng tự kết luận chính xác module chỉ từ tên exception nếu một class có thể có trong nhiều JAR.

~~~text
java.lang.ClassNotFoundException: some.package.RequiredType
~~~

Thường liên quan một class loader không tìm được tên lớp được yêu cầu, đặc biệt với reflection.

~~~text
java.lang.NoSuchMethodError: some.package.Client.perform()
~~~

Thường cần kiểm tra ABI/version mismatch; loại module chưa chắc chữa đúng vấn đề.

### 10.4. Việc loại nhầm có thể chỉ ảnh hưởng production

Một module bị loại không nhất thiết làm `compileJava` fail nếu Java compiler không cần class từ module đó để compile source của project. Nhưng thư viện bên thứ ba có thể tham chiếu class đó khi chạy. Vì vậy **thành công khi build không phải bằng chứng an toàn**.

## 11. Khi không nên exclude: quản lý version và variant

Nếu vấn đề là module X tồn tại nhưng **phiên bản đang được chọn không đúng**, loại toàn bộ X có thể gây mất tính năng. Các cơ chế nên cân nhắc:

| Công cụ | Mục đích |
| --- | --- |
| **Dependency constraints** | Diễn đạt yêu cầu/hạn chế version |
| **BOM/platform** | Đồng bộ nhiều phiên bản thư viện liên quan |
| **Rich versions** (`strictly`, `reject`) | Tránh/chặn phiên bản không chấp nhận |
| **Component metadata rules** | Điều chỉnh metadata dependency công bố sai |
| **Capabilities** | Mô hình hóa những implementations cạnh tranh |
| **Dependency substitution** | Thay module bằng module/project khác |
| **Dependency locking** | Cố định kết quả resolve để dễ tái tạo |
| **Exclude** | Loại module thực sự không cần trong phạm vi đã xác định |

Ví dụ Kotlin DSL về dependency constraint:

~~~kotlin
dependencies {
    constraints {
        implementation("org.apache.commons:commons-lang3:3.14.0") {
            because("Dùng phiên bản đã kiểm thử")
        }
    }
}
~~~

Constraint là **một yêu cầu chọn phiên bản nếu module tham gia graph**, không tự thêm module vào graph. Đây là đoạn minh họa dùng trong project đã áp dụng Java plugin; nó không tự thiết lập repository.

Trường hợp nhiều logging implementations hoặc modules thay thế nhau, dùng capability/conflict modeling thích hợp có thể rõ ràng hơn việc loại một nhóm module trên mọi configuration. Gradle có thể chọn variant/runtime khác nhau dựa vào attributes, nên việc “cùng tên nhóm” chưa đủ để quyết định exclude.

## 12. Exclude theo configuration nào là đúng?

Với Java/JVM plugin, mỗi scope có nhiệm vụ riêng:

| Scope/configuration | Vai trò |
| --- | --- |
| `implementation` | Dependency dùng compile và runtime mã chính |
| `compileOnly` | Chỉ dùng ở compile mã chính |
| `runtimeOnly` | Chỉ cần khi chạy mã chính |
| `annotationProcessor` | Dùng cho annotation processing |
| `testImplementation` | Thư viện dùng compile/run test |
| `testRuntimeOnly` | Chỉ dùng trong runtime của test |
| `compileClasspath` | Resolvable classpath cho `compileJava` |
| `runtimeClasspath` | Resolvable classpath cho `run` hoặc application runtime |
| `testCompileClasspath` | Resolvable classpath cho compile test |
| `testRuntimeClasspath` | Resolvable classpath cho test |

Nếu một annotation processor thực sự cần helper B, exclude B từ `annotationProcessor` có thể khiến compile hỏng; tác động sẽ khác so với exclusion ở runtimeClasspath. Tương tự, loại test engine/launcher bắc cầu có thể khiến test không khởi động.

**Chỉ gắn rule lên dependency/configuration thực sự liên quan**. Trước khi kết luận cần global exclusion, phải xem graph của từng consumer quan trọng.

## 13. Exclude trong multi-project build

Ví dụ có `:app` và `:library`:

~~~kotlin
// app/build.gradle.kts, đã có Java/Application plugin.
dependencies {
    implementation(project(":library")) {
        exclude(group = "org.example", module = "legacy-helper")
    }
}
~~~

Đây là **đoạn minh họa**, không phải project chạy độc lập. Nó giả định `settings.gradle.kts` đã `include(":app", ":library")` và library có variant mà app tiêu thụ được.

Khi app phụ thuộc library:

- Một module có thể xuất hiện qua project dependency hoặc qua external dependencies khác của app.
- Exclude trong app **không xóa** dependency declaration khỏi library build script.
- `java-library` có `api`/`implementation` khác nhau, ảnh hưởng compile/runtime variants mà consumer nhìn thấy.
- Không dùng `extendsFrom` xuyên project để “đẩy” exclusion: `extendsFrom` là quan hệ configuration trong **một** project.
- Nếu một module được đưa vào qua nhiều project paths, cần kiểm tra `:app:dependencies`/`:app:dependencyInsight` với configuration phù hợp.

Một sửa đổi exclusion ở root project có thể ảnh hưởng nhiều subprojects nếu bạn áp dụng qua `allprojects`/`subprojects` hoặc cấu hình chung, nên tránh lan rộng không cần thiết.

## 14. Exclude và file/package có phải cùng việc không?

**Không.** Phân biệt:

| Cú pháp | Tác động |
| --- | --- |
| `implementation("A") { exclude(group, module) }` | Loại dependency module trong nhánh resolution |
| `configurations.named("runtimeClasspath") { exclude(...) }` | Loại module theo configuration |
| `tasks.register<Copy>("copy") { exclude("**/*.tmp") }` | Bỏ file path khi copy |
| `gradle build -x test` | Bỏ task `test` khỏi task execution |
| `.gitignore` | Điều khiển Git tracking |
| `jar { exclude("...") }` | Lọc file entry khi đóng gói JAR |
| `packaging/resources { ... }` | Chính sách của plugin đóng gói, có thể khác dependency resolution |

Nếu file đã nằm trong một fat JAR do plugin khác tạo, exclusion trên một configuration chỉ có tác dụng **khi plugin thực sự dùng configuration đó**. Kiểm tra archive thật, không chỉ xem Gradle dependency report.

Exclusion cũng không xóa artifact đã tải khỏi cache và không tự cập nhật đầy đủ mọi report SBOM/vulnerability/license. Khi mục tiêu là security/compliance, phải xem **artifact đã phân phối** và metadata đầu ra theo quy trình của dự án.

## 15. Bảo trì lâu dài: ghi nguyên nhân và kiểm thử

Không nên để một exclusion “bí ẩn” trong dự án:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        // Chỉ giữ rule khi integration/smoke test xác nhận
        // chức năng sử dụng không yêu cầu Commons Collections 3.x.
        // Xem quyết định dependency của dự án.
        exclude(group = "commons-collections", module = "commons-collections")
    }
}
~~~

Gợi ý reviewer hỏi:

1. Module bị loại đã được chỉ định **đúng group + module** chưa?
2. Có báo cáo `dependencyInsight` xác nhận đường tới module không?
3. Vì sao module **không cần**, thay vì chỉ “version không thích hợp”?
4. Có cách nào đặt rule hẹp hơn không?
5. Có còn đường khác kéo module vào graph không?
6. Compile, runtime, test và distribution classpaths còn đủ không?
7. Các code path của thư viện cha có integration/smoke tests chưa?
8. Việc loại ảnh hưởng tới API của consumer/project khác không?
9. Khi nâng version thư viện cha, có cần giữ rule cũ không?
10. Có ghi issue/ADR để sau này giải thích không?

Một rule có thể hợp lý hôm nay nhưng nguy hiểm sau khi nâng thư viện cha, vì dependency metadata và code paths thay đổi. Kiểm tra lại khi nâng cấp quan trọng.

## 16. Lỗi thường gặp và cách sửa

### Lỗi 1. Sai group/module

`commons-collections:commons-collections` khác `org.apache.commons:commons-collections4`. Dùng report để lấy đúng tọa độ, không đoán theo một phần tên.

### Lỗi 2. Một exclude không đủ vì có nhánh khác

Chạy `dependencyInsight` và xác định mọi đường. Nếu các nhánh khác thực sự cần module, **không nên loại toàn bộ** chỉ để làm graph “đẹp”.

### Lỗi 3. Exclude group quá rộng

~~~kotlin
exclude(group = "org.apache.commons")
~~~

Có thể loại nhiều modules cần thiết. Thu hẹp bằng `module = "tên-thực-tế"`.

### Lỗi 4. Dùng `isTransitive = false` để bỏ đúng một JAR

Cách này bỏ mọi dependency bắc cầu qua declaration đó; dễ gây thiếu logging/parser/helper. Dùng per-dependency exclude nếu chỉ một module không cần.

### Lỗi 5. Chỉ kiểm tra compileClasspath

Bài toán ở runtime thì phải kiểm tra `runtimeClasspath` và packaged application. Sửa exclusion ở runtimeClasspath có thể không thay đổi compileClasspath.

### Lỗi 6. Thấy `(*)` trong report và tưởng module bị exclude

`(*)` chỉ rút gọn subtree lặp, không có nghĩa module bị loại khỏi graph.

### Lỗi 7. Module chỉ cần trong một code path hiếm

Unit test pass nhưng production fail vì reflection/driver/ServiceLoader. Bổ sung smoke/integration tests của chức năng dùng thực tế.

### Lỗi 8. Exclude để giải quyết version conflict

Nếu module vẫn cần, sử dụng constraint/BOM/platform phù hợp; loại module có thể tạo `NoClassDefFoundError`.

### Lỗi 9. Configuration-wide rule lan sang những classpaths khác

`implementation` là scope declarable thường được nhiều classpaths kế thừa; configuration-level exclude tại đây có thể gây tác động rộng hơn mong muốn.

### Lỗi 10. Dùng exclude để sửa fat JAR mà không biết input task

Plugin tạo fat JAR có thể dùng configuration khác hoặc thêm file tùy biến. Phải kiểm tra graph và file đầu ra thật, không suy luận từ `runtimeClasspath` duy nhất.

### Lỗi 11. Cố loại “chỉ version 1.2”

Rule exclude không lựa chọn version theo kiểu “không lấy 1.2 nhưng lấy 1.3”. Dùng rich version constraint/reject hoặc resolution rule cho yêu cầu chọn version.

### Lỗi 12. Test-only dependency che lỗi runtime production

So sánh `runtimeClasspath` và `testRuntimeClasspath`. Nếu test classpath có B do một test library khác nhưng production không có, hãy thêm test trên production-like runtime classpath.

## 17. Bài tập kèm đáp án

### Bài 1. Viết rule hẹp

Cho:

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4")
}
~~~

Chỉ bỏ `commons-collections` qua BeanUtils, không bỏ `commons-logging`.

**Đáp án:**

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }
}
~~~

### Bài 2. Direct dependency vẫn có mặt

~~~kotlin
dependencies {
    implementation("commons-beanutils:commons-beanutils:1.9.4") {
        exclude(group = "commons-collections", module = "commons-collections")
    }

    implementation("commons-collections:commons-collections:3.2.2")
}
~~~

Collections3 có biến mất không?

**Đáp án:** Không. Direct dependency thứ hai vẫn mang nó vào runtime graph.

### Bài 3. Một nhánh khác mang module vào

A và B đều kéo X; chỉ A có `exclude(X)`. X còn không?

**Đáp án:** Có thể còn qua B. Chạy `dependencyInsight` để kiểm tra đường thực tế; chỉ loại B khi đã xác nhận an toàn.

### Bài 4. Tắt mọi transitive có phù hợp?

Bạn chỉ muốn bỏ X nhưng viết:

~~~kotlin
implementation("org.example:parent:1.0") {
    isTransitive = false
}
~~~

**Đáp án:** Không tương đương. Nó loại mọi transitive qua parent, có thể bỏ cả Y/Z cần thiết. Nên dùng exclude đúng X.

### Bài 5. Chọn scope

Muốn xem module nào được ứng dụng Java dùng lúc chạy, giữa `compileClasspath` và `runtimeClasspath` chọn cái nào?

**Đáp án:** `runtimeClasspath`. Kiểm tra thêm classpath của distribution/task nếu plugin đóng gói khác cấu hình này.

### Bài 6. Lệnh truy vết module

Muốn biết module `commons-collections` đến từ đâu trong runtime:

~~~bash
gradle dependencyInsight --dependency commons-collections --configuration runtimeClasspath
~~~

**Đáp án:** Lệnh trên đúng. Không dùng `--single-path` trong bước đầu nếu phải xem tất cả nhánh.

### Bài 7. Loại một group có nguy hiểm?

~~~kotlin
exclude(group = "org.apache.commons")
~~~

**Đáp án:** Có. Rule rộng có thể loại nhiều artifact của group. Chỉ ra `module` khi có bằng chứng cụ thể.

### Bài 8. Tại sao Java chương trình vẫn chạy sau exclude?

Thí nghiệm mục 7 sau exclusion in `collections3=false` nhưng `gradle run` thành công. Điều này chứng minh BeanUtils không bao giờ cần Commons Collections?

**Đáp án:** Không. Chương trình chỉ kiểm tra **sự hiện diện của class file**, không gọi tất cả BeanUtils APIs. Cần test các code paths được ứng dụng sử dụng.

### Bài 9. Exclude và version conflict

Module X cần có nhưng version 1.2 bị lỗi; bạn muốn version 1.5. Có nên exclude X?

**Đáp án:** Không mặc định. Dùng constraints/versions/platform đúng cách, kiểm tra compatibility và resolved graph.

### Bài 10. Per-dependency vs per-configuration

So sánh:

~~~kotlin
implementation("commons-beanutils:commons-beanutils:1.9.4") {
    exclude(group = "commons-collections", module = "commons-collections")
}
~~~

với:

~~~kotlin
configurations.named("runtimeClasspath") {
    exclude(group = "commons-collections", module = "commons-collections")
}
~~~

**Đáp án:** Đoạn đầu chỉ gắn exclusion lên một dependency declaration; đoạn sau gắn rule trên runtime configuration và có thể ảnh hưởng nhiều nhánh. Hai scope khác nhau, không thay thế máy móc cho nhau.

### Bài 11. Lỗi runtime

Sau khi exclude X, production xuất hiện `NoClassDefFoundError` của class thuộc X. Hành động hợp lý?

**Đáp án:** Kiểm tra stacktrace/graph/runtime; gỡ exclusion nếu X là dependency bắt buộc hoặc thay bằng một giải pháp khác tương thích; thêm integration test code path gây lỗi.

### Bài 12. Kiểm tra lại khi nâng thư viện

Thư viện A v2 không còn phụ thuộc X như v1; rule exclude X còn tác dụng không?

**Đáp án:** Có thể không còn cần. Hãy xem metadata/graph mới, loại bỏ rule thừa nếu đã xác minh và kiểm thử. Không mặc định giữ mọi exclusion vô hạn.

## 18. Tờ ghi nhớ

| Cần làm gì? | Cú pháp / nguyên tắc |
| --- | --- |
| Loại một transitive module trong nhánh A | `implementation("A") { exclude(group = "g", module = "x") }` |
| Loại module trong một configuration | `configurations.named("runtimeClasspath") { exclude(group = "g", module = "x") }` |
| Tắt mọi transitive qua A | `isTransitive = false` — chỉ khi thực sự muốn điều đó |
| Tìm resolved graph | `gradle dependencies --configuration runtimeClasspath` |
| Truy nguyên module/phiên bản | `gradle dependencyInsight --dependency x --configuration runtimeClasspath` |
| Một đường exclude, đường khác vẫn yêu cầu | Module **có thể vẫn xuất hiện** |
| X tồn tại nhưng version không phù hợp | Constraints, BOM/platform, rich versions |
| X cần bởi code path hiếm | **Không exclude** trước khi kiểm chứng chức năng |
| Chỉ test mà runtime production khác | Kiểm tra cả distribution/smoke test |
| Exclude cả group | Tránh nếu chỉ một module cần loại |
| Gradle dependency exclude | **Không** phải file filtering hoặc bỏ task |

**Kết luận:** Exclusion thành công không phải là làm cho dependency report ngắn nhất, mà là tạo classpath **đúng, đầy đủ và kiểm chứng được**. Bắt đầu từ nhu cầu thật, tìm mọi đường tới module, chỉ loại đúng group/module trong phạm vi nhỏ nhất, so sánh graph trước/sau, và kiểm thử các code paths sử dụng thư viện. Nếu module vẫn cần nhưng version không phù hợp, hãy giải quyết vấn đề **version** thay vì loại nó.

## Tài liệu chính thức

- [Gradle — How to Exclude Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html)
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Using Resolution Rules](https://docs.gradle.org/current/userguide/resolution_rules.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
- [Gradle — ModuleDependency.exclude API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts/-module-dependency/exclude.html)
- [Gradle — Configuration.exclude API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts/-configuration/exclude.html)
