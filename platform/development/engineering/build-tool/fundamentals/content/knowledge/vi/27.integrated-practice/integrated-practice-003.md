# Bổ sung thư viện bên ngoài và giải thích đồ thị phụ thuộc

Một ứng dụng Java thường sử dụng thư viện đã được phát hành thay vì tự viết mọi chức năng. Thư viện có thể hỗ trợ xử lý JSON, gọi HTTP, ghi log, truy cập database, kiểm thử hoặc làm việc với ngày giờ. Khi thêm thư viện, build tool phải biết artifact nằm ở đâu, version nào được chọn, cần tải những thành phần nào và những thư viện khác nào được kéo theo.

Các quan hệ đó tạo thành **đồ thị phụ thuộc** (dependency graph). Hiểu graph giúp trả lời những câu hỏi thực tế: Vì sao build tải một JAR mà mình không khai báo? Hai thư viện cùng yêu cầu các version khác nhau thì build chọn bản nào? Vì sao compile thành công nhưng runtime lại thiếu class? Làm sao tìm đường dẫn khiến một dependency xuất hiện?

Bài học này hướng dẫn cách thêm thư viện bên ngoài bằng Gradle và Maven, đọc dependency coordinates, phân biệt dependency trực tiếp và bắc cầu, hiểu scope/configuration, xem graph, xử lý version conflict và xác nhận build dùng đúng thư viện.

## 1. Thư viện bên ngoài là gì?

Thư viện bên ngoài (external library) là mã đã được đóng gói và phát hành để dự án khác sử dụng, thường dưới dạng JAR trong hệ sinh thái Java.

Ví dụ thư viện có thể cung cấp:

- API để xử lý JSON hoặc XML.
- HTTP client để gọi dịch vụ.
- Logging framework.
- JDBC driver để kết nối database.
- Bộ tiện ích cho collection, date/time hoặc validation.
- Framework ứng dụng.
- Công cụ kiểm thử.
- Annotation processor hoặc compiler extension.

Thay vì tự viết bộ chuyển đổi JSON, dự án có thể dùng Jackson. Thay vì tự xây HTTP client, dự án có thể dùng thư viện phù hợp với framework đang sử dụng.

Thư viện thường được tải từ repository như Maven Central hoặc repository nội bộ. Gradle và Maven đọc metadata để tìm artifact, xác định dependency bắc cầu và tải các file cần thiết.

## 2. Dependency coordinates: xác định đúng thư viện

Trong Maven ecosystem, một artifact thường được nhận diện bằng các thành phần:

- **groupId**: namespace hoặc tổ chức phát hành.
- **artifactId**: tên artifact.
- **version**: phiên bản cụ thể.
- **type/extension**: loại file, thường là JAR hoặc POM.
- **classifier**: biến thể bổ sung nếu có, ví dụ sources hoặc javadoc.

Ví dụ tọa độ:

```text
com.fasterxml.jackson.core:jackson-databind:2.17.2
```

| Thành phần | Giá trị |
|---|---|
| groupId | com.fasterxml.jackson.core |
| artifactId | jackson-databind |
| version | 2.17.2 |
| type phổ biến | jar |

Tọa độ thường được viết theo dạng groupId:artifactId:version. Không nên chỉ dựa vào tên thư viện. Nhiều artifact có tên gần giống nhau, cùng tên nhưng thuộc group khác hoặc được phát hành bởi tổ chức khác. Khi thêm dependency, cần xác nhận tọa độ từ tài liệu chính thức hoặc repository đáng tin cậy.

### Repository là nơi lưu artifact

Repository là máy chủ hoặc dịch vụ lưu metadata và artifact. Ví dụ:

- Maven Central.
- Gradle Plugin Portal cho plugin Gradle.
- Repository riêng của công ty.
- Repository do framework hoặc nhà cung cấp quản lý.

Khai báo dependency và khai báo repository là hai việc khác nhau. Dependency nói dự án cần artifact nào; repository nói build tool tìm artifact ở đâu.

Ví dụ Gradle:

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
```

Với Maven Central, Maven thường có thể tìm artifact mà không cần khai báo repository riêng trong POM. Gradle cần repository được cấu hình trong build/settings theo chính sách của dự án.

## 3. Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp** (direct dependency) là thư viện được dự án khai báo rõ ràng trong build file.

**Dependency bắc cầu** (transitive dependency) là thư viện được kéo vào vì một dependency khác cần nó.

Ví dụ:

```text
Ứng dụng
  |
  +-- jackson-databind
  |      |
  |      +-- jackson-core
  |      |
  |      +-- jackson-annotations
  |
  +-- slf4j-api
```

Trong sơ đồ:

- Ứng dụng khai báo jackson-databind trực tiếp.
- jackson-core và jackson-annotations được kéo theo gián tiếp theo metadata của Jackson.
- slf4j-api là dependency trực tiếp khác.

Khi Gradle hoặc Maven resolve dependency, chúng xây dựng graph từ các khai báo trực tiếp và metadata của từng artifact. Một thư viện có thể xuất hiện qua nhiều đường khác nhau.

### Vì sao cần biết dependency bắc cầu?

Nếu build tải một JAR mà nhóm không nhớ đã thêm, có thể nó là dependency bắc cầu. Nếu một thư viện xuất hiện qua hai đường với hai version được yêu cầu, build tool phải áp dụng quy tắc chọn version. Nếu bỏ dependency cha, những dependency chỉ được kéo qua đường đó có thể biến mất.

Không nên khai báo trực tiếp một thư viện chỉ vì thấy nó trong graph mà chưa hiểu mục đích. Nhưng nếu source code của dự án trực tiếp import API của thư viện đó, nên khai báo dependency trực tiếp thay vì dựa vào việc một dependency khác tình cờ kéo nó theo.

## 4. Đồ thị phụ thuộc biểu diễn điều gì?

Dependency graph biểu diễn các module và quan hệ phụ thuộc giữa chúng. Mỗi nút là một module/artifact; mỗi cạnh chỉ ra một module yêu cầu module khác.

Ví dụ:

```text
:shop-app
  |
  +-- jackson-databind:2.17.2
  |       |
  |       +-- jackson-core
  |       |
  |       +-- jackson-annotations
  |
  +-- httpclient5
          |
          +-- httpcore5
          |
          +-- slf4j-api
