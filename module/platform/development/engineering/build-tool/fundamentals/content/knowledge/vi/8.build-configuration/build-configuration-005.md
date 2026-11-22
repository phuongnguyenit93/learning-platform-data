# Thứ tự ưu tiên cấu hình và cách truy tìm giá trị có hiệu lực

Một dự án Java có thể nhận cấu hình từ nhiều nơi: tệp trong repository, cấu hình người dùng, biến môi trường, tham số dòng lệnh, system property, plugin và các giá trị mặc định của build tool. Vì vậy, khi một giá trị không giống điều ta mong đợi, chỉ tìm thấy một dòng trong `build.gradle`, `pom.xml` hoặc `gradle.properties` vẫn chưa đủ để kết luận đó là giá trị cuối cùng.

**Giá trị có hiệu lực** là giá trị mà thành phần đang thực thi thực sự sử dụng sau khi đọc, hợp nhất và áp dụng các nguồn cấu hình theo quy tắc của nó. Muốn tìm đúng giá trị này, trước hết phải xác định đang hỏi về loại cấu hình nào, phạm vi nào và thành phần nào tiêu thụ nó.

Bài này trình bày cách tư duy và các công cụ thực tế để truy tìm cấu hình trong Gradle và Maven, đồng thời phân biệt cấu hình của build tool, cấu hình biên dịch Java và cấu hình lúc ứng dụng chạy.

## 1. Vì sao một giá trị có thể được khai báo nhiều lần?

Trong một dự án, cùng một thuộc tính có thể xuất hiện ở nhiều phạm vi vì mỗi phạm vi phục vụ một mục đích:

- Cấu hình cấp dự án xác định quy tắc mà cả nhóm cần chia sẻ.
- Cấu hình người dùng điều chỉnh build theo tài khoản hoặc máy đang làm việc.
- Cấu hình môi trường cung cấp giá trị riêng cho local, test, staging hoặc CI.
- Tham số dòng lệnh cho phép ghi đè có chủ đích trong một lần chạy.
- Plugin và build tool có thể cung cấp giá trị mặc định khi không có cấu hình tường minh.

Ví dụ, một dự án có thể khai báo phiên bản ứng dụng mặc định là `1.0.0`, trong khi CI truyền `2.4.0` cho lần phát hành. Cấu hình dự án vẫn giữ giá trị mặc định; lần build CI sử dụng giá trị được truyền vào nếu build script được viết để đọc property đó.

Một ví dụ khác là repository Maven. POM có thể khai báo repository của dự án, nhưng `settings.xml` ở máy người dùng có thể định nghĩa mirror để chuyển yêu cầu qua máy chủ nội bộ. Nếu chỉ đọc POM, ta sẽ không thấy URL cuối cùng mà Maven thực sự truy cập.

Do đó, không tồn tại một thứ tự ưu tiên duy nhất áp dụng cho mọi giá trị. Thứ tự phụ thuộc vào loại cấu hình và cơ chế mà Gradle, Maven, plugin hoặc ứng dụng dùng để đọc giá trị.

## 2. Phân loại trước khi truy tìm

Trước khi tìm nơi khai báo, hãy xác định giá trị thuộc nhóm nào:

| Nhóm giá trị | Ví dụ | Thành phần đọc giá trị |
|---|---|---|
| Gradle project property | `appVersion`, `-PappVersion=...` | Build script hoặc plugin Gradle |
| JVM system property | `-Dhttp.proxyHost=...`, `System.getProperty(...)` | JVM chạy Gradle/Maven hoặc ứng dụng |
| Environment variable | `JAVA_HOME`, `ORG_GRADLE_PROJECT_appVersion` | Launcher, build tool, plugin hoặc ứng dụng |
| Gradle setting/build configuration | plugin, repository, task, toolchain | Gradle settings và project model |
| Maven user property | `-Drevision=...` khi chạy Maven | Maven model interpolation hoặc plugin nhận property |
| Maven model property | `<properties>` trong `pom.xml` | Maven model và plugin |
| Maven settings | mirror, proxy, server, local repository | Maven khi phân giải repository và môi trường |
| Java compiler option | `--release`, source/target, encoding | `javac` hoặc compiler plugin |
| Application configuration | `application.yml`, system property lúc chạy | Chính ứng dụng hoặc framework runtime |

