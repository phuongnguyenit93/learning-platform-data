# Kiểu artifact, phần mở rộng và classifier

Trong quá trình build và phân phối một dự án Java, ta thường tạo ra nhiều tệp: JAR chứa bytecode, WAR cho ứng dụng web, JAR chứa mã nguồn, JAR chứa tài liệu API, gói kiểm thử, file ZIP phân phối hoặc POM mô tả dependency. Các tệp này đều có thể được gọi là **artifact**, nhưng chúng không có cùng vai trò.

Để build tool và repository phân biệt đúng các sản phẩm, cần hiểu ba khái niệm thường xuất hiện cùng nhau: **kiểu artifact (artifact type)**, **phần mở rộng (extension)** và **classifier**. Chúng có liên quan nhưng không đồng nghĩa:

- Kiểu artifact mô tả loại sản phẩm hoặc cách nó được sử dụng trong hệ thống build/dependency.
- Extension mô tả phần mở rộng của tệp được tạo hoặc phân phối, chẳng hạn `.jar`, `.war`, `.zip`.
- Classifier phân biệt một artifact phụ với artifact chính có cùng tọa độ module và version, chẳng hạn `sources`, `javadoc` hoặc `tests`.

Ví dụ, cùng module `order-service` phiên bản `2.4.0` có thể phát hành:

```text
order-service-2.4.0.jar             # Artifact chính
order-service-2.4.0-sources.jar     # Mã nguồn, classifier=sources
order-service-2.4.0-javadoc.jar    # Tài liệu API, classifier=javadoc
order-service-2.4.0-tests.jar      # Test classes, classifier=tests
order-service-2.4.0.pom            # Metadata Maven
```

Tên file giúp người đọc nhận biết sản phẩm, còn metadata của build tool/repository xác định artifact thuộc module nào, phiên bản nào, có classifier gì và được tiêu thụ theo cách nào.

## 1. Artifact là gì?

Artifact là một sản phẩm được tạo ra hoặc được phân phối bởi quá trình build. Trong dự án Java, artifact thường là một tệp có thể được lưu trữ trong repository, tải xuống hoặc dùng làm đầu vào cho một bước build khác.

Một số artifact thường gặp:

| Artifact | Nội dung/mục đích |
|---|---|
| JAR ứng dụng hoặc thư viện | Bytecode, resource và metadata cần thiết |
| WAR | Web application archive theo cấu trúc WAR |
| Sources JAR | Mã nguồn Java tương ứng với artifact chính |
| Javadoc JAR | Tài liệu API được sinh từ source và Javadoc |
| Test JAR | Class và resource dùng chung cho kiểm thử của module khác |
| ZIP/TAR | Gói phân phối, bộ cài, source bundle hoặc tài liệu |
| POM | Metadata Maven mô tả module và dependency |
| Gradle module metadata | Metadata mô tả component, variant và artifact của module |

Không phải mọi artifact đều là thư viện Java có thể đặt trực tiếp lên compile classpath. Ví dụ, một Javadoc JAR chứa HTML và tài nguyên tài liệu; một ZIP phân phối có thể chứa script, cấu hình và nhiều JAR; một POM chứa metadata chứ không phải bytecode.

Build tool tạo artifact bằng các task đóng gói hoặc plugin tương ứng. Repository lưu artifact cùng metadata để consumer tìm và lựa chọn sản phẩm phù hợp.

## 2. Phân biệt artifact type, extension và classifier

### 2.1. Artifact type

Artifact type mô tả loại sản phẩm hoặc cách hệ thống build/dependency hiểu sản phẩm đó. Ý nghĩa cụ thể phụ thuộc hệ sinh thái và metadata được sử dụng.

Ví dụ:

- `jar`: thư viện hoặc ứng dụng được đóng gói theo định dạng Java Archive.
- `war`: web application archive.
- `test-jar`: trong Maven là một artifact type có quy ước đặc biệt, thường ánh xạ tới JAR có classifier `tests`.
- `pom`: artifact metadata Maven.
- `zip`: gói lưu trữ dạng ZIP.

Không nên giả định rằng type luôn là phần mở rộng file. Một type có thể được ánh xạ sang extension và classifier theo quy tắc của build tool. Ví dụ Maven `test-jar` thường tương ứng file `.jar` có classifier `tests`, chứ không tạo file `.test-jar`.