```

Đây là graph minh họa, không phải output của một build cụ thể. Metadata thực tế và version được chọn phụ thuộc vào phiên bản artifact, repository và quy tắc resolution.

Một cạnh có thể mang theo thông tin:

- Module nào yêu cầu dependency.
- Version được yêu cầu.
- Scope hoặc configuration mà dependency thuộc về.
- Version được chọn sau conflict resolution.
- Constraint hoặc platform tác động đến kết quả.
- Dependency có bị loại trừ hoặc thay thế không.

Graph không chỉ là danh sách JAR. Nó giải thích vì sao một module xuất hiện và đường nào khiến nó được đưa vào classpath.

Cùng một thư viện có thể là direct dependency trong project A nhưng là transitive dependency trong project B. Cách phân loại phụ thuộc vào vị trí đang xét trong graph.

## 5. Thêm thư viện bằng Gradle Groovy DSL

Trong Gradle, dependency thường được khai báo trong khối dependencies của build.gradle.

Ví dụ:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Sau khi thêm, chạy:

```bash
./gradlew compileJava
```

Gradle sẽ resolve compile classpath và tải artifact cần thiết nếu chưa có trong cache.

Nếu muốn chạy test:

```bash
./gradlew test
```

Gradle cũng resolve các dependency thuộc test classpath theo configuration tương ứng.

Sau khi dependency được thêm và classpath được cấu hình, source code có thể import API của thư viện:

```java
import org.apache.commons.lang3.StringUtils;

public class NameFormatter {
    public String normalize(String name) {
        return StringUtils.trimToEmpty(name);
    }
}
```

Nếu dependency nằm đúng compile classpath, compiler có thể tìm được class StringUtils. Nếu khai báo nhầm configuration chỉ dành cho runtime hoặc test, compile có thể báo không tìm thấy package/class.

## 6. Thêm thư viện bằng Gradle Kotlin DSL

Nếu dự án dùng build.gradle.kts, cú pháp tương ứng:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Cần dùng cú pháp đúng với DSL của dự án. Không trộn cú pháp Groovy vào Kotlin DSL một cách máy móc.

- build.gradle thường dùng Groovy DSL.
- build.gradle.kts dùng Kotlin DSL.
- settings.gradle hoặc settings.gradle.kts cấu hình build và repository ở phạm vi tương ứng.

Tọa độ dependency có thể giống nhau, nhưng cách biểu diễn trong build script khác nhau.

## 7. Dùng Gradle Version Catalog

Version Catalog tập trung alias và version trong file gradle/libs.versions.toml. Cách này hữu ích khi nhiều module dùng cùng thư viện.

Ví dụ:

```toml
[versions]
commonsLang = "3.17.0"

[libraries]
commons-lang3 = {
    module = "org.apache.commons:commons-lang3",
    version.ref = "commonsLang"
}
```

Trong build.gradle:

```groovy
dependencies {
    implementation libs.commons.lang3
}
```

Trong build.gradle.kts:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Gradle tạo accessor từ alias. IDE có thể hỗ trợ autocomplete.

Version Catalog chỉ tập trung khai báo alias và version. Nó không tự thêm tất cả thư viện vào classpath. Module vẫn phải khai báo dependency trong dependencies. Catalog cũng không tự khóa toàn bộ dependency bắc cầu; nếu cần cố định kết quả resolution, hãy dùng dependency locking hoặc cơ chế quản lý phù hợp.

## 8. Thêm thư viện bằng Maven

Maven khai báo dependency trong phần dependencies của pom.xml.

Ví dụ:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>shop-app</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
    </dependencies>
</project>
```

Khi chạy:

```bash
mvn compile
```

Maven resolve dependency cần cho compile lifecycle và đưa artifact vào compile classpath.

Chạy test:

```bash
mvn test
```

Maven resolve thêm dependency có scope test và các plugin cần thiết cho lifecycle.

Maven còn hỗ trợ type, classifier, scope, optional và exclusions. Không phải mọi dependency đều chỉ cần ba trường groupId, artifactId và version.

## 9. Gradle configurations và Maven scopes

Gradle và Maven phân loại dependency theo mục đích sử dụng, nhưng mô hình của chúng không hoàn toàn giống nhau.

### Các Gradle configuration thường gặp

| Configuration | Mục đích |
|---|---|
| implementation | Dependency dùng cho compile/runtime implementation của module |
| api | Dependency được expose trên compile API của library khi dùng java-library plugin |
| compileOnly | Cần khi compile nhưng không đưa vào runtime classpath |
| runtimeOnly | Chỉ cần khi chạy ứng dụng |
| testImplementation | Dependency dùng để compile và chạy test |
| testRuntimeOnly | Chỉ cần khi chạy test |
| annotationProcessor | Processor dùng trong quá trình compile |
| testAnnotationProcessor | Processor dùng khi compile test |

Ví dụ:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    compileOnly 'org.projectlombok:lombok:1.18.34'
    annotationProcessor 'org.projectlombok:lombok:1.18.34'

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Các configuration cụ thể phụ thuộc plugin được áp dụng. Với Java plugin và java-library plugin, những configuration phổ biến được tạo sẵn.

### Các Maven scope thường gặp

