# Maven JAR Plugin và artifact chính của packaging=jar

## 1. Mục tiêu

Khi một dự án Maven khai báo `<packaging>jar</packaging>`, default lifecycle của Maven gắn goal `jar:jar` của **Maven JAR Plugin** vào phase `package`. Sau khi mã nguồn được biên dịch và tài nguyên được xử lý, plugin tạo tệp JAR chứa class và resources của sản phẩm. JAR đó thông thường là **main artifact**: đầu ra chính gắn với tọa độ Maven của dự án, có classifier rỗng.

Ví dụ:

```xml
<groupId>demo</groupId>
<artifactId>jar-artifact-lab</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
```

Khi dùng build directory và tên mặc định, lệnh:

```bash
mvn -B clean package
```

thường tạo:

```text
target/jar-artifact-lab-1.0.0.jar
```

Bài học này giải thích rõ **packaging – lifecycle – plugin – goal – main artifact**, các file bên trong JAR, `META-INF/MANIFEST.MF`, cách làm JAR chạy được, vấn đề runtime dependencies, attached artifacts với classifier, install/deploy và kiểm chứng đầu ra trên CI.

**Điều không nên nhầm:** một JAR được tạo ra không chứng minh unit test đã chạy, không bảo đảm chứa toàn bộ dependency, và không mặc nhiên chạy được bằng `java -jar`. Những yêu cầu đó cần kiểm tra riêng.

## 2. Phân biệt các thành phần

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Packaging | `jar` | Loại artifact chính và lifecycle bindings |
| Build phase | `package` | Mốc trong default lifecycle |
| Plugin | `org.apache.maven.plugins:maven-jar-plugin:3.4.2` | Công cụ đóng gói JAR |
| Goal | `jar:jar` | Tạo một JAR từ project hiện tại |
| GAV | `demo:jar-artifact-lab:1.0.0` | Định danh `groupId:artifactId:version` |
| Main artifact | `jar-artifact-lab-1.0.0.jar` | JAR chính, extension `jar`, classifier rỗng |
| Attached artifact | `jar-artifact-lab-1.0.0-tests.jar` | Artifact bổ sung có classifier, không thay main JAR |
| Manifest | `META-INF/MANIFEST.MF` | Metadata của JAR, có thể có `Main-Class` |
| Main resource | `src/main/resources/messages/greeting.txt` | Dữ liệu vào `target/classes` và JAR |
| Test output | `target/test-classes` và `target/surefire-reports` | Class test/report, không nằm trong main JAR mặc định |

Một artifact Maven được phân giải bằng groupId/artifactId/version cộng type/extension và classifier khi cần. Không được đồng nhất **filename trong `target`** với danh tính artifact trên local/remote repository.

## 3. Default lifecycle với packaging=jar

Trong một project Java `jar` theo cấu hình phổ biến:

```text
process-resources       → resources:resources
                           copy src/main/resources → target/classes
compile                 → compiler:compile
                           compile src/main/java → target/classes
process-test-resources  → resources:testResources
test-compile            → compiler:testCompile
test                    → surefire:test
package                 → jar:jar
                           target/classes → target/*.jar
verify                  → các goal kiểm tra bổ sung nếu có
install                 → cài artifact vào local Maven repository
deploy                  → triển khai artifact lên remote repository
```

Maven còn nhiều phase nằm giữa các dòng; sơ đồ chỉ nêu các goal quan trọng liên quan đến JAR. Các binding cụ thể có thể thay đổi theo packaging, Maven/plugin versions, parent, profiles và executions đã khai báo.

So sánh:

```bash
mvn -B test
mvn -B package
mvn -B verify
mvn -B clean package
mvn -B org.apache.maven.plugins:maven-jar-plugin:3.4.2:jar
```

- `test` chạy tới phase kiểm thử, thông thường **chưa** tạo JAR ở `package`.
- `package` chạy toàn bộ các phase cần thiết trước đó, rồi đóng gói.
- `verify` đi qua `package` và tới các kiểm tra tiếp theo đã được cấu hình.
- `clean package` xóa đầu ra cũ rồi chạy tới `package`, giúp phát hiện lỗi bị che bởi cache tại `target`.
- Lời gọi trực tiếp `jar:jar` **không tự chạy toàn bộ lifecycle trước phase package**. Nếu `target/classes` rỗng hoặc stale, plugin có thể tạo JAR thiếu class/resource.

**Khuyến nghị:** CI nên chạy `mvn -B clean verify` hoặc một lifecycle command tương ứng với yêu cầu kiểm thử và phát hành, không lấy một goal `jar:jar` đơn lẻ thay thế cho compile/test.

## 4. Goal jar:jar đóng gói những gì?

Maven JAR Plugin lấy file từ **classes directory**, mặc định `${project.build.outputDirectory}`, thường là `target/classes`. Compiler Plugin đã tạo các `.class` ở đây; Resources Plugin đã copy tài nguyên ở đây.

Ví dụ trước packaging:

```text
target/classes/
├── demo/jar/JarApp.class
└── messages/greeting.txt
```

JAR đầu ra có thể có:

```text
META-INF/
META-INF/MANIFEST.MF
META-INF/maven/demo/jar-artifact-lab/pom.xml
META-INF/maven/demo/jar-artifact-lab/pom.properties
demo/jar/JarApp.class
messages/greeting.txt
```

