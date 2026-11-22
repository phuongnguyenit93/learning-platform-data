# Tiêu thụ BOM bằng `platform` và `enforcedPlatform` trong Gradle

## 1. Mục tiêu và vấn đề cần giải quyết

Một ứng dụng Java thường dùng nhiều thư viện của cùng một hệ sinh thái: Jackson gồm `jackson-databind`, `jackson-core`, `jackson-annotations`; Spring và JUnit cũng có các module cần phối hợp version. Nếu mỗi module đều tự ghi version, ứng dụng có thể gặp lỗi API/ABI như `NoSuchMethodError`, `ClassNotFoundException` hoặc có bộ thư viện chưa từng được kiểm thử chung.

**Bill of Materials (BOM)** là một tập **quy tắc quản lý phiên bản** mà nhà phát hành công bố, thường dưới dạng Maven POM với phần `dependencyManagement`. Trong Gradle, bạn tiêu thụ BOM thông qua **platform dependency**:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Ở đây, `platform(...)` đưa **version constraints từ BOM** vào quá trình giải quyết dependency; nó **không tự đưa mọi JAR của BOM vào classpath**. Module `jackson-databind` được khai báo riêng và nhận version được điều phối bởi BOM.

Nếu cần bắt các module được BOM quản lý dùng version do BOM quy định, Gradle có `enforcedPlatform(...)`:

~~~kotlin
dependencies {
    implementation(enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Hai ví dụ là **hai lựa chọn thay thế**, không thêm cả hai BOM cùng lúc. `enforcedPlatform` sử dụng **forced versions** và có thể ghi đè lựa chọn version mà dependency khác yêu cầu. Quyết định này mạnh và có khả năng **lan sang consumer** khi thư viện publish dependency/metadata, nên không phải mặc định tốt cho thư viện dùng chung.

Sau bài học, bạn sẽ:

- Hiểu Maven BOM, Gradle platform, dependency constraints, requested/selected version và variant resolution.
- Biết khi nào dùng `platform`, khi nào cần `enforcedPlatform` và tại sao thường ưu tiên lựa chọn không cưỡng ép.
- Có một ví dụ **Java 17 + Gradle Kotlin DSL chạy được** sử dụng Jackson BOM mà không cần chỉ rõ version cho `jackson-databind`.
- Dùng `dependencies` và `dependencyInsight` để xác nhận phiên bản thực sự được chọn.
- Quản lý BOM qua **version catalog**, `java-platform` project và cấu hình test/runtime.
- Phân biệt import BOM với plugin `io.spring.dependency-management`, project dependency, artifact JAR, dependency locking và publication metadata.
- Xử lý conflict, nhiều BOM, thiếu version, BOM đặt sai scope và nguy cơ enforced versions ở downstream project.

Các phiên bản nêu trong bài là **mốc thực hành**, không phải khẳng định chúng là phiên bản mới nhất. Khi áp dụng thực tế phải kiểm tra tương thích JDK/Gradle/framework và chính sách cập nhật.

## 2. BOM là gì? Vì sao một BOM không phải thư viện để import Java?

Maven BOM thường là một POM có `<packaging>pom</packaging>` và một nhóm entries quản lý version trong `<dependencyManagement>`. Ví dụ minh họa cấu trúc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>example-bom</artifactId>
    <version>1.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.example</groupId>
                <artifactId>core</artifactId>
                <version>1.7</version>
            </dependency>
            <dependency>
                <groupId>org.example</groupId>
                <artifactId>adapter</artifactId>
                <version>1.4</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

Đây là **mô hình XML minh họa**, không phải một BOM đã được publish tại Maven Central. Nó nêu hai modules, nhưng khi Gradle tiêu thụ BOM, chỉ những module **được một dependency khác yêu cầu** mới xuất hiện trên classpath. Nếu ứng dụng chỉ khai báo `org.example:core`, BOM không tự đem `adapter` vào.

Một module BOM:

- **Không** nhất thiết có JAR để code Java `import` một class.
- **Không** có nghĩa nó đã khai báo dependency runtime đến mọi module được liệt kê.
- Chủ yếu góp các **version constraints** cho những module có mặt trong dependency graph.
- Có thể quản lý các version **khác nhau** cho các module: đừng giả định tất cả modules trong BOM phải cùng một số version.
- Có thể import BOM khác hoặc thể hiện version properties/rules qua Maven metadata; Gradle xử lý theo định dạng và khả năng metadata mà repository cung cấp.

**Một câu ghi nhớ:** BOM trả lời “**nếu** dùng module này, nên/chỉ được dùng version nào?”, còn dependency declaration trả lời “ứng dụng **có dùng** module này không?”.

## 3. `platform`: nhập constraints nhưng không ép version bất chấp graph

Gradle cung cấp hàm `platform(...)` trong dependency DSL. Nó biến dependency được truyền thành **platform dependency**, để Gradle tiêu thụ BOM/Gradle platform theo metadata quản lý version.

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))

    // Không cần ghi version ở từng module được BOM quản lý.
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.core:jackson-core")
}
~~~

Đây là **ví dụ độc lập về cú pháp**, project có plugin Java và Maven Central. Hai module được khai báo **trực tiếp**; BOM quyết định ràng buộc về version. Các module khác như `jackson-annotations` có thể xuất hiện **bắc cầu** theo metadata của Jackson và được BOM quản lý khi có mặt.

### Nó ảnh hưởng những gì?