Trong Gradle hiện đại, việc chọn biến thể thư viện còn dựa vào variant attributes như usage, category, library elements, bundling và target JVM version. Vì vậy, không thể quy toàn bộ khái niệm type trong hệ sinh thái Maven thành một thuộc tính đơn giản trong Gradle.

### 2.2. Extension

Extension là phần mở rộng của tên tệp, thường đứng sau dấu chấm cuối cùng:

```text
application.jar
application.war
distribution.zip
documentation.tar
```

Extension thường gợi ý định dạng đóng gói hoặc nội dung tệp. Nó không tự mô tả đầy đủ cách sử dụng artifact. Hai tệp cùng extension `.jar` có thể có mục đích rất khác nhau: JAR thư viện chính, sources JAR, Javadoc JAR, test JAR hoặc executable/fat JAR.

### 2.3. Classifier

Classifier là nhãn bổ sung để phân biệt một artifact phụ với artifact chính của cùng module và version. Các classifier quen thuộc:

| Classifier | Ý nghĩa thường gặp |
|---|---|
| `sources` | Mã nguồn của module |
| `javadoc` | Tài liệu API |
| `tests` | Class/resource phục vụ kiểm thử |
| `test-fixtures` | Các fixture dùng chung cho test, tùy plugin và quy ước dự án |
| `all` | Một biến thể đóng gói tổng hợp, ý nghĩa phụ thuộc dự án |
| `linux-x86_64` | Artifact dành cho nền tảng cụ thể, nếu dự án quy ước như vậy |

Classifier không phải extension và cũng không phải một thư mục. Nó là một phần của định danh artifact trong metadata và thường xuất hiện trong tên file.

Ví dụ:

```text
order-service-2.4.0-sources.jar
                  ^^^^^^^
                  classifier
```

Tệp có extension `jar` và classifier `sources`. Nếu classifier rỗng, artifact thường là sản phẩm chính của module.

## 3. Cấu trúc tọa độ artifact trong Maven

Maven nhận diện một module bằng các tọa độ cơ bản:

```text
groupId : artifactId : version
```

Ví dụ:

```text
com.example : order-service : 2.4.0
```

Khi module có nhiều artifact, classifier và extension giúp phân biệt các tệp đi kèm. Có thể hình dung định danh đầy đủ của một artifact là:

```text
groupId : artifactId : version : classifier @ extension
```

Đây là cách viết khái niệm để thấy các thành phần. Không phải mọi công cụ đều dùng đúng cú pháp này ở mọi vị trí.

Với module ví dụ:

| groupId | artifactId | version | classifier | extension | Tên file thường gặp |
|---|---|---|---|---|---|
| `com.example` | `order-service` | `2.4.0` | *(rỗng)* | `jar` | `order-service-2.4.0.jar` |
| `com.example` | `order-service` | `2.4.0` | `sources` | `jar` | `order-service-2.4.0-sources.jar` |
| `com.example` | `order-service` | `2.4.0` | `javadoc` | `jar` | `order-service-2.4.0-javadoc.jar` |
| `com.example` | `order-service` | `2.4.0` | `tests` | `jar` | `order-service-2.4.0-tests.jar` |
| `com.example` | `order-service` | `2.4.0` | *(rỗng)* | `pom` | `order-service-2.4.0.pom` |

Các artifact này thuộc cùng module/version, nhưng không phải cùng một tệp. Repository có thể lưu chúng cạnh nhau trong thư mục theo group, artifact và version.

### 3.1. Tên file Maven thông thường

Tên file artifact Maven thường được tạo theo cấu trúc:

```text
<artifactId>-<version>[-<classifier>].<extension>
```

Ví dụ:

```text
order-service-2.4.0.jar
order-service-2.4.0-sources.jar
order-service-2.4.0-javadoc.jar
order-service-2.4.0-tests.jar
```

Classifier được thêm vào khi có giá trị. Extension xác định phần mở rộng của tệp. Tên file thực tế có thể chịu ảnh hưởng từ cấu hình plugin hoặc cách đóng gói của dự án.

### 3.2. Repository path

Với Maven repository layout thông thường, `groupId` được chuyển thành các thư mục con bằng dấu `/`, tiếp theo là `artifactId` và `version`:

```text
com/example/order-service/2.4.0/
├── order-service-2.4.0.jar
├── order-service-2.4.0.pom
├── order-service-2.4.0-sources.jar
├── order-service-2.4.0-javadoc.jar
└── order-service-2.4.0-tests.jar
```

Đây là cách tổ chức phổ biến của Maven-compatible repository. Metadata đi kèm giúp công cụ xác định các artifact và dependency của module.

## 4. Phân biệt Maven packaging, type, classifier và extension

Trong Maven, một số thuật ngữ gần nhau nhưng có vai trò khác nhau.

| Thuật ngữ | Vị trí/ý nghĩa | Ví dụ |
|---|---|---|
| `packaging` | Khai báo loại sản phẩm chính của project trong POM, ảnh hưởng lifecycle/plugin mapping | `jar`, `war`, `pom` |
| `type` | Loại dependency được yêu cầu trong khai báo dependency; Maven dùng artifact handler để ánh xạ type sang extension/classifier mặc định | `jar`, `test-jar` |
| `classifier` | Phân biệt artifact phụ thuộc cùng tọa độ module | `tests`, `sources` |
| `extension` | Phần mở rộng thực tế của file artifact | `jar`, `pom`, `zip` |

Ví dụ project có:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
  <packaging>jar</packaging>
</project>
```

`packaging` là `jar`, nên sản phẩm chính thông thường là `order-service-2.4.0.jar`. Điều này không có nghĩa project không thể phát hành thêm sources JAR, Javadoc JAR hoặc test JAR.

### 4.1. `test-jar` là một ví dụ dễ gây nhầm

Maven có artifact type `test-jar`. Theo artifact handler mặc định, type này thường được ánh xạ tới extension `jar` và classifier `tests`.

Vì vậy, một dependency khai báo:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
  <type>test-jar</type>
  <scope>test</scope>
</dependency>
```

thường yêu cầu artifact tương ứng với:

```text
order-service-2.4.0-tests.jar
```

Không phải file có phần mở rộng `.test-jar`. `test-jar` là type trong mô hình Maven, còn tệp được tải về là JAR với classifier `tests`.

Khi dự án dùng type tùy chỉnh, extension/classifier mapping có thể phụ thuộc artifact handler hoặc plugin. Hãy kiểm tra tài liệu plugin và repository metadata thay vì suy luận mọi type đều ánh xạ giống `test-jar`.

## 5. Tạo các artifact phụ trong Maven

Maven có thể gắn nhiều artifact vào cùng một project. Các plugin chuyên dụng thường tạo sources JAR, Javadoc JAR hoặc test JAR.

Ví dụ cấu hình plugin để tạo JAR chứa test classes:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
      <executions>
        <execution>
          <goals>
            <goal>test-jar</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Plugin tạo artifact kiểm thử gắn với classifier `tests` theo quy ước của goal `test-jar`. Version ở ví dụ chỉ minh họa cấu hình plugin; dự án nên chọn version phù hợp với baseline và quy định dependency của mình.

Sau khi build, artifact phụ có thể được cài vào local repository hoặc publish cùng module chính. Một module khác có thể yêu cầu nó trong scope test.

### 5.1. Khai báo dependency tới test JAR

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
  <type>test-jar</type>
  <scope>test</scope>