Các entry `META-INF/maven` thường được Maven Archiver thêm theo mặc định; archive configuration có thể thay đổi hành vi. File JAR thực tế còn có directory entries và metadata khác nên danh sách trên chỉ minh họa những path quan trọng.

Theo layout chuẩn:

- Class ở `src/main/java` sau compile → `target/classes` → **main JAR**.
- File ở `src/main/resources` sau copy → `target/classes` → **main JAR**.
- Class ở `src/test/java` → `target/test-classes` → **không vào main JAR mặc định**.
- File `src/test/resources` → `target/test-classes` → **không vào main JAR mặc định**.
- Báo cáo `target/surefire-reports` → **không vào main JAR mặc định**.

Điểm quan trọng: JAR Plugin **không biên dịch Java**. Nó đóng gói bytecode/resources đã được các plugin trước đó tạo ra. Nếu test class bị cấu hình sai và lọt vào `target/classes`, JAR Plugin có thể đưa nó vào archive; không có quy tắc chung “mọi class tên Test đều bị loại”.

## 5. Các parameter quan trọng của Maven JAR Plugin

Với plugin version `3.4.2`, những lựa chọn đáng chú ý:

| Parameter | Vai trò |
| --- | --- |
| `classesDirectory` | Thư mục đầu vào, mặc định `${project.build.outputDirectory}` |
| `outputDirectory` | Thư mục ghi JAR, mặc định `${project.build.directory}` |
| `finalName` / `project.build.finalName` | Tên file khi build, mặc định thường `artifactId-version` |
| `classifier` | Khi có classifier, tạo/đính kèm supplemental JAR thay vì main artifact |
| `includes` | Những path được phép đưa vào JAR, tính tương đối với input |
| `excludes` | Những path bị loại khỏi JAR |
| `archive` | Maven Archiver: manifest, custom entries, metadata... |
| `skipIfEmpty` | Bỏ tạo archive nếu không có nội dung, khi bật |
| `forceCreation` | Buộc tạo lại JAR ngay cả khi input được coi là không đổi |
| `outputTimestamp` | Timestamp các archive entries để hỗ trợ reproducible builds |
| `detectMultiReleaseJar` | Nhận biết layout multi-release JAR nếu phù hợp |

Không nhầm `<archive>` với cấu hình của compiler: nó không quyết định Java source có biên dịch thành công hay không. Cần tra tài liệu **đúng plugin version**, vì danh sách/default có thể khác ở các đời plugin.

### 5.1. includes/excludes tính từ input directory

Ví dụ **đoạn cấu hình**, không phải một POM hoàn chỉnh:

```xml
<configuration>
    <excludes>
        <exclude>internal/debug/**</exclude>
        <exclude>config/local-only.properties</exclude>
    </excludes>
</configuration>
```

Các path này thường được hiểu tương đối từ `target/classes`, **không phải** `src/main/java`. Nếu loại nhầm `META-INF/services` hoặc resource framework cần, JAR vẫn có thể tạo được nhưng chạy sai.

Không dùng excludes như biện pháp duy nhất để bảo mật secrets. Nếu một credential đã nằm trong repository hoặc từng được phát hành, việc loại khỏi JAR mới không tự giải quyết rò rỉ.

### 5.2. skipIfEmpty không sửa lỗi “không compile”

`skipIfEmpty` không tự tạo bytecode khi `target/classes` rỗng. Nếu ứng dụng đáng lẽ có nhiều class mà JAR trống, kiểm tra source roots, Compiler Plugin, lifecycle command, includes/excludes và classesDirectory; không chỉ bật/tắt skipIfEmpty.

### 5.3. forceCreation và plugin post-processing

JAR Plugin có cơ chế tránh tạo lại archive nếu output được xem là không đổi. Khi một plugin khác như Shade đã **sửa file JAR sau khi JAR Plugin tạo**, vòng build tiếp có thể gặp vấn đề do file đã được post-process. `forceCreation=true` có thể hữu ích để buộc tái tạo main JAR trước bước xử lý tiếp, nhưng phải xác minh thứ tự các goals và plugin nào sở hữu artifact cuối. Không nên bật nó như cách chữa mọi khác biệt build.

## 6. finalName và Maven coordinates không phải một

Một POM có GAV:

```xml
<groupId>demo</groupId>
<artifactId>jar-artifact-lab</artifactId>
<version>1.0.0</version>
```

thường tạo:

```text
target/jar-artifact-lab-1.0.0.jar
```

Nếu đổi:

```xml
<build>
    <finalName>my-service</finalName>
</build>
```

file local có thể thành:

```text
target/my-service.jar
```

**Nhưng tọa độ project vẫn là `demo:jar-artifact-lab:1.0.0`.** Khi `mvn install`/`mvn deploy`, Maven dùng repository layout dựa trên GAV và artifact type/classifier, chứ không lấy một tên local tùy ý làm tọa độ mới.

Nếu mục tiêu là đổi danh tính mà các dự án khác phụ thuộc, phải đổi `groupId/artifactId/version` theo quy trình release. `finalName` thường phục vụ việc đặt tên file tại `target` hoặc distribution. CI nên xác định đúng output path, không hardcode một filename không còn khớp với POM.

