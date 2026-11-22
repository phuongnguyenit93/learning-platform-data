# BOM, căn chỉnh phiên bản và phát hiện tổ hợp thư viện không tương thích trong Gradle

## 1. Mục tiêu của bài học

Trong dự án Java, một ứng dụng có thể sử dụng hàng trăm **dependency trực tiếp và bắc cầu (transitive dependencies)**. Chẳng hạn bạn khai báo `jackson-databind`, một framework web lại mang theo `jackson-core`, còn thư viện khác yêu cầu `jackson-annotations` từ phiên bản khác. Dự án vẫn có thể compile, nhưng khi chạy gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi xử lý dữ liệu bất thường.

**BOM (Bill of Materials)** và **dependency version alignment** giúp quản lý một tập module có quan hệ phiên bản, còn các công cụ **dependency graph / dependencyInsight / constraints / capabilities / tests** giúp phát hiện và xử lý tổ hợp dependency không phù hợp.

Sau bài học, bạn cần:

1. Phân biệt **dependency declaration**, **resolved version**, **transitive dependency**, **platform**, **Maven BOM**, **version catalog**, **dependency constraint**.
2. Import một BOM bằng `platform(...)` của Gradle Kotlin DSL/Groovy DSL và dùng dependency không ghi version riêng.
3. Hiểu ranh giới giữa `platform(...)` (constraints) và `enforcedPlatform(...)` (strong enforcement), đặc biệt khi xuất bản library.
4. Tạo một **Java Platform project** dùng plugin `java-platform` và chia sẻ constraints cho nhiều module.
5. Căn chỉnh các module cùng release train với published BOM hoặc **virtual platform** khi không có BOM.
6. Đọc các ký hiệu `->`, `(c)`, `(*)` trong output `dependencies` và dùng `dependencyInsight` để truy ngược vì sao Gradle chọn version.
7. Dùng `strictly`, `prefer`, `reject`, `because` và cảnh báo `failOnVersionConflict()` đúng mục đích.
8. Phân biệt **version conflict**, **capability conflict**, **metadata incompatibility**, **binary/runtime incompatibility**.
9. Kết hợp dependency locking, verification, CI và regression tests để tránh lỗi chỉ xuất hiện sau khi triển khai.
10. Không dùng `force`, exclusions hoặc `enforcedPlatform` tùy tiện để che sai lệch giữa các thư viện.

Bài thuộc nhóm **Phân giải dependency** của Build Tool Gradle. Ví dụ ưu tiên **Gradle Kotlin DSL** (`build.gradle.kts`) trên Gradle 8.x/9.x và Java 17; phiên bản thư viện minh họa là các bản đã biết, không phải khuyến nghị dùng bản mới nhất cho mọi dự án.

## 2. Hiểu cách Gradle phân giải dependency

Đầu tiên cần phân biệt **requested version** với **selected version**.

Giả sử graph có:

~~~text
application
  |
  +-- library-A:1.0 ----> common-lib:1.4
  |
  +-- library-B:2.0 ----> common-lib:1.8
  |
  +-- common-lib:1.5 (khai báo trực tiếp)
~~~

Gradle xử lý conflict của **cùng module** (`group:name` giống nhau) trên một resolvable configuration. Với yêu cầu phiên bản thông thường, nó thường chọn **phiên bản cao nhất phù hợp** trong graph; ở ví dụ đó có thể là `1.8`.

Chọn `common-lib:1.8` **không bảo đảm** `library-A:1.0` được viết để tương thích với 1.8. Nó chỉ là quyết định dependency resolution dựa trên metadata và rules, không phải chạy test kiểm tra binary compatibility.

Một vài khái niệm:

- **Direct dependency:** khai báo trong `dependencies { ... }` của project.
- **Transitive dependency:** dependency do các module khác kéo vào.
- **Resolvable configuration:** tập dependency thực sự được Gradle resolve, ví dụ `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`.
- **Selected component/variant:** module version và variant cuối cùng được Gradle chọn theo metadata, attributes, capabilities và resolution rules.
- **Conflict resolution:** chọn kết quả khi graph có nhiều yêu cầu khác nhau cho một module hoặc nhiều component cung cấp cùng capability.
- **Version alignment:** đưa các module liên quan vào một tập version tương thích, đôi khi yêu cầu **cùng version**, đôi khi chỉ cần một bộ version được BOM xác nhận.

### 2.1. Compile classpath và runtime classpath có thể khác

`compileClasspath` phục vụ biên dịch mã chính; `runtimeClasspath` có cả dependency cần khi chạy. Test dùng những configuration riêng như `testCompileClasspath`, `testRuntimeClasspath`.

Một graph biên dịch đúng không có nghĩa graph chạy đúng. Ví dụ code compile với API mới nhưng runtime được cấu hình để dùng implementation cũ có thể làm phát sinh `NoSuchMethodError`.

Vì thế khi điều tra lỗi runtime, **kiểm tra `runtimeClasspath` trước**, không chỉ dừng ở `compileClasspath`.

### 2.2. Một module có một version trong một graph, nhưng không nhất thiết đồng bộ các module khác

Nếu `com.example:core:2.0` và `com.example:util:1.7` có **tên module khác nhau**, Gradle không tự suy luận chúng bắt buộc cùng version chỉ vì cùng group. Cơ chế version conflict thông thường chỉ xử lý **các yêu cầu đến cùng module**.

Để căn chỉnh *nhiều module khác nhau*, cần metadata/platform/BOM hoặc một quy tắc alignment được thiết kế đúng.

## 3. Maven BOM là gì?

**BOM (Bill of Materials)** trong hệ sinh thái Maven thường là một POM có `packaging=pom` và khối `dependencyManagement` khai báo những module/version được quản lý cùng nhau.

BOM **không phải file JAR** và không nhất thiết thêm tất cả module trong BOM vào classpath của ứng dụng.

Ví dụ POM minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.example</groupId>
  <artifactId>example-bom</artifactId>
  <version>1.2.0</version>
  <packaging>pom</packaging>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.example</groupId>
        <artifactId>example-core</artifactId>
        <version>1.2.0</version>
      </dependency>
      <dependency>
        <groupId>org.example</groupId>
        <artifactId>example-util</artifactId>
        <version>1.2.0</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
~~~

BOM trên đưa ra phiên bản quản lý cho hai module. Một project chỉ phụ thuộc `example-core` sẽ **không tự có `example-util`** chỉ vì BOM nhắc đến nó.

Gradle có thể import Maven BOM thành **platform dependency**. Khi đó những entry trong `dependencyManagement` được diễn giải thành **dependency constraints** tham gia quá trình chọn version.

### 3.1. Không nhầm BOM với version catalog

| Khía cạnh | BOM / `platform(...)` | Version catalog / `libs.versions.toml` |
| --- | --- | --- |
| Nguồn | Module platform/BOM (hoặc Java Platform project) | Alias + version định nghĩa trong TOML/Settings |
| Vai trò chính | Tham gia **resolution** bằng constraints trên dependency graph | Tập trung khai báo dependency coordinates, version và type-safe accessor |
| Ảnh hưởng transitive graph | Có, constraints áp dụng khi platform được đưa vào configuration | Không tự áp version catalog vào transitive graph |
| Có tự thêm mọi module? | Không, BOM chỉ đặt constraints trừ khi có dependency thực | Không, alias chỉ được dùng khi bạn khai báo dependency |
| Có thể chia sẻ qua Maven metadata? | Có, platform được publish đúng cách | TOML local không tự trở thành BOM cho consumer |