Một tên giống nhau có thể đại diện cho các loại khác nhau. Ví dụ `version` có thể là Gradle project property, Maven model property, phiên bản artifact, hoặc một trường cấu hình riêng của ứng dụng. Phải tìm nơi tiêu thụ nó trước khi suy luận về thứ tự ưu tiên.

### 2.1. Phân biệt `-P` và `-D`

Đây là điểm dễ gây nhầm lẫn nhất khi chuyển giữa Gradle và Maven.

| Cú pháp | Gradle | Maven |
|---|---|---|
| `-Pname=value` | Đặt Gradle project property tên `name` | Không phải cú pháp chuẩn để đặt Maven user property |
| `-Dname=value` | Đặt JVM system property tên `name` cho tiến trình Gradle theo cơ chế Gradle nhận tham số JVM | Đặt Maven user property tên `name`; đồng thời Maven chạy trong JVM có thể thấy system property tương ứng theo cơ chế launcher |
| `-Dorg.gradle.project.name=value` | Đặt Gradle project property qua system property có tiền tố đặc biệt | Chỉ là system/user property Maven có tên đầy đủ đó, không có ý nghĩa project property của Gradle |

Ví dụ Gradle:

```bash
./gradlew -PappVersion=2.0.0 build
```

Build script có thể đọc `appVersion` như một Gradle project property.

Ví dụ Maven:

```bash
./mvnw -Drevision=2.0.0 verify
```

POM có thể tham chiếu `${revision}` trong model nếu dự án được cấu hình tương ứng.

Không nên sao chép nguyên cú pháp `-P` hoặc `-D` từ công cụ này sang công cụ kia mà không kiểm tra ý nghĩa của nó.

## 3. Thứ tự ưu tiên Gradle project properties

Gradle hỗ trợ project property để truyền giá trị vào build script và plugin. Một project property có thể đến từ đối số dòng lệnh, system property theo quy ước Gradle, environment variable hoặc `gradle.properties` ở nhiều vị trí.

Với project property thông thường, thứ tự ưu tiên phổ biến từ cao xuống thấp là:

1. Đối số dòng lệnh `-Pname=value`.
2. System property có dạng `-Dorg.gradle.project.name=value`.
3. Environment variable có dạng `ORG_GRADLE_PROJECT_name=value`.
4. `gradle.properties` trong Gradle User Home.
5. `gradle.properties` ở root project.
6. `gradle.properties` trong Gradle installation.

Thứ tự trên nói về **Gradle project property**. Nó không phải bảng ưu tiên chung cho mọi JVM system property, mọi tùy chọn daemon hay mọi thiết lập trong settings/build script.

### 3.1. Ví dụ một property được khai báo nhiều lần

Giả sử root project có `gradle.properties`:

```properties
appVersion=1.0.0
```

Gradle User Home (`~/.gradle/gradle.properties`) có:

```properties
appVersion=1.1.0
```

Môi trường CI có:

```text
ORG_GRADLE_PROJECT_appVersion=1.2.0
```

Nếu chạy:

```bash
./gradlew -PappVersion=2.0.0 printVersion
```

và task/build logic đọc project property `appVersion`, giá trị dòng lệnh `2.0.0` có ưu tiên cao nhất trong các nguồn được liệt kê. Nếu bỏ `-PappVersion`, giá trị environment variable `1.2.0` được ưu tiên hơn hai tệp properties. Nếu bỏ cả biến môi trường, giá trị trong Gradle User Home được ưu tiên hơn giá trị ở root project.

Điểm quan trọng là phải xác định build script thực sự đọc project property đó. Nếu nó đọc một system property khác hoặc một biến môi trường trực tiếp, thứ tự vừa nêu không áp dụng.

### 3.2. Đọc project property trong build script