## 7. Main artifact: tại sao classifier phải rỗng?

Maven có khái niệm **main artifact** của mỗi project. Với `packaging=jar`, nó thường là JAR không classifier, được tiêu thụ qua dependency đơn giản:

```xml
<dependency>
    <groupId>demo</groupId>
    <artifactId>jar-artifact-lab</artifactId>
    <version>1.0.0</version>
</dependency>
```

Dependency không nêu classifier sẽ nhắm main artifact phù hợp, không tự chọn `-tests.jar`, `-sources.jar` hoặc một JAR bổ sung chỉ vì filename có cùng gốc.

### 7.1. Không chạy jar:jar không classifier hai lần

Default lifecycle `jar` **đã có** binding tạo main JAR ở `package`. Nếu thêm execution mới:

```xml
<execution>
    <id>extra-jar</id>
    <phase>package</phase>
    <goals>
        <goal>jar</goal>
    </goals>
</execution>
```

mà không có classifier, Maven có thể cố tạo main artifact lần hai và JAR Plugin báo lỗi yêu cầu dùng classifier cho supplemental artifact.

Nếu cần **điều chỉnh main JAR**, cấu hình plugin cho binding mặc định. Nếu cần **một JAR khác**, khai báo classifier ở execution bổ sung.

### 7.2. Ví dụ attached JAR với classifier