Version catalog và BOM **có thể dùng cùng nhau**: catalog khai báo alias cho BOM, còn `platform(libs.some.bom)` mới làm BOM tham gia resolution.

### 3.2. BOM không đồng nghĩa mọi module có cùng số version

Một BOM có thể quản lý `junit-jupiter` phiên bản **5.x** và `junit-platform` phiên bản **1.x**. Đây là **bộ version được thiết kế tương thích**, không phải cùng chuỗi version.

Tương tự, một số bộ thư viện có module nằm ở các dòng phiên bản riêng. Không dùng thuật toán “ép toàn bộ artifact trong một group về cùng version” nếu nhà sản xuất BOM **không định nghĩa** quan hệ như vậy.

## 4. `platform(...)`: cách nhập BOM trong Gradle Kotlin DSL

Giả sử project Java cần JUnit 5 cho unit test.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "bom-junit-demo"
~~~

**build.gradle.kts**

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    // Chỉ đưa BOM vào graph của các cấu hình test phù hợp.
    testImplementation(platform("org.junit:junit-bom:5.10.2"))

    // Không ghi version ở các module được BOM quản lý.
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Điểm cần hiểu:

1. `platform("org.junit:junit-bom:5.10.2")` yêu cầu Gradle tiêu thụ BOM dưới dạng platform.
2. BOM cung cấp constraints về các phiên bản JUnit liên quan; `junit-jupiter` và `junit-platform-launcher` có thể khai báo **không kèm version**.
3. `testImplementation` được đưa vào các classpath test thích hợp; `testRuntimeOnly` phục vụ runtime test.
4. `useJUnitPlatform()` yêu cầu Gradle Test chạy JUnit Platform.
5. Phải có `repositories { mavenCentral() }` hoặc repository mirror được phép để tải BOM và dependency thực.

**Không cần plugin quản lý BOM riêng** chỉ để dùng `platform(...)`: đây là native Gradle functionality.

### 4.1. Vì sao platform đặt trong testImplementation?

Nếu bạn dùng JUnit chỉ để test, BOM và các module của nó nên nằm trong scope test thay vì kéo vào classpath production. Nếu muốn quản lý library production, đưa platform vào `implementation` hoặc `api` tùy tính chất của thư viện.

Ví dụ với Jackson (đoạn bổ sung khi project có nhu cầu JSON):

~~~kotlin
dependencies {
    implementation(
        platform("com.fasterxml.jackson:jackson-bom:2.17.2")
    )

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.core:jackson-core")
    implementation("com.fasterxml.jackson.core:jackson-annotations")
}
~~~

Đây là **mẫu khai báo dependency**, không phải file build.gradle.kts độc lập; cần Java plugin và repository. Nếu một dependency khác đưa vào một version Jackson cao hơn, BOM regular có thể không bắt các module ở version cũ như bạn tưởng — xem phần `platform` vs `enforcedPlatform` và phần version alignment.

### 4.2. Kiểm tra BOM thực sự tham gia resolution

Trên macOS/Linux:

~~~bash
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath --console=plain
~~~

Bạn sẽ thấy graph gồm `org.junit:junit-bom:5.10.2`, các module JUnit, và các dấu `(c)` cho **constraints** ở vị trí thích hợp. Cấu trúc/indent/output chính xác thay đổi giữa các bản Gradle, vì vậy đừng so sánh nguyên văn với một ảnh chụp từ tài liệu phiên bản khác.

`platform()` không có tác dụng nếu bạn chỉ gõ tọa độ BOM vào `implementation("org.junit:junit-bom:5.10.2")` như một JAR thường; Gradle cần biết bạn muốn **platform variant**, không phải artifact runtime thông thường.

## 5. Ví dụ Java 17 hoàn chỉnh: dùng JUnit BOM và chạy test

Để xác minh phần thực hành ở mục 4, tạo thêm hai file Java vào project `bom-junit-demo`.

Cấu trúc:

~~~text
bom-junit-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/java/demo/Calculator.java
│   └── test/java/demo/CalculatorTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

**src/main/java/demo/Calculator.java**

~~~java
package demo;

public final class Calculator {
    private Calculator() {}

    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

**src/test/java/demo/CalculatorTest.java**

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }
}
~~~

Chạy:

~~~bash
./gradlew clean test --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test --console=plain
~~~

**Kết quả mong đợi:** Gradle resolve BOM và các module JUnit, compile code Java, phát hiện 1 test `addsTwoNumbers()` và test thành công. `CalculatorTest` **không tự in ra console**, nên không khẳng định một chuỗi stdout riêng; Gradle in danh sách task/`BUILD SUCCESSFUL` theo phiên bản, còn báo cáo HTML thường ở:

~~~text
build/reports/tests/test/index.html
~~~

Lệnh trực tiếp kiểm tra version được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency org.junit.jupiter:junit-jupiter-api \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Từ kết quả có thể biết **module/version được chọn** và đường đi dẫn đến module. Việc JUnit test pass là minh chứng có test thực thi trên graph hiện tại, nhưng **không chứng minh mọi thư viện sản xuất của cả ứng dụng đều tương thích**.

### 5.1. Không cần `junit-jupiter` và `junit-jupiter-api` cùng lúc

`org.junit.jupiter:junit-jupiter` là aggregator dependency thông dụng mang API và engine liên quan. Nếu bạn dùng cách khai báo tách `junit-jupiter-api` và `junit-jupiter-engine`, cần chắc chắn engine nằm trên test runtime classpath. Đừng vô tình khai báo cả aggregator và các module con nhiều lần chỉ để “chữa” lỗi version; giải thích graph trước khi thêm dependencies.

### 5.2. Kiểm tra JUnit Platform Launcher

Trong Gradle 8/9 hiện đại, khai báo rõ `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` giúp tránh phụ thuộc vào việc Gradle tự suy luận phiên bản launcher. BOM quản lý phiên bản launcher phù hợp dòng JUnit. Nếu IDE, Gradle Test runner hoặc plugin riêng có yêu cầu launcher khác, phân tích `testRuntimeClasspath` thay vì đổi version ngẫu nhiên.

## 6. `platform` và `enforcedPlatform` khác nhau như thế nào?

Đây là khác biệt có hậu quả lớn.

| Cách import | Ý nghĩa | Hệ quả điển hình |
| --- | --- | --- |
| `platform("g:bom:v")` | Các version của BOM trở thành **constraints/recommendations**; vẫn chịu dependency resolution | Dependency khác có thể yêu cầu version cao hơn và được chọn |
| `enforcedPlatform("g:bom:v")` | Ràng buộc version theo BOM mạnh hơn, về bản chất biến constraints thành strict/enforced | Version ngoài BOM bị chặn hoặc có thể gây resolution failure |
| `constraints { ... }` | Ràng buộc theo từng module | Có thể chỉ định đúng module cần điều chỉnh |
| `strictly("...")` cho module | Giới hạn version chấp nhận của một module | Đụng constraint không tương thích có thể làm resolution fail |