Với Kotlin DSL, có thể đọc property bằng `providers.gradleProperty`:

```kotlin
val appVersion = providers.gradleProperty("appVersion")
    .orElse("0.0.0-local")

version = appVersion.get()
```

Với Groovy DSL:

```groovy
version = providers.gradleProperty('appVersion').getOrElse('0.0.0-local')
```

`providers.gradleProperty` đọc Gradle project property theo cơ chế của Gradle. Nếu không có property, `orElse` hoặc `getOrElse` cung cấp giá trị dự phòng. Vì vậy, khi thấy phiên bản artifact khác dự kiến, hãy kiểm tra cả nguồn property lẫn giá trị mặc định trong build script.

### 3.3. System property không đồng nghĩa với project property

Trong Gradle, lệnh:

```bash
./gradlew -Dapp.environment=staging build
```

đặt system property cho JVM chạy Gradle. Build logic có thể đọc nó bằng `System.getProperty("app.environment")` hoặc chuyển tiếp nó theo cách riêng.

Lệnh:

```bash
./gradlew -Papp.environment=staging build
```

đặt Gradle project property. Build logic đọc nó qua `providers.gradleProperty("app.environment")` hoặc API project property tương ứng.

Hai giá trị có thể cùng tồn tại và thậm chí có nội dung khác nhau. Gradle không tự coi chúng là một biến duy nhất. Muốn biết giá trị nào được sử dụng, hãy tìm đúng API đọc giá trị trong build script hoặc plugin.

### 3.4. Các nguồn cấu hình khác của Gradle

Gradle còn có những loại cấu hình không nên gộp vào bảng project property:

- `org.gradle.jvmargs` điều chỉnh JVM chạy Gradle daemon, thường đặt trong `gradle.properties` hoặc qua cấu hình môi trường phù hợp.
- `systemProp.http.proxyHost` trong `gradle.properties` có thể thiết lập system property cho JVM chạy Gradle.
- `JAVA_HOME` và `PATH` ảnh hưởng đến việc launcher tìm Java để khởi chạy Gradle.
- `org.gradle.java.home` có thể chỉ định Java home cho Gradle daemon.
- Init script trong Gradle User Home có thể cấu hình hoặc thay đổi hành vi của nhiều build.
- `settings.gradle(.kts)` có thể cấu hình plugin management, dependency resolution management và cấu trúc project.

Ví dụ:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.java.home=C:/Java/jdk-21
systemProp.http.proxyHost=proxy.example.com
systemProp.http.proxyPort=8080
```

Đây là các thiết lập có mục đích khác nhau. Không thể kết luận `-P` sẽ ghi đè `org.gradle.jvmargs` hoặc `JAVA_HOME`; mỗi giá trị được đọc bởi một thành phần và có quy tắc riêng.

## 4. Gradle settings, plugin và build logic cũng tham gia tạo cấu hình cuối

Ngay cả khi đã xác định đúng project property, giá trị có hiệu lực của một thiết lập build vẫn có thể đến từ nhiều lớp logic:

```text
Gradle Wrapper / JVM khởi chạy
          |
          v
Init scripts và settings
          |
          v
Plugins và convention plugins
          |
          v
Build script của root/project
          |
          v
Task configuration và command-line options
          |
          v