| Scope | Compile source chính | Runtime ứng dụng | Test | Truyền sang consumer |
|---|---:|---:|---:|---|
| compile | Có | Có | Có | Có |
| provided | Có | Không theo runtime classpath thông thường | Có | Không truyền như compile dependency thông thường |
| runtime | Không | Có | Có | Có theo quy tắc scope |
| test | Không | Không | Có | Không |
| system | Có | Không theo repository resolution | Có | Không truyền như dependency thông thường |
| import | Dùng trong dependencyManagement với type pom | Không phải scope dependency thông thường | Tùy quản lý version | Nhập dependency management |

Maven scope quyết định dependency được dùng trong những classpath/lifecycle nào và cách nó truyền sang consumer. Cần xem quy tắc Maven cụ thể khi kết hợp scope qua nhiều tầng.

### Chọn scope/configuration đúng

- Thư viện mà source code chính import: Gradle implementation hoặc api tùy public API; Maven compile.
- JUnit chỉ dùng trong test: Gradle testImplementation; Maven test.
- JDBC driver chỉ cần khi chạy: Gradle runtimeOnly; Maven runtime.
- Annotation processor: Gradle annotationProcessor hoặc testAnnotationProcessor tùy source set.
- API mà library expose trong public signature: Gradle api với java-library plugin nếu consumer cần dependency đó trên compile classpath.

Chọn sai scope có thể tạo lỗi compile hoặc runtime dù dependency đã được khai báo.

## 10. Khi nào dùng api và implementation trong Gradle?

Với ứng dụng, implementation thường là lựa chọn phù hợp cho thư viện nội bộ của module. Với thư viện được consumer sử dụng, cần phân biệt dependency thuộc public API hay implementation detail.

Ví dụ module library có public API:

```java
import com.google.common.collect.ImmutableList;

public class ProductCatalog {
    public ImmutableList<String> productNames() {
        return ImmutableList.of("Book", "Pen");
    }
}
```

Kiểu ImmutableList xuất hiện trong public method signature. Consumer compile code sử dụng API này cần nhìn thấy Guava trên compile classpath. Trong java-library plugin, có thể khai báo:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'com.google.guava:guava:33.3.1-jre'
}
```

Nếu Guava chỉ được dùng bên trong implementation và không xuất hiện trong public API, có thể dùng implementation:

```groovy
dependencies {
    implementation 'com.google.guava:guava:33.3.1-jre'
}
```

implementation giúp tránh expose compile dependency không cần thiết cho consumer. Điều này giảm classpath và hạn chế ràng buộc API giữa các module.

Không dùng api chỉ để consumer nhìn thấy mọi thứ. Hãy xác định kiểu nào thực sự thuộc public API.

## 11. Dependency bắc cầu hoạt động như thế nào?

Giả sử project khai báo thư viện A:

```text
application
  |
  +-- library-A:1.0
         |
         +-- library-B:2.0
         |
         +-- library-C:3.1
                |
                +-- library-D:1.5
```

Build tool đọc metadata của A, biết A yêu cầu B và C. Metadata của C lại yêu cầu D. Graph mở rộng cho tới khi tất cả dependency cần thiết được resolve.

Ứng dụng không nhất thiết phải khai báo B, C và D nếu chỉ dùng API của A. Nhưng nếu source code ứng dụng trực tiếp import B, nên khai báo B trực tiếp để thể hiện đúng dependency của source code.

### Transitive dependency có thể bị loại trừ

Nếu một dependency kéo theo module không cần thiết hoặc gây xung đột, có thể dùng exclusion. Tuy nhiên, loại bỏ dependency chỉ an toàn khi biết module đó không cần cho runtime hoặc được cung cấp bằng cách khác.

Gradle:

```groovy
dependencies {
    implementation('com.example:legacy-client:1.4.0') {
        exclude group: 'commons-logging', module: 'commons-logging'
    }
}
```

Maven:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion được gắn với một cạnh/đường dependency. Nếu cùng module vẫn được kéo vào qua một đường khác, nó có thể tiếp tục xuất hiện trong graph.

## 12. Một dependency có thể được yêu cầu qua nhiều đường

Ví dụ:

```text
app
  |
  +-- library-A:1.0
  |      |
  |      +-- common-utils:1.4
  |
  +-- library-B:2.0
         |
         +-- common-utils:2.1
```

Cả A và B đều yêu cầu common-utils, nhưng version khác nhau. Build tool cần chọn một version hoặc báo conflict tùy quy tắc và cấu hình.

Cần phân biệt:

- Requested version: version một dependency yêu cầu.
- Selected version: version cuối cùng build tool chọn sau resolution.
- Constraint: giới hạn hoặc gợi ý version.
- Platform/BOM: bộ version được quản lý tập trung.
- Lock state: version đã được ghi nhận để tái sử dụng.

Một graph report tốt cho biết cả đường yêu cầu và version cuối cùng được chọn.

## 13. Gradle xử lý version conflict như thế nào?

Gradle xây graph và áp dụng conflict resolution. Với cùng một module được yêu cầu qua nhiều đường, Gradle thường chọn version cao hơn theo quy tắc mặc định. Tuy nhiên, constraints, platforms, rich versions, resolution rules hoặc dependency substitution có thể ảnh hưởng kết quả.

Ví dụ:

```groovy
dependencies {
    implementation 'com.example:common-utils:1.4'
    implementation 'com.example:report-client:2.0'
}
```

Giả sử report-client cũng yêu cầu common-utils:2.1. Gradle có thể chọn common-utils:2.1 theo quy tắc mặc định nếu không có constraint khác.

Không nên giả định version được chọn chỉ dựa vào dòng khai báo đầu tiên. Hãy dùng dependencyInsight để xem lý do.

### Constraints

Có thể thêm constraint để hướng resolution:

```groovy
dependencies {
    implementation 'com.example:report-client:2.0'

    constraints {
        implementation('com.example:common-utils:2.1') {
            because 'Giữ version tương thích với các consumer đã kiểm thử'
        }
    }
}
```

Constraint ảnh hưởng tới version khi module được đưa vào graph; nó không tự thêm module như một dependency thông thường.

### Platform/BOM

Nếu nhiều artifact cùng thuộc một bộ thư viện, platform/BOM giúp căn chỉnh version:

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
```