Ví dụ Regular Platform:

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))
    implementation("com.fasterxml.jackson.core:jackson-databind")

    // Một dependency khác có thể yêu cầu Jackson mới hơn.
    // Version thực tế phải xem dependencyInsight.
}
~~~

`platform` **không phải lệnh đóng đinh vĩnh viễn mọi module** ở version hiển thị trong BOM. Nếu graph có một yêu cầu phiên bản cao hơn hợp lệ, Gradle có thể nâng version.

Một ví dụ ràng buộc mạnh hơn:

~~~kotlin
dependencies {
    implementation(
        enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.17.2")
    )
    implementation("com.fasterxml.jackson.core:jackson-databind")
}
~~~

Đoạn này là **mẫu phân biệt cơ chế**, không phải khuyến nghị mặc định. Nó có thể gây conflict với thư viện đòi API mới hơn, hoặc khiến ứng dụng buộc dùng một tổ hợp không thích hợp.

### 6.1. Vì sao tránh enforcedPlatform trong library publish cho bên khác?

Khi bạn publish một library phụ thuộc **enforced platform**, ràng buộc mạnh có thể **truyền sang consumer**, ép phiên bản của những dependency mà consumer cũng sử dụng. Điều này làm các dự án sử dụng thư viện của bạn khó nâng cấp hoặc gặp resolution failure.

Thông thường:

- Với **ứng dụng** cần kiểm soát một stack đã được test, `enforcedPlatform` có thể được cân nhắc sau khi đánh giá ảnh hưởng.
- Với **library dùng chung**, ưu tiên `platform`, constraints có lý do rõ ràng, hoặc `strictly` theo **range tương thích** ở những module thực sự cần giới hạn.
- Khi có BOM mới, ưu tiên **nâng BOM và test lại stack** thay vì duy trì nhiều `strictly` trái nhau.

### 6.2. `enforcedPlatform` không phải bài thuốc cho lỗi runtime

Nếu thư viện A chỉ tương thích với API B >= 2.0 nhưng BOM ép B = 1.5, build có thể resolution được nhưng runtime lỗi. **Một version cưỡng chế không chứng minh API compatibility**.

Để giải quyết nguyên nhân, xem yêu cầu của từng component, upgrade các thư viện liên quan, kiểm tra release notes và chạy integration tests trên resolved graph thực tế.

## 7. Version alignment: nhiều module cần nhất quán

Cơ chế **version conflict** chỉ xử lý các request vào *cùng module*. **Version alignment** xử lý một tập *nhiều module* cùng cần tương thích.

Ví dụ nhóm Jackson:

~~~text
jackson-databind
jackson-core
jackson-annotations
~~~

Một thư viện web có thể kéo `jackson-core` cao hơn, trong khi một dependency cũ mang `jackson-annotations` thấp hơn. Gradle không luôn tự biết bộ version nào tương thích nếu metadata thiếu quan hệ giữa các module.

Các lựa chọn theo thứ tự:

1. **BOM chính thức của nhà phát hành** nếu có.
2. **Gradle platform** của tổ chức khi quản lý bộ module tùy chỉnh.
3. **Virtual platform** qua component metadata rule nếu module cùng release train nhưng publisher không có BOM/metadata phù hợp.
4. Constraints/rich versions cho một vài module riêng lẻ.
5. Resolution rules mạnh/force chỉ khi thực sự cần, có lý do và test minh chứng.

### 7.1. Import Jackson BOM

~~~kotlin
dependencies {
    implementation(
        platform("com.fasterxml.jackson:jackson-bom:2.17.2")
    )
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.core:jackson-annotations")
    implementation("com.fasterxml.jackson.core:jackson-core")
}
~~~

Khi ba module cùng có version được BOM quản lý, Gradle có thông tin constraints để chọn bộ version. Nhưng **BOM regular vẫn tham gia resolution với các yêu cầu bắc cầu khác**; đừng kết luận graph cuối cùng giống 100% phiên bản trong POM chỉ dựa vào khai báo.

### 7.2. Khi các module không cùng số version

Không phải mọi BOM đều đặt version giống nhau cho mọi artifact. JUnit 5 là ví dụ: JUnit Jupiter/Platform có hệ thống version riêng được BOM phối hợp. Alignment nên theo **bộ tương thích do nhà sản xuất xác nhận**, không ép tất cả thành một số version máy móc.

### 7.3. Khi nào cần một virtual platform?

Nếu một tập module cùng release train **không có BOM chính thức** hoặc không công bố thông tin alignment đầy đủ, Gradle cho phép thêm **component metadata rule** để gán những module đó vào **cùng virtual platform**.

Một ví dụ từ cơ chế Gradle, chỉ dùng khi bạn xác nhận các module thực sự versioned together:

~~~kotlin
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

abstract class JacksonAlignmentRule : ComponentMetadataRule {
    override fun execute(context: ComponentMetadataContext) {
        context.details.run {
            if (id.group.startsWith("com.fasterxml.jackson")) {
                belongsTo(
                    "com.fasterxml.jackson:jackson-virtual-platform:${id.version}"
                )
            }
        }
    }
}

dependencies {
    components.all<JacksonAlignmentRule>()

    implementation("com.fasterxml.jackson.core:jackson-databind:2.8.9")
    implementation("io.vertx:vertx-core:3.5.3")
}
~~~

Đây là **ví dụ nâng cao minh họa một build.gradle.kts có Java plugin và repository**; thêm class và block vào script phù hợp. Virtual platform có coordinate ảo nhằm đưa các module Jackson liên quan vào một tập alignment. Gradle có thể chọn cùng release version khi có xung đột bắc cầu.

**Cảnh báo:** rule `startsWith("com.fasterxml.jackson")` là ví dụ mô tả kỹ thuật trong tài liệu Gradle, có thể quá rộng đối với bộ thư viện hoặc version hiện tại. Không copy nguyên điều kiện vào production khi chưa xác minh modules nào thực sự versioned together. Nếu nhà phát hành có BOM, **ưu tiên BOM** vì nó phản ánh chính sách tương thích cụ thể hơn.

Một virtual platform **không tự thêm JAR**, và không biết API nhị phân có tương thích hay không; nó chỉ thêm quan hệ phiên bản để dependency resolver sử dụng.

## 8. Tạo Java Platform nội bộ cho một multi-project build

Khi nhiều module trong tổ chức cần thống nhất những version dependency, có thể tạo một subproject chuyên quản lý constraints bằng plugin `java-platform`.

Cấu trúc:

~~~text
multi-project-platform/
├── settings.gradle.kts
├── platform/
│   └── build.gradle.kts
├── app/
│   └── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

**settings.gradle.kts**

~~~kotlin
rootProject.name = "multi-project-platform"
include(":platform", ":app")
~~~

**platform/build.gradle.kts**

~~~kotlin
plugins {
    `java-platform`
}

dependencies {
    constraints {
        // Những version mà nhóm đã chọn và kiểm thử.
        api("org.apache.commons:commons-lang3:3.14.0")
        api("com.google.guava:guava:33.3.1-jre")
        api("org.slf4j:slf4j-api:2.0.16")
    }
}
~~~

**app/build.gradle.kts**

~~~kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(project(":platform")))

    // Các version đến từ platform nội bộ.
    implementation("org.apache.commons:commons-lang3")
    implementation("com.google.guava:guava")
}
~~~