Task execution
```

Sơ đồ biểu diễn các nơi cần xem, không phải một bảng ưu tiên tuyến tính cho mọi thuộc tính. Một plugin có thể đặt giá trị mặc định, convention plugin có thể cung cấp quy ước chung, build script module có thể cấu hình riêng, và người dùng có thể truyền property mà build logic đọc.

Ví dụ Java toolchain:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain chọn JDK cho các task hỗ trợ Java toolchain. Nó không đồng nghĩa với JVM dùng để khởi chạy Gradle. Nếu Gradle daemon chạy bằng JDK 17 nhưng Java compile task yêu cầu toolchain 21, Gradle có thể tìm một JDK 21 đã cài hoặc provision một JDK nếu cấu hình resolver cho phép.

Khi điều tra, cần hỏi rõ: đang truy tìm JVM chạy Gradle, compiler JDK, hay phiên bản bytecode/API mục tiêu? Ba giá trị này có thể khác nhau.

## 5. Thứ tự và cách hợp nhất cấu hình Maven

Maven có một mô hình cấu hình khác Gradle. Những nguồn thường ảnh hưởng đến model và hành vi build gồm:

- POM của project và POM cha.
- POM của các module trong reactor build.
- Profile trong POM và profile trong settings.
- Global `settings.xml` của Maven installation.
- User `settings.xml` của tài khoản.
- User properties truyền qua `-D` trên dòng lệnh.
- System properties của JVM và environment variables.
- Cấu hình plugin và giá trị mặc định của plugin.

Không nên ghép tất cả thành một thứ tự duy nhất vì Maven xử lý model, settings, profile và tham số plugin theo các quy tắc khác nhau.

### 5.1. Global settings và user settings

Maven có hai tệp settings phổ biến:

- Global settings: `${maven.home}/conf/settings.xml`.
- User settings: `${user.home}/.m2/settings.xml`.

Maven hợp nhất hai nguồn. User settings có thể ghi đè các phần cấu hình tương ứng từ global settings; các phần không bị ghi đè vẫn có thể được kế thừa từ global settings.

Có thể chỉ định tệp khác bằng:

```bash
./mvnw -s ci-settings.xml verify
```

hoặc chỉ định global settings:

```bash
./mvnw -gs company-global-settings.xml verify
```

Nếu build local tải dependency thành công nhưng CI thất bại, hãy kiểm tra hai môi trường có đang dùng cùng settings hay không, có cùng mirror/server id, proxy và credential hay không.

### 5.2. Maven user properties và `-D`

Maven cho phép truyền user property từ dòng lệnh:

```bash
./mvnw -Drevision=2.5.0 verify
```

POM có thể tham chiếu property đó:

```xml
<properties>
    <revision>1.0.0-SNAPSHOT</revision>
</properties>

<version>${revision}</version>
```

Khi chạy với `-Drevision=2.5.0`, user property truyền từ dòng lệnh được Maven ưu tiên trong các phép nội suy model tương ứng, nên giá trị dùng trong lần chạy có thể là `2.5.0` thay vì giá trị mặc định trong POM.

Tuy nhiên, không phải mọi plugin parameter đều tự động dùng một property tùy ý. Plugin phải khai báo user property hoặc expression phù hợp, hoặc build phải truyền giá trị vào cấu hình plugin. Khi property không có tác dụng, hãy kiểm tra tài liệu/plugin descriptor và effective POM thay vì chỉ đổi tên biến.

### 5.3. Properties, profiles và parent POM

Maven có thể lấy property từ POM hiện tại, parent POM và profile đang active. Profile có thể thêm hoặc thay đổi properties, repositories, dependencies và một số phần build theo phạm vi Maven cho phép.

Profile có thể được kích hoạt bằng:

- Đối số `-Pprofile-id`.
- Điều kiện activation theo JDK, hệ điều hành, property hoặc file.
- Danh sách profile active trong settings.
- Cơ chế `activeByDefault` trong những trường hợp phù hợp.

Một profile khác được kích hoạt trong cùng POM có thể làm profile `activeByDefault` ngừng được áp dụng theo quy tắc activation của Maven. Vì vậy, khi giá trị khác nhau giữa local và CI, hãy xem profile nào thực sự active trong từng môi trường.

Ví dụ:

```xml
<profiles>
    <profile>
        <id>local</id>
        <properties>
            <app.environment>local</app.environment>
        </properties>
    </profile>
    <profile>
        <id>ci</id>
        <properties>
            <app.environment>ci</app.environment>
        </properties>
    </profile>