BOM quản lý version các module Jackson. Các dependency vẫn cần được khai báo để chúng được đưa vào classpath.

Không dùng force như cách sửa mặc định. Ép version có thể phá giả định tương thích của dependency khác. Trước khi dùng, hãy kiểm tra graph, release notes và test. Ưu tiên platform, constraint hoặc nâng dependency cha lên bộ version tương thích.

## 14. Maven xử lý version conflict như thế nào?

Maven dùng quy tắc dependency mediation. Khi cùng một artifact xuất hiện ở nhiều đường với version khác nhau, Maven thường chọn version gần nhất với project trong dependency tree (nearest definition). Nếu hai version ở cùng độ sâu, thứ tự khai báo có thể quyết định lựa chọn.

Ví dụ:

```text
app
  |
  +-- library-A:1.0
  |      |
  |      +-- common-utils:1.4
  |
  +-- library-B:2.0
         |
         +-- common-utils:2.1
```

Nếu hai đường có độ sâu bằng nhau, thứ tự khai báo dependency có thể ảnh hưởng version được chọn. Vì vậy, không nên dựa vào thứ tự không rõ ràng để quản lý version.

### dependencyManagement

Maven có thể quản lý version tập trung:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>common-utils</artifactId>
            <version>2.1</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

dependencyManagement quản lý version/scope khi dependency tương ứng được khai báo; nó không tự thêm mọi artifact vào classpath.

Nếu cần thêm dependency, vẫn khai báo trong dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>common-utils</artifactId>
    </dependency>
</dependencies>
```

### BOM import

Maven có thể import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Sau đó dependency Jackson có thể không cần khai báo version riêng nếu BOM quản lý artifact đó.

## 15. Exclusion và optional dependency trong Maven

Maven hỗ trợ exclusion trên một dependency:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion loại artifact khỏi đường bắc cầu của dependency đó. Nếu artifact được yêu cầu qua dependency khác, nó vẫn có thể xuất hiện.

Một dependency được khai báo optional trong Maven không tự động truyền tiếp như dependency thông thường sang consumer. Consumer cần tự khai báo nếu muốn sử dụng nó.

Ví dụ trong thư viện:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>optional-integration</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
```

Optional phù hợp với tính năng tích hợp không phải consumer nào cũng cần. Không nên dùng optional để che một dependency runtime bắt buộc; nếu implementation luôn cần thư viện đó, consumer có thể thiếu class khi chạy.

## 16. Đọc dependency graph trong Gradle

Lệnh cơ bản:

```bash
./gradlew dependencies
```

Lệnh này hiển thị dependency report cho các configuration của project hiện tại.

Trong multi-project build, có thể chỉ định project:

```bash
./gradlew :app:dependencies
```

Chỉ định configuration:

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Một số configuration hữu ích:

- compileClasspath.
- runtimeClasspath.
- testCompileClasspath.
- testRuntimeClasspath.
- annotationProcessor.

Tên configuration có thể khác nếu dự án dùng plugin hoặc source set tùy chỉnh.

Ví dụ output minh họa:

```text
compileClasspath
+--- org.apache.commons:commons-lang3:3.17.0
+--- com.fasterxml.jackson.core:jackson-databind:2.17.2
|    +--- com.fasterxml.jackson.core:jackson-annotations:2.17.2
|    \--- com.fasterxml.jackson.core:jackson-core:2.17.2
\--- org.slf4j:slf4j-api:2.0.16
```

Ký hiệu thường thấy:

- +--- biểu thị một nhánh dependency.
- | thể hiện nhánh tiếp tục ở dòng dưới.
- \--- biểu thị nhánh cuối ở cấp đang hiển thị.
- Version có thể kèm thông tin selection hoặc conflict trong output thực tế.

Hãy đọc từ configuration gốc xuống các dependency con. Nếu một artifact xuất hiện nhiều lần, kiểm tra version và lý do chọn.

## 17. Gradle dependencyInsight: tìm vì sao một thư viện xuất hiện

Khi muốn điều tra một module cụ thể:

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Lệnh này tập trung vào module được hỏi và cho biết:

- Các đường dependency yêu cầu module.
- Version được yêu cầu.
- Version được chọn.
- Constraint hoặc rule có ảnh hưởng.
- Lý do Gradle chọn version cuối.

Có thể dùng cho compileClasspath hoặc runtimeClasspath tùy lỗi đang điều tra.

- Compile báo thiếu method: xem compileClasspath và version được chọn.
- Runtime báo NoSuchMethodError: xem runtimeClasspath và kiểm tra version thực tế.
- Một dependency xuất hiện ngoài dự kiến: xem các đường kéo nó vào.

dependencyInsight là công cụ giải thích resolution, không phải công cụ sửa dependency tự động.

## 18. Đọc dependency graph trong Maven

Lệnh cơ bản:

```bash
mvn dependency:tree
```

Có thể xem chi tiết hơn:

```bash
mvn dependency:tree -Dverbose
```

Để lọc theo artifact:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Có thể lọc theo scope hoặc nhóm package tùy tham số của plugin dependency đang dùng.

Ví dụ output:

```text
com.example:shop-app:jar:1.0.0
+- org.apache.commons:commons-lang3:jar:3.17.0:compile
\- com.example:report-client:jar:2.0.0:compile
   \- com.example:common-utils:jar:2.1:compile
```

Output cho biết project gốc, dependency trực tiếp và dependency bắc cầu. Với -Dverbose, Maven có thể hiển thị các dependency bị omitted do conflict hoặc quy tắc mediation.

### Xem effective POM

```bash
mvn help:effective-pom
```