Chạy:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath --console=plain
~~~

Nếu repository truy cập được, Gradle đưa constraints từ `:platform` vào graph của `:app`. `platform` nội bộ **không tự tải** `slf4j-api` khi app không có dependency trực tiếp hoặc bắc cầu cần nó; constraint chỉ có tác dụng khi module đó được yêu cầu.

**Lưu ý:** ví dụ trên chọn các thư viện thuộc **những dự án khác nhau**, nên `java-platform` chỉ quản lý version của từng module. Nó **không** khẳng định ba dependency có chung một số version hoặc cùng release train. Khi tổ chức sở hữu một bộ module phải cùng release version, cần khai báo constraints/metadata có phản ánh quan hệ ấy.

### 8.1. Vì sao platform project không phải java-library?

`java-platform` dành để công bố constraints/BOM, không để compile source Java như một JAR thông thường. Nếu cố gắng áp dụng đồng thời `java-platform` và `java` trong cùng project, mô hình có thể không phù hợp/Gradle từ chối; nên tách project platform riêng như ví dụ.

### 8.2. `api` constraints và khả năng publish

Các `api(...)` constraints của Java Platform được dùng bởi consumer. Khi xuất bản platform qua `maven-publish` đúng cấu hình, nó có thể cung cấp Gradle Module Metadata và Maven BOM/POM cho những consumer thích hợp.

Đừng nhầm việc chỉ có subproject `:platform` với việc đã publish lên Maven repository. Publishing là một bước độc lập, cần plugin/configuration/credentials phù hợp.

## 9. Import BOM khác với tạo BOM riêng

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Thư viện có BOM do vendor công bố | `implementation(platform("group:bom:version"))` |
| Ứng dụng cần dùng chính xác BOM trong scope đã kiểm thử | Cân nhắc `enforcedPlatform(...)` sau khi xác minh tác động |
| Tổ chức cần công bố tập constraints giữa nhiều module | Plugin `java-platform`, dependencies constraints, publishing nếu cần |
| Chỉ muốn một alias version thống nhất trong source | Version catalog |
| Không có BOM, các module được versioned together | Component metadata rule + virtual platform, sau khi xác minh quan hệ |
| Một hoặc hai module cần giới hạn compatibility cụ thể | Dependency constraint với rich version |

Không nên tạo một platform nội bộ để lặp nguyên tất cả BOM vendor **mà không có lý do quản trị**. Nếu vendor đã công bố BOM, có thể dùng BOM trực tiếp; platform nội bộ chỉ cần bổ sung các lựa chọn/constraints đặc thù của tổ chức.

### 9.1. Version catalog dùng cùng BOM

Ví dụ **gradle/libs.versions.toml**:

~~~toml
[versions]
junit = "5.10.2"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter" }
~~~

Trong build.gradle.kts có Java plugin:

~~~kotlin
dependencies {
    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
}
~~~

Ở đây `libs.junit.bom` chỉ cung cấp **tọa độ BOM** từ catalog. Chính lời gọi `platform(...)` khiến BOM trở thành dependency platform có tác dụng ở resolution. `libs.junit.jupiter` không có version riêng nên phụ thuộc vào BOM/constraints trong graph để chọn version.

## 10. Dependency constraints và rich version declarations

Đôi khi BOM không quản lý một module cụ thể hoặc bạn cần thể hiện phiên bản tối thiểu/tập phiên bản an toàn.

### 10.1. Một constraint thông thường

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3")

    constraints {
        implementation("org.apache.commons:commons-lang3:3.14.0") {
            because("Cùng version được kiểm thử trong ứng dụng")
        }
    }
}
~~~

Constraint giúp Gradle chọn version khi module xuất hiện trong graph. Nhưng nó **không phải hard pin trong mọi trường hợp**: yêu cầu version cao hơn phù hợp từ nơi khác có thể được chọn.

`because(...)` giúp người duy trì hiểu **lý do** của constraint, và có thể xuất hiện trong báo cáo dependency insight.

### 10.2. `strictly`, `prefer`, `reject`

Một rich version requirement:

~~~kotlin
dependencies {
    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                strictly("[3.14, 4.0[")
                prefer("3.14.0")
                reject("3.15.0")
            }
            because(
                "Chỉ chấp nhận nhánh API 3.x đã đánh giá; " +
                "phiên bản 3.15.0 bị từ chối theo chính sách ví dụ"
            )
        }
    }
}
~~~

Đây là **mẫu cú pháp minh họa**; việc reject một version chỉ nên làm sau khi xác minh lỗi hoặc chính sách thật, không xem `3.15.0` là phiên bản có lỗi thực tế từ ví dụ.

Ý nghĩa:

- `strictly("[3.14, 4.0[")`: chỉ chấp nhận phiên bản nằm trong khoảng được quy định, không chấp nhận ngoài khoảng.
- `prefer("3.14.0")`: ưu tiên version đó khi các yêu cầu khác cho phép; **không phải ràng buộc bắt buộc**.
- `reject("3.15.0")`: từ chối candidate cụ thể nếu có.
- `because`: giải thích nguồn của chính sách.

Nếu không có version nào đồng thời thỏa các constraints, Gradle báo lỗi resolution. Đó là **tín hiệu cần xử lý**, không phải lý do tự động bỏ mọi constraint.

### 10.3. Không dùng strictly exact một cách tùy tiện

Nếu một library publish với `strictly("1.0.0")` cho dependency phổ biến, nó có thể khiến consumer không thể dùng version 1.1 dù API tương thích. Với thư viện tái sử dụng, cân nhắc **range compatible** và test thực tế; với ứng dụng cuối có thể ràng buộc chặt hơn theo bộ version đã kiểm thử.

**Strictly** là tuyên bố về **điều kiện chấp nhận**; dùng nó khi có bằng chứng, không phải khi chỉ muốn “build ổn định”.

## 11. Phát hiện conflict bằng dependency graph

Lệnh cơ bản khi dự án áp dụng Java plugin:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

Nếu cần graph của test:

~~~bash
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath --console=plain
.\gradlew.bat dependencies --configuration testRuntimeClasspath --console=plain
~~~

Một đoạn output **minh họa** về hình thức:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- example:lib-a:1.0
|    \--- example:common:1.4 -> 1.8
+--- example:lib-b:2.0
|    \--- example:common:1.8
\--- example:common:1.5 -> 1.8
~~~

Không giả định các module `example:*` tồn tại. Đây là sơ đồ chữ để giải thích ký hiệu:

- `1.4 -> 1.8`: Gradle đã chọn version `1.8` thay cho yêu cầu `1.4`.
- `(c)`: node xuất phát từ **constraint**, không phải một dependency jar được thêm trực tiếp.
- `(*)`: một subtree đã xuất hiện ở nhánh trước nên output không lặp lại toàn bộ.
- `(n)`: một dependency hoặc configuration chưa được resolve/không thể resolve trong ngữ cảnh tương ứng; cần xem phiên bản Gradle cụ thể.
- `FAILED`: không resolve được module/variant; cần tìm nguyên nhân thật, không chỉ nhìn mũi tên.

**Đừng nhìn duy nhất version ở dòng đầu**. Một module có thể bị kéo bởi hàng chục đường bắc cầu; node đã được viết tắt `(c)`/`(*)` dễ khiến người đọc bỏ sót nguồn conflict.