1. `platform(...)` làm graph chứa **platform component** và các version constraints đã import.
2. Các dependency yêu cầu module trong BOM được giải quyết **cùng với** constraints, transitive dependencies và những version yêu cầu ở nơi khác.
3. Nếu một module chưa ai yêu cầu, BOM **không tự thêm** module đó.
4. Nếu graph có yêu cầu version mạnh hơn/higher version phù hợp, `platform` thông thường **không tự force quay về** con số BOM. Selected version có thể cao hơn một recommendation trong BOM.
5. Khi dùng Gradle platform có **strict version constraints**, Gradle có cơ chế `endorseStrictVersions` theo mặc định đối với dependency `platform`. Đây là chi tiết nâng cao: với BOM Maven thường chứa constraints không phải strict, còn một Gradle platform tự publish có thể mang rich/strict constraints. Không rút gọn thành “platform luôn yếu trong mọi hoàn cảnh”.

Vì Gradle có conflict resolution, **version trong BOM không đồng nghĩa exact lock**. Trong code review cần phân biệt **requested by BOM**, **requested by dependency**, và **selected by resolution**.

## 4. Ví dụ chạy được: Java 17 và Jackson BOM

Ta viết một chương trình Java tạo JSON bằng Jackson, để việc dùng BOM được kiểm chứng từ chính build.

### 4.1. Thư mục project

~~~text
bom-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/example/App.java
~~~

Gradle Wrapper phải có sẵn và hoạt động với JDK 17+; nếu máy chưa có Wrapper, tạo theo quy trình Gradle chính thức trước. Mã Java dùng JDK 17 nhưng chỉ cần API chuẩn của Java 8+ ngoài Jackson.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "bom-lab"
~~~

### 4.2. Toàn bộ `build.gradle.kts`

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
    // BOM chỉ quản lý version các module Jackson.
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))

    // Module thực sự được yêu cầu, không ghi version riêng.
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

`application` cung cấp task `run` cùng Java compilation. `mavenCentral()` cần thiết vì đây là **external module dependencies** — khác với `files("libs/x.jar")` trỏ JAR cục bộ. `java.toolchain` yêu cầu Java 17 cho compilation; môi trường cần JDK cài sẵn hoặc provisioning phù hợp.

### 4.3. `src/main/java/example/App.java`

~~~java
package example;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("topic", "Gradle BOM");
        values.put("level", 17);

        ObjectMapper mapper = new ObjectMapper();
        System.out.println(mapper.writeValueAsString(values));
    }
}
~~~

`LinkedHashMap` giữ thứ tự insertions để dòng JSON được minh họa ổn định. `ObjectMapper` thuộc `jackson-databind`; chương trình không dùng module `jackson-core` trực tiếp, dù Jackson có thể yêu cầu nó transitively.

### 4.4. Lệnh chạy và stdout

~~~bash
./gradlew --version
./gradlew -q run
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency com.fasterxml.jackson.core:jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency com.fasterxml.jackson.core:jackson-core --configuration runtimeClasspath
~~~

Khi đã resolve được dependencies và chạy thành công, **dòng do `App.main` in** là:

~~~text
{"topic":"Gradle BOM","level":17}
~~~

Không dự đoán toàn bộ log Gradle: tải dependencies, JDK toolchain, daemon, Configuration Cache và repository có thể tạo thông báo khác. Nếu `run` thất bại vì không có mạng/proxy/repository, xử lý nguyên nhân resolution trước khi đổ lỗi cho `platform`.

### 4.5. Quan sát graph

Bạn kỳ vọng:

- `jackson-bom:2.17.2` xuất hiện như **platform dependency** cung cấp constraints.
- `jackson-databind` được chọn version tương thích BOM, thường là `2.17.2` trong graph mẫu không có yêu cầu khác.
- `jackson-core` và `jackson-annotations` có thể xuất hiện qua transitive dependency của databind, và cũng được BOM quản lý khi constraints tương ứng có mặt.
- Không phải tất cả module trong Jackson BOM đều nằm trên classpath; chỉ những module được yêu cầu.

Minh họa rút gọn, **không phải transcript chính xác**:

~~~text
runtimeClasspath
+--- com.fasterxml.jackson:jackson-bom:2.17.2
|    +--- com.fasterxml.jackson.core:jackson-databind:2.17.2 (c)
|    +--- com.fasterxml.jackson.core:jackson-core:2.17.2 (c)
|    \--- ...
\--- com.fasterxml.jackson.core:jackson-databind -> 2.17.2
     +--- com.fasterxml.jackson.core:jackson-annotations:...
     \--- com.fasterxml.jackson.core:jackson-core:...
~~~

Ký hiệu `(c)` trong `dependencies` thường đánh dấu **constraint**, không phải một artifact thứ hai. Nếu một node ghi `2.16.1 -> 2.17.2`, nó nghĩa là requested version khác selected version. Khi muốn biết chính xác vì sao Gradle chọn version, dựa vào `dependencyInsight`, không chỉ nhìn danh sách JAR được tải.

## 5. `enforcedPlatform`: vì sao khả năng ép version nguy hiểm?

Kotlin DSL:

~~~kotlin
dependencies {
    implementation(enforcedPlatform(
        "com.fasterxml.jackson:jackson-bom:2.17.2"
    ))
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Đây là **mẫu thay thế** cho `implementation(platform(...))` của cùng BOM, **không đặt cả hai trong một file để so sánh**. Khi dùng `enforcedPlatform`, các versions mà platform quản lý có thể **được force** đối với module tương ứng trong resolved graph. Các direct/transitive version requests khác có thể bị ghi đè, kể cả yêu cầu mới hơn.

Ví dụ khái niệm:

~~~text
BOM enforced: jackson-databind = 2.17.2
Dependency A: jackson-databind = 2.18.1

platform(BOM) thông thường:
  dependency constraints + requests được giải quyết chung;
  version 2.18.1 có thể được chọn nếu thỏa các yêu cầu.

enforcedPlatform(BOM):
  version do BOM force thường được áp dụng;
  selected jackson-databind có thể bị giữ ở 2.17.2.
~~~

Đây là **minh họa cơ chế**, không phải bảo đảm mọi trường hợp có rich strict constraints/rules đều sẽ resolve thành công. Một số xung đột nghiêm ngặt có thể gây resolution error; nếu có constraints khác, hãy xem error và `dependencyInsight`.

### So sánh trực tiếp

| Câu hỏi | `platform(...)` | `enforcedPlatform(...)` |
| --- | --- | --- |
| Import BOM constraints? | Có. | Có. |
| Tự thêm mọi module trong BOM? | **Không.** | **Không.** |
| Có thể chọn version cao hơn BOM khi graph yêu cầu? | Có trong tình huống thông thường, tùy các constraints. | Bị force theo platform, nên thường không. |
| Có thể ghi đè direct/transitive version request? | Áp constraints và conflict resolution, không mặc nhiên cưỡng ép. | **Có**, vì forced versions. |
| Dùng cho ứng dụng độc lập? | Thường là lựa chọn đầu tiên. | Chỉ khi cần chính sách version cưỡng ép và đã kiểm thử. |
| Dùng trong thư viện sẽ publish cho người khác? | Thường an toàn hơn về quản lý version. | **Cần tránh hoặc cân nhắc cực kỹ** vì tác động ép version có thể truyền sang consumer. |
| Thay thế dependency declaration đến module cụ thể? | Không. | Không. |
| Thay thế lockfile cho tính tái lập? | Không. | Không; còn thiếu các yêu cầu về version/artifact và build environment. |

**Phân biệt “BOM đưa ra một bộ version đã kiểm thử” với “BOM cần thắng mọi yêu cầu version khác”.** Một BOM được curate không có nghĩa ứng dụng phải áp `enforcedPlatform` vô điều kiện. Với thư viện có consumers khác nhau, cưỡng ép version là một quyết định ảnh hưởng người khác.

## 6. Thực nghiệm xung đột version: đừng đoán từ source

Để quan sát sự khác nhau, dùng bản sao `build.gradle.kts` của ví dụ Jackson.

### 6.1. Thử với `platform` thường

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))

    // Yêu cầu trực tiếp một version cao hơn ví dụ BOM.
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.1")
}
~~~

Trong graph đơn giản không có constraints mạnh khác, Gradle thường chọn `2.18.1` cho databind thay vì tự ép về `2.17.2`. Tuy nhiên BOM có thể vẫn quản lý các module Jackson khác ở version `2.17.2`; **trộn version Jackson có thể không an toàn** nếu các modules cần phối hợp. Không xem việc Gradle resolve thành công là bằng chứng binary compatibility.

Xem:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-annotations --configuration runtimeClasspath
./gradlew -q run
~~~

### 6.2. Thử với `enforcedPlatform`

Thay duy nhất platform declaration bằng:

~~~kotlin
dependencies {
    implementation(enforcedPlatform(
        "com.fasterxml.jackson:jackson-bom:2.17.2"
    ))
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.1")
}
~~~

Nếu tất cả constraints khác cho phép resolution, version được BOM force có thể thắng yêu cầu databind `2.18.1`. Điều này làm `enforcedPlatform` giống một chính sách **ép nền tảng của toàn graph**, chứ không phải hint thông thường.

**Không chạy hai phiên bản cùng lúc**. Đây là hai phương án thay thế để so sánh. Và không dùng tình huống ép thấp hơn làm cách khắc phục một lỗi an toàn bảo mật: việc downgrade có thể phục hồi lỗ hổng hoặc phá API mà module khác yêu cầu.

### 6.3. Cách giải thích report

Trong `dependencyInsight`, xem:

- **Requested**: version một dependency cụ thể đã yêu cầu.
- **Selected**: version cuối được dùng.
- **Selection reasons**: có thể thấy “By constraint”, “By conflict resolution”, “Forced” hoặc những reasons khác theo Gradle version.
- **Paths**: module nào kéo dependency vào graph?
- **Variants/attributes**: nếu version đúng nhưng classpath thiếu artifact hoặc xảy ra `No matching variant`, xem cả API/runtime variant.

Nếu `enforcedPlatform` được áp nhưng không thấy module A, có thể A **không có trong graph**. BOM không đưa mọi module vào; force version chỉ liên quan khi module được yêu cầu.

## 7. Tại sao `enforcedPlatform` có thể “rò” phiên bản sang consumer?