</dependency>
```

Dependency này yêu cầu artifact test JAR của `order-service`. Nó hữu ích khi module khác cần tái sử dụng test utility hoặc test fixture được chia sẻ.

Không nên dùng test JAR như một cách chia sẻ business code chính. Nếu class được sử dụng bởi ứng dụng production, hãy đặt nó trong source set chính hoặc một module thư viện riêng. Test JAR thường chỉ nên chứa thành phần phục vụ kiểm thử.

### 5.2. Sources và Javadoc artifact

Sources JAR và Javadoc JAR thường được tạo bởi plugin tương ứng. Chúng giúp IDE hiển thị source, hỗ trợ debug và cung cấp tài liệu cho người tiêu thụ thư viện.

Hai artifact này thường được phát hành cùng GAV nhưng có classifier:

```text
order-service-2.4.0-sources.jar
order-service-2.4.0-javadoc.jar
```

Chúng không thay thế JAR chính. Khi consumer khai báo dependency thông thường, build tool sẽ chọn artifact chính theo metadata; IDE hoặc công cụ tài liệu có thể tải artifact classifier tương ứng để hiển thị nội dung bổ sung.

## 6. Artifact và classifier trong Gradle

Gradle cũng tạo các archive như JAR, WAR và ZIP. Các task archive có các property để cấu hình tên sản phẩm.

Với `AbstractArchiveTask`, các property quan trọng gồm:

| Property | Ý nghĩa |
|---|---|
| `archiveBaseName` | Phần tên cơ sở |
| `archiveAppendix` | Phần phụ được thêm vào tên, nếu có |
| `archiveVersion` | Version của archive |
| `archiveClassifier` | Classifier của archive |
| `archiveExtension` | Extension của archive |
| `archiveFileName` | Tên file hoàn chỉnh, có thể cấu hình trực tiếp |
| `archiveFile` | Provider trỏ tới file archive đầu ra |
| `destinationDirectory` | Thư mục chứa archive |

Tên archive thông thường được tạo từ các thành phần base name, appendix, version, classifier và extension. Với cấu hình phổ biến không có appendix:

```text
<baseName>-<version>[-<classifier>].<extension>
```

Ví dụ:

```groovy
tasks.named('jar') {
    archiveBaseName = 'order-service'
    archiveVersion = '2.4.0'
    archiveClassifier = ''
    archiveExtension = 'jar'
}
```

Kết quả tên file là `order-service-2.4.0.jar`. Nếu đặt classifier:

```groovy
tasks.named('jar') {
    archiveClassifier = 'internal'
}
```

tên file sẽ có dạng `order-service-2.4.0-internal.jar` theo các giá trị còn lại.

Trong build script hiện đại, nên dùng property API và `set(...)` khi cần truyền Provider:

```groovy
tasks.named('jar') {
    archiveClassifier.set('internal')
}
```

## 7. Tạo JAR phụ trong Gradle

Giả sử project dùng Java plugin và muốn tạo thêm JAR chứa output của source set `test` để module khác tái sử dụng test utilities.

```groovy
plugins {
    id 'java'
}

tasks.register('testJar', Jar) {
    archiveClassifier.set('tests')
    from(sourceSets.test.output)
}
```

Task `testJar` tạo file có tên tương tự:

```text
<project-name>-<version>-tests.jar
```

`from(sourceSets.test.output)` lấy class và resource của source set kiểm thử. Nó không tự đưa toàn bộ dependency của test runtime vào JAR. Nếu cần một gói chứa dependency, đó là một dạng distribution/fat JAR khác và phải được thiết kế riêng.

Nếu task được yêu cầu trực tiếp:

```bash
./gradlew testJar
```

Gradle sẽ chạy các task cần thiết để tạo output của `sourceSets.test` theo dependency graph. Nếu muốn artifact này được tạo cùng `assemble`, có thể gắn task vào lifecycle:

```groovy
tasks.named('assemble') {
    dependsOn(tasks.named('testJar'))
}
```

Chỉ nên gắn vào `assemble` nếu test JAR là artifact cần được tạo trong quy trình assembly thường xuyên. Nếu nó chỉ phục vụ một thao tác publish riêng, có thể để task được gọi qua publication hoặc một task chuyên biệt.

### 7.1. Tạo Sources JAR và Javadoc JAR

Java plugin cung cấp các tùy chọn để tạo sources và Javadoc archive:

```groovy
plugins {
    id 'java'
}