</profiles>
```

Chạy profile tương ứng:

```bash
./mvnw -Plocal verify
./mvnw -Pci verify
```

Nếu cả hai profile được kích hoạt hoặc có profile cùng tên ở POM và settings, cần xem model đã hợp nhất và danh sách profile active để hiểu giá trị thực tế.

### 5.4. Environment variable và system property trong Maven

Maven cho phép biểu thức truy cập một số nguồn hệ thống, ví dụ:

```xml
<properties>
    <build.user>${user.name}</build.user>
    <java.home.used>${java.home}</java.home.used>
    <repository.token>${env.REPOSITORY_TOKEN}</repository.token>
</properties>
```

`user.name` và `java.home` là system properties của JVM; `env.REPOSITORY_TOKEN` tham chiếu environment variable. Khả năng nội suy có thể khác nhau theo ngữ cảnh model/plugin và phiên bản Maven, vì vậy cần kiểm tra giá trị qua công cụ tương ứng.

Không in token hoặc password ra log khi truy tìm giá trị. Nếu cần xác nhận biến bí mật đã được cấp, hãy kiểm tra sự tồn tại hoặc trạng thái cấu hình mà không hiển thị nội dung của nó.

## 6. Plugin và giá trị mặc định cũng có thể quyết định kết quả

Một lỗi thường gặp là tìm thấy property trong POM hoặc Gradle build file nhưng plugin vẫn sử dụng giá trị khác. Nguyên nhân có thể là:

- Plugin không đọc property đó.
- Plugin có cấu hình riêng trong `plugins`/`build`.
- Plugin có default value riêng.
- Parent POM hoặc convention plugin đã cung cấp cấu hình.
- Task được cấu hình lại ở một vị trí khác.
- Giá trị được tính toán trong lúc thực thi task.

Ví dụ, Maven Compiler Plugin có thể nhận cấu hình `release` từ plugin configuration hoặc property được plugin hỗ trợ. Chỉ khai báo một property tên `java.version` không bảo đảm mọi compiler plugin đều sử dụng nó nếu plugin không liên kết property đó với tham số compiler.

Tương tự, Gradle task có thể được cấu hình bởi Java plugin, convention plugin của tổ chức và module build script. Khi tìm giá trị cuối, cần xem task/property sau khi plugin đã được áp dụng và cấu hình hoàn tất.

## 7. Phân biệt ba phiên bản Java trong một lần build

Một trong những nguyên nhân phổ biến nhất gây hiểu sai cấu hình là gộp ba khái niệm thành một:

1. **JDK/JVM chạy build tool**: Java được dùng để chạy Gradle hoặc Maven.
2. **JDK dùng để biên dịch/kiểm thử**: compiler/toolchain mà task compile hoặc test sử dụng.
3. **Phiên bản Java mục tiêu**: phiên bản ngôn ngữ, bytecode và API mà artifact được phép dựa vào.

Ví dụ, một CI agent có thể chạy Gradle bằng JDK 21, compile bằng toolchain JDK 21 và đặt `--release 17` để artifact tương thích với Java 17. Ứng dụng khi triển khai có thể chạy trên runtime Java 17.

Các lệnh kiểm tra môi trường:

```bash
java -version
javac -version
```

Với Gradle Wrapper:

```bash
./gradlew --version
```

Với Maven Wrapper:

```bash
./mvnw --version
```

`--version` cho biết build tool và JVM dùng để chạy nó. Để biết compiler toolchain hoặc `--release` thực tế, hãy xem build script/POM, cấu hình plugin và log của task compile. Không thể suy ra đầy đủ phiên bản mục tiêu chỉ từ `java -version`.

## 8. Cách truy tìm giá trị có hiệu lực trong Gradle

Nên truy tìm theo một trình tự cố định để tránh đọc quá nhiều tệp không liên quan.

### Bước 1 — Xác định tên và loại giá trị

Ví dụ cần biết `appVersion` là Gradle project property, JVM system property hay giá trị tính trong build script. Tìm nơi đọc nó:

```kotlin
providers.gradleProperty("appVersion")
System.getProperty("appVersion")
System.getenv("APP_VERSION")
```

Ba biểu thức trên đọc ba nguồn khác nhau.

### Bước 2 — Kiểm tra các nguồn theo đúng loại

Với project property, kiểm tra lần lượt:

1. Lệnh Gradle có `-PappVersion=...` hay không.
2. Có `-Dorg.gradle.project.appVersion=...` hay không.
3. Environment có `ORG_GRADLE_PROJECT_appVersion` hay không.
4. `GRADLE_USER_HOME/gradle.properties`.
5. `project-root/gradle.properties`.
6. `gradle.properties` trong Gradle installation.

Với system property, tìm tham số `-D`, `systemProp.*` trong `gradle.properties`, cấu hình daemon và biến môi trường launcher liên quan. Đừng áp dụng thứ tự project property cho system property một cách máy móc.

### Bước 3 — Kiểm tra settings và init script

Nếu giá trị liên quan đến plugin, repository, project inclusion hoặc toolchain, xem:

- `settings.gradle(.kts)`.
- `build.gradle(.kts)` ở root và module liên quan.
- Convention plugin hoặc included build nếu dự án dùng.
- Init script trong Gradle User Home.
- Các plugin đã áp dụng và cấu hình task.

### Bước 4 — Xem thông tin Gradle đã cấu hình

Một số lệnh hữu ích:

```bash
# Phiên bản Gradle và JVM chạy Gradle
./gradlew --version