Đoạn plugin minh họa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <executions>
        <execution>
            <id>attach-client-jar</id>
            <phase>package</phase>
            <goals>
                <goal>jar</goal>
            </goals>
            <configuration>
                <classifier>client</classifier>
                <includes>
                    <include>demo/client/**</include>
                </includes>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Cấu hình này chỉ có ý nghĩa nếu project **thật sự có** class trong `demo/client` và được kết hợp đúng với phần khai báo plugin hiện tại. Nó không có trong ví dụ runnable ở phần 12.

Khi thành công, project có thể có:

```text
target/jar-artifact-lab-1.0.0.jar
target/jar-artifact-lab-1.0.0-client.jar
```

File đầu là **main**, file sau là **attached**. Consumer muốn dùng attached JAR phải yêu cầu classifier:

```xml
<dependency>
    <groupId>demo</groupId>
    <artifactId>jar-artifact-lab</artifactId>
    <version>1.0.0</version>
    <type>jar</type>
    <classifier>client</classifier>
</dependency>
```

Một attached JAR **không tự thay thế** main artifact, và artifact có classifier không phải lúc nào cũng có cùng public API/dependencies với main JAR.

### 7.3. Test JAR, source JAR và Javadoc JAR

Maven JAR Plugin còn có goal `jar:test-jar` để đóng gói `target/test-classes` thành JAR có classifier thường là `tests`; goal này **không tự chạy trong mọi project packaging=jar**. Source JAR thường do Maven Source Plugin tạo; Javadoc JAR do Maven Javadoc Plugin tạo.

Các file giả định:

```text
jar-artifact-lab-1.0.0.jar
jar-artifact-lab-1.0.0-tests.jar
jar-artifact-lab-1.0.0-sources.jar
jar-artifact-lab-1.0.0-javadoc.jar
```

không mặc nhiên xuất hiện cùng lúc. Cần plugin/execution tương ứng.

Nếu chia sẻ test utilities qua test JAR, nhớ rằng các dependency scope `test` của producer không tự mang theo đầy đủ cho consumer như một thư viện runtime chính. Dự án lớn thường có thể chọn **module test-support riêng** để quản lý API và dependency rõ ràng hơn.

## 8. JAR và manifest: Main-Class có ý nghĩa gì?

JAR là dạng ZIP archive được Java định nghĩa. Đường dẫn tiêu chuẩn cho manifest:

```text
META-INF/MANIFEST.MF
```

Manifest có thể chứa:

```text
Manifest-Version: 1.0
Main-Class: demo.jar.JarApp
Implementation-Title: jar-artifact-lab
Implementation-Version: 1.0.0
```

Đây là **những dòng cần quan sát**, không phải toàn bộ manifest cố định. Một archive có thể có thêm metadata Maven/JDK hoặc attribute khác.

### 8.1. java -jar cần Main-Class

Để dùng:

```bash
java -jar target/jar-artifact-lab-1.0.0.jar
```

Java launcher cần biết lớp entrypoint qua `Main-Class`, và class ấy phải có phương thức `public static void main(String[] args)` phù hợp.

Nếu không cấu hình `Main-Class`, một thư viện JAR vẫn là sản phẩm hợp lệ, nhưng `java -jar` có thể báo:

```text
no main manifest attribute, in target/jar-artifact-lab-1.0.0.jar
```

Đây là dạng lỗi điển hình, không cam kết thông điệp giống mọi hệ điều hành/JDK. **Không phải JAR library nào cũng cần entrypoint.**

### 8.2. Cấu hình Main-Class bằng Maven Archiver

Trong `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <archive>
            <manifest>
                <mainClass>demo.jar.JarApp</mainClass>
            </manifest>
        </archive>
    </configuration>
</plugin>
```

Thẻ `<archive><manifest><mainClass>` được Maven Archiver hỗ trợ và sẽ ghi `Main-Class` vào manifest. Nó **không biên dịch**, **không chạy test** và **không tự tìm đúng main class** nếu tên bạn khai báo sai.

### 8.3. Main-Class không đồng nghĩa chứa dependencies

Maven Archiver còn hỗ trợ:

```xml
<archive>
    <manifest>
        <mainClass>demo.jar.JarApp</mainClass>
        <addClasspath>true</addClasspath>
        <classpathPrefix>lib/</classpathPrefix>
    </manifest>
</archive>
```

Manifest có thể tham chiếu:

```text
Main-Class: demo.jar.JarApp
Class-Path: lib/commons-lang3-3.14.0.jar
```

**Nhưng attribute Class-Path không sao chép JAR dependency** vào file `lib`. Nếu distribution yêu cầu `lib/commons-lang3-3.14.0.jar`, bạn phải tạo và phát hành tệp đó đúng vị trí. Maven JAR Plugin theo mặc định đóng gói class/resource của **chính project**, không biến mọi dependency thành class bên trong main JAR.

Điều này giải thích vì sao `java -jar` có thể báo `NoClassDefFoundError` ngay cả khi manifest có Main-Class hợp lệ.

## 9. Library JAR, thin executable JAR và fat JAR

| Loại | Nội dung chính | Đặc trưng |
| --- | --- | --- |
| Library JAR | Class/resource dùng bởi project khác | Thường không cần Main-Class |
| Thin executable JAR | Class/resource sản phẩm, có Main-Class | Cần external dependencies trên classpath nếu ứng dụng dùng |
| Fat/uber JAR | Class/resource + dependencies được đóng gói/gộp | Cần plugin packaging/transformer chuyên dụng |
| Framework repackaged JAR | Layout/launcher theo framework | Ví dụ Spring Boot Maven Plugin |

Maven JAR Plugin **không tự tạo fat JAR**. Một dự án có thể sử dụng Maven Shade Plugin, Assembly Plugin hoặc Spring Boot Maven Plugin để tạo distribution có dependencies, nhưng cơ chế khác nhau: gộp classes, relocate packages, xử lý `META-INF/services`, thêm boot loader, hoặc attach classifier.

Khi sử dụng plugin post-processing, cần hỏi: **artifact nào là main sau cùng?** Plugin có thể thay main JAR hoặc tạo JAR có classifier. Đừng đoán theo filename lớn nhất trong `target`.

### 9.1. Cú pháp java -cp khi dependencies ở ngoài

Đối với dự án có external runtime JAR và class `demo.app.Main`, ví dụ Linux/macOS:

```bash
java -cp "target/my-app.jar:lib/*" demo.app.Main
```

Trên Windows PowerShell:

```powershell
java -cp "target\my-app.jar;lib\*" demo.app.Main
```

Đây chỉ là **ví dụ cú pháp**, không phải lệnh của dự án Java mẫu ở dưới. Thư mục `lib` phải chứa dependency JAR thật. Trên Windows, classpath separator là `;`, còn trên hệ kiểu POSIX thường là `:`. Với `java -jar`, cách Java launcher xử lý application classpath khác `java -cp ... Main`; không thể sửa thiếu dependency bằng cách ghép `-cp` tùy tiện vào cùng lời gọi `-jar`.

## 10. Cách Maven xác định tên file và metadata trong JAR

Mặc định `project.build.finalName` thường là `${project.artifactId}-${project.version}`. Đặt:

```xml
<build>
    <finalName>my-tool</finalName>
</build>
```

có thể đổi tệp local ở `target` thành `my-tool.jar`, **không** đổi GAV khi install/deploy.

Trong JAR có thể có:

```text
META-INF/maven/demo/jar-artifact-lab/pom.xml
META-INF/maven/demo/jar-artifact-lab/pom.properties
```

Các metadata này hữu ích khi tra xuất nguồn build nhưng không tự chứng minh file an toàn hoặc byte từ repository đáng tin. Một quy trình release nghiêm túc còn cần kiểm tra checksum, provenance và chính sách cấm ghi đè release artifact.

### 10.1. outputTimestamp và tính tái lập

JAR Plugin 3.4.2 hỗ trợ `outputTimestamp` và đọc mặc định từ `${project.build.outputTimestamp}` khi có. Ví dụ:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Điều này giúp ổn định timestamp entry trong archive. Tuy nhiên **không bảo đảm checksum giống nhau tuyệt đối** nếu plugin/JDK, inputs, resource filtering, generated code, manifest, filesystem ordering hoặc các bước post-processing còn thay đổi.

Trong production, chọn timestamp từ một nguồn build/release xác định, không mặc định mọi dự án phải dùng giá trị cố định của bài thực hành.

### 10.2. Multi-release JAR là trường hợp riêng

Một multi-release JAR có thể chứa version-specific classes dưới `META-INF/versions/<N>/` và manifest `Multi-Release: true` để JVM chọn implementation phù hợp. JAR Plugin 3.4.x có khả năng nhận biết layout này, nhưng **không tự sinh các class cho nhiều Java releases** chỉ từ một `maven.compiler.release`. Việc biên dịch riêng từng release, đặt classes vào đúng layout và kiểm thử trên nhiều JDK đòi cấu hình thêm.

Không biến ví dụ JAR Java 17 thông thường ở phần 12 thành multi-release JAR nếu không thực sự cần.

## 11. Pin Maven JAR Plugin version

Một project đơn module có thể khai báo:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
```

Dự án nhiều module có thể đưa version vào parent `<build><pluginManagement>` để các module kế thừa sử dụng cùng bản:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

**Lưu ý:** `pluginManagement` quản lý version/configuration, không tự kích hoạt goal tùy biến. Tuy nhiên ở project `packaging=jar`, default lifecycle đã gắn `jar:jar`, nên version được quản lý có thể áp dụng cho binding này.

Parent POM chỉ được thừa kế khi child khai báo đúng `<parent>`, không phải chỉ vì aggregator liệt kê `<modules>`. Hãy xem effective POM của từng module quan trọng để xác nhận version thực tế.

Theo tài liệu Maven JAR Plugin `3.4.2`, plugin này cần Maven tối thiểu 3.6.3 và JDK tối thiểu 8 **cho chính plugin**. Ví dụ chạy được của bài này sử dụng Java 17 nên vẫn cần JDK 17+ để compile và chạy code.

## 12. Dự án thực hành Java 17 + JUnit Jupiter 5

Ta tạo project `jar-artifact-lab`, có resource tiếng Việt, lớp Java xử lý resource, ba unit test, main JAR cấu hình `Main-Class` và một công cụ Java tùy chọn kiểm tra artifact **sau khi đã package**.

### 12.1. Cấu trúc project

```text
jar-artifact-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/demo/jar/JarApp.java
│   │   └── resources/messages/greeting.txt
│   └── test/java/demo/jar/JarAppTest.java
└── tools/InspectJar.java
```

Tệp trong `tools` không thuộc Maven source root mặc định; nó dùng Java source-file mode để kiểm chứng JAR sau build, không phải class sản phẩm.

### 12.2. POM hoàn chỉnh

Tệp `jar-artifact-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>jar-artifact-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>demo.jar.JarApp</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Implementation-Title>${project.artifactId}</Implementation-Title>
                            <Implementation-Version>${project.version}</Implementation-Version>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích những điểm cốt lõi:

- `packaging=jar` gọi `jar:jar` qua default lifecycle, không cần tự khai báo execution thứ hai cho main artifact.
- `maven.compiler.release=17` yêu cầu compiler nhắm Java release 17; không tự cài JDK.
- `<mainClass>demo.jar.JarApp</mainClass>` thêm `Main-Class` để `java -jar` chạy được.
- `Implementation-Title` và `Implementation-Version` lấy giá trị từ POM cho manifest.
- `project.build.outputTimestamp` hỗ trợ tính tái lập của entry timestamps.
- JUnit chỉ có scope `test`; ứng dụng không cần dependency runtime bên ngoài JDK.
- Surefire chạy unit test và báo fail nếu không tìm thấy test theo cấu hình `failIfNoTests`; phải đọc báo cáo thật để xác minh.

### 12.3. Mã nguồn Java 17

Tệp `src/main/java/demo/jar/JarApp.java`:

```java
package demo.jar;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class JarApp {
    private JarApp() {
    }

    public static String readResource(String absolutePath) throws IOException {
        if (absolutePath == null || !absolutePath.startsWith("/")) {
            throw new IllegalArgumentException(
                    "resource path must start with /");
        }
        try (InputStream input =
                     JarApp.class.getResourceAsStream(absolutePath)) {
            if (input == null) {
                throw new IOException("Missing resource: " + absolutePath);
            }
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static String message() throws IOException {
        return "JAR demo: " + readResource("/messages/greeting.txt");
    }

    public static void main(String[] args) throws IOException {
        System.out.println(message());
    }
}
```

Dùng `Class.getResourceAsStream` để đọc từ **classpath**, không đọc file bằng `Path.of("src/main/resources/...")`. Vì vậy cùng code hoạt động khi resource nằm trong `target/classes` hoặc nằm trong JAR đã đóng gói.

`InputStream.readAllBytes()` và `String.strip()` có trong Java 17. Hàm `strip()` bỏ newline sau file text, giúp stdout không có dòng trống ngoài ý muốn.

### 12.4. File resource UTF-8

Tệp `src/main/resources/messages/greeting.txt`:

```text
Xin chào Maven!
```

Resources Plugin copy đến `target/classes/messages/greeting.txt`. JAR Plugin đóng gói entry tương ứng là `messages/greeting.txt`. Dấu `/` trong `getResourceAsStream("/messages/greeting.txt")` có ý nghĩa tra từ classpath root.

### 12.5. Test Java

Tệp `src/test/java/demo/jar/JarAppTest.java`:

```java
package demo.jar;

import org.junit.jupiter.api.Test;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JarAppTest {
    @Test
    void readsMainResource() throws IOException {
        assertEquals("Xin chào Maven!",
                     JarApp.readResource("/messages/greeting.txt"));
    }

    @Test
    void makesExpectedMessage() throws IOException {
        assertEquals("JAR demo: Xin chào Maven!", JarApp.message());
        assertNotNull(JarApp.class.getResource("/messages/greeting.txt"));
    }

    @Test
    void rejectsMissingResource() {
        IOException error = assertThrows(IOException.class,
                () -> JarApp.readResource("/missing.txt"));
        assertEquals("Missing resource: /missing.txt",
                     error.getMessage());
    }
}
```

Ba test kiểm tra resource có thể được tìm thấy trên classpath, ứng dụng trả chuỗi mong đợi và lỗi khi resource bị thiếu. Vì test chạy trước phase `package`, nó **chưa** chứng minh JAR cuối có các entry đúng; cần kiểm tra artifact ở các bước sau.

### 12.6. Build và stdout

Từ thư mục `jar-artifact-lab`:

```bash
mvn -version
mvn -B clean package
```

Nếu môi trường Maven/JDK/repository phù hợp, Surefire chạy **3 tests, 0 failures, 0 errors, 0 skipped** và JAR Plugin tạo:

```text
target/jar-artifact-lab-1.0.0.jar
```

Báo cáo test ở `target/surefire-reports`. Không chỉ nhìn `BUILD SUCCESS`; cần kiểm tra thật sự số test được thực thi.

Chạy JAR:

```bash
java -jar target/jar-artifact-lab-1.0.0.jar
```

Stdout **chính xác của riêng lệnh Java**:

```text
JAR demo: Xin chào Maven!
```

Với Java 17/terminal UTF-8 phù hợp, tiếng Việt hiển thị đúng. Có thể thay bằng:

```bash
java -cp target/jar-artifact-lab-1.0.0.jar demo.jar.JarApp
```

Cũng in chuỗi trên. `java -jar` lấy main class từ manifest, còn `java -cp ... demo.jar.JarApp` nhận main class trực tiếp từ CLI.

### 12.7. Kiểm tra danh sách entry với jar tf

```bash
jar tf target/jar-artifact-lab-1.0.0.jar
```

Phải tìm thấy:

```text
META-INF/MANIFEST.MF
demo/jar/JarApp.class
messages/greeting.txt
```

Main JAR **không nên có**:

```text
demo/jar/JarAppTest.class
org/junit/jupiter/api/Test.class
```

Vì test class nằm ở `target/test-classes` và JUnit là dependency test, không được tự gộp vào main JAR. Output `jar tf` thực tế còn nhiều entry khác, ví dụ thư mục và Maven metadata; không xem danh sách tối thiểu trên là toàn bộ nội dung chính xác.

### 12.8. Kiểm tra manifest

Trên Linux/macOS:

```bash
mkdir -p jar-inspection
(cd jar-inspection && jar xf ../target/jar-artifact-lab-1.0.0.jar META-INF/MANIFEST.MF)
cat jar-inspection/META-INF/MANIFEST.MF
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path jar-inspection | Out-Null
Push-Location jar-inspection
jar xf ..\target\jar-artifact-lab-1.0.0.jar META-INF/MANIFEST.MF
Pop-Location
Get-Content .\jar-inspection\META-INF\MANIFEST.MF
```

Tìm các thuộc tính được POM yêu cầu:

```text
Main-Class: demo.jar.JarApp
Implementation-Title: jar-artifact-lab
Implementation-Version: 1.0.0
```

Đây chỉ là **những dòng cần xác minh**, không phải toàn bộ manifest. Manifest có quy tắc gấp dòng; một giá trị dài có thể trải trên nhiều dòng vật lý. Với QA tự động nên dùng Java API để parse attribute hơn là chỉ grep text.

### 12.9. Java 17 đọc artifact cuối bằng JarFile

Tệp tùy chọn `tools/InspectJar.java`:

```java
import java.util.jar.Attributes;
import java.util.jar.JarFile;

public final class InspectJar {
    private InspectJar() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("pass one JAR path");
        }
        try (JarFile jar = new JarFile(args[0])) {
            String entrypoint = jar.getManifest()
                    .getMainAttributes()
                    .getValue(Attributes.Name.MAIN_CLASS);
            System.out.println("Main-Class: " + entrypoint);
            System.out.println("App class: "
                    + (jar.getEntry("demo/jar/JarApp.class") != null));
            System.out.println("Greeting: "
                    + (jar.getEntry("messages/greeting.txt") != null));
            System.out.println("Test class: "
                    + (jar.getEntry("demo/jar/JarAppTest.class") != null));
        }
    }
}
```

Java 17 hỗ trợ chạy file source trực tiếp:

```bash
java tools/InspectJar.java target/jar-artifact-lab-1.0.0.jar
```

Với JAR của ví dụ, stdout chính xác:

```text
Main-Class: demo.jar.JarApp
App class: true
Greeting: true
Test class: false
```

Công cụ này không nằm trong `src/main/java` nên không tự có trong JAR. Nếu `tools/InspectJar.java` chưa được tạo, lệnh không chạy. Nó kiểm tra **artifact đã package**, bổ sung cho JUnit test vốn chạy trước packaging.

## 13. Main JAR và Maven install/deploy

Sau khi JAR chính đã được tạo, `install` và `deploy` sử dụng artifact gắn với project cùng POM.

```bash
mvn -B clean install
```

Thông thường cài `demo:jar-artifact-lab:1.0.0` vào local Maven repository:

```text
~/.m2/repository/demo/jar-artifact-lab/1.0.0/
├── jar-artifact-lab-1.0.0.pom
└── jar-artifact-lab-1.0.0.jar
```

Đường dẫn mặc định có thể khác nếu settings thay local repository. Những tệp metadata/phụ khác không được liệt kê.

`mvn deploy` đưa artifact vào remote repository **chỉ khi** project và môi trường có distributionManagement, credentials và quyền publish phù hợp. Bài mẫu không có server publish thật nên không cần thực hành deploy. Không dùng lệnh deploy trên repository production chỉ để thử tạo JAR.

Một consumer dùng dependency mặc định không classifier sẽ tìm main JAR theo GAV và POM metadata của project. Vì vậy không được chỉ tạo attached JAR có classifier rồi kỳ vọng consumer mặc định sẽ chọn nó.

## 14. Multi-module: mỗi module có artifact chính riêng

Ví dụ:

```text
workspace/
├── pom.xml          (packaging=pom)
├── shared/pom.xml   (packaging=jar)
├── service/pom.xml  (packaging=jar)
└── web/pom.xml      (packaging=war)
```

Khi chạy `mvn -B clean package` từ root:

- Root `packaging=pom` có **POM main artifact**, không mặc định gọi JAR Plugin tạo main JAR.
- `shared` có main JAR của riêng module.
- `service` có main JAR của riêng module.
- `web` dùng `war` packaging, thường do Maven WAR Plugin đóng gói.
- Nếu service dùng class của shared, service cần khai báo dependency đúng GAV; chỉ liệt kê modules trong aggregator không tự tạo classpath dependency.

Không trỏ source/resource module này thẳng vào `../module-khac/target/classes` chỉ để “gom JAR”; cách đó phụ thuộc output filesystem và thứ tự build, phá hợp đồng artifact.

Parent POM có thể quản lý Maven JAR Plugin version trong `pluginManagement` nhưng chỉ các child **kế thừa parent đúng qua `<parent>`** mới nhận cấu hình. Với module quan trọng, xem effective POM và artifact thực tế thay vì suy đoán từ aggregator.

## 15. QA JAR trong CI: không chỉ nhìn tên file

Một pipeline tốt cho `packaging=jar` nên:

1. Checkout đúng source commit.
2. Chọn Maven/JDK version được duyệt, ưu tiên Maven Wrapper nếu project quản lý.
3. Chạy `mvn -B clean verify` với test thật, không skip.
4. Đọc test reports và exit code, xác nhận có số test kỳ vọng.
5. Xác định main JAR (classifier rỗng), không nhầm attached JAR.
6. Dùng `jar tf` kiểm tra class/resource có mặt.
7. Đọc `MANIFEST.MF` xác nhận Main-Class khi sản phẩm cần executable.
8. Chạy smoke test bằng **JAR đã package**, không chỉ bằng IDE/classpath của test.
9. Kiểm tra những entry **không được có**, ví dụ test fixture, secret, log.
10. Kiểm tra checksum/provenance và publish sau khi QA pass.

Lệnh QA của ví dụ:

```bash
mvn -B clean verify
jar tf target/jar-artifact-lab-1.0.0.jar
java -jar target/jar-artifact-lab-1.0.0.jar
java tools/InspectJar.java target/jar-artifact-lab-1.0.0.jar
```

**Kiểm tra sự vắng mặt** cũng quan trọng: test classes, `target/surefire-reports` và JUnit library không được tự nằm trong main JAR. Nếu plugin khác repackage artifact, phải chạy lại những kiểm tra trên **artifact cuối được dùng để deploy**.

### 15.1. Checksum

Linux/macOS:

```bash
sha256sum target/jar-artifact-lab-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 target\jar-artifact-lab-1.0.0.jar
```

Không có một checksum cố định trong bài: nó phụ thuộc byte thực của artifact, JDK/plugin/môi trường. Nếu hai clean builds cùng commit cho hash khác, kiểm tra timestamp, generated resources, plugin versions và các input không ổn định.

### 15.2. Kiểm tra JAR binary và tài nguyên không phải Java

Nếu có PNG, PDF, font hoặc file cấu hình nhị phân, không nên bật Maven Resources filtering bừa trên file đó. So SHA-256 input và entry đã trích xuất nếu cần kiểm chứng bảo toàn byte. Một JAR có tên entry đúng nhưng resource bị filtering làm hỏng không được coi là output hợp lệ.

## 16. Sự cố thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Không có `target/*.jar` | Chưa chạy phase `package` hoặc build fail trước đó | Xem command và log; thử `mvn -B clean package` |
| JAR tồn tại nhưng thiếu `.class` | Compiler không chạy, source roots sai, classesDirectory sai | Xem `target/classes` và `jar tf` |
| JAR có class nhưng thiếu resource | Resources Plugin chưa copy hoặc file bị exclude | Xem `target/classes`, includes/excludes |
| `no main manifest attribute` | Thiếu `Main-Class` | Cấu hình `archive.manifest.mainClass` nếu là executable JAR |
| `Could not find or load main class` | Sai mainClass FQCN hoặc class không trong JAR | Đọc manifest, kiểm tra package/path |
| `NoClassDefFoundError` | Thiếu runtime dependency | So dependency graph và runtime classpath |
| Chạy bằng IDE được nhưng `java -jar` fail | IDE cấp classpath khác artifact | Smoke test trên JAR cuối |
| Test class có trong JAR chính | Lẫn test output vào main output hoặc packaging tùy chỉnh | Kiểm tra source roots và archive entries |
| JAR chứa secret | Resource/config đã bị đóng gói ngoài ý muốn | Sửa secret management và xử lý artifact đã phát hành |
| JAR đóng gói twice báo lỗi | Thêm `jar:jar` execution không classifier | Dùng classifier cho supplemental JAR hoặc xóa execution dư |
| Có `-tests.jar` nhưng consumer không tìm thấy | Consumer cần main JAR hoặc thiếu classifier | Kiểm tra GAV, classifier, type |
| Tên file local khác tên artifact trong repo | `finalName` khác artifactId/version | Không nhầm filename với coordinates |
| POM packaging nhưng không có JAR | `packaging=pom` không gắn default JAR goal | Xác nhận đúng loại module |
| JAR bị rỗng | Không có đầu vào hoặc include quá hẹp | Kiểm tra compile, resources, skipIfEmpty |
| JAR có Main-Class vẫn thiếu lib | Manifest không copy dependencies | Dùng external classpath hoặc packaging chuyên dụng |
| JAR đổi checksum dù code không đổi | Timestamp/encoding/JDK/plugin/generator khác | Kiểm tra reproducibility và outputTimestamp |
| Shade/Boot tạo JAR khác | Repackage/attach/replace artifact | Đọc plugin executions và output artifact cuối |
| ServiceLoader lỗi | Service descriptor bị exclude hoặc không merge | Kiểm tra `META-INF/services` trong JAR |
| Install/deploy lỗi sau package pass | Repository/credentials/policy/metadata | Tách lỗi packaging với lỗi publish |
| CI thu sai JAR | Glob chọn attached JAR hoặc JAR cũ | Clean build, kiểm tra classifier và path rõ ràng |

### 16.1. Phân biệt build failure và runtime failure

Nếu `mvn clean package` fail trước `jar:jar` do test, phải sửa test/compile chứ không đổi manifest. Nếu Maven package thành công nhưng `java -jar` fail, cần kiểm tra **Main-Class, bytecode/JDK runtime, resource và dependency**. Nếu chạy tốt nhưng `mvn deploy` fail, kiểm tra **distributionManagement, credentials/repository policy**, không nghi ngờ JAR contents ngay lập tức.

### 16.2. Khi Shade/Boot/Assembly can thiệp

Các plugin này có thể thêm file `original-*.jar`, `*-exec.jar` hoặc thay main artifact; filename cụ thể phụ thuộc cấu hình. Đừng mặc định file lớn nhất dưới `target` là file đúng. Cần xác nhận plugin nào **attach** và plugin nào **replace** artifact trước `install/deploy`, sau đó QA byte thực được phát hành.

## 17. Checklist khi review POM và artifact

- [ ] `packaging=jar` đúng với sản phẩm mong muốn?
- [ ] Maven JAR Plugin version được pin và tương thích Maven/JDK?
- [ ] JAR chính là artifact **classifier rỗng**; attached artifacts có classifier rõ ràng?
- [ ] Không khai báo thêm goal `jar:jar` không classifier làm trùng binding mặc định?
- [ ] `target/classes` chứa các class/resource sản phẩm trước package?
- [ ] Main JAR có class/resource cần thiết, không có test output/secrets?
- [ ] `Main-Class` đúng class có `main` nếu cần chạy bằng `java -jar`?
- [ ] Runtime dependencies được cấp bằng cơ chế phù hợp; không suy ra manifest tự gộp thư viện?
- [ ] `finalName` được phân biệt với `groupId/artifactId/version`?
- [ ] Includes/excludes không loại metadata, service descriptors hoặc resource cần thiết?
- [ ] Multi-module dùng parent/dependency/packaging đúng, không trỏ nhầm giữa `target` của modules?
- [ ] Build sạch chạy test thật, có Surefire reports và exit code phù hợp?
- [ ] Đã smoke test bằng **chính JAR cuối cùng**, không chỉ IDE?
- [ ] Artifact/JAR metadata, checksum, provenance và repository policy đáp ứng yêu cầu phát hành?
- [ ] Sau post-processing, đã kiểm tra artifact cuối và đường install/deploy?

**Kết luận:** `packaging=jar` yêu cầu Maven tạo **main JAR** qua goal `jar:jar` tại phase `package`, đóng gói class/resource từ `target/classes`. Main artifact có classifier rỗng và được nhận dạng bằng GAV/type; các JAR có classifier là **attached artifacts**. JAR Plugin không tự compile, chạy test, gộp dependencies hay bảo đảm `java -jar` có entrypoint. Hiểu đúng lifecycle, manifest, classpath và artifact publishing giúp xây dựng JAR chính xác, có thể kiểm chứng và phân phối đáng tin cậy.

### Tài liệu chính thức

- [Maven JAR Plugin 3.4.2 — Plugin Documentation](https://maven.apache.org/plugins-archives/maven-jar-plugin-3.4.2/plugin-info.html)
- [Apache Maven JAR Plugin — jar:jar reference](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Apache Maven Archiver — Set Up the Classpath / Make the JAR Executable](https://maven.apache.org/shared/maven-archiver/examples/classpath.html)
- [Apache Maven Archiver — Manifest](https://maven.apache.org/shared/maven-archiver/examples/manifest.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Repository Layout](https://maven.apache.org/repository/layout.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