java {
    withSourcesJar()
    withJavadocJar()
}
```

Các task tương ứng tạo artifact có classifier `sources` và `javadoc` theo quy ước Java component của Gradle. Ví dụ tên file:

```text
order-service-2.4.0-sources.jar
order-service-2.4.0-javadoc.jar
```

Các artifact này thường được nối vào Java component để có thể publish cùng artifact chính khi dùng `maven-publish`.

## 8. Extension của các loại archive trong Gradle

Gradle có task type khác nhau cho các định dạng đóng gói:

| Task type | Extension thường dùng | Mục đích |
|---|---|---|
| `Jar` | `jar` | Đóng gói class, resource và metadata dạng JAR |
| `War` | `war` | Đóng gói web application dạng WAR |
| `Zip` | `zip` | Đóng gói thư mục/tệp dạng ZIP |
| `Tar` | `tar` | Đóng gói dạng TAR |
| `Tar` với compression | `tar.gz`, `tgz` hoặc cấu hình tương ứng | Gói TAR có nén |

Ví dụ tạo ZIP phân phối:

```groovy
tasks.register('distributionZip', Zip) {
    archiveBaseName.set('order-service-distribution')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('')
    from('scripts')
    from('config')
}
```

Task tạo archive ZIP từ nội dung hai thư mục `scripts` và `config`. Extension được xác định bởi task type `Zip`; không nên đổi extension thành `jar` nếu nội dung không phải JAR.

Nếu dự án áp dụng War plugin, task `war` tạo WAR archive. WAR vẫn là một archive có cấu trúc riêng theo quy ước web application; không chỉ là JAR đổi tên phần mở rộng.

## 9. Publish artifact bằng Gradle Maven Publish

Khi dùng `maven-publish`, Gradle tạo publication để đưa component và artifact lên Maven-compatible repository.

Ví dụ:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '2.4.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` publish Java component và các artifact phụ đã được component cung cấp, bao gồm sources/Javadoc nếu được cấu hình theo cách trên. Gradle có thể sinh POM và Gradle module metadata tùy cấu hình publication/repository.

### 9.1. Thêm artifact tùy chỉnh vào publication

Có thể thêm một archive khác vào publication:

```groovy
tasks.register('testJar', Jar) {
    archiveClassifier.set('tests')
    from(sourceSets.test.output)
}

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifact(tasks.named('testJar'))
        }
    }
}
```

Task archive đã đặt classifier `tests`; publication đưa artifact đó vào cùng module/version. Khi publish thành công, repository có thể chứa JAR chính và JAR classifier `tests`.

Nếu thêm artifact bằng publication DSL, cần bảo đảm task tạo archive được nối vào publication. `artifact(TaskProvider)` là cách tham chiếu task output để Gradle biết artifact đến từ task nào.

### 9.2. Artifact và metadata publication

Một publication Maven-compatible thường có POM mô tả GAV, packaging, dependency và metadata khác. Gradle có thể bổ sung Gradle Module Metadata (`.module`) để mô tả variants và attributes phong phú hơn POM truyền thống.

Không nên cho rằng một file JAR đơn lẻ đã đủ mô tả module. Consumer cần metadata để biết dependency, version và cách lựa chọn artifact. Khi publish, cần bảo đảm artifact và metadata tương ứng được đưa lên repository nhất quán.

## 10. Lựa chọn artifact classifier khi khai báo dependency

### 10.1. Trong Maven

Dependency thông thường:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
</dependency>
```

Khai báo này yêu cầu artifact chính theo metadata, thường là JAR trong project có packaging `jar`.

Để yêu cầu artifact có classifier cụ thể, có thể khai báo:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
  <classifier>tests</classifier>
  <type>jar</type>
  <scope>test</scope>
</dependency>
```

Khai báo trên chọn JAR có classifier `tests`. Với type `test-jar`, Maven có quy tắc ánh xạ mặc định như đã trình bày ở phần trước; nên dùng một kiểu khai báo nhất quán để tránh yêu cầu nhầm artifact.

### 10.2. Trong Gradle

Gradle có thể khai báo dependency artifact với classifier bằng notation hoặc artifact configuration. Ví dụ dạng map notation:

```groovy
dependencies {
    testImplementation(
        group: 'com.example',
        name: 'order-service',
        version: '2.4.0',
        classifier: 'tests'
    )
}
```

Đây là dependency tới artifact JAR có classifier `tests`. Cấu hình scope `testImplementation` phù hợp khi artifact chỉ phục vụ kiểm thử.

Khi cần chỉ định rõ artifact file name, extension hoặc type khác, Gradle hỗ trợ cấu hình artifact của dependency theo API tương ứng. Cú pháp chi tiết phụ thuộc dạng dependency và phiên bản Gradle; nên ưu tiên khai báo module dependency và variant metadata chuẩn thay vì hard-code đường dẫn repository.

### 10.3. Classifier không thay thế variant selection

Gradle có cơ chế variant-aware dependency management. Một module có thể xuất bản nhiều variants, ví dụ API và runtime, hoặc các biến thể dành cho những target JVM khác nhau. Consumer yêu cầu một usage/attribute phù hợp; Gradle chọn variant dựa trên attributes và metadata.