### 11.1. Đọc graph không thay thế unit test

Nếu hai module có version giống nhau, chúng vẫn có thể không tương thích với những thư viện khác, API chuyển đổi, JVM version hoặc hệ thống plugin ở runtime. Graph là **bằng chứng về dependency selection**, không phải bằng chứng tất cả code tương tác chính xác.

## 12. `dependencyInsight`: ai đã chọn version này và vì sao?

`dependencyInsight` là công cụ nên dùng sớm nhất khi gặp một dependency lạ trên classpath.

Ví dụ:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-core \
  --configuration runtimeClasspath \
  --console=plain
~~~

Hoặc:

~~~bash
./gradlew dependencyInsight \
  --dependency org.junit.jupiter:junit-jupiter-api \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --dependency jackson-core --configuration runtimeClasspath --console=plain
~~~

Báo cáo cho biết:

1. Version nào được **selected**.
2. Những version nào đã được **requested**.
3. Đường đi **ngược từ module tới những dependency yêu cầu nó** (đường “required by”).
4. Lý do như **By conflict resolution**, **By constraint**, **By ancestor**, **Forced**, **Selected by rule**, **Rejection** (tùy trường hợp).
5. Attributes/variants liên quan nếu có.

Khi thấy một BOM xuất hiện ở graph nhưng version thực tế vẫn không như dự kiến, báo cáo này giúp tìm **ràng buộc cạnh tranh** nào đã tác động đến kết quả.

### 12.1. Một quy trình phân tích cụ thể

Giả sử một ứng dụng lỗi `NoSuchMethodError` tại method của Jackson:

1. Xác định class và module sở hữu API ở stack trace.
2. Chạy `dependencyInsight --dependency jackson-databind --configuration runtimeClasspath`.
3. Chạy thêm cho `jackson-core` và `jackson-annotations`.
4. Ghi lại version **selected** của từng module và đường đi yêu cầu chúng.
5. Tìm BOM/platform/strict constraint/force nào ảnh hưởng selection.
6. So sánh với release train mà vendor công bố, sau đó nâng BOM hoặc module phù hợp.
7. Chạy lại unit/integration tests trên **runtimeClasspath thực tế**.

Nếu lỗi chỉ xảy ra trong test, kiểm tra `testRuntimeClasspath` thay vì `runtimeClasspath`. Nếu plugin Gradle bị lỗi khi áp dụng, cần kiểm tra **plugin classpath**, không mặc định đó là classpath Java của ứng dụng.

### 12.2. Build scan/Develocity

Một Build Scan có thể hiển thị dependency graph và nguồn version selection theo cách trực quan, nhưng phải xem chính sách chia sẻ của tổ chức trước khi tạo/gửi scan, vì scan có thể tiết lộ tên dependency nội bộ, repository hoặc cấu hình build.

Lệnh CLI `dependencies` và `dependencyInsight` thường đủ cho một cuộc điều tra ban đầu và không cần dữ liệu gửi tới dịch vụ bên ngoài.

## 13. Cách phát hiện và xử lý các loại không tương thích

Không phải mọi vấn đề đều là một “version conflict”.

| Loại vấn đề | Dấu hiệu | Gradle có thể làm gì? | Cần làm gì thêm? |
| --- | --- | --- | --- |
| Cùng module, nhiều requested versions | Graph có `1.0 -> 1.4` | Chọn version theo rules/constraints | Kiểm tra API và test |
| Các module liên quan bị lệch release train | `core 2.0`, `annotations 1.8` | BOM/platform/virtual alignment | Theo BOM vendor, chạy tests |
| Hai implementation cùng cung cấp một chức năng | Hai logging providers hoặc implementation thay thế | **Capabilities** nếu metadata có khai báo | Chọn một provider đúng |
| Missing class | `NoClassDefFoundError` | Graph giúp xác định thiếu module/variant | Kiểm tra runtime dependency, shading, exclusions |
| Method không tồn tại | `NoSuchMethodError` | Không tự chứng minh binary compatibility | Kiểm tra compile/runtime graph, API version |
| Linkage error | `AbstractMethodError`, `LinkageError` | Không luôn detect được qua version number | Kiểm tra ABI, classloaders, plugins |
| Test engine không được tải | Không chạy test hoặc thiếu engine/launcher | BOM và graph giúp chọn version | Kiểm tra JUnit Platform runtime |
| Same class từ hai JAR khác module | Classpath duplicate | Không luôn bắt được nếu metadata thiếu | Kiểm tra capabilities, classpath scan, packaging |
| JPMS/module-path conflict | Module name trùng hoặc split package | Java module system có thể phát hiện lúc chạy | Xem module path, module descriptors |

**Quan trọng:** BOM giảm rủi ro tổ hợp sai, nhưng không đảm bảo **tương thích nhị phân, hành vi hoặc logic nghiệp vụ**. Cần test thực tế.

### 13.1. NoSuchMethodError là dấu hiệu nào?

Ví dụ khi code compile trên API mới, nhưng runtime lấy JAR cũ không chứa method đó, JVM có thể ném `NoSuchMethodError`. Hãy kiểm tra version/classpath **lúc chạy**. Tránh lập tức thêm version constraint mới mà chưa biết class thật được tải từ JAR nào.

Trong môi trường plugin, IDE, application server hoặc Java module system, có thể còn classloader khác. `runtimeClasspath` của Gradle là một nguồn dữ liệu quan trọng, nhưng không nhất thiết mô tả mọi classloader của runtime ngoài.

### 13.2. NoClassDefFoundError không luôn là thiếu dependency trực tiếp

Lỗi này có thể do module không có trên runtime classpath, dependency bị `exclude`, classifier/variant sai, class không tương thích hoặc lỗi trong static initialization của class. Xem **nguyên nhân gốc** trong stack trace, rồi đối chiếu graph.

Nếu chỉ có một `ClassNotFoundException` trong ứng dụng nhưng module có thật, cần xem nơi classloader tìm lớp, không giả định BOM là lời giải.

## 14. Capability conflicts: khác version conflicts

Một **capability** mô tả chức năng mà một component/variant cung cấp. Hai module **khác tên** có thể cung cấp cùng capability, chẳng hạn hai implementation logging thay thế.

Trong khi version conflict xử lý `same group:name, different version`, capability conflict có thể xảy ra ở **different group:name, same capability**.

Nếu hai variant cùng khai báo capability không thể đồng thời tồn tại, Gradle có thể **fail resolution** để người dùng chọn một implementation. Điều này thường tốt hơn việc lặng lẽ đặt hai provider trên classpath.

Ví dụ **mẫu xử lý khi metadata thực sự có capability**:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.capabilitiesResolution.withCapability(
        "com.example:logging"
    ) {
        // Chỉ minh họa API. Không tự chọn cao nhất
        // nếu các implementation không thể so version.
        selectHighestVersion()
    }
}
~~~

**Cảnh báo:** `com.example:logging` là capability minh họa, không phải tên chuẩn của mọi logging provider. `selectHighestVersion()` giữa hai implementation khác nhau có thể dẫn đến lựa chọn không mong muốn. Khi làm thật, ưu tiên **chọn đúng provider theo kiến trúc**, loại bỏ provider dư hoặc khai báo `select(...)` theo hướng dẫn của plugin/Gradle API.