Effective POM cho thấy kết quả sau khi Maven áp dụng parent POM, properties, profiles và dependency/plugin management. Khi version được quản lý ở parent, file POM của module có thể không thể hiện trực tiếp version cuối cùng.

Dependency tree cho biết graph đã resolve; effective POM giúp hiểu cấu hình Maven đã được hợp nhất.

## 19. Phân biệt compile graph và runtime graph

Một ứng dụng có thể dùng các dependency khác nhau khi compile và khi chạy.

```text
Compile classpath
  +-- application API
  +-- annotation/API types
  +-- compile-time library

Runtime classpath
  +-- application runtime library
  +-- JDBC driver
  +-- logging implementation
  +-- runtime transitive dependency
```

Một thư viện có thể không cần trong compile nhưng cần khi chạy. Ngược lại, annotation processor hoặc compile-only API có thể không cần trong runtime.

### Lỗi compile và lỗi runtime khác nhau

- package does not exist: có thể dependency không có trên compile classpath.
- cannot find symbol: class/method không tồn tại trong version được compile hoặc import sai.
- ClassNotFoundException: class không được tìm thấy tại thời điểm classloader yêu cầu.
- NoClassDefFoundError: class cần thiết không thể được nạp khi runtime/linking.
- NoSuchMethodError: code được compile với API khác version đang có lúc chạy.
- NoSuchFieldError: tương tự nhưng liên quan field.

Không nên thêm JAR tùy ý chỉ để hết lỗi. Hãy xác định class thuộc artifact nào và xem graph của classpath liên quan.

## 20. Vì sao thêm thư viện nhưng IDE vẫn báo lỗi?

Một số nguyên nhân:

- Dependency được thêm vào build file nhưng IDE chưa sync/reimport project.
- Đang sửa nhầm build file hoặc module.
- Khai báo sai configuration/scope.
- Repository không truy cập được.
- Tọa độ hoặc version không tồn tại.
- Dependency resolution thất bại.
- IDE dùng JDK hoặc project model khác.
- Source code import class từ artifact khác với artifact đã thêm.

Cách xử lý:

1. Đọc lỗi Gradle/Maven đầy đủ.
2. Chạy compile task hoặc Maven compile để xác nhận build tool.
3. Xem dependency report của đúng module/configuration.
4. Kiểm tra repository và tọa độ.
5. Sync/reimport IDE sau khi build file hợp lệ.

Nếu command-line build pass nhưng IDE lỗi, tập trung vào IDE project sync, JDK và module import. Nếu command-line build cũng fail, điều tra build file hoặc repository trước.

## 21. Thêm dependency vào đúng module trong multi-module build

Giả sử dự án có:

```text
shop/
  settings.gradle
  app/
    build.gradle
  domain/
    build.gradle
  persistence/
    build.gradle
```

Nếu source trong persistence import JDBC driver hoặc ORM API, dependency cần được khai báo ở module persistence. Nếu app trực tiếp import thư viện JSON, dependency nên nằm ở app, trừ khi nó được cung cấp qua API của module khác theo thiết kế rõ ràng.

Root settings:

```groovy
rootProject.name = 'shop'
include 'app', 'domain', 'persistence'
```

Trong persistence/build.gradle:

```groovy
dependencies {
    implementation 'org.postgresql:postgresql:42.7.4'
}
```

Trong app/build.gradle:

```groovy
dependencies {
    implementation project(':domain')
    implementation project(':persistence')
}
```

Không nên thêm tất cả dependency vào root project chỉ vì tiện. Root thường quản lý plugin, version hoặc convention; module chứa code sử dụng thư viện mới là nơi phù hợp để khai báo dependency.

## 22. Project dependency và external dependency

Hai loại dependency thường gặp:

**External dependency** là artifact được tải từ repository:

```groovy
implementation 'org.apache.commons:commons-lang3:3.17.0'
```

**Project dependency** là quan hệ giữa các project trong cùng Gradle build:

```groovy
implementation project(':domain')
```

Trong Maven reactor, module có thể phụ thuộc module khác bằng tọa độ groupId/artifactId/version tương ứng, và reactor sắp xếp thứ tự build theo quan hệ đó.

Khi xem graph, cần phân biệt module nội bộ và artifact bên ngoài. Module nội bộ có thể tạo thêm external dependency của chính nó, khiến graph tổng thể mở rộng.

## 23. Dùng Maven BOM để quản lý một nhóm thư viện

BOM (Bill of Materials) là POM đóng vai trò quản lý version cho một nhóm dependency liên quan. Nó thường giúp tránh việc mỗi module dùng một version không tương thích.

Ví dụ Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

BOM cung cấp version management. Nó không tự thêm tất cả module vào project. Chỉ những dependency được khai báo trong dependencies mới được đưa vào graph.

BOM hữu ích khi nhiều artifact thuộc cùng framework/library family, nhà cung cấp công bố bộ version tương thích hoặc nhiều module cần cùng version. Không nên import nhiều BOM có version xung đột mà không hiểu precedence của dependency management.

## 24. Gradle platform và BOM

Gradle có thể import Maven BOM thông qua platform:

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')

    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