Classifier là một nhãn artifact gắn với module/version, thường dùng cho artifact phụ hoặc quy ước tương thích Maven. Nó không thay thế toàn bộ hệ thống variant. Ví dụ, không nên tạo classifier `java8`, `java17`, `api`, `runtime` một cách tùy tiện nếu mô hình Gradle có thể biểu diễn những khác biệt đó bằng attributes và variants.

## 11. File dependency và module artifact

Một dự án có thể tham chiếu trực tiếp một file JAR cục bộ:

```groovy
dependencies {
    implementation(files('libs/vendor-library.jar'))
}
```

Đây là file dependency. Gradle biết đường dẫn file nhưng không có đầy đủ module metadata như GAV, POM hoặc Gradle module metadata. Vì vậy, dependency transitives của file JAR không tự được phân giải từ metadata module.

Ngược lại, module dependency:

```groovy
dependencies {
    implementation('com.example:order-service:2.4.0')
}
```

được phân giải từ repository và metadata tương ứng. Metadata cho phép build tool biết module, version, dependency và artifact/variant được chọn.

Nếu cần classifier hoặc artifact phụ, nên publish và tiêu thụ nó theo metadata của module. Đưa một JAR vào `libs/` chỉ bằng file path không tự mang theo quy tắc classifier hoặc dependency graph của module gốc.

## 12. Phân biệt classifier với version và appendix

Classifier không phải version. Ví dụ:

```text
order-service-2.4.0-sources.jar
               ^^^^^ ^^^^^^^
               |     classifier
               version
```

`2.4.0` là version của module. `sources` là classifier của artifact. Nếu version đổi thành `2.5.0`, tất cả artifact của module có thể được publish với version mới:

```text
order-service-2.5.0.jar
order-service-2.5.0-sources.jar
order-service-2.5.0-javadoc.jar
```

Classifier cũng không nhất thiết là appendix. Trong Gradle, `archiveAppendix` và `archiveClassifier` là hai property khác nhau. Cả hai có thể ảnh hưởng tên file, nhưng classifier có ý nghĩa trong nhận diện artifact được publish.

Không nên nhồi tên môi trường, ngày build hoặc commit hash vào classifier nếu đó thực chất là versioning scheme. Hãy chọn quy ước version và classifier rõ ràng để repository có thể quản lý artifact một cách nhất quán.

## 13. Quy tắc đặt classifier

Classifier thường là chuỗi ngắn, dễ đọc, ổn định và có ý nghĩa với consumer. Ví dụ:

```text
sources
javadoc
tests
linux-x86_64
windows-x86_64
```

Khi đặt classifier, nên xác định:

- Artifact đó chứa nội dung gì?
- Consumer nào cần nó?
- Nó có thể được tạo lại từ artifact chính hoặc source không?
- Có cần phân biệt theo nền tảng, kiến trúc, mục đích hoặc tập hợp nội dung không?
- Classifier có ổn định giữa các phiên bản hay chỉ là tên tạm thời?

Tránh dùng nhiều cách viết cho cùng một ý nghĩa, chẳng hạn `source`, `sources`, `src` trong các module khác nhau mà không có lý do. Quy ước thống nhất giúp consumer biết chính xác classifier cần dùng.

## 14. Artifact naming và tính tái lập

Tên artifact là một phần của hợp đồng phân phối. Nếu build cùng source/version nhưng tạo tên file không ổn định, pipeline publish và consumer có thể gặp khó khăn.

Ví dụ, không nên tùy tiện dùng thời điểm hiện tại làm classifier:

```text
order-service-2.4.0-20261113-101500.jar
```

trừ khi đây là quy ước versioning có chủ đích. Với artifact release thông thường, version và classifier nên ổn định; build metadata thay đổi theo từng lần build nên được quản lý riêng nếu cần truy vết.

Gradle archive task hỗ trợ khai báo các thành phần tên file, và có thể đặt tên hoàn chỉnh qua `archiveFileName`. Khi ghi đè `archiveFileName`, cần hiểu rằng nó có thể làm tên file không còn phản ánh version/classifier theo quy ước. Nếu publication metadata vẫn mô tả một classifier nhưng file name bị đặt tùy ý, cần xác nhận publication vẫn trỏ đúng artifact.