# Các property của project hiện tại
./gradlew properties

# Danh sách task, bao gồm task được plugin thêm vào
./gradlew tasks --all

# Thông tin dependency của build script/plugin classpath
./gradlew buildEnvironment
```

`properties` giúp xem các project property mà Gradle hiển thị cho project. Nó không nhất thiết giải thích đầy đủ nguồn gốc của mọi giá trị hoặc mọi cấu hình nội bộ của plugin. Nếu cần biết dependency nào được chọn cho một configuration cụ thể, dùng `dependencyInsight`:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Lệnh này giúp xem dependency được chọn và lý do chọn phiên bản trong configuration chỉ định. Nó không phải công cụ truy nguồn mọi loại property.

### Bước 5 — Bật log khi cần thêm bằng chứng

```bash
./gradlew --info build
```

Nếu vẫn chưa rõ, có thể dùng `--debug`, nhưng log debug rất chi tiết và có nguy cơ chứa URL nội bộ hoặc dữ liệu nhạy cảm do plugin in ra. Chỉ chia sẻ log sau khi đã kiểm tra và che thông tin bí mật.

## 9. Cách truy tìm giá trị có hiệu lực trong Maven

Maven cung cấp các goal của Maven Help Plugin để xem model và settings sau khi hợp nhất. Các goal này là plugin goal, nên môi trường cần có plugin phù hợp trong local repository hoặc truy cập được repository để tải plugin.

### Bước 1 — Xác định property được đọc ở đâu

Tìm biểu thức trong POM, parent POM, profile và plugin configuration:

```xml
<properties>
    <app.environment>local</app.environment>
</properties>

<configuration>
    <environment>${app.environment}</environment>
</configuration>
```

Sau đó xác định property có thể đến từ `-D`, profile, parent POM, settings hay environment variable hay không.

### Bước 2 — Xem effective POM

```bash
./mvnw help:effective-pom -Dverbose
```

Effective POM là model sau khi Maven áp dụng parent, inheritance, profile active và các phần cấu hình liên quan. Với chế độ verbose được plugin hỗ trợ, output có thể kèm chú thích nguồn gốc phần tử để giúp truy vết.

Nếu chỉ muốn lưu kết quả ra file:

```bash
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Đây là bằng chứng quan trọng khi nghi ngờ cấu hình trong parent POM hoặc profile đã làm thay đổi cấu hình project.

### Bước 3 — Xem effective settings và profile active

```bash
./mvnw help:effective-settings
./mvnw help:active-profiles
```

Effective settings giúp xem cấu hình settings sau khi global và user settings được hợp nhất. Active profiles cho biết profile nào thực sự được kích hoạt trong lần chạy.

Nếu nghi ngờ mirror, proxy hoặc local repository, kiểm tra effective settings và tệp settings đang được chọn bằng `-s`/`-gs`.