```

Có thể dùng enforcedPlatform khi muốn ép version được quản lý mạnh hơn trong graph, nhưng cần thận trọng vì nó có thể ghi đè lựa chọn version của consumer.

Thông thường, platform là lựa chọn phù hợp để chia sẻ constraints mà vẫn cho phép resolution áp dụng quy tắc chung. Chỉ dùng enforcedPlatform khi policy thực sự yêu cầu các module phải theo version đã chỉ định.

## 25. Gradle constraints và rich versions

Dependency constraint có thể mô tả version mong muốn hoặc giới hạn cho một module:

```groovy
dependencies {
    constraints {
        implementation('com.example:common-utils') {
            version {
                strictly '2.1.0'
            }
            because 'Giữ version tương thích với các consumer đã kiểm thử'
        }
    }
}
```

Các khái niệm rich version có thể gồm:

- require: yêu cầu một version hoặc range.
- strictly: giới hạn nghiêm ngặt, không cho resolution vượt khỏi điều kiện.
- prefer: ưu tiên một version nếu các điều kiện khác cho phép.
- reject: loại bỏ version hoặc range không được chấp nhận.

Cú pháp cụ thể khác giữa Groovy và Kotlin DSL. Cần xem Gradle version và tài liệu tương ứng.

Constraints ảnh hưởng đến resolution khi module xuất hiện trong graph. Chúng không tự thêm module vào graph như một dependency thông thường.

## 26. Kiểm tra dependency chưa được dùng hoặc dùng không đúng

Khai báo quá nhiều dependency có thể làm build nặng, tăng bề mặt bảo mật và gây khó bảo trì. Nhưng không nên xóa dependency chỉ vì một lần tìm kiếm source không thấy import: thư viện có thể được dùng qua reflection, service loader, annotation processor hoặc runtime configuration.

Một số công cụ hỗ trợ phân tích dependency:

- Gradle dependency report và dependencyInsight.
- Maven dependency:tree.
- Maven dependency:analyze.
- IDE dependency analyzer.
- Static analysis hoặc software composition analysis tool.

Maven:

```bash
mvn dependency:analyze
```

Lệnh này giúp tìm dependency được khai báo nhưng không được sử dụng trực tiếp theo phân tích bytecode/source của plugin. Kết quả có thể có false positive/false negative với reflection, generated code hoặc framework convention.

Dùng báo cáo như tín hiệu để review, không xóa dependency tự động mà không kiểm tra runtime behavior.

## 27. Xử lý lỗi version conflict theo quy trình

Khi thấy hai version của cùng module:

1. Xác định module bị conflict.
2. Dùng Gradle dependencyInsight hoặc Maven dependency:tree để tìm tất cả đường yêu cầu.
3. Xác định dependency nào đang kéo version cũ/mới.
4. Kiểm tra release notes và compatibility của các thư viện liên quan.
5. Ưu tiên nâng dependency cha lên version tương thích nếu có.
6. Nếu cần, dùng BOM, constraint hoặc dependencyManagement để căn chỉnh.
7. Chỉ dùng exclusion khi biết dependency bị loại không còn cần thiết hoặc được thay thế.
8. Chạy compile, unit test và integration test liên quan.
9. Kiểm tra runtimeClasspath và artifact đóng gói.
10. Ghi lại lý do lựa chọn version để nhóm hiểu quyết định.

Version cao hơn không luôn tương thích. Major release có thể có breaking changes. Một version thấp hơn có thể là version được framework yêu cầu hoặc đã được kiểm thử. Cần cân bằng compatibility, security và support policy.

## 28. Lỗi thường gặp khi thêm dependency

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Could not find artifact | Tọa độ/version sai hoặc repository không có | Kiểm tra coordinates và repository |
| Could not resolve dependency | Mạng, proxy, auth hoặc metadata conflict | Đọc lỗi resolution, kiểm tra repository |
| Package does not exist | Dependency không có trên compile classpath | Kiểm tra configuration/scope |
| NoClassDefFoundError | Runtime classpath thiếu artifact/class | Xem runtime dependency graph |
| NoSuchMethodError | Version compile và runtime không tương thích | So sánh compile/runtime graph |
| Duplicate classes | Nhiều artifact chứa class trùng | Xem dependency tree và packaging |
| Unsupported class file version | JDK/runtime không hỗ trợ bytecode | Kiểm tra Java version/toolchain |
| Version conflict | Nhiều đường yêu cầu version khác nhau | dependencyInsight hoặc dependency:tree |
| IDE không nhận thư viện | Chưa sync hoặc import sai module | Reimport project, chạy build CLI |
| Build local pass, CI fail | Cache, repository, JDK hoặc secret khác nhau | So sánh môi trường và log |

## 29. Ví dụ thực hành: thêm thư viện JSON bằng Gradle

Giả sử ứng dụng cần Jackson để chuyển đổi JSON.

### Bước 1: xác định artifact

Chọn artifact chính cần dùng và kiểm tra tọa độ từ nguồn chính thức:

```text
com.fasterxml.jackson.core:jackson-databind
```

Chọn version phù hợp với JDK và các module Jackson còn lại.

### Bước 2: khai báo repository và dependency

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}
```

### Bước 3: compile và xem graph

```bash
./gradlew compileJava
./gradlew dependencies --configuration compileClasspath
```

Graph sẽ hiển thị jackson-databind và dependency bắc cầu của nó theo metadata/version đã resolve.

### Bước 4: sử dụng API

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class JsonWriter {
    private final ObjectMapper mapper = new ObjectMapper();

    public String toJson(Object value) throws Exception {
        return mapper.writeValueAsString(value);
    }
}
```

### Bước 5: kiểm tra runtime

Nếu ứng dụng chạy qua main class hoặc integration test, hãy xác nhận runtimeClasspath có đủ artifact. Compile pass chưa chứng minh runtime classpath đầy đủ.

## 30. Ví dụ thực hành: thêm thư viện JSON bằng Maven

Trong pom.xml:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
```

Compile:

```bash
mvn compile
```

Xem graph:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core
```

Maven sẽ hiển thị dependency Jackson trực tiếp và các artifact liên quan được kéo theo. Nếu dự án dùng BOM, version có thể được quản lý ở dependencyManagement thay vì khai báo tại dependency.

## 31. Ví dụ thực hành: xử lý thư viện trùng version

Giả sử graph cho thấy:

```text
application
  +-- report-client:2.0
  |      +-- common-utils:1.4
  |
  +-- storage-client:3.0
         +-- common-utils:2.1