Với Maven, plugin có thể cho phép cấu hình final name hoặc classifier. Không nên thay đổi tên output bằng cách đổi file sau khi plugin đã đăng ký artifact nếu metadata publication vẫn tham chiếu tên cũ.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Consumer không tìm thấy `sources.jar` | Sources artifact chưa được tạo hoặc chưa publish | Kiểm tra task/plugin tạo sources và repository contents |
| Dependency tải JAR chính thay vì test JAR | Thiếu classifier hoặc khai báo sai type | Kiểm tra dependency metadata và classifier `tests` |
| Tên file có `.jar` nhưng consumer không dùng được | Nội dung archive không đúng vai trò mong đợi hoặc thiếu metadata | Kiểm tra archive entries, publication và dependency graph |
| Maven tạo file `-tests.jar` nhưng POM dependency không chọn nó | Consumer chưa khai báo test-jar/classifier đúng cách | Kiểm tra `<type>test-jar</type>` hoặc `<classifier>tests</classifier>` |
| Gradle không publish artifact tùy chỉnh | Task archive chưa được thêm vào publication | Kiểm tra `artifact(tasks.named(...))` và publication task |
| Artifact phụ bị ghi đè artifact chính | Classifier rỗng hoặc tên output trùng nhau | Đặt classifier riêng và kiểm tra archive file name |
| Hai artifact khác nội dung nhưng cùng tọa độ | Version/classifier/extension không phân biệt chúng | Thiết kế lại tọa độ và classifier ổn định |
| Dependency file cục bộ thiếu transitive dependencies | File dependency không có module metadata | Dùng module publication hoặc khai báo dependency rõ ràng |
| Nhầm `test-jar` là extension | Nhầm artifact type Maven với phần mở rộng file | Hiểu mapping type `test-jar` sang JAR + classifier `tests` |
| Artifact production bị chọn nhầm variant | Consumer và publication có attributes/metadata không phù hợp | Kiểm tra Gradle variants, attributes và module metadata |

## 16. Quy trình lần theo một artifact

Khi cần biết một file được tạo và tiêu thụ như thế nào, hãy lần theo các bước:

1. **Xác định module và version:** tìm `group`, `artifactId`/module name và version.
2. **Xác định artifact chính hay phụ:** kiểm tra classifier có rỗng hay không.
3. **Xác định định dạng file:** kiểm tra extension và nội dung archive thực tế.
4. **Tìm task tạo artifact:** ví dụ `jar`, `sourcesJar`, `javadocJar`, `testJar`, `war` hoặc task ZIP tùy chỉnh.
5. **Kiểm tra publication:** xác nhận artifact đã được thêm vào Maven publication hoặc repository metadata.
6. **Kiểm tra consumer:** xem dependency khai báo classifier/type hay yêu cầu variant nào.
7. **Kiểm tra metadata repository:** xác nhận artifact file và POM/module metadata tồn tại cùng nhau.

Một file có tên đúng chưa chắc đã được publish hoặc consumer lựa chọn. Cần kiểm tra cả task tạo file, publication và metadata.

## 17. Tổng kết

Artifact là sản phẩm được tạo hoặc phân phối bởi build. Type mô tả loại sản phẩm trong mô hình build/dependency; extension mô tả định dạng tệp; classifier phân biệt artifact phụ với artifact chính của cùng module và version. Một module có thể phát hành nhiều artifact như JAR chính, sources JAR, Javadoc JAR và test JAR.

Trong Maven, tọa độ module gồm groupId, artifactId và version; classifier và extension giúp phân biệt các artifact. `packaging` của project, `type` của dependency, classifier và extension có quy tắc riêng. Đặc biệt, `test-jar` thường ánh xạ tới JAR có classifier `tests`.

Trong Gradle, archive task cung cấp các property như `archiveBaseName`, `archiveVersion`, `archiveClassifier`, `archiveExtension` và `archiveFile`. Java component có thể tạo sources/Javadoc JAR, còn publication có thể thêm artifact tùy chỉnh. Gradle variants và attributes cung cấp một cơ chế lựa chọn phong phú hơn classifier đơn thuần.

Khi thiết kế artifact, hãy chọn extension đúng định dạng, classifier có ý nghĩa ổn định, khai báo publication và metadata nhất quán, rồi xác nhận consumer chọn đúng sản phẩm. Điều đó giúp build, repository và các module phụ thuộc hiểu chính xác mỗi tệp được tạo ra để làm gì.