### 14.1. Nếu metadata không khai báo capability thì sao?

Gradle **không tự biết** hai JAR có cùng chức năng hoặc cùng class. Nếu module metadata thiếu capability, có thể phải thêm **component metadata rule** để khai báo quan hệ, hoặc đưa dependency/exclusion đúng vào build. Chỉ thêm `failOnVersionConflict()` sẽ không xử lý xung đột giữa **hai module khác group:name**.

### 14.2. Ví dụ SLF4J

Với ứng dụng dùng SLF4J, classpath có nhiều SLF4J provider có thể gây cảnh báo hoặc behavior không như mong đợi. BOM chọn version cho API không tự bảo đảm chỉ có **một logging implementation**. Cần xem runtime graph, loại bỏ provider không mong muốn và chạy smoke test khởi động ứng dụng.

Không dựa vào module name hoặc BOM để khẳng định một provider nào luôn tương thích với tất cả API version; đối chiếu tài liệu chính thức của logging framework/version cụ thể.

## 15. `failOnVersionConflict()` — bật khi điều tra, không phải thay BOM

Gradle cho phép làm resolution thất bại nếu trong graph có nhiều requested versions của cùng module, thay vì tự nâng version theo quy tắc bình thường.

~~~kotlin
configurations.configureEach {
    resolutionStrategy {
        failOnVersionConflict()
    }
}
~~~

Đây là **mẫu cấu hình bổ sung** đặt ở `build.gradle.kts` của project. Khi bật, một graph vốn được Gradle tự giải quyết bằng cách chọn phiên bản cao có thể trở thành **build failure**.

Sử dụng hữu ích khi:

- Audit một dự án mới, muốn thấy nơi module version không thống nhất.
- Tạo job CI chẩn đoán dependency drift.
- Có policy rõ rằng mọi yêu cầu phiên bản phải phù hợp tuyệt đối.

Nhưng không phải lúc nào cũng nên bật trong mọi project: nhiều hệ sinh thái có transitive requests khác nhau **một cách hợp lệ** và BOM/constraints được dùng chính để giải quyết chúng. Một build có BOM vẫn có thể chứa những requested versions khác nhau do thư viện bắc cầu; `failOnVersionConflict` có thể báo lỗi ngay cả khi resolved graph đã được căn chỉnh theo chính sách.

**Không nhầm công cụ cảnh báo với chứng minh incompatibility.** Version conflict có thể là điều Gradle xử lý bình thường; binary incompatibility có thể xảy ra ngay cả khi không có version conflict nào.

### 15.1. Một số rule fail khác

Gradle có những API như:

~~~kotlin
configurations.configureEach {
    resolutionStrategy {
        failOnDynamicVersions()
        failOnChangingVersions()
    }
}
~~~

Mẫu này làm build fail khi dependency graph dùng dynamic versions (`1.+`) hoặc changing versions (`-SNAPSHOT` và metadata liên quan) theo quy tắc được hỗ trợ. Có thể dùng để tăng tính ổn định trong CI release. Nó **không trực tiếp kiểm tra phiên bản API có tương thích**; chỉ kiểm tra tính tái lập và chính sách version.

### 15.2. Tránh `resolutionStrategy.force()` làm giải pháp đầu tiên

Ví dụ can thiệp mạnh:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.force("com.example:core:1.2.0")
}
~~~

Đây là **mảnh minh họa** cho một module giả. `force` có thể che việc dependency khác cần version 1.3 hoặc cao hơn. Trước khi dùng, tìm hiểu vì sao graph chọn version đó; thường có giải pháp rõ hơn qua BOM upgrade/constraints hoặc sửa dependency khai báo sai.

## 16. Dependency locking: cố định graph đã được chọn

Ngay cả với BOM, graph vẫn có thể đổi nếu có dynamic version, changing metadata hoặc repository cập nhật. **Dependency locking** giúp lưu những resolved versions của các configuration, tránh việc hai lần build tự chọn phiên bản khác nhau mà không được review.

Một mẫu cho dự án Java:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Chạy trên project có dependency và các resolvable configurations phù hợp:

~~~bash
./gradlew dependencies --write-locks
~~~

Để chỉ tập trung một classpath:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --write-locks
~~~

Lệnh có thể tạo **gradle.lockfile** trong project; file này nên được **commit vào Git** cùng cấu hình build để mọi môi trường sử dụng cùng resolved versions. Với multi-project, phải chạy các task/configurations cần resolve ở đúng project để sinh lock state tương ứng.

### 16.1. Lock file khác BOM như thế nào?

- **BOM:** nêu version constraints/recommendations cho một tập dependency.
- **Lock file:** ghi **resolved versions cuối cùng** của các module trên những configuration được lock.
- **Version catalog:** giúp source dùng tên/coordinates nhất quán.
- **Dependency verification:** kiểm tra integrity của artifact qua hash/signature, không chọn version.

Các cơ chế bổ sung cho nhau.

### 16.2. Đổi BOM nhưng quên cập nhật locks

Nếu nâng BOM từ bản X lên Y làm resolved versions thay đổi, lock state cũ có thể làm resolution fail hoặc tiếp tục ghim những version không còn phù hợp. Khi chủ động nâng cấp:

1. Sửa version BOM/constraints trong source.
2. Chạy lệnh resolve với `--write-locks` theo đúng phạm vi.
3. Review `gradle.lockfile` diff.
4. Chạy unit, integration, smoke tests.
5. Commit cùng một thay đổi gồm BOM và lockfile.

Không sửa lockfile bằng tay để né lỗi, trừ trường hợp quản trị đã hiểu chính xác format và lý do.

### 16.3. Những trường hợp lock chưa đủ

Lock file ghi phiên bản module, nhưng artifact dạng changing dependency có thể đổi nội dung với **cùng tọa độ version**. Vì vậy Gradle không khuyến nghị locking để coi `-SNAPSHOT` như nguồn byte hoàn toàn ổn định. Kết hợp fixed release versions và dependency verification khi cần độ tin cậy cao.

## 17. Dependency verification và an ninh chuỗi cung ứng

Version alignment giải quyết **version compatibility policy**; nó không chứng minh JAR được tải đúng byte từ nguồn đáng tin.

Gradle hỗ trợ **dependency verification** qua metadata checksum/signature. Đây là kiểm tra **integrity**, không giống BOM và locking.

Một cách nhìn:

~~~text
BOM/platform       -> chọn bộ version mong muốn
Conflict resolution-> chọn module variant/version trong graph
Dependency locking -> giữ resolved graph ổn định
Verification       -> kiểm tra artifact/metadata tải về
Tests               -> kiểm tra behavior tương tác lúc chạy
~~~

Nếu một artifact trong repository bị thay thế nhưng vẫn giữ version cũ, BOM và lockfile có thể không phát hiện thay đổi byte; verification có thể bổ sung khả năng phát hiện. Ngược lại, checksum hợp lệ không chứng minh API tương thích — test vẫn cần thiết.

Với kho nội bộ hoặc public registry, áp dụng repository filters và TLS, khóa quyền publish và cập nhật BOM sau khi kiểm thử.

## 18. Gradle Module Metadata, Maven POM và sự tương thích

Gradle có thể nhận dữ liệu từ **Gradle Module Metadata (.module)** hoặc Maven POM. Metadata có thể thể hiện các ý nghĩa khác nhau:

- Dependency trực tiếp/bắc cầu và yêu cầu version.
- Dependency constraints và platforms.
- Attributes để chọn variant như API/runtime, target JVM, capabilities.
- Những ràng buộc mà Maven POM không biểu đạt đầy đủ.

Một thư viện publish metadata tốt giúp Gradle chọn graph phù hợp hơn; nếu nhà phát hành chỉ có POM cũ hoặc metadata thiếu, Gradle có thể không biết một tổ hợp version bất tương thích.

### 18.1. Hệ quả thực tế

- Khi dùng Gradle BOM có metadata platform, xem `dependencyInsight` để xác định constraints thực tế.
- Khi project library publish sang Maven consumer, cân nhắc những thông tin được giữ/mất ở POM so với `.module`.
- Không suy luận rằng dependency phù hợp với Java 17 chỉ vì BOM đã align version: các variant có thể yêu cầu JVM cao hơn.
- Khi có lỗi “No matching variant”, xem attributes và target JVM, không chỉ thay BOM.

## 19. Quy trình điều tra một lỗi runtime do dependency

Giả sử ứng dụng Java 17 gặp:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Một quy trình kiểm tra gồm:

**Bước 1 — Xác định nơi lỗi xảy ra.** Đọc stack trace, class/method, môi trường chạy (local, test, app server, container). Không tự kết luận thư viện nào sai chỉ từ tên exception.

**Bước 2 — Chọn configuration tương ứng.**

- Ứng dụng chạy: `runtimeClasspath`.
- Unit/integration test: `testRuntimeClasspath` hoặc configuration của test suite tương ứng.
- Java annotation processor: `annotationProcessor` hoặc `testAnnotationProcessor`.
- Gradle plugin: plugin/buildscript classpath, không phải runtimeClasspath của app.

**Bước 3 — Xem graph và candidate.**

~~~bash
./gradlew dependencies --configuration runtimeClasspath --console=plain
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath --console=plain
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath --console=plain
~~~

**Bước 4 — Đối chiếu BOM và ràng buộc mạnh.** Tìm `platform`, `enforcedPlatform`, `strictly`, `force` hoặc custom resolution rules. Nếu graph chọn version cao hơn BOM, tìm request gây upgrade thay vì tin rằng BOM luôn pin.

**Bước 5 — Xem runtime packaging.** Với WAR, fat JAR, Spring Boot executable archive, application server và container, classloader/runtime classpath có thể khác với output `runtimeClasspath`. Kiểm tra file thực sự được đóng gói và version của chúng.

**Bước 6 — Sửa nguyên nhân.** Ưu tiên nâng BOM cùng các module vendor; hoặc thêm constraint có căn cứ để giới hạn một module bị lỗi. Tránh `exclude` bừa làm mất class.

**Bước 7 — Kiểm chứng.** Chạy `./gradlew clean test`, integration tests, smoke test khởi động app và kiểm tra dependency graph/lockfile ở CI. Nếu sự cố chỉ xảy ra ở production, cần tái tạo đúng môi trường/classpath.

## 20. Ví dụ một kịch bản conflict và cách đọc

Một app khai báo:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    // Một dependency khác có thể kéo cùng module ở version cũ hơn.
}
~~~

Nếu một dependency bắc cầu yêu cầu `commons-lang3:3.12.0`, graph sẽ có nhiều requests cho cùng module. Gradle có thể chọn 3.14.0 vì là version cao hơn được yêu cầu. Điều này không nhất thiết là build lỗi.

Đoạn output **minh họa**:

~~~text
+--- org.apache.commons:commons-lang3:3.14.0
\--- some.group:legacy-lib:1.0
     \--- org.apache.commons:commons-lang3:3.12.0 -> 3.14.0
~~~

Giải thích:

1. `legacy-lib` yêu cầu 3.12.0.
2. App yêu cầu 3.14.0.
3. Gradle chọn 3.14.0 cho graph đang xét.
4. Cần test để biết `legacy-lib` có hoạt động với 3.14.0 không; **mũi tên `->` chỉ cho thấy lựa chọn**, không phải xác nhận tương thích.

Nếu các dependencies này có thêm một BOM/constraint cạnh tranh, kết quả có thể khác. Luôn đọc `dependencyInsight` khi có bất ngờ.

## 21. Tránh các sai lầm phổ biến

| Sai lầm | Tại sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Tưởng BOM kéo tất cả JAR vào classpath | BOM chỉ cung cấp constraints/version policy | Khai báo module thực sự cần dùng |
| Dùng dependency BOM như JAR thường | Không chọn platform variant | Dùng `platform("g:bom:v")` |
| Nhầm BOM với version catalog | Catalog không tự điều khiển transitive graph | Dùng `platform(libs.bom)` trong dependencies |
| Cho rằng `platform` pin cứng mọi version | Regular platform cho phép upgrade theo graph | Đọc dependencyInsight; dùng enforcement chỉ khi có lý do |
| `enforcedPlatform` trong library publish chung | Ràng buộc mạnh có thể truyền sang consumer | Ưu tiên platform/constraints hoặc compatible strict range |
| Ép mọi module cùng group về một số version | Vendor có thể dùng nhiều version scheme | Theo BOM/metadata của vendor |
| Chỉ xem `compileClasspath` khi runtime lỗi | Runtime graph có thể khác | Kiểm tra `runtimeClasspath` và artifact đóng gói |
| Chọn `force` ngay khi gặp conflict | Có thể che API requirement của dependency | Tìm nguồn request và sửa BOM/constraints |
| `exclude` thư viện lạ không kiểm tra | Có thể làm class runtime biến mất | Dùng dependencyInsight, xem module thực sự cần |
| Bật failOnVersionConflict ở mọi project mà không đánh giá | Conflict được giải quyết hợp lệ cũng có thể làm build fail | Dùng có mục đích, hiểu BOM/constraints |
| Chỉ so version số học để đánh giá compatibility | Major/minor không luôn phản ánh ABI | Đọc compatibility matrix, chạy integration tests |
| Tưởng mọi provider conflict đều là version conflict | Hai implementation khác module có thể gây capability conflict | Dùng capabilities và chọn provider |
| Chỉ dùng lockfile, bỏ verification | Lock không chứng minh artifact byte không đổi | Dùng dependency verification khi cần |
| Dùng dynamic version trong release | Graph có thể trôi theo thời gian | Pin version và/hoặc dependency locking |
| Đổi BOM nhưng quên lockfile | Lock cũ xung đột với graph mới | Regenerate và review lockfile |
| Dùng `--offline` để kiểm tra BOM mới chưa cache | Không có metadata/artifact mới | Cho phép online resolve từ repo đáng tin |
| Báo version mới nhất dựa vào tài liệu cũ | Dependency versions đổi theo thời gian | Xác nhận version phù hợp với Wrapper/vendor docs |

## 22. Checklist triển khai trong CI

Một CI build đáng tin có thể thực hiện theo thứ tự:

1. Chạy với **Gradle Wrapper** được commit và JDK/toolchain mà dự án xác định.
2. Resolve dependencies từ repositories được phép (ưu tiên HTTPS; lọc internal groups).
3. Import BOM hoặc platform do tổ chức đã chọn.
4. Có `gradle.lockfile` nếu sử dụng dependency locking, và bắt buộc review thay đổi.
5. Dùng `dependencyInsight` khi phát hiện version drift hoặc runtime failure.
6. Chạy compile/test/integration tests trên resolved graph thật.
7. Có smoke test khởi động Java app để bắt API/linkage/classloading errors.
8. Kiểm tra classpath của artifact phân phối nếu dùng fat JAR/WAR/container.
9. Dùng dependency verification nếu policy yêu cầu checksum/signature.
10. Chỉ nâng BOM sau khi đánh giá release notes, policy an ninh và compatibility matrix.
11. Không tự thêm `force` hay `enforcedPlatform` để vượt qua một CI failure mà chưa phân tích.
12. Lưu báo cáo graph/CI theo quy định bảo mật nếu tên module nội bộ nhạy cảm.

### 22.1. Các lệnh tóm tắt

~~~bash
# Xem runtime graph:
./gradlew dependencies --configuration runtimeClasspath

# Truy ngược một module:
./gradlew dependencyInsight \
  --dependency jackson-core \
  --configuration runtimeClasspath

# Xem test graph:
./gradlew dependencies --configuration testRuntimeClasspath

# Chạy unit tests:
./gradlew clean test

# Tạo/cập nhật dependency locks khi đã bật locking:
./gradlew dependencies --write-locks
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency jackson-core --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat clean test
.\gradlew.bat dependencies --write-locks
~~~

Nếu một project không áp dụng Java plugin, configuration `runtimeClasspath` có thể không tồn tại; cần chọn configuration thực tế từ `./gradlew resolvableConfigurations` hoặc báo cáo dependencies theo Gradle Wrapper đang dùng.

## 23. Câu hỏi tự kiểm tra

**Câu 1:** `implementation(platform("g:bom:v"))` có thêm tất cả các thư viện trong BOM vào classpath không?

**Trả lời:** Không. BOM thêm constraints; các module chỉ xuất hiện khi được khai báo trực tiếp hoặc bắc cầu.

**Câu 2:** BOM JUnit cùng quản lý Jupiter và Platform, có bắt buộc mọi module dùng cùng số `5.10.2` không?

**Trả lời:** Không. JUnit Platform có version scheme riêng; BOM định nghĩa các version tương thích, không bắt mọi artifact cùng số.

**Câu 3:** Vì sao imported regular platform vẫn có thể chọn version cao hơn BOM?

**Trả lời:** Vì các version thông thường từ BOM là constraints/recommendations tham gia Gradle conflict resolution, không phải enforced pin trong mọi tình huống.

**Câu 4:** Khi nào cân nhắc enforcedPlatform?

**Trả lời:** Khi cần enforce toàn bộ BOM ở một ứng dụng đã được thử nghiệm và hiểu rõ tác động; tránh mặc định áp dụng cho library được consumer khác sử dụng.

**Câu 5:** Version catalog chứa alias `libs.jackson.bom` có tự quản lý runtime Jackson versions không?

**Trả lời:** Không. Cần khai báo `platform(libs.jackson.bom)` trong configuration phù hợp.

**Câu 6:** `dependencyInsight` hữu ích hơn `dependencies` ở điểm gì?

**Trả lời:** Nó giải thích **vì sao một selected module version được chọn**, những request nguồn và các ràng buộc tham gia.

**Câu 7:** `failOnVersionConflict()` có bắt mọi trường hợp binary incompatibility không?

**Trả lời:** Không. Nó chỉ bắt version conflicts theo cơ chế resolution. Binary incompatibility có thể tồn tại dù chỉ có một version cho mỗi module.

**Câu 8:** Hai logging implementations khác module cùng classpath, version conflict có tự loại một bên không?

**Trả lời:** Không nhất thiết. Đây có thể là **capability/implementation conflict**, Gradle chỉ phát hiện nếu metadata/rules mô tả sự trùng chức năng.

**Câu 9:** Lockfile và BOM khác nhau thế nào?

**Trả lời:** BOM quy định constraints cho một tập library; lockfile ghi **resolved versions cuối cùng** cho các configurations được lock, nhằm cố định graph giữa các lần build.

**Câu 10:** `NoSuchMethodError` ở production trong khi test local pass thì cần xem gì?

**Trả lời:** So sánh runtimeClasspath thực sự, file được đóng gói, classloaders, JDK, BOM version và transitive graph của môi trường production; tái hiện bằng integration/smoke test.

**Câu 11:** Khi không có published BOM nhưng module cùng release train cần alignment, Gradle có cách nào?

**Trả lời:** Dùng component metadata rules và virtual platform (`belongsTo(...)`), nhưng phải giới hạn chính xác module có chính sách version chung.

**Câu 12:** Dùng `strictly("[2.0,3.0[")` có nghĩa Gradle sẽ luôn chọn version 2.0?

**Trả lời:** Không. Nó đặt khoảng version chấp nhận; Gradle còn xét các yêu cầu khác, candidates có sẵn và `prefer` nếu được khai báo.

## 24. Tóm tắt quyết định

~~~text
Có BOM chính thức?
   |
   +-- Có --> import platform(BOM), không hard-code từng version
   |           |
   |           +-- Kiểm tra selected versions bằng dependencyInsight
   |           +-- Nâng BOM cùng test khi graph không phù hợp
   |
   +-- Không --> Java Platform của tổ chức / constraints cụ thể
               |
               +-- Các module cùng release train?
                   -> cân nhắc virtual platform nếu có metadata đầy đủ

Nếu có vấn đề:
   dependencies -> dependencyInsight -> BOM/constraints/variants
       -> runtime compatibility tests -> lockfile + verification
~~~

**Điều cần nhớ nhất:** BOM/platform giải quyết **quản trị phiên bản**; Gradle dependency resolution chọn **module và variant**; `dependencyInsight` giải thích kết quả; còn **tương thích thực tế** phải được xác minh bằng metadata chính xác, constraints có căn cứ và tests trên classpath thực sự. Không có một checkbox Gradle nào chứng minh toàn bộ tổ hợp thư viện luôn tương thích.

## 25. Tài liệu chính thức

1. Gradle — Platforms & Maven BOMs: https://docs.gradle.org/current/userguide/platforms.html
2. Gradle — How to Align Dependency Versions: https://docs.gradle.org/current/userguide/how_to_align_dependency_versions.html
3. Gradle — Dependency Constraints and Conflict Resolution: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
4. Gradle — Declaring Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
5. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
6. Gradle — Graph Resolution: https://docs.gradle.org/current/userguide/graph_resolution.html
7. Gradle — Using Resolution Rules: https://docs.gradle.org/current/userguide/resolution_rules.html
8. Gradle — Locking Dependency Versions: https://docs.gradle.org/current/userguide/dependency_locking.html
9. Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
10. Gradle — Java Platform Plugin: https://docs.gradle.org/current/userguide/java_platform_plugin.html
11. Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html

Tài liệu `current` phản ánh phiên bản Gradle mới nhất tại thời điểm truy cập, không phải mặc nhiên bản của mọi repository. Khi áp dụng thật, đối chiếu **phiên bản Gradle Wrapper**, version BOM/vendor compatibility matrix và metadata thực tế; các version trong bài chỉ là ví dụ kỹ thuật, không phải thông báo chúng là phiên bản mới nhất.