```

Ứng dụng có thể resolve common-utils thành version theo quy tắc của build tool. Trước khi ép version, cần biết report-client có tương thích với 2.1 không.

Quy trình:

1. Dùng dependencyInsight/dependency:tree để xác nhận đường graph.
2. Kiểm tra release note của report-client và common-utils.
3. Tìm version report-client mới có hỗ trợ common-utils 2.1.
4. Nếu có, nâng report-client và kiểm thử.
5. Nếu chưa có, đánh giá constraint/exclusion hoặc giải pháp thay thế.
6. Chạy integration test cho các chức năng dùng cả report và storage.

Không nên chỉ ép common-utils lên 2.1 rồi xem build pass là đủ. Có thể compile được nhưng runtime behavior vẫn không tương thích.

## 32. Dependency graph thay đổi theo configuration

Một module không có duy nhất một graph. Gradle có nhiều configuration; Maven có scope và profile. Cùng một dependency có thể xuất hiện trên compile classpath nhưng không ở runtime, hoặc chỉ xuất hiện khi test.

Ví dụ:

```text
compileClasspath
  +-- commons-lang3
  +-- jackson-databind

runtimeClasspath
  +-- commons-lang3
  +-- jackson-databind
  +-- jdbc-driver
  +-- logging-implementation

testRuntimeClasspath
  +-- compile/runtime dependencies
  +-- junit
  +-- test-engine