Giả sử bạn phát triển `:sdk` để publish. Nếu thư viện dùng:

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    api(enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    api("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Đây là **mảnh ví dụ**, trong project thực tế cần `repositories { mavenCentral() }` và publication cấu hình đúng. `api` công bố Jackson là phần API của library, đồng thời enforced platform áp chính sách version mạnh.

Gradle cảnh báo rằng **enforced platform là transitive**: khi library được tiêu thụ, những dependency constraints dạng forced có thể ảnh hưởng resolution của **consumer**, dù consumer có lựa chọn version khác. Khi publish, Gradle Module Metadata lưu những thông tin quản lý version/variant có thể tác động tới consumer Gradle. Maven POM biểu diễn một phần thông tin theo semantics Maven, nên hiệu ứng ở Maven consumer có thể khác; cần kiểm thử với công cụ thật.

**Với thư viện**, ưu tiên:

~~~kotlin
dependencies {
    api(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    api("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Hoặc dùng `implementation(platform(...))` nếu version management chỉ cần cho implementation của SDK và không chủ ý công bố như contract API. Quyết định `api`/`implementation` phải xuất phát từ API dependency của Java library, không phải chỉ từ thói quen copy ví dụ.

**Không khẳng định platform thường hoàn toàn không ảnh hưởng consumer**: khi library publish, các constraints có thể được công bố qua metadata theo variant và vẫn tham gia conflict resolution; điều khác biệt là **không cưỡng ép** như enforced platform.

### Khi enforced platform có thể hợp lý?

Một **application**/dịch vụ cuối không publish thư viện cho người khác đôi khi cần khóa một tập version do vendor kiểm thử, để giảm biến động khi có dependency khác yêu cầu version không phù hợp. Có thể dùng `enforcedPlatform` nếu:

1. Có lý do kỹ thuật rõ (ma trận tương thích, test thực, dependency bug đã biết).
2. Có chủ sở hữu policy và quy trình nâng version BOM định kỳ.
3. Kiểm thử toàn bộ runtimeClasspath/integration test, vì force có thể ép xuống phiên bản thiếu API.
4. Không vô tình xuất các forced requirements ra consumers khác.
5. Không dùng enforcement để bỏ qua lỗi cần sửa ở dependency graph.

Trong phần lớn app/library đơn giản, **bắt đầu với `platform` thường**, sau đó mới quyết định có cần force thật không.

## 8. Scope quan trọng: BOM cho production, test hay annotation processor?

Gradle dùng configuration scopes. Đặt BOM sai configuration có thể khiến “tôi đã import BOM mà module vẫn chưa có version”.

| Nơi khai báo | Graph chịu ảnh hưởng phổ biến | Lưu ý |
| --- | --- | --- |
| `implementation(platform(...))` | `compileClasspath` và `runtimeClasspath` sản phẩm Java, theo cấu hình plugin. | Thường dùng cho dependencies application. |
| `api(platform(...))` | API của `java-library`, có thể công bố constraints tới consumer. | Chỉ có `api` nếu áp dụng `java-library`. |
| `testImplementation(platform(...))` | Compile/runtime classpath cho test, theo inheritance/configuration. | Không mặc nhiên điều khiển runtime của ứng dụng sản phẩm. |
| `testRuntimeOnly(platform(...))` | Runtime của test, không có trên test compile classpath. | Dùng khi chỉ runtime cần alignment. |
| `annotationProcessor(platform(...))` | Annotation processor path. | Tách khỏi `implementation`, ví dụ Lombok/Micronaut processing. |
| `testAnnotationProcessor(platform(...))` | Test annotation processor path. | Chỉ khi toolchain/test processing có nhu cầu. |
| `runtimeOnly(platform(...))` | Runtime graph sản phẩm. | Không giúp một compile-only dependency thiếu version trên compile classpath. |

Một BOM import qua `implementation` không có nghĩa mọi **tách biệt configuration** (ví dụ `annotationProcessor`) tự dùng constraints đó. Nếu kapt/KSP/Android/plugin khác tạo configuration riêng, phải theo đúng API/scope của plugin ấy, không đoán rằng mọi dependency graph kế thừa từ `implementation`.

### BOM cho unit tests: ví dụ JUnit

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là **file build script mẫu** có thể sử dụng trong project có source test Java; không có `src/test` nên chạy `test` có thể là `NO-SOURCE`. `testImplementation(platform(...))` cung cấp constraints cho các modules JUnit có mặt trên test classpath; `testImplementation("org.junit.jupiter:junit-jupiter")` mới thực sự yêu cầu thư viện.

Để nhìn rõ trạng thái:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew test
~~~

`useJUnitPlatform()` nói Gradle Test task dùng JUnit Platform để khám phá/chạy tests, không có nghĩa nó tự tải JUnit dependencies; việc đó thuộc `dependencies`.

### Mẫu test runnable

`src/test/java/example/CalculatorTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
~~~

Với build script JUnit ở trên, test chạy thành công khi dependencies resolve đúng. Gradle mặc định không nhất thiết in stdout mỗi test; không bịa một dòng output `PASS` cố định. Có thể dùng `./gradlew test --info` hoặc mở HTML test report để xem kết quả. Mục này là **ví dụ bổ sung**, không thay thế project Jackson đầy đủ.

## 9. Version catalog không phải BOM

Trong `gradle/libs.versions.toml`:

~~~toml
[versions]
jackson = "2.17.2"

[libraries]
jackson-bom = { module = "com.fasterxml.jackson:jackson-bom", version.ref = "jackson" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind" }
jackson-core = { module = "com.fasterxml.jackson.core:jackson-core" }
~~~

Trong `build.gradle.kts`:

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(libs.jackson.bom))
    implementation(libs.jackson.databind)
    implementation(libs.jackson.core)
}
~~~

Đoạn trên minh họa cách dùng **version catalog aliases** cho BOM và modules. Để chạy như một app đầy đủ, còn cần `application.mainClass` và Java source phù hợp (xem mục 4).

**Hai chức năng khác nhau:**

- Version catalog chỉ giúp viết tọa độ module/version trong build script tập trung. Nó **không tự áp version của Jackson BOM lên cả project** nếu bạn không khai báo `platform(libs.jackson.bom)` trên đúng configuration.
- BOM/platform bổ sung **version constraints** vào dependency resolution graph. Nếu module chưa có ai yêu cầu, BOM không tự thêm module.
- Một alias có version riêng cho `jackson-databind` có thể tạo version request **cạnh tranh** với version trong BOM. Để BOM thật sự là nguồn version cho Jackson, các alias modules thường nên **không chỉ rõ version**, còn alias BOM pin version.
- Version catalog không mặc định giải quyết xung đột bắc cầu trên mọi dependency chỉ nhờ có bảng TOML; đó là việc của constraints/platforms tham gia graph.

Cũng không nhầm plugin alias `libs.plugins.*` (plugin ID/version) với library alias trong `dependencies` hoặc Gradle model accessor.

### Nếu nhiều module cùng cần BOM

Trong multi-project build, **mỗi project/configuration tiêu thụ** cần nhận version constraints bằng một cách phù hợp. Bạn có thể dùng alias thống nhất, convention plugin, hoặc một **`java-platform` project** được chia sẻ. Không đặt `platform(...)` ở root `build.gradle.kts` rồi tự suy ra subprojects đều đã có constraint; root project là một project riêng.

## 10. Tạo Gradle platform nội bộ bằng `java-platform`

BOM có thể do vendor publish dưới dạng Maven POM; Gradle cũng có `java-platform` plugin để công bố **platform component** của tổ chức.

Giả sử build có:

~~~text
company-build/
├── settings.gradle.kts
├── versions/build.gradle.kts
├── app/build.gradle.kts
└── ...
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "company-build"
include("versions", "app")
~~~

`versions/build.gradle.kts`:

~~~kotlin
plugins {
    `java-platform`
}

group = "org.example"
version = "1.0"

dependencies {
    constraints {
        api("com.fasterxml.jackson.core:jackson-databind:2.17.2")
        api("com.fasterxml.jackson.core:jackson-core:2.17.2")
        api("com.fasterxml.jackson.core:jackson-annotations:2.17.2")
    }
}
~~~

Kotlin syntax ``java-platform`` ở trong phần trên có nghĩa là plugin ID được đặt trong **cặp backticks**; không dùng string literal khác. `java-platform` tạo một project **chỉ quản lý version**, không yêu cầu chính project `versions` phải dùng Jackson class.

`app/build.gradle.kts`:

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(project(":versions")))
    implementation("com.fasterxml.jackson.core:jackson-databind")
}

application {
    mainClass.set("example.App")
}
~~~

Ở đây app nhận constraints từ project `:versions`, thay vì viết version cho module Jackson từng nơi. Để thực sự chạy app, cần `example.App` (có thể dùng file Java ở mục 4) và JDK/Wrapper thích hợp.

### Import Maven BOM vào `java-platform` nội bộ

Một `java-platform` project có thể muốn **nhập một BOM đã publish** và đưa constraints đến nhiều apps. Gradle yêu cầu bật dependency declaration cho platform bằng `allowDependencies()`:

~~~kotlin
plugins {
    `java-platform`
}

repositories {
    mavenCentral()
}

javaPlatform {
    allowDependencies()
}

dependencies {
    api(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
}
~~~

Đây là **phương án thay thế** cho `versions/build.gradle.kts` ở trên, không kết hợp với block constraints y hệt nếu không cần. Từ đó app có thể dùng `implementation(platform(project(":versions")))`. `allowDependencies()` là yêu cầu vì `java-platform` không cho phép dependencies thông thường theo mặc định; đây là một platform-to-platform dependency, không phải thư viện Java cần compile.

Nếu publish platform project:

~~~kotlin
plugins {
    `java-platform`
    `maven-publish`
}

group = "org.example"
version = "1.0"

publishing {
    publications {
        create<MavenPublication>("companyPlatform") {
            from(components["javaPlatform"])
        }
    }
}
~~~

Đây là **mảnh publish** cần ghép với configuration `java-platform` hoàn chỉnh và repository hợp lệ. Platform có thể được Gradle publish với Gradle Module Metadata và một Maven BOM/POM mapping, cho phép các consumer sử dụng. Nhưng không tự suy từ một `publish` thành công rằng Maven/Gradle consumers đều nhận giống nhau: kiểm tra metadata và dependency constraints thực tế.

## 11. BOM khác với plugin quản lý dependency của Spring

Trong ví dụ Gradle cơ bản, **không cần plugin bổ sung** để nhập Maven BOM:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.0"))
    implementation("org.springframework:spring-core")
}
~~~

`platform(...)` là **cơ chế native của Gradle**. Một số dự án Spring Boot sử dụng plugin `io.spring.dependency-management` để có semantics/quy trình quản lý version gần Maven hơn hoặc theo cấu hình của Spring plugin. Đó là **hệ cơ chế khác**; không mặc định kết hợp hai cách hoặc sao chép `dependencyManagement { imports { ... } }` từ tài liệu plugin vào build chỉ dùng native Gradle platform.

Nếu một dự án đã có plugin Spring Boot/dependency management, hãy xác định **nguồn version đang có hiệu lực** trước khi thêm một BOM mới. Dùng đồng thời version constraints từ nhiều cơ chế mà không có chủ đích có thể khiến graph khó giải thích.

**Không nhầm Spring Boot BOM và Spring Boot Gradle plugin version:** phiên bản plugin và phiên bản BOM thường liên quan, nhưng là hai tọa độ/đối tượng khác nhau. Ví dụ `org.springframework.boot:spring-boot-dependencies:3.3.0` là BOM có metadata quản lý dependency, không phải plugin ID.

## 12. Hai BOM cùng quản lý một module: chuyện gì xảy ra?

Nếu một project nhập hai BOM:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.0"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Đây là **tình huống chẩn đoán**, không phải khuyến nghị phối hợp hai BOM với version như trên. Cả hai có thể cung cấp constraints cho Jackson. Gradle resolve các yêu cầu đó **cùng nhau**, không có quy tắc “BOM viết cuối cùng luôn thắng”. Selected version phụ thuộc version constraints/ranges, strictness và rules trong graph. Nếu một BOM enforced, forced constraints có thể ghi đè lựa chọn từ BOM khác, nhưng cũng có thể gây xung đột nghiêm ngặt hoặc tương thích runtime kém.

**Cách xử lý tốt:**

1. Xác định BOM nào là **owner của hệ sinh thái** (ví dụ Spring Boot BOM quản lý Jackson mà Spring Boot đã kiểm thử).
2. Tránh nhập BOM thứ hai nếu chỉ tạo một bộ version chồng chéo mà không có yêu cầu thực tế.
3. Nếu buộc phải override một module, hiểu kỹ binary compatibility, constraints, strictness và tests.
4. Dùng `dependencyInsight --dependency jackson-databind` để thấy các đường và lý do chọn version.
5. Khi cần nâng toàn hệ Jackson, ưu tiên nâng BOM/stack theo tổ hợp được kiểm thử, không chỉ ép đơn lẻ một artifact mà không kiểm tra phần còn lại.

### BOM không tự giải quyết “dependency hell”

Một BOM không thể bảo đảm:

- Một module JAR có version chỉ tồn tại trong `libs/` tự biến thành module có group/version.
- Một dependency của app không được khai báo bỗng xuất hiện.
- Mọi modules ngoài BOM tương thích với version trong BOM.
- Một version bị force vẫn binary-compatible với code đã compile bằng version cao hơn.
- Build có thể lặp lại nếu dùng dynamic versions, repositories thiếu kiểm soát hoặc toolchains biến động.

BOM là một lớp quản lý version trong dependency resolution, **không thay thế quản trị dependency tổng thể**.

## 13. BOM và các dạng version constraints khác

Có thể dùng rich version constraint riêng cho một module:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))

    constraints {
        implementation("com.fasterxml.jackson.core:jackson-databind") {
            version {
                strictly("2.17.2")
            }
            because("Đã xác thực tương thích ABI cho module này")
        }
    }

    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

`strictly` đặt ràng buộc nghiêm ngặt đối với **module cụ thể**, khác với `enforcedPlatform` có thể force **một tập version** từ BOM. Nếu có strict constraints không tương thích, Gradle có thể fail resolution; không áp dụng `strictly` đại trà.

Phân biệt:

| Công cụ | Tác động |
| --- | --- |
| `platform(BOM)` | Nhập các version constraints từ BOM/Gradle platform. |
| `enforcedPlatform(BOM)` | Nhập và **force** phiên bản do platform quản lý. |
| `constraints { implementation("g:n:v") }` | Đặt version requirement cho module có mặt trong graph. |
| `strictly("v")` | Tăng độ nghiêm ngặt của requirement cho module/range. |
| `resolutionStrategy.force("g:n:v")` | Rule cưỡng ép version ở resolution strategy của configuration, cần thận trọng về scope. |
| Dependency locking | Lưu/kiểm tra **resolved versions** của graph để tái lập. |
| Version catalog | Quản lý notation/aliases khi khai báo dependencies, không tự áp graph constraints. |

Không thể thay thế mọi thứ bằng `enforcedPlatform`. Cũng không suy ra “constraint 2.17.2” là version cố định như `strictly("2.17.2")`. Nếu cần version ổn định và update kiểm soát, phối hợp BOM thường, lockfile, dependency verification và tests thích hợp.

## 14. Debug: vì sao module không lấy version từ BOM?

Hãy kiểm tra theo thứ tự:

1. **Plugin có tạo configuration chưa?** Nếu chưa có `java`/`application`/`java-library` hoặc plugin tương ứng, `implementation` có thể không tồn tại.
2. **BOM có resolve được không?** Repository `mavenCentral()` hoặc repository chứa BOM được khai báo đúng chưa? Proxy/network có bị chặn không?
3. **Đây là BOM thật?** Tọa độ có POM quản lý versions/Gradle platform metadata không, hay chỉ là một module JAR thông thường?
4. **Module muốn align có xuất hiện trong graph không?** BOM chỉ quản lý version, không đưa module vào.
5. **BOM ở đúng configuration chưa?** `testImplementation(platform(...))` không tự quản lý compile classpath sản phẩm.
6. **Module có nằm trong danh sách BOM quản lý không?** Nếu không có constraint cho `group:name` ấy, Gradle không thể lấy version chỉ vì cùng namespace.
7. **Version được yêu cầu ở nơi khác là gì?** Direct dependency và transitive requests có thể khiến selected version cao hơn platform thường.
8. **Có constraint mạnh/force/enforced platform khác không?** Xem `strictly`, platform khác, resolution rules hoặc plugin quản lý dependency.
9. **Variant nào được chọn?** `java-api`/`java-runtime`, target JVM và metadata có thể ảnh hưởng graph.
10. **Có dùng versionless dependency đúng cú pháp?** `implementation("g:n")` hợp lệ nếu graph cung cấp version constraint thích hợp, nhưng nếu thiếu sẽ báo không resolve được module version.

Các lệnh thiết yếu:

~~~bash
# App root đơn module
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath

# Một module và lý do version cuối được chọn
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath

# Tìm BOM/platform trong graph
./gradlew dependencyInsight --dependency jackson-bom --configuration runtimeClasspath

# Multi-project: project :app
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath

# Nếu cần thêm thông tin variant (theo phiên bản Gradle)
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath --all-variants
~~~

Trong output có thể gặp:

- `2.16.1 -> 2.17.2`: requested → selected.
- `(c)`: constraint, không phải artifact.
- `(*)`: subtree đã mở rộng ở chỗ khác.
- “By constraint”: version được tác động bởi một constraint.
- “By conflict resolution”: Gradle chọn khi có nhiều version requests.
- “Forced”: rule hoặc enforced platform cưỡng ép một version.

Các chuỗi selection reasons cụ thể và vị trí hiển thị thay đổi theo Gradle version; hãy đọc **report thật** thay vì gán một template kết quả cố định.

### Lỗi `Could not find g:n:.` khi module không ghi version

Lỗi có thể xuất hiện nếu `implementation("g:n")` không có version constraint nào phù hợp trong configuration được resolve. Kiểm tra BOM có đúng module, có nằm trên đúng graph, và repository có metadata hợp lệ. **Thêm version tay** có thể giúp chẩn đoán, nhưng nếu mục tiêu dùng BOM, hãy sửa nguồn constraint trước để tránh vận hành hai nguồn version song song.

## 15. Tình huống quyết định: nên chọn `platform` hay `enforcedPlatform`?

| Tình huống | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| Ứng dụng Java dùng Jackson/JUnit BOM để đồng bộ thư viện | `platform` | Dùng constraints do nhà phát hành cung cấp, vẫn tham gia resolution bình thường. |
| Bộ test riêng cần versions JUnit đồng nhất | `testImplementation(platform(...))` | Đúng scope test, không áp chính sách vào production. |
| Thư viện `java-library` sẽ publish cho nhiều clients | `api/implementation(platform(...))` theo API contract | Tránh force version ngoài ý muốn cho consumer. |
| Ứng dụng cuối bắt buộc dùng một stack đã kiểm thử, không publish | Cân nhắc `enforcedPlatform`, test kỹ | Force có thể phù hợp nếu tương thích được chứng minh. |
| Hai BOM chồng chéo và xung đột | Rà soát ownership, version requirements, dependencyInsight | Không mặc định thêm enforced chỉ để im lỗi. |
| Muốn giữ đúng versions qua nhiều build | `platform` + dependency locking | BOM đưa constraints; lockfile ghi resolved versions. |
| Muốn một doanh nghiệp phát hành chung quy tắc versions | `java-platform` và publication chuẩn | Tập trung constraints, chia sẻ rõ model. |
| Một module chỉ tồn tại dưới JAR local | Cần publish module metadata hoặc khai báo file đúng | BOM không biết identity của file path. |
| Có lỗi versionless dependency trong processor path | Import platform trên đúng processor configuration | Configuration riêng cần constraint riêng. |

**Gợi ý triển khai:** bắt đầu bằng `platform`, xác minh graph và tests, chỉ chọn `enforcedPlatform` khi thực sự có chính sách cưỡng ép version được ghi lại và được kiểm thử.

## 16. Các lỗi hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| Đã import BOM nhưng không thấy một JAR | BOM không tự thêm module. | Thêm `implementation("group:name")`/scope thích hợp. |
| Module versionless báo không resolve | BOM không quản lý module hoặc đặt sai scope/repository. | Kiểm tra tọa độ BOM, configuration và metadata. |
| Version cuối cao hơn số trong BOM | `platform` bình thường không cưỡng ép, conflict resolution chọn version khác. | Dùng `dependencyInsight`; kiểm tra consistency, không ép thấp tùy tiện. |
| `enforcedPlatform` làm một module bị downgrade | Forced versions ghi đè yêu cầu khác. | Rà soát compatibility, cân nhắc platform thường và nâng BOM. |
| Library của bạn làm app consumer bị ép Jackson | Enforced platform được công bố transitively qua library dependency model. | Tránh publish forced platform, thay bằng platform thường. |
| App chạy lỗi `NoSuchMethodError` | Các modules bị trộn versions/force xuống API thiếu method. | Kiểm tra runtime graph tất cả Jackson modules, nâng stack có test. |
| Spring Boot/BOM phiên bản chồng chéo | Có nhiều nguồn version management. | Chọn owner BOM, hiểu plugin/native platform rules. |
| Import BOM ở `testImplementation` nhưng main compile vẫn thiếu version | BOM chỉ tham gia test scope. | Đặt platform ở `implementation` cho main nếu cần. |
| Annotation processor không nhận BOM | `annotationProcessor` có graph khác. | Import platform vào processor configuration. |
| `api(platform(...))` báo lỗi | `api` chưa có vì chưa áp dụng `java-library` plugin. | Áp dụng plugin đúng hoặc chọn `implementation`. |
| Alias TOML có version Jackson khác BOM | Catalog alias tạo version request cạnh tranh. | Dùng versionless module aliases khi BOM là nguồn quản lý. |
| POM publish không giống Gradle consumer | Maven POM không bảo toàn toàn bộ Gradle constraints/variants/forced semantics. | Kiểm tra `.module`, POM và test consumer Maven/Gradle. |
| BOM module không tải được | Repository thiếu POM, sai tọa độ, proxy/network. | Kiểm tra `repositories`, credentials, `--info` và artifact URL thực. |
| Cache/build phụ thuộc môi trường | Dynamic versions, repository thay đổi, Java toolchain khác. | Chốt versions, wrapper, lockfile/verification và CI. |

## 17. Checklist review và thực hành an toàn

- [ ] BOM có tọa độ module chính xác, version cố định và repository đáng tin.
- [ ] BOM được import bằng `platform(...)` trên configuration thực sự cần quản lý versions.
- [ ] Module sẽ dùng có dependency declaration riêng; BOM không tự thêm nó.
- [ ] Mọi versionless module được BOM/constraint quản lý thật, không suy đoán từ group name.
- [ ] Đã xem `dependencyInsight` để phân biệt requested và selected versions.
- [ ] Không mặc định `platform` pin cứng version; hiểu rich/strict constraints khi có.
- [ ] `enforcedPlatform` chỉ dùng khi có lý do cưỡng ép rõ và kiểm thử binary/runtime compatibility.
- [ ] Không vô tình publish/enforce forced versions lên consumer libraries.
- [ ] Test/runtime/processor platform declarations nằm đúng configuration.
- [ ] Version catalog aliases không tự xung đột BOM bằng versions thừa.
- [ ] Với nhiều BOM, xác định một owner version management cho từng module family.
- [ ] Có tests khi nâng BOM hoặc thay đổi constraints; xem cả artifact runtime, không chỉ compile.
- [ ] Dùng Gradle Wrapper và dependency locking/verification khi cần reproducibility.
- [ ] Với library publication, kiểm tra Gradle Module Metadata, Maven POM và consumer độc lập.
- [ ] Không coi `BUILD SUCCESSFUL` của một task là bằng chứng toàn bộ runtime dependency stack tương thích.

## 18. Câu hỏi tự kiểm tra

1. **BOM là gì?** Tập quản lý version, thường công bố qua Maven POM `dependencyManagement`.
2. **`implementation(platform("g:bom:v"))` có tự đưa mọi JAR trong BOM lên classpath không?** Không. Chỉ module được yêu cầu thực sự xuất hiện.
3. **Tại sao `implementation("jackson-databind")` không ghi version vẫn có thể chạy?** Vì platform trên đúng graph cung cấp constraint version cho module.
4. **`platform` có luôn pin chính xác version BOM?** Không. Version selection vẫn kết hợp requirements/rules; selected version có thể khác.
5. **`enforcedPlatform` làm gì thêm?** Force các versions do platform quản lý, có thể ghi đè direct/transitive requests.
6. **Nên dùng enforced platform trong library publish không?** Thường tránh vì forced constraints có thể lan tới consumers; chỉ dùng với lý do/test rõ.
7. **Nếu chỉ import BOM mà không khai báo Jackson module, có thể `import com.fasterxml...ObjectMapper` không?** Không. BOM không tự cấp JAR thư viện.
8. **`testImplementation(platform(...))` có mặc định kiểm soát `runtimeClasspath` của main app không?** Không.
9. **Version catalog có thay cho BOM không?** Không. Catalog quản lý notation/alias; BOM cấp version constraints trong graph.
10. **Làm sao biết Gradle chọn version nào và vì sao?** Dùng `dependencies` + `dependencyInsight` trên đúng configuration.
11. **Hai BOM cùng quản lý Jackson có quy tắc “dòng cuối thắng” không?** Không. Gradle dùng constraints/conflict resolution, xem graph thực.
12. **Một local JAR `libs/jackson-core.jar` có tự chịu BOM constraints không?** Không như module GAV; nó là file dependency.
13. **`java-platform` project dùng để làm gì?** Tập trung/publish version constraints cho nhiều modules/projects.
14. **Muốn import Maven BOM vào `java-platform` project cần gì?** `javaPlatform { allowDependencies() }` rồi `api(platform("g:bom:v"))`.
15. **BOM có thay dependency locking không?** Không. BOM đưa constraints, locking ghi resolved versions để tăng khả năng tái lập.
16. **Nếu `enforcedPlatform` buộc version thấp hơn API mà library khác cần, điều gì có thể xảy ra?** Build có thể fail resolution hoặc runtime lỗi ABI; phải kiểm tra dependency graph và compatibility.
17. **Tại sao JUnit BOM thường đặt trong test configuration?** Nó quản lý những modules chủ yếu dùng ở test, không cần ép vào production graph.

## 19. Tài liệu chính thức

- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): `platform`, `enforcedPlatform`, Maven BOM và native Gradle platform.
- [Gradle — Declaring Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): platform constraints, rich versions, publication.
- [Gradle — Declaring and Managing Versions](https://docs.gradle.org/current/userguide/dependency_versions.html): requested vs selected, version ranges, rich version constraints.
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): graph resolution, conflict selection, artifacts.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`, selection reasons.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): `libs.versions.toml`, aliases và điểm khác version constraints.
- [Gradle — Java Platform Plugin](https://docs.gradle.org/current/userguide/java_platform_plugin.html): `java-platform`, `allowDependencies`, publishing.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): lock resolved versions, reproducible dependency graph.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): publication metadata, variants và constraints.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): component publication và Maven POM.