### Bước 4 — Đọc giá trị của một expression cụ thể

```bash
./mvnw help:evaluate \
    -Dexpression=app.environment \
    -q \
    -DforceStdout
```

Goal `help:evaluate` giúp hiển thị giá trị expression Maven có thể phân giải trong project. Nếu giá trị không xuất hiện như mong đợi, hãy kiểm tra expression có thuộc model/property mà goal hỗ trợ và profile tương ứng đã active hay chưa.

Không dùng lệnh này để in secret. Nếu expression tham chiếu token hoặc password, hãy kiểm tra cấu hình theo cách không tiết lộ giá trị.

### Bước 5 — Xem dependency và log phân giải

```bash
./mvnw dependency:tree
```

Lệnh này cho biết dependency graph thực tế của project, gồm các dependency bắc cầu và một số thông tin về phiên bản được chọn. Khi cần log chi tiết hơn:

```bash
./mvnw -X verify
```

`-X` tạo debug log rất dài và có thể để lộ đường dẫn, repository URL hoặc dữ liệu nhạy cảm. Hãy kiểm tra log trước khi gửi cho người khác.

## 10. Một quy trình chung để tìm giá trị có hiệu lực

Có thể dùng quy trình sau cho cả Gradle và Maven:

```text
1. Xác định giá trị cần truy tìm
             |
             v
2. Xác định loại property và thành phần đọc nó
             |
             v
3. Liệt kê các nguồn cấu hình có thể áp dụng
             |
             v
4. Áp dụng thứ tự ưu tiên đúng của loại property đó
             |
             v
5. Xem cấu hình đã hợp nhất / task / profile thực tế
             |
             v
6. Đối chiếu log hoặc dependency graph khi cần
             |
             v
7. Thay đổi đúng nguồn sở hữu và chạy lại để xác nhận
```

Ví dụ cần tìm URL repository cuối cùng:

1. Xác định build tool đang dùng là Gradle hay Maven.
2. Xác định repository được khai báo trong settings/build script hoặc POM.
3. Kiểm tra Gradle init script hoặc Maven mirror trong settings.
4. Kiểm tra biến môi trường proxy và cấu hình người dùng.
5. Xem log phân giải để biết URL thực tế được truy cập.
6. Chỉnh đúng nguồn cấu hình và xác nhận lại bằng một lần build.

Ví dụ cần tìm Java compiler đang dùng:

1. Xem JDK chạy build tool bằng `./gradlew --version` hoặc `./mvnw --version`.
2. Kiểm tra Gradle Java toolchain hoặc Maven Toolchains Plugin.
3. Kiểm tra compiler plugin và tùy chọn `release`/source/target.
4. Xem log compile để xác định compiler thực tế.
5. Đối chiếu với runtime Java mà sản phẩm cần hỗ trợ.

## 11. Sửa ở đâu để kết quả ổn định?

Khi đã tìm được giá trị có hiệu lực, hãy xác định nơi nên sửa dựa trên phạm vi mong muốn:

| Mục tiêu | Nơi nên xem xét |
|---|---|
| Thay đổi quy tắc chung cho cả nhóm | Build script/settings hoặc POM được commit |
| Thay đổi dependency mặc định cho project | Dependency declaration/version catalog hoặc dependency management |
| Thay đổi giá trị riêng cho một lần CI | Tham số dòng lệnh hoặc environment variable được thiết kế rõ trong build |
| Cấu hình proxy/credential của người dùng | User settings hoặc secret/environment của máy/CI |
| Thay đổi Gradle/Maven version | Wrapper properties và các tệp wrapper liên quan |
| Thay đổi JVM chạy build tool | `JAVA_HOME`, `org.gradle.java.home`, `org.gradle.jvmargs`, `MAVEN_OPTS` hoặc `.mvn/jvm.config` theo trường hợp |
| Thay đổi JDK compile | Java toolchain hoặc Maven toolchain/plugin configuration |
| Thay đổi Java API/bytecode mục tiêu | `--release` hoặc cấu hình compiler plugin tương ứng |
| Thay đổi cấu hình lúc ứng dụng chạy | Runtime config, JVM arguments hoặc environment của ứng dụng |