```

Khi điều tra, hãy xem đúng configuration:

- Compile error: compileClasspath.
- Application startup error: runtimeClasspath.
- Test compile error: testCompileClasspath.
- Test runtime error: testRuntimeClasspath.
- Annotation processing error: annotationProcessor hoặc testAnnotationProcessor.

Không dùng graph của một configuration để kết luận về configuration khác.

## 33. Dependency resolution và artifact đóng gói

Dependency có thể được dùng khi compile nhưng không được đóng gói vào JAR thông thường của ứng dụng. JAR do Java plugin tạo thường chứa class/resource của project, còn dependency được cung cấp qua runtime classpath.

Nếu cần tạo fat JAR hoặc executable archive, plugin đóng gói có thể gom dependency vào artifact. Hãy kiểm tra cấu hình plugin và nội dung archive.

Một số câu hỏi cần xác nhận:

- Dependency có được đưa vào runtime classpath không?
- Artifact phát hành có chứa dependency hay khai báo dependency metadata?
- Container image có copy đúng runtime dependencies không?
- Service có dùng classpath do launcher cung cấp không?
- Có duplicate resource hoặc service descriptor không?

Compile thành công không đồng nghĩa artifact triển khai chứa đủ runtime dependency.

Có thể liệt kê nội dung JAR:

```bash
jar tf build/libs/shop-app.jar
```

Với Maven:

```bash
jar tf target/shop-app-1.0.0.jar
```

Lệnh này cho biết nội dung archive, nhưng JAR thường không chứa dependency trừ khi plugin tạo fat JAR hoặc executable archive. Hãy kiểm tra loại archive và plugin packaging.

## 34. Dependency verification và nguồn tin cậy

Khi thêm thư viện mới, ngoài coordinates và version, cần xem xét nguồn phát hành.

- Chọn repository được dự án phê duyệt.
- Kiểm tra group/artifact/version.
- Xem release notes và compatibility.
- Xem dependency bắc cầu.
- Kiểm tra advisory bảo mật.
- Dùng checksum/signature verification theo policy.
- Cập nhật lockfile nếu dự án bật dependency locking.
- Review diff graph trước khi merge.

Với Gradle, dependency verification metadata có thể lưu checksum hoặc trusted key. Với Maven, repository checksum policy và quy trình xác minh chữ ký có thể được tổ chức bổ sung.

Không nên tạo checksum metadata rồi tự động tin mọi artifact vừa tải nếu nguồn chưa được xác minh.

## 35. Không dựa vào dependency bắc cầu một cách tình cờ

Giả sử ứng dụng dùng library-A và library-A kéo theo library-B. Source code ứng dụng bắt đầu import trực tiếp class của B.

Dù build hiện tại compile thành công, việc không khai báo B trực tiếp tạo ra dependency ẩn: nếu A đổi metadata hoặc ngừng kéo B theo, ứng dụng có thể không compile được.

Khi source code sử dụng API của một thư viện, nên khai báo thư viện đó trực tiếp theo đúng module và scope. Điều này làm graph phản ánh rõ dependency thực sự của source code.

Với library module, cần phân biệt dependency public API và implementation detail. Nếu kiểu của B xuất hiện trong public signature, consumer có thể cần B trên compile classpath; trong Gradle java-library, cân nhắc api thay vì implementation.

## 36. Dependency graph không chỉ là compile graph

Build tool có thể quản lý nhiều loại dependency khác nhau:

- Compile dependency.
- Runtime dependency.
- Test dependency.
- Annotation processor.
- Plugin/build logic dependency.
- Project dependency.
- Platform/BOM và constraints.
- Toolchain hoặc compiler dependency.
- Dependency phục vụ code generation.

Khi điều tra, cần biết đang xem graph nào. Một plugin không nhất thiết xuất hiện trong runtimeClasspath của ứng dụng. Một annotation processor có thể được resolve trong configuration riêng và chạy ở compile time.

Đừng nhầm plugin dependency với dependency mà ứng dụng import trong source code.

## 37. Quy trình thêm một thư viện mới

Một quy trình thực tế:

1. **Xác định nhu cầu.** Chức năng nào cần thư viện? Có thư viện hiện có trong dự án đã đáp ứng không?
2. **Chọn nhà phát hành và artifact.** Xác minh groupId/artifactId hoặc package coordinates.
3. **Chọn version.** Kiểm tra JDK, framework, release notes, support và security advisory.
4. **Chọn repository.** Dùng nguồn được tổ chức chấp thuận; không thêm repository lạ chỉ để tải được artifact.
5. **Chọn module.** Khai báo ở module có source code trực tiếp sử dụng.
6. **Chọn scope/configuration.** Compile, runtime, test, annotation processor hoặc API exposure.
7. **Khai báo dependency.** Dùng Gradle DSL/version catalog hoặc Maven POM/BOM.
8. **Resolve và compile.** Chạy task phù hợp để xác nhận tọa độ và classpath.
9. **Đọc dependency graph.** Kiểm tra transitive dependency và version được chọn.
10. **Xử lý conflict.** Dùng BOM, constraints, dependencyManagement hoặc exclusion có lý do.
11. **Chạy test.** Xác nhận behavior và runtime.
12. **Review thay đổi.** Xem diff build file, lockfile và dependency graph.
13. **Ghi nhận quyết định.** Nêu lý do thêm dependency và phạm vi sử dụng.

## 38. Những lệnh cần nhớ

| Mục đích | Gradle | Maven |
|---|---|---|
| Build/compile | ./gradlew compileJava | mvn compile |
| Chạy test | ./gradlew test | mvn test |
| Xem dependency graph | ./gradlew dependencies | mvn dependency:tree |
| Xem graph module cụ thể | ./gradlew :app:dependencies | mvn -pl app dependency:tree |
| Xem một dependency | ./gradlew dependencyInsight --dependency name --configuration runtimeClasspath | mvn dependency:tree -Dincludes=group:artifact |
| Xem POM hiệu lực | Không có lệnh tương đương trực tiếp; xem Gradle model/report | mvn help:effective-pom |
| Xem runtime graph | ./gradlew dependencies --configuration runtimeClasspath | mvn dependency:tree -Dscope=runtime |
| Cập nhật lock state | ./gradlew build --write-locks | Quản lý version qua BOM/dependencyManagement và công cụ phù hợp |

Tên project, configuration và plugin có thể khác theo cấu trúc build. Với Gradle multi-project, dùng project path như :app. Với Maven reactor, dùng -pl để chọn module.

## 39. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Thêm một dependency chỉ tải một JAR | Artifact có thể kéo theo nhiều dependency bắc cầu. |
| Dependency xuất hiện trong graph là direct dependency | Nó có thể được kéo qua nhiều đường transitive. |
| Version trong build file luôn là version cuối cùng | Conflict resolution, constraints, BOM và dependency management có thể thay đổi version được chọn. |
| Version Catalog tự thêm thư viện vào classpath | Catalog chỉ cung cấp alias/version; module vẫn khai báo dependency. |
| Maven dependencyManagement tự thêm dependency | Nó quản lý version/scope khi dependency được khai báo, không tự thêm mọi artifact. |
| Gradle implementation luôn đủ cho mọi library API | Nếu dependency type xuất hiện trong public API, consumer compile classpath có thể cần api với java-library plugin. |
| Compile pass chứng minh runtime đủ dependency | RuntimeClasspath và artifact packaging cần được kiểm tra riêng. |
| Exclusion xóa module khỏi mọi graph path | Exclusion gắn với một đường; dependency có thể được kéo vào qua đường khác. |
| Version cao hơn luôn tốt hơn | Có thể có breaking changes hoặc không tương thích với dependency cha. |
| IDE báo lỗi nghĩa là dependency không tồn tại | Có thể IDE chưa sync, sai module hoặc sai JDK. |
| Có thể dựa vào dependency bắc cầu để import API trực tiếp | Nên khai báo direct dependency khi source code trực tiếp sử dụng thư viện đó. |
| dependency:tree và Gradle dependencies chỉ liệt kê file tải về | Chúng biểu diễn quan hệ, scope/configuration và thông tin resolution của graph. |

## 40. Checklist khi thêm thư viện

Trước khi hoàn tất thay đổi, hãy kiểm tra:

- Tọa độ group/artifact/version có đúng không?
- Nguồn phát hành và repository có đáng tin cậy không?
- Version có tương thích JDK/framework không?
- Dependency được khai báo ở đúng module không?
- Scope/configuration có đúng mục đích không?
- Thư viện có cần ở compile, runtime, test hay annotation processing?
- Source code có import API của dependency bắc cầu mà chưa khai báo trực tiếp không?
- Dependency graph kéo theo những artifact nào?
- Có version conflict hoặc constraint nào tác động không?
- BOM/platform có cần quản lý bộ version không?
- Exclusion có thật sự an toàn không?
- Runtime graph có đủ dependency không?
- Artifact đóng gói có chứa/cung cấp đúng thư viện không?
- Test có xác nhận hành vi không?
- Lockfile/verification metadata có cần cập nhật không?
- Review có giải thích lý do thêm dependency và tác động của graph không?

## 41. Nguyên tắc áp dụng trong thực tế

Thêm thư viện không chỉ là thêm một dòng coordinates. Build tool sẽ resolve metadata, mở rộng dependency bắc cầu, áp dụng scope/configuration và chọn version cuối cùng theo quy tắc của nó. Vì vậy, cần hiểu direct dependency, transitive dependency và graph của đúng classpath đang dùng.

Trong Gradle, dùng implementation/api, runtimeOnly, testImplementation, annotationProcessor và Version Catalog theo mục đích. Trong Maven, dùng dependencies, scopes, dependencyManagement, BOM và exclusions phù hợp. Sau khi thêm thư viện, chạy compile/test, xem graph bằng dependencies hoặc dependency:tree, dùng dependencyInsight khi cần tìm lý do chọn version và kiểm tra runtime classpath khi ứng dụng chạy.

Khai báo trực tiếp những thư viện mà source code thực sự sử dụng; quản lý version tập trung khi nhiều module cần cùng bộ thư viện; xử lý conflict dựa trên graph và compatibility thay vì ép version tùy tiện. Một dependency graph rõ ràng giúp build dễ giải thích, dễ nâng cấp và dễ chẩn đoán khi có lỗi compile hoặc runtime.