Không nên sửa cấu hình người dùng để giải quyết một yêu cầu cần áp dụng cho cả nhóm; thay đổi đó sẽ không tự đi cùng repository. Ngược lại, không nên đưa credential hoặc đường dẫn cục bộ vào build file chung.

## 12. Những nhầm lẫn thường gặp

**Cho rằng dòng xuất hiện trong `gradle.properties` luôn là giá trị cuối.** Gradle có thể nhận project property từ dòng lệnh, system property theo quy ước hoặc environment variable với ưu tiên cao hơn. Cần xác định property được đọc qua API nào.

**Cho rằng `-D` có cùng ý nghĩa ở Gradle và Maven.** Gradle dùng `-D` để đặt system property cho JVM; Maven dùng `-D` để đặt user property phục vụ model/plugin, đồng thời giá trị cũng có thể được nhìn thấy như system property trong JVM. Cần phân biệt ngữ cảnh.

**Cho rằng effective POM hiển thị mọi cấu hình runtime.** Effective POM cho thấy Maven project model đã hợp nhất. Nó không hiển thị toàn bộ environment variable, JVM runtime options hoặc cách ứng dụng đọc cấu hình sau khi khởi chạy.

**Cho rằng một profile luôn active vì có khai báo trong POM.** Profile phải được kích hoạt theo điều kiện hoặc lựa chọn. Hãy xem danh sách active profiles của lần chạy cụ thể.

**Cho rằng wrapper quyết định JDK compile.** Wrapper chọn phiên bản Gradle/Maven. JDK chạy build tool và JDK toolchain dùng để biên dịch là những lựa chọn riêng.

**Cho rằng plugin sẽ đọc mọi property có tên quen thuộc.** Plugin chỉ dùng property được khai báo hoặc liên kết trong cấu hình của nó. Kiểm tra plugin parameter và effective configuration trước khi kết luận.

**Chia sẻ debug log mà không kiểm tra.** Log `--debug` của Gradle hoặc `-X` của Maven có thể chứa URL nội bộ, đường dẫn máy và dữ liệu nhạy cảm. Hãy lọc/redact trước khi chia sẻ.

## 13. Những điều cần ghi nhớ

- Giá trị có hiệu lực phụ thuộc loại property và thành phần đọc nó; không có một thứ tự ưu tiên chung cho tất cả cấu hình.
- Với Gradle project property, `-P` có ưu tiên cao; system property `org.gradle.project.*`, environment `ORG_GRADLE_PROJECT_*` và các tệp `gradle.properties` cung cấp những nguồn tiếp theo theo quy tắc của Gradle.
- Gradle `-D` đặt JVM system property; Gradle `-P` đặt project property.
- Maven `-D` đặt user property; POM, parent, profile và plugin configuration cùng tham gia tạo model/cấu hình cuối.
- Maven user settings được hợp nhất với global settings và có thể ghi đè phần tương ứng.
- Effective POM, effective settings, active profiles, Gradle `properties`, dependency insight và log là bằng chứng để truy tìm cấu hình thực tế.
- JDK chạy build tool, JDK compiler/toolchain và Java version mục tiêu là các giá trị riêng.
- Sửa nguồn cấu hình phù hợp với phạm vi mong muốn; giữ credential trong secret store và kiểm tra log trước khi chia sẻ.

Khi một giá trị không như mong đợi, đừng bắt đầu bằng cách sửa ngẫu nhiên nhiều tệp. Hãy xác định loại giá trị, tìm nơi tiêu thụ, liệt kê nguồn có thể áp dụng, xem cấu hình đã hợp nhất và đối chiếu bằng chứng từ build tool. Khi biết nguồn nào đang quyết định kết quả, ta có thể sửa đúng chỗ và làm cho hành vi build rõ ràng giữa máy cá nhân và CI.